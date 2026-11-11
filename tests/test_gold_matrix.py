"""Gold-Matrix (suche/gold_matrix.py, suche/VORAB_gold_matrix.yaml): Das Rechenwerk hält sich an die versiegelte Regel,
schaut nie in die Zukunft und rechnet im Zweifel gegen den Trade. Alle Kurse hier sind erfunden."""
import numpy as np
import pandas as pd
import pytest

from suche import gold_matrix as gm

P = gm.P
MONTAG = pd.Timestamp("2026-01-05 00:00")           # Winterzeit: New York ist UTC minus 5 Stunden


# ---------- Hilfen ----------

def kerzen(o, h, lo, c, start=MONTAG) -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(o), freq="1min")
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx, dtype=float)


def ruhig(n: int, kurs: float = 100.0, start=MONTAG) -> pd.DataFrame:
    return kerzen([kurs] * n, [kurs + 1] * n, [kurs - 1] * n, [kurs] * n, start)


def handelszeiten(von: str, bis: str) -> pd.DatetimeIndex:
    idx = pd.date_range(von, bis, freq="1min", inclusive="left")
    ny = idx.tz_localize("UTC").tz_convert("America/New_York")
    zu = ((ny.weekday == 4) & (ny.hour >= 17)) | (ny.weekday == 5) | ((ny.weekday == 6) & (ny.hour < 18)) | (ny.hour == 17)
    return idx[~zu]


def zufallsmarkt(von="2025-12-28", bis="2026-01-24", seed=7, start=2000.0) -> pd.DataFrame:
    """Irrfahrt ohne jeden Vorteil, mit Wochenenden und Handelspause."""
    rng = np.random.default_rng(seed)
    idx = handelszeiten(von, bis)
    weg = start * np.exp(np.cumsum(rng.normal(0, 0.00016, (len(idx), 4)).reshape(-1))).reshape(len(idx), 4)
    o = np.r_[start, weg[:-1, 3]]
    return pd.DataFrame({"open": o, "high": np.maximum(weg.max(axis=1), o), "low": np.minimum(weg.min(axis=1), o),
                         "close": weg[:, 3]}, index=idx).round(2)


def fremdmarkt(idx1: pd.DatetimeIndex, seed: int, start: float) -> pd.DataFrame:
    idx = idx1[idx1.minute % 5 == 0]
    c = start * np.exp(np.cumsum(np.random.default_rng(seed).normal(0, 0.0003, len(idx))))
    o = np.r_[start, c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c), "low": np.minimum(o, c), "close": c}, index=idx)


def voller_markt(gold: pd.DataFrame, termine=()) -> gm.Markt:
    fremd = {n: fremdmarkt(gold.index, 100 + i, s) for i, (n, s) in enumerate(
        [("EURUSD", 1.1), ("USDJPY", 140.0), ("GBPUSD", 1.25), ("USDCAD", 1.35), ("USDCHF", 0.9), ("XAGUSD", 24.0),
         ("SPXUSD", 4500.0)])}
    tage = pd.bdate_range(gold.index[0] - pd.Timedelta(days=30), gold.index[-1])
    werte = 1.5 + np.cumsum(np.random.default_rng(5).normal(0, 0.03, len(tage)))
    return gm.markt(gold, fremd, (tage.values.astype("datetime64[D]"), werte),
                    np.array(list(termine), dtype="datetime64[ns]"))


@pytest.fixture(scope="module")
def zm() -> gm.Markt:
    return voller_markt(zufallsmarkt(), [np.datetime64("2026-01-09T13:30"), np.datetime64("2026-01-14T13:30")])


def trade(o, h, lo, c, e=0, d=1, dist=5.0, modus=0, zahl=1.0, sp=0.5, halte=10 ** 9, tmin=None, sess=None, lcx=None,
          atrx=None, tiefx=None, hochx=None, lagex=None, stx=None):
    """Der Kern mit erfundenen Feldern. Ohne Angabe ist jede Minute zugleich eine Kerze der Ausstiegs-Ebene."""
    n = len(o)
    f = lambda x: np.asarray(x, float)
    nan = np.full(n, np.nan)
    return gm._trade(e, d, float(dist), modus, float(zahl), float(sp), halte, f(o), f(h), f(lo), f(c),
                     np.arange(n, dtype=np.int64) if tmin is None else np.asarray(tmin, np.int64),
                     np.zeros(n, np.int64) if sess is None else np.asarray(sess, np.int64),
                     np.arange(-1, n - 1, dtype=np.int64) if lcx is None else np.asarray(lcx, np.int64),
                     nan if atrx is None else f(atrx), nan if tiefx is None else f(tiefx),
                     nan if hochx is None else f(hochx), np.zeros(n, np.int8) if lagex is None else np.asarray(lagex, np.int8),
                     np.zeros(n, np.int8) if stx is None else np.asarray(stx, np.int8))


# ---------- Die Regeldatei und der Code sagen dasselbe ----------

def test_zahl_der_zellen_und_varianten_wie_festgelegt():
    assert len(gm.zellen()) == P["zellen"] == 305
    assert gm.zahl_varianten() == P["varianten"] == 54375
    assert len(P["einstiege"]) == 13 and gm.FILTER == ["ohne", "trend_hoch", "dollar_wind", "realzins", "news_richtung"]
    assert [len(gm.stop_liste(e)) for e in gm.EINSTIEGS_EBENEN] == [9, 9, 9, 9, 6]
    assert [len(gm.ausstieg_liste(e)) for e in gm.EINSTIEGS_EBENEN] == [24, 24, 24, 19, 14]
    assert "1d" not in {eb for p in P["einstiege"].values() for eb in p["zeitebenen"]}


def test_stop_und_ausstieg_duerfen_von_hoeheren_ebenen_kommen():
    assert [s for s, _, _ in gm.stop_liste("5m")] == ["atr1_5m", "atr2_5m", "swing_5m", "atr1_15m", "atr2_15m", "swing_15m",
                                                      "atr1_1h", "atr2_1h", "swing_1h"]
    namen = [a for a, _, _, _ in gm.ausstieg_liste("5m")]
    assert namen[:3] == ["ziel_1r", "ziel_2r", "ziel_3r"] and namen[-1] == "tagesende"
    assert {"supertrend_5m", "supertrend_15m", "supertrend_1h", "supertrend_4h"} <= set(namen) and "supertrend_1d" not in namen
    assert {x for _, _, _, x in gm.ausstieg_liste("4h") if x} == {"4h", "1d"}


def test_feste_werte_der_regeldatei():
    assert (gm.SPREAD, gm.ROBUST, gm.SATZ_LONG, gm.SATZ_SHORT) == (0.5, 1.5, 6.5, 2.0)
    assert gm.MIN_ABSTAND == 2.5 == 5 * gm.SPREAD and gm.HALTE_MIN == 14 * 1440 and gm.LUECKE_MIN == 5
    assert (gm.HAUPT_VON, gm.HAUPT_BIS) == (pd.Timestamp("2024-01-01"), pd.Timestamp("2026-10-31"))
    assert gm.MITTE == gm.HAUPT_VON + (pd.Timestamp("2026-10-30") - gm.HAUPT_VON) / 2          # wie VORAB_gold_zonen
    a, b = P["auswahl"], P["bestaetigung"]
    assert (a["verschiebungen"], a["wertbar_min_trades"], a["finalisten_max"], a["plaetze_schnell"], a["max_je_einstieg"]) == (100, 50, 12, 6, 2)
    assert (b["verschiebungen"], b["min_rang_pct"], b["holm_alpha"], b["min_z"]) == ("alle", 95, 0.05, 3.0)
    assert (gm.SPERRE_TAGE, gm.ZW_ATR) == (60, 14) and "seed" not in P["zwilling"]              # es wird nicht gewürfelt


def test_ohne_siegel_wird_nicht_gerechnet(monkeypatch):
    monkeypatch.setattr(gm, "vorab_ok", lambda: False)
    with pytest.raises(SystemExit):
        gm.main(["auswahl", "daten", "arbeit"])


def test_bestaetigung_erst_nach_dem_siegel_der_finalisten(monkeypatch):
    monkeypatch.setattr(gm, "vorab_ok", lambda: True)
    monkeypatch.setattr(gm, "finalisten_ok", lambda: False)
    with pytest.raises(SystemExit):
        gm.main(["bestaetigung", "daten", "arbeit"])


# ---------- Uhr und Kerzen ----------

