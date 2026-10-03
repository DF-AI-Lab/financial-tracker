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

- Payday transfer rule (rent by transfer): within 2 days of payday, about the usual amount (10%), asked once with examples, remembered; a new price is noticed after 2 payments
- `all` answer and skipping tiny one-offs in the question list

## Next up
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

## Ideas for v2 (3 Oct, user)
- **Typed spends: full wipe on a new PDF.** v1 (now): typed spends that match the statement are removed,
  others are asked about, ones after the statement's last day stay. Idea: wipe them all when the next
  statement goes in. Open question: wipe at the statement's end date or at payday? Payday makes most sense
  but varies (end of the month), and a statement end date can fall after the next payday.
  **User's answer (3 Oct):** tie it to the pay box. When a new pay is typed in (home page or `run.py`), ask
  "New pay. Clear your typed spends? y/n". Typing the pay = "I got paid", so no date guessing. It is a question,
  not automatic, so fixing a typo in the pay does not wipe anything.
- **Home page order (user, 3 Oct):** 1 This month's pay, 2 Add a spend, 3 Bills, 4 Subscriptions,
  5 Where did last cycle's money go?, then the rest (Last month's spending, Spending by category,
  6 / 12 months / this year). Only `templates/home.html` changes (cards move, nothing else).
- **Easier question list (user, 3 Oct):** after showing the 10 items, ask one question at a time:
  "Which are Common? (numbers)" -> "Which are One-off?" -> "Which are Yearly?" -> the rest are Random.
  Then "Any categories to change?" Enter = skip each step. No keywords to remember.
