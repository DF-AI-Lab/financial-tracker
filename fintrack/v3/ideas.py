"""v3 Settings -> Ideas & feedback (Darren, 15 Oct 2026). Type a note any time (💡 idea, 🐞 something odd, ❤️ love this),
then 📋 Copy all for Claude and paste it into a new chat to plan the next version. ✅ Done moves a note out of the way.

kv key ideas (JSON text): [{"id", "text", "tag", "at" (ISO), "done"}], oldest first.
"""
from datetime import datetime

from flask import redirect, render_template, request

from fintrack.appversion import VERSION
from fintrack.v3 import auth

TAGS = {"idea": "💡 Idea", "odd": "🐞 Something odd", "love": "❤️ Love this"}
BUTTONS = {"idea": "💡 Idea", "odd": "🐞 Odd", "love": "❤️ Love it"}
MAX_TEXT = 1000


def saved(app) -> list:
    return auth._get(app, "ideas", [])


def _save(app, notes) -> None:
    auth._set(app, "ideas", notes)


def nice_date(iso: str) -> str:
    d = datetime.fromisoformat(iso)
    return f"{d.day} {d:%b %Y}"


def copy_text(notes, version=VERSION) -> str:
    """The open notes as plain text for a chat with Claude, in the order they were written."""
    lines = [f"Where's My Money? ideas & feedback (v{version}, copied {nice_date(datetime.now().isoformat())})", ""]
    for n in notes:
        if not n["done"]:
            lines.append(f"- {TAGS[n['tag']]} ({nice_date(n['at'])}): {n['text']}")
    return "\n".join(lines)


def _id() -> int:
    try:
        return int(request.form.get("id", ""))
    except ValueError:
        return -1


def register(app) -> None:

    @app.route("/ideas")
    def ideas_page():
        notes = saved(app)
        open_notes = [n for n in reversed(notes) if not n["done"]]
        done = [n for n in reversed(notes) if n["done"]]
        return render_template("ideas.html", open_notes=open_notes, done=done, tags=TAGS, buttons=BUTTONS, nice_date=nice_date,
                               copy=copy_text(notes), app_version=VERSION)

    @app.route("/ideas/add", methods=["POST"])
    def ideas_add():
        text = " ".join((request.form.get("text") or "").split())[:MAX_TEXT]
        tag = request.form.get("tag")
        if text:
            notes = saved(app)
            notes.append({"id": max((n["id"] for n in notes), default=0) + 1, "text": text,
                          "tag": tag if tag in TAGS else "idea", "at": datetime.now().isoformat(timespec="minutes"),
                          "done": False})
            _save(app, notes)
        return redirect("/ideas", code=303)

    @app.route("/ideas/done", methods=["POST"])
    def ideas_done():
        notes = saved(app)
        for n in notes:
            if n["id"] == _id():
                n["done"] = not n["done"]
        _save(app, notes)
        return redirect("/ideas", code=303)

    @app.route("/ideas/remove", methods=["POST"])
    def ideas_remove():
        _save(app, [n for n in saved(app) if n["id"] != _id()])
        return redirect("/ideas", code=303)
