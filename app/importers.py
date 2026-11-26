"""CSV importers.

Column names are matched loosely so exports from most banks and accounting tools
work without editing. New sources (QuickBooks, Xero, Plaid...) can be added by
writing a function that returns a ``Dataset``.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime

from .models import Dataset, Invoice, Transaction

DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%Y/%m/%d", "%b %d, %Y", "%d-%b-%Y")

ALIASES = {
    "date": ["date", "transaction date", "posted date", "posting date", "txn date"],
    "description": ["description", "memo", "payee", "name", "details", "narrative"],
    "amount": ["amount", "value", "total"],
    "debit": ["debit", "withdrawal", "money out", "outflow"],
    "credit": ["credit", "deposit", "money in", "inflow"],
    "category": ["category", "account name", "class", "expense category"],
    "account": ["account", "bank account", "split"],
    "id": ["id", "transaction id", "ref", "reference", "txn id"],
    "number": ["invoice", "invoice number", "invoice no", "number", "invoice #", "no"],
    "customer": ["customer", "client", "bill to"],
    "issue_date": ["issue date", "invoice date", "date"],
    "due_date": ["due date", "due"],
    "status": ["status", "state"],
    "paid_date": ["paid date", "date paid", "payment date"],
}


class ImportError_(ValueError):
    pass


def parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ImportError_(f"Unrecognized date: {value!r}")


def parse_amount(value: str) -> float | None:
    value = (value or "").strip()
    if not value:
        return None
    negative = value.startswith("(") and value.endswith(")")
    cleaned = re.sub(r"[^0-9.\-]", "", value)
    if cleaned in ("", "-", "."):
        return None
    amount = float(cleaned)
    return -abs(amount) if negative else amount


def _column_map(headers: list[str], wanted: list[str]) -> dict[str, str]:
    normalized = {h.strip().lower(): h for h in headers}
    found: dict[str, str] = {}
    for key in wanted:
        for alias in ALIASES[key]:
            if alias in normalized and normalized[alias] not in found.values():
                found[key] = normalized[alias]
                break
    return found


def _reader(text: str) -> csv.DictReader:
    text = text.lstrip("﻿")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ImportError_("CSV has no header row")
    return reader


def read_transactions(text: str, source: str) -> list[Transaction]:
    reader = _reader(text)
    cols = _column_map(list(reader.fieldnames or []),
                       ["date", "description", "amount", "debit", "credit", "category", "account", "id"])
    if "date" not in cols or "description" not in cols:
        raise ImportError_(f"{source} CSV needs a date and a description column; found {reader.fieldnames}")
    if "amount" not in cols and not ("debit" in cols or "credit" in cols):
        raise ImportError_(f"{source} CSV needs an amount column (or debit/credit columns)")

    txns: list[Transaction] = []
    for i, row in enumerate(reader, start=1):
        if not any((v or "").strip() for v in row.values()):
            continue
        if "amount" in cols:
            amount = parse_amount(row[cols["amount"]]) or 0.0
        else:
            credit = parse_amount(row.get(cols.get("credit", ""), "")) or 0.0
            debit = parse_amount(row.get(cols.get("debit", ""), "")) or 0.0
            amount = abs(credit) - abs(debit)
        d = parse_date(row[cols["date"]])
        if d is None:
            raise ImportError_(f"{source} row {i} has no date")
        txn_id = (row.get(cols["id"]) or "").strip() if "id" in cols else ""
        txns.append(Transaction(
            id=f"{source[0].upper()}-{txn_id or i}",
            date=d,
            description=(row[cols["description"]] or "").strip(),
            amount=round(amount, 2),
            source=source,
            category=(row.get(cols["category"]) or "").strip() if "category" in cols else "",
            account=(row.get(cols["account"]) or "").strip() if "account" in cols else "",
        ))
    return txns


def read_invoices(text: str) -> list[Invoice]:
    reader = _reader(text)
    cols = _column_map(list(reader.fieldnames or []),
                       ["number", "customer", "issue_date", "due_date", "amount", "status", "paid_date"])
    for need in ("number", "amount", "issue_date"):
        if need not in cols:
            raise ImportError_(f"Invoice CSV needs a {need.replace('_', ' ')} column; found {reader.fieldnames}")
    invoices = []
    for row in reader:
        if not any((v or "").strip() for v in row.values()):
            continue
        paid_date = parse_date(row.get(cols.get("paid_date", ""), "")) if "paid_date" in cols else None
        status = (row.get(cols["status"]) or "").strip().lower() if "status" in cols else ""
        status = "paid" if status == "paid" or paid_date else "unpaid"
        invoices.append(Invoice(
            number=row[cols["number"]].strip(),
            customer=(row.get(cols["customer"]) or "").strip() if "customer" in cols else "",
            issue_date=parse_date(row[cols["issue_date"]]),
            due_date=parse_date(row.get(cols["due_date"], "")) if "due_date" in cols else None,
            amount=round(parse_amount(row[cols["amount"]]) or 0.0, 2),
            status=status,
            paid_date=paid_date,
        ))
    return invoices


def load_csvs(bank: str | None, ledger: str | None, invoices: str | None) -> Dataset:
    if not (bank or ledger or invoices):
        raise ImportError_("Upload at least one CSV file")
    return Dataset(
        bank=read_transactions(bank, "bank") if bank else [],
        ledger=read_transactions(ledger, "ledger") if ledger else [],
        invoices=read_invoices(invoices) if invoices else [],
    )
