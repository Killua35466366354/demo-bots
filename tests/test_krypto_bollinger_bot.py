"""Tests für suche/krypto_bollinger_bot.py: Der Bot sieht mit Stundenkerzen dieselben Einstiege, Stops, Ziele und
Ausstiege wie der Test der Runde "Kirons Notizen" (Fassung bollinger_umkehr_krypto_weit) mit 5-Minuten-Kerzen. Er
handelt nur auf Account 3, höchstens einen Trade je Markt, mit Stop und Ziel beim Broker, und steigt spätestens nach
24 Stunden aus. Alle Kurse und Kontonummern hier sind erfunden."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from suche import krypto_bollinger_bot as kb
from suche import krypto_bollinger_gegenprobe as gp
from suche import notizen_runde as nr
from suche import rueckblick as rb
from suche import youtube_runde2 as y2
from suche.demo_bots import Quote

ROOT = Path(__file__).resolve().parents[1]
HAUPT = "111111113150"
KONTO3 = "111111113333"
MIN = pd.Timedelta(minutes=1)
SYM, EPIC = "BTCUSD", "BTCUSD"
SPREAD = 30.0
EURUSD = 1.1
VON, BIS = "2025-07-10", "2025-07-31"


def erfundene_kurse(von="2025-06-01", bis="2025-08-05", seed=5, start=60000.0) -> pd.DataFrame:
    """5-Minuten-Kerzen rund um die Uhr wie bei Krypto. Ruhige und wilde Stunden wechseln sich ab, so gibt es Schlüsse
    über und unter den Bändern in beide Richtungen."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(von, bis, freq="5min", inclusive="left")
    n = len(idx)
    vol = np.where((np.arange(n) // 288) % 3 == 0, 0.0022, 0.0010)
    c = start * np.exp(np.cumsum(rng.normal(0.0, vol, n)))
    o = np.r_[start, c[:-1]]
    h = np.maximum(o, c) * (1 + rng.uniform(0, 0.0005, n))
    lo = np.minimum(o, c) * (1 - rng.uniform(0, 0.0005, n))
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx).round(1)


def schreibe_npz(df: pd.DataFrame, ordner: Path) -> None:
    """Kursdatei im Format von suche/youtube_runde.baue_krypto."""
    ny = df.index.tz_localize("UTC").tz_convert(rb.NY).tz_localize(None)
    tag = (ny + pd.Timedelta(hours=7)).normalize()
    np.savez(ordner / f"{SYM}.npz", t=df.index.values.astype("datetime64[ns]"), o=df["open"].to_numpy(float),
             h=df["high"].to_numpy(float), l=df["low"].to_numpy(float), c=df["close"].to_numpy(float),
             sp=np.full(len(df), SPREAD), nymin=np.asarray(ny.hour * 60 + ny.minute, dtype=np.int32),
             tag=tag.values.astype("datetime64[D]"), prof=np.full(96, 0.0005))


@pytest.fixture(autouse=True)
def _welt(monkeypatch):
    from gold.bot import konten
    monkeypatch.setattr(kb, "vorab_ok", lambda: True)
    monkeypatch.setattr(kb, "KONTO", KONTO3)
    monkeypatch.setattr(konten, "load", lambda *a: {})


@pytest.fixture(scope="module")
def w(tmp_path_factory):
    """Die erfundene Welt: 5-Minuten-Kerzen, der Markt des Tests, die Stundenkerzen des Brokers und alles, was der Test
    im Fenster handeln dürfte."""
    ordner = tmp_path_factory.mktemp("krypto")
    df = erfundene_kurse()
    schreibe_npz(df, ordner)
    cfg = kb.lade_cfg(pruefen=True)
    m = nr.Markt(SYM, ordner, cfg)
    sig = [s for s in nr.signale(kb.FASSUNG, m, cfg, kb.KEINE_TERMINE)
           if pd.Timestamp(VON) <= pd.Timestamp(m.t[s["i0"]]) < pd.Timestamp(BIS) + pd.Timedelta(days=1)]
    test = {kb.naechste_grenze(pd.Timestamp(m.t[s["i0"] - 1])): s for s in sig}
    return SimpleNamespace(ordner=ordner, df=df, cfg=cfg, m=m, sig=sig, test=test, std=gp.stunden_aus(m),
                           lang=sorted(t for t, s in test.items() if s["d"] > 0),
                           kurz=sorted(t for t, s in test.items() if s["d"] < 0))


def kurs_um(w, t) -> float:
    return float(w.df["open"].loc[pd.Timestamp(t)])


def utc(t):
    return pd.Timestamp(t).tz_localize("UTC").to_pydatetime()


def sig_bei(w, t_g, **kw):
    fenster = w.std[(w.std.index < t_g) & (w.std.index >= kb.vorlauf_ab(t_g))]
    return kb.signal(SYM, kw.get("stunden", fenster), t_g, kw.get("bid", kurs_um(w, t_g)), w.cfg)


# --------------------------------------------------------------------------------------------------------------------
# Bot und Test sehen dasselbe

def test_bot_sieht_dieselben_einstiege_stops_ziele_und_ausstiege_wie_der_test(w):
    res = gp.gegenprobe(SYM, w.ordner, w.cfg, VON, BIS)
    assert res["test_einstiege"] == len(w.test) >= 15 and w.lang and w.kurz
    assert res["bot_einstiege"] == res["beide"] == res["richtung_gleich"] == len(w.test)
    assert res["nur_bot"] == {} and res["nur_test"] == {} and res["verpasst_markt_zu"] == []
    assert res["stop_abweichung_rel"]["groesste"] < 1e-6 and res["ziel_abweichung_rel"]["groesste"] < 1e-6
    assert res["trades_ausstieg_nach_zeit"] >= 1 and res["trades_ausstieg_gleich"] == res["trades_ausstieg_nach_zeit"]
    assert res["bot_wartet"] == 0                      # genug Tage Vorlauf, und an jeder Grenze ist die Stunde davor da


def test_fassung_kommt_aus_der_versiegelten_runde(w):
    spec = w.cfg["varianten"][kb.FASSUNG]
    assert list(w.cfg["varianten"]) == [kb.FASSUNG] and spec["basis"] == kb.GRUNDREGEL == "bollinger_rsi"
    assert (spec["umkehr"], spec["stop_faktor"], spec["ziel_r_umkehr"], spec["quelle"]) == ("weit", 1.5, 2.0,
                                                                                            "youtube_runde2")
    assert kb.MAERKTE == {"BTCUSD": "BTCUSD", "ETHUSD": "ETHUSD"}
    p = kb.regel(w.cfg)
    assert (p["bb_n"], p["bb_breite"], p["rsi_n"], p["rsi_unten"], p["rsi_oben"], p["atr_n"], p["stop_atr"],
            p["halte_stunden"], p["frist_min"]) == (20, 2.0, 14, 30, 70, 14, 1.0, 24, 15)
    assert w.cfg["quell_regeln"]["youtube_runde2"]["bollinger_rsi"] == p
    assert set(kb.MAERKTE) <= set(w.cfg["daten"]["krypto_alle_tage"])


def test_umgedreht_mit_weitem_stop_und_ziel_zwei_r(w):
    """Jedes Signal der Fassung ist ein Signal der Grundregel in Gegenrichtung, Stop 1,5-fach, Ziel 2 R."""
    q = nr.regel_cfg(w.cfg, w.cfg["varianten"][kb.FASSUNG])
    grund = {s["i0"]: s for s in y2.regel_bollinger(w.m, q)}
    for s in w.sig:
        g = grund[s["i0"]]
        assert s["d"] == -g["d"] and s["sd"] == pytest.approx(1.5 * g["sd"]) and s["zd"] == pytest.approx(2 * s["sd"])
        assert s["t_max"] == w.m.t[s["i0"]] + np.timedelta64(24, "h")


@pytest.mark.parametrize("jetzt, beginn, naechste", [
    ("2026-01-07 12:10", "2026-01-07 12:00", "2026-01-07 13:00"),
    ("2026-07-01 23:59", "2026-07-01 23:00", "2026-07-02 00:00"),
    ("2026-11-01 05:00", "2026-11-01 05:00", "2026-11-01 06:00"),      # Uhr in New York zurück: UTC zählt
])
def test_grenzen_zur_vollen_utc_stunde(jetzt, beginn, naechste):
    assert kb.grenze(pd.Timestamp(jetzt)) == pd.Timestamp(beginn)
    assert kb.naechste_grenze(pd.Timestamp(jetzt)) == pd.Timestamp(naechste)


def test_handelstag_wie_in_den_kursdateien(w):
    i = np.arange(0, w.m.n, 997)
    tage = (w.m.tage[w.m.tix[i]] - np.datetime64("1970-01-01")).astype(int)
    assert [kb.handelstag(pd.Timestamp(t)) for t in w.m.t[i]] == list(tage)
    assert kb.handelstag("2026-01-09 21:59") + 1 == kb.handelstag("2026-01-09 22:00")      # 17:00 New York im Winter
    assert kb.tagesende(pd.Timestamp("2026-07-01 22:00")) == pd.Timestamp("2026-07-02 21:00")


def test_krypto_hat_sieben_handelstage(w):
    assert w.m.klasse == "krypto"
    wochentage = set(pd.DatetimeIndex(w.m.tage[w.m.gi]).weekday)
    assert wochentage == set(range(7))


def test_signal_haengt_nicht_an_der_zukunft(w):
    t_g = w.lang[0]
    a = sig_bei(w, t_g)
    b = sig_bei(w, t_g, stunden=w.std)                         # mit allen späteren Stundenkerzen
    s = w.test[t_g]
    assert a["ok"] and (a["richtung"], a["dist"], a["ziel_abstand"]) == (b["richtung"], b["dist"], b["ziel_abstand"])
    assert a["dist"] == pytest.approx(s["sd"]) and a["richtung"] == 1
    assert a["schluss"] > a["oben"] and a["rsi"] > 70          # Kauf über dem oberen Band: umgedreht


def test_verkauf_unter_dem_unteren_band(w):
    a = sig_bei(w, w.kurz[0])
    assert a["ok"] and a["richtung"] == -1 and a["schluss"] < a["unten"] and a["rsi"] < 30


def test_signal_wartet_wenn_die_letzte_stunde_fehlt_oder_zu_wenig_tage_da_sind(w, monkeypatch):
    t_g = w.lang[0]
    s = sig_bei(w, t_g, stunden=w.std[w.std.index < t_g - kb.STUNDE])
    assert s["warten"] and not s["ok"] and "Stundenkerze" in s["ergebnis"]
    monkeypatch.setattr(kb, "MIN_TAGE", 500)
    s = sig_bei(w, t_g)
    assert s["warten"] and not s["ok"] and "zu wenig Kerzen" in s["ergebnis"]


def test_ohne_extrem_kein_einstieg(w):
    ruhig = None
    for t_g in pd.date_range("2025-07-11 03:00", "2025-07-30 03:00", freq="h"):
        if t_g in w.test:
            continue
        s = sig_bei(w, t_g)
        if s["richtung"] == 0:
            ruhig = s
            break
    assert ruhig and not ruhig["ok"] and "im Band" in ruhig["ergebnis"]


def _q(**kw):
    base = dict(bid=60000.0, offer=60030.0, tradeable=True, currency="USD", lot=1.0, min_size=0.0001,
                size_step=0.0001, margin_pct=50.0, decimals=1, min_dist=1.0, eur_rate=EURUSD)
    base.update(kw)
    return Quote(**base)


def test_groesse():
    assert kb.groesse(550.0, _q()) == (0.01, "")               # 5 € = 5,50 $ / 550 $ = 0,01 Bitcoin
    size, warum = kb.groesse(550.0, _q(min_size=0.1, size_step=0.1))
    assert size is None and "zu grob" in warum
    assert kb.groesse(550.0, _q(eur_rate=None))[0] is None


def test_konto_kommt_nach_dem_namen_aus_konten_json():
    daten = {"konten": [{"id": "111111110001", "name": "Account 6"}, {"id": KONTO3, "name": "Account 3"}]}
    assert kb.konto_id(daten) == KONTO3
    assert kb.konto_id({"konten": daten["konten"] + [{"id": "111111110002", "name": "Account 3"}]}) == ""
    assert kb.konto_id({}) == ""


def test_echtes_konto_steht_in_konten_json_und_ist_nie_das_hauptkonto():
    from gold.bot import konten
    echt = konten.DATEI and (ROOT / "journal" / konten.DATEI)
    k = kb.konto_id(json.loads(echt.read_text(encoding="utf-8")))
    assert k and not k.endswith(kb.HAUPT_ENDUNG)


# --------------------------------------------------------------------------------------------------------------------
# Der Lauf auf dem Demokonto

class Antwort:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class Konto:
    """Capital.com zum Testen: Hauptkonto und Account 3, Positionen auf Account 3, Stundenkerzen aus der erfundenen
    Welt für BTCUSD. Für ETHUSD liefert der Broker keine Kerzen."""

    def __init__(self, std, bid=60000.0, konto3=True, frei=900.0):
        self.account_id = HAUPT
        self.std = std
        self.bid, self.offer = bid, bid + SPREAD
        self.konto3, self.frei, self.markt_auf = konto3, frei, True
        self.pos: dict[str, dict] = {}
        self.fremd: list[dict] = []
        self.acts: dict[str, list] = {}
        self.calls: list = []
        self.abrufe: list = []
        self.refs: dict = {}
        self.nr = 0
        self.order_fehler = False

    def accounts(self):
        out = [{"accountId": HAUPT, "balance": {"balance": 990.0, "available": 900.0}}]
        if self.konto3:
            out.append({"accountId": KONTO3, "balance": {"balance": 1000.0, "available": self.frei}})
        return out

    def switch_account(self, aid):
        self.calls.append(("konto", aid))
        self.account_id = aid

    def market(self, epic):
        if epic in kb.MAERKTE.values():
            return {"snapshot": {"bid": self.bid, "offer": self.offer, "decimalPlacesFactor": 1,
                                 "marketStatus": "TRADEABLE" if self.markt_auf else "CLOSED"},
                    "instrument": {"currency": "USD", "lotSize": 1, "marginFactor": 50, "marginFactorUnit": "PERCENTAGE"},
                    "dealingRules": {"minDealSize": {"value": 0.0001}, "minSizeIncrement": {"value": 0.0001},
                                     "minStopOrProfitDistance": {"unit": "POINTS", "value": 1.0}}}
        assert epic == "EURUSD"
        return {"snapshot": {"bid": EURUSD, "offer": EURUSD}}

    def positions(self):
        assert self.account_id == KONTO3, "der Bot darf nur auf Account 3 Positionen lesen"
        return [{"market": {"epic": p["epic"]}, "position": p} for p in self.pos.values()] + self.fremd

    def _get(self, path, **params):
        assert path.startswith("/prices/") and params["resolution"] == "HOUR" and params["max"] == 1000
        von, bis = pd.Timestamp(params["from"]), pd.Timestamp(params["to"])
        assert bis - von <= pd.Timedelta(days=40)
        self.abrufe.append((path, von, bis))
        if path != "/prices/BTCUSD":
            return {"prices": []}
        df = self.std[(self.std.index >= von) & (self.std.index <= bis)]
        return {"prices": [{"snapshotTimeUTC": t.strftime("%Y-%m-%dT%H:%M:%S"),
                            **{f"{n}Price": {"bid": float(x), "ask": float(x) + SPREAD}
                               for n, x in zip(("open", "high", "low", "close"), row)}}
                           for t, row in zip(df.index, df[kb.SPALTEN].to_numpy())]}

    def _request(self, method, path, json=None):
        assert self.account_id == KONTO3
        assert method == "POST" and path == "/positions"
        self.calls.append((method, path, json))
        self.nr += 1
        ref, deal = f"R{self.nr}", f"D{self.nr}"
        d = 1 if json["direction"] == "BUY" else -1
        level = self.offer if d > 0 else self.bid
        self.pos[deal] = {"dealId": deal, "epic": json["epic"], "level": level, "size": json["size"],
                          "direction": json["direction"], "stopLevel": json["stopLevel"], "profitLevel": json["profitLevel"]}
        self.refs[ref] = {"dealStatus": "ACCEPTED", "affectedDeals": [{"dealId": deal}], "level": level}
        if self.order_fehler:
            raise RuntimeError("Zeitüberschreitung")
        return Antwort({"dealReference": ref})

    def confirm(self, ref):
        return self.refs.get(ref, {"dealStatus": "ACCEPTED"})

    def close_position(self, deal_id):
        assert self.account_id == KONTO3
        self.calls.append(("DELETE", deal_id))
        p = self.pos.pop(deal_id)
        return {"dealStatus": "ACCEPTED", "level": self.bid if p.get("direction") == "BUY" else self.offer}

    def activity(self, deal_id, since, until):
        assert until - since <= pd.Timedelta(days=1)
        return self.acts.get(deal_id, [])

    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]


