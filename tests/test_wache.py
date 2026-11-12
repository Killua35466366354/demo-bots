"""Wache: Siegel aller Regeldateien und stille Fehler der Bot-Schritte (suche/wache.py; Befunde B-05, B-06 und B-09 der
Projekt-Prüfung vom 11.11.2026)."""
import json
from pathlib import Path

import yaml

from suche import wache

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / ".github" / "workflows"


# ---------- Siegel ----------

def test_alle_siegel_stimmen():
    """Macht einen PR rot, der eine Siegel-Zeile verliert (so geschehen bei #30 und #35 beim Lösen eines Konflikts) oder
    eine Regeldatei nach dem Festlegen ändert. Dann würden die Bots nach dem Merge nichts mehr öffnen."""
    probleme = wache.siegel_pruefen()
    assert probleme == [], ("Siegel fehlt oder passt nicht. Eine Regeldatei wird nie nachträglich geändert, und beim Lösen "
                            "eines Konflikts in journal/strategie-suche-protokoll.md bleiben beide Seiten Zeile für Zeile "
                            "erhalten:\n" + "\n".join(p["text"] for p in probleme))


def test_wache_rechnet_wie_die_bots():
    from suche.runde1 import journal_lines, last_value
    from suche.runde3 import sha256_text
    dateien = wache.vorab_dateien()
    assert len(dateien) >= 39 and all(p.name.startswith("VORAB") for p in dateien)
    zeilen = journal_lines()
    for p in dateien:
        text = p.read_text(encoding="utf-8")
        assert wache.sha256_text(text) == sha256_text(text)
        assert wache.letzter_wert(zeilen, f"{p.stem} sha256 ") == last_value(zeilen, f"{p.stem} sha256 ")


def test_jede_regeldatei_der_laufenden_bots_wird_bewacht():
    from gold import ausbruch4h_bot, grossbox_bot, hand_bot, pine5m_bot, zonen_bot
    from gold.bot import schalter
    from suche import demo_pruefung, gold_staffel_bot, scalper_bot, vergleich
    bewacht = {f"{p.stem} sha256 " for p in wache.vorab_dateien()}
    keys = {ausbruch4h_bot.KEY, grossbox_bot.KEY, hand_bot.KEY, zonen_bot.KEY, pine5m_bot.KEY, pine5m_bot.KEY_PRUEFER, pine5m_bot.KEY_K5, pine5m_bot.KEY_4H,
            schalter.KEY, gold_staffel_bot.KEY, gold_staffel_bot.KEY_ABFANG, scalper_bot.KEY, vergleich.KEY,
            demo_pruefung.KEY, demo_pruefung.LABOR_KEY, demo_pruefung.MESS_KEY, demo_pruefung.RUTSCH_KEY,
            demo_pruefung.FRIST_KEY, demo_pruefung.WOCHE_KEY}
    assert keys <= bewacht, f"nicht bewacht: {sorted(keys - bewacht)}"


def test_ausnahmen_sind_begruendet_und_es_gibt_die_dateien():
    for rel, grund in wache.AUSNAHMEN.items():
        assert (ROOT / rel).exists() and len(grund) > 10


def _mini(tmp_path, zeilen, inhalt="regel: 1\n"):
    (tmp_path / "suche").mkdir()
    (tmp_path / "gold" / "bot").mkdir(parents=True)
    (tmp_path / "journal").mkdir()
    (tmp_path / "suche" / "VORAB_test.yaml").write_text(inhalt, encoding="utf-8")
    (tmp_path / wache.PROTOKOLL).write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    return wache.sha256_text(inhalt)


