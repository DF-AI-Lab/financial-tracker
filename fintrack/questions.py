"""The "confirm as you go" questions: which items are regular / common / random / one-off."""
from typing import Dict, List, Tuple

from fintrack.models import Txn

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
    raise NotImplementedError


def suggest(stat: dict) -> Tuple[str, str]:
    """(kind, label) to suggest for an item.

    kind: group SO or DD -> "regular". Otherwise (BP, CARD, CASH): "oneoff" when there is a
    single payment of 1000 or more; "common" when at least 4 payments are within 15% of the
    median amount (statistics.median); else "random".
    label: (reference or name) in Title Case, e.g. "RENT" -> "Rent", "GYM CLUB" -> "Gym Club".
    """
    raise NotImplementedError


def pending_items(stats: Dict[str, dict], saved: dict, skip=frozenset()) -> List[dict]:
    """Stats whose key is not in `saved` (the dict from fintrack.store.get_items) and not in
    `skip` (a set of keys), biggest total first (ties: by key)."""
    raise NotImplementedError


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
    raise NotImplementedError


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
    raise NotImplementedError


def fix_items(conn, ask, out=print) -> int:
    """Let the user change saved answers. Returns how many items were changed.

    Print `SAVED ITEMS` and one numbered line per saved item sorted by key:
    `  1  <key>  <kind name>  <label>` with `  (suggested)` appended when source is "suggested".
    Then print the same hint line and ask("> ") once (EOFError/OSError -> return 0). parse_answer
    it (on error print `Sorry, I did not understand:` + message and return 0). For each item with a
    typed kind and/or label call set_item with source "user" (keep the old kind or label for
    whatever was not typed). "later" and "stop" change nothing.
    """
    raise NotImplementedError
