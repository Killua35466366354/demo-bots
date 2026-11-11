"""Gold-Zonen und News (suche/gold_zonen.py, suche/VORAB_gold_zonen.yaml): Die Rechnung hält sich an die versiegelte
Regel, schaut nie in die Zukunft und rechnet im Zweifel gegen den Trade. Alle Kurse hier sind erfunden."""
import numpy as np
import pandas as pd
import pytest

from suche import gold_zonen as gz

START = pd.Timestamp("2026-01-05 23:00")           # Montag 18:00 New York: Beginn einer 4-Std.-Kerze


def bars_aus_4h(kerzen: list[tuple]) -> pd.DataFrame:
    """Aus 4-Std.-Kerzen (o, h, l, c) 5-Minuten-Kerzen bauen: erst zum Tief, dann zum Hoch, dann zum Schluss."""
    rows = []
    for o, h, lo, c in kerzen:
        weg = np.r_[np.linspace(o, lo, 13), np.linspace(lo, h, 21)[1:], np.linspace(h, c, 17)[1:]]   # 49 Punkte
        for a, b in zip(weg[:-1], weg[1:]):
            rows.append((a, max(a, b), min(a, b), b))
    idx = pd.date_range(START, periods=len(rows), freq="5min")
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"])


def ruhig(n: int, kurs: float = 100.0) -> list[tuple]:
    return [(kurs, kurs + 1.0, kurs - 1.0, kurs)] * n


def test_4h_kerzen_und_markt_stimmen_mit_der_vorgabe():
    kerzen = ruhig(20) + [(100, 110, 99, 106)] + ruhig(10)
    m = gz.markt(bars_aus_4h(kerzen))
    assert len(m.c4) == len(kerzen) and list(np.diff(m.k_bis)) == [48] * (len(kerzen) - 1)
    assert (m.h4[20], m.l4[20], m.o4[20], m.c4[20]) == (110.0, 99.0, 100.0, 106.0)


def test_zone_aus_swing_hoch_mit_begrenzter_hoehe_und_bruch():
    o4 = np.full(40, 100.0)
    h4, l4, c4 = o4 + 1.0, o4 - 1.0, o4.copy()
    o4[20], h4[20], c4[20] = 104.0, 110.0, 106.0                 # Swing-Hoch 110, Körper bis 106
    atr = np.full(40, 2.0)
    zz = [z for z in gz.zonen(o4, h4, l4, c4, atr) if z.typ == -1 and z.aussen == 110.0]
    assert len(zz) == 1
    z = zz[0]
    assert z.k_best == 25                                         # bestätigt erst 5 Kerzen später
    assert z.innen == pytest.approx(110.0 - 0.75 * 2.0)           # 4,0 hoch wäre mehr als 0,75 ATR
    assert z.k_bruch == -1 and z.k_ende == 39
    c4[30] = 110.5                                                # Schluss über dem Hoch: Bruch
    z = next(z for z in gz.zonen(o4, h4, l4, c4, atr) if z.typ == -1 and z.aussen == 110.0)
    assert z.k_bruch == 30 and z.k_ende == 30
    atr[:] = 40.0                                                 # sehr unruhig: Zone mindestens 0,15 ATR hoch
    z = next(z for z in gz.zonen(o4, h4, l4, c4, atr) if z.typ == -1 and z.aussen == 110.0)
    assert z.innen == pytest.approx(110.0 - 0.15 * 40.0)


def test_unterstuetzung_spiegelbildlich():
    o4 = np.full(40, 100.0)
    h4, l4, c4 = o4 + 1.0, o4 - 1.0, o4.copy()
    o4[20], l4[20], c4[20] = 96.0, 90.0, 95.0
    z = next(z for z in gz.zonen(o4, h4, l4, c4, np.full(40, 10.0)) if z.typ == 1 and z.aussen == 90.0)
    assert z.innen == pytest.approx(95.0) and z.k_best == 25      # Körper-Unterkante 95, Höhe 5 liegt in 1,5 bis 7,5


