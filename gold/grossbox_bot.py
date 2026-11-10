"""Gold Groß-Box: die große Box aus Runde 12d (Seite gross_box) live auf einem Capital.com-DEMOKONTO. Nie echtes Geld.

    python -m gold.grossbox_bot              # ein Lauf: Kerzen holen, offene Trades führen, neuer Trade?
    python -m gold.grossbox_bot --dry-run    # nur rechnen und zeigen, keine Order

Kirons Wahl vom 10.11.2026 17:35 UTC ("Gold Groß-Box" auf der Karte "Welche Strategie soll mit der neuen Regel live
auf Demo?"). Grundlage ist die neue Bewertung (suche/VORAB_bewertung_2024_26.yaml, 2024 bis 2026 zählt): 11/2024 bis
10/2026 945 Trades, 9,1 je Woche, Gewinnfaktor 1,21, 1,5-facher Spread 1,15, Zufall 95,5 %. Größter Rückgang im
Backtest 76,7 R. Regeln und Urteil in suche/VORAB_gold_grossbox.yaml, Prüfsumme im Protokoll vor dem ersten Trade, ohne
passende Prüfsumme öffnet der Bot nichts.

Regeln (gold/tiktok_schatten.gross_box, kerze=False, auf 15-Min.-Bid-Kerzen):
- Große Box = SuperTrend 20/2 auf fertigen 1-Std.-Kerzen und letzter 4-Std.-Strukturbruch zeigen gleich, sie endet,
  sobald eine der beiden dreht. Einstiege nur in Boxrichtung (Kauf und Verkauf): bei Beginn der Box, bei jedem
  15-Min.-Wechsel des SuperTrend 20/1,75 und bei jedem 15-Min.-Strukturbruch. Höchstens 3 offen.
- Ein Drittel mit Ziel 1 R beim Broker, danach Stop des Rests auf den Einstieg. Der Rest läuft ohne Ziel bis zum Ende der
  großen Box und wird dann zum Markt geschlossen. Stop beider Teile beim Broker.

Live-Ausführung wie beim Gold-Short-Bot (gold/short_bot.py, dessen Hilfen der Bot nutzt):
- Jeder Lauf (Minute 1, 16, 31, 46) holt etwa 30 Tage Viertelstunden-Kerzen. 1-Std.- und 4-Std.-Kerzen zählen nur,
  wenn sie fertig sind. Dahinter hängt eine Kerze "jetzt" mit dem aktuellen Kurs. Ein neuer Trade ist ein Einstieg des
  Modells genau in dieser Kerze. Zeigt die große Box in der Kerze "jetzt" nicht mehr in Trade-Richtung, ist der normale
  Ausstieg fällig.
- Nur Account 6 (Endung 3678), den er mit dem Laborbot London GBP/USD teilt (anderer Markt, kein Netting). Nie das
  Hauptkonto des Gold-Bots (Endung 3150). Er kennt seine Positionen an der Deal-ID. Liegt eine fremde Gold-Position auf
  dem Konto, öffnet er nichts Neues.
- Ab -25 R seit Start nichts Neues mehr (Sicherung), zurück nur mit Kirons Entscheidung.
- Er schreibt nur journal/gold-grossbox/ und journal/gold-grossbox.json, nie die Dateien des Gold-Bots.
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

import numpy as np
import pandas as pd

from gold import short_bot as sb
from gold import tiktok_schatten as ts

ROOT = ts.ROOT
BOT_ID = "gold-grossbox"
NAME = "Gold Groß-Box (Runde 12d)"
EPIC = ts.EPIC
KONTO = "332263759556203678"          # Account 6, geteilt mit dem Laborbot r6-london-gbpusd (GBP/USD)
KONTO_NAME = "Account 6"
HAUPT_ENDUNG = sb.HAUPT_ENDUNG        # Hauptkonto des Gold-Bots, hier nie handeln
GEWICHTE = ts.LAUFEN[1]               # ein Drittel, zwei Drittel
ZIEL_R = ts.LAUFEN[0][0]              # das erste Drittel bei 1 R, der Rest bis zur neuen Box
RISIKO_EUR = 5.0
MAX_OFFEN = ts.GROSS_MAX_OFFEN        # 3, wie im Backtest
MAX_OZ_TRADE, MAX_OZ_GESAMT = 1.0, 3.0
MAX_RISIKO_FAKTOR = 2.0               # Runden auf die kleinste Größe darf das Risiko höchstens verdoppeln
PAUSE_R = -25.0
ZWISCHEN_NACH, ZWISCHEN_PF = 15, 0.6
URTEIL_NACH, URTEIL_PF = 40, 1.2
MIN_BARS, CHUNKS = sb.MIN_BARS, sb.CHUNKS
VIERTEL = sb.VIERTEL
VORAB = ROOT / "suche" / "VORAB_gold_grossbox.yaml"
KEY = "VORAB_gold_grossbox sha256 "
JDIR = ROOT / "journal" / "gold-grossbox"
COCKPIT = ROOT / "journal" / "gold-grossbox.json"
GOLD_BOT_DATEIEN = sb.GOLD_BOT_DATEIEN
SEITE = {1: "Kauf", -1: "Verkauf"}
REGEL = ("Große Box aus Runde 12d: 1-Std.-SuperTrend 20/2 und 4-Std.-Strukturbruch gleich, Einstiege nur in "
         "Boxrichtung (Boxbeginn, 15-Min.-SuperTrend 20/1,75, 15-Min.-Strukturbruch), höchstens 3 offen. Ein Drittel "
         "bei 1 R, dann Einstand, der Rest bis zur neuen Box. 5 € Risiko je Trade.")
TEST = ("Bewertung 2024-26: 11/2024 bis 10/2026 945 Trades (9,1 je Woche), GF 1,21, +93 R, 1,5x Spread 1,15, Zufall "
        "95,5 %. Größter Rückgang 76,7 R, 53 % der Wochen im Minus. 2024-26 war ein starker Gold-Aufwärtstrend.")


def vorab_ok() -> bool:
    """Ist suche/VORAB_gold_grossbox.yaml mit seiner Prüfsumme im Protokoll festgelegt?"""
    from suche.runde1 import journal_lines, last_value, sha256_text
    if not VORAB.exists():
        return False
    return last_value(journal_lines(), KEY) == sha256_text(VORAB.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------------------------------------
# Das Modell auf den Kerzen

def modell(b: ts.Basis, n: int | None = None) -> tuple[list[dict], np.ndarray]:
    """gross_box (ohne Kerzen-Filter) mit der Führung des Backtests. Die Ebenen kommen nur aus den ersten n Kerzen (die
    fertigen), gehandelt wird auf allen Kerzen von b (live hängt dahinter die Kerze "jetzt"). Jeder Trade bekommt _j0
    (Einstiegskerze). Zweiter Wert: Richtung der großen Box je Kerze von b (0 = keine Box)."""
    n = len(b) if n is None else n
    bz = sb._bis(b, n)
    m15 = ts.ebene(bz, "15m")
    h1 = sb.fertig(ts.ebene(bz, "1h"), bz, "1h")
    h4 = sb.fertig(ts.ebene(bz, "4h"), bz, "4h")
    trades = ts.gross_box(b, m15, h1, h4, kerze=False)
    for t in trades:
        t["_j0"] = int(np.searchsorted(b.t, np.datetime64(pd.Timestamp(t["einstieg_zeit"]))))
    return trades, ts.grosse_richtung(b, h1, h4)


def groessen(dist: float, q) -> tuple[list[float] | None, str]:
    """Größe je Teil: zusammen RISIKO_EUR bis zum Stop, höchstens MAX_OZ_TRADE Unzen, je Teil mindestens die kleinste
    Größe. Größen None, wenn das Runden das Risiko mehr als verdoppeln würde."""
    if not q.eur_rate or not dist > 0:
        return None, "kein Kurs EUR/USD oder kein Stopabstand"
    lot = q.lot or 1.0
    gesamt = min(RISIKO_EUR * q.eur_rate / (dist * lot), MAX_OZ_TRADE / lot)
    step = q.size_step or q.min_size
    out = [round(max(math.floor(round(gesamt * w / step, 9)) * step, q.min_size), 8) for w in GEWICHTE]
    risiko = sum(out) * lot * dist / q.eur_rate
    if risiko > MAX_RISIKO_FAKTOR * RISIKO_EUR:
        return None, f"kleinste Größe zu grob ({risiko:.2f} € Risiko statt {RISIKO_EUR:.0f} €)"
    return out, ""


def pf(r) -> float | None:
    return ts.pf(r)


def bewertung(trades: list[dict]) -> dict:
    r = [float(t["r"]) for t in trades]
    n = len(r)
    if n >= URTEIL_NACH:
        erste = r[:URTEIL_NACH]
        ok = (pf(erste) or 0) >= URTEIL_PF and sum(erste) > 0
        text = ("bestanden nach 40 Trades, Kiron entscheidet über den nächsten Schritt" if ok else
                "durchgefallen nach 40 Trades, Vorschlag an Kiron: stoppen oder neue Regeln mit neuem Vorab")
    elif n >= ZWISCHEN_NACH and (pf(r) or 0) < ZWISCHEN_PF:
        text = f"Zwischencheck nach {n} Trades: Gewinnfaktor unter {ZWISCHEN_PF}, Vorschlag an Kiron: stoppen"
    else:
        text = f"läuft ({n} von {URTEIL_NACH} Trades)"
    return {"trades": n, "pf_r": pf(r), "summe_r": round(float(sum(r)), 2),
            "trefferquote": round(sum(x > 0 for x in r) / n, 3) if n else None,
            "summe_eur": round(float(sum(float(t.get("pnl_eur") or 0) for t in trades)), 2), "urteil": text}


_num = sb._num
_jetzt = sb._jetzt


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
        self.send = send_orders
        self.log: list[dict] = []
        self.fertige: list[dict] = []
        self.q = None
        self.st.setdefault("format", 1)
        self.st.setdefault("start", self.stamp)
        self.st.setdefault("offen", [])
        self.st.setdefault("summe_r", 0.0)
        self.st.setdefault("trades", 0)
        self.andere_gold: list[str] = []

    def ev(self, event: str, **kw) -> None:
        self.log.append({"time": self.stamp, "event": event, **kw})

    def kurs_raus(self, d: int) -> float:
        """Zu diesem Kurs schließt ein Teil zum Markt: Kauf am Bid, Verkauf am Ask."""
        return self.q.bid if d > 0 else self.q.offer

    # ---- Broker ----

    def aendere(self, teil: dict, stop: float, warum: str) -> bool:
        body = {"stopLevel": round(stop, 2)}
        if teil.get("ziel") is not None:
            body["profitLevel"] = round(teil["ziel"], 2)
        if not self.send:
            self.ev("würde ändern", dealId=teil["dealId"], **body, warum=warum)
            return True
        try:
            ref = self.client._request("PUT", f"/positions/{teil['dealId']}", json=body).json().get("dealReference")
            conf = self.client.confirm(ref) if ref else {}
        except Exception as err:            # noqa: BLE001 - dann schließt der Bot den Teil zum Markt
            self.ev("ändern fehlgeschlagen", dealId=teil["dealId"], warum=warum, fehler=str(err)[:200])
            return False
        if conf and str(conf.get("dealStatus") or "").upper() == "REJECTED":
            self.ev("ändern abgelehnt", dealId=teil["dealId"], warum=warum, grund=conf.get("reason"))
            return False
        teil["stop"] = body["stopLevel"]
        self.ev("geändert", dealId=teil["dealId"], **body, warum=warum)
        return True

    def schliesse(self, tr: dict, teil: dict, warum: str) -> None:
        if not self.send:
            self.ev("würde schließen", dealId=teil["dealId"], warum=warum, kurs=self.kurs_raus(tr["richtung"]))
            return
        try:
            conf = self.client.close_position(teil["dealId"])
        except Exception as err:            # noqa: BLE001 - nächster Lauf versucht es wieder, Stop liegt beim Broker
            self.ev("schließen fehlgeschlagen", dealId=teil["dealId"], warum=warum, fehler=str(err)[:200])
            return
        level = _num((conf or {}).get("level")) or self.kurs_raus(tr["richtung"])
        teil.update(offen=False, exit=round(float(level), 2), grund=warum, closed_utc=self.stamp)
        self.ev("geschlossen", dealId=teil["dealId"], kurs=level, warum=warum)

    # ---- Abgleich mit dem Konto ----

    def abgleich(self, gold: list[dict]) -> None:
        """Teile, die beim Broker nicht mehr offen sind (Stop oder Ziel), schließen. Der Teil mit Ziel, der am Ziel oder
        besser schloss, zählt als Ziel erreicht (dann Einstand für den Rest)."""
        from suche.demo_bots import broker_exit
        pos = {str(p["position"].get("dealId")): p["position"] for p in gold}
        for tr in self.st["offen"]:
            d = tr["richtung"]
            for teil in tr["teile"]:
                if not teil["offen"]:
                    continue
                if teil["dealId"] in pos:                  # Stop und Ziel so, wie sie beim Broker stehen
                    p = pos[teil["dealId"]]
                    teil["stop"] = _num(p.get("stopLevel")) or teil.get("stop")
                    teil["ziel"] = _num(p.get("profitLevel"))
                    continue
                level, quelle = broker_exit(self.client, {"dealId": teil["dealId"], "opened_utc": tr["opened_utc"]},
                                            self.now.to_pydatetime())
                if level is None:
                    level, quelle = teil.get("stop") or teil["entry"], "geschätzt (Stop)"
                orig, tol = teil.get("ziel_orig"), 0.1 * tr["dist"]
                if orig is not None and (quelle == "TP" or d * (level - orig) >= -tol):
                    grund = "ziel"
                    tr["tp1"] = True
                elif quelle in ("SL", "geschätzt (Stop)"):
                    grund = "einstand" if tr.get("einstand") else "stop"
                else:
                    grund = f"beim Broker ({quelle or 'unbekannt'})"
                teil.update(offen=False, exit=round(float(level), 2), grund=grund, closed_utc=self.stamp)
                self.ev("Teil zu beim Broker", trade=tr["id"], dealId=teil["dealId"], kurs=level, grund=grund)

    def buchen(self) -> None:
        rest = []
        for tr in self.st["offen"]:
            if any(t["offen"] for t in tr["teile"]):
                rest.append(tr)
                continue
            d = tr["richtung"]
            size = sum(t["size"] for t in tr["teile"])
            r = sum(t["size"] * d * (t["exit"] - t["entry"]) for t in tr["teile"]) / (size * tr["dist"])
            pnl_usd = sum(t["size"] * (self.q.lot or 1.0) * d * (t["exit"] - t["entry"]) for t in tr["teile"])
            rate = self.q.eur_rate
            rec = {**{k: tr[k] for k in ("id", "art", "signal", "einstieg_zeit", "opened_utc", "dist", "richtung")},
                   "seite": SEITE[d], "size": round(size, 4),
                   "entry": round(sum(t["size"] * t["entry"] for t in tr["teile"]) / size, 2),
                   "exit": round(sum(t["size"] * t["exit"] for t in tr["teile"]) / size, 2),
                   "closed_utc": self.stamp, "r": round(r, 3), "pnl_usd": round(pnl_usd, 2),
                   "pnl_eur": round(pnl_usd / rate, 2) if rate else None,
                   "teile": [{k: t.get(k) for k in ("dealId", "size", "entry", "exit", "grund", "ziel_nr")}
                             for t in tr["teile"]], "erstes_ziel": tr.get("tp1")}
            self.fertige.append(rec)
            self.st["summe_r"] = round(float(self.st["summe_r"]) + rec["r"], 3)
            self.st["trades"] = int(self.st["trades"]) + 1
            self.ev("Trade fertig", trade=tr["id"], seite=rec["seite"], r=rec["r"], pnl_eur=rec["pnl_eur"])
        self.st["offen"] = rest
        if self.st.get("pausiert") is None and self.st["summe_r"] <= PAUSE_R:
            self.st["pausiert"] = {"seit": self.stamp, "grund": f"Summe R seit Start {self.st['summe_r']} (Grenze "
                                                                f"{PAUSE_R}), zurück nur mit Kirons Entscheidung"}
            self.ev("Pause", grund=self.st["pausiert"]["grund"])

    # ---- Führung der offenen Trades ----

    def fuehren(self, box_jetzt: int) -> None:
        """1. Nach dem ersten Ziel Stop des Rests auf den Einstieg. 2. Zeigt die große Box in der Kerze "jetzt" nicht mehr
        in Trade-Richtung: Rest zum Markt schließen (normaler Ausstieg "neue Box")."""
        q = self.q
        for tr in self.st["offen"]:
            d = tr["richtung"]
            offene = [t for t in tr["teile"] if t["offen"]]
            if not offene:
                continue
            if tr.get("tp1") and not tr.get("einstand"):
                tr["einstand"] = self.stamp
                for t in offene:
                    zu_nah = d * (self.kurs_raus(d) - t["entry"]) <= (q.min_dist or 0)
                    if zu_nah or not self.aendere(t, t["entry"], "einstand"):
                        self.schliesse(tr, t, "einstand")
                offene = [t for t in tr["teile"] if t["offen"]]
            if offene and box_jetzt != d:
                tr["box_ende"] = self.stamp
                self.ev("Box zu Ende", trade=tr["id"], box_jetzt=int(box_jetzt))
                for t in offene:
                    self.schliesse(tr, t, "neue_box")

    # ---- Neuer Trade ----

    def einstieg(self, b: ts.Basis, n: int, trades: list[dict], gold: list[dict], fremde: list[dict],
                 available_eur: float | None) -> None:
        from suche.demo_bots import open_market
        q = self.q
        t_ph = pd.Timestamp(b.t[n])
        kand = [t for t in trades if t["_j0"] == n]
        if not kand or self.st.get("letzte_kerze") == str(t_ph):
            return
        sig = kand[0]
        d = int(sig["richtung"])
        if not q.tradeable:
            self.ev("Signal, Markt zu", kerze=str(t_ph))
            return                                        # nächster Lauf versucht es wieder
        self.st["letzte_kerze"] = str(t_ph)
        gruende = []
        if not sb.frisch(t_ph, self.now):
            gruende.append("Signal zu alt")
        if self.st.get("pausiert"):
            gruende.append(f"Pause ab {PAUSE_R:.0f} R")
        if not vorab_ok():
            gruende.append("VORAB_gold_grossbox.yaml nicht festgelegt")
        offen = [tr for tr in self.st["offen"] if any(t["offen"] for t in tr["teile"])]
        if len(offen) >= MAX_OFFEN:
            gruende.append(f"schon {MAX_OFFEN} Trades offen")
        if any(tr["richtung"] != d for tr in offen):
            gruende.append("ein Trade der Gegenrichtung ist noch offen (kein Hedging)")
        if fremde:
            gruende.append("fremde Gold-Position auf dem Konto")
        if self.andere_gold:
            gruende.append(f"{KONTO_NAME} ist laut journal/konten.json auch für {', '.join(self.andere_gold)} vergeben")
        dist = float(sig["r_usd"])
        sizes, warum = groessen(dist, q)
        if sizes is None:
            gruende.append(warum)
        else:
            offen_oz = sum(t["size"] for tr in offen for t in tr["teile"] if t["offen"]) * (q.lot or 1)
            if offen_oz + sum(sizes) * (q.lot or 1) > MAX_OZ_GESAMT + 1e-9:
                gruende.append(f"mehr als {MAX_OZ_GESAMT:.0f} Unzen zusammen")
            marge = sum(sizes) * (q.lot or 1) * q.bid * q.margin_pct / 100 / (q.eur_rate or 1)
            if available_eur is not None and marge > 0.8 * available_eur:
                gruende.append(f"zu wenig freie Marge ({available_eur:.0f} €)")
        if q.min_dist and dist < q.min_dist:
            gruende.append("Stop näher als der Mindestabstand des Brokers")
        info = {"seite": SEITE[d], "art": sig.get("art"), "kerze": str(t_ph), "signal": sig["signal"],
                "dist": round(dist, 2)}
        if gruende:
            self.ev("Einstieg ausgelassen", **info, gruende=gruende)
            return
        abst = [ZIEL_R * dist, None]
        tr = {"id": f"{t_ph:%Y-%m-%dT%H:%M}", "art": sig.get("art"), "richtung": d, "signal": sig["signal"],
              "einstieg_zeit": str(t_ph), "opened_utc": self.stamp, "dist": round(dist, 2),
              "sim_einstieg": sig["einstieg"], "teile": [], "tp1": False, "einstand": None, "box_ende": None}
        if not self.send:
            self.ev("würde " + ("kaufen" if d > 0 else "verkaufen"), **info, groessen=sizes,
                    ziele=[None if a is None else round(a, 2) for a in abst])
            return
        for nr, (size, abstand) in enumerate(zip(sizes, abst), start=1):
            vorher = {str(p["position"].get("dealId")) for p in gold}
            order = {"size": size, "stop_dist": round(dist, 2),
                     "tp_dist": None if abstand is None else round(max(abstand, q.min_dist or 0), 2)}
            try:
                conf = open_market(self.client, EPIC, d, order)
            except Exception as err:            # noqa: BLE001 - kein zweiter Versuch, damit nichts doppelt entsteht
                self.ev("Order fehlgeschlagen", teil=nr, fehler=str(err)[:200])
                break
            if str((conf or {}).get("dealStatus") or "").upper() == "REJECTED":
                self.ev("Order abgelehnt", teil=nr, grund=(conf or {}).get("reason"))
                break
            gold = [p for p in self.client.positions() if p.get("market", {}).get("epic") == EPIC]
            neu = [p for p in gold if str(p["position"].get("dealId")) not in vorher]
            pos = neu[0]["position"] if len(neu) == 1 else None
            deal = str(pos.get("dealId")) if pos else str(((conf or {}).get("affectedDeals") or [{}])[0].get("dealId")
                                                           or conf.get("dealId"))
            level = (_num(pos.get("level")) if pos else _num((conf or {}).get("level"))) or (
                q.offer if d > 0 else q.bid)
            stop = (_num(pos.get("stopLevel")) if pos else None) or level - d * dist
            ziel = _num(pos.get("profitLevel")) if pos else None
            if ziel is None and order["tp_dist"] is not None:
                ziel = level + d * order["tp_dist"]
            tr["teile"].append({"dealId": deal, "size": size, "entry": round(level, 2), "ziel_nr": nr,
                                "stop": round(stop, 2), "ziel": None if ziel is None else round(ziel, 2),
                                "ziel_orig": None if ziel is None else round(ziel, 2),
                                "offen": True, "exit": None, "grund": None, "closed_utc": None})
        if tr["teile"]:
            self.st["offen"].append(tr)
            self.ev(("Kauf" if d > 0 else "Verkauf") + " eröffnet", **info,
                    teile=[{k: t[k] for k in ("dealId", "size", "entry", "stop", "ziel")} for t in tr["teile"]])


def run(client, state: dict, now: datetime, send_orders: bool = True) -> tuple[dict, list[dict], list[dict], dict]:
    """Ein Lauf. Rückgabe: neuer Stand, Ereignisse, fertige Trades, Blick (für das Cockpit)."""
    from gold.bot import konten
    from gold.bot.rules import bars_from_prices
    from suche.demo_bots import eur_rate, quote_from_market, with_now_bar

    lauf = Lauf(client, state, now, send_orders)
    accounts = client.accounts()
    konto = next((a for a in accounts if str(a.get("accountId")) == KONTO), None)
    if konto is None or KONTO.endswith(HAUPT_ENDUNG):
        lauf.ev("kein Konto", konto="…" + KONTO[-4:])
        return lauf.st, lauf.log, [], {"status": f"{KONTO_NAME} nicht gefunden, nichts gehandelt"}
    available = _num((konto.get("balance") or {}).get("available"))
    # nur lesen: bekommt laut journal/konten.json ein anderer Gold-Bot dieses Konto, öffnet dieser Bot nichts Neues
    lauf.andere_gold = sorted(bid for bid, aid in (konten.load().get("zuordnung") or {}).items()
                              if str(aid) == KONTO and "gold" in str(bid).lower() and bid != BOT_ID)
    vorher = client.account_id
    client.switch_account(KONTO)
    try:
        lauf.q = q = quote_from_market(client.market(EPIC), None)
        q.eur_rate = eur_rate(client, q.currency, {})
        gold = [p for p in client.positions() if p.get("market", {}).get("epic") == EPIC]
        lauf.abgleich(gold)
        lauf.buchen()
        meine = {t["dealId"] for tr in lauf.st["offen"] for t in tr["teile"]}
        fremde = [p for p in gold if str(p["position"].get("dealId")) not in meine]
        if fremde:
            lauf.ev("fremde Gold-Position", deals=[str(p["position"].get("dealId")) for p in fremde])
        bars, spread = bars_from_prices(ts.fetch_candles(client, EPIC, chunks=CHUNKS), lauf.now, "15min")
        blick: dict = {"kerzen": len(bars)}
        if len(bars) < MIN_BARS:
            lauf.ev("zu wenig Kerzen", kerzen=len(bars), braucht=MIN_BARS)
        else:
            t_ph = pd.Timestamp(bars.index[-1]) + VIERTEL
            bars2, sp2 = with_now_bar(bars, spread, t_ph, q.bid, q.offer)
            b = ts.basis(bars2, sp2)
            n = len(b) - 1
            trades, gd = modell(b, n)
            lauf.fuehren(int(gd[n]))
            lauf.buchen()
            lauf.einstieg(b, n, trades, gold, fremde, available)
            blick.update(blick_auf(b, n, trades, gd))
        lauf.st["stand"] = lauf.stamp
        return lauf.st, lauf.log, lauf.fertige, blick
    finally:
        with contextlib.suppress(Exception):
            if vorher and vorher != KONTO:
                client.switch_account(vorher)


def blick_auf(b: ts.Basis, n: int, trades: list[dict], gd: np.ndarray) -> dict:
    """Was das Modell gerade sieht (für das Cockpit): Richtung der großen Box und offene Trades im Modell."""
    box = int(gd[n])
    offen = [{"einstieg_zeit": t.get("einstieg_zeit"), "richtung": t.get("richtung"), "art": t.get("art"),
              "einstieg": t.get("einstieg"), "stop": t.get("stop")} for t in trades if t.get("offen")]
    return {"letzte_kerze": str(pd.Timestamp(b.t[n - 1])), "kurs": round(float(b.o[n]), 2),
            "grosse_box": {1: "Kauf", -1: "Verkauf"}.get(box, "keine (1 Std. und 4 Std. uneinig)"),
            "modell_offen": offen[:10]}


# --------------------------------------------------------------------------------------------------------------------
# Journal und Cockpit

def status(st: dict, blick: dict) -> str:
    if st.get("pausiert"):
        return "Pause: " + st["pausiert"]["grund"]
    offen = [tr for tr in st.get("offen", []) if any(t["offen"] for t in tr["teile"])]
    box = (blick or {}).get("grosse_box")
    teil = f"große Box: {box}" if box else "wartet auf Kerzen"
    if not offen:
        return f"kein Trade offen, {teil}"
    seiten = ", ".join(f"{SEITE[tr['richtung']]} ab {tr['teile'][0]['entry']:.2f}" for tr in offen)
    return f"{len(offen)} offen ({seiten}), {teil}"


def cockpit(st: dict, alle_trades: list[dict], blick: dict) -> dict:
    return {"bot": BOT_ID, "name": NAME, "konto": f"{KONTO_NAME} …" + KONTO[-4:], "stand": st.get("stand"),
            "start": st.get("start"), "pausiert": st.get("pausiert"), "status": status(st, blick), "regel": REGEL,
            "backtest": TEST, "vorab": "suche/VORAB_gold_grossbox.yaml", "vorab_ok": vorab_ok(),
            "offen": [{k: tr.get(k) for k in ("id", "art", "richtung", "einstieg_zeit", "dist", "tp1", "einstand")} |
                      {"teile": [{k: t.get(k) for k in ("size", "entry", "stop", "ziel", "offen")} for t in tr["teile"]]}
                      for tr in st.get("offen", [])],
            "zusammenfassung": bewertung(alle_trades), "letzte_trades": alle_trades[-10:], "blick": blick}


def schreiben(st: dict, log: list[dict], fertige: list[dict], blick: dict, jdir: Path = JDIR,
              cockpit_pfad: Path = COCKPIT) -> None:
    for p in (jdir, cockpit_pfad):
        if p.name in GOLD_BOT_DATEIEN:
            raise RuntimeError(f"{p} gehört dem Gold-Bot")
    jdir.mkdir(parents=True, exist_ok=True)
    (jdir / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for name, rows in (("log.jsonl", log), ("trades.jsonl", fertige)):
        if rows:
            with open(jdir / name, "a", encoding="utf-8") as fh:
                fh.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    alle = sb._lies_jsonl(jdir / "trades.jsonl")
    cockpit_pfad.write_text(json.dumps(cockpit(st, alle, blick), ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8")


def main(argv: list[str]) -> int:
    from gold.bot.capital import CapitalClient
    from gold.bot.runner import CRED_KEYS, clean_credentials

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="nur rechnen, keine Order")
    args = ap.parse_args(argv)
    creds = clean_credentials({k: os.environ.get(k, "") for k in CRED_KEYS})
    if not all(creds):
        print("Keine Capital.com-Zugangsdaten, Gold Groß-Box übersprungen")
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
    print(json.dumps({"ereignisse": log, "fertig": fertige, "offen": len(st.get("offen", [])), "blick": blick},
                     ensure_ascii=False, default=str))
    if not args.dry_run:
        schreiben(st, log, fertige, blick)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
