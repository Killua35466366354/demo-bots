"""Runde 3 des Gold-Backtest-Protokolls: Gold-Bot 2.0 und der Bestätigungs-Stop (VORAB.yaml, Abschnitt runde_3).

Usage (from the repo root):
    python -m gold.backtest.runde3 --festlegen "Grund"     # VORAB-Prüfsumme ins Journal, BEVOR gerechnet wird
    python -m gold.backtest.runde3 <daten> <out_dir>        # rechnen; <daten> = HistData-Ordner oder chart.json

<daten> darf der Ordner mit den HistData-Minutendateien sein oder die Datei chart.json aus dem Chart-Review
(gold/backtest/chart_review.py, Feld candles). Beide geben dieselben Stundenkerzen: Mit chart.json kommen die
275 Trades des Bots von heute exakt wieder heraus.

Zwei Kandidaten werden an den Schwellen gemessen, alles andere ist Vergleich:
1. Bot heute + Bestätigungs-Stop: dieselben Ein- und Ausstiege wie heute, aber statt 5,60 $ ein harter Stop von
   3 x ATR und ein früher Ausstieg im Minus, wenn 2 von 3 Warnungen zutreffen (Kirons Stop-Frage).
2. Gold-Bot 2.0: Signale nur mit Markt-Richtung, Pause rund um US-Termine und nach Kursschocks, Ziel und
   Zeitgrenze, Ausstiegssignal nur im Plus, Stop aus der Auswahl (nur 2023-24 angesehen).
Alle Messgrößen, die nicht von der Kontogröße abhängen, laufen in R; Rendite und Rückgang mit 250 € und 2 % Risiko.
"""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timezone
from itertools import product

import numpy as np
import pandas as pd
import yaml

from gold.backtest.pine_port import htf_ema
from gold.backtest.protocol import VORAB, buy_and_hold_pct, journal_add, journal_lines, last_value, session_bars, sha256_text, signals
from gold.backtest.runde2 import pf, r_with_swap
from gold.backtest.sizing import atr_rma, every_n_months
from gold.v2 import news, richtung, termine
from gold.v2.fuehrung import Fuehrung, Markt, run_v2, twin_r

FROM, TO = "2023-01-01", "2026-10-23 23:59"
DEV = ("2023-01-01", "2025-12-31 23:59")
ROOT = pathlib.Path(__file__).resolve().parents[2]


def load_hourly(path: str) -> pd.DataFrame:
    p = pathlib.Path(path)
    if p.is_dir():
        from gold.backtest.run_backtest import load
        return session_bars(load(str(p)).loc[FROM:TO], "60min")
    c = np.array(json.loads(p.read_text(encoding="utf-8"))["candles"], float)
    bars = pd.DataFrame(c[:, 1:5], columns=["open", "high", "low", "close"], index=pd.to_datetime(c[:, 0], unit="s"))
    return bars.loc[FROM:TO]


def prepare(bars: pd.DataFrame, cfg: dict, spread: pd.Series | None = None) -> dict:
    """Signale, Filter und Markt-Arrays. spread: echte Spreads je Kerze (Bot), sonst der feste aus VORAB."""
    r3, cost = cfg["runde_3"], cfg["kosten"]
    sc, sb = signals(bars, r3["zeitrahmen"], r3["zeitrahmen"])
    atr = atr_rma(bars)
    rich = richtung.direction(bars, r3["richtung"]["tag_sma"], r3["richtung"]["vier_stunden_ema"])
    ema = htf_ema(bars).to_numpy(float)
    nw = r3["news"]
    events = termine.load(ROOT / nw["termine"])["utc"]
    pause = news.entry_pause(bars.index, events, nw["pause_vorher_h"], nw["pause_nachher_h"]).to_numpy()
    flat = news.flat_before(bars.index, events, nw["flach_vorher_min"]).to_numpy()
    shock = news.shock_pause(bars, atr, nw["schock_atr"], nw["schock_pause_kerzen"]).to_numpy()
    if spread is None:
        spread = pd.Series(cost["spread_usd"], index=bars.index)
    m = Markt.build(bars, spread, atr, sc, sb, rich.to_numpy(), ema, flat)
    raw_l, raw_s = sc["entry"].to_numpy(bool), sb["entry"].to_numpy(bool)
    r = rich.to_numpy()
    ok = ~pause & ~shock
    trend_l, trend_s = bars["close"].to_numpy() > ema, bars["close"].to_numpy() < ema
    return {"bars": bars, "m": m, "atr": atr, "richtung": r, "pause": pause, "flat": flat, "shock": shock, "events": events,
            "entries": {"roh": (raw_l, raw_s), "richtung": (raw_l & (r == 1), raw_s & (r == -1)),
                        "voll": (raw_l & (r == 1) & ok, raw_s & (r == -1) & ok)},
            "pools": {"roh": (trend_l, trend_s), "voll": (trend_l & (r == 1) & ok, trend_s & (r == -1) & ok)}}


