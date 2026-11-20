"""Tests für suche/williams_bot.py: Der Bot sieht mit Stunden- und 5-Minuten-Kerzen vom Broker dieselben Einstiege,
Stops und Ausstiege wie der Test der YouTube-Runde (Fassung williams_us) mit den 5-Minuten-Kerzen von HistData. Er kauft
nur um 16:00 New York, nur auf Account 7, höchstens einen Trade je Markt, mit Stop beim Broker und ohne Ziel, und
steigt um 16:00 New York nach der Regel aus. Alle Kurse und Kontonummern hier sind erfunden."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from suche import modell_indizes_gegenprobe as mg
from suche import rueckblick as rb
from suche import williams_bot as wb
from suche import williams_gegenprobe as gp
from suche import youtube_runde as yr
from suche.demo_bots import Quote

ROOT = Path(__file__).resolve().parents[1]
HAUPT = "111111113150"
KONTO7 = "111111117070"
MIN = pd.Timedelta(minutes=1)
SYM, EPIC = "SPXUSD", "US500"
SPREAD = 0.6
EURUSD = 1.1
VON, BIS = "2025-11-03", "2026-03-13"


def erfundene_kurse(von="2025-09-01", bis="2026-03-21", seed=5, start=5000.0) -> pd.DataFrame:
    """5-Minuten-Kerzen eines Index wie bei HistData: von Sonntag 18:00 bis Freitag 17:00 New York, jeden Tag eine
    Pause von 17:00 bis 18:00 New York."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(von, bis, freq="5min", inclusive="left")
    ny = idx.tz_localize("UTC").tz_convert(rb.NY).tz_localize(None)
    tag = (ny + pd.Timedelta(hours=7)).normalize()
    idx = idx[(ny.hour != 17) & (tag.weekday < 5)]
    n = len(idx)
    c = start * np.exp(np.cumsum(rng.normal(0.00001, 0.0007, n)))
    o = np.r_[start, c[:-1]]
    h = np.maximum(o, c) * (1 + rng.uniform(0, 0.0002, n))
    lo = np.minimum(o, c) * (1 - rng.uniform(0, 0.0002, n))
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx).round(2)


def schreibe_npz(df: pd.DataFrame, ordner: Path, sym: str = SYM) -> None:
    ny = df.index.tz_localize("UTC").tz_convert(rb.NY).tz_localize(None)
    tag = (ny + pd.Timedelta(hours=7)).normalize()
    np.savez(ordner / f"{sym}.npz", t=df.index.values.astype("datetime64[ns]"), o=df["open"].to_numpy(float),
             h=df["high"].to_numpy(float), l=df["low"].to_numpy(float), c=df["close"].to_numpy(float),
             sp=np.full(len(df), SPREAD), nymin=np.asarray(ny.hour * 60 + ny.minute, dtype=np.int32),
             tag=tag.values.astype("datetime64[D]"))


@pytest.fixture(autouse=True)
def _welt(monkeypatch):
    monkeypatch.setattr(wb, "vorab_ok", lambda: True)
    monkeypatch.setattr(wb, "KONTO", KONTO7)


@pytest.fixture(scope="module")
def w(tmp_path_factory):
    """Die erfundene Welt: Kurse, der Markt des Tests und alle Trades des Tests im Fenster."""
    ordner = tmp_path_factory.mktemp("kurse")
    df = erfundene_kurse()
    schreibe_npz(df, ordner)
    cfg = wb.lade_cfg(pruefen=True)
    p = wb.regel(cfg)
    m = yr.Markt(SYM, ordner, cfg, cfg["fenster"]["bis"])
    alle = rb.echte_trades(m, yr.regel_williams(m, cfg), cfg)
    trades = []
    for r in alle.itertuples():
        if not np.datetime64(VON) <= m.t[r.i0] <= np.datetime64(BIS) + np.timedelta64(1, "D"):
            continue
        ex = int(np.searchsorted(m.t, np.datetime64(pd.Timestamp(r.aus_utc), "ns")))
        trades.append({"tag": str(r.tag)[:10], "i0": int(r.i0), "sd": float(r.stop_abstand), "ex": ex,
                       "t_e": pd.Timestamp(m.t[r.i0]), "t_aus": pd.Timestamp(m.t[ex]), "um_16": int(m.nymin[ex]) == 960})
    return SimpleNamespace(ordner=ordner, df=df, cfg=cfg, p=p, m=m, test=trades, std=mg.stunden_aus(m),
                           s=wb.sitzungen(m, p))


def utc(t):
    return pd.Timestamp(t).tz_localize("UTC").to_pydatetime()


def kurs_um(w, t) -> float:
    return float(w.df["open"].loc[pd.Timestamp(t)])


def fuenf_vor(w, t_s) -> pd.DataFrame:
    return w.df[w.df.index < t_s].iloc[-wb.FUENF_MAX:]


def sig_am(w, tag, **kw) -> dict:
    t_s = wb.schluss(pd.Timestamp(tag), w.p)
    return wb.signal(SYM, w.std[w.std.index < t_s], fuenf_vor(w, t_s), t_s, kurs_um(w, t_s), w.cfg, **kw)


def sitzungstage(w, nach, bis) -> list[str]:
    """Die vollen Sitzungen des Tests nach dem Tag `nach` bis zum Tag `bis`."""
    return [str(d)[:10] for d in w.s["datum"] if np.datetime64(nach) < d <= np.datetime64(bis)]


