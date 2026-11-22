"""Interview preparation pages, one per finance role. Run: python engine/interview_pages.py
Writes site/interview/<slug>/index.html and site/interview/index.html. The sitemap picks them up (seo.py)."""
import html, os
import sitenav

SITE = "https://finrehearse.pages.dev"
APP = SITE + "/app/"

PAGES = [
 {"slug": "accounts-payable", "role": "Accounts Payable (AP) executive", "area": "accounts-payable", "m": "m7",
  "intro": "AP interviews test whether you can take a vendor invoice from receipt to payment without paying the wrong amount, paying twice or missing GST credit. Expect questions on the procure-to-pay flow, three-way match and month-end payables.",
  "skills": ["Procure to pay (P2P): purchase order, goods receipt, invoice, payment", "Three-way match between PO, GRN and invoice", "GR/IR clearing and why it carries a balance", "Input GST and TDS on vendor payments", "Vendor ageing and payment runs", "Reconciling the vendor ledger to the general ledger"],
  "qa": [("What is a three-way match?", "The invoice is checked against the purchase order (what was ordered, at what price) and the goods receipt (what actually arrived). The invoice is paid only for quantities received at the agreed price. Any difference goes on hold for the buyer or the store to resolve."),
         ("What is GR/IR and why does it have a balance?", "GR/IR is a clearing account. The goods receipt credits it and the invoice debits it. A balance means goods arrived without an invoice yet (credit) or an invoice came before the goods (debit). At month-end you review old items and accrue or chase them."),
         ("How do you stop a duplicate invoice?", "The ERP checks vendor, invoice reference, amount and date. Before posting, search the vendor ledger for the same reference. If a duplicate slips through, block it for payment and reverse it, never just delete it."),
         ("When is TDS deducted on a vendor payment?", "At the time of credit to the vendor account or payment, whichever is earlier, under the section that applies (for example 194C for contracts, 194J for professional fees). The vendor gets paid the net amount and the TDS goes to the government by the 7th of the next month."),
         ("What do you check before releasing a payment run?", "Due dates and payment terms, blocked invoices, debit notes to adjust, bank details of new vendors, and that the total ties to the approved proposal.")]},
 {"slug": "accounts-receivable", "role": "Accounts Receivable (AR) executive", "area": "accounts-receivable", "m": "m11",
  "intro": "AR interviews focus on order to cash: raising correct invoices, applying customer receipts to the right items, handling short payments and following up on overdue money.",
  "skills": ["Order to cash (O2C): sales order, delivery, billing, receipt", "Cash application and clearing open items", "Short payments, overpayments and residual items", "Credit notes and customer reconciliation", "Debtor ageing and provision for doubtful debts", "Output GST on sales"],
  "qa": [("A customer paid less than the invoice. What do you do?", "Find out why: discount, deduction, TDS or a dispute. Small agreed differences can be written off within the tolerance. Otherwise clear the invoice and leave the difference as a residual item, then follow up."),
         ("What is cash application?", "Matching each receipt to the invoices it pays so the customer account shows only what is still open. Unmatched receipts sit on account until you know which invoices they cover."),
         ("How do you read a debtor ageing report?", "It splits open receivables by how long they are overdue, such as 0 to 30, 31 to 60, 61 to 90 and over 90 days. Older buckets need follow-up first and may need a provision."),
         ("Why is TDS deducted by a customer shown as receivable?", "The customer pays you the net amount and deposits TDS for you. You claim it against your own tax, so it is an asset (TDS receivable) until it appears in your Form 26AS."),
         ("What is a credit memo?", "A document that reduces what the customer owes, for a return, a price correction or a discount. It is posted against the customer and matched with the original invoice.")]},
 {"slug": "record-to-report", "role": "Record to Report (R2R) and GL accountant", "area": "record-to-report", "m": "c2",
  "intro": "R2R interviews test the general ledger and month-end close: journal entries, accruals, reconciliations and a clean trial balance on time.",
  "skills": ["Journal entries and reversals", "Accruals, prepayments and provisions", "Month-end close checklist and period close", "Balance sheet reconciliations", "Bank reconciliation", "Trial balance review and intercompany basics"],
  "qa": [("What is an accrual and when is it reversed?", "An accrual records an expense in the month it belongs to when the invoice has not arrived, for example Dr Electricity, Cr Accrued expenses. It is reversed on the first day of the next month so that when the real invoice is posted the cost is not counted twice."),
         ("Walk me through a month-end close.", "Cut-off for postings, accruals and prepayment releases, depreciation, reconciliations of bank, vendors, customers and GR/IR, intercompany matching, review of the trial balance and variances, then close the period so nothing more is posted."),
         ("How do you correct a wrong journal entry?", "Reverse it with a reversal document that refers to the original, then post the correct entry. You never edit or delete a posted document because the audit trail must show both."),
         ("What is a balance sheet reconciliation?", "Proving that a ledger balance is supported by detail, such as a bank statement, a sub-ledger or a schedule. Every difference is explained and old items are cleared."),
         ("Why can't you post directly to a reconciliation account?", "Accounts like trade payables are updated only from vendor or customer postings so the sub-ledger and the general ledger always agree.")]},
 {"slug": "fpa", "role": "FP&A analyst", "area": "fpa", "m": "fa1",
  "intro": "FP&A interviews mix accounting with analysis: reading the trial balance and P&L, explaining variances against budget, and building a simple forecast.",
  "skills": ["Reading a trial balance, P&L and balance sheet", "Budget versus actual variance analysis", "Rolling forecasts and driver-based planning", "Unit economics, margins and contribution", "Working capital: debtor, creditor and inventory days", "Presenting numbers in plain language"],
  "qa": [("How do you explain a cost variance?", "Split it into price and volume. For example, raw material spend is 10% over budget: 6% because we bought more to support higher sales (volume) and 4% because the price per kg rose (price). Then say what action follows."),
         ("What is the difference between budget and forecast?", "The budget is fixed at the start of the year. A forecast is updated during the year using actuals so far and the latest view of the remaining months."),
         ("How would you build a revenue forecast?", "Start from drivers: customers or volume times price, by product or region. Use history for seasonality, add known events, and keep the assumptions visible so they can be challenged."),
         ("What are debtor days and why do they matter?", "Receivables divided by sales, times the days in the period. Rising debtor days mean cash is stuck with customers even if profit looks fine."),
         ("Where do you get actuals from?", "The general ledger, usually the trial balance by cost centre or profit centre, after month-end close. Knowing how entries reach the ledger helps you spot wrong postings in the numbers.")]},
 {"slug": "tax-gst", "role": "Indirect tax and GST executive", "area": "tax", "m": "g2",
  "intro": "GST interviews check that you can apply the right tax on invoices, claim input credit correctly and reconcile your books with GSTR-1, GSTR-3B and GSTR-2B.",
  "skills": ["CGST, SGST and IGST: intra-state versus inter-state", "Input tax credit and its conditions", "GSTR-1, GSTR-3B and GSTR-2B reconciliation", "Reverse charge", "Tax codes in an ERP and rate changes", "E-invoicing and e-way bills"],
  "qa": [("When do you charge IGST instead of CGST and SGST?", "When the place of supply is in a different state from the supplier's location (inter-state). Within the same state you charge CGST and SGST in equal halves."),
         ("What are the conditions to claim input tax credit?", "You hold a valid tax invoice, you have received the goods or services, the supplier has reported it so it appears in your GSTR-2B, and the supplier has paid the tax. Credit is blocked for some items under section 17(5)."),
         ("How do you reconcile GSTR-2B with your books?", "Match each supplier invoice by GSTIN, invoice number and amount. Follow up with suppliers whose invoices are missing in 2B and do not claim credit for them until they appear."),
         ("What is reverse charge?", "For notified goods and services, or some purchases from unregistered suppliers, the buyer pays the GST to the government instead of the supplier, and can usually claim it back as input credit."),
         ("How is a GST rate change handled in an ERP?", "A new tax code or a validity date is set up so invoices dated before the change use the old rate and those after use the new one.")]},
 {"slug": "audit", "role": "Audit and assurance associate", "area": "audit", "m": "p1a",
  "intro": "Audit interviews ask how you test whether the numbers are right: controls, vouching, sampling and the common ways accounts go wrong.",
  "skills": ["Internal controls and segregation of duties", "Vouching and verification", "Sampling and testing of controls", "Cut-off testing", "Duplicate payments and unusual journal entries", "SOX and internal financial controls basics"],
  "qa": [("How would you test for duplicate vendor payments?", "Pull the vendor ledger and sort by vendor, invoice reference and amount. Look for the same reference or the same amount on close dates. Check whether the ERP's duplicate check was switched off."),
         ("What is cut-off testing?", "Checking that transactions near the year-end are recorded in the right period, for example goods received on 31 March are in March purchases and sales invoiced in April are not in March revenue."),
         ("What is segregation of duties?", "No one person should both create a vendor and approve its payment, or post an entry and approve it. Splitting these steps prevents fraud and errors going unnoticed."),
         ("What do you look for in journal entries?", "Entries posted at odd times, by unusual users, to rarely used accounts, round amounts, and manual entries to revenue or cash near period end."),
         ("Vouching versus verification?", "Vouching goes from the books to the documents to prove an entry is real. Verification checks that an asset exists, is owned and is valued correctly.")]},
 {"slug": "treasury", "role": "Treasury and cash management analyst", "area": "treasury", "m": "p3a",
  "intro": "Treasury interviews cover cash visibility and payments: daily cash position, bank reconciliation, payment runs and managing short-term funds.",
  "skills": ["Daily cash position and cash forecasting", "Bank reconciliation", "Vendor payment runs and approvals", "Working capital and short-term funding", "Fixed deposits and interest accruals", "Foreign exchange basics"],
  "qa": [("What goes into a daily cash position?", "Opening bank balances, expected receipts and payments for the day, payroll and tax outflows, and any maturing deposits. The result shows whether to invest surplus or arrange funding."),
         ("Why does the bank balance differ from the book balance?", "Timing: cheques issued but not presented, deposits not yet credited, and bank charges or interest the bank has posted but you have not. A bank reconciliation explains each difference."),
         ("How do you control a payment run?", "Only approved and due invoices are proposed, bank details changes are verified, the proposal is reviewed by someone other than the preparer, and the file sent to the bank ties to the approved total."),
         ("How do you account for interest on a fixed deposit?", "Accrue interest for each month it is earned (Dr Interest receivable, Cr Interest income), even if the bank pays it only at maturity."),
         ("What is a cash flow forecast used for?", "To see shortfalls weeks ahead so the company can delay payments, collect faster or arrange a loan before it runs out of cash.")]},
 {"slug": "freshers", "role": "accounts fresher (B.Com, M.Com)", "area": None, "m": "m1",
  "intro": "First interviews for accounts roles check basics: debit and credit, GST, a simple journal entry, and whether you understand how an ERP records everyday work. You do not need experience, but you need to show you can learn the system quickly.",
  "skills": ["Golden rules of debit and credit", "Journal entries for purchase, sale, payment and receipt", "Basics of GST and TDS", "What a ledger, trial balance and balance sheet show", "How an ERP handles vendors, customers and the general ledger", "Excel basics: VLOOKUP, pivot tables"],
  "qa": [("You buy goods on credit for Rs. 10,000 plus 18% GST. What is the entry?", "Dr Purchases 10,000, Dr Input GST 1,800, Cr Vendor 11,800. The vendor is a liability because you owe the money."),
         ("What is the difference between a ledger and a trial balance?", "A ledger shows all postings to one account. The trial balance lists the closing balance of every account; total debits must equal total credits."),
         ("What is an ERP?", "One system where purchasing, sales, inventory and accounts share the same data. When stores post a goods receipt, accounts sees the liability at once without re-entering it."),
         ("What is depreciation?", "Spreading the cost of a fixed asset over its useful life, because the asset helps earn income for several years."),
         ("Why should we hire a fresher like you?", "Say what you have practised: for example, that you have posted invoices, payments and a month-end close in a practice ERP and can explain each entry. Concrete practice beats general claims.")]},
]


