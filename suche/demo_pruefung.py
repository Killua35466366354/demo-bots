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
6. Labor (Kirons Entscheidung vom 05.11.2026, suche/VORAB_labor.yaml): vier abgeschaltete, aber bestandene Strategien
   bekommen einmal ein freies Konto zurück, solange danach noch genug Konten frei bleiben. Danach gilt für sie die
   Prüfung nach 15/40 Trades wie für alle.
7. Mess-Bots (Kirons Ja vom 05.11.2026 17:07 UTC, suche/VORAB_messbots.yaml): Vortag EUR/USD mit 1 x ATR bekommt einmal
   Account 2. Rutsch-Regel (Kirons Ja vom selben Zeitpunkt, suche/VORAB_rutschen.yaml): rutscht ein Vortag-Bot beim
   Einstieg im Median der letzten 10 Trades mehr als seine Grenze, wird er abgelöst wie in Schritt 2.
8. Feste Frist (Kritik D1, suche/VORAB_frist.yaml): alle 6 Monate auf dem Konto ein Urteil, auch ohne 40 Trades.

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
LABOR = ROOT / "suche" / "VORAB_labor.yaml"
LABOR_KEY = "VORAB_labor sha256 "
MESS = ROOT / "suche" / "VORAB_messbots.yaml"
MESS_KEY = "VORAB_messbots sha256 "
RUTSCH = ROOT / "suche" / "VORAB_rutschen.yaml"
RUTSCH_KEY = "VORAB_rutschen sha256 "
FRIST = ROOT / "suche" / "VORAB_frist.yaml"
FRIST_KEY = "VORAB_frist sha256 "
WOCHE = ROOT / "suche" / "VORAB_eine_woche.yaml"
WOCHE_KEY = "VORAB_eine_woche sha256 "


def regel() -> dict | None:
    """Die Regel aus VORAB_wechsel.yaml, nur wenn ihre Prüfsumme im Journal steht (sonst keine Prüfung)."""
    from suche.runde1 import journal_lines, last_value
    from suche.runde3 import sha256_text
    text = VORAB.read_text(encoding="utf-8")
    if last_value(journal_lines(), KEY) != sha256_text(text):
        return None
    return yaml.safe_load(text)["wechsel"]


def _versiegelt(path: Path, key: str, feld: str) -> dict | None:
    """Inhalt `feld` einer VORAB-Datei, nur wenn ihre Prüfsumme im Journal steht (sonst gilt die Datei nicht)."""
    from suche.runde1 import journal_lines, last_value
    from suche.runde3 import sha256_text
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if last_value(journal_lines(), key) != sha256_text(text):
        return None
    return yaml.safe_load(text)[feld]


def labor_regel() -> dict | None:
    """Die Regel aus VORAB_labor.yaml, nur wenn ihre Prüfsumme im Journal steht (sonst kein Labor)."""
    return _versiegelt(LABOR, LABOR_KEY, "labor")


def mess_regel() -> dict | None:
    """Die Mess-Bots aus VORAB_messbots.yaml, nur wenn ihre Prüfsumme im Journal steht."""
    return _versiegelt(MESS, MESS_KEY, "messbots")


def rutsch_regel() -> dict | None:
    """Die Rutsch-Regel aus VORAB_rutschen.yaml, nur wenn ihre Prüfsumme im Journal steht."""
    return _versiegelt(RUTSCH, RUTSCH_KEY, "rutschen")


def frist_regel() -> dict | None:
    """Die feste Frist aus VORAB_frist.yaml, nur wenn ihre Prüfsumme im Journal steht."""
    return _versiegelt(FRIST, FRIST_KEY, "frist")


def woche_regel() -> dict | None:
    """Eine Woche live (VORAB_eine_woche.yaml, Fassung B des Gerichts), nur wenn ihre Prüfsumme im Journal steht."""
    return _versiegelt(WOCHE, WOCHE_KEY, "eine_woche")


def start_utc(bot_id: str, j: Path | None = None) -> str | None:
    """start_utc des Bots aus seinem Journal: journal/r6-bots/state.json, seine eigene Datei oder journal/demo-bots.json."""
    j = j or J

    def lies(p: Path) -> dict:
        try:
            d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        except (OSError, ValueError):
            return {}
        return d if isinstance(d, dict) else {}
    v = ((lies(j / "r6-bots" / "state.json").get("bots") or {}).get(bot_id) or {}).get("start_utc")
    if v:
        return str(v)
    for p in sorted(j.glob("*.json")):
        d = lies(p)
        if d.get("bot") == bot_id and d.get("start_utc"):
            return str(d["start_utc"])
    d = lies(j / "demo-bots.json")
    if d.get("start_utc") and any(isinstance(b, dict) and b.get("id") == bot_id for b in d.get("bots") or []):
        return str(d["start_utc"])
    return None


