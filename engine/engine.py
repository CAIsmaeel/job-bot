"""Finance job engine v0: reads jobs straight from company career sites (no LinkedIn / Naukri).

Flow per company:
  1. discover: open the careers page (and a few job-search links on it), detect the hiring system (ATS)
  2. fetch: call that system's public job feed with finance keywords, India only where the feed allows
  3. filter: keep jobs whose TITLE is a finance role and whose location is in India
Output (engine/out/): jobs.json (all current), new.json (first seen this run), report.md (per company), state.json (seen ids)

Polite: public pages only, no login, small pages, short pauses, a handful of companies at a time.
"""
import json, os, re, time, html, hashlib, sys
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin, quote
from concurrent.futures import ThreadPoolExecutor
import requests
import seo

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
UA = "Mozilla/5.0 (compatible; FinanceJobEngine/0.1)"
T = 25
TERMS = ["finance", "accounting", "accountant", "tax", "audit", "treasury", "controller", "FP&A"]
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ---------------- finance + India filters (on the job TITLE) ----------------
CATS = [
    ("FP&A / Business Finance", r"fp&a|fpa\b|financial planning|business finance|finance business partner|\bfbp\b|commercial finance|budget|forecast|management reporting|\bmis\b"),
    ("Accounts Payable / P2P", r"accounts payable|\bp2p\b|ptp\b|procure to pay|invoice processing|vendor payment"),
    ("Accounts Receivable / O2C", r"accounts receivable|\bo2c\b|otc\b|order to cash|ar collections?|credit control|billing|cash application|\bi2c\b"),
    ("Record to Report / GL", r"\br2r\b|\brtr\b|record to report|general ledger|\bgl\b|reconciliation|month.end|close\b|intercompany|fixed asset"),
    ("Controllership / Reporting", r"controller|controllership|financial reporting|statutory|consolidation|ifrs|ind ?as|us gaap|technical accounting|financial control|product control"),
    ("Tax", r"\btax|gst|transfer pricing|indirect tax|direct tax"),
    ("Audit / Assurance / SOX", r"audit|assurance|sox\b|internal control|ifc\b"),
    ("Treasury", r"treasury|cash management|liquidity"),
    ("Costing", r"cost account|costing|cost controller|product cost"),
    ("Deals / Valuation / IB", r"valuation|m&a|mergers|transaction|due diligence|deal advisory|investment banking|corporate development|equity research"),
    ("Risk / Credit", r"credit risk|credit analyst|market risk|financial risk|underwrit"),
    ("Payroll", r"payroll"),
    ("Finance Transformation / Systems", r"finance transformation|finance systems?|sap fi|fico|s/4hana finance|oracle financials|epm\b"),
    ("Accounting / Finance (general)", r"accountant|accounting|accounts\b|finance|financial|\bca\b|chartered accountant|\bcma\b|\bacca\b|cfo|f&a"),
]
CATS = [(n, re.compile(p, re.I)) for n, p in CATS]
NOT_FIN = re.compile(r"software|developer|engineer(?!ing finance)|architect|devops|\bqa\b|tester|designer|data scientist|"
                     r"full ?stack|front ?end|back ?end|sales executive|relationship manager|^rm\b|^rm[- ]|\brm-|field sales|"
                     r"workday hcm|oracle hcm|successfactors|servicenow|salesforce|cyber|security analyst|"
                     r"hr business partner|recruiter|talent acquisition|marketing|nurse|driver|technician|mechanic|electrical|mechanical|"
                     r"lending collection|collections? (executive|officer|agent)|area collection|collection manager|recovery|tele ?caller|"
                     r"quality (auditor|analyst)|\bvoice\b|design assurance|product manag|program manag|product team|"
                     r"strategic accounts|key accounts?|account (manager|executive|director)|\bit due diligence|"
                     r"housing finance.*(sales|product)|loan officer|\bsales\b(?! tax| accounting| audit| finance)|"
                     r"identity|governance user|access management|\biam\b|user reconciliation|business development", re.I)
INDIA = re.compile(r"\bindia\b|\bind\b|, ?in\b|mumbai|navi mumbai|thane|pune|bengaluru|bangalore|hyderabad|chennai|gurgaon|gurugram|"
                   r"noida|delhi|kolkata|ahmedabad|vadodara|jaipur|kochi|coimbatore|chandigarh|indore|nagpur|lucknow|bhubaneswar|"
                   r"vizag|visakhapatnam|mysore|mysuru|trivandrum|thiruvananthapuram|goa|surat|jamnagar|bhopal|maharashtra|karnataka|"
                   r"telangana|tamil nadu|haryana|uttar pradesh|west bengal|gujarat|kerala|rajasthan", re.I)
FOREIGN = re.compile(r"\b(usa|united states|united kingdom|\buk\b|london|poland|philippines|manila|mexico|brazil|singapore|"
                     r"dubai|china|germany|spain|portugal|costa rica|malaysia|kuala lumpur|hungary|romania|czech|canada|australia)\b", re.I)


def category(title):
    t = title or ""
    if not t or NOT_FIN.search(t):
        return None
    for name, rx in CATS:
        if rx.search(t):
            return name
    return None


def tidy_title(t):
    t = clean(str(t or "")).rstrip("_ ")
    t = re.sub(r"(_[0-9]{2,})+$", "", t)                 # internal codes like _0412_4289_1017039
    t = re.sub(r"\s*_\s*", " - ", t)
    t = re.sub(r"\s*[(\[]\s*$", "", t)                  # dangling bracket
    return t.strip(" -")


def tidy_loc(l):
    l = clean(str(l or ""))
    l = re.sub(r"\b\d{6}\b", "", l)                       # pin codes
    l = re.sub(r",\s*IN\b", ", India", l)
    parts, out = [p.strip(" ,|()") for p in re.split(r"[,|]", l)], []
    for p in parts:
        p = re.sub(r"\bIndia(\s+India)+\b", "India", p, flags=re.I)
        if p and p.lower() not in [o.lower() for o in out]:
            out.append(p)
    return ", ".join(out)


def in_india(loc, title="", default=None):
    s = f"{loc or ''} {title or ''}"
    if INDIA.search(s):
        return True
    if FOREIGN.search(s):
        return False
    return default


# ---------------- http helpers ----------------
_tl = {}


def sess():
    import threading
    k = threading.get_ident()
    if k not in _tl:
        s = requests.Session()
        s.headers.update({"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.8"})
        _tl[k] = s
    return _tl[k]


import threading
WD_LOCK = threading.Lock()   # Workday sites share one backend: talk to them one request at a time
WD_BLOCKS = [0]              # consecutive refusals; after 3 the rest of Workday is skipped this run


class Skipped(Exception):
    pass


