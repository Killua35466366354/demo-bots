"""The vectorised port must give exactly the signals of a plain bar-by-bar reading of the Pine code."""
import math

import numpy as np
import pandas as pd
import pytest

from gold.backtest.pine_port import (crossover, htf_ema, signals_a_long, signals_b_short, signals_c_long,
                                     stdev, stoch)

WARMUP = 120


def random_bars(seed, n=4000):
    rng = np.random.default_rng(seed)
    close = 4000 * np.exp(np.cumsum(rng.standard_t(4, n) * 0.0004))
    open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.0001, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.0003, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.0003, n)))
    idx = pd.date_range("2026-01-05", periods=n, freq="1min")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=idx)


def win(xs, i, n):
    return xs[i - n + 1:i + 1]


def mean(xs):
    return sum(xs) / len(xs)


def pstdev(xs):
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def stoch_k_d(o, h, l, c, n=14, sk=3, sd=3):
    raw = [None] * len(c)
    for i in range(n - 1, len(c)):
        ll, hh = min(win(l, i, n)), max(win(h, i, n))
        raw[i] = 100 * (c[i] - ll) / (hh - ll)
    k = [mean(win(raw, i, sk)) if i >= n + sk - 2 else None for i in range(len(c))]
    d = [mean(win(k, i, sd)) if i >= n + sk + sd - 3 else None for i in range(len(c))]
    return k, d


def reference_a(df):
    """Strategy A read line by line from A_long_vixfix_stochrsi_v2.pine, default inputs."""
    o, h, l, c = (df[x].tolist() for x in ("open", "high", "low", "close"))
    k, d = stoch_k_d(o, h, l, c)
    n = len(c)
    wvf = [None] * n
    for i in range(21, n):
        hc = max(win(c, i, 22))
        wvf[i] = (hc - l[i]) / hc * 100
    upper, rhigh = [None] * n, [None] * n
    for i in range(70, n):
        w = win(wvf, i, 20)
        upper[i] = mean(w) + 2.0 * pstdev(w)
        rhigh[i] = max(win(wvf, i, 50)) * 0.85
    entry, exit_ = [False] * n, [False] * n
    for i in range(WARMUP, n):
        spike_prev = wvf[i - 1] >= upper[i - 1] or wvf[i - 1] >= rhigh[i - 1]
        calm = wvf[i] < upper[i] and wvf[i] < rhigh[i]
        ctx = c[i] > c[i - 3] and (c[i] < c[i - 40] or c[i] < c[i - 14])
        up_range = l[i] > l[i - 1] and c[i] > h[i - 1]
        up_aggr = c[i] > c[i - 1] and c[i] > o[i - 1]
        entry[i] = (up_range and ctx and spike_prev and calm) or (up_aggr and ctx and spike_prev and not calm)
        exit_[i] = k[i] > d[i] and k[i - 1] <= d[i - 1] and k[i] > 80
    return entry, exit_


def reference_b(df):
    """Strategy B read line by line from B_short_vixfix_meanrev_v6.pine, default inputs."""
    o, h, l, c = (df[x].tolist() for x in ("open", "high", "low", "close"))
    k, d = stoch_k_d(o, h, l, c)
    n = len(c)
    wvf = [None] * n
    for i in range(21, n):
        lc = min(win(c, i, 22))
        wvf[i] = (h[i] - lc) / lc * 100
    upper, rhigh = [None] * n, [None] * n
    for i in range(70, n):
        w = win(wvf, i, 20)
        upper[i] = mean(w) + 2.0 * pstdev(w)
        rhigh[i] = max(win(wvf, i, 50)) * 0.85
    entry, exit_ = [False] * n, [False] * n
    for i in range(WARMUP, n):
        spike_now = wvf[i] >= upper[i] or wvf[i] >= rhigh[i]
        spike_prev = wvf[i - 1] >= upper[i - 1] or wvf[i - 1] >= rhigh[i - 1]
        ctx = c[i] < c[i - 3] and (c[i] > c[i - 40] or c[i] > c[i - 14])
        dn_range = h[i] < h[i - 1] and c[i] < l[i - 1]
        dn_aggr = c[i] < c[i - 1] and c[i] < o[i - 1]
        entry[i] = (dn_range and ctx and spike_prev and not spike_now) or (dn_aggr and ctx and spike_prev and spike_now)
        exit_[i] = k[i] < d[i] and k[i - 1] >= d[i - 1] and k[i] < 20
    return entry, exit_


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_strategy_a_matches_bar_by_bar_reading(seed):
    df = random_bars(seed)
    sig = signals_a_long(df)
    entry, exit_ = reference_a(df)
    assert sig["entry"].iloc[WARMUP:].tolist() == entry[WARMUP:]
    assert sig["exit"].iloc[WARMUP:].tolist() == exit_[WARMUP:]
    assert sum(entry) > 5 and sum(exit_) > 5      # the test data really produces signals


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_strategy_b_matches_bar_by_bar_reading(seed):
    df = random_bars(seed)
    sig = signals_b_short(df)
    entry, exit_ = reference_b(df)
    assert sig["entry"].iloc[WARMUP:].tolist() == entry[WARMUP:]
    assert sig["exit"].iloc[WARMUP:].tolist() == exit_[WARMUP:]
    assert sum(entry) > 5 and sum(exit_) > 5


