"""Subscription spotter (Oct 2026): small card payments most months, so you can see what you are still paying for
(the user's HPI Instant Ink ran for months unnoticed). Fake data only."""
import shutil
from datetime import date

import pytest

import run
from fintrack.models import Txn
from fintrack.subs import find_subscriptions, format_subscriptions
from tests.conftest import DATA


def T(m, d, desc, amt, typ="VIS"):
    return Txn(date(2024, m, d), typ, desc, "", -amt)


def txns():
    tx = []
    for m in range(1, 7):
        tx += [T(m, 5, "NETFLIX", 10.99), T(m, 6, "GYM CLUB", 31.0 if m == 2 else 30.0),
               T(m, 7, "BIG BOX", 80.0),                      # too big for a subscription
               T(m, 8, "IVA CO", 20.0),                       # answered one-off below
               T(m, 9, "WATER CO", 25.0, "DD")]               # a direct debit is a bill, not a card subscription
    tx += [T(m, 5, "HPI INSTANT INK", 2.99) for m in (1, 2, 3)]           # stopped after March
    tx += [T(1, 10, "HPI INSTANT INK", 2.99)]                             # twice in January: still one month
    tx += [T(1, 11, "TWICE ONLY", 5.0), T(2, 11, "TWICE ONLY", 5.0)]     # only 2 months
    tx += [T(m, 12, "CORNER SHOP", a) for m, a in [(1, 3.0), (2, 9.0), (3, 20.0), (4, 6.0)]]   # amounts all over
    tx.append(T(6, 20, "LAST THING", 1.0))                                # the newest payment: 20 Jun
    return sorted(tx, key=lambda t: t.date)


ITEMS = {"CARD|IVA CO|": {"kind": "oneoff", "label": "", "source": "user"},
         "CARD|NETFLIX|": {"kind": "common", "label": "Telly", "source": "user"}}


def test_find_subscriptions():
    s = find_subscriptions(txns(), items=ITEMS)
    assert [(a["name"], a["usual"], a["since"], a["last"], a["total"], a["months"]) for a in s["active"]] == [
        ("Gym Club", pytest.approx(30), date(2024, 1, 6), date(2024, 6, 6), pytest.approx(181), 6),
        ("Telly", pytest.approx(10.99), date(2024, 1, 5), date(2024, 6, 5), pytest.approx(65.94), 6)]
    assert [(a["name"], a["usual"], a["since"], a["last"], a["total"], a["months"]) for a in s["stopped"]] == [
        ("Hpi Instant Ink", pytest.approx(2.99), date(2024, 1, 5), date(2024, 3, 5), pytest.approx(11.96), 3)]


def test_format_subscriptions():
    assert format_subscriptions(find_subscriptions(txns(), items=ITEMS)) == [
        "SUBSCRIPTIONS (card payments most months)",
        "  Still paying:",
        f"    {'Gym Club':<24}{'30.00':>8} a month   since Jan 2024   paid 181.00 so far",
        f"    {'Telly':<24}{'10.99':>8} a month   since Jan 2024   paid 65.94 so far",
        f"    {'Total':<24}{'40.99':>8} a month",
        "  Stopped:",
        f"    {'Hpi Instant Ink':<24}{'2.99':>8} a month   Jan 2024 to Mar 2024   paid 11.96",
    ]


def test_nothing_found():
    s = find_subscriptions([T(1, 1, "CORNER SHOP", 5.0)])
    assert s == {"active": [], "stopped": []}
    assert format_subscriptions(s) == ["SUBSCRIPTIONS: none found."]


def test_run_prints_subscriptions_after_the_pay_block(tmp_path, capsys):
    inbox = tmp_path / "statements"
    inbox.mkdir()
    for n in ("statement_2024_08.pdf", "statement_2024_09.pdf", "statement_2024_10.pdf"):
        shutil.copy(DATA / n, inbox / n)
    run.main(in_dir=inbox, out_dir=tmp_path / "output", ask=lambda p: "2500", wage_payer="ACME MOTORS PLC",
             ask_items=lambda p: "")
    text = capsys.readouterr().out
    assert "SUBSCRIPTION" in text and text.index("SPARE CASH") < text.index("SUBSCRIPTION")


def test_a_shop_now_and_then_is_not_a_subscription():
    # Real oddity (Oct 2026): Sainsburys, Tesco and Taco Bell showed as stopped subscriptions: a similar amount in
    # 3 months, but spread over a year. A subscription is (nearly) the same price in most months of its run.
    tx = [T(1, 3, "SAINSBURYS", 40.0), T(5, 3, "SAINSBURYS", 40.5), T(11, 3, "SAINSBURYS", 39.8),
          T(2, 3, "SAINSBURYS", 12.0), T(7, 3, "SAINSBURYS", 75.0),
          T(3, 1, "TAKEAWAY", 18.0), T(4, 1, "TAKEAWAY", 20.5), T(5, 1, "TAKEAWAY", 18.4),    # 20.5 is 11% off
          T(12, 20, "LAST THING", 1.0)]
    s = find_subscriptions(sorted(tx, key=lambda t: t.date))
    assert s == {"active": [], "stopped": []}


def test_a_missed_month_is_still_a_subscription():
    tx = [T(m, 5, "MUSIC APP", 9.99) for m in (1, 2, 4, 5, 6)] + [T(6, 20, "LAST THING", 1.0)]   # March missed
    assert [a["name"] for a in find_subscriptions(tx)["active"]] == ["Music App"]
