"""The "confirm as you go" questions: which items are regular / common / random / one-off."""
from typing import Dict, List, Tuple
from statistics import median
import re

from fintrack.models import Txn
from fintrack.store import item_key

KIND_NAMES = {"regular": "Regular", "common": "Common", "random": "Random", "oneoff": "One-off"}
GROUP_NAMES = {"DD": "Direct debit", "SO": "Standing order", "BP": "Bill payment",
               "CARD": "Card", "CASH": "Cash", "IN": "Money in"}


def item_stats(txns: List[Txn]) -> Dict[str, dict]:
    """Facts about every item that has money OUT (amount < 0), keyed by fintrack.store.item_key.

    Each stat: {"key", "group", "name", "reference", "count", "months", "total", "average",
    "last", "amounts"}. group/name/reference come from splitting the key on "|".
    count = number of payments, months = number of distinct "YYYY-MM" months they fall in,
    total = sum of the amounts as a POSITIVE number, average = total / count,
    last = ISO date of the latest payment, amounts = list of the positive amounts.
    """
    stats = {}

    for txn in txns:
        if txn.amount >= 0:  # Only money OUT (amount < 0)
            continue

        key = item_key(txn)
        if key not in stats:
            group, name, reference = key.split("|")
            stats[key] = {
                "key": key,
                "group": group,
                "name": name,
                "reference": reference,
                "count": 0,
                "months": set(),
                "total": 0.0,
                "amounts": [],
                "last": None
            }

        stat = stats[key]
        amount = abs(txn.amount)
        stat["count"] += 1
        stat["months"].add(txn.date.strftime("%Y-%m"))
        stat["total"] += amount
        stat["amounts"].append(amount)
        stat["last"] = txn.date.isoformat()

    # Convert months set to count and remove the set
    for key in stats:
        stat = stats[key]
        stat["months"] = len(stat["months"])
        stat["average"] = stat["total"] / stat["count"] if stat["count"] > 0 else 0.0

    return stats


def suggest(stat: dict) -> Tuple[str, str]:
    """(kind, label) to suggest for an item.

    kind: group SO or DD -> "regular". Otherwise (BP, CARD, CASH): "oneoff" when there is a
    single payment of 1000 or more; "common" when at least 4 payments are within 15% of the
    median amount (statistics.median); else "random".
    label: (reference or name) in Title Case, e.g. "RENT" -> "Rent", "GYM CLUB" -> "Gym Club".
    """
    group = stat["group"]
    name = stat["name"]
    reference = stat["reference"]
    amounts = stat["amounts"]
    count = stat["count"]

    # Determine kind
    if group in ("SO", "DD"):
        kind = "regular"
    else:
        # Check for oneoff: single payment of 1000 or more
        if count == 1 and amounts[0] >= 1000:
            kind = "oneoff"
        # Check for common: at least 4 payments within 15% of median
        elif count >= 4:
            med = median(amounts)
            within_tolerance = sum(1 for amt in amounts if med > 0 and abs(amt - med) / med <= 0.15)
            if within_tolerance >= 4:
                kind = "common"
            else:
                kind = "random"
        else:
            kind = "random"

    # Determine label: use reference if it exists, otherwise name, in Title Case
    label_text = reference if reference else name
    label = " ".join(word.capitalize() for word in label_text.split())

    return (kind, label)


def pending_items(stats: Dict[str, dict], saved: dict, skip=frozenset()) -> List[dict]:
    """Stats whose key is not in `saved` (the dict from fintrack.store.get_items) and not in
    `skip` (a set of keys), biggest total first (ties: by key)."""
    pending = []
    for key, stat in stats.items():
        if key not in saved and key not in skip:
            pending.append(stat)

    # Sort by total descending, then by key ascending
    pending.sort(key=lambda x: (-x["total"], x["key"]))
    return pending


