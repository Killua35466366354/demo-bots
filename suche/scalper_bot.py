"""Scalper mit Open-Filter auf Account 1: die 3 Scalping-Strategien mit dem höchsten Gewinnfaktor (nur Capital.com-DEMO).

Kirons Wort vom 10.11.2026 12:16 UTC ("nutze die neuen filter aus dem tiktok viedo ... und tue die 3 profitablsten nach
gewinnfactor scalping strategien live auf demo accounts stellen"). Regeln und Auswahl: suche/VORAB_scalping_opens.yaml,
Ergebnis suche/ergebnis_scalping_opens.md. Die Regeln je Familie sind dieselben wie in suche/scalping2.py (Runde 2b),
der Filter derselbe wie in suche/opens.py (Video TikTok montyfinance). Läuft im 5-Min.-Lauf (pine5m.yml).

- scalp-us100: Nasdaq 100, erste 15-Min.-Kerze ab 09:30 New York, Richtung der Kerze, Stop am anderen Ende, Ziel 10 R,
  raus 16:00 New York; nur wenn der Kurs auf derselben Seite von Jahres-, Quartals-, Monats- und Wochen-Open liegt.
- scalp-de40: DAX, dasselbe ab 09:00 Berlin, raus 17:30 Berlin.
- scalp-j225: Nikkei 225, 30 Min. vor Schluss (15:00 Tokio) gegen die Bewegung seit dem Vortagsschluss, ohne Stop, raus
  15:30 Tokio; nur wenn der Kurs auf derselben Seite des Wochen-Opens liegt.

Aufruf: python -m suche.scalper_bot [--dry-run]
"""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import pathlib
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from suche import scalping as sc
from suche import scalping2 as s2

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_scalping_opens.yaml"
KEY = "VORAB_scalping_opens sha256 "
JOURNAL = ROOT / "journal"
KONTO = "332263725196465310"            # Account 1 (frei seit Brent, 10.11.2026)
KONTO_NAME = "Account 1"
RISIKO_EUR = 5.0                        # 1 R = 5 € (wie die Pine-Bots)
ZIEL_R = 10.0
FENSTER = pd.Timedelta(minutes=10)      # später als 10 Min. nach der Einstiegszeit: an dem Tag kein Trade
NY = sc.NY
OPEN_SPALTEN = ("jahr", "quartal", "monat", "woche")


@dataclass(frozen=True)
class Scalper:
    bot_id: str
    epic: str
    sym: str                # Markt im Test (HistData-Name)
    familie: str            # eroeffnung | halbe_stunde
    variante: str           # folgen_10r | gegen
    kerzen: int             # 15 oder 5 Min.
    filter: str             # alle | woche
    name: str
    test: str

    def sitzung(self, tag: pd.Timestamp) -> tuple[str, str, str]:
        tz, start, schluss = s2.sitzung(self.sym)
        return tz, start, s2.schluss_von(schluss, tag)

    def opens_noetig(self) -> tuple[str, ...]:
        return OPEN_SPALTEN if self.filter == "alle" else (self.filter,)

    def regel(self) -> str:
        tz, start, schluss = self.sitzung(pd.Timestamp("2026-11-10"))
        ort = {sc.NY: "New York", sc.BERLIN: "Berlin", sc.TOKIO: "Tokio"}.get(tz, tz)
        if self.familie == "eroeffnung":
            f = ("Jahres-, Quartals-, Monats- und Wochen-Open" if self.filter == "alle" else f"{self.filter}-Open")
            return (f"Erste 15-Min.-Kerze ab {start} Uhr {ort}: grün Long, rot Short, Einstieg danach, Stop am anderen "
                    f"Ende der Kerze, Ziel 10 R, sonst raus um {schluss} Uhr {ort}. Nur wenn der Kurs auf der Seite von "
                    f"{f} liegt (Long darüber, Short darunter). 1 R = 5 €.")
        return (f"30 Min. vor Schluss ({s2.minus(schluss, 30)} Uhr {ort}) gegen die Bewegung seit dem Vortagsschluss, "
                f"ohne Stop, raus um {schluss} Uhr {ort}. Nur wenn der Kurs auf der Seite des Wochen-Opens liegt (Long "
                f"darüber, Short darunter). Kleinste Größe.")


