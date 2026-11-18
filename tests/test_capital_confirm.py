"""Bestätigung nach 404 "error.not-found.dealReference" (18.11.2026): nachlesen, die Order nie wiederholen."""
import pytest

from gold.bot import capital
from gold.bot.capital import CapitalClient, CapitalError

UNBEKANNT = '{"errorCode":"error.not-found.dealReference"}'


class Resp:
    def __init__(self, status, payload=None, text=""):
        self.status_code, self.ok, self.payload, self.text, self.headers = status, status < 400, payload, text, {}

    def json(self):
        return self.payload


class Session:
    """Antwortet auf POST /positions mit einer dealReference und auf GET /confirms nacheinander mit `antworten`."""

    def __init__(self, antworten):
        self.antworten, self.calls = list(antworten), []

    def request(self, method, url, **kw):
        self.calls.append((method, url.split("/api/v1")[1]))
        if method == "POST":
            return Resp(200, {"dealReference": "o_1"})
        return self.antworten.pop(0)


@pytest.fixture
def schlaf(monkeypatch):
    gewartet = []
    monkeypatch.setattr(capital.time, "sleep", gewartet.append)
    return gewartet


def test_unknown_reference_is_read_again_and_the_order_is_sent_once(schlaf):
    s = Session([Resp(404, text=UNBEKANNT), Resp(404, text=UNBEKANNT), Resp(200, {"dealStatus": "ACCEPTED"})])
    res = CapitalClient("k", "i", "p", session=s).open_position("GOLD", "SELL", 0.08, stop_level=3922.17)
    assert res == {"dealStatus": "ACCEPTED"}
    assert s.calls == [("POST", "/positions")] + [("GET", "/confirms/o_1")] * 3
    assert schlaf == [0.5, 1.0]


def test_close_confirm_is_read_again_too(schlaf):
    s = Session([Resp(404, text=UNBEKANNT), Resp(200, {"dealStatus": "ACCEPTED", "level": 3770.1})])
    s.request = (lambda alt: (lambda m, u, **kw: Resp(200, {"dealReference": "o_2"}) if m == "DELETE"
                              else alt(m, u, **kw)))(s.request)
    assert CapitalClient("k", "i", "p", session=s).close_position("d1")["level"] == 3770.1
    assert schlaf == [0.5]


def test_gives_up_after_four_more_reads(schlaf):
    s = Session([Resp(404, text=UNBEKANNT)] * 5)
    with pytest.raises(CapitalError, match="not-found.dealReference"):
        CapitalClient("k", "i", "p", session=s).confirm("o_1")
    assert len(s.calls) == 5 and schlaf == list(capital.BESTAETIGUNG_WARTEN)
    assert sum(schlaf) <= 6.5


@pytest.mark.parametrize("antwort", [Resp(500, text="boom"), Resp(404, text='{"errorCode":"error.not-found.x"}'),
                                     Resp(429, text="")])
def test_other_errors_are_not_retried(schlaf, antwort):
    s = Session([antwort])
    with pytest.raises(CapitalError):
        CapitalClient("k", "i", "p", session=s).confirm("o_1")
    assert len(s.calls) == 1 and schlaf == []
