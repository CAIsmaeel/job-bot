"""Interview preparation pages, one per finance role. Run: python engine/interview_pages.py
Writes site/interview/<slug>/index.html and site/interview/index.html. The sitemap picks them up (seo.py)."""
import html, os

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
 {"slug": "record-to-report", "role": "Record to Report (R2R) and GL accountant", "area": "record-to-report", "m": "m13",
  "intro": "R2R interviews test the general ledger and month-end close: journal entries, accruals, reconciliations and a clean trial balance on time.",
  "skills": ["Journal entries and reversals", "Accruals, prepayments and provisions", "Month-end close checklist and period close", "Balance sheet reconciliations", "Bank reconciliation", "Trial balance review and intercompany basics"],
  "qa": [("What is an accrual and when is it reversed?", "An accrual records an expense in the month it belongs to when the invoice has not arrived, for example Dr Electricity, Cr Accrued expenses. It is reversed on the first day of the next month so that when the real invoice is posted the cost is not counted twice."),
         ("Walk me through a month-end close.", "Cut-off for postings, accruals and prepayment releases, depreciation, reconciliations of bank, vendors, customers and GR/IR, intercompany matching, review of the trial balance and variances, then close the period so nothing more is posted."),
         ("How do you correct a wrong journal entry?", "Reverse it with a reversal document that refers to the original, then post the correct entry. You never edit or delete a posted document because the audit trail must show both."),
         ("What is a balance sheet reconciliation?", "Proving that a ledger balance is supported by detail, such as a bank statement, a sub-ledger or a schedule. Every difference is explained and old items are cleared."),
         ("Why can't you post directly to a reconciliation account?", "Accounts like trade payables are updated only from vendor or customer postings so the sub-ledger and the general ledger always agree.")]},
 {"slug": "fpa", "role": "FP&A analyst", "area": "fpa", "m": "m4",
  "intro": "FP&A interviews mix accounting with analysis: reading the trial balance and P&L, explaining variances against budget, and building a simple forecast.",
  "skills": ["Reading a trial balance, P&L and balance sheet", "Budget versus actual variance analysis", "Rolling forecasts and driver-based planning", "Unit economics, margins and contribution", "Working capital: debtor, creditor and inventory days", "Presenting numbers in plain language"],
  "qa": [("How do you explain a cost variance?", "Split it into price and volume. For example, raw material spend is 10% over budget: 6% because we bought more to support higher sales (volume) and 4% because the price per kg rose (price). Then say what action follows."),
         ("What is the difference between budget and forecast?", "The budget is fixed at the start of the year. A forecast is updated during the year using actuals so far and the latest view of the remaining months."),
         ("How would you build a revenue forecast?", "Start from drivers: customers or volume times price, by product or region. Use history for seasonality, add known events, and keep the assumptions visible so they can be challenged."),
         ("What are debtor days and why do they matter?", "Receivables divided by sales, times the days in the period. Rising debtor days mean cash is stuck with customers even if profit looks fine."),
         ("Where do you get actuals from?", "The general ledger, usually the trial balance by cost centre or profit centre, after month-end close. Knowing how entries reach the ledger helps you spot wrong postings in the numbers.")]},
 {"slug": "tax-gst", "role": "Indirect tax and GST executive", "area": "tax", "m": "m9",
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
 {"slug": "treasury", "role": "Treasury and cash management analyst", "area": "treasury", "m": "m10",
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

CSS = """body{font-family:'Plus Jakarta Sans',system-ui,sans-serif}.w{max-width:760px}main h2{margin-top:34px}
.lead{font-size:18px;color:#374151}.qa{border-top:1px solid #E5E7EB;padding:16px 0}.qa h3{margin:0 0 6px;font-size:17px}.qa p{margin:0;color:#374151}
.box{background:#ECFDF5;border:1px solid #A7F3D0;border-radius:14px;padding:20px;margin:28px 0}.box p{margin:0 0 12px}
ul.sk li{margin:6px 0}.more a{display:inline-block;margin:0 14px 8px 0}"""


def art(role):
    return "an" if role[0] in "AEIOUaeiou" or role.startswith("FP") else "a"


def head(title, desc, path):
    return f"""<!doctype html><html lang="en-IN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="/favicon.ico" sizes="any"><link rel="icon" type="image/svg+xml" href="/mark.svg"><link rel="apple-touch-icon" href="/apple-touch-icon.png"><meta name="theme-color" content="#064E3B">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(desc)}"><link rel="canonical" href="{SITE}{path}">
<link rel="stylesheet" href="/style.css"><style>{CSS}</style></head><body>
<header><div class="w"><a class="logo" href="/"><img src="/logo.svg" alt="FinRehearse" width="150" height="30"></a><nav><a href="/interview/">Interview guides</a><a href="/jobs/">Finance jobs</a><a href="/app/">Try the free demo</a></nav></div></header>"""


FOOT = """<footer><div class="w"><a href="/terms.html">Terms</a><a href="/privacy.html">Privacy</a><a href="/contact.html">Contact</a></div></footer></body></html>"""


def build(root="site"):
    out = []
    for p in PAGES:
        path = f"/interview/{p['slug']}/"
        title = f"How to prepare for {art(p['role'])} {p['role']} interview | FinRehearse"
        e = html.escape
        qa = "".join(f'<div class="qa"><h3>{e(q)}</h3><p>{e(a)}</p></div>' for q, a in p["qa"])
        sk = "".join(f"<li>{e(s)}</li>" for s in p["skills"])
        jobs = f'<a href="/jobs/area/{p["area"]}/">See live {e(p["role"])} jobs</a>' if p["area"] else '<a href="/jobs/freshers/">See live jobs for freshers</a>'
        others = "".join(f'<a href="/interview/{o["slug"]}/">{e(o["role"])}</a>' for o in PAGES if o is not p)
        body = f"""<main class="w"><h1>How to prepare for {art(p['role'])} {e(p['role'])} interview</h1><p class="lead">{e(p['intro'])}</p>
<h2>What interviewers check</h2><ul class="sk">{sk}</ul>
<div class="box"><p><b>Practise it, don't just read it.</b> Interviewers can tell when you have only memorised answers. Post the entries yourself in a practice ERP and you can explain every step.</p>
<a class="btn" href="{APP}#practise={p['m']}">Practise a real {e(p['role'].split(' (')[0].split(' and ')[0])} task free</a></div>
<h2>Common questions, with short answers</h2>{qa}
<h2>Next steps</h2><p class="more">{jobs}<a href="{APP}">Open the free simulator</a></p>
<h2>Other interview guides</h2><p class="more">{others}</p></main>"""
        d = os.path.join(root, path.strip("/"))
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(
            head(title, f"{p['intro'][:150]}", path) + body + FOOT)
        out.append(path)
    links = "".join(f'<li><a href="/interview/{p["slug"]}/">{html.escape(p["role"])}</a></li>' for p in PAGES)
    os.makedirs(os.path.join(root, "interview"), exist_ok=True)
    open(os.path.join(root, "interview", "index.html"), "w", encoding="utf-8").write(
        head("Finance interview preparation guides | FinRehearse", "How to prepare for accounts, AP, AR, R2R, FP&A, GST, audit and treasury interviews in India, with common questions and free practice.", "/interview/")
        + f'<main class="w"><h1>Finance interview guides</h1><p class="lead">Pick your role. Each guide lists what interviewers check, common questions with short answers, and a free practice task in the simulator.</p><ul class="sk">{links}</ul></main>' + FOOT)
    return ["/interview/"] + out


if __name__ == "__main__":
    print(build())