def stop_parts(kind: str, r3: dict) -> dict:
    if kind == "bestaetigung":
        b = r3["bestaetigungs_stop"]
        return {"stop_atr": b["hart_atr"], "confluence": True, "min_warn": b["min_warnungen"]}
    if kind.startswith("atr "):
        return {"stop_atr": float(kind.split()[1])}
    raise ValueError(f"unbekannte Stop-Art {kind}")


def v2_fuehrung(r3: dict, tp: float, bars_max: int, stop: str, dir_exit: bool, news_exit: bool) -> Fuehrung:
    return Fuehrung(tp_atr=tp, max_bars=bars_max, exit_signal=r3["fuehrung_auswahl"]["ausstieg_signal"],
                    dir_exit=dir_exit, news_exit=news_exit, **stop_parts(stop, r3))


def span(index: pd.DatetimeIndex, window) -> slice:
    a, b = window
    return slice(int(index.searchsorted(pd.Timestamp(a))), int(index.searchsorted(pd.Timestamp(b), side="right")))


def years_of(tr: pd.DataFrame, r: np.ndarray) -> dict:
    ys = pd.to_datetime(tr["entry_time"]).dt.year.to_numpy() if len(tr) else np.array([])
    out = {}
    for y in sorted(set(ys.tolist())):
        ry = r[ys == y]
        out[str(int(y))] = {"trades": int(len(ry)), "win_pct": round(100 * float((ry > 0).mean()), 1),
                            "sum_r": round(float(ry.sum()), 1), "pf_r": pf(ry)}
    return out


def stats(tr: pd.DataFrame, curve: pd.Series, start: float, swap: float) -> dict:
    r = r_with_swap(tr, swap) if len(tr) else np.array([])
    streak = longest = 0
    for x in r:
        streak = streak + 1 if x <= 0 else 0
        longest = max(longest, streak)
    return {"trades": int(len(tr)), "win_pct": round(100 * float((r > 0).mean()), 1) if len(r) else None,
            "pf_r": pf(r), "sum_r": round(float(r.sum()), 1), "mean_r": round(float(r.mean()), 3) if len(r) else None,
            "avg_win_r": round(float(r[r > 0].mean()), 2) if (r > 0).any() else None,
            "avg_loss_r": round(float(r[r <= 0].mean()), 2) if (r <= 0).any() else None,
            "worst_r": round(float(r.min()), 2) if len(r) else None, "longest_losing_streak": longest,
            "end_eur": round(float(curve.iloc[-1]), 2), "return_pct": round(100 * (float(curve.iloc[-1]) / start - 1), 1),
            "dd_high_pct": round(100 * float((1 - curve / curve.cummax()).max()), 1),
            "avg_hours": round(float(tr["bars"].mean()), 1) if len(tr) else None,
            "exits": tr["reason"].value_counts().to_dict() if len(tr) else {},
            "by_side_r": {s: round(float(r[(tr["side"] == s).to_numpy()].sum()), 1) for s in ("long", "short")} if len(tr) else {},
            "years": years_of(tr, r)}


