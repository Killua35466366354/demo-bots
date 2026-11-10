"""Tests für gold/grossbox_bot.py: Modell wie die Gesamtrechnung (kein Blick in die Zukunft), Größen, Kauf und Verkauf
auf Account 6 (nie das Hauptkonto, nie die Dateien des Gold-Bots), Einstand nach dem ersten Ziel, Ausstieg bei neuer
Box, Sperren und Pause."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gold import grossbox_bot as gb
from gold import tiktok_schatten as ts
from suche.demo_bots import Quote, with_now_bar

HAUPT = "111111113150"
NOW = pd.Timestamp("2026-03-04 15:17", tz="UTC").to_pydatetime()


def _q(**kw):
    base = dict(bid=4000.0, offer=4000.3, tradeable=True, currency="USD", lot=1.0, min_size=0.01, size_step=0.01,
                margin_pct=5.0, decimals=2, min_dist=0.1, eur_rate=1.08)
    base.update(kw)
    return Quote(**base)


# --------------------------------------------------------------------------------------------------------------------
# Modell

def _zufall(n=1400, seed=4):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-05 00:00", periods=n, freq="15min")
    c = 4000 + np.cumsum(rng.normal(0.15, 3, n))
    o = np.r_[4000, c[:-1]]
    h = np.maximum(o, c) + rng.uniform(0, 2, n)
    lo = np.minimum(o, c) - rng.uniform(0, 2, n)
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx), pd.Series(0.3, index=idx)


def test_modell_ist_gross_box_ohne_kerzenfilter():
    bars, sp = _zufall()
    b = ts.basis(bars, sp)
    trades, gd = gb.modell(b)
    m15, h1, h4 = ts.ebene(b, "15m"), ts.ebene(b, "1h"), ts.ebene(b, "4h")
    assert [t["einstieg_zeit"] for t in trades] == [t["einstieg_zeit"] for t in ts.gross_box(b, m15, h1, h4, False)]
    assert {t["richtung"] for t in trades} <= {1, -1} and len(gd) == len(b)
    # jeder Trade geht in Richtung der großen Box zu seinem Einstieg
    assert trades and all(gd[t["_j0"]] == t["richtung"] for t in trades)


def test_live_wie_gesamtrechnung():
    """Je Lauf nur die fertigen Kerzen plus eine Kerze "jetzt": dieselben Einstiege und dieselben Box-Enden wie die
    Rechnung über alle Kerzen."""
    bars, sp = _zufall()
    b = ts.basis(bars, sp)
    trades, gd = gb.modell(b)
    n_all = len(bars)
    ab = n_all - 300
    gesamt = {t["_j0"]: (t["richtung"], t["art"]) for t in trades if t["_j0"] >= ab}
    live, box = {}, {}
    for k in range(ab, n_all):
        t_ph = bars.index[k - 1] + pd.Timedelta("15min")
        b2, s2 = with_now_bar(bars.iloc[:k], sp.iloc[:k], t_ph, bars["open"].iloc[k], bars["open"].iloc[k] + 0.3)
        bb = ts.basis(b2, s2)
        tr, g = gb.modell(bb, len(bb) - 1)
        kand = [t for t in tr if t["_j0"] == len(bb) - 1]
        if kand:
            live[k] = (kand[0]["richtung"], kand[0]["art"])
        box[k] = int(g[len(bb) - 1])
    assert len(gesamt) >= 5 and live == gesamt
    assert box == {k: int(gd[k]) for k in range(ab, n_all)}


def test_groessen():
    sizes, _ = gb.groessen(20.0, _q())
    assert sizes == [0.09, 0.18]                    # 5 € * 1,08 / 20 $ = 0,27 Unzen, ein Drittel und zwei Drittel
    sizes, warum = gb.groessen(2000.0, _q())
    assert sizes is None and "zu grob" in warum
    sizes, _ = gb.groessen(1.0, _q())
    assert sum(sizes) <= gb.MAX_OZ_TRADE + 1e-9


# --------------------------------------------------------------------------------------------------------------------
# Der Lauf auf dem Demokonto

class Antwort:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class Konto:
    """Capital.com zum Testen: Hauptkonto und Account 6, Gold-Positionen auf Account 6, Kerzen ohne Netz."""

    def __init__(self, bid=4000.0, offer=4000.3, konto6=True):
        self.account_id = HAUPT
        self.bid, self.offer = bid, offer
        self.konto6 = konto6
        self.pos: dict[str, dict] = {}
        self.fremd: list[dict] = []
        self.acts: dict[str, list] = {}
        self.calls: list = []
        self.refs: dict = {}
        self.nr = 0

    def accounts(self):
        out = [{"accountId": HAUPT, "balance": {"balance": 990.0, "available": 900.0}}]
        if self.konto6:
            out.append({"accountId": gb.KONTO, "balance": {"balance": 1000.0, "available": 1000.0}})
        return out

    def switch_account(self, aid):
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
        assert self.account_id == gb.KONTO, "Groß-Box darf nur auf Account 6 Positionen lesen"
        return [{"market": {"epic": "GOLD"}, "position": p} for p in self.pos.values()] + self.fremd

    def prices(self, epic, resolution, max_bars):
        return []

    def _get(self, path, **params):
        return {"prices": []}

    def _request(self, method, path, json=None):
        assert self.account_id == gb.KONTO
        self.calls.append((method, path, json))
        self.nr += 1
        ref = f"R{self.nr}"
        if method == "POST" and path == "/positions":
            deal = f"D{self.nr}"
            d = 1 if json["direction"] == "BUY" else -1
            level = self.offer if d > 0 else self.bid
            p = {"dealId": deal, "level": level, "size": json["size"], "direction": json["direction"],
                 "stopLevel": round(level - d * json["stopDistance"], 2)}
            if json.get("profitDistance"):
                p["profitLevel"] = round(level + d * json["profitDistance"], 2)
            self.pos[deal] = p
            self.refs[ref] = {"dealStatus": "ACCEPTED", "affectedDeals": [{"dealId": deal}], "level": level}
        elif method == "PUT":
            deal = path.rsplit("/", 1)[1]
            self.pos[deal].update(dict(json))
            if "profitLevel" not in json:
                self.pos[deal].pop("profitLevel", None)
            self.refs[ref] = {"dealStatus": "ACCEPTED"}
        return Antwort({"dealReference": ref})

    def confirm(self, ref):
        return self.refs.get(ref, {"dealStatus": "ACCEPTED"})

    def close_position(self, deal_id):
        assert self.account_id == gb.KONTO
        self.calls.append(("DELETE", deal_id))
        p = self.pos.pop(deal_id)
        return {"dealStatus": "ACCEPTED", "level": self.bid if p.get("direction") == "BUY" else self.offer}

    def activity(self, deal_id, since, until):
        return self.acts.get(deal_id, [])


def _bars_fuer(now, n=1300, kurs=4000.0):
    ende = pd.Timestamp(now).tz_convert(None).floor("15min") - pd.Timedelta("15min")
    idx = pd.date_range(end=ende, periods=n, freq="15min")
    x = np.full(n, kurs)
    return pd.DataFrame({"open": x, "high": x + 1, "low": x - 1, "close": x}, index=idx), pd.Series(0.3, index=idx)


@pytest.fixture
def welt(monkeypatch):
    """Kerzen und Modell zum Einstellen: modell["trades"] gibt gb.modell zurück (j0 "jetzt" = Kerze jetzt),
    modell["box"] ist die Richtung der großen Box in der Kerze "jetzt"."""
    welt = {"trades": [], "box": 1, "kerzen": None}

    def modell(b, n=None):
        n = len(b) - 1 if n is None else n
        trades = [dict(t, _j0=n if t["_j0"] == "jetzt" else t["_j0"]) for t in welt["trades"]]
        gd = np.zeros(len(b), int)
        gd[n] = welt["box"]
        return trades, gd

    from gold.bot import konten, rules
    monkeypatch.setattr(konten, "load", lambda *a: {})
    monkeypatch.setattr(rules, "bars_from_prices", lambda prices, now, tf: welt["kerzen"])
    monkeypatch.setattr(gb, "modell", modell)
    monkeypatch.setattr(gb, "vorab_ok", lambda: True)
    welt["kerzen"] = _bars_fuer(NOW)
    return welt


def _signal(d=1, j0="jetzt", dist=20.0, art="b"):
    return {"_j0": j0, "richtung": d, "r_usd": dist, "signal": "2026-03-04 15:00:00", "einstieg": 4000.0, "art": art,
            "einstieg_zeit": "2026-03-04 15:15:00", "offen": True}


def test_kauf_zwei_teile_auf_account_6(welt):
    welt["trades"] = [_signal(d=1)]
    k = Konto()
    st, log, fertig, blick = gb.run(k, {}, NOW)
    assert len(st["offen"]) == 1 and st["offen"][0]["richtung"] == 1
    teile = st["offen"][0]["teile"]
    assert [t["size"] for t in teile] == [0.09, 0.18]
    assert teile[0]["ziel"] == 4020.3 and teile[1]["ziel"] is None and {t["stop"] for t in teile} == {3980.3}
    posts = [c for c in k.calls if c[0] == "POST"]
    assert len(posts) == 2 and all(c[2]["direction"] == "BUY" and c[2]["stopDistance"] == 20.0 for c in posts)
    assert posts[0][2]["profitDistance"] == 20.0 and "profitDistance" not in posts[1][2]
    assert k.calls[0] == ("konto", gb.KONTO) and k.account_id == HAUPT       # zurück aufs Hauptkonto
    assert blick["grosse_box"] == "Kauf"
    # Nächster Lauf mit derselben Kerze: kein zweiter Trade
    st2, _, _, _ = gb.run(k, st, NOW)
    assert len([c for c in k.calls if c[0] == "POST"]) == 2 and len(st2["offen"]) == 1


def test_verkauf(welt):
    welt["trades"] = [_signal(d=-1)]
    welt["box"] = -1
    k = Konto()
    st, _, _, _ = gb.run(k, {}, NOW)
    teile = st["offen"][0]["teile"]
    assert st["offen"][0]["richtung"] == -1 and teile[0]["ziel"] == 3980.0 and {t["stop"] for t in teile} == {4020.0}
    assert all(c[2]["direction"] == "SELL" for c in k.calls if c[0] == "POST")


def test_nie_auf_dem_hauptkonto(welt):
    welt["trades"] = [_signal()]
    k = Konto(konto6=False)
    st, log, _, blick = gb.run(k, {}, NOW)
    assert not st["offen"] and not [c for c in k.calls if c[0] in ("POST", "konto")]
    assert log[0]["event"] == "kein Konto" and not gb.KONTO.endswith(gb.HAUPT_ENDUNG)


def test_sperren_und_grenzen(welt, monkeypatch):
    welt["trades"] = [_signal()]
    k = Konto()
    k.fremd = [{"market": {"epic": "GOLD"}, "position": {"dealId": "FREMD", "level": 3990.0, "size": 1}}]
    st, log, _, _ = gb.run(k, {}, NOW)
    assert not st["offen"] and "fremde Gold-Position auf dem Konto" in log[-1]["gruende"]
    k.fremd = []
    st, log, _, _ = gb.run(k, {"pausiert": {"seit": "x", "grund": "y"}}, NOW)
    assert not st["offen"] and "Pause ab -25 R" in log[-1]["gruende"]
    # schon 3 offen
    drei = {"offen": [_offener(f"T{i}") for i in range(3)]}
    for tr in drei["offen"]:
        _pos_aus(k, tr)
    st, log, _, _ = gb.run(k, drei, NOW)
    assert len(st["offen"]) == 3 and "schon 3 Trades offen" in log[-1]["gruende"]
    # anderer Gold-Bot laut journal/konten.json auf Account 6
    from gold.bot import konten
    monkeypatch.setattr(konten, "load", lambda *a: {"zuordnung": {"gold2": gb.KONTO, "r6-london-gbpusd": gb.KONTO}})
    st, log, _, _ = gb.run(Konto(), {}, NOW)
    assert not st["offen"] and any("gold2" in g for g in log[-1]["gruende"])


def test_ohne_siegel_nichts(welt, monkeypatch):
    monkeypatch.setattr(gb, "vorab_ok", lambda: False)
    welt["trades"] = [_signal()]
    k = Konto()
    st, log, _, _ = gb.run(k, {}, NOW)
    assert not st["offen"] and "VORAB_gold_grossbox.yaml nicht festgelegt" in log[-1]["gruende"]


def test_signal_zu_alt(welt):
    welt["trades"] = [_signal()]
    spaet = pd.Timestamp("2026-03-04 15:40", tz="UTC").to_pydatetime()
    welt["kerzen"] = _bars_fuer(NOW)                  # Kerze "jetzt" bleibt 15:15, der Lauf kommt 25 Min. später
    st, log, _, _ = gb.run(Konto(), {}, spaet)
    assert not st["offen"] and "Signal zu alt" in log[-1]["gruende"]


def _offener(tid="a", d=1, entry=4000.0, dist=20.0):
    return {"id": tid, "art": "b", "richtung": d, "einstieg_zeit": "2026-03-04 12:15:00", "dist": dist,
            "opened_utc": "2026-03-04T12:16:00", "tp1": False, "einstand": None, "box_ende": None, "signal": "s",
            "teile": [{"dealId": f"{tid}P{i}", "size": s, "entry": entry, "stop": entry - d * dist, "ziel": z,
                       "ziel_orig": z, "ziel_nr": i + 1, "offen": True}
                      for i, (s, z) in enumerate(((0.09, entry + d * dist), (0.18, None)))]}


def _pos_aus(k, tr):
    for t in tr["teile"]:
        if t["offen"]:
            k.pos[t["dealId"]] = {"dealId": t["dealId"], "level": t["entry"], "size": t["size"],
                                  "direction": "BUY" if tr["richtung"] > 0 else "SELL",
                                  "stopLevel": t["stop"], "profitLevel": t["ziel"]}


def test_erstes_ziel_dann_einstand(welt):
    tr = _offener()
    k = Konto(bid=4022.0, offer=4022.3)
    _pos_aus(k, tr)
    del k.pos["aP0"]                                             # erstes Drittel am Ziel geschlossen
    k.acts["aP0"] = [{"dateUTC": "2026-03-04T14:00:00", "source": "TP", "type": "POSITION", "status": "ACCEPTED",
                      "details": {"level": 4020.0, "actions": [{"actionType": "POSITION_CLOSED"}]}}]
    st, log, _, _ = gb.run(k, {"offen": [tr]}, NOW)
    t = st["offen"][0]
    assert t["tp1"] and t["einstand"] and t["teile"][0]["grund"] == "ziel"
    assert k.pos["aP1"]["stopLevel"] == 4000.0 and "profitLevel" not in k.pos["aP1"]
    # Danach Stop am Einstand: Trade fertig mit 1/3 * 1 R
    del k.pos["aP1"]
    k.acts["aP1"] = [{"dateUTC": "2026-03-04T15:10:00", "source": "SL", "type": "POSITION", "status": "ACCEPTED",
                      "details": {"level": 4000.0, "actions": [{"actionType": "POSITION_CLOSED"}]}}]
    st2, _, fertig, _ = gb.run(k, st, NOW)
    assert not st2["offen"] and fertig[0]["r"] == pytest.approx(1 / 3, abs=1e-3)
    assert [x["grund"] for x in fertig[0]["teile"]] == ["ziel", "einstand"] and fertig[0]["seite"] == "Kauf"


def test_einstand_zu_nah_schliesst_zum_markt(welt):
    tr = _offener()
    tr["tp1"] = True
    tr["teile"][0].update(offen=False, exit=4020.0, grund="ziel")
    k = Konto(bid=4000.05, offer=4000.35)                        # Kurs schon fast am Einstieg
    _pos_aus(k, tr)
    st, log, fertig, _ = gb.run(k, {"offen": [tr]}, NOW)
    assert not st["offen"] and ("DELETE", "aP1") in k.calls
    assert fertig[0]["teile"][1]["grund"] == "einstand"


def test_neue_box_schliesst_im_plus_und_im_minus(welt):
    welt["box"] = 0                                             # 1 Std. und 4 Std. nicht mehr einig: Box zu Ende
    for bid, r in ((4010.0, 0.5), (3990.0, -0.5)):
        tr = _offener()
        k = Konto(bid=bid, offer=bid + 0.3)
        _pos_aus(k, tr)
        st, log, fertig, _ = gb.run(k, {"offen": [tr]}, NOW)
        assert not st["offen"] and fertig[0]["r"] == pytest.approx(r, abs=1e-3)
        assert {x["grund"] for x in fertig[0]["teile"]} == {"neue_box"}
        assert any(e["event"] == "Box zu Ende" for e in log)


def test_box_dreht_alter_trade_zu_neuer_in_gegenrichtung(welt):
    welt["box"] = -1
    welt["trades"] = [_signal(d=-1, art="a")]
    tr = _offener()
    k = Konto(bid=4010.0, offer=4010.3)
    _pos_aus(k, tr)
    st, log, fertig, _ = gb.run(k, {"offen": [tr]}, NOW)
    assert fertig and fertig[0]["richtung"] == 1
    assert len(st["offen"]) == 1 and st["offen"][0]["richtung"] == -1
    # schlägt das Schließen fehl, kommt kein Trade der Gegenrichtung dazu (kein Hedging)
    k2 = Konto(bid=4010.0, offer=4010.3)
    _pos_aus(k2, tr)
    k2.close_position = lambda deal_id: (_ for _ in ()).throw(RuntimeError("Netz weg"))
    st2, log2, _, _ = gb.run(k2, {"offen": [tr]}, NOW)
    assert [x["richtung"] for x in st2["offen"]] == [1]
    assert "ein Trade der Gegenrichtung ist noch offen (kein Hedging)" in log2[-1]["gruende"]


def test_pause_ab_minus_25_r(welt):
    tr = _offener()
    k = Konto(bid=3980.0, offer=3980.3)
    k.acts = {f"aP{i}": [{"dateUTC": "2026-03-04T15:00:00", "source": "SL", "type": "POSITION", "status": "ACCEPTED",
                          "details": {"level": 3980.0, "actions": []}}] for i in range(2)}
    st, log, fertig, _ = gb.run(k, {"offen": [tr], "summe_r": -24.5, "trades": 60}, NOW)
    assert fertig[0]["r"] == -1.0 and st["summe_r"] == -25.5 and st["pausiert"]


def test_trockenlauf_aendert_nichts(welt):
    welt["trades"] = [_signal()]
    k = Konto()
    st, log, _, _ = gb.run(k, {}, NOW, send_orders=False)
    assert not [c for c in k.calls if c[0] in ("POST", "PUT", "DELETE")] and log[-1]["event"] == "würde kaufen"


def test_schreibt_nur_eigene_dateien(tmp_path):
    gb.schreiben({"offen": [], "stand": "x"}, [{"event": "e"}], [{"r": 1.0, "pnl_eur": 4.0}], {"grosse_box": "Kauf"},
                 tmp_path / "gg", tmp_path / "gold-grossbox.json")
    assert sorted(p.name for p in (tmp_path / "gg").iterdir()) == ["log.jsonl", "state.json", "trades.jsonl"]
    c = json.loads((tmp_path / "gold-grossbox.json").read_text(encoding="utf-8"))
    assert c["zusammenfassung"]["trades"] == 1 and c["status"].startswith("kein Trade offen")
    with pytest.raises(RuntimeError):
        gb.schreiben({}, [], [], {}, tmp_path / "x", tmp_path / "gold-state.json")
    assert gb.JDIR.name == "gold-grossbox" and gb.COCKPIT.name not in gb.GOLD_BOT_DATEIEN


def test_urteil_nach_40():
    gut = [{"r": 2.0}] * 20 + [{"r": -1.0}] * 20
    assert gb.bewertung(gut)["urteil"].startswith("bestanden")
    schlecht = [{"r": -1.0}] * 12 + [{"r": 0.5}] * 3
    assert gb.bewertung(schlecht)["urteil"].startswith("Zwischencheck")


def test_vorab_und_workflow():
    vorab = gb.VORAB.read_text(encoding="utf-8")
    assert gb.KONTO in vorab and "-25 R" in vorab and "5 Euro Risiko" in vorab
    wf = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "demo-bots.yml").read_text(encoding="utf-8")
    assert "tests/test_grossbox_bot.py" in wf and "python -m gold.grossbox_bot" in wf
    assert "touch .tests-ok/gold_grossbox" in wf
