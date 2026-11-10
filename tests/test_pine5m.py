"""Tests für gold/pine5m_bot.py: Kirons Pine A (Long) und B (Short) auf 5-Min.-Gold-Kerzen, Bots auf drei Konten.

Bot Hand (pine-k5, Account 5): Marktorder ohne Stop und Ziel, Nachricht, Trade-Abfänger, Hinweis beim Pine-Ausstieg,
schließt nie selbst, Hedging (Long und Short gleichzeitig), Termin-Pause, Hintergrund, Termin-Warnung.
Bot pine-hand (Vortag USDJPY): ausgelaufen, betreut nur noch offene Trades.
Bot TP 3 €: Take-Profit +3 €, kein Stop, Notausstieg bei zusammen -250 €. Beide: nur 7 bis 20 Uhr UTC, frische Signale,
höchstens 4 Goldpositionen, nie gegen die Gegenrichtung, Marge für die anderen Bots, nie das Hauptkonto, eigene Dateien."""
import json

import numpy as np
import pandas as pd
import pytest

from gold import pine5m_bot as pb
from gold.backtest import pine_port as pp

HAUPT = "111111113150"
HAND, TP3, ALT = pb.BOTS
NOW = pd.Timestamp("2026-03-04 15:17", tz="UTC").to_pydatetime()


def _kerzen(now=NOW, n=300, kurs=4000.0):
    ende = pd.Timestamp(now).tz_convert(None).floor("5min") - pd.Timedelta("5min")
    idx = pd.date_range(end=ende, periods=n, freq="5min")
    x = np.full(n, kurs)
    return pd.DataFrame({"open": x, "high": x + 1, "low": x - 1, "close": x}, index=idx), pd.Series(0.3, index=idx)


class Konto:
    """Capital.com zum Testen: Hauptkonto und die beiden Bot-Konten, Gold-Positionen je Konto, ohne Netz."""

    def __init__(self, bid=4000.0, offer=4000.3, frei=1000.0):
        self.account_id = HAUPT
        self.bid, self.offer = bid, offer
        self.frei = {HAND.konto: frei, TP3.konto: frei, ALT.konto: frei}
        self.pos: dict[str, dict[str, dict]] = {HAND.konto: {}, TP3.konto: {}, ALT.konto: {}}
        self.fremd: dict[str, list] = {HAND.konto: [], TP3.konto: [], ALT.konto: []}
        self.hedging = {HAND.konto: True, TP3.konto: False, ALT.konto: False}
        self.hedging_sperre = False
        self.acts: dict[str, list] = {}
        self.calls: list = []
        self.refs: dict = {}
        self.nr = 0

    def accounts(self):
        return [{"accountId": HAUPT, "balance": {"balance": 990.0, "available": 900.0}}] + [
            {"accountId": k, "balance": {"balance": 1000.0, "available": v}} for k, v in self.frei.items()]

    def switch_account(self, aid):
        assert aid != HAUPT or True
        self.calls.append(("konto", aid))
        self.account_id = aid

    def market(self, epic):
        if epic == "GOLD":
            return {"snapshot": {"bid": self.bid, "offer": self.offer, "marketStatus": "TRADEABLE",
                                 "decimalPlacesFactor": 2},
                    "instrument": {"currency": "USD", "lotSize": 1, "marginFactor": 5, "marginFactorUnit": "PERCENTAGE"},
                    "dealingRules": {"minDealSize": {"value": 0.01}, "minSizeIncrement": {"value": 0.01},
                                     "minStopOrProfitDistance": {"unit": "POINTS", "value": 0.1}}}
        return {"snapshot": {"bid": 1.08, "offer": 1.08}}

    def positions(self):
        assert self.account_id in self.pos, "Positionen nur auf den Bot-Konten lesen"
        return ([{"market": {"epic": "GOLD"}, "position": p} for p in self.pos[self.account_id].values()]
                + self.fremd[self.account_id])

    def _request(self, method, path, json=None):
        assert self.account_id in (HAND.konto, TP3.konto, ALT.konto), "nie auf dem Hauptkonto handeln"
        self.calls.append((method, path, json, self.account_id))
        self.nr += 1
        ref = f"R{self.nr}"
        if path == "/accounts/preferences":
            assert method == "PUT" and json == {"hedgingMode": True}
            if self.hedging_sperre:
                raise RuntimeError("PUT /accounts/preferences -> 400: error.hedging")
            self.hedging[self.account_id] = True
            return type("A", (), {"json": lambda s: {"status": "SUCCESS"}})()
        if method == "POST" and path == "/positions":
            deal = f"D{self.nr}"
            lvl = self.offer if json["direction"] == "BUY" else self.bid
            p = {"dealId": deal, "level": lvl, "size": json["size"], "direction": json["direction"]}
            for k in ("stopLevel", "profitLevel"):
                if k in json:
                    p[k] = json[k]
            self.pos[self.account_id][deal] = p
            self.refs[ref] = {"dealStatus": "ACCEPTED", "affectedDeals": [{"dealId": deal}], "level": lvl}
        elif method == "PUT":
            self.pos[self.account_id][path.rsplit("/", 1)[1]].update(json)
            self.refs[ref] = {"dealStatus": "ACCEPTED"}
        return type("A", (), {"json": lambda s: {"dealReference": ref}})()

    def confirm(self, ref):
        return self.refs.get(ref, {"dealStatus": "ACCEPTED"})

    def close_position(self, deal_id):
        assert self.account_id == TP3.konto
        self.calls.append(("DELETE", deal_id, self.account_id))
        p = self.pos[self.account_id].pop(deal_id)
        lvl = self.bid if p["direction"] == "BUY" else self.offer
        self.acts[deal_id] = [{"dateUTC": "2026-03-04T15:17:00", "source": "USER", "type": "POSITION",
                               "status": "ACCEPTED", "details": {"level": lvl,
                                                                 "actions": [{"actionType": "POSITION_CLOSED"}]}}]
        return {"dealStatus": "ACCEPTED"}

    def activity(self, deal_id, since, until):
        return self.acts.get(deal_id, [])

    def _get(self, path, **params):
        if path == "/accounts/preferences":
            return {"hedgingMode": self.hedging[self.account_id], "leverages": {}}
        assert path == "/session"
        return {"accountId": self.aktiv_falsch or self.account_id}

    aktiv_falsch = None