BOTS = (
    Scalper("scalp-us100", "US100", "NSXUSD", "eroeffnung", "folgen_10r", 15, "alle", "Nasdaq Eröffnungskerze (15 Min.)",
            "PF 2,06, 123 Trades in 2 Jahren (1,2 je Woche), Kontrolle 2022-24 1,11, schlägt 99 % der Zufallsläufe"),
    Scalper("scalp-de40", "DE40", "GRXEUR", "eroeffnung", "folgen_10r", 15, "alle", "DAX Eröffnungskerze (15 Min.)",
            "PF 1,63, 123 Trades in 2 Jahren (1,2 je Woche), Kontrolle 2022-24 1,13, schlägt 90,5 % der Zufallsläufe"),
    Scalper("scalp-j225", "J225", "JPXJPY", "halbe_stunde", "gegen", 5, "woche", "Nikkei letzte halbe Stunde (5 Min.)",
            "PF 1,53, 174 Trades in 2 Jahren (1,7 je Woche), Kontrolle 2022-24 nur 0,69, schlägt 100 % der Zufallsläufe"),
)


def sha256_vorab() -> str:
    from suche.runde1 import sha256_text
    return sha256_text(VORAB.read_text(encoding="utf-8"))


def vorab_ok() -> bool:
    from suche.runde1 import journal_lines, last_value, sha256_text
    return VORAB.exists() and last_value(journal_lines(), KEY) == sha256_text(VORAB.read_text(encoding="utf-8"))


# ---------- Opens (wie suche/opens.py: Handelstag endet 17:00 New York) ----------

def handelstag(ts: pd.Timestamp) -> pd.Timestamp:
    """Handelstag einer Kerze (Beginn in UTC, naiv): Datum in New York plus 7 Stunden."""
    ny = pd.Timestamp(ts).tz_localize("UTC").tz_convert(NY).tz_localize(None)
    return (ny + pd.Timedelta(hours=7)).normalize()


def periode(tag: pd.Timestamp, art: str) -> tuple[str, pd.Timestamp]:
    """(Schlüssel, erster Kalendertag) der Periode, zu der der Handelstag gehört."""
    tag = pd.Timestamp(tag).normalize()
    if art == "jahr":
        return f"{tag.year}", pd.Timestamp(tag.year, 1, 1)
    if art == "quartal":
        q = (tag.month - 1) // 3
        return f"{tag.year}Q{q + 1}", pd.Timestamp(tag.year, 3 * q + 1, 1)
    if art == "monat":
        return f"{tag:%Y-%m}", pd.Timestamp(tag.year, tag.month, 1)
    iso = tag.isocalendar()
    return f"{iso.year}W{iso.week:02d}", tag - pd.Timedelta(days=tag.weekday())


def gleiche_periode(a: pd.Timestamp, b: pd.Timestamp, art: str) -> bool:
    return periode(a, art)[0] == periode(b, art)[0]


def open_aus_kerzen(kerzen: pd.DataFrame, tag: pd.Timestamp, art: str) -> float | None:
    """Eröffnung der ersten Kerze (Mo-Fr-Handelstag) der Periode von `tag`, aus Kerzen mit Spalte open (Bid)."""
    _, erster = periode(tag, art)
    for t, row in kerzen.sort_index().iterrows():
        ht = handelstag(t)
        if ht.weekday() < 5 and ht >= erster and gleiche_periode(ht, tag, art):
            return float(row["open"])
    return None


def hole_open(client, epic: str, tag: pd.Timestamp, art: str) -> float | None:
    """Open der Periode aus Capital.com-Stundenkerzen (Bid) rund um den Beginn der Periode."""
    from gold.bot.rules import bars_from_prices
    _, erster = periode(tag, art)
    von = sc.ortszeit(erster - pd.Timedelta(days=1), "16:00", NY)
    bis = von + pd.Timedelta(days=5)
    fmt = "%Y-%m-%dT%H:%M:%S"
    raw = client._get(f"/prices/{epic}", resolution="HOUR", max=200,
                      **{"from": von.strftime(fmt), "to": bis.strftime(fmt)}).get("prices", [])
    kerzen, _ = bars_from_prices(raw, bis.to_pydatetime() + pd.Timedelta(hours=1), "60min")
    return open_aus_kerzen(kerzen, tag, art)


