"""Große Runde vom 19.11.2026: Siegel, Stufen-Trade, fremde Reihen ohne Blick nach vorn, Modell, Holm. Ohne Kursdaten."""
import numpy as np
import pytest

from suche import grosse_runde as gr
from suche import rueckblick as rb
from suche.runde1 import journal_lines, last_value, sha256_text


@pytest.mark.parametrize("nr", sorted(gr.DATEIEN))
def test_siegel_passt(nr):
    if not gr.vorab(nr).exists():
        pytest.skip("Durchgang noch nicht festgelegt")
    assert last_value(journal_lines(), gr.schluessel(nr)) == sha256_text(gr.vorab(nr).read_text(encoding="utf-8"))


def test_durchgang_1_hat_dreizehn_varianten_mit_eigener_regel():
    c = gr.lade_vorab(1, pruefen=False)
    assert len(c["varianten"]) == 13 and c["huerden"]["holm_anzahl"] == 26
    arten = {"umschichtung", "fed_zyklus", "zahlentag", "reihe", "tokio", "funding", "geduld", "modell"}
    for name, v in c["varianten"].items():
        assert v["regel"] == name and c["regeln"][name]["art"] in arten
    for name in ("geduld_us_ziel", "geduld_us_fern", "geduld_us_stufen"):
        assert c["varianten"][name]["maerkte"] == ["SPXUSD", "NSXUSD"]       # Rücksetzer nur dort, wo sie bisher hielten


def zufallspfad(n=600, saat=3):
    rng = np.random.default_rng(saat)
    c = 100 + np.cumsum(rng.normal(0, 0.2, n))
    o = np.r_[100.0, c[:-1]] + rng.normal(0, 0.05, n)
    h = np.maximum(o, c) + rng.uniform(0, 0.15, n)
    l = np.minimum(o, c) - rng.uniform(0, 0.15, n)
    return o, h, l, c, np.full(n, 0.02)


def test_stufen_trade_ohne_stufe_wie_ein_normaler_trade():
    o, h, l, c, sp = zufallspfad()
    for i0 in range(5, 500, 23):
        for sd, zd in ((0.8, 0.0), (0.5, 1.0), (1.5, 0.3), (3.0, 0.25)):
            for kf in (1.0, 1.5):
                alt = rb._trade(o, h, l, c, sp, i0, 1, np.nan, sd, zd, i0 + 80, kf, 0.5)
                neu = gr._trade_stufen(o, h, l, c, sp, i0, sd, zd, 10**9, 0.0, 10**9, 0.0, i0 + 80, kf, 0.5)
                assert alt[0] == neu[0] and alt[1] == pytest.approx(neu[1]) and alt[2] == pytest.approx(neu[2])


def tal(tief, zurueck, n=30):
    """Kurs 100, fällt um tief, steigt dann bis 100 plus zurueck. Kleine Kerzen, Spread 0,1."""
    p = np.r_[np.linspace(100, 100 - tief, n), np.linspace(100 - tief, 100 + zurueck, 2 * n)]
    o = np.r_[100.0, p[:-1]]
    return o, np.maximum(o, p) + 0.01, np.minimum(o, p) - 0.01, p, np.full(len(p), 0.1)


def test_stufen_trade_schliesst_auf_einstand_und_mit_kleinem_verlust():
    # Long bei 100 (Ask 100,1). Der Kurs fällt um 2 und kommt bis 100,5 zurück. Das Ziel 1,0 wird nie erreicht.
    o, h, l, c, sp = tal(2.0, 0.5)
    ohne = gr._trade_stufen(o, h, l, c, sp, 1, 5.0, 1.0, 10**9, 0.0, 10**9, 0.0, len(c) - 1, 1.0, 0.5)
    assert ohne[0] == len(c) - 1 and ohne[1] == pytest.approx(o[-1] - ohne[2])          # hält bis zum Zeit-Ausstieg
    # Ab Kerze 20 reicht der Einstand: Ausstieg, sobald der Bid den Einstiegskurs (Ask) wieder erreicht, Ergebnis 0.
    einstand = gr._trade_stufen(o, h, l, c, sp, 1, 5.0, 1.0, 20, 0.0, 10**9, 0.0, len(c) - 1, 1.0, 0.5)
    assert einstand[1] == pytest.approx(0.0) and einstand[0] < len(c) - 1
    # Ab Kerze 25 reicht ein Verlust von 0,8: der Ausstieg kommt früher und kostet genau 0,8.
    klein = gr._trade_stufen(o, h, l, c, sp, 1, 5.0, 1.0, 20, 0.0, 25, -0.8, len(c) - 1, 1.0, 0.5)
    assert klein[1] == pytest.approx(-0.8) and klein[0] < einstand[0]
    # Der Stop gilt immer: liegt er näher als das Tal, endet der Trade dort (halber Spread schlechter).
    stop = gr._trade_stufen(o, h, l, c, sp, 1, 1.0, 1.0, 20, 0.0, 25, -0.8, len(c) - 1, 1.0, 0.5)
    assert stop[1] == pytest.approx(-1.0 - 0.1 - 0.05, abs=0.02)