def _call(method, url, **kw):
    slow = "myworkdayjobs.com" in url
    if slow and WD_BLOCKS[0] >= 3:
        raise Skipped("Workday is refusing this server today, skipped")
    for wait in ((0, 10) if slow else (0, 8, 20)):
        if wait:
            time.sleep(wait)
        if slow:
            with WD_LOCK:
                time.sleep(1.5)
                r = sess().request(method, url, timeout=T, allow_redirects=True, **kw)
        else:
            time.sleep(0.6)
            r = sess().request(method, url, timeout=T, allow_redirects=True, **kw)
        if r.status_code != 429:
            if slow and r.ok and "json" in r.headers.get("Content-Type", ""):
                WD_BLOCKS[0] = 0
            return r
    if slow:
        WD_BLOCKS[0] += 1
    return r


def get(url, **kw):
    return _call("GET", url, **kw)


def post(url, **kw):
    kw.setdefault("headers", {"Accept": "application/json", "Content-Type": "application/json"})
    return _call("POST", url, **kw)


def clean(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s.replace("<![CDATA[", "").replace("]]>", "")).strip()


# ---------------- discovery ----------------
def identify(blob, url):
    """Return a platform config dict from page text + url, or None."""
    m = re.search(r"https?://([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]+)", blob)
    if m and m.group(3).lower() not in ("wday", "login", "en-us"):
        return {"platform": "workday", "tenant": m.group(1), "wd": m.group(2), "site": m.group(3)}
    m = re.search(r"https?://([\w.-]+\.oraclecloud\.com)/hcmUI/CandidateExperience/[a-z]{2}(?:-[A-Z]{2})?/sites/([\w-]+)", blob)
    if m:
        return {"platform": "oracle", "host": m.group(1), "site": m.group(2)}
    m = re.search(r"(?:careers|jobs|api)\.smartrecruiters\.com/(?:v1/companies/)?([A-Za-z0-9_-]{2,})", blob)
    if m and m.group(1).lower() not in ("static", "assets", "api", "careers", "jobs", "js", "css", "v1"):
        return {"platform": "smartrecruiters", "company": m.group(1)}
    m = re.search(r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board(?:/js)?\?for=)?([A-Za-z0-9_-]+)", blob)
    if m and m.group(1) not in ("embed",):
        return {"platform": "greenhouse", "token": m.group(1)}
    for m in re.finditer(r"([a-z0-9-]+)\.keka\.com", blob, re.I):
        if m.group(1).lower() not in ("www", "cdn", "app", "help", "stkekastaticdev"):
            return {"platform": "keka", "host": m.group(1).lower() + ".keka.com"}
    m = re.search(r"([a-z0-9-]+)\.ripplehire\.com", blob, re.I)
    if m and m.group(1).lower() not in ("www", "cdn", "static"):
        return {"platform": "ripplehire", "host": m.group(1).lower() + ".ripplehire.com"}
    m = re.search(r"jobs\.lever\.co/([A-Za-z0-9_-]+)", blob)
    if m:
        return {"platform": "lever", "name": m.group(1)}
    m = re.search(r"https?://([\w-]+\.eightfold\.ai)", blob)
    if m:
        d = re.search(r"domain[\"']?\s*[:=]\s*[\"']([\w.-]+\.[a-z]{2,})", blob)
        return {"platform": "eightfold", "host": m.group(1), "domain": d.group(1) if d else ""}
    if re.search(r"phenompeople|phApp\.|ph-page|\"phenom", blob, re.I):
        p = urlparse(url)
        lp = re.match(r"^/([a-z]{2,8}/[a-z]{2})(/|$)", p.path)
        return {"platform": "phenom", "origin": f"{p.scheme}://{p.netloc}", "prefix": "/" + lp.group(1) if lp else ""}
    m = re.search(r"(https?://[\w.-]+/[\w-]+)/(?:JobDetail|SearchJobs)\b", blob)
    if m and "avature" not in m.group(1):
        return {"platform": "avature", "base": m.group(1)}
    if re.search(r"rmkcdn|jobs2web|successfactors|/services/rss/job", blob, re.I) or re.search(r"/job/[^/\"']+/\d{8,}/", blob):
        p = urlparse(url)
        return {"platform": "successfactors", "origin": f"{p.scheme}://{p.netloc}"}
    return None


LINK_HINT = re.compile(r"job|career|opening|vacanc|search|position|opportunit|apply|join", re.I)


def discover(name, url):
    seen, queue, tried = set(), [url], 0
    while queue and tried < 7:
        u = queue.pop(0)
        if u in seen:
            continue
        seen.add(u)
        tried += 1
        try:
            r = get(u)
        except Exception:
            continue
        if r.status_code >= 400:
            continue
        blob = r.text[:600000] + " " + r.url
        cfg = identify(blob, r.url)
        if cfg:
            cfg["found_on"] = r.url
            return cfg, r
        if tried == 1:
            links = []
            for href, text in re.findall(r'<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', r.text, re.S | re.I):
                full = urljoin(r.url, html.unescape(href))
                if full.startswith("http") and (LINK_HINT.search(href) or LINK_HINT.search(clean(text))):
                    if not re.search(r"\.(pdf|jpg|png|svg)$|linkedin\.com|facebook|twitter|instagram|youtube", full, re.I):
                        links.append(full)
            # prefer links that leave the main site (often the ATS) and "search jobs" links
            links.sort(key=lambda x: (urlparse(x).netloc == urlparse(r.url).netloc, not re.search(r"search|job", x, re.I)))
            for l in links[:10]:
                if l not in seen:
                    queue.append(l)
            first = r
    cfg = probe_boards(name)
    if cfg:
        return cfg, None
    return {"platform": "sitemap", "origin": "{0.scheme}://{0.netloc}".format(urlparse(url)), "probed": True}, None


def slugs(name):
    base = re.sub(r"\(.*?\)", " ", name).lower().replace("&", " and ")
    words = re.findall(r"[a-z0-9]+", base)
    drop = {"india", "bank", "group", "limited", "ltd", "the", "and", "inc", "technologies", "services"}
    core = [w for w in words if w not in drop] or words
    out = []
    for s in ("".join(words), "".join(core), "-".join(core), core[0] if core else ""):
        if s and s not in out:
            out.append(s)
    return out[:4]


