"""4-Std.-Ausbruch auf DAX, FTSE 100 und Nikkei 225 mit Ziel 1 R, live auf einem Capital.com-DEMOKONTO. Nie echtes Geld.

    python -m suche.welt4h_bot              # ein Lauf: offene Trades führen, nach einem 4-Std.-Schluss neue Signale?
    python -m suche.welt4h_bot --dry-run    # nur rechnen und zeigen, keine Order

Kirons Wahl vom 19.11.2026 12:23 UTC auf der Karte "Soll der 4-Std.-Ausbruch DAX, FTSE und Nikkei zusätzlich als
Demo-Bot handeln?": "Ja, als Demo-Bot auf Account 7". Die Regel ist die Fassung ausbruch4h_welt_ziel_1r aus
suche/VORAB_notizen_runde.yaml, unverändert. Sie hat den Test NICHT bestanden, sie ist ein Kandidat
(suche/ergebnis_notizen_runde.md): 2024 bis 2026 393 Trades, Gewinnfaktor 1,30, aber nur 2,26 statt 3
Standardabweichungen über dem Zufall. Die Vorwärts-Zählung ohne Bot (suche/VORAB_notizen_vorwaerts.yaml) läuft
unverändert weiter. Regeln des Bots und Urteil stehen in suche/VORAB_welt_ausbruch4h_bot.yaml, Prüfsumme im Protokoll
vor dem ersten Trade. Ohne passende Prüfsumme öffnet der Bot nichts.

Regel, je Markt für sich (4-Std.-Kerzen beginnen um 18, 22, 2, 6, 10 und 14 Uhr New York):
- Einstieg: Eine 4-Std.-Kerze schließt über dem höchsten Hoch der 20 Kerzen davor, und die Kerze davor tat das nicht.
  Verkauf spiegelbildlich. Kauf nur, wenn der letzte fertige Handelstag über seinem EMA 50 schloss und der EMA 50 höher
  steht als 5 Tage davor. Verkauf spiegelbildlich.
- Stop: hinter dem tiefsten Tief (Kauf) der letzten 10 4-Std.-Kerzen plus 0,1 ATR Puffer, mindestens 0,5 und höchstens
  4 ATR vom Bid beim Einstieg. Ziel: 1 R, also so weit wie der Stop. Beide liegen beim Broker.
- Ausstieg zum Markt, sobald nach dem Einstieg 4 weitere 4-Std.-Kerzen fertig sind, spätestens nach 14 Tagen.
- Höchstens ein Trade je Markt, also höchstens drei zugleich.

Live-Ausführung:
- Signal, Tagestrend, Sperre, Stop und Ziel rechnet die Funktion des Tests (suche/notizen_runde.signale) mit den
  Zahlen aus den versiegelten Dateien. Sie bekommt fertige Stundenkerzen von Capital.com, jede als zwölf gleiche
  5-Minuten-Zeilen, dahinter eine Zeile zur ersten Minute nach der Signalkerze mit dem aktuellen Bid.
- Der Lauf kommt alle 15 Minuten. Gerechnet wird nur in den ersten 25 Minuten nach dem Schluss einer 4-Std.-Kerze.
  Solange ein Trade offen ist, zählt jeder Lauf die fertigen 4-Std.-Kerzen.
- Nur Account 7, den er mit dem Labor-Bot Noise USD/JPY teilt (anderer Markt). Die Kontonummer liest er nach dem
  Namen aus journal/konten.json. Er kennt seine Positionen an der Deal-ID. Liegt eine fremde Position auf demselben
  Markt, öffnet er dort nichts Neues.
- Ab -25 R seit Start nichts Neues mehr (Sicherung), zurück nur mit Kirons Entscheidung.
- Er schreibt nur journal/welt-ausbruch4h/ und journal/welt-ausbruch4h.json.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import json
import math
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from gold import short_bot as sb
from suche import notizen_runde as nr
from suche import rueckblick as rb
from suche import schluss as belegt_pruefung
from suche import youtube_runde2 as y2
from suche.rueckblick_daten import MAERKTE as _EPICS

ROOT = Path(nr.ROOT)
BOT_ID = "welt-ausbruch4h"
NAME = "4-Std.-Ausbruch DAX, FTSE, Nikkei"
KONTO_NAME = "Account 7"              # geteilt mit dem Labor-Bot r6-noise-usdjpy (USD/JPY)
HAUPT_ENDUNG = sb.HAUPT_ENDUNG        # Hauptkonto des Gold-Bots, hier nie handeln
FASSUNG = "ausbruch4h_welt_ziel_1r"
RISIKO_EUR = 5.0
MAX_RISIKO_FAKTOR = 2.0               # Runden auf die kleinste Größe darf das Risiko höchstens verdoppeln
MARGE_ANTEIL = 0.2                    # eine Order darf höchstens diesen Teil des freien Gelds als Margin brauchen
PAUSE_R = -25.0
ZWISCHEN_NACH, ZWISCHEN_PF = 15, 0.6
URTEIL_NACH, URTEIL_PF = 40, 1.2
TAGE_KERZEN = 400                     # so viele Kalendertage Stundenkerzen je Signal-Rechnung (EMA 50 der Tage, ATR)
MIN_TAGESKERZEN = 150                 # mit weniger gültigen Handelstagen vor dem Einstieg rechnet der Bot kein Signal
FRIST = pd.Timedelta(minutes=25)      # so lange nach dem Schluss der Signalkerze darf der Bot noch einsteigen
SCHLUSS_WARTEN = pd.Timedelta(hours=1)     # so lange sucht der Bot den Schlusskurs beim Broker, dann schätzt er
STUNDE = pd.Timedelta(hours=1)
FUENF = np.timedelta64(5, "m")
FMT = "%Y-%m-%dT%H:%M:%S"
SPALTEN = ["open", "high", "low", "close"]
VORAB = ROOT / "suche" / "VORAB_welt_ausbruch4h_bot.yaml"
KEY = "VORAB_welt_ausbruch4h_bot sha256 "
JDIR = ROOT / "journal" / "welt-ausbruch4h"
COCKPIT = ROOT / "journal" / "welt-ausbruch4h.json"
FREMDE_DATEIEN = sb.GOLD_BOT_DATEIEN + ("konten.json", "r6-bots.json")
SEITE = {1: "Kauf", -1: "Verkauf"}
NAMEN = {"GRXEUR": "DAX", "UKXGBP": "FTSE 100", "JPXJPY": "Nikkei 225"}
REGEL = ("4-Std.-Ausbruch mit Tagestrend auf DAX, FTSE 100 und Nikkei 225 (Fassung ausbruch4h_welt_ziel_1r): Schluss "
         "einer 4-Std.-Kerze über dem Hoch der 20 Kerzen davor, nur mit dem Trend des Tages (Schluss über EMA 50, EMA 50 "
         "steigt). Stop hinter dem Tief der letzten 10 Kerzen, Ziel 1 R. Ausstieg spätestens nach 4 fertigen "
         "4-Std.-Kerzen. Verkauf spiegelbildlich. Höchstens ein Trade je Markt, 5 € Risiko.")
TEST = ("Test NICHT bestanden, Kandidat (suche/ergebnis_notizen_runde.md): 2024 bis 2026 393 Trades (etwa 2,7 je "
        "Woche), Gewinnfaktor 1,30, 2026 1,66, aber nur 2,26 statt 3 Standardabweichungen über dem Zufall. Dieselbe "
        "Regel ohne Ziel war am 18.11. mit 1,24 schon knapp (suche/ergebnis_rueckblick.md).")


def _fassung_maerkte() -> list[str]:
    import yaml
    roh = yaml.safe_load(nr.VORAB.read_text(encoding="utf-8"))["notizen_runde"]["varianten"][FASSUNG]
    return list(roh["maerkte"])


MAERKTE = {sym: _EPICS[sym][0] for sym in _fassung_maerkte()}      # HistData-Name -> Epic bei Capital.com


def konto_id(konten_daten: dict | None = None) -> str:
    """Die volle Kontonummer von Account 7 aus journal/konten.json, gesucht nach dem Namen (suche/mitnutzer.py
    konto_nach_name). Leer, wenn es das Konto dort nicht genau einmal gibt. Die Nummer wird nie abgetippt und nie
    ausgegeben."""
    from suche.mitnutzer import konto_nach_name
    return konto_nach_name(KONTO_NAME, konten_daten)


KONTO = konto_id()


def lade_cfg(pruefen: bool = False) -> dict | None:
    """Die versiegelte Runde mit nur dieser Fassung. None, wenn eine der Quelldateien nicht zu ihrem Siegel passt."""
    try:
        cfg = nr.lade_vorab(pruefen=pruefen)
    except SystemExit:
        return None
    cfg["varianten"] = {FASSUNG: cfg["varianten"][FASSUNG]}
    return cfg


def vorab_ok() -> bool:
    """Ist die Regeldatei des Bots versiegelt, und passen die Runde "Kirons Notizen" und ihre Quelldateien zu ihren
    Siegeln? Nur dann öffnet der Bot etwas."""
    from suche.runde1 import journal_lines, last_value, sha256_text
    if not VORAB.exists() or lade_cfg(pruefen=True) is None:
        return False
    return last_value(journal_lines(), KEY) == sha256_text(VORAB.read_text(encoding="utf-8"))


def regel(cfg: dict) -> dict:
    """Die Zahlen der Grundregel ausbruch4h, so wie die Fassung sie nutzt (nr.regel_cfg)."""
    spec = cfg["varianten"][FASSUNG]
    return nr.regel_cfg(cfg, spec)["regeln"][spec["basis"]]


# --------------------------------------------------------------------------------------------------------------------
# Zeit, Kerzen, Signal (ohne Netz, außer stundenkerzen)

def _ny(idx) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(idx).tz_localize("UTC").tz_convert(rb.NY).tz_localize(None)


def _nymin(idx) -> np.ndarray:
    ny = _ny(idx)
    return np.asarray(ny.hour * 60 + ny.minute, dtype=np.int64)


def schluessel(t: np.ndarray, nymin: np.ndarray) -> np.ndarray:
    """4-Std.-Kerze jeder Zeile, genau wie in rueckblick.regel_ausbruch4h (y2._kerzen_4h)."""
    ms18 = (np.asarray(nymin, dtype=np.int64) - 18 * 60) % 1440
    tag18 = (np.asarray(t, dtype="datetime64[ns]") - ms18.astype("timedelta64[m]")).astype("datetime64[D]").astype(np.int64)
    return tag18 * 6 + ms18 // 240


def _block(zeiten) -> np.ndarray:
    idx = pd.DatetimeIndex(zeiten)
    return schluessel(idx.values.astype("datetime64[ns]"), _nymin(idx))


def grenze(now: pd.Timestamp) -> pd.Timestamp:
    """Beginn der laufenden 4-Std.-Kerze als UTC: die erste Minute nach der letzten fertigen Kerze, im Test die Zeile
    des Einstiegs."""
    h = pd.Timestamp(now).floor("h")
    kand = pd.DatetimeIndex([h - k * STUNDE for k in range(6)])        # eine Kerze dauert höchstens 5 Stunden
    b = _block(kand)
    return kand[b == b[0]].min()


def naechste_grenze(now: pd.Timestamp) -> pd.Timestamp:
    h = pd.Timestamp(now).floor("h")
    kand = pd.DatetimeIndex([h + k * STUNDE for k in range(7)])
    b = _block(kand)
    return kand[b != b[0]].min()


def handelstag(t) -> int:
    """Handelstag (endet 17:00 Uhr New York) als Tageszahl, wie `tag` in den Kursdateien des Tests."""
    ny = _ny([pd.Timestamp(t)])[0]
    return int(((ny + pd.Timedelta(hours=7)).normalize() - pd.Timestamp("1970-01-01")).days)


def tagesende(t: pd.Timestamp) -> pd.Timestamp:
    """Ende des Handelstags (17:00 Uhr New York), in den t fällt, als UTC."""
    tag = pd.Timestamp("1970-01-01") + pd.Timedelta(days=handelstag(t))
    return (tag + pd.Timedelta(hours=17)).tz_localize(rb.NY).tz_convert("UTC").tz_localize(None)


def gesperrt(t, p: dict, termine: np.ndarray) -> bool:
    """Sperre des Tests zur Minute t: 20:55 bis 23:05 UTC und 15 Minuten um Fed, CPI und NFP."""
    t = np.datetime64(pd.Timestamp(t), "ns")
    utc_min = int((t - t.astype("datetime64[D]")) / rb.MIN)
    if p["sperre_utc"][0] <= utc_min <= p["sperre_utc"][1]:
        return True
    return bool(len(termine) and np.min(np.abs((termine - t) / rb.MIN)) <= p["termin_sperre_min"])


def stundenkerzen(client, epic: str, von: pd.Timestamp, bis: pd.Timestamp) -> pd.DataFrame:
    """Fertige Stundenkerzen (Bid) von `von` bis `bis`, in Abrufen zu je 40 Tagen (nur lesen)."""
    from suche.demo_bots import frame
    teile, ende = [], pd.Timestamp(bis)
    while ende > von:
        ab = max(pd.Timestamp(von), ende - pd.Timedelta(days=40))
        teile.extend(client._get(f"/prices/{epic}", resolution="HOUR", max=1000,
                                 **{"from": ab.strftime(FMT), "to": ende.strftime(FMT)}).get("prices", []))
        ende = ab
    bars, _ = frame(teile)
    if not len(bars):
        return pd.DataFrame(columns=SPALTEN, dtype=float, index=pd.DatetimeIndex([]))
    bars = bars[~bars.index.duplicated(keep="last")].sort_index()
    return bars[bars.index + STUNDE <= bis][SPALTEN]


def zeilen(stunden: pd.DataFrame, t_g: pd.Timestamp, bid: float) -> tuple[dict, int]:
    """Die Kursdatei des Tests aus Stundenkerzen: jede fertige Stundenkerze vor t_g als zwölf gleiche 5-Minuten-Zeilen,
    dann die Einstiegszeile zur Zeit t_g mit dem aktuellen Bid. Dahinter Zeilen mit demselben Bid bis zum Ende des
    Handelstags, damit der laufende Tag als gültiger Tag zählt wie im Test (nur für den Tagestrend, sie liegen alle nach
    dem Einstieg). Rückgabe: Felder der npz-Datei und die Zeile des Einstiegs."""
    alt = stunden[stunden.index < t_g][SPALTEN]
    t_alt = (alt.index.values.astype("datetime64[ns]")[:, None] + np.arange(12) * FUENF).ravel()
    werte = {k: np.repeat(alt[s].to_numpy(float), 12) for k, s in zip("ohlc", SPALTEN)}
    ende = tagesende(t_g)
    t_neu = np.arange(np.datetime64(t_g, "ns"), np.datetime64(max(ende, t_g + STUNDE), "ns"), FUENF)
    t = np.r_[t_alt, t_neu].astype("datetime64[ns]")
    for k in "ohlc":
        werte[k] = np.r_[werte[k], np.full(len(t_neu), float(bid))]
    ny = _ny(t)
    tag = (ny + pd.Timedelta(hours=7)).normalize().values.astype("datetime64[D]")
    return {"t": t, **werte, "sp": np.zeros(len(t)), "nymin": np.asarray(ny.hour * 60 + ny.minute, dtype=np.int32),
            "tag": tag}, len(t_alt)


def markt_live(sym: str, stunden: pd.DataFrame, t_g: pd.Timestamp, bid: float, cfg: dict) -> tuple[nr.Markt, int]:
    """Der Markt des Tests (suche/notizen_runde.Markt) aus diesen Zeilen und die Zeile des Einstiegs."""
    felder, e = zeilen(stunden, t_g, bid)
    with tempfile.TemporaryDirectory() as tmp:
        np.savez(Path(tmp) / f"{sym}.npz", **felder)
        return nr.Markt(sym, Path(tmp), cfg), e


def signal(sym: str, stunden: pd.DataFrame, t_g: pd.Timestamp, bid: float, cfg: dict,
           termine: np.ndarray) -> dict:
    """Was der Test zur Zeit t_g (erste Minute nach der Signalkerze) auf diesem Markt sieht. `ok` heißt: Der Test nähme
    diesen Einstieg (ohne die Frage, ob schon ein Trade offen ist), dazu Richtung, Stop- und Ziel-Abstand. `warten`
    heißt: Es fehlen Kerzen, der nächste Lauf sieht noch einmal nach. Die Entscheidung trifft allein nr.signale, der
    Rest ist nur die Begründung für das Journal."""
    out = {"markt": sym, "grenze": str(t_g), "richtung": 0, "trend": None, "dist": None, "ziel_abstand": None,
           "ok": False, "warten": False, "ergebnis": ""}
    alt = stunden[stunden.index < t_g]
    if not len(alt) or alt.index[-1] != t_g - STUNDE:
        # Im Test verfällt ein Signal, wenn nach der Signalkerze eine Lücke liegt. Live kann die letzte Stundenkerze
        # auch nur noch nicht da sein, darum sieht der nächste Lauf in der Frist noch einmal nach.
        return {**out, "warten": True, "ergebnis": "die letzte Stundenkerze vor dem Schluss fehlt (Markt war zu oder die "
                                                   "Kerze ist noch nicht da)"}
    m, e = markt_live(sym, stunden, t_g, bid, cfg)
    g = int(m.gpos[m.tix[e]])
    fertige_tage = int(np.searchsorted(m.gi, m.tix[e]))           # gültige Handelstage vor dem Tag des Einstiegs
    out["tageskerzen"] = fertige_tage
    if fertige_tage < MIN_TAGESKERZEN:
        return {**out, "warten": True, "ergebnis": f"zu wenig Kerzen vom Broker ({fertige_tage} fertige Handelstage, "
                                                   f"nötig {MIN_TAGESKERZEN})"}
    treffer = [s for s in nr.signale(FASSUNG, m, cfg, termine) if int(s["i0"]) == e]
    # Begründung wie in rueckblick.regel_ausbruch4h
    p = regel(cfg)
    k = y2._kerzen_4h(m)
    j = int(np.searchsorted(k["b"], e - 1))                       # die Signalkerze endet mit der Zeile vor dem Einstieg
    n = int(p["kanal"])
    hh, ll = (pd.Series(k["H"]).rolling(n).max().shift(1).to_numpy(),
              pd.Series(k["L"]).rolling(n).min().shift(1).to_numpy())
    ueber, unter = k["C"] > hh, k["C"] < ll
    d = 1 if (ueber[j] and not ueber[j - 1]) else (-1 if (unter[j] and not unter[j - 1]) else 0)
    trend = int(m.trend_vor[g]) if g >= 0 else 0
    out.update(richtung=d, schluss=float(k["C"][j]), hoch_davor=float(hh[j]), tief_davor=float(ll[j]),
               trend=None if d == 0 else bool(trend == d), tagestrend=trend, kerzen_5min=int(k["n"][j]),
               gesperrt=gesperrt(t_g, p, termine))
    if treffer:
        s = treffer[0]
        return {**out, "ok": True, "richtung": int(s["d"]), "trend": True, "dist": round(float(s["sd"]), 6),
                "ziel_abstand": round(float(s["zd"]), 6), "ergebnis": f"{SEITE[int(s['d'])]}-Ausbruch mit dem Tagestrend"}
    if d == 0:
        return {**out, "ergebnis": "kein Ausbruch"}
    if out["kerzen_5min"] < p["min_kerzen"]:
        return {**out, "ergebnis": f"{SEITE[d]}-Ausbruch, aber die Kerze hat zu wenig Kurse"}
    if trend != d:
        return {**out, "ergebnis": f"{SEITE[d]}-Ausbruch gegen den Tagestrend"}
    if out["gesperrt"]:
        return {**out, "ergebnis": f"{SEITE[d]}-Ausbruch in der Sperre (Handelspause oder Termin)"}
    return {**out, "ergebnis": f"{SEITE[d]}-Ausbruch, aber kein Einstieg nach der Regel"}


def kerzen_seit(stunden: pd.DataFrame, t_g: pd.Timestamp, now: pd.Timestamp) -> int:
    """So viele 4-Std.-Kerzen sind seit dem Einstieg fertig: Kerzen mit mindestens einer Stundenkerze ab t_g, die vor
    der laufenden Kerze liegen. So zählt der Test (j + halte_kerzen, nur Kerzen mit Kursen)."""
    s = stunden[(stunden.index >= t_g) & (stunden.index + STUNDE <= pd.Timestamp(now))]
    if not len(s):
        return 0
    b = _block(s.index)
    return int(len(np.unique(b[b < _block([pd.Timestamp(now)])[0]])))


def groesse(dist: float, q) -> tuple[float | None, str]:
    """Größe für RISIKO_EUR bis zum Stop, auf die Schrittweite des Brokers abgerundet, mindestens die kleinste Größe.
    None, wenn das Runden das Risiko mehr als verdoppeln würde."""
    if not q.eur_rate or not dist > 0:
        return None, "kein Kurs EUR zur Währung des Markts oder kein Stopabstand"
    lot = q.lot or 1.0
    roh = RISIKO_EUR * q.eur_rate / (dist * lot)
    step = q.size_step or q.min_size
    size = round(max(math.floor(round(roh / step, 9)) * step, q.min_size), 8)
    risiko = size * lot * dist / q.eur_rate
    if risiko > MAX_RISIKO_FAKTOR * RISIKO_EUR:
        return None, f"kleinste Größe zu grob ({risiko:.2f} € Risiko statt {RISIKO_EUR:.0f} €)"
    return size, ""


def pf(r) -> float | None:
    return rb.pf(np.asarray(r, dtype=float)) if len(r) else None


def bewertung(trades: list[dict]) -> dict:
    r = [float(t["r"]) for t in trades]
    n = len(r)
    g = pf(r)
    if n >= URTEIL_NACH:
        erste = r[:URTEIL_NACH]
        ok = (pf(erste) or 0) >= URTEIL_PF and sum(erste) > 0
        text = ("bestanden nach 40 Trades, Kiron entscheidet über den nächsten Schritt" if ok else
                "durchgefallen nach 40 Trades, Vorschlag an Kiron: stoppen oder neue Regeln mit neuem Vorab")
    elif n >= ZWISCHEN_NACH and (g or 0) < ZWISCHEN_PF:
        text = f"Zwischencheck nach {n} Trades: Gewinnfaktor unter {ZWISCHEN_PF}, Vorschlag an Kiron: stoppen"
    else:
        text = f"läuft ({n} von {URTEIL_NACH} Trades)"
    je = {}
    for t in trades:
        x = je.setdefault(t.get("markt") or "?", {"trades": 0, "summe_r": 0.0})
        x["trades"] += 1
        x["summe_r"] = round(x["summe_r"] + float(t["r"]), 3)
    return {"trades": n, "pf_r": None if g is None else round(float(min(g, 999.0)), 3), "summe_r": round(float(sum(r)), 2),
            "trefferquote": round(sum(x > 0 for x in r) / n, 3) if n else None,
            "summe_eur": round(float(sum(float(t.get("pnl_eur") or 0) for t in trades)), 2), "je_markt": je,
            "urteil": text}


_num = sb._num
_jetzt = sb._jetzt


def _zeit(x, ersatz: pd.Timestamp) -> pd.Timestamp:
    try:
        t = _jetzt(pd.Timestamp(x))
        return ersatz if pd.isna(t) else t
    except (TypeError, ValueError):
        return ersatz


def _rund(x: float, q) -> float:
    return round(float(x), q.decimals if q.decimals < 6 else 2)


# --------------------------------------------------------------------------------------------------------------------
# Ein Lauf

class Lauf:
    """Ein Lauf auf dem Demokonto für alle drei Märkte. Alle Order- und Schließ-Aufrufe gehen über diese Klasse, damit
    ein Trockenlauf (send_orders=False) nichts beim Broker ändert."""

    def __init__(self, client, state: dict, now: datetime, send_orders: bool = True, cfg: dict | None = None,
                 termine: np.ndarray | None = None):
        self.client = client
        self.st = copy.deepcopy(state or {})
        self.now = _jetzt(now)
        self.stamp = self.now.isoformat(timespec="seconds")
        self.send = send_orders
        self.cfg = cfg
        self.termine = termine if termine is not None else np.array([], dtype="datetime64[ns]")
        self.log: list[dict] = []
        self.fertige: list[dict] = []
        self.q = None
        self.sym = ""
        self.epic = ""
        self.eigene_zu: set[str] = set()
        self.blick: dict = {}
        for k, v in (("format", 1), ("start", self.stamp), ("summe_r", 0.0), ("trades", 0), ("maerkte", {})):
            self.st.setdefault(k, v)
        for sym in MAERKTE:
            self.st["maerkte"].setdefault(sym, {"trade": None})

    @property
    def mst(self) -> dict:
        return self.st["maerkte"][self.sym]

    def ev(self, event: str, **kw) -> None:
        self.log.append({"time": self.stamp, "event": event, "markt": self.sym or None, **kw})

    def kurs_raus(self, d: int) -> float:
        """Zu diesem Kurs schließt eine Position zum Markt: Kauf am Bid, Verkauf am Ask."""
        return self.q.bid if d > 0 else self.q.offer

    def nur_mein_konto(self) -> None:
        if not KONTO or str(self.client.account_id) != KONTO:
            raise RuntimeError(f"aktives Konto ist nicht {KONTO_NAME}, nichts gesendet")

    def kerzen(self, von: pd.Timestamp) -> pd.DataFrame | None:
        try:
            return stundenkerzen(self.client, self.epic, von, self.now)
        except Exception as err:            # noqa: BLE001 - der nächste Lauf versucht es wieder
            print(f"Stundenkerzen {self.epic} nicht lesbar: {err}")
            self.blick.setdefault(self.sym, {})["wartet"] = "Stundenkerzen nicht lesbar"
            return None

    def warte(self, text: str) -> None:
        self.blick.setdefault(self.sym, {})["wartet"] = text

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
        level, offen = belegt_pruefung.belegt(self.client, conf, tr["dealId"], self.kurs_raus(tr["richtung"]),
                                              float(tr["dist"]))
        if level is None:                   # nichts buchen: der nächste Lauf schließt wieder oder liest den Schlusskurs
            tr["schliessen_versucht"] = warum
            self.ev("Schluss nicht belegt", dealId=tr["dealId"], warum=warum, **offen)
            return False
        self.abschluss(tr, level, warum, self.now)
        return True

    def schluss_beim_broker(self, tr: dict) -> tuple[float | None, str, pd.Timestamp]:
        """Schlusskurs, Quelle (SL, TP, CLOSE_OUT, USER ...) und Zeit aus der Kontoaktivität zu dieser Position. Der
        Broker gibt je Abruf höchstens einen Tag her, darum die letzten 23 Std. 59 Min. (None, "", jetzt), wenn dort
        kein Schluss steht."""
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
        d, dist = int(tr["richtung"]), float(tr["dist"])
        naechte = max(handelstag(wann) - handelstag(tr["grenze"]), 0)
        gebuehr_r = float(tr["satz_nacht"]) * naechte / 365.0 * float(tr["entry"]) / dist
        r_roh = d * (level - float(tr["entry"])) / dist
        pnl = float(tr["size"]) * float(tr.get("lot") or 1.0) * d * (level - float(tr["entry"]))
        rate = _num(tr.get("eur_rate")) or (self.q.eur_rate if self.q else None)
        rec = {**{k: tr.get(k) for k in ("id", "markt", "epic", "richtung", "grenze", "dealId", "size", "entry",
                                         "stop", "ziel", "dist", "opened_utc", "spaet_min", "kerzen")},
               "seite": SEITE[d], "exit": round(level, 4), "grund": grund,
               "closed_utc": pd.Timestamp(wann).isoformat(timespec="seconds"), "naechte": naechte,
               "r_roh": round(r_roh, 3), "gebuehr_r": round(gebuehr_r, 3), "r": round(r_roh - gebuehr_r, 3),
               "pnl_waehrung": round(pnl, 2), "pnl_eur": round(pnl / rate, 2) if rate else None, **mehr}
        self.fertige.append(rec)
        self.eigene_zu.add(str(tr.get("dealId")))
        self.mst["letzter_schluss"] = rec["closed_utc"]
        self.mst["trade"] = None
        self.st["summe_r"] = round(float(self.st["summe_r"]) + rec["r"], 3)
        self.st["trades"] = int(self.st["trades"]) + 1
        self.ev("Trade fertig", trade=tr["id"], seite=rec["seite"], grund=grund, r=rec["r"], pnl_eur=rec["pnl_eur"])
        if self.st.get("pausiert") is None and self.st["summe_r"] <= PAUSE_R:
            self.st["pausiert"] = {"seit": self.stamp, "grund": f"Summe R seit Start {self.st['summe_r']} (Grenze "
                                                                f"{PAUSE_R}), zurück nur mit Kirons Entscheidung"}
            self.ev("Pause", grund=self.st["pausiert"]["grund"])

    def abgleich(self, eigene: list[dict]) -> None:
        """Ist der offene Trade beim Broker zu (Stop oder Ziel)? Und: Liegt eine Order ohne Bestätigung jetzt als
        Position da?"""
        pos = {str(p["position"].get("dealId")): p["position"] for p in eigene}
        offen = self.mst.get("ungeklaert")
        if offen and self.mst.get("trade") is None:
            self.mst["ungeklaert"] = None
            neu = [p for i, p in pos.items() if i not in set(offen.get("vorher") or [])
                   and p.get("direction") == ("BUY" if offen["richtung"] > 0 else "SELL")
                   and abs((_num(p.get("size")) or 0) - offen["size"]) < 1e-9]
            if len(neu) == 1:
                self.uebernehmen(neu[0], offen, offen["seit"])
            else:
                self.ev("Order ohne Bestätigung liegt nicht beim Broker", grenze=offen["grenze"], gefunden=len(neu))
        tr = self.mst.get("trade")
        if not tr:
            return
        if tr["dealId"] in pos:                            # Stop und Ziel so, wie sie beim Broker stehen
            tr["stop"] = _num(pos[tr["dealId"]].get("stopLevel")) or tr.get("stop")
            tr["ziel"] = _num(pos[tr["dealId"]].get("profitLevel")) or tr.get("ziel")
            tr.pop("weg_seit", None)
            return
        level, quelle, wann = self.schluss_beim_broker(tr)
        geschaetzt = level is None
        seit = tr.setdefault("weg_seit", self.stamp)
        if geschaetzt and self.now - pd.Timestamp(seit) < SCHLUSS_WARTEN:
            if seit == self.stamp:
                self.ev("Position beim Broker zu, Schlusskurs noch nicht lesbar", trade=tr["id"])
            return
        d = int(tr["richtung"])
        if geschaetzt:                                     # Ziel, wenn der Kurs jetzt auf der Gewinnseite steht
            gewinn = d * (self.kurs_raus(d) - float(tr["entry"])) > 0
            quelle = "TP" if gewinn and tr.get("ziel") else "SL"
            level = tr.get("ziel") if quelle == "TP" else (tr.get("stop") or float(tr["entry"]) - d * float(tr["dist"]))
            wann = pd.Timestamp(seit)
        if quelle == "SL":
            grund = "stop"
        elif quelle == "TP":
            grund = "ziel"
        elif tr.get("schliessen_versucht"):
            grund = tr["schliessen_versucht"]
        else:
            grund = f"beim Broker ({quelle or 'unbekannt'})"
        self.abschluss(tr, float(level), grund, wann, **({"exit_geschaetzt": True} if geschaetzt else {}))

    def uebernehmen(self, p: dict, plan: dict, opened_utc: str) -> None:
        """Macht aus einer Position beim Broker den offenen Trade des Bots."""
        d = int(plan["richtung"])
        level = _num(p.get("level")) or (self.q.offer if d > 0 else self.q.bid)
        self.mst["trade"] = {
            "id": f"{self.epic} {pd.Timestamp(plan['grenze']):%Y-%m-%dT%H:%M}", "markt": self.sym, "epic": self.epic,
            "richtung": d, "grenze": plan["grenze"], "dealId": str(p.get("dealId")), "size": plan["size"],
            "entry": float(level), "stop": _num(p.get("stopLevel")) or plan["stop"],
            "ziel": _num(p.get("profitLevel")) or plan["ziel"], "dist": plan["dist"], "bid_ein": plan["bid"],
            "opened_utc": opened_utc, "spaet_min": plan.get("spaet_min"), "kerzen": 0,
            "halte_kerzen": plan["halte_kerzen"], "bis_utc": plan["bis_utc"], "satz_nacht": plan["satz_nacht"],
            "lot": plan["lot"], "eur_rate": plan["eur_rate"]}
        self.ev(SEITE[d] + " eröffnet", **{k: self.mst["trade"][k] for k in ("id", "dealId", "size", "entry", "stop",
                                                                            "ziel", "dist", "spaet_min")})

    # ---- Führung des offenen Trades ----

    def fuehren(self) -> None:
        """Ausstieg zum Markt, sobald nach dem Einstieg halte_kerzen 4-Std.-Kerzen fertig sind, spätestens zur
        Haltezeit des Tests. Die Zahlen stehen im Trade selbst, so führt der Bot ihn auch ohne lesbare Regeldatei."""
        tr = self.mst.get("trade")
        if not tr or tr.get("weg_seit"):
            return
        zu_alt = self.now >= pd.Timestamp(tr["bis_utc"])
        t_g = pd.Timestamp(tr["grenze"])
        st = self.kerzen(t_g)
        n = kerzen_seit(st, t_g, self.now) if st is not None else None
        if n is not None and n != tr.get("kerzen"):
            tr["kerzen"] = n
        if not zu_alt and (n is None or n < int(tr["halte_kerzen"])):
            return
        if not self.q.tradeable:
            self.warte("Ausstieg fällig, Markt zu")
            return
        self.schliesse(tr, "haltezeit" if zu_alt and (n is None or n < int(tr["halte_kerzen"])) else "zeit")

    # ---- Neues Signal ----

    def pruefen(self, eigene: list[dict], fremde: list[dict], available_eur: float | None) -> None:
        """Einmal je 4-Std.-Kerze und Markt, in den ersten FRIST Minuten nach ihrem Schluss: Gibt es ein Signal, und
        darf der Bot es nehmen?"""
        t_g = grenze(self.now)
        key = str(t_g)
        if self.mst.get("letzte_grenze") == key:
            return

        def fertig(ergebnis: str, **kw) -> None:
            self.mst["letzte_grenze"] = key
            self.mst["letzte_pruefung"] = {"grenze": key, "ergebnis": ergebnis, **kw}

        if self.now - t_g > FRIST:
            if not self.send:
                return
            return fertig("Start des Bots mitten in der Kerze" if self.mst.get("letzte_grenze") is None else
                          "verfallen: In der Frist kam kein Lauf zum Zug (Markt zu, Stundenkerze fehlte oder Lauf fiel aus)")
        if self.mst.get("trade") is not None:
            return fertig("ein Trade ist offen, höchstens einer je Markt")
        zuletzt = self.mst.get("letzter_schluss")
        if zuletzt and pd.Timestamp(zuletzt) >= t_g:
            return fertig("der letzte Trade endete erst nach dem Schluss dieser Kerze")
        if self.cfg is None:
            self.warte("Regeldateien nicht lesbar (Siegel einer Quelldatei passt nicht)")
            return
        p = regel(self.cfg)
        if gesperrt(t_g, p, self.termine):
            return fertig("Sperre zur ersten Minute nach der Kerze (Handelspause oder Termin)")
        if not self.q.tradeable:
            self.warte("Markt zu")
            return
        if gesperrt(self.now, p, self.termine):
            self.warte("Termin-Sperre")
            return
        kurz = self.kerzen(t_g - 3 * STUNDE)               # ein kleiner Abruf: Ist die letzte Stundenkerze schon da?
        if kurz is None:
            return
        if not len(kurz) or kurz.index[-1] != t_g - STUNDE:
            self.warte("die letzte Stundenkerze vor dem Schluss fehlt")
            return
        stunden = self.kerzen(self.now - pd.Timedelta(days=TAGE_KERZEN))
        if stunden is None:
            return
        sig = signal(self.sym, stunden, t_g, self.q.bid, self.cfg, self.termine)
        self.blick.setdefault(self.sym, {})["signal"] = sig
        if sig["warten"]:
            self.warte(sig["ergebnis"])
            return
        kurz_info = {k: sig.get(k) for k in ("richtung", "schluss", "hoch_davor", "tief_davor", "trend", "dist")}
        if not sig["ok"]:
            if sig["richtung"]:
                self.ev("Ausbruch ohne Einstieg", grenze=key, grund=sig["ergebnis"], **kurz_info)
            return fertig(sig["ergebnis"], **kurz_info)
        self.einstieg(sig, t_g, eigene, fremde, available_eur, fertig, kurz_info, p)

    def einstieg(self, sig: dict, t_g: pd.Timestamp, eigene: list[dict], fremde: list[dict],
                 available_eur: float | None, fertig, kurz_info: dict, p: dict) -> None:
        q, d = self.q, int(sig["richtung"])
        dist, zd = float(sig["dist"]), float(sig["ziel_abstand"])
        stop, ziel = _rund(q.bid - d * dist, q), _rund(q.bid + d * zd, q)   # beide am Bid gemessen wie im Test
        gruende = []
        if self.st.get("pausiert"):
            gruende.append(f"Pause ab {PAUSE_R:.0f} R")
        if not vorab_ok():
            gruende.append("Regeln nicht festgelegt (Prüfsumme im Protokoll fehlt oder passt nicht)")
        if fremde:
            gruende.append(f"fremde Position auf {self.epic} im Konto")
        size, warum = groesse(dist, q)
        if size is None:
            gruende.append(warum)
        else:
            marge = size * (q.lot or 1) * q.bid * q.margin_pct / 100 / (q.eur_rate or 1)
            if available_eur is not None and marge > MARGE_ANTEIL * available_eur:
                gruende.append(f"Margin {marge:.0f} € wäre mehr als {MARGE_ANTEIL:.0%} des freien Gelds ({available_eur:.0f} €)")
        abstand = min(abs(q.offer - stop), abs(ziel - q.offer)) if d > 0 else min(abs(stop - q.bid), abs(q.bid - ziel))
        if q.min_dist and abstand < q.min_dist:
            gruende.append("Stop oder Ziel näher als der Mindestabstand des Brokers")
        spaet = round((self.now - t_g).total_seconds() / 60, 1)
        info = {"seite": SEITE[d], "grenze": str(t_g), "dist": round(dist, 4), "stop": stop, "ziel": ziel,
                "spaet_min": spaet, "bid": q.bid}
        if gruende:
            self.ev("Einstieg ausgelassen", **info, gruende=gruende)
            return fertig("Signal, aber kein Einstieg: " + "; ".join(gruende), **kurz_info)
        if not self.send:
            self.ev("würde " + ("kaufen" if d > 0 else "verkaufen"), **info, size=size)
            return
        fertig(f"{SEITE[d]} gesendet", **kurz_info)        # vor der Order: nie eine zweite Order für dieselbe Kerze
        vorher = {str(x["position"].get("dealId")) for x in eigene + fremde}
        satz = self.cfg["kosten"]["nacht_pro_jahr"]["index"]["long" if d > 0 else "short"]
        plan = {"grenze": str(t_g), "richtung": d, "size": size, "dist": round(dist, 6), "stop": stop, "ziel": ziel,
                "bid": q.bid, "spaet_min": spaet, "halte_kerzen": int(p["halte_kerzen"]),
                "bis_utc": str(t_g + pd.Timedelta(days=int(p["halte_tage_max"]))), "satz_nacht": float(satz),
                "lot": q.lot or 1.0, "eur_rate": q.eur_rate}
        body = {"epic": self.epic, "direction": "BUY" if d > 0 else "SELL", "size": size, "guaranteedStop": False,
                "stopLevel": stop, "profitLevel": ziel}
        conf = None
        try:
            self.nur_mein_konto()
            ref = self.client._request("POST", "/positions", json=body).json()["dealReference"]
            conf = self.client.confirm(ref) or {}
        except Exception as err:            # noqa: BLE001 - kein zweiter Versuch, damit nichts doppelt entsteht
            self.ev("Order ohne Bestätigung", **info, fehler=str(err)[:200])
            fertig(f"{SEITE[d]} gesendet, Bestätigung fehlt", **kurz_info)
        if conf is not None and str(conf.get("dealStatus") or "").upper() == "REJECTED":
            self.ev("Order abgelehnt", **info, grund=conf.get("reason"))
            return fertig(f"Signal, aber die Order wurde abgelehnt ({conf.get('reason')})", **kurz_info)
        try:
            jetzt = [x["position"] for x in self.client.positions() if (x.get("market") or {}).get("epic") == self.epic]
        except Exception as err:            # noqa: BLE001
            print(f"Positionen nach der Order nicht lesbar: {err}")
            jetzt = None
        neu = [x for x in jetzt or [] if str(x.get("dealId")) not in vorher
               and x.get("direction", "BUY" if d > 0 else "SELL") == ("BUY" if d > 0 else "SELL")]
        deal = ((conf or {}).get("affectedDeals") or [{}])[0].get("dealId") or (conf or {}).get("dealId")
        if len(neu) == 1 or (conf and deal):                # sonst bestätigt, aber noch nicht in der Liste der Positionen
            fertig(f"{SEITE[d]} eröffnet", **kurz_info)
            return self.uebernehmen(neu[0] if len(neu) == 1 else {"dealId": deal, "level": conf.get("level")}, plan,
                                    self.stamp)
        # keine Bestätigung und keine Position gefunden: Der nächste Lauf sucht sie an Richtung und Größe
        self.mst["ungeklaert"] = {**plan, "seit": self.stamp, "vorher": sorted(vorher)}


def run(client, state: dict, now: datetime, send_orders: bool = True) -> tuple[dict, list[dict], list[dict], dict]:
    """Ein Lauf. Rückgabe: neuer Stand, Ereignisse, fertige Trades, Blick (für das Cockpit)."""
    from suche.demo_bots import eur_rate, quote_from_market

    lauf = Lauf(client, state, now, send_orders, cfg=lade_cfg(pruefen=False), termine=rb.termine_utc())
    if not KONTO or KONTO.endswith(HAUPT_ENDUNG):
        lauf.ev("kein Konto", konto=KONTO_NAME)
        return lauf.st, lauf.log, [], {"status": f"{KONTO_NAME} steht nicht in journal/konten.json, nichts gehandelt"}
    konto = next((a for a in client.accounts() if str(a.get("accountId")) == KONTO), None)
    if konto is None:
        lauf.ev("kein Konto", konto=KONTO_NAME)
        return lauf.st, lauf.log, [], {"status": f"{KONTO_NAME} nicht gefunden, nichts gehandelt"}
    available = _num((konto.get("balance") or {}).get("available"))
    vorher = client.account_id
    client.switch_account(KONTO)
    try:
        alle = client.positions()
        kurse: dict = {}
        for sym, epic in MAERKTE.items():
            lauf.sym, lauf.epic, lauf.eigene_zu = sym, epic, set()
            lauf.q = q = quote_from_market(client.market(epic), None)
            q.eur_rate = eur_rate(client, q.currency, kurse)
            hier = [x for x in alle if (x.get("market") or {}).get("epic") == epic]
            tr = lauf.mst.get("trade")
            meine = {tr["dealId"]} if tr else set()
            if lauf.mst.get("ungeklaert"):
                meine |= {str(x["position"].get("dealId")) for x in hier
                          if str(x["position"].get("dealId")) not in set(lauf.mst["ungeklaert"].get("vorher") or [])}
            lauf.abgleich([x for x in hier if str(x["position"].get("dealId")) in meine])
            lauf.fuehren()
            tr = lauf.mst.get("trade")
            meine = ({tr["dealId"]} if tr else set()) | lauf.eigene_zu
            fremde = [x for x in hier if str(x["position"].get("dealId")) not in meine]
            fremd = sorted(str(x["position"].get("dealId")) for x in fremde)
            if fremd != (lauf.mst.get("fremd") or []):     # nur melden, wenn sich etwas ändert
                lauf.mst["fremd"] = fremd
                if fremd:
                    lauf.ev("fremde Position auf dem Markt", deals=fremd)
            eigene = [x for x in hier if str(x["position"].get("dealId")) in meine]
            lauf.pruefen(eigene, fremde, available)
            lauf.blick.setdefault(sym, {})["kurs"] = q.bid
        lauf.sym = ""
        lauf.st["stand"] = lauf.stamp
        return lauf.st, lauf.log, lauf.fertige, blick_auf(lauf)
    finally:
        with contextlib.suppress(Exception):
            if vorher and vorher != KONTO:
                client.switch_account(vorher)


def blick_auf(lauf: Lauf) -> dict:
    """Was der Bot gerade sieht (für das Cockpit)."""
    return {"naechste_4h_kerze_endet_utc": str(naechste_grenze(lauf.now)),
            "maerkte": {sym: {"epic": MAERKTE[sym], "letzte_pruefung": lauf.st["maerkte"][sym].get("letzte_pruefung"),
                              **lauf.blick.get(sym, {})} for sym in MAERKTE}}


# --------------------------------------------------------------------------------------------------------------------
# Journal und Cockpit

def status(st: dict) -> str:
    if st.get("pausiert"):
        return "Pause: " + st["pausiert"]["grund"]
    teile = []
    for sym, m in (st.get("maerkte") or {}).items():
        tr = m.get("trade")
        name = NAMEN.get(sym, sym)
        if tr and tr.get("weg_seit"):
            teile.append(f"{name}: Position beim Broker zu, der Bot liest den Schlusskurs")
        elif tr:
            teile.append(f"{name}: {SEITE[tr['richtung']]} offen ab {tr['entry']}, Stop {tr['stop']}, Ziel {tr['ziel']}, "
                         f"Ausstieg nach {tr['halte_kerzen']} fertigen 4-Std.-Kerzen (bisher {tr.get('kerzen') or 0})")
        elif m.get("ungeklaert"):
            teile.append(f"{name}: Order gesendet, Bestätigung fehlt, der nächste Lauf sieht nach")
    if teile:
        return ". ".join(teile)
    zuletzt = [m.get("letzte_pruefung") for m in (st.get("maerkte") or {}).values() if m.get("letzte_pruefung")]
    if not zuletzt:
        return "kein Trade offen, wartet auf den Schluss der nächsten 4-Std.-Kerze"
    p = max(zuletzt, key=lambda x: x["grenze"])
    return f"kein Trade offen. Letzte Kerze (bis {p['grenze'][:16]} UTC): {p['ergebnis']}"


def cockpit(st: dict, alle_trades: list[dict], blick: dict) -> dict:
    offen = [{k: m["trade"].get(k) for k in ("id", "markt", "epic", "richtung", "entry", "stop", "ziel", "size", "dist",
                                              "opened_utc", "kerzen")}
             for m in (st.get("maerkte") or {}).values() if m.get("trade")]
    return {"bot": BOT_ID, "name": NAME, "konto": KONTO_NAME, "stand": st.get("stand"), "start": st.get("start"),
            "pausiert": st.get("pausiert"), "status": status(st), "regel": REGEL, "backtest": TEST,
            "vorab": "suche/VORAB_welt_ausbruch4h_bot.yaml", "vorab_ok": vorab_ok(),
            "maerkte": {sym: NAMEN.get(sym, sym) for sym in MAERKTE}, "offen": offen,
            "zusammenfassung": bewertung(alle_trades), "letzte_trades": alle_trades[-10:], "blick": blick}


def _ohne_zeit(st: dict) -> dict:
    return {k: v for k, v in (st or {}).items() if k != "stand"}


def schreiben(st: dict, log: list[dict], fertige: list[dict], blick: dict, jdir: Path = JDIR,
              cockpit_pfad: Path = COCKPIT) -> bool:
    """Schreibt Zustand, Log, Trades und Cockpit. Hat sich außer der Uhrzeit nichts geändert, schreibt der Lauf nichts."""
    for p in (jdir, cockpit_pfad):
        if p.name in FREMDE_DATEIEN:
            raise RuntimeError(f"{p} gehört einem anderen Bot")
    pfad = jdir / "state.json"
    alt = json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else None
    if alt is not None and not log and not fertige and _ohne_zeit(alt) == _ohne_zeit(st) and cockpit_pfad.exists():
        return False
    jdir.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(st, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    for name, rows in (("log.jsonl", log), ("trades.jsonl", fertige)):
        if rows:
            with open(jdir / name, "a", encoding="utf-8") as fh:
                fh.writelines(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows)
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
        print("Keine Capital.com-Zugangsdaten, 4-Std.-Ausbruch DAX, FTSE, Nikkei übersprungen")
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
