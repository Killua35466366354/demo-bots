"""Gold-Duo doppelt (suche/gold_duo.py, suche/VORAB_gold_duo_doppelt.yaml): Zählung ohne Order auf einem gedachten Konto."""
import copy
import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from suche import gold_duo as gd
from suche import kombinierer as k


def regel(**konto):
    g = copy.deepcopy(gd.regel(pruefen=False))
    g["konto"].update(konto)
    return g


def t(bot, ein, aus, eur, margin=100.0, richtung=-1):
    """Ein Trade des gedachten Kontos, eur schon mit doppeltem Einsatz."""
    return {"bot": bot, "ein": pd.Timestamp(ein), "aus": None if aus is None else pd.Timestamp(aus), "eur": eur,
            "margin": margin, "richtung": richtung}


def test_regel_ist_versiegelt_und_wie_besprochen():
    g = gd.regel(pruefen=True)
    assert g is not None, "Prüfsumme von VORAB_gold_duo_doppelt.yaml fehlt im Protokoll"
    assert g["mitglieder"] == {"gold-cb": "journal/gold-trades.jsonl", "pine-k5": "journal/pine-k5/trades.jsonl"}
    assert g["start_utc"] == "2026-11-25T08:00:00"
    assert g["konto"] == {"topf_eur": 1000, "einsatz_faktor": 2, "hebel": 20, "usd_je_eur": 1.10, "bremse_pct": 30}
    u = g["urteil"]
    assert (u["ab_trades"], u["mindestens_tage"], u["pf_mindestens"]) == (100, 61, 1.3)
    assert (u["summe_eur_ueber"], u["letzte_tage"], u["summe_letzte_tage_ueber"]) == (0, 61, 0)
    assert u["zweite_haelfte_pf_mindestens"] == 1.0


def test_trades_vor_dem_start_zaehlen_nicht_und_der_einsatz_ist_doppelt(tmp_path):
    g = regel()
    (tmp_path / "journal" / "pine-k5").mkdir(parents=True)
    cb = [{"side": "short", "size": 1.0, "entry": 3900.0, "opened_utc": "2026-11-13T06:11:39.815",
           "closed_utc": "2026-11-18T07:11:27+00:00", "pnl_eur": 113.16},              # November: zählt nicht
          {"side": "long", "size": 0.5, "entry": 3600.0, "opened_utc": "2026-11-25T09:11:39.815",
           "closed_utc": "2026-11-25T15:11:27+00:00", "pnl_eur": -10.0}]
    k5 = [{"richtung": -1, "size": 0.4, "entry": 3630.0, "opened_utc": "2026-11-25T07:59:59",
           "closed_utc": "2026-11-25T12:00:00", "pnl_eur": 22.0},                      # eine Sekunde vor dem Start
          {"richtung": -1, "size": 0.4, "entry": 3630.0, "opened_utc": "2026-11-25T08:00:00",
           "closed_utc": "2026-11-25T12:00:00", "pnl_eur": 21.5},
          {"richtung": 1, "size": 0.3, "entry": 3640.0, "opened_utc": "2026-11-25T13:00:00",
           "closed_utc": "2026-11-25T14:00:00", "pnl_eur": None}]                       # ohne Ergebnis: zählt nicht
    (tmp_path / "journal" / "gold-trades.jsonl").write_text("\n".join(json.dumps(x) for x in cb) + "\n")
    (tmp_path / "journal" / "pine-k5" / "trades.jsonl").write_text("\n".join(json.dumps(x) for x in k5) + "\nkaputt\n")
    s = gd.stand(datetime(2026, 11, 27, 9, 0, tzinfo=timezone.utc), tmp_path, g)
    assert s["trades"] == 2 and s["summe_eur"] == pytest.approx(2 * 21.5 - 2 * 10.0) and s["tage"] == 2
    assert s["je_bot"] == {"gold-cb": {"trades": 1, "eur": -20.0}, "pine-k5": {"trades": 1, "eur": 43.0}}
    assert s["richtung"] == {"kauf": {"trades": 1, "eur": -20.0}, "verkauf": {"trades": 1, "eur": 43.0}}
    assert s["monate"] == {"2026-11": {"trades": 2, "eur": 23.0, "pct": 2.3}}
    assert s["urteil"] == {"status": "sammelt", "text": "2 von 100 Trades, 2 von 61 Tagen"}
    # Sicherheitsgeld: 2 x 0,4 x 3630 / 20 / 1,10 = 132 €, dazu ab 9:11 Uhr 2 x 0,5 x 3600 / 20 / 1,10 = 163,64 €
    assert s["groesste_margin_eur"] == pytest.approx(132.0 + 163.64, abs=0.01)
    json.dumps(s)                                                         # der Stand passt in journal/kombinierer.json


