"""Bündel: kopiert die Trades laufender Demo-Bots auf ein Capital.com-DEMOKONTO. Nie echtes Geld.

    python -m suche.buendel_bot              # ein Lauf: Kopien führen, neue Trades der Mitglieder kopieren
    python -m suche.buendel_bot --dry-run    # nur rechnen und zeigen, keine Order
    python -m suche.buendel_bot --regel suche/VORAB_gold_buendel_bot.yaml   # ein anderes Bündel derselben Art

Welches Bündel ein Lauf führt, sagt seine Regeldatei (bot_id, Mitglieder). Seit Kirons Wahl vom 26.11.2026 09:59 UTC
("Zwei Bündel auf einem Konto") laufen zwei Bündel auf "Vortag USDJPY": das Gold-Bündel (gold-buendel, die drei
Gold-Bots, suche/VORAB_gold_buendel_bot.yaml) und buendel9 ohne Gold (die sechs anderen,
suche/VORAB_buendel9_ohne_gold.yaml). Jedes hält die Kopien des anderen für fremd und fasst sie nie an.

Kirons Wahl vom 20.11.2026 16:20 UTC auf der Karte "Wie soll das Bündel aller Strategien jetzt auf Demo laufen?": "Ein
Konto mit 9 Bots". Davor sein Wunsch 15:57 UTC: ein Bot, der alle Strategien gleichzeitig mit demselben Geld handelt.
Seit 16:27 UTC ist die Zahl der Demokonten voll, darum teilt das Bündel das Konto "Vortag USDJPY" mit dem Kern-Bot
Vortag GBP/USD (anderer Markt) und dem ruhenden pine-hand. Regeln, Zahlen und Urteil stehen in
suche/VORAB_buendel9_bot.yaml, Prüfsumme im Protokoll vor der ersten Kopie. Ohne passende Prüfsumme kopiert der Bot
nichts Neues.

Was ein Lauf tut (alle 15 Minuten im Lauf demo-bots.yml, nach den Bots dieses Laufs):
- Er liest aus den Dateien der Mitglieder ihre offenen Trades (Deal-ID und Konto) und beim Broker auf deren Konten
  die Positionen dazu (Richtung, Stop, Ziel, Eröffnung). Er ändert dort nichts.
- Jeder Trade eines Mitglieds, der höchstens 30 Minuten alt ist, bekommt eine Kopie auf "Vortag USDJPY": dieselbe
  Richtung, derselbe Stop-Kurs, dasselbe Ziel, Größe für 7 € Risiko bis zum Stop. Eine Kopie je Trade, eine
  gescheiterte Order wird nie wiederholt. Einen Trade, den das andere Bündel des Kontos schon kopiert hat, kopiert
  er nicht noch einmal.
- Ändert die Quelle Stop oder Ziel, gleicht er die Kopie an. Ist der Trade der Quelle zu, schließt er die Kopie.
- Konto-Wächter: Margin aller Kopien höchstens 50 % von gedachten 700 € plus Ergebnis, beim Broker bleiben nach jeder
  Kopie mindestens 250 € frei, ab 30 % unter dem Höchststand nichts Neues mehr. Ohne Hedging höchstens eine Kopie je
  Markt. Ein Mitglied mit 40 Demo-Trades und Gewinnfaktor unter 1,2 bekommt keine neuen Kopien mehr.
- Er kennt seine Kopien an der Deal-ID und fasst nie eine fremde Position an. Findet er eine Kopie unter ihrer Deal-ID
  nicht, sucht er sie nach Markt, Richtung, Größe und Eröffnungszeit, bevor er sie als geschlossen bucht (Fehler bis
  26.11.2026, siehe passende_position).
- Er schreibt nur journal/<bot_id>/ und journal/<bot_id>.json (buendel9 oder gold-buendel).
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import json
import math
import os
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from gold.bot.konten import HAUPT_ENDUNG  # Hauptkonto des Gold-Bots, hier nie handeln

ROOT = Path(__file__).resolve().parents[1]
J = ROOT / "journal"
BOT_ID = "buendel9"
NAME = "Bündel aus 9 Bots"
KONTO_NAME = "Vortag USDJPY"          # geteilt mit r6-vortag-gbpusd (GBPUSD) und pine-hand (ruht)
SPERR_MAERKTE = ("GBPUSD",)            # Märkte der anderen Bots dieses Kontos, hier nie eine Kopie
VORAB = ROOT / "suche" / "VORAB_buendel9_bot.yaml"            # die erste Regel von buendel9 (bis 26.11.2026)
KEY = "VORAB_buendel9_bot sha256 "
VORAB_OHNE_GOLD = ROOT / "suche" / "VORAB_buendel9_ohne_gold.yaml"   # buendel9 seit Kirons Wahl vom 26.11.2026
KEY_OHNE_GOLD = "VORAB_buendel9_ohne_gold sha256 "
VORAB_GOLD = ROOT / "suche" / "VORAB_gold_buendel_bot.yaml"          # das Gold-Bündel seit Kirons Wahl vom 26.11.2026
KEY_GOLD = "VORAB_gold_buendel_bot sha256 "
GOLD_ID = "gold-buendel"
BUENDEL = (BOT_ID, GOLD_ID)            # alle Bündel auf "Vortag USDJPY": jedes hält die Kopien der anderen für fremd
JDIR = J / "buendel9"
COCKPIT = J / "buendel9.json"
FREMDE_DATEIEN = ("gold-trades.jsonl", "gold-state.json", "konten.json", "r6-bots.json", "vergleich.json")
SCHLUSS_WARTEN = pd.Timedelta(hours=1)  # so lange sucht der Bot den Schlusskurs einer Kopie beim Broker, dann schätzt er
GESCHAETZT = "beim Broker zu, Schlusskurs geschätzt (Stop)"
ZUORDNUNG = pd.Timedelta(minutes=5)    # so weit darf die Eröffnung beim Broker neben der Uhrzeit der Kopie liegen
NACHPRUEFEN = pd.Timedelta(days=30)    # so lange sucht er eine als geschätzt gebuchte Kopie noch unter seinen Positionen
GESEHEN_TAGE = 3                       # so lange merkt er sich Trades, die er nicht kopiert hat
HEDGING_WIEDER = pd.Timedelta(hours=1)
FMT = "%Y-%m-%dT%H:%M:%S"
SEITE = {1: "Kauf", -1: "Verkauf"}
REGEL = ("Kopiert jeden neuen Trade von 9 Demo-Bots (Gold-Bot C/B, Gold-Zonen, Gold 4-Std.-Ausbruch, Rücksetzer US500 "
         "und US100, Noise-Band Nasdaq, Scalper DAX und Nasdaq, 4-Std.-Ausbruch DAX/FTSE/Nikkei) mit 7 € Risiko auf "
         "gedachte 700 €. Stop und Ziel wie die Quelle, raus, wenn die Quelle rausgeht. Konto-Wächter: Margin höchstens "
         "50 % des Kontostands, Bremse ab 30 % Rückgang.")
TEST = ("Backtest November 2024 bis Oktober 2026 (Auskunft): 993 von 996 Trades passen durch den Wächter, +76,5 € im "
        "Monat auf 700 € (10,9 % Rendite pro Monat), schlimmster Rückgang 149 €, 6 von 24 Monaten im Minus. Die 9 sind "
        "an denselben Monaten ausgesucht, live wird es weniger. 47 % des Gewinns kamen von den Scalpern, deren Test "
        "durchgefallen ist.")


# --------------------------------------------------------------------------------------------------------------------
# Regel und Konto

def lade_regel(pfad: Path = VORAB) -> dict:
    """Der Abschnitt der Regeldatei, benannt wie die Datei ohne "VORAB_" (VORAB_buendel9_bot.yaml: buendel9_bot)."""
    import yaml
    return yaml.safe_load(Path(pfad).read_text(encoding="utf-8"))[Path(pfad).stem.removeprefix("VORAB_")]


def vorab_ok(pfad: Path = VORAB) -> bool:
    """Ist die Regeldatei versiegelt (letzte Zeile im Protokoll mit ihrer Prüfsumme)? Nur dann kopiert der Bot."""
    from suche.runde1 import journal_lines, last_value, sha256_text
    pfad = Path(pfad)
    if not pfad.exists():
        return False
    return last_value(journal_lines(), f"{pfad.stem} sha256 ") == sha256_text(pfad.read_text(encoding="utf-8"))


def bot_id(regel: dict) -> str:
    return str(regel.get("bot_id") or BOT_ID)


def fremde_kopien(eigen: str, jdir: Path = J) -> dict[str, dict]:
    """Die offenen Kopien der anderen Bündel auf demselben Konto (aus ihrem state.json), Trade der Quelle -> Kopie.
    Ihre Positionen fasst das Bündel nie an, auch nicht beim Wiederfinden einer Kopie (passende_position), ihre Trades
    kopiert es nicht ein zweites Mal, und ohne Hedging zählen ihre Märkte wie eigene Kopien."""
    out: dict[str, dict] = {}
    for b in BUENDEL:
        if b == eigen:
            continue
        pfad = jdir / b / "state.json"
        with contextlib.suppress(OSError, ValueError, AttributeError):
            daten = json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else {}
            out.update({str(qd): dict(k) for qd, k in (daten.get("kopien") or {}).items() if isinstance(k, dict)})
    return out


def konto_id(konten_daten: dict | None = None) -> str:
    """Die volle Kontonummer von "Vortag USDJPY" aus journal/konten.json, gesucht nach dem Namen. Leer, wenn es das
    Konto dort nicht genau einmal gibt. Die Nummer wird nie abgetippt und nie ausgegeben."""
    from suche.mitnutzer import konto_nach_name
    return konto_nach_name(KONTO_NAME, konten_daten)


KONTO = konto_id()


def _norm(text) -> str:
    return unicodedata.normalize("NFC", str(text or "")).strip().casefold()


def _num(x) -> float | None:
    try:
        return None if x is None or x == "" else float(x)
    except (TypeError, ValueError):
        return None


def _jetzt(now: datetime) -> pd.Timestamp:
    t = pd.Timestamp(now)
    return t.tz_convert("UTC").tz_localize(None) if t.tzinfo else t


def _zeit(x) -> pd.Timestamp | None:
    try:
        t = pd.Timestamp(str(x).replace("Z", ""))
    except (TypeError, ValueError):
        return None
    return t.tz_convert("UTC").tz_localize(None) if t.tzinfo else t


def deal_aus_bestaetigung(conf: dict | None) -> str:
    """Die Deal-ID der Position aus der Bestätigung einer Order. Capital.com schreibt oben die Deal-ID der Order und
    unter affectedDeals die der Position, die beiden sind verschieden. Bis zum 26.11.2026 nahm das Bündel die obere:
    Unter ihr fand es keine seiner 7 Kopien unter seinen Positionen und buchte jede nach gut einer Stunde mit -1 R als
    "beim Broker zu", obwohl vier davon noch offen lagen. Die anderen Bots nehmen wie hier zuerst affectedDeals."""
    conf = conf or {}
    return str((conf.get("affectedDeals") or [{}])[0].get("dealId") or conf.get("dealId") or "")


def passende_position(k: dict, eigene: dict, vergeben: set[str]) -> str | None:
    """Die eigene Position zu einer Kopie, deren Deal-ID unter den Positionen fehlt: derselbe Markt, dieselbe Richtung,
    dieselbe Größe, beim Broker höchstens 5 Minuten neben der Uhrzeit der Kopie eröffnet, nie GBPUSD (Vortag GBP/USD)
    und keiner anderen Kopie zugeordnet. Nur bei genau einem Treffer die Deal-ID, sonst None."""
    auf = _zeit(k.get("opened_utc"))
    if auf is None or k.get("epic") in SPERR_MAERKTE:
        return None
    seite = "BUY" if int(k["richtung"]) > 0 else "SELL"
    treffer = []
    for did, p in eigene.items():
        pos, mk = p.get("position") or {}, p.get("market") or {}
        epic = str(mk.get("epic") or pos.get("epic") or "")
        if did in vergeben or epic != k.get("epic") or epic in SPERR_MAERKTE:
            continue
        size = _num(pos.get("size"))
        if str(pos.get("direction")).upper() != seite or size is None or abs(size - float(k["size"])) > 1e-9:
            continue
        eroeffnet = _zeit(pos["createdDateUTC"]) if pos.get("createdDateUTC") else None   # nie die Ortszeit
        if eroeffnet is not None and abs(eroeffnet - auf) <= ZUORDNUNG:
            treffer.append(did)
    return treffer[0] if len(treffer) == 1 else None


# --------------------------------------------------------------------------------------------------------------------
# Die Mitglieder: offene Trades aus ihren eigenen Dateien (ohne Netz)

def _konto_aus_code(modul: str) -> str:
    import importlib
    return str(getattr(importlib.import_module(modul), "KONTO", "") or "")


def _feld(daten: dict, feld: str) -> list[dict]:
    """Die offenen Trades unter `feld` (Punkt-Pfad, * = alle Einträge einer Ebene)."""
    stufe: list = [daten]
    for teil in feld.split("."):
        neu: list = []
        for x in stufe:
            if not isinstance(x, dict):
                continue
            neu += list(x.values()) if teil == "*" else [x.get(teil)]
        stufe = neu
    return [x for x in stufe if isinstance(x, dict) and x.get("dealId")]


def quell_deals(regel: dict, jdir: Path = J, konten_daten: dict | None = None) -> tuple[list[dict], set[str], list[str]]:
    """Offene Trades der Mitglieder: [{bot, konto, dealId}], die Mitglieder, deren Datei lesbar war, und Fehler.

    Das Konto kommt aus dem Code des Mitglieds (Konstante KONTO), aus seiner Datei (konto_id) oder ist das Hauptkonto
    (gold-cb). Ein Mitglied ohne lesbare Datei oder ohne Konto zählt als nicht gelesen: dann schließt der Bot keine
    Kopie dieses Mitglieds, weil er nicht weiß, ob die Quelle noch offen ist."""
    if konten_daten is None:
        from gold.bot import konten
        konten_daten = konten.load()
    out, gelesen, fehler = [], set(), []
    for bot, m in {**(regel.get("mitglieder") or {}), **(regel.get("auslaufend") or {})}.items():
        pfad = jdir / m["datei"]
        try:
            daten = json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else {}
            art = str(m["konto"])
            if art == "haupt":
                konto = str((konten_daten or {}).get("haupt") or "")
            elif art == "konto_id":
                konto = str(daten.get("konto_id") or "")
            else:
                konto = _konto_aus_code(art)
        except Exception as err:            # noqa: BLE001 - ein Mitglied hält die anderen nie auf
            fehler.append(f"{bot}: {type(err).__name__}")
            continue
        trades = _feld(daten, m["feld"])
        if trades and not konto:
            fehler.append(f"{bot}: kein Konto")
            continue
        gelesen.add(bot)
        out += [{"bot": bot, "konto": konto, "dealId": str(t["dealId"])} for t in trades]
    return out, gelesen, fehler


def mitglieder_raus(regel: dict, vergleich: dict | None) -> dict[str, str]:
    """Mitglieder, die ihr eigenes Urteil nicht bestanden haben (VORAB_wechsel: 40 Trades, Gewinnfaktor unter 1,2),
    aus journal/vergleich.json, und auslaufende Mitglieder der Regeldatei (nur ihre offenen Kopien laufen zu Ende).
    Bot -> Grund."""
    w = (regel.get("waechter") or {}).get("mitglied_raus") or {}
    n, pf_min = int(w.get("trades", 40)), float(w.get("gewinnfaktor_unter", 1.2))
    zeilen = list((vergleich or {}).get("rangliste") or []) + list((vergleich or {}).get("wunsch") or [])
    out = {b: str((m or {}).get("grund") or "läuft aus") for b, m in (regel.get("auslaufend") or {}).items()}
    for z in zeilen:
        bid = z.get("id")
        if bid not in (regel.get("mitglieder") or {}) or bid in out:
            continue
        ist = z.get("ist") or {}
        trades, pf = int(ist.get("trades") or 0), _num(ist.get("pf_r"))
        if trades >= n and pf is not None and pf < pf_min:
            out[bid] = f"{trades} Demo-Trades, Gewinnfaktor {pf:.2f} unter {pf_min:.1f}"
    return out


# --------------------------------------------------------------------------------------------------------------------
# Größe und Margin (ohne Netz)

def euro_je_punkt(q) -> float:
    """So viele Euro ist eine Größe von 1 je Kurspunkt wert."""
    return (q.lot or 1) / (q.eur_rate or 1)


def groesse(risiko_eur: float, dist: float, q, faktor: float) -> tuple[float | None, str]:
    """Größe für risiko_eur bis zum Stop, auf die Schrittweite abgerundet, mindestens die kleinste Größe. None, wenn
    der Euro-Kurs fehlt oder die kleinste Größe mehr als faktor mal risiko_eur riskieren würde."""
    if not q.eur_rate or dist <= 0:
        return None, "Euro-Kurs oder Stop-Abstand fehlt"
    je = dist * euro_je_punkt(q)
    step = q.size_step or q.min_size
    roh = risiko_eur / je
    size = round(max(math.floor(round(roh / step, 9)) * step, q.min_size), 8)
    if size * je > faktor * risiko_eur:
        return None, f"kleinste Größe zu grob ({size * je:.2f} € Risiko statt {risiko_eur:.0f} €)"
    return size, ""


def margin_eur(size: float, kurs: float, q) -> float:
    return size * kurs * euro_je_punkt(q) * q.margin_pct / 100


def _rund(x: float, q) -> float:
    return round(float(x), q.decimals if q.decimals < 6 else 2)


# --------------------------------------------------------------------------------------------------------------------
# Ein Lauf

class Lauf:
    """Ein Lauf. Alle Order-, Änderungs- und Schließ-Aufrufe gehen über diese Klasse, damit ein Trockenlauf
    (send_orders=False) nichts beim Broker ändert."""

    def __init__(self, client, state: dict, now: datetime, regel: dict, send_orders: bool = True,
                 siegel: bool = True):
        self.client = client
        self.st = copy.deepcopy(state or {})
        self.now = _jetzt(now)
        self.stamp = self.now.strftime(FMT)
        self.regel = regel
        self.send = send_orders
        self.siegel = siegel
        self.bot_id = bot_id(regel)
        self.fremde: dict[str, dict] = {}   # offene Kopien der anderen Bündel auf diesem Konto (fremde_kopien)
        self.erster_lauf = not (state or {}).get("start")
        self.log: list[dict] = []
        self.fertige: list[dict] = []
        self.kurse: dict = {}
        self.quotes: dict = {}
        g = regel["geld"]
        self.kapital, self.risiko, self.faktor = float(g["kapital_eur"]), float(g["risiko_eur"]), float(g["max_risiko_faktor"])
        w = regel["waechter"]
        self.margin_anteil, self.bremse = float(w["margin_anteil"]), float(w["bremse_rueckgang"])
        self.frei_danach = float(w.get("frei_danach_eur", 0))
        self.frist = pd.Timedelta(minutes=int(regel["kopieren"]["frist_minuten"]))
        for k, v in (("format", 1), ("start", self.stamp), ("kopien", {}), ("gesehen", {}), ("summe_eur", 0.0),
                     ("summe_r", 0.0), ("trades", 0)):
            self.st.setdefault(k, v)
        self.st.setdefault("hoechst", self.stand())

    @property
    def fremd(self) -> set[str]:
        """Deal-IDs der Kopien der anderen Bündel: fremde Positionen."""
        return {str(k["dealId"]) for k in self.fremde.values() if k.get("dealId")}

    def ev(self, event: str, **kw) -> None:
        self.log.append({"time": self.stamp, "event": event, **kw})

    def stand(self) -> float:
        """Gedachter Kontostand: 700 € plus das Ergebnis aller fertigen Kopien seit dem Start."""
        return round(self.kapital + float(self.st.get("summe_eur") or 0), 2)

    def neue_regel(self, name: str) -> None:
        """Merkt sich die Regeldatei des Laufs. Wechselt sie (Kirons Wahl vom 26.11.2026: buendel9 ohne Gold), steht
        der Wechsel mit Zeit in st["regeln"] und st["regel_seit"]. Kontostand, Höchststand, Bremse und Zählung laufen
        weiter wie bisher: das Urteil zählt nach VORAB_aufstieg_alle.yaml alle Kopien in journal/<bot>/trades.jsonl seit
        dem Start. Ein Zustand mit Start, aber ohne Eintrag, lief unter der ersten Regel von buendel9."""
        alt = self.st.get("vorab") or (VORAB.name if not self.erster_lauf and self.bot_id == BOT_ID else None)
        if alt and alt != name:
            self.st.setdefault("regeln", []).append({"vorab": alt, "bis": self.stamp})
            self.st["regel_seit"] = self.stamp
            self.ev("neue Regel", alt=alt, neu=name)
        self.st["vorab"] = name

    def nur_mein_konto(self) -> None:
        if not KONTO or str(self.client.account_id) != KONTO:
            raise RuntimeError(f"aktives Konto ist nicht {KONTO_NAME}, nichts gesendet")

    def quote(self, epic: str):
        from suche.demo_bots import eur_rate, quote_from_market
        if epic not in self.quotes:
            q = quote_from_market(self.client.market(epic), None)
            q.eur_rate = eur_rate(self.client, q.currency, self.kurse)
            self.quotes[epic] = q
        return self.quotes[epic]

    def merke(self, quelle_deal: str, bot: str, grund: str) -> None:
        if quelle_deal not in self.st["gesehen"]:
            self.st["gesehen"][quelle_deal] = {"bot": bot, "zeit": self.stamp, "grund": grund}
            self.ev("nicht kopiert", quelle=bot, quelle_deal=quelle_deal, grund=grund)

    def aufraeumen(self, noch_offen: set[str]) -> None:
        """Nicht kopierte Trades vergisst er nach 3 Tagen, aber nur, wenn die Quelle sie nicht mehr offen hat."""
        grenze = self.now - pd.Timedelta(days=GESEHEN_TAGE)
        self.st["gesehen"] = {k: v for k, v in self.st["gesehen"].items()
                              if k in noch_offen or (_zeit(v.get("zeit")) or self.now) >= grenze}

    # ---- Hedging ----

    def hedging_an(self) -> bool:
        """Ist der Hedging-Modus des Kontos an? Wenn nicht, einschalten (höchstens einmal je Stunde versuchen). Ohne
        Hedging gilt: höchstens eine Kopie je Markt."""
        try:
            an = bool((self.client._get("/accounts/preferences") or {}).get("hedgingMode"))
        except Exception as err:            # noqa: BLE001 - dann ohne Hedging
            self.ev("Hedging nicht lesbar", fehler=str(err)[:200])
            return False
        if an or not self.send:
            self.st["hedging"] = an
            return an
        letzt = _zeit(self.st.get("hedging_versuch"))
        if letzt is not None and self.now - letzt < HEDGING_WIEDER:
            return False
        self.st["hedging_versuch"] = self.stamp
        try:
            self.nur_mein_konto()
            self.client._request("PUT", "/accounts/preferences", json={"hedgingMode": True})
            an = bool((self.client._get("/accounts/preferences") or {}).get("hedgingMode"))
        except Exception as err:            # noqa: BLE001
            self.ev("Hedging nicht eingeschaltet", fehler=str(err)[:200])
            an = False
        if an:
            self.ev("Hedging eingeschaltet")
        self.st["hedging"] = an
        return an

    # ---- Kopien führen ----

    def buche(self, k: dict, level: float, grund: str, wann: pd.Timestamp, geschaetzt: bool = False) -> None:
        d = int(k["richtung"])
        dist = abs(float(k["entry"]) - float(k["stop_start"]))
        r = d * (level - float(k["entry"])) / dist if dist else 0.0
        eur = d * (level - float(k["entry"])) * float(k["size"]) * float(k["lot"]) / float(k["eur_rate"] or 1)
        rec = {"id": self.bot_id, "quelle": k["quelle"], "quelle_deal": k["quelle_deal"], "dealId": k["dealId"],
               "epic": k["epic"], "richtung": d, "size": k["size"], "entry": k["entry"], "stop_start": k["stop_start"],
               "stop": k.get("stop"), "ziel": k.get("ziel"), "exit": round(float(level), 6), "grund": grund,
               "geschaetzt": geschaetzt, "opened_utc": k["opened_utc"], "closed_utc": wann.strftime(FMT),
               "risiko_eur": k.get("risiko_eur"), "r": round(r, 4), "eur": round(eur, 2)}
        self.fertige.append(rec)
        del self.st["kopien"][k["quelle_deal"]]
        self.ev("Kopie zu", quelle=k["quelle"], dealId=k["dealId"], kurs=rec["exit"], grund=grund, r=rec["r"],
                eur=rec["eur"], geschaetzt=geschaetzt)
        self.st["summe_eur"] = round(float(self.st["summe_eur"]) + eur, 2)
        self.st["summe_r"] = round(float(self.st["summe_r"]) + r, 4)
        self.st["trades"] = int(self.st["trades"]) + 1
        self.st["hoechst"] = max(float(self.st.get("hoechst") or self.kapital), self.stand())
        if not self.st.get("gebremst") and self.stand() <= float(self.st["hoechst"]) * (1 - self.bremse):
            self.st["gebremst"] = {"zeit": self.stamp, "stand": self.stand(), "hoechst": self.st["hoechst"]}
            self.ev("Bremse", stand=self.stand(), hoechst=self.st["hoechst"])

    def schliesse(self, k: dict, warum: str) -> None:
        if not self.send:
            self.ev("würde schließen", dealId=k["dealId"], warum=warum)
            return
        try:
            self.nur_mein_konto()
            conf = self.client.close_position(k["dealId"])
        except Exception as err:            # noqa: BLE001 - nächster Lauf versucht es wieder, der Stop liegt beim Broker
            self.ev("schließen fehlgeschlagen", dealId=k["dealId"], warum=warum, fehler=str(err)[:200])
            return
        if str((conf or {}).get("dealStatus") or "").upper() == "REJECTED":
            self.ev("schließen abgelehnt", dealId=k["dealId"], warum=warum, grund=(conf or {}).get("reason"))
            return
        level = _num((conf or {}).get("level"))
        if level is None:
            q = self.quote(k["epic"])
            level = q.bid if int(k["richtung"]) > 0 else q.offer
        self.buche(k, level, warum, self.now)

    def angleichen(self, k: dict, stop: float | None, ziel: float | None) -> None:
        if stop is None:
            return
        q = self.quote(k["epic"])
        body = {"stopLevel": _rund(stop, q)}
        if ziel is not None:
            body["profitLevel"] = _rund(ziel, q)
        if not self.send:
            self.ev("würde angleichen", dealId=k["dealId"], **body)
            return
        try:
            self.nur_mein_konto()
            ref = self.client._request("PUT", f"/positions/{k['dealId']}", json=body).json().get("dealReference")
            conf = self.client.confirm(ref) if ref else {}
        except Exception as err:            # noqa: BLE001 - der nächste Lauf versucht es wieder
            self.ev("angleichen fehlgeschlagen", dealId=k["dealId"], fehler=str(err)[:200])
            return
        if conf and str(conf.get("dealStatus") or "").upper() == "REJECTED":
            self.ev("angleichen abgelehnt", dealId=k["dealId"], grund=conf.get("reason"))
            return
        k["stop"], k["ziel"] = body["stopLevel"], body.get("profitLevel")
        k["stop_quelle"], k["ziel_quelle"] = stop, ziel
        self.ev("angeglichen", quelle=k["quelle"], dealId=k["dealId"], **body)

    def fuehren(self, deals: list[dict], gelesen: set[str], quell_pos: dict, konten_ok: set[str],
                eigene: dict) -> None:
        """Jede offene Kopie: beim Broker zu (buchen), Quelle zu (schließen) oder Stop und Ziel angleichen."""
        offen_quelle = {d["dealId"] for d in deals}
        vergeben = {k["dealId"] for k in self.st["kopien"].values() if k["dealId"] in eigene} | self.fremd
        for qd, k in list(self.st["kopien"].items()):
            if k["dealId"] not in eigene:
                neu = passende_position(k, eigene, vergeben)
                if neu is None:
                    self.weg(k)
                    continue
                self.ev("Deal-ID berichtigt", quelle=k["quelle"], quelle_deal=qd, alt=k["dealId"], dealId=neu)
                k["dealId"] = neu
                vergeben.add(neu)
            k.pop("weg_seit", None)
            if k["quelle"] in gelesen and qd not in offen_quelle:
                self.schliesse(k, "Quelle zu")
                continue
            if k.get("quelle_konto") in konten_ok and qd not in quell_pos:
                self.schliesse(k, "Quelle beim Broker zu")
                continue
            p = (quell_pos.get(qd) or {}).get("position") or {}
            stop, ziel = _num(p.get("stopLevel")), _num(p.get("profitLevel"))
            if p and (stop != _num(k.get("stop_quelle")) or ziel != _num(k.get("ziel_quelle"))):
                self.angleichen(k, stop, ziel)

    def weg(self, k: dict) -> None:
        """Die Kopie ist beim Broker zu (Stop oder Ziel). Schlusskurs aus der Kontoaktivität, nach 1 Std. geschätzt."""
        from suche.demo_bots import broker_exit
        level, quelle = broker_exit(self.client, {"dealId": k["dealId"], "opened_utc": k["opened_utc"]},
                                    self.now.to_pydatetime())
        if level is not None:
            self.buche(k, float(level), {"SL": "Stop", "TP": "Ziel"}.get(quelle, quelle or "beim Broker zu"), self.now)
            return
        seit = _zeit(k.get("weg_seit"))
        if seit is None:
            k["weg_seit"] = self.stamp
            return
        if self.now - seit >= SCHLUSS_WARTEN:
            self.buche(k, float(k.get("stop") or k["stop_start"]), GESCHAETZT, self.now, geschaetzt=True)

    def nachpruefen(self, gebucht: list[dict], eigene: dict, deals: list[dict]) -> None:
        """Als geschätzt gebuchte Kopien der letzten 30 Tage, deren Position noch offen liegt (Fehler der Deal-ID bis
        26.11.2026, siehe deal_aus_bestaetigung): Er führt die Kopie wieder und nimmt die falsche Buchung zurück. Sie
        kommt aus trades.jsonl nach storniert.jsonl (schreiben). Ist die Quelle schon zu, schließt fuehren die Kopie
        danach wie jede andere zum Markt. Liegt keine passende Position mehr offen, bleibt die Buchung, wie sie ist."""
        storniert = {(s["dealId"], s["quelle_deal"]) for s in self.st.get("storniert") or []}
        vergeben = {k["dealId"] for k in self.st["kopien"].values()} | self.fremd
        konto_von = {d["dealId"]: d["konto"] for d in deals}
        for t in gebucht:
            qd = t.get("quelle_deal")
            zu = _zeit(t.get("closed_utc"))
            if (not t.get("geschaetzt") or t.get("grund") != GESCHAETZT or not qd or qd in self.st["kopien"]
                    or (t.get("dealId"), qd) in storniert or zu is None or self.now - zu > NACHPRUEFEN):
                continue
            did = passende_position(t, eigene, vergeben)
            if did is None:
                continue
            try:
                q = self.quote(t["epic"])
            except Exception as err:        # noqa: BLE001 - der nächste Lauf versucht es wieder
                self.ev("Kopie nicht wieder geführt", quelle_deal=qd, fehler=str(err)[:200])
                continue
            pos = eigene[did].get("position") or {}
            stop, ziel = _num(pos.get("stopLevel")), _num(pos.get("profitLevel"))
            self.st["kopien"][qd] = {
                "quelle": t["quelle"], "quelle_deal": qd, "epic": t["epic"], "richtung": int(t["richtung"]),
                "size": t["size"], "stop": stop, "ziel": ziel,
                "margin_eur": round(margin_eur(float(t["size"]), float(t["entry"]), q), 2),
                "risiko_eur": t.get("risiko_eur"), "dealId": did, "entry": t["entry"], "stop_start": t["stop_start"],
                "stop_quelle": stop, "ziel_quelle": ziel, "quelle_konto": konto_von.get(qd), "lot": q.lot,
                "eur_rate": q.eur_rate, "opened_utc": t["opened_utc"], "wieder_seit": self.stamp}
            self.st["gesehen"].pop(qd, None)
            vergeben.add(did)
            self.st["summe_eur"] = round(float(self.st["summe_eur"]) - float(t.get("eur") or 0), 2)
            self.st["summe_r"] = round(float(self.st["summe_r"]) - float(t.get("r") or 0), 4)
            self.st["trades"] = int(self.st["trades"]) - 1
            self.st["hoechst"] = max(float(self.st.get("hoechst") or self.kapital), self.stand())
            self.st.setdefault("storniert", []).append(
                {"dealId": t.get("dealId"), "quelle_deal": qd, "neu": did, "zeit": self.stamp, "r": t.get("r"),
                 "eur": t.get("eur")})
            self.ev("Kopie wieder geführt", quelle=t["quelle"], quelle_deal=qd, alt=t.get("dealId"), dealId=did,
                    zurueck_r=t.get("r"), zurueck_eur=t.get("eur"))

    # ---- Neue Kopien ----

    def offene_margin(self) -> float:
        return round(sum(float(k.get("margin_eur") or 0) for k in self.st["kopien"].values()), 2)

    def neue(self, deals: list[dict], quell_pos: dict, konten_ok: set[str], raus: dict[str, str],
             available: float | None, hedging: bool) -> None:
        for d in deals:
            qd, bot = d["dealId"], d["bot"]
            if qd in self.st["kopien"] or qd in self.st["gesehen"]:
                continue
            if qd in self.fremde:
                self.merke(qd, bot, "schon vom anderen Bündel dieses Kontos kopiert")
                continue
            p = quell_pos.get(qd)
            if p is None:
                if d["konto"] in konten_ok:
                    self.merke(qd, bot, "Quelle beim Broker schon zu")
                continue
            pos, mk = p.get("position") or {}, p.get("market") or {}
            epic = str(mk.get("epic") or pos.get("epic") or "")
            seite = 1 if str(pos.get("direction")).upper() == "BUY" else -1
            eroeffnet = _zeit(pos.get("createdDateUTC") or pos.get("createdDate"))
            stop, ziel = _num(pos.get("stopLevel")), _num(pos.get("profitLevel"))
            if eroeffnet is None or self.now - eroeffnet > self.frist:
                self.merke(qd, bot, f"älter als {int(self.frist.total_seconds() // 60)} Minuten")
                continue
            if not self.siegel:
                self.merke(qd, bot, "Siegel fehlt")
                continue
            if self.st.get("gebremst"):
                self.merke(qd, bot, "Bremse: 30 % unter dem Höchststand")
                continue
            if bot in raus:
                self.merke(qd, bot, "Mitglied raus: " + raus[bot])
                continue
            if not epic or epic in SPERR_MAERKTE:
                self.merke(qd, bot, f"Markt {epic or '?'} ist hier gesperrt")
                continue
            if stop is None:
                self.merke(qd, bot, "Quelle ohne Stop")
                continue
            if not hedging and any(k.get("epic") == epic for k in [*self.st["kopien"].values(), *self.fremde.values()]):
                self.merke(qd, bot, "ohne Hedging höchstens eine Kopie je Markt")
                continue
            try:
                q = self.quote(epic)
            except Exception as err:        # noqa: BLE001
                self.merke(qd, bot, f"Markt nicht lesbar ({type(err).__name__})")
                continue
            if not q.tradeable:
                self.merke(qd, bot, "Markt zu")
                continue
            kurs = q.offer if seite > 0 else q.bid
            dist = seite * (kurs - stop)
            if dist <= max(q.min_dist, 0.0):
                self.merke(qd, bot, "Kurs schon am oder hinter dem Stop der Quelle")
                continue
            size, warum = groesse(self.risiko, dist, q, self.faktor)
            if size is None:
                self.merke(qd, bot, warum)
                continue
            marg = round(margin_eur(size, kurs, q), 2)
            if self.offene_margin() + marg > self.margin_anteil * self.stand():
                self.merke(qd, bot, f"Margin {self.offene_margin() + marg:.0f} € über "
                                    f"{self.margin_anteil * 100:.0f} % von {self.stand():.0f} €")
                continue
            if available is not None and available - marg < self.frei_danach:
                self.merke(qd, bot, f"beim Broker blieben nur {available - marg:.0f} € frei")
                continue
            body = {"epic": epic, "direction": "BUY" if seite > 0 else "SELL", "size": size, "guaranteedStop": False,
                    "stopLevel": _rund(stop, q)}
            if ziel is not None:
                body["profitLevel"] = _rund(ziel, q)
            info = {"quelle": bot, "quelle_deal": qd, "epic": epic, "richtung": seite, "size": size,
                    "stop": body["stopLevel"], "ziel": body.get("profitLevel"), "margin_eur": marg,
                    "risiko_eur": round(size * dist * euro_je_punkt(q), 2)}
            if not self.send:
                self.ev("würde kopieren", kurs=kurs, **info)
                continue
            self.merke_versuch(qd)
            try:
                self.nur_mein_konto()
                ref = self.client._request("POST", "/positions", json=body).json()["dealReference"]
                conf = self.client.confirm(ref)
            except Exception as err:        # noqa: BLE001 - nie wiederholen
                self.merke(qd, bot, f"Order fehlgeschlagen ({str(err)[:120]})")
                continue
            if str((conf or {}).get("dealStatus") or "").upper() == "REJECTED":
                self.merke(qd, bot, f"Order abgelehnt ({(conf or {}).get('reason')})")
                continue
            deal = deal_aus_bestaetigung(conf)
            if not deal:
                self.merke(qd, bot, "Order ohne Deal-ID in der Bestätigung, nachsehen")
                continue
            entry = _num((conf or {}).get("level")) or kurs
            self.st["versuche"].pop(qd, None)
            self.st["kopien"][qd] = {**info, "dealId": deal, "entry": entry, "stop_start": body["stopLevel"],
                                     "stop_quelle": stop, "ziel_quelle": ziel, "quelle_konto": d["konto"],
                                     "lot": q.lot, "eur_rate": q.eur_rate, "opened_utc": self.stamp,
                                     "quelle_opened_utc": eroeffnet.strftime(FMT)}
            if available is not None:
                available -= marg
            self.ev("kopiert", dealId=deal, entry=entry, **info)

    def merke_versuch(self, qd: str) -> None:
        """Vor dem Senden: Bricht der Lauf mitten in der Order ab, sieht der nächste Lauf den Versuch und sendet nie
        ein zweites Mal."""
        self.st.setdefault("versuche", {})[qd] = self.stamp


def run(client, state: dict, now: datetime, send_orders: bool = True, jdir: Path = J,
        konten_daten: dict | None = None, regel: dict | None = None,
        gebucht: list[dict] | None = None, vorab: Path = VORAB) -> tuple[dict, list[dict], list[dict]]:
    """Ein Lauf des Bündels der Regeldatei `vorab`. Rückgabe: neuer Stand, Ereignisse, fertige Kopien. `gebucht` sind
    die fertigen Kopien aus trades.jsonl (ohne Angabe aus jdir/<bot_id>/trades.jsonl), für nachpruefen."""
    regel = regel or lade_regel(vorab)
    siegel = vorab_ok(vorab)
    lauf = Lauf(client, state, now, regel, send_orders, siegel=siegel)
    if _norm(regel.get("konto_name") or KONTO_NAME) != _norm(KONTO_NAME):
        lauf.ev("kein Konto", konto=str(regel.get("konto_name")))
        lauf.st["stand"] = lauf.stamp
        return lauf.st, lauf.log, []
    lauf.fremde = fremde_kopien(lauf.bot_id, jdir)
    lauf.neue_regel(Path(vorab).name)
    lauf.st.setdefault("versuche", {})
    for qd in list(lauf.st["versuche"]):          # Order ohne Antwort im letzten Lauf: nie ein zweites Mal senden
        lauf.merke(qd, "?", "Order im letzten Lauf ohne Antwort, nicht wiederholt")
        del lauf.st["versuche"][qd]
    if not KONTO or KONTO.endswith(HAUPT_ENDUNG):
        lauf.ev("kein Konto", konto=KONTO_NAME)
        lauf.st["stand"] = lauf.stamp
        return lauf.st, lauf.log, []
    konten = client.accounts()
    acc = next((a for a in konten if str(a.get("accountId")) == KONTO), None)
    if acc is None or _norm(acc.get("accountName") or KONTO_NAME) != _norm(KONTO_NAME):
        lauf.ev("kein Konto", konto=KONTO_NAME)
        lauf.st["stand"] = lauf.stamp
        return lauf.st, lauf.log, []
    euro = str(acc.get("currency") or "EUR").upper() == str(regel.get("waehrung") or "EUR").upper()
    available = _num((acc.get("balance") or {}).get("available"))
    deals, gelesen, fehler = quell_deals(regel, jdir, konten_daten)
    for f in fehler:
        lauf.ev("Mitglied nicht lesbar", fehler=f)
    mitglied_konten = {d["konto"] for d in deals}
    if KONTO in mitglied_konten:                  # ein Mitglied auf diesem Konto: Quelle und Kopie wären nicht zu trennen
        lauf.ev("Mitglied auf dem Bündel-Konto, nichts kopiert")
        deals = [d for d in deals if d["konto"] != KONTO]
    try:
        vergleich = json.loads((jdir / "vergleich.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        vergleich = None
    raus = mitglieder_raus(regel, vergleich)
    vorher = client.account_id
    quell_pos, konten_ok = {}, set()
    try:
        for konto in sorted({d["konto"] for d in deals}):
            try:
                client.switch_account(konto)
                for p in client.positions():
                    did = str((p.get("position") or {}).get("dealId") or "")
                    if did:
                        quell_pos[did] = p
                konten_ok.add(konto)
            except Exception as err:        # noqa: BLE001 - dann bleibt alles dieses Kontos, wie es ist
                lauf.ev("Quellkonto nicht lesbar", fehler=str(err)[:200])
        quell_pos = {d["dealId"]: quell_pos[d["dealId"]] for d in deals if d["dealId"] in quell_pos}
        client.switch_account(KONTO)
        eigene = {str((p.get("position") or {}).get("dealId")): p for p in client.positions()}
        if gebucht is None:
            gebucht = _lies_jsonl(jdir / lauf.bot_id / "trades.jsonl")
        lauf.nachpruefen(gebucht, eigene, deals)
        lauf.fuehren(deals, gelesen, quell_pos, konten_ok, eigene)
        neu = [d for d in deals if d["dealId"] not in lauf.st["kopien"] and d["dealId"] not in lauf.st["gesehen"]]
        if neu:
            if not euro:
                for d in neu:
                    lauf.merke(d["dealId"], d["bot"], "Konto nicht in Euro")
            else:
                lauf.neue(neu, quell_pos, konten_ok, raus, available, lauf.hedging_an())
        lauf.aufraeumen({d["dealId"] for d in deals})
        lauf.st["raus"] = raus
        lauf.st["stand"] = lauf.stamp
        return lauf.st, lauf.log, lauf.fertige
    finally:
        with contextlib.suppress(Exception):
            if vorher and vorher != client.account_id:
                client.switch_account(vorher)


# --------------------------------------------------------------------------------------------------------------------
# Journal und Cockpit

def bewertung(trades: list[dict]) -> dict:
    r = [float(t["r"]) for t in trades if t.get("r") is not None]
    gew, verl = sum(x for x in r if x > 0), -sum(x for x in r if x < 0)
    pf = round(gew / verl, 2) if verl else None
    return {"trades": len(r), "summe_r": round(sum(r), 2), "gewinnfaktor": pf, "pf_r": pf,     # pf_r wie die anderen Bots
            "summe_eur": round(sum(float(t.get("eur") or 0) for t in trades), 2),           # liest das Cockpit
            "urteil": "Urteil nach VORAB_aufstieg_alle.yaml (einzeln): 100 Demo-Trades, 61 Tage, Gewinnfaktor 1,3"}


def status(st: dict, kapital: float = 700.0) -> str:
    if st.get("gebremst"):
        return f"Bremse seit {str(st['gebremst']['zeit'])[:16]} UTC, kopiert nichts Neues mehr, nur Kirons Entscheidung"
    n = len(st.get("kopien") or {})
    stand = float(kapital) + float(st.get("summe_eur") or 0)
    teil = f"{n} Kopie offen" if n == 1 else f"{n} Kopien offen"
    return f"{teil}, gedachter Kontostand {stand:.2f} € nach {int(st.get('trades') or 0)} fertigen Kopien"


def cockpit(st: dict, alle: list[dict], regel: dict, vorab: Path = VORAB) -> dict:
    offen = [{k: v.get(k) for k in ("quelle", "epic", "richtung", "entry", "stop", "ziel", "size", "risiko_eur",
                                     "margin_eur", "opened_utc")} for v in (st.get("kopien") or {}).values()]
    text, test = regel.get("text") or REGEL, regel.get("backtest_text") or TEST
    vorab = Path(vorab)
    ab = st.get("regel_seit")
    return {"bot": bot_id(regel), "name": regel.get("name") or NAME, "konto": regel.get("konto_name") or KONTO_NAME,
            "stand": st.get("stand"), "start": st.get("start"),
            "status": status(st, regel["geld"]["kapital_eur"]), "regel": text, "backtest": test, "test": test,
            "vorab": f"suche/{vorab.name}", "vorab_ok": vorab_ok(vorab),
            "mitglieder": list((regel.get("mitglieder") or {}).keys()),
            "auslaufend": list((regel.get("auslaufend") or {}).keys()),
            "raus": st.get("raus") or {}, "kapital_eur": regel["geld"]["kapital_eur"],
            "kontostand_gedacht_eur": round(float(regel["geld"]["kapital_eur"]) + float(st.get("summe_eur") or 0), 2),
            "hedging": st.get("hedging"), "offen": offen, "zusammenfassung": bewertung(alle),
            "regel_seit": ab, "regeln_vorher": st.get("regeln") or [],
            "seit_regel": bewertung([t for t in alle if str(t.get("opened_utc") or "") >= str(ab)]) if ab else None,
            "letzte_trades": alle[-10:]}


def _ohne_zeit(st: dict) -> dict:
    return {k: v for k, v in (st or {}).items() if k != "stand"}


def _lies_jsonl(path: Path) -> list[dict]:
    out = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            with contextlib.suppress(ValueError):
                out.append(json.loads(line))
    return out


def stornieren(st: dict, jdir: Path) -> int:
    """Falsche Buchungen, die nachpruefen zurückgenommen hat, kommen aus trades.jsonl nach storniert.jsonl. Nichts geht
    verloren, jede Zeile steht danach in storniert.jsonl mit Zeit und neuer Deal-ID. Rückgabe: Zahl der Zeilen."""
    weg = {(s["dealId"], s["quelle_deal"]): s for s in st.get("storniert") or []}
    pfad = jdir / "trades.jsonl"
    if not weg or not pfad.exists():
        return 0
    bleiben, raus = [], []
    for line in pfad.read_text(encoding="utf-8").splitlines():
        try:
            t = json.loads(line)
        except ValueError:
            bleiben.append(line)
            continue
        s = weg.get((t.get("dealId"), t.get("quelle_deal")))
        if s is None:
            bleiben.append(line)
        else:
            raus.append({**t, "storniert": s["zeit"], "neue_dealId": s["neu"],
                         "warum": "Kopie lag noch offen, falsche Deal-ID bis 26.11.2026"})
    if raus:
        with open(jdir / "storniert.jsonl", "a", encoding="utf-8") as fh:
            fh.writelines(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in raus)
        pfad.write_text("".join(line + "\n" for line in bleiben), encoding="utf-8")
    return len(raus)


def schreiben(st: dict, log: list[dict], fertige: list[dict], regel: dict, jdir: Path | None = None,
              cockpit_pfad: Path | None = None, vorab: Path = VORAB) -> bool:
    """Schreibt Zustand, Log, Kopien und Cockpit. Hat sich außer der Uhrzeit nichts geändert, schreibt der Lauf nichts.
    Ohne Angabe: journal/<bot_id>/ und journal/<bot_id>.json. Nie die Dateien eines anderen Bots oder Bündels."""
    eigen = bot_id(regel)
    jdir = Path(jdir) if jdir is not None else J / eigen
    cockpit_pfad = Path(cockpit_pfad) if cockpit_pfad is not None else J / f"{eigen}.json"
    andere = {n for b in BUENDEL if b != eigen for n in (b, f"{b}.json")}
    for p in (jdir, cockpit_pfad):
        if p.name in FREMDE_DATEIEN or p.name in andere:
            raise RuntimeError(f"{p} gehört einem anderen Bot")
    pfad = jdir / "state.json"
    alt = json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else None
    if alt is not None and not log and not fertige and _ohne_zeit(alt) == _ohne_zeit(st) and cockpit_pfad.exists():
        return False
    jdir.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(st, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    stornieren(st, jdir)
    for name, rows in (("log.jsonl", log), ("trades.jsonl", fertige)):
        if rows:
            with open(jdir / name, "a", encoding="utf-8") as fh:
                fh.writelines(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows)
    alle = _lies_jsonl(jdir / "trades.jsonl")
    cockpit_pfad.write_text(json.dumps(cockpit(st, alle, regel, vorab), ensure_ascii=False, indent=1, default=str)
                            + "\n", encoding="utf-8")
    return True


def main(argv: list[str]) -> int:
    from gold.bot.capital import CapitalClient
    from gold.bot.runner import CRED_KEYS, clean_credentials

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="nur rechnen, keine Order")
    ap.add_argument("--regel", default=str(VORAB_OHNE_GOLD.relative_to(ROOT)),
                    help="Regeldatei des Bündels (Standard: buendel9 ohne Gold)")
    args = ap.parse_args(argv)
    vorab = ROOT / args.regel
    if vorab.resolve() not in {x.resolve() for x in (VORAB_OHNE_GOLD, VORAB_GOLD)}:
        raise SystemExit(f"{args.regel} ist keine Regeldatei eines laufenden Bündels")
    creds = clean_credentials({k: os.environ.get(k, "") for k in CRED_KEYS})
    if not all(creds):
        print("Keine Capital.com-Zugangsdaten, Bündel übersprungen")
        return 0
    regel = lade_regel(vorab)
    path = J / bot_id(regel) / "state.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    client = CapitalClient(*creds, environment="demo")
    client.login()
    try:
        st, log, fertige = run(client, state, datetime.now(timezone.utc), send_orders=not args.dry_run, regel=regel,
                               vorab=vorab)
    finally:
        with contextlib.suppress(Exception):
            client.logout()
    print(json.dumps({"ereignisse": log, "fertig": fertige, "status": status(st, regel["geld"]["kapital_eur"])},
                     ensure_ascii=False, default=str))
    if not args.dry_run:
        schreiben(st, log, fertige, regel, vorab=vorab)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
