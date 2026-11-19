import re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
B = "https://hdfcbank.ripplehire.com/candidate/candresource/candidate/"
for f in ("require_main.js", "app.js"):
    t = requests.get(B + f, headers=H, timeout=20).text
    print("=== FILE", f); print(t[:7000])
# try likely joblist module locations
for p in ("apps/joblist/joblist_app.js", "apps/joblist/list/list_controller.js", "apps/joblistnew/joblistnew_app.js",
          "apps/joblist/list/list_view.js", "entities/joblist.js", "entities/job.js", "entities/jobs.js"):
    t = requests.get(B + p, headers=H, timeout=20)
    print("=== TRY", t.status_code, p)
    if t.status_code == 200: print(t.text[:5000])
