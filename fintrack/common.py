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
    - For INT'L payments the detail is cut before the first currency code (USD, EUR ...) or "VISA RATE".
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
        # stop before the currency / exchange-rate lines ("... USD 19.99 @ 1.27 VISA RATE ...")
        text = re.split(r'\s+(?:USD|EUR|GBP|CAD|AUD|CHF|JPY|SEK|NOK|DKK|PLN|NZD)\b|\s+VISA RATE', text)[0]
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
            oneoff_limit: float = 1000.0, answers: Optional[dict] = None,
            rules: Optional[list] = None) -> Analysis:
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
      over the window, "average": total / cycles_used, "kind": "bill" or "other", "last": total
      (positive) in the newest cycle (index cycles_used - 1), 0 if no payment there; "type": the
      Txn.type of the most recent payment of this entry}.
    - common_per_cycle = sum of common totals / cycles_used;
      random_per_cycle = sum of random payments / cycles_used. Round nothing (tests use approx).

    `answers` (default None = {}) is what the user confirmed, the dict from fintrack.store.get_items:
    {item_key: {"kind": "regular"|"common"|"random"|"oneoff"|"yearly", "label": str, "source": str}}.
    For every outgoing payment in the window whose fintrack.store.item_key(t) is in `answers`, the
    answer decides instead of the automatic rules above:
      - "regular" or "common": the payment is COMMON. Group key = the answer's label if it is not
        empty, otherwise the item key. Several items with the same label are merged into one common
        entry (cycles = window cycles where any of them appears; kind = "bill" if any of its
        payments is DD or SO, else "other"). "last" is the sum over the merged parts in the newest
        cycle; "type" comes from the latest payment of all of them.
      - "random": RANDOM, even if it is big.
      - "oneoff" or "yearly": a ONE-OFF (goes in one_offs, left out of the averages), whatever its size.
    `rules` (default None = []) are the payday-transfer rules from fintrack.store.get_rules. A payment is
    covered by a rule when fintrack.paydayrule.matches_rule(t, rule, cycle.start) is true, using the start date
    (payday) of the cycle the payment is in. A covered payment is COMMON whatever its item answer says and is never
    a one-off: group key = the rule's label (or the rule's payer when the label is empty), kind "other" (merged
    with an "answers" entry of the same label, which can make the merged kind "bill"). Rules with kind "declined"
    do nothing. Rules are checked BEFORE `answers`.
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

    if rules is None:
        rules = []

    # Import item_key and matches_rule here to avoid circular imports
    from fintrack.store import item_key
    from fintrack.paydayrule import matches_rule

    # Identify rule-covered payments first (rules checked BEFORE answers)
    rule_covered_txns = set()  # Set of (cycle_idx, txn id) to mark them as covered
    rules_common = {}  # label -> {cycles_set, is_bill, total, txn_list}

    for cycle_idx, cycle in enumerate(window_cycles):
        for txn in cycle.txns:
            if txn.amount < 0:  # Money out only
                # Check if covered by any rule
                for rule in rules:
                    if rule["kind"] != "common":  # Skip declined rules
                        continue
                    if matches_rule(txn, rule, cycle.start):
                        rule_covered_txns.add(id(txn))
                        # Add to rules_common
                        label = rule.get("label", "") or rule["payer"]
                        if label not in rules_common:
                            rules_common[label] = {
                                "cycles_set": set(),
                                "is_bill": False,
                                "total": 0,
                                "txn_list": []
                            }
                        rules_common[label]["cycles_set"].add(cycle_idx)
                        rules_common[label]["is_bill"] = rules_common[label]["is_bill"] or txn.type in ("DD", "SO")
                        rules_common[label]["total"] += abs(txn.amount)
                        rules_common[label]["txn_list"].append((cycle_idx, txn))
                        break  # Stop checking rules once matched

    # Separate payments into answered and unanswered (excluding rule-covered)
    answered_txns = []  # (cycle_idx, txn, item_key)
    unanswered_txns = []  # (cycle_idx, txn)

    for cycle_idx, cycle in enumerate(window_cycles):
        for txn in cycle.txns:
            if txn.amount < 0:  # Money out only
                if id(txn) in rule_covered_txns:
                    continue  # Skip rule-covered payments
                key = item_key(txn)
                if key in answers:
                    answered_txns.append((cycle_idx, txn, key))
                else:
                    unanswered_txns.append((cycle_idx, txn))

    # Process answered payments
    answered_common = {}  # label -> {cycles_set, is_bill, total, txn_list}
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
                    "txn_list": []
                }
            answered_common[label]["cycles_set"].add(cycle_idx)
            answered_common[label]["is_bill"] = answered_common[label]["is_bill"] or txn.type in ("DD", "SO")
            answered_common[label]["total"] += abs(txn.amount)
            answered_common[label]["txn_list"].append((cycle_idx, txn))
        elif kind == "random":
            answered_random.append(txn)
        elif kind in ("oneoff", "yearly"):
            answered_one_offs.append(txn)

    # Process unanswered payments using automatic rules
    key_cycle_total = {}
    key_txn_list = {}  # track (cycle_idx, txn) pairs for each key

    for cycle_idx, txn in unanswered_txns:
        key = payee_key(txn)
        if key not in key_cycle_total:
            key_cycle_total[key] = {}
            key_txn_list[key] = []

        if cycle_idx not in key_cycle_total[key]:
            key_cycle_total[key][cycle_idx] = 0

        key_cycle_total[key][cycle_idx] += abs(txn.amount)
        key_txn_list[key].append((cycle_idx, txn))

    # Determine which unanswered keys are COMMON
    unanswered_common = {}
    unanswered_one_offs = []
    unanswered_random = []

    for key in key_cycle_total:
        per_cycle_totals = [key_cycle_total[key].get(i, 0) for i in range(cycles_used)]
        cycles_with_payment = sum(1 for t in per_cycle_totals if t > 0)
        total = sum(per_cycle_totals)

        is_bill = any(txn.type in ("DD", "SO") for _, txn in key_txn_list[key])
        kind = "bill" if is_bill else "other"

        is_common = False
        if is_bill:
            is_common = cycles_with_payment >= needed
        else:
            # Other: common if at least `needed` cycles have totals within tolerance of the median
            nonzero_totals = [t for t in per_cycle_totals if t > 0]
            if nonzero_totals:
                med = median(nonzero_totals)
                within_tolerance = sum(1 for t in nonzero_totals if med > 0 and abs(t - med) / med <= tolerance)
                is_common = within_tolerance >= needed

        if is_common:
            unanswered_common[key] = {
                "cycles": cycles_with_payment,
                "total": total,
                "average": total / cycles_used,
                "kind": kind,
                "txn_list": key_txn_list[key]
            }
        else:
            for _, txn in key_txn_list[key]:
                if abs(txn.amount) >= oneoff_limit:
                    unanswered_one_offs.append(txn)
                else:
                    unanswered_random.append(txn)

    # Merge rule-common, answered and unanswered common entries
    common = dict(unanswered_common)

    # Add rule-common entries
    for label, data in rules_common.items():
        cycles_num = len(data["cycles_set"])
        kind = "bill" if data["is_bill"] else "other"

        if label in common:
            # Merge with existing (e.g., an unanswered common of same payee_key)
            common[label]["cycles"] = max(common[label]["cycles"], cycles_num)
            common[label]["total"] += data["total"]
            common[label]["average"] = common[label]["total"] / cycles_used
            common[label]["kind"] = "bill" if (common[label]["kind"] == "bill" or kind == "bill") else "other"
            common[label].setdefault("txn_list", []).extend(data["txn_list"])
        else:
            common[label] = {
                "cycles": cycles_num,
                "total": data["total"],
                "average": data["total"] / cycles_used,
                "kind": kind,
                "txn_list": list(data["txn_list"])
            }

    # Merge answered common entries
    for label, data in answered_common.items():
        cycles_num = len(data["cycles_set"])
        kind = "bill" if data["is_bill"] else "other"

        if label in common:
            # Merge with existing (e.g., rule-common of same label)
            # Keep track of all cycles that have this label
            if "cycles_set" not in common[label]:
                common[label]["cycles_set"] = set(range(common[label].get("cycles", 0)))
            common[label]["cycles_set"] |= data["cycles_set"]
            common[label]["cycles"] = len(common[label]["cycles_set"])
            common[label]["total"] += data["total"]
            common[label]["average"] = common[label]["total"] / cycles_used
            common[label]["kind"] = "bill" if (common[label]["kind"] == "bill" or kind == "bill") else "other"
            if "txn_list" not in common[label]:
                common[label]["txn_list"] = []
            common[label]["txn_list"].extend(data["txn_list"])
        else:
            common[label] = {
                "cycles": cycles_num,
                "total": data["total"],
                "average": data["total"] / cycles_used,
                "kind": kind,
                "txn_list": data["txn_list"]
            }

    # Compute "last" and "type" for each common entry from txn_list
    newest_cycle_idx = cycles_used - 1
    for label in common:
        txn_list = common[label].get("txn_list", [])

        # Find transactions in the newest cycle
        last_amount = 0.0
        most_recent_txn = None
        most_recent_date = None

        for cycle_idx, txn in txn_list:
            # Track most recent by date
            if most_recent_date is None or txn.date > most_recent_date:
                most_recent_date = txn.date
                most_recent_txn = txn

            # Sum amount in newest cycle
            if cycle_idx == newest_cycle_idx:
                last_amount += abs(txn.amount)

        common[label]["last"] = last_amount
        common[label]["type"] = most_recent_txn.type if most_recent_txn else ""

        # Clean up: remove txn_list since it's no longer needed
        del common[label]["txn_list"]

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
