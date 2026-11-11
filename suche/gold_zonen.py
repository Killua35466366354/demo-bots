"""Gold-Zonen und News: Swing-Trades an Unterstützungs- und Widerstandszonen des 4-Std.-Charts (nur Rechnung, kein Bot).

Kirons Wunsch vom 11.11.2026 09:47 UTC. Regeln, Kosten und Hürden stehen in suche/VORAB_gold_zonen.yaml und sind dort
festgelegt, bevor gerechnet wurde (Prüfsumme im Protokoll). Dieser Code liest seine Werte aus der Datei, er hat keine
eigenen Stellschrauben.

- A "Abpraller": Long an der Unterstützung, Short am Widerstand, Limit-Order außen oder innen an der Zone, Stop 0,25 ATR
  hinter der Zone, mit oder ohne Hintergrund-Filter.
- B "Bruch mit Rollenwechsel": Schließt eine 4-Std.-Kerze jenseits der Zone, wird das alte Hoch zur neuen Unterstützung.
  Einstieg beim Rücklauf, einmal nur nach wichtigen US-Terminen (B_news), einmal nach jedem Bruch (B_alle).
- Führung für alle gleich: Einstand nach 2 R, Ziel die nächste Zone der Gegenseite (ab 4 R, sonst 10 R), 14 Tage.

    python -m suche.gold_zonen --festlegen "Grund"     # Prüfsumme ins Protokoll, BEVOR gerechnet wird
    python -m suche.gold_zonen <Ordner mit XAUUSD_5min.csv.gz>   # rechnet, schreibt suche/ergebnis_gold_zonen.json/.md

Ohne passende Prüfsumme im Protokoll rechnet das Programm nicht.
"""
from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_gold_zonen.yaml"
KEY = "VORAB_gold_zonen sha256 "
ERGEBNIS = ROOT / "suche" / "ergebnis_gold_zonen"
NY = "America/New_York"

# Die Werte der versiegelten Regel in Zahlen. tests/test_gold_zonen.py prüft, dass sie zum Text der Datei passen.
SWING = 5
ZONE_MIN_ATR, ZONE_MAX_ATR = 0.15, 0.75
STOP_ATR = 0.25
ABLAUF_KERZEN = 180
RUECKLAUF_KERZEN = 30
NEWS_STUNDEN = 24
EINSTAND_R, ZIEL_MIN_R, ZIEL_SONST_R = 2.0, 4.0, 10.0
HALTE_TAGE = 14
HG_SMA_TAGE, HG_EMA_4H = 50, 50
HAUPT_VON, HAUPT_BIS = pd.Timestamp("2024-01-01"), pd.Timestamp("2026-10-31")
MITTE = HAUPT_VON + (pd.Timestamp("2026-10-30") - HAUPT_VON) / 2


def regel() -> dict:
    return yaml.safe_load(VORAB.read_text(encoding="utf-8"))["gold_zonen"]


def vorab_ok() -> bool:
    from suche.runde1 import journal_lines, last_value, sha256_text
    return VORAB.exists() and last_value(journal_lines(), KEY) == sha256_text(VORAB.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------------------------------------------------
# Kerzen

@dataclass
class Markt:
    """5-Minuten-Bid-Kerzen, dazu die 4-Std.-Kerzen (Beginn 18, 22, 2, 6, 10, 14 Uhr New York) und die Handelstage."""
    t: np.ndarray            # datetime64[ns] UTC, Beginn der 5-Minuten-Kerze
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    tag: np.ndarray          # Handelstag (endet 17:00 New York) als Zahl
    k_bis: np.ndarray        # letzte 5-Minuten-Kerze jeder 4-Std.-Kerze
    o4: np.ndarray
    h4: np.ndarray
    l4: np.ndarray
    c4: np.ndarray
    atr4: np.ndarray
    hg: np.ndarray           # Hintergrund je 4-Std.-Kerze: +1 kein Short, -1 kein Long, 0 beides erlaubt
    monat: np.ndarray        # Kalendermonat (UTC) je 5-Minuten-Kerze als Zahl

    def __len__(self) -> int:
        return len(self.t)


def atr_wilder(h: np.ndarray, lo: np.ndarray, c: np.ndarray, n: int = 14) -> np.ndarray:
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.vstack([h - lo, np.abs(h - pc), np.abs(lo - pc)]), axis=0)
    out = np.full(len(h), np.nan)
    if len(h) < n:
        return out
    out[n - 1] = tr[:n].mean()
    for i in range(n, len(h)):
        out[i] = out[i - 1] + (tr[i] - out[i - 1]) / n
    return out


