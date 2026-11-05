"""Backtest-Protokoll für die Gold-Strategien nach der Wissensbasis (wissen/youtube/SYNTHESE.md 4.6 und 6.2).

Usage (from the repo root):
    python -m gold.backtest.protocol <data_dir> <out_dir>                  # nur das Entwicklungsfenster
    python -m gold.backtest.protocol <data_dir> <out_dir> --open-sealed    # einmalig: versiegeltes Fenster
    python -m gold.backtest.protocol <data_dir> <out_dir> --neue-vorab "Grund"

Was es tut:
1. VORAB.yaml legt Fenster, Kosten, Varianten und Schwellen fest, bevor gerechnet wird. Ihre Prüfsumme und
   die der Kursdaten im versiegelten Fenster stehen in journal/gold-backtest-protokoll.md. Ändert sich eine
   der beiden ohne Eintrag mit Grund, bricht der Lauf ab.
2. Jede Variante läuft mit den Regeln des Bots (run_live) im Entwicklungsfenster und wird gemessen an:
   gematchten Zufalls-Zwillingen, Gold-Buy-and-Hold, Gewinn je Strategie, Drawdown aufs Startkapital,
   Ausstiegsgründen, R-Vielfachen und dem Kostenanteil.
3. Nur Varianten, die alle Schwellen erfüllen, dürfen ins versiegelte Fenster, und das genau einmal.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yaml

from gold.backtest.engine import run_live, summary
from gold.backtest.pine_port import signals_b_short, signals_c_long
from gold.backtest.run_backtest import load, months, resample

HERE = pathlib.Path(__file__).resolve().parent
VORAB = HERE / "VORAB.yaml"
JOURNAL = HERE.parents[1] / "journal" / "gold-backtest-protokoll.md"
SESSION_START = "22h"           # Goldhandel beginnt Sonntag 22:00 UTC (im Sommer 21:00), Tageskerzen ab 22:00


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def data_hash(m1: pd.DataFrame) -> str:
    """Prüfsumme der 1-Minuten-Kerzen eines Fensters (Zeit und OHLC, auf Cent gerundet)."""
    return sha256_text(m1[["open", "high", "low", "close"]].round(2).to_csv())


def session_bars(m1: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Kerzen ab 22:00 UTC. Reste bis zu einem Viertel der üblichen Minuten (Sonntagabend im Sommer) fallen weg."""
    if rule in ("1min", "5min", "15min", "60min"):
        return resample(m1, rule)
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    step = pd.Timedelta("24h" if rule == "1D" else rule)          # Tick-Frequenz, sonst wirkt offset nicht
    grouped = m1.resample(step, label="left", closed="left", offset=SESSION_START)
    bars = grouped.agg(agg)
    minutes = grouped["close"].count()
    full = step.total_seconds() / 60
    return bars[minutes > full / 4].dropna(subset=["open"])


def trend_ema(bars: pd.DataFrame, length: int = 200) -> pd.Series:
    """request.security mit Trend-Zeitrahmen = Chart-Zeitrahmen und ta.ema(close, length)[1]: die EMA der
    vorigen Kerze. na, bis `length` Kerzen da sind."""
    ema = bars["close"].ewm(span=length, adjust=False).mean()
    ema.iloc[:length - 1] = np.nan
    return ema.shift(1)


def signals(bars: pd.DataFrame, timeframe: str, trend: str):
    """C (Long) und B (Short) mit Trendfilter, wie in TradingView mit dem Häkchen beim Trendfilter."""
    if trend == "60min":
        return signals_c_long(bars, useTrend=True), signals_b_short(bars, useTrend=True)
    if trend != timeframe:
        raise ValueError("Trend-Zeitrahmen muss 60min oder der Chart-Zeitrahmen sein")
    ema = trend_ema(bars)
    c, b = signals_c_long(bars), signals_b_short(bars)
    c["entry"] = c["entry"] & (bars["close"] > ema)
    b["entry"] = b["entry"] & (bars["close"] < ema)
    return c, b


def trend_side(bars: pd.DataFrame, trend: str) -> tuple[pd.Series, pd.Series]:
    if trend == "60min":
        from gold.backtest.pine_port import htf_ema
        ema = htf_ema(bars)
    else:
        ema = trend_ema(bars)
    return bars["close"] > ema, bars["close"] < ema


def drawdown_on_start(curve: pd.Series, start: float) -> float:
    """Größter Rückgang vom bisherigen Höchststand in Prozent des Startkapitals (#10: 27,5 % vom Hoch
    können 72 % des Starts sein)."""
    return round(100 * float((curve.cummax() - curve).max()) / start, 1) if len(curve) else 0.0


