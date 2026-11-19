"""Static, Google-readable job pages: one per city, company, finance area and freshers, plus sitemap.xml.

Each page is plain HTML (no JavaScript needed to see the jobs), with its own title and description, so a
search like "finance jobs in Pune" or "HDFC Bank finance jobs" can land on it. Pages with fewer than
MIN_JOBS jobs are skipped so Google never sees near-empty pages.
"""
import html, os, re
from datetime import datetime, timezone

MIN_JOBS = 3
FRESHER = re.compile(r"fresher|trainee|graduate|intern\b|internship|apprentice|entry[ -]level|junior|\bjr\b|articleship|"
                     r"\bca inter\b|semi[- ]qualified|management trainee|\bmt\b", re.I)
AREA_SLUG = {"FP&A / Business Finance": ("fpa", "FP&A and Business Finance"), "Accounts Payable / P2P": ("accounts-payable", "Accounts Payable (P2P)"),
             "Accounts Receivable / O2C": ("accounts-receivable", "Accounts Receivable (O2C)"),
             "Record to Report / GL": ("record-to-report", "Record to Report (R2R) and GL"),
             "Controllership / Reporting": ("financial-reporting", "Controllership and Financial Reporting"), "Tax": ("tax", "Tax"),
             "Audit / Assurance / SOX": ("audit", "Audit, Assurance and SOX"), "Treasury": ("treasury", "Treasury"),
             "Costing": ("cost-accounting", "Cost Accounting"), "Deals / Valuation / IB": ("valuation", "Valuation, Deals and Investment Banking"),
             "Risk / Credit": ("credit-risk", "Credit and Risk"), "Payroll": ("payroll", "Payroll"),
             "Finance Transformation / Systems": ("finance-systems", "Finance Systems and ERP"),
             "Accounting / Finance (general)": ("accounting", "Accounting and Finance")}

CSS = """body{margin:0;background:#f7f5ef;color:#1d2a26;font:17px/1.6 "Atkinson Hyperlegible",system-ui,sans-serif}
main{max-width:860px;margin:0 auto;padding:28px 18px 60px}a{color:#145c4a}h1{font:600 2rem/1.2 Newsreader,Georgia,serif;margin:.2em 0 .3em}
.lede{color:#4a5752;max-width:68ch}.crumb{font-size:.9rem}.cta{background:#e5efe9;border-left:4px solid #145c4a;padding:12px 16px;margin:20px 0}
ul.jobs{list-style:none;padding:0;margin:0}ul.jobs li{background:#fff;border:1px solid #e1ddd2;border-radius:8px;padding:12px 16px;margin:8px 0}
.t{font-weight:700}.m{color:#5b6763;font-size:.93rem}.links{columns:3 200px;font-size:.95rem}.links a{display:block}
footer{margin-top:40px;font-size:.85rem;color:#6a746f}"""


def slug(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (s or "").lower().replace("&", " and "))).strip("-")


def page(site, path, title, h1, lede, jobs, city_of, tg, sim, related):
    rows = []
    for j in jobs[:150]:
        rows.append(f'<li><div class="t"><a href="{html.escape(j["url"])}" rel="nofollow noopener" target="_blank">{html.escape(j["title"])}</a></div>'
                    f'<div class="m">{html.escape(j["company"])} · {html.escape(city_of(j.get("location")))} · {html.escape(j.get("category") or "")}</div></li>')
    rel = "".join(f'<a href="{site}{p}">{html.escape(n)}</a>' for n, p in related)
    cta = (f'<div class="cta">New finance jobs every 2 hours on Telegram. <a href="{tg}">Join the free channel</a>.'
           + (f' Interview coming up? <a href="{sim}">Practise ERP finance work in the simulator</a>.' if sim else "") + "</div>") if tg else ""
    upd = datetime.now(timezone.utc).strftime("%d %b %Y")
    desc = f"{lede} {len(jobs)} openings, updated {upd}."
    return f"""<!doctype html><html lang="en-IN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(desc[:300])}">
<link rel="canonical" href="{site}{path}"><style>{CSS}</style></head><body><main>
<p class="crumb"><a href="{site}/">Home</a> › <a href="{site}/jobs/">All finance jobs</a> › <a href="{site}/jobs/browse/">Browse</a></p>
<h1>{html.escape(h1)}</h1><p class="lede">{html.escape(lede)} {len(jobs)} openings right now, taken from the companies' own career sites. Updated {upd}.</p>
{cta}<ul class="jobs">{"".join(rows)}</ul>
<h2>Related searches</h2><div class="links">{rel}</div>
<footer>Every job links to the employer's own page. We do not charge job seekers or employers for listings.</footer>
</main></body></html>"""


