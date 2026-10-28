"""Ismaeel's job bot.

Every run: read Telegram commands -> find fresh jobs -> ask Gemini to read each JD ->
build a tailored one-page CV + cover letter PDF -> send to Telegram.
Nothing here ever invents experience: the CV is assembled only from profile.json
(plus skills Ismaeel marks as learned with /learned).
"""
import datetime as dt
import html
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

import requests

ROOT = Path(__file__).parent
STATE_FILE = ROOT / "state.json"
OUT = ROOT / "out"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
DRY_RUN = os.environ.get("DRY_RUN") == "1"  # local testing: no network calls


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


CFG = load("config.json")
PROFILE = load("profile.json")
# Phone/email live in a GitHub secret so the repo can be public
PROFILE["contact"] = PROFILE["contact"].replace("{{CONTACT_LINE}}", os.environ.get(
    "CONTACT_LINE", "Kharghar, Navi Mumbai  •  linkedin.com/in/ismaeelsyed").strip())
LETTERS = load("letters.json")


# ---------------------------------------------------------------- state
def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(s):
    s["seen"] = s.get("seen", [])[-3000:]
    STATE_FILE.write_text(json.dumps(s, indent=1, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- telegram
def tg(method, **kw):
    if DRY_RUN:
        print(f"[tg {method}]", {k: (v if k != "files" else "<file>") for k, v in kw.items()})
        return {"ok": True, "result": []}
    files = kw.pop("files", None)
    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/{method}", data=kw, files=files, timeout=60)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "description": r.text[:200]}


def send(state, text):
    chat = state.get("chat_id")
    if not chat:
        return
    for i in range(0, len(text), 3900):
        tg("sendMessage", chat_id=chat, text=text[i:i + 3900], parse_mode="HTML", disable_web_page_preview="true")


def send_file(state, path, caption=""):
    chat = state.get("chat_id")
    if not chat:
        return
    with open(path, "rb") as f:
        tg("sendDocument", chat_id=chat, caption=caption[:1000], files={"document": (Path(path).name, f)})


HELP = (
    "Commands:\n"
    "/learned skill name — ye skill seekh li, ab se CV mein aayegi\n"
    "/unlearn skill name — galti se add hui skill hatao\n"
    "/skills — tumhari added skills\n"
    "/gaps — sabse zyada maangi gayi missing skills\n"
    "/pause — bot band\n/resume — bot chalu\n\n"
    "Note: bot har ghante chalta hai (7 AM – 11 PM), toh jawab agle run pe aayega."
)


def handle_commands(state):
    if DRY_RUN:
        return
    res = tg("getUpdates", offset=state.get("tg_offset", 0), timeout=0)
    for upd in res.get("result", []):
        state["tg_offset"] = upd["update_id"] + 1
        msg = upd.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        text = (msg.get("text") or "").strip()
        if not chat_id:
            continue
        if not state.get("chat_id"):
            state["chat_id"] = chat_id  # first person to talk to the bot owns it
            send(state, "✅ Bot connect ho gaya! Ab har ghante (7 AM – 11 PM) nayi jobs yahan aayengi.\n\n" + HELP)
            if text.lower().startswith(("/start", "/help")):
                continue
        if chat_id != state["chat_id"]:
            continue
        low = text.lower()
        learned = state.setdefault("learned", [])
        if low.startswith("/learned"):
            skill = text[len("/learned"):].strip()
            if skill and skill.lower() not in [s.lower() for s in learned]:
                learned.append(skill)
                send(state, f"✅ <b>{html.escape(skill)}</b> add ho gaya. Ab se jahan relevant ho, CV mein aayega.")
            else:
                send(state, "Skill ka naam likho, jaise: /learned LBO modelling")
        elif low.startswith("/unlearn"):
            skill = text[len("/unlearn"):].strip().lower()
            state["learned"] = [s for s in learned if s.lower() != skill]
            send(state, "🗑️ Hata diya.")
        elif low.startswith("/skills"):
            send(state, "Tumhari added skills:\n" + ("\n".join("• " + html.escape(s) for s in learned) or "Abhi koi nahi."))
        elif low.startswith("/gaps"):
            send(state, gap_report(state, days=30))
        elif low.startswith("/pause"):
            state["paused"] = True
            send(state, "⏸️ Bot pause. /resume se wapas chalu karo.")
        elif low.startswith("/resume"):
            state["paused"] = False
            send(state, "▶️ Bot chalu.")
        elif low.startswith("/start") or low.startswith("/help"):
            send(state, HELP)


# ---------------------------------------------------------------- gaps
def gap_report(state, days=7):
    cutoff = (dt.datetime.now(IST) - dt.timedelta(days=days)).date().isoformat()
    counts, label = {}, {}
    for g in state.get("gap_log", []):
        if g["date"] >= cutoff:
            k = g["skill"].strip().lower()
            counts[k] = counts.get(k, 0) + 1
            label.setdefault(k, g["skill"].strip())
    if not counts:
        return "Pichhle dino mein koi khaas skill gap nahi mila. 👍"
    top = sorted(counts.items(), key=lambda x: -x[1])[:6]
    lines = [f"📚 <b>Pichhle {days} din ki jobs mein sabse zyada maangi gayi missing skills:</b>"]
    for i, (k, n) in enumerate(top, 1):
        lines.append(f"{i}. {html.escape(label[k])} — {n} jobs")
    lines.append(f"\n👉 Pehle <b>{html.escape(label[top[0][0]])}</b> seekho. Seekh lo toh bhejo: /learned {html.escape(label[top[0][0]])}")
    return "\n".join(lines)


def maybe_daily_digest(state):
    now = dt.datetime.now(IST)
    today = now.date().isoformat()
    if now.hour < 21 or state.get("last_digest") == today:
        return
    items = sorted([n for n in state.get("near_miss", []) if n["date"] == today], key=lambda n: -n["score"])[:10]
    sent = state.get("sent_count", {}).get(today, 0)
    lines = [f"🌙 <b>Aaj ka summary</b>: {sent} job(s) CV ke saath bheji."]
    if items:
        lines.append("\n<b>Thoda kam match wali jobs</b> (score 45–64, CV nahi banaya). Pasand aaye toh khud dekh lo:")
        for i, n in enumerate(items, 1):
            lines.append(f"{i}. {n['score']} · <a href=\"{html.escape(n['url'])}\">{html.escape(n['title'])}</a> @ {html.escape(n['company'])} ({html.escape(n['site'])})")
    else:
        lines.append("Aaj aur koi kaam ki job nahi mili.")
    send(state, "\n".join(lines))
    state["last_digest"] = today
    cutoff = (now - dt.timedelta(days=3)).date().isoformat()
    state["near_miss"] = [n for n in state.get("near_miss", []) if n["date"] >= cutoff]


def maybe_weekly_report(state):
    now = dt.datetime.now(IST)
    week = now.strftime("%G-W%V")
    if now.weekday() == 6 and now.hour >= 18 and state.get("last_weekly") != week:  # Sunday evening
        send(state, gap_report(state, days=7))
        state["last_weekly"] = week


# ---------------------------------------------------------------- jobs
def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


DIAG = {"per_site": {}, "errors": []}
START = time.time()
SCRAPE_BUDGET, TOTAL_BUDGET = 5 * 60, 10 * 60  # seconds; keeps GitHub's free minutes safe


def fetch_jobs():
    from jobspy import scrape_jobs
    import pandas as pd

    frames = []
    for site in CFG["sites"]:
        t0 = time.time()
        DIAG["per_site"][site] = 0
        for term in CFG["search_terms"]:
            if time.time() - START > SCRAPE_BUDGET:
                DIAG["errors"].append(f"time budget hit while scraping {site}")
                break
            try:
                df = scrape_jobs(
                    site_name=[site], search_term=term, location=CFG["location"],
                    distance=CFG["distance_miles"], results_wanted=CFG["results_per_search"],
                    hours_old=CFG["hours_old"], country_indeed="India",
                    fetch_description=True, verbose=0,
                )
                if df is not None and len(df):
                    frames.append(df)
                    DIAG["per_site"][site] += len(df)
            except Exception as e:
                print(f"{site} / {term}: {str(e)[:150]}")
                DIAG["errors"].append(f"{site}: {str(e)[:120]}")
            time.sleep(6 if site == "linkedin" else 2)
        DIAG[f"secs_{site}"] = int(time.time() - t0)
    if not frames:
        return []
    df = pd.concat(frames, ignore_index=True)
    jobs = []
    for _, r in df.iterrows():
        d = {k: (None if (isinstance(v, float) and v != v) else v) for k, v in r.to_dict().items()}
        jobs.append(d)
    return jobs


def annual_inr(job):
    amt = job.get("max_amount") or job.get("min_amount")
    if not amt or (job.get("currency") or "INR") != "INR":
        return None
    mult = {"yearly": 1, "monthly": 12, "weekly": 52, "daily": 260, "hourly": 2080}.get(str(job.get("interval") or "yearly").lower(), 1)
    return float(amt) * mult


def prefilter(jobs, state):
    seen = set(state.get("seen", []))
    inc, exc = CFG["title_must_contain_any"], CFG["title_exclude_any"]
    out, keys = [], set()
    for j in jobs:
        key = norm(j.get("company")) + "|" + norm(j.get("title"))
        jid = str(j.get("id") or j.get("job_url"))
        if key in keys or key in seen or jid in seen:
            continue
        keys.add(key)
        title = " " + str(j.get("title") or "").lower() + " "
        comp = " " + str(j.get("company") or "").lower() + " "
        loc = str(j.get("location") or "").lower()
        if not (j.get("is_remote") or any(p in loc for p in CFG.get("allowed_locations", ["mumbai"]))):
            seen.add(key)  # Gurugram / Bengaluru / Pune etc: outside Mumbai region
            continue
        if any(x in comp for x in CFG.get("exclude_companies", [])):
            seen.add(key)  # bank / lender / Big 4 / advisory firm: not for him
            continue
        if not any(w in title for w in inc) or any(w in title for w in exc):
            seen.add(key)
            continue
        sal = annual_inr(j)
        if sal and sal < CFG["min_salary_inr_per_year"]:
            seen.add(key)
            continue
        if len(str(j.get("description") or "")) < 200:
            continue  # no JD to read yet; try again next run
        j["_key"], j["_jid"] = key, jid
        out.append(j)
    state["seen"] = list(seen)
    return out



# ---------------------------------------------------------------- rule-based fallback (no AI)
DOMAIN_WORDS = {
    "advisory": ["due diligence", "transaction", "valuation", "m&a", "mergers", "acquisition", "deal", "quality of earnings", "financial modelling", "financial modeling", "dcf"],
    "fpa": ["fp&a", "budget", "forecast", "variance", "mis", "planning", "business finance", "business partner", "commercial finance", "controller", "month end", "month-end", "aop", "cost control", "corporate development", "unit economics"],
    "consulting": ["consult", "client engagement", "advisory services", "process improvement", "strategy", "transformation", "stakeholder"],
}
SKILL_WORDS = {
    "Financial due diligence": ["due diligence", "fdd"],
    "Quality of earnings": ["quality of earnings", "qoe", "normalised ebitda", "normalized ebitda", "adjusted ebitda"],
    "DCF valuation (WACC, terminal value)": ["dcf", "discounted cash flow", "valuation", "wacc"],
    "Ind AS (101, 116)": ["ind as", "ind-as", "indas"],
    "Consolidation": ["consolidation"],
    "3-statement modelling": ["financial model", "three statement", "3 statement", "3-statement"],
    "AOP": ["aop", "annual operating plan", "budget"],
    "Variance analysis": ["variance"],
    "MIS reporting": ["mis", "management reporting"],
    "Statutory audit": ["statutory audit", "audit"],
    "Internal controls": ["internal control", "icfr", "ifc", "sox"],
    "Excel & VBA (certified)": ["excel", "vba", "macro"],
    "Power BI (DAX)": ["power bi", "powerbi", "dax"],
    "Alteryx (certified)": ["alteryx"],
    "SAP": ["sap"],
    "Oracle": ["oracle"],
    "Tally": ["tally"],
    "Financial statements (Ind AS)": ["financial statement", "financial reporting", "book closure", "finalisation", "finalization"],
    "Cash flow & fund flow": ["cash flow", "fund flow", "liquidity", "working capital"],
    "GST & direct tax": ["gst", "direct tax", "income tax", "indirect tax"],
}
GAP_WORDS = {
    "LBO modelling": (["lbo", "leveraged buyout"], "2 weeks"),
    "Capital IQ / PitchBook": (["capital iq", "capiq", "pitchbook", "pitch book"], "1 week"),
    "Bloomberg terminal": (["bloomberg"], "1 week"),
    "US GAAP": (["us gaap", "usgaap"], "1 month"),
    "IFRS": (["ifrs"], "2 weeks"),
    "CFA": (["cfa"], "long term"),
    "SQL": ([" sql"], "2 weeks"),
    "Python": (["python"], "1 month"),
    "Tableau": (["tableau"], "1 week"),
    "Hyperion / Anaplan (EPM tools)": (["hyperion", "anaplan", "oracle epm", "sap bpc", "adaptive insights"], "2 weeks"),
    "Pitch books / IMs": (["pitch book", "pitchbook", "information memorandum", " im "], "1 week"),
    "Big 4 experience": (["big 4 experience", "big four experience", "big4 experience"], "n/a"),
    "Transfer pricing": (["transfer pricing"], "2 weeks"),
    "Capex planning & tracking": (["capex", "capital expenditure"], "1 week"),
    "Cost & profitability analysis": (["cost accounting", "costing", "profitability analysis", "product cost", "standard cost"], "2 weeks"),
    "Month-end close": (["month end close", "month-end close", "monthly close", "book closing"], "1 week"),
    "SAP FICO / S/4HANA": (["sap fico", "s/4hana", "s4hana", "s/4 hana"], "2 weeks"),
    "Revenue recognition (Ind AS 115)": (["ind as 115", "revenue recognition", "ifrs 15"], "1 week"),
    "Treasury & cash management": (["treasury", "cash management", "fund management"], "2 weeks"),
    "Unit economics & pricing": (["unit economics", "pricing analysis", "contribution margin"], "1 week"),
}

# True headline phrases, picked by what the JD asks for most (no-AI mode headline)
HEADLINE_WORDS = [
    ("FP&A", ["fp&a", "financial planning"]),
    ("Business Finance", ["business finance", "business partner", "commercial finance"]),
    ("Budgeting & Forecasting", ["budget", "forecast", "aop", "annual operating plan"]),
    ("MIS & Management Reporting", ["mis", "management report", "dashboard"]),
    ("Variance Analysis", ["variance", "budget vs actual"]),
    ("Financial Reporting (Ind AS)", ["financial reporting", "ind as", "ifrs", "financial statement"]),
    ("Consolidation", ["consolidat"]),
    ("Financial Due Diligence", ["due diligence", "fdd", "quality of earnings"]),
    ("Internal Controls", ["internal control", "icfr", "ifc", "sox"]),
    ("Cash Flow & Liquidity", ["cash flow", "fund flow", "liquidity", "working capital"]),
    ("Process Automation", ["automation", "process improvement", "vba", "alteryx"]),
]
SHORT = {"FP&A": "FP&A", "Business Finance": "business finance", "Budgeting & Forecasting": "budgeting",
         "MIS & Management Reporting": "MIS reporting", "Variance Analysis": "variance analysis",
         "Financial Reporting (Ind AS)": "Ind AS reporting", "Consolidation": "consolidation",
         "Financial Due Diligence": "due diligence", "Internal Controls": "internal controls",
         "Cash Flow & Liquidity": "cash-flow reporting", "Process Automation": "automation"}
# Which real piece of work proves each headline area (one fact per key, never repeated)
EVIDENCE_KEY = {"FP&A": "aop", "Business Finance": "aop", "Budgeting & Forecasting": "aop", "Variance Analysis": "var",
                "MIS & Management Reporting": "mis", "Cash Flow & Liquidity": "mis", "Financial Reporting (Ind AS)": "ipo",
                "Consolidation": "ipo", "Financial Due Diligence": "fdd", "Internal Controls": "ctl", "Process Automation": "vba"}
EVIDENCE = {
    "aop": "built a client's annual operating plan from department budgets up, testing each assumption against prior-year actuals",
    "var": "set up budget-vs-actual variance reviews for a client's divisions",
    "ipo": "prepared Ind AS financial statements for 12 acquired entities ahead of a ₹2,600 Cr IPO, alongside a Big 4 team",
    "mis": "prepared the MIS and fund-flow reports management used to track liquidity during a ₹2,600 Cr IPO preparation",
    "fdd": "worked on the financial due diligence of a healthcare InsurTech acquisition",
    "ctl": "tested internal controls and CARO compliance across three statutory audits",
    "vba": "built an Excel VBA macro that saved the audit team 50+ hours a month",
}


SECTOR_WORDS = [
    ("real estate", ["real estate", "realty", "property", "warehousing", "industrial park", "logistics park"]),
    ("healthcare", ["healthcare", "hospital", "pharma", "life sciences", "medical", "insurtech"]),
    ("financial services", ["bfsi", "nbfc", "fintech", "banking", "insurance", "asset management", "wealth"]),
    ("manufacturing", ["manufacturing", "plant", "factory", "industrial", "auto components", "chemicals"]),
    ("consumer and retail", ["fmcg", "consumer", "retail", "d2c", "e-commerce", "ecommerce"]),
    ("infrastructure and energy", ["infrastructure", "infra ", "energy", "power sector", "power plant", "power generation", "renewable", "solar", "ports"]),
    ("technology", ["saas", "software", "it services", "technology company", "tech company"]),
    ("logistics", ["logistics", "supply chain", "shipping"]),
]
FOCUS_WORDS = [
    ("financial due diligence", ["due diligence", "fdd"]),
    ("valuations", ["valuation"]),
    ("M&A transactions", ["m&a", "mergers", "acquisition"]),
    ("transaction support", ["transaction"]),
    ("quality-of-earnings work", ["quality of earnings", "qoe"]),
    ("FP&A", ["fp&a", "financial planning"]),
    ("budgeting and forecasting", ["budget", "forecast"]),
    ("MIS and management reporting", ["mis", "management reporting"]),
    ("variance analysis", ["variance"]),
    ("group consolidation", ["consolidation"]),
    ("Ind AS reporting", ["ind as", "ind-as"]),
    ("internal controls", ["internal control", "icfr", "ifc", "sox"]),
    ("process improvement", ["process improvement", "automation", "transformation"]),
    ("IPO readiness", ["ipo", "listing", "drhp"]),
]
WHY_TEMPLATES = {
    "advisory": "{lead} {focus}{sector} is close to the deal-side work I do now, and it is where I want to build my career.",
    "fpa": "{lead} {focus}{sector} is close to the work I do now, and it is the direction I want to grow in.",
    "consulting": "{lead} {focus}{sector} is close to the client work I do now, and I would like to do more of it.",
}
BANNED = ["spearhead", "leverag", "synerg", "passionate", "dynamic", "results-driven", "esteemed", "utiliz", "utilis",
          "go-getter", "thought leader", "seamless", "cutting-edge", "world-class", "robust", "delve", "tapestry", "proven track record"]


def jd_text(job):
    return " " + (str(job.get("title") or "") + " " + str(job.get("description") or "")).lower() + " "


def btext(b, domain):
    t = b["text"]
    return t.get(domain) or t.get("advisory") if isinstance(t, dict) else t


def all_bullets():
    out = []
    for sid, sec in PROFILE["current_job"]["sections"].items():
        out += [(sid, b) for b in sec["bullets"]]
    out += [("articleship", b) for b in PROFILE["past_job"]["bullets"]]
    return out


def corpus(state):
    parts = [json.dumps(PROFILE, ensure_ascii=False), " ".join(state.get("learned", []))]
    return " ".join(parts)


def bullet_relevance(jd):
    return {b["id"]: sum(jd.count(t) for t in b.get("tags", [])) for _, b in all_bullets()}


def rules_why(job, domain):
    jd = jd_text(job)
    focus = sorted([(sum(jd.count(w) for w in ws), name) for name, ws in FOCUS_WORDS], reverse=True)
    focus = [n for c, n in focus if c > 0][:2]
    sec = sorted([(sum(jd.count(w) for w in ws), name) for name, ws in SECTOR_WORDS], reverse=True)
    sector = f" in {sec[0][1]}" if sec and sec[0][0] > 0 else ""
    if not focus:
        focus = [{"advisory": "transaction work", "fpa": "planning and reporting", "consulting": "finance problem-solving"}[domain]]
    company = str(job.get("company") or "").strip()
    if not company or len(company) > 40 or any(w in company.lower() for w in ["recruit", "placement", "consultan", "talent", "hr ", "staffing", "manpower"]):
        lead = "This role’s focus on"  # recruiter posting: don't praise the agency
    else:
        lead = f"{company}{'’' if company.endswith('s') else '’s'} focus on"
    focus.sort(key=lambda f: " and " in f)
    return WHY_TEMPLATES[domain].format(lead=lead, focus=(", " if any(" and " in f for f in focus) else " and ").join(focus), sector=sector)


def jd_focus(job, n=3):
    jd = jd_text(job)
    scored = sorted([(sum(jd.count(w) for w in ws), i, name) for i, (name, ws) in enumerate(HEADLINE_WORDS)], key=lambda x: (-x[0], x[1]))
    return [name for c, i, name in scored if c > 0][:n]


def rules_headline(job, domain):
    f = jd_focus(job, 3)
    if len(f) < 2:
        return PROFILE["headlines"][domain]
    return "  |  ".join(f)


def rules_summary(job, domain):
    f = jd_focus(job, 3)
    if not f:
        return PROFILE["summaries"][domain]
    keys = []
    for name in f + ["Financial Reporting (Ind AS)", "Budgeting & Forecasting"]:
        k = EVIDENCE_KEY[name]
        if k not in keys:
            keys.append(k)
    keys = keys[:2]
    if set(keys) == {"ipo", "mis"}:
        s2 = ("In my current role I prepared Ind AS financial statements for 12 acquired entities and the MIS and fund-flow "
              "reports management used to track liquidity ahead of a ₹2,600 Cr IPO, alongside a Big 4 team.")
    elif set(keys) == {"aop", "var"}:
        s2 = (f"In my current role I {EVIDENCE['aop']}, and set up the budget-vs-actual variance reviews that tracked it.")
    else:
        s2 = f"In my current role I {EVIDENCE[keys[0]]}, and {EVIDENCE[keys[1]]}."
    short = []
    for n in f:
        if SHORT[n] not in short:
            short.append(SHORT[n])
    short = (short + ["Ind AS reporting", "budgeting"])[:2] if len(short) < 2 else short[:2]
    s1 = f"Chartered Accountant (2025) with a year of hands-on {' and '.join(short)} work, after three years of statutory audit."
    return s1 + " " + s2


# ---------------------------------------------------------------- validation (no invented facts)
def nums(t):
    return set(re.findall(r"\d[\d,]*(?:\.\d+)?", t))


def acronyms(t):
    return set(re.findall(r"\b[A-Z][A-Z0-9&]{1,}\b", t))


CLAIM_TERMS = ["net debt", "working capital", "valuation", "dcf", "lbo", "model", "pitch", "forecast", "budget", "ebitda",
               "capital iq", "pitchbook", "bloomberg", "ifrs", "us gaap", "python", "sql", "tableau", "hyperion", "anaplan",
               "led ", "managed a team", "team of", "client-facing", "negotiat", "deal team", "sell-side",
               "board", "cfo", "investor", "lender", "bank", "treasury", "fundrais", "cross-border", "ipo", "audit"]


def bullet_pool(orig):
    """All verified wordings of the bullet this text came from (any domain variant)."""
    for _, b in all_bullets():
        texts = list(b["text"].values()) if isinstance(b["text"], dict) else [b["text"]]
        if orig in texts:
            return " ".join(texts).lower()
    return orig.lower()


STOP = set("a an the and or of to for in on at by with from into its it this that as was were be been is are over under up down across through during before after ahead each all both their his her our my".split())
SAFE_NEW = set("prepared built created delivered developed designed produced supported handled performed reviewed analysed analyzed monitored tracked using used including covering management monthly quarterly reporting reports report statements financial key team teams helped ensured led drove".split())
LEAK = ["working hours", "regular hours", "near home", "close to home", "work-life", "commute", "night shift",
        "epilep", "health", "halal", "shariah", "looking for", "seeking", "prefer"]


def words(t):
    return {w for w in re.findall(r"[a-z][a-z&\-]{2,}", t.lower()) if w not in STOP}


def safe_rewrite(new, orig, state, max_ratio=1.3, jd=""):
    """Accept an AI rewrite only if it keeps the same numbers, adds no new acronyms/tools and has no buzzwords."""
    if not isinstance(new, str):
        return orig
    new = new.strip().rstrip(".")
    if not new or len(new) > len(orig) * max_ratio + 25 or len(new) < len(orig) * 0.5:
        return orig
    if not nums(new.replace("**", "")) <= nums(orig.replace("**", "")):
        return orig
    known = acronyms(corpus(state))
    if not acronyms(new) <= known:
        return orig
    if any(w in new.lower() for w in BANNED):
        return orig
    pool = bullet_pool(orig)
    if any(t in new.lower() and t not in pool for t in CLAIM_TERMS):
        return orig  # mentions work/tools this bullet never had
    extra = words(new) - words(pool) - SAFE_NEW
    if extra - words(jd) or len(extra) > 3:
        return orig  # new content words only if they are the JD's own terms, max 3 (no "outlet-wise" inventions)
    if not nums(orig.replace("**", "")) <= nums(new.replace("**", "")):
        return orig  # dropped a key number (e.g. the ₹2,600 Cr IPO)
    if any(w in new.lower() for w in LEAK):
        return orig
    for b in re.findall(r"\*\*(.+?)\*\*", orig):  # keep key numbers bold
        if b in new and f"**{b}**" not in new:
            new = new.replace(b, f"**{b}**", 1)
    if new.count("**") % 2:
        new = new.replace("**", "")
    return new


# ---------------------------------------------------------------- analysis
def analyse_rules(job, state):
    jd = jd_text(job)
    dom_scores = {d: sum(jd.count(w) for w in ws) for d, ws in DOMAIN_WORDS.items()}
    domain = max(dom_scores, key=dom_scores.get)
    learned = state.get("learned", [])
    matched = [sk for sk, ws in SKILL_WORDS.items() if any(w in jd for w in ws)]
    matched += [sk for sk in learned if sk.lower() in jd]
    gaps = []
    for sk, (ws, t) in GAP_WORDS.items():
        if any(w in jd for w in ws) and not any(sk.lower().split(" ")[0] in l.lower() for l in learned):
            gaps.append({"skill": sk, "learn_time": t})
    years = None
    m = re.search(r"(\d{1,2})\s*(?:\+|plus)?\s*(?:-|–|to)?\s*(\d{1,2})?\s*\+?\s*(?:years|yrs)", jd)
    if m:
        years = int(m.group(1))
    # Preference (epilepsy: regular hours matter): in-company FP&A / business finance first,
    # in-house corporate development next, advisory-firm roles with deal-season late nights last.
    score = 40 + min(len(matched), 8) * 5 + {"fpa": 14, "advisory": 6, "consulting": 4}[domain]
    if "corporate development" in jd or "corp dev" in jd:
        score += 8
    company = str(job.get("company") or "").lower()
    if any(f in company for f in ["deloitte", "kpmg", "ernst", " ey", "pwc", "pricewaterhouse"]) or "big 4 firm" in jd:
        score -= 12
    if any(w in jd for w in ["24x7", "long hours", "work under extreme pressure", "night shift", "rotational shift"]):
        score -= 10
    title = " " + str(job.get("title") or "").lower() + " "
    # Backward-looking roles (reporting/compliance) rank below planning/business finance
    if any(w in title for w in ["external reporting", "statutory reporting", "regulatory reporting", "financial reporting", " audit", " tax", "accountant", "accounts executive", "compliance"]) \
            and not any(w in title for w in ["fp&a", "planning", "business finance", "controller"]):
        score -= 12
    if any(w in jd for w in [" ca ", "chartered accountant", "qualified ca"]):
        score += 8
    if years is not None and years >= 4:
        score -= 30
    if years is not None and years >= 5:
        score = 0  # far too senior for ~1 year post-qualification: no point applying
    score -= 5 * len(gaps)
    debt = any(w in jd for w in ["debt syndication", "dcm", "loan syndication", "lending", "fixed income", "credit underwriting"])
    halal_ok = not ("investment bank" in jd and debt)
    rel = bullet_relevance(jd)
    sec_rel = {sid: sum(rel[b["id"]] for b in sec["bullets"]) for sid, sec in PROFILE["current_job"]["sections"].items()}
    base_order = {"advisory": ["fdd", "ipo", "budget"], "fpa": ["budget", "ipo", "fdd"], "consulting": ["fdd", "budget", "ipo"]}[domain]
    order = sorted(base_order, key=lambda s: (-sec_rel[s], base_order.index(s)))
    return clean_analysis({
        "score": max(0, min(100, score)), "domain": domain, "required_years": years, "halal_ok": halal_ok,
        "matched_skills": matched, "section_order": order, "gaps": gaps,
        "why_line": rules_why(job, domain),
        "role_title": job.get("title"), "company": job.get("company"),
        "match_note": f"{len(matched)} skills JD se match (no-AI mode)",
        "relevance": rel, "rewrites": {}, "ai": False,
        "headline": rules_headline(job, domain), "summary": rules_summary(job, domain),
    }, state)


def all_skills(state):
    return PROFILE["finance_skills"] + PROFILE["tool_skills"] + state.get("learned", [])


AI_OFF = {"off": False}


def analyse(job, state):
    base = analyse_rules(job, state)
    if not GEMINI_KEY or AI_OFF["off"]:
        return base
    try:
        return analyse_ai(job, state, base)
    except Exception as e:
        print("AI failed, using rules:", str(e)[:150])
        DIAG["errors"].append("AI: " + str(e)[:120])
        return base


def call_gemini(prompt):
    last_err = None
    for model in CFG["gemini_models"]:
        for attempt in range(2):
            try:
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"x-goog-api-key": GEMINI_KEY, "Content-Type": "application/json"},
                    json={"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                          "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4}},
                    timeout=90,
                )
                if r.status_code == 429:
                    last_err = f"{model} quota/rate limit (429)"
                    if attempt == 0:
                        time.sleep(15)
                        continue
                    break  # this model's free quota is used up -> try next model
                if r.status_code == 404:
                    last_err = f"{model} not found (404)"
                    break
                r.raise_for_status()
                return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
            except Exception as e:
                last_err = e
                time.sleep(5)
    AI_OFF["off"] = True  # don't waste minutes retrying for the rest of this run
    raise RuntimeError(f"Gemini failed: {last_err}")


