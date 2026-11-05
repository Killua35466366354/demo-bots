"""Ein eigenes Capital.com-Demokonto je Bot (Kirons Wunsch vom 03.11.2026: "alles extra accounts").

Capital.com: GET /accounts listet alle Konten des Logins, PUT /session {"accountId"} macht eines davon zum aktiven Konto
der Sitzung (CapitalClient.switch_account). Orders, Positionen und Kontoaktivität gelten immer für das aktive Konto.
Neue Demokonten legt Kiron selbst auf capital.com an; der Code legt nie ein Konto an und löscht nie eines.

journal/konten.json (format 1) schreibt der Lauf der Demo-Bots (suche/demo_bots.py); der London-Bot
(suche/london_bot.py) und der Asien-Bot (suche/asien_bot.py) tragen dort nur ihr eigenes Konto unter
zuordnung["london-eurusd"] bzw. zuordnung["asien-gbpnzd"] ein. Alle anderen lesen nur:
- haupt: das Konto, auf dem der Gold-Bot (C und B) seit dem 31.10.2026 handelt. Beim ersten Lauf ist das das Konto, das
  nach dem Login aktiv ist (das bevorzugte). Danach bleibt es fest, der Gold-Bot wechselt vor jedem Lauf dorthin.
- zuordnung: Bot-ID -> Konto-ID. Ein neues Konto bekommt zuerst der Bot, zu dessen `konto_namen` der Kontoname passt
  (z. B. ein Konto namens "Brent"), sonst der Reihe nach der nächste Bot ohne Konto, in der Reihenfolge der Bots in
  suche/demo_bots.yaml. Nur Konten ohne offene Position werden vergeben, und ein Bot mit offener Position zieht erst
  um, wenn sie zu ist. Einmal vergeben, bleibt die Zuordnung.
- start: Kontostand je Konto, als es zugeordnet wurde (für "seit Start").
- konten: Stand aller Konten aus dem letzten Lauf (Name, Währung, Kontostand, frei, wofür).

Ohne eigenes Konto handelt ein Bot wie bisher auf dem Hauptkonto, außer er hat `eigenes_konto: true` (Gold-Bot 2.0:
auf dem Hauptkonto stünde er mit C und B auf demselben Gold-Markt). Der wartet dann.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATEI = "konten.json"
# Das Demokonto, auf dem der Gold-Bot seit dem 31.10.2026 handelt (Trockenlauf 03.11.: "Account", EUR, 995,17 €). So
# wird das Hauptkonto auch richtig erkannt, wenn Kiron neue Konten anlegt und eines davon zum bevorzugten wird.
HAUPT_ENDUNG = "3150"
AUS = {"DISABLED", "CLOSED", "SUSPENDED", "SUSPENDED_FROM_DEALING"}


def load(journal_dir: Path | None = None) -> dict:
    path = (journal_dir or ROOT / "journal") / DATEI
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        return {}


def save(data: dict, journal_dir: Path | None = None) -> None:
    path = (journal_dir or ROOT / "journal") / DATEI
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")


def wechseln(client, account_id: str | None) -> None:
    """Aktives Konto wechseln, wenn der Client das kann und es nicht schon aktiv ist."""
    if account_id and hasattr(client, "switch_account"):
        client.switch_account(account_id)


def haupt_von(accounts: list[dict], k: dict, aktiv: str | None = None) -> str | None:
    """Das Hauptkonto: aus konten.json, sonst das Konto mit der Endung HAUPT_ENDUNG, sonst das aktive bzw. bevorzugte."""
    if k.get("haupt"):
        return str(k["haupt"])
    ids = [str(a.get("accountId")) for a in accounts if a.get("accountId")]
    hit = [i for i in ids if i.endswith(HAUPT_ENDUNG)]
    if len(hit) == 1:
        return hit[0]
    if aktiv:
        return str(aktiv)
    pref = next((str(a.get("accountId")) for a in accounts if a.get("preferred") and a.get("accountId")), None)
    return pref or (ids[0] if ids else None)


def _id_key(account_id: str):
    return (len(str(account_id)), str(account_id))


def kurz(account_id: str | None) -> str | None:
    """Die letzten 4 Zeichen der Konto-ID, so erkennt Kiron das Konto in der Kontoliste wieder."""
    return None if not account_id else "…" + str(account_id)[-4:]


def zuordnen(alt: dict, accounts: list[dict], bots: list[dict], frei: dict[str, bool], start_id: str | None,
             gesperrt: set[str], stamp: str) -> tuple[dict, list[dict]]:
    """Neue Zuordnung der Konten (reine Funktion, ohne Netz).

    alt: bisheriger Inhalt von konten.json. accounts: Antwort von GET /accounts. bots: alle Bots in ihrer Reihenfolge.
    frei: Konto-ID -> True, wenn das Konto keine offene Position hat (nur für noch nicht vergebene Konten nötig).
    start_id: das nach dem Login aktive Konto. gesperrt: Bots mit offener Position auf einem anderen Konto als dem
    zugeordneten (die ziehen erst nach dem Schließen um). Rückgabe: neuer Inhalt und Ereignisse fürs Log."""
    k = {"format": 1, **alt}
    k["zuordnung"] = dict(alt.get("zuordnung") or {})
    k["start"] = dict(alt.get("start") or {})
    log: list[dict] = []
    by_id = {str(a.get("accountId")): a for a in accounts if a.get("accountId")}
    if not k.get("haupt"):
        h = haupt_von(accounts, k, start_id)
        if h:
            k["haupt"] = h
            log.append({"time": stamp, "event": "hauptkonto", "konto": kurz(h)})
    haupt = k.get("haupt")
    if haupt in by_id and haupt not in k["start"]:
        k["start"][haupt] = (by_id[haupt].get("balance") or {}).get("balance")
    for bot_id, aid in list(k["zuordnung"].items()):
        if aid not in by_id:                       # Konto gibt es nicht mehr
            del k["zuordnung"][bot_id]
            log.append({"time": stamp, "event": "konto weg", "bot": bot_id, "konto": kurz(aid)})
    vergeben = {haupt, *k["zuordnung"].values()}
    frei_konten = [aid for aid in sorted(by_id, key=_id_key)
                   if aid not in vergeben and frei.get(aid) and str(by_id[aid].get("status") or "").upper() not in AUS]
    offen = [b for b in bots if b["id"] not in k["zuordnung"] and b["id"] not in gesperrt]

    def give(bot: dict, aid: str, wie: str) -> None:
        k["zuordnung"][bot["id"]] = aid
        k["start"][aid] = (by_id[aid].get("balance") or {}).get("balance")
        frei_konten.remove(aid)
        log.append({"time": stamp, "event": "konto zugeordnet", "bot": bot["id"], "konto": kurz(aid),
                    "name": by_id[aid].get("accountName"), "wie": wie})

    for bot in list(offen):                        # 1. Name passt
        namen = [str(n).lower() for n in bot.get("konto_namen") or []]
        hit = next((aid for aid in frei_konten
                    if any(n and n in str(by_id[aid].get("accountName") or "").lower() for n in namen)), None)
        if hit:
            give(bot, hit, "Name")
            offen.remove(bot)
    for bot in offen:                              # 2. der Reihe nach
        if not frei_konten:
            break
        give(bot, frei_konten[0], "Reihenfolge")
    wofuer = {aid: bid for bid, aid in k["zuordnung"].items()}
    k["konten"] = [{"id": kurz(aid), "name": a.get("accountName"), "waehrung": a.get("currency"),
                    "balance": (a.get("balance") or {}).get("balance"), "frei": (a.get("balance") or {}).get("available"),
                    "bevorzugt": bool(a.get("preferred")),
                    "fuer": "gold" if aid == haupt else wofuer.get(aid)}
                   for aid, a in sorted(by_id.items(), key=lambda x: _id_key(x[0]))]
    k["stand_utc"] = stamp
    return k, log


def konto_info(k: dict, accounts: list[dict], aid: str | None) -> dict | None:
    """Kurzinfo eines Kontos für Cockpit und Bericht: Name, Währung, Kontostand, Stand beim Zuordnen, Plus/Minus."""
    if not aid:
        return None
    a = next((x for x in accounts if str(x.get("accountId")) == str(aid)), None)
    if a is None:
        return {"id": kurz(aid), "eigen": aid != k.get("haupt")}
    bal = (a.get("balance") or {}).get("balance")
    start = (k.get("start") or {}).get(str(aid))
    return {"id": kurz(aid), "name": a.get("accountName"), "waehrung": a.get("currency"), "eigen": aid != k.get("haupt"),
            "balance": bal, "start": start,
            "seit_start": None if bal is None or start is None else round(float(bal) - float(start), 2)}
