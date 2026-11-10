"""Scalping mit den Open-Filtern aus Kirons Video: Top 3 nach Gewinnfaktor für den Demo-Vorwärtstest.

Regeln: suche/VORAB_scalping_opens.yaml (versiegelt im Journal, bevor gerechnet wurde), Kirons Wort vom 10.11.2026
12:16 UTC. Kombinationen und Regeln aus suche/scalping2.py (Runde 2b, 5 und 15 Min.), Filter aus suche/opens.py (Video
TikTok montyfinance: Jahres-, Quartals-, Monats- und Wochen-Open).

Aufruf: python -m suche.scalping_opens [--daten ORDNER] [--nur EURUSD,...]
"""
from __future__ import annotations

import argparse
import functools
import json
import pathlib

import numpy as np
import pandas as pd
import yaml

from suche import opens as op
from suche import scalping as sc
from suche import scalping2 as s2
from suche.runde1 import journal_lines, last_value, sha256_text

ROOT = s2.ROOT
VORAB = ROOT / "suche" / "VORAB_scalping_opens.yaml"
KEY = "VORAB_scalping_opens sha256 "
ERGEBNIS = ROOT / "suche" / "ergebnis_scalping_opens"
FILTER = ("jahr", "quartal", "monat", "woche", "alle")
MIN_TRADES = 100
TOP = 3


def check_vorab() -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("suche/VORAB_scalping_opens.yaml passt nicht zur Prüfsumme im Journal, erst festlegen.")
    return yaml.safe_load(text)["scalping_opens"]


def mit_opens(p: pd.DataFrame, trades: list[dict]) -> dict[str, np.ndarray]:
    """Je Filter eine Maske über `trades`: Richtung des Trades gleich der Seite des Kurses zum Open. Kurs = Schluss der
    letzten fertigen 5-Min.-Kerze (Beginn höchstens Einstieg minus 5 Min.), Opens dieser Kerze (VORAB_opens teil_a)."""
    if not trades:
        return {f: np.zeros(0, bool) for f in FILTER}
    t = pd.DatetimeIndex([x["t"] for x in trades])
    pos = p.index.searchsorted(t - pd.Timedelta(minutes=5), side="right") - 1
    ok = pos >= 0
    pos = np.where(ok, pos, 0)
    ref = p.iloc[pos]
    kurs = ref["close"].to_numpy(float)
    seite = np.array([x["d"] for x in trades], float)
    m = {f: ok & (seite * (kurs - ref[c].to_numpy(float)) > 0) for f, c in op.FILTER.items()}
    m["alle"] = m["jahr"] & m["quartal"] & m["monat"] & m["woche"]
    return m


def gefiltert(p: pd.DataFrame, trades: list[dict]) -> dict[str, list[dict]]:
    m = mit_opens(p, trades)
    return {f: [x for x, k in zip(trades, m[f]) if k] for f in FILTER}


def vergleich(z: list[dict], rng: np.random.Generator) -> dict:
    """Wie Runde 2b: 200 Läufe mit zufälliger Richtung zu denselben Zeiten (gleiche Abstände)."""
    if not z:
        return {"geschlagen_pct": 0.0, "zufall_pf_median": None}
    eigen = np.array([t["r"] for t in z])
    gegen = np.array([t["r_gegen"] for t in z])
    pfk = sc.pf_von(eigen)
    pfs = np.array([sc.pf_von(np.where(rng.random(len(z)) < 0.5, gegen, eigen)) for _ in range(s2.ZUFALL_LAEUFE)])
    return {"geschlagen_pct": round(100 * float((pfk > pfs).mean()), 1),
            "zufall_pf_median": round(float(np.median(pfs)), 2)}


def kombinationen(m: sc.Markt, sym: str, tf: int, ereignisse, ter) -> list[tuple]:
    """(familie, variante, termin, rechne, kontrolle) wie scalping2.rechne_alles, nur 5 und 15 Min."""
    out = []
    for v in ("folgen_10r", "folgen_2r", "gegen_2r"):
        out.append(("eroeffnung", v, False, functools.partial(s2.eroeffnung, m, sym, v), s2.KONTROLLE))
    for v in ("news_gegen", "news_folgen"):
        out.append(("news", v, True, functools.partial(s2.news, m, v, ereignisse), s2.KONTROLLE_TERMINE))
    if tf == 5:
        for v in ("folgen", "gegen"):
            out.append(("halbe_stunde", v, False, functools.partial(s2.halbe_stunde, m, sym, v), s2.KONTROLLE))
        if sym in s2.INDIZES:
            out.append(("vor_der_zahl", "vor_der_zahl", True, functools.partial(s2.vor_der_zahl, m, ter),
                        s2.KONTROLLE_TERMINE))
    return out