def btc(st):
    return st["maerkte"][SYM]


def test_kauf_wie_im_test_mit_stop_und_ziel_vom_bid(w):
    t_g = w.lang[0]
    s = w.test[t_g]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, fertig, blick = kb.run(k, {}, utc(t_g + MIN))
    tr = btc(st)["trade"]
    stop, ziel = round(k.bid - s["sd"], 1), round(k.bid + s["zd"], 1)
    assert tr["richtung"] == 1 and tr["dist"] == pytest.approx(s["sd"], abs=1e-5) and tr["grenze"] == str(t_g)
    assert tr["entry"] == k.offer and (tr["stop"], tr["ziel"]) == (stop, ziel) and tr["spaet_min"] == 1.0
    assert k.posts() == [("POST", "/positions", {"epic": EPIC, "direction": "BUY", "size": kb.groesse(s["sd"], _q())[0],
                                                  "guaranteedStop": False, "stopLevel": stop, "profitLevel": ziel})]
    assert k.calls[0] == ("konto", KONTO3) and k.account_id == HAUPT              # zurück aufs Hauptkonto
    assert btc(st)["letzte_grenze"] == str(t_g) and [e["event"] for e in log] == ["Kauf eröffnet"]
    assert tr["bis_utc"] == str(t_g + pd.Timedelta(hours=24)) and tr["satz_nacht"] == 0.20
    assert "Stundenkerze" in blick["maerkte"]["ETHUSD"]["wartet"]            # für Ether liefert der Broker hier nichts
    st2, _, _, _ = kb.run(k, st, utc(t_g + 16 * MIN))                        # zweiter Lauf in derselben Stunde
    assert len(k.posts()) == 1 and btc(st2)["trade"]["dealId"] == tr["dealId"]