def main(argv: list[str]) -> int:
    vorab_text = VORAB.read_text(encoding="utf-8")
    if argv[:1] == ["--festlegen"]:
        journal_add(f"VORAB geändert, Grund: {argv[1]}. VORAB sha256 {sha256_text(vorab_text)}")
        print("Im Journal eingetragen:", sha256_text(vorab_text))
        return 0
    if last_value(journal_lines(), "VORAB sha256 ") != sha256_text(vorab_text):
        raise SystemExit("VORAB.yaml steht so nicht im Journal. Erst --festlegen \"Grund\" und committen, dann rechnen.")
    data, out_dir = argv[:2]
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(vorab_text)
    r3, cost, acc = cfg["runde_3"], cfg["kosten"], cfg["konto"]
    swap = cost["swap_pct_jahr"]
    bars = load_hourly(data)
    P = prepare(bars, cfg)
    m, idx = P["m"], bars.index
    acct = dict(eurusd=cost["eurusd"], swap_pct_year=swap, day_loss_pct=acc["tag_pct"], week_loss_pct=acc["woche_pct"],
                kill_dd_pct=acc["not_aus_pct"], lot_step=r3["groesse"]["schritt_oz"])
    risk = r3["groesse"]["risiko_pct"]

    def run(window, entries: str, f: Fuehrung, start=250.0, risk_pct=risk, deposits=None, **extra):
        s = span(idx, window)
        el, es = P["entries"][entries] if isinstance(entries, str) else entries
        kw = dict(acct, **extra)
        return run_v2(m.slice(s.start, s.stop), el[s], es[s], f, start_eur=start, risk_pct=risk_pct,
                      deposits=deposits, **kw)

    # 1) Auswahl der Trade-Führung für 2.0, nur mit 2023-24
    fa = r3["fuehrung_auswahl"]
    auswahl = []
    for tp, kmax, stop in product(fa["ziel_atr"], fa["max_kerzen"], fa["stop"]):
        tr = run(r3["auswahl_fenster"], "voll", v2_fuehrung(r3, tp, kmax, stop, True, True))[0]
        rr = r_with_swap(tr, swap) if len(tr) else np.array([])
        auswahl.append({"ziel_atr": tp, "max_kerzen": kmax, "stop": stop, "trades": int(len(tr)), "pf_r": pf(rr),
                        "win_pct": round(100 * float((rr > 0).mean()), 1) if len(rr) else None,
                        "sum_r": round(float(rr.sum()), 1)})
        print("  Auswahl", auswahl[-1], flush=True)
    best = max(auswahl, key=lambda x: x["pf_r"] or 0)          # bei Gleichstand die erste in VORAB-Reihenfolge
    sel = (best["ziel_atr"], best["max_kerzen"], best["stop"])
    print("  gewählt:", sel, flush=True)

    rows = [
        {"key": "heute", "name": "Bot heute: C+B, Stop 5,60 $", "entries": "roh", "f": Fuehrung(stop_usd=5.6)},
        {"key": "runde2", "name": "Runde 2: C+B, Stop 1 × ATR", "entries": "roh", "f": Fuehrung(stop_atr=1.0)},
        {"key": "kand_stop", "name": "Kandidat 1: Bot heute + Bestätigungs-Stop", "entries": "roh", "kandidat": True,
         "pool": "roh", "f": Fuehrung(**stop_parts("bestaetigung", r3))},
        {"key": "stufe1", "name": "2.0 Stufe 1: nur Trade-Führung", "entries": "roh", "f": v2_fuehrung(r3, *sel, False, False)},
        {"key": "stufe2", "name": "2.0 Stufe 2: + Markt-Richtung", "entries": "richtung", "f": v2_fuehrung(r3, *sel, True, False)},
        {"key": "kand_v2", "name": "Kandidat 2: Gold-Bot 2.0 (+ News-Check)", "entries": "voll", "kandidat": True,
         "pool": "voll", "f": v2_fuehrung(r3, *sel, True, True)},
    ]
    th = r3["schwellen"]
    gold_pct = buy_and_hold_pct(bars.iloc[span(idx, DEV)])
    kk = r3["kleines_konto"]
    deps = every_n_months(DEV[0], DEV[1], kk["alle_monate"], kk["einzahlung_eur"])
    rng = np.random.default_rng(r3["zufall"]["seed"])
    results = []
    for row in rows:
        f = row["f"]
        tr, curve, skipped, swap_paid, _ = run(DEV, row["entries"], f)
        res = {"key": row["key"], "name": row["name"], "kandidat": bool(row.get("kandidat")),
               **stats(tr, curve, 250.0, swap), "skipped": skipped, "swap_eur": round(swap_paid, 2), "gold_pct": gold_pct}
        r = r_with_swap(tr, swap) if len(tr) else np.array([])
        test = tr[pd.to_datetime(tr["entry_time"]) >= pd.Timestamp(r3["test_fenster"][0])] if len(tr) else tr
        res["test_pf_r"] = pf(r_with_swap(test, swap)) if len(test) else None
        tr26, c26, *_ = run(r3["info_fenster"], row["entries"], f)
        res["info_2026"] = {k: v for k, v in stats(tr26, c26, 250.0, swap).items() if k not in ("years",)}
        res["kleines_konto"] = {}
        for rp in kk["risiko_pct"]:
            _, cs, sks, _, paid = run(DEV, row["entries"], f, start=kk["start_eur"], risk_pct=rp, deposits=deps)
            res["kleines_konto"][str(rp)] = {"end_eur": round(float(cs.iloc[-1]), 2), "paid_eur": round(paid, 2),
                                            "dd_high_pct": round(100 * float((1 - cs / cs.cummax()).max()), 1),
                                            "too_small": sks["too_small"]}
        if row.get("kandidat"):
            s = span(idx, DEV)
            pl, ps = P["pools"][row["pool"]]
            ms = m.slice(s.start, s.stop)
            twins = [twin_r(ms, tr, pl[s], ps[s], f, rng, swap) for _ in range(r3["zufall"]["laeufe"])]
            sums = np.array([t.sum() for t in twins])
            res["twins"] = {"median_sum_r": round(float(np.median(sums)), 1),
                            "as_good_pct": round(100 * float((sums >= r.sum()).mean()), 1),
                            "win_pct": round(100 * float(np.mean([(t > 0).mean() for t in twins if len(t)])), 1),
                            "pf_r_median": round(float(np.median([pf(t) or 0 for t in twins])), 2)}
            misses = []
            if res["trades"] < th["min_trades"]:
                misses.append(f"nur {res['trades']} Trades")
            if (res["pf_r"] or 0) < th["min_gewinnfaktor_r"]:
                misses.append(f"Gewinnfaktor {res['pf_r']} unter {th['min_gewinnfaktor_r']}")
            if res["twins"]["as_good_pct"] > th["max_zufall_gleich_gut_pct"]:
                misses.append(f"{res['twins']['as_good_pct']} % der Zwillinge so gut")
            if th["besser_als_buy_and_hold"] and res["return_pct"] <= gold_pct:
                misses.append(f"Rendite {res['return_pct']} % nicht über Gold {gold_pct} %")
            if res["dd_high_pct"] > th["max_drawdown_hoch_pct"]:
                misses.append(f"Rückgang {res['dd_high_pct']} % vom Hoch")
            if (res["test_pf_r"] or 0) <= th["test_fenster_gewinnfaktor_r_ueber"]:
                misses.append(f"Prüfjahr 2025: Gewinnfaktor {res['test_pf_r']}")
            res["verfehlt"] = misses
        results.append(res)
        print("  fertig", row["name"], {k: res[k] for k in ("trades", "win_pct", "pf_r", "sum_r", "end_eur", "dd_high_pct", "test_pf_r")},
              res.get("twins"), res.get("verfehlt"), flush=True)

    # 2) Vergleich: Halten bis Plus ohne Stop (Ziel und Zeitgrenze von 2.0), in Dollar je Unze
    f_ns = Fuehrung(tp_atr=sel[0], max_bars=sel[1], exit_signal=fa["ausstieg_signal"], dir_exit=True, news_exit=True,
                    size_basis_atr=r3["bestaetigungs_stop"]["hart_atr"])
    tr_ns, *_ = run(DEV, "voll", f_ns, start=1e6, risk_pct=None, size_oz=1.0, day_loss_pct=None,
                    week_loss_pct=None, kill_dd_pct=None)
    usd = (tr_ns["pnl_eur"] * cost["eurusd"]).to_numpy() if len(tr_ns) else np.array([])
    tr_vs, *_ = run(DEV, "voll", v2_fuehrung(r3, *sel, True, True), start=1e6, risk_pct=None, size_oz=1.0,
                    day_loss_pct=None, week_loss_pct=None, kill_dd_pct=None)
    usd_vs = (tr_vs["pnl_eur"] * cost["eurusd"]).to_numpy() if len(tr_vs) else np.array([])
    ohne_stop = {"trades": int(len(usd)), "win_pct": round(100 * float((usd > 0).mean()), 1) if len(usd) else None,
                 "sum_usd_oz": round(float(usd.sum()), 1), "worst_usd_oz": round(float(usd.min()), 1) if len(usd) else None,
                 "pf_usd": pf(usd), "mit_stop": {"trades": int(len(usd_vs)), "sum_usd_oz": round(float(usd_vs.sum()), 1),
                                                 "worst_usd_oz": round(float(usd_vs.min()), 1) if len(usd_vs) else None,
                                                 "win_pct": round(100 * float((usd_vs > 0).mean()), 1) if len(usd_vs) else None,
                                                 "pf_usd": pf(usd_vs)}}
    print("  ohne Stop", ohne_stop, flush=True)

    # 3) Bringt jeder Baustein mehr als Weglassen per Zufall? (nur Bericht)
    wz = r3["weglassen_zufall"]
    rng2 = np.random.default_rng(wz["seed"])
    s = span(idx, DEV)
    weglassen = {}
    for key, frm, to, f in (("richtung", "roh", "richtung", rows[4]["f"]), ("news", "richtung", "voll", rows[5]["f"])):
        (fl, fs), (tl, ts) = P["entries"][frm], P["entries"][to]
        keep_l = tl[s].sum() / max(fl[s].sum(), 1)
        keep_s = ts[s].sum() / max(fs[s].sum(), 1)
        real = float(r_with_swap(run(DEV, to, f)[0], swap).sum())
        sums = []
        for _ in range(wz["laeufe"]):
            dl = fl & (rng2.random(len(fl)) < keep_l)
            ds = fs & (rng2.random(len(fs)) < keep_s)
            trw = run(DEV, (dl, ds), f)[0]
            sums.append(float(r_with_swap(trw, swap).sum()) if len(trw) else 0.0)
        sums = np.array(sums)
        weglassen[key] = {"real_sum_r": round(real, 1), "random_median_sum_r": round(float(np.median(sums)), 1),
                          "as_good_pct": round(100 * float((sums >= real).mean()), 1),
                          "kept_long": int(tl[s].sum()), "all_long": int(fl[s].sum()),
                          "kept_short": int(ts[s].sum()), "all_short": int(fs[s].sum())}
        print("  weglassen", key, weglassen[key], flush=True)

    cands = [x for x in results if x["kandidat"]]
    passed = [x["name"] for x in cands if not x["verfehlt"]]
    journal_add(f"Runde 3 gerechnet, Auswahl 2.0: Ziel {sel[0]} ATR, {sel[1]} Kerzen, Stop {sel[2]}; "
                f"bestanden: " + (", ".join(passed) or "keine"))
    counts = {"termine": int(len(termine.load(ROOT / r3["news"]["termine"]))),
              "pause_kerzen_dev": int(P["pause"][s].sum()), "schock_kerzen_dev": int(P["shock"][s].sum()),
              "richtung_dev": {str(k): int((P["richtung"][s] == k).sum()) for k in (-1, 0, 1)}}
    payload = {"made": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "vorab_sha256": sha256_text(vorab_text),
               "data_from": str(idx[0]), "data_to": str(idx[-1]), "auswahl": auswahl, "gewaehlt": sel,
               "results": results, "ohne_stop": ohne_stop, "weglassen": weglassen, "zaehler": counts, "gold_pct": gold_pct}
    (out / "runde3.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"bestanden": passed, "gewaehlt": sel, "zaehler": counts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