import json

QB = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "qb_public.json"), encoding="utf-8"))
BY = {p["slug"]: p for p in PAGES}
E = html.escape
LVL = {"F": "Fresher", "X": "Experienced"}

# left index: (anchor, label, guide slug or None)
INDEX = [("basics", "Basics", "freshers"), ("ap", "Accounts payable", "accounts-payable"), ("ar", "Accounts receivable", "accounts-receivable"),
         ("r2r", "Record to report", "record-to-report"), ("gst", "GST and tax", "tax-gst"), ("fpa", "FP&A", "fpa"),
         ("audit", "Audit", "audit"), ("treasury", "Treasury", "treasury")]


def art(role):
    return "an" if role[0] in "AEIOUaeiou" or role.startswith("FP") else "a"


def card(q, a, pill=""):
    pl = '<span class="lv mono">%s</span>' % pill if pill else ""
    return (f'<details class="qa" data-s="{E((q + " " + a).lower())}"><summary><span class="qq">{E(q)}</span>'
            f'{pl}<span class="tg" aria-hidden="true"></span></summary>'
            f'<div class="ans"><p>{E(a)}</p><div class="rc"><button type="button" class="k" data-k="1">I knew it</button>'
            f'<button type="button" class="k" data-k="0">Review again</button></div></div></details>')


