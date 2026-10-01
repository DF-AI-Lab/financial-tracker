# Spec: Where does my wage go?

_Written 1 Oct 2026 from the wayfinder map: https://github.com/DF-AI-Lab/financial-tracker/issues/1
(each decision's detail is in its ticket). `DECISIONS.md` still wins if anything disagrees._

**What this adds:** a six-month picture, expected vs actual spare, and "where did the missing spare go?".
**How:** build on the existing app (154 passing tests). Terminal first, home page last.
**Rules for every step:** tests first (fake data only), all old tests still pass (or are updated only where this
spec changes a rule), never commit PDFs or `.db` files, saved answers in `tracker.db` keep working.

---

## Words used
- **Cycle** = payday to payday (wage = VERTU MOTORS PLC, as now).
- **Label** = one thing (Rent, Tesco). **Category** = a group of labels, bills included
  (🏠 Household, 🚗 Car incl. fuel, 🛒 Food shopping, 📺 Subscriptions, ❓ Unsorted...). No fixed list.
- **Bills** = Direct Debits + Standing Orders + Common items (as `DECISIONS.md` says now).
- **Normal spending** = everything else going out, without one-offs and yearly bills.
- **Money moved out** = the Savings/Transfers category.

---

## Step 1: Same bill, different name  ([ticket](https://github.com/DF-AI-Lab/financial-tracker/issues/11))
- `store.item_key`: for **DD**, ignore the reference completely (today only "FIRST PAYMENT" is ignored).
  SO and BP keep the reference (Katie RENT / BILLS / FOOD stay separate).
- Names that are only **similar** (e.g. CAR LOAN PAYMENT / CAR PAYMENT OWED): the question list asks
  **"Same bill? y/n"** once and remembers it (new table, e.g. `same_as(key, main_key)`). Changeable in `fix`.
- Existing saved items whose DD key changes must keep their answer (move it to the new key).

## Step 2: Categories  ([ticket](https://github.com/DF-AI-Lab/financial-tracker/issues/5))
- `items` gets a **category**. Starter list = the one in `DECISIONS.md`, grouped as above; new ones can be typed any time.
- The question list **suggests** a category from the name (TESCO → Food shopping); Enter accepts, as now.
- Payments with no category count as **Unsorted** (its own total).

## Step 3: Yearly bills  ([ticket](https://github.com/DF-AI-Lab/financial-tracker/issues/10))
- New answer in the question list: **`yearly 3`** → item kind "yearly". "No" = a normal one-off.
- Yearly bills are not in monthly bills or averages. From **11 months after** the last payment, show:
  `⚠️ Possible yearly bill: AVIVA £180, paid Oct 2025`.

## Step 4: Six-month picture  ([ticket](https://github.com/DF-AI-Lab/financial-tracker/issues/4))
Last 6 complete cycles; with fewer, use what's there and say "based on N cycles".
```
SIX-MONTH PICTURE   (based on 6 cycles)
Wage (average)            £2,700      Vertu wage only
Bills (average)           £1,450
Normal spending (avg)       £500      no one-offs
One-offs (not counted)      £320
Unsorted                     £42

BILLS                 6-mth avg   Last month
Rent      SO            £550        £550
Gas/Elec  DD             £82         £95
TV licence DD            £13         —      ⚠️ stopped?

OTHER REGULAR (card)    6-mth avg   Last month
Netflix                  £11         £11
Fuel                    £160        £148     (several payments added up per cycle)
```
- A bill missing from the last cycle stays listed with **⚠️ stopped?**.
- No "how often" column.

## Step 5: Spending by category  ([ticket](https://github.com/DF-AI-Lab/financial-tracker/issues/5))
One row per category: **Now | Avg | +/−** (this cycle vs 6-cycle average), biggest over-spend first.
Each category opens to show its labels with the same columns (terminal: `cat 2`; page: tap).

## Step 6: Expected / actual / missing  ([ticket](https://github.com/DF-AI-Lab/financial-tracker/issues/6))
Replaces the "Latest pay?" block (`fintrack/left.py`). Wage is typed in (Enter = last wage), as now.
```
  Left over from last month    £200    balance just before this payday
+ Wage                       £2,700
− Bills                      £1,450    LAST MONTH's amount of each bill; stopped? bills still counted
− Normal spending              £500    6-cycle average
= Expected spare               £950
⚠️ Possible yearly bill: AVIVA £180 → expected spare if it's paid: £770

At the end of the cycle (next payday):
  Left over + wage + other money in − all money out = Actual spare £510  (= end balance)
  Missing = expected − actual = £440
```

## Step 7: Where did it go?  ([ticket](https://github.com/DF-AI-Lab/financial-tracker/issues/7), [good month](https://github.com/DF-AI-Lab/financial-tracker/issues/12))
```
WHERE DID THE £440 GO?
 1. One-off: CURRYS                 £299   (12 Oct)
 2. Food shopping over normal       £180   (£480 vs usual £300)
 3. Moved out: to savings           £100   (usually £0)
 4. Gas/Elec went up                 £13   (£95 vs £82 last month)
 5. Small bits (under £20 each)      £28
    Spent LESS than normal:         −£120  (Fuel −£40, Takeaways −£80)
    Other money in                   −£60
    Adds up to                      £440 ✅
```
- Reasons: one-offs (full amount); category over its 6-cycle average (non-bill spending only);
  money moved out over its average; bill went up vs last month (new bill = full amount).
- Nothing counted twice. Biggest first, at most 5 lines, anything under £20 → "Small bits".
- **The lines always add up to the gap.** `show 2` lists the payments behind line 2.
- **Good month** (actual > expected): same breakdown, flipped: "👍 Where did the extra £150 come from?".

## Step 8: Typed spends as you go  ([ticket](https://github.com/DF-AI-Lab/financial-tracker/issues/14))
- Add a spend: amount + name (terminal: `run.py add 150 Argos TV`). Category optional (guessed from the name).
- **Left now** = left over + wage − bills − typed spends so far.
- When the statement arrives: each typed spend is matched to a real payment (same amount, within a few days)
  and removed. Any it can't match, it asks about.

## Step 9: Home page  ([layout](https://github.com/DF-AI-Lab/financial-tracker/issues/8), [how it runs](https://github.com/DF-AI-Lab/financial-tracker/issues/3), [terminal vs page](https://github.com/DF-AI-Lab/financial-tracker/issues/13))
- Flask, on your own PC only (127.0.0.1), started by double-clicking `start.bat`, which opens the browser.
- Looks like `prototype/home.html`, top to bottom: 3 tiles (Expected | Actual | Missing) → yearly warning →
  where did it go (tap to open) → this month's pay (wage box) → spending by category (tap to open) →
  add a spend → drop PDFs → bills → other regular → six-month picture.
- Shows the same numbers as the terminal. Phone width with no sideways scroll; light and dark mode.
- The terminal stays as a backup; the questions stay in the terminal for now.

---

## Not in this spec
Other banks, email fetching, logins, CSV import, warnings/nudges ("£100 over on food with 10 days to go").
