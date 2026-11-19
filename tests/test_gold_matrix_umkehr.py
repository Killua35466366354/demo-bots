"""Gold-Matrix umgedreht (suche/gold_matrix_umkehr.py, suche/VORAB_gold_matrix_umkehr.yaml): Die Auswahl hält sich an die
versiegelte Regel, jeder Trade läuft in der Gegenrichtung des Originals, und bewertet wird mit den Hürden der
Gold-Matrix. Alle Kurse hier sind erfunden."""
import numpy as np
import pandas as pd
import pytest

from suche import gold_matrix as gm
from suche import gold_matrix_umkehr as gu
from test_gold_matrix import voller_markt, zufallsmarkt

P = gu.regel()


@pytest.fixture(scope="module")
def zm() -> gm.Markt:
    return voller_markt(zufallsmarkt())


def zeile(key: str, z: float, summe: float = -80.0, zw: float = -20.0, trades: int = 200) -> dict:
    return {**gu.teile(key), "trades": trades, "summe_r": summe, "zw_mittel": zw, "z": z}


def test_auswahl_nimmt_die_schlimmsten_eine_je_zelle_zwei_je_einstieg():
    tab = pd.DataFrame([
        zeile("pivot_abprall.5m.ohne.atr1_1h.zeit_15m", -3.9),
        zeile("pivot_abprall.5m.ohne.atr2_1h.zeit_15m", -3.8),              # dieselbe Zelle: fällt weg
        zeile("pivot_abprall.1m.ohne.atr1_5m.ziel_1r", -3.7),
        zeile("pivot_abprall.1h.ohne.atr1_4h.ziel_1r", -3.6),               # dritter desselben Einstiegs: fällt weg
        zeile("ausbruch.15m.ohne.atr1_1h.ziel_1r", -3.5, trades=49),        # nicht wertbar
        zeile("ausbruch.15m.trend_hoch.atr1_1h.ziel_1r", -2.99),            # z nicht tief genug
        zeile("ausbruch.1h.ohne.atr1_4h.ziel_1r", -3.4, summe=-30.0),       # Verlust kleiner als doppelte Kosten
        zeile("ema_kreuz.5m.ohne.atr1_15m.ziel_1r", -3.0),
        zeile("ruecksetzer.5m.ohne.atr1_15m.ziel_1r", 3.5, summe=90.0),     # ein Gewinner
    ])
    wahl = gu.waehle(tab, P["auswahl"])
    assert [f["key"] for f in wahl] == ["pivot_abprall.5m.ohne.atr1_1h.zeit_15m", "pivot_abprall.1m.ohne.atr1_5m.ziel_1r",
                                        "ema_kreuz.5m.ohne.atr1_15m.ziel_1r"]
    assert wahl[0]["schaetzung_r"] == pytest.approx(2 * -20.0 + 80.0)
    viele = pd.DataFrame([zeile(f"{fam}.{eb}.ohne.atr1_4h.ziel_1r", -3.1 - i / 100)
                          for i, (fam, eb) in enumerate((fam, eb) for fam in list(gm.P["einstiege"])[:8]
                                                        for eb in ("5m", "15m"))])
    assert len(gu.waehle(viele, P["auswahl"])) == int(P["auswahl"]["finalisten_max"]) == 12


def test_versiegelte_finalisten_passen_zur_regel_und_zum_rechenwerk():
    a, fin = P["auswahl"], [gu.teile(f["key"]) | {"z": f["z"]} for f in P["finalisten"]]
    assert 1 <= len(fin) <= int(a["finalisten_max"]) and all(f["z"] <= float(a["max_z"]) for f in fin)
    assert [f["z"] for f in fin] == sorted(f["z"] for f in fin)
    zellen = [(f["einstieg"], f["ebene"], f["filter"]) for f in fin]
    assert len(set(zellen)) == len(zellen)
    assert max(sum(f["einstieg"] == g["einstieg"] for g in fin) for f in fin) <= int(a["max_je_einstieg"])
    for f in fin:
        assert f["ebene"] in gm.P["einstiege"][f["einstieg"]]["zeitebenen"] and f["filter"] in gm.FILTER
        assert f["stop"] in [s[0] for s in gm.stop_liste(f["ebene"])]
        assert f["ausstieg"] in [x[0] for x in gm.ausstieg_liste(f["ebene"])]
    assert P["quelle"]["tabelle_sha256"] == gm.yaml.safe_load(gm.FINALISTEN.read_text(encoding="utf-8"))[
        "gold_matrix_finalisten"]["tabelle_sha256"]