def head(title, desc, path):
    return f"""<!doctype html><html lang="en-IN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="/favicon.ico" sizes="any"><link rel="icon" type="image/svg+xml" href="/mark.svg"><link rel="apple-touch-icon" href="/apple-touch-icon.png"><meta name="theme-color" content="#FAFAFA">
<title>{E(title)}</title><meta name="description" content="{E(desc)}"><link rel="canonical" href="{SITE}{path}">
<link rel="stylesheet" href="/style.css">{sitenav.head()}<link rel="stylesheet" href="/docs.css"></head><body class="docs">{sitenav.html("guides")}"""


def sidebar(cur=""):
    hub = "" if cur else ' aria-current="page"'
    items = "".join(f'<li><a href="/interview/#{a}" data-a="{a}">{E(l)}</a></li>' for a, l, _ in INDEX)
    ac = ' aria-current="page"'
    guides = "".join('<li><a href="/interview/%s/"%s>%s</a></li>' % (p["slug"], ac if p["slug"] == cur else "", E(p["role"])) for p in PAGES)
    return f"""<aside class="dside"><div class="dsticky">
<div class="dsearch"><input id="q" type="search" placeholder="Search questions" aria-label="Search questions" autocomplete="off"><kbd class="mono">/</kbd></div>
<p class="dh mono">Topics</p><ul class="dnav"><li><a href="/interview/"{hub}>All questions</a></li>{items}<li><a href="/interview/#more">More in the full version</a></li><li><a href="/interview/#sheet">Revision sheet</a></li></ul>
<p class="dh mono">Role guides</p><ul class="dnav sm">{guides}</ul></div></aside>"""


