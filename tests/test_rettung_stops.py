"""Stop-Prüfung "Rettung" (suche/rettung_stops.py): Siegel, die Lesart des Rettungs-Ausstiegs und die Auswertung."""
import numpy as np
import pandas as pd
import pytest

from suche import rettung_stops as rs
from suche.runde1 import journal_lines, last_value, sha256_text


def weg(schlecht, gut, r, ende="zeit", brutto=None, bot="test", t="2025-01-02", halb=None):
    return rs.Weg(bot, pd.Timestamp(t), r, r if brutto is None else brutto, np.array(gut, float),
                  np.array(schlecht, float), ende, halb=halb)


def test_siegel_steht_im_protokoll():
    text = rs.VORAB.read_text(encoding="utf-8")
    assert last_value(journal_lines(), rs.KEY) == sha256_text(text)


def test_vorab_zaehlt_die_fassungen_richtig():
    cfg = rs.lade_vorab(pruefen=False)
    v = cfg["varianten"]
    anzahl = sum(len(x.get("bots", cfg["bots"])) for x in v.values())
    assert anzahl == cfg["vergleich"]["anzahl_fassungen"] == 15
    assert set(v["stop_halb"]["bots"]) <= set(cfg["bots"])
    assert v["rettung_einstand"]["ausloeser_r"] == v["rettung_kleines_minus"]["ausloeser_r"] == -0.5


def test_ohne_ausloeser_bleibt_das_original():
    w = weg(schlecht=[-0.2, -0.4, -0.49], gut=[0.3, 0.5, 0.1], r=-0.3)
    assert rs.rettung(w, -0.5, 0.0) == (-0.3, False)


def test_rettung_am_einstand_ab_der_naechsten_kerze():
    # Kerze 0 löst aus und kommt in derselben Kerze zurück: zählt nicht. Kerze 2 erreicht den Einstand.
    w = weg(schlecht=[-0.6, -0.7, -0.3, -1.0], gut=[0.2, -0.1, 0.05, -0.5], r=-1.05, brutto=-1.0, ende="stop")
    r, gerettet = rs.rettung(w, -0.5, 0.0)
    assert gerettet and r == pytest.approx(-0.05)          # 0 R vor Gebühr, die Gebühr des Originals bleibt


def test_kleines_minus_fuellt_genau_zum_limit():
    w = weg(schlecht=[-0.6, -0.5], gut=[-0.4, 0.4], r=0.3)
    r, gerettet = rs.rettung(w, -0.5, -0.25)
    assert gerettet and r == pytest.approx(-0.25)          # nie besser als das Limit, auch wenn der Kurs höher lief


def test_in_der_stop_kerze_gilt_der_stop_zuerst():
    w = weg(schlecht=[-0.6, -1.0], gut=[-0.3, 0.2], r=-1.0, ende="stop")
    assert rs.rettung(w, -0.5, 0.0) == (-1.0, False)


def test_in_der_ziel_kerze_fuellt_das_limit_vor_dem_ziel():
    w = weg(schlecht=[-0.6, -0.2], gut=[-0.3, 10.0], r=10.0, ende="ziel")
    r, gerettet = rs.rettung(w, -0.5, 0.0)
    assert gerettet and r == pytest.approx(0.0)            # der spätere Gewinner wird verschenkt


def test_leerer_weg_bleibt_das_original():
    assert rs.rettung(weg([], [], -1.0, ende="stop"), -0.5, 0.0) == (-1.0, False)


def test_tal_und_kennzahlen():
    k = rs.kennz(np.array([1.0, -0.5, -0.5, 2.0, -1.0]))
    assert k["trades"] == 5 and k["summe_r"] == 1.0 and k["gewinnfaktor"] == 1.5
    assert k["tiefstes_tal_r"] == 1.0 and k["groesster_verlust_r"] == -1.0
    assert k["mittlerer_verlust_r"] == pytest.approx(-0.667, abs=1e-3)


def test_auswertung_urteil_und_holm():
    cfg = {"varianten": {"rettung_einstand": {"ausloeser_r": -0.5, "ziel_r": 0.0},
                         "stop_halb": {"faktor": 0.5, "bots": ["b"]}},
           "vergleich": {"saat": 1, "laeufe": 2000, "alpha": 0.05}, "fenster": {"haupt": ["2024-01-01", "2026-10-30"]}}
    # Bot a: jeder Verlierer läuft erst ins Minus, kommt zum Einstand zurück und wird dann gestoppt. Die Rettung hilft.
    a = [weg([-0.6, -0.2, -1.0], [-0.1, 0.1, -0.3], -1.0, ende="stop", bot="a", t=f"2025-01-{i + 1:02d}") for i in range(20)]
    a += [weg([-0.1], [1.0], 1.0, bot="a", t=f"2025-02-{i + 1:02d}") for i in range(20)]
    # Bot b: der halbe Stop ändert nichts
    b = [weg([-0.1], [1.0], 1.0, bot="b", t=f"2025-03-{i + 1:02d}", halb=1.0) for i in range(10)]
    erg = rs.auswerten(cfg, {"a": a, "b": b})
    assert erg["anzahl_fassungen"] == 3
    z = erg["bots"]["a"]["rettung_einstand"]
    assert z["urteil"] == "bestanden" and z["eingegriffen"] == 20 and z["davon_im_original_gewinner"] == 0
    assert z["haupt"]["summe_r"] == 20.0 and erg["bots"]["a"]["original"]["haupt"]["summe_r"] == 0.0
    assert erg["bots"]["b"]["stop_halb"]["urteil"] == "durchgefallen" and erg["bots"]["b"]["stop_halb"]["p"] == 1.0
    assert "stop_halb" not in erg["bots"]["a"]
