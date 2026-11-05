"""Vergleich der Demo-Profite und Aufstiegs-Check (suche/vergleich.py, suche/VORAB_aufstieg.yaml)."""
import json
from datetime import datetime, timezone

import pandas as pd
import yaml

from suche import vergleich as vg

REGEL = yaml.safe_load(open("suche/VORAB_aufstieg.yaml", encoding="utf-8"))["aufstieg"]


def _t(rs):
    t0 = pd.Timestamp("2027-01-01 15:00")
    return [{"r": r, "pnl_eur": r * 2, "closed_utc": (t0 + pd.Timedelta(days=i)).isoformat()} for i, r in enumerate(rs)]


def test_rule_is_registered_in_protocol():
    assert vg.regel() == REGEL, "Prüfsumme von VORAB_aufstieg.yaml fehlt im Protokoll oder ist veraltet"


def test_kennzahlen_drawdown_and_profit_factor():
    z = vg.kennzahlen(_t([1, -1, -1, 2, -0.5]))
    assert z["trades"] == 5 and z["gewonnen"] == 2 and z["summe_r"] == 0.5
    assert z["pf_r"] == round(3 / 2.5, 2) and z["rueckgang_r"] == 2.0 and z["eur"] == 1.0
    assert vg.kennzahlen(_t([1, 2]))["pf_r"] is None          # ohne Verlust: hoch


def test_single_needs_40_trades_and_all_hurdles():
    e = REGEL["einzeln"]
    assert vg.pruefe(_t([1] * 39), e, 3)["status"] == "sammelt"
    gut = [1.0, -1.0, 1.0] * 14                                  # 42 Trades, Gewinnfaktor 2
    assert vg.pruefe(_t(gut), e, 6)["status"] == "reif"
    p = vg.pruefe(_t(gut), e, 0.5)
    assert p["status"] == "nicht_reif" and "Rückgang" in p["text"]
    spaet_schlecht = [1.0] * 25 + [-1.0, -1.0, 0.5] * 5         # vorne Glück, die neuere Hälfte verliert
    p = vg.pruefe(_t(spaet_schlecht), e, 30)
    assert p["status"] == "nicht_reif" and "neuere Hälfte" in p["text"]
    p = vg.pruefe(_t([1.0, -1.0] * 20), e, 30)                    # Gewinnfaktor 1,0
    assert p["status"] == "nicht_reif" and "Gewinnfaktor" in p["text"]


def test_kombi_needs_60_trades():
    k = REGEL["kombi"]
    assert vg.pruefe(_t([1.0, -1.0, 1.0] * 19), k)["status"] == "sammelt"      # 57 Trades
    assert vg.pruefe(_t([1.0, -1.0, 1.0] * 20), k)["status"] == "reif"


def test_report_ranks_live_bots_and_kombi_only_holds_kept_strategies():
    v = vg.vergleich(datetime(2026, 11, 7, 8, 0, tzinfo=timezone.utc))
    aus = yaml.safe_load(open("suche/auswahl.yaml", encoding="utf-8"))["auswahl"]
    ids = [b["id"] for b in v["rangliste"]]
    zu = json.load(open("journal/konten.json", encoding="utf-8")).get("zuordnung") or {}
    # Eine neu behaltene Strategie steht erst in der Rangliste, wenn ersatz() ihr ein Konto gegeben hat (nächster Lauf).
    assert vg.GOLD in ids and {b for b in aus["behalten"] if b in zu} <= set(ids)
    assert [b["rang"] for b in v["rangliste"]] == list(range(1, len(ids) + 1))
    aktiv = [b["aktiv"] for b in v["rangliste"]]
    assert aktiv == sorted(aktiv, reverse=True)                 # aktive Bots zuerst
    assert set(v["kombi"]["mitglieder"]) | {d["id"] for d in v["kombi"]["draussen"]} <= set(aus["behalten"])
    assert v["regel_aufstieg"] == "festgelegt"
    assert all(b["aufstieg"]["status"] in ("sammelt", "nicht_reif", "reif") for b in v["rangliste"] if b["aktiv"])
    assert all(b["aufstieg"] is None for b in v["rangliste"] if not b["aktiv"])
    assert "| # | Strategie |" in vg.text(v) and v["tag"] == "2026-11-07"
