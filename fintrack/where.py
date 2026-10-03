"""Step 7 of SPEC.md: "Where did it go?" for the last finished cycle."""
from datetime import date
from typing import Optional, List

from fintrack.models import Cycle, Txn
from fintrack.common import analyse
from fintrack.spare import last_cycle_check
from fintrack.bycategory import label_and_category


def where_did_it_go(cycles: List[Cycle], answers: Optional[dict] = None, rules: Optional[list] = None,
                    categories: Optional[dict] = None, items: Optional[dict] = None) -> Optional[dict]:
    """Analyse where the missing money in the last finished cycle went.

    Returns dict with keys: "start", "end", "missing", "reasons" or None if not enough data.
    Each reason is a dict with keys: "kind", "name", "amount", "now", "usual", "txns", and "date" (for one-offs).
    """
    if answers is None:
        answers = {}
    if rules is None:
        rules = []
    if categories is None:
        categories = {}
    if items is None:
        items = {}

    # Get the last cycle check
    c = last_cycle_check(cycles, answers=answers, rules=rules)
    if c is None:
        return None

    # Find target cycle (the last complete cycle)
    complete_cycles = [cy for cy in cycles if cy.complete]
    if not complete_cycles:
        return None

    target_idx = None
    for i, cy in enumerate(cycles):
        if cy.complete and cy is complete_cycles[-1]:
            target_idx = i
            break

    if target_idx is None or target_idx == 0:
        return None

    target = cycles[target_idx]

    # Analyse before and after
    before = analyse(cycles[:target_idx], answers=answers, rules=rules)
    after = analyse(cycles[:target_idx + 1], answers=answers, rules=rules)

    # Build target_ids set
    target_ids = set(id(t) for t in target.txns)

    reasons = []

    # --- One-offs ---
    for txn in after.one_offs:
        if id(txn) in target_ids:
            # Get label from answers
            from fintrack.store import item_key
            key = item_key(txn)
            if key in answers and answers[key].get("label"):
                name = answers[key]["label"]
            else:
                name = txn.description

            if abs(txn.amount) >= 0.005:
                reasons.append({
                    "kind": "oneoff",
                    "name": name,
                    "amount": -txn.amount,
                    "now": -txn.amount,
                    "usual": 0.0,
                    "txns": [txn],
                    "date": txn.date
                })

    # --- Bills ---
    for key in set(list(before.common.keys()) + list(after.common.keys())):
        usual = 0.0
        if key in before.common:
            entry = before.common[key]
            usual = entry["last"] if entry["last"] > 0 else entry["average"]

        now = 0.0
        if key in after.common:
            now = after.common[key]["last"]

        amount = now - usual

        if abs(amount) >= 0.005:
            # Get txns from after.common_txns for this key that are in target
            bill_txns = [t for t in after.common_txns.get(key, []) if id(t) in target_ids]

            reasons.append({
                "kind": "bill",
                "name": key,
                "amount": amount,
                "now": now,
                "usual": usual,
                "txns": bill_txns
            })

    # --- Categories (random spending grouped by category) ---
    before_random = before.random_txns
    now_random = [t for t in after.random_txns if id(t) in target_ids]

    # Group by category
    category_groups = {}

    # Group before_random by category
    for txn in before_random:
        label, category = label_and_category(txn, items, categories, [], None, 1000.0)
        if label is not None and category is not None:
            if category not in category_groups:
                category_groups[category] = {"before": [], "now": []}
            category_groups[category]["before"].append(txn)

    # Group now_random by category
    for txn in now_random:
        label, category = label_and_category(txn, items, categories, [], None, 1000.0)
        if label is not None and category is not None:
            if category not in category_groups:
                category_groups[category] = {"before": [], "now": []}
            category_groups[category]["now"].append(txn)

    # Calculate amounts for each category
    for category, data in category_groups.items():
        now = sum(-t.amount for t in data["now"])
        usual = sum(-t.amount for t in data["before"]) / before.cycles_used if before.cycles_used > 0 else 0.0
        amount = now - usual

        if abs(amount) >= 0.005:
            kind = "moved" if category == "Savings/Transfers" else "category"
            reasons.append({
                "kind": kind,
                "name": category,
                "amount": amount,
                "now": now,
                "usual": usual,
                "txns": data["now"]
            })

    # --- Other money in ---
    # The amount is last_cycle_check's (all money in minus the wage), so the reasons always add up.
    # The payments behind it (for "show"): money in, minus the wage credits (the payer's credits of 500 or more).
    if abs(c["other_in"]) >= 0.005:
        wage_payer = target.txns[0].description if target.txns and target.txns[0].amount > 0 else None
        other_in_txns = [t for t in target.txns
                         if t.amount > 0 and not (t.description == wage_payer and t.amount >= 500)]
        reasons.append({
            "kind": "other_in",
            "name": "Other money in",
            "amount": -c["other_in"],
            "now": c["other_in"],
            "usual": 0.0,
            "txns": other_in_txns
        })

    return {
        "start": c["start"],
        "end": c["end"],
        "missing": c["missing"],
        "reasons": reasons
    }