def probe_boards(name):
    """Careers page did not reveal the hiring system: ask the public job-board APIs by company slug.
    A board counts only if it has jobs in India, so a same-named foreign company is not picked up."""
    for s in slugs(name):
        tests = [
            ("greenhouse", f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs", lambda j: any(INDIA.search((x.get("location") or {}).get("name") or "") for x in j.get("jobs") or []), {"token": s}),
            ("lever", f"https://api.lever.co/v0/postings/{s}?mode=json", lambda j: isinstance(j, list) and any(INDIA.search(str(x.get("categories", {}).get("location") or "")) for x in j), {"name": s}),
            ("smartrecruiters", f"https://api.smartrecruiters.com/v1/companies/{s}/postings?limit=1&country=in",
             lambda j: j.get("totalFound"), {"company": s}),
        ]
        for plat, u, ok, cfg in tests:
            try:
                r = get(u)
                if r.ok and ok(r.json()):
                    return {"platform": plat, "found_on": u, **cfg}
            except Exception:
                pass
    return None


# ---------------- adapters: each returns list of dicts {id,title,location,url,posted} ----------------
def a_workday(c):
    base = f"https://{c['tenant']}.{c['wd']}.myworkdayjobs.com"
    api = f"{base}/wday/cxs/{c['tenant']}/{c['site']}/jobs"
    home = f"{base}/en-US/{c['site']}"
    try:
        get(home)
    except Exception:
        pass
    hdr = {"Accept": "application/json", "Content-Type": "application/json", "Origin": base, "Referer": home}
    # find the India facet if the site has one
    facets = {}
    r = post(api, json={"limit": 1, "offset": 0, "searchText": "", "appliedFacets": {}}, headers=hdr)
    r.raise_for_status()

    def walk(node, param=None):
        if isinstance(node, list):
            for x in node:
                walk(x, param)
        elif isinstance(node, dict):
            param = node.get("facetParameter", param)
            if (node.get("descriptor") or "").strip().lower() == "india" and param and node.get("id"):
                facets.setdefault(param, []).append(node["id"])
            for v in node.values():
                if isinstance(v, (list, dict)):
                    walk(v, param)
    walk(r.json().get("facets"))
    india_facet = {k: v for k, v in facets.items() if "country" in k.lower() or "location" in k.lower()} or facets
    out, ids = [], set()
    for term in TERMS[:6]:
        for off in range(0, 60, 20):
            body = {"limit": 20, "offset": off, "searchText": term, "appliedFacets": india_facet}
            j = post(api, json=body, headers=hdr).json()
            posts = j.get("jobPostings", [])
            for p in posts:
                path = p.get("externalPath", "")
                if path in ids:
                    continue
                ids.add(path)
                out.append({"id": path, "title": p.get("title"), "location": p.get("locationsText"),
                            "url": f"{base}/en-US/{c['site']}{path}", "posted": p.get("postedOn"),
                            "_detail": f"{base}/wday/cxs/{c['tenant']}/{c['site']}{path}",
                            "_india_facet": bool(india_facet)})
            if len(posts) < 20:
                break
    # resolve "N Locations" for finance titles only (capped)
    n = 0
    for j in out:
        if j["_india_facet"]:
            j["location"] = (j["location"] or "") + " (India)"
        elif category(j["title"]) and not INDIA.search(j["location"] or "") and n < 25:
            n += 1
            try:
                d = get(j["_detail"], headers={"Accept": "application/json", "Referer": home}).json().get("jobPostingInfo", {})
                j["location"] = " | ".join([d.get("location") or ""] + (d.get("additionalLocations") or []) + [str(d.get("country", {}).get("descriptor", ""))])
            except Exception:
                pass
    return out


def a_oracle(c):
    out, ids = [], set()
    for term in TERMS:
        for off in range(0, 200, 25):
            api = (f"https://{c['host']}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true"
                   f"&expand=requisitionList.secondaryLocations&finder=findReqs;siteNumber={c['site']},"
                   f"keyword={quote(term)},location=India,limit=25,offset={off},sortBy=POSTING_DATES_DESC")
            it = (get(api).json().get("items") or [{}])[0]
            rl = it.get("requisitionList", []) or []
            for p in rl:
                if p.get("Id") in ids:
                    continue
                ids.add(p.get("Id"))
                out.append({"id": p.get("Id"), "title": p.get("Title"), "location": (p.get("PrimaryLocation") or "") + " India",
                            "url": f"https://{c['host']}/hcmUI/CandidateExperience/en/sites/{c['site']}/job/{p.get('Id')}",
                            "posted": p.get("PostedDate")})
            if len(rl) < 25:
                break
    return out


def a_smartrecruiters(c):
    out, ids = [], set()
    for term in TERMS:
        api = f"https://api.smartrecruiters.com/v1/companies/{c['company']}/postings?country=in&q={quote(term)}&limit=100"
        for p in get(api).json().get("content", []):
            if p.get("id") in ids:
                continue
            ids.add(p.get("id"))
            loc = p.get("location") or {}
            out.append({"id": p.get("id"), "title": p.get("name"), "location": f"{loc.get('city', '')}, India",
                        "url": f"https://jobs.smartrecruiters.com/{c['company']}/{p.get('id')}", "posted": p.get("releasedDate")})
    return out


def a_greenhouse(c):
    j = get(f"https://boards-api.greenhouse.io/v1/boards/{c['token']}/jobs").json()
    return [{"id": p.get("id"), "title": p.get("title"), "location": (p.get("location") or {}).get("name"),
             "url": p.get("absolute_url"), "posted": p.get("updated_at")} for p in j.get("jobs", [])]


def a_lever(c):
    j = get(f"https://api.lever.co/v0/postings/{c['name']}?mode=json").json()
    return [{"id": p.get("id"), "title": p.get("text"), "location": (p.get("categories") or {}).get("location"),
             "url": p.get("hostedUrl"), "posted": p.get("createdAt")} for p in j]


def a_keka(c):
    """Keka career portals: the portal's own public job widget feed."""
    host = c["host"]
    r = get(f"https://{host}/careers")
    m = re.search(r"/ats/documents/([0-9a-f-]{36})/careerportal", r.text) or re.search(r"embedjobs/js/([0-9a-f-]{36})", r.text)
    if not m:
        return []
    jobs = get(f"https://{host}/careers/api/embedjobs/default/active/{m.group(1)}").json() or []
    out = []
    for p in jobs:
        locs = p.get("jobLocations") or p.get("locations") or []
        loc = ", ".join(filter(None, ((x.get("city") or x.get("name") or "") if isinstance(x, dict) else str(x) for x in locs))) \
            or p.get("location") or p.get("city") or "India"
        out.append({"id": p.get("id"), "title": p.get("title"), "location": loc,
                    "url": f"https://{host}/careers/jobdetails/{p.get('id')}", "posted": p.get("publishedOn") or p.get("createdOn")})
    return out


def a_ripplehire(c):
    """RippleHire career sites (HDFC Bank, Axis Bank, Tata Steel ...): the page's own job search call."""
    host = c["host"]
    page = None
    for start in ("/candidate/careers", "/candidate/", "/ripplehire/careers"):
        r = get(f"https://{host}{start}")
        m = re.search(r'id="token"\s+value="([^"]+)"', r.text) or re.search(r"token=(\w+)", r.url)
        if r.ok and m:
            page = m.group(1)
            break
    if not page:
        return []
    out = []
    for n in range(12):
        prm = {"page": n, "search": "*:*", "token": page, "source": "CAREERSITE", "pagesize": 100}
        j = post(f"https://{host}/candidate/candidatejobsearch", data={"careerSiteUrlParams": json.dumps(prm), "lang": "en"},
                 headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}).json()
        jobs = j.get("jobVoList") or []
        for p in jobs:
            seq = p.get("jobSeq") or p.get("jobId")
            out.append({"id": seq, "title": p.get("jobTitle"), "location": p.get("locations") or p.get("jobLocation") or "India",
                        "url": f"https://{host}/candidate/?token={page}&source=CAREERSITE#detail/job/{seq}",
                        "posted": p.get("jobPostingDate") or p.get("careerSiteDate")})
        if len(jobs) < 100 or len(out) >= (j.get("totalJobCount") or 0):
            break
    return out


