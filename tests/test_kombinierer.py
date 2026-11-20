"""Kombinierer (suche/kombinierer.py, suche/VORAB_schatten.yaml): ein Konto, ein Topf, feste Kontoregeln."""
import pandas as pd
import pytest

from suche import kombinierer as k

OHNE = {"hoechstens_offen": None, "je_markt_hoechstens": None, "tagesstopp_pct": None, "gesamtbremse_pct": None}


def t(i, markt, ein, aus, r):
    return {"id": f"b{i}", "markt": markt, "ein": pd.Timestamp(ein), "aus": pd.Timestamp(aus), "r": r}


def test_ohne_grenzen_zaehlt_jeden_trade_und_leere_monate():
    tr = [t(1, "A", "2026-01-05 10:00", "2026-01-05 12:00", 2.0), t(2, "B", "2026-03-02 10:00", "2026-03-02 11:00", -1.0)]
    e = k.topf(tr, OHNE, 1000.0, 10.0)
    assert e["genommen"] == 2 and e["summe_eur"] == 10.0 and e["endstand_eur"] == 1010.0
    assert list(e["monate"]) == ["2026-01", "2026-02", "2026-03"]          # ein Monat ohne Trade zählt mit 0 €
    assert e["schnitt_monat_eur"] == pytest.approx(10.0 / 3, abs=0.01) and e["monate_im_minus"] == 1


def test_hoechstens_offen_und_je_markt():
    tr = [t(1, "A", "2026-01-05 10:00", "2026-01-05 15:00", 1.0), t(2, "B", "2026-01-05 10:05", "2026-01-05 15:00", 1.0),
          t(3, "C", "2026-01-05 10:10", "2026-01-05 15:00", 1.0), t(4, "A", "2026-01-05 16:00", "2026-01-05 17:00", 1.0)]
    e = k.topf(tr, {**OHNE, "hoechstens_offen": 2}, 1000.0, 10.0)
    assert e["genommen"] == 3 and e["verpasst"] == {"hoechstens_offen": 1}
    tr.append(t(5, "A", "2026-01-05 16:30", "2026-01-05 18:00", 5.0))    # A ist noch belegt (Trade 4 bis 17:00)
    e = k.topf(tr, {**OHNE, "je_markt_hoechstens": 1}, 1000.0, 10.0)
    assert e["verpasst"] == {"je_markt": 1} and e["summe_eur"] == 40.0     # Trade 4 kam nach dem Ausstieg von Trade 1


def test_ausstieg_genau_beim_einstieg_macht_platz():
    tr = [t(1, "A", "2026-01-05 10:00", "2026-01-05 12:00", 1.0), t(2, "A", "2026-01-05 12:00", "2026-01-05 13:00", 1.0)]
    assert k.topf(tr, {**OHNE, "je_markt_hoechstens": 1}, 1000.0, 10.0)["genommen"] == 2


def test_tagesstopp_zaehlt_nur_geschlossene_trades_des_tages():
    tr = [t(1, "A", "2026-01-05 08:00", "2026-01-05 09:00", -3.0), t(2, "B", "2026-01-05 10:00", "2026-01-05 11:00", 1.0),
          t(3, "B", "2026-01-06 10:00", "2026-01-06 11:00", 1.0)]
    e = k.topf(tr, {**OHNE, "tagesstopp_pct": 3}, 1000.0, 10.0)
    assert e["verpasst"] == {"tagesstopp": 1} and e["genommen"] == 2


def test_gesamtbremse_stoppt_alles_danach():
    tr = [t(i, "A", f"2026-01-{5 + i:02d} 10:00", f"2026-01-{5 + i:02d} 11:00", -10.0) for i in range(3)]
    tr.append(t(9, "B", "2026-01-20 10:00", "2026-01-20 11:00", 50.0))
    e = k.topf(tr, {**OHNE, "gesamtbremse_pct": 20}, 1000.0, 10.0)
    assert e["genommen"] == 2 and e["verpasst"] == {"gesamtbremse": 2} and e["summe_eur"] == -200.0
    assert e["gesamtbremse_seit"].startswith("2026-01-07")


def test_regeln_sind_versiegelt_und_wie_im_plan():
    rg = k.regel(pruefen=True)
    assert rg is not None, "Prüfsumme von VORAB_schatten.yaml fehlt im Protokoll"
    assert rg["topf_eur"] == 1000 and rg["risiko_je_trade_pct"] == 1.0
    assert rg["regeln"]["konto"] == {"hoechstens_offen": 3, "je_markt_hoechstens": 1, "tagesstopp_pct": 3,
                                     "gesamtbremse_pct": 20}


def test_demo_trades_wie_im_vergleich():
    """Der Kombinierer zählt genau die Trades, die der Demo-Vergleich für die Gruppe und die Kern-Kombi zählt."""
    g, v = k.demo_gruppen()
    if v.get("gruppe"):
        assert len(g["demo_gruppe"]) == v["gruppe"]["ist"]["trades"]
        r = sum(x["r"] for x in g["demo_gruppe"])
        assert r == pytest.approx(v["gruppe"]["ist"]["summe_r"], abs=0.02)
    assert len(g["demo_kern"]) == v["kombi"]["ist"]["trades"]
    for x in g["demo_gruppe"]:
        assert x["ein"] <= x["aus"] and x["markt"]


def test_satz_ohne_doppelpunkt_und_semikolon():
    rg = k.regel(pruefen=False)
    tr = [t(1, "A", "2026-01-05 10:00", "2026-01-05 12:00", 2.0)]
    s = {"tag": "2026-01-06", "gruppen": {"demo_gruppe": k.alle_regeln(tr, rg)}}
    satz = k.satz(s)
    assert "+20 €" in satz and ":" not in satz and ";" not in satz
