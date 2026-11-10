"""Prüfungen für suche/opens.py (Opens aus Kirons Strategie-Video, suche/VORAB_opens.yaml)."""
import numpy as np
import pandas as pd

from suche import opens


def _bars(start: str, tage: int, kurs=None) -> pd.DataFrame:
    idx = pd.date_range(start, periods=tage * 288, freq="5min")
    c = np.full(len(idx), 1.0) if kurs is None else np.asarray(kurs, float)
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c}, index=idx)


def test_handelstag_endet_17_uhr_new_york():
    # Winter: 17:00 New York = 22:00 UTC, Sommer: 21:00 UTC
    b = _bars("2025-01-06 21:00", 1)
    p = opens.perioden(b)
    assert p.loc["2025-01-06 21:55", "tag"] == pd.Timestamp("2025-01-06")
    assert p.loc["2025-01-06 22:00", "tag"] == pd.Timestamp("2025-01-07")
    b = _bars("2025-07-07 20:00", 1)
    p = opens.perioden(b)
    assert p.loc["2025-07-07 20:55", "tag"] == pd.Timestamp("2025-07-07")
    assert p.loc["2025-07-07 21:00", "tag"] == pd.Timestamp("2025-07-08")


def test_opens_sind_erste_kerze_der_periode():
    b = _bars("2024-12-30 00:00", 10)
    b["open"] = np.arange(len(b), dtype=float)
    p = opens.perioden(b)
    # Handelstag 2025-01-02 (Donnerstag) beginnt 2025-01-01 22:00 UTC
    zeile = p.loc["2025-01-02 12:00"]
    assert zeile["tag"] == pd.Timestamp("2025-01-02")
    erste_2025 = p[p["tag"] >= pd.Timestamp("2025-01-01")].iloc[0]
    assert zeile["o_jahr"] == erste_2025["open"] == zeile["o_monat"] == zeile["o_quartal"]
    assert zeile["o_tag"] == p.loc["2025-01-01 22:00", "open"]
    # Woche: Montag 2024-12-30 ist Handelstag der ISO-Woche, erste Kerze dieser Woche im Datensatz
    assert zeile["o_woche"] == p[p["tag"] >= pd.Timestamp("2024-12-30")].iloc[0]["open"]
    # Samstag/Sonntag-Handelstage fallen weg
    assert (pd.DatetimeIndex(p["tag"]).weekday < 5).all()


def _tag(kurse, spread=0.0, variante="tag", atr=1.0, o_jahr=0.0, o_woche=None):
    """Ein Handelstag mit 5-Min.-Kerzen ab 22:00 UTC (Winter); kurse = Liste (open, high, low, close) ab 7:00 UTC."""
    idx = pd.date_range("2025-01-06 22:00", "2025-01-07 21:55", freq="5min")
    o = kurse[0][0]
    df = pd.DataFrame({"open": o, "high": o, "low": o, "close": o}, index=idx, dtype=float)
    start = idx.get_loc(pd.Timestamp("2025-01-07 07:00"))
    for k, (op, hi, lo, cl) in enumerate(kurse):
        df.iloc[start + k] = [op, hi, lo, cl]
    df.iloc[start + len(kurse):, :] = kurse[-1][3]
    p = df.copy()
    p["tag"] = pd.Timestamp("2025-01-07")
    p["o_tag"] = o
    p["o_jahr"] = p["o_quartal"] = p["o_monat"] = o_jahr
    p["o_woche"] = o if o_woche is None else o_woche
    a = pd.Series([atr], index=[pd.Timestamp("2025-01-07")])
    return opens.simuliere(p, a, spread, [7, 20], variante)


def test_tag_long_ziel_nach_ruecklauf():
    # Long-Tag (Open 10 über Jahres-Open 0), erst 0,25 ATR hoch, dann zurück zum Tages-Open, dann +2 ATR
    t = _tag([(10, 10.3, 10, 10.3), (10.3, 10.3, 9.9, 10.0), (10, 12.1, 10, 12.0)])
    assert len(t) == 1 and t[0]["seite"] == "long" and t[0]["grund"] == "ziel" and t[0]["r"] == 2.0


def test_tag_ohne_vorlauf_kein_trade():
    t = _tag([(10, 10.2, 9.5, 9.6), (9.6, 9.7, 8.5, 8.6)])
    assert t == []


def test_stop_zaehlt_in_fuellungskerze():
    t = _tag([(10, 10.3, 10, 10.3), (10.3, 10.3, 8.9, 9.0)])
    assert len(t) == 1 and t[0]["grund"] == "stop" and t[0]["r"] == -1.0


def test_short_tag_mit_spread_und_schluss():
    # Short-Tag (Open 10 unter Jahres-Open 20), runter, zurück zum Open, dann kleiner Gewinn bis Handelsschluss
    t = _tag([(10, 10, 9.7, 9.7), (9.7, 10.0, 9.7, 9.9), (9.9, 9.9, 9.5, 9.5)], spread=0.1, o_jahr=20.0)
    assert len(t) == 1 and t[0]["seite"] == "short" and t[0]["grund"] == "schluss"
    assert abs(t[0]["r"] - (10.0 - (9.5 + 0.1)) / 1.0) < 1e-9


def test_woche_long_braucht_spread_unter_linie():
    # Wochen-Open 9, Tages-Open 10: Long-Limit bei 9, Bid-Tief 8,95 reicht bei Spread 0,1 nicht
    t = _tag([(10, 10, 8.95, 9.5), (9.5, 9.6, 9.2, 9.3)], spread=0.1, variante="woche", o_woche=9.0)
    assert t == []
    t = _tag([(10, 10, 8.85, 9.5), (9.5, 9.6, 9.2, 9.3)], spread=0.1, variante="woche", o_woche=9.0)
    assert len(t) == 1 and t[0]["seite"] == "long"


def test_zufall_p_gleiche_auswahl():
    r = np.array([1.0, -1.0] * 20)
    assert opens.zufall_p(r, 20, 99.0) < 0.01
    assert opens.zufall_p(r, 20, 0.0) == 1.0