def test_histdata_uhr_wird_echte_utc():
    # Winter: "plus 5 Stunden" stimmt schon. Sommer: Die Projekt-Spalte geht 1 Stunde nach.
    got = gm.echte_utc(pd.DatetimeIndex(["2026-01-15 13:30", "2026-07-01 13:30", "2026-10-26 13:30"]))
    assert list(got) == [pd.Timestamp("2026-01-15 13:30"), pd.Timestamp("2026-07-01 12:30"), pd.Timestamp("2026-10-26 13:30")]


def test_kerzen_aus_minuten_und_letzte_fertige_kerze():
    n = 180
    c = 100.0 + np.arange(n) * 0.1
    m = gm.markt(kerzen(c - 0.05, c + 0.2, c - 0.3, c))
    k5, k1h = m.eb["5m"], m.eb["1h"]
    assert len(k5) == 36 and len(k1h) == 3 and list(k5.ende1[:3]) == [4, 9, 14]
    assert k5.o[1] == pytest.approx(c[5] - 0.05) and k5.c[1] == pytest.approx(c[9])
    assert k5.h[1] == pytest.approx(c[9] + 0.2) and k5.l[1] == pytest.approx(c[5] - 0.3)
    # Minute 9 gehört noch zur zweiten 5-Minuten-Kerze: fertig ist dann erst die erste. Ab Minute 10 die zweite.
    assert (k5.lc[4], k5.lc[5], k5.lc[9], k5.lc[10]) == (-1, 0, 0, 1)
    assert (k1h.lc[59], k1h.lc[60], k1h.lc[179]) == (-1, 0, 1)
    assert list(m.eb["1m"].lc[:3]) == [-1, 0, 1]


@pytest.mark.parametrize("start, grenze_4h, grenze_tag", [
    ("2026-01-05 20:00", "2026-01-05 23:00", "2026-01-05 22:00"),          # Winter: 18 Uhr New York ist 23 Uhr UTC
    ("2026-07-06 20:00", "2026-07-06 22:00", "2026-07-06 21:00"),          # Sommer: 18 Uhr New York ist 22 Uhr UTC
])
def test_4h_und_handelstag_liegen_auf_new_york(start, grenze_4h, grenze_tag):
    m = gm.markt(ruhig(300, start=pd.Timestamp(start)))
    t = pd.DatetimeIndex(m.t)
    enden_4h, enden_tag = t[m.eb["4h"].ende1], t[m.eb["1d"].ende1]
    assert pd.Timestamp(grenze_4h) - pd.Timedelta(minutes=1) in enden_4h
    assert pd.Timestamp(grenze_tag) - pd.Timedelta(minutes=1) in enden_tag
    assert m.tag[t.get_loc(pd.Timestamp(grenze_tag))] == m.tag[t.get_loc(pd.Timestamp(grenze_tag)) - 1] + 1


def test_sperren_nacht_und_termin():
    termin = np.datetime64("2026-01-05T13:30")
    m = gm.markt(ruhig(1440), termine=np.array([termin]))
    t = pd.DatetimeIndex(m.t)
    zu = set(t[m.gesperrt].strftime("%H:%M"))
    assert {"20:55", "22:00", "23:04", "13:15", "13:30", "13:45"} <= zu
    assert not {"20:54", "23:05", "13:14", "13:46", "12:00"} & zu


# ---------- Einstiege: gegen eine langsame, wörtliche Nachrechnung ----------