def a_eightfold(c):
    out, ids = [], set()
    dom = c.get("domain") or c.get("company_domain") or ""
    for term in TERMS:
        api = f"https://{c['host']}/api/apply/v2/jobs?domain={dom}&query={quote(term)}&location=India&start=0&num=50"
        for p in get(api).json().get("positions", []):
            if p.get("id") in ids:
                continue
            ids.add(p.get("id"))
            out.append({"id": p.get("id"), "title": p.get("name"), "location": p.get("location"),
                        "url": p.get("canonicalPositionUrl") or f"https://{c['host']}/careers/job/{p.get('id')}",
                        "posted": p.get("t_create")})
    return out


def a_phenom(c):
    out, ids = [], set()
    for term in TERMS[:5]:
        u = f"{c['origin']}{c['prefix']}/search-results?keywords={quote(term)}"
        t = get(u).text
        jobs = []
        i = t.find('"eagerLoadRefineSearch"')
        if i >= 0:
            try:
                obj, _ = json.JSONDecoder().raw_decode(t[t.index("{", i):])
                jobs = (obj.get("data") or {}).get("jobs", []) or []
            except Exception:
                jobs = []
        if not jobs:
            for blk in re.findall(r'\{[^{}]*"jobId"\s*:\s*"[^"]+"[^{}]*\}', t):
                try:
                    jobs.append(json.loads(blk))
                except Exception:
                    pass
        for p in jobs:
            jid = p.get("jobId") or p.get("reqId")
            if not jid or jid in ids:
                continue
            ids.add(jid)
            out.append({"id": jid, "title": p.get("title"), "location": p.get("location") or p.get("cityStateCountry") or p.get("country"),
                        "url": p.get("applyUrl") or f"{c['origin']}{c['prefix']}/job/{jid}", "posted": p.get("postedDate")})
    return out


def a_avature(c):
    out, ids = [], set()
    for term in TERMS[:6]:
        t = get(f"{c['base']}/SearchJobs?keyword={quote(term)}&jobRecordsPerPage=50").text
        for href, text in re.findall(r'<a[^>]+href=["\']([^"\']*/JobDetail/[^"\']+)["\'][^>]*>(.*?)</a>', t, re.S | re.I):
            title = clean(text)
            if not title or href in ids:
                continue
            ids.add(href)
            # location usually sits in the next few hundred characters of the listing
            i = t.find(href)
            near = clean(t[i:i + 1500])
            out.append({"id": href, "title": title, "location": near[:300], "url": urljoin(c["base"] + "/", href), "posted": None})
    return out


def a_successfactors(c):
    out, ids = [], set()
    for term in TERMS:
        for start in range(0, 100, 25):
            t = get(f"{c['origin']}/search/?q={quote(term)}&locationsearch=India&startrow={start}").text
            rows = re.findall(r'<tr class="data-row[^"]*">(.*?)</tr>', t, re.S)
            for row in rows:
                a = re.search(r'href="(/job/[^"]+)"[^>]*>(.*?)</a>', row, re.S)
                if not a or a.group(1) in ids:
                    continue
                ids.add(a.group(1))
                loc = re.search(r'class="jobLocation"[^>]*>(.*?)</span>', row, re.S)
                date = re.search(r'class="jobDate"[^>]*>(.*?)</span>', row, re.S)
                out.append({"id": a.group(1), "title": clean(a.group(2)), "location": clean(loc.group(1)) if loc else "India",
                            "url": c["origin"] + a.group(1), "posted": clean(date.group(1)) if date else None})
            if len(rows) < 25:
                break
    if out:
        return out
    for term in TERMS:
        r = get(f"{c['origin']}/services/rss/job/?locale=en_US&keywords={quote(term)}")
        if r.status_code != 200 or "<item" not in r.text:
            continue
        for it in re.findall(r"<item>(.*?)</item>", r.text, re.S):
            title = clean((re.search(r"<title>(.*?)</title>", it, re.S) or [None, ""])[1])
            link = clean((re.search(r"<link>(.*?)</link>", it, re.S) or [None, ""])[1])
            if link in ids:
                continue
            ids.add(link)
            # CSB titles look like "Finance Executive (Mumbai, MH, IN, 400001)"
            m = re.match(r"(.*)\(([^()]*)\)\s*$", title)
            t, loc = (m.group(1).strip(), m.group(2)) if m else (title, "")
            loc = loc + (" India" if re.search(r",\s*IN\b", loc) else "")
            out.append({"id": link, "title": t, "location": loc, "url": link,
                        "posted": clean((re.search(r"<pubDate>(.*?)</pubDate>", it, re.S) or [None, ""])[1])})
    if not out:
        return a_sitemap(c)
    return out


def a_sitemap(c):
    """Fallback: read job URLs from sitemap(s); title and city come from the URL slug."""
    origin = c["origin"]
    try:
        r = get(origin + "/sitemap.xml")
    except Exception:
        return []
    if r.status_code != 200:
        return []
    locs = re.findall(r"<loc>(.*?)</loc>", r.text)
    subs = [l for l in locs if l.endswith(".xml") or "sitemap" in l.lower()][:6]
    for s in subs:
        try:
            locs += re.findall(r"<loc>(.*?)</loc>", get(s).text)
        except Exception:
            pass
    out, ids = [], set()
    for u in locs:
        m = re.search(r"/job/([^/]+)/([^/]+)/(\d+)/(\d+)", u)            # radancy: /job/<city>/<title>/<id>/<id>
        if m:
            city, title = m.group(1), m.group(2)
        else:
            m = re.search(r"/job/([^/]+)/(\d{6,})/?", u)                 # successfactors: /job/<City-TITLE-ST>/<id>/
            if not m:
                continue
            city, title = "", m.group(1)
        if u in ids:
            continue
        ids.add(u)
        out.append({"id": u, "title": title.replace("-", " ").replace("%20", " "), "location": city.replace("-", " "),
                    "url": u, "posted": None, "approx": True})
    return out


