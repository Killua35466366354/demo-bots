"""Strategie-Suche, Runde 3: beide Gold-Logiken auf vielen Capital.com-Märkten, März bis Oktober 2026
(suche/VORAB_runde3.yaml).

Usage (from the repo root):
    python -m suche.runde3 --festlegen "Grund"       # Prüfsumme der VORAB ins Journal, BEVOR gerechnet wird
    python -m suche.runde3 <kerzen> <out_dir>         # Rangliste, Null-Suche, Demo-Kandidaten

<kerzen> ist der Ordner mit <EPIC>_MINUTE_15.csv.gz und bericht_runde3.json aus suche/runde3_kerzen.py.

Die Bausteine (prepare, entries) benutzt auch der Demo-Bot (suche/demo_bots.py), damit Backtest und Demo genau
dieselben Signale, Filter und Führungen rechnen.
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

from gold.backtest.pine_port import signals_b_short, signals_c_long
from gold.backtest.runde2 import pf, r_with_swap
from gold.backtest.sizing import atr_rma
from gold.v2 import news, richtung, termine
from gold.v2.fuehrung import Fuehrung, Markt, run_v2
from suche.runde1 import journal_add, journal_lines, last_value

HERE = pathlib.Path(__file__).resolve().parent
VORAB = HERE / "VORAB_runde3.yaml"
SIDES = {"C+B": (True, True), "nur C": (True, False), "nur B": (False, True)}
AGG = {"open": "first", "high": "max", "low": "min", "close": "last"}
KEY = "VORAB_runde3 sha256 "


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_vorab() -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("suche/VORAB_runde3.yaml steht so nicht im Journal. Erst --festlegen \"Grund\" und committen.")
    return yaml.safe_load(text)


# ---------- Kerzen ----------

def read_capital(path: str | pathlib.Path) -> tuple[pd.DataFrame, pd.Series]:
    """CSV aus runde3_kerzen -> Bid-Kerzen (open/high/low/close) und Spread zur Eröffnung je Kerze."""
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.DatetimeIndex(df.index).tz_localize(None) if df.index.tz is not None else pd.DatetimeIndex(df.index)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=["open_bid", "high_bid", "low_bid", "close_bid"])
    bars = df[["open_bid", "high_bid", "low_bid", "close_bid"]].astype(float)
    bars.columns = ["open", "high", "low", "close"]
    spread = (df["open_ask"] - df["open_bid"]).astype(float)
    spread = spread.where(spread >= 0).ffill().fillna(0.0)
    return bars, spread


def resample(bars: pd.DataFrame, spread: pd.Series, tf: str) -> tuple[pd.DataFrame, pd.Series]:
    """Größere Kerzen aus kleineren, Beginn zur vollen Zeit (UTC). Spread: der der ersten Teilkerze."""
    if tf == "15min":
        return bars, spread
    g = bars.resample(tf, label="left", closed="left")
    out = g.agg(AGG).dropna(subset=["open"])
    sp = spread.resample(tf, label="left", closed="left").first().reindex(out.index).ffill().fillna(0.0)
    return out, sp


def trend_ema(hourly: pd.DataFrame, index: pd.DatetimeIndex, length: int = 200) -> np.ndarray:
    """Wie pine_port.htf_ema: EMA 200 der Stundenschlüsse, Wert der letzten FERTIGEN Stunde, für jede Kerze in index."""
    ema = hourly["close"].ewm(span=length, adjust=False).mean()
    ema.iloc[:length - 1] = np.nan
    # Als-ob-Suche statt reindex: dieselben Werte wie htf_ema, aber auch richtig, wenn die laufende Stunde (im Bot)
    # noch fehlt. Wert = EMA der letzten Stunde, die bis zum Beginn der Stunde der Kerze fertig war.
    closes = (ema.index + pd.Timedelta("60min")).to_numpy()
    pos = np.searchsorted(closes, index.floor("60min").to_numpy(), side="right") - 1
    vals = ema.to_numpy(float)
    return np.where(pos >= 0, vals[np.clip(pos, 0, None)], np.nan)


def richtung_on(hourly: pd.DataFrame, index: pd.DatetimeIndex, tf: str) -> np.ndarray:
    """Markt-Richtung von Gold-Bot 2.0 (aus Stundenkerzen) für Kerzen in index, gültig auf ihrem Schluss."""
    try:
        r = richtung.direction(hourly)
    except IndexError:
        # Märkte mit sehr kurzer Handelszeit (z. B. Lean Hogs, Live Cattle: etwa 5 Stunden am Tag) haben keine
        # vollen Tages- oder 4-Stunden-Kerzen. Dann gibt es keine Richtung, Gold-Bot 2.0 steigt dort nie ein.
        return np.zeros(len(index), dtype=int)
    closes = (hourly.index + pd.Timedelta("60min")).to_numpy()
    pos = np.searchsorted(closes, (index + pd.Timedelta(tf)).to_numpy(), side="right") - 1
    vals = r.to_numpy()
    return np.where(pos >= 0, vals[np.clip(pos, 0, None)], 0).astype(int)


@dataclasses.dataclass
class Prepared:
    tf: str
    bars: pd.DataFrame
    m: Markt
    entries: dict           # logik -> (long, short), bool je Kerze, alle Filter
    pools: dict             # logik -> (long, short): Kerzen, auf denen ein Zufalls-Einstieg erlaubt ist


def prepare(bars: pd.DataFrame, spread: pd.Series, hourly: pd.DataFrame, tf: str, events: pd.Series,
            nw: dict) -> Prepared:
    """Signale (Pine unverändert, Trend aus Stundenkerzen wie htf_ema), Filter von 2.0 und Markt-Arrays."""
    sc, sb = signals_c_long(bars), signals_b_short(bars)      # ohne Trend; den Trendfilter setzt trend_ema davor
    ema = trend_ema(hourly, bars.index)
    c = bars["close"].to_numpy(float)
    up, down = c > ema, c < ema                                # NaN-Vergleiche sind False wie in Pine
    raw_l = sc["entry"].to_numpy(bool) & up
    raw_s = sb["entry"].to_numpy(bool) & down
    atr = atr_rma(bars)
    rich = richtung_on(hourly, bars.index, tf)
    pause = news.entry_pause(bars.index, events, nw["pause_vorher_h"], nw["pause_nachher_h"]).to_numpy()
    flat = news.flat_before(bars.index, events, nw["flach_vorher_min"]).to_numpy()
    shock = news.shock_pause(bars, atr, nw["schock_atr"], nw["schock_pause_kerzen"]).to_numpy()
    ok = ~pause & ~shock
    m = Markt.build(bars, spread, atr, sc, sb, rich, ema, flat)
    return Prepared(tf, bars, m,
                    {"gold": (raw_l, raw_s), "gold2": (raw_l & (rich == 1) & ok, raw_s & (rich == -1) & ok)},
                    {"gold": (up, down), "gold2": (up & (rich == 1) & ok, down & (rich == -1) & ok)})


def fuehrung(spec: dict) -> Fuehrung:
    f = spec["fuehrung"]
    return Fuehrung(stop_atr=f["stop_atr"], tp_atr=f.get("ziel_atr"), max_bars=f.get("max_kerzen"),
                    exit_signal=f["ausstieg_signal"], dir_exit=bool(f.get("raus_bei_richtungswechsel")),
                    news_exit=bool(f.get("raus_vor_termin")))


def span(index: pd.DatetimeIndex, window) -> slice:
    a, b = window
    return slice(int(index.searchsorted(pd.Timestamp(a))), int(index.searchsorted(pd.Timestamp(b), side="right")))


def run_r(P: Prepared, s: slice, el: np.ndarray, es: np.ndarray, f: Fuehrung, swap: float, spread_factor: float = 1.0):
    m = P.m.slice(s.start, s.stop)
    if spread_factor != 1.0:
        m = dataclasses.replace(m, sp=m.sp * spread_factor)
    tr = run_v2(m, el, es, f, start_eur=1e12, eurusd=1.0, margin_rate=0.0, size_oz=1.0, swap_pct_year=0.0)[0]
    return tr, (r_with_swap(tr, swap) if len(tr) else np.array([]))


def measure(tr: pd.DataFrame, r: np.ndarray) -> dict:
    if not len(r):
        return {"trades": 0, "win_pct": None, "pf_r": None, "sum_r": 0.0, "max_dd_r": 0.0, "monate": {}}
    cum = np.cumsum(r)
    months = pd.to_datetime(tr["entry_time"]).dt.strftime("%Y-%m").to_numpy()
    side = tr["side"].to_numpy()
    return {"trades": int(len(r)), "win_pct": round(100 * float((r > 0).mean()), 1), "pf_r": pf(r),
            "sum_r": round(float(r.sum()), 1), "mean_r": round(float(r.mean()), 3),
            "max_dd_r": round(float((np.maximum.accumulate(np.r_[0.0, cum]) - np.r_[0.0, cum]).max()), 1),
            "avg_kerzen": round(float(tr["bars"].mean()), 1),
            "long_r": round(float(r[side == "long"].sum()), 1), "short_r": round(float(r[side == "short"].sum()), 1),
            "monate": {mo: round(float(r[months == mo].sum()), 1) for mo in sorted(set(months.tolist()))},
            "gruende": {k: int(v) for k, v in tr["reason"].value_counts().items()}}


def passes(res: dict, rule: dict) -> bool:
    return res["trades"] >= rule["min_trades"] and (res["pf_r"] or 0) > rule["min_gewinnfaktor_r"]


def random_entries(rng: np.random.Generator, pool: np.ndarray, n: int) -> np.ndarray:
    out = np.zeros(len(pool), bool)
    idx = np.flatnonzero(pool[:-1])
    if n and len(idx):
        out[rng.choice(idx, size=min(n, len(idx)), replace=False)] = True
    return out


def null_run(P: Prepared, s: slice, logik: str, side: str, f: Fuehrung, swap: float, rng) -> dict:
    """Ein Lauf mit zufälligen Einstiegen: gleich viele wie die echten Signale je Seite, nur auf erlaubten Kerzen."""
    use_l, use_s = SIDES[side]
    el, es = (x[s] for x in P.entries[logik])
    pl, ps = (x[s] for x in P.pools[logik])
    rl = random_entries(rng, pl, int(el.sum())) if use_l else np.zeros(len(pl), bool)
    rs = random_entries(rng, ps, int(es.sum())) if use_s else np.zeros(len(ps), bool)
    tr, r = run_r(P, s, rl, rs, f, swap)
    return {"trades": int(len(r)), "pf_r": pf(r) if len(r) else None}


# ---------- Ein Markt ----------

def market_job(args) -> dict:
    """Ein Markt, alle Kombis. Ein Fehler in einem Markt stoppt nicht die ganze Runde, er steht im Bericht."""
    try:
        return _market_job(args)
    except Exception as err:          # noqa: BLE001
        path, info = args[0], args[1]
        print(info["epic"], "Fehler", repr(err), flush=True)
        return {"epic": info["epic"], "name": (info.get("meta") or {}).get("name") or info.get("name"),
                "typ": info.get("typ"), "nur_vergleich": bool(info.get("nur_vergleich")), "kombis": [],
                "fehler": f"Rechenfehler: {err!r}"}


def _market_job(args) -> dict:
    path, info, cfg, null_seed = args
    r3 = cfg["runde_3"]
    out = {"epic": info["epic"], "name": (info.get("meta") or {}).get("name") or info.get("name"),
           "typ": info.get("typ"), "nur_vergleich": bool(info.get("nur_vergleich")), "kombis": []}
    try:
        bars15, spread15 = read_capital(path)
    except Exception as err:          # noqa: BLE001 - kaputte Datei: Markt fällt heraus, steht im Bericht
        out["fehler"] = f"Kerzen nicht lesbar: {err}"
        return out
    a, b = r3["fenster"]
    if len(bars15) < 500 or bars15.index[0] > pd.Timestamp(r3["fenster"][0]) - pd.Timedelta(days=30):
        out["fehler"] = f"zu wenige Kerzen ({len(bars15)}, ab {bars15.index[0] if len(bars15) else '-'})"
        return out
    out["kerzen_15min"] = int(len(bars15))
    win = bars15.loc[a:b]
    if len(win) < 200:
        out["fehler"] = f"im Fenster nur {len(win)} Kerzen"
        return out
    sp_atr = float(np.nanmedian(spread15.loc[a:b].to_numpy() / np.maximum(atr_rma(bars15)[bars15.index.get_indexer(win.index)], 1e-12)))
    out["spread_in_atr_15min"] = round(sp_atr, 3)
    swap = r3["kosten"]["swap_pct_jahr"].get(info.get("typ"), 6.0)
    events = termine.load()["utc"]
    hourly, _ = resample(bars15, spread15, "60min")
    rng = np.random.default_rng(null_seed)
    for tf in r3["zeitrahmen"]:
        bars, spread = resample(bars15, spread15, tf)
        P = prepare(bars, spread, hourly, tf, events, r3["logiken"]["gold2"]["news"])
        s = span(bars.index, r3["fenster"])
        for logik, spec in r3["logiken"].items():
            f = fuehrung(spec)
            for side in r3["seiten"]:
                use_l, use_s = SIDES[side]
                el, es = (x[s] for x in P.entries[logik])
                el, es = el & use_l, es & use_s
                tr, r = run_r(P, s, el, es, f, swap)
                res = measure(tr, r)
                _, r2 = run_r(P, s, el, es, f, swap, r3["kosten"]["spread_faktor_robust"])
                res["robust_pf_r"] = pf(r2) if len(r2) else None
                res.update({"zeitrahmen": tf, "logik": logik, "seiten": side})
                res["regel"] = passes(res, r3["regel_demo"])
                nulls = [null_run(P, s, logik, side, f, swap, rng) for _ in range(r3["zufall"]["null_suche"]["laeufe"])]
                res["null"] = {"regel": sum(passes(n, r3["regel_demo"]) for n in nulls),
                               "ab_1_5": sum(n["trades"] >= r3["regel_demo"]["min_trades"] and (n["pf_r"] or 0) >= 1.5
                                             for n in nulls),
                               "laeufe": len(nulls)}
                out["kombis"].append(res)
    print(info["epic"], "fertig", sum(k["regel"] for k in out["kombis"]), "von", len(out["kombis"]), flush=True)
    return out


def candidate_twins(args) -> dict:
    """Für einen Demo-Kandidaten: 200 Zufalls-Läufe, wie oft mindestens so guter Gewinnfaktor."""
    path, info, cfg, combo = args
    r3 = cfg["runde_3"]
    bars15, spread15 = read_capital(path)
    hourly, _ = resample(bars15, spread15, "60min")
    bars, spread = resample(bars15, spread15, combo["zeitrahmen"])
    P = prepare(bars, spread, hourly, combo["zeitrahmen"], termine.load()["utc"], r3["logiken"]["gold2"]["news"])
    s = span(bars.index, r3["fenster"])
    f = fuehrung(r3["logiken"][combo["logik"]])
    swap = r3["kosten"]["swap_pct_jahr"].get(info.get("typ"), 6.0)
    z = r3["zufall"]["kandidaten"]
    rng = np.random.default_rng(z["seed"])
    pfs = [null_run(P, s, combo["logik"], combo["seiten"], f, swap, rng)["pf_r"] or 0 for _ in range(z["laeufe"])]
    return {"epic": info["epic"], "zufall_gleich_gut_pct": round(100 * float(np.mean(np.array(pfs) >= combo["pf_r"])), 1),
            "zufall_median_pf": round(float(np.median(pfs)), 2)}


def pick(markets: list[dict], rule: dict) -> list[dict]:
    """Kirons Regel: je Markt die beste Variante über der Schwelle, davon die besten `anzahl` nach Gewinnfaktor."""
    best = []
    for mk in markets:
        if mk.get("nur_vergleich") or mk["epic"] in rule.get("nie", []) or not mk.get("kombis"):
            continue
        ok = [k for k in mk["kombis"] if k["regel"]]
        if ok:
            k = max(ok, key=lambda x: (x["pf_r"], x["trades"]))
            best.append({"epic": mk["epic"], "name": mk["name"], "typ": mk["typ"],
                         **{key: k[key] for key in ("zeitrahmen", "logik", "seiten", "trades", "win_pct", "pf_r",
                                                    "robust_pf_r", "sum_r", "max_dd_r", "long_r", "short_r", "monate")}})
    best.sort(key=lambda x: (x["pf_r"], x["trades"]), reverse=True)
    return best


def main(argv: list[str]) -> int:
    if argv[:1] == ["--festlegen"]:
        text = VORAB.read_text(encoding="utf-8")
        journal_add(f"Runde 3 festgelegt, Grund: {argv[1]}. {KEY}{sha256_text(text)}")
        print("Im Journal:", sha256_text(text))
        return 0
    cfg = check_vorab()
    r3 = cfg["runde_3"]
    data, out = pathlib.Path(argv[0]), pathlib.Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    report = json.loads((data / "bericht_runde3.json").read_text(encoding="utf-8"))
    infos = [m for m in report["maerkte"] if m.get("kerzen", {}).get("anzahl")]
    seed = r3["zufall"]["null_suche"]["seed"]
    jobs = [(data / f"{m['epic']}_MINUTE_15.csv.gz", m, cfg, seed + i) for i, m in enumerate(infos)]
    with ProcessPoolExecutor(max_workers=4) as ex:
        markets = list(ex.map(market_job, jobs, chunksize=1))
    rule = r3["regel_demo"]
    ranked = pick(markets, rule)
    chosen = ranked[:rule["anzahl"]]
    by_epic = {m["epic"]: m for m in infos}
    with ProcessPoolExecutor(max_workers=4) as ex:
        tw = list(ex.map(candidate_twins, [(data / f"{c['epic']}_MINUTE_15.csv.gz", by_epic[c["epic"]], cfg, c)
                                           for c in ranked[:15]]))
    tw_by = {t["epic"]: t for t in tw}
    for c in ranked[:15]:
        c.update({k: v for k, v in tw_by[c["epic"]].items() if k != "epic"})
    combos = [k for mk in markets for k in mk.get("kombis", []) if not mk.get("nur_vergleich")]
    n_null = r3["zufall"]["null_suche"]["laeufe"]
    summary = {
        "maerkte_mit_kerzen": len(infos), "maerkte_gerechnet": sum(1 for mk in markets if mk.get("kombis")),
        "varianten": len(combos),
        "regel_bestanden": sum(k["regel"] for k in combos),
        "regel_bestanden_ab_1_5": sum(1 for k in combos if k["regel"] and k["pf_r"] >= 1.5),
        "zufall_regel_im_schnitt": round(sum(k["null"]["regel"] for k in combos) / n_null, 1),
        "zufall_ab_1_5_im_schnitt": round(sum(k["null"]["ab_1_5"] for k in combos) / n_null, 1),
        "maerkte_mit_treffer": len(ranked),
        "demo": [c["epic"] for c in chosen],
    }
    payload = {"made": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
               "vorab_sha256": sha256_text(VORAB.read_text(encoding="utf-8")), "zusammenfassung": summary,
               "rangliste": ranked, "demo": chosen, "markets": markets}
    (out / "runde3.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    journal_add("Runde 3 gerechnet: " + json.dumps(summary, ensure_ascii=False))
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