# ---------- Entscheidung (ohne Netz, testbar) ----------

def zeiten(bot: Scalper, jetzt: pd.Timestamp) -> dict | None:
    """Einstieg und Ausstieg (UTC, naiv) des heutigen Ortstags, None am Wochenende."""
    tz = bot.sitzung(jetzt)[0]
    tag = pd.Timestamp(jetzt).tz_localize("UTC").tz_convert(tz).tz_localize(None).normalize()
    if tag.weekday() >= 5:
        return None
    _, start, schluss = bot.sitzung(tag)
    if bot.familie == "eroeffnung":
        erste = sc.ortszeit(tag, start, tz)
        ein = erste + pd.Timedelta(minutes=bot.kerzen)
    else:
        erste = None
        ein = sc.ortszeit(tag, s2.minus(schluss, 30), tz)
    return {"tag": tag, "erste": erste, "ein": ein, "aus": sc.ortszeit(tag, schluss, tz), "tz": tz}


def vortagsschluss(bot: Scalper, b5: pd.DataFrame, tag: pd.Timestamp) -> float | None:
    """Wie scalping2.halbe_stunde: Schluss der Kerze 5 Min. vor Sitzungsschluss am letzten Werktag davor (bis 5 zurück)."""
    tz = bot.sitzung(tag)[0]
    d = tag
    for _ in range(5):
        d = sc.voriger_werktag(d)
        t = sc.ortszeit(d, s2.minus(bot.sitzung(d)[2], 5), tz)
        if t in b5.index:
            return float(b5.loc[t, "close"])
    return None


def entscheide(bot: Scalper, z: dict, b5: pd.DataFrame, b_tf: pd.DataFrame, opens: dict, bid: float, ask: float,
               ein_open: float | None = None) -> dict:
    """Signal am Einstieg. b5: fertige 5-Min.-Kerzen (Bid), b_tf: fertige Kerzen im Chart des Bots, opens: {art: Kurs},
    bid/ask: Kurs jetzt, ein_open: Eröffnung der Kerze zur Einstiegszeit (halbe_stunde). Rückgabe {"d": 0|1|-1, ...}."""
    if bot.familie == "eroeffnung":
        if z["erste"] not in b_tf.index:
            return {"d": 0, "warum": "erste Kerze fehlt"}
        k = b_tf.loc[z["erste"]]
        if k["close"] == k["open"]:
            return {"d": 0, "warum": "erste Kerze ohne Richtung"}
        d = 1 if k["close"] > k["open"] else -1
        if bot.variante != "folgen_10r":
            raise ValueError(bot.variante)
        stop = float(k["low"] if d == 1 else k["high"])
        entry = ask if d == 1 else bid
        if (d == 1 and bid <= stop) or (d == -1 and ask >= stop):
            return {"d": 0, "warum": "Kurs schon jenseits des Stops"}
        dist = abs(entry - stop)
        sig = {"d": d, "entry": entry, "stop": stop, "ziel": entry + d * ZIEL_R * dist, "dist": dist}
    else:
        ref = vortagsschluss(bot, b5, z["tag"])
        if ref is None or ein_open is None:
            return {"d": 0, "warum": "Vortagsschluss oder Einstiegskurs fehlt"}
        d = int(math.copysign(1, ein_open - ref)) * (1 if bot.variante == "folgen" else -1) if ein_open != ref else 0
        if not d:
            return {"d": 0, "warum": "keine Bewegung seit dem Vortagsschluss"}
        sig = {"d": d, "entry": ask if d == 1 else bid, "stop": None, "ziel": None, "dist": None, "ref": ref}
    vor = z["ein"] - pd.Timedelta(minutes=5)
    fertig = b5[b5.index <= vor]
    if fertig.empty or fertig.index[-1] < vor - pd.Timedelta(minutes=30):
        return {"d": 0, "warum": "keine 5-Min.-Kerze vor dem Einstieg"}
    kurs = float(fertig["close"].iloc[-1])
    sig["kurs_filter"] = kurs
    for art in bot.opens_noetig():
        o = opens.get(art)
        if o is None:
            return {"d": 0, "warum": f"{art}-Open fehlt"}
        if not sig["d"] * (kurs - o) > 0:
            return {"d": 0, "warum": f"Filter: Kurs {kurs:g} nicht auf der {'Long' if d == 1 else 'Short'}-Seite des "
                                     f"{art}-Opens {o:g}", "kurs_filter": kurs}
    return sig


