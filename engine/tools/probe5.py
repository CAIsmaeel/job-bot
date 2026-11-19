import re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
B = "https://hdfcbank.ripplehire.com"
r = requests.get(B + "/candidate/?token=pvB5iAMcmu4ydUh2IW2O&source=CAREERSITE", headers=H, timeout=20)
print("REQ tags:", re.findall(r'<script[^>]*require[^>]*>', r.text))
print("HIDDEN:", re.findall(r'<input[^>]*type="hidden"[^>]*>', r.text)[:20])
seen, queue = set(), []
for dm in re.findall(r'data-main="([^"]+)"', r.text):
    queue.append(dm)
queue += ["./candresource/candidate/main", "./candresource/candidate/app", "./candresource/candidate/config"]
URL = re.compile(r"""["']([^"'\s]{0,100}(?:\.do|/candidate/[a-zA-Z]+[^"'\s]*|/api/[^"'\s]*|rest/[^"'\s]*|getJob[^"'\s]*|joblist[^"'\s]*|jobList[^"'\s]*|search[A-Z][^"'\s]*))["']""")
n = 0
while queue and n < 40:
    q = queue.pop(0)
    u = q if q.startswith("http") else B + "/candidate/" + q.lstrip("./").replace("candidate/", "candidate/", 1)
    if not u.endswith(".js"): u += ".js"
    if u in seen: continue
    seen.add(u); n += 1
    try:
        t = requests.get(u, headers=H, timeout=20)
    except Exception as e:
        print("ERR", u, e); continue
    print("##", t.status_code, u, len(t.text))
    if t.status_code != 200: continue
    for m in sorted(set(URL.findall(t.text)))[:80]:
        print("   URL", m)
    for dep in re.findall(r"""["']((?:\./|candresource/)[\w/.-]+)["']""", t.text):
        if not re.search(r"\.(css|png|svg|html|tpl)$", dep): queue.append(dep)
    for k, v in re.findall(r"""['"]?([\w-]+)['"]?\s*:\s*['"]((?:\.\./|\./)?[\w/.-]*candidate[\w/.-]*)['"]""", t.text)[:80]:
        queue.append(v)