# --------------------------------------------------------------------------------------------------------------------
# Bot und Test sehen dasselbe

def test_die_erfundene_welt_hat_trades_mit_ausstieg_nach_der_regel(w):
    assert len(w.test) >= 4 and any(t["um_16"] for t in w.test)
    assert all(int(w.m.nymin[t["i0"]]) == 960 for t in w.test)                   # Einstieg zur Kerze um 16:00


def test_bot_sieht_dieselben_einstiege_stops_und_ausstiege_wie_der_test(w):
    res = gp.gegenprobe(SYM, w.ordner, w.cfg, VON, BIS)
    assert res["test_trades"] == res["bot_trades"] == res["beide"] == len(w.test)
    assert res["nur_bot"] == [] and res["nur_test"] == [] and res["bot_wartet"] == {}
    assert res["ausstieg_gleich"] == res["beide"] and res["ausstieg_anders"] == {}
    assert res["stop_abweichung_rel"]["groesste"] < 1e-6


def test_fassung_kommt_aus_der_versiegelten_runde(w):
    p = w.p
    assert p is w.cfg["regeln"]["williams"] and w.cfg["varianten"][wb.FASSUNG]["regel"] == "williams"
    assert (p["tage"], p["kauf_unter"], p["raus_ueber"], p["max_tage"], p["stop_atr"]) == (2, -90, -30, 10, 3.0)
    assert (p["sitzung_von_min"], p["sitzung_bis_min"], p["min_kerzen_sitzung"], p["toleranz_min"]) == (570, 960, 70, 30)
    assert wb.MAERKTE == {"SPXUSD": "US500", "NSXUSD": "US100"}
    assert w.cfg["kosten"]["nacht_pro_jahr"]["index"]["long"] == 0.065


def test_sitzungen_wie_der_test(w):
    """Dieselben Sitzungen und dasselbe %R wie suche/youtube_runde.regel_williams: Aus den Werten von
    williams_bot.sitzungen folgen genau die Einstiege und spätesten Ausstiege des Tests."""
    s, m, p = w.s, w.m, w.p
    test = yr.regel_williams(m, w.cfg)
    eigene = []
    for q in range(p["tage"], len(s["C"]) - 1):
        if not s["wr"][q] < p["kauf_unter"] or s["i_s"][q] < 0:
            continue
        i0 = int(s["i_s"][q])
        g = m.gpos[m.tix[i0]]
        if g < 1 or not np.isfinite(m.atr_vor[g]):
            continue
        aus = next((e for e in range(q + 1, min(q + 1 + p["max_tage"], len(s["C"]))) if s["i_s"][e] >= 0
                    and (s["raus"][e] or e == q + p["max_tage"])), None)
        eigene.append((i0, None if aus is None else m.t[s["i_s"][aus]]))
    assert [(x["i0"], x["t_max"]) for x in test] == eigene[:len(test)] and len(eigene) - len(test) <= 1


def test_signal_kauft_wie_der_test(w):
    for t in w.test:
        s = sig_am(w, t["tag"])
        assert s["kauf"] and not s["warten"] and s["wr"] < -90 and s["dist"] == pytest.approx(t["sd"], abs=1e-5), t
        assert s["tage"] >= wb.MIN_TAGE and "Kauf (unter -90)" in s["ergebnis"]


def test_signal_haengt_nicht_an_der_zukunft(w):
    tag = w.test[0]["tag"]
    t_s = wb.schluss(pd.Timestamp(tag), w.p)
    a = sig_am(w, tag)
    spaeter = w.df[w.df.index >= fuenf_vor(w, t_s).index[0]]                     # dazu alle Kerzen ab 16:00
    b = wb.signal(SYM, w.std, spaeter, t_s, kurs_um(w, t_s), w.cfg)
    assert a == b and a["kauf"]


def test_signal_wartet_ohne_kerzen_und_ausserhalb_von_16_uhr(w):
    tag = w.test[0]["tag"]
    t_s = wb.schluss(pd.Timestamp(tag), w.p)
    bid = kurs_um(w, t_s)
    kurz = w.std[(w.std.index < t_s) & (w.std.index >= t_s - pd.Timedelta(days=15))]
    s = wb.signal(SYM, kurz, fuenf_vor(w, t_s), t_s, bid, w.cfg)
    assert s["warten"] and "zu wenig Kerzen" in s["ergebnis"] and not s["kauf"]
    s = wb.signal(SYM, w.std, fuenf_vor(w, t_s).iloc[-100:], t_s, bid, w.cfg)      # Sitzung davor nur in Stunden
    assert s["warten"] and "Sitzung davor fehlt" in s["ergebnis"] and not s["kauf"]
    for t_e in (t_s - pd.Timedelta(hours=2), t_s + 31 * MIN):
        s = wb.signal(SYM, w.std, fuenf_vor(w, t_s), t_e, bid, w.cfg)
        assert not s["kauf"] and not s["warten"] and s["ergebnis"] == "nicht um 16:00 New York"
    s = wb.signal(SYM, w.std, w.df, pd.Timestamp("2026-03-14 20:00"), bid, w.cfg)
    assert not s["kauf"] and "Wochenende" in s["ergebnis"]
    f = fuenf_vor(w, t_s)
    halb = f[f.index < t_s - pd.Timedelta(hours=3)]                                # halber Tag: Schluss um 13:00
    s = wb.signal(SYM, w.std, halb, t_s, bid, w.cfg)
    assert not s["kauf"] and not s["warten"] and s["keine_sitzung"] and "keine volle Sitzung" in s["ergebnis"]


