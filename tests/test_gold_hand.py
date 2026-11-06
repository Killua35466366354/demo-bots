"""Tests für gold/hand_bot.py: Short und Long ohne Stop und Ziel, nur auf Konto 5, nie gegen eine offene Position,
Grenzen, Nachricht über ntfy, Kirons eigene Schlüsse werden gebucht, nur eigene Dateien."""
import pandas as pd
import pytest

from gold import hand_bot as hb
from gold import short_bot as sb
from tests.test_gold_short import HAUPT, NOW, Konto, _bars_fuer, _signal


RSS = (b'<?xml version="1.0"?><rss><channel>'
       b'<item><title>Gold slips as dollar firms - Reuters</title><pubDate>Wed, 04 Mar 2026 14:50:00 GMT</pubDate></item>'
       b'<item><title>Alte Meldung</title><pubDate>Tue, 03 Mar 2026 01:00:00 GMT</pubDate></item>'
       b'</channel></rss>')


class Holen:
    """Ersetzt das Netz: ForexFactory-Kalender und Google-News-RSS."""

    def __init__(self, ff=None):
        self.ff = ff or []
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        ff, rss = self.ff, RSS
        return type("R", (), {"json": lambda s: ff, "content": rss})()


def _kerzen_preise(start, n, freq, schritt, kurs=4000.0):
    idx = pd.date_range(start, periods=n, freq=freq)
    out = []
    for i, t in enumerate(idx):
        c = kurs + i * schritt
        px = lambda v: {"bid": v, "ask": v + 0.3}
        out.append({"snapshotTimeUTC": t.strftime("%Y-%m-%dT%H:%M:%S"), "openPrice": px(c), "highPrice": px(c + 1),
                    "lowPrice": px(c - 1), "closePrice": px(c)})
    return out


class HandKonto(Konto):
    trend = 0.0                                  # >0: Gold steigt auf Tag und 4 Std., <0: fällt, 0: keine Kerzen

    def prices(self, epic, resolution, max_bars):
        if not self.trend:
            return []
        if resolution == "DAY":
            return _kerzen_preise("2025-12-01", 80, "1D", self.trend)
        return _kerzen_preise("2026-02-12", 120, "4h", self.trend)

    def accounts(self):
        return [{"accountId": HAUPT, "balance": {"balance": 990.0, "available": 900.0}},
                {"accountId": hb.KONTO, "balance": {"balance": 1000.0, "available": 1000.0}}]

    def positions(self):
        assert self.account_id == hb.KONTO, "Gold-Hand-Bot darf nur auf Konto 5 Positionen lesen"
        return [{"market": {"epic": "GOLD"}, "position": p} for p in self.pos.values()] + self.fremd

    def _request(self, method, path, json=None):
        assert self.account_id == hb.KONTO
        self.calls.append((method, path, json))
        self.nr += 1
        ref = f"R{self.nr}"
        if method == "POST" and path == "/positions":
            deal = f"D{self.nr}"
            lvl = self.offer if json["direction"] == "BUY" else self.bid
            self.pos[deal] = {"dealId": deal, "level": lvl, "size": json["size"], "direction": json["direction"]}
            self.refs[ref] = {"dealStatus": "ACCEPTED", "affectedDeals": [{"dealId": deal}], "level": lvl}
        return type("A", (), {"json": lambda s: {"dealReference": ref}})()


@pytest.fixture
def welt(monkeypatch):
    modell = {"trades": {s: [] for s in sb.SEITEN}, "kerzen": None}

    def simuliere(b, n=None):
        n = len(b) - 1 if n is None else n
        return {s: [dict(t, _j0=n if t["_j0"] == "jetzt" else t["_j0"]) for t in trs]
                for s, trs in modell["trades"].items()}, {}

    from gold.bot import rules
    monkeypatch.setattr(rules, "bars_from_prices", lambda prices, now, tf: modell["kerzen"])
    monkeypatch.setattr(sb, "simuliere", simuliere)
    monkeypatch.setattr(hb, "vorab_ok", lambda: True)
    modell["holen"] = Holen()
    monkeypatch.setattr(hb, "_holen", lambda url: modell["holen"](url))
    modell["kerzen"] = _bars_fuer(NOW)
    return modell


def _long(**kw):
    return dict(_signal(**kw), richtung=1)