def woche_bis(kont: dict, bot_id: str, wo: dict | None, start: str | None = None) -> str | None:
    """Ende der ersten Woche (VORAB_eine_woche.yaml): 7 Tage nach dem spätesten von start_utc, letzter Kontoübergabe
    und Merge der letzten Regeländerung. None ohne Regel oder für den Gold-Bot."""
    import pandas as pd
    if not wo or bot_id in (wo.get("nie_fuer") or []) or bot_id == HAUPT_BOT:
        return None
    zeiten = [t for t in (start, seit_wann(kont, bot_id), (wo.get("konto_seit") or {}).get(bot_id),
                          (wo.get("regel_seit") or {}).get(bot_id)) if t]
    beginn = max(pd.Timestamp(t) for t in zeiten) if zeiten else pd.Timestamp(wo["ohne_eintrag"])
    return (beginn + pd.Timedelta(days=int(wo["tage"]))).isoformat()


def kirons_wort(text) -> bool:
    """Kirons eigenes datiertes Wort (VORAB_eine_woche.yaml kirons_wort): Text beginnt mit "Kirons Wort vom TT.MM.JJJJ"."""
    import re
    return bool(re.match(r"Kirons Wort vom \d{2}\.\d{2}\.\d{4}", str(text or "").strip()))


def wartet(kont: dict, bot_id: str, bis: str, warum: str, stamp: str) -> list[dict]:
    """Eine aufgeschobene Ablösung: einmal je Grund "Ablösung wartet" ins Log (kont["woche"] merkt sich den Grund)."""
    if (kont.get("woche") or {}).get(bot_id, {}).get("why") == warum:
        return []
    kont.setdefault("woche", {})[bot_id] = {"bis": bis, "why": warum, "seit": stamp}
    return [{"time": stamp, "event": "Ablösung wartet", "bot": bot_id, "bis": bis, "why": warum}]


def frist_grund(kont: dict, bot_id: str, k: dict, rg: dict, fr: dict | None, stamp: str) -> str | None:
    """Feste Frist (VORAB_frist.yaml): an jeder Frist (alle fr["monate"] Monate ab dem Start) mit weniger als 40 Trades
    wird ein Bot abgelöst, wenn seine Summe R unter 0 liegt oder er keinen Trade hatte. Jede Frist wird nur einmal
    geprüft (kont["frist"][bot_id] = Nummer der zuletzt geprüften Frist)."""
    import pandas as pd
    if not fr:
        return None
    start = max(pd.Timestamp(seit_wann(kont, bot_id) or fr["ab_datum"]), pd.Timestamp(fr["ab_datum"]))
    jetzt, n = pd.Timestamp(stamp), 0
    while jetzt >= start + pd.DateOffset(months=int(fr["monate"]) * (n + 1)):
        n += 1
    schon = int((kont.get("frist") or {}).get(bot_id, {}).get("nr", 0))
    if n <= schon:
        return None
    kont.setdefault("frist", {})[bot_id] = {"nr": n, "zeit": stamp, "start": str(start), **k}
    if k["trades"] >= rg["urteil"]["ab_trades"]:
        return None
    if k["trades"] == 0 or k["summe_r"] < 0:
        return (f"Frist nach {int(fr['monate']) * n} Monaten (suche/VORAB_frist.yaml): {k['trades']} Demo-Trades, Summe "
                f"{k['summe_r']:+.2f} R")
    return None


def mess_vergeben(kont: dict, mb: dict | None, lauf_ids, stamp: str) -> list[dict]:
    """Mess-Bots (VORAB_messbots.yaml): ein Mess-Bot mit festem Konto bekommt es genau einmal, wenn es frei ist und danach
    noch vergabe["frei_lassen"] Konten frei bleiben. Ändert `kont` (zuordnung, frei, uebergaben, messung)."""
    if not mb:
        return []
    zu = kont.setdefault("zuordnung", {})
    schon = kont.get("messung") or {}
    halten = int((mb.get("vergabe") or {}).get("frei_lassen", 0))
    log = []
    for bot_id, m in mb.items():
        aid = str((m or {}).get("konto") or "") if isinstance(m, dict) else ""
        frei = [str(x) for x in kont.get("frei") or []]
        if (not aid or bot_id in schon or bot_id in zu or bot_id not in lauf_ids or bot_id == HAUPT_BOT
                or bot_id in (kont.get("abgeloest") or {}) or aid not in frei or len(frei) - 1 < halten):
            continue
        zu[bot_id] = aid
        kont["frei"] = [x for x in kont.get("frei") or [] if str(x) != aid]
        kont.setdefault("messung", {})[bot_id] = {"seit": stamp, "konto": _kurz(aid)}
        kont.setdefault("uebergaben", []).append({"zeit": stamp, "konto": _kurz(aid), "konto_id": aid, "von": None,
                                                  "an": bot_id, "messung": True})
        log.append({"time": stamp, "event": "Mess-Konto vergeben", "bot": bot_id, "konto": _kurz(aid),
                    "why": "Kirons Ja vom 05.11.2026 17:07 UTC (suche/VORAB_messbots.yaml)"})
    return log