def test_fehlende_und_falsche_siegel_werden_erkannt(tmp_path):
    h = _mini(tmp_path, ["# Protokoll"])
    p = wache.siegel_pruefen(tmp_path)
    assert [x["problem"] for x in p] == ["fehlt"] and "VORAB_test" in p[0]["text"]
    prot = tmp_path / wache.PROTOKOLL
    prot.write_text(f"- 2026-11-10 10:00 UTC: festgelegt. VORAB_test sha256 {h}\n", encoding="utf-8")
    assert wache.siegel_pruefen(tmp_path) == []
    # eine spätere Zeile mit anderer Prüfsumme zählt (die letzte gilt), genau wie bei den Bots
    prot.write_text(prot.read_text(encoding="utf-8") + "- später: VORAB_test sha256 " + "0" * 64 + "\n", encoding="utf-8")
    assert [x["problem"] for x in wache.siegel_pruefen(tmp_path)] == ["passt nicht"]
    # die Datei nachträglich geändert
    prot.write_text(f"- VORAB_test sha256 {h}.\n", encoding="utf-8")
    assert wache.siegel_pruefen(tmp_path) == []                      # Punkt am Zeilenende zählt nicht mit
    (tmp_path / "suche" / "VORAB_test.yaml").write_text("regel: 2\n", encoding="utf-8")
    assert [x["problem"] for x in wache.siegel_pruefen(tmp_path)] == ["passt nicht"]
    # eine Regeldatei unter gold/ wird genauso geprüft
    (tmp_path / "gold" / "bot" / "VORAB_extra.yaml").write_text("x: 1\n", encoding="utf-8")
    assert {x["datei"] for x in wache.siegel_pruefen(tmp_path)} == {"gold/bot/VORAB_extra.yaml", "suche/VORAB_test.yaml"}


def test_verlorene_zeile_aus_dem_echten_protokoll_wird_gefunden(tmp_path):
    """Wie bei #30: Die Zeile einer echten Regeldatei fehlt nach dem Lösen des Konflikts."""
    echt = (ROOT / wache.PROTOKOLL).read_text(encoding="utf-8").splitlines()
    name = "VORAB_pine5m_abfang4h"
    ohne = [z for z in echt if f"{name} sha256 " not in z]
    assert len(ohne) < len(echt)
    _mini(tmp_path, ohne, (ROOT / "suche" / f"{name}.yaml").read_text(encoding="utf-8"))
    (tmp_path / "suche" / "VORAB_test.yaml").rename(tmp_path / "suche" / f"{name}.yaml")
    p = wache.siegel_pruefen(tmp_path)
    assert [x["datei"] for x in p] == [f"suche/{name}.yaml"] and p[0]["problem"] == "fehlt"


def test_ohne_protokoll_ist_das_ein_problem(tmp_path):
    (tmp_path / "suche").mkdir()
    (tmp_path / "gold").mkdir()
    assert wache.siegel_pruefen(tmp_path)[0]["problem"] == "fehlt"


# ---------- Schritte ----------

def _steps(**ergebnis):
    return {k: {"outcome": v, "conclusion": "success", "outputs": {}} for k, v in ergebnis.items()}


def test_zaehlung_in_folge_und_zuruecksetzen():
    assert wache.gescheitert(_steps(r6="failure", us500="success", r7="skipped")) == ["r6"]
    assert wache.gescheitert(None) == [] and wache.gescheitert("kaputt") == []
    z1 = wache.zaehlen({}, ["r6"], "t1")
    z2 = wache.zaehlen(z1, ["r6", "us500"], "t2")
    z3 = wache.zaehlen(z2, ["r6"], "t3")
    assert z1 == {"r6": {"in_folge": 1, "seit": "t1"}}
    assert z2 == {"r6": {"in_folge": 2, "seit": "t1"}, "us500": {"in_folge": 1, "seit": "t2"}}
    assert z3 == {"r6": {"in_folge": 3, "seit": "t1"}} and wache.alarm(z3) == ["r6"] and wache.alarm(z2) == []
    assert wache.zaehlen(z3, ["r6"], "t4") == z3                      # bleibt bei 3 stehen: die Datei ändert sich nicht mehr
    assert wache.zaehlen(z3, [], "t5") == {}                          # ein guter Lauf setzt zurück
    assert wache.zaehlen({"r6": "kaputt"}, ["r6"], "t6") == {"r6": {"in_folge": 1, "seit": "t6"}}