class Post:
    def __init__(self):
        self.calls = []

    def __call__(self, url, json=None, timeout=None, **kw):
        self.calls.append((url, json))
        return type("R", (), {"status_code": 200})()


@pytest.fixture
def welt(monkeypatch):
    bars, spread = _kerzen()
    modell = {"bars": bars, "spread": spread, "sig": None}

    def sig_leer(b):
        return pd.DataFrame({"long": False, "short": False, "aus_long": False, "aus_short": False, "atr": 3.0},
                            index=b.index)

    modell["sig"] = sig_leer(bars)
    monkeypatch.setattr(pb, "kerzen", lambda client, now: (modell["bars"], modell["spread"]))
    monkeypatch.setattr(pb, "signale", lambda b: modell["sig"])
    monkeypatch.setattr(pb, "vorab_ok", lambda: True)
    monkeypatch.setenv("NTFY_THEMA", "pine-test")
    modell["news"] = {"pause": False, "gruende": [], "naechster": None, "termine": []}
    modell["hg"] = {"richtung": 0}
    modell["termine"] = []
    monkeypatch.setattr(pb.hb, "news_lage", lambda st, now: modell["news"])
    monkeypatch.setattr(pb.hb, "hintergrund", lambda client, now: modell["hg"])
    monkeypatch.setattr(pb.hb, "alle_termine", lambda st, now: modell["termine"])
    return modell


def _setze(welt, spalte, wert=True, t=-1):
    welt["sig"].iloc[t, welt["sig"].columns.get_loc(spalte)] = wert


def _orders(k, konto=None):
    return [c for c in k.calls if c[0] == "POST" and (konto is None or c[3] == konto)]


# --------------------------------------------------------------------------------------------------------------------

def test_konten_und_nie_hauptkonto():
    assert {b.art for b in pb.BOTS} == {"hand", "tp3"}
    assert HAND.konto.endswith("9086") and HAND.konto == pb.hb.KONTO and HAND.bot_id == "pine-k5"
    assert HAND.hedging and HAND.gold_pruefer and HAND.neu
    assert TP3.konto.endswith("8878") and not TP3.hedging and not TP3.gold_pruefer and TP3.neu
    assert ALT.bot_id == "pine-hand" and ALT.konto.endswith("4094") and not ALT.neu
    assert not any(b.konto.endswith(pb.HAUPT_ENDUNG) for b in pb.BOTS)
    assert len({b.konto for b in pb.BOTS}) == 3


def test_long_signal_beide_bots_eroeffnen(welt):
    _setze(welt, "long")
    k, post = Konto(), Post()
    out = pb.run(k, {}, NOW, post=post)
    hand, tp3 = _orders(k, HAND.konto), _orders(k, TP3.konto)
    assert len(hand) == 1 and len(tp3) == 1
    assert hand[0][2]["direction"] == "BUY" and "stopLevel" not in hand[0][2] and "profitLevel" not in hand[0][2]
    # 1 R = 3 x ATR 3 = 9 $; 5 € je R bei 1,08 $/€: 5 * 1,08 / 9 = 0,6 oz
    assert hand[0][2]["size"] == 0.6 and tp3[0][2]["size"] == 0.6
    # TP 3 € = 3 * 1,08 / 0,6 = 5,40 $ über dem Einstieg (Ask 4000,30)
    assert tp3[0][2]["profitLevel"] == pytest.approx(4005.70) and "stopLevel" not in tp3[0][2]
    st_h, _, _, msg_h = out[HAND.bot_id]
    st_t, _, _, msg_t = out["pine-tp3"]
    assert st_h["offen"][0]["dist"] == 9.0 and st_t["offen"][0]["tp"] == pytest.approx(4005.70)
    assert len(msg_h) == 1 and msg_h[0]["titel"] == "Pine-Gold LONG eröffnet" and not msg_t
    assert len(post.calls) == 1                                   # nur Bot Hand meldet
    assert k.account_id == HAUPT                                  # zurück aufs Hauptkonto