def build(jobs, out_dir, site, city_of, tg, sim):
    site = site.rstrip("/")
    groups = {}

    def add(path, title, h1, lede, j):
        g = groups.setdefault(path, {"title": title, "h1": h1, "lede": lede, "jobs": []})
        g["jobs"].append(j)

    for j in jobs:
        c = city_of(j.get("location"))
        c = c.split(" +")[0]
        if c and c != "India":
            add(f"/jobs/in/{slug(c)}/", f"Finance jobs in {c} | Accounts, FP&A, Audit, Tax", f"Finance jobs in {c}",
                f"Latest accounting and finance jobs in {c}: accounts, FP&A, audit, tax, treasury and more.", j)
        add(f"/jobs/at/{slug(j['company'])}/", f"{j['company']} finance jobs in India", f"{j['company']} finance jobs",
            f"Open finance and accounting roles at {j['company']} in India.", j)
        a = AREA_SLUG.get(j.get("category"))
        if a:
            add(f"/jobs/area/{a[0]}/", f"{a[1]} jobs in India", f"{a[1]} jobs in India",
                f"Latest {a[1]} jobs across India at banks, GCCs, Big 4 firms and corporates.", j)
        if FRESHER.search(j.get("title") or ""):
            add("/jobs/freshers/", "Finance jobs for freshers in India | Trainee, Graduate, Junior",
                "Finance jobs for freshers", "Entry-level finance jobs: trainee, graduate, junior and intern roles in accounts and finance.", j)
    groups = {p: g for p, g in groups.items() if len(g["jobs"]) >= MIN_JOBS}

    def links(prefix, limit=40):
        items = sorted(((g["h1"], p, len(g["jobs"])) for p, g in groups.items() if p.startswith(prefix)), key=lambda x: -x[2])
        return [(f"{h} ({n})", p) for h, p, n in items[:limit]]

    cities, comps, areas = links("/jobs/in/"), links("/jobs/at/", 60), links("/jobs/area/")
    fresh = [("Finance jobs for freshers", "/jobs/freshers/")] if "/jobs/freshers/" in groups else []
    for p, g in groups.items():
        rel = (cities[:12] + areas[:8] + fresh) if not p.startswith("/jobs/in/") else (areas[:14] + fresh + cities[:10])
        rel = [x for x in rel if x[1] != p]
        d = os.path.join(out_dir, p.strip("/"))
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(
            page(site, p, g["title"], g["h1"], g["lede"], g["jobs"], city_of, tg, sim, rel))

    # browse page that links every page (helps Google find them)
    def block(name, items):
        return f"<h2>{name}</h2><div class='links'>" + "".join(f'<a href="{site}{p}">{html.escape(n)}</a>' for n, p in items) + "</div>"
    body = (block("By city", links("/jobs/in/", 200)) + block("By finance area", links("/jobs/area/", 200))
            + block("For freshers", fresh) + block("By company", links("/jobs/at/", 500)))
    d = os.path.join(out_dir, "jobs", "browse")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(
        f"""<!doctype html><html lang="en-IN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Browse finance jobs in India by city, company and area</title><meta name="description" content="Finance and accounting jobs in India sorted by city, company and finance area. Updated every 2 hours.">
<link rel="canonical" href="{site}/jobs/browse/"><style>{CSS}</style></head><body><main><p class="crumb"><a href="{site}/">Home</a> › <a href="{site}/jobs/">All finance jobs</a></p>
<h1>Browse finance jobs</h1>{body}</main></body></html>""")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = ["/", "/jobs/", "/jobs/browse/", "/app/"] + sorted(groups)
    sm = "".join(f"<url><loc>{site}{u}</loc><lastmod>{now}</lastmod></url>" for u in urls)
    open(os.path.join(out_dir, "sitemap.xml"), "w").write(
        f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>')
    open(os.path.join(out_dir, "robots.txt"), "w").write(f"User-agent: *\nAllow: /\nSitemap: {site}/sitemap.xml\n")
    return len(groups)
