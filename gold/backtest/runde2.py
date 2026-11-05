"""Runde 2 des Gold-Backtest-Protokolls: Stop nach ATR, nur C, Größe nach Risiko (VORAB.yaml, Abschnitt runde_2).

Usage (from the repo root):
    python -m gold.backtest.runde2 <data_dir> <out_dir>
    python -m gold.backtest.runde2 <data_dir> <out_dir> --open-sealed   # einmalig, nur nach Kirons Ja

Läuft nur, wenn die aktuelle VORAB.yaml schon im Journal steht (also vor dem Rechnen festgelegt wurde), und rechnet
nur im Entwicklungsfenster. Mit --open-sealed rechnet es zusätzlich die bestandenen Varianten im versiegelten Fenster,
genau einmal für alle Runden zusammen (danach verweigern runde2.py und protocol.py ein zweites Öffnen). Die Indikatoren
laufen dafür ab Oktober 2025 warm, gezählt wird nur ab dem 1.1.2026.

Messgrößen, die nicht von der Kontogröße abhängen, laufen in R (Ergebnis geteilt durch das Risiko des Trades):
Gewinnfaktor, Walk-Forward-Test 2025 und die Zufalls-Zwillinge. Rendite gegen Gold und Rückgang laufen in Euro mit
250 € Start. Dazu ein Bericht fürs kleine Konto (50 € plus 50 € alle zwei Monate) mit Monte-Carlo-Spanne.
"""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yaml

from gold.backtest.protocol import (VORAB, buy_and_hold_pct, journal_add, last_value, journal_lines, seal,
                                    session_bars, sha256_text, signals, trend_side)
from gold.backtest.run_backtest import load
from gold.backtest.sizing import atr_rma, every_n_months, run_risk


def pf(r: pd.Series | np.ndarray) -> float | None:
    r = np.asarray(r, float)
    loss = -r[r <= 0].sum()
    return round(float(r[r > 0].sum() / loss), 2) if loss > 0 else None


def r_with_swap(tr: pd.DataFrame, swap_pct: float) -> np.ndarray:
    """R je Trade inklusive Übernachtkosten (run_risk bucht sie täglich vom Konto, nicht im Trade)."""
    if not len(tr):
        return np.array([])
    nights = (pd.to_datetime(tr["exit_time"]).dt.normalize() - pd.to_datetime(tr["entry_time"]).dt.normalize()).dt.days
    swap_usd = tr["entry_px"] * swap_pct / 100 / 365 * nights
    return ((tr["pnl_eur"] / tr["risk_eur"]) - swap_usd / tr["stop_usd"]).to_numpy(float)


def twin_r(bars, trades, long_ok, short_ok, atr, rng, spread, swap_pct, stop_usd, stop_atr) -> float:
    """Summe der R eines Laufs gematchter Zwillinge: gleiche Seite, gleiche Haltedauer, gleiche Stop-Regel,
    Einstieg auf einer zufälligen Kerze in Trendrichtung (Füllung zur nächsten Eröffnung)."""
    o, h, l, c = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    days = bars.index.normalize()
    pos_of = pd.Series(np.arange(len(bars)), index=bars.index)
    ok = {1: np.flatnonzero(long_ok.to_numpy(bool)[:-1]), -1: np.flatnonzero(short_ok.to_numpy(bool)[:-1])}
    total = 0.0
    for tr in trades.itertuples():
        side = 1 if tr.side == "long" else -1
        hold = max(int(pos_of[tr.exit_time] - pos_of[tr.entry_time]), 1)
        pool = ok[side][ok[side] + 1 + hold < len(bars)]
        if not len(pool):
            continue
        s = int(rng.choice(pool))
        t = s + 1
        dist = stop_usd if stop_atr is None else stop_atr * float(atr[s])
        epx = o[t] + spread if side > 0 else o[t]
        stop = epx - dist if side > 0 else epx + dist
        end, xpx = t + hold, None
        for u in range(t, end):
            if side > 0 and l[u] <= stop:
                xpx, end = min(o[u], stop), u
                break
            if side < 0 and h[u] + spread >= stop:
                xpx, end = max(o[u] + spread, stop), u
                break
        if xpx is None:
            xpx = o[end] if side > 0 else o[end] + spread
        nights = int((days[end] - days[t]).days)
        total += (side * (xpx - epx) - c[t] * swap_pct / 100 / 365 * nights) / dist
    return total


