import re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
B = "https://flipkart.turbohire.co"
for s in ("/main.0fbeb7233f472c0db0a8.chunk.js", "/18.ad1f07674b986c5052f1.chunk.js", "/30.86c6a5b9e9f7200f24dd.chunk.js", "/runtime-main.05e45417c9cf8a8068a9.js"):
    try:
        t = requests.get(B + s, headers=H, timeout=40).text
    except Exception as e:
        print("ERR", s, e); continue
    print("JS", s, len(t))
    print("  HOSTS", sorted(set(h for h in re.findall(r"https?://[a-zA-Z0-9.-]+", t) if "turbohire" in h or "api" in h))[:40])
    for m in sorted(set(re.findall(r"""["'`]([A-Za-z0-9_/{}.$-]*(?:[Cc]areer[Pp]age|[Cc]areerpage|[Jj]obs?[A-Z][A-Za-z]*|[Oo]penings?)[A-Za-z0-9_/{}.$-]*)["'`]""", t))):
        if "/" in m: print("  P", m)
    for k in re.finditer(r"careerpage|CareerPage", t):
        print("  CTX", re.sub(r"\s+", " ", t[max(0, k.start()-200):k.start()+300])); break
K = "https://jupiter.keka.com"
r = requests.get(K + "/careers", headers=H, timeout=25)
m = re.search(r"fetch\('([^']+)'", r.text)
print("KEKA script:", re.sub(r"\s+", " ", r.text)[1200:3000])
if m:
    d = requests.get(K + m.group(1), headers=H, timeout=25).text
    print("KEKA doc len", len(d))
    print("KEKA urls:", sorted(set(re.findall(r"""["'](/[A-Za-z0-9_/{}.?=&$-]*(?:api|job|Job)[A-Za-z0-9_/{}.?=&$-]*)["']""", d)))[:60])
    print("KEKA srcs:", re.findall(r'src="([^"]+)"', d)[:20])
    for s in re.findall(r'src="([^"]+\.js[^"]*)"', d)[:8]:
        u = s if s.startswith("http") else K + s
        t = requests.get(u, headers=H, timeout=25).text
        print(" KJS", u, len(t), sorted(set(re.findall(r"""["'`](/?[A-Za-z0-9_/{}.$-]*(?:api|embedjobs|jobboard|JobBoard)[A-Za-z0-9_/{}.$-]*)["'`]""", t)))[:40])