ADAPTERS = {"workday": a_workday, "oracle": a_oracle, "smartrecruiters": a_smartrecruiters, "greenhouse": a_greenhouse,
            "lever": a_lever, "eightfold": a_eightfold, "phenom": a_phenom, "avature": a_avature,
            "successfactors": a_successfactors, "ripplehire": a_ripplehire, "keka": a_keka, "sitemap": a_sitemap}


# ---------------- run ----------------
CACHE = {}
CACHE_DAYS = 7


def cached_cfg(name):
    c = CACHE.get(name)
    if not c or (c["cfg"].get("platform") == "sitemap" and not c["cfg"].get("probed")):
        return None
    try:
        age = (datetime.now(timezone.utc) - datetime.strptime(c["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).days
    except Exception:
        return None
    return c["cfg"] if age < CACHE_DAYS else None


def run_company(co):
    name, url = co["name"], co["careers"]
    rep = {"company": name, "careers": url}
    try:
        cfg = co.get("ats") or cached_cfg(name)
        if not cfg:
            cfg = discover(name, url)[0]
            CACHE[name] = {"cfg": cfg, "at": NOW}
        host = urlparse(url).netloc.split(".")
        cfg.setdefault("company_domain", ".".join(host[-3:] if host[-2] in ("co", "com") and len(host[-1]) == 2 else host[-2:]))
        rep["platform"] = cfg["platform"]
        rep["config"] = {k: v for k, v in cfg.items() if k != "platform"}
        try:
            raw = ADAPTERS[cfg["platform"]](cfg)
        except Exception:
            if cfg["platform"] != "workday":
                raise
            raw = []
        if cfg["platform"] == "workday" and not raw:
            # Workday turned us away: read the company's own public careers site list instead
            origins = {"{0.scheme}://{0.netloc}".format(urlparse(u)) for u in (url, cfg.get("found_on") or "") if u}
            for o in origins:
                if "myworkdayjobs.com" not in o:
                    raw += a_sitemap({"origin": o})
            rep["platform"] = "workday+site"
        if cfg["platform"] == "phenom" and not raw:
            raw = a_sitemap({"origin": cfg["origin"]})
            rep["platform"] = "phenom+sitemap"
    except Exception as e:
        rep.update(error=f"{type(e).__name__}: {str(e)[:160]}", raw=0, kept=0)
        return rep, []
    kept = []
    for j in raw:
        cat = category(j.get("title"))
        if not cat:
            continue
        india = in_india(j.get("location"), j.get("title"), default=co.get("india_default"))
        if not india:
            continue
        key = hashlib.sha1(f"{name}|{j.get('id')}".encode()).hexdigest()[:16]
        kept.append({"key": key, "company": name, "title": tidy_title(j.get("title")), "category": cat,
                     "location": tidy_loc(j.get("location"))[:120], "url": j.get("url"),
                     "posted": j.get("posted"), "platform": rep["platform"], "approx": bool(j.get("approx"))})
    # de-duplicate same title + location within a company
    seen, uniq = set(), []
    for j in kept:
        k = (j["title"].lower(), j["location"].lower()[:40])
        if k not in seen:
            seen.add(k)
            uniq.append(j)
    rep.update(raw=len(raw), kept=len(uniq))
    return rep, uniq


BRAND = os.environ.get("BRAND_NAME") or "Finance Jobs India"
SITE_URL = (os.environ.get("SITE_URL") or "").rstrip("/")
SIM_URL = os.environ.get("SIMULATOR_URL") or (SITE_URL + "/app/" if SITE_URL else "")


def build_page(jobs):
    t = open(os.path.join(HERE, "page_template.html"), encoding="utf-8").read()
    ist = datetime.now(timezone.utc).timestamp() + 5.5 * 3600
    upd = datetime.utcfromtimestamp(ist).strftime("%-I:%M %p, %-d %b") + " IST"
    practice = (f'<div class="practice"><p>Interview coming up? <a href="{html.escape(SIM_URL)}">Practise real ERP finance work</a> '
                f'in our simulator: postings, GR/IR, bank reconciliation, month-end close. Free demo, no sign-up.</p></div>') if SIM_URL else ""
    slim = [{k: j[k] for k in ("title", "company", "category", "location", "url", "first_seen")} for j in jobs]
    data = json.dumps(slim, ensure_ascii=False).replace("</", "<\\/")
    t = (t.replace("__JOBS__", data).replace("__UPDATED_ISO__", NOW).replace("__UPDATED__", upd)
          .replace("__PRACTICE__", practice + '<p class="browse"><a href="/jobs/browse/">Browse finance jobs by city, company or area</a></p>').replace("__BRAND__", html.escape(BRAND)))
    os.makedirs(os.path.join(OUT, "site"), exist_ok=True)
    open(os.path.join(OUT, "site", "index.html"), "w", encoding="utf-8").write(t)


TAGS = {"FP&A / Business Finance": "FPandA", "Accounts Payable / P2P": "AccountsPayable", "Accounts Receivable / O2C": "AccountsReceivable",
        "Record to Report / GL": "R2R", "Controllership / Reporting": "Controllership", "Tax": "Tax", "Audit / Assurance / SOX": "Audit",
        "Treasury": "Treasury", "Costing": "Costing", "Deals / Valuation / IB": "Valuation", "Risk / Credit": "CreditRisk",
        "Payroll": "Payroll", "Finance Transformation / Systems": "FinanceSystems", "Accounting / Finance (general)": "Accounting"}
CITY = [("Mumbai", r"mumbai|navi mumbai|thane"), ("Pune", r"pune"), ("Bengaluru", r"bengaluru|bangalore"), ("Hyderabad", r"hyderabad"),
        ("Chennai", r"chennai"), ("Gurugram", r"gurgaon|gurugram"), ("Noida", r"noida"), ("Delhi", r"delhi"), ("Kolkata", r"kolkata"),
        ("Ahmedabad", r"ahmedabad"), ("Vadodara", r"vadodara"), ("Jaipur", r"jaipur"), ("Kochi", r"kochi"), ("Coimbatore", r"coimbatore"),
        ("Chandigarh", r"chandigarh"), ("Indore", r"indore"), ("Nagpur", r"nagpur"), ("Lucknow", r"lucknow")]
CITY = [(n, re.compile(p, re.I)) for n, p in CITY]


def city_of(loc):
    hits = [n for n, rx in CITY if rx.search(loc or "")]
    if not hits:
        st = re.search(r"gujarat|maharashtra|karnataka|telangana|tamil nadu|haryana|kerala|rajasthan|west bengal|uttar pradesh", loc or "", re.I)
        return st.group(0).title() if st else "India"
    return hits[0] if len(hits) == 1 else f"{hits[0]} +{len(hits) - 1} more"


def nice_title(t):
    t = t.strip()
    if t and t == t.lower():                      # slug titles from sitemaps come in lower case
        small = {"and", "of", "the", "for", "in", "to", "a", "an", "&"}
        keep = {"r2r", "a2r", "p2p", "o2c", "gl", "ap", "ar", "fp&a", "sox", "gst", "tds", "ifrs", "hr", "it", "sap", "ca", "cma"}
        out = []
        for k, w in enumerate(t.split()):
            out.append(w.upper() if w in keep else (w if (w in small and k) else w.capitalize()))
        t = " ".join(out)
    return t


def channel_link():
    c = os.environ.get("TG_CHANNEL_ID") or ""
    return f"https://t.me/{c[1:]}" if c.startswith("@") else ""


def tg_send(tok, chat, text, button=None):
    """button: one (text, url) pair, or a list of them (one button per row)."""
    data = {"chat_id": chat, "text": text[:4090], "parse_mode": "HTML", "disable_web_page_preview": "true"}
    if button:
        rows = button if isinstance(button, list) else [button]
        data["reply_markup"] = json.dumps({"inline_keyboard": [[{"text": t, "url": u}] for t, u in rows]})
    try:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=T, data=data)
        print("telegram:", r.status_code, r.text[:100])
        if r.status_code == 429:
            time.sleep(int((r.json().get("parameters") or {}).get("retry_after", 20)) + 1)
            requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=T, data=data)
        return r.ok
    except Exception as ex:
        print("telegram error:", ex)
        return False


# ---------------- Daily Close: one journal-entry quiz a day on the channel ----------------
def post_daily_quiz(state):
    """Same question as entry 4 of today's Daily Close in the simulator (index (day*5) % N, day = IST day number)."""
    tok, chat = os.environ.get("TG_CHANNEL_TOKEN"), os.environ.get("TG_CHANNEL_ID")
    if not (tok and chat):
        return
    now = time.time() + 19800
    day, hour = int(now // 86400), int(now % 86400 // 3600)
    key = time.strftime("%Y-%m-%d", time.gmtime(day * 86400))
    if hour < 8 or state.get("daily_posted") == key:
        return
    try:
        E = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "daily_entries.json"), encoding="utf-8"))
    except Exception as ex:
        print("daily quiz: no question file", ex)
        return
    q = E[(day * 5) % len(E)]
    data = {"chat_id": chat, "question": ("Daily Close: " + q["q"])[:300], "options": json.dumps([o[:100] for o in q["o"]]),
            "type": "quiz", "correct_option_id": q["k"], "explanation": q["why"][:200], "is_anonymous": "true"}
    try:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendPoll", timeout=T, data=data)
        print("daily quiz:", r.status_code, r.text[:120])
        if r.ok:
            state["daily_posted"] = key
            if SIM_URL:
                tg_send(tok, chat, "3 more questions and your streak are waiting in today's Daily Close. Free, no sign-up.",
                        ("Open today's Daily Close", SIM_URL.rstrip("/") + "/#daily"))
    except Exception as ex:
        print("daily quiz error:", ex)