def monte_carlo(r: np.ndarray, n_trades: int, risk_pct: float, start: float, deposit: float, n_deposits: int,
                kill_pct: float, runs: int, seed: int) -> dict:
    """Trade-Reihenfolge neu gezogen (mit Zurücklegen). Jeder Trade riskiert risk_pct des Kontos, Einzahlungen
    gleichmäßig verteilt. Fällt das Konto 25 % unter den Höchststand, handelt der Bot nicht mehr (Not-Aus)."""
    rng = np.random.default_rng(seed)
    dep_at = set(np.linspace(0, n_trades, n_deposits + 2)[1:-1].astype(int))
    ends, kills = [], 0
    for _ in range(runs):
        eq = peak = start
        stopped = False
        for i, x in enumerate(rng.choice(r, size=n_trades, replace=True)):
            if i in dep_at:
                eq += deposit
                peak += deposit
            if stopped:
                continue
            eq *= 1 + risk_pct / 100 * x
            peak = max(peak, eq)
            if eq < peak * (1 - kill_pct / 100):
                stopped = True
        kills += stopped
        ends.append(eq)
    ends = np.array(ends)
    paid = start + deposit * n_deposits
    return {"paid_eur": paid, "p10_eur": round(float(np.percentile(ends, 10)), 0),
            "median_eur": round(float(np.median(ends)), 0), "p90_eur": round(float(np.percentile(ends, 90)), 0),
            "loss_pct": round(100 * float((ends < paid).mean()), 1), "kill_pct": round(100 * kills / runs, 1)}


def daily(curve: pd.Series) -> pd.Series:
    return curve.resample("1D").last().dropna()


