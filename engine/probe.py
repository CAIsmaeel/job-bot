"""Dry run for fixing companies: finds out why a company gives 0 jobs. Posts nothing, saves nothing.
Usage: python engine/probe.py [company names...]   (no names = every company that gave 0 raw jobs last run)
Prints one line per company and writes engine/out/probe.json."""
import json, os, re, sys, html
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse
sys.path.insert(0, os.path.dirname(__file__))
import engine as E

HINTS = r"(myworkdayjobs\.com|oraclecloud\.com|successfactors\.\w+|eightfold\.ai|phenompeople|avature\.net|smartrecruiters\.com|greenhouse\.io|lever\.co|icims\.com|taleo\.net|darwinbox\.\w+|peoplestrong\.com|keka\.com|zohorecruit\.\w+|ripplehire\.com|turbohire\.co|jobvite\.com|workable\.com|recruitee\.com|teamtailor\.com|ashbyhq\.com|naukri\.com|brassring\.com|jibeapply\.com|cornerstoneondemand\.com|ultipro\.com|paradox\.ai|beesite\.de|csod\.com)"

def probe(co):
    name, url = co["name"], co["careers"]
    out = {"company": name, "careers": url, "status": None, "hints": [], "cfg": None, "raw": 0, "kept": 0, "sample": []}
    pages = [url]
    try:
        r = E.get(url)
        if r.status_code >= 400:
            # careers link is stale: try the home page and common careers paths
            o = "{0.scheme}://{0.netloc}".format(urlparse(url))
            host = urlparse(url).netloc
            base = "https://www." + host[4:] if host.startswith("www.") else "https://" + host
            for cand in [o + "/careers", o + "/careers/", o + "/en/careers", o + "/career", o + "/careers.html", o + "/about-us/careers", o + "/"]:
                try:
                    rc = E.get(cand)
                except Exception:
                    continue
                if rc.status_code < 400:
                    if cand.endswith("/") and cand == o + "/":
                        links = [urljoin(rc.url, html.unescape(h)) for h in re.findall(r'href=["\']([^"\'#]*career[^"\'#]*)["\']', rc.text, re.I)]
                        links = [l for l in links if l.startswith("http")]
                        if links:
                            try:
                                rl = E.get(links[0])
                                if rl.status_code < 400:
                                    rc = rl
                            except Exception:
                                pass
                    r = rc
                    out["new_careers"] = rc.url
                    break
        out["status"] = r.status_code
        out["final"] = r.url
        blob = r.text[:800000]
        hs = set(m.group(1).lower() for m in re.finditer(HINTS, blob + " " + r.url, re.I))
        for href, text in re.findall(r'<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', r.text, re.S | re.I):
            full = urljoin(r.url, html.unescape(href))
            if full.startswith("http") and (E.LINK_HINT.search(href) or E.LINK_HINT.search(E.clean(text))):
                pages.append(full)
        for u in list(dict.fromkeys(pages[1:]))[:8]:
            try:
                r2 = E.get(u)
                b2 = r2.text[:600000] + " " + r2.url
                hs |= set(m.group(1).lower() for m in re.finditer(HINTS, b2, re.I))
                cfg = E.identify(b2, r2.url)
                if cfg and not out["cfg"]:
                    cfg["found_on"] = r2.url
                    out["cfg"] = cfg
            except Exception:
                pass
        if not out["cfg"]:
            cfg = E.identify(blob + " " + r.url, r.url)
            if cfg:
                out["cfg"] = cfg
        out["hints"] = sorted(hs)
    except Exception as ex:
        out["error"] = f"{type(ex).__name__}: {str(ex)[:120]}"
    if co.get("ats"):
        out["cfg"] = dict(co["ats"])
    if not out["cfg"]:
        out["cfg"] = E.probe_boards(name)
    if out["cfg"]:
        rep, js = E.run_company(dict(co, ats=out["cfg"]))
        out["raw"], out["kept"] = rep.get("raw"), rep.get("kept")
        out["sample"] = [j["title"] for j in js[:3]]
        if rep.get("error"):
            out["error"] = rep["error"]
    return out

def main():
    cos = json.load(open(os.path.join(E.HERE, "companies.json")))
    names = sys.argv[1:] or [n for n in os.environ.get("PROBE_NAMES", "").split("|") if n.strip()]
    if names:
        cos = [c for c in cos if c["name"] in names]
    else:
        rp = os.path.join(E.OUT, "companies_report.json")
        zero = {x["company"] for x in json.load(open(rp)) if not x.get("raw")} if os.path.exists(rp) else set()
        cos = [c for c in cos if c["name"] in zero]
    lim = int(os.environ.get("PROBE_LIMIT") or 0)
    if lim:
        cos = cos[:lim]
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(probe, cos))
    for o in res:
        print(f"PROBE | {o['company'][:30]:<30} | st={o['status']} | {(o['cfg'] or {}).get('platform','-'):<15} | raw={o['raw']} kept={o['kept']} | hints={','.join(o['hints'])[:120]} | {o.get('error','')}", flush=True)
    for o in res:
        if o["cfg"] or o.get("new_careers"):
            print("PROBECFG", json.dumps({"company": o["company"], "new_careers": o.get("new_careers"), "cfg": o["cfg"], "raw": o["raw"], "kept": o["kept"], "error": o.get("error")}), flush=True)
    os.makedirs(E.OUT, exist_ok=True)
    json.dump(res, open(os.path.join(E.OUT, "probe.json"), "w"), indent=1)
    print("PROBE_SUMMARY", sum(1 for o in res if o["kept"]), "of", len(res), "now give India finance jobs")

if __name__ == "__main__":
    main()
