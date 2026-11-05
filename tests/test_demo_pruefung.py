"""Prüfung der Demo-Bots nach 15/40 Trades und Wechsel (suche/demo_pruefung.py, Regel suche/VORAB_wechsel.yaml)."""
import json

from suche import demo_bots as db
from suche import demo_pruefung as dp
from suche import london_bot as lb

RG = {"frueh": {"ab_trades": 15, "wechsel_wenn_pf_unter": 0.6},
      "urteil": {"ab_trades": 40, "wechsel_wenn_pf_unter": 1.0, "wechsel_mit_ersatz_wenn_pf_unter": 1.2}}


def _trades(n_win, n_loss, bot="b1", win=1.0, start="2026-11-05"):
    out = [{"bot": bot, "r": win, "closed_utc": f"{start}T10:{i:02d}:00"} for i in range(n_win)]
    return out + [{"bot": bot, "r": -1.0, "closed_utc": f"{start}T11:{i:02d}:00"} for i in range(n_loss)]


def test_rule_is_journaled_and_matches_the_tests():
    rg = dp.regel()
    assert rg is not None and rg["frueh"] == RG["frueh"] and rg["urteil"] == RG["urteil"]


def test_thresholds():
    k = dp.kennzahl
    assert dp.entscheide(k(_trades(4, 10)), RG, False) is None                 # 14 Trades: noch zu früh
    assert "deutlich unter 0.6" in dp.entscheide(k(_trades(5, 10)), RG, False)  # 15 Trades, PF 0,5
    assert dp.entscheide(k(_trades(6, 9)), RG, False) is None                  # 15 Trades, PF 0,67
    assert "unter 1.0" in dp.entscheide(k(_trades(19, 21)), RG, False)         # 40 Trades, PF 0,9
    assert dp.entscheide(k(_trades(21, 19)), RG, False) is None                # PF 1,1 ohne Ersatz: bleibt
    assert "Ersatz bereit" in dp.entscheide(k(_trades(21, 19)), RG, True)      # PF 1,1 mit Ersatz: Wechsel
    assert dp.entscheide(k(_trades(23, 17)), RG, True) is None                 # PF 1,35: bleibt
    assert dp.entscheide(k(_trades(40, 0)), RG, True) is None                  # ohne Verlust nie


def _setup(tmp_path, trades, reserve=False):
    f = tmp_path / "t.jsonl"
    f.write_text("".join(json.dumps(t) + "\n" for t in trades))
    kont = {"zuordnung": {"b1": "1001", "b2": "1002", "gold-cb": "1000"},
            "konten": [{"id": "…1001", "name": "Account 1", "fuer": "b1"}, {"id": "…1002", "name": "Account 2", "fuer": "b2"}]}
    pf = {"bots": [{"rang": 1, "id": "b2", "name": "B2", "bestanden": True, "rolle": "aktiv"},
                   {"rang": 2, "id": "b1", "name": "B1", "bestanden": True, "rolle": "aktiv"},
                   {"rang": 3, "id": "x", "name": "X", "bestanden": reserve, "rolle": "nicht_gewaehlt"},
                   {"rang": 4, "id": "alt", "name": "Alt", "bestanden": False, "rolle": "abgeloest"}]}
    dateien = {"b1": f, "b2": tmp_path / "leer.jsonl", "x": f, "gold-cb": f}
    return kont, pf, dateien


def test_weak_bot_is_replaced_by_the_best_free_passed_strategy(tmp_path):
    kont, pf, dateien = _setup(tmp_path, _trades(5, 10), reserve=True)
    log, stand = dp.pruefen(kont, pf, {}, "2026-12-01T10:00:00", RG, dateien)
    assert kont["abgeloest"]["b1"]["an"] == "x" and "b2" not in kont["abgeloest"] and "gold-cb" not in stand
    assert stand["b2"]["pruefung"].startswith("0 von 15")
    assert dp.portfolio_stand(pf, kont, stand)
    rollen = {b["id"]: (b["rolle"], b.get("konto"), b.get("ersetzt"), b.get("ersetzt_durch")) for b in pf["bots"]}
    assert rollen["b1"] == ("abgeloest", None, None, "X") and rollen["x"] == ("wartet", "Account 1", "B1", None)
    # zweiter Lauf: nichts Neues
    assert dp.pruefen(kont, pf, {}, "2026-12-01T10:15:00", RG, dateien)[0] == []


def test_without_a_passed_reserve_the_account_is_freed_and_given_later(tmp_path):
    kont, pf, dateien = _setup(tmp_path, _trades(5, 10))
    dp.pruefen(kont, pf, {}, "2026-12-01T10:00:00", RG, dateien)
    assert kont["abgeloest"]["b1"]["an"] is None
    # der Lauf des Bots gibt das Konto frei, sobald nichts mehr offen ist
    db.uebergeben(kont, kont["abgeloest"], set(), [], "2026-12-01T10:16:00")
    assert "b1" not in kont["zuordnung"] and kont["frei"] == ["1001"]
    # später besteht eine neue Strategie mit Bot-Lauf die Regel: sie bekommt das freie Konto
    pf["bots"][2]["bestanden"] = True
    log, _ = dp.pruefen(kont, pf, {}, "2027-01-10T10:00:00", RG, dateien)
    assert kont["zuordnung"]["x"] == "1001" and kont["frei"] == [] and log[-1]["event"] == "freies Konto vergeben"