def analyse_ai(job, state, base):
    d = base["domain"]
    lines = [f"[{b['id']}] ({sid}) {btext(b, d)}" for sid, b in all_bullets()]
    prompt = f"""You are a senior finance recruiter in Mumbai rewriting a Chartered Accountant's CV for ONE specific job. Answer ONLY with JSON.

CANDIDATE FACTS: {PROFILE['facts_for_matching']}
CANDIDATE SKILLS (only these exist): {json.dumps(all_skills(state))}
CURRENT PROFILE SUMMARY: {PROFILE['summaries'][d]}
CURRENT CV BULLETS (id, section, text; **bold** marks key numbers):
{chr(10).join(lines)}

Pure reporting / audit / tax / compliance roles score about 12 points lower (he wants forward-looking work). Banks, lenders and Big 4 / advisory firms are already excluded.
His preferences: FP&A / Business Finance / Finance Controller roles inside a company FIRST (he needs regular working hours and enough sleep), then in-house Corporate Development / M&A teams, then finance consulting. Roles at Big 4 or advisory firms with deal-season late nights, night shifts or 'long hours' should score lower (about 15 points less than an equivalent in-company role).
Investment banking only if Shariah-compliant (no interest-based lending, conventional debt syndication or conventional banking products).
Target fixed pay ₹13 LPA+. Navi Mumbai / Mumbai.

JOB:
Title: {job.get('title')}
Company: {job.get('company')}
Location: {job.get('location')}
Description:
{str(job.get('description'))[:7000]}

RULES FOR REWRITING (very important):
- Rewrite EVERY bullet so it speaks the JD's language: use the JD's own terms for the same work, lead with what this employer cares about, and cut what it doesn't.
- Keep every fact true. Do NOT add any tool, skill, number, client, sector, responsibility or result that is not already in that bullet. Keep all numbers exactly as written and keep the ** around them.
- One line of natural, plain English per bullet, past tense, starting with a strong verb; about the same length as the original. No buzzwords (spearheaded, leveraged, synergy, dynamic, passionate, results-driven, robust, seamless).
- The summary: exactly 2 sentences, plain recruiter-friendly English. Sentence 1: "Chartered Accountant (2025) with a year of <the 2 JD functions he has really done> work and three years of statutory audit before that." Sentence 2: the two facts from his bullets that answer this JD's main requirements. No slogans, no "I build numbers people use", no adjectives about himself.
- The headline: 3 phrases from the JD's own wording for work he has really done.
- It must read like a sharp human wrote it, not AI.
- NEVER mention his preferences (working hours, location, commute, health, halal) anywhere in the CV.
- NEVER add the employer's context to his past work (e.g. do not call his dashboards "outlet-wise" because the JD says outlets). Use only words already in the bullet, plus at most two of the JD's terms for the SAME thing.
- Keep the strongest facts: the ₹2,600 Cr IPO, 12 entities, ~₹5 Cr liabilities, ₹2,000+ Cr audit, 50+ hours a month.

Return JSON with exactly these keys:
{{
 "score": integer 0-100 (fit for HIM: experience level, skills, domain preference; >4 years required or wrong domain => below 45),
 "domain": "advisory" | "fpa" | "consulting",
 "required_years": number or null,
 "halal_ok": true/false (false only if the role is centred on interest-based lending/debt/conventional banking products),
 "matched_skills": [skills from CANDIDATE SKILLS that the JD asks for, most important first],
 "section_order": ["fdd","ipo","budget"] reordered so the most relevant section is first,
 "bullet_order": [all bullet ids, most relevant to this JD first],
 "rewrites": {{"<bullet id>": "rewritten bullet", ... for every id}},
 "summary": "rewritten profile summary",
 "headline": "3 short role phrases separated by '  |  ', drawn from the JD and true for him (e.g. Transaction Advisory  |  Financial Due Diligence  |  Ind AS)",
 "gaps": [up to 4 objects {{"skill": short name of a skill/tool/qualification the JD clearly asks for that he does NOT have, "learn_time": realistic time to learn it e.g. "1 week", "1 month"}}],
 "why_line": one plain-English sentence for his cover letter on why THIS company/role appeals, citing a specific detail from the JD or company (no buzzwords; must not claim any experience or numbers),
 "role_title": clean role title,
 "company": clean company name,
 "match_note": one short Hinglish line on why it fits him (or why not)
}}"""
    a = call_gemini(prompt)
    a = clean_analysis(a, state)
    a["ai"] = True
    # Validate every AI rewrite against the true text; anything suspicious falls back to the verified version.
    safe = {}
    for _, b in all_bullets():
        shown = btext(b, d)  # the exact text Gemini was given
        r = safe_rewrite((a.get("rewrites") or {}).get(b["id"]), shown, state, jd=jd_text(job))
        safe[b["id"]] = btext(b, a["domain"]) if r == shown else r
    a["rewrites"] = safe
    s_ref = PROFILE["summaries"][d] + " " + PROFILE["summaries"][a["domain"]]
    summ = str(a.get("summary") or "").strip()
    ok = (180 < len(summ) < 520 and nums(summ) <= nums(s_ref) and acronyms(summ) <= acronyms(corpus(state))
          and not any(w in summ.lower() for w in BANNED) and not any(w in summ.lower() for w in LEAK)
          and len(words(summ) - words(corpus(state)) - words(jd_text(job))) <= 2)
    a["summary"] = base["summary"]  # AI summaries kept failing checks or sounded generated: use the clean JD-based one
    hl = str(a.get("headline") or "")
    a["headline"] = hl if (hl and len(hl) < 90 and acronyms(hl) <= acronyms(corpus(state)) | acronyms(str(job.get("description") or ""))
                           and not any(w in hl.lower() for w in BANNED)) else base["headline"]
    a["headline"] = base["headline"]  # consistent, true phrases picked from the JD
    a["cv_learn"] = base["gaps"]  # clean skill names only (AI gap names can be long/odd)
    why = a.get("why_line") or ""
    a["why_line"] = why if (why and not nums(why) and len(why) < 260 and not any(w in why.lower() for w in BANNED)) else base["why_line"]
    order = [i for i in (a.get("bullet_order") or []) if i in base["relevance"]]
    a["relevance"] = {i: (len(order) - order.index(i)) if i in order else 0 for i in base["relevance"]}
    for k in ("gaps", "matched_skills"):
        if not a.get(k):
            a[k] = base[k]
    return a


