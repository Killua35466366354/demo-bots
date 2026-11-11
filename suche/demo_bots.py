"""Demo-Bots der Strategie-Suche Runde 3: die besten Varianten aus dem Backtest handeln 4 Handelstage echt auf dem
Capital.com-DEMOKONTO (Kirons Wunsch vom 02.11.2026). Nie Live-Geld: Der Client ist fest auf "demo".

    python -m suche.demo_bots             # ein Lauf: Kerzen holen, entscheiden, Orders auf dem Demokonto
    python -m suche.demo_bots --dry-run   # nur rechnen und ins Log schreiben, keine Order

Welche Bots laufen, steht in suche/demo_bots.yaml (aus dem Backtest, Rangliste nach Gewinnfaktor). Jeder Bot rechnet
mit genau dem Code des Backtests (suche.runde3.prepare und gold.v2.fuehrung.manage): Pine C und B unverändert, die
Logik "gold" (Stop 1 x ATR, Ausstieg auf eigenes Signal) oder "gold2" (Gold-Bot 2.0 mit Richtung, News, Ziel 0,5 ATR,
höchstens 8 Kerzen, Stop 1,5 ATR).

Ablauf je Bot und Lauf:
- Nur wenn eine neue Kerze seines Zeitrahmens fertig ist. Signale zählen nur auf der gerade fertigen Kerze; ein
  verpasstes Signal wird nicht nachgeholt (wie beim Gold-Bot).
- Offene Position: Stop (und bei 2.0 das Ziel) liegen beim Broker. Die übrigen Ausstiege rechnet manage() auf den
  Kerzen bis jetzt; an die Kerzen wird dafür eine "Jetzt-Kerze" mit dem aktuellen Kurs gehängt, damit ein Ausstieg auf
  dem Schluss sofort zur nächsten Eröffnung (= jetzt) ausgeführt wird.
- Ist die Position beim Broker weg, hat Stop oder Ziel ausgelöst: Schlusskurs aus der Kontoaktivität.
- Einstieg mit der kleinsten Ordergröße des Marktes, Stop und Ziel als Abstand beim Broker.

Schutz für den Gold-Bot (gleiches Demokonto): kein Gold, eine Position je Markt, ein Bot öffnet nur, wenn danach noch
`reserve_margin_eur` frei sind, nicht über `max_risiko_eur` je Trade und nicht mehr, wenn die Demo-Bots heute schon
`max_tagesverlust_r` R verloren haben. Positionen, die der Bot nicht selbst geöffnet hat, fasst er nie an.

Eigene Konten (Kirons Wunsch vom 03.11.2026, gold/bot/konten.py): Hat Kiron weitere Demokonten angelegt, bekommt jeder
Bot sein eigenes und handelt nur dort; die Margin-Reserve für den Gold-Bot gilt dann nur noch auf dem Hauptkonto. Ohne
eigenes Konto handelt ein Bot wie bisher auf dem Hauptkonto. `extra_bots` in demo_bots.yaml sind Bots außerhalb der
Runde-3-Regel (Gold-Bot 2.0 auf Gold); sie handeln nur auf einem eigenen Konto (`eigenes_konto: true`). Am Ende jedes
Laufs ist wieder das Hauptkonto aktiv. `ende_utc` in demo_bots.yaml verschiebt das Testende (Kiron: eine Woche).

Abgelöste Bots (Kirons Wunsch vom 04.11.2026: die Demokonten sind am Maximum, die besten Strategien sollen die Konten der
schwächeren bekommen; Wahl nach der gleichen Bewertung 2025-2026, suche/VORAB_bewertung.yaml): `abgeloest` in
demo_bots.yaml (alte Bot-ID -> {an: neue Bot-ID}). Ein abgelöster Bot öffnet keinen Trade mehr; eine offene Position
führt er nach seinen Regeln zu Ende. Sobald er keine Position mehr hat, schreibt der Lauf sein Konto in
journal/konten.json auf den Nachfolger um (uebergeben()); dessen eigener Lauf (us500_bot, r6_bots, r7_nasdaq_bot) läuft
im selben Workflow danach und handelt dann dort. Seine Trades bleiben im Journal und im Cockpit.

Dateien: journal/demo-bots.json (Stand für das Cockpit, Format bei cockpit()), journal/demo-bots/state.json,
journal/demo-bots/trades.jsonl (ein abgeschlossener Trade je Zeile), journal/demo-bots/log.jsonl (Ereignisse),
journal/demo-bots-chart.json (Kerzen, EMA 200, Ein- und Ausstiege je Bot für die Charts im Cockpit, Format bei
chart_file()), journal/konten.json (welcher Bot auf welchem Konto handelt, gold/bot/konten.py).
"""
from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from gold.backtest.runde2 import pf
from gold.bot import konten
from gold.v2 import termine
from gold.v2.fuehrung import manage
from suche.runde3 import SIDES, fuehrung, prepare, richtung_on, trend_ema

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "suche" / "demo_bots.yaml"
VORAB = ROOT / "suche" / "VORAB_runde3.yaml"
JDIR = ROOT / "journal" / "demo-bots"
COCKPIT = ROOT / "journal" / "demo-bots.json"
CHART = ROOT / "journal" / "demo-bots-chart.json"
PORTFOLIO = ROOT / "journal" / "portfolio.json"     # Rangliste der Bewertung 2025-2026 (suche/bewertung.py)
CHART_TAGE = 8                       # so viele Kalendertage Kerzen je Bot zeigt der Chart im Cockpit (Kiron 03.11.:
                                     # "wie sie letzte Woche gelaufen sind", also eine ganze Handelswoche und etwas mehr)
RES = {"15min": "MINUTE_15", "30min": "MINUTE_30", "60min": "HOUR"}
LOGIK_TEXT = {"gold": "Gold-Bot", "gold2": "Gold-Bot 2.0"}
GRUND = {"stop": "Stop (laut Kerzen)", "ziel": "Ziel (laut Kerzen)", "termin": "vor einem US-Termin",
         "zeit": "Zeitgrenze", "signal": "Ausstiegssignal", "richtung": "Markt-Richtung gedreht",
         "SL": "Stop beim Broker", "TP": "Ziel beim Broker", "USER": "von Hand geschlossen",
         "CLOSE_OUT": "Zwangsschließung (zu wenig Margin)", "ende": "Testende"}


# ---------- kleine Helfer ----------

def utc_naive(t) -> pd.Timestamp:
    t = pd.Timestamp(t)
    return t.tz_convert("UTC").tz_localize(None) if t.tzinfo else t


def end_after(start: pd.Timestamp, trading_days: int) -> pd.Timestamp:
    """start plus `trading_days` Werktage (Samstag und Sonntag zählen nicht), gleiche Uhrzeit."""
    t, left = pd.Timestamp(start), trading_days
    while left > 0:
        t += pd.Timedelta(days=1)
        if t.day_of_week < 5:
            left -= 1
    return t


