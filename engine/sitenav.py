"""One site menu for every page (landing, jobs, guides, legal pages, the app). Always visible at the top."""

LINKS = [("home", "/", "Home", "Home"), ("app", "/app/", "Practice app", "Practice"), ("guides", "/interview/", "Interview guides", "Guides"),
         ("jobs", "/jobs/", "Finance jobs", "Jobs"), ("pricing", "/#price", "Pricing", "Pricing")]

CSS = """.sitehdr{position:sticky;top:0;z-index:60;background:#fff;border-bottom:1px solid #E5E7EB;font-family:'Plus Jakarta Sans',system-ui,-apple-system,sans-serif}
.sitehdr .in{max-width:1160px;margin:0 auto;padding:0 20px;display:flex;align-items:center;gap:20px;min-height:58px;box-sizing:border-box}
.sitehdr .lg{display:flex;align-items:center;margin:0}.sitehdr .lg img{height:30px;width:auto;display:block}
.sitehdr nav{display:flex;gap:2px;margin-left:auto;overflow-x:auto;scrollbar-width:none}.sitehdr nav::-webkit-scrollbar{display:none}
.sitehdr nav a{padding:8px 12px;margin:0;border-radius:8px;color:#111827;text-decoration:none;font-size:15px;font-weight:500;white-space:nowrap}
.sitehdr nav a:hover{background:#F3F4F6}.sitehdr nav a[aria-current]{color:#047857;font-weight:700;background:#ECFDF5}
@media (max-width:760px){.sitehdr .in{flex-wrap:wrap;gap:4px;padding:8px 12px 6px;min-height:0}.sitehdr nav{margin-left:-8px;width:calc(100% + 8px)}.sitehdr nav a{padding:7px 10px;font-size:14px}}
.sitehdr .sh{display:none}
@media (max-width:520px){.sitehdr .fl{display:none}.sitehdr .sh{display:inline}}
@media (max-width:400px){.sitehdr nav a{padding:6px 7px!important;font-size:13px}}
@media print{.sitehdr{display:none}}"""


def html(active="", logo=True):
    cur = ' aria-current="page"'
    links = "".join('<a href="%s"%s><span class="fl">%s</span><span class="sh">%s</span></a>' % (u, cur if k == active else "", t, sh)
                    for k, u, t, sh in LINKS)
    lg = ('<a class="lg" href="/" aria-label="FinRehearse home"><img src="/logo.svg" alt="FinRehearse" width="150" height="30"></a>'
          if logo else "")
    return '<header class="sitehdr"><div class="in">%s<nav aria-label="Site">%s</nav></div></header>' % (lg, links)