def _gruppen(g: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    neu = np.r_[True, g[1:] != g[:-1]]
    i0 = np.flatnonzero(neu)
    return i0, np.r_[i0[1:] - 1, len(g) - 1]


def markt(bars: pd.DataFrame) -> Markt:
    """bars: 5-Minuten-Bid-Kerzen mit UTC-Index (naiv) und open, high, low, close."""
    bars = bars[~bars.index.duplicated(keep="last")].sort_index()
    idx = pd.DatetimeIndex(bars.index)
    ny = idx.tz_localize("UTC").tz_convert(NY).tz_localize(None)
    o, h, lo, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    tag = (ny + pd.Timedelta(hours=7)).normalize().values.astype("datetime64[D]").astype(np.int64)
    i0, i1 = _gruppen(np.asarray((ny + pd.Timedelta(hours=6)).floor("4h").values))
    o4, h4, l4, c4 = o[i0], np.maximum.reduceat(h, i0), np.minimum.reduceat(lo, i0), c[i1]
    # Hintergrund wie gold/hand_bot.py: Tagesschluss gegen den Schnitt der letzten 50 Tagesschlüsse, 4-Std.-Schluss
    # gegen EMA 50. Je 4-Std.-Kerze der Stand an ihrem Schluss, mit dem letzten Tag, der dann schon fertig ist.
    _, d1 = _gruppen(tag)
    cd = pd.Series(c[d1])
    a_tag = np.sign((cd - cd.rolling(HG_SMA_TAGE).mean()).to_numpy())            # nan, solange 50 Tage fehlen
    letzter_tag = np.searchsorted(d1, i1, side="right") - 1                      # letzter Tag mit Schluss bis hier
    a = np.where(letzter_tag >= 0, a_tag[np.maximum(letzter_tag, 0)], np.nan)
    ema = pd.Series(c4).ewm(span=HG_EMA_4H, adjust=False).mean().to_numpy()
    f = np.sign(c4 - ema)
    f[:HG_EMA_4H + 10 - 1] = np.nan                                              # wie der Hand-Bot: ab 60 Kerzen
    hg = np.where((a > 0) & (f > 0), 1, np.where((a < 0) & (f < 0), -1, 0)).astype(int)
    monat = (idx.year * 12 + idx.month).to_numpy()
    return Markt(idx.values.astype("datetime64[ns]"), o, h, lo, c, tag, i1, o4, h4, l4, c4, atr_wilder(h4, l4, c4, 14),
                 hg, monat)


# ---------------------------------------------------------------------------------------------------------------------
# Zonen

@dataclass
class Zone:
    typ: int                 # +1 Unterstützung (Long), -1 Widerstand (Short)
    aussen: float            # das Swing-Tief bzw. Swing-Hoch
    innen: float             # Rand zum Kurs hin
    atr: float
    k_best: int              # 4-Std.-Kerze, an deren Schluss die Zone bestätigt ist
    k_ende: int              # letzte 4-Std.-Kerze als Abpraller-Zone (Bruch-Kerze oder Ablauf)
    k_bruch: int             # 4-Std.-Kerze des Bruchs, -1 ohne Bruch
    atr_bruch: float = float("nan")


def zonen(o4, h4, l4, c4, atr4) -> list[Zone]:
    """Alle Zonen aus bestätigten Swing-Hochs und Swing-Tiefs, in der Reihenfolge ihrer Bestätigung."""
    n, out = SWING, []
    letzte = len(c4) - 1
    for k in range(2 * n, len(c4)):
        i = k - n
        atr = atr4[k]
        if not np.isfinite(atr) or atr <= 0:
            continue
        for typ in (-1, 1):
            if typ < 0:
                ist = h4[i] > h4[i - n:i].max() and h4[i] >= h4[i + 1:k + 1].max()
                aussen, koerper = h4[i], max(o4[i], c4[i])
            else:
                ist = l4[i] < l4[i - n:i].min() and l4[i] <= l4[i + 1:k + 1].min()
                aussen, koerper = l4[i], min(o4[i], c4[i])
            if not ist:
                continue
            hoehe = float(np.clip(abs(aussen - koerper), ZONE_MIN_ATR * atr, ZONE_MAX_ATR * atr))
            ablauf = min(k + ABLAUF_KERZEN, letzte)
            spaeter = c4[k + 1:ablauf + 1]
            durch = np.flatnonzero(spaeter > aussen if typ < 0 else spaeter < aussen)
            kb = k + 1 + int(durch[0]) if len(durch) else -1
            out.append(Zone(typ, float(aussen), float(aussen + typ * hoehe), float(atr), k, kb if kb >= 0 else ablauf,
                            kb, float(atr4[kb]) if kb >= 0 else float("nan")))
    return out


def _erster(mask: np.ndarray) -> int:
    k = int(np.argmax(mask)) if len(mask) else 0
    return k if len(mask) and mask[k] else -1


def _fuellung(m: Markt, d: int, linie: float, j0: int, j1: int, sp: float) -> tuple[int, float]:
    """Erste 5-Minuten-Kerze in j0..j1, in der die Limit-Order füllt, und der Füllkurs. (-1, nan) ohne Füllung."""
    if j0 > j1 or j0 >= len(m):
        return -1, float("nan")
    j1 = min(j1, len(m) - 1)
    k = _erster(m.l[j0:j1 + 1] + sp <= linie) if d > 0 else _erster(m.h[j0:j1 + 1] >= linie)
    if k < 0:
        return -1, float("nan")
    j = j0 + k
    return j, float(min(m.o[j] + sp, linie) if d > 0 else max(m.o[j], linie))


def kandidaten_abpraller(m: Markt, zz: list[Zone], einstieg: str, sp: float) -> list[dict]:
    """Je Zone die erste Berührung der Einstiegslinie, solange sie als Abpraller gilt."""
    out = []
    for q, z in enumerate(zz):
        linie = z.aussen if einstieg == "aussen" else z.innen
        j, fill = _fuellung(m, z.typ, linie, int(m.k_bis[z.k_best]) + 1, int(m.k_bis[z.k_ende]), sp)
        if j < 0 or z.typ * (fill - z.aussen) < 0:               # keine Berührung oder Kurslücke hinter die Zone
            continue
        out.append({"j": j, "zone": q, "d": z.typ, "fill": fill, "stop": z.aussen - z.typ * STOP_ATR * z.atr})
    return sorted(out, key=lambda x: (x["j"], x["zone"]))


def nach_news(m: Markt, k: int, termine: np.ndarray) -> bool:
    """Lag ein Termin in den 24 Stunden vor dem Schluss der 4-Std.-Kerze k (später als Schluss minus 24 Std., bis zum
    Schluss)? Schluss = Ende ihrer letzten 5-Minuten-Kerze."""
    schluss = m.t[m.k_bis[k]] + np.timedelta64(5, "m")
    a = np.searchsorted(termine, schluss - np.timedelta64(NEWS_STUNDEN, "h"), side="right")
    return bool(a < len(termine) and termine[a] <= schluss)


def kandidaten_bruch(m: Markt, zz: list[Zone], nur_news: bool, termine: np.ndarray, sp: float) -> list[dict]:
    """Je gebrochener Zone der Rücklauf an ihre äußere Linie, in Richtung des Bruchs."""
    out = []
    letzte = len(m.c4) - 1
    for q, z in enumerate(zz):
        kb = z.k_bruch
        if kb < 0 or kb >= letzte or (nur_news and not nach_news(m, kb, termine)):
            continue
        d = -z.typ                                               # Widerstand nach oben gebrochen: Long
        ende = min(kb + RUECKLAUF_KERZEN, letzte)
        spaeter = m.c4[kb + 1:ende + 1]
        zurueck = np.flatnonzero(spaeter < z.innen if d > 0 else spaeter > z.innen)
        if len(zurueck):
            ende = kb + 1 + int(zurueck[0])
        j, fill = _fuellung(m, d, z.aussen, int(m.k_bis[kb]) + 1, int(m.k_bis[ende]), sp)
        if j < 0 or d * (fill - z.innen) < 0:
            continue
        out.append({"j": j, "zone": q, "d": d, "fill": fill, "stop": z.innen - d * STOP_ATR * z.atr_bruch})
    return sorted(out, key=lambda x: (x["j"], x["zone"]))


def ziel_fuer(m: Markt, zz: list[Zone], k_best: np.ndarray, j: int, d: int, fill: float, r: float) -> float:
    """Innere Linie der nächstgelegenen gültigen Zone der Gegenseite, die mindestens 4 R entfernt ist (nähere werden
    übersprungen). Gibt es keine, 10 R. Gültig: bei der Füllung bestätigt, nicht gebrochen, nicht abgelaufen."""
    k4 = int(np.searchsorted(m.k_bis, j, side="left")) - 1       # letzte fertige 4-Std.-Kerze
    a = int(np.searchsorted(k_best, k4 - ABLAUF_KERZEN, side="left"))
    b = int(np.searchsorted(k_best, k4, side="right"))
    bestes = None
    for z in zz[a:b]:
        if z.typ != -d or (z.k_bruch >= 0 and z.k_bruch <= k4) or z.k_best + ABLAUF_KERZEN < k4:
            continue
        if d * (z.innen - fill) >= ZIEL_MIN_R * r and (bestes is None or d * (z.innen - bestes) < 0):
            bestes = z.innen
    return float(bestes) if bestes is not None else fill + d * ZIEL_SONST_R * r


# ---------------------------------------------------------------------------------------------------------------------
# Führung

def fuehre(m: Markt, d: int, j: int, fill: float, stop: float, ziel: float, sp: float, satz: float) -> dict:
    """Ein Trade ab der 5-Minuten-Kerze j. Rückgabe: r (nach Spread und Übernachtgebühr), j_aus, exit, grund."""
    r = abs(fill - stop)
    jz = int(np.searchsorted(m.t, m.t[j] + np.timedelta64(HALTE_TAGE, "D"), side="left"))
    ende = min(jz, len(m))
    if d > 0:
        gegen, dafuer, auf = m.l[j:ende], m.h[j:ende], m.o[j:ende]
        ks = _erster(gegen <= stop)
        k2 = _erster(dafuer[1:] >= fill + EINSTAND_R * r)
        kz = _erster(dafuer[1:] >= ziel)
    else:
        gegen, dafuer, auf = m.h[j:ende] + sp, m.l[j:ende] + sp, m.o[j:ende] + sp
        ks = _erster(gegen >= stop)
        k2 = _erster(dafuer[1:] <= fill - EINSTAND_R * r)
        kz = _erster(dafuer[1:] <= ziel)
    k2, kz = (k2 + 1 if k2 >= 0 else -1), (kz + 1 if kz >= 0 else -1)

    def raus(k: int, kurs: float, grund: str) -> dict:
        ja = min(j + k, len(m) - 1)
        naechte = max(int(m.tag[ja] - m.tag[j]), 0)
        wert = d * (kurs - fill) / r - satz / 100.0 / 365.0 * naechte * fill / r
        return {"r": float(wert), "j_aus": ja, "exit": float(kurs), "grund": grund}

    if ks >= 0 and (k2 < 0 or ks <= k2):                         # Stop zuerst (auch in derselben Kerze)
        kurs = stop if ks == 0 else (min(auf[ks], stop) if d > 0 else max(auf[ks], stop))
        return raus(ks, kurs, "stop")
    if k2 >= 0:                                                  # 2 R erreicht: ab der nächsten Kerze Stop am Einstieg
        rest = gegen[k2 + 1:]
        ke = _erster(rest <= fill) if d > 0 else _erster(rest >= fill)
        ke = k2 + 1 + ke if ke >= 0 else -1
        if kz >= 0 and (ke < 0 or kz < ke):
            return raus(kz, max(auf[kz], ziel) if d > 0 else min(auf[kz], ziel), "ziel")
        if ke >= 0:
            return raus(ke, min(auf[ke], fill) if d > 0 else max(auf[ke], fill), "einstand")
    if jz < len(m):                                              # Zeit um: zur nächsten Eröffnung
        return raus(jz - j, m.o[jz] if d > 0 else m.o[jz] + sp, "zeit")
    n = len(m) - 1
    return raus(n - j, m.c[n] if d > 0 else m.c[n] + sp, "datenende")


def handle(m: Markt, zz: list[Zone], kand: list[dict], filter_hg: bool, sp: float, satz: dict) -> list[dict]:
    """Kandidaten der Reihe nach, höchstens ein Trade gleichzeitig. Was nicht genommen wird, verfällt."""
    k_best = np.array([z.k_best for z in zz], dtype=int)
    out, frei_ab = [], -1
    for x in kand:
        j, d = x["j"], x["d"]
        if j <= frei_ab:
            continue
        if filter_hg:
            k4 = int(np.searchsorted(m.k_bis, j, side="left")) - 1
            if k4 >= 0 and m.hg[k4] == -d:
                continue
        r = abs(x["fill"] - x["stop"])
        if not r > 0:
            continue
        ziel = ziel_fuer(m, zz, k_best, j, d, x["fill"], r)
        t = fuehre(m, d, j, x["fill"], x["stop"], ziel, sp, satz[d])
        frei_ab = t["j_aus"]
        out.append({"zeit": pd.Timestamp(m.t[j]), "j": j, "d": d, "fill": round(x["fill"], 3), "stop": round(x["stop"], 3),
                    "r_usd": round(r, 3), "ziel_r": round(d * (ziel - x["fill"]) / r, 3), "zeit_aus": pd.Timestamp(m.t[t["j_aus"]]),
                    "exit": round(t["exit"], 3), "grund": t["grund"], "r": round(t["r"], 4)})
    return out


def rechne(m: Markt, zz: list[Zone], v: dict, termine: np.ndarray, sp: float, satz: dict) -> list[dict]:
    if v["familie"] == "abpraller":
        return handle(m, zz, kandidaten_abpraller(m, zz, v["einstieg"], sp), v["filter"] == "hintergrund", sp, satz)
    return handle(m, zz, kandidaten_bruch(m, zz, bool(v["news"]), termine, sp), False, sp, satz)


# ---------------------------------------------------------------------------------------------------------------------
# Bewertung

def pf(r: np.ndarray) -> float | None:
    g, v = float(r[r > 0].sum()), float(-r[r < 0].sum())
    return round(g / v, 2) if v > 0 else None


def kennzahlen(trades: list[dict]) -> dict:
    r = np.array([t["r"] for t in trades], dtype=float)
    if not len(r):
        return {"trades": 0, "pf": None, "summe_r": 0.0, "treffer": None, "rueckgang_r": 0.0}
    eq = np.cumsum(r)
    return {"trades": int(len(r)), "pf": pf(r), "summe_r": round(float(r.sum()), 1),
            "treffer": round(float((r > 0).mean() * 100), 1),
            "rueckgang_r": round(float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()), 1)}


