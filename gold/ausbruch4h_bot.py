"""Gold 4-Std.-Ausbruch mit Tagestrend: der nächste Kandidat der Gold-Matrix live auf einem Capital.com-DEMOKONTO.
Nie echtes Geld.

    python -m gold.ausbruch4h_bot              # ein Lauf: offenen Trade führen, nach einem 4-Std.-Schluss neues Signal?
    python -m gold.ausbruch4h_bot --dry-run    # nur rechnen und zeigen, keine Order

Kirons Wahl vom 11.11.2026 19:59 UTC auf der Karte "4-Std.-Ausbruch auf Gold trotz knapp verfehltem Test mitlaufen
lassen?": "Besten als Demo-Bot starten". Die Regel ist die Variante ausbruch.4h.trend_hoch.swing_4h.zeit_4h der
Gold-Matrix (suche/VORAB_gold_matrix.yaml), unverändert. Sie hat den Test NICHT bestanden, sie ist ein Kandidat
(suche/ergebnis_gold_matrix.md): Sie schlug alle 306 Zufallsläufe, verfehlte aber die Hürde von 3 Standardabweichungen
knapp (2,93). Regeln des Bots und Urteil stehen in suche/VORAB_gold_ausbruch4h_bot.yaml, Prüfsumme im Protokoll vor dem
ersten Trade. Ohne passende Prüfsumme öffnet der Bot nichts.

Regel (4-Std.-Kerzen beginnen um 18, 22, 2, 6, 10 und 14 Uhr New York):
- Einstieg: Eine 4-Std.-Kerze schließt über dem höchsten Hoch der 20 Kerzen davor, und die Kerze davor tat das nicht.
  Verkauf spiegelbildlich. Kauf nur, wenn der letzte fertige Handelstag über seinem EMA 50 schloss und der EMA 50 höher
  steht als 5 Tage davor.
- Stop: unter dem tiefsten Tief der letzten 10 fertigen 4-Std.-Kerzen minus 0,1 ATR, mindestens 0,5 und höchstens
  4 ATR vom Kurs entfernt. Er liegt beim Broker und bleibt bis zum Ende.
- Ausstieg: zum Markt, sobald nach dem Einstieg 4 weitere 4-Std.-Kerzen fertig sind (etwa 16 Handelsstunden).
  Spätestens nach 14 Tagen. Höchstens ein Trade gleichzeitig.

Live-Ausführung:
- Signal, Filter und Stop-Abstand rechnen dieselben Funktionen wie der Test (suche/gold_matrix.py), auf fertigen
  Stundenkerzen von Capital.com. Dahinter hängt die Einstiegskerze mit dem aktuellen Kurs.
- Der Lauf kommt alle 15 Minuten (Minute 1, 16, 31, 46). Gerechnet wird nur in den ersten 25 Minuten nach dem Schluss
  einer 4-Std.-Kerze, also sechsmal am Tag. Solange ein Trade offen ist, zählt jeder Lauf die fertigen 4-Std.-Kerzen.
- Nur Account 4, den er mit dem Kern-Bot Vortag EUR/USD teilt (anderer Markt). Nie das Hauptkonto des Gold-Bots. Er
  kennt seine Position an der Deal-ID. Liegt eine fremde Gold-Position auf dem Konto, öffnet er nichts Neues.
- Ab -25 R seit Start nichts Neues mehr (Sicherung), zurück nur mit Kirons Entscheidung.
- Er schreibt nur journal/gold-ausbruch4h/ und journal/gold-ausbruch4h.json, nie die Dateien des Gold-Bots.
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
from suche import gold_matrix as gm

ROOT = Path(gm.ROOT)
BOT_ID = "gold-ausbruch4h"
NAME = "Gold 4-Std.-Ausbruch mit Tagestrend"
EPIC = sb.EPIC
KONTO = "332263746671301790"          # Account 4, geteilt mit dem Kern-Bot r6-vortag-eurusd (EUR/USD)
KONTO_NAME = "Account 4"
HAUPT_ENDUNG = sb.HAUPT_ENDUNG        # Hauptkonto des Gold-Bots, hier nie handeln
VARIANTE = "ausbruch.4h.trend_hoch.swing_4h.zeit_4h"
RISIKO_EUR = 5.0
MAX_OZ = 1.0
MAX_RISIKO_FAKTOR = 2.0               # Runden auf die kleinste Größe darf das Risiko höchstens verdoppeln
MARGE_ANTEIL = 0.2                    # die Order darf höchstens diesen Teil des freien Gelds als Margin brauchen
PAUSE_R = -25.0
ZWISCHEN_NACH, ZWISCHEN_PF = 15, 0.6
URTEIL_NACH, URTEIL_PF = 40, 1.2
TAGE_KERZEN = 400                     # so viele Kalendertage Stundenkerzen je Signal-Rechnung (EMA 50 der Tage, ATR)
MIN_TAGESKERZEN = 150                 # mit weniger fertigen Handelstagen rechnet der Bot kein Signal
FRIST = pd.Timedelta(minutes=25)      # so lange nach dem Schluss der Signalkerze darf der Bot noch einsteigen
VORLAUF_TRADE = pd.Timedelta(hours=12)     # so weit vor dem Einstieg beginnen die Kerzen für das Zählen des Ausstiegs
SCHLUSS_WARTEN = pd.Timedelta(hours=1)     # so lange sucht der Bot den Schlusskurs beim Broker, dann zählt der Stop
STUNDE = pd.Timedelta(hours=1)
FMT = "%Y-%m-%dT%H:%M:%S"
SPALTEN = ["open", "high", "low", "close"]
VORAB = ROOT / "suche" / "VORAB_gold_ausbruch4h_bot.yaml"
KEY = "VORAB_gold_ausbruch4h_bot sha256 "
JDIR = ROOT / "journal" / "gold-ausbruch4h"
COCKPIT = ROOT / "journal" / "gold-ausbruch4h.json"
GOLD_BOT_DATEIEN = sb.GOLD_BOT_DATEIEN
SEITE = {1: "Kauf", -1: "Verkauf"}
REGEL = ("4-Std.-Ausbruch mit Tagestrend (Gold-Matrix, ausbruch.4h.trend_hoch.swing_4h.zeit_4h): Schluss einer "
         "4-Std.-Kerze über dem Hoch der 20 Kerzen davor, nur mit dem Trend des Tages (Schluss über EMA 50, EMA 50 "
         "steigt). Stop hinter dem Tief der letzten 10 Kerzen. Ausstieg nach 4 fertigen 4-Std.-Kerzen. Verkauf "
         "spiegelbildlich. Höchstens ein Trade, 5 € Risiko.")
TEST = ("Test NICHT bestanden, Kandidat (suche/ergebnis_gold_matrix.md): 2024 bis 2026 153 Trades (1,04 je Woche), GF "
        "2,35, +22,9 R, Trefferquote 62 %, beide Hälften über 2, alle 306 Zufallsläufe geschlagen, aber nur 2,93 statt "
        "3 Standardabweichungen über dem Zufall. 2016 bis 2023 GF 0,83. Im Schnitt +0,15 R je Trade.")


def variante() -> dict:
    """Die Variante aus der versiegelten Finalisten-Liste der Gold-Matrix, dazu Stop und Ausstieg wie in
    gm.trades_von: stop_art, stop_ebene, modus, zahl (Kerzen bis zum Ausstieg), aus_ebene."""
    import yaml
    liste = yaml.safe_load(gm.FINALISTEN.read_text(encoding="utf-8"))["gold_matrix_finalisten"]["finalisten"]
    f = dict(next(x for x in liste if x["key"] == VARIANTE))
    art, seb = {name: (a, s) for name, a, s in gm.stop_liste(f["ebene"])}[f["stop"]]
    modus, zahl, xeb = {name: (m, z, x) for name, m, z, x in gm.ausstieg_liste(f["ebene"])}[f["ausstieg"]]
    if modus != gm.MODUS["zeit"]:
        raise RuntimeError("dieser Bot kann nur den Ausstieg nach Zeit")
    return {**f, "stop_art": art, "stop_ebene": seb, "modus": modus, "zahl": int(zahl), "aus_ebene": xeb}


V = variante()
ZEIT_KERZEN = V["zahl"]


def vorab_ok() -> bool:
    """Sind die Regeln des Bots festgelegt und die beiden Dateien der Gold-Matrix unverändert, aus denen die Rechnung
    ihre Werte liest?"""
    from suche.runde1 import journal_lines, last_value, sha256_text
    if not VORAB.exists():
        return False
    return (last_value(journal_lines(), KEY) == sha256_text(VORAB.read_text(encoding="utf-8"))
            and gm.vorab_ok() and gm.finalisten_ok())


# --------------------------------------------------------------------------------------------------------------------
# Zeit, Kerzen, Signal (ohne Netz, außer stundenkerzen)

def _ny(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return idx.tz_localize("UTC").tz_convert(gm.NY).tz_localize(None)


def _block(zeiten: pd.DatetimeIndex) -> np.ndarray:
    """Die 4-Std.-Kerze des Tests, in die jede Zeit fällt (gm.schluessel)."""
    return gm.schluessel(zeiten, _ny(zeiten), V["ebene"])


def grenze(now: pd.Timestamp) -> pd.Timestamp:
    """Beginn der laufenden 4-Std.-Kerze als UTC. Das ist die erste Minute nach der letzten fertigen Kerze, im Test die
    Minute des Einstiegs."""
    h = pd.Timestamp(now).floor("h")
    kand = pd.DatetimeIndex([h - k * STUNDE for k in range(6)])        # eine Kerze dauert höchstens 5 Stunden (Uhr-Umstellung)
    b = _block(kand)
    return kand[b == b[0]].min()


def naechste_grenze(now: pd.Timestamp) -> pd.Timestamp:
    h = pd.Timestamp(now).floor("h")
    kand = pd.DatetimeIndex([h + k * STUNDE for k in range(7)])
    b = _block(kand)
    return kand[b != b[0]].min()


def handelstag(t) -> int:
    """Handelstag (endet 17:00 Uhr New York) als Zahl, wie `tag` in suche/gold_matrix.py. Für die Nächte eines Trades."""
    ny = _ny(pd.DatetimeIndex([pd.Timestamp(t)]))[0]
    return int(((ny + pd.Timedelta(hours=7)).normalize() - pd.Timestamp("1970-01-01")).days)


def gesperrt(zeiten) -> np.ndarray:
    """Sperre des Tests je Minute (Handelspause 20:55 bis 23:05 UTC, 15 Minuten um einen Termin), nach Zeit sortiert.
    Gerechnet von gm.markt selbst, es gibt keine zweite Fassung der Regel."""
    idx = pd.DatetimeIndex(sorted({pd.Timestamp(t).floor("min") for t in zeiten}))
    return gm.markt(pd.DataFrame(1.0, index=idx, columns=SPALTEN), termine=gm.lies_termine()).gesperrt


def stundenkerzen(client, von: pd.Timestamp, bis: pd.Timestamp) -> pd.DataFrame:
    """Fertige Stundenkerzen (Bid) von `von` bis `bis`, in Abrufen zu je 40 Tagen (nur lesen)."""
    from suche.demo_bots import frame
    teile, ende = [], pd.Timestamp(bis)
    while ende > von:
        ab = max(pd.Timestamp(von), ende - pd.Timedelta(days=40))
        teile.extend(client._get(f"/prices/{EPIC}", resolution="HOUR", max=1000,
                                 **{"from": ab.strftime(FMT), "to": ende.strftime(FMT)}).get("prices", []))
        ende = ab
    bars, _ = frame(teile)
    if not len(bars):
        return pd.DataFrame(columns=SPALTEN, dtype=float, index=pd.DatetimeIndex([]))
    return bars[bars.index + STUNDE <= bis][SPALTEN]


def markt_live(stunden: pd.DataFrame, t_grenze: pd.Timestamp, now: pd.Timestamp, bid: float) -> tuple[gm.Markt, int]:
    """Der Markt des Tests aus fertigen Stundenkerzen vor t_grenze. Dahinter hängt die Einstiegskerze: eine Zeile zur
    ersten Minute nach der Signalkerze mit dem aktuellen Bid als Eröffnung und, kommt der Lauf später, eine Zeile
    "jetzt". Rückgabe: Markt und die Zeile des Einstiegs."""
    alt = stunden[stunden.index < t_grenze][SPALTEN]
    zeiten = sorted({pd.Timestamp(t_grenze), max(pd.Timestamp(now).floor("min"), pd.Timestamp(t_grenze))})
    neu = pd.DataFrame(float(bid), index=pd.DatetimeIndex(zeiten), columns=SPALTEN)
    return gm.markt(pd.concat([alt, neu]), termine=gm.lies_termine()), len(alt)


def signal(stunden: pd.DataFrame, t_grenze: pd.Timestamp, now: pd.Timestamp, bid: float) -> dict:
    """Was der Test in der ersten Minute nach der 4-Std.-Kerze sieht, die bei t_grenze endet: Richtung des Ausbruchs
    (0: keiner), Tagestrend, Stop-Abstand, Sperre. `ok` heißt: Der Test nähme diesen Einstieg (ohne die Frage, ob schon
    ein Trade offen ist). `warten` heißt: Es fehlen Kerzen, der nächste Lauf sieht noch einmal nach."""
    out = {"grenze": str(t_grenze), "richtung": 0, "trend": None, "dist": None, "gesperrt": None, "ok": False,
           "warten": False, "ergebnis": ""}
    alt = stunden[stunden.index < t_grenze]
    if not len(alt) or alt.index[-1] != t_grenze - STUNDE:
        # Im Test verfällt ein Signal, wenn nach der Signalkerze eine Lücke liegt (Wochenende, Handelspause). Live kann
        # die letzte Stundenkerze auch nur noch nicht da sein, darum sieht der nächste Lauf in der Frist noch einmal nach.
        return {**out, "warten": True, "ergebnis": "die letzte Stundenkerze vor dem Schluss fehlt (Markt war zu oder die "
                                                   "Kerze ist noch nicht da)"}
    m, e = markt_live(stunden, t_grenze, now, bid)
    k4, tage = m.eb[V["ebene"]], m.eb[gm.P["filter"][V["filter"]]["ebene"][V["ebene"]]]
    j, fertige_tage = int(k4.lc[e]), int(tage.lc[e]) + 1
    out.update(kerzen_4h=j + 1, tageskerzen=fertige_tage)
    if fertige_tage < MIN_TAGESKERZEN:
        return {**out, "warten": True, "ergebnis": f"zu wenig Kerzen vom Broker ({fertige_tage} fertige Handelstage, "
                                                   f"nötig {MIN_TAGESKERZEN})"}
    lang, kurz = gm.roh_signale(m, V["einstieg"], V["ebene"])
    d = 1 if lang[j] else -1 if kurz[j] else 0
    n = int(gm.P["einstiege"][V["einstieg"]]["kerzen"])
    out.update(richtung=d, schluss=round(float(k4.c[j]), 2), hoch_davor=round(float(k4.h[j - n:j].max()), 2),
               tief_davor=round(float(k4.l[j - n:j].min()), 2), gesperrt=bool(m.gesperrt[e]),
               gesperrt_jetzt=bool(m.gesperrt[-1]))
    if d == 0:
        return {**out, "ergebnis": "kein Ausbruch"}
    ea, da = np.array([e], dtype=np.int64), np.array([d], dtype=np.int64)
    trend = bool(gm.filter_maske(m, V["filter"], V["ebene"], ea, da)[0])
    dist = float(gm.stop_abstand(m, V["stop_art"], V["stop_ebene"], ea, da)[0])
    out.update(trend=trend, dist=None if math.isnan(dist) else round(dist, 4))
    if not trend:
        return {**out, "ergebnis": f"{SEITE[d]}-Ausbruch gegen den Tagestrend"}
    if not dist >= gm.MIN_ABSTAND:
        return {**out, "ergebnis": f"{SEITE[d]}-Ausbruch, aber kein gültiger Stop-Abstand"}
    if out["gesperrt"]:
        return {**out, "ergebnis": f"{SEITE[d]}-Ausbruch in der Sperre (Handelspause oder Termin)"}
    return {**out, "ok": True, "ergebnis": f"{SEITE[d]}-Ausbruch mit dem Tagestrend"}


def kerzen_seit(stunden: pd.DataFrame, t_grenze: pd.Timestamp, now: pd.Timestamp) -> int | None:
    """So viele 4-Std.-Kerzen sind seit der Minute des Einstiegs fertig geworden, gezählt wie im Test (letzte fertige
    Kerze jetzt minus letzte fertige Kerze beim Einstieg). None, wenn die Signalkerze in den Kerzen fehlt."""
    jetzt = pd.Timestamp(now).floor("min")
    alt = stunden[stunden.index < jetzt][SPALTEN]
    if not len(alt) or jetzt < t_grenze:
        return None
    kurs = float(alt["close"].iloc[-1])
    m = gm.markt(pd.concat([alt, pd.DataFrame(kurs, index=pd.DatetimeIndex([jetzt]), columns=SPALTEN)]))
    lc = m.eb[V["aus_ebene"]].lc
    i0 = int(np.searchsorted(m.t, np.datetime64(pd.Timestamp(t_grenze), "ns"), side="left"))
    if lc[i0] < 0:
        return None
    return int(lc[len(m) - 1] - lc[i0])


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
    pf = gm.gf(np.array(r, dtype=float)) if n else None
    if n >= URTEIL_NACH:
        erste = np.array(r[:URTEIL_NACH], dtype=float)
        ok = (gm.gf(erste) or 0) >= URTEIL_PF and float(erste.sum()) > 0
        text = ("bestanden nach 40 Trades, Kiron entscheidet über den nächsten Schritt" if ok else
                "durchgefallen nach 40 Trades, Vorschlag an Kiron: stoppen oder neue Regeln mit neuem Vorab")
    elif n >= ZWISCHEN_NACH and (pf or 0) < ZWISCHEN_PF:
        text = f"Zwischencheck nach {n} Trades: Gewinnfaktor unter {ZWISCHEN_PF}, Vorschlag an Kiron: stoppen"
    else:
        text = f"läuft ({n} von {URTEIL_NACH} Trades)"
    return {"trades": n, "pf_r": None if pf is None else round(float(pf), 3), "summe_r": round(float(sum(r)), 2),
            "trefferquote": round(sum(x > 0 for x in r) / n, 3) if n else None,
            "summe_eur": round(float(sum(float(t.get("pnl_eur") or 0) for t in trades)), 2), "urteil": text}


_num = sb._num
_jetzt = sb._jetzt


def _zeit(x, ersatz: pd.Timestamp) -> pd.Timestamp:
    try:
        t = _jetzt(pd.Timestamp(x))
        return ersatz if pd.isna(t) else t
    except (TypeError, ValueError):
        return ersatz


# --------------------------------------------------------------------------------------------------------------------
# Ein Lauf

class Lauf:
    """Ein Lauf auf dem Demokonto. Alle Order- und Schließ-Aufrufe gehen über diese Klasse, damit ein Trockenlauf
    (send_orders=False) nichts beim Broker ändert."""

    def __init__(self, client, state: dict, now: datetime, send_orders: bool = True):
        self.client = client
        self.st = copy.deepcopy(state or {})
        self.now = _jetzt(now)
        self.stamp = self.now.isoformat(timespec="seconds")
        self.send = send_orders
        self.log: list[dict] = []
        self.fertige: list[dict] = []
        self.q = None
        self.andere_gold: list[str] = []
        self.eigene_zu: set[str] = set()
        self.blick: dict = {}
        for k, v in (("format", 1), ("start", self.stamp), ("trade", None), ("summe_r", 0.0), ("trades", 0)):
            self.st.setdefault(k, v)

    def ev(self, event: str, **kw) -> None:
        self.log.append({"time": self.stamp, "event": event, **kw})

    def kurs_raus(self, d: int) -> float:
        """Zu diesem Kurs schließt eine Position zum Markt: Kauf am Bid, Verkauf am Ask."""
        return self.q.bid if d > 0 else self.q.offer

    def nur_mein_konto(self) -> None:
        if str(self.client.account_id) != KONTO:
            raise RuntimeError(f"aktives Konto ist nicht {KONTO_NAME}, nichts gesendet")

    def kerzen(self, von: pd.Timestamp) -> pd.DataFrame | None:
        try:
            return stundenkerzen(self.client, von, self.now)
        except Exception as err:            # noqa: BLE001 - der nächste Lauf versucht es wieder
            print(f"Stundenkerzen nicht lesbar: {err}")
            self.blick["wartet"] = "Stundenkerzen nicht lesbar"
            return None

    # ---- Broker ----

    def schliesse(self, tr: dict, warum: str) -> bool:
        if not self.send:
            self.ev("würde schließen", dealId=tr["dealId"], warum=warum, kurs=self.kurs_raus(tr["richtung"]))
            return False
        try:
            self.nur_mein_konto()
            conf = self.client.close_position(tr["dealId"])
        except Exception as err:            # noqa: BLE001 - nächster Lauf versucht es wieder, Stop liegt beim Broker
            tr["schliessen_versucht"] = warum
            self.ev("schließen fehlgeschlagen", dealId=tr["dealId"], warum=warum, fehler=str(err)[:200])
            return False
        if str((conf or {}).get("dealStatus") or "").upper() == "REJECTED":
            tr["schliessen_versucht"] = warum
            self.ev("schließen abgelehnt", dealId=tr["dealId"], warum=warum, grund=(conf or {}).get("reason"))
            return False
        level = _num((conf or {}).get("level")) or self.kurs_raus(tr["richtung"])
        self.abschluss(tr, float(level), warum, self.now)
        return True

    def schluss_beim_broker(self, tr: dict) -> tuple[float | None, str, pd.Timestamp]:
        """Schlusskurs, Quelle (SL, CLOSE_OUT, USER ...) und Zeit aus der Kontoaktivität zu dieser Position. Der Broker
        gibt je Abruf höchstens einen Tag her, darum die letzten 23 Std. 59 Min., auch wenn der Trade älter ist. Es
        zählt nur ein eindeutiger Schluss, nie eine Änderung. (None, "", jetzt), wenn dort kein Schluss steht."""
        von = max(pd.Timestamp(tr["opened_utc"]) - pd.Timedelta(minutes=10),
                  self.now - pd.Timedelta(hours=23, minutes=59))
        try:
            acts = self.client.activity(tr["dealId"], von.to_pydatetime(), self.now.to_pydatetime())
        except Exception as err:            # noqa: BLE001
            print(f"Kontoaktivität nicht lesbar: {err}")
            return None, "", self.now
        rows = [{"dateUTC": str(a.get("dateUTC") or ""), "source": a.get("source"),
                 "level": _num((a.get("details") or {}).get("level")),
                 "actions": [x.get("actionType") for x in (a.get("details") or {}).get("actions", [])]}
                for a in acts or [] if a.get("type", "POSITION") == "POSITION" and a.get("status", "ACCEPTED") == "ACCEPTED"]
        zu = sorted((r for r in rows if r["level"] is not None
                     and (r["source"] in ("SL", "TP", "CLOSE_OUT") or "POSITION_CLOSED" in r["actions"])),
                    key=lambda r: r["dateUTC"])
        if not zu:
            return None, "", self.now
        return zu[-1]["level"], str(zu[-1]["source"] or ""), _zeit(zu[-1]["dateUTC"], self.now)

    # ---- Abgleich mit dem Konto ----

    def abschluss(self, tr: dict, level: float, grund: str, wann: pd.Timestamp, **mehr) -> None:
        """Bucht den Trade. R nach Übernachtgebühr mit den Sätzen des Tests, das Euro-Ergebnis ohne Gebühr."""
        d, dist = tr["richtung"], float(tr["dist"])
        satz = gm.SATZ_LONG if d > 0 else gm.SATZ_SHORT
        naechte = max(handelstag(wann) - handelstag(tr["opened_utc"]), 0)
        gebuehr_r = satz / 36500.0 * naechte * tr["entry"] / dist
        r_roh = d * (level - tr["entry"]) / dist
        pnl_usd = tr["size"] * (self.q.lot or 1.0) * d * (level - tr["entry"])
        rate = self.q.eur_rate
        rec = {**{k: tr.get(k) for k in ("id", "richtung", "grenze", "dealId", "size", "entry", "stop", "dist",
                                         "opened_utc", "spaet_min", "kerzen")},
               "seite": SEITE[d], "exit": round(level, 2), "grund": grund,
               "closed_utc": pd.Timestamp(wann).isoformat(timespec="seconds"), "naechte": naechte,
               "r_roh": round(r_roh, 3), "gebuehr_r": round(gebuehr_r, 3), "r": round(r_roh - gebuehr_r, 3),
               "pnl_usd": round(pnl_usd, 2), "pnl_eur": round(pnl_usd / rate, 2) if rate else None, **mehr}
        self.fertige.append(rec)
        self.eigene_zu.add(str(tr.get("dealId")))
        self.st["letzter_schluss"] = rec["closed_utc"]
        self.st["summe_r"] = round(float(self.st["summe_r"]) + rec["r"], 3)
        self.st["trades"] = int(self.st["trades"]) + 1
        self.st["trade"] = None
        self.ev("Trade fertig", trade=tr["id"], seite=rec["seite"], grund=grund, r=rec["r"], pnl_eur=rec["pnl_eur"])
        if self.st.get("pausiert") is None and self.st["summe_r"] <= PAUSE_R:
            self.st["pausiert"] = {"seit": self.stamp, "grund": f"Summe R seit Start {self.st['summe_r']} (Grenze "
                                                                f"{PAUSE_R}), zurück nur mit Kirons Entscheidung"}
            self.ev("Pause", grund=self.st["pausiert"]["grund"])

    def abgleich(self, gold: list[dict]) -> None:
        """Ist der offene Trade beim Broker zu (Stop)? Und: Liegt eine Order ohne Bestätigung jetzt als Position da?"""
        pos = {str(p["position"].get("dealId")): p["position"] for p in gold}
        offen = self.st.get("ungeklaert")
        if offen and self.st.get("trade") is None:
            self.st["ungeklaert"] = None
            neu = [p for i, p in pos.items() if i not in set(offen.get("vorher") or [])
                   and p.get("direction") == ("BUY" if offen["richtung"] > 0 else "SELL")
                   and abs((_num(p.get("size")) or 0) - offen["size"]) < 1e-9]
            if len(neu) == 1:
                self.uebernehmen(neu[0], offen, offen["seit"])
            else:
                self.ev("Order ohne Bestätigung liegt nicht beim Broker", grenze=offen["grenze"], gefunden=len(neu))
        tr = self.st.get("trade")
        if not tr:
            return
        if tr["dealId"] in pos:                            # Stop so, wie er beim Broker steht
            tr["stop"] = _num(pos[tr["dealId"]].get("stopLevel")) or tr.get("stop")
            tr.pop("weg_seit", None)
            return
        level, quelle, wann = self.schluss_beim_broker(tr)
        geschaetzt = level is None
        seit = tr.setdefault("weg_seit", self.stamp)
        if geschaetzt and self.now - pd.Timestamp(seit) < SCHLUSS_WARTEN:
            if seit == self.stamp:
                self.ev("Position beim Broker zu, Schlusskurs noch nicht lesbar", trade=tr["id"])
            return
        if geschaetzt:
            level, quelle, wann = tr.get("stop") or tr["entry"] - tr["richtung"] * tr["dist"], "SL", pd.Timestamp(seit)
        if quelle == "SL":
            grund = "stop"
        elif tr.get("schliessen_versucht"):
            grund = tr["schliessen_versucht"]
        else:
            grund = f"beim Broker ({quelle or 'unbekannt'})"
        self.abschluss(tr, float(level), grund, wann, **({"exit_geschaetzt": True} if geschaetzt else {}))

    def uebernehmen(self, p: dict, plan: dict, opened_utc: str) -> None:
        """Macht aus einer Position beim Broker den offenen Trade des Bots."""
        d = int(plan["richtung"])
        level = _num(p.get("level")) or (self.q.offer if d > 0 else self.q.bid)
        stop = _num(p.get("stopLevel")) or level - d * plan["dist"]
        self.st["trade"] = {"id": f"{pd.Timestamp(plan['grenze']):%Y-%m-%dT%H:%M}", "richtung": d,
                            "grenze": plan["grenze"], "dealId": str(p.get("dealId")), "size": plan["size"],
                            "entry": round(float(level), 2), "stop": round(float(stop), 2), "dist": plan["dist"],
                            "opened_utc": opened_utc, "spaet_min": plan.get("spaet_min"), "kerzen": 0}
        self.ev(SEITE[d] + " eröffnet", **{k: self.st["trade"][k] for k in ("id", "dealId", "size", "entry", "stop",
                                                                            "dist", "spaet_min")})

    # ---- Führung des offenen Trades ----

    def fuehren(self) -> None:
        """Ausstieg zum Markt, sobald nach dem Einstieg ZEIT_KERZEN 4-Std.-Kerzen fertig sind, spätestens nach der
        Haltezeit des Tests."""
        tr = self.st.get("trade")
        if not tr or tr.get("weg_seit"):
            return
        zu_alt = self.now - pd.Timestamp(tr["opened_utc"]) >= pd.Timedelta(minutes=gm.HALTE_MIN)
        t_g = pd.Timestamp(tr["grenze"])
        st = self.kerzen(t_g - VORLAUF_TRADE)
        n = kerzen_seit(st, t_g, self.now) if st is not None else None
        if n is not None and n != tr.get("kerzen"):
            tr["kerzen"] = n
        if not zu_alt and (n is None or n < ZEIT_KERZEN):
            return
        if not self.q.tradeable:
            self.blick["wartet"] = "Ausstieg fällig, Markt zu"
            return
        self.schliesse(tr, "haltezeit" if zu_alt and (n is None or n < ZEIT_KERZEN) else "zeit")

    # ---- Neues Signal ----

    def pruefen(self, gold: list[dict], fremde: list[dict], available_eur: float | None) -> None:
        """Einmal je 4-Std.-Kerze, in den ersten FRIST Minuten nach ihrem Schluss: Gibt es ein Signal, und darf der Bot
        es nehmen?"""
        t_g = grenze(self.now)
        key = str(t_g)
        if self.st.get("letzte_grenze") == key:
            return

        def fertig(ergebnis: str, **kw) -> None:
            self.st["letzte_grenze"] = key
            self.st["letzte_pruefung"] = {"grenze": key, "ergebnis": ergebnis, **kw}

        if self.now - t_g > FRIST:
            if not self.send:
                return
            return fertig("Start des Bots mitten in der Kerze" if self.st.get("letzte_grenze") is None else
                          "verfallen: In der Frist kam kein Lauf zum Zug (Markt zu, Stundenkerze fehlte oder Lauf fiel aus)")
        if self.st.get("trade") is not None:
            return fertig("ein Trade ist offen, höchstens einer gleichzeitig")
        zuletzt = self.st.get("letzter_schluss")
        if zuletzt and pd.Timestamp(zuletzt) >= t_g:
            return fertig("der letzte Trade endete erst nach dem Schluss dieser Kerze")
        sperre = gesperrt([t_g, self.now])
        if sperre[0]:
            return fertig("Sperre zur ersten Minute nach der Kerze (Handelspause oder Termin)")
        if not self.q.tradeable:
            self.blick["wartet"] = "Markt zu"
            return
        if sperre[-1]:
            self.blick["wartet"] = "Termin-Sperre"
            return
        kurz = self.kerzen(t_g - 3 * STUNDE)               # ein kleiner Abruf: Ist die letzte Stundenkerze schon da?
        if kurz is None:
            return
        if not len(kurz) or kurz.index[-1] != t_g - STUNDE:
            self.blick["wartet"] = "die letzte Stundenkerze vor dem Schluss fehlt"
            return
        stunden = self.kerzen(self.now - pd.Timedelta(days=TAGE_KERZEN))
        if stunden is None:
            return
        sig = signal(stunden, t_g, self.now, self.q.bid)
        self.blick["signal"] = sig
        if sig["warten"]:
            self.blick["wartet"] = sig["ergebnis"]
            return
        kurz_info = {k: sig.get(k) for k in ("richtung", "schluss", "hoch_davor", "tief_davor", "trend", "dist")}
        if not sig["ok"]:
            if sig["richtung"]:
                self.ev("Ausbruch ohne Einstieg", grenze=key, grund=sig["ergebnis"], **kurz_info)
            return fertig(sig["ergebnis"], **kurz_info)
        self.einstieg(sig, t_g, gold, fremde, available_eur, fertig, kurz_info)

    def einstieg(self, sig: dict, t_g: pd.Timestamp, gold: list[dict], fremde: list[dict],
                 available_eur: float | None, fertig, kurz_info: dict) -> None:
        from suche.demo_bots import open_market
        q, d, dist = self.q, int(sig["richtung"]), round(float(sig["dist"]), 2)
        gruende = []
        if self.st.get("pausiert"):
            gruende.append(f"Pause ab {PAUSE_R:.0f} R")
        if not vorab_ok():
            gruende.append("Regeln nicht festgelegt (Prüfsumme im Protokoll fehlt oder passt nicht)")
        if fremde:
            gruende.append("fremde Gold-Position auf dem Konto")
        if self.andere_gold:
            gruende.append(f"{KONTO_NAME} ist laut journal/konten.json auch für {', '.join(self.andere_gold)} vergeben")
        size, warum = groesse(dist, q)
        if size is None:
            gruende.append(warum)
        else:
            marge = size * (q.lot or 1) * q.bid * q.margin_pct / 100 / (q.eur_rate or 1)
            if available_eur is not None and marge > MARGE_ANTEIL * available_eur:
                gruende.append(f"Margin {marge:.0f} € wäre mehr als {MARGE_ANTEIL:.0%} des freien Gelds ({available_eur:.0f} €)")
        if q.min_dist and dist < q.min_dist:
            gruende.append("Stop näher als der Mindestabstand des Brokers")
        spaet = round((self.now - t_g).total_seconds() / 60, 1)
        info = {"seite": SEITE[d], "grenze": str(t_g), "dist": dist, "spaet_min": spaet, "bid": round(q.bid, 2)}
        if gruende:
            self.ev("Einstieg ausgelassen", **info, gruende=gruende)
            return fertig("Signal, aber kein Einstieg: " + "; ".join(gruende), **kurz_info)
        if not self.send:
            self.ev("würde " + ("kaufen" if d > 0 else "verkaufen"), **info, size=size)
            return
        fertig(f"{SEITE[d]} gesendet", **kurz_info)        # vor der Order: nie eine zweite Order für dieselbe Kerze
        vorher = {str(p["position"].get("dealId")) for p in gold}
        plan = {"grenze": str(t_g), "richtung": d, "size": size, "dist": dist, "spaet_min": spaet}
        conf = None
        try:
            self.nur_mein_konto()
            conf = open_market(self.client, EPIC, d, {"size": size, "stop_dist": dist, "tp_dist": None}) or {}
        except Exception as err:            # noqa: BLE001 - kein zweiter Versuch, damit nichts doppelt entsteht
            self.ev("Order ohne Bestätigung", **info, fehler=str(err)[:200])
            fertig(f"{SEITE[d]} gesendet, Bestätigung fehlt", **kurz_info)
        if conf is not None and str(conf.get("dealStatus") or "").upper() == "REJECTED":
            self.ev("Order abgelehnt", **info, grund=conf.get("reason"))
            return fertig(f"Signal, aber die Order wurde abgelehnt ({conf.get('reason')})", **kurz_info)
        try:
            jetzt = [p["position"] for p in self.client.positions() if p.get("market", {}).get("epic") == EPIC]
        except Exception as err:            # noqa: BLE001
            print(f"Positionen nach der Order nicht lesbar: {err}")
            jetzt = None
        neu = [p for p in jetzt or [] if str(p.get("dealId")) not in vorher
               and p.get("direction", "BUY" if d > 0 else "SELL") == ("BUY" if d > 0 else "SELL")]
        deal = ((conf or {}).get("affectedDeals") or [{}])[0].get("dealId") or (conf or {}).get("dealId")
        if len(neu) == 1 or (conf and deal):                # sonst bestätigt, aber noch nicht in der Liste der Positionen
            fertig(f"{SEITE[d]} eröffnet", **kurz_info)
            return self.uebernehmen(neu[0] if len(neu) == 1 else {"dealId": deal, "level": conf.get("level")}, plan,
                                    self.stamp)
        # keine Bestätigung und keine Position gefunden: Der nächste Lauf sucht sie an Richtung und Größe
        self.st["ungeklaert"] = {**plan, "seit": self.stamp, "vorher": sorted(vorher)}


def run(client, state: dict, now: datetime, send_orders: bool = True) -> tuple[dict, list[dict], list[dict], dict]:
    """Ein Lauf. Rückgabe: neuer Stand, Ereignisse, fertige Trades, Blick (für das Cockpit)."""
    from gold.bot import konten
    from suche.demo_bots import eur_rate, quote_from_market

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
        lauf.fuehren()
        tr = lauf.st.get("trade")
        meine = ({tr["dealId"]} if tr else set()) | lauf.eigene_zu
        fremde = [p for p in gold if str(p["position"].get("dealId")) not in meine]
        fremd = sorted(str(p["position"].get("dealId")) for p in fremde)
        if fremd != (lauf.st.get("fremd") or []):          # nur melden, wenn sich etwas ändert
            lauf.st["fremd"] = fremd
            if fremd:
                lauf.ev("fremde Gold-Position auf dem Konto", deals=fremd)
        lauf.pruefen(gold, fremde, available)
        lauf.st["stand"] = lauf.stamp
        return lauf.st, lauf.log, lauf.fertige, blick_auf(lauf)
    finally:
        with contextlib.suppress(Exception):
            if vorher and vorher != KONTO:
                client.switch_account(vorher)


def blick_auf(lauf: Lauf) -> dict:
    """Was der Bot gerade sieht (für das Cockpit)."""
    return {"kurs": round(float(lauf.q.bid), 2) if lauf.q else None,
            "naechste_4h_kerze_endet_utc": str(naechste_grenze(lauf.now)),
            "letzte_pruefung": lauf.st.get("letzte_pruefung"), **lauf.blick}


# --------------------------------------------------------------------------------------------------------------------
# Journal und Cockpit

def status(st: dict) -> str:
    if st.get("pausiert"):
        return "Pause: " + st["pausiert"]["grund"]
    tr = st.get("trade")
    if tr and tr.get("weg_seit"):
        return "Position beim Broker geschlossen, der Bot liest den Schlusskurs"
    if tr:
        return (f"{SEITE[tr['richtung']]} offen ab {tr['entry']:.2f}, Stop {tr['stop']:.2f}, Ausstieg nach "
                f"{ZEIT_KERZEN} fertigen 4-Std.-Kerzen (bisher {tr.get('kerzen') or 0})")
    if st.get("ungeklaert"):
        return "Order gesendet, Bestätigung fehlt, der nächste Lauf sieht nach"
    p = st.get("letzte_pruefung")
    if not p:
        return "kein Trade offen, wartet auf den Schluss der nächsten 4-Std.-Kerze"
    return f"kein Trade offen. Letzte Kerze (bis {p['grenze'][:16]} UTC): {p['ergebnis']}"


def cockpit(st: dict, alle_trades: list[dict], blick: dict) -> dict:
    tr = st.get("trade")
    return {"bot": BOT_ID, "name": NAME, "konto": f"{KONTO_NAME} …" + KONTO[-4:], "stand": st.get("stand"),
            "start": st.get("start"), "pausiert": st.get("pausiert"), "status": status(st), "regel": REGEL,
            "backtest": TEST, "vorab": "suche/VORAB_gold_ausbruch4h_bot.yaml", "vorab_ok": vorab_ok(),
            "offen": [{k: tr.get(k) for k in ("id", "richtung", "entry", "stop", "size", "dist", "opened_utc",
                                             "kerzen")}] if tr else [],
            "zusammenfassung": bewertung(alle_trades), "letzte_trades": alle_trades[-10:], "blick": blick}


def _ohne_zeit(st: dict) -> dict:
    return {k: v for k, v in (st or {}).items() if k != "stand"}


def schreiben(st: dict, log: list[dict], fertige: list[dict], blick: dict, jdir: Path = JDIR,
              cockpit_pfad: Path = COCKPIT) -> bool:
    """Schreibt Zustand, Log, Trades und Cockpit. Hat sich außer der Uhrzeit nichts geändert, schreibt der Lauf nichts.
    Der Zustand ändert sich mit jeder geprüften 4-Std.-Kerze, also etwa sechsmal am Tag."""
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
    cockpit_pfad.write_text(json.dumps(cockpit(st, alle, blick), ensure_ascii=False, indent=1, default=str) + "\n",
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
        print("Keine Capital.com-Zugangsdaten, Gold 4-Std.-Ausbruch übersprungen")
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
