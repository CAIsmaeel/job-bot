import re, json, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
for host, start in (("hdfcbank", "/candidate/careers"), ("axisbank", "/candidate/"), ("tatasteel", "/candidate/"), ("mphasis", "/ripplehire/careers")):
    s = requests.Session(); s.headers.update(H)
    r = s.get(f"https://{host}.ripplehire.com{start}", timeout=20)
    m = re.search(r'id="token"\s+value="([^"]*)"', r.text) or re.search(r"token=([\w]+)", r.url)
    tok = m.group(1) if m else ""
    print("####", host, r.status_code, r.url, "token:", tok)
    p = {"page": 0, "search": "*:*", "token": tok, "source": "CAREERSITE", "pagesize": 100}
    x = s.post(f"https://{host}.ripplehire.com/candidate/candidatejobsearch", data={"careerSiteUrlParams": json.dumps(p), "lang": "en"}, timeout=30)
    try:
        j = x.json(); jl = j.get("jobVoList") or []
        print("  total", j.get("totalJobCount"), "got", len(jl))
        if jl: print("  first:", json.dumps(jl[0])[:2500])
        p["page"] = 1
        y = s.post(f"https://{host}.ripplehire.com/candidate/candidatejobsearch", data={"careerSiteUrlParams": json.dumps(p), "lang": "en"}, timeout=30).json()
        print("  page2 got", len(y.get("jobVoList") or []))
    except Exception as e:
        print("  ERR", x.status_code, x.text[:300], e)