def groesse(bot: Scalper, dist: float | None, q) -> float:
    """5 € je R, abgerundet auf die Schrittweite, mindestens die kleinste Größe; ohne Stop die kleinste Größe."""
    if dist is None or not dist > 0 or not q.eur_rate:
        return q.min_size
    step = q.size_step or q.min_size
    roh = RISIKO_EUR * q.eur_rate / (dist * (q.lot or 1.0))
    return round(max(math.floor(round(roh / step, 9)) * step, q.min_size), 8)


# ---------- Ein Lauf ----------

class Lauf:
    def __init__(self, bot: Scalper, client, st: dict, now: pd.Timestamp, send: bool):
        self.bot, self.client, self.now, self.send = bot, client, now, send
        self.st = {"format": 1, "offen": None, "tag_erledigt": None, "opens": {}, "trades": 0, "summe_r": 0.0,
                   "summe_pct": 0.0, "summe_eur": 0.0, **(st or {})}
        self.log: list[dict] = []
        self.fertige: list[dict] = []
        self.stamp = now.strftime("%Y-%m-%dT%H:%M:%S")

    def ev(self, event: str, **kw) -> None:
        self.log.append({"time": self.stamp, "bot": self.bot.bot_id, "event": event, **kw})

    def eur(self, d: int, entry: float, exit_: float, size: float, q) -> float | None:
        if not q or not q.eur_rate:
            return None
        return d * (exit_ - entry) * size * (q.lot or 1.0) / q.eur_rate

    def buche(self, tr: dict, level: float | None, quelle: str, q) -> None:
        rec = {**tr, "exit": None if level is None else round(level, 4), "quelle": quelle, "closed_utc": self.stamp}
        if level is not None:
            if tr.get("dist"):
                rec["r"] = round(tr["richtung"] * (level - tr["entry"]) / tr["dist"], 3)
                self.st["summe_r"] = round(float(self.st["summe_r"]) + rec["r"], 3)
            rec["pct"] = round(100 * tr["richtung"] * (level - tr["entry"]) / tr["entry"], 4)
            self.st["summe_pct"] = round(float(self.st["summe_pct"]) + rec["pct"], 4)
            e = self.eur(tr["richtung"], tr["entry"], level, tr["size"], q)
            rec["pnl_eur"] = None if e is None else round(e, 2)
            self.st["summe_eur"] = round(float(self.st["summe_eur"]) + float(rec["pnl_eur"] or 0), 2)
        self.st["trades"] = int(self.st["trades"]) + 1
        self.st["offen"] = None
        self.fertige.append(rec)
        self.ev("Trade zu", dealId=tr["dealId"], kurs=rec["exit"], r=rec.get("r"), pct=rec.get("pct"),
                eur=rec.get("pnl_eur"), quelle=quelle)

    def abgleich(self, positionen: list[dict], q) -> None:
        from suche.demo_bots import broker_exit
        tr = self.st["offen"]
        if not tr:
            return
        if tr["dealId"] in {str(p["position"].get("dealId")) for p in positionen}:
            return
        level, quelle = broker_exit(self.client, {"dealId": tr["dealId"], "opened_utc": tr["opened_utc"]},
                                    self.now.to_pydatetime())
        self.buche(tr, level, quelle or "Broker", q)

    def zeit_aus(self, q) -> None:
        tr = self.st["offen"]
        if not tr or self.now < pd.Timestamp(tr["aus_utc"]):
            return
        if not self.send:
            self.ev("würde schließen (Zeit)", dealId=tr["dealId"])
            return
        try:
            conf = self.client.close_position(tr["dealId"])
        except Exception as err:            # noqa: BLE001 - nächster Lauf versucht es wieder
            self.ev("schließen fehlgeschlagen", dealId=tr["dealId"], fehler=str(err)[:200])
            return
        if str((conf or {}).get("dealStatus") or "").upper() == "REJECTED":
            self.ev("schließen abgelehnt", dealId=tr["dealId"], grund=(conf or {}).get("reason"))
            return
        level = _num((conf or {}).get("level")) or (q.bid if tr["richtung"] > 0 else q.offer)
        self.buche(tr, level, "Zeit", q)

    def opens(self, tag: pd.Timestamp) -> dict:
        out = {}
        for art in self.bot.opens_noetig():
            key = f"{art}:{periode(tag, art)[0]}"
            if key not in self.st["opens"]:
                try:
                    o = hole_open(self.client, self.bot.epic, tag, art)
                except Exception as err:     # noqa: BLE001 - dann fehlt das Open, kein Trade
                    self.ev("Open nicht lesbar", art=art, fehler=str(err)[:160])
                    o = None
                if o is not None:
                    self.st["opens"][key] = round(o, 4)
            out[art] = self.st["opens"].get(key)
        # nur die aktuellen Perioden behalten
        aktuell = {f"{a}:{periode(tag, a)[0]}" for a in self.bot.opens_noetig()}
        self.st["opens"] = {k: v for k, v in self.st["opens"].items() if k in aktuell}
        return out

    def einstieg(self, z: dict, q, available: float, positionen: list[dict]) -> None:
        from gold.bot.rules import bars_from_prices
        tag = str(z["tag"].date())
        if self.st.get("tag_erledigt") == tag or self.st["offen"] or self.now < z["ein"]:
            return
        if positionen:                       # höchstens 1 offene Position je Markt, auch eine, die wir nicht kennen
            self.st["tag_erledigt"] = tag
            self.ev("Position schon offen, kein neuer Trade", tag=tag,
                    deals=[str(p["position"].get("dealId")) for p in positionen])
            return
        if self.now > z["ein"] + FENSTER:
            self.st["tag_erledigt"] = tag
            self.st["letzte_entscheidung"] = {"zeit": self.stamp, "tag": tag, "action": "none",
                                              "why": "Einstiegszeit verpasst (mehr als 10 Min. später)"}
            self.ev("verpasst", tag=tag)
            return
        raw5 = self.client.prices(self.bot.epic, "MINUTE_5", 1000)
        b5, _ = bars_from_prices(raw5, self.now.to_pydatetime(), "5min")
        ein_open = next((float(p["openPrice"]["bid"]) for p in raw5
                         if pd.Timestamp(p["snapshotTimeUTC"]) == z["ein"]), None)
        if ein_open is None and self.bot.familie == "halbe_stunde":
            ein_open = q.bid                 # laufende Kerze nicht geliefert: Kurs jetzt (höchstens 3 Min. später)
        if self.bot.kerzen == 15:
            b_tf, _ = bars_from_prices(self.client.prices(self.bot.epic, "MINUTE_15", 20), self.now.to_pydatetime(),
                                       "15min")
        else:
            b_tf = b5
        opens = self.opens(handelstag(z["ein"] - pd.Timedelta(minutes=5)))
        sig = entscheide(self.bot, z, b5, b_tf, opens, q.bid, q.offer, ein_open)
        self.st["tag_erledigt"] = tag
        self.st["letzte_entscheidung"] = {"zeit": self.stamp, "tag": tag, "action": "open" if sig["d"] else "none",
                                          "why": sig.get("warum") or "Signal", "opens": opens,
                                          "kurs_filter": sig.get("kurs_filter")}
        if not sig["d"]:
            self.ev("kein Trade", tag=tag, warum=sig["warum"])
            return
        if not q.tradeable:
            self.ev("Markt zu", tag=tag)
            return
        size = groesse(self.bot, sig["dist"], q)
        marge = size * (q.lot or 1) * sig["entry"] * q.margin_pct / 100 / (q.eur_rate or 1)
        if marge > 0.8 * available:
            self.ev("zu wenig Margin", tag=tag, marge=round(marge, 2), frei=round(available, 2))
            return
        d = sig["d"]
        body = {"epic": self.bot.epic, "direction": "BUY" if d > 0 else "SELL", "size": size, "guaranteedStop": False}
        if sig["stop"] is not None:
            body["stopLevel"] = round(sig["stop"], q.decimals if q.decimals < 6 else 2)
            body["profitLevel"] = round(sig["ziel"], q.decimals if q.decimals < 6 else 2)
        info = {"tag": tag, "richtung": d, "size": size, "stop": body.get("stopLevel"), "ziel": body.get("profitLevel")}
        if not self.send:
            self.ev("würde öffnen", **info, kurs=sig["entry"])
            return
        try:
            ref = self.client._request("POST", "/positions", json=body).json()["dealReference"]
            conf = self.client.confirm(ref)
        except Exception as err:            # noqa: BLE001 - kein zweiter Versuch, damit nichts doppelt entsteht
            self.ev("Order fehlgeschlagen", **info, fehler=str(err)[:200])
            return
        if str((conf or {}).get("dealStatus") or "").upper() == "REJECTED":
            self.ev("Order abgelehnt", **info, grund=(conf or {}).get("reason"))
            return
        deal = str(((conf or {}).get("affectedDeals") or [{}])[0].get("dealId") or (conf or {}).get("dealId"))
        level = _num((conf or {}).get("level")) or sig["entry"]
        dist = None if sig["stop"] is None else abs(level - sig["stop"])
        self.st["offen"] = {"dealId": deal, "richtung": d, "size": size, "entry": round(level, 4), "stop": sig["stop"],
                            "ziel": sig["ziel"], "dist": None if dist is None else round(dist, 4),
                            "opened_utc": self.stamp, "aus_utc": z["aus"].strftime("%Y-%m-%dT%H:%M:%S"), "tag": tag}
        self.ev("eröffnet", **info, dealId=deal, entry=round(level, 4))