def test_verkauf_wie_im_test(w):
    t_g = w.kurz[0]
    s = w.test[t_g]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, _, _ = kb.run(k, {}, utc(t_g + MIN))
    tr = btc(st)["trade"]
    assert tr["richtung"] == -1 and tr["entry"] == k.bid
    assert (tr["stop"], tr["ziel"]) == (round(k.bid + s["sd"], 1), round(k.bid - s["zd"], 1))
    assert k.posts()[0][2]["direction"] == "SELL" and tr["satz_nacht"] == 0.20


def test_ausstieg_nach_24_stunden(w):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, _, _, _ = kb.run(k, {}, utc(t_g + MIN))
    deal = btc(st)["trade"]["dealId"]
    st, log, fertig, _ = kb.run(k, st, utc(t_g + pd.Timedelta(hours=23, minutes=46)))
    assert not fertig and btc(st)["trade"]
    st, log, fertig, _ = kb.run(k, st, utc(t_g + pd.Timedelta(hours=24, minutes=1)))
    assert fertig and fertig[0]["grund"] == "zeit" and ("DELETE", deal) in k.calls
    assert btc(st)["trade"] is None and btc(st)["letzter_schluss"] == fertig[0]["closed_utc"]
    assert st["trades"] == 1 and st["summe_r"] == fertig[0]["r"] and fertig[0]["naechte"] == 1
    assert fertig[0]["gebuehr_r"] == pytest.approx(0.20 / 365 * fertig[0]["entry"] / fertig[0]["dist"], abs=1e-3)
    # In derselben Stunde wie der Ausstieg gibt es keinen neuen Einstieg, wie im Test
    assert btc(st)["letzte_pruefung"]["ergebnis"].startswith(("der letzte Trade endete", "Schluss im Band",
                                                              "Signal, aber", "Kauf", "Verkauf"))
    assert len(k.posts()) == 1


