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


def test_lab_bot_goes_only_with_kirons_dated_word(tmp_path):
    """Ein Labor-Bot (VORAB_labor.yaml) bleibt bei einer bloßen Auswahlliste, Kirons datiertes Wort schaltet ihn ab
    (Kirons Wort vom 10.11.2026 10:35 UTC: Brent macht Account 1 frei). Sein Konto wird frei, er bekommt es nie zurück."""
    kont, pf, dateien = _setup(tmp_path, [])
    kont["labor"] = {"b1": {"seit": "2026-11-05T11:16:36", "konto": "…1001"}}
    log, _ = dp.pruefen(kont, pf, {}, "2026-11-10T11:00:00", RG, dateien, aus={"b1": "zu wenig Trades"})
    assert log == [] and "b1" not in kont["abgeloest"]
    wort = {"b1": "Kirons Wort vom 10.11.2026 10:35 UTC: Konto frei machen"}
    log, _ = dp.pruefen(kont, pf, {}, "2026-11-10T11:00:00", RG, dateien, aus=wort, wo=WO,
                        starts={"b1": "2026-11-05T11:16:36"})
    assert [(e["event"], e["bot"]) for e in log] == [("Bot abgeschaltet", "b1")]
    assert kont["abgeloest"]["b1"]["an"] is None and kont["abgeloest"]["b1"]["grund"].startswith("Kirons Wort vom")
    db.uebergeben(kont, kont["abgeloest"], set(), [], "2026-11-10T11:01:00")
    assert kont["frei"] == ["1001"] and "b1" not in kont["zuordnung"]
    dp.pruefen(kont, pf, {}, "2026-11-10T11:15:00", RG, dateien, aus=wort)
    assert "b1" not in kont["zuordnung"] and kont["labor"]["b1"]["konto"] == "…1001"


def test_brent_is_switched_off_by_kirons_word():
    import yaml
    a = yaml.safe_load(open("suche/auswahl.yaml", encoding="utf-8"))["auswahl"]
    assert dp.kirons_wort(a["abschalten"]["oil-brent"]) and "oil-brent" not in a["labor"]


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


# ---------- Mess-Bots und Rutsch-Regel (Kritik F2/D3, Kirons Ja vom 05.11.2026 17:07 UTC) ----------

def test_mess_and_rutsch_rules_are_journaled():
    mb, ru = dp.mess_regel(), dp.rutsch_regel()
    assert mb is not None and ru is not None, "Prüfsumme von VORAB_messbots.yaml oder VORAB_rutschen.yaml fehlt"
    assert mb["r6-vortag-eurusd-1atr"]["konto"] == "332263729491432606"            # Account 2
    assert set(ru["gilt_fuer"]) == {"r6-vortag-eurusd", "r6-vortag-gbpusd", "r6-vortag-gbpjpy"}
    assert "r6-vortag-eurusd-1atr" not in ru["gilt_fuer"] and ru["ab_trades"] == ru["fenster"] == 10
    from suche.r6_bots import BOTS
    assert "r6-vortag-eurusd-1atr" in {b.bot_id for b in BOTS} and "r6-vortag-eurusd-1atr" in dp.laeufe()


def test_mess_bot_gets_its_free_account_exactly_once(tmp_path):
    mb = {"m1": {"konto": "2606"}, "vergabe": {"frei_lassen": 0}}
    kont = {"zuordnung": {"b1": "1001"}, "frei": ["2606"]}
    log = dp.mess_vergeben(kont, mb, {"m1": tmp_path / "t.jsonl"}, "2026-11-05T17:30:00")
    assert kont["zuordnung"]["m1"] == "2606" and kont["frei"] == [] and kont["messung"]["m1"]["konto"] == "…2606"
    assert log[0]["event"] == "Mess-Konto vergeben" and kont["uebergaben"][-1]["messung"]
    # abgelöst und Konto wieder frei: nie ein zweites Mal
    del kont["zuordnung"]["m1"]
    kont["frei"] = ["2606"]
    assert dp.mess_vergeben(kont, mb, {"m1": tmp_path / "t.jsonl"}, "2026-12-01T10:00:00") == []
    # Konto nicht frei (gehört einem anderen Bot) oder kein Lauf: nichts
    k2 = {"zuordnung": {"b1": "2606"}, "frei": []}
    assert dp.mess_vergeben(k2, mb, {"m1": tmp_path / "t.jsonl"}, "2026-11-05T17:30:00") == [] and "m1" not in k2["zuordnung"]
    assert dp.mess_vergeben({"frei": ["2606"]}, mb, {}, "2026-11-05T17:30:00") == []


