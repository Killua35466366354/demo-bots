"""Tests für suche/vix_sprung_bot.py: Der Bot sieht mit Stundenkerzen vom Broker und dem VIX von Cboe dieselben
Einstiege, Stops und Ausstiege wie der Test der großen Runde (Fassungen vix_sprung_us und vix_sprung_welt) mit
5-Minuten-Kerzen und der FRED-Reihe. Er kauft nur nach einem VIX-Sprung, nur auf Account 5, höchstens einen Trade je
Markt, mit Stop beim Broker und ohne Ziel, und steigt vor 15:55 New York aus. An Tagen ohne Sprung fragt er den Broker
nichts. Alle Kurse, Reihen und Kontonummern hier sind erfunden."""
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from suche import grosse_runde as gr
from suche import modell_indizes_bot as mb
from suche import modell_indizes_gegenprobe as mg
from suche import rueckblick as rb
from suche import vix_sprung_bot as vb
from suche import vix_sprung_gegenprobe as gp
from suche.demo_bots import Quote

ROOT = Path(__file__).resolve().parents[1]
HAUPT = "111111113150"
KONTO5 = "111111115555"
MIN = pd.Timedelta(minutes=1)
SYM, EPIC = "SPXUSD", "US500"
SPREAD = 0.6
EURUSD = 1.1
VON, BIS = "2026-02-02", "2026-03-13"
SPRUENGE = ["2026-02-03", "2026-02-11", "2026-02-19", "2026-02-27", "2026-03-10"]   # 27.02. ist ein Freitag


def erfundene_kurse(von="2025-11-02", bis="2026-03-21", seed=7, start=5000.0) -> pd.DataFrame:
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


def erfundener_vix(seed=11) -> pd.Series:
    """VIX an jedem Werktag, auf zwei Stellen wie bei Cboe. Sonst höchstens 8 % am Tag, an SPRUENGE 15 % hoch."""
    rng = np.random.default_rng(seed)
    tage = pd.bdate_range("2025-10-01", "2026-03-31")
    r = np.clip(rng.normal(0, 0.03, len(tage)), -0.08, 0.08)
    r[tage.isin(pd.DatetimeIndex(SPRUENGE))] = 0.15
    werte, v = [], 18.0
    for x in r:
        v = round(v * (1 + x), 2)
        werte.append(v)
    return pd.Series(werte, tage)


class Netz:
    """Cboe zum Testen: liefert den erfundenen VIX als CSV wie die echte Seite."""

    def __init__(self, vix: pd.Series, fehler: bool = False):
        self.vix, self.fehler, self.urls = vix, fehler, []

    def __call__(self, url, timeout=None):
        self.urls.append(url)
        if self.fehler:
            raise RuntimeError("keine Verbindung")
        assert url == mb.CBOE.format(name="VIX")
        zeilen = ["DATE,OPEN,HIGH,LOW,CLOSE"] + [f"{t:%m/%d/%Y},{v:.6f},{v:.6f},{v:.6f},{v:.6f}" for t, v in self.vix.items()]
        return SimpleNamespace(text="\n".join(zeilen) + "\n", raise_for_status=lambda: None)


@pytest.fixture(autouse=True)
def _welt(monkeypatch):
    monkeypatch.setattr(vb, "vorab_ok", lambda: True)
    monkeypatch.setattr(vb, "KONTO", KONTO5)


@pytest.fixture(scope="module")
def w(tmp_path_factory):
    """Die erfundene Welt: Kurse, VIX, der Markt des Tests und alle Signale des Tests im Fenster."""
    ordner, fred = tmp_path_factory.mktemp("kurse"), tmp_path_factory.mktemp("fred")
    df = erfundene_kurse()
    schreibe_npz(df, ordner)
    shutil.copy(ordner / f"{SYM}.npz", ordner / "GRXEUR.npz")      # dieselben Kurse als DAX für vix_sprung_welt
    vix = erfundener_vix()
    mb.fremd_schreiben({"VIXCLS": vix}, fred)
    cfgs = vb.lade_cfg(pruefen=True)
    cfg, p = cfgs[1], vb.regel(SYM, cfgs)
    m = gr.Markt(SYM, ordner, cfg, cfg["fenster"]["bis"])
    with mb.fred_ordner(fred):
        rich = gr.richtung_reihe(m.gtag, p)
    sig = gr._tagestrades(m, cfg, rich, p["stop_atr"])
    test = {str(m.gtag[m.gpos[m.tix[s["i0"]]]])[:10]: s for s in sig}
    im = {t: s for t, s in test.items() if VON <= t <= BIS}
    ohne = [str(t)[:10] for t in m.gtag if VON <= str(t)[:10] <= BIS and str(t)[:10] not in test]
    return SimpleNamespace(ordner=ordner, fred=fred, df=df, vix=vix, cfgs=cfgs, cfg=cfg, p=p, m=m, sig=sig, test=im,
                           std=mg.stunden_aus(m), tage=sorted(im), ohne=ohne)