def parse_answer(text: str, count: int) -> dict:
    """Read the one-line answer to a list of `count` numbered items.

    Returns {"kinds": {n: kind}, "labels": {n: text}, "later": set of n, "stop": bool,
    "error": None or a short message}. Numbers are 1-based.
    Words (any case): common, regular, random, oneoff (also "one-off") each followed by item
    numbers (space separated, ranges like 1-3 allowed); "later" + numbers; "stop" alone;
    "label" + one number + the label text, which runs until the next keyword.
    Examples: "common 1 2 4  oneoff 6", "label 2 Katie top-ups  common 3", "later 3 5", "stop".
    Blank text -> nothing set, no error. Error (and nothing else trusted) for an unknown word,
    a keyword with no numbers, or a number below 1 or above `count` (the message names it).
    """
    result = {"kinds": {}, "labels": {}, "later": set(), "stop": False, "error": None}

    if not text.strip():
        return result

    # Tokenize: split on whitespace, but keep track of "label" specially
    tokens = text.split()
    i = 0

    while i < len(tokens):
        token = tokens[i]
        token_lower = token.lower()

        if token_lower == "stop":
            result["stop"] = True
            i += 1
        elif token_lower == "label":
            # "label" + number + rest of text until next keyword
            i += 1
            if i >= len(tokens):
                result["error"] = "label needs a number"
                return result

            try:
                num = int(tokens[i])
                if num < 1 or num > count:
                    result["error"] = f"{num}"
                    return result
            except ValueError:
                result["error"] = f"label needs a number, got {tokens[i]}"
                return result

            i += 1
            # Collect label text until the next keyword
            label_parts = []
            while i < len(tokens):
                if tokens[i].lower() in ("common", "regular", "random", "oneoff", "one-off", "later", "stop", "label"):
                    break
                label_parts.append(tokens[i])
                i += 1

            result["labels"][num] = " ".join(label_parts)

        elif token_lower in ("common", "regular", "random", "oneoff", "one-off", "later"):
            # Map "one-off" to "oneoff"
            kind = "oneoff" if token_lower == "one-off" else token_lower

            # Collect numbers for this keyword
            numbers = []
            i += 1

            while i < len(tokens):
                t = tokens[i]
                if t.lower() in ("common", "regular", "random", "oneoff", "one-off", "later", "stop", "label"):
                    break

                # Check if it's a range like "1-3"
                if "-" in t:
                    try:
                        parts = t.split("-")
                        if len(parts) == 2:
                            start = int(parts[0])
                            end = int(parts[1])
                            for n in range(start, end + 1):
                                numbers.append(n)
                        else:
                            result["error"] = f"{t}"
                            return result
                    except ValueError:
                        result["error"] = f"{t}"
                        return result
                else:
                    try:
                        n = int(t)
                        numbers.append(n)
                    except ValueError:
                        result["error"] = f"{t}"
                        return result

                i += 1

            # Validate numbers
            if not numbers:
                result["error"] = f"{token_lower}"
                return result

            for n in numbers:
                if n < 1 or n > count:
                    result["error"] = f"{n}"
                    return result

            # Add to kinds or later
            if kind == "later":
                result["later"].update(numbers)
            else:
                for n in numbers:
                    result["kinds"][n] = kind

        else:
            # Unknown keyword
            result["error"] = token_lower
            return result

    return result