def test_stufen_trade_wechsel_ueber_dem_neuen_ziel_zaehlt_die_eroeffnung():
    # Der Kurs steht beim Wechsel leicht im Plus (unter dem ersten Ziel). Mit dem Wechsel auf Einstand wird sofort
    # zur Eröffnung geschlossen, nicht erst am Ziel.
    n = 40
    p = np.r_[np.linspace(100, 100.6, 10), np.full(n - 10, 100.6)]
    o = np.r_[100.0, p[:-1]]
    h, l, sp = np.maximum(o, p) + 0.01, np.minimum(o, p) - 0.01, np.full(n, 0.1)
    ex, pnl, e = gr._trade_stufen(o, h, l, p, sp, 1, 5.0, 2.0, 15, 0.0, 10**9, 0.0, n - 1, 1.0, 0.5)
    assert ex == 15 and pnl == pytest.approx(o[15] - e) and pnl > 0


def test_fremde_reihe_nur_werte_vor_dem_handelstag(monkeypatch):
    tage = np.arange("2024-01-01", "2024-01-11", dtype="datetime64[D]")
    werte = np.arange(10.0)
    monkeypatch.setattr(gr, "fred", lambda name: (tage, werte))
    handelstage = np.array(["2024-01-01", "2024-01-05", "2024-01-08", "2024-02-01"], dtype="datetime64[D]")
    w, d = gr.vor("X", handelstage)
    assert np.isnan(w[0]) and np.isnat(d[0])                         # vor dem ersten Wert gibt es nichts
    assert list(w[1:]) == [3.0, 6.0, 9.0] and all(d[1:] < handelstage[1:])
    w1, _ = gr.vor("X", handelstage, 1)
    assert list(w1[1:]) == [2.0, 5.0, 8.0]
    wl, dl = gr.vor("X", handelstage, 0, 1)                           # Reihe erscheint einen Tag später
    assert list(wl[1:]) == [2.0, 5.0, 9.0] and all(dl[1:] < handelstage[1:] - np.timedelta64(1, "D"))


def test_richtung_reihe_sprung_und_frische(monkeypatch):
    tage = np.array(["2024-03-04", "2024-03-05", "2024-03-06", "2024-03-07", "2024-03-08"], dtype="datetime64[D]")
    monkeypatch.setattr(gr, "fred", lambda name: (tage, np.array([20.0, 20.5, 23.0, 22.0, 30.0])))
    p = {"reihe": "VIX", "tage": 1, "relativ": True, "nur_anstieg": True, "schwelle": 0.10, "vorzeichen": 1,
         "frisch_tage": 3}
    gtag = np.array(["2024-03-06", "2024-03-07", "2024-03-08", "2024-03-11", "2024-03-18"], dtype="datetime64[D]")
    # 07.03.: Sprung am 06.03. von 20,5 auf 23 (+12 %). 11.03. (Montag): Sprung am Freitag (+36 %), drei Tage alt.
    # 18.03.: derselbe Wert wäre zehn Tage alt und zählt nicht mehr.
    assert list(gr.richtung_reihe(gtag, p)) == [0, 1, 0, 1, 0]
    beide = {**p, "relativ": False, "nur_anstieg": False, "schwelle": 1.0, "vorzeichen": -1}
    assert list(gr.richtung_reihe(gtag, beide)) == [0, -1, 1, -1, 0]