def clean_analysis(a, state):
    """Never trust the model blindly: keep only things that exist in the profile."""
    allowed = {s.lower(): s for s in all_skills(state)}
    a["matched_skills"] = [allowed[s.lower()] for s in a.get("matched_skills", []) if isinstance(s, str) and s.lower() in allowed]
    secs = list(PROFILE["current_job"]["sections"].keys())
    order = [s for s in a.get("section_order", []) if s in secs]
    a["section_order"] = order + [s for s in secs if s not in order]
    if a.get("domain") not in ("advisory", "fpa", "consulting"):
        a["domain"] = "advisory"
    a["score"] = int(a.get("score") or 0)
    a["gaps"] = [g for g in a.get("gaps", []) if isinstance(g, dict) and g.get("skill")][:4]
    a["why_line"] = (a.get("why_line") or "").strip()
    a.setdefault("relevance", {})
    a.setdefault("rewrites", {})
    return a


# ---------------------------------------------------------------- PDFs
def pdf_setup():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.fonts import addMapping
    for style, f in [("", "Regular"), ("-Bold", "Bold"), ("-Italic", "Italic"), ("-BoldItalic", "BoldItalic")]:
        pdfmetrics.registerFont(TTFont("Carlito" + style, str(ROOT / "fonts" / f"Carlito-{f}.ttf")))
    addMapping("Carlito", 0, 0, "Carlito")
    addMapping("Carlito", 1, 0, "Carlito-Bold")
    addMapping("Carlito", 0, 1, "Carlito-Italic")
    addMapping("Carlito", 1, 1, "Carlito-BoldItalic")


