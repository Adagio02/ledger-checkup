"""Generate extra sample books for three more fictional small businesses, each with its own planted problems.

All businesses, people, customers and invoice numbers are made up. Vendor names (Home Depot,
USPS, Shopify...) are only there so the descriptions look like a real bank export.

Run: python scripts/make_more_sample_data.py   (writes sample_data/more/<business>/*.csv)

The planted problems for each business are listed in sample_data/more/README.md and checked by
tests/test_more_samples.py.
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "sample_data" / "more"


class Books:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.bank, self.ledger, self.invoices = [], [], []
        self.n = 0

    def add(self, d, desc, amount, cat, in_bank=True, in_ledger=True, ledger_cat=None, ledger_shift=0):
        self.n += 1
        if in_bank:
            self.bank.append({"Date": d.isoformat(), "Description": desc, "Amount": f"{amount:.2f}",
                              "Ref": f"{self.n}"})
        if in_ledger:
            self.ledger.append({"Date": (d + timedelta(days=ledger_shift)).isoformat(), "Memo": desc,
                                "Amount": f"{amount:.2f}",
                                "Category": ledger_cat if ledger_cat is not None else cat, "Ref": f"{self.n}"})

    def money(self, lo, hi):
        return round(self.rng.uniform(lo, hi), 2)

    def invoice(self, number, customer, issued, amount, paid_after=None, terms=30):
        self.invoices.append({
            "Invoice Number": number, "Customer": customer, "Invoice Date": issued.isoformat(),
            "Due Date": (issued + timedelta(days=terms)).isoformat(), "Amount": f"{amount:.2f}",
            "Status": "Paid" if paid_after is not None else "Unpaid",
            "Paid Date": (issued + timedelta(days=paid_after)).isoformat() if paid_after is not None else "",
        })

    def write(self, slug):
        folder = OUT / slug
        folder.mkdir(parents=True, exist_ok=True)
        for name, rows in (("bank.csv", self.bank), ("ledger.csv", self.ledger), ("invoices.csv", self.invoices)):
            if not rows:
                continue
            rows.sort(key=lambda r: r.get("Date") or r.get("Invoice Date"))
            with open(folder / name, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
        print(f"{slug}: bank={len(self.bank)} ledger={len(self.ledger)} invoices={len(self.invoices)}")


# =========================================================================== 1. contractor
def summit_ridge_renovations():
    """A two-truck home renovation contractor. Big-ticket problems: duplicate subcontractor
    payment, an unrecorded client deposit, a never-cashed check, overdue invoices."""
    b = Books(seed=11)
    for month in range(3):
        m0 = date(2026, 7 + month, 1)
        b.add(m0 + timedelta(days=1), "ACH PAYMENT FORD CREDIT TRUCK LOAN", -689.42, "Loan Payments")
        b.add(m0 + timedelta(days=5), "HISCOX GENERAL LIABILITY", -211.00, "Insurance")
        b.add(m0 + timedelta(days=7), "VERIZON WIRELESS", -164.38, "Utilities & Telecom")
        b.add(m0 + timedelta(days=12), "QUICKBOOKS ONLINE", -55.00, "Software & Subscriptions")
        b.add(m0 + timedelta(days=14), "ADP PAYROLL", -5280.00 - month * 120, "Payroll")
        b.add(m0 + timedelta(days=28), "ADP PAYROLL", -5280.00 - month * 120, "Payroll")
        b.add(m0 + timedelta(days=20), "STORAGE YARD LEASE PINE ST", -850.00, "Rent")
        for week in range(4):
            d = m0 + timedelta(days=2 + week * 7)
            b.add(d, "THE HOME DEPOT 4417", -b.money(180, 640), "Materials & Supplies", ledger_shift=1)
            b.add(d + timedelta(days=2), "MILLER LUMBER YARD", -b.money(700, 1150), "Materials & Supplies")
            b.add(d + timedelta(days=3), "SHELL OIL 57442", -b.money(78, 132), "Vehicle & Fuel")
        # Subcontractors paid by ACH twice a month
        b.add(m0 + timedelta(days=9), "ACH CASTILLO ELECTRIC LLC", -b.money(1800, 2600), "Subcontractors")
        b.add(m0 + timedelta(days=22), "ACH RIVERBEND PLUMBING", -b.money(1400, 2200), "Subcontractors")
        b.add(m0 + timedelta(days=16), "ACH VALLEYVIEW DRYWALL", -b.money(1500, 2100), "Subcontractors")
        b.add(m0 + timedelta(days=25), "CHASE MONTHLY SERVICE FEE", -15.00, "Bank Fees")

    # Client payments (progress payments on jobs) reach the bank as mobile check deposits
    invoices = [
        ("SRR-2026-101", "Okafor Residence", date(2026, 7, 3), 8400.00, 15),
        ("SRR-2026-102", "Delgado Kitchen Remodel", date(2026, 7, 10), 6250.00, 21),
        ("SRR-2026-103", "Brookstone HOA", date(2026, 7, 17), 3900.00, 18),
        ("SRR-2026-104", "Okafor Residence", date(2026, 7, 28), 7150.00, 14),
        ("SRR-2026-105", "Patel Basement Finish", date(2026, 8, 4), 5600.00, None),    # overdue
        ("SRR-2026-106", "Lindqvist Deck", date(2026, 8, 11), 4320.00, 20),
        ("SRR-2026-107", "Delgado Kitchen Remodel", date(2026, 8, 20), 9800.00, None),  # paid, not marked
        ("SRR-2026-108", "Brookstone HOA", date(2026, 8, 27), 2750.00, 16),
        ("SRR-2026-110", "Nguyen Bathroom", date(2026, 9, 8), 6900.00, 12),            # 109 is missing
        ("SRR-2026-111", "Lindqvist Deck", date(2026, 9, 15), 3180.00, None),           # not due yet
        ("SRR-2026-112", "Okafor Residence", date(2026, 9, 22), 5475.00, None),         # not due yet
    ]
    for num, cust, issued, amt, paid_after in invoices:
        b.invoice(num, cust, issued, amt, paid_after, terms=15)
        if paid_after is not None:
            b.add(issued + timedelta(days=paid_after), f"MOBILE DEPOSIT {cust.split()[0].upper()}", amt, "Sales")
    # ---- Planted problems --------------------------------------------------
    # 1. Duplicate in the ledger: an electrician payment keyed twice (critical, over $1,000)
    elec = [r for r in b.ledger if r["Memo"] == "ACH CASTILLO ELECTRIC LLC"][1]
    b.ledger.append({**elec, "Ref": "dup1"})
    # 2. Bank double charge at Home Depot (not in the books)
    hd = [r for r in b.bank if r["Description"] == "THE HOME DEPOT 4417"][6]
    b.add(date.fromisoformat(hd["Date"]), "THE HOME DEPOT 4417", float(hd["Amount"]), "Materials & Supplies",
          in_ledger=False)
    # 3. Paid invoice SRR-2026-107 deposited but still marked unpaid, and never recorded in the books
    b.add(date(2026, 9, 2), "MOBILE DEPOSIT DELGADO", 9800.00, "Sales", in_ledger=False)
    # 4. Check to a subcontractor written in the books but never cashed
    b.add(date(2026, 8, 18), "CHECK 2211 HARGROVE ROOFING", -1650.00, "Subcontractors", in_bank=False)
    # 5. Uncategorized purchases
    b.add(date(2026, 7, 24), "SUNBELT RENTALS EXCAVATOR", -486.00, "", ledger_cat="")
    b.add(date(2026, 8, 30), "ZELLE TO M REYES", -300.00, "", ledger_cat="Ask My Accountant")
    b.add(date(2026, 9, 19), "CHEVRON 0092", -96.15, "", ledger_cat="Uncategorized")
    # 6. Miscategorized: a lumber yard purchase filed under Meals
    for r in b.ledger:
        if r["Memo"] == "MILLER LUMBER YARD" and r["Date"].startswith("2026-08"):
            r["Category"] = "Meals"
            break
    # 7. Unusually large Home Depot run
    b.add(date(2026, 9, 10), "THE HOME DEPOT 4417", -3975.60, "Materials & Supplies")
    # 8. Owner draw booked as an expense
    b.add(date(2026, 8, 31), "ONLINE TRANSFER TO SAV 3390", -4000.00, "Materials & Supplies")
    b.write("summit-ridge-renovations")


# =========================================================================== 2. online shop
def maple_and_thread():
    """A one-person online shop selling handmade candles and textiles, plus some wholesale to
    boutiques. Lots of small transactions, ad spend, and sloppy invoice numbering."""
    b = Books(seed=23)
    for month in range(3):
        m0 = date(2026, 9 + month, 1)
        b.add(m0, "SHOPIFY BASIC PLAN", -39.00, "Software & Subscriptions")
        b.add(m0 + timedelta(days=3), "MAILCHIMP MONTHLY", -26.50, "Advertising & Marketing")
        b.add(m0 + timedelta(days=6), "CANVA PRO", -14.99, "Software & Subscriptions")
        b.add(m0 + timedelta(days=10), "GOOGLE WORKSPACE", -14.40, "Software & Subscriptions")
        b.add(m0 + timedelta(days=12), "STUDIO SHARE RENT WESTGATE MAKERS", -475.00, "Rent")
        for week in range(4):
            d = m0 + timedelta(days=1 + week * 7)
            b.add(d, "SHOPIFY PAYOUT", b.money(880, 1640), "Sales")
            b.add(d + timedelta(days=2), "ETSY DEPOSIT", b.money(310, 690), "Sales")
            b.add(d + timedelta(days=1), "USPS CLICK N SHIP", -b.money(95, 175), "Shipping & Postage",
                  ledger_shift=1)
            b.add(d + timedelta(days=4), "META ADS", -b.money(60, 120), "Advertising & Marketing")
        b.add(m0 + timedelta(days=8), "ULINE SHIPPING SUPPLIES", -b.money(140, 260), "Packaging")
        b.add(m0 + timedelta(days=15), "CANDLESCIENCE WAX & WICKS", -b.money(520, 780), "Cost of Goods Sold")
        b.add(m0 + timedelta(days=17), "FABRIC DEPOT WHOLESALE", -b.money(300, 460), "Cost of Goods Sold")
        b.add(m0 + timedelta(days=24), "CANDLESCIENCE WAX & WICKS", -b.money(380, 600), "Cost of Goods Sold")

    wholesale = [
        ("MT-0041", "Juniper & Moss Boutique", date(2026, 9, 4), 640.00, 18),
        ("MT-0042", "The Copper Kettle Gifts", date(2026, 9, 11), 425.50, 25),
        ("MT-0043", "Hollow Pine General", date(2026, 9, 18), 880.00, None),   # overdue
        ("MT-0044", "Juniper & Moss Boutique", date(2026, 9, 29), 512.75, 20),
        ("MT-0045", "Wren Street Market", date(2026, 10, 6), 760.00, None),    # paid, not marked
        ("MT-0047", "The Copper Kettle Gifts", date(2026, 10, 20), 395.25, 14),  # 46 missing
        ("MT-0048", "Hollow Pine General", date(2026, 11, 3), 615.00, None),   # not due yet
    ]
    for num, cust, issued, amt, paid_after in wholesale:
        b.invoice(num, cust, issued, amt, paid_after, terms=30)
        if paid_after is not None:
            b.add(issued + timedelta(days=paid_after), f"PAYPAL TRANSFER {cust.split()[0].upper()}", amt, "Sales")
    # ---- Planted problems --------------------------------------------------
    # 1. Duplicate invoice number: MT-0044 reused for a different boutique
    b.invoice("MT-0044", "Wren Street Market", date(2026, 10, 1), 298.00, 15)
    b.add(date(2026, 10, 16), "PAYPAL TRANSFER WREN", 298.00, "Sales")
    # 2. Wholesale payment for MT-0045 arrived but was never recorded
    b.add(date(2026, 10, 30), "PAYPAL TRANSFER WREN", 760.00, "Sales", in_ledger=False)
    # 3. Ledger duplicate: the same USPS label purchase entered twice
    usps = [r for r in b.ledger if r["Memo"] == "USPS CLICK N SHIP"][4]
    b.ledger.append({**usps, "Ref": "dup1"})
    # 4. Miscategorized: two Meta ads charges filed under Office Supplies
    seen = 0
    for r in b.ledger:
        if r["Memo"] == "META ADS" and r["Date"][5:7] in ("09", "11"):
            r["Category"] = "Office Supplies"
            seen += 1
            if seen == 2:
                break
    # 5. Uncategorized: a refund and some one-off purchases
    b.add(date(2026, 9, 21), "ETSY REFUND ORDER 3318842", -48.00, "", ledger_cat="")
    b.add(date(2026, 10, 13), "AMAZON MKTPLACE PMTS", -73.29, "", ledger_cat="Uncategorized")
    b.add(date(2026, 10, 27), "PINTEREST ADS", -150.00, "", ledger_cat="Misc")
    b.add(date(2026, 11, 9), "MICHAELS STORE 2290", -61.84, "", ledger_cat="")
    b.add(date(2026, 11, 14), "STAPLES PRINT & MARKETING", -112.60, "", ledger_cat="")
    # 6. Holiday ad blowout: a Meta ads charge many times the usual size
    b.add(date(2026, 11, 20), "META ADS", -1240.00, "Advertising & Marketing")
    # 7. Recent payout recorded in the books that hasn't hit the bank yet (should be low severity)
    b.add(date(2026, 11, 27), "SHOPIFY PAYOUT", 1312.48, "Sales", in_bank=False)
    # 8. Bank-only processing fee nobody recorded
    b.add(date(2026, 10, 31), "SHOPIFY CHARGEBACK FEE", -15.00, "Bank Fees", in_ledger=False)
    b.write("maple-and-thread")


# =========================================================================== 3. mostly healthy
def lakeside_paws_grooming():
    """A tidy pet grooming salon. Only a handful of small problems, to show what a healthy
    scan looks like next to the messier ones."""
    b = Books(seed=37)
    for month in range(3):
        m0 = date(2026, 8 + month, 1)
        b.add(m0, "ACH LAKESIDE PLAZA LLC RENT", -2150.00, "Rent")
        b.add(m0 + timedelta(days=4), "XFINITY BUSINESS", -99.95, "Utilities & Telecom")
        b.add(m0 + timedelta(days=8), "GUSTO PAYROLL", -3860.00, "Payroll")
        b.add(m0 + timedelta(days=22), "GUSTO PAYROLL", -3860.00, "Payroll")
        b.add(m0 + timedelta(days=11), "STATE FARM BUSINESS POLICY", -118.00, "Insurance")
        b.add(m0 + timedelta(days=13), "MOEGO GROOMING SOFTWARE", -79.00, "Software & Subscriptions")
        b.add(m0 + timedelta(days=17), "CITY WATER UTILITY", -b.money(140, 175), "Utilities & Telecom")
        for week in range(4):
            d = m0 + timedelta(days=2 + week * 7)
            b.add(d, "CHEWY BUSINESS SUPPLIES", -b.money(110, 210), "Grooming Supplies")
        for day in range(0, 30, 3):
            b.add(m0 + timedelta(days=day), "SQUARE PAYOUT", b.money(980, 1620), "Sales")
        b.add(m0 + timedelta(days=20), "SQUARE MONTHLY FEE", -29.00, "Bank Fees")

    # A few house-call/boarding partner invoices, all paid on time but one
    partners = [
        ("LPG-301", "Bayside Animal Clinic", date(2026, 8, 6), 420.00, 10),
        ("LPG-302", "Sunnyfield Kennels", date(2026, 8, 20), 655.00, 12),
        ("LPG-303", "Bayside Animal Clinic", date(2026, 9, 3), 380.00, 9),
        ("LPG-304", "Sunnyfield Kennels", date(2026, 9, 17), 610.00, None),  # overdue
        ("LPG-305", "Bayside Animal Clinic", date(2026, 10, 1), 445.00, 11),
    ]
    for num, cust, issued, amt, paid_after in partners:
        b.invoice(num, cust, issued, amt, paid_after, terms=21)
        if paid_after is not None:
            b.add(issued + timedelta(days=paid_after), f"DEPOSIT {cust.split()[0].upper()}", amt, "Sales")
    # ---- Planted problems --------------------------------------------------
    # 1. One uncategorized purchase
    b.add(date(2026, 9, 26), "HARBOR FREIGHT TOOLS 118", -64.99, "", ledger_cat="")
    # 2. One Chewy order filed under Meals
    for r in b.ledger:
        if r["Memo"] == "CHEWY BUSINESS SUPPLIES" and r["Date"].startswith("2026-09"):
            r["Category"] = "Meals"
            break
    # 3. A bank fee that never made it into the books
    b.add(date(2026, 10, 9), "INCOMING WIRE FEE", -15.00, "Bank Fees", in_ledger=False)
    b.write("lakeside-paws-grooming")


if __name__ == "__main__":
    summit_ridge_renovations()
    maple_and_thread()
    lakeside_paws_grooming()
