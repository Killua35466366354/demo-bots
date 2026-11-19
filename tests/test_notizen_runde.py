"""Runde "Kirons Notizen" vom 19.11.2026: Siegel, Fassungen, Stufen-Stop und Umkehr auf erfundenen Kerzen. Ohne Kursdaten."""
import numpy as np
import pytest

from suche import notizen_runde as nr
from suche import rueckblick as rb
from suche.runde1 import journal_lines, last_value, sha256_text


def test_siegel_passt():
    assert last_value(journal_lines(), nr.KEY) == sha256_text(nr.VORAB.read_text(encoding="utf-8"))


def test_elf_fassungen_mit_bekannten_grundregeln():
    c = nr.lade_vorab(pruefen=False)
    assert len(c["varianten"]) == 11
    for name, v in c["varianten"].items():
        assert v["regel"] == name
        assert v["basis"] in c["quell_regeln"][v["quelle"]]
        for k in v.get("aendern", {}):
            assert k in c["quell_regeln"][v["quelle"]][v["basis"]], f"{name}: {k} gibt es in der Grundregel nicht"


def test_grundregel_bleibt_bis_auf_aendern_gleich():
    c = nr.lade_vorab(pruefen=False)
    spec = c["varianten"]["silver_bullet_lang"]
    q = nr.regel_cfg(c, spec)
    alt = c["quell_regeln"]["youtube_runde2"]["silver_bullet"]
    neu = q["regeln"]["silver_bullet"]
    assert neu["ziel_r"] == 0.0 and neu["ausstieg_min"] == 960
    assert {k: v for k, v in neu.items() if k not in spec["aendern"]} == \
        {k: v for k, v in alt.items() if k not in spec["aendern"]}
    assert alt["ziel_r"] == 2.0 and alt["ausstieg_min"] == 720          # die versiegelte Quelle bleibt unberührt


def zufallspfad(n=600, saat=3):
    rng = np.random.default_rng(saat)
    c = 100 + np.cumsum(rng.normal(0, 0.2, n))
    o = np.r_[100.0, c[:-1]] + rng.normal(0, 0.05, n)
    h = np.maximum(o, c) + rng.uniform(0, 0.15, n)
    l = np.minimum(o, c) - rng.uniform(0, 0.15, n)
    return o, h, l, c, np.full(n, 0.02)


@pytest.mark.parametrize("d", [1, -1])
@pytest.mark.parametrize("mit_marke", [False, True])
def test_stufen_stop_ohne_stufe_wie_ein_normaler_trade(d, mit_marke):
    o, h, l, c, sp = zufallspfad()
    for i0 in range(5, 500, 37):
        lvl = (o[i0] + 0.05 * d) if mit_marke else np.nan
        for sd, zd in ((0.8, 0.0), (0.5, 1.0), (1.5, 0.7)):
            alt = rb._trade(o, h, l, c, sp, i0, d, lvl, sd, zd, i0 + 80, 1.0, 0.5)
            neu = nr._trade_stufen(o, h, l, c, sp, i0, d, lvl, sd, zd, i0 + 80, 1.0, 0.5, 1e9)
            assert alt[0] == neu[0] and alt[1] == pytest.approx(neu[1]) and alt[2] == pytest.approx(neu[2])


def bogen(hoch, tief, n=40):
    """Kurs 100, steigt um hoch, fällt dann bis 100 minus tief. Kleine Kerzen, kein Spread."""
    p = np.r_[np.linspace(100, 100 + hoch, n), np.linspace(100 + hoch, 100 - tief, 2 * n)]
    o = np.r_[100.0, p[:-1]]
    return o, np.maximum(o, p) + 0.01, np.minimum(o, p) - 0.01, p, np.zeros(len(p))


def test_stufen_stop_sichert_einstand():
    # Long, Stop 1 Punkt. Der Kurs steigt um 1,5 Punkte (1,5 R) und fällt dann auf 98.
    o, h, l, c, sp = bogen(1.5, 2.0)
    ohne = rb._trade(o, h, l, c, sp, 1, 1, np.nan, 1.0, 0.0, len(c), 1.0, 0.5)
    mit = nr._trade_stufen(o, h, l, c, sp, 1, 1, np.nan, 1.0, 0.0, len(c), 1.0, 0.5, 1.0)
    assert ohne[1] == pytest.approx(-1.0, abs=0.06)
    assert mit[1] == pytest.approx(0.0, abs=0.06) and mit[0] < ohne[0]


def test_stufen_stop_sichert_eine_stufe_short():
    # Short, Stop 1 Punkt. Der Kurs fällt um 2,4 Punkte und steigt dann über den Einstieg: +1 R bleibt.
    o, h, l, c, sp = bogen(-2.4, -1.0)
    mit = nr._trade_stufen(o, h, l, c, sp, 1, -1, np.nan, 1.0, 0.0, len(c), 1.0, 0.5, 1.0)
    assert mit[1] == pytest.approx(1.0, abs=0.06)


def test_wahl_nutzt_den_stufen_stop_nur_mit_stufe():
    o, h, l, c, sp = bogen(1.5, 2.0)
    with nr._diese_runde():
        nr._STUFE = 0.0
        assert rb._trade(o, h, l, c, sp, 1, 1, np.nan, 1.0, 0.0, len(c), 1.0, 0.5)[1] == pytest.approx(-1.0, abs=0.06)
        nr._STUFE = 1.0
        assert rb._trade(o, h, l, c, sp, 1, 1, np.nan, 1.0, 0.0, len(c), 1.0, 0.5)[1] == pytest.approx(0.0, abs=0.06)
        ex, pnl, _ = rb._viele(o, h, l, c, sp, np.array([1]), np.array([1]), np.array([1.0]), np.array([0.0]),
                               np.array([len(c)]), np.array([1.0]), 0.5)
        assert pnl[0] == pytest.approx(0.0, abs=0.06)
    assert rb._trade is nr._ORIG["trade"] and rb._viele is nr._ORIG["viele"] and nr._STUFE == 0.0


def test_spiegel_und_weit():
    sig = [{"i0": 10, "d": 1, "sd": 2.0, "zd": 3.0, "t_max": np.datetime64("2025-01-02")}]
    s = nr.aendere(sig, {"umkehr": "spiegel"})[0]
    assert (s["d"], s["sd"], s["zd"]) == (-1, 3.0, 2.0)
    w = nr.aendere(sig, {"umkehr": "weit", "stop_faktor": 1.5, "ziel_r_umkehr": 2.0})[0]
    assert (w["d"], w["sd"], w["zd"]) == (-1, 3.0, 6.0)
    assert sig[0]["d"] == 1                                              # das Original bleibt
    with pytest.raises(SystemExit):
        nr.aendere([{**sig[0], "lvl": 100.0}], {"umkehr": "spiegel"})


def test_ziele():
    sig = [{"i0": 10, "d": -1, "sd": 2.0, "zd": 4.0, "t_max": np.datetime64("2025-01-02")}]
    assert nr.aendere(sig, {"ziel_r_neu": 1.0})[0]["zd"] == 2.0
    assert nr.aendere(sig, {"ziel_r_neu": 0.0})[0]["zd"] == 0.0
    assert nr.aendere(sig, {"ziel_faktor": 0.5})[0]["zd"] == 2.0
    assert nr.aendere(sig, {})[0] == sig[0]