def frame(prices: list[dict]) -> tuple[pd.DataFrame, pd.Series]:
    """Capital.com-Kerzen -> Bid-OHLC und Spread zur Eröffnung (Ask minus Bid), wie im Backtest."""
    rows = []
    for p in prices or []:
        o, h, l, c = (p.get(k) or {} for k in ("openPrice", "highPrice", "lowPrice", "closePrice"))
        if None in (o.get("bid"), h.get("bid"), l.get("bid"), c.get("bid")):
            continue
        rows.append({"time": utc_naive(p["snapshotTimeUTC"]), "open": o["bid"], "high": h["bid"], "low": l["bid"],
                     "close": c["bid"], "spread": (o.get("ask") or o["bid"]) - o["bid"]})
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close"], dtype=float), pd.Series(dtype=float)
    df = pd.DataFrame(rows).set_index("time").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df[["open", "high", "low", "close"]].astype(float), df["spread"].clip(lower=0).astype(float)


def only_closed(bars: pd.DataFrame, spread: pd.Series, now: pd.Timestamp, tf: str):
    done = bars.index + pd.Timedelta(tf) <= now
    return bars[done], spread[done]


def with_now_bar(bars: pd.DataFrame, spread: pd.Series, t: pd.Timestamp, bid: float, offer: float):
    """Hängt eine Kerze zur Zeit t an, Open = High = Low = Close = aktueller Bid, Spread = aktueller Spread."""
    nb = pd.DataFrame([[bid, bid, bid, bid]], index=pd.DatetimeIndex([t]), columns=bars.columns)
    return pd.concat([bars, nb]), pd.concat([spread, pd.Series([max(offer - bid, 0.0)], index=[t])])


@dataclass
class Quote:
    bid: float
    offer: float
    tradeable: bool
    currency: str
    lot: float
    min_size: float
    size_step: float
    margin_pct: float
    decimals: int
    min_dist: float          # Mindestabstand für Stop und Ziel in Kurs-Einheiten (0 = unbekannt)
    eur_rate: float | None   # Kurs EUR/<currency> (1 bei EUR), None = unbekannt


def quote_from_market(market: dict, eur_rate: float | None) -> Quote:
    snap, inst, rules = market.get("snapshot", {}), market.get("instrument", {}), market.get("dealingRules", {})
    bid, offer = float(snap.get("bid") or 0), float(snap.get("offer") or 0)
    mid = (bid + offer) / 2
    dist = rules.get("minStopOrProfitDistance") or {}
    if dist.get("unit") == "PERCENTAGE":
        min_dist = mid * float(dist.get("value") or 0) / 100
    else:
        min_dist = float(dist.get("value") or 0)
    unit = inst.get("marginFactorUnit", "PERCENTAGE")
    margin_pct = float(inst.get("marginFactor") or 20) if unit == "PERCENTAGE" else 20.0
    min_size = float((rules.get("minDealSize") or {}).get("value") or 1)
    step = float((rules.get("minSizeIncrement") or {}).get("value") or min_size)
    return Quote(bid, offer, snap.get("marketStatus") == "TRADEABLE", str(inst.get("currency") or "EUR"),
                 float(inst.get("lotSize") or 1), min_size, step, margin_pct, int(snap.get("decimalPlacesFactor") or 5),
                 min_dist, eur_rate)


def r_of(side: int, entry: float, exit_: float, risk_dist: float, nights: int, swap_pct: float) -> float:
    swap = entry * swap_pct / 100 / 365 * max(nights, 0)
    return (side * (exit_ - entry) - swap) / risk_dist if risk_dist else 0.0


# ---------- Entscheidung je Bot (ohne Netz, testbar) ----------

def decide(bot: dict, r3: dict, bars: pd.DataFrame, spread: pd.Series, hourly: pd.DataFrame, q: Quote,
           sb: dict, now: pd.Timestamp, events: pd.Series) -> dict:
    """Was dieser Bot jetzt tun soll. bars/spread: nur fertige Kerzen. sb: Zustand des Bots (open = eigene Position,
    die der Broker noch hat). Rückgabe: {"bar", "action": none|open|close, ...}."""
    tf = bot["zeitrahmen"]
    last = bars.index[-1]
    B, S = with_now_bar(bars, spread, last + pd.Timedelta(tf), q.bid, q.offer)
    P = prepare(B, S, hourly, tf, events, r3["logiken"]["gold2"]["news"])
    f = fuehrung(r3["logiken"][bot["logik"]])
    t = len(B) - 2
    out = {"bar": str(last), "action": "none", "why": []}
    op = sb.get("open")
    if op:
        ts = pd.Timestamp(op["t_sig"])
        if ts not in B.index:
            out.update(action="close", reason="signal", why=["Signalkerze nicht mehr in den Kerzen, sicherheitshalber raus"])
            return out
        p = manage(P.m, int(op["side"]), int(B.index.get_loc(ts)), f)
        if p is not None and p["reason"] != "datenende":
            out.update(action="close", reason=p["reason"], why=[GRUND.get(p["reason"], p["reason"])])
        return out
    use_l, use_s = SIDES[bot["seiten"]]
    el, es = P.entries[bot["logik"]]
    long_sig, short_sig = bool(el[t]) and use_l, bool(es[t]) and use_s
    if long_sig and short_sig:
        out["why"] = ["Long und Short zugleich, kein Einstieg"]
        return out
    if not (long_sig or short_sig):
        return out
    side = 1 if long_sig else -1
    a = float(P.m.atr[t])
    spec = r3["logiken"][bot["logik"]]["fuehrung"]
    out.update(action="open", side=side, t_sig=str(last), atr=a, stop_dist=spec["stop_atr"] * a,
               tp_dist=(spec["ziel_atr"] * a) if spec.get("ziel_atr") else None)
    return out


def size_for(q: Quote) -> float:
    steps = math.ceil(round(q.min_size / q.size_step, 9))
    return round(steps * q.size_step, 8)


