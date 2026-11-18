"""Runde "Starker Rückblick": Kosten, Stops, Einstiegskerze, Urteil und Siegel. Ohne Kursdaten."""
import numpy as np
import pytest
import yaml

from suche import rueckblick as rb
from suche import rueckblick_daten as rd
from suche.runde1 import journal_lines, last_value, sha256_text

NAN = float("nan")


def kerzen(zeilen, spread=0.1):
    a = np.array(zeilen, float)
    return a[:, 0].copy(), a[:, 1].copy(), a[:, 2].copy(), a[:, 3].copy(), np.full(len(a), spread)


def test_long_markt_stop_zaehlt_vor_ziel_und_rutscht():
    o, h, l, c, sp = kerzen([[100, 100.4, 99.8, 100.2], [100.2, 102.5, 98.5, 101.0], [101, 101, 101, 101]])
    ex, pnl, e = rb._trade(o, h, l, c, sp, 0, 1, NAN, 1.0, 2.0, 99, 1.0, 0.5)
    assert e == pytest.approx(100.1)                       # Kauf zum Ask
    assert ex == 1
    assert pnl == pytest.approx(99.0 - 0.05 - 100.1)       # Stop am Bid 99, halber Spread schlechter


def test_long_luecke_ueber_den_stop_zaehlt_die_eroeffnung():
    o, h, l, c, sp = kerzen([[100, 100.4, 99.8, 100.2], [98.0, 98.4, 97.5, 98.2]])
    ex, pnl, e = rb._trade(o, h, l, c, sp, 0, 1, NAN, 1.0, 0.0, 99, 1.0, 0.5)
    assert ex == 1 and pnl == pytest.approx(98.0 - 0.05 - 100.1)


def test_zeit_ausstieg_zur_eroeffnung():
    o, h, l, c, sp = kerzen([[100, 100.4, 99.8, 100.2], [100.3, 100.6, 100.1, 100.5], [100.6, 100.7, 100.5, 100.6]])
    ex, pnl, e = rb._trade(o, h, l, c, sp, 0, 1, NAN, 5.0, 0.0, 2, 1.0, 0.5)
    assert ex == 2 and pnl == pytest.approx(100.6 - 100.1)
    ex, pnl, e = rb._trade(o, h, l, c, sp, 0, -1, NAN, 5.0, 0.0, 2, 1.0, 0.5)
    assert ex == 2 and pnl == pytest.approx(100.0 - (100.6 + 0.1))   # Short kauft zum Ask zurück


def test_short_stop_loest_am_ask_aus():
    o, h, l, c, sp = kerzen([[100, 100.2, 99.9, 100.0], [100.0, 100.95, 99.9, 100.5]])
    ex, pnl, e = rb._trade(o, h, l, c, sp, 0, -1, NAN, 1.0, 0.0, 99, 1.0, 0.5)
    assert e == pytest.approx(100.0)
    assert ex == 1 and pnl == pytest.approx(100.0 - (101.0 + 0.05))


def test_stop_order_einstiegskerze_tief_vor_dem_einstieg_zaehlt_nicht():
    # Eröffnung näher am Tief: O, Tief, Hoch, Schluss. Das Tief lag vor dem Einstieg an der Marke 100,5.
    o, h, l, c, sp = kerzen([[100.0, 101.0, 99.8, 100.9], [100.9, 101.0, 100.8, 100.9]])
    ex, pnl, e = rb._trade(o, h, l, c, sp, 0, 1, 100.5, 0.3, 0.0, 1, 1.0, 0.5)
    assert e == pytest.approx(100.5 + 0.1 + 0.05)          # Ask plus halber Spread Rutschen
    assert ex == 1 and pnl == pytest.approx(100.9 - e)


def test_stop_order_einstiegskerze_tief_nach_dem_einstieg_stoppt():
    # Eröffnung näher am Hoch: O, Hoch, Tief, Schluss. Nach dem Einstieg fällt der Kurs unter den Stop 100,2.
    o, h, l, c, sp = kerzen([[100.4, 100.6, 99.5, 99.6], [99.6, 99.7, 99.5, 99.6]])
    ex, pnl, e = rb._trade(o, h, l, c, sp, 0, 1, 100.5, 0.3, 0.0, 1, 1.0, 0.5)
    assert ex == 0 and pnl == pytest.approx(100.2 - 0.05 - e)


def test_stop_order_short_spiegelbild():
    o, h, l, c, sp = kerzen([[100.6, 101.5, 100.4, 101.4], [101.4, 101.5, 101.3, 101.4]])
    # Eröffnung näher am Tief: O, Tief, Hoch, Schluss. Verkauf an 100,5, danach Hoch 101,5 über dem Stop 100,8.
    ex, pnl, e = rb._trade(o, h, l, c, sp, 0, -1, 100.5, 0.3, 0.0, 1, 1.0, 0.5)
    assert e == pytest.approx(100.5 - 0.05)
    assert ex == 0 and pnl == pytest.approx(e - (100.8 + 0.05))


def test_gewinnfaktor():
    assert rb.pf(np.array([1.0, 2.0, -1.5])) == pytest.approx(2.0)
    assert rb.pf(np.array([])) is None


def test_sechs_varianten_mit_bekannten_maerkten_und_regeln():
    cfg = yaml.safe_load(rb.VORAB.read_text(encoding="utf-8"))["rueckblick"]
    assert len(cfg["varianten"]) == 6
    for v in cfg["varianten"].values():
        assert v["regel"] in ("ausbruch4h", "dienstag")     # die Vortag-Regel ist nicht Teil dieser Runde
        assert set(v["maerkte"]) <= set(rd.MAERKTE)
    assert cfg["huerden"]["min_z"] == 3.0 and cfg["huerden"]["min_trades"] == 100


def test_urteil_holm_zaehlt_ueber_alle_sechs():
    cfg = yaml.safe_load(rb.VORAB.read_text(encoding="utf-8"))["rueckblick"]

    def e(p, z, pct):
        return {"trades": 150, "gewinnfaktor": 1.5, "gewinnfaktor_robust": 1.3,
                "haelfte_1": {"gewinnfaktor": 1.4}, "haelfte_2": {"gewinnfaktor": 1.6},
                "jahr_2026": {"trades": 30, "gewinnfaktor": 1.2},
                "zufall": {"p": p, "z": z, "geschlagen_pct": pct}}

    erg = {"a": e(0.002, 3.5, 100.0), "b": e(0.02, 2.5, 98.5), "c": e(0.3, 0.5, 70.0)}
    rb.urteile(erg, cfg)
    assert erg["a"]["urteil"] == "bestanden"               # 0,002 <= 0,05 / 6
    assert erg["b"]["urteil"] == "Kandidat"                # 95 % geschlagen, aber Holm und z fehlen
    assert erg["c"]["urteil"] == "durchgefallen"
    erg = {"a": e(0.009, 3.5, 100.0)}                      # 0,009 > 0,05 / 6: Holm fehlt trotz z
    rb.urteile(erg, cfg)
    assert erg["a"]["urteil"] == "Kandidat" and erg["a"]["durchgefallen_bei"] == ["Holm"]


def test_regeldatei_ist_versiegelt():
    text = rb.VORAB.read_text(encoding="utf-8")
    assert last_value(journal_lines(), rb.KEY) == sha256_text(text)
