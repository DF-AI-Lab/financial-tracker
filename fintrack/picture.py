"""Six-month spending picture: wage, bills, random spending, and unsorted categories."""
from statistics import mean


def six_month_picture(cycles, analysis, items=None, categories=None, window=6):
    """Summarize the last N complete cycles as a six-month spending picture.

    Args:
        cycles: list[Cycle] - the payday cycles
        analysis: Analysis - the output of fintrack.common.analyse()
        items: dict - item_key -> {"label": str, ...}, from fintrack.store.get_items()
        categories: dict - item_key -> category_name, from fintrack.store.get_categories()
        window: int - how many complete cycles to look at (default 6)

    Returns:
        dict with keys:
        - cycles_used: how many complete cycles were used
        - wage_avg: mean wage over the last window complete cycles
        - bills_avg: analysis.common_per_cycle
        - normal_avg: analysis.random_per_cycle
        - oneoffs_total: sum of abs(amount) from analysis.one_offs
        - unsorted_avg: average of unsorted money-out txns in those cycles
        - bills: list of dicts {"name": str, "type": str, "avg": float, "last": float or None, "stopped": bool}
        - other_regular: list of dicts (same shape)
    """
    if items is None:
        items = {}
    if categories is None:
        categories = {}

    # Filter to complete cycles and take the last window
    complete_cycles = [c for c in cycles if c.complete]
    if not complete_cycles:
        return {
            "cycles_used": 0,
            "wage_avg": 0.0,
            "bills_avg": 0.0,
            "normal_avg": 0.0,
            "oneoffs_total": 0.0,
            "unsorted_avg": 0.0,
            "bills": [],
            "other_regular": []
        }

    window_cycles = complete_cycles[-window:]
    cycles_used = len(window_cycles)

    # Wage average
    wage_avg = mean(c.wage for c in window_cycles) if window_cycles else 0.0

    # Oneoffs total
    oneoffs_total = sum(abs(t.amount) for t in analysis.one_offs)

    # Unsorted average: money-out txns not in one_offs whose category is "Unsorted".
    # With no saved label, the reference (e.g. "RENT") helps the guess.
    from fintrack.store import item_key as store_item_key
    from fintrack.categories import category_for

    one_off_ids = set(id(t) for t in analysis.one_offs)
    unsorted_total = 0.0
    for cycle in window_cycles:
        for txn in cycle.txns:
            if txn.amount < 0 and id(txn) not in one_off_ids:  # Money out, not one-off
                key = store_item_key(txn)
                if key in items:
                    label = items[key].get("label", "")
                else:
                    label = key.split("|")[2]
                cat = category_for(key, label, categories.get(key, ""))
                if cat == "Unsorted":
                    unsorted_total += abs(txn.amount)

    unsorted_avg = unsorted_total / cycles_used if cycles_used > 0 else 0.0

    # Build bills and other_regular lists
    bills = []
    other_regular = []

    for key, entry in analysis.common.items():
        row = {
            "name": key,
            "type": entry.get("type", ""),
            "avg": entry["average"],
            "last": entry["last"] if entry["last"] > 0 else None,
            "stopped": entry["last"] == 0
        }

        if entry["kind"] == "bill":
            bills.append(row)
        else:
            other_regular.append(row)

    # Sort by avg, biggest first
    bills.sort(key=lambda r: r["avg"], reverse=True)
    other_regular.sort(key=lambda r: r["avg"], reverse=True)

    return {
        "cycles_used": cycles_used,
        "wage_avg": wage_avg,
        "bills_avg": analysis.common_per_cycle,
        "normal_avg": analysis.random_per_cycle,
        "oneoffs_total": oneoffs_total,
        "unsorted_avg": unsorted_avg,
        "bills": bills,
        "other_regular": other_regular
    }


def _show_type(t):
    """The payment type as shown: card payments ("VIS", contactless ")))") show as CARD."""
    return "CARD" if t in ("VIS", ")))") else t


def format_picture(p):
    """Format a six-month picture as a list of plain-ASCII strings.

    Args:
        p: dict - the output of six_month_picture()

    Returns:
        list[str] - ASCII lines suitable for printing to the Windows terminal
    """
    if p["cycles_used"] == 0:
        return ["SIX-MONTH PICTURE: not enough finished paydays yet."]

    cycle_word = "1 cycle" if p["cycles_used"] == 1 else f"{p['cycles_used']} cycles"
    lines = []

    # Header
    lines.append(f"SIX-MONTH PICTURE (based on {cycle_word})")

    # Summary block
    lines.append(f"  {'Wage (average)':<38}{p['wage_avg']:>10,.2f}")
    lines.append(f"  {'Bills (average)':<38}{p['bills_avg']:>10,.2f}")
    lines.append(f"  {'Normal spending (average)':<38}{p['normal_avg']:>10,.2f}")
    lines.append(f"  {'One-offs (not counted)':<38}{p['oneoffs_total']:>10,.2f}")
    lines.append(f"  {'Unsorted (average)':<38}{p['unsorted_avg']:>10,.2f}")

    # Bills section
    if p["bills"]:
        lines.append("")
        lines.append(f"{'BILLS':<40}{'6-mth avg':>10}   {'Last month':>10}")
        for row in p["bills"]:
            last_str = f"{row['last']:>10,.2f}" if row['last'] is not None else "         -"
            stopped_str = "  STOPPED?" if row['stopped'] else ""
            label = f"{row['name']} ({_show_type(row['type'])})"
            lines.append(f"  {label:<38}{row['avg']:>10,.2f}   {last_str}{stopped_str}")

    # Other regular section
    if p["other_regular"]:
        lines.append("")
        lines.append(f"{'OTHER REGULAR':<40}{'6-mth avg':>10}   {'Last month':>10}")
        for row in p["other_regular"]:
            last_str = f"{row['last']:>10,.2f}" if row['last'] is not None else "         -"
            stopped_str = "  STOPPED?" if row['stopped'] else ""
            label = f"{row['name']} ({_show_type(row['type'])})"
            lines.append(f"  {label:<38}{row['avg']:>10,.2f}   {last_str}{stopped_str}")

    return lines