def md(t):
    t = re.sub(r"\*{3,}", "", str(t))  # never print stray markdown like "****"
    if t.count("**") % 2:
        t = t.replace("**", "")
    t = html.escape(t, quote=False)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)


def build_cv(a, state, path):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.colors import HexColor
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, ListFlowable, ListItem, Spacer
    from reportlab.lib.units import mm

    navy, grey = HexColor("#1F3A5F"), HexColor("#555555")
    base = ParagraphStyle("b", fontName="Carlito", fontSize=10.8, leading=14.4, spaceAfter=1.5)
    S = {
        "name": ParagraphStyle("n", parent=base, fontName="Carlito-Bold", fontSize=17, leading=20, alignment=TA_CENTER, textColor=navy),
        "head": ParagraphStyle("h", parent=base, alignment=TA_CENTER, textColor=grey, fontSize=10),
        "contact": ParagraphStyle("c", parent=base, alignment=TA_CENTER, fontSize=9),
        "sec": ParagraphStyle("s", parent=base, fontName="Carlito-Bold", textColor=navy, fontSize=11.4, spaceBefore=11, spaceAfter=2),
        "hl": ParagraphStyle("hl", parent=base, alignment=TA_CENTER, fontSize=10.2, textColor=navy),
        "body": ParagraphStyle("p", parent=base, alignment=TA_JUSTIFY),
        "role": ParagraphStyle("r", parent=base, fontName="Carlito-Bold", fontSize=10.3),
        "date": ParagraphStyle("d", parent=base, textColor=grey, fontSize=9, alignment=2),
        "sub": ParagraphStyle("u", parent=base, fontName="Carlito-BoldItalic", textColor=navy, spaceBefore=3),
    }
    width = A4[0] - 2 * 12.7 * mm - 12  # frame has 6pt padding each side

    def section(title):
        t = Table([[Paragraph(title.upper(), S["sec"])]], colWidths=[width])
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.8, navy), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 1), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
        return [t, Spacer(1, 3)]

    def role(left, right):
        t = Table([[Paragraph(left, S["role"]), Paragraph(right, S["date"])]], colWidths=[width * 0.78, width * 0.22])
        t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
        return t

    rel = a.get("relevance") or {}

    def ranked(items, limit=None):
        order = sorted(range(len(items)), key=lambda i: (-rel.get(items[i]["id"], 0), not items[i].get("core"), i))
        keep = order[:limit] if limit else order
        return [items[i] for i in keep]

    def text_of(b):
        return a.get("rewrites", {}).get(b["id"]) or btext(b, a["domain"])

    def bullets(items):
        return ListFlowable([ListItem(Paragraph(md(text_of(b)), base), leftIndent=12, value="•") for b in items],
                            bulletType="bullet", start="•", leftIndent=12, bulletFontSize=10.8,
                            bulletFontName="Carlito", bulletOffsetY=0, spaceBefore=1)

    def story(drop):
        d = a["domain"]
        st = [Paragraph(PROFILE["name"], S["name"]), Paragraph(md(a.get("headline") or PROFILE["headlines"][d]), S["head"]),
              Paragraph(md(PROFILE["contact"]).replace("linkedin.com/in/ismaeelsyed",
                        f'<a href="{PROFILE["linkedin_url"]}" color="#1F3A5F">linkedin.com/in/ismaeelsyed</a>'), S["contact"])]
        st += section("Profile") + [Paragraph(md(a.get("summary") or PROFILE["summaries"][d]), S["body"])]
        st += section("Experience")
        cj = PROFILE["current_job"]
        st.append(role(cj["title"], cj["dates"]))
        for n, sid in enumerate(a["section_order"]):
            sec = cj["sections"][sid]
            st.append(Paragraph(md(sec["heading"]), S["sub"]))
            st.append(bullets(ranked([b for b in sec["bullets"] if b["id"] not in drop], 3 if n == 0 else 2)))
        pj = PROFILE["past_job"]
        st.append(role(pj["title"], pj["dates"]))
        st.append(bullets(ranked([b for b in pj["bullets"] if b["id"] not in drop], 3)))
        st += section("Education")
        for deg, inst, yr in PROFILE["education"]:
            st.append(role(f"{deg}<font name='Carlito'>  —  {md(inst)}</font>", yr))
        st += section("Skills")
        fin_all = PROFILE["finance_skills"] + [s for s in state.get("learned", []) if s not in PROFILE["tool_skills"]]
        first = [s for s in a["matched_skills"] if s in fin_all]
        learn = [g["skill"] for g in a.get("cv_learn", a.get("gaps", [])) if g.get("learn_time") not in ("n/a", "long term")
                 and g["skill"] not in ("Big 4 experience", "CFA")]
        fin = first + learn + [s for s in fin_all if s not in first]  # JD skills he is learning before the interview
        tools = [s for s in a["matched_skills"] if s in PROFILE["tool_skills"]]
        tools += [s for s in PROFILE["tool_skills"] if s not in tools]
        st.append(Paragraph("<b>Finance:</b> " + md(", ".join(fin)), base))
        st.append(Paragraph("<b>Tools:</b> " + md(", ".join(tools)), base))
        return st

    optional = [b["id"] for sec in PROFILE["current_job"]["sections"].values() for b in sec["bullets"] if b.get("optional")]
    optional += [b["id"] for b in PROFILE["past_job"]["bullets"] if b.get("optional")]
    optional.sort(key=lambda i: rel.get(i, 0))  # least relevant goes first if space is short
    drop = []
    for _ in range(len(optional) + 1):
        pages = []
        doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=12.7 * mm, rightMargin=12.7 * mm,
                                topMargin=11 * mm, bottomMargin=10 * mm, title="Ismaeel Syed - CV", author="Ismaeel Syed")
        doc.build(story(drop), onLaterPages=lambda c, d: pages.append(1))
        if not pages or len(drop) == len(optional):
            break
        drop.append(optional[len(drop)])  # over one page: drop least important bullet and retry


