"""Gold-Zonen Bruch: Bruch mit Rollenwechsel an Zonen des 4-Std.-Charts, live auf einem Capital.com-DEMOKONTO. Nie
echtes Geld.

    python -m gold.zonen_bot              # ein Lauf: Trade führen, Plan rechnen, Limit-Orders legen oder löschen
    python -m gold.zonen_bot --dry-run    # nur rechnen und zeigen, keine Order

Kirons Wahl vom 11.11.2026 10:20 UTC ("Ja, Bruch-Variante als Demo-Bot") auf der Karte "Gold-Bot mit Zonen trotz
durchgefallenem Test auf einem Demokonto starten?". Die Regel ist die Variante B_alle aus suche/VORAB_gold_zonen.yaml.
Sie ist im Test DURCHGEFALLEN (suche/ergebnis_gold_zonen.md): 2024 bis 2026 182 Trades, Gewinnfaktor 1,51, +68,0 R,
aber nur 78,2 % der Zufallsläufe geschlagen. Der Gewinn kam vor allem aus dem Goldanstieg. Der Bot ist ein
Vorwärtstest auf Kirons Wunsch. Regeln, Abweichungen vom Test und Urteil stehen in suche/VORAB_gold_zonen_bot.yaml,
Prüfsumme im Protokoll vor dem ersten Trade. Ohne passende Prüfsumme legt der Bot keine Order.

Regel kurz (Rechnung in suche/gold_zonen.py, dieselben Funktionen wie im Test):
- Zonen aus bestätigten Swing-Hochs und Swing-Tiefs fertiger 4-Std.-Kerzen. Schließt eine 4-Std.-Kerze jenseits der
  äußeren Linie, ist die Zone gebrochen. Limit-Order auf der äußeren Linie in Richtung des Bruchs, 30 fertige
  4-Std.-Kerzen gültig, früher weg bei einem 4-Std.-Schluss zurück jenseits der inneren Linie.
- Stop 0,25 ATR jenseits der inneren Linie. Nach 2 R Stop auf den Einstieg. Ziel die innere Linie der nächstgelegenen
  gültigen Zone der Gegenseite ab 4 R, sonst 10 R. Spätestens nach 14 Kalendertagen raus. Ein Trade gleichzeitig.

Live-Ausführung (alle 5 Minuten im Lauf pine5m.yml):
- Einmal je Stunde holt der Bot etwa 75 Tage Stundenkerzen und rechnet den Plan: welche Orders jetzt gelten und welche
  Zonen als Ziel taugen. Dazwischen prüft er an 5-Minuten-Kerzen und am Kurs, ob eine Linie berührt wurde.
- Es liegt höchstens eine Limit-Order beim Broker: die wartende Zone, deren Linie dem Kurs am nächsten ist, mit Stop
  und vorläufigem Ziel. Account 2 hat kein Hedging. Eine zweite Order der Gegenrichtung könnte sonst einen offenen
  Trade schließen. Solange ein Trade offen ist und von Freitag 16:45 bis Sonntag 18:05 Uhr New York liegt keine Order.
- Nur Account 2 (Endung 2606), den er mit dem Mess-Bot Vortag EUR/USD 1 ATR teilt (anderer Markt). Nie das Hauptkonto
  des Gold-Bots (Endung 3150). Er kennt seine Order und seine Position an der Deal-ID. Liegt eine fremde Gold-Position
  oder eine fremde Gold-Order auf dem Konto, legt er keine Order.
- Ab -25 R seit Start keine neue Order mehr (Sicherung), zurück nur mit Kirons Entscheidung.
- Er schreibt nur journal/gold-zonen/ und journal/gold-zonen.json, nie die Dateien des Gold-Bots.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from gold import short_bot as sb
from suche import gold_zonen as gz

ROOT = gz.ROOT
BOT_ID = "gold-zonen"
NAME = "Gold-Zonen Bruch (Rollenwechsel)"
EPIC = sb.EPIC
KONTO = "332263729491432606"          # Account 2, geteilt mit dem Mess-Bot r6-vortag-eurusd-1atr (EUR/USD)
KONTO_NAME = "Account 2"
HAUPT_ENDUNG = sb.HAUPT_ENDUNG        # Hauptkonto des Gold-Bots, hier nie handeln
RISIKO_EUR = 5.0
MAX_OZ = 1.0
MAX_RISIKO_FAKTOR = 2.0               # Runden auf die kleinste Größe darf das Risiko höchstens verdoppeln
PAUSE_R = -25.0
ZWISCHEN_NACH, ZWISCHEN_PF = 15, 0.6
URTEIL_NACH, URTEIL_PF = 40, 1.2
TAGE_KERZEN = 75                      # so viele Kalendertage Stundenkerzen je Plan
MIN_4H = 250                          # darunter ist die ATR noch nicht eingeschwungen: kein Plan
PLAN_ZU_ALT = pd.Timedelta(hours=4)   # älterer Plan: Orders löschen
MAX_VERSUCHE = 3                      # so oft darf das Legen einer Order scheitern, dann ist die Zone verbraucht
MERKEN_TAGE = 90                      # so lange bleibt eine verbrauchte Zone im Zustand
SCHLUSS_WARTEN = pd.Timedelta(hours=1)  # so lange sucht der Bot den Schlusskurs beim Broker, dann zählt der Stop-Kurs
NY = gz.NY
FMT = "%Y-%m-%dT%H:%M:%S"
STUNDE, FUENF = pd.Timedelta(hours=1), pd.Timedelta(minutes=5)
VORAB = ROOT / "suche" / "VORAB_gold_zonen_bot.yaml"
KEY = "VORAB_gold_zonen_bot sha256 "
JDIR = ROOT / "journal" / "gold-zonen"
COCKPIT = ROOT / "journal" / "gold-zonen.json"
GOLD_BOT_DATEIEN = sb.GOLD_BOT_DATEIEN
SEITE = {1: "Kauf", -1: "Verkauf"}
REGEL = ("Bruch mit Rollenwechsel: Schließt eine 4-Std.-Kerze jenseits einer Zone, liegt eine Limit-Order auf der "
         "alten Linie in Richtung des Bruchs (30 Kerzen gültig). Stop 0,25 ATR hinter der Zone, nach 2 R Einstand, Ziel "
         "die nächste Zone der Gegenseite ab 4 R, sonst 10 R, höchstens 14 Tage. Ein Trade und eine Order gleichzeitig, "
         "5 € Risiko.")
TEST = ("Test DURCHGEFALLEN (suche/ergebnis_gold_zonen.md): 2024 bis 2026 182 Trades (1,23 je Woche), GF 1,51, +68,0 R, "
        "Zufall nur 78,2 % (nötig 95 %). Trefferquote etwa 15 %, größter Rückgang 33,2 R, Shorts im Minus (GF 0,81). "
        "2015 bis 2023 GF 0,90. Läuft auf Kirons Wunsch als Vorwärtstest.")

_num = sb._num
_jetzt = sb._jetzt


def vorab_ok() -> bool:
    """Ist suche/VORAB_gold_zonen_bot.yaml mit seiner Prüfsumme im Protokoll festgelegt?"""
    from suche.runde1 import journal_lines, last_value, sha256_text
    if not VORAB.exists():
        return False
    return last_value(journal_lines(), KEY) == sha256_text(VORAB.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------------------------------------
# Zeit, Kerzen, Plan (ohne Netz, außer stundenkerzen)

def _ny(t: pd.Timestamp) -> pd.Timestamp:
    return t.tz_localize("UTC").tz_convert(NY).tz_localize(None)


def wochenende(now: pd.Timestamp) -> bool:
    """Freitag 16:45 Uhr bis Sonntag 18:05 Uhr New York: In dieser Zeit liegt keine Order beim Broker."""
    ny = _ny(now)
    minute = ny.hour * 60 + ny.minute
    return (ny.weekday() == 4 and minute >= 16 * 60 + 45) or ny.weekday() == 5 or (
        ny.weekday() == 6 and minute < 18 * 60 + 5)


def order_ende(now: pd.Timestamp) -> pd.Timestamp:
    """Bis dahin gilt eine neue Order beim Broker: der nächste Freitag 16:45 Uhr New York, als UTC."""
    ny = _ny(now)
    ende = ny.normalize() + pd.Timedelta(days=(4 - ny.weekday()) % 7, hours=16, minutes=45)
    if ende <= ny:
        ende += pd.Timedelta(days=7)
    return ende.tz_localize(NY).tz_convert("UTC").tz_localize(None)


def handelstag(t: pd.Timestamp) -> int:
    """Handelstag (endet 17:00 Uhr New York) als Zahl, wie in suche/gold_zonen.py. Für die Nächte eines Trades."""
    return int(((_ny(pd.Timestamp(t)) + pd.Timedelta(hours=7)).normalize() - pd.Timestamp("1970-01-01")).days)


def kerzen_ask(prices: list[dict]) -> pd.DataFrame:
    """Capital.com-Kerzen als Bid-OHLC (open, high, low, close) und dazu ask_low, das Tief am Ask. Eine Kauf-Linie gilt
    als berührt, wenn der Ask sie erreicht, eine Verkaufs-Linie, wenn der Bid sie erreicht."""
    from suche.demo_bots import utc_naive
    rows = []
    for p in prices or []:
        o, h, lo, c = (p.get(k) or {} for k in ("openPrice", "highPrice", "lowPrice", "closePrice"))
        if None in (o.get("bid"), h.get("bid"), lo.get("bid"), c.get("bid")):
            continue
        ask_low = lo.get("ask")
        if ask_low is None:                               # ohne Ask: Bid-Tief plus Spread zur Eröffnung
            ask_low = lo["bid"] + max((o.get("ask") or o["bid"]) - o["bid"], 0.0)
        rows.append({"time": utc_naive(p["snapshotTimeUTC"]), "open": o["bid"], "high": h["bid"], "low": lo["bid"],
                     "close": c["bid"], "ask_low": max(ask_low, lo["bid"])})
    spalten = ["open", "high", "low", "close", "ask_low"]
    if not rows:
        return pd.DataFrame(columns=spalten, dtype=float, index=pd.DatetimeIndex([], name="time"))
    df = pd.DataFrame(rows).set_index("time").sort_index()
    return df[~df.index.duplicated(keep="last")][spalten].astype(float)


def stundenkerzen(client, now: pd.Timestamp) -> pd.DataFrame:
    """Fertige Stundenkerzen der letzten TAGE_KERZEN Kalendertage, in Abrufen zu je 40 Tagen (nur lesen)."""
    teile, bis = [], pd.Timestamp(now)
    beginn = bis - pd.Timedelta(days=TAGE_KERZEN)
    while bis > beginn:
        von = max(beginn, bis - pd.Timedelta(days=40))
        teile.extend(client._get(f"/prices/{EPIC}", resolution="HOUR", max=1000,
                                 **{"from": von.strftime(FMT), "to": bis.strftime(FMT)}).get("prices", []))
        bis = von
    df = kerzen_ask(teile)
    return df[df.index + STUNDE <= now]


def plan_rechnen(stunden: pd.DataFrame, now: pd.Timestamp) -> dict | None:
    """Der Plan zum Zeitpunkt now aus fertigen Stundenkerzen: wartende Orders (suche.gold_zonen.wartende_bruch) und die
    Linien für das Ziel. None, wenn zu wenig fertige 4-Std.-Kerzen da sind."""
    if not len(stunden):
        return None
    m = gz.markt(stunden[["open", "high", "low", "close"]])
    n4 = gz.fertige_4h(m, now)
    if n4 < MIN_4H:
        return None
    sp = (stunden["ask_low"] - stunden["low"]).clip(lower=0).to_numpy()
    wartend, linien = gz.wartende_bruch(m, n4, sp)
    return {"stunde": str(pd.Timestamp(now).floor("h")), "gerechnet_bis": str(stunden.index[-1] + STUNDE),
            "kerzen_4h": int(n4), "letzte_4h": str(pd.Timestamp(m.t[m.k_bis[n4 - 1]]) + STUNDE),
            "atr_4h": round(float(m.atr4[n4 - 1]), 2), "kandidaten": wartend,
            "linien": {"1": [round(x, 3) for x in linien[1]], "-1": [round(x, 3) for x in linien[-1]]}}


def groesse(dist: float, q) -> tuple[float | None, str]:
    """Größe für RISIKO_EUR bis zum Stop: höchstens MAX_OZ Unzen, auf die Schrittweite des Brokers abgerundet, mindestens
    die kleinste Größe. None, wenn das Runden das Risiko mehr als verdoppeln würde."""
    if not q.eur_rate or not dist > 0:
        return None, "kein Kurs EUR/USD oder kein Stopabstand"
    lot = q.lot or 1.0
    roh = min(RISIKO_EUR * q.eur_rate / (dist * lot), MAX_OZ / lot)
    step = q.size_step or q.min_size
    size = round(max(math.floor(round(roh / step, 9)) * step, q.min_size), 8)
    risiko = size * lot * dist / q.eur_rate
    if risiko > MAX_RISIKO_FAKTOR * RISIKO_EUR:
        return None, f"kleinste Größe zu grob ({risiko:.2f} € Risiko statt {RISIKO_EUR:.0f} €)"
    return size, ""


def bewertung(trades: list[dict]) -> dict:
    r = [float(t["r"]) for t in trades]
    n = len(r)
    pf = gz.pf(pd.Series(r, dtype=float).to_numpy()) if n else None
    if n >= URTEIL_NACH:
        erste = pd.Series(r[:URTEIL_NACH], dtype=float).to_numpy()
        ok = (gz.pf(erste) or 0) >= URTEIL_PF and float(erste.sum()) > 0
        text = ("bestanden nach 40 Trades, Kiron entscheidet über den nächsten Schritt" if ok else
                "durchgefallen nach 40 Trades, Vorschlag an Kiron: stoppen oder neue Regeln mit neuem Vorab")
    elif n >= ZWISCHEN_NACH and (pf or 0) < ZWISCHEN_PF:
        text = f"Zwischencheck nach {n} Trades: Gewinnfaktor unter {ZWISCHEN_PF}, Vorschlag an Kiron: stoppen"
    else:
        text = f"läuft ({n} von {URTEIL_NACH} Trades)"
    return {"trades": n, "pf_r": pf, "summe_r": round(float(sum(r)), 2),
            "trefferquote": round(sum(x > 0 for x in r) / n, 3) if n else None,
            "summe_eur": round(float(sum(float(t.get("pnl_eur") or 0) for t in trades)), 2), "urteil": text}


# --------------------------------------------------------------------------------------------------------------------
# Ein Lauf

class Lauf:
    """Ein Lauf auf dem Demokonto. Alle Order-, Änderungs- und Schließ-Aufrufe gehen über diese Klasse, damit ein
    Trockenlauf (send_orders=False) nichts beim Broker ändert."""

    def __init__(self, client, state: dict, now: datetime, send_orders: bool = True):
        self.client = client
        self.st = copy.deepcopy(state or {})
        self.now = _jetzt(now)
        self.stamp = self.now.isoformat(timespec="seconds")
        self.vorher = self.st.get("stand")              # Zeit des letzten Laufs
        self.send = send_orders
        self.log: list[dict] = []
        self.fertige: list[dict] = []
        self.q = None
        self.andere_gold: list[str] = []
        self.fremde_orders: list[str] = []              # Gold-Orders auf dem Konto, die nicht von diesem Bot sind
        self.eigene_zu: set[str] = set()                # in diesem Lauf geschlossene eigene Positionen
        self.st.setdefault("format", 1)
        self.st.setdefault("start", self.stamp)
        self.st.setdefault("summe_r", 0.0)
        self.st.setdefault("trades", 0)
        self.st.setdefault("plan", None)
        self.st.setdefault("orders", [])
        self.st.setdefault("trade", None)
        self.st.setdefault("verbraucht", {})
        self.st.setdefault("versuche", {})
        self.st.setdefault("keine_order", [])

    def ev(self, event: str, **kw) -> None:
        self.log.append({"time": self.stamp, "event": event, **kw})

    def kurs_raus(self, d: int) -> float:
        """Zu diesem Kurs schließt eine Position zum Markt: Kauf am Bid, Verkauf am Ask."""
        return self.q.bid if d > 0 else self.q.offer

    def nur_mein_konto(self) -> None:
        if str(self.client.account_id) != KONTO:
            raise RuntimeError(f"aktives Konto ist nicht {KONTO_NAME}, nichts gesendet")

    def verbrauche(self, name: str, grund: str) -> None:
        if name not in self.st["verbraucht"]:
            self.st["verbraucht"][name] = {"zeit": self.stamp, "grund": grund}
            self.ev("Zone verbraucht", zone=name, grund=grund)

    def kerzen5(self) -> pd.DataFrame:
        """5-Minuten-Kerzen seit dem Plan bzw. seit dem letzten Blick auf den offenen Trade (mindestens 40, höchstens
        1000). Sind sie nicht lesbar, legt der Lauf keine neue Order."""
        seit = [self.now - 40 * FUENF]
        plan, tr = self.st.get("plan"), self.st.get("trade")
        if plan:
            seit.append(pd.Timestamp(plan["gerechnet_bis"]))
        if tr:
            seit.append(pd.Timestamp(tr.get("gesehen_bis") or tr["fuellkerze"]))
        n = int(min(1000, max(40, (self.now - min(seit)) / FUENF + 5)))
        try:
            return kerzen_ask(self.client.prices(EPIC, "MINUTE_5", n))
        except Exception as err:            # noqa: BLE001
            self.ev("5-Minuten-Kerzen nicht lesbar", fehler=str(err)[:200])
            return kerzen_ask([])

    # ---- Broker ----

    def aendere(self, tr: dict, stop: float, ziel: float | None, warum: str) -> bool:
        body = {"stopLevel": round(stop, 2)}
        if ziel is not None:
            body["profitLevel"] = round(ziel, 2)
        if not self.send:
            self.ev("würde ändern", dealId=tr["dealId"], **body, warum=warum)
            return True
        try:
            self.nur_mein_konto()
            ref = self.client._request("PUT", f"/positions/{tr['dealId']}", json=body).json().get("dealReference")
            conf = self.client.confirm(ref) if ref else {}
        except Exception as err:            # noqa: BLE001 - der nächste Lauf versucht es wieder, Stop liegt beim Broker
            self.ev("ändern fehlgeschlagen", dealId=tr["dealId"], warum=warum, fehler=str(err)[:200])
            return False
        if conf and str(conf.get("dealStatus") or "").upper() == "REJECTED":
            self.ev("ändern abgelehnt", dealId=tr["dealId"], warum=warum, grund=conf.get("reason"))
            return False
        tr["stop"] = body["stopLevel"]
        tr["ziel_broker"] = body.get("profitLevel")
        self.ev("geändert", dealId=tr["dealId"], **body, warum=warum)
        return True

    def schliesse(self, tr: dict, warum: str) -> bool:
        if not self.send:
            self.ev("würde schließen", dealId=tr["dealId"], warum=warum, kurs=self.kurs_raus(tr["richtung"]))
            return False
        try:
            self.nur_mein_konto()
            conf = self.client.close_position(tr["dealId"])
        except Exception as err:            # noqa: BLE001 - nächster Lauf versucht es wieder, Stop liegt beim Broker
            self.ev("schließen fehlgeschlagen", dealId=tr["dealId"], warum=warum, fehler=str(err)[:200])
            return False
        if str((conf or {}).get("dealStatus") or "").upper() == "REJECTED":
            self.ev("schließen abgelehnt", dealId=tr["dealId"], warum=warum, grund=(conf or {}).get("reason"))
            return False
        level = _num((conf or {}).get("level")) or self.kurs_raus(tr["richtung"])
        self.abschluss(tr, float(level), warum, self.now)
        return True

    def loesche(self, o: dict, warum: str) -> None:
        if not self.send:
            self.ev("würde Order löschen", zone=o["name"], warum=warum)
            return
        from suche.r6_bots import loesche_order
        if not o.get("dealId"):                 # Bestätigung fehlte: erst der nächste Lauf weiß, ob sie beim Broker liegt
            return
        try:
            self.nur_mein_konto()
            conf = loesche_order(self.client, o["dealId"])
        except Exception as err:            # noqa: BLE001 - vielleicht gerade gefüllt: der nächste Lauf sieht nach
            o["loeschen"] = True
            self.ev("Order löschen fehlgeschlagen", zone=o["name"], warum=warum, fehler=str(err)[:200])
            return
        if str((conf or {}).get("dealStatus") or "").upper() == "REJECTED":
            o["loeschen"] = True
            self.ev("Order löschen abgelehnt", zone=o["name"], warum=warum, grund=(conf or {}).get("reason"))
            return
        self.st["orders"] = [x for x in self.st["orders"] if x is not o]
        self.ev("Order gelöscht", zone=o["name"], seite=SEITE[o["d"]], linie=o["linie"], warum=warum)

    # ---- Abgleich mit dem Konto ----

    def abschluss(self, tr: dict, level: float, grund: str, wann: pd.Timestamp, **mehr) -> None:
        """Bucht den Trade. R nach Übernachtgebühr mit den Sätzen des Tests, das Euro-Ergebnis ohne Gebühr."""
        d, r_usd = tr["richtung"], float(tr["r_usd"])
        satz = gz.regel()["kosten"]["uebernacht_pct_jahr"]["long" if d > 0 else "short"]
        naechte = max(handelstag(pd.Timestamp(wann)) - handelstag(pd.Timestamp(tr["opened_utc"])), 0)
        gebuehr_r = float(satz) / 100.0 / 365.0 * naechte * tr["entry"] / r_usd
        r_roh = d * (level - tr["entry"]) / r_usd
        pnl_usd = tr["size"] * (self.q.lot or 1.0) * d * (level - tr["entry"])
        rate = self.q.eur_rate
        rec = {**{k: tr.get(k) for k in ("id", "zone", "richtung", "linie", "innen", "dealId", "size", "entry",
                                         "stop_plan", "ziel", "r_usd", "opened_utc", "bestes", "einstand")},
               "seite": SEITE[d], "exit": round(level, 2), "grund": grund,
               "closed_utc": pd.Timestamp(wann).isoformat(timespec="seconds"), "naechte": naechte,
               "r_roh": round(r_roh, 3), "gebuehr_r": round(gebuehr_r, 3), "r": round(r_roh - gebuehr_r, 3),
               "pnl_usd": round(pnl_usd, 2), "pnl_eur": round(pnl_usd / rate, 2) if rate else None, **mehr}
        self.fertige.append(rec)
        self.eigene_zu.add(str(tr.get("dealId")))
        if tr.get("dealId"):                                # ihr Schluss darf nie für eine spätere Order zählen
            self.st["letzte_deals"] = ([str(tr["dealId"])] + list(self.st.get("letzte_deals") or []))[:5]
        self.st["summe_r"] = round(float(self.st["summe_r"]) + rec["r"], 3)
        self.st["trades"] = int(self.st["trades"]) + 1
        if self.st.get("trade") is tr:
            self.st["trade"] = None
        self.ev("Trade fertig", trade=tr["id"], seite=rec["seite"], grund=grund, r=rec["r"], pnl_eur=rec["pnl_eur"])
        if self.st.get("pausiert") is None and self.st["summe_r"] <= PAUSE_R:
            self.st["pausiert"] = {"seit": self.stamp, "grund": f"Summe R seit Start {self.st['summe_r']} (Grenze "
                                                                f"{PAUSE_R}), zurück nur mit Kirons Entscheidung"}
            self.ev("Pause", grund=self.st["pausiert"]["grund"])

    def zuordnen(self, wo: list[dict]) -> None:
        """Gold-Orders des Kontos den eigenen Orders zuordnen. Fehlte beim Legen die Bestätigung des Brokers (Order ohne
        Deal-ID), wird sie hier an Richtung und Kurs wiedergefunden. Jede andere Gold-Order ist fremd: Dann legt der Bot
        keine Order. Er löscht eine fremde Order nie."""
        bekannt = {o["dealId"] for o in self.st["orders"] if o.get("dealId")}
        fremd = [w for w in wo if str(w.get("dealId")) not in bekannt]
        for o in self.st["orders"]:
            if o.get("dealId"):
                continue
            richtung = "BUY" if o["d"] > 0 else "SELL"
            passend = [w for w in fremd if str(w.get("direction")).upper() == richtung
                       and abs((_num(w.get("orderLevel")) or 0.0) - o["linie"]) < 0.011]
            if passend:
                o["dealId"] = str(passend[0].get("dealId"))
                fremd = [w for w in fremd if w is not passend[0]]
                self.ev("Order wiedergefunden (Bestätigung fehlte)", zone=o["name"], dealId=o["dealId"])
        self.fremde_orders = sorted(str(w.get("dealId")) for w in fremd)

    def abgleich(self, gold: list[dict], wo_ids: set[str]) -> None:
        """1. Ist der offene Trade beim Broker zu (Stop oder Ziel)? 2. Ist eine Order nicht mehr da: gefüllt (neuer
        Trade), gefüllt und schon wieder zu (aus der Kontoaktivität) oder abgelaufen?"""
        pos = {str(p["position"].get("dealId")): p["position"] for p in gold}
        tr = self.st.get("trade")
        if tr:
            if tr["dealId"] in pos:                        # Stop und Ziel so, wie sie beim Broker stehen
                p = pos[tr["dealId"]]
                tr["stop"] = _num(p.get("stopLevel")) or tr.get("stop")
                tr["ziel_broker"] = _num(p.get("profitLevel"))
                tr.pop("weg_seit", None)
            else:
                level, quelle = self.schluss_beim_broker(tr)
                geschaetzt = level is None
                seit = tr.setdefault("weg_seit", self.stamp)
                if geschaetzt and self.now - pd.Timestamp(seit) < SCHLUSS_WARTEN:
                    if seit == self.stamp:                  # ein Ziel darf nie als Stop gebucht werden: erst nachsehen
                        self.ev("Position beim Broker zu, Schlusskurs noch nicht lesbar", trade=tr["id"])
                else:
                    if geschaetzt:
                        level, quelle = tr.get("stop") or tr["stop_plan"], "SL"
                    if quelle == "TP":
                        grund = "ziel"
                    elif quelle == "SL":
                        grund = "einstand" if tr.get("einstand") else "stop"
                    else:
                        grund = f"beim Broker ({quelle or 'unbekannt'})"
                    self.abschluss(tr, float(level), grund, self.now, **({"exit_geschaetzt": True} if geschaetzt else {}))
        rest = []
        for o in self.st["orders"]:
            if o["dealId"] in wo_ids:
                rest.append(o)
                continue
            d = o["d"]
            if self.st.get("trade") is None:
                neu = [p for i, p in pos.items() if i not in self.eigene_zu and self.passt(o, p)]
                if neu:
                    p = min(neu, key=lambda x: abs((_num(x.get("level")) or o["linie"]) - o["linie"]))
                    self.uebernehmen(o, p)
                    continue
                zu = self.gefuellt_und_zu(o)
                if zu is None:                              # Kontoaktivität nicht lesbar: nächster Lauf sieht nach
                    rest.append(o)
                    continue
                if zu:
                    continue
            self.ev("Order nicht mehr beim Broker (abgelaufen oder gelöscht)", zone=o["name"], seite=SEITE[d])
        self.st["orders"] = rest

    def schluss_beim_broker(self, tr: dict) -> tuple[float | None, str]:
        """Schlusskurs und Quelle (SL, TP, ...) aus der Kontoaktivität zu dieser Position. Der Broker gibt je Abruf
        höchstens einen Tag her, darum die letzten 23 Std. 59 Min., auch wenn der Trade älter ist. Es zählt nur ein
        eindeutiger Schluss (Stop, Ziel, Zwangsschluss oder POSITION_CLOSED), nie eine Änderung von Stop oder Ziel.
        (None, ""), wenn dort kein Schluss steht oder die Aktivität nicht lesbar ist."""
        von = max(pd.Timestamp(tr["opened_utc"]) - pd.Timedelta(minutes=10),
                  self.now - pd.Timedelta(hours=23, minutes=59))
        try:
            acts = self.client.activity(tr["dealId"], von.to_pydatetime(), self.now.to_pydatetime())
        except Exception as err:            # noqa: BLE001
            print(f"Kontoaktivität nicht lesbar: {err}")
            return None, ""
        rows = [{"dateUTC": str(a.get("dateUTC") or ""), "source": a.get("source"),
                 "level": _num((a.get("details") or {}).get("level")),
                 "actions": [x.get("actionType") for x in (a.get("details") or {}).get("actions", [])]}
                for a in acts or [] if a.get("type", "POSITION") == "POSITION" and a.get("status", "ACCEPTED") == "ACCEPTED"]
        zu = sorted((r for r in rows if r["level"] is not None
                     and (r["source"] in ("SL", "TP", "CLOSE_OUT") or "POSITION_CLOSED" in r["actions"])),
                    key=lambda r: r["dateUTC"])
        return (zu[-1]["level"], str(zu[-1]["source"] or "")) if zu else (None, "")

    @staticmethod
    def passt(o: dict, p: dict) -> bool:
        """Ist die Position die Füllung dieser Order? Gleiche Richtung, gleiche Größe und ein Kurs an der Linie oder
        besser (eine Limit-Order füllt nie schlechter). Alles andere ist eine fremde Position."""
        d = o["d"]
        if (1 if str(p.get("direction")).upper() == "BUY" else -1) != d:
            return False
        size, level = _num(p.get("size")), _num(p.get("level"))
        if size is not None and abs(size - o["size"]) > 1e-9:
            return False
        return level is None or d * (level - o["linie"]) <= 0.1 * abs(o["linie"] - o["stop"])

    def uebernehmen(self, o: dict, p: dict) -> None:
        """Die Limit-Order hat gefüllt: Aus der Position wird der offene Trade."""
        from suche.demo_bots import utc_naive
        d = o["d"]
        entry = _num(p.get("level")) or o["linie"]
        opened = self.now                                   # Zeit der Füllung: nur, wenn sie seit dem letzten Lauf liegt
        with contextlib.suppress(Exception):
            t = utc_naive(p.get("createdDateUTC"))
            ab = (pd.Timestamp(self.vorher) if self.vorher else pd.Timestamp(o["gelegt_utc"])) - pd.Timedelta(minutes=1)
            if ab <= t <= self.now:
                opened = t
        luecke = d * (entry - o["innen"]) < 0               # Füllung jenseits der inneren Linie: sofort schließen
        r_usd = abs(o["linie"] - o["stop"]) if luecke else abs(entry - o["stop"])
        tr = {"id": f"{opened:%Y-%m-%dT%H:%M}", "zone": o["name"], "richtung": d, "linie": o["linie"],
              "innen": o["innen"], "dealId": str(p.get("dealId")), "size": _num(p.get("size")) or o["size"],
              "entry": round(float(entry), 2), "stop_plan": o["stop"], "stop": _num(p.get("stopLevel")) or o["stop"],
              "ziel": None, "ziel_broker": _num(p.get("profitLevel")), "r_usd": round(float(r_usd), 2),
              "opened_utc": opened.isoformat(timespec="seconds"), "fuellkerze": str(opened.floor("5min")),
              "bestes": None, "einstand": None, "luecke": bool(luecke)}
        self.st["trade"] = tr
        self.verbrauche(o["name"], "gehandelt")
        self.ev(SEITE[d] + " gefüllt", trade=tr["id"], zone=o["name"], entry=tr["entry"], linie=o["linie"],
                stop=tr["stop"], size=tr["size"], dealId=tr["dealId"])

    def gefuellt_und_zu(self, o: dict) -> bool | None:
        """Order weg und keine Position: Hat sie gefüllt, und Stop oder Ziel haben schon zwischen zwei Läufen getroffen?
        Aus der Kontoaktivität seit dem Legen bzw. seit dem letzten Lauf (höchstens ein Tag). Dann wird der Trade
        gebucht (True). False: dort steht kein Schluss. None: Die Aktivität ist nicht lesbar."""
        von = max(pd.Timestamp(o["gelegt_utc"]), self.now - pd.Timedelta(hours=23, minutes=59),
                  (pd.Timestamp(self.vorher) - pd.Timedelta(minutes=10)) if self.vorher else pd.Timestamp(o["gelegt_utc"]))
        try:
            acts = self.client._get("/history/activity", **{"from": von.strftime(FMT), "to": self.now.strftime(FMT),
                                                            "detailed": "true"}).get("activities", [])
        except Exception as err:            # noqa: BLE001
            self.ev("Kontoaktivität nicht lesbar", zone=o["name"], fehler=str(err)[:200])
            return None
        alte = set(self.st.get("letzte_deals") or [])       # schon gebuchte Trades: ihr Schluss zählt hier nie
        rows = [{"dateUTC": a.get("dateUTC"), "source": a.get("source"), "level": _num((a.get("details") or {}).get("level")),
                 "actions": [x.get("actionType") for x in (a.get("details") or {}).get("actions", [])]}
                for a in acts if a.get("epic") == EPIC and a.get("type", "POSITION") == "POSITION"
                and a.get("status", "ACCEPTED") == "ACCEPTED" and str(a.get("dealId")) not in alte]
        rows = sorted((r for r in rows if r["level"] is not None), key=lambda r: str(r["dateUTC"] or ""))
        zu = [r for r in rows if r["source"] in ("SL", "TP", "CLOSE_OUT") or "POSITION_CLOSED" in r["actions"]]
        if not zu:
            return False
        auf = [r for r in rows if "POSITION_OPENED" in r["actions"]]
        d = o["d"]
        entry = auf[0]["level"] if auf else o["linie"]
        opened = pd.Timestamp(auf[0]["dateUTC"]) if auf and auf[0]["dateUTC"] else pd.Timestamp(o["gelegt_utc"])
        closed = pd.Timestamp(zu[-1]["dateUTC"]) if zu[-1]["dateUTC"] else self.now
        luecke = d * (entry - o["innen"]) < 0
        r_usd = abs(o["linie"] - o["stop"]) if luecke else abs(entry - o["stop"])
        tr = {"id": f"{opened:%Y-%m-%dT%H:%M}", "zone": o["name"], "richtung": d, "linie": o["linie"],
              "innen": o["innen"], "dealId": None, "size": o["size"], "entry": round(float(entry), 2),
              "stop_plan": o["stop"], "ziel": o.get("ziel"), "r_usd": round(float(r_usd), 2),
              "opened_utc": opened.isoformat(timespec="seconds"), "bestes": None, "einstand": None}
        self.verbrauche(o["name"], "gehandelt")
        grund = "ziel" if zu[-1]["source"] == "TP" else "stop" if zu[-1]["source"] == "SL" else "beim Broker"
        self.abschluss(tr, float(zu[-1]["level"]), grund, closed, einstieg_geschaetzt=not auf, zwischen_zwei_laeufen=True)
        return True

    # ---- Führung des offenen Trades ----

    def fuehren(self, m5: pd.DataFrame) -> None:
        """Kurslücke: sofort schließen. Ziel aus dem Füllkurs setzen. Nach 2 R Stop auf den Einstieg. Nach 14 Tagen raus."""
        tr, q = self.st.get("trade"), self.q
        if not tr or tr.get("weg_seit"):                    # Position beim Broker zu: abgleich bucht sie
            return
        d = tr["richtung"]
        if tr.get("luecke"):
            if q.tradeable:
                self.schliesse(tr, "kurslücke")
            return
        if tr.get("ziel") is None:                          # mit den Linien des Plans, wie er bei der Füllung galt
            linien = ((self.st.get("plan") or {}).get("linien") or {}).get(str(-d)) or []
            tr["ziel"] = round(gz.ziel_kurs(linien, d, tr["entry"], tr["r_usd"]), 2)
            tr["ziel_r"] = round(d * (tr["ziel"] - tr["entry"]) / tr["r_usd"], 2)
        fk = pd.Timestamp(tr["fuellkerze"])
        nach = m5[m5.index > fk]
        werte = []
        if len(nach):
            werte.append(float(nach["high"].max()) if d > 0 else float(nach["ask_low"].min()))
        if self.now.floor("5min") > fk and q.bid > 0 and q.offer > 0:
            werte.append(q.bid if d > 0 else q.offer)
        if tr.get("bestes") is not None:
            werte.append(float(tr["bestes"]))
        if werte:
            tr["bestes"] = round(max(werte) if d > 0 else min(werte), 2)
        tr["gesehen_bis"] = self.stamp
        if not q.tradeable:
            return
        if tr.get("ziel_broker") is None or abs(tr["ziel_broker"] - tr["ziel"]) > 0.011:
            if d * (self.kurs_raus(d) - tr["ziel"]) >= 0:   # Kurs schon am Ziel oder dahinter
                if self.schliesse(tr, "ziel"):
                    return
            else:
                self.aendere(tr, tr["stop"], tr["ziel"], "ziel aus dem Füllkurs")
        if (not tr.get("einstand") and tr.get("bestes") is not None
                and d * (tr["bestes"] - tr["entry"]) >= gz.EINSTAND_R * tr["r_usd"]):
            zu_nah = d * (self.kurs_raus(d) - tr["entry"]) <= (q.min_dist or 0)
            if not zu_nah and self.aendere(tr, tr["entry"], tr["ziel"], "einstand nach 2 R"):
                tr["einstand"] = self.stamp
            else:
                tr["einstand"] = self.stamp                 # steht im gebuchten Trade
                if self.schliesse(tr, "einstand"):
                    return
                tr["einstand"] = None                       # nicht geklappt: der nächste Lauf versucht es wieder
        if self.now >= pd.Timestamp(tr["opened_utc"]) + pd.Timedelta(days=gz.HALTE_TAGE):
            self.schliesse(tr, "zeit")

    # ---- Plan und Berührungen ----

    def planen(self, m5: pd.DataFrame) -> None:
        """Einmal je Stunde: Stundenkerzen holen und den Plan neu rechnen."""
        stunde = self.now.floor("h")
        plan = self.st.get("plan")
        if plan and plan.get("stunde") == str(stunde):
            return
        if wochenende(self.now) and plan:                   # der Markt ist zu: erst Sonntag 18:05 Uhr New York wieder
            return
        try:
            stunden = stundenkerzen(self.client, self.now)
        except Exception as err:            # noqa: BLE001 - der alte Plan bleibt, der nächste Lauf versucht es wieder
            self.ev("Stundenkerzen nicht lesbar", fehler=str(err)[:200])
            return
        letzte = stunde - STUNDE
        if (len(stunden) and len(m5) and ((m5.index >= letzte) & (m5.index < stunde)).any()
                and stunden.index[-1] < letzte):
            self.ev("letzte Stundenkerze fehlt noch", letzte=str(stunden.index[-1]))
            return
        neu = plan_rechnen(stunden, self.now)
        if neu is None:
            self.ev("zu wenig Kerzen für den Plan", stundenkerzen=len(stunden))
            return
        alt = {(k["name"], k["beruehrt"]) for k in (plan or {}).get("kandidaten", [])}
        if plan is None or alt != {(k["name"], k["beruehrt"]) for k in neu["kandidaten"]}:
            self.ev("Plan neu", kerzen_4h=neu["kerzen_4h"], atr_4h=neu["atr_4h"],
                    wartend=[{"zone": k["name"], "seite": SEITE[k["d"]], "linie": round(k["linie"], 2),
                              "stop": round(k["stop"], 2), "rest": k["rest"], "beruehrt": k["beruehrt"]}
                             for k in neu["kandidaten"]])
        self.st["plan"] = neu
        grenze = str(self.now - pd.Timedelta(days=MERKEN_TAGE))
        self.st["verbraucht"] = {k: v for k, v in self.st["verbraucht"].items() if str(v.get("zeit")) >= grenze[:19]}
        namen = {k["name"] for k in neu["kandidaten"]}
        self.st["versuche"] = {k: v for k, v in self.st["versuche"].items() if k in namen}

    def beruehrungen(self, m5: pd.DataFrame, wo_ids: set[str]) -> None:
        """Eine Zone ohne Order beim Broker ist verbraucht, sobald der Kurs ihre Linie erreicht hat: laut Stundenkerzen
        (Plan), laut 5-Minuten-Kerzen seit dem Plan oder laut aktuellem Kurs. Liegt die Order, entscheidet der Broker."""
        plan, q = self.st.get("plan"), self.q
        if not plan:
            return
        live = {o["name"] for o in self.st["orders"] if o["dealId"] in wo_ids and not o.get("loeschen")}
        neu = m5[m5.index >= pd.Timestamp(plan["gerechnet_bis"])]
        for k in plan["kandidaten"]:
            name, d, linie = k["name"], k["d"], k["linie"]
            if name in self.st["verbraucht"] or name in live:
                continue
            if k["beruehrt"]:
                self.verbrauche(name, "Linie schon berührt (Stundenkerzen), ohne dass eine Order lag")
            elif len(neu) and (neu["ask_low"].min() <= linie if d > 0 else neu["high"].max() >= linie):
                self.verbrauche(name, "Linie berührt (5-Minuten-Kerzen), ohne dass eine Order lag")
            elif q.bid > 0 and q.offer > 0 and (q.offer <= linie if d > 0 else q.bid >= linie):
                self.verbrauche(name, "Kurs steht schon an oder hinter der Linie")

    # ---- Orders ----

    def sperren(self, fremde: list[dict]) -> tuple[list[str], list[str]]:
        """Gründe, warum gerade keine Order liegen darf (dann werden liegende gelöscht), und Gründe, warum nur keine
        neue gelegt wird (liegende bleiben)."""
        plan = self.st.get("plan")
        alter = self.now - pd.Timestamp(plan["stunde"]) if plan else None
        hart, weich = [], []
        if self.st.get("trade"):
            hart.append("ein Trade ist offen")
        if wochenende(self.now):
            hart.append("Wochenende (Freitag 16:45 bis Sonntag 18:05 Uhr New York)")
        if self.st.get("pausiert"):
            hart.append(f"Pause ab {PAUSE_R:.0f} R")
        if not vorab_ok():
            hart.append("VORAB_gold_zonen_bot.yaml nicht festgelegt")
        if fremde:
            hart.append("fremde Gold-Position auf dem Konto")
        if self.fremde_orders:
            hart.append("fremde Gold-Order auf dem Konto")
        if self.andere_gold:
            hart.append(f"{KONTO_NAME} ist laut journal/konten.json auch für {', '.join(self.andere_gold)} vergeben")
        if plan is None or alter >= PLAN_ZU_ALT:
            hart.append("kein Plan" if plan is None else "Plan älter als 4 Stunden")
        elif alter >= STUNDE:
            weich.append("Plan nicht aus dieser Stunde")
        return hart, weich

    def ordern(self, fremde: list[dict], m5: pd.DataFrame, wo_ids: set[str], available_eur: float | None) -> None:
        """Höchstens eine Limit-Order beim Broker: die wartende Zone, deren Linie dem Kurs am nächsten liegt (Kauf-Linie
        gegen den Ask, Verkaufs-Linie gegen den Bid). Das Konto hat kein Hedging: Eine zweite Order der Gegenrichtung
        könnte einen offenen Trade schließen."""
        hart, weich = self.sperren(fremde)
        q = self.q
        if not len(m5):
            weich.append("keine 5-Minuten-Kerzen")
        if not q.tradeable:
            weich.append("Markt gerade nicht handelbar")
        elif not (q.bid > 0 and q.offer > 0):
            weich.append("kein Kurs")
        gruende = hart + weich
        if gruende != (self.st.get("keine_order") or []):   # nur melden, wenn sich etwas ändert
            self.st["keine_order"] = gruende
            if gruende:
                self.ev("keine neue Order", gruende=gruende)
        plan = self.st.get("plan") or {}
        live = {o["name"] for o in self.st["orders"] if o["dealId"] in wo_ids and not o.get("loeschen")}
        soll = None
        if not hart:
            kand = [k for k in plan.get("kandidaten", []) if k["name"] not in self.st["verbraucht"]
                    and (not k["beruehrt"] or k["name"] in live)]
            if kand:
                soll = min(kand, key=lambda k: abs((q.offer if k["d"] > 0 else q.bid) - k["linie"]))
        for o in list(self.st["orders"]):
            if soll is not None and o["name"] == soll["name"]:
                o.pop("loeschen", None)
                continue
            if weich and not hart and o["name"] not in self.st["verbraucht"]:
                continue                                    # ohne frischen Plan oder Kurs nichts anfassen
            self.loesche(o, "; ".join(hart) if hart else "Zone gilt nicht mehr oder ist nicht mehr die nächste")
        if gruende or soll is None or self.st["orders"]:    # liegt noch eine Order (auch eine nicht gelöschte): warten
            return
        self.lege(soll, plan, available_eur)

    def lege(self, k: dict, plan: dict, available_eur: float | None) -> None:
        from suche.r6_bots import deal_id
        q, d, name = self.q, k["d"], k["name"]
        linie, stop = round(k["linie"], 2), round(k["stop"], 2)
        dist = abs(linie - stop)
        ziel = round(gz.ziel_kurs((plan.get("linien") or {}).get(str(-d)) or [], d, linie, dist), 2)
        fest, spaeter = [], []                               # fest: zählt als Versuch, spaeter: nächster Lauf
        size, warum = groesse(dist, q) if q.eur_rate else (None, "")
        if not q.eur_rate:
            spaeter.append("kein Kurs EUR/USD")
        elif size is None:
            fest.append(warum)
        elif available_eur is not None:
            marge = size * (q.lot or 1) * linie * q.margin_pct / 100 / (q.eur_rate or 1)
            if marge > 0.8 * available_eur:
                spaeter.append(f"zu wenig freie Marge ({available_eur:.0f} €)")
        if q.min_dist and dist < q.min_dist:
            fest.append("Stop näher als der Mindestabstand des Brokers")
        if q.min_dist and d * ((q.offer if d > 0 else q.bid) - linie) < q.min_dist:
            spaeter.append("Kurs näher an der Linie als der Mindestabstand des Brokers")
        info = {"zone": name, "seite": SEITE[d], "linie": linie, "stop": stop, "ziel": ziel, "size": size,
                "risiko_usd": round(dist, 2)}
        if fest or spaeter:
            merk = {"zone": name, "gruende": fest + spaeter}
            if fest or merk != self.st.get("wartet"):       # dieselbe Lage nur einmal melden
                self.ev("Order nicht gelegt", **info, gruende=fest + spaeter)
            self.st["wartet"] = merk
            if fest:
                self.versuch(name, fest[0])
            return
        self.st.pop("wartet", None)
        body = {"epic": EPIC, "direction": "BUY" if d > 0 else "SELL", "size": size, "level": linie, "type": "LIMIT",
                "goodTillDate": order_ende(self.now).strftime(FMT), "guaranteedStop": False, "stopLevel": stop,
                "profitLevel": ziel}
        if not self.send:
            self.ev("würde Order legen", **info, gilt_bis=body["goodTillDate"])
            return
        self.nur_mein_konto()                                # falsches Konto: der Lauf bricht ab, nichts ist gesendet
        try:
            ref = self.client._request("POST", "/workingorders", json=body).json()["dealReference"]
            conf = self.client.confirm(ref)
        except Exception as err:            # noqa: BLE001 - kein zweiter Versuch im selben Lauf
            # Vielleicht liegt die Order trotzdem beim Broker. Sie bleibt ohne Deal-ID im Zustand: Der nächste Lauf
            # findet sie wieder (zuordnen) oder sieht, dass es sie nicht gibt. Bis dahin legt der Bot keine zweite.
            self.st["orders"].append({"name": name, "d": d, "linie": linie, "innen": round(k["innen"], 3), "stop": stop,
                                      "ziel": ziel, "size": size, "dealId": None, "gelegt_utc": self.stamp,
                                      "gilt_bis": body["goodTillDate"]})
            self.ev("Order fehlgeschlagen", **info, fehler=str(err)[:200])
            self.versuch(name, "Order fehlgeschlagen")
            return
        if str((conf or {}).get("dealStatus") or "").upper() != "ACCEPTED":
            self.ev("Order abgelehnt", **info, grund=(conf or {}).get("reason") or str(conf)[:200])
            self.versuch(name, "Order abgelehnt")
            return
        self.st["orders"].append({"name": name, "d": d, "linie": linie, "innen": round(k["innen"], 3), "stop": stop,
                                  "ziel": ziel, "size": size, "dealId": str(deal_id(conf)), "gelegt_utc": self.stamp,
                                  "gilt_bis": body["goodTillDate"]})
        self.ev("Order gelegt", **info, dealId=str(deal_id(conf)), gilt_bis=body["goodTillDate"])

    def versuch(self, name: str, grund: str) -> None:
        n = self.st["versuche"][name] = int(self.st["versuche"].get(name, 0)) + 1
        if n >= MAX_VERSUCHE:
            self.verbrauche(name, f"{MAX_VERSUCHE}-mal keine Order möglich ({grund})")


def run(client, state: dict, now: datetime, send_orders: bool = True) -> tuple[dict, list[dict], list[dict], dict]:
    """Ein Lauf. Rückgabe: neuer Stand, Ereignisse, fertige Trades, Blick (für das Cockpit)."""
    from gold.bot import konten
    from suche.demo_bots import eur_rate, quote_from_market
    from suche.r6_bots import arbeitsorders

    lauf = Lauf(client, state, now, send_orders)
    accounts = client.accounts()
    konto = next((a for a in accounts if str(a.get("accountId")) == KONTO), None)
    if konto is None or KONTO.endswith(HAUPT_ENDUNG):
        lauf.ev("kein Konto", konto="…" + KONTO[-4:])
        return lauf.st, lauf.log, [], {"status": f"{KONTO_NAME} nicht gefunden, nichts gehandelt"}
    available = _num((konto.get("balance") or {}).get("available"))
    # nur lesen: bekommt laut journal/konten.json ein anderer Gold-Bot dieses Konto, legt dieser Bot keine Order
    lauf.andere_gold = sorted(bid for bid, aid in (konten.load().get("zuordnung") or {}).items()
                              if str(aid) == KONTO and "gold" in str(bid).lower() and bid != BOT_ID)
    vorher = client.account_id
    client.switch_account(KONTO)
    try:
        lauf.q = q = quote_from_market(client.market(EPIC), None)
        q.eur_rate = eur_rate(client, q.currency, {})
        gold = [p for p in client.positions() if p.get("market", {}).get("epic") == EPIC]
        wo = arbeitsorders(client, EPIC)
        wo_ids = {str(w.get("dealId")) for w in wo}
        lauf.zuordnen(wo)
        m5 = lauf.kerzen5()
        lauf.abgleich(gold, wo_ids)
        lauf.fuehren(m5)                                    # vor dem neuen Plan: das Ziel gilt zur Zeit der Füllung
        tr = lauf.st.get("trade")
        meine = ({tr["dealId"]} if tr else set()) | lauf.eigene_zu
        fremde = [p for p in gold if str(p["position"].get("dealId")) not in meine]
        fremd = {"positionen": sorted(str(p["position"].get("dealId")) for p in fremde), "orders": lauf.fremde_orders}
        if fremd != (lauf.st.get("fremd") or {"positionen": [], "orders": []}):       # nur melden, wenn sich etwas ändert
            lauf.st["fremd"] = fremd
            if fremde or lauf.fremde_orders:
                lauf.ev("fremdes Gold auf dem Konto", **fremd)
        lauf.planen(m5)
        lauf.beruehrungen(m5, wo_ids)
        lauf.ordern(fremde, m5, wo_ids, available)
        lauf.st["stand"] = lauf.stamp
        return lauf.st, lauf.log, lauf.fertige, blick_auf(lauf.st, q)
    finally:
        with contextlib.suppress(Exception):
            if vorher and vorher != KONTO:
                client.switch_account(vorher)


def blick_auf(st: dict, q) -> dict:
    """Was der Bot gerade sieht (für das Cockpit): Kurs, Plan und wartende Zonen."""
    plan = st.get("plan") or {}
    liegt = {o["name"] for o in st.get("orders", [])}
    wartend = [{"zone": k["name"], "seite": SEITE[k["d"]], "linie": round(k["linie"], 2), "stop": round(k["stop"], 2),
                "noch_kerzen": k["rest"],
                "stand": ("Order liegt" if k["name"] in liegt else
                          "verbraucht: " + st["verbraucht"][k["name"]]["grund"] if k["name"] in st.get("verbraucht", {})
                          else "wartet (nicht die nächste Linie oder gesperrt)")}
               for k in plan.get("kandidaten", [])]
    return {"kurs": round(float(q.bid), 2) if q else None, "plan_von": plan.get("stunde"),
            "letzte_4h_kerze_bis": plan.get("letzte_4h"), "atr_4h": plan.get("atr_4h"), "zonen": wartend,
            "keine_order_weil": st.get("keine_order") or []}


# --------------------------------------------------------------------------------------------------------------------
# Journal und Cockpit

def status(st: dict) -> str:
    if st.get("pausiert"):
        return "Pause: " + st["pausiert"]["grund"]
    tr = st.get("trade")
    if tr and tr.get("weg_seit"):
        return "Position beim Broker geschlossen, der Bot liest den Schlusskurs"
    if tr:
        return (f"{SEITE[tr['richtung']]} offen ab {tr['entry']:.2f}, Stop {tr['stop']:.2f}"
                + (f", Ziel {tr['ziel']:.2f}" if tr.get("ziel") else "") + (", Stop am Einstieg" if tr.get("einstand") else ""))
    orders = st.get("orders") or []
    if orders:
        return "Order liegt: " + ", ".join(f"{SEITE[o['d']]} bei {o['linie']:.2f} (Stop {o['stop']:.2f})" for o in orders)
    if st.get("keine_order"):
        return "keine Order: " + "; ".join(st["keine_order"])
    if not st.get("plan"):
        return "wartet auf den ersten Plan"
    return "keine Order, wartet auf den nächsten Bruch einer Zone"


def cockpit(st: dict, alle_trades: list[dict], blick: dict) -> dict:
    tr = st.get("trade")
    return {"bot": BOT_ID, "name": NAME, "konto": f"{KONTO_NAME} …" + KONTO[-4:], "stand": st.get("stand"),
            "start": st.get("start"), "pausiert": st.get("pausiert"), "status": status(st), "regel": REGEL,
            "backtest": TEST, "vorab": "suche/VORAB_gold_zonen_bot.yaml", "vorab_ok": vorab_ok(),
            "offen": [{k: tr.get(k) for k in ("id", "zone", "richtung", "entry", "stop", "ziel", "ziel_r", "size", "r_usd",
                                             "opened_utc", "bestes", "einstand")}] if tr else [],
            "orders": [{k: o.get(k) for k in ("name", "d", "linie", "stop", "ziel", "size", "gelegt_utc", "gilt_bis")}
                       for o in st.get("orders") or []],
            "zusammenfassung": bewertung(alle_trades), "letzte_trades": alle_trades[-10:], "blick": blick}


def _ohne_zeit(st: dict) -> dict:
    out = {k: v for k, v in (st or {}).items() if k != "stand"}
    if out.get("trade"):
        out["trade"] = {k: v for k, v in out["trade"].items() if k != "gesehen_bis"}
    return out


def schreiben(st: dict, log: list[dict], fertige: list[dict], blick: dict, jdir: Path = JDIR,
              cockpit_pfad: Path = COCKPIT) -> bool:
    """Schreibt Zustand, Log, Trades und Cockpit. Hat sich außer der Uhrzeit nichts geändert, schreibt der Lauf nichts
    (sonst gäbe es alle 5 Minuten einen Journal-Commit ohne Inhalt). Der Plan ändert sich jede Stunde."""
    for p in (jdir, cockpit_pfad):
        if p.name in GOLD_BOT_DATEIEN:
            raise RuntimeError(f"{p} gehört dem Gold-Bot")
    pfad = jdir / "state.json"
    alt = json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else None
    if alt is not None and not log and not fertige and _ohne_zeit(alt) == _ohne_zeit(st) and cockpit_pfad.exists():
        return False
    jdir.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for name, rows in (("log.jsonl", log), ("trades.jsonl", fertige)):
        if rows:
            with open(jdir / name, "a", encoding="utf-8") as fh:
                fh.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    alle = sb._lies_jsonl(jdir / "trades.jsonl")
    cockpit_pfad.write_text(json.dumps(cockpit(st, alle, blick), ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8")
    return True


def main(argv: list[str]) -> int:
    from gold.bot.capital import CapitalClient
    from gold.bot.runner import CRED_KEYS, clean_credentials

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="nur rechnen, keine Order")
    args = ap.parse_args(argv)
    creds = clean_credentials({k: os.environ.get(k, "") for k in CRED_KEYS})
    if not all(creds):
        print("Keine Capital.com-Zugangsdaten, Gold-Zonen-Bot übersprungen")
        return 0
    path = JDIR / "state.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    client = CapitalClient(*creds, environment="demo")
    client.login()
    try:
        st, log, fertige, blick = run(client, state, datetime.now(timezone.utc), send_orders=not args.dry_run)
    finally:
        with contextlib.suppress(Exception):
            client.logout()
    print(json.dumps({"ereignisse": log, "fertig": fertige, "status": status(st), "blick": blick},
                     ensure_ascii=False, default=str))
    if not args.dry_run:
        schreiben(st, log, fertige, blick)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