def test_ausstieg_nach_zehn_sitzungen_und_nach_einem_verpassten_lauf(w):
    s = w.s
    tage = [str(d)[:10] for d in s["datum"]]
    im = [k for k, d in enumerate(tage) if VON <= d <= BIS and k >= 11]
    h = next(k for k in im if not s["raus"][k])                                   # heute kein Ausstieg nach der Regel
    a = sig_am(w, tage[h], offen_seit=tage[h - 10], geprueft_bis=tage[h - 1])
    assert a["raus"] and a["grund"] == "zehn_tage" and a["sitzungen"] == 10 and "faellig_seit" not in a
    b = sig_am(w, tage[h], offen_seit=tage[h - 9], geprueft_bis=tage[h - 1])
    assert not b["raus"] and b["sitzungen"] == 9 and "bleibt offen (9 von 10 Sitzungen)" in b["ergebnis"]
    h = next(k for k in im if s["raus"][k - 1] and not s["raus"][k])               # gestern wäre er raus gewesen
    c = sig_am(w, tage[h], offen_seit=tage[h - 3], geprueft_bis=tage[h - 2])       # gestern lief der Bot nicht
    assert c["raus"] and c["grund"] == "regel" and c["faellig_seit"] == tage[h - 1] and "der Lauf" in c["ergebnis"]
    d = sig_am(w, tage[h], offen_seit=tage[h - 3], geprueft_bis=tage[h - 1])
    assert not d["raus"]
    e = sig_am(w, tage[h - 1], offen_seit=tage[h - 3])                            # am Tag selbst: raus nach der Regel
    assert e["raus"] and e["grund"] == "regel" and "faellig_seit" not in e


@pytest.mark.parametrize("tag, utc_16", [("2026-01-15", "2026-01-15 21:00"), ("2026-03-09", "2026-03-09 20:00"),
                                         ("2026-07-15", "2026-07-15 20:00"), ("2026-11-02", "2026-11-02 21:00")])
def test_schluss_um_16_uhr_new_york_in_sommer_und_winterzeit(w, tag, utc_16):
    assert wb.schluss(pd.Timestamp(tag), w.p) == pd.Timestamp(utc_16)


def _q(**kw):
    base = dict(bid=5000.0, offer=5000.6, tradeable=True, currency="USD", lot=1.0, min_size=0.01, size_step=0.01,
                margin_pct=5.0, decimals=1, min_dist=1.0, eur_rate=EURUSD)
    base.update(kw)
    return Quote(**base)


def test_groesse():
    assert wb.groesse(55.0, _q()) == (0.1, "")                    # 5 € = 5,50 $ / 55 Punkte = 0,1
    size, warum = wb.groesse(55.0, _q(min_size=1.0, size_step=1.0))
    assert size is None and "zu grob" in warum
    assert wb.groesse(55.0, _q(eur_rate=None))[0] is None


def test_konto_wird_nach_dem_namen_gefunden():
    kurz = "…" + KONTO7[-4:]
    daten = {"konten": [{"id": "…0001", "name": "Account 3"}, {"id": kurz, "name": "Account 7"}],
             "zuordnung": {"r6-noise-usdjpy": KONTO7}, "haupt": HAUPT, "frei": []}
    assert wb.konto_id(daten) == KONTO7
    assert wb.konto_id({**daten, "zuordnung": {}}) == ""
    assert wb.konto_id({**daten, "konten": daten["konten"] + [{"id": "…7777", "name": "Account 7"}]}) == ""


def test_echtes_konto_steht_in_konten_json_und_ist_das_von_noise_usdjpy():
    from gold.bot import konten
    from suche import welt4h_bot
    daten = json.loads((ROOT / "journal" / konten.DATEI).read_text(encoding="utf-8"))
    k = wb.konto_id(daten)
    assert k and not k.endswith(wb.HAUPT_ENDUNG) and k.isdigit() and len(k) > 5
    assert k == welt4h_bot.konto_id(daten) == daten["zuordnung"]["r6-noise-usdjpy"]


# --------------------------------------------------------------------------------------------------------------------
# Der Lauf auf dem Demokonto

class Antwort:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


def _kerzen(df: pd.DataFrame) -> list[dict]:
    return [{"snapshotTimeUTC": t.strftime("%Y-%m-%dT%H:%M:%S"),
             **{f"{n}Price": {"bid": float(x), "ask": float(x) + SPREAD} for n, x in zip(("open", "high", "low", "close"),
                                                                                        row)}}
            for t, row in zip(df.index, df[wb.SPALTEN].to_numpy())]