def _welt(tmp_path):
    h = _mini(tmp_path, [])
    (tmp_path / wache.PROTOKOLL).write_text(f"- VORAB_test sha256 {h}\n", encoding="utf-8")
    post = []
    return post, (lambda url, text: post.append((url, text)))


def test_ein_aussetzer_meldet_nichts_drei_in_folge_schon(tmp_path):
    post, senden = _welt(tmp_path)
    pfad = tmp_path / wache.ZUSTAND["demo-bots"]
    fehler = _steps(r6="failure", us500="success")
    for i, erwartet in enumerate([False, False, True], 1):
        out = wache.lauf("demo-bots", tmp_path, fehler, "KEY", stamp=f"t{i}", senden=senden)
        assert (out["alarm"] == ["r6"]) is erwartet
        url = [u for u, _ in post if "/bot-schritte" in u][-1]
        assert url.endswith("/bot-schritte/fail?create=1") is erwartet
    assert json.loads(pfad.read_text(encoding="utf-8"))["schritte"]["r6"] == {"in_folge": 3, "seit": "t1"}
    assert "r6" in [t for u, t in post if "/bot-schritte/fail" in u][-1]
    # vierter Fehlerlauf: Alarm bleibt, die Datei ändert sich nicht mehr
    vorher = pfad.read_text(encoding="utf-8")
    out = wache.lauf("demo-bots", tmp_path, fehler, "KEY", stamp="t4", senden=senden)
    assert out["alarm"] == ["r6"] and not out["gespeichert"] and pfad.read_text(encoding="utf-8") == vorher
    # ein guter Lauf: Entwarnung
    out = wache.lauf("demo-bots", tmp_path, _steps(r6="success"), "KEY", stamp="t5", senden=senden)
    assert out["alarm"] == [] and out["gespeichert"] and post[-1][0].endswith("/bot-schritte?create=1")
    assert all("/KEY/" in u for u, _ in post)


def test_ruhiger_lauf_schreibt_nur_beim_ersten_mal(tmp_path):
    post, senden = _welt(tmp_path)
    a = wache.lauf("demo-bots", tmp_path, _steps(r6="success"), "KEY", stamp="t1", senden=senden)
    b = wache.lauf("demo-bots", tmp_path, _steps(r6="success"), "KEY", stamp="t2", senden=senden)
    assert a["gespeichert"] and not b["gespeichert"]
    assert [u.split("/KEY/")[1] for u, _ in post] == ["siegel?create=1", "bot-schritte?create=1"] * 2


def test_fehlendes_siegel_meldet_sofort(tmp_path):
    post, senden = _welt(tmp_path)
    (tmp_path / wache.PROTOKOLL).write_text("# leer\n", encoding="utf-8")
    out = wache.lauf("demo-bots", tmp_path, {}, "KEY", stamp="t1", senden=senden)
    assert out["siegel"] and post[0][0].endswith("/siegel/fail?create=1") and "VORAB_test" in post[0][1]
    assert json.loads((tmp_path / wache.ZUSTAND["demo-bots"]).read_text(encoding="utf-8"))["siegel"]


def test_fuenf_minuten_lauf_zaehlt_nur_und_der_grosse_lauf_meldet(tmp_path):
    post, senden = _welt(tmp_path)
    for i in range(3):
        out = wache.lauf("pine5m", tmp_path, _steps(scalper="failure", staffel="success"), "KEY", stamp=f"t{i}",
                         senden=senden)
    assert post == [] and out["alarm"] == ["scalper"] and out["siegel"] is None
    assert (tmp_path / wache.ZUSTAND["pine5m"]).name.startswith("pine-")      # wird vom 5-Minuten-Lauf mitgesichert
    out = wache.lauf("demo-bots", tmp_path, _steps(r6="success"), "KEY", stamp="t9", senden=senden)
    assert out["alarm"] == ["pine5m/scalper"] and post[-1][0].endswith("/bot-schritte/fail?create=1")


