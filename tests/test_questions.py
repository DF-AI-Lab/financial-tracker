import pytest

from fintrack.questions import fix_items, item_stats, parse_answer, pending_items, review, suggest
from fintrack.store import get_items, open_db, set_item
from tests.synth import synth_txns

TXNS = synth_txns()


def stats():
    return item_stats(TXNS)


def test_item_stats():
    s = stats()
    assert len(s) == 9                               # only money OUT: no wage, bonus, family credit
    rent = s["SO|LANDLORD|RENT"]
    assert rent["group"] == "SO" and rent["name"] == "LANDLORD" and rent["reference"] == "RENT"
    assert rent["count"] == 8 and rent["months"] == 8
    assert rent["total"] == pytest.approx(4400.0) and rent["average"] == pytest.approx(550.0)
    assert rent["last"] == "2024-09-01"
    assert s["CARD|CAR DEALER|"]["count"] == 1 and s["CARD|CAR DEALER|"]["total"] == pytest.approx(10377.0)
    assert s["CARD|BARBER|"]["count"] == 3


def test_suggestions():
    s = stats()
    want = {
        "SO|LANDLORD|RENT": ("common", "Rent"),
        "DD|GYM CLUB|": ("common", "Gym Club"),
        "DD|ENERGY CO|": ("common", "Energy Co"),
        "CARD|STREAM VIDEO|": ("common", "Stream Video"),      # 8 payments, all 12.99
        "CASH|CASH MACHINE|": ("common", "Cash Machine"),      # 4 payments, all 50
        "CARD|CORNER SHOP|": ("random", "Corner Shop"),        # amounts all over the place
        "CARD|BARBER|": ("random", "Barber"),                  # only 3 payments
        "CARD|CAR DEALER|": ("oneoff", "Car Dealer"),          # one payment of 1000 or more
        "CARD|EARLY SHOP|": ("random", "Early Shop"),
    }
    for key, w in want.items():
        assert suggest(s[key]) == w, key


def test_pending_items_order_and_filters():
    s = stats()
    p = pending_items(s, {})
    assert [x["key"] for x in p] == [
        "CARD|CAR DEALER|", "SO|LANDLORD|RENT", "DD|ENERGY CO|", "DD|GYM CLUB|", "CASH|CASH MACHINE|",
        "CARD|CORNER SHOP|", "CARD|STREAM VIDEO|", "CARD|BARBER|", "CARD|EARLY SHOP|"]
    p2 = pending_items(s, {"SO|LANDLORD|RENT": {"kind": "regular", "label": "", "source": "user"}},
                       skip={"DD|GYM CLUB|"})
    assert "SO|LANDLORD|RENT" not in [x["key"] for x in p2] and "DD|GYM CLUB|" not in [x["key"] for x in p2]
    assert len(p2) == 7


@pytest.mark.parametrize("text,count,kinds,labels,later,stop", [
    ("", 10, {}, {}, set(), False),
    ("common 1 2 4  oneoff 6", 10, {1: "common", 2: "common", 4: "common", 6: "oneoff"}, {}, set(), False),
    ("Common 1-3", 10, {1: "common", 2: "common", 3: "common"}, {}, set(), False),
    ("one-off 2  REGULAR 5  random 7 8", 10, {2: "oneoff", 5: "common", 7: "random", 8: "random"}, {}, set(), False),
    ("later 3 5", 10, {}, {}, {3, 5}, False),
    ("stop", 10, {}, {}, set(), True),
    ("label 1 Rent", 10, {}, {1: "Rent"}, set(), False),
    ("label 2 Katie top-ups  common 3", 10, {3: "common"}, {2: "Katie top-ups"}, set(), False),
])
def test_parse_answer_ok(text, count, kinds, labels, later, stop):
    r = parse_answer(text, count)
    assert r["error"] is None
    assert (r["kinds"], r["labels"], r["later"], r["stop"]) == (kinds, labels, later, stop)


