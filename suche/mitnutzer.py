"""Mitnutzer: Bots, die auf einem Demokonto handeln, ohne in journal/konten.json unter "zuordnung" zu stehen.

Projekt-Prüfung vom 11.11.2026, Befund B-04: Die drei Scalper und die Gold-Staffel handeln auf Account 1 (Kirons Wort
vom 10.11.2026 12:16 und 16:37 UTC), die Pine-Bots auf Account 5 und "US500", die Groß-Box auf Account 6. Ihr Konto
steht als feste Konstante in ihrem Code, nicht in der Zuordnung, denn dort stehen nur Bots unter der Prüfung nach 15/40
Trades (suche/VORAB_wechsel.yaml). Account 1 steht deshalb in journal/konten.json weiter unter "frei". Das soll auch so
bleiben: "frei" schützt das Konto vor der Erst-Zuordnung in gold/bot/konten.py. Die Prüfung (suche/demo_pruefung.py)
würde ein freies Konto aber an die nächste bestandene Strategie vergeben. Damit das nie auf einem geteilten Konto
passiert, fragt sie hier nach.

Diese Datei ist die eine Stelle, an der alle Mitnutzer stehen. Sie liest Konto und Namen aus dem Code der Bots selbst,
es gibt also keine zweite Liste, die veralten kann. Ein neuer Bot mit festem Konto wird hier eingetragen
(tests/test_mitnutzer.py prüft, dass jeder Bot aus dem 5-Minuten-Lauf und die Groß-Box dabei sind).

Liest nur Code-Konstanten, spricht mit keinem Broker und ändert nichts. Keine Regel in einer VORAB-Datei hängt davon ab.

    python -m suche.mitnutzer     # Übersicht (Konten nur mit den letzten 4 Stellen)
"""
from __future__ import annotations

import sys


def _kurz(konto: str | None) -> str | None:
    return None if not konto else "…" + str(konto)[-4:]


def bots() -> list[dict]:
    """Alle Mitnutzer: bot, konto (volle Konto-ID), konto_name, neu (öffnet neue Trades) und quelle (Datei).

    Ein Fehler beim Lesen eines Bots wird nicht geschluckt: Wer die Liste braucht, muss wissen, dass sie unvollständig
    wäre (suche/demo_pruefung.py vergibt dann gar kein freies Konto)."""
    from gold import grossbox_bot, hand_bot, pine5m_bot
    from suche import gold_staffel_bot, scalper_bot

    out = [{"bot": b.bot_id, "konto": scalper_bot.KONTO, "konto_name": scalper_bot.KONTO_NAME, "neu": True,
            "quelle": "suche/scalper_bot.py"} for b in scalper_bot.BOTS]
    out.append({"bot": gold_staffel_bot.BOT_ID, "konto": gold_staffel_bot.KONTO,
                "konto_name": gold_staffel_bot.KONTO_NAME, "neu": True, "quelle": "suche/gold_staffel_bot.py"})
    out.append({"bot": grossbox_bot.BOT_ID, "konto": grossbox_bot.KONTO, "konto_name": grossbox_bot.KONTO_NAME,
                "neu": True, "quelle": "gold/grossbox_bot.py"})
    out += [{"bot": b.bot_id, "konto": b.konto, "konto_name": b.konto_name, "neu": bool(b.neu),
             "quelle": "gold/pine5m_bot.py"} for b in pine5m_bot.BOTS]
    # Der Gold-Hand-Bot öffnet seit dem 10.11.2026 nichts mehr (NEUE_EINSTIEGE), betreut aber offene Trades weiter.
    out.append({"bot": hand_bot.BOT_ID, "konto": hand_bot.KONTO, "konto_name": hand_bot.KONTO_NAME,
                "neu": bool(hand_bot.NEUE_EINSTIEGE), "quelle": "gold/hand_bot.py"})
    return [{**b, "konto": str(b["konto"])} for b in out]


def konten() -> dict[str, list[str]]:
    """Konto-ID -> Bot-IDs der Mitnutzer auf diesem Konto (auch ruhende, solange ihr Lauf noch Trades betreut)."""
    out: dict[str, list[str]] = {}
    for b in bots():
        out.setdefault(b["konto"], []).append(b["bot"] if b["neu"] else f"{b['bot']} (ruht)")
    return {k: sorted(v) for k, v in out.items()}


def aktive() -> list[dict]:
    """Mitnutzer, die neue Trades öffnen (für den Vergleich, suche/vergleich.py)."""
    return [b for b in bots() if b["neu"]]


def main(argv: list[str]) -> int:
    for b in bots():
        print(f"{b['bot']:16s} {b['konto_name']:14s} {_kurz(b['konto'])}  {'handelt' if b['neu'] else 'ruht'}  "
              f"({b['quelle']})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