def buy_and_hold_pct(bars: pd.DataFrame) -> float:
    return round(100 * (float(bars["close"].iloc[-1]) / float(bars["open"].iloc[0]) - 1), 1)


def twin_trades(bars: pd.DataFrame, trades: pd.DataFrame, long_ok: pd.Series, short_ok: pd.Series,
                rng: np.random.Generator, spread: float, swap_pct: float, eurusd: float,
                size_oz: float, stop_usd: float | None) -> list[tuple[int, float]]:
    """Ein Lauf gematchter Zufalls-Zwillinge: je echtem Trade einer mit derselben Seite und Haltedauer, das
    Signal auf einer zufälligen Kerze in Trendrichtung, Füllung zur nächsten Eröffnung, gleicher Notfall-Stop,
    gleiche Kosten. Zwillinge dürfen sich überlappen, Limits gelten nicht (der Zufall wird eher begünstigt).
    Gibt je Zwilling (Kerze des Ausstiegs, Ergebnis in €) zurück."""
    o, h, l, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    days = bars.index.normalize()
    pos_of = pd.Series(np.arange(len(bars)), index=bars.index)
    ok = {1: np.flatnonzero(long_ok.to_numpy(bool)[:-1]), -1: np.flatnonzero(short_ok.to_numpy(bool)[:-1])}
    out = []
    for tr in trades.itertuples():
        side = 1 if tr.side == "long" else -1
        hold = max(int(pos_of[tr.exit_time] - pos_of[tr.entry_time]), 1)
        pool = ok[side][ok[side] + 1 + hold < len(bars)]
        if not len(pool):
            continue
        t = int(rng.choice(pool)) + 1
        epx = o[t] + spread if side > 0 else o[t]
        stop = None if stop_usd is None else (epx - stop_usd if side > 0 else epx + stop_usd)
        end, xpx = t + hold, None
        for u in range(t, end):
            if stop is not None and side > 0 and l[u] <= stop:
                xpx, end = min(o[u], stop), u
                break
            if stop is not None and side < 0 and h[u] + spread >= stop:
                xpx, end = max(o[u] + spread, stop), u
                break
        if xpx is None:
            xpx = o[end] if side > 0 else o[end] + spread
        nights = int((days[end] - days[t]).days)
        swap = c[t] * size_oz * swap_pct / 100 / 365 * nights
        out.append((end, (side * (xpx - epx) * size_oz - swap) / eurusd))
    return out


def twin_net(bars: pd.DataFrame, trades: pd.DataFrame, long_ok: pd.Series, short_ok: pd.Series,
             rng: np.random.Generator, spread: float, swap_pct: float, eurusd: float,
             size_oz: float, stop_usd: float | None) -> float:
    """Summe eines Laufs von twin_trades."""
    return sum((net for _, net in twin_trades(bars, trades, long_ok, short_ok, rng, spread, swap_pct,
                                              eurusd, size_oz, stop_usd)), 0.0)


def evaluate(bars: pd.DataFrame, variant: dict, cfg: dict, rng: np.random.Generator) -> dict:
    k, cost, acc = variant, cfg["kosten"], cfg["konto"]
    spread = pd.Series(cost["spread_usd"], index=bars.index)
    sc, sb = signals(bars, k["zeitrahmen"], k["trend"])
    tr, curve, skipped, swap_paid = run_live(
        bars, spread, sc, sb, size_oz=acc["size_oz"], start_eur=acc["start_eur"], eurusd=cost["eurusd"],
        stop_usd=k["stop_usd"], conflict=acc["conflict"], swap_pct_year=cost["swap_pct_jahr"],
        day_loss_pct=acc["tag_pct"], week_loss_pct=acc["woche_pct"], kill_dd_pct=acc["not_aus_pct"])
    start = acc["start_eur"]
    s = summary(tr["pnl_eur"] if len(tr) else [], curve, start, months(bars))
    end_eur = float(curve.iloc[-1])
    s.update({"end_eur": round(end_eur, 2), "net_incl_swap": round(end_eur - start, 2),
              "return_incl_swap_pct": round(100 * (end_eur / start - 1), 1),
              "swap_paid_eur": round(swap_paid, 2), "skipped": skipped,
              "max_drawdown_start_pct": drawdown_on_start(curve, start),
              "lowest_eur": round(float(curve.min()), 2),
              "buy_and_hold_pct": buy_and_hold_pct(bars),
              "from": str(bars.index[0]), "to": str(bars.index[-1]), "bars": len(bars)})
    if len(tr):
        s["by_strategy"] = {"C long": round(float(tr.loc[tr.side == "long", "pnl_eur"].sum()), 2),
                            "B short": round(float(tr.loc[tr.side == "short", "pnl_eur"].sum()), 2)}
        s["trades_by_strategy"] = {"C long": int((tr.side == "long").sum()), "B short": int((tr.side == "short").sum())}
        s["exit_reasons"] = tr["reason"].value_counts().to_dict()
        cost_eur = len(tr) * cost["spread_usd"] * acc["size_oz"] / cost["eurusd"] + swap_paid
        gross = (tr["pnl_eur"] + cost["spread_usd"] * acc["size_oz"] / cost["eurusd"]).abs().sum()
        s["cost_share_pct"] = round(100 * cost_eur / gross, 1) if gross else None
        if k["stop_usd"]:
            r = tr["pnl_eur"] / (k["stop_usd"] * acc["size_oz"] / cost["eurusd"])
            s["r_multiple"] = {"mean": round(float(r.mean()), 2), "median": round(float(r.median()), 2),
                               "best": round(float(r.max()), 2), "worst": round(float(r.min()), 2)}
        long_ok, short_ok = trend_side(bars, k["trend"])
        twins = np.array([twin_net(bars, tr, long_ok, short_ok, rng, cost["spread_usd"], cost["swap_pct_jahr"],
                                   cost["eurusd"], acc["size_oz"], k["stop_usd"])
                          for _ in range(cfg["zufall"]["laeufe"])])
        s["random_twins"] = {"median_eur": round(float(np.median(twins)), 2),
                             "p90_eur": round(float(np.percentile(twins, 90)), 2),
                             "as_good_pct": round(100 * float((twins >= s["net_incl_swap"]).mean()), 1)}
    return s