def test_trade_ohne_freies_sicherheitsgeld_ist_verpasst():
    g = regel()
    tr = [t("gold-cb", "2026-12-01 10:00", "2026-12-01 18:00", 50.0, margin=700.0),
          t("pine-k5", "2026-12-01 11:00", "2026-12-01 12:00", 500.0, margin=400.0),   # 700 + 400 > 1.000: verpasst
          t("pine-k5", "2026-12-01 13:00", "2026-12-01 14:00", 30.0, margin=300.0),    # 700 + 300 passt genau
          t("pine-k5", "2026-12-01 18:00", "2026-12-01 19:00", 10.0, margin=1050.0)]   # nach dem Schluss: Konto 1.080
    e = gd.zaehlen(tr, g)
    assert len(e["gebucht"]) == 3 and e["verpasst"] == {"margin": 1}
    assert e["summe_eur"] == 90.0 and e["groesste_margin_eur"] == 1050.0
    ohne = gd.zaehlen([t("pine-k5", "2026-12-01 11:00", "2026-12-01 12:00", 5.0, margin=None)], g)
    assert ohne["verpasst"] == {"margin_unbekannt": 1} and ohne["summe_eur"] == 0.0


def test_offene_position_bindet_sicherheitsgeld_und_zaehlt_noch_nicht(tmp_path):
    g = regel()
    (tmp_path / "journal" / "pine-k5").mkdir(parents=True)
    (tmp_path / "journal" / "gold-state.json").write_text(json.dumps(
        {"open_trade": {"side": "short", "size": 5.0, "entry": 3520.0, "opened_utc": "2026-12-01T09:11:38.387"}}))
    (tmp_path / "journal" / "pine-k5.json").write_text(json.dumps({"offen": [], "konto": "nie gelesen"}))
    (tmp_path / "journal" / "pine-k5" / "trades.jsonl").write_text(json.dumps(
        {"richtung": -1, "size": 1.5, "entry": 3520.0, "opened_utc": "2026-12-01T10:00:00",
         "closed_utc": "2026-12-01T11:00:00", "pnl_eur": 40.0}) + "\n")
    s = gd.stand(datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc), tmp_path, g)
    # offen: 2 x 5 x 3520 / 20 / 1,10 = 1.600 € passt nicht auf 1.000 €, die offene Position selbst zählt also nicht mit
    assert s["offen"] == 0 and s["trades"] == 1 and s["verpasst"] == {}
    (tmp_path / "journal" / "gold-state.json").write_text(json.dumps(
        {"open_trade": {"side": "short", "size": 2.0, "entry": 3520.0, "opened_utc": "2026-12-01T09:11:38.387"}}))
    s = gd.stand(datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc), tmp_path, g)
    # offen: 640 € gebunden, der Pine-Trade bräuchte 480 € dazu: verpasst
    assert s["offen"] == 1 and s["trades"] == 0 and s["verpasst"] == {"margin": 1} and s["summe_eur"] == 0.0