def test_beruehrung_vor_der_bestaetigung_zaehlt_nicht():
    """Der Kurs läuft schon 3 Kerzen nach dem Hoch wieder an die Linie. Die Zone gilt erst nach der Bestätigung."""
    kerzen = ruhig(20) + [(100, 110, 99, 106)] + ruhig(2, 105) + [(105, 110, 104, 105)] + ruhig(8, 105)
    kerzen += [(105, 110.2, 104, 105)] + ruhig(6, 105)            # Kerze 32: zweite Berührung, nach der Bestätigung
    m = gz.markt(bars_aus_4h(kerzen))
    zz = gz.zonen(m.o4, m.h4, m.l4, m.c4, m.atr4)
    ziel = next(q for q, z in enumerate(zz) if z.typ == -1 and z.aussen == 110.0)
    assert zz[ziel].k_best == 25
    kand = [x for x in gz.kandidaten_abpraller(m, zz, "aussen", 0.5) if x["zone"] == ziel]
    assert len(kand) == 1 and kand[0]["d"] == -1 and kand[0]["fill"] == 110.0
    assert m.k_bis[31] < kand[0]["j"] <= m.k_bis[32]              # Füllung in Kerze 32, nicht in Kerze 23
    assert kand[0]["stop"] == pytest.approx(110.0 + 0.25 * zz[ziel].atr)


def test_kurslücke_hinter_die_zone_gibt_keinen_trade():
    kerzen = ruhig(20) + [(100, 110, 99, 106)] + ruhig(11, 105) + [(111, 112, 110.5, 111.5)] + ruhig(4, 111)
    m = gz.markt(bars_aus_4h(kerzen))
    zz = gz.zonen(m.o4, m.h4, m.l4, m.c4, m.atr4)
    q = next(q for q, z in enumerate(zz) if z.typ == -1 and z.aussen == 110.0)
    assert not [x for x in gz.kandidaten_abpraller(m, zz, "aussen", 0.5) if x["zone"] == q]


def klein(pfad: list[tuple]) -> gz.Markt:
    idx = pd.date_range("2026-03-02 08:00", periods=len(pfad), freq="5min")
    return gz.markt(pd.DataFrame(pfad, index=idx, columns=["open", "high", "low", "close"]))


def test_fuehrung_stop_in_der_kerze_der_fuellung_zaehlt_voll():
    m = klein([(100, 100, 97, 98)] + [(98, 99, 98, 98)] * 5)
    t = gz.fuehre(m, 1, 0, 99.0, 98.0, 103.0, 0.5, 0.0)
    assert (t["grund"], t["exit"], t["j_aus"]) == ("stop", 98.0, 0) and t["r"] == pytest.approx(-1.0)


def test_fuehrung_einstand_nach_2r_und_ziel():
    # Long 100, Stop 99 (1 R = 1), Ziel 104. Erst +2 R, dann zurück unter den Einstieg: raus am Einstand
    m = klein([(100, 100.2, 99.9, 100)] + [(100, 102.1, 100, 102)] + [(102, 102, 99.5, 99.8)] + [(99.8, 100, 99.5, 99.7)] * 3)
    t = gz.fuehre(m, 1, 0, 100.0, 99.0, 104.0, 0.5, 0.0)
    assert (t["grund"], t["exit"], t["j_aus"]) == ("einstand", 100.0, 2) and t["r"] == pytest.approx(0.0)
    # dasselbe, aber der Kurs läuft weiter bis zum Ziel
    m = klein([(100, 100.2, 99.9, 100)] + [(100, 102.1, 100, 102)] + [(102, 104.5, 101.5, 104)] + [(104, 104, 103, 103)] * 3)
    t = gz.fuehre(m, 1, 0, 100.0, 99.0, 104.0, 0.5, 0.0)
    assert (t["grund"], t["exit"], t["j_aus"]) == ("ziel", 104.0, 2) and t["r"] == pytest.approx(4.0)


