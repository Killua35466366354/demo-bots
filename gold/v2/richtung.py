"""Markt-Richtungs-Check: Wohin läuft Gold gerade, auf Tages- und 4-Stunden-Sicht?

+1 = Tagesschluss über seinem 50-Tage-Durchschnitt UND 4-Stunden-Schluss über seiner EMA 50 (nur Long erlaubt)
-1 = beide darunter (nur Short erlaubt)
 0 = uneinig oder noch zu wenig Daten (kein Einstieg)

Gerechnet aus den Stundenkerzen, damit Backtest und Bot genau dasselbe sehen. Handelstag und 4-Stunden-Kerzen
beginnen um 22:00 UTC wie in gold/backtest/protocol.py. Eine Stundenkerze sieht nur Tages- und 4-Stunden-Kerzen,
die vor ihrem eigenen Schluss fertig waren (kein Blick in die Zukunft).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

OFFSET = "22h"


def session_from_hourly(bars: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Tages- ("1D") oder 4-Stunden-Kerzen ("240min") aus Stundenkerzen, Beginn 22:00 UTC. Reste mit höchstens
    einem Viertel der üblichen Stunden fallen weg (wie session_bars bei den Minutendaten)."""
    step = pd.Timedelta("24h" if rule == "1D" else rule)
    g = bars.resample(step, label="left", closed="left", offset=OFFSET)
    out = g.agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    n = g["close"].count()
    full = step / pd.Timedelta("60min")
    return out[n > full / 4].dropna(subset=["open"])


def _asof(sig: pd.Series, ready: pd.DatetimeIndex, index: pd.DatetimeIndex, bar: pd.Timedelta) -> np.ndarray:
    """Wert von sig (fertig zu den Zeiten `ready`) für jede Stundenkerze, die zu index + bar schließt."""
    pos = ready.searchsorted(index + bar, side="right") - 1
    vals = sig.to_numpy()
    return np.where(pos >= 0, vals[np.clip(pos, 0, None)], 0)


def direction(bars: pd.DataFrame, sma_days: int = 50, ema_4h: int = 50, bar: str = "60min") -> pd.Series:
    """+1, -1 oder 0 je Stundenkerze, gültig auf ihrem Schlusskurs."""
    d = session_from_hourly(bars, "1D")
    sma = d["close"].rolling(sma_days, min_periods=sma_days).mean()
    day = pd.Series(np.where(sma.isna(), 0, np.sign(d["close"] - sma)), index=d.index)
    h4 = session_from_hourly(bars, "240min")
    ema = h4["close"].ewm(span=ema_4h, adjust=False).mean()
    ema.iloc[:ema_4h - 1] = np.nan
    four = pd.Series(np.where(ema.isna(), 0, np.sign(h4["close"] - ema)), index=h4.index)
    b = pd.Timedelta(bar)
    a = _asof(day, d.index + pd.Timedelta("24h"), bars.index, b)
    f = _asof(four, h4.index + pd.Timedelta("240min"), bars.index, b)
    out = np.where((a > 0) & (f > 0), 1, np.where((a < 0) & (f < 0), -1, 0))
    return pd.Series(out.astype(int), index=bars.index, name="richtung")