def test_stop_und_ziel_beim_broker_werden_gebucht(w):
    t_g = w.lang[0]
    for quelle, grund in (("SL", "stop"), ("TP", "ziel")):
        k = Konto(w.std, bid=kurs_um(w, t_g))
        st, _, _, _ = kb.run(k, {}, utc(t_g + MIN))
        tr = btc(st)["trade"]
        level = tr["stop"] if quelle == "SL" else tr["ziel"]
        k.pos.pop(tr["dealId"])
        k.acts[tr["dealId"]] = [{"dateUTC": (t_g + 30 * MIN).strftime("%Y-%m-%dT%H:%M:%S"), "source": quelle,
                                 "type": "POSITION", "status": "ACCEPTED", "details": {"level": level, "actions": []}}]
        st, log, fertig, _ = kb.run(k, st, utc(t_g + 46 * MIN))
        r = fertig[0]
        assert r["grund"] == grund and r["exit"] == level and r["markt"] == SYM and "exit_geschaetzt" not in r
        assert r["r_roh"] == pytest.approx((level - tr["entry"]) / tr["dist"], abs=1e-3)
        assert r["pnl_eur"] == round(tr["size"] * (level - tr["entry"]) / EURUSD, 2)


def test_schluss_nicht_lesbar_wird_nach_einer_stunde_geschaetzt(w):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, _, _, _ = kb.run(k, {}, utc(t_g + MIN))
    tr = btc(st)["trade"]
    k.pos.pop(tr["dealId"])
    st, log, fertig, _ = kb.run(k, st, utc(t_g + 16 * MIN))
    assert not fertig and log[0]["event"].startswith("Position beim Broker zu") and "Schlusskurs" in kb.status(st)
    k.bid, k.offer = tr["ziel"] + 50, tr["ziel"] + 50 + SPREAD                 # Kurs jetzt über dem Ziel
    st, log, fertig, _ = kb.run(k, st, utc(t_g + 76 * MIN))
    assert fertig[0]["grund"] == "ziel" and fertig[0]["exit"] == tr["ziel"] and fertig[0]["exit_geschaetzt"]


