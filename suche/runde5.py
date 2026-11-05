"""Strategie-Suche Runde 5: Swing-Strategien auf Tageskerzen, einzeln und kombiniert (suche/VORAB_runde5.yaml).

Kirons Wunsch (04.11.2026): große Recherche zu Scalping, Daytrading und Swing, die Ideen logisch verbinden, eigene
Strategien bauen und ehrlich testen; Gewinnfaktor über 1, am besten 1,2 bis 1,5 und mehr. Alle bisherigen Runden waren
intraday und ohne Vorteil; Swing auf Tageskerzen ist neu.

Daten: HistData-Stundenkerzen (Bid) von 41 Märkten (suche/tag_daten.py), Indizes ab 2010, Gold/Silber ab 2009, Devisen ab
2000/2002. Je Markt ein fester Entscheidungszeitpunkt T in einer liquiden Stunde (US-Indizes 15:00 New York, Europa,
Devisen, Rohstoffe 16:00 London, Asien 14:00 Ortszeit). Eine Tageskerze = die 24 Stunden bis T. Signale werden zum
Schluss dieser Kerze gerechnet und sofort zum Kurs bei T ausgeführt (ein Bot im 15-Minuten-Takt kann das). Kauf zum Ask
(Bid + echter Capital.com-Spread bei T), Verkauf zum Bid. Stops werden auf den Stundenkerzen geprüft. Übernachtgebühr
je Nacht (vorab festgelegte Sätze), auch für Short.

Gemessen wird jeder Trade in Einheiten der Tagesschwankung beim Einstieg (ATR 20), damit alle Märkte gleich viel zählen
(so würde ein Bot die Größe wählen: gleiches Risiko je Trade). Gewinnfaktor = Summe der Gewinne / Summe der Verluste.

    python -m suche.runde5 --festlegen "Grund"           # Prüfsumme der VORAB ins Journal, BEVOR gerechnet wird
    python -m suche.runde5 <h1_ordner> <capital_15min_ordner> <out_dir>
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import zlib
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

import numpy as np
import pandas as pd
import yaml

from suche.runde1 import journal_add, journal_lines, last_value
from suche.runde3 import read_capital

HERE = pathlib.Path(__file__).resolve().parent
VORAB = HERE / "VORAB_runde5.yaml"
KEY = "VORAB_runde5 sha256 "

# HistData-Kürzel -> Capital.com-Kürzel (für den Spread), Klasse, Zeitzone und Stunde des Entscheidungszeitpunkts
MAERKTE = {
    "SPXUSD": ("US500", "index_us", "America/New_York", 15), "NSXUSD": ("US100", "index_us", "America/New_York", 15),
    "GRXEUR": ("DE40", "index_eu", "Europe/London", 16), "UKXGBP": ("UK100", "index_eu", "Europe/London", 16),
    "FRXEUR": ("FR40", "index_eu", "Europe/London", 16), "ETXEUR": ("EU50", "index_eu", "Europe/London", 16),
    "JPXJPY": ("J225", "index_asien", "Asia/Tokyo", 14), "HKXHKD": ("HK50", "index_asien", "Asia/Hong_Kong", 14),
    "AUXAUD": ("AU200", "index_asien", "Australia/Sydney", 14),
    "XAUUSD": ("GOLD", "metall", "Europe/London", 16), "XAGUSD": ("SILVER", "metall", "Europe/London", 16),
    "WTIUSD": ("OIL_CRUDE", "energie", "Europe/London", 16), "BCOUSD": ("OIL_BRENT", "energie", "Europe/London", 16),
}
for _fx in ("EURUSD GBPUSD USDJPY AUDUSD USDCAD USDCHF NZDUSD EURGBP EURJPY GBPJPY EURCHF AUDJPY CADJPY CHFJPY NZDJPY "
            "EURAUD EURCAD EURNZD GBPAUD GBPCAD GBPCHF GBPNZD AUDCAD AUDCHF AUDNZD CADCHF NZDCAD NZDCHF").split():
    MAERKTE[_fx] = (_fx, "fx", "Europe/London", 16)
INDEX = {"index_us", "index_eu", "index_asien"}
# Beginn der Kassa-Sitzung (volle Ortsstunde) für die Sitzungskerze der Indizes (IBS rechnet auf der Kassa-Sitzung bis T)
SITZUNG_AB = {"America/New_York": 9, "Europe/London": 8, "Asia/Tokyo": 9, "Asia/Hong_Kong": 9, "Australia/Sydney": 10}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_vorab() -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("VORAB_runde5.yaml stimmt nicht mit der Prüfsumme im Journal überein. Erst festlegen.")
    return yaml.safe_load(text)["runde_5"]


# --------------------------------------------------------------------------------------------------------------------
# Tageskerzen aus Stundenkerzen

@dataclass
class Tage:
    sym: str
    klasse: str
    datum: np.ndarray        # datetime64[D], Handelstag
    t: np.ndarray            # datetime64[ns] UTC, Entscheidungszeitpunkt (Ende der letzten Stunde des Tages)
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    sh: np.ndarray           # Hoch/Tief der Kassa-Sitzung bis T (nur Indizes; sonst wie h/l)
    sl: np.ndarray
    i0: np.ndarray           # erste Stundenkerze des Tages
    i1: np.ndarray           # letzte Stundenkerze des Tages (inklusive)
    ho: np.ndarray           # Stundenkerzen (Bid)
    hh: np.ndarray
    hl: np.ndarray
    hsp: np.ndarray          # Spread je Stundenkerze (für die Ask-Seite der Stops)
    ht: np.ndarray           # Beginn der Stundenkerze, UTC
    sp: float                # Spread beim Entscheidungszeitpunkt
    fin_long: float          # Übernachtgebühr je Nacht, Anteil vom Kurs
    fin_short: float


def lade_h1(path: pathlib.Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df.dropna(subset=["open", "high", "low", "close"])


def tageslabel(index: pd.DatetimeIndex, zone: str, stunde: int) -> np.ndarray:
    """Handelstag je Stundenkerze: die 24 Stunden bis `stunde` Uhr Ortszeit. Samstag/Sonntag zählen zum Montag."""
    ende = (index + pd.Timedelta(hours=1)).tz_localize("UTC").tz_convert(zone).tz_localize(None)
    d = (ende - pd.Timedelta(hours=stunde, microseconds=1)).values.astype("datetime64[D]") + np.timedelta64(1, "D")
    wd = (d.astype(np.int64) + 3) % 7                    # Montag = 0
    d = d + np.where(wd == 5, 2, np.where(wd == 6, 1, 0)).astype("timedelta64[D]")
    return d


def spread_profil(capital_csv: pathlib.Path | None, zone: str, stunde: int, ersatz: float) -> tuple[float, dict]:
    """Spread bei T (Median über alle Tage) und je Ortsstunde; ohne Capital.com-Datei der Ersatzwert."""
    if capital_csv is None or not capital_csv.exists():
        return ersatz, {}
    _, sp = read_capital(capital_csv)
    lok = sp.index.tz_localize("UTC").tz_convert(zone)
    s = pd.Series(sp.to_numpy(), index=np.asarray(lok.hour * 60 + lok.minute))
    bei_t = s[s.index == stunde * 60]
    je_stunde = pd.Series(sp.to_numpy(), index=np.asarray(lok.hour)).groupby(level=0).median().to_dict()
    return float(bei_t.median()) if len(bei_t) else float(s.median()), je_stunde


def baue_tage(sym: str, h1: pd.DataFrame, capital_csv: pathlib.Path | None, kosten: dict, min_stunden: int = 4) -> Tage:
    epic, klasse, zone, stunde = MAERKTE[sym]
    lab = tageslabel(h1.index, zone, stunde)
    grenzen = np.flatnonzero(lab[1:] != lab[:-1]) + 1
    i0 = np.r_[0, grenzen]
    i1 = np.r_[grenzen - 1, len(lab) - 1]
    n = i1 - i0 + 1
    keep = n >= min_stunden
    i0, i1 = i0[keep], i1[keep]
    ho, hh, hl, hc = (h1[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    h_max = np.maximum.reduceat(hh, np.r_[0, grenzen])[keep]
    l_min = np.minimum.reduceat(hl, np.r_[0, grenzen])[keep]
    ht = h1.index.values
    lok_h = h1.index.tz_localize("UTC").tz_convert(zone).hour
    if klasse in INDEX:
        drin = np.asarray(lok_h >= SITZUNG_AB[zone])
        s_max = np.maximum.reduceat(np.where(drin, hh, -np.inf), np.r_[0, grenzen])[keep]
        s_min = np.minimum.reduceat(np.where(drin, hl, np.inf), np.r_[0, grenzen])[keep]
        sh, sl_ = np.where(np.isfinite(s_max), s_max, np.nan), np.where(np.isfinite(s_min), s_min, np.nan)
    else:
        sh, sl_ = h_max, l_min
    sp_t, je_stunde = spread_profil(capital_csv, zone, stunde, kosten["spread_ersatz"].get(klasse, 0.0) * hc[-1])
    hsp = np.array([je_stunde.get(int(x), sp_t) for x in lok_h], float) if je_stunde else np.full(len(h1), sp_t)
    fin = kosten["uebernacht"][("index" if klasse in INDEX else klasse)]
    return Tage(sym, klasse, lab[i0], ht[i1] + np.timedelta64(1, "h"), ho[i0], h_max, l_min, hc[i1], sh, sl_, i0, i1,
                ho, hh, hl, hsp, ht, sp_t, fin["long"] / 100 / 365, fin["short"] / 100 / 365)


# --------------------------------------------------------------------------------------------------------------------
# Kennzahlen auf Tageskerzen

def sma(x: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(x).rolling(n).mean().to_numpy()


def wilder(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    ok = np.flatnonzero(~np.isnan(x))
    if len(ok) < n:
        return out
    s = ok[0]
    out[s + n - 1] = np.nanmean(x[s:s + n])
    for i in range(s + n, len(x)):
        out[i] = (out[i - 1] * (n - 1) + x[i]) / n
    return out


def rsi(c: np.ndarray, n: int) -> np.ndarray:
    d = np.diff(c, prepend=np.nan)
    up = wilder(np.where(np.isnan(d), np.nan, np.clip(d, 0, None)), n)
    dn = wilder(np.where(np.isnan(d), np.nan, np.clip(-d, 0, None)), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(dn == 0, 100.0, 100 - 100 / (1 + up / dn))


def atr(T: Tage, n: int) -> np.ndarray:
    vc = np.r_[np.nan, T.c[:-1]]
    with np.errstate(invalid="ignore"):
        tr = np.nanmax(np.vstack([T.h - T.l, np.abs(T.h - vc), np.abs(T.l - vc)]), axis=0)
    return wilder(tr, n)


def vorher_max(x: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(x).rolling(n).max().shift(1).to_numpy()


def vorher_min(x: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(x).rolling(n).min().shift(1).to_numpy()


def monatsende(datum: np.ndarray) -> np.ndarray:
    m = datum.astype("datetime64[M]")
    return np.r_[m[1:] != m[:-1], False]


def tag_im_monat(datum: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Handelstag im Monat (1 = erster) und wie viele Handelstage im Monat danach noch kommen (aus dem Kalender)."""
    m = datum.astype("datetime64[M]").astype(np.int64)
    s = pd.Series(np.arange(len(m)), index=m)
    erster = s.groupby(level=0).transform("min").to_numpy()
    anzahl = s.groupby(level=0).transform("count").to_numpy()
    nr = np.arange(len(m)) - erster + 1
    return nr, anzahl - nr


