"""Step 5 of SPEC.md: spending by category, this cycle vs the 6-cycle average."""
from fintrack.store import item_key as store_item_key
from fintrack.categories import category_for, guess_category
from fintrack.paydayrule import matches_rule


def category_spending(cycles, items=None, categories=None, rules=None, window=6, oneoff_limit=1000.0) -> dict:
    """Summarize spending by category: this cycle vs the window-cycle average.

    Args:
        cycles: list[Cycle] - the payday cycles
        items: dict - item_key -> {"kind": str, "label": str, ...}, from fintrack.store.get_items()
        categories: dict - item_key -> category_name, from fintrack.store.get_categories()
        rules: list[dict] - payday transfer rules, from fintrack.store.get_rules()
        window: int - how many complete cycles to use for the average (default 6)
        oneoff_limit: float - transaction >= this amount (unanswered) is a one-off (default 1000.0)

    Returns:
        dict with keys:
        - cycles_used: how many complete cycles were used (0 if not enough finished cycles)
        - now_start: start date of the now cycle (None if no cycles)
        - now_complete: whether the now cycle is complete
        - rows: list of dicts {"category", "now", "avg", "diff", "labels": [{"label", "now", "avg", "diff"}, ...]}
                sorted by diff biggest first (ties: category name), labels sorted the same way
    """
    if items is None:
        items = {}
    if categories is None:
        categories = {}
    if rules is None:
        rules = []

    # If no cycles, return early
    if not cycles:
        return {
            "cycles_used": 0,
            "now_start": None,
            "now_complete": False,
            "rows": []
        }

    # Get the now cycle (last cycle, which may be incomplete)
    now_cycle = cycles[-1]

    # Get complete cycles
    complete_cycles = [c for c in cycles if c.complete]

    # Not enough finished cycles
    if len(complete_cycles) == 0:
        return {
            "cycles_used": 0,
            "now_start": now_cycle.start,
            "now_complete": now_cycle.complete,
            "rows": []
        }

    # Take the last window complete cycles
    window_cycles = complete_cycles[-window:]
    cycles_used = len(window_cycles)

    # Build spending data: dict of category -> { label -> {"now": x, "avg": x} }
    spending = {}

    # Process the now cycle
    for txn in now_cycle.txns:
        if txn.amount >= 0:  # Ignore money in
            continue

        # Find label and category
        label, category = _get_label_and_category(txn, items, categories, rules, now_cycle, oneoff_limit)

        if label is None or category is None:  # Skip one-offs
            continue

        if category not in spending:
            spending[category] = {}
        if label not in spending[category]:
            spending[category][label] = {"now": 0.0, "avg": 0.0}

        spending[category][label]["now"] += abs(txn.amount)

    # Process the window cycles (for averages)
    for cycle in window_cycles:
        for txn in cycle.txns:
            if txn.amount >= 0:  # Ignore money in
                continue

            # Find label and category
            label, category = _get_label_and_category(txn, items, categories, rules, cycle, oneoff_limit)

            if label is None or category is None:  # Skip one-offs
                continue

            if category not in spending:
                spending[category] = {}
            if label not in spending[category]:
                spending[category][label] = {"now": 0.0, "avg": 0.0}

            spending[category][label]["avg"] += abs(txn.amount)

    # Compute averages and diffs
    for category_data in spending.values():
        for label_data in category_data.values():
            label_data["avg"] = label_data["avg"] / cycles_used if cycles_used > 0 else 0.0
            label_data["diff"] = label_data["now"] - label_data["avg"]

    # Build rows
    rows = []
    for category, labels_dict in spending.items():
        # Sum by category
        now_total = sum(l["now"] for l in labels_dict.values())
        avg_total = sum(l["avg"] for l in labels_dict.values())
        diff_total = now_total - avg_total

        # Build label rows, sorted by diff (biggest first), ties: label name
        label_rows = []
        for label, data in labels_dict.items():
            label_rows.append({
                "label": label,
                "now": data["now"],
                "avg": data["avg"],
                "diff": data["diff"]
            })

        label_rows.sort(key=lambda r: (-r["diff"], r["label"]))

        rows.append({
            "category": category,
            "now": now_total,
            "avg": avg_total,
            "diff": diff_total,
            "labels": label_rows
        })

    # Sort rows by diff (biggest first), ties: category name
    rows.sort(key=lambda r: (-r["diff"], r["category"]))

    return {
        "cycles_used": cycles_used,
        "now_start": now_cycle.start,
        "now_complete": now_cycle.complete,
        "rows": rows
    }


