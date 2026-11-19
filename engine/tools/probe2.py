import re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
T = ["https://hdfcbank.ripplehire.com/candidate/careers", "https://axisbank.ripplehire.com/candidate/",
     "https://bflcareers.peoplestrong.com/", "https://sobhalimited-careers.peoplestrong.com/job/joblist",
     "https://flipkart.turbohire.co/careerpage/4d757ba0-3d57-448a-b82c-238ed87ac90f",
     "https://perfios.darwinbox.in/ms/candidate/careers", "https://autalenthub.darwinbox.in/ms/candidatev2/main/careers/allJobs",
     "https://jupiter.keka.com/careers",
     "https://pepjobs-pepsico.icims.com/jobs/search?ss=1&in_iframe=1&searchLocation=-India-&searchKeyword=finance"]
API = re.compile(r"""["'`]((?:https?:)?/?/?[\w.-]*/?(?:api|ms|ripplehire|rest|job|jobs|careers?|candidate)[\w/.{}$-]*(?:job|career|opening|list|search|requisition|vacanc)[\w/.{}$-]*)["'`]""", re.I)
for u in T:
    print("#####", u)
    try:
        r = requests.get(u, headers=H, timeout=20)
        print(r.status_code, r.url, r.headers.get("content-type"), len(r.text))
        body = re.sub(r"\s+", " ", r.text)
        print("BODY:", body[:1500])
        if "icims" in u:
            print("LINKS:", sorted(set(re.findall(r'href="(https://[^"]+/jobs/\d+/[^"]+/job[^"]*)"', r.text)))[:10])
            print("TITLES:", re.findall(r'<h3[^>]*>(.*?)</h3>', r.text, re.S)[:5])
        base = "{0.scheme}://{0.netloc}".format(requests.utils.urlparse(r.url))
        js = re.findall(r'src="([^"]+\.js[^"]*)"', r.text)
        for s in js:
            if re.search(r"jquery|turnstile|google|gtm|analytics|polyfill|bootstrap", s, re.I):
                continue
            su = s if s.startswith("http") else base + ("" if s.startswith("/") else "/") + s.lstrip("./")
            try:
                y = requests.get(su, headers=H, timeout=20)
            except Exception:
                continue
            hits = sorted(set(m.group(1) for m in API.finditer(y.text)))
            if hits:
                print("JS", su, len(y.text)); print("  " + "\n  ".join(hits[:60]))
    except Exception as e:
        print("ERR", e)