def test_short_signal_mit_tp_unter_dem_einstieg(welt):
    _setze(welt, "short")
    k = Konto()
    pb.run(k, {}, NOW, post=Post())
    tp3 = _orders(k, TP3.konto)
    assert tp3[0][2]["direction"] == "SELL" and tp3[0][2]["profitLevel"] == pytest.approx(3994.60)


def test_ausserhalb_der_handelszeit_kein_trade(welt):
    nacht = pd.Timestamp("2026-03-04 21:17", tz="UTC").to_pydatetime()
    welt["bars"], welt["spread"] = _kerzen(nacht)
    welt["sig"] = welt["sig"].set_axis(welt["bars"].index)
    _setze(welt, "long")
    k = Konto()
    pb.run(k, {}, nacht, post=Post())
    assert not _orders(k)


def test_altes_signal_verfaellt_still(welt):
    spaet = pd.Timestamp("2026-03-04 15:29", tz="UTC").to_pydatetime()   # Kerze endete 15:15, 14 Min. her
    _setze(welt, "long")
    k, post = Konto(), Post()
    out = pb.run(k, {}, spaet, post=post)
    assert not _orders(k) and not post.calls
    assert any("Signal zu alt" in e.get("gruende", []) for e in out[HAND.bot_id][1])


def test_tp_bot_nie_gegen_die_gegenrichtung_und_hoechstens_vier(welt):
    _setze(welt, "long")
    k = Konto()
    k.pos[TP3.konto]["X"] = {"dealId": "X", "level": 3990.0, "size": 0.5, "direction": "SELL"}
    for i in range(4):
        k.pos[HAND.konto][f"L{i}"] = {"dealId": f"L{i}", "level": 3990.0, "size": 0.1, "direction": "SELL"}
    post = Post()
    out = pb.run(k, {}, NOW, post=post)
    assert not _orders(k) and not post.calls                         # beides still, nur im Log
    assert any("andere Richtung" in g for e in out["pine-tp3"][1] for g in e.get("gruende", []))
    assert any("4 Goldpositionen" in g for e in out[HAND.bot_id][1] for g in e.get("gruende", []))


# ---- Account 5: Hedging, Termin-Pause, Hintergrund (Kirons Wort vom 10.11.2026 07:29 UTC) ----

def test_k5_mit_hedging_long_neben_short(welt):
    _setze(welt, "long")
    k, post = Konto(), Post()
    k.pos[HAND.konto]["X"] = {"dealId": "X", "level": 3990.0, "size": 0.5, "direction": "SELL"}
    out = pb.run(k, {}, NOW, post=post)
    hand = _orders(k, HAND.konto)
    assert len(hand) == 1 and hand[0][2]["direction"] == "BUY" and "X" in k.pos[HAND.konto]
    assert not [c for c in k.calls if c[1] == "/accounts/preferences"]      # war schon an: nichts umgestellt
    assert out[HAND.bot_id][0]["hedging"] is True
    assert "Gegenposition offen, mit Hedging erlaubt" in post.calls[0][1]["message"]


def test_k5_schaltet_hedging_ein_und_meldet_es_einmal(welt):
    _setze(welt, "short")
    k, post = Konto(), Post()
    k.hedging[HAND.konto] = False
    k.pos[HAND.konto]["X"] = {"dealId": "X", "level": 3990.0, "size": 0.5, "direction": "BUY"}
    out = pb.run(k, {}, NOW, post=post)
    assert ("PUT", "/accounts/preferences", {"hedgingMode": True}, HAND.konto) in k.calls
    assert not [c for c in k.calls if c[1] == "/accounts/preferences" and c[3] != HAND.konto]
    assert [c[1]["title"] for c in post.calls] == ["Pine-Gold: Hedging an", "Pine-Gold SHORT eröffnet"]
    assert len(_orders(k, HAND.konto)) == 1
    pb.run(k, {b: out[b][0] for b in out}, NOW, post=Post())
    assert len([c for c in k.calls if c[1] == "/accounts/preferences"]) == 1


def test_k5_ohne_hedging_nie_gegen_und_versucht_es_stuendlich(welt):
    _setze(welt, "short")
    k, post = Konto(), Post()
    k.hedging[HAND.konto], k.hedging_sperre = False, True
    k.pos[HAND.konto]["X"] = {"dealId": "X", "level": 3990.0, "size": 0.5, "direction": "BUY"}
    out = pb.run(k, {}, NOW, post=post)
    assert not _orders(k, HAND.konto)
    assert [c[1]["title"] for c in post.calls] == ["Pine-Gold: Hedging nicht eingeschaltet"]
    st = out[HAND.bot_id][0]
    st["letzte_kerze"] = str(welt["bars"].index[-2])
    post2 = Post()
    spaeter = pd.Timestamp(NOW) + pd.Timedelta(minutes=5)
    pb.run(k, {HAND.bot_id: st}, spaeter.to_pydatetime(), post=post2)
    assert len([c for c in k.calls if c[1] == "/accounts/preferences"]) == 1 and not post2.calls