class Post:
    def __init__(self):
        self.calls = []

    def __call__(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        return type("R", (), {"status_code": 200})()


def test_short_ohne_stop_und_ziel_mit_nachricht(welt, monkeypatch):
    monkeypatch.setenv("NTFY_THEMA", "gold-hand-test")
    welt["trades"]["gross_box_kerze"] = [_signal(dist=20.0)]
    welt["trades"]["gross_box"] = [_signal(dist=30.0)]                  # gleicher Einstieg: die erste Seite gilt
    k, post = HandKonto(), Post()
    st, log, _, msg = hb.run(k, {}, NOW, post=post)
    posts = [c for c in k.calls if c[0] == "POST"]
    assert len(posts) == 1
    body = posts[0][2]
    assert body["direction"] == "SELL" and "stopDistance" not in body and "profitDistance" not in body
    assert body["size"] == 0.27                                          # 5 € je 20 $ bei EUR/USD 1,08
    assert st["offen"][0]["seite"] == "gross_box_kerze" and st["offen"][0]["stop_strategie"] == 4020.0
    assert len(post.calls) == 1 and post.calls[0][1]["topic"] == "gold-hand-test"
    assert "SHORT eröffnet" in post.calls[0][1]["title"] and "Ohne Stop" in post.calls[0][1]["message"]
    assert k.account_id == HAUPT                                         # zurück aufs Hauptkonto
    # Nächster Lauf mit derselben Kerze: nichts Neues, keine zweite Nachricht
    st2, _, _, msg2 = hb.run(k, st, NOW, post=post)
    assert len([c for c in k.calls if c[0] == "POST"]) == 1 and not msg2 and len(post.calls) == 1


def test_long_nur_ohne_short_in_der_kerze(welt):
    welt["trades"]["gross_klein_3"] = [_long()]
    k = HandKonto()
    st, _, _, _ = hb.run(k, {}, NOW, post=Post())
    assert [c[2]["direction"] for c in k.calls if c[0] == "POST"] == ["BUY"]
    assert st["offen"][0]["richtung"] == 1 and st["offen"][0]["stop_strategie"] == round(4000.3 - 20.0, 2)
    # Short und Long in derselben Kerze: der Short gilt
    welt["trades"]["gross_box"] = [_signal()]
    k2 = HandKonto()
    hb.run(k2, {}, NOW, post=Post())
    assert [c[2]["direction"] for c in k2.calls if c[0] == "POST"] == ["SELL"]


def test_nie_gegen_eine_offene_position(welt):
    welt["trades"]["gross_klein_3"] = [_long()]
    k, post = HandKonto(), Post()
    k.fremd = [{"market": {"epic": "GOLD"}, "position": {"dealId": "K1", "direction": "SELL", "size": 0.5}}]
    st, log, _, msg = hb.run(k, {}, NOW, post=post)
    assert not [c for c in k.calls if c[0] == "POST"] and not st["offen"]
    assert msg and "nicht eröffnet" in msg[0]["titel"] and "andere Richtung" in msg[0]["text"]


def test_grenzen(welt):
    welt["trades"]["gross_klein_3"] = [_signal()]
    k = HandKonto()
    k.fremd = [{"market": {"epic": "GOLD"}, "position": {"dealId": f"K{i}", "direction": "SELL", "size": 0.1}}
               for i in range(4)]
    st, log, _, _ = hb.run(k, {}, NOW, post=Post())
    assert not st["offen"] and any("schon 4" in g for g in log[-2]["gruende"])
    k2 = HandKonto()
    k2.fremd = [{"market": {"epic": "GOLD"}, "position": {"dealId": "K1", "direction": "SELL", "size": 1.9}}]
    st2, log2, _, _ = hb.run(k2, {}, NOW, post=Post())
    assert not st2["offen"] and any("Unzen" in g for g in log2[-2]["gruende"])


def test_altes_signal_und_vorab(welt, monkeypatch):
    welt["trades"]["gross_klein_3"] = [_signal()]
    spaet = (pd.Timestamp(NOW) + pd.Timedelta("40min")).to_pydatetime()
    welt["kerzen"] = _bars_fuer(NOW)
    st, log, _, msg = hb.run(HandKonto(), {}, spaet, post=Post())
    assert not st["offen"] and not msg
    monkeypatch.setattr(hb, "vorab_ok", lambda: False)
    st2, _, _, msg2 = hb.run(HandKonto(), {}, NOW, post=Post())
    assert not st2["offen"] and not msg2


def test_kirons_schluss_wird_gebucht(welt, monkeypatch):
    from suche import demo_bots
    welt["trades"]["gross_klein_3"] = [_signal()]
    k = HandKonto()
    st, _, _, _ = hb.run(k, {}, NOW, post=Post())
    deal = st["offen"][0]["dealId"]
    k.pos.pop(deal)                                                       # Kiron schließt in der App
    monkeypatch.setattr(demo_bots, "broker_exit", lambda client, op, now, until=None: (3990.0, "USER"))
    welt["trades"]["gross_klein_3"] = []
    st2, _, fertig, _ = hb.run(k, st, NOW, post=Post())
    assert not st2["offen"] and fertig[0]["r"] == 0.5 and fertig[0]["pnl_eur"] == round(10 * 0.27 / 1.08, 2)


def test_trockenlauf_ohne_order_und_ohne_nachricht(welt, monkeypatch):
    monkeypatch.setenv("NTFY_THEMA", "gold-hand-test")
    welt["trades"]["gross_klein_3"] = [_signal()]
    k, post = HandKonto(), Post()
    st, log, _, _ = hb.run(k, {}, NOW, send_orders=False, post=post)
    assert not [c for c in k.calls if c[0] == "POST"] and not post.calls and not st["offen"]


def test_ohne_thema_keine_nachricht(monkeypatch):
    monkeypatch.delenv("NTFY_THEMA", raising=False)
    post = Post()
    assert hb.sende("x", "y", [], post=post) is False and not post.calls


def test_schreibt_nur_eigene_dateien(tmp_path):
    hb.schreiben({"offen": []}, [{"event": "x"}], [], [{"titel": "t", "text": "x"}], tmp_path / "gold-hand",
                 tmp_path / "gold-hand.json")
    assert (tmp_path / "gold-hand" / "nachrichten.jsonl").exists() and (tmp_path / "gold-hand.json").exists()
    with pytest.raises(RuntimeError):
        hb.schreiben({}, [], [], [], tmp_path / "gold-short", tmp_path / "x.json")
    with pytest.raises(RuntimeError):
        hb.schreiben({}, [], [], [], tmp_path / "x", tmp_path / "gold-state.json")


def test_nie_auf_dem_hauptkonto():
    assert not hb.KONTO.endswith(hb.HAUPT_ENDUNG)


def test_workflow_testet_vor_dem_lauf():
    from pathlib import Path
    wf = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "demo-bots.yml").read_text(encoding="utf-8")
    assert wf.index("tests/test_gold_hand.py") < wf.index("python -m gold.hand_bot")
    assert "NTFY_THEMA: ${{ secrets.NTFY_THEMA }}" in wf


