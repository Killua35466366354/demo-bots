"""Strategie-Suche, Runde 1: Kirons Pine-Strategien C und B auf 19 Märkten, 5/15/60 Minuten (suche/VORAB.yaml).

Usage (from the repo root):
    python -m suche.runde1 --festlegen "Grund"            # VORAB-Prüfsumme ins Journal, BEVOR gerechnet wird
    python -m suche.runde1 --pruefsummen <daten>           # Prüfsummen der Kerzen im versiegelten Fenster ins Journal
    python -m suche.runde1 <daten> <out_dir>               # Auswahl 2015-2020 und Prüfung 2021-2023
    python -m suche.runde1 --siegel-oeffnen <daten> <out_dir>   # genau einmal: Finalisten im versiegelten Fenster

<daten> ist der Ordner mit <SYMBOL>_5min.csv.gz aus suche/daten.py. Auswahl und Prüfung sehen keine Kerze ab dem
versiegelten Fenster: Die Daten werden vor jeder Rechnung davor abgeschnitten.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yaml

from gold.backtest.pine_port import htf_ema, signals_b_short, signals_c_long
from gold.backtest.runde2 import pf, r_with_swap
from gold.backtest.sizing import atr_rma
from gold.v2.fuehrung import Fuehrung, Markt, run_v2, twin_r
from suche.daten import read_bars, to_bars

HERE = pathlib.Path(__file__).resolve().parent
VORAB = HERE / "VORAB.yaml"
JOURNAL = HERE.parent / "journal" / "strategie-suche-protokoll.md"
SIDES = {"C+B": (True, True), "nur C": (True, False), "nur B": (False, True)}


# ---------- Journal ----------

def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def journal_lines() -> list[str]:
    return JOURNAL.read_text(encoding="utf-8").splitlines() if JOURNAL.exists() else []


def journal_add(text: str) -> None:
    lines = journal_lines() or ["# Strategie-Suche: Protokoll", "",
                                "Jede Zeile wird nur angehängt. Prüfsummen stehen hier, bevor gerechnet wird.", ""]
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    JOURNAL.write_text("\n".join(lines + [f"- {stamp}: {text}"]) + "\n", encoding="utf-8")


def last_value(lines: list[str], key: str) -> str | None:
    for line in reversed(lines):
        if key in line:
            return line.split(key, 1)[1].split()[0].rstrip(".,;")
    return None


def bars_hash(bars: pd.DataFrame) -> str:
    return sha256_text(bars[["open", "high", "low", "close"]].round(6).to_csv())


def check_vorab() -> tuple[str, dict]:
    text = VORAB.read_text(encoding="utf-8")
    if last_value(journal_lines(), "VORAB sha256 ") != sha256_text(text):
        raise SystemExit("suche/VORAB.yaml steht so nicht im Journal. Erst --festlegen \"Grund\" und committen.")
    return text, yaml.safe_load(text)


# ---------- Rechnen ----------

def fuehrung(spec: dict) -> Fuehrung:
    return Fuehrung(stop_atr=spec["stop_atr"], tp_atr=spec.get("ziel_atr"), max_bars=spec.get("max_kerzen"),
                    exit_signal=spec["ausstieg_signal"])


def in_hours(index: pd.DatetimeIndex, step: pd.Timedelta, hours) -> np.ndarray:
    """Füllzeit (Eröffnung der nächsten Kerze) liegt in [von, bis) Uhr UTC."""
    fill = index + step
    h = fill.hour + fill.minute / 60
    return np.asarray((h >= hours[0]) & (h < hours[1]))


@dataclasses.dataclass
class Prepared:
    m: Markt
    entries: dict
    pools: tuple
    index: pd.DatetimeIndex


def prepare(bars5: pd.DataFrame, tf: str, spec: dict) -> Prepared:
    bars = bars5 if tf == "5min" else to_bars(bars5, tf)
    sc, sb = signals_c_long(bars, useTrend=True), signals_b_short(bars, useTrend=True)
    atr = atr_rma(bars)
    ema = htf_ema(bars).to_numpy(float)
    ok = in_hours(bars.index, pd.Timedelta(tf), spec["stunden"])
    m = Markt.build(bars, float(spec["spread"]), atr, sc, sb, None, ema, None)
    c = bars["close"].to_numpy(float)
    entries = {"long": sc["entry"].to_numpy(bool) & ok, "short": sb["entry"].to_numpy(bool) & ok}
    pools = ((c > ema) & ok, (c < ema) & ok)
    return Prepared(m, entries, pools, bars.index)


def span(index: pd.DatetimeIndex, window) -> slice:
    a, b = window
    return slice(int(index.searchsorted(pd.Timestamp(a))), int(index.searchsorted(pd.Timestamp(b), side="right")))


def run_r(P: Prepared, window, side: str, f: Fuehrung, swap: float, spread_factor: float = 1.0):
    s = span(P.index, window)
    m = P.m.slice(s.start, s.stop)
    if spread_factor != 1.0:
        m = dataclasses.replace(m, sp=m.sp * spread_factor)
    use_l, use_s = SIDES[side]
    el = P.entries["long"][s] & use_l
    es = P.entries["short"][s] & use_s
    tr = run_v2(m, el, es, f, start_eur=1e12, eurusd=1.0, margin_rate=0.0, size_oz=1.0, swap_pct_year=0.0)[0]
    return tr, (r_with_swap(tr, swap) if len(tr) else np.array([])), m, s


def measure(tr: pd.DataFrame, r: np.ndarray) -> dict:
    if not len(r):
        return {"trades": 0, "win_pct": None, "pf_r": None, "sum_r": 0.0, "max_dd_r": 0.0, "jahre": {}}
    cum = np.cumsum(r)
    years = pd.to_datetime(tr["entry_time"]).dt.year.to_numpy()
    jahre = {str(int(y)): round(float(r[years == y].sum()), 1) for y in sorted(set(years.tolist()))}
    return {"trades": int(len(r)), "win_pct": round(100 * float((r > 0).mean()), 1), "pf_r": pf(r),
            "sum_r": round(float(r.sum()), 1), "mean_r": round(float(r.mean()), 3),
            "max_dd_r": round(float((np.maximum.accumulate(np.r_[0.0, cum]) - np.r_[0.0, cum]).max()), 1),
            "avg_kerzen": round(float(tr["bars"].mean()), 1),
            "long_r": round(float(r[(tr["side"] == "long").to_numpy()].sum()), 1),
            "short_r": round(float(r[(tr["side"] == "short").to_numpy()].sum()), 1), "jahre": jahre}


def twins(P: Prepared, tr: pd.DataFrame, m: Markt, s: slice, f: Fuehrung, swap: float, real_sum: float, z: dict) -> dict:
    rng = np.random.default_rng(z["seed"])
    sums = np.array([twin_r(m, tr, P.pools[0][s], P.pools[1][s], f, rng, swap).sum() for _ in range(z["laeufe"])])
    return {"median_sum_r": round(float(np.median(sums)), 1), "as_good_pct": round(100 * float((sums >= real_sum).mean()), 1)}


def selection_misses(res: dict, th: dict) -> list[str]:
    miss = []
    if res["trades"] < th["min_trades"]:
        miss.append(f"nur {res['trades']} Trades")
    if (res["pf_r"] or 0) < th["min_gewinnfaktor_r"]:
        miss.append(f"Gewinnfaktor {res['pf_r']}")
    if (res["robust_pf_r"] or 0) < th["min_gewinnfaktor_r_robust"]:
        miss.append(f"mit 1,5-fachem Spread Gewinnfaktor {res['robust_pf_r']}")
    plus = sum(1 for v in res["jahre"].values() if v > 0)
    if plus < th["min_jahre_im_plus"]:
        miss.append(f"nur {plus} Jahre im Plus")
    if "zwillinge" in res and res["zwillinge"]["as_good_pct"] > th["max_zufall_gleich_gut_pct"]:
        miss.append(f"{res['zwillinge']['as_good_pct']} % der Zufalls-Zwillinge so gut")
    return miss


def check_window(res: dict, th: dict) -> list[str]:
    miss = []
    if "min_trades" in th and res["trades"] < th["min_trades"]:
        miss.append(f"nur {res['trades']} Trades")
    if (res["pf_r"] or 0) < th["min_gewinnfaktor_r"]:
        miss.append(f"Gewinnfaktor {res['pf_r']}")
    if res["sum_r"] <= th["summe_r_ueber"]:
        miss.append(f"Summe {res['sum_r']} R")
    if "min_gewinnfaktor_r_robust" in th and (res["robust_pf_r"] or 0) < th["min_gewinnfaktor_r_robust"]:
        miss.append(f"mit 1,5-fachem Spread Gewinnfaktor {res['robust_pf_r']}")
    if "summe_r_robust_ueber" in th and res["robust_sum_r"] <= th["summe_r_robust_ueber"]:
        miss.append(f"mit 1,5-fachem Spread Summe {res['robust_sum_r']} R")
    return miss


def evaluate(P: Prepared, window, side: str, f: Fuehrung, r1: dict) -> dict:
    swap = r1["swap_pct_jahr"]
    tr, r, m, s = run_r(P, window, side, f, swap)
    res = measure(tr, r)
    tr2, r2, *_ = run_r(P, window, side, f, swap, r1["spread_faktor_robust"])
    res["robust_pf_r"], res["robust_sum_r"] = pf(r2), round(float(r2.sum()), 1) if len(r2) else 0.0
    res["_ctx"] = (tr, m, s)
    return res


def selection_market(args) -> dict:
    """Alle 18 Kombinationen eines Marktes in der Auswahl, dann die beste bestandene in der Prüfung."""
    path, spec, r1 = args
    bars5 = read_bars(path).loc[:r1["fenster"]["pruefung"][1]]          # nichts aus dem versiegelten Fenster
    out = {"symbol": spec["symbol"], "name": spec["name"], "art": spec["art"], "kerzen_5min": int(len(bars5)),
           "von": str(bars5.index[0]), "bis": str(bars5.index[-1]), "kombis": []}
    best = None
    for tf in r1["zeitrahmen"]:
        P = prepare(bars5, tf, spec)
        for fname, fspec in r1["fuehrungen"].items():
            f = fuehrung(fspec)
            for side in r1["seiten"]:
                res = evaluate(P, r1["fenster"]["auswahl"], side, f, r1)
                tr, m, s = res.pop("_ctx")
                res.update({"zeitrahmen": tf, "fuehrung": fname, "seiten": side})
                if not selection_misses(res, r1["auswahl_schwellen"]):
                    res["zwillinge"] = twins(P, tr, m, s, f, r1["swap_pct_jahr"], res["sum_r"], r1["zufall"])
                res["verfehlt"] = selection_misses(res, r1["auswahl_schwellen"])
                out["kombis"].append(res)
                if not res["verfehlt"] and (best is None or (res["pf_r"], res["trades"]) > (best["pf_r"], best["trades"])):
                    best = res
                print(spec["symbol"], tf, fname, side, res["trades"], res["pf_r"], res["sum_r"], res["verfehlt"], flush=True)
    if best is not None:
        P = prepare(bars5, best["zeitrahmen"], spec)
        pr = evaluate(P, r1["fenster"]["pruefung"], best["seiten"], fuehrung(r1["fuehrungen"][best["fuehrung"]]), r1)
        pr.pop("_ctx")
        pr["verfehlt"] = check_window(pr, r1["pruef_schwellen"])
        out["gewaehlt"] = {k: best[k] for k in ("zeitrahmen", "fuehrung", "seiten")}
        out["pruefung"] = pr
    return out


def chance_expectation(n: int, p: float = 0.05) -> float:
    return round(n * p, 1)


def main(argv: list[str]) -> int:
    if argv[:1] == ["--festlegen"]:
        text = VORAB.read_text(encoding="utf-8")
        journal_add(f"VORAB festgelegt, Grund: {argv[1]}. VORAB sha256 {sha256_text(text)}")
        print("Im Journal:", sha256_text(text))
        return 0
    text, cfg = check_vorab()
    r1 = cfg["runde_1"]
    specs = {m["symbol"]: m for m in r1["maerkte"]}
    if argv[:1] == ["--pruefsummen"]:
        data = pathlib.Path(argv[1])
        a, b = r1["fenster"]["versiegelt"]
        for sym in specs:
            sealed = read_bars(data / f"{sym}_5min.csv.gz").loc[a:b]
            journal_add(f"Siegel {sym} {len(sealed)} Kerzen bis {sealed.index[-1]} sha256 {bars_hash(sealed)}")
        print("\n".join(journal_lines()[-len(specs):]))
        return 0
    if argv[:1] == ["--siegel-oeffnen"]:
        return open_seal(pathlib.Path(argv[1]), pathlib.Path(argv[2]), r1, specs, text)
    data, out = pathlib.Path(argv[0]), pathlib.Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(data / f"{sym}_5min.csv.gz", spec, r1) for sym, spec in specs.items()]
    with ProcessPoolExecutor(max_workers=4) as ex:
        markets = list(ex.map(selection_market, jobs))
    cands = [mk for mk in markets if "pruefung" in mk and not mk["pruefung"]["verfehlt"]
             and not specs[mk["symbol"]].get("nur_vergleich")]
    cands.sort(key=lambda mk: mk["pruefung"]["sum_r"], reverse=True)
    finals = [mk["symbol"] for mk in cands[:r1["finalisten_max"]]]
    n_combo = sum(len(mk["kombis"]) for mk in markets)
    n_pass = sum(1 for mk in markets for k in mk["kombis"] if not k["verfehlt"])
    n_val = sum(1 for mk in markets if "pruefung" in mk)
    payload = {"made": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "vorab_sha256": sha256_text(text),
               "markets": markets, "finalisten": finals,
               "zufall_erwartet": {"kombis": n_combo, "bestanden_auswahl": n_pass,
                                   "erwartet_durch_zufall_auswahl": chance_expectation(n_combo),
                                   "in_pruefung": n_val, "bestanden_pruefung": len(cands),
                                   "erwartet_durch_zufall_pruefung": chance_expectation(n_val)}}
    (out / "runde1.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    journal_add(f"Runde 1 gerechnet (Auswahl und Prüfung): Finalisten {', '.join(finals) if finals else 'keine'}")
    print(json.dumps(payload["zufall_erwartet"], ensure_ascii=False), "Finalisten:", finals)
    return 0


def open_seal(data: pathlib.Path, out: pathlib.Path, r1: dict, specs: dict, text: str) -> int:
    lines = journal_lines()
    if any("Siegel geöffnet" in line for line in lines):
        raise SystemExit("Das versiegelte Fenster wurde schon geöffnet. Ein zweites Mal gibt es nicht.")
    prev = json.loads((out / "runde1.json").read_text(encoding="utf-8"))
    if prev["vorab_sha256"] != sha256_text(text):
        raise SystemExit("runde1.json passt nicht zur VORAB.yaml.")
    if not prev["finalisten"]:
        raise SystemExit("Keine Finalisten: Das Siegel bleibt zu und steht für eine spätere Runde bereit.")
    a, b = r1["fenster"]["versiegelt"]
    results = []
    for sym in prev["finalisten"]:
        bars5 = read_bars(data / f"{sym}_5min.csv.gz")
        if last_value(lines, f"Siegel {sym} ") is None:
            raise SystemExit(f"Keine Prüfsumme für {sym} im Journal.")
        sealed = bars5.loc[a:b]
        recorded = [line for line in lines if f"Siegel {sym} " in line][-1].split("sha256 ")[1].strip()
        if bars_hash(sealed) != recorded:
            raise SystemExit(f"Die Kerzen von {sym} im versiegelten Fenster haben sich geändert.")
        mk = next(x for x in prev["markets"] if x["symbol"] == sym)
        g = mk["gewaehlt"]
        P = prepare(bars5, g["zeitrahmen"], specs[sym])
        res = evaluate(P, (a, b), g["seiten"], fuehrung(r1["fuehrungen"][g["fuehrung"]]), r1)
        tr, *_ = res.pop("_ctx")
        res["verfehlt"] = check_window(res, r1["siegel_schwellen"])
        r = r_with_swap(tr, r1["swap_pct_jahr"]) if len(tr) else np.array([])
        konto = 250.0 * np.cumprod(1 + 0.02 * r) if len(r) else np.array([250.0])
        res["spielkonto_250_2pct"] = round(float(konto[-1]), 2)
        res["kurve"] = [[str(pd.Timestamp(t).date()), round(float(x), 2)]
                        for t, x in zip(tr["exit_time"], np.cumsum(r))] if len(r) else []
        results.append({"symbol": sym, "name": mk["name"], **g, "siegel": res})
    journal_add("Siegel geöffnet für " + (", ".join(prev["finalisten"]) or "niemand") + ": "
                + "; ".join(f"{x['symbol']} {'bestanden' if not x['siegel']['verfehlt'] else 'nicht bestanden'}" for x in results))
    (out / "runde1-siegel.json").write_text(json.dumps({"made": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                                                         "results": results}, ensure_ascii=False, indent=1, default=str),
                                            encoding="utf-8")
    for x in results:
        print(x["symbol"], x["zeitrahmen"], x["fuehrung"], x["seiten"], {k: x["siegel"][k] for k in ("trades", "pf_r", "sum_r", "robust_sum_r", "verfehlt")})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
