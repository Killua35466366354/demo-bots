"""Die Demo-Bots aus Runde 6, jeder auf seinem eigenen Capital.com-DEMOKONTO. Nie echtes Geld.

Kirons Wahl vom 04.11.2026: "Soll die USD/JPY-Regel auf einem eigenen Demokonto probehandeln?" -> "Ja, plus EUR/GBP-USD
mitschreiben"; danach "lasse 2 und 3 auch bestehen". Die Regeln stehen in suche/r6_regeln.py (gegen den Backtest
nachgespielt: suche/r6_nachspiel.py), der Vorwärtstest ist vorab festgelegt in suche/VORAB_r6_demo.yaml.

- Platz 1, Vortageshoch/-tief USD/JPY (bestanden): ab 4:31 New York zwei Stop-Orders beim Broker (Kauf am Vortageshoch
  plus Spread, Verkauf am Vortagestief), Stop 10 % und Ziel 25 % der Vortagesspanne als feste Kurse, gültig bis 16:30
  New York. Löst eine aus, löscht der Bot im nächsten Lauf die andere. Raus im Lauf um 16:46 New York. Beendet am
  04.11.2026 vor dem ersten Trade (Vergleich 2025 bis heute: Gewinnfaktor 0,95); sein Konto geht an Vortag GBP/USD.
- Platz 2, London-Stunde GBP/USD (knapp nicht bestanden): Long per Marktorder zur vollen Stunde, Stop am Bereichstief,
  Ziel 1,5 x Risiko, raus um 17 Uhr London. Nur bei ruhigem Markt (Schwankung bis 0,876).
- Platz 3, Noise-Band USD/JPY (knapp nicht bestanden): Long oder Short per Marktorder zur halben Stunde, raus beim
  Gegensignal oder um 17 Uhr London. Im Backtest ohne Stop; beim Broker liegt ein Notstop von 2 x Tages-ATR(14).
- Vortageshoch/-tief EUR/USD und GBP/USD: dieselbe Regel und derselbe Code wie USD/JPY. Bis 04.11.2026 nur Schatten
  (Zwilling ohne Order). Beim Vergleich aller Strategien 2025 bis heute (Kirons Wunsch vom 04.11.2026: "tue alle
  strategien gleich auswerten ... und dann wählen") lagen sie vorn. Sie handeln nur, wenn journal/konten.json ihnen ein
  Konto zuordnet; ein Konto über den Namen nehmen sie sich nie. Stop seit 04.11.2026 (Kirons Wahl nach der Stop-Wahl,
  VORAB_r6_demo.yaml nachtrag_vortag_stop_2026_11_04): 0,5 x ATR(14) der Viertelstunden-Kerzen beim Legen der
  Stop-Orders statt 10 % der Vortagesspanne. Liegt er näher als der Mindestabstand des Brokers, rückt er auf 1,05 x
  Mindestabstand. Verpasster Ausbruch (Kiron 04.11.2026 13:53 UTC: "dann nimm den halt einfach ... zu spät"): Lagen
  noch keine Stop-Orders, holt der Bot den Ausbruch bis 65 Minuten nach Beginn der Ausbruchskerze per Marktorder nach,
  mit denselben Stop- und Zielkursen, solange beide noch nicht erreicht sind (nachtrag_vortag_nachholen_2026_11_04).

Größe: höchstens 1 % des Kontostands und höchstens 10 Euro Risiko bis zum Stop, mindestens die kleinste Ordergröße
(wenn die nicht mehr als 10 Euro riskiert); die Margin darf höchstens die Hälfte des freien Gelds brauchen.

Konto: das Konto, das journal/konten.json dem Bot zuordnet, sonst ein Konto, dessen Name zum Bot passt ("Vortag",
"London" oder "GBPUSD", "Noise"); nie das Hauptkonto (Gold-Bot) und nie ein Konto, das schon einem anderen Bot gehört.
Seit dem 04.11.2026 ist bei Capital.com die Höchstzahl an Demokonten erreicht. Der Lauf der Demo-Bots
(suche/demo_bots.py) gibt dann Konten beendeter Bots weiter, sobald dort nichts mehr offen ist, und schreibt sie unter
zuordnung ein (welcher Bot welches Konto bekommt, entscheidet Kiron nach dem Vergleich aller Strategien). Ohne Konto
wartet der Bot. Ein Konto unter frei (abgelöst ohne Nachfolger) nimmt sich ein Bot nie; das vergibt die Prüfung.

Automatischer Wechsel (Kiron 04.11.2026 11:55 UTC, suche/VORAB_wechsel.yaml, suche/demo_pruefung.py): Steht ein Bot in
journal/konten.json unter abgeloest, gilt er wie ein beendeter Bot. Er öffnet nichts Neues (Vortag: liegende Stop-Orders
löscht er), eine offene Position führt er nach seinen Regeln zu Ende, danach geht das Konto an den Nachfolger oder in
frei.
Am Ende jedes Laufs ist wieder das Hauptkonto aktiv.

Zwilling (suche/r6_zwilling.py): nach jedem fertigen Tag rechnet der Lauf den Backtest-Motor auf den Capital.com-Kerzen
dieses Tages und vergleicht mit dem, was der Bot getan hat. Für EUR/USD und GBP/USD rechnet er die Vortags-Regel; solange
diese beiden Bots kein Konto haben, steht die Zeile als Schatten (ohne Order) im Journal.

    python -m suche.r6_bots             # ein Lauf (im Workflow der Demo-Bots, Mo-Fr alle 15 Minuten)
    python -m suche.r6_bots --dry-run   # nur rechnen und ausgeben, keine Order, nichts speichern

Dateien: journal/r6-bots/state.json, trades.jsonl (ein Trade je Zeile), log.jsonl, zwilling.jsonl, und
journal/r6-bots.json (Stand für das Cockpit). Tests: tests/test_r6_bots.py.
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

from suche import r6_regeln as rg

ROOT = Path(__file__).resolve().parents[1]
JDIR = ROOT / "journal" / "r6-bots"
COCKPIT = ROOT / "journal" / "r6-bots.json"
FMT = "%Y-%m-%dT%H:%M:%S"
RISIKO_PCT = 1.0                 # vom Kontostand je Trade
MAX_RISIKO_EUR = 10.0
MARGIN_ANTEIL = 0.5              # höchstens so viel vom freien Geld als Margin
NOTSTOP_ATR = 2.0                # Noise-Band: Notstop in Tages-ATR(14)
MAX_VERSUCHE = 3                 # Stop-Orders legen: so oft je Tag, dann ist der Tag erledigt
LEER = pd.DataFrame(columns=["open", "high", "low", "close"], dtype=float)
GRUND = {"SL": "Stop beim Broker", "TP": "Ziel beim Broker", "USER": "von Hand geschlossen",
         "CLOSE_OUT": "Zwangsschließung (zu wenig Margin)", "zeit": "Tagesende", "signal": "Gegensignal (Band/VWAP)"}


@dataclass(frozen=True)
class Bot:
    bot_id: str
    strategie: str
    epic: str
    konto_namen: tuple            # das Konto des Bots hat eines dieser Wörter im Namen
    konto_vorschlag: str          # fürs Cockpit, solange der Bot noch kein Konto hat
    titel: str
    regel: str
    backtest: str
    schatten: tuple = ()          # Märkte, auf denen der Zwilling nur mitschreibt (solange es dort keinen Bot mit Konto gibt)
    stop_atr: float | None = None  # nur Mess-Bot (suche/VORAB_messbots.yaml): eigener Stop-Faktor, sonst VORTAG["stop_atr"]


VORTAG = Bot(
    "r6-vortag-usdjpy", "vortag_stop_oco", "USDJPY", ("vortag",), "Konto folgt",
    "Vortageshoch/-tief mit Stop-Orders (USD/JPY)",
    "Ab 10:30 Uhr deutscher Zeit (4:30 New York): Kauf-Stop am Vortageshoch, Verkauf-Stop am Vortagestief. Stop 10 %, "
    "Ziel 25 % der Vortagesspanne, raus spätestens 22:45 Uhr deutscher Zeit (16:45 New York). Bricht der Kurs schon "
    "vor 10:30 Uhr aus, gibt es an dem Tag keinen Trade.",
    "Runde 6 bestanden: Prüfjahre 2021 bis Oktober 2026 mit 269 Trades, Gewinnfaktor 1,24, Treffer 37 %, 5 von 6 Jahren "
    "im Plus, besser als 97 % der Zufallsläufe. 2026 bisher im Minus.",
    ("EURUSD", "GBPUSD"))
LONDON = Bot(
    "r6-london-gbpusd", "london_stunde_long", "GBPUSD", ("london", "gbpusd"), "Konto folgt",
    "London-Stunde, nur Long (GBP/USD)",
    "Bereich = Hoch/Tief der Stunden 4 bis 8 Uhr London. Ab der 9-Uhr-Kerze: die erste Stundenkerze, die unter dem "
    "Bereichshoch eröffnet, darüber schließt und 1 bis 2,5 Stunden-ATR groß ist: Long zur nächsten vollen Stunde, Stop "
    "am Bereichstief, Ziel 1,5 x Risiko, raus um 17 Uhr London. Nur wenn der Markt ruhiger ist als sonst.",
    "Runde 6 knapp nicht bestanden (Kirons Wunsch: trotzdem auf Demo): 144 Trades, Gewinnfaktor 1,22, Zufall 92,5 % "
    "statt 95 %.")
NOISE = Bot(
    "r6-noise-usdjpy", "noise_band", "USDJPY", ("noise",), "Konto folgt",
    "Noise-Band (USD/JPY)",
    "Sitzung 8 bis 17 Uhr London. Schluss über dem Band: Long, darunter: Short (Prüfung jede halbe Stunde). Raus, wenn "
    "der Schluss wieder hinter Band bzw. VWAP fällt, sonst um 17 Uhr London. Nur wenn der Markt ruhiger ist als sonst. "
    "Notstop beim Broker 2 x Tages-ATR (im Backtest kein Stop).",
    "Runde 6 knapp nicht bestanden (Kirons Wunsch: trotzdem auf Demo): 474 Trades, Gewinnfaktor 1,19, 3 von 6 Jahren im "
    "Plus, Zufall 94,9 % statt 95 %.")
VORTAG_ATR_REGEL = (
    "Ab 10:30 Uhr deutscher Zeit (4:30 New York): Kauf-Stop am Vortageshoch, Verkauf-Stop am Vortagestief. Stop 0,5 x "
    "ATR der Viertelstunden-Kerzen beim Legen der Orders (seit 04.11.2026, vorher 10 % der Vortagesspanne), Ziel 25 % "
    "der Vortagesspanne, raus spätestens 22:45 Uhr deutscher Zeit (16:45 New York). Bricht der Kurs schon vor 10:30 Uhr "
    "aus, gibt es an dem Tag keinen Trade. Verpasst der Bot einen Ausbruch, steigt er bis gut eine Stunde später per "
    "Marktorder ein, solange Stop und Ziel noch nicht erreicht sind.")
VORTAG_EURUSD = Bot(
    "r6-vortag-eurusd", "vortag_stop_oco", "EURUSD", (), "Konto folgt",
    "Vortageshoch/-tief mit Stop-Orders (EUR/USD)", VORTAG_ATR_REGEL,
    "Gleiche Regel wie USD/JPY, in Runde 6 nur mitgeschrieben: Prüfjahre 2021 bis Oktober 2026 mit 438 Trades, "
    "Gewinnfaktor 1,26. Mit dem neuen Stop (Stop-Wahl 04.11.2026, 1.000 Euro, 1 % Risiko): 2025 bis Oktober 2026 "
    "133 Trades, 486 statt 426 Euro, Gewinnfaktor 2,33 statt 1,67, Treffer 33 statt 44 %; 2015 bis 2024 1.582 statt "
    "828 Euro. Rutschen ist nicht eingerechnet (0,5 Pip je Einstieg und Stop: 341 statt 292 Euro).")
VORTAG_GBPUSD = Bot(
    "r6-vortag-gbpusd", "vortag_stop_oco", "GBPUSD", (), "Konto folgt",
    "Vortageshoch/-tief mit Stop-Orders (GBP/USD)", VORTAG_ATR_REGEL,
    "Gleiche Regel wie USD/JPY, in Runde 6 nur mitgeschrieben: Prüfjahre 2021 bis Oktober 2026 mit 399 Trades, "
    "Gewinnfaktor 1,19. Mit dem neuen Stop (Stop-Wahl 04.11.2026, 1.000 Euro, 1 % Risiko): 2025 bis Oktober 2026 "
    "130 Trades, 263 statt 165 Euro, Gewinnfaktor 1,61 statt 1,22, Treffer 27 statt 39 %; 2015 bis 2024 2.055 statt "
    "1.098 Euro. Rutschen ist nicht eingerechnet (0,5 Pip je Einstieg und Stop: 137 statt 55 Euro).")
VORTAG_GBPJPY = Bot(
    "r6-vortag-gbpjpy", "vortag_stop_oco", "GBPJPY", (), "Konto folgt",
    "Vortageshoch/-tief mit Stop-Orders (GBP/JPY)", VORTAG_ATR_REGEL,
    "Kirons Auswahl vom 04.11.2026 (verbessern: Vortag auf weiteren Paaren), vorab festgelegter Test vom 05.11.2026 "
    "(Prüfsumme 7e19dbe7 im Protokoll des privaten Repos): 9 Paare, gewählt auf 2015 bis 2024, geurteilt nur auf 2025 "
    "bis Oktober 2026, nur GBP/JPY bestanden. 2025 bis Oktober 2026 (1.000 Euro, 1 % Risiko, Stop 0,5 x ATR beim "
    "Legen): 94 Trades, 190 Euro, Gewinnfaktor 1,45, Treffer 25 %, besser als 99 % der Zufallsläufe. Aber 2026 nur "
    "+0,5 Euro und größter Rückgang 150 Euro (EUR/USD: 36 Euro). Mit 9 Paaren kann eines zufällig bestehen.")
# Mess-Bot (Kritik F2/D3, Kirons Ja vom 05.11.2026 17:07 UTC, suche/VORAB_messbots.yaml): dieselbe Regel wie Vortag
# EUR/USD, nur der Stop 1 x ATR statt 0,5 x ATR. Er misst, ob der breitere Stop das Rutschen beim Einstieg besser
# verkraftet. Ein Konto bekommt er nur über suche/demo_pruefung.py mess_vergeben (Account 2), nie über einen Namen.
VORTAG_EURUSD_1ATR = Bot(
    "r6-vortag-eurusd-1atr", "vortag_stop_oco", "EURUSD", (), "Account 2 (Mess-Bot)",
    "Vortageshoch/-tief mit Stop-Orders (EUR/USD, Stop 1 x ATR, Mess-Bot)",
    VORTAG_ATR_REGEL.replace("Stop 0,5 x ATR der Viertelstunden-Kerzen beim Legen der Orders (seit 04.11.2026, vorher "
                             "10 % der Vortagesspanne)", "Stop 1 x ATR der Viertelstunden-Kerzen beim Legen der Orders "
                             "(Mess-Bot, der Kern-Bot nimmt 0,5 x ATR)"),
    "Mess-Bot ohne eigenen Backtest-Sieg: gleiche Regel wie Vortag EUR/USD (0,5 x ATR: 2025 bis Oktober 2026 133 Trades, "
    "486 Euro, Gewinnfaktor 2,33 ohne Rutschen). Mit 1 x ATR halbiert sich bei gleichem Euro-Risiko die Größe, also "
    "auch der Anteil des Rutschens am Risiko. Verglichen wird nur Demo gegen Demo (suche/VORAB_messbots.yaml).",
    stop_atr=1.0)
BOTS = (VORTAG, LONDON, NOISE, VORTAG_EURUSD, VORTAG_GBPUSD, VORTAG_GBPJPY, VORTAG_EURUSD_1ATR)
# Beendete Bots und wer ihr Konto bekommt. Kirons einheitlicher Vergleich vom 04.11.2026 (Backtest 2025 bis heute,
# suche/VORAB_bewertung.yaml): Vortag USD/JPY besteht nicht (Gewinnfaktor 0,95, 2026: 0,88), Vortag GBP/USD schon (1,22).
# Ein beendeter Bot legt nichts Neues mehr, löscht noch liegende Stop-Orders, führt eine offene Position zu Ende und gibt
# sein Konto dann an den Nachfolger weiter (journal/konten.json: zuordnung, start, uebergaben, konten[].fuer).
BEENDET = {
    "r6-vortag-usdjpy": {"an": "r6-vortag-gbpusd",
                         "status": "beendet am 04.11.2026 (Vergleich 2025 bis heute nicht bestanden: Gewinnfaktor 0,95, "
                                   "vor dem ersten Trade)"},
}


# ---------------------------------------------------------------------------------------------------------------------
# Kleine Helfer (ohne Netz)

def utc(t) -> pd.Timestamp:
    t = pd.Timestamp(t)
    return t.tz_convert("UTC").tz_localize(None) if t.tzinfo else t


def tag_von(bot: Bot, t) -> str:
    """Handelstag wie im Backtest: Vortags-Regel 18 bis 17 Uhr New York (verschoben), sonst London-Datum."""
    if bot.strategie == "vortag_stop_oco":
        return str((rg.ortszeit([utc(t)], rg.NY)[0] + rg.VERSCH).date())
    return str(rg.ortszeit([utc(t)], rg.LON)[0].date())


def fertiger_tag(strategie: str, jetzt) -> str | None:
    """Der letzte Handelstag (Mo-Fr), der zum Zeitpunkt `jetzt` fertig ist (Vortags-Regel: 17 Uhr New York, sonst
    17 Uhr London)."""
    if strategie == "vortag_stop_oco":
        v = rg.ortszeit([utc(jetzt)], rg.NY)[0] + rg.VERSCH
        ende = rg.VORTAG["tag_ende"]
    else:
        v = rg.ortszeit([utc(jetzt)], rg.LON)[0]
        ende = rg.LONDON["sitzung_bis"]
    d = v.normalize()
    if v.hour * 60 + v.minute < ende or d.weekday() >= 5:
        d -= pd.Timedelta(days=1)
    while d.weekday() >= 5:
        d -= pd.Timedelta(days=1)
    return str(d.date())


def pip(epic: str) -> float:
    return 0.01 if epic.endswith("JPY") else 0.0001


def konto_fuer(bot: Bot, accounts: list[dict], kont: dict, haupt: str | None, frei) -> str | None:
    """Das Konto des Bots (reine Auswahl). Schon zugeordnet: dieses. Sonst nur ein Konto mit passendem Namen, das nicht
    das Hauptkonto ist, keinem anderen Bot gehört und keine offene Position hat (`frei(aid)`). Kein Ersatzkonto."""
    from gold.bot.konten import AUS, _id_key
    ids = {str(a.get("accountId")): a for a in accounts if a.get("accountId")}
    zu = kont.get("zuordnung") or {}
    aid = zu.get(bot.bot_id)
    if aid and str(aid) in ids and str(aid) != str(haupt):
        return str(aid)
    belegt = {str(haupt), *(str(v) for k, v in zu.items() if k != bot.bot_id), *(str(x) for x in kont.get("frei") or [])}
    kand = [a for a in ids if a not in belegt and str(ids[a].get("status") or "").upper() not in AUS
            and any(w in str(ids[a].get("accountName") or "").lower() for w in bot.konto_namen)]
    for a in sorted(kand, key=_id_key, reverse=True):
        if frei(a):
            return a
    return None


def groesse(q, risiko_je_einheit: float, kontostand: float | None, frei_eur: float | None,
            preis: float) -> tuple[float | None, dict, list[str]]:
    """Ordergröße: Risiko bis zum Stop höchstens RISIKO_PCT % des Kontostands und MAX_RISIKO_EUR, mindestens die kleinste
    Größe (wenn die nicht mehr als MAX_RISIKO_EUR riskiert); Margin höchstens MARGIN_ANTEIL des freien Gelds."""
    from suche.demo_bots import size_for
    if not q.eur_rate:
        return None, {}, [f"kein Umrechnungskurs EUR/{q.currency}"]
    if not risiko_je_einheit > 0:
        return None, {}, ["kein Abstand zum Stop"]
    grenze = MAX_RISIKO_EUR if not kontostand else min(MAX_RISIKO_EUR, float(kontostand) * RISIKO_PCT / 100)
    eur_je = risiko_je_einheit * q.lot / q.eur_rate
    kleinste = size_for(q)
    size = round(math.floor(grenze / eur_je / q.size_step + 1e-9) * q.size_step, 8)
    if size < kleinste:
        if kleinste * eur_je > MAX_RISIKO_EUR:
            return None, {"risiko_eur": round(kleinste * eur_je, 2)}, [
                f"Risiko bei kleinster Größe {kleinste * eur_je:.2f} EUR, mehr als {MAX_RISIKO_EUR:g} EUR"]
        size = kleinste
    margin_je = preis * q.lot * q.margin_pct / 100 / q.eur_rate
    if frei_eur is not None and size * margin_je > MARGIN_ANTEIL * float(frei_eur):
        size = round(math.floor(MARGIN_ANTEIL * float(frei_eur) / margin_je / q.size_step + 1e-9) * q.size_step, 8)
        if size < kleinste:
            return None, {}, ["zu wenig freies Geld für die Margin"]
    return size, {"risiko_eur": round(size * eur_je, 2), "margin_eur": round(size * margin_je, 2)}, []


def buche(bot: Bot, op: dict, exit_level: float | None, now: pd.Timestamp, grund: str, eur: float | None) -> dict:
    """Ein abgeschlossener Trade. Ergebnis in Prozent vom Kurs (wie der Backtest), R (wenn es einen Stop gibt) und Euro."""
    side, entry = int(op["side"]), op.get("entry")
    geschaetzt = exit_level is None
    if geschaetzt and entry is not None:
        exit_level = (op.get("ziel_level") if grund == "TP" else op.get("stop_level")) or entry
    entry = None if entry is None else float(entry)
    pct = None if entry is None else (float(exit_level) / entry - 1) * side * 100
    stop_abst = abs(entry - float(op["stop_level"])) if entry is not None and op.get("stop_level") else None
    r = None if not stop_abst else side * (float(exit_level) - entry) / stop_abst
    pnl = None if entry is None else side * (float(exit_level) - entry) * float(op["size"]) * float(op.get("lot", 1))
    eur = eur or op.get("eur_rate")
    return {"bot": bot.bot_id, "strategie": bot.strategie, "epic": bot.epic, "side": "long" if side > 0 else "short",
            "dealId": op.get("dealId"), "tag": op.get("tag"), "einstieg_kerze": op.get("einstieg_kerze"),
            "signal_bar": op.get("signal_bar"), "size": op["size"], "entry": entry,
            "exit": None if exit_level is None else round(float(exit_level), 6),
            "stop_level": op.get("stop_level"), "ziel_level": op.get("ziel_level"), "notstop": op.get("notstop", False),
            "opened_utc": op.get("opened_utc"), "closed_utc": now.isoformat(), "reason": GRUND.get(grund, grund),
            "pct": None if pct is None else round(pct, 4), "r": None if r is None else round(r, 3),
            "pnl": None if pnl is None else round(pnl, 4), "waehrung": op.get("currency"),
            "pnl_eur": None if pnl is None or not eur else round(pnl / eur, 2), "geschaetzt": geschaetzt,
            "rutschen_pips": op.get("rutschen_pips"), "konto": op.get("konto_kurz"),
            "uebernommen": op.get("uebernommen", False), "nachgeholt": op.get("nachgeholt", False)}


def zusammenfassung(trades: list[dict]) -> dict:
    p = np.array([t["pct"] for t in trades if t.get("pct") is not None], float)
    g, v = p[p > 0].sum(), -p[p < 0].sum()
    return {"trades": len(p), "treffer_pct": round(100 * float((p > 0).mean()), 1) if len(p) else None,
            "pf": (round(float(g / v), 3) if v > 0 else None) if len(p) else None,
            "summe_pct": round(float(p.sum()), 3) if len(p) else 0.0,
            "pnl_eur": round(float(sum(t.get("pnl_eur") or 0 for t in trades)), 2)}


# ---------------------------------------------------------------------------------------------------------------------
# Broker (nur Demokonto)

def kerzen(client, epic: str, res: str, n: int, jetzt: pd.Timestamp) -> tuple[pd.DataFrame, pd.Series]:
    """Die letzten n fertigen Kerzen (Bid) und der Spread zur Eröffnung."""
    from suche.demo_bots import frame, only_closed
    tf = {"MINUTE_15": "15min", "HOUR": "60min"}[res]
    return only_closed(*frame(client.prices(epic, res, n)), jetzt, tf)


def kerzen_zeitraum(client, epic: str, res: str, tage: int, jetzt: pd.Timestamp) -> tuple[pd.DataFrame, pd.Series]:
    """Fertige Kerzen der letzten `tage` Kalendertage, in Abrufen zu höchstens 1000 Kerzen."""
    from suche.demo_bots import frame, only_closed
    tf, je = {"MINUTE_15": ("15min", 10), "HOUR": ("60min", 40)}[res]
    teile, bis = [], pd.Timestamp(jetzt)
    beginn = bis - pd.Timedelta(days=tage)
    while bis > beginn:
        von = max(beginn, bis - pd.Timedelta(days=je))
        try:
            got = client._get(f"/prices/{epic}", resolution=res, max=1000,
                              **{"from": von.strftime(FMT), "to": bis.strftime(FMT)}).get("prices", [])
        except Exception:                # noqa: BLE001 - weiter zurück gibt es keine Kerzen
            got = []
        teile.extend(got)
        bis = von
    return only_closed(*frame(teile), jetzt, tf)


def arbeitsorders(client, epic: str) -> list[dict]:
    """Offene Stop-Orders des aktiven Kontos in diesem Markt (workingOrderData)."""
    out = []
    for w in client._get("/workingorders").get("workingOrders", []):
        d = w.get("workingOrderData") or {}
        if (d.get("epic") or (w.get("marketData") or {}).get("epic")) == epic:
            out.append(d)
    return out


def lege_stop_order(client, epic: str, side: int, size: float, level: float, stop: float, ziel: float,
                    bis_utc: pd.Timestamp) -> dict:
    body = {"epic": epic, "direction": "BUY" if side > 0 else "SELL", "size": size, "level": level, "type": "STOP",
            "goodTillDate": pd.Timestamp(bis_utc).strftime(FMT), "guaranteedStop": False, "stopLevel": stop,
            "profitLevel": ziel}
    ref = client._request("POST", "/workingorders", json=body).json()["dealReference"]
    return client.confirm(ref)


def loesche_order(client, deal_id: str) -> dict:
    ref = client._request("DELETE", f"/workingorders/{deal_id}").json().get("dealReference")
    return client.confirm(ref) if ref else {}


def markt_order(client, epic: str, side: int, size: float, stop_level: float | None = None,
                stop_dist: float | None = None, ziel_level: float | None = None) -> dict:
    body = {"epic": epic, "direction": "BUY" if side > 0 else "SELL", "size": size, "guaranteedStop": False}
    if stop_level is not None:
        body["stopLevel"] = stop_level
    elif stop_dist is not None:
        body["stopDistance"] = stop_dist
    if ziel_level is not None:
        body["profitLevel"] = ziel_level
    ref = client._request("POST", "/positions", json=body).json()["dealReference"]
    return client.confirm(ref)


def deal_id(res: dict) -> str | None:
    return res.get("dealId") or (res.get("affectedDeals") or [{}])[0].get("dealId")


class Lauf:
    """Was ein Lauf über alle Bots teilt: Client, Zeit, Log, neue Trades, Kerzen-Zwischenspeicher."""

    def __init__(self, client, now, kont: dict, send: bool):
        self.client, self.now, self.kont, self.send = client, utc(now), kont, send
        self.stamp = self.now.isoformat()
        self.log: list[dict] = []
        self.neu: list[dict] = []
        self.eur: dict = {}
        self.accounts: list[dict] = []
        self.haupt: str | None = None
        self.pos: dict = {}

    def ereignis(self, bot: Bot | None, event: str, **kw) -> None:
        self.log.append({"time": self.stamp, "bot": bot.bot_id if bot else None, "event": event, **kw})

    def positionen(self, aid: str) -> list[dict]:
        from gold.bot import konten
        konten.wechseln(self.client, aid)
        if aid not in self.pos:
            self.pos[aid] = self.client.positions()
        return self.pos[aid]

    def quote(self, epic: str):
        from suche.demo_bots import eur_rate, quote_from_market
        q = quote_from_market(self.client.market(epic), None)
        q.eur_rate = eur_rate(self.client, q.currency, self.eur)
        return q


def tageswerte(lauf: Lauf, state: dict, epic: str, tag: str) -> dict | None:
    """ATR(14), ATR(100) und Schwankung der Tageskerzen bis vor `tag` (Handelstag bis 17 Uhr New York), einmal am Tag aus
    Stundenkerzen der letzten 170 Tage; gespeichert im Zustand."""
    m = state.setdefault("maerkte", {}).setdefault(epic, {})
    werte = m.setdefault("tageswerte", {})
    if tag in werte:
        return werte[tag]
    st, _ = kerzen_zeitraum(lauf.client, epic, "HOUR", 170, lauf.now)
    w = rg.tageswerte(st, pd.Timestamp(tag))
    werte[tag] = w
    for alt in sorted(werte)[:-10]:
        del werte[alt]
    return w


def uebernehmen(bot: Bot, p: dict, q, konto_kurz: str | None) -> dict:
    """Eine Position im Markt des Bots auf seinem Konto, die nicht im Zustand steht (Journal nach einem Fehler nicht
    gesichert). Das Konto gehört nur diesem Bot; sie wird wie eine eigene geführt und zum Tagesende geschlossen."""
    pos = p["position"]
    side = 1 if str(pos.get("direction")).upper() == "BUY" else -1
    opened = utc(pos.get("createdDateUTC") or pd.Timestamp.now(tz="UTC"))
    return {"dealId": pos.get("dealId"), "side": side, "tag": tag_von(bot, opened), "signal_bar": None,
            "einstieg_kerze": str(opened.floor("15min")), "entry": float(pos.get("level") or 0) or None,
            "stop_level": pos.get("stopLevel"), "ziel_level": pos.get("profitLevel"), "size": pos.get("size"),
            "lot": q.lot, "currency": q.currency, "eur_rate": q.eur_rate, "opened_utc": str(opened),
            "konto_kurz": konto_kurz, "uebernommen": True}


def _schliessen(lauf: Lauf, bot: Bot, st: dict, op: dict, grund: str, q) -> None:
    if not lauf.send:
        lauf.ereignis(bot, "würde schließen (Trockenlauf)", grund=grund)
        return
    res = lauf.client.close_position(op["dealId"])
    if res.get("dealStatus") == "ACCEPTED":
        tr = buche(bot, op, res.get("level"), lauf.now, grund, q.eur_rate)
        lauf.neu.append(tr)
        st["open"] = None
        lauf.ereignis(bot, "geschlossen", **{k: tr[k] for k in ("exit", "pct", "reason")})
    else:
        lauf.ereignis(bot, "schließen abgelehnt", res=str(res)[:200])


def _vom_broker_zu(lauf: Lauf, bot: Bot, st: dict, op: dict, q) -> None:
    from suche.demo_bots import broker_exit
    level, source = broker_exit(lauf.client, op, lauf.now)
    tr = buche(bot, op, level, lauf.now, source or "SL", q.eur_rate)
    lauf.neu.append(tr)
    st["open"] = None
    lauf.ereignis(bot, "vom Broker geschlossen", **{k: tr[k] for k in ("exit", "pct", "reason")})


# ---------------------------------------------------------------------------------------------------------------------
# Platz 1: Stop-Orders

def _aktivitaet(lauf: Lauf, bot: Bot, von: pd.Timestamp, bis: pd.Timestamp) -> list[dict] | None:
    """Positions-Zeilen der Kontoaktivität des aktiven Kontos in diesem Markt (nur lesen). None, wenn nicht lesbar."""
    try:
        acts = lauf.client._get("/history/activity", **{"from": von.strftime(FMT), "to": bis.strftime(FMT),
                                                        "detailed": "true"}).get("activities", [])
    except Exception as err:            # noqa: BLE001
        lauf.ereignis(bot, "Kontoaktivität nicht lesbar", why=str(err)[:200])
        return None
    return [{"dateUTC": a.get("dateUTC"), "source": a.get("source"), "type": a.get("type"), "status": a.get("status"),
             "level": (a.get("details") or {}).get("level"), "direction": (a.get("details") or {}).get("direction"),
             "actions": [x.get("actionType") for x in (a.get("details") or {}).get("actions", [])]}
            for a in acts if a.get("epic") == bot.epic]


def _seite(orders: dict, weg: list[str], auf: list[dict], zu: dict) -> str:
    """Welche der weggefallenen Stop-Orders ausgelöst hat: bei einer diese, sonst die Richtung der Eröffnung, sonst die
    Order, deren Kurs (Einstieg, sonst Stop oder Ziel beim Schluss) am nächsten liegt."""
    if len(weg) == 1:
        return weg[0]
    d = str((auf[0].get("direction") if auf else None) or "").upper()
    if d in ("BUY", "SELL"):
        return "long" if d == "BUY" else "short"
    if auf:
        return min(weg, key=lambda s: abs(float(orders[s]["level"]) - float(auf[0]["level"])))
    lvl = float(zu["level"])
    return min(weg, key=lambda s: min(abs(float(orders[s][k]) - lvl) for k in ("stop", "ziel", "level")
                                      if orders[s].get(k) is not None))


def _gefuellt_und_zu(lauf: Lauf, bot: Bot, orders: dict, weg: list[str], rows: list[dict] | None = None) -> dict | None:
    """Stop-Orders sind weg und es gibt keine Position: Hat eine ausgelöst und Stop oder Ziel schon zwischen zwei Läufen
    getroffen? Aus der Kontoaktivität seit dem Legen. Auch wenn beide weg sind (eine ausgelöst und zu, die andere um
    21:30 UTC abgelaufen). Bis 05.11.2026 wurde dann nicht nachgesehen, und der GBP/JPY-Short vom 05.11. fehlte im
    Journal (siehe NACHPRUEFEN). None, wenn dort kein Schluss steht."""
    from gold.bot.runner import close_activity
    if rows is None:
        since = utc(orders.get("gelegt_utc") or lauf.now) - pd.Timedelta(minutes=5)
        rows = _aktivitaet(lauf, bot, since, lauf.now)
    if not rows:
        return None
    zu = close_activity(rows, None)
    if zu is None or (zu.get("source") not in ("SL", "TP", "CLOSE_OUT")
                      and "POSITION_CLOSED" not in (zu.get("actions") or [])):
        return None
    auf = sorted((r for r in rows if "POSITION_OPENED" in (r.get("actions") or []) and r.get("level") is not None),
                 key=lambda r: str(r.get("dateUTC") or ""))
    seite = _seite(orders, weg, auf, zu)
    o, side = orders[seite], 1 if seite == "long" else -1
    entry = float(auf[0]["level"]) if auf else float(o["level"])
    opened = utc(auf[0]["dateUTC"]) if auf and auf[0].get("dateUTC") else None
    op = {"dealId": None, "side": side, "tag": orders["tag"], "entry": entry, "stop_level": o["stop"],
          "ziel_level": o["ziel"], "size": o["size"], "lot": orders.get("lot", 1), "currency": orders.get("currency"),
          "eur_rate": orders.get("eur_rate"), "konto_kurz": orders.get("konto_kurz"),
          "opened_utc": str(opened) if opened is not None else orders.get("gelegt_utc"),
          "einstieg_kerze": str(opened.floor("15min")) if opened is not None else None,
          # Rutschen wie bei jedem Einstieg über die Stop-Order (suche/VORAB_rutschen.yaml), nur mit echtem Einstiegskurs
          "rutschen_pips": round((entry - float(o["level"])) * side / pip(bot.epic), 1) if auf else None}
    closed = utc(zu["dateUTC"]) if zu.get("dateUTC") else lauf.now
    tr = buche(bot, op, float(zu["level"]), closed, str(zu.get("source") or "SL"), None)
    tr["einstieg_geschaetzt"] = not auf
    return tr


# Einmal nachprüfen (Fehler bis 05.11.2026, siehe _gefuellt_und_zu): Beim Lauf um 21:31 UTC waren beide GBP/JPY-Orders
# weg, das Konto aber 4,52 € kleiner (journal/konten.json), und der Zwilling sah den Short ab der 21:15-Kerze, um 21:30
# ausgestoppt. Die Orders wie in journal/r6-bots/state.json bis 21:16 UTC. Der Lauf bucht den Trade aus der Kontoaktivität
# (echte Kurse) und merkt sich den Tag unter "nachgeprueft".
NACHPRUEFEN: dict[str, dict] = {
    "r6-vortag-gbpjpy": {
        "tag": "2026-11-05", "gelegt_utc": "2026-11-05T11:46:51.956368", "bis_utc": "2026-11-05 21:30:00", "lot": 1.0,
        "currency": "JPY", "eur_rate": 177.7215, "konto_kurz": "…4494",
        "long": {"dealId": "00000000-7131-49f9-049c-701d0015549e", "level": 213.786, "marke": 213.763, "stop": 213.706,
                 "ziel": 214.187, "size": 12500.0},
        "short": {"dealId": "00000000-7131-4a02-049c-701d0015549e", "level": 212.067, "marke": 212.067, "stop": 212.124,
                  "ziel": 211.643, "size": 12500.0}},
}


def nachpruefen(lauf: Lauf, bot: Bot, st: dict) -> None:
    """Orders aus NACHPRUEFEN einmal in der Kontoaktivität nachsehen und einen dort geschlossenen Trade buchen. Ist die
    Aktivität nicht lesbar, versucht es der nächste Lauf wieder."""
    o = NACHPRUEFEN.get(bot.bot_id)
    if not o or o["tag"] in (st.get("nachgeprueft") or []) or st.get("konto") != o["konto_kurz"]:
        return
    von = utc(o["gelegt_utc"]) - pd.Timedelta(minutes=5)
    rows = _aktivitaet(lauf, bot, von, min(lauf.now, utc(o["bis_utc"]) + pd.Timedelta(hours=1)))
    if rows is None:
        return
    tr = _gefuellt_und_zu(lauf, bot, o, ["long", "short"], rows)
    if tr:
        tr["nachgebucht"] = lauf.stamp
        lauf.neu.append(tr)
        lauf.ereignis(bot, "nachgebucht", **{k: tr[k] for k in ("tag", "side", "entry", "exit", "r", "pnl_eur", "reason")})
    else:
        lauf.ereignis(bot, "nachgeprüft, kein Trade", tag=o["tag"])
    st["nachgeprueft"] = [*(st.get("nachgeprueft") or []), o["tag"]]


def lauf_vortag(lauf: Lauf, bot: Bot, st: dict, aid: str, q, neu: bool = True) -> None:
    """Ein Lauf der Vortags-Regel auf dem Konto `aid`. neu=False (beendeter Bot): ausgelöste Orders und offene Positionen
    werden wie immer geführt, aber keine neuen Stop-Orders gelegt."""
    from gold.bot import konten
    from suche.demo_bots import own_position
    c, now = lauf.client, lauf.now
    mine = own_position(lauf.positionen(aid), bot.epic)
    wos = arbeitsorders(c, bot.epic)
    wo_ids = {str(w.get("dealId")) for w in wos}
    op, orders = st.get("open"), st.get("orders")
    nachpruefen(lauf, bot, st)

    if orders and not op:                                       # hat eine Stop-Order ausgelöst?
        if mine:
            pos = mine[0]["position"]
            side = 1 if str(pos.get("direction")).upper() == "BUY" else -1
            seite, andere = ("long", "short") if side > 0 else ("short", "long")
            o = orders[seite]
            opened = utc(pos.get("createdDateUTC") or now)
            entry = float(pos.get("level") or o["level"])
            op = st["open"] = {
                "dealId": pos.get("dealId"), "side": side, "tag": orders["tag"], "signal_bar": None,
                "einstieg_kerze": str(opened.floor("15min")), "entry": entry, "marke": o["marke"],
                "order_level": o["level"], "stop_level": o["stop"], "ziel_level": o["ziel"], "size": pos.get("size") or o["size"],
                "lot": q.lot, "currency": q.currency, "eur_rate": q.eur_rate, "opened_utc": str(opened),
                "konto_kurz": konten.kurz(aid), "rutschen_pips": round((entry - o["level"]) * side / pip(bot.epic), 1)}
            if orders.get(andere) and str(orders[andere]["dealId"]) in wo_ids and lauf.send:
                loesche_order(c, orders[andere]["dealId"])
            st["orders"] = None
            st["tag_erledigt"] = orders["tag"]
            lauf.ereignis(bot, "Stop-Order ausgelöst", side=seite, entry=entry, order=o["level"],
                          rutschen_pips=op["rutschen_pips"], dealId=op["dealId"])
        else:
            weg = [s for s in ("long", "short") if orders.get(s) and str(orders[s]["dealId"]) not in wo_ids]
            if weg:
                tr = _gefuellt_und_zu(lauf, bot, orders, weg)
                if tr:
                    lauf.neu.append(tr)
                    lauf.ereignis(bot, "ausgelöst und schon wieder zu", **{k: tr[k] for k in ("side", "exit", "pct", "reason")})
                else:
                    lauf.ereignis(bot, "Stop-Orders nicht mehr da (abgelaufen oder gelöscht)", weg=weg)
                for s in ("long", "short"):
                    if orders.get(s) and str(orders[s]["dealId"]) in wo_ids and lauf.send:
                        loesche_order(c, orders[s]["dealId"])
                st["tag_erledigt"] = orders["tag"]
                st["orders"], orders = None, None

    if op:
        if op.get("dealId") not in {p["position"].get("dealId") for p in mine}:
            _vom_broker_zu(lauf, bot, st, op, q)
            return
        d = rg.vt_entscheide(LEER, now, {"open": op})
        st["letzte_entscheidung"] = {"zeit": lauf.stamp, "action": d["action"], "why": d["why"]}
        if d["action"] == "close":
            _schliessen(lauf, bot, st, op, "zeit", q)
        return

    if orders:
        d = rg.vt_entscheide(LEER, now, {"orders": orders})
        st["letzte_entscheidung"] = {"zeit": lauf.stamp, "action": d["action"], "why": d["why"]}
        if d["action"] == "cancel":
            for s in ("long", "short"):
                if orders.get(s) and str(orders[s]["dealId"]) in wo_ids and lauf.send:
                    loesche_order(c, orders[s]["dealId"])
            st["orders"] = None
            st["tag_erledigt"] = orders["tag"]
            lauf.ereignis(bot, "Stop-Orders gelöscht", why=d["why"])
        return

    if mine:                                                    # eigene Position ohne Zustand: übernehmen
        op = st["open"] = uebernehmen(bot, mine[0], q, konten.kurz(aid))
        lauf.ereignis(bot, "Position übernommen", dealId=op["dealId"])
        return
    if wos:                                                     # Stop-Orders ohne Zustand: löschen, neu rechnen
        for w in wos:
            if lauf.send:
                loesche_order(c, w.get("dealId"))
        lauf.ereignis(bot, "unbekannte Stop-Orders gelöscht", anzahl=len(wos))

    if not neu:
        return
    v = rg.ortszeit([now], rg.NY)[0] + rg.VERSCH
    minute, tag = v.hour * 60 + v.minute, str(v.date())
    braucht = (v.weekday() < 5 and st.get("tag_erledigt") != tag
               and rg.VORTAG["uhrzeit_ueber"] + 15 <= minute < rg.VORTAG["tag_ende"] - 30)
    bars = kerzen(c, bot.epic, "MINUTE_15", 700, now)[0] if braucht else LEER
    d = rg.vt_entscheide(bars, now, {"tag_erledigt": st.get("tag_erledigt"), "stop_atr": bot.stop_atr})
    st["letzte_entscheidung"] = {"zeit": lauf.stamp, "action": d["action"], "why": d["why"],
                                 "bar": str(bars.index[-1]) if len(bars) else None}
    if d.get("erledigt"):
        st["tag_erledigt"] = d["tag"]
    if d["action"] == "nachholen":
        vortag_nachholen(lauf, bot, st, aid, q, d)
        return
    if d["action"] != "orders":
        return
    versuche = st.setdefault("versuche", {})
    versuche[d["tag"]] = versuche.get(d["tag"], 0) + 1
    for alt in sorted(versuche)[:-5]:
        del versuche[alt]
    spread = max(q.offer - q.bid, 0.0)
    long_level, short_level = d["long"]["marke"] + spread, d["short"]["marke"]
    ev = {"ph": d["ph"], "pl": d["pl"], "long": round(long_level, q.decimals), "short": round(short_level, q.decimals)}
    why = []
    if not q.tradeable:
        why.append("Markt gerade nicht handelbar")
    if not (q.offer < long_level and q.bid > short_level):
        why.append("Kurs steht schon hinter einer Marke")
        st["tag_erledigt"] = d["tag"]
    # Stop seit 04.11.2026: 0,5 x ATR der Viertelstunden (VORAB_r6_demo.yaml nachtrag_vortag_stop_2026_11_04). Liegt er
    # näher an der Order als der Mindestabstand des Brokers, rückt er auf 1,05 x Mindestabstand (wie suche/demo_bots).
    min_s = q.min_dist * 1.05 if q.min_dist > 0 else 0.0
    l_stop = min(d["long"]["stop"], long_level - min_s)
    s_stop = max(d["short"]["stop"], short_level + min_s)
    if l_stop != d["long"]["stop"] or s_stop != d["short"]["stop"]:
        ev["stop_erweitert"] = {"long": round(l_stop, q.decimals), "short": round(s_stop, q.decimals),
                                "min_dist": q.min_dist}
    ev.update(stop_abstand=d.get("stop_abstand"), atr15=d.get("atr15"))
    risiko = max(long_level - l_stop, s_stop - short_level)
    if min(d["long"]["ziel"] - long_level, short_level - d["short"]["ziel"]) < q.min_dist:
        why.append("Ziel näher als der Mindestabstand des Brokers")
        st["tag_erledigt"] = d["tag"]
    acc = next((a for a in lauf.accounts if str(a.get("accountId")) == aid), {})
    bal = acc.get("balance") or {}
    size, info, w = groesse(q, risiko, bal.get("balance"), bal.get("available"), q.offer)
    why += w
    ev.update(size=size, **info)
    if why:
        lauf.ereignis(bot, "Stop-Orders nicht gelegt", why=why, **ev)
        if versuche[d["tag"]] >= MAX_VERSUCHE:
            st["tag_erledigt"] = d["tag"]
        return
    if not lauf.send:
        lauf.ereignis(bot, "würde Stop-Orders legen (Trockenlauf)", **ev)
        return
    bis = pd.Timestamp(d["gueltig_bis_utc"])
    dec = q.decimals
    res_l = lege_stop_order(c, bot.epic, 1, size, round(long_level, dec), round(l_stop, dec),
                            round(d["long"]["ziel"], dec), bis)
    res_s = lege_stop_order(c, bot.epic, -1, size, round(short_level, dec), round(s_stop, dec),
                            round(d["short"]["ziel"], dec), bis) if res_l.get("dealStatus") == "ACCEPTED" else {}
    if res_l.get("dealStatus") != "ACCEPTED" or res_s.get("dealStatus") != "ACCEPTED":
        if res_l.get("dealStatus") == "ACCEPTED":
            loesche_order(c, deal_id(res_l))
        lauf.ereignis(bot, "Stop-Orders abgelehnt", long=str(res_l)[:200], short=str(res_s)[:200], **ev)
        if versuche[d["tag"]] >= MAX_VERSUCHE:
            st["tag_erledigt"] = d["tag"]
        return
    st["orders"] = {
        "tag": d["tag"], "ph": d["ph"], "pl": d["pl"], "gelegt_utc": lauf.stamp, "bis_utc": str(bis),
        "lot": q.lot, "currency": q.currency, "eur_rate": q.eur_rate, "konto_kurz": konten.kurz(aid),
        "long": {"dealId": deal_id(res_l), "level": round(long_level, dec), "marke": d["long"]["marke"],
                 "stop": round(l_stop, dec), "ziel": round(d["long"]["ziel"], dec), "size": size},
        "short": {"dealId": deal_id(res_s), "level": round(short_level, dec), "marke": d["short"]["marke"],
                  "stop": round(s_stop, dec), "ziel": round(d["short"]["ziel"], dec), "size": size},
        "stop_abstand": d.get("stop_abstand"), "atr15": d.get("atr15")}
    lauf.ereignis(bot, "Stop-Orders gelegt", **ev)


def vortag_nachholen(lauf: Lauf, bot: Bot, st: dict, aid: str, q, d: dict) -> None:
    """Verpasster Ausbruch (Kirons Wunsch vom 04.11.2026 13:53 UTC, VORAB_r6_demo.yaml
    nachtrag_vortag_nachholen_2026_11_04): Marktorder in Ausbruchsrichtung mit denselben Stop- und Zielkursen wie die
    Stop-Orders, solange der Kurs noch zwischen Stop und Ziel steht. Größe nach dem Abstand vom Kurs jetzt bis zum Stop
    (also wie immer höchstens 1 % bzw. 10 Euro Risiko). Die Einstiegskerze ist die Ausbruchskerze (für den Zwilling)."""
    from gold.bot import konten
    from suche.demo_bots import own_position
    c, side, dec = lauf.client, d["side"], q.decimals
    versuche = st.setdefault("versuche", {})
    versuche[d["tag"]] = versuche.get(d["tag"], 0) + 1
    for alt in sorted(versuche)[:-5]:
        del versuche[alt]
    preis = q.offer if side > 0 else q.bid
    spread = max(q.offer - q.bid, 0.0)
    min_s = q.min_dist * 1.05 if q.min_dist > 0 else 0.0
    stop = min(d["stop"], preis - min_s) if side > 0 else max(d["stop"], preis + min_s)
    ziel = d["ziel"]
    ev = {"side": "long" if side > 0 else "short", "preis": round(preis, dec), "marke": d["marke"],
          "stop": round(stop, dec), "ziel": round(ziel, dec), "ausbruch_kerze": d["ausbruch_kerze"],
          "verspaetung_min": d["verspaetung_min"], "stop_abstand": d["stop_abstand"], "atr15": d["atr15"]}
    if stop != d["stop"]:
        ev["stop_erweitert"] = {"regel": round(d["stop"], dec), "min_dist": q.min_dist}
    why = []
    if not q.tradeable:
        why.append("Markt gerade nicht handelbar")
    noch_drin = (q.bid > d["stop"] and preis < ziel) if side > 0 else (q.offer < d["stop"] and preis > ziel)
    if not noch_drin or (ziel - preis) * side < q.min_dist:
        why.append("Kurs schon am Stop oder zu nah am Ziel")
        st["tag_erledigt"] = d["tag"]
    acc = next((a for a in lauf.accounts if str(a.get("accountId")) == aid), {})
    bal = acc.get("balance") or {}
    size, info, w = groesse(q, (preis - stop) * side, bal.get("balance"), bal.get("available"), preis)
    why += w
    ev.update(size=size, **info)
    if why:
        lauf.ereignis(bot, "Ausbruch nicht nachgeholt", why=why, **ev)
        if versuche[d["tag"]] >= MAX_VERSUCHE:
            st["tag_erledigt"] = d["tag"]
        return
    if not lauf.send:
        lauf.ereignis(bot, "würde Ausbruch nachholen (Trockenlauf)", **ev)
        return
    res = markt_order(c, bot.epic, side, size, stop_level=round(stop, dec), ziel_level=round(ziel, dec))
    lauf.pos.pop(aid, None)
    if res.get("dealStatus") != "ACCEPTED":
        lauf.ereignis(bot, "Nachhol-Order abgelehnt", res=str(res)[:300], **ev)
        if versuche[d["tag"]] >= MAX_VERSUCHE:
            st["tag_erledigt"] = d["tag"]
        return
    nach = own_position(lauf.positionen(aid), bot.epic)
    pos = nach[0]["position"] if nach else {}
    entry = float(pos.get("level") or res.get("level") or preis)
    order_level = d["marke"] + (spread if side > 0 else 0.0)
    st["open"] = {
        "dealId": pos.get("dealId") or deal_id(res), "side": side, "tag": d["tag"], "signal_bar": None,
        "einstieg_kerze": d["ausbruch_kerze"], "entry": entry, "marke": d["marke"], "order_level": round(order_level, dec),
        "stop_level": round(stop, dec), "ziel_level": round(ziel, dec), "size": size, "lot": q.lot,
        "currency": q.currency, "eur_rate": q.eur_rate, "opened_utc": pos.get("createdDateUTC") or lauf.stamp,
        "konto_kurz": konten.kurz(aid), "rutschen_pips": round((entry - order_level) * side / pip(bot.epic), 1),
        "nachgeholt": True, "verspaetung_min": d["verspaetung_min"]}
    st["tag_erledigt"] = d["tag"]
    lauf.ereignis(bot, "Ausbruch nachgeholt (Marktorder)", entry=entry, dealId=st["open"]["dealId"],
                  rutschen_pips=st["open"]["rutschen_pips"], **ev)


# ---------------------------------------------------------------------------------------------------------------------
# Platz 2 und 3: Marktorders

def entscheidung_markt(lauf: Lauf, bot: Bot, st: dict, state: dict, op: dict | None) -> dict:
    """Die Entscheidung von London- oder Noise-Bot; holt Kerzen nur, wenn sie gebraucht werden."""
    c, now = lauf.client, lauf.now
    lo_ = rg.ortszeit([now], rg.LON)[0]
    minute, heute = lo_.hour * 60 + lo_.minute, str(lo_.date())
    werktag = lo_.weekday() < 5
    ht = str(rg.handelstag_ny17(now).date())
    if bot.strategie == "london_stunde_long":
        braucht = (not op and werktag and st.get("tag_erledigt") != heute
                   and (rg.LONDON["signal_ab"] + 1) * 60 <= minute < rg.LONDON["sitzung_bis"] - 60 + 16)
        if not braucht:
            return rg.ld_entscheide(LEER, LEER, now, {"open": op, "tag_erledigt": st.get("tag_erledigt")}, None)
        w = tageswerte(lauf, state, bot.epic, ht)
        bars = kerzen(c, bot.epic, "MINUTE_15", 120, now)[0]
        stunden = kerzen(c, bot.epic, "HOUR", 400, now)[0]
        d = rg.ld_entscheide(bars, stunden, now, {"tag_erledigt": st.get("tag_erledigt")}, w and w["schwankung"])
        d["tageswerte"] = w
        return d
    # Noise-Band
    schluss = op and (str(op.get("tag")) != heute or minute >= rg.NOISE["sitzung_bis"])
    braucht = werktag and rg.NOISE["sitzung_von"] + 30 <= minute < rg.NOISE["sitzung_bis"]
    if schluss or not braucht:
        return rg.nb_entscheide(LEER, now, {"open": op}, None, None)
    w = tageswerte(lauf, state, bot.epic, ht)
    b = st.get("band") or {}
    if b.get("tag") != heute:
        alt, _ = kerzen_zeitraum(c, bot.epic, "MINUTE_15", 45, now)
        nb = rg.nb_band(rg.nb_sitzungen(alt), pd.Timestamp(heute))
        b = {"tag": heute, "sig": None if nb is None else [float(x) for x in nb["sig"]],
             "vortag_schluss": None if nb is None else nb["vortag_schluss"]}
        st["band"] = b
    band = None if b.get("sig") is None else {"sig": np.array(b["sig"]), "vortag_schluss": b["vortag_schluss"]}
    bars = kerzen(c, bot.epic, "MINUTE_15", 100, now)[0]
    if band is None:
        return {"action": "none", "tag": heute, "why": ["weniger als 14 vollständige Sitzungen in den Kerzen"]}
    d = rg.nb_entscheide(bars, now, {"open": op}, w and w["schwankung"], band)
    d["tageswerte"] = w
    return d


def lauf_markt(lauf: Lauf, bot: Bot, st: dict, state: dict, aid: str, q, neu: bool = True) -> None:
    """Ein Lauf von London- oder Noise-Bot auf dem Konto `aid`. neu=False (beendeter oder abgelöster Bot): eine offene
    Position wird wie immer geführt und geschlossen, aber kein neuer Trade geöffnet."""
    from gold.bot import konten
    from suche.demo_bots import own_position
    c = lauf.client
    mine = own_position(lauf.positionen(aid), bot.epic)
    op = st.get("open")
    if op and op.get("dealId") not in {p["position"].get("dealId") for p in mine}:
        _vom_broker_zu(lauf, bot, st, op, q)
        op = None
    if not op and mine:
        op = st["open"] = uebernehmen(bot, mine[0], q, konten.kurz(aid))
        lauf.ereignis(bot, "Position übernommen", dealId=op["dealId"])
    if not op and not neu:
        return
    d = entscheidung_markt(lauf, bot, st, state, op)
    st["letzte_entscheidung"] = {"zeit": lauf.stamp, "action": d["action"], "why": d.get("why")}
    if d.get("linien"):
        st["linien"] = {"zeit": lauf.stamp, **{k: round(float(v), 5) for k, v in d["linien"].items()}}
    if d.get("erledigt"):
        st["tag_erledigt"] = d["tag"]
    if d["action"] == "close" and op:
        _schliessen(lauf, bot, st, op, d.get("reason", "zeit"), q)
        return
    if d["action"] != "open" or op or not neu:
        return
    side = int(d["side"])
    preis = q.offer if side > 0 else q.bid
    ev = {"side": "long" if side > 0 else "short", "bar": d.get("signal_bar")}
    why, stop_level, stop_dist, ziel_level = [], None, None, None
    if bot.strategie == "london_stunde_long":
        st["tag_erledigt"] = d["tag"]                           # ein Versuch am Tag
        stop_level = float(d["stop_level"])
        ziel_level = q.bid + float(d["ziel_r"]) * (q.bid - stop_level)
        risiko = q.offer - stop_level
        if q.bid - stop_level < q.min_dist or ziel_level - q.bid < q.min_dist:
            why.append("Stop oder Ziel näher als der Mindestabstand des Brokers")
        einstieg_kerze = pd.Timestamp(d["signal_bar"]) + pd.Timedelta(hours=1)
    else:
        w = d.get("tageswerte") or {}
        if not w.get("atr14"):
            why.append("Tages-ATR unbekannt, kein Notstop möglich")
            risiko = 0.0
        else:
            stop_dist = max(NOTSTOP_ATR * float(w["atr14"]), q.min_dist * 1.05)
            risiko = stop_dist
        einstieg_kerze = pd.Timestamp(d["signal_bar"]) + pd.Timedelta(minutes=15)
    if not q.tradeable:
        why.append("Markt gerade nicht handelbar")
    acc = next((a for a in lauf.accounts if str(a.get("accountId")) == aid), {})
    bal = acc.get("balance") or {}
    size, info, w2 = groesse(q, risiko, bal.get("balance"), bal.get("available"), preis) if risiko > 0 else (None, {}, [])
    why += w2
    ev.update(size=size, **info)
    if why:
        lauf.ereignis(bot, "Signal nicht genutzt", why=why, **ev)
        return
    dec = q.decimals
    order = {"stop_level": None if stop_level is None else round(stop_level, dec),
             "stop_dist": None if stop_dist is None else round(stop_dist, dec),
             "ziel_level": None if ziel_level is None else round(ziel_level, dec)}
    if not lauf.send:
        lauf.ereignis(bot, "würde öffnen (Trockenlauf)", **ev, **order)
        return
    res = markt_order(c, bot.epic, side, size, **order)
    lauf.pos.pop(aid, None)
    if res.get("dealStatus") != "ACCEPTED":
        lauf.ereignis(bot, "Order abgelehnt", res=str(res)[:300], **ev)
        return
    nach = own_position(lauf.positionen(aid), bot.epic)
    pos = nach[0]["position"] if nach else {}
    entry = float(pos.get("level") or res.get("level") or preis)
    st["open"] = {"dealId": pos.get("dealId") or deal_id(res), "side": side, "tag": d["tag"],
                  "signal_bar": d.get("signal_bar"), "einstieg_kerze": str(einstieg_kerze), "entry": entry,
                  "stop_level": pos.get("stopLevel") or order["stop_level"] or round(entry - side * stop_dist, dec),
                  "ziel_level": order["ziel_level"], "notstop": stop_dist is not None, "size": size, "lot": q.lot,
                  "currency": q.currency, "eur_rate": q.eur_rate, "opened_utc": pos.get("createdDateUTC") or lauf.stamp,
                  "konto_kurz": konten.kurz(aid)}
    lauf.ereignis(bot, "eröffnet", entry=entry, dealId=st["open"]["dealId"], **ev, **order)


# ---------------------------------------------------------------------------------------------------------------------
# Zwilling: Backtest-Motor auf den Capital.com-Kerzen des fertigen Tages

def ende_fuer(bot_id: str, kont: dict) -> dict | None:
    """Ist der Bot beendet? BEENDET (Kirons Vergleich 2025 bis heute) oder abgelöst durch die Prüfung nach 15/40
    Demo-Trades (suche/demo_pruefung.py, suche/VORAB_wechsel.yaml: journal/konten.json["abgeloest"]). Rückgabe:
    {"an": Nachfolger oder None (dann wird das Konto frei), "status": Text fürs Cockpit} oder None."""
    if bot_id in BEENDET:
        return BEENDET[bot_id]
    abl = kont.get("abgeloest") or {}
    if bot_id not in abl:
        return None
    a = abl[bot_id] or {}
    return {"an": a.get("an"), "status": "abgelöst" + (f" ({a['grund']})" if a.get("grund") else "")}


def uebergabe(kont: dict, alt: str, an: str | None, accounts: list[dict], stamp: str) -> dict | None:
    """Konto des beendeten Bots `alt` an `an`, ohne Nachfolger (an=None) in kont["frei"] (reine Funktion, ändert
    `kont`; gleiche Buchführung wie suche/demo_bots.uebergeben). Hat `an` schon ein Konto, passiert nichts. Rückgabe:
    Ereignis fürs Log."""
    from gold.bot import konten
    zu = kont.setdefault("zuordnung", {})
    aid = zu.get(alt)
    if not aid or (an and an in zu):
        return None
    zu.pop(alt)
    if an:
        zu[an] = aid
    elif str(aid) not in (kont.get("frei") or []):
        kont.setdefault("frei", []).append(str(aid))
    acc = next((a for a in accounts if str(a.get("accountId")) == str(aid)), {})
    bal = (acc.get("balance") or {}).get("balance")
    kont.setdefault("start", {})[str(aid)] = bal
    kont.setdefault("uebergaben", []).append({"zeit": stamp, "konto": konten.kurz(aid), "konto_id": str(aid),
                                              "name": acc.get("accountName"), "von": alt, "an": an, "kontostand": bal})
    for e in kont.get("konten") or []:
        if e.get("id") == konten.kurz(aid):
            e["fuer"] = an
    return {"konto": konten.kurz(aid), "name": acc.get("accountName"), "an": an, "kontostand": bal}


def _nach_ende(st: dict) -> str:
    if "uebergeben_an" not in st:
        return ""
    return f"; Konto an {st['uebergeben_an']} übergeben" if st["uebergeben_an"] else "; Konto freigegeben"


def beenden(lauf: Lauf, bot: Bot, st: dict, ende: dict, state: dict) -> None:
    """Ein beendeter oder abgelöster Bot (ende_fuer): nichts Neues; noch liegende Stop-Orders löschen; eine offene
    Position nach seinen Regeln zu Ende führen (Vortag: Stop, Ziel oder 16:46 New York; London: Stop, Ziel oder 17 Uhr
    London; Noise: Gegensignal, Notstop oder 17 Uhr London). Ist das Konto in seinem Markt leer, geht es an den
    Nachfolger oder wird frei."""
    from gold.bot import konten
    from suche.demo_bots import own_position
    aid = (lauf.kont.get("zuordnung") or {}).get(bot.bot_id)
    if not aid:
        st["status"] = ende["status"] + _nach_ende(st)
        return
    q = lauf.quote(bot.epic)
    lauf.positionen(aid)
    if bot.strategie == "vortag_stop_oco":
        lauf_vortag(lauf, bot, st, aid, q, neu=False)
        orders = st.get("orders")
        if orders and not st.get("open"):                      # noch nicht ausgelöst: nicht mehr nötig
            for s in ("long", "short"):
                if orders.get(s) and lauf.send:
                    loesche_order(lauf.client, orders[s]["dealId"])
            st["orders"] = None
            lauf.ereignis(bot, "Stop-Orders gelöscht (Bot beendet)")
    else:
        lauf_markt(lauf, bot, st, state, aid, q, neu=False)
    if st.get("open") or st.get("orders") or not lauf.send:
        st["status"] = ende["status"] + ("; Position läuft noch zu Ende" if st.get("open") else "")
        return
    konten.wechseln(lauf.client, aid)
    if own_position(lauf.client.positions(), bot.epic) or arbeitsorders(lauf.client, bot.epic):
        st["status"] = ende["status"] + "; wartet, bis im Konto nichts mehr offen ist"
        return
    ev = uebergabe(lauf.kont, bot.bot_id, ende.get("an"), lauf.accounts, lauf.stamp)
    if ev:
        lauf.ereignis(bot, "konto übergeben" if ende.get("an") else "konto frei", **ev)
        st["uebergeben_an"] = ende.get("an")
        for k in ("konto_id", "konto", "konto_name", "kontostand"):
            st[k] = None
    st["status"] = ende["status"] + _nach_ende(st)


def zwillinge(lauf: Lauf, state: dict, alle_trades: list[dict]) -> list[dict]:
    from suche import r6_zwilling as zw
    out = []
    zst = state.setdefault("zwilling", {})
    echte = {(b.strategie, b.epic) for b in BOTS}
    jobs = [(b, b.epic, False) for b in BOTS] + [(VORTAG, m, True) for m in VORTAG.schatten
                                                  if (VORTAG.strategie, m) not in echte]
    for bot, epic, schatten in jobs:
        key = f"{bot.strategie}|{epic}" + (f"|{bot.bot_id}" if bot.stop_atr else "")   # Mess-Bot: eigener Zwilling
        tag = fertiger_tag(bot.strategie, lauf.now)
        if tag is None or zst.get(key, "") >= tag:
            continue
        try:
            if bot.strategie == "noise_band":
                bars, sp = kerzen_zeitraum(lauf.client, epic, "MINUTE_15", 45, lauf.now)
            else:
                bars, sp = kerzen(lauf.client, epic, "MINUTE_15", 1000, lauf.now)
            schw = None
            if bot.strategie != "vortag_stop_oco":
                w = tageswerte(lauf, state, epic, str(rg.handelstag_ny17(pd.Timestamp(tag) + pd.Timedelta(hours=12)).date()))
                schw = w and w["schwankung"]
            z = zw.zwilling_tag(bot.strategie, epic, bars, sp, tag, schw, stop_atr=bot.stop_atr)
        except Exception as err:        # noqa: BLE001 - der Zwilling hält die Bots nie auf
            lauf.ereignis(bot, "Zwilling fehlgeschlagen", markt=epic, why=str(err)[:200])
            continue
        rec = {"tag": tag, "strategie": bot.strategie, "markt": epic, "schatten": schatten, "schwankung": schw,
               "tag_gezaehlt": z["tag_gezaehlt"], "trades": z["trades"], "berechnet_utc": lauf.stamp}
        if bot.stop_atr:
            rec.update(bot=bot.bot_id, stop_atr=bot.stop_atr)
        if not schatten:
            bt = [t for t in alle_trades if t.get("bot") == bot.bot_id and t.get("tag") == tag]
            rec["bot_trades"] = [{k: t.get(k) for k in ("einstieg_kerze", "side", "pct", "reason")} for t in bt]
            rec["konto"] = bool((state.get("bots") or {}).get(bot.bot_id, {}).get("konto_id"))
            rec["vergleich"] = zw.vergleiche(z["trades"], bt)
            # Vortag EUR/USD und GBP/USD ohne Konto: weiter als Schatten, wie bis zum 04.11.2026
            rec["schatten"] = ((bot.strategie == VORTAG.strategie and epic in VORTAG.schatten and not rec["konto"])
                               or ende_fuer(bot.bot_id, lauf.kont) is not None)
        out.append(rec)
        zst[key] = tag
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Ein Lauf

def run(client, state: dict, kont: dict, now, send_orders: bool = True,
        alte_trades: list[dict] | None = None) -> tuple[dict, list, list, list]:
    """Ein Lauf über alle Bots und den Zwilling. Rückgabe: Zustand, neue Trades, Log, neue Zwilling-Zeilen.
    `kont` (journal/konten.json) bekommt die Zuordnung der Bots."""
    from gold.bot import konten
    lauf = Lauf(client, now, kont, send_orders)
    state = json.loads(json.dumps(state or {}))
    bots_st = state.setdefault("bots", {})
    zw_neu: list[dict] = []
    client.login()
    lauf.accounts = client.accounts()
    lauf.haupt = konten.haupt_von(lauf.accounts, kont, getattr(client, "account_id", None))
    try:
        for bot in BOTS:
            st = bots_st.setdefault(bot.bot_id, {})
            try:
                ende = ende_fuer(bot.bot_id, kont)
                if ende:
                    beenden(lauf, bot, st, ende, state)
                    continue
                aid = konto_fuer(bot, lauf.accounts, kont, lauf.haupt, lambda a: not lauf.positionen(a))
                if aid is None:
                    st["status"] = ("wartet auf ein eigenes Demokonto (Kontolimit erreicht: Zuteilung nach dem "
                                    "Vergleich aller Strategien)")
                    continue
                if (kont.get("zuordnung") or {}).get(bot.bot_id) != aid:
                    kont.setdefault("zuordnung", {})[bot.bot_id] = aid
                    acc0 = next(a for a in lauf.accounts if str(a.get("accountId")) == aid)
                    kont.setdefault("start", {})[aid] = (acc0.get("balance") or {}).get("balance")
                    lauf.ereignis(bot, "konto zugeordnet", konto=konten.kurz(aid), name=acc0.get("accountName"))
                acc = next(a for a in lauf.accounts if str(a.get("accountId")) == aid)
                bal = acc.get("balance") or {}
                st.update(konto_id=aid, konto=konten.kurz(aid), konto_name=acc.get("accountName"),
                          kontostand=bal.get("balance"), waehrung=acc.get("currency"))
                st.setdefault("start_utc", lauf.stamp)
                st.setdefault("start_kontostand", bal.get("balance"))
                lauf.positionen(aid)
                q = lauf.quote(bot.epic)
                fremd = [p for p in lauf.positionen(aid) if (p.get("market") or {}).get("epic") != bot.epic]
                if fremd:
                    lauf.ereignis(bot, "andere Märkte auf dem Konto", anzahl=len(fremd))
                if bot.strategie == "vortag_stop_oco":
                    lauf_vortag(lauf, bot, st, aid, q)
                else:
                    lauf_markt(lauf, bot, st, state, aid, q)
                if st.get("open"):
                    st["status"] = "Position offen"
                elif st.get("orders"):
                    st["status"] = "Stop-Orders liegen"
                else:
                    st["status"] = "wartet auf das nächste Signal"
                if st.get("open"):
                    from suche.demo_bots import own_position
                    p = own_position(lauf.positionen(aid), bot.epic, {st["open"].get("dealId")})
                    st["position"] = ({"upl": p[0]["position"].get("upl"), "stop": p[0]["position"].get("stopLevel"),
                                       "ziel": p[0]["position"].get("profitLevel")} if p else None)
                else:
                    st["position"] = None
            except Exception as err:    # noqa: BLE001 - ein Bot stört nie die anderen
                st["status"] = f"Fehler: {str(err)[:160]}"
                lauf.ereignis(bot, "fehler", why=str(err)[:300])
            finally:
                st["stand_utc"] = lauf.stamp
        zw_neu = zwillinge(lauf, state, (alte_trades or []) + lauf.neu)
    finally:
        try:                            # am Ende ist wieder das Hauptkonto aktiv (der Gold-Bot erwartet es)
            konten.wechseln(client, lauf.haupt)
        except Exception as err:        # noqa: BLE001
            lauf.ereignis(None, "zurück aufs Hauptkonto fehlgeschlagen", why=str(err)[:160])
    state["stand_utc"] = lauf.stamp
    return state, lauf.neu, lauf.log, zw_neu


def cockpit(state: dict, trades: list[dict], zwilling: list[dict]) -> dict:
    bots = []
    for bot in BOTS:
        st = (state.get("bots") or {}).get(bot.bot_id, {})
        tr = [t for t in trades if t.get("bot") == bot.bot_id]
        zw = [z for z in zwilling if z.get("strategie") == bot.strategie and z.get("markt") == bot.epic
              and z.get("stop_atr") == bot.stop_atr]
        abw = [z for z in zw if z.get("konto") and not (z.get("vergleich") or {}).get("gleich", True)]
        bots.append({"bot": bot.bot_id, "titel": bot.titel, "epic": bot.epic, "regel": bot.regel,
                     "backtest": bot.backtest, "konto_vorschlag": bot.konto_vorschlag, "konto": st.get("konto"),
                     "konto_name": st.get("konto_name"), "kontostand": st.get("kontostand"),
                     "start_kontostand": st.get("start_kontostand"), "start_utc": st.get("start_utc"),
                     "status": st.get("status"), "offen": st.get("open"), "orders": st.get("orders"),
                     "position": st.get("position"), "letzte_entscheidung": st.get("letzte_entscheidung"),
                     "zusammenfassung": zusammenfassung(tr), "letzte_trades": tr[-10:],
                     "zwilling": {"tage": len(zw), "abweichungen": len(abw), "zusammenfassung": zusammenfassung(
                         [{"pct": t["pct"]} for z in zw for t in z.get("trades", []) if t.get("zaehlt")]),
                         "letzte": zw[-5:]}})
    schatten = []
    for m in VORTAG.schatten:
        zw = [z for z in zwilling if z.get("strategie") == VORTAG.strategie and z.get("markt") == m
              and not z.get("stop_atr")]
        schatten.append({"markt": m, "strategie": VORTAG.strategie, "tage": len(zw),
                         "zusammenfassung": zusammenfassung([{"pct": t["pct"]} for z in zw for t in z.get("trades", [])
                                                             if t.get("zaehlt")]), "letzte": zw[-5:]})
    return {"stand_utc": state.get("stand_utc"), "titel": "Runde-6-Bots (Demo)", "bots": bots, "schatten": schatten,
            "vorab": "suche/VORAB_r6_demo.yaml"}


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []


def _anhaengen(path: Path, zeilen: list[dict]) -> None:
    if zeilen:
        with open(path, "a", encoding="utf-8") as fh:
            fh.writelines(json.dumps(z, ensure_ascii=False, default=str) + "\n" for z in zeilen)


def main(argv: list[str]) -> int:
    from gold.bot import konten
    from gold.bot.capital import CapitalClient
    from gold.bot.runner import CRED_KEYS, clean_credentials

    creds = clean_credentials({k: os.environ.get(k, "") for k in CRED_KEYS})
    if not all(creds):
        print("Keine Capital.com-Zugangsdaten, Runde-6-Bots übersprungen")
        return 0
    dry = "--dry-run" in argv
    JDIR.mkdir(parents=True, exist_ok=True)
    spath = JDIR / "state.json"
    state = json.loads(spath.read_text(encoding="utf-8")) if spath.exists() else {}
    alte = _jsonl(JDIR / "trades.jsonl")
    kont = konten.load()
    client = CapitalClient(*creds, environment="demo")      # fest Demo: Live gibt es hier nicht
    try:
        st, neu, log, zw = run(client, state, kont, datetime.now(timezone.utc), send_orders=not dry, alte_trades=alte)
    finally:
        try:
            client.logout()
        except Exception:               # noqa: BLE001, S110 - Abmelden darf scheitern
            pass
    if dry:                             # Trockenlauf: nichts speichern
        print(json.dumps({"trockenlauf": True, "bots": {k: {x: v.get(x) for x in ("status", "konto", "letzte_entscheidung")}
                                                         for k, v in st.get("bots", {}).items()},
                          "log": log, "zwilling": zw}, ensure_ascii=False, indent=1, default=str))
        return 0
    _anhaengen(JDIR / "trades.jsonl", neu)
    _anhaengen(JDIR / "log.jsonl", log)
    _anhaengen(JDIR / "zwilling.jsonl", zw)
    if any((kont.get("zuordnung") or {}).get(b.bot_id) for b in BOTS):
        konten.save(kont)
    spath.write_text(json.dumps(st, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    COCKPIT.write_text(json.dumps(cockpit(st, alte + neu, _jsonl(JDIR / "zwilling.jsonl")), ensure_ascii=False, indent=1,
                                  default=str) + "\n", encoding="utf-8")
    print(json.dumps({"neue_trades": len(neu), "log": log, "zwilling": len(zw)}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
