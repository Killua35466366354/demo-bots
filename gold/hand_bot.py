"""Gold-Hand-Bot: Gold Short und Long nach den drei Seiten des Gold-Short-Bots, ohne Stop und ohne Ziel, mit einer
Nachricht aufs Handy. Kiron geht selbst raus. Nur Capital.com-DEMOKONTO, nie echtes Geld.

    python -m gold.hand_bot              # ein Lauf: Kerzen holen, Signal in der Kerze "jetzt"? Dann öffnen und melden
    python -m gold.hand_bot --dry-run    # nur rechnen und zeigen, keine Order, keine Nachricht

Kirons Wunsch vom 06.11.2026 15:51 UTC: den Short-Bot und den Long-Bot zusammentun, "ohne Stop-Loss, ohne nix und ohne
Backtest", nur die Einstiege. Der Bot soll eine Nachricht schicken, wenn er in einen Trade geht, damit Kiron selbst
rausgehen kann, wann er will. Regeln festgelegt in suche/VORAB_gold_hand.yaml (Prüfsumme im Protokoll vor dem ersten
Trade, sonst öffnet der Bot nichts).

Regeln:
- Signale wie der Gold-Short-Bot (gold/short_bot.simuliere: gross_klein_3, gross_box_kerze, gross_box auf 15-Min.-
  Kerzen, nur fertige 1-Std.- und 4-Std.-Kerzen), dazu die Käufe derselben drei Seiten (Komitee 2, Variante longs).
- Kommt in der Kerze "jetzt" ein Short, gilt der (erste Seite gewinnt). Ein Long nur, wenn es in dieser Kerze keinen
  Short gibt.
- Kein Stop, kein Ziel beim Broker. Der Bot schließt nie etwas. Stop und Ziel 1 der Strategie stehen nur zur
  Orientierung in der Nachricht.
- Größe: 5 € bis zum Stop der Strategie (nur zum Rechnen), höchstens 1 Unze je Trade und 2 Unzen zusammen, höchstens 4
  Goldpositionen zugleich auf dem Konto (auch Kirons eigene zählen).
- Ist eine Goldposition in die andere Richtung offen, öffnet er nichts (das Konto hat kein Hedging, sonst würde die neue
  Order die alte schließen) und schickt nur die Nachricht.
- Hintergrund (Kirons Wunsch vom 06.11.2026 16:12 UTC, "damit keine völlig unnötigen Trades genommen werden"): wie
  der Richtungs-Check von Gold-Bot 2.0 (gold/v2/richtung.py). Stehen der letzte fertige Tagesschluss über seinem
  50-Tage-Schnitt und der letzte fertige 4-Std.-Schluss über seiner EMA 50, gibt es keinen Short. Stehen beide darunter,
  gibt es keinen Long. Sind sie uneins, ist beides erlaubt.
- News-Agent (derselbe Wunsch): kein Einstieg von 60 Minuten vor bis 30 Minuten nach einem wichtigen US-Termin
  (Fed-Zinsentscheid, Inflation, Arbeitsmarkt aus gold/v2/termine.yaml und alle roten USD-Termine aus dem
  ForexFactory-Wochenkalender), und 45 Minuten Pause nach einem Kursschock (15-Min.-Kerze über 3 x ATR 20). Sind
  Goldpositionen offen, warnt er bis zu 45 Minuten vor einem solchen Termin einmal. Jede Nachricht zeigt die neuesten
  Gold-Schlagzeilen (Google News), damit Kiron selbst einordnen kann. Die Schlagzeilen entscheiden nichts.
- Nachricht über ntfy (App "ntfy", Thema im GitHub-Secret NTFY_THEMA). Ohne Thema steht sie nur im Journal. Kommt
  eine Nachricht nicht an (ntfy.sh lässt ohne Konto 250 Nachrichten je 12 Std. und IP-Adresse zu, GitHub teilt sich
  die Adressen), holt der nächste Lauf sie nach, bis 12 Std. lang. Mit dem Secret NTFY_TOKEN (Zugang eines eigenen
  ntfy-Kontos) zählt die Grenze für Kiron allein. Beim ersten Lauf kommt eine Start-Nachricht.
- Er schreibt nur journal/gold-hand/ und journal/gold-hand.json.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from gold import short_bot as sb
from gold import tiktok_schatten as ts

ROOT = ts.ROOT
BOT_ID = "gold-hand"
EPIC = ts.EPIC
KONTO = "332263750966269086"          # Account 5 (Kirons Wahl), statt des Gold-Short-Bots, geteilt mit dem Dow-Laborbot
KONTO_NAME = "Account 5"
HAUPT_ENDUNG = sb.HAUPT_ENDUNG        # Hauptkonto des Gold-Bots, hier nie handeln
SEITEN = sb.SEITEN
MAX_OFFEN = 4
MAX_OZ_GESAMT = 2.0
VORAB = ROOT / "suche" / "VORAB_gold_hand.yaml"
KEY = "VORAB_gold_hand sha256 "
JDIR = ROOT / "journal" / "gold-hand"
COCKPIT = ROOT / "journal" / "gold-hand.json"
NTFY = "https://ntfy.sh/"
KLICK = "https://capital.com/trading/platform/"
BERLIN = "Europe/Berlin"
NAMEN = {"gross_klein_3": "Groß-und-klein 3", "gross_box_kerze": "Große Box mit Kerze", "gross_box": "Große Box"}
GOLD_BOT_DATEIEN = sb.GOLD_BOT_DATEIEN
HG_SMA_TAGE, HG_EMA_4H = 50, 50
NEWS_VOR, NEWS_NACH = pd.Timedelta(minutes=60), pd.Timedelta(minutes=30)
WARN_VOR = pd.Timedelta(minutes=45)
SCHOCK_ATR, SCHOCK_KERZEN, ATR_N = 3.0, 3, 20
FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FF_ALTER = pd.Timedelta(hours=6)
RSS_URL = "https://news.google.com/rss/search?q=spot+gold+when:1d&hl=en-US&gl=US&ceid=US:en"
SCHLAGZEILEN, SCHLAGZEILEN_STD = 3, 6
NACHHOLEN_STD = 12                 # nicht zugestellte Nachrichten so lange nachholen
TERMIN_NAMEN = {"fomc": "Fed-Zinsentscheid", "cpi": "US-Inflation (CPI)", "nfp": "US-Arbeitsmarkt (NFP)"}


def _holen(url: str):
    """GET mit kurzer Wartezeit (in den Tests ersetzt)."""
    import requests
    return requests.get(url, timeout=15, headers={"User-Agent": "gold-hand-bot"})


# --------------------------------------------------------------------------------------------------------------------
# Hintergrund und News

def _schluesse(prices: list[dict], now: pd.Timestamp, dauer: str) -> pd.DataFrame:
    """Bid-Schlusskurse der fertigen Kerzen (die laufende fällt weg)."""
    if not prices:
        return pd.DataFrame(columns=["close"], dtype=float)
    df = pd.DataFrame([{"t": pd.Timestamp(p["snapshotTimeUTC"]), "close": float(p["closePrice"]["bid"])}
                       for p in prices]).drop_duplicates("t", keep="last").set_index("t").sort_index()
    return df[df.index + pd.Timedelta(dauer) <= now]


def hintergrund(client, now: pd.Timestamp) -> dict:
    """+1: Tagesschluss über SMA 50 und 4-Std.-Schluss über EMA 50 (kein Short), -1: beide darunter (kein Long), 0 sonst.
    Nur fertige Kerzen. Fehlen Daten, ist der Wert 0 (dann sperrt der Hintergrund nichts)."""
    out: dict = {"richtung": 0}
    try:
        tag = _schluesse(client.prices(EPIC, "DAY", 80), now, "1D")
        h4 = _schluesse(client.prices(EPIC, "HOUR_4", 120), now, "4h")
    except Exception as err:            # noqa: BLE001
        out["fehler"] = str(err)[:120]
        return out
    a = f = 0
    if len(tag) >= HG_SMA_TAGE:
        c, sma = float(tag["close"].iloc[-1]), float(tag["close"].iloc[-HG_SMA_TAGE:].mean())
        a = 1 if c > sma else -1 if c < sma else 0
        out.update(tag=round(c, 2), sma50=round(sma, 2))
    if len(h4) >= HG_EMA_4H + 10:
        c4 = float(h4["close"].iloc[-1])
        ema = float(h4["close"].ewm(span=HG_EMA_4H, adjust=False).mean().iloc[-1])
        f = 1 if c4 > ema else -1 if c4 < ema else 0
        out.update(h4=round(c4, 2), ema50=round(ema, 2))
    out["richtung"] = 1 if a > 0 and f > 0 else -1 if a < 0 and f < 0 else 0
    return out


def hg_text(hg: dict) -> str:
    r = hg.get("richtung", 0)
    if r > 0:
        return "Hintergrund: Gold steigt (Tag über 50-Tage-Schnitt, 4 Std. über EMA 50)."
    if r < 0:
        return "Hintergrund: Gold fällt (Tag unter 50-Tage-Schnitt, 4 Std. unter EMA 50)."
    return "Hintergrund: uneinig, Short und Long erlaubt."


def ff_termine(st: dict, now: pd.Timestamp) -> list[tuple[pd.Timestamp, str]]:
    """Rote USD-Termine dieser Woche von ForexFactory, höchstens alle 6 Stunden neu geholt (Stand in state.json)."""
    from gold.v2.news import ff_events
    cache = st.get("ff") or {}
    if not cache or now - pd.Timestamp(cache.get("stand")) > FF_ALTER:
        try:
            ev = ff_events(_holen(FF_URL).json())
            cache = {"stand": now.isoformat(timespec="seconds"),
                     "termine": [[t.isoformat(), s] for t, s in zip(ev["utc"], ev["title"])]}
        except Exception as err:        # noqa: BLE001 - dann der alte Stand
            cache = dict(cache, fehler=str(err)[:120]) if cache else {"stand": now.isoformat(), "termine": [],
                                                                      "fehler": str(err)[:120]}
        st["ff"] = cache
    return [(pd.Timestamp(t), str(s)) for t, s in cache.get("termine", [])]


def alle_termine(st: dict, now: pd.Timestamp) -> list[tuple[pd.Timestamp, str]]:
    from gold.v2 import termine
    ev = termine.load()
    nah = ev[(ev["utc"] >= now - pd.Timedelta(days=1)) & (ev["utc"] <= now + pd.Timedelta(days=2))]
    out = [(pd.Timestamp(t), TERMIN_NAMEN.get(a, a)) for t, a in zip(nah["utc"], nah["art"])]
    return sorted(out + ff_termine(st, now))


def schock(b: ts.Basis, n: int) -> bool:
    """Eine der letzten SCHOCK_KERZEN fertigen 15-Min.-Kerzen hatte eine Spanne über SCHOCK_ATR x ATR 20 davor."""
    import numpy as np
    h, lo, c = b.h[:n], b.l[:n], b.c[:n]
    if n < ATR_N + SCHOCK_KERZEN + 1:
        return False
    tr = np.maximum(h[1:] - lo[1:], np.maximum(abs(h[1:] - c[:-1]), abs(lo[1:] - c[:-1])))
    for k in range(1, SCHOCK_KERZEN + 1):
        i = len(tr) - k
        atr = tr[i - ATR_N:i].mean()
        if atr > 0 and (h[1:][i] - lo[1:][i]) > SCHOCK_ATR * atr:
            return True
    return False


def news_lage(st: dict, now: pd.Timestamp, b: ts.Basis | None = None, n: int | None = None) -> dict:
    ev = alle_termine(st, now)
    nah = [(t, s) for t, s in ev if now - NEWS_NACH <= t <= now + NEWS_VOR]
    gruende = [f"{s} um {_berlin(t)} Uhr" for t, s in nah]
    if b is not None and n is not None and schock(b, n):
        gruende.append("Kursschock in den letzten 45 Minuten")
    naechster = next(((t, s) for t, s in ev if t > now), None)
    return {"pause": bool(gruende), "gruende": gruende, "termine": ev,
            "naechster": None if naechster is None else f"{naechster[1]} am {_berlin(naechster[0])} Uhr"}


def schlagzeilen(now: pd.Timestamp) -> list[str]:
    """Die neuesten Gold-Schlagzeilen der letzten Stunden (Google News RSS). Nur zum Lesen, entscheiden nichts."""
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    try:
        root = ET.fromstring(_holen(RSS_URL).content)
    except Exception:                   # noqa: BLE001
        return []
    out = []
    for it in root.iter("item"):
        titel = (it.findtext("title") or "").strip()
        try:
            t = pd.Timestamp(parsedate_to_datetime(it.findtext("pubDate") or "")).tz_convert("UTC").tz_localize(None)
        except (TypeError, ValueError):
            continue
        if titel and now - t <= pd.Timedelta(hours=SCHLAGZEILEN_STD):
            out.append((t, titel[:110]))
    out.sort(reverse=True)
    return [f"{_berlin(t)} {s}" for t, s in out[:SCHLAGZEILEN]]


def vorab_ok() -> bool:
    from suche.runde1 import journal_lines, last_value, sha256_text
    if not VORAB.exists():
        return False
    return last_value(journal_lines(), KEY) == sha256_text(VORAB.read_text(encoding="utf-8"))


def _num(x) -> float | None:
    return sb._num(x)


def _de(x: float, n: int = 2) -> str:
    return f"{x:,.{n}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _berlin(t) -> str:
    return pd.Timestamp(t).tz_localize("UTC").tz_convert(BERLIN).strftime("%d.%m. %H:%M")


def richtung(p: dict) -> int:
    return 1 if str(p["position"].get("direction") or "").upper() == "BUY" else -1


def sende(text: str, titel: str, tags: list[str], thema: str | None = None, post=None) -> bool:
    """Nachricht über ntfy. Ohne Thema nichts senden. Fehler halten den Lauf nie auf."""
    thema = thema if thema is not None else os.environ.get("NTFY_THEMA", "").strip()
    if not thema:
        return False
    if post is None:
        import requests
        post = requests.post
    token = os.environ.get("NTFY_TOKEN", "").strip()
    extra = {"headers": {"Authorization": f"Bearer {token}"}} if token else {}
    try:
        r = post(NTFY, json={"topic": thema, "title": titel, "message": text, "tags": tags, "priority": 4,
                             "click": KLICK}, timeout=15, **extra)
        code = int(getattr(r, "status_code", 200))
        if not 200 <= code < 300:
            print(f"ntfy antwortet {code}")
        return 200 <= code < 300
    except Exception as err:            # noqa: BLE001
        print(f"ntfy nicht erreichbar: {err}")
        return False


class Lauf:
    def __init__(self, client, state: dict, now: datetime, send_orders: bool = True, post=None):
        self.client = client
        self.st = copy.deepcopy(state or {})
        self.now = sb._jetzt(now)
        self.stamp = self.now.isoformat(timespec="seconds")
        self.send = send_orders
        self.post = post
        self.log: list[dict] = []
        self.fertige: list[dict] = []
        self.nachrichten: list[dict] = []
        self.q = None
        self._zeilen: list[str] | None = None
        self.st.setdefault("format", 1)
        self.st.setdefault("start", self.stamp)
        self.st.setdefault("offen", [])
        self.st.setdefault("trades", 0)
        self.st.setdefault("summe_r", 0.0)

    def ev(self, event: str, **kw) -> None:
        self.log.append({"time": self.stamp, "event": event, **kw})

    def zeilen(self) -> list[str]:
        if self._zeilen is None:
            self._zeilen = schlagzeilen(self.now)
        return self._zeilen

    def melde(self, titel: str, text: str, tags: list[str]) -> None:
        z = self.zeilen()
        if z:
            text += "\n\nNews:\n" + "\n".join(z)
        self.nachrichten.append({"titel": titel, "text": text})
        if not self.send:
            self.ev("würde melden", titel=titel, text=text)
            return
        ok = sende(text, titel, tags, post=self.post)
        self.ev("Nachricht", titel=titel, gesendet=ok)
        if not ok and os.environ.get("NTFY_THEMA", "").strip():
            self.merken(titel, text, tags)

    def merken(self, titel: str, text: str, tags: list[str]) -> None:
        """Nicht zugestellt: der nächste Lauf versucht es noch einmal (höchstens 20, bis NACHHOLEN_STD alt)."""
        self.st.setdefault("nachholen", []).append({"zeit": self.stamp, "titel": titel, "text": text, "tags": tags})
        self.st["nachholen"] = self.st["nachholen"][-20:]

    def nachholen(self) -> None:
        """Nachrichten aus früheren Läufen, die ntfy nicht angenommen hat, noch einmal schicken."""
        rest = []
        for m in self.st.get("nachholen", []):
            alt = (self.now - pd.Timestamp(m["zeit"])).total_seconds() / 3600
            if alt > NACHHOLEN_STD:
                self.ev("Nachricht verworfen", titel=m["titel"], zeit=m["zeit"])
                continue
            text = f"(verspätet, von {_berlin(pd.Timestamp(m['zeit']))})\n" + m["text"]
            ok = sende(text, m["titel"], m["tags"], post=self.post)
            self.ev("Nachricht nachgeholt", titel=m["titel"], gesendet=ok)
            if not ok:
                rest.append(m)
        if rest:
            self.st["nachholen"] = rest
        else:
            self.st.pop("nachholen", None)

    # ---- Positionen, die Kiron geschlossen hat ----

    def abgleich(self, gold: list[dict]) -> None:
        from suche.demo_bots import broker_exit
        da = {str(p["position"].get("dealId")) for p in gold}
        rest = []
        for tr in self.st["offen"]:
            if tr["dealId"] in da:
                rest.append(tr)
                continue
            level, quelle = broker_exit(self.client, {"dealId": tr["dealId"], "opened_utc": tr["opened_utc"]},
                                        self.now.to_pydatetime())
            d = tr["richtung"]
            rec = {**tr, "exit": None if level is None else round(level, 2), "quelle": quelle or "unbekannt",
                   "closed_utc": self.stamp}
            if level is not None:
                rec["r"] = round(d * (level - tr["entry"]) / tr["dist"], 3)
                usd = d * (level - tr["entry"]) * tr["size"] * (self.q.lot or 1.0)
                rec["pnl_eur"] = round(usd / self.q.eur_rate, 2) if self.q.eur_rate else None
                self.st["summe_r"] = round(float(self.st["summe_r"]) + rec["r"], 3)
            self.st["trades"] = int(self.st["trades"]) + 1
            self.fertige.append(rec)
            self.ev("Trade zu", dealId=tr["dealId"], kurs=rec["exit"], r=rec.get("r"), quelle=rec["quelle"])
        self.st["offen"] = rest

    # ---- Warnung vor wichtigen Terminen, wenn Gold offen ist ----

    def warne(self, gold: list[dict]) -> None:
        if not gold:
            return
        try:
            ev = alle_termine(self.st, self.now)
        except Exception as err:            # noqa: BLE001
            self.ev("Termine nicht lesbar", fehler=str(err)[:120])
            return
        gewarnt = list(self.st.get("gewarnt") or [])
        bald = [(t, s) for t, s in ev if self.now < t <= self.now + WARN_VOR and f"{t.isoformat()} {s}" not in gewarnt]
        if not bald:
            return
        n_s = sum(1 for p in gold if richtung(p) < 0)
        n_l = len(gold) - n_s
        was = ", ".join(f"{s} um {_berlin(t)} Uhr" for t, s in bald)
        self.melde("Gold: wichtiger Termin bald",
                   f"{was}. Du hast {n_s} Short und {n_l} Long in Gold offen, ohne Stop. Der Kurs kann dann stark "
                   f"springen. Jetzt prüfen, ob du rausgehen oder absichern willst.", ["warning"])
        self.st["gewarnt"] = (gewarnt + [f"{t.isoformat()} {s}" for t, s in bald])[-50:]

    # ---- Neuer Trade ----

    def einstieg(self, b: ts.Basis, n: int, trades: dict, gold: list[dict], available_eur: float | None) -> None:
        q = self.q
        t_ph = pd.Timestamp(b.t[n])
        shorts = [(s, t) for s in SEITEN for t in trades.get(s, []) if t["richtung"] < 0 and t["_j0"] == n]
        longs = [(s, t) for s in SEITEN for t in trades.get(s, []) if t["richtung"] > 0 and t["_j0"] == n]
        kand = shorts or longs
        if not kand or self.st.get("letzte_kerze") == str(t_ph):
            return
        seite, sig = kand[0]
        d = int(sig["richtung"])
        if not q.tradeable:
            self.ev("Signal, Markt zu", seite=seite, richtung=d, kerze=str(t_ph))
            return                                    # nächster Lauf versucht es wieder
        self.st["letzte_kerze"] = str(t_ph)
        wort = "LONG" if d > 0 else "SHORT"
        dist = float(sig["r_usd"])
        kurs = q.offer if d > 0 else q.bid
        stop_ref, ziel_ref = kurs - d * dist, kurs + d * sb.ZIEL_FAKTOR * dist
        gruende = []
        if not sb.frisch(t_ph, self.now):
            gruende.append("Signal zu alt")
        if not vorab_ok():
            gruende.append("VORAB_gold_hand.yaml nicht festgelegt")
        hg = hintergrund(self.client, self.now)
        if hg["richtung"] == -d:
            gruende.append("gegen den Hintergrund (" + ("Gold steigt" if d < 0 else "Gold fällt") + " auf Tag und 4 Std.)")
        nl = news_lage(self.st, self.now, b, n)
        if nl["pause"]:
            gruende.append("News-Pause: " + ", ".join(nl["gruende"]))
        gegen = [p for p in gold if richtung(p) != d]
        if gegen:
            gruende.append(f"eine Goldposition in die andere Richtung ist offen ({len(gegen)})")
        if len(gold) >= MAX_OFFEN:
            gruende.append(f"schon {MAX_OFFEN} Goldpositionen offen")
        sizes, warum = sb.groessen(dist, q, (1.0,))
        if sizes is None:
            gruende.append(warum)
        else:
            offen_oz = sum(float(_num(p["position"].get("size")) or 0) for p in gold) * (q.lot or 1)
            if offen_oz + sizes[0] * (q.lot or 1) > MAX_OZ_GESAMT + 1e-9:
                gruende.append(f"mehr als {MAX_OZ_GESAMT:.0f} Unzen zusammen")
            marge = sizes[0] * (q.lot or 1) * kurs * q.margin_pct / 100 / (q.eur_rate or 1)
            if available_eur is not None and marge > 0.8 * available_eur:
                gruende.append(f"zu wenig freie Marge ({available_eur:.0f} €)")
        info = {"seite": seite, "richtung": d, "kerze": str(t_ph), "signal": sig.get("signal"), "dist": round(dist, 2),
                "hintergrund": hg, "news": nl["gruende"]}
        lage = hg_text(hg) + (f" Nächster wichtiger Termin: {nl['naechster']}." if nl["naechster"] else "")
        orient = (f"Zur Orientierung: Stop der Strategie {_de(stop_ref)} (1 R = {_de(dist)} $), Ziel 1 bei "
                  f"{_de(ziel_ref)}.")
        quelle = f"Seite {NAMEN.get(seite, seite)}, 15-Min.-Kerze bis {_berlin(t_ph)} Uhr."
        if gruende:
            self.ev("ausgelassen", **info, gruende=gruende)
            if "Signal zu alt" not in gruende and not any("VORAB" in g for g in gruende):
                self.melde(f"Gold-Signal {wort}, nicht eröffnet",
                           f"Grund: {'; '.join(gruende)}. Kurs {_de(kurs)}. {quelle} Du kannst selbst entscheiden. "
                           f"{orient} {lage}", ["warning"])
            return
        if not self.send:
            self.ev("würde öffnen", **info, size=sizes[0])
            self.melde(f"Gold {wort} eröffnet", f"(Trockenlauf) {sizes[0]} oz bei {_de(kurs)}. {quelle} {orient} {lage}",
                       ["chart_with_upwards_trend" if d > 0 else "chart_with_downwards_trend"])
            return
        vorher = {str(p["position"].get("dealId")) for p in gold}
        body = {"epic": EPIC, "direction": "BUY" if d > 0 else "SELL", "size": sizes[0], "guaranteedStop": False}
        try:
            ref = self.client._request("POST", "/positions", json=body).json()["dealReference"]
            conf = self.client.confirm(ref)
        except Exception as err:                    # noqa: BLE001 - kein zweiter Versuch, damit nichts doppelt entsteht
            self.ev("Order fehlgeschlagen", **info, fehler=str(err)[:200])
            self.melde(f"Gold {wort}: Order fehlgeschlagen", f"{err}"[:200] + f" {quelle}", ["x"])
            return
        if str((conf or {}).get("dealStatus") or "").upper() == "REJECTED":
            self.ev("Order abgelehnt", **info, grund=(conf or {}).get("reason"))
            self.melde(f"Gold {wort}: Order abgelehnt", f"Grund: {(conf or {}).get('reason')}. {quelle}", ["x"])
            return
        neu = [p for p in self.client.positions() if p.get("market", {}).get("epic") == EPIC
               and str(p["position"].get("dealId")) not in vorher]
        pos = neu[0]["position"] if len(neu) == 1 else {}
        deal = str(pos.get("dealId") or ((conf or {}).get("affectedDeals") or [{}])[0].get("dealId")
                   or (conf or {}).get("dealId"))
        level = _num(pos.get("level")) or _num((conf or {}).get("level")) or kurs
        tr = {"dealId": deal, "richtung": d, "size": sizes[0], "entry": round(level, 2), "dist": round(dist, 2),
              "seite": seite, "signal": sig.get("signal"), "einstieg_zeit": str(t_ph), "opened_utc": self.stamp,
              "stop_strategie": round(level - d * dist, 2), "ziel1_strategie": round(level + d * sb.ZIEL_FAKTOR * dist, 2)}
        self.st["offen"].append(tr)
        self.ev("eröffnet", **info, dealId=deal, size=sizes[0], entry=tr["entry"])
        self.melde(f"Gold {wort} eröffnet",
                   f"{KONTO_NAME} (Demo): {_de(sizes[0])} oz bei {_de(level)}. Ohne Stop und ohne Ziel, raus gehst du "
                   f"selbst. {quelle} Zur Orientierung: Stop der Strategie {_de(tr['stop_strategie'])} (1 R = "
                   f"{_de(dist)} $ = etwa 5 €), Ziel 1 bei {_de(tr['ziel1_strategie'])}. {lage}",
                   ["chart_with_upwards_trend" if d > 0 else "chart_with_downwards_trend"])


def run(client, state: dict, now: datetime, send_orders: bool = True, post=None):
    """Ein Lauf. Rückgabe: neuer Stand, Ereignisse, geschlossene Trades, Nachrichten."""
    from gold.bot.rules import bars_from_prices
    from suche.demo_bots import eur_rate, quote_from_market, with_now_bar

    lauf = Lauf(client, state, now, send_orders, post)
    if send_orders and lauf.st.get("nachholen"):
        lauf.nachholen()
    konto = next((a for a in client.accounts() if str(a.get("accountId")) == KONTO), None)
    if konto is None or KONTO.endswith(HAUPT_ENDUNG):
        lauf.ev("kein Konto", konto="…" + KONTO[-4:])
        return lauf.st, lauf.log, [], []
    available = _num((konto.get("balance") or {}).get("available"))
    vorher = client.account_id
    client.switch_account(KONTO)
    try:
        lauf.q = q = quote_from_market(client.market(EPIC), None)
        q.eur_rate = eur_rate(client, q.currency, {})
        gold = [p for p in client.positions() if p.get("market", {}).get("epic") == EPIC]
        lauf.abgleich(gold)
        lauf.warne(gold)
        bars, spread = bars_from_prices(ts.fetch_candles(client, EPIC, chunks=sb.CHUNKS), lauf.now, "15min")
        if len(bars) < sb.MIN_BARS:
            lauf.ev("zu wenig Kerzen", kerzen=len(bars), braucht=sb.MIN_BARS)
        else:
            t_ph = pd.Timestamp(bars.index[-1]) + sb.VIERTEL
            bars2, sp2 = with_now_bar(bars, spread, t_ph, q.bid, q.offer)
            b = ts.basis(bars2, sp2)
            n = len(b) - 1
            trades, _ = sb.simuliere(b, n)
            lauf.einstieg(b, n, trades, gold, available)
            lauf.st["letzter_kurs"] = round(float(q.bid), 2)
        lauf.st["stand"] = lauf.stamp
        return lauf.st, lauf.log, lauf.fertige, lauf.nachrichten
    finally:
        with contextlib.suppress(Exception):
            if vorher and vorher != KONTO:
                client.switch_account(vorher)


START_TEXT = ("Der Gold-Hand-Bot läuft jetzt auf dem Demokonto „Account 5“ von Capital.com. Er meldet jeden Einstieg "
              "(Short oder Long, ohne Stop und ohne Ziel) und jedes ausgelassene Signal mit Grund. Rausgehen machst "
              "du selbst in der Capital.com-App.")


def start_nachricht(st: dict, post=None) -> bool:
    """Einmal beim ersten echten Lauf. Kommt sie nicht an, holt der nächste Lauf sie nach."""
    ok = sende(START_TEXT, "Gold-Hand-Bot ist live", ["rocket"], post=post)
    if not ok and os.environ.get("NTFY_THEMA", "").strip():
        st.setdefault("nachholen", []).append({"zeit": st.get("stand") or st.get("start"),
                                               "titel": "Gold-Hand-Bot ist live", "text": START_TEXT,
                                               "tags": ["rocket"]})
    return ok


def cockpit(st: dict, alle: list[dict]) -> dict:
    r = [float(t["r"]) for t in alle if t.get("r") is not None]
    return {"bot": BOT_ID, "name": "Gold-Hand-Bot (Short und Long ohne Stop, Kiron geht selbst raus)",
            "konto": "…" + KONTO[-4:], "stand": st.get("stand"), "start": st.get("start"),
            "regel": ("Einstiege der drei Seiten des Gold-Short-Bots, Shorts und Longs, ohne Stop und Ziel. Nachricht "
                      "über ntfy, Kiron schließt selbst. 5 € je Strategie-R, höchstens 4 Goldpositionen, 2 oz."),
            "vorab": "suche/VORAB_gold_hand.yaml", "offen": st.get("offen", []),
            "zusammenfassung": {"trades": len(alle), "pf_r": ts.pf(r) if r else None, "summe_r": round(sum(r), 2),
                                "summe_eur": round(sum(float(t.get("pnl_eur") or 0) for t in alle), 2),
                                "urteil": "nur zur Info, Kiron schließt selbst"},
            "letzte_trades": alle[-10:]}


def schreiben(st: dict, log: list[dict], fertige: list[dict], nachrichten: list[dict], jdir: Path = JDIR,
              cockpit_pfad: Path = COCKPIT) -> None:
    for p in (jdir, cockpit_pfad):
        if p.name in GOLD_BOT_DATEIEN or p.name in ("gold-short", "gold-short.json"):
            raise RuntimeError(f"{p} gehört einem anderen Bot")
    jdir.mkdir(parents=True, exist_ok=True)
    (jdir / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for name, rows in (("log.jsonl", log), ("trades.jsonl", fertige),
                       ("nachrichten.jsonl", [{"time": st.get("stand"), **m} for m in nachrichten])):
        if rows:
            with open(jdir / name, "a", encoding="utf-8") as fh:
                fh.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    alle = sb._lies_jsonl(jdir / "trades.jsonl")
    cockpit_pfad.write_text(json.dumps(cockpit(st, alle), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    from gold.bot.capital import CapitalClient
    from gold.bot.runner import CRED_KEYS, clean_credentials

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="nur rechnen, keine Order, keine Nachricht")
    ap.add_argument("--test-nachricht", action="store_true", help="nur eine Probe-Nachricht über ntfy schicken")
    args = ap.parse_args(argv)
    if args.test_nachricht:
        ok = sende("Probe vom Gold-Hand-Bot. So sieht eine Nachricht aus, wenn er Gold kauft oder verkauft.",
                   "Gold-Hand-Bot: Probe", ["white_check_mark"])
        print("Probe gesendet" if ok else "Probe nicht gesendet (NTFY_THEMA fehlt oder ntfy nicht erreichbar)")
        return 0
    creds = clean_credentials({k: os.environ.get(k, "") for k in CRED_KEYS})
    if not all(creds):
        print("Keine Capital.com-Zugangsdaten, Gold-Hand-Bot übersprungen")
        return 0
    path = JDIR / "state.json"
    erster = not path.exists()
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    client = CapitalClient(*creds, environment="demo")
    client.login()
    try:
        st, log, fertige, nachrichten = run(client, state, datetime.now(timezone.utc), send_orders=not args.dry_run)
    finally:
        with contextlib.suppress(Exception):
            client.logout()
    print(json.dumps({"ereignisse": log, "fertig": fertige, "nachrichten": nachrichten,
                      "offen": len(st.get("offen", []))}, ensure_ascii=False, default=str))
    if not args.dry_run:
        if erster:
            print("Start-Nachricht", "gesendet" if start_nachricht(st) else "nicht gesendet")
        schreiben(st, log, fertige, nachrichten)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
