# Future features

_Ideas agreed but not built yet. Newest at the bottom._

## Next up (after the database exists)
- **Common vs one-off:** a payment is *common* if the same payer appears in most of the
  last 6 months with a similar amount. Large, rare payments (car payoff, family money) are
  *one-offs* and stay out of the averages. The user can override it, and the app remembers.
- **Payday-to-payday months:** a "month" runs from one wage arrival (VERTU MOTORS PLC) to
  the next, instead of the bank's 23rd to 22nd. The cycle resets on the real wage date.
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