def guards(d: dict, q: Quote, cfg: dict, available_eur: float, today_r: float, now: pd.Timestamp,
           ende: pd.Timestamp, reserve_eur: float | None = None) -> tuple[list[str], dict]:
    """Gründe gegen einen Einstieg, und die Order-Werte (Größe, Abstände), wie sie zum Broker gehen. reserve_eur: so
    viel Margin muss danach frei bleiben (Standard: reserve_margin_eur für den Gold-Bot auf dem Hauptkonto)."""
    why, size = [], size_for(q)
    reserve = cfg["reserve_margin_eur"] if reserve_eur is None else reserve_eur
    stop = max(d["stop_dist"], q.min_dist * 1.05)
    tp = None if d["tp_dist"] is None else max(d["tp_dist"], q.min_dist * 1.05)
    order = {"size": size, "stop_dist": round(stop, q.decimals), "tp_dist": None if tp is None else round(tp, q.decimals),
             "stop_breiter": stop > d["stop_dist"] * 1.0001, "ziel_weiter": tp is not None and tp > d["tp_dist"] * 1.0001}
    if now >= ende:
        why.append("Testzeit vorbei")
    if not q.tradeable:
        why.append("Markt gerade nicht handelbar")
    if today_r <= -abs(cfg["max_tagesverlust_r"]):
        why.append(f"Demo-Bots heute schon {today_r:.1f} R im Minus")
    price = q.offer if d["side"] > 0 else q.bid
    if q.eur_rate:
        risk_eur = stop * size * q.lot / q.eur_rate
        margin_eur = price * size * q.lot * q.margin_pct / 100 / q.eur_rate
        order.update(risk_eur=round(risk_eur, 2), margin_eur=round(margin_eur, 2))
        if risk_eur > cfg["max_risiko_eur"]:
            why.append(f"Risiko bei kleinster Größe {risk_eur:.2f} EUR, mehr als {cfg['max_risiko_eur']} EUR")
        if available_eur - margin_eur < reserve:
            why.append(f"Margin: danach weniger als {reserve:g} EUR frei"
                       + (" (Vorrang Gold-Bot)" if reserve_eur is None else ""))
    else:
        why.append(f"kein Umrechnungskurs EUR/{q.currency}, Risiko unbekannt")
    return why, order


# ---------- Broker ----------

def open_market(client, epic: str, side: int, order: dict) -> dict:
    """Marktorder auf dem Demokonto mit Stop- und Zielabstand beim Broker. Wird nie automatisch wiederholt."""
    body = {"epic": epic, "direction": "BUY" if side > 0 else "SELL", "size": order["size"], "guaranteedStop": False,
            "stopDistance": order["stop_dist"]}
    if order.get("tp_dist"):
        body["profitDistance"] = order["tp_dist"]
    ref = client._request("POST", "/positions", json=body).json()["dealReference"]
    return client.confirm(ref)


def own_position(positions: list[dict], epic: str, deal_ids: set[str] | None = None) -> list[dict]:
    out = [p for p in positions if p.get("market", {}).get("epic") == epic]
    return [p for p in out if p["position"].get("dealId") in deal_ids] if deal_ids is not None else out


def _utc_naiv(t) -> pd.Timestamp:
    """Zeitpunkt als UTC ohne Zeitzone (Journal-Zeiten sind UTC ohne Zone, `now` der Läufe hat oft eine)."""
    ts = pd.Timestamp(t)
    return ts.tz_convert("UTC").tz_localize(None) if ts.tzinfo is not None else ts


def broker_exit(client, op: dict, now: datetime, until: datetime | None = None) -> tuple[float | None, str]:
    """Schlusskurs und Grund, wenn der Broker die Position geschlossen hat (Stop, Ziel), aus der Kontoaktivität des
    aktiven Kontos. Dort steht auch die Eröffnung durch den Bot (source USER, Einstiegskurs). Die darf nie als Schluss
    gelten: Bis zum 03.11.2026 abends wurden so drei Dow-Trades zum Einstiegskurs als "von Hand geschlossen" gebucht,
    obwohl der Stop ausgelöst hatte (Konto -0,21 €). Darum dieselbe Auswahl wie beim Gold-Bot (close_activity).
    Ohne eindeutigen Schluss: (None, ""), dann schätzt trade_record den Stop.
    Capital.com erlaubt zwischen from und to höchstens 1 Tag (open-api.capital.com, GET /history/activity). Bis zum
    11.11.2026 fragte diese Funktion ab Eröffnung minus 1 Std. bis jetzt: Für jeden Trade, der länger als rund 23 Std.
    offen war, kam dann kein Schluss zurück und der Bot buchte den Stop als Schätzung, auch wenn das Ziel getroffen
    hatte. Darum wie beim Gold-Bot (gold/bot/runner.py closed_outside) höchstens die letzten 23 Std. 59 Min. Die Bots
    laufen alle 5 bis 15 Minuten, der Schluss liegt also immer in diesem Fenster."""
    from gold.bot.runner import close_activity
    try:
        bis = _utc_naiv(until or now)
        since = max(_utc_naiv(op.get("opened_utc") or bis) - pd.Timedelta(hours=1),
                    bis - pd.Timedelta(hours=23, minutes=59))
        acts = client.activity(op["dealId"], since.to_pydatetime(), until or now)
        raw = [{"dateUTC": a.get("dateUTC"), "source": a.get("source"), "type": a.get("type"), "status": a.get("status"),
                "level": (a.get("details") or {}).get("level"),
                "actions": [x.get("actionType") for x in (a.get("details") or {}).get("actions", [])]} for a in acts]
        close = close_activity(raw, op.get("opened_utc"))
        if close is None:
            return None, ""
        return float(close["level"]), str(close.get("source") or "")
    except Exception as err:            # noqa: BLE001 - dann geschätzt
        print(f"Kontoaktivität nicht lesbar: {err}")
        return None, ""


def falsch_gebucht(t: dict) -> bool:
    """Ein Trade, den das alte broker_exit zum Einstiegskurs als "von Hand geschlossen" gebucht hat (siehe oben)."""
    return (t.get("reason") == GRUND["USER"] and t.get("entry") is not None and t.get("exit") == t.get("entry")
            and not t.get("korrigiert"))