def test_aggressive_long_uses_previous_open():
    """A compares close with open[1]. A bar that closes below its own open still counts."""
    df = random_bars(4, n=20000)
    df["open"] = df["close"].shift(1).fillna(df["close"]) * (1 + np.random.default_rng(5).normal(0, 0.001, len(df)))
    df["high"] = df[["open", "high", "close"]].max(axis=1)
    df["low"] = df[["open", "low", "close"]].min(axis=1)
    sig = signals_a_long(df)
    red = df["close"] < df["open"]
    assert (sig["entry_aggr"] & red).any()
    assert sig["entry"].iloc[WARMUP:].tolist() == reference_a(df)[0][WARMUP:]


def test_aggressive_short_uses_previous_open():
    """B compares close with open[1] too (line 94 of the Pine code). A green bar can still count."""
    df = random_bars(6, n=20000)
    df["open"] = df["close"].shift(1).fillna(df["close"]) * (1 + np.random.default_rng(7).normal(0, 0.001, len(df)))
    df["high"] = df[["open", "high", "close"]].max(axis=1)
    df["low"] = df[["open", "low", "close"]].min(axis=1)
    sig = signals_b_short(df)
    green = df["close"] > df["open"]
    assert (sig["entry_aggr"] & green).any()
    assert sig["entry"].iloc[WARMUP:].tolist() == reference_b(df)[0][WARMUP:]


def test_pine_helpers():
    x = pd.Series([1.0, 2.0, 3.0, 4.0])
    assert stdev(x, 4).iloc[-1] == pytest.approx(math.sqrt(1.25))      # biased, as in Pine
    flat = pd.Series([5.0] * 20)
    assert stoch(flat, flat, flat, 14).isna().all()                       # 0/0 is na in Pine
    a, b = pd.Series([1, 2, 3.0]), pd.Series([2, 2, 2.0])
    assert crossover(a, b).tolist() == [False, False, True]


def test_htf_ema_uses_last_completed_hour():
    """request.security(..., ta.ema(close, n)[1], lookahead_on): inside hour H the value is the EMA up to hour H-1."""
    df = random_bars(8, n=3000)
    got = htf_ema(df, "60min", 5)
    hourly = df["close"].resample("60min").last().tolist()
    alpha, ema = 2 / 6, []
    for i, x in enumerate(hourly):
        ema.append(x if i == 0 else alpha * x + (1 - alpha) * ema[-1])
    for t in (df.index[400], df.index[1799], df.index[2999]):
        h = (t - df.index[0]) // pd.Timedelta("60min")
        assert got[t] == pytest.approx(ema[h - 1])
    assert got.iloc[:300].isna().all()                  # first 4 hours have no EMA yet, the 5th waits for its close


def test_short_trend_filter_only_removes_entries_above_the_ema():
    df = random_bars(9, n=20000)
    plain, filt = signals_b_short(df), signals_b_short(df, useTrend=True, trendLen=20)
    ema = htf_ema(df, "60min", 20)
    assert (filt["entry"] <= plain["entry"]).all()
    assert (filt["entry"] == (plain["entry"] & (df["close"] < ema))).all()
    assert filt["entry"].sum() < plain["entry"].sum()


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_long_v6_with_defaults_gives_the_signals_of_strategy_a(seed):
    """C is written so that its defaults reproduce A v2. TradingView must then show the same trades."""
    df = random_bars(seed)
    c, a = signals_c_long(df), signals_a_long(df)
    entry, exit_ = reference_a(df)
    assert c["entry"].iloc[WARMUP:].tolist() == entry[WARMUP:] == a["entry"].iloc[WARMUP:].tolist()
    assert c["exit"].iloc[WARMUP:].tolist() == exit_[WARMUP:]


def test_long_trend_filter_only_removes_entries_below_the_ema():
    df = random_bars(10, n=20000)
    plain, filt = signals_c_long(df), signals_c_long(df, useTrend=True, trendLen=20)
    ema = htf_ema(df, "60min", 20)
    assert (filt["entry"] == (plain["entry"] & (df["close"] > ema))).all()
    assert 0 < filt["entry"].sum() < plain["entry"].sum()