def _get_label_and_category(txn, items, categories, rules, cycle, oneoff_limit):
    """Helper to get label and category for a transaction, or (None, None) if it should be skipped."""
    key = store_item_key(txn)

    # Check if covered by a rule with kind "common"
    if rules:
        for rule in rules:
            if rule["kind"] == "common" and matches_rule(txn, rule, cycle.start):
                label = rule.get("label") or rule.get("payer", "")
                category = guess_category(label)
                return label, category

    # Check if it's a one-off or yearly bill
    if key in items:
        if items[key]["kind"] in ("oneoff", "yearly"):
            return None, None  # Skip

    # Check if unanswered and >= oneoff_limit
    if key not in items and abs(txn.amount) >= oneoff_limit:
        return None, None  # Skip

    # Get label
    if key in items and items[key].get("label"):
        label = items[key]["label"]
    else:
        # Use key's reference part if non-empty, else name part, in Title Case
        parts = key.split("|")
        if len(parts) >= 3 and parts[2]:  # reference part
            label = " ".join(w.capitalize() for w in parts[2].split())
        elif len(parts) >= 2:  # name part
            label = " ".join(w.capitalize() for w in parts[1].split())
        else:
            label = "Unknown"

    # Get category
    saved_category = categories.get(key, "")
    category = category_for(key, label, saved_category)

    return label, category


def format_categories(res) -> list[str]:
    """Format spending by category as a list of plain-ASCII strings."""
    if res["cycles_used"] == 0:
        return ["SPENDING BY CATEGORY: not enough finished paydays yet."]

    now_start = res["now_start"]
    now_complete = res["now_complete"]
    cycles_used = res["cycles_used"]
    rows = res["rows"]

    lines = []

    # Header
    cycle_word = "1-cycle" if cycles_used == 1 else f"{cycles_used}-cycle"
    cycle_text = "this cycle," if now_complete else "this cycle so far,"
    start_str = now_start.strftime("%d %b %Y")
    header = f"SPENDING BY CATEGORY   ({cycle_text} from {start_str}, vs the {cycle_word} average)"
    lines.append(header)

    # Column header
    lines.append(f"     {'Category':<24}{'Now':>10}{'Avg':>10}{'+/-':>10}")

    # Category rows
    for n, row in enumerate(rows, start=1):
        now_str = _format_money(row["now"])
        avg_str = _format_money(row["avg"])
        diff_str = _format_diff(row["diff"])
        lines.append(f"  {n}  {row['category']:<24}{now_str:>10}{avg_str:>10}{diff_str:>10}")

    # Footer
    lines.append("  To see what is inside one:  run.py cat 1")

    return lines


def format_category_detail(res, n) -> list[str]:
    """Format details of a specific category as a list of plain-ASCII strings."""
    rows = res.get("rows", [])

    # Check if n is valid (1-indexed)
    if n < 1 or n > len(rows):
        return [f"There is no category {n}. Pick 1 to {len(rows)}."]

    row = rows[n - 1]
    category = row["category"]
    labels = row["labels"]
    now_complete = res.get("now_complete", False)

    lines = []

    # Header
    cycle_text = "this cycle" if now_complete else "this cycle so far"
    lines.append(f"{category.upper()}   ({cycle_text} vs the {res['cycles_used']}-cycle average)")

    # Column header
    lines.append(f"     {'Label':<24}{'Now':>10}{'Avg':>10}{'+/-':>10}")

    # Label rows
    for label_row in labels:
        now_str = _format_money(label_row["now"])
        avg_str = _format_money(label_row["avg"])
        diff_str = _format_diff(label_row["diff"])
        lines.append(f"     {label_row['label']:<24}{now_str:>10}{avg_str:>10}{diff_str:>10}")

    return lines


def _format_money(amount: float) -> str:
    """Format a money amount as 'XXX.XX' (2 decimals, no thousands commas)."""
    return f"{amount:.2f}"


def _format_diff(diff: float) -> str:
    """Format a diff amount: '+' when > 0.005, '-' otherwise, '0.00' when rounds to zero."""
    rounded = round(diff, 2)

    # Handle zero
    if rounded == 0.0:
        return "0.00"

    # Add sign
    if rounded > 0:
        return f"+{rounded:.2f}"
    else:
        return f"{rounded:.2f}"
