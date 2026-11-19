import re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
B = "https://hdfcbank.ripplehire.com/candidate/candresource/candidate/"
t = requests.get(B + "apps/candidates/controller/candidatejoblist_controller.js", headers=H, timeout=20).text
for i, line in enumerate(t.splitlines()):
    if 40 <= i <= 80 or 230 <= i <= 275:
        print("L%04d %s" % (i, line.strip()[:220]))