def test_rutsch_rule_counts_only_stop_order_entries_and_uses_the_median_of_the_last_10():
    ru = {"gilt_fuer": {"v1": 0.5}, "ab_trades": 10, "fenster": 10}
    t = lambda p, **k: {"bot": "v1", "r": 1.0, "rutschen_pips": p, **k}      # noqa: E731
    assert dp.rutsch_grund("v1", [t(2.0)] * 9, ru) is None                        # erst ab 10 Trades
    assert dp.rutsch_grund("v1", [t(0.5)] * 10, ru) is None                       # genau an der Grenze: bleibt
    assert "Median 0.6" in dp.rutsch_grund("v1", [t(0.6)] * 10, ru)
    nach = [t(5.0, nachgeholt=True)] * 10 + [t(None)] * 3                          # nachgeholt/ohne Messung zählen nicht
    assert dp.rutsch_grund("v1", nach + [t(0.0)] * 9, ru) is None
    assert dp.rutsch_grund("v1", [t(3.0)] * 10 + [t(0.1)] * 10, ru) is None       # nur die letzten 10 zählen
    assert dp.rutsch_grund("anderer", [t(3.0)] * 10, ru) is None                  # gilt nur für die genannten Bots


def test_rutsch_rule_replaces_the_bot_like_the_switch_rule(tmp_path):
    tr = [{"bot": "b1", "r": 1.0 if i % 2 else -0.5, "rutschen_pips": 0.9, "closed_utc": f"2026-11-20T10:{i:02d}:00"}
          for i in range(10)]
    kont, pf, dateien = _setup(tmp_path, tr)
    ru = {"gilt_fuer": {"b1": 0.5}, "ab_trades": 10, "fenster": 10}
    log, stand = dp.pruefen(kont, pf, {}, "2026-12-01T10:00:00", RG, dateien, ru=ru)
    assert "Rutschen" in kont["abgeloest"]["b1"]["grund"] and kont["abgeloest"]["b1"]["an"] is None
    assert stand["b1"]["rutschen"] == {"trades": 10, "median_pips": 0.9} and log[0]["event"] == "Bot abgelöst"


def test_fixed_deadline_judges_slow_bots_every_6_months(tmp_path):
    """Kritik D1 (suche/VORAB_frist.yaml): an der Frist mit unter 40 Trades ab, wenn Summe R unter 0 oder kein Trade."""
    fr = dp.frist_regel()
    assert fr is not None and fr["monate"] == 6, "Prüfsumme von VORAB_frist.yaml fehlt"
    tr = [{"bot": "b1", "r": r, "closed_utc": f"2027-0{m}-10T10:00:00"} for m, r in ((1, 1.0), (2, -1.0), (3, 0.5))]
    kont, pf, dateien = _setup(tmp_path, tr)
    assert dp.pruefen(kont, pf, {}, "2027-05-04T10:00:00", RG, dateien, fr=fr)[0] == []    # vor der Frist: nichts
    log, _ = dp.pruefen(kont, pf, {}, "2027-05-05T10:00:00", RG, dateien, fr=fr)
    assert [(e["event"], e["bot"]) for e in log] == [("Frist bestanden", "b1"), ("Bot abgelöst", "b2")]
    assert kont["frist"]["b1"]["nr"] == 1
    assert kont["frist"]["b2"]["nr"] == 1 and "b2" in kont["abgeloest"]                  # b2: kein Trade in 6 Monaten
    assert "Frist nach 6 Monaten" in kont["abgeloest"]["b2"]["grund"] and "b1" not in kont["abgeloest"]
    assert dp.pruefen(kont, pf, {}, "2027-06-01T10:00:00", RG, dateien, fr=fr)[0] == []    # zwischen den Fristen: nichts
    (tmp_path / "t.jsonl").write_text("".join(json.dumps(t) + "\n" for t in tr + [
        {"bot": "b1", "r": -1.0, "closed_utc": "2027-07-01T10:00:00"}]))
    log, _ = dp.pruefen(kont, pf, {}, "2027-11-05T10:00:00", RG, dateien, fr=fr)
    assert "Frist nach 12 Monaten" in kont["abgeloest"]["b1"]["grund"] and log[0]["event"] == "Bot abgelöst"
    assert dp.frist_grund({}, "x", {"trades": 0, "summe_r": 0}, RG, None, "2030-01-01T00:00:00") is None


