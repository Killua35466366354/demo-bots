"""Was der Gold-Bot nach jedem fertigen Balken tut. Reiner Code ohne Netz, damit er testbar ist.

Die Regeln sind dieselben wie in `gold/backtest/engine.py::run_live` (Schritt 3, Signale auf dem
Schlusskurs): eine Position gleichzeitig, kein Nachkaufen, Gegensignal nach `conflict`, Tages-,
Wochen- und Not-Aus-Limit sperren nur neue Einstiege, ebenso der Sicherheitsschalter (gold/bot/schalter.py).
Der Notfall-Stop liegt als Stop-Order beim Broker.

Limits kommen aus dem Abschnitt `gold:` in config/limits.yaml. Den Abschnitt schreibt nur Kiron.
Fehlt er, läuft der Bot in Stufe 0: er rechnet und schreibt ins Journal, sendet aber keine Order.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml

DEFAULT_LIMITS = Path(__file__).resolve().parents[2] / "config" / "limits.yaml"


@dataclass(frozen=True)
class GoldLimits:
    stage: int = 0                     # 0 = nur rechnen, 1 = Demo-Orders, Live gibt es hier nicht
    epic: str = "GOLD"
    size: float = 1.0                  # Kontrakte, höchstens (siehe trade_size); mal lotSize des Instruments = Unzen
    stop_usd: float = 5.6              # Notfall-Stop, Abstand zum Einstiegskurs
    stop_atr: float | None = None      # gesetzt: Stop = stop_atr x ATR(14) der Signalkerze statt stop_usd
    risk_per_trade_pct: float = 2.0    # Stop-Abstand mal Unzen darf höchstens so viel vom Konto kosten: Kostet
                                       # `size` mehr, handelt der Bot kleiner (trade_size), er lässt das Signal nicht aus
    day_loss_pct: float = 4.0
    week_loss_pct: float = 8.0
    kill_dd_pct: float = 25.0          # unter dem Höchststand des Gold-Kontos: keine neuen Einstiege mehr
    conflict: str = "first"            # first = Gegensignal ignorieren, reverse = umdrehen
    sides: tuple[str, ...] = ("long", "short")
    max_spread_usd: float = 1.0
    timeframe: str = "60min"

    @classmethod
    def load(cls, path: Path | str = DEFAULT_LIMITS) -> GoldLimits:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        gold = raw.get("gold")
        if not gold:
            return cls()
        known = {k: v for k, v in gold.items() if k in cls.__dataclass_fields__}
        if "sides" in known:
            known["sides"] = tuple(known["sides"])
        limits = cls(**known)
        if limits.conflict not in ("first", "reverse"):
            raise ValueError(f"conflict muss first oder reverse sein, nicht {limits.conflict}")
        if not set(limits.sides) <= {"long", "short"}:
            raise ValueError(f"sides darf nur long und short enthalten: {limits.sides}")
        if limits.stop_atr is not None and not 0 < float(limits.stop_atr) <= 3:
            raise ValueError(f"stop_atr muss zwischen 0 und 3 liegen, nicht {limits.stop_atr}")
        if limits.timeframe != "60min":
            raise ValueError("Getestet ist nur der 60-Minuten-Chart mit Trendfilter, timeframe muss 60min sein")
        return limits


@dataclass(frozen=True)
class Signals:
    long_entry: bool
    long_exit: bool
    short_entry: bool
    short_exit: bool


@dataclass(frozen=True)
class Account:
    equity_eur: float                  # mit offenem Gewinn oder Verlust
    balance_eur: float                 # nur abgeschlossene Trades, wie `eq` im Backtest
    available_eur: float
    peak_eur: float
    day_start_eur: float
    week_start_eur: float


@dataclass(frozen=True)
class Quote:
    bid: float
    offer: float
    eurusd: float
    margin_rate: float                 # 0.05 bei Hebel 1:20
    oz_per_contract: float = 1.0
    tradeable: bool = True
    min_size: float = 0.01             # kleinste Ordergröße des Brokers in Kontrakten
    size_step: float = 0.01            # Schrittweite der Ordergröße


@dataclass
class Decision:
    action: str                        # none, open, close, reverse
    side: int = 0                      # Richtung der neuen Position: +1 long, -1 short
    reasons: list[str] = field(default_factory=list)
    size: float = 0.0                  # Kontrakte der neuen Position (bei open und reverse), sonst 0


def bars_from_prices(prices: list[dict], now: datetime, timeframe: str = "60min") -> tuple[pd.DataFrame, pd.Series]:
    """Capital.com-Kerzen -> Bid-OHLC und Spread. Die noch laufende Kerze fällt weg."""
    if not prices:
        empty = pd.DataFrame(columns=["open", "high", "low", "close"], index=pd.DatetimeIndex([], name="time"))
        return empty.astype(float), pd.Series(dtype=float)
    rows = [{"time": pd.Timestamp(p["snapshotTimeUTC"]),
             "open": p["openPrice"]["bid"], "high": p["highPrice"]["bid"],
             "low": p["lowPrice"]["bid"], "close": p["closePrice"]["bid"],
             "spread": p["closePrice"]["ask"] - p["closePrice"]["bid"]} for p in prices]
    df = pd.DataFrame(rows).set_index("time").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    done = df.index + pd.Timedelta(timeframe) <= pd.Timestamp(now).tz_localize(None)
    df = df[done]
    return df[["open", "high", "low", "close"]].astype(float), df["spread"].astype(float)


def last_bar_is_current(bars: pd.DataFrame, now: datetime, timeframe: str = "60min") -> bool:
    """Nur handeln, wenn die letzte fertige Kerze die gerade abgeschlossene ist (keine alten Signale)."""
    if bars.empty:
        return False
    expected = pd.Timestamp(now).tz_localize(None).floor(timeframe) - pd.Timedelta(timeframe)
    return bars.index[-1] == expected


def trade_size(limits: GoldLimits, account: Account, quote: Quote) -> float:
    """Kontrakte für den nächsten Einstieg: `limits.size`, aber nie so viel, dass der Stop mehr als
    `risk_per_trade_pct` des Kontos kostet. Dann handelt der Bot kleiner, abgerundet auf die Schrittweite des Brokers.
    Rückgabe 0, wenn schon die kleinste Ordergröße zu teuer wäre.

    Kirons Wahl vom 11.11.2026 09:42 UTC ("Ja, kleiner handeln"). Vorher fiel das ganze Signal weg, sobald 1 Kontrakt
    mehr als 2 % kostete (journal/gold-decisions.jsonl, 05.11.2026 17:11 UTC: 20,40 € statt 19,90 €). Der Backtest
    (gold/backtest/engine.py run_live) kennt diese Sperre nicht, er nimmt jedes Signal. Einstieg, Stop und Ausstieg
    bleiben, wie sie sind; das Risiko je Trade wird nie größer als vorher."""
    step = quote.size_step if quote.size_step > 0 else 0.01
    erlaubt = account.equity_eur * limits.risk_per_trade_pct / 100
    je_kontrakt = limits.stop_usd * quote.oz_per_contract / quote.eurusd
    if je_kontrakt <= 0 or je_kontrakt * limits.size <= erlaubt:
        return float(limits.size)
    size = round(math.floor(erlaubt / je_kontrakt / step + 1e-9) * step, 8)
    return size if size >= quote.min_size - 1e-12 else 0.0


def entry_blocks(limits: GoldLimits, account: Account, quote: Quote, side: int) -> list[str]:
    """Gründe, warum gerade kein neuer Einstieg erlaubt ist. Leer = erlaubt."""
    blocks = []
    if account.balance_eur < account.day_start_eur * (1 - limits.day_loss_pct / 100):
        blocks.append(f"Tageslimit: Konto mehr als {limits.day_loss_pct:g} % unter dem Tagesbeginn")
    if account.balance_eur < account.week_start_eur * (1 - limits.week_loss_pct / 100):
        blocks.append(f"Wochenlimit: Konto mehr als {limits.week_loss_pct:g} % unter dem Wochenbeginn")
    if account.equity_eur < account.peak_eur * (1 - limits.kill_dd_pct / 100):
        blocks.append(f"Not-Aus: Konto mehr als {limits.kill_dd_pct:g} % unter dem Höchststand "
                      f"({account.peak_eur:.2f} €), nur Kiron kann es zurücksetzen")
    if not quote.tradeable:
        blocks.append("Markt ist gerade nicht handelbar")
    spread = quote.offer - quote.bid
    if spread > limits.max_spread_usd:
        blocks.append(f"Spread {spread:.2f} $ über der Grenze von {limits.max_spread_usd:.2f} $")
    size = trade_size(limits, account, quote)
    oz = (size or quote.min_size) * quote.oz_per_contract
    price = quote.offer if side > 0 else quote.bid
    margin = price * oz * quote.margin_rate / quote.eurusd
    if margin > account.available_eur:
        blocks.append(f"Margin {margin:.2f} € nötig, nur {account.available_eur:.2f} € frei")
    if not size:                       # selbst die kleinste Ordergröße kostet mehr als erlaubt
        risk = limits.stop_usd * oz / quote.eurusd
        blocks.append(f"Stop kostet {risk:.2f} € schon bei der kleinsten Größe {quote.min_size:g}, erlaubt sind "
                      f"{limits.risk_per_trade_pct:g} % = {account.equity_eur * limits.risk_per_trade_pct / 100:.2f} €")
    return blocks


def decide(sig: Signals, position: int, limits: GoldLimits, account: Account, quote: Quote,
           pause: str | None = None) -> Decision:
    """position: +1 long, -1 short, 0 flach (laut Broker). Abgeschaltete Seiten zählen nicht als Signal.
    pause: Grund des Sicherheitsschalters (gold/bot/schalter.py), sperrt wie die Limits nur neue Einstiege."""
    sig = Signals(sig.long_entry and "long" in limits.sides, sig.long_exit,
                  sig.short_entry and "short" in limits.sides, sig.short_exit)
    if position == 0:
        if sig.long_entry and sig.short_entry:
            return Decision("none", reasons=["Long- und Short-Signal gleichzeitig, kein Einstieg"])
        if not (sig.long_entry or sig.short_entry):
            return Decision("none")
        want = 1 if sig.long_entry else -1
        blocks = ([pause] if pause else []) + entry_blocks(limits, account, quote, want)
        if blocks:
            return Decision("none", reasons=blocks)
        return Decision("open", want, size=trade_size(limits, account, quote))

    own_exit = sig.long_exit if position > 0 else sig.short_exit
    same_in = sig.long_entry if position > 0 else sig.short_entry
    other_in = sig.short_entry if position > 0 else sig.long_entry
    if own_exit:
        return Decision("close", reasons=["Ausstiegssignal der eigenen Strategie"])
    if other_in and limits.conflict == "reverse":
        blocks = ([pause] if pause else []) + entry_blocks(limits, account, quote, -position)
        if not blocks:
            return Decision("reverse", -position, ["Gegensignal, Regel reverse"],
                            size=trade_size(limits, account, quote))
        return Decision("none", reasons=["Gegensignal, Umdrehen gesperrt"] + blocks)
    if other_in:
        return Decision("none", reasons=["Gegensignal, Regel first: Position bleibt"])
    if same_in:
        return Decision("none", reasons=["Weiteres Signal in dieselbe Richtung, kein Nachkaufen"])
    return Decision("none")


def catch_up(sig: Signals, position: int, missed: pd.DataFrame) -> tuple[Signals, list[str]]:
    """GitHub lässt geplante Läufe manchmal ausfallen. Dann liegen fertige Kerzen zwischen dem letzten Lauf
    und jetzt (`missed`: Spalten long_entry, long_exit, short_entry, short_exit, eine Zeile pro Kerze).
    Ein Ausstiegssignal der offenen Position auf einer davon zählt jetzt noch, nur später als im Backtest.
    Verpasste Einstiege holt der Bot nicht nach, sie stehen nur im Journal."""
    notes: list[str] = []
    if missed.empty:
        return sig, notes
    own = "long_exit" if position > 0 else "short_exit" if position < 0 else None
    if own and missed[own].any():
        notes.append(f"Ausstiegssignal der Kerze {missed.index[missed[own].to_numpy(bool)][0]} verpasst, jetzt nachgeholt")
        sig = replace(sig, **{own: True})
    entries = missed.index[(missed["long_entry"] | missed["short_entry"]).to_numpy(bool)]
    if len(entries):
        notes.append(f"Einstiegssignal der Kerze {entries[-1]} verpasst (Lauf ausgefallen), nicht nachgeholt")
    return sig, notes


def stop_level(side: int, quote: Quote, stop_usd: float) -> float:
    """Long kauft zum Offer, Stop darunter. Short verkauft zum Bid, Stop darüber."""
    return quote.offer - stop_usd if side > 0 else quote.bid + stop_usd


def roll_account_marks(state: dict, equity_eur: float, balance_eur: float, now: datetime) -> dict:
    """Höchststand (mit offenem Ergebnis), Tages- und Wochenbeginn (abgeschlossene Trades) fortschreiben.
    UTC-Tage, Wochen ab Montag, wie im Backtest."""
    day = now.date().isoformat()
    week = (now.date() - timedelta(days=now.weekday())).isoformat()
    out = dict(state)
    out["peak_eur"] = round(max(float(state.get("peak_eur", equity_eur)), equity_eur), 2)
    if state.get("day") != day:
        out["day"], out["day_start_eur"] = day, round(balance_eur, 2)
    if state.get("week") != week:
        out["week"], out["week_start_eur"] = week, round(balance_eur, 2)
    return out