def test_fuehrung_stop_und_2r_in_derselben_kerze_zaehlt_der_stop():
    m = klein([(100, 100.2, 99.9, 100)] + [(100, 102.5, 98.9, 101)] + [(101, 105, 101, 105)] * 3)
    t = gz.fuehre(m, 1, 0, 100.0, 99.0, 104.0, 0.5, 0.0)
    assert t["grund"] == "stop" and t["r"] == pytest.approx(-1.0)


def test_fuehrung_short_rechnet_stop_und_ziel_am_ask():
    # Short zum Bid 100, Stop 101: Der Ask (Bid + 0,5) erreicht 101 schon bei Bid 100,5
    m = klein([(100, 100.1, 99.9, 100)] + [(100, 100.5, 99.9, 100.2)] + [(100.2, 100.3, 100, 100.1)] * 3)
    t = gz.fuehre(m, -1, 0, 100.0, 101.0, 96.0, 0.5, 0.0)
    assert (t["grund"], t["j_aus"]) == ("stop", 1) and t["r"] == pytest.approx(-1.0)
    # Ziel 96 am Ask heißt Bid 95,5
    m = klein([(100, 100.1, 99.9, 100)] + [(100, 100, 97.4, 97.5)] + [(97.5, 97.6, 95.5, 95.6)] + [(95.6, 95.7, 95.5, 95.6)] * 3)
    t = gz.fuehre(m, -1, 0, 100.0, 101.0, 96.0, 0.5, 0.0)
    assert (t["grund"], t["exit"], t["j_aus"]) == ("ziel", 96.0, 2) and t["r"] == pytest.approx(4.0)


def test_fuehrung_zeit_um_und_uebernachtgebuehr():
    n = 14 * 288 + 5
    m = klein([(100, 100.3, 99.8, 100)] * n)
    t = gz.fuehre(m, 1, 0, 100.0, 99.0, 104.0, 0.5, 6.5)
    assert t["grund"] == "zeit" and t["j_aus"] == 14 * 288
    assert t["r"] == pytest.approx(0.0 - 6.5 / 100 / 365 * 14 * 100.0 / 1.0)      # 14 Nächte Gebühr auf den Einstieg
    kurz = klein([(100, 100.3, 99.8, 100)] * 50)
    assert gz.fuehre(kurz, 1, 0, 100.0, 99.0, 104.0, 0.5, 0.0)["grund"] == "datenende"


def test_nach_news_nur_in_den_24_stunden_vor_dem_schluss():
    m = gz.markt(bars_aus_4h(ruhig(12)))
    schluss = m.t[m.k_bis[8]] + np.timedelta64(5, "m")
    def t(stunden):
        return np.array([schluss - np.timedelta64(int(stunden * 60), "m")])
    assert gz.nach_news(m, 8, t(0)) and gz.nach_news(m, 8, t(3)) and gz.nach_news(m, 8, t(23.9))
    assert not gz.nach_news(m, 8, t(24)) and not gz.nach_news(m, 8, t(30)) and not gz.nach_news(m, 8, t(-1))
    assert not gz.nach_news(m, 8, np.array([], dtype="datetime64[ns]"))