TOOLBAR = """<div class="dbar"><label class="sw"><input type="checkbox" id="recall"><span class="tr"><i></i></span><span>Active recall mode</span></label>
<span class="dcount mono" id="dcount"></span><span class="dsp"></span>
<button type="button" class="btn alt sm" id="expand">Expand all</button><button type="button" class="btn sm" id="printsheet">One-Page Revision Sheet</button></div>"""

SCRIPT = r"""<script>
(function(){
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const q=$('#q'),cnt=$('#dcount'),cards=$$('.qa');let known=0,seen=0;
function count(){const v=cards.filter(c=>!c.hidden).length;if(cnt)cnt.textContent=v+' questions'+(seen?' · knew '+known+' of '+seen:'')}
function filter(){const t=(q&&q.value||'').trim().toLowerCase();cards.forEach(c=>c.hidden=!!t&&!c.dataset.s.includes(t));
  $$('.dsec').forEach(s=>{const has=s.querySelector('.qa:not([hidden])');s.hidden=!!t&&!has});count()}
if(q){q.addEventListener('input',filter);document.addEventListener('keydown',e=>{if(e.key==='/'&&document.activeElement!==q){e.preventDefault();q.focus()}})}
const rc=$('#recall');if(rc)rc.addEventListener('change',()=>{document.body.classList.toggle('recall',rc.checked);cards.forEach(c=>c.open=false);known=0;seen=0;count()});
const ex=$('#expand');if(ex)ex.addEventListener('click',()=>{const open=ex.dataset.o!=='1';cards.forEach(c=>{if(!c.hidden)c.open=open});ex.dataset.o=open?'1':'0';ex.textContent=open?'Collapse all':'Expand all'});
document.addEventListener('click',e=>{const b=e.target.closest('.k');if(!b)return;const d=b.closest('.qa');if(d.dataset.m)return;d.dataset.m=b.dataset.k;seen++;if(b.dataset.k==='1')known++;d.classList.add(b.dataset.k==='1'?'ok':'again');d.open=false;count()});
const pr=$('#printsheet');if(pr)pr.addEventListener('click',()=>{document.body.classList.add('sheet');setTimeout(()=>{window.print();},50)});
window.addEventListener('afterprint',()=>document.body.classList.remove('sheet'));
const links=$$('.dnav a[data-a]');if('IntersectionObserver' in window&&links.length){const io=new IntersectionObserver(es=>{es.forEach(en=>{if(en.isIntersecting){links.forEach(l=>l.classList.toggle('on',l.dataset.a===en.target.id))}})},{rootMargin:'-80px 0px -70% 0px'});$$('.dsec[id]').forEach(s=>io.observe(s))}
count();
})();
</script>"""


