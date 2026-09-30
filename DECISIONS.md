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