def test_bremse_beendet_die_zaehlung():
    g = regel()
    tr = [t("pine-k5", "2026-12-01 10:00", "2026-12-01 11:00", 100.0),      # Höchststand 1.100
          t("pine-k5", "2026-12-02 10:00", "2026-12-02 11:00", -200.0),     # 900
          t("gold-cb", "2026-12-03 10:00", "2026-12-03 11:00", -130.0),     # 770 = 30 % unter 1.100
          t("pine-k5", "2026-12-04 10:00", "2026-12-04 11:00", 500.0),      # zählt nicht mehr
          t("pine-k5", "2026-12-05 10:00", "2026-12-05 11:00", 500.0)]
    e = gd.zaehlen(tr, g)
    assert len(e["gebucht"]) == 3 and e["verpasst"] == {"bremse": 2} and e["endstand_eur"] == 770.0
    assert e["groesster_rueckgang_eur"] == 330.0 and e["bremse_seit"] == "2026-12-04 10:00:00"
    u = gd.urteil(e, g["urteil"], 200, pd.Timestamp("2027-06-01"), 30)
    assert u["status"] == "durchgefallen"
    knapp = gd.zaehlen(tr[:2] + [t("gold-cb", "2026-12-03 10:00", "2026-12-03 11:00", -129.0), tr[3]], g)
    assert knapp["bremse_seit"] is None and len(knapp["gebucht"]) == 4       # 771 € liegt noch über der Bremse


def _hundert(gewinn, verlust, start="2026-12-01"):
    """100 Trades an 100 Tagen, abwechselnd Gewinn und Verlust."""
    tage = pd.date_range(start, periods=100, freq="D")
    return [t("pine-k5", d + pd.Timedelta(hours=10), d + pd.Timedelta(hours=11), gewinn if i % 2 == 0 else -verlust)
            for i, d in enumerate(tage)]


def test_urteil_erst_nach_100_trades_und_61_tagen():
    g = regel()
    u = g["urteil"]
    tag = pd.Timestamp("2027-03-11")
    e = gd.zaehlen(_hundert(14.0, 10.0), g)
    assert gd.urteil(e, u, 60, tag)["status"] == "sammelt"                  # 100 Trades, aber erst 60 Tage
    assert gd.urteil(e, u, 61, tag)["status"] == "reif"                     # Gewinnfaktor 1,4
    kurz = gd.zaehlen(_hundert(14.0, 10.0)[:99], g)
    assert gd.urteil(kurz, u, 300, tag) == {"status": "sammelt", "text": "99 von 100 Trades, 300 von 61 Tagen"}
    schwach = gd.urteil(gd.zaehlen(_hundert(12.0, 10.0), g), u, 100, tag)
    assert schwach["status"] == "nicht_reif" and "Gewinnfaktor 1,20 unter 1,3" in schwach["text"]


def test_urteil_neuere_haelfte_und_letzte_tage():
    g = regel()
    u = g["urteil"]
    tr = _hundert(14.0, 10.0)
    for x in tr[50:]:                                                      # die neuere Hälfte verliert
        x["eur"] = 9.0 if x["eur"] > 0 else -10.0
    for x in tr[:50]:
        x["eur"] = 30.0 if x["eur"] > 0 else -10.0
    e = gd.zaehlen(tr, g)
    r = gd.urteil(e, u, 100, pd.Timestamp("2027-03-11"))
    assert r["status"] == "nicht_reif" and "neuere Hälfte Gewinnfaktor 0,90 unter 1,0" in r["text"]
    spaet = gd.urteil(gd.zaehlen(_hundert(14.0, 10.0), g), u, 400, pd.Timestamp("2027-12-31"))
    assert spaet["status"] == "nicht_reif" and "letzte 61 Tage" in spaet["text"]    # seit zwei Monaten kein Trade