def fenster(trades: list[dict], von, bis) -> list[dict]:
    return [t for t in trades if von <= t["zeit"] < bis]


def zufall(m: Markt, trades: list[dict], sp: float, satz: dict, laeufe: int, seed: int) -> dict:
    """Je Trade ein Zwilling in dieselbe Richtung zu einer zufälligen 5-Minuten-Kerze im selben Kalendermonat."""
    if not trades:
        return {"geschlagen_pct": None, "p": 1.0, "median_r": None}
    rng = np.random.default_rng(seed)
    mon = m.monat
    grenzen = {int(x): (int(np.searchsorted(mon, x, side="left")), int(np.searchsorted(mon, x, side="right")))
               for x in np.unique(mon[[t["j"] for t in trades]])}
    summen = np.zeros(laeufe)
    for t in trades:
        a, b = grenzen[int(mon[t["j"]])]
        d, r = t["d"], t["r_usd"]
        for q, j in enumerate(rng.integers(a, b, size=laeufe)):
            fill = m.o[j] + sp if d > 0 else m.o[j]
            summen[q] += fuehre(m, d, int(j), float(fill), float(fill - d * r), float(fill + d * t["ziel_r"] * r), sp,
                                satz[d])["r"]
    echt = sum(t["r"] for t in trades)
    return {"geschlagen_pct": round(float((summen < echt).mean() * 100), 1),
            "p": max(float((summen >= echt).mean()), 1.0 / (laeufe + 1)),
            "median_r": round(float(np.median(summen)), 1)}


