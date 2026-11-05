"""Order simulation for the two gold strategies.

run_tv:   rebuilds TradingView's Strategy Tester for ONE strategy (3 % of equity per entry,
          up to 9 entries, every entry counted as its own trade, fills at the next bar's open,
          no costs unless given). Used to compare with Kiron's TradingView numbers.
run_live: what the bot could really do with a small CFD account: one position at a time,
          fixed size (1 oz), only the first entry of each signal, A opens longs, B opens shorts,
          each position is closed by its own strategy's exit, real spread, margin and limits.
"""
import numpy as np
import pandas as pd


def run_tv(df, sig, direction, pyramiding=9, pct=3.0, init_cap=10000.0,
           commission_pct=0.0, close_includes_new_entry=True):
    o = df["open"].to_numpy(float)
    c = df["close"].to_numpy(float)
    ent = sig["entry"].to_numpy(bool)
    ext = sig["exit"].to_numpy(bool)
    idx = df.index
    open_tr, trades, curve = [], [], np.empty(len(df))
    net = 0.0
    pend_entry = pend_exit = False
    pend_qty = 0.0
    for t in range(len(df)):
        if pend_entry or pend_exit:
            px = o[t]
            before = list(open_tr)
            if pend_entry and len(open_tr) < pyramiding:
                open_tr.append((t, px, pend_qty))
            if pend_exit:
                closing = open_tr if close_includes_new_entry else before
                for ei, epx, q in closing:
                    fee = commission_pct / 100 * q * (epx + px)
                    pnl = direction * (px - epx) * q - fee
                    net += pnl
                    trades.append({"entry_time": idx[ei], "entry_px": epx, "exit_time": idx[t],
                                   "exit_px": px, "qty": q, "pnl": pnl, "pos_id": closing[0][0]})
                open_tr = [x for x in open_tr if x not in closing]
            pend_entry = pend_exit = False
        open_pnl = sum(direction * (c[t] - epx) * q for _, epx, q in open_tr)
        curve[t] = init_cap + net + open_pnl
        if ent[t]:
            pend_qty = pct / 100 * curve[t] / c[t]
            pend_entry = True
        if ext[t] and open_tr:
            pend_exit = True
    return pd.DataFrame(trades), pd.Series(curve, index=idx)


