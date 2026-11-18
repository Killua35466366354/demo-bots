"""Runde "Starker Rückblick": Kursdaten vorbereiten (echte UTC-Zeit, Handelstage, Spread-Profil).

Aufruf: python -m suche.rueckblick_daten <Arbeitsordner> [SYMBOL ...]

Liest die HistData-5-Minuten-Kerzen (Bid) aus dem Projektordner, rechnet die Uhr auf echtes UTC um (LIESMICH_zeit.md:
Dateizeit + 2 Stunden ist Ortszeit Athen) und speichert je Markt eine npz-Datei mit Kerzen, New Yorker Uhrzeit,
Handelstag (beginnt 17:00 New York) und dem Spread je Kerze. Der Spread kommt aus echten Capital.com-Kerzen
(Bid und Ask, 15 Minuten, Dezember 2025 bis November 2026): Median je Viertelstunde der New Yorker Uhr.
Dieses Programm rechnet keine Strategie.
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd

DATEN = pathlib.Path("/mnt/project-files/strategie-suche/daten")
KERZEN = pathlib.Path("/mnt/project-files/strategie-suche/runde3/kerzen")
NY = "America/New_York"

# Symbol -> (Capital.com-Epic, Klasse)
MAERKTE = {
    "SPXUSD": ("US500", "index"), "NSXUSD": ("US100", "index"), "GRXEUR": ("DE40", "index"),
    "UKXGBP": ("UK100", "index"), "JPXJPY": ("J225", "index"),
    "XAUUSD": ("GOLD", "metall"), "XAGUSD": ("SILVER", "metall"),
    "EURUSD": ("EURUSD", "fx"), "GBPUSD": ("GBPUSD", "fx"), "USDJPY": ("USDJPY", "fx"), "USDCHF": ("USDCHF", "fx"),
    "USDCAD": ("USDCAD", "fx"), "AUDUSD": ("AUDUSD", "fx"), "NZDUSD": ("NZDUSD", "fx"), "EURJPY": ("EURJPY", "fx"),
    "GBPJPY": ("GBPJPY", "fx"), "EURGBP": ("EURGBP", "fx"), "EURCHF": ("EURCHF", "fx"), "AUDNZD": ("AUDNZD", "fx"),
    "GBPNZD": ("GBPNZD", "fx"),
}


def echtes_utc(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """HistData-Dateizeit (+5 h, so stehen die Dateien) -> echtes UTC. Ortszeit Athen = Index + 2 Stunden."""
    lokal = (idx + pd.Timedelta(hours=2)).tz_localize("Europe/Athens", ambiguous="NaT", nonexistent="NaT")
    return lokal.tz_convert("UTC").tz_localize(None)


def spread_profil(epic: str) -> np.ndarray:
    """Median-Spread (Ask minus Bid zur Eröffnung) je Viertelstunde der New Yorker Uhr, 96 Werte."""
    df = pd.read_csv(KERZEN / f"{epic}_MINUTE_15.csv.gz", parse_dates=["utc"], index_col="utc")
    sp = (df["open_ask"] - df["open_bid"]).astype(float)
    sp = sp[sp > 0]
    ny = sp.index.tz_localize("UTC").tz_convert(NY)
    slot = np.asarray(ny.hour * 4 + ny.minute // 15)
    prof = pd.Series(sp.to_numpy(), index=slot).groupby(level=0).median().reindex(range(96))
    return prof.interpolate(limit_direction="both").to_numpy(float)


def baue(sym: str, ziel: pathlib.Path) -> dict:
    epic, klasse = MAERKTE[sym]
    df = pd.read_csv(DATEN / f"{sym}_5min.csv.gz", index_col=0, parse_dates=True)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    utc = echtes_utc(df.index)
    ok = ~utc.isna()
    df, utc = df[ok], utc[ok]
    order = np.argsort(utc.values, kind="stable")
    df, utc = df.iloc[order], utc[order]
    keep = ~pd.Index(utc).duplicated(keep="last")
    df, utc = df[keep], utc[keep]
    ny = utc.tz_localize("UTC").tz_convert(NY).tz_localize(None)
    # Handelstag: beginnt 17:00 New York, heißt wie der Kalendertag, an dem er endet
    tag = (ny + pd.Timedelta(hours=7)).normalize()
    nymin = np.asarray(ny.hour * 60 + ny.minute, dtype=np.int32)
    prof = spread_profil(epic)
    sp = prof[np.asarray(ny.hour * 4 + ny.minute // 15)]
    np.savez_compressed(
        ziel / f"{sym}.npz",
        t=utc.values.astype("datetime64[ns]"), o=df["open"].to_numpy(float), h=df["high"].to_numpy(float),
        l=df["low"].to_numpy(float), c=df["close"].to_numpy(float), sp=sp.astype(float), nymin=nymin,
        tag=tag.values.astype("datetime64[D]"), prof=prof)
    return {"symbol": sym, "kerzen": int(len(df)), "von": str(utc[0]), "bis": str(utc[-1]),
            "spread_median": float(np.median(sp)), "spread_min": float(prof.min()), "spread_max": float(prof.max())}


def main(argv: list[str]) -> int:
    ziel = pathlib.Path(argv[0])
    ziel.mkdir(parents=True, exist_ok=True)
    for sym in argv[1:] or list(MAERKTE):
        print(baue(sym, ziel), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