# --------------------------------------------------------------------------------------------------------------------
# Signale je Strategie: Einstieg/Ausstieg Long/Short zum Tagesschluss (Regeln in VORAB_runde5.yaml)

@dataclass
class Signal:
    el: np.ndarray
    es: np.ndarray
    xl: np.ndarray
    xs: np.ndarray
    stop_atr: float | None = None          # fester Stop im Abstand x ATR(20) vom Einstieg
    trail_atr: float | None = None         # nachgezogener Stop: x ATR(20, beim Einstieg) vom besten Schluss seit Einstieg
    max_tage: int | None = None            # Zeitstopp in Handelstagen


def _leer(n: int) -> np.ndarray:
    return np.zeros(n, bool)


def _gt(a, b):
    with np.errstate(invalid="ignore"):
        return a > b


def _lt(a, b):
    with np.errstate(invalid="ignore"):
        return a < b


def wochenende(datum: np.ndarray) -> np.ndarray:
    """Letzter Handelstag jeder Woche (Montag bis Freitag)."""
    w = (datum.astype(np.int64) + 3) // 7
    return np.r_[w[1:] != w[:-1], False]


def rendite(c: np.ndarray, n: int) -> np.ndarray:
    return c / np.r_[np.full(n, np.nan), c[:-n]] - 1


