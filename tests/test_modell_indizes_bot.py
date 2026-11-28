"""Tests für suche/modell_indizes_bot.py: Der Bot sieht mit Stundenkerzen vom Broker und VIX und Renditen von Cboe und
vom US-Finanzministerium dieselben Einstiege, Stops und Ausstiege wie der Test der großen Runde (Fassung
modell_indizes) mit 5-Minuten-Kerzen und FRED-Reihen. Er handelt nur auf Account 6, höchstens einen Trade je Markt,
mit Stop beim Broker und ohne Ziel, und steigt vor 15:55 New York aus. Alle Kurse, Reihen, Gewichte und Kontonummern
hier sind erfunden."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from suche import grosse_runde as gr
from suche import modell_indizes_bot as mb
from suche import modell_indizes_gegenprobe as gp
from suche import rueckblick as rb
from suche.demo_bots import Quote

ROOT = Path(__file__).resolve().parents[1]
HAUPT = "111111113150"
KONTO6 = "111111116666"
MIN = pd.Timedelta(minutes=1)
SYM, EPIC = "SPXUSD", "US500"
SPREAD = 0.6
EURUSD = 1.1
VON, BIS = "2026-02-02", "2026-03-13"
REIHEN = ("VIXCLS", "VXVCLS", "DGS10", "DGS2")


def erfundene_kurse(von="2024-09-02", bis="2026-03-21", seed=7, start=5000.0) -> pd.DataFrame:
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


def schreibe_npz(df: pd.DataFrame, ordner: Path) -> None:
    ny = df.index.tz_localize("UTC").tz_convert(rb.NY).tz_localize(None)
    tag = (ny + pd.Timedelta(hours=7)).normalize()
    np.savez(ordner / f"{SYM}.npz", t=df.index.values.astype("datetime64[ns]"), o=df["open"].to_numpy(float),
             h=df["high"].to_numpy(float), l=df["low"].to_numpy(float), c=df["close"].to_numpy(float),
             sp=np.full(len(df), SPREAD), nymin=np.asarray(ny.hour * 60 + ny.minute, dtype=np.int32),
             tag=tag.values.astype("datetime64[D]"))


def erfundene_reihen(seed=11) -> dict[str, pd.Series]:
    """VIX, VIX3M und Renditen an jedem Werktag, auf zwei Stellen wie in den Quellen."""
    rng = np.random.default_rng(seed)
    tage = pd.bdate_range("2024-06-03", "2026-03-31")
    vix = 18 * np.exp(np.cumsum(rng.normal(0, 0.05, len(tage))))
    return {"VIXCLS": pd.Series(vix, tage).round(2),
            "VXVCLS": pd.Series(vix * (1.06 + rng.normal(0, 0.03, len(tage))), tage).round(2),
            "DGS10": pd.Series(4.2 + np.cumsum(rng.normal(0, 0.04, len(tage))), tage).round(2),
            "DGS2": pd.Series(3.8 + np.cumsum(rng.normal(0, 0.04, len(tage))), tage).round(2)}


class Netz:
    """Cboe und US-Finanzministerium zum Testen: liefert die erfundenen Reihen als CSV wie die echten Seiten."""

    def __init__(self, reihen: dict[str, pd.Series], fehler: bool = False):
        self.reihen, self.fehler, self.urls = reihen, fehler, []

    def __call__(self, url, timeout=None):
        self.urls.append(url)
        if self.fehler:
            raise RuntimeError("keine Verbindung")
        if "cboe" in url:
            s = self.reihen["VIXCLS" if "/VIX_History" in url else "VXVCLS"]
            zeilen = ["DATE,OPEN,HIGH,LOW,CLOSE"] + [f"{t:%m/%d/%Y},{v:.2f},{v:.2f},{v:.2f},{v:.2f}" for t, v in s.items()]
        else:
            jahr = int(url.split("field_tdr_date_value=")[1][:4])
            a, b = self.reihen["DGS10"], self.reihen["DGS2"]
            tage = [t for t in a.index.union(b.index) if t.year == jahr][::-1]       # neueste zuerst wie die echte Datei
            zeilen = ['Date,"1 Mo","2 Yr","10 Yr","30 Yr"'] + [
                f"{t:%m/%d/%Y},4.00,{b.get(t, np.nan):.2f},{a.get(t, np.nan):.2f},4.50" for t in tage]
        return SimpleNamespace(text="\n".join(zeilen) + "\n", raise_for_status=lambda: None)


@pytest.fixture(autouse=True)
def _welt(monkeypatch, request):
    monkeypatch.setattr(mb, "vorab_ok", lambda: True)
    monkeypatch.setattr(mb, "KONTO", KONTO6)
    if "w" in request.fixturenames:
        w = request.getfixturevalue("w")
        monkeypatch.setattr(mb, "lade_gewichte", lambda pruefen=True: w.gew)


@pytest.fixture(scope="module")
def w(tmp_path_factory):
    """Die erfundene Welt: Kurse, Reihen, Gewichte für 2026, der Markt des Tests und alle Signale des Tests im
    Fenster (so wie gr.regel_modell sie aus den Wahrscheinlichkeiten macht)."""
    ordner, fred = tmp_path_factory.mktemp("kurse"), tmp_path_factory.mktemp("fred")
    df = erfundene_kurse()
    schreibe_npz(df, ordner)
    reihen = erfundene_reihen()
    mb.fremd_schreiben(reihen, fred)
    cfg = mb.lade_cfg(pruefen=True)
    p, gruppe = mb.regel(cfg), mb.gruppe(cfg)
    m = gr.Markt(SYM, ordner, cfg, cfg["fenster"]["bis"])
    with mb.fred_ordner(fred):
        X, _, _ = gr.merkmale(m, cfg, p, gruppe)
    Xg = np.column_stack([X, mb.grundwerte(0, len(gruppe), len(X))])
    rng = np.random.default_rng(3)
    mittel, streu = np.nanmean(Xg, axis=0), np.nanstd(Xg, axis=0)
    par = {"jahr": 2026, "mittel": list(mittel), "streu": list(np.where(streu > 0, streu, 1.0)),
           "gewichte": [0.0] + list(rng.normal(0, 0.35, Xg.shape[1]))}
    gew = {"fassung": mb.FASSUNG, "jahre": {"2026": par}}
    q = np.array([mb.wahrscheinlichkeit(x, par) for x in Xg])
    rich = np.where(q >= 0.5 + p["abstand"], 1, np.where(q <= 0.5 - p["abstand"], -1, 0))
    rich[m.gtag < np.datetime64("2026-01-01")] = 0                  # nur Tage mit Gewichten
    sig = gr._tagestrades(m, cfg, rich, p["stop_atr"])
    test = {str(m.gtag[m.gpos[m.tix[s["i0"]]]])[:10]: s for s in sig}
    im = {t: s for t, s in test.items() if VON <= t <= BIS}
    return SimpleNamespace(ordner=ordner, fred=fred, df=df, reihen=reihen, cfg=cfg, p=p, m=m, gew=gew, sig=sig,
                           test=im, std=gp.stunden_aus(m), lang=sorted(t for t, s in im.items() if s["d"] > 0),
                           kurz=sorted(t for t, s in im.items() if s["d"] < 0))


def utc(t):
    return pd.Timestamp(t).tz_localize("UTC").to_pydatetime()


def einstieg(w, tag) -> pd.Timestamp:
    return pd.Timestamp(w.m.t[w.test[tag]["i0"]])


def kurs_um(w, t) -> float:
    return float(w.df["open"].loc[pd.Timestamp(t)])


# --------------------------------------------------------------------------------------------------------------------
# Bot und Test sehen dasselbe

def test_bot_sieht_dieselben_einstiege_stops_und_ausstiege_wie_der_test(w):
    res = gp.gegenprobe(SYM, w.ordner, w.cfg, w.gew, VON, BIS, test_signale=w.sig, fred=w.fred)
    assert res["test_signale"] == len(w.test) >= 10 and w.lang and w.kurz
    assert res["bot_signale"] == res["beide"] == len(w.test) == res["ausstieg_gleich"]
    assert res["richtung_anders"] == {} and res["nur_bot"] == {} and res["nur_test"] == {}
    assert res["bot_wartet"] == {} and res["stop_abweichung_rel"]["groesste"] < 1e-6


def test_wahrscheinlichkeit_wie_der_test():
    """Die Zahlen eines Jahres (gp.parameter) geben für jede Zeile dieses Jahres dieselbe Wahrscheinlichkeit wie
    gr.vorhersagen, das im Test zu jedem Jahr neu lernt."""
    rng = np.random.default_rng(1)
    tage = np.concatenate([np.repeat(np.arange(f"{j}-01-01", f"{j}-12-31", 1, dtype="datetime64[D]")[:300], 2)
                           for j in range(2019, 2025)])                # zwei Märkte, je Jahr 600 Zeilen
    X = rng.normal(0, 1, (len(tage), 6)) * [1, 2, 0.5, 1, 3, 1]
    X[rng.random(X.shape) < 0.02] = np.nan                       # Lücken bekommen das Mittel
    X[:, 5] = 0.0                                                # Spalte ohne Streuung
    y = (rng.random(len(tage)) < 1 / (1 + np.exp(-(0.4 * np.nan_to_num(X[:, 0]) - 0.2 * np.nan_to_num(X[:, 1]))))) * 1.0
    y[rng.random(len(y)) < 0.05] = np.nan
    p = {"min_lernzeilen": 1500, "min_lernjahre": 3, "strafe": 10.0}
    test = gr.vorhersagen(tage, X, y, p)
    jahre = tage.astype("datetime64[Y]").astype(int) + 1970
    for j in (2022, 2023, 2024):
        par = gp.parameter(tage, X, y, p, j)
        q = np.array([mb.wahrscheinlichkeit(x, par) for x in X[jahre == j]])
        assert np.nanmax(np.abs(q - test[jahre == j])) < 1e-9 and par["lernjahre"] == list(range(2019, j))
    assert gp.parameter(tage, X, y, p, 2021) is None and np.isnan(test[jahre == 2021]).all()   # zu wenig Lernjahre


def test_fassung_kommt_aus_der_versiegelten_runde(w):
    p, cfg = w.p, w.cfg
    assert p["art"] == "modell" and (p["rueckblick_tage"], p["rsi"], p["schnitt_tage"]) == ([1, 2, 5, 20], [2, 14],
                                                                                            [50, 200])
    assert (p["strafe"], p["abstand"], p["stop_atr"], p["min_lernzeilen"], p["min_lernjahre"]) == (10.0, 0.04, 2.0,
                                                                                                  1500, 3)
    assert cfg["varianten"][mb.FASSUNG] == {"regel": mb.FASSUNG, "maerkte": ["SPXUSD", "NSXUSD", "GRXEUR", "UKXGBP",
                                                                             "JPXJPY"]}
    assert mb.MAERKTE == {"SPXUSD": "US500", "NSXUSD": "US100", "GRXEUR": "DE40", "UKXGBP": "UK100", "JPXJPY": "J225"}
    assert (cfg["daten"]["pause_min"], cfg["tageshandel"]["toleranz_min"], cfg["tageshandel"]["aus_min"]) == (60, 540,
                                                                                                             955)
    with mb.fred_ordner(w.fred):
        _, _, namen = gr.merkmale(w.m, cfg, p, mb.gruppe(cfg))
    assert mb.merkmal_namen(cfg) == namen + ["markt_NSXUSD", "markt_GRXEUR", "markt_UKXGBP", "markt_JPXJPY"]


def test_gewichte_datei():
    """Die echte Datei: drei Jahre, jedes nur aus den Jahren davor gelernt, geprüft gegen den Test."""
    g = json.loads(mb.GEWICHTE.read_text(encoding="utf-8"))
    cfg = mb.lade_cfg(pruefen=True)
    assert g["fassung"] == mb.FASSUNG and g["maerkte"] == mb.gruppe(cfg) and g["merkmale"] == mb.merkmal_namen(cfg)
    assert sorted(g["jahre"]) == [str(j) for j in mb.JAHRE] == ["2024", "2025", "2026"]
    for j, par in g["jahre"].items():
        n = len(g["merkmale"])
        assert len(par["mittel"]) == len(par["streu"]) == n and len(par["gewichte"]) == n + 1
        assert max(par["lernjahre"]) == int(j) - 1 and par["lernzeilen"] >= 1500
        assert par["pruefung"]["zeilen"] > 1000 and par["pruefung"]["groesste_abweichung"] < 1e-9
        assert all(np.isfinite(par["mittel"])) and all(x > 0 for x in par["streu"])


# --------------------------------------------------------------------------------------------------------------------
# Zeit, VIX und Renditen

@pytest.mark.parametrize("tag, ab_utc, aus_utc", [
    ("2026-11-23", "2026-11-22 23:00", "2026-11-23 20:55"),      # Montag, Einstieg Sonntagabend, Winterzeit
    ("2026-07-07", "2026-07-06 22:00", "2026-07-07 19:55"),      # Sommerzeit
])
def test_zeiten_des_tests(w, tag, ab_utc, aus_utc):
    t = pd.Timestamp(tag)
    assert mb.einstieg_ab(t, w.cfg) == pd.Timestamp(ab_utc)
    assert mb.einstieg_bis(t, w.cfg) == pd.Timestamp(ab_utc) + pd.Timedelta(hours=9)
    assert mb.ausstieg(t, w.cfg) == pd.Timestamp(aus_utc)
    assert mb.tag_von(pd.Timestamp(ab_utc) + MIN) == t and mb.tag_von(pd.Timestamp(aus_utc)) == t
    assert mb.tagesende(pd.Timestamp(ab_utc) + MIN) == pd.Timestamp(aus_utc) + pd.Timedelta(minutes=65)


@pytest.mark.parametrize("name, tag, erwartet", [
    ("VIXCLS", "2026-11-24", "2026-11-23"),
    ("DGS10", "2026-11-23", "2026-11-20"),                       # Montag: Wert vom Freitag
    ("VXVCLS", "2026-11-27", "2026-11-25"),                      # Thanksgiving ohne Wert
    ("DGS2", "2026-12-28", "2026-12-24"),                        # Weihnachten ohne Wert
])
def test_erwarteter_wert(name, tag, erwartet):
    assert mb.erwartet(name, pd.Timestamp(tag)) == pd.Timestamp(erwartet)


def test_vix_und_renditen_wie_die_fred_dateien(w, tmp_path):
    netz = Netz(w.reihen)
    reihen = mb.fremd_holen(pd.Timestamp("2026-02-10 23:01"), netz)
    assert len(netz.urls) == 4 and sum("cboe" in u for u in netz.urls) == 2
    assert {"2025", "2026"} == {u.split("field_tdr_date_value=")[1][:4] for u in netz.urls if "treasury" in u}
    for name in REIHEN:
        s = reihen[name]
        assert s.index.is_monotonic_increasing and not s.index.has_duplicates
        assert (s == w.reihen[name].loc[s.index]).all()
    mb.fremd_schreiben(reihen, tmp_path)
    with mb.fred_ordner(tmp_path):
        werte, daten = gr.vor("DGS2", np.array(["2026-02-10"], dtype="datetime64[D]"))
    assert str(daten[0]) == "2026-02-09" and werte[0] == w.reihen["DGS2"]["2026-02-09"]
    assert gr.FRED != tmp_path                                     # danach wieder die Dateien des Tests
    stand = mb.fremd_stand(reihen, pd.Timestamp("2026-02-10"))
    assert all(s["frisch"] and s["datum"] == "2026-02-09" for s in stand.values())
    ohne = {**reihen, "VIXCLS": reihen["VIXCLS"].drop(pd.Timestamp("2026-02-09"))}
    assert [n for n, s in mb.fremd_stand(ohne, pd.Timestamp("2026-02-10")).items() if not s["frisch"]] == ["VIXCLS"]


def test_signal_haengt_nicht_an_der_zukunft(w):
    tag = w.lang[0]
    t_e = einstieg(w, tag)
    std = w.std[w.std.index < t_e.floor("h")]
    a = mb.signal(SYM, std, t_e, kurs_um(w, t_e), w.cfg, w.gew, fred=w.fred)
    verrueckt = {n: s.copy() for n, s in w.reihen.items()}
    for s in verrueckt.values():
        s[s.index >= pd.Timestamp(tag)] *= 3                       # Werte ab dem Handelstag selbst
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        mb.fremd_schreiben(verrueckt, Path(tmp))
        b = mb.signal(SYM, std, t_e, kurs_um(w, t_e), w.cfg, w.gew, fred=Path(tmp))
    assert a["ok"] and a["richtung"] == b["richtung"] == 1 and a["wahrscheinlichkeit"] == b["wahrscheinlichkeit"]
    c = mb.signal(SYM, w.std[w.std.index < t_e.floor("h") + pd.Timedelta(days=3)], t_e, kurs_um(w, t_e), w.cfg,
                  w.gew, fred=w.fred)                              # Kerzen nach dem Einstieg zählen nicht
    assert c["wahrscheinlichkeit"] == a["wahrscheinlichkeit"] and c["dist"] == a["dist"]


def test_signal_wartet_ohne_kerzen_und_ohne_gewichte(w):
    tag = w.lang[0]
    t_e = einstieg(w, tag)
    kurz = w.std[(w.std.index < t_e.floor("h")) & (w.std.index >= t_e - pd.Timedelta(days=200))]
    s = mb.signal(SYM, kurz, t_e, kurs_um(w, t_e), w.cfg, w.gew, fred=w.fred)
    assert s["warten"] and "zu wenig Kerzen" in s["ergebnis"] and not s["ok"]
    s = mb.signal(SYM, w.std[w.std.index < t_e.floor("h")], t_e, kurs_um(w, t_e), w.cfg, {"jahre": {}}, fred=w.fred)
    assert not s["ok"] and not s["warten"] and "keine Gewichte für 2026" in s["ergebnis"]
    s = mb.signal(SYM, w.std, t_e - pd.Timedelta(hours=2), kurs_um(w, t_e), w.cfg, w.gew, fred=w.fred)
    assert not s["ok"] and "außerhalb" in s["ergebnis"]


def _q(**kw):
    base = dict(bid=5000.0, offer=5000.6, tradeable=True, currency="USD", lot=1.0, min_size=0.01, size_step=0.01,
                margin_pct=5.0, decimals=1, min_dist=1.0, eur_rate=EURUSD)
    base.update(kw)
    return Quote(**base)


def test_groesse():
    assert mb.groesse(55.0, _q()) == (0.1, "")                    # 5 € = 5,50 $ / 55 Punkte = 0,1
    size, warum = mb.groesse(55.0, _q(min_size=1.0, size_step=1.0))
    assert size is None and "zu grob" in warum
    assert mb.groesse(55.0, _q(eur_rate=None))[0] is None


def test_konto_mit_gekuerzter_id_wird_ueber_die_volle_id_gefunden():
    kurz = "…" + KONTO6[-4:]
    daten = {"konten": [{"id": "…0001", "name": "Account 3"}, {"id": kurz, "name": "Account 6"}],
             "zuordnung": {"r6-london-gbpusd": KONTO6}, "haupt": HAUPT, "frei": []}
    assert mb.konto_id(daten) == KONTO6
    assert mb.konto_id({**daten, "zuordnung": {}}) == ""
    assert mb.konto_id({**daten, "konten": daten["konten"] + [{"id": "…7777", "name": "Account 6"}]}) == ""


def test_echtes_konto_steht_in_konten_json_und_ist_nie_das_hauptkonto():
    from gold.bot import konten
    k = mb.konto_id(json.loads((ROOT / "journal" / konten.DATEI).read_text(encoding="utf-8")))
    assert k and not k.endswith(mb.HAUPT_ENDUNG) and k.isdigit() and len(k) > 5


# --------------------------------------------------------------------------------------------------------------------
# Der Lauf auf dem Demokonto

class Antwort:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class Konto:
    """Capital.com zum Testen: Hauptkonto und Account 6. Kerzen nur für US500 aus der erfundenen Welt, die anderen
    vier Märkte sind zu."""

    def __init__(self, w, bid, konto6=True, frei=900.0):
        self.account_id = HAUPT
        self.w = w
        self.bid, self.offer = bid, bid + SPREAD
        self.konto6, self.frei, self.markt_auf = konto6, frei, True
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
        if self.konto6:
            out.append({"accountId": KONTO6, "balance": {"balance": 1000.0, "available": self.frei}})
        return out

    def switch_account(self, aid):
        self.calls.append(("konto", aid))
        self.account_id = aid

    def market(self, epic):
        if epic in mb.MAERKTE.values():
            auf = self.markt_auf and epic == EPIC
            return {"snapshot": {"bid": self.bid, "offer": self.offer, "decimalPlacesFactor": 1,
                                 "marketStatus": "TRADEABLE" if auf else "CLOSED"},
                    "instrument": {"currency": "USD", "lotSize": 1, "marginFactor": 5, "marginFactorUnit": "PERCENTAGE"},
                    "dealingRules": {"minDealSize": {"value": 0.01}, "minSizeIncrement": {"value": 0.01},
                                     "minStopOrProfitDistance": {"unit": "POINTS", "value": 1.0}}}
        assert epic == "EURUSD"
        return {"snapshot": {"bid": EURUSD, "offer": EURUSD}}

    def positions(self):
        assert self.account_id == KONTO6, "der Bot darf nur auf Account 6 Positionen lesen"
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
        if params["resolution"] == "MINUTE_5":
            df = df[df.index + pd.Timedelta(minutes=5) <= bis + pd.Timedelta(minutes=5)]
        return {"prices": [{"snapshotTimeUTC": t.strftime("%Y-%m-%dT%H:%M:%S"),
                            **{f"{n}Price": {"bid": float(x), "ask": float(x) + SPREAD}
                               for n, x in zip(("open", "high", "low", "close"), row)}}
                           for t, row in zip(df.index, df[mb.SPALTEN].to_numpy())]}

    def _request(self, method, path, json=None):
        assert self.account_id == KONTO6
        assert method == "POST" and path == "/positions"
        self.calls.append((method, path, json))
        self.nr += 1
        ref, deal = f"R{self.nr}", f"D{self.nr}"
        d = 1 if json["direction"] == "BUY" else -1
        level = self.offer if d > 0 else self.bid
        self.pos[deal] = {"dealId": deal, "epic": json["epic"], "level": level, "size": json["size"],
                          "direction": json["direction"], "stopLevel": json["stopLevel"]}
        self.refs[ref] = {"dealStatus": "ACCEPTED", "affectedDeals": [{"dealId": deal}], "level": level}
        if self.order_fehler:
            raise RuntimeError("Zeitüberschreitung")
        return Antwort({"dealReference": ref})

    def confirm(self, ref):
        return self.refs.get(ref, {"dealStatus": "ACCEPTED"})

    def close_position(self, deal_id):
        assert self.account_id == KONTO6
        self.calls.append(("DELETE", deal_id))
        p = self.pos.pop(deal_id)
        return {"dealStatus": "ACCEPTED", "level": self.bid if p.get("direction") == "BUY" else self.offer}

    def activity(self, deal_id, since, until):
        assert until - since <= pd.Timedelta(days=1)
        return self.acts.get(deal_id, [])

    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]


def us(st):
    return st["maerkte"][SYM]


def lauf(w, k, st, jetzt, netz=None, **kw):
    return mb.run(k, st, utc(jetzt), fremd_get=netz or Netz(w.reihen), **kw)


def test_kauf_wie_im_test_mit_stop_vom_bid_und_ohne_ziel(w):
    tag = w.lang[0]
    s, t_e = w.test[tag], einstieg(w, tag)
    k = Konto(w, bid=kurs_um(w, t_e))
    st, log, fertig, blick = lauf(w, k, {}, t_e + MIN)
    tr = us(st)["trade"]
    stop = round(k.bid - s["sd"], 1)
    assert tr["richtung"] == 1 and tr["dist"] == pytest.approx(s["sd"], abs=1e-5) and tr["tag"] == tag
    assert tr["entry"] == k.offer and tr["stop"] == stop and tr["spaet_min"] == 1.0 and tr["nach_18_min"] == 1.0
    assert k.posts() == [("POST", "/positions", {"epic": EPIC, "direction": "BUY", "size": mb.groesse(s["sd"], _q())[0],
                                                  "guaranteedStop": False, "stopLevel": stop})]
    assert k.calls[0] == ("konto", KONTO6) and k.account_id == HAUPT              # zurück aufs Hauptkonto
    assert tr["bis_utc"] == str(pd.Timestamp(s["t_max"])) and tr["satz_nacht"] == 0.065
    assert us(st)["letzter_tag"] == tag and [e["event"] for e in log] == ["Kauf eröffnet"]
    assert blick["maerkte"]["GRXEUR"]["wartet"] == "Markt zu"
    st2, _, _, _ = lauf(w, k, st, t_e + 16 * MIN)                                 # zweiter Lauf, derselbe Tag
    assert len(k.posts()) == 1 and us(st2)["trade"]["dealId"] == tr["dealId"]


def test_verkauf_wie_im_test(w):
    tag = w.kurz[0]
    s, t_e = w.test[tag], einstieg(w, tag)
    k = Konto(w, bid=kurs_um(w, t_e))
    st, _, _, _ = lauf(w, k, {}, t_e + MIN)
    tr = us(st)["trade"]
    assert tr["richtung"] == -1 and tr["entry"] == k.bid and tr["stop"] == round(k.bid + s["sd"], 1)
    assert k.posts()[0][2]["direction"] == "SELL" and tr["satz_nacht"] == 0.02


def test_ausstieg_vor_15_55_new_york(w):
    tag = w.lang[0]
    t_e = einstieg(w, tag)
    k = Konto(w, bid=kurs_um(w, t_e))
    st, _, _, _ = lauf(w, k, {}, t_e + MIN)
    tr = us(st)["trade"]
    bis = pd.Timestamp(tr["bis_utc"])
    assert bis == mb.ausstieg(pd.Timestamp(tag), w.cfg)
    st, _, fertig, _ = lauf(w, k, st, bis - 16 * MIN)
    assert not fertig and us(st)["trade"]
    st, _, fertig, _ = lauf(w, k, st, bis - 14 * MIN)
    r = fertig[0]
    assert r["grund"] == "zeit" and ("DELETE", tr["dealId"]) in k.calls and us(st)["trade"] is None
    assert r["naechte"] == 0 and r["gebuehr_r"] == 0 and st["trades"] == 1 and st["summe_r"] == r["r"]
    assert r["r_roh"] == pytest.approx((k.bid - tr["entry"]) / tr["dist"], abs=1e-3)


def test_stop_beim_broker_wird_gebucht_und_sonst_nach_einer_stunde_geschaetzt(w):
    tag = w.lang[0]
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
    assert not fertig and log[0]["event"].startswith("Position beim Broker zu") and "Schlusskurs" in mb.status(st2)
    st3, _, fertig, _ = lauf(w, k, st2, t_e + pd.Timedelta(hours=5, minutes=1))
    assert fertig[0]["grund"] == "stop" and fertig[0]["exit_geschaetzt"] and us(st3)["trade"] is None


def test_schluss_ohne_beleg_wird_nicht_gebucht_und_im_naechsten_lauf_wiederholt(w):
    """27.11.2026: Capital.com bestätigte den Zeitausstieg von US500 mit dem Kurs 0,24, die Position blieb offen."""
    tag = w.lang[0]
    t_e = einstieg(w, tag)
    k = Konto(w, bid=kurs_um(w, t_e))
    st, _, _, _ = lauf(w, k, {}, t_e + MIN)
    tr = us(st)["trade"]
    bis = pd.Timestamp(tr["bis_utc"])
    echt = k.close_position
    k.close_position = lambda deal_id: (k.calls.append(("DELETE", deal_id)) or {"dealStatus": "ACCEPTED", "level": 0.24})
    st, log, fertig, _ = lauf(w, k, st, bis - 14 * MIN)
    assert not fertig and st["trades"] == 0 and us(st)["trade"]["dealId"] == tr["dealId"]
    ev = [e for e in log if e["event"] == "Schluss nicht belegt"][0]
    assert ev["kurs_bestaetigt"] == 0.24 and ev["noch_offen"] is True and ev["kurs_lauf"] == k.bid
    assert not us(st).get("fremd")                                                # bleibt sein eigener Trade
    k.close_position = echt
    st, _, fertig, _ = lauf(w, k, st, bis - MIN)                                  # nächster Lauf schließt wieder
    assert fertig[0]["grund"] == "zeit" and fertig[0]["exit"] == k.bid and us(st)["trade"] is None
    assert fertig[0]["r_roh"] == pytest.approx((k.bid - tr["entry"]) / tr["dist"], abs=1e-3)


def test_schluss_mit_falschem_kurs_liest_den_kurs_aus_der_kontoaktivitaet(w):
    tag = w.lang[0]
    t_e = einstieg(w, tag)
    k = Konto(w, bid=kurs_um(w, t_e))
    st, _, _, _ = lauf(w, k, {}, t_e + MIN)
    tr = us(st)["trade"]
    bis = pd.Timestamp(tr["bis_utc"])
    k.close_position = lambda deal_id: (k.pos.pop(deal_id) and {"dealStatus": "ACCEPTED", "level": 0.24})
    st, log, fertig, _ = lauf(w, k, st, bis - 14 * MIN)                           # zu, aber mit falschem Kurs
    assert not fertig and [e for e in log if e["event"] == "Schluss nicht belegt"][0]["noch_offen"] is False
    k.acts[tr["dealId"]] = [{"dateUTC": (bis - 14 * MIN).strftime("%Y-%m-%dT%H:%M:%S"), "source": "USER",
                             "type": "POSITION", "status": "ACCEPTED",
                             "details": {"level": k.bid, "actions": [{"actionType": "POSITION_CLOSED"}]}}]
    st, _, fertig, _ = lauf(w, k, st, bis + MIN)
    assert fertig[0]["grund"] == "zeit" and fertig[0]["exit"] == k.bid and "exit_geschaetzt" not in fertig[0]


def test_falsch_gebuchte_offene_position_wird_wieder_gefuehrt_und_storniert(w, tmp_path):
    tag = w.lang[0]
    t_e = einstieg(w, tag)
    k = Konto(w, bid=kurs_um(w, t_e))
    st, log0, _, blick0 = lauf(w, k, {}, t_e + MIN)
    tr = us(st)["trade"]
    bis = pd.Timestamp(tr["bis_utc"])
    # so stand es nach dem 27.11.2026: gebucht mit dem Kurs 0,24, die Position liegt weiter beim Broker
    falsch = {**{x: tr[x] for x in ("id", "markt", "epic", "richtung", "tag", "dealId", "size", "entry", "stop",
                                    "dist", "wahrscheinlichkeit", "opened_utc", "spaet_min", "nach_18_min")},
              "seite": "Kauf", "exit": 0.24, "grund": "zeit", "closed_utc": (bis - 14 * MIN).isoformat(),
              "naechte": 0, "r_roh": -19.69, "gebuehr_r": 0.0, "r": -19.69, "pnl_waehrung": -72.32, "pnl_eur": -65.92}
    alt = {**st, "summe_r": -19.69, "trades": 1}
    alt["maerkte"] = {**st["maerkte"], SYM: {**us(st), "trade": None, "fremd": [tr["dealId"]]}}
    j, c = tmp_path / "modell-indizes", tmp_path / "modell-indizes.json"
    j.mkdir()
    (j / "trades.jsonl").write_text(json.dumps(falsch) + "\n", encoding="utf-8")
    k.markt_auf = False                                                           # Wochenende: Markt zu
    st2, log, fertig, _ = lauf(w, k, alt, bis + pd.Timedelta(hours=2), gebucht=[falsch])
    neu = us(st2)["trade"]
    assert not fertig and neu["dealId"] == tr["dealId"] and neu["bis_utc"] == tr["bis_utc"]
    assert neu["satz_nacht"] == tr["satz_nacht"] and neu["entry"] == tr["entry"] and neu["wieder_seit"]
    assert st2["summe_r"] == 0.0 and st2["trades"] == 0 and us(st2)["fremd"] == []
    assert [e["event"] for e in log if e["markt"] == SYM][0] == "Trade wieder geführt"
    assert st2["storniert"][0]["closed_utc"] == falsch["closed_utc"] and st2["storniert"][0]["r"] == -19.69
    assert not [x for x in k.calls if x[0] == "DELETE"]                           # Markt zu: noch kein Schluss
    st3, _, _, _ = lauf(w, k, st2, bis + pd.Timedelta(hours=2, minutes=15), gebucht=[falsch])
    assert len(st3["storniert"]) == 1 and us(st3)["trade"]["dealId"] == tr["dealId"]    # nur einmal
    k.markt_auf = True
    st4, _, fertig, blick = lauf(w, k, st3, bis + pd.Timedelta(hours=3), gebucht=[falsch])
    assert fertig[0]["dealId"] == tr["dealId"] and fertig[0]["exit"] == k.bid and fertig[0]["wieder_seit"]
    assert us(st4)["trade"] is None and st4["trades"] == 1 and st4["summe_r"] == fertig[0]["r"]
    assert mb.schreiben(st4, log, fertig, blick, j, c)
    zeilen = [json.loads(x) for x in (j / "trades.jsonl").read_text(encoding="utf-8").splitlines()]
    weg = [json.loads(x) for x in (j / "storniert.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [z["exit"] for z in zeilen] == [k.bid] and [z["exit"] for z in weg] == [0.24] and weg[0]["storniert"]
    assert mb.stornieren(st4, j) == 0                                             # zweiter Aufruf ändert nichts
    st5, log5, _, _ = lauf(w, k, st4, bis + pd.Timedelta(hours=4), gebucht=zeilen + weg)
    assert not [e for e in log5 if e["event"] == "Trade wieder geführt"]          # die Position ist jetzt zu


def test_fremde_position_wird_nie_wieder_gefuehrt(w):
    tag = w.lang[0]
    t_e = einstieg(w, tag)
    k = Konto(w, bid=kurs_um(w, t_e))
    k.fremd = [{"market": {"epic": EPIC}, "position": {"dealId": "FREMD", "level": 5000.0, "size": 0.1}}]
    gebucht = [{"id": "US500 x", "markt": SYM, "dealId": "ANDERS", "closed_utc": t_e.isoformat(), "r": -1.0,
                "richtung": 1, "tag": tag}]
    st, log, _, _ = lauf(w, k, {}, t_e + MIN, gebucht=gebucht)
    assert us(st)["trade"] is None and us(st)["fremd"] == ["FREMD"] and "storniert" not in st
    alt = [{**gebucht[0], "dealId": "FREMD", "closed_utc": (t_e - pd.Timedelta(days=31)).isoformat()}]
    st, log, _, _ = lauf(w, k, {}, t_e + MIN, gebucht=alt)                        # älter als 30 Tage
    assert us(st)["trade"] is None and "storniert" not in st


def test_sperren(w, monkeypatch):
    tag = w.lang[0]
    t_e = einstieg(w, tag)
    jetzt = t_e + MIN
    k = Konto(w, bid=kurs_um(w, t_e))
    k.fremd = [{"market": {"epic": EPIC}, "position": {"dealId": "FREMD", "level": 5000.0, "size": 0.1}},
               {"market": {"epic": "GOLD"}, "position": {"dealId": "GROSSBOX", "level": 2600.0, "size": 0.1}}]
    st, log, _, _ = lauf(w, k, {}, jetzt)
    assert us(st)["trade"] is None and not k.posts() and "fremde Position auf US500 im Konto" in log[-1]["gruende"]
    assert us(st)["fremd"] == ["FREMD"] and not [c for c in k.calls if c[0] == "DELETE"]
    k = Konto(w, bid=kurs_um(w, t_e))
    k.fremd = [{"market": {"epic": "GOLD"}, "position": {"dealId": "GROSSBOX", "level": 2600.0, "size": 0.1}}]
    lauf(w, k, {}, jetzt)                                                         # Gold der Groß-Box stört nicht
    assert len(k.posts()) == 1
    k = Konto(w, bid=kurs_um(w, t_e))
    st, log, _, _ = lauf(w, k, {"pausiert": {"seit": "x", "grund": "y"}}, jetzt)
    assert not k.posts() and "Pause ab -25 R" in log[-1]["gruende"]
    k = Konto(w, bid=kurs_um(w, t_e), frei=10.0)                                  # zu wenig freies Geld
    st, log, _, _ = lauf(w, k, {}, jetzt)
    assert not k.posts() and any("des freien Gelds" in g for g in log[-1]["gruende"])
    monkeypatch.setattr(mb, "vorab_ok", lambda: False)
    k = Konto(w, bid=kurs_um(w, t_e))
    st, log, _, _ = lauf(w, k, {}, jetzt)
    assert not k.posts() and any("nicht festgelegt" in g for g in log[-1]["gruende"])


def test_nie_auf_dem_hauptkonto_und_nie_ohne_konto(w, monkeypatch):
    t_e = einstieg(w, w.lang[0])
    k = Konto(w, bid=kurs_um(w, t_e), konto6=False)
    st, log, _, blick = lauf(w, k, {}, t_e + MIN)
    assert not [c for c in k.calls if c[0] in ("POST", "konto")] and "nicht gefunden" in blick["status"]
    monkeypatch.setattr(mb, "KONTO", "")
    k = Konto(w, bid=kurs_um(w, t_e))
    st, log, _, blick = lauf(w, k, {}, t_e + MIN)
    assert not k.calls and "journal/konten.json" in blick["status"]
    monkeypatch.setattr(mb, "KONTO", HAUPT)                                        # endet wie das Hauptkonto
    st, log, _, _ = lauf(w, Konto(w, bid=kurs_um(w, t_e)), {}, t_e + MIN)
    assert log[0]["event"] == "kein Konto"


def test_frist_markt_zu_und_trockenlauf(w):
    tag = w.lang[0]
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


def test_ohne_frische_vix_und_renditen_wartet_der_bot_und_laesst_den_tag_dann_aus(w):
    tag = w.lang[0]
    t_e = einstieg(w, tag)
    vortag = mb.erwartet("DGS10", pd.Timestamp(tag))
    alt = {**w.reihen, "DGS10": w.reihen["DGS10"].drop(vortag)}                  # Rendite vom Vortag noch nicht da
    k = Konto(w, bid=kurs_um(w, t_e))
    st, _, _, blick = lauf(w, k, {}, t_e + MIN, Netz(alt))
    assert not k.posts() and "noch nicht veröffentlicht: DGS10" in blick["maerkte"][SYM]["wartet"]
    assert us(st).get("letzter_tag") is None
    st, _, _, _ = lauf(w, k, st, t_e + 16 * MIN, Netz(alt))                       # letzter Lauf der Frist
    assert not k.posts() and us(st)["letzter_tag"] == tag and us(st)["ausgelassen"] == {"fremd_alt": 1}
    assert "kein Einstieg" in us(st)["letzte_pruefung"]["ergebnis"]
    k = Konto(w, bid=kurs_um(w, t_e))
    st, _, _, blick = lauf(w, k, {}, t_e + MIN, Netz(w.reihen, fehler=True))      # Quelle nicht erreichbar
    assert not k.posts() and blick["maerkte"][SYM]["wartet"] == "VIX oder Renditen nicht lesbar"
    st, _, _, _ = lauf(w, k, st, t_e + 16 * MIN, Netz(w.reihen, fehler=True))
    assert not k.posts() and us(st)["ausgelassen"] == {"fremd_fehlt": 1}
    k = Konto(w, bid=kurs_um(w, t_e))
    st, _, _, _ = lauf(w, k, {}, t_e + 16 * MIN, Netz(alt))
    st, _, _, _ = lauf(w, k, st, t_e + 16 * MIN, Netz(w.reihen))                  # derselbe Tag kommt nicht wieder
    assert not k.posts()


def test_ohne_gewichte_fuer_das_jahr_kein_trade(w, monkeypatch):
    monkeypatch.setattr(mb, "lade_gewichte", lambda pruefen=True: {"jahre": {"2025": w.gew["jahre"]["2026"]}})
    t_e = einstieg(w, w.lang[0])
    k = Konto(w, bid=kurs_um(w, t_e))
    st, _, _, _ = lauf(w, k, {}, t_e + MIN)
    assert not k.posts() and "keine Gewichte für 2026" in us(st)["letzte_pruefung"]["ergebnis"]
    monkeypatch.setattr(mb, "lade_gewichte", lambda pruefen=True: None)          # Prüfsumme passt nicht
    k = Konto(w, bid=kurs_um(w, t_e))
    st, _, _, blick = lauf(w, k, {}, t_e + MIN)
    assert not k.posts() and "Gewichte" in blick["maerkte"][SYM]["wartet"]


def test_order_ohne_bestaetigung_wird_uebernommen(w):
    t_e = einstieg(w, w.lang[0])
    k = Konto(w, bid=kurs_um(w, t_e))
    k.order_fehler = True
    st, _, _, _ = lauf(w, k, {}, t_e + MIN)
    assert len(k.posts()) == 1 and us(st)["trade"]["dealId"] == "D1"
    lauf(w, k, st, t_e + 16 * MIN)
    assert len(k.posts()) == 1


def test_abrufe_nur_im_einstieg(w):
    t_e = einstieg(w, w.lang[0])
    k = Konto(w, bid=kurs_um(w, t_e))
    netz = Netz(w.reihen)
    lauf(w, k, {}, t_e - pd.Timedelta(hours=3), netz)                             # Nachmittag New York: nichts zu tun
    assert not k.abrufe and not netz.urls
    lauf(w, k, {}, t_e + MIN, netz)
    assert len(netz.urls) == 4                                                    # einmal je Lauf, nicht je Markt
    stunden = [a for a in k.abrufe if a[1] == "HOUR"]
    assert stunden and min(a[2] for a in stunden) >= pd.Timestamp(t_e) + MIN - pd.Timedelta(days=mb.TAGE_KERZEN)


def test_freitagabend_kein_einstieg_und_naechster_am_sonntag(w):
    """Freitag ab 18:00 New York beginnt kein Handelstag (die Index-CFDs sind übers Wochenende zu): kein Abruf, keine
    Order, und das Cockpit nennt als nächsten Einstieg Sonntag 18:00 New York."""
    k = Konto(w, bid=5000.0)
    netz = Netz(w.reihen)
    freitag = pd.Timestamp("2026-03-20 22:05")                                    # Freitag 18:05 New York (Sommerzeit)
    st, log, _, blick = lauf(w, k, {}, freitag, netz)
    assert not k.abrufe and not netz.urls and not k.posts() and not log
    assert us(st).get("letzter_tag") is None
    assert blick["naechster_einstieg_utc"] == "2026-03-22 22:00:00"               # Sonntag 18:00 New York
    for jetzt in ("2026-03-21 12:00", "2026-03-22 21:00"):                          # Samstag, Sonntag vor 18:00
        assert lauf(w, k, {}, pd.Timestamp(jetzt), netz)[3]["naechster_einstieg_utc"] == "2026-03-22 22:00:00"
    assert lauf(w, k, {}, pd.Timestamp("2026-03-19 21:00"), netz)[3]["naechster_einstieg_utc"] == \
        "2026-03-19 22:00:00"                                                       # Donnerstag 17:00: heute Abend


def test_schreiben(tmp_path, w):
    t_e = einstieg(w, w.lang[0])
    k = Konto(w, bid=kurs_um(w, t_e))
    st, log, fertig, blick = lauf(w, k, {}, t_e + MIN)
    j, c = tmp_path / "modell-indizes", tmp_path / "modell-indizes.json"
    assert mb.schreiben(st, log, fertig, blick, j, c)
    assert not mb.schreiben(st, [], [], blick, j, c)                              # nichts Neues, nichts geschrieben
    karte = json.loads(c.read_text(encoding="utf-8"))
    assert karte["bot"] == "modell-indizes" and karte["konto"] == "Account 6" and KONTO6 not in c.read_text()
    assert karte["offen"][0]["epic"] == EPIC and karte["zusammenfassung"]["urteil"].startswith("läuft (0 von 40")
    assert set(karte["ausgelassen"]) == set(mb.MAERKTE) and "NICHT bestanden" in karte["backtest"]
    with pytest.raises(RuntimeError):
        mb.schreiben(st, log, fertig, blick, j, tmp_path / "konten.json")


def test_login_wartet_nach_rate_limit_und_gibt_dann_auf():
    from gold.bot.capital import CapitalError

    class Login:
        def __init__(self, fehler):
            self.fehler, self.versuche = list(fehler), 0

        def login(self):
            self.versuche += 1
            if self.fehler:
                raise self.fehler.pop(0)

    pausen = []
    rate = CapitalError("Rate-Limit erreicht für /session")
    c = Login([rate, rate])
    mb.anmelden(c, schlafen=pausen.append)
    assert c.versuche == 3 and pausen == list(mb.ANMELDEN_WARTEN)
    with pytest.raises(CapitalError):
        mb.anmelden(Login([rate, rate, rate]), schlafen=pausen.append)
    c = Login([CapitalError("POST /session -> 401: falsches Passwort")])
    with pytest.raises(CapitalError):
        mb.anmelden(c, schlafen=pausen.append)                   # nur das Rate-Limit wird wiederholt
    assert c.versuche == 1


def test_bewertung():
    tr = [{"r": 1.0, "markt": "SPXUSD", "pnl_eur": 5}] * 25 + [{"r": -1.0, "markt": "GRXEUR", "pnl_eur": -5}] * 15
    b = mb.bewertung(tr)
    assert b["trades"] == 40 and b["pf_r"] == pytest.approx(25 / 15, abs=1e-3) and b["urteil"].startswith("bestanden")
    assert b["je_markt"]["GRXEUR"] == {"trades": 15, "summe_r": -15.0}
    assert mb.bewertung([{"r": -1.0}] * 15)["urteil"].startswith("Zwischencheck")


def test_mitnutzer_kennt_den_bot():
    from suche import mitnutzer
    b = {x["bot"]: x for x in mitnutzer.bots()}["modell-indizes"]
    assert b["konto_name"] == "Account 6" and b["neu"] and b["konto"] == KONTO6


def test_regeln_sind_versiegelt(monkeypatch):
    monkeypatch.undo()
    assert mb.vorab_ok(), "suche/VORAB_modell_indizes_bot.yaml braucht seine Prüfsumme im Protokoll"
    vorab = mb.VORAB.read_text(encoding="utf-8")
    assert mb.KONTO not in vorab and "Account 6" in vorab
    for wort in (mb.FASSUNG, "-25 R", "Test NICHT", "Kandidat", "1,21", "0,94", "nach_trades: 40", "12:25 UTC",
                 "VORAB_schatten", "jahr_2027"):
        assert wort in vorab, wort
    import yaml
    r = yaml.safe_load(vorab)["modell_indizes_bot"]
    assert r["bot"] == mb.BOT_ID and r["gewichte"]["jahre"] == mb.JAHRE
    assert r["gewichte"]["sha256"] == mb._sha(mb.GEWICHTE.read_text(encoding="utf-8"))
    assert r["groesse"]["risiko_eur"] == mb.RISIKO_EUR and r["groesse"]["margin_anteil"] == mb.MARGE_ANTEIL
    assert r["groesse"]["max_risiko_faktor"] == mb.MAX_RISIKO_FAKTOR
    assert r["ausfuehrung"]["frist_min"] == mb.FRIST.total_seconds() / 60
    assert r["ausfuehrung"]["vorlauf_tage"] == mb.TAGE_KERZEN and r["ausfuehrung"]["min_handelstage"] == mb.MIN_TAGE
    assert r["urteil"]["nach_trades"] == mb.URTEIL_NACH and r["urteil"]["pause_r"] == mb.PAUSE_R
    z = r["gegenprobe_zahlen"]
    assert set(mb.MAERKTE) <= set(z) and all(z[m]["nur_bot"] == 0 and z[m]["richtung_anders"] == 0 for m in mb.MAERKTE)


def test_ablauf_im_workflow():
    wf = (ROOT / ".github" / "workflows" / "demo-bots.yml").read_text(encoding="utf-8")
    assert "python -m pytest -q tests/test_modell_indizes_bot.py" in wf and "python -m suche.modell_indizes_bot" in wf
    assert "touch .tests-ok/modell_indizes" in wf and "python -m suche.modell_indizes_bot --dry-run" in wf