def open_sealed(m1: pd.DataFrame, cfg: dict, vorab_text: str, passed: list[dict]) -> dict:
    """Das versiegelte Fenster genau einmal für die bestandenen Varianten der Runde 2 rechnen."""
    if any("versiegelt geöffnet" in line for line in journal_lines()):
        raise SystemExit("Das versiegelte Fenster wurde schon geöffnet. Ein zweites Mal gibt es nicht.")
    if not passed:
        journal_add("Öffnen verlangt (Runde 2), aber keine Variante hat bestanden. Fenster bleibt zu.")
        return {}
    r2, cost, acc = cfg["runde_2"], cfg["kosten"], cfg["konto"]
    seal_from, seal_to = cfg["fenster"]["versiegelt"]
    seal(m1.loc[seal_from:seal_to], vorab_text)                  # Prüfsummen von VORAB und Kursdaten
    warm = session_bars(m1.loc[pd.Timestamp(seal_from) - pd.Timedelta(days=92):seal_to], r2["zeitrahmen"])
    sc, sb = signals(warm, r2["zeitrahmen"], r2["trend"])
    atr = atr_rma(warm)
    keep = warm.index >= pd.Timestamp(seal_from)
    bars, atr, sc, sb = warm[keep], atr[keep], sc[keep], sb[keep]
    spread = pd.Series(cost["spread_usd"], index=bars.index)
    th = r2["schwellen_versiegelt"]
    out = {"from": str(bars.index[0]), "to": str(bars.index[-1]), "gold_pct": buy_and_hold_pct(bars), "rows": [],
           "gold250": [[d.strftime("%Y-%m-%d"), round(250 * float(x) / float(bars["close"].iloc[0]), 2)]
                       for d, x in daily(bars["close"]).items()]}
    for row in passed:
        kw = dict(eurusd=cost["eurusd"], conflict=acc["conflict"], swap_pct_year=cost["swap_pct_jahr"],
                  day_loss_pct=acc["tag_pct"], week_loss_pct=acc["woche_pct"], kill_dd_pct=acc["not_aus_pct"],
                  lot_step=r2["groesse"]["schritt_oz"], stop_usd=None if row.get("stop_atr") else 5.6,
                  stop_atr=row.get("stop_atr"), atr=atr, sides=tuple(row["seiten"]))
        tr, curve, skipped, _, _ = run_risk(bars, spread, sc, sb, start_eur=250.0, risk_pct=r2["groesse"]["risiko_pct"], **kw)
        r = r_with_swap(tr, cost["swap_pct_jahr"])
        kk = r2["kleines_konto"]
        deps = every_n_months(seal_from, seal_to, kk["alle_monate"], kk["einzahlung_eur"])
        _, small, _, _, paid = run_risk(bars, spread, sc, sb, start_eur=kk["start_eur"], deposits=deps,
                                        risk_pct=r2["groesse"]["risiko_pct"], **kw)
        small_rep = {}                                            # nur Bericht, entscheidet nichts
        for rp in r2["risiko_bericht_pct"]:
            _, small_rep[str(rp)], _, _, _ = run_risk(bars, spread, sc, sb, start_eur=kk["start_eur"], deposits=deps,
                                                      risk_pct=rp, **kw)
        res = {"name": row["name"], "trades": int(len(tr)), "win_pct": round(100 * float((r > 0).mean()), 1) if len(r) else None,
               "pf_r": pf(r), "sum_r": round(float(r.sum()), 1), "end_eur": round(float(curve.iloc[-1]), 2),
               "net_eur": round(float(curve.iloc[-1]) - 250, 2),
               "dd_high_pct": round(100 * float((1 - curve / curve.cummax()).max()), 1), "skipped": skipped,
               "small_end_eur": round(float(small.iloc[-1]), 2), "small_paid_eur": round(paid, 2),
               "small_bericht_end_eur": {k: round(float(c.iloc[-1]), 2) for k, c in small_rep.items()},
               "curves": {k: [[d.strftime("%Y-%m-%d"), round(float(x), 2)] for d, x in daily(c).items()]
                          for k, c in {"250": curve, str(r2["groesse"]["risiko_pct"]): small, **small_rep}.items()},
               "trade_list": [{"side": t.side, "in": str(t.entry_time), "out": str(t.exit_time), "in_px": round(t.entry_px, 2),
                               "out_px": round(t.exit_px, 2), "oz": t.oz, "stop_usd": round(t.stop_usd, 2),
                               "eur": round(t.pnl_eur, 2), "r": round(float(rr), 3), "why": t.reason}
                              for t, rr in zip(tr.itertuples(), r)] if len(tr) else []}
        misses = []
        if res["trades"] < th["min_trades"]:
            misses.append(f"nur {res['trades']} Trades")
        if (res["pf_r"] or 0) < th["min_gewinnfaktor_r"]:
            misses.append(f"Gewinnfaktor {res['pf_r']}")
        if res["net_eur"] <= th["min_netto_eur"]:
            misses.append(f"netto {res['net_eur']} €")
        if res["dd_high_pct"] > th["max_drawdown_hoch_pct"]:
            misses.append(f"Rückgang {res['dd_high_pct']} % vom Hoch")
        res["verfehlt"] = misses
        out["rows"].append(res)
        print("  versiegelt", row["name"], res, flush=True)
    journal_add("versiegelt geöffnet (Runde 2) für " + ", ".join(
        f"{x['name']}: {'bestanden' if not x['verfehlt'] else 'nicht bestanden'}" for x in out["rows"]))
    return out