def _num(x) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def lauf_bot(bot: Scalper, client, st: dict, now: pd.Timestamp, available: float, send: bool) -> Lauf:
    from suche.demo_bots import eur_rate, quote_from_market
    lauf = Lauf(bot, client, st, now, send)
    q = quote_from_market(client.market(bot.epic), None)
    q.eur_rate = eur_rate(client, q.currency, {})
    positionen = [p for p in client.positions() if (p.get("market") or {}).get("epic") == bot.epic]
    lauf.abgleich(positionen, q)
    lauf.zeit_aus(q)
    if lauf.st["offen"] is None and any(e["event"] == "Trade zu" for e in lauf.log):
        positionen = [p for p in client.positions() if (p.get("market") or {}).get("epic") == bot.epic]
    z = zeiten(bot, now)
    if z is not None:
        lauf.einstieg(z, q, available, positionen)
    lauf.st["stand"] = lauf.stamp
    return lauf


def run(client, states: dict, now: datetime, send: bool = True) -> dict:
    nowts = pd.Timestamp(now).tz_convert("UTC").tz_localize(None) if pd.Timestamp(now).tzinfo else pd.Timestamp(now)
    out = {}
    if not vorab_ok():
        for bot in BOTS:
            lauf = Lauf(bot, client, states.get(bot.bot_id), nowts, send)
            lauf.ev("Regeln nicht versiegelt, nichts getan")
            out[bot.bot_id] = lauf
        return out
    konto = next((a for a in client.accounts() if str(a.get("accountId")) == KONTO), None)
    if konto is None:
        for bot in BOTS:
            lauf = Lauf(bot, client, states.get(bot.bot_id), nowts, send)
            lauf.ev("kein Konto", konto="…" + KONTO[-4:])
            out[bot.bot_id] = lauf
        return out
    available = float(_num((konto.get("balance") or {}).get("available")) or 0)
    vorher = client.account_id
    client.switch_account(KONTO)
    try:
        aktiv = None
        with contextlib.suppress(Exception):
            aktiv = str((client._get("/session") or {}).get("accountId") or "") or None
        for bot in BOTS:
            if aktiv is not None and aktiv != KONTO:
                lauf = Lauf(bot, client, states.get(bot.bot_id), nowts, send)
                lauf.ev("anderes Konto aktiv, nichts getan", aktiv="…" + aktiv[-4:])
            else:
                try:
                    lauf = lauf_bot(bot, client, states.get(bot.bot_id), nowts, available, send)
                except Exception as err:     # noqa: BLE001 - ein Bot hält die anderen nie auf
                    lauf = Lauf(bot, client, states.get(bot.bot_id), nowts, send)
                    lauf.ev("Fehler", fehler=f"{type(err).__name__}: {err}"[:300])
            out[bot.bot_id] = lauf
    finally:
        with contextlib.suppress(Exception):
            if vorher and vorher != KONTO:
                client.switch_account(vorher)
    return out


