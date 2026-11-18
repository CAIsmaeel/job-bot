"""Source probe: can we read company career-site job feeds directly (no LinkedIn / Naukri)?

For each company it opens the public careers page, detects which hiring system (ATS) runs it,
tries that system's public job feed, and counts finance jobs in India.
Writes source_test/report.md and source_test/report.json.

Polite by design: one request at a time, a pause between companies, public pages only, no login.
"""
import json, re, time, html
from urllib.parse import urlparse, urljoin
import requests

UA = "Mozilla/5.0 (compatible; CareerFeedProbe/0.1; one-off feasibility test)"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.8"})
T = 25
FIN = re.compile(r"financ|account|fp&a|fpa|audit|tax|treasury|controller|r2r|p2p|o2c|payable|receivable|ledger|costing", re.I)
INDIA = re.compile(r"india|mumbai|pune|bengaluru|bangalore|hyderabad|chennai|gurgaon|gurugram|noida|delhi|kolkata|ahmedabad|navi mumbai|thane", re.I)

COMPANIES = [
 ("Mastercard", "https://careers.mastercard.com"), ("Visa", "https://jobs.smartrecruiters.com/Visa"),
 ("JPMorgan Chase", "https://careers.jpmorgan.com/in/en/home"), ("Caterpillar", "https://careers.caterpillar.com"),
 ("PwC India", "https://www.pwc.in/careers.html"), ("EY", "https://careers.ey.com"),
 ("Deloitte USI", "https://usijobs.deloitte.com"), ("KPMG India", "https://kpmg.com/in/en/home/careers.html"),
 ("Grant Thornton Bharat", "https://www.grantthornton.in/careers/"), ("BDO India", "https://www.bdo.in/en-gb/careers"),
 ("Accenture", "https://www.accenture.com/in-en/careers"), ("Genpact", "https://www.genpact.com/careers"),
 ("WNS", "https://www.wns.com/careers"), ("EXL", "https://www.exlservice.com/careers"),
 ("Barclays", "https://search.jobs.barclays"), ("HSBC", "https://www.hsbc.com/careers"),
 ("Deutsche Bank", "https://careers.db.com"), ("Citi", "https://jobs.citi.com"),
 ("Goldman Sachs", "https://higher.gs.com"), ("Morgan Stanley", "https://www.morganstanley.com/careers"),
 ("Wells Fargo", "https://www.wellsfargojobs.com"), ("American Express", "https://www.americanexpress.com/en-us/careers/"),
 ("Maersk", "https://www.maersk.com/careers"), ("Michelin", "https://jobs.michelin.com"),
 ("Shell", "https://www.shell.in/careers.html"), ("BP", "https://www.bp.com/en/global/corporate/careers.html"),
 ("Unilever / HUL", "https://careers.unilever.com"), ("Nestle India", "https://www.nestle.in/jobs"),
 ("P&G", "https://www.pgcareers.com"), ("Siemens", "https://jobs.siemens.com"),
 ("Honeywell", "https://careers.honeywell.com"), ("Cummins", "https://cummins.jobs"),
 ("Bosch India", "https://www.bosch.in/careers/"), ("Schneider Electric", "https://careers.se.com"),
 ("AB InBev", "https://www.ab-inbev.com/careers/"), ("Diageo", "https://www.diageo.com/en/careers"),
 ("Novartis", "https://www.novartis.com/careers"), ("Reliance Industries", "https://careers.ril.com"),
 ("Tata Steel", "https://www.tatasteel.com/careers/"), ("Mahindra", "https://www.mahindra.com/careers"),
 ("HDFC Bank", "https://www.hdfc.bank.in/careers"), ("ICICI Bank", "https://www.icicicareers.com"),
 ("Bajaj Finance", "https://bflcareers.peoplestrong.com"), ("Godrej Industries", "https://www.godrejindustries.com/careers"),
 ("Aditya Birla Group", "https://careers.adityabirla.com"), ("Larsen & Toubro", "https://www.larsentoubro.com/corporate/careers/"),
 ("Asian Paints", "https://careers.asianpaints.com"), ("Infosys", "https://www.infosys.com/careers/"),
 ("Flipkart", "https://www.flipkartcareers.com"), ("Razorpay", "https://razorpay.com/jobs/"),
]

