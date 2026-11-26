"""Generate the sample books for a fictional coffee shop, with known problems planted in them.

Run: python scripts/make_sample_data.py   (writes sample_data/*.csv)
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(7)
OUT = Path(__file__).resolve().parent.parent / "sample_data"
START = date(2026, 8, 1)

bank, ledger = [], []
n = 0


def add(d, desc, amount, cat, in_bank=True, in_ledger=True, ledger_cat=None, ledger_shift=0):
    global n
    n += 1
    if in_bank:
        bank.append({"Date": d.isoformat(), "Description": desc, "Amount": f"{amount:.2f}", "Ref": f"{n}"})
    if in_ledger:
        ledger.append({"Date": (d + timedelta(days=ledger_shift)).isoformat(), "Memo": desc,
                       "Amount": f"{amount:.2f}", "Category": ledger_cat if ledger_cat is not None else cat,
                       "Ref": f"{n}"})


for month in range(3):
    m0 = date(2026, 8 + month, 1)
    add(m0, "ACH PAYMENT OAKWOOD PROPERTIES RENT", -3200.00, "Rent")
    add(m0 + timedelta(days=4), "COMCAST BUSINESS INTERNET", -129.99, "Utilities & Telecom")
    add(m0 + timedelta(days=9), "GUSTO PAYROLL", -6400.00 - month * 150, "Payroll")
    add(m0 + timedelta(days=23), "GUSTO PAYROLL", -6400.00 - month * 150, "Payroll")
    add(m0 + timedelta(days=11), "NEXT INSURANCE PREMIUM", -142.00, "Insurance")
    add(m0 + timedelta(days=14), "SHOPIFY SUBSCRIPTION", -39.00, "Software & Subscriptions")
    add(m0 + timedelta(days=2), "ADOBE CREATIVE CLOUD", -59.99, "Software & Subscriptions")
    if month != 1:
        add(m0 + timedelta(days=17), "PG&E ELECTRIC", -280.00 - month * 16.2, "Utilities & Telecom")
    # Weekly food supplier deliveries and roaster invoices
    for week in range(4):
        d = m0 + timedelta(days=3 + week * 7)
        add(d, "SYSCO FOODS DELIVERY", -round(random.uniform(610, 890), 2), "Cost of Goods Sold", ledger_shift=1)
        add(d + timedelta(days=2), "BLUE RIDGE ROASTERS", -round(random.uniform(420, 560), 2), "Cost of Goods Sold")
    # Daily card sales arrive as Square payouts every few days
    for day in range(0, 30, 3):
        add(m0 + timedelta(days=day), "SQUARE PAYOUT", round(random.uniform(2100, 3300), 2), "Sales")
    add(m0 + timedelta(days=20), "SQUARE MONTHLY FEE", -29.00, "Bank Fees")

# ---- Planted problems -------------------------------------------------------
# 1. Duplicate: the same Sysco delivery keyed into the ledger twice
ledger.append({**[r for r in ledger if r["Memo"] == "SYSCO FOODS DELIVERY"][5], "Ref": "dup1"})
# 2. Bank double charge from a vendor (also missing from the books)
add(date(2026, 9, 3), "ADOBE CREATIVE CLOUD", -59.99, "Software & Subscriptions", in_ledger=False)
# 3. Uncategorized entries
add(date(2026, 8, 19), "STAPLES STORE 0442", -86.47, "", ledger_cat="")
add(date(2026, 9, 12), "AMAZON WEB SERVICES", -23.10, "", ledger_cat="Ask My Accountant")
add(date(2026, 10, 8), "DOORDASH TEAM LUNCH", -64.20, "", ledger_cat="Uncategorized")
add(date(2026, 10, 15), "VENMO J MARTINEZ", -150.00, "", ledger_cat="")
# 4. Miscategorized: one roaster payment filed under Office Supplies
for r in ledger:
    if r["Memo"] == "BLUE RIDGE ROASTERS":
        r["Category"] = "Office Supplies"
        break
# 5. In bank, not in books
add(date(2026, 9, 18), "PG&E ELECTRIC", -312.40, "Utilities & Telecom", in_ledger=False)
add(date(2026, 10, 22), "STRIPE PAYOUT CATERING", 1850.00, "Sales", in_ledger=False)
# 6. In books, not in bank (check never cashed / never sent)
add(date(2026, 8, 26), "CHECK 1043 JOES PLUMBING", -450.00, "Repairs & Maintenance", in_bank=False)
# 7. Unusually large supplier payment
add(date(2026, 10, 3), "BLUE RIDGE ROASTERS", -4850.00, "Cost of Goods Sold")
# 8. Large round-number payment that is probably an owner draw
add(date(2026, 9, 30), "ONLINE TRANSFER TO CHK 7781", -5000.00, "Consulting")
# Catering invoice payments that did reach the bank
add(date(2026, 8, 20), "STRIPE PAYOUT ACME CORP", 1200.00, "Sales")
add(date(2026, 9, 25), "STRIPE PAYOUT GREENLEAF", 980.00, "Sales")

invoices = []
customers = ["Acme Corp", "Greenleaf Studio", "Harbor Dental", "Northside School", "Acme Corp",
             "Pinecrest Realty", "Greenleaf Studio", "Harbor Dental", "Lumen Labs", "Pinecrest Realty",
             "Lumen Labs", "Northside School"]
amounts = [1200, 640, 455, 2100, 980, 720, 980, 515, 1850, 890, 1340, 760]
for k in range(12):
    num = 1001 + k
    issued = date(2026, 8, 5) + timedelta(days=k * 7)
    inv = {"Invoice Number": f"INV-{num}", "Customer": customers[k], "Invoice Date": issued.isoformat(),
           "Due Date": (issued + timedelta(days=30)).isoformat(), "Amount": f"{amounts[k]:.2f}",
           "Status": "Paid", "Paid Date": (issued + timedelta(days=12)).isoformat()}
    invoices.append(inv)

by_num = {i["Invoice Number"]: i for i in invoices}
by_num["INV-1001"]["Paid Date"] = "2026-08-20"
by_num["INV-1007"]["Paid Date"] = "2026-09-25"
# Paid in the bank but still marked unpaid in the invoice list
by_num["INV-1009"].update(Status="Unpaid", **{"Paid Date": ""})
# Overdue and never paid
by_num["INV-1002"].update(Status="Unpaid", **{"Paid Date": ""})
# Missing invoice number
invoices.remove(by_num["INV-1006"])
# Duplicate invoice number
invoices.append({**by_num["INV-1010"], "Customer": "Harbor Dental", "Amount": "515.00"})

OUT.mkdir(exist_ok=True)
for name, rows in (("bank.csv", bank), ("ledger.csv", ledger), ("invoices.csv", invoices)):
    rows.sort(key=lambda r: r.get("Date") or r.get("Invoice Date"))
    with open(OUT / name, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
print(f"bank={len(bank)} ledger={len(ledger)} invoices={len(invoices)}")