def rechne_alles(daten: pathlib.Path = s2.DATEN, nur: set | None = None) -> tuple[list[dict], list[dict]]:
    """Alle Varianten (Kombination x Filter), echt und als Zufallszwilling (derselbe Filter auf den gedrehten Trades)."""
    rng = np.random.default_rng(s2.SAAT)
    sp = s2.spreads()
    ter = sc.termine()
    ereignisse = sorted(ter["nfp"] + ter["cpi"] + ter["fomc"])
    echt, zwill = [], []
    for sym in s2.ALLE:
        if nur and sym not in nur:
            continue
        p = op.perioden(op.lade(daten, sym))
        for tf in (5, 15):
            m = s2.lade_markt(sym, tf, daten, s2.M1, sp)
            if m is None:
                continue
            for fam, var, termin, rechne, kon in kombinationen(m, sym, tf, ereignisse, ter):
                tr, rob, ko = rechne(1.0, *s2.ZEITRAUM), rechne(s2.ROBUST, *s2.ZEITRAUM), rechne(1.0, *kon)
                # vor_der_zahl rechnet die Gegenrichtung in Runde 2b nicht mit (dort Placebo-Tage), hier für Zwilling
                # und Zufallsvergleich nötig: derselbe Trade umgedreht, gleiche Zeiten
                tr = [t if "r_gegen" in t else s2.mit_gegen(m, t, m.spread) for t in tr]
                f_tr, f_rob, f_ko = gefiltert(p, tr), gefiltert(p, rob), gefiltert(p, ko)
                zw = s2.zwilling(tr, rng)
                f_zw = gefiltert(p, zw)
                for f in FILTER:
                    v = s2.kennzahlen_satz(f_tr[f], f_rob[f], f_ko[f], kon)
                    kopf = {"familie": fam, "variante": var, "markt": sym, "kerzen": tf, "termin": termin, "filter": f}
                    echt.append({**kopf, **v, "_trades": f_tr[f]})
                    zwill.append({**kopf, "zeitraum": sc.kennzahlen(f_zw[f], *s2.ZEITRAUM)})
            print(f"{sym} {tf} Min.: {len(echt)} Varianten", flush=True)
            del m
    return echt, zwill


def waehle(res: list[dict], top: int = TOP) -> list[dict]:
    """Mindestens 100 Trades im Zeitraum, Rang nach Gewinnfaktor (bei Gleichstand mehr Trades), 3 verschiedene Märkte."""
    kand = [r for r in res if r["zeitraum"]["trades"] >= MIN_TRADES]
    kand.sort(key=lambda r: (-r["zeitraum"]["pf"], -r["zeitraum"]["trades"]))
    out, maerkte = [], set()
    for r in kand:
        if r["markt"] in maerkte:
            continue
        out.append(r)
        maerkte.add(r["markt"])
        if len(out) == top:
            break
    return out


def name(r: dict) -> str:
    return f"{r['familie']} {r['variante']} {r['markt']} {r['kerzen']} Min. Filter {r['filter']}"


def zeile(r: dict) -> str:
    z = r["zeitraum"]
    vg = r.get("vergleich") or {}
    return (f"| {r['familie']} | {r['variante']} | {r['markt']} | {r['kerzen']} | {r['filter']} | {z['trades']} | "
            f"{z['je_woche']} | {z['pf']} | {z['summe']} | {z['max_rueckgang']} | {r['robust']['pf']} | "
            f"{r['haelfte_1']['pf']} | {r['haelfte_2']['pf']} | {r['jahr_2026']['pf']} | {r['kontrolle']['pf']} | "
            f"{vg.get('geschlagen_pct', '')} |")