def run_live(bid, spread, sig_a, sig_b, size_oz=1.0, start_eur=250.0, eurusd=1.117,
             margin_rate=0.05, stop_usd=None, conflict="first", swap_pct_year=0.0,
             day_loss_pct=None, week_loss_pct=None, kill_dd_pct=None):
    """bid: OHLC of bid prices; spread: Series (USD) aligned with bid, ask = bid + spread."""
    o, h, l, c = (bid[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    sp = spread.reindex(bid.index).ffill().to_numpy(float)
    a_in, a_out = sig_a["entry"].to_numpy(bool), sig_a["exit"].to_numpy(bool)
    b_in, b_out = sig_b["entry"].to_numpy(bool), sig_b["exit"].to_numpy(bool)
    idx = bid.index
    days = idx.normalize()
    weeks = idx.to_period("W")
    eq = start_eur
    peak = start_eur
    pos, epx, et, stop = 0, 0.0, None, None
    pend = None                      # ("open", +1/-1) or ("close",) or ("reverse", +1/-1)
    trades, curve = [], np.empty(len(bid))
    skipped = {"margin": 0, "conflict": 0, "limits": 0, "busy": 0, "addon": 0}
    day_start_eq, week_start_eq = eq, eq
    last_day, last_week = days[0], weeks[0]
    swap_paid = 0.0

    def close_at(t, px, why):
        nonlocal eq, pos, stop
        pnl_eur = pos * (px - epx) * size_oz / eurusd
        eq += pnl_eur
        trades.append({"side": "long" if pos > 0 else "short", "entry_time": et, "entry_px": epx,
                       "exit_time": idx[t], "exit_px": px, "pnl_eur": pnl_eur, "reason": why})
        pos, stop = 0, None

    for t in range(len(bid)):
        if days[t] != last_day:
            if pos != 0 and swap_pct_year:
                fee = c[t - 1] * size_oz * swap_pct_year / 100 / 365 / eurusd
                eq -= fee
                swap_paid += fee
            day_start_eq, last_day = eq, days[t]
        if weeks[t] != last_week:
            week_start_eq, last_week = eq, weeks[t]

        # 1) orders from the previous bar's close fill at this bar's open
        if pend is not None:
            if pend[0] in ("close", "reverse") and pos != 0:
                close_at(t, o[t] if pos > 0 else o[t] + sp[t], "signal")
            if pend[0] in ("open", "reverse"):
                side = pend[1]
                epx = o[t] + sp[t] if side > 0 else o[t]
                pos, et = side, idx[t]
                if stop_usd:
                    stop = epx - stop_usd if side > 0 else epx + stop_usd
            pend = None

        # 2) stop and margin close-out inside the bar
        if pos > 0 and stop is not None and l[t] <= stop:
            close_at(t, min(o[t], stop), "stop")
        elif pos < 0 and stop is not None and h[t] + sp[t] >= stop:
            close_at(t, max(o[t] + sp[t], stop), "stop")
        if pos != 0:
            worst = l[t] if pos > 0 else h[t] + sp[t]
            margin = epx * size_oz * margin_rate / eurusd
            if eq + pos * (worst - epx) * size_oz / eurusd < 0.5 * margin:
                close_at(t, worst, "margin call")

        mark = c[t] if pos >= 0 else c[t] + sp[t]
        curve[t] = eq + (pos * (mark - epx) * size_oz / eurusd if pos else 0.0)
        peak = max(peak, curve[t])

        # 3) signals on this bar's close
        blocked = ((day_loss_pct and eq < day_start_eq * (1 - day_loss_pct / 100)) or
                   (week_loss_pct and eq < week_start_eq * (1 - week_loss_pct / 100)) or
                   (kill_dd_pct and curve[t] < peak * (1 - kill_dd_pct / 100)))
        if pos == 0:
            if a_in[t] and b_in[t]:
                skipped["conflict"] += 1
            elif a_in[t] or b_in[t]:
                want = 1 if a_in[t] else -1
                if blocked:
                    skipped["limits"] += 1
                elif c[t] * size_oz * margin_rate / eurusd > eq:
                    skipped["margin"] += 1
                else:
                    pend = ("open", want)
        else:
            own_exit = a_out[t] if pos > 0 else b_out[t]
            same_in = a_in[t] if pos > 0 else b_in[t]
            other_in = b_in[t] if pos > 0 else a_in[t]
            if own_exit:
                pend = ("close",)
            elif other_in and conflict == "reverse" and not blocked:
                pend = ("reverse", -pos)
            elif other_in:
                skipped["busy"] += 1
            elif same_in:
                skipped["addon"] += 1
    if pos != 0:
        close_at(len(bid) - 1, c[-1] if pos > 0 else c[-1] + sp[-1], "end of data")
    return pd.DataFrame(trades), pd.Series(curve, index=idx), skipped, swap_paid


def summary(pnl, curve, start_value, months):
    """Key numbers for a list of trade results (same currency as curve)."""
    pnl = pd.Series(pnl, dtype=float)
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    streak = longest = 0
    for x in pnl:
        streak = streak + 1 if x <= 0 else 0
        longest = max(longest, streak)
    dd = (curve / curve.cummax() - 1).min() if len(curve) else 0.0
    return {
        "trades": int(len(pnl)),
        "trades_per_month": round(len(pnl) / months, 1) if months else None,
        "win_rate_pct": round(100 * len(wins) / len(pnl), 1) if len(pnl) else None,
        "avg_win": round(wins.mean(), 2) if len(wins) else 0.0,
        "avg_loss": round(losses.mean(), 2) if len(losses) else 0.0,
        "profit_factor": round(wins.sum() / -losses.sum(), 2) if losses.sum() < 0 else None,
        "expectancy": round(pnl.mean(), 2) if len(pnl) else None,
        "net": round(pnl.sum(), 2),
        "return_pct": round(100 * pnl.sum() / start_value, 1),
        "max_drawdown_pct": round(100 * dd, 1),
        "longest_losing_streak": longest,
    }