def review(conn, txns: List[Txn], ask, out=print, size: int = 10) -> int:
    """Ask about every item that has no saved answer, `size` at a time. Returns how many items were saved.

    - stats = item_stats(txns); saved = fintrack.store.get_items(conn).
    - Loop: take the next `size` items from pending_items (skipping items you skipped with "later"
      in THIS run). If none, finish. Print (out) a heading `NEW ITEMS (biggest first)` and one line
      per item:  `  1  Standing order  SAM PARKER - RENT   avg 550.00  (8 in 8 months)  suggest: Regular`
      (index, GROUP_NAMES[group], name plus " - reference" when there is one, average with 2
      decimals, count and months, then suggest: KIND_NAMES[kind]). Then print the hint line
      `Type e.g.  common 1 2  oneoff 3  label 1 Rent  later 4  stop   (Enter keeps my suggestions)`.
    - answer = ask("> "). EOFError or OSError -> stop quietly. parse_answer; if error: out a line
      starting `Sorry, I did not understand:` plus the message, and ask again for the SAME round.
    - "stop": end (nothing from this round is saved). Items in "later" are not saved, and are not asked
      again in this run (but are asked again in the next run).
    - Every other item of the round is saved with fintrack.store.set_item: kind = typed kind or the
      suggestion, label = typed label or the suggestion. source is "user" if you typed a kind or label
      for that item, else "suggested".
    """
    from fintrack.store import get_items, set_item

    stats = item_stats(txns)
    saved = get_items(conn)

    total_saved = 0
    later_set = set()

    while True:
        # Get pending items, skipping those marked "later" in this run
        pending = pending_items(stats, saved, skip=later_set)

        if not pending:
            break

        # Take the next `size` items
        round_items = pending[:size]
        if not round_items:
            break

        # Print heading
        out("NEW ITEMS (biggest first)")

        # Print one line per item
        for idx, stat in enumerate(round_items, start=1):
            group = stat["group"]
            name = stat["name"]
            reference = stat["reference"]
            average = stat["average"]
            count = stat["count"]
            months = stat["months"]

            # Format the name and reference
            group_name = GROUP_NAMES.get(group, group)
            if reference:
                display_name = f"{name} - {reference}"
            else:
                display_name = name

            # Get suggestion
            kind, label = suggest(stat)
            kind_name = KIND_NAMES[kind]

            # Format the line
            line = f"  {idx}  {group_name}  {display_name}   avg {average:.2f}  ({count} in {months} months)  suggest: {kind_name}"
            out(line)

        # Print hint line
        out("Type e.g.  common 1 2  oneoff 3  label 1 Rent  later 4  stop   (Enter keeps my suggestions)")

        # Ask for answer
        while True:
            try:
                answer_text = ask("> ")
            except (EOFError, OSError):
                return total_saved

            parsed = parse_answer(answer_text, len(round_items))

            if parsed["error"]:
                out(f"Sorry, I did not understand: {parsed['error']}")
                continue

            # Process the answer
            if parsed["stop"]:
                # Nothing from this round is saved
                return total_saved

            # Save items
            for idx, stat in enumerate(round_items, start=1):
                if idx in parsed["later"]:
                    # Mark as "later" for skipping in this run
                    later_set.add(stat["key"])
                else:
                    # Determine kind and label to save
                    if idx in parsed["kinds"]:
                        kind = parsed["kinds"][idx]
                        source = "user"
                    else:
                        kind, _ = suggest(stat)
                        source = "suggested"

                    if idx in parsed["labels"]:
                        label = parsed["labels"][idx]
                        source = "user"
                    else:
                        _, label = suggest(stat)

                    # If kind was typed, source is "user"
                    if idx in parsed["kinds"] or idx in parsed["labels"]:
                        source = "user"
                    else:
                        source = "suggested"

                    set_item(conn, stat["key"], kind, label, source)
                    saved[stat["key"]] = {"kind": kind, "label": label, "source": source}
                    total_saved += 1

            break

    return total_saved


def fix_items(conn, ask, out=print) -> int:
    """Let the user change saved answers. Returns how many items were changed.

    Print `SAVED ITEMS` and one numbered line per saved item sorted by key:
    `  1  <key>  <kind name>  <label>` with `  (suggested)` appended when source is "suggested".
    Then print the same hint line and ask("> ") once (EOFError/OSError -> return 0). parse_answer
    it (on error print `Sorry, I did not understand:` + message and return 0). For each item with a
    typed kind and/or label call set_item with source "user" (keep the old kind or label for
    whatever was not typed). "later" and "stop" change nothing.
    """
    from fintrack.store import get_items, set_item

    items = get_items(conn)

    # Sort items by key
    sorted_keys = sorted(items.keys())

    # Print heading
    out("SAVED ITEMS")

    # Print one line per item
    key_to_idx = {}
    for idx, key in enumerate(sorted_keys, start=1):
        item = items[key]
        kind_name = KIND_NAMES.get(item["kind"], item["kind"])
        label = item["label"]
        suggested_suffix = "  (suggested)" if item["source"] == "suggested" else ""

        line = f"  {idx}  {key}  {kind_name}  {label}{suggested_suffix}"
        out(line)
        key_to_idx[idx] = key

    # Print hint line
    out("Type e.g.  common 1 2  oneoff 3  label 1 Rent  later 4  stop   (Enter keeps my suggestions)")

    # Ask for answer once
    try:
        answer_text = ask("> ")
    except (EOFError, OSError):
        return 0

    parsed = parse_answer(answer_text, len(sorted_keys))

    if parsed["error"]:
        out(f"Sorry, I did not understand: {parsed['error']}")
        return 0

    # Count changes
    changed_count = 0

    # Process each item with typed kind and/or label
    for idx in list(set(parsed["kinds"].keys()) | set(parsed["labels"].keys())):
        if idx not in key_to_idx:
            continue

        key = key_to_idx[idx]
        old_item = items[key]

        # Get the new kind and label
        new_kind = parsed["kinds"].get(idx, old_item["kind"])
        new_label = parsed["labels"].get(idx, old_item["label"])

        # Only count as changed if something actually changed
        if new_kind != old_item["kind"] or new_label != old_item["label"]:
            set_item(conn, key, new_kind, new_label, source="user")
            changed_count += 1

    return changed_count