def test_sperren(w, monkeypatch):
    t_g = w.lang[0]
    jetzt = utc(t_g + MIN)
    k = Konto(w.std, bid=kurs_um(w, t_g))
    k.fremd = [{"market": {"epic": EPIC}, "position": {"dealId": "FREMD", "level": 59990.0, "size": 0.01}},
               {"market": {"epic": "GBPJPY"}, "position": {"dealId": "VORTAG", "level": 200.0, "size": 1}}]
    st, log, _, _ = kb.run(k, {}, jetzt)
    assert btc(st)["trade"] is None and not k.posts() and "fremde Position auf BTCUSD im Konto" in log[-1]["gruende"]
    assert btc(st)["fremd"] == ["FREMD"] and not [c for c in k.calls if c[0] == "DELETE"]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    k.fremd = [{"market": {"epic": "GBPJPY"}, "position": {"dealId": "VORTAG", "level": 200.0, "size": 1}}]
    st, _, _, _ = kb.run(k, {}, jetzt)                                       # GBP/JPY des Vortag-Bots stört nicht
    assert len(k.posts()) == 1
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, _, _ = kb.run(k, {"pausiert": {"seit": "x", "grund": "y"}}, jetzt)
    assert not k.posts() and "Pause ab -25 R" in log[-1]["gruende"]
    k = Konto(w.std, bid=kurs_um(w, t_g), frei=100.0)                        # zu wenig freies Geld für die Margin
    st, log, _, _ = kb.run(k, {}, jetzt)
    assert not k.posts() and any("des freien Gelds" in g for g in log[-1]["gruende"]) and log[-1]["margin_eur"] > 40
    monkeypatch.setattr(kb, "vorab_ok", lambda: False)
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, _, _ = kb.run(k, {}, jetzt)
    assert not k.posts() and any("nicht festgelegt" in g for g in log[-1]["gruende"])