SIGS = [("workday", r"myworkdayjobs\.com"), ("oracle", r"oraclecloud\.com/hcmUI"), ("smartrecruiters", r"smartrecruiters\.com"),
        ("greenhouse", r"greenhouse\.io"), ("lever", r"jobs\.lever\.co"), ("successfactors", r"successfactors|jobs2web|/services/rss/job|career site builder|rmkcdn"),
        ("eightfold", r"eightfold\.ai"), ("avature", r"avature|/careers[A-Za-z]*/JobDetail/|/careers[A-Za-z]*/SearchJobs"),
        ("phenom", r"phenompeople|phenom\.com|ph-page"), ("radancy", r"radancy|tmp\.com|/job/[^\"']+/\d{4,}/\d{6,}"),
        ("darwinbox", r"darwinbox"), ("peoplestrong", r"peoplestrong"), ("taleo", r"taleo\.net"), ("icims", r"icims\.com"),
        ("keka", r"keka\.com"), ("zoho", r"zohorecruit")]


def get(url, **kw):
    return S.get(url, timeout=T, allow_redirects=True, **kw)


def jsonld_jobs(text):
    n = 0
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', text, re.S | re.I):
        if '"JobPosting"' in m.group(1):
            n += m.group(1).count('"JobPosting"')
    return n


def fin_india(rows):
    """rows: list of (title, location)"""
    return sum(1 for t, l in rows if FIN.search(t or "") and INDIA.search(l or ""))


def try_workday(text):
    m = re.search(r"https://([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)", text)
    if not m:
        return None
    tenant, wd, site = m.groups()
    api = f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    r = S.post(api, json={"limit": 20, "offset": 0, "searchText": "finance", "appliedFacets": {}}, timeout=T)
    r.raise_for_status()
    j = r.json()
    rows = [(p.get("title"), p.get("locationsText")) for p in j.get("jobPostings", [])]
    return {"feed": api, "finance_total_global": j.get("total"), "sample_20_finance_india": fin_india(rows),
            "sample": rows[:3]}


def try_smartrecruiters(text, final):
    m = re.search(r"smartrecruiters\.com/([A-Za-z0-9_-]+)", text + " " + final)
    if not m:
        return None
    co = m.group(1)
    api = f"https://api.smartrecruiters.com/v1/companies/{co}/postings?country=in&limit=100"
    j = get(api).json()
    rows = [(p.get("name"), (p.get("location") or {}).get("city", "") + " India") for p in j.get("content", [])]
    return {"feed": api, "india_total": j.get("totalFound"), "finance_india_in_first_100": fin_india(rows), "sample": rows[:3]}


def try_greenhouse(text):
    m = re.search(r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_-]+)", text)
    if not m:
        return None
    api = f"https://boards-api.greenhouse.io/v1/boards/{m.group(1)}/jobs"
    j = get(api).json()
    rows = [(p.get("title"), (p.get("location") or {}).get("name")) for p in j.get("jobs", [])]
    return {"feed": api, "total": len(rows), "finance_india": fin_india(rows), "sample": rows[:3]}


def try_lever(text):
    m = re.search(r"jobs\.lever\.co/([A-Za-z0-9_-]+)", text)
    if not m:
        return None
    api = f"https://api.lever.co/v0/postings/{m.group(1)}?mode=json"
    j = get(api).json()
    rows = [(p.get("text"), (p.get("categories") or {}).get("location")) for p in j]
    return {"feed": api, "total": len(rows), "finance_india": fin_india(rows), "sample": rows[:3]}


def try_oracle(text):
    m = re.search(r"https://([\w.-]+\.oraclecloud\.com)/hcmUI/CandidateExperience/[a-z]{2}/sites/([\w-]+)", text)
    if not m:
        return None
    host, site = m.groups()
    api = (f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true"
           f"&expand=requisitionList&finder=findReqs;siteNumber={site},keyword=finance,location=India,limit=25")
    j = get(api).json()
    it = (j.get("items") or [{}])[0]
    rows = [(p.get("Title"), p.get("PrimaryLocation")) for p in it.get("requisitionList", [])]
    return {"feed": api, "finance_india_total": it.get("TotalJobsCount"), "sample": rows[:3]}


