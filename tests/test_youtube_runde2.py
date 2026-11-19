"""Zweite YouTube-Runde vom 19.11.2026: Siegel, Varianten und die neuen Regeln auf erfundenen Kerzen. Ohne Kursdaten."""
import numpy as np
import pandas as pd
import pytest
import yaml

from suche import youtube_runde2 as y2
from suche.runde1 import journal_lines, last_value, sha256_text


def cfg():
    return yaml.safe_load(y2.VORAB.read_text(encoding="utf-8"))["youtube_runde2"]


def test_siegel_passt():
    assert last_value(journal_lines(), y2.KEY) == sha256_text(y2.VORAB.read_text(encoding="utf-8"))


def test_fuenf_varianten_mit_bekannten_regeln():
    c = cfg()
    assert len(c["varianten"]) == 5
    for v in c["varianten"].values():
        assert v["regel"] in ("supertrend", "bollinger_rsi", "nr7", "silver_bullet")


def test_supertrend_dreht_mit_dem_kurs():
    # 60 Kerzen steigend, dann 60 fallend: genau ein Wechsel nach unten, und zwar erst nach dem Hoch.
    c = np.r_[np.linspace(100, 160, 60), np.linspace(159, 100, 60)]
    h, l = c + 1, c - 1
    tr = np.r_[np.nan, np.fmax(h[1:] - l[1:], np.fmax(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))]
    atr = pd.Series(tr).ewm(alpha=0.1, adjust=False, min_periods=10).mean().to_numpy()
    richtung, linie = y2.supertrend(h, l, c, atr, 3.0)
    gueltig = richtung[np.isfinite(atr)]
    wechsel = np.flatnonzero(gueltig[1:] != gueltig[:-1])
    assert len(wechsel) == 1 and gueltig[-1] == -1
    assert int(np.flatnonzero(np.isfinite(atr))[0] + wechsel[0] + 1) > 60
    i = np.flatnonzero(richtung > 0)[-1]
    assert linie[i] < c[i]                                     # im Aufwärtstrend liegt die Linie unter dem Kurs


def test_rsi_grenzen():
    assert y2._rsi(np.linspace(1, 50, 60), 14)[-1] == pytest.approx(100.0)
    assert y2._rsi(np.linspace(50, 1, 60), 14)[-1] == pytest.approx(0.0)


def markt(tmp_path, t, preise, spanne):
    """Erfundener Markt (nicht Krypto): 5-Minuten-Kerzen zu den Zeiten t (UTC), Hoch und Tief = Kurs +/- spanne."""
    p, sp = np.asarray(preise, float), np.asarray(spanne, float)
    ny = t.tz_localize("UTC").tz_convert(y2.NY).tz_localize(None)
    tag = (ny + pd.Timedelta(hours=7)).normalize()
    np.savez(tmp_path / "EURUSD.npz", t=t.values.astype("datetime64[ns]"), o=p, h=p + sp, l=p - sp, c=p,
             sp=np.full(len(p), 0.0001), nymin=np.asarray(ny.hour * 60 + ny.minute, np.int32),
             tag=tag.values.astype("datetime64[D]"), prof=np.full(96, 0.0001))
    c = cfg()
    c["trend"]["vorlauf_tage"] = 1
    return y2.Markt("EURUSD", tmp_path, c), c


def handelszeiten(von, bis):
    t = pd.date_range(von, bis, freq="5min", inclusive="left")
    ny = t.tz_localize("UTC").tz_convert(y2.NY)
    offen = (ny.weekday < 4) | ((ny.weekday == 4) & (ny.hour < 17)) | ((ny.weekday == 6) & (ny.hour >= 17))
    pause = ny.hour == 17
    return t[offen & ~pause]


