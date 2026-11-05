"""Kleines Konto: Positionsgröße nach Risiko, Stop nach Schwankung (ATR), Einzahlungen.

run_risk macht dasselbe wie engine.run_live (eine Position, Füllung zur nächsten Eröffnung, Notfall-Stop beim
Broker, Tages-, Wochen- und Not-Aus-Limit, Übernachtkosten), mit drei Erweiterungen:

1. Stop: fester Abstand in Dollar (stop_usd) oder ein Vielfaches der ATR(14) der Signalkerze (stop_atr). Das
   entspricht der Eingabe "Stop loss: ATR" in Kirons v6-Skripten; der Bot rechnet die ATR auf der letzten fertigen
   Kerze, weil er die Stop-Order gleich mit dem Einstieg schickt.
2. Größe: feste Unzen (size_oz) oder risk_pct Prozent des Kontos geteilt durch den Stop-Abstand, abgerundet auf
   lot_step Unzen (Capital.com: 0,01). Passt nicht einmal die kleinste Größe ins Risiko oder in die Margin, wird
   der Einstieg übersprungen.
3. Einzahlungen: {Zeitpunkt: Betrag in €}, gebucht auf der ersten Kerze ab dem Zeitpunkt. Sie heben auch den
   Höchststand und die Tages- und Wochenbasis an, damit sie weder den Not-Aus verdecken noch auslösen.
4. Break-even (be_at_r): Lag der Trade auf einer Kerze be_at_r × Stop-Abstand im Plus, rückt der Stop ab der
   nächsten Kerze auf den Einstiegskurs. Standard aus, nur für Versuche.

Mit size_oz=1, stop_usd fest, sides beide und ohne Einzahlungen kommen genau die Trades von run_live heraus
(tests/test_gold_sizing.py).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def atr_rma(bars: pd.DataFrame, length: int = 14) -> np.ndarray:
    """ta.atr(length) wie in Pine: gleitender RMA-Durchschnitt der True Range."""
    h, l, c = (bars[k].to_numpy(float) for k in ("high", "low", "close"))
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h, pc) - np.minimum(l, pc)
    tr[0] = h[0] - l[0]
    return pd.Series(tr).ewm(alpha=1 / length, adjust=False).mean().to_numpy()


def run_risk(bid, spread, sig_long, sig_short, *, start_eur=250.0, eurusd=1.117, margin_rate=0.05,
             stop_usd=None, stop_atr=None, atr=None, size_oz=None, risk_pct=None, lot_step=0.01,
             sides=("long", "short"), conflict="first", swap_pct_year=0.0, day_loss_pct=None,
             week_loss_pct=None, kill_dd_pct=None, deposits=None, be_at_r=None):
    o, h, l, c = (bid[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    sp = spread.reindex(bid.index).ffill().to_numpy(float)
    a_in, a_out = sig_long["entry"].to_numpy(bool), sig_long["exit"].to_numpy(bool)
    b_in, b_out = sig_short["entry"].to_numpy(bool), sig_short["exit"].to_numpy(bool)
    if "long" not in sides:
        a_in = np.zeros_like(a_in)
    if "short" not in sides:
        b_in = np.zeros_like(b_in)
    if stop_atr is not None and atr is None:
        atr = atr_rma(bid)
    idx = bid.index
    days = idx.normalize()
    weeks = idx.to_period("W")
    dep = sorted((pd.Timestamp(k), float(v)) for k, v in (deposits or {}).items())
    eq = peak = start_eur
    deposited = start_eur
    pos, epx, et, stop, oz, risk_eur, dist = 0, 0.0, None, None, 0.0, 0.0, 0.0
    pend = None
    trades, curve = [], np.empty(len(bid))
    skipped = {"margin": 0, "conflict": 0, "limits": 0, "busy": 0, "addon": 0, "too_small": 0}
    day_start_eq = week_start_eq = eq
    last_day, last_week = days[0], weeks[0]
    swap_paid = 0.0

    def close_at(t, px, why):
        nonlocal eq, pos, stop
        pnl_eur = pos * (px - epx) * oz / eurusd
        eq += pnl_eur
        trades.append({"side": "long" if pos > 0 else "short", "entry_time": et, "entry_px": epx,
                       "exit_time": idx[t], "exit_px": px, "oz": oz, "stop_usd": dist, "risk_eur": risk_eur,
                       "pnl_eur": pnl_eur, "r": pnl_eur / risk_eur if risk_eur else 0.0, "reason": why})
        pos, stop = 0, None

    def size_for(t_sig, entry_ref):
        """Unzen und Stop-Abstand für ein Signal auf Kerze t_sig, oder (0, d) wenn es nicht passt."""
        d = stop_usd if stop_atr is None else stop_atr * float(atr[t_sig])
        if risk_pct is None:
            return (size_oz, d)
        if not d:
            return (0.0, d)
        raw = eq * risk_pct / 100 * eurusd / d
        units = math.floor(raw / lot_step + 1e-9) * lot_step
        while units >= lot_step and units * entry_ref * margin_rate / eurusd > eq:
            units -= lot_step
        return (round(units, 6) if units >= lot_step else 0.0, d)

    for t in range(len(bid)):
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

        if pend is not None:
            if pend[0] in ("close", "reverse") and pos != 0:
                close_at(t, o[t] if pos > 0 else o[t] + sp[t], "signal")
            if pend[0] in ("open", "reverse"):
                side, oz, dist = pend[1], pend[2], pend[3]
                epx = o[t] + sp[t] if side > 0 else o[t]
                pos, et = side, idx[t]
                risk_eur = dist * oz / eurusd if dist else 0.0
                stop = None
                if dist:
                    stop = epx - dist if side > 0 else epx + dist
            pend = None

        if pos > 0 and stop is not None and l[t] <= stop:
            close_at(t, min(o[t], stop), "stop")
        elif pos < 0 and stop is not None and h[t] + sp[t] >= stop:
            close_at(t, max(o[t] + sp[t], stop), "stop")
        if pos != 0:
            worst = l[t] if pos > 0 else h[t] + sp[t]
            margin = epx * oz * margin_rate / eurusd
            if eq + pos * (worst - epx) * oz / eurusd < 0.5 * margin:
                close_at(t, worst, "margin call")
        if pos != 0 and be_at_r and dist and stop is not None:          # gilt ab der nächsten Kerze
            if pos > 0 and h[t] >= epx + be_at_r * dist:
                stop = max(stop, epx)
            elif pos < 0 and l[t] + sp[t] <= epx - be_at_r * dist:
                stop = min(stop, epx)

        mark = c[t] if pos >= 0 else c[t] + sp[t]
        curve[t] = eq + (pos * (mark - epx) * oz / eurusd if pos else 0.0)
        peak = max(peak, curve[t])

        blocked = ((day_loss_pct and eq < day_start_eq * (1 - day_loss_pct / 100)) or
                   (week_loss_pct and eq < week_start_eq * (1 - week_loss_pct / 100)) or
                   (kill_dd_pct and curve[t] < peak * (1 - kill_dd_pct / 100)))
        if pos == 0:
            if a_in[t] and b_in[t]:
                skipped["conflict"] += 1
            elif a_in[t] or b_in[t]:
                want = 1 if a_in[t] else -1
                units, d = size_for(t, c[t])
                if blocked:
                    skipped["limits"] += 1
                elif risk_pct is None and c[t] * units * margin_rate / eurusd > eq:
                    skipped["margin"] += 1
                elif not units:
                    skipped["too_small"] += 1
                else:
                    pend = ("open", want, units, d)
        else:
            own_exit = a_out[t] if pos > 0 else b_out[t]
            same_in = a_in[t] if pos > 0 else b_in[t]
            other_in = b_in[t] if pos > 0 else a_in[t]
            if own_exit:
                pend = ("close",)
            elif other_in and conflict == "reverse" and not blocked:
                units, d = size_for(t, c[t])
                pend = ("reverse", -pos, units, d) if units else ("close",)
            elif other_in:
                skipped["busy"] += 1
            elif same_in:
                skipped["addon"] += 1
    if pos != 0:
        close_at(len(bid) - 1, c[-1] if pos > 0 else c[-1] + sp[-1], "end of data")
    return pd.DataFrame(trades), pd.Series(curve, index=idx), skipped, swap_paid, deposited


def every_n_months(start, end, months: int, amount: float) -> dict:
    """Einzahlungen von amount € alle `months` Monate ab dem ersten Monat nach start, bis end."""
    out, t = {}, pd.Timestamp(start).normalize() + pd.DateOffset(months=months)
    while t <= pd.Timestamp(end):
        out[t] = amount
        t += pd.DateOffset(months=months)
    return out
