"""Der Probelauf der Gold-Matrix: erfundener Markt ohne Vorteil, und das Rechenwerk schreibt dabei nie ins Repo."""
import numpy as np
import pandas as pd
import pytest

from suche import gold_matrix as gm
from suche import gold_matrix_probelauf as pl

VON, BIS = "2026-01-05", "2026-01-24"


@pytest.fixture(scope="module")
def daten():
    return pl.alles(VON, BIS, seed=5)


def test_handelszeiten_ohne_wochenende_und_tagespause():
    idx = pl.zeiten(VON, BIS)
    ny = idx.tz_localize("UTC").tz_convert("America/New_York")
    assert len(idx) > 15000 and not (ny.weekday == 5).any() and not (ny.hour == 17).any()
    assert not ((ny.weekday == 4) & (ny.hour >= 17)).any() and not ((ny.weekday == 6) & (ny.hour < 18)).any()


def test_gold_ist_fest_bei_gleichem_seed_und_die_kerzen_passen(daten):
    g, _, _ = daten
    g2, _ = pl.gold(VON, BIS, 5)
    assert g.equals(g2) and not g.equals(pl.gold(VON, BIS, 6)[0])
    assert (g["high"] >= g[["open", "close"]].max(axis=1)).all() and (g["low"] <= g[["open", "close"]].min(axis=1)).all()
    assert (g["open"].iloc[1:].to_numpy() == g["close"].iloc[:-1].to_numpy()).all()      # keine Sprünge zwischen Kerzen
    assert 1000 < g["close"].iloc[-1] < 1500 and (g["high"] - g["low"]).median() > 0.05


def test_gold_hat_keinen_vorteil_aus_der_letzten_kerze(daten):
    g, _, _ = daten
    r = np.log(g["close"]).diff().dropna().to_numpy()
    assert abs(np.corrcoef(r[1:], r[:-1])[0, 1]) < 0.03                                  # kein Nachlauf, keine Umkehr
    assert np.corrcoef(np.abs(r[1:]), np.abs(r[:-1]))[0, 1] > 0.1                        # aber die Schwankung hält an


def test_andere_maerkte_laufen_mit_aber_nie_voraus(daten):
    g, fr, rz = daten
    assert set(fr) == {"EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDCHF", "XAGUSD", "SPXUSD"} and len(rz[0]) == len(rz[1])
    g5 = np.log(g["close"]).groupby(g.index.floor("5min")).last().diff()
    s = np.log(fr["XAGUSD"]["close"]).diff()
    assert (fr["XAGUSD"].index.minute % 5 == 0).all() and s.index.equals(g5.index)
    beide = pd.concat([g5, s], axis=1).dropna().to_numpy()
    assert np.corrcoef(beide[:, 0], beide[:, 1])[0, 1] > 0.5                             # gleichzeitig: ja
    assert abs(np.corrcoef(beide[1:, 0], beide[:-1, 1])[0, 1]) < 0.06                    # Silber vor Gold: nein
    j = np.log(fr["USDJPY"]["close"]).diff()
    assert np.corrcoef(pd.concat([g5, j], axis=1).dropna().to_numpy().T)[0, 1] < -0.15


def test_rechenwerk_haengt_nur_im_block_am_erfundenen_markt(daten, tmp_path):
    alt = (gm.lade_markt, gm.FINALISTEN, gm.ERGEBNIS, gm.daten_siegel)
    with pl.erfundener_markt(tmp_path, daten):
        assert gm.FINALISTEN == tmp_path / "VORAB_gold_matrix_finalisten.yaml" and gm.ERGEBNIS.parent == tmp_path
        m = gm.lade_markt(None, "2026-01-12", "2026-01-17")
        assert pd.Timestamp(m.t[0]) >= pd.Timestamp("2026-01-12") and pd.Timestamp(m.t[-1]) < pd.Timestamp("2026-01-17")
        assert set(m.fremd) == set(daten[1]) and gm.daten_siegel(None) == {"erfunden": f"Seed {pl.SEED}"}
        assert (m.termine >= np.datetime64("2026-01-12")).all() and (m.termine < np.datetime64("2026-01-17")).all()
    assert (gm.lade_markt, gm.FINALISTEN, gm.ERGEBNIS, gm.daten_siegel) == alt
    assert gm.FINALISTEN.parent == gm.ROOT / "suche"
    with pytest.raises(RuntimeError):
        with pl.erfundener_markt(tmp_path, daten):
            raise RuntimeError("Abbruch")
    assert (gm.lade_markt, gm.FINALISTEN, gm.ERGEBNIS, gm.daten_siegel) == alt           # auch nach einem Fehler
    with pl.erfundener_markt(tmp_path, daten, 24):
        assert gm.daten_siegel(None) == {"erfunden": "Seed 24"}                           # ein anderer erfundener Markt


def test_probelauf_schreibt_nie_ins_repo():
    with pytest.raises(SystemExit):
        pl.main([str(gm.ROOT / "suche" / "probelauf")])
    with pytest.raises(SystemExit):
        pl.main([str(gm.ROOT / "suche" / "probelauf"), "24"])
    with pytest.raises(SystemExit):
        pl.main([])
    with pytest.raises(SystemExit):
        pl.main(["a", "24", "zu viel"])