def test_bruch_gibt_long_am_alten_hoch_mit_stop_unter_der_zone():
    kerzen = ruhig(20) + [(100, 110, 99, 106)] + ruhig(9, 105) + [(105, 113, 104.5, 112)]      # Kerze 30 schließt über 110
    kerzen += [(112, 113, 109.4, 112)] + ruhig(6, 112)                    # Kerze 31: Rücklauf, der Ask erreicht 110
    m = gz.markt(bars_aus_4h(kerzen))
    zz = gz.zonen(m.o4, m.h4, m.l4, m.c4, m.atr4)
    q = next(q for q, z in enumerate(zz) if z.typ == -1 and z.aussen == 110.0)
    assert zz[q].k_bruch == 30
    kein_termin = np.array([], dtype="datetime64[ns]")
    termin = np.array([m.t[m.k_bis[30]] - np.timedelta64(2, "h")])
    assert not [x for x in gz.kandidaten_bruch(m, zz, True, kein_termin, 0.5) if x["zone"] == q]
    for nur_news, ter in ((True, termin), (False, kein_termin)):
        [x] = [x for x in gz.kandidaten_bruch(m, zz, nur_news, ter, 0.5) if x["zone"] == q]
        assert x["d"] == 1 and x["fill"] == 110.0 and m.k_bis[30] < x["j"] <= m.k_bis[31]
        assert x["stop"] == pytest.approx(zz[q].innen - 0.25 * zz[q].atr_bruch)
    # die gebrochene Zone ist kein Abpraller mehr
    assert not [x for x in gz.kandidaten_abpraller(m, zz, "aussen", 0.5) if x["zone"] == q and x["j"] > m.k_bis[30]]


def test_ziel_ist_die_naechste_zone_der_gegenseite_ab_4r_sonst_10r():
    kerzen = ruhig(20) + [(100, 110, 99, 106)] + ruhig(14, 100)
    m = gz.markt(bars_aus_4h(kerzen))
    zz = gz.zonen(m.o4, m.h4, m.l4, m.c4, m.atr4)
    z = next(z for z in zz if z.typ == -1 and z.aussen == 110.0)
    k_best = np.array([x.k_best for x in zz])
    j = int(m.k_bis[33]) + 1
    assert gz.ziel_fuer(m, zz, k_best, j, 1, 100.0, 1.0) == pytest.approx(z.innen)             # mehr als 4 R weg
    assert gz.ziel_fuer(m, zz, k_best, j, 1, 100.0, 3.0) == pytest.approx(130.0)               # näher als 4 R: 10 R
    assert gz.ziel_fuer(m, zz, k_best, int(m.k_bis[24]) + 1, 1, 100.0, 1.0) == pytest.approx(110.0)   # noch nicht bestätigt


def test_nur_ein_trade_gleichzeitig_und_hintergrund_sperrt_die_gegenrichtung():
    n = 400
    m = klein([(100, 100.3, 99.8, 100)] * n)
    kand = [{"j": 10, "zone": 0, "d": 1, "fill": 100.0, "stop": 99.0},
            {"j": 20, "zone": 1, "d": 1, "fill": 100.0, "stop": 99.0},           # der erste Trade läuft noch
            ]
    tr = gz.handle(m, [], kand, False, 0.5, {1: 0.0, -1: 0.0})
    assert len(tr) == 1 and tr[0]["j"] == 10 and tr[0]["ziel_r"] == pytest.approx(10.0)
    m.hg[:] = 1                                                                  # Gold steigt: kein Short
    kurz = [{"j": 100, "zone": 0, "d": -1, "fill": 100.0, "stop": 101.0}]         # nach der ersten fertigen 4-Std.-Kerze
    assert gz.handle(m, [], kurz, True, 0.5, {1: 0.0, -1: 0.0}) == []
    assert len(gz.handle(m, [], kurz, False, 0.5, {1: 0.0, -1: 0.0})) == 1
    lang = [{"j": 100, "zone": 0, "d": 1, "fill": 100.0, "stop": 99.0}]
    assert len(gz.handle(m, [], lang, True, 0.5, {1: 0.0, -1: 0.0})) == 1          # Long bleibt erlaubt
    m.hg[:] = -1                                                                 # Gold fällt: kein Long
    assert gz.handle(m, [], lang, True, 0.5, {1: 0.0, -1: 0.0}) == []
    assert len(gz.handle(m, [], kurz, True, 0.5, {1: 0.0, -1: 0.0})) == 1