class Konto:
    """Capital.com zum Testen: Hauptkonto und Account 7. Kerzen nur für US500 aus der erfundenen Welt, US100 ist zu."""

    def __init__(self, w, bid, konto7=True, frei=900.0, min_size=0.01):
        self.account_id = HAUPT
        self.w = w
        self.bid, self.offer = bid, bid + SPREAD
        self.konto7, self.frei, self.markt_auf, self.min_size = konto7, frei, True, min_size
        self.jetzt = None
        self.pos: dict[str, dict] = {}
        self.fremd: list[dict] = []
        self.acts: dict[str, list] = {}
        self.calls: list = []
        self.abrufe: list = []
        self.refs: dict = {}
        self.nr = 0
        self.order_fehler = False

    def setze(self, bid):
        self.bid, self.offer = bid, bid + SPREAD

    def accounts(self):
        out = [{"accountId": HAUPT, "balance": {"balance": 990.0, "available": 900.0}}]
        if self.konto7:
            out.append({"accountId": KONTO7, "balance": {"balance": 1000.0, "available": self.frei}})
        return out

    def switch_account(self, aid):
        self.calls.append(("konto", aid))
        self.account_id = aid

    def market(self, epic):
        if epic in wb.MAERKTE.values():
            auf = self.markt_auf and epic == EPIC
            return {"snapshot": {"bid": self.bid, "offer": self.offer, "decimalPlacesFactor": 1,
                                 "marketStatus": "TRADEABLE" if auf else "CLOSED"},
                    "instrument": {"currency": "USD", "lotSize": 1, "marginFactor": 5, "marginFactorUnit": "PERCENTAGE"},
                    "dealingRules": {"minDealSize": {"value": self.min_size}, "minSizeIncrement": {"value": self.min_size},
                                     "minStopOrProfitDistance": {"unit": "POINTS", "value": 1.0}}}
        assert epic == "EURUSD"
        return {"snapshot": {"bid": EURUSD, "offer": EURUSD}}

    def positions(self):
        assert self.account_id == KONTO7, "der Bot darf nur auf Account 7 Positionen lesen"
        return [{"market": {"epic": p["epic"]}, "position": p} for p in self.pos.values()] + self.fremd

    def prices(self, epic, resolution="HOUR", max_bars=1000):
        """Die jüngsten Kerzen wie beim Broker, die laufende Kerze eingeschlossen."""
        self.abrufe.append((f"/prices/{epic}", resolution, max_bars))
        assert resolution == "MINUTE_5" and max_bars == wb.FUENF_MAX
        if epic != EPIC:
            return []
        return _kerzen(self.w.df[self.w.df.index <= self.jetzt].iloc[-max_bars:])

    def _get(self, path, **params):
        von, bis = pd.Timestamp(params["from"]), pd.Timestamp(params["to"])
        self.abrufe.append((path, params["resolution"], von, bis))
        assert params["resolution"] == "HOUR" and params["max"] == 1000 and bis - von <= pd.Timedelta(days=40)
        if path != f"/prices/{EPIC}":
            return {"prices": []}
        df = self.w.std
        return {"prices": _kerzen(df[(df.index >= von) & (df.index <= bis)])}

    def _request(self, method, path, json=None):
        assert self.account_id == KONTO7
        assert method == "POST" and path == "/positions"
        self.calls.append((method, path, json))
        self.nr += 1
        ref, deal = f"R{self.nr}", f"D{self.nr}"
        level = self.offer
        self.pos[deal] = {"dealId": deal, "epic": json["epic"], "level": level, "size": json["size"],
                          "direction": json["direction"], "stopLevel": json["stopLevel"]}
        self.refs[ref] = {"dealStatus": "ACCEPTED", "affectedDeals": [{"dealId": deal}], "level": level}
        if self.order_fehler:
            raise RuntimeError("Zeitüberschreitung")
        return Antwort({"dealReference": ref})

    def confirm(self, ref):
        return self.refs.get(ref, {"dealStatus": "ACCEPTED"})

    def close_position(self, deal_id):
        assert self.account_id == KONTO7
        self.calls.append(("DELETE", deal_id))
        self.pos.pop(deal_id)
        return {"dealStatus": "ACCEPTED", "level": self.bid}

    def activity(self, deal_id, since, until):
        assert until - since <= pd.Timedelta(days=1)
        return self.acts.get(deal_id, [])

    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]

    def zu(self):
        return [c for c in self.calls if c[0] == "DELETE"]


def us(st):
    return st["maerkte"][SYM]


def lauf(w, k, st, jetzt, **kw):
    k.jetzt = pd.Timestamp(jetzt)
    return wb.run(k, st, utc(jetzt), **kw)


def um_16(w, tag, k=None, minuten=1) -> pd.Timestamp:
    """Der Lauf `minuten` nach 16:00 New York an diesem Tag, das Bid dazu wie zur Kerze um 16:00 im Test."""
    t_s = wb.schluss(pd.Timestamp(tag), w.p)
    if k is not None:
        k.setze(kurs_um(w, t_s))
    return t_s + minuten * MIN


def test_kauf_um_16_uhr_wie_im_test_mit_stop_vom_bid_und_ohne_ziel(w):
    t = w.test[0]
    k = Konto(w, bid=kurs_um(w, t["t_e"]))
    st, log, fertig, blick = lauf(w, k, {}, t["t_e"] + MIN)
    tr = us(st)["trade"]
    stop = round(k.bid - t["sd"], 1)
    assert tr["richtung"] == 1 and tr["dist"] == pytest.approx(t["sd"], abs=1e-5) and tr["tag"] == t["tag"]
    assert tr["entry"] == k.offer and tr["stop"] == stop and tr["spaet_min"] == 1.0 and tr["wr"] < -90
    assert tr["fassung"] == "williams_us" and tr["satz_nacht"] == 0.065
    assert k.posts() == [("POST", "/positions", {"epic": EPIC, "direction": "BUY", "size": wb.groesse(t["sd"], _q())[0],
                                                  "guaranteedStop": False, "stopLevel": stop})]
    assert k.calls[0] == ("konto", KONTO7) and k.account_id == HAUPT              # zurück aufs Hauptkonto
    assert us(st)["letzter_tag"] == t["tag"] and [e["event"] for e in log] == ["Kauf eröffnet"] and not fertig
    assert blick["maerkte"]["NSXUSD"]["wartet"] == "Markt zu" and st["maerkte"]["NSXUSD"].get("letzter_tag") is None
    st2, _, _, _ = lauf(w, k, st, t["t_e"] + 16 * MIN)                            # zweiter Lauf, derselbe Tag
    assert len(k.posts()) == 1 and us(st2)["trade"]["dealId"] == tr["dealId"]


