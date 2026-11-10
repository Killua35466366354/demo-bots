"""Tests für gold/pine5m_bot.py: Kirons Pine A (Long) und B (Short) auf 5-Min.-Gold-Kerzen, zwei Bots auf zwei Konten.

Bot Hand: Marktorder ohne Stop und Ziel, Nachricht, Trade-Abfänger, Hinweis beim Pine-Ausstieg, schließt nie selbst.
Bot TP 3 €: Take-Profit +3 €, kein Stop, Notausstieg bei zusammen -250 €. Beide: nur 7 bis 20 Uhr UTC, frische Signale,
höchstens 4 Goldpositionen, nie gegen die Gegenrichtung, Marge für die anderen Bots, nie das Hauptkonto, eigene Dateien."""
import json

import numpy as np
import pandas as pd
import pytest

from gold import pine5m_bot as pb
from gold.backtest import pine_port as pp

HAUPT = "111111113150"
HAND, TP3 = pb.BOTS
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
        self.frei = {HAND.konto: frei, TP3.konto: frei}
        self.pos: dict[str, dict[str, dict]] = {HAND.konto: {}, TP3.konto: {}}
        self.fremd: dict[str, list] = {HAND.konto: [], TP3.konto: []}
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
        assert self.account_id in (HAND.konto, TP3.konto), "nie auf dem Hauptkonto handeln"
        self.calls.append((method, path, json, self.account_id))
        self.nr += 1
        ref = f"R{self.nr}"
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
    return modell


def _setze(welt, spalte, wert=True, t=-1):
    welt["sig"].iloc[t, welt["sig"].columns.get_loc(spalte)] = wert


def _orders(k, konto=None):
    return [c for c in k.calls if c[0] == "POST" and (konto is None or c[3] == konto)]


# --------------------------------------------------------------------------------------------------------------------

def test_konten_und_nie_hauptkonto():
    assert {b.art for b in pb.BOTS} == {"hand", "tp3"}
    assert HAND.konto.endswith("4094") and TP3.konto.endswith("8878")
    assert not any(b.konto.endswith(pb.HAUPT_ENDUNG) for b in pb.BOTS)
    assert HAND.konto != TP3.konto


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
    st_h, _, _, msg_h = out["pine-hand"]
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
    assert any("Signal zu alt" in e.get("gruende", []) for e in out["pine-hand"][1])


def test_nie_gegen_die_gegenrichtung_und_hoechstens_vier(welt):
    _setze(welt, "long")
    k = Konto()
    k.pos[HAND.konto]["X"] = {"dealId": "X", "level": 3990.0, "size": 0.5, "direction": "SELL"}
    for i in range(4):
        k.pos[TP3.konto][f"L{i}"] = {"dealId": f"L{i}", "level": 3990.0, "size": 0.1, "direction": "BUY"}
    post = Post()
    out = pb.run(k, {}, NOW, post=post)
    assert not _orders(k) and not post.calls                         # beides still, nur im Log
    assert any("andere Richtung" in g for e in out["pine-hand"][1] for g in e.get("gruende", []))
    assert any("4 Goldpositionen" in g for e in out["pine-tp3"][1] for g in e.get("gruende", []))


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
    assert any("frei für die anderen Bots" in g for e in out["pine-hand"][1] for g in e.get("gruende", []))
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
    out = pb.run(k, {"pine-hand": st}, NOW, post=post)
    p = k.pos[HAND.konto]["H"]
    assert p["stopLevel"] == 3991.0 and p["profitLevel"] == 4000.0
    assert out["pine-hand"][0]["offen"][0]["abfang"]["warum"].startswith("Fehltrade")
    assert "Abfänger greift" in post.calls[0][1]["title"]


def test_abfaenger_notbremse_nach_ziel_1(welt):
    bars = welt["bars"].copy()
    bars.iloc[-3, bars.columns.get_loc("high")] = 4008.0          # Ziel 1 (4006,75) erreicht
    welt["bars"] = bars
    k = Konto(bid=3990.5, offer=3990.8)                          # jetzt gut 1 R im Minus
    k.pos[HAND.konto]["H"] = {"dealId": "H", "level": 4000.0, "size": 0.6, "direction": "BUY"}
    st = {"offen": [{"dealId": "H", "richtung": 1, "size": 0.6, "entry": 4000.0, "dist": 9.0,
                     "opened_utc": "2026-03-04T14:58:00"}], "letzte_kerze": str(bars.index[-1])}
    pb.run(k, {"pine-hand": st}, NOW, post=Post())
    p = k.pos[HAND.konto]["H"]
    assert p["stopLevel"] == pytest.approx(3986.0) and "profitLevel" not in p


def test_abfaenger_aus_wenn_kiron_selbst_stop_setzt(welt):
    k = Konto(bid=3990.0, offer=3990.3)
    k.pos[HAND.konto]["H"] = {"dealId": "H", "level": 4000.0, "size": 0.6, "direction": "BUY", "stopLevel": 3980.0}
    st = {"offen": [{"dealId": "H", "richtung": 1, "size": 0.6, "entry": 4000.0, "dist": 9.0,
                     "opened_utc": "2026-03-04T15:00:00"}], "letzte_kerze": str(welt["bars"].index[-1])}
    out = pb.run(k, {"pine-hand": st}, NOW, post=Post())
    assert out["pine-hand"][0]["offen"][0]["agent"] == "aus"
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
    out = pb.run(k, {"pine-hand": st}, NOW, post=post)
    assert [c[1]["title"] for c in post.calls] == ["Pine-Gold: Strategie würde LONG schließen"]
    assert "H" in k.pos[HAND.konto] and not [c for c in k.calls if c[0] == "DELETE"]   # schließt nie selbst
    st2 = out["pine-hand"][0]
    st2["letzte_kerze"] = str(welt["bars"].index[-2])
    post2 = Post()
    pb.run(k, {"pine-hand": st2}, NOW, post=post2)
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
    out = pb.run(k, {"pine-hand": st}, NOW, post=Post())
    st2, _, fertig, _ = out["pine-hand"]
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
    assert (tmp_path / "journal" / "pine-hand" / "state.json").exists()
    cp = json.loads((tmp_path / "journal" / "pine-hand.json").read_text())
    assert cp["konto"] == "…4094" and cp["vorab"] == "suche/VORAB_pine5m.yaml"
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
    assert any(e["event"] == "Fehler" for e in out["pine-hand"][1])
    assert len(_orders(k, TP3.konto)) == 1


def test_anderes_konto_aktiv_nichts_tun(welt):
    _setze(welt, "long")
    k = Konto()
    k.aktiv_falsch = HAUPT
    out = pb.run(k, {}, NOW, post=Post())
    assert not _orders(k) and all(e["event"].startswith("anderes Konto") for b in out for e in out[b][1])
