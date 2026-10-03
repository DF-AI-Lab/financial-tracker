"""Payday transfers: a bill payment (transfer) to the same person, paid within a couple of days of
payday, for about the same amount every time (for example rent), even if the reference is wrong."""
from datetime import date
from typing import List, Optional

from fintrack.models import Txn

MAX_DAYS = 2          # how many days after payday
TOLERANCE = 0.10      # how far from the usual amount (10%)
MIN_USUAL = 100.0     # ignore small amounts (top-ups)
MIN_COUNT = 3         # payments needed before we ask; 2 when the payer already has an accepted rule


def payer_name(t: Txn) -> str:
    """The payer part of fintrack.store.item_key(t): its NAME (the text between the first and second "|")."""
    from fintrack.store import item_key
    key = item_key(t)
    parts = key.split("|")
    return parts[1]


def matches_rule(t: Txn, rule: dict, payday: date) -> bool:
    """True when t is covered by the rule (a dict as returned by fintrack.store.get_rules).

    All of: rule["kind"] == "common"; t.type == "BP"; t.amount < 0; payer_name(t) == rule["payer"];
    abs(amount) within rule["tolerance"] of rule["usual"] (abs(abs(amount) - usual) <= usual * tolerance);
    and 0 <= (t.date - payday).days <= rule["max_days"].
    """
    if rule["kind"] != "common":
        return False

    if t.type != "BP":
        return False

    if t.amount >= 0:
        return False

    if payer_name(t) != rule["payer"]:
        return False

    usual = rule["usual"]
    tolerance = rule["tolerance"]
    if abs(abs(t.amount) - usual) > usual * tolerance:
        return False

    days = (t.date - payday).days
    if days < 0 or days > rule["max_days"]:
        return False

    return True


def days_after_payday(d: date, paydays: List[date]) -> Optional[int]:
    """Days from the latest payday on or before d to d, or None if there is no such payday."""
    latest_payday = None
    for payday in paydays:
        if payday <= d:
            latest_payday = payday

    if latest_payday is None:
        return None

    return (d - latest_payday).days


def find_candidates(txns: List[Txn], paydays: List[date], rules: List[dict], max_days: int = MAX_DAYS,
                    tolerance: float = TOLERANCE) -> List[dict]:
    """Payers that look like a payday transfer and have no rule yet. Returns a list (sorted by usual, biggest
    first) of {"payer", "usual", "examples", "suggest_label"}.

    - Only bill payments (type BP) that are money OUT, paid 0..max_days days after a payday
      (days_after_payday), are considered. Group them by payer_name.
    - Drop a payment that is already covered by an accepted rule (kind "common", using matches_rule with the
      payday before it) or that belongs to a "declined" rule (same payer and within tolerance of its usual).
    - For each payer find the usual amount: filter out payments under MIN_USUAL, then for every remaining payment
      amount a as a trial centre, take the group of payments within tolerance of a (abs(amount - a) <= a * tolerance).
      Use the trial whose group is the biggest (ties: the smaller a). usual = the median of that group's amounts and
      the group is the "kept" payments. Skip payers with no payments left after filtering.
    - The payer is a candidate when usual >= MIN_USUAL and the kept payments number at least MIN_COUNT, or at
      least 2 when that payer already has an accepted ("common") rule (a new price).
    - examples = the kept payments in date order, each {"date": ISO string, "amount": positive float,
      "reference": t.detail, "days": days after payday}. usual is rounded to 2 decimals.
    - suggest_label = "Rent" when any example reference contains "RENT" (any case), else the payer in Title Case.
    """
    import statistics

    candidates = {}

    for t in txns:
        if t.type != "BP" or t.amount >= 0:
            continue

        days = days_after_payday(t.date, paydays)
        if days is None or days > max_days:
            continue

        # Check if covered by a rule
        covered = False
        for rule in rules:
            if rule["kind"] == "common":
                # Find the payday before/on this transaction
                payday = None
                for p in paydays:
                    if p <= t.date:
                        payday = p
                    else:
                        break
                if payday and matches_rule(t, rule, payday):
                    covered = True
                    break
            elif rule["kind"] == "declined":
                if payer_name(t) == rule["payer"]:
                    if abs(abs(t.amount) - rule["usual"]) <= rule["usual"] * rule["tolerance"]:
                        covered = True
                        break

        if covered:
            continue

        payer = payer_name(t)
        if payer not in candidates:
            candidates[payer] = []
        candidates[payer].append(t)

    result = []
    for payer, txns_list in candidates.items():
        # Filter out payments under MIN_USUAL before finding the usual amount
        filtered_txns = [t for t in txns_list if abs(t.amount) >= MIN_USUAL]
        if not filtered_txns:
            continue

        # Find best trial amount for this payer
        amounts = sorted(set(abs(t.amount) for t in filtered_txns))
        best_group = None
        best_count = 0
        best_trial = None

        for trial in amounts:
            group = [t for t in filtered_txns if abs(abs(t.amount) - trial) <= trial * tolerance]
            if len(group) > best_count or (len(group) == best_count and (best_trial is None or trial < best_trial)):
                best_group = group
                best_count = len(group)
                best_trial = trial

        # Check if this payer is a candidate
        usual = statistics.median(abs(t.amount) for t in best_group)
        has_accepted_rule = any(r["payer"] == payer and r["kind"] == "common" for r in rules)
        min_count = 2 if has_accepted_rule else MIN_COUNT

        if usual >= MIN_USUAL and len(best_group) >= min_count:
            # Create the example list
            examples = []
            for t in sorted(best_group, key=lambda x: x.date):
                days = days_after_payday(t.date, paydays)
                reference = t.detail.strip().upper() if t.detail else ""
                if reference == "FIRST PAYMENT":
                    reference = ""
                examples.append({
                    "date": t.date.isoformat(),
                    "amount": abs(t.amount),
                    "reference": reference,
                    "days": days
                })

            # Determine suggest_label
            if any("RENT" in e["reference"].upper() for e in examples):
                suggest_label = "Rent"
            else:
                suggest_label = payer.title()

            result.append({
                "payer": payer,
                "usual": round(usual, 2),
                "examples": examples,
                "suggest_label": suggest_label
            })

    # Sort by usual, biggest first
    result.sort(key=lambda x: -x["usual"])

    return result