def test_ausstieg_um_16_uhr_nach_der_regel_wie_im_test(w):
    t = max((x for x in w.test if x["um_16"]), key=lambda x: x["t_aus"] - x["t_e"])      # der längste, übers Wochenende
    k = Konto(w, bid=kurs_um(w, t["t_e"]))
    st, _, _, _ = lauf(w, k, {}, t["t_e"] + MIN)
    tr = us(st)["trade"]
    aus_tag = str(wb.tag_von(t["t_aus"]).date())
    tage = sitzungstage(w, t["tag"], aus_tag)
    assert tage[-1] == aus_tag and len(tage) >= 3
    for tag in tage:
        st, log, fertig, _ = lauf(w, k, st, um_16(w, tag, k))
        if tag != aus_tag:
            assert not fertig and not k.zu() and us(st)["trade"]["geprueft_bis"] == tag
            assert "bleibt offen" in us(st)["letzte_pruefung"]["ergebnis"]
    r = fertig[0]
    assert k.zu() == [("DELETE", tr["dealId"])] and us(st)["trade"] is None and len(k.posts()) == 1
    assert r["grund"] in ("regel", "zehn_tage") and r["closed_utc"].startswith(str(t["t_aus"] + MIN)[:16].replace(" ", "T"))
    naechte = (pd.Timestamp(aus_tag) - pd.Timestamp(t["tag"])).days                   # wie rueckblick.gebuehr
    assert r["exit"] == kurs_um(w, t["t_aus"]) and r["naechte"] == naechte > len(tage)
    gebuehr = 0.065 * naechte / 365.0 * tr["entry"] / tr["dist"]
    assert r["gebuehr_r"] == pytest.approx(gebuehr, abs=1e-3) and r["r"] == pytest.approx(r["r_roh"] - r["gebuehr_r"],
                                                                                           abs=1e-3)
    assert r["r_roh"] == pytest.approx((r["exit"] - tr["entry"]) / tr["dist"], abs=1e-3)
    assert "der Test kauft heute nicht" in us(st)["letzte_pruefung"]["ergebnis"] and us(st)["letzter_tag"] == aus_tag
    assert st["trades"] == 1 and st["summe_r"] == r["r"]


def _nach_kauf(w):
    t = w.test[0]
    k = Konto(w, bid=kurs_um(w, t["t_e"]))
    st, _, _, _ = lauf(w, k, {}, t["t_e"] + MIN)
    morgen = sitzungstage(w, t["tag"], "2099-01-01")[0]
    return t, k, st, morgen


def test_kein_neuer_kauf_an_der_kerze_des_ausstiegs_ausser_nach_einem_verpassten_lauf(w, monkeypatch):
    echt = wb.signal

    def raus_und_kauf(faellig):
        def f(*a, **kw):
            out = echt(*a, **kw)
            out.update(raus=True, grund="regel", kauf=True, dist=50.0, warten=False)
            if faellig:
                out["faellig_seit"] = "gestern"
            return out
        return f

    t, k, st, morgen = _nach_kauf(w)
    monkeypatch.setattr(wb, "signal", raus_und_kauf(False))
    st2, _, fertig, _ = lauf(w, k, st, um_16(w, morgen, k))
    assert fertig[0]["grund"] == "regel" and len(k.zu()) == 1 and len(k.posts()) == 1   # zu, aber kein neuer Kauf
    assert "der Test kauft heute nicht" in us(st2)["letzte_pruefung"]["ergebnis"]
    t, k, st, morgen = _nach_kauf(w)
    monkeypatch.setattr(wb, "signal", raus_und_kauf(True))
    st2, _, fertig, _ = lauf(w, k, st, um_16(w, morgen, k))
    assert fertig[0]["grund"] == "regel" and len(k.zu()) == 1 and len(k.posts()) == 2   # der Test war schon frei
    assert us(st2)["trade"]["tag"] == morgen and us(st2)["trade"]["dist"] == 50.0