def test_hintergrund_sperrt_gegen_den_trend(welt):
    welt["trades"]["gross_klein_3"] = [_signal()]
    k, post = HandKonto(), Post()
    k.trend = 2.0                                                           # Gold steigt: kein Short
    st, log, _, msg = hb.run(k, {}, NOW, post=post)
    assert not st["offen"] and "gegen den Hintergrund" in msg[0]["text"] and "Gold steigt" in msg[0]["text"]
    # Long bei steigendem Gold geht, und die Nachricht nennt den Hintergrund
    welt["trades"]["gross_klein_3"] = [_long()]
    k2 = HandKonto()
    k2.trend = 2.0
    st2, _, _, msg2 = hb.run(k2, {}, NOW, post=Post())
    assert st2["offen"] and "Hintergrund: Gold steigt" in msg2[0]["text"]
    # Fällt Gold, gibt es keinen Long
    k3 = HandKonto()
    k3.trend = -2.0
    st3, _, _, msg3 = hb.run(k3, {}, NOW, post=Post())
    assert not st3["offen"] and "Gold fällt" in msg3[0]["text"]


def test_hintergrund_werte():
    k = HandKonto()
    k.trend = 1.0
    hg = hb.hintergrund(k, pd.Timestamp(NOW).tz_convert(None))
    assert hg["richtung"] == 1 and hg["tag"] > hg["sma50"] and hg["h4"] > hg["ema50"]
    k.trend = 0.0
    assert hb.hintergrund(k, pd.Timestamp(NOW).tz_convert(None))["richtung"] == 0


def test_news_pause_vor_wichtigem_termin(welt):
    welt["holen"].ff = [{"country": "USD", "impact": "High", "title": "ISM Services PMI",
                         "date": "2026-03-04T11:00:00-05:00"}]                    # 16:00 UTC, 43 Min. nach NOW
    welt["trades"]["gross_klein_3"] = [_signal()]
    st, log, _, msg = hb.run(HandKonto(), {}, NOW, post=Post())
    assert not st["offen"] and "News-Pause" in msg[0]["text"] and "ISM Services PMI" in msg[0]["text"]
    assert st["ff"]["termine"]                                                 # Kalender im Stand gemerkt
    # Der Kalender wird nicht bei jedem Lauf neu geholt
    n = len([u for u in welt["holen"].urls if u == hb.FF_URL])
    hb.alle_termine(st, pd.Timestamp(NOW).tz_convert(None) + pd.Timedelta("15min"))
    assert len([u for u in welt["holen"].urls if u == hb.FF_URL]) == n