def nachbuchen(client, buchungen: list[dict], bots: list[dict], kont: dict, haupt: str | None, nowts: pd.Timestamp,
               r3: dict, rates: dict) -> list[dict]:
    """Falsch gebuchte Trades der letzten 7 Tage aus der Kontoaktivität ihres Kontos neu buchen (ändert `buchungen`).
    Nur mit eindeutigem Schluss beim Broker; sonst bleibt der Trade, wie er ist, und der nächste Lauf versucht es
    wieder. Rückgabe: Ereignisse fürs Log."""
    log = []
    by_id = {b["id"]: b for b in bots}
    zu = kont.get("zuordnung") or {}
    for i, t in enumerate(buchungen):
        bot = by_id.get(t.get("bot"))
        closed = pd.Timestamp(t.get("closed_utc") or nowts)
        closed = closed.tz_convert(None) if closed.tzinfo else closed
        if not bot or not falsch_gebucht(t) or nowts - closed > pd.Timedelta(days=7):
            continue
        frueher = [u.get("konto_id") for u in kont.get("uebergaben") or [] if u.get("von") == bot["id"]]
        aid = next((a for a in (zu.get(bot["id"]), *frueher, haupt) if a and konten.kurz(a) == t.get("konto")), None)
        if aid is None:
            continue
        try:
            konten.wechseln(client, aid)
            level, source = broker_exit(client, {"dealId": t["dealId"], "opened_utc": t.get("opened_utc")}, nowts.to_pydatetime(),
                                        until=min(closed + pd.Timedelta(hours=1), nowts).to_pydatetime())
            if level is None or (source == "USER" and abs(level - float(t["entry"])) < 1e-9):
                continue
            q = quote_from_market(client.market(bot["epic"]), None)
            q.eur_rate = eur_rate(client, q.currency, rates)
            op = {"side": 1 if t["side"] == "long" else -1, "entry": t["entry"], "size": t["size"], "lot": q.lot,
                  "stop_dist": t["stop_dist"], "tp_dist": t.get("tp_dist"), "t_sig": t.get("signal_bar"),
                  "dealId": t["dealId"], "opened_utc": t.get("opened_utc"), "currency": t.get("waehrung") or q.currency,
                  "konto": aid}
            swap = r3["kosten"]["swap_pct_jahr"].get(bot.get("typ"), 6.0)
            neu = trade_record(bot, op, level, closed, source or "SL", swap, False, q)
            neu["closed_utc"] = t.get("closed_utc")
            neu["korrigiert"] = nowts.isoformat()
            buchungen[i] = neu
            log.append({"time": nowts.isoformat(), "bot": bot["id"], "event": "nachgebucht", "dealId": t["dealId"],
                        "exit": neu["exit"], "r": neu["r"], "reason": neu["reason"]})
        except Exception as err:        # noqa: BLE001 - nächster Lauf versucht es wieder
            log.append({"time": nowts.isoformat(), "bot": bot["id"], "event": "nachbuchen fehlgeschlagen",
                        "why": str(err)[:160]})
    return log


def fetch(client, epic: str, tf: str) -> tuple[list[dict], list[dict]]:
    """Kerzen des Zeitrahmens (1.000) und etwa 1.900 Stundenkerzen für Trend-EMA und Markt-Richtung. Nur GET."""
    from gold.v2.schatten import fetch_candles
    hourly = fetch_candles(client, epic, chunks=1)
    chart = hourly if tf == "60min" else client.prices(epic, RES[tf], 1000)
    return chart, hourly


def eur_rate(client, currency: str, cache: dict) -> float | None:
    if currency == "EUR":
        return 1.0
    if currency not in cache:
        try:
            snap = client.market(f"EUR{currency}")["snapshot"]
            cache[currency] = (float(snap["bid"]) + float(snap["offer"])) / 2
        except Exception:               # noqa: BLE001
            cache[currency] = None
    return cache[currency]


# ---------- Ein Lauf ----------

def read_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def trade_record(bot: dict, op: dict, exit_level: float | None, now: pd.Timestamp, reason: str, swap_pct: float,
                 estimated: bool, q: Quote | None) -> dict:
    side = int(op["side"])
    entry = float(op["entry"]) if op.get("entry") is not None else None
    if exit_level is None and entry is not None:       # geschätzt: Stop oder Ziel
        exit_level = entry + (side * op["tp_dist"] if reason == "TP" and op.get("tp_dist") else -side * op["stop_dist"])
        estimated = True
    nights = int((now.normalize() - pd.Timestamp(op.get("opened_utc") or now).normalize()).days)
    r = r_of(side, entry, exit_level, op["stop_dist"], nights, swap_pct) if entry is not None else None
    pnl = None if entry is None else side * (exit_level - entry) * float(op["size"]) * float(op.get("lot", 1))
    rate = q.eur_rate if q else op.get("eur_rate")
    return {"bot": bot["id"], "name": bot["name"], "epic": bot["epic"], "zeitrahmen": bot["zeitrahmen"],
            "logik": bot["logik"], "side": "long" if side > 0 else "short", "dealId": op.get("dealId"),
            "size": op["size"], "entry": entry, "exit": None if exit_level is None else round(float(exit_level), 6),
            "stop_dist": op["stop_dist"], "tp_dist": op.get("tp_dist"), "signal_bar": op["t_sig"],
            "opened_utc": op.get("opened_utc"), "closed_utc": now.isoformat(), "reason": GRUND.get(reason, reason),
            "r": None if r is None else round(r, 3), "pnl": None if pnl is None else round(pnl, 4),
            "waehrung": op.get("currency"), "pnl_eur": None if pnl is None or not rate else round(pnl / rate, 2),
            "geschaetzt": estimated, "konto": konten.kurz(op.get("konto"))}


def summary(trades: list[dict]) -> dict:
    r = np.array([t["r"] for t in trades if t.get("r") is not None], float)
    return {"trades": int(len(r)), "win_pct": round(100 * float((r > 0).mean()), 1) if len(r) else None,
            "pf_r": pf(r) if len(r) else None, "sum_r": round(float(r.sum()), 2) if len(r) else 0.0,
            "pnl_eur": round(float(sum(t.get("pnl_eur") or 0 for t in trades)), 2)}


def bewertung(s: dict, rules: dict) -> str:
    if s["trades"] < 3:
        return "zu wenige Trades"
    return "gut" if s["sum_r"] > 0 and (s["pf_r"] or 0) >= 1.2 else "schlecht"


def alle_bots(cfg: dict) -> list[dict]:
    """Die Bots der Runde-3-Regel und danach die Extra-Bots (Gold-Bot 2.0), in dieser Reihenfolge."""
    return list(cfg.get("bots") or []) + list(cfg.get("extra_bots") or [])


def _abl_text(nach: dict) -> str:
    return f"abgelöst, Konto an {nach['an']}" if (nach or {}).get("an") else "abgelöst, Konto wird frei"


def uebergeben(kont: dict, abgeloest: dict, offen: set[str], accounts: list[dict], stamp: str) -> list[dict]:
    """Konten abgelöster Bots an ihre Nachfolger (reine Funktion, ändert `kont`). Kirons Wunsch vom 04.11.2026: die
    Demokonten sind am Maximum, also bekommen bessere Strategien die Konten der schwächeren (suche/VORAB_bewertung.yaml).
    abgeloest: alte Bot-ID -> {"an": neue Bot-ID, ...}. offen: Bots, die noch eine Position haben; deren Konto wechselt
    erst, wenn sie zu ist. Hat der Nachfolger schon ein Konto, passiert nichts. Rückgabe: Ereignisse fürs Log."""
    zu = kont.setdefault("zuordnung", {})
    by_id = {str(a.get("accountId")): a for a in accounts if a.get("accountId")}
    log = []
    for alt, nach in abgeloest.items():
        neu_id = (nach or {}).get("an")
        aid = zu.get(alt)
        if not aid or alt in offen or (neu_id and neu_id in zu):
            continue
        zu.pop(alt)
        if neu_id:
            zu[neu_id] = aid
        elif str(aid) not in (kont.get("frei") or []):  # kein Ersatz: Konto frei, die Prüfung vergibt es später
            kont.setdefault("frei", []).append(str(aid))
        acc = by_id.get(str(aid)) or {}
        bal = (acc.get("balance") or {}).get("balance")
        kont.setdefault("start", {})[str(aid)] = bal
        kont.setdefault("uebergaben", []).append({"zeit": stamp, "konto": konten.kurz(aid), "konto_id": str(aid),
                                                  "name": acc.get("accountName"), "von": alt, "an": neu_id,
                                                  "kontostand": bal})
        for e in kont.get("konten") or []:
            if e.get("id") == konten.kurz(aid):
                e["fuer"] = neu_id
        log.append({"time": stamp, "event": "konto übergeben" if neu_id else "konto frei", "bot": alt, "an": neu_id,
                    "konto": konten.kurz(aid),
                    "name": acc.get("accountName"), "kontostand": bal})
    return log