def test_fed_zyklus_nur_gerade_wochen_und_nie_in_die_naechste_woche_null():
    gtag = np.arange("2024-01-01", "2024-04-10", dtype="datetime64[D]")
    gtag = gtag[np.is_busday(gtag)]
    fomc = np.array([gtag[10], gtag[35]])
    r = gr.richtung_fed_zyklus(gtag, fomc, [[9, 13], [19, 23], [29, 33]])
    an = set(np.flatnonzero(r).tolist())
    # nach dem ersten Entscheid: Tage 19 bis 23 und 29 bis 33, Woche 6 (ab Tag 39) nur bis vor Tag -1 des zweiten
    assert an >= set(range(19, 24)) | set(range(29, 34)) and 34 not in an and 35 not in an
    assert not (an & set(range(0, 19))) and not (an & set(range(24, 29)))
    assert set(range(44, 49)) <= an                                   # Woche 2 nach dem zweiten Entscheid


def test_modell_lernt_nur_aus_frueheren_jahren():
    rng = np.random.default_rng(5)
    n = 2400
    tage = np.datetime64("2015-01-01") + np.arange(n) * np.timedelta64(1, "D")
    X = rng.normal(size=(n, 4))
    y = (X[:, 0] + 0.5 * rng.normal(size=n) > 0).astype(float)
    p = {"strafe": 1.0, "min_lernzeilen": 300, "min_lernjahre": 2}
    q = gr.vorhersagen(tage, X, y, p)
    jahr = tage.astype("datetime64[Y]").astype(int) + 1970
    assert np.isnan(q[jahr <= 2016]).all() and np.isfinite(q[jahr >= 2017]).all()
    treffer = ((q[jahr >= 2017] > 0.5) == (y[jahr >= 2017] > 0.5)).mean()
    assert treffer > 0.8                                              # das Modell findet den eingebauten Zusammenhang
    # Die Zukunft ändert nichts an einer Vorhersage: Ergebnisse ab 2019 vertauschen lässt 2017 und 2018 gleich.
    y2 = y.copy()
    y2[jahr >= 2019] = 1.0 - y2[jahr >= 2019]
    q2 = gr.vorhersagen(tage, X, y2, p)
    assert np.allclose(q[(jahr == 2017) | (jahr == 2018)], q2[(jahr == 2017) | (jahr == 2018)])
    assert np.allclose(q[jahr == 2019], q2[jahr == 2019])             # 2019 lernt nur aus den Jahren davor


def _ergebnis(p, trades=300):
    return {"trades": trades, "gewinnfaktor": 1.5, "gewinnfaktor_robust": 1.3,
            "haelfte_1": {"gewinnfaktor": 1.4}, "haelfte_2": {"gewinnfaktor": 1.6},
            "jahr_2026": {"trades": 50, "gewinnfaktor": 1.3},
            "zufall": {"p": p, "geschlagen_pct": 100.0 * (1 - p), "z": 3.5}}


def test_holm_zaehlt_mit_der_festen_gesamtzahl():
    h = {"min_trades": 100, "min_gewinnfaktor": 1.2, "min_robust": 1.0, "jahr_2026_ab_trades": 20, "min_rang_pct": 95,
         "holm_alpha": 0.05, "holm_anzahl": 26, "min_z": 3.0}
    cfg = {"huerden": h, "varianten": {"a": {}, "b": {}}}
    erg = {"a": _ergebnis(0.0019), "b": _ergebnis(0.004)}
    gr.urteile(erg, cfg)
    assert erg["a"]["urteil"] == "bestanden" and erg["a"]["holm"]     # 0,0019 <= 0,05 / 26
    assert erg["b"]["urteil"] == "Kandidat" and not erg["b"]["holm"]  # 0,004 > 0,05 / 25
    erg = {"a": _ergebnis(0.0021), "b": _ergebnis(0.0019)}
    gr.urteile(erg, cfg)
    assert erg["a"]["urteil"] == "Kandidat" and erg["b"]["urteil"] == "bestanden"       # Rang 2 braucht 0,05 / 25 = 0,002
    erg = {"a": _ergebnis(0.0020), "b": _ergebnis(0.0019), "c": _ergebnis(0.5)}
    gr.urteile(erg, {"huerden": h, "varianten": {"a": {}, "b": {}, "c": {}}})
    assert erg["a"]["urteil"] == "bestanden" and erg["c"]["urteil"] == "durchgefallen"
    # In Durchgang 2 kann eine Variante höchstens Kandidat werden.
    cfg2 = {"huerden": {**h, "hoechstens_kandidat": True}, "varianten": {"a": {}}}
    erg = {"a": _ergebnis(0.0015)}
    gr.urteile(erg, cfg2)
    assert erg["a"]["urteil"] == "Kandidat" and "hinweis" in erg["a"]
