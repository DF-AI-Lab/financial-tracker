# Future features

_Ideas agreed but not built yet. Newest at the bottom._

## Built (30 Sep, with tests)
- Payday-to-payday cycles (wage = VERTU MOTORS PLC, 500 or more; a second credit within 10 days is a bonus in the same cycle)
- Common / random / one-off split over the last 6 complete cycles (bills: 4 of 6 cycles; others: 4 of 6 within 15%; one-off: 1,000 or more and not common)
- "Latest pay?" question at the end of `run.py` (Enter = last wage) showing what is left

- SQLite database (`tracker.db` next to the statements folder): statements and payments stored once, duplicates skipped
- Confirm-as-you-go questions (10 at a time; `common 1 2`, `oneoff 3`, `label 1 Rent`, `later`, `stop`), saved answers, and `run.py fix`
- Your answers decide common / random / one-off; items with the same label merge
- `run.py folder "C:\path"` remembers the statements folder

## Next up
- **Payday transfer rule (rent by transfer):** a bill payment to the same person is counted as rent (Common)
  when it is paid within 2 days of payday AND the amount is within 10% of the usual amount (the app finds the usual
  amount itself), whatever the reference says (the reference is sometimes forgotten). Small top-ups stay Random.
  Asked once per person with examples first ("count these as Common, label Rent? y/n") and remembered.
  If rent jumps by more than 10% it asks again.
- **Categories report:** totals per label (Rent, Gas & Electric...) month by month and the 6-cycle average
  per label (the labels are already saved by the questions).
- **Missing statements warning:** if one statement does not start where the last one ended,
  say which month is missing (cycles across a gap are wrong).
- **"Same bill?" question:** when two bill names look similar (for example CAR LOAN PAYMENT
  and CAR PAYMENT OWED), ask the user once and remember the answer. Build the database with a
  place to store these answers.
- **"Off by X" marker:** when a statement's balance check is off by a small amount, keep the
  CHECK warning and show how much it is off by.

## Also planned
- Spending so far in the current cycle vs the typical cycle
- Fetch statement PDFs from email automatically
- Side income and bonus tracking
- Other banks