def utc(t):
    return pd.Timestamp(t).tz_localize("UTC").to_pydatetime()


def einstieg(w, tag) -> pd.Timestamp:
    return pd.Timestamp(w.m.t[w.test[tag]["i0"]])


def einstieg_ohne(w, tag) -> pd.Timestamp:
    i, _ = gr.tages_einstieg(w.m, w.cfg)
    return pd.Timestamp(w.m.t[i[int(np.searchsorted(w.m.gtag, np.datetime64(tag)))]])


def kurs_um(w, t) -> float:
    return float(w.df["open"].loc[pd.Timestamp(t)])


# --------------------------------------------------------------------------------------------------------------------
# Bot und Test sehen dasselbe

def test_die_erfundene_welt_hat_spruenge_auch_nach_einem_freitag(w):
    nach = [str((pd.Timestamp(t) + pd.offsets.BDay(1)).date()) for t in SPRUENGE]
    assert w.tage == nach and "2026-03-02" in w.tage                 # Freitag 27.02. -> Montag, 3 Tage alt
    assert all(s["d"] == 1 for s in w.test.values())


@pytest.mark.parametrize("sym", ["SPXUSD", "GRXEUR"])
@pytest.mark.parametrize("abkuerzung", [True, False])
def test_bot_sieht_dieselben_einstiege_stops_und_ausstiege_wie_der_test(w, sym, abkuerzung):
    cfg, p = w.cfgs[vb.DURCHGANG[sym]], vb.regel(sym, w.cfgs)
    m = gr.Markt(sym, w.ordner, cfg, cfg["fenster"]["bis"])
    with mb.fred_ordner(w.fred):
        test = gr.signale(vb.FASSUNG[sym], m, cfg, np.array([], dtype="datetime64[ns]"))
    res = gp.gegenprobe(sym, w.ordner, w.cfgs, VON, BIS, test_signale=test, fred=w.fred, abkuerzung=abkuerzung)
    assert res["test_signale"] == len(w.test) == 5 and res["fassung"] == vb.FASSUNG[sym]
    assert res["bot_signale"] == res["beide"] == res["einstieg_gleich"] == res["ausstieg_gleich"] == 5
    assert res["nur_bot"] == {} and res["nur_test"] == {} and res["abkuerzung_falsch"] == {}
    assert res["bot_wartet"] == {} and res["stop_abweichung_rel"]["groesste"] < 1e-6


def test_fassungen_kommen_aus_den_versiegelten_runden(w):
    for sym in vb.MAERKTE:
        p = vb.regel(sym, w.cfgs)
        assert p["art"] == "reihe" and p["reihe"] == vb.REIHE == "VIXCLS" and p.get("lag", 0) == 0
        assert (p["tage"], p["relativ"], p["nur_anstieg"], p["schwelle"], p["vorzeichen"], p["frisch_tage"],
                p["stop_atr"]) == (1, True, True, 0.10, 1, 3, 3.0)
        assert "halte_tage" not in p and "geduld" not in p
    assert w.cfgs[1]["varianten"]["vix_sprung_us"] == {"regel": "vix_sprung_us", "maerkte": ["SPXUSD", "NSXUSD"]}
    assert w.cfgs[2]["varianten"]["vix_sprung_welt"] == {"regel": "vix_sprung_welt",
                                                         "maerkte": ["GRXEUR", "UKXGBP", "JPXJPY"]}
    assert vb.MAERKTE == {"SPXUSD": "US500", "NSXUSD": "US100", "GRXEUR": "DE40", "UKXGBP": "UK100", "JPXJPY": "J225"}
    assert w.cfgs[1]["tageshandel"] == w.cfgs[2]["tageshandel"] and w.cfgs[1]["kosten"] == w.cfgs[2]["kosten"]
    assert (w.cfg["daten"]["pause_min"], w.cfg["tageshandel"]["toleranz_min"], w.cfg["tageshandel"]["aus_min"]) == (
        60, 540, 955)


# --------------------------------------------------------------------------------------------------------------------
# Zeit und VIX

@pytest.mark.parametrize("tag, erwartet", [
    ("2026-11-24", "2026-11-23"),
    ("2026-11-23", "2026-11-20"),                                # Montag: Wert vom Freitag
    ("2026-11-27", "2026-11-25"),                                # Thanksgiving ohne Wert
    ("2026-12-28", "2026-12-24"),                                # Weihnachten ohne Wert
    ("2027-01-19", "2027-01-15"),                                # Martin Luther King Day
    ("2027-03-29", "2027-03-25"),                                # Karfreitag
])
def test_erwarteter_vix_wert(tag, erwartet):
    assert vb.erwartet(pd.Timestamp(tag)) == pd.Timestamp(erwartet)


def test_feiertage_sind_werktage_und_reichen_bis_ende_2027():
    tage = pd.DatetimeIndex(vb.FEIERTAGE)
    assert (tage.weekday < 5).all() and tage.is_monotonic_increasing and tage.max().year == 2027


