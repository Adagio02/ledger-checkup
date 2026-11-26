"""Apply owner-approved fixes and export the corrected books."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timezone

from .models import Dataset, Issue, Transaction


class FixError(ValueError):
    pass


def apply_fix(ds: Dataset, issue: Issue) -> str:
    """Apply an approved fix to the dataset in place. Returns a human-readable audit note."""
    fix, p = issue.fix, issue.fix.params
    if fix.action == "review":
        return f"Marked reviewed: {fix.summary}"

    if fix.action == "delete_transaction":
        for lst in (ds.bank, ds.ledger):
            for t in lst:
                if t.id == p["txn_id"]:
                    lst.remove(t)
                    return f"Deleted {t.source} transaction {t.id} ({t.date}, {t.description}, {t.amount:.2f})"
        raise FixError(f"Transaction {p['txn_id']} no longer exists")

    if fix.action == "set_category":
        t = ds.find_txn(p["txn_id"])
        if not t:
            raise FixError(f"Transaction {p['txn_id']} no longer exists")
        old, t.category = t.category, p["category"]
        return f"Changed category of {t.id} from '{old or 'none'}' to '{t.category}'"

    if fix.action == "add_ledger_entry":
        b = ds.find_txn(p["txn_id"])
        if not b:
            raise FixError(f"Transaction {p['txn_id']} no longer exists")
        new = Transaction(id=f"L-from-{b.id}", date=b.date, description=b.description, amount=b.amount,
                          source="ledger", category=p.get("category", "Uncategorized"), account=b.account)
        if ds.find_txn(new.id):
            raise FixError("Ledger entry already added")
        ds.ledger.append(new)
        return f"Added ledger entry {new.id} ({new.date}, {new.description}, {new.amount:.2f}, {new.category})"

    if fix.action == "mark_invoice_paid":
        for inv in ds.invoices:
            if inv.number == p["invoice"] and inv.status != "paid":
                inv.status, inv.paid_date = "paid", date.fromisoformat(p["paid_date"])
                return f"Marked invoice {inv.number} paid on {inv.paid_date}"
        raise FixError(f"Invoice {p['invoice']} not found or already paid")

    raise FixError(f"Unknown fix action {fix.action}")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _csv(rows: list[dict], fields: list[str]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def export_csv(ds: Dataset, kind: str, audit: list[dict] | None = None) -> str:
    if kind in ("bank", "ledger"):
        rows = [t.to_dict() for t in sorted(getattr(ds, kind), key=lambda t: t.date)]
        return _csv(rows, ["id", "date", "description", "amount", "category", "account"])
    if kind == "invoices":
        return _csv([i.to_dict() for i in ds.invoices],
                    ["number", "customer", "issue_date", "due_date", "amount", "status", "paid_date"])
    if kind == "audit":
        return _csv(audit or [], ["time", "issue_id", "decision", "note"])
    raise FixError(f"Unknown export {kind}")