def build_letter(a, job, path):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.units import mm

    navy = HexColor("#1F3A5F")
    base = ParagraphStyle("b", fontName="Carlito", fontSize=11, leading=15, spaceAfter=9)
    role_t = a.get("role_title") or job.get("title")
    company = a.get("company") or job.get("company")
    st = [Paragraph(PROFILE["name"], ParagraphStyle("n", parent=base, fontName="Carlito-Bold", fontSize=16, textColor=navy, spaceAfter=0))]
    t = Table([[Paragraph(md(PROFILE["contact"]), ParagraphStyle("c", parent=base, fontSize=9, textColor=HexColor("#555555"), spaceAfter=0))]],
              colWidths=[A4[0] - 2 * 25 * mm - 12])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.8, navy), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    st += [t, Spacer(1, 14)]
    st.append(Paragraph(dt.datetime.now(IST).strftime("%d %B %Y"), base))
    loc = str(job.get("location") or "Mumbai").split(",")[0]
    st.append(Paragraph(f"Hiring Team<br/>{md(str(company))}<br/>{md(loc)}", base))
    st.append(Paragraph(f"<b>Re: {md(str(role_t))}</b>", base))
    st.append(Paragraph("Dear Hiring Team,", base))
    focus = jd_focus(job, 4)
    keys = []
    for name in focus + ["Financial Reporting (Ind AS)", "Budgeting & Forecasting", "Financial Due Diligence"]:
        k = EVIDENCE_KEY[name]
        if k not in keys:
            keys.append(k)
    keys = keys[:3]
    if "ipo" in keys and "mis" in keys:  # tell the IPO story together: statements first, then MIS
        keys.remove("mis")
        keys.insert(keys.index("ipo") + 1, "mis")
    needs = []
    for n in focus[:3]:
        if SHORT[n] not in needs:
            needs.append(SHORT[n])
    ask = (", ".join(needs[:-1]) + " and " + needs[-1]) if len(needs) > 1 else (needs[0] if needs else "")
    p1 = f"I would like to be considered for the {role_t} role at {company}."
    if ask:
        p1 += f" The role asks for {ask}, which is close to what I have been doing for the past year."
    proof = []
    for k in keys:
        t = LETTERS["proof"][k]
        if k == "mis" and "ipo" in keys and keys.index("ipo") < keys.index("mis"):
            t = LETTERS["proof"]["mis_after_ipo"]
        if k == "var" and "aop" in keys and keys.index("aop") < keys.index("var"):
            t = LETTERS["proof"]["var_after_aop"]
        elif k == "var" and proof:
            t = "Separately, " + t[0].lower() + t[1:]
        proof.append(t)
    st.append(Paragraph(md(p1), base))
    st.append(Paragraph(md(" ".join(proof)), base))
    st.append(Paragraph(md(LETTERS["closing"]), base))
    st.append(Paragraph("Regards,<br/><b>Ismaeel Syed, CA</b>", base))
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=25 * mm, rightMargin=25 * mm, topMargin=20 * mm, bottomMargin=18 * mm,
                      title="Ismaeel Syed - Cover Letter", author="Ismaeel Syed").build(st)