def test_vix_von_cboe_wie_die_fred_datei(w, tmp_path):
    netz = Netz(w.vix)
    vix = vb.vix_holen(netz)
    assert len(netz.urls) == 1 and vix.index.is_monotonic_increasing and (vix == w.vix).all()
    mb.fremd_schreiben({"VIXCLS": vix}, tmp_path)
    with mb.fred_ordner(tmp_path):
        werte, daten = gr.vor("VIXCLS", np.array(["2026-02-04"], dtype="datetime64[D]"))
    assert str(daten[0]) == "2026-02-03" and werte[0] == w.vix["2026-02-03"]
    assert gr.FRED != tmp_path                                     # danach wieder die Datei des Tests
    assert vb.vix_stand(vix, pd.Timestamp("2026-02-04")) == {"datum": "2026-02-03", "erwartet": "2026-02-03",
                                                             "frisch": True}
    alt = vb.vix_stand(vix.drop(pd.Timestamp("2026-02-03")), pd.Timestamp("2026-02-04"))
    assert alt["datum"] == "2026-02-02" and not alt["frisch"]
    assert not vb.vix_stand(None, pd.Timestamp("2026-02-04"))["frisch"]


def test_sprung_wie_der_test(w):
    for tag in [str(t)[:10] for t in w.m.gtag if VON <= str(t)[:10] <= BIS]:
        s = vb.sprung(pd.Timestamp(tag), w.p, w.fred)
        assert s["richtung"] == (1 if tag in w.test else 0), tag
    s = vb.sprung(pd.Timestamp("2026-03-02"), w.p, w.fred)
    assert s["vix_datum"] == "2026-02-27" and s["vix_vorher_datum"] == "2026-02-26"
    erwartet = w.vix["2026-02-27"] / w.vix["2026-02-26"] - 1
    assert erwartet >= 0.10 and s["vix_aenderung"] == pytest.approx(erwartet, abs=1e-6)


def test_signal_haengt_nicht_an_der_zukunft(w, tmp_path):
    tag = w.tage[0]
    t_e = einstieg(w, tag)
    std = w.std[w.std.index < t_e.floor("h")]
    a = vb.signal(SYM, std, t_e, kurs_um(w, t_e), w.cfgs, fred=w.fred)
    verrueckt = w.vix.copy()
    verrueckt[verrueckt.index >= pd.Timestamp(tag)] *= 0.5        # Werte ab dem Handelstag selbst
    mb.fremd_schreiben({"VIXCLS": verrueckt}, tmp_path)
    b = vb.signal(SYM, std, t_e, kurs_um(w, t_e), w.cfgs, fred=tmp_path)
    assert a["ok"] and b["ok"] and a["dist"] == b["dist"] and a["vix_aenderung"] == b["vix_aenderung"]
    c = vb.signal(SYM, w.std[w.std.index < t_e.floor("h") + pd.Timedelta(days=3)], t_e, kurs_um(w, t_e), w.cfgs,
                  fred=w.fred)                                     # Kerzen nach dem Einstieg zählen nicht
    assert c["dist"] == a["dist"] and c["bis_utc"] == a["bis_utc"] == str(pd.Timestamp(w.test[tag]["t_max"]))


def test_signal_wartet_ohne_kerzen_und_ausserhalb_des_einstiegs(w):
    tag = w.tage[0]
    t_e = einstieg(w, tag)
    kurz = w.std[(w.std.index < t_e.floor("h")) & (w.std.index >= t_e - pd.Timedelta(days=20))]
    s = vb.signal(SYM, kurz, t_e, kurs_um(w, t_e), w.cfgs, fred=w.fred)
    assert s["warten"] and "zu wenig Kerzen" in s["ergebnis"] and not s["ok"]
    s = vb.signal(SYM, w.std, t_e - pd.Timedelta(hours=2), kurs_um(w, t_e), w.cfgs, fred=w.fred)
    assert not s["ok"] and "außerhalb" in s["ergebnis"]
    t0 = einstieg_ohne(w, w.ohne[3])
    s = vb.signal(SYM, w.std[w.std.index < t0.floor("h")], t0, kurs_um(w, t0), w.cfgs, fred=w.fred)
    assert not s["ok"] and not s["warten"] and s["ergebnis"].startswith("kein Trade: VIX")


def _q(**kw):
    base = dict(bid=5000.0, offer=5000.6, tradeable=True, currency="USD", lot=1.0, min_size=0.01, size_step=0.01,
                margin_pct=5.0, decimals=1, min_dist=1.0, eur_rate=EURUSD)
    base.update(kw)
    return Quote(**base)


def test_groesse():
    assert vb.groesse(55.0, _q()) == (0.1, "")                    # 5 € = 5,50 $ / 55 Punkte = 0,1
    size, warum = vb.groesse(55.0, _q(min_size=1.0, size_step=1.0))
    assert size is None and "zu grob" in warum
    assert vb.groesse(55.0, _q(eur_rate=None))[0] is None


