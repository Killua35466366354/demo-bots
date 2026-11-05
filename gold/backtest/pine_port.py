"""1:1 port of Kiron's TradingView strategies, default inputs.

A: "Vix FIX / StochRSI Strategy" (Pine v2, long only)      -> strategies/A_long_vixfix_stochrsi_v2.pine
B: "Vix Fix Mean Reversion SHORT v6" (Pine v6, short only) -> strategies/B_short_vixfix_meanrev_v6.pine
C: "Vix Fix Mean Reversion LONG v6" (Pine v6, long only)   -> strategies/C_long_vixfix_meanrev_v6.pine
   (mirror of B, written for Kiron; with default inputs it gives A's signals)

Everything is evaluated on bar close, as Pine does with calc_on_every_tick=false.
Pine rules reproduced here:
  * sma/highest/lowest/stdev return na until the window is full
  * stdev is the biased (population) estimate, Pine's default
  * division by zero gives na, and any comparison with na is false
  * crossover(a, b) = a > b and a[1] <= b[1]
"""
import pandas as pd


def sma(x, n):
    return x.rolling(n, min_periods=n).mean()


def stdev(x, n):
    return x.rolling(n, min_periods=n).std(ddof=0)


def highest(x, n):
    return x.rolling(n, min_periods=n).max()


def lowest(x, n):
    return x.rolling(n, min_periods=n).min()


def stoch(close, high, low, n):
    ll = lowest(low, n)
    rng = highest(high, n) - ll
    return 100 * (close - ll) / rng.where(rng != 0)


def htf_ema(df, tf="60min", length=200):
    """request.security(syminfo.tickerid, tf, ta.ema(close, length)[1], lookahead = barmerge.lookahead_on):
    on every chart bar, the EMA as of the last COMPLETED higher-timeframe bar (no repainting).
    na until `length` higher-timeframe bars exist."""
    htf_close = df["close"].resample(tf, label="left", closed="left").last().dropna()
    ema = htf_close.ewm(span=length, adjust=False).mean()
    ema.iloc[:length - 1] = float("nan")
    prev = ema.shift(1)
    return pd.Series(prev.reindex(df.index.floor(tf)).to_numpy(), index=df.index)


def crossover(a, b):
    return (a > b) & (a.shift(1) <= b.shift(1))


def crossunder(a, b):
    return (a < b) & (a.shift(1) >= b.shift(1))


def signals_a_long(df, Stochlength=14, StochOverBought=80, smoothK=3, smoothD=3,
                   pd_=22, bbl=20, mult=2.0, lb=50, ph=0.85, ltLB=40, mtLB=14, str_=3):
    """Strategy A. Returns DataFrame with columns entry, exit (bool) plus helpers."""
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    k = sma(stoch(c, h, l, Stochlength), smoothK)
    d = sma(k, smoothD)

    hc = highest(c, pd_)
    wvf = (hc - l) / hc * 100
    sDev = mult * stdev(wvf, bbl)
    midLine = sma(wvf, bbl)
    upperBand = midLine + sDev
    rangeHigh = highest(wvf, lb) * ph

    upRange = (l > l.shift(1)) & (c > h.shift(1))
    upRange_Aggr = (c > c.shift(1)) & (c > o.shift(1))      # open[1] in the original, not open
    spikePrev = (wvf.shift(1) >= upperBand.shift(1)) | (wvf.shift(1) >= rangeHigh.shift(1))
    calm = (wvf < upperBand) & (wvf < rangeHigh)
    filtered = spikePrev & calm
    filtered_Aggr = spikePrev & ~calm & wvf.notna() & upperBand.notna() & rangeHigh.notna()

    ctx = (c > c.shift(str_)) & ((c < c.shift(ltLB)) | (c < c.shift(mtLB)))
    alert3 = upRange & ctx & filtered
    alert4 = upRange_Aggr & ctx & filtered_Aggr

    isOverBought = crossover(k, d) & (k > StochOverBought)
    return pd.DataFrame({"entry": alert3 | alert4, "entry_filt": alert3, "entry_aggr": alert4,
                         "exit": isOverBought, "wvf": wvf, "k": k, "d": d}, index=df.index)


