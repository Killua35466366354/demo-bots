"""Scalping-Komitee, Runde 2b: die Regeln aus Schritt 2 auf weiteren Märkten, auf 1-, 5- und 15-Min.-Kerzen und in
anderen Spielarten, mit Zufalls-Gegenprobe.

Regeln: suche/VORAB_scalping2.yaml (versiegelt im Journal, bevor gerechnet wurde). Kirons Wort vom 10.11.2026 11:11 UTC
("wo anders und auf andere weise ... so viele trades wie möglich") und 11:13 UTC ("1, 5 oder 15min chart").
Kosten, Kalender und Kennzahlen kommen aus suche/scalping.py. Neu ist nur der schnellere Stop-/Ziel-Check (gleiche
Regeln, mit numpy statt Schleife; tests/test_scalping2.py prüft, dass beide dasselbe rechnen).

Aufruf: python -m suche.scalping2 [--daten ORDNER] [--m1 ORDNER]
"""
from __future__ import annotations

import argparse
import functools
import json
import pathlib

import numpy as np
import pandas as pd
import yaml

from suche import scalping as sc
from suche.runde1 import journal_lines, last_value, sha256_text

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_scalping2.yaml"
KEY = "VORAB_scalping2 sha256 "
DATEN = sc.DATEN
M1 = sc.M1.parent
ERGEBNIS = ROOT / "suche" / "ergebnis_scalping2"

ZEITRAUM, HAELFTEN, JAHR_2026 = sc.ZEITRAUM, sc.HAELFTEN, sc.JAHR_2026
KONTROLLE, KONTROLLE_TERMINE = sc.KONTROLLE, sc.KONTROLLE_TERMINE
NY, BERLIN, LONDON, TOKIO = sc.NY, sc.BERLIN, sc.LONDON, sc.TOKIO
ROBUST = 1.5
MIN_TRADES, MIN_TRADES_TERMIN, MIN_HAELFTE = 100, 30, 20
PF_MIN, PF_KONTROLLE, ZUFALL_PCT = 1.2, 1.1, 95.0
ZUFALL_LAEUFE, SAAT = 200, 20261110
NEWS_ATR, NEWS_STOP_ATR = 2.0, 0.5
FX = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY", "EURCHF",
      "AUDNZD", "GBPNZD"]
INDIZES = ["SPXUSD", "NSXUSD", "GRXEUR", "UKXGBP", "JPXJPY"]
ALLE = FX + ["XAUUSD", "XAGUSD", "WTIUSD"] + INDIZES
GOTOBI = ["USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY"]


def spreads() -> dict[str, float]:
    from suche.pine5m import EXTRA
    r1 = yaml.safe_load((ROOT / "suche" / "VORAB.yaml").read_text(encoding="utf-8"))["runde_1"]["maerkte"]
    out = {m["symbol"]: float(m["spread"]) for m in r1}
    out.update({m["symbol"]: float(m["spread"]) for m in EXTRA})
    out.update(sc.SPREAD)
    out.update({"AUDJPY": 0.02, "CADJPY": 0.025})
    return out


def sitzung(sym: str) -> tuple[str, str, object]:
    """(Zeitzone, Start, Schluss); Schluss ist eine Uhrzeit oder eine Funktion des Ortsdatums."""
    if sym in ("SPXUSD", "NSXUSD"):
        return NY, "09:30", "16:00"
    if sym == "GRXEUR":
        return BERLIN, "09:00", "17:30"
    if sym == "UKXGBP":
        return LONDON, "08:00", "16:30"
    if sym == "JPXJPY":
        return TOKIO, "09:00", lambda tag: "15:30" if tag >= pd.Timestamp("2024-11-05") else "15:00"
    if sym == "WTIUSD":
        return NY, "09:00", "14:30"
    return LONDON, "08:00", "16:00"


def schluss_von(schluss, tag) -> str:
    return schluss(tag) if callable(schluss) else schluss


def check_vorab() -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("VORAB_scalping2.yaml passt nicht zur Prüfsumme im Journal. Erst versiegeln, dann rechnen.")
    return yaml.safe_load(text)["scalping2"]


@functools.lru_cache(maxsize=None)
def oz(tag: pd.Timestamp, uhr: str, tz: str) -> pd.Timestamp:
    return sc.ortszeit(tag, uhr, tz)