def portfolio_rollen(pf: dict, zu: dict) -> bool:
    """journal/portfolio.json (Rangliste der Bewertung 2025-2026, im Cockpit): ein gewählter Bot, der auf sein Konto
    wartet, steht als aktiv da, sobald journal/konten.json ihm das Konto zuordnet. Gibt True zurück, wenn sich etwas
    geändert hat."""
    neu = False
    for b in (pf or {}).get("bots") or []:
        if b.get("rolle") == "wartet" and b.get("id") in (zu or {}):
            b["rolle"], neu = "aktiv", True
    return neu


def run(client, cfg: dict, r3: dict, state: dict, now: datetime, send_orders: bool = True,
        charts: dict | None = None, kont: dict | None = None,
        buchungen: list[dict] | None = None) -> tuple[dict, list, list]:
    """Ein Lauf über alle Bots. Gibt neuen Zustand, neue Trades und Ereignisse zurück. Ist `charts` ein dict, kommen
    dort je Bot die Kerzen für den Chart im Cockpit hinein (chart_series). `kont` ist der Inhalt von
    journal/konten.json; er wird hier mit der neuen Zuordnung überschrieben (gold/bot/konten.py). `buchungen` sind die
    bisherigen Trades (journal/demo-bots/trades.jsonl); falsch gebuchte werden darin korrigiert (nachbuchen)."""
    nowts = utc_naive(now)
    st = dict(state)
    st.setdefault("bots", {})
    kont = {} if kont is None else kont
    log, new_trades = [], []
    stamp = nowts.isoformat()
    bots = alle_bots(cfg)
    # abgelöste Bots: kein neuer Trade, Konto geht an den Nachfolger (nur Bots dieses Laufs; andere Läufe übergeben selbst)
    # dazu die Bots, die die Prüfung nach 15/40 Demo-Trades abgelöst hat (suche/demo_pruefung.py, journal/konten.json)
    abl = {a: n for a, n in {**(cfg.get("abgeloest") or {}), **(kont.get("abgeloest") or {})}.items()
           if a in {b["id"] for b in bots}}
    aktive = [b for b in bots if b["id"] not in abl]
    if not st.get("start_utc"):
        st["start_utc"] = stamp
        st["ende_utc"] = end_after(nowts, cfg["handelstage"]).isoformat()
        log.append({"time": stamp, "event": "start", "ende_utc": st["ende_utc"]})
    if cfg.get("ende_utc"):                       # Kirons Wunsch: Testende verschoben
        neu = pd.Timestamp(cfg["ende_utc"]).isoformat()
        if st.get("ende_utc") != neu:
            log.append({"time": stamp, "event": "ende verschoben", "von": st.get("ende_utc"), "auf": neu})
            st["ende_utc"] = neu
    ende = pd.Timestamp(st["ende_utc"])
    events = termine.load()["utc"]
    client.login()
    accounts = client.accounts()
    start_id = getattr(client, "account_id", None) or next(
        (a.get("accountId") for a in accounts if a.get("preferred")), None) or (accounts[0].get("accountId") if accounts else None)
    start_id = None if start_id is None else str(start_id)
    haupt = konten.haupt_von(accounts, kont, start_id)
    pos_cache: dict = {}

    def positions_of(aid):
        """Positionen eines Kontos (wechselt dorthin). Ohne Konto-IDs (ein einziges Konto) nur das aktive."""
        konten.wechseln(client, aid)
        if aid not in pos_cache:
            pos_cache[aid] = client.positions()
        return pos_cache[aid]

    # Konten zuordnen: nur wenn es mehr als ein Konto gibt und noch Bots ohne eigenes Konto sind
    if cfg.get("eigene_konten", True) and len(accounts) > 1 and haupt:
        vergeben = {haupt, *(kont.get("zuordnung") or {}).values(), *(kont.get("frei") or [])}
        frei = {}
        if any(b["id"] not in (kont.get("zuordnung") or {}) for b in aktive):
            for a in accounts:
                aid = str(a.get("accountId") or "")
                if aid and aid not in vergeben:
                    try:
                        frei[aid] = not positions_of(aid)
                    except Exception as err:   # noqa: BLE001 - dann eben nicht vergeben
                        log.append({"time": stamp, "event": "konto nicht lesbar", "konto": konten.kurz(aid),
                                    "why": str(err)[:160]})
        gesperrt = set()
        for b in aktive:
            op = (st["bots"].get(b["id"]) or {}).get("open")
            if op and str(op.get("konto") or haupt) != (kont.get("zuordnung") or {}).get(b["id"]):
                gesperrt.add(b["id"])
        neu, klog = konten.zuordnen(kont, accounts, aktive, frei, start_id, gesperrt, stamp)
        kont.clear()
        kont.update(neu)
        log += klog
    elif haupt and not kont.get("haupt"):
        neu, klog = konten.zuordnen(kont, accounts, aktive, {}, start_id, set(), stamp)
        kont.clear()
        kont.update(neu)
        log += klog
    zu = kont.get("zuordnung") or {}
    acc_by_id = {str(a.get("accountId")): a for a in accounts if a.get("accountId")}
    main_acc = acc_by_id.get(haupt or "") or next((a for a in accounts if a.get("preferred")), None) or (accounts or [{}])[0]
    bal = main_acc.get("balance", {})
    available = {aid: float((a.get("balance") or {}).get("available") or 0) for aid, a in acc_by_id.items()}
    available.setdefault(haupt, float(bal.get("available") or 0))
    st["konto"] = {"waehrung": main_acc.get("currency", "EUR"), "balance": bal.get("balance"), "frei": bal.get("available")}
    today = nowts.normalize()
    past = st.get("trades_heute", {})
    today_r = float(past.get("r", 0.0)) if past.get("tag") == str(today.date()) else 0.0
    rates: dict = {}
    if buchungen:
        log += nachbuchen(client, buchungen, bots, kont, haupt, nowts, r3, rates)
    positionen: dict = {}
    for bot in bots:
        sb = dict(st["bots"].get(bot["id"], {}))
        swap = r3["kosten"]["swap_pct_jahr"].get(bot.get("typ"), 6.0)
        nach = abl.get(bot["id"])
        if nach and not sb.get("open"):
            sb["status"] = _abl_text(nach)
            sb["konto"] = None
            st["bots"][bot["id"]] = sb
            continue
        try:
            op = sb.get("open")
            if op:                                   # eine offene Position bleibt auf ihrem Konto
                aid = str(op.get("konto") or haupt or "") or None
            else:
                aid = zu.get(bot["id"]) or (None if bot.get("eigenes_konto") else haupt)
            if aid is None and bot.get("eigenes_konto"):
                sb["status"] = "wartet auf ein eigenes Demokonto"
                sb["konto"] = None
                st["bots"][bot["id"]] = sb
                continue
            sb["konto"] = konten.kurz(aid)
            positions = positions_of(aid)
            reserve = None if (aid == haupt or not zu) else float(cfg.get("reserve_margin_eigen_eur", 0))
            market = client.market(bot["epic"])
            q = quote_from_market(market, None)
            q.eur_rate = eur_rate(client, q.currency, rates)
            mine = own_position(positions, bot["epic"])
            # 1. Position weg, die der Bot hatte -> Broker hat geschlossen (Stop oder Ziel)
            if op and op.get("dealId") not in {p["position"].get("dealId") for p in mine}:
                level, source = broker_exit(client, op, now)
                tr = trade_record(bot, op, level, nowts, source or "SL", swap, level is None, q)
                new_trades.append(tr)
                today_r += tr["r"] or 0.0
                log.append({"time": stamp, "bot": bot["id"], "event": "vom Broker geschlossen", **{k: tr[k] for k in ("exit", "r", "reason")}})
                sb["open"], op = None, None
            if nach and not op:                      # abgelöst: nach dem Schließen kein neuer Trade mehr
                sb["status"] = _abl_text(nach)
                st["bots"][bot["id"]] = sb
                continue
            # 2. Testende: offene Position schließen, dann nichts mehr
            if nowts >= ende:
                if op and send_orders:
                    res = client.close_position(op["dealId"])
                    if res.get("dealStatus") == "ACCEPTED":
                        tr = trade_record(bot, op, res.get("level"), nowts, "ende", swap, False, q)
                        new_trades.append(tr)
                        sb["open"] = None
                sb["status"] = "beendet"
                st["bots"][bot["id"]] = sb
                continue
            foreign = [p for p in mine if not op or p["position"].get("dealId") != op.get("dealId")]
            if foreign:
                sb["status"] = "fremde Position auf diesem Markt, Bot wartet"
                st["bots"][bot["id"]] = sb
                log.append({"time": stamp, "bot": bot["id"], "event": "gesperrt", "why": sb["status"]})
                continue
            chart, hourly_p = fetch(client, bot["epic"], bot["zeitrahmen"])
            bars, spread = only_closed(*frame(chart), nowts, bot["zeitrahmen"])
            hourly, _ = only_closed(*frame(hourly_p), nowts, "60min")
            if len(bars) < 300 or len(hourly) < 300:
                sb["status"] = f"zu wenige Kerzen ({len(bars)}/{len(hourly)})"
                st["bots"][bot["id"]] = sb
                continue
            if charts is not None:
                try:
                    charts[bot["id"]] = chart_series(bot, bars, hourly, q.decimals)
                except Exception as err:    # noqa: BLE001 - der Chart ist nur Anzeige, der Bot handelt trotzdem
                    log.append({"time": stamp, "bot": bot["id"], "event": "chart fehler", "why": str(err)[:200]})
            last = str(bars.index[-1])
            if sb.get("last_bar") == last:          # Kerze schon verarbeitet (zweiter Lauf in derselben Kerze)
                sb["status"] = "Position offen" if sb.get("open") else "wartet auf Signal"
                st["bots"][bot["id"]] = sb
                continue
            d = decide(bot, r3, bars, spread, hourly, q, sb, nowts, events)
            sb["last_bar"] = last
            sb["letzte_entscheidung"] = {k: d[k] for k in ("bar", "action", "why")}
            if d["action"] == "close" and op:
                if send_orders:
                    res = client.close_position(op["dealId"])
                    pos_cache.pop(aid, None)
                    if res.get("dealStatus") == "ACCEPTED":
                        tr = trade_record(bot, op, res.get("level"), nowts, d["reason"], swap, False, q)
                        new_trades.append(tr)
                        today_r += tr["r"] or 0.0
                        sb["open"] = None
                        log.append({"time": stamp, "bot": bot["id"], "event": "geschlossen", **{k: tr[k] for k in ("exit", "r", "reason")}})
                    else:
                        log.append({"time": stamp, "bot": bot["id"], "event": "schließen abgelehnt", "res": str(res)[:200]})
                else:
                    log.append({"time": stamp, "bot": bot["id"], "event": "würde schließen (Trockenlauf)", "why": d["why"]})
            elif d["action"] == "open" and not nach:
                why, order = guards(d, q, cfg, available.get(aid, 0.0), today_r, nowts, ende, reserve)
                ev = {"time": stamp, "bot": bot["id"], "bar": last, "side": "long" if d["side"] > 0 else "short",
                      "konto": konten.kurz(aid), **order}
                if why:
                    log.append({**ev, "event": "Signal nicht genutzt", "why": why})
                elif not send_orders:
                    log.append({**ev, "event": "würde öffnen (Trockenlauf)"})
                else:
                    res = open_market(client, bot["epic"], d["side"], order)
                    pos_cache.pop(aid, None)
                    if res.get("dealStatus") != "ACCEPTED":
                        log.append({**ev, "event": "Order abgelehnt", "res": str(res)[:300]})
                    else:
                        after = own_position(positions_of(aid), bot["epic"])
                        pos = after[0]["position"] if after else {}
                        sb["open"] = {"dealId": pos.get("dealId") or res.get("dealId") or (res.get("affectedDeals") or [{}])[0].get("dealId"),
                                      "side": d["side"], "t_sig": d["t_sig"], "entry": pos.get("level") or res.get("level"),
                                      "stop_dist": order["stop_dist"], "tp_dist": order["tp_dist"], "size": order["size"],
                                      "lot": q.lot, "currency": q.currency, "eur_rate": q.eur_rate,
                                      "stop_breiter": order["stop_breiter"], "ziel_weiter": order["ziel_weiter"],
                                      "opened_utc": pos.get("createdDateUTC") or stamp, "konto": aid}
                        available[aid] = available.get(aid, 0.0) - order.get("margin_eur", 0.0)
                        log.append({**ev, "event": "eröffnet", "entry": sb["open"]["entry"], "dealId": sb["open"]["dealId"]})
            sb["status"] = "Position offen" if sb.get("open") else "wartet auf Signal"
        except Exception as err:        # noqa: BLE001 - ein Bot darf die anderen nie aufhalten
            sb["status"] = f"Fehler: {str(err)[:160]}"
            log.append({"time": stamp, "bot": bot["id"], "event": "fehler", "why": str(err)[:300]})
        st["bots"][bot["id"]] = sb
    st["trades_heute"] = {"tag": str(today.date()), "r": round(today_r, 3)}
    st["stand_utc"] = stamp
    st["phase"] = "beendet" if nowts >= ende else "laeuft"
    for bot in bots:                     # nur für die Anzeige: Stop, Ziel und Buchgewinn der offenen Positionen
        op = (st["bots"].get(bot["id"]) or {}).get("open")
        if not op:
            continue
        try:
            p = own_position(positions_of(str(op.get("konto") or haupt or "") or None), bot["epic"], {op.get("dealId")})
            if p:
                positionen[bot["id"]] = {"upl": p[0]["position"].get("upl"), "level": p[0]["position"].get("level"),
                                         "stop": p[0]["position"].get("stopLevel"), "ziel": p[0]["position"].get("profitLevel")}
        except Exception:                # noqa: BLE001 - nur für die Anzeige
            pass
    st["positionen"] = positionen
    if abl and kont.get("haupt"):
        offen = {b for b, sb in st["bots"].items() if sb.get("open")}
        if any((kont.get("zuordnung") or {}).get(a) and a not in offen for a in abl):
            try:                         # frischer Kontostand als Start des Nachfolgers
                accounts = client.accounts() or accounts
            except Exception:            # noqa: BLE001 - dann der Stand vom Anfang des Laufs
                pass
            log += uebergeben(kont, abl, offen, accounts, stamp)
        zu = kont.get("zuordnung") or {}
    try:                                 # Ordnung: am Ende ist wieder das Hauptkonto aktiv (der Gold-Bot erwartet es)
        konten.wechseln(client, haupt)
    except Exception as err:             # noqa: BLE001
        log.append({"time": stamp, "event": "zurück aufs Hauptkonto fehlgeschlagen", "why": str(err)[:160]})
    if kont.get("haupt"):
        st["konten"] = {b["id"]: konten.konto_info(kont, accounts, (st["bots"].get(b["id"], {}).get("open") or {}).get("konto")
                                                    or zu.get(b["id"])
                                                    or (None if b.get("eigenes_konto") or b["id"] in abl else haupt))
                        for b in bots}
    return st, new_trades, log