def where_summary(w: Optional[dict]) -> Optional[dict]:
    """Extract structured summary from where_did_it_go result for use by both terminal and web.

    Returns None for None, else {"kind": "none" | "missing" | "extra", "amount": abs(missing),
    "lines": [...], "against": [...]}.
    - kind "none" when abs(missing) < 0.005, else "missing" or "extra"
    - lines = the numbered lines: {"n", "text", "value", "note", "txns"}
    - against = the grouped lines: {"text", "value", "note"}
    """
    if w is None:
        return None

    missing = w["missing"]

    # Determine kind
    if abs(missing) < 0.005:
        kind = "none"
    elif missing > 0:
        kind = "missing"
    else:
        kind = "extra"

    # Get numbered and against from _numbered_lines
    numbered, against_reasons = _numbered_lines(w)
    d = 1 if missing > 0 else -1

    # Build lines list
    lines = []
    for n, text, v, note, txns in numbered:
        lines.append({
            "n": n,
            "text": text,
            "value": v,
            "note": note,
            "txns": sorted(txns, key=lambda t: t.date)
        })

    # Build against list (grouped)
    against = []
    if against_reasons:
        against_by_type = {}
        for reason, v in against_reasons:
            kind_key = reason["kind"]

            # Group by type
            if kind_key in ("category", "moved"):
                group_key = "category_moved"
            elif kind_key == "bill":
                group_key = "bill"
            elif kind_key == "other_in":
                group_key = "other_in"
            elif kind_key == "oneoff":
                group_key = "oneoff"
            else:
                group_key = kind_key

            if group_key not in against_by_type:
                against_by_type[group_key] = []
            against_by_type[group_key].append((reason, v))

        # Format groups based on direction
        if d == 1:  # Missing money (money went out)
            order = ["category_moved", "bill", "other_in"]
            group_names = {
                "category_moved": "Spent LESS than normal",
                "bill": "Bills went down",
                "other_in": "Other money in"
            }
        else:  # Extra money (money came in)
            order = ["category_moved", "bill", "oneoff"]
            group_names = {
                "category_moved": "Spent MORE than normal",
                "bill": "Bills went up",
                "oneoff": "One-offs"
            }

        for group_key in order:
            if group_key in against_by_type:
                reasons_in_group = against_by_type[group_key]
                group_v = sum(v for _, v in reasons_in_group)

                # Sort by v most negative first
                reasons_in_group.sort(key=lambda x: x[1])

                # Build note (up to 3 reasons with most negative v first)
                parts = []
                for reason, v in reasons_in_group[:3]:
                    def money(x):
                        return f"{x:,.2f}"
                    parts.append(f"{reason['name']} {money(v)}")

                note_text = ", ".join(parts)
                if len(reasons_in_group) > 3:
                    note_text += ", ..."

                group_name = group_names.get(group_key, group_key)

                if group_key == "other_in":
                    against.append({
                        "text": group_name,
                        "value": group_v,
                        "note": ""
                    })
                else:
                    against.append({
                        "text": group_name,
                        "value": group_v,
                        "note": f"({note_text})"
                    })

    return {
        "kind": kind,
        "amount": abs(missing),
        "lines": lines,
        "against": against
    }


def format_where(w: Optional[dict]) -> List[str]:
    """Format where_did_it_go as a list of plain-ASCII strings (built from where_summary)."""
    s = where_summary(w)
    if s is None:
        return []
    if s["kind"] == "none":
        return ["WHERE DID IT GO?   Nothing missing: the cycle went as expected."]

    def money(x):
        return f"{x:,.2f}"

    dates = f"({w['start']:%d %b %Y} to {w['end']:%d %b %Y})"
    if s["kind"] == "missing":
        lines = [f"WHERE DID THE {money(s['amount'])} GO?   {dates}"]
    else:
        lines = [f"WHERE DID THE EXTRA {money(s['amount'])} COME FROM?   {dates}"]

    for l in s["lines"]:
        line = f"  {l['n']}. {l['text']:<34}{money(l['value']):>10}"
        lines.append(line + (f"   {l['note']}" if l["note"] else ""))
    for a in s["against"]:
        line = f"     {a['text']:<34}{money(a['value']):>10}"
        lines.append(line + (f"   {a['note']}" if a["note"] else ""))

    lines.append(f"     {'-' * 44}")
    lines.append(f"     {'Adds up to':<34}{money(s['amount']):>10}")
    lines.append("  To see the payments behind a line:  run.py show 1")
    return lines


