"""News-Check: keine Einstiege rund um angekündigte US-Termine, vorher flach, und Pause nach einem Kursschock.

Alles bezieht sich auf die Füllzeit: Ein Signal auf dem Schluss von Kerze t wird zur Eröffnung von Kerze t+1
ausgeführt (der Bot läuft um :11 nach jeder vollen Stunde).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def fill_times(index: pd.DatetimeIndex, bar: str = "60min") -> pd.DatetimeIndex:
    """Füllzeit je Signalkerze: Eröffnung der nächsten Kerze (nach einer Lücke die nächste vorhandene)."""
    nxt = index[1:].append(pd.DatetimeIndex([index[-1] + pd.Timedelta(bar)])) if len(index) else index
    return pd.DatetimeIndex(nxt)


def entry_pause(index: pd.DatetimeIndex, events: pd.Series | pd.DatetimeIndex, before_h: float = 2,
                after_h: float = 2) -> pd.Series:
    """True, wenn die Füllung des Signals von Kerze t in [Termin - before_h, Termin + after_h] fiele."""
    ev = np.sort(pd.DatetimeIndex(events).to_numpy())
    f = fill_times(index).to_numpy()
    lo = np.searchsorted(ev, f - np.timedelta64(int(after_h * 60), "m"), side="left")
    hi = np.searchsorted(ev, f + np.timedelta64(int(before_h * 60), "m"), side="right")
    return pd.Series(hi > lo, index=index, name="news_pause")


def flat_before(index: pd.DatetimeIndex, events: pd.Series | pd.DatetimeIndex, minutes: float = 30) -> pd.Series:
    """True auf Kerze t, wenn ihre Füllung die letzte mindestens `minutes` vor einem Termin ist: dann eine offene
    Position jetzt schließen (Füllung t <= Termin - minutes < Füllung t+1)."""
    cut = np.sort((pd.DatetimeIndex(events) - pd.Timedelta(minutes=minutes)).to_numpy())
    f = fill_times(index)
    f_next = fill_times(f).to_numpy()
    lo = np.searchsorted(cut, f.to_numpy(), side="left")
    hi = np.searchsorted(cut, f_next, side="left")
    return pd.Series(hi > lo, index=index, name="flach_vor_termin")


def shock_pause(bars: pd.DataFrame, atr: np.ndarray, mult: float = 3.0, bars_paused: int = 3) -> pd.Series:
    """True auf der Schock-Kerze (Spanne über mult x ATR der Kerze davor) und den bars_paused - 1 folgenden."""
    rng = (bars["high"] - bars["low"]).to_numpy(float)
    prev = np.r_[np.nan, np.asarray(atr, float)[:-1]]
    shock = rng > mult * prev
    out = np.zeros(len(bars), bool)
    for k in range(bars_paused):
        out[k:] |= shock[:len(bars) - k]
    return pd.Series(out, index=bars.index, name="schock_pause")


def ff_events(raw: list[dict], country: str = "USD", impact: str = "High") -> pd.DataFrame:
    """ForexFactory-Wochenkalender (nfs.faireconomy.media/ff_calendar_thisweek.json) -> Termine in UTC.
    Nur zum Mitschreiben im Schattenlauf (Kirons OK vom 02.11.2026), ändert keine Entscheidung."""
    rows = []
    for e in raw or []:
        if e.get("country") != country or e.get("impact") != impact or not e.get("date"):
            continue
        try:
            t = pd.Timestamp(e["date"]).tz_convert("UTC").tz_localize(None)
        except (ValueError, TypeError):
            continue
        rows.append({"utc": t, "title": str(e.get("title", ""))[:80]})
    return pd.DataFrame(rows, columns=["utc", "title"]).sort_values("utc").reset_index(drop=True)


def ff_window(ff: pd.DataFrame, fill: pd.Timestamp, before_h: float = 2, after_h: float = 2) -> list[str]:
    """Titel der ForexFactory-Termine, deren Zeit in [Füllung - after_h, Füllung + before_h] liegt (wie entry_pause)."""
    if ff is None or ff.empty:
        return []
    m = (ff["utc"] >= fill - pd.Timedelta(hours=after_h)) & (ff["utc"] <= fill + pd.Timedelta(hours=before_h))
    return [f"{t:%Y-%m-%d %H:%M} {s}" for t, s in zip(ff.loc[m, "utc"], ff.loc[m, "title"])]