def zusammenfassung(st: dict, fertige_alle: list[dict]) -> dict:
    r = [t["r"] for t in fertige_alle if t.get("r") is not None]
    g, v = sum(x for x in r if x > 0), -sum(x for x in r if x < 0)
    return {"trades": int(st.get("trades") or 0), "pf_r": (round(g / v, 2) if v > 0 else None),
            "summe_r": st.get("summe_r"), "summe_pct": st.get("summe_pct"), "summe_eur": st.get("summe_eur"),
            "urteil": "Demo-Vorwärtstest, Urteil nach 40 Trades"}


def schreiben(bot: Scalper, st: dict, log: list[dict], fertige: list[dict]) -> None:
    ordner = JOURNAL / bot.bot_id
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=1, default=str) + "\n",
                                       encoding="utf-8")
    wichtig = [e for e in log if e["event"] not in ("würde öffnen", "würde schließen (Zeit)")]
    if wichtig:
        with open(ordner / "log.jsonl", "a", encoding="utf-8") as fh:
            for e in wichtig:
                fh.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
    if fertige:
        with open(ordner / "trades.jsonl", "a", encoding="utf-8") as fh:
            for t in fertige:
                fh.write(json.dumps(t, ensure_ascii=False, default=str) + "\n")
    alle = []
    p = ordner / "trades.jsonl"
    if p.exists():
        alle = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    karte = {"bot": bot.bot_id, "name": bot.name, "epic": bot.epic, "konto": "…" + KONTO[-4:], "konto_name": KONTO_NAME,
             "stand": st.get("stand"), "start": st.get("start"), "regel": bot.regel(),
             "vorab": "suche/VORAB_scalping_opens.yaml", "test": bot.test, "offen": st.get("offen"),
             "letzte_entscheidung": st.get("letzte_entscheidung"), "zusammenfassung": zusammenfassung(st, alle),
             "letzte_trades": alle[-5:]}
    (JOURNAL / f"{bot.bot_id}.json").write_text(json.dumps(karte, ensure_ascii=False, indent=1, default=str) + "\n",
                                                encoding="utf-8")


