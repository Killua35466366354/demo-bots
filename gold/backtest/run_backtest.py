"""Backtest both strategies on 1, 5, 15 and 60 minute gold bars.

Usage (from the repo root): python3 -m gold.backtest.run_backtest <data_dir> <out_dir> [spread_usd ...]
On Kiron's Mac, where the files sit flat in one folder: python3 backtest/run_backtest.py <data_dir> <out_dir>
data_dir holds either the HistData.com ZIPs (read directly, same rules as convert_histdata.py) or the
monthly XAUUSD_M1_*.csv.gz files written by convert_histdata.py or fetch_dukascopy.py.
Each spread gives report_spread_<x>.json; without a spread the one in the files is used (0.30 for ZIPs).
summary.txt collects the main numbers of every run in one table.

Signal sets: "orig" = both strategies with Kiron's default inputs.
"trend" = the v6 pair with their trend filters switched on: C (long mirror of B, same signals as A with
defaults) only long above the 60-minute EMA 200, B only short below it. A v2 itself has no such input.
"""
import json
import pathlib
import sys
import zipfile

import pandas as pd

try:
    from gold.backtest.engine import run_live, run_tv, summary
    from gold.backtest.pine_port import signals_a_long, signals_b_short, signals_c_long
except ImportError:                      # flat copy next to engine.py and pine_port.py
    from engine import run_live, run_tv, summary
    from pine_port import signals_a_long, signals_b_short, signals_c_long

TIMEFRAMES = ["1min", "5min", "15min", "60min"]
STOPS = [None, 5.6, 10.0, 20.0]          # USD distance of the bot's emergency stop for 1 oz
EST = pd.Timedelta(hours=5)              # HistData time is EST without daylight saving


def load(data_dir):
    zips = sorted(pathlib.Path(data_dir).glob("*.zip"))
    if not zips:
        files = sorted(pathlib.Path(data_dir).glob("XAUUSD_M1_*.csv.gz"))
        df = pd.concat(pd.read_csv(f, index_col="time", parse_dates=["time"]) for f in files)
        return df[~df.index.duplicated()].sort_index()
    frames = []
    for path in zips:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.lower().endswith(".csv"):
                    frames.append(pd.read_csv(z.open(name), sep=";", header=None, dtype={"t": str},
                                              names=["t", "open", "high", "low", "close", "vol"]))
    df = pd.concat(frames)
    df.index = pd.to_datetime(df["t"], format="%Y%m%d %H%M%S") + EST
    df.index.name = "time"
    df = df[["open", "high", "low", "close"]].astype(float)
    df["spread_open"] = 0.30
    return df[~df.index.duplicated(keep="last")].sort_index()


def resample(m1, rule):
    if rule == "1min":
        return m1
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "spread_open": "first"}
    return m1.resample(rule, label="left", closed="left").agg(agg).dropna(subset=["open"])


def months(df):
    return (df.index[-1] - df.index[0]).days / 30.44


def signal_sets(bars):
    return {"orig": (signals_a_long(bars), signals_b_short(bars)),
            "trend": (signals_c_long(bars, useTrend=True), signals_b_short(bars, useTrend=True))}


def backtest(m1):
    report = {"data": {"from": str(m1.index[0]), "to": str(m1.index[-1]), "bars_1min": len(m1),
                       "median_spread_usd": round(float(m1["spread_open"].median()), 3)}}
    for name in TIMEFRAMES:
        bars = resample(m1, name)
        mo = months(bars)
        res = {"bars": len(bars)}
        for set_name, (sa, sb) in signal_sets(bars).items():
            res[f"signals_{set_name}"] = {"A_entries": int(sa["entry"].sum()), "A_exits": int(sa["exit"].sum()),
                                          "B_entries": int(sb["entry"].sum()), "B_exits": int(sb["exit"].sum())}
            for label, sig, side, cap in (("A_tv", sa, 1, 10000.0), ("B_tv", sb, -1, 1000000.0)):
                tr, curve = run_tv(bars, sig, side, init_cap=cap)
                s = summary(tr["pnl"] if len(tr) else [], curve, cap, mo)
                pos = tr.groupby("pos_id")["pnl"].sum() if len(tr) else pd.Series(dtype=float)
                s["positions"] = int(len(pos))
                s["position_win_rate_pct"] = round(100 * (pos > 0).mean(), 1) if len(pos) else None
                s["entries_per_position"] = round(len(tr) / len(pos), 2) if len(pos) else None
                if len(tr):
                    s["net_by_year"] = tr.groupby(pd.to_datetime(tr["exit_time"]).dt.year)["pnl"].sum().round(0).to_dict()
                res[f"{label}_{set_name}"] = s
            for stop in STOPS:
                for rule_name in ("first", "reverse"):
                    tr, curve, skipped, swap = run_live(bars, bars["spread_open"], sa, sb, stop_usd=stop,
                                                        conflict=rule_name, day_loss_pct=4, week_loss_pct=8,
                                                        kill_dd_pct=25)
                    s = summary(tr["pnl_eur"] if len(tr) else [], curve, 250.0, mo)
                    s["skipped"] = skipped
                    s["end_eur"] = round(float(curve.iloc[-1]), 2)
                    if len(tr):
                        s["by_side"] = {k: summary(g["pnl_eur"], curve, 250.0, mo)["net"]
                                        for k, g in tr.groupby("side")}
                        s["exit_reasons"] = tr["reason"].value_counts().to_dict()
                        s["net_by_year"] = tr.groupby(pd.to_datetime(tr["exit_time"]).dt.year)["pnl_eur"].sum().round(2).to_dict()
                        hold = (pd.to_datetime(tr["exit_time"]) - pd.to_datetime(tr["entry_time"]))
                        s["median_hold_min"] = round(hold.dt.total_seconds().median() / 60, 1)
                    res[f"live_{set_name}_stop{stop}_{rule_name}"] = s
        report[name] = res
        print("  done", name, flush=True)
    return report


def table(report):
    keys = ["trades", "win_rate_pct", "profit_factor", "net", "max_drawdown_pct"]
    d = report["data"]
    lines = [f"## spread {d['median_spread_usd']:.2f} USD, data {d['from']} to {d['to']}, {d['bars_1min']} bars"]
    for tf in TIMEFRAMES:
        for label, s in report[tf].items():
            if label.startswith("signals"):
                lines.append(f"{tf} {label} {json.dumps(s)}")
            elif isinstance(s, dict):
                extra = {k: s[k] for k in ("positions", "position_win_rate_pct", "end_eur", "by_side",
                                           "net_by_year", "exit_reasons", "skipped") if k in s}
                lines.append(f"{tf} " + " | ".join([label] + [str(s.get(k)) for k in keys]) + " | "
                             + json.dumps(extra, default=str))
    return lines


def main(data_dir, out_dir, *spreads):
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    m1 = load(data_dir)
    print("loaded", len(m1), "bars", m1.index[0], "to", m1.index[-1], flush=True)
    lines = ["label | trades | win_rate_pct | profit_factor | net | max_drawdown_pct | extra"]
    for spread in spreads or [None]:
        run = m1.copy()
        if spread is not None:
            run["spread_open"] = float(spread)
        report = backtest(run)
        tag = f"{report['data']['median_spread_usd']:.2f}"
        (out / f"report_spread_{tag}.json").write_text(json.dumps(report, indent=1, default=str))
        lines += table(report)
    (out / "summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main(*sys.argv[1:])