def test_k5_trockenlauf_schaltet_hedging_nicht_ein(welt):
    k = Konto()
    k.hedging[HAND.konto] = False
    out = pb.run(k, {}, NOW, send_orders=False, post=Post())
    assert not [c for c in k.calls if c[1] == "/accounts/preferences"] and not k.hedging[HAND.konto]
    assert any(e["event"] == "würde Hedging einschalten" for e in out[HAND.bot_id][1])


def test_k5_news_pause_mit_nachricht_tp_bot_ohne(welt):
    _setze(welt, "long")
    welt["news"] = {"pause": True, "gruende": ["US-Inflation (CPI) um 14:30 Uhr"], "naechster": None, "termine": []}
    k, post = Konto(), Post()
    pb.run(k, {}, NOW, post=post)
    assert not _orders(k, HAND.konto) and len(_orders(k, TP3.konto)) == 1
    assert post.calls[0][1]["title"] == "Pine-Gold LONG, nicht eröffnet"
    assert "News-Pause: US-Inflation (CPI)" in post.calls[0][1]["message"]


def test_k5_hintergrund_sperrt_still(welt):
    _setze(welt, "short")
    welt["hg"] = {"richtung": 1, "tag": 4100.0, "sma50": 4000.0}
    k, post = Konto(), Post()
    out = pb.run(k, {}, NOW, post=post)
    assert not _orders(k, HAND.konto) and len(_orders(k, TP3.konto)) == 1 and not post.calls
    assert any("gegen den Hintergrund" in g for e in out[HAND.bot_id][1] for g in e.get("gruende", []))
    _setze(welt, "short", False)
    _setze(welt, "long")
    k2, post2 = Konto(), Post()
    pb.run(k2, {}, NOW, post=post2)                               # Long mit dem Hintergrund: offen
    assert len(_orders(k2, HAND.konto)) == 1 and "Gold steigt" in post2.calls[0][1]["message"]


def test_k5_warnt_einmal_vor_termin(welt):
    welt["termine"] = [(pd.Timestamp("2026-03-04 15:47"), "Fed-Zinsentscheid")]
    k, post = Konto(), Post()
    k.pos[HAND.konto]["X"] = {"dealId": "X", "level": 3990.0, "size": 0.5, "direction": "SELL"}
    out = pb.run(k, {}, NOW, post=post)
    assert [c[1]["title"] for c in post.calls] == ["Pine-Gold: wichtiger Termin bald"]
    assert "1 Short und 0 Long" in post.calls[0][1]["message"]
    post2 = Post()
    pb.run(k, {b: out[b][0] for b in out}, NOW, post=post2)
    assert not post2.calls


def test_alter_bot_oeffnet_nichts_und_fragt_ohne_offene_trades_nichts_ab(welt, tmp_path):
    _setze(welt, "long")
    k = Konto()
    alt = {"format": 1, "start": "2026-03-04T03:48:53", "offen": [], "trades": 0, "summe_r": 0.0, "summe_eur": 0.0,
           "letzte_kerze": "2026-03-04 07:00:00", "stand": "2026-03-04T07:08:31"}
    out = pb.run(k, {ALT.bot_id: alt}, NOW, post=Post())
    assert not _orders(k, ALT.konto) and ("konto", ALT.konto) not in k.calls
    st, log, fertig, msg = out[ALT.bot_id]
    assert st == alt and not log and not fertig and not msg
    assert pb.schreiben(ALT, alt, st, log, fertig, msg, root=tmp_path) is False      # keine Datei, kein Commit


def test_alter_bot_betreut_seine_offenen_trades(welt):
    _setze(welt, "long")
    k, post = Konto(bid=3995.0, offer=3995.3), Post()
    k.pos[ALT.konto]["A"] = {"dealId": "A", "level": 4000.0, "size": 0.6, "direction": "BUY"}
    st = {"offen": [{"dealId": "A", "richtung": 1, "size": 0.6, "entry": 4000.0, "dist": 9.0,
                     "opened_utc": "2026-03-04T15:00:00"}], "letzte_kerze": str(welt["bars"].index[-2])}
    pb.run(k, {ALT.bot_id: st}, NOW, post=post)
    assert not _orders(k, ALT.konto)
    assert k.pos[ALT.konto]["A"]["stopLevel"] == 3991.0 and k.pos[ALT.konto]["A"]["profitLevel"] == 4000.0
    assert not [c for c in k.calls if c[1] == "/accounts/preferences"]


