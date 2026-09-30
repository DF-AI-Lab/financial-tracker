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
    raise NotImplementedError


def matches_rule(t: Txn, rule: dict, payday: date) -> bool:
    """True when t is covered by the rule (a dict as returned by fintrack.store.get_rules).

    All of: rule["kind"] == "common"; t.type == "BP"; t.amount < 0; payer_name(t) == rule["payer"];
    abs(amount) within rule["tolerance"] of rule["usual"] (abs(abs(amount) - usual) <= usual * tolerance);
    and 0 <= (t.date - payday).days <= rule["max_days"].
    """
    raise NotImplementedError


def days_after_payday(d: date, paydays: List[date]) -> Optional[int]:
    """Days from the latest payday on or before d to d, or None if there is no such payday."""
    raise NotImplementedError


def find_candidates(txns: List[Txn], paydays: List[date], rules: List[dict], max_days: int = MAX_DAYS,
                    tolerance: float = TOLERANCE) -> List[dict]:
    """Payers that look like a payday transfer and have no rule yet. Returns a list (sorted by usual, biggest
    first) of {"payer", "usual", "examples", "suggest_label"}.

    - Only bill payments (type BP) that are money OUT, paid 0..max_days days after a payday
      (days_after_payday), are considered. Group them by payer_name.
    - Drop a payment that is already covered by an accepted rule (kind "common", using matches_rule with the
      payday before it) or that belongs to a "declined" rule (same payer and within tolerance of its usual).
    - For each payer find the usual amount: for every payment amount a as a trial centre, take the group of
      payments within tolerance of a (abs(amount - a) <= a * tolerance). Use the trial whose group is the
      biggest (ties: the smaller a). usual = the median of that group's amounts and the group is the "kept" payments.
    - The payer is a candidate when usual >= MIN_USUAL and the kept payments number at least MIN_COUNT, or at
      least 2 when that payer already has an accepted ("common") rule (a new price).
    - examples = the kept payments in date order, each {"date": ISO string, "amount": positive float,
      "reference": t.detail, "days": days after payday}. usual is rounded to 2 decimals.
    - suggest_label = "Rent" when any example reference contains "RENT" (any case), else the payer in Title Case.
    """
    raise NotImplementedError


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
    """
    raise NotImplementedError
