"""London-Breakout EUR/USD: Entscheidung für einen Vorwärtstest auf einem Capital.com-DEMOKONTO.

Herkunft: Strategie-Suche Runde 4 (suche/PROTOKOLL.md). Die Strategie "vorbereich" (London-Breakout, Strategy Court und
Trading Steady) hat Runde 4 nicht bestanden. Auf EUR/USD lag sie aber in Auswahl (Gewinnfaktor 1,62) und Siegel (1,65)
im Plus, Dezember bis Februar im Minus (0,88). Das war nicht vorab festgelegt; prüfen lässt es sich nur vorwärts.
Kiron entscheidet, ob und ab wann der Bot auf Demo läuft. Nie echtes Geld.

Regeln (wie Runde 4, Variante mit Marktorder, damit ein Bot mit den vorhandenen Order-Funktionen handeln kann):
- Bereich: alle fertigen 15-Minuten-Kerzen von 0:00 bis 8:00 Uhr London (mindestens 16 Kerzen).
- Ab 8:00 Uhr London: Die erste fertige Kerze, deren Bid-Hoch über dem Bereichshoch (Bid-Tief unter dem Bereichstief)
  liegt, gibt die Richtung. Durchbricht eine Kerze beide Seiten, gibt es an dem Tag keinen Trade.
- Einstieg sofort per Marktorder (= Eröffnung der Kerze nach dem Ausbruch), nur wenn die Ausbruchskerze spätestens um
  16:15 Uhr London beginnt und nur in dem Lauf direkt nach dieser Kerze. Ein verpasster Ausbruch wird nicht nachgeholt.
- Stop: andere Seite des Bereichs. Ziel: Ausbruchsmarke plus eine Bereichsbreite. Beides als Kursniveau, beim Broker als
  Abstand vom tatsächlichen Einstieg.
- Raus spätestens um 17:00 Uhr London. Höchstens ein Trade pro Tag, Montag bis Freitag.

Kiron hat am 04.11.2026 entschieden: sofort, auf einem eigenen neuen Demokonto. Vorwärtstest vorab festgelegt in
suche/VORAB_london.yaml (Urteil nach 60 Trades).

    python -m suche.london_bot             # ein Lauf (im Workflow der Demo-Bots, Mo-Fr alle 15 Minuten)
    python -m suche.london_bot --dry-run   # nur rechnen und ausgeben, keine Order, nichts speichern

Konto: nie das Hauptkonto (Gold-Bot) und nie ein Konto eines anderen Demo-Bots. Der Bot nimmt das Konto, dessen Name
"London" oder "EURUSD" enthält, sonst das neueste freie Konto ohne offene Position (nie eines mit "Asien" oder "GBPNZD"
im Namen, das gehört dem Asien-Bot), und trägt es in journal/konten.json unter zuordnung["london-eurusd"] ein. Danach bleibt es fest. Am Ende jedes Laufs ist wieder das Hauptkonto aktiv.
Positionen, die der Bot nicht selbst geöffnet hat, fasst er nie an.

Dateien: journal/london-bot/state.json, trades.jsonl (ein Trade je Zeile), log.jsonl, journal/london-bot.json (Stand für
das Cockpit). Entscheidung ohne Netz und Tests: tests/test_london_bot.py.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

TZ = "Europe/London"
EPIC = "EURUSD"
BEREICH_BIS = 8 * 60          # Minuten nach Mitternacht London
LETZTE_AUSBRUCHSKERZE = 16 * 60 + 15
SCHLUSS = 17 * 60
MIN_KERZEN = 16


def _lokal(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    idx = index if index.tz is not None else index.tz_localize("UTC")
    return idx.tz_convert(TZ)


def bereich(bars: pd.DataFrame, tag) -> tuple[float, float, int] | None:
    """Hoch, Tief und Zahl der Kerzen von 0:00 bis 8:00 London am Tag `tag` (date). bars: fertige Bid-Kerzen, UTC."""
    lok = _lokal(bars.index)
    tod = lok.hour * 60 + lok.minute
    drin = (lok.date == tag) & (tod < BEREICH_BIS)
    if drin.sum() < MIN_KERZEN:
        return None
    b = bars[drin]
    return float(b["high"].max()), float(b["low"].min()), int(drin.sum())


def entscheide(bars: pd.DataFrame, now_utc: pd.Timestamp, sb: dict) -> dict:
    """Was der Bot jetzt tun soll. bars: nur FERTIGE 15-Minuten-Bid-Kerzen (Index = Kerzenbeginn UTC, ohne Zeitzone).
    sb: Zustand des Bots ({"open": {...}} bei offener Position, "tag_erledigt": "YYYY-MM-DD").
    Rückgabe: {"action": "none" | "open" | "close", "why": [...], ...}; bei "open" side, marke, stop_level, ziel_level."""
    now = pd.Timestamp(now_utc)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    jetzt = now.tz_convert(TZ)
    tag = jetzt.date()
    minute = jetzt.hour * 60 + jetzt.minute
    out = {"action": "none", "why": [], "tag": str(tag)}
    if sb.get("open"):
        if minute >= SCHLUSS or str(tag) != str(sb["open"].get("tag")):
            out.update(action="close", reason="zeit", why=["17:00 Uhr London: Tagesende"])
        return out
    if jetzt.weekday() >= 5:
        out["why"].append("Wochenende")
        return out
    if sb.get("tag_erledigt") == str(tag):
        out["why"].append("heute schon erledigt")
        return out
    if minute < BEREICH_BIS or minute >= SCHLUSS:
        out["why"].append("außerhalb 8:00 bis 17:00 Uhr London")
        return out
    b = bereich(bars, tag)
    if b is None:
        out.update(erledigt=True, why=["Bereich 0 bis 8 Uhr zu kurz (weniger als 16 Kerzen)"])
        return out
    oben, unten, _ = b
    lok = _lokal(bars.index)
    tod = lok.hour * 60 + lok.minute
    sitzung = bars[(lok.date == tag) & (tod >= BEREICH_BIS) & (tod < SCHLUSS)]
    if sitzung.empty:
        return out
    for t, k in sitzung.iterrows():
        hoch, tief = k["high"] > oben, k["low"] < unten
        if not (hoch or tief):
            continue
        t_lok = _lokal(pd.DatetimeIndex([t]))[0]
        beginn = t_lok.hour * 60 + t_lok.minute
        if hoch and tief:
            out.update(erledigt=True, why=["eine Kerze durchbricht beide Seiten, heute kein Trade"])
            return out
        if t != sitzung.index[-1]:
            out.update(erledigt=True, why=[f"Ausbruch um {t_lok:%H:%M} verpasst, wird nicht nachgeholt"])
            return out
        if beginn > LETZTE_AUSBRUCHSKERZE:
            out.update(erledigt=True, why=["Ausbruch erst nach 16:15 Uhr, zu spät"])
            return out
        side = 1 if hoch else -1
        marke = oben if side > 0 else unten
        out.update(action="open", side=side, signal_bar=str(t), marke=marke, oben=oben, unten=unten,
                   stop_level=unten if side > 0 else oben, ziel_level=marke + side * (oben - unten),
                   why=[f"Ausbruch {'über' if side > 0 else 'unter'} den Bereich {unten:.5f} bis {oben:.5f}"])
        return out
    out["why"].append("noch kein Ausbruch")
    return out


def abstaende(d: dict, bid: float, offer: float) -> tuple[float, float] | None:
    """Stop- und Zielabstand vom tatsächlichen Einstieg (Long kauft zum Ask, Short verkauft zum Bid). None, wenn der Kurs
    schon hinter Stop oder Ziel liegt."""
    side = d["side"]
    ein = offer if side > 0 else bid
    stop = (ein - d["stop_level"]) * side
    ziel = (d["ziel_level"] - ein) * side
    if stop <= 0 or ziel <= 0:
        return None
    return stop, ziel


# ---------- Lauf mit dem Broker (nur Demokonto) ----------
#
# Derselbe Lauf dient mehreren Tages-Bots mit eigenem Konto (London-Breakout EUR/USD, Asien-ORB GBP/NZD in
# suche/asien_bot.py). Was je Bot anders ist, steht in einer BotDef.

ROOT = Path(__file__).resolve().parents[1]
MAX_RISIKO_EUR = 10
GRUND = {"SL": "Stop beim Broker", "TP": "Ziel beim Broker", "USER": "von Hand geschlossen",
         "CLOSE_OUT": "Zwangsschließung (zu wenig Margin)"}


@dataclass(frozen=True)
class BotDef:
    bot_id: str
    epic: str
    konto_namen: tuple            # Kontoname mit einem dieser Wörter wird bevorzugt
    fremde_namen: tuple           # Kontoname mit einem dieser Wörter gehört einem anderen Tages-Bot: nie nehmen
    entscheide: Callable
    abstaende: Callable
    tag_von: Callable             # Handelstag (Text) eines Zeitpunkts, für übernommene Positionen
    jdir: Path
    cockpit: Path
    regel_text: str
    zeit_grund: str               # Text für den Ausstieg zur Zeit
    kerzen: Callable | None = None   # eigene Kerzen (client, jetzt, zustand) -> Bid-Kerzen; sonst 15 Minuten wie hier
    warte_text: str = "wartet auf Ausbruch"
    nur_mit_namen: bool = False   # True: nur ein Konto mit passendem Namen, nie das neueste freie als Ersatz


def _london_tag(ts: pd.Timestamp) -> str:
    return str(pd.Timestamp(ts).tz_localize("UTC").tz_convert(TZ).date())


BOT_ID = "london-eurusd"
KONTO_NAMEN = ("london", "eurusd", "eur/usd")
JDIR = ROOT / "journal" / "london-bot"
COCKPIT = ROOT / "journal" / "london-bot.json"
REGEL_TEXT = ("London-Breakout EUR/USD: Bereich 0 bis 8 Uhr London, Ausbruch per Marktorder, Stop andere Seite, Ziel "
              "eine Bereichsbreite, raus um 17 Uhr London, kleinste Größe. Vorwärtstest seit 04.11.2026, Urteil nach "
              "60 Trades (Gewinnfaktor ab 1,2 und Summe im Plus). Runde 4: 0,88 / 1,62 / 1,65 in drei Zeiträumen, "
              "nicht vorab festgelegt.")
LONDON = BotDef(BOT_ID, EPIC, KONTO_NAMEN, ("asien", "asia", "gbpnzd", "gbp/nzd"), entscheide, abstaende, _london_tag,
                JDIR, COCKPIT, REGEL_TEXT, "17 Uhr London")


KOMBI = ROOT / "suche" / "kombi.yaml"


def kombi_gruppe(bot_id: str) -> dict | None:
    """Die Gruppe aus suche/kombi.yaml, in der der Bot mit anderen Strategien ein Konto teilt (Kirons Wunsch vom
    04.11.2026: die besten 3 auf einem Demokonto), sonst None."""
    import yaml
    try:
        cfg = yaml.safe_load(KOMBI.read_text(encoding="utf-8")) or {}
    except OSError:
        return None
    for gid, g in (cfg.get("kombi") or {}).items():
        if bot_id in (g.get("bots") or []):
            return {"id": gid, **g}
    return None


def finde_konto(accounts: list[dict], kont: dict, haupt: str | None, st: dict, frei,
                bot: BotDef | None = None) -> str | None:
    """Das Konto des Bots (reine Auswahl; `frei(aid)` sagt, ob ein Konto keine offene Position hat)."""
    from gold.bot.konten import AUS, _id_key
    bot = bot or LONDON
    ids = {str(a.get("accountId")): a for a in accounts if a.get("accountId")}
    zu = kont.get("zuordnung") or {}
    # belegt: Konten anderer Bots und freie Konten aus der Prüfung (suche/demo_pruefung.py vergibt sie)
    belegt = {str(haupt), *(str(v) for k, v in zu.items() if k != bot.bot_id), *(str(x) for x in kont.get("frei") or [])}
    for aid in (zu.get(bot.bot_id), st.get("konto_id")):
        if aid and str(aid) in ids and str(aid) != str(haupt) and (aid == zu.get(bot.bot_id) or str(aid) not in belegt):
            return str(aid)

    def name_hat(aid, woerter):
        return any(n in str(ids[aid].get("accountName") or "").lower() for n in woerter)

    kand = [aid for aid in ids if aid not in belegt and str(ids[aid].get("status") or "").upper() not in AUS
            and not name_hat(aid, bot.fremde_namen)]
    name = [aid for aid in kand if name_hat(aid, bot.konto_namen)]
    ersatz = [] if bot.nur_mit_namen else sorted(kand, key=_id_key, reverse=True)
    for aid in sorted(name, key=_id_key, reverse=True) + ersatz:
        if frei(aid):
            return aid
    return None


def buche(op: dict, exit_level: float | None, now: pd.Timestamp, grund: str, eur: float | None,
          bot: BotDef | None = None) -> dict:
    """Ein abgeschlossener Trade. Rendite in Prozent vom Kurs (wie im Backtest), dazu R und Euro."""
    bot = bot or LONDON
    side, entry = int(op["side"]), op.get("entry")
    geschaetzt = exit_level is None
    if geschaetzt and entry is not None:
        exit_level = entry + (side * (op.get("tp_dist") or 0) if grund == "TP" else -side * (op.get("stop_dist") or 0))
    entry = None if entry is None else float(entry)
    pct = None if entry is None else (float(exit_level) / entry - 1) * side * 100
    r = None if entry is None or not op.get("stop_dist") else side * (float(exit_level) - entry) / op["stop_dist"]
    pnl = None if entry is None else side * (float(exit_level) - entry) * float(op["size"]) * float(op.get("lot", 1))
    eur = eur or op.get("eur_rate")
    return {"bot": bot.bot_id, "epic": bot.epic, "side": "long" if side > 0 else "short", "dealId": op.get("dealId"),
            "tag": op.get("tag"), "signal_bar": op.get("signal_bar"), "size": op["size"], "entry": entry,
            "exit": None if exit_level is None else round(float(exit_level), 6), "stop_dist": op["stop_dist"],
            "tp_dist": op.get("tp_dist"), "oben": op.get("oben"), "unten": op.get("unten"),
            "opened_utc": op.get("opened_utc"), "closed_utc": now.isoformat(),
            "reason": bot.zeit_grund if grund == "zeit" else GRUND.get(grund, grund),
            "pct": None if pct is None else round(pct, 4), "r": None if r is None else round(r, 3),
            "pnl": None if pnl is None else round(pnl, 4), "waehrung": op.get("currency"),
            "pnl_eur": None if pnl is None or not eur else round(pnl / eur, 2), "geschaetzt": geschaetzt,
            "konto": op.get("konto_kurz")}


def uebernehmen(p: dict, q, konto_kurz: str | None, bot: BotDef | None = None) -> dict:
    """Eine Position im Markt des Bots auf dem eigenen Konto, die nicht im Zustand steht (etwa weil das Journal nach
    einem Fehler nicht gesichert wurde). Das Konto gehört nur diesem Bot, also ist es seine; sie wird wie eine eigene
    geführt und spätestens zum Sitzungsende geschlossen."""
    bot = bot or LONDON
    pos = p["position"]
    side = 1 if str(pos.get("direction")).upper() == "BUY" else -1
    lvl = float(pos.get("level") or 0)
    opened = pd.Timestamp(pos.get("createdDateUTC") or pd.Timestamp.now(tz="UTC")).tz_localize(None)
    tag = bot.tag_von(opened)
    stop, ziel = pos.get("stopLevel"), pos.get("profitLevel")
    return {"dealId": pos.get("dealId"), "side": side, "tag": tag, "signal_bar": None, "entry": lvl or None,
            "stop_dist": abs(lvl - float(stop)) if stop else 0.0, "tp_dist": abs(float(ziel) - lvl) if ziel else None,
            "size": pos.get("size"), "lot": q.lot, "currency": q.currency, "eur_rate": q.eur_rate,
            "opened_utc": str(opened), "konto_kurz": konto_kurz, "uebernommen": True}


def zusammenfassung(trades: list[dict]) -> dict:
    p = np.array([t["pct"] for t in trades if t.get("pct") is not None], float)
    g, v = p[p > 0].sum(), -p[p < 0].sum()
    return {"trades": int(len(p)), "treffer_pct": round(100 * float((p > 0).mean()), 1) if len(p) else None,
            "pf": (round(float(g / v), 3) if v > 0 else None) if len(p) else None,
            "summe_pct": round(float(p.sum()), 3) if len(p) else 0.0,
            "pnl_eur": round(float(sum(t.get("pnl_eur") or 0 for t in trades)), 2)}


def kombi_umzug(kont: dict, bot: BotDef, gruppe: dict, st: dict, stamp: str, log: list, eigene_pos) -> bool:
    """Ein Bot einer Kombi-Gruppe zieht ins Konto des Ankers, sobald er keine Position mehr hat; sein altes Konto wird
    frei (kont["frei"]). Ohne eigenes Konto kommt er gleich dazu. Rückgabe True: er steht noch im alten Konto (eine
    Position läuft dort zu Ende) und öffnet nichts Neues."""
    from gold.bot import konten
    zu = kont.setdefault("zuordnung", {})
    ziel = zu.get(gruppe["anker"])
    if not ziel or bot.bot_id == gruppe["anker"] or zu.get(bot.bot_id) == ziel:
        return False
    alt = zu.get(bot.bot_id)
    if alt is None:
        zu[bot.bot_id] = ziel
        log.append({"time": stamp, "event": "ins gemeinsame Konto", "konto": konten.kurz(ziel), "kombi": gruppe["id"]})
        return False
    if st.get("open") or eigene_pos(alt):
        return True
    zu[bot.bot_id] = ziel
    if alt not in zu.values() and alt not in (kont.get("frei") or []):
        kont.setdefault("frei", []).append(alt)
    kont.setdefault("uebergaben", []).append({"zeit": stamp, "konto": konten.kurz(alt), "konto_id": alt, "von": bot.bot_id,
                                              "an": None, "kombi": gruppe["id"]})
    for e in kont.get("konten") or []:
        if e.get("id") == konten.kurz(alt):
            e["fuer"] = None
    st.pop("start_kontostand", None)
    log.append({"time": stamp, "event": "ins gemeinsame Konto umgezogen", "von": konten.kurz(alt),
                "nach": konten.kurz(ziel), "kombi": gruppe["id"]})
    return False


def run(client, state: dict, kont: dict, now: datetime, send_orders: bool = True,
        bot: BotDef | None = None) -> tuple[dict, list, list]:
    """Ein Lauf. Gibt neuen Zustand, neue Trades und Ereignisse zurück; `kont` (journal/konten.json) bekommt die
    Zuordnung des Bots."""
    bot = bot or LONDON
    from gold.bot import konten
    from suche.demo_bots import (_abl_text, broker_exit, eur_rate, frame, only_closed, open_market, own_position,
                                 quote_from_market, size_for, uebergeben, utc_naive)
    nowts = utc_naive(now)
    stamp = nowts.isoformat()
    st, log, neu = dict(state), [], []
    client.login()
    accounts = client.accounts()
    haupt = konten.haupt_von(accounts, kont, getattr(client, "account_id", None))
    pos_cache: dict = {}

    def positions_of(aid):
        konten.wechseln(client, aid)
        if aid not in pos_cache:
            pos_cache[aid] = client.positions()
        return pos_cache[aid]

    # abgelöst (Prüfung nach 15/40 Demo-Trades, suche/demo_pruefung.py): nichts Neues, Position zu Ende, dann Konto weg
    abgeloest = (kont.get("abgeloest") or {}).get(bot.bot_id)
    # gemeinsames Konto (suche/kombi.yaml): Positionen gehören dem Bot, dessen Deal-ID in kont["deals"] steht
    gruppe = kombi_gruppe(bot.bot_id)
    deals = kont.setdefault("deals", {}) if gruppe else {}
    umzug = False
    try:
        if abgeloest and not (kont.get("zuordnung") or {}).get(bot.bot_id):
            st.update(status=_abl_text(abgeloest), konto_id=None, konto=None, konto_name=None, kontostand=None)
            return st, neu, log
        if gruppe and not abgeloest:
            umzug = kombi_umzug(kont, bot, gruppe, st, stamp, log, lambda a: own_position(positions_of(a), bot.epic))
        aid = finde_konto(accounts, kont, haupt, st, lambda a: not positions_of(a), bot)
        if aid is None:
            st["status"] = (f"wartet auf ein eigenes Demokonto mit „{bot.konto_namen[0].title()}“ im Namen"
                            if bot.nur_mit_namen else "wartet auf ein eigenes neues Demokonto")
            return st, neu, log
        if (kont.get("zuordnung") or {}).get(bot.bot_id) != aid:
            kont.setdefault("zuordnung", {})[bot.bot_id] = aid
            log.append({"time": stamp, "event": "konto zugeordnet", "konto": konten.kurz(aid)})
        acc = next(a for a in accounts if str(a.get("accountId")) == aid)
        bal = acc.get("balance") or {}
        st.update(konto_id=aid, konto=konten.kurz(aid), konto_name=acc.get("accountName"),
                  kontostand=bal.get("balance"), waehrung=acc.get("currency"))
        st.setdefault("start_utc", stamp)
        st.setdefault("start_kontostand", bal.get("balance"))
        positions = positions_of(aid)
        mine = own_position(positions, bot.epic)
        if gruppe:                                     # Positionen der anderen Strategien im Konto gehören ihnen
            mine = [p for p in mine if deals.get(str(p["position"].get("dealId"))) in (None, bot.bot_id)]
        op = st.get("open")
        market = client.market(bot.epic)
        q = quote_from_market(market, None)
        q.eur_rate = eur_rate(client, q.currency, {})
        if op and op.get("dealId") not in {p["position"].get("dealId") for p in mine}:
            level, source = broker_exit(client, op, now)
            tr = buche(op, level, nowts, source or "SL", q.eur_rate, bot)
            neu.append(tr)
            log.append({"time": stamp, "event": "vom Broker geschlossen", **{k: tr[k] for k in ("exit", "pct", "reason")}})
            deals.pop(str(op.get("dealId")), None)
            st["open"], op = None, None
        if not op and len(mine) == 1:                  # eigene Position, aber Zustand verloren: übernehmen
            op = st["open"] = uebernehmen(mine[0], q, konten.kurz(aid), bot)
            if gruppe:
                deals[str(op["dealId"])] = bot.bot_id
            log.append({"time": stamp, "event": "Position übernommen", "dealId": op["dealId"]})
        fremd = [p for p in mine if not op or p["position"].get("dealId") != op.get("dealId")]
        if fremd:
            st["status"] = f"fremde {bot.epic}-Position auf dem Konto, Bot wartet"
            return st, neu, log
        if bot.kerzen is not None:
            bars = bot.kerzen(client, nowts, st)
        else:
            bars, _ = only_closed(*frame(client.prices(bot.epic, "MINUTE_15", 200)), nowts, "15min")
        d = bot.entscheide(bars, nowts, {"open": op, "tag_erledigt": st.get("tag_erledigt")})
        st["letzte_entscheidung"] = {"zeit": stamp, "action": d["action"], "why": d["why"],
                                     "bar": str(bars.index[-1]) if len(bars) else None}
        if d.get("erledigt"):
            st["tag_erledigt"] = d["tag"]
        if d["action"] == "close" and op:
            if send_orders:
                res = client.close_position(op["dealId"])
                if res.get("dealStatus") == "ACCEPTED":
                    tr = buche(op, res.get("level"), nowts, d.get("reason", "zeit"), q.eur_rate, bot)
                    neu.append(tr)
                    deals.pop(str(op.get("dealId")), None)
                    st["open"] = None
                    log.append({"time": stamp, "event": "geschlossen", **{k: tr[k] for k in ("exit", "pct", "reason")}})
                else:
                    log.append({"time": stamp, "event": "schließen abgelehnt", "res": str(res)[:200]})
            else:
                log.append({"time": stamp, "event": "würde schließen (Trockenlauf)", "why": d["why"]})
        elif d["action"] == "open" and not abgeloest and not umzug:
            st["tag_erledigt"] = d["tag"]                  # ein Versuch pro Tag, auch wenn er nicht klappt
            ab = bot.abstaende(d, q.bid, q.offer)
            size = size_for(q)
            ev = {"time": stamp, "event": "", "side": "long" if d["side"] > 0 else "short", "bar": d["signal_bar"],
                  "oben": d.get("oben"), "unten": d.get("unten"), "size": size}
            why = []
            if not q.tradeable:
                why.append("Markt gerade nicht handelbar")
            if ab is None:
                why.append("Kurs liegt schon hinter Stop oder Ziel")
            else:
                if min(x for x in ab if x is not None) < q.min_dist:
                    why.append("Stop oder Ziel näher als der Mindestabstand des Brokers")
                if q.eur_rate:
                    risiko = ab[0] * size * q.lot / q.eur_rate
                    ev["risiko_eur"] = round(risiko, 2)
                    if risiko > MAX_RISIKO_EUR:
                        why.append(f"Risiko {risiko:.2f} EUR, mehr als {MAX_RISIKO_EUR} EUR")
                else:
                    why.append(f"kein Umrechnungskurs EUR/{q.currency}")
            if gruppe:                                 # Konto ohne Hedging: eine Gegenposition schlösse die andere
                eigene = {p["position"].get("dealId") for p in mine}
                richtung = "BUY" if d["side"] > 0 else "SELL"
                if [p for p in own_position(positions_of(aid), bot.epic) if p["position"].get("dealId") not in eigene
                        and p["position"].get("direction") not in (None, richtung)]:
                    why.append("Gegenposition einer anderen Strategie auf demselben Markt im gemeinsamen Konto")
            if why:
                log.append({**ev, "event": "Signal nicht genutzt", "why": why})
            elif not send_orders:
                log.append({**ev, "event": "würde öffnen (Trockenlauf)", "stop_dist": ab[0], "tp_dist": ab[1]})
            else:
                order = {"size": size, "stop_dist": round(ab[0], q.decimals),
                         "tp_dist": None if ab[1] is None else round(ab[1], q.decimals)}
                vorher = {p["position"].get("dealId") for p in own_position(positions_of(aid), bot.epic)}
                res = open_market(client, bot.epic, d["side"], order)
                pos_cache.pop(aid, None)
                if res.get("dealStatus") != "ACCEPTED":
                    log.append({**ev, "event": "Order abgelehnt", "res": str(res)[:300]})
                else:                                  # die neue Position, nicht die einer anderen Strategie
                    alle = own_position(positions_of(aid), bot.epic)
                    nach = [p for p in alle if p["position"].get("dealId") not in vorher] or ([] if gruppe else alle)
                    pos = nach[0]["position"] if nach else {}
                    st["open"] = {"dealId": pos.get("dealId") or res.get("dealId")
                                  or (res.get("affectedDeals") or [{}])[0].get("dealId"),
                                  "side": d["side"], "tag": d["tag"], "signal_bar": d["signal_bar"],
                                  "entry": pos.get("level") or res.get("level"), "oben": d.get("oben"),
                                  "unten": d.get("unten"),
                                  "stop_dist": order["stop_dist"], "tp_dist": order["tp_dist"], "size": size,
                                  "lot": q.lot, "currency": q.currency, "eur_rate": q.eur_rate,
                                  "opened_utc": pos.get("createdDateUTC") or stamp, "konto_kurz": konten.kurz(aid)}
                    if gruppe and st["open"]["dealId"]:
                        deals[str(st["open"]["dealId"])] = bot.bot_id
                    log.append({**ev, "event": "eröffnet", "entry": st["open"]["entry"], "dealId": st["open"]["dealId"]})
        st["status"] = "Position offen" if st.get("open") else bot.warte_text
        if abgeloest and not st.get("open"):
            pos_cache.pop(aid, None)
            geteilt = any(k != bot.bot_id and str(v) == str(aid) for k, v in (kont.get("zuordnung") or {}).items())
            leer = (not [p for p in own_position(positions_of(aid), bot.epic)
                         if deals.get(str(p["position"].get("dealId"))) in (None, bot.bot_id)]
                    if geteilt else not positions_of(aid))
            if send_orders and leer and geteilt:          # gemeinsames Konto: nur dieser Bot geht, das Konto bleibt
                kont["zuordnung"].pop(bot.bot_id, None)
                log.append({"time": stamp, "event": "aus dem gemeinsamen Konto genommen", "konto": konten.kurz(aid)})
                st.update(konto_id=None, konto=None, konto_name=None, kontostand=None)
                st["status"] = _abl_text({"an": None}).replace("Konto wird frei", "nicht mehr im gemeinsamen Konto")
            elif send_orders and leer:                    # Konto leer: an den Nachfolger oder frei
                log += uebergeben(kont, {bot.bot_id: abgeloest}, set(), accounts, stamp)
                st.update(konto_id=None, konto=None, konto_name=None, kontostand=None)
                st["status"] = _abl_text(abgeloest)
            else:
                st["status"] = _abl_text(abgeloest) + "; wartet, bis im Konto nichts mehr offen ist"
        elif abgeloest:
            st["status"] = _abl_text(abgeloest) + "; Position läuft noch zu Ende"
        elif umzug:
            st["status"] += "; zieht nach diesem Trade ins gemeinsame Konto"
        if st.get("open"):
            p = own_position(positions_of(aid), bot.epic, {st["open"].get("dealId")})
            st["position"] = ({"upl": p[0]["position"].get("upl"), "stop": p[0]["position"].get("stopLevel"),
                               "ziel": p[0]["position"].get("profitLevel")} if p else None)
        else:
            st["position"] = None
    except Exception as err:            # noqa: BLE001 - der Lauf darf nie die anderen Bots stören
        st["status"] = f"Fehler: {str(err)[:160]}"
        log.append({"time": stamp, "event": "fehler", "why": str(err)[:300]})
    finally:
        try:                            # Ordnung: am Ende ist wieder das Hauptkonto aktiv (der Gold-Bot erwartet es)
            konten.wechseln(client, haupt)
        except Exception as err:        # noqa: BLE001
            log.append({"time": stamp, "event": "zurück aufs Hauptkonto fehlgeschlagen", "why": str(err)[:160]})
        st["stand_utc"] = stamp
    return st, neu, log


def _stand(kont: dict) -> str:
    """Vergleichsstand von journal/konten.json: gespeichert wird, sobald ein Lauf etwas daran geändert hat."""
    return json.dumps(kont, sort_keys=True, ensure_ascii=False, default=str)


def main(argv: list[str], bot: BotDef | None = None) -> int:
    from gold.bot import konten
    from gold.bot.capital import CapitalClient
    from gold.bot.runner import CRED_KEYS, clean_credentials

    bot = bot or LONDON
    creds = clean_credentials({k: os.environ.get(k, "") for k in CRED_KEYS})
    if not all(creds):
        print(f"Keine Capital.com-Zugangsdaten, {bot.bot_id} übersprungen")
        return 0
    dry = "--dry-run" in argv
    bot.jdir.mkdir(parents=True, exist_ok=True)
    path = bot.jdir / "state.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    kont = konten.load()
    kont_vorher = _stand(kont)
    client = CapitalClient(*creds, environment="demo")      # fest Demo: Live gibt es hier nicht
    try:
        st, neu, log = run(client, state, kont, datetime.now(timezone.utc), send_orders=not dry, bot=bot)
    finally:
        try:
            client.logout()
        except Exception:               # noqa: BLE001
            pass
    if dry:                             # Trockenlauf: nichts speichern
        print(json.dumps({"trockenlauf": True, "status": st.get("status"), "konto": st.get("konto"),
                          "entscheidung": st.get("letzte_entscheidung"), "log": log}, ensure_ascii=False,
                         indent=1, default=str))
        return 0
    tpath = bot.jdir / "trades.jsonl"
    if neu:
        with open(tpath, "a", encoding="utf-8") as fh:
            for t in neu:
                fh.write(json.dumps(t, ensure_ascii=False, default=str) + "\n")
    if log:
        with open(bot.jdir / "log.jsonl", "a", encoding="utf-8") as fh:
            for e in log:
                fh.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
    if _stand(kont) != kont_vorher:     # auch wenn der Bot sein Konto gerade abgegeben hat (frei, Nachfolger)
        konten.save(kont)
    path.write_text(json.dumps(st, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    trades = [json.loads(x) for x in tpath.read_text(encoding="utf-8").splitlines() if x.strip()] if tpath.exists() else []
    cockpit = {"stand_utc": st.get("stand_utc"), "status": st.get("status"), "regel": bot.regel_text,
               "bot": bot.bot_id, "epic": bot.epic, "konto": st.get("konto"), "konto_name": st.get("konto_name"),
               "kontostand": st.get("kontostand"), "start_kontostand": st.get("start_kontostand"),
               "start_utc": st.get("start_utc"), "offen": st.get("open"), "position": st.get("position"),
               "letzte_entscheidung": st.get("letzte_entscheidung"), "zusammenfassung": zusammenfassung(trades),
               "letzte_trades": trades[-10:]}
    bot.cockpit.write_text(json.dumps(cockpit, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"status": st.get("status"), "neue_trades": len(neu), "log": log}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