def rutsch_messung(trades: list[dict], ru: dict) -> dict:
    """Rutschen beim Einstieg über die Stop-Orders (ohne nachgeholte und übernommene Trades): Anzahl und Median der
    letzten ru["fenster"] Trades in Pips."""
    import statistics
    r = [float(t["rutschen_pips"]) for t in trades
         if t.get("rutschen_pips") is not None and not t.get("nachgeholt") and not t.get("uebernommen")]
    letzte = r[-int(ru.get("fenster", 10)):]
    return {"trades": len(r), "median_pips": round(statistics.median(letzte), 2) if letzte else None}


def rutsch_grund(bot_id: str, trades: list[dict], ru: dict | None) -> str | None:
    """Grund für die Ablösung nach VORAB_rutschen.yaml, sonst None."""
    grenze = ((ru or {}).get("gilt_fuer") or {}).get(bot_id)
    if grenze is None:
        return None
    m = rutsch_messung(trades, ru)
    if m["trades"] < int(ru.get("ab_trades", 10)) or m["median_pips"] is None or m["median_pips"] <= float(grenze):
        return None
    return (f"Rutschen beim Einstieg im Median {m['median_pips']:.1f} Pips (letzte {min(m['trades'], int(ru.get('fenster', 10)))} "
            f"Trades), über der Grenze von {grenze} Pips (suche/VORAB_rutschen.yaml)")