def test_nie_auf_dem_hauptkonto_und_nie_ohne_konto(w, monkeypatch):
    k = Konto(w.std, konto3=False)
    st, log, _, blick = kb.run(k, {}, utc(w.lang[0] + MIN))
    assert not [c for c in k.calls if c[0] in ("POST", "konto")] and "nicht gefunden" in blick["status"]
    monkeypatch.setattr(kb, "KONTO", "")
    k = Konto(w.std)
    st, log, _, blick = kb.run(k, {}, utc(w.lang[0] + MIN))
    assert not k.calls and "journal/konten.json" in blick["status"]
    monkeypatch.setattr(kb, "KONTO", "111111113150")                        # endet wie das Hauptkonto
    st, log, _, blick = kb.run(Konto(w.std), {}, utc(w.lang[0] + MIN))
    assert log[0]["event"] == "kein Konto"


def test_frist_markt_zu_und_trockenlauf(w):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, _, _, _ = kb.run(k, {}, utc(t_g + 21 * MIN))                          # frischer Bot, Frist vorbei
    assert not k.posts() and "Start des Bots" in btc(st)["letzte_pruefung"]["ergebnis"]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, _, _, _ = kb.run(k, {}, utc(t_g + 16 * MIN))                          # zweiter Lauf der Stunde, noch in der Frist
    assert len(k.posts()) == 1 and btc(st)["trade"]["spaet_min"] == 16.0
    k = Konto(w.std, bid=kurs_um(w, t_g))
    k.markt_auf = False
    st, _, _, blick = kb.run(k, {}, utc(t_g + MIN))
    assert not k.posts() and blick["maerkte"][SYM]["wartet"] == "Markt zu" and btc(st).get("letzte_grenze") is None
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, _, _ = kb.run(k, {}, utc(t_g + MIN), send_orders=False)
    assert not k.posts() and log[-1]["event"] == "würde kaufen" and btc(st).get("letzte_grenze") is None


