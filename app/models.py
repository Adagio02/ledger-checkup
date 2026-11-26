"""Core data types shared by importers, checks, fixes and the API."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


@dataclass
class Transaction:
    id: str
    date: date
    description: str
    amount: float  # positive = money in, negative = money out
    source: str  # "bank" or "ledger"
    category: str = ""
    account: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["date"] = self.date.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Transaction":
        return cls(**{**d, "date": date.fromisoformat(d["date"])})


@dataclass
class Invoice:
    number: str
    customer: str
    issue_date: date
    due_date: date | None
    amount: float
    status: str = "unpaid"  # "paid" or "unpaid"
    paid_date: date | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("issue_date", "due_date", "paid_date"):
            d[k] = d[k].isoformat() if d[k] else None
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Invoice":
        d = dict(d)
        for k in ("issue_date", "due_date", "paid_date"):
            d[k] = date.fromisoformat(d[k]) if d.get(k) else None
        return cls(**d)


@dataclass
class Dataset:
    bank: list[Transaction] = field(default_factory=list)
    ledger: list[Transaction] = field(default_factory=list)
    invoices: list[Invoice] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bank": [t.to_dict() for t in self.bank],
            "ledger": [t.to_dict() for t in self.ledger],
            "invoices": [i.to_dict() for i in self.invoices],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Dataset":
        return cls(
            bank=[Transaction.from_dict(t) for t in d.get("bank", [])],
            ledger=[Transaction.from_dict(t) for t in d.get("ledger", [])],
            invoices=[Invoice.from_dict(i) for i in d.get("invoices", [])],
        )

    def find_txn(self, txn_id: str) -> Transaction | None:
        for t in self.bank + self.ledger:
            if t.id == txn_id:
                return t
        return None


@dataclass
class Fix:
    """A proposed change. Nothing is applied until the owner approves it."""

    action: str  # delete_transaction | set_category | add_ledger_entry | mark_invoice_paid | review
    summary: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Issue:
    id: str
    check: str
    severity: str  # critical | serious | warning | info
    title: str
    explanation: str
    amount_at_stake: float
    records: list[str]  # ids of transactions / invoice numbers involved
    fix: Fix
    status: str = "open"  # open | approved | rejected

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Issue":
        d = dict(d)
        d["fix"] = Fix(**d["fix"])
        return cls(**d)
