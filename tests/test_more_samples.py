"""The extra sample businesses in sample_data/more must keep surfacing exactly their planted problems."""
from collections import Counter
from pathlib import Path

import pytest

from app.checks import run_all
from app.importers import load_csvs

MORE = Path(__file__).resolve().parent.parent / "sample_data" / "more"


def scan(slug):
    read = lambda n: (MORE / slug / n).read_text()
    issues = run_all(load_csvs(read("bank.csv"), read("ledger.csv"), read("invoices.csv")))
    return issues, " | ".join(i.title for i in issues)


EXPECTED = {
    "summit-ridge-renovations": (
        {"duplicate": 2, "unreconciled": 2, "invoice": 3, "anomaly": 3, "miscategorized": 1, "uncategorized": 3},
        ["ACH CASTILLO ELECTRIC LLC", "MOBILE DEPOSIT DELGADO ($9,800.00)", "CHECK 2211 HARGROVE ROOFING",
         "SRR-2026-107 looks paid", "Overdue: invoice SRR-2026-105", "SRR-2026-109",
         "THE HOME DEPOT 4417 ($3,975.60)", "Large round-number payment", "MILLER LUMBER YARD"],
    ),
    "maple-and-thread": (
        {"duplicate": 1, "unreconciled": 3, "invoice": 4, "anomaly": 1, "miscategorized": 2, "uncategorized": 5},
        ["MT-0044 used 2 times", "MT-0045 looks paid", "Overdue: invoice MT-0043", "MT-0046",
         "USPS CLICK N SHIP", "META ADS ($1,240.00)", "SHOPIFY CHARGEBACK FEE", "PINTEREST ADS"],
    ),
    "lakeside-paws-grooming": (
        {"unreconciled": 1, "invoice": 1, "miscategorized": 1, "uncategorized": 1},
        ["INCOMING WIRE FEE", "Overdue: invoice LPG-304", "CHEWY BUSINESS SUPPLIES", "HARBOR FREIGHT TOOLS"],
    ),
}


@pytest.mark.parametrize("slug", EXPECTED)
def test_more_samples_find_their_planted_problems(slug):
    counts, phrases = EXPECTED[slug]
    issues, titles = scan(slug)
    assert dict(Counter(i.check for i in issues)) == counts
    for phrase in phrases:
        assert phrase in titles


def test_recent_unmatched_payout_is_low_severity():
    issues, _ = scan("maple-and-thread")
    payout = [i for i in issues if "SHOPIFY PAYOUT" in i.title]
    assert [i.severity for i in payout] == ["info"]