def section(aid, title, intro, cards_html, guide=None, extra=""):
    g = BY.get(guide) if guide else None
    gl = f'<a class="glink" href="/interview/{g["slug"]}/">Full {E(g["role"])} guide</a>' if g else ""
    pr = f'<a class="btn alt sm" href="{APP}#practise={g["m"]}">Practise a real task</a>' if g else ""
    return (f'<section class="dsec" id="{aid}"><div class="dsh"><h2>{E(title)}</h2><div class="dsa">{gl}{pr}</div></div>'
            + ('<p class="dlead">%s</p>' % E(intro) if intro else "") + f'<div class="qas">{cards_html}</div>{extra}</section>')


def build(root="site"):
    out = []
    qb = {}
    for x in QB["free"]:
        qb.setdefault(x["a"], []).append(x)
    cards = lambda a: "".join(card(x["q"], x["ans"], LVL.get(x["l"], "")) for x in qb.get(a, []))
    gcards = lambda slug: "".join(card(q, a, "Guide") for q, a in BY[slug]["qa"])
    locked = {x["a"]: x for x in QB["locked"]}
    tease = lambda k: (f'<div class="lock"><span class="pill mono">+{locked[k]["count"]} more</span><p>{E(locked[k]["n"])} questions with model answers are in the full version, for example: '
                       f'{E("; ".join(locked[k]["sample"][:3]))}.</p><a class="btn sm" href="/#price">See pricing</a></div>') if k in locked else ""
    secs = [section("basics", "Basics", "Asked in almost every first interview for an accounts role.", cards("BAS") + gcards("freshers"), "freshers"),
            section("ap", "Accounts payable", BY["accounts-payable"]["intro"], cards("AP") + gcards("accounts-payable"), "accounts-payable", tease("P2P")),
            section("ar", "Accounts receivable", BY["accounts-receivable"]["intro"], cards("AR") + gcards("accounts-receivable"), "accounts-receivable", tease("O2C")),
            section("r2r", "Record to report", BY["record-to-report"]["intro"], gcards("record-to-report"), "record-to-report", tease("GL")),
            section("gst", "GST and tax", BY["tax-gst"]["intro"], gcards("tax-gst"), "tax-gst", tease("TAX")),
            section("fpa", "FP&A", BY["fpa"]["intro"], gcards("fpa"), "fpa"),
            section("audit", "Audit", BY["audit"]["intro"], gcards("audit"), "audit"),
            section("treasury", "Treasury", BY["treasury"]["intro"], gcards("treasury"), "treasury", tease("BANK"))]
    more = "".join(f'<li><span>{E(x["n"])}</span><span class="mono">{x["count"]}</span></li>' for x in QB["locked"])
    more_sec = (f'<section class="dsec" id="more"><div class="dsh"><h2>More in the full version</h2></div><p class="dlead">The simulator has 165 questions with model answers, '
                f'a recall drill that tracks what you know, and the full revision sheet.</p><ul class="morel">{more}</ul>'
                f'<p><a class="btn" href="/#price">See pricing</a> <a class="btn alt" href="{APP}">Try the free demo</a></p></section>')
    tc = "".join(f"<tr><td>{E(a)}</td><td class=\"mono\">{E(b)}</td></tr>" for a, b in QB["tc"])
    je = "".join(f"<tr><td>{E(r[0])}</td><td class=\"mono\">{E(r[1])}</td><td class=\"mono\">{E(r[2])}</td></tr>" for r in QB["je"])
    sheet = (f'<section class="dsec" id="sheet"><div class="dsh"><h2>One-page revision sheet</h2></div><p class="dlead">The night before the interview: read it once and say the answers out loud. '
             f'Press <b>One-Page Revision Sheet</b> above to print it or save it as a PDF.</p>'
             f'<h3>T-codes by area</h3><div class="tw"><table><thead><tr><th>Area</th><th>T-codes</th></tr></thead><tbody>{tc}</tbody></table></div>'
             f'<h3>Key accounting entries</h3><div class="tw"><table><thead><tr><th>Event</th><th>Debit</th><th>Credit</th></tr></thead><tbody>{je}</tbody></table></div></section>')
    pq = [x for x in QB["free"] if x["t"]][:12]
    printq = "".join(f'<div class="pq"><b>{i}. {E(x["q"])}</b> {E(x["ans"])}</div>' for i, x in enumerate(pq, 1))
    printsheet = f'<div class="printonly"><h1>FinRehearse revision sheet</h1><h3>Top questions</h3><div class="pqs">{printq}</div></div>'
    hub = (head("Finance interview questions with answers: AP, AR, R2R, GST, FP&A | FinRehearse",
                "Free finance interview questions with model answers for accounts, AP, AR, R2R, GST, FP&A, audit and treasury roles in India, with an active recall mode and a one-page revision sheet.", "/interview/")
           + '<div class="dwrap">' + sidebar() + '<main class="dmain"><div class="dhead"><p class="crumb mono">Interview guides</p>'
           + '<h1>Finance interview questions, with model answers</h1><p class="dlead">Read a question, say your answer out loud, then open the model answer. '
           + 'Turn on active recall to hide every answer and mark what you knew.</p>' + TOOLBAR + '</div>'
           + "".join(secs) + more_sec + sheet + printsheet + '</main></div>' + sitenav.footer() + SCRIPT + "</body></html>")
    d = os.path.join(root, "interview"); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(hub)
    out.append("/interview/")
    for p in PAGES:
        path = f"/interview/{p['slug']}/"
        sk = "".join(f"<li>{E(x)}</li>" for x in p["skills"])
        jobs = f'<a href="/jobs/area/{p["area"]}/">See live {E(p["role"])} jobs</a>' if p["area"] else '<a href="/jobs/freshers/">See live jobs for freshers</a>'
        body = (f'<div class="dwrap">{sidebar(p["slug"])}<main class="dmain"><div class="dhead"><p class="crumb mono"><a href="/interview/">Interview guides</a> / {E(p["role"])}</p>'
                f'<h1>How to prepare for {art(p["role"])} {E(p["role"])} interview</h1><p class="dlead">{E(p["intro"])}</p>{TOOLBAR}</div>'
                f'<section class="dsec"><h2>What interviewers check</h2><ul class="skl">{sk}</ul></section>'
                f'<div class="callout"><p><b>Practise it, don\'t just read it.</b> Interviewers can tell when you have only memorised answers. Post the entries yourself in a practice ERP and you can explain every step.</p>'
                f'<a class="btn" href="{APP}#practise={p["m"]}">Practise a real {E(p["role"].split(" (")[0].split(" and ")[0])} task free</a></div>'
                f'<section class="dsec"><h2>Common questions, with short answers</h2><div class="qas">{"".join(card(q, a) for q, a in p["qa"])}</div></section>'
                f'<section class="dsec"><h2>Next steps</h2><p class="more">{jobs} · <a href="{APP}">Open the free simulator</a> · <a href="/interview/">All interview questions</a></p></section>'
                f'</main></div>')
        d = os.path.join(root, path.strip("/")); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(
            head(f"How to prepare for {art(p['role'])} {p['role']} interview | FinRehearse", p["intro"][:150], path) + body + sitenav.footer() + SCRIPT + "</body></html>")
        out.append(path)
    return out


if __name__ == "__main__":
    print(build())