def holm(ps: dict[str, float], alpha: float = 0.05) -> dict[str, bool]:
    """Holm über alle Varianten: die k-kleinste p muss höchstens alpha / (m - k + 1) sein, sonst fällt sie und alle
    größeren durch."""
    reihe = sorted(ps, key=lambda k: (ps[k], k))
    out, offen = {}, True
    for k, name in enumerate(reihe):
        offen = offen and ps[name] <= alpha / (len(reihe) - k)
        out[name] = offen
    return out


def bewerte(trades: list[dict], robust: list[dict]) -> dict:
    h = fenster(trades, HAUPT_VON, HAUPT_BIS)
    wochen = (HAUPT_BIS - HAUPT_VON).days / 7
    k = kennzahlen(h)
    h1, h2 = kennzahlen(fenster(h, HAUPT_VON, MITTE)), kennzahlen(fenster(h, MITTE, HAUPT_BIS))
    j26 = kennzahlen(fenster(h, pd.Timestamp("2026-01-01"), HAUPT_BIS))
    gr: dict[str, int] = {}
    for t in h:
        gr[t["grund"]] = gr.get(t["grund"], 0) + 1
    return {**k, "je_woche": round(k["trades"] / wochen, 2), "robust_pf": kennzahlen(fenster(robust, HAUPT_VON, HAUPT_BIS))["pf"],
            "h1": (h1["pf"], h1["trades"]), "h2": (h2["pf"], h2["trades"]), "j2026": (j26["pf"], j26["trades"]),
            "long": kennzahlen([t for t in h if t["d"] > 0]), "short": kennzahlen([t for t in h if t["d"] < 0]),
            "gruende": gr, "vor_2024": kennzahlen(fenster(trades, pd.Timestamp("2015-01-01"), HAUPT_VON))}