def signals_b_short(df, wvfLen=22, bbLen=20, bbMult=2.0, pctLen=50, pctHigh=0.85,
                    useFilt=True, useAggr=True, ltLB=40, mtLB=14, strBars=3,
                    stochLen=14, smoothK=3, smoothD=3, osLevel=20,
                    useTrend=False, trendTF="60min", trendLen=200):
    """Strategy B. Default inputs; of the regime filters only the trend filter is ported so far.
    Stop, take profit, time stop, add-on spacing and the session filter are not ported."""
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    lc = lowest(c, wvfLen)
    wvf = (h - lc) / lc * 100
    bbDev = bbMult * stdev(wvf, bbLen)
    midLine = sma(wvf, bbLen)
    upperBand = midLine + bbDev
    rangeHigh = highest(wvf, pctLen) * pctHigh

    spikeNow = (wvf >= upperBand) | (wvf >= rangeHigh)
    spikePrev = (wvf.shift(1) >= upperBand.shift(1)) | (wvf.shift(1) >= rangeHigh.shift(1))

    dnRange = (h < h.shift(1)) & (c < l.shift(1))
    dnRangeAggr = (c < c.shift(1)) & (c < o.shift(1))       # open[1] in the original, as in A
    priceCtx = (c < c.shift(strBars)) & ((c > c.shift(ltLB)) | (c > c.shift(mtLB)))

    filtSig = dnRange & priceCtx & spikePrev & ~spikeNow
    aggrSig = dnRangeAggr & priceCtx & spikePrev & spikeNow

    k = sma(stoch(c, h, l, stochLen), smoothK)
    d = sma(k, smoothD)
    exitSig = crossunder(k, d) & (k < osLevel)
    trendOk = c < htf_ema(df, trendTF, trendLen) if useTrend else True
    entry = ((filtSig & useFilt) | (aggrSig & useAggr)) & trendOk
    return pd.DataFrame({"entry": entry, "entry_filt": filtSig, "entry_aggr": aggrSig,
                         "exit": exitSig, "wvf": wvf, "k": k, "d": d}, index=df.index)


def signals_c_long(df, wvfLen=22, bbLen=20, bbMult=2.0, pctLen=50, pctHigh=0.85,
                   useFilt=True, useAggr=True, ltLB=40, mtLB=14, strBars=3,
                   stochLen=14, smoothK=3, smoothD=3, obLevel=80,
                   useTrend=False, trendTF="60min", trendLen=200):
    """Strategy C, the long mirror of B. Same parts ported as for B."""
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    hc = highest(c, wvfLen)
    wvf = (hc - l) / hc * 100
    bbDev = bbMult * stdev(wvf, bbLen)
    midLine = sma(wvf, bbLen)
    upperBand = midLine + bbDev
    rangeHigh = highest(wvf, pctLen) * pctHigh

    spikeNow = (wvf >= upperBand) | (wvf >= rangeHigh)
    spikePrev = (wvf.shift(1) >= upperBand.shift(1)) | (wvf.shift(1) >= rangeHigh.shift(1))

    upRange = (l > l.shift(1)) & (c > h.shift(1))
    upRangeAggr = (c > c.shift(1)) & (c > o.shift(1))
    priceCtx = (c > c.shift(strBars)) & ((c < c.shift(ltLB)) | (c < c.shift(mtLB)))

    filtSig = upRange & priceCtx & spikePrev & ~spikeNow
    aggrSig = upRangeAggr & priceCtx & spikePrev & spikeNow

    k = sma(stoch(c, h, l, stochLen), smoothK)
    d = sma(k, smoothD)
    exitSig = crossover(k, d) & (k > obLevel)
    trendOk = c > htf_ema(df, trendTF, trendLen) if useTrend else True
    entry = ((filtSig & useFilt) | (aggrSig & useAggr)) & trendOk
    return pd.DataFrame({"entry": entry, "entry_filt": filtSig, "entry_aggr": aggrSig,
                         "exit": exitSig, "wvf": wvf, "k": k, "d": d}, index=df.index)