def test_hintergrund_wie_beim_hand_bot_nur_aus_fertigen_kerzen():
    steigt = [(100 + 0.5 * k, 101 + 0.5 * k, 99.5 + 0.5 * k, 100.5 + 0.5 * k) for k in range(6 * 70)]
    m = gz.markt(bars_aus_4h(steigt))
    assert m.hg[-1] == 1 and m.hg[100] == 0                       # 50 Tagesschlüsse fehlen am Anfang noch
    faellt = [(300 - 0.5 * k, 300.5 - 0.5 * k, 299 - 0.5 * k, 299.5 - 0.5 * k) for k in range(6 * 70)]
    assert gz.markt(bars_aus_4h(faellt)).hg[-1] == -1


def test_zufall_gleiche_richtung_fester_seed_und_holm():
    rng = np.random.default_rng(1)
    c = 100 + np.cumsum(rng.normal(0, 0.05, 6000))
    m = klein([(a, max(a, b) + 0.02, min(a, b) - 0.02, b) for a, b in zip(np.r_[100, c[:-1]], c)])
    tr = [{"j": 100, "d": 1, "r_usd": 0.5, "ziel_r": 4.0, "r": 1.0}, {"j": 900, "d": -1, "r_usd": 0.5, "ziel_r": 10.0, "r": -1.0}]
    a = gz.zufall(m, tr, 0.05, {1: 0.0, -1: 0.0}, 50, 7)
    assert a == gz.zufall(m, tr, 0.05, {1: 0.0, -1: 0.0}, 50, 7) and 1 / 51 <= a["p"] <= 1.0
    assert gz.zufall(m, [], 0.05, {1: 0.0, -1: 0.0}, 50, 7)["p"] == 1.0
    assert gz.holm({"a": 0.001, "b": 0.02, "c": 0.5}) == {"a": True, "b": True, "c": False}
    assert gz.holm({"a": 0.02, "b": 0.02, "c": 0.02}) == {"a": False, "b": False, "c": False}   # 0,02 > 0,05 / 3


def zufallsmarkt(n: int, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    c = 2000 + np.cumsum(rng.normal(0, 0.8, n))
    o = np.r_[2000.0, c[:-1]]
    idx = pd.date_range("2025-01-05 23:00", periods=n, freq="5min")
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + rng.uniform(0, 0.6, n),
                         "low": np.minimum(o, c) - rng.uniform(0, 0.6, n), "close": c}, index=idx)


def test_alle_varianten_rechnen_und_schauen_nie_in_die_zukunft():
    """Dieselben Kurse, einmal ganz und einmal früher abgeschnitten: Jeder Trade, der vor dem Schnitt fertig war, muss
    in beiden Rechnungen gleich sein. Sonst hätte die Rechnung Kurse benutzt, die es zu dem Zeitpunkt noch nicht gab."""
    bars = zufallsmarkt(40000)
    schnitt = 30000
    termine = np.sort(bars.index[[2000, 9000, 16000, 23000, 31000]].values.astype("datetime64[ns]"))
    satz = {1: 6.5, -1: 2.0}
    ganz, teil = gz.markt(bars), gz.markt(bars.iloc[:schnitt])
    zg, zt = gz.zonen(ganz.o4, ganz.h4, ganz.l4, ganz.c4, ganz.atr4), gz.zonen(teil.o4, teil.h4, teil.l4, teil.c4, teil.atr4)
    gesamt = 0
    for v in gz.regel()["varianten"]:
        a, b = gz.rechne(ganz, zg, v, termine, 0.5, satz), gz.rechne(teil, zt, v, termine, 0.5, satz)
        grenze = bars.index[schnitt - 300]                        # davor fertig: die letzte 4-Std.-Kerze ist dann auch fertig
        fa = [t for t in a if t["zeit_aus"] < grenze]
        fb = [t for t in b if t["zeit_aus"] < grenze and t["grund"] != "datenende"]
        assert fa == fb, v["key"]
        gesamt += len(fa)
        for t in a:                                               # Stop und Ziel liegen immer auf der richtigen Seite
            assert t["r_usd"] > 0 and t["ziel_r"] >= 4.0 - 1e-9 and t["d"] * (t["fill"] - t["stop"]) > 0, v["key"]
            assert t["r"] >= -1.0 - 6.5 / 100 / 365 * 15 * t["fill"] / t["r_usd"] - 1e-6 or t["grund"] in ("stop", "einstand")
    assert gesamt > 20