def check(s: dict, limits: dict) -> list[str]:
    """Verfehlte Schwellen. Leer = bestanden."""
    misses = []
    if s["trades"] < limits["min_trades"]:
        misses.append(f"nur {s['trades']} Trades, verlangt {limits['min_trades']}")
    pf = s.get("profit_factor")
    if pf is None or pf < limits["min_gewinnfaktor"]:
        misses.append(f"Gewinnfaktor {pf}, verlangt {limits['min_gewinnfaktor']}")
    if "max_zufall_gleich_gut_pct" in limits:
        good = s.get("random_twins", {}).get("as_good_pct", 100.0)
        if good > limits["max_zufall_gleich_gut_pct"]:
            misses.append(f"{good} % der Zufalls-Zwillinge mindestens so gut, erlaubt {limits['max_zufall_gleich_gut_pct']} %")
    if limits.get("besser_als_buy_and_hold") and s["return_incl_swap_pct"] <= s["buy_and_hold_pct"]:
        misses.append(f"Rendite {s['return_incl_swap_pct']} % nicht über Gold-Buy-and-Hold {s['buy_and_hold_pct']} %")
    if "min_netto_eur" in limits and s["net_incl_swap"] <= limits["min_netto_eur"]:
        misses.append(f"netto {s['net_incl_swap']} €")
    if s["max_drawdown_start_pct"] > limits["max_drawdown_start_pct"]:
        misses.append(f"Drawdown {s['max_drawdown_start_pct']} % vom Start, erlaubt {limits['max_drawdown_start_pct']} %")
    return misses


def label(v: dict) -> str:
    return f"{v['zeitrahmen']} Trend {v['trend']} Stop {v['stop_usd'] if v['stop_usd'] else 'keiner'}"


def journal_lines() -> list[str]:
    return JOURNAL.read_text(encoding="utf-8").splitlines() if JOURNAL.exists() else []


def journal_add(text: str) -> None:
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    head = [] if JOURNAL.exists() else ["# Gold: Backtest-Protokoll", "",
                                        "Jede Zeile ein Ereignis. Nur anhängen, nie ändern (Hygieneregel 2).", ""]
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open(JOURNAL, "a", encoding="utf-8") as fh:
        fh.write("\n".join(head + [f"- {stamp}: {text}"]) + "\n")


def last_value(lines: list[str], key: str) -> str | None:
    found = [line.split(key, 1)[1].split()[0].strip(".,") for line in lines if key in line]
    return found[-1] if found else None


def seal(sealed_m1: pd.DataFrame, vorab_text: str, reason: str | None = None) -> None:
    """VORAB und versiegelte Daten gegen das Journal prüfen; beim ersten Lauf (oder mit Grund) eintragen."""
    lines = journal_lines()
    vorab_now, data_now = sha256_text(vorab_text), data_hash(sealed_m1)
    vorab_old, data_old = last_value(lines, "VORAB sha256 "), last_value(lines, "Daten sha256 ")
    if reason:
        journal_add(f"VORAB geändert, Grund: {reason}. VORAB sha256 {vorab_now}")
    elif vorab_old is None:
        journal_add(f"VORAB festgelegt. VORAB sha256 {vorab_now}")
    elif vorab_old != vorab_now:
        raise SystemExit("VORAB.yaml wurde geändert. Erst mit --neue-vorab \"Grund\" im Journal eintragen.")
    if data_old is None:
        journal_add(f"Versiegeltes Fenster {sealed_m1.index[0]} bis {sealed_m1.index[-1]}, "
                    f"{len(sealed_m1)} Minuten. Daten sha256 {data_now}")
    elif data_old != data_now:
        raise SystemExit("Die Kursdaten im versiegelten Fenster haben sich geändert. Nicht weiterrechnen, erst klären.")


