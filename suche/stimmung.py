"""Kunden-Stimmung von Capital.com mitschreiben (Idee 6 aus Kirons Ideen-Buch, 18.11.2026, Kirons Karte "Alles ohne
Regeländerung").

Capital.com zeigt je Markt, wie viel Prozent seiner Kunden gerade long sind (GET /clientsentiment?marketIds=GOLD,US500,
Antwort {"clientSentiments": [{"marketId", "longPositionPercentage", "shortPositionPercentage"}]}). Viele Händler sehen
darin ein Gegen-Signal: Die Mehrheit der Privatkunden liegt oft falsch. Ob das für unsere Bots stimmt, weiß niemand.
Rückwirkend gibt es die Zahlen nicht, darum schreibt dieser Schritt sie ab jetzt mit.

Was er tut: einmal je Lauf der Demo-Bots (alle 15 Minuten) die Stimmung aller Märkte lesen, auf denen ein Bot handelt,
und eine Zeile an journal/stimmung.jsonl anhängen:
    {"zeit": "2026-11-18T12:16Z", "long": {"GOLD": 71.4, "US500": 45.2, ...}, "fehlt": [], "fehler": null}
"long" ist der Anteil der Kunden in Prozent, die long sind. Short ist 100 minus long.

Was er nie tut: keine Order, kein Kontowechsel, kein Bot liest die Datei, keine Regel hängt daran. Ein Fehler hält
nichts auf. Er steht dann in der Zeile unter "fehler", und der Schritt endet trotzdem ohne Fehler (sonst zählte die
Wache ihn als gescheiterten Bot-Schritt und Kiron bekäme eine E-Mail für eine reine Beobachtung).

Später ordnet der Wochen-Check jedem Trade die Stimmung beim Einstieg zu (stimmung_bei). Wann und wie ausgewertet wird,
steht vorab in suche/VORAB_stimmung.yaml (versiegelt, bevor die erste Zeile da war).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT / "journal"
DATEI = "stimmung.jsonl"

# Alle Märkte der Demo-Bots (Stand 18.11.2026): Gold-Bots, Rücksetzer US500, US100 und Dow, Nasdaq Noise-Band, Scalper
# Nasdaq, DAX und Nikkei, Vortag EUR/USD, GBP/USD, GBP/JPY, London GBP/USD, Noise USD/JPY. Kommt ein Bot auf einem
# neuen Markt dazu, nimmt maerkte() ihn aus journal/vergleich.json mit.
MAERKTE = ("GOLD", "US500", "US100", "US30", "DE40", "J225", "EURUSD", "GBPUSD", "GBPJPY", "USDJPY")
EPIC = re.compile(r"^[A-Z0-9_]{2,20}$")
MIN_ABSTAND = timedelta(minutes=10)        # zwei Läufe kurz nacheinander schreiben nur eine Zeile
MAX_ALTER = timedelta(minutes=30)          # stimmung_bei: ältere Zeilen gelten nicht mehr als "beim Einstieg"
PAUSE_EINZELN = 0.15                       # Rückfall auf einzelne Abfragen: unter 10 Anfragen je Sekunde bleiben


def maerkte(journal: Path = JOURNAL) -> list[str]:
    """MAERKTE plus jeder Markt, den journal/vergleich.json für einen Bot nennt (nur Namen in Epic-Form)."""
    out = list(MAERKTE)
    try:
        v = json.loads((journal / "vergleich.json").read_text(encoding="utf-8"))
        for zeile in v.get("rangliste") or []:
            e = str(zeile.get("epic") or zeile.get("markt") or "")
            if EPIC.match(e) and e not in out:
                out.append(e)
    except (OSError, ValueError, AttributeError):
        pass
    return out


def _anteil(eintrag: dict) -> tuple[str | None, float | None]:
    mid = eintrag.get("marketId")
    try:
        return mid, round(float(eintrag["longPositionPercentage"]), 2)
    except (KeyError, TypeError, ValueError):
        return mid, None


def lesen(client, ids: list[str], schlaf=time.sleep) -> tuple[dict[str, float], list[str], str | None]:
    """Stimmung für `ids`: erst eine Abfrage für alle, bei einem Fehler oder fehlenden Märkten je Markt einzeln.
    Gibt (long-Anteile, fehlende Märkte, erster Fehlertext) zurück."""
    long: dict[str, float] = {}
    fehler: str | None = None
    try:
        data = client._get("/clientsentiment", marketIds=",".join(ids))
        for e in (data or {}).get("clientSentiments") or []:
            mid, wert = _anteil(e)
            if mid in ids and wert is not None:
                long[mid] = wert
    except Exception as err:                # noqa: BLE001 - eine Beobachtung darf nie etwas aufhalten
        fehler = str(err)[:200]
    for mid in [i for i in ids if i not in long]:
        schlaf(PAUSE_EINZELN)
        try:
            m, wert = _anteil(client._get(f"/clientsentiment/{mid}") or {})
            if wert is not None and m in (mid, None):
                long[mid] = wert
        except Exception as err:            # noqa: BLE001
            fehler = fehler or str(err)[:200]
    return {i: long[i] for i in ids if i in long}, [i for i in ids if i not in long], fehler


def zeile(stamp: datetime, long: dict[str, float], fehlt: list[str], fehler: str | None) -> dict:
    return {"zeit": stamp.strftime("%Y-%m-%dT%H:%MZ"), "long": long, "fehlt": fehlt, "fehler": fehler}


def _zeit(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        t = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def laden(journal: Path = JOURNAL) -> list[dict]:
    path = journal / DATEI
    if not path.exists():
        return []
    out = []
    for x in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(x))
        except ValueError:
            continue
    return out


def letzte_zeit(journal: Path = JOURNAL) -> datetime | None:
    zeilen = laden(journal)
    return _zeit(zeilen[-1].get("zeit")) if zeilen else None


def stimmung_bei(zeilen: list[dict], epic: str, zeit, max_alter: timedelta = MAX_ALTER) -> float | None:
    """Anteil der Kunden long auf `epic` beim Zeitpunkt `zeit`: die letzte Zeile an oder vor `zeit`, die den Markt hat
    und höchstens `max_alter` alt ist. Sonst None. So kommt nie eine Zahl aus der Zeit nach dem Einstieg hinein."""
    t = zeit if isinstance(zeit, datetime) else _zeit(zeit)
    if t is None:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    best = None
    for z in zeilen:
        zt = _zeit(z.get("zeit"))
        wert = (z.get("long") or {}).get(epic)
        if zt is None or wert is None or zt > t or t - zt > max_alter:
            continue
        if best is None or zt > best[0]:
            best = (zt, float(wert))
    return None if best is None else best[1]


def anhaengen(z: dict, journal: Path = JOURNAL) -> None:
    journal.mkdir(parents=True, exist_ok=True)
    with (journal / DATEI).open("a", encoding="utf-8") as f:
        f.write(json.dumps(z, ensure_ascii=False, separators=(",", ":")) + "\n")


def lauf(client, jetzt: datetime, journal: Path = JOURNAL, trocken: bool = False, schlaf=time.sleep) -> dict | None:
    """Ein Lauf: lesen und anhängen. None, wenn die letzte Zeile jünger als MIN_ABSTAND ist."""
    alt = letzte_zeit(journal)
    if alt is not None and jetzt - alt < MIN_ABSTAND:
        return None
    ids = maerkte(journal)
    try:
        client.login()
        long, fehlt, fehler = lesen(client, ids, schlaf=schlaf)
    except Exception as err:                # noqa: BLE001
        long, fehlt, fehler = {}, ids, str(err)[:200]
    finally:
        try:
            client.logout()
        except Exception:                   # noqa: BLE001
            pass
    z = zeile(jetzt, long, fehlt, fehler)
    if not trocken:
        anhaengen(z, journal)
    return z


def main(argv: list[str]) -> int:
    try:
        from gold.bot.capital import CapitalClient
        from gold.bot.runner import CRED_KEYS, clean_credentials
        creds = clean_credentials({k: os.environ.get(k, "") for k in CRED_KEYS})
        if not all(creds):
            print("Keine Capital.com-Zugangsdaten, Kunden-Stimmung übersprungen")
            return 0
        client = CapitalClient(*creds, environment="demo")      # fest Demo, nur lesen
        z = lauf(client, datetime.now(timezone.utc), trocken="--dry-run" in argv)
        if z is None:
            print("Kunden-Stimmung: letzte Zeile ist jünger als 10 Minuten, nichts Neues")
        else:
            print("Kunden-Stimmung:", json.dumps(z, ensure_ascii=False))
    except Exception as err:                # noqa: BLE001 - nie den Lauf der Bots stören
        print("Kunden-Stimmung nicht gelesen:", str(err)[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