def _numbered_lines(w):
    """([(n, text, v, note, txns)], against) for the numbered lines and the (reason, v) pairs against the gap.

    v = d * amount (d = 1 when money is missing, -1 when there is extra). Reasons with v > 0, biggest first:
    the first up to 4 with v >= 20 get their own line; the rest are lumped into one more line.
    """
    d = 1 if w["missing"] > 0 else -1
    pairs = [(r, d * r["amount"]) for r in w["reasons"]]
    main = sorted([(r, v) for r, v in pairs if v > 0], key=lambda x: (-x[1], x[0]["name"]))
    against = [(r, v) for r, v in pairs if v < 0]

    top, lumped = [], []
    for r, v in main:
        if len(top) < 4 and v >= 20:
            top.append((r, v))
        else:
            lumped.append((r, v))

    numbered = []
    for n, (r, v) in enumerate(top, start=1):
        text, note = _format_reason_text(r, v, d, w["missing"])
        numbered.append((n, text, v, note, list(r.get("txns", []))))
    if lumped:
        text = "Small bits (under 20 each)" if all(v < 20 for _, v in lumped) else "Everything else"
        txns = [t for r, _ in lumped for t in r.get("txns", [])]
        numbered.append((len(top) + 1, text, sum(v for _, v in lumped), "", txns))
    return numbered, against


def _format_reason_text(reason, v, d, missing):
    """Format the text and note for a reason line."""
    def money(x):
        return f"{x:,.2f}"

    kind = reason["kind"]
    name = reason["name"]
    amount = reason["amount"]
    now = reason["now"]
    usual = reason["usual"]

    if kind == "oneoff":
        text = f"One-off: {name}"
        date = reason.get("date")
        if date:
            note = f"({date.day} {date:%b})"
        else:
            note = ""
        return text, note

    elif kind == "bill":
        if amount > 0:
            if usual > 0:
                text = f"{name} went up"
                note = f"({money(now)} vs {money(usual)} last month)"
            else:
                text = f"New bill: {name}"
                note = ""
        else:
            if now > 0:
                text = f"{name} went down"
                note = f"({money(now)} vs {money(usual)} last month)"
            else:
                text = f"{name} not paid this time"
                note = ""
        return text, note

    elif kind == "category":
        if amount > 0:
            text = f"{name} over normal"
            note = f"({money(now)} vs usual {money(usual)})"
        else:
            text = f"{name} under normal"
            note = f"({money(now)} vs usual {money(usual)})"
        return text, note

    elif kind == "moved":
        if amount > 0:
            text = "Moved out (Savings/Transfers)"
            note = f"({money(now)} vs usually {money(usual)})"
        else:
            text = "Moved out less than usual"
            note = f"({money(now)} vs usually {money(usual)})"
        return text, note

    elif kind == "other_in":
        text = "Other money in"
        note = ""
        return text, note

    return "", ""


def show_lines(w: Optional[dict], n: Optional[int]) -> List[str]:
    """Show the transactions behind a numbered line from format_where."""
    if w is None:
        return []

    # Build the numbered lines exactly as format_where does
    missing = w["missing"]
    d = 1 if missing > 0 else -1

    def money(x):
        return f"{x:,.2f}"

    numbered_lines, _ = _numbered_lines(w)

    # Check if n is valid
    if n is None or n < 1 or n > len(numbered_lines):
        count = len(numbered_lines)
        return [f"There is no line {n}. Pick 1 to {count}."]

    # Get the requested line and the payments behind it
    idx, text, v, note, txns = numbered_lines[n - 1]

    # Sort by date
    txns_sorted = sorted(txns, key=lambda t: t.date)

    # Build output
    lines = [f"LINE {idx}: {text}"]

    if txns_sorted:
        for t in txns_sorted:
            line = f"  {t.date:%d %b %Y}  {t.description:<30}{money(t.amount):>10}"
            lines.append(line)
    else:
        lines.append("  (no payments in this cycle)")

    return lines