def bericht(res: list[dict], gewaehlt: list[dict], zw_top: list[dict]) -> str:
    kopf = ["| Familie | Variante | Markt | Min. | Filter | Trades | je Woche | PF | Summe | Rückgang | 1,5x Spread | "
            "H1 | H2 | 2026 | Kontrolle 22-24 | schlägt Zufall % |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    genug = [r for r in res if r["zeitraum"]["trades"] >= MIN_TRADES]
    z = ["# Scalping mit den Open-Filtern aus Kirons Video: die 3 mit dem höchsten Gewinnfaktor", "",
         "Regeln: suche/VORAB_scalping_opens.yaml (versiegelt vor dem Rechnen). Runde-2b-Kombinationen auf 5 und 15 Min. "
         "mal 5 Open-Filter (Jahr, Quartal, Monat, Woche, alle), Zeitraum 01.11.2024 bis 30.10.2026, mindestens 100 Trades, "
         "Rang nach Gewinnfaktor, 3 verschiedene Märkte. Mit Stop in R, ohne Stop in Prozent. Live gehen die 3 auf "
         "Kirons Wunsch auf jeden Fall (Account 1, Demo).", "",
         f"**Varianten: {len(res)}, davon mit mindestens 100 Trades: {len(genug)}.**", "",
         "## Die 3 gewählten", ""] + kopf + [zeile(r) for r in gewaehlt] + [""]
    if gewaehlt and zw_top:
        echt3 = gewaehlt[-1]["zeitraum"]["pf"]
        zw3 = zw_top[-1]["zeitraum"]["pf"]
        z += ["## Zufallsgegenprobe", "",
              f"Dieselbe Auswahl auf den Zufallszwillingen (Richtung je Trade per Zufall, dann derselbe Filter): Platz 3 "
              f"hat dort Gewinnfaktor {zw3}, bei den echten {echt3}. "
              + ("Die echten liegen nicht höher: der Vorsprung ist vermutlich Glück."
                 if echt3 <= zw3 else "Die echten liegen höher, aber bei so vielen Varianten bleibt Glück möglich."), "",
              "| Platz | Zwilling | Trades | PF |", "|---|---|---|---|"]
        z += [f"| {i + 1} | {name(r)} | {r['zeitraum']['trades']} | {r['zeitraum']['pf']} |" for i, r in enumerate(zw_top)]
        z += [""]
    beste = sorted(genug, key=lambda r: (-r["zeitraum"]["pf"], -r["zeitraum"]["trades"]))[:15]
    z += ["## Die 15 besten Varianten (mindestens 100 Trades, auch gleicher Markt)", ""] + kopf + [zeile(r) for r in beste]
    fil = {}
    for r in genug:
        fil.setdefault(r["filter"], []).append(r["zeitraum"]["pf"])
    z += ["", "## Je Filter", "", "| Filter | Varianten mit 100 Trades | PF Median | PF über 1,2 |", "|---|---|---|---|"]
    for f in FILTER:
        v = fil.get(f, [])
        z.append(f"| {f} | {len(v)} | {round(float(np.median(v)), 2) if v else ''} | {sum(x >= 1.2 for x in v)} |")
    return "\n".join(z) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--daten", type=pathlib.Path, default=s2.DATEN)
    ap.add_argument("--nur", default="")
    a = ap.parse_args(argv)
    check_vorab()
    s2.check_vorab()
    op.check_vorab()
    res, zw = rechne_alles(a.daten, set(a.nur.split(",")) if a.nur else None)
    gewaehlt = waehle(res)
    rng = np.random.default_rng(s2.SAAT)
    for r in gewaehlt:
        r["vergleich"] = vergleich(r["_trades"], rng)
    zw_top = waehle(zw)
    md = bericht(res, gewaehlt, zw_top)
    if a.nur:
        print(md)
        return
    aus = [{k: v for k, v in r.items() if k != "_trades"} for r in res]
    erg = {"vorab_sha256": sha256_text(VORAB.read_text(encoding="utf-8")),
           "gewaehlt": [{k: v for k, v in r.items() if k != "_trades"} for r in gewaehlt],
           "zwilling_top": zw_top, "varianten": aus}
    ERGEBNIS.with_suffix(".json").write_text(json.dumps(erg, ensure_ascii=False, indent=0, default=str) + "\n",
                                             encoding="utf-8")
    ERGEBNIS.with_suffix(".md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