def test_konto_wird_nach_dem_namen_gefunden():
    kurz = "…" + KONTO5[-4:]
    daten = {"konten": [{"id": "…0001", "name": "Account 3"}, {"id": kurz, "name": "Account 5"}],
             "zuordnung": {"r5-ruecksetzer-us30": KONTO5}, "haupt": HAUPT, "frei": []}
    assert vb.konto_id(daten) == KONTO5
    assert vb.konto_id({**daten, "zuordnung": {}}) == ""
    assert vb.konto_id({**daten, "konten": daten["konten"] + [{"id": "…7777", "name": "Account 5"}]}) == ""


def test_echtes_konto_steht_in_konten_json_und_ist_nie_das_hauptkonto():
    from gold.bot import konten
    k = vb.konto_id(json.loads((ROOT / "journal" / konten.DATEI).read_text(encoding="utf-8")))
    assert k and not k.endswith(vb.HAUPT_ENDUNG) and k.isdigit() and len(k) > 5


# --------------------------------------------------------------------------------------------------------------------
# Der Lauf auf dem Demokonto

class Antwort:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class Konto:
    """Capital.com zum Testen: Hauptkonto und Account 5. Kerzen nur für US500 aus der erfundenen Welt, die anderen
    vier Märkte sind zu."""

    def __init__(self, w, bid, konto5=True, frei=900.0, min_size=0.01):
        self.account_id = HAUPT
        self.w = w
        self.bid, self.offer = bid, bid + SPREAD
        self.konto5, self.frei, self.markt_auf, self.min_size = konto5, frei, True, min_size
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
        if self.konto5:
            out.append({"accountId": KONTO5, "balance": {"balance": 1000.0, "available": self.frei}})
        return out

    def switch_account(self, aid):
        self.calls.append(("konto", aid))
        self.account_id = aid

    def market(self, epic):
        if epic in vb.MAERKTE.values():
            auf = self.markt_auf and epic == EPIC
            return {"snapshot": {"bid": self.bid, "offer": self.offer, "decimalPlacesFactor": 1,
                                 "marketStatus": "TRADEABLE" if auf else "CLOSED"},
                    "instrument": {"currency": "USD", "lotSize": 1, "marginFactor": 5, "marginFactorUnit": "PERCENTAGE"},
                    "dealingRules": {"minDealSize": {"value": self.min_size}, "minSizeIncrement": {"value": self.min_size},
                                     "minStopOrProfitDistance": {"unit": "POINTS", "value": 1.0}}}
        assert epic == "EURUSD"
        return {"snapshot": {"bid": EURUSD, "offer": EURUSD}}

    def positions(self):
        assert self.account_id == KONTO5, "der Bot darf nur auf Account 5 Positionen lesen"
        return [{"market": {"epic": p["epic"]}, "position": p} for p in self.pos.values()] + self.fremd

    def _get(self, path, **params):
        von, bis = pd.Timestamp(params["from"]), pd.Timestamp(params["to"])
        self.abrufe.append((path, params["resolution"], von, bis))
        if path != f"/prices/{EPIC}":
            return {"prices": []}
        if params["resolution"] == "HOUR":
            assert params["max"] == 1000 and bis - von <= pd.Timedelta(days=40)
            df = self.w.std
        else:
            assert params["resolution"] == "MINUTE_5"
            df = self.w.df
        df = df[(df.index >= von) & (df.index <= bis)]
        return {"prices": [{"snapshotTimeUTC": t.strftime("%Y-%m-%dT%H:%M:%S"),
                            **{f"{n}Price": {"bid": float(x), "ask": float(x) + SPREAD}
                               for n, x in zip(("open", "high", "low", "close"), row)}}
                           for t, row in zip(df.index, df[mb.SPALTEN].to_numpy())]}

    def _request(self, method, path, json=None):
        assert self.account_id == KONTO5
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
        assert self.account_id == KONTO5
        self.calls.append(("DELETE", deal_id))
        self.pos.pop(deal_id)
        return {"dealStatus": "ACCEPTED", "level": self.bid}

    def activity(self, deal_id, since, until):
        assert until - since <= pd.Timedelta(days=1)
        return self.acts.get(deal_id, [])

    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]


def us(st):
    return st["maerkte"][SYM]


def lauf(w, k, st, jetzt, netz=None, **kw):
    return vb.run(k, st, utc(jetzt), vix_get=netz or Netz(w.vix), **kw)