def test_stop_beim_broker_wird_gebucht_und_bis_dahin_kein_neuer_kauf(w):
    t, k, st, morgen = _nach_kauf(w)
    tr = us(st)["trade"]
    k.pos.pop(tr["dealId"])
    k.acts[tr["dealId"]] = [{"dateUTC": (t["t_e"] + pd.Timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S"),
                             "source": "SL", "type": "POSITION", "status": "ACCEPTED",
                             "details": {"level": tr["stop"], "actions": []}}]
    st2, _, fertig, _ = lauf(w, k, st, t["t_e"] + pd.Timedelta(hours=4))
    assert fertig[0]["grund"] == "stop" and fertig[0]["exit"] == tr["stop"] and "exit_geschaetzt" not in fertig[0]
    assert fertig[0]["r_roh"] == pytest.approx(-1.0, abs=0.02) and us(st2)["trade"] is None
    k.acts = {}                                                                   # Schluss noch nicht lesbar
    st2, log, fertig, blick = lauf(w, k, st, um_16(w, morgen, k))
    assert not fertig and log[0]["event"].startswith("Position beim Broker zu") and "Schlusskurs" in wb.status(st2)
    assert blick["maerkte"][SYM]["wartet"].startswith("Position beim Broker zu") and us(st2).get("letzter_tag") != morgen
    st3, _, fertig, _ = lauf(w, k, st2, um_16(w, morgen, k, 16))                  # letzter Lauf der Frist
    assert not fertig and len(k.posts()) == 1 and us(st3)["ausgelassen"] == {"offen": 1}
    st4, _, fertig, _ = lauf(w, k, st3, um_16(w, morgen, k, 62))
    assert fertig[0]["grund"] == "stop" and fertig[0]["exit_geschaetzt"] and us(st4)["trade"] is None


def test_sperren(w, monkeypatch):
    t = w.test[0]
    jetzt = t["t_e"] + MIN
    k = Konto(w, bid=kurs_um(w, t["t_e"]))
    k.fremd = [{"market": {"epic": EPIC}, "position": {"dealId": "FREMD", "level": 5000.0, "size": 0.1}},
               {"market": {"epic": "USDJPY"}, "position": {"dealId": "NOISE", "level": 150.0, "size": 0.1}}]
    st, log, _, _ = lauf(w, k, {}, jetzt)
    assert us(st)["trade"] is None and not k.posts() and "fremde Position auf US500 im Konto" in log[-1]["gruende"]
    assert us(st)["fremd"] == ["FREMD"] and not k.zu() and us(st)["ausgelassen"] == {"sperre": 1}
    k = Konto(w, bid=kurs_um(w, t["t_e"]))
    k.fremd = [{"market": {"epic": "USDJPY"}, "position": {"dealId": "NOISE", "level": 150.0, "size": 0.1}},
               {"market": {"epic": "DE40"}, "position": {"dealId": "WELT", "level": 24000.0, "size": 0.1}}]
    lauf(w, k, {}, jetzt)                                                         # USD/JPY und DAX stören nicht
    assert len(k.posts()) == 1
    k = Konto(w, bid=kurs_um(w, t["t_e"]))
    st, log, _, _ = lauf(w, k, {"pausiert": {"seit": "x", "grund": "y"}}, jetzt)
    assert not k.posts() and "Pause ab -25 R" in log[-1]["gruende"]
    k = Konto(w, bid=kurs_um(w, t["t_e"]), frei=10.0)                             # zu wenig freies Geld
    st, log, _, _ = lauf(w, k, {}, jetzt)
    assert not k.posts() and any("des freien Gelds" in g for g in log[-1]["gruende"])
    k = Konto(w, bid=kurs_um(w, t["t_e"]), min_size=1.0)                          # kleinste Größe zu grob
    st, log, _, _ = lauf(w, k, {}, jetzt)
    assert not k.posts() and us(st)["ausgelassen"] == {"groesse": 1}
    monkeypatch.setattr(wb, "vorab_ok", lambda: False)
    k = Konto(w, bid=kurs_um(w, t["t_e"]))
    st, log, _, _ = lauf(w, k, {}, jetzt)
    assert not k.posts() and any("nicht festgelegt" in g for g in log[-1]["gruende"])


def test_ohne_siegel_der_runde_kein_signal(w, monkeypatch):
    t = w.test[0]
    monkeypatch.setattr(wb, "lade_cfg", lambda pruefen=False: None if pruefen else w.cfg)
    k = Konto(w, bid=kurs_um(w, t["t_e"]))
    st, _, _, blick = lauf(w, k, {}, t["t_e"] + MIN)
    assert not k.posts() and not k.abrufe and "Siegel passt nicht" in blick["maerkte"][SYM]["wartet"]
    assert blick["naechste_pruefung_utc"] is None


def test_margin_zaehlt_die_orders_aus_demselben_lauf(w, monkeypatch):
    t = w.test[0]
    laeufe, orig = [], wb.Lauf.__init__

    def merken(self, *a, **kw):
        orig(self, *a, **kw)
        laeufe.append(self)
    monkeypatch.setattr(wb.Lauf, "__init__", merken)
    k = Konto(w, bid=kurs_um(w, t["t_e"]))
    lauf(w, k, {}, t["t_e"] + MIN)
    size = k.posts()[0][2]["size"]
    assert laeufe[-1].gebunden > 0 and laeufe[-1].gebunden == pytest.approx(size * k.bid * 0.05 / EURUSD, rel=1e-9)

    def schon_gebunden(self, *a, **kw):
        orig(self, *a, **kw)
        self.gebunden = 899.0                                 # 900 € frei, davon 899 € schon von diesem Lauf gebunden
    monkeypatch.setattr(wb.Lauf, "__init__", schon_gebunden)
    k = Konto(w, bid=kurs_um(w, t["t_e"]))
    st, log, _, _ = lauf(w, k, {}, t["t_e"] + MIN)
    assert not k.posts() and any("des freien Gelds (1 €)" in g for g in log[-1]["gruende"])
    assert us(st)["ausgelassen"] == {"sperre": 1}


def test_nie_auf_dem_hauptkonto_und_nie_ohne_konto(w, monkeypatch):
    t_e = w.test[0]["t_e"]
    k = Konto(w, bid=kurs_um(w, t_e), konto7=False)
    st, log, _, blick = lauf(w, k, {}, t_e + MIN)
    assert not [c for c in k.calls if c[0] in ("POST", "konto")] and "nicht gefunden" in blick["status"]
    monkeypatch.setattr(wb, "KONTO", "")
    k = Konto(w, bid=kurs_um(w, t_e))
    st, log, _, blick = lauf(w, k, {}, t_e + MIN)
    assert not k.calls and "journal/konten.json" in blick["status"]
    monkeypatch.setattr(wb, "KONTO", HAUPT)                                        # endet wie das Hauptkonto
    st, log, _, _ = lauf(w, Konto(w, bid=kurs_um(w, t_e)), {}, t_e + MIN)
    assert log[0]["event"] == "kein Konto"


def test_frist_verpasst_markt_zu_und_trockenlauf(w):
    t = w.test[0]
    t_e = t["t_e"]
    k = Konto(w, bid=kurs_um(w, t_e))
    st, _, _, _ = lauf(w, k, {}, t_e - MIN)                                       # vor 16:00: nichts
    assert not k.abrufe and us(st).get("letzter_tag") is None
    st, _, _, _ = lauf(w, k, {}, t_e + 21 * MIN)                                  # kein Lauf in der Frist
    assert not k.posts() and not k.abrufe and us(st)["letzter_tag"] == t["tag"]
    assert us(st)["ausgelassen"] == {"verpasst": 1} and us(st)["letzte_pruefung"]["ergebnis"].startswith("verpasst")
    st, _, _, _ = lauf(w, k, {}, t_e + 21 * MIN, send_orders=False)
    assert us(st).get("letzter_tag") is None and not us(st).get("ausgelassen")
    k = Konto(w, bid=kurs_um(w, t_e))
    st, _, _, _ = lauf(w, k, {}, t_e + 16 * MIN)                                  # letzter Lauf in der Frist
    assert len(k.posts()) == 1 and us(st)["trade"]["spaet_min"] == 16.0
    k = Konto(w, bid=kurs_um(w, t_e))
    k.markt_auf = False
    st, _, _, blick = lauf(w, k, {}, t_e + MIN)
    assert not k.posts() and blick["maerkte"][SYM]["wartet"] == "Markt zu" and us(st).get("letzter_tag") is None
    st, _, _, _ = lauf(w, k, st, t_e + 16 * MIN)
    assert not k.posts() and us(st)["ausgelassen"] == {"markt_zu": 1} and us(st)["letzter_tag"] == t["tag"]
    k = Konto(w, bid=kurs_um(w, t_e))
    st, log, _, _ = lauf(w, k, {}, t_e + MIN, send_orders=False)
    assert not k.posts() and log[-1]["event"] == "würde kaufen" and us(st).get("letzter_tag") is None


def test_tag_ohne_volle_sitzung_zaehlt_mit(w, monkeypatch):
    t = w.test[0]
    echt = wb.signal
    monkeypatch.setattr(wb, "signal", lambda *a, **kw: {**echt(*a, **kw), "kauf": False, "keine_sitzung": True,
                                                          "ergebnis": "keine volle Sitzung 9:30 bis 16:00 New York heute"})
    k = Konto(w, bid=kurs_um(w, t["t_e"]))
    st, _, _, _ = lauf(w, k, {}, t["t_e"] + MIN)
    assert not k.posts() and us(st)["ausgelassen"] == {"keine_sitzung": 1} and us(st)["letzter_tag"] == t["tag"]


def test_order_ohne_bestaetigung_wird_uebernommen(w):
    t_e = w.test[0]["t_e"]
    k = Konto(w, bid=kurs_um(w, t_e))
    k.order_fehler = True
    st, _, _, _ = lauf(w, k, {}, t_e + MIN)
    assert len(k.posts()) == 1 and us(st)["trade"]["dealId"] == "D1"
    lauf(w, k, st, t_e + 16 * MIN)
    assert len(k.posts()) == 1


def test_abrufe_nur_um_16_uhr(w):
    t_e = w.test[0]["t_e"]
    k = Konto(w, bid=kurs_um(w, t_e))
    st, _, _, blick = lauf(w, k, {}, t_e - pd.Timedelta(hours=4))                 # Mittag New York: nichts zu tun
    assert not k.abrufe and pd.Timestamp(blick["naechste_pruefung_utc"]) == t_e
    lauf(w, k, {}, t_e + MIN)
    fuenf = [a for a in k.abrufe if a[1] == "MINUTE_5"]
    stunden = [a for a in k.abrufe if a[1] == "HOUR"]
    assert fuenf == [(f"/prices/{EPIC}", "MINUTE_5", 1000)]                       # einmal, US100 ist zu: kein Abruf
    assert stunden and min(a[2] for a in stunden) >= t_e + MIN - pd.Timedelta(days=wb.TAGE_KERZEN)
    assert {a[0] for a in k.abrufe} == {f"/prices/{EPIC}"}


@pytest.mark.parametrize("jetzt, naechste", [("2026-03-13 20:10", "2026-03-13 20:00"),    # Freitag in der Frist
                                             ("2026-03-13 20:25", "2026-03-16 20:00"),    # Freitag danach: Montag
                                             ("2026-03-14 12:00", "2026-03-16 20:00"),    # Samstag
                                             ("2026-03-12 15:00", "2026-03-12 20:00")])   # Donnerstag Vormittag
def test_naechste_pruefung_ueberspringt_das_wochenende(w, jetzt, naechste):
    _, _, _, blick = lauf(w, Konto(w, bid=5000.0), {}, pd.Timestamp(jetzt), send_orders=False)
    assert blick["naechste_pruefung_utc"] == naechste + ":00"


def test_schreiben(tmp_path, w):
    t_e = w.test[0]["t_e"]
    k = Konto(w, bid=kurs_um(w, t_e))
    st, log, fertig, blick = lauf(w, k, {}, t_e + MIN)
    j, c = tmp_path / "williams-us", tmp_path / "williams-us.json"
    assert wb.schreiben(st, log, fertig, blick, j, c)
    assert not wb.schreiben(st, [], [], blick, j, c)                              # nichts Neues, nichts geschrieben
    karte = json.loads(c.read_text(encoding="utf-8"))
    assert karte["bot"] == "williams-us" and karte["konto"] == "Account 7" and KONTO7 not in c.read_text()
    assert karte["offen"][0]["epic"] == EPIC and karte["zusammenfassung"]["urteil"].startswith("läuft (0 von 40")
    assert set(karte["ausgelassen"]) == set(wb.MAERKTE) and "NICHT bestanden" in karte["backtest"]
    assert karte["maerkte"] == {"SPXUSD": "US500", "NSXUSD": "US100"} and "Kauf offen seit" in karte["status"]
    for fremd in ("konten.json", "welt-ausbruch4h.json", "r6-bots.json", "vix-sprung.json"):
        with pytest.raises(RuntimeError):
            wb.schreiben(st, log, fertig, blick, j, tmp_path / fremd)


def test_bewertung():
    tr = ([{"r": 1.0, "markt": "SPXUSD", "pnl_eur": 5}] * 25 + [{"r": -1.0, "markt": "NSXUSD", "pnl_eur": -5}] * 15)
    b = wb.bewertung(tr)
    assert b["trades"] == 40 and b["pf_r"] == pytest.approx(25 / 15, abs=1e-3) and b["urteil"].startswith("bestanden")
    assert b["je_markt"]["NSXUSD"] == {"trades": 15, "summe_r": -15.0} and b["summe_eur"] == 50.0
    assert wb.bewertung([{"r": -1.0}] * 15)["urteil"].startswith("Zwischencheck")
    assert wb.bewertung([{"r": 1.0}] * 14 + [{"r": -1.0}] * 26)["urteil"].startswith("durchgefallen")


def test_mitnutzer_kennt_den_bot():
    from suche import mitnutzer
    b = {x["bot"]: x for x in mitnutzer.bots()}["williams-us"]
    assert b["konto_name"] == "Account 7" and b["neu"] and b["konto"] == KONTO7


def test_regeln_sind_versiegelt(monkeypatch):
    monkeypatch.undo()
    assert wb.vorab_ok(), "suche/VORAB_williams_bot.yaml braucht seine Prüfsumme im Protokoll"
    vorab = wb.VORAB.read_text(encoding="utf-8")
    assert wb.KONTO not in vorab and "Account 7" in vorab
    for wort in ("williams_us", "-25 R", "Test NICHT", "2,66", "z 2,35", "1,51", "47 von 77", "nach_trades: 40",
                 "11:53 UTC", "VORAB_schatten", "-7,70 Euro", "verpasst"):
        assert wort in vorab, wort
    import yaml
    r = yaml.safe_load(vorab)["williams_bot"]
    assert r["bot"] == wb.BOT_ID
    assert r["groesse"]["risiko_eur"] == wb.RISIKO_EUR and r["groesse"]["margin_anteil"] == wb.MARGE_ANTEIL
    assert r["groesse"]["max_risiko_faktor"] == wb.MAX_RISIKO_FAKTOR
    assert r["ausfuehrung"]["frist_min"] == wb.FRIST.total_seconds() / 60
    assert r["ausfuehrung"]["vorlauf_tage"] == wb.TAGE_KERZEN and r["ausfuehrung"]["min_handelstage"] == wb.MIN_TAGE
    assert r["ausfuehrung"]["fuenf_kerzen"] == wb.FUENF_MAX
    assert r["urteil"]["nach_trades"] == wb.URTEIL_NACH and r["urteil"]["pause_r"] == wb.PAUSE_R
    z = r["gegenprobe_zahlen"]
    assert all(z[m]["nur_bot"] == 0 and z[m]["nur_test"] == 0 and z[m]["gleich"] == z[m]["test_trades"]
               == z[m]["ausstieg_gleich"] for m in wb.MAERKTE)
    assert z["SPXUSD"]["gleich"] + z["NSXUSD"]["gleich"] == 77


def test_ablauf_im_workflow():
    wf = (ROOT / ".github" / "workflows" / "demo-bots.yml").read_text(encoding="utf-8")
    assert "python -m pytest -q tests/test_williams_bot.py" in wf and "python -m suche.williams_bot" in wf
    assert "touch .tests-ok/williams" in wf and "python -m suche.williams_bot --dry-run" in wf