@pytest.mark.parametrize("text,mention", [("common 12", "12"), ("common 0", "0"), ("banana", "banana"),
                                          ("common", "common"), ("label Rent", "label")])
def test_parse_answer_errors(text, mention):
    r = parse_answer(text, 10)
    assert r["error"] and mention in r["error"]


def runner(*replies):
    it = iter(replies)
    calls = []

    def ask(prompt):
        calls.append(prompt)
        r = next(it) if replies else ""
        if isinstance(r, Exception):
            raise r
        return r
    ask.calls = calls
    return ask


def test_accepting_suggestions_saves_everything_once():
    conn, lines = open_db(":memory:"), []
    ask = runner()                                 # always answers "" (Enter)
    assert review(conn, TXNS, ask, out=lines.append, size=4, auto_dd=False) == 9
    assert len(ask.calls) == 3                     # rounds of 4, 4 and 1
    items = get_items(conn)
    assert len(items) == 9
    assert items["CARD|CAR DEALER|"]["kind"] == "oneoff" and items["CARD|CAR DEALER|"]["source"] == "suggested"
    assert items["SO|LANDLORD|RENT"] == {"kind": "common", "label": "Rent", "source": "suggested"}
    text = "\n".join(lines)
    assert "NEW ITEMS" in text and "Standing order" in text and "LANDLORD - RENT" in text
    assert "suggest: One-off" in text and "550.00" in text
    # never asked twice
    ask2 = runner()
    assert review(conn, TXNS, ask2, out=lines.append, size=4, auto_dd=False) == 0
    assert ask2.calls == []


def test_typed_answers_override_suggestions():
    conn = open_db(":memory:")
    # round 1 order: 1 CAR DEALER, 2 RENT, 3 ENERGY, 4 GYM
    ask = runner("common 1 3  random 2  label 2 Landlord rent", "", "")
    review(conn, TXNS, ask, out=lambda s: None, size=4, auto_dd=False)
    items = get_items(conn)
    assert items["CARD|CAR DEALER|"]["kind"] == "common" and items["CARD|CAR DEALER|"]["source"] == "user"
    assert items["DD|ENERGY CO|"]["kind"] == "common"
    assert items["SO|LANDLORD|RENT"] == {"kind": "random", "label": "Landlord rent", "source": "user"}
    assert items["DD|GYM CLUB|"]["source"] == "suggested"      # not mentioned: suggestion kept


def test_later_skips_now_and_asks_again_next_run():
    conn = open_db(":memory:")
    ask = runner("later 1 2", "", "")
    assert review(conn, TXNS, ask, out=lambda s: None, size=4, auto_dd=False) == 7
    items = get_items(conn)
    assert "CARD|CAR DEALER|" not in items and "SO|LANDLORD|RENT" not in items
    assert len(ask.calls) == 3                     # not asked about them again in the same run
    again = runner("")
    assert review(conn, TXNS, again, out=lambda s: None, size=4, auto_dd=False) == 2
    assert len(again.calls) == 1
    assert "CARD|CAR DEALER|" in get_items(conn)


def test_stop_saves_nothing_from_that_round():
    conn = open_db(":memory:")
    ask = runner("", "stop")
    assert review(conn, TXNS, ask, out=lambda s: None, size=4, auto_dd=False) == 4
    assert len(get_items(conn)) == 4 and len(ask.calls) == 2


def test_bad_answer_is_asked_again():
    conn, lines = open_db(":memory:"), []
    ask = runner("banana", "", "", "")
    assert review(conn, TXNS, ask, out=lines.append, size=4, auto_dd=False) == 9
    assert len(ask.calls) == 4
    assert any(l.startswith("Sorry, I did not understand:") for l in lines)


@pytest.mark.parametrize("err", [EOFError(), OSError()])
def test_no_keyboard_stops_quietly(err):
    conn = open_db(":memory:")
    assert review(conn, TXNS, runner(err), out=lambda s: None, size=4, auto_dd=False) == 0
    assert get_items(conn) == {}


