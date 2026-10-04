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
- **Subscription spotter:** card payments, about one a month, of 50 or less, at set prices (each price
  paid at least twice, so a price change is fine: HP Instant Ink 2.99 -> 3.99 -> 1.49), in 3+ months and in at least
  60% of the months of their run, and the set prices make up 60%+ of those months (a shop with a few round amounts is not one). "a month" shows the latest price.
  Still paying = paid in the last 45 days of the statements; otherwise stopped.
- **Rent question:** an answer of more than 3 words / 25 characters is a sentence, not a label: asked once more, then skipped.

## 3 Oct 2026: spare cash = pay - bills (user)
- SPARE CASH = pay - bills (last month's amounts). Left over (balance before payday) is NOT added; it was a month
  stale when the newest statement ends before the latest payday. "If you spend like usual" is dropped from the
  terminal and the home page. Typed spends then come off the spare cash ("Left now").
- Payments made just before payday can be counted from that payday: `run.py early N`.

## 3 Oct 2026: DD / SO are bills by default (user)
- A direct debit or standing order paid in 2+ months, with no saved answer, is saved as Common (a bill) without a
  question (`questions.auto_bills`, source "auto"). Paid only once: still asked. Saved answers are never changed.
  Change one with `run.py fix`.

## 4 Oct 2026: phone copy (user, grill session)
- PC = final say. Phone changes only happen on the PC after the user says yes (Enter = all).
- PIN (not a password). PythonAnywhere free (log in there once every 3 months). Phone = spends only.
- Two files online: the PC's copy (only the PC writes it) and the phone's changes (only the phone writes them).
- PC uploads on start and after every change. Phone: changes count straight away, sent with one Send button.

## 4 Oct 2026: new and stopped bills (user)
- Every DD / SO goes straight into Bills, even when paid only once, marked "🆕 new" until it has been paid in 2 pay
  cycles (the user can tap Yearly / One-off if it is not monthly). A new bill shows as soon as it is paid, also in the
  pay cycle still running (Zopa was hidden because of that).
- A bill not paid in the last finished pay cycle = stopped: shown as stopped and NOT counted in the bills total any more
  (e.g. the old car insurance after a switch). The user can also tap "Stopped" on a bill to drop it sooner.
- A new bill's first payment counts as paid (e.g. a bigger first month); the ✏️ this-month change still works.
- Card payments are never auto-bills: a deposit or pay-in-full by card is asked about as a new item (One-off / Yearly).