def wie_im_text(fam: str, o, h, lo, c, atr, tag_h=None) -> tuple[set, set]:
    """Die Regel aus der VORAB-Datei Kerze für Kerze mit Schleifen, ohne die schnellen Felder des Rechenwerks."""
    p, n = P["einstiege"][fam], len(c)
    lang, kurz = np.zeros(n, bool), np.zeros(n, bool)
    s = pd.Series(c)
    for j in range(1, n):
        if fam == "ausbruch" and j >= p["kerzen"]:
            lang[j], kurz[j] = c[j] > h[j - 20:j].max(), c[j] < lo[j - 20:j].min()
        elif fam == "fehlausbruch" and j >= p["kerzen"]:
            t, hh = lo[j - 20:j].min(), h[j - 20:j].max()
            lang[j], kurz[j] = lo[j] < t and c[j] > t, h[j] > hh and c[j] < hh
        elif fam == "schwungkerze" and not np.isnan(atr[j - 1]):
            sp = h[j] - lo[j]
            gross = sp >= 2.0 * atr[j - 1]
            lang[j] = gross and c[j] >= h[j] - 0.25 * sp and c[j] > o[j]
            kurz[j] = gross and c[j] <= lo[j] + 0.25 * sp and c[j] < o[j]
        elif fam == "rund_bruch":
            lang[j], kurz[j] = c[j] // 50 > c[j - 1] // 50, c[j] // 50 < c[j - 1] // 50
        elif fam == "rund_abprall" and not np.isnan(atr[j]):
            unten = (c[j - 1] // 50) * 50
            lang[j] = lo[j] <= unten and c[j] >= unten + 0.25 * atr[j]
            kurz[j] = h[j] >= unten + 50 and c[j] <= unten + 50 - 0.25 * atr[j]
        elif fam == "band_umkehr" and j >= 19:
            mitte, sd = c[j - 19:j + 1].mean(), c[j - 19:j + 1].std()
            lang[j], kurz[j] = c[j] < mitte - 2.5 * sd, c[j] > mitte + 2.5 * sd
    if fam in ("ausbruch", "band_umkehr"):                       # frisch
        lang, kurz = lang & ~np.r_[False, lang[:-1]], kurz & ~np.r_[False, kurz[:-1]]
    if fam == "ema_kreuz":
        a, b = s.ewm(span=9, adjust=False).mean().to_numpy(), s.ewm(span=21, adjust=False).mean().to_numpy()
        for j in range(21, n):
            lang[j], kurz[j] = a[j] > b[j] and a[j - 1] <= b[j - 1], a[j] < b[j] and a[j - 1] >= b[j - 1]
    beide = lang & kurz
    return set(np.flatnonzero(lang & ~beide)), set(np.flatnonzero(kurz & ~beide))


@pytest.mark.parametrize("fam", ["ausbruch", "fehlausbruch", "schwungkerze", "rund_bruch", "rund_abprall", "band_umkehr",
                                 "ema_kreuz"])
@pytest.mark.parametrize("ebene", ["5m", "15m"])
def test_einstieg_wie_im_text_der_regel(zm, fam, ebene):
    k = zm.eb[ebene]
    lang, kurz = gm.roh_signale(zm, fam, ebene)
    soll_l, soll_k = wie_im_text(fam, k.o, k.h, k.l, k.c, gm.ind(k, "atr", 14))
    ab = 30                                                       # Einlauf der Indikatoren
    assert {j for j in np.flatnonzero(lang) if j >= ab} == {j for j in soll_l if j >= ab}
    assert {j for j in np.flatnonzero(kurz) if j >= ab} == {j for j in soll_k if j >= ab}
    assert len(soll_l) + len(soll_k) > 5


def mit_ausbruch(start=MONTAG) -> pd.DataFrame:
    """240 ruhige Minuten. Die 5-Minuten-Kerze 155 bis 159 schließt bei 102 über dem Hoch 101 der 20 Kerzen davor."""
    df = ruhig(240, start=start)
    df.iloc[159, :] = [100.0, 102.5, 99.5, 102.0]
    df.iloc[160:165, :] = [102.0, 102.4, 101.5, 102.2]           # die nächste schließt auch hoch, aber unter 102,5
    return df


def test_ausbruch_handelt_zur_naechsten_minute_und_ist_frisch():
    m = gm.markt(mit_ausbruch())
    e, d = gm.einstiege(m, "ausbruch", "5m")
    assert list(e) == [160] and list(d) == [1]
    lang, kurz = gm.roh_signale(m, "ausbruch", "5m")
    assert list(np.flatnonzero(lang)) == [31] and not kurz.any()


def test_signal_verfaellt_nach_luecke_und_in_der_sperre():
    df = mit_ausbruch()
    luecke = df.drop(df.index[160:170])                           # nach der Signalkerze fehlen 10 Minuten
    assert len(gm.einstiege(gm.markt(luecke), "ausbruch", "5m")[0]) == 0
    kurze_luecke = df.drop(df.index[160:164])                     # 4 Minuten fehlen: Einstieg zur Minute 164
    assert list(gm.einstiege(gm.markt(kurze_luecke), "ausbruch", "5m")[0]) == [160]
    assert gm.markt(kurze_luecke).t[160] == df.index[164].to_datetime64()
    nacht = mit_ausbruch(start=pd.Timestamp("2026-01-05 18:20"))  # Signalkerze endet 20:59, Einstieg wäre 21:00 UTC
    assert len(gm.einstiege(gm.markt(nacht), "ausbruch", "5m")[0]) == 0
    termin = np.array([np.datetime64("2026-01-05T02:50")])        # Einstieg 02:40 liegt in den 15 Minuten vor dem Termin
    assert len(gm.einstiege(gm.markt(df, termine=termin), "ausbruch", "5m")[0]) == 0


def test_ruecksetzer_nur_im_aufwaertstrend(zm):
    k = zm.eb["1m"]
    lang, kurz = gm.roh_signale(zm, "ruecksetzer", "1m")
    e50, e200, rsi = gm.ind(k, "ema", 50), gm.ind(k, "ema", 200), gm.ind(k, "rsi", 2)
    j = np.flatnonzero(lang)
    assert len(j) > 20 and (e50[j] > e200[j]).all() and (k.c[j] > e200[j]).all() and (rsi[j] < 10).all()
    assert not (((e50[j - 1] > e200[j - 1]) & (k.c[j - 1] > e200[j - 1]) & (rsi[j - 1] < 10))).any()      # frisch
    j = np.flatnonzero(kurz)
    assert len(j) > 20 and (e50[j] < e200[j]).all() and (rsi[j] > 90).all()


def test_rsi_und_atr_nach_wilder():
    c = np.array([10, 11, 12, 11, 10, 9, 10, 11, 12, 13, 12, 13, 14, 13, 12, 13.0])
    r = gm.rsi_wilder(c, 2)
    auf = ab = 0.0
    for i in range(1, len(c)):
        d = c[i] - c[i - 1]
        auf, ab = auf + (max(d, 0) - auf) / 2, ab + (max(-d, 0) - ab) / 2
    assert r[-1] == pytest.approx(100 - 100 / (1 + auf / ab))
    from suche.gold_zonen import atr_wilder
    h, lo = c + 1.0, c - 0.5
    np.testing.assert_allclose(gm.atr_wilder(h, lo, c, 14), atr_wilder(h, lo, c, 14), equal_nan=True)


def test_enge_ausbruch_braucht_enge_baender():
    zacken = np.where(np.arange(190) % 2 == 0, 1.0, -1.0)
    c = np.r_[100 + zacken[:150], 100 + 0.05 * zacken[150:], 101.5, 101.6, 101.7]     # erst weit, dann 40 Kerzen eng, dann Ausbruch
    m = gm.markt(kerzen(c, c + 0.01, c - 0.01, c))
    lang, kurz = gm.roh_signale(m, "enge_ausbruch", "1m")
    assert list(np.flatnonzero(lang)) == [190] and not kurz.any()   # nur die erste Kerze über dem Band
    weit = np.r_[100 + zacken, 103.5, 103.6, 103.7]                 # derselbe Ausbruch ohne enge Bänder davor
    lang2, _ = gm.roh_signale(gm.markt(kerzen(weit, weit + 0.01, weit - 0.01, weit)), "enge_ausbruch", "1m")
    assert not lang2.any()


def test_pivot_abprall_nimmt_den_letzten_fertigen_handelstag():
    start = pd.Timestamp("2026-01-05 23:00")                     # Montag 18 Uhr New York: Beginn eines Handelstags
    idx = handelszeiten("2026-01-05 23:00", "2026-01-07 12:00")
    df = pd.DataFrame({"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0}, index=idx)
    df.loc[start + pd.Timedelta(hours=3), ["high"]] = 104.0      # Tag 1: Hoch 104, Tief 98, Schluss 100
    df.loc[start + pd.Timedelta(hours=5), ["low"]] = 98.0
    piv = (104.0 + 98.0 + 100.0) / 3
    s1 = 2 * piv - 104.0                                         # 97,33
    tag2 = pd.Timestamp("2026-01-06 23:00")
    df.loc[tag2 + pd.Timedelta(hours=2), ["low", "close"]] = [s1 - 0.3, 99.0]      # Tag 2 berührt S1 und schließt darüber
    m = gm.markt(df)
    lang, kurz = gm.roh_signale(m, "pivot_abprall", "1m")
    assert list(pd.DatetimeIndex(m.t)[lang]) == [tag2 + pd.Timedelta(hours=2)] and not kurz.any()
    # Am ersten Tag gibt es noch keinen fertigen Vortag, also auch kein Signal, egal was der Kurs macht
    df.loc[start + pd.Timedelta(hours=1), ["low"]] = 90.0
    lang2, _ = gm.roh_signale(gm.markt(df), "pivot_abprall", "1m")
    assert not lang2[:1000].any()


def test_fremdkurs_nur_fertig_und_frisch():
    gold = ruhig(60)
    fr = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": [1.0, 1.1, 1.2]},
                      index=pd.DatetimeIndex(["2026-01-05 00:00", "2026-01-05 00:05", "2026-01-05 00:10"]))
    m = gm.markt(gold, {"XAGUSD": fr})
    x = gm.fremd_auf(m, "XAGUSD", "5m")
    # Gold-Kerze 00:00 bis 00:04 schließt um 00:05: Dann ist die Silber-Kerze von 00:00 fertig, die von 00:05 noch nicht.
    assert x[0] == 1.0 and x[1] == 1.1 and x[2] == 1.2
    assert x[5] == 1.2 and np.isnan(x[6])                        # 00:30 ist sie 15 Minuten alt, 00:35 zu alt


def test_dollar_nachlauf_long_wenn_der_dollar_faellt(zm):
    k = zm.eb["5m"]
    lang, kurz = gm.roh_signale(zm, "dollar_nachlauf", "5m")
    zd, _ = gm.z_wert(gm.dollar_korb(zm, "5m"), 12, 500)
    zg, _ = gm.z_wert(np.log(k.c), 12, 500)
    assert lang.sum() > 3 and kurz.sum() > 3
    assert (zd[lang] <= -1.5).all() and (zg[lang] <= 0.5).all() and (zd[kurz] >= 1.5).all() and (zg[kurz] >= -0.5).all()
    korb = sum(w * np.log(gm.fremd_auf(zm, n, "5m")) for n, w in P["fremdkurse"]["gewichte"].items())
    np.testing.assert_allclose(gm.dollar_korb(zm, "5m"), korb, equal_nan=True)
    assert P["fremdkurse"]["gewichte"]["EURUSD"] < 0 < P["fremdkurse"]["gewichte"]["USDJPY"]


@pytest.mark.parametrize("fam, ebene", [(f, e) for f, p in P["einstiege"].items() for e in p["zeitebenen"]])
def test_jeder_einstieg_rechnet_und_gibt_beide_richtungen_nie_zugleich(zm, fam, ebene):
    lang, kurz = gm.roh_signale(zm, fam, ebene)
    assert len(lang) == len(zm.eb[ebene]) and not (lang & kurz).any()
    e, d = gm.einstiege(zm, fam, ebene)
    assert (np.diff(e) > 0).all() and set(np.unique(d)) <= {-1, 1}
    assert not zm.gesperrt[e].any() and not zm.nach_luecke[e].any()


# ---------- Kein Blick in die Zukunft ----------

def test_nichts_aendert_sich_wenn_die_zukunft_fehlt():
    gold = zufallsmarkt()
    termine = [np.datetime64("2026-01-09T13:30"), np.datetime64("2026-01-14T13:30")]
    voll = voller_markt(gold, termine)
    schnitt = gold.index[len(gold) * 2 // 3]
    kurz = voller_markt(gold[gold.index < schnitt], termine)
    nk = len(kurz)
    geprueft = 0
    for fam, p in P["einstiege"].items():
        for eb in p["zeitebenen"]:
            ev, dv = gm.einstiege(voll, fam, eb)
            ek, dk = gm.einstiege(kurz, fam, eb)
            ok = ev < nk
            assert list(ev[ok]) == list(ek) and list(dv[ok]) == list(dk), (fam, eb)
            for flt in gm.FILTER:
                assert (gm.filter_maske(voll, flt, eb, ek, dk) == gm.filter_maske(kurz, flt, eb, ek, dk)).all(), (fam, eb, flt)
            for _, art, seb in gm.stop_liste(eb):
                np.testing.assert_array_equal(gm.stop_abstand(voll, art, seb, ek, dk), gm.stop_abstand(kurz, art, seb, ek, dk))
            geprueft += len(ek)
    assert geprueft > 2000
    for eb in gm.LEITER:                                          # Felder der Ausstiege: jede fertige Kerze ist gleich
        fv, fk = gm.x_felder(voll, eb), gm.x_felder(kurz, eb)
        fertig = len(kurz.eb[eb]) - 1
        np.testing.assert_array_equal(fv[0][:nk], fk[0])
        for a, b in zip(fv[1:], fk[1:]):
            np.testing.assert_array_equal(a[:fertig], b[:fertig])


def test_trades_gleich_solange_sie_vor_dem_schnitt_enden():
    gold = zufallsmarkt()
    voll = voller_markt(gold)
    kurz = voller_markt(gold[gold.index < gold.index[len(gold) * 2 // 3]])
    f = {"einstieg": "ausbruch", "ebene": "5m", "filter": "trend_hoch", "stop": "atr2_15m", "ausstieg": "trail_atr_1h"}
    tv, tk = gm.trades_von(voll, f, "2026-01-01", "2026-02-01"), gm.trades_von(kurz, f, "2026-01-01", "2026-02-01")
    fertig = tk[tk["grund"] != "datenende"]
    assert len(fertig) >= 10
    pd.testing.assert_frame_equal(tv.iloc[:len(fertig)].reset_index(drop=True), fertig.reset_index(drop=True))


# ---------- Filter ----------

def test_trend_filter_sieht_nur_fertige_kerzen_der_hoeheren_ebene(zm):
    e, d = gm.einstiege(zm, "ema_kreuz", "5m")
    ok = gm.filter_maske(zm, "trend_hoch", "5m", e, d)
    k = zm.eb["1h"]
    em = gm.ind(k, "ema", 50)
    assert 0 < ok.sum() < len(e)
    for i in np.flatnonzero(ok)[:50]:
        q = k.lc[e[i]]
        assert k.ende1[q] < e[i] and (q + 1 >= len(k) or k.ende1[q + 1] >= e[i])
        assert d[i] * (k.c[q] - em[q]) > 0 and d[i] * (em[q] - em[q - 5]) > 0


def test_realzins_filter_wartet_zwei_tage():
    m = gm.markt(ruhig(600, start=pd.Timestamp("2026-01-14 08:00")),
                 realzins=(np.arange("2026-01-01", "2026-01-15", dtype="datetime64[D]"),
                           np.r_[np.linspace(2.0, 1.0, 12), 5.0, 9.0]))            # bis 12.01. fallend, am 13. und 14. Sprung
    e, lang, kurz = np.array([10]), np.array([1]), np.array([-1])
    # Einstieg am 14.01.: Es zählt der Wert vom 12.01. gegen den 5 Werte davor. Der Sprung vom 13.01. ist noch unbekannt.
    assert gm.filter_maske(m, "realzins", "5m", e, lang)[0] and not gm.filter_maske(m, "realzins", "5m", e, kurz)[0]


def test_news_filter_richtung_und_fenster():
    termin = pd.Timestamp("2026-01-06 13:30")
    idx = pd.date_range("2026-01-05 00:00", "2026-01-08 00:00", freq="1min", inclusive="left")
    c = np.where(idx < termin, 100.0, 110.0)                     # Gold springt zum Termin um 10 USD nach oben
    df = pd.DataFrame({"open": c, "high": c + 0.5, "low": c - 0.5, "close": c}, index=idx)
    m = gm.markt(df, termine=np.array([termin.to_datetime64()]))
    assert list(gm.news_richtungen(m)) == [1]
    pos = lambda zeit: np.array([idx.get_loc(pd.Timestamp(zeit))])
    lang, kurz = np.array([1]), np.array([-1])
    f = lambda zeit, d: bool(gm.filter_maske(m, "news_richtung", "5m", pos(zeit), d)[0])
    assert not f("2026-01-06 14:29", lang) and f("2026-01-06 14:30", lang) and not f("2026-01-06 14:30", kurz)
    assert f("2026-01-07 13:29", lang) and not f("2026-01-07 13:30", lang) and not f("2026-01-06 12:00", lang)
    # Ein Weg unter 0,5 ATR gibt keine Richtung
    flach = pd.DataFrame({"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0}, index=idx)
    assert list(gm.news_richtungen(gm.markt(flach, termine=np.array([termin.to_datetime64()])))) == [0]


def test_dollar_wind_filter(zm):
    e, d = gm.einstiege(zm, "ausbruch", "5m")
    ok = gm.filter_maske(zm, "dollar_wind", "5m", e, d)
    korb = gm.dollar_korb(zm, "1h")
    em = gm.ema(korb, 50)
    q = zm.eb["1h"].lc[e]
    assert 0 < ok.sum() < len(e)
    assert (d[ok] * (korb[q[ok]] - em[q[ok]]) < 0).all()         # Long nur bei schwachem Dollar


# ---------- Stops ----------

def test_stop_abstand_atr_und_swing():
    df = ruhig(260)
    df.iloc[150, :] = [100.0, 101.0, 97.0, 100.0]                # ein Tief bei 97 in den letzten 10 fertigen 5-Minuten-Kerzen
    m = gm.markt(df)
    k = m.eb["5m"]
    e, lang, kurz = np.array([170]), np.array([1]), np.array([-1])
    a = gm.ind(k, "atr", 14)[k.lc[170]]
    assert gm.stop_abstand(m, "atr1", "5m", e, lang)[0] == pytest.approx(a)
    assert gm.stop_abstand(m, "atr2", "5m", e, lang)[0] == pytest.approx(2 * a)
    assert gm.stop_abstand(m, "swing", "5m", e, lang)[0] == pytest.approx(100.0 - (97.0 - 0.1 * a))
    assert gm.stop_abstand(m, "swing", "5m", e, kurz)[0] == pytest.approx((101.0 + 0.1 * a) - 100.0)
    # Minute 259: Die letzten 10 fertigen Kerzen reichen von Minute 205 bis 254, das Tief von Minute 150 ist nicht mehr dabei.
    assert gm.stop_abstand(m, "swing", "5m", np.array([259]), lang)[0] == pytest.approx(1.0 + 0.1 * gm.ind(k, "atr", 14)[k.lc[259]])
    assert np.isnan(gm.stop_abstand(m, "atr1", "1h", np.array([30]), lang)[0])       # noch keine fertige Stunde


def test_swing_stop_mindestens_halber_und_hoechstens_vierfacher_atr():
    df = ruhig(200)
    df.iloc[150, :] = [100.0, 101.0, 60.0, 100.0]                # sehr tiefes Tief: Der Stop wird auf 4 ATR gekappt
    m = gm.markt(df)
    k = m.eb["5m"]
    a = gm.ind(k, "atr", 14)[k.lc[170]]
    assert gm.stop_abstand(m, "swing", "5m", np.array([170]), np.array([1]))[0] == pytest.approx(4 * a)
    hoch = ruhig(200)
    hoch.iloc[169, :] = [100.0, 100.0, 100.0, 100.0]
    hoch.iloc[170:, :] = [130.0, 131.0, 129.0, 130.0]            # Kurs ist weit über dem Hoch: Short-Stop wäre negativ
    m2 = gm.markt(hoch)
    a2 = gm.ind(m2.eb["5m"], "atr", 14)[m2.eb["5m"].lc[170]]
    assert gm.stop_abstand(m2, "swing", "5m", np.array([170]), np.array([-1]))[0] == pytest.approx(0.5 * a2)


# ---------- Der Kern: ein Trade ----------

def test_long_ziel_und_stop_mit_spread():
    o, c = [100.0] * 6, [100.0] * 6
    # Kauf zum Ask 100,50. Stop 95,50, Ziel 105,50 (1 R = 5 USD).
    assert trade(o, [100, 101, 105.4, 105.5, 100, 100], [100, 99, 99, 99, 99, 99], c) == (3, 105.5, 100.5, 2)
    assert trade(o, [100, 101, 102, 102, 100, 100], [100, 99, 95.6, 95.5, 99, 99], c) == (3, 95.5, 100.5, 1)
    assert trade(o, [100, 101, 102, 106, 100, 100], [100, 99, 99, 95, 99, 99], c)[3] == 1          # beides in einer Kerze: Stop
    x, kurs, fill, grund = trade([100, 100, 94.0, 100], [100, 100, 94.5, 100], [100, 100, 93, 100], [100] * 4)
    assert (x, kurs, grund) == (2, 94.0, 1)                       # Eröffnung unter dem Stop: schlechterer Kurs
    assert trade([100, 100, 107.0, 100], [100, 100, 108, 100], [100, 100, 106, 100], [100] * 4)[1] == 105.5   # Ziel nie besser


def test_stop_und_ziel_gelten_schon_in_der_einstiegskerze():
    assert trade([100, 100], [100.2, 100], [95.0, 100], [100, 100]) == (0, 95.5, 100.5, 1)
    assert trade([100, 100], [105.6, 100], [99.8, 100], [100, 100]) == (0, 105.5, 100.5, 2)


def test_short_steigt_zum_ask_aus():
    o, c = [100.0] * 5, [100.0] * 5
    # Verkauf zum Bid 100. Stop am Ask 105 (Bid-Hoch 104,5), Ziel am Ask 95 (Bid-Tief 94,5).
    assert trade(o, [100, 104.4, 104.5, 100, 100], [100, 99, 99, 99, 99], c, d=-1) == (2, 105.0, 100.0, 1)
    assert trade(o, [100, 101, 101, 101, 100], [100, 94.6, 94.5, 99, 99], c, d=-1) == (2, 95.0, 100.0, 2)
    assert trade([100, 100, 106.0], [100, 100, 107], [100, 100, 105], [100] * 3, d=-1)[:2] == (2, 106.5)   # Lücke: Ask der Eröffnung


def test_ausstieg_nach_vier_fertigen_kerzen():
    n = 40
    lcx = np.arange(n) // 5 - 1                                  # 5-Minuten-Kerzen: fertig nach jeder fünften Minute
    o = 100.0 + np.arange(n) * 0.01
    x, kurs, _, grund = trade(o, o + 0.2, o - 0.2, o, e=7, modus=1, zahl=4, lcx=lcx)
    # Einstieg in Kerze 1 (Minute 5 bis 9). Fertig werden die Kerzen 1, 2, 3, 4: die vierte mit Minute 24, raus zur Minute 25.
    assert (x, grund) == (25, 3) and kurs == pytest.approx(o[25])


def test_trail_atr_zieht_nur_nach():
    n = 30
    lcx = np.arange(n) // 5 - 1
    o = np.r_[np.full(5, 100.0), np.full(5, 110.0), np.full(5, 120.0), np.full(15, 112.0)]
    h, lo = o + 1.0, o - 1.0
    atrx = np.full(6, 2.0)
    x, kurs, fill, grund = trade(o, h, lo, o, e=0, dist=5.0, modus=2, zahl=3.0, lcx=lcx, atrx=atrx)
    # Nach Kerze 0: Hoch 101, Stop bleibt 95,5. Nach Kerze 1: Hoch 111 minus 6 = 105. Nach Kerze 2: 121 minus 6 = 115.
    # Minute 15 eröffnet bei 112 unter dem Stop 115: raus zur Eröffnung.
    assert (x, kurs, grund) == (15, 112.0, 1)
    # Short spiegelbildlich: Verkauf 100, Stop am Ask 105. Nach Kerze 1: Tief 89 plus Spread plus 6 = 95,5. Nach Kerze 2:
    # 79 plus 0,5 plus 6 = 85,5. Minute 15 eröffnet bei 88, Ask 88,5 über dem Stop: raus zum Ask der Eröffnung.
    u = np.r_[np.full(5, 100.0), np.full(5, 90.0), np.full(5, 80.0), np.full(15, 88.0)]
    assert trade(u, u + 1.0, u - 1.0, u, e=0, d=-1, dist=5.0, modus=2, zahl=3.0, lcx=lcx, atrx=atrx)[:2] == (15, 88.5)
    # Ohne fertige Kerze kein Nachziehen: Der erste Stop bleibt, auch wenn der Kurs schon weit gelaufen ist
    assert trade(o[:5], h[:5] + 30, lo[:5], o[:5], e=0, dist=5.0, modus=2, zahl=3.0, lcx=lcx[:5], atrx=atrx)[3] == 5


def test_trail_struktur_folgt_dem_tief_der_letzten_kerzen():
    n = 30
    lcx = np.arange(n) // 5 - 1
    o = np.r_[np.full(10, 100.0), np.full(10, 110.0), np.full(10, 104.0)]
    tiefx = np.array([98.5, 98.5, 98.5, 109.0, 103.0, 103.0])    # Tief der letzten Kerzen je fertiger Kerze
    x, kurs, _, grund = trade(o, o + 1, o - 1, o, e=0, dist=5.0, modus=3, lcx=lcx, tiefx=tiefx)
    # Nach Kerze 3 (Minute 15 bis 19) steigt der Stop auf 109. Minute 20 eröffnet bei 104: raus zur Eröffnung.
    assert (x, kurs, grund) == (20, 104.0, 1)
    hochx = np.array([101.5, 101.5, 101.5, 91.0, 97.0, 97.0])
    u = np.r_[np.full(10, 100.0), np.full(10, 90.0), np.full(10, 96.0)]
    # Short: Nach Kerze 3 sinkt der Stop auf Hoch 91 plus Spread. Minute 20 eröffnet bei 96: raus zum Ask 96,5.
    assert trade(u, u + 1, u - 1, u, e=0, d=-1, dist=5.0, modus=3, lcx=lcx, hochx=hochx)[:2] == (20, 96.5)


def test_ema_und_supertrend_nur_kerzen_nach_dem_einstieg():
    n = 20
    lcx = np.arange(n) // 5 - 1
    o = np.full(n, 100.0)
    gegen = np.array([-1, 1, -1, -1], dtype=np.int8)             # Kerze 0 stand schon vor dem Einstieg gegen den Trade
    for modus, feld in ((4, "lagex"), (5, "stx")):
        x, kurs, _, grund = trade(o, o + 1, o - 1, o, e=6, modus=modus, lcx=lcx, **{feld: gegen})
        # Einstieg in Kerze 1. Kerze 1 schließt dafür, Kerze 2 (fertig mit Minute 14) dagegen: raus zur Minute 15.
        assert (x, kurs, grund) == (15, 100.0, 3)
        x, _, _, _ = trade(o, o + 1, o - 1, o, e=6, d=-1, modus=modus, lcx=lcx, **{feld: gegen})
        assert x == 10                                           # Short: Kerze 1 steht dagegen


def test_tagesende_haltezeit_und_datenende():
    n = 10
    o = np.full(n, 100.0)
    sess = np.r_[np.zeros(6), np.ones(4)].astype(np.int64)
    assert trade(o, o + 1, o - 1, o, modus=6, sess=sess)[:2] == (6, 100.0)
    assert trade(o, o + 1, o - 1, o, modus=0, zahl=3.0, halte=4)[0::3] == (4, 4)
    assert trade(o, o + 1, o - 1, o + 0.3, modus=0, zahl=3.0) == (9, 100.3, 100.5, 5)
    assert trade(o, o + 1, o - 1, o + 0.3, d=-1, modus=0, zahl=3.0) == (9, 100.8, 100.0, 5)


# ---------- Ein Lauf ----------

def lauf(m: gm.Markt, e, d, dist, modus=0, zahl=1.0, xeb=None, faktor=1.0):
    return gm.rechne(m, np.asarray(e, np.int64), np.asarray(d, np.int64), np.asarray(dist, float), modus, zahl, xeb, faktor)


def test_ein_trade_gleichzeitig_und_kleine_stops_verfallen():
    o = np.full(60, 100.0)
    h, lo = o + 1.0, o - 1.0
    h[20] = 106.0                                                # Ziel des ersten Trades in Minute 20
    h[40] = 106.0
    m = gm.markt(kerzen(o, h, lo, o))
    r, aus, grund = lauf(m, [5, 10, 20, 21, 30], [1, 1, 1, 1, 1], [5.0, 5.0, 5.0, 5.0, 2.4])
    assert list(aus) == [20, -1, -1, 40, -1]                     # 10 und 20: noch im Trade. 30: Stop unter 2,50 USD
    assert r[0] == pytest.approx(1.0) and np.isnan(r[1]) and np.isnan(r[2]) and r[3] == pytest.approx(1.0) and np.isnan(r[4])
    assert list(grund) == [2, 0, 0, 2, 0]


def test_ergebnis_in_r_mit_uebernachtgebuehr():
    idx = pd.date_range("2026-01-05 12:00", "2026-01-08 12:00", freq="1min", inclusive="left")
    df = pd.DataFrame({"open": 4000.0, "high": 4001.0, "low": 3999.0, "close": 4000.0}, index=idx)
    df.iloc[-1, df.columns.get_loc("high")] = 4100.0             # Ziel erst nach drei Tagen
    m = gm.markt(df)
    r, aus, _ = lauf(m, [0], [1], [20.0], zahl=1.0)
    naechte = m.tag[aus[0]] - m.tag[0]
    assert naechte == 3                                          # dreimal 17:00 New York
    assert r[0] == pytest.approx(1.0 - 6.5 / 36500 * 3 * 4000.5 / 20.0)
    rob, _, _ = lauf(m, [0], [1], [20.0], zahl=1.0, faktor=1.5)
    assert rob[0] == pytest.approx(1.0 - 1.5 * 6.5 / 36500 * 3 * 4000.75 / 20.0)
    kurz, _, _ = lauf(m, [0], [-1], [200.0], zahl=3.0)           # Short läuft bis zum Datenende, zahlt 2 % im Jahr
    assert kurz[0] == pytest.approx(-0.5 / 200.0 - 2.0 / 36500 * 3 * 4000.0 / 200.0)


def test_robust_rechnung_ist_nie_besser(zm):
    f = {"einstieg": "fehlausbruch", "ebene": "5m", "filter": "ohne", "stop": "atr2_15m", "ausstieg": "ziel_2r"}
    tr, rob = gm.trades_von(zm, f, "2026-01-01", "2026-02-01"), gm.trades_von(zm, f, "2026-01-01", "2026-02-01", gm.ROBUST)
    assert len(tr) > 20 and rob["r"].sum() < tr["r"].sum()
    assert (tr["r_usd"] >= gm.MIN_ABSTAND).all() and (tr["zeit_aus"] >= tr["zeit"]).all()
    assert (np.diff(tr["e"]) > 0).all() and (tr["zeit"].iloc[1:].to_numpy() > tr["zeit_aus"].iloc[:-1].to_numpy()).all()


# ---------- Zwillinge: die ganze Strategie um Handelstage verschoben ----------

FENSTER = ("2026-01-01", "2026-01-20")


def einzel(m: gm.Markt, e, d, dist, sp, modus, zahl, xeb):
    """Ein Trade direkt aus dem Kern: Ergebnis in R ohne Gebühr, und die Zahl der Nächte."""
    x, kurs, fill, _ = gm._trade(int(e), int(d), float(dist), modus, float(zahl), float(sp), gm.HALTE_MIN,
                                 *gm._kern_felder(m)[:6], *gm.x_felder(m, xeb))
    return d * (kurs - fill) / dist, m.tag[x] - m.tag[e]


def test_kalender_zaehlt_handelstage_und_minuten_seit_17_uhr_new_york(zm):
    kal = gm.kalender(zm, *FENSTER)
    t = pd.DatetimeIndex(zm.t[kal.kerzen])
    ny = t.tz_localize("UTC").tz_convert("America/New_York")
    assert kal.tage == len(np.unique(zm.tag[kal.kerzen])) == 14          # 13 Werktage und die erste Stunde des 20.01.
    assert (np.diff(kal.key) > 0).all() and (np.diff(kal.kerzen) > 0).all()
    assert (kal.key % 1440 == ((ny.hour - 17) % 24) * 60 + ny.minute).all()
    assert (kal.key // 1440 == np.searchsorted(np.unique(zm.tag[kal.kerzen]), zm.tag[kal.kerzen])).all()
    assert not zm.gesperrt[kal.kerzen].any() and not zm.nach_luecke[kal.kerzen].any()
    assert (t >= pd.Timestamp(FENSTER[0])).all() and (t < pd.Timestamp(FENSTER[1])).all()
    assert (kal.je_kerze[kal.kerzen] == kal.key).all() and (kal.je_kerze >= 0).sum() == len(kal.kerzen)
    assert gm.kalender(zm, *FENSTER) is kal                              # aus dem Zwischenspeicher


def test_verschiebungen_lassen_den_tag_des_einstiegs_und_60_tage_davor_aus():
    alle = gm.schritte(369)
    assert list(alle[:3]) == [1, 2, 3] and alle[-1] == 369 - 61 and len(alle) == 308
    teil = gm.schritte(369, 100)
    assert len(teil) == 100 and teil[0] == 1 and teil[-1] == 308 and set(np.diff(teil)) <= {3, 4}
    assert (gm.schritte(369, 1000) == alle).all() and list(gm.schritte(62)) == [1]
    with pytest.raises(ValueError):
        gm.schritte(61)                                                  # zu kurz: Es bliebe keine Verschiebung


def test_zwilling_liegt_um_ganze_handelstage_weiter_zur_selben_uhrzeit(zm, monkeypatch):
    monkeypatch.setattr(gm, "SPERRE_TAGE", 3)
    kal = gm.kalender(zm, *FENSTER)
    e, _ = gm.einstiege(zm, "ausbruch", "5m")
    e = e[gm.im_fenster(zm, e, *FENSTER)]
    schr = gm.schritte(kal.tage)
    tw = gm.verschiebe(kal, e, schr)
    assert list(schr) == list(range(1, 11)) and tw.shape == (len(e), 10) and len(e) > 50
    assert not zm.gesperrt[tw].any() and not zm.nach_luecke[tw].any() and (kal.je_kerze[tw] >= 0).all()
    tag_e, tag_tw = kal.je_kerze[e] // 1440, kal.je_kerze[tw] // 1440
    weiter = (tag_tw - tag_e[:, None]) % kal.tage
    genau = zm.nymin[tw] == zm.nymin[e][:, None]
    assert genau.mean() > 0.9                                            # fast immer dieselbe Minute in New York
    assert (weiter[genau] == np.broadcast_to(schr, tw.shape)[genau]).all()
    assert (weiter >= 1).all() and (weiter <= kal.tage - gm.SPERRE_TAGE).all()   # nie am selben Tag, nie kurz davor
    # sonst die nächste erlaubte Kerze danach
    ziel = (tag_e[:, None] + schr[None, :]) % kal.tage * 1440 + zm.nymin[e][:, None]
    for k, b in zip(*np.nonzero(~genau)):
        spaeter = kal.kerzen[kal.key >= ziel[k, b]]
        assert tw[k, b] == (spaeter[0] if len(spaeter) else kal.kerzen[0])
    # Alle Trades einer Verschiebung wandern gemeinsam: Die Abstände zwischen den Trades bleiben in Handelstagen gleich
    b = 4
    assert ((np.diff(tag_tw[:, b]) - np.diff(tag_e)) % kal.tage == 0)[genau[1:, b] & genau[:-1, b]].all()


def test_am_fensterende_geht_die_verschiebung_vorn_weiter(zm, monkeypatch):
    monkeypatch.setattr(gm, "SPERRE_TAGE", 3)
    kal = gm.kalender(zm, *FENSTER)
    letzter = kal.kerzen[kal.key // 1440 == kal.tage - 1][::50]
    tw = gm.verschiebe(kal, letzter, gm.schritte(kal.tage))
    assert (kal.je_kerze[tw] // 1440 <= 9).all() and (kal.je_kerze[tw[:, 0]] // 1440 <= 1).all()
    assert (zm.t[tw] < zm.t[letzter][:, None]).all()                     # liegt im Kalender vor dem echten Einstieg
    with pytest.raises(ValueError):
        gm.verschiebe(kal, np.flatnonzero(zm.gesperrt)[:3], gm.schritte(kal.tage))


def test_schwankung_am_zwilling_geteilt_durch_schwankung_am_einstieg(zm, monkeypatch):
    monkeypatch.setattr(gm, "SPERRE_TAGE", 3)
    kal = gm.kalender(zm, *FENSTER)
    e = kal.kerzen[200::400]
    tw = gm.verschiebe(kal, e, gm.schritte(kal.tage))
    k = zm.eb["15m"]
    atr = gm.ind(k, "atr", 14)
    lam = gm.vola_faktor(zm, "15m", e, tw)
    assert lam.shape == tw.shape and (lam > 0).all() and lam.min() < 0.9 and lam.max() > 1.1
    assert lam == pytest.approx(atr[k.lc[tw]] / atr[k.lc[e]][:, None])   # ATR der letzten fertigen 15-Minuten-Kerze
    assert (gm.vola_faktor(zm, "15m", e, e[:, None]) == 1.0).all()
    assert (gm.vola_faktor(zm, "1h", e, tw) != lam).any()                # eine andere Stop-Ebene misst anders
    assert (gm.vola_faktor(zm, "15m", np.array([0, 1]), np.array([[5], [6]])) == 1.0).all()   # ohne ATR: Faktor 1


def test_zwillings_lauf_passt_stop_und_kosten_an_die_schwankung_an(zm, monkeypatch):
    monkeypatch.setattr(gm, "SPERRE_TAGE", 3)
    f = {"einstieg": "ausbruch", "ebene": "5m", "filter": "ohne", "stop": "atr2_15m", "ausstieg": "trail_struktur_1h"}
    tr = gm.trades_von(zm, f, *FENSTER).iloc[:12]
    e, d, dist = tr["e"].to_numpy(np.int64), tr["d"].to_numpy(np.int64), tr["r_usd"].to_numpy(float)
    kal = gm.kalender(zm, *FENSTER)
    tw = gm.verschiebe(kal, e, gm.schritte(kal.tage, 3))
    lam = gm.vola_faktor(zm, "15m", e, tw)
    nacht = gm.nacht_r(zm, e, d, dist)
    assert nacht == pytest.approx(np.where(d > 0, 6.5, 2.0) / 36500 * (zm.o[e] + np.where(d > 0, 0.5, 0.0)) / dist)
    modus = gm.MODUS["trail_struktur"]
    s, g, v = gm.zwillinge(zm, tw, lam, d, dist, modus, 0.0, "1h", nacht)
    naechte = 0
    for b in range(tw.shape[1]):
        summe = 0.0
        for k in range(len(e)):                                  # Stop-Abstand und Spread mal lam, Gebühr je Nacht wie echt
            r, n = einzel(zm, tw[k, b], d[k], dist[k] * lam[k, b], 0.5 * lam[k, b], modus, 0.0, "1h")
            summe += r - nacht[k] * n
            naechte += n
        assert s[b] == pytest.approx(summe) and g[b] - v[b] == pytest.approx(s[b])
    assert naechte > 0                                           # die Gebühr wurde wirklich geprüft
    # Der Zwilling am echten Einstieg mit Faktor 1 ist der echte Trade
    s0, _, _ = gm.zwillinge(zm, e[:, None], np.ones((len(e), 1)), d, dist, modus, 0.0, "1h")
    assert s0[0] == pytest.approx(tr["r"].sum())


def test_zwilling_in_doppelter_schwankung_ist_derselbe_trade_in_r():
    """Zwei Tage, der zweite mit doppelt so großen Bewegungen. Der Zwilling des Trades vom ersten Tag bringt am zweiten
    Tag dasselbe Ergebnis in R, weil Stop-Abstand und Spread mitwachsen."""
    n = 300
    weg = np.cumsum(np.random.default_rng(3).normal(0, 0.4, n))
    def tag(start, faktor):
        c = 2000.0 + faktor * weg
        o = np.r_[2000.0, c[:-1]]
        return kerzen(o, np.maximum(o, c) + 0.2 * faktor, np.minimum(o, c) - 0.2 * faktor, c, start)
    m = gm.markt(pd.concat([tag("2026-01-06 10:00", 1.0), tag("2026-01-07 10:00", 2.0)]))
    e, d, dist = np.array([20, 60]), np.array([1, -1]), np.array([3.0, 4.0])
    echt = [lauf(m, [e[k]], [d[k]], [dist[k]], zahl=2.0)[0][0] for k in range(2)]      # jeder für sich, wie die Zwillinge
    s, _, _ = gm.zwillinge(m, (e + n)[:, None], np.full((2, 1), 2.0), d, dist, gm.MODUS["ziel"], 2.0, None,
                           np.zeros(2))
    assert echt == pytest.approx([2.0, -1.0]) and s[0] == pytest.approx(sum(echt))
    ohne, _, _ = gm.zwillinge(m, (e + n)[:, None], np.ones((2, 1)), d, dist, gm.MODUS["ziel"], 2.0, None, np.zeros(2))
    assert ohne[0] != pytest.approx(s[0])                        # ohne Anpassung wäre es ein anderer Trade


# ---------- Auswahl ----------

def test_auswahl_zelle_rechnet_jede_variante_einmal(zm, monkeypatch):
    monkeypatch.setattr(gm, "SPERRE_TAGE", 3)
    z = gm.auswahl_zelle(zm, "rund_bruch", "4h", "ohne", "2026-01-01", "2026-01-20", 5, 3)
    assert len(z) == 6 * 14 and len({x["key"] for x in z}) == len(z)
    assert all(x["key"] == f"rund_bruch.4h.ohne.{x['stop']}.{x['ausstieg']}" for x in z)
    mit = [x for x in z if x["trades"] >= 3]
    assert mit and all(x["rang_pct"] is not None and 0 <= x["rang_pct"] <= 100 and x["pf_robust"] is not None for x in mit)
    assert all(x["z"] is None for x in z if x["trades"] < 3)


def zeile(fam, eb, flt, stop, aus, trades=200, pf=1.5, rob=1.3, z=2.0, rang=99.0, je_woche=3.0, halte=60.0) -> dict:
    return {"key": f"{fam}.{eb}.{flt}.{stop}.{aus}", "einstieg": fam, "ebene": eb, "filter": flt, "stop": stop,
            "ausstieg": aus, "signale": 999, "trades": trades, "je_woche": je_woche, "pf": pf, "summe_r": 10.0,
            "pf_robust": rob, "median_halte_min": halte, "zw_mittel": 0.0, "zw_sd": 1.0, "z": z, "rang_pct": rang,
            "zw_pf12": 0.1}


def zelle(fam, eb, flt, z_bester, n=10, **kw) -> list[dict]:
    """n wertbare Varianten: eine qualifizierte mit z_bester, der Rest mittelmäßig."""
    out = [zeile(fam, eb, flt, f"s{i}", "ziel_1r", pf=1.0, rob=0.9, z=z_bester - 1.0, rang=50.0) for i in range(n - 1)]
    return out + [zeile(fam, eb, flt, "atr1_5m", "ziel_2r", z=z_bester, **kw)]


def test_finalisten_hoechstens_12_sechs_schnelle_zuerst_zwei_je_einstieg():
    fams = list(P["einstiege"])
    zeilen = []
    for i, fam in enumerate(fams):                                # je Einstieg 5 Zellen, davon 2 langsame mit hohem Wert
        for j, flt in enumerate(gm.FILTER):
            langsam = j < 2
            zeilen += zelle(fam, "5m", flt, 5.0 - 0.1 * i - 0.01 * j + (1.0 if langsam else 0.0),
                            je_woche=0.5 if langsam else 4.0, halte=5000.0 if langsam else 30.0)
    fin, zt = gm.waehle_finalisten(pd.DataFrame(zeilen))
    assert len(fin) == 12 and int(zt["zaehlt"].sum()) == 65
    assert all(f["schnell"] for f in fin[:6]) and not any(f["schnell"] for f in fin[6:])
    je = pd.Series([f["einstieg"] for f in fin]).value_counts()
    assert je.max() <= 2
    assert [f["einstieg"] for f in fin[:6]] == [fams[0]] * 2 + [fams[1]] * 2 + [fams[2]] * 2   # die besten schnellen zuerst
    assert [f["einstieg"] for f in fin[6:8]] == [fams[3]] * 2     # die ersten drei Einstiege sind schon voll
    assert fin[0]["key"].endswith("atr1_5m.ziel_2r")              # die qualifizierte Variante mit dem höchsten z


def test_zelle_zaehlt_nur_mit_acht_wertbaren_und_einer_qualifizierten():
    zu_wenig = zelle("ausbruch", "5m", "ohne", 5.0, n=7)
    keine_quali = [zeile("ema_kreuz", "5m", "ohne", f"s{i}", "ziel_1r", pf=1.19, z=3.0) for i in range(10)]
    wenig_trades = zelle("rund_bruch", "5m", "ohne", 5.0, n=10, trades=49)
    schwach_robust = zelle("band_umkehr", "5m", "ohne", 5.0, n=10, rob=0.99)
    rang_89 = zelle("fehlausbruch", "5m", "ohne", 5.0, n=10, rang=89.0)
    gut = zelle("schwungkerze", "5m", "ohne", 1.0, n=8)
    fin, zt = gm.waehle_finalisten(pd.DataFrame(zu_wenig + keine_quali + wenig_trades + schwach_robust + rang_89 + gut))
    assert [f["einstieg"] for f in fin] == ["schwungkerze"]
    assert gm.waehle_finalisten(pd.DataFrame(zu_wenig + keine_quali))[0] == []


def test_zufalls_zaehlung_zaehlt_echt_und_erwartet():
    tab = pd.DataFrame(zelle("ausbruch", "5m", "ohne", 5.0, n=10) + zelle("ema_kreuz", "5m", "ohne", 5.0, n=10))
    zz = {q["einstieg"]: q for q in gm.zufalls_zaehlung(tab)}
    assert zz["ausbruch"]["wertbar"] == 10 and zz["ausbruch"]["pf_ab_1_2"] == 1 and zz["ausbruch"]["qualifiziert"] == 1
    assert zz["ausbruch"]["zufall_pf_ab_1_2"] == pytest.approx(1.0) and zz["alle"]["wertbar"] == 20
    assert zz["alle"]["zufall_rang_ab_90"] == pytest.approx(2.0) and zz["rund_bruch"]["wertbar"] == 0


def test_karte_ordnet_nach_bausteinen():
    tab = pd.DataFrame([zeile("ausbruch", "5m", "ohne", "atr2_15m", "supertrend_1h", z=2.0, rang=95.0),
                        zeile("ausbruch", "5m", "ohne", "swing_5m", "ziel_2r", z=0.0, rang=50.0),
                        zeile("ausbruch", "5m", "ohne", "atr1_1h", "tagesende", trades=10)])
    ka = gm.karte(tab)
    assert ka["einstieg_ebene"] == [{"einstieg": "ausbruch", "ebene": "5m", "wertbar": 2, "pf_median": 1.5,
                                     "z_median": 1.0, "rang_ab_90_pct": 50.0}]
    assert {(q["stop_art"], q["stop_abstand"]) for q in ka["stop"]} == {("atr2", 1), ("swing", 0)}
    assert {(q["ausstieg_art"], q["ausstieg_abstand"]) for q in ka["ausstieg"]} == {("supertrend", 2), ("ziel_2r", -1)}
    assert gm._abstand("1h", "trail_struktur_1d") == ("trail_struktur", 2) and gm._abstand("5m", "tagesende") == ("tagesende", None)
    assert gm.karte(tab[tab["trades"] < 50]) == {}


# ---------- Urteil und Bericht ----------

def test_holm_ueber_alle_finalisten():
    ps = {f"f{i}": 0.5 for i in range(10)} | {"a": 1 / 309, "b": 2 / 309}
    hm = gm.holm(ps, 0.05)
    assert hm["a"] and not hm["b"] and not hm["f0"]              # a: 0,05 / 12 = 0,0042. b bräuchte 0,05 / 11 = 0,0045
    assert all(gm.holm({f"f{i}": 1 / 309 for i in range(12)}, 0.05).values())   # wer jede Verschiebung schlägt, besteht


def finalist(z=3.2, rang=100.0, **kw) -> dict:
    b = {"trades": 300, "pf": 1.4, "robust_pf": 1.2, "h1": (1.5, 150), "h2": (1.3, 150), "j2026": (1.2, 80),
         "zufall": {"geschlagen_pct": rang, "p": 1 / 310, "z": z}}
    return b | kw


def test_bestanden_braucht_alle_huerden_holm_und_z_ab_3():
    assert gm.urteil_finalist(finalist(), True) == ("bestanden", [])
    assert gm.urteil_finalist(finalist(z=3.0), True)[0] == "bestanden"
    # Der Finalist aus dem Probelauf ohne Vorteil: alle 309 Verschiebungen geschlagen, aber z nur 2,90
    assert gm.urteil_finalist(finalist(z=2.9), True) == ("kandidat", ["z unter 3,0"])
    assert gm.urteil_finalist(finalist(), False) == ("kandidat", ["Holm"])
    assert gm.urteil_finalist(finalist(z=None), False) == ("kandidat", ["Holm", "z unter 3,0"])
    urteil, fehlt = gm.urteil_finalist(finalist(rang=94.9), True)             # unter 95 % der Läufe: gar kein Kandidat
    assert urteil == "durchgefallen" and fehlt == ["Zufallsvergleich"]
    urteil, fehlt = gm.urteil_finalist(finalist(pf=1.19, z=5.0), True)        # kein z rettet eine verfehlte Hürde
    assert urteil == "durchgefallen" and "Holm" not in fehlt and len(fehlt) == 1
    assert gm.urteil_finalist(finalist(h2=(0.99, 150)), True)[0] == "durchgefallen"
    assert gm.urteil_finalist(finalist(trades=99), True)[0] == "durchgefallen"


def test_bewertung_eines_finalisten_und_bericht(zm, monkeypatch):
    monkeypatch.setattr(gm, "HAUPT_VON", pd.Timestamp("2026-01-01"))
    monkeypatch.setattr(gm, "MITTE", pd.Timestamp("2026-01-12"))
    monkeypatch.setattr(gm, "HAUPT_BIS", pd.Timestamp("2026-01-24"))
    f = {"einstieg": "fehlausbruch", "ebene": "5m", "filter": "ohne", "stop": "atr2_15m", "ausstieg": "ziel_2r"}
    monkeypatch.setattr(gm, "SPERRE_TAGE", 3)
    b, tr = gm.bewerte_finalist(zm, f)
    assert b["trades"] == len(tr) == b["h1"][1] + b["h2"][1] and b["trades"] > 30
    assert b["long"]["trades"] + b["short"]["trades"] == b["trades"]
    assert b["zufall"]["laeufe"] == 6 == len(gm.schritte(gm.kalender(zm, gm.MITTE, gm.HAUPT_BIS).tage))   # 10 Tage, alle
    assert 1 / 7 <= b["zufall"]["p"] <= 1 and round(b["zufall"]["p"] * 7) == pytest.approx(b["zufall"]["p"] * 7)
    assert gm.bewerte_finalist(zm, f, 2)[0]["zufall"]["laeufe"] == 2
    h2 = tr[tr["zeit"] >= gm.MITTE]
    e, d, dist = h2["e"].to_numpy(np.int64), h2["d"].to_numpy(np.int64), h2["r_usd"].to_numpy(float)
    kal = gm.kalender(zm, gm.MITTE, gm.HAUPT_BIS)
    tw = gm.verschiebe(kal, e, gm.schritte(kal.tage))
    s, _, _ = gm.zwillinge(zm, tw, gm.vola_faktor(zm, "15m", e, tw), d, dist, gm.MODUS["ziel"], 2.0, None, gm.nacht_r(zm, e, d, dist))
    assert b["zufall"]["z"] == pytest.approx((h2["r"].sum() - s.mean()) / s.std(), abs=1e-3)
    assert b["zufall"]["geschlagen_pct"] == pytest.approx((s < h2["r"].sum()).mean() * 100, abs=0.01)
    assert b["spread_r"] == pytest.approx(float((0.5 / tr["r_usd"]).mean()), abs=1e-3)
    b.update(urteil="kandidat", holm=False, fehlt=["Holm"], auswahl={"schnell": True, "zellwert": 1.0, "trades": 60,
                                                                     "pf": 1.3, "z": 2.0, "rang_pct": 97.0}, **f)
    text = gm.bericht({"vorab_sha256": "a" * 64, "finalisten_sha256": "b" * 64, "varianten": 54375, "zellen": 305,
                       "zellen_die_zaehlen": 1, "finalisten": {"fehlausbruch.5m.ohne.atr2_15m.ziel_2r": b},
                       "kombi": {"bestanden": gm.kombi([]), "bestanden_und_kandidaten": gm.kombi([tr])},
                       "zufalls_zaehlung": gm.zufalls_zaehlung(pd.DataFrame(zelle("ausbruch", "5m", "ohne", 5.0))),
                       "karte": gm.karte(pd.DataFrame(zelle("ausbruch", "5m", "ohne", 5.0)))})
    assert "| Kandidat |" in text and "Bestanden: 0. Kandidaten: 1." in text and "Zufalls-Zählung" in text
    assert "## Karte der Auswahl-Hälfte" in text and "| ziel_2r | – |" in text
    assert "Jede mögliche Verschiebung ist ein Lauf (hier 6)" in text and "Bei 1 Finalisten" in text
    assert "| Holm | z |" in text and "z ab 3,0" in text
    leer = gm.bericht({"vorab_sha256": "a" * 64, "finalisten_sha256": "b" * 64, "finalisten": {}})
    assert "keinen Finalisten" in leer
