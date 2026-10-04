"""No. 6b (user, 3 Oct 2026): sort new items on the home page instead of the keyword question list.

Each new item gets buttons (Bill / Random / One-off / Yearly), a category and a name, with my guess already picked.
'Copy for AI' makes a text to paste into an AI chat; 'Paste answers' reads its reply back into the buttons.
"""
import re
from typing import Dict, List

from fintrack.categories import STARTER, guess_category
from fintrack.questions import GROUP_NAMES, auto_bills, item_stats, pending_items, suggest
from fintrack.store import get_categories, get_items, set_category, set_item

KINDS = ["bill", "random", "oneoff", "yearly"]
KIND_TO_SAVED = {"bill": "common", "random": "random", "oneoff": "oneoff", "yearly": "yearly"}
SAVED_TO_KIND = {"common": "bill", "regular": "bill", "random": "random", "oneoff": "oneoff", "yearly": "yearly"}
WORDS = {"bill": "bill", "bills": "bill", "common": "bill", "regular": "bill", "random": "random",
         "oneoff": "oneoff", "one-off": "oneoff", "one off": "oneoff", "yearly": "yearly", "annual": "yearly"}
LIMIT = 30                                   # shown at once; the rest come after a save


def pending_for_page(conn, txns) -> List[dict]:
    """New items to sort, biggest first. DD/SO paid in 2+ months are saved as bills first (auto_bills); a new DD/SO
    paid once is always asked; other tiny ones (2 or fewer payments, under 50 in all) are not asked, like run.py."""
    auto_bills(conn, txns)
    stats = item_stats(txns)
    saved = get_items(conn)
    tiny = {k for k, s in stats.items() if s["count"] <= 2 and s["total"] < 50 and s["group"] not in ("DD", "SO")}
    out = []
    for n, s in enumerate(pending_items(stats, saved, skip=tiny)[:LIMIT], start=1):
        kind, label = suggest(s)
        out.append({"n": n, "key": s["key"], "group": GROUP_NAMES.get(s["group"], s["group"]),
                    "name": label, "detail": s["name"] + (" - " + s["reference"] if s["reference"] else ""),
                    "average": s["average"], "count": s["count"], "months": s["months"],
                    "kind": SAVED_TO_KIND[kind], "category": guess_category(s["name"], label, s["group"])})
    return out


def save_answers(conn, answers: List[dict]) -> int:
    """Save [{key, kind (bill/random/oneoff/yearly), label, category}] as the user's answers. Bad kinds are skipped.
    An empty label keeps the suggested name."""
    stats_names = {}
    n = 0
    for a in answers:
        kind = KIND_TO_SAVED.get(str(a.get("kind", "")))
        key = str(a.get("key", ""))
        if not kind or key.count("|") != 2:
            continue
        label = str(a.get("label", "")).strip()
        if not label:
            group, name, ref = key.split("|")
            label = " ".join(w.capitalize() for w in (ref or name).split())
        set_item(conn, key, kind, label[:60], "user")
        category = str(a.get("category", "")).strip()
        if category:
            set_category(conn, key, category[:40])
        n += 1
    return n


def category_names(conn) -> List[str]:
    """The starter categories plus the user's own, no repeats."""
    names = list(STARTER)
    for c in sorted(set(get_categories(conn).values())):
        if c and c not in names:
            names.append(c)
    return names


def ai_prompt(items: List[dict], categories: List[str]) -> str:
    lines = ["Please help me sort these payments from my bank statement.",
             "For each number, reply on its own line with: NUMBER KIND CATEGORY",
             "KIND is one of: bill, random, oneoff or yearly",
             "  bill = paid every month (rent, phone, insurance, subscriptions)",
             "  random = everyday spending that changes (shops, takeaways, cash)",
             "  oneoff = a single big buy that will not come back",
             "  yearly = paid once a year (car tax, insurance paid yearly)",
             "CATEGORY is one of: " + ", ".join(categories),
             "Example reply line: 1 bill Household",
             "Only the list please, no other text.",
             ""]
    for i in items:
        lines.append(f"{i['n']}. {i['name']} ({i['group']}: {i['detail']}) - average {i['average']:.2f}, "
                     f"{i['count']} payments in {i['months']} months")
    return "\n".join(lines)


def parse_ai(text: str, count: int, categories: List[str]) -> Dict[int, dict]:
    """Read an AI reply: lines like '1 bill Household', '2. Random - food shopping', '3) BILL Household'.
    Numbers outside 1..count and lines without a kind are ignored. A category matching a known one (any case) uses
    its spelling; anything else is kept as typed."""
    known = {c.lower(): c for c in categories}
    kinds = "|".join(sorted((re.escape(w) for w in WORDS), key=len, reverse=True))
    pattern = re.compile(r"^\W*(\d+)\s*[.):\-]?\s*(" + kinds + r")\b\W*(.*)$", re.IGNORECASE)
    out = {}
    for line in text.splitlines():
        m = pattern.match(line.strip())
        if not m:
            continue
        n = int(m.group(1))
        if not 1 <= n <= count:
            continue
        cat = m.group(3).strip(" .-:*,").strip()
        out[n] = {"kind": WORDS[m.group(2).lower()], "category": known.get(cat.lower(), cat)}
    return out
