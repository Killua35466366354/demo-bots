"""Geteilte Konten werden nie automatisch vergeben (suche/mitnutzer.py, suche/demo_pruefung.py; Befund B-04 der
Projekt-Prüfung vom 11.11.2026). Konten stehen hier nur mit erfundenen Nummern oder den letzten 4 Stellen."""
import json
import re
from pathlib import Path

from gold.bot import konten
from suche import demo_pruefung as dp
from suche import mitnutzer as mn

ROOT = Path(__file__).resolve().parents[1]
RG = {"frueh": {"ab_trades": 15, "wechsel_wenn_pf_unter": 0.6},
      "urteil": {"ab_trades": 40, "wechsel_wenn_pf_unter": 1.0, "wechsel_mit_ersatz_wenn_pf_unter": 1.2}}


def _welt(tmp_path, frei):
    f = tmp_path / "t.jsonl"
    f.write_text("")
    kont = {"zuordnung": {"b1": "1001", "gold-cb": "1000"}, "frei": list(frei)}
    pf = {"bots": [{"rang": 1, "id": "b1", "name": "B1", "bestanden": True, "rolle": "aktiv"},
                   {"rang": 2, "id": "x", "name": "X", "bestanden": True, "rolle": "nicht_gewaehlt"}]}
    return kont, pf, {"b1": f, "x": f}


def test_ohne_mitnutzer_bekommt_die_naechste_bestandene_strategie_das_freie_konto(tmp_path):
    kont, pf, dateien = _welt(tmp_path, ["1005"])
    log, _ = dp.pruefen(kont, pf, {}, "2026-12-01T10:00:00", RG, dateien)
    assert kont["zuordnung"]["x"] == "1005" and kont["frei"] == []
    assert [e["event"] for e in log] == ["freies Konto vergeben"]


def test_geteiltes_konto_bleibt_frei_und_wird_nur_einmal_gemeldet(tmp_path):
    kont, pf, dateien = _welt(tmp_path, ["1005"])
    mit = {"1005": ["gold-staffel", "scalp-de40"]}
    log, _ = dp.pruefen(kont, pf, {}, "2026-12-01T10:00:00", RG, dateien, mit=mit)
    assert "x" not in kont["zuordnung"] and kont["frei"] == ["1005"]
    assert [e["event"] for e in log] == ["freies Konto bleibt bei den Mitnutzern"]
    assert log[0]["konto"] == "…1005" and log[0]["bots"] == ["gold-staffel", "scalp-de40"]
    # zweiter Lauf: still, das Konto bleibt weiter frei stehen
    assert dp.pruefen(kont, pf, {}, "2026-12-01T10:15:00", RG, dateien, mit=mit)[0] == []
    assert kont["frei"] == ["1005"] and "x" not in kont["zuordnung"]
    # ändert sich die Besetzung, steht es einmal neu im Log
    mit2 = {"1005": ["gold-staffel"]}
    assert len(dp.pruefen(kont, pf, {}, "2026-12-01T10:30:00", RG, dateien, mit=mit2)[0]) == 1


def test_ein_zweites_freies_konto_ohne_mitnutzer_wird_weiter_vergeben(tmp_path):
    kont, pf, dateien = _welt(tmp_path, ["1005", "1006"])
    log, _ = dp.pruefen(kont, pf, {}, "2026-12-01T10:00:00", RG, dateien, mit={"1005": ["scalp-us100"]})
    assert kont["zuordnung"]["x"] == "1006" and kont["frei"] == ["1005"]
    assert {e["event"] for e in log} == {"freies Konto bleibt bei den Mitnutzern", "freies Konto vergeben"}


def test_labor_und_mess_bots_bekommen_kein_geteiltes_konto():
    lb = {"frei_lassen": 0, "bots": {"lab": {"konto": "1005"}}}
    kont = {"zuordnung": {}, "frei": ["1005"], "abgeloest": {"lab": {"an": None, "grund": "Kirons Auswahl"}}}
    assert dp.labor_vergeben(kont, lb, {"lab"}, {}, "2026-12-01T10:00:00", frozenset({"1005"})) == []
    assert kont["frei"] == ["1005"] and "lab" not in kont["zuordnung"]
    assert dp.labor_vergeben(kont, lb, {"lab"}, {}, "2026-12-01T10:00:00")[0]["event"] == "Labor-Konto vergeben"
    mb = {"mess": {"konto": "1007"}, "vergabe": {"frei_lassen": 0}}
    kont = {"zuordnung": {}, "frei": ["1007"]}
    assert dp.mess_vergeben(kont, mb, {"mess"}, "2026-12-01T10:00:00", frozenset({"1007"})) == []
    assert dp.mess_vergeben(kont, mb, {"mess"}, "2026-12-01T10:00:00")[0]["event"] == "Mess-Konto vergeben"


