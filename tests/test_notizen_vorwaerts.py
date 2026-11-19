"""Vorwärts-Zählung des Kandidaten aus der Runde "Kirons Notizen": Siegel, Fassung und Urteil. Ohne Kursdaten."""
from suche import notizen_vorwaerts as nv
from suche.runde1 import journal_lines, last_value, sha256_text


def test_siegel_passt():
    assert last_value(journal_lines(), nv.KEY) == sha256_text(nv.VORAB.read_text(encoding="utf-8"))


def test_genau_die_versiegelte_fassung():
    v, cfg = nv.lade_vorab(pruefen=True)
    assert list(cfg["varianten"]) == ["ausbruch4h_welt_ziel_1r"]
    spec = cfg["varianten"]["ausbruch4h_welt_ziel_1r"]
    assert spec["maerkte"] == ["GRXEUR", "UKXGBP", "JPXJPY"] and spec["ziel_r_neu"] == 1.0
    assert v["zaehlt_ab"] == "2026-11-20"


def test_urteil():
    v, _ = nv.lade_vorab(pruefen=False)
    e = lambda n, gf, rob, s: {"trades": n, "gewinnfaktor": gf, "gewinnfaktor_robust": rob, "summe_R": s}
    assert nv.urteil(e(39, 2.0, 2.0, 9.0), v, "2027-03-01") == "zählt weiter"
    assert nv.urteil(e(10, 2.0, 2.0, 9.0), v, "2028-01-02") == "verworfen (Frist)"
    assert nv.urteil(e(40, 1.25, 1.05, 3.0), v, "2027-03-01") == "bestanden"
    assert nv.urteil(e(40, 1.25, 0.95, 3.0), v, "2027-03-01") == "zählt weiter bis 100"
    assert nv.urteil(e(40, 0.95, 0.9, -1.0), v, "2027-03-01") == "verworfen"
    assert nv.urteil(e(100, 1.1, 1.0, 2.0), v, "2027-09-01") == "verworfen"
