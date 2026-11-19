"""One-off check: which hiring software do the 'sitemap' companies use? Writes probe_out/*."""
import json, re, os, sys, requests
from concurrent.futures import ThreadPoolExecutor
os.makedirs("probe_out", exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
PAT = re.compile(r"[\w.-]*(darwinbox|keka\.com|zohorecruit|freshteam|ripplehire|peoplestrong|taleo|icims|ultipro|jobvite|ashbyhq|workable|recruitee|teamtailor|breezy|bamboohr|personio|brassring|kenexa|csod\.com|cornerstone|myworkdayjobs|successfactors|oraclecloud|eightfold|phenom|greenhouse|lever\.co|smartrecruiters|avature|naukri|hirist|instahyre|turbohire|superset|springverify|jobs\.ashbyhq|mynexthire|hrmantra|zwayam|talentrecruit|recruitcrm|skillate|xobin|imocha|mettl|hirepro|talview)[\w./-]*", re.I)
rep = json.load(open("engine/out/companies_report.json"))
todo = [r for r in rep if r.get("platform") == "sitemap"]
def one(r):
    out = {"company": r["company"], "careers": r["careers"], "hits": [], "final": None, "status": None}
    try:
        x = requests.get(r["careers"], headers=H, timeout=20, allow_redirects=True)
        out["final"], out["status"] = x.url, x.status_code
        hits = sorted(set(m.group(0)[:120] for m in PAT.finditer(x.url + " " + x.text)))
        out["hits"] = hits[:15]
    except Exception as e:
        out["status"] = type(e).__name__
    return out
with ThreadPoolExecutor(24) as ex:
    res = list(ex.map(one, todo))
json.dump(res, open("probe_out/ats_hits.json", "w"), indent=1)
# save a few Darwinbox careers pages for adapter work
dbx = set()
for r in res:
    for h in r["hits"]:
        m = re.search(r"([\w-]+\.darwinbox\.(?:in|com))", h, re.I)
        if m: dbx.add(m.group(1).lower())
json.dump(sorted(dbx), open("probe_out/darwinbox_hosts.json", "w"), indent=1)
for host in sorted(dbx)[:4]:
    for path in ("/ms/candidate/careers", "/ms/candidatev2/main/careers/allJobs"):
        try:
            x = requests.get(f"https://{host}{path}", headers=H, timeout=12)
            open(f"probe_out/{host}{path.replace('/','_')}.txt", "w").write(f"{x.status_code} {x.url}\n{x.headers.get('content-type')}\n\n{x.text[:200000]}")
            for js in re.findall(r'src="([^"]+\.js[^"]*)"', x.text)[:6]:
                u = js if js.startswith("http") else f"https://{host}{js if js.startswith('/') else '/'+js}"
                y = requests.get(u, headers=H, timeout=12)
                apis = sorted(set(re.findall(r'["\'](/?(?:ms|api)[\w/.-]*(?:job|career|opening|requisition)[\w/.-]*)["\']', y.text, re.I)))
                open(f"probe_out/{host}_apis.txt", "a").write(f"{u}\n" + "\n".join(apis[:200]) + "\n\n")
        except Exception as e:
            open(f"probe_out/{host}_err.txt", "a").write(f"{path} {e}\n")
from collections import Counter
c = Counter()
for r in res:
    for k in {re.sub(r"[^a-z]", "", PAT.search(h).group(1).lower())[:12] for h in r["hits"]}:
        c[k] += 1
print(c.most_common(40)); print(len(dbx), "darwinbox hosts")
# print results to the log (artifacts are not reachable from the workspace)
print("=====HITS=====")
for r in res:
    if r["hits"]:
        print("HIT", r["company"], "|", r["final"], "|", " ; ".join(r["hits"][:8]))
for f in sorted(os.listdir("probe_out")):
    if f.endswith(".txt"):
        print("=====FILE", f)
        print(open("probe_out/" + f).read()[:6000])