def test_code_und_versiegelte_regel_passen_zusammen():
    """Die Zahlen im Code sind die Zahlen der Regeldatei, und die Regeldatei steht mit ihrer Prüfsumme im Protokoll."""
    cfg = gz.regel()
    assert gz.vorab_ok()
    z = cfg["zonen"]
    assert "die 5 Hochs davor" in z["swing"] and gz.SWING == 5
    assert "mindestens 0,15 ATR und höchstens 0,75 ATR" in z["widerstand"]
    assert (gz.ZONE_MIN_ATR, gz.ZONE_MAX_ATR) == (0.15, 0.75)
    assert z["ablauf"].startswith("180 ") and gz.ABLAUF_KERZEN == 180
    assert cfg["abpraller"]["stop"].startswith("0,25 ATR") and cfg["bruch_rollenwechsel"]["stop"].startswith("0,25 ATR")
    assert gz.STOP_ATR == 0.25
    assert "30 fertige 4-Std.-Kerzen" in cfg["bruch_rollenwechsel"]["einstieg"] and gz.RUECKLAUF_KERZEN == 30
    assert "24 Stunden" in cfg["bruch_rollenwechsel"]["news"]["B_news"] and gz.NEWS_STUNDEN == 24
    f = cfg["fuehrung"]
    assert "2 R im Plus" in f["einstand"] and "mindestens 4 R" in f["ziel"] and "bei 10 R" in f["ziel"]
    assert (gz.EINSTAND_R, gz.ZIEL_MIN_R, gz.ZIEL_SONST_R) == (2.0, 4.0, 10.0)
    assert "14 Kalendertage" in f["zeit"] and gz.HALTE_TAGE == 14
    assert [v["key"] for v in cfg["varianten"]] == ["A_aussen_alle", "A_aussen_hintergrund", "A_innen_alle",
                                                    "A_innen_hintergrund", "B_news", "B_alle"]
    assert cfg["kosten"] == {"spread_usd": 0.5, "uebernacht_pct_jahr": {"long": 6.5, "short": 2.0}, "robust_faktor": 1.5,
                             "preise": cfg["kosten"]["preise"]}
    assert cfg["bewertung"]["zufall"]["laeufe"] == 1000 and cfg["bewertung"]["zufall"]["seed"] == 20261111
    assert str(gz.HAUPT_VON.date()) == "2024-01-01"


# ---------------------------------------------------------------------------------------------------------------------
# Stand "jetzt" für den Demo-Bot (gold/zonen_bot.py): Er rechnet mit Stundenkerzen und nur mit fertigen 4-Std.-Kerzen.

def stunden_vor(bars: pd.DataFrame, jetzt: pd.Timestamp) -> pd.DataFrame:
    """Die fertigen Stundenkerzen vor dem Zeitpunkt jetzt, so wie sie der Demo-Bot vom Broker bekommt."""
    st = bars[bars.index < jetzt].resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    st = st.dropna()
    return st[st.index + pd.Timedelta(hours=1) <= jetzt]


