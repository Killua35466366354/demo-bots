"""Tag nach einem VIX-Sprung auf fünf Indizes, live auf einem Capital.com-DEMOKONTO. Nie echtes Geld.

    python -m suche.vix_sprung_bot              # ein Lauf: offene Trades führen, nach 18 Uhr New York Einstiege?
    python -m suche.vix_sprung_bot --dry-run    # nur rechnen und zeigen, keine Order

Kirons Wunsch vom 20.11.2026 ("Schatten soll direkt Live-Demo sein", 11:44 UTC), seine Wahl auf der Karte "die paar
stärksten zu erst" mit dem Zusatz "aber alle anderen die bischen mehr machen dann und vielleicht die alle 1$ zusammen
fügen in einen bot" (11:53 UTC) und "baue danach aber weiter aus" (12:26 UTC). Der Bot handelt zwei versiegelte Fassungen
derselben Regel unverändert, zusammen in einem Bot:
- vix_sprung_us aus suche/VORAB_grosse_runde.yaml (US500, US100): Test NICHT bestanden, Kandidat
  (suche/ergebnis_grosse_runde.md), 136 Trades, Gewinnfaktor 1,93, z 2,17 statt 3, ohne Holm. Vor 2024 1,13.
- vix_sprung_welt aus suche/VORAB_grosse_runde2.yaml (DAX, FTSE 100, Nikkei 225): Test durchgefallen
  (suche/ergebnis_grosse_runde2.md), 204 Trades, Gewinnfaktor 1,41, erste Hälfte 0,96, Zufall nur zu 93,1 % geschlagen.
Beide zählen an denselben 68 Tagen (2024 bis Oktober 2026), also etwa zwei Tage im Monat mit je fünf Trades.
Regeln des Bots und Urteil stehen in suche/VORAB_vix_sprung_bot.yaml, Prüfsumme im Protokoll vor dem ersten Trade.
Ohne passende Prüfsumme öffnet der Bot nichts.

Regel (für alle fünf Märkte dieselbe):
- Schließt der VIX (die "Angstzahl" der US-Börse) mindestens 10 % über seinem Schluss vom Vortag, kauft der Bot am
  folgenden Handelstag, einen Handelstag lang. Der jüngste VIX-Wert darf höchstens 3 Kalendertage alt sein.
- Einstieg mit dem ersten Kurs ab 18:00 New York am Vorabend des Handelstags, Notstop 3 Tages-ATR beim Broker, kein
  Ziel, Ausstieg zum Markt vor 15:55 New York. Nur Käufe.
- Höchstens ein Trade je Markt, also höchstens fünf zugleich.

Live-Ausführung:
- Ob der VIX gesprungen ist, rechnet die Funktion des Tests (suche/grosse_runde.richtung_reihe) auf den VIX-Werten von
  Cboe. Das ist die Quelle der FRED-Reihe VIXCLS des Tests, FRED selbst kommt einen Tag später. Stop und Ausstiegszeit
  rechnet suche/grosse_runde._tagestrades auf Stundenkerzen von Capital.com (60 Tage), jede als zwölf gleiche
  5-Minuten-Zeilen (wie suche/modell_indizes_bot.py), dahinter eine Zeile zur Minute des Einstiegs mit dem Bid.
- Fehlt beim letzten Lauf in der Frist noch der VIX-Wert vom Vortag, lässt der Bot den Handelstag aus. Mit dem Wert
  von vorgestern wäre es ein anderes Signal als im Test.
- Der Lauf kommt alle 15 Minuten. Eingestiegen wird höchstens 20 Minuten nach dem ersten Kurs des Handelstags beim
  Broker. Ausgestiegen wird im ersten Lauf ab 15:40 New York, damit DAX und FTSE (Schluss bei Capital.com um 16:00
  New York) noch offen sind.
- Nur Account 5, den er mit dem Dow-Rücksetzer (US30), Pine-Gold K5 und Gold-Hand (Gold) teilt (andere Märkte). Die
  Kontonummer findet er nach dem Namen über journal/konten.json (suche/mitnutzer.konto_nach_name). Er kennt seine
  Positionen an der Deal-ID. Liegt eine fremde Position auf demselben Markt, öffnet er dort nichts Neues.
- Ab -25 R seit Start nichts Neues mehr (Sicherung), zurück nur mit Kirons Entscheidung.
- Er schreibt nur journal/vix-sprung/ und journal/vix-sprung.json.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import io
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
from suche import grosse_runde as gr
from suche import modell_indizes_bot as mb
from suche import rueckblick as rb
from suche import schluss as belegt_pruefung
from suche.rueckblick_daten import MAERKTE as _EPICS

ROOT = Path(gr.ROOT)
BOT_ID = "vix-sprung"
NAME = "Tag nach einem VIX-Sprung (US500, US100, DAX, FTSE, Nikkei)"
KONTO_NAME = "Account 5"              # geteilt mit r5-ruecksetzer-us30 (US30), pine-k5 und gold-hand (Gold)
HAUPT_ENDUNG = sb.HAUPT_ENDUNG        # Hauptkonto des Gold-Bots, hier nie handeln
FASSUNGEN = {"vix_sprung_us": 1, "vix_sprung_welt": 2}     # Fassung -> Durchgang der großen Runde
REIHE = "VIXCLS"
RISIKO_EUR = 5.0
MAX_RISIKO_FAKTOR = 2.0               # Runden auf die kleinste Größe darf das Risiko höchstens verdoppeln
MARGE_ANTEIL = 0.2                    # eine Order darf höchstens diesen Teil des freien Gelds als Margin brauchen
PAUSE_R = -25.0
URTEIL_NACH, URTEIL_PF = 40, 1.2      # suche/VORAB_wechsel.yaml
ZWISCHEN_NACH, ZWISCHEN_PF = 15, 0.6
TAGE_KERZEN = 60                      # so viele Kalendertage Stundenkerzen je Rechnung (ATR 14 der Tageskerzen)
MIN_TAGE = 20                         # mit weniger gültigen Handelstagen vor dem Einstieg rechnet der Bot nichts
FRIST = pd.Timedelta(minutes=20)      # so lange nach dem ersten Kurs des Handelstags darf der Bot noch einsteigen
TAKT = pd.Timedelta(minutes=15)       # Abstand der Läufe
AUS_VORLAUF = pd.Timedelta(minutes=15)     # Ausstieg im ersten Lauf ab 15:55 New York minus diese Zeit
SCHLUSS_WARTEN = pd.Timedelta(hours=1)     # so lange sucht der Bot den Schlusskurs beim Broker, dann schätzt er
VORAB = ROOT / "suche" / "VORAB_vix_sprung_bot.yaml"
KEY = "VORAB_vix_sprung_bot sha256 "
JDIR = ROOT / "journal" / "vix-sprung"
COCKPIT = ROOT / "journal" / "vix-sprung.json"
FREMDE_DATEIEN = sb.GOLD_BOT_DATEIEN + ("konten.json", "r6-bots.json", "gold-grossbox.json", "welt-ausbruch4h.json",
                                        "krypto-bollinger.json", "modell-indizes.json", "pine-k5.json",
                                        "gold-hand.json")
SEITE = {1: "Kauf", -1: "Verkauf"}
NAMEN = {"SPXUSD": "US500", "NSXUSD": "US100", "GRXEUR": "DAX", "UKXGBP": "FTSE 100", "JPXJPY": "Nikkei 225"}
# Werktage ohne VIX-Wert (Börse New York geschlossen), bis Ende 2027. Fehlt hier ein Feiertag, wartet der Bot am Tag
# danach auf einen Wert, der nie kommt, und lässt den Tag aus. Er kauft dadurch nie mit einem falschen Wert.
FEIERTAGE = ["2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
             "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24"]
REGEL = ("Tag nach einem VIX-Sprung (Fassungen vix_sprung_us und vix_sprung_welt): Schließt der VIX mindestens 10 % über "
         "dem Vortag, kauft der Bot US500, US100, DAX, FTSE 100 und Nikkei 225 mit dem ersten Kurs ab 18:00 New York, "
         "Notstop 3 Tages-ATR, kein Ziel, Ausstieg vor 15:55 New York. Höchstens ein Trade je Markt, 5 € Risiko.")
TEST = ("Test NICHT bestanden. US500 und US100 (vix_sprung_us, suche/ergebnis_grosse_runde.md): Kandidat, 136 Trades, "
        "Gewinnfaktor 1,93, 2026 2,45, z 2,17 statt 3, ohne Holm, vor 2024 1,13. DAX, FTSE und Nikkei (vix_sprung_welt, "
        "suche/ergebnis_grosse_runde2.md): durchgefallen, 204 Trades, Gewinnfaktor 1,41, erste Hälfte 0,96. Zusammen "
        "340 Trades an 68 Tagen (2024 bis Oktober 2026), Gewinnfaktor 1,60. Auf 1.000 € mit 10 € je Trade im Rückblick "
        "etwa 4,90 € im Monat. Kirons Wunsch vom 20.11.2026: weitere Fassungen mit etwas mehr Gewinn live testen.")


def _roh(nr: int) -> dict:
    import yaml
    return yaml.safe_load(gr.vorab(nr).read_text(encoding="utf-8"))["grosse_runde"]


def _maerkte() -> dict[str, tuple[str, str, int]]:
    """HistData-Name -> (Epic bei Capital.com, Fassung, Durchgang), aus den versiegelten Regeldateien."""
    out = {}
    for fassung, nr in FASSUNGEN.items():
        for sym in _roh(nr)["varianten"][fassung]["maerkte"]:
            out[sym] = (_EPICS[sym][0], fassung, nr)
    return out


_MAERKTE = _maerkte()
MAERKTE = {sym: v[0] for sym, v in _MAERKTE.items()}
FASSUNG = {sym: v[1] for sym, v in _MAERKTE.items()}
DURCHGANG = {sym: v[2] for sym, v in _MAERKTE.items()}


def konto_id(konten_daten: dict | None = None) -> str:
    """Die volle Kontonummer von Account 5 aus journal/konten.json, gesucht nach dem Namen (suche/mitnutzer.py
    konto_nach_name). Leer, wenn es das Konto dort nicht genau einmal gibt. Die Nummer wird nie abgetippt und nie
    ausgegeben."""
    from suche.mitnutzer import konto_nach_name
    return konto_nach_name(KONTO_NAME, konten_daten)


KONTO = konto_id()


def lade_cfg(pruefen: bool = False) -> dict[int, dict] | None:
    """Beide versiegelten Durchgänge der großen Runde. None, wenn eine Regeldatei nicht zu ihrem Siegel passt."""
    try:
        return {nr: gr.lade_vorab(nr, pruefen=pruefen) for nr in sorted(set(FASSUNGEN.values()))}
    except SystemExit:
        return None


def regel(sym: str, cfgs: dict[int, dict]) -> dict:
    return cfgs[DURCHGANG[sym]]["regeln"][FASSUNG[sym]]


def _sha(text: str) -> str:
    from suche.runde1 import sha256_text
    return sha256_text(text)


def vorab_ok() -> bool:
    """Ist die Regeldatei des Bots versiegelt, und passen beide Durchgänge der großen Runde zu ihren Siegeln? Nur dann
    öffnet der Bot etwas."""
    from suche.runde1 import journal_lines, last_value
    if not VORAB.exists() or lade_cfg(pruefen=True) is None:
        return False
    return last_value(journal_lines(), KEY) == _sha(VORAB.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------------------------------------
# Zeit (wie das Vorhersage-Modell: Handelstag endet 17:00 New York, Einstieg ab 18:00 am Vorabend)

_ny = mb._ny
handelstag = mb.handelstag
tag_von = mb.tag_von
einstieg_ab = mb.einstieg_ab
einstieg_bis = mb.einstieg_bis
ausstieg = mb.ausstieg


# --------------------------------------------------------------------------------------------------------------------
# VIX (Netz nur in vix_holen) und Kerzen (Netz in mb.stundenkerzen)

def vix_holen(get=None) -> pd.Series:
    """Tagesschlüsse des VIX von Cboe, mit Datum, ohne Lücken."""
    if get is None:
        import requests
        get = requests.get
    r = get(mb.CBOE.format(name="VIX"), timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    werte = pd.to_numeric(df["CLOSE"], errors="coerce").to_numpy(float)
    return pd.Series(werte, index=pd.to_datetime(df["DATE"], format="%m/%d/%Y")).dropna().sort_index()


def erwartet(tag: pd.Timestamp) -> pd.Timestamp:
    """Der jüngste VIX-Wert, den der Test für diesen Handelstag nähme: der letzte Werktag davor ohne Feiertag."""
    frei = {pd.Timestamp(x) for x in FEIERTAGE}
    d = pd.Timestamp(tag) - pd.Timedelta(days=1)
    while d.weekday() >= 5 or d in frei:
        d -= pd.Timedelta(days=1)
    return d


def vix_stand(vix: pd.Series | None, tag: pd.Timestamp) -> dict:
    """Datum des VIX-Werts, den der Bot für diesen Handelstag nimmt, und ob es das erwartete ist."""
    vor = vix[vix.index < pd.Timestamp(tag)] if vix is not None else None
    datum = None if vor is None or not len(vor) else vor.index[-1]
    soll = erwartet(tag)
    return {"datum": None if datum is None else str(datum.date()), "erwartet": str(soll.date()),
            "frisch": datum is not None and datum >= soll}


def sprung(tag: pd.Timestamp, p: dict, fred: Path | None = None) -> dict:
    """Die Rechnung des Tests für diesen einen Handelstag: Richtung (1 Kauf, 0 nichts), dazu die zwei VIX-Werte."""
    t = np.array([np.datetime64(pd.Timestamp(tag).date())])
    with mb.fred_ordner(fred):
        d = int(gr.richtung_reihe(t, p)[0])
        a, da = gr.vor(p["reihe"], t, 0, p.get("lag", 0))
        b, db = gr.vor(p["reihe"], t, int(p["tage"]), p.get("lag", 0))
    a, b = float(a[0]), float(b[0])
    aend = a / b - 1.0 if np.isfinite(a) and np.isfinite(b) and b else None
    return {"richtung": d, "vix": _zahl(a), "vix_vorher": _zahl(b), "vix_aenderung": _zahl(aend),
            "vix_datum": str(da[0])[:10], "vix_vorher_datum": str(db[0])[:10]}


def _zahl(x) -> float | None:
    return round(float(x), 6) if x is not None and np.isfinite(x) else None


def _prozent(x: float | None) -> str:
    return "?" if x is None else f"{x:+.1%}"


def signal(sym: str, stunden: pd.DataFrame, t_e: pd.Timestamp, bid: float, cfgs: dict[int, dict],
           fred: Path | None = None) -> dict:
    """Was der Test zur Minute t_e (Einstieg nach 18:00 New York) auf diesem Markt sieht. `ok` heißt: Der Test nähme
    diesen Einstieg (ohne die Frage, ob schon ein Trade offen ist), dazu Stop-Abstand und Ausstiegszeit. `warten` heißt:
    Es fehlen Kerzen. fred: Ordner mit VIXCLS.csv im FRED-Format (None: die Dateien des Tests). Die Entscheidung treffen
    allein gr.richtung_reihe und gr._tagestrades."""
    cfg, p = cfgs[DURCHGANG[sym]], regel(sym, cfgs)
    t_e = pd.Timestamp(t_e)
    tag = tag_von(t_e)
    out = {"markt": sym, "fassung": FASSUNG[sym], "tag": str(tag.date()), "einstieg_utc": str(t_e), "richtung": 0,
           "vix_aenderung": None, "dist": None, "bis_utc": None, "ok": False, "warten": False, "ergebnis": ""}
    if tag.weekday() >= 5:
        return {**out, "ergebnis": "kein Handelstag (Wochenende)"}
    ab = einstieg_ab(tag, cfg)
    if not ab <= t_e <= einstieg_bis(tag, cfg):
        return {**out, "ergebnis": "außerhalb des Einstiegs (18:00 bis 3:00 New York)"}
    vorher = stunden[(stunden.index < ab) & (stunden.index >= t_e - pd.Timedelta(days=TAGE_KERZEN))]
    m, e = mb.markt_live(sym, vorher, t_e, bid, cfg)
    g = int(m.gpos[m.tix[e]])
    fertige = int(np.searchsorted(m.gi, m.tix[e]))               # gültige Handelstage vor dem Tag des Einstiegs
    out["tage"] = fertige
    if g < 0:
        return {**out, "ergebnis": "der Handelstag zählt im Test nicht"}
    if fertige < MIN_TAGE:
        return {**out, "warten": True, "ergebnis": f"zu wenig Kerzen vom Broker ({fertige} fertige Handelstage, nötig "
                                                   f"{MIN_TAGE})"}
    with mb.fred_ordner(fred):
        rich = gr.richtung_reihe(m.gtag, p)
    v = sprung(tag, p, fred)
    out.update({k: v[k] for k in ("vix", "vix_vorher", "vix_aenderung", "vix_datum", "vix_vorher_datum")},
               richtung=int(rich[g]), atr=_zahl(m.atr_vor[g]))
    if rich[g] == 0:
        return {**out, "ergebnis": f"kein Trade: VIX {_prozent(v['vix_aenderung'])}, nötig mindestens "
                                   f"{float(p['schwelle']):+.0%}"}
    treffer = [s for s in gr._tagestrades(m, cfg, rich, p["stop_atr"]) if int(s["i0"]) == e]
    if not treffer or not treffer[0]["sd"] > 0:
        return {**out, "ergebnis": "VIX-Sprung, aber kein Einstieg nach der Regel (keine ATR)"}
    s = treffer[0]
    return {**out, "ok": True, "richtung": int(s["d"]), "dist": round(float(s["sd"]), 6),
            "bis_utc": str(pd.Timestamp(s["t_max"])), "ergebnis": f"Kauf: VIX {_prozent(v['vix_aenderung'])}"}


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
    je, je_fassung = {}, {}
    for t in trades:
        for ziel, name in ((je, t.get("markt")), (je_fassung, t.get("fassung"))):
            x = ziel.setdefault(name or "?", {"trades": 0, "summe_r": 0.0})
            x["trades"] += 1
            x["summe_r"] = round(x["summe_r"] + float(t["r"]), 3)
    return {"trades": n, "tage": len({t.get("tag") for t in trades}), "je_fassung": je_fassung,
            "pf_r": None if g is None else round(float(min(g, 999.0)), 3), "summe_r": round(float(sum(r)), 2),
            "trefferquote": round(sum(x > 0 for x in r) / n, 3) if n else None,
            "summe_eur": round(float(sum(float(t.get("pnl_eur") or 0) for t in trades)), 2), "je_markt": je,
            "urteil": text}


_num = sb._num
_zeit = mb._zeit
_rund = mb._rund


# --------------------------------------------------------------------------------------------------------------------
# Ein Lauf

class Lauf:
    """Ein Lauf auf dem Demokonto für alle fünf Märkte. Alle Order- und Schließ-Aufrufe gehen über diese Klasse, damit
    ein Trockenlauf (send_orders=False) nichts beim Broker ändert."""

    def __init__(self, client, state: dict, now: datetime, send_orders: bool = True, cfgs: dict | None = None,
                 vix_get=None, ordner: Path | None = None, konto: str | None = None):
        self.client = client
        self.st = copy.deepcopy(state or {})
        self.now = sb._jetzt(now)
        self.stamp = self.now.isoformat(timespec="seconds")
        self.send = send_orders
        self.cfgs = cfgs
        self.vix_get = vix_get
        self.ordner = ordner
        self.konto = KONTO if konto is None else konto
        self._vix: dict | None = None
        self.log: list[dict] = []
        self.fertige: list[dict] = []
        self.q = None
        self.sym = ""
        self.epic = ""
        self.eigene_zu: set[str] = set()
        self.blick: dict = {}
        self.gebunden = 0.0              # Margin der Orders aus diesem Lauf (an einem Sprung-Tag bis zu fünf)
        for k, v in (("format", 1), ("start", self.stamp), ("summe_r", 0.0), ("trades", 0), ("maerkte", {})):
            self.st.setdefault(k, v)
        for sym in MAERKTE:
            self.st["maerkte"].setdefault(sym, {"trade": None})

    @property
    def mst(self) -> dict:
        return self.st["maerkte"][self.sym]

    @property
    def cfg(self) -> dict | None:
        return None if self.cfgs is None else self.cfgs[DURCHGANG[self.sym]]

    def ev(self, event: str, **kw) -> None:
        self.log.append({"time": self.stamp, "event": event, "markt": self.sym or None, **kw})

    def kurs_raus(self, d: int) -> float:
        """Zu diesem Kurs schließt eine Position zum Markt: Kauf am Bid, Verkauf am Ask."""
        return self.q.bid if d > 0 else self.q.offer

    def nur_mein_konto(self) -> None:
        if not self.konto or str(self.client.account_id) != self.konto:
            raise RuntimeError(f"aktives Konto ist nicht {KONTO_NAME}, nichts gesendet")

    def warte(self, text: str) -> None:
        self.blick.setdefault(self.sym, {})["wartet"] = text

    def kerzen(self, von: pd.Timestamp) -> pd.DataFrame | None:
        try:
            return mb.stundenkerzen(self.client, self.epic, von, self.now)
        except Exception as err:            # noqa: BLE001 - der nächste Lauf versucht es wieder
            print(f"Stundenkerzen {self.epic} nicht lesbar: {err}")
            self.warte("Stundenkerzen nicht lesbar")
            return None

    def erste_kerze(self, ab: pd.Timestamp) -> pd.Timestamp | None:
        """Beginn der ersten 5-Minuten-Kerze beim Broker ab `ab` (ab 18:00 New York). So spät stiege der Test ein.
        Ohne Kerze (der Markt öffnet gerade) die Zeit des Laufs."""
        from suche.demo_bots import frame
        try:
            got = self.client._get(f"/prices/{self.epic}", resolution="MINUTE_5", max=200,
                                   **{"from": ab.strftime(mb.FMT), "to": self.now.strftime(mb.FMT)}).get("prices", [])
        except Exception as err:            # noqa: BLE001
            print(f"5-Minuten-Kerzen {self.epic} nicht lesbar: {err}")
            self.warte("5-Minuten-Kerzen nicht lesbar")
            return None
        bars, _ = frame(got)
        bars = bars[bars.index >= ab] if len(bars) else bars
        return pd.Timestamp(bars.index.min()) if len(bars) else self.now

    def vix(self) -> dict:
        """VIX einmal je Lauf holen und für den Test als Datei ablegen."""
        if self._vix is None:
            try:
                reihe = vix_holen(self.vix_get)
                mb.fremd_schreiben({REIHE: reihe}, self.ordner)
                self._vix = {"reihe": reihe}
            except Exception as err:        # noqa: BLE001 - der nächste Lauf versucht es wieder
                print(f"VIX nicht lesbar: {err}")
                self._vix = {"fehler": str(err)[:200]}
        return self._vix

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
        """Schlusskurs, Quelle (SL, CLOSE_OUT, USER ...) und Zeit aus der Kontoaktivität zu dieser Position. Der Broker
        gibt je Abruf höchstens einen Tag her, darum die letzten 23 Std. 59 Min. (None, "", jetzt), wenn dort kein
        Schluss steht."""
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
        """Bucht den Trade. R nach Übernachtgebühr mit den Sätzen des Tests (nur wenn er über 17:00 New York lief),
        das Euro-Ergebnis ohne Gebühr."""
        d, dist = int(tr["richtung"]), float(tr["dist"])
        naechte = max(handelstag(wann) - handelstag(tr["opened_utc"]), 0)
        gebuehr_r = float(tr["satz_nacht"]) * naechte / 365.0 * float(tr["entry"]) / dist
        r_roh = d * (level - float(tr["entry"])) / dist
        pnl = float(tr["size"]) * float(tr.get("lot") or 1.0) * d * (level - float(tr["entry"]))
        rate = _num(tr.get("eur_rate")) or (self.q.eur_rate if self.q else None)
        rec = {**{k: tr.get(k) for k in ("id", "markt", "epic", "fassung", "richtung", "tag", "dealId", "size", "entry",
                                         "stop", "dist", "vix_aenderung", "opened_utc", "spaet_min", "nach_18_min")},
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
        """Ist der offene Trade beim Broker zu (Stop)? Und: Liegt eine Order ohne Bestätigung jetzt als Position da?"""
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
                self.ev("Order ohne Bestätigung liegt nicht beim Broker", tag=offen["tag"], gefunden=len(neu))
        tr = self.mst.get("trade")
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
        d = int(tr["richtung"])
        if geschaetzt:                                     # ohne Ziel bleibt nur der Stop
            quelle = "SL"
            level = tr.get("stop") or float(tr["entry"]) - d * float(tr["dist"])
            wann = pd.Timestamp(seit)
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
        self.mst["trade"] = {
            "id": f"{self.epic} {plan['tag']}", "markt": self.sym, "epic": self.epic, "fassung": FASSUNG[self.sym],
            "richtung": d, "tag": plan["tag"], "dealId": str(p.get("dealId")), "size": plan["size"],
            "entry": float(level), "stop": _num(p.get("stopLevel")) or plan["stop"], "dist": plan["dist"],
            "bid_ein": plan["bid"], "vix_aenderung": plan["vix_aenderung"], "opened_utc": opened_utc,
            "spaet_min": plan.get("spaet_min"), "nach_18_min": plan.get("nach_18_min"), "bis_utc": plan["bis_utc"],
            "satz_nacht": plan["satz_nacht"], "lot": plan["lot"], "eur_rate": plan["eur_rate"]}
        self.ev(SEITE[d] + " eröffnet", **{k: self.mst["trade"][k] for k in ("id", "dealId", "size", "entry", "stop",
                                                                            "dist", "vix_aenderung", "spaet_min")})

    # ---- Führung des offenen Trades ----

    def fuehren(self) -> None:
        """Ausstieg zum Markt zur Zeit des Tests (15:55 New York), im ersten Lauf ab 15 Minuten davor. Die Zeit steht im
        Trade selbst, so führt der Bot ihn auch ohne lesbare Regeldatei."""
        tr = self.mst.get("trade")
        if not tr or tr.get("weg_seit") or self.now < pd.Timestamp(tr["bis_utc"]) - AUS_VORLAUF:
            return
        if not self.q.tradeable:
            self.warte("Ausstieg fällig, Markt zu")
            return
        self.schliesse(tr, "zeit")

    # ---- Neuer Einstieg ----

    def pruefen(self, eigene: list[dict], fremde: list[dict], available_eur: float | None) -> None:
        """Einmal je Handelstag und Markt, im Einstieg des Tests (ab 18:00 New York am Vorabend): Ist der VIX gesprungen,
        und darf der Bot kaufen?"""
        if self.cfgs is None:
            self.warte("Regeldatei der großen Runde nicht lesbar (Siegel passt nicht)")
            return
        tag = tag_von(self.now)
        key = str(tag.date())
        if self.mst.get("letzter_tag") == key or tag.weekday() >= 5:
            return
        ab, bis = einstieg_ab(tag, self.cfg), einstieg_bis(tag, self.cfg)
        if not ab <= self.now <= bis:
            return

        def fertig(ergebnis: str, grund: str | None = None, **kw) -> None:
            """Der Handelstag ist für diesen Markt erledigt. grund: Kurzname, wenn der Bot ihn ohne Rechnung auslässt
            (zählt im Zustand mit, damit ein Bot, der still nie handelt, im Cockpit auffällt)."""
            self.mst["letzter_tag"] = key
            self.mst["letzte_pruefung"] = {"tag": key, "ergebnis": ergebnis, **kw}
            if grund:
                zaehler = self.mst.setdefault("ausgelassen", {})
                zaehler[grund] = int(zaehler.get(grund, 0)) + 1

        if self.mst.get("trade") is not None:
            return fertig("ein Trade ist noch offen, höchstens einer je Markt")
        p = regel(self.sym, self.cfgs)
        v = self.vix()
        stand = vix_stand(v.get("reihe"), tag)
        if "fehler" not in v and stand["frisch"]:
            vorab_sprung = sprung(tag, p, self.ordner)
            if vorab_sprung["richtung"] == 0:          # kein Sprung: ohne Kerzen und ohne Rechnung erledigt
                return fertig(f"kein Trade: VIX {_prozent(vorab_sprung['vix_aenderung'])}, nötig mindestens "
                              f"{float(p['schwelle']):+.0%}", vix_stand=stand,
                              **{k: vorab_sprung[k] for k in ("vix", "vix_vorher", "vix_aenderung")})
        if not self.q.tradeable:
            self.warte("Markt zu")
            return
        erste = self.erste_kerze(ab)
        if erste is None:
            return
        spaet = self.now - max(erste, ab)
        if spaet > FRIST:
            if not self.send:
                return
            return fertig(f"verfallen: der Markt ist seit {str(erste)[:16]} UTC offen, der Test stiege mit dem ersten "
                          f"Kurs ein (Frist {int(FRIST.total_seconds() // 60)} Minuten)", grund="verfallen")
        letzte_chance = spaet + TAKT > FRIST
        if "fehler" in v:
            if letzte_chance and self.send:
                return fertig("VIX nicht lesbar, kein Einstieg: " + v["fehler"], grund="vix_fehlt")
            self.warte("VIX nicht lesbar")
            return
        if not stand["frisch"]:          # mit dem Wert von vorgestern wäre es ein anderes Signal als im Test: auslassen
            text = f"VIX vom {stand['erwartet']} noch nicht veröffentlicht"
            if letzte_chance and self.send:
                return fertig(text + ", kein Einstieg", grund="vix_alt", vix_stand=stand)
            self.warte(text)
            return
        stunden = self.kerzen(self.now - pd.Timedelta(days=TAGE_KERZEN))
        if stunden is None:
            return
        sig = signal(self.sym, stunden, self.now, self.q.bid, self.cfgs, fred=self.ordner)
        sig["vix_stand"] = stand
        self.blick.setdefault(self.sym, {})["signal"] = sig
        if sig["warten"]:
            if letzte_chance and self.send:
                return fertig(sig["ergebnis"], grund="kerzen")
            self.warte(sig["ergebnis"])
            return
        kurz_info = {k: sig.get(k) for k in ("richtung", "vix", "vix_vorher", "vix_aenderung", "dist", "atr")}
        if not sig["ok"]:
            return fertig(sig["ergebnis"], **kurz_info)
        kurz_info["nach_18_min"] = round((self.now - ab).total_seconds() / 60, 1)   # Test: meist 0 bis 5 Minuten
        self.einstieg(sig, tag, eigene, fremde, available_eur, fertig, kurz_info, round(spaet.total_seconds() / 60, 1))

    def einstieg(self, sig: dict, tag: pd.Timestamp, eigene: list[dict], fremde: list[dict],
                 available_eur: float | None, fertig, kurz_info: dict, spaet: float) -> None:
        q, d = self.q, int(sig["richtung"])
        dist = float(sig["dist"])
        stop = _rund(q.bid - d * dist, q)                  # am Bid gemessen wie im Test
        gruende = []
        if d != 1:
            gruende.append("die Regel kauft nur")
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
            frei = None if available_eur is None else available_eur - self.gebunden
            if frei is not None and marge > MARGE_ANTEIL * frei:
                gruende.append(f"Margin {marge:.0f} € wäre mehr als {MARGE_ANTEIL:.0%} des freien Gelds ({frei:.0f} €)")
        abstand = abs(q.offer - stop) if d > 0 else abs(stop - q.bid)
        if q.min_dist and abstand < q.min_dist:
            gruende.append("Stop näher als der Mindestabstand des Brokers")
        info = {"seite": SEITE.get(d, "?"), "tag": str(tag.date()), "dist": round(dist, 4), "stop": stop,
                "spaet_min": spaet, "nach_18_min": kurz_info.get("nach_18_min"), "bid": q.bid,
                "vix_aenderung": sig["vix_aenderung"], "margin_eur": None if marge is None else round(marge, 2)}
        if gruende:                       # zählt im Zustand mit (selten: zwei Tage im Monat, fünf Märkte)
            self.ev("Einstieg ausgelassen", **info, gruende=gruende)
            return fertig("VIX-Sprung, aber kein Einstieg: " + "; ".join(gruende),
                          grund="groesse" if size is None else "sperre", **kurz_info)
        if not self.send:
            self.ev("würde kaufen", **info, size=size)
            return
        fertig("Kauf gesendet", **kurz_info)               # vor der Order: nie eine zweite Order für denselben Tag
        self.gebunden += marge or 0.0                       # das freie Geld sinkt schon mit der gesendeten Order
        vorher = {str(x["position"].get("dealId")) for x in eigene + fremde}
        satz = self.cfg["kosten"]["nacht_pro_jahr"]["index"]["long"]
        plan = {"tag": str(tag.date()), "richtung": d, "size": size, "dist": round(dist, 6), "stop": stop, "bid": q.bid,
                "spaet_min": spaet, "nach_18_min": kurz_info.get("nach_18_min"), "bis_utc": sig["bis_utc"],
                "vix_aenderung": sig["vix_aenderung"], "satz_nacht": float(satz), "lot": q.lot or 1.0,
                "eur_rate": q.eur_rate}
        body = {"epic": self.epic, "direction": "BUY", "size": size, "guaranteedStop": False, "stopLevel": stop}
        conf = None
        try:
            self.nur_mein_konto()
            ref = self.client._request("POST", "/positions", json=body).json()["dealReference"]
            conf = self.client.confirm(ref) or {}
        except Exception as err:            # noqa: BLE001 - kein zweiter Versuch, damit nichts doppelt entsteht
            self.ev("Order ohne Bestätigung", **info, fehler=str(err)[:200])
            fertig("Kauf gesendet, Bestätigung fehlt", **kurz_info)
        if conf is not None and str(conf.get("dealStatus") or "").upper() == "REJECTED":
            self.ev("Order abgelehnt", **info, grund=conf.get("reason"))
            return fertig(f"VIX-Sprung, aber die Order wurde abgelehnt ({conf.get('reason')})", **kurz_info)
        try:
            jetzt = [x["position"] for x in self.client.positions() if (x.get("market") or {}).get("epic") == self.epic]
        except Exception as err:            # noqa: BLE001
            print(f"Positionen nach der Order nicht lesbar: {err}")
            jetzt = None
        neu = [x for x in jetzt or [] if str(x.get("dealId")) not in vorher and x.get("direction", "BUY") == "BUY"]
        deal = ((conf or {}).get("affectedDeals") or [{}])[0].get("dealId") or (conf or {}).get("dealId")
        if len(neu) == 1 or (conf and deal):                # sonst bestätigt, aber noch nicht in der Liste der Positionen
            fertig("Kauf eröffnet", **kurz_info)
            return self.uebernehmen(neu[0] if len(neu) == 1 else {"dealId": deal, "level": conf.get("level")}, plan,
                                    self.stamp)
        # keine Bestätigung und keine Position gefunden: Der nächste Lauf sucht sie an Richtung und Größe
        self.mst["ungeklaert"] = {**plan, "seit": self.stamp, "vorher": sorted(vorher)}


def run(client, state: dict, now: datetime, send_orders: bool = True,
        vix_get=None) -> tuple[dict, list[dict], list[dict], dict]:
    """Ein Lauf. Rückgabe: neuer Stand, Ereignisse, fertige Trades, Blick (für das Cockpit)."""
    from suche.demo_bots import eur_rate, quote_from_market

    with tempfile.TemporaryDirectory() as tmp:
        lauf = Lauf(client, state, now, send_orders, cfgs=lade_cfg(pruefen=False), vix_get=vix_get, ordner=Path(tmp))
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
    tag = tag_von(lauf.now)
    cfg = None if lauf.cfgs is None else lauf.cfgs[min(lauf.cfgs)]
    naechster = None
    if cfg:                                                # der nächste Abend vor einem Handelstag Montag bis Freitag
        while naechster is None or naechster < lauf.now or tag.weekday() >= 5:
            if naechster is not None:
                tag += pd.Timedelta(days=1)
            naechster = einstieg_ab(tag, cfg)
    return {"naechster_einstieg_utc": None if naechster is None else str(naechster),
            "maerkte": {sym: {"epic": MAERKTE[sym], "fassung": FASSUNG[sym],
                              "letzte_pruefung": lauf.st["maerkte"][sym].get("letzte_pruefung"),
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
            teile.append(f"{name}: Kauf offen ab {tr['entry']}, Stop {tr['stop']}, Ausstieg vor "
                         f"{str(tr['bis_utc'])[:16]} UTC")
        elif m.get("ungeklaert"):
            teile.append(f"{name}: Order gesendet, Bestätigung fehlt, der nächste Lauf sieht nach")
    if teile:
        return ". ".join(teile)
    zuletzt = [m.get("letzte_pruefung") for m in (st.get("maerkte") or {}).values() if m.get("letzte_pruefung")]
    if not zuletzt:
        return "kein Trade offen, wartet auf 18:00 New York"
    p = max(zuletzt, key=lambda x: x["tag"])
    return f"kein Trade offen. Zuletzt (Handelstag {p['tag']}): {p['ergebnis']}"


def cockpit(st: dict, alle_trades: list[dict], blick: dict) -> dict:
    offen = [{k: m["trade"].get(k) for k in ("id", "markt", "epic", "fassung", "richtung", "entry", "stop", "size",
                                              "dist", "vix_aenderung", "opened_utc", "bis_utc")}
             for m in (st.get("maerkte") or {}).values() if m.get("trade")]
    return {"bot": BOT_ID, "name": NAME, "konto": KONTO_NAME, "stand": st.get("stand"), "start": st.get("start"),
            "pausiert": st.get("pausiert"), "status": status(st), "regel": REGEL, "backtest": TEST,
            "vorab": "suche/VORAB_vix_sprung_bot.yaml", "vorab_ok": vorab_ok(),
            "maerkte": {sym: NAMEN.get(sym, sym) for sym in MAERKTE}, "fassungen": dict(FASSUNG), "offen": offen,
            "ausgelassen": {sym: m.get("ausgelassen") or {} for sym, m in (st.get("maerkte") or {}).items()},
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
        print("Keine Capital.com-Zugangsdaten, VIX-Sprung übersprungen")
        return 0
    path = JDIR / "state.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    client = CapitalClient(*creds, environment="demo")
    mb.anmelden(client)
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
