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


# ---------------------------------------------------------------------------------------------------------------------
# Durchgang 2: Reihe gegen ihr Quantil, Geduld-Ausstieg nach einem Signal, Schluss-Schub, runde Marken, Fonds-Fenster.
# Alles auf erfundenen Kerzen (Januar und Februar 2024, New York ist dann UTC minus 5, London ist UTC).

CFG = {"daten": {"min_kerzen_je_tag": 60, "pause_min": 60, "krypto_alle_tage": ["BTCUSD"]}, "trend": {"vorlauf_tage": 100},
       "tageshandel": {"toleranz_min": 540, "aus_min": 955}}
TAGE = np.arange("2024-01-02", "2024-02-10", dtype="datetime64[D]")


def kunstmarkt(tmp_path, sym, kurs, alle_tage=False, von_min=60, bis_min=1395):
    """Schreibt <sym>.npz mit 5-Minuten-Kerzen und lädt den Markt. kurs(tag, minute) gibt die Eröffnung der Kerze,
    minute zählt ab 17:00 New York am Vorabend. Hoch und Tief liegen 0,01 % um Eröffnung und Schluss."""
    tage = TAGE if alle_tage else TAGE[np.is_busday(TAGE)]
    t, o, tag = [], [], []
    for d in tage:
        start = d.astype("datetime64[ns]") - np.timedelta64(2, "h")          # 17:00 New York am Vorabend = 22:00 UTC
        for minute in range(von_min, bis_min + 5, 5):
            t.append(start + np.timedelta64(minute, "m"))
            o.append(float(kurs(d, minute)))
            tag.append(d)
    t, o = np.array(t), np.array(o)
    c = np.r_[o[1:], o[-1]]
    nymin = ((t - t.astype("datetime64[D]")).astype("timedelta64[m]").astype(np.int64) - 300) % 1440
    np.savez(tmp_path / f"{sym}.npz", t=t, o=o, h=np.maximum(o, c) * 1.0001, l=np.minimum(o, c) * 0.9999, c=c,
             sp=np.full(len(t), 0.5), nymin=nymin.astype(np.int32), tag=np.array(tag), prof=np.full(96, 0.5))
    return gr.Markt(sym, tmp_path, CFG)


def ny(tag, stunde, minute=0):
    return np.datetime64(tag, "ns") + np.timedelta64(stunde * 60 + minute + 300, "m")


def test_reihe_gegen_ihr_eigenes_quantil(monkeypatch):
    tage = np.arange("2024-03-01", "2024-03-21", dtype="datetime64[D]")
    werte = np.r_[np.arange(10.0), 3.0, 30.0, 4.0, 5.0, 40.0, 6.0, 7.0, 8.0, 9.0, 50.0]
    monkeypatch.setattr(gr, "fred", lambda name: (tage, werte))
    p = {"reihe": "X", "niveau": True, "quantil": {"fenster": 5, "q": 0.8}, "nur_anstieg": True, "vorzeichen": 1,
         "frisch_tage": 3, "lag": 1}
    gtag = tage[5:] + np.timedelta64(2, "D")              # mit lag 1 sieht der Handelstag den Wert von vorgestern
    r = gr.richtung_reihe(gtag, p)
    q = gr.quantil_vor(gtag, p)
    for k, g in enumerate(gtag):
        i = int(np.flatnonzero(tage == g - np.timedelta64(2, "D"))[0])
        assert q[k] == pytest.approx(np.quantile(werte[i - 5:i], 0.8))          # nur die fünf Werte davor
        assert r[k] == int(werte[i] >= np.quantile(werte[i - 5:i], 0.8))
    assert r.sum() >= 3 and r[np.flatnonzero(tage[5:] == np.datetime64("2024-03-11"))[0]] == 0      # der Wert 3 ist kein Hoch
    with pytest.raises(SystemExit):
        gr.richtung_reihe(gtag, {**p, "nur_anstieg": False})


