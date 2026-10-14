"""14 Oct 2026: the new look on a separate demo page (/demo). The normal page (/) must not change. Fake data only."""
import re

import pytest

from tests.test_web import ACME, client, db  # noqa: F401  (fixtures)

pytest.importorskip("flask")


def forms(html):
    return sorted(set(re.findall(r'action="(/[a-z/]*)"', html)))


def test_demo_page_has_the_new_name_icon_and_ring(client):
    html = client.get("/demo").get_data(as_text=True)
    assert "Where's My Money?" in html and "Payday to payday" in html
    assert 'id="ring"' in html and 'id="zring"' in html                  # the spare cash ring and the Zopa ring
    assert 'id="st-bills"' in html and 'id="st-spends"' in html         # statement rows
    assert 'class="demohead"' in html and 'id="setbtn"' in html         # fixed header with Settings
    assert 'id="editbtn"' in html and 'id="updbtn"' in html             # the buttons Settings opens
    from fintrack.appversion import VERSION
    assert f"demo.v.{VERSION}" in html                                  # which version is running


def test_demo_keeps_every_form_and_card_of_the_normal_page(client):
    normal = client.get("/").get_data(as_text=True)
    demo = client.get("/demo").get_data(as_text=True)
    assert forms(demo) == forms(normal)                                  # nothing removed
    for text in ("Add a spend", "Credit card", "Bills (every month)", "Last month's spending",
                 "Spending by category", "Subscriptions", "6 months, 12 months and this year",
                 'id="payform"', 'id="spare-big"', 'id="mfs"', 'id="leftnow"', 'id="ccused"', 'id="ccfree"'):
        assert text in demo, text


def test_normal_page_does_not_change(client):
    html = client.get("/").get_data(as_text=True)
    assert "Where does my wage go?" in html and "Where's My Money?" not in html
    assert 'id="ring"' not in html and 'id="setbtn"' not in html and "💳 Credit card" in html and "➕ Add a spend" in html


def test_changes_made_on_the_demo_go_back_to_the_demo(client):
    r = client.post("/add", data={"amount": "3.50", "name": "Costa"}, headers={"Referer": "http://localhost/demo"})
    assert r.status_code == 303 and r.headers["Location"].endswith("/demo")
    r = client.post("/add", data={"amount": "", "name": ""}, headers={"Referer": "http://localhost/demo"})
    assert "/demo?error=spend" in r.headers["Location"]
    r = client.post("/add", data={"amount": "3.50", "name": "Costa"})
    assert r.headers["Location"].endswith("/")                          # the normal page still goes home


def test_new_payday_panel_on_the_demo(client):
    html = client.get("/demo").get_data(as_text=True)
    assert 'id="quick" hidden' in html and 'id="quicktab"' in html           # hidden until the arrow tab is pressed
    panel = html[html.index('id="quick"'):html.index('class="st-grid"')]
    assert 'action="/pay"' in panel and 'id="qleft"' in panel and "Work it out" in panel
