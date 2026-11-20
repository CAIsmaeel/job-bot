import re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
t = requests.get("https://flipkart.turbohire.co/main.0fbeb7233f472c0db0a8.chunk.js", headers=H, timeout=40).text
seen = set()
for k in re.finditer(r"/api/[A-Za-z]*[Cc]areer[A-Za-z]*/?[^\"'`]{0,80}", t):
    v = k.group(0)
    if v in seen or "reports" in v: continue
    seen.add(v)
    print("U", v, "::", re.sub(r"\s+", " ", t[max(0, k.start()-160):k.start()+120]))
for k in re.finditer(r"[Pp]ublic[A-Za-z]*[Jj]ob|jobsforcareerpage|careerpagejobs|getJobsFor|openjobs|OpenJobs|publishedJobs", t):
    v = t[k.start():k.start()+40]
    if v in seen: continue
    seen.add(v); print("F", re.sub(r"\s+", " ", t[max(0, k.start()-200):k.start()+250]))
    if len(seen) > 60: break