def test_auskunft_ohne_die_zwei_besten_tage():
    g = regel()
    tr = [t("gold-cb", "2026-12-01 10:00", "2026-12-01 11:00", 226.0), t("pine-k5", "2026-12-02 10:00", "2026-12-02 11:00", 174.0),
          t("pine-k5", "2026-12-03 10:00", "2026-12-03 11:00", -30.0, richtung=1),
          t("pine-k5", "2026-12-04 10:00", "2026-12-04 11:00", -14.0)]
    z = gd.kennzahlen(gd.zaehlen(tr, g), g)
    assert z["beste_tage"] == [["2026-12-01", 226.0], ["2026-12-02", 174.0]] and z["ohne_zwei_beste_tage_eur"] == -44.0
    assert z["pf"] == pytest.approx(400 / 44, abs=0.01) and z["gewonnen"] == 2
    assert z["richtung"]["kauf"] == {"trades": 1, "eur": -30.0}


def test_die_echten_dateien_zaehlen_nur_ab_dem_start():
    g = gd.regel(pruefen=True)
    start = pd.Timestamp(g["start_utc"])
    alle = gd.trades(g)
    assert all(x["ein"] >= start for x in alle)
    assert all(x["margin"] is not None for x in alle), "Größe oder Einstieg fehlt in einem Trade der zwei Bots"
    s = gd.stand()
    assert s is not None and s["trades"] + sum(s["verpasst"].values()) == sum(1 for x in alle if x["aus"] is not None)


def test_saetze_ohne_doppelpunkt_und_semikolon():
    g = regel()
    leer = gd.stand(datetime(2026, 11, 25, 9, 0, tzinfo=timezone.utc), root=gd.ROOT / "gibt-es-nicht", g=g)
    assert leer["trades"] == 0 and "wartet auf den ersten gezählten Trade seit dem 25.11.2026" in leer["satz"]
    voll = {**leer, **gd.kennzahlen(gd.zaehlen(_hundert(14.0, 10.0), g), g), "summe_eur": 200.0, "endstand_eur": 1200.0,
            "groesster_rueckgang_eur": 10.0, "tage": 100,
            "urteil": {"status": "reif", "text": "reif für Kirons Entscheidung (echtes Geld nur nach seinem Ja und einem PR)"}}
    voll["satz"] = gd.satz(voll)
    assert "nach 100 Trades und 100 Tagen bei +200 €" in voll["satz"] and "reif für Kirons Entscheidung" in voll["satz"]
    for s in (leer, voll):
        prosa = [z for z in gd.abschnitt(s) if z and not z.startswith(("|", "#"))]
        assert prosa and not any(":" in z or ";" in z for z in prosa)


def test_kombinierer_zeigt_den_abschnitt_und_bleibt_bei_einem_fehler_heil(monkeypatch):
    s = k.stand(datetime(2026, 11, 25, 9, 0, tzinfo=timezone.utc))
    assert s is not None and s["gold_duo"]["start_utc"] == "2026-11-25T08:00:00"
    text = k.bericht(s)
    assert "## Gold-Duo doppelt (Zählung ohne Order)" in text and text.index("## Gold-Duo") > text.index("## Kern-Kombi")

    def kaputt(*a, **kw):
        raise ValueError("kaputt")
    monkeypatch.setattr(gd, "stand", kaputt)
    s = k.stand(datetime(2026, 11, 25, 9, 0, tzinfo=timezone.utc))
    assert s["gold_duo"] == {"fehler": "ValueError"} and s["gruppen"]["demo_gruppe"]["ohne_grenzen"]["trades"] > 0
    assert "konnte in diesem Lauf nicht rechnen (ValueError)" in k.bericht(s)
    monkeypatch.setattr(gd, "stand", lambda *a, **kw: None)                 # ohne Siegel kein Abschnitt
    s = k.stand(datetime(2026, 11, 25, 9, 0, tzinfo=timezone.utc))
    assert "gold_duo" not in s and "Gold-Duo" not in k.bericht(s)
