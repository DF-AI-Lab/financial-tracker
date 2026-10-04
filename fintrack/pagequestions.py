"""No. 6c (user, 3 Oct 2026): the last terminal questions, on the home page.

- "Same bill?" (fintrack/samebill.py): two saved items that look like one bill under two names.
- "Is this your rent?" (fintrack/paydayrule.py): bill payments of about the same amount just after payday.
- Typed spends (fintrack/typed.py): typed spends found in the statements are removed; one not found (dated on or
  before the last statement day) is asked about: Keep (not asked again) or Remove.
Same rules and the same saved answers as run.py, so either can be used.
"""
import json
from typing import List

from fintrack.paydayrule import find_candidates
from fintrack.samebill import answer_same_bill, pending_same_bills
from fintrack.store import add_rule, delete_spend, get_items, get_rules, get_spends, get_value, set_value
from fintrack.typed import match_spends

KEPT = "kept_spends"                         # kv: ids of typed spends the user chose to keep
NOT_JOB = "not_wage"                         # kv: payer names the user said are not a new job (No. 4)


def _kept(conn) -> List[int]:
    try:
        return [int(i) for i in json.loads(get_value(conn, KEPT) or "[]")]
    except (ValueError, TypeError):
        return []


def _readable(key: str) -> str:
    group, name, ref = key.split("|")
    return f"{group} {name}" + (f' "{ref}"' if ref else "")


def _declined_jobs(conn) -> List[str]:
    return [n for n in (get_value(conn, NOT_JOB) or "").split("\n") if n]


def questions(conn, txns, paydays, payers=None) -> List[dict]:
    """Every question still to answer, as dicts with a "type" of "job", "same", "rent" or "spend".
    payers = the known wage payers (fintrack.wages.all_payers); None = no new-job question."""
    out = []
    if payers:
        from fintrack.newjob import new_job_candidates
        for c in new_job_candidates(txns, payers, _declined_jobs(conn)):
            out.append(dict(c, type="job"))
    saved = get_items(conn)
    for big, small in pending_same_bills(conn, txns):
        out.append({"type": "same", "big": big, "small": small, "big_text": _readable(big),
                    "small_text": _readable(small), "big_label": saved[big]["label"],
                    "small_label": saved[small]["label"]})
    if paydays:
        for c in find_candidates(txns, paydays, get_rules(conn)):
            out.append({"type": "rent", "payer": c["payer"], "usual": c["usual"], "label": c["suggest_label"],
                        "examples": c["examples"]})
    # Typed spends: found in the statements -> removed (like run.py); not found -> asked unless kept before
    matched, unmatched = match_spends(get_spends(conn), txns)
    for sid in matched:
        delete_spend(conn, sid)
    last = max((t.date for t in txns), default=None)
    kept = set(_kept(conn))
    for s in unmatched:
        if last is not None and s["date"] <= last and s["id"] not in kept:
            out.append({"type": "spend", "id": s["id"], "name": s["name"], "amount": s["amount"], "date": s["date"]})
    return out


def answer(conn, a: dict, txns, paydays, payers=None) -> bool:
    """Save one answer from the page. Anything that does not match a question still open is ignored (False)."""
    t = a.get("type")
    if t == "job":
        from fintrack.newjob import new_job_candidates
        names = [c["name"] for c in new_job_candidates(txns, payers or [], _declined_jobs(conn))]
        if a.get("name") not in names:
            return False
        if a.get("yes"):
            from fintrack.wages import add_payer
            add_payer(conn, a["name"])
        else:
            set_value(conn, NOT_JOB, "\n".join(_declined_jobs(conn) + [a["name"]]))
        return True
    if t == "same":
        if (a.get("big"), a.get("small")) not in pending_same_bills(conn, txns):
            return False
        answer_same_bill(conn, a["big"], a["small"], bool(a.get("yes")))
        return True
    if t == "rent":
        cand = {c["payer"]: c for c in find_candidates(txns, paydays, get_rules(conn))}.get(a.get("payer"))
        if not cand:
            return False
        if a.get("yes"):
            label = str(a.get("label") or "").strip()[:30] or cand["suggest_label"]
            add_rule(conn, cand["payer"], cand["usual"], label)
        else:
            add_rule(conn, cand["payer"], cand["usual"], "", kind="declined")
        return True
    if t == "spend":
        try:
            sid = int(a.get("id"))
        except (TypeError, ValueError):
            return False
        if sid not in [s["id"] for s in get_spends(conn)]:
            return False
        if a.get("keep"):
            set_value(conn, KEPT, json.dumps(sorted(set(_kept(conn)) | {sid})))
        else:
            delete_spend(conn, sid)
        return True
    return False
