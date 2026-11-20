import re, json, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Accept": "application/json, text/plain, */*"}
t = requests.get("https://flipkart.turbohire.co/main.0fbeb7233f472c0db0a8.chunk.js", headers=H, timeout=40).text
for pat in ('"/api/careerpage"', '"/api/careerpage/details"', 'careerpage/jobs', 'CareerPageJobs', 'getCareerPageJobs', 'careerpagejobs'):
    for k in list(re.finditer(re.escape(pat), t, re.I))[:2]:
        print("CTX", pat, "::", re.sub(r"\s+", " ", t[max(0, k.start()-500):k.start()+400]))
print("API_SERVER", sorted(set(re.findall(r'API_SERVER_BASE_URL\s*[:=]\s*"([^"]+)"', t)))[:5])
k = requests.get("https://jupiter.keka.com/careers/api/embedjobs/js/b5279857-cf81-4dde-a215-fc48957ee2b5", headers=H, timeout=25).text
print("KEKAJS", len(k)); print(sorted(set(re.findall(r"""["'`](/?[A-Za-z0-9_/{}.$:-]*(?:api|embedjobs)[A-Za-z0-9_/{}.$?=&-]*)["'`]""", k)))[:40])
for kk in list(re.finditer(r"embedjobs", k))[:4]:
    print("KCTX", re.sub(r"\s+", " ", k[max(0, kk.start()-300):kk.start()+300]))
for u in ("https://jupiter.keka.com/careers/api/embedjobs/default/active/b5279857-cf81-4dde-a215-fc48957ee2b5",
          "https://jupiter.keka.com/careers/api/embedjobs/active/b5279857-cf81-4dde-a215-fc48957ee2b5"):
    x = requests.get(u, headers=H, timeout=25)
    print("TRY", x.status_code, u, x.headers.get("content-type"), x.text[:800])