# ---------------- job details (read only for jobs we are about to post) ----------------
SKILLS = ["SAP", "SAP FICO", "S/4HANA", "Oracle", "Tally", "Excel", "Power BI", "SQL", "Python", "Alteryx", "Hyperion", "Blackline",
          "GST", "TDS", "Income Tax", "Transfer Pricing", "Ind AS", "IFRS", "US GAAP", "Consolidation", "Reconciliation",
          "Month-end close", "Budgeting", "Forecasting", "Variance analysis", "Financial modelling", "Valuation", "SOX",
          "Internal controls", "Statutory audit", "Accounts payable", "Accounts receivable", "Fixed assets", "Payroll",
          "Treasury", "Cash flow", "Costing", "MIS reporting", "Stakeholder management", "Credit analysis"]
SKILL_RX = [(k, re.compile(r"\b" + re.escape(k).replace(r"\ ", r"[\s-]") + r"\b", re.I)) for k in SKILLS]
QUALS = [("CA", r"\bCA\b|chartered accountant"), ("CMA", r"\bCMA\b|\bICWA\b|cost accountant"), ("ACCA", r"\bACCA\b"),
         ("CPA", r"\bCPA\b"), ("CFA", r"\bCFA\b"), ("MBA Finance", r"\bMBA\b|\bPGDM\b"), ("M.Com", r"\bM\.?\s?Com\b"),
         ("B.Com", r"\bB\.?\s?Com\b"), ("CS", r"company secretary")]
QUALS = [(n, re.compile(p, re.I)) for n, p in QUALS]


def _jsonld_job(t):
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', t, re.S | re.I):
        try:
            d = json.loads(m.group(1).strip())
        except Exception:
            continue
        for x in (d if isinstance(d, list) else d.get("@graph", [d]) if isinstance(d, dict) else []):
            if isinstance(x, dict) and x.get("@type") == "JobPosting":
                return x
    return None


