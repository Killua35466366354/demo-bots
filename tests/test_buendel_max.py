"""Prüft die Rechnung des Tests Super-Bündel für 1.000 € (suche/buendel_max.py) an erfundenen Zahlen."""
import numpy as np
import pandas as pd

from suche import buendel_max as bm


def _t(rows):
    return pd.DataFrame(rows, columns=["id", "ein", "aus", "r", "margin_je_r"]).assign(
        ein=lambda d: pd.to_datetime(d.ein), aus=lambda d: pd.to_datetime(d.aus))


def test_regel_ist_versiegelt():
    assert bm.siegel_ok()
    rg = bm.regel()
    assert rg["konto"]["start_eur"] == 1000
    assert set(bm.BEENDET) == {"pine-tp3", "r6-vortag-gbpjpy"}


def test_margin_offener_trades_und_schluss_zuerst():
    t = _t([["a", "2025-01-01 10:00", "2025-01-01 12:00", 1.0, 30.0],
            ["b", "2025-01-01 12:00", "2025-01-01 14:00", 1.0, 30.0]])
    e = bm.lauf(t, 10.0, 1)
    # a schließt um 12:00 vor der Eröffnung von b: nie 600 € gleichzeitig
    assert e["margin_max"] == 300.0
    assert np.isclose(e["margin_quote"], 300 / 1000)
    assert e["eur_monat"] == 20.0 and np.isclose(e["rendite"], 0.02)


def test_ueberlappung_zaehlt_doppelt_und_kontostand_nur_geschlossen():
    t = _t([["a", "2025-01-01 10:00", "2025-01-01 13:00", -5.0, 40.0],
            ["b", "2025-01-01 11:00", "2025-01-01 14:00", 0.0, 40.0]])
    e = bm.lauf(t, 10.0, 1)
    assert e["margin_max"] == 800.0
    # um 11:00 beide offen: 800 € Margin auf 1.000 € Kontostand (offener Verlust zählt nicht)
    assert np.isclose(e["margin_quote"], 0.80)
    assert e["machbar"]
    e2 = bm.lauf(t, 12.0, 1)
    assert not e2["machbar"]


def test_rueckgang_vom_hoechststand():
    t = _t([["a", "2025-01-01", "2025-01-02", 20.0, 1.0],
            ["a", "2025-01-03", "2025-01-04", -40.0, 1.0],
            ["a", "2025-02-03", "2025-02-04", 5.0, 1.0]])
    e = bm.lauf(t, 10.0, 2)
    assert np.isclose(e["rueckgang_eur"], 400.0)
    assert np.isclose(e["rueckgang_pct"], 400 / 1200)
    assert not e["machbar"]
    assert e["monate_minus"] == 1


def test_trade_ohne_dauer_macht_keine_negative_margin():
    t = _t([["a", "2025-01-01 10:00", "2025-01-01 10:00", 1.0, 5.0]])
    e = bm.lauf(t, 10.0, 1)
    assert e["margin_max"] == 50.0


def test_fehlende_margin_vom_dax_scalper():
    t = _t([["scalp-de40", "2025-01-01", "2025-01-02", 1.0, 10.0],
            ["scalp-de40", "2025-01-03", "2025-01-04", 1.0, 20.0],
            ["scalp-de40", "2025-01-05", "2025-01-06", 1.0, 40.0],
            ["scalp-us100", "2025-01-01", "2025-01-02", 1.0, np.nan]])
    f = bm.margin_auffuellen(t)
    assert f.loc[f.id == "scalp-us100", "margin_je_r"].iloc[0] == 20.0


def test_zeitraum_nach_einstieg_und_monate():
    t = _t([["a", "2025-12-31 23:00", "2026-01-02", 1.0, 1.0],
            ["a", "2026-01-01 00:00", "2026-01-02", 1.0, 1.0]])
    assert len(bm.zeitraum(t, "2024-11-01", "2025-12-31")) == 1
    assert len(bm.zeitraum(t, "2026-01-01", "2026-10-31")) == 1
    assert bm.monate("2024-11-01", "2025-12-31") == 14
    assert bm.monate("2026-01-01", "2026-10-31") == 10


def test_wahl_streicht_nix_und_dann_den_schwaechsten_je_margin():
    rg = {"wahl": {"zeitraum": ["2025-01-01", "2025-01-31"]},
          "konto": {"start_eur": 1000, "einsatz_stufen_prozent": [1.0, 2.0]}}
    rows = []
    # gut: wenig Margin, schwer: viel Margin gleichzeitig, nix: bringt fast nichts, pine-tp3 ist beendet
    for d in range(1, 21):
        rows.append(["gut", f"2025-01-{d:02d} 10:00", f"2025-01-{d:02d} 12:00", 1.0, 5.0])
        rows.append(["schwer", f"2025-01-{d:02d} 10:00", f"2025-01-{d:02d} 12:00", 0.5, 70.0])
        rows.append(["pine-tp3", f"2025-01-{d:02d} 10:00", f"2025-01-{d:02d} 12:00", 5.0, 1.0])
    rows.append(["nix", "2025-01-05 10:00", "2025-01-05 12:00", 0.1, 1.0])
    w = bm.waehle(_t(rows), rg)
    assert w["raus_nix"] == ["nix"]
    assert "pine-tp3" not in w["uebrig"]
    s1, s2 = w["stufen"]
    assert s1["bots"] == ["gut", "schwer"] and s1["machbar"]          # 750 € von 1.000 €
    assert s2["bots"] == ["gut"] and s2["gestrichen"] == ["schwer"]   # 1.500 € zu viel, schwer fliegt
    # 1 %: 20 * (10 + 5) = 300 €; 2 %: 20 * 20 = 400 € -> Stufe 2 % gewinnt
    assert w["gewaehlt"]["stufe"] == 2.0
