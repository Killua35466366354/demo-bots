"""Tests für gold/ausbruch4h_bot.py: Der Bot sieht mit Stundenkerzen dieselben Einstiege, Stops und Ausstiege wie der
Test der Gold-Matrix mit 1-Minuten-Kerzen. Er handelt nur auf Account 4 (nie das Hauptkonto, nie die Dateien des
Gold-Bots), höchstens einen Trade, mit Stop beim Broker, und steigt nach 4 fertigen 4-Std.-Kerzen aus. Alle Kurse und
Kontonummern hier sind erfunden."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from gold import ausbruch4h_bot as ab
from suche import gold_ausbruch4h_gegenprobe as gp
from suche import gold_matrix as gm
from suche.demo_bots import Quote

ROOT = Path(__file__).resolve().parents[1]
HAUPT = "111111113150"
MIN = pd.Timedelta(minutes=1)
# Termine der erfundenen Welt: einer mitten in einer Kerze, einer genau zum Schluss einer 4-Std.-Kerze (14:00 New York)
TERMINE = np.array(["2026-01-09T13:30", "2026-03-18T18:00"], dtype="datetime64[ns]")
VON, BIS = "2026-01-01", "2026-03-21"


def handelszeiten(von: str, bis: str) -> pd.DatetimeIndex:
    idx = pd.date_range(von, bis, freq="1min", inclusive="left")
    ny = idx.tz_localize("UTC").tz_convert("America/New_York")
    zu = ((ny.weekday == 4) & (ny.hour >= 17)) | (ny.weekday == 5) | ((ny.weekday == 6) & (ny.hour < 18)) | (ny.hour == 17)
    return idx[~zu]


def erfundener_markt(von="2025-09-01", bis="2026-03-28", seed=3, start=4000.0) -> pd.DataFrame:
    """1-Minuten-Kerzen mit Wochenenden und Handelspause. Erst steigt der Kurs, dann fällt er: So gibt es Ausbrüche mit
    dem Tagestrend in beide Richtungen."""
    rng = np.random.default_rng(seed)
    idx = handelszeiten(von, bis)
    n = len(idx)
    drift = np.where(np.arange(n) < n * 0.55, 2.5e-6, -3.0e-6)
    c = start * np.exp(np.cumsum(rng.normal(drift, 0.00028, n)))
    o = np.r_[start, c[:-1]]
    h = np.maximum(o, c) * (1 + rng.uniform(0, 0.0002, n))
    lo = np.minimum(o, c) * (1 - rng.uniform(0, 0.0002, n))
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx).round(2)


@pytest.fixture(autouse=True)
def _welt_regeln(monkeypatch):
    from gold.bot import konten
    monkeypatch.setattr(gm, "lies_termine", lambda: TERMINE)
    monkeypatch.setattr(ab, "MIN_TAGESKERZEN", 60)             # die erfundene Welt ist nur 7 Monate lang
    monkeypatch.setattr(ab, "vorab_ok", lambda: True)
    monkeypatch.setattr(konten, "load", lambda *a: {})


@pytest.fixture(scope="module")
def w():
    """Die erfundene Welt: 1-Minuten-Kerzen, der Markt des Tests, die Stundenkerzen des Brokers und alles, was der Test
    im Fenster handeln dürfte."""
    g = erfundener_markt()
    m = gm.markt(g, termine=TERMINE)
    f = ab.V
    e, d = gm.einstiege(m, f["einstieg"], f["ebene"])
    drin = gm.im_fenster(m, e, pd.Timestamp(VON), pd.Timestamp(BIS))
    e, d = e[drin], d[drin]
    ok = gm.filter_maske(m, f["filter"], f["ebene"], e, d)
    dist = gm.stop_abstand(m, f["stop_art"], f["stop_ebene"], e, d)
    gut = ok & (dist >= gm.MIN_ABSTAND)
    test = {pd.Timestamp(m.t[e[i]]): (int(d[i]), float(dist[i])) for i in np.flatnonzero(gut)}
    trades = gm.trades_von(m, f, pd.Timestamp(VON), pd.Timestamp(BIS))
    return SimpleNamespace(g=g, m=m, std=gp.stunden_aus_minuten(g), test=test, trades=trades,
                           lang=sorted(t for t, v in test.items() if v[0] > 0),
                           kurz=sorted(t for t, v in test.items() if v[0] < 0))


def kurs_um(w, t) -> float:
    """Eröffnung der 1-Minuten-Kerze zur Zeit t (im Test der Bid beim Einstieg)."""
    return float(w.g["open"].loc[pd.Timestamp(t)])


def utc(t) -> "pd.Timestamp":
    return pd.Timestamp(t).tz_localize("UTC").to_pydatetime()


# --------------------------------------------------------------------------------------------------------------------
# Bot und Test sehen dasselbe

def test_bot_sieht_dieselben_einstiege_stops_und_ausstiege_wie_der_test(w, monkeypatch):
    monkeypatch.setattr(gm, "VORLAUF_AB", pd.Timestamp("2025-09-01"))
    res = gp.gegenprobe(w.g, VON, BIS)
    assert res["test_einstiege_erlaubt"] == len(w.test) >= 15
    assert res["bot_einstiege_erlaubt"] == res["beide"] == res["richtung_gleich"] == len(w.test)
    assert res["nur_bot"] == [] and res["nur_test"] == [] and res["test_ohne_grenze"] == []
    assert res["stop_abstand_abweichung_usd"]["groesste"] < 1e-3
    assert res["trades_im_test"] == len(w.trades) >= 10 and res["trades_einstieg_gleich"] == len(w.trades)
    assert res["trades_ausstieg_nach_zeit"] >= 8 and res["trades_ausstieg_gleich"] == res["trades_ausstieg_nach_zeit"]
    assert res["abweichungen"] == [] and w.lang and w.kurz
    # die Handelspause jeden Abend: Dort fehlt die Stunde vor dem Schluss, der Bot nimmt nichts
    assert res["bot_wartet_auf_kerze"] >= 50


def test_variante_kommt_aus_der_versiegelten_finalisten_liste():
    assert ab.V["key"] == ab.VARIANTE == "ausbruch.4h.trend_hoch.swing_4h.zeit_4h"
    assert (ab.V["stop_art"], ab.V["stop_ebene"], ab.V["aus_ebene"], ab.ZEIT_KERZEN) == ("swing", "4h", "4h", 4)
    assert ab.V["modus"] == gm.MODUS["zeit"]


def test_signal_haengt_nicht_an_der_zukunft_und_nicht_an_der_unfertigen_stunde(w):
    t_g = w.lang[0]
    kurs = kurs_um(w, t_g)
    a = ab.signal(w.std[w.std.index < t_g], t_g, t_g, kurs)
    b = ab.signal(w.std, t_g, t_g + 3 * MIN, kurs)             # mit allen späteren Kerzen und einem späteren Lauf
    assert a["ok"] and (a["richtung"], a["dist"], a["trend"]) == (b["richtung"], b["dist"], b["trend"]) == (
        1, round(w.test[t_g][1], 4), True)
    assert a["schluss"] > a["hoch_davor"]


def test_signal_wartet_wenn_die_letzte_stunde_fehlt_oder_zu_wenig_tage_da_sind(w, monkeypatch):
    t_g = w.lang[0]
    ohne = w.std[w.std.index < t_g - ab.STUNDE]
    s = ab.signal(ohne, t_g, t_g, kurs_um(w, t_g))
    assert s["warten"] and not s["ok"] and "Stundenkerze" in s["ergebnis"]
    monkeypatch.setattr(ab, "MIN_TAGESKERZEN", 500)
    s = ab.signal(w.std[w.std.index < t_g], t_g, t_g, kurs_um(w, t_g))
    assert s["warten"] and not s["ok"] and "zu wenig Kerzen" in s["ergebnis"]


def test_gegen_den_tagestrend_gibt_es_keinen_einstieg(w):
    """Ein Ausbruch nach oben, während der Tag unter seinem EMA 50 liegt: Der Test nimmt ihn nicht, der Bot auch nicht."""
    f = ab.V
    e, d = gm.einstiege(w.m, f["einstieg"], f["ebene"])
    ok = gm.filter_maske(w.m, f["filter"], f["ebene"], e, d)
    gegen = [pd.Timestamp(w.m.t[i]) for i in e[~ok] if pd.Timestamp(VON) <= pd.Timestamp(w.m.t[i]) < pd.Timestamp(BIS)]
    assert gegen
    s = ab.signal(w.std[w.std.index < gegen[0]], gegen[0], gegen[0], kurs_um(w, gegen[0]))
    assert s["richtung"] != 0 and s["trend"] is False and not s["ok"] and "gegen den Tagestrend" in s["ergebnis"]


@pytest.mark.parametrize("jetzt, beginn, naechste", [
    ("2026-01-07 12:10", "2026-01-07 11:00", "2026-01-07 15:00"),      # Winter: 6 Uhr New York ist 11 Uhr UTC
    ("2026-07-01 14:01", "2026-07-01 14:00", "2026-07-01 18:00"),      # Sommer: 10 Uhr New York ist 14 Uhr UTC
    ("2026-11-01 05:30", "2026-11-01 02:00", "2026-11-01 07:00"),      # Uhr zurück: diese Kerze dauert 5 Stunden
    ("2026-03-08 08:10", "2026-03-08 07:00", "2026-03-08 10:00"),      # Uhr vor: diese Kerze dauert 3 Stunden
])
def test_grenzen_der_4h_kerzen_liegen_auf_new_york(jetzt, beginn, naechste):
    assert ab.grenze(pd.Timestamp(jetzt)) == pd.Timestamp(beginn)
    assert ab.naechste_grenze(pd.Timestamp(jetzt)) == pd.Timestamp(naechste)
    idx = pd.date_range(beginn, naechste, freq="1min", inclusive="left")
    assert len(set(ab._block(idx))) == 1 and ab._block(pd.DatetimeIndex([naechste]))[0] != ab._block(idx)[0]


def test_sperre_ist_die_des_tests():
    zeiten = pd.date_range("2026-01-09 12:00", "2026-01-10 00:00", freq="1min")
    m = gm.markt(pd.DataFrame(1.0, index=zeiten, columns=ab.SPALTEN), termine=TERMINE)
    assert (ab.gesperrt(zeiten) == m.gesperrt).all()
    assert list(ab.gesperrt(["2026-01-09 13:14", "2026-01-09 13:15", "2026-01-09 13:45", "2026-01-09 13:46"])) == [
        False, True, True, False]
    assert list(ab.gesperrt(["2026-01-09 20:54", "2026-01-09 20:55", "2026-01-09 23:04", "2026-01-09 23:05"])) == [
        False, True, True, False]


def test_handelstag_zaehlt_naechte_wie_der_test(w):
    i = np.arange(0, len(w.m), 997)
    assert [ab.handelstag(pd.Timestamp(t)) for t in w.m.t[i]] == list(w.m.tag[i])
    assert ab.handelstag("2026-01-09 21:59") + 1 == ab.handelstag("2026-01-09 22:00")      # 17:00 New York im Winter


def test_groesse():
    q = _q()
    assert ab.groesse(60.0, q) == (0.09, "")                    # 5 € * 1,08 / 60 $ = 0,09 Unzen
    assert ab.groesse(2.5, q)[0] <= ab.MAX_OZ
    size, warum = ab.groesse(2000.0, q)
    assert size is None and "zu grob" in warum
    assert ab.groesse(60.0, _q(eur_rate=None))[0] is None


def _q(**kw):
    base = dict(bid=4000.0, offer=4000.5, tradeable=True, currency="USD", lot=1.0, min_size=0.01, size_step=0.01,
                margin_pct=5.0, decimals=2, min_dist=0.1, eur_rate=1.08)
    base.update(kw)
    return Quote(**base)


# --------------------------------------------------------------------------------------------------------------------
# Der Lauf auf dem Demokonto

class Antwort:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class Konto:
    """Capital.com zum Testen: Hauptkonto und Account 4, Gold-Positionen auf Account 4, Stundenkerzen aus der
    erfundenen Welt. Der Abruf liefert wie der Broker auch die noch laufende Stunde."""

    def __init__(self, std, bid=4000.0, konto4=True, frei=500.0):
        self.account_id = HAUPT
        self.std = std
        self.bid, self.offer = bid, bid + 0.5
        self.konto4, self.frei, self.markt_auf = konto4, frei, True
        self.fehlt: set = set()
        self.pos: dict[str, dict] = {}
        self.fremd: list[dict] = []
        self.acts: dict[str, list] = {}
        self.calls: list = []
        self.abrufe: list = []
        self.refs: dict = {}
        self.nr = 0
        self.order_fehler = False
        self.positionen_fehler = 0

    def accounts(self):
        out = [{"accountId": HAUPT, "balance": {"balance": 990.0, "available": 900.0}}]
        if self.konto4:
            out.append({"accountId": ab.KONTO, "balance": {"balance": 1000.0, "available": self.frei}})
        return out

    def switch_account(self, aid):
        self.calls.append(("konto", aid))
        self.account_id = aid

    def market(self, epic):
        if epic == "GOLD":
            return {"snapshot": {"bid": self.bid, "offer": self.offer, "decimalPlacesFactor": 2,
                                 "marketStatus": "TRADEABLE" if self.markt_auf else "CLOSED"},
                    "instrument": {"currency": "USD", "lotSize": 1, "marginFactor": 5, "marginFactorUnit": "PERCENTAGE"},
                    "dealingRules": {"minDealSize": {"value": 0.01}, "minSizeIncrement": {"value": 0.01},
                                     "minStopOrProfitDistance": {"unit": "POINTS", "value": 0.1}}}
        return {"snapshot": {"bid": 1.08, "offer": 1.08}}

    def positions(self):
        assert self.account_id == ab.KONTO, "der Bot darf nur auf Account 4 Positionen lesen"
        if self.positionen_fehler:
            self.positionen_fehler -= 1
            raise RuntimeError("Netz weg")
        return [{"market": {"epic": "GOLD"}, "position": p} for p in self.pos.values()] + self.fremd

    def _get(self, path, **params):
        assert path == "/prices/GOLD" and params["resolution"] == "HOUR" and params["max"] == 1000
        von, bis = pd.Timestamp(params["from"]), pd.Timestamp(params["to"])
        assert bis - von <= pd.Timedelta(days=40)
        self.abrufe.append((von, bis))
        df = self.std[(self.std.index >= von) & (self.std.index <= bis) & ~self.std.index.isin(list(self.fehlt))]
        assert len(df) <= 1000
        return {"prices": [{"snapshotTimeUTC": t.strftime("%Y-%m-%dT%H:%M:%S"),
                            **{f"{n}Price": {"bid": float(x), "ask": float(x) + 0.5}
                               for n, x in zip(("open", "high", "low", "close"), row)}}
                           for t, row in zip(df.index, df[ab.SPALTEN].to_numpy())]}

    def _request(self, method, path, json=None):
        assert self.account_id == ab.KONTO
        self.calls.append((method, path, json))
        self.nr += 1
        ref = f"R{self.nr}"
        assert method == "POST" and path == "/positions"
        deal = f"D{self.nr}"
        d = 1 if json["direction"] == "BUY" else -1
        level = self.offer if d > 0 else self.bid
        self.pos[deal] = {"dealId": deal, "level": level, "size": json["size"], "direction": json["direction"],
                          "stopLevel": round(level - d * json["stopDistance"], 2)}
        self.refs[ref] = {"dealStatus": "ACCEPTED", "affectedDeals": [{"dealId": deal}], "level": level}
        if self.order_fehler:
            raise RuntimeError("Zeitüberschreitung")
        return Antwort({"dealReference": ref})

    def confirm(self, ref):
        return self.refs.get(ref, {"dealStatus": "ACCEPTED"})

    def close_position(self, deal_id):
        assert self.account_id == ab.KONTO
        self.calls.append(("DELETE", deal_id))
        p = self.pos.pop(deal_id)
        return {"dealStatus": "ACCEPTED", "level": self.bid if p.get("direction") == "BUY" else self.offer}

    def activity(self, deal_id, since, until):
        assert until - since <= pd.Timedelta(days=1)
        return self.acts.get(deal_id, [])

    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]


def test_kauf_wie_im_test_auf_account_4(w):
    t_g = w.lang[0]
    d, dist = w.test[t_g]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, fertig, blick = ab.run(k, {}, utc(t_g + MIN))
    tr = st["trade"]
    assert tr["richtung"] == d == 1 and tr["dist"] == round(dist, 2) and tr["grenze"] == str(t_g)
    assert tr["size"] == ab.groesse(round(dist, 2), _q())[0] and tr["entry"] == k.offer
    assert tr["stop"] == round(k.offer - dist, 2) and tr["spaet_min"] == 1.0
    assert k.posts() == [("POST", "/positions", {"epic": "GOLD", "direction": "BUY", "size": tr["size"],
                                                  "guaranteedStop": False, "stopDistance": round(dist, 2)})]
    assert k.calls[0] == ("konto", ab.KONTO) and k.account_id == HAUPT             # zurück aufs Hauptkonto
    assert st["letzte_grenze"] == str(t_g) and log[-1]["event"] == "Kauf eröffnet"
    assert blick["signal"]["ok"] and ab.status(st).startswith("Kauf offen ab")
    # ein kleiner Abruf für die letzte Stunde, dann 400 Tage in Stücken zu 40 Tagen
    assert len(k.abrufe) == 1 + 10 and k.abrufe[1][1] - k.abrufe[-1][0] == pd.Timedelta(days=ab.TAGE_KERZEN)
    # der nächste Lauf in derselben Kerze öffnet nichts Zweites
    st2, _, _, _ = ab.run(k, st, utc(t_g + 16 * MIN))
    assert len(k.posts()) == 1 and st2["trade"]["dealId"] == tr["dealId"]


def test_verkauf_wie_im_test(w):
    t_g = w.kurz[0]
    d, dist = w.test[t_g]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, _, _ = ab.run(k, {}, utc(t_g + MIN))
    tr = st["trade"]
    assert tr["richtung"] == d == -1 and tr["dist"] == round(dist, 2) and tr["entry"] == k.bid
    assert tr["stop"] == round(k.bid + dist, 2) and k.posts()[0][2]["direction"] == "SELL"
    assert "profitDistance" not in k.posts()[0][2] and log[-1]["event"] == "Verkauf eröffnet"


def _ohne_ausbruch(w):
    """Ein 4-Std.-Schluss am Vormittag, zu dem der Test nichts sieht."""
    for t in pd.date_range("2026-02-02 11:00", "2026-02-20 11:00", freq="1D"):
        if t in w.std.index and not ab.signal(w.std[w.std.index < t], t, t, kurs_um(w, t))["richtung"]:
            return t
    raise AssertionError("kein Schluss ohne Ausbruch gefunden")


def test_ohne_ausbruch_wird_die_kerze_einmal_geprueft(w):
    t_g = _ohne_ausbruch(w)
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, _, blick = ab.run(k, {}, utc(t_g + MIN))
    assert st["trade"] is None and not k.posts() and not log
    assert st["letzte_pruefung"] == {"grenze": str(t_g), "ergebnis": "kein Ausbruch", **{
        x: st["letzte_pruefung"][x] for x in ("richtung", "schluss", "hoch_davor", "tief_davor", "trend", "dist")}}
    n = len(k.abrufe)
    st2, _, _, _ = ab.run(k, st, utc(t_g + 16 * MIN))
    assert len(k.abrufe) == n and ab._ohne_zeit(st2) == ab._ohne_zeit(st)       # kein zweiter Abruf, nichts Neues
    # mitten in der Kerze rechnet der Bot gar nicht
    st3, _, _, _ = ab.run(k, st, utc(t_g + 90 * MIN))
    assert len(k.abrufe) == n and "kein Trade offen. Letzte Kerze" in ab.status(st3)


def test_nie_auf_dem_hauptkonto(w):
    k = Konto(w.std, konto4=False)
    st, log, _, blick = ab.run(k, {}, utc(w.lang[0] + MIN))
    assert st["trade"] is None and not [c for c in k.calls if c[0] in ("POST", "konto")]
    assert log[0]["event"] == "kein Konto" and "nicht gefunden" in blick["status"]
    assert not ab.KONTO.endswith(ab.HAUPT_ENDUNG) and ab.KONTO_NAME == "Account 4"


def test_sperren(w, monkeypatch):
    t_g = w.lang[0]
    jetzt = utc(t_g + MIN)

    def lauf(state=None, **kw):
        k = Konto(w.std, bid=kurs_um(w, t_g), **kw)
        return k, ab.run(k, state or {}, jetzt)

    k = Konto(w.std, bid=kurs_um(w, t_g))
    k.fremd = [{"market": {"epic": "GOLD"}, "position": {"dealId": "FREMD", "level": 3990.0, "size": 1}}]
    st, log, _, _ = ab.run(k, {}, jetzt)
    assert st["trade"] is None and not k.posts() and "fremde Gold-Position auf dem Konto" in log[-1]["gruende"]
    assert st["letzte_grenze"] == str(t_g) and st["fremd"] == ["FREMD"]
    assert not [c for c in k.calls if c[0] == "DELETE"]                         # Fremdes fasst er nie an
    k, (st, log, _, _) = lauf({"pausiert": {"seit": "x", "grund": "y"}})
    assert not k.posts() and "Pause ab -25 R" in log[-1]["gruende"]
    k, (st, log, _, _) = lauf(frei=20.0)                                        # Margin wäre mehr als ein Fünftel
    assert not k.posts() and any("des freien Gelds" in g for g in log[-1]["gruende"])
    monkeypatch.setattr(ab, "vorab_ok", lambda: False)
    k, (st, log, _, _) = lauf()
    assert not k.posts() and any("nicht festgelegt" in g for g in log[-1]["gruende"])
    monkeypatch.setattr(ab, "vorab_ok", lambda: True)
    from gold.bot import konten
    monkeypatch.setattr(konten, "load", lambda *a: {"zuordnung": {"gold2": ab.KONTO, "r6-vortag-eurusd": ab.KONTO}})
    k, (st, log, _, _) = lauf()
    assert not k.posts() and any("gold2" in g and "r6-vortag" not in g for g in log[-1]["gruende"])


def test_frist_und_start_mitten_in_der_kerze(w):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, _, _ = ab.run(k, {}, utc(t_g + 26 * MIN))                          # frischer Bot, Frist vorbei
    assert not k.posts() and not k.abrufe and "Start des Bots" in st["letzte_pruefung"]["ergebnis"]
    st, log, _, _ = ab.run(k, {"letzte_grenze": "2026-01-01 03:00:00"}, utc(t_g + 26 * MIN))
    assert not k.posts() and not k.abrufe and st["letzte_pruefung"]["ergebnis"].startswith("verfallen")
    st, _, _, _ = ab.run(k, {}, utc(t_g + 25 * MIN))                            # gerade noch in der Frist
    assert len(k.posts()) == 1


def test_fehlt_die_letzte_stundenkerze_sieht_der_naechste_lauf_nach(w):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    k.fehlt = {t_g - ab.STUNDE}
    st, log, _, blick = ab.run(k, {}, utc(t_g + MIN))
    assert not k.posts() and "Stundenkerze" in blick["wartet"] and st.get("letzte_grenze") is None
    assert len(k.abrufe) == 1                                                    # nur der kleine Abruf
    k.fehlt = set()
    st, log, _, _ = ab.run(k, st, utc(t_g + 16 * MIN))
    assert len(k.posts()) == 1 and st["trade"]["spaet_min"] == 16.0


def test_handelspause_und_termin_sperren_ohne_abruf(w):
    abend = pd.Timestamp("2026-02-10 23:00")                                    # 18 Uhr New York, Handelspause
    k = Konto(w.std)
    st, log, _, _ = ab.run(k, {}, utc(abend + MIN))
    assert not k.abrufe and not k.posts() and "Sperre" in st["letzte_pruefung"]["ergebnis"]
    termin = pd.Timestamp("2026-03-18 18:00")                                   # Termin genau zum Schluss der Kerze
    assert ab.grenze(termin + MIN) == termin
    st, log, _, _ = ab.run(Konto(w.std), {}, utc(termin + 16 * MIN))            # auch wenn der Lauf erst danach kommt
    assert "Sperre" in st["letzte_pruefung"]["ergebnis"] and st["letzte_grenze"] == str(termin)


def test_markt_zu_wartet(w):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    k.markt_auf = False
    st, _, _, blick = ab.run(k, {}, utc(t_g + MIN))
    assert not k.posts() and blick["wartet"] == "Markt zu" and st.get("letzte_grenze") is None


def _signal(d=1, dist=60.0):
    return {"grenze": "x", "richtung": d, "trend": True, "dist": dist, "gesperrt": False, "ok": True, "warten": False,
            "ergebnis": "Ausbruch", "schluss": 1.0, "hoch_davor": 1.0, "tief_davor": 1.0}


def _offener(w, zeile, deal="D0", size=0.09):
    """Ein Trade des Tests als offener Trade des Bots (Zustand und Position beim Broker)."""
    t_g, d, dist = pd.Timestamp(zeile.zeit), int(zeile.d), round(float(zeile.r_usd), 2)
    entry = round(kurs_um(w, t_g) + (0.5 if d > 0 else 0.0), 2)
    tr = {"id": f"{t_g:%Y-%m-%dT%H:%M}", "richtung": d, "grenze": str(t_g), "dealId": deal, "size": size,
          "entry": entry, "stop": round(entry - d * dist, 2), "dist": dist,
          "opened_utc": (t_g + MIN).isoformat(timespec="seconds"), "spaet_min": 1.0, "kerzen": 0}
    pos = {"dealId": deal, "level": entry, "size": size, "direction": "BUY" if d > 0 else "SELL", "stopLevel": tr["stop"]}
    return {"trade": tr, "letzte_grenze": str(t_g), "start": "2026-01-01T00:00:00", "summe_r": 0.0, "trades": 0}, pos


def _zeit_trade(w, wochenende=False):
    for z in w.trades.itertuples():
        ueber_we = pd.Timestamp(z.zeit_aus) - pd.Timestamp(z.zeit) > pd.Timedelta(days=2)
        if z.grund == "regel" and ueber_we == wochenende:
            return z
    raise AssertionError("kein passender Trade in der erfundenen Welt")


def test_ausstieg_nach_vier_fertigen_kerzen_in_der_minute_des_tests(w, monkeypatch):
    z = _zeit_trade(w)
    te, tx = pd.Timestamp(z.zeit), pd.Timestamp(z.zeit_aus)
    st0, pos = _offener(w, z)
    k = Konto(w.std, bid=kurs_um(w, tx))
    k.pos["D0"] = pos
    st, log, fertig, _ = ab.run(k, st0, utc(tx - 14 * MIN))                     # letzter Lauf vor dem Schluss
    assert st["trade"]["kerzen"] == 3 and not fertig and ("DELETE", "D0") not in k.calls
    monkeypatch.setattr(ab, "signal", lambda *a: _signal(d=int(z.d)))           # selbst mit neuem Signal in dieser Kerze
    st, log, fertig, _ = ab.run(k, st, utc(tx + MIN))
    assert ("DELETE", "D0") in k.calls and st["trade"] is None and not k.posts()
    f = fertig[0]
    d, dist, entry = int(z.d), st0["trade"]["dist"], st0["trade"]["entry"]
    aus = k.bid if d > 0 else k.offer
    naechte = ab.handelstag(tx + MIN) - ab.handelstag(te + MIN)
    gebuehr = (gm.SATZ_LONG if d > 0 else gm.SATZ_SHORT) / 36500.0 * naechte * entry / dist
    assert f["grund"] == "zeit" and f["kerzen"] == 4 and f["naechte"] == naechte and f["exit"] == round(aus, 2)
    assert f["r"] == pytest.approx(d * (aus - entry) / dist - gebuehr, abs=2e-3) and f["gebuehr_r"] >= 0
    assert f["pnl_eur"] == pytest.approx(0.09 * d * (aus - entry) / 1.08, abs=0.01)
    assert st["trades"] == 1 and st["summe_r"] == f["r"] and st["letzter_schluss"] == f["closed_utc"]
    # Im Test nimmt ein Signal dieselbe Minute wie der Ausstieg nie. Der Bot auch nicht.
    assert "endete erst nach dem Schluss" in st["letzte_pruefung"]["ergebnis"]


def test_ausstieg_ueber_das_wochenende_wartet_auf_die_oeffnung(w):
    z = _zeit_trade(w, wochenende=True)
    tx = pd.Timestamp(z.zeit_aus)
    st0, pos = _offener(w, z)
    k = Konto(w.std, bid=kurs_um(w, tx))
    k.pos["D0"] = pos
    k.markt_auf = False
    samstag = tx - pd.Timedelta(days=1)
    st, _, fertig, blick = ab.run(k, st0, utc(samstag))                         # die Uhr sagt 4 Kerzen, der Markt ist zu
    assert not fertig and ("DELETE", "D0") not in k.calls and blick["wartet"] == "Ausstieg fällig, Markt zu"
    k.markt_auf = True
    st, _, fertig, _ = ab.run(k, st, utc(tx + MIN))
    assert fertig[0]["grund"] == "zeit" and fertig[0]["naechte"] >= 3            # das Wochenende zählt mit


def test_stop_beim_broker_wird_aus_der_kontoaktivitaet_gebucht(w, monkeypatch):
    z = _zeit_trade(w)
    te, tx = pd.Timestamp(z.zeit), pd.Timestamp(z.zeit_aus)
    st0, pos = _offener(w, z)
    d, stop = st0["trade"]["richtung"], st0["trade"]["stop"]
    k = Konto(w.std, bid=kurs_um(w, tx))
    wann = tx - 30 * MIN                                                        # Stop eine halbe Stunde vor dem Schluss
    k.acts["D0"] = [{"dateUTC": wann.strftime("%Y-%m-%dT%H:%M:%S.000"), "source": "SL", "type": "POSITION",
                     "status": "ACCEPTED", "details": {"level": stop, "actions": [{"actionType": "POSITION_CLOSED"}]}}]
    monkeypatch.setattr(ab, "signal", lambda *a: _signal(d=d))
    st, log, fertig, _ = ab.run(k, st0, utc(tx + MIN))
    f = fertig[0]
    assert f["grund"] == "stop" and f["exit"] == stop and f["r_roh"] == -1.0 and f["r"] <= -1.0
    assert f["closed_utc"] == wann.isoformat(timespec="seconds")
    # Der Trade war vor dem Schluss der Kerze zu: Wie im Test darf das neue Signal handeln.
    assert len(k.posts()) == 1 and st["trade"]["richtung"] == d and st["trade"]["dealId"] != "D0"


def test_schlusskurs_nicht_lesbar_wartet_eine_stunde_dann_zaehlt_der_stop(w):
    z = _zeit_trade(w)
    te = pd.Timestamp(z.zeit)
    st0, _ = _offener(w, z)
    k = Konto(w.std, bid=kurs_um(w, te))
    st, log, fertig, _ = ab.run(k, st0, utc(te + 31 * MIN))
    assert not fertig and st["trade"]["weg_seit"] and log[0]["event"].startswith("Position beim Broker zu")
    assert "liest den Schlusskurs" in ab.status(st)
    st, log, fertig, _ = ab.run(k, st, utc(te + 46 * MIN))
    assert not fertig and not log
    st, log, fertig, _ = ab.run(k, st, utc(te + 91 * MIN))
    assert fertig[0]["grund"] == "stop" and fertig[0]["exit_geschaetzt"] and fertig[0]["exit"] == st0["trade"]["stop"]


def test_schliessen_scheitert_dann_versucht_es_der_naechste_lauf(w):
    z = _zeit_trade(w)
    tx = pd.Timestamp(z.zeit_aus)
    st0, pos = _offener(w, z)
    k = Konto(w.std, bid=kurs_um(w, tx))
    k.pos["D0"] = pos
    echt = k.close_position
    k.close_position = lambda deal_id: (_ for _ in ()).throw(RuntimeError("Netz weg"))
    st, log, fertig, _ = ab.run(k, st0, utc(tx + MIN))
    assert not fertig and st["trade"]["schliessen_versucht"] == "zeit" and log[-1]["event"] == "schließen fehlgeschlagen"
    k.close_position = echt
    st, log, fertig, _ = ab.run(k, st, utc(tx + 16 * MIN))
    assert fertig[0]["grund"] == "zeit" and st["trade"] is None


def test_haltezeit_des_tests_schliesst_spaetestens(w):
    z = _zeit_trade(w)
    te = pd.Timestamp(z.zeit)
    st0, pos = _offener(w, z)
    k = Konto(w.std.iloc[:0], bid=4000.0)                                       # der Broker liefert keine Kerzen
    k.pos["D0"] = pos
    st, _, fertig, _ = ab.run(k, st0, utc(te + pd.Timedelta(days=13, hours=23)))
    assert not fertig
    st, _, fertig, _ = ab.run(k, st, utc(te + pd.Timedelta(days=14, minutes=2)))
    assert fertig[0]["grund"] == "haltezeit"


def test_order_ohne_bestaetigung_wird_als_eigene_position_gefunden(w, monkeypatch):
    t_g = w.lang[0]
    monkeypatch.setattr(ab, "signal", lambda *a: _signal())
    k = Konto(w.std, bid=kurs_um(w, t_g))
    k.order_fehler = True                                                       # Order kommt an, die Antwort nicht
    st, log, _, _ = ab.run(k, {}, utc(t_g + MIN))
    assert st["trade"]["dealId"] == "D1" and [e["event"] for e in log] == ["Order ohne Bestätigung", "Kauf eröffnet"]
    # auch die Positionen sind gerade nicht lesbar: Der nächste Lauf findet sie an Richtung und Größe
    k = Konto(w.std, bid=kurs_um(w, t_g))
    k.order_fehler = True
    echt, zaehler = k.positions, {"n": 0}

    def positions():
        zaehler["n"] += 1
        if zaehler["n"] == 2:
            raise RuntimeError("Netz weg")
        return echt()

    k.positions = positions
    st, log, _, _ = ab.run(k, {}, utc(t_g + MIN))
    assert st["trade"] is None and st["ungeklaert"]["size"] == 0.09 and "Bestätigung fehlt" in ab.status(st)
    st, log, _, _ = ab.run(k, st, utc(t_g + 16 * MIN))
    assert st["trade"]["dealId"] == "D1" and st["ungeklaert"] is None and len(k.posts()) == 1
    assert st["trade"]["opened_utc"] == (t_g + MIN).isoformat(timespec="seconds") and not st.get("fremd")
    # kam die Order gar nicht an, vergisst der Bot sie
    st, log, _, _ = ab.run(Konto(w.std), {"ungeklaert": {"grenze": str(t_g), "richtung": 1, "size": 0.09, "dist": 60.0,
                                                         "seit": "2026-01-01T00:00:00", "vorher": []},
                                         "letzte_grenze": str(t_g)}, utc(t_g + 16 * MIN))
    assert st["trade"] is None and st["ungeklaert"] is None and "liegt nicht beim Broker" in log[0]["event"]


def test_abgelehnte_order_wird_nicht_wiederholt(w, monkeypatch):
    t_g = w.lang[0]
    monkeypatch.setattr(ab, "signal", lambda *a: _signal())
    k = Konto(w.std, bid=kurs_um(w, t_g))
    k.confirm = lambda ref: {"dealStatus": "REJECTED", "reason": "RISK_CHECK"}
    echt = k._request

    def ohne_position(method, path, json=None):
        antwort = echt(method, path, json)
        k.pos.clear()
        return antwort

    k._request = ohne_position
    st, log, _, _ = ab.run(k, {}, utc(t_g + MIN))
    assert st["trade"] is None and log[-1]["event"] == "Order abgelehnt" and log[-1]["grund"] == "RISK_CHECK"
    st, _, _, _ = ab.run(k, st, utc(t_g + 16 * MIN))
    assert len(k.posts()) == 1


def test_pause_ab_minus_25_r(w):
    z = _zeit_trade(w)
    tx = pd.Timestamp(z.zeit_aus)
    st0, pos = _offener(w, z)
    st0.update(summe_r=-24.5, trades=60)
    k = Konto(w.std, bid=kurs_um(w, tx))
    k.acts["D0"] = [{"dateUTC": (tx - 30 * MIN).strftime("%Y-%m-%dT%H:%M:%S"), "source": "SL", "type": "POSITION",
                     "status": "ACCEPTED", "details": {"level": st0["trade"]["stop"], "actions": []}}]
    st, log, fertig, _ = ab.run(k, st0, utc(tx - 14 * MIN))
    assert fertig[0]["r"] <= -1.0 and st["summe_r"] <= -25.5 and st["pausiert"] and "Pause" in ab.status(st)


def test_trockenlauf_aendert_nichts(w):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, _, _ = ab.run(k, {}, utc(t_g + MIN), send_orders=False)
    assert not [c for c in k.calls if c[0] in ("POST", "DELETE")] and log[-1]["event"] == "würde kaufen"
    assert st["trade"] is None and st.get("letzte_grenze") is None


def test_schreibt_nur_eigene_dateien_und_nur_wenn_sich_etwas_aendert(tmp_path):
    st = {"trade": None, "stand": "2026-01-01T00:00:00", "start": "2026-01-01T00:00:00", "summe_r": 0.0, "trades": 0}
    ziel = (tmp_path / "ga", tmp_path / "gold-ausbruch4h.json")
    assert ab.schreiben(st, [{"event": "e"}], [{"r": 1.0, "pnl_eur": 4.0}], {"kurs": 4000.0}, *ziel) is True
    assert sorted(p.name for p in ziel[0].iterdir()) == ["log.jsonl", "state.json", "trades.jsonl"]
    c = json.loads(ziel[1].read_text(encoding="utf-8"))
    assert c["bot"] == "gold-ausbruch4h" and c["zusammenfassung"]["trades"] == 1 and c["konto"].startswith("Account 4 …")
    assert c["status"].startswith("kein Trade offen") and c["vorab"] == "suche/VORAB_gold_ausbruch4h_bot.yaml"
    assert ab.KONTO not in json.dumps(c)                                        # nur die letzten 4 Stellen
    assert ab.schreiben({**st, "stand": "2026-01-01T00:15:00"}, [], [], {}, *ziel) is False
    assert ab.schreiben({**st, "letzte_grenze": "x"}, [], [], {}, *ziel) is True
    with pytest.raises(RuntimeError):
        ab.schreiben({}, [], [], {}, tmp_path / "x", tmp_path / "gold-state.json")
    assert ab.JDIR.name == "gold-ausbruch4h" and ab.COCKPIT.name not in ab.GOLD_BOT_DATEIEN


def test_urteil_nach_40():
    gut = [{"r": 0.5}] * 30 + [{"r": -1.0}] * 10
    assert ab.bewertung(gut)["urteil"].startswith("bestanden") and ab.bewertung(gut)["pf_r"] == 1.5
    assert ab.bewertung([{"r": 0.2}] * 30 + [{"r": -1.0}] * 10)["urteil"].startswith("durchgefallen")
    assert ab.bewertung([{"r": -1.0}] * 12 + [{"r": 0.5}] * 3)["urteil"].startswith("Zwischencheck")
    assert ab.bewertung([])["urteil"] == "läuft (0 von 40 Trades)"


# --------------------------------------------------------------------------------------------------------------------
# Regeldatei, Ablauf und Listen

def test_regeln_sind_versiegelt_und_nennen_keine_kontonummer(monkeypatch):
    monkeypatch.undo()                                                          # hier zählt das echte Siegel
    vorab = ab.VORAB.read_text(encoding="utf-8")
    assert ab.vorab_ok(), "Prüfsumme von suche/VORAB_gold_ausbruch4h_bot.yaml fehlt im Protokoll oder passt nicht"
    assert ab.KONTO not in vorab and "Account 4" in vorab
    for wort in (ab.VARIANTE, "-25 R", "NICHT bestanden", "2,93", "nach_trades: 40"):
        assert wort in vorab, wort
    import yaml
    r = yaml.safe_load(vorab)["gold_ausbruch4h_bot"]
    assert r["groesse"]["risiko_eur"] == ab.RISIKO_EUR and r["groesse"]["max_unzen"] == ab.MAX_OZ
    assert r["groesse"]["margin_anteil"] == ab.MARGE_ANTEIL
    assert r["ausfuehrung"]["frist_min"] == ab.FRIST.total_seconds() / 60
    assert r["ausfuehrung"]["vorlauf_tage"] == ab.TAGE_KERZEN and r["ausfuehrung"]["min_handelstage"] == 150
    assert r["urteil"]["nach_trades"] == ab.URTEIL_NACH and r["urteil"]["pause_r"] == ab.PAUSE_R


def test_ablauf_und_listen():
    wf = (ROOT / ".github" / "workflows" / "demo-bots.yml").read_text(encoding="utf-8")
    assert "tests/test_ausbruch4h_bot.py" in wf and "python -m gold.ausbruch4h_bot" in wf
    assert "touch .tests-ok/gold_ausbruch4h" in wf and '[ "$n" -ge 9 ]' in wf and "von 9 Testgruppen" in wf
    from suche import mitnutzer as mn
    eintrag = {b["bot"]: b for b in mn.bots()}[ab.BOT_ID]
    assert eintrag == {"bot": ab.BOT_ID, "konto": ab.KONTO, "konto_name": "Account 4", "neu": True,
                       "quelle": "gold/ausbruch4h_bot.py"}
    from gold.bot import konten
    echt = konten.load(ROOT / "journal")
    assert ab.BOT_ID not in (echt.get("zuordnung") or {})                       # Mitnutzer, nie in der Zuordnung
    assert not ab.KONTO.endswith(konten.HAUPT_ENDUNG)
