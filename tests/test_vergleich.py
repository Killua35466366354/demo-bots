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
    assert all(b["aufstieg"]["status"] in ("sammelt", "nicht_reif", "reif") for b in v["rangliste"]
               if b["aktiv"] and b["gruppe"] != "messung")
    # Mess-Zeile "Gold nur Long" (suche/VORAB_messbots.yaml): nur C-Trades, nie ein Aufstieg, nie in der Kombi
    gl = next(b for b in v["rangliste"] if b["id"] == vg.GOLD_LONG)
    g = next(b for b in v["rangliste"] if b["id"] == vg.GOLD)
    assert gl["gruppe"] == "messung" and gl["aufstieg"]["status"] == "messung" and gl["ist"]["trades"] <= g["ist"]["trades"]
    assert vg.GOLD_LONG not in v["kombi"]["mitglieder"]
    assert vg.GOLD_START == "2026-11-03T09:05:00"               # fürs Urteil zählt nur die jetzige Regel (1-ATR-Stop)
    assert all(b["aufstieg"] is None for b in v["rangliste"] if not b["aktiv"])
    assert "| # | Strategie |" in vg.text(v) and v["tag"] == "2026-11-07"


def test_wunsch_bots_stehen_in_eigener_gruppe_und_nie_in_rangliste_oder_kombi():
    from suche import mitnutzer as mn
    v = vg.vergleich(datetime(2026, 11, 11, 8, 0, tzinfo=timezone.utc))
    w = {b["id"]: b for b in v["wunsch"]}
    assert set(w) == {b["bot"] for b in mn.aktive()} and v["wunsch_fehler"] is None
    assert {"pine-k5", "pine-tp3", "scalp-us100", "scalp-de40", "scalp-j225", "gold-staffel", "gold-grossbox"} <= set(w)
    assert not set(w) & {b["id"] for b in v["rangliste"]}
    assert not set(w) & (set(v["kombi"]["mitglieder"]) | {d["id"] for d in v["kombi"]["draussen"]})
    for bid, b in w.items():
        p = vg.J / bid / "trades.jsonl"
        n = sum(1 for z in p.read_text(encoding="utf-8").splitlines() if z.strip()) if p.exists() else 0
        assert b["ist"]["trades"] <= n and b["konto"] and b["vorab"], bid
    t = vg.text(v)
    assert "## Auf Kirons Wunsch" in t and "Pine-Gold TP 3 €" in t and "suche/VORAB_scalping_opens.yaml" in t
    assert "Der Gold-Bot zählt hier ab 2026-11-03 09:05 UTC" in t
    # die Dateien hängen weiter nur vom Tag und den Trades ab, nicht von der Uhrzeit des Laufs
    assert vg.vergleich(datetime(2026, 11, 11, 20, 0, tzinfo=timezone.utc)) == v


def test_wunsch_gruppe_haelt_den_vergleich_nie_auf(monkeypatch):
    from suche import mitnutzer as mn

    def kaputt():
        raise RuntimeError("Bot-Code fehlt")
    monkeypatch.setattr(mn, "aktive", kaputt)
    v = vg.vergleich(datetime(2026, 11, 11, 8, 0, tzinfo=timezone.utc))
    assert v["wunsch"] == [] and "nicht lesbar" in v["wunsch_fehler"] and v["rangliste"]
    assert "ließ sich nicht lesen" in vg.text(v)


def test_bots_ohne_stop_zaehlen_in_prozent():
    # Nikkei-Scalper (scalp-j225): kein Stop, darum kein R, nur Prozent vom Kurs; vorher stand er mit 0 Trades da
    ohne_r = [{"pct": 0.03, "pnl_eur": 0.01, "closed_utc": "2026-11-12T06:33:30"},
              {"pct": -0.05, "closed_utc": "2026-11-13T06:33:30"}, {"pct": None, "opened_utc": "2026-11-14T06:00:00"}]
    assert vg._einheit(ohne_r) == "pct"
    z = vg.kennzahlen(ohne_r, "pct")
    assert z["trades"] == 2 and z["summe_r"] == -0.02 and z["pf_r"] == 0.6 and z["gewonnen"] == 1
    mit_r = [{"r": -1.0, "pct": -0.3, "closed_utc": "2026-11-11T09:18:36"}, {"pct": 0.1, "closed_utc": "2026-11-12"}]
    assert vg._einheit(mit_r) == "r" and vg._einheit([]) == "r"
    v = vg.vergleich(datetime(2026, 11, 14, 8, 0, tzinfo=timezone.utc))
    assert all(b["einheit"] in ("R", "%") for b in v["wunsch"])
