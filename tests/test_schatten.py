"""Schatten-Labor (suche/schatten.py, suche/VORAB_schatten.yaml): Zählen ohne Order, Holm, Stufen."""
import numpy as np
import pandas as pd
import pytest

from suche import schatten as sch


def test_alle_52_fassungen_mit_gueltigem_siegel():
    v = sch.lade_vorab(pruefen=True)
    alle = sch.fassungen(v, pruefen=True)                  # jede Runde prüft dabei ihr eigenes Siegel
    assert len(alle) == v["schatten"]["fassungen"] == 52
    assert "notizen_runde:ausbruch4h_welt_ziel_1r" in alle
    assert v["schatten"]["zaehlt_ab"] >= "2026-11-21"      # nur Kerzen nach dem Siegel


def test_holm_der_reihe_nach():
    p = {"a": 0.001, "b": 0.012, "c": 0.02, "d": 0.5}
    assert sch.holm(p, 0.05) == {"a", "b", "c"}            # 0,001 <= 0,0125, 0,012 <= 0,0167, 0,02 <= 0,025, 0,5 > 0,05
    assert sch.holm({"a": 0.02, "b": 0.001}, 0.05) == {"a", "b"}
    assert sch.holm({"a": 0.03, "b": 0.04}, 0.05) == set()


def test_vorzeichen_test():
    gut = np.full(30, 1.0)
    assert sch.p_vorzeichen(gut, 2000, 1) < 0.001
    rng = np.random.default_rng(3)
    zufall = rng.choice([-1.0, 1.0], 200)
    assert 0.01 < sch.p_vorzeichen(zufall - zufall.mean(), 2000, 1) < 0.99
    assert sch.p_vorzeichen(np.array([]), 100, 1) == 1.0


def _e(**x):
    e = {"trades": 120, "tage": 90, "gewinnfaktor": 1.5, "gewinnfaktor_robust": 1.2, "summe_R": 20.0,
         "letzte_61_tage_R": 5.0, "neuere_haelfte_gewinnfaktor": 1.3}
    e.update(x)
    return e


def test_stufen():
    s = sch.lade_vorab(pruefen=False)["schatten"]["stufen"]
    assert sch.stufe(_e(), s, holm_ok=True) == "kandidat"
    assert sch.stufe(_e(), s, holm_ok=False) == "fruehzeichen"          # ohne Holm nie Kandidat
    assert sch.stufe(_e(tage=40), s, holm_ok=True) == "fruehzeichen"
    assert sch.stufe(_e(letzte_61_tage_R=-0.5), s, holm_ok=True) == "fruehzeichen"
    assert sch.stufe(_e(trades=39), s, holm_ok=True) == "zaehlt"
    assert sch.stufe(_e(trades=45, gewinnfaktor=0.8, summe_R=-5.0), s, holm_ok=False) == "schwach"
    assert sch.stufe(_e(trades=45, gewinnfaktor=1.1), s, holm_ok=False) == "zaehlt"


def test_kennzahlen():
    w = pd.DataFrame({"ein_utc": pd.date_range("2026-12-01", periods=4, freq="20D"),
                      "aus_utc": pd.date_range("2026-12-01 05:00", periods=4, freq="20D"),
                      "R": [1.0, -1.0, 2.0, -0.5], "R_robust": [0.9, -1.1, 1.9, -0.6]})
    e = sch.kennzahlen(w, "2027-02-10")
    assert e["trades"] == 4 and e["summe_R"] == 1.5 and e["gewinnfaktor"] == 2.0
    assert e["neuere_haelfte_gewinnfaktor"] == 4.0 and e["tage"] == 71
    assert e["letzte_61_tage_R"] == 0.5                                  # nur Ausstiege ab 11.12.2026: -1 +2 -0,5


