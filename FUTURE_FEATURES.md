# Future features

_Ideas agreed but not built yet. Newest at the bottom._

## Built (30 Sep, with tests)
- Payday-to-payday cycles (wage = VERTU MOTORS PLC, 500 or more; a second credit within 10 days is a bonus in the same cycle)
- Common / random / one-off split over the last 6 complete cycles (bills: 4 of 6 cycles; others: 4 of 6 within 15%; one-off: 1,000 or more and not common)
- "Latest pay?" question at the end of `run.py` (Enter = last wage) showing what is left

## Next up
- **Overrides:** let the user say "this is common" / "this is a one-off" for a payment or payer,
  and remember it (needs the database).
- **Missing statements warning:** if one statement does not start where the last one ended,
  say which month is missing (cycles across a gap are wrong).
- **"Same bill?" question:** when two bill names look similar (for example CAR LOAN PAYMENT
  and CAR PAYMENT OWED), ask the user once and remember the answer. Build the database with a
  place to store these answers.
- **"Off by X" marker:** when a statement's balance check is off by a small amount, keep the
  CHECK warning and show how much it is off by.

## Also planned
- SQLite database with categories (see DECISIONS.md for the starter list)
- 6-month average per category
- Type in this month's wage, then see spare cash and spending so far
- Fetch statement PDFs from email automatically
- Side income and bonus tracking
- Other banks
