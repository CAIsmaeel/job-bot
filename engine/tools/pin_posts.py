"""One-off: post and pin the two guide messages on the channel (jobs site, simulator)."""
import os, json, requests
tok, chat = os.environ["TG_CHANNEL_TOKEN"], os.environ["TG_CHANNEL_ID"]
API = f"https://api.telegram.org/bot{tok}"
def send(text, btn):
    r = requests.post(f"{API}/sendMessage", data={"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true",
        "reply_markup": json.dumps({"inline_keyboard": [[{"text": btn[0], "url": btn[1]}]]})}, timeout=30).json()
    print("send", r.get("ok"), r.get("description")); return r["result"]["message_id"]
def pin(mid):
    r = requests.post(f"{API}/pinChatMessage", data={"chat_id": chat, "message_id": mid, "disable_notification": "true"}, timeout=30).json()
    print("pin", mid, r.get("ok"), r.get("description"))
sim = send("""<b>🎯 Interview coming up? Practise first.</b>

FinRehearse is a hands-on ERP finance simulator. Post real entries, make real mistakes and see exactly what went wrong.

• Vendor invoices, payments, GR/IR, three-way match
• Bank reconciliation and month-end close
• Interview missions, a level check and a daily close quiz

Runs in your browser. Nothing to install. Free demo, no sign-up.""", ("Try the free demo", "https://finrehearse.pages.dev/app/"))
pin(sim)
jobs = send("""<b>📌 All finance jobs in one place</b>

1,100+ live finance jobs in India, taken straight from company career sites and updated every 2 hours.

Filter by:
• City: Mumbai, Bengaluru, Pune, Hyderabad, Gurugram and more
• Area: AP/AR, R2R, FP&A, audit, tax, treasury, controllership
• Company: banks, Big 4, GCCs, NBFCs, corporates
• Freshers: trainee, graduate and junior roles

Every job links to the company's own site. Apply there directly.""", ("Browse and filter jobs", "https://finrehearse.pages.dev/jobs/"))
pin(jobs)
