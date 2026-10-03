# Decisions

> **1 Oct 2026:** the new plan (six-month picture, expected vs actual spare, where did it go, categories as
> groups, yearly bills, same-bill merging, typed spends, home page) is agreed in `SPEC.md`.

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
- **One word: Common.** "Regular" and "Common" counted the same, so there is only Common now (typing `regular`
  still works and means Common). Kinds are Common / Random / One-off.
- **Suggestions by type:** standing orders and direct debits suggest Common; bill-payment top-ups (BP) always
  suggest Random; cards and cash suggest Common when 4 or more payments are within 15% of the usual amount, a single
  payment of 1,000 or more suggests One-off, otherwise Random.
- **Payday transfer rule (rent by transfer).** A bill payment to the same person is counted as Common (label e.g. "Rent")
  when it is paid within 2 days of payday AND within 10% of the usual amount, whatever the reference says. The app
  finds the usual amount itself, asks once with examples (y / n / type another label) and remembers the answer. Payments
  under 100 (top-ups) never trigger it. A new price (more than 10% off) is asked about again after 2 payments.
  The rule beats the item answers, and a covered payment is never a one-off.
- **Question list shortcuts:** `all` keeps the suggestions for everything left; items with 2 or fewer payments under 50
  in total are never asked about.


- **Pay block (3 Oct 2026, the user's own layout).** After typing the pay: every-month bills (6-mth avg | last month),
  then SPARE CASH = left over + pay - bills (last month's amounts) = **the No. 1 number**, then last month's spending
  that is not bills by category (last month | 6-mth avg), then "if you spend like usual, left". Then subscriptions.
- **Subscription spotter:** card payments of 50 or less in 3+ different months at about the same price (5%), paid in at
  least 60% of the months of their run (so a shop now and then is not one).
  Still paying = paid in the last 45 days of the statements; otherwise stopped.
- **Rent question:** an answer of more than 3 words / 25 characters is a sentence, not a label: asked once more, then skipped.