def test_warnung_vor_termin_wenn_gold_offen(welt):
    welt["holen"].ff = [{"country": "USD", "impact": "High", "title": "Fed Chair Speaks",
                         "date": "2026-03-04T10:45:00-05:00"}]                    # 15:45 UTC, 28 Min. nach NOW
    k = HandKonto()
    k.fremd = [{"market": {"epic": "GOLD"}, "position": {"dealId": "K1", "direction": "BUY", "size": 0.2}}]
    st, _, _, msg = hb.run(k, {}, NOW, post=Post())
    assert len(msg) == 1 and "Fed Chair Speaks" in msg[0]["text"] and "1 Long" in msg[0]["text"]
    st2, _, _, msg2 = hb.run(k, st, NOW, post=Post())                          # nur einmal
    assert not msg2
    # Ohne offene Goldposition keine Warnung
    _, _, _, msg3 = hb.run(HandKonto(), {}, NOW, post=Post())
    assert not msg3


def test_schock_pause():
    import numpy as np
    from tests.test_gold_short import _b
    o = [100.0] * 40
    h = [100.5] * 40
    lo = [99.5] * 40
    h[-2], lo[-2] = 106.0, 99.0                                                 # Spanne 7 statt 1
    b = _b(o, h, lo, o)
    assert hb.schock(b, len(b)) and not hb.schock(_b(o, [100.5] * 40, [99.5] * 40, o), 40)


def test_schlagzeilen_in_der_nachricht(welt, monkeypatch):
    monkeypatch.setenv("NTFY_THEMA", "gold-hand-test")
    welt["trades"]["gross_klein_3"] = [_signal()]
    post = Post()
    hb.run(HandKonto(), {}, NOW, post=post)
    text = post.calls[0][1]["message"]
    assert "Gold slips as dollar firms" in text and "Alte Meldung" not in text


class Voll(Post):
    """ntfy.sh antwortet 429 (Tagesgrenze der IP-Adresse erreicht)."""

    def __init__(self, code=429):
        super().__init__()
        self.code = code

    def __call__(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        return type("R", (), {"status_code": self.code})()


def test_nicht_zugestellte_nachricht_kommt_im_naechsten_lauf(welt, monkeypatch):
    monkeypatch.setenv("NTFY_THEMA", "gold-hand-test")
    welt["trades"]["gross_box"] = [_signal()]
    st, log, _, _ = hb.run(HandKonto(), {}, NOW, post=Voll())
    assert len(st["nachholen"]) == 1 and "eröffnet" in st["nachholen"][0]["titel"]
    welt["trades"]["gross_box"] = []
    post = Post()
    st2, log2, _, _ = hb.run(HandKonto(), st, NOW + pd.Timedelta(minutes=15), post=post)
    assert "nachholen" not in st2 and len(post.calls) == 1
    assert post.calls[0][1]["message"].startswith("(verspätet, von ")
    assert any(e["event"] == "Nachricht nachgeholt" and e["gesendet"] for e in log2)


def test_zu_alte_nachricht_wird_verworfen(welt, monkeypatch):
    monkeypatch.setenv("NTFY_THEMA", "gold-hand-test")
    alt = {"zeit": (pd.Timestamp(NOW).tz_localize(None) - pd.Timedelta(hours=13)).isoformat(), "titel": "x",
           "text": "y", "tags": []}
    post = Post()
    st, log, _, _ = hb.run(HandKonto(), {"start": "2026-03-01T00:00:00", "nachholen": [alt]}, NOW, post=post)
    assert "nachholen" not in st and not post.calls
    assert any(e["event"] == "Nachricht verworfen" for e in log)


def test_trockenlauf_holt_nichts_nach(welt, monkeypatch):
    monkeypatch.setenv("NTFY_THEMA", "gold-hand-test")
    m = {"zeit": "2026-03-04T15:00:00", "titel": "x", "text": "y", "tags": []}
    post = Post()
    st, _, _, _ = hb.run(HandKonto(), {"nachholen": [m]}, NOW, send_orders=False, post=post)
    assert st["nachholen"] == [m] and not post.calls


def test_start_nachricht_und_token(monkeypatch):
    monkeypatch.setenv("NTFY_THEMA", "gold-hand-test")
    st = {"stand": "2026-03-04T15:00:00"}
    assert not hb.start_nachricht(st, post=Voll()) and st["nachholen"][0]["titel"] == "Gold-Hand-Bot ist live"
    gesehen = {}

    def post(url, json=None, timeout=None, headers=None):
        gesehen.update(json=json, headers=headers)
        return type("R", (), {"status_code": 200})()

    monkeypatch.setenv("NTFY_TOKEN", "tk_test")
    assert hb.sende("t", "T", [], post=post) and gesehen["headers"] == {"Authorization": "Bearer tk_test"}
    assert gesehen["json"]["message"] == "t" and "Account 5" in hb.START_TEXT