def fetch_detail(j):
    """Return dict(text, type, mode, salary) for one job, best effort."""
    cfg = (CACHE.get(j["company"]) or {}).get("cfg") or {}
    plat, url, d = j.get("platform", ""), j.get("url") or "", {"text": ""}
    try:
        if plat == "ripplehire" and cfg.get("host"):
            m = re.search(r"token=(\w+).*#detail/job/(\w+)", url)
            if m:
                x = get(f"https://{cfg['host']}/candidate/candidatejobdetail",
                        params={"token": m.group(1), "jobSeq": m.group(2), "source": "CAREERSITE", "lang": "en"},
                        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}).json()
                d["text"] = clean(x.get("jobDesc") or x.get("jobDescription") or "")
                d["type"] = x.get("jobType")
        elif plat == "oracle" and cfg.get("host"):
            jid = url.rstrip("/").split("/")[-1]
            api = (f"https://{cfg['host']}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?expand=all&onlyData=true"
                   f'&finder=ById;Id="{jid}",siteNumber={cfg["site"]}')
            x = (get(api).json().get("items") or [{}])[0]
            d["text"] = " ".join(clean(x.get(k) or "") for k in ("ExternalDescriptionStr", "ExternalResponsibilitiesStr", "ExternalQualificationsStr"))
            d["type"] = x.get("JobSchedule") or x.get("JobType")
            d["mode"] = x.get("WorkplaceType")
        elif plat == "smartrecruiters" and cfg.get("company"):
            jid = url.rstrip("/").split("/")[-1]
            x = get(f"https://api.smartrecruiters.com/v1/companies/{cfg['company']}/postings/{jid}").json()
            sec = (x.get("jobAd") or {}).get("sections") or {}
            d["text"] = " ".join(clean((sec.get(k) or {}).get("text", "")) for k in ("jobDescription", "qualifications"))
            d["type"] = (x.get("typeOfEmployment") or {}).get("label")
            d["level"] = (x.get("experienceLevel") or {}).get("label")
        elif plat == "lever" and cfg.get("name"):
            jid = url.rstrip("/").split("/")[-1]
            x = get(f"https://api.lever.co/v0/postings/{cfg['name']}/{jid}").json()
            d["text"] = clean(x.get("descriptionPlain", "")) + " " + " ".join(clean(l.get("content", "")) for l in x.get("lists", []))
            d["type"] = (x.get("categories") or {}).get("commitment")
            d["mode"] = x.get("workplaceType")
        elif plat == "greenhouse" and cfg.get("token"):
            jid = re.findall(r"\d{5,}", url)[-1]
            x = get(f"https://boards-api.greenhouse.io/v1/boards/{cfg['token']}/jobs/{jid}").json()
            d["text"] = clean(html.unescape(x.get("content", "")))
        elif plat == "eightfold" and cfg.get("host"):
            jid = re.findall(r"\d{6,}", url)[-1]
            x = get(f"https://{cfg['host']}/api/apply/v2/jobs/{jid}?domain={cfg.get('domain') or cfg.get('company_domain', '')}").json()
            d["text"] = clean(x.get("job_description", ""))
            d["type"] = x.get("type")
            d["mode"] = x.get("work_location_option")
    except Exception as ex:
        print("detail api failed:", j["company"], str(ex)[:80])
    if len(d["text"]) < 200 and url:
        try:
            t = get(url).text
            x = _jsonld_job(t)
            if x:
                d["text"] = clean(x.get("description", "")) + " " + clean(str(x.get("experienceRequirements", ""))) + " " + clean(str(x.get("educationRequirements", "")))
                d["type"] = d.get("type") or (x.get("employmentType") if isinstance(x.get("employmentType"), str) else None)
                bs = x.get("baseSalary") or {}
                v = (bs.get("value") or {}) if isinstance(bs, dict) else {}
                if v.get("minValue") or v.get("value"):
                    d["salary"] = f"{v.get('minValue') or v.get('value')}-{v.get('maxValue') or ''} {bs.get('currency', '')} {v.get('unitText', '')}".strip(" -")
            else:
                body = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", t)
                d["text"] = clean(body)[:6000]
        except Exception as ex:
            print("detail page failed:", j["company"], str(ex)[:80])
    return d


def facts(j, d):
    t = d.get("text") or ""
    f = {}
    m = re.search(r"(\d{1,2})\s*(?:\+|plus)?\s*(?:-|to|–)\s*(\d{1,2})\s*\+?\s*(?:years|yrs)", t, re.I) or \
        re.search(r"(?:minimum|min\.?|at least|over)\s*(?:of\s*)?(\d{1,2})\s*\+?\s*(?:years|yrs)", t, re.I) or \
        re.search(r"(\d{1,2})\s*\+\s*(?:years|yrs)", t, re.I) or re.search(r"(\d{1,2})\s*(?:years|yrs)\.?\s*(?:of\s*)?(?:relevant|work|professional|post|experience)", t, re.I)
    if m:
        g = [x for x in m.groups() if x]
        if all(int(x) <= 30 for x in g):
            f["exp"] = (f"{g[0]}-{g[1]} years" if len(g) == 2 else f"{g[0]}+ years")
    elif re.search(r"\bfresher|fresh graduate|0\s*-\s*1 year|newly qualified", t, re.I):
        f["exp"] = "Freshers can apply"
    elif d.get("level"):
        f["exp"] = d["level"]
    q = [n for n, rx in QUALS if rx.search(t)]
    if q:
        f["qual"] = " / ".join(q[:3])
    m = re.search(r"(?:rs\.?|inr|₹)\s?\d[\d,.]*\s*(?:-|to)\s*\d[\d,.]*\s*(?:lpa|lakhs?|l\b|per annum)?|\d{1,2}(?:\.\d)?\s*(?:-|to)\s*\d{1,2}(?:\.\d)?\s*lpa", t, re.I)
    f["salary"] = d.get("salary") or (clean(m.group(0)).replace("₹", "Rs. ") if m else "Not disclosed")
    typ = d.get("type") or ("Contract" if re.search(r"\bcontract(ual)?\b|temporary", t, re.I) else "Full-time")
    mode = d.get("mode") or ("Hybrid" if re.search(r"\bhybrid\b", t, re.I) else "Remote" if re.search(r"\bremote\b|work from home", t, re.I) else "")
    f["type"] = ", ".join(x for x in (str(typ).replace("_", " ").title(), str(mode).replace("_", " ").title()) if x)
    f["skills"] = [k for k, rx in SKILL_RX if rx.search(t) or rx.search(j["title"])][:7]
    # 1-2 sentence summary from the description, never more than 220 characters
    sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", t) if 40 <= len(x.strip()) <= 260 and not re.search(r"cookie|javascript|equal opportunity|privacy|©", x, re.I)]
    f["summary"] = sents[0][:220] if sents else ""
    return f


def job_card(j, f=None):
    e = html.escape
    f = f or {}
    tag = TAGS.get(j["category"], "Finance")
    city = city_of(j["location"])
    ctag = re.sub(r"[^A-Za-z]", "", city.split(" +")[0])
    L = [f"📢 <b>Hiring: {e(nice_title(j['title']))}</b>", "",
         f"🏢 <b>{e(j['company'])}</b> is hiring in <b>{e(city)}</b>", ""]
    if f.get("exp"):
        L.append(f"🔹 Experience: {e(f['exp'])}")
    if f.get("qual"):
        L.append(f"🔹 Qualification: {e(f['qual'])}")
    L.append(f"🔹 Salary: {e(f.get('salary') or 'Not disclosed')}")
    if f.get("type"):
        L.append(f"🔹 Job type: {e(f['type'])}")
    L.append(f"🔹 Area: {e(j['category'])}")
    if f.get("skills"):
        L += ["", f"<b>Key skills:</b> {e(', '.join(f['skills']))}"]
    if f.get("summary"):
        L += ["", f"📝 {e(f['summary'])}"]
    L += ["", f"#{tag} #{ctag} #FinanceJobs"]
    return "\n".join(L)


SINGLE_MAX = 6


