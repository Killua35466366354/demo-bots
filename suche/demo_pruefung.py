"""Prüfung der Demo-Bots nach 15 und 40 Trades und Wechsel deutlich schlechterer (Regel: suche/VORAB_wechsel.yaml).

Kirons Wunsch vom 04.11.2026, 11:55 UTC: "stelle sicher mit strategien zu wechseln die deutlich schlechter sind". Nur
Capital.com-Demo. Die Prüfung liest nur Dateien (kein Broker) und läuft im Workflow der Demo-Bots vor allen Bot-Läufen:

1. Für jeden Bot mit eigenem Konto (journal/konten.json, zuordnung; nicht der Gold-Bot auf dem Hauptkonto) zählt sie
   die geschlossenen Demo-Trades seit er sein jetziges Konto hat und rechnet den Gewinnfaktor auf R.
2. Ab 15 Trades unter 0,6, ab 40 Trades unter 1,0 (oder unter 1,2, wenn ein bestandener Ersatz bereitsteht): der Bot
   kommt unter abgeloest in journal/konten.json, mit dem Nachfolger aus der Rangliste (journal/portfolio.json) oder
   ohne (dann wird sein Konto frei).
3. Die Bot-Läufe (suche/demo_bots.py, suche/london_bot.py für US500/US100/Dow/Nasdaq, suche/r6_bots.py) öffnen für einen
   abgelösten Bot nichts Neues; ist seine Position zu, schreiben sie das Konto auf den Nachfolger um oder geben es frei
   (kont["frei"]). Ein freies Konto vergibt diese Prüfung an die nächste bestandene Strategie mit Bot-Lauf.
4. journal/portfolio.json bekommt je Bot den Demo-Stand ("demo") und die Rolle (aktiv, wartet, abgeloest).
5. Kirons Auswahl (suche/auswahl.yaml, "abschalten"): diese Bots werden abgelöst wie in Schritt 2, ohne Nachfolger.

    python -m suche.demo_pruefung             # prüfen und speichern
    python -m suche.demo_pruefung --dry-run   # nur ausgeben
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
J = ROOT / "journal"
VORAB = ROOT / "suche" / "VORAB_wechsel.yaml"
KEY = "VORAB_wechsel sha256 "
HAUPT_BOT = "gold-cb"            # das Hauptkonto gehört dem Gold-Bot, er wird hier nie geprüft
AUSWAHL = ROOT / "suche" / "auswahl.yaml"


def regel() -> dict | None:
    """Die Regel aus VORAB_wechsel.yaml, nur wenn ihre Prüfsumme im Journal steht (sonst keine Prüfung)."""
    from suche.runde1 import journal_lines, last_value
    from suche.runde3 import sha256_text
    text = VORAB.read_text(encoding="utf-8")
    if last_value(journal_lines(), KEY) != sha256_text(text):
        return None
    return yaml.safe_load(text)["wechsel"]


def laeufe() -> dict[str, Path]:
    """Bot-ID -> Datei mit seinen Demo-Trades, für jeden Bot, der einen Lauf hat."""
    from suche.demo_bots import alle_bots
    from suche.wochenbericht import WEITERE
    cfg = yaml.safe_load((ROOT / "suche" / "demo_bots.yaml").read_text(encoding="utf-8"))
    out = {b["id"]: J / "demo-bots" / "trades.jsonl" for b in alle_bots(cfg)}
    out.update({w[0]: J / w[5] for w in WEITERE})
    return out


def _kurz(aid) -> str | None:
    from gold.bot.konten import kurz
    return kurz(None if aid is None else str(aid))


def _lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for x in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(x))
        except ValueError:
            continue
    return out


def _kombi(bot_id: str) -> bool:
    """Teilt der Bot sein Konto mit anderen Strategien (suche/kombi.yaml)? Dann bekommt beim Wechsel niemand sein Konto."""
    from suche.london_bot import kombi_gruppe
    return kombi_gruppe(bot_id) is not None


def _r6_beendet() -> dict:
    """Runde-6-Bots, die ihr eigener Lauf beendet (suche/r6_bots.py, BEENDET), im Format von abgeloest."""
    try:
        from suche.r6_bots import BEENDET
    except Exception:                 # noqa: BLE001 - ohne die Liste prüft die Prüfung sie eben mit
        return {}
    return {k: {"an": v.get("an")} for k, v in BEENDET.items()}


def abschalten() -> dict:
    """Kirons Auswahl: Bots, die abgeschaltet werden ({bot_id: Grund})."""
    if not AUSWAHL.exists():
        return {}
    return (yaml.safe_load(AUSWAHL.read_text(encoding="utf-8")) or {}).get("auswahl", {}).get("abschalten") or {}


def seit_wann(kont: dict, bot_id: str) -> str | None:
    """Ab wann der Bot sein jetziges Konto hat: die letzte Übergabe an ihn, sonst von Anfang an (None)."""
    zeiten = [u.get("zeit") for u in kont.get("uebergaben") or [] if u.get("an") == bot_id and u.get("zeit")]
    return max(zeiten) if zeiten else None


def kennzahl(trades: list[dict]) -> dict:
    r = [float(t["r"]) for t in trades if t.get("r") is not None]
    g, v = sum(x for x in r if x > 0), -sum(x for x in r if x < 0)
    return {"trades": len(r), "pf": None if v == 0 else round(g / v, 3), "summe_r": round(sum(r), 2)}


def demo_trades(path: Path, bot_id: str, seit: str | None) -> list[dict]:
    return [t for t in _lines(path) if t.get("bot") in (bot_id, None) and (seit is None or str(t.get("closed_utc") or "") >= seit)]


def entscheide(k: dict, rg: dict, ersatz_da: bool) -> str | None:
    """Grund für einen Wechsel nach der Regel, sonst None. Ohne Verlust-Trade (pf None) nie."""
    n, pf = k["trades"], k["pf"]
    if pf is None:
        return None
    u, f = rg["urteil"], rg["frueh"]
    if n >= u["ab_trades"] and pf < u["wechsel_wenn_pf_unter"]:
        return f"nach {n} Demo-Trades Gewinnfaktor {pf:.2f}, unter {u['wechsel_wenn_pf_unter']}"
    if n >= u["ab_trades"] and pf < u["wechsel_mit_ersatz_wenn_pf_unter"] and ersatz_da:
        return f"nach {n} Demo-Trades Gewinnfaktor {pf:.2f}, unter {u['wechsel_mit_ersatz_wenn_pf_unter']}, Ersatz bereit"
    if n >= f["ab_trades"] and pf < f["wechsel_wenn_pf_unter"]:
        return f"nach {n} Demo-Trades Gewinnfaktor {pf:.2f}, deutlich unter {f['wechsel_wenn_pf_unter']}"
    return None


def stand_text(k: dict, rg: dict) -> str:
    n, f, u = k["trades"], rg["frueh"]["ab_trades"], rg["urteil"]["ab_trades"]
    if n < f:
        return f"{n} von {f} Trades bis zur ersten Prüfung"
    if n < u:
        return f"erste Prüfung bestanden, {n} von {u} Trades bis zum Urteil"
    return f"Urteil nach {n} Trades bestanden"


def ersatz(kont: dict, pf: dict, lauf_ids, demo_abl: dict) -> str | None:
    """Die beste bestandene Strategie mit Bot-Lauf, die kein Konto hat, nicht wartet und nie abgelöst wurde."""
    zu = kont.get("zuordnung") or {}
    abl = {**demo_abl, **(kont.get("abgeloest") or {})}
    vergeben = {n.get("an") for n in abl.values() if n} | set(zu)
    for b in sorted((pf or {}).get("bots") or [], key=lambda x: x.get("rang") or 999):
        bid = b.get("id")
        if (b.get("bestanden") and bid in lauf_ids and bid != HAUPT_BOT and bid not in vergeben and bid not in abl
                and b.get("rolle") not in ("abgeloest", "wartet")):
            return bid
    return None


def pruefen(kont: dict, pf: dict | None, demo_cfg: dict, stamp: str, rg: dict | None = None,
            dateien: dict[str, Path] | None = None, aus: dict | None = None) -> tuple[list[dict], dict]:
    """Eine Prüfung (reine Funktion bis auf das Lesen der Trade-Dateien). Ändert `kont` (abgeloest, zuordnung für
    freie Konten). Rückgabe: Ereignisse fürs Log und Demo-Stand je Bot."""
    rg = rg or regel()
    if rg is None:
        return [{"time": stamp, "event": "Prüfung übersprungen", "why": "Prüfsumme von VORAB_wechsel.yaml fehlt"}], {}
    dateien = dateien if dateien is not None else laeufe()
    demo_abl = {**(demo_cfg.get("abgeloest") or {}), **_r6_beendet()}   # schon abgelöst (Bewertung 2025-2026)
    zu = kont.setdefault("zuordnung", {})
    abl = kont.setdefault("abgeloest", {})
    log, stand = [], {}
    # Kirons Auswahl (suche/auswahl.yaml): abschalten ohne Nachfolger, das Konto wird frei
    for bot_id, warum in sorted((abschalten() if aus is None else aus).items()):
        if bot_id in zu and bot_id != HAUPT_BOT and bot_id not in abl and bot_id not in demo_abl:
            grund = f"Kirons Auswahl vom 04.11.2026 (abschalten): {warum}"
            abl[bot_id] = {"an": None, "seit": stamp, "grund": grund}
            log.append({"time": stamp, "event": "Bot abgeschaltet", "bot": bot_id, "an": None, "why": grund})
    for bot_id in sorted(zu):
        if bot_id == HAUPT_BOT or bot_id in abl or bot_id in demo_abl or bot_id not in dateien:
            continue
        k = kennzahl(demo_trades(dateien[bot_id], bot_id, seit_wann(kont, bot_id)))
        stand[bot_id] = {**k, "pruefung": stand_text(k, rg)}
        nach = None if _kombi(bot_id) else ersatz(kont, pf, dateien, demo_abl)   # gemeinsames Konto bleibt den anderen
        grund = entscheide(k, rg, nach is not None)
        if grund:
            abl[bot_id] = {"an": nach, "seit": stamp, "grund": grund, "messung": k}
            stand[bot_id]["pruefung"] = "abgelöst: " + grund
            log.append({"time": stamp, "event": "Bot abgelöst", "bot": bot_id, "an": nach, "why": grund})
    # Freie Konten (abgelöst ohne Nachfolger) an die nächste bestandene Strategie mit Bot-Lauf
    for aid in list(kont.get("frei") or []):
        nach = ersatz(kont, pf, dateien, demo_abl)
        if not nach:
            break
        zu[nach] = aid
        kont["frei"].remove(aid)
        kont.setdefault("uebergaben", []).append({"zeit": stamp, "konto": _kurz(aid), "konto_id": str(aid),
                                                  "von": None, "an": nach})
        log.append({"time": stamp, "event": "freies Konto vergeben", "an": nach, "konto": _kurz(aid)})
    return log, stand


def portfolio_stand(pf: dict, kont: dict, stand: dict) -> bool:
    """Demo-Stand und Rollen in journal/portfolio.json eintragen. True, wenn sich etwas geändert hat."""
    zu = kont.get("zuordnung") or {}
    abl = kont.get("abgeloest") or {}
    namen = {b.get("id"): b.get("name") for b in pf.get("bots") or []}
    konto_name = {e.get("id"): e.get("name") for e in kont.get("konten") or []}
    vorher = json.dumps(pf, sort_keys=True, ensure_ascii=False)
    nachfolger = {n["an"]: alt for alt, n in abl.items() if n and n.get("an")}
    for b in pf.get("bots") or []:
        bid = b.get("id")
        if bid in stand:
            b["demo"] = stand[bid]
        if bid in abl:
            b["rolle"], b["ersetzt_durch"] = "abgeloest", namen.get((abl[bid] or {}).get("an"))
            b["warum"] = "Demo: " + (abl[bid] or {}).get("grund", "") + (
                "" if (abl[bid] or {}).get("an") else ". Konto wird frei")
        elif bid in nachfolger and bid not in zu:
            alt = nachfolger[bid]
            b["rolle"], b["ersetzt"] = "wartet", namen.get(alt)
            aid = zu.get(alt)
            b["konto"] = konto_name.get(_kurz(aid)) if aid else b.get("konto")
        elif bid in zu:
            if b.get("rolle") in ("wartet", "nicht_gewaehlt"):
                b["rolle"] = "aktiv"
            b["konto"] = konto_name.get(_kurz(zu[bid])) or b.get("konto")
            geteilt = sorted(namen.get(k) or k for k, v in zu.items() if v == zu[bid] and k != bid)
            if geteilt:
                b["konto_geteilt_mit"] = geteilt
    return json.dumps(pf, sort_keys=True, ensure_ascii=False) != vorher


def main(argv: list[str]) -> int:
    from datetime import datetime, timezone

    from gold.bot import konten
    stamp = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat()
    kont = konten.load(J)
    if not kont.get("zuordnung"):
        print("Keine Konten zugeordnet, nichts zu prüfen")
        return 0
    pf_path = J / "portfolio.json"
    pf = json.loads(pf_path.read_text(encoding="utf-8")) if pf_path.exists() else None
    demo_cfg = yaml.safe_load((ROOT / "suche" / "demo_bots.yaml").read_text(encoding="utf-8"))
    log, stand = pruefen(kont, pf, demo_cfg, stamp)
    print(json.dumps({"log": log, "stand": stand}, ensure_ascii=False, indent=1))
    if "--dry-run" in argv:
        return 0
    if log and any(e["event"] != "Prüfung übersprungen" for e in log):
        konten.save(kont, J)
        with open(J / "demo-pruefung.jsonl", "a", encoding="utf-8") as fh:
            for e in log:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    if pf is not None and portfolio_stand(pf, kont, stand):
        pf_path.write_text(json.dumps(pf, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
