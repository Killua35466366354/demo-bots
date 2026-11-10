"""Scalping-Komitee, Schritt 2: sieben kurze Tagestrades zu festen Uhrzeiten aus der Recherche.

Regeln: suche/VORAB_scalping.yaml (versiegelt im Journal, bevor gerechnet wurde). Kirons Wunsch vom 10.11.2026 10:11 UTC.
Recherche: /mnt/project-files/strategie-suche/scalping-komitee/.

Kosten wie im VORAB: Bid-Kerzen, Long kauft zum Ask und verkauft zum Bid, Short umgekehrt. Stop und Ziel: berührt eine
Kerze beide, zählt der Stop; springt die Eröffnung über den Stop, zählt die Eröffnung. Haltekosten 5 % im Jahr für jede
Nacht über 22:00 UTC. Ergebnis mit Stop in R, ohne Stop in Prozent vom Einstiegskurs.

Aufruf: python -m suche.scalping [--daten ORDNER] [--m1 DATEI]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import yaml

from suche.pine5m import atr_rma
from suche.runde1 import journal_lines, last_value, sha256_text

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_scalping.yaml"
KEY = "VORAB_scalping sha256 "
TERMINE = ROOT / "gold" / "v2" / "termine.yaml"
DATEN = pathlib.Path("/mnt/project-files/strategie-suche/daten")
M1 = pathlib.Path("/mnt/project-files/strategie-suche/scalper/m1/USDJPY_1min.csv.gz")
ERGEBNIS = ROOT / "suche" / "ergebnis_scalping"

ZEITRAUM = ("2024-11-01", "2026-10-30 23:59")
HAELFTEN = (("2024-11-01", "2025-10-31 23:59"), ("2025-11-01", "2026-10-30 23:59"))
JAHR_2026 = ("2026-01-01", "2026-10-30 23:59")
KONTROLLE = ("2022-11-01", "2024-10-31 23:59")
KONTROLLE_TERMINE = ("2023-01-01", "2024-10-31 23:59")   # Termine und 1-Min.-Daten erst ab 2023-01
VORLAUF = pd.Timedelta(days=60)
SPREAD = {"EURUSD": 0.00010, "USDJPY": 0.012, "SPXUSD": 0.6, "NSXUSD": 1.8, "GRXEUR": 1.8, "XAUUSD": 0.50}
ROBUST = 1.5
SWAP_JAHR = 0.05
ATR_N = 14
FILTER_SPREAD_ATR = 0.07
FILTER_MINUTEN = 60
FILTER_TAGE = 14
ZUFALL_LAEUFE = 200
ZUFALL_SCHLAGEN = 0.90
SAAT = 20261110
MIN_TRADES, MIN_TRADES_TERMIN = 100, 30
MIN_HAELFTE = 20
ZIEL_R = 10.0
FED_SCHWELLE = 0.0020
FED_ATR = 0.5

NY, BERLIN, LONDON, TOKIO = "America/New_York", "Europe/Berlin", "Europe/London", "Asia/Tokyo"


def check_vorab() -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("VORAB_scalping.yaml passt nicht zur Prüfsumme im Journal. Erst versiegeln, dann rechnen.")
    return yaml.safe_load(text)["scalping"]


# ---------- Daten ----------

def lade(pfad: pathlib.Path, ab: str = KONTROLLE[0]) -> pd.DataFrame:
    df = pd.read_csv(pfad, parse_dates=["utc"], index_col="utc")
    df = df[df.index >= pd.Timestamp(ab) - VORLAUF]
    return df[~df.index.duplicated()].sort_index()


def termine(pfad: pathlib.Path = TERMINE) -> dict[str, list[pd.Timestamp]]:
    """Fed, CPI und NFP als UTC-Zeitpunkte (naiv), aus New Yorker Ortszeit mit Sommerzeit."""
    roh = yaml.safe_load(pfad.read_text(encoding="utf-8"))
    tz = roh.get("zeitzone", NY)
    out = {}
    for k in ("fomc", "cpi", "nfp"):
        uhr = roh[k]["uhrzeit"]
        out[k] = sorted(ortszeit(d, uhr, tz) for d in roh[k]["tage"])
    return out


def ortszeit(tag, uhr: str, tz: str) -> pd.Timestamp:
    """Datum + Ortszeit -> UTC (naiv), Sommerzeit inklusive."""
    return pd.Timestamp(f"{pd.Timestamp(tag).date()} {uhr}").tz_localize(tz).tz_convert("UTC").tz_localize(None)


@dataclass
class Markt:
    symbol: str
    df: pd.DataFrame
    spread: float
    minuten: int = 5
    t: pd.DatetimeIndex = field(init=False)

    def __post_init__(self):
        self.t = self.df.index
        self.o = self.df["open"].to_numpy(float)
        self.h = self.df["high"].to_numpy(float)
        self.l = self.df["low"].to_numpy(float)
        self.c = self.df["close"].to_numpy(float)
        self.atr = atr_rma(self.df, ATR_N).to_numpy(float)
        self.tn = self.t.to_numpy()
        self.n = len(self.df)

    def kerze(self, ts: pd.Timestamp) -> int:
        """Index der Kerze, die genau um ts eröffnet, sonst -1."""
        i = int(np.searchsorted(self.tn, np.datetime64(ts)))
        return i if i < self.n and self.tn[i] == np.datetime64(ts) else -1

    def ab(self, ts: pd.Timestamp, max_min: int = 60) -> int:
        """Erste Kerze ab ts (höchstens max_min später), sonst -1."""
        i = int(np.searchsorted(self.tn, np.datetime64(ts)))
        if i < self.n and self.tn[i] - np.datetime64(ts) <= np.timedelta64(max_min, "m"):
            return i
        return -1

    def spanne(self, ts: pd.Timestamp, minuten: int = FILTER_MINUTEN) -> float | None:
        a = int(np.searchsorted(self.tn, np.datetime64(ts - pd.Timedelta(minutes=minuten))))
        b = int(np.searchsorted(self.tn, np.datetime64(ts)))
        if b - a < max(1, (minuten // self.minuten) // 2):
            return None
        return float(self.h[a:b].max() - self.l[a:b].min())


# ---------- Ein Trade ----------

def naechte(t0: pd.Timestamp, t1: pd.Timestamp) -> int:
    """Wie oft 22:00 UTC zwischen Einstieg und Ausstieg liegt."""
    s = pd.Timedelta(hours=22)
    return int(((t1 - s).floor("D") - (t0 - s).floor("D")).days)


def trade(m: Markt, i0: int, ie: int, d: int, aus: str = "open", spread: float | None = None,
          stop: float | None = None, ziel: float | None = None, stop_abstand: float | None = None,
          ziel_abstand: float | None = None) -> dict | None:
    """Ein Trade ab Eröffnung der Kerze i0 in Richtung d (+1 Long, -1 Short).

    aus="open": raus zur Eröffnung der Kerze ie. aus="close": raus zum Schluss der Kerze ie.
    stop/ziel sind Kurse auf der Ausstiegsseite (Long: Bid, Short: Ask). Statt Kursen gehen auch Abstände vom
    Einstiegskurs (für die Zufallsläufe mit gleichem Stop- und Zielabstand).
    Rückgabe None, wenn der Einstieg schon jenseits des Stops liegt.
    """
    s = m.spread if spread is None else spread
    entry = m.o[i0] + s if d == 1 else m.o[i0]
    if stop_abstand is not None:
        stop = entry - d * stop_abstand
    if ziel_abstand is not None:
        ziel = entry + d * ziel_abstand
    seite = 0.0 if d == 1 else s          # Ausstiegskurs = Bid + seite
    if stop is not None:
        if d == 1 and m.o[i0] <= stop:
            return None
        if d == -1 and m.o[i0] + s >= stop:
            return None
    letzte = ie - 1 if aus == "open" else ie
    exit_px, grund, k_aus = None, "zeit", letzte
    for k in (range(i0, letzte + 1) if stop is not None or ziel is not None else ()):
        o, h, l = m.o[k] + seite, m.h[k] + seite, m.l[k] + seite
        if stop is not None:
            if k > i0 and (o <= stop if d == 1 else o >= stop):
                exit_px, grund, k_aus = o, "stop", k
                break
            if (l <= stop) if d == 1 else (h >= stop):
                exit_px, grund, k_aus = stop, "stop", k
                break
        if ziel is not None and ((h >= ziel) if d == 1 else (l <= ziel)):
            exit_px, grund, k_aus = ziel, "ziel", k
            break
    if exit_px is None:
        exit_px = (m.o[ie] if aus == "open" else m.c[ie]) + seite
        t1 = m.t[ie] if aus == "open" else m.t[ie] + pd.Timedelta(minutes=m.minuten)
    else:
        t1 = m.t[k_aus] + pd.Timedelta(minutes=m.minuten)
    pnl = d * (exit_px - entry)
    nacht = naechte(m.t[i0], t1)
    swap_px = nacht * SWAP_JAHR / 365 * entry
    if stop is not None:
        r_dist = abs(entry - stop)
        r = (pnl - swap_px) / r_dist
    else:
        r_dist = None
        r = 100 * (pnl - swap_px) / entry
    return {"t": m.t[i0], "i0": i0, "d": d, "r": float(r), "grund": grund, "naechte": nacht,
            "r_dist": r_dist, "ziel_dist": (abs(ziel - entry) if ziel is not None else None)}


# ---------- Wann/Wo-Filter ----------

def filter_ok(m: Markt, ts: pd.Timestamp, uhr: str, tz: str, i0: int) -> bool:
    """(a) Spread höchstens 7 % der ATR(14) vor dem Einstieg, (b) Spanne der letzten 60 Min. mindestens ihr Schnitt
    zur selben Ortszeit an den 14 Handelstagen davor."""
    atr = m.atr[i0 - 1] if i0 > 0 else np.nan
    if not np.isfinite(atr) or m.spread > FILTER_SPREAD_ATR * atr:
        return False
    jetzt = m.spanne(ts)
    if jetzt is None:
        return False
    tag = pd.Timestamp(ts).tz_localize("UTC").tz_convert(tz).normalize().tz_localize(None)
    vorher = []
    for k in range(1, 45):
        dk = tag - pd.Timedelta(days=k)
        if dk.weekday() >= 5:
            continue
        sp = m.spanne(ortszeit(dk, uhr, tz))
        if sp is not None:
            vorher.append(sp)
        if len(vorher) == FILTER_TAGE:
            break
    if len(vorher) < FILTER_TAGE:
        return False
    return jetzt >= float(np.mean(vorher))


# ---------- Kennzahlen ----------

def wochen(von: str, bis: str) -> float:
    return (pd.Timestamp(bis) - pd.Timestamp(von)) / pd.Timedelta(days=7)


def kennzahlen(trades: list[dict], von: str, bis: str) -> dict:
    a, b = pd.Timestamp(von), pd.Timestamp(bis)
    tr = sorted((t for t in trades if a <= t["t"] <= b), key=lambda t: t["t"])
    r = np.array([t["r"] for t in tr]) if tr else np.zeros(0)
    gew, ver = r[r > 0].sum(), -r[r < 0].sum()
    pf = round(float(gew / ver), 2) if ver > 0 else (99.0 if gew > 0 else 0.0)
    kum = np.r_[0.0, np.cumsum(r)]
    dd = float(np.max(np.maximum.accumulate(kum) - kum))
    gruende: dict[str, int] = {}
    for t in tr:
        gruende[t["grund"]] = gruende.get(t["grund"], 0) + 1
    return {"trades": len(tr), "je_woche": round(len(tr) / wochen(von, bis), 2), "pf": pf,
            "summe": round(float(r.sum()), 2), "schnitt": round(float(r.mean()), 4) if len(r) else None,
            "max_rueckgang": round(dd, 2), "trefferquote_pct": round(100 * float((r > 0).mean()), 1) if len(r) else None,
            "long_n": sum(1 for t in tr if t["d"] == 1), "short_n": sum(1 for t in tr if t["d"] == -1),
            "gruende": gruende}


def pf_von(r: np.ndarray) -> float:
    gew, ver = r[r > 0].sum(), -r[r < 0].sum()
    return float(gew / ver) if ver > 0 else (99.0 if gew > 0 else 0.0)


def im(trades: list[dict], von: str, bis: str) -> list[dict]:
    a, b = pd.Timestamp(von), pd.Timestamp(bis)
    return [t for t in trades if a <= t["t"] <= b]


def zufall_vergleich(m: Markt, trades: list[dict], rng: np.random.Generator, wiederhole) -> dict:
    """200 Läufe mit zufälliger Richtung zu denselben Zeiten (gleiche Abstände). Der Kandidat muss 90 % schlagen."""
    z = im(trades, *ZEITRAUM)
    if not z:
        return {"laeufe": ZUFALL_LAEUFE, "geschlagen_pct": 0.0, "bestanden": False, "zufall_pf_median": None}
    eigen = np.array([t["r"] for t in z])
    gegen = np.array([wiederhole(t) for t in z])          # Ergebnis der Gegenrichtung je Trade
    pf_k = pf_von(eigen)
    pfs = []
    for _ in range(ZUFALL_LAEUFE):
        tausch = rng.random(len(z)) < 0.5
        pfs.append(pf_von(np.where(tausch, gegen, eigen)))
    pfs = np.array(pfs)
    anteil = float((pf_k > pfs).mean())
    return {"laeufe": ZUFALL_LAEUFE, "geschlagen_pct": round(100 * anteil, 1), "bestanden": anteil >= ZUFALL_SCHLAGEN,
            "zufall_pf_median": round(float(np.median(pfs)), 2)}


def placebo_vergleich(kand: list[dict], placebo: list[dict]) -> dict:
    k, p = kennzahlen(kand, *ZEITRAUM), kennzahlen(placebo, *ZEITRAUM)
    return {"placebo_trades": p["trades"], "placebo_pf": p["pf"], "kandidat_pf": k["pf"], "bestanden": k["pf"] > p["pf"]}


def bewerte(name: str, symbol: str, einheit: str, termin: bool, rechne, vergleich, kontrolle=KONTROLLE) -> dict:
    """rechne(spread_faktor, von, bis) -> Trades. vergleich(trades_zeitraum) -> dict mit 'bestanden'."""
    tr = rechne(1.0, ZEITRAUM[0], ZEITRAUM[1])
    tr_rob = rechne(ROBUST, ZEITRAUM[0], ZEITRAUM[1])
    tr_k = rechne(1.0, kontrolle[0], kontrolle[1])
    v = {"zeitraum": kennzahlen(tr, *ZEITRAUM), "robust": kennzahlen(tr_rob, *ZEITRAUM),
         "haelfte_1": kennzahlen(tr, *HAELFTEN[0]), "haelfte_2": kennzahlen(tr, *HAELFTEN[1]),
         "jahr_2026": kennzahlen(tr, *JAHR_2026), "kontrolle": kennzahlen(tr_k, *kontrolle)}
    v["vergleich"] = vergleich(tr)
    ok, fehl = bestanden(v, termin)
    return {"variante": name, "markt": symbol, "einheit": einheit, "termin": termin, **v,
            "bestanden": ok, "verfehlt": fehl}


def bestanden(v: dict, termin: bool) -> tuple[bool, list[str]]:
    z, fehl = v["zeitraum"], []
    mind = MIN_TRADES_TERMIN if termin else MIN_TRADES
    if z["trades"] < mind:
        fehl.append(f"nur {z['trades']} Trades (mindestens {mind})")
    if z["pf"] < 1.2:
        fehl.append(f"Gewinnfaktor {z['pf']}")
    if v["robust"]["pf"] < 1.0:
        fehl.append(f"mit 1,5-fachem Spread {v['robust']['pf']}")
    for k, nm in (("jahr_2026", "2026"), ("kontrolle", "Kontrolle")):
        if v[k]["pf"] <= 1.0:
            fehl.append(f"{nm} {v[k]['pf']}")
    if v["haelfte_1"]["trades"] >= MIN_HAELFTE and v["haelfte_2"]["trades"] >= MIN_HAELFTE:
        for k, nm in (("haelfte_1", "1. Hälfte"), ("haelfte_2", "2. Hälfte")):
            if v[k]["pf"] <= 1.0:
                fehl.append(f"{nm} {v[k]['pf']}")
    if not v["vergleich"]["bestanden"]:
        fehl.append("Vergleich nicht bestanden")
    return not fehl, fehl


# ---------- Kalender ----------

def werktage(von: str, bis: str, tz: str) -> list[pd.Timestamp]:
    """Ortsdaten Mo bis Fr (naiv) zwischen von und bis."""
    return [d for d in pd.date_range(pd.Timestamp(von).normalize() - pd.Timedelta(days=3), pd.Timestamp(bis).normalize(),
                                     freq="D") if d.weekday() < 5]


def gotobi_tage(von: str, bis: str) -> set[pd.Timestamp]:
    """5., 10., 15., 20., 25. und letzter Wochentag des Monats; Samstag/Sonntag -> Freitag davor."""
    out = set()
    for mo in pd.period_range(pd.Timestamp(von) - pd.Timedelta(days=31), pd.Timestamp(bis), freq="M"):
        kandidaten = [pd.Timestamp(mo.year, mo.month, t) for t in (5, 10, 15, 20, 25)]
        letzter = pd.Timestamp(mo.year, mo.month, mo.days_in_month)
        while letzter.weekday() >= 5:
            letzter -= pd.Timedelta(days=1)
        kandidaten.append(letzter)
        for d in kandidaten:
            while d.weekday() >= 5:
                d -= pd.Timedelta(days=1)
            out.add(d)
    return out


def naechster_werktag(d: pd.Timestamp) -> pd.Timestamp:
    d = d + pd.Timedelta(days=1)
    while d.weekday() >= 5:
        d += pd.Timedelta(days=1)
    return d


def voriger_werktag(d: pd.Timestamp) -> pd.Timestamp:
    d = d - pd.Timedelta(days=1)
    while d.weekday() >= 5:
        d -= pd.Timedelta(days=1)
    return d


def ism_tage(von: str, bis: str) -> list[pd.Timestamp]:
    """ISM Industrie: erster Wochentag des Monats, 1. Januar zählt nicht (dann der nächste Wochentag)."""
    out = []
    for mo in pd.period_range(pd.Timestamp(von) - pd.Timedelta(days=31), pd.Timestamp(bis) + pd.Timedelta(days=31),
                              freq="M"):
        d = pd.Timestamp(mo.year, mo.month, 1)
        while d.weekday() >= 5 or (d.month == 1 and d.day == 1):
            d += pd.Timedelta(days=1)
        out.append(d)
    return out


# ---------- Kandidaten ----------

def fenster_trades(m: Markt, tage, tz: str, ein: str, raus: str, d_von, spread_f: float, filt: bool = False,
                   raus_folgetag: bool = False, aus: str = "open") -> list[dict]:
    """Ein Trade je Ortsdatum: Einstieg zur Eröffnung der Kerze 'ein', raus zur Eröffnung der Kerze 'raus'
    (aus="close": zum Schluss der Kerze 'raus'). d_von(tag, i0) -> Richtung oder 0."""
    out = []
    s = m.spread * spread_f
    for tag in tage:
        t0 = ortszeit(tag, ein, tz)
        t1 = ortszeit(naechster_werktag(tag) if raus_folgetag else tag, raus, tz)
        i0 = m.kerze(t0)
        if i0 < 0:
            continue
        ie = m.kerze(t1) if aus == "close" else m.ab(t1, 30)
        if ie <= i0:
            continue
        d = d_von(tag, i0)
        if not d:
            continue
        if filt and not filter_ok(m, t0, ein, tz, i0):
            continue
        tr = trade(m, i0, ie, d, aus=aus, spread=s)
        if tr:
            tr.update({"ie": ie, "aus": aus})
            out.append(tr)
    return out


def gegenrichtung(m: Markt):
    """Ergebnis desselben Trades in der Gegenrichtung (gleiche Zeit, gleicher Stop- und Zielabstand)."""
    def f(t: dict) -> float:
        g = trade(m, t["i0"], t["ie"], -t["d"], aus=t["aus"], stop_abstand=t["r_dist"],
                  ziel_abstand=t["ziel_dist"])
        if g is None:                       # kann bei Abständen nicht passieren, nur zur Sicherheit
            return 0.0
        return g["r"]
    return f


def kand_gotobi(m: Markt, rng) -> list[dict]:
    res = []
    for name, ein in (("gotobi_a", "03:00"), ("gotobi_b", "08:00")):
        def rechne(sf, von, bis, ein=ein, placebo=False):
            alle = werktage(von, bis, TOKIO)
            gt = gotobi_tage(von, bis)
            tage = [d for d in alle if (d not in gt) == placebo]
            return im(fenster_trades(m, tage, TOKIO, ein, "09:55", lambda t, i: 1, sf), von, bis)

        def vergleich(_tr, rechne=rechne):
            return placebo_vergleich(rechne(1.0, *ZEITRAUM), rechne(1.0, *ZEITRAUM, placebo=True))
        res.append(bewerte(name, m.symbol, "%", True, rechne, vergleich, KONTROLLE_TERMINE))
    return res


def kand_eurusd(m: Markt, rng) -> list[dict]:
    res = []
    for name, filt in (("eurusd_a", False), ("eurusd_a_f", True)):
        def rechne(sf, von, bis, filt=filt):
            tage = werktage(von, bis, NY)
            a = fenster_trades(m, tage, NY, "03:00", "11:00", lambda t, i: -1, sf, filt)
            b = fenster_trades(m, tage, NY, "11:00", "16:00", lambda t, i: 1, sf, filt)
            return im(a + b, von, bis)
        res.append(bewerte(name, m.symbol, "%", False, rechne,
                           lambda tr: zufall_vergleich(m, tr, rng, gegenrichtung(m))))

    def rechne_b(sf, von, bis):
        return im(fenster_trades(m, werktage(von, bis, LONDON), LONDON, "09:00", "13:00", lambda t, i: -1, sf), von, bis)
    res.append(bewerte("eurusd_b", m.symbol, "%", False, rechne_b,
                       lambda tr: zufall_vergleich(m, tr, rng, gegenrichtung(m))))
    return res


def kand_eroeffnung(m: Markt, tz: str, start: str, schluss: str, rng) -> list[dict]:
    res = []
    letzte = (pd.Timestamp(f"2000-01-01 {schluss}") - pd.Timedelta(minutes=5)).strftime("%H:%M")
    zweite = (pd.Timestamp(f"2000-01-01 {start}") + pd.Timedelta(minutes=5)).strftime("%H:%M")
    for name, filt in (("eroeffnung", False), ("eroeffnung_f", True)):
        def rechne(sf, von, bis, filt=filt):
            out = []
            s = m.spread * sf
            for tag in werktage(von, bis, tz):
                i1 = m.kerze(ortszeit(tag, start, tz))
                t0 = ortszeit(tag, zweite, tz)
                i0 = m.kerze(t0)
                ie = m.kerze(ortszeit(tag, letzte, tz))
                if min(i1, i0, ie) < 0 or i0 != i1 + 1 or ie <= i0:
                    continue
                if m.c[i1] == m.o[i1]:
                    continue
                d = 1 if m.c[i1] > m.o[i1] else -1
                stop = m.l[i1] if d == 1 else m.h[i1]
                entry = m.o[i0] + s if d == 1 else m.o[i0]
                if (d == 1 and m.o[i0] <= stop) or (d == -1 and m.o[i0] + s >= stop):
                    continue
                if filt and not filter_ok(m, t0, zweite, tz, i0):
                    continue
                ziel = entry + d * ZIEL_R * abs(entry - stop)
                tr = trade(m, i0, ie, d, aus="close", spread=s, stop=stop, ziel=ziel)
                if tr:
                    tr.update({"ie": ie, "aus": "close"})
                    out.append(tr)
            return im(out, von, bis)
        res.append(bewerte(name, m.symbol, "R", False, rechne,
                           lambda tr: zufall_vergleich(m, tr, rng, gegenrichtung(m))))
    return res


def kand_halbe_stunde(m: Markt, tz: str, schluss: str, rng, news_tage: set | None = None) -> list[dict]:
    """Letzte halbe Stunde: Richtung = Rendite vom Vortagsschluss bis zum Einstieg (bzw. bis 10:00 NY bei News)."""
    ein = (pd.Timestamp(f"2000-01-01 {schluss}") - pd.Timedelta(minutes=30)).strftime("%H:%M")
    letzte = (pd.Timestamp(f"2000-01-01 {schluss}") - pd.Timedelta(minutes=5)).strftime("%H:%M")

    def vortag_schluss(tag) -> float | None:
        d = tag
        for _ in range(5):
            d = voriger_werktag(d)
            i = m.kerze(ortszeit(d, letzte, tz))
            if i >= 0:
                return m.c[i]
        return None

    def richtung(tag, i0, bis_uhr=None):
        ref = vortag_schluss(tag)
        if ref is None:
            return 0
        if bis_uhr is None:
            jetzt = m.o[i0]
        else:
            j = m.kerze(ortszeit(tag, bis_uhr, tz))
            if j < 0:
                return 0
            jetzt = m.o[j]
        return int(np.sign(jetzt - ref))

    res = []
    if news_tage is None:
        for name, filt in (("halbe_stunde", False), ("halbe_stunde_f", True)):
            def rechne(sf, von, bis, filt=filt):
                return im(fenster_trades(m, werktage(von, bis, tz), tz, ein, letzte, richtung, sf, filt, aus="close"),
                          von, bis)
            res.append(bewerte(name, m.symbol, "%", False, rechne,
                               lambda tr: zufall_vergleich(m, tr, rng, gegenrichtung(m))))
    else:
        def rechne_n(sf, von, bis):
            tage = [d for d in werktage(von, bis, tz) if d in news_tage]
            return im(fenster_trades(m, tage, tz, ein, letzte, lambda t, i: richtung(t, i, "10:00"), sf, aus="close"),
                      von, bis)
        res.append(bewerte("news_halbe_stunde", m.symbol, "%", True, rechne_n,
                           lambda tr: zufall_vergleich(m, tr, rng, gegenrichtung(m)), KONTROLLE_TERMINE))
    return res


def kand_fed_fade(m: Markt, fed: list[pd.Timestamp], rng) -> list[dict]:
    def rechne(sf, von, bis):
        out = []
        s = m.spread * sf
        for T in fed:
            iv = m.kerze(T - pd.Timedelta(minutes=5))
            iT = m.kerze(T)
            i25 = m.kerze(T + pd.Timedelta(minutes=25))
            i0 = m.kerze(T + pd.Timedelta(minutes=30))
            ie = m.ab(T + pd.Timedelta(minutes=90), 30)
            if min(iv, iT, i25, i0, ie) < 0 or ie <= i0:
                continue
            vor = m.c[iv]
            bew = (m.c[i25] - vor) / vor
            if abs(bew) < FED_SCHWELLE:
                continue
            d = -1 if bew > 0 else 1
            atr = m.atr[iT - 1]
            if not np.isfinite(atr):
                continue
            if d == -1:
                stop = m.h[iT:i25 + 1].max() + FED_ATR * atr
            else:
                stop = m.l[iT:i25 + 1].min() - FED_ATR * atr
            tr = trade(m, i0, ie, d, aus="open", spread=s, stop=stop, ziel=vor)
            if tr:
                tr.update({"ie": ie, "aus": "open"})
                out.append(tr)
        return im(out, von, bis)
    return [bewerte("fed_fade", m.symbol, "R", True, rechne,
                    lambda tr: zufall_vergleich(m, tr, rng, gegenrichtung(m)), KONTROLLE_TERMINE)]


def kand_vor_der_zahl(m: Markt, ter: dict) -> list[dict]:
    """Long 15:55 NY am Wochentag vor NFP oder ISM, raus 5 Min. vor der Zahl. Nicht an Fed-Tagen."""
    fed_tage = {pd.Timestamp(t).tz_localize("UTC").tz_convert(NY).normalize().tz_localize(None) for t in ter["fomc"]}

    def zahl_tage(von, bis) -> dict[pd.Timestamp, str]:
        """Ortsdatum -> Ausstiegsuhrzeit (5 Min. vor der ersten Zahl des Tages)."""
        out: dict[pd.Timestamp, str] = {}
        for t in ter["nfp"]:
            d = pd.Timestamp(t).tz_localize("UTC").tz_convert(NY).normalize().tz_localize(None)
            out[d] = "08:25"
        for d in ism_tage(von, bis):
            out.setdefault(d, "09:55")
        return {d: u for d, u in out.items() if d not in fed_tage}

    def rechne(sf, von, bis, placebo=False):
        zt = zahl_tage(von, bis)
        out = []
        s = m.spread * sf
        for tag in werktage(von, bis, NY):
            folge = naechster_werktag(tag)
            if placebo:
                if folge in zt or folge in fed_tage:
                    continue
                uhren = ("08:25", "09:55")
            else:
                if folge not in zt:
                    continue
                uhren = (zt[folge],)
            i0 = m.kerze(ortszeit(tag, "15:55", NY))
            if i0 < 0:
                continue
            for u in uhren:
                ie = m.ab(ortszeit(folge, u, NY), 30)
                if ie <= i0:
                    continue
                tr = trade(m, i0, ie, 1, aus="open", spread=s)
                if tr:
                    tr.update({"ie": ie, "aus": "open"})
                    out.append(tr)
        return im(out, von, bis)

    def vergleich(_tr):
        return placebo_vergleich(rechne(1.0, *ZEITRAUM), rechne(1.0, *ZEITRAUM, placebo=True))
    return [bewerte("vor_der_zahl", m.symbol, "%", True, rechne, vergleich, KONTROLLE_TERMINE)]


# ---------- Lauf ----------

def rechne_alles(daten: pathlib.Path = DATEN, m1: pathlib.Path = M1) -> list[dict]:
    rng = np.random.default_rng(SAAT)
    ter = termine()
    news = set()
    for k in ("fomc", "cpi", "nfp"):
        for t in ter[k]:
            news.add(pd.Timestamp(t).tz_localize("UTC").tz_convert(NY).normalize().tz_localize(None))
    mk = {s: Markt(s, lade(daten / f"{s}_5min.csv.gz"), SPREAD[s]) for s in ("EURUSD", "SPXUSD", "NSXUSD", "GRXEUR",
                                                                              "XAUUSD")}
    usdjpy = Markt("USDJPY", lade(m1, KONTROLLE_TERMINE[0]), SPREAD["USDJPY"], minuten=1)
    res = []
    res += kand_gotobi(usdjpy, rng)
    res += kand_eurusd(mk["EURUSD"], rng)
    res += kand_eroeffnung(mk["GRXEUR"], BERLIN, "09:00", "17:30", rng)
    res += kand_eroeffnung(mk["SPXUSD"], NY, "09:30", "16:00", rng)
    for s, tz, schluss in (("SPXUSD", NY, "16:00"), ("NSXUSD", NY, "16:00"), ("GRXEUR", BERLIN, "17:30"),
                           ("XAUUSD", NY, "13:30")):
        res += kand_halbe_stunde(mk[s], tz, schluss, rng)
    for s in ("SPXUSD", "NSXUSD"):
        res += kand_halbe_stunde(mk[s], NY, "16:00", rng, news_tage=news)
    for s in ("SPXUSD", "NSXUSD"):
        res += kand_fed_fade(mk[s], ter["fomc"], rng)
    for s in ("SPXUSD", "NSXUSD"):
        res += kand_vor_der_zahl(mk[s], ter)
    return res


def bericht(res: list[dict]) -> str:
    z = ["# Scalping-Komitee Schritt 2: Ergebnis", "",
         "Regeln: suche/VORAB_scalping.yaml (versiegelt vor dem Rechnen). Zeitraum 01.11.2024 bis 30.10.2026, Kontrolle "
         "01.11.2022 bis 31.10.2024 (Termine und USD/JPY 1 Min. ab 2023). Mit Stop in R, ohne Stop in Prozent vom Einstieg.",
         "", "| Variante | Markt | Trades | je Woche | PF | Summe | 1,5x Spread | 1. Hälfte | 2. Hälfte | 2026 | Kontrolle "
         "| Vergleich | Urteil |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in res:
        v = r["vergleich"]
        if "geschlagen_pct" in v:
            vg = f"schlägt {v['geschlagen_pct']} % der Zufallsläufe (Median PF {v['zufall_pf_median']})"
        else:
            vg = f"Placebo PF {v['placebo_pf']} ({v['placebo_trades']} Trades)"
        e = r["einheit"]
        z.append(f"| {r['variante']} | {r['markt']} | {r['zeitraum']['trades']} | {r['zeitraum']['je_woche']} | "
                 f"{r['zeitraum']['pf']} | {r['zeitraum']['summe']} {e} | {r['robust']['pf']} | {r['haelfte_1']['pf']} | "
                 f"{r['haelfte_2']['pf']} | {r['jahr_2026']['pf']} | {r['kontrolle']['pf']} | {vg} | "
                 f"{'bestanden' if r['bestanden'] else 'durchgefallen: ' + '; '.join(r['verfehlt'])} |")
    ok = [r for r in res if r["bestanden"]]
    z += ["", f"Bestanden: {len(ok)} von {len(res)}." + (
        " " + ", ".join(f"{r['variante']} {r['markt']}" for r in ok) if ok else
        " Nach der Regel geht nichts live, außer Kiron will es ausdrücklich als reinen Demo-Test."), ""]
    return "\n".join(z)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--daten", type=pathlib.Path, default=DATEN)
    ap.add_argument("--m1", type=pathlib.Path, default=M1)
    a = ap.parse_args(argv)
    check_vorab()
    res = rechne_alles(a.daten, a.m1)
    ERGEBNIS.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n",
                                             encoding="utf-8")
    md = bericht(res)
    ERGEBNIS.with_suffix(".md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
