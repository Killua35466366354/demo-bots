"""Labor-Vorwärtstest auf freien Demokonten (suche/VORAB_labor.yaml, suche/demo_pruefung.labor_vergeben)."""
import json
from copy import deepcopy

import yaml

from suche import demo_pruefung as dp
from suche import vergleich as vg

RG = {"frueh": {"ab_trades": 15, "wechsel_wenn_pf_unter": 0.6},
      "urteil": {"ab_trades": 40, "wechsel_wenn_pf_unter": 1.0, "wechsel_mit_ersatz_wenn_pf_unter": 1.2}}
LB = {"bots": {"a": {"konto": "2001"}, "b": {"konto": "2002"}, "c": {"konto": "2003"}}, "frei_lassen": 2}
AUSWAHL = "Kirons Auswahl vom 04.11.2026 (abschalten): kaum vom Zufall zu unterscheiden"


def _kont():
    return {"zuordnung": {"k": "1001"}, "frei": ["2005", "2001", "2002", "2003", "2004"],
            "abgeloest": {x: {"an": None, "seit": "2026-11-04T13:00:00", "grund": AUSWAHL} for x in "abc"},
            "konten": [{"id": "…2001", "name": "Account 1"}, {"id": "…1001", "name": "Kern"}]}


def _pf():
    return {"bots": [{"rang": 1, "id": "k", "name": "K", "bestanden": True, "rolle": "aktiv"},
                     *({"rang": i, "id": x, "name": x.upper(), "bestanden": True, "rolle": "abgeloest",
                        "ersetzt_durch": None} for i, x in enumerate("abc", 2))]}


def _dateien(tmp_path):
    leer = tmp_path / "leer.jsonl"
    leer.write_text("")
    return {x: leer for x in "kabc"}


def test_rule_is_registered_and_names_real_strategies():
    lb = dp.labor_regel()
    assert lb is not None, "Prüfsumme von VORAB_labor.yaml fehlt im Protokoll oder ist veraltet"
    aus = yaml.safe_load(open("suche/auswahl.yaml", encoding="utf-8"))["auswahl"]
    assert set(lb["bots"]) == set(aus["labor"]) and not set(aus["labor"]) & set(aus["behalten"])
    assert not set(aus["labor"]) & set(aus["abschalten"]) and lb["frei_lassen"] >= 2
    kont = json.load(open("journal/konten.json", encoding="utf-8"))
    alle = {str(k) for k in kont.get("start") or {}}
    assert all(str(w["konto"]) in alle for w in lb["bots"].values())       # echte Demokonten
    kombi = yaml.safe_load(open("suche/kombi.yaml", encoding="utf-8"))["kombi"]
    assert not any(set(g["bots"]) & set(lb["bots"]) for g in kombi.values())


def test_lab_bots_get_their_old_free_account_and_two_stay_free(tmp_path):
    kont = _kont()
    log = dp.labor_vergeben(kont, LB, _dateien(tmp_path), {}, "2026-11-05T12:00:00")
    assert [e["bot"] for e in log] == ["a", "b", "c"]
    assert kont["zuordnung"] == {"k": "1001", "a": "2001", "b": "2002", "c": "2003"}
    assert kont["frei"] == ["2005", "2004"] and not kont["abgeloest"]
    assert all(u["labor"] and u["von"] is None for u in kont["uebergaben"])
    assert dp.seit_wann(kont, "a") == "2026-11-05T12:00:00"                 # gezählt wird ab der Labor-Übergabe
    # zweiter Lauf: nichts Neues
    assert dp.labor_vergeben(kont, LB, _dateien(tmp_path), {}, "2026-11-05T12:15:00") == []


def test_never_below_the_free_reserve(tmp_path):
    kont = _kont()
    kont["frei"] = ["2001", "2002", "2003"]
    log = dp.labor_vergeben(kont, LB, _dateien(tmp_path), {}, "2026-11-05T12:00:00")
    assert [e["bot"] for e in log] == ["a"] and len(kont["frei"]) == 2


def test_bots_switched_off_by_the_15_40_check_never_come_back(tmp_path):
    kont = _kont()
    kont["abgeloest"]["a"] = {"an": None, "grund": "nach 15 Demo-Trades Gewinnfaktor 0.40", "messung": {"trades": 15}}
    kont["labor"] = {"b": {"seit": "2026-11-05T12:00:00"}}                   # schon einmal im Labor
    del kont["abgeloest"]["b"]
    log = dp.labor_vergeben(kont, LB, _dateien(tmp_path), {}, "2026-11-06T12:00:00")
    assert [e["bot"] for e in log] == ["c"] and "a" not in kont["zuordnung"] and "b" not in kont["zuordnung"]
    assert dp.labor_vergeben(_kont(), LB, _dateien(tmp_path), {"a": {"an": None}}, "x")[0]["bot"] == "b"
    assert dp.labor_vergeben(_kont(), None, _dateien(tmp_path), {}, "x") == []


def test_check_keeps_lab_bots_running_and_marks_their_role(tmp_path):
    kont, pf = _kont(), _pf()
    log, stand = dp.pruefen(kont, pf, {}, "2026-11-05T12:00:00", RG, _dateien(tmp_path), aus={}, lb=LB)
    assert {e["event"] for e in log} == {"Labor-Konto vergeben"} and set(stand) == {"k", "a", "b", "c"}
    assert all(s["pruefung"].startswith("0 von 15") for s in stand.values())
    assert dp.portfolio_stand(pf, kont, stand)
    rollen = {b["id"]: b["rolle"] for b in pf["bots"]}
    assert rollen == {"k": "aktiv", "a": "labor", "b": "labor", "c": "labor"}
    assert next(b for b in pf["bots"] if b["id"] == "a")["konto"] == "Account 1"
    # Kirons alte Auswahl schaltet einen Labor-Bot nicht wieder ab, die freien Konten gehen an niemanden sonst
    vorher = deepcopy(kont)
    log, _ = dp.pruefen(kont, pf, {}, "2026-11-05T12:15:00", RG, _dateien(tmp_path), aus={"a": AUSWAHL}, lb=LB)
    assert log == [] and kont == vorher
    # ohne Labor-Regel (Standard) bleibt alles wie bisher
    kont2 = _kont()
    log, _ = dp.pruefen(kont2, _pf(), {}, "2026-11-05T12:00:00", RG, _dateien(tmp_path), aus={})
    assert "labor" not in kont2 and set(kont2["abgeloest"]) == set("abc")


def test_comparison_shows_lab_group():
    v = vg.vergleich()
    lab = set(yaml.safe_load(open("suche/auswahl.yaml", encoding="utf-8"))["auswahl"]["labor"])
    assert all(b["gruppe"] == "labor" for b in v["rangliste"] if b["id"] in lab)
    assert not lab & set(v["kombi"]["mitglieder"])
