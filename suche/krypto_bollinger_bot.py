"""Bollinger und RSI auf Bitcoin und Ether, umgedreht, live auf einem Capital.com-DEMOKONTO. Nie echtes Geld.

    python -m suche.krypto_bollinger_bot              # ein Lauf: offene Trades führen, nach einem Stundenschluss Signal?
    python -m suche.krypto_bollinger_bot --dry-run    # nur rechnen und zeigen, keine Order

Kirons Wahl vom 20.11.2026 11:53 UTC auf der Karte zu seinem Wunsch "Schatten soll direkt Live-Demo sein": "die paar
stärksten zu erst". Diese Fassung ist eine der zwei stärksten, die bisher nur gerechnet wurden. Die Regel ist die
Fassung bollinger_umkehr_krypto_weit aus suche/VORAB_notizen_runde.yaml, unverändert. Sie hat den Test NICHT
bestanden (suche/ergebnis_notizen_runde.md): 2024 bis 2026 1.150 Trades, Gewinnfaktor 1,07, die neuere Hälfte 0,98,
2026 allein 1,00. Das Schatten-Labor zählt dieselbe Fassung ohne Order unverändert weiter (suche/VORAB_schatten.yaml).
Regeln des Bots und Urteil stehen in suche/VORAB_krypto_bollinger_bot.yaml, Prüfsumme im Protokoll vor dem ersten
Trade. Ohne passende Prüfsumme öffnet der Bot nichts.

Regel, je Markt für sich (Stundenkerzen zur vollen UTC-Stunde):
- Grundregel bollinger_rsi: Schließt eine Stundenkerze unter dem unteren Bollinger-Band (20, 2) und liegt RSI 14 unter
  30, wäre das ein Kauf zurück zur Mitte. Über dem oberen Band mit RSI über 70 ein Verkauf. Liegt die Mitte des Bands
  nicht auf der Gewinnseite, gibt es kein Signal.
- Umgedreht (umkehr "weit"): Der Bot handelt die Gegenrichtung, also Verkauf unter dem unteren Band und Kauf über dem
  oberen. Stop 1,5 ATR 14 der Stundenkerzen, Ziel 2 R (3 ATR). Beide liegen beim Broker.
- Ausstieg zum Markt spätestens 24 Stunden nach dem Einstieg.
- Höchstens ein Trade je Markt, also höchstens zwei zugleich.

Live-Ausführung:
- Signal, Stop und Ziel rechnet die Funktion des Tests (suche/notizen_runde.signale) mit den Zahlen aus den
  versiegelten Dateien. Sie bekommt fertige Stundenkerzen von Capital.com, jede als zwölf gleiche 5-Minuten-Zeilen,
  dahinter eine Zeile zur ersten Minute nach der Signalkerze mit dem aktuellen Bid.
- Der Lauf kommt alle 15 Minuten. Gerechnet wird nur in den ersten 20 Minuten nach dem Schluss einer Stundenkerze.
- Nur Account 3, den er mit dem Bot Vortag GBP/JPY teilt (anderer Markt). Die Kontonummer liest er nach dem Namen aus
  journal/konten.json. Er kennt seine Positionen an der Deal-ID. Liegt eine fremde Position auf demselben Markt,
  öffnet er dort nichts Neues.
- Ab -25 R seit Start nichts Neues mehr (Sicherung), zurück nur mit Kirons Entscheidung.
- Er schreibt nur journal/krypto-bollinger/ und journal/krypto-bollinger.json.
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
from suche import youtube_runde as yr
from suche import youtube_runde2 as y2

ROOT = Path(nr.ROOT)
BOT_ID = "krypto-bollinger"
NAME = "Bollinger Krypto umgedreht (Bitcoin, Ether)"
KONTO_NAME = "Account 3"              # geteilt mit dem Bot r6-vortag-gbpjpy (GBP/JPY)
HAUPT_ENDUNG = sb.HAUPT_ENDUNG        # Hauptkonto des Gold-Bots, hier nie handeln
FASSUNG = "bollinger_umkehr_krypto_weit"
GRUNDREGEL = "bollinger_rsi"
RISIKO_EUR = 5.0
MAX_RISIKO_FAKTOR = 2.0               # Runden auf die kleinste Größe darf das Risiko höchstens verdoppeln
MARGE_ANTEIL = 0.4                    # eine Order darf höchstens diesen Teil des freien Gelds als Margin brauchen
PAUSE_R = -25.0
ZWISCHEN_NACH, ZWISCHEN_PF = 15, 0.6
URTEIL_NACH, URTEIL_PF = 40, 1.2
TAGE_KERZEN = 40                      # so viele Kalendertage Stundenkerzen je Signal-Rechnung (ein Abruf beim Broker)
MIN_TAGE = 20                         # mit weniger gültigen Handelstagen vor dem Einstieg rechnet der Bot kein Signal
FRIST = pd.Timedelta(minutes=20)      # so lange nach dem Schluss der Signalkerze darf der Bot noch einsteigen
SCHLUSS_WARTEN = pd.Timedelta(hours=1)     # so lange sucht der Bot den Schlusskurs beim Broker, dann schätzt er
STUNDE = pd.Timedelta(hours=1)
FUENF = np.timedelta64(5, "m")
FMT = "%Y-%m-%dT%H:%M:%S"
SPALTEN = ["open", "high", "low", "close"]
KEINE_TERMINE = np.array([], dtype="datetime64[ns]")       # die Regel kennt keine Termin-Sperre, Krypto keine Pause
VORAB = ROOT / "suche" / "VORAB_krypto_bollinger_bot.yaml"
KEY = "VORAB_krypto_bollinger_bot sha256 "
JDIR = ROOT / "journal" / "krypto-bollinger"
COCKPIT = ROOT / "journal" / "krypto-bollinger.json"
FREMDE_DATEIEN = sb.GOLD_BOT_DATEIEN + ("konten.json", "r6-bots.json", "welt-ausbruch4h.json")
SEITE = {1: "Kauf", -1: "Verkauf"}
NAMEN = {"BTCUSD": "Bitcoin", "ETHUSD": "Ether"}
REGEL = ("Bollinger und RSI auf Bitcoin und Ether, umgedreht (Fassung bollinger_umkehr_krypto_weit): Schließt eine "
         "Stundenkerze unter dem unteren Bollinger-Band (20, 2) mit RSI 14 unter 30, verkauft der Bot, über dem oberen "
         "Band mit RSI über 70 kauft er. Stop 1,5 ATR der Stundenkerzen, Ziel 2 R, Ausstieg spätestens nach 24 Stunden. "
         "Höchstens ein Trade je Markt, 5 € Risiko.")
TEST = ("Test NICHT bestanden (suche/ergebnis_notizen_runde.md): 2024 bis 2026 1.150 Trades (etwa 7,8 je Woche), "
        "Gewinnfaktor 1,07, neuere Hälfte 0,98, 2026 1,00, Bitcoin 0,97 und Ether 1,18. Auf 1.000 € mit 10 € je Trade "
        "im Rückblick etwa 16 € im Monat. Kirons Wahl vom 20.11.2026: eine der zwei stärksten Fassungen live testen.")


def _fassung_maerkte() -> list[str]:
    import yaml
    roh = yaml.safe_load(nr.VORAB.read_text(encoding="utf-8"))["notizen_runde"]["varianten"][FASSUNG]
    return list(roh["maerkte"])


MAERKTE = {sym: yr.KRYPTO[sym][1] for sym in _fassung_maerkte()}     # Name im Test -> Epic bei Capital.com


def konto_id(konten_daten: dict | None = None) -> str:
    """Die volle Kontonummer von Account 3 aus journal/konten.json, gesucht nach dem Namen (suche/mitnutzer.py
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
    """Die Zahlen der Grundregel bollinger_rsi, so wie die Fassung sie nutzt (nr.regel_cfg)."""
    spec = cfg["varianten"][FASSUNG]
    return nr.regel_cfg(cfg, spec)["regeln"][spec["basis"]]


# --------------------------------------------------------------------------------------------------------------------
# Zeit, Kerzen, Signal (ohne Netz, außer stundenkerzen)

def _ny(idx) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(idx).tz_localize("UTC").tz_convert(rb.NY).tz_localize(None)


def grenze(now: pd.Timestamp) -> pd.Timestamp:
    """Beginn der laufenden Stunde (UTC): die erste Minute nach der letzten fertigen Stundenkerze, im Test die Zeile
    des Einstiegs."""
    return pd.Timestamp(now).floor("h")


def naechste_grenze(now: pd.Timestamp) -> pd.Timestamp:
    return grenze(now) + STUNDE


def handelstag(t) -> int:
    """Handelstag (endet 17:00 Uhr New York) als Tageszahl, wie `tag` in den Kursdateien des Tests."""
    ny = _ny([pd.Timestamp(t)])[0]
    return int(((ny + pd.Timedelta(hours=7)).normalize() - pd.Timestamp("1970-01-01")).days)


def tagesende(t: pd.Timestamp) -> pd.Timestamp:
    """Ende des Handelstags (17:00 Uhr New York), in den t fällt, als UTC."""
    tag = pd.Timestamp("1970-01-01") + pd.Timedelta(days=handelstag(t))
    return (tag + pd.Timedelta(hours=17)).tz_localize(rb.NY).tz_convert("UTC").tz_localize(None)


def vorlauf_ab(t_g: pd.Timestamp) -> pd.Timestamp:
    """Ab hier holt der Bot Stundenkerzen für das Signal zur Grenze t_g: TAGE_KERZEN Tage minus eine Stunde, damit es
    auch mit 20 Minuten Verspätung ein einziger Abruf beim Broker bleibt (höchstens 40 Tage je Abruf)."""
    return pd.Timestamp(t_g) - pd.Timedelta(days=TAGE_KERZEN) + STUNDE


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
    Handelstags, mindestens eine Stunde (sie liegen alle nach dem Einstieg und ändern kein Signal, der Test braucht nur
    Zeilen nach dem Einstieg). Rückgabe: Felder der npz-Datei und die Zeile des Einstiegs."""
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
    """Der Markt des Tests (suche/notizen_runde.Markt, Krypto mit sieben Handelstagen) und die Zeile des Einstiegs."""
    felder, e = zeilen(stunden, t_g, bid)
    with tempfile.TemporaryDirectory() as tmp:
        np.savez(Path(tmp) / f"{sym}.npz", **felder)
        return nr.Markt(sym, Path(tmp), cfg), e


def _zahl(x) -> float | None:
    return round(float(x), 6) if x is not None and np.isfinite(x) else None


def signal(sym: str, stunden: pd.DataFrame, t_g: pd.Timestamp, bid: float, cfg: dict) -> dict:
    """Was der Test zur Zeit t_g (erste Minute nach der Signalkerze) auf diesem Markt sieht. `ok` heißt: Der Test nähme
    diesen Einstieg (ohne die Frage, ob schon ein Trade offen ist), dazu Richtung, Stop- und Ziel-Abstand. `warten`
    heißt: Es fehlen Kerzen, der nächste Lauf sieht noch einmal nach. Die Entscheidung treffen allein nr.signale und
    die Bedingungen von rueckblick.echte_trades, der Rest ist nur die Begründung für das Journal."""
    out = {"markt": sym, "grenze": str(t_g), "richtung": 0, "dist": None, "ziel_abstand": None, "ok": False,
           "warten": False, "ergebnis": ""}
    alt = stunden[stunden.index < t_g]
    if not len(alt) or alt.index[-1] != t_g - STUNDE:
        return {**out, "warten": True, "ergebnis": "die letzte Stundenkerze vor dem Schluss fehlt (Markt war zu oder die "
                                                   "Kerze ist noch nicht da)"}
    m, e = markt_live(sym, stunden, t_g, bid, cfg)
    g = int(m.gpos[m.tix[e]])
    fertige_tage = int(np.searchsorted(m.gi, m.tix[e]))           # gültige Handelstage vor dem Tag des Einstiegs
    out["tage"] = fertige_tage
    if fertige_tage < MIN_TAGE:
        return {**out, "warten": True, "ergebnis": f"zu wenig Kerzen vom Broker ({fertige_tage} fertige Handelstage, "
                                                   f"nötig {MIN_TAGE})"}
    treffer = [s for s in nr.signale(FASSUNG, m, cfg, KEINE_TERMINE) if int(s["i0"]) == e]
    # Begründung wie in youtube_runde2.regel_bollinger
    p = regel(cfg)
    k = y2._kerzen_1h(m)
    j = int(np.searchsorted(k["b"], e - 1))                       # die Signalkerze endet mit der Zeile vor dem Einstieg
    s_c = pd.Series(k["C"])
    mitte = s_c.rolling(p["bb_n"]).mean().to_numpy()
    sa = s_c.rolling(p["bb_n"]).std(ddof=0).to_numpy()
    oben, unten = mitte + p["bb_breite"] * sa, mitte - p["bb_breite"] * sa
    rsi = y2._rsi(k["C"], p["rsi_n"])
    atr = rb._wilder(k["tr"], p["atr_n"])
    c = float(k["C"][j])
    grund = 1 if (c < unten[j] and rsi[j] < p["rsi_unten"]) else (-1 if (c > oben[j] and rsi[j] > p["rsi_oben"]) else 0)
    out.update(richtung=-grund, schluss=c, mitte=_zahl(mitte[j]), oben=_zahl(oben[j]), unten=_zahl(unten[j]),
               rsi=_zahl(rsi[j]), atr=_zahl(atr[j]))
    handelbar = g >= 1 and bool(np.isfinite(m.atr_vor[g]))       # wie rueckblick.echte_trades
    if treffer and handelbar and treffer[0]["sd"] > 0:
        s = treffer[0]
        art = "unter dem unteren Band" if int(s["d"]) < 0 else "über dem oberen Band"
        return {**out, "ok": True, "richtung": int(s["d"]), "dist": round(float(s["sd"]), 6),
                "ziel_abstand": round(float(s["zd"]), 6), "ergebnis": f"{SEITE[int(s['d'])]}: Schluss {art}, umgedreht"}
    if grund == 0:
        return {**out, "ergebnis": "Schluss im Band oder RSI nicht extrem"}
    seite = SEITE[-grund]
    if treffer:
        return {**out, "ergebnis": f"{seite}-Signal, aber zu wenig Tage für den Test"}
    if d_mitte := (mitte[j] - bid) * grund:
        if not d_mitte > 0:
            return {**out, "ergebnis": f"{seite}-Signal, aber die Mitte des Bands liegt nicht auf der Gewinnseite der "
                                       f"Grundregel"}
    if not np.isfinite(atr[j]):
        return {**out, "ergebnis": f"{seite}-Signal, aber keine ATR"}
    return {**out, "ergebnis": f"{seite}-Signal, aber kein Einstieg nach der Regel"}


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
    """Ein Lauf auf dem Demokonto für beide Märkte. Alle Order- und Schließ-Aufrufe gehen über diese Klasse, damit
    ein Trockenlauf (send_orders=False) nichts beim Broker ändert."""

    def __init__(self, client, state: dict, now: datetime, send_orders: bool = True, cfg: dict | None = None):
        self.client = client
        self.st = copy.deepcopy(state or {})
        self.now = _jetzt(now)
        self.stamp = self.now.isoformat(timespec="seconds")
        self.send = send_orders
        self.cfg = cfg
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
                                         "stop", "ziel", "dist", "opened_utc", "spaet_min")},
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
            "opened_utc": opened_utc, "spaet_min": plan.get("spaet_min"), "bis_utc": plan["bis_utc"],
            "satz_nacht": plan["satz_nacht"], "lot": plan["lot"], "eur_rate": plan["eur_rate"]}
        self.ev(SEITE[d] + " eröffnet", **{k: self.mst["trade"][k] for k in ("id", "dealId", "size", "entry", "stop",
                                                                            "ziel", "dist", "spaet_min")})

    # ---- Führung des offenen Trades ----

    def fuehren(self) -> None:
        """Ausstieg zum Markt zur Haltezeit des Tests (24 Stunden nach der ersten Minute nach der Signalkerze). Die Zeit
        steht im Trade selbst, so führt der Bot ihn auch ohne lesbare Regeldatei."""
        tr = self.mst.get("trade")
        if not tr or tr.get("weg_seit") or self.now < pd.Timestamp(tr["bis_utc"]):
            return
        if not self.q.tradeable:
            self.warte("Ausstieg fällig, Markt zu")
            return
        self.schliesse(tr, "zeit")

    # ---- Neues Signal ----

    def pruefen(self, eigene: list[dict], fremde: list[dict], available_eur: float | None) -> None:
        """Einmal je Stundenkerze und Markt, in den ersten FRIST Minuten nach ihrem Schluss: Gibt es ein Signal, und
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
            return fertig("Start des Bots mitten in der Stunde" if self.mst.get("letzte_grenze") is None else
                          "verfallen: In der Frist kam kein Lauf zum Zug (Markt zu, Stundenkerze fehlte oder Lauf fiel aus)")
        if self.mst.get("trade") is not None:
            return fertig("ein Trade ist offen, höchstens einer je Markt")
        zuletzt = self.mst.get("letzter_schluss")
        if zuletzt and pd.Timestamp(zuletzt) >= t_g:
            return fertig("der letzte Trade endete erst nach dem Schluss dieser Kerze")
        if self.cfg is None:
            self.warte("Regeldateien nicht lesbar (Siegel einer Quelldatei passt nicht)")
            return
        if not self.q.tradeable:
            self.warte("Markt zu")
            return
        stunden = self.kerzen(vorlauf_ab(t_g))
        if stunden is None:
            return
        sig = signal(self.sym, stunden, t_g, self.q.bid, self.cfg)
        self.blick.setdefault(self.sym, {})["signal"] = sig
        if sig["warten"]:
            self.warte(sig["ergebnis"])
            return
        kurz_info = {k: sig.get(k) for k in ("richtung", "schluss", "mitte", "oben", "unten", "rsi", "atr", "dist")}
        if not sig["ok"]:
            if sig["richtung"]:
                self.ev("Signal ohne Einstieg", grenze=key, grund=sig["ergebnis"], **kurz_info)
            return fertig(sig["ergebnis"], **kurz_info)
        self.einstieg(sig, t_g, eigene, fremde, available_eur, fertig, kurz_info, regel(self.cfg))

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
        marge = None
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
                "spaet_min": spaet, "bid": q.bid, "margin_eur": None if marge is None else round(marge, 2)}
        if gruende:
            self.ev("Einstieg ausgelassen", **info, gruende=gruende)
            return fertig("Signal, aber kein Einstieg: " + "; ".join(gruende), **kurz_info)
        if not self.send:
            self.ev("würde " + ("kaufen" if d > 0 else "verkaufen"), **info, size=size)
            return
        fertig(f"{SEITE[d]} gesendet", **kurz_info)        # vor der Order: nie eine zweite Order für dieselbe Kerze
        vorher = {str(x["position"].get("dealId")) for x in eigene + fremde}
        satz = self.cfg["kosten"]["nacht_pro_jahr"]["krypto"]["long" if d > 0 else "short"]
        plan = {"grenze": str(t_g), "richtung": d, "size": size, "dist": round(dist, 6), "stop": stop, "ziel": ziel,
                "bid": q.bid, "spaet_min": spaet, "bis_utc": str(t_g + pd.Timedelta(hours=int(p["halte_stunden"]))),
                "satz_nacht": float(satz), "lot": q.lot or 1.0, "eur_rate": q.eur_rate}
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

    lauf = Lauf(client, state, now, send_orders, cfg=lade_cfg(pruefen=False))
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
    return {"naechste_stunde_endet_utc": str(naechste_grenze(lauf.now)),
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
                         f"Ausstieg spätestens {str(tr['bis_utc'])[:16]} UTC")
        elif m.get("ungeklaert"):
            teile.append(f"{name}: Order gesendet, Bestätigung fehlt, der nächste Lauf sieht nach")
    if teile:
        return ". ".join(teile)
    zuletzt = [m.get("letzte_pruefung") for m in (st.get("maerkte") or {}).values() if m.get("letzte_pruefung")]
    if not zuletzt:
        return "kein Trade offen, wartet auf den Schluss der nächsten Stundenkerze"
    p = max(zuletzt, key=lambda x: x["grenze"])
    return f"kein Trade offen. Letzte Kerze (bis {p['grenze'][:16]} UTC): {p['ergebnis']}"


def cockpit(st: dict, alle_trades: list[dict], blick: dict) -> dict:
    offen = [{k: m["trade"].get(k) for k in ("id", "markt", "epic", "richtung", "entry", "stop", "ziel", "size", "dist",
                                              "opened_utc", "bis_utc")}
             for m in (st.get("maerkte") or {}).values() if m.get("trade")]
    return {"bot": BOT_ID, "name": NAME, "konto": KONTO_NAME, "stand": st.get("stand"), "start": st.get("start"),
            "pausiert": st.get("pausiert"), "status": status(st), "regel": REGEL, "backtest": TEST,
            "vorab": "suche/VORAB_krypto_bollinger_bot.yaml", "vorab_ok": vorab_ok(),
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
        print("Keine Capital.com-Zugangsdaten, Bollinger Krypto übersprungen")
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