# ---------------------------------------------------------------- message
def job_message(a, job):
    e = lambda x: html.escape(str(x or ""))
    sal = annual_inr(job)
    pay = f"₹{sal / 1e5:.1f} L" if sal else "pay not disclosed"
    posted = job.get("date_posted") or "recent"
    lines = [
        f"🟢 <b>{a['score']}/100 — {e(a.get('role_title') or job.get('title'))}</b>",
        f"🏢 {e(a.get('company') or job.get('company'))}",
        f"📍 {e(job.get('location'))}  ·  💰 {e(pay)}  ·  🕒 {e(posted)}  ·  {e(job.get('site'))}",
        f"✅ {e(a.get('match_note'))}",
    ]
    lines.append("🧠 CV: " + ("AI ne har line is JD ke shabdon mein likhi (sab facts verified)" if a.get("ai")
                              else "is JD ke domain ke hisaab se lines aur order badla (no-AI)"))
    if a["matched_skills"]:
        lines.append("🎯 JD match: " + e(", ".join(a["matched_skills"][:6])))
    if a["gaps"]:
        lines.append("📚 Seekhna padega: " + e(", ".join(f"{g['skill']} ({g.get('learn_time', '?')})" for g in a["gaps"])))
        lines.append("   ↳ ⚠️ Ye skills CV ke Skills section mein DAALE hain — interview se pehle zaroor seekh lena. Seekh liya toh: /learned " + e(a["gaps"][0]["skill"]))
    if a.get("required_years"):
        lines.append(f"🧾 Experience maanga: {e(a['required_years'])} saal")
    lines.append(f"\n👉 <a href=\"{e(job.get('job_url_direct') or job.get('job_url'))}\">Apply link</a>  — neeche CV + cover letter ready hai")
    return "\n".join(lines)


