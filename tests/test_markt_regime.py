"""Prüft die Rechnung des Tests Trend oder Seitwärts (suche/markt_regime.py) an erfundenen Zahlen."""
import numpy as np
import pandas as pd

from suche import markt_regime as mr


def test_effizienz_gerade_und_zickzack():
    gerade = np.arange(30, dtype=float)
    assert mr.effizienz(gerade, 20)[25] == 1.0
    zick = np.array([100.0 + (i % 2) for i in range(30)])
    assert mr.effizienz(zick, 20)[25] == 0.0
    assert np.isnan(mr.effizienz(gerade, 20)[19])


def test_phase_nimmt_nur_schluesse_vor_dem_einstieg():
    zeiten = pd.date_range("2025-01-01 22:00", periods=30, freq="D")
    schluesse = pd.Series(np.arange(30, dtype=float), index=zeiten)
    schluesse.iloc[25] = 0.0          # Sturz am Tag 25 macht diesen Tag seitwärts
    ein = pd.Series([zeiten[25], zeiten[25] + pd.Timedelta(minutes=5)])
    ph, wert = mr.phase_je_trade(ein, schluesse, 20, 0.30)
    assert ph.iloc[0] == "trend"       # genau zum Schluss: der Schluss zählt noch nicht
    assert ph.iloc[1] == "seitwaerts"  # danach ist er bekannt
    assert wert.iloc[0] == 1.0


def test_phase_fehlt_ohne_genug_tage():
    zeiten = pd.date_range("2025-01-01 22:00", periods=10, freq="D")
    schluesse = pd.Series(np.arange(10, dtype=float), index=zeiten)
    ph, _ = mr.phase_je_trade(pd.Series([zeiten[-1] + pd.Timedelta(hours=1)]), schluesse, 20, 0.30)
    assert ph.iloc[0] is None


def test_holm_und_zufall():
    assert mr.holm({"a": 0.01, "b": 0.04, "c": 0.03}) == {"a": True, "b": False, "c": False}
    assert mr.holm({"a": 0.01, "b": 0.02}) == {"a": True, "b": True}
    r = np.array([1.0] * 10 + [-1.0] * 10)
    stark = np.array([True] * 10 + [False] * 10)
    assert mr.zufall_p(r, stark, 2000, 1) < 0.01
    assert mr.zufall_p(r, ~stark, 2000, 1) > 0.99
    assert mr.zufall_p(r, stark, 500, 7) == mr.zufall_p(r, stark, 500, 7)
