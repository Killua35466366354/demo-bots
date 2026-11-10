"""Tests für suche/nachpruefung_2024_26.py (Grundregel 2024 bis 2026, Kirons Wort vom 10.11.2026 17:05 UTC)."""
import pandas as pd

from suche import nachpruefung_2024_26 as np


def _z(**kw):
    z = {"trades": 150, "pf": 1.3, "robust_pf": 1.1, "h1": (1.2, 70), "h2": (1.1, 80), "j2026": (1.05, 40),
         "zufall": None}
    z.update(kw)
    return z


def test_regel_versiegelt_und_schwellen_wie_vorab():
    assert np.vorab_ok()
    t = np.VORAB.read_text(encoding="utf-8")
    assert "mindestens 100" in t and "mindestens 1,2" in t and "01.01.2024" in t
    assert (np.MIN_TRADES, np.MIN_PF, np.MIN_ROBUST, np.AB) == (100, 1.2, 1.0, pd.Timestamp("2024-01-01"))


def test_urteil():
    assert np.urteil(_z())[0]
    assert not np.urteil(_z(trades=99))[0]
    assert not np.urteil(_z(pf=1.19))[0]
    assert not np.urteil(_z(robust_pf=0.99))[0]
    assert np.urteil(_z(robust_pf=None))[0]                       # keine Spread-Probe: entfällt
    assert not np.urteil(_z(h2=(1.0, 80)))[0]
    assert not np.urteil(_z(j2026=(0.9, 20)))[0]
    assert np.urteil(_z(j2026=(0.9, 19)))[0]                      # unter 20 Trades 2026: nur Auskunft
    assert not np.urteil(_z(zufall=False))[0]


def test_vor_2024_zaehlt_nicht():
    alt = pd.Series(pd.date_range("2018-01-01", "2023-12-01", periods=200))
    neu = pd.Series(pd.date_range("2024-01-02", "2026-10-01", periods=200))
    t = pd.concat([alt, neu], ignore_index=True)
    r = pd.Series([-1.0] * 200 + [2.0 if i % 2 else -1.0 for i in range(200)])
    z = np.aus_trades("x", "y", t, r)
    assert z["trades"] == 200 and z["pf"] == 2.0 and z["bestanden"] is True
    assert z["vor_2024_auskunft"]["pf"] == 0.0                    # 2018-23 nur Verluste: lässt nicht durchfallen
