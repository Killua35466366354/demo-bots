"""Mitnutzer: Bots, die auf einem Demokonto handeln, ohne in journal/konten.json unter "zuordnung" zu stehen.

Projekt-Prüfung vom 11.11.2026, Befund B-04: Die drei Scalper und die Gold-Staffel handeln auf Account 1 (Kirons Wort
vom 10.11.2026 12:16 und 16:37 UTC), die Pine-Bots auf Account 5 und "US500", die Groß-Box auf Account 6, der
Gold-Zonen-Bot auf Account 2 (Kirons Wahl vom 11.11.2026 10:20 UTC), der Gold 4-Std.-Ausbruch auf Account 4 (Kirons
Wahl vom 11.11.2026 19:59 UTC), der 4-Std.-Ausbruch DAX, FTSE, Nikkei auf Account 7 (Kirons Wahl vom 19.11.2026 12:23
UTC, Konto nach dem Namen aus journal/konten.json), Bollinger Krypto umgedreht auf Account 3 (Kirons Wahl vom 20.11.2026
11:53 UTC, ebenso nach dem Namen), das Vorhersage-Modell Indizes auf Account 6 (Kirons Wahl vom 20.11.2026 12:25 UTC,
ebenso nach dem Namen), der Tag nach einem VIX-Sprung auf Account 5 (Kirons Wunsch vom 20.11.2026 12:26 UTC "baue
danach aber weiter aus", ebenso nach dem Namen), Williams %R auf US500 und US100 auf Account 7 (derselbe Wunsch, ebenso
nach dem Namen), der 4-Std.-Ausbruch auf Bitcoin und Ether auf Account 5 (derselbe Wunsch, ebenso nach dem Namen),
das Bündel aus 9 Bots auf "Vortag USDJPY" (Kirons Wahl vom 20.11.2026 16:20 UTC, ebenso nach dem Namen).
Ihr Konto steht als feste Konstante in ihrem Code,
nicht in der Zuordnung, denn dort stehen nur Bots unter der Prüfung nach 15/40 Trades (suche/VORAB_wechsel.yaml).
Account 1 steht deshalb in journal/konten.json weiter unter "frei". Das soll auch so bleiben: "frei" schützt das Konto
vor der Erst-Zuordnung in gold/bot/konten.py. Die Prüfung (suche/demo_pruefung.py) würde ein freies Konto aber an die
nächste bestandene Strategie vergeben. Damit das nie auf einem geteilten Konto passiert, fragt sie hier nach.

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


def konto_nach_name(name: str, konten_daten: dict | None = None) -> str:
    """Die volle Konto-ID des Demokontos mit diesem Namen (für Bots, die ihr Konto nach dem Namen suchen).
    journal/konten.json nennt unter "konten" jedes Konto mit Namen, aber nur mit den letzten vier Stellen (…1234). Die
    volle ID steht dort, wo Konten vergeben werden: "zuordnung", "haupt" und "frei". Gesucht wird darum erst der Name,
    dann die eine volle ID mit diesen vier Endziffern. Leer, wenn es eins von beiden nicht genau einmal gibt.
    Die ID wird nie abgetippt und nie ausgegeben (Befund vom 20.11.2026: mit der gekürzten ID fanden zwei Bots ihr
    Konto beim Broker nicht)."""
    if konten_daten is None:
        from gold.bot import konten
        konten_daten = konten.load()
    k = konten_daten or {}
    kurz = [str(x.get("id") or "") for x in k.get("konten") or [] if x.get("name") == name]
    if len(kurz) != 1:
        return ""
    if not kurz[0].startswith("…"):                # ältere Form: die volle ID steht schon unter "konten"
        return kurz[0] if kurz[0].isdigit() and len(kurz[0]) > 4 else ""
    endung = kurz[0][1:]
    if len(endung) < 4 or not endung.isdigit():
        return ""
    voll = {str(v) for v in (k.get("zuordnung") or {}).values() if v}
    voll |= {str(x) for x in k.get("frei") or [] if x}
    if k.get("haupt"):
        voll.add(str(k["haupt"]))
    treffer = sorted(v for v in voll if v.endswith(endung) and len(v) > len(endung) and v.isdigit())
    return treffer[0] if len(treffer) == 1 else ""


def bots() -> list[dict]:
    """Alle Mitnutzer: bot, konto (volle Konto-ID), konto_name, neu (öffnet neue Trades) und quelle (Datei).

    Ein Fehler beim Lesen eines Bots wird nicht geschluckt: Wer die Liste braucht, muss wissen, dass sie unvollständig
    wäre (suche/demo_pruefung.py vergibt dann gar kein freies Konto)."""
    from gold import ausbruch4h_bot, grossbox_bot, hand_bot, pine5m_bot, zonen_bot
    from suche import buendel_bot, gold_staffel_bot, krypto4h_bot, krypto_bollinger_bot, modell_indizes_bot, scalper_bot
    from suche import vix_sprung_bot, welt4h_bot, williams_bot

    out = [{"bot": b.bot_id, "konto": scalper_bot.KONTO, "konto_name": scalper_bot.KONTO_NAME, "neu": True,
            "quelle": "suche/scalper_bot.py"} for b in scalper_bot.BOTS]
    out.append({"bot": gold_staffel_bot.BOT_ID, "konto": gold_staffel_bot.KONTO,
                "konto_name": gold_staffel_bot.KONTO_NAME, "neu": True, "quelle": "suche/gold_staffel_bot.py"})
    out.append({"bot": grossbox_bot.BOT_ID, "konto": grossbox_bot.KONTO, "konto_name": grossbox_bot.KONTO_NAME,
                "neu": True, "quelle": "gold/grossbox_bot.py"})
    out.append({"bot": zonen_bot.BOT_ID, "konto": zonen_bot.KONTO, "konto_name": zonen_bot.KONTO_NAME,
                "neu": True, "quelle": "gold/zonen_bot.py"})
    out.append({"bot": ausbruch4h_bot.BOT_ID, "konto": ausbruch4h_bot.KONTO,
                "konto_name": ausbruch4h_bot.KONTO_NAME, "neu": True, "quelle": "gold/ausbruch4h_bot.py"})
    out.append({"bot": welt4h_bot.BOT_ID, "konto": welt4h_bot.KONTO, "konto_name": welt4h_bot.KONTO_NAME,
                "neu": True, "quelle": "suche/welt4h_bot.py"})
    out.append({"bot": krypto_bollinger_bot.BOT_ID, "konto": krypto_bollinger_bot.KONTO,
                "konto_name": krypto_bollinger_bot.KONTO_NAME, "neu": True, "quelle": "suche/krypto_bollinger_bot.py"})
    out.append({"bot": modell_indizes_bot.BOT_ID, "konto": modell_indizes_bot.KONTO,
                "konto_name": modell_indizes_bot.KONTO_NAME, "neu": True, "quelle": "suche/modell_indizes_bot.py"})
    out.append({"bot": vix_sprung_bot.BOT_ID, "konto": vix_sprung_bot.KONTO, "konto_name": vix_sprung_bot.KONTO_NAME,
                "neu": True, "quelle": "suche/vix_sprung_bot.py"})
    out.append({"bot": williams_bot.BOT_ID, "konto": williams_bot.KONTO, "konto_name": williams_bot.KONTO_NAME,
                "neu": True, "quelle": "suche/williams_bot.py"})
    out.append({"bot": krypto4h_bot.BOT_ID, "konto": krypto4h_bot.KONTO, "konto_name": krypto4h_bot.KONTO_NAME,
                "neu": True, "quelle": "suche/krypto4h_bot.py"})
    out.append({"bot": buendel_bot.BOT_ID, "konto": buendel_bot.KONTO, "konto_name": buendel_bot.KONTO_NAME,
                "neu": True, "quelle": "suche/buendel_bot.py"})
    # Das Gold-Bündel (Kirons Wahl vom 26.11.2026 "Zwei Bündel auf einem Konto"): derselbe Code, eigene Regeldatei.
    out.append({"bot": buendel_bot.GOLD_ID, "konto": buendel_bot.KONTO, "konto_name": buendel_bot.KONTO_NAME,
                "neu": True, "quelle": "suche/buendel_bot.py"})
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
