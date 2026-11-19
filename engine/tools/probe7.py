import re, json, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
     "X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
for host, start in (("hdfcbank", "/candidate/careers"), ("axisbank", "/candidate/")):
    s = requests.Session(); s.headers.update(H)
    r = s.get(f"https://{host}.ripplehire.com{start}", timeout=20)
    tok = re.search(r'id="token" value="([^"]+)"', r.text).group(1)
    print("####", host, tok, r.url)
    B = f"https://{host}.ripplehire.com/candidate/"
    for name, params in (("plain", {"token": tok, "source": "CAREERSITE"}),
                         ("page", {"token": tok, "source": "CAREERSITE", "pageNumber": 1, "pageSize": 50})):
        for meth in ("post", "get"):
            try:
                data = {"careerSiteUrlParams": json.dumps(params), "lang": "en"}
                x = s.post(B + "candidatejobsearch", data=data, timeout=25) if meth == "post" else s.get(B + "candidatejobsearch", params=data, timeout=25)
                print("--", name, meth, x.status_code, x.headers.get("content-type"), len(x.text))
                try:
                    j = x.json()
                    print("   keys:", list(j)[:30])
                    jl = j.get("jobVoList") or []
                    print("   n jobs:", len(jl), "total:", {k: j[k] for k in j if re.search("count|total|page", k, re.I)})
                    if jl: print("   first:", json.dumps(jl[0])[:1500])
                except Exception:
                    print("   body:", x.text[:300])
            except Exception as e:
                print("ERR", e)
    t = s.get(B + "candresource/candidate/apps/candidates/candidates_app.js", timeout=20).text
    print("APP:", re.findall(r'["\']((?:apps|entities)/[\w/]+)["\']', t)[:60])
    break_after = True
