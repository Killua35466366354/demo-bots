"""Zwilling der Runde-6-Bots: der Backtest-Motor von Runde 6 (runde4/runde4b, gleicher Code wie in der Auswertung) auf
den echten Capital.com-Kerzen eines fertigen Tages.

Nach jedem fertigen Handelstag rechnet der Lauf der Bots (suche/r6_bots.py), was der Backtest an diesem Tag mit genau
diesen Kerzen getan hätte: Richtung, Einstiegskerze, Ergebnis in Prozent vom Kurs (mit dem echten Spread). Damit sieht
man jeden Tag, ob der Bot wie der Backtest handelt, und für EUR/USD und GBP/USD (Kirons Wahl vom 04.11.2026: "plus
EUR/GBP-USD mitschreiben"), wie die Vortags-Regel dort gelaufen wäre, ohne Order.

Rein rechnend, ohne Netz. Die Bedingungen aus Runde 6 gelten wie im Bot: Vortags-Regel nur mit Einstiegskerze ab 4:30
New York (uhrzeit > 615 in der verschobenen Zeit), London und Noise nur bei Schwankung bis zur gelernten Grenze.
"""
from __future__ import annotations

import dataclasses
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from suche import r6_regeln as rg
from suche import runde4 as r4
from suche import runde4b as r4b

TYP = "CURRENCIES"
STRATEGIE = {      # Name in Runde 6 -> (Familie, Logik, Sitzung, Parameter), wie in VORAB_runde4.yaml / VORAB_runde4b.yaml
    "vortag_stop_oco": ("r4b", "vortag_stop_oco", "TAG24", {"stop_anteil": 0.1, "ziel_anteil": 0.25}),
    "london_stunde_long": ("r4b", "london_stunde", "LONDON_FRUEH",
                           {"bereich_von": 4, "bereich_bis": 8, "signal_ab": 9, "atr_n": 14, "atr_min": 1.0,
                            "atr_max": 2.5, "ziel_r": 1.5}),
    "noise_band": ("r4", "noise_band", None, {"vm": 1.0}),
}


def vortag_atr_stops(m, su: list) -> list:
    """Vortags-Regel seit 04.11.2026 (VORAB_r6_demo.yaml nachtrag_vortag_stop_2026_11_04): Stop stop_atr x ATR(14) der
    15-Minuten-Kerzen beim Legen der Stop-Orders statt 10 % der Vortagesspanne. Gelegt wird zur ersten Kerze des
    Handelstags ab 4:30 New York (630 Minuten nach 18 Uhr); es zählt die ATR der Kerze davor (letzte fertige Kerze).
    Ziel und alles andere bleiben. m: Markt aus runde4b.baue_markt (Sitzung TAG24, m.lokal = New York + 6 h)."""
    if not su:
        return su
    a = r4b.atr_rma(np.asarray(m.h, float), np.asarray(m.l, float), np.asarray(m.c, float), rg.VORTAG["atr_n"])
    lok = pd.DatetimeIndex(m.lokal)
    minute = np.asarray(lok.hour * 60 + lok.minute)
    tag = np.asarray(lok.normalize().asi8)
    ab = rg.VORTAG["uhrzeit_ueber"] + 15
    out = []
    for s in su:
        k = s.i
        if minute[k] >= ab:
            while k - 1 >= 0 and tag[k - 1] == tag[s.i] and minute[k - 1] >= ab:
                k -= 1
        else:
            while k + 1 < len(minute) and tag[k + 1] == tag[s.i] and minute[k] < ab:
                k += 1
        w = a[k - 1] if k >= 1 else np.nan
        out.append(dataclasses.replace(s, stop_abst=float(rg.VORTAG["stop_atr"] * w)) if np.isfinite(w) else s)
    return out


def als_csv(bars: pd.DataFrame, spread: pd.Series, ziel: Path) -> Path:
    """Capital.com-Kerzen (Bid) und Spread zur Eröffnung -> CSV im Format, das runde4/runde4b.baue_markt lesen."""
    sp = spread.reindex(bars.index).fillna(0.0).to_numpy()
    out = pd.DataFrame({"open_bid": bars["open"], "high_bid": bars["high"], "low_bid": bars["low"],
                        "close_bid": bars["close"], "open_ask": bars["open"] + sp, "high_ask": bars["high"] + sp,
                        "low_ask": bars["low"] + sp, "close_ask": bars["close"] + sp, "volume": 0}, index=bars.index)
    out.index.name = "utc"
    out.to_csv(ziel, compression="gzip", float_format="%.8g")
    return ziel