# ---------- Charts für das Cockpit ----------

def _digits(decimals: int) -> int:
    return int(min(max(decimals if decimals and decimals > 0 else 5, 0), 8))


def chart_series(bot: dict, bars: pd.DataFrame, hourly: pd.DataFrame, decimals: int = 5) -> dict:
    """Die fertigen Bid-Kerzen der letzten CHART_TAGE Tage, dazu die EMA 200 der Stunde (Trendfilter von C und B,
    so wie der Bot sie für jede Kerze sieht) und bei Gold-Bot 2.0 die Richtung (+1, -1, 0)."""
    dg = _digits(decimals)
    ema = trend_ema(hourly, bars.index)
    tail = bars[bars.index >= bars.index[-1] - pd.Timedelta(days=CHART_TAGE)]
    e = ema[-len(tail):]
    out = {"kerzen": [[str(t), round(float(r.open), dg), round(float(r.high), dg), round(float(r.low), dg),
                       round(float(r.close), dg)] for t, r in tail.iterrows()],
           "ema200": [[str(t), round(float(v), dg)] for t, v in zip(tail.index, e) if np.isfinite(v)]}
    if bot["logik"] == "gold2":
        rich = richtung_on(hourly, bars.index, bot["zeitrahmen"])[-len(tail):]
        out["richtung"] = [[str(t), int(v)] for t, v in zip(tail.index, rich)]
    return out


