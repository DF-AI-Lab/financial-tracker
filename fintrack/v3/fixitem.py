"""v3 Settings -> Fix an item (14 Oct 2026). Replaces `run.py fix`, `cat N` and `yearly N`.

GET /fix lists every saved item (newest paid first) with its kind; tap one to change its kind, category or name.
POST /fix/save {key, kind, label, category} saves one answer with sortpage.save_answers.
"""
from datetime import date
from pathlib import Path

from flask import jsonify, render_template, request

from fintrack.appversion import VERSION
from fintrack.questions import GROUP_NAMES, item_stats
from fintrack.sortpage import KIND_TO_SAVED, SAVED_TO_KIND, category_names, save_answers
from fintrack.store import get_categories, get_items, load_txns, open_db

KIND_WORDS = {"bill": "Bill", "random": "Random", "oneoff": "One-off", "yearly": "Yearly"}


def tidy(key: str) -> str:
    """'DD|ENERGY CO|' -> 'Energy Co' (the reference when there is one), like save_answers."""
    group, name, ref = (key.split("|") + ["", ""])[:3]
    return " ".join(w.capitalize() for w in (ref or name).split())


def nice_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {d:%b %Y}"


def fix_rows(conn) -> list:
    """Every saved item for the page, newest paid first; items never paid go last (by name)."""
    stats = item_stats(load_txns(conn))
    cats = get_categories(conn)
    rows = []
    for key, item in get_items(conn).items():
        s = stats.get(key, {})
        kind = SAVED_TO_KIND.get(item["kind"], "random")
        parts = [GROUP_NAMES.get(key.split("|")[0], key.split("|")[0]), cats.get(key, "")]
        if s.get("last"):
            parts.append("last paid " + nice_date(s["last"]))
            parts.append(f"avg £{s['average']:,.2f}")
        rows.append({"key": key, "name": item["label"] or tidy(key), "label": item["label"],
                     "category": cats.get(key, ""), "kind": kind, "kind_word": KIND_WORDS[kind],
                     "detail": " · ".join(p for p in parts if p), "last": s.get("last") or ""})
    rows.sort(key=lambda r: r["name"].lower())
    rows.sort(key=lambda r: r["last"], reverse=True)
    return rows


def register(app) -> None:
    db_path = Path(app.config["V3_DATA_DIR"]) / "tracker.db"

    @app.route("/fix")
    def fix_page():
        conn = open_db(db_path)
        try:
            rows, cats = fix_rows(conn), category_names(conn)
        finally:
            conn.close()
        return render_template("fix.html", rows=rows, categories=cats, kinds=KIND_WORDS, app_version=VERSION)

    @app.route("/fix/save", methods=["POST"])
    def fix_save():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return "Sorry, that did not come through. Please try again.", 400
        key, kind = str(data.get("key", "")), str(data.get("kind", ""))
        if kind not in KIND_TO_SAVED:
            return "Please pick Bill, Random, One-off or Yearly.", 400
        conn = open_db(db_path)
        try:
            if key not in get_items(conn):
                return "Sorry, I can't find that item.", 400
            label = str(data.get("label") or "").strip()[:60]
            category = str(data.get("category") or "").strip()[:40]
            save_answers(conn, [{"key": key, "kind": kind, "label": label, "category": category}])
            row = next(r for r in fix_rows(conn) if r["key"] == key)
        finally:
            conn.close()
        return jsonify(row)
