"""Scalping-Komitee, Schritt 3a: der Markt-Bot. Trend-Rücksetzer unverändert auf allen Aktien mit Capital.com-Kerzen.

Regeln: suche/VORAB_markt_bot.yaml (versiegelt im Journal, bevor gerechnet wurde). Kirons Wunsch vom 10.11.2026 10:11 UTC:
die seltenen, starken Strategien häufen und einen Markt-Bot daraus machen, der viele Märkte nach Gelegenheiten absucht.
Signal, Simulation, Stop, Kosten und Zufallsvergleich kommen unverändert aus suche/runde5.py (gleicher Code wie der
US500-Bot). Neu sind nur die Kerzen: Capital.com-Stundenkerzen der Aktien mit echtem Bid und Ask.

Aufruf: python -m suche.markt_bot [--daten ORDNER]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import zlib

import numpy as np
import pandas as pd
import yaml

from suche import runde5 as r5
from suche.runde1 import journal_lines, last_value, sha256_text

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_markt_bot.yaml"
KEY = "VORAB_markt_bot sha256 "
DATEN = pathlib.Path("/mnt/project-files/strategie-suche/aktien")
ERGEBNIS = ROOT / "suche" / "ergebnis_markt_bot"

EUR_AKTIEN = {"SAP", "SIE", "DB1", "IBE"}
ZEIT_USD, ZEIT_EUR = ("America/New_York", 15), ("Europe/London", 16)
PARAMETER = {"trend": 200, "unter": 10, "stop_atr": 3.0, "max_tage": 5}       # wie VORAB_runde5.yaml
VORLAUF_TAGE, MIN_ABDECKUNG = 400, 0.85
FEHLER_ANTEIL, FEHLER_FENSTER = 0.20, 11
FIN_LONG, FIN_SHORT = 6.5, 2.0
ROBUST = 1.5
LAEUFE, SAAT = 1000, 20261110
FENSTER = {"lernen": ("2018-06-01", "2024-12-31"), "pruefen": ("2025-01-01", "2026-10-30"),
           "jahr_2025": ("2025-01-01", "2025-12-31"), "jahr_2026": ("2026-01-01", "2026-10-30")}
PREISE = [f"{a}_{s}" for s in ("bid", "ask") for a in ("open", "high", "low", "close")]


def check_vorab() -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("VORAB_markt_bot.yaml passt nicht zur Prüfsumme im Journal. Erst versiegeln, dann rechnen.")
    return yaml.safe_load(text)["markt_bot"]


def lade(pfad: pathlib.Path) -> pd.DataFrame:
    """Stundenkerzen mit Bid und Ask; Kerzen mit einem Preis über 20 % neben dem Median der 11 Schlusskurse um sie
    herum fallen als Datenfehler weg."""
    df = pd.read_csv(pfad, parse_dates=["utc"], index_col="utc")
    df = df[~df.index.duplicated(keep="last")].sort_index().dropna(subset=PREISE)
    med = df["close_bid"].rolling(FEHLER_FENSTER, center=True, min_periods=1).median()
    schlecht = np.zeros(len(df), bool)
    for k in PREISE:
        schlecht |= ((df[k] / med - 1).abs() > FEHLER_ANTEIL).to_numpy()
    return df[~schlecht]


def baue_tage(sym: str, df: pd.DataFrame) -> r5.Tage:
    """Wie runde5.baue_tage, aber mit dem echten Spread je Stundenkerze (Ask minus Bid)."""
    zone, stunde = ZEIT_EUR if sym in EUR_AKTIEN else ZEIT_USD
    idx = df.index
    lab = r5.tageslabel(idx, zone, stunde)
    grenzen = np.flatnonzero(lab[1:] != lab[:-1]) + 1
    i0 = np.r_[0, grenzen]
    i1 = np.r_[grenzen - 1, len(lab) - 1]
    keep = (i1 - i0 + 1) >= 4
    i0, i1 = i0[keep], i1[keep]
    ho, hh, hl, hc = (df[f"{k}_bid"].to_numpy(float) for k in ("open", "high", "low", "close"))
    h_max = np.maximum.reduceat(hh, np.r_[0, grenzen])[keep]
    l_min = np.minimum.reduceat(hl, np.r_[0, grenzen])[keep]
    hsp = np.clip(df["close_ask"].to_numpy(float) - hc, 0.0, None)
    ht = idx.values
    t_ende = ht[i1] + np.timedelta64(1, "h")
    letzt = t_ende >= t_ende[-1] - np.timedelta64(365, "D")
    sp_t = float(np.median(hsp[i1][letzt]))
    return r5.Tage(sym, "aktie", lab[i0], t_ende, ho[i0], h_max, l_min, hc[i1], h_max, l_min, i0, i1, ho, hh, hl, hsp,
                   ht, sp_t, FIN_LONG / 100 / 365, FIN_SHORT / 100 / 365)


def signale(T: r5.Tage) -> dict[str, r5.Signal]:
    s = r5.sig_trend_ruecksetzer(T, PARAMETER, {})
    nur_long = r5.Signal(s.el, np.zeros_like(s.es), s.xl, s.xs, stop_atr=s.stop_atr, max_tage=s.max_tage)
    return {"markt_rs": s, "markt_rs_long": nur_long}


def aktie(sym: str, pfad: pathlib.Path) -> dict:
    T = baue_tage(sym, lade(pfad))
    start = int(np.searchsorted(T.datum, np.datetime64(T.datum[0]) + np.timedelta64(VORLAUF_TAGE, "D")))
    deckt = {f: r5.abdeckung(T, *FENSTER[f], MIN_ABDECKUNG, start) for f in ("lernen", "pruefen")}
    out = {"sym": sym, "tage": int(len(T.c)), "von": str(T.datum[0]), "bis": str(T.datum[-1]), "spread_t": T.sp,
           "kurs": float(T.c[-1]), "deckt": deckt, "varianten": {}}
    for name, s in signale(T).items():
        tr = r5.simuliere(T, s, start, mit_zwilling=(name == "markt_rs"))
        rob = r5.simuliere(T, s, start, sp_mult=ROBUST, fin_mult=ROBUST)
        zl = {}
        if name == "markt_rs_long":
            rng = np.random.default_rng(SAAT + zlib.crc32((sym + name).encode()) % 10_000)
            for f in ("lernen", "pruefen"):
                w = r5.im_fenster(tr, *FENSTER[f])
                a = int(np.searchsorted(T.datum, np.datetime64(FENSTER[f][0])))
                b = int(np.searchsorted(T.datum, np.datetime64(FENSTER[f][1]), side="right")) - 1
                zl[f] = r5.zufall_long(T, w, max(a, start), b, rng, LAEUFE)
        out["varianten"][name] = {"trades": tr, "robust": rob, "zufall_long": zl}
    return out


def wochen(f: str) -> float:
    a, b = FENSTER[f]
    return (pd.Timestamp(b) - pd.Timestamp(a)).days / 7


def bewerte(name: str, jobs: list[dict], rng: np.random.Generator) -> dict:
    def sammle(f: str, feld: str = "trades", fenster: str | None = None) -> list[dict]:
        out = []
        for j in jobs:
            if j["deckt"][f]:
                out += r5.im_fenster(j["varianten"][name][feld], *FENSTER[fenster or f])
        return out

    res: dict = {"variante": name}
    for f in ("lernen", "pruefen"):
        tr = sammle(f)
        k = r5.kennzahlen(tr)
        k["je_woche"] = round(len(tr) / wochen(f), 2)
        r = np.array([t["r"] for t in tr])
        if name == "markt_rs":
            rz = np.array([t["r_zwilling"] for t in tr])
            null = r5.null_beide(r, rz, LAEUFE, rng) if len(r) else np.zeros(1)
        else:
            mats = [j["varianten"][name]["zufall_long"][f] for j in jobs if j["deckt"][f]]
            mats = [m for m in mats if m.shape[1]]
            null = r5.pf_matrix(np.hstack(mats)) if mats else np.zeros(1)
        k["zufall_perzentil"] = round(100 * float(np.mean((k["pf"] or 0) > null)), 1) if len(r) else 0.0
        k["zufall_pf_median"] = round(float(np.median(null)), 3)
        res[f] = k
    for f in ("jahr_2025", "jahr_2026"):
        res[f] = r5.kennzahlen(sammle("pruefen", fenster=f))
    res["robust_pruefen"] = r5.kennzahlen(sammle("pruefen", "robust"))
    je = {}
    for j in jobs:
        if not j["deckt"]["pruefen"]:
            continue
        w = r5.im_fenster(j["varianten"][name]["trades"], *FENSTER["pruefen"])
        if w:
            je[j["sym"]] = {"trades": len(w), "summe_r": round(sum(t["r"] for t in w), 2), "pf": r5.pf([t["r"] for t in w])}
    res["je_aktie_pruefen"] = je
    res["aktien_im_plus_pct"] = round(100 * np.mean([v["summe_r"] > 0 for v in je.values()]), 1) if je else 0.0
    ok, fehl = bestanden(res)
    res["bestanden"], res["verfehlt"] = ok, fehl
    return res


def bestanden(v: dict) -> tuple[bool, list[str]]:
    fehl = []
    le, pr = v["lernen"], v["pruefen"]
    if le["trades"] < 150:
        fehl.append(f"Lernen nur {le['trades']} Trades")
    if (le["pf"] or 0) < 1.2:
        fehl.append(f"Lernen Gewinnfaktor {le['pf']}")
    if le["zufall_perzentil"] < 95:
        fehl.append(f"Lernen nur besser als {le['zufall_perzentil']} % Zufall")
    if pr["trades"] < 75:
        fehl.append(f"Prüfen nur {pr['trades']} Trades")
    if (pr["pf"] or 0) < 1.2:
        fehl.append(f"Prüfen Gewinnfaktor {pr['pf']}")
    for f, nm in (("jahr_2025", "2025"), ("jahr_2026", "2026")):
        if (v[f]["pf"] or 0) <= 1.0:
            fehl.append(f"{nm} Gewinnfaktor {v[f]['pf']}")
    if (v["robust_pruefen"]["pf"] or 0) < 1.1:
        fehl.append(f"Prüfen mit 1,5-fachen Kosten {v['robust_pruefen']['pf']}")
    if pr["zufall_perzentil"] < 95:
        fehl.append(f"Prüfen nur besser als {pr['zufall_perzentil']} % Zufall")
    if v["aktien_im_plus_pct"] < 50:
        fehl.append(f"nur {v['aktien_im_plus_pct']} % der Aktien im Plus")
    return not fehl, fehl


def bericht(jobs: list[dict], res: list[dict]) -> str:
    z = ["# Markt-Bot (Scalping-Komitee Schritt 3a): Ergebnis", "",
         "Regeln: suche/VORAB_markt_bot.yaml (versiegelt vor dem Rechnen). Trend-Rücksetzer wie der US500-Bot, "
         "unverändert, auf allen Aktien mit Capital.com-Stundenkerzen. Ergebnis in R (Tagesschwankung ATR 20).", "",
         "Aktien: " + ", ".join(f"{j['sym']} ({'L' if j['deckt']['lernen'] else '-'}{'P' if j['deckt']['pruefen'] else '-'})"
                                for j in jobs) + "  (L = zählt im Lernen, P = zählt im Prüfen)", "",
         "| Variante | Fenster | Trades | je Woche | PF | Summe R | Treffer | Zufall geschlagen |",
         "|---|---|---|---|---|---|---|---|"]
    for r in res:
        for f, nm in (("lernen", "Lernen 2018-2024"), ("pruefen", "Prüfen 2025-2026")):
            k = r[f]
            z.append(f"| {r['variante']} | {nm} | {k['trades']} | {k['je_woche']} | {k['pf']} | {k.get('summe_r')} | "
                     f"{k.get('treffer_pct')} % | {k['zufall_perzentil']} % (Median Zufall {k['zufall_pf_median']}) |")
        z.append(f"| {r['variante']} | 2025 / 2026 | {r['jahr_2025']['trades']} / {r['jahr_2026']['trades']} | | "
                 f"{r['jahr_2025']['pf']} / {r['jahr_2026']['pf']} | | | |")
        z.append(f"| {r['variante']} | Prüfen 1,5-fache Kosten | {r['robust_pruefen']['trades']} | | "
                 f"{r['robust_pruefen']['pf']} | {r['robust_pruefen'].get('summe_r')} | | |")
    z.append("")
    for r in res:
        z.append(f"**{r['variante']}**: " + ("bestanden." if r["bestanden"] else "durchgefallen: " + "; ".join(r["verfehlt"]) + ".")
                 + f" Aktien im Plus (Prüfen): {r['aktien_im_plus_pct']} %.")
        z.append("")
        z.append("| Aktie | Trades Prüfen | Summe R | PF |")
        z.append("|---|---|---|---|")
        for s, v in sorted(r["je_aktie_pruefen"].items(), key=lambda kv: -kv[1]["summe_r"]):
            z.append(f"| {s} | {v['trades']} | {v['summe_r']} | {v['pf']} |")
        z.append("")
    return "\n".join(z)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--daten", type=pathlib.Path, default=DATEN)
    a = ap.parse_args(argv)
    check_vorab()
    jobs = [aktie(p.name.split("_")[0], p) for p in sorted(a.daten.glob("*_HOUR.csv.gz"))]
    rng = np.random.default_rng(SAAT)
    res = [bewerte(name, jobs, rng) for name in ("markt_rs", "markt_rs_long")]
    ERGEBNIS.with_suffix(".json").write_text(json.dumps(
        {"aktien": [{k: v for k, v in j.items() if k != "varianten"} for j in jobs], "varianten": res},
        ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    md = bericht(jobs, res)
    ERGEBNIS.with_suffix(".md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