def bedingung(name: str, uhrzeit: int, schwankung: float | None) -> bool | None:
    """Die Bedingung aus Runde 6 für einen Einstieg. None, wenn sie sich nicht prüfen lässt (Schwankung unbekannt)."""
    if name == "vortag_stop_oco":
        return uhrzeit > rg.VORTAG["uhrzeit_ueber"]
    grenze = rg.LONDON["schwankung_max"] if name == "london_stunde_long" else rg.NOISE["schwankung_max"]
    if schwankung is None:
        return None
    return schwankung <= grenze


def zwilling_tag(name: str, epic: str, bars: pd.DataFrame, spread: pd.Series, tag: str,
                 schwankung: float | None = None) -> dict:
    """Was der Backtest am Tag `tag` (Datum der Sitzung wie im Backtest: Vortags-Regel = Handelstag 18 bis 17 Uhr New
    York, sonst London-Datum) mit diesen Kerzen getan hätte. Rückgabe: {"tag_gezaehlt": bool, "trades": [...]};
    tag_gezaehlt False heißt: Der Backtest zählt den Tag nicht (zu wenige Kerzen oder die erste fehlt)."""
    fam, logik, sitzung, p = STRATEGIE[name]
    if not len(bars):
        return {"tag_gezaehlt": False, "trades": []}
    with tempfile.TemporaryDirectory() as tmp:
        path = als_csv(bars, spread, Path(tmp) / f"{epic}.csv.gz")
        von = str(bars.index[0])
        if fam == "r4":
            m = r4.baue_markt(path, epic, TYP, von=von, sitzung=sitzung)
            su = r4.STRATEGIEN[logik](m, p)
            sim = r4.simuliere
        else:
            m = r4b.baue_markt(path, epic, TYP, sitzung, von=von)
            su = r4b.STRATEGIEN_B[logik](m, p)
            sim = r4b.simuliere
            if name == "vortag_stop_oco":
                su = vortag_atr_stops(m, su)
    gezaehlt = any(t.datum == tag for t in m.tage)
    out = []
    for s in su:
        if s.datum != tag:
            continue
        lok = m.lokal[s.i]
        uhr = int(lok.hour * 60 + lok.minute)
        ok = bedingung(name, uhr, schwankung)
        res = sim(m, s)
        ein = s.ref + (m.sp[s.i] if s.d > 0 else 0.0)
        k_aus = s.i + res["kerzen"] - 1
        out.append({"einstieg_kerze": str(pd.Timestamp(m.t[s.i])), "side": "long" if s.d > 0 else "short",
                    "einstieg": round(float(ein), 6), "pct": round(float(res["r"]), 4), "grund": res["grund"],
                    "ausstieg_kerze": str(pd.Timestamp(m.t[k_aus])), "uhrzeit": uhr,
                    "bedingung": ok, "zaehlt": bool(ok),
                    "stop_abst": round(float(s.stop_abst), 6) if np.isfinite(getattr(s, "stop_abst", np.nan)) else None})
    return {"tag_gezaehlt": gezaehlt, "trades": out}


def vergleiche(zwilling: list[dict], bot: list[dict]) -> dict:
    """Bot-Trades eines Tages gegen die Zwilling-Trades (nur die mit erfüllter Bedingung): gleich, wenn Richtung und
    Einstiegskerze übereinstimmen."""
    z = {(t["einstieg_kerze"], t["side"]) for t in zwilling if t.get("zaehlt")}
    b = {(str(t.get("einstieg_kerze")), t.get("side")) for t in bot}
    return {"gleich": z == b, "nur_zwilling": sorted(map(list, z - b)), "nur_bot": sorted(map(list, b - z)),
            "zwilling_pct": round(float(np.sum([t["pct"] for t in zwilling if t.get("zaehlt")])), 4),
            "bot_pct": round(float(np.sum([t.get("pct") or 0.0 for t in bot])), 4)}