def test_fertige_4h_kerzen_und_feste_namen_der_zonen():
    kerzen = ruhig(20) + [(104, 110, 103, 106)] + ruhig(9) + [(100, 112, 99, 111)] + ruhig(10, 114.0)
    bars = bars_aus_4h(kerzen)
    m = gz.markt(bars)
    vier = pd.Timedelta(hours=4)
    assert gz.fertige_4h(m, START) == 0 and gz.fertige_4h(m, START + vier - pd.Timedelta(minutes=1)) == 0
    assert gz.fertige_4h(m, START + vier) == 1 and gz.fertige_4h(m, START + 7 * vier + pd.Timedelta(minutes=5)) == 7
    assert gz.fertige_4h(m, START + 1000 * vier) == len(kerzen)
    z = next(z for z in gz.zonen(m.o4, m.h4, m.l4, m.c4, m.atr4) if z.aussen == 110.0)
    name = gz.zonen_name(m, z)
    assert name.startswith("W2026") and len(name) == 11
    # derselbe Markt ohne die ersten 4 Kerzen (der Abruf rollt weiter): Die Zone heißt gleich
    m2 = gz.markt(bars.iloc[4 * 48:])
    z2 = next(z for z in gz.zonen(m2.o4, m2.h4, m2.l4, m2.c4, m2.atr4) if z.aussen == 110.0)
    assert gz.zonen_name(m2, z2) == name and z2.k_best == z.k_best - 4


def test_wartende_order_gilt_30_kerzen_und_endet_beim_schluss_zurueck():
    """Widerstand 110 wird in Kerze 30 gebrochen. Die Kauf-Order liegt, solange die laufende Kerze höchstens die 60. ist
    und keine fertige Kerze unter der inneren Linie geschlossen hat. Eine Berührung wird gemeldet, nicht verschwiegen."""
    kerzen = ruhig(20) + [(104, 110, 103, 106)] + ruhig(9) + [(100, 112, 99, 111)] + ruhig(40, 114.0)
    m = gz.markt(bars_aus_4h(kerzen))
    assert gz.wartende_bruch(m, 30, 0.5)[0] == []                 # Kerze 30 läuft noch: kein Bruch bekannt
    w, linien = gz.wartende_bruch(m, 31, 0.5)
    lang = [x for x in w if x["d"] == 1 and x["linie"] == 110.0]
    assert len(lang) == 1 and lang[0]["rest"] == 30 and not lang[0]["beruehrt"]
    assert lang[0]["stop"] < lang[0]["innen"] < 110.0
    assert lang[0]["stop"] == pytest.approx(lang[0]["innen"] - 0.25 * m.atr4[30])
    assert all(x > 110 for x in linien[-1]) and linien[1] == []   # als Ziel taugt nur ein gültiger Widerstand darüber
    assert [x["rest"] for x in gz.wartende_bruch(m, 60, 0.5)[0] if x["linie"] == 110.0] == [1]
    assert [x for x in gz.wartende_bruch(m, 61, 0.5)[0] if x["linie"] == 110.0] == []        # die 61. Kerze läuft: weg
    # Schluss zurück unter die innere Linie in Kerze 35: ab dann keine Order mehr
    k2 = list(kerzen)
    k2[35] = (114, 115, 105, 106)
    vor = [x for x in gz.wartende_bruch(gz.markt(bars_aus_4h(k2[:35])), 35, 0.5)[0] if x["linie"] == 110.0]
    assert len(vor) == 1 and not vor[0]["beruehrt"]               # bis zum Beginn von Kerze 35 liegt die Order
    m2 = gz.markt(bars_aus_4h(k2))
    mitten = [x for x in gz.wartende_bruch(m2, 35, 0.5)[0] if x["linie"] == 110.0]
    assert len(mitten) == 1 and mitten[0]["beruehrt"]             # Kerze 35 läuft und hat die Linie schon berührt
    assert [x for x in gz.wartende_bruch(m2, 36, 0.5)[0] if x["linie"] == 110.0] == []
    # Berührung ohne Schluss zurück (Tief 109,8, Schluss 114): die Order gälte noch, ist aber als berührt markiert
    k3 = list(kerzen)
    k3[35] = (114, 115, 109.4, 114)
    nach = [x for x in gz.wartende_bruch(gz.markt(bars_aus_4h(k3)), 36, 0.5)[0] if x["linie"] == 110.0]
    assert len(nach) == 1 and nach[0]["beruehrt"]