def test_vorab_konto5_ist_versiegelt():
    from suche.runde1 import journal_lines, last_value, sha256_text
    assert last_value(journal_lines(), pb.KEY_K5) == sha256_text(pb.VORAB_K5.read_text(encoding="utf-8"))


def test_widerspruch_ohne_position_verfaellt_mit_long_stockt_auf(welt):
    _setze(welt, "long")
    _setze(welt, "short")
    k = Konto()
    k.pos[TP3.konto]["L"] = {"dealId": "L", "level": 3990.0, "size": 0.1, "direction": "BUY"}
    pb.run(k, {}, NOW, post=Post())
    assert not _orders(k, HAND.konto)
    tp3 = _orders(k, TP3.konto)
    assert len(tp3) == 1 and tp3[0][2]["direction"] == "BUY"


def test_marge_fuer_die_anderen_bots(welt):
    _setze(welt, "long")
    k, post = Konto(frei=300.0), Post()
    out = pb.run(k, {}, NOW, post=post)
    assert not _orders(k)
    assert any("frei für die anderen Bots" in g for e in out[HAND.bot_id][1] for g in e.get("gruende", []))
    assert len(post.calls) == 1 and "nicht eröffnet" in post.calls[0][1]["title"]


def test_hoechstens_250_euro_marge_je_bot(welt):
    _setze(welt, "long")
    k = Konto()
    # 3 eigene Positionen zu 0,5 oz bei 4000 $: 3 * 0,5 * 4000 * 5 % / 1,08 = 278 € Marge
    st = {"offen": [{"dealId": f"M{i}", "richtung": 1, "size": 0.5, "entry": 4000.0, "dist": 9.0,
                     "opened_utc": "2026-03-04T15:00:00"} for i in range(3)]}
    for i in range(3):
        k.pos[TP3.konto][f"M{i}"] = {"dealId": f"M{i}", "level": 4000.0, "size": 0.5, "direction": "BUY"}
    out = pb.run(k, {"pine-tp3": st}, NOW, post=Post())
    assert not _orders(k, TP3.konto) and len(_orders(k, HAND.konto)) == 1
    assert any("250 € Marge" in g for e in out["pine-tp3"][1] for g in e.get("gruende", []))


def test_vorab_nicht_versiegelt_kein_trade(welt, monkeypatch):
    monkeypatch.setattr(pb, "vorab_ok", lambda: False)
    _setze(welt, "long")
    k = Konto()
    pb.run(k, {}, NOW, post=Post())
    assert not _orders(k)


def test_echte_vorab_ist_versiegelt():
    assert pb.vorab_ok()


def test_dieselbe_kerze_nur_einmal(welt):
    _setze(welt, "long")
    k = Konto()
    out = pb.run(k, {}, NOW, post=Post())
    states = {b: out[b][0] for b in out}
    k2 = Konto()
    pb.run(k2, states, NOW, post=Post())
    assert not _orders(k2)


def test_abfaenger_fehltrade_setzt_stop_und_ziel(welt):
    k = Konto(bid=3995.0, offer=3995.3)                          # Long von 4000, 1 R = 9: 0,5 R dagegen = 3995,5
    k.pos[HAND.konto]["H"] = {"dealId": "H", "level": 4000.0, "size": 0.6, "direction": "BUY"}
    st = {"offen": [{"dealId": "H", "richtung": 1, "size": 0.6, "entry": 4000.0, "dist": 9.0,
                     "opened_utc": "2026-03-04T15:00:00"}], "letzte_kerze": str(welt["bars"].index[-1])}
    post = Post()
    out = pb.run(k, {HAND.bot_id: st}, NOW, post=post)
    p = k.pos[HAND.konto]["H"]
    assert p["stopLevel"] == 3991.0 and p["profitLevel"] == 4000.0
    assert out[HAND.bot_id][0]["offen"][0]["abfang"]["warum"].startswith("Fehltrade")
    assert "Abfänger greift" in post.calls[0][1]["title"]


def test_abfaenger_notbremse_nach_ziel_1(welt):
    bars = welt["bars"].copy()
    bars.iloc[-3, bars.columns.get_loc("high")] = 4008.0          # Ziel 1 (4006,75) erreicht
    welt["bars"] = bars
    k = Konto(bid=3990.5, offer=3990.8)                          # jetzt gut 1 R im Minus
    k.pos[HAND.konto]["H"] = {"dealId": "H", "level": 4000.0, "size": 0.6, "direction": "BUY"}
    st = {"offen": [{"dealId": "H", "richtung": 1, "size": 0.6, "entry": 4000.0, "dist": 9.0,
                     "opened_utc": "2026-03-04T14:58:00"}], "letzte_kerze": str(bars.index[-1])}
    pb.run(k, {HAND.bot_id: st}, NOW, post=Post())
    p = k.pos[HAND.konto]["H"]
    assert p["stopLevel"] == pytest.approx(3986.0) and "profitLevel" not in p


