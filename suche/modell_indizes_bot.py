"""Vorhersage-Modell auf fünf Indizes, live auf einem Capital.com-DEMOKONTO. Nie echtes Geld.

    python -m suche.modell_indizes_bot              # ein Lauf: offene Trades führen, nach 18 Uhr New York Einstiege?
    python -m suche.modell_indizes_bot --dry-run    # nur rechnen und zeigen, keine Order

Kirons Wahl vom 20.11.2026 12:25 UTC auf der Karte "Welches Vorhersage-Modell soll Bot 2 werden?": "Modell Indizes,
jetzt bauen" (zu seinem Wunsch "Schatten soll direkt Live-Demo sein"). Die Regel ist die Fassung modell_indizes aus
suche/VORAB_grosse_runde.yaml, unverändert. Sie hat den Test NICHT bestanden, sie ist ein Kandidat
(suche/ergebnis_grosse_runde.md): 2024 bis 2026 1.874 Trades, Gewinnfaktor 1,21, mit 1,5-fachen Kosten 1,16, beide
Hälften über 1, besser als 97,5 % der Zufallsläufe, aber nur 1,89 Standardabweichungen über dem Zufall (nötig 3) und
ohne Holm. Vor 2024 verlor dieselbe Rechnung (Gewinnfaktor 0,94). Das Schatten-Labor zählt dieselbe Fassung ohne
Order unverändert weiter (suche/VORAB_schatten.yaml). Regeln des Bots und Urteil stehen in
suche/VORAB_modell_indizes_bot.yaml, Prüfsumme im Protokoll vor dem ersten Trade. Ohne passende Prüfsumme öffnet der
Bot nichts.

Regel (gemeinsames Modell für US500, US100, DAX, FTSE 100 und Nikkei 225):
- Ein Vorhersage-Modell (logistische Regression mit Strafe gegen Überanpassung) schätzt zu jedem Handelstag die
  Wahrscheinlichkeit, dass der Index vom Einstieg bis 15:55 New York steigt. Merkmale, alle vom Vortag: Lauf über 1,
  2, 5 und 20 Tage in ATR, RSI 2 und 14, Abstand zum 50- und 200-Tage-Schnitt, Lage des Schlusskurses im Vortag,
  Schwankung gegen ihre 100 Tage, Wochentag, VIX, VIX-Änderung, VIX gegen VIX3M, Änderung der 10- und 2-jährigen
  US-Rendite über 5 Tage, ein eigener Grundwert je Markt.
- Ab 54 % kauft der Bot, bis 46 % verkauft er, dazwischen nichts. Einstieg mit dem ersten Kurs ab 18:00 New York am
  Vorabend des Handelstags, Stop 2 Tages-ATR beim Broker, kein Ziel, Ausstieg zum Markt vor 15:55 New York.
- Höchstens ein Trade je Markt, also höchstens fünf zugleich.

Live-Ausführung:
- Das Modell lernt im Test zu jedem Kalenderjahr neu, nur mit den Jahren davor. Live fehlen dem Bot die Kurse von
  HistData, darum nimmt er für jedes Jahr genau die Zahlen, die der Test in diesem Jahr benutzt
  (suche/modell_indizes_gewichte.json, gebaut von suche/modell_indizes_gegenprobe.py, Prüfsumme in der Regeldatei).
  Für 2027 gibt es noch keine Gewichte, dann öffnet der Bot nichts, bis eine neue Datei per PR kommt.
- Merkmale, Stop und Ausstiegszeit rechnet die Funktion des Tests (suche/grosse_runde.merkmale und _tagestrades) auf
  Stundenkerzen von Capital.com (420 Tage), jede als zwölf gleiche 5-Minuten-Zeilen, dahinter eine Zeile zur Minute
  des Einstiegs mit dem aktuellen Bid.
- VIX und VIX3M kommen direkt von Cboe, die Renditen direkt vom US-Finanzministerium. Das sind die Quellen der
  FRED-Reihen des Tests (VIXCLS, VXVCLS, DGS10, DGS2). FRED selbst veröffentlicht sie erst einen Tag später. Fehlt
  beim letzten Lauf in der Frist noch der Wert vom Vortag, lässt der Bot den Handelstag aus. Mit einem Tag älteren
  Werten hätte das Modell im Test an 13 % der Tage anders entschieden.
- Der Lauf kommt alle 15 Minuten. Eingestiegen wird höchstens 20 Minuten nach dem ersten Kurs des Handelstags beim
  Broker. Ausgestiegen wird im ersten Lauf ab 15:40 New York, damit DAX und FTSE (Schluss bei Capital.com um 16:00
  New York) noch offen sind.
- Nur Account 6, den er mit der Groß-Box (Gold) und dem Labor-Bot London GBP/USD teilt (andere Märkte). Die
  Kontonummer findet er nach dem Namen über journal/konten.json (suche/mitnutzer.konto_nach_name). Er kennt seine
  Positionen an der Deal-ID. Liegt eine fremde Position auf demselben Markt, öffnet er dort nichts Neues.
- Ab -25 R seit Start nichts Neues mehr (Sicherung), zurück nur mit Kirons Entscheidung.
- Er schreibt nur journal/modell-indizes/ und journal/modell-indizes.json.
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
from suche import rueckblick as rb
from suche import schluss as belegt_pruefung
from suche import youtube_runde as yr
from suche import youtube_runde2 as y2
from suche.rueckblick_daten import MAERKTE as _EPICS

ROOT = Path(gr.ROOT)
BOT_ID = "modell-indizes"
NAME = "Vorhersage-Modell Indizes (US500, US100, DAX, FTSE, Nikkei)"
KONTO_NAME = "Account 6"              # geteilt mit gold-grossbox (Gold) und r6-london-gbpusd (GBP/USD)
HAUPT_ENDUNG = sb.HAUPT_ENDUNG        # Hauptkonto des Gold-Bots, hier nie handeln
FASSUNG = "modell_indizes"
JAHRE = [2024, 2025, 2026]            # Jahre mit Gewichten (2024 und 2025 nur für die Gegenprobe)
RISIKO_EUR = 5.0
MAX_RISIKO_FAKTOR = 2.0               # Runden auf die kleinste Größe darf das Risiko höchstens verdoppeln
MARGE_ANTEIL = 0.2                    # eine Order darf höchstens diesen Teil des freien Gelds als Margin brauchen
PAUSE_R = -25.0
ZWISCHEN_NACH, ZWISCHEN_PF = 15, 0.6
URTEIL_NACH, URTEIL_PF = 40, 1.2
TAGE_KERZEN = 420                     # so viele Kalendertage Stundenkerzen je Rechnung (200-Tage-Schnitt, RSI 14)
MIN_TAGE = 220                        # mit weniger gültigen Handelstagen vor dem Einstieg rechnet der Bot nichts
FRIST = pd.Timedelta(minutes=20)      # so lange nach dem ersten Kurs des Handelstags darf der Bot noch einsteigen
TAKT = pd.Timedelta(minutes=15)       # Abstand der Läufe
AUS_VORLAUF = pd.Timedelta(minutes=15)     # Ausstieg im ersten Lauf ab 15:55 New York minus diese Zeit
SCHLUSS_WARTEN = pd.Timedelta(hours=1)     # so lange sucht der Bot den Schlusskurs beim Broker, dann schätzt er
NACHPRUEFEN = pd.Timedelta(days=30)        # so alte Buchungen prüft wieder_fuehren, ob ihre Position noch offen liegt
STUNDE = pd.Timedelta(hours=1)
FUENF = np.timedelta64(5, "m")
FMT = "%Y-%m-%dT%H:%M:%S"
SPALTEN = ["open", "high", "low", "close"]
VORAB = ROOT / "suche" / "VORAB_modell_indizes_bot.yaml"
KEY = "VORAB_modell_indizes_bot sha256 "
GEWICHTE = ROOT / "suche" / "modell_indizes_gewichte.json"
JDIR = ROOT / "journal" / "modell-indizes"
COCKPIT = ROOT / "journal" / "modell-indizes.json"
FREMDE_DATEIEN = sb.GOLD_BOT_DATEIEN + ("konten.json", "r6-bots.json", "gold-grossbox.json", "welt-ausbruch4h.json",
                                        "krypto-bollinger.json")
SEITE = {1: "Kauf", -1: "Verkauf"}
NAMEN = {"SPXUSD": "US500", "NSXUSD": "US100", "GRXEUR": "DAX", "UKXGBP": "FTSE 100", "JPXJPY": "Nikkei 225"}
# Fremde Reihen: Name im Test (FRED) -> Quelle live. Cboe und das US-Finanzministerium liefern dieselben Zahlen wie FRED
# (geprüft in suche/modell_indizes_gegenprobe.py), aber noch am selben Abend.
CBOE = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{name}_History.csv"
TREASURY = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
            "{jahr}/all?type=daily_treasury_yield_curve&field_tdr_date_value={jahr}&page&_format=csv")
QUELLEN = {"VIXCLS": ("Cboe", "VIX"), "VXVCLS": ("Cboe", "VIX3M"), "DGS10": ("US-Finanzministerium", "10 Yr"),
           "DGS2": ("US-Finanzministerium", "2 Yr")}
# Tage ohne Wert in der Reihe, obwohl Werktag (Börse New York und Anleihemarkt geschlossen). Nur bis Ende 2026, denn für
# 2027 braucht der Bot ohnehin neue Gewichte und eine neue Regeldatei.
FEIERTAGE = {"VIXCLS": ["2026-11-26", "2026-12-25"], "VXVCLS": ["2026-11-26", "2026-12-25"],
             "DGS10": ["2026-11-26", "2026-12-25"], "DGS2": ["2026-11-26", "2026-12-25"]}
REGEL = ("Vorhersage-Modell auf US500, US100, DAX, FTSE 100 und Nikkei 225 (Fassung modell_indizes): Eine logistische "
         "Regression schätzt aus Kursen des Vortags, VIX und US-Renditen, ob der Index bis 15:55 New York steigt. Ab 54 % "
         "Kauf, bis 46 % Verkauf, Einstieg ab 18:00 New York, Stop 2 Tages-ATR, kein Ziel, Ausstieg vor 15:55 New York. "
         "Höchstens ein Trade je Markt, 5 € Risiko.")
TEST = ("Test NICHT bestanden, Kandidat (suche/ergebnis_grosse_runde.md): 2024 bis 2026 1.874 Trades (etwa 12,7 je "
        "Woche), Gewinnfaktor 1,21, mit 1,5-fachen Kosten 1,16, Hälften 1,09 und 1,34, 2026 1,27, aber z 1,89 statt 3 "
        "und ohne Holm. Vor 2024 Gewinnfaktor 0,94. Fast nur Käufe. Auf 1.000 € mit 10 € je Trade im Rückblick etwa "
        "13 € im Monat. Kirons Wahl vom 20.11.2026: eine der zwei stärksten Fassungen live testen.")


def _roh_fassung() -> dict:
    import yaml
    return yaml.safe_load(gr.vorab(1).read_text(encoding="utf-8"))["grosse_runde"]["varianten"][FASSUNG]


MAERKTE = {sym: _EPICS[sym][0] for sym in _roh_fassung()["maerkte"]}     # HistData-Name -> Epic bei Capital.com


def konto_id(konten_daten: dict | None = None) -> str:
    """Die volle Kontonummer von Account 6 aus journal/konten.json, gesucht nach dem Namen (suche/mitnutzer.py
    konto_nach_name). Leer, wenn es das Konto dort nicht genau einmal gibt. Die Nummer wird nie abgetippt und nie
    ausgegeben."""
    from suche.mitnutzer import konto_nach_name
    return konto_nach_name(KONTO_NAME, konten_daten)


KONTO = konto_id()


def lade_cfg(pruefen: bool = False) -> dict | None:
    """Die versiegelte große Runde (Durchgang 1). None, wenn die Regeldatei nicht zu ihrem Siegel passt."""
    try:
        return gr.lade_vorab(1, pruefen=pruefen)
    except SystemExit:
        return None


def regel(cfg: dict) -> dict:
    return cfg["regeln"][FASSUNG]


def gruppe(cfg: dict) -> list[str]:
    return list(cfg["varianten"][FASSUNG]["maerkte"])


def grundwerte(nr: int, anzahl: int, zeilen: int) -> np.ndarray:
    """Der eigene Grundwert je Markt wie in gr.regel_modell: eine Spalte je Markt außer dem ersten."""
    eigen = np.zeros((zeilen, anzahl - 1))
    if nr > 0:
        eigen[:, nr - 1] = 1.0
    return eigen


def merkmal_namen(cfg: dict) -> list[str]:
    p, g = regel(cfg), gruppe(cfg)
    namen = [f"lauf_{k}" for k in p["rueckblick_tage"]] + [f"rsi_{n}" for n in p["rsi"]]
    namen += [f"abstand_{n}" for n in p["schnitt_tage"]] + ["lage_im_tag", "schwankung"]
    namen += [f"wochentag_{w}" for w in range(4)] + ["vix", "vix_aenderung", "vix_kurve", "DGS10_5", "DGS2_5"]
    return namen + [f"markt_{s}" for s in g[1:]]


def wahrscheinlichkeit(x: np.ndarray, par: dict) -> float:
    """Wahrscheinlichkeit für "steigt" einer Zeile, gerechnet wie gr.vorhersagen mit den Zahlen eines Jahres."""
    mittel, streu, w = (np.asarray(par[k], dtype=float) for k in ("mittel", "streu", "gewichte"))
    z = (np.asarray(x, dtype=float) - mittel) / streu
    z = np.clip(np.where(np.isfinite(z), z, 0.0), -5.0, 5.0)
    return float(1.0 / (1.0 + np.exp(-np.clip(np.r_[1.0, z] @ w, -30, 30))))


def richtung(q: float, p: dict) -> int:
    """Wie gr.regel_modell: ab 0,5 + abstand Kauf, bis 0,5 - abstand Verkauf."""
    return int(np.where(q >= 0.5 + p["abstand"], 1, np.where(q <= 0.5 - p["abstand"], -1, 0)))


def _sha(text: str) -> str:
    from suche.runde1 import sha256_text
    return sha256_text(text)


def _vorab_bot() -> dict | None:
    import yaml
    try:
        return yaml.safe_load(VORAB.read_text(encoding="utf-8"))["modell_indizes_bot"]
    except (OSError, KeyError, TypeError, ValueError):
        return None


def lade_gewichte(pruefen: bool = True) -> dict | None:
    """Die Zahlen des Modells je Jahr. Mit pruefen nur, wenn ihre Prüfsumme die aus der Regeldatei des Bots ist."""
    try:
        text = GEWICHTE.read_text(encoding="utf-8")
    except OSError:
        return None
    if pruefen:
        v = _vorab_bot()
        if not v or (v.get("gewichte") or {}).get("sha256") != _sha(text):
            return None
    return json.loads(text)


def vorab_ok() -> bool:
    """Ist die Regeldatei des Bots versiegelt, passen die große Runde und die Gewichte zu ihren Siegeln? Nur dann
    öffnet der Bot etwas."""
    from suche.runde1 import journal_lines, last_value
    if not VORAB.exists() or lade_cfg(pruefen=True) is None or lade_gewichte(pruefen=True) is None:
        return False
    return last_value(journal_lines(), KEY) == _sha(VORAB.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------------------------------------
# Zeit

def _ny(idx) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(idx).tz_localize("UTC").tz_convert(rb.NY).tz_localize(None)


def handelstag(t) -> int:
    """Handelstag (endet 17:00 Uhr New York) als Tageszahl, wie `tag` in den Kursdateien des Tests."""
    ny = _ny([pd.Timestamp(t)])[0]
    return int(((ny + pd.Timedelta(hours=7)).normalize() - pd.Timestamp("1970-01-01")).days)


def tag_von(t) -> pd.Timestamp:
    """Der Handelstag (Kalendertag, an dem er um 17:00 New York endet), in den die UTC-Zeit t fällt."""
    return pd.Timestamp("1970-01-01") + pd.Timedelta(days=handelstag(t))


def tagesende(t: pd.Timestamp) -> pd.Timestamp:
    """Ende des Handelstags (17:00 Uhr New York), in den t fällt, als UTC."""
    return (tag_von(t) + pd.Timedelta(hours=17)).tz_localize(rb.NY).tz_convert("UTC").tz_localize(None)


def einstieg_ab(tag: pd.Timestamp, cfg: dict) -> pd.Timestamp:
    """Beginn des Einstiegs für den Handelstag: 17:00 New York am Vortag plus die Pause des Tests (18:00), als UTC."""
    t0 = (pd.Timestamp(tag) - pd.Timedelta(days=1) + pd.Timedelta(hours=17)).tz_localize(rb.NY).tz_convert("UTC")
    return t0.tz_localize(None) + pd.Timedelta(minutes=int(cfg["daten"]["pause_min"]))


def einstieg_bis(tag: pd.Timestamp, cfg: dict) -> pd.Timestamp:
    """Ende des Einstiegs im Test: so lange darf die erste Kerze nach der Pause auf sich warten lassen."""
    return einstieg_ab(tag, cfg) + pd.Timedelta(minutes=int(cfg["tageshandel"]["toleranz_min"]))


def ausstieg(tag: pd.Timestamp, cfg: dict) -> pd.Timestamp:
    """Spätester Ausstieg des Tests: 15:55 New York am Handelstag, als UTC."""
    return pd.Timestamp(y2._ny_utc(pd.DatetimeIndex([pd.Timestamp(tag)]), int(cfg["tageshandel"]["aus_min"]))[0])


# --------------------------------------------------------------------------------------------------------------------
# Kerzen und fremde Reihen (Netz nur in stundenkerzen und fremd_holen)

def stundenkerzen(client, epic: str, von: pd.Timestamp, bis: pd.Timestamp) -> pd.DataFrame:
    """Fertige Stundenkerzen (Bid) von `von` bis `bis`, in Abrufen zu je 40 Tagen (nur lesen). Gibt der Broker für
    einen älteren Abschnitt nichts mehr her, hört der Abruf dort auf."""
    from suche.demo_bots import frame
    teile, ende = [], pd.Timestamp(bis)
    while ende > von:
        ab = max(pd.Timestamp(von), ende - pd.Timedelta(days=40))
        got = client._get(f"/prices/{epic}", resolution="HOUR", max=1000,
                          **{"from": ab.strftime(FMT), "to": ende.strftime(FMT)}).get("prices", [])
        if not got and teile:
            break
        teile.extend(got)
        ende = ab
    bars, _ = frame(teile)
    if not len(bars):
        return pd.DataFrame(columns=SPALTEN, dtype=float, index=pd.DatetimeIndex([]))
    bars = bars[~bars.index.duplicated(keep="last")].sort_index()
    return bars[bars.index + STUNDE <= bis][SPALTEN]


def fremd_holen(jetzt: pd.Timestamp, get=None) -> dict[str, pd.Series]:
    """VIX und VIX3M von Cboe, die Renditen 10 und 2 Jahre vom US-Finanzministerium (dieses und letztes Jahr).
    Je Reihe Tageswerte mit Datum, ohne Lücken."""
    if get is None:
        import requests
        get = requests.get
    out = {}
    for name, (_, quelle) in QUELLEN.items():
        if name.startswith("VX") or name.startswith("VIX"):
            r = get(CBOE.format(name=quelle), timeout=30)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            werte = pd.to_numeric(df["CLOSE"], errors="coerce").to_numpy(float)
            out[name] = pd.Series(werte, index=pd.to_datetime(df["DATE"], format="%m/%d/%Y")).dropna().sort_index()
    teile = []
    for jahr in (jetzt.year - 1, jetzt.year):
        r = get(TREASURY.format(jahr=jahr), timeout=30)
        r.raise_for_status()
        teile.append(pd.read_csv(io.StringIO(r.text)))
    df = pd.concat(teile, ignore_index=True)
    tage = pd.to_datetime(df["Date"], format="%m/%d/%Y")
    for name in ("DGS10", "DGS2"):
        s = pd.Series(pd.to_numeric(df[QUELLEN[name][1]], errors="coerce").to_numpy(float), index=tage).dropna()
        out[name] = s[~s.index.duplicated(keep="last")].sort_index()
    return out


def fremd_schreiben(reihen: dict[str, pd.Series], ordner: Path) -> Path:
    """Die Reihen im Format der FRED-Dateien des Tests (observation_date,NAME)."""
    for name, s in reihen.items():
        pd.DataFrame({"observation_date": pd.DatetimeIndex(s.index).strftime("%Y-%m-%d"),
                      name: s.to_numpy(float)}).to_csv(ordner / f"{name}.csv", index=False)
    return ordner


@contextlib.contextmanager
def fred_ordner(pfad: Path | None):
    """Der Test liest seine Reihen aus gr.FRED. Mit pfad liest er sie hier aus den Dateien des Bots."""
    if pfad is None:
        yield
        return
    alt = gr.FRED
    gr.FRED = Path(pfad)
    gr.fred.cache_clear()
    try:
        yield
    finally:
        gr.FRED = alt
        gr.fred.cache_clear()


@contextlib.contextmanager
def fremd_verspaetet(reihen):
    """Für die Gegenprobe: diese Reihen erscheinen einen Tag später (lag 1 in gr.vor)."""
    alt = gr.vor

    def vor(name, tage, k=0, lag=0):
        return alt(name, tage, k, 1 if name in reihen else lag)

    gr.vor = vor
    try:
        yield
    finally:
        gr.vor = alt


def erwartet(name: str, tag: pd.Timestamp) -> pd.Timestamp:
    """Der jüngste Wert, den der Test für diesen Handelstag nähme: der letzte Werktag davor ohne Feiertag der Reihe."""
    frei = {pd.Timestamp(x) for x in FEIERTAGE.get(name, [])}
    d = pd.Timestamp(tag) - pd.Timedelta(days=1)
    while d.weekday() >= 5 or d in frei:
        d -= pd.Timedelta(days=1)
    return d


def fremd_stand(reihen: dict[str, pd.Series], tag: pd.Timestamp) -> dict:
    """Je Reihe: Datum des Werts, den der Bot für diesen Handelstag nimmt, und ob es das erwartete ist."""
    out = {}
    for name in QUELLEN:
        s = reihen.get(name)
        vor = s[s.index < pd.Timestamp(tag)] if s is not None else None
        datum = None if vor is None or not len(vor) else vor.index[-1]
        out[name] = {"datum": None if datum is None else str(datum.date()), "erwartet": str(erwartet(name, tag).date()),
                     "frisch": datum is not None and datum >= erwartet(name, tag)}
    return out


# --------------------------------------------------------------------------------------------------------------------
# Signal (ohne Netz)

def zeilen(stunden: pd.DataFrame, t_e: pd.Timestamp, bid: float) -> tuple[dict, int]:
    """Die Kursdatei des Tests aus Stundenkerzen: jede Stundenkerze als zwölf gleiche 5-Minuten-Zeilen, dann die
    Einstiegszeile zur Zeit t_e mit dem aktuellen Bid. Dahinter Zeilen mit demselben Bid bis zum Ende des Handelstags,
    damit der Handelstag als gültig zählt wie im Test (sie liegen alle nach dem Einstieg, das Modell liest nur Werte vom
    Vortag). Rückgabe: Felder der npz-Datei und die Zeile des Einstiegs."""
    alt = stunden[stunden.index + STUNDE <= t_e][SPALTEN]
    t_alt = (alt.index.values.astype("datetime64[ns]")[:, None] + np.arange(12) * FUENF).ravel()
    werte = {k: np.repeat(alt[s].to_numpy(float), 12) for k, s in zip("ohlc", SPALTEN)}
    ende = tagesende(t_e)
    t_neu = np.arange(np.datetime64(t_e, "ns"), np.datetime64(max(ende, t_e + STUNDE), "ns"), FUENF)
    t = np.r_[t_alt, t_neu].astype("datetime64[ns]")
    for k in "ohlc":
        werte[k] = np.r_[werte[k], np.full(len(t_neu), float(bid))]
    ny = _ny(t)
    tag = (ny + pd.Timedelta(hours=7)).normalize().values.astype("datetime64[D]")
    return {"t": t, **werte, "sp": np.zeros(len(t)), "nymin": np.asarray(ny.hour * 60 + ny.minute, dtype=np.int32),
            "tag": tag}, len(t_alt)


def markt_live(sym: str, stunden: pd.DataFrame, t_e: pd.Timestamp, bid: float, cfg: dict) -> tuple[yr.Markt, int]:
    """Der Markt des Tests (Tageskerzen wie suche/rueckblick.Markt) aus diesen Zeilen und die Zeile des Einstiegs."""
    felder, e = zeilen(stunden, t_e, bid)
    with tempfile.TemporaryDirectory() as tmp:
        np.savez(Path(tmp) / f"{sym}.npz", **felder)
        return yr.Markt(sym, Path(tmp), cfg), e


def _zahl(x) -> float | None:
    return round(float(x), 6) if x is not None and np.isfinite(x) else None


def signal(sym: str, stunden: pd.DataFrame, t_e: pd.Timestamp, bid: float, cfg: dict, gew: dict,
           fred: Path | None = None) -> dict:
    """Was der Test zur Minute t_e (Einstieg nach 18:00 New York) auf diesem Markt sieht. `ok` heißt: Der Test nähme
    diesen Einstieg (ohne die Frage, ob schon ein Trade offen ist), dazu Richtung, Stop-Abstand und Ausstiegszeit.
    `warten` heißt: Es fehlen Kerzen. fred: Ordner mit den Reihen im FRED-Format (None: die Dateien des Tests).
    Die Entscheidung treffen allein gr.merkmale, die Gewichte des Jahres und gr._tagestrades."""
    p, g_liste = regel(cfg), gruppe(cfg)
    t_e = pd.Timestamp(t_e)
    tag = tag_von(t_e)
    out = {"markt": sym, "tag": str(tag.date()), "einstieg_utc": str(t_e), "richtung": 0, "wahrscheinlichkeit": None,
           "dist": None, "bis_utc": None, "ok": False, "warten": False, "ergebnis": ""}
    if tag.weekday() >= 5:
        return {**out, "ergebnis": "kein Handelstag (Wochenende)"}
    ab = einstieg_ab(tag, cfg)
    if not ab <= t_e <= einstieg_bis(tag, cfg):
        return {**out, "ergebnis": "außerhalb des Einstiegs (18:00 bis 3:00 New York)"}
    vorher = stunden[(stunden.index < ab) & (stunden.index >= t_e - pd.Timedelta(days=TAGE_KERZEN))]
    m, e = markt_live(sym, vorher, t_e, bid, cfg)
    g = int(m.gpos[m.tix[e]])
    fertige = int(np.searchsorted(m.gi, m.tix[e]))               # gültige Handelstage vor dem Tag des Einstiegs
    out["tage"] = fertige
    if g < 0:
        return {**out, "ergebnis": "der Handelstag zählt im Test nicht"}
    if fertige < MIN_TAGE:
        return {**out, "warten": True, "ergebnis": f"zu wenig Kerzen vom Broker ({fertige} fertige Handelstage, nötig "
                                                   f"{MIN_TAGE})"}
    par = (gew.get("jahre") or {}).get(str(tag.year))
    if par is None:
        return {**out, "ergebnis": f"keine Gewichte für {tag.year} (neue Datei per PR nötig)"}
    with fred_ordner(fred):
        X, _, namen = gr.merkmale(m, cfg, p, g_liste)
        stand = {n: str(gr.vor(n, np.array([np.datetime64(tag.date())]))[1][0]) for n in QUELLEN}
    x = np.r_[X[g], grundwerte(g_liste.index(sym), len(g_liste), 1)[0]]
    q = wahrscheinlichkeit(x, par)
    d = richtung(q, p)
    out.update(wahrscheinlichkeit=round(q, 6), richtung=d, fremd_datum=stand,
               merkmale={n: _zahl(v) for n, v in zip(namen, X[g])}, atr=_zahl(m.atr_vor[g]))
    unten, oben = 0.5 - p["abstand"], 0.5 + p["abstand"]
    if d == 0:
        return {**out, "ergebnis": f"kein Trade: {q:.1%} für steigt, zwischen {unten:.0%} und {oben:.0%}"}
    rich = np.zeros(len(m.gtag), np.int64)
    rich[g] = d
    treffer = [s for s in gr._tagestrades(m, cfg, rich, p["stop_atr"]) if int(s["i0"]) == e]
    if not treffer or not treffer[0]["sd"] > 0:
        return {**out, "ergebnis": f"{SEITE[d]}-Signal ({q:.1%}), aber kein Einstieg nach der Regel (keine ATR)"}
    s = treffer[0]
    return {**out, "ok": True, "dist": round(float(s["sd"]), 6), "bis_utc": str(pd.Timestamp(s["t_max"])),
            "ergebnis": f"{SEITE[d]}: {q:.1%} für steigt"}


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
    """Ein Lauf auf dem Demokonto für alle fünf Märkte. Alle Order- und Schließ-Aufrufe gehen über diese Klasse, damit
    ein Trockenlauf (send_orders=False) nichts beim Broker ändert."""

    def __init__(self, client, state: dict, now: datetime, send_orders: bool = True, cfg: dict | None = None,
                 gew: dict | None = None, fremd_get=None, ordner: Path | None = None, konto: str | None = None):
        self.client = client
        self.st = copy.deepcopy(state or {})
        self.now = _jetzt(now)
        self.stamp = self.now.isoformat(timespec="seconds")
        self.send = send_orders
        self.cfg = cfg
        self.gew = gew
        self.fremd_get = fremd_get
        self.ordner = ordner
        self.konto = KONTO if konto is None else konto
        self._fremd: dict | None = None
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
        if not self.konto or str(self.client.account_id) != self.konto:
            raise RuntimeError(f"aktives Konto ist nicht {KONTO_NAME}, nichts gesendet")

    def warte(self, text: str) -> None:
        self.blick.setdefault(self.sym, {})["wartet"] = text

    def kerzen(self, von: pd.Timestamp) -> pd.DataFrame | None:
        try:
            return stundenkerzen(self.client, self.epic, von, self.now)
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
                                   **{"from": ab.strftime(FMT), "to": self.now.strftime(FMT)}).get("prices", [])
        except Exception as err:            # noqa: BLE001
            print(f"5-Minuten-Kerzen {self.epic} nicht lesbar: {err}")
            self.warte("5-Minuten-Kerzen nicht lesbar")
            return None
        bars, _ = frame(got)
        bars = bars[bars.index >= ab] if len(bars) else bars
        return pd.Timestamp(bars.index.min()) if len(bars) else self.now

    def fremd(self) -> dict:
        """VIX und Renditen einmal je Lauf holen und für den Test als Dateien ablegen."""
        if self._fremd is None:
            try:
                reihen = fremd_holen(self.now, self.fremd_get)
                fremd_schreiben(reihen, self.ordner)
                self._fremd = {"reihen": reihen}
            except Exception as err:        # noqa: BLE001 - der nächste Lauf versucht es wieder
                print(f"VIX oder Renditen nicht lesbar: {err}")
                self._fremd = {"fehler": str(err)[:200]}
        return self._fremd

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
        rec = {**{k: tr.get(k) for k in ("id", "markt", "epic", "richtung", "tag", "dealId", "size", "entry", "stop",
                                         "dist", "wahrscheinlichkeit", "opened_utc", "spaet_min", "nach_18_min")},
               "seite": SEITE[d], "exit": round(level, 4), "grund": grund,
               "closed_utc": pd.Timestamp(wann).isoformat(timespec="seconds"), "naechte": naechte,
               "r_roh": round(r_roh, 3), "gebuehr_r": round(gebuehr_r, 3), "r": round(r_roh - gebuehr_r, 3),
               "pnl_waehrung": round(pnl, 2), "pnl_eur": round(pnl / rate, 2) if rate else None,
               **({"wieder_seit": tr["wieder_seit"]} if tr.get("wieder_seit") else {}), **mehr}
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
            "id": f"{self.epic} {plan['tag']}", "markt": self.sym, "epic": self.epic, "richtung": d, "tag": plan["tag"],
            "dealId": str(p.get("dealId")), "size": plan["size"], "entry": float(level),
            "stop": _num(p.get("stopLevel")) or plan["stop"], "dist": plan["dist"], "bid_ein": plan["bid"],
            "wahrscheinlichkeit": plan["wahrscheinlichkeit"], "opened_utc": opened_utc, "spaet_min": plan.get("spaet_min"),
            "nach_18_min": plan.get("nach_18_min"), "bis_utc": plan["bis_utc"], "satz_nacht": plan["satz_nacht"],
            "lot": plan["lot"], "eur_rate": plan["eur_rate"]}
        self.ev(SEITE[d] + " eröffnet", **{k: self.mst["trade"][k] for k in ("id", "dealId", "size", "entry", "stop",
                                                                            "dist", "wahrscheinlichkeit", "spaet_min")})

    def wieder_fuehren(self, hier: list[dict], gebucht: list[dict]) -> None:
        """Eine gebuchte Position dieses Markts, die beim Broker noch offen liegt, war nie zu. So ging es am 27.11.2026
        mit US500: Capital.com bestätigte den Zeitausstieg mit dem Kurs 0,24, die Position blieb offen, der Bot buchte
        -19,69 R und hielt sie danach für fremd. Er führt sie wieder als seinen Trade und nimmt die falsche Buchung
        zurück. Sie kommt aus trades.jsonl nach storniert.jsonl (stornieren). Ist der Ausstieg fällig, schließt fuehren
        die Position im selben Lauf, sobald der Markt offen ist. Nur Deal-IDs, die der Bot selbst gebucht hat, nie eine
        fremde Position."""
        if self.mst.get("trade") or not self.cfg:
            return
        offen = {str(x["position"].get("dealId")): x["position"] for x in hier}
        storniert = {(s.get("dealId"), s.get("closed_utc")) for s in self.st.get("storniert") or []}
        for t in reversed(gebucht):
            did, zu = str(t.get("dealId")), t.get("closed_utc")
            if (t.get("markt") != self.sym or did not in offen or zu is None or (did, zu) in storniert
                    or self.now - _zeit(zu, self.now) > NACHPRUEFEN):
                continue
            d, p = int(t["richtung"]), offen[did]
            satz = self.cfg["kosten"]["nacht_pro_jahr"]["index"]["long" if d > 0 else "short"]
            self.mst["trade"] = {
                **{k: t.get(k) for k in ("id", "markt", "epic", "richtung", "tag", "dealId", "size", "entry", "dist",
                                         "wahrscheinlichkeit", "opened_utc", "spaet_min", "nach_18_min")},
                "stop": _num(p.get("stopLevel")) or t.get("stop"), "bid_ein": None,
                "bis_utc": str(ausstieg(pd.Timestamp(t["tag"]), self.cfg)), "satz_nacht": float(satz),
                "lot": self.q.lot or 1.0, "eur_rate": self.q.eur_rate, "wieder_seit": self.stamp}
            self.st["summe_r"] = round(float(self.st["summe_r"]) - float(t.get("r") or 0), 3)
            self.st["trades"] = int(self.st["trades"]) - 1
            self.st.setdefault("storniert", []).append(
                {"dealId": did, "id": t.get("id"), "closed_utc": zu, "exit": t.get("exit"), "r": t.get("r"),
                 "pnl_eur": t.get("pnl_eur"), "zeit": self.stamp})
            self.ev("Trade wieder geführt", trade=t.get("id"), dealId=did, zurueck_r=t.get("r"),
                    zurueck_eur=t.get("pnl_eur"), falscher_kurs=t.get("exit"))
            return

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
        """Einmal je Handelstag und Markt, im Einstieg des Tests (ab 18:00 New York am Vorabend): Sagt das Modell Kauf
        oder Verkauf, und darf der Bot es nehmen?"""
        if self.cfg is None:
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
        if self.gew is None:
            self.warte("Gewichte des Modells nicht lesbar (Prüfsumme passt nicht)")
            return
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
        f = self.fremd()
        if "fehler" in f:
            if letzte_chance and self.send:
                return fertig("VIX oder Renditen nicht lesbar, kein Einstieg: " + f["fehler"], grund="fremd_fehlt")
            self.warte("VIX oder Renditen nicht lesbar")
            return
        stand = fremd_stand(f["reihen"], tag)
        alt = [n for n, s in stand.items() if not s["frisch"]]
        if alt:                         # mit einem Tag älteren Werten wäre es ein anderes Signal als im Test: auslassen
            text = "noch nicht veröffentlicht: " + ", ".join(f"{n} vom {stand[n]['erwartet']}" for n in alt)
            if letzte_chance and self.send:
                return fertig(text + ", kein Einstieg", grund="fremd_alt", fremd=stand)
            self.warte(text)
            return
        stunden = self.kerzen(self.now - pd.Timedelta(days=TAGE_KERZEN))
        if stunden is None:
            return
        sig = signal(self.sym, stunden, self.now, self.q.bid, self.cfg, self.gew, fred=self.ordner)
        sig["fremd"] = stand
        self.blick.setdefault(self.sym, {})["signal"] = {k: v for k, v in sig.items() if k != "merkmale"}
        if sig["warten"]:
            if letzte_chance and self.send:
                return fertig(sig["ergebnis"], grund="kerzen")
            self.warte(sig["ergebnis"])
            return
        kurz_info = {k: sig.get(k) for k in ("richtung", "wahrscheinlichkeit", "dist", "atr")}
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
        abstand = abs(q.offer - stop) if d > 0 else abs(stop - q.bid)
        if q.min_dist and abstand < q.min_dist:
            gruende.append("Stop näher als der Mindestabstand des Brokers")
        info = {"seite": SEITE[d], "tag": str(tag.date()), "dist": round(dist, 4), "stop": stop, "spaet_min": spaet,
                "nach_18_min": kurz_info.get("nach_18_min"),
                "bid": q.bid, "wahrscheinlichkeit": sig["wahrscheinlichkeit"],
                "margin_eur": None if marge is None else round(marge, 2)}
        if gruende:
            self.ev("Einstieg ausgelassen", **info, gruende=gruende)
            return fertig("Signal, aber kein Einstieg: " + "; ".join(gruende), **kurz_info)
        if not self.send:
            self.ev("würde " + ("kaufen" if d > 0 else "verkaufen"), **info, size=size)
            return
        fertig(f"{SEITE[d]} gesendet", **kurz_info)        # vor der Order: nie eine zweite Order für denselben Tag
        vorher = {str(x["position"].get("dealId")) for x in eigene + fremde}
        satz = self.cfg["kosten"]["nacht_pro_jahr"]["index"]["long" if d > 0 else "short"]
        plan = {"tag": str(tag.date()), "richtung": d, "size": size, "dist": round(dist, 6), "stop": stop, "bid": q.bid,
                "spaet_min": spaet, "nach_18_min": kurz_info.get("nach_18_min"), "bis_utc": sig["bis_utc"],
                "wahrscheinlichkeit": sig["wahrscheinlichkeit"],
                "satz_nacht": float(satz), "lot": q.lot or 1.0, "eur_rate": q.eur_rate}
        body = {"epic": self.epic, "direction": "BUY" if d > 0 else "SELL", "size": size, "guaranteedStop": False,
                "stopLevel": stop}
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


def run(client, state: dict, now: datetime, send_orders: bool = True,
        fremd_get=None, gebucht: list[dict] | None = None) -> tuple[dict, list[dict], list[dict], dict]:
    """Ein Lauf. Rückgabe: neuer Stand, Ereignisse, fertige Trades, Blick (für das Cockpit). `gebucht` sind die Zeilen
    aus trades.jsonl (für wieder_fuehren)."""
    from suche.demo_bots import eur_rate, quote_from_market

    with tempfile.TemporaryDirectory() as tmp:
        lauf = Lauf(client, state, now, send_orders, cfg=lade_cfg(pruefen=False), gew=lade_gewichte(pruefen=True),
                    fremd_get=fremd_get, ordner=Path(tmp))
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
                lauf.wieder_fuehren(hier, gebucht or [])
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
    naechster = None
    if lauf.cfg:                                           # der nächste Abend vor einem Handelstag Montag bis Freitag
        while naechster is None or naechster < lauf.now or tag.weekday() >= 5:
            if naechster is not None:
                tag += pd.Timedelta(days=1)
            naechster = einstieg_ab(tag, lauf.cfg)
    return {"naechster_einstieg_utc": None if naechster is None else str(naechster),
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
            teile.append(f"{name}: {SEITE[tr['richtung']]} offen ab {tr['entry']}, Stop {tr['stop']}, Ausstieg vor "
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
    offen = [{k: m["trade"].get(k) for k in ("id", "markt", "epic", "richtung", "entry", "stop", "size", "dist",
                                              "wahrscheinlichkeit", "opened_utc", "bis_utc")}
             for m in (st.get("maerkte") or {}).values() if m.get("trade")]
    return {"bot": BOT_ID, "name": NAME, "konto": KONTO_NAME, "stand": st.get("stand"), "start": st.get("start"),
            "pausiert": st.get("pausiert"), "status": status(st), "regel": REGEL, "backtest": TEST,
            "vorab": "suche/VORAB_modell_indizes_bot.yaml", "vorab_ok": vorab_ok(),
            "maerkte": {sym: NAMEN.get(sym, sym) for sym in MAERKTE}, "offen": offen,
            "ausgelassen": {sym: m.get("ausgelassen") or {} for sym, m in (st.get("maerkte") or {}).items()},
            "zusammenfassung": bewertung(alle_trades), "letzte_trades": alle_trades[-10:], "blick": blick}


def _ohne_zeit(st: dict) -> dict:
    return {k: v for k, v in (st or {}).items() if k != "stand"}


def stornieren(st: dict, jdir: Path) -> int:
    """Falsche Buchungen, die wieder_fuehren zurückgenommen hat, kommen aus trades.jsonl nach storniert.jsonl. Gesucht
    wird nach Deal-ID und Schlusszeit, so bleibt die spätere richtige Buchung derselben Position stehen. Nichts geht
    verloren, jede Zeile steht danach in storniert.jsonl mit Zeit und Grund. Rückgabe: Zahl der Zeilen."""
    weg = {(s.get("dealId"), s.get("closed_utc")): s for s in st.get("storniert") or []}
    pfad = jdir / "trades.jsonl"
    if not weg or not pfad.exists():
        return 0
    bleiben, raus = [], []
    for line in pfad.read_text(encoding="utf-8").splitlines():
        try:
            t = json.loads(line)
        except ValueError:
            bleiben.append(line)
            continue
        s = weg.get((t.get("dealId"), t.get("closed_utc")))
        if s is None:
            bleiben.append(line)
        else:
            raus.append({**t, "storniert": s["zeit"],
                         "warum": "Position lag noch offen, Schluss ohne Beleg gebucht (bis 28.11.2026)"})
    if raus:
        with open(jdir / "storniert.jsonl", "a", encoding="utf-8") as fh:
            fh.writelines(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in raus)
        pfad.write_text("".join(line + "\n" for line in bleiben), encoding="utf-8")
    return len(raus)


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
    stornieren(st, jdir)
    alle = sb._lies_jsonl(jdir / "trades.jsonl")
    cockpit_pfad.write_text(json.dumps(cockpit(st, alle, blick), ensure_ascii=False, indent=1, default=str) + "\n",
                            encoding="utf-8")
    return True


ANMELDEN_WARTEN = (2.0, 5.0)           # Sekunden vor dem zweiten und dritten Login nach "Rate-Limit"


def anmelden(client, warten=ANMELDEN_WARTEN, schlafen=None) -> None:
    """Login bei Capital.com. Capital.com nimmt je API-Schlüssel nur wenige Logins kurz hintereinander an. Der
    5-Minuten-Lauf und die anderen Bot-Schritte melden sich mit demselben Schlüssel an, darum kam am 20.11.2026 13:01 UTC
    beim 4-Std.-Ausbruch "Rate-Limit erreicht für /session". Ein Login ändert nichts beim Broker, darum versucht es der
    Bot dann nach kurzer Pause noch zweimal. Orders werden nie wiederholt."""
    import time
    from gold.bot.capital import CapitalError
    for pause in (*warten, None):
        try:
            client.login()
            return
        except CapitalError as err:
            if pause is None or "Rate-Limit" not in str(err):
                raise
            print(f"Login: {err}, neuer Versuch in {pause:.0f} s")
            (schlafen or time.sleep)(pause)


def main(argv: list[str]) -> int:
    from gold.bot.capital import CapitalClient
    from gold.bot.runner import CRED_KEYS, clean_credentials

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="nur rechnen, keine Order")
    args = ap.parse_args(argv)
    creds = clean_credentials({k: os.environ.get(k, "") for k in CRED_KEYS})
    if not all(creds):
        print("Keine Capital.com-Zugangsdaten, Vorhersage-Modell übersprungen")
        return 0
    path = JDIR / "state.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    client = CapitalClient(*creds, environment="demo")
    anmelden(client)
    try:
        st, log, fertige, blick = run(client, state, datetime.now(timezone.utc), send_orders=not args.dry_run,
                                      gebucht=sb._lies_jsonl(JDIR / "trades.jsonl"))
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