def test_demo_bot_sieht_vor_jeder_fuellung_dieselbe_order_und_dasselbe_ziel_wie_die_rechnung():
    """Für jede Füllung der Rechnung (B_alle): Aus den Stundenkerzen bis kurz davor muss genau diese Order als wartend
    herauskommen, mit derselben Linie, demselben Stop und demselben Ziel. Sonst handelt der Bot etwas anderes als der
    Test."""
    bars = zufallsmarkt(40000)
    m = gz.markt(bars)
    zz = gz.zonen(m.o4, m.h4, m.l4, m.c4, m.atr4)
    k_best = np.array([z.k_best for z in zz], dtype=int)
    kand = gz.kandidaten_bruch(m, zz, False, np.array([], dtype="datetime64[ns]"), 0.5)
    assert len(kand) >= 20
    for x in kand:
        jetzt, z, d = bars.index[x["j"]], zz[x["zone"]], x["d"]
        mh = gz.markt(stunden_vor(bars, jetzt))
        wartend, linien = gz.wartende_bruch(mh, gz.fertige_4h(mh, jetzt), 0.5)
        w = [w for w in wartend if w["d"] == d and abs(w["linie"] - z.aussen) < 1e-9]
        assert len(w) == 1 and not w[0]["beruehrt"], str(jetzt)
        assert w[0]["stop"] == pytest.approx(x["stop"], abs=1e-9) and w[0]["innen"] == pytest.approx(z.innen, abs=1e-9)
        assert 1 <= w[0]["rest"] <= 30
        r = abs(x["fill"] - x["stop"])
        assert gz.ziel_kurs(linien[-d], d, x["fill"], r) == pytest.approx(
            gz.ziel_fuer(m, zz, k_best, x["j"], d, x["fill"], r), abs=1e-9), str(jetzt)


def test_demo_bot_haelt_keine_order_die_die_rechnung_nicht_kennt():
    """Umgekehrt, zu vielen Zeitpunkten: Jede Order, die der Bot als wartend und unberührt sieht, gehört zu einer
    gebrochenen Zone der Rechnung, und die Rechnung hat sie nicht schon früher gefüllt."""
    bars = zufallsmarkt(40000)
    m = gz.markt(bars)
    zz = gz.zonen(m.o4, m.h4, m.l4, m.c4, m.atr4)
    fuellung = {x["zone"]: x["j"] for x in gz.kandidaten_bruch(m, zz, False, np.array([], dtype="datetime64[ns]"), 0.5)}
    geprueft = spaeter_gefuellt = 0
    for j in range(5003, 39000, 211):
        jetzt = bars.index[j]
        st = stunden_vor(bars, jetzt)
        mh = gz.markt(st)
        wartend, _ = gz.wartende_bruch(mh, gz.fertige_4h(mh, jetzt), 0.5)
        rest = bars[(bars.index >= st.index[-1] + pd.Timedelta(hours=1)) & (bars.index < jetzt)]   # seit der letzten Stunde
        for w in wartend:
            d = w["d"]
            if w["beruehrt"] or (len(rest) and ((rest["low"].min() + 0.5 <= w["linie"]) if d > 0
                                                else (rest["high"].max() >= w["linie"]))):
                continue
            q = [i for i, z in enumerate(zz) if z.typ == -d and z.k_bruch >= 0 and abs(z.aussen - w["linie"]) < 1e-9]
            assert len(q) == 1, str(jetzt)
            assert fuellung.get(q[0], j) >= j, str(jetzt)
            geprueft += 1
            spaeter_gefuellt += q[0] in fuellung
    assert geprueft >= 20 and spaeter_gefuellt >= 5
