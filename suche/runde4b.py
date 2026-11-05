"""Strategie-Suche Runde 4b: die Day-Trading-Strategien aus Runde 4 so, wie sie in den Videos selbst stehen
(suche/VORAB_runde4b.yaml).

Runde 4 hat Standardfassungen aus Titel, Beschreibung und Literatur gerechnet, weil die Untertitel noch fehlten. Die
VORAB von Runde 4 verspricht: Weichen die Videos deutlich ab, bekommt die Fassung aus dem Video eine eigene, wieder
vorab festgelegte Runde 4b. Die Untertitel (47 von 60, vom Mac geholt) zeigen solche Abweichungen, zum Beispiel:
ORB mit Kerzenschluss statt Stop-Order und Ziel 1,5 x Risiko, London-Breakout auf Stundenkerzen 4 bis 8 Uhr mit
ATR-Filter und nur Long, Larry Williams mit 0,7 x Vortagesspanne und Ziel 3 x Stop, DAX-Lücke MIT der Lücke statt
dagegen.

Ablauf, Kosten und Hürden sind dieselben wie in Runde 4 (suche/runde4.py): Auswahl März bis August 2026, bester Markt
je Strategie, Glückstest gegen den besten Markt der Zufallsläufe, Gegenprobe mit 1,5-fachem Spread, Siegel September
und Oktober 2026.

    python -m suche.runde4b --festlegen "Grund"     # Prüfsumme der VORAB ins Journal, BEVOR gerechnet wird
    python -m suche.runde4b <kerzen> <out_dir>       # rechnen
"""
from __future__ import annotations

import json
import pathlib
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yaml

from suche import runde4 as r4
from suche.runde1 import journal_add, journal_lines, last_value
from suche.runde3 import read_capital
from suche.runde4 import (Markt, Setup, Tag, auswerten, ausbruch, einstiegs_kerzen, fenster, kennzahlen, nan, null_pf,
                          passt, sha256_text, tag_hoch_tief)

HERE = pathlib.Path(__file__).resolve().parent
VORAB = HERE / "VORAB_runde4b.yaml"
KEY = "VORAB_runde4b sha256 "

# Sitzungen: Zeitzone, Beginn, Ende (in verschobener Ortszeit), Verschiebung in Stunden. Die Verschiebung macht aus
# einer Sitzung über Mitternacht einen Kalendertag: New York + 6 Stunden -> 18:00 wird 0:00 des nächsten Tages.
SITZUNGEN_B = {name: (tz, beg, end, 0) for name, (tz, beg, end) in r4.SITZUNGEN.items()}
SITZUNGEN_B.update({
    "NY_ABEND": ("America/New_York", "00:00", "07:00", 6),     # 18:00 bis 1:00 New York (Asien-Sitzung)
    "TAG24": ("America/New_York", "00:00", "23:00", 6),        # 18:00 bis 17:00 New York (Handelstag Futures und MT-Broker)
    "LONDON_FRUEH": ("Europe/London", "04:00", "17:00", 0),    # 4:00 bis 17:00 London
})


def check_vorab() -> dict:
    text = VORAB.read_text(encoding="utf-8")
    want = last_value(journal_lines(), KEY)
    if want != sha256_text(text):
        raise SystemExit("VORAB_runde4b.yaml stimmt nicht mit der Prüfsumme im Journal überein. Erst festlegen.")
    return yaml.safe_load(text)


# --------------------------------------------------------------------------------------------------------------------
# Markt mit frei wählbarer Sitzung und Stundenkerzen

@dataclass
class MarktB(Markt):
    tod: np.ndarray | None = None    # Minute des Tages in verschobener Ortszeit
    b0: int = 0                      # Sitzungsbeginn (Minute)


