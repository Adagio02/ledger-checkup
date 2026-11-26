from datetime import date
from pathlib import Path

from app.checks import reconcile, run_all, summarize, vendor_key
from app.fixes import apply_fix, export_csv
from app.importers import load_csvs, parse_amount, read_transactions
from app.models import Dataset, Transaction

SAMPLE = Path(__file__).resolve().parent.parent / "sample_data"


def sample() -> Dataset:
    read = lambda n: (SAMPLE / n).read_text()
    return load_csvs(read("bank.csv"), read("ledger.csv"), read("invoices.csv"))


def t(id, d, desc, amt, src="ledger", cat=""):
    return Transaction(id=id, date=date.fromisoformat(d), description=desc, amount=amt, source=src, category=cat)


def test_parse_amount_formats():
    assert parse_amount("$1,234.50") == 1234.5
    assert parse_amount("(45.00)") == -45.0
    assert parse_amount("-12") == -12.0
    assert parse_amount("") is None


def test_debit_credit_columns():
    csv_text = "Posted Date,Payee,Debit,Credit\n01/05/2026,Coffee,4.50,\n01/06/2026,Client,,100\n"
    txns = read_transactions(csv_text, "bank")
    assert [x.amount for x in txns] == [-4.5, 100.0]
    assert txns[0].date == date(2026, 1, 5)


def test_vendor_key_normalizes():
    assert vendor_key("POS DEBIT STAPLES STORE 0442") == vendor_key("Staples Store #99")


def test_sample_data_finds_every_planted_problem():
    issues = run_all(sample())
    titles = " | ".join(i.title for i in issues)
    by_check = {}
    for i in issues:
        by_check.setdefault(i.check, []).append(i)
    assert len(by_check["duplicate"]) == 2
    assert len(by_check["uncategorized"]) == 4
    assert len(by_check["miscategorized"]) == 1
    assert len(by_check["unreconciled"]) == 3
    assert "BLUE RIDGE ROASTERS ($4,850.00)" in titles
    assert "Large round-number payment" in titles
    assert "INV-1009 looks paid" in titles
    assert "Overdue: invoice INV-1002" in titles
    assert "INV-1006" in titles
    assert "INV-1010 used 2 times" in titles
    # No false alarms on the clean recurring bills
    assert "PG&E ELECTRIC ($280" not in titles
    assert len(issues) == 16


def test_issues_are_sorted_by_severity():
    order = {"critical": 0, "serious": 1, "warning": 2, "info": 3}
    sev = [order[i.severity] for i in run_all(sample())]
    assert sev == sorted(sev)


def test_recurring_monthly_charges_are_not_duplicates():
    ds = Dataset(ledger=[t("1", "2026-01-01", "Rent", -1000, cat="Rent"),
                         t("2", "2026-02-01", "Rent", -1000, cat="Rent")])
    assert not [i for i in run_all(ds) if i.check == "duplicate"]


def test_reconcile_tolerates_small_date_shift():
    ds = Dataset(bank=[t("b1", "2026-01-01", "X", -50, "bank")],
                 ledger=[t("l1", "2026-01-03", "X", -50)])
    assert reconcile(ds) == ([], [])


def test_fixes_only_apply_when_approved_and_change_the_data():
    ds = sample()
    issues = run_all(ds)
    before = len(ds.ledger)
    dup = next(i for i in issues if i.check == "duplicate" and i.fix.action == "delete_transaction")
    apply_fix(ds, dup)
    assert len(ds.ledger) == before - 1

    unc = next(i for i in issues if i.fix.action == "set_category")
    apply_fix(ds, unc)
    assert ds.find_txn(unc.fix.params["txn_id"]).category == unc.fix.params["category"]

    missing = next(i for i in issues if i.fix.action == "add_ledger_entry")
    apply_fix(ds, missing)
    paid = next(i for i in issues if i.fix.action == "mark_invoice_paid")
    apply_fix(ds, paid)
    assert next(x for x in ds.invoices if x.number == "INV-1009").status == "paid"

    remaining = run_all(ds)
    assert len(remaining) < len(issues)
    assert "L-from-" in export_csv(ds, "ledger")


def test_summary_shape():
    ds = sample()
    s = summarize(ds, run_all(ds))
    assert 0 <= s["health_score"] <= 100
    assert s["open_issues"] == 16
    assert {m["month"] for m in s["monthly"]} == {"2026-08", "2026-09", "2026-10"}