# ---------------------------------------------------------------- referrals
AGENCY = ["recruit", "placement", "consultan", "talent", "staffing", "manpower", "hiring", "search", "hr services", "people"]


def referral_block(a, job):
    from urllib.parse import quote
    company = str(a.get("company") or job.get("company") or "").strip()
    role = str(a.get("role_title") or job.get("title") or "this").strip()
    if not company or any(w in company.lower() for w in AGENCY):
        return None  # posted by a recruitment agency: no one inside to ask
    def ppl(q):
        return "https://www.linkedin.com/search/results/people/?keywords=" + quote(q)
    links = [
        ("🎓 Alumni (St. Joseph's / Osmania / M. Bhaskara Rao)", ppl(f'{company} "St. Joseph" OR Osmania OR "Bhaskara Rao"')),
        ("🧾 CAs in their finance team", ppl(f"{company} chartered accountant finance")),
        ("👔 Finance head / hiring manager", ppl(f'{company} "finance controller" OR "head of finance" OR "FP&A manager" OR CFO')),
    ]
    msgs = [
        ("Alumni ko",
         f"Hi [Name], saw you're at {company}. I'm a fellow [St. Joseph's / Osmania] grad, now a CA in Mumbai. "
         f"I've applied for the {role} role there. Would you be open to a quick chat about the team, or a referral if I seem a fit? Thanks either way!"),
        ("Finance team ke CA ko",
         f"Hi [Name], I'm a CA in Navi Mumbai working on MIS, budgeting and consolidation. "
         f"The {role} opening at {company} is close to what I do. Would you be comfortable referring me? Happy to share my CV. Thanks!"),
        ("Hiring manager ko",
         f"Hi [Name], I applied for the {role} role on your team. I'm a CA who built an AOP and Power BI variance dashboards, "
         f"and prepared financials for 12 entities ahead of a ₹2,600 Cr IPO. Happy to share more if useful. Thanks for your time!"),
    ]
    e = html.escape
    out = [f"🤝 <b>Referral: {e(company)}</b>  (har job pe 2–3 log kaafi hain)", ""]
    out += [f'{n}. <a href="{e(u)}">{e(t)}</a>' for n, (t, u) in enumerate(links, 1)]
    out += ["", "<b>Connect request ke saath bhejo</b> ([Name] badal dena):"]
    for t, m in msgs:
        out.append(f"\n<i>{e(t)}:</i>\n<code>{e(m[:300])}</code>")
    return "\n".join(out)