def test_abfaenger_aus_wenn_kiron_selbst_stop_setzt(welt):
    k = Konto(bid=3990.0, offer=3990.3)
    k.pos[HAND.konto]["H"] = {"dealId": "H", "level": 4000.0, "size": 0.6, "direction": "BUY", "stopLevel": 3980.0}
    st = {"offen": [{"dealId": "H", "richtung": 1, "size": 0.6, "entry": 4000.0, "dist": 9.0,
                     "opened_utc": "2026-03-04T15:00:00"}], "letzte_kerze": str(welt["bars"].index[-1])}
    out = pb.run(k, {HAND.bot_id: st}, NOW, post=Post())
    assert out[HAND.bot_id][0]["offen"][0]["agent"] == "aus"
    assert k.pos[HAND.konto]["H"]["stopLevel"] == 3980.0 and not [c for c in k.calls if c[0] == "PUT"]


def test_tp_bot_hat_keinen_abfaenger(welt):
    k = Konto(bid=3985.0, offer=3985.3)
    k.pos[TP3.konto]["T"] = {"dealId": "T", "level": 4000.0, "size": 0.6, "direction": "BUY", "profitLevel": 4005.4}
    st = {"offen": [{"dealId": "T", "richtung": 1, "size": 0.6, "entry": 4000.0, "dist": 9.0, "tp": 4005.4,
                     "opened_utc": "2026-03-04T15:00:00"}], "letzte_kerze": str(welt["bars"].index[-1])}
    pb.run(k, {"pine-tp3": st}, NOW, post=Post())
    assert not [c for c in k.calls if c[0] in ("PUT", "DELETE")]


def test_hinweis_beim_pine_ausstieg_einmal(welt):
    _setze(welt, "aus_long")
    k = Konto(bid=4003.0, offer=4003.3)
    k.pos[HAND.konto]["H"] = {"dealId": "H", "level": 4000.0, "size": 0.6, "direction": "BUY"}
    st = {"offen": [{"dealId": "H", "richtung": 1, "size": 0.6, "entry": 4000.0, "dist": 9.0,
                     "opened_utc": "2026-03-04T15:00:00"}], "letzte_kerze": str(welt["bars"].index[-2])}
    post = Post()
    out = pb.run(k, {HAND.bot_id: st}, NOW, post=post)
    assert [c[1]["title"] for c in post.calls] == ["Pine-Gold: Strategie würde LONG schließen"]
    assert "H" in k.pos[HAND.konto] and not [c for c in k.calls if c[0] == "DELETE"]   # schließt nie selbst
    st2 = out[HAND.bot_id][0]
    st2["letzte_kerze"] = str(welt["bars"].index[-2])
    post2 = Post()
    pb.run(k, {HAND.bot_id: st2}, NOW, post=post2)
    assert not post2.calls


def test_notausstieg_tp_bot_ab_250_euro(welt):
    # 2 Longs zu 1 oz von 4000, Bid 3860: je -140 $ = -129,6 €, zusammen -259 €
    k = Konto(bid=3860.0, offer=3860.3)
    st = {"offen": []}
    for i in range(2):
        k.pos[TP3.konto][f"T{i}"] = {"dealId": f"T{i}", "level": 4000.0, "size": 1.0, "direction": "BUY"}
        st["offen"].append({"dealId": f"T{i}", "richtung": 1, "size": 1.0, "entry": 4000.0, "dist": 9.0,
                            "opened_utc": "2026-03-04T10:00:00"})
    st["letzte_kerze"] = str(welt["bars"].index[-1])
    post = Post()
    out = pb.run(k, {"pine-tp3": st}, NOW, post=post)
    assert not k.pos[TP3.konto]
    st3, log, fertig, _ = out["pine-tp3"]
    assert not st3["offen"] and len(fertig) == 2 and fertig[0]["r"] == pytest.approx(-140 / 9, abs=1e-3)
    assert post.calls[0][1]["title"] == "Pine-Gold TP 3 €: Notausstieg"


def test_kein_notausstieg_unter_der_grenze(welt):
    k = Konto(bid=3900.0, offer=3900.3)                            # 2 x -100 $ = -185 €
    st = {"offen": []}
    for i in range(2):
        k.pos[TP3.konto][f"T{i}"] = {"dealId": f"T{i}", "level": 4000.0, "size": 1.0, "direction": "BUY"}
        st["offen"].append({"dealId": f"T{i}", "richtung": 1, "size": 1.0, "entry": 4000.0, "dist": 9.0,
                            "opened_utc": "2026-03-04T10:00:00"})
    st["letzte_kerze"] = str(welt["bars"].index[-1])
    pb.run(k, {"pine-tp3": st}, NOW, post=Post())
    assert len(k.pos[TP3.konto]) == 2