def test_trockenlauf_und_fehlender_schluessel_aendern_nichts(tmp_path, capsys):
    post, senden = _welt(tmp_path)
    out = wache.lauf("demo-bots", tmp_path, _steps(r6="failure"), "KEY", trocken=True, senden=senden)
    assert post == [] and not out["gespeichert"] and not (tmp_path / wache.ZUSTAND["demo-bots"]).exists()
    assert wache.ping("siegel", True, None) is False and wache.ping("siegel", True, "") is False

    def kaputt(url, text):
        raise OSError("Netz weg: " + url)
    assert wache.ping("siegel", False, "GEHEIM123", "x", kaputt) is False
    assert "GEHEIM123" not in capsys.readouterr().out                  # der Schlüssel steht nie im Protokoll


def test_main_haelt_nie_einen_lauf_auf(monkeypatch, capsys):
    monkeypatch.setenv("STEPS_JSON", "kein json")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.delenv("HC_PING_KEY", raising=False)
    assert wache.main(["--lauf", "demo-bots"]) == 0
    assert wache.main(["--lauf", "gibt-es-nicht"]) == 0
    assert wache.main(["--lauf"]) == 0
    assert wache.main([]) == 0 and "Regeldateien geprüft, 0 Probleme" in capsys.readouterr().out


# ---------- Workflows ----------

def _schritte(name):
    d = yaml.safe_load((WF / name).read_text(encoding="utf-8"))
    return d["jobs"]["run"]["steps"]


def _pos(steps, teil):
    return next(i for i, s in enumerate(steps) if teil in str(s.get("name") or ""))


def test_wache_laeuft_im_15_minuten_lauf_nach_den_bots_und_vor_dem_sichern():
    steps = _schritte("demo-bots.yml")
    w = steps[_pos(steps, "Wache")]
    assert w["run"] == "python -m suche.wache --lauf demo-bots"
    assert w["continue-on-error"] is True and "!cancelled()" in w["if"]
    assert w["env"]["STEPS_JSON"] == "${{ toJSON(steps) }}" and "HC_PING_KEY" in w["env"]
    ids = [s.get("id") for s in steps[:_pos(steps, "Wache")] if s.get("id")]
    assert len(ids) == len(set(ids))
    # jeder Schritt, der einen Bot oder die Prüfung startet, hat eine ID, sonst sieht die Wache ihn nicht
    for s in steps[:_pos(steps, "Wache")]:
        if "python -m " in str(s.get("run") or "") and s.get("continue-on-error"):
            assert s.get("id"), f"Schritt ohne ID: {s.get('name')}"
    assert _pos(steps, "Wache") < _pos(steps, "Journal sichern") < _pos(steps, "Lebenszeichen")
    # die Wache zählt nicht zu den Testgruppen
    assert "tests-ok" not in w["run"]


def test_fuenf_minuten_lauf_hat_wache_und_lebenszeichen():
    steps = _schritte("pine5m.yml")
    w = steps[_pos(steps, "Wache")]
    assert w["run"] == "python -m suche.wache --lauf pine5m" and w["continue-on-error"] is True
    assert {"pine", "scalper", "staffel", "zonen"} <= {s.get("id") for s in steps}
    assert _pos(steps, "Wache") < _pos(steps, "Journal sichern") < _pos(steps, "Lebenszeichen")
    sichern = steps[_pos(steps, "Journal sichern")]["run"]
    assert "'journal/pine-*'" in sichern                               # nimmt journal/pine-wache.json mit
    assert "'journal/gold-zonen*'" in sichern
    leb = steps[-1]
    assert leb["name"] == "Lebenszeichen" and leb["continue-on-error"] is True and "!cancelled()" in leb["if"]
    assert "hc-ping.com/${HC_PING_KEY}/pine5m${pfad}?create=1" in leb["run"]
    assert leb["env"] == {"HC_PING_KEY": "${{ secrets.HC_PING_KEY }}", "ERGEBNIS": "${{ job.status }}"}