def ewma(x: np.ndarray, span: int) -> np.ndarray:
    return pd.Series(x).ewm(span=span, adjust=False).mean().to_numpy()


def sig_tsmom(T: Tage, p: dict, ctx: dict) -> Signal:
    """Zeitreihen-Momentum (Moskowitz/Ooi/Pedersen): am Monatsende in Richtung der Rendite der letzten `tage` Handelstage."""
    me = monatsende(T.datum)
    r = rendite(T.c, int(p["tage"]))
    up, dn = me & _gt(r, 0), me & _lt(r, 0)
    return Signal(up, dn, dn, up)


def sig_abstimmung(T: Tage, p: dict, ctx: dict) -> Signal:
    """AQR-Abstimmung über 1, 3 und 12 Monate, wöchentlich: Einstieg wenn alle drei gleich zeigen, raus bei Mehrheit dagegen."""
    we = wochenende(T.datum)
    v = sum(np.sign(np.nan_to_num(rendite(T.c, n))) for n in (21, 63, 252))
    ok = ~np.isnan(rendite(T.c, 252))
    return Signal(we & ok & (v == 3), we & ok & (v == -3), we & ok & (v <= -1), we & ok & (v >= 1))


def sig_ewmac(T: Tage, p: dict, ctx: dict) -> Signal:
    """Carvers EWMAC 16/64, 32/128, 64/256 mit seinen veröffentlichten Skalaren, gekappt bei +-20, gemittelt.
    Diskret: am Wochenende Long bei Summe > 0, Short bei < 0 (immer im Markt, Wechsel = neuer Trade)."""
    sig_p = pd.Series(np.diff(T.c, prepend=np.nan)).ewm(span=35, adjust=False).std().to_numpy()
    teile = []
    for f, skalar in ((16, 4.1), (32, 2.79), (64, 1.91)):
        with np.errstate(invalid="ignore", divide="ignore"):
            roh = (ewma(T.c, f) - ewma(T.c, 4 * f)) / sig_p
        teile.append(np.clip(roh * skalar, -20, 20))
    kombi = np.mean(teile, axis=0)
    we = wochenende(T.datum) & ~np.isnan(kombi)
    up, dn = we & _gt(kombi, 0), we & _lt(kombi, 0)
    return Signal(up, dn, dn, up)


def sig_donchian_trend(T: Tage, p: dict, ctx: dict) -> Signal:
    """Ausbruch über den höchsten Schluss der letzten `einstieg` Tage, nur wenn EWMA 64 über EWMA 256 (Short gespiegelt).
    Raus nur über den nachgezogenen Stop (oder das Gegensignal)."""
    hi, lo = vorher_max(T.c, int(p["einstieg"])), vorher_min(T.c, int(p["einstieg"]))
    f, s = ewma(T.c, 64), ewma(T.c, 256)
    n = len(T.c)
    return Signal(_gt(T.c, hi) & _gt(f, s), _lt(T.c, lo) & _lt(f, s), _leer(n), _leer(n), trail_atr=float(p["trail_atr"]))


