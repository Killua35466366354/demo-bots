"""Probelauf der Gold-Matrix auf einem erfundenen Markt ohne Vorteil.

Die ganze Suche (Auswahl, Finalisten, Bestätigung) läuft unverändert, nur die Kurse sind erfunden: Gold als Irrfahrt mit
32 Schritten je Minute, Schwankung mit Tagesgang und langsamen und schnellen Wechseln, Kursniveau und Anstieg ab 2024
ähnlich wie Gold. Die anderen Märkte hängen nur gleichzeitig mit Gold zusammen, nie im Voraus. In so einem Markt bringt
kein Einstieg etwas. Was hier besteht, besteht aus Glück oder wegen eines Fehlers im Verfahren. Der Lauf zeigt also, wie
oft das Verfahren sich täuscht.

Aufruf:  python -m suche.gold_matrix_probelauf <Arbeitsordner> [Seed]

Ohne Seed gilt 23. Ein anderer Seed gibt einen anderen erfundenen Markt. Schreibt nur in den Arbeitsordner, nie ins
Repo und nie ins Protokoll. Braucht keine Kursdateien.
"""
from __future__ import annotations

import contextlib
import pathlib
import sys

import numpy as np
import pandas as pd

from suche import gold_matrix as gm

SEED = 23
VON, BIS = "2015-01-01", "2026-11-07"
SCHRITTE = 32
TAGESGANG = np.array([0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.8, 1.0, 1.1, 1.0, 0.9, 1.0,      # UTC 0 bis 11
                      1.4, 1.7, 1.7, 1.5, 1.2, 1.0, 0.9, 0.8, 0.7, 0.5, 0.5, 0.6])     # UTC 12 bis 23
FREMD = [("EURUSD", 1.1, 0.4), ("USDJPY", 140.0, -0.3), ("GBPUSD", 1.25, 0.3), ("USDCAD", 1.35, -0.25),
         ("USDCHF", 0.9, -0.4), ("XAGUSD", 24.0, 0.7), ("SPXUSD", 4500.0, 0.1)]      # Name, Startkurs, Gleichlauf mit Gold


def zeiten(von: str, bis: str) -> pd.DatetimeIndex:
    """Handelsminuten: Sonntag 18 Uhr bis Freitag 17 Uhr New York, täglich eine Stunde Pause ab 17 Uhr."""
    idx = pd.date_range(von, bis, freq="1min", inclusive="left")
    ny = idx.tz_localize("UTC").tz_convert("America/New_York")
    wd, hh = ny.weekday, ny.hour
    offen = ~(((wd == 4) & (hh >= 17)) | (wd == 5) | ((wd == 6) & (hh < 18)) | (hh == 17))
    return idx[offen]


def gold(von: str, bis: str, seed: int, start: float = 1200.0, sd: float = 0.0002, schritte: int = SCHRITTE,
         stueck: int = 200_000) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed)
    idx = zeiten(von, bis)
    n = len(idx)
    langsam = np.clip(np.cumsum(rng.normal(0, 0.01, n)), -1, 1) * 0.5
    schnell = np.empty(n)
    x = 0.0
    stoss = rng.normal(0, 0.06, n)
    for i in range(n):                                     # AR(1), Halbwertszeit gut eine Stunde
        x = 0.99 * x + stoss[i]
        schnell[i] = x
    tg = TAGESGANG[idx.hour.to_numpy()]
    tg = tg / np.sqrt((tg ** 2).mean())
    vola = sd * np.exp(langsam + schnell) * tg
    drift = np.where(idx >= pd.Timestamp("2024-01-01"), 6.5e-7, 1.67e-7)
    ret, hoch, tief = np.empty(n), np.empty(n), np.empty(n)
    for a in range(0, n, stueck):
        b = min(n, a + stueck)
        weg = np.cumsum(rng.normal(0, 1, (b - a, schritte)) * (vola[a:b, None] / np.sqrt(schritte))
                        + drift[a:b, None] / schritte, axis=1)
        ret[a:b], hoch[a:b], tief[a:b] = weg[:, -1], np.maximum(weg.max(axis=1), 0), np.minimum(weg.min(axis=1), 0)
    lc = np.log(start) + np.cumsum(ret)
    lo = lc - ret
    df = pd.DataFrame({"open": np.exp(lo), "high": np.exp(lo + hoch), "low": np.exp(lo + tief), "close": np.exp(lc)},
                      index=idx).round(2)
    return df, pd.Series(ret, index=idx)