def test_kauf_nach_dem_sprung_wie_im_test_mit_stop_vom_bid_und_ohne_ziel(w):
    tag = w.tage[0]
    s, t_e = w.test[tag], einstieg(w, tag)
    k = Konto(w, bid=kurs_um(w, t_e))
    st, log, fertig, blick = lauf(w, k, {}, t_e + MIN)
    tr = us(st)["trade"]
    stop = round(k.bid - s["sd"], 1)
    assert tr["richtung"] == 1 and tr["dist"] == pytest.approx(s["sd"], abs=1e-5) and tr["tag"] == tag
    assert tr["fassung"] == "vix_sprung_us" and tr["vix_aenderung"] == pytest.approx(0.15, abs=0.002)
    assert tr["entry"] == k.offer and tr["stop"] == stop and tr["spaet_min"] == 1.0 and tr["nach_18_min"] == 1.0
    assert k.posts() == [("POST", "/positions", {"epic": EPIC, "direction": "BUY", "size": vb.groesse(s["sd"], _q())[0],
                                                  "guaranteedStop": False, "stopLevel": stop})]
    assert k.calls[0] == ("konto", KONTO5) and k.account_id == HAUPT              # zurück aufs Hauptkonto
    assert tr["bis_utc"] == str(pd.Timestamp(s["t_max"])) and tr["satz_nacht"] == 0.065
    assert us(st)["letzter_tag"] == tag and [e["event"] for e in log] == ["Kauf eröffnet"]
    assert blick["maerkte"]["GRXEUR"]["wartet"] == "Markt zu" and st["maerkte"]["GRXEUR"].get("letzter_tag") is None
    st2, _, _, _ = lauf(w, k, st, t_e + 16 * MIN)                                 # zweiter Lauf, derselbe Tag
    assert len(k.posts()) == 1 and us(st2)["trade"]["dealId"] == tr["dealId"]


def test_nach_einem_freitag_mit_sprung_kauft_er_am_montag(w):
    t_e = einstieg(w, "2026-03-02")
    k = Konto(w, bid=kurs_um(w, t_e))
    st, _, _, _ = lauf(w, k, {}, t_e + MIN)
    assert len(k.posts()) == 1 and us(st)["trade"]["tag"] == "2026-03-02"


def test_ohne_sprung_ist_der_tag_ohne_kerzen_erledigt(w):
    tag = w.ohne[3]
    t0 = einstieg_ohne(w, tag)
    k = Konto(w, bid=kurs_um(w, t0))
    k.markt_auf = False                                            # auch geschlossene Märkte sind erledigt
    netz = Netz(w.vix)
    st, log, _, blick = lauf(w, k, {}, t0 + MIN, netz)
    assert not k.posts() and not k.abrufe and not log and len(netz.urls) == 1   # VIX einmal je Lauf, nicht je Markt
    for sym in vb.MAERKTE:
        m = st["maerkte"][sym]
        assert m["letzter_tag"] == tag and m["letzte_pruefung"]["ergebnis"].startswith("kein Trade: VIX")
        assert not m.get("ausgelassen")
    lauf(w, k, st, t0 + 16 * MIN, netz)
    assert len(netz.urls) == 1 and not k.abrufe                     # der Tag ist erledigt: kein neuer Abruf


def test_ausstieg_vor_15_55_new_york(w):
    tag = w.tage[0]
    t_e = einstieg(w, tag)
    k = Konto(w, bid=kurs_um(w, t_e))
    st, _, _, _ = lauf(w, k, {}, t_e + MIN)
    tr = us(st)["trade"]
    bis = pd.Timestamp(tr["bis_utc"])
    assert bis == vb.ausstieg(pd.Timestamp(tag), w.cfg)
    st, _, fertig, _ = lauf(w, k, st, bis - 16 * MIN)
    assert not fertig and us(st)["trade"]
    st, _, fertig, _ = lauf(w, k, st, bis - 14 * MIN)
    r = fertig[0]
    assert r["grund"] == "zeit" and ("DELETE", tr["dealId"]) in k.calls and us(st)["trade"] is None
    assert r["naechte"] == 0 and r["gebuehr_r"] == 0 and st["trades"] == 1 and st["summe_r"] == r["r"]
    assert r["r_roh"] == pytest.approx((k.bid - tr["entry"]) / tr["dist"], abs=1e-3) and r["fassung"] == "vix_sprung_us"


