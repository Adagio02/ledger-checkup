"""Issue detectors.

Each check takes a Dataset and returns a list of Issues, each with a proposed Fix.
Checks never modify data; fixes are only applied after the owner approves them.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta

from .models import Dataset, Fix, Invoice, Issue, Transaction

UNCATEGORIZED = {"", "uncategorized", "uncategorized expense", "uncategorized income",
                 "ask my accountant", "suspense", "misc", "miscellaneous", "other"}

KEYWORD_CATEGORIES = [
    (r"\b(aws|amazon web services|google cloud|github|slack|zoom|adobe|microsoft|dropbox|notion|quickbooks|shopify)\b", "Software & Subscriptions"),
    (r"\b(uber|lyft|delta|united|american airlines|southwest|airbnb|marriott|hilton|hotel)\b", "Travel"),
    (r"\b(shell|chevron|exxon|bp|fuel|gas station)\b", "Vehicle & Fuel"),
    (r"\b(staples|office depot|officemax)\b", "Office Supplies"),
    (r"\b(comcast|verizon|at&t|t-mobile|internet|phone)\b", "Utilities & Telecom"),
    (r"\b(pg&e|electric|water|utility|edison)\b", "Utilities & Telecom"),
    (r"\b(rent|lease|landlord)\b", "Rent"),
    (r"\b(gusto|adp|payroll|paychex)\b", "Payroll"),
    (r"\b(irs|tax|franchise tax board|eftps)\b", "Taxes"),
    (r"\b(insurance|geico|state farm|hiscox|next insurance)\b", "Insurance"),
    (r"\b(restaurant|cafe|coffee|starbucks|doordash|grubhub|ubereats)\b", "Meals"),
    (r"\b(google ads|facebook ads|meta ads|mailchimp|linkedin)\b", "Advertising & Marketing"),
    (r"\b(stripe|square|paypal) (payout|transfer|deposit)\b", "Sales"),
    (r"\b(bank fee|service charge|overdraft|monthly fee|wire fee)\b", "Bank Fees"),
]

STOP_WORDS = {"pos", "debit", "card", "purchase", "ach", "payment", "online", "recurring", "inc", "llc",
              "co", "the", "transfer", "to", "from", "www", "com", "ref"}


def vendor_key(description: str) -> str:
    """Normalize a bank description to a stable vendor name ("AMZN Mktp #123" -> "amzn mktp")."""
    text = re.sub(r"[^a-z& ]", " ", description.lower())
    words = [w for w in text.split() if w not in STOP_WORDS and len(w) > 1]
    return " ".join(words[:2])


def suggest_category(txn: Transaction, history: dict[str, Counter]) -> tuple[str | None, str]:
    key = vendor_key(txn.description)
    if key and history.get(key):
        cat, n = history[key].most_common(1)[0]
        return cat, f"{n} earlier '{key}' transaction(s) were filed under {cat}"
    desc = txn.description.lower()
    for pattern, cat in KEYWORD_CATEGORIES:
        if re.search(pattern, desc):
            return cat, f"the description matches common {cat} vendors"
    if txn.amount > 0:
        return "Sales", "it is a deposit"
    return None, "no similar transactions were found"


def _books(ds: Dataset) -> list[Transaction]:
    """The set of transactions treated as 'the books' (ledger if provided, else bank)."""
    return ds.ledger or ds.bank


def _category_history(txns: list[Transaction]) -> dict[str, Counter]:
    history: dict[str, Counter] = defaultdict(Counter)
    for t in txns:
        if t.category.strip().lower() not in UNCATEGORIZED:
            history[vendor_key(t.description)][t.category] += 1
    return history


def as_of_date(ds: Dataset) -> date:
    dates = [t.date for t in ds.bank + ds.ledger] + [i.issue_date for i in ds.invoices]
    return max(dates) if dates else date.today()


def _money(x: float) -> str:
    return f"${abs(x):,.2f}"


# --------------------------------------------------------------------------- checks

def check_duplicates(ds: Dataset) -> list[Issue]:
    issues: list[Issue] = []
    for source, txns in (("bank", ds.bank), ("ledger", ds.ledger)):
        groups: dict[tuple, list[Transaction]] = defaultdict(list)
        for t in txns:
            groups[(round(t.amount, 2), vendor_key(t.description))].append(t)
        for group in groups.values():
            group.sort(key=lambda t: t.date)
            for a, b in zip(group, group[1:]):
                if (b.date - a.date).days <= 1:
                    issues.append(Issue(
                        id="", check="duplicate", severity="critical" if abs(b.amount) >= 1000 else "serious",
                        title=f"Possible duplicate: {b.description} ({_money(b.amount)})",
                        explanation=(f"Two {source} entries for {_money(b.amount)} to the same payee "
                                     f"('{a.description}' on {a.date}, '{b.description}' on {b.date}) "
                                     f"are within a day of each other. Double entries overstate "
                                     f"{'expenses' if b.amount < 0 else 'income'} and distort your profit."),
                        amount_at_stake=abs(b.amount), records=[a.id, b.id],
                        fix=(Fix("delete_transaction", f"Remove the second entry ({b.id}, {b.date})",
                                 {"txn_id": b.id}) if source == "ledger" else
                             Fix("review", "Ask the vendor or bank to refund the double charge",
                                 {"txn_id": b.id})),
                    ))
    return issues


def check_uncategorized(ds: Dataset) -> list[Issue]:
    books = _books(ds)
    history = _category_history(books)
    issues = []
    for t in books:
        if t.category.strip().lower() not in UNCATEGORIZED:
            continue
        cat, why = suggest_category(t, history)
        label = f"'{t.category}'" if t.category else "no category"
        fix = (Fix("set_category", f"Categorize as {cat}", {"txn_id": t.id, "category": cat})
               if cat else Fix("review", "Ask your bookkeeper which category fits", {"txn_id": t.id}))
        issues.append(Issue(
            id="", check="uncategorized", severity="warning",
            title=f"Uncategorized: {t.description} ({_money(t.amount)})",
            explanation=(f"This {t.date} transaction has {label}. Uncategorized items hide where money "
                         f"goes and can mean missed tax deductions. Suggested: {cat or 'needs review'}, "
                         f"because {why}."),
            amount_at_stake=abs(t.amount), records=[t.id], fix=fix,
        ))
    return issues


def check_miscategorized(ds: Dataset) -> list[Issue]:
    books = _books(ds)
    history = _category_history(books)
    issues = []
    for t in books:
        if t.category.strip().lower() in UNCATEGORIZED:
            continue
        counts = history.get(vendor_key(t.description))
        if not counts or sum(counts.values()) < 3:
            continue
        top, top_n = counts.most_common(1)[0]
        if top != t.category and top_n / sum(counts.values()) >= 0.66:
            issues.append(Issue(
                id="", check="miscategorized", severity="warning",
                title=f"Inconsistent category: {t.description}",
                explanation=(f"This payment is filed under {t.category}, but {top_n} of "
                             f"{sum(counts.values())} payments to the same vendor are filed under {top}. "
                             f"Inconsistent categories make reports and tax returns inaccurate."),
                amount_at_stake=abs(t.amount), records=[t.id],
                fix=Fix("set_category", f"Change category from {t.category} to {top}",
                        {"txn_id": t.id, "category": top}),
            ))
    return issues


def reconcile(ds: Dataset, window_days: int = 4) -> tuple[list[Transaction], list[Transaction]]:
    """Match bank lines to ledger lines by amount and nearby date. Returns the unmatched of each."""
    unmatched_ledger = sorted(ds.ledger, key=lambda t: t.date)
    unmatched_bank = []
    for b in sorted(ds.bank, key=lambda t: t.date):
        best = None
        for l in unmatched_ledger:
            if abs(l.amount - b.amount) < 0.005 and abs((l.date - b.date).days) <= window_days:
                if best is None or abs((l.date - b.date).days) < abs((best.date - b.date).days):
                    best = l
        if best:
            unmatched_ledger.remove(best)
        else:
            unmatched_bank.append(b)
    return unmatched_bank, unmatched_ledger


def check_unreconciled(ds: Dataset) -> list[Issue]:
    if not (ds.bank and ds.ledger):
        return []
    missing_in_books, missing_in_bank = reconcile(ds)
    history = _category_history(ds.ledger)
    last_bank = max(t.date for t in ds.bank)
    issues = []
    for b in missing_in_books:
        cat, why = suggest_category(b, history)
        issues.append(Issue(
            id="", check="unreconciled", severity="critical" if abs(b.amount) >= 1000 else "serious",
            title=f"In bank but not in books: {b.description} ({_money(b.amount)})",
            explanation=(f"Your bank shows {_money(b.amount)} {'received' if b.amount > 0 else 'paid'} on "
                         f"{b.date}, but no matching entry exists in the ledger. Your books will "
                         f"{'understate income' if b.amount > 0 else 'understate expenses'} until it is recorded."),
            amount_at_stake=abs(b.amount), records=[b.id],
            fix=Fix("add_ledger_entry", f"Record it in the ledger as {cat or 'Uncategorized'}",
                    {"txn_id": b.id, "category": cat or "Uncategorized"}),
        ))
    for l in missing_in_bank:
        recent = (last_bank - l.date).days <= 7
        issues.append(Issue(
            id="", check="unreconciled", severity="info" if recent else "serious",
            title=f"In books but not in bank: {l.description} ({_money(l.amount)})",
            explanation=(f"The ledger records {_money(l.amount)} on {l.date}, but no bank transaction matches. "
                         + ("It is recent, so it may simply not have cleared yet."
                            if recent else
                            "It may be a typo, a duplicate, a payment that never happened, or one paid "
                            "from a different account.")),
            amount_at_stake=abs(l.amount), records=[l.id],
            fix=Fix("review", "Confirm the payment happened; delete or correct the entry if it did not",
                    {"txn_id": l.id}),
        ))
    return issues


def check_anomalies(ds: Dataset) -> list[Issue]:
    books = _books(ds)
    by_cat: dict[str, list[Transaction]] = defaultdict(list)
    for t in books:
        if t.amount < 0 and t.category.strip().lower() not in UNCATEGORIZED:
            by_cat[t.category].append(t)
    issues = []
    for cat, txns in by_cat.items():
        if len(txns) < 5:
            continue
        amounts = [abs(t.amount) for t in txns]
        med = statistics.median(amounts)
        mad = statistics.median(abs(a - med) for a in amounts) or med * 0.1 or 1.0
        for t in txns:
            z = 0.6745 * (abs(t.amount) - med) / mad
            if z > 3.5 and abs(t.amount) > 3 * med:
                issues.append(Issue(
                    id="", check="anomaly", severity="warning",
                    title=f"Unusually large {cat} expense: {t.description} ({_money(t.amount)})",
                    explanation=(f"This is {abs(t.amount) / med:.1f}x your typical {cat} payment "
                                 f"(median {_money(med)} across {len(txns)} payments). It may be legitimate, "
                                 f"but large outliers are where billing errors and fraud usually show up."),
                    amount_at_stake=abs(t.amount) - med, records=[t.id],
                    fix=Fix("review", "Check the receipt or contract and confirm the amount", {"txn_id": t.id}),
                ))
    for t in books:
        if t.amount <= -2000 and abs(t.amount) % 1000 == 0 and t.category.lower() not in ("rent", "payroll", "taxes"):
            issues.append(Issue(
                id="", check="anomaly", severity="info",
                title=f"Large round-number payment: {t.description} ({_money(t.amount)})",
                explanation=("Exact round-number payments are often owner draws, loans or transfers rather "
                             "than business expenses. If so, they belong in equity or a liability account, "
                             "not in expenses."),
                amount_at_stake=abs(t.amount), records=[t.id],
                fix=Fix("review", "Confirm what this payment was for and that it is categorized correctly",
                        {"txn_id": t.id}),
            ))
    return issues


def _invoice_seq(number: str) -> tuple[str, int, int] | None:
    m = re.match(r"^(.*?)(\d+)$", number.strip())
    return (m.group(1), int(m.group(2)), len(m.group(2))) if m else None


def check_invoices(ds: Dataset) -> list[Issue]:
    if not ds.invoices:
        return []
    issues: list[Issue] = []
    as_of = as_of_date(ds)

    # Duplicate invoice numbers
    counts = Counter(i.number for i in ds.invoices)
    for number, n in counts.items():
        if n > 1:
            dupes = [i for i in ds.invoices if i.number == number]
            issues.append(Issue(
                id="", check="invoice", severity="serious",
                title=f"Invoice number {number} used {n} times",
                explanation=("Each invoice needs a unique number. Reused numbers confuse customers and "
                             "auditors and can mean the same sale was billed or recorded twice."),
                amount_at_stake=sum(i.amount for i in dupes[1:]), records=[number],
                fix=Fix("review", f"Renumber or void the duplicate {number}", {"invoice": number}),
            ))

    # Gaps in the numbering sequence
    by_prefix: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for inv in ds.invoices:
        seq = _invoice_seq(inv.number)
        if seq:
            by_prefix[seq[0]].append((seq[1], seq[2]))
    for prefix, nums in by_prefix.items():
        present = {n for n, _ in nums}
        width = max(w for _, w in nums)
        missing = [n for n in range(min(present), max(present)) if n not in present]
        if missing and len(missing) <= 50:
            names = [f"{prefix}{str(n).zfill(width)}" for n in missing]
            issues.append(Issue(
                id="", check="invoice", severity="warning",
                title=f"Missing invoice number(s): {', '.join(names[:5])}{'...' if len(names) > 5 else ''}",
                explanation=("Your invoice numbers skip these values. A gap usually means an invoice was "
                             "deleted, voided without a record, or never entered, which can hide unbilled "
                             "or unrecorded revenue."),
                amount_at_stake=0.0, records=names,
                fix=Fix("review", "Find these invoices, or record them as voided", {"invoices": names}),
            ))

    # Unpaid invoices that look paid / overdue invoices
    deposits = sorted((t for t in ds.bank if t.amount > 0), key=lambda t: t.date)
    used: set[str] = set()
    for inv in sorted(ds.invoices, key=lambda i: i.issue_date):
        if inv.status == "paid":
            continue
        candidates = [d for d in deposits if d.id not in used and abs(d.amount - inv.amount) < 0.005
                      and d.date >= inv.issue_date]
        candidates.sort(key=lambda d: (inv.customer.lower().split()[0] not in d.description.lower()
                                       if inv.customer else True, d.date))
        if candidates:
            dep = candidates[0]
            used.add(dep.id)
            issues.append(Issue(
                id="", check="invoice", severity="warning",
                title=f"Invoice {inv.number} looks paid but is marked unpaid",
                explanation=(f"A bank deposit of {_money(dep.amount)} on {dep.date} ('{dep.description}') "
                             f"matches invoice {inv.number} for {inv.customer or 'this customer'}. "
                             f"Leaving it unpaid overstates receivables and could trigger a wrong reminder."),
                amount_at_stake=inv.amount, records=[inv.number, dep.id],
                fix=Fix("mark_invoice_paid", f"Mark {inv.number} paid on {dep.date}",
                        {"invoice": inv.number, "paid_date": dep.date.isoformat()}),
            ))
        elif inv.due_date and inv.due_date < as_of:
            days = (as_of - inv.due_date).days
            issues.append(Issue(
                id="", check="invoice", severity="serious" if days > 60 else "warning",
                title=f"Overdue: invoice {inv.number} ({_money(inv.amount)}, {days} days late)",
                explanation=(f"{inv.customer or 'The customer'} was due to pay {_money(inv.amount)} on "
                             f"{inv.due_date} and no matching deposit was found. Invoices over 90 days late "
                             f"are much less likely to be collected."),
                amount_at_stake=inv.amount, records=[inv.number],
                fix=Fix("review", f"Send a payment reminder to {inv.customer or 'the customer'}",
                        {"invoice": inv.number}),
            ))
    return issues


CHECKS = [check_duplicates, check_uncategorized, check_miscategorized, check_unreconciled,
          check_anomalies, check_invoices]

SEVERITY_ORDER = {"critical": 0, "serious": 1, "warning": 2, "info": 3}

CHECK_LABELS = {
    "duplicate": "Duplicate entries",
    "uncategorized": "Uncategorized",
    "miscategorized": "Inconsistent categories",
    "unreconciled": "Bank vs. books mismatch",
    "anomaly": "Unusual amounts",
    "invoice": "Invoice problems",
}


def run_all(ds: Dataset) -> list[Issue]:
    issues: list[Issue] = []
    for check in CHECKS:
        issues.extend(check(ds))
    # A duplicate also shows up as a reconciliation mismatch; report it once, as the duplicate.
    dup_ids = {i.records[-1] for i in issues if i.check == "duplicate"}
    issues = [i for i in issues if not (i.check == "unreconciled" and i.records[0] in dup_ids)]
    issues.sort(key=lambda i: (SEVERITY_ORDER[i.severity], -i.amount_at_stake))
    for n, issue in enumerate(issues, start=1):
        issue.id = f"{issue.check}-{n}"
    return issues


def summarize(ds: Dataset, issues: list[Issue]) -> dict:
    open_issues = [i for i in issues if i.status == "open"]
    by_check = Counter(i.check for i in open_issues)
    by_sev = Counter(i.severity for i in open_issues)
    penalty = sum({"critical": 8, "serious": 4, "warning": 2, "info": 0.5}[i.severity] for i in open_issues)
    monthly: dict[str, dict[str, float]] = defaultdict(lambda: {"in": 0.0, "out": 0.0})
    for t in ds.bank or ds.ledger:
        m = t.date.strftime("%Y-%m")
        monthly[m]["in" if t.amount > 0 else "out"] += abs(t.amount)
    spend: Counter = Counter()
    for t in _books(ds):
        if t.amount < 0:
            spend[t.category or "Uncategorized"] += abs(t.amount)
    return {
        "as_of": as_of_date(ds).isoformat(),
        "health_score": max(0, round(100 - penalty)),
        "counts": {"bank": len(ds.bank), "ledger": len(ds.ledger), "invoices": len(ds.invoices)},
        "open_issues": len(open_issues),
        "total_issues": len(issues),
        "approved": sum(1 for i in issues if i.status == "approved"),
        "rejected": sum(1 for i in issues if i.status == "rejected"),
        "amount_at_stake": round(sum(i.amount_at_stake for i in open_issues), 2),
        "by_severity": {s: by_sev.get(s, 0) for s in SEVERITY_ORDER},
        "by_check": [{"check": c, "label": CHECK_LABELS[c], "count": by_check[c],
                      "amount": round(sum(i.amount_at_stake for i in open_issues if i.check == c), 2)}
                     for c in CHECK_LABELS if by_check.get(c)],
        "monthly": [{"month": m, **{k: round(v, 2) for k, v in vals.items()}}
                    for m, vals in sorted(monthly.items())],
        "top_spend": [{"category": c, "amount": round(a, 2)} for c, a in spend.most_common(8)],
    }