def test_nr7_kauft_ueber_dem_ruhigen_tag(tmp_path):
    # Januar 2025: Spanne je Tag 0,0040, am NR7-Tag (Montag 13.01.) nur 0,0010. Am Dienstag steigt der Kurs.
    t = handelszeiten("2025-01-01 00:00", "2025-01-18 00:00")
    ny = t.tz_localize("UTC").tz_convert(y2.NY).tz_localize(None)
    tag = (ny + pd.Timedelta(hours=7)).normalize()
    preise = np.full(len(t), 1.0300)
    spanne = np.where(tag == pd.Timestamp("2025-01-13"), 0.0005, 0.0020)
    spanne = np.where(tag == pd.Timestamp("2025-01-14"), 0.0003, spanne)   # Einstiegstag ruhig, keine Kerze berührt beide
    preise = np.where(ny >= pd.Timestamp("2025-01-14 04:00"), 1.0320, preise)
    m, c = markt(tmp_path, t, preise, spanne)
    sig = [s for s in y2.regel_nr7(m, c) if pd.Timestamp(m.t[s["i0"]]) < pd.Timestamp("2025-01-15")]
    assert len(sig) == 1
    s = sig[0]
    assert s["d"] == 1 and s["lvl"] == pytest.approx(1.0305) and s["sd"] == pytest.approx(0.0010)
    assert pd.Timestamp(m.t[s["i0"]]) == pd.Timestamp("2025-01-14 09:00")   # 04:00 New York
    assert pd.Timestamp(s["t_max"]) == pd.Timestamp("2025-01-15 21:55")     # 16:55 New York am Folgetag


def test_silver_bullet_erste_luecke_im_fenster(tmp_path):
    # Mittwoch 15.01.2025, 10:00 bis 11:00 New York = 15:00 bis 16:00 UTC. Sprung nach oben um 10:10.
    t = handelszeiten("2025-01-15 12:00", "2025-01-15 20:00")
    ny = t.tz_localize("UTC").tz_convert(y2.NY).tz_localize(None)
    preise = np.where(ny >= pd.Timestamp("2025-01-15 10:10"), 1.0350, 1.0300)
    m, c = markt(tmp_path, t, preise, np.full(len(t), 0.0005))
    sig = y2.regel_silver_bullet(m, c)
    assert len(sig) == 1
    s = sig[0]
    assert s["d"] == 1
    assert pd.Timestamp(m.t[s["i0"]]) == pd.Timestamp("2025-01-15 15:15")   # Kerze nach der dritten (10:15 New York)
    assert s["sd"] == pytest.approx(1.0350 - 1.0295) and s["zd"] == pytest.approx(2 * s["sd"])
    assert pd.Timestamp(s["t_max"]) == pd.Timestamp("2025-01-15 17:00")     # 12:00 New York


def test_bollinger_kauft_unter_dem_band(tmp_path):
    # Ruhiger Kurs mit kleinem Zickzack, dann fällt er in einer Stunde stark: Kauf, Ziel ist die Mitte des Bands.
    t = handelszeiten("2025-01-06 00:00", "2025-01-17 00:00")
    n = len(t)
    preise = 1.0300 + 0.0002 * np.sin(np.arange(n) / 3.0)
    fall = (t >= pd.Timestamp("2025-01-15 10:00")) & (t < pd.Timestamp("2025-01-15 11:00"))
    preise = np.where(fall, 1.0300 - 0.0005 * (np.arange(n) - np.flatnonzero(fall)[0] + 1), preise)
    preise = np.where(t >= pd.Timestamp("2025-01-15 11:00"), preise[fall][-1], preise)
    m, c = markt(tmp_path, t, preise, np.full(n, 0.0001))
    sig = [s for s in y2.regel_bollinger(m, c) if pd.Timestamp(m.t[s["i0"]]) == pd.Timestamp("2025-01-15 11:00")]
    assert len(sig) == 1
    s = sig[0]
    assert s["d"] == 1 and s["zd"] > 0 and s["sd"] > 0
    assert pd.Timestamp(s["t_max"]) == pd.Timestamp("2025-01-16 11:00")