def main(argv: list[str]) -> int:
    from gold.bot.capital import CapitalClient
    from gold.bot.runner import CRED_KEYS, clean_credentials

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="nur rechnen, keine Order")
    args = ap.parse_args(argv)
    creds = clean_credentials({k: os.environ.get(k, "") for k in CRED_KEYS})
    if not all(creds):
        print("Keine Capital.com-Zugangsdaten, Scalper übersprungen")
        return 0
    states = {}
    for bot in BOTS:
        p = JOURNAL / bot.bot_id / "state.json"
        states[bot.bot_id] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    client = CapitalClient(*creds, environment="demo")
    client.login()
    now = datetime.now(timezone.utc)
    try:
        out = run(client, states, now, send=not args.dry_run)
    finally:
        with contextlib.suppress(Exception):
            client.logout()
    fehler = False
    for bot in BOTS:
        lauf = out[bot.bot_id]
        fehler = fehler or any(e["event"] == "Fehler" for e in lauf.log)
        print(bot.bot_id, json.dumps({"ereignisse": lauf.log, "fertig": lauf.fertige, "offen": lauf.st.get("offen")},
                                     ensure_ascii=False, default=str))
        if not args.dry_run:
            lauf.st.setdefault("start", lauf.stamp)
            schreiben(bot, lauf.st, lauf.log, lauf.fertige)
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
