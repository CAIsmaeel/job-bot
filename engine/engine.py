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
                     r"full ?stack|front ?end|back ?end|sales executive|relationship manager|field sales|"
                     r"workday hcm|oracle hcm|successfactors|servicenow|salesforce|cyber|security analyst|"
                     r"hr business partner|recruiter|talent acquisition|marketing|nurse|driver|technician|mechanic|electrical|mechanical|"
                     r"lending collection|collections? (executive|officer|agent)|area collection|collection manager|recovery|tele ?caller|"
                     r"quality (auditor|analyst)|\bvoice\b|design assurance|product manag|program manag|product team|"
                     r"strategic accounts|key accounts?|account (manager|executive|director)|\bit due diligence|"
                     r"housing finance.*(sales|product)|loan officer", re.I)
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
    return {"platform": "sitemap", "origin": "{0.scheme}://{0.netloc}".format(urlparse(url))}, None


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
            "successfactors": a_successfactors, "sitemap": a_sitemap}


# ---------------- run ----------------
CACHE = {}
CACHE_DAYS = 7


def cached_cfg(name):
    c = CACHE.get(name)
    if not c or c["cfg"].get("platform") == "sitemap":
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
        raw = ADAPTERS[cfg["platform"]](cfg)
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
                     "location": clean(str(j.get("location") or ""))[:120], "url": j.get("url"),
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
          .replace("__PRACTICE__", practice).replace("__BRAND__", html.escape(BRAND)))
    os.makedirs(os.path.join(OUT, "site"), exist_ok=True)
    open(os.path.join(OUT, "site", "index.html"), "w", encoding="utf-8").write(t)


def post_telegram(new):
    tok, chat = os.environ.get("TG_CHANNEL_TOKEN"), os.environ.get("TG_CHANNEL_ID")
    if not (tok and chat) or not new:
        print("telegram: skipped", "(no secrets)" if not tok else f"({len(new)} new)")
        return
    e = html.escape
    new = sorted(new, key=lambda j: (j["category"], j["company"]))
    foot = []
    if SITE_URL:
        foot.append(f'All openings with filters: {e(SITE_URL)}/jobs/')
    if SIM_URL:
        foot.append(f'Interview soon? Practise ERP finance work: {e(SIM_URL)}')
    foot = ("\n\n" + "\n".join(foot)) if foot else ""
    batch_size, max_msgs = 8, 4
    batches = [new[i:i + batch_size] for i in range(0, len(new), batch_size)][:max_msgs]
    for bi, b in enumerate(batches):
        head = f"<b>New finance openings</b> ({len(new)} new)" if bi == 0 else "<b>More new openings</b>"
        body = "\n\n".join(f'<b>{e(j["title"])}</b>\n{e(j["company"])}, {e(j["location"][:60])}\n{e(j["category"])}\n'
                            f'<a href="{e(j["url"])}">Apply on company site</a>' for j in b)
        rest = len(new) - batch_size * max_msgs
        tail = (f"\n\n+{rest} more on the website" if rest > 0 and bi == len(batches) - 1 else "")
        text = f"{head}\n\n{body}{tail}{foot if bi == len(batches) - 1 else ''}"
        try:
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=T,
                              data={"chat_id": chat, "text": text[:4090], "parse_mode": "HTML", "disable_web_page_preview": "true"})
            print("telegram:", r.status_code, r.text[:120])
        except Exception as ex:
            print("telegram error:", ex)
        time.sleep(3)


def welcome_post(jobs):
    """One-off: introduce the channel and show a few current openings."""
    tok, chat = os.environ.get("TG_CHANNEL_TOKEN"), os.environ.get("TG_CHANNEL_ID")
    if not (tok and chat):
        print("telegram test: secrets missing")
        return
    text = ("<b>Finance Jobs India is live</b>\n\n"
            "Finance, accounting, tax, audit, FP&amp;A and treasury openings in India, read directly from company career pages "
            "and posted here as soon as we find them.\n\nApply on the company's own site. We never charge for jobs.")
    r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=T,
                      data={"chat_id": chat, "text": text, "parse_mode": "HTML"})
    print("telegram test welcome:", r.status_code, r.text[:200])
    if r.ok:
        time.sleep(3)
        pick, seen = [], set()
        for j in jobs:
            if j["company"] not in seen:
                seen.add(j["company"])
                pick.append(j)
            if len(pick) == 5:
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
    if os.environ.get("TG_TEST") == "true":
        welcome_post(jobs)
    else:
        post_telegram(new)
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
