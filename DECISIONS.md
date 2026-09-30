# Decisions

_Last updated 30 Sep 2026. Only things you have said yes to._

## Recorded 30 Sep
- **Wage = VERTU MOTORS PLC**, paid around the 27th to 31st.
- **Small balance mismatches are accepted** (like the 50.00 ones). Keep the CHECK warning
  and mark the statement "off by X". _(Not built yet: today it just prints CHECK.)_

## Earlier
- Personal use only, no login. HSBC only.
- PDFs are dropped in the `statements/` folder by hand (email fetch is later).
- Wage is typed in by the user (side income and bonus tracking come later).
- Bills = direct debits and standing orders. Everything else out is "random".
- Cash stays as "cash out" and the user labels it.
- Data goes in a SQLite file kept on the PC only. Never commit the database or any PDFs.
- Duplicate statements are skipped automatically.
- Starter categories: Rent, Water, Gas & Electric, Council tax, Internet/TV/Phone,
  Car (loan, insurance, tax), Life insurance, Food shop, Takeaways, Fuel, Cash,
  Fun/Subscriptions, Shopping, Savings/Transfers, One-offs, Unsorted.

## Recorded 30 Sep (confirm-as-you-go and the database)
- **What gets labelled:** each item = payment type + payer + reference, not just the payer.
  Example: standing order KATIE FINCH "RENT", standing order KATIE FINCH "BILLS" and bill
  payment KATIE FINCH "Food and bil" are three separate items.
- **Standing orders and direct debits set what is common.** Bill-payment top-ups (for example
  to Katie when she is short) are extras: random by default, but labelled ("Katie top-ups")
  so the total is visible.
- **The app asks, you confirm.** After reading the PDFs it lists new items (10 at a time,
  biggest money first) with a suggested kind (Regular / Common / Random / One-off) and a
  suggested label. You answer in one line, e.g. `common 1 2 4  oneoff 6`.
  The suggestion comes from the payment type: SO and DD suggest Regular; BP and card suggest Random.
- **Never asked twice.** Once answered, an item is saved and not asked again (also not twice in one run).
  - Enter (or leaving a number out) accepts the suggestion and saves it.
  - `later 3 5` skips those items; they are asked again next run and nothing is saved.
  - `stop` ends the questions for this run.
  - `fix` lists saved items (suggestions you accepted are marked "suggested") so any can be changed.
- **SQLite, not memory.** The database remembers statements, payments and your answers.
  It lives next to the real statements folder (`Financial Tracker Project\tracker.db`), NOT in the
  code folder (the ZIP is re-downloaded each time), and is never committed to Git.