def fremd(ret: pd.Series, seed: int, start: float, rho: float, sd: float = 0.0003) -> pd.DataFrame:
    """5-Minuten-Kerzen eines anderen Marktes. Er läuft in derselben Kerze zum Teil mit Gold mit, nie davor."""
    rng = np.random.default_rng(seed)
    r5 = ret.groupby(ret.index.floor("5min")).sum()
    z = (r5 / r5.std()).to_numpy()
    c = start * np.exp(np.cumsum(sd * (rho * z + np.sqrt(1 - rho ** 2) * rng.normal(0, 1, len(r5)))))
    o = np.r_[start, c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c), "low": np.minimum(o, c), "close": c}, index=r5.index)


def alles(von: str = VON, bis: str = BIS, seed: int = SEED) -> tuple[pd.DataFrame, dict, tuple]:
    g, ret = gold(von, bis, seed)
    fr = {name: fremd(ret, seed + 10 + i, start, rho) for i, (name, start, rho) in enumerate(FREMD)}
    tage = pd.bdate_range(pd.Timestamp(von) - pd.Timedelta(days=30), bis)
    rz = (tage.values.astype("datetime64[D]"),
          1.5 + np.cumsum(np.random.default_rng(seed + 99).normal(0, 0.03, len(tage))))
    return g, fr, rz


@contextlib.contextmanager
def erfundener_markt(arbeit: pathlib.Path, daten: tuple, seed: int = SEED):
    """Hängt das Rechenwerk für die Dauer des Blocks an den erfundenen Markt und an den Arbeitsordner."""
    g, fr, rz = daten

    def lade(ordner, von, bis):
        von, bis = pd.Timestamp(von), pd.Timestamp(bis)
        schnitt = lambda df: df[(df.index >= von) & (df.index < bis)]      # noqa: E731
        t = gm.lies_termine()
        t = t[(t >= np.datetime64(von, "ns")) & (t < np.datetime64(bis, "ns"))]
        ok = rz[0] < np.datetime64(bis, "D")
        return gm.markt(schnitt(g), {k: schnitt(v) for k, v in fr.items()}, (rz[0][ok], rz[1][ok]), t)

    alt = (gm.lade_markt, gm.FINALISTEN, gm.ERGEBNIS, gm.daten_siegel)
    gm.lade_markt, gm.daten_siegel = lade, (lambda ordner: {"erfunden": f"Seed {seed}"})
    gm.FINALISTEN, gm.ERGEBNIS = arbeit / "VORAB_gold_matrix_finalisten.yaml", arbeit / "ergebnis_gold_matrix"
    try:
        yield
    finally:
        gm.lade_markt, gm.FINALISTEN, gm.ERGEBNIS, gm.daten_siegel = alt


def main(argv: list[str]) -> int:
    if len(argv) not in (1, 2):
        raise SystemExit(__doc__)
    seed = int(argv[1]) if len(argv) == 2 else SEED
    arbeit = pathlib.Path(argv[0]).resolve()
    if gm.ROOT in arbeit.parents or arbeit == gm.ROOT:
        raise SystemExit("Der Arbeitsordner des Probelaufs darf nicht im Repo liegen.")
    arbeit.mkdir(parents=True, exist_ok=True)
    daten = alles(seed=seed)
    print(f"erfundener Markt (Seed {seed}): {len(daten[0])} Minuten, {daten[0].index[0]} bis {daten[0].index[-1]}", flush=True)
    with erfundener_markt(arbeit, daten, seed):
        if not gm.FINALISTEN.exists():
            gm.lauf_auswahl(arbeit, arbeit)
        gm.lauf_bestaetigung(arbeit, arbeit)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