def post_telegram(new):
    tok, chat = os.environ.get("TG_CHANNEL_TOKEN"), os.environ.get("TG_CHANNEL_ID")
    if not (tok and chat) or not new:
        print("telegram: skipped", "(no secrets)" if not tok else f"({len(new)} new)")
        return
    e = html.escape
    # spread across companies and areas so one employer does not fill the channel
    order, seen_co = [], {}
    for j in sorted(new, key=lambda x: x["company"]):
        seen_co[j["company"]] = seen_co.get(j["company"], 0) + 1
        order.append((seen_co[j["company"]], j))
    order = [j for _, j in sorted(order, key=lambda x: x[0])]
    singles, rest = order[:SINGLE_MAX], order[SINGLE_MAX:]
    for j in singles:
        try:
            f = facts(j, fetch_detail(j))
        except Exception as ex:
            print("facts failed:", j["company"], ex)
            f = {}
        btns = [("✅ Apply on company site", j["url"])]
        if SIM_URL:
            btns.append(("🎯 Practise for this interview (free)", seo.practise_link(SIM_URL, j.get("category"))))
        tg_send(tok, chat, job_card(j, f), btns)
        time.sleep(3)
    if rest:
        lines = [f"➕ <b>{len(rest)} more new finance jobs</b>\n"]
        for j in rest[:25]:
            lines.append(f'▫️ <a href="{e(j["url"])}">{e(nice_title(j["title"]))}</a>\n     {e(j["company"])}, {e(city_of(j["location"]))}')
        if len(rest) > 25:
            lines.append(f"\n…and {len(rest) - 25} more" + (f" on {e(SITE_URL)}/jobs/" if SITE_URL else ""))
        foot = []
        if SIM_URL:
            foot.append(f"🎯 Interview soon? Practise real ERP finance work: {e(SIM_URL)}")
        if channel_link():
            foot.append(f"📢 Share with a friend who is job hunting: {channel_link()}")
        tg_send(tok, chat, "\n".join(lines) + ("\n\n" + "\n".join(foot) if foot else ""))


def sample_post(jobs):
    """One-off test: post 3 current openings in the new format."""
    tok, chat = os.environ.get("TG_CHANNEL_TOKEN"), os.environ.get("TG_CHANNEL_ID")
    if not (tok and chat):
        print("telegram test: secrets missing")
        return
    pick, seen = [], set()
    for j in jobs:
        if j["company"] not in seen and not j.get("approx"):
            seen.add(j["company"])
            pick.append(j)
        if len(pick) == 3:
            break
    post_telegram(pick)


def main():
    os.makedirs(OUT, exist_ok=True)
    companies = json.load(open(os.path.join(HERE, "companies.json")))
    only = sys.argv[1:]  # optional: company names to run
    if only:
        companies = [c for c in companies if c["name"] in only]
    sp = os.path.join(OUT, "state.json")
    state = json.load(open(sp)) if os.path.exists(sp) else {"seen": {}}
    cp = os.path.join(OUT, "configs.json")
    if os.path.exists(cp):
        CACHE.update(json.load(open(cp)))
    reports, jobs = [], []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for rep, js in ex.map(run_company, companies):
            print(f"{rep['company']:<28} {rep.get('platform', '-'):<16} raw={rep.get('raw')} kept={rep.get('kept')} {rep.get('error', '')}", flush=True)
            reports.append(rep)
            jobs += js
    new = []
    last = state.setdefault("last", {})
    for j in jobs:
        last[j["key"]] = NOW
    # forget jobs not seen for 60 days, so the record does not grow for ever
    cutoff = (datetime.now(timezone.utc).timestamp() - 60 * 86400)
    for k in [k for k, t in state["seen"].items()
              if datetime.strptime(last.get(k, t), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() < cutoff]:
        state["seen"].pop(k, None)
        last.pop(k, None)
    for j in jobs:
        if j["key"] not in state["seen"]:
            state["seen"][j["key"]] = NOW
            j["first_seen"] = NOW
            new.append(j)
        else:
            j["first_seen"] = state["seen"][j["key"]]
    jobs.sort(key=lambda x: (x["first_seen"], x["company"]), reverse=True)
    json.dump(jobs, open(os.path.join(OUT, "jobs.json"), "w"), indent=1, ensure_ascii=False)
    json.dump(new, open(os.path.join(OUT, "new.json"), "w"), indent=1, ensure_ascii=False)
    json.dump(state, open(sp, "w"))
    json.dump(CACHE, open(cp, "w"), indent=1)
    build_page(jobs)
    try:
        import seo
        n = seo.build(jobs, os.path.join(OUT, "seo"), SITE_URL or "https://finrehearse.pages.dev", city_of, channel_link(), SIM_URL)
        print(f"seo pages: {n}")
    except Exception as e:
        print("seo pages failed:", e)
    if os.environ.get("TG_TEST") == "true":
        sample_post(jobs)
    else:
        post_telegram(new)
        post_daily_quiz(state)
        json.dump(state, open(sp, "w"))
    json.dump(reports, open(os.path.join(OUT, "companies_report.json"), "w"), indent=1, ensure_ascii=False)
    # markdown report
    working = [r for r in reports if r.get("kept")]
    by_plat, by_cat = {}, {}
    for r in reports:
        p = r.get("platform", "error")
        by_plat.setdefault(p, [0, 0])
        by_plat[p][0] += 1
        by_plat[p][1] += r.get("kept") or 0
    for j in jobs:
        by_cat[j["category"]] = by_cat.get(j["category"], 0) + 1
    L = [f"# Finance job engine v0 report", "", f"Run: {NOW}", "",
         f"- Companies: {len(reports)}", f"- Companies with finance jobs in India: {len(working)}",
         f"- Finance jobs in India (after title filter, de-duplicated): {len(jobs)}", f"- New this run: {len(new)}", "",
         "## By hiring system", "", "| Platform | Companies | Finance jobs |", "|---|---|---|"]
    L += [f"| {k} | {v[0]} | {v[1]} |" for k, v in sorted(by_plat.items(), key=lambda x: -x[1][1])]
    L += ["", "## By finance area", "", "| Area | Jobs |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in sorted(by_cat.items(), key=lambda x: -x[1])]
    L += ["", "## By company", "", "| Company | Platform | Raw jobs read | Finance India kept | Note |", "|---|---|---|---|---|"]
    for r in sorted(reports, key=lambda x: -(x.get("kept") or 0)):
        L.append(f"| {r['company']} | {r.get('platform', '-')} | {r.get('raw', '')} | {r.get('kept', '')} | {r.get('error', '')} |")
    L += ["", "## Sample of jobs", "", "| Company | Title | Area | Location |", "|---|---|---|---|"]
    for j in jobs[:60]:
        L.append(f"| {j['company']} | [{j['title'][:70]}]({j['url']}) | {j['category']} | {j['location'][:50]} |")
    open(os.path.join(OUT, "report.md"), "w").write("\n".join(L) + "\n")
    print(f"\nDONE: {len(jobs)} finance jobs in India from {len(working)} of {len(reports)} companies, {len(new)} new")


if __name__ == "__main__":
    main()
