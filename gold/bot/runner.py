"""Ein Lauf des Gold-Bots für das Capital.com-Demokonto. Gedacht für einen stündlichen Aufruf kurz nach
der vollen Stunde (GitHub Action `gold-bot.yml`).

    python -m gold.bot.runner            # rechnet, und sendet Orders nur ab Stufe 1 im Abschnitt gold:
    python -m gold.bot.runner --dry-run  # rechnet nur, sendet nie

Ablauf: Kerzen holen, Signale der LONG v6 (C) und SHORT v6 (B) mit Trendfilter auf der letzten fertigen
Kerze berechnen, Position und Konto beim Broker lesen, `rules.decide` entscheiden lassen, ausführen,
alles ins Journal. Der Broker ist die Wahrheit über die Position.

GitHub startet geplante Läufe oft spät oder gar nicht, deshalb gibt es zwei Versuche pro Stunde. Die
zuletzt verarbeitete Kerze steht in journal/gold-state.json (`last_bar`): der zweite Versuch auf derselben
Kerze tut nichts. Ist ein Lauf ganz ausgefallen, holt `rules.catch_up` verpasste Ausstiege nach.

Nach jeder verarbeiteten Kerze schreibt der Lauf journal/gold-chart.json (Format bei `chart_snapshot`): die
letzten Stundenkerzen und die offene Position, für die Chart-Seite mit Pfeilen wie in TradingView. Die Datei
ist nur zum Anschauen, an Entscheidungen und Orders ändert sie nichts.

Jeder abgeschlossene Trade landet in journal/gold-trades.jsonl (Format bei `trade_entry`), auch wenn der
Notfall-Stop beim Broker zwischen zwei Läufen auslöst: Dann fehlt die Position, die in gold-state.json
(`open_trade`) stand, und der Lauf liest den Schlusskurs aus der Kontoaktivität des Brokers.

Vor jeder Entscheidung prüft `schalter.pruefen` den Sicherheitsschalter (Kritik D4): Steht die Summe R seit dem
Start des 1-ATR-Tests bei -8 oder tiefer, oder bestehen die ersten 30 Trades das Urteil nicht, gibt es keine neuen
Einstiege mehr, bis Kiron per PR einen neuen Start einträgt. Ausstiege und Stops laufen weiter.

Zugangsdaten nur aus Umgebungsvariablen (GitHub-Secrets): CAPITAL_API_KEY, CAPITAL_IDENTIFIER,
CAPITAL_API_PASSWORD. Live-Handel gibt es hier nicht.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from gold.backtest.pine_port import signals_b_short, signals_c_long
from gold.backtest.sizing import atr_rma
from gold.bot import konten, schalter
from gold.bot.capital import CapitalClient, CapitalError
from gold.bot.rules import (Account, GoldLimits, Quote, Signals, bars_from_prices, catch_up, decide,
                            last_bar_is_current, roll_account_marks, stop_level)
from ops.notify import Notifier

ROOT = Path(__file__).resolve().parents[2]
MIN_BARS = 300                         # Trend-EMA 200 plus Vorlauf der Vix-Fix-Bänder
CHART_BARS = 500                       # so viele Stundenkerzen landen in journal/gold-chart.json


def read_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def quote_for(client: CapitalClient, epic: str, currency: str) -> Quote:
    market = client.market(epic)
    snap, inst = market["snapshot"], market.get("instrument", {})
    rate = float(inst.get("marginFactor", 5))
    margin_rate = rate / 100 if inst.get("marginFactorUnit", "PERCENTAGE") == "PERCENTAGE" else 0.05
    if currency == "USD":
        fx = 1.0
    elif currency == "EUR":
        eur = client.market("EURUSD")["snapshot"]
        fx = (float(eur["bid"]) + float(eur["offer"])) / 2
    else:
        raise CapitalError(f"Kontowährung {currency} wird nicht unterstützt, nur EUR oder USD")
    return Quote(bid=float(snap["bid"]), offer=float(snap["offer"]), eurusd=fx, margin_rate=margin_rate,
                 oz_per_contract=float(inst.get("lotSize", 1) or 1), tradeable=snap.get("marketStatus") == "TRADEABLE")


def execute(client: CapitalClient, decision, deal_id: str | None, limits: GoldLimits, quote: Quote) -> list[dict]:
    results = []
    if decision.action in ("close", "reverse"):
        res = client.close_position(deal_id)
        results.append({"step": "close", "dealStatus": res.get("dealStatus"), "level": res.get("level")})
        if res.get("dealStatus") != "ACCEPTED":
            return results
    if decision.action in ("open", "reverse"):
        stop = stop_level(decision.side, quote, limits.stop_usd)
        res = client.open_position(limits.epic, "BUY" if decision.side > 0 else "SELL", limits.size, stop)
        results.append({"step": "open", "dealStatus": res.get("dealStatus"), "level": res.get("level"),
                        "dealId": res.get("dealId"), "stopLevel": round(stop, 2)})
    return results


def _num(value) -> float | None:
    return None if value is None else round(float(value), 2)


def chart_position(raw: dict | None) -> dict | None:
    """Capital.com-Position -> kleiner Eintrag für den Chart. None, wenn keine Gold-Position offen ist."""
    if not raw:
        return None
    pos = raw.get("position", {})
    direction = pos.get("direction")
    return {"side": "long" if direction == "BUY" else "short", "direction": direction,
            "entry": _num(pos.get("level")), "size": _num(pos.get("size")), "stop": _num(pos.get("stopLevel")),
            "dealId": pos.get("dealId"), "opened_utc": pos.get("createdDateUTC"), "upl": _num(pos.get("upl"))}


def chart_snapshot(bars: pd.DataFrame, position: dict | None, now: datetime, limits: GoldLimits,
                   environment: str, equity: float, currency: str) -> dict:
    """Inhalt von journal/gold-chart.json (format 1).

    bars: Liste von [Zeit, Open, High, Low, Close], älteste zuerst, nur fertige Kerzen, Bid-Kurse in USD.
    Zeit = Beginn der Kerze in UTC, geschrieben wie das Feld "bar" in gold-decisions.jsonl
    ("2026-10-30 20:00:00"). Eine Entscheidung auf Kerze X wird zum Eröffnungskurs der Kerze danach
    ausgeführt. position: offene Gold-Position nach diesem Lauf oder null."""
    tail = bars.tail(CHART_BARS)
    return {"format": 1, "updated_utc": now.isoformat(timespec="seconds"), "environment": environment,
            "epic": limits.epic, "timeframe": limits.timeframe, "price": "bid",
            "columns": ["time_utc", "open", "high", "low", "close"],
            "bars": [[str(t), *(round(float(v), 2) for v in row)]
                     for t, row in zip(tail.index, tail[["open", "high", "low", "close"]].to_numpy())],
            "position": position, "account": {"equity": round(equity, 2), "currency": currency}}


def write_chart(journal_dir: Path, bars: pd.DataFrame, after: list[dict], now: datetime, limits: GoldLimits,
                environment: str, equity: float, currency: str) -> None:
    """Schreibt journal/gold-chart.json. Ein Fehler hier stoppt den Lauf nie, die Order ist dann schon raus."""
    try:
        snap = chart_snapshot(bars, chart_position(after[0] if after else None), now, limits, environment,
                              equity, currency)
        (journal_dir / "gold-chart.json").write_text(json.dumps(snap, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception as err:           # noqa: BLE001 - der Chart ist Beiwerk
        print(f"Chart-Datei nicht geschrieben: {err}")


REASONS = {"SL": "Stop beim Broker", "TP": "Ziel beim Broker", "USER": "von Hand geschlossen",
           "CLOSE_OUT": "Zwangsschließung (zu wenig Margin)"}


def trade_entry(trade: dict, exit_level, now: datetime, exit_bar: str | None, reason: str,
                estimated: bool = False, broker=None) -> dict:
    """Eine Zeile in journal/gold-trades.jsonl (ein abgeschlossener Trade).

    side long|short, size Unzen, entry/exit Füllkurse in USD (inklusive Spread), opened_utc/closed_utc,
    entry_bar/exit_bar = Kerze der Entscheidung wie "bar" im Journal (exit_bar null, wenn der Broker
    geschlossen hat), reason, pnl_usd = (exit - entry) x Richtung x Größe, r = pnl_usd / Abstand zum Stop,
    strategy C (long) oder B (short), pnl_eur ungefähr (pnl_usd / EURUSD des Laufs), balance_after_eur =
    Kontostand nach dem Trade (Broker-Schließung: genau, vom Bot geschlossen: Kontostand + pnl_eur),
    exit_estimated = true, wenn der Schlusskurs geschätzt ist (dann der Stop-Kurs), broker = gekürzte
    Kontoaktivität zur Kontrolle."""
    side = 1 if trade.get("side") == "long" else -1
    entry, size, stop = trade.get("entry"), float(trade.get("size") or 1.0), trade.get("stop")
    pnl = None if entry is None or exit_level is None else round((float(exit_level) - float(entry)) * side * size, 2)
    risk = None if entry is None or stop is None else abs(float(entry) - float(stop)) * size
    rec = {"dealId": trade.get("dealId"), "side": trade.get("side"), "strategy": "C" if side > 0 else "B",
           "size": size, "entry": entry,
           "opened_utc": trade.get("opened_utc"), "entry_bar": trade.get("bar"), "stop": stop,
           "exit": None if exit_level is None else round(float(exit_level), 2),
           "closed_utc": now.isoformat(timespec="seconds"), "exit_bar": exit_bar, "reason": reason,
           "pnl_usd": pnl, "r": round(pnl / risk, 2) if pnl is not None and risk else None, "pnl_eur": None,
           "balance_after_eur": None, "exit_estimated": estimated}
    if broker is not None:
        rec["broker"] = broker
    return rec


_EPOCH = datetime.fromtimestamp(0, timezone.utc).replace(tzinfo=None)


def _utc(text) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo is None else t.astimezone(timezone.utc).replace(tzinfo=None)


def close_activity(raw: list[dict], opened_utc: str | None) -> dict | None:
    """Die Schluss-Aktivität einer Position aus der Kontoaktivität (neueste zuerst oder ungeordnet).

    Die Eröffnung durch den Bot steht dort auch, mit source USER und dem Einstiegskurs. Sie darf nie als
    Schluss gelten (Fehler am 03.11.2026: Stop bei 3960,45 wurde als "von Hand geschlossen" zum
    Einstiegskurs gebucht). Deshalb: zuerst eindeutige Schlüsse (POSITION_CLOSED, SL, TP, CLOSE_OUT),
    sonst USER erst deutlich nach der Eröffnung; ohne Eröffnungszeit zählt die älteste USER-Zeile als
    Eröffnung."""
    rows = [a for a in raw if a.get("level") is not None and a.get("status", "ACCEPTED") == "ACCEPTED"
            and a.get("type", "POSITION") == "POSITION"]
    rows.sort(key=lambda a: _utc(a.get("dateUTC")) or _EPOCH, reverse=True)
    clear = [a for a in rows if "POSITION_CLOSED" in (a.get("actions") or []) or a.get("source") in ("SL", "TP", "CLOSE_OUT")]
    if clear:
        return clear[0]
    user = [a for a in rows if a.get("source") == "USER"]
    opened = _utc(opened_utc) if opened_utc else None
    if opened is not None:
        later = [a for a in user if (_utc(a.get("dateUTC")) or _EPOCH) > opened + timedelta(seconds=5)]
    else:
        later = user[:-1]
    return later[0] if later else None


def closed_outside(client: CapitalClient, trade: dict, now: datetime) -> dict:
    """Die Position aus dem letzten Lauf ist weg, ohne dass der Bot sie geschlossen hat (meist der Notfall-Stop).
    Schlusskurs und Grund aus der Kontoaktivität; klappt das nicht, gilt der Stop-Kurs als Schätzung."""
    level, source, raw = None, None, None
    try:
        acts = client.activity(trade["dealId"], now - timedelta(hours=23, minutes=59), now)
        raw = [{"dateUTC": a.get("dateUTC"), "source": a.get("source"), "type": a.get("type"),
                "status": a.get("status"), "level": (a.get("details") or {}).get("level"),
                "actions": [x.get("actionType") for x in (a.get("details") or {}).get("actions", [])]} for a in acts]
        close = close_activity(raw, trade.get("opened_utc"))
        if close:
            level, source = close["level"], close["source"]
    except Exception as err:           # noqa: BLE001 - dann eben geschätzt
        raw = f"Kontoaktivität nicht lesbar: {err}"
    estimated = level is None
    return trade_entry(trade, trade.get("stop") if estimated else level, now, None,
                       REASONS.get(source, "beim Broker geschlossen"), estimated=estimated, broker=raw)


def open_trade_after(after: list[dict] | None, previous: dict | None, results: list[dict], side: int,
                     limits: GoldLimits, last: str) -> dict | None:
    """Was in gold-state.json als offene Position steht: frisch vom Broker, sonst aus der Order-Antwort."""
    if after is not None:
        if not after:
            return None
        pos = chart_position(after[0])
        same = previous and previous.get("dealId") == pos["dealId"]
        return {**pos, "bar": previous.get("bar") if same else last}
    opened = next((r for r in results if r.get("step") == "open" and r.get("dealStatus") == "ACCEPTED"), None)
    if opened:
        return {"side": "long" if side > 0 else "short", "direction": "BUY" if side > 0 else "SELL",
                "entry": opened.get("level"), "size": limits.size, "stop": opened.get("stopLevel"),
                "dealId": opened.get("dealId"), "opened_utc": None, "upl": None, "bar": last}
    closed = any(r.get("step") == "close" and r.get("dealStatus") == "ACCEPTED" for r in results)
    return None if closed else previous


def run(client: CapitalClient, limits: GoldLimits, journal_dir: Path, now: datetime,
        notify=print, send_orders: bool = True) -> dict | None:
    client.login()
    # Eigene Konten je Bot (gold/bot/konten.py): der Gold-Bot handelt immer auf dem Hauptkonto, auch wenn ein anderes
    # Konto gerade das bevorzugte ist (aus journal/konten.json, sonst die bekannte Konto-Endung, sonst das aktive).
    accounts = client.accounts()
    haupt = konten.haupt_von(accounts, konten.load(journal_dir), getattr(client, "account_id", None))
    if haupt and len(accounts) > 1:
        konten.wechseln(client, haupt)
    account = (next((a for a in accounts if haupt and str(a.get("accountId")) == str(haupt)), None)
               or next((a for a in accounts if a.get("preferred")), None) or accounts[0])
    currency = account.get("currency", "EUR")
    bars, spread = bars_from_prices(client.prices(limits.epic, "HOUR", 1000), now, limits.timeframe)
    if not last_bar_is_current(bars, now, limits.timeframe):
        print(f"Keine frische Kerze (letzte: {bars.index[-1] if len(bars) else 'keine'}), nichts zu tun")
        return None
    if len(bars) < MIN_BARS:
        raise CapitalError(f"Nur {len(bars)} Kerzen, für die Signale braucht es {MIN_BARS}")
    state_path = journal_dir / "gold-state.json"
    previous = read_json(state_path, {})
    last = bars.index[-1]
    if send_orders and previous.get("last_bar") == str(last):
        print(f"Kerze {last} ist schon verarbeitet, nichts zu tun")
        return None

    atr14 = float(atr_rma(bars, 14)[-1])
    if limits.stop_atr and atr14 > 0:  # wie Runde 2 im Backtest: Vielfaches der ATR(14) der Signalkerze
        limits = replace(limits, stop_usd=round(float(limits.stop_atr) * atr14, 2))
    c, b = signals_c_long(bars, useTrend=True), signals_b_short(bars, useTrend=True)
    sig = Signals(bool(c["entry"].iloc[-1]), bool(c["exit"].iloc[-1]),
                  bool(b["entry"].iloc[-1]), bool(b["exit"].iloc[-1]))
    table = pd.DataFrame({"long_entry": c["entry"], "long_exit": c["exit"],
                          "short_entry": b["entry"], "short_exit": b["exit"]}).astype(bool)
    done = pd.Timestamp(previous["last_bar"]) if previous.get("last_bar") else last
    missed = table[(table.index > done) & (table.index < last)]

    gold = [p for p in client.positions() if p.get("market", {}).get("epic") == limits.epic]
    if len(gold) > 1:
        notify(f"Gold-Bot: {len(gold)} Gold-Positionen offen, erwartet ist höchstens eine. Kein Handel, bitte prüfen.")
        return None
    position = 0 if not gold else (1 if gold[0]["position"]["direction"] == "BUY" else -1)
    deal_id = gold[0]["position"]["dealId"] if gold else None
    sig, notes = catch_up(sig, position, missed)
    trades = []                        # abgeschlossene Trades dieses Laufs -> journal/gold-trades.jsonl
    prev_trade = previous.get("open_trade")
    if send_orders and prev_trade and prev_trade.get("dealId") not in {p["position"].get("dealId") for p in gold}:
        trades.append(closed_outside(client, prev_trade, now))

    bal = account["balance"]
    balance, upl, available = float(bal["balance"]), float(bal.get("profitLoss", 0)), float(bal["available"])
    state = roll_account_marks(previous, balance + upl, balance, now)
    if send_orders:
        state["last_bar"] = str(last)
    acc = Account(equity_eur=balance + upl, balance_eur=balance, available_eur=available,
                  peak_eur=state["peak_eur"], day_start_eur=state["day_start_eur"],
                  week_start_eur=state["week_start_eur"])
    quote = quote_for(client, limits.epic, currency)
    # Sicherheitsschalter (Kritik D4, gold/bot/VORAB_sicherheit.yaml): rechnet jedes Mal neu aus dem Trade-Journal,
    # einschließlich der Trades, die der Broker seit dem letzten Lauf geschlossen hat.
    stand = schalter.pruefen(schalter.lese_trades(journal_dir / "gold-trades.jsonl") + trades,
                             schalter.gesiegelte_regel())
    decision = decide(sig, position, limits, acc, quote, pause=stand.grund)
    decision.reasons = notes + decision.reasons
    if send_orders:
        if stand.pause and not previous.get("schalter_pause"):
            notify(f"Gold-Bot: {stand.grund}. Offene Positionen laufen mit ihrem Stop weiter.")
        state["schalter_pause"] = stand.grund

    record = {"time": now.isoformat(timespec="seconds"), "bar": str(last), "close_bid": bars["close"].iloc[-1],
              "spread": round(float(spread.iloc[-1]), 3), "signals": sig.__dict__, "position": position,
              "missed_bars": len(missed), "equity": round(acc.equity_eur, 2), "currency": currency,
              "stage": limits.stage, "action": decision.action, "side": decision.side, "reasons": decision.reasons,
              "stop_usd": limits.stop_usd, "atr14": round(atr14, 2), "schalter": stand.journal()}
    if decision.action != "none":
        if limits.stage >= 1 and send_orders:
            record["results"] = execute(client, decision, deal_id, limits, quote)
            done_close = next((r for r in record["results"]
                               if r["step"] == "close" and r.get("dealStatus") == "ACCEPTED"), None)
            if done_close and gold:
                trades.append(trade_entry({**chart_position(gold[0]), "bar": (prev_trade or {}).get("bar")},
                                          done_close.get("level"), now, str(last),
                                          "Gegensignal" if decision.action == "reverse" else "Ausstiegssignal"))
        else:
            record["results"] = [{"step": "nicht gesendet", "why": f"Stufe {limits.stage} oder Trockenlauf"}]
        notify(f"Gold-Bot ({client.environment}): {decision.action} "
               f"{'long' if decision.side > 0 else 'short' if decision.side < 0 else ''} bei {quote.bid:.2f}, "
               f"Ergebnis {record['results']}")
    elif decision.reasons and (sig.long_entry or sig.short_entry):
        notify(f"Gold-Bot: Einstiegssignal nicht genutzt: {'; '.join(decision.reasons)}")

    sent = decision.action != "none" and limits.stage >= 1 and send_orders
    after: list[dict] | None = gold
    if sent:                           # nach einer Order die Position frisch beim Broker lesen
        try:
            after = [p for p in client.positions() if p.get("market", {}).get("epic") == limits.epic]
        except Exception as err:       # noqa: BLE001 - die Order ist raus, der Lauf darf jetzt nicht abbrechen
            print(f"Positionen nach der Order nicht lesbar: {err}")
            after = None
    if send_orders:
        state["open_trade"] = open_trade_after(after, prev_trade, record.get("results", []), decision.side,
                                               limits, str(last))
    for t in trades:
        t["pnl_eur"] = None if t["pnl_usd"] is None else round(t["pnl_usd"] / quote.eurusd, 2)
        by_bot = t["exit_bar"] is not None
        t["balance_after_eur"] = round(balance + (t["pnl_eur"] or 0.0), 2) if by_bot else round(balance, 2)
        notify(f"Gold-Bot: {t['side']} geschlossen ({t['reason']}) bei {t['exit']}, "
               f"Ergebnis {t['pnl_usd']} $ (etwa {t['pnl_eur']} {currency})")
    if trades:
        record["trades_closed"] = len(trades)

    journal_dir.mkdir(parents=True, exist_ok=True)
    if trades:
        with open(journal_dir / "gold-trades.jsonl", "a", encoding="utf-8") as fh:
            for t in trades:
                fh.write(json.dumps(t, ensure_ascii=False, default=str) + "\n")
    state_path.write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")
    if decision.action != "none" or decision.reasons or sig.long_entry or sig.short_entry or trades:
        with open(journal_dir / "gold-decisions.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    write_chart(journal_dir, bars, after if after is not None else gold, now, limits,
                getattr(client, "environment", "demo"), acc.equity_eur, currency)
    return record


CRED_KEYS = ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_API_PASSWORD")


def clean_credentials(raw: dict[str, str]) -> list[str]:
    """Beim Einfügen in GitHub rutscht leicht ein Leerzeichen oder Zeilenumbruch mit. Schlüssel und E-Mail
    werden ganz bereinigt, beim Passwort nur Zeilenumbrüche, ein Leerzeichen dort könnte Absicht sein."""
    key, identifier, password = (raw.get(k) or "" for k in CRED_KEYS)
    return [key.strip(), identifier.strip(), password.strip("\r\n")]


def login_hints(raw: dict[str, str]) -> list[str]:
    """Was an den Zugangsdaten auffällt, wenn Capital.com den Login ablehnt. Nennt nie einen Wert."""
    key, identifier, password = (raw.get(k) or "" for k in CRED_KEYS)
    clean = clean_credentials(raw)
    hints = [f"{name} hatte Leerzeichen oder Zeilenumbruch am Rand, ist für diesen Lauf entfernt"
             for name, before, after in zip(CRED_KEYS, (key, identifier, password), clean) if before != after]
    login = clean[1].lower()
    if "@" not in login:
        hints.append("CAPITAL_IDENTIFIER ist keine E-Mail-Adresse, Capital.com erwartet die Login-E-Mail")
    if login.endswith("privaterelay.appleid.com"):
        hints.append("CAPITAL_IDENTIFIER ist eine Apple-Weiterleitungsadresse, nimm genau die E-Mail aus dem Capital.com-Profil")
    if clean[2] in (clean[0], clean[1]):
        hints.append("CAPITAL_API_PASSWORD ist gleich dem Schlüssel oder der E-Mail, gemeint ist das eigene Passwort des Schlüssels")
    hints.append(f"CAPITAL_API_KEY hat {len(clean[0])} Zeichen")
    return hints


def main(argv: list[str]) -> int:
    raw = {k: os.environ.get(k, "") for k in CRED_KEYS}
    creds = clean_credentials(raw)
    if not all(creds):
        print("Keine Capital.com-Zugangsdaten in der Umgebung, Gold-Bot übersprungen")
        return 0
    limits = GoldLimits.load()
    client = CapitalClient(*creds, environment="demo")
    try:
        record = run(client, limits, ROOT / "journal", datetime.now(timezone.utc), Notifier(),
                     send_orders="--dry-run" not in argv)
    except CapitalError as err:
        if "/session -> 401" in str(err):
            print("Capital.com lehnt den Login ab. Prüfen: Demokonto vorhanden, Schlüssel nicht pausiert, "
                  "Passwort ist das des Schlüssels.")
            for hint in login_hints(raw):
                print("Hinweis:", hint)
        raise
    print(json.dumps(record, ensure_ascii=False, default=str) if record else "kein Eintrag")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
