"""v3 Settings -> Ideas & feedback (Darren, 15 Oct 2026): notes for the next version, then Copy all for Claude.
Fake data only."""
import pytest

from tests.v3_helpers import v3_data, v3_app, v3_client, ACME  # noqa: F401

pytest.importorskip("flask")
from fintrack.v3 import ideas  # noqa: E402


def add(client, text, tag="idea"):
    return client.post("/ideas/add", data={"text": text, "tag": tag})


def test_page_needs_sign_in(v3_app):
    assert v3_app.test_client().get("/ideas").status_code in (302, 303)
    assert v3_app.test_client().post("/ideas/add", data={"text": "x"}).status_code == 401


def test_settings_links_to_ideas(v3_client):
    assert 'href="/ideas"' in v3_client.get("/").get_data(as_text=True)


def test_empty_page(v3_client):
    page = v3_client.get("/ideas").get_data(as_text=True)
    assert "Ideas &amp; feedback" in page and 'name="text"' in page


def test_add_saves_text_tag_and_date(v3_app, v3_client):
    r = add(v3_client, "  Show the rent day on the top card  ", "idea")
    assert r.status_code in (302, 303) and r.headers["Location"].endswith("/ideas")
    notes = ideas.saved(v3_app)
    assert len(notes) == 1
    n = notes[0]
    assert n["text"] == "Show the rent day on the top card" and n["tag"] == "idea" and not n["done"]
    assert n["at"][:4].isdigit()
    assert "Show the rent day on the top card" in v3_client.get("/ideas").get_data(as_text=True)


def test_tags(v3_app, v3_client):
    add(v3_client, "Bills total looked wrong", "odd")
    add(v3_client, "Fingerprint is great", "love")
    add(v3_client, "Strange tag", "nonsense")                 # unknown tag = idea
    assert [n["tag"] for n in ideas.saved(v3_app)] == ["odd", "love", "idea"]


def test_empty_or_huge_text(v3_app, v3_client):
    add(v3_client, "   ")
    assert ideas.saved(v3_app) == []
    add(v3_client, "x" * 5000)
    assert len(ideas.saved(v3_app)[0]["text"]) == ideas.MAX_TEXT


def test_newest_first_on_the_page(v3_client):
    add(v3_client, "First note")
    add(v3_client, "Second note")
    page = v3_client.get("/ideas").get_data(as_text=True)
    assert page.index("Second note") < page.index("First note")


def test_done_and_back(v3_app, v3_client):
    add(v3_client, "Build me")
    nid = ideas.saved(v3_app)[0]["id"]
    v3_client.post("/ideas/done", data={"id": nid})
    assert ideas.saved(v3_app)[0]["done"]
    v3_client.post("/ideas/done", data={"id": nid})            # tap again = not done
    assert not ideas.saved(v3_app)[0]["done"]


def test_remove(v3_app, v3_client):
    add(v3_client, "Keep")
    add(v3_client, "Bin")
    gone = next(n["id"] for n in ideas.saved(v3_app) if n["text"] == "Bin")
    v3_client.post("/ideas/remove", data={"id": gone})
    assert [n["text"] for n in ideas.saved(v3_app)] == ["Keep"]
    assert v3_client.post("/ideas/remove", data={"id": "999"}).status_code in (302, 303)    # unknown: no crash


def test_ids_stay_unique_after_remove(v3_app, v3_client):
    add(v3_client, "a")
    add(v3_client, "b")
    v3_client.post("/ideas/remove", data={"id": ideas.saved(v3_app)[1]["id"]})
    add(v3_client, "c")
    ids = [n["id"] for n in ideas.saved(v3_app)]
    assert len(set(ids)) == len(ids)


def test_copy_text_open_notes_only(v3_app, v3_client):
    add(v3_client, "Rent day on top", "idea")
    add(v3_client, "Bills total odd", "odd")
    add(v3_client, "Already built", "idea")
    built = next(n["id"] for n in ideas.saved(v3_app) if n["text"] == "Already built")
    v3_client.post("/ideas/done", data={"id": built})
    text = ideas.copy_text(ideas.saved(v3_app), "3.62")
    assert "v3.62" in text
    assert "💡 Idea" in text and "Rent day on top" in text
    assert "🐞 Something odd" in text and "Bills total odd" in text
    assert "Already built" not in text
    assert text.index("Rent day on top") < text.index("Bills total odd")     # oldest first: the order they came


def test_copy_box_on_the_page(v3_client):
    add(v3_client, "Rent day on top")
    page = v3_client.get("/ideas").get_data(as_text=True)
    assert 'id="copytext"' in page and "Copy all for Claude" in page


def test_text_is_escaped(v3_client):
    add(v3_client, "<script>alert(1)</script>")
    page = v3_client.get("/ideas").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page


def test_restoring_a_backup_keeps_the_notes(v3_app, v3_client, v3_data):
    from fintrack.v3 import backup
    backup.before(v3_data, "test")
    add(v3_client, "Written after the backup")
    backup.restore(v3_data, backup.list_backups(v3_data)[0]["name"])
    assert [n["text"] for n in ideas.saved(v3_app)] == ["Written after the backup"]