def test_stop_beim_broker_wird_gebucht_und_sonst_nach_einer_stunde_geschaetzt(w):
    tag = w.tage[0]
    t_e = einstieg(w, tag)
    k = Konto(w, bid=kurs_um(w, t_e))
    st, _, _, _ = lauf(w, k, {}, t_e + MIN)
    tr = us(st)["trade"]
    k.pos.pop(tr["dealId"])
    k.acts[tr["dealId"]] = [{"dateUTC": (t_e + 3 * pd.Timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S"),
                             "source": "SL", "type": "POSITION", "status": "ACCEPTED",
                             "details": {"level": tr["stop"], "actions": []}}]
    st2, _, fertig, _ = lauf(w, k, st, t_e + pd.Timedelta(hours=4))
    assert fertig[0]["grund"] == "stop" and fertig[0]["exit"] == tr["stop"] and "exit_geschaetzt" not in fertig[0]
    assert fertig[0]["r_roh"] == pytest.approx(-1.0, abs=0.02)
    k.acts = {}
    st2, log, fertig, _ = lauf(w, k, st, t_e + pd.Timedelta(hours=4))
    assert not fertig and log[0]["event"].startswith("Position beim Broker zu") and "Schlusskurs" in vb.status(st2)
    st3, _, fertig, _ = lauf(w, k, st2, t_e + pd.Timedelta(hours=5, minutes=1))
    assert fertig[0]["grund"] == "stop" and fertig[0]["exit_geschaetzt"] and us(st3)["trade"] is None


def test_sperren(w, monkeypatch):
    tag = w.tage[0]
    t_e = einstieg(w, tag)
    jetzt = t_e + MIN
    k = Konto(w, bid=kurs_um(w, t_e))
    k.fremd = [{"market": {"epic": EPIC}, "position": {"dealId": "FREMD", "level": 5000.0, "size": 0.1}},
               {"market": {"epic": "GOLD"}, "position": {"dealId": "PINE", "level": 2600.0, "size": 0.1}}]
    st, log, _, _ = lauf(w, k, {}, jetzt)
    assert us(st)["trade"] is None and not k.posts() and "fremde Position auf US500 im Konto" in log[-1]["gruende"]
    assert us(st)["fremd"] == ["FREMD"] and not [c for c in k.calls if c[0] == "DELETE"]
    assert us(st)["ausgelassen"] == {"sperre": 1}
    k = Konto(w, bid=kurs_um(w, t_e))
    k.fremd = [{"market": {"epic": "GOLD"}, "position": {"dealId": "PINE", "level": 2600.0, "size": 0.1}},
               {"market": {"epic": "US30"}, "position": {"dealId": "DOW", "level": 44000.0, "size": 0.1}}]
    lauf(w, k, {}, jetzt)                                                         # Gold und Dow stören nicht
    assert len(k.posts()) == 1
    k = Konto(w, bid=kurs_um(w, t_e))
    st, log, _, _ = lauf(w, k, {"pausiert": {"seit": "x", "grund": "y"}}, jetzt)
    assert not k.posts() and "Pause ab -25 R" in log[-1]["gruende"]
    k = Konto(w, bid=kurs_um(w, t_e), frei=10.0)                                  # zu wenig freies Geld
    st, log, _, _ = lauf(w, k, {}, jetzt)
    assert not k.posts() and any("des freien Gelds" in g for g in log[-1]["gruende"])
    k = Konto(w, bid=kurs_um(w, t_e), min_size=1.0)                               # kleinste Größe zu grob
    st, log, _, _ = lauf(w, k, {}, jetzt)
    assert not k.posts() and us(st)["ausgelassen"] == {"groesse": 1}
    monkeypatch.setattr(vb, "vorab_ok", lambda: False)
    k = Konto(w, bid=kurs_um(w, t_e))
    st, log, _, _ = lauf(w, k, {}, jetzt)
    assert not k.posts() and any("nicht festgelegt" in g for g in log[-1]["gruende"])


def test_margin_zaehlt_die_orders_aus_demselben_lauf(w, monkeypatch):
    """An einem Sprung-Tag kauft der Bot bis zu fünf Märkte in einem Lauf. Jede Order prüft die 20 % am freien Geld
    abzüglich der Margin, die seine Orders davor im selben Lauf schon binden."""
    t_e = einstieg(w, w.tage[0])
    laeufe, orig = [], vb.Lauf.__init__

    def merken(self, *a, **kw):
        orig(self, *a, **kw)
        laeufe.append(self)
    monkeypatch.setattr(vb.Lauf, "__init__", merken)
    k = Konto(w, bid=kurs_um(w, t_e))
    lauf(w, k, {}, t_e + MIN)
    size = k.posts()[0][2]["size"]
    assert laeufe[-1].gebunden > 0 and laeufe[-1].gebunden == pytest.approx(size * k.bid * 0.05 / EURUSD, rel=1e-9)

    def schon_gebunden(self, *a, **kw):
        orig(self, *a, **kw)
        self.gebunden = 899.0                                 # 900 € frei, davon 899 € schon von dieser Runde gebunden
    monkeypatch.setattr(vb.Lauf, "__init__", schon_gebunden)
    k = Konto(w, bid=kurs_um(w, t_e))
    st, log, _, _ = lauf(w, k, {}, t_e + MIN)
    assert not k.posts() and any("des freien Gelds (1 €)" in g for g in log[-1]["gruende"])
    assert us(st)["ausgelassen"] == {"sperre": 1}


def test_nie_auf_dem_hauptkonto_und_nie_ohne_konto(w, monkeypatch):
    t_e = einstieg(w, w.tage[0])
    k = Konto(w, bid=kurs_um(w, t_e), konto5=False)
    st, log, _, blick = lauf(w, k, {}, t_e + MIN)
    assert not [c for c in k.calls if c[0] in ("POST", "konto")] and "nicht gefunden" in blick["status"]
    monkeypatch.setattr(vb, "KONTO", "")
    k = Konto(w, bid=kurs_um(w, t_e))
    st, log, _, blick = lauf(w, k, {}, t_e + MIN)
    assert not k.calls and "journal/konten.json" in blick["status"]
    monkeypatch.setattr(vb, "KONTO", HAUPT)                                        # endet wie das Hauptkonto
    st, log, _, _ = lauf(w, Konto(w, bid=kurs_um(w, t_e)), {}, t_e + MIN)
    assert log[0]["event"] == "kein Konto"


def test_frist_markt_zu_und_trockenlauf(w):
    tag = w.tage[0]
    t_e = einstieg(w, tag)
    k = Konto(w, bid=kurs_um(w, t_e))
    st, _, _, _ = lauf(w, k, {}, t_e + 21 * MIN)                                  # Frist vorbei
    assert not k.posts() and us(st)["letzte_pruefung"]["ergebnis"].startswith("verfallen")
    assert us(st)["ausgelassen"] == {"verfallen": 1}
    k = Konto(w, bid=kurs_um(w, t_e))
    st, _, _, _ = lauf(w, k, {}, t_e + 16 * MIN)                                  # letzter Lauf in der Frist
    assert len(k.posts()) == 1 and us(st)["trade"]["spaet_min"] == 16.0
    k = Konto(w, bid=kurs_um(w, t_e))
    k.markt_auf = False
    st, _, _, blick = lauf(w, k, {}, t_e + MIN)
    assert not k.posts() and blick["maerkte"][SYM]["wartet"] == "Markt zu" and us(st).get("letzter_tag") is None
    k = Konto(w, bid=kurs_um(w, t_e))
    st, log, _, _ = lauf(w, k, {}, t_e + MIN, send_orders=False)
    assert not k.posts() and log[-1]["event"] == "würde kaufen" and us(st).get("letzter_tag") is None


def test_ohne_frischen_vix_wartet_der_bot_und_laesst_den_tag_dann_aus(w):
    tag = w.tage[0]
    t_e = einstieg(w, tag)
    alt = w.vix.drop(vb.erwartet(pd.Timestamp(tag)))                              # VIX vom Vortag noch nicht da
    k = Konto(w, bid=kurs_um(w, t_e))
    st, _, _, blick = lauf(w, k, {}, t_e + MIN, Netz(alt))
    assert not k.posts() and "noch nicht veröffentlicht" in blick["maerkte"][SYM]["wartet"]
    assert us(st).get("letzter_tag") is None
    st, _, _, _ = lauf(w, k, st, t_e + 16 * MIN, Netz(alt))                       # letzter Lauf der Frist
    assert not k.posts() and us(st)["letzter_tag"] == tag and us(st)["ausgelassen"] == {"vix_alt": 1}
    assert "kein Einstieg" in us(st)["letzte_pruefung"]["ergebnis"]
    k = Konto(w, bid=kurs_um(w, t_e))
    st, _, _, blick = lauf(w, k, {}, t_e + MIN, Netz(w.vix, fehler=True))         # Quelle nicht erreichbar
    assert not k.posts() and blick["maerkte"][SYM]["wartet"] == "VIX nicht lesbar"
    st, _, _, _ = lauf(w, k, st, t_e + 16 * MIN, Netz(w.vix, fehler=True))
    assert not k.posts() and us(st)["ausgelassen"] == {"vix_fehlt": 1}
    k = Konto(w, bid=kurs_um(w, t_e))
    st, _, _, _ = lauf(w, k, {}, t_e + 16 * MIN, Netz(alt))
    st, _, _, _ = lauf(w, k, st, t_e + 16 * MIN, Netz(w.vix))                     # derselbe Tag kommt nicht wieder
    assert not k.posts()


def test_order_ohne_bestaetigung_wird_uebernommen(w):
    t_e = einstieg(w, w.tage[0])
    k = Konto(w, bid=kurs_um(w, t_e))
    k.order_fehler = True
    st, _, _, _ = lauf(w, k, {}, t_e + MIN)
    assert len(k.posts()) == 1 and us(st)["trade"]["dealId"] == "D1"
    lauf(w, k, st, t_e + 16 * MIN)
    assert len(k.posts()) == 1


def test_abrufe_nur_im_einstieg_und_nur_am_sprung_tag(w):
    t_e = einstieg(w, w.tage[0])
    k = Konto(w, bid=kurs_um(w, t_e))
    netz = Netz(w.vix)
    st, _, _, blick = lauf(w, k, {}, t_e - pd.Timedelta(hours=3), netz)           # Nachmittag New York: nichts zu tun
    assert not k.abrufe and not netz.urls
    assert pd.Timestamp(blick["naechster_einstieg_utc"]) == vb.einstieg_ab(pd.Timestamp(w.tage[0]), w.cfg)
    lauf(w, k, {}, t_e + MIN, netz)
    assert len(netz.urls) == 1
    stunden = [a for a in k.abrufe if a[1] == "HOUR"]
    assert stunden and min(a[2] for a in stunden) >= pd.Timestamp(t_e) + MIN - pd.Timedelta(days=vb.TAGE_KERZEN)
    assert {a[0] for a in k.abrufe} == {f"/prices/{EPIC}"}                        # geschlossene Märkte: kein Abruf


def test_naechster_einstieg_ueberspringt_das_wochenende(w):
    k = Konto(w, bid=5000.0)
    _, _, _, blick = lauf(w, k, {}, pd.Timestamp("2026-03-06 21:00"))            # Freitag nach Schluss
    assert pd.Timestamp(blick["naechster_einstieg_utc"]) == vb.einstieg_ab(pd.Timestamp("2026-03-09"), w.cfg)


def test_schreiben(tmp_path, w):
    t_e = einstieg(w, w.tage[0])
    k = Konto(w, bid=kurs_um(w, t_e))
    st, log, fertig, blick = lauf(w, k, {}, t_e + MIN)
    j, c = tmp_path / "vix-sprung", tmp_path / "vix-sprung.json"
    assert vb.schreiben(st, log, fertig, blick, j, c)
    assert not vb.schreiben(st, [], [], blick, j, c)                              # nichts Neues, nichts geschrieben
    karte = json.loads(c.read_text(encoding="utf-8"))
    assert karte["bot"] == "vix-sprung" and karte["konto"] == "Account 5" and KONTO5 not in c.read_text()
    assert karte["offen"][0]["epic"] == EPIC and karte["zusammenfassung"]["urteil"].startswith("läuft (0 von 40")
    assert set(karte["ausgelassen"]) == set(vb.MAERKTE) and "NICHT bestanden" in karte["backtest"]
    assert karte["fassungen"]["UKXGBP"] == "vix_sprung_welt"
    for fremd in ("konten.json", "modell-indizes.json", "pine-k5.json"):
        with pytest.raises(RuntimeError):
            vb.schreiben(st, log, fertig, blick, j, tmp_path / fremd)


def test_bewertung():
    tr = ([{"r": 1.0, "markt": "SPXUSD", "fassung": "vix_sprung_us", "tag": "a", "pnl_eur": 5}] * 25
          + [{"r": -1.0, "markt": "GRXEUR", "fassung": "vix_sprung_welt", "tag": "b", "pnl_eur": -5}] * 15)
    b = vb.bewertung(tr)
    assert b["trades"] == 40 and b["pf_r"] == pytest.approx(25 / 15, abs=1e-3) and b["urteil"].startswith("bestanden")
    assert b["je_markt"]["GRXEUR"] == {"trades": 15, "summe_r": -15.0} and b["tage"] == 2
    assert b["je_fassung"] == {"vix_sprung_us": {"trades": 25, "summe_r": 25.0},
                               "vix_sprung_welt": {"trades": 15, "summe_r": -15.0}}
    assert vb.bewertung([{"r": -1.0}] * 15)["urteil"].startswith("Zwischencheck")


def test_mitnutzer_kennt_den_bot():
    from suche import mitnutzer
    b = {x["bot"]: x for x in mitnutzer.bots()}["vix-sprung"]
    assert b["konto_name"] == "Account 5" and b["neu"] and b["konto"] == KONTO5


def test_regeln_sind_versiegelt(monkeypatch):
    monkeypatch.undo()
    assert vb.vorab_ok(), "suche/VORAB_vix_sprung_bot.yaml braucht seine Prüfsumme im Protokoll"
    vorab = vb.VORAB.read_text(encoding="utf-8")
    assert vb.KONTO not in vorab and "Account 5" in vorab
    for wort in ("vix_sprung_us", "vix_sprung_welt", "-25 R", "Test NICHT", "Kandidat", "1,93", "0,85", "68",
                 "nach_trades: 40", "11:53 UTC", "VORAB_schatten", "21:11 New York"):
        assert wort in vorab, wort
    import yaml
    r = yaml.safe_load(vorab)["vix_sprung_bot"]
    assert r["bot"] == vb.BOT_ID
    assert r["groesse"]["risiko_eur"] == vb.RISIKO_EUR and r["groesse"]["margin_anteil"] == vb.MARGE_ANTEIL
    assert r["groesse"]["max_risiko_faktor"] == vb.MAX_RISIKO_FAKTOR
    assert r["ausfuehrung"]["frist_min"] == vb.FRIST.total_seconds() / 60
    assert r["ausfuehrung"]["vorlauf_tage"] == vb.TAGE_KERZEN and r["ausfuehrung"]["min_handelstage"] == vb.MIN_TAGE
    assert r["urteil"]["nach_trades"] == vb.URTEIL_NACH and r["urteil"]["pause_r"] == vb.PAUSE_R
    z = r["gegenprobe_zahlen"]
    assert all(z[m]["nur_bot"] == 0 and z[m]["nur_test"] == 0 and z[m]["gemeinsam"] == 68 for m in vb.MAERKTE)


def test_ablauf_im_workflow():
    wf = (ROOT / ".github" / "workflows" / "demo-bots.yml").read_text(encoding="utf-8")
    assert "python -m pytest -q tests/test_vix_sprung_bot.py" in wf and "python -m suche.vix_sprung_bot" in wf
    assert "touch .tests-ok/vix_sprung" in wf and "python -m suche.vix_sprung_bot --dry-run" in wf