def sig_rsi2(T: Tage, p: dict, ctx: dict) -> Signal:
    """Connors RSI(2): über dem 200-Tage-Schnitt kaufen, wenn RSI(2) unter `unter` schließt; raus über dem 5-Tage-Schnitt."""
    r, trend, kurz = rsi(T.c, 2), sma(T.c, int(p["trend"])), sma(T.c, 5)
    n = len(T.c)
    return Signal(_gt(T.c, trend) & _lt(r, p["unter"]), _leer(n), _gt(T.c, kurz), _leer(n))


def sig_ibs(T: Tage, p: dict, ctx: dict) -> Signal:
    """IBS auf der Kassa-Sitzung bis T: kaufen bei IBS unter `unter`, raus wenn der Schluss über dem Vortageshoch der
    Sitzung liegt, spätestens nach `max_tage`."""
    with np.errstate(invalid="ignore", divide="ignore"):
        ibs = (T.c - T.sl) / (T.sh - T.sl)
    n = len(T.c)
    return Signal(_lt(ibs, p["unter"]), _leer(n), _gt(T.c, np.r_[np.nan, T.sh[:-1]]), _leer(n),
                  max_tage=int(p["max_tage"]))


def sig_double7(T: Tage, p: dict, ctx: dict) -> Signal:
    """Connors Double 7: über dem 200-Tage-Schnitt kaufen, wenn der Schluss der tiefste der letzten `tage` Tage ist;
    raus, wenn er der höchste der letzten `tage` Tage ist."""
    k = int(p["tage"])
    tief = pd.Series(T.c).rolling(k).min().to_numpy()
    hoch = pd.Series(T.c).rolling(k).max().to_numpy()
    n = len(T.c)
    return Signal(_gt(T.c, sma(T.c, 200)) & (T.c <= tief), _leer(n), T.c >= hoch, _leer(n))


def sig_monatswechsel(T: Tage, p: dict, ctx: dict) -> Signal:
    """Monatswechsel: kaufen, wenn im Monat danach noch `einstieg_rest` Handelstage kommen; raus am `ausstieg_tag`-ten
    Handelstag des neuen Monats."""
    nr, rest = tag_im_monat(T.datum)
    n = len(T.c)
    return Signal(rest == int(p["einstieg_rest"]), _leer(n), nr == int(p["ausstieg_tag"]), _leer(n))


def _ruecksetzer(T: Tage, p: dict, long_ok: np.ndarray, short_ok: np.ndarray) -> Signal:
    r, kurz = rsi(T.c, 2), sma(T.c, 5)
    u = float(p["unter"])
    return Signal(long_ok & _lt(r, u), short_ok & _gt(r, 100 - u), _gt(T.c, kurz), _lt(T.c, kurz),
                  stop_atr=float(p["stop_atr"]), max_tage=int(p["max_tage"]))


def sig_trend_ruecksetzer(T: Tage, p: dict, ctx: dict) -> Signal:
    """Kombination Swing + Kurzfrist (S2): Richtung aus dem 200-Tage-Schnitt, Einstieg auf RSI(2) unter `unter` (Long)
    bzw. über 100 - `unter` (Short). Raus über/unter dem 5-Tage-Schnitt, spätestens nach `max_tage`, Notstop `stop_atr`."""
    tr = sma(T.c, int(p["trend"]))
    return _ruecksetzer(T, p, _gt(T.c, tr), _lt(T.c, tr))


def sig_vola_ruecksetzer(T: Tage, p: dict, ctx: dict) -> Signal:
    """Gegenmodell S3 (Nagel 2012): Rücksetzer wie S2, aber ohne Trendfilter und nur, wenn die Schwankung
    (ATR 20 / Kurs) mindestens ihr Median der letzten 252 Tage ist."""
    v = atr(T, 20) / T.c
    med = pd.Series(v).rolling(252).median().to_numpy()
    hoch = ~np.isnan(med) & (v >= med)
    return _ruecksetzer(T, p, hoch, hoch)


def sig_index_momentum(T: Tage, p: dict, ctx: dict) -> Signal:
    """Reddit (r/algotrading, "Leverage Dual Momentum", hier ohne Hebel): am Monatsende Long, wenn
    0,7 x Rendite 126 Tage + 0,3 x Rendite 252 Tage über 0 liegt und die Rendite über 63 Tage über 0; sonst raus."""
    me = monatsende(T.datum)
    score = 0.7 * rendite(T.c, 126) + 0.3 * rendite(T.c, 252)
    r3 = rendite(T.c, 63)
    rein = _gt(score, 0) & _gt(r3, 0)
    ok = ~np.isnan(score) & ~np.isnan(r3)
    n = len(T.c)
    return Signal(me & rein, _leer(n), me & ok & ~rein, _leer(n))


SIGNALE = {"index_momentum": sig_index_momentum, "tsmom": sig_tsmom, "abstimmung": sig_abstimmung, "ewmac": sig_ewmac, "donchian_trend": sig_donchian_trend,
           "rsi2": sig_rsi2, "ibs": sig_ibs, "double7": sig_double7, "monatswechsel": sig_monatswechsel,
           "trend_ruecksetzer": sig_trend_ruecksetzer, "vola_ruecksetzer": sig_vola_ruecksetzer}


# --------------------------------------------------------------------------------------------------------------------
# Simulation

def naechte(t_ein: np.datetime64, t_aus: np.datetime64) -> int:
    """Wie oft 22:00 UTC (Rollover) zwischen Einstieg und Ausstieg liegt; Wochenende zählt wie beim Broker dreifach."""
    a = (np.datetime64(t_ein) - np.timedelta64(22, "h")).astype("datetime64[D]")
    b = (np.datetime64(t_aus) - np.timedelta64(22, "h")).astype("datetime64[D]")
    return int((b - a).astype(int))