def _z(x, n: int = 2) -> str:
    return "–" if x is None else f"{x:.{n}f}".replace(".", ",")


def bericht(res: dict) -> str:
    zeilen = ["# Gold-Zonen und News: Ergebnis", "",
              f"Regeln: suche/VORAB_gold_zonen.yaml (Prüfsumme {res['vorab_sha256'][:8]} im Protokoll, festgelegt vor der "
              "Rechnung). Daten: XAUUSD 5 Min. (HistData), Spread 0,50 USD, Übernachtgebühr eingerechnet.",
              f"Zonen im ganzen Zeitraum: {res['zonen']}. Hauptfenster: Einstieg 01.01.2024 bis 30.10.2026.", "",
              "| Variante | Trades | je Woche | Gewinnfaktor | Summe R | Treffer | 1,5x Kosten | Hälfte 1 | Hälfte 2 | 2026 | "
              "Zufall | Holm | bestanden |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, v in res["varianten"].items():
        zf = v["zufall"]
        zeilen.append(
            f"| {name} | {v['trades']} | {_z(v['je_woche'])} | {_z(v['pf'])} | {_z(v['summe_r'], 1)} | "
            f"{_z(v['treffer'], 0)} % | {_z(v['robust_pf'])} | {_z(v['h1'][0])} ({v['h1'][1]}) | {_z(v['h2'][0])} "
            f"({v['h2'][1]}) | {_z(v['j2026'][0])} ({v['j2026'][1]}) | {_z(zf['geschlagen_pct'], 1)} % | "
            f"{'ja' if v['holm'] else 'nein'} | {'JA' if v['bestanden'] else 'nein'} |")
    zeilen += ["", "Was fehlt, je Variante:", ""]
    zeilen += [f"- {name}: {', '.join(v['fehlt']) if v['fehlt'] else 'nichts, alle Hürden geschafft'}"
               for name, v in res["varianten"].items()]
    zeilen += ["", "## Auskunft", "",
               "| Variante | Long (Trades, GF, R) | Short (Trades, GF, R) | größter Rückgang | Ausstiege | 2015 bis 2023 "
               "(Trades, GF, R) |", "|---|---|---|---|---|---|"]
    for name, v in res["varianten"].items():
        lo, sh, alt = v["long"], v["short"], v["vor_2024"]
        gr = ", ".join(f"{k} {n}" for k, n in sorted(v["gruende"].items(), key=lambda x: -x[1]))
        zeilen.append(f"| {name} | {lo['trades']}, {_z(lo['pf'])}, {_z(lo['summe_r'], 1)} | {sh['trades']}, {_z(sh['pf'])}, "
                      f"{_z(sh['summe_r'], 1)} | {_z(v['rueckgang_r'], 1)} R | {gr or '–'} | {alt['trades']}, "
                      f"{_z(alt['pf'])}, {_z(alt['summe_r'], 1)} |")
    zeilen += ["", "Bestanden heißt: mindestens 100 Trades im Hauptfenster, Gewinnfaktor ab 1,2, mit 1,5-fachen Kosten ab "
               "1,0, beide Hälften und 2026 über 1,0, mindestens 95 % der Zufallsläufe geschlagen und Holm über alle 6 "
               "Varianten. Der Zufallslauf eröffnet in dieselbe Richtung zu zufälligen Zeiten im selben Monat. Keine "
               "Nachbesserung nach dem Ergebnis.", ""]
    return "\n".join(zeilen)


def main(argv: list[str]) -> int:
    from suche.runde1 import journal_add, sha256_text
    if argv[:1] == ["--festlegen"]:
        journal_add(f"{argv[1]} VORAB_gold_zonen sha256 {sha256_text(VORAB.read_text(encoding='utf-8'))}")
        return 0
    if not vorab_ok():
        raise SystemExit("suche/VORAB_gold_zonen.yaml steht so nicht im Protokoll. Erst --festlegen \"Grund\".")
    from gold.v2 import termine as tm
    from suche.daten import read_bars
    from suche.nachpruefung_2024_26 import urteil
    cfg = regel()
    bars = read_bars(pathlib.Path(argv[0]) / "XAUUSD_5min.csv.gz")
    bars = bars[(bars.index >= cfg["daten"]["von"]) & (bars.index < pd.Timestamp(cfg["daten"]["bis"]) + pd.Timedelta(days=1))]
    m = markt(bars)
    zz = zonen(m.o4, m.h4, m.l4, m.c4, m.atr4)
    termine = np.sort(tm.load()["utc"].to_numpy().astype("datetime64[ns]"))
    sp, fak = float(cfg["kosten"]["spread_usd"]), float(cfg["kosten"]["robust_faktor"])
    geb = cfg["kosten"]["uebernacht_pct_jahr"]
    satz = {1: float(geb["long"]), -1: float(geb["short"])}
    satz_r = {k: x * fak for k, x in satz.items()}
    zf = cfg["bewertung"]["zufall"]
    res = {"vorab_sha256": sha256_text(VORAB.read_text(encoding="utf-8")), "zonen": len(zz),
           "daten": [str(bars.index[0]), str(bars.index[-1])], "varianten": {}}
    alle_trades = {}
    for v in cfg["varianten"]:
        tr = rechne(m, zz, v, termine, sp, satz)
        b = bewerte(tr, rechne(m, zz, v, termine, sp * fak, satz_r))
        b["zufall"] = zufall(m, fenster(tr, HAUPT_VON, HAUPT_BIS), sp, satz, int(zf["laeufe"]), int(zf["seed"]))
        res["varianten"][v["key"]] = b
        alle_trades[v["key"]] = tr
        print(v["key"], b["trades"], b["pf"], b["summe_r"], b["zufall"], flush=True)
    hm = holm({k: b["zufall"]["p"] for k, b in res["varianten"].items()})
    for k, b in res["varianten"].items():
        b["holm"] = hm[k]
        ok = (b["zufall"]["geschlagen_pct"] or 0) >= 95 and hm[k]
        b["bestanden"], b["fehlt"] = urteil({"trades": b["trades"], "pf": b["pf"], "robust_pf": b["robust_pf"],
                                             "h1": b["h1"], "h2": b["h2"], "j2026": b["j2026"], "zufall": ok})
    ERGEBNIS.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n",
                                             encoding="utf-8")
    ERGEBNIS.with_suffix(".md").write_text(bericht(res), encoding="utf-8")
    if len(argv) > 1:                                            # einzelne Trades für spätere Nachprüfungen
        aus = pathlib.Path(argv[1])
        aus.mkdir(parents=True, exist_ok=True)
        for k, tr in alle_trades.items():
            pd.DataFrame(tr).drop(columns=["j"], errors="ignore").to_csv(aus / f"trades_{k}.csv", index=False)
    print(bericht(res))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
