"""Tests für suche/runde5.py (Swing auf Tageskerzen): Tageslabel, Kosten, Stops, Zufallsvergleich, ohne echte Daten."""
import numpy as np
import pandas as pd

from suche import runde5 as r5

KOSTEN = {"spread_ersatz": {"index_us": 0.0, "fx": 0.0}, "uebernacht": {"index": {"long": 0.0, "short": 0.0},
                                                                       "fx": {"long": 0.0, "short": 0.0}}}


def stunden(start: str, preise, zone_freq: str = "1h") -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(preise), freq=zone_freq)
    p = np.asarray(preise, float)
    return pd.DataFrame({"open": p, "high": p + 0.5, "low": p - 0.5, "close": p}, index=idx)


def test_tageslabel_wochenende_zaehlt_zum_montag():
    # US-Index, T = 15:00 New York. Freitag 19:00 UTC (15:00 NY, Sommerzeit) gehört noch zum Freitag,
    # Freitag 20:00 UTC und alles am Wochenende zum Montag.
    idx = pd.DatetimeIndex(["2026-06-05 18:00", "2026-06-05 19:00", "2026-06-06 12:00", "2026-06-07 22:00",
                            "2026-06-08 18:00"])
    lab = r5.tageslabel(idx, "America/New_York", 15)
    assert [str(d) for d in lab] == ["2026-06-05", "2026-06-08", "2026-06-08", "2026-06-08", "2026-06-08"]


def test_naechte_zaehlt_rollover_um_22_utc():
    t = np.datetime64
    assert r5.naechte(t("2026-06-01T20:00"), t("2026-06-02T20:00")) == 1
    assert r5.naechte(t("2026-06-01T20:00"), t("2026-06-01T21:00")) == 0
    assert r5.naechte(t("2026-06-05T20:00"), t("2026-06-08T20:00")) == 3          # Freitag bis Montag: dreifach


def test_tage_und_trade_mit_spread_und_gebuehr():
    h1 = stunden("2026-06-01 00:00", np.linspace(100, 110, 24 * 10))
    T = r5.baue_tage("EURUSD", h1, None, {"spread_ersatz": {"fx": 0.001},
                                         "uebernacht": {"fx": {"long": 36.5, "short": 0.0}}})
    assert T.klasse == "fx" and len(T.c) >= 8
    assert abs(T.sp - 0.001 * h1["close"].iloc[-1]) < 1e-9
    a20 = np.full(len(T.c), 1.0)
    tr = r5.trade(T, 0, 1, T.c[1], T.t[1], "test", 1, a20, 1.0, 1.0, False)
    erwartet = (T.c[1] - (T.c[0] + T.sp)) - 0.001 * T.c[0] * r5.naechte(T.t[0], T.t[1])
    assert abs(tr["r"] - erwartet) < 1e-9


def test_long_stop_fuellt_zum_stop_oder_zur_luecke():
    h1 = stunden("2026-06-01 00:00", [100.0] * 48)
    T = r5.baue_tage("EURUSD", h1, None, KOSTEN)
    t = 1
    T.hl, T.ho = T.hl.copy(), T.ho.copy()
    T.hl[T.i0[t] + 2] = 95.0                                  # Tief reißt den Stop bei 98
    preis, _ = r5.stop_pruefen(T, t, 1, 98.0, 1.0)
    assert preis == 98.0
    T.ho[T.i0[t] + 2] = 96.0                                  # Eröffnung schon unter dem Stop: Füllung zur Eröffnung
    preis, _ = r5.stop_pruefen(T, t, 1, 98.0, 1.0)
    assert preis == 96.0


def test_nachgezogener_stop_rueckt_nach_und_schliesst():
    # Kurs steigt zwei Monate, fällt dann stark: der nachgezogene Stop (2 ATR vom besten Schluss) schließt mit Gewinn.
    tage = list(np.linspace(100, 120, 24 * 60)) + list(np.linspace(120, 90, 24 * 5))
    T = r5.baue_tage("EURUSD", stunden("2026-03-02 00:00", tage), None, KOSTEN)
    n = len(T.c)
    el = np.zeros(n, bool)
    el[22] = True
    s = r5.Signal(el, np.zeros(n, bool), np.zeros(n, bool), np.zeros(n, bool), trail_atr=2.0)
    tr = r5.simuliere(T, s, 21)
    assert len(tr) == 1 and tr[0]["grund"] == "stop" and tr[0]["r"] > 0


def test_zwilling_ist_gespiegelt_ohne_kosten():
    T = r5.baue_tage("EURUSD", stunden("2026-03-02 00:00", np.linspace(100, 130, 24 * 40)), None, KOSTEN)
    n = len(T.c)
    el, xl = np.zeros(n, bool), np.zeros(n, bool)
    el[25], xl[30] = True, True
    s = r5.Signal(el, np.zeros(n, bool), xl, np.zeros(n, bool))
    tr = r5.simuliere(T, s, 21, mit_zwilling=True)
    assert len(tr) == 1 and abs(tr[0]["r"] + tr[0]["r_zwilling"]) < 1e-9


def test_monatswechsel_und_wochenende():
    datum = np.array(pd.bdate_range("2026-01-01", "2026-03-31").values.astype("datetime64[D]"))
    nr, rest = r5.tag_im_monat(datum)
    assert nr[0] == 1 and rest[datum.astype("datetime64[M]") == np.datetime64("2026-01")][-1] == 0
    we = r5.wochenende(datum)
    assert all(pd.Timestamp(d).day_of_week == 4 for d in datum[we])          # ohne Feiertage immer Freitag


def test_pf_und_abdeckung():
    assert r5.pf([1, -1, 2]) == 3.0
    assert r5.pf([1, 2]) == 99.0
    h1 = stunden("2020-01-01 00:00", [1.0] * (24 * 800))
    T = r5.baue_tage("EURUSD", h1, None, KOSTEN)
    assert r5.abdeckung(T, "2020-01-01", "2021-12-31", 0.85, 0)
    assert not r5.abdeckung(T, "2020-01-01", "2024-12-31", 0.85, 0)          # Daten enden zu früh