def minute(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def baue_markt(path: pathlib.Path, epic: str, typ: str, sitzung: str, von: str = "2025-12-01") -> MarktB:
    """Wie runde4.baue_markt, aber mit Verschiebung (Sitzungen über Mitternacht) und Minutenzähler je Kerze."""
    bars, spread = read_capital(path)
    bars, spread = bars.loc[von:], spread.loc[von:]
    tz, beg, end, versch = SITZUNGEN_B[sitzung]
    lokal = bars.index.tz_localize("UTC").tz_convert(tz).tz_localize(None) + pd.Timedelta(hours=versch)
    tod = np.asarray(lokal.hour * 60 + lokal.minute)
    b0, e0 = minute(beg), minute(end)
    soll = (e0 - b0) // 15
    drin = (tod >= b0) & (tod < e0) & (np.asarray(lokal.weekday) < 5)
    pos = np.flatnonzero(drin)
    tage: list[Tag] = []
    if len(pos):
        tagnr = lokal.values.astype("datetime64[D]")
        grenzen = np.flatnonzero(np.diff(tagnr[pos].astype(np.int64))) + 1
        for teil in np.split(pos, grenzen):
            if len(teil) >= soll - 2 and tod[teil[0]] == b0:
                tage.append(Tag(str(tagnr[teil[0]]), teil, tage[-1] if tage else None))
    return MarktB(epic, typ, bars.index, bars["open"].to_numpy(), bars["high"].to_numpy(), bars["low"].to_numpy(),
                  bars["close"].to_numpy(), spread.reindex(bars.index).to_numpy(), tage, lokal, tod, b0)


@dataclass
class Stunde:
    g: int          # Stunde seit Sitzungsbeginn (0 = erste)
    i0: int         # erste 15-Minuten-Kerze
    i1: int         # letzte 15-Minuten-Kerze
    o: float
    h: float
    l: float
    c: float


def stunden(m: MarktB, tag: Tag) -> list[Stunde]:
    """Stundenkerzen der Sitzung, ab Sitzungsbeginn gezählt (New York: 9:30, 10:30, ...)."""
    g = (m.tod[tag.idx] - m.b0) // 60
    grenzen = np.flatnonzero(np.diff(g)) + 1
    out = []
    for teil, gg in zip(np.split(tag.idx, grenzen), np.split(g, grenzen)):
        out.append(Stunde(int(gg[0]), int(teil[0]), int(teil[-1]), float(m.o[teil[0]]), float(m.h[teil].max()),
                          float(m.l[teil].min()), float(m.c[teil[-1]])))
    return out


def atr_rma(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int = 14) -> np.ndarray:
    """ATR wie TradingView ta.atr: True Range, geglättet nach Wilder (Start mit dem Mittel der ersten n Werte)."""
    vc = np.r_[np.nan, c[:-1]]
    with np.errstate(invalid="ignore"):
        tr = np.nanmax(np.vstack([h - l, np.abs(h - vc), np.abs(l - vc)]), axis=0)
    out = np.full(len(tr), np.nan)
    if len(tr) >= n:
        out[n - 1] = tr[:n].mean()
        for i in range(n, len(tr)):
            out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


def stop_order(m: Markt, tag: Tag, k: int, d: int, marke: float, stop_level: float, ziel_level: float) -> Setup | None:
    """Stop-Order an der Marke mit festen Stop- und Zielkursen. Springt der Kurs über die Marke, Füllung zur Eröffnung."""
    ref = max(marke, m.o[k]) if d > 0 else min(marke, m.o[k])
    abst = (ref - stop_level) * d
    ziel = (ziel_level - ref) * d
    if not (abst > 0 and ziel > 0):
        return None
    return Setup(tag.datum, int(k), float(ref), d, float(abst), float(ziel), int(tag.idx[-1]), schluss=True, im_bar=True)


def ohne_tag(tag: Tag, p: dict) -> bool:
    return pd.Timestamp(tag.datum).weekday() in p.get("ohne_wochentage", [])


# --------------------------------------------------------------------------------------------------------------------
# Simulation. Wie runde4.simuliere, nur die Einstiegskerze von Stop-Orders wird anders gelesen.
#
# Runde 4 hat in der Kerze, in der eine Stop-Order auslöst, jedes Tief unter dem Stop als Stop gezählt, auch wenn das
# Tief VOR dem Einstieg lag (die Kerze eröffnet unter der Marke, fällt erst und steigt dann durch). Bei engen Stops
# (Rampton: 10 % der Vortagesspanne) wären so in Dezember bis Februar 223 von 393 Trades schon in der Einstiegskerze
# ausgestoppt worden. Runde 4b liest die Einstiegskerze wie der Broker-Emulator von TradingView, mit dem die meisten
# Videos testen: Liegt die Eröffnung näher am Hoch, läuft der Kurs Eröffnung -> Hoch -> Tief -> Schluss, sonst
# Eröffnung -> Tief -> Hoch -> Schluss. Stop und Ziel zählen erst nach dem Auslösen. Ab der nächsten Kerze gilt wieder
# Runde 4: Liegen Stop und Ziel in derselben Kerze, zählt der Stop.

def einstiegskerze(m: Markt, s: Setup, d: int, sp: float, stop: float | None,
                   ziel: float | None) -> tuple[float, str] | None:
    """Ausstieg schon in der Kerze, in der die Stop-Order (Richtung s.d, Marke s.ref) auslöst, für eine Position in
    Richtung d. None, wenn in dieser Kerze weder Stop noch Ziel erreicht wird."""
    k = s.i
    o, h, l, c = float(m.o[k]), float(m.h[k]), float(m.l[k]), float(m.c[k])
    pfad = [o, h, l, c] if (h - o) < (o - l) else [o, l, h, c]
    if (s.d > 0 and o >= s.ref) or (s.d < 0 and o <= s.ref):
        start = 0                                            # Lücke über die Marke: ausgelöst zur Eröffnung
    else:
        start = next((j for j in range(1, 4) if (pfad[j] >= s.ref if s.d > 0 else pfad[j] <= s.ref)), None)
        if start is None:
            return None
    for v in pfad[start:]:                                   # Rest des Auslöse-Abschnitts, dann die weiteren Ecken
        kurs = v if d > 0 else v + sp                         # Long schließt zum Bid, Short zum Ask
        if stop is not None and (kurs <= stop if d > 0 else kurs >= stop):
            return stop, "stop"
        if ziel is not None and (kurs >= ziel if d > 0 else kurs <= ziel):
            return ziel, "ziel"
    return None


def simuliere(m: Markt, s: Setup, d: int | None = None, faktor: float = 1.0) -> dict:
    """Ein Trade. d überschreibt die Richtung (Zufall: gleiche Zeit, gespiegelte Abstände)."""
    d = s.d if d is None else d
    sp = m.sp * faktor
    ein = s.ref + (sp[s.i] if d > 0 else 0.0)
    stop = s.ref - d * s.stop_abst if s.stop_abst == s.stop_abst else None
    ziel = s.ref + d * s.ziel_abst if s.ziel_abst == s.ziel_abst else None
    aus, grund, k_aus = None, "zeit", s.ende
    erste = s.i
    if s.im_bar:
        treffer = einstiegskerze(m, s, d, float(sp[s.i]), stop, ziel)
        if treffer:
            (aus, grund), k_aus = treffer, s.i
        erste = s.i + 1
    if aus is None:
        letzte = s.ende if s.schluss else s.ende - 1
        for k in range(erste, letzte + 1):
            lo, hi, op = m.l[k], m.h[k], m.o[k]
            a_lo, a_hi = lo + sp[k], hi + sp[k]
            if stop is not None:
                if d > 0 and lo <= stop:
                    aus, grund, k_aus = (min(stop, op) if k > s.i else stop), "stop", k
                    break
                if d < 0 and a_hi >= stop:
                    aus, grund, k_aus = (max(stop, op + sp[k]) if k > s.i else stop), "stop", k
                    break
            if ziel is not None:
                if d > 0 and hi >= ziel:
                    aus, grund, k_aus = (max(ziel, op) if k > s.i else ziel), "ziel", k
                    break
                if d < 0 and a_lo <= ziel:
                    aus, grund, k_aus = (min(ziel, op + sp[k]) if k > s.i else ziel), "ziel", k
                    break
    if aus is None:
        aus = (m.c[s.ende] if s.schluss else m.o[s.ende]) + (sp[s.ende] if d < 0 else 0.0)
    r = (aus / ein - 1) * d * 100
    return {"datum": s.datum, "d": d, "r": float(r), "grund": grund, "kerzen": int(k_aus - s.i + 1)}


def rechne(m: Markt, setups: list[Setup], faktor: float = 1.0) -> list[dict]:
    return [simuliere(m, s, None, faktor) for s in setups]


# --------------------------------------------------------------------------------------------------------------------
# Strategien (Regeln und Quellen: VORAB_runde4b.yaml)

def s_orb_schluss(m: MarktB, p: dict) -> list[Setup]:
    """ORB mit Kerzenschluss: Bereich = erste `kerzen` Kerzen der Sitzung. Die erste Kerze, die außerhalb schließt,
    gibt die Richtung; Einstieg zur Eröffnung der nächsten Kerze, Stop andere Seite (oder Mitte), Ziel `ziel_r` x
    Risiko, sonst Sitzungsschluss. Ein Trade am Tag. richtung=long: nur Schlüsse über dem Bereich zählen."""
    out = []
    n, nur = int(p["kerzen"]), p.get("richtung", "beide")
    for tag in m.tage:
        if ohne_tag(tag, p):
            continue
        idx = tag.idx
        hi, lo = float(m.h[idx[:n]].max()), float(m.l[idx[:n]].min())
        for j in range(n, len(idx) - 2):                 # Signal j, Einstieg j+1, danach bleibt mindestens eine Kerze
            k = idx[j]
            d = 1 if m.c[k] > hi else -1 if m.c[k] < lo else 0
            if d == 0 or (nur == "long" and d < 0):
                continue
            k1 = int(idx[j + 1])
            ref = float(m.o[k1])
            stop = (hi + lo) / 2 if p["stop"] == "mitte" else (lo if d > 0 else hi)
            abst = (ref - stop) * d
            if abst > 0:
                out.append(Setup(tag.datum, k1, ref, d, float(abst), float(p["ziel_r"] * abst), int(idx[-1]),
                                 schluss=True))
            break
    return out


def s_london_stunde(m: MarktB, p: dict) -> list[Setup]:
    """London-Breakout nach Trading Steady: Stundenkerzen London, Bereich = Hoch/Tief der Stunden 4 bis 8 Uhr. Ab der
    9-Uhr-Kerze: eine Stundenkerze eröffnet unter dem Bereichshoch und schließt darüber, ihre Größe liegt zwischen
    atr_min und atr_max x ATR(14) der Stunde davor -> Long zur Eröffnung der nächsten Stunde, Stop am Bereichstief,
    Ziel `ziel_r` x Risiko, sonst raus um 17 Uhr London. Nur Long, ein Trade am Tag."""
    df = pd.DataFrame({"o": m.o, "h": m.h, "l": m.l, "c": m.c}, index=m.t)
    hr = df.resample("60min", label="left", closed="left").agg({"o": "first", "h": "max", "l": "min", "c": "last"})
    hr = hr.dropna()
    atr = atr_rma(hr["h"].to_numpy(), hr["l"].to_numpy(), hr["c"].to_numpy(), int(p["atr_n"]))
    atr_vor = pd.Series(np.r_[np.nan, atr[:-1]], index=hr.index)          # ATR der vorigen Stunde
    b_von, b_bis, s_von = int(p["bereich_von"]), int(p["bereich_bis"]), int(p["signal_ab"])
    out = []
    for tag in m.tage:
        st = stunden(m, tag)
        bereich = [s for s in st if b_von <= s.g + m.b0 // 60 <= b_bis]
        if len(bereich) != b_bis - b_von + 1:
            continue
        hi, lo = max(s.h for s in bereich), min(s.l for s in bereich)
        for q, s in enumerate(st[:-1]):
            if s.g + m.b0 // 60 < s_von:
                continue
            if not (s.o < hi < s.c):
                continue
            a = atr_vor.get(m.t[s.i0].floor("60min"), np.nan)
            if not (a == a and p["atr_min"] * a <= s.h - s.l <= p["atr_max"] * a):
                continue
            e = st[q + 1]
            ref = float(m.o[e.i0])
            abst = ref - lo
            if abst > 0:
                out.append(Setup(tag.datum, e.i0, ref, 1, float(abst), float(p["ziel_r"] * abst), int(tag.idx[-1]),
                                 schluss=True))
            break
    return out


def s_vortag_stop_oco(m: MarktB, p: dict) -> list[Setup]:
    """Rampton FX (getestet von Trading Steady): Stop-Orders am Hoch und Tief des Vortags (Handelstag 18 bis 17 Uhr
    New York), die erste ausgelöste löscht die andere. Stop `stop_anteil` x Vortagesspanne hinter der Marke, Ziel
    `ziel_anteil` x Vortagesspanne vor der Marke, sonst raus zum Tagesende."""
    out = []
    for tag in m.tage:
        if tag.vor is None:
            continue
        ph, pl = tag_hoch_tief(m, tag.vor)
        spanne = ph - pl
        hit = ausbruch(m, einstiegs_kerzen(tag, 0), ph, pl)
        if hit is None or not spanne > 0:
            continue
        k, d = hit
        marke = ph if d > 0 else pl
        s = stop_order(m, tag, k, d, marke, marke - d * p["stop_anteil"] * spanne, marke + d * p["ziel_anteil"] * spanne)
        if s:
            out.append(s)
    return out


def s_vortag_hoch_stunde(m: MarktB, p: dict) -> list[Setup]:
    """TradePro (getestet von Trading Steady, S&P 500): nur Long. Die Sitzung eröffnet zwischen Vortageshoch und
    -tief. Die erste Stundenkerze, die unter dem Vortageshoch eröffnet und darüber schließt -> Long zur Eröffnung der
    nächsten Stunde, Stop = größerer Abstand von (Tief dieser Kerze, `atr_stop` x ATR(14) der Stundenkerzen), Ziel
    `ziel_r` x Risiko, sonst Sitzungsschluss. Kein Einstieg in der letzten Stundenkerze."""
    alle = [stunden(m, tag) for tag in m.tage]
    flach = [s for st in alle for s in st]
    if not flach:
        return []
    atr = atr_rma(np.array([s.h for s in flach]), np.array([s.l for s in flach]), np.array([s.c for s in flach]),
                  int(p["atr_n"]))
    out, pos = [], 0
    for tag, st in zip(m.tage, alle):
        a_tag = atr[pos:pos + len(st)]
        pos += len(st)
        if tag.vor is None:
            continue
        ph, pl = tag_hoch_tief(m, tag.vor)
        if not pl < m.o[tag.idx[0]] < ph:
            continue
        for q in range(len(st) - 2):                    # Einstieg in st[q+1], nie in der letzten Stundenkerze
            s = st[q]
            if not (s.o < ph < s.c):
                continue
            e = st[q + 1]
            ref = float(m.o[e.i0])
            abst = max(ref - s.l, p["atr_stop"] * a_tag[q])
            if abst > 0:
                out.append(Setup(tag.datum, e.i0, ref, 1, float(abst), float(p["ziel_r"] * abst), int(tag.idx[-1]),
                                 schluss=True))
            break
    return out


def s_gap_fill_prozent(m: MarktB, p: dict) -> list[Setup]:
    """Cory Mitchell (ES): Lücke zwischen Vortagesschluss und Eröffnung zwischen min_luecke und max_luecke (Anteil vom
    Kurs). Ist die Lücke in der ersten Kerze schon geschlossen, kein Trade. Sonst Einstieg nach der ersten Kerze gegen
    die Lücke, Ziel = Vortagesschluss, Stop gleich weit wie das Ziel, höchstens max_verlust (Anteil vom Kurs), sonst
    Sitzungsschluss."""
    out = []
    for tag in m.tage:
        if tag.vor is None:
            continue
        vs = float(m.c[tag.vor.idx[-1]])
        k0, k1 = int(tag.idx[0]), int(tag.idx[1])
        luecke = m.o[k0] / vs - 1
        if not p["min_luecke"] <= abs(luecke) <= p["max_luecke"]:
            continue
        d = -1 if luecke > 0 else 1
        if (d < 0 and m.l[k0] <= vs) or (d > 0 and m.h[k0] >= vs):
            continue
        ref = float(m.o[k1])
        ziel = (vs - ref) * d
        if not ziel > 0:
            continue
        out.append(Setup(tag.datum, k1, ref, d, float(min(ziel, p["max_verlust"] * ref)), float(ziel),
                         int(tag.idx[-1]), schluss=True))
    return out


def s_larry_williams_tag(m: MarktB, p: dict) -> list[Setup]:
    """Larry Williams nach YuRa (Gold): Stop-Orders bei Tageseröffnung +/- k x Vortagesspanne (Handelstag 18 bis 17 Uhr
    New York), erster Ausbruch des Tages, Stop `stop_k` x Vortagesspanne hinter der Marke, Ziel `ziel_x` x Stopabstand,
    sonst raus zum Tagesende."""
    out = []
    for tag in m.tage:
        if tag.vor is None:
            continue
        ph, pl = tag_hoch_tief(m, tag.vor)
        spanne = ph - pl
        o0 = float(m.o[tag.idx[0]])
        oben, unten = o0 + p["k"] * spanne, o0 - p["k"] * spanne
        hit = ausbruch(m, einstiegs_kerzen(tag, 0), oben, unten)
        if hit is None or not spanne > 0:
            continue
        k, d = hit
        marke = oben if d > 0 else unten
        stop = p["stop_k"] * spanne
        s = stop_order(m, tag, k, d, marke, marke - d * stop, marke + d * p["ziel_x"] * stop)
        if s:
            out.append(s)
    return out


def s_luecke_mit(m: MarktB, p: dict) -> list[Setup]:
    """Tradingdusche (DAX): echte Lücke = Eröffnung über dem Vortageshoch (unter dem Vortagestief). Dann Einstieg zur
    Eröffnung MIT der Lücke, Stop am Vortageshoch (-tief), kein Ziel, raus zum Sitzungsschluss."""
    out = []
    for tag in m.tage:
        if tag.vor is None:
            continue
        ph, pl = tag_hoch_tief(m, tag.vor)
        k0 = int(tag.idx[0])
        o0 = float(m.o[k0])
        if o0 > ph:
            d, stop = 1, ph
        elif o0 < pl:
            d, stop = -1, pl
        else:
            continue
        out.append(Setup(tag.datum, k0, o0, d, float((o0 - stop) * d), nan(), int(tag.idx[-1]), schluss=True))
    return out


STRATEGIEN_B = {
    "orb_schluss": s_orb_schluss,
    "london_stunde": s_london_stunde,
    "vortag_stop_oco": s_vortag_stop_oco,
    "vortag_hoch_stunde": s_vortag_hoch_stunde,
    "gap_fill_prozent": s_gap_fill_prozent,
    "larry_williams_tag": s_larry_williams_tag,
    "luecke_mit": s_luecke_mit,
}


# --------------------------------------------------------------------------------------------------------------------
# Lauf (wie Runde 4)

def markt_job(args) -> dict:
    path, info, cfg, seed = args
    try:
        return _markt_job(path, info, cfg, seed)
    except Exception as err:          # noqa: BLE001  ein Markt stoppt nicht die Runde
        return {"epic": info["epic"], "fehler": repr(err)}


def setups_fuer(path, epic: str, typ: str, strat: dict, cache: dict) -> tuple[MarktB, list[Setup], str]:
    sitz = strat.get("sitzung") or r4.sitzung_fuer(epic, typ)
    if sitz not in cache:
        cache[sitz] = baue_markt(path, epic, typ, sitz)
    m = cache[sitz]
    return m, STRATEGIEN_B[strat["logik"]](m, strat.get("parameter", {})), sitz


def _markt_job(path, info, cfg, seed) -> dict:
    epic, typ = info["epic"], info["typ"]
    cache: dict = {}
    rng = np.random.default_rng(seed)
    a_von, a_bis = cfg["auswahl"]
    s_von, s_bis = cfg["siegel"]
    n_null = cfg["zufall"]["laeufe"]
    faktor = cfg["kosten"]["spread_faktor_robust"]
    out = {"epic": epic, "typ": typ, "name": (info.get("meta") or {}).get("name"), "tage": {}, "strategien": {}}
    for name, strat in cfg["strategien"].items():
        if not passt(strat, epic, typ):
            continue
        m, setups, sitz = setups_fuer(path, epic, typ, strat, cache)
        out["tage"][sitz] = len(m.tage)
        aus = fenster(setups, a_von, a_bis)
        sie = fenster(setups, s_von, s_bis)
        lang = [simuliere(m, x, 1) for x in aus]
        kurz = [simuliere(m, x, -1) for x in aus]
        tr_a = [lang[i] if x.d > 0 else kurz[i] for i, x in enumerate(aus)]
        k_a = kennzahlen(tr_a)
        k_a["pf_robust"] = kennzahlen(rechne(m, aus, faktor=faktor))["pf"]
        k_a["monate"], k_a["ausstiege"] = {}, {}
        for t in tr_a:
            k_a["monate"][t["datum"][:7]] = round(k_a["monate"].get(t["datum"][:7], 0.0) + t["r"], 3)
            k_a["ausstiege"][t["grund"]] = k_a["ausstiege"].get(t["grund"], 0) + 1
        k_a["kerzen_im_schnitt"] = round(float(np.mean([t["kerzen"] for t in tr_a])), 1) if tr_a else None
        null = (null_pf(np.array([t["r"] for t in lang]), np.array([t["r"] for t in kurz]), n_null, rng)
                if aus else np.zeros(0, np.float32))
        out["strategien"][name] = {"sitzung": sitz, "auswahl": k_a, "siegel": kennzahlen(rechne(m, sie)),
                                   "null_pf": null}
    return out


def run(kerzen: pathlib.Path, out: pathlib.Path) -> dict:
    cfg = check_vorab()["runde_4b"]
    out.mkdir(parents=True, exist_ok=True)
    report = json.loads((kerzen / "bericht_runde3.json").read_text(encoding="utf-8"))
    infos = [mk for mk in report["maerkte"] if mk.get("kerzen", {}).get("anzahl") and mk["epic"] not in cfg["ohne"]]
    seed = cfg["zufall"]["seed"]
    jobs = [(kerzen / f"{mk['epic']}_MINUTE_15.csv.gz", mk, cfg, seed + i) for i, mk in enumerate(infos)]
    with ProcessPoolExecutor(max_workers=4) as ex:
        maerkte = list(ex.map(markt_job, jobs, chunksize=2))
    ergebnis = auswerten(maerkte, cfg)
    np.savez_compressed(out / "runde4b_zufall.npz", **{f"{mk['epic']}|{n}": st.pop("null_pf")
                                                        for mk in maerkte for n, st in (mk.get("strategien") or {}).items()})
    payload = {"made": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
               "vorab_sha256": sha256_text(VORAB.read_text(encoding="utf-8")),
               "ergebnis": ergebnis, "fehler": [mk for mk in maerkte if mk.get("fehler")], "maerkte": maerkte}
    (out / "runde4b.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    kurz = {n: {"sieger": (e["sieger"] or {}).get("epic"), "pf": ((e["sieger"] or {}).get("auswahl") or {}).get("pf"),
                "demo": (e["sieger"] or {}).get("demo"), "ueber_schwelle": e["ueber_schwelle"],
                "zufall": e["ueber_schwelle_zufall_im_schnitt"]} for n, e in ergebnis.items()}
    journal_add("Runde 4b gerechnet: " + json.dumps(kurz, ensure_ascii=False))
    return payload


def main(argv: list[str]) -> int:
    if argv[:1] == ["--festlegen"]:
        text = VORAB.read_text(encoding="utf-8")
        journal_add(f"Runde 4b festgelegt, Grund: {argv[1]}. {KEY}{sha256_text(text)}")
        print("Im Journal:", sha256_text(text))
        return 0
    if len(argv) != 2:
        print(__doc__)
        return 2
    payload = run(pathlib.Path(argv[0]), pathlib.Path(argv[1]))
    print(json.dumps({n: {k: v for k, v in e.items() if k != "rangliste"} for n, e in payload["ergebnis"].items()},
                     ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
