"""Prüft die Rechnung des Tests Rückgänge von V1 (suche/v1_rueckgang.py) an erfundenen Zahlen."""
import numpy as np
import pandas as pd

from suche import v1_rueckgang as v


def _t(zeilen):
    """zeilen: (markt, ein, aus, r, margin_je_r)"""
    t = pd.DataFrame(zeilen, columns=["markt", "ein", "aus", "r", "margin_je_r"])
    t["id"] = "bot"
    t["ein"], t["aus"] = pd.to_datetime(t.ein), pd.to_datetime(t.aus)
    return t


def test_wert_vom_tag_gilt_erst_ab_folgetag():
    s = pd.Series([10.0, 20.0], index=pd.to_datetime(["2026-01-05", "2026-01-06"]))
    ein = pd.Series(pd.to_datetime(["2026-01-06 23:59", "2026-01-07 00:00", "2026-01-05 12:00"]))
    assert list(v.letzter_wert(s, ein)) == [0, 1, -1]


def test_f1_relativ_und_f3_nur_gold():
    tage = pd.bdate_range("2025-01-01", periods=260)
    gvz = pd.Series(np.r_[np.full(259, 20.0), 40.0], index=tage)
    vix = pd.Series(np.r_[np.full(259, 15.0), 25.0], index=tage)
    ein = tage[-1] + pd.Timedelta(days=1, hours=1)
    t = _t([("GOLD", ein, ein + pd.Timedelta(hours=2), 1.0, 1.0),
            ("US500", ein, ein + pd.Timedelta(hours=2), 1.0, 1.0),
            ("GOLD", tage[-2] + pd.Timedelta(days=1, hours=1), tage[-2] + pd.Timedelta(days=1, hours=3), 1.0, 1.0),
            ("GOLD", tage[100] + pd.Timedelta(days=1), tage[100] + pd.Timedelta(days=1, hours=1), 1.0, 1.0)])
    m = v.merkmale(t, vix, gvz)
    assert list(m.F1) == [True, False, False, False]      # zu wenig Tage davor: nie
    assert list(m.F3) == [True, False, False, False]      # VIX schadet nur Gold
    assert m.gvz_grenze.isna().iloc[3]


def test_einsatz_waechst_und_schluss_vor_eroeffnung():
    t = _t([("GOLD", "2026-01-02 10:00", "2026-01-02 11:00", 2.0, 1.0),
            ("GOLD", "2026-01-02 11:00", "2026-01-02 12:00", 1.0, 1.0)])
    k = v.Konto(t, np.arange(2), abzug=0.1)
    res = k.lauf()
    erst = 1000 + 1.9 * 20             # 2 % von 1.000 € = 20 € je R
    assert abs(res["ende"] - (erst + 0.9 * 0.02 * erst)) < 1e-9
    assert res["genommen"].all()


def test_grenze_des_brokers_und_gedraenge():
    z = [("GOLD", f"2026-01-02 10:0{i}", "2026-01-02 12:00", 1.0, 10.0) for i in range(5)]
    t = _t(z)
    k = v.Konto(t, np.arange(5))
    res = k.lauf()                      # Margin 10 × 20 € = 200 € je Trade, 5 × 200 = 1.000 € passt genau
    assert res["broker_aus"] == 0
    t.loc[4, "margin_je_r"] = 11.0
    assert v.Konto(t, np.arange(5)).lauf()["broker_aus"] == 1
    g = v.Konto(_t(z), np.arange(5)).lauf(gedraenge=3)
    assert list(g["aus"]) == [False, False, False, True, True]


def test_umkehr_dreht_nur_die_ausgelassenen():
    t = _t([("GOLD", "2026-01-02 10:00", "2026-01-02 11:00", -1.0, 1.0),
            ("US500", "2026-01-02 12:00", "2026-01-02 13:00", 1.0, 1.0)])
    k = v.Konto(t, np.arange(2), abzug=0.0)
    raus = np.array([True, False])
    assert abs(k.lauf(raus=raus)["ende"] - 1020.0) < 1e-9
    assert abs(k.lauf(raus=raus, umkehr=True)["ende"] - (1020.0 + 0.02 * 1020.0)) < 1e-9


def test_rueckgang_in_prozent_vom_hoechststand():
    t = _t([("GOLD", "2026-01-02 10:00", "2026-01-02 11:00", 5.0, 1.0),
            ("GOLD", "2026-01-03 10:00", "2026-01-03 11:00", -5.0, 1.0)])
    res = v.Konto(t, np.arange(2), abzug=0.0).lauf()
    assert abs(res["rueckgang_pct"] - 0.1) < 1e-9


def test_zufall_findet_einen_klaren_filter():
    rng = np.random.default_rng(1)
    zeilen, schlecht = [], []
    for i in range(120):
        a = pd.Timestamp("2026-01-02") + pd.Timedelta(hours=3 * i)
        b = i % 4 == 0
        zeilen.append(("GOLD", a, a + pd.Timedelta(hours=1), -1.0 if b else float(rng.choice([1.5, -0.5])), 1.0))
        schlecht.append(b)
    t = _t(zeilen)
    k = v.Konto(t, np.arange(len(t)))
    raus = np.array(schlecht)
    res = k.lauf(raus=raus)
    p = v.zufall_p(k, np.arange(len(t)), int(raus.sum()), res["ende"], 500, 7)
    assert p < 0.01
    p_gut = v.zufall_p(k, np.arange(len(t)), int((~raus).sum() // 3), k.lauf(raus=~raus & (np.arange(120) % 3 == 0))["ende"], 300, 7)
    assert p_gut > 0.5


def test_episoden_finden_den_tiefsten_rueckgang():
    z = [("GOLD", f"2026-01-{d:02d} 10:00", f"2026-01-{d:02d} 11:00", r, 1.0)
         for d, r in [(2, 5.0), (3, -3.0), (4, -3.0), (5, 10.0), (6, -1.0)]]
    t = _t(z)
    mk = pd.DataFrame({"gvz": np.full(5, 20.0), "vix": np.full(5, 15.0)})
    k = v.Konto(t, np.arange(5), abzug=0.0)
    ep = v.episoden(k, t, mk)
    assert ep[0]["von"] == "2026-01-02" and ep[0]["bis"] == "2026-01-04" and ep[0]["trades"] == 2
    assert abs(ep[0]["je_bot"]["bot"]["summe_r"] + 6.0) < 1e-9


def test_regeldatei_passt_zum_code():
    rg = v.regel()
    assert rg["konto"]["kurse_schlechter"] == 0.1 and rg["konto"]["start"] == 1000.0
    assert len(rg["trades"]["bots"]) == 9 and set(rg["filter"]) == set(v.FILTER)
    assert rg["wahl"]["zeitraum"] == ["2024-11-01", "2025-12-31"]
    assert rg["urteil"]["zeitraum"] == ["2026-01-01", "2026-10-31"]
    assert "20,67" in rg["filter"]["F3"]["regel"] and v.VIX_GRENZE == 20.67
    assert "250" in rg["filter"]["F1"]["regel"] and v.GVZ_TAGE == 250
    assert "2.000" in rg["urteil"]["zufall"] and "20261126" in rg["urteil"]["zufall"]
    assert "20261127" in rg["urteil"]["probelauf"] and "10 %" in rg["urteil"]["probelauf"]


def test_siegel():
    assert v.siegel_ok()
