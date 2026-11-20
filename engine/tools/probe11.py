import re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
def scan(url, label):
    r = requests.get(url, headers=H, timeout=25)
    base = "{0.scheme}://{0.netloc}".format(requests.utils.urlparse(r.url))
    print("#####", label, r.status_code, r.url, len(r.text))
    print("HTML:", re.sub(r"\s+", " ", r.text)[:1200])
    srcs = re.findall(r'(?:src|href)="([^"]+\.js[^"]*)"', r.text)
    print("SCRIPTS:", srcs)
    for s in srcs:
        if re.search(r"gtm|google|analytics|polyfill|clarity|hotjar|facebook", s): continue
        su = s if s.startswith("http") else base + ("" if s.startswith("/") else "/") + s.lstrip("./")
        try: t = requests.get(su, headers=H, timeout=25).text
        except Exception: continue
        hosts = sorted(set(re.findall(r"https?://[a-zA-Z0-9.-]+(?:/[a-zA-Z0-9_/.-]*)?", t)))
        hosts = [h for h in hosts if not re.search(r"w3\.org|github|reactjs|mozilla|google|fb\.me|npm|unpkg|jsdelivr|sentry|schema\.org", h)]
        paths = sorted(set(re.findall(r"""["'`](/?(?:api|v\d)/[A-Za-z0-9_/{}.$-]*)["'`]""", t)))
        jobish = sorted(set(re.findall(r"""["'`]([A-Za-z0-9_/{}.$-]*(?:[Jj]ob|[Cc]areer|[Oo]pening)[A-Za-z0-9_/{}.$-]*)["'`]""", t)))
        print("JS", su, len(t)); print("  HOSTS", hosts[:40]); print("  PATHS", paths[:80]); print("  JOBISH", [j for j in jobish if "/" in j][:80])
scan("https://flipkart.turbohire.co/careerpage/4d757ba0-3d57-448a-b82c-238ed87ac90f", "turbohire")
scan("https://jupiter.keka.com/careers", "keka")