def stop_pruefen(T: Tage, t: int, d: int, stop: float, sp_mult: float) -> tuple[float, np.datetime64] | None:
    """Stop auf den Stundenkerzen des Tages t. Long: Bid-Tief; Short: Ask-Hoch. Lücke: Füllung zur Eröffnung."""
    a, b = T.i0[t], T.i1[t] + 1
    if d > 0:
        k = np.flatnonzero(T.hl[a:b] <= stop)
        if len(k):
            k = a + k[0]
            return min(stop, T.ho[k]), T.ht[k] + np.timedelta64(1, "h")
        return None
    sp = T.hsp[a:b] * sp_mult
    k = np.flatnonzero(T.hh[a:b] + sp >= stop)
    if len(k):
        j = k[0]
        return max(stop, T.ho[a + j] + sp[j]), T.ht[a + j] + np.timedelta64(1, "h")
    return None


def trade(T: Tage, ti: int, d: int, aus_bid: float, t_aus, grund: str, te: int, a20: np.ndarray, sp_mult: float,
          fin_mult: float, aus_ask: bool) -> dict:
    sp = T.sp * sp_mult
    ein = T.c[ti] + (sp if d > 0 else 0.0)
    aus = aus_bid + (sp if (d < 0 and not aus_ask) else 0.0)
    nacht = naechte(T.t[ti], t_aus)
    fin = (T.fin_long if d > 0 else T.fin_short) * fin_mult * nacht * T.c[ti]
    pnl = (aus - ein) * d - fin
    return {"sym": T.sym, "klasse": T.klasse, "datum": str(T.datum[ti]), "ti": ti, "te": te, "d": d,
            "r": float(pnl / a20[ti]), "pct": float(pnl / ein * 100), "grund": grund, "tage": int(te - ti),
            "naechte": nacht}


def simuliere(T: Tage, s: Signal, start: int, sp_mult: float = 1.0, fin_mult: float = 1.0,
              mit_zwilling: bool = False) -> list[dict]:
    """Ein Trade je Markt gleichzeitig. Ablauf je Tag t: Stop auf den Stunden von t prüfen, dann zum Schluss von t
    Ausstieg (Signal, Gegensignal, Zeitstopp), dann Einstieg; ein nachgezogener Stop rückt zum Schluss nach."""
    a20 = atr(T, 20)
    n = len(T.c)
    out: list[dict] = []
    pos, ti, stop, abstand, best = 0, 0, None, 0.0, 0.0

    def schliessen(te: int, aus_bid: float, t_aus, grund: str, aus_ask: bool = False):
        tr = trade(T, ti, pos, aus_bid, t_aus, grund, te, a20, sp_mult, fin_mult, aus_ask)
        if mit_zwilling:
            tr["r_zwilling"] = zwilling(T, ti, -pos, te, s, a20, sp_mult, fin_mult)
        out.append(tr)

    for t in range(start, n):
        if pos != 0 and stop is not None and t > ti:
            hit = stop_pruefen(T, t, pos, stop, sp_mult)
            if hit is not None:
                schliessen(t, hit[0], hit[1], "stop", aus_ask=True)
                pos, stop = 0, None
        if pos != 0:
            raus = (pos > 0 and (s.xl[t] or s.es[t])) or (pos < 0 and (s.xs[t] or s.el[t]))
            if s.max_tage and t - ti >= s.max_tage:
                raus = True
            if raus or t == n - 1:
                schliessen(t, T.c[t], T.t[t], "signal" if raus else "datenende")
                pos, stop = 0, None
            elif s.trail_atr:
                best = max(best, T.c[t]) if pos > 0 else min(best, T.c[t])
                stop = best - pos * abstand
        if pos == 0 and t < n - 1 and not np.isnan(a20[t]) and a20[t] > 0:
            d = 1 if (s.el[t] and not s.xl[t]) else -1 if (s.es[t] and not s.xs[t]) else 0
            if d:
                pos, ti, best = d, t, T.c[t]
                abstand = (s.trail_atr or s.stop_atr or 0.0) * a20[t]
                stop = (T.c[t] - d * abstand) if (s.stop_atr or s.trail_atr) else None
    return out


def zwilling(T: Tage, ti: int, d: int, te: int, s: Signal, a20: np.ndarray, sp_mult: float, fin_mult: float) -> float:
    """Zufallsvergleich: gleicher Einstieg, Richtung umgedreht, gleicher (gespiegelter, auch nachgezogener) Stop,
    spätestens am Ausstiegstag des echten Trades raus."""
    abstand = (s.trail_atr or s.stop_atr or 0.0) * a20[ti]
    if abstand:
        best = T.c[ti]
        stop = T.c[ti] - d * abstand
        for t in range(ti + 1, te + 1):
            hit = stop_pruefen(T, t, d, stop, sp_mult)
            if hit is not None:
                return trade(T, ti, d, hit[0], hit[1], "stop", t, a20, sp_mult, fin_mult, True)["r"]
            if s.trail_atr:
                best = max(best, T.c[t]) if d > 0 else min(best, T.c[t])
                stop = best - d * abstand
    return trade(T, ti, d, T.c[te], T.t[te], "zeit", te, a20, sp_mult, fin_mult, False)["r"]


