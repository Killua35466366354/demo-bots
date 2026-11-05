"""Trade-Führung von Gold-Bot 2.0 und ein Konto-Lauf, der sie Kerze für Kerze abspielt.

Eine Position gleichzeitig, Füllung zur Eröffnung der nächsten Kerze, Größe nach Risiko (wie
gold/backtest/sizing.py::run_risk). Neu gegenüber run_risk ist, wie ein Trade endet. In dieser Reihenfolge:

In der Kerze (Orders beim Broker, gelten sofort ab der Füllung):
  1. Stop: fester Abstand in Dollar oder Vielfaches der ATR(14) der Signalkerze. Füllung zum Stop, bei einer Lücke
     zum schlechteren Eröffnungskurs.
  2. Ziel: Limit-Order Vielfaches der ATR vom Einstieg, netto nach Spread. Bei einer Lücke über das Ziel zum
     besseren Eröffnungskurs.
  Liegen Stop und Ziel in derselben Stunde, ist die Reihenfolge unbekannt: dann zählt der Stop (vorsichtig).

Auf dem Schluss (Ausführung zur nächsten Eröffnung, wie der stündliche Bot):
  3. Termin: die letzte Füllung vor einem wichtigen US-Termin (News-Check)
  4. Zeitgrenze: nach max_bars Stundenkerzen
  5. Eigenes Ausstiegssignal der Strategie (Stochastik), wahlweise immer oder nur im Plus
  6. Markt-Richtung dreht gegen die Position
  7. Bestätigungs-Stop: im Minus und mindestens min_warn von 3 Warnungen
     - Dip-Tief gebrochen: Schluss unter dem tiefsten Tief der Signalkerze und der 4 davor (Short: über dem Hoch)
     - Schluss auf der falschen Seite der EMA 200 (60 min), der Linie des Trendfilters
     - Markt-Richtung nicht mehr für die Seite

R = Ergebnis geteilt durch das Risiko beim Einstieg (Stop-Abstand mal Unzen). Ohne Stop dient size_basis_atr als
Maßstab, damit sich Varianten vergleichen lassen.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

STRUCT_BARS = 5


@dataclass(frozen=True)
class Fuehrung:
    stop_usd: float | None = None          # fester Stop in Dollar (Bot heute: 5,60)
    stop_atr: float | None = None          # oder Stop x ATR der Signalkerze
    tp_atr: float | None = None            # Ziel x ATR
    max_bars: int | None = None            # Zeitgrenze in Stundenkerzen
    exit_signal: str = "immer"             # "immer" oder "nur_im_plus"
    confluence: bool = False               # Bestätigungs-Stop
    min_warn: int = 2
    dir_exit: bool = False
    news_exit: bool = False
    size_basis_atr: float | None = None    # Maßstab für Größe und R, wenn es keinen Stop gibt

    def __post_init__(self):
        if self.exit_signal not in ("immer", "nur_im_plus"):
            raise ValueError(f"exit_signal muss immer oder nur_im_plus sein, nicht {self.exit_signal}")


@dataclass
class Markt:
    """Alles, was die Führung über den Markt wissen muss, als Arrays je Stundenkerze (Bid-Kurse)."""
    index: pd.DatetimeIndex
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    sp: np.ndarray
    atr: np.ndarray
    long_exit: np.ndarray
    short_exit: np.ndarray
    richtung: np.ndarray
    ema: np.ndarray
    flat_before: np.ndarray
    struct_lo: np.ndarray
    struct_hi: np.ndarray

    @classmethod
    def build(cls, bars: pd.DataFrame, spread: pd.Series | float, atr, sig_long: pd.DataFrame,
              sig_short: pd.DataFrame, richtung=None, ema=None, flat_before=None) -> "Markt":
        n = len(bars)
        sp = (spread.reindex(bars.index).ffill().to_numpy(float) if isinstance(spread, pd.Series)
              else np.full(n, float(spread)))
        lo = bars["low"].rolling(STRUCT_BARS, min_periods=1).min().to_numpy(float)
        hi = bars["high"].rolling(STRUCT_BARS, min_periods=1).max().to_numpy(float)
        return cls(bars.index, *(bars[k].to_numpy(float) for k in ("open", "high", "low", "close")), sp,
                   np.asarray(atr, float), sig_long["exit"].to_numpy(bool), sig_short["exit"].to_numpy(bool),
                   np.zeros(n, int) if richtung is None else np.asarray(richtung, int),
                   np.full(n, np.nan) if ema is None else np.asarray(ema, float),
                   np.zeros(n, bool) if flat_before is None else np.asarray(flat_before, bool), lo, hi)

    def slice(self, a: int, b: int) -> "Markt":
        return Markt(self.index[a:b], *(getattr(self, k)[a:b] for k in (
            "o", "h", "l", "c", "sp", "atr", "long_exit", "short_exit", "richtung", "ema", "flat_before",
            "struct_lo", "struct_hi")))


def risk_distance(f: Fuehrung, atr_sig: float) -> float | None:
    if f.stop_usd:
        return f.stop_usd
    if f.stop_atr:
        return f.stop_atr * atr_sig
    if f.size_basis_atr:
        return f.size_basis_atr * atr_sig
    return None


def manage(m: Markt, side: int, t_sig: int, f: Fuehrung) -> dict | None:
    """Ein Trade vom Signal auf Kerze t_sig bis zum Ausstieg. None, wenn es keine Kerze zum Füllen gibt."""
    n = len(m.c)
    t = t_sig + 1
    if t >= n:
        return None
    o, h, l, c, sp = m.o, m.h, m.l, m.c, m.sp
    epx = o[t] + sp[t] if side > 0 else o[t]
    a = float(m.atr[t_sig])
    dist = f.stop_usd or (f.stop_atr * a if f.stop_atr else None)
    stop = None if not dist else epx - side * dist
    tp = None if not f.tp_atr else epx + side * f.tp_atr * a
    s_lo, s_hi = m.struct_lo[t_sig], m.struct_hi[t_sig]
    own_exit = m.long_exit if side > 0 else m.short_exit

    def done(u, px, why):
        return {"side": side, "t_sig": t_sig, "t_in": t, "t_out": u, "entry_px": epx, "exit_px": px,
                "reason": why, "risk_dist": risk_distance(f, a)}

    for u in range(t, n):
        if side > 0:
            ob = o[u]
            if stop is not None and ob <= stop:
                return done(u, ob, "stop")
            if tp is not None and ob >= tp:
                return done(u, ob, "ziel")
            if stop is not None and l[u] <= stop:
                return done(u, stop, "stop")
            if tp is not None and h[u] >= tp:
                return done(u, tp, "ziel")
        else:
            ob = o[u] + sp[u]
            if stop is not None and ob >= stop:
                return done(u, ob, "stop")
            if tp is not None and ob <= tp:
                return done(u, ob, "ziel")
            if stop is not None and h[u] + sp[u] >= stop:
                return done(u, stop, "stop")
            if tp is not None and l[u] + sp[u] <= tp:
                return done(u, tp, "ziel")
        if u == n - 1:
            return done(u, c[u] if side > 0 else c[u] + sp[u], "datenende")
        mark = c[u] if side > 0 else c[u] + sp[u]
        in_profit = side * (mark - epx) > 0
        why = None
        if f.news_exit and m.flat_before[u]:
            why = "termin"
        elif f.max_bars and u - t + 1 >= f.max_bars:
            why = "zeit"
        elif own_exit[u] and (f.exit_signal == "immer" or in_profit):
            why = "signal"
        elif f.dir_exit and m.richtung[u] == -side:
            why = "richtung"
        elif f.confluence and not in_profit:
            if side > 0:
                warn = int(c[u] < s_lo) + int(c[u] < m.ema[u]) + int(m.richtung[u] != 1)
            else:
                warn = int(c[u] > s_hi) + int(c[u] > m.ema[u]) + int(m.richtung[u] != -1)
            if warn >= f.min_warn:
                why = "bestaetigung"
        if why:
            return done(u + 1, o[u + 1] if side > 0 else o[u + 1] + sp[u + 1], why)
    return None


def run_v2(m: Markt, long_in: np.ndarray, short_in: np.ndarray, f: Fuehrung, *, start_eur=250.0, eurusd=1.117,
           margin_rate=0.05, size_oz=None, risk_pct=None, lot_step=0.01, swap_pct_year=0.0, day_loss_pct=None,
           week_loss_pct=None, kill_dd_pct=None, deposits=None):
    """Konto-Lauf. long_in/short_in: Einstiegssignale nach allen Filtern (bool je Kerze, auf dem Schluss).
    Rückgabe wie run_risk: Trades, Kontokurve, übersprungene Signale, Übernachtkosten, eingezahlt."""
    idx = m.index
    n = len(idx)
    o, h, l, c, sp = m.o, m.h, m.l, m.c, m.sp
    a_in, b_in = np.asarray(long_in, bool), np.asarray(short_in, bool)
    days, weeks = idx.normalize(), idx.to_period("W")
    dep = sorted((pd.Timestamp(k), float(v)) for k, v in (deposits or {}).items())
    eq = peak = deposited = start_eur
    day_start_eq = week_start_eq = eq
    last_day, last_week = days[0], weeks[0]
    pos, oz, plan, pend = 0, 0.0, None, None
    trades, curve = [], np.empty(n)
    skipped = {"margin": 0, "conflict": 0, "limits": 0, "busy": 0, "too_small": 0}
    swap_paid = 0.0

    def close(t, px, why):
        nonlocal eq, pos, plan
        pnl = pos * (px - plan["entry_px"]) * oz / eurusd
        eq += pnl
        risk_eur = plan["risk_dist"] * oz / eurusd if plan["risk_dist"] else 0.0
        trades.append({"side": "long" if pos > 0 else "short", "entry_time": idx[plan["t_in"]],
                       "entry_px": plan["entry_px"], "exit_time": idx[t], "exit_px": px, "oz": oz,
                       "stop_usd": plan["risk_dist"], "risk_eur": risk_eur, "pnl_eur": pnl,
                       "r": pnl / risk_eur if risk_eur else 0.0, "reason": why, "bars": t - plan["t_in"] + 1})
        pos, plan = 0, None

    for t in range(n):
        while dep and dep[0][0] <= idx[t]:
            amount = dep.pop(0)[1]
            eq += amount
            peak += amount
            day_start_eq += amount
            week_start_eq += amount
            deposited += amount
        if days[t] != last_day:
            if pos != 0 and swap_pct_year:
                fee = c[t - 1] * oz * swap_pct_year / 100 / 365 / eurusd
                eq -= fee
                swap_paid += fee
            day_start_eq, last_day = eq, days[t]
        if weeks[t] != last_week:
            week_start_eq, last_week = eq, weeks[t]

        if pend is not None:                        # Füllung zur Eröffnung dieser Kerze
            plan, oz, pos = pend
            pend = None
        if pos != 0 and plan["t_out"] == t:
            close(t, plan["exit_px"], plan["reason"])
        if pos != 0:
            worst = l[t] if pos > 0 else h[t] + sp[t]
            margin = plan["entry_px"] * oz * margin_rate / eurusd
            if eq + pos * (worst - plan["entry_px"]) * oz / eurusd < 0.5 * margin:
                close(t, worst, "margin call")

        mark = c[t] if pos >= 0 else c[t] + sp[t]
        curve[t] = eq + (pos * (mark - plan["entry_px"]) * oz / eurusd if pos else 0.0)
        peak = max(peak, curve[t])

        blocked = ((day_loss_pct and eq < day_start_eq * (1 - day_loss_pct / 100)) or
                   (week_loss_pct and eq < week_start_eq * (1 - week_loss_pct / 100)) or
                   (kill_dd_pct and curve[t] < peak * (1 - kill_dd_pct / 100)))
        if pos != 0:
            if a_in[t] or b_in[t]:
                skipped["busy"] += 1
            continue
        if not (a_in[t] or b_in[t]):
            continue
        if a_in[t] and b_in[t]:
            skipped["conflict"] += 1
            continue
        if blocked:
            skipped["limits"] += 1
            continue
        side = 1 if a_in[t] else -1
        p = manage(m, side, t, f)
        if p is None:
            continue
        if risk_pct is None:
            units = size_oz
            if c[t] * units * margin_rate / eurusd > eq:
                skipped["margin"] += 1
                continue
        else:
            d = p["risk_dist"]
            units = 0.0
            if d:
                units = math.floor(eq * risk_pct / 100 * eurusd / d / lot_step + 1e-9) * lot_step
                while units >= lot_step and units * c[t] * margin_rate / eurusd > eq:
                    units -= lot_step
            if units < lot_step:
                skipped["too_small"] += 1
                continue
            units = round(units, 6)
        pend = (p, units, side)
    if pos != 0:
        close(n - 1, c[-1] if pos > 0 else c[-1] + sp[-1], "datenende")
    return pd.DataFrame(trades), pd.Series(curve, index=idx), skipped, swap_paid, deposited


def twin_r(m: Markt, trades: pd.DataFrame, pool_long: np.ndarray, pool_short: np.ndarray, f: Fuehrung,
           rng: np.random.Generator, swap_pct: float) -> np.ndarray:
    """Ein Lauf gematchter Zufalls-Zwillinge: je echtem Trade einer mit derselben Seite, das Signal auf einer
    zufälligen Kerze, die Trendfilter und Filter erlauben, und genau derselben Führung. R je Zwilling."""
    n = len(m.c)
    pools = {1: np.flatnonzero(np.asarray(pool_long, bool)[:n - 2]),
             -1: np.flatnonzero(np.asarray(pool_short, bool)[:n - 2])}
    days = m.index.normalize()
    out = []
    for side_name in trades["side"]:
        side = 1 if side_name == "long" else -1
        pool = pools[side]
        if not len(pool):
            continue
        p = manage(m, side, int(rng.choice(pool)), f)
        if p is None or not p["risk_dist"]:
            continue
        nights = int((days[p["t_out"]] - days[p["t_in"]]).days)
        swap = m.c[p["t_in"]] * swap_pct / 100 / 365 * nights
        out.append((side * (p["exit_px"] - p["entry_px"]) - swap) / p["risk_dist"])
    return np.array(out)