def main(argv: list[str]) -> int:
    data_dir, out_dir = argv[:2]
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    vorab_text = VORAB.read_text(encoding="utf-8")
    if last_value(journal_lines(), "VORAB sha256 ") != sha256_text(vorab_text):
        raise SystemExit("VORAB.yaml steht so nicht im Journal. Erst protocol.py mit --neue-vorab \"Grund\" laufen lassen.")
    cfg = yaml.safe_load(vorab_text)
    r2, cost, acc = cfg["runde_2"], cfg["kosten"], cfg["konto"]
    dev_from, dev_to = cfg["fenster"]["entwicklung"]
    m1 = load(data_dir)
    bars = session_bars(m1.loc[dev_from:dev_to], r2["zeitrahmen"])
    sc, sb = signals(bars, r2["zeitrahmen"], r2["trend"])
    atr = atr_rma(bars)
    spread = pd.Series(cost["spread_usd"], index=bars.index)
    long_ok, short_ok = trend_side(bars, r2["trend"])
    base = dict(eurusd=cost["eurusd"], conflict=acc["conflict"], swap_pct_year=cost["swap_pct_jahr"],
                day_loss_pct=acc["tag_pct"], week_loss_pct=acc["woche_pct"], kill_dd_pct=acc["not_aus_pct"],
                lot_step=r2["groesse"]["schritt_oz"])

    def run(window, sides, stop_usd, stop_atr, risk, start=250.0, deposits=None):
        a, b = window
        sl = slice(bars.index.searchsorted(pd.Timestamp(a)), bars.index.searchsorted(pd.Timestamp(b), side="right"))
        return run_risk(bars.iloc[sl], spread.iloc[sl], sc.iloc[sl], sb.iloc[sl], start_eur=start, stop_usd=stop_usd,
                        stop_atr=stop_atr, atr=atr[sl], risk_pct=risk, sides=tuple(sides), deposits=deposits, **base)

    rng = np.random.default_rng(r2["zufall"]["seed"])
    risk = r2["groesse"]["risiko_pct"]
    th = r2["schwellen"]
    gold_pct = buy_and_hold_pct(bars)
    results, curves = [], {}
    for v in r2["varianten"]:
        row = {"name": v["name"], "seiten": v["seiten"]}
        k = None
        if v.get("stop_atr") == "auswahl":
            sel = {}
            for cand in r2["stop_atr_auswahl"]:
                tr_sel = run(r2["auswahl_fenster"], v["seiten"], None, cand, risk)[0]
                sel[str(cand)] = {"trades": len(tr_sel), "pf_r": pf(r_with_swap(tr_sel, cost["swap_pct_jahr"]))}
            k = max(r2["stop_atr_auswahl"], key=lambda x: sel[str(x)]["pf_r"] or 0)
            row["auswahl"] = sel
            row["stop_atr"] = k
        stop_usd = v.get("stop_usd")
        tr, curve, skipped, swap_paid, _ = run((dev_from, dev_to), v["seiten"], stop_usd, k, risk)
        r = r_with_swap(tr, cost["swap_pct_jahr"])
        test = tr[pd.to_datetime(tr["entry_time"]) >= pd.Timestamp(r2["test_fenster"][0])]
        twins = np.array([twin_r(bars, tr, long_ok, short_ok, atr, rng, cost["spread_usd"], cost["swap_pct_jahr"],
                                 stop_usd, k) for _ in range(r2["zufall"]["laeufe"])])
        years = {}
        for y in sorted(set(pd.to_datetime(tr["entry_time"]).dt.year)):
            ry = r[pd.to_datetime(tr["entry_time"]).dt.year.to_numpy() == y]
            years[int(y)] = {"trades": int(len(ry)), "win_pct": round(100 * float((ry > 0).mean()), 1),
                             "sum_r": round(float(ry.sum()), 1), "pf_r": pf(ry)}
        dd_high = round(100 * float((1 - curve / curve.cummax()).max()), 1)
        row.update({
            "trades": int(len(tr)), "win_pct": round(100 * float((r > 0).mean()), 1), "pf_r": pf(r),
            "sum_r": round(float(r.sum()), 1), "mean_r": round(float(r.mean()), 3),
            "end_eur": round(float(curve.iloc[-1]), 2), "return_pct": round(100 * (float(curve.iloc[-1]) / 250 - 1), 1),
            "gold_pct": gold_pct, "dd_high_pct": dd_high, "swap_eur": round(swap_paid, 2), "skipped": skipped,
            "test_trades": int(len(test)), "test_pf_r": pf(r_with_swap(test, cost["swap_pct_jahr"])),
            "twins_median_r": round(float(np.median(twins)), 1),
            "twins_as_good_pct": round(100 * float((twins >= r.sum()).mean()), 1),
            "by_side_r": {s: round(float(r[(tr["side"] == s).to_numpy()].sum()), 1) for s in ("long", "short")},
            "stop_usd_median": round(float(tr["stop_usd"].median()), 2), "years": years,
        })
        misses = []
        if row["trades"] < th["min_trades"]:
            misses.append(f"nur {row['trades']} Trades")
        if (row["pf_r"] or 0) < th["min_gewinnfaktor_r"]:
            misses.append(f"Gewinnfaktor {row['pf_r']} unter {th['min_gewinnfaktor_r']}")
        if row["twins_as_good_pct"] > th["max_zufall_gleich_gut_pct"]:
            misses.append(f"{row['twins_as_good_pct']} % der Zwillinge so gut")
        if th["besser_als_buy_and_hold"] and row["return_pct"] <= gold_pct:
            misses.append(f"Rendite {row['return_pct']} % nicht über Gold {gold_pct} %")
        if dd_high > th["max_drawdown_hoch_pct"]:
            misses.append(f"Rückgang {dd_high} % vom Hoch")
        if (row["test_pf_r"] or 0) <= th["test_fenster_gewinnfaktor_r_ueber"]:
            misses.append(f"Walk-Forward 2025: Gewinnfaktor {row['test_pf_r']}")
        row["verfehlt"] = misses
        # Bericht: 1 % Risiko und kleines Konto
        for rp in r2["risiko_bericht_pct"]:
            tr1, c1, *_ = run((dev_from, dev_to), v["seiten"], stop_usd, k, rp)
            row[f"risk_{rp}"] = {"end_eur": round(float(c1.iloc[-1]), 2),
                                 "dd_high_pct": round(100 * float((1 - c1 / c1.cummax()).max()), 1)}
        kk = r2["kleines_konto"]
        deps = every_n_months(dev_from, dev_to, kk["alle_monate"], kk["einzahlung_eur"])
        small = {}
        for rp in [risk] + r2["risiko_bericht_pct"]:
            trs, cs, sks, _, paid = run((dev_from, dev_to), v["seiten"], stop_usd, k, rp, kk["start_eur"], deps)
            mc = monte_carlo(r, len(tr), rp, kk["start_eur"], kk["einzahlung_eur"], len(deps), acc["not_aus_pct"],
                             kk["monte_carlo"]["laeufe"], kk["monte_carlo"]["seed"])
            small[str(rp)] = {"end_eur": round(float(cs.iloc[-1]), 2), "paid_eur": round(paid, 2),
                              "lowest_eur": round(float(cs.min()), 2), "too_small": sks["too_small"],
                              "blocked": sks["limits"], "trades": int(len(trs)),
                              "dd_high_pct": round(100 * float((1 - cs / cs.cummax()).max()), 1),
                              "min_oz": float(trs["oz"].min()) if len(trs) else None, "monte_carlo": mc}
            curves[f"{v['name']}|{rp}"] = daily(cs)
        row["kleines_konto"] = small
        curves[f"{v['name']}|250"] = daily(curve)
        results.append(row)
        print("  fertig", v["name"], "k =", k, "verfehlt:", misses or "nichts", flush=True)

    passed = [r["name"] for r in results if not r["verfehlt"]]
    journal_add(f"Runde 2 gerechnet, {len(results)} Varianten, bestanden: " + (", ".join(passed) or "keine"))
    sealed = open_sealed(m1, cfg, vorab_text, [r for r in results if not r["verfehlt"]]) if "--open-sealed" in argv else None
    days = sorted(set().union(*[set(c.index) for c in curves.values()]))
    payload = {"made": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
               "vorab_sha256": sha256_text(vorab_text), "results": results, "sealed": sealed,
               "days": [d.strftime("%Y-%m-%d") for d in days],
               "curves": {k: [round(float(x), 2) for x in c.reindex(days).ffill().bfill()] for k, c in curves.items()}}
    (out / "runde2.json").write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding="utf-8")
    for r in results:
        print(json.dumps({k: r[k] for k in r if k not in ("years", "kleines_konto")}, ensure_ascii=False, default=str))
        print("   Jahre", r["years"])
        print("   kleines Konto", json.dumps(r["kleines_konto"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