def test_umkehr_handelt_dieselben_signale_in_der_gegenrichtung(zm, monkeypatch):
    f = gu.teile("fehlausbruch.5m.ohne.atr2_15m.ziel_2r")
    von, bis = "2026-01-01", "2026-01-24"
    gesehen = []
    echt = gm.rechne
    monkeypatch.setattr(gm, "rechne", lambda m, e, d, dist, *a: gesehen.append((e.copy(), d.copy(), dist.copy())) or echt(m, e, d, dist, *a))
    orig, um = gm.trades_von(zm, f, von, bis), gu.trades_umkehr(zm, f, von, bis)
    (e1, d1, s1), (e2, d2, s2) = gesehen
    assert len(e1) > 30 and (e1 == e2).all() and (d2 == -d1).all() and np.array_equal(s1, s2, equal_nan=True)
    assert orig.iloc[0]["e"] == um.iloc[0]["e"] and orig.iloc[0]["d"] == -um.iloc[0]["d"]
    assert orig.iloc[0]["r_usd"] == um.iloc[0]["r_usd"]
    gleich = orig.merge(um, on="e", suffixes=("_o", "_u"))                   # Signale, die beide Läufe nehmen
    assert len(gleich) > 10 and (gleich["d_o"] == -gleich["d_u"]).all()
    rob = gu.trades_umkehr(zm, f, von, bis, gm.ROBUST)                       # derselbe erste Trade mit 1,5-fachen Kosten
    assert rob.iloc[0]["e"] == um.iloc[0]["e"] and rob.iloc[0]["r"] <= um.iloc[0]["r"]


def test_trend_filter_entscheidet_mit_der_richtung_des_originals(zm):
    f = gu.teile("ausbruch.5m.trend_hoch.atr2_15m.ziel_1r")
    orig, um = gm.trades_von(zm, f, "2026-01-01", "2026-01-24"), gu.trades_umkehr(zm, f, "2026-01-01", "2026-01-24")
    if len(orig) and len(um):                                                # erster Trade: gleiche Kerze, andere Seite
        assert orig.iloc[0]["e"] == um.iloc[0]["e"] and orig.iloc[0]["d"] == -um.iloc[0]["d"]


def test_bewertung_wie_ein_finalist_der_gold_matrix(zm, monkeypatch):
    monkeypatch.setattr(gm, "HAUPT_VON", pd.Timestamp("2026-01-01"))
    monkeypatch.setattr(gm, "MITTE", pd.Timestamp("2026-01-12"))
    monkeypatch.setattr(gm, "HAUPT_BIS", pd.Timestamp("2026-01-24"))
    monkeypatch.setattr(gm, "SPERRE_TAGE", 3)
    f = gu.teile("fehlausbruch.5m.ohne.atr2_15m.ziel_2r")
    b, tr = gu.bewerte_umkehr(zm, f)
    assert b["trades"] == len(tr) == b["h1"][1] + b["h2"][1] and b["trades"] > 30
    assert b["zufall"]["laeufe"] == len(gm.schritte(gm.kalender(zm, gm.MITTE, gm.HAUPT_BIS).tage))
    h2 = tr[tr["zeit"] >= gm.MITTE]
    e, d, dist = h2["e"].to_numpy(np.int64), h2["d"].to_numpy(np.int64), h2["r_usd"].to_numpy(float)
    kal = gm.kalender(zm, gm.MITTE, gm.HAUPT_BIS)
    tw = gm.verschiebe(kal, e, gm.schritte(kal.tage))
    s, _, _ = gm.zwillinge(zm, tw, gm.vola_faktor(zm, "15m", e, tw), d, dist, gm.MODUS["ziel"], 2.0, None, gm.nacht_r(zm, e, d, dist))
    assert b["zufall"]["z"] == pytest.approx((h2["r"].sum() - s.mean()) / s.std(), abs=1e-3)
    assert b["h2_r"] == pytest.approx(h2["r"].sum(), abs=0.05)
    og, _ = gm.bewerte_finalist(zm, f)
    assert b["original"]["h2"] == og["h2"] and b["original"]["h1"] == og["h1"]
    assert gm.urteil_finalist(b, False)[0] in ("kandidat", "durchgefallen")
    b.update(urteil="durchgefallen", holm=False, fehlt=["GF 0.9"], auswahl={})
    text = gu.bericht({"vorschau": P["vorschau"], "finalisten": {f["key"]: b}})
    assert "Von 1 umgedrehten Verlierern besteht 0." in text and "| durchgefallen |" in text
    assert "97 % des Verlusts sind also Kosten" in text and "Keine umgedrehte Variante besteht." in text


def test_ohne_siegel_und_nach_dem_ergebnis_wird_nicht_gerechnet(monkeypatch, tmp_path):
    monkeypatch.setattr(gu, "vorab_ok", lambda: False)
    with pytest.raises(SystemExit, match="Protokoll"):
        gu.main(["rechnen", "daten", "arbeit"])
    monkeypatch.setattr(gu, "vorab_ok", lambda: True)
    monkeypatch.setattr(gm, "vorab_ok", lambda: True)
    fertig = tmp_path / "ergebnis"
    fertig.with_suffix(".json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(gu, "ERGEBNIS", fertig)
    with pytest.raises(SystemExit, match="nur einmal"):
        gu.main(["rechnen", "daten", "arbeit"])


def test_falsche_tabelle_wird_abgelehnt(tmp_path):
    falsch = tmp_path / "auswahl_varianten.csv.gz"
    pd.DataFrame([zeile("pivot_abprall.5m.ohne.atr1_1h.zeit_15m", -3.9)]).to_csv(falsch, index=False)
    with pytest.raises(SystemExit, match="nicht die versiegelte Tabelle"):
        gu.pruefe_tabelle(falsch, P)