def minus(uhr: str, minuten: int) -> str:
    return (pd.Timestamp(f"2000-01-01 {uhr}") - pd.Timedelta(minutes=minuten)).strftime("%H:%M")


def zu_15(df: pd.DataFrame) -> pd.DataFrame:
    return df.resample("15min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


# ---------- ein Trade, schnell ----------

def trade_v(m: sc.Markt, i0: int, ie: int, d: int, aus: str = "open", spread: float | None = None,
            stop: float | None = None, ziel: float | None = None, stop_abstand: float | None = None,
            ziel_abstand: float | None = None) -> dict | None:
    """Gleiche Regeln wie scalping.trade (Stop vor Ziel in derselben Kerze, Lücke über den Stop zählt die Eröffnung)."""
    s = m.spread if spread is None else spread
    entry = m.o[i0] + s if d == 1 else m.o[i0]
    if stop_abstand is not None:
        stop = entry - d * stop_abstand
    if ziel_abstand is not None:
        ziel = entry + d * ziel_abstand
    seite = 0.0 if d == 1 else s
    if stop is not None and ((d == 1 and m.o[i0] <= stop) or (d == -1 and m.o[i0] + s >= stop)):
        return None
    letzte = ie - 1 if aus == "open" else ie
    exit_px, grund, k_aus = None, "zeit", letzte
    if stop is not None or ziel is not None:
        o = m.o[i0:letzte + 1] + seite
        h = m.h[i0:letzte + 1] + seite
        l = m.l[i0:letzte + 1] + seite
        n = len(o)
        ks = kt = n
        if stop is not None:
            hit = (l <= stop) if d == 1 else (h >= stop)
            ks = int(np.argmax(hit)) if hit.any() else n
        if ziel is not None:
            hit = (h >= ziel) if d == 1 else (l <= ziel)
            kt = int(np.argmax(hit)) if hit.any() else n
        if ks < n and ks <= kt:
            gap = ks > 0 and ((o[ks] <= stop) if d == 1 else (o[ks] >= stop))
            exit_px, grund, k_aus = (o[ks] if gap else stop), "stop", i0 + ks
        elif kt < n:
            exit_px, grund, k_aus = ziel, "ziel", i0 + kt
    if exit_px is None:
        exit_px = (m.o[ie] if aus == "open" else m.c[ie]) + seite
        t1 = m.t[ie] if aus == "open" else m.t[ie] + pd.Timedelta(minutes=m.minuten)
    else:
        t1 = m.t[k_aus] + pd.Timedelta(minutes=m.minuten)
    pnl = d * (exit_px - entry)
    nacht = sc.naechte(m.t[i0], t1)
    swap_px = nacht * sc.SWAP_JAHR / 365 * entry
    if stop is not None:
        r_dist = abs(entry - stop)
        r = (pnl - swap_px) / r_dist
    else:
        r_dist = None
        r = 100 * (pnl - swap_px) / entry
    return {"t": m.t[i0], "i0": i0, "ie": ie, "aus": aus, "d": d, "r": float(r), "grund": grund,
            "r_dist": r_dist, "ziel_dist": (abs(ziel - entry) if ziel is not None else None)}


def mit_gegen(m: sc.Markt, tr: dict | None, s: float) -> dict | None:
    """Hängt das Ergebnis desselben Trades in Gegenrichtung an (gleiche Zeit, gleicher Stop- und Zielabstand)."""
    if tr is None:
        return None
    g = trade_v(m, tr["i0"], tr["ie"], -tr["d"], tr["aus"], s, stop_abstand=tr["r_dist"], ziel_abstand=tr["ziel_dist"])
    tr["r_gegen"] = g["r"] if g else 0.0
    return tr


# ---------- Familien ----------

def eroeffnung(m: sc.Markt, sym: str, variante: str, sf: float, von: str, bis: str) -> list[dict]:
    tz, start, schluss = sitzung(sym)
    tf = m.minuten
    zweite = (pd.Timestamp(f"2000-01-01 {start}") + pd.Timedelta(minutes=tf)).strftime("%H:%M")
    s = m.spread * sf
    out = []
    for tag in sc.werktage(von, bis, tz):
        i1 = m.kerze(oz(tag, start, tz))
        i0 = m.kerze(oz(tag, zweite, tz))
        if i1 < 0 or i0 != i1 + 1:
            continue
        ende = oz(tag, schluss_von(schluss, tag), tz)
        ie = int(np.searchsorted(m.tn, np.datetime64(ende))) - 1
        if ie <= i0 or m.t[ie] < ende - pd.Timedelta(minutes=60):
            continue
        if m.c[i1] == m.o[i1]:
            continue
        d = 1 if m.c[i1] > m.o[i1] else -1
        stop = m.l[i1] if d == 1 else m.h[i1]
        if (d == 1 and m.o[i0] <= stop) or (d == -1 and m.o[i0] + s >= stop):
            continue
        entry = m.o[i0] + s if d == 1 else m.o[i0]
        dist = abs(entry - stop)
        if variante == "folgen_10r":
            tr = trade_v(m, i0, ie, d, "close", s, stop=stop, ziel=entry + d * 10 * dist)
        elif variante == "folgen_2r":
            tr = trade_v(m, i0, ie, d, "close", s, stop=stop, ziel=entry + d * 2 * dist)
        else:                                   # gegen_2r
            tr = trade_v(m, i0, ie, -d, "close", s, stop_abstand=dist, ziel_abstand=2 * dist)
        tr = mit_gegen(m, tr, s)
        if tr:
            out.append(tr)
    return sc.im(out, von, bis)


def halbe_stunde(m: sc.Markt, sym: str, variante: str, sf: float, von: str, bis: str) -> list[dict]:
    tz, _, schluss = sitzung(sym)
    s = m.spread * sf
    out = []

    def vortag(tag):
        d = tag
        for _ in range(5):
            d = sc.voriger_werktag(d)
            i = m.kerze(oz(d, minus(schluss_von(schluss, d), 5), tz))
            if i >= 0:
                return m.c[i]
        return None

    for tag in sc.werktage(von, bis, tz):
        sch = schluss_von(schluss, tag)
        i0 = m.kerze(oz(tag, minus(sch, 30), tz))
        ie = m.kerze(oz(tag, minus(sch, 5), tz))
        if i0 < 0 or ie <= i0:
            continue
        ref = vortag(tag)
        if ref is None:
            continue
        d = int(np.sign(m.o[i0] - ref)) * (1 if variante == "folgen" else -1)
        if not d:
            continue
        tr = mit_gegen(m, trade_v(m, i0, ie, d, "close", s), s)
        if tr:
            out.append(tr)
    return sc.im(out, von, bis)


def news(m: sc.Markt, variante: str, termine: list[pd.Timestamp], sf: float, von: str, bis: str) -> list[dict]:
    s = m.spread * sf
    out = []
    a, b = pd.Timestamp(von), pd.Timestamp(bis)
    for T in termine:
        if not (a - pd.Timedelta(days=1) <= T <= b + pd.Timedelta(days=1)):
            continue
        iT = m.kerze(T)
        i0 = m.kerze(T + pd.Timedelta(minutes=30))
        ie = m.ab(T + pd.Timedelta(minutes=90), 30)
        if min(iT, i0, ie) < 1 or ie <= i0 or i0 <= iT:
            continue
        atr = m.atr[iT - 1]
        if not np.isfinite(atr) or atr <= 0:
            continue
        ref = m.o[iT]
        bew = (m.o[i0] - ref) / atr
        if abs(bew) < NEWS_ATR:
            continue
        if variante == "news_gegen":
            d = -1 if bew > 0 else 1
            stop = (m.h[iT:i0].max() + NEWS_STOP_ATR * atr) if d == -1 else (m.l[iT:i0].min() - NEWS_STOP_ATR * atr)
            tr = trade_v(m, i0, ie, d, "open", s, stop=stop, ziel=ref)
        else:
            d = 1 if bew > 0 else -1
            tr = trade_v(m, i0, ie, d, "open", s, stop=ref)
        tr = mit_gegen(m, tr, s)
        if tr:
            out.append(tr)
    return sc.im(out, von, bis)


def gotobi(m: sc.Markt, variante: str, sf: float, von: str, bis: str, placebo: bool = False) -> list[dict]:
    ein = "03:00" if variante == "gotobi_a" else "08:00"
    gt = sc.gotobi_tage(von, bis)
    s = m.spread * sf
    out = []
    for tag in sc.werktage(von, bis, TOKIO):
        if (tag in gt) == placebo:
            continue
        i0 = m.kerze(oz(tag, ein, TOKIO))
        ie = m.ab(oz(tag, "09:55", TOKIO), 30)
        if i0 < 0 or ie <= i0:
            continue
        tr = trade_v(m, i0, ie, 1, "open", s)
        if tr:
            out.append(tr)
    return sc.im(out, von, bis)


def vor_der_zahl(m: sc.Markt, ter: dict, sf: float, von: str, bis: str, placebo: bool = False) -> list[dict]:
    fed = {pd.Timestamp(t).tz_localize("UTC").tz_convert(NY).normalize().tz_localize(None) for t in ter["fomc"]}
    zt: dict[pd.Timestamp, str] = {}
    for t in ter["nfp"]:
        zt[pd.Timestamp(t).tz_localize("UTC").tz_convert(NY).normalize().tz_localize(None)] = "08:25"
    for d in sc.ism_tage(von, bis):
        zt.setdefault(d, "09:55")
    zt = {d: u for d, u in zt.items() if d not in fed}
    s = m.spread * sf
    out = []
    for tag in sc.werktage(von, bis, NY):
        folge = sc.naechster_werktag(tag)
        if placebo:
            if folge in zt or folge in fed:
                continue
            uhren = ("08:25", "09:55")
        elif folge in zt:
            uhren = (zt[folge],)
        else:
            continue
        i0 = m.kerze(oz(tag, "15:55", NY))
        if i0 < 0:
            continue
        for u in uhren:
            ie = m.ab(oz(folge, u, NY), 30)
            if ie > i0:
                tr = trade_v(m, i0, ie, 1, "open", s)
                if tr:
                    out.append(tr)
    return sc.im(out, von, bis)


# ---------- Bewertung ----------

def bestanden(v: dict, termin: bool, mit_vergleich: bool = True) -> tuple[bool, list[str]]:
    z, fehl = v["zeitraum"], []
    mind = MIN_TRADES_TERMIN if termin else MIN_TRADES
    if z["trades"] < mind:
        fehl.append(f"nur {z['trades']} Trades")
    if z["pf"] < PF_MIN:
        fehl.append(f"PF {z['pf']}")
    if v["robust"]["pf"] < 1.0:
        fehl.append(f"1,5x Spread {v['robust']['pf']}")
    if v["jahr_2026"]["pf"] <= 1.0:
        fehl.append(f"2026 {v['jahr_2026']['pf']}")
    if v["kontrolle"]["pf"] < PF_KONTROLLE:
        fehl.append(f"Kontrolle {v['kontrolle']['pf']}")
    if v["haelfte_1"]["trades"] >= MIN_HAELFTE and v["haelfte_2"]["trades"] >= MIN_HAELFTE:
        for k, nm in (("haelfte_1", "1. Hälfte"), ("haelfte_2", "2. Hälfte")):
            if v[k]["pf"] <= 1.0:
                fehl.append(f"{nm} {v[k]['pf']}")
    if mit_vergleich and not v["vergleich"]["bestanden"]:
        fehl.append("Vergleich")
    return not fehl, fehl


def kennzahlen_satz(tr: list[dict], rob: list[dict], kon: list[dict], kontrolle) -> dict:
    return {"zeitraum": sc.kennzahlen(tr, *ZEITRAUM), "robust": sc.kennzahlen(rob, *ZEITRAUM),
            "haelfte_1": sc.kennzahlen(tr, *HAELFTEN[0]), "haelfte_2": sc.kennzahlen(tr, *HAELFTEN[1]),
            "jahr_2026": sc.kennzahlen(tr, *JAHR_2026), "kontrolle": sc.kennzahlen(kon, *kontrolle)}


def zwilling(tr: list[dict], rng: np.random.Generator) -> list[dict]:
    """Je Trade per Zufall die eigene oder die umgedrehte Richtung."""
    tausch = rng.random(len(tr)) < 0.5
    return [dict(t, r=t["r_gegen"], d=-t["d"]) if w else t for t, w in zip(tr, tausch)]


def bewerte_richtung(familie, variante, sym, tf, termin, rechne, kontrolle, rng) -> dict:
    tr = rechne(1.0, *ZEITRAUM)
    rob = rechne(ROBUST, *ZEITRAUM)
    kon = rechne(1.0, *kontrolle)
    v = kennzahlen_satz(tr, rob, kon, kontrolle)
    z = sc.im(tr, *ZEITRAUM)
    if z:
        eigen = np.array([t["r"] for t in z])
        gegen = np.array([t["r_gegen"] for t in z])
        pfk = sc.pf_von(eigen)
        pfs = np.array([sc.pf_von(np.where(rng.random(len(z)) < 0.5, gegen, eigen)) for _ in range(ZUFALL_LAEUFE)])
        pct = round(100 * float((pfk > pfs).mean()), 1)
        v["vergleich"] = {"geschlagen_pct": pct, "zufall_pf_median": round(float(np.median(pfs)), 2),
                          "bestanden": pct >= ZUFALL_PCT}
    else:
        v["vergleich"] = {"geschlagen_pct": 0.0, "zufall_pf_median": None, "bestanden": False}
    ok, fehl = bestanden(v, termin)
    zw = kennzahlen_satz(zwilling(tr, rng), zwilling(rob, rng), zwilling(kon, rng), kontrolle)
    zok, _ = bestanden(zw, termin, mit_vergleich=False)
    return {"familie": familie, "variante": variante, "markt": sym, "kerzen": tf, "termin": termin, **v,
            "bestanden": ok, "verfehlt": fehl, "zwilling_bestanden": zok, "zwilling_pf": zw["zeitraum"]["pf"]}


def bewerte_placebo(familie, variante, sym, tf, rechne, kontrolle) -> dict:
    tr, rob, kon = rechne(1.0, *ZEITRAUM), rechne(ROBUST, *ZEITRAUM), rechne(1.0, *kontrolle)
    pt, prob, pkon = (rechne(1.0, *ZEITRAUM, placebo=True), rechne(ROBUST, *ZEITRAUM, placebo=True),
                      rechne(1.0, *kontrolle, placebo=True))
    v = kennzahlen_satz(tr, rob, kon, kontrolle)
    p = kennzahlen_satz(pt, prob, pkon, kontrolle)
    v["vergleich"] = {"placebo_pf": p["zeitraum"]["pf"], "placebo_trades": p["zeitraum"]["trades"],
                      "bestanden": v["zeitraum"]["pf"] > p["zeitraum"]["pf"]}
    ok, fehl = bestanden(v, True)
    zok, _ = bestanden(p, True, mit_vergleich=False)
    return {"familie": familie, "variante": variante, "markt": sym, "kerzen": tf, "termin": True, **v,
            "bestanden": ok, "verfehlt": fehl, "zwilling_bestanden": zok, "zwilling_pf": p["zeitraum"]["pf"]}


def lade_markt(sym: str, tf: int, daten: pathlib.Path, m1: pathlib.Path, sp: dict) -> sc.Markt | None:
    if tf == 1:
        p = m1 / f"{sym}_1min.csv.gz"
        if not p.exists():
            return None
        return sc.Markt(sym, sc.lade(p, KONTROLLE_TERMINE[0]), sp[sym], minuten=1)
    p = daten / f"{sym}_5min.csv.gz"
    if not p.exists():
        return None
    df = sc.lade(p)
    return sc.Markt(sym, zu_15(df) if tf == 15 else df, sp[sym], minuten=tf)


def rechne_alles(daten: pathlib.Path = DATEN, m1: pathlib.Path = M1, nur: set | None = None) -> list[dict]:
    rng = np.random.default_rng(SAAT)
    sp = spreads()
    ter = sc.termine()
    ereignisse = sorted(ter["nfp"] + ter["cpi"] + ter["fomc"])
    res = []
    for tf in (1, 5, 15):
        for sym in ALLE + (["AUDJPY", "CADJPY"] if tf == 1 else []):
            if nur and sym not in nur:
                continue
            m = lade_markt(sym, tf, daten, m1, sp)
            if m is None:
                continue
            kon = KONTROLLE_TERMINE if tf == 1 else KONTROLLE
            if sym not in ("AUDJPY", "CADJPY"):
                for v in ("folgen_10r", "folgen_2r", "gegen_2r"):
                    res.append(bewerte_richtung("eroeffnung", v, sym, tf, False,
                                                functools.partial(eroeffnung, m, sym, v), kon, rng))
                for v in ("news_gegen", "news_folgen"):
                    res.append(bewerte_richtung("news", v, sym, tf, True,
                                                functools.partial(news, m, v, ereignisse), KONTROLLE_TERMINE, rng))
                if tf == 5:
                    for v in ("folgen", "gegen"):
                        res.append(bewerte_richtung("halbe_stunde", v, sym, tf, False,
                                                    functools.partial(halbe_stunde, m, sym, v), kon, rng))
                    if sym in INDIZES:
                        res.append(bewerte_placebo("vor_der_zahl", "vor_der_zahl", sym, tf,
                                                   functools.partial(vor_der_zahl, m, ter), KONTROLLE_TERMINE))
            if tf == 1 and sym in GOTOBI:
                for v in ("gotobi_a", "gotobi_b"):
                    res.append(bewerte_placebo("gotobi", v, sym, tf, functools.partial(gotobi, m, v), KONTROLLE_TERMINE))
            print(f"{tf} Min. {sym}: {len(res)} Kombinationen", flush=True)
            del m
    return res


def zeile(r: dict) -> str:
    v = r["vergleich"]
    vg = f"{v['geschlagen_pct']} % Zufall" if "geschlagen_pct" in v else f"Placebo {v['placebo_pf']}"
    return (f"| {r['familie']} | {r['variante']} | {r['markt']} | {r['kerzen']} | {r['zeitraum']['trades']} | "
            f"{r['zeitraum']['je_woche']} | {r['zeitraum']['pf']} | {r['robust']['pf']} | {r['jahr_2026']['pf']} | "
            f"{r['kontrolle']['pf']} | {vg} | {'ja' if r['bestanden'] else '; '.join(r['verfehlt'])} |")


def bericht(res: list[dict]) -> str:
    ok = sorted([r for r in res if r["bestanden"]], key=lambda r: -r["zeitraum"]["je_woche"])
    zw = [r for r in res if r["zwilling_bestanden"]]
    kopf = ["| Familie | Variante | Markt | Min. | Trades | je Woche | PF | 1,5x | 2026 | Kontrolle | Vergleich | bestanden |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    z = ["# Scalping-Komitee Runde 2b: Ergebnis", "",
         "Regeln: suche/VORAB_scalping2.yaml (versiegelt vor dem Rechnen). Zeitraum 01.11.2024 bis 30.10.2026, Kontrolle "
         "2022 bis 2024 (1 Min. und Termine ab 2023). Mit Stop in R, ohne Stop in Prozent.", "",
         f"**Kombinationen: {len(res)}. Bestanden: {len(ok)}. Zufallszwillinge bestanden: {len(zw)}.**", ""]
    if len(ok) <= len(zw):
        z += ["Es bestehen nicht mehr echte Kombinationen als Zufallszwillinge. Was besteht, ist vermutlich Glück.", ""]
    z += ["## Bestanden", ""] + (kopf + [zeile(r) for r in ok] if ok else ["Keine."]) + [""]
    fam = {}
    for r in res:
        fam.setdefault((r["familie"], r["variante"]), []).append(r)
    z += ["## Je Familie und Variante", "", "| Familie | Variante | Kombinationen | bestanden | Zwillinge bestanden | "
          "PF im Zeitraum (Median) | Trades/Woche (Summe) |", "|---|---|---|---|---|---|---|"]
    for (f, v), rs in fam.items():
        z.append(f"| {f} | {v} | {len(rs)} | {sum(r['bestanden'] for r in rs)} | {sum(r['zwilling_bestanden'] for r in rs)} | "
                 f"{round(float(np.median([r['zeitraum']['pf'] for r in rs])), 2)} | "
                 f"{round(sum(r['zeitraum']['je_woche'] for r in rs), 1)} |")
    beste = sorted([r for r in res if not r["bestanden"] and r["zeitraum"]["trades"] >= (30 if r["termin"] else 100)],
                   key=lambda r: -r["zeitraum"]["pf"])[:15]
    z += ["", "## Die 15 besten, die nicht bestanden haben (genug Trades)", ""] + kopf + [zeile(r) for r in beste] + [""]
    return "\n".join(z)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--daten", type=pathlib.Path, default=DATEN)
    ap.add_argument("--m1", type=pathlib.Path, default=M1)
    ap.add_argument("--nur", default="")
    a = ap.parse_args(argv)
    check_vorab()
    res = rechne_alles(a.daten, a.m1, set(a.nur.split(",")) if a.nur else None)
    if a.nur:
        print(bericht(res))
        return
    ERGEBNIS.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=0, default=str) + "\n",
                                             encoding="utf-8")
    md = bericht(res)
    ERGEBNIS.with_suffix(".md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
