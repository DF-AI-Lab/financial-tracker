import re
from statistics import median
from typing import List, Optional

from fintrack.models import Analysis, Cycle, Txn
from fintrack.sort import bill_key


def payee_key(t: Txn) -> str:
    """Name a payment is grouped under when looking for common payments.

    - DD and SO payments: use fintrack.sort.bill_key(t).
    - Everything else: the description upper-cased; but if it starts with "INT'L" (foreign
      card payments) use the detail instead. Remove every run of digits, remove a trailing
      " LTD", " LIMITED" or " PLC", collapse repeated spaces, strip.
      e.g. "CORNER SHOP 12" -> "CORNER SHOP".
    - A "*" becomes a space ("GOOGLE *YOUTUBE" -> "GOOGLE YOUTUBE") and trailing "+" and spaces are dropped.
    - Cash machines (type ATM): also drop a trailing month word (JAN..DEC), because the bank
      writes the date into the name: "CASH NOTEMAC APR18" -> "CASH NOTEMAC".
    """
    # For DD and SO, use bill_key
    if t.type in ("DD", "SO"):
        return bill_key(t)

    # For other types, check if description starts with INT'L
    desc_upper = t.description.strip().upper()
    if desc_upper.startswith("INT'L"):
        text = t.detail.upper()
    else:
        text = desc_upper

    # Remove every run of digits
    text = re.sub(r'\d+', '', text)

    # A star is just bank punctuation ("GOOGLE *YOUTUBE"); a trailing plus is left over from a phone number
    text = text.replace('*', ' ')
    text = re.sub(r'[ +]+$', '', text)

    # Remove trailing " LTD", " LIMITED", or " PLC"
    if text.endswith(" LTD"):
        text = text[:-4].strip()
    elif text.endswith(" LIMITED"):
        text = text[:-8].strip()
    elif text.endswith(" PLC"):
        text = text[:-4].strip()

    # Collapse repeated spaces and strip
    text = re.sub(r' +', ' ', text).strip()

    # Cash machines: the bank writes the date into the name ("CASH NOTEMAC APR18"), so drop a
    # trailing month word, otherwise every month becomes a different item
    if t.type == "ATM":
        text = re.sub(r' (JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)$', '', text).strip()

    return text


