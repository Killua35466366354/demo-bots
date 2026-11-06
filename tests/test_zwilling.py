"""Zwillinge (suche/VORAB_zwilling.yaml, suche/zwilling.py, suche/zwillinge.yaml).

Kirons Zusatz vom 06.11.2026, 10:25 UTC und seine Wahl von 15:22 UTC: Verbesserungen laufen als Zwilling neben dem
unveränderten Original und ersetzen es erst, wenn sie sich bewiesen haben; VORAB_wechsel.yaml gilt weiter. Läuft nur
bei PRs und lokal (nicht im Demo-Bots-Lauf), damit ein Fehler hier nie die Bots aufhält."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
import yaml

from suche import demo_pruefung as dp
from suche import vergleich as vg
from suche import zwilling as zw
from suche.runde3 import sha256_text

RG = yaml.safe_load(open("suche/VORAB_zwilling.yaml", encoding="utf-8"))["zwilling"]
T0 = "2026-12-01T00:00:00"


def _t(rs, bot="z", ab=T0, tage=1.0):
    t0 = pd.Timestamp(ab)
    return [{"bot": bot, "r": r, "closed_utc": (t0 + pd.Timedelta(days=tage * (i + 1))).isoformat()}
            for i, r in enumerate(rs)]


def _kont() -> dict:
    p = dp.J / "konten.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _mess(kont: dict) -> set:
    mb = yaml.safe_load(open("suche/VORAB_messbots.yaml", encoding="utf-8"))["messbots"]
    return set(kont.get("messung") or {}) | {k for k in mb if k != "vergabe"}


def test_rule_is_journaled_and_the_frozen_checks_stay():
    assert zw.regel() == RG, "Prüfsumme von VORAB_zwilling.yaml fehlt im Protokoll oder ist veraltet"
    assert RG["frueh_ende"] == {"ab_trades": 15, "ende_wenn_pf_unter": 0.6}
    assert RG["ersatz"]["ab_trades"] == 40 and RG["nie_fuer"] == ["gold-cb"]
    assert dp.regel() is not None, "VORAB_wechsel.yaml muss unverändert gelten (Kirons Wahl vom 06.11.2026 15:22 UTC)"
    assert dp.woche_regel() is not None, "VORAB_eine_woche.yaml muss unverändert gelten"


def test_every_listed_twin_follows_the_rule():
    kont = _kont()
    bots = set(dp.laeufe()) | {dp.HAUPT_BOT}
    liste = zw.eintraege()
    wo = dp.woche_regel()
    for zid, e in liste.items():
        org = e.get("original")
        bis = dp.woche_bis(kont, org, wo, dp.start_utc(org)) if org else None
        f = zw.fehler(zid, e, RG, bots=bots, mess=_mess(kont), zuordnung=kont.get("zuordnung") or {}, alle=liste,
                      woche_bis_original=bis)
        assert not f, f"{zid}: " + "; ".join(f)


def _fall(tmp_path, **anders):
    vorab = tmp_path / "suche" / "VORAB_z1.yaml"
    vorab.parent.mkdir(parents=True, exist_ok=True)
    vorab.write_text("format: 1\nz1: {stop_atr: 1.0}\n", encoding="utf-8")
    sha = sha256_text(vorab.read_text(encoding="utf-8"))
    lines = ["# Protokoll", f"- 2026-11-30 09:00 UTC: VORAB_z1 sha256 {sha}"]
    e = {"original": "orig", "vorab": "suche/VORAB_z1.yaml", "vorab_key": "VORAB_z1 sha256 ", "start_utc": T0,
         "konto": "schatten", "trades": "journal/z1.jsonl", "pr": 99}
    e.update(anders)
    return e, lines


def _fehler(tmp_path, e, lines, alle=None, bis="2026-11-12T00:00:00", zuordnung=None, zid="orig-z1"):
    return zw.fehler(zid, e, RG, bots={"orig", "anderer", "gold-cb", "mess"}, mess={"mess"},
                     zuordnung=zuordnung or {}, alle=alle if alle is not None else {zid: e},
                     woche_bis_original=bis, lines=lines, root=tmp_path)


def test_a_sealed_twin_after_day_7_is_fine(tmp_path):
    e, lines = _fall(tmp_path)
    assert _fehler(tmp_path, e, lines) == []


def test_twin_waits_for_day_7_and_a_seal_before_its_start(tmp_path):
    e, lines = _fall(tmp_path)
    assert any("vor Tag 7" in f for f in _fehler(tmp_path, e, lines, bis="2026-12-03T00:00:00"))
    assert any("Prüfsumme" in f for f in _fehler(tmp_path, e, lines[:1]))
    spaet = [lines[0], lines[1].replace("2026-11-30 09:00", "2026-12-02 09:00")]
    assert any("erst nach dem Start" in f for f in _fehler(tmp_path, e, spaet))
    assert any("fehlt" in f for f in _fehler(tmp_path, {**e, "pr": None}, lines))


def test_no_twin_for_gold_or_mess_bots_and_no_foreign_account(tmp_path):
    e, lines = _fall(tmp_path)
    assert any("eigener Plan" in f for f in _fehler(tmp_path, {**e, "original": "gold-cb"}, lines))
    assert any("Mess-Bot" in f for f in _fehler(tmp_path, {**e, "original": "mess"}, lines))
    assert any("eigene Bot-ID" in f for f in _fehler(tmp_path, e, lines, zid="anderer"))
    besetzt = _fehler(tmp_path, {**e, "konto": "123"}, lines, zuordnung={"anderer": "123"})
    assert any("gehört schon anderer" in f for f in besetzt)
    assert _fehler(tmp_path, {**e, "konto": "123"}, lines, zuordnung={"orig-z1": "123"}) == []


def test_one_running_twin_per_original_and_one_new_per_week(tmp_path):
    e, lines = _fall(tmp_path)
    zwei = {"orig-z1": e, "orig-z2": {**e, "start_utc": "2026-12-20T00:00:00"}}
    assert any("laufender Zwilling" in f for f in _fehler(tmp_path, e, lines, alle=zwei))
    zwei["orig-z2"]["ende_utc"] = "2026-12-21T00:00:00"
    zwei["orig-z1"]["ende_utc"] = "2026-12-19T00:00:00"
    assert _fehler(tmp_path, zwei["orig-z1"], lines, alle=zwei) == []
    gleiche_woche = {"orig-z1": e, "anderer-z1": {**e, "original": "anderer", "start_utc": "2026-12-02T00:00:00"}}
    assert any("Kalenderwoche" in f for f in _fehler(tmp_path, e, lines, alle=gleiche_woche))


def test_stand_collects_then_ends_early_like_the_15_trade_check():
    now = pd.Timestamp("2027-01-01")
    st = zw.stand(_t([1, -1, 1]), [], RG, T0, now)
    assert st["status"] == "sammelt" and "3 von 40" in st["text"] and zw.offen(st)
    schlecht = [-1.0] * 10 + [0.5] * 5                       # 15 Trades, Gewinnfaktor 0,25
    st = zw.stand(_t(schlecht), [], RG, T0, now)
    assert st["status"] == "frueh_ende" and not zw.offen(st)
    st = zw.stand(_t(schlecht + [3.0] * 10), [], RG, T0, now)  # später gute Trades heilen das frühe Ende nicht
    assert st["status"] == "frueh_ende"


def test_after_40_trades_the_twin_must_beat_the_original_in_the_same_time():
    now = pd.Timestamp("2027-06-01")
    gut = [1.0, -1.0, 1.0] * 14                                # 42 Trades, die ersten 40: Gewinnfaktor 2
    schwach = _t([1.0, -1.0] * 20, bot="orig")                # Original im selben Zeitraum: 0 R
    st = zw.stand(_t(gut), schwach, RG, T0, now, {"konto": "schatten"})
    assert st["status"] == "reif" and "Schatten" in st["text"] and zw.offen(st)
    stark = _t([2.0, -1.0, 2.0] * 14, bot="orig")
    st = zw.stand(_t(gut), stark, RG, T0, now)
    assert st["status"] == "nicht_besser" and "Original" in st["text"] and not zw.offen(st)
    spaeter = _t([5.0] * 10, bot="orig", ab="2027-03-01")      # Trades des Originals nach dem 40. zählen nicht
    assert zw.stand(_t(gut), schwach + spaeter, RG, T0, now)["status"] == "reif"
    assert zw.stand(_t([1.0, -1.0] * 20), [], RG, T0, now)["status"] == "nicht_besser"   # Gewinnfaktor 1,0


def test_deadline_reports_but_does_not_end_and_ended_twins_stay_ended():
    st = zw.stand(_t([1, -1]), [], RG, T0, pd.Timestamp("2027-06-02"))
    assert st["status"] == "frist" and zw.offen(st)
    st = zw.stand(_t([1, -1]), [], RG, T0, pd.Timestamp("2027-01-01"), {"ende_utc": "2026-12-24", "ende_grund": "x"})
    assert st["status"] == "beendet" and not zw.offen(st)


def test_vergleich_shows_a_twin_next_to_its_original(tmp_path, monkeypatch):
    org = next(iter(json.load(open("journal/konten.json", encoding="utf-8")).get("zuordnung") or {"r6-vortag-eurusd": 1}))
    datei = tmp_path / "z.jsonl"
    datei.write_text("".join(json.dumps(t) + "\n" for t in _t([1.0, -0.5], bot="test-zwilling",
                                                               ab="2026-11-01T00:00:00")), encoding="utf-8")
    e = {"original": org, "start_utc": "2026-11-01T00:00:00", "konto": "schatten", "trades": str(datei)}
    monkeypatch.setattr(vg, "_zwillinge", lambda laeufe: ({"test-zwilling": e}, RG))
    v = vg.vergleich(datetime(2026, 11, 7, 8, 0, tzinfo=timezone.utc))
    z = next(b for b in v["rangliste"] if b["id"] == "test-zwilling")
    assert z["gruppe"] == "zwilling" and z["ist"]["trades"] == 2 and z["aufstieg"]["status"] == "sammelt"
    assert z["konto"].startswith("Schatten") and z["aufstieg"]["original"] == org
    assert "test-zwilling" not in v["kombi"]["mitglieder"]