def try_csb_rss(final):
    o = urlparse(final)
    api = f"{o.scheme}://{o.netloc}/services/rss/job/?locale=en_US&keywords=finance"
    r = get(api)
    if r.status_code != 200 or "<item" not in r.text:
        return None
    items = re.findall(r"<item>(.*?)</item>", r.text, re.S)
    rows = [(html.unescape((re.search(r"<title>(.*?)</title>", i, re.S) or [None, ""])[1]),
             html.unescape(i)) for i in items]
    return {"feed": api, "rss_items": len(items), "finance_india": fin_india(rows), "sample": [x[0] for x in rows[:3]]}


def sitemap_jobs(final):
    o = urlparse(final)
    try:
        r = get(f"{o.scheme}://{o.netloc}/sitemap.xml")
        if r.status_code == 200 and "<loc>" in r.text:
            locs = re.findall(r"<loc>(.*?)</loc>", r.text)
            return {"sitemap_urls": len(locs), "job_like_urls": sum(1 for u in locs if re.search(r"/job|jobid|requisition", u, re.I))}
    except Exception:
        pass
    return None


def probe(name, url):
    out = {"company": name, "start_url": url}
    try:
        r = get(url)
        out.update(status=r.status_code, final_url=r.url)
        text = r.text
    except Exception as e:
        out.update(status="error", error=str(e)[:150], verdict="unreachable")
        return out
    blob = text + " " + r.url
    out["ats"] = [k for k, pat in SIGS if re.search(pat, blob, re.I)] or ["unknown/custom"]
    out["jsonld_jobposting_on_page"] = jsonld_jobs(text)
    feed = None
    for fn in (try_workday, try_oracle, try_greenhouse, try_lever):
        try:
            feed = fn(text)
        except Exception as e:
            out.setdefault("feed_errors", []).append(f"{fn.__name__}: {str(e)[:120]}")
        if feed:
            break
    if not feed:
        try:
            feed = try_smartrecruiters(text, r.url)
        except Exception as e:
            out.setdefault("feed_errors", []).append(f"try_smartrecruiters: {str(e)[:120]}")
    if not feed:
        try:
            feed = try_csb_rss(r.url)
        except Exception as e:
            out.setdefault("feed_errors", []).append(f"try_csb_rss: {str(e)[:120]}")
    if feed:
        out["feed"] = feed
        out["verdict"] = "EASY: public feed works"
    else:
        sm = sitemap_jobs(r.url)
        if sm:
            out["sitemap"] = sm
        if out["jsonld_jobposting_on_page"] or (sm and sm["job_like_urls"]):
            out["verdict"] = "MEDIUM: readable via sitemap / structured data"
        elif r.status_code in (401, 403, 429):
            out["verdict"] = "BLOCKED for bots"
        else:
            out["verdict"] = "HARD: custom page, needs its own adapter"
    return out


def main():
    res = []
    for name, url in COMPANIES:
        print("probing", name, flush=True)
        res.append(probe(name, url))
        time.sleep(3)
    json.dump(res, open("source_test/report.json", "w"), indent=1, ensure_ascii=False)
    count = {}
    for x in res:
        k = x["verdict"].split(":")[0]
        count[k] = count.get(k, 0) + 1
    lines = ["# Career-site feed probe", "", f"Companies tested: {len(res)}", "",
             "| Verdict | Companies |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(count.items())] + [
             "", "| Company | HTTP | ATS detected | Verdict | Finance jobs found |", "|---|---|---|---|---|"]
    for x in res:
        f = x.get("feed") or {}
        n = next((f[k] for k in ("finance_india_total", "finance_india", "finance_india_in_first_100",
                                 "sample_20_finance_india") if k in f), "")
        if "finance_total_global" in f:
            n = f"{f['finance_total_global']} global, {n} India in first 20"
        lines.append(f"| {x['company']} | {x.get('status')} | {', '.join(x.get('ats', []))} | {x['verdict']} | {n} |")
    open("source_test/report.md", "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
