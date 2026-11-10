"""Tests für suche/scalping2.py (Scalping-Komitee Runde 2b).

- trade_v rechnet genau wie scalping.trade (Stop vor Ziel, Lücke über den Stop, Abstände, Swap), auf Zufallskerzen.
- 15-Min.-Kerzen aus 5-Min.-Kerzen (Eröffnung der ersten, Hoch, Tief, Schluss der letzten, Raster ab :00).
- Sitzungen und Spreads wie in VORAB_scalping2.yaml, Zufallszwilling dreht nur die Richtung, Regeln versiegelt.
"""
import numpy as np
import pandas as pd
import pytest

from suche import scalping as sc
from suche import scalping2 as s2


def _markt(n=400, saat=1, minuten=5):
    rng = np.random.default_rng(saat)
    idx = pd.date_range("2025-03-03 20:00", periods=n, freq=f"{minuten}min")
    c = 100 + np.cumsum(rng.normal(0, 0.2, n))
    o = np.r_[100.0, c[:-1]] + rng.normal(0, 0.05, n)          # mit kleinen Lücken
    h = np.maximum(o, c) + rng.uniform(0, 0.3, n)
    lo = np.minimum(o, c) - rng.uniform(0, 0.3, n)
    df = pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx)
    return sc.Markt("TEST", df, 0.02, minuten=minuten)


def _gleich(a, b):
    if a is None or b is None:
        return a is None and b is None
    return a["r"] == pytest.approx(b["r"], abs=1e-9) and a["grund"] == b["grund"] and a["d"] == b["d"]


def test_trade_v_rechnet_wie_scalping_trade():
    rng = np.random.default_rng(7)
    for saat in range(5):
        m = _markt(saat=saat)
        for _ in range(300):
            i0 = int(rng.integers(20, 300))
            ie = i0 + int(rng.integers(1, 90))
            d = int(rng.choice([1, -1]))
            aus = str(rng.choice(["open", "close"]))
            art = int(rng.integers(0, 4))
            kw = {}
            if art == 1:
                kw = {"stop": m.o[i0] - d * rng.uniform(0.05, 1.5)}
            elif art == 2:
                kw = {"stop": m.o[i0] - d * rng.uniform(0.05, 1.5), "ziel": m.o[i0] + d * rng.uniform(0.05, 2.0)}
            elif art == 3:
                kw = {"stop_abstand": rng.uniform(0.05, 1.0), "ziel_abstand": rng.uniform(0.05, 2.0)}
            a = sc.trade(m, i0, ie, d, aus, 0.03, **kw)
            b = s2.trade_v(m, i0, ie, d, aus, 0.03, **kw)
            assert _gleich(a, b), (saat, i0, ie, d, aus, kw, a, b)


def test_trade_v_stop_vor_ziel_und_luecke():
    idx = pd.date_range("2025-03-04 10:00", periods=5, freq="5min")
    df = pd.DataFrame({"open": [100, 100, 98, 99, 99], "high": [100.5, 103, 99, 99, 99],
                       "low": [99.5, 98.9, 97, 99, 99], "close": [100, 100, 98.5, 99, 99]}, index=idx, dtype=float)
    m = sc.Markt("T", df, 0.0)
    t = s2.trade_v(m, 0, 4, 1, "open", 0.0, stop=99.0, ziel=102.0)        # Kerze 1 berührt beides: Stop zählt
    assert t["grund"] == "stop" and t["r"] == pytest.approx(-1.0)
    t = s2.trade_v(m, 0, 4, 1, "open", 0.0, stop=98.5, ziel=110.0)        # Kerze 2 öffnet unter dem Stop: Eröffnung
    assert t["grund"] == "stop" and t["r"] == pytest.approx(-2 / 1.5)


def test_15_min_kerzen():
    idx = pd.date_range("2025-03-04 10:00", periods=6, freq="5min")
    df = pd.DataFrame({"open": [1, 2, 3, 4, 5, 6], "high": [10, 11, 12, 13, 14, 15], "low": [0, -1, -2, -3, -4, -5],
                       "close": [1.5, 2.5, 3.5, 4.5, 5.5, 6.5]}, index=idx, dtype=float)
    z = s2.zu_15(df)
    assert list(z.index) == [pd.Timestamp("2025-03-04 10:00"), pd.Timestamp("2025-03-04 10:15")]
    assert z.iloc[0].tolist() == [1, 12, -2, 3.5] and z.iloc[1].tolist() == [4, 15, -5, 6.5]


def test_sitzungen_und_spreads():
    assert s2.sitzung("SPXUSD")[:3] == (sc.NY, "09:30", "16:00")
    assert s2.sitzung("EURUSD")[:3] == (sc.LONDON, "08:00", "16:00")
    tz, start, schluss = s2.sitzung("JPXJPY")
    assert (start, s2.schluss_von(schluss, pd.Timestamp("2024-11-04")),
            s2.schluss_von(schluss, pd.Timestamp("2024-11-05"))) == ("09:00", "15:00", "15:30")
    sp = s2.spreads()
    assert sp["USDJPY"] == 0.012 and sp["AUDJPY"] == 0.02 and sp["CADJPY"] == 0.025 and sp["GBPNZD"] == 0.0005
    assert all(s in sp for s in s2.ALLE + s2.GOTOBI)


def test_zwilling_dreht_nur_die_richtung():
    tr = [{"t": pd.Timestamp("2025-01-01"), "d": 1, "r": 1.0, "r_gegen": -1.2, "grund": "zeit"} for _ in range(400)]
    zw = s2.zwilling(tr, np.random.default_rng(1))
    gedreht = [z for z in zw if z["d"] == -1]
    assert 150 < len(gedreht) < 250 and all(z["r"] == -1.2 for z in gedreht)
    assert all(t["d"] == 1 for t in tr)                                   # das Original bleibt unverändert


def test_vorab_ist_versiegelt():
    s2.check_vorab()
