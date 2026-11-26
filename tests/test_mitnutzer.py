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
    from gold import ausbruch4h_bot, grossbox_bot, hand_bot, pine5m_bot, zonen_bot
    from suche import gold_staffel_bot, krypto_bollinger_bot, modell_indizes_bot, scalper_bot, vix_sprung_bot
    from suche import buendel_bot, krypto4h_bot, welt4h_bot, williams_bot
    alle = {b["bot"]: b for b in mn.bots()}
    erwartet = ({b.bot_id for b in scalper_bot.BOTS} | {b.bot_id for b in pine5m_bot.BOTS}
                | {gold_staffel_bot.BOT_ID, grossbox_bot.BOT_ID, hand_bot.BOT_ID, zonen_bot.BOT_ID,
                   ausbruch4h_bot.BOT_ID, welt4h_bot.BOT_ID, krypto_bollinger_bot.BOT_ID, modell_indizes_bot.BOT_ID,
                   vix_sprung_bot.BOT_ID, williams_bot.BOT_ID, krypto4h_bot.BOT_ID, buendel_bot.BOT_ID,
                   buendel_bot.GOLD_ID, buendel_bot.V1_ID})
    assert set(alle) == erwartet and len(mn.bots()) == len(erwartet)
    assert alle["gold-staffel"]["konto"] == gold_staffel_bot.KONTO == scalper_bot.KONTO
    assert alle["gold-grossbox"]["konto"] == grossbox_bot.KONTO
    assert alle["gold-zonen"]["konto"] == zonen_bot.KONTO and alle["gold-zonen"]["konto_name"] == "Account 2"
    assert alle["gold-ausbruch4h"]["konto"] == ausbruch4h_bot.KONTO and alle["gold-ausbruch4h"]["konto_name"] == "Account 4"
    assert alle["welt-ausbruch4h"]["konto"] == welt4h_bot.KONTO and alle["welt-ausbruch4h"]["konto_name"] == "Account 7"
    # jeder Gold-Mitnutzer hat sein eigenes Konto: Zwei Gold-Bots auf einem Konto könnten sich Positionen schließen
    gold = [alle[b]["konto"] for b in ("gold-grossbox", "gold-zonen", "gold-ausbruch4h")]
    assert len(set(gold)) == 3 and gold_staffel_bot.KONTO not in gold
    assert welt4h_bot.KONTO and welt4h_bot.KONTO not in gold    # anderer Markt, aber nie auf einem Gold-Konto
    k = alle["krypto-bollinger"]
    assert k["konto"] == krypto_bollinger_bot.KONTO and k["konto_name"] == "Account 3"
    assert krypto_bollinger_bot.KONTO not in gold + [gold_staffel_bot.KONTO, welt4h_bot.KONTO]
    m = alle["modell-indizes"]
    assert m["konto"] == modell_indizes_bot.KONTO and m["konto_name"] == "Account 6"
    # Account 6 teilt er mit der Groß-Box (Gold, andere Märkte), aber nie mit einem anderen Index-Bot
    assert modell_indizes_bot.KONTO == grossbox_bot.KONTO
    assert modell_indizes_bot.KONTO not in [gold_staffel_bot.KONTO, welt4h_bot.KONTO, krypto_bollinger_bot.KONTO]
    v = alle["vix-sprung"]
    assert v["konto"] == vix_sprung_bot.KONTO and v["konto_name"] == "Account 5"
    # Account 5 teilt er mit pine-k5 (Gold) und dem Dow-Rücksetzer (US30), aber nie mit einem Bot auf seinen Märkten
    assert vix_sprung_bot.KONTO == hand_bot.KONTO == alle["pine-k5"]["konto"]
    assert vix_sprung_bot.KONTO not in [scalper_bot.KONTO, welt4h_bot.KONTO, krypto_bollinger_bot.KONTO,
                                        modell_indizes_bot.KONTO]
    wi = alle["williams-us"]
    assert wi["konto"] == williams_bot.KONTO and wi["konto_name"] == "Account 7"
    # Account 7 teilt er mit dem 4-Std.-Ausbruch DAX, FTSE, Nikkei und Noise USD/JPY, aber nie mit einem anderen Bot
    # auf US500 oder US100 (Vorhersage-Modell Account 6, VIX-Sprung Account 5, Rücksetzer auf eigenen Konten)
    assert williams_bot.KONTO == welt4h_bot.KONTO
    zuordnung = json.loads((ROOT / "journal" / "konten.json").read_text(encoding="utf-8"))["zuordnung"]
    assert williams_bot.KONTO not in [modell_indizes_bot.KONTO, vix_sprung_bot.KONTO, scalper_bot.KONTO,
                                      zuordnung["us500-ruecksetzer"], zuordnung["r5-ruecksetzer-us100"],
                                      zuordnung["r7-nasdaq-noise-long"]]
    k4 = alle["krypto-ausbruch4h"]
    assert k4["konto"] == krypto4h_bot.KONTO and k4["konto_name"] == "Account 5"
    # Account 5 teilt er mit pine-k5, dem Dow-Rücksetzer und dem VIX-Sprung: kein Kern-Bot und nie der Bollinger-Bot
    # auf Bitcoin und Ether (Account 3)
    assert krypto4h_bot.KONTO == vix_sprung_bot.KONTO == zuordnung["r5-ruecksetzer-us30"] != krypto_bollinger_bot.KONTO
    from suche.r6_bots import BEENDET
    kern = ("us500-ruecksetzer", "r5-ruecksetzer-us100", "r7-nasdaq-noise-long", "r6-vortag-eurusd", "r6-vortag-gbpusd",
            "r6-vortag-gbpjpy")
    # Ohne Konto darf nur ein beendeter Kern-Bot sein (Vortag GBP/JPY seit 22.11.2026), jeder laufende braucht eines
    assert all(b in zuordnung or b in BEENDET for b in kern)
    assert krypto4h_bot.KONTO not in [zuordnung[b] for b in kern if b in zuordnung]
    bu = alle["buendel9"]
    # Das Bündel kopiert die Trades von 9 Bots auf "Vortag USDJPY". Das Konto teilt es mit Vortag GBP/USD (GBPUSD, dort
    # kopiert es nie) und dem ruhenden pine-hand, nie mit einem seiner Mitglieder
    assert bu["konto"] == buendel_bot.KONTO == str(zuordnung["r6-vortag-gbpusd"]) and bu["konto_name"] == "Vortag USDJPY"
    assert buendel_bot.KONTO not in [scalper_bot.KONTO, zonen_bot.KONTO, ausbruch4h_bot.KONTO, welt4h_bot.KONTO,
                                     str(zuordnung["us500-ruecksetzer"]), str(zuordnung["r5-ruecksetzer-us100"]),
                                     str(zuordnung["r7-nasdaq-noise-long"])]
    # Das Gold-Bündel (seit 26.11.2026) teilt dasselbe Konto mit buendel9, nie mit einem Gold-Bot, den es kopiert
    gb = alle["gold-buendel"]
    assert gb["konto"] == bu["konto"] and gb["konto_name"] == "Vortag USDJPY" and gb["neu"] is True
    assert gb["konto"] not in [zonen_bot.KONTO, ausbruch4h_bot.KONTO, grossbox_bot.KONTO, gold_staffel_bot.KONTO]
    # V1 mit wachsendem Einsatz (seit 26.11.2026) teilt "Account 3" nur mit dem Bollinger-Bot Krypto, nie mit einem der
    # 9 Bots, die er kopiert, und nie mit den beiden Bündeln
    v1 = alle["v1-wachsend"]
    assert v1["konto"] == buendel_bot.V1_KONTO == krypto_bollinger_bot.KONTO and v1["konto_name"] == "Account 3"
    assert v1["neu"] is True and v1["konto"] != bu["konto"]
    assert v1["konto"] not in [scalper_bot.KONTO, zonen_bot.KONTO, ausbruch4h_bot.KONTO, welt4h_bot.KONTO,
                               str(konten.load()["haupt"]), str(zuordnung["us500-ruecksetzer"]),
                               str(zuordnung["r5-ruecksetzer-us100"]), str(zuordnung["r7-nasdaq-noise-long"])]
    assert {b["bot"] for b in mn.bots() if b["konto"] == v1["konto"]} == {"krypto-bollinger", "v1-wachsend"}
    assert alle["gold-hand"]["neu"] is bool(hand_bot.NEUE_EINSTIEGE)
    assert {b["bot"] for b in mn.aktive()} == {k for k, b in alle.items() if b["neu"]}
    haupt = konten.HAUPT_ENDUNG
    assert not any(k.endswith(haupt) for k in mn.konten()), "Mitnutzer handeln nie auf dem Hauptkonto des Gold-Bots"
    # Die Prüfung vergleicht volle Konto-IDs. Eine gekürzte (…1234) schützt kein Konto, und der Bot fände es beim
    # Broker nicht (Befund vom 20.11.2026).
    kurz = [b["bot"] for b in mn.bots() if not (b["konto"].isdigit() and len(b["konto"]) > 5)]
    assert not kurz, f"Mitnutzer ohne volle Konto-ID: {kurz}"


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
    from suche import krypto_bollinger_bot
    for aid in kont.get("frei") or []:
        if str(aid) == str(krypto_bollinger_bot.KONTO):
            # Account 3 ist frei, seit Vortag GBP/JPY beendet ist (Kirons Wort vom 22.11.2026). Dort handeln der
            # Bollinger-Krypto-Bot und seit dem 26.11.2026 V1 mit wachsendem Einsatz, und die Prüfung vergibt das Konto
            # darum nie.
            assert mit[str(aid)] == [krypto_bollinger_bot.BOT_ID, "v1-wachsend"]
        elif str(aid) in mit:
            assert any(b.startswith("scalp-") or b == "gold-staffel" for b in mit[str(aid)])
    # kein Mitnutzer steht zugleich in der Zuordnung (dann gälte für ihn die Prüfung nach 15/40 Trades doppelt)
    assert not {b["bot"] for b in mn.bots()} & set(kont.get("zuordnung") or {})