def test_fix_items_changes_saved_answers():
    conn, lines = open_db(":memory:"), []
    review(conn, TXNS, runner(), out=lambda s: None, size=10, auto_dd=False)
    ask = runner("common 1  label 2 Car")
    assert fix_items(conn, ask, out=lines.append) == 2
    text = "\n".join(lines)
    assert "SAVED ITEMS" in text and "(suggested)" in text and "CARD|BARBER|" in text
    items = get_items(conn)            # sorted by key: 1 CARD|BARBER|, 2 CARD|CAR DEALER|
    assert items["CARD|BARBER|"]["kind"] == "common" and items["CARD|BARBER|"]["source"] == "user"
    assert items["CARD|CAR DEALER|"]["label"] == "Car" and items["CARD|CAR DEALER|"]["kind"] == "oneoff"


def test_fix_items_ignores_bad_input_and_no_keyboard():
    conn, lines = open_db(":memory:"), []
    set_item(conn, "DD|GYM CLUB|", "regular", "Gym")
    assert fix_items(conn, runner("banana"), out=lines.append) == 0
    assert any(l.startswith("Sorry, I did not understand:") for l in lines)
    assert fix_items(conn, runner(EOFError()), out=lambda s: None) == 0
    assert get_items(conn)["DD|GYM CLUB|"]["kind"] == "regular"


def test_bill_payment_top_ups_are_always_suggested_random():
    from datetime import date
    from fintrack.models import Txn
    txns = [Txn(date(2024, m, 10), "BP", "SAM PARKER", "Food and bil", -20.0) for m in range(1, 9)]  # 8 identical top-ups
    stat = item_stats(txns)["BP|SAM PARKER|FOOD AND BIL"]
    assert suggest(stat) == ("random", "Food And Bil")


def test_the_word_regular_is_shown_as_common(capsys):
    from fintrack.questions import KIND_NAMES
    assert KIND_NAMES["regular"] == KIND_NAMES["common"] == "Common"


def test_parse_answer_all_keyword():
    assert parse_answer("all", 10)["all"] is True and parse_answer("all", 10)["error"] is None
    r = parse_answer("common 1  all", 10)
    assert r["all"] is True and r["kinds"] == {1: "common"}
    assert parse_answer("common 1", 10)["all"] is False and parse_answer("", 10)["all"] is False


def test_all_accepts_suggestions_for_everything_left():
    conn = open_db(":memory:")
    ask = runner("all")
    assert review(conn, TXNS, ask, out=lambda s: None, size=4, auto_dd=False) == 9
    assert len(ask.calls) == 1 and len(get_items(conn)) == 9
    assert get_items(conn)["CARD|CAR DEALER|"]["kind"] == "oneoff"


def test_all_still_respects_typed_answers_and_later():
    conn = open_db(":memory:")
    ask = runner("common 1  later 2  label 3 Power  all")      # round 1: 1 CAR DEALER, 2 RENT, 3 ENERGY, 4 GYM
    assert review(conn, TXNS, ask, out=lambda s: None, size=4, auto_dd=False) == 8
    items = get_items(conn)
    assert items["CARD|CAR DEALER|"]["kind"] == "common" and items["CARD|CAR DEALER|"]["source"] == "user"
    assert "SO|LANDLORD|RENT" not in items                      # 'later' is still skipped
    assert items["DD|ENERGY CO|"]["label"] == "Power"
    assert items["CARD|BARBER|"]["source"] == "suggested"       # from a later round, taken as suggested


def test_skip_small_does_not_ask_about_tiny_one_offs():
    conn, lines = open_db(":memory:"), []
    ask = runner()
    assert review(conn, TXNS, ask, out=lines.append, size=10, skip_small=True, auto_dd=False) == 8
    assert "CARD|EARLY SHOP|" not in get_items(conn)            # 1 payment of 5.00
    assert "EARLY SHOP" not in "\n".join(lines)
    assert "CARD|BARBER|" in get_items(conn)                    # 3 payments: kept