def test_tagestrade_mit_geduld_ausstieg(tmp_path):
    m = kunstmarkt(tmp_path, "SPXUSD", lambda d, minute: 5000.0 + 3.0 * np.sin(minute / 90.0))
    g = 18
    richtung = np.zeros(len(m.gtag), np.int64)
    richtung[g] = 1
    ohne = gr._tagestrades(m, CFG, richtung, 3.0)[0]
    mit = gr._tagestrades(m, CFG, richtung, 3.0, 1, {"ziel_atr": 0.25, "stufen": [[2, 0.0], [4, -0.5]], "max_tage": 10})[0]
    atr = m.atr_vor[g]
    assert ohne["zd"] == 0.0 and "stufen" not in ohne and ohne["t_max"] == ny(m.gtag[g], 15, 55)
    assert mit["i0"] == ohne["i0"] and m.t[mit["i0"]] == ny(m.gtag[g] - np.timedelta64(1, "D"), 18)
    assert mit["zd"] == pytest.approx(0.25 * atr) and mit["sd"] == pytest.approx(3.0 * atr)
    assert mit["stufen"] == ((2, 0.0), (4, pytest.approx(-0.5 * atr))) and mit["t_max"] == ny(m.gtag[g + 10], 15, 55)
    tr = gr.echte_trades(m, [mit], {**CFG, "kosten": {"rutschen_spread": 0.5, "robust_faktor": 1.5,
                                                         "nacht_pro_jahr": {"index": {"long": 0.065, "short": 0.02}}}})
    assert len(tr) == 1 and tr["w1"][0] == 2 and tr["w2"][0] == 4


def test_schluss_schub_nur_an_tagen_mit_grosser_bewegung(tmp_path):
    gross, klein = np.datetime64("2024-01-30"), np.datetime64("2024-02-01")

    def kurs(d, minute):
        if d == gross:
            return 5000.0 * (1.0 + 0.02 * min(minute, 1350) / 1350.0)        # steigt bis 15:30 New York um 2 %
        if d == klein:
            return 5100.0 * (1.0 - 0.012 * min(minute, 1350) / 1350.0)       # fällt um 1,2 %, unter der Schwelle
        return 5000.0 if d < gross else 5100.0
    m = kunstmarkt(tmp_path, "NSXUSD", kurs)
    p = {"ein_min": 930, "aus_min": 955, "toleranz_min": 10, "schwelle": {"NSXUSD": 0.015}, "stop_anteil": 0.004}
    sig = gr.regel_schluss_schub(m, CFG, p)
    assert len(sig) == 1
    s = sig[0]
    assert m.t[s["i0"]] == ny(gross, 15, 30) and s["d"] == 1 and s["t_max"] == ny(gross, 15, 55)
    assert s["sd"] == pytest.approx(0.004 * m.o[s["i0"]]) and s["zd"] == 0.0
    sig = gr.regel_schluss_schub(m, CFG, {**p, "schwelle": {"NSXUSD": 0.01}})
    assert [x["d"] for x in sig] == [1, -1]                                    # mit 1,0 % zählt auch der schwache Tag


def marken_kerzen(schluss_je_kerze, start="2024-01-10T06:00"):
    c = np.asarray(schluss_je_kerze, float)
    t = np.datetime64(start, "ns") + np.arange(len(c)) * np.timedelta64(5, "m")
    o = np.r_[c[0], c[:-1]]
    return t, np.maximum(o, c), np.minimum(o, c), c


P_MARKE = {"marke_pips": 100, "abstand_pips": 5, "vorher_min": 120, "luecke_min": 10, "von_min": 480, "bis_min": 1020}


def test_runde_marke_erster_schluss_nach_zwei_stunden_auf_der_anderen_Seite():
    # ab 06:00 London drei Stunden unter 1,0800, dann ein Schluss 6 Pips darüber, Rücklauf, zweiter Ausbruch
    c = np.r_[np.full(36, 1.0790), 1.08060, np.full(30, 1.0785), 1.08070, np.full(5, 1.0810)]
    t, h, l, c = marken_kerzen(c)
    sig = gr.marken_signale(t, h, l, c, 0.0001, P_MARKE)
    assert sig == [(36, 1)]                                # der zweite Ausbruch ist nicht mehr der erste des Tages
    # genau 5 Pips darüber zählt nicht (mehr als 5), und nach nur einer Stunde darunter zählt es auch nicht
    assert gr.marken_signale(*marken_kerzen(np.r_[np.full(36, 1.0790), 1.08050, 1.0790]), 0.0001, P_MARKE) == []
    kurz = np.r_[np.full(20, 1.0810), np.full(12, 1.0790), 1.08060, 1.0806]
    assert gr.marken_signale(*marken_kerzen(kurz), 0.0001, P_MARKE) == []
    # nach unten, im Yen (Marke 152,00, Pip 0,01)
    t, h, l, c = marken_kerzen(np.r_[np.full(40, 152.30), 151.93, 151.90])
    assert gr.marken_signale(t, h, l, c, 0.01, P_MARKE) == [(40, -1)]
    # vor 8 Uhr London gibt es kein Signal, und der Ausbruch gilt für den Tag als verbraucht
    frueh = np.r_[np.full(30, 1.0790), 1.08060, np.full(30, 1.0785), 1.08070]
    assert gr.marken_signale(*marken_kerzen(frueh, "2024-01-10T05:00"), 0.0001, P_MARKE) == []


