"""Strategie-Suche Runde 5c: Gegenprobe des Trend-Rücksetzers auf Capital.com-Tageskerzen 2005-2010 (VORAB_runde5c.yaml).

Gleiche Regel, Parameter, Kosten und Zufallsvergleiche wie Runde 5/5b (suche/runde5.py). Anders sind nur die Kerzen:
Capital.com-Tageskerzen statt HistData-Stunden, deshalb Notstop auf Tageshoch/-tief.

    python -m suche.runde5c --festlegen "Grund"
    python -m suche.runde5c <capital_tag_ordner> <out_dir>
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd
import yaml

from suche import runde5 as r5
from suche.runde1 import journal_add, journal_lines, last_value

VORAB = r5.HERE / "VORAB_runde5c.yaml"
KEY = "VORAB_runde5c sha256 "


def check_vorab() -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if last_value(journal_lines(), KEY) != r5.sha256_text(text):
        raise SystemExit("VORAB_runde5c.yaml stimmt nicht mit der Prüfsumme im Journal überein. Erst festlegen.")
    return yaml.safe_load(text)["runde_5c"]


def tage_aus_tageskerzen(epic: str, df: pd.DataFrame, kosten: dict) -> r5.Tage:
    """Capital.com-Tageskerzen -> Tage. Sonntag zählt zum Montag; eine 'Stunde' je Tag (Stop auf Tageshoch/-tief)."""
    d = df.index.values.astype("datetime64[D]")
    wd = (d.astype(np.int64) + 3) % 7
    d = d + np.where(wd == 6, 1, np.where(wd == 5, 2, 0)).astype("timedelta64[D]")
    g = pd.DataFrame({"o": df["open_bid"].to_numpy(float), "h": df["high_bid"].to_numpy(float),
                      "l": df["low_bid"].to_numpy(float), "c": df["close_bid"].to_numpy(float)}, index=d)
    g = g.groupby(level=0).agg({"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()
    datum = g.index.values.astype("datetime64[D]")
    n = len(g)
    sp_alle = (df["close_ask"] - df["close_bid"])[df.index >= "2019-01-01"]
    sp = float(sp_alle[sp_alle > 0].median())
    fin = kosten["uebernacht"]["index"]
    t = datum.astype("datetime64[ns]") + np.timedelta64(22, "h")
    i = np.arange(n)
    o, h, l, c = (g[k].to_numpy(float) for k in "ohlc")
    return r5.Tage(epic, "index_us", datum, t, o, h, l, c, h, l, i, i, o, h, l, np.full(n, sp),
                   datum.astype("datetime64[ns]"), sp, fin["long"] / 100 / 365, fin["short"] / 100 / 365)


def markt(epic: str, ordner: pathlib.Path, cfg5: dict, st: dict, cfg: dict) -> dict:
    df = pd.read_csv(ordner / f"{epic}_DAY.csv.gz", index_col=0, parse_dates=True).sort_index()
    T = tage_aus_tageskerzen(epic, df, cfg5["kosten"])
    start = int(np.searchsorted(T.datum, T.datum[0] + np.timedelta64(cfg["vorlauf_tage"], "D")))
    s = r5.SIGNALE[st["logik"]](T, st["parameter"], {})
    tr = r5.simuliere(T, s, start, mit_zwilling=True)
    rob = r5.simuliere(T, s, start, sp_mult=cfg5["kosten"]["robust_faktor"], fin_mult=cfg5["kosten"]["robust_faktor"])
    return {"epic": epic, "spread": T.sp, "von": str(T.datum[0]), "bis": str(T.datum[-1]), "tage": len(T.c),
            "trades": tr, "robust": rob}


def kennz(tr: list[dict], rob: list[dict], rng: np.random.Generator, laeufe: int) -> dict:
    k = r5.kennzahlen(tr)
    if tr:
        null = r5.null_beide(np.array([t["r"] for t in tr]), np.array([t["r_zwilling"] for t in tr]), laeufe, rng)
        k["zufall_perzentil"] = round(float((null < (k["pf"] or 0)).mean() * 100), 1)
    else:
        k["zufall_perzentil"] = 0.0
    k["pf_robust"] = r5.pf([t["r"] for t in rob])
    k["je_jahr"] = r5.je_jahr(tr)
    return k


def run(ordner: pathlib.Path, out: pathlib.Path) -> dict:
    cfg = check_vorab()
    cfg5 = r5.check_vorab()
    st = cfg5["strategien"]["trend_ruecksetzer"]
    h = cfg["huerden"]
    jobs = {e: markt(e, ordner, cfg5, st, cfg) for e in cfg["test_maerkte"] + cfg["info_maerkte"]}
    rng = np.random.default_rng(h["zufall_seed"])
    von, bis = cfg["fenster"]
    res: dict = {"maerkte": {e: {k: j[k] for k in ("spread", "von", "bis", "tage")} for e, j in jobs.items()}}

    def sammle(maerkte, a, b):
        tr = [t for e in maerkte for t in r5.im_fenster(jobs[e]["trades"], a, b)]
        rob = [t for e in maerkte for t in r5.im_fenster(jobs[e]["robust"], a, b)]
        return tr, rob

    k = kennz(*sammle(cfg["test_maerkte"], von, bis), rng, h["zufall_laeufe"])
    k["je_markt"] = {e: r5.kennzahlen(r5.im_fenster(jobs[e]["trades"], von, bis)) for e in cfg["test_maerkte"]}
    jahre_gut = sum(1 for v in k["je_jahr"].values() if (v["pf"] or 0) > 1)
    tests = {"trades": k["trades"] >= h["min_trades"], "pf": (k["pf"] or 0) >= h["min_pf"],
             "zufall": k["zufall_perzentil"] >= h["min_zufall_perzentil"],
             "robust": (k["pf_robust"] or 0) >= h["min_pf_robust"], "jahre": jahre_gut >= h["min_jahre_pf_ueber_1"]}
    res["test"] = {**k, "jahre_pf_ueber_1": jahre_gut, "tests": tests, "bestanden": all(tests.values())}
    res["info"] = {}
    for name, (a, b) in cfg["info_fenster"].items():
        res["info"][name] = {"test_maerkte": kennz(*sammle(cfg["test_maerkte"], a, b), rng, h["zufall_laeufe"])}
    for e in cfg["info_maerkte"]:
        res["info"][e] = {f: r5.kennzahlen(r5.im_fenster(jobs[e]["trades"], *w))
                          for f, w in {"test": cfg["fenster"], **cfg["info_fenster"]}.items()}
    out.mkdir(parents=True, exist_ok=True)
    (out / "runde5c.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    t = res["test"]
    journal_add("Runde 5c gerechnet (Capital.com-Tageskerzen 2005-2010, US500+US100): " + json.dumps(
        {"trades": t["trades"], "pf": t["pf"], "zufall": t["zufall_perzentil"], "robust": t["pf_robust"],
         "jahre": t["jahre_pf_ueber_1"], "bestanden": t["bestanden"]}, ensure_ascii=False))
    return res


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--festlegen":
        text = VORAB.read_text(encoding="utf-8")
        journal_add(f"Runde 5c festgelegt, Grund: {' '.join(argv[1:])}. VORAB_runde5c sha256 {r5.sha256_text(text)}")
        return 0
    res = run(pathlib.Path(argv[0]), pathlib.Path(argv[1]))
    print(json.dumps({"test": {k: res["test"][k] for k in ("trades", "pf", "zufall_perzentil", "pf_robust",
                                                            "jahre_pf_ueber_1", "tests", "bestanden")}},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
