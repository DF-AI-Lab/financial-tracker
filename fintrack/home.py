"""Step 9 of SPEC.md: the home page data aggregation."""
from datetime import date
from typing import Optional

from fintrack.cycles import build_cycles
from fintrack.common import analyse
from fintrack.spare import pay_block, last_cycle_check
from fintrack.where import where_did_it_go, where_summary
from fintrack.bycategory import category_spending
from fintrack.subs import find_subscriptions
from fintrack.sparehist import spare_history
from fintrack.picture import six_month_picture
from fintrack.yearly import yearly_due
from fintrack.periods import period_totals
from fintrack.store import load_txns, get_items, get_rules, get_categories, get_spends, get_value


def home_data(conn, wage_payer, wage=None, today=None) -> dict:
    """Load and aggregate all data for the home page.

    Args:
        conn: sqlite3 connection
        wage_payer: the wage payer name (e.g. "ACME MOTORS PLC")
        wage: optional fixed wage; if None, uses saved "pay" value or last cycle wage
        today: optional reference date; if None, uses max transaction date

    Returns:
        dict with ready=False if no data, else dict with all page data
    """
    # Load all the data
    from fintrack.early import load_moved
    from fintrack.wages import all_payers
    txns = sorted(load_moved(conn, all_payers(conn, wage_payer)), key=lambda t: t.date)

    if not txns:
        return {"ready": False}

    from fintrack.wages import all_payers
    cycles = build_cycles(txns, payer=all_payers(conn, wage_payer))
    answers = get_items(conn)
    rules = get_rules(conn)
    categories = get_categories(conn)

    analysis = analyse(cycles, answers=answers, rules=rules)

    # Check if we have enough data
    if not cycles or analysis.cycles_used == 0:
        return {"ready": False}

    # Determine wage
    if wage is None:
        saved_wage = get_value(conn, "pay")
        if saved_wage is not None:
            try:
                wage = float(saved_wage)
            except (ValueError, TypeError):
                wage = cycles[-1].wage
        else:
            wage = cycles[-1].wage

    # Determine today
    if today is None:
        today = max(t.date for t in txns)

    # Get yearly due
    due = yearly_due(txns, answers, today=today)

    # Build the pay block
    from fintrack.billchange import get_changes
    pay = pay_block(cycles, analysis, wage, categories=categories, items=answers, yearly=due,
                    changes=get_changes(conn, cycles[-1].start))

    # Get last cycle check
    last = last_cycle_check(cycles, answers=answers, rules=rules)

    # Get where did it go
    where = None
    if last is not None:
        w = where_did_it_go(cycles, answers=answers, rules=rules, categories=categories, items=answers)
        where = where_summary(w)

    # Get spending by category
    cats = category_spending(cycles, items=answers, categories=categories, rules=rules)

    # Get subscriptions
    subs = find_subscriptions(txns, items=answers)

    # Get typed spends
    spends = get_spends(conn)

    # Get money for spending
    money = pay["spare"]                     # pay - bills, with any bill changed for this cycle

    # Calculate left_now
    left_now = money - sum(s["amount"] for s in spends)

    # Get picture
    picture = six_month_picture(cycles, analysis, items=answers, categories=categories)

    # Get statements_to (max transaction date)
    statements_to = max(t.date for t in txns)

    # Get periods data
    periods = period_totals(cycles, answers=answers, rules=rules)

    return {
        "ready": True,
        "pay": pay,
        "last": last,
        "where": where,
        "categories": cats,
        "subs": subs,
        "spends": spends,
        "money_for_spending": money,
        "left_now": left_now,
        "typed_total": money - left_now,
        "cycle_start": cycles[-1].start,
        "history": spare_history(cycles, analysis),
        "picture": picture,
        "statements_to": statements_to,
        "periods": periods
    }
