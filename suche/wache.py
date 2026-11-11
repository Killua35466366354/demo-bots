"""Wache: fehlende Siegel und stille Fehler der Bot-Schritte melden. Liest nur, spricht mit keinem Broker.

Projekt-Prüfung vom 11.11.2026, Befunde B-06 und B-09.

1. Siegel. Jede Regeldatei suche/VORAB*.yaml und gold/**/VORAB*.yaml gilt nur, wenn ihre Prüfsumme im Protokoll
   journal/strategie-suche-protokoll.md steht ("<Dateiname ohne .yaml> sha256 <Prüfsumme>", die letzte Zeile zählt).
   Fehlt die Zeile oder passt sie nicht, öffnen die Bots richtigerweise nichts mehr. Bisher hat das aber niemand
   gemeldet: Bei demo-bots #30 und #35 ging beim Lösen eines Konflikts im Web je eine Siegel-Zeile verloren.
   - Im PR: tests/test_wache.py verlangt, dass alle Siegel stimmen. Ein PR, der eine Zeile verliert, wird rot.
   - Im Betrieb: Der 15-Minuten-Lauf meldet das Ergebnis an healthchecks.io (Check "siegel"). Kiron bekommt eine E-Mail.
2. Stille Fehler. Die Bot-Schritte laufen mit continue-on-error, damit ein Fehler die anderen Bots nie aufhält. Der Lauf
   bleibt dabei grün, und das Lebenszeichen auch. Die Wache zählt je Schritt, wie oft er in Folge gescheitert ist
   (journal/wache.json, für den 5-Minuten-Lauf journal/pine-wache.json). Ab ALARM_AB Läufen in Folge meldet der
   15-Minuten-Lauf das an healthchecks.io (Check "bot-schritte"). Ein einzelner Aussetzer der Börsen-Schnittstelle
   löst nichts aus. Die Dateien ändern sich nur, wenn sich die Zählung ändert.

Die Wache ändert keinen Bot, keine Regel und kein Siegel. Sie nutzt nur die Standardbibliothek, damit ein Fehler in
einem Bot-Modul sie nicht mitreißt. Jeder eigene Fehler wird ausgegeben und nie weitergereicht.

    python -m suche.wache                    # Siegel prüfen und anzeigen
    python -m suche.wache --lauf demo-bots   # im 15-Minuten-Lauf: Siegel und Schritte, Zählung speichern, melden
    python -m suche.wache --lauf pine5m      # im 5-Minuten-Lauf: nur die Schritte zählen (gemeldet wird im 15-Minuten-Lauf)

Umgebung im Workflow: STEPS_JSON (toJSON(steps)), HC_PING_KEY (Secret, wird nie ausgegeben), DRY_RUN.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOKOLL = "journal/strategie-suche-protokoll.md"
# Ausnahmen mit Grund. gold/backtest/VORAB.yaml sind die Regeln des Gold-Backtests aus dem privaten Repo, ihr Siegel
# steht dort in journal/gold-backtest-protokoll.md. Der Schlüssel "VORAB sha256 " gehört in diesem Repo suche/VORAB.yaml.
AUSNAHMEN = {"gold/backtest/VORAB.yaml": "Siegel im privaten Repo (journal/gold-backtest-protokoll.md)"}
ALARM_AB = 3                               # so viele Läufe in Folge muss ein Schritt scheitern
ZUSTAND = {"demo-bots": "journal/wache.json", "pine5m": "journal/pine-wache.json"}
CHECK_SIEGEL = "siegel"
CHECK_SCHRITTE = "bot-schritte"


# ---------- Siegel ----------

def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def letzter_wert(zeilen: list[str], key: str) -> str | None:
    """Wie suche/runde1.py last_value: der Wert hinter `key` in der letzten Zeile, die ihn enthält."""
    for zeile in reversed(zeilen):
        if key in zeile:
            teile = zeile.split(key, 1)[1].split()
            return teile[0].rstrip(".,;") if teile else ""
    return None


def vorab_dateien(root: Path = ROOT) -> list[Path]:
    alle = [*(root / "suche").glob("VORAB*.yaml"), *(root / "gold").rglob("VORAB*.yaml")]
    return sorted(p for p in alle if p.relative_to(root).as_posix() not in AUSNAHMEN)


def siegel_pruefen(root: Path = ROOT) -> list[dict]:
    """Alle Regeldateien gegen das Protokoll. Rückgabe: je Problem {"datei", "problem", "text"}; leer heißt alles gut."""
    prot = root / PROTOKOLL
    if not prot.exists():
        return [{"datei": PROTOKOLL, "problem": "fehlt", "text": f"{PROTOKOLL} fehlt, kein Siegel prüfbar"}]
    zeilen = prot.read_text(encoding="utf-8").splitlines()
    out = []
    for p in vorab_dateien(root):
        rel = p.relative_to(root).as_posix()
        soll = sha256_text(p.read_text(encoding="utf-8"))
        ist = letzter_wert(zeilen, f"{p.stem} sha256 ")
        if ist is None:
            out.append({"datei": rel, "problem": "fehlt",
                        "text": f"{rel}: keine Siegel-Zeile \"{p.stem} sha256 …\" im Protokoll"})
        elif ist != soll:
            out.append({"datei": rel, "problem": "passt nicht",
                        "text": f"{rel}: die letzte Siegel-Zeile passt nicht zur Datei (Datei oder Zeile geändert)"})
    return out


# ---------- Schritte ----------

def gescheitert(steps) -> list[str]:
    """IDs der Schritte mit outcome "failure" (das Ergebnis vor continue-on-error)."""
    if not isinstance(steps, dict):
        return []
    return sorted(k for k, v in steps.items() if isinstance(v, dict) and v.get("outcome") == "failure")


def zaehlen(alt, fehler: list[str], stamp: str) -> dict:
    """Neue Zählung je Schritt: Läufe in Folge gescheitert (höchstens ALARM_AB, damit die Datei danach still bleibt) und
    seit wann. Ein Schritt, der diesmal nicht gescheitert ist, fällt heraus."""
    alt = alt if isinstance(alt, dict) else {}
    neu = {}
    for sid in fehler:
        a = alt.get(sid) if isinstance(alt.get(sid), dict) else {}
        try:
            bisher = int(a.get("in_folge") or 0)
        except (TypeError, ValueError):
            bisher = 0
        neu[sid] = {"in_folge": min(bisher + 1, ALARM_AB), "seit": a.get("seit") or stamp}
    return neu


def alarm(schritte) -> list[str]:
    if not isinstance(schritte, dict):
        return []
    return sorted(k for k, v in schritte.items() if isinstance(v, dict) and int(v.get("in_folge") or 0) >= ALARM_AB)


def lesen(pfad: Path) -> dict:
    try:
        d = json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else {}
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def zustand_neu(lauf: str, alt: dict, steps, siegel: list[dict] | None, stamp: str) -> dict:
    """Der neue Inhalt der Zustandsdatei. Ohne Uhrzeit des Laufs, damit ein ruhiger Lauf nichts ändert."""
    neu = {"format": 1, "lauf": lauf, "schritte": zaehlen(alt.get("schritte"), gescheitert(steps), stamp)}
    if siegel is not None:
        neu["siegel"] = [s["text"] for s in siegel]
    return neu


# ---------- Melden ----------

def ping(slug: str, ok: bool, key: str | None, text: str = "", senden=None) -> bool:
    """Meldung an healthchecks.io. Ohne Schlüssel passiert nichts. Der Schlüssel wird nie ausgegeben."""
    if not key:
        print(f"Kein HC_PING_KEY: keine Meldung für {slug}")
        return False
    url = f"https://hc-ping.com/{key}/{slug}{'' if ok else '/fail'}?create=1"
    try:
        if senden is not None:
            senden(url, text)
        else:
            req = urllib.request.Request(url, data=text.encode("utf-8")[:9000], method="POST")
            with urllib.request.urlopen(req, timeout=10) as antwort:
                antwort.read()
    except Exception as e:                          # noqa: BLE001 - die Meldung darf den Lauf nie stören
        print(f"Meldung {slug} nicht gesendet ({type(e).__name__})")
        return False
    print(f"Meldung {slug} gesendet ({'gut' if ok else 'ALARM'})")
    return True


def lauf(name: str, root: Path = ROOT, steps=None, key: str | None = None, trocken: bool = False,
         stamp: str | None = None, senden=None) -> dict:
    """Ein Durchgang der Wache für den Lauf `name`. Rückgabe: was geprüft, gespeichert und gemeldet wurde."""
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    pfad = root / ZUSTAND[name]
    alt = lesen(pfad)
    siegel = siegel_pruefen(root) if name == "demo-bots" else None
    neu = zustand_neu(name, alt, steps, siegel, stamp)
    geaendert = neu != alt
    if geaendert and not trocken:
        pfad.write_text(json.dumps(neu, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    out = {"lauf": name, "gescheitert": gescheitert(steps), "zustand": neu, "gespeichert": geaendert and not trocken,
           "siegel": siegel, "alarm": alarm(neu["schritte"])}
    if name != "demo-bots":
        return out
    # Der 15-Minuten-Lauf meldet auch für den 5-Minuten-Lauf, so gibt es je Check nur einen Absender.
    pine = alarm(lesen(root / ZUSTAND["pine5m"]).get("schritte"))
    out["alarm"] = out["alarm"] + [f"pine5m/{s}" for s in pine]
    if trocken:
        return out
    ping(CHECK_SIEGEL, not siegel, key,
         "alle Siegel stimmen" if not siegel else "\n".join(s["text"] for s in siegel), senden)
    ping(CHECK_SCHRITTE, not out["alarm"], key,
         "kein Schritt scheitert wiederholt" if not out["alarm"]
         else f"{ALARM_AB} Läufe in Folge gescheitert: " + ", ".join(out["alarm"]), senden)
    return out


def main(argv: list[str]) -> int:
    try:
        if "--lauf" not in argv:
            probleme = siegel_pruefen()
            print(f"{len(vorab_dateien())} Regeldateien geprüft, {len(probleme)} Probleme")
            for p in probleme:
                print("  " + p["text"])
            return 0
        name = argv[argv.index("--lauf") + 1]
        if name not in ZUSTAND:
            print(f"Unbekannter Lauf {name!r}, bekannt: {sorted(ZUSTAND)}")
            return 0
        try:
            steps = json.loads(os.environ.get("STEPS_JSON") or "{}")
        except ValueError:
            steps = {}
        out = lauf(name, steps=steps, key=os.environ.get("HC_PING_KEY"),
                   trocken=os.environ.get("DRY_RUN") == "true")
        print(json.dumps(out, ensure_ascii=False, indent=1))
    except Exception as e:                          # noqa: BLE001 - die Wache hält nie einen Lauf auf
        print(f"Wache: eigener Fehler ({type(e).__name__}: {e})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
