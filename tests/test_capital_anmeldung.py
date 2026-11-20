"""Anmeldung nach 429 "Rate-Limit" (20.11.2026): POST und PUT /session neu versuchen, Orders nie."""
import pytest

from gold.bot import capital
from gold.bot.capital import CapitalClient, CapitalError, CapitalRateLimit


class Resp:
    def __init__(self, status, payload=None, text="", headers=None):
        self.status_code, self.ok, self.payload, self.text = status, status < 400, payload, text
        self.headers = headers or {}

    def json(self):
        return self.payload


OK_LOGIN = Resp(200, {"currentAccountId": "A1"}, headers={"CST": "c", "X-SECURITY-TOKEN": "t"})
LIMIT = Resp(429, text="")


class Session:
    def __init__(self, antworten):
        self.antworten, self.calls = list(antworten), []

    def request(self, method, url, **kw):
        self.calls.append((method, url.split("/api/v1")[1]))
        return self.antworten.pop(0)


@pytest.fixture
def schlaf(monkeypatch):
    gewartet = []
    monkeypatch.setattr(capital.time, "sleep", gewartet.append)
    monkeypatch.setattr(capital.random, "uniform", lambda a, b: 0.25)
    return gewartet


def test_login_is_tried_again_after_rate_limit(schlaf):
    s = Session([LIMIT, LIMIT, OK_LOGIN])
    c = CapitalClient("k", "i", "p", session=s)
    assert c.login() == {"currentAccountId": "A1"}
    assert s.calls == [("POST", "/session")] * 3
    assert schlaf == [1.75, 3.25]
    assert c.account_id == "A1"


def test_login_gives_up_after_three_more_tries_with_the_old_text(schlaf):
    s = Session([LIMIT] * 4)
    with pytest.raises(CapitalError, match="Rate-Limit erreicht für /session"):
        CapitalClient("k", "i", "p", session=s).login()
    assert len(s.calls) == 4
    assert len(schlaf) == 3 and sum(schlaf) <= sum(capital.ANMELDUNG_WARTEN) + 3 * 0.5 <= 12


def test_switch_account_is_tried_again_too(schlaf):
    s = Session([LIMIT, Resp(200, {}, headers={"CST": "c2"})])
    c = CapitalClient("k", "i", "p", session=s)
    c.account_id = "A1"
    c.switch_account("A2")
    assert s.calls == [("PUT", "/session")] * 2 and c.account_id == "A2" and c._tokens["CST"] == "c2"
    assert schlaf == [1.75]


@pytest.mark.parametrize("antwort", [Resp(401, text="error.invalid.details"), Resp(500, text="boom")])
def test_other_login_errors_are_not_retried(schlaf, antwort):
    s = Session([antwort])
    with pytest.raises(CapitalError):
        CapitalClient("k", "i", "p", session=s).login()
    assert len(s.calls) == 1 and schlaf == []


def test_an_order_is_never_sent_twice_on_rate_limit(schlaf):
    s = Session([LIMIT])
    with pytest.raises(CapitalRateLimit):
        CapitalClient("k", "i", "p", session=s).open_position("GOLD", "BUY", 0.5, stop_level=3500.0)
    assert s.calls == [("POST", "/positions")] and schlaf == []


def test_closing_is_never_sent_twice_on_rate_limit(schlaf):
    s = Session([LIMIT])
    with pytest.raises(CapitalRateLimit):
        CapitalClient("k", "i", "p", session=s).close_position("d1")
    assert s.calls == [("DELETE", "/positions/d1")] and schlaf == []


def test_rate_limit_still_counts_as_capital_error():
    assert issubclass(CapitalRateLimit, CapitalError)
