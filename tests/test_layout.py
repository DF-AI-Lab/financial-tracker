"""Home page layout (3 Oct 2026): drag cards and rows into the user's order, rename rows. Kept for good in the kv
table (page only: the bills, items and the terminal are not changed). Fake data only."""
from fintrack.layout import apply_order, get_layout, save_order, set_name, reset_order, CARDS
from fintrack.store import open_db, get_items


def test_apply_order_keeps_new_rows_at_the_bottom():
    rows = [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}]
    out = apply_order(rows, ["c", "gone", "a"], key=lambda r: r["id"])
    assert [r["id"] for r in out] == ["c", "a", "b", "d"]
    assert apply_order(rows, [], key=lambda r: r["id"]) == rows


def test_order_and_names_are_kept(tmp_path):
    conn = open_db(tmp_path / "t.db")
    assert get_layout(conn) == {"order": {}, "names": {}}
    save_order(conn, "bills", ["bill:B", "bill:A"])
    save_order(conn, "cards", ["subs", "bills"])
    set_name(conn, "bill:DD|CITY OF YORK|", "Council Tax")
    lay = get_layout(conn)
    assert lay["order"] == {"bills": ["bill:B", "bill:A"], "cards": ["subs", "bills"]}
    assert lay["names"] == {"bill:DD|CITY OF YORK|": "Council Tax"}
    set_name(conn, "bill:DD|CITY OF YORK|", "  ")                     # empty = back to the bank's name
    assert get_layout(conn)["names"] == {}
    reset_order(conn)
    assert get_layout(conn)["order"] == {}
    assert get_items(conn) == {}                                       # bills untouched
    assert "bills" in CARDS and "subs" in CARDS