def test_geteilte_konten_zaehlen_im_labor_nicht_als_freie_reserve():
    lb = {"frei_lassen": 1, "bots": {"lab": {"konto": "1006"}}}
    kont = {"zuordnung": {}, "frei": ["1005", "1006"], "abgeloest": {"lab": {"an": None, "grund": "Kirons Auswahl"}}}
    # 1005 ist geteilt: es bleibt nur 1006 als freies Konto, und eines muss frei bleiben
    assert dp.labor_vergeben(kont, lb, {"lab"}, {}, "2026-12-01T10:00:00", frozenset({"1005"})) == []


def test_abloesung_auf_geteiltem_konto_nennt_die_mitnutzer(tmp_path):
    kont, pf, dateien = _welt(tmp_path, [])
    dateien["b1"].write_text("".join(json.dumps({"bot": "b1", "r": r, "closed_utc": f"2026-11-05T10:{i:02d}:00"}) + "\n"
                                     for i, r in enumerate([1.0] * 5 + [-1.0] * 10)))
    log, _ = dp.pruefen(kont, pf, {}, "2026-12-01T10:00:00", RG, dateien, mit={"1001": ["gold-grossbox"]})
    assert log[0]["event"] == "Bot abgelöst" and log[0]["an"] == "x" and log[0]["mitnutzer"] == ["gold-grossbox"]


def test_liste_nicht_lesbar_sperrt_jedes_freie_konto(monkeypatch):
    def kaputt():
        raise RuntimeError("Bot-Code fehlt")
    monkeypatch.setattr(mn, "konten", kaputt)
    mit = dp.mitnutzer_konten({"frei": ["1005", "1006"]})
    assert set(mit) == {"1005", "1006"} and "nicht lesbar" in mit["1005"][0]


def test_liste_kommt_aus_dem_code_der_bots():
    from gold import grossbox_bot, hand_bot, pine5m_bot
    from suche import gold_staffel_bot, scalper_bot
    alle = {b["bot"]: b for b in mn.bots()}
    erwartet = ({b.bot_id for b in scalper_bot.BOTS} | {b.bot_id for b in pine5m_bot.BOTS}
                | {gold_staffel_bot.BOT_ID, grossbox_bot.BOT_ID, hand_bot.BOT_ID})
    assert set(alle) == erwartet and len(mn.bots()) == len(erwartet)
    assert alle["gold-staffel"]["konto"] == gold_staffel_bot.KONTO == scalper_bot.KONTO
    assert alle["gold-grossbox"]["konto"] == grossbox_bot.KONTO
    assert alle["gold-hand"]["neu"] is bool(hand_bot.NEUE_EINSTIEGE)
    assert {b["bot"] for b in mn.aktive()} == {k for k, b in alle.items() if b["neu"]}
    haupt = konten.HAUPT_ENDUNG
    assert not any(k.endswith(haupt) for k in mn.konten()), "Mitnutzer handeln nie auf dem Hauptkonto des Gold-Bots"


def test_jeder_bot_aus_dem_5_minuten_lauf_steht_in_der_liste():
    """Ein neuer Bot im 5-Minuten-Lauf hat ein festes Konto. Fehlt er in suche/mitnutzer.py, könnte sein Konto vergeben
    werden. Der Test liest die Module aus dem Workflow und verlangt, dass jedes dort als Quelle vorkommt."""
    wf = (ROOT / ".github" / "workflows" / "pine5m.yml").read_text(encoding="utf-8")
    module = set(re.findall(r"python -m ((?:gold|suche)\.\w+_bot)\b", wf))
    assert module, "im 5-Minuten-Lauf wurde kein Bot gefunden"
    quellen = {b["quelle"] for b in mn.bots()}
    for m in module:
        assert m.replace(".", "/") + ".py" in quellen, f"{m} fehlt in suche/mitnutzer.py"


def test_heute_ist_account_1_frei_gemeldet_und_bleibt_bei_scalpern_und_staffel():
    kont = konten.load(ROOT / "journal")
    mit = dp.mitnutzer_konten(kont)
    for aid in kont.get("frei") or []:
        if str(aid) in mit:
            assert any(b.startswith("scalp-") or b == "gold-staffel" for b in mit[str(aid)])
    # kein Mitnutzer steht zugleich in der Zuordnung (dann gälte für ihn die Prüfung nach 15/40 Trades doppelt)
    assert not {b["bot"] for b in mn.bots()} & set(kont.get("zuordnung") or {})
