"""Move to Bills (user, 5 Oct 2026): last month's spending opens per category to show what was paid (payments of 4 or
more), each with a -> Bill button; subscriptions get a -> Bill button too (they stay in Subscriptions as well).
Fake data only."""
import shutil
from datetime import date

import pytest

import run
from fintrack.models import Txn
from fintrack.subs import find_subscriptions
from fintrack.store import open_db, get_items
from tests.conftest import DATA
from tests.test_payblock import block, txns


def test_each_category_lists_what_was_paid_last_month():
    tx = txns() + [Txn(date(2024, 4, 11), "VIS", "TESCO STORES", "", -3.50),     # under 4: left out of the list
                   Txn(date(2024, 4, 12), "VIS", "SPAR", "", -12.0)]
    tx.sort(key=lambda t: t.date)
    p = block(tx=tx)
    rows = {s["category"]: s for s in p["spending"]}
    assert rows["Unsorted"]["items"] == [
        {"key": "CARD|CORNER SHOP|", "name": "Corner Shop", "last": pytest.approx(150)},     # biggest first
        {"key": "CARD|SPAR|", "name": "Spar", "last": pytest.approx(12)}]
    assert [(i["name"], i["last"]) for i in rows["Food shopping"]["items"]] == [("Tesco Stores", pytest.approx(40))]
    assert rows["Food shopping"]["last"] == pytest.approx(43.5)                 # the category total still counts all


def subs_tx():
    d = [date(2024, m, 5) for m in range(1, 6)]
    return [Txn(x, "VIS", "STREAM VIDEO", "", -12.99) for x in d] + [Txn(date(2024, 5, 20), "VIS", "CORNER SHOP", "", -5.0)]


def test_subscriptions_know_their_keys_and_if_they_are_a_bill():
    s = find_subscriptions(subs_tx())["active"][0]
    assert s["keys"] == ["CARD|STREAM VIDEO|"] and s["bill"] is False
    items = {"CARD|STREAM VIDEO|": {"kind": "common", "label": "Stream Video", "source": "user"}}
    assert find_subscriptions(subs_tx(), items=items)["active"][0]["bill"] is True


@pytest.fixture
def db(tmp_path):
    inbox = tmp_path / "statements"
    inbox.mkdir()
    for n in ("statement_2024_08.pdf", "statement_2024_09.pdf", "statement_2024_10.pdf"):
        shutil.copy(DATA / n, inbox / n)
    run.main(in_dir=inbox, out_dir=tmp_path / "output", ask=lambda p: "2500", wage_payer="ACME MOTORS PLC",
             ask_items=lambda p: "")
    return tmp_path / "tracker.db"


def test_page_has_to_bill_buttons_and_folding(db):
    pytest.importorskip("flask")
    import web
    app = web.create_app(db, wage_payer="ACME MOTORS PLC", today=date(2024, 10, 25))
    app.testing = True
    client = app.test_client()
    page = client.get("/").data.decode()
    last = page.split('data-card="lastmonth"')[1].split('data-card=')[0]
    assert 'class="small tobill"' in last and 'data-key="CARD|' in last
    subs = page.split('data-card="subs"')[1].split('data-card=')[0]
    assert 'class="small tobill"' in subs
    assert 'class="fold"' in page                                              # every card can fold
    key = last.split('data-key="')[1].split('"')[0]
    client.post("/sort/save", json={"answers": [{"key": key, "kind": "bill", "label": "", "category": ""}]})
    assert get_items(open_db(db))[key]["kind"] == "common"                       # the existing save makes it a bill