def test_kirons_eigener_schluss_wird_gebucht(welt):
    k = Konto()
    k.acts["H"] = [{"dateUTC": "2026-03-04T15:10:00", "source": "USER", "type": "POSITION", "status": "ACCEPTED",
                    "details": {"level": 4012.0, "actions": [{"actionType": "POSITION_CLOSED"}]}}]
    st = {"offen": [{"dealId": "H", "richtung": 1, "size": 0.6, "entry": 4000.0, "dist": 9.0,
                     "opened_utc": "2026-03-04T15:00:00"}], "letzte_kerze": str(welt["bars"].index[-1])}
    out = pb.run(k, {HAND.bot_id: st}, NOW, post=Post())
    st2, _, fertig, _ = out[HAND.bot_id]
    assert not st2["offen"] and fertig[0]["r"] == pytest.approx(12 / 9, abs=1e-3)
    assert fertig[0]["pnl_eur"] == pytest.approx(12 * 0.6 / 1.08, abs=0.01) and st2["trades"] == 1


def test_trockenlauf_ohne_order_und_nachricht(welt):
    _setze(welt, "long")
    k, post = Konto(), Post()
    out = pb.run(k, {}, NOW, send_orders=False, post=post)
    assert not _orders(k) and not post.calls
    assert any(e["event"] == "würde öffnen" for e in out["pine-tp3"][1])


def test_signale_sind_kirons_pine_a_und_b():
    rng = np.random.default_rng(7)
    c = 4000 + np.cumsum(rng.normal(0, 2, 600))
    idx = pd.date_range("2026-03-02 07:00", periods=600, freq="5min")
    bars = pd.DataFrame({"open": np.r_[c[0], c[:-1]], "high": c + 1.5, "low": c - 1.5, "close": c}, index=idx)
    s = pb.signale(bars)
    a, b = pp.signals_a_long(bars), pp.signals_b_short(bars)
    assert (s["long"] == a["entry"].fillna(False)).all() and (s["short"] == b["entry"].fillna(False)).all()
    assert (s["aus_long"] == a["exit"].fillna(False)).all() and (s["aus_short"] == b["exit"].fillna(False)).all()
    assert s["atr"].iloc[-1] > 0


def test_r_mindestens_vier_spreads():
    assert pb.r_dist(0.05, 0.3) == pytest.approx(1.2) and pb.r_dist(3.0, 0.3) == pytest.approx(9.0)


def test_nur_eigene_dateien_und_weniger_commits(tmp_path):
    st = {"stand": "2026-03-04T15:17:00", "offen": [], "trades": 0}
    assert pb.schreiben(HAND, {}, st, [], [], [], root=tmp_path)
    assert (tmp_path / "journal" / "pine-k5" / "state.json").exists()
    cp = json.loads((tmp_path / "journal" / "pine-k5.json").read_text())
    assert cp["konto"] == "…9086" and cp["vorab"] == "suche/VORAB_pine5m_konto5.yaml" and "Hedging" in cp["regel"]
    assert pb.schreiben(ALT, {}, st, [], [], [], root=tmp_path)
    alt = json.loads((tmp_path / "journal" / "pine-hand.json").read_text())
    assert alt["konto"] == "…4094" and alt["regel"].startswith("Seit 10.11.2026 auf Account 5 umgezogen")
    st2 = dict(st, stand="2026-03-04T15:22:00", letzte_kerze="2026-03-04 15:15:00")
    assert not pb.schreiben(HAND, st, st2, [], [], [], root=tmp_path)          # nichts Neues, 5 Min. später
    st3 = dict(st, stand="2026-03-04T15:52:00")
    assert pb.schreiben(HAND, st, st3, [], [], [], root=tmp_path)              # Lebenszeichen nach 30 Min.
    falsch = pb.Bot("gold-hand", "1", "x", "hand", "x")
    with pytest.raises(RuntimeError):
        pb.schreiben(falsch, {}, st, [], [], [], root=tmp_path)


def test_ein_fehler_haelt_den_anderen_bot_nicht_auf(welt):
    _setze(welt, "long")

    class Kaputt(Konto):
        def market(self, epic):
            if self.account_id == HAND.konto:
                raise RuntimeError("Netz weg")
            return super().market(epic)

    k = Kaputt()
    out = pb.run(k, {}, NOW, post=Post())
    assert any(e["event"] == "Fehler" for e in out[HAND.bot_id][1])
    assert len(_orders(k, TP3.konto)) == 1


def test_anderes_konto_aktiv_nichts_tun(welt):
    _setze(welt, "long")
    k = Konto()
    k.aktiv_falsch = HAUPT
    out = pb.run(k, {}, NOW, post=Post())
    assert not _orders(k) and all(e["event"].startswith("anderes Konto") for b in out for e in out[b][1])


# ---- Prüfer des TP-Bots (suche/VORAB_pine5m_pruefer.yaml, Kirons Wort vom 10.11.2026 02:48 UTC) ----

def _tp_pos(k, welt, seit, entry=4000.0, tp=4005.4, d="BUY"):
    k.pos[TP3.konto]["T"] = {"dealId": "T", "level": entry, "size": 0.6, "direction": d, "profitLevel": tp}
    return {"offen": [{"dealId": "T", "richtung": 1 if d == "BUY" else -1, "size": 0.6, "entry": entry, "dist": 9.0,
                       "tp": tp, "opened_utc": seit}], "letzte_kerze": str(welt["bars"].index[-1])}