def review_rules(conn, txns: List[Txn], paydays: List[date], ask, out=print) -> int:
    """Ask once about each candidate and save the answer with fintrack.store.add_rule. Returns how many rules were saved.

    For each candidate (from find_candidates with the saved rules from get_rules) print (out), plain ASCII:
        PAYDAY TRANSFERS            (only once, before the first candidate)
          KATIE FINCH: bill payments of about 550.00, within 2 days of payday (4 found)
            2024-02-29  550.00  ref FOOD  (1 days after payday)
            ...
          Count these as Common, label "Rent"?  y = yes, n = no, or type another label
    (one example line per example, use the word "days" whatever the number). Then answer = ask("> ").
    EOFError or OSError -> stop and return what was saved so far. "y" or "" (any case) -> add_rule(conn, payer,
    usual, suggest_label, kind="common"). "n" (any case) -> add_rule(..., label="", kind="declined"). Anything
    else is taken as the label: add_rule(..., that text stripped, kind="common"). Nothing is asked when there are
    no candidates.

    A sentence (>3 words or >25 characters) prompts: "That looks like a sentence. Type y, n, or a short label (up to 3 words)."
    and asks once more. If the second answer is also a sentence, save nothing (ask again next run).
    """
    from fintrack.store import get_rules, add_rule

    def is_sentence(text: str) -> bool:
        """A sentence has >3 words or >25 characters."""
        word_count = len(text.split())
        return word_count > 3 or len(text) > 25

    rules = get_rules(conn)
    candidates = find_candidates(txns, paydays, rules)

    if not candidates:
        return 0

    saved = 0
    first = True

    for candidate in candidates:
        if first:
            out("PAYDAY TRANSFERS")
            first = False

        payer = candidate["payer"]
        usual = candidate["usual"]
        suggest_label = candidate["suggest_label"]
        examples = candidate["examples"]

        # Print candidate info
        out(f"  {payer}: bill payments of about {usual:.2f}, within 2 days of payday ({len(examples)} found)")

        # Print examples
        for example in examples:
            date_str = example["date"]
            amount = example["amount"]
            reference = example["reference"]
            days = example["days"]
            if reference:
                out(f"    {date_str}  {amount:.2f}  ref {reference}  ({days} days after payday)")
            else:
                out(f"    {date_str}  {amount:.2f}  ({days} days after payday)")

        # Print question
        out(f'  Count these as Common, label "{suggest_label}"?  y = yes, n = no, or type another label')

        # Ask the user (first time)
        try:
            answer = ask("> ").strip()
        except (EOFError, OSError):
            break

        # Handle the response
        answer_lower = answer.lower()
        if answer_lower == "y" or answer_lower == "":
            add_rule(conn, payer, usual, suggest_label)
            saved += 1
        elif answer_lower == "n":
            add_rule(conn, payer, usual, "", kind="declined")
            saved += 1
        else:
            # Check if it's a sentence
            if is_sentence(answer):
                out("That looks like a sentence. Type y, n, or a short label (up to 3 words).")
                # Ask once more
                try:
                    answer2 = ask("> ").strip()
                except (EOFError, OSError):
                    break

                answer2_lower = answer2.lower()
                if answer2_lower == "y" or answer2_lower == "":
                    add_rule(conn, payer, usual, suggest_label)
                    saved += 1
                elif answer2_lower == "n":
                    add_rule(conn, payer, usual, "", kind="declined")
                    saved += 1
                elif is_sentence(answer2):
                    # Second answer is also a sentence, don't save (ask again next run)
                    pass
                else:
                    # Second answer is a short label
                    add_rule(conn, payer, usual, answer2)
                    saved += 1
            else:
                # First answer is a short label
                add_rule(conn, payer, usual, answer)
                saved += 1

    return saved