def test_fonds_fenster_handelt_gegen_die_bewegung_der_fensterstunde(tmp_path):
    hoch, flach = np.datetime64("2024-01-30"), np.datetime64("2024-01-31")

    def kurs(d, minute):                                   # minute 1320 = 15:00 New York, 1380 = 16:00
        if d == hoch and minute >= 1320:
            return 40000.0 * (1.0 + 0.01 * min(minute - 1320, 60) / 60.0)
        if d == flach and minute >= 1320:
            return 40400.0 * (1.0 + 0.002 * min(minute - 1320, 60) / 60.0)
        return 40000.0 if d <= hoch else 40400.0
    kunstmarkt(tmp_path, "SPXUSD", lambda d, minute: 5000.0)
    m = kunstmarkt(tmp_path, "BTCUSD", kurs, alle_tage=True, von_min=0, bis_min=1435)
    p = {"boersentage": "SPXUSD", "von_min": 900, "bis_min": 960, "ein_min": 965, "aus_min": 1200, "toleranz_min": 10,
         "schwelle": 0.005, "ziel_anteil": 0.6, "stop_anteil": 1.0}
    sig = gr.regel_fonds_fenster(m, CFG, p)
    assert len(sig) == 1                                   # 0,2 % am zweiten Tag reichen nicht, am Wochenende gibt es kein Fenster
    s = sig[0]
    assert m.t[s["i0"]] == ny(hoch, 16, 5) and s["d"] == -1 and s["t_max"] == ny(hoch, 20)
    assert s["sd"] == pytest.approx(400.0) and s["zd"] == pytest.approx(240.0)


def test_us_schreck_kauft_am_naechsten_tokioter_morgen(tmp_path):
    fall, freitag = np.datetime64("2024-01-30"), np.datetime64("2024-02-02")

    def us(d, minute):                                     # zwei Tage mit minus 2 %, einer davon ein Freitag
        stufe = 5000.0 * 0.98 ** (int(d >= fall) + int(d >= freitag))
        return stufe / 0.98 if d in (fall, freitag) and minute < 1200 else stufe
    kunstmarkt(tmp_path, "SPXUSD", us)
    m = kunstmarkt(tmp_path, "USDJPY", lambda d, minute: 150.0 + 0.2 * np.sin(minute / 70.0), von_min=0, bis_min=1435)
    p = {"signal_markt": "SPXUSD", "schwelle": 0.015, "ein_min": 540, "aus_min": 900, "toleranz_min": 10, "stop_atr": 1.0}
    sig = gr.regel_us_schreck(m, CFG, p)
    assert len(sig) == 2 and all(s["d"] == 1 and s["zd"] == 0.0 for s in sig)
    a, b = sig
    assert m.t[a["i0"]] == np.datetime64("2024-01-31T00:00", "ns")              # 9:00 Tokio am Tag danach
    assert a["t_max"] == np.datetime64("2024-01-31T06:00", "ns")                # 15:00 Tokio
    assert m.t[b["i0"]] == np.datetime64("2024-02-05T00:00", "ns")              # nach dem Freitag erst am Montag
    g = m.gpos[m.tix[a["i0"]]]
    assert m.gtag[g] == np.datetime64("2024-01-31") and a["sd"] == pytest.approx(m.atr_vor[g])
    assert gr.signale("x", m, {**CFG, "regeln": {"x": {**p, "art": "us_schreck"}}}, np.array([])) == sig