def _snap(t, tf: str, first: str, last: str) -> str | None:
    """Zeitpunkt -> Beginn der Kerze, in der er liegt; nach der letzten fertigen Kerze -> letzte Kerze."""
    if not t:
        return None
    ts = pd.Timestamp(str(t).replace("Z", "")).floor(tf)
    if ts < pd.Timestamp(first):
        return None
    return str(min(ts, pd.Timestamp(last)))


def chart_file(cfg: dict, st: dict, trades: list[dict], charts: dict, old: dict | None = None) -> dict:
    """Inhalt von journal/demo-bots-chart.json (format 1): je Bot Kerzen, EMA 200, Marker und offene Position.

    Marker: Einstieg auf der Signalkerze (wie die Pfeile in TradingView), Ausstieg auf der Kerze, in der er geschah.
    Hat ein Bot in diesem Lauf keine Kerzen geholt (z. B. Markt zu), bleiben seine Kerzen aus der alten Datei."""
    prev = {b.get("id"): b for b in (old or {}).get("bots", [])}
    bots = []
    for bot in alle_bots(cfg):
        ser = charts.get(bot["id"]) or {k: prev.get(bot["id"], {}).get(k) for k in ("kerzen", "ema200", "richtung")}
        kerzen = ser.get("kerzen") or []
        sb = st.get("bots", {}).get(bot["id"], {})
        marker, position = [], None
        if kerzen:
            first, last = kerzen[0][0], kerzen[-1][0]
            for t in (t for t in trades if t.get("bot") == bot["id"]):
                side = t.get("side")
                k_in = _snap(t.get("signal_bar"), bot["zeitrahmen"], first, last)
                if k_in:
                    marker.append({"zeit": k_in, "art": "einstieg", "side": side, "preis": t.get("entry"),
                                   "text": ("Long" if side == "long" else "Short") + " Einstieg"})
                k_out = _snap(t.get("closed_utc"), bot["zeitrahmen"], first, last)
                if k_out:
                    r = t.get("r")
                    marker.append({"zeit": k_out, "art": "ausstieg", "side": side, "preis": t.get("exit"),
                                   "text": f"Ausstieg: {t.get('reason')}" + ("" if r is None else f", {r:+.2f} R")})
            op = sb.get("open")
            if op:
                side = "long" if op["side"] > 0 else "short"
                pos = (st.get("positionen") or {}).get(bot["id"]) or {}
                k_in = _snap(op.get("t_sig"), bot["zeitrahmen"], first, last)
                if k_in:
                    marker.append({"zeit": k_in, "art": "einstieg", "side": side, "preis": op.get("entry"),
                                   "text": ("Long" if side == "long" else "Short") + " Einstieg (offen)"})
                position = {"side": side, "entry": op.get("entry"), "stop": pos.get("stop"), "ziel": pos.get("ziel"),
                            "opened_utc": op.get("opened_utc"), "upl": pos.get("upl")}
        marker.sort(key=lambda m: m["zeit"])
        bots.append({"id": bot["id"], "name": bot["name"], "epic": bot["epic"], "zeitrahmen": bot["zeitrahmen"],
                     "logik_text": LOGIK_TEXT[bot["logik"]], "seiten": bot["seiten"], "kerzen": kerzen,
                     "ema200": ser.get("ema200") or [], "richtung": ser.get("richtung"), "marker": marker,
                     "position": position})
    return {"format": 1, "stand_utc": st.get("stand_utc"),
            "hinweis": f"Bid-Kerzen vom Capital.com-Demokonto, die fertigen Kerzen der letzten {CHART_TAGE} Tage je Bot. Zeiten in "
                       "UTC, Beginn der Kerze. EMA 200 = Trendfilter (Long nur darüber, Short nur darunter).",
            "bots": bots}