def zufall_long(T: Tage, trades: list[dict], von: int, bis: int, rng: np.random.Generator, n_laeufe: int,
                sp_mult: float = 1.0) -> np.ndarray:
    """Für reine Long-Strategien: gleiche Haltedauer, zufälliger Einstiegstag im selben Fenster und Markt (ohne Stop,
    wie die Strategien selbst). Rückgabe: Matrix Läufe x Trades in ATR-Einheiten."""
    a20 = atr(T, 20)
    L = np.array([tr["te"] - tr["ti"] for tr in trades], int)
    out = np.zeros((n_laeufe, len(trades)))
    if not len(trades):
        return out
    for j, l in enumerate(L):
        hi = max(von + 1, min(bis, len(T.c) - 1 - l))
        st = rng.integers(von, hi, n_laeufe)
        en = st + l
        sp = T.sp * sp_mult
        ein = T.c[st] + sp
        nacht = ((T.t[en] - T.t[st]).astype("timedelta64[h]").astype(np.int64) / 24).round()
        fin = T.fin_long * nacht * T.c[st]
        out[:, j] = (T.c[en] - ein - fin) / a20[st]
    return out


# --------------------------------------------------------------------------------------------------------------------
# Auswertung

def pf(r) -> float | None:
    r = np.asarray(r, float)
    if not len(r):
        return None
    loss = -r[r < 0].sum()
    return round(float(r[r > 0].sum() / loss), 3) if loss > 0 else 99.0


