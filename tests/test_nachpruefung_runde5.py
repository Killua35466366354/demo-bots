"""Nachtrag zur Nachprüfung 2024-26 für Runde 5 (suche/nachpruefung_runde5.py). Alle Trades hier sind erfunden."""
import json

import pandas as pd

from suche import nachpruefung_runde5 as n5


def trades(von: str, anzahl: int, r: list[float], schritt_tage: int = 7) -> list[dict]:
    tage = pd.date_range(von, periods=anzahl, freq=f"{schritt_tage}D")
    return [{"datum": str(t.date()), "d": 1, "r": r[k % len(r)], "pct": 0.0, "grund": "signal", "tage": 3}
            for k, t in enumerate(tage)]


def ordner(tmp_path, r5: dict, r5b: dict, klassen: dict):
    d = tmp_path / "runde5"
    d.mkdir()
    (d / "runde5_trades.json").write_text(json.dumps(r5), encoding="utf-8")
    (d / "runde5b_trades.json").write_text(json.dumps(r5b), encoding="utf-8")
    (d / "runde5.json").write_text(json.dumps({"maerkte": {s: {"klasse": k} for s, k in klassen.items()}}), encoding="utf-8")
    return tmp_path


def test_strategie_ueber_alle_maerkte_und_urteil(tmp_path):
    gut = trades("2024-01-08", 76, [2.0, -1.0])                  # je Markt 76 Trades ab 2024, Gewinnfaktor 2
    alt = trades("2019-01-07", 40, [-1.0, 0.5])                  # vor 2024 schlecht: zählt nur als Auskunft
    r5 = {"EURUSD": {"tsmom_12m": alt + gut, "ewmac": trades("2024-01-08", 60, [-1.0, 0.5])},
          "XAUUSD": {"tsmom_12m": gut}, "SPXUSD": {"rsi2_index": trades("2024-02-05", 30, [1.0, -1.0])}}
    res = n5.lesen(ordner(tmp_path, r5, {"SPXUSD": {"trend_ruecksetzer": gut}, "NSXUSD": {"trend_ruecksetzer": gut}},
                          {"EURUSD": "fx", "XAUUSD": "metall", "SPXUSD": "index_us"}))
    v = {z["name"]: z for z in res["varianten"]}
    ts = v[n5.NAMEN["tsmom_12m"]]
    assert ts["trades"] == 152 and ts["maerkte"] == 2 and ts["pf"] == 2.0 and ts["bestanden"]
    assert ts["vor_2024_auskunft"]["trades"] == 40 and ts["vor_2024_auskunft"]["pf"] < 1      # nur Auskunft
    assert ts["robust_pf"] is None and ts["zufall"] is None                                   # gibt es hier nicht
    ew = v[n5.NAMEN["ewmac"]]
    assert not ew["bestanden"] and any("Trades" in f for f in ew["fehlt"]) and any("GF" in f for f in ew["fehlt"])
    assert not v[n5.NAMEN["rsi2_index"]]["bestanden"]                                         # nur 30 Trades
    us = v[n5.US["trend_ruecksetzer"]]
    assert us["quelle"] == "Runde 5b" and us["trades"] == 152 and us["bestanden"]
    assert res["bestehen"] == [n5.NAMEN["tsmom_12m"], n5.US["trend_ruecksetzer"]]
    assert [z["name"] for z in res["varianten"]][:2] == [n5.NAMEN["ewmac"], n5.NAMEN["tsmom_12m"]]   # Trendfolger zuerst


def test_je_klasse_ist_nur_auskunft_und_bericht_nennt_was_fehlt(tmp_path):
    r5 = {"EURUSD": {"tsmom_12m": trades("2024-01-08", 60, [-1.0, 0.5])},
          "XAUUSD": {"tsmom_12m": trades("2024-01-08", 60, [3.0, -1.0])}}
    res = n5.lesen(ordner(tmp_path, r5, {}, {"EURUSD": "fx", "XAUUSD": "metall"}))
    kl = {a["name"]: a for a in res["trendfolger_je_klasse_nur_auskunft"]}
    assert kl[n5.NAMEN["tsmom_12m"] + ", nur metall"]["pf"] == 3.0
    assert kl[n5.NAMEN["tsmom_12m"] + ", nur fx"]["pf"] == 0.5
    assert all("bestanden" not in a for a in kl.values())                                     # daraus besteht nichts
    text = n5.bericht(res)
    assert "1 Varianten gelesen" in text and "keinen Zufallsvergleich" in text and "nur Auskunft" in text.replace("Nur", "nur")