def test_pruefer_wartet_drei_stunden(welt):
    k = Konto(bid=3994.0, offer=3994.3)                          # 0,67 R im Minus, aber erst 2 Std. offen
    st = _tp_pos(k, welt, "2026-03-04T13:17:00")
    pb.run(k, {"pine-tp3": st}, NOW, post=Post())
    assert not [c for c in k.calls if c[0] in ("PUT", "DELETE")]


def test_pruefer_fehltrade_stop_und_einstand(welt):
    k = Konto(bid=3994.0, offer=3994.3)                          # 3 Std. 17 Min. offen, 0,67 R im Minus
    st = _tp_pos(k, welt, "2026-03-04T12:00:00")
    out = pb.run(k, {"pine-tp3": st}, NOW, post=Post())
    p = k.pos[TP3.konto]["T"]
    assert p["stopLevel"] == 3991.0 and p["profitLevel"] == 4000.0
    tr = out["pine-tp3"][0]["offen"][0]
    assert tr["pruefer"]["warum"].startswith("Fehltrade") and tr["tp"] == 4000.0
    k2 = Konto(bid=3994.0, offer=3994.3)                         # nur einmal je Position
    k2.pos = k.pos
    pb.run(k2, {"pine-tp3": out["pine-tp3"][0]}, NOW, post=Post())
    assert not [c for c in k2.calls if c[0] == "PUT"]


def test_pruefer_hinter_dem_stop_halbes_r_hinter_den_kurs(welt):
    k = Konto(bid=3988.0, offer=3988.3)                          # 1,33 R im Minus
    st = _tp_pos(k, welt, "2026-03-04T12:00:00")
    pb.run(k, {"pine-tp3": st}, NOW, post=Post())
    p = k.pos[TP3.konto]["T"]
    assert p["stopLevel"] == pytest.approx(3983.5) and p["profitLevel"] == 4000.0


def test_pruefer_short_fehltrade(welt):
    k = Konto(bid=4005.5, offer=4005.8)                          # Short von 4000: 0,64 R im Minus
    st = _tp_pos(k, welt, "2026-03-04T12:00:00", tp=3994.6, d="SELL")
    pb.run(k, {"pine-tp3": st}, NOW, post=Post())
    p = k.pos[TP3.konto]["T"]
    assert p["stopLevel"] == 4009.0 and p["profitLevel"] == 4000.0


def test_pruefer_fehltrade_wieder_im_plus_ziel_bleibt(welt):
    bars = welt["bars"].copy()
    bars.iloc[-20, bars.columns.get_loc("low")] = 3994.0          # lag nach dem Einstieg 0,67 R im Minus
    welt["bars"] = bars
    k = Konto(bid=4002.0, offer=4002.3)                          # jetzt wieder im Plus
    st = _tp_pos(k, welt, "2026-03-04T12:00:00")
    pb.run(k, {"pine-tp3": st}, NOW, post=Post())
    p = k.pos[TP3.konto]["T"]
    assert p["stopLevel"] == 3991.0 and p["profitLevel"] == 4005.4


def test_pruefer_langes_warten_im_plus_raus(welt):
    k = Konto(bid=4001.0, offer=4001.3)                          # 25 Std. offen, nie 0,5 R im Minus, jetzt im Plus
    st = _tp_pos(k, welt, "2026-03-03T14:00:00")
    pb.run(k, {"pine-tp3": st}, NOW, post=Post())
    assert ("DELETE", "T", TP3.konto) in k.calls and "T" not in k.pos[TP3.konto]


def test_pruefer_langes_warten_im_minus_einstand(welt):
    k = Konto(bid=3998.0, offer=3998.3)                          # 25 Std. offen, 0,22 R im Minus
    st = _tp_pos(k, welt, "2026-03-03T14:00:00")
    pb.run(k, {"pine-tp3": st}, NOW, post=Post())
    p = k.pos[TP3.konto]["T"]
    assert p["stopLevel"] == 3991.0 and p["profitLevel"] == 4000.0


def test_pruefer_aus_wenn_ziel_von_hand_geaendert(welt):
    k = Konto(bid=3994.0, offer=3994.3)
    st = _tp_pos(k, welt, "2026-03-04T12:00:00")
    k.pos[TP3.konto]["T"]["profitLevel"] = 4020.0
    out = pb.run(k, {"pine-tp3": st}, NOW, post=Post())
    assert not [c for c in k.calls if c[0] == "PUT"] and out["pine-tp3"][0]["offen"][0]["agent"] == "aus"


def test_pruefer_vorab_ist_versiegelt():
    from suche.runde1 import journal_lines, last_value, sha256_text
    assert last_value(journal_lines(), pb.KEY_PRUEFER) == sha256_text(pb.VORAB_PRUEFER.read_text(encoding="utf-8"))
