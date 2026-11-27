# More sample businesses

Three extra sets of made-up books to try Ledger Checkup with. Every business, person, customer and
invoice here is fictional; vendor names like Home Depot or USPS only make the bank lines look realistic.

Each folder has the same three files the upload page asks for: `bank.csv`, `ledger.csv` and `invoices.csv`.

## How to try one

1. Open the app and go to the upload page.
2. Type the business name (for example "Summit Ridge Renovations").
3. Pick the folder's `bank.csv` for **Bank transactions**, `ledger.csv` for **General ledger** and
   `invoices.csv` for **Invoices**.
4. Click **Run scan**. Approve or reject the proposed fixes, then ask the assistant about the results.

## What's planted in each

| Business | What it is | Health score | Problems found |
|---|---|---|---|
| [Summit Ridge Renovations](summit-ridge-renovations/) | Home renovation contractor, Jul to Sep 2026 | about 58 | 14 |
| [Maple & Thread](maple-and-thread/) | Online shop for handmade candles and textiles, Sep to Nov 2026 | about 62 | 16 |
| [Lakeside Paws Grooming](lakeside-paws-grooming/) | Tidy pet grooming salon, Aug to Oct 2026 | about 90 | 4 |

### Summit Ridge Renovations (big-dollar mistakes)
- A $2,171 electrician payment entered twice in the ledger
- Home Depot charged the card twice on the same day
- A $9,800 client deposit in the bank that was never recorded, and the matching invoice still marked unpaid
- A $1,650 check to a roofer recorded in the books that never cleared the bank
- An overdue $5,600 invoice, and a gap in the invoice numbers (SRR-2026-109)
- A $3,975 Home Depot run far above normal
- A $4,000 transfer to savings booked as Materials (probably an owner draw)
- A lumber yard purchase filed under Meals, and three uncategorized purchases

### Maple & Thread (lots of small, sloppy entries)
- Invoice number MT-0044 used for two different boutiques, and MT-0046 missing
- A wholesale payment received but not recorded, with its invoice still marked unpaid
- An overdue boutique invoice
- A USPS label purchase entered twice
- Two Meta ads charges filed under Office Supplies, plus a $1,240 holiday ad charge far above normal
- Five uncategorized items (a refund, Amazon, Pinterest ads, Michaels, Staples)
- A chargeback fee in the bank that never made it into the books
- A payout from the last day that hasn't reached the bank yet (flagged as low priority, which is correct)

### Lakeside Paws Grooming (mostly healthy)
- One overdue partner invoice, one uncategorized purchase, one supply order filed under Meals,
  and one unrecorded $15 wire fee

To regenerate the files: `python scripts/make_more_sample_data.py`. The tests in
`tests/test_more_samples.py` make sure each set keeps surfacing exactly these problems.
