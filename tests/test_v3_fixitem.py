"""v3 Settings -> Fix an item (14 Oct 2026): /fix lists every saved item, /fix/save changes one. Fake data only."""
import re

import pytest

from fintrack.store import get_categories, get_items, open_db, set_item
from tests.v3_helpers import v3_data, v3_app, ACME  # noqa: F401


@pytest.fixture
def client(v3_app):
    """Like client, but also works before fintrack/v3/auth.py exists (that import raises ImportError)."""
    c = v3_app.test_client()
    try:
        from fintrack.v3 import auth
    except ImportError:
        return c
    auth.sign_in_for_tests(v3_app, c)
    return c


def db(v3_data):
    return open_db(v3_data / "tracker.db")


def keys_in_order(html):
    return re.findall(r'data-key="([^"]+)"', html)


def test_fix_page_lists_every_saved_item(client, v3_data):
    r = client.get("/fix")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    items = get_items(db(v3_data))
    assert items
    assert set(keys_in_order(html)) == set(items)
    assert len(keys_in_order(html)) == len(items)
    assert "Council Tax" in html and "Petrol Station" in html
    assert "Direct debit" in html and "Household" in html
    assert "1 Oct 2024" in html                      # Council Tax last paid
    assert "£161.00" in html                         # its average
    assert 'href="/"' in html                        # Back


def test_fix_page_shows_kind_words(client, v3_data):
    html = client.get("/fix").get_data(as_text=True)
    rent = html.split('data-key="SO|SAM PARKER|RENT"')[1].split("data-key=")[0]
    assert 'class="pill bill">Bill<' in rent
    shop = html.split('data-key="CARD|FURNITURE STORE|"')[1].split("data-key=")[0]
    assert 'class="pill random">Random<' in shop


def test_fix_page_newest_paid_first(client, v3_data):
    conn = db(v3_data)
    set_item(conn, "DD|OLD GYM|", "common", "Old Gym", "user")      # saved, never paid: last
    conn.close()
    keys = keys_in_order(client.get("/fix").get_data(as_text=True))
    assert keys[0] == "CARD|STREAM VIDEO|"                           # 15 Oct
    assert keys.index("CARD|PETROL STATION|") < keys.index("CARD|TACO PLACE|") < keys.index("DD|ENERGY CO|")
    assert keys.index("DD|ENERGY CO|") < keys.index("CASH|CASH MACHINE|") < keys.index("CARD|CHIROPRACTOR|")
    assert keys[-1] == "DD|OLD GYM|"


def test_fix_page_has_categories_for_the_box(client):
    html = client.get("/fix").get_data(as_text=True)
    assert "<datalist" in html and 'value="Food shopping"' in html


def test_save_changes_kind_category_and_name(client, v3_data):
    r = client.post("/fix/save", json={"key": "CARD|FURNITURE STORE|", "kind": "oneoff",
                                          "label": "New sofa", "category": "Home"})
    assert r.status_code == 200
    out = r.get_json()
    assert out["kind"] == "oneoff" and out["label"] == "New sofa" and out["category"] == "Home"
    conn = db(v3_data)
    item = get_items(conn)["CARD|FURNITURE STORE|"]
    assert item["kind"] == "oneoff" and item["label"] == "New sofa" and item["source"] == "user"
    assert get_categories(conn)["CARD|FURNITURE STORE|"] == "Home"


def test_save_bill_and_yearly(client, v3_data):
    assert client.post("/fix/save", json={"key": "CARD|TACO PLACE|", "kind": "bill", "label": "Tacos",
                                             "category": ""}).status_code == 200
    assert client.post("/fix/save", json={"key": "DD|TV LICENCE|", "kind": "yearly", "label": "TV Licence",
                                             "category": "Household"}).status_code == 200
    items = get_items(db(v3_data))
    assert items["CARD|TACO PLACE|"]["kind"] == "common"
    assert items["DD|TV LICENCE|"]["kind"] == "yearly"
    html = client.get("/fix").get_data(as_text=True)
    tv = html.split('data-key="DD|TV LICENCE|"')[1].split("data-key=")[0]
    assert 'class="pill yearly">Yearly<' in tv


def test_save_bad_kind_is_refused(client, v3_data):
    before = get_items(db(v3_data))
    r = client.post("/fix/save", json={"key": "DD|GYM CLUB|", "kind": "weekly", "label": "X", "category": "Y"})
    assert r.status_code == 400
    assert r.get_data(as_text=True).strip()
    assert get_items(db(v3_data)) == before
    assert get_categories(db(v3_data))["DD|GYM CLUB|"] == "Unsorted"


def test_save_unknown_or_bad_key_is_refused(client, v3_data):
    before = get_items(db(v3_data))
    for key in ("DD|NOT SAVED|", "nonsense", ""):
        r = client.post("/fix/save", json={"key": key, "kind": "bill", "label": "X", "category": "Y"})
        assert r.status_code == 400
    assert client.post("/fix/save", data="not json").status_code == 400
    assert get_items(db(v3_data)) == before