def labor_vergeben(kont: dict, lb: dict | None, lauf_ids, demo_abl: dict, stamp: str) -> list[dict]:
    """Labor-Vorwärtstest (VORAB_labor.yaml): jeder Labor-Bot bekommt einmal ein freies Konto, am liebsten sein altes,
    solange danach noch lb["frei_lassen"] Konten frei sind. Nur Bots, die Kirons Auswahl abgeschaltet hat, nie einen,
    den die Prüfung nach 15/40 Trades abgelöst hat. Ändert `kont` (abgeloest, zuordnung, frei, uebergaben, labor)."""
    if not lb:
        return []
    zu = kont.setdefault("zuordnung", {})
    abl = kont.setdefault("abgeloest", {})
    schon = kont.get("labor") or {}
    log = []
    for bot_id, wunsch in (lb.get("bots") or {}).items():
        a = abl.get(bot_id) or {}
        if (bot_id in schon or bot_id in zu or bot_id not in lauf_ids or bot_id in demo_abl or bot_id == HAUPT_BOT
                or a.get("messung") or a.get("an") or (bot_id in abl and "Kirons Auswahl" not in str(a.get("grund")))):
            continue
        frei = [str(x) for x in kont.get("frei") or []]
        if len(frei) <= int(lb.get("frei_lassen", 2)):
            break
        alt = str((wunsch or {}).get("konto") or "")
        aid = alt if alt in frei else frei[0]
        abl.pop(bot_id, None)
        zu[bot_id] = aid
        kont["frei"] = [x for x in kont.get("frei") or [] if str(x) != aid]
        kont.setdefault("labor", {})[bot_id] = {"seit": stamp, "konto": _kurz(aid)}
        kont.setdefault("uebergaben", []).append({"zeit": stamp, "konto": _kurz(aid), "konto_id": aid, "von": None,
                                                  "an": bot_id, "labor": True})
        log.append({"time": stamp, "event": "Labor-Konto vergeben", "bot": bot_id, "konto": _kurz(aid),
                    "why": "Kirons Entscheidung vom 05.11.2026 (suche/VORAB_labor.yaml)"})
    return log


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
            dateien: dict[str, Path] | None = None, aus: dict | None = None,
            lb: dict | None = None, mb: dict | None = None, ru: dict | None = None,
            fr: dict | None = None, wo: dict | None = None,
            starts: dict[str, str] | None = None) -> tuple[list[dict], dict]:
    """Eine Prüfung (reine Funktion bis auf das Lesen der Trade-Dateien). Ändert `kont` (abgeloest, zuordnung für
    freie Konten). Rückgabe: Ereignisse fürs Log und Demo-Stand je Bot. wo/starts: VORAB_eine_woche.yaml und start_utc je
    Bot; die eingefrorenen Prüfungen (Wechsel, Rutschen, Frist, Labor, Mess-Bots) setzt die Woche nicht aus."""
    import pandas as pd
    rg = rg or regel()
    if rg is None:
        return [{"time": stamp, "event": "Prüfung übersprungen", "why": "Prüfsumme von VORAB_wechsel.yaml fehlt"}], {}
    dateien = dateien if dateien is not None else laeufe()
    demo_abl = {**(demo_cfg.get("abgeloest") or {}), **_r6_beendet()}   # schon abgelöst (Bewertung 2025-2026)
    zu = kont.setdefault("zuordnung", {})
    abl = kont.setdefault("abgeloest", {})
    log, stand = [], {}
    # Labor (suche/VORAB_labor.yaml): abgeschaltete, aber bestandene Strategien bekommen einmal ein freies Konto
    log += labor_vergeben(kont, lb, dateien, demo_abl, stamp)
    # Mess-Bots (suche/VORAB_messbots.yaml): Vortag EUR/USD mit 1 x ATR bekommt einmal sein festes freies Konto
    log += mess_vergeben(kont, mb, dateien, stamp)
    # Kirons Auswahl (suche/auswahl.yaml): abschalten ohne Nachfolger, das Konto wird frei
    for bot_id, warum in sorted((abschalten() if aus is None else aus).items()):
        # Ein Labor-Bot (VORAB_labor.yaml) geht nur mit Kirons datiertem Wort, nie mit einer bloßen Auswahlliste
        if (bot_id in zu and bot_id != HAUPT_BOT and bot_id not in abl and bot_id not in demo_abl
                and (bot_id not in (kont.get("labor") or {}) or kirons_wort(warum))):
            # Erste Woche live (VORAB_eine_woche.yaml): eine Auswahlliste schaltet nichts ab, nur Kirons datiertes Wort
            bis = woche_bis(kont, bot_id, wo, (starts or {}).get(bot_id))
            if bis and pd.Timestamp(stamp) < pd.Timestamp(bis) and not kirons_wort(warum):
                log += wartet(kont, bot_id, bis, f"suche/auswahl.yaml abschalten: {warum}", stamp)
                continue
            grund = (str(warum) if kirons_wort(warum) else f"Kirons Auswahl vom 04.11.2026 (abschalten): {warum}")
            abl[bot_id] = {"an": None, "seit": stamp, "grund": grund}
            log.append({"time": stamp, "event": "Bot abgeschaltet", "bot": bot_id, "an": None, "why": grund})
    for bot_id in sorted(zu):
        if bot_id == HAUPT_BOT or bot_id in abl or bot_id in demo_abl or bot_id not in dateien:
            continue
        tr = demo_trades(dateien[bot_id], bot_id, seit_wann(kont, bot_id))
        k = kennzahl(tr)
        stand[bot_id] = {**k, "pruefung": stand_text(k, rg)}
        if bot_id in ((ru or {}).get("gilt_fuer") or {}):
            stand[bot_id]["rutschen"] = rutsch_messung(tr, ru)
        nach = None if _kombi(bot_id) else ersatz(kont, pf, dateien, demo_abl)   # gemeinsames Konto bleibt den anderen
        alte_frist = ((kont.get("frist") or {}).get(bot_id) or {}).get("nr")
        grund = (entscheide(k, rg, nach is not None) or rutsch_grund(bot_id, tr, ru)
                 or frist_grund(kont, bot_id, k, rg, fr, stamp))
        neue_frist = ((kont.get("frist") or {}).get(bot_id) or {}).get("nr")
        if not grund and neue_frist != alte_frist:          # Frist bestanden: festhalten, damit sie nur einmal zählt
            log.append({"time": stamp, "event": "Frist bestanden", "bot": bot_id, "nr": neue_frist,
                        "trades": k["trades"], "summe_r": k["summe_r"]})
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
    labor = kont.get("labor") or {}
    for b in pf.get("bots") or []:
        bid = b.get("id")
        if bid in stand:
            b["demo"] = stand[bid]
        if bid in abl:
            b["rolle"], b["ersetzt_durch"] = "abgeloest", namen.get((abl[bid] or {}).get("an"))
            b["warum"] = "Demo: " + (abl[bid] or {}).get("grund", "") + (
                "" if (abl[bid] or {}).get("an") else ". Konto wird frei")
        elif bid in labor and bid in zu:
            b["rolle"], b["ersetzt_durch"] = "labor", None
            b["konto"] = konto_name.get(_kurz(zu[bid])) or b.get("konto")
            b["warum"] = (f"Labor-Vorwärtstest seit {str(labor[bid].get('seit'))[:10]} (Kirons Entscheidung vom "
                          "05.11.2026, suche/VORAB_labor.yaml); nicht im Kern und nicht in der Kombi")
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
    wo = woche_regel()
    starts = {b: v for b in kont.get("zuordnung") or {} if (v := start_utc(b))}
    log, stand = pruefen(kont, pf, demo_cfg, stamp, lb=labor_regel(), mb=mess_regel(), ru=rutsch_regel(),
                         fr=frist_regel(), wo=wo, starts=starts)
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
