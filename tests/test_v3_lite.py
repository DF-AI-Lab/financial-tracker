"""Lite (map #22, 21 Oct 2026): /lite and /lite/demo are the main page from their own template copies. Fake data only."""
import pytest

from tests.v3_helpers import v3_data, v3_app, v3_client, ACME  # noqa: F401

pytest.importorskip("flask")


@pytest.mark.parametrize("url", ["/lite", "/lite/demo"])
def test_needs_sign_in(v3_app, url):
    assert v3_app.test_client().get(url).status_code in (302, 303)


@pytest.mark.parametrize("url", ["/lite", "/lite/demo"])
def test_same_page_and_data_as_main(v3_client, url):
    main = v3_client.get("/").get_data(as_text=True)
    lite = v3_client.get(url).get_data(as_text=True)
    assert 'class="lite">Lite</span>' in lite and 'class="lite"' not in main
    assert 'id="payform"' in lite and 'data-pay="2500.00"' in lite and 'data-pay="2500.00"' in main


def test_own_css_and_icon(v3_client):
    lite = v3_client.get("/lite").get_data(as_text=True)
    demo = v3_client.get("/lite/demo").get_data(as_text=True)
    assert 'href="/lite/static/look.css' in lite and 'href="/lite/demo/static/look.css' in demo
    for url in ("/lite/static/look.css", "/lite/demo/static/look.css", "/lite/static/icon-192.png"):
        assert v3_client.get(url).status_code == 200
    assert ".tagline .lite" in v3_client.get("/lite/static/look.css").get_data(as_text=True)
    assert ".tagline .lite" not in v3_client.get("/static/look.css").get_data(as_text=True)


def test_static_needs_sign_in_and_stays_in_its_folder(v3_app, v3_client):
    assert v3_app.test_client().get("/lite/static/look.css").status_code in (302, 303, 401)
    assert v3_client.get("/lite/static/../../v3app.py").status_code == 404
    assert v3_client.get("/lite/static/nothing.css").status_code == 404