def test_zaehle_nur_geschlossene_trades_ab_zaehlbeginn(tmp_path, monkeypatch):
    t = pd.date_range("2026-11-01", "2026-12-31 23:55", freq="5min").values
    np.savez(tmp_path / "AAA.npz", t=t)
    tr = pd.DataFrame({"variante": ["x", "x", "x"], "markt": ["AAA"] * 3,
                       "ein_utc": pd.to_datetime(["2026-11-20 10:00", "2026-12-01 10:00", "2026-12-31 20:00"]),
                       "aus_utc": pd.to_datetime(["2026-11-24 10:00", "2026-12-02 10:00", "2026-12-31 23:55"]),
                       "R": [1.0, -1.0, 3.0], "R_robust": [1.0, -1.0, 3.0]})
    cfg = {"varianten": {"x": {"regel": "probe", "maerkte": ["AAA"]}}}
    monkeypatch.setattr(sch, "runde", lambda name: ((lambda pruefen=True: cfg), (lambda *a, **k: ({}, tr.copy()))))
    v = sch.lade_vorab(pruefen=False)
    v["schatten"] = {**v["schatten"], "runden": {"probe": "-"}, "fassungen": 1}
    erg, trades, bis = sch.zaehle(tmp_path, v, "2026-11-23", pruefen=False)
    assert bis == "2026-12-31" and len(trades) == 1                     # vor dem Zählbeginn und am Datenende offen: nein
    assert erg["probe:x"]["trades"] == 1 and erg["probe:x"]["summe_R"] == -1.0 and erg["probe:x"]["stufe"] == "zaehlt"


def test_falsche_zahl_der_fassungen_bricht_ab(monkeypatch):
    v = sch.lade_vorab(pruefen=False)
    v["schatten"] = {**v["schatten"], "fassungen": 51}
    with pytest.raises(SystemExit):
        sch.zaehle(sch.ROOT, v, "2026-11-23", pruefen=False)


# ---------------------------------------------------------------------------------------------------------------------
# Die 53. Fassung (suche/VORAB_schatten_modell_breit.yaml, Kirons Wahl vom 20.11.2026)

def test_zusatz_versiegelt_und_nur_modell_breit():
    v, z = sch.lade_vorab(pruefen=True), sch.lade_zusatz(pruefen=True)
    zus = sch.fassungen_zusatz(z, pruefen=True)
    assert list(zus) == ["trade_notizen:modell_breit"]
    assert len(sch.fassungen(v, pruefen=True)) + len(zus) == z["fassungen_gesamt"] == 53
    assert z["zaehlt_ab"] == v["schatten"]["zaehlt_ab"]


def test_alte_saat_bleibt_und_holm_ueber_alle():
    v = sch.lade_vorab(pruefen=False)
    alle = {"a:x": {"regel": "x"}, "c:y": {"regel": "y"}}
    zus = {"b:z": {"regel": "z", "zusatz": True}}          # sortiert zwischen den alten, bekommt trotzdem die Saat danach
    tr = pd.DataFrame({"fassung": ["a:x"] * 3 + ["c:y"] * 3 + ["b:z"] * 3,
                       "ein_utc": pd.date_range("2026-12-01", periods=9, freq="D"),
                       "aus_utc": pd.date_range("2026-12-01 05:00", periods=9, freq="D"),
                       "R": [1.0, -0.5, 2.0] * 3, "R_robust": [0.9, -0.6, 1.9] * 3})
    ohne = sch.bewerte(tr, alle, v, "2026-12-31")
    mit = sch.bewerte(tr, alle, v, "2026-12-31", zus)
    assert ohne["a:x"]["p"] == mit["a:x"]["p"] and ohne["c:y"]["p"] == mit["c:y"]["p"]
    assert set(mit) == {"a:x", "b:z", "c:y"}


def test_termine_jahre_nur_mit_allen_drei_arten():
    j = sch.termine_jahre()
    assert {2023, 2024, 2025, 2026} <= j
    assert all(isinstance(x, int) for x in j)


def test_falsche_gesamtzahl_bricht_ab():
    v, z = sch.lade_vorab(pruefen=False), sch.lade_zusatz(pruefen=False)
    with pytest.raises(SystemExit):
        sch.zaehle(sch.ROOT, v, "2026-11-23", pruefen=False, z={**z, "fassungen_gesamt": 54})