WO = {"tage": 7, "ohne_eintrag": "2026-11-04T00:00:00", "nie_fuer": ["gold-cb"],
      "regel_seit": {"b2": "2026-11-05T09:00:00"}}


def test_week_start_is_the_latest_of_start_handover_and_rule_change():
    kont = {"uebergaben": [{"zeit": "2026-11-04T11:46:39", "an": "b1"}]}
    assert dp.woche_bis(kont, "b1", WO, "2026-11-04T07:00:00") == "2026-11-11T11:46:39"
    assert dp.woche_bis(kont, "b1", WO, "2026-11-04T12:00:00") == "2026-11-11T12:00:00"
    assert dp.woche_bis(kont, "b2", WO, "2026-11-04T12:00:00") == "2026-11-12T09:00:00"     # Regeländerung zählt
    assert dp.woche_bis({}, "b3", WO) == "2026-11-11T00:00:00"                              # ohne Eintrag
    assert dp.woche_bis(kont, "gold-cb", WO, "2026-11-04T12:00:00") is None                 # nie für den Gold-Bot
    assert dp.woche_bis(kont, "b1", None) is None


def test_selection_list_waits_for_day_7_but_frozen_checks_do_not(tmp_path):
    """Fassung B: auswahl.yaml abschalten wartet bis Tag 7 ("Ablösung wartet", einmal), Kirons datiertes Wort gilt sofort,
    und eine eingefrorene Prüfung (hier die Rutsch-Regel) löst auch in der ersten Woche ab."""
    tr = [{"bot": "b1", "r": 1.0 if i % 2 else -0.5, "rutschen_pips": 0.9, "closed_utc": f"2026-11-05T10:{i:02d}:00"}
          for i in range(10)]
    kont, pf, dateien = _setup(tmp_path, [])
    starts = {"b1": "2026-11-04T11:00:00", "b2": "2026-11-04T11:00:00"}
    aus = {"b2": "zu schwach im Backtest"}
    log, _ = dp.pruefen(kont, pf, {}, "2026-11-06T10:00:00", RG, dateien, aus=aus, wo=WO, starts=starts)
    assert [(e["event"], e["bot"]) for e in log] == [("Ablösung wartet", "b2")] and "b2" not in kont["abgeloest"]
    assert log[0]["bis"] == "2026-11-12T09:00:00" and "Backtest" in log[0]["why"]
    assert dp.pruefen(kont, pf, {}, "2026-11-06T10:15:00", RG, dateien, aus=aus, wo=WO, starts=starts)[0] == []
    log, _ = dp.pruefen(kont, pf, {}, "2026-11-12T09:00:00", RG, dateien, aus=aus, wo=WO, starts=starts)
    assert [(e["event"], e["bot"]) for e in log] == [("Bot abgeschaltet", "b2")]           # Tag 7: Liste gilt

    kont, pf, dateien = _setup(tmp_path, [])
    wort = {"b2": "Kirons Wort vom 06.11.2026 10:40 UTC: b2 raus"}
    log, _ = dp.pruefen(kont, pf, {}, "2026-11-06T11:00:00", RG, dateien, aus=wort, wo=WO, starts=starts)
    assert [(e["event"], e["bot"]) for e in log] == [("Bot abgeschaltet", "b2")]
    assert kont["abgeloest"]["b2"]["grund"].startswith("Kirons Wort vom 06.11.2026")

    kont, pf, dateien = _setup(tmp_path, tr)
    ru = {"gilt_fuer": {"b1": 0.5}, "ab_trades": 10, "fenster": 10}
    log, _ = dp.pruefen(kont, pf, {}, "2026-11-06T10:00:00", RG, dateien, ru=ru, wo=WO, starts=starts)
    assert [(e["event"], e["bot"]) for e in log] == [("Bot abgelöst", "b1")] and "Rutschen" in kont["abgeloest"]["b1"]["grund"]
