"""Strategie-Suche Runde 4: Day-Trading-Strategien aus YouTube und Forschung auf allen Capital.com-Märkten
(suche/VORAB_runde4.yaml).

Kirons Wunsch (03.11.2026): viele Strategien aus YouTube abschreiben, testen und die guten auf eigene Demo-Konten
verteilen, jedes Konto auf den einen Markt mit dem besten Backtest-Faktor der letzten Monate beschränkt.

Ablauf je Strategie:
1. Auswahl März bis August 2026: auf jedem Markt rechnen, Gewinnfaktor nach echtem Spread.
2. Je Strategie der Markt mit dem besten Gewinnfaktor (mindestens 30 Trades) = Kirons Regel.
3. Glückstest: dieselbe Auswahl mit zufälliger Richtung (gleiche Zeitpunkte, gleiche Stop- und Zielabstände). Wie
   gut ist der beste Markt, wenn nur Zufall im Spiel ist? Der echte Sieger muss besser sein als 95 % dieser Läufe.
4. Siegel September und Oktober 2026: Der gewählte Markt muss dort im Plus bleiben (Gewinnfaktor über 1).

Alles in Prozent vom Kurs je Trade mit fester Größe (so wie die Demo-Bots mit der kleinsten Ordergröße handeln);
Gewinnfaktor = Summe der Gewinne / Summe der Verluste. Kurse sind Bid-Kerzen; Kauf zum Ask (Bid + Spread der Kerze),
Verkauf zum Bid. Alle Trades sind vor Sitzungsende flach, also ohne Übernachtkosten.

    python -m suche.runde4 --festlegen "Grund"     # Prüfsumme der VORAB ins Journal, BEVOR gerechnet wird
    python -m suche.runde4 <kerzen> <out_dir>       # rechnen
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yaml

from suche.runde1 import journal_add, journal_lines, last_value
from suche.runde3 import read_capital

HERE = pathlib.Path(__file__).resolve().parent
VORAB = HERE / "VORAB_runde4.yaml"
KEY = "VORAB_runde4 sha256 "

# Hauptsitzung je Markt: Zeitzone, Beginn, Ende (Ortszeit)
SITZUNGEN = {
    "NY": ("America/New_York", "09:30", "16:00"),
    "EUROPA": ("Europe/Berlin", "09:00", "17:30"),
    "LONDON": ("Europe/London", "08:00", "16:30"),
    "TOKIO": ("Asia/Tokyo", "09:00", "15:30"),
    "HONGKONG": ("Asia/Hong_Kong", "09:30", "16:00"),
    "SYDNEY": ("Australia/Sydney", "10:00", "16:00"),
    "SINGAPUR": ("Asia/Singapore", "09:00", "17:00"),
    "FX": ("Europe/London", "08:00", "17:00"),
}
EUROPA_AKTIEN = {"SAPD", "SIE", "IBEES", "DB1", "ALVD", "BMW", "MBGN", "VOW3", "BASD", "BAYN", "DTE", "DBK", "ADSGN",
                 "IFX", "RHM", "AIRFR", "MCFR", "TTE", "NESN", "NOVN"}
LONDON_AKTIEN = {"SHELGB", "AZN", "HSBA", "BP"}
INDEX_SITZUNG = {"DE40": "EUROPA", "FR40": "EUROPA", "EU50": "EUROPA", "IT40": "EUROPA", "NL25": "EUROPA",
                 "SP35": "EUROPA", "SW20": "EUROPA", "UK100": "LONDON", "J225": "TOKIO", "HK50": "HONGKONG",
                 "AU200": "SYDNEY", "CN50": "SINGAPUR", "SG25": "SINGAPUR", "DXY": "FX"}


def sitzung_fuer(epic: str, typ: str) -> str:
    if typ == "CURRENCIES":
        return "FX"
    if typ == "SHARES":
        return "EUROPA" if epic in EUROPA_AKTIEN else "LONDON" if epic in LONDON_AKTIEN else "NY"
    if typ == "INDICES":
        return INDEX_SITZUNG.get(epic, "NY")
    return "NY"                                   # Rohstoffe und Krypto: New Yorker Eröffnung als Anker


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_vorab() -> dict:
    text = VORAB.read_text(encoding="utf-8")
    want = last_value(journal_lines(), KEY)
    if want != sha256_text(text):
        raise SystemExit("VORAB_runde4.yaml stimmt nicht mit der Prüfsumme im Journal überein. Erst festlegen.")
    return yaml.safe_load(text)


# --------------------------------------------------------------------------------------------------------------------
# Markt und Handelstage

@dataclass
class Tag:
    datum: str
    idx: np.ndarray                  # Kerzen der Hauptsitzung (Index in den Markt-Arrays)
    vor: "Tag | None" = None         # vorheriger vollständiger Handelstag
    extra: dict = field(default_factory=dict)


@dataclass
class Markt:
    epic: str
    typ: str
    t: pd.DatetimeIndex              # UTC, Kerzenbeginn
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    sp: np.ndarray                   # Spread (Ask - Bid) zur Eröffnung der Kerze
    tage: list[Tag]
    lokal: pd.DatetimeIndex          # Ortszeit der Sitzung


def baue_markt(path: pathlib.Path, epic: str, typ: str, von: str = "2025-12-01", sitzung: str | None = None) -> Markt:
    bars, spread = read_capital(path)
    bars, spread = bars.loc[von:], spread.loc[von:]
    tz, beg, end = SITZUNGEN[sitzung or sitzung_fuer(epic, typ)]
    lokal = bars.index.tz_localize("UTC").tz_convert(tz)
    tod = lokal.hour * 60 + lokal.minute
    b0 = int(beg[:2]) * 60 + int(beg[3:])
    e0 = int(end[:2]) * 60 + int(end[3:])
    soll = (e0 - b0) // 15
    drin = (tod >= b0) & (tod < e0) & (lokal.weekday < 5)
    pos = np.flatnonzero(drin)
    tage: list[Tag] = []
    datum = lokal.date
    if len(pos):
        grenzen = np.flatnonzero(np.diff(np.array([datum[p] for p in pos], dtype="datetime64[D]").astype(int))) + 1
        for teil in np.split(pos, grenzen):
            if len(teil) >= soll - 2 and tod[teil[0]] == b0:
                tag = Tag(str(datum[teil[0]]), teil, tage[-1] if tage else None)
                tage.append(tag)
    return Markt(epic, typ, bars.index, bars["open"].to_numpy(), bars["high"].to_numpy(), bars["low"].to_numpy(),
                 bars["close"].to_numpy(), spread.reindex(bars.index).to_numpy(), tage, lokal)


# --------------------------------------------------------------------------------------------------------------------
# Setups und Simulation

@dataclass
class Setup:
    datum: str
    i: int                 # Einstiegskerze
    ref: float             # Bid-Referenzkurs des Einstiegs (Eröffnung der Kerze oder Ausbruchsmarke)
    d: int                 # +1 Long, -1 Short
    stop_abst: float       # Abstand Stop vom Referenzkurs (nan = kein Stop)
    ziel_abst: float       # Abstand Ziel vom Referenzkurs (nan = kein Ziel)
    ende: int              # spätestens raus: Eröffnung dieser Kerze (oder Schluss, wenn schluss=True)
    schluss: bool = False  # True: raus zum Schluss der Kerze `ende`
    im_bar: bool = False   # Einstieg innerhalb der Kerze i (Stop-Order); dann zählt in Kerze i nur der Stop


def simuliere(m: Markt, s: Setup, d: int | None = None, faktor: float = 1.0) -> dict:
    """Ein Trade. d überschreibt die Richtung (Zufall: gleiche Zeit, gespiegelte Abstände)."""
    d = s.d if d is None else d
    sp = m.sp * faktor
    ein = s.ref + (sp[s.i] if d > 0 else 0.0)          # Long kauft zum Ask, Short verkauft zum Bid
    stop = s.ref - d * s.stop_abst if s.stop_abst == s.stop_abst else None
    ziel = s.ref + d * s.ziel_abst if s.ziel_abst == s.ziel_abst else None
    aus, grund, k_aus = None, "zeit", s.ende
    letzte = s.ende if s.schluss else s.ende - 1
    for k in range(s.i, letzte + 1):
        lo, hi, op = m.l[k], m.h[k], m.o[k]
        a_lo, a_hi = lo + sp[k], hi + sp[k]               # Ask-Seite der Kerze
        if stop is not None:
            if d > 0 and lo <= stop:
                aus, grund, k_aus = (min(stop, op) if k > s.i else stop), "stop", k
                break
            if d < 0 and a_hi >= stop:
                aus, grund, k_aus = (max(stop, op + sp[k]) if k > s.i else stop), "stop", k
                break
        if ziel is not None and not (s.im_bar and k == s.i):
            if d > 0 and hi >= ziel:
                aus, grund, k_aus = (max(ziel, op) if k > s.i else ziel), "ziel", k
                break
            if d < 0 and a_lo <= ziel:
                aus, grund, k_aus = (min(ziel, op + sp[k]) if k > s.i else ziel), "ziel", k
                break
    if aus is None:
        if s.schluss:
            aus = m.c[s.ende] + (sp[s.ende] if d < 0 else 0.0)
        else:
            aus = m.o[s.ende] + (sp[s.ende] if d < 0 else 0.0)
    r = (aus / ein - 1) * d * 100
    return {"datum": s.datum, "d": d, "r": float(r), "grund": grund, "kerzen": int(k_aus - s.i + 1)}


def rechne(m: Markt, setups: list[Setup], rng: np.random.Generator | None = None, faktor: float = 1.0) -> list[dict]:
    if rng is None:
        return [simuliere(m, s, None, faktor) for s in setups]
    dirs = np.where(rng.random(len(setups)) < 0.5, 1, -1)
    return [simuliere(m, s, int(dd), faktor) for s, dd in zip(setups, dirs)]


def gewinnfaktor(r: np.ndarray) -> float | None:
    r = np.asarray(r, float)
    loss = -r[r < 0].sum()
    return round(float(r[r > 0].sum() / loss), 3) if loss > 0 else (None if not len(r) else 99.0)


def kennzahlen(tr: list[dict]) -> dict:
    if not tr:
        return {"trades": 0, "pf": None, "treffer_pct": None, "summe_pct": 0.0, "mittel_pct": None}
    r = np.array([t["r"] for t in tr])
    d = np.array([t["d"] for t in tr])
    return {"trades": int(len(r)), "pf": gewinnfaktor(r), "treffer_pct": round(float((r > 0).mean() * 100), 1),
            "summe_pct": round(float(r.sum()), 2), "mittel_pct": round(float(r.mean()), 4),
            "long_pf": gewinnfaktor(r[d > 0]) if (d > 0).any() else None,
            "short_pf": gewinnfaktor(r[d < 0]) if (d < 0).any() else None}


# --------------------------------------------------------------------------------------------------------------------
# Hilfen für die Strategien

def nan() -> float:
    return float("nan")


def tag_hoch_tief(m: Markt, tag: Tag) -> tuple[float, float]:
    return float(m.h[tag.idx].max()), float(m.l[tag.idx].min())


def ausbruch(m: Markt, idx: np.ndarray, oben: float, unten: float, nur: str = "beide") -> tuple[int, int] | None:
    """Erste Kerze in idx, deren Hoch über `oben` oder Tief unter `unten` geht. Beide in derselben Kerze: kein Trade."""
    for k in idx:
        hoch = nur != "short" and m.h[k] > oben
        tief = nur != "long" and m.l[k] < unten
        if hoch and tief:
            return None
        if hoch:
            return int(k), 1
        if tief:
            return int(k), -1
    return None


def stop_einstieg(m: Markt, tag: Tag, k: int, d: int, marke: float, stop: float, ziel_r: float | None) -> Setup | None:
    """Stop-Order an der Marke (Kerze k löst aus). Raus spätestens zum Schluss der letzten Sitzungskerze."""
    ref = max(marke, m.o[k]) if d > 0 else min(marke, m.o[k])      # Lücke über die Marke: Füllung zur Eröffnung
    abst = (ref - stop) * d
    if not abst > 0:
        return None
    ziel = float(ziel_r * abst) if ziel_r else nan()
    return Setup(tag.datum, int(k), float(ref), d, float(abst), ziel, int(tag.idx[-1]), schluss=True, im_bar=True)


def einstiegs_kerzen(tag: Tag, ab: int) -> np.ndarray:
    """Kerzen ab Position `ab` der Sitzung, in denen noch eingestiegen werden darf (mindestens 2 Kerzen bleiben)."""
    return tag.idx[ab:len(tag.idx) - 2]


def bereich_ausbruch(m: Markt, tag: Tag, ab: int, oben: float, unten: float, stop_art: str,
                     ziel_r: float | None) -> Setup | None:
    """Erster Ausbruch aus [unten, oben] ab Sitzungsposition `ab`. Stop: andere Seite oder Mitte des Bereichs."""
    if not oben > unten:
        return None
    hit = ausbruch(m, einstiegs_kerzen(tag, ab), oben, unten)
    if hit is None:
        return None
    k, d = hit
    marke = oben if d > 0 else unten
    stop = (unten if d > 0 else oben) if stop_art == "gegenseite" else (oben + unten) / 2
    return stop_einstieg(m, tag, k, d, marke, stop, ziel_r)


def vortage(tag: Tag, n: int) -> list[Tag] | None:
    out, t = [], tag.vor
    while t is not None and len(out) < n:
        out.append(t)
        t = t.vor
    return out if len(out) == n else None


def adr(m: Markt, tag: Tag, n: int = 14) -> float | None:
    """Mittlere Tagesspanne (Hoch - Tief) / Eröffnung der letzten n Sitzungen, als Anteil."""
    vt = vortage(tag, n)
    if vt is None:
        return None
    return float(np.mean([(m.h[t.idx].max() - m.l[t.idx].min()) / m.o[t.idx[0]] for t in vt]))


# --------------------------------------------------------------------------------------------------------------------
# Strategien. Jede bekommt den Markt und liefert Setups (ein Setup = ein möglicher Trade). Regeln: VORAB_runde4.yaml.

def s_orb(m: Markt, p: dict) -> list[Setup]:
    """Opening Range Breakout: Bereich = erste `kerzen` Kerzen der Sitzung, Stop-Order am Ausbruch (erster Ausbruch des
    Tages), Stop andere Seite oder Mitte, Ziel `ziel_r` x Risiko, sonst raus zum Sitzungsschluss. Mit kerzen=4 und
    Stop in der Mitte ist das die Initial Balance (erste Stunde)."""
    out = []
    n = int(p["kerzen"])
    for tag in m.tage:
        r = tag.idx[:n]
        s = bereich_ausbruch(m, tag, n, float(m.h[r].max()), float(m.l[r].min()), p["stop"], p.get("ziel_r"))
        if s:
            out.append(s)
    return out


def s_orb_richtung(m: Markt, p: dict) -> list[Setup]:
    """Zarattini/Aziz: Richtung der ersten Kerze, Einstieg zur Eröffnung der zweiten, Stop andere Seite der ersten
    Kerze, Ziel `ziel_r` x Risiko, sonst raus zum Sitzungsschluss."""
    out = []
    for tag in m.tage:
        k0, k1 = tag.idx[0], tag.idx[1]
        if m.c[k0] == m.o[k0]:
            continue
        d = 1 if m.c[k0] > m.o[k0] else -1
        ref = m.o[k1]
        stop = m.l[k0] if d > 0 else m.h[k0]
        abst = (ref - stop) * d
        if abst > 0:
            out.append(Setup(tag.datum, int(k1), float(ref), d, float(abst), float(p["ziel_r"] * abst),
                             int(tag.idx[-1]), schluss=True))
    return out


def s_vorbereich(m: Markt, p: dict) -> list[Setup]:
    """London-Breakout, verallgemeinert: Bereich = alle Kerzen von Mitternacht (Ortszeit der Sitzung) bis
    Sitzungsbeginn (bei Devisen 0 bis 8 Uhr London = Asien-Sitzung). Ausbruch per Stop-Order während der Sitzung."""
    out = []
    for tag in m.tage:
        k0 = int(tag.idx[0])
        j0 = int(np.searchsorted(m.lokal, m.lokal[k0].normalize()))
        if k0 - j0 < p["min_kerzen"]:
            continue
        r = np.arange(j0, k0)
        s = bereich_ausbruch(m, tag, 0, float(m.h[r].max()), float(m.l[r].min()), p["stop"], p.get("ziel_r"))
        if s:
            out.append(s)
    return out


def s_vortag_ausbruch(m: Markt, p: dict) -> list[Setup]:
    """Ausbruch über Vortageshoch oder unter Vortagestief (Sitzung), nur wenn die Sitzung innerhalb der Vortagesspanne
    eröffnet. Stop `stop_anteil` x Vortagesspanne hinter der Marke, Ziel `ziel_r` x Risiko, sonst Sitzungsschluss."""
    out = []
    for tag in m.tage:
        if tag.vor is None:
            continue
        ph, pl = tag_hoch_tief(m, tag.vor)
        if not pl < m.o[tag.idx[0]] < ph:
            continue
        hit = ausbruch(m, einstiegs_kerzen(tag, 0), ph, pl)
        if hit is None:
            continue
        k, d = hit
        marke = ph if d > 0 else pl
        s = stop_einstieg(m, tag, k, d, marke, marke - d * p["stop_anteil"] * (ph - pl), p.get("ziel_r"))
        if s:
            out.append(s)
    return out


def s_fehlausbruch_vortag(m: Markt, p: dict) -> list[Setup]:
    """Turtle Soup im Tag: Die erste Kerze, die über das Vortageshoch (unter das Vortagestief) sticht, schließt wieder
    darunter (darüber) -> Gegenrichtung zur Eröffnung der nächsten Kerze, Stop am Extrem dieser Kerze, Ziel `ziel_r` x
    Risiko, sonst Sitzungsschluss. Schließt die erste Kerze jenseits der Marke (echter Ausbruch), kein Trade an dem Tag."""
    out = []
    for tag in m.tage:
        if tag.vor is None:
            continue
        ph, pl = tag_hoch_tief(m, tag.vor)
        if not pl < m.o[tag.idx[0]] < ph:
            continue
        kand = einstiegs_kerzen(tag, 0)[:-1]                   # Einstieg erst in der Kerze danach
        for j, k in enumerate(kand):
            hoch, tief = m.h[k] > ph, m.l[k] < pl
            if not (hoch or tief):
                continue
            if hoch and tief:
                break
            if hoch and m.c[k] < ph:
                d, stop = -1, float(m.h[k])
            elif tief and m.c[k] > pl:
                d, stop = 1, float(m.l[k])
            else:
                break
            k1 = int(tag.idx[np.searchsorted(tag.idx, k) + 1])
            ref = float(m.o[k1])
            abst = (ref - stop) * d
            if abst > 0:
                out.append(Setup(tag.datum, k1, ref, d, abst, float(p["ziel_r"] * abst), int(tag.idx[-1]),
                                 schluss=True))
            break
    return out


def s_gap_fill(m: Markt, p: dict) -> list[Setup]:
    """Gap Fill: Sitzung eröffnet mit Lücke zum Vortagesschluss, Lücke zwischen min_adr und max_adr x mittlere
    Tagesspanne (14 Sitzungen). Einstieg zur Eröffnung gegen die Lücke, Ziel = Vortagesschluss, Stop `stop_r` x Lücke
    auf der anderen Seite, sonst Sitzungsschluss."""
    out = []
    for tag in m.tage:
        a = adr(m, tag, 14)
        if a is None:
            continue
        vs = float(m.c[tag.vor.idx[-1]])
        k = int(tag.idx[0])
        o0 = float(m.o[k])
        gap = o0 / vs - 1
        if not p["min_adr"] * a <= abs(gap) <= p["max_adr"] * a:
            continue
        d = -1 if gap > 0 else 1
        abst = abs(o0 - vs)
        out.append(Setup(tag.datum, k, o0, d, float(p["stop_r"] * abst), float(abst), int(tag.idx[-1]), schluss=True))
    return out


def s_larry_williams(m: Markt, p: dict) -> list[Setup]:
    """Volatilitätsausbruch nach Larry Williams: Stop-Order bei Eröffnung +/- k x Vortagesspanne, erster Ausbruch des
    Tages, Stop zurück an der Eröffnung, kein Ziel, raus zum Sitzungsschluss."""
    out = []
    for tag in m.tage:
        if tag.vor is None:
            continue
        ph, pl = tag_hoch_tief(m, tag.vor)
        o0 = float(m.o[tag.idx[0]])
        oben, unten = o0 + p["k"] * (ph - pl), o0 - p["k"] * (ph - pl)
        hit = ausbruch(m, einstiegs_kerzen(tag, 0), oben, unten)
        if hit is None:
            continue
        k, d = hit
        s = stop_einstieg(m, tag, k, d, oben if d > 0 else unten, o0, p.get("ziel_r"))
        if s:
            out.append(s)
    return out


def s_intraday_momentum(m: Markt, p: dict) -> list[Setup]:
    """Gao/Han/Li/Zhou: Rendite vom Vortagesschluss bis Ende der ersten halben Stunde -> Richtung der letzten halben
    Stunde. Einstieg zur Eröffnung der vorletzten Kerze, raus zum Schluss der letzten."""
    out = []
    for tag in m.tage:
        if tag.vor is None:
            continue
        vor_schluss = m.c[tag.vor.idx[-1]]
        r1 = m.c[tag.idx[1]] / vor_schluss - 1
        if r1 == 0:
            continue
        d = 1 if r1 > 0 else -1
        k = tag.idx[-2]
        out.append(Setup(tag.datum, int(k), float(m.o[k]), d, nan(), nan(), int(tag.idx[-1]), schluss=True))
    return out


def noise_band_trades(m: Markt, p: dict, nur_long: bool = False) -> list[Setup]:
    """Zarattini/Aziz/Barbon 2024, auf die Sitzung des Markts übertragen (Prüfung jede halbe Stunde). Liefert die
    echten Trades als Setups ohne Stop mit festem Ausstiegszeitpunkt (der Ausstieg folgt aus Band und VWAP)."""
    out = []
    bewegungen: list[np.ndarray] = []
    n = min(len(t.idx) for t in m.tage) if m.tage else 0
    for tag in m.tage:
        idx = tag.idx[:n]
        o0 = m.o[idx[0]]
        bew = np.abs(m.c[idx] / o0 - 1)
        if len(bewegungen) >= 14 and tag.vor is not None:
            sig = np.mean(bewegungen[-14:], axis=0)
            vs = m.c[tag.vor.idx[-1]]
            ub = max(o0, vs) * (1 + p["vm"] * sig)
            lb = min(o0, vs) * (1 - p["vm"] * sig)
            tp = (m.h[idx] + m.l[idx] + m.c[idx]) / 3
            vw = np.cumsum(tp) / np.arange(1, len(idx) + 1)
            pos, k_ein = 0, 0
            for k in range(1, len(idx) - 1, 2):            # Schluss der Kerzen nach 30, 60, ... Minuten
                if pos == 0:
                    if m.c[idx[k]] > ub[k]:
                        pos = 1
                    elif m.c[idx[k]] < lb[k] and not nur_long:
                        pos = -1
                    if pos:
                        k_ein = k + 1
                else:
                    raus = m.c[idx[k]] < max(ub[k], vw[k]) if pos == 1 else m.c[idx[k]] > min(lb[k], vw[k])
                    if raus:
                        out.append(Setup(tag.datum, int(idx[k_ein]), float(m.o[idx[k_ein]]), pos, nan(), nan(),
                                         int(idx[k + 1])))
                        pos = 0
            if pos:
                out.append(Setup(tag.datum, int(idx[k_ein]), float(m.o[idx[k_ein]]), pos, nan(), nan(),
                                 int(idx[-1]), schluss=True))
        bewegungen.append(bew)
    return out


def s_noise_band(m: Markt, p: dict) -> list[Setup]:
    return noise_band_trades(m, p, nur_long=False)


def s_noise_band_long(m: Markt, p: dict) -> list[Setup]:
    return noise_band_trades(m, p, nur_long=True)


STRATEGIEN = {
    "orb": s_orb,
    "orb_richtung": s_orb_richtung,
    "vorbereich": s_vorbereich,
    "vortag_ausbruch": s_vortag_ausbruch,
    "fehlausbruch_vortag": s_fehlausbruch_vortag,
    "gap_fill": s_gap_fill,
    "larry_williams": s_larry_williams,
    "intraday_momentum": s_intraday_momentum,
    "noise_band": s_noise_band,
    "noise_band_long": s_noise_band_long,
}


# --------------------------------------------------------------------------------------------------------------------
# Lauf

def fenster(tr_or_setups, von: str, bis: str) -> list:
    return [x for x in tr_or_setups if von <= (x.datum if isinstance(x, Setup) else x["datum"]) <= bis]


def markt_job(args) -> dict:
    path, info, cfg, seed = args
    try:
        return _markt_job(path, info, cfg, seed)
    except Exception as err:          # noqa: BLE001  ein Markt stoppt nicht die Runde
        return {"epic": info["epic"], "fehler": repr(err)}


def passt(strat: dict, epic: str, typ: str) -> bool:
    m = strat.get("maerkte", "alle")
    if m == "alle":
        return True
    return epic in m or typ in m


def null_pf(r_long: np.ndarray, r_short: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    """Gewinnfaktoren von n Zufallsläufen: je Setup zufällig Long oder Short (gleiche Zeit, gespiegelte Abstände)."""
    wahl = rng.random((n, len(r_long))) < 0.5
    r = np.where(wahl, r_long, r_short)
    g = np.where(r > 0, r, 0.0).sum(1)
    v = -np.where(r < 0, r, 0.0).sum(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        pf = np.where(v > 0, g / np.where(v > 0, v, 1.0), np.where(g > 0, 99.0, 0.0))
    return pf.astype(np.float32)


def _markt_job(path, info, cfg, seed) -> dict:
    epic, typ = info["epic"], info["typ"]
    cache: dict = {}
    rng = np.random.default_rng(seed)
    a_von, a_bis = cfg["auswahl"]
    s_von, s_bis = cfg["siegel"]
    n_null = cfg["zufall"]["laeufe"]
    faktor = cfg["kosten"]["spread_faktor_robust"]
    out = {"epic": epic, "typ": typ, "name": (info.get("meta") or {}).get("name"), "sitzung": sitzung_fuer(epic, typ),
           "tage": {}, "strategien": {}}
    for name, strat in cfg["strategien"].items():
        if not passt(strat, epic, typ):
            continue
        sitz = strat.get("sitzung") or sitzung_fuer(epic, typ)
        if sitz not in cache:
            cache[sitz] = baue_markt(path, epic, typ, sitzung=sitz)
            out["tage"][sitz] = len(cache[sitz].tage)
        m = cache[sitz]
        setups = STRATEGIEN[strat.get("logik", name)](m, strat.get("parameter", {}))
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


def auswerten(maerkte: list[dict], cfg: dict) -> dict:
    regel = cfg["regel"]
    ergebnis = {}
    for name in cfg["strategien"]:
        zeilen = []
        for mk in maerkte:
            s = (mk.get("strategien") or {}).get(name)
            if not s or mk["epic"] in regel.get("nie", []):
                continue
            zeilen.append((mk, s))
        echt = [(mk, s) for mk, s in zeilen if s["auswahl"]["trades"] >= regel["min_trades"]]
        ueber = [(mk, s) for mk, s in echt if (s["auswahl"]["pf"] or 0) > regel["min_pf"]]
        ueber.sort(key=lambda x: (x[1]["auswahl"]["pf"], x[1]["auswahl"]["trades"]), reverse=True)
        # Glückstest: bester Markt je Zufallslauf, über dieselben Märkte mit genug Trades
        if echt:
            mat = np.stack([s["null_pf"] for mk, s in echt])
            beste_zufall = mat.max(axis=0)
            anzahl_zufall = (mat > regel["min_pf"]).sum(axis=0)
        else:
            beste_zufall = anzahl_zufall = np.zeros(0)
        rang = []
        for mk, s in ueber[:10]:
            pf = s["auswahl"]["pf"]
            pz_markt = round(100 * float(np.mean(s["null_pf"] < pf)), 1) if len(s["null_pf"]) else None
            pz_max = round(100 * float(np.mean(beste_zufall < pf)), 1) if len(beste_zufall) else None
            rang.append({"epic": mk["epic"], "name": mk["name"], "typ": mk["typ"], "sitzung": s["sitzung"],
                         "auswahl": s["auswahl"], "siegel": s["siegel"], "zufall_perzentil_markt": pz_markt,
                         "zufall_perzentil_bester_markt": pz_max})
        sieger = rang[0] if rang else None
        if sieger:
            sg = sieger["siegel"]
            sieger["besteht"] = {
                "glueck": (sieger["zufall_perzentil_bester_markt"] or 0) >= regel["min_perzentil_bester_markt"],
                "robust": (sieger["auswahl"]["pf_robust"] or 0) > regel["min_pf_robust"],
                "siegel": sg["trades"] >= regel["siegel_min_trades"] and (sg["pf"] or 0) > regel["siegel_min_pf"],
            }
            sieger["demo"] = all(sieger["besteht"].values())
        ergebnis[name] = {
            "maerkte": len(zeilen), "mit_genug_trades": len(echt), "ueber_schwelle": len(ueber),
            "ueber_schwelle_zufall_im_schnitt": round(float(np.mean(anzahl_zufall)), 1) if len(anzahl_zufall) else None,
            "bester_zufall_pf_median": round(float(np.median(beste_zufall)), 3) if len(beste_zufall) else None,
            "bester_zufall_pf_95": round(float(np.percentile(beste_zufall, 95)), 3) if len(beste_zufall) else None,
            "rangliste": rang, "sieger": sieger,
        }
    return ergebnis


def run(kerzen: pathlib.Path, out: pathlib.Path) -> dict:
    cfg_all = check_vorab()
    cfg = cfg_all["runde_4"]
    out.mkdir(parents=True, exist_ok=True)
    report = json.loads((kerzen / "bericht_runde3.json").read_text(encoding="utf-8"))
    infos = [mk for mk in report["maerkte"] if mk.get("kerzen", {}).get("anzahl") and mk["epic"] not in cfg["ohne"]]
    seed = cfg["zufall"]["seed"]
    jobs = [(kerzen / f"{mk['epic']}_MINUTE_15.csv.gz", mk, cfg, seed + i) for i, mk in enumerate(infos)]
    with ProcessPoolExecutor(max_workers=4) as ex:
        maerkte = list(ex.map(markt_job, jobs, chunksize=2))
    ergebnis = auswerten(maerkte, cfg)
    np.savez_compressed(out / "runde4_zufall.npz", **{f"{mk['epic']}|{n}": st.pop("null_pf")
                                                       for mk in maerkte for n, st in (mk.get("strategien") or {}).items()})
    payload = {"made": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
               "vorab_sha256": sha256_text(VORAB.read_text(encoding="utf-8")),
               "ergebnis": ergebnis, "fehler": [mk for mk in maerkte if mk.get("fehler")], "maerkte": maerkte}
    (out / "runde4.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    kurz = {n: {"sieger": (e["sieger"] or {}).get("epic"), "pf": ((e["sieger"] or {}).get("auswahl") or {}).get("pf"),
                "demo": (e["sieger"] or {}).get("demo"), "ueber_schwelle": e["ueber_schwelle"],
                "zufall": e["ueber_schwelle_zufall_im_schnitt"]} for n, e in ergebnis.items()}
    journal_add("Runde 4 gerechnet: " + json.dumps(kurz, ensure_ascii=False))
    return payload


def main(argv: list[str]) -> int:
    if argv[:1] == ["--festlegen"]:
        text = VORAB.read_text(encoding="utf-8")
        journal_add(f"Runde 4 festgelegt, Grund: {argv[1]}. {KEY}{sha256_text(text)}")
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
