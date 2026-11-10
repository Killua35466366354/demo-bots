"""Kirons Pine-Strategien A (Long) und B (Short) auf 5-Min.-Gold-Kerzen: zwei Demo-Bots mit denselben Einstiegen.

Kirons Wunsch vom 09.11.2026 20:41 UTC, Regeln und Test in suche/VORAB_pine5m.yaml (Gold war der beste Markt, der Test
ist trotzdem nicht bestanden, beide Bots laufen als reiner Demo-Vorwärtstest).

- Bot "pine-k5" (Account 5 …9086, seit Kirons Wort vom 10.11.2026 07:29 UTC, suche/VORAB_pine5m_konto5.yaml): jeder
  Einstieg als Marktorder ohne Stop und Ziel, Nachricht aufs Handy über ntfy, Kiron geht selbst raus. Trade-Abfänger
  seit Kirons Wort vom 10.11.2026 11:18 UTC (suche/VORAB_pine5m_abfang4h.yaml): die ersten 4 Std. nichts, danach Stop
  0,5 R hinter dem besten Kurs seit der Übernahme, nur nachgezogen, nie zurück (schließt am nächsten Hoch im Plus oder
  mit möglichst wenig Minus). Meldet, wenn die Strategie selbst rausgehen würde
  (Pine-Ausstiegssignal), schließt aber nie selbst. Dazu der Gold-Prüfer des Gold-Hand-Bots: kein Einstieg 60 Min. vor
  bis 30 Min. nach wichtigen US-Terminen (keine Sperre nach Kurssprüngen), Warnung vor Terminen, Hintergrund (Tag über
  SMA 50 und 4 Std. über EMA 50: kein Short, beide darunter: kein Long). Hedging: Long und Short dürfen gleichzeitig
  offen sein, der Bot schaltet den Hedging-Modus des Kontos ein (PUT /accounts/preferences). Ist er aus, gilt wie
  vorher "nie gegen die Gegenrichtung".
- Bot "pine-hand" (Konto "Vortag USDJPY" …4094): lief dort vom 10.11. 03:48 bis zum Umzug auf Account 5, öffnet nichts
  Neues mehr und betreut nur noch seine offenen Trades (alter Abfänger wie beim Gold-Hand-Bot: Fehltrade, 0,5 R
  dagegen vor 0,75 R dafür, setzt Stop 1 R und Ziel auf den Einstieg, Notbremse ab 1 R im Minus; Pine-Ausstiegshinweis).
- Bot "pine-tp3" (Konto "US500" …8878): jeder Einstieg mit Take-Profit +3 € und ohne Stop. Notausstieg nur, wenn seine
  offenen Trades zusammen 250 € im Minus sind (schützt die anderen Bots auf dem Konto), sonst schließt er nie selbst.

Beide: Einstieg auf dem Schluss jeder fertigen 5-Min.-Kerze von 7 bis 20 Uhr UTC, 1 R = 3 x ATR(14) der 5-Min.-Kerzen,
5 € je R, höchstens 1 oz je Trade, höchstens 4 Goldpositionen auf dem Konto, nie gegen eine offene Goldposition der
Gegenrichtung (außer pine-k5 mit Hedging). Die anderen Bots auf dem Konto handeln andere Märkte und behalten Marge: Ein Pine-Bot
belegt höchstens 250 € Marge, und nach jeder Order bleiben mindestens 250 € frei. Nie auf dem Hauptkonto des Gold-Bots.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from gold import hand_bot as hb
from gold import short_bot as sb
from gold.backtest import pine_port as pp

ROOT = Path(__file__).resolve().parents[1]
EPIC = "GOLD"
HAUPT_ENDUNG = sb.HAUPT_ENDUNG
VORAB = ROOT / "suche" / "VORAB_pine5m.yaml"
KEY = "VORAB_pine5m sha256 "
STUNDEN = (7.0, 20.0)                  # Einstiege nur in der Handelszeit aus dem Test (UTC)
R_ATR, R_MIN_SPREAD, ATR_N = 3.0, 4.0, 14
FEHL_R, ZIEL1_R = 0.5, 0.75
KERZE = pd.Timedelta(minutes=5)
FRISCH = pd.Timedelta(minutes=10)      # älter als 10 Min. nach Kerzenschluss: Signal verfällt
MAX_OFFEN = 4
MARGE_MAX_EUR = 250.0
FREI_NACH_EUR = 250.0
TP_EUR = 3.0
NOT_AUS_EUR = 250.0                    # Kirons Karte vom 10.11.2026 02:49 UTC: äußerste Grenze, None = nie raus
# Prüfer des TP-Bots (Kirons Wort 10.11.2026 02:48 UTC, suche/VORAB_pine5m_pruefer.yaml, gewählt pruefer_3_1)
PRUEF_WARTEN = pd.Timedelta(hours=3)   # so lange tut der Prüfer nichts
PRUEF_STOP_R = 1.0                     # Stop so weit hinter dem Einstieg, wenn er eingreift
PRUEF_LANG = pd.Timedelta(hours=24)    # nach so langem Warten im Plus raus, im Minus Ziel auf den Einstieg
VORAB_PRUEFER = ROOT / "suche" / "VORAB_pine5m_pruefer.yaml"
KEY_PRUEFER = "VORAB_pine5m_pruefer sha256 "
VORAB_K5 = ROOT / "suche" / "VORAB_pine5m_konto5.yaml"
KEY_K5 = "VORAB_pine5m_konto5 sha256 "
# Abfänger von pine-k5 (Kirons Wort 10.11.2026 11:18 UTC, suche/VORAB_pine5m_abfang4h.yaml)
VORAB_4H = ROOT / "suche" / "VORAB_pine5m_abfang4h.yaml"
KEY_4H = "VORAB_pine5m_abfang4h sha256 "
ABFANG_WARTEN = pd.Timedelta(hours=4)  # so lange tut der Abfänger nichts
NACHZIEH_R = 0.5                       # danach Stop so weit hinter dem besten Kurs seit der Übernahme
NACHZIEH_SCHRITT_R = 0.05              # kleinere Verbesserungen schickt der Bot nicht (weniger Aufrufe)
HEDGING_WIEDER = pd.Timedelta(hours=1)  # schlug das Einschalten fehl, erst nach 1 Std. neu versuchen
KERZEN_MAX = 1000
LEBENSZEICHEN = pd.Timedelta(minutes=30)
GOLD_BOT_DATEIEN = sb.GOLD_BOT_DATEIEN


@dataclass(frozen=True)
class Bot:
    bot_id: str
    konto: str
    konto_name: str
    art: str                           # "hand" oder "tp3"
    name: str
    neu: bool = True                   # False: keine neuen Einstiege, nur offene Trades betreuen
    hedging: bool = False              # Long und Short gleichzeitig (Hedging-Modus des Kontos)
    gold_pruefer: bool = False         # Termin-Pause, Termin-Warnung und Hintergrund wie beim Gold-Hand-Bot
    abfang_4h: bool = False            # Abfänger erst nach 4 Std., dann Stop am besten Kurs nachziehen


BOTS = (
    Bot("pine-k5", hb.KONTO, "Account 5", "hand",
        "Pine-Gold Hand auf Account 5 (Kirons Long A und Short B auf 5 Min., Long und Short gleichzeitig, Kiron geht "
        "selbst raus)", hedging=True, gold_pruefer=True, abfang_4h=True),
    Bot("pine-tp3", "332317231899038878", "US500", "tp3",
        "Pine-Gold TP 3 € (Kirons Long A und Short B auf 5 Min., Take-Profit +3 €, ohne Stop)"),
    Bot("pine-hand", "332325912027944094", "Vortag USDJPY", "hand",
        "Pine-Gold Hand auf Vortag USDJPY (seit 10.11.2026 auf Account 5 umgezogen, betreut nur noch offene Trades)",
        neu=False),
)


def vorab_ok() -> bool:
    from suche.runde1 import journal_lines, last_value, sha256_text
    zeilen = journal_lines()
    return all(v.exists() and last_value(zeilen, k) == sha256_text(v.read_text(encoding="utf-8"))
               for v, k in ((VORAB, KEY), (VORAB_PRUEFER, KEY_PRUEFER), (VORAB_K5, KEY_K5), (VORAB_4H, KEY_4H)))


def atr_rma(bars: pd.DataFrame, n: int = ATR_N) -> pd.Series:
    c1 = bars["close"].shift(1)
    tr = pd.concat([bars["high"] - bars["low"], (bars["high"] - c1).abs(), (bars["low"] - c1).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def signale(bars: pd.DataFrame) -> pd.DataFrame:
    """Kirons A (Long) und B (Short) mit Standardwerten auf fertigen 5-Min.-Bid-Kerzen, dazu ATR(14)."""
    a, b = pp.signals_a_long(bars), pp.signals_b_short(bars)
    return pd.DataFrame({"long": a["entry"].fillna(False).astype(bool), "short": b["entry"].fillna(False).astype(bool),
                         "aus_long": a["exit"].fillna(False).astype(bool),
                         "aus_short": b["exit"].fillna(False).astype(bool), "atr": atr_rma(bars)}, index=bars.index)


def in_handelszeit(t: pd.Timestamp) -> bool:
    h = t.hour + t.minute / 60
    return STUNDEN[0] <= h < STUNDEN[1]


def r_dist(atr: float, spread: float) -> float:
    return max(R_ATR * float(atr), R_MIN_SPREAD * float(spread))


def wort(d: int) -> str:
    return "LONG" if d > 0 else "SHORT"


class Lauf:
    """Ein Lauf eines Bots auf seinem Konto. Ohne Netz testbar (client und post von außen)."""

    def __init__(self, bot: Bot, client, state: dict, now, send_orders: bool = True, post=None):
        self.bot, self.client, self.send, self.post = bot, client, send_orders, post
        self.st = copy.deepcopy(state or {})
        self.now = sb._jetzt(now)
        self.stamp = self.now.isoformat(timespec="seconds")
        self.log: list[dict] = []
        self.fertige: list[dict] = []
        self.nachrichten: list[dict] = []
        self.q = None
        for k, v in (("format", 1), ("start", self.stamp), ("offen", []), ("trades", 0), ("summe_r", 0.0),
                     ("summe_eur", 0.0)):
            self.st.setdefault(k, v)

    def ev(self, event: str, **kw) -> None:
        self.log.append({"time": self.stamp, "bot": self.bot.bot_id, "event": event, **kw})

    def melde(self, titel: str, text: str, tags: list[str]) -> None:
        self.nachrichten.append({"titel": titel, "text": text})
        if not self.send:
            self.ev("würde melden", titel=titel, text=text)
            return
        ok = hb.sende(text, titel, tags, post=self.post)
        self.ev("Nachricht", titel=titel, gesendet=ok)
        if not ok and os.environ.get("NTFY_THEMA", "").strip():
            self.st.setdefault("nachholen", []).append({"zeit": self.stamp, "titel": titel, "text": text, "tags": tags})
            self.st["nachholen"] = self.st["nachholen"][-20:]

    def nachholen(self) -> None:
        rest = []
        for m in self.st.get("nachholen", []):
            if (self.now - pd.Timestamp(m["zeit"])).total_seconds() / 3600 > hb.NACHHOLEN_STD:
                self.ev("Nachricht verworfen", titel=m["titel"], zeit=m["zeit"])
                continue
            ok = hb.sende(f"(verspätet, von {hb._berlin(pd.Timestamp(m['zeit']))})\n" + m["text"], m["titel"], m["tags"],
                          post=self.post)
            if not ok:
                rest.append(m)
        if rest:
            self.st["nachholen"] = rest
        else:
            self.st.pop("nachholen", None)

    def eur(self, d: int, entry: float, kurs: float, size: float) -> float | None:
        q = self.q
        return d * (kurs - entry) * size * (q.lot or 1.0) / q.eur_rate if q and q.eur_rate else None

    # ---- geschlossene Positionen buchen (Kiron, Take-Profit, Stop des Abfängers) ----

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
            rec = {**tr, "exit": None if level is None else round(level, 2), "quelle": quelle or "unbekannt",
                   "closed_utc": self.stamp}
            if level is not None:
                rec["r"] = round(tr["richtung"] * (level - tr["entry"]) / tr["dist"], 3)
                rec["pnl_eur"] = None if self.eur(tr["richtung"], tr["entry"], level, tr["size"]) is None else \
                    round(self.eur(tr["richtung"], tr["entry"], level, tr["size"]), 2)
                self.st["summe_r"] = round(float(self.st["summe_r"]) + rec["r"], 3)
                self.st["summe_eur"] = round(float(self.st["summe_eur"]) + float(rec["pnl_eur"] or 0), 2)
            self.st["trades"] = int(self.st["trades"]) + 1
            self.fertige.append(rec)
            self.ev("Trade zu", dealId=tr["dealId"], kurs=rec["exit"], r=rec.get("r"), eur=rec.get("pnl_eur"),
                    quelle=rec["quelle"])
            if self.bot.art == "hand" and level is not None and tr.get("abfang") and tr.get("agent") != "aus" \
                    and not (tr.get("nachzieh") or {}).get("zu"):
                nah = max(0.5, 0.1 * tr["dist"])
                stop_text = ("durch den nachgezogenen Stop des Abfängers (nächstes " + ("Hoch" if tr["richtung"] > 0
                             else "Tief") + ")") if tr.get("nachzieh") else "durch den Stop des Abfängers"
                wo = (stop_text if tr.get("stop") is not None and abs(level - tr["stop"]) <= nah
                      else "am Einstieg (Abfänger)" if tr.get("ziel") is not None and abs(level - tr["ziel"]) <= nah
                      else None)
                if wo:
                    eur = f" ({hb._de(rec['pnl_eur'])} €)" if rec.get("pnl_eur") is not None else ""
                    self.melde(f"Pine-Gold {wort(tr['richtung'])} geschlossen",
                               f"{hb._de(tr['size'])} oz von {hb._de(tr['entry'])} bei {hb._de(level)} {wo} "
                               f"geschlossen: {hb._de(rec['r'])} R{eur}.", ["stop_sign"])
        self.st["offen"] = rest

    # ---- Trade-Abfänger (nur Bot Hand) ----

    def setze(self, tr: dict, stop: float | None, ziel: float | None, warum: str) -> bool:
        body = {k: round(v, 2) for k, v in (("stopLevel", stop), ("profitLevel", ziel)) if v is not None}
        if not self.send:
            self.ev("würde setzen", dealId=tr["dealId"], **body, warum=warum)
            return False
        try:
            ref = self.client._request("PUT", f"/positions/{tr['dealId']}", json=body).json().get("dealReference")
            conf = self.client.confirm(ref) if ref else {}
        except Exception as err:            # noqa: BLE001 - nächster Lauf versucht es wieder
            self.ev("setzen fehlgeschlagen", dealId=tr["dealId"], warum=warum, fehler=str(err)[:200])
            return False
        if conf and str(conf.get("dealStatus") or "").upper() == "REJECTED":
            self.ev("setzen abgelehnt", dealId=tr["dealId"], warum=warum, grund=conf.get("reason"))
            return False
        tr["stop"], tr["ziel"] = body.get("stopLevel"), body.get("profitLevel")
        tr.setdefault("abfang", {"zeit": self.stamp, "warum": warum})
        self.ev("Abfänger gesetzt", dealId=tr["dealId"], **body, warum=warum)
        return True

    def abfaenger(self, bars: pd.DataFrame, spread: pd.Series, gold: list[dict]) -> None:
        pos = {str(p["position"].get("dealId")): p["position"] for p in gold}
        q = self.q
        abstand = max(1.05 * (q.min_dist or 0.0), 0.01)
        t = bars.index.to_numpy()
        lo, hi = bars["low"].to_numpy(float), bars["high"].to_numpy(float)
        sp = spread.reindex(bars.index).fillna(0.0).to_numpy(float)
        for tr in self.st["offen"]:
            p = pos.get(tr["dealId"])
            if p is None or tr.get("agent") == "aus":
                continue
            d, e, r = int(tr["richtung"]), float(tr["entry"]), float(tr["dist"])
            kopf = f"{wort(d)} {hb._de(tr['size'])} oz von {hb._de(e)}"
            jetzt = q.bid if d > 0 else q.offer
            b_stop, b_ziel = hb._num(p.get("stopLevel")), hb._num(p.get("profitLevel"))
            if tr.get("abfang"):
                if hb._anders(b_stop, tr.get("stop")) or hb._anders(b_ziel, tr.get("ziel")):
                    self._aus(tr, kopf, b_stop, b_ziel)
                elif tr.get("nachzieh"):
                    self.nachziehen(tr, kopf, bars, spread, jetzt, abstand)
                continue
            if b_stop is not None or b_ziel is not None:
                self._aus(tr, kopf, b_stop, b_ziel)
                continue
            if self.bot.abfang_4h:
                if self.now - pd.Timestamp(tr["opened_utc"]).tz_localize(None) < ABFANG_WARTEN:
                    continue                                   # die ersten 4 Std. geht Kiron selbst raus
                tr["nachzieh"] = {"seit": self.stamp, "bestes": round(float(jetzt), 2)}
                tr["abfang"] = {"zeit": self.stamp, "warum": "4 Std. ohne Ausstieg"}
                self.ev("Abfänger übernimmt", dealId=tr["dealId"], kurs=round(float(jetzt), 2))
                r_jetzt = d * (jetzt - e) / r
                eur = self.eur(d, e, jetzt, tr["size"])
                self.melde("Pine-Gold: Abfänger übernimmt",
                           f"{kopf}: seit 4 Std. offen, du bist nicht raus. Kurs {hb._de(jetzt)} ({hb._de(r_jetzt)} R"
                           + (f", {hb._de(eur)} €" if eur is not None else "") + "). Ab jetzt hält der Abfänger den "
                           f"Stop 0,5 R ({hb._de(NACHZIEH_R * r)} $) hinter dem besten Kurs und zieht ihn nach. So "
                           f"schließt der Trade am nächsten {'Hoch' if d > 0 else 'Tief'}: im Plus mit möglichst viel "
                           f"Gewinn, im Minus mit möglichst wenig Verlust. Du kannst weiter selbst raus. Setzt du "
                           f"Stop oder Ziel selbst, lässt er die Position in Ruhe.", ["shield"])
                self.nachziehen(tr, kopf, bars, spread, jetzt, abstand)
                continue
            j0 = int(np.searchsorted(t, np.datetime64(pd.Timestamp(tr["opened_utc"]).tz_localize(None).floor("5min"))))
            if d > 0:
                gegen, dafuer = np.r_[lo[j0:], q.bid], np.r_[hi[j0:], q.bid]
                kf, kz = hb._erst(gegen <= e - FEHL_R * r), hb._erst(dafuer >= e + ZIEL1_R * r)
            else:
                gegen, dafuer = np.r_[hi[j0:] + sp[j0:], q.offer], np.r_[lo[j0:] + sp[j0:], q.offer]
                kf, kz = hb._erst(gegen >= e + FEHL_R * r), hb._erst(dafuer <= e - ZIEL1_R * r)
            minus_r = d * (e - jetzt) / r
            fehl = kf >= 0 and not (0 <= kz < kf)
            if not fehl and minus_r < 1.0:
                continue
            stop = e - d * r
            if d * (jetzt - stop) <= abstand:              # schon hinter 1 R: Notbremse 0,5 R hinter dem Kurs
                stop = jetzt - d * 0.5 * r
            ziel = e if fehl and d * (e - jetzt) > abstand else None
            warum = "Fehltrade (0,5 R dagegen vor Ziel 1)" if fehl else "Notbremse (1 R im Minus)"
            if self.setze(tr, stop, ziel, warum):
                text = f"{kopf}: {warum}. Kurs {hb._de(jetzt)}. Stop jetzt bei {hb._de(stop)}"
                text += (f", Ziel auf dem Einstieg {hb._de(e)}, damit der Trade bei null endet, wenn der Kurs "
                         f"zurückkommt." if ziel is not None else ".")
                self.melde("Pine-Gold: Abfänger greift", text + " Raus gehst du weiter selbst.", ["shield"])

    def nachziehen(self, tr: dict, kopf: str, bars: pd.DataFrame, spread: pd.Series, jetzt: float,
                   abstand: float) -> None:
        """Stop 0,5 R hinter dem besten Kurs seit der Übernahme (Long: höchster Bid, Short: tiefster Ask), nur in
        Richtung des Trades. Ist der Kurs schon so weit zurück, dass der Stop nicht mehr vor den Kurs passt: sofort raus."""
        nz = tr["nachzieh"]
        if nz.get("zu"):                    # schon geschlossen, aber noch offen beim Broker: nochmal, ohne Nachricht
            self.schliessen(tr, kopf, jetzt, float(nz["bestes"]))
            return
        d, r = int(tr["richtung"]), float(tr["dist"])
        t0 = pd.Timestamp(nz["seit"]).tz_localize(None).ceil("5min")     # nur Kerzen, die nach der Übernahme begannen
        k0 = int(np.searchsorted(bars.index.to_numpy(), np.datetime64(t0)))
        if d > 0:
            kurse = np.r_[bars["high"].to_numpy(float)[k0:], jetzt]
            bestes = max(float(nz["bestes"]), float(kurse.max()))
        else:
            sp = spread.reindex(bars.index).fillna(0.0).to_numpy(float)[k0:]
            kurse = np.r_[bars["low"].to_numpy(float)[k0:] + sp, jetzt]
            bestes = min(float(nz["bestes"]), float(kurse.min()))
        nz["bestes"] = round(bestes, 2)
        soll = round(bestes - d * NACHZIEH_R * r, 2)
        if d * (jetzt - soll) <= abstand:
            self.schliessen(tr, kopf, jetzt, bestes)
            return
        alt = tr.get("stop")
        if alt is not None and d * (soll - alt) < NACHZIEH_SCHRITT_R * r:
            return
        if self.setze(tr, soll, None, "nachziehen (0,5 R hinter dem besten Kurs)"):
            nz["stop_seit"] = self.stamp

    def schliessen(self, tr: dict, kopf: str, jetzt: float, bestes: float) -> None:
        if not self.send:
            self.ev("würde schließen (Abfänger)", dealId=tr["dealId"], kurs=round(float(jetzt), 2))
            return
        try:
            conf = self.client.close_position(tr["dealId"])
        except Exception as err:            # noqa: BLE001 - nächster Lauf versucht es wieder
            self.ev("schließen fehlgeschlagen", dealId=tr["dealId"], fehler=str(err)[:200])
            return
        if str((conf or {}).get("dealStatus") or "").upper() == "REJECTED":
            self.ev("schließen abgelehnt", dealId=tr["dealId"], grund=(conf or {}).get("reason"))
            return
        erst = not tr["nachzieh"].get("zu")
        tr["nachzieh"]["zu"] = self.stamp
        if not erst:
            self.ev("Abfänger schließt nochmal", dealId=tr["dealId"])
            return
        d = int(tr["richtung"])
        r_jetzt = d * (jetzt - tr["entry"]) / tr["dist"]
        eur = self.eur(d, tr["entry"], jetzt, tr["size"])
        self.ev("Abfänger schließt", dealId=tr["dealId"], kurs=round(float(jetzt), 2), bestes=round(bestes, 2))
        self.melde(f"Pine-Gold {wort(d)} geschlossen",
                   f"{kopf}: Der Kurs ist 0,5 R vom besten Kurs {hb._de(bestes)} zurückgelaufen. Der Abfänger hat bei "
                   f"etwa {hb._de(jetzt)} geschlossen: {hb._de(r_jetzt)} R"
                   + (f" ({hb._de(eur)} €)" if eur is not None else "") + ".", ["stop_sign"])

    def _aus(self, tr: dict, kopf: str, b_stop, b_ziel) -> None:
        tr["agent"] = "aus"
        self.ev("Abfänger aus", dealId=tr["dealId"], stop=b_stop, ziel=b_ziel)
        self.melde("Pine-Gold: Abfänger lässt die Position in Ruhe",
                   f"{kopf}: Du hast Stop oder Ziel selbst gesetzt oder geändert (Stop "
                   f"{hb._de(b_stop) if b_stop else 'keiner'}, Ziel {hb._de(b_ziel) if b_ziel else 'keins'}). "
                   f"Der Abfänger ändert an dieser Position nichts mehr.", ["information_source"])

    def ausstieg_hinweis(self, sig: pd.DataFrame, neue: list[pd.Timestamp]) -> None:
        """Pine würde jetzt raus: einmal je Position, beim ersten Ausstiegssignal ihrer Seite nach dem Einstieg."""
        for d, spalte in ((1, "aus_long"), (-1, "aus_short")):
            for t in neue:
                if not bool(sig.at[t, spalte]):
                    continue
                trs = [tr for tr in self.st["offen"] if tr["richtung"] == d and not tr.get("hinweis")
                       and pd.Timestamp(tr["opened_utc"]).tz_localize(None).floor("5min") <= t]
                if not trs:
                    continue
                kurs = self.q.bid if d > 0 else self.q.offer
                zeilen = []
                for tr in trs:
                    tr["hinweis"] = self.stamp
                    eur = self.eur(d, tr["entry"], kurs, tr["size"])
                    zeilen.append(f"{hb._de(tr['size'])} oz von {hb._de(tr['entry'])}: "
                                  f"{hb._de(d * (kurs - tr['entry']) / tr['dist'])} R"
                                  + (f" ({hb._de(eur)} €)" if eur is not None else ""))
                self.ev("Pine-Ausstieg", richtung=d, kerze=str(t), deals=[tr["dealId"] for tr in trs])
                self.melde(f"Pine-Gold: Strategie würde {wort(d)} schließen",
                           f"Die Pine-Strategie gibt auf der 5-Min.-Kerze bis {hb._berlin(t + KERZE)} Uhr ihr "
                           f"Ausstiegssignal. Kurs {hb._de(kurs)}. Offen: " + "; ".join(zeilen) +
                           ". Der Bot schließt nicht selbst, du entscheidest.", ["bell"])

    # ---- Prüfer (nur Bot TP 3 €) ----

    def pruefer(self, bars: pd.DataFrame, spread: pd.Series, gold: list[dict]) -> None:
        """Erst 3 Std. nichts. Danach einmal je Position: lag der Trade seit dem Einstieg 0,5 R im Minus (Fehltrade),
        Stop 1 R hinter dem Einstieg (liegt der Kurs schon dahinter: 0,5 R hinter den Kurs) und, wenn der Kurs unter dem
        Einstieg liegt, Ziel auf den Einstieg. Nach 24 Std. ohne Eingriff: im Plus sofort raus, sonst wie Fehltrade.
        Ändert jemand Stop oder Ziel von Hand, lässt der Prüfer die Position in Ruhe."""
        pos = {str(p["position"].get("dealId")): p["position"] for p in gold}
        q = self.q
        abstand = max(1.05 * (q.min_dist or 0.0), 0.01)
        t = bars.index.to_numpy()
        lo, hi = bars["low"].to_numpy(float), bars["high"].to_numpy(float)
        sp = spread.reindex(bars.index).fillna(0.0).to_numpy(float)
        for tr in list(self.st["offen"]):
            p = pos.get(tr["dealId"])
            if p is None or tr.get("pruefer") or tr.get("agent") == "aus":
                continue
            b_stop, b_ziel = hb._num(p.get("stopLevel")), hb._num(p.get("profitLevel"))
            if b_stop is not None or hb._anders(b_ziel, tr.get("tp")):
                tr["agent"] = "aus"
                self.ev("Prüfer aus", dealId=tr["dealId"], stop=b_stop, ziel=b_ziel)
                continue
            offen_seit = pd.Timestamp(tr["opened_utc"]).tz_localize(None)
            alter = self.now - offen_seit
            if alter < PRUEF_WARTEN:
                continue
            d, e, r = int(tr["richtung"]), float(tr["entry"]), float(tr["dist"])
            jetzt = q.bid if d > 0 else q.offer
            j0 = int(np.searchsorted(t, np.datetime64(offen_seit.floor("5min"))))
            gegen = np.r_[lo[j0:], jetzt] if d > 0 else np.r_[hi[j0:] + sp[j0:], jetzt]
            fehl = bool((d * (e - gegen) >= FEHL_R * r).any())
            lang = alter >= PRUEF_LANG
            if not (fehl or lang):
                continue
            if not fehl and d * (jetzt - e) >= 0:
                if not self.send:
                    self.ev("würde schließen (langes Warten)", dealId=tr["dealId"])
                    continue
                try:
                    self.client.close_position(tr["dealId"])
                except Exception as err:        # noqa: BLE001 - nächster Lauf versucht es wieder
                    self.ev("schließen fehlgeschlagen", dealId=tr["dealId"], fehler=str(err)[:200])
                    continue
                tr["pruefer"] = {"zeit": self.stamp, "warum": "langes Warten, im Plus raus"}
                self.ev("Prüfer schließt", dealId=tr["dealId"], warum="langes Warten (24 Std.), im Plus")
                continue
            stop = e - d * PRUEF_STOP_R * r
            if d * (jetzt - stop) <= abstand:
                stop = jetzt - d * 0.5 * r
            ziel = e if d * (e - jetzt) > abstand else tr.get("tp")
            warum = "Fehltrade (0,5 R im Minus)" if fehl else "langes Warten (24 Std.)"
            if self.setze(tr, stop, ziel, warum):
                tr["tp"] = tr["ziel"]
                tr["pruefer"] = {"zeit": self.stamp, "warum": warum}
                self.ev("Prüfer greift", dealId=tr["dealId"], stop=round(stop, 2), ziel=tr["ziel"], warum=warum)

    # ---- Notausstieg (nur Bot TP 3 €) ----

    def notausstieg(self, gold: list[dict]) -> None:
        if NOT_AUS_EUR is None:
            return
        meine = {tr["dealId"]: tr for tr in self.st["offen"]}
        offen = [p for p in gold if str(p["position"].get("dealId")) in meine]
        if not offen:
            return
        summe = 0.0
        for p in offen:
            tr = meine[str(p["position"]["dealId"])]
            kurs = self.q.bid if tr["richtung"] > 0 else self.q.offer
            summe += self.eur(tr["richtung"], tr["entry"], kurs, tr["size"]) or 0.0
        if summe > -NOT_AUS_EUR:
            return
        self.ev("Notausstieg", offen_eur=round(summe, 2), deals=list(meine))
        if not self.send:
            return
        for p in offen:
            with contextlib.suppress(Exception):
                self.client.close_position(str(p["position"]["dealId"]))
        self.melde("Pine-Gold TP 3 €: Notausstieg",
                   f"Die {len(offen)} offenen Trades des TP-Bots lagen zusammen bei {hb._de(summe)} € (Grenze "
                   f"-{NOT_AUS_EUR:.0f} €). Er hat sie geschlossen, damit die anderen Bots auf dem Konto "
                   f"„{self.bot.konto_name}“ genug Marge behalten, und fängt mit dem nächsten Signal neu an.", ["warning"])

    # ---- Hedging und Gold-Prüfer (nur pine-k5) ----

    def hedging_an(self) -> bool:
        """Ist der Hedging-Modus des aktiven Kontos an? Wenn nicht, einmal einschalten (Kirons Wort vom 10.11.2026
        07:29 UTC: Long und Short gleichzeitig). Schlägt das fehl, gilt "nie gegen die Gegenrichtung", und der Bot
        versucht es frühestens nach 1 Std. wieder."""
        try:
            an = bool((self.client._get("/accounts/preferences") or {}).get("hedgingMode"))
        except Exception as err:            # noqa: BLE001 - dann ohne Hedging
            self.ev("Hedging nicht lesbar", fehler=str(err)[:200])
            return False
        if an:
            self.st["hedging"] = True
            self.st.pop("hedging_fehler", None)
            return True
        if self.st.get("hedging"):
            self.ev("Hedging ist aus")      # jemand hat es ausgeschaltet: wieder einschalten wie beim ersten Mal
            self.st["hedging"] = False
        if not self.send:
            self.ev("würde Hedging einschalten")
            return False
        letzt = self.st.get("hedging_versuch")
        if letzt and self.now - pd.Timestamp(letzt) < HEDGING_WIEDER:
            return False
        self.st["hedging_versuch"] = self.stamp
        try:
            self.client._request("PUT", "/accounts/preferences", json={"hedgingMode": True})
            an = bool((self.client._get("/accounts/preferences") or {}).get("hedgingMode"))
            fehler = None if an else "Capital.com meldet den Hedging-Modus weiter als aus"
        except Exception as err:            # noqa: BLE001
            an, fehler = False, str(err)[:200]
        if an:
            self.st["hedging"] = True
            self.st.pop("hedging_fehler", None)
            self.ev("Hedging eingeschaltet")
            self.melde("Pine-Gold: Hedging an",
                       f"Auf „{self.bot.konto_name}“ ist jetzt der Hedging-Modus an. Long und Short in Gold können "
                       f"gleichzeitig offen sein, eine Gegen-Order schließt die alte Position nicht mehr. Schließ "
                       f"Positionen in der App einzeln.", ["information_source"])
            return True
        self.ev("Hedging einschalten fehlgeschlagen", fehler=fehler)
        if not self.st.get("hedging_fehler"):
            self.melde("Pine-Gold: Hedging nicht eingeschaltet",
                       f"Capital.com hat den Hedging-Modus auf „{self.bot.konto_name}“ nicht eingeschaltet ({fehler}). "
                       f"Bis es klappt, öffnet der Bot nichts gegen eine offene Goldposition. Er versucht es jede "
                       f"Stunde wieder.", ["warning"])
        self.st["hedging_fehler"] = self.stamp
        return False

    def warne(self, gold: list[dict]) -> None:
        """Bis 45 Min. vor einem wichtigen US-Termin einmal warnen, wenn Gold offen ist (wie der Gold-Hand-Bot)."""
        if not gold:
            return
        try:
            ev = hb.alle_termine(self.st, self.now)
        except Exception as err:            # noqa: BLE001
            self.ev("Termine nicht lesbar", fehler=str(err)[:120])
            return
        gewarnt = list(self.st.get("gewarnt") or [])
        bald = [(t, s) for t, s in ev if self.now < t <= self.now + hb.WARN_VOR and f"{t.isoformat()} {s}" not in gewarnt]
        if not bald:
            return
        n_s = sum(1 for p in gold if hb.richtung(p) < 0)
        was = ", ".join(f"{s} um {hb._berlin(t)} Uhr" for t, s in bald)
        self.melde("Pine-Gold: wichtiger Termin bald",
                   f"{was}. Auf „{self.bot.konto_name}“ sind {n_s} Short und {len(gold) - n_s} Long in Gold offen. Der "
                   f"Kurs kann dann stark springen. Jetzt prüfen, ob du rausgehen willst.", ["warning"])
        self.st["gewarnt"] = (gewarnt + [f"{t.isoformat()} {s}" for t, s in bald])[-50:]

    # ---- Einstiege ----

    def einstiege(self, sig: pd.DataFrame, spread: pd.Series, neue: list[pd.Timestamp], gold: list[dict],
                  available: float | None, hedge: bool = False) -> None:
        q = self.q
        for t in neue:
            ende = t + KERZE
            lang, kurz = bool(sig.at[t, "long"]), bool(sig.at[t, "short"])
            if not (lang or kurz) or not in_handelszeit(t):
                continue
            seiten = {1 if hb.richtung(p) > 0 else -1 for p in gold}
            if lang and kurz:
                if len(seiten) != 1:
                    self.ev("widersprüchliches Signal", kerze=str(t))
                    continue
                d = seiten.pop()
            else:
                d = 1 if lang else -1
            info = {"richtung": d, "kerze": str(t), "strategie": "A Long" if d > 0 else "B Short"}
            gruende, still = [], False
            if self.now - ende > FRISCH:
                gruende.append("Signal zu alt")
                still = True
            if not vorab_ok():
                gruende.append("VORAB_pine5m.yaml nicht festgelegt")
                still = True
            if not q.tradeable:
                gruende.append("Markt zu")
            if not hedge and any(hb.richtung(p) != d for p in gold):
                gruende.append("eine Goldposition in die andere Richtung ist offen")
                still = True
            if len(gold) >= MAX_OFFEN:
                gruende.append(f"schon {MAX_OFFEN} Goldpositionen offen")
                still = True
            lage = ""
            if self.bot.gold_pruefer and not still:
                try:
                    nl = hb.news_lage(self.st, self.now)
                except Exception as err:    # noqa: BLE001 - ohne Termine keine Sperre
                    nl = {"pause": False, "gruende": [], "naechster": None}
                    self.ev("Termine nicht lesbar", fehler=str(err)[:120])
                if nl["pause"]:
                    gruende.append("News-Pause: " + ", ".join(nl["gruende"]))
                hg = hb.hintergrund(self.client, self.now)
                info["hintergrund"] = hg
                if hg.get("richtung") == -d:
                    gruende.append("gegen den Hintergrund (" + ("Gold steigt" if d < 0 else "Gold fällt")
                                   + " auf Tag und 4 Std.)")
                    still = True        # kommt oft vor: nur im Journal, keine Nachricht
                lage = hb.hg_text(hg) + (f" Nächster wichtiger Termin: {nl['naechster']}." if nl.get("naechster")
                                         else "")
                if hedge and any(hb.richtung(p) != d for p in gold):
                    lage += " Gegenposition offen, mit Hedging erlaubt."
            info["lage"] = lage
            atr = float(sig.at[t, "atr"])
            sp = float(spread.get(t, q.offer - q.bid))
            if not np.isfinite(atr):
                gruende.append("ATR noch nicht gefüllt")
                still = True
            dist = r_dist(atr if np.isfinite(atr) else 0.0, sp)
            kurs = q.offer if d > 0 else q.bid
            sizes, warum = sb.groessen(dist, q, (1.0,))
            if sizes is None:
                gruende.append(warum)
            else:
                marge_neu = sizes[0] * (q.lot or 1) * kurs * q.margin_pct / 100 / (q.eur_rate or 1)
                meine = {tr["dealId"] for tr in self.st["offen"]}
                marge_alt = sum(float(hb._num(p["position"].get("size")) or 0) * (q.lot or 1) * kurs * q.margin_pct
                                / 100 / (q.eur_rate or 1) for p in gold if str(p["position"].get("dealId")) in meine)
                if marge_alt + marge_neu > MARGE_MAX_EUR:
                    gruende.append(f"mehr als {MARGE_MAX_EUR:.0f} € Marge für diesen Bot")
                if available is not None and available - marge_neu < FREI_NACH_EUR:
                    gruende.append(f"danach weniger als {FREI_NACH_EUR:.0f} € frei für die anderen Bots "
                                   f"({available:.0f} € frei)")
            if gruende:
                self.ev("ausgelassen", **info, gruende=gruende)
                if self.bot.art == "hand" and not still:
                    self.melde(f"Pine-Gold {wort(d)}, nicht eröffnet",
                               f"Grund: {'; '.join(gruende)}. Kurs {hb._de(kurs)}. Signal der 5-Min.-Kerze bis "
                               f"{hb._berlin(ende)} Uhr. Du kannst selbst entscheiden.", ["warning"])
                continue
            tp = None
            if self.bot.art == "tp3":
                abst = max(TP_EUR * q.eur_rate / (sizes[0] * (q.lot or 1)), 1.05 * (q.min_dist or 0.0))
                tp = round(kurs + d * abst, 2)
            if not self.send:
                self.ev("würde öffnen", **info, size=sizes[0], kurs=kurs, tp=tp, dist=round(dist, 2))
                continue
            neu = self.oeffnen(d, sizes[0], tp, kurs, dist, info, gold)
            if neu is None:
                continue
            gold.append(neu)
            if available is not None:
                available -= sizes[0] * (q.lot or 1) * kurs * q.margin_pct / 100 / (q.eur_rate or 1)

    def oeffnen(self, d: int, size: float, tp: float | None, kurs: float, dist: float, info: dict,
                gold: list[dict]) -> dict | None:
        q = self.q
        vorher = {str(p["position"].get("dealId")) for p in gold}
        body = {"epic": EPIC, "direction": "BUY" if d > 0 else "SELL", "size": size, "guaranteedStop": False}
        if tp is not None:
            body["profitLevel"] = tp
        try:
            ref = self.client._request("POST", "/positions", json=body).json()["dealReference"]
            conf = self.client.confirm(ref)
        except Exception as err:                    # noqa: BLE001 - kein zweiter Versuch, damit nichts doppelt entsteht
            self.ev("Order fehlgeschlagen", **info, fehler=str(err)[:200])
            if self.bot.art == "hand":
                self.melde(f"Pine-Gold {wort(d)}: Order fehlgeschlagen", f"{err}"[:200], ["x"])
            return None
        if str((conf or {}).get("dealStatus") or "").upper() == "REJECTED":
            self.ev("Order abgelehnt", **info, grund=(conf or {}).get("reason"))
            if self.bot.art == "hand":
                self.melde(f"Pine-Gold {wort(d)}: Order abgelehnt", f"Grund: {(conf or {}).get('reason')}.", ["x"])
            return None
        neu = [p for p in self.client.positions() if (p.get("market") or {}).get("epic") == EPIC
               and str(p["position"].get("dealId")) not in vorher]
        pos = neu[0]["position"] if len(neu) == 1 else {}
        deal = str(pos.get("dealId") or ((conf or {}).get("affectedDeals") or [{}])[0].get("dealId")
                   or (conf or {}).get("dealId"))
        level = hb._num(pos.get("level")) or hb._num((conf or {}).get("level")) or kurs
        tr = {"dealId": deal, "richtung": d, "size": size, "entry": round(level, 2), "dist": round(dist, 2),
              "einstieg_kerze": info["kerze"], "strategie": info["strategie"], "opened_utc": self.stamp}
        if tp is not None:
            # Ziel genau 3 € über dem echten Einstieg (die Order kannte nur den Kurs davor)
            soll = round(level + d * (abs(tp - kurs)), 2)
            tr["tp"] = tp
            if abs(soll - tp) > hb.STOP_TOL:
                with contextlib.suppress(Exception):
                    ref = self.client._request("PUT", f"/positions/{deal}", json={"profitLevel": soll}).json()
                    c = self.client.confirm(ref.get("dealReference")) if ref.get("dealReference") else {}
                    if str((c or {}).get("dealStatus") or "ACCEPTED").upper() != "REJECTED":
                        tr["tp"] = soll
        self.st["offen"].append(tr)
        self.ev("eröffnet", **info, dealId=deal, size=size, entry=tr["entry"], tp=tr.get("tp"))
        if self.bot.art == "hand":
            stop1, fehl, ziel1 = level - d * dist, level - d * FEHL_R * dist, level + d * ZIEL1_R * dist
            abfang = (f"Bist du nach 4 Std. (um {hb._berlin(self.now + ABFANG_WARTEN)} Uhr) noch drin, übernimmt "
                      f"der Abfänger: Stop 0,5 R ({hb._de(NACHZIEH_R * dist)} $) hinter dem besten Kurs, nachgezogen, "
                      f"raus am nächsten {'Hoch' if d > 0 else 'Tief'}." if self.bot.abfang_4h else
                      f"Läuft er 0,5 R gegen dich ({hb._de(fehl)}), bevor {hb._de(ziel1)} kommt, setzt der Abfänger "
                      f"Stop {hb._de(stop1)} (1 R = {hb._de(dist)} $ = etwa 5 €) und Ziel auf den Einstieg.")
            self.melde(f"Pine-Gold {wort(d)} eröffnet",
                       f"{self.bot.konto_name} (Demo): {hb._de(size)} oz bei {hb._de(level)}, Strategie "
                       f"{info['strategie']}, 5-Min.-Kerze bis {hb._berlin(pd.Timestamp(info['kerze']) + KERZE)} Uhr. "
                       f"Ohne Stop und ohne Ziel, raus gehst du selbst. " + abfang +
                       (f" {info['lage']}" if info.get("lage") else ""),
                       ["chart_with_upwards_trend" if d > 0 else "chart_with_downwards_trend"])
        return {"market": {"epic": EPIC}, "position": {"dealId": deal, "direction": body["direction"], "size": size,
                                                       "level": level}}


def neue_kerzen(bars: pd.DataFrame, letzte: str | None) -> list[pd.Timestamp]:
    """Fertige Kerzen nach der zuletzt gesehenen. Beim ersten Lauf nur die letzte."""
    if bars.empty:
        return []
    if not letzte:
        return [bars.index[-1]]
    return [t for t in bars.index if t > pd.Timestamp(letzte)]


def lauf_bot(bot: Bot, client, state: dict, now, bars: pd.DataFrame, spread: pd.Series, sig: pd.DataFrame,
             send_orders: bool = True, post=None):
    from suche.demo_bots import eur_rate, quote_from_market

    lauf = Lauf(bot, client, state, now, send_orders, post)
    if send_orders and lauf.st.get("nachholen"):
        lauf.nachholen()
    if not bot.neu and not lauf.st["offen"]:
        return lauf.st, lauf.log, [], []          # ausgelaufen: nichts mehr zu betreuen, nichts abfragen
    konto = next((a for a in client.accounts() if str(a.get("accountId")) == bot.konto), None)
    if konto is None or bot.konto.endswith(HAUPT_ENDUNG):
        lauf.ev("kein Konto", konto="…" + bot.konto[-4:])
        return lauf.st, lauf.log, [], []
    available = hb._num((konto.get("balance") or {}).get("available"))
    vorher = client.account_id
    client.switch_account(bot.konto)
    try:
        aktiv = aktives_konto(client)
        if aktiv is not None and aktiv != bot.konto:
            lauf.ev("anderes Konto aktiv, nichts getan", aktiv="…" + aktiv[-4:])
            return lauf.st, lauf.log, [], []
        lauf.q = q = quote_from_market(client.market(EPIC), None)
        q.eur_rate = eur_rate(client, q.currency, {})
        gold = [p for p in client.positions() if (p.get("market") or {}).get("epic") == EPIC]
        lauf.abgleich(gold)
        neue = neue_kerzen(bars, lauf.st.get("letzte_kerze"))
        hedge = lauf.hedging_an() if bot.hedging and bot.neu else False
        if bot.art == "hand":
            lauf.abfaenger(bars, spread, gold)
            lauf.ausstieg_hinweis(sig, neue)
            if bot.gold_pruefer:
                lauf.warne(gold)
        else:
            lauf.pruefer(bars, spread, gold)
            lauf.notausstieg(gold)
            if send_orders and any(e["event"] == "Notausstieg" for e in lauf.log):
                gold = [p for p in client.positions() if (p.get("market") or {}).get("epic") == EPIC]
                lauf.abgleich(gold)
        if bot.neu:
            lauf.einstiege(sig, spread, neue, gold, available, hedge)
        if neue:
            lauf.st["letzte_kerze"] = str(neue[-1])
        lauf.st["letzter_kurs"] = round(float(q.bid), 2)
        lauf.st["stand"] = lauf.stamp
        return lauf.st, lauf.log, lauf.fertige, lauf.nachrichten
    finally:
        with contextlib.suppress(Exception):
            if vorher and vorher != bot.konto:
                client.switch_account(vorher)


def aktives_konto(client) -> str | None:
    """Welches Konto ist in dieser Sitzung aktiv (GET /session)? Zusätzliche Sicherung, weil dieser Lauf neben den
    anderen Bot-Läufen eine eigene Sitzung hat. None, wenn Capital.com es nicht sagt."""
    try:
        aid = (client._get("/session") or {}).get("accountId")
    except Exception:                   # noqa: BLE001 - dann gilt der eigene Wechsel
        return None
    return str(aid) if aid else None


def kerzen(client, now) -> tuple[pd.DataFrame, pd.Series]:
    from gold.bot.rules import bars_from_prices
    return bars_from_prices(client.prices(EPIC, "MINUTE_5", KERZEN_MAX), now, "5min")


START_TEXT = ("Der Pine-Gold-Hand-Bot handelt ab jetzt auf Account 5: deine Strategien A (Long) und B (Short) auf "
              "5-Min.-Gold-Kerzen, 8 bis 21 Uhr deutscher Zeit, Long und Short auch gleichzeitig (Hedging). Er meldet "
              "jeden Einstieg ohne Stop und Ziel, macht vor wichtigen US-Terminen Pause, nimmt nichts gegen den "
              "Hintergrund (Tag und 4 Std.) und greift mit dem Trade-Abfänger ein. Eine Sperre nach Kurssprüngen gibt "
              "es nicht. Rausgehen machst du selbst. Der Box-Bot auf Account 5 nimmt keine neuen Trades mehr, auf "
              "„Vortag USDJPY“ kommen keine neuen Pine-Trades mehr. Der TP-Bot auf „US500“ bleibt, wie er ist.")
START_BOT = "pine-k5"


def cockpit(bot: Bot, st: dict, alle: list[dict]) -> dict:
    r = [float(t["r"]) for t in alle if t.get("r") is not None]
    regel = ("Kirons Pine A (Long) und B (Short) auf 5-Min.-Gold-Kerzen, Standardwerte, Einstiege 7 bis 20 Uhr UTC, "
             "1 R = 3 x ATR(14), 5 € je R, höchstens 4 Goldpositionen, "
             + ("Long und Short gleichzeitig erlaubt (Hedging). " if bot.hedging else "nie gegen die Gegenrichtung. "))
    if bot.gold_pruefer:
        regel += ("Gold-Prüfer: keine Einstiege 60 Min. vor bis 30 Min. nach wichtigen US-Terminen (keine Sperre nach "
                  "Kurssprüngen), nichts gegen den Hintergrund (Tag über SMA 50 und 4 Std. über EMA 50). ")
    if not bot.neu:
        regel = "Seit 10.11.2026 auf Account 5 umgezogen, hier keine neuen Einstiege mehr. " + regel
    regel += ("Ohne Stop und Ziel, Kiron geht selbst raus. Trade-Abfänger (seit 10.11.2026): die ersten 4 Std. "
              "nichts, danach Stop 0,5 R hinter dem besten Kurs, nur nachgezogen (raus am nächsten Hoch bzw. Tief). "
              "Hinweis beim Pine-Ausstiegssignal."
              if bot.art == "hand" and bot.abfang_4h else
              "Ohne Stop und Ziel, Kiron geht selbst raus. Trade-Abfänger: Fehltrade (0,5 R dagegen vor 0,75 R dafür) "
              "Stop 1 R und Ziel am Einstieg, Notbremse ab 1 R Minus. Hinweis beim Pine-Ausstiegssignal."
              if bot.art == "hand" else
              "Take-Profit +3 €, kein Stop beim Einstieg. Prüfer: erst 3 Std. nichts, dann bei Fehltrade (0,5 R im "
              "Minus seit dem Einstieg) Stop 1 R und Ziel am Einstieg, nach 24 Std. im Plus raus. Äußerste Grenze: "
              f"Notausstieg aller eigenen Trades bei zusammen -{NOT_AUS_EUR:.0f} €.")
    return {"bot": bot.bot_id, "name": bot.name, "konto": "…" + bot.konto[-4:], "konto_name": bot.konto_name,
            "stand": st.get("stand"), "start": st.get("start"), "regel": regel,
            "vorab": ("suche/VORAB_pine5m_abfang4h.yaml" if bot.abfang_4h else "suche/VORAB_pine5m_konto5.yaml"
                      if bot.gold_pruefer else "suche/VORAB_pine5m.yaml"),
            "test": ("nicht bestanden (Gewinnfaktor 1,09 mit Hedging, Termin-Pause und Hintergrund, Kontrolle 2022-24 "
                     "0,76)" if bot.gold_pruefer else
                     "nicht bestanden (Gold bester Markt, Gewinnfaktor 1,05 mit Abfänger, Kontrolle 2022-24 0,72)"),
            "offen": st.get("offen", []),
            "zusammenfassung": {"trades": len(alle), "pf_r": sb.ts.pf(r) if r else None, "summe_r": round(sum(r), 2),
                                "summe_eur": round(sum(float(t.get("pnl_eur") or 0) for t in alle), 2),
                                "urteil": "Demo-Vorwärtstest, Urteil nach 40 Trades"},
            "letzte_trades": alle[-10:]}


def _ohne_stand(st: dict) -> dict:
    return {k: v for k, v in st.items() if k not in ("stand", "letzte_kerze", "letzter_kurs")}


def schreiben(bot: Bot, alt: dict, st: dict, log: list[dict], fertige: list[dict], nachrichten: list[dict],
              root: Path = ROOT) -> bool:
    """Nur eigene Dateien. Ohne Neues höchstens alle 30 Min. ein Lebenszeichen (weniger Commits)."""
    jdir, pfad = root / "journal" / bot.bot_id, root / "journal" / f"{bot.bot_id}.json"
    for p in (jdir, pfad):
        if p.name in GOLD_BOT_DATEIEN or p.name.startswith(("gold-", "gold.")):
            raise RuntimeError(f"{p} gehört einem anderen Bot")
    still = not log or all(e["event"] in ("ausgelassen",) and "Signal zu alt" in e.get("gruende", []) for e in log)
    if alt and still and not fertige and not nachrichten and _ohne_stand(alt) == _ohne_stand(st) and alt.get("stand"):
        if pd.Timestamp(st["stand"]) - pd.Timestamp(alt["stand"]) < LEBENSZEICHEN:
            return False
    jdir.mkdir(parents=True, exist_ok=True)
    (jdir / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for name, rows in (("log.jsonl", log), ("trades.jsonl", fertige),
                       ("nachrichten.jsonl", [{"time": st.get("stand"), **m} for m in nachrichten])):
        if rows:
            with open(jdir / name, "a", encoding="utf-8") as fh:
                fh.writelines(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows)
    alle = sb._lies_jsonl(jdir / "trades.jsonl")
    pfad.write_text(json.dumps(cockpit(bot, st, alle), ensure_ascii=False, indent=1, default=str) + "\n",
                    encoding="utf-8")
    return True


def run(client, states: dict, now, send_orders: bool = True, post=None) -> dict:
    """Ein Lauf beider Bots mit denselben Kerzen. Rückgabe je Bot (state, log, fertige, nachrichten)."""
    bars, spread = kerzen(client, now)
    out = {}
    if len(bars) < 200:
        for bot in BOTS:
            out[bot.bot_id] = (copy.deepcopy(states.get(bot.bot_id) or {}),
                               [{"time": str(now), "bot": bot.bot_id, "event": "zu wenig Kerzen", "kerzen": len(bars)}],
                               [], [])
        return out
    sig = signale(bars)
    for bot in BOTS:
        try:
            out[bot.bot_id] = lauf_bot(bot, client, states.get(bot.bot_id) or {}, now, bars, spread, sig,
                                       send_orders, post)
        except Exception as err:          # noqa: BLE001 - ein Bot darf den anderen nie aufhalten
            out[bot.bot_id] = (copy.deepcopy(states.get(bot.bot_id) or {}),
                               [{"time": str(now), "bot": bot.bot_id, "event": "Fehler", "fehler": str(err)[:300]}],
                               [], [])
    return out


def main(argv: list[str]) -> int:
    from gold.bot.capital import CapitalClient
    from gold.bot.runner import CRED_KEYS, clean_credentials

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="nur rechnen, keine Order, keine Nachricht")
    args = ap.parse_args(argv)
    creds = clean_credentials({k: os.environ.get(k, "") for k in CRED_KEYS})
    if not all(creds):
        print("Keine Capital.com-Zugangsdaten, Pine-Gold-Bots übersprungen")
        return 0
    states, erster = {}, False
    for bot in BOTS:
        p = ROOT / "journal" / bot.bot_id / "state.json"
        states[bot.bot_id] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        erster = erster or (bot.bot_id == START_BOT and not p.exists())
    client = CapitalClient(*creds, environment="demo")
    client.login()
    try:
        out = run(client, states, datetime.now(timezone.utc), send_orders=not args.dry_run)
    finally:
        with contextlib.suppress(Exception):
            client.logout()
    fehler = False
    for bot in BOTS:
        st, log, fertige, nachrichten = out[bot.bot_id]
        fehler = fehler or any(e["event"] == "Fehler" for e in log)
        print(bot.bot_id, json.dumps({"ereignisse": log, "fertig": fertige, "nachrichten": nachrichten,
                                      "offen": len(st.get("offen", []))}, ensure_ascii=False, default=str))
        if not args.dry_run:
            if bot.bot_id == START_BOT and erster:
                ok = hb.sende(START_TEXT, "Pine-Gold jetzt auf Account 5", ["rocket"])
                print("Start-Nachricht", "gesendet" if ok else "nicht gesendet")
            schreiben(bot, states[bot.bot_id], st, log, fertige, nachrichten)
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