def test_verfallstage_dritter_freitag_und_feiertag():
    tage = np.arange("2025-03-03", "2025-06-01", dtype="datetime64[D]")
    gtag = tage[np.is_busday(tage) & (tage != np.datetime64("2025-04-18"))]      # Karfreitag fehlt in den Kursen
    assert list(gtag[gr.verfallstage(gtag, 3)]) == [np.datetime64(x) for x in ("2025-03-21", "2025-04-17", "2025-05-16")]
    assert list(gtag[gr.verfallstage(gtag, 2)]) == [np.datetime64(x) for x in ("2025-03-14", "2025-04-11", "2025-05-09")]
    assert len(gr.verfallstage(gtag[:10], 3)) == 0                               # der dritte Freitag liegt hinter den Kursen


def test_verfallstag_morgen_kauft_am_vorabend_und_verkauft_nach_der_abrechnung(tmp_path):
    m = kunstmarkt(tmp_path, "SPXUSD", lambda d, minute: 5000.0 + 2.0 * np.sin(minute / 80.0))
    p = {"toleranz_min": 10, "stop_anteil": 0.0075,
         "ort": {"SPXUSD": {"zone": "America/New_York", "nummer": 3, "kauf_min": 960, "wechsel_min": 570,
                            "short_min": 575, "aus_min": 720}}}
    sig = gr.regel_verfallstag(m, CFG, p)
    assert len(sig) == 2                                   # im Januar 2024 ist der 19. der dritte Freitag, im Februar endet der Markt vorher
    kauf, short = sig
    assert m.t[kauf["i0"]] == ny("2024-01-18", 16) and kauf["d"] == 1 and kauf["t_max"] == ny("2024-01-19", 9, 30)
    assert m.t[short["i0"]] == ny("2024-01-19", 9, 35) and short["d"] == -1 and short["t_max"] == ny("2024-01-19", 12)
    assert kauf["sd"] == pytest.approx(0.0075 * m.o[kauf["i0"]]) and kauf["zd"] == 0.0
    tokio = {"toleranz_min": 10, "stop_anteil": 0.0075,
             "ort": {"SPXUSD": {"zone": "Asia/Tokyo", "nummer": 2, "kauf_min": 900, "wechsel_min": 540,
                                "short_min": 545, "aus_min": 690}}}
    k1, s1, k2, s2 = gr.regel_verfallstag(m, CFG, tokio)                         # zweiter Freitag im Januar und im Februar
    assert m.t[k1["i0"]] == np.datetime64("2024-01-11T06:00", "ns") and k1["t_max"] == np.datetime64("2024-01-12T00:00", "ns")
    assert m.t[s1["i0"]] == np.datetime64("2024-01-12T00:05", "ns") and s1["t_max"] == np.datetime64("2024-01-12T02:30", "ns")
    assert m.t[k2["i0"]] == np.datetime64("2024-02-08T06:00", "ns") and m.t[s2["i0"]] == np.datetime64("2024-02-09T00:05", "ns")
    tr = gr.echte_trades(m, [k2, s2], {**CFG, "kosten": {"rutschen_spread": 0.5, "robust_faktor": 1.5,
                                                         "nacht_pro_jahr": {"index": {"long": 0.065, "short": 0.02}}}})
    assert len(tr) == 2 and list(tr["richtung"]) == [1, -1]                      # der zweite Teil beginnt nach dem ersten
    assert tr["aus_utc"].iloc[0] == np.datetime64("2024-02-09T00:00", "ns")
    assert tr["gebuehr_R"].iloc[0] > 0 and tr["gebuehr_R"].iloc[1] == 0          # nur der erste Teil hält über 17:00 New York


def test_durchgang_2_hoechstens_dreizehn_und_nur_kandidat():
    if not gr.vorab(2).exists():
        pytest.skip("Durchgang noch nicht festgelegt")
    c = gr.lade_vorab(2, pruefen=False)
    assert 1 <= len(c["varianten"]) <= 13 and c["huerden"]["holm_anzahl"] == 26 and c["huerden"]["hoechstens_kandidat"] is True
    eins = gr.lade_vorab(1, pruefen=False)
    assert not set(c["varianten"]) & set(eins["varianten"])
    for k in ("kosten", "zwilling", "tageshandel"):
        assert c[k] == eins[k]                             # dieselbe Rechnung wie in Durchgang 1
    for k in ("von", "bis", "mitte"):
        assert c["fenster"][k] == eins["fenster"][k]       # dasselbe Fenster und dieselben Hälften
    for name, v in c["varianten"].items():
        assert v["regel"] == name and name in c["regeln"]
