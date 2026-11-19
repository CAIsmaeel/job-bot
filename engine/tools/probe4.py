import re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
r = requests.get("https://hdfcbank.ripplehire.com/candidate/?token=pvB5iAMcmu4ydUh2IW2O&source=CAREERSITE", headers=H, timeout=20)
t = r.text
print("RH scripts:", re.findall(r'<script[^>]*src="([^"]+)"', t))
for m in re.findall(r"<script[^>]*>(.*?)</script>", t, re.S):
    m = re.sub(r"\s+", " ", m)
    if len(m) > 30: print("RH INLINE:", m[:2500])
r = requests.get("https://flipkart.turbohire.co/careerpage/4d757ba0-3d57-448a-b82c-238ed87ac90f", headers=H, timeout=20)
print("TH scripts:", re.findall(r'src="([^"]+)"', r.text))
for s in re.findall(r'src="(/static/js/[^"]+)"', r.text):
    y = requests.get("https://flipkart.turbohire.co" + s, headers=H, timeout=20).text
    for k in sorted(set(re.findall(r"""["'`]([^"'`\s]{0,60}(?:[Cc]areer[Pp]age|[Jj]ob[Ll]ist|[Oo]pening|getJobs|GetJobs|jobs\?)[^"'`\s]{0,80})["'`]""", y)))[:60]:
        print("TH", k)
    for k in sorted(set(re.findall(r"https://[a-z0-9.-]*turbohire[a-z0-9./-]*", y)))[:30]:
        print("TH host", k)
r = requests.get("https://jupiter.keka.com/careers", headers=H, timeout=20)
print("KEKA:", re.sub(r"\s+", " ", r.text)[:2400])
