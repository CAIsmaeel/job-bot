import re, requests
from urllib.parse import urlparse
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
T = ["https://hdfcbank.ripplehire.com/candidate/?token=pvB5iAMcmu4ydUh2IW2O&source=CAREERSITE",
     "https://bflcareers.peoplestrong.com/",
     "https://flipkart.turbohire.co/careerpage/4d757ba0-3d57-448a-b82c-238ed87ac90f",
     "https://perfios.darwinbox.in/ms/candidate/careers",
     "https://jupiter.keka.com/careers"]
S = re.compile(r"""["'`]([^"'`\s<>]{0,80}(?:/api/|api\.|/ajax/|\.do\b|/rest/|/service/|/v1/|/v2/)[^"'`\s<>]{0,120})["'`]""", re.I)
for u in T:
    print("#####", u)
    try:
        r = requests.get(u, headers=H, timeout=20)
        base = "{0.scheme}://{0.netloc}".format(urlparse(r.url))
        srcs = [r.text]
        for s in re.findall(r'src="([^"]+\.js[^"]*)"', r.text):
            if re.search(r"jquery|turnstile|google|gtm|analytics|polyfill|bootstrap|dboxuilib|formbuilder", s, re.I):
                continue
            su = s if s.startswith("http") else base + ("" if s.startswith("/") else "/") + s.lstrip("./")
            try:
                srcs.append(requests.get(su, headers=H, timeout=20).text)
            except Exception:
                pass
        hits = []
        for t in srcs:
            for m in S.finditer(t):
                v = m.group(1)
                if re.search(r"\.(png|svg|css|woff)|googleapis|fonts|gstatic|w3\.org", v):
                    continue
                if v not in hits:
                    hits.append(v)
        print(len(srcs), "files")
        for h in hits[:120]:
            print("  ", h)
    except Exception as e:
        print("ERR", e)
