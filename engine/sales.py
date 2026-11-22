"""FinRehearse sales: find new Razorpay payments, issue a licence key, email it, tell the owner.

Runs on GitHub Actions every 15 minutes (.github/workflows/sales.yml).
Each payment is handled once: after the key is emailed, the key id is written into the
payment's notes on Razorpay (fr_key). The repo is public, so this script never prints
names, emails or keys to the log.

Secrets: RZP_KEY_ID, RZP_KEY_SECRET, GMAIL_APP_PASSWORD, LICENCE_PRIVATE_JWK, TELEGRAM_TOKEN
"""
import base64, json, os, random, smtplib, string, sys, time
from datetime import date
from email.message import EmailMessage
import requests
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

GMAIL = "finrehearse.help@gmail.com"
APP_URL = "https://finrehearse.pages.dev/app/"
PLANS = {49900: 3, 99900: 12}          # amount in paise -> months
API = "https://api.razorpay.com/v1"


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def b64u_dec(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def add_months(d, m):
    y, mo = divmod(d.month - 1 + m, 12)
    y += d.year
    mo += 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, mo, day)
        except ValueError:
            pass


def make_key(jwk, name, months, today=None):
    """Same format as tools/keygen.js: LL1.<payload>.<P1363 ECDSA P-256 signature>."""
    priv = ec.derive_private_key(int.from_bytes(b64u_dec(jwk["d"]), "big"), ec.SECP256R1())
    today = today or date.today()
    kid = "FR-" + today.strftime("%Y%m%d") + "-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    payload = {"id": kid, "name": name, "plan": "individual", "iat": today.isoformat(),
               "exp": add_months(today, months).isoformat()}
    body = "LL1." + b64u(json.dumps(payload, separators=(",", ":")).encode())
    r, s = decode_dss_signature(priv.sign(body.encode(), ec.ECDSA(hashes.SHA256())))
    return body + "." + b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big")), payload


def buyer_name(p):
    notes = p.get("notes") or {}
    if isinstance(notes, dict):
        for k, v in notes.items():
            if "name" in k.lower() and str(v).strip():
                return str(v).strip()[:60]
    return (p.get("email") or "FinRehearse learner").split("@")[0][:60]


def email_text(name, key, payload, months):
    return f"""Hi {name},

Thank you for buying FinRehearse ({months} months). Here is your licence key:

{key}

How to use it:
1. Open {APP_URL}
2. Type LICENCE in the command field and press Enter (or open Menu, then Licence).
3. Paste the whole key, starting with LL1, and press Activate.

Your key works until {payload['exp']}. Key id: {payload['id']} (quote it if you write to us).
Practice data stays in your browser, so use the same browser each time, or export your data.

Not happy? Reply within 7 days of payment for a full refund.

FinRehearse
{GMAIL}
"""


def send_email(to, subject, text):
    m = EmailMessage()
    m["From"] = f"FinRehearse <{GMAIL}>"
    m["To"] = to
    m["Subject"] = subject
    m["Reply-To"] = GMAIL
    m.set_content(text)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(GMAIL, os.environ["GMAIL_APP_PASSWORD"].replace(" ", ""))
        s.send_message(m)


def tell_owner(text):
    """Sales alerts go to the separate FinRehearse sales bot only (SALES_BOT_TOKEN + SALES_CHAT_ID)."""
    tok, chat = os.environ.get("SALES_BOT_TOKEN"), os.environ.get("SALES_CHAT_ID")
    if tok and chat:
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      data={"chat_id": chat, "text": text, "disable_web_page_preview": "true"}, timeout=30)


def sales_bot_setup():
    """Reply to whoever messaged the sales bot with their chat id (sent in Telegram, never logged)."""
    tok = os.environ.get("SALES_BOT_TOKEN")
    if not tok or os.environ.get("SALES_CHAT_ID"):
        return
    ups = requests.get(f"https://api.telegram.org/bot{tok}/getUpdates", timeout=30).json().get("result", [])
    chats = {(u.get("message") or {}).get("chat", {}).get("id") for u in ups
             if (u.get("message") or {}).get("chat", {}).get("type") == "private"} - {None}
    for c in chats:
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", data={"chat_id": c,
            "text": f"Your chat id is {c}\n\nSave it in GitHub as a secret named SALES_CHAT_ID. After that, every FinRehearse sale will be reported here."}, timeout=30)
    print("sales bot setup: replied to", len(chats), "chat(s)")


def main():
    sales_bot_setup()
    auth = (os.environ["RZP_KEY_ID"], os.environ["RZP_KEY_SECRET"])
    jwk = json.loads(os.environ["LICENCE_PRIVATE_JWK"])
    since = int(time.time()) - 7 * 86400
    r = requests.get(f"{API}/payments", auth=auth, params={"from": since, "count": 100}, timeout=30)
    r.raise_for_status()
    pays = r.json().get("items", [])
    todo = [p for p in pays if p.get("status") == "captured" and p.get("amount") in PLANS
            and not (isinstance(p.get("notes"), dict) and p["notes"].get("fr_key"))]
    print(f"payments in last 7 days: {len(pays)}, new paid ones to handle: {len(todo)}")
    done = 0
    for p in todo:
        months = PLANS[p["amount"]]
        name, to = buyer_name(p), p.get("email")
        if not to:
            tell_owner(f"⚠️ FinRehearse: payment {p['id']} (Rs {p['amount']//100}) has no email. Issue the key by hand.")
            continue
        key, payload = make_key(jwk, name, months)
        try:
            send_email(to, f"Your FinRehearse licence key ({months} months)", email_text(name, key, payload, months))
        except Exception as e:
            print("email failed:", type(e).__name__)
            tell_owner(f"⚠️ FinRehearse: could not email the key for payment {p['id']}. Check the Gmail app password.")
            continue
        notes = dict(p["notes"]) if isinstance(p.get("notes"), dict) else {}
        notes["fr_key"] = payload["id"]
        u = requests.patch(f"{API}/payments/{p['id']}", auth=auth, json={"notes": notes}, timeout=30)
        if not u.ok:
            print("could not mark payment as done:", u.status_code)
        done += 1
        tell_owner(f"💰 New FinRehearse sale: Rs {p['amount']//100} ({months} months)\n"
                   f"Buyer: {name} <{to}>\nPayment: {p['id']}\nKey id: {payload['id']} (emailed)\n\n"
                   f"Key, in case they ask again:\n{key}"
                   + ("" if u.ok else "\n\n⚠️ Could not mark the payment as done on Razorpay, so the next run may email the key again."))
    print(f"keys emailed: {done}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        k, pl = make_key(json.loads(os.environ["LICENCE_PRIVATE_JWK"]), "Test Buyer", 12)
        send_email(GMAIL, "TEST: your FinRehearse licence key (12 months)", email_text("Test Buyer", k, pl, 12))
        tell_owner("✅ FinRehearse sales system test: a sample key email was sent to " + GMAIL + ". Razorpay, Gmail and key signing all work.")
        print("selftest ok")
    elif len(sys.argv) > 2 and sys.argv[1] == "--test-key":
        k, _ = make_key(json.load(open(sys.argv[2])), "Test Buyer", 12)
        print(k)
    else:
        main()