def report_lines(title: str, rows: list[tuple[dict, dict, list[str]]]) -> list[str]:
    out = [f"## {title}", "",
           "| Variante | Trades | Gewinnfaktor | netto € | Rendite % | Gold B&H % | DD vom Start % | Zufall so gut % "
           "| C long € | B short € | Kostenanteil % | bestanden |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for v, s, misses in rows:
        st = s.get("by_strategy", {})
        out.append(f"| {label(v)}{' (schon gesehen)' if v.get('schon_gesehen') else ''} | {s['trades']} "
                   f"| {s.get('profit_factor')} | {s['net_incl_swap']} | {s['return_incl_swap_pct']} "
                   f"| {s['buy_and_hold_pct']} | {s['max_drawdown_start_pct']} "
                   f"| {s.get('random_twins', {}).get('as_good_pct')} | {st.get('C long')} | {st.get('B short')} "
                   f"| {s.get('cost_share_pct')} | {'ja' if not misses else 'nein'} |")
    out.append("")
    for v, s, misses in rows:
        if misses:
            out.append(f"- {label(v)}: " + "; ".join(misses))
    return out + [""]


def main(argv: list[str]) -> int:
    data_dir, out_dir, *rest = argv
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    vorab_text = VORAB.read_text(encoding="utf-8")
    cfg = yaml.safe_load(vorab_text)
    reason = rest[rest.index("--neue-vorab") + 1] if "--neue-vorab" in rest else None
    m1 = load(data_dir)
    dev_from, dev_to = cfg["fenster"]["entwicklung"]
    seal_from, seal_to = cfg["fenster"]["versiegelt"]
    seal(m1.loc[seal_from:seal_to], vorab_text, reason)
    rng = np.random.default_rng(cfg["zufall"]["seed"])

    dev_rows, results = [], {}
    for v in cfg["varianten"]:
        bars = session_bars(m1.loc[dev_from:dev_to], v["zeitrahmen"])
        s = evaluate(bars, v, cfg, rng)
        misses = check(s, cfg["schwellen_entwicklung"])
        if v.get("schon_gesehen"):
            misses = ["schon über alle Daten angesehen, kein Vorabtest"] + misses
        dev_rows.append((v, s, misses))
        results[label(v)] = {"entwicklung": s, "verfehlt": misses}
        print("  fertig", label(v), flush=True)
    passed = [v for v, s, misses in dev_rows if not misses]
    journal_add(f"Entwicklungsfenster gerechnet, {len(dev_rows)} Varianten, bestanden: "
                + (", ".join(label(v) for v in passed) or "keine"))
    lines = [f"# Gold-Backtest-Protokoll ({datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC)", "",
             f"VORAB sha256 {sha256_text(vorab_text)}. Kosten: Spread {cfg['kosten']['spread_usd']} $, "
             f"Übernacht {cfg['kosten']['swap_pct_jahr']} % im Jahr. {len(cfg['varianten'])} Varianten getestet.", ""]
    lines += report_lines(f"Entwicklungsfenster {dev_from} bis {dev_to}", dev_rows)

    if "--open-sealed" in rest:
        if any("versiegelt geöffnet" in line for line in journal_lines()):
            raise SystemExit("Das versiegelte Fenster wurde schon geöffnet. Ein zweites Mal gibt es nicht.")
        if not passed:
            journal_add("Öffnen verlangt, aber keine Variante hat das Entwicklungsfenster bestanden. Fenster bleibt zu.")
        else:
            seal_rows = []
            for v in passed:
                bars = session_bars(m1.loc[seal_from:seal_to], v["zeitrahmen"])
                s = evaluate(bars, v, cfg, rng)
                misses = check(s, cfg["schwellen_versiegelt"])
                seal_rows.append((v, s, misses))
                results[label(v)]["versiegelt"] = s
            lines += report_lines(f"Versiegeltes Fenster {seal_from} bis {seal_to}", seal_rows)
            journal_add("versiegelt geöffnet für " + ", ".join(
                f"{label(v)}: {'bestanden' if not m else 'nicht bestanden'}" for v, s, m in seal_rows))
    (out / "protokoll.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "protokoll.json").write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
