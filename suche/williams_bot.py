"""Williams %R auf US500 und US100, live auf einem Capital.com-DEMOKONTO. Nie echtes Geld.

    python -m suche.williams_bot              # ein Lauf: offene Trades führen, um 16:00 New York ein- und aussteigen
    python -m suche.williams_bot --dry-run    # nur rechnen und zeigen, keine Order

Kirons Wunsch vom 20.11.2026 ("Schatten soll direkt Live-Demo sein", 11:44 UTC), seine Wahl auf der Karte "die paar
stärksten zu erst" mit dem Zusatz "aber alle anderen die bischen mehr machen dann" (11:53 UTC) und "baue danach aber
weiter aus" (12:26 UTC). Der Bot handelt die versiegelte Fassung williams_us aus suche/VORAB_youtube_runde.yaml
unverändert. Test NICHT bestanden (suche/ergebnis_youtube_runde.md): 77 Trades 2024 bis Oktober 2026, Gewinnfaktor
2,66, Holm erfüllt, aber unter 100 Trades und z 2,35 statt 3. Vor 2024 327 Trades, Gewinnfaktor 1,51. Bei 47 von 77
Trades kaufte auch der US500-Rücksetzer binnen 2 Tagen. Regeln des Bots und Urteil stehen in
suche/VORAB_williams_bot.yaml, Prüfsumme im Protokoll vor dem ersten Trade. Ohne passende Prüfsumme öffnet der Bot
nichts.

Regel (für beide Märkte dieselbe):
- Tageskerze der Kassa-Sitzung 9:30 bis 16:00 New York. Williams %R(2) = -100 mal (Hoch der 2 Tage minus Schluss)
  geteilt durch (Hoch der 2 Tage minus Tief der 2 Tage).
- Schließt %R unter -90, kauft der Bot um 16:00 New York. Notstop 3 Tages-ATR beim Broker, kein Ziel.
- Ausstieg zum Markt um 16:00 New York am ersten späteren Tag, an dem der Schluss über dem Hoch des Vortags liegt oder
  %R über -30 schließt, spätestens nach 10 vollen Sitzungen. Nur Käufe, höchstens ein Trade je Markt.

Live-Ausführung:
- Sitzung, %R und Ausstieg rechnet der Bot wie suche/youtube_runde.regel_williams (Funktion sitzungen, gleiche
  Zeilen), ATR und Tageskerzen rechnet suche/rueckblick.Markt. Die Kurse: die letzten 1.000 5-Minuten-Kerzen von
  Capital.com (gut drei Handelstage, darin heute und die Sitzung davor) und davor Stundenkerzen (60 Tage, jede als
  zwölf gleiche 5-Minuten-Zeilen wie suche/modell_indizes_bot.py). Dahinter eine Zeile zur Minute des Laufs mit dem Bid.
- Der Lauf kommt alle 15 Minuten. Gerechnet wird höchstens 20 Minuten nach 16:00 New York, einmal je Handelstag.
- Nur Account 7, den er mit Noise USD/JPY und dem 4-Std.-Ausbruch DAX, FTSE, Nikkei teilt (andere Märkte). Die
  Kontonummer findet er nach dem Namen über journal/konten.json (suche/mitnutzer.konto_nach_name). Er kennt seine
  Positionen an der Deal-ID. Liegt eine fremde Position auf demselben Markt, öffnet er dort nichts Neues.
- Ab -25 R seit Start nichts Neues mehr (Sicherung), zurück nur mit Kirons Entscheidung.
- Er schreibt nur journal/williams-us/ und journal/williams-us.json.
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
from suche import modell_indizes_bot as mb
from suche import rueckblick as rb
from suche import schluss as belegt_pruefung
from suche import youtube_runde as yr
from suche.rueckblick_daten import MAERKTE as _EPICS

ROOT = Path(yr.ROOT)
BOT_ID = "williams-us"
NAME = "Williams %R (US500, US100)"
KONTO_NAME = "Account 7"              # geteilt mit r6-noise-usdjpy (USD/JPY) und welt-ausbruch4h (DAX, FTSE, Nikkei)
HAUPT_ENDUNG = sb.HAUPT_ENDUNG        # Hauptkonto des Gold-Bots, hier nie handeln
FASSUNG = "williams_us"
RISIKO_EUR = 5.0
MAX_RISIKO_FAKTOR = 2.0               # Runden auf die kleinste Größe darf das Risiko höchstens verdoppeln
MARGE_ANTEIL = 0.2                    # eine Order darf höchstens diesen Teil des freien Gelds als Margin brauchen
PAUSE_R = -25.0
URTEIL_NACH, URTEIL_PF = 40, 1.2      # suche/VORAB_wechsel.yaml
ZWISCHEN_NACH, ZWISCHEN_PF = 15, 0.6
TAGE_KERZEN = 60                      # so viele Kalendertage Stundenkerzen je Rechnung (ATR 14, bis 10 Sitzungen offen)
FUENF_MAX = 1000                      # so viele 5-Minuten-Kerzen (die jüngsten) je Rechnung
MIN_TAGE = 20                         # mit weniger gültigen Handelstagen vor heute rechnet der Bot nichts
FRIST = pd.Timedelta(minutes=20)      # so lange nach 16:00 New York darf der Bot noch rechnen und handeln
TAKT = pd.Timedelta(minutes=15)       # Abstand der Läufe
SCHLUSS_WARTEN = pd.Timedelta(hours=1)     # so lange sucht der Bot den Schlusskurs beim Broker, dann schätzt er
STUNDE, FUENF, SPALTEN = mb.STUNDE, mb.FUENF, mb.SPALTEN
VORAB = ROOT / "suche" / "VORAB_williams_bot.yaml"
KEY = "VORAB_williams_bot sha256 "
JDIR = ROOT / "journal" / "williams-us"
COCKPIT = ROOT / "journal" / "williams-us.json"
FREMDE_DATEIEN = sb.GOLD_BOT_DATEIEN + ("konten.json", "r6-bots.json", "gold-grossbox.json", "welt-ausbruch4h.json",
                                        "krypto-bollinger.json", "modell-indizes.json", "vix-sprung.json")
SEITE = {1: "Kauf", -1: "Verkauf"}
NAMEN = {"SPXUSD": "US500", "NSXUSD": "US100"}
GRUND_TEXT = {"regel": "Schluss über dem Vortageshoch oder %R über -30", "zehn_tage": "spätestens nach 10 Sitzungen"}
REGEL = ("Williams %R auf US500 und US100 (Fassung williams_us): Schließt Williams %R(2) der Kassa-Sitzung unter -90, "
         "kauft der Bot um 16:00 New York. Ausstieg um 16:00 New York am ersten Tag, an dem der Schluss über dem Hoch "
         "des Vortags liegt oder %R über -30 schließt, spätestens nach 10 Sitzungen. Notstop 3 Tages-ATR, kein Ziel. "
         "Höchstens ein Trade je Markt, 5 € Risiko.")
TEST = ("Test NICHT bestanden (suche/ergebnis_youtube_runde.md): 2024 bis Oktober 2026 77 Trades (etwa 2 im Monat), "
        "Gewinnfaktor 2,66, mit 1,5-fachen Kosten 2,65, Hälften 2,39 und 3,28, 2026 1,75, 81 % Treffer, Holm erfüllt, "
        "aber unter 100 Trades und z 2,35 statt 3. US500 4,21 (41 Trades), US100 1,82 (36). Vor 2024 327 Trades, "
        "Gewinnfaktor 1,51. Auf 1.000 € mit 10 € je Trade im Rückblick etwa 3,90 € im Monat. Bei 47 von 77 Trades "
        "kaufte auch der US500-Rücksetzer. Kirons Wunsch vom 20.11.2026: weitere Fassungen mit etwas mehr Gewinn live "
        "testen.")


def _roh() -> dict:
    import yaml
    return yaml.safe_load(yr.VORAB.read_text(encoding="utf-8"))["youtube_runde"]


MAERKTE = {sym: _EPICS[sym][0] for sym in _roh()["varianten"][FASSUNG]["maerkte"]}   # Name im Test -> Epic


def konto_id(konten_daten: dict | None = None) -> str:
    """Die volle Kontonummer von Account 7 aus journal/konten.json, gesucht nach dem Namen (suche/mitnutzer.py
    konto_nach_name). Leer, wenn es das Konto dort nicht genau einmal gibt. Die Nummer wird nie abgetippt und nie
    ausgegeben."""
    from suche.mitnutzer import konto_nach_name
    return konto_nach_name(KONTO_NAME, konten_daten)


KONTO = konto_id()


def lade_cfg(pruefen: bool = False) -> dict | None:
    """Die versiegelte Regeldatei der YouTube-Runde. None, wenn sie nicht zu ihrem Siegel passt."""
    try:
        return yr.lade_vorab(pruefen=pruefen)
    except SystemExit:
        return None


def regel(cfg: dict) -> dict:
    return cfg["regeln"][cfg["varianten"][FASSUNG]["regel"]]


def _sha(text: str) -> str:
    from suche.runde1 import sha256_text
    return sha256_text(text)


def vorab_ok() -> bool:
    """Ist die Regeldatei des Bots versiegelt, und passt die Regeldatei der YouTube-Runde zu ihrem Siegel? Nur dann
    öffnet der Bot etwas."""
    from suche.runde1 import journal_lines, last_value
    if not VORAB.exists() or lade_cfg(pruefen=True) is None:
        return False
    return last_value(journal_lines(), KEY) == _sha(VORAB.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------------------------------------
# Zeit (Handelstag endet 17:00 New York, die Sitzung 9:30 bis 16:00 New York)

_ny = mb._ny
handelstag = mb.handelstag
tag_von = mb.tag_von


def schluss(tag: pd.Timestamp, p: dict) -> pd.Timestamp:
    """Ende der Kassa-Sitzung (16:00 New York) am Handelstag, als UTC. Hier steigt der Test ein und aus."""
    t = (pd.Timestamp(tag).normalize() + pd.Timedelta(minutes=int(p["sitzung_bis_min"]))).tz_localize(rb.NY)
    return t.tz_convert("UTC").tz_localize(None)


# --------------------------------------------------------------------------------------------------------------------
# Kerzen und die Rechnung des Tests

def fuenf_kerzen(client, epic: str) -> pd.DataFrame:
    """Die jüngsten FUENF_MAX 5-Minuten-Kerzen (Bid) vom Broker (nur lesen)."""
    from suche.demo_bots import frame
    bars, _ = frame(client.prices(epic, "MINUTE_5", FUENF_MAX))
    return bars


def zeilen(stunden: pd.DataFrame, fuenf: pd.DataFrame, t_s: pd.Timestamp, t_e: pd.Timestamp,
           bid: float) -> tuple[dict, int, pd.Timestamp | None]:
    """Die Kursdatei des Tests: Stundenkerzen als zwölf gleiche 5-Minuten-Zeilen bis zur ersten vollen Stunde der
    5-Minuten-Kerzen, ab dort die 5-Minuten-Kerzen bis vor t_s (16:00 New York), dann die Zeile zur Zeit t_e mit dem
    aktuellen Bid (die erste Kerze ab 16:00 New York im Test). Rückgabe: Felder der npz-Datei, die Zeile von t_e und der
    Beginn der echten 5-Minuten-Zeilen (None ohne 5-Minuten-Kerzen)."""
    f = fuenf[fuenf.index < t_s][SPALTEN] if len(fuenf) else fuenf
    ab = pd.Timestamp(f.index.min()).ceil("h") if len(f) else None
    if ab is not None:
        f = f[f.index >= ab]
        ab = ab if len(f) else None
    grenze = ab if ab is not None else t_s
    alt = stunden[stunden.index + STUNDE <= grenze][SPALTEN] if len(stunden) else stunden
    t_alt = (alt.index.values.astype("datetime64[ns]")[:, None] + np.arange(12) * FUENF).ravel()
    werte = {k: np.repeat(alt[s].to_numpy(float), 12) for k, s in zip("ohlc", SPALTEN)}
    t_f = f.index.values.astype("datetime64[ns]") if len(f) else np.array([], dtype="datetime64[ns]")
    t = np.r_[t_alt, t_f, np.datetime64(pd.Timestamp(t_e), "ns")].astype("datetime64[ns]")
    for k, s in zip("ohlc", SPALTEN):
        werte[k] = np.r_[werte[k], f[s].to_numpy(float) if len(f) else [], float(bid)]
    ny = _ny(t)
    tag = (ny + pd.Timedelta(hours=7)).normalize().values.astype("datetime64[D]")
    return ({"t": t, **werte, "sp": np.zeros(len(t)), "nymin": np.asarray(ny.hour * 60 + ny.minute, dtype=np.int32),
             "tag": tag}, len(t) - 1, ab)


def markt_live(sym: str, felder: dict, cfg: dict) -> rb.Markt:
    """Der Markt des Tests (Tageskerzen und ATR wie suche/rueckblick.Markt) aus diesen Zeilen."""
    with tempfile.TemporaryDirectory() as tmp:
        np.savez(Path(tmp) / f"{sym}.npz", **felder)
        return yr.Markt(sym, Path(tmp), cfg)


def sitzungen(m, p: dict) -> dict | None:
    """Die volle Kassa-Sitzung je Handelstag mit Hoch, Tief, Schluss, Williams %R, Ausstiegs-Bedingung und der ersten
    Kerze ab 16:00 New York. Zeile für Zeile wie suche/youtube_runde.regel_williams (dort ohne Rückgabe dieser Werte).
    None ohne Sitzung."""
    sitz = (m.nymin >= p["sitzung_von_min"]) & (m.nymin < p["sitzung_bis_min"])
    idx = np.flatnonzero(sitz)
    if len(idx) == 0:
        return None
    tix = m.tix[idx]
    a = np.flatnonzero(np.r_[True, tix[1:] != tix[:-1]])
    b = np.r_[a[1:], len(idx)] - 1
    tage = tix[a]
    anzahl = b - a + 1
    H, L = np.maximum.reduceat(m.h[idx], a), np.minimum.reduceat(m.l[idx], a)
    C = m.c[idx[b]]
    letzte_min = m.nymin[idx[b]]
    erste = m.t[idx[a]]
    voll = (anzahl >= p["min_kerzen_sitzung"]) & (letzte_min >= p["sitzung_bis_min"] - 5)
    keep = np.flatnonzero(voll)
    tage, H, L, C, erste = tage[keep], H[keep], L[keep], C[keep], erste[keep]
    n = p["tage"]
    hh = pd.Series(H).rolling(n).max().to_numpy()
    ll = pd.Series(L).rolling(n).min().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        wr = -100.0 * (hh - C) / (hh - ll)
    schluss_utc = (pd.DatetimeIndex(m.tage[tage]) + pd.Timedelta(minutes=p["sitzung_bis_min"])).tz_localize(rb.NY) \
        .tz_convert("UTC").tz_localize(None).values.astype("datetime64[ns]")
    i_s = yr._erste_ab(m, schluss_utc, p["toleranz_min"])
    i_s = np.where((i_s >= 0) & (m.tix[np.maximum(i_s, 0)] == tage), i_s, -1)
    raus = np.zeros(len(C), bool)
    raus[1:] = (C[1:] > H[:-1]) | (wr[1:] > p["raus_ueber"])
    return {"tage": tage, "datum": m.tage[tage], "H": H, "L": L, "C": C, "wr": wr, "raus": raus, "i_s": i_s,
            "erste": erste}


def _zahl(x) -> float | None:
    return round(float(x), 6) if x is not None and np.isfinite(x) else None


def signal(sym: str, stunden: pd.DataFrame, fuenf: pd.DataFrame, t_e: pd.Timestamp, bid: float, cfg: dict,
           offen_seit: str | None = None, geprueft_bis: str | None = None) -> dict:
    """Was der Test zur Minute t_e (erste Kerze ab 16:00 New York) auf diesem Markt sieht. `kauf`: Der Test kaufte jetzt
    (ohne die Frage, ob schon ein Trade offen ist), mit Stop-Abstand `dist`. offen_seit: Handelstag des Einstiegs eines
    offenen Trades. Dann sagt `raus`, ob er jetzt zu schließen ist, und `grund` warum. geprueft_bis: der letzte
    Handelstag, an dem der Bot den Ausstieg schon gerechnet hat. Hätte der Test an einem Tag danach (ohne Rechnung des
    Bots, etwa nach einem ausgefallenen Lauf) schon verkauft, ist der Ausstieg jetzt fällig. `warten`: Es fehlen
    Kerzen."""
    p = regel(cfg)
    t_e = pd.Timestamp(t_e)
    tag = tag_von(t_e)
    out = {"markt": sym, "tag": str(tag.date()), "zeit_utc": str(t_e), "kauf": False, "raus": False, "grund": None,
           "dist": None, "wr": None, "warten": False, "ergebnis": ""}
    if tag.weekday() >= 5:
        return {**out, "ergebnis": "kein Handelstag (Wochenende)"}
    t_s = schluss(tag, p)
    if not t_s <= t_e <= t_s + pd.Timedelta(minutes=int(p["toleranz_min"])):
        return {**out, "ergebnis": "nicht um 16:00 New York"}
    vorher_h = stunden[(stunden.index < t_s) & (stunden.index >= t_e - pd.Timedelta(days=TAGE_KERZEN))]
    felder, e, ab = zeilen(vorher_h, fuenf, t_s, t_e, bid)
    m = markt_live(sym, felder, cfg)
    g = int(m.gpos[m.tix[e]])
    fertige = int(np.searchsorted(m.gi, m.tix[e]))               # gültige Handelstage vor heute
    out["tage"] = fertige
    if g < 0:
        return {**out, "keine_sitzung": True, "ergebnis": "der Handelstag zählt im Test nicht"}
    if fertige < MIN_TAGE:
        return {**out, "warten": True, "ergebnis": f"zu wenig Kerzen vom Broker ({fertige} fertige Handelstage, nötig "
                                                   f"{MIN_TAGE})"}
    s = sitzungen(m, p)
    heute = -1 if s is None else len(s["C"]) - 1
    if s is None or heute < 1 or s["datum"][heute] != np.datetime64(tag.date()) or s["i_s"][heute] != e:
        return {**out, "keine_sitzung": True, "ergebnis": "keine volle Sitzung 9:30 bis 16:00 New York heute"}
    if ab is None or s["erste"][heute - 1] < np.datetime64(ab, "ns"):
        return {**out, "warten": True, "ergebnis": "zu wenig 5-Minuten-Kerzen vom Broker (Sitzung davor fehlt)"}
    wr = float(s["wr"][heute])
    out.update(wr=_zahl(wr), schluss=_zahl(s["C"][heute]), hoch_vortag=_zahl(s["H"][heute - 1]),
               atr=_zahl(m.atr_vor[g]))
    teile = [f"%R {wr:.1f}"]
    if offen_seit is not None:
        seit = np.datetime64(pd.Timestamp(offen_seit).date())
        bis = max(seit, np.datetime64(pd.Timestamp(geprueft_bis).date())) if geprueft_bis else seit
        nach = (s["datum"] > seit) & (np.arange(len(s["C"])) <= heute)
        zahl, max_tage = int(nach.sum()), int(p["max_tage"])
        out["sitzungen"] = zahl
        regel_raus = np.flatnonzero(nach & (s["datum"] > bis) & s["raus"] & (s["i_s"] >= 0))
        zehnte = np.flatnonzero(nach)[max_tage - 1] if zahl >= max_tage else None
        if len(regel_raus) and (zehnte is None or regel_raus[0] <= zehnte):
            out.update(raus=True, grund="regel")
        elif zehnte is not None:
            out.update(raus=True, grund="zehn_tage")
        if out["raus"]:
            erst = int(regel_raus[0]) if out["grund"] == "regel" else int(zehnte)
            if erst != heute:
                out["faellig_seit"] = str(s["datum"][erst])
            teile.append("Ausstieg: " + GRUND_TEXT[out["grund"]] + (f" (fällig seit {out['faellig_seit']}, der Lauf "
                                                                    f"an diesem Tag fehlte)" if erst != heute else ""))
        else:
            teile.append(f"bleibt offen ({zahl} von {max_tage} Sitzungen)")
    if heute >= int(p["tage"]) and wr < float(p["kauf_unter"]) and np.isfinite(m.atr_vor[g]) and g >= 1:
        out.update(kauf=True, dist=round(float(p["stop_atr"] * m.atr_vor[g]), 6))
        teile.append(f"Kauf (unter {float(p['kauf_unter']):.0f})")
    elif offen_seit is None:
        teile.append(f"kein Kauf (nötig unter {float(p['kauf_unter']):.0f})")
    return {**out, "ergebnis": ", ".join(teile)}


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
    return {"trades": n, "pf_r": None if g is None else round(float(min(g, 999.0)), 3),
            "summe_r": round(float(sum(r)), 2), "trefferquote": round(sum(x > 0 for x in r) / n, 3) if n else None,
            "summe_eur": round(float(sum(float(t.get("pnl_eur") or 0) for t in trades)), 2), "je_markt": je,
            "urteil": text}


_num = sb._num
_zeit = mb._zeit
_rund = mb._rund


# --------------------------------------------------------------------------------------------------------------------
# Ein Lauf

class Lauf:
    """Ein Lauf auf dem Demokonto für beide Märkte. Alle Order- und Schließ-Aufrufe gehen über diese Klasse, damit ein
    Trockenlauf (send_orders=False) nichts beim Broker ändert."""

    def __init__(self, client, state: dict, now: datetime, send_orders: bool = True, cfg: dict | None = None,
                 konto: str | None = None):
        self.client = client
        self.st = copy.deepcopy(state or {})
        self.now = sb._jetzt(now)
        self.stamp = self.now.isoformat(timespec="seconds")
        self.send = send_orders
        self.cfg = cfg
        self.konto = KONTO if konto is None else konto
        self.log: list[dict] = []
        self.fertige: list[dict] = []
        self.q = None
        self.sym = ""
        self.epic = ""
        self.eigene_zu: set[str] = set()
        self.blick: dict = {}
        self.gebunden = 0.0              # Margin der Orders aus diesem Lauf
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
        if not self.konto or str(self.client.account_id) != self.konto:
            raise RuntimeError(f"aktives Konto ist nicht {KONTO_NAME}, nichts gesendet")

    def warte(self, text: str) -> None:
        self.blick.setdefault(self.sym, {})["wartet"] = text

    def kerzen(self) -> tuple[pd.DataFrame, pd.DataFrame] | None:
        try:
            stunden = mb.stundenkerzen(self.client, self.epic, self.now - pd.Timedelta(days=TAGE_KERZEN), self.now)
            fuenf = fuenf_kerzen(self.client, self.epic)
        except Exception as err:            # noqa: BLE001 - der nächste Lauf versucht es wieder
            print(f"Kerzen {self.epic} nicht lesbar: {err}")
            self.warte("Kerzen nicht lesbar")
            return None
        return stunden, fuenf

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
                for a in acts or []
                if a.get("type", "POSITION") == "POSITION" and a.get("status", "ACCEPTED") == "ACCEPTED"]
        zu = sorted((r for r in rows if r["level"] is not None
                     and (r["source"] in ("SL", "TP", "CLOSE_OUT") or "POSITION_CLOSED" in r["actions"])),
                    key=lambda r: r["dateUTC"])
        if not zu:
            return None, "", self.now
        return zu[-1]["level"], str(zu[-1]["source"] or ""), _zeit(zu[-1]["dateUTC"], self.now)

    # ---- Abgleich mit dem Konto ----

    def abschluss(self, tr: dict, level: float, grund: str, wann: pd.Timestamp, **mehr) -> None:
        """Bucht den Trade. R nach Übernachtgebühr mit den Sätzen des Tests (je Nacht über 17:00 New York), das
        Euro-Ergebnis ohne Gebühr."""
        d, dist = int(tr["richtung"]), float(tr["dist"])
        naechte = max(handelstag(wann) - handelstag(tr["opened_utc"]), 0)
        gebuehr_r = float(tr["satz_nacht"]) * naechte / 365.0 * float(tr["entry"]) / dist
        r_roh = d * (level - float(tr["entry"])) / dist
        pnl = float(tr["size"]) * float(tr.get("lot") or 1.0) * d * (level - float(tr["entry"]))
        rate = _num(tr.get("eur_rate")) or (self.q.eur_rate if self.q else None)
        rec = {**{k: tr.get(k) for k in ("id", "markt", "epic", "fassung", "richtung", "tag", "dealId", "size", "entry",
                                         "stop", "dist", "wr", "opened_utc", "spaet_min")},
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
            "id": f"{self.epic} {plan['tag']}", "markt": self.sym, "epic": self.epic, "fassung": FASSUNG,
            "richtung": d, "tag": plan["tag"], "dealId": str(p.get("dealId")), "size": plan["size"],
            "entry": float(level), "stop": _num(p.get("stopLevel")) or plan["stop"], "dist": plan["dist"],
            "bid_ein": plan["bid"], "wr": plan["wr"], "opened_utc": opened_utc, "spaet_min": plan.get("spaet_min"),
            "satz_nacht": plan["satz_nacht"], "lot": plan["lot"], "eur_rate": plan["eur_rate"]}
        self.ev(SEITE[d] + " eröffnet", **{k: self.mst["trade"][k] for k in ("id", "dealId", "size", "entry", "stop",
                                                                            "dist", "wr", "spaet_min")})

    # ---- Führung des offenen Trades ----

    def fuehren(self) -> None:
        """Ein fälliger Ausstieg, der im Lauf um 16:00 New York nicht ging (Markt zu, Schließen gescheitert), kommt im
        nächsten Lauf. Die Entscheidung steht im Trade selbst, so führt der Bot ihn auch ohne lesbare Regeldatei."""
        tr = self.mst.get("trade")
        if not tr or tr.get("weg_seit") or not tr.get("raus_faellig"):
            return
        if not self.q.tradeable:
            self.warte("Ausstieg fällig, Markt zu")
            return
        self.schliesse(tr, tr["raus_faellig"])

    # ---- Täglich um 16:00 New York: Ausstieg und Einstieg ----

    def pruefen(self, eigene: list[dict], fremde: list[dict], available_eur: float | None) -> None:
        """Einmal je Handelstag und Markt, ab 16:00 New York: Schließt der Test einen offenen Trade, und kauft er?"""
        if self.cfg is None:
            self.warte("Regeldatei der YouTube-Runde nicht lesbar (Siegel passt nicht)")
            return
        p = regel(self.cfg)
        tag = tag_von(self.now)
        key = str(tag.date())
        if self.mst.get("letzter_tag") == key or tag.weekday() >= 5:
            return
        t_s = schluss(tag, p)
        if self.now < t_s:
            return
        letzte_chance = self.now - t_s + TAKT > FRIST

        def fertig(ergebnis: str, grund: str | None = None, **kw) -> None:
            """Der Handelstag ist für diesen Markt erledigt. grund: Kurzname, wenn der Bot ihn ohne Rechnung auslässt
            (zählt im Zustand mit, damit ein Bot, der still nie handelt, im Cockpit auffällt)."""
            self.mst["letzter_tag"] = key
            self.mst["letzte_pruefung"] = {"tag": key, "ergebnis": ergebnis, **kw}
            if grund:
                zaehler = self.mst.setdefault("ausgelassen", {})
                zaehler[grund] = int(zaehler.get(grund, 0)) + 1

        if self.now > t_s + FRIST:                         # kein Lauf in der Frist (Ausfall): zählen, nichts rechnen
            if self.send:
                fertig(f"verpasst: kein Lauf in den {int(FRIST.total_seconds() // 60)} Minuten nach 16:00 New York",
                       grund="verpasst")
            return
        tr = self.mst.get("trade")
        if tr and tr.get("weg_seit"):                      # Stop beim Broker, der Schluss ist noch nicht gebucht
            if letzte_chance and self.send:
                return fertig("Position beim Broker zu, Schluss noch nicht gebucht, kein Einstieg", grund="offen")
            self.warte("Position beim Broker zu, Schluss noch nicht gebucht")
            return
        if not self.q.tradeable:
            if letzte_chance and self.send:
                return fertig("Markt um 16:00 New York zu", grund="markt_zu")
            self.warte("Markt zu")
            return
        k = self.kerzen()
        if k is None:
            if letzte_chance and self.send:
                return fertig("Kerzen nicht lesbar", grund="kerzen")
            return
        sig = signal(self.sym, k[0], k[1], self.now, self.q.bid, self.cfg, offen_seit=tr["tag"] if tr else None,
                     geprueft_bis=tr.get("geprueft_bis") if tr else None)
        self.blick.setdefault(self.sym, {})["signal"] = sig
        if sig["warten"]:
            if letzte_chance and self.send:
                return fertig(sig["ergebnis"], grund="kerzen")
            self.warte(sig["ergebnis"])
            return
        if sig.get("keine_sitzung"):                     # Feiertag, halber Tag oder Lücke in den Kerzen: zählt mit
            return fertig(sig["ergebnis"], grund="keine_sitzung")
        kurz = {k: sig.get(k) for k in ("wr", "schluss", "hoch_vortag", "dist", "atr", "sitzungen")}
        if tr:
            if not sig["raus"]:
                tr["geprueft_bis"] = key
                return fertig(sig["ergebnis"], **kurz)
            tr["raus_faellig"] = sig["grund"]
            if not self.schliesse(tr, sig["grund"]):
                return fertig(sig["ergebnis"] + " (Schließen offen, der nächste Lauf versucht es)", **kurz)
            if not sig.get("faellig_seit"):
                # Der Tag ist erledigt, auch wenn erst ein späterer Lauf das Schließen schafft: Der Test kauft nie an
                # der Kerze, an der er aussteigt
                return fertig(sig["ergebnis"] + ". Gleiche Kerze wie ein neuer Einstieg: der Test kauft heute nicht",
                              **kurz)
            # Der Test stieg schon an einem früheren Tag aus und dürfte heute kaufen: weiter wie ohne Trade
        if not sig["kauf"]:
            return fertig(sig["ergebnis"], **kurz)
        spaet = round((self.now - t_s).total_seconds() / 60, 1)
        self.einstieg(sig, tag, eigene, fremde, available_eur, fertig, kurz, spaet)

    def einstieg(self, sig: dict, tag: pd.Timestamp, eigene: list[dict], fremde: list[dict],
                 available_eur: float | None, fertig, kurz: dict, spaet: float) -> None:
        q, d = self.q, 1
        dist = float(sig["dist"])
        stop = _rund(q.bid - d * dist, q)                  # am Bid gemessen wie im Test
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
            frei = None if available_eur is None else available_eur - self.gebunden
            if frei is not None and marge > MARGE_ANTEIL * frei:
                gruende.append(f"Margin {marge:.0f} € wäre mehr als {MARGE_ANTEIL:.0%} des freien Gelds ({frei:.0f} €)")
        abstand = abs(q.offer - stop)
        if q.min_dist and abstand < q.min_dist:
            gruende.append("Stop näher als der Mindestabstand des Brokers")
        info = {"seite": SEITE[d], "tag": str(tag.date()), "dist": round(dist, 4), "stop": stop, "spaet_min": spaet,
                "bid": q.bid, "wr": sig["wr"], "margin_eur": None if marge is None else round(marge, 2)}
        if gruende:
            self.ev("Einstieg ausgelassen", **info, gruende=gruende)
            return fertig("Kauf-Signal, aber kein Einstieg: " + "; ".join(gruende),
                          grund="groesse" if size is None else "sperre", **kurz)
        if not self.send:
            self.ev("würde kaufen", **info, size=size)
            return
        fertig("Kauf gesendet", **kurz)                    # vor der Order: nie eine zweite Order für denselben Tag
        self.gebunden += marge or 0.0
        vorher = {str(x["position"].get("dealId")) for x in eigene + fremde}
        satz = self.cfg["kosten"]["nacht_pro_jahr"]["index"]["long"]
        plan = {"tag": str(tag.date()), "richtung": d, "size": size, "dist": round(dist, 6), "stop": stop, "bid": q.bid,
                "spaet_min": spaet, "wr": sig["wr"], "satz_nacht": float(satz), "lot": q.lot or 1.0,
                "eur_rate": q.eur_rate}
        body = {"epic": self.epic, "direction": "BUY", "size": size, "guaranteedStop": False, "stopLevel": stop}
        conf = None
        try:
            self.nur_mein_konto()
            ref = self.client._request("POST", "/positions", json=body).json()["dealReference"]
            conf = self.client.confirm(ref) or {}
        except Exception as err:            # noqa: BLE001 - kein zweiter Versuch, damit nichts doppelt entsteht
            self.ev("Order ohne Bestätigung", **info, fehler=str(err)[:200])
            fertig("Kauf gesendet, Bestätigung fehlt", **kurz)
        if conf is not None and str(conf.get("dealStatus") or "").upper() == "REJECTED":
            self.ev("Order abgelehnt", **info, grund=conf.get("reason"))
            return fertig(f"Kauf-Signal, aber die Order wurde abgelehnt ({conf.get('reason')})", **kurz)
        try:
            jetzt = [x["position"] for x in self.client.positions() if (x.get("market") or {}).get("epic") == self.epic]
        except Exception as err:            # noqa: BLE001
            print(f"Positionen nach der Order nicht lesbar: {err}")
            jetzt = None
        neu = [x for x in jetzt or [] if str(x.get("dealId")) not in vorher and x.get("direction", "BUY") == "BUY"]
        deal = ((conf or {}).get("affectedDeals") or [{}])[0].get("dealId") or (conf or {}).get("dealId")
        if len(neu) == 1 or (conf and deal):                # sonst bestätigt, aber noch nicht bei den Positionen
            fertig("Kauf eröffnet", **kurz)
            return self.uebernehmen(neu[0] if len(neu) == 1 else {"dealId": deal, "level": conf.get("level")}, plan,
                                    self.stamp)
        # keine Bestätigung und keine Position gefunden: Der nächste Lauf sucht sie an Richtung und Größe
        self.mst["ungeklaert"] = {**plan, "seit": self.stamp, "vorher": sorted(vorher)}


def run(client, state: dict, now: datetime, send_orders: bool = True) -> tuple[dict, list[dict], list[dict], dict]:
    """Ein Lauf. Rückgabe: neuer Stand, Ereignisse, fertige Trades, Blick (für das Cockpit)."""
    from suche.demo_bots import eur_rate, quote_from_market

    lauf = Lauf(client, state, now, send_orders, cfg=lade_cfg(pruefen=True))      # ohne Siegel kein Signal
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
    naechster = None
    if lauf.cfg:                                           # die nächste 16:00 New York Montag bis Freitag
        p, tag = regel(lauf.cfg), tag_von(lauf.now)
        while naechster is None or naechster + FRIST < lauf.now or tag.weekday() >= 5:
            if naechster is not None:
                tag += pd.Timedelta(days=1)
            naechster = schluss(tag, p)
    return {"naechste_pruefung_utc": None if naechster is None else str(naechster),
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
            teile.append(f"{name}: Kauf offen seit {tr['tag']} ab {tr['entry']}, Stop {tr['stop']}, Ausstieg um "
                         f"16:00 New York nach der Regel")
        elif m.get("ungeklaert"):
            teile.append(f"{name}: Order gesendet, Bestätigung fehlt, der nächste Lauf sieht nach")
    if teile:
        return ". ".join(teile)
    zuletzt = [m.get("letzte_pruefung") for m in (st.get("maerkte") or {}).values() if m.get("letzte_pruefung")]
    if not zuletzt:
        return "kein Trade offen, wartet auf 16:00 New York"
    p = max(zuletzt, key=lambda x: x["tag"])
    return f"kein Trade offen. Zuletzt (Handelstag {p['tag']}): {p['ergebnis']}"


def cockpit(st: dict, alle_trades: list[dict], blick: dict) -> dict:
    offen = [{k: m["trade"].get(k) for k in ("id", "markt", "epic", "fassung", "richtung", "tag", "entry", "stop",
                                              "size", "dist", "wr", "opened_utc")}
             for m in (st.get("maerkte") or {}).values() if m.get("trade")]
    return {"bot": BOT_ID, "name": NAME, "konto": KONTO_NAME, "stand": st.get("stand"), "start": st.get("start"),
            "pausiert": st.get("pausiert"), "status": status(st), "regel": REGEL, "backtest": TEST,
            "vorab": "suche/VORAB_williams_bot.yaml", "vorab_ok": vorab_ok(),
            "maerkte": {sym: NAMEN.get(sym, sym) for sym in MAERKTE}, "offen": offen,
            "ausgelassen": {sym: m.get("ausgelassen") or {} for sym, m in (st.get("maerkte") or {}).items()},
            "zusammenfassung": bewertung(alle_trades), "letzte_trades": alle_trades[-10:], "blick": blick}


def _ohne_zeit(st: dict) -> dict:
    return {k: v for k, v in (st or {}).items() if k != "stand"}


def schreiben(st: dict, log: list[dict], fertige: list[dict], blick: dict, jdir: Path = JDIR,
              cockpit_pfad: Path = COCKPIT) -> bool:
    """Schreibt Zustand, Log, Trades und Cockpit. Hat sich außer der Uhrzeit nichts geändert, schreibt der Lauf
    nichts."""
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
        print("Keine Capital.com-Zugangsdaten, Williams %R übersprungen")
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
