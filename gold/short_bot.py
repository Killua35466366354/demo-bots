"""Gold-Short-Bot: die große Strategie nur mit Shorts (Runde 12h) live auf einem Capital.com-DEMOKONTO. Nie echtes Geld.

    python -m gold.short_bot              # ein Lauf: Kerzen holen, offene Trades führen, neuer Short?
    python -m gold.short_bot --dry-run    # nur rechnen und zeigen, keine Order

Kirons Wunsch vom 06.11.2026 12:51 UTC: "gebe der nur short strategie einen eigenen live trading bot ... der nur short
bot soll ab jetzt live laufen". Die Regeln kommen aus dem Repo portfolio-manager, suche/VORAB_runde12h.yaml (Variante
gross_short) und suche/runde12h.py. Der Vorwärtstest ist hier in suche/VORAB_gold_short.yaml festgelegt, Prüfsumme in
journal/strategie-suche-protokoll.md vor dem ersten Trade. Ohne passende Prüfsumme öffnet der Bot nichts.

Ehrlich vorweg: gross_short ist im Backtest durchgefallen (11/2024 bis 10/2026 465 Trades, PF_R 0,94, -9 R, Kontrolle
2022 bis 2024 PF_R 0,66, gut nur 2026). Der Bot läuft auf Kirons ausdrücklichen Wunsch als Vorwärtstest.

Regeln wie gross_short (gold/tiktok_schatten.py rechnet die drei Seiten auf 15-Min.-Kerzen):
- Drei Seiten, nur Verkäufe, in dieser Reihenfolge: gross_klein_3, gross_box_kerze, gross_box. Kommt derselbe Einstieg
  von mehreren Seiten, zählt er einmal (die erste Seite gewinnt).
- Ziele mal 0,75: gross_klein_3 je ein Drittel bei 0,75, 1,5 und 2,25 R, gross_box_kerze und gross_box ein Drittel bei
  0,75 R und der Rest bis zur neuen Box. Nach dem ersten Ziel Stop auf Einstand.
- Prüfer: läuft der Kurs vor dem ersten Ziel 0,5 R gegen den Trade, ist er ein Fehltrade. Er schließt, sobald der Kurs
  wieder am Einstieg ist. Der Stop bleibt.
- Halten: wäre ein Trade zum normalen Ausstieg (Gegensignal, Ende der 4-Std.-Box, neue Box) im Minus, bleibt er offen,
  bis der Kurs wieder am Einstieg ist oder der Stop kommt.
- Sperre: kein neuer Short, solange ein offener Short schon ein Fehltrade ist.
Die Filter-Boxen von gross_klein_3 (4 Std. und 1 Std.) rechnen wie in runde12h.einzeln mit der alten Führung.

Risiko (Rat des Quant-Komitees vom 06.11.2026): 5 € bis zum Stop je Trade (0,5 % von 1.000 €), höchstens 4 Trades
zugleich offen, höchstens 1 Unze je Trade und 2 Unzen zusammen. Ab -10 R seit Start öffnet der Bot nichts Neues mehr,
offene Trades führt er zu Ende. Zurück nur mit Kirons Entscheidung (PR).

Live-Ausführung:
- Jeder Lauf (Minute 1, 16, 31, 46) holt etwa 30 Tage Viertelstunden-Kerzen und rechnet die drei Seiten neu. Die
  1-Std.- und 4-Std.-Kerzen zählen nur, wenn sie fertig sind. Dahinter hängt eine Kerze "jetzt" mit dem aktuellen Kurs.
  Ein neuer Short ist ein Einstieg der Strategie genau in dieser Kerze (Einstieg zur nächsten Eröffnung wie im Backtest,
  hier etwa 1 bis 4 Minuten danach zum Marktkurs).
- Stop und Ziele liegen beim Broker (je Drittel eine eigene Position). Einstand, Prüfer und Halten setzt der Bot beim
  nächsten Lauf (bis zu 15 Minuten später als im Backtest) über das Ändern von Stop und Ziel der offenen Positionen.
- Der Bot handelt nur auf Konto 5 (Endung 9086), das er mit dem Dow-Laborbot teilt (anderer Markt, kein Netting). Nie auf
  dem Hauptkonto des Gold-Bots (Endung 3150). Er kennt seine Positionen an der Deal-ID. Liegt eine fremde Gold-Position
  auf dem Konto, öffnet er nichts Neues (das Konto hat kein Hedging).
- Er schreibt nur journal/gold-short/ und journal/gold-short.json, nie die Dateien des Gold-Bots.
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

from gold import tiktok_schatten as ts

ROOT = ts.ROOT
BOT_ID = "gold-short"
EPIC = ts.EPIC
NY = ts.NY
KONTO = "332263750966269086"          # Account 5, geteilt mit dem Dow-Laborbot r5-ruecksetzer-us30 (US30)
HAUPT_ENDUNG = "3150"                 # Hauptkonto des Gold-Bots, hier nie handeln
SEITEN = ("gross_klein_3", "gross_box_kerze", "gross_box")
ZIEL_FAKTOR = 0.75
FEHL_F = 0.5
RISIKO_EUR = 5.0
MAX_OFFEN = 4
MAX_OZ_TRADE, MAX_OZ_GESAMT = 1.0, 2.0
MAX_RISIKO_FAKTOR = 2.0               # Runden auf die kleinste Größe darf das Risiko höchstens verdoppeln
PAUSE_R = -10.0
ZWISCHEN_NACH, ZWISCHEN_PF = 15, 0.6
URTEIL_NACH, URTEIL_PF = 40, 1.2
FRISCH = pd.Timedelta(minutes=20)
MIN_BARS = 1200
CHUNKS = 2                            # 1.000 Kerzen plus 2 x 10 Tage, etwa 30 Tage
VIERTEL = pd.Timedelta(minutes=15)
DAUER = {"1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4)}
VORAB = ROOT / "suche" / "VORAB_gold_short.yaml"
KEY = "VORAB_gold_short sha256 "
JDIR = ROOT / "journal" / "gold-short"
COCKPIT = ROOT / "journal" / "gold-short.json"
GOLD_BOT_DATEIEN = ("gold-trades.jsonl", "gold-state.json")   # gehören dem Gold-Bot (Schalter -8 R), nie schreiben


# --------------------------------------------------------------------------------------------------------------------
# Die neue Führung (wie portfolio-manager suche/runde12h.py fuehre_h mit Fuehrung(neu=True, halten=True))

_ORIG = ts.fuehre
_AKT: dict = {"seite": None, "log": None}


def _kurse(b: ts.Basis, d: int, j0: int, jf: int):
    """Kauf am Bid, Verkauf am Ask (wie tiktok_schatten.fuehre)."""
    if d > 0:
        return b.l[j0:jf], b.h[j0:jf], b.o[j0:jf]
    return (b.l + b.sp)[j0:jf], (b.h + b.sp)[j0:jf], (b.o + b.sp)[j0:jf]


def fehl_index(b: ts.Basis, d: int, j0: int, jf: int, einstieg: float, a: float) -> int:
    """Kerze, in der der Trade zum Fehltrade wird (0,5 R gegen ihn), sonst -1. Erreicht er sein erstes Ziel (0,75 R)
    in einer früheren Kerze, wird er nie zum Fehltrade (wie runde12f.fehl_index)."""
    jf = min(jf, len(b))
    if jf <= j0 or not a > 0:
        return -1
    lo, hi, _ = _kurse(b, d, j0, jf)
    fehl = (lo <= einstieg - FEHL_F * a) if d > 0 else (hi >= einstieg + FEHL_F * a)
    ziel = einstieg + d * ZIEL_FAKTOR * a
    z = (hi >= ziel) if d > 0 else (lo <= ziel)
    kf, kz = ts._erster(fehl, 0), ts._erster(z, 0)
    if kf < 0 or (0 <= kz < kf):
        return -1
    return j0 + kf


def halten(b: ts.Basis, d: int, einstieg: float, stop: float, teile: list[dict], offen: bool,
           grund_ende: str) -> tuple[list[dict], bool]:
    """Wäre der Rest zum normalen Ausstieg im Minus, bleibt er offen, bis der Kurs wieder am Einstieg ist (Grund
    "halten") oder der Stop kommt (nach dem ersten Ziel der Einstand). Stop zuerst, wenn beides in derselben Kerze
    liegt (wie runde12h.halten)."""
    if offen or not teile:
        return teile, offen
    letzt = max(teile, key=lambda t: t["j"])
    if letzt["grund"] != grund_ende or d * (letzt["px"] - einstieg) >= 0:
        return teile, offen
    n, j = len(b), letzt["j"]
    tp = any(str(t["grund"]).startswith("tp") for t in teile)
    st = einstieg if tp else stop
    lo, hi, op = _kurse(b, d, j, n)
    s = (lo <= st) if d > 0 else (hi >= st)
    z = (hi >= einstieg) if d > 0 else (lo <= einstieg)
    ks, kn = ts._erster(s, 0), ts._erster(z, 0)
    rest = [t for t in teile if t is not letzt]
    if ks >= 0 and (kn < 0 or ks <= kn):
        px = min(op[ks], st) if d > 0 else max(op[ks], st)
        return rest + [{"w": letzt["w"], "px": float(px), "j": j + ks, "grund": "einstand" if tp else "stop"}], False
    if kn >= 0:
        px = max(op[kn], einstieg) if d > 0 else min(op[kn], einstieg)
        return rest + [{"w": letzt["w"], "px": float(px), "j": j + kn, "grund": "halten"}], False
    return rest, True


def fuehre_neu(b: ts.Basis, d: int, j0: int, jf: int, einstieg: float, stop: float, ziele: tuple = ts.ZIELE,
               gewichte: tuple = ts.GEWICHTE, grund_ende: str = "gegensignal") -> tuple[list[dict], bool]:
    """tiktok_schatten.fuehre mit Zielen mal 0,75, Prüfer (0,5 R) und Halten. Merkt sich je Trade den normalen
    Ausstieg jf der Strategie (für den Live-Lauf: ist er fällig?)."""
    n = len(b)
    jf = min(jf, n)
    ziele = tuple(z * ZIEL_FAKTOR for z in ziele)
    a = abs(einstieg - stop)
    kf = fehl_index(b, d, j0, jf, einstieg, a)
    if kf < 0:
        teile, offen = _ORIG(b, d, j0, jf, einstieg, stop, ziele, gewichte, grund_ende)
    else:
        lo, hi, op = _kurse(b, d, j0, jf)
        s = (lo <= stop) if d > 0 else (hi >= stop)
        z = (hi >= einstieg) if d > 0 else (lo <= einstieg)
        ks, kn = ts._erster(s, kf - j0), ts._erster(z, kf - j0 + 1)
        if ks >= 0 and (kn < 0 or ks <= kn):
            px = min(op[ks], stop) if d > 0 else max(op[ks], stop)
            teile, offen = [{"w": 1.0, "px": float(px), "j": j0 + ks, "grund": "stop"}], False
        elif kn >= 0:
            px = max(op[kn], einstieg) if d > 0 else min(op[kn], einstieg)
            teile, offen = [{"w": 1.0, "px": float(px), "j": j0 + kn, "grund": "pruefer"}], False
        elif jf < n:
            px = b.o[jf] if d > 0 else b.o[jf] + b.sp[jf]
            teile, offen = [{"w": 1.0, "px": float(px), "j": jf, "grund": grund_ende}], False
        else:
            teile, offen = [], True
    teile, offen = halten(b, d, einstieg, stop, teile, offen, grund_ende)
    if _AKT["log"] is not None:
        _AKT["log"][(_AKT["seite"], int(j0), int(d))] = {"jf": int(jf), "fehl": int(kf), "offen": bool(offen),
                                                          "jende": n if offen else max(t["j"] for t in teile)}
    return teile, offen


@contextlib.contextmanager
def neue_fuehrung(log: dict, seite: str):
    alt = ts.fuehre
    ts.fuehre = fuehre_neu
    _AKT.update(seite=seite, log=log)
    try:
        yield
    finally:
        ts.fuehre = alt
        _AKT.update(seite=None, log=None)


# --------------------------------------------------------------------------------------------------------------------
# Die drei Seiten auf den Kerzen

def _bis(b: ts.Basis, n: int) -> ts.Basis:
    return ts.Basis(b.t[:n], b.o[:n], b.h[:n], b.l[:n], b.c[:n], b.sp[:n], b.tag[:n], b.ny[:n])


def fertig(e: ts.Ebene, b: ts.Basis, name: str) -> ts.Ebene:
    """Ohne die letzte 1-Std.- bzw. 4-Std.-Kerze, wenn sie noch läuft. Fertig ist sie, wenn ihr Zeitraum bis zum Ende
    der letzten fertigen 15-Min.-Kerze vorbei ist. Um 17:00 New York (Tagesschluss, danach eine Stunde zu) zählt auch
    die Stunde bis 18:00 (die 4-Std.-Kerze ab 14:00 hat nur drei Stunden)."""
    if len(e.c) == 0 or len(b) == 0:
        return e
    i0 = int(e.i1[-2]) + 1 if len(e.i1) > 1 else 0
    t0, ny0 = pd.Timestamp(b.t[i0]), pd.Timestamp(b.ny[i0])
    if name == "1h":
        start = t0.floor("1h")
    else:
        start = t0 - (ny0 - ((ny0 + pd.Timedelta(hours=6)).floor("4h") - pd.Timedelta(hours=6)))
    ende = pd.Timestamp(b.t[-1]) + VIERTEL
    ende_ny = pd.Timestamp(b.ny[-1]) + VIERTEL
    grenze = ende + pd.Timedelta(hours=1) if (ende_ny.hour, ende_ny.minute) == (17, 0) else ende
    if start + DAUER[name] <= grenze:
        return e
    return ts.Ebene(e.name, e.ende[:-1], e.h[:-1], e.l[:-1], e.c[:-1], e.i1[:-1], e.atr[:-1], e.o[:-1])


def simuliere(b: ts.Basis, n: int | None = None) -> tuple[dict[str, list[dict]], dict]:
    """Die drei Seiten mit der neuen Führung. Die Ebenen kommen nur aus den ersten n Kerzen (die fertigen), gehandelt
    wird auf allen Kerzen von b (live hängt dahinter die Kerze "jetzt"). Jeder Trade bekommt _j0 (Einstiegskerze), _jf
    (normaler Ausstieg der Strategie), _fehl (Fehltrade-Kerze oder -1) und _jende (letzte Kerze, len(b) wenn offen)."""
    n = len(b) if n is None else n
    bz = _bis(b, n)
    m15 = ts.ebene(bz, "15m")
    h1 = fertig(ts.ebene(bz, "1h"), bz, "1h")
    h4 = fertig(ts.ebene(bz, "4h"), bz, "4h")
    box4 = ts.signalbox(b, h4, ts.strukturbrueche(h4))           # Filter-Boxen mit der alten Führung
    box1 = ts.signalbox(b, h1, ts.strukturbrueche(h1))
    log: dict = {}
    out: dict[str, list[dict]] = {}
    with neue_fuehrung(log, "gross_klein_3"):
        out["gross_klein_3"] = ts.gross_klein(b, m15, ts.strukturbrueche(m15), box4, box1)
    with neue_fuehrung(log, "gross_box_kerze"):
        out["gross_box_kerze"] = ts.gross_box(b, m15, h1, h4, kerze=True)
    with neue_fuehrung(log, "gross_box"):
        out["gross_box"] = ts.gross_box(b, m15, h1, h4, kerze=False)
    for seite, trs in out.items():
        for t in trs:
            j0 = int(np.searchsorted(b.t, np.datetime64(pd.Timestamp(t["einstieg_zeit"]))))
            info = log.get((seite, j0, int(t["richtung"]))) or {}
            t["_j0"], t["_jf"] = j0, info.get("jf")
            t["_fehl"], t["_jende"] = info.get("fehl", -1), info.get("jende", len(b))
    return out, log


def kombi(trades: dict[str, list[dict]]) -> tuple[list[tuple[str, dict]], list[tuple[str, dict]], int]:
    """gross_short wie runde12h.kombi: alle Shorts der drei Seiten nach Einstieg, gleiche Einstiege einmal (erste Seite),
    kein neuer Short, solange ein offener Short schon ein Fehltrade ist. Rückgabe: genommen, gesperrt, doppelt."""
    kand = sorted(((t["_j0"], rang, seite, t) for rang, seite in enumerate(SEITEN) for t in trades.get(seite, [])
                   if t["richtung"] < 0), key=lambda x: (x[0], x[1]))
    genommen, weg, offen, gesehen, doppelt = [], [], [], set(), 0
    for j0, _, seite, t in kand:
        if j0 in gesehen:
            doppelt += 1
            continue
        gesehen.add(j0)
        offen = [o for o in offen if o["_jende"] > j0]
        if any(0 <= o["_fehl"] < j0 for o in offen):
            weg.append((seite, t))
            continue
        genommen.append((seite, t))
        offen.append(t)
    return genommen, weg, doppelt


# --------------------------------------------------------------------------------------------------------------------
# Hilfen für den Live-Lauf

def vorab_ok() -> bool:
    """Ist suche/VORAB_gold_short.yaml mit seiner Prüfsumme im Protokoll festgelegt?"""
    from suche.runde1 import journal_lines, last_value, sha256_text
    if not VORAB.exists():
        return False
    return last_value(journal_lines(), KEY) == sha256_text(VORAB.read_text(encoding="utf-8"))


def frisch(letzte_ende: pd.Timestamp, now: pd.Timestamp) -> bool:
    """Ist die letzte fertige Kerze die gerade abgeschlossene? Nach dem Tagesschluss (17:00 New York) zählt die erste
    Viertelstunde nach der Öffnung um 18:00 (auch Sonntag nach dem Wochenende)."""
    if now - letzte_ende <= FRISCH:
        return True
    ende_ny = letzte_ende.tz_localize("UTC").tz_convert(NY)
    jetzt_ny = now.tz_localize("UTC").tz_convert(NY)
    if (ende_ny.hour, ende_ny.minute) != (17, 0):
        return False
    auf = jetzt_ny.normalize() + pd.Timedelta(hours=18)
    return auf <= jetzt_ny <= auf + FRISCH and jetzt_ny.date() >= ende_ny.date()


def groessen(dist: float, q, gewichte: tuple) -> tuple[list[float] | None, str]:
    """Größe je Teil: zusammen RISIKO_EUR bis zum Stop, höchstens MAX_OZ_TRADE Unzen, je Teil mindestens die kleinste
    Größe. Rückgabe (Größen, Grund). Größen None, wenn das Runden das Risiko mehr als verdoppeln würde."""
    if not q.eur_rate or not dist > 0:
        return None, "kein Kurs EUR/USD oder kein Stopabstand"
    lot = q.lot or 1.0
    gesamt = min(RISIKO_EUR * q.eur_rate / (dist * lot), MAX_OZ_TRADE / lot)
    step = q.size_step or q.min_size
    out = []
    for w in gewichte:
        s = math.floor(round(gesamt * w / step, 9)) * step
        out.append(round(max(s, q.min_size), 8))
    risiko = sum(out) * lot * dist / q.eur_rate
    if risiko > MAX_RISIKO_FAKTOR * RISIKO_EUR:
        return None, f"kleinste Größe zu grob ({risiko:.2f} € Risiko statt {RISIKO_EUR:.0f} €)"
    return out, ""


def ziel_abstaende(seite: str, dist: float) -> tuple[tuple, list[float | None]]:
    """Gewichte und Zielabstände je Teil (None = kein Ziel, läuft bis zur neuen Box)."""
    if seite == "gross_klein_3":
        return ts.GEWICHTE, [z * ZIEL_FAKTOR * dist for z in ts.ZIELE]
    return ts.LAUFEN[1], [ts.LAUFEN[0][0] * ZIEL_FAKTOR * dist, None]


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


def _jetzt(now: datetime) -> pd.Timestamp:
    t = pd.Timestamp(now)
    return t.tz_convert("UTC").tz_localize(None) if t.tzinfo else t


def _num(x) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


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
        self.andere_gold: list[str] = []     # andere Gold-Bots, denen journal/konten.json Konto 5 gibt

    def ev(self, event: str, **kw) -> None:
        self.log.append({"time": self.stamp, "event": event, **kw})

    # ---- Broker ----

    def aendere(self, teil: dict, stop: float | None, ziel: float | None, warum: str) -> bool:
        body = {"stopLevel": round(stop, 2) if stop is not None else None,
                "profitLevel": round(ziel, 2) if ziel is not None else None}
        body = {k: v for k, v in body.items() if v is not None}
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
        teil["stop"] = body.get("stopLevel", teil.get("stop"))
        if "profitLevel" in body:
            teil["ziel"] = body["profitLevel"]
        self.ev("geändert", dealId=teil["dealId"], **body, warum=warum)
        return True

    def schliesse(self, tr: dict, teil: dict, warum: str) -> None:
        if not self.send:
            self.ev("würde schließen", dealId=teil["dealId"], warum=warum, kurs=self.q.offer)
            return
        try:
            conf = self.client.close_position(teil["dealId"])
        except Exception as err:            # noqa: BLE001 - nächster Lauf versucht es wieder, Stop liegt beim Broker
            self.ev("schließen fehlgeschlagen", dealId=teil["dealId"], warum=warum, fehler=str(err)[:200])
            return
        level = _num((conf or {}).get("level")) or self.q.offer
        self._teil_zu(tr, teil, level, warum)
        self.ev("geschlossen", dealId=teil["dealId"], kurs=level, warum=warum)

    def _teil_zu(self, tr: dict, teil: dict, level: float, grund: str) -> None:
        teil.update(offen=False, exit=round(float(level), 2), grund=grund, closed_utc=self.stamp)

    # ---- Abgleich mit dem Konto ----

    def abgleich(self, gold: list[dict]) -> None:
        """Teile, die beim Broker nicht mehr offen sind (Stop oder Ziel), schließen. Ein Teil mit Ziel, der am Ziel
        oder besser schloss, zählt als Ziel erreicht (dann Einstand für den Rest)."""
        from suche.demo_bots import broker_exit
        pos = {str(p["position"].get("dealId")): p["position"] for p in gold}
        for tr in self.st["offen"]:
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
                ziel, orig = teil.get("ziel"), teil.get("ziel_orig")
                tol = 0.1 * tr["dist"]
                if orig is not None and ziel is not None and abs(ziel - orig) < 0.01 and (quelle == "TP" or
                                                                                         level <= orig + tol):
                    grund = "ziel"
                    if teil.get("ziel_nr") == 1:
                        tr["tp1"] = True
                elif ziel is not None and (quelle == "TP" or level <= ziel + tol):
                    grund = "pruefer" if tr.get("fehl") else "halten"
                elif quelle in ("SL", "geschätzt (Stop)"):
                    grund = "einstand" if tr.get("einstand") else "stop"
                else:
                    grund = f"beim Broker ({quelle or 'unbekannt'})"
                self._teil_zu(tr, teil, level, grund)
                self.ev("Teil zu beim Broker", trade=tr["id"], dealId=teil["dealId"], kurs=level, grund=grund)

    def buchen(self) -> None:
        rest = []
        for tr in self.st["offen"]:
            if any(t["offen"] for t in tr["teile"]):
                rest.append(tr)
                continue
            size = sum(t["size"] for t in tr["teile"])
            r = sum(t["size"] * (t["entry"] - t["exit"]) for t in tr["teile"]) / (size * tr["dist"])
            pnl_usd = sum(t["size"] * (self.q.lot or 1.0) * (t["entry"] - t["exit"]) for t in tr["teile"])
            rate = self.q.eur_rate
            rec = {**{k: tr[k] for k in ("id", "seite", "signal", "einstieg_zeit", "opened_utc", "dist")},
                   "richtung": -1, "size": round(size, 4), "entry": round(sum(t["size"] * t["entry"] for t in
                                                                          tr["teile"]) / size, 2),
                   "exit": round(sum(t["size"] * t["exit"] for t in tr["teile"]) / size, 2),
                   "closed_utc": self.stamp, "r": round(r, 3), "pnl_usd": round(pnl_usd, 2),
                   "pnl_eur": round(pnl_usd / rate, 2) if rate else None,
                   "teile": [{k: t.get(k) for k in ("dealId", "size", "entry", "exit", "grund", "ziel_nr")}
                             for t in tr["teile"]],
                   "fehltrade": tr.get("fehl"), "gehalten": tr.get("halten"), "erstes_ziel": tr.get("tp1")}
            self.fertige.append(rec)
            self.st["summe_r"] = round(float(self.st["summe_r"]) + rec["r"], 3)
            self.st["trades"] = int(self.st["trades"]) + 1
            self.ev("Trade fertig", trade=tr["id"], seite=tr["seite"], r=rec["r"], pnl_eur=rec["pnl_eur"])
        self.st["offen"] = rest
        if self.st.get("pausiert") is None and self.st["summe_r"] <= PAUSE_R:
            self.st["pausiert"] = {"seit": self.stamp, "grund": f"Summe R seit Start {self.st['summe_r']} (Grenze "
                                                                f"{PAUSE_R}), zurück nur mit Kirons Entscheidung"}
            self.ev("Pause", grund=self.st["pausiert"]["grund"])

    # ---- Führung der offenen Trades ----

    def fuehren(self, b: ts.Basis, n: int, trades: dict, log_sim: dict) -> None:
        q = self.q
        for tr in self.st["offen"]:
            offene = [t for t in tr["teile"] if t["offen"]]
            if not offene:
                continue
            entry = sum(t["size"] * t["entry"] for t in offene) / sum(t["size"] for t in offene)
            # 1. Nach dem ersten Ziel: Stop auf Einstand
            if tr.get("tp1") and not tr.get("einstand"):
                tr["einstand"] = self.stamp
                for t in offene:
                    if q.offer >= t["entry"] - q.min_dist or not self.aendere(t, t["entry"], t.get("ziel"), "einstand"):
                        self.schliesse(tr, t, "einstand")
                offene = [t for t in tr["teile"] if t["offen"]]
            # 2. Prüfer: 0,5 R gegen den Trade vor dem ersten Ziel
            j0 = int(np.searchsorted(b.t, np.datetime64(pd.Timestamp(tr["einstieg_zeit"]))))
            if offene and not tr.get("tp1") and not tr.get("fehl"):
                hoch = max([float((b.h + b.sp)[j0:n].max()) if n > j0 else -np.inf, q.offer])
                if hoch >= entry + FEHL_F * tr["dist"]:
                    tr["fehl"] = self.stamp
                    self.ev("Fehltrade", trade=tr["id"], hoch=round(hoch, 2), grenze=round(entry + FEHL_F * tr["dist"], 2))
                    self._bis_einstieg(tr, offene, "pruefer")
                    offene = [t for t in tr["teile"] if t["offen"]]
            # 3. Normaler Ausstieg der Strategie fällig?
            if not offene or tr.get("zwang"):
                continue
            sim = next((t for t in trades.get(tr["seite"], []) if t["_j0"] == j0 and t["richtung"] < 0), None)
            info = log_sim.get((tr["seite"], j0, -1)) if sim else None
            if sim is not None and info is not None and info["jf"] > n:
                continue
            tr["zwang"] = self.stamp
            grund = "nicht mehr im Modell" if sim is None or info is None else "normaler Ausstieg der Strategie"
            if entry - q.offer > 0:
                self.ev("Ausstieg im Plus", trade=tr["id"], grund=grund)
                for t in offene:
                    self.schliesse(tr, t, "ausstieg")
            elif tr.get("einstand"):
                for t in offene:
                    self.schliesse(tr, t, "ausstieg")
            else:
                tr["halten"] = self.stamp
                self.ev("Halten bis Einstieg", trade=tr["id"], grund=grund, kurs=q.offer)
                if not tr.get("fehl"):
                    self._bis_einstieg(tr, offene, "halten")

    def _bis_einstieg(self, tr: dict, offene: list[dict], warum: str) -> None:
        """Ziel jedes offenen Teils auf seinen Einstieg (ein Short schließt, wenn der Kurs wieder dort ist). Steht der
        Kurs schon dort oder zu nah dran, gleich zum Markt schließen."""
        for t in offene:
            if self.q.offer <= t["entry"] + self.q.min_dist or not self.aendere(t, t.get("stop"), t["entry"], warum):
                self.schliesse(tr, t, warum)

    # ---- Neuer Short ----

    def einstieg(self, b: ts.Basis, n: int, trades: dict, gold: list[dict], fremde: list[dict],
                 available_eur: float | None) -> None:
        from suche.demo_bots import open_market
        q = self.q
        t_ph = pd.Timestamp(b.t[n])
        kand = [(seite, t) for seite in SEITEN for t in trades.get(seite, []) if t["richtung"] < 0 and t["_j0"] == n]
        if not kand:
            return
        if self.st.get("letzte_kerze") == str(t_ph):
            return
        seite, sig = kand[0]
        gruende = []
        if not q.tradeable:
            self.ev("Signal, Markt zu", seite=seite, kerze=str(t_ph))
            return                                        # nächster Lauf versucht es wieder
        self.st["letzte_kerze"] = str(t_ph)
        if not frisch(t_ph, self.now):
            gruende.append("Signal zu alt")
        if self.st.get("pausiert"):
            gruende.append("Pause ab -10 R")
        if not vorab_ok():
            gruende.append("VORAB_gold_short.yaml nicht festgelegt")
        if any(tr.get("fehl") for tr in self.st["offen"]):
            gruende.append("Sperre: ein offener Short ist schon ein Fehltrade")
        if len(self.st["offen"]) >= MAX_OFFEN:
            gruende.append(f"schon {MAX_OFFEN} Trades offen")
        if fremde:
            gruende.append("fremde Gold-Position auf dem Konto")
        if self.andere_gold:
            gruende.append(f"Konto 5 ist laut journal/konten.json auch für {', '.join(self.andere_gold)} vergeben")
        dist = float(sig["r_usd"])
        gewichte, abst = ziel_abstaende(seite, dist)
        sizes, warum = groessen(dist, q, gewichte)
        if sizes is None:
            gruende.append(warum)
        else:
            offen_oz = sum(t["size"] for tr in self.st["offen"] for t in tr["teile"] if t["offen"]) * (q.lot or 1)
            if offen_oz + sum(sizes) * (q.lot or 1) > MAX_OZ_GESAMT + 1e-9:
                gruende.append(f"mehr als {MAX_OZ_GESAMT:.0f} Unzen zusammen")
            marge = sum(sizes) * (q.lot or 1) * q.bid * q.margin_pct / 100 / (q.eur_rate or 1)
            if available_eur is not None and marge > 0.8 * available_eur:
                gruende.append(f"zu wenig freie Marge ({available_eur:.0f} €)")
        if q.min_dist and dist < q.min_dist:
            gruende.append("Stop näher als der Mindestabstand des Brokers")
        info = {"seite": seite, "kerze": str(t_ph), "signal": sig["signal"], "dist": round(dist, 2),
                "andere": [s for s, _ in kand[1:]]}
        if gruende:
            self.ev("Short ausgelassen", **info, gruende=gruende)
            return
        tr = {"id": f"{t_ph:%Y-%m-%dT%H:%M}", "seite": seite, "signal": sig["signal"], "einstieg_zeit": str(t_ph),
              "opened_utc": self.stamp, "dist": round(dist, 2), "sim_einstieg": sig["einstieg"], "teile": [],
              "tp1": False, "einstand": None, "fehl": None, "halten": None, "zwang": None}
        if not self.send:
            self.ev("würde verkaufen", **info, groessen=sizes, ziele=[None if a is None else round(a, 2) for a in abst])
            return
        for nr, (size, abstand) in enumerate(zip(sizes, abst), start=1):
            vorher = {str(p["position"].get("dealId")) for p in gold}
            order = {"size": size, "stop_dist": round(dist, 2),
                     "tp_dist": None if abstand is None else round(max(abstand, q.min_dist or 0), 2)}
            try:
                conf = open_market(self.client, EPIC, -1, order)
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
            level = (_num(pos.get("level")) if pos else _num((conf or {}).get("level"))) or q.bid
            stop = (_num(pos.get("stopLevel")) if pos else None) or level + dist
            ziel = (_num(pos.get("profitLevel")) if pos else None)
            if ziel is None and order["tp_dist"] is not None:
                ziel = level - order["tp_dist"]
            tr["teile"].append({"dealId": deal, "size": size, "entry": round(level, 2), "ziel_nr": nr,
                                "stop": round(stop, 2), "ziel": None if ziel is None else round(ziel, 2),
                                "ziel_orig": None if ziel is None else round(ziel, 2),
                                "offen": True, "exit": None, "grund": None, "closed_utc": None})
        if tr["teile"]:
            self.st["offen"].append(tr)
            self.ev("Short eröffnet", **info, teile=[{k: t[k] for k in ("dealId", "size", "entry", "stop", "ziel")}
                                                     for t in tr["teile"]])


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
        return lauf.st, lauf.log, [], {"status": "Konto 5 nicht gefunden, nichts gehandelt"}
    available = _num((konto.get("balance") or {}).get("available"))
    # nur lesen: bekommt laut journal/konten.json ein anderer Gold-Bot Konto 5, öffnet dieser Bot nichts Neues
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
            trades, log_sim = simuliere(b, n)
            lauf.fuehren(b, n, trades, log_sim)
            lauf.buchen()
            lauf.einstieg(b, n, trades, gold, fremde, available)
            blick.update(blick_auf(b, n, trades))
        lauf.st["stand"] = lauf.stamp
        return lauf.st, lauf.log, lauf.fertige, blick
    finally:
        with contextlib.suppress(Exception):
            if vorher and vorher != KONTO:
                client.switch_account(vorher)


def blick_auf(b: ts.Basis, n: int, trades: dict) -> dict:
    """Was die drei Seiten gerade sehen (für das Cockpit): offene Shorts im Modell und die Richtung der großen Box."""
    offen = [{"seite": s, "einstieg_zeit": t.get("einstieg_zeit"), "einstieg": t.get("einstieg"), "stop": t.get("stop")}
             for s in SEITEN for t in trades.get(s, []) if t["richtung"] < 0 and t["_jende"] > n]
    return {"letzte_kerze": str(pd.Timestamp(b.t[n - 1])), "kurs": round(float(b.o[n]), 2),
            "modell_offen": offen[:10]}


# --------------------------------------------------------------------------------------------------------------------
# Journal und Cockpit

def cockpit(st: dict, alle_trades: list[dict], blick: dict) -> dict:
    return {"bot": BOT_ID, "name": "Gold-Short-Bot (große Strategie nur Shorts)", "konto": "…" + KONTO[-4:],
            "stand": st.get("stand"), "start": st.get("start"), "pausiert": st.get("pausiert"),
            "regel": ("Shorts aus gross_klein_3, gross_box_kerze und gross_box (Runde 12h), Ziele mal 0,75, Prüfer "
                      "0,5 R, Halten bis Einstieg, Sperre bei Fehltrade. 5 € Risiko je Trade, höchstens 4 offen."),
            "backtest": "11/2024 bis 10/2026 465 Trades, PF_R 0,94, -9,3 R, Kontrolle 2022 bis 2024 PF_R 0,66 "
                        "(durchgefallen, läuft auf Kirons Wunsch)",
            "vorab": "suche/VORAB_gold_short.yaml",
            "offen": [{k: tr.get(k) for k in ("id", "seite", "einstieg_zeit", "dist", "tp1", "fehl", "halten")} |
                      {"teile": [{k: t.get(k) for k in ("size", "entry", "stop", "ziel", "offen")} for t in tr["teile"]]}
                      for tr in st.get("offen", [])],
            "zusammenfassung": bewertung(alle_trades), "letzte_trades": alle_trades[-10:], "blick": blick}


def _lies_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        with contextlib.suppress(ValueError):
            out.append(json.loads(line))
    return out


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
    alle = _lies_jsonl(jdir / "trades.jsonl")
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
        print("Keine Capital.com-Zugangsdaten, Gold-Short-Bot übersprungen")
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