def analyse(cycles: List[Cycle], window: int = 6, min_cycles: int = 4, tolerance: float = 0.15,
            oneoff_limit: float = 1000.0, answers: Optional[dict] = None) -> Analysis:
    """Work out which spending is COMMON, which is a ONE-OFF and which is RANDOM.

    - Use only cycles with complete=True, and only the last `window` of them.
      cycles_used = how many that is (0 -> Analysis(0, {}, 0.0, 0.0, [])).
    - needed = min(min_cycles, cycles_used).
    - Only money OUT counts (amount < 0). Wage and other money in are ignored.
    - Group payments by payee_key. For each key, its total per cycle = sum of the amounts
      paid out in that cycle (as a positive number).
    - A key is COMMON when
        * any payment of it is type DD or SO ("bill"): it appears in >= needed cycles of
          the window, whatever the amounts; or
        * otherwise ("other"): at least `needed` of the window's cycles have a total within
          `tolerance` (a fraction, 0.15 = 15%) of the MEDIAN of that key's per-cycle totals.
    - If a key is common, ALL its payments in the window are common.
    - A payment that is not common and whose size is >= oneoff_limit is a ONE-OFF
      (collected in Analysis.one_offs, in date order) and is left out of every average.
    - Every other payment is RANDOM.
    - common[key] = {"cycles": number of window cycles the key appears in, "total": its total
      over the window, "average": total / cycles_used, "kind": "bill" or "other"}.
    - common_per_cycle = sum of common totals / cycles_used;
      random_per_cycle = sum of random payments / cycles_used. Round nothing (tests use approx).

    `answers` (default None = {}) is what the user confirmed, the dict from fintrack.store.get_items:
    {item_key: {"kind": "regular"|"common"|"random"|"oneoff", "label": str, "source": str}}.
    For every outgoing payment in the window whose fintrack.store.item_key(t) is in `answers`, the
    answer decides instead of the automatic rules above:
      - "regular" or "common": the payment is COMMON. Group key = the answer's label if it is not
        empty, otherwise the item key. Several items with the same label are merged into one common
        entry (cycles = window cycles where any of them appears; kind = "bill" if any of its
        payments is DD or SO, else "other").
      - "random": RANDOM, even if it is big.
      - "oneoff": a ONE-OFF (goes in one_offs, left out of the averages), whatever its size.
    Payments whose item is NOT in `answers` still follow the automatic rules, which are worked out
    from the unanswered payments only. one_offs stay sorted by date.
    """
    # Filter to complete cycles and take the last window
    complete_cycles = [c for c in cycles if c.complete]
    if not complete_cycles:
        return Analysis(0, {}, 0.0, 0.0, [])

    window_cycles = complete_cycles[-window:]
    cycles_used = len(window_cycles)
    needed = min(min_cycles, cycles_used)

    if answers is None:
        answers = {}

    # Import item_key here to avoid circular imports
    from fintrack.store import item_key

    # Separate payments into answered and unanswered
    answered_txns = []  # (cycle_idx, txn)
    unanswered_txns = []  # (cycle_idx, txn)

    for cycle_idx, cycle in enumerate(window_cycles):
        for txn in cycle.txns:
            if txn.amount < 0:  # Money out only
                key = item_key(txn)
                if key in answers:
                    answered_txns.append((cycle_idx, txn, key))
                else:
                    unanswered_txns.append((cycle_idx, txn))

    # Process answered payments
    answered_common = {}  # label -> {cycles_set, is_bill, total, txns}
    answered_one_offs = []
    answered_random = []

    for cycle_idx, txn, item_k in answered_txns:
        answer = answers[item_k]
        kind = answer["kind"]
        label = answer.get("label", "") or item_k

        if kind in ("regular", "common"):
            # Common payment
            if label not in answered_common:
                answered_common[label] = {
                    "cycles_set": set(),
                    "is_bill": False,
                    "total": 0,
                    "txns": []
                }
            answered_common[label]["cycles_set"].add(cycle_idx)
            answered_common[label]["is_bill"] = answered_common[label]["is_bill"] or txn.type in ("DD", "SO")
            answered_common[label]["total"] += abs(txn.amount)
            answered_common[label]["txns"].append(txn)
        elif kind == "random":
            answered_random.append(txn)
        elif kind == "oneoff":
            answered_one_offs.append(txn)

    # Process unanswered payments using automatic rules
    key_cycle_total = {}
    key_txns = {}

    for cycle_idx, txn in unanswered_txns:
        key = payee_key(txn)
        if key not in key_cycle_total:
            key_cycle_total[key] = {}
            key_txns[key] = []

        if cycle_idx not in key_cycle_total[key]:
            key_cycle_total[key][cycle_idx] = 0
        key_cycle_total[key][cycle_idx] += abs(txn.amount)
        key_txns[key].append(txn)

    # Determine which unanswered keys are COMMON
    unanswered_common = {}
    unanswered_one_offs = []
    unanswered_random = []

    for key in key_cycle_total:
        # Get the per-cycle totals for this key (including zeros for cycles without payment)
        per_cycle_totals = [key_cycle_total[key].get(i, 0) for i in range(cycles_used)]
        cycles_with_payment = sum(1 for t in per_cycle_totals if t > 0)
        total = sum(per_cycle_totals)

        # Check if any payment is a bill (DD or SO)
        is_bill = any(txn.type in ("DD", "SO") for txn in key_txns[key])
        kind = "bill" if is_bill else "other"

        is_common = False
        if is_bill:
            # Bill: common if appears in >= needed cycles
            is_common = cycles_with_payment >= needed
        else:
            # Other: common if at least needed cycles with payment have totals within tolerance of median
            # Only consider non-zero totals for the median calculation
            nonzero_totals = [t for t in per_cycle_totals if t > 0]
            if nonzero_totals:
                med = median(nonzero_totals)
                within_tolerance = sum(1 for t in nonzero_totals if med > 0 and abs(t - med) / med <= tolerance)
                is_common = within_tolerance >= needed

        if is_common:
            # All payments of this key are common
            unanswered_common[key] = {
                "cycles": cycles_with_payment,
                "total": total,
                "average": total / cycles_used,
                "kind": kind
            }
        else:
            # Not common: check each payment for one-off or random
            for txn in key_txns[key]:
                if abs(txn.amount) >= oneoff_limit:
                    unanswered_one_offs.append(txn)
                else:
                    unanswered_random.append(txn)

    # Merge answered and unanswered common entries
    common = dict(unanswered_common)
    for label, data in answered_common.items():
        cycles_num = len(data["cycles_set"])
        kind = "bill" if data["is_bill"] else "other"
        common[label] = {
            "cycles": cycles_num,
            "total": data["total"],
            "average": data["total"] / cycles_used,
            "kind": kind
        }

    # Merge one-offs and random
    one_offs = answered_one_offs + unanswered_one_offs
    one_offs.sort(key=lambda t: t.date)

    random_payments = answered_random + unanswered_random

    # Calculate per-cycle averages
    common_total = sum(v["total"] for v in common.values())
    common_per_cycle = common_total / cycles_used if cycles_used > 0 else 0.0

    random_total = sum(abs(t.amount) for t in random_payments)
    random_per_cycle = random_total / cycles_used if cycles_used > 0 else 0.0

    return Analysis(cycles_used, common, common_per_cycle, random_per_cycle, one_offs)
