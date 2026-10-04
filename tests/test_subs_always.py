"""Always a subscription (user, 4 Oct 2026): Claude, ChatGPT, Google Play and Audible are subscriptions even when they
stop and start or the price jumps about. Names copied from the user's real statements' layout (fake amounts)."""
from datetime import date

from fintrack.models import Txn
from fintrack.subs import find_subscriptions, ALWAYS


def V(d, desc, detail, amt, typ="VIS"):
    return Txn(d, typ, desc, detail, amt)


TX = [
    # overseas card payments: the shop name is on the second line
    V(date(2025, 5, 6), "INT'L 0096848406", "OPENAI *CHATGPT SU OPENAI.COM", -20.0),
    V(date(2025, 10, 1), "INT'L 0041521368", "OPENAI OPENAI.COM USD 12.00 @ 1.3377 Visa Rate", -8.97),
    V(date(2026, 6, 22), "INT'L 0067269984", "OPENAI *CHATGPT SU OPENAI.COM", -7.0),
    V(date(2026, 9, 7), "INT'L 0099212837", "ANTHROPIC* CLAUDE DUBLIN 4", -18.0),
    V(date(2026, 8, 10), "Google Play Apps", "London", -0.89),
    V(date(2026, 9, 14), "Google Play Apps", "London", -4.48),
    V(date(2026, 5, 28), "Audible UK", "adbl.co/pymt", 0.99),                 # a refund: not counted
    V(date(2026, 8, 20), "Audible UK", "adbl.co/pymt", -2.29),
    V(date(2026, 4, 16), "CASH YCSH APR16", "88 DOBWORTH @20:00 SAINSBURYS S/MKTS AUDIBLE UK", -78.49, "ATM"),
    V(date(2026, 9, 20), "CORNER SHOP", "", -5.0),                             # sets the end date
]


def subs():
    s = find_subscriptions(TX)
    return {x["name"]: x for x in s["active"]}, {x["name"]: x for x in s["stopped"]}


def test_the_list():
    assert [name for name, _ in ALWAYS] == ["Claude", "ChatGPT", "Google Play", "Audible"]


def test_always_subscriptions_show_even_paid_once_or_on_and_off():
    active, stopped = subs()
    assert set(active) == {"Claude", "Google Play", "Audible"}
    assert set(stopped) == {"ChatGPT"}                                          # last paid 22 Jun, 90 days before
    assert active["Claude"]["usual"] == 18.0 and active["Claude"]["months"] == 1
    assert active["Google Play"]["usual"] == 4.48 and active["Google Play"]["total"] == 0.89 + 4.48
    assert stopped["ChatGPT"]["total"] == 20.0 + 8.97 + 7.0                    # every OpenAI payment, one entry
    assert stopped["ChatGPT"]["since"] == date(2025, 5, 6) and stopped["ChatGPT"]["last"] == date(2026, 6, 22)


def test_cash_and_refunds_are_not_counted():
    active, _ = subs()
    assert active["Audible"]["total"] == 2.29                                   # not the cash line, not the refund


def test_a_one_off_answer_does_not_hide_them():
    items = {"CARD|ANTHROPIC CLAUDE DUBLIN|": {"kind": "oneoff", "label": "", "source": "user"}}
    s = find_subscriptions(TX, items=items)
    assert "Claude" in [x["name"] for x in s["active"]]
