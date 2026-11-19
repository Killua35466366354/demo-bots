"""Runde "YouTube 19.11.2026": Siegel, Varianten und die drei neuen Regeln auf erfundenen Kerzen. Ohne Kursdaten."""
import numpy as np
import pandas as pd
import pytest
import yaml

from suche import youtube_runde as yr
from suche.runde1 import journal_lines, last_value, sha256_text


def cfg():
    return yaml.safe_load(yr.VORAB.read_text(encoding="utf-8"))["youtube_runde"]


def test_siegel_passt():
    assert last_value(journal_lines(), yr.KEY) == sha256_text(yr.VORAB.read_text(encoding="utf-8"))


def test_vier_varianten_mit_bekannten_regeln():
    c = cfg()
    assert len(c["varianten"]) == 4
    for v in c["varianten"].values():
        assert v["regel"] in ("williams", "cme_luecke", "ausbruch4h", "montag")


def test_ausbruch4h_werte_wie_im_rueckblick():
    alt = yaml.safe_load(yr.rb.VORAB.read_text(encoding="utf-8"))["rueckblick"]["regeln"]["ausbruch4h"]
    neu = cfg()["regeln"]["ausbruch4h"]
    for k, v in alt.items():
        if k not in ("quelle", "regel", "abweichung"):
            assert neu[k] == v, k


def krypto_markt(tmp_path, preise, start="2025-01-03 00:00"):
    """Erfundener Krypto-Markt: 5-Minuten-Kerzen ab start (UTC), Kurs je Kerze aus preise (o = h = l = c)."""
    t = pd.date_range(start, periods=len(preise), freq="5min")
    p = np.asarray(preise, float)
    ny = t.tz_localize("UTC").tz_convert(yr.NY).tz_localize(None)
    tag = (ny + pd.Timedelta(hours=7)).normalize()
    np.savez(tmp_path / "BTCUSD.npz", t=t.values.astype("datetime64[ns]"), o=p, h=p + 1, l=p - 1, c=p,
             sp=np.full(len(p), 0.5), nymin=np.asarray(ny.hour * 60 + ny.minute, np.int32),
             tag=tag.values.astype("datetime64[D]"), prof=np.full(96, 1e-4))
    c = cfg()
    c["trend"]["vorlauf_tage"] = 1
    return yr.Markt("BTCUSD", tmp_path, c), c


def test_cme_luecke_handelt_gegen_die_luecke(tmp_path):
    # Freitag 03.01.2025: 1000 bis Samstag, am Wochenende 1020 (+2 %). Bezug Freitag 17:00 New York (22:00 UTC).
    t = pd.date_range("2025-01-03 00:00", "2025-01-13 00:00", freq="5min", inclusive="left")
    preise = np.where(t < pd.Timestamp("2025-01-04 00:00"), 1000.0, 1020.0)
    m, c = krypto_markt(tmp_path, preise)
    sig = yr.regel_cme(m, c)
    assert len(sig) == 1
    s = sig[0]
    assert s["d"] == -1                                         # Lücke nach oben: Verkauf Richtung Freitagskurs
    assert m.t[s["i0"]] == np.datetime64("2025-01-05T23:00")    # Sonntag 18:00 New York
    assert s["sd"] == pytest.approx(20.0) and s["zd"] == pytest.approx(20.0)
    assert s["t_max"] == np.datetime64("2025-01-10T22:00")      # nächster Freitag 17:00 New York


def test_kleine_luecke_kein_trade(tmp_path):
    t = pd.date_range("2025-01-03 00:00", "2025-01-13 00:00", freq="5min", inclusive="left")
    preise = np.where(t < pd.Timestamp("2025-01-04 00:00"), 1000.0, 1005.0)
    m, c = krypto_markt(tmp_path, preise)
    assert yr.regel_cme(m, c) == []


def test_montag_bereich_erster_ausbruch(tmp_path):
    # Montag 06.01.2025 schwankt zwischen 990 und 1010, am Mittwoch steigt der Kurs auf 1030.
    t = pd.date_range("2025-01-06 00:00", "2025-01-13 00:00", freq="5min", inclusive="left")
    preise = np.where(t < pd.Timestamp("2025-01-07"), np.where(np.arange(len(t)) % 2 == 0, 990.0, 1010.0), 1000.0)
    preise = np.where(t >= pd.Timestamp("2025-01-08 12:00"), 1030.0, preise)
    m, c = krypto_markt(tmp_path, preise, start="2025-01-06 00:00")
    sig = yr.regel_montag(m, c)
    assert len(sig) == 1
    s = sig[0]
    assert s["d"] == 1 and s["lvl"] == pytest.approx(1011.0)   # Montagshoch (Hoch = Kurs + 1)
    assert s["sd"] == pytest.approx((1011.0 - 989.0) / 2)
    assert s["zd"] == pytest.approx(1011.0 - 989.0)
    assert m.t[s["i0"]] == np.datetime64("2025-01-08T12:00")
    assert s["t_max"] == np.datetime64("2025-01-13T00:00")