# ---------------------------------------------------------------- main
def safe_name(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", str(s or "Company")).strip("_")[:40] or "Company"


def process(job, state):
    a = analyse(job, state)
    DIAG.setdefault("checked", []).append(f"{a['score']} | {job.get('title')} @ {job.get('company')} ({job.get('site')})"[:120])
    state.setdefault("seen", []).extend([job["_key"], job["_jid"]])
    today = dt.datetime.now(IST).date().isoformat()
    for g in a["gaps"]:
        state.setdefault("gap_log", []).append({"date": today, "skill": g["skill"]})
    if a["score"] < CFG["min_score_to_send"] or not a.get("halal_ok", True):
        print(f"skip {a['score']} {job.get('title')} @ {job.get('company')}")
        if a["score"] >= 45 and a.get("halal_ok", True):
            state.setdefault("near_miss", []).append({
                "date": today, "score": a["score"], "title": str(a.get("role_title") or job.get("title")),
                "company": str(a.get("company") or job.get("company")), "site": str(job.get("site")),
                "url": str(job.get("job_url_direct") or job.get("job_url")), "note": str(a.get("match_note") or "")[:120]})
        return False
    OUT.mkdir(exist_ok=True)
    comp = safe_name(a.get("company") or job.get("company"))
    cv = OUT / f"Ismaeel_Syed_CV_{comp}.pdf"
    cl = OUT / f"Ismaeel_Syed_Cover_Letter_{comp}.pdf"
    build_cv(a, state, cv)
    build_letter(a, job, cl)
    send(state, job_message(a, job))
    sc = state.setdefault("sent_count", {})
    sc[today] = sc.get(today, 0) + 1
    send_file(state, cv, "CV — is JD ke hisaab se")
    send_file(state, cl, "Cover letter (zaroorat ho toh)")
    rb = referral_block(a, job)
    if rb:
        send(state, rb)
    return True


def main():
    state = load_state()
    pdf_setup()
    handle_commands(state)
    save_state(state)
    if not state.get("chat_id"):
        print("No Telegram chat yet: open your bot in Telegram and send /start")
        save_state(state)
        return
    maybe_weekly_report(state)
    maybe_daily_digest(state)
    if state.get("paused"):
        save_state(state)
        return
    sent = 0
    try:
        jobs = prefilter(fetch_jobs(), state)
        DIAG["candidates"] = len(jobs)
        # Best jobs first, whichever site they came from (quick no-AI score)
        quick = {id(j): analyse_rules(j, state)["score"] for j in jobs}
        jobs.sort(key=lambda j: -quick[id(j)])
        DIAG["by_site_queued"] = {s: sum(1 for j in jobs[: CFG["max_jobs_to_analyse_per_run"]] if j.get("site") == s) for s in CFG["sites"]}
        print(f"{len(jobs)} new candidate jobs")
        for job in jobs[: CFG["max_jobs_to_analyse_per_run"]]:
            if time.time() - START > TOTAL_BUDGET:
                DIAG["errors"].append("time budget hit; rest next run")
                break
            try:
                sent += process(job, state)
                DIAG["analysed"] = DIAG.get("analysed", 0) + 1
                save_state(state)  # save after every job so a killed run never re-sends
            except Exception as e:
                traceback.print_exc()
                DIAG["errors"].append("process: " + str(e)[:120])
            time.sleep(7)  # stay inside Gemini free-tier rate limits
    finally:
        DIAG["sent"], DIAG["ai"] = sent, ("gemini" if GEMINI_KEY else "rules")
        DIAG["errors"] = DIAG["errors"][:15]
        state["last_run"] = dt.datetime.now(IST).isoformat(timespec="minutes")
        state["diag"] = DIAG
        save_state(state)
    print(f"sent {sent}", json.dumps(DIAG))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Offline test: build sample PDFs without any network calls
        pdf_setup()
        s = {"learned": []}
        a = clean_analysis({"score": 80, "domain": sys.argv[2] if len(sys.argv) > 2 else "advisory",
                            "matched_skills": ["Financial due diligence", "SAP"], "section_order": ["fdd", "ipo", "budget"],
                            "gaps": [{"skill": "LBO modelling", "learn_time": "2 weeks"}], "why_line": "Your mid-market deals practice is the kind of work I want to do more of.",
                            "role_title": "Associate, Financial Due Diligence", "company": "Sample Advisors", "match_note": "FDD experience direct match", "relevance": {}, "rewrites": {}}, s)
        OUT.mkdir(exist_ok=True)
        build_cv(a, s, OUT / "test_cv.pdf")
        build_letter(a, {"location": "Mumbai, Maharashtra"}, OUT / "test_cl.pdf")
        print(job_message(a, {"location": "Mumbai", "site": "linkedin", "job_url": "https://example.com"}))
    else:
        main()
