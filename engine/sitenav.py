"""Shared site shell: one header and one footer on every page (landing, app, guides, jobs, legal).
Styles live in /fr.css (foundation, also loaded by the app) and /fr-pages.css (page layer)."""

LINKS = [("home", "/", "Home", "Home"), ("app", "/app/", "Practice", "Practice"), ("guides", "/interview/", "Guides", "Guides"),
         ("jobs", "/jobs/", "Jobs", "Jobs"), ("pricing", "/#price", "Pricing", "Pricing")]

CSS = ""  # kept for older callers; styles are in /fr.css


def head(pages=True):
    """<link> tags to put at the END of <head>, after the page's own styles."""
    return ('<link rel="preload" href="/fonts/jakarta-500.woff2" as="font" type="font/woff2" crossorigin>'
            '<link rel="stylesheet" href="/fr.css">' + ('<link rel="stylesheet" href="/fr-pages.css">' if pages else ""))


def html(active="", logo=True):
    cur = ' aria-current="page"'
    links = "".join('<a href="%s"%s><span class="fl">%s</span><span class="sh">%s</span></a>' % (u, cur if k == active else "", t, sh)
                    for k, u, t, sh in LINKS)
    lg = '<a class="lg" href="/" aria-label="FinRehearse home"><img src="/logo.svg" alt="FinRehearse" width="140" height="28"></a>'
    return ('<header class="sitehdr"><div class="in">%s<nav aria-label="Site">%s</nav>'
            '<a class="launch" href="/app/">Launch App</a></div></header>') % (lg, links)


def footer():
    return '''<footer class="sitefoot"><div class="in"><div class="cols">
<div class="about"><img src="/logo-light.svg" alt="FinRehearse" width="130" height="26"><p>Practise real ERP finance work before your interview. Free finance jobs from company career pages.</p></div>
<div><h4>Product</h4><ul><li><a href="/app/">Practice app</a></li><li><a href="/interview/">Interview guides</a></li><li><a href="/#price">Pricing</a></li><li><a href="/verify/">Verify a certificate</a></li></ul></div>
<div><h4>Jobs</h4><ul><li><a href="/jobs/">All finance jobs</a></li><li><a href="/jobs/browse/">Browse by city or area</a></li><li><a href="/jobs/freshers/">Jobs for freshers</a></li><li><a href="https://t.me/financeopeningsindia">Telegram channel</a></li></ul></div>
<div><h4>Legal</h4><ul><li><a href="/terms.html">Terms</a></li><li><a href="/privacy.html">Privacy</a></li><li><a href="/refund.html">Refunds</a></li><li><a href="/contact.html">Contact</a></li></ul></div>
</div><div class="legal-note"><p>FinRehearse is an independent educational simulator. It is not SAP software and is not affiliated with, sponsored by or endorsed by SAP SE. SAP and S/4HANA are trademarks or registered trademarks of SAP SE in Germany and other countries.</p><p>&copy; 2026 FinRehearse</p></div></div></footer>'''