def pf_matrix(m: np.ndarray) -> np.ndarray:
    g = np.where(m > 0, m, 0).sum(1)
    v = -np.where(m < 0, m, 0).sum(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(v > 0, g / np.where(v > 0, v, 1), 99.0)


def kennzahlen(tr: list[dict]) -> dict:
    if not tr:
        return {"trades": 0, "pf": None}
    r = np.array([t["r"] for t in tr])
    pct = np.array([t["pct"] for t in tr])
    d = np.array([t["d"] for t in tr])
    return {"trades": int(len(r)), "pf": pf(r), "treffer_pct": round(float((r > 0).mean() * 100), 1),
            "summe_r": round(float(r.sum()), 1), "mittel_r": round(float(r.mean()), 3), "pf_pct": pf(pct),
            "long_pf": pf(r[d > 0]), "short_pf": pf(r[d < 0]), "haltedauer_median": float(np.median([t["tage"] for t in tr])),
            "t_wert": round(float(r.mean() / r.std(ddof=1) * np.sqrt(len(r))), 2) if len(r) > 2 and r.std() > 0 else None,
            "maerkte_im_plus_pct": round(100 * float(np.mean([sum(t["r"] for t in tr if t["sym"] == m) > 0
                                                              for m in {t["sym"] for t in tr}])), 1)}


def im_fenster(tr: list[dict], von: str, bis: str) -> list[dict]:
    return [t for t in tr if von <= t["datum"] <= bis]


def abdeckung(T: Tage, von: str, bis: str, min_anteil: float, start: int) -> bool:
    """Markt zählt in einem Fenster, wenn er es ab seinem eigenen Beginn (nach dem Vorlauf) bis zum Ende abdeckt:
    mindestens ein Jahr lang, Daten bis spätestens 31 Tage vor Fensterende, Werktage mit Kerze / alle Werktage >= min_anteil."""
    if start >= len(T.datum):
        return False
    a, b = max(np.datetime64(von), T.datum[start]), np.datetime64(bis)
    if b - a < np.timedelta64(365, "D") or T.datum[-1] < b - np.timedelta64(31, "D"):
        return False
    werktage = np.busday_count(a, b + np.timedelta64(1, "D"))
    drin = ((T.datum >= a) & (T.datum <= b)).sum()
    return bool(drin / werktage >= min_anteil)


def markt_job(args) -> dict:
    sym, h1_dir, cap_dir, cfg = args
    try:
        return _markt_job(sym, h1_dir, cap_dir, cfg)
    except Exception as err:          # noqa: BLE001  ein Markt stoppt nicht die Runde
        return {"sym": sym, "fehler": repr(err)}


def _markt_job(sym, h1_dir, cap_dir, cfg) -> dict:
    h1 = lade_h1(pathlib.Path(h1_dir) / f"{sym}_H1.csv.gz")
    epic = MAERKTE[sym][0]
    cap = pathlib.Path(cap_dir) / f"{epic}_MINUTE_15.csv.gz"
    T = baue_tage(sym, h1, cap if cap.exists() else None, cfg["kosten"])
    fen = cfg["fenster"]
    ctx: dict = {}
    start = int(np.searchsorted(T.datum, np.datetime64(T.datum[0]) + np.timedelta64(cfg["regel"]["vorlauf_tage"], "D")))
    deckt = {f: abdeckung(T, *fen[f], cfg["regel"]["min_abdeckung"], start) for f in ("auswahl", "pruefung", "siegel")}
    out = {"sym": sym, "klasse": T.klasse, "spread": T.sp, "tage": int(len(T.c)), "von": str(T.datum[0]),
           "bis": str(T.datum[-1]), "deckt": deckt, "strategien": {}}
    for name, st in cfg["strategien"].items():
        if T.klasse not in st["klassen"] or (st.get("nur") and sym not in st["nur"]):
            continue
        p = st.get("parameter", {})
        s = SIGNALE[st["logik"]](T, p, ctx)
        tr = simuliere(T, s, start, mit_zwilling=True)
        rob = simuliere(T, s, start, sp_mult=cfg["kosten"]["robust_faktor"], fin_mult=cfg["kosten"]["robust_faktor"])
        plateau = {}
        for key, werte in (st.get("plateau") or {}).items():
            for w in werte:
                q = dict(p, **{key: w})
                plateau[f"{key}={w}"] = simuliere(T, SIGNALE[st["logik"]](T, q, ctx), start)
        zl = {}
        if st.get("richtung") == "long":
            rng = np.random.default_rng(cfg["zufall"]["seed"] + zlib.crc32((sym + name).encode()) % 10_000)
            for f in ("auswahl", "pruefung"):
                w = im_fenster(tr, *fen[f])
                a = int(np.searchsorted(T.datum, np.datetime64(fen[f][0])))
                b = int(np.searchsorted(T.datum, np.datetime64(fen[f][1]), side="right")) - 1
                zl[f] = zufall_long(T, w, max(a, start), b, rng, cfg["zufall"]["laeufe"]).astype(np.float32)
            w = im_fenster(tr, *fen["siegel"])
            a = int(np.searchsorted(T.datum, np.datetime64(fen["siegel"][0])))
            zl["siegel"] = zufall_long(T, w, max(a, start), len(T.c) - 1, rng, cfg["zufall"]["laeufe"]).astype(np.float32)
        out["strategien"][name] = {"trades": tr, "robust": rob, "plateau": plateau, "zufall_long": zl}
    return out


def null_beide(r: np.ndarray, rz: np.ndarray, n: int, rng: np.random.Generator) -> np.ndarray:
    wahl = rng.random((n, len(r))) < 0.5
    return pf_matrix(np.where(wahl, r, rz))


def je_jahr(tr: list[dict]) -> dict:
    out = {}
    for t in tr:
        out.setdefault(t["datum"][:4], []).append(t["r"])
    return {y: {"trades": len(v), "pf": pf(v), "summe_r": round(float(np.sum(v)), 1)} for y, v in sorted(out.items())}


def bewerte(name: str, st: dict, jobs: list[dict], cfg: dict, rng: np.random.Generator) -> dict:
    fen, reg = cfg["fenster"], cfg["regel"]
    res: dict = {"logik": st["logik"], "klassen": st["klassen"], "richtung": st.get("richtung", "beide")}

    def sammle(f: str, feld: str = "trades") -> list[dict]:
        out = []
        for j in jobs:
            s = j.get("strategien", {}).get(name)
            if s and j["deckt"][f]:
                out += im_fenster(s[feld], *fen[f])
        return out

    def zufall(f: str, tr: list[dict]) -> float:
        echt = pf([t["r"] for t in tr]) or 0.0
        if not tr:
            return 0.0
        if st.get("richtung") == "long":
            mats = [j["strategien"][name]["zufall_long"][f] for j in jobs
                    if j.get("strategien", {}).get(name) and j["deckt"][f] and j["strategien"][name]["zufall_long"][f].shape[1]]
            null = pf_matrix(np.hstack(mats)) if mats else np.zeros(1)
        else:
            null = null_beide(np.array([t["r"] for t in tr]), np.array([t["r_zwilling"] for t in tr]),
                              cfg["zufall"]["laeufe"], rng)
        return round(float((null < echt).mean() * 100), 1)

    for f in ("auswahl", "pruefung"):
        tr = sammle(f)
        k = kennzahlen(tr)
        k["zufall_perzentil"] = zufall(f, tr)
        k["pf_robust"] = pf([t["r"] for t in sammle(f, "robust")])
        k["maerkte"] = len({t["sym"] for t in tr})
        k["je_klasse"] = {kl: kennzahlen([t for t in tr if t["klasse"] == kl]) for kl in sorted({t["klasse"] for t in tr})}
        k["je_jahr"] = je_jahr(tr)
        res[f] = k
    a, p_ = res["auswahl"], res["pruefung"]
    res["tests_auswahl"] = {"trades": a["trades"] >= reg["min_trades_auswahl"], "pf": (a["pf"] or 0) >= reg["min_pf_auswahl"],
                            "zufall": a["zufall_perzentil"] >= reg["min_zufall_perzentil"],
                            "robust": (a["pf_robust"] or 0) >= reg["min_pf_robust"]}
    res["tests_pruefung"] = {"trades": p_["trades"] >= reg["min_trades_pruefung"],
                             "pf": (p_["pf"] or 0) >= reg["min_pf_pruefung"]}
    plateau = {}
    keys = set()
    for j in jobs:
        keys |= set((j.get("strategien", {}).get(name) or {}).get("plateau", {}).keys())
    for key in sorted(keys):
        tr = []
        for j in jobs:
            s = j.get("strategien", {}).get(name)
            if s and j["deckt"]["auswahl"]:
                tr += im_fenster(s["plateau"].get(key, []), *fen["auswahl"])
        plateau[key] = pf([t["r"] for t in tr])
    res["plateau_auswahl"] = plateau
    res["tests_plateau"] = {"alle_nachbarn": all((v or 0) >= reg["min_pf_plateau"] for v in plateau.values())}
    res["finalist"] = all(res["tests_auswahl"].values()) and all(res["tests_pruefung"].values()) and \
        all(res["tests_plateau"].values())
    # bester einzelner Markt in der Auswahl (Kirons Regel "ein Markt je Konto"), nur zur Information
    best = None
    for j in jobs:
        s = j.get("strategien", {}).get(name)
        if not (s and j["deckt"]["auswahl"]):
            continue
        tr = im_fenster(s["trades"], *fen["auswahl"])
        if len(tr) >= reg["min_trades_markt"]:
            v = pf([t["r"] for t in tr]) or 0
            if best is None or v > best[1]:
                best = (j["sym"], v, len(tr), pf([t["r"] for t in im_fenster(s["trades"], *fen["pruefung"])]))
    res["bester_markt_auswahl"] = best
    if res["finalist"]:                       # Siegel nur für Finalisten öffnen
        tr = sammle("siegel")
        k = kennzahlen(tr)
        k["zufall_perzentil"] = zufall("siegel", tr)
        k["pf_robust"] = pf([t["r"] for t in sammle("siegel", "robust")])
        k["je_jahr"] = je_jahr(tr)
        k["je_klasse"] = {kl: kennzahlen([t for t in tr if t["klasse"] == kl]) for kl in sorted({t["klasse"] for t in tr})}
        res["siegel"] = k
        res["tests_siegel"] = {"trades": k["trades"] >= reg["min_trades_siegel"], "pf": (k["pf"] or 0) >= reg["min_pf_siegel"],
                               "robust": (k["pf_robust"] or 0) >= reg["min_pf_robust_siegel"]}
        res["bestanden"] = all(res["tests_siegel"].values())
    else:
        res["bestanden"] = False
    return res


def kombi(name: str, kd: dict, jobs: list[dict], cfg: dict, ergebnisse: dict) -> dict:
    """Vorab festgelegte Kombination mehrerer Strategien: alle ihre Trades zusammen (gleiches Risiko je Trade). Nur zur
    Information; das Siegel öffnet nur, wenn alle Teile Finalisten sind."""
    fen = cfg["fenster"]
    out = {"teile": kd["teile"]}
    alle_finalisten = all(ergebnisse.get(t, {}).get("finalist") for t in kd["teile"])
    out["siegel_offen"] = alle_finalisten
    for f in ("auswahl", "pruefung") + (("siegel",) if alle_finalisten else ()):
        tr = []
        for teil in kd["teile"]:
            for j in jobs:
                s = j.get("strategien", {}).get(teil)
                if s and j["deckt"][f]:
                    tr += im_fenster(s["trades"], *fen[f])
        k = kennzahlen(tr)
        k["je_jahr"] = je_jahr(tr)
        out[f] = k
    return out


def run(h1_dir: pathlib.Path, cap_dir: pathlib.Path, out: pathlib.Path) -> dict:
    cfg = check_vorab()
    out.mkdir(parents=True, exist_ok=True)
    syms = [s for s in cfg["maerkte"] if (h1_dir / f"{s}_H1.csv.gz").exists()]
    for s in syms:                                              # Siegel-Daten festhalten, bevor sie jemand ansieht
        h1 = lade_h1(h1_dir / f"{s}_H1.csv.gz")
        teil = h1.loc[cfg["fenster"]["siegel"][0]:]
        journal_add(f"Siegel-Runde5 {s} {len(teil)} Stunden sha256 {sha256_text(teil.round(6).to_csv())}")
    with ProcessPoolExecutor(max_workers=cfg.get("prozesse", 4)) as pool:
        jobs = list(pool.map(markt_job, [(s, str(h1_dir), str(cap_dir), cfg) for s in syms]))
    rng = np.random.default_rng(cfg["zufall"]["seed"])
    res = {"maerkte": {j["sym"]: {k: j.get(k) for k in ("klasse", "spread", "tage", "von", "bis", "deckt", "fehler")}
                       for j in jobs}, "strategien": {}, "kombis": {}}
    for name, st in cfg["strategien"].items():
        res["strategien"][name] = bewerte(name, st, jobs, cfg, rng)
        r = res["strategien"][name]
        print(name, json.dumps({"auswahl": (r["auswahl"]["trades"], r["auswahl"]["pf"], r["auswahl"]["zufall_perzentil"]),
                                "pruefung": (r["pruefung"]["trades"], r["pruefung"]["pf"]), "finalist": r["finalist"],
                                "bestanden": r["bestanden"]}), flush=True)
    for name, kd in (cfg.get("kombis") or {}).items():
        res["kombis"][name] = kombi(name, kd, jobs, cfg, res["strategien"])
    (out / "runde5.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    alle = {j["sym"]: {n: [{k: t[k] for k in ("datum", "d", "r", "pct", "grund", "tage")} for t in s["trades"]]
                       for n, s in j.get("strategien", {}).items()} for j in jobs}
    (out / "runde5_trades.json").write_text(json.dumps(alle, default=str), encoding="utf-8")
    journal_add("Runde 5 gerechnet: " + json.dumps({n: {"finalist": r["finalist"], "bestanden": r["bestanden"],
                                                        "pf_auswahl": r["auswahl"]["pf"]}
                                                    for n, r in res["strategien"].items()}, ensure_ascii=False))
    return res


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--festlegen":
        text = VORAB.read_text(encoding="utf-8")
        journal_add(f"Runde 5 festgelegt, Grund: {' '.join(argv[1:])}. VORAB_runde5 sha256 {sha256_text(text)}")
        return 0
    run(pathlib.Path(argv[0]), pathlib.Path(argv[1]), pathlib.Path(argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
