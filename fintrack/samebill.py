"""Find and ask about items that might be the same bill under different names."""
from typing import Callable, Dict, List, Tuple
from fintrack.questions import item_stats
from fintrack.store import get_items, get_same_bills, set_same_bill, set_item


FILLER = {"PAYMENT", "PAYMENTS", "AND", "THE", "FOR"}


def similar_pairs(stats: Dict) -> List[Tuple[str, str]]:
    """List of (key_big, key_small) pairs that look like the same bill with different names.

    Consider only stats with group "SO" or "BP" and a non-empty reference. Two items pair when
    they have the same name, different references, and their references share at least one word
    (split on spaces) of 3+ letters that is not in FILLER. In each pair the item with the bigger
    "total" comes first. Sort the pairs by combined total, biggest first.
    """
    # Filter stats: only SO and BP with non-empty reference
    candidates = [
        (key, stat) for key, stat in stats.items()
        if stat["group"] in ("SO", "BP") and stat["reference"]
    ]

    pairs = []

    # Find similar pairs
    for i, (key_i, stat_i) in enumerate(candidates):
        for key_j, stat_j in candidates[i+1:]:
            # Must have the same name
            if stat_i["name"] != stat_j["name"]:
                continue

            # Must have different references
            if stat_i["reference"] == stat_j["reference"]:
                continue

            # Check if references share at least one word of 3+ letters not in FILLER
            ref_i_words = set(w for w in stat_i["reference"].split() if len(w) >= 3 and w not in FILLER)
            ref_j_words = set(w for w in stat_j["reference"].split() if len(w) >= 3 and w not in FILLER)

            if not ref_i_words or not ref_j_words:
                continue

            if not ref_i_words & ref_j_words:
                continue

            # This is a match: add to pairs
            if stat_i["total"] >= stat_j["total"]:
                pairs.append((key_i, key_j))
            else:
                pairs.append((key_j, key_i))

    # Sort by combined total, biggest first
    pairs.sort(key=lambda p: -(stats[p[0]]["total"] + stats[p[1]]["total"]))

    return pairs


def ask_same_bills(conn, txns: List, ask: Callable, out=print) -> int:
    """Ask about similar-looking items and save answers. Returns how many answers were saved (y or n).

    For each similar pair:
    - Skip if either key is not in the saved items
    - Skip if the pair has already been answered
    - Skip if the two saved labels are equal (case-insensitive, ignoring surrounding spaces)
    - Otherwise ask a yes/no question containing both keys' group+name+reference in readable form

    Replies:
    - "y" or "yes": copy first item's kind and label to second, set source="same", save the answer as True
    - "n", "no" or "" (Enter): save the answer as False (Enter keeps them apart, like accepting a suggestion)
    - "stop": stop asking and return immediately
    - "later" or anything else: save nothing, ask again next run (return answer count so far)
    """
    stats = item_stats(txns)
    saved = get_items(conn)
    answered = get_same_bills(conn)

    pairs = similar_pairs(stats)

    count = 0
    for key_big, key_small in pairs:
        # Skip if either key is not saved
        if key_big not in saved or key_small not in saved:
            continue

        # Skip if already answered
        pair_set = frozenset({key_big, key_small})
        if pair_set in answered:
            continue

        # Skip if labels are equal (case-insensitive, ignoring surrounding spaces)
        label_big = saved[key_big]["label"].strip().lower()
        label_small = saved[key_small]["label"].strip().lower()
        if label_big == label_small:
            continue

        # Build readable form of the keys: GROUP NAME "REFERENCE"
        def format_key(key):
            parts = key.split("|")
            group, name, reference = parts[0], parts[1], parts[2]
            if reference:
                return f"{group} {name} \"{reference}\""
            else:
                return f"{group} {name}"

        big_fmt = format_key(key_big)
        small_fmt = format_key(key_small)

        prompt = f"Same bill?  {big_fmt}  and  {small_fmt}  (y / n (Enter = n) / later / stop)"

        try:
            reply = ask(prompt).strip().lower()
        except (EOFError, OSError):
            return count

        if reply in ("y", "yes"):
            # Copy first to second, set source="same"
            set_same_bill(conn, key_big, key_small, True)
            first_item = saved[key_big]
            set_item(conn, key_small, first_item["kind"], first_item["label"], source="same")
            count += 1
        elif reply in ("n", "no", ""):
            # Save the answer as False
            set_same_bill(conn, key_big, key_small, False)
            count += 1
        elif reply == "stop":
            return count
        # else: "later" or anything else -> save nothing, asked again next run

    return count
