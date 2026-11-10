"""Markt-Bot-Test (suche/markt_bot.py): Datenfehler-Filter, echter Spread, nur-Long-Signal, Siegel."""
import numpy as np
import pandas as pd

from suche import markt_bot as mb


def kerzen(n=60, start="2026-03-02 13:00", kurs=100.0, spread=0.2):
    idx = pd.date_range(start, periods=n, freq="h")
    c = kurs + np.arange(n) * 0.1
    df = pd.DataFrame({"open_bid": c, "high_bid": c + 0.5, "low_bid": c - 0.5, "close_bid": c}, index=idx)
    for k in ("open", "high", "low", "close"):
        df[f"{k}_ask"] = df[f"{k}_bid"] + spread
    df["volume"] = 1
    df.index.name = "utc"
    return df


def test_ausreisser_kerze_faellt_weg(tmp_path):
    df = kerzen()
    df.iloc[20, df.columns.get_loc("open_bid")] = 10.0          # wie NVDA am 10.06.2024
    p = tmp_path / "TEST_HOUR.csv.gz"
    df.to_csv(p)
    sauber = mb.lade(p)
    assert len(sauber) == len(df) - 1 and df.index[20] not in sauber.index


def test_spread_kommt_aus_bid_und_ask():
    T = mb.baue_tage("TEST", kerzen(n=24 * 30))
    assert abs(T.sp - 0.2) < 1e-9 and np.allclose(T.hsp, 0.2)
    assert T.fin_long > T.fin_short > 0


def test_nur_long_hat_keine_short_signale():
    T = mb.baue_tage("TEST", kerzen(n=24 * 300))
    s = mb.signale(T)
    assert not s["markt_rs_long"].es.any()
    assert (s["markt_rs_long"].el == s["markt_rs"].el).all()


def test_eur_aktien_entscheiden_um_16_uhr_london():
    assert "SAP" in mb.EUR_AKTIEN and mb.ZEIT_EUR == ("Europe/London", 16) and mb.ZEIT_USD == ("America/New_York", 15)


def test_vorab_ist_versiegelt():
    assert mb.check_vorab()["varianten"].keys() == {"markt_rs", "markt_rs_long"}