def test_count_starts_again_after_a_handover(tmp_path):
    kont, pf, dateien = _setup(tmp_path, _trades(5, 10, start="2026-11-05"), reserve=True)
    kont["uebergaben"] = [{"zeit": "2026-11-20T00:00:00", "an": "b1"}]
    log, stand = dp.pruefen(kont, pf, {}, "2026-12-01T10:00:00", RG, dateien)
    assert log == [] and stand["b1"]["trades"] == 0


def test_bots_replaced_by_the_yaml_or_on_the_main_account_are_not_checked(tmp_path):
    kont, pf, dateien = _setup(tmp_path, _trades(5, 10), reserve=True)
    log, stand = dp.pruefen(kont, pf, {"abgeloest": {"b1": {"an": "y"}}}, "2026-12-01T10:00:00", RG, dateien)
    assert log == [] and "b1" not in stand and "gold-cb" not in stand


def test_london_family_never_takes_a_freed_or_foreign_account_back():
    accounts = [{"accountId": a, "accountName": n} for a, n in (("1000", "Account"), ("1001", "Account 1"),
                                                               ("1002", "Account 2"))]
    kont = {"zuordnung": {"other": "1002"}, "frei": ["1001"]}
    st = {"konto_id": "1001"}
    bot = lb.LONDON
    assert lb.finde_konto(accounts, kont, "1000", st, lambda a: True, bot) is None
    st = {"konto_id": "1002"}
    assert lb.finde_konto(accounts, kont, "1000", st, lambda a: True, bot) is None
    kont["zuordnung"][bot.bot_id] = "1001"
    assert lb.finde_konto(accounts, kont, "1000", {}, lambda a: True, bot) == "1001"


def test_workflow_runs_the_check_before_the_bots():
    from pathlib import Path
    wf = Path(".github/workflows/demo-bots.yml").read_text(encoding="utf-8")
    assert "python -m suche.demo_pruefung" in wf
    assert wf.index("python -m suche.demo_pruefung") < wf.index("python -m suche.demo_bots")


def test_kirons_selection_switches_bots_off_without_successor(tmp_path):
    kont, pf, dateien = _setup(tmp_path, _trades(10, 5), reserve=True)
    log, stand = dp.pruefen(kont, pf, {}, "2026-12-01T10:00:00", RG, dateien, aus={"b1": "zu wenig", "gold-cb": "nie"})
    assert kont["abgeloest"]["b1"]["an"] is None and "Kirons Auswahl" in kont["abgeloest"]["b1"]["grund"]
    assert "gold-cb" not in kont["abgeloest"] and "b2" not in kont["abgeloest"] and "b1" not in stand
    assert [e["event"] for e in log] == ["Bot abgeschaltet"]
    # das Konto wird frei, sobald nichts mehr offen ist; ein abgeschalteter Bot bekommt es nie zurück
    db.uebergeben(kont, kont["abgeloest"], set(), [], "2026-12-01T10:16:00")
    assert kont["frei"] == ["1001"]
    dp.pruefen(kont, pf, {}, "2026-12-01T10:30:00", RG, dateien, aus={"b1": "zu wenig"})
    assert kont["zuordnung"].get("x") == "1001" and "b1" not in kont["zuordnung"]


def test_selection_file_names_real_strategies():
    import yaml
    a = yaml.safe_load(open("suche/auswahl.yaml", encoding="utf-8"))["auswahl"]
    ids = {b["id"] for b in json.load(open("journal/portfolio.json", encoding="utf-8"))["bots"]}
    assert set(a["behalten"]) <= ids and set(a["abschalten"]) <= ids
    assert not set(a["behalten"]) & set(a["abschalten"]) and dp.HAUPT_BOT not in a["abschalten"]
    assert dp.abschalten() == a["abschalten"]
    kombi = yaml.safe_load(open("suche/kombi.yaml", encoding="utf-8"))["kombi"]
    assert all(set(g["bots"]) <= set(a["behalten"]) for g in kombi.values())


def test_euro_respects_leverage_and_stop_unit():
    from suche import bewertung as bw
    assert bw.euro(1.0, 1.0, "INDICES") == 10.0                        # 1 % Stop: 1.000 € Position, +1 % = 10 €
    assert bw.euro(0.1, 2.0, "FX") == 15.0                             # Stop 0,05 %: Position auf 15.000 € begrenzt
    assert bw.euro(3.0, 3.0, "INDICES", je_stop=3.0) == 10.0           # R in ATR, Stop 3 x ATR: ein R bis zum Stop
    assert bw.euro(-0.5, -1.0, "COMMODITIES") == -10.0 and bw.euro(1.0, None, "FX") is None
