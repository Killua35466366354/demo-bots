"""Rechenkern des Scalping-Tests (suche/scalping.py): Spread, Stop vor Ziel, Kurslücke, Haltekosten, Kalender."""
import numpy as np
import pandas as pd

from suche import scalping as sc


def markt(kerzen, spread=1.0, start="2026-03-02 14:00"):
    idx = pd.date_range(start, periods=len(kerzen), freq="5min")
    df = pd.DataFrame(kerzen, columns=["open", "high", "low", "close"], index=idx)
    return sc.Markt("TEST", df, spread)


def test_long_ohne_stop_zahlt_den_spread_in_prozent():
    m = markt([(100, 100, 100, 100), (100, 100, 100, 100), (101, 101, 101, 101)])
    t = sc.trade(m, 0, 2, 1)
    # kauft zu 101 (Ask), verkauft zu 101 (Bid): 0 %
    assert abs(t["r"]) < 1e-12 and t["grund"] == "zeit"
    s = sc.trade(m, 0, 2, -1)
    # verkauft zu 100 (Bid), kauft zu 102 (Ask) zurück: -2 %
    assert abs(s["r"] - (-2.0)) < 1e-9


def test_stop_geht_vor_dem_ziel_in_derselben_kerze():
    m = markt([(100, 100, 100, 100), (100, 120, 80, 100), (100, 100, 100, 100)], spread=0.0)
    t = sc.trade(m, 0, 2, 1, stop=90, ziel=110)
    assert t["grund"] == "stop" and abs(t["r"] - (-1.0)) < 1e-9


def test_kursluecke_ueber_den_stop_zaehlt_die_eroeffnung():
    m = markt([(100, 101, 99, 100), (85, 86, 84, 85), (85, 85, 85, 85)], spread=0.0)
    t = sc.trade(m, 0, 2, 1, stop=90)
    assert t["grund"] == "stop" and abs(t["r"] - (-1.5)) < 1e-9


def test_kein_trade_wenn_einstieg_schon_jenseits_des_stops():
    m = markt([(100, 100, 100, 100), (100, 100, 100, 100)], spread=0.0)
    assert sc.trade(m, 0, 1, 1, stop=100) is None
    assert sc.trade(m, 0, 1, -1, stop=100) is None


def test_short_stop_und_ziel_auf_der_ask_seite():
    # Short zu 100 (Bid), Ask = Bid + 1. Ziel 95 wird erst bei Bid-Tief 94 (Ask 95) erreicht.
    m = markt([(100, 100, 100, 100), (99, 99, 95, 96), (96, 96, 94, 95), (95, 95, 95, 95)], spread=1.0)
    t = sc.trade(m, 0, 3, -1, stop=110, ziel=95)
    assert t["grund"] == "ziel" and abs(t["r"] - 0.5) < 1e-9


def test_gegenrichtung_mit_gleichen_abstaenden():
    m = markt([(100, 100, 100, 100), (100, 103, 100, 103), (103, 103, 103, 103)], spread=0.0)
    t = sc.trade(m, 0, 2, -1, stop=102, ziel=96)
    assert t["grund"] == "stop"
    g = sc.trade(m, 0, 2, 1, stop_abstand=t["r_dist"], ziel_abstand=t["ziel_dist"])
    assert g["grund"] == "zeit" and abs(g["r"] - 1.5) < 1e-9


def test_haltekosten_je_nacht_ueber_22_uhr_utc():
    assert sc.naechte(pd.Timestamp("2026-03-02 18:00"), pd.Timestamp("2026-03-03 00:55")) == 1
    assert sc.naechte(pd.Timestamp("2026-03-02 23:00"), pd.Timestamp("2026-03-03 00:55")) == 0
    assert sc.naechte(pd.Timestamp("2026-03-06 20:55"), pd.Timestamp("2026-03-09 14:25")) == 3


def test_gotobi_tage_und_wochenende():
    tage = sc.gotobi_tage("2026-01-01", "2026-01-31")
    # 05.01. Mo, 10.01. Sa -> 09.01., 15.01. Do, 20.01. Di, 25.01. So -> 23.01., letzter Wochentag 30.01.
    for d in ("2026-01-05", "2026-01-09", "2026-01-15", "2026-01-20", "2026-01-23", "2026-01-30"):
        assert pd.Timestamp(d) in tage
    assert pd.Timestamp("2026-01-10") not in tage


def test_ism_nie_am_ersten_januar():
    tage = sc.ism_tage("2026-01-01", "2026-03-31")
    assert pd.Timestamp("2026-01-02") in tage and pd.Timestamp("2026-01-01") not in tage
    assert pd.Timestamp("2026-02-02") in tage and pd.Timestamp("2026-03-02") in tage


def test_ortszeit_mit_sommerzeit():
    assert sc.ortszeit("2026-01-15", "09:30", sc.NY) == pd.Timestamp("2026-01-15 14:30")
    assert sc.ortszeit("2026-07-15", "09:30", sc.NY) == pd.Timestamp("2026-07-15 13:30")
    assert sc.ortszeit("2026-01-15", "03:00", sc.TOKIO) == pd.Timestamp("2026-01-14 18:00")


def test_zufallsvergleich_erkennt_reinen_zufall():
    rng = np.random.default_rng(1)
    tr = [{"t": pd.Timestamp("2025-06-02") + pd.Timedelta(days=i), "r": 1.0 if i % 2 else -1.0} for i in range(200)]
    v = sc.zufall_vergleich(None, tr, rng, lambda t: -t["r"])
    assert not v["bestanden"]


def test_vorab_ist_versiegelt():
    assert sc.check_vorab()["zufall_saat"] == sc.SAAT