def test_order_ohne_bestaetigung_wird_uebernommen(w):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    k.order_fehler = True
    st, log, _, _ = kb.run(k, {}, utc(t_g + MIN))
    assert len(k.posts()) == 1 and btc(st)["trade"]["dealId"] == "D1"        # sofort in den Positionen gefunden
    st2, _, _, _ = kb.run(k, st, utc(t_g + 16 * MIN))
    assert len(k.posts()) == 1


def test_ein_abruf_je_markt_und_stunde(w):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    kb.run(k, {}, utc(t_g + MIN))
    assert len([a for a in k.abrufe if a[0] == "/prices/BTCUSD"]) == 1


def test_schreiben(tmp_path, w):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, fertig, blick = kb.run(k, {}, utc(t_g + MIN))
    j, c = tmp_path / "krypto-bollinger", tmp_path / "krypto-bollinger.json"
    assert kb.schreiben(st, log, fertig, blick, j, c)
    assert not kb.schreiben(st, [], [], blick, j, c)                          # nichts Neues, nichts geschrieben
    karte = json.loads(c.read_text(encoding="utf-8"))
    assert karte["bot"] == "krypto-bollinger" and karte["konto"] == "Account 3" and KONTO3 not in c.read_text()
    assert karte["offen"][0]["epic"] == EPIC and karte["zusammenfassung"]["urteil"].startswith("läuft (0 von 40")
    with pytest.raises(RuntimeError):
        kb.schreiben(st, log, fertig, blick, j, tmp_path / "konten.json")


