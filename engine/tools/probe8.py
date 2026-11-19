import re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
B = "https://hdfcbank.ripplehire.com/candidate/candresource/candidate/"
t = requests.get(B + "candidates_app.js", headers=H, timeout=20).text
print("CAPP", len(t)); print(t[:3000])
mods = sorted(set(re.findall(r'["\']((?:apps|entities)/[\w/]+)["\']', t)))
print("MODS", mods)
for m in mods:
    if not re.search(r"list|search", m, re.I): continue
    x = requests.get(B + m + ".js", headers=H, timeout=20)
    print("=== MOD", x.status_code, m, len(x.text))
    for sub in re.findall(r'["\']((?:apps|entities)/[\w/]+)["\']', x.text):
        if sub not in mods and re.search(r"list|search", sub, re.I): mods.append(sub)
    txt = x.text
    for k in re.finditer(r"careerSiteUrlParams|getJobSearchResult|jobsearch|urlParams|searchParams", txt):
        a = max(0, k.start() - 1500); print("CTX>>", re.sub(r"\s+", " ", txt[a:k.start() + 700])); break
