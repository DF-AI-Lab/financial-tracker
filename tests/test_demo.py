"""14 Oct 2026: the new look (built on /demo, now the main page /). The phone page keeps the old look for now. Fake data only."""
import re

import pytest

from tests.test_web import ACME, client, db  # noqa: F401  (fixtures)

pytest.importorskip("flask")

FORMS = ["/add", "/card/add", "/card/balance", "/card/limit", "/card/remove", "/layout/reset", "/left", "/pay",
         "/remove", "/stopped"]


def forms(html):
    return sorted(set(re.findall(r'action="(/[a-z/]*)"', html)))


def test_page_has_the_new_name_icon_rings_and_header(client):
    html = client.get("/").get_data(as_text=True)
    assert "Where's My Money?" in html and "Payday to payday" in html
    assert 'id="ring"' in html and 'id="zring"' in html                  # the spare cash ring and the Zopa ring
    assert 'id="st-bills"' in html and 'id="st-spends"' in html         # statement rows
    assert 'class="demohead"' in html and 'id="setbtn"' in html         # fixed header with Settings
    assert 'id="editbtn"' in html and 'id="updbtn"' in html             # the buttons Settings opens
    from fintrack.appversion import VERSION
    assert f"v{VERSION}" in html and "demo.v" not in html               # which version is running


def test_page_keeps_every_form_and_card(client):
    client.post("/add", data={"amount": "3.50", "name": "Costa"})
    client.post("/card/add", data={"amount": "40", "name": "Shell"})
    client.post("/left", data={"amount": "20"})
    html = client.get("/").get_data(as_text=True)
    assert forms(html) == FORMS
    for text in ("Add a spend", "Credit card", "Bills (every month)", "Last month's spending",
                 "Spending by category", "Subscriptions", "6 months, 12 months and this year",
                 'id="payform"', 'id="spare-big"', 'id="mfs"', 'id="leftnow"', 'id="ccused"', 'id="ccfree"'):
        assert text in html, text


def test_demo_address_goes_to_the_main_page(client):
    r = client.get("/demo")
    assert r.status_code == 302 and r.headers["Location"].endswith("/")
    r = client.post("/add", data={"amount": "3.50", "name": "Costa"})
    assert r.status_code == 303 and r.headers["Location"].endswith("/")


def test_new_payday_panel(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="quick" hidden' in html and 'id="quicktab"' in html           # hidden until the arrow tab is pressed
    panel = html[html.index('id="quick"'):html.index('class="st-grid"')]
    assert 'action="/pay"' in panel and 'id="qleft"' in panel and "Work it out" in panel


def test_bills_card_keeps_every_bill_button(client, db):
    from fintrack.home import home_data
    from fintrack.store import open_db
    n = len(home_data(open_db(db), wage_payer=ACME)["pay"]["bills"])
    html = client.get("/").get_data(as_text=True)
    assert 'class="dbills"' in html
    assert html.count('<tr class="bill') == n
    assert html.count('action="/stopped"') == n and html.count('class="amount billbox"') == n


def test_last_month_rows_and_bill_buttons(client):
    html = client.get("/").get_data(as_text=True)
    assert 'class="dlast"' in html and 'data-sort="lastmonth"' in html
    table = html.split('class="dlast"')[1].split("</table>")[0]
    assert table.count('class="item"') == table.count('class="small tobill"') > 0   # every shop row has its → Bill


def test_phone_page_keeps_the_old_look(db):
    import web
    html = web.phone_page(db, wage_payer=ACME)
    assert "Where's My Money?" not in html and "💳 Credit card" in html


def test_tags_are_split_off_the_bill_name():
    import web
    app = web.create_app(":memory:")
    f = app.jinja_env.filters["tagsplit"]
    assert f("Rent KT (Household) (BP)") == ("Rent KT", ["Household", "BP"])
    assert f("Council Tax") == ("Council Tax", [])