def cockpit(cfg: dict, st: dict, trades: list[dict]) -> dict:
    """Inhalt von journal/demo-bots.json (format 1), für die Karte "Demo-Tests" im Cockpit."""
    bots = []
    for bot in alle_bots(cfg):
        sb = st.get("bots", {}).get(bot["id"], {})
        mine = [t for t in trades if t["bot"] == bot["id"]]
        s = summary(mine)
        op, pos = sb.get("open"), (st.get("positionen") or {}).get(bot["id"])
        bots.append({"id": bot["id"], "name": bot["name"], "epic": bot["epic"], "typ": bot.get("typ"),
                     "zeitrahmen": bot["zeitrahmen"], "logik_text": LOGIK_TEXT[bot["logik"]], "seiten": bot["seiten"],
                     "backtest": bot.get("backtest"), "status": sb.get("status", "startet beim nächsten Lauf"),
                     "position": None if not op else {
                         "side": "long" if op["side"] > 0 else "short", "entry": op.get("entry"),
                         "stop": (pos or {}).get("stop"), "ziel": (pos or {}).get("ziel"), "size": op.get("size"),
                         "upl": (pos or {}).get("upl"), "opened_utc": op.get("opened_utc")},
                     **s, "letzte_kerze": sb.get("last_bar"),
                     "bewertung": bewertung(s, cfg) if st.get("phase") == "beendet" else None,
                     "hinweis": bot.get("hinweis"), "konto": (st.get("konten") or {}).get(bot["id"]),
                     "extra": bot in (cfg.get("extra_bots") or []),
                     "abgeloest": (cfg.get("abgeloest") or {}).get(bot["id"])})
    return {"format": 1, "stand_utc": st.get("stand_utc"), "phase": st.get("phase", "wartet"),
            "start_utc": st.get("start_utc"), "ende_utc": st.get("ende_utc"), "konto": st.get("konto"),
            "regel": cfg.get("regel_text"), "bots": bots, "extra_regel": cfg.get("extra_regel_text"),
            "trades": [{k: t.get(k) for k in ("bot", "name", "side", "opened_utc", "closed_utc", "entry", "exit", "r",
                                              "pnl", "waehrung", "reason")} for t in trades[-50:]]}


def main(argv: list[str]) -> int:
    from gold.bot.capital import CapitalClient
    from gold.bot.runner import CRED_KEYS, clean_credentials

    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if not cfg.get("aktiv") or not alle_bots(cfg):
        print("Demo-Bots nicht aktiv")
        return 0
    creds = clean_credentials({k: os.environ.get(k, "") for k in CRED_KEYS})
    if not all(creds):
        print("Keine Capital.com-Zugangsdaten, Demo-Bots übersprungen")
        return 0
    r3 = yaml.safe_load(VORAB.read_text(encoding="utf-8"))["runde_3"]
    JDIR.mkdir(parents=True, exist_ok=True)
    state = read_json(JDIR / "state.json", {})
    if state.get("phase") == "beendet" and state.get("abgeschlossen"):
        print("Demo-Test ist beendet")
        return 0
    client = CapitalClient(*creds, environment="demo")      # fest Demo: Live gibt es hier nicht
    now = datetime.now(timezone.utc)
    dry = "--dry-run" in argv
    kont = konten.load(COCKPIT.parent)
    try:
        charts: dict = {}
        path = JDIR / "trades.jsonl"
        alt = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []
        st, new_trades, log = run(client, cfg, r3, state, now, send_orders=not dry, charts=charts, kont=kont,
                                  buchungen=alt)
    finally:
        try:
            client.logout()
        except Exception:               # noqa: BLE001
            pass
    if dry:                             # Trockenlauf: nichts speichern, sonst liefe die Testzeit schon los
        ch = chart_file(cfg, st, new_trades, charts)
        print(json.dumps({"trockenlauf": True, "log": log, "konten": kont.get("konten"),
                          "zuordnung": {b: konten.kurz(a) for b, a in (kont.get("zuordnung") or {}).items()},
                          "hauptkonto": konten.kurz(kont.get("haupt")), "cockpit": cockpit(cfg, st, new_trades),
                          "chart": [{"id": b["id"], "kerzen": len(b["kerzen"]), "von": (b["kerzen"] or [[None]])[0][0],
                                     "bis": (b["kerzen"] or [[None]])[-1][0], "ema200": len(b["ema200"]),
                                     "marker": b["marker"]} for b in ch["bots"]]},
                         ensure_ascii=False, indent=1, default=str))
        return 0
    if any(e.get("event") == "nachgebucht" for e in log):     # korrigierte Trades: Datei neu schreiben
        path.write_text("".join(json.dumps(t, ensure_ascii=False, default=str) + "\n" for t in alt), encoding="utf-8")
    if new_trades:
        with open(path, "a", encoding="utf-8") as fh:
            for t in new_trades:
                fh.write(json.dumps(t, ensure_ascii=False, default=str) + "\n")
    if log:
        with open(JDIR / "log.jsonl", "a", encoding="utf-8") as fh:
            for e in log:
                fh.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
    trades = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []
    if st.get("phase") == "beendet" and not any(b.get("open") for b in st["bots"].values()):
        st["abgeschlossen"] = True
    if kont.get("haupt"):
        konten.save(kont, COCKPIT.parent)
        pf = read_json(PORTFOLIO, None)
        if isinstance(pf, dict) and portfolio_rollen(pf, kont.get("zuordnung")):
            PORTFOLIO.write_text(json.dumps(pf, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (JDIR / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    COCKPIT.write_text(json.dumps(cockpit(cfg, st, trades), ensure_ascii=False, indent=1, default=str) + "\n",
                       encoding="utf-8")
    try:                                # nur Anzeige: ein Fehler hier darf den Lauf nicht kaputt machen
        CHART.write_text(json.dumps(chart_file(cfg, st, trades, charts, read_json(CHART, {})), ensure_ascii=False,
                                    separators=(",", ":"), default=str) + "\n", encoding="utf-8")
    except Exception as err:            # noqa: BLE001
        print("Chart nicht geschrieben:", err)
    print(json.dumps({"phase": st.get("phase"), "neue_trades": len(new_trades), "log": log}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