def test_bewertung():
    tr = [{"r": 1.0, "markt": "BTCUSD", "pnl_eur": 5}] * 25 + [{"r": -1.0, "markt": "ETHUSD", "pnl_eur": -5}] * 15
    b = kb.bewertung(tr)
    assert b["trades"] == 40 and b["pf_r"] == pytest.approx(25 / 15, abs=1e-3) and b["urteil"].startswith("bestanden")
    assert b["je_markt"]["ETHUSD"] == {"trades": 15, "summe_r": -15.0}
    assert kb.bewertung([{"r": -1.0}] * 15)["urteil"].startswith("Zwischencheck")


def test_mitnutzer_kennt_den_bot():
    from suche import mitnutzer
    b = {x["bot"]: x for x in mitnutzer.bots()}["krypto-bollinger"]
    assert b["konto_name"] == "Account 3" and b["neu"] and b["konto"] == KONTO3


def test_regeln_sind_versiegelt(monkeypatch):
    monkeypatch.undo()
    assert kb.vorab_ok(), "suche/VORAB_krypto_bollinger_bot.yaml braucht seine Prüfsumme im Protokoll"
    vorab = kb.VORAB.read_text(encoding="utf-8")
    assert kb.KONTO not in vorab and "Account 3" in vorab
    for wort in (kb.FASSUNG, "-25 R", "NICHT bestanden", "1,07", "nach_trades: 40", "11:53 UTC", "VORAB_schatten"):
        assert wort in vorab, wort
    import yaml
    r = yaml.safe_load(vorab)["krypto_bollinger_bot"]
    assert r["bot"] == kb.BOT_ID
    assert r["groesse"]["risiko_eur"] == kb.RISIKO_EUR and r["groesse"]["margin_anteil"] == kb.MARGE_ANTEIL
    assert r["groesse"]["max_risiko_faktor"] == kb.MAX_RISIKO_FAKTOR
    assert r["ausfuehrung"]["frist_min"] == kb.FRIST.total_seconds() / 60
    assert r["ausfuehrung"]["vorlauf_tage"] == kb.TAGE_KERZEN and r["ausfuehrung"]["min_handelstage"] == kb.MIN_TAGE
    assert r["urteil"]["nach_trades"] == kb.URTEIL_NACH and r["urteil"]["pause_r"] == kb.PAUSE_R
    z = r["gegenprobe_zahlen"]
    assert set(z) == set(kb.MAERKTE) and all(z[m]["nur_bot"] == 0 and z[m]["richtung_gleich"] == z[m]["gemeinsam"]
                                             for m in z)


def test_ablauf_im_workflow():
    wf = (ROOT / ".github" / "workflows" / "demo-bots.yml").read_text(encoding="utf-8")
    assert "python -m pytest -q tests/test_krypto_bollinger_bot.py" in wf and "python -m suche.krypto_bollinger_bot" in wf
    assert "touch .tests-ok/krypto_bollinger" in wf and "python -m suche.krypto_bollinger_bot --dry-run" in wf
