"""Gold-Matrix: große Suche nach Gold-Strategien über 1 Min., 5 Min., 15 Min., 1 Std. und 4 Std. (nur Rechnung, kein Bot).

Kirons Wunsch vom 11.11.2026 15:07 UTC. Alle Regeln, Kosten und Hürden stehen in suche/VORAB_gold_matrix.yaml und sind
dort festgelegt, bevor gerechnet wurde (Prüfsumme im Protokoll). Dieser Code liest seine Werte aus der Datei, er hat
keine eigenen Stellschrauben.

- 13 Einstiege auf bis zu 5 Zeitebenen, 5 Filter, 9 Stops, 24 Ausstiege: 305 Zellen, 54.375 Varianten.
- Stop und Ausstieg dürfen von einer höheren Zeitebene kommen als der Einstieg (Einstieg 5m, Ausstieg 1h).
- Auswahl auf der ersten Hälfte des Hauptfensters, Bestätigung der höchstens 12 Finalisten auf der zweiten Hälfte.
- Zufallsvergleich: Die ganze Strategie wird als Block um ganze Handelstage verschoben (Abschnitt zwilling).

    python -m suche.gold_matrix --festlegen "Grund"                 # Prüfsumme ins Protokoll, BEVOR gerechnet wird
    python -m suche.gold_matrix auswahl <Datenordner> <Arbeitsordner>     # erste Hälfte, schreibt die Finalisten
    python -m suche.gold_matrix --festlegen-finalisten "Grund"      # Prüfsumme der Finalisten ins Protokoll
    python -m suche.gold_matrix bestaetigung <Datenordner> <Arbeitsordner>   # zweite Hälfte, schreibt das Ergebnis

Ohne passende Prüfsumme im Protokoll rechnet das Programm nicht. Die Bestätigung rechnet erst, wenn auch die
Finalisten versiegelt sind. Mit numba (kein Pflicht-Paket des Repos) läuft die Rechnung in Minuten statt Tagen, ohne
numba rechnet derselbe Code langsam in reinem Python (so laufen die Tests).
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import yaml

try:
    from numba import njit, prange
    SCHNELL = True
except ImportError:                                              # reines Python, gleiche Rechnung
    SCHNELL = False
    prange = range

    def njit(*args, **kwargs):
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]
        return lambda f: f

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_gold_matrix.yaml"
FINALISTEN = ROOT / "suche" / "VORAB_gold_matrix_finalisten.yaml"
KEY = "VORAB_gold_matrix sha256 "
KEY_FIN = "VORAB_gold_matrix_finalisten sha256 "
ERGEBNIS = ROOT / "suche" / "ergebnis_gold_matrix"
NY = "America/New_York"


def regel() -> dict:
    return yaml.safe_load(VORAB.read_text(encoding="utf-8"))["gold_matrix"]


P = regel()
LEITER: list[str] = list(P["zeitebenen"]["leiter"])
EINSTIEGS_EBENEN = LEITER[:-1]
FILTER: list[str] = list(P["filter"])
HAUPT_VON, HAUPT_BIS = pd.Timestamp(P["fenster"]["haupt_von"]), pd.Timestamp(P["fenster"]["haupt_bis"])
MITTE = pd.Timestamp(P["fenster"]["mitte"])
VORLAUF_AB = pd.Timestamp(P["daten"]["vorlauf_ab"])
NACHLAUF = pd.Timedelta(days=int(P["daten"]["nachlauf_tage"]))
SPREAD = float(P["kosten"]["spread_usd"])
ROBUST = float(P["kosten"]["robust_faktor"])
SATZ_LONG = float(P["kosten"]["uebernacht_pct_jahr"]["long"])
SATZ_SHORT = float(P["kosten"]["uebernacht_pct_jahr"]["short"])
MIN_ABSTAND = float(P["stops"]["min_abstand_usd"])
HALTE_MIN = int(P["allgemein"]["halte_tage"]) * 1440
LUECKE_MIN = int(P["zeitebenen"]["luecke_min"])
SPERRE_TAGE = int(P["zwilling"]["sperre_davor_tage"])
ZW_ATR = int(P["zwilling"]["atr"])
MODUS = {"ziel": 0, "zeit": 1, "trail_atr": 2, "trail_struktur": 3, "ema_schluss": 4, "supertrend": 5, "tagesende": 6}
GRUND = {1: "stop", 2: "ziel", 3: "regel", 4: "haltezeit", 5: "datenende"}


def sha256_datei(pfad: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def vorab_ok() -> bool:
    from suche.runde1 import journal_lines, last_value, sha256_text
    return VORAB.exists() and last_value(journal_lines(), KEY) == sha256_text(VORAB.read_text(encoding="utf-8"))


def finalisten_ok() -> bool:
    from suche.runde1 import journal_lines, last_value, sha256_text
    return (FINALISTEN.exists()
            and last_value(journal_lines(), KEY_FIN) == sha256_text(FINALISTEN.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------------------------------------------------
# Daten

def echte_utc(idx) -> pd.DatetimeIndex:
    """Spalte "utc" der HistData-Dateien des Projekts (Dateizeit plus 5 Stunden) in echte UTC. Die Dateizeit ist eine
    osteuropäische Server-Uhr minus 7 Stunden, also ist "utc" plus 2 Stunden Athener Ortszeit. Zeiten, die es dort
    nicht oder doppelt gibt (Umstellung der Uhr), werden NaT."""
    lokal = (pd.DatetimeIndex(idx) + pd.Timedelta(hours=2)).tz_localize("Europe/Athens", ambiguous="NaT",
                                                                        nonexistent="NaT")
    return lokal.tz_convert("UTC").tz_localize(None)


def _lies_csv(pfad: pathlib.Path) -> pd.DataFrame:
    df = pd.read_csv(pfad, index_col=0, parse_dates=True)
    return df[["open", "high", "low", "close"]].astype(float)


def lies_gold(ordner: pathlib.Path) -> pd.DataFrame:
    """1-Minuten-Bid in echter UTC (schon umgerechnet)."""
    df = _lies_csv(pathlib.Path(ordner) / "XAUUSD_1min_utc.csv.gz")
    return df[~df.index.duplicated(keep="last")].sort_index()


def lies_fremd(ordner: pathlib.Path, name: str) -> pd.DataFrame:
    """5-Minuten-Bid eines anderen Marktes, hier erst in echte UTC umgerechnet."""
    df = _lies_csv(pathlib.Path(ordner) / f"{name}_5min.csv.gz")
    df.index = echte_utc(df.index)
    df = df[df.index.notna()]
    return df[~df.index.duplicated(keep="last")].sort_index()


def lies_realzins(ordner: pathlib.Path) -> tuple[np.ndarray, np.ndarray]:
    df = pd.read_csv(pathlib.Path(ordner) / "DFII10.csv")
    werte = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    ok = werte.notna().to_numpy()
    tage = pd.to_datetime(df.iloc[:, 0]).to_numpy().astype("datetime64[D]")
    return tage[ok], werte.to_numpy(float)[ok]


def lies_termine() -> np.ndarray:
    from gold.v2 import termine as tm
    return np.sort(tm.load()["utc"].to_numpy().astype("datetime64[ns]"))


# ---------------------------------------------------------------------------------------------------------------------
# Kerzen und Indikatoren

@dataclass
class Ebene:
    """Kerzen einer Zeitebene, gebaut aus den 1-Minuten-Kerzen."""
    name: str
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    ende1: np.ndarray        # letzte 1-Minuten-Kerze jeder Kerze
    lc: np.ndarray           # je 1-Minuten-Kerze: letzte Kerze dieser Ebene, die vor ihr fertig war (-1: keine)
    cache: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.c)


@dataclass
class Markt:
    t: np.ndarray            # datetime64[ns] UTC, Beginn der 1-Minuten-Kerze
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    tmin: np.ndarray         # Minuten seit 1970
    tag: np.ndarray          # Handelstag (endet 17:00 New York) als Zahl
    sess: np.ndarray         # Zähler, der um 20:55 UTC weiterspringt (Ausstieg tagesende)
    nymin: np.ndarray        # Minuten seit 17:00 New York, dem Beginn des Handelstags (Uhrzeit der Zwillinge)
    gesperrt: np.ndarray     # kein Einstieg: Nacht-Sperre oder Termin
    nach_luecke: np.ndarray  # die Kerze davor liegt mehr als LUECKE_MIN Minuten zurück
    eb: dict                 # Name -> Ebene
    fremd: dict              # Markt -> (Zeit, zu der die 5-Minuten-Kerze fertig ist, Schluss)
    realzins: tuple          # (Tage, Werte)
    termine: np.ndarray
    cache: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.t)


def _hhmm(text: str) -> int:
    hh, mm = (int(x) for x in str(text).split(":"))
    return hh * 60 + mm


def _gruppen(g: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    neu = np.r_[True, g[1:] != g[:-1]]
    i0 = np.flatnonzero(neu)
    return i0, np.r_[i0[1:] - 1, len(g) - 1]


def schluessel(idx: pd.DatetimeIndex, ny: pd.DatetimeIndex, ebene: str) -> np.ndarray:
    """Je 1-Minuten-Kerze die Kerze der Ebene, in die sie fällt. Gleiche Werte heißen gleiche Kerze."""
    if ebene == "1m":
        return idx.values
    if ebene in ("5m", "15m", "1h"):
        return idx.floor({"5m": "5min", "15m": "15min", "1h": "1h"}[ebene]).values
    if ebene == "4h":                                            # Beginn 18, 22, 2, 6, 10, 14 Uhr New York
        return (ny + pd.Timedelta(hours=6)).floor("4h").values
    if ebene == "1d":                                            # Handelstag endet 17:00 New York
        return (ny + pd.Timedelta(hours=7)).normalize().values
    raise ValueError(ebene)


def markt(gold: pd.DataFrame, fremd: dict | None = None, realzins: tuple | None = None,
          termine: np.ndarray | None = None) -> Markt:
    """gold: 1-Minuten-Bid mit UTC-Index (naiv). fremd: Name -> 5-Minuten-Bid in echter UTC."""
    gold = gold[~gold.index.duplicated(keep="last")].sort_index()
    idx = pd.DatetimeIndex(gold.index)
    n = len(idx)
    ny = idx.tz_localize("UTC").tz_convert(NY).tz_localize(None)
    t = idx.values.astype("datetime64[ns]")
    o, h, lo, c = (np.ascontiguousarray(gold[k].to_numpy(float)) for k in ("open", "high", "low", "close"))
    tmin = t.astype("datetime64[m]").astype(np.int64)
    tag = (ny + pd.Timedelta(hours=7)).normalize().values.astype("datetime64[D]").astype(np.int64)
    im_tag = tmin % 1440
    sp = P["allgemein"]["sperre_utc"]
    gesperrt = (im_tag >= _hhmm(sp["von"])) & (im_tag < _hhmm(sp["bis"]))
    termine = np.sort(np.asarray(termine if termine is not None else [], dtype="datetime64[ns]"))
    rand = np.timedelta64(int(P["allgemein"]["termin_sperre_min"]), "m")
    for ev in termine:
        gesperrt[np.searchsorted(t, ev - rand, side="left"):np.searchsorted(t, ev + rand, side="right")] = True
    sess = (tmin - _hhmm(P["ausstiege"]["tagesende"]["utc"])) // 1440
    nach_luecke = np.r_[True, np.diff(tmin) > LUECKE_MIN]
    ny7 = ny + pd.Timedelta(hours=7)
    nymin = (ny7.hour * 60 + ny7.minute).to_numpy().astype(np.int64)
    eb = {}
    for name in LEITER:
        i0, i1 = _gruppen(schluessel(idx, ny, name))
        lc = np.searchsorted(i1, np.arange(n), side="left") - 1
        eb[name] = Ebene(name, o[i0], np.maximum.reduceat(h, i0), np.minimum.reduceat(lo, i0), c[i1],
                         i1.astype(np.int64), lc.astype(np.int64))
    fr = {}
    for name, df in (fremd or {}).items():
        fr[name] = (df.index.values.astype("datetime64[ns]") + np.timedelta64(5, "m"), df["close"].to_numpy(float))
    rz = realzins if realzins is not None else (np.array([], dtype="datetime64[D]"), np.array([], dtype=float))
    return Markt(t, o, h, lo, c, tmin, tag, sess, nymin, gesperrt, nach_luecke, eb, fr, rz, termine)


@njit(cache=True)
def _atr_kern(h, lo, c, n):
    m = len(h)
    out = np.full(m, np.nan)
    if m < n:
        return out
    s = 0.0
    letzter = 0.0
    for i in range(m):
        tr = h[i] - lo[i]
        if i > 0:
            a = abs(h[i] - c[i - 1])
            b = abs(lo[i] - c[i - 1])
            if a > tr:
                tr = a
            if b > tr:
                tr = b
        if i < n:
            s += tr
            if i == n - 1:
                letzter = s / n
                out[i] = letzter
        else:
            letzter = letzter + (tr - letzter) / n
            out[i] = letzter
    return out


def atr_wilder(h: np.ndarray, lo: np.ndarray, c: np.ndarray, n: int = 14) -> np.ndarray:
    """Wie suche/gold_zonen.py atr_wilder: Start mit dem Schnitt der ersten n Spannen, dann Wilder."""
    return _atr_kern(np.asarray(h, float), np.asarray(lo, float), np.asarray(c, float), int(n))


@njit(cache=True)
def _supertrend_kern(h, lo, c, atr, faktor):
    """Richtung des SuperTrend je Kerze: +1 Aufwärtstrend, -1 Abwärtstrend, 0 solange der ATR fehlt."""
    m = len(c)
    out = np.zeros(m, np.int8)
    ob = 0.0
    un = 0.0
    r = 0
    for i in range(m):
        a = atr[i]
        if a != a:
            continue
        mitte = (h[i] + lo[i]) / 2.0
        ob_roh = mitte + faktor * a
        un_roh = mitte - faktor * a
        if r == 0:
            ob, un = ob_roh, un_roh
            r = 1 if c[i] >= mitte else -1
        else:
            if ob_roh < ob or c[i - 1] > ob:
                ob = ob_roh
            if un_roh > un or c[i - 1] < un:
                un = un_roh
            if r == 1 and c[i] < un:
                r = -1
            elif r == -1 and c[i] > ob:
                r = 1
        out[i] = r
    return out


def ema(x: np.ndarray, n: int) -> np.ndarray:
    out = pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy().copy()
    out[:n - 1] = np.nan
    return out


def rsi_wilder(c: np.ndarray, n: int) -> np.ndarray:
    d = np.diff(c, prepend=np.nan)
    auf = pd.Series(np.where(d > 0, d, 0.0)).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()
    ab = pd.Series(np.where(d < 0, -d, 0.0)).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(ab > 0, 100.0 - 100.0 / (1.0 + auf / ab), np.where(auf > 0, 100.0, 50.0))
    out[:5 * n] = np.nan
    return out


def _vor(x: np.ndarray) -> np.ndarray:
    return np.r_[np.nan, x[:-1]]


def _roll(x: np.ndarray, n: int, was: str) -> np.ndarray:
    r = pd.Series(x).rolling(n)
    return {"max": r.max, "min": r.min, "mean": r.mean}[was]().to_numpy()


def ind(k: Ebene, name: str, *arg):
    """Indikatoren je Ebene, einmal gerechnet und gemerkt."""
    key = (name, *arg)
    if key in k.cache:
        return k.cache[key]
    if name == "atr":
        out = atr_wilder(k.h, k.l, k.c, arg[0])
    elif name == "ema":
        out = ema(k.c, arg[0])
    elif name == "rsi":
        out = rsi_wilder(k.c, arg[0])
    elif name == "sma":
        out = _roll(k.c, arg[0], "mean")
    elif name == "sd":
        out = pd.Series(k.c).rolling(arg[0]).std(ddof=0).to_numpy()
    elif name == "hoch":
        out = _roll(k.h, arg[0], "max")
    elif name == "tief":
        out = _roll(k.l, arg[0], "min")
    elif name == "supertrend":
        out = _supertrend_kern(k.h, k.l, k.c, atr_wilder(k.h, k.l, k.c, arg[0]), float(arg[1]))
    else:
        raise ValueError(name)
    k.cache[key] = out
    return out


def fremd_auf(m: Markt, name: str, ebene: str) -> np.ndarray:
    """Je Kerze der Ebene der Schluss der letzten 5-Minuten-Kerze des anderen Marktes, die zum Schluss der Gold-Kerze
    fertig war. Zu alt oder nicht vorhanden: nan."""
    key = ("fremd", name, ebene)
    if key not in m.cache:
        fertig, schluss = m.fremd[name]
        jetzt = m.t[m.eb[ebene].ende1] + np.timedelta64(1, "m")
        pos = np.searchsorted(fertig, jetzt, side="right") - 1
        pp = np.maximum(pos, 0)
        alt = np.timedelta64(int(P["fremdkurse"]["max_alter_min"]), "m")
        ok = (pos >= 0) & (jetzt - fertig[pp] <= alt)
        m.cache[key] = np.where(ok, schluss[pp], np.nan)
    return m.cache[key]


def dollar_korb(m: Markt, ebene: str) -> np.ndarray:
    key = ("korb", ebene)
    if key not in m.cache:
        out = np.zeros(len(m.eb[ebene]))
        for name, gewicht in P["fremdkurse"]["gewichte"].items():
            out = out + float(gewicht) * np.log(fremd_auf(m, name, ebene))
        m.cache[key] = out
    return m.cache[key]


def z_wert(x: np.ndarray, kerzen: int, z_kerzen: int) -> tuple[np.ndarray, np.ndarray]:
    """Änderung über `kerzen` Kerzen, geteilt durch ihre Standardabweichung über die `z_kerzen` Kerzen davor."""
    s = pd.Series(x)
    dx = s - s.shift(kerzen)
    sd = dx.rolling(z_kerzen, min_periods=z_kerzen // 2).std().shift(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = (dx / sd).to_numpy()
    return z, dx.to_numpy()


# ---------------------------------------------------------------------------------------------------------------------
# Einstiege

def _frisch(b: np.ndarray) -> np.ndarray:
    return b & ~np.r_[False, b[:-1]]


def roh_signale(m: Markt, fam: str, ebene: str) -> tuple[np.ndarray, np.ndarray]:
    """Je Kerze der Ebene: Long-Signal, Short-Signal. Nur Werte bis zum Schluss dieser Kerze."""
    k, p = m.eb[ebene], P["einstiege"][fam]
    o, h, lo, c = k.o, k.h, k.l, k.c
    with np.errstate(invalid="ignore", divide="ignore"):
        if fam == "ausbruch":
            n = int(p["kerzen"])
            lang, kurz = _frisch(c > _vor(ind(k, "hoch", n))), _frisch(c < _vor(ind(k, "tief", n)))
        elif fam == "ruecksetzer":
            es, el, r = ind(k, "ema", int(p["ema_schnell"])), ind(k, "ema", int(p["ema_langsam"])), ind(k, "rsi", int(p["rsi_laenge"]))
            lang = _frisch((es > el) & (c > el) & (r < float(p["rsi_unter"])))
            kurz = _frisch((es < el) & (c < el) & (r > 100.0 - float(p["rsi_unter"])))
        elif fam == "band_umkehr":
            n, b = int(p["laenge"]), float(p["breite_sd"])
            mitte, sd = ind(k, "sma", n), ind(k, "sd", n)
            lang, kurz = _frisch(c < mitte - b * sd), _frisch(c > mitte + b * sd)
        elif fam == "schwungkerze":
            a, sp, rand = _vor(ind(k, "atr", 14)), h - lo, float(p["rand_anteil"])
            gross = sp >= float(p["spanne_atr"]) * a
            lang = gross & (c >= h - rand * sp) & (c > o)
            kurz = gross & (c <= lo + rand * sp) & (c < o)
        elif fam == "fehlausbruch":
            n = int(p["kerzen"])
            tief, hoch = _vor(ind(k, "tief", n)), _vor(ind(k, "hoch", n))
            lang, kurz = (lo < tief) & (c > tief), (h > hoch) & (c < hoch)
        elif fam == "enge_ausbruch":
            n, b = int(p["laenge"]), float(p["breite_sd"])
            mitte, sd = ind(k, "sma", n), ind(k, "sd", n)
            breite = 2.0 * b * sd / mitte
            rang = pd.Series(breite).rolling(int(p["rang_kerzen"])).rank(pct=True).to_numpy()
            eng = np.r_[False, (rang <= float(p["rang_anteil"]))[:-1]]
            lang, kurz = _frisch(eng & (c > _vor(mitte + b * sd))), _frisch(eng & (c < _vor(mitte - b * sd)))
        elif fam == "ema_kreuz":
            es, el = ind(k, "ema", int(p["ema_schnell"])), ind(k, "ema", int(p["ema_langsam"]))
            lang, kurz = (es > el) & (_vor(es) <= _vor(el)), (es < el) & (_vor(es) >= _vor(el))
        elif fam == "rund_bruch":
            fach = np.floor(c / float(p["raster_usd"]))
            lang, kurz = fach > _vor(fach), fach < _vor(fach)
        elif fam == "rund_abprall":
            raster, a = float(p["raster_usd"]), float(p["abstand_atr"]) * ind(k, "atr", 14)
            unten = np.floor(_vor(c) / raster) * raster
            oben = unten + raster
            lang, kurz = (lo <= unten) & (c >= unten + a), (h >= oben) & (c <= oben - a)
        elif fam == "pivot_abprall":
            d = m.eb["1d"]
            tage = m.tag[d.ende1]
            pos = np.searchsorted(tage, m.tag[k.ende1], side="left") - 1          # letzter Handelstag vor dem der Kerze
            pp = np.maximum(pos, 0)
            hh, tt, ss = (np.where(pos >= 0, x[pp], np.nan) for x in (d.h, d.l, d.c))
            piv = (hh + tt + ss) / 3.0
            s1, r1, pc = 2.0 * piv - hh, 2.0 * piv - tt, _vor(c)
            lang, kurz = (lo <= s1) & (c > s1) & (pc > s1), (h >= r1) & (c < r1) & (pc < r1)
        elif fam in ("dollar_nachlauf", "silber_vorlauf", "aktien_flucht"):
            nk, nz, zs = int(p["kerzen"]), int(p["z_kerzen"]), float(p["z_schwelle"])
            zg, dg = z_wert(np.log(c), nk, nz)
            if fam == "dollar_nachlauf":
                zd, _ = z_wert(dollar_korb(m, ebene), nk, nz)
                gm = float(p["z_gold_max"])
                lang, kurz = _frisch((zd <= -zs) & (zg <= gm)), _frisch((zd >= zs) & (zg >= -gm))
            elif fam == "silber_vorlauf":
                zx, _ = z_wert(np.log(fremd_auf(m, "XAGUSD", ebene)), nk, nz)
                gm = float(p["z_gold_max"])
                lang, kurz = _frisch((zx >= zs) & (zg <= gm)), _frisch((zx <= -zs) & (zg >= -gm))
            else:
                za, _ = z_wert(np.log(fremd_auf(m, "SPXUSD", ebene)), nk, nz)
                lang, kurz = _frisch((za <= -zs) & (dg > 0)), _frisch((za >= zs) & (dg < 0))
        else:
            raise ValueError(fam)
    lang, kurz = np.asarray(lang, bool), np.asarray(kurz, bool)
    beide = lang & kurz
    return lang & ~beide, kurz & ~beide


def einstiege(m: Markt, fam: str, ebene: str) -> tuple[np.ndarray, np.ndarray]:
    """1-Minuten-Kerzen, zu deren Eröffnung ein Signal handelt, und die Richtung. Nach Zeit sortiert."""
    key = ("einstiege", fam, ebene)
    if key not in m.cache:
        lang, kurz = roh_signale(m, fam, ebene)
        j = np.flatnonzero(lang | kurz)
        d = np.where(lang[j], 1, -1).astype(np.int64)
        e = m.eb[ebene].ende1[j] + 1
        ok = e < len(m)
        e, d = e[ok], d[ok]
        ok = ~m.nach_luecke[e] & ~m.gesperrt[e]
        m.cache[key] = (e[ok].astype(np.int64), d[ok])
    return m.cache[key]


# ---------------------------------------------------------------------------------------------------------------------
# Filter

def news_richtungen(m: Markt) -> np.ndarray:
    """Je Termin die Richtung, in die Gold von kurz davor bis eine Stunde danach gelaufen ist (0: keine)."""
    if "news" not in m.cache:
        p = P["filter"]["news_richtung"]
        vor, ab, alt = (np.timedelta64(int(p[x]), "m") for x in ("vor_min", "ab_min", "alt_min"))
        k1h = m.eb["1h"]
        a1h = ind(k1h, "atr", 14)
        out = np.zeros(len(m.termine), dtype=np.int64)
        for i, ev in enumerate(m.termine):
            i0 = int(np.searchsorted(m.t, ev - vor, side="left")) - 1
            i1 = int(np.searchsorted(m.t, ev + ab, side="left")) - 1
            ie = int(np.searchsorted(m.t, ev, side="left"))
            if i0 < 0 or ie >= len(m) or m.t[i0] < ev - vor - alt or m.t[i1] < ev + ab - alt:
                continue
            q = k1h.lc[ie]
            a = a1h[q] if q >= 0 else np.nan
            weg = m.c[i1] - m.c[i0]
            if a == a and abs(weg) >= float(p["min_atr"]) * a:
                out[i] = 1 if weg > 0 else -1
        m.cache["news"] = out
    return m.cache["news"]


def filter_maske(m: Markt, name: str, ebene: str, e: np.ndarray, d: np.ndarray) -> np.ndarray:
    """Je Einstieg: erlaubt der Filter ihn? Nur Werte, die vor der Einstiegskerze feststehen."""
    if name == "ohne":
        return np.ones(len(e), bool)
    p = P["filter"][name]
    if name == "trend_hoch":
        k = m.eb[p["ebene"][ebene]]
        em, n = ind(k, "ema", int(p["ema"])), int(p["steigung_kerzen"])
        q = k.lc[e]
        qq = np.maximum(q, n)
        with np.errstate(invalid="ignore"):
            auf = (k.c[qq] > em[qq]) & (em[qq] > em[qq - n])
            ab = (k.c[qq] < em[qq]) & (em[qq] < em[qq - n])
        return (q >= n) & np.where(d > 0, auf, ab)
    if name == "dollar_wind":
        k = m.eb[p["ebene"]]
        korb = dollar_korb(m, p["ebene"])
        em = ema(korb, int(p["ema"]))
        q = k.lc[e]
        qq = np.maximum(q, 0)
        with np.errstate(invalid="ignore"):
            return (q >= 0) & np.where(d > 0, korb[qq] < em[qq], korb[qq] > em[qq])
    if name == "realzins":
        tage, werte = m.realzins
        n = int(p["abstand_werte"])
        if len(tage) <= n:
            return np.zeros(len(e), bool)
        stichtag = m.t[e].astype("datetime64[D]") - np.timedelta64(int(p["verzug_tage"]), "D")
        pos = np.searchsorted(tage, stichtag, side="right") - 1
        pp = np.maximum(pos, n)
        weg = werte[pp] - werte[pp - n]
        return (pos >= n) & np.where(d > 0, weg < 0, weg > 0)
    if name == "news_richtung":
        if not len(m.termine):
            return np.zeros(len(e), bool)
        richtung = news_richtungen(m)
        ab, bis = np.timedelta64(int(p["ab_min"]), "m"), np.timedelta64(int(p["bis_std"]), "h")
        te = m.t[e]
        pos = np.searchsorted(m.termine + ab, te, side="right") - 1
        pp = np.maximum(pos, 0)
        return (pos >= 0) & (te < m.termine[pp] + bis) & (richtung[pp] == d)
    raise ValueError(name)


# ---------------------------------------------------------------------------------------------------------------------
# Stops und Ausstiege

def stop_liste(ebene: str) -> list[tuple[str, str, str]]:
    """(Name, Art, Stop-Ebene) für eine Einstiegs-Ebene."""
    i = LEITER.index(ebene)
    return [(f"{art}_{s}", art, s) for s in LEITER[i:i + int(P["stops"]["ebenen"])] for art in P["stops"]["arten"]]


def ausstieg_liste(ebene: str) -> list[tuple[str, int, float, str | None]]:
    """(Name, Modus, Zahl, Ausstiegs-Ebene) für eine Einstiegs-Ebene."""
    a, i = P["ausstiege"], LEITER.index(ebene)
    out = [(f"ziel_{r}r", MODUS["ziel"], float(r), None) for r in a["ziel"]["r"]]
    for x in LEITER[i:i + int(a["ebenen"])]:
        out += [(f"zeit_{x}", MODUS["zeit"], float(a["zeit"]["kerzen"]), x),
                (f"trail_atr_{x}", MODUS["trail_atr"], float(a["trail_atr"]["atr"]), x),
                (f"trail_struktur_{x}", MODUS["trail_struktur"], 0.0, x),
                (f"ema_schluss_{x}", MODUS["ema_schluss"], 0.0, x),
                (f"supertrend_{x}", MODUS["supertrend"], 0.0, x)]
    out.append(("tagesende", MODUS["tagesende"], 0.0, None))
    return out


def zellen() -> list[tuple[str, str, str]]:
    """Alle Zellen (Einstieg, Zeitebene, Filter) in fester Reihenfolge."""
    return [(fam, eb, flt) for fam, p in P["einstiege"].items() for eb in p["zeitebenen"] for flt in FILTER]


def zahl_varianten() -> int:
    return sum(len(stop_liste(eb)) * len(ausstieg_liste(eb)) for _, eb, _ in zellen())


def stop_abstand(m: Markt, art: str, ebene: str, e: np.ndarray, d: np.ndarray) -> np.ndarray:
    """Stop-Abstand in USD je Einstieg (nan: kein Trade)."""
    k, p = m.eb[ebene], P["stops"]["arten"][art]
    q = k.lc[e]
    qq = np.maximum(q, 0)
    a = ind(k, "atr", 14)[qq]
    if art == "swing":
        n = int(p["kerzen"])
        tief, hoch = ind(k, "tief", n)[qq], ind(k, "hoch", n)[qq]
        puffer = float(p["puffer_atr"]) * a
        with np.errstate(invalid="ignore"):
            dist = np.where(d > 0, m.o[e] - (tief - puffer), (hoch + puffer) - m.o[e])
            dist = np.minimum(np.maximum(dist, float(p["min_atr"]) * a), float(p["max_atr"]) * a)
        dist = np.where(np.isnan(tief) | np.isnan(a), np.nan, dist)
    else:
        dist = float(p["atr"]) * a
    return np.where(q >= 0, dist, np.nan).astype(float)


def x_felder(m: Markt, ebene: str | None) -> tuple:
    """Felder der Ausstiegs-Ebene für den Kern: letzte fertige Kerze je Minute, ATR, Tief und Hoch der letzten Kerzen,
    Lage zum EMA, SuperTrend."""
    ebene = ebene or "1m"
    key = ("x", ebene)
    if key not in m.cache:
        a, k = P["ausstiege"], m.eb[ebene]
        n = int(a["trail_struktur"]["kerzen"])
        em = ind(k, "ema", int(a["ema_schluss"]["ema"]))
        with np.errstate(invalid="ignore"):
            lage = np.where(np.isnan(em), 0, np.sign(k.c - em)).astype(np.int8)
        st = ind(k, "supertrend", int(a["supertrend"]["laenge"]), float(a["supertrend"]["faktor"]))
        m.cache[key] = (k.lc, ind(k, "atr", 14), ind(k, "tief", n), ind(k, "hoch", n), lage, st)
    return m.cache[key]


# ---------------------------------------------------------------------------------------------------------------------
# Kern: ein Trade, ein Lauf, viele Zwillinge

@njit(cache=True)
def _trade(e, d, dist, modus, zahl, sp, halte_min, o, h, lo, c, tmin, sess, lcx, atrx, tiefx, hochx, lagex, stx):
    """Ein Trade ab der 1-Minuten-Kerze e. Rückgabe: Kerze des Ausstiegs, Ausstiegskurs, Einstiegskurs, Grund
    (1 Stop, 2 Ziel, 3 Regel, 4 Haltezeit, 5 Datenende). Long steigt zum Bid aus, Short zum Ask."""
    n = len(o)
    if d > 0:
        fill = o[e] + sp
        stop = fill - dist
        ziel = fill + zahl * dist
    else:
        fill = o[e]
        stop = fill + dist
        ziel = fill - zahl * dist
    hh = h[e]
    ll = lo[e]
    t_max = tmin[e] + halte_min
    s0 = sess[e]
    q0 = lcx[e]
    qv = q0
    for i in range(e, n):
        if i > e:
            raus = 0
            if tmin[i] >= t_max:
                raus = 4
            elif modus == 6:
                if sess[i] > s0:
                    raus = 3
            elif modus >= 1:
                q = lcx[i]
                if q != qv:                                      # seit der letzten Minute ist eine Kerze fertig geworden
                    qv = q
                    if modus == 1:
                        if q >= q0 + zahl:
                            raus = 3
                    elif modus == 4:
                        if lagex[q] * d < 0:
                            raus = 3
                    elif modus == 5:
                        if stx[q] * d < 0:
                            raus = 3
                    elif modus == 2:
                        a = atrx[q]
                        if a == a:
                            if d > 0:
                                neu = hh - zahl * a
                                if neu > stop:
                                    stop = neu
                            else:
                                neu = ll + sp + zahl * a
                                if neu < stop:
                                    stop = neu
                    else:
                        if d > 0:
                            neu = tiefx[q]
                            if neu > stop:
                                stop = neu
                        else:
                            neu = hochx[q] + sp
                            if neu < stop:
                                stop = neu
            if raus != 0:
                if d > 0:
                    return i, o[i], fill, raus
                return i, o[i] + sp, fill, raus
        if d > 0:
            if o[i] <= stop:
                return i, o[i], fill, 1
            if lo[i] <= stop:
                return i, stop, fill, 1
            if modus == 0 and h[i] >= ziel:
                return i, ziel, fill, 2
        else:
            auf = o[i] + sp
            if auf >= stop:
                return i, auf, fill, 1
            if h[i] + sp >= stop:
                return i, stop, fill, 1
            if modus == 0 and lo[i] + sp <= ziel:
                return i, ziel, fill, 2
        if h[i] > hh:
            hh = h[i]
        if lo[i] < ll:
            ll = lo[i]
    if d > 0:
        return n - 1, c[n - 1], fill, 5
    return n - 1, c[n - 1] + sp, fill, 5


@njit(cache=True)
def lauf_echt(se, sd, sdist, modus, zahl, sp, satz_long, satz_short, min_abstand, halte_min,
              o, h, lo, c, tmin, sess, tag, lcx, atrx, tiefx, hochx, lagex, stx):
    """Signale der Reihe nach, höchstens ein Trade gleichzeitig. Je Signal: Ergebnis in R (nan: nicht genommen), Kerze
    des Ausstiegs, Grund."""
    m = len(se)
    r = np.full(m, np.nan)
    aus = np.full(m, -1, np.int64)
    grund = np.zeros(m, np.int8)
    frei = -1
    for k in range(m):
        e = se[k]
        if e <= frei:
            continue
        dist = sdist[k]
        if not (dist >= min_abstand):
            continue
        d = sd[k]
        x, kurs, fill, g = _trade(e, d, dist, modus, zahl, sp, halte_min, o, h, lo, c, tmin, sess,
                                  lcx, atrx, tiefx, hochx, lagex, stx)
        satz = satz_long if d > 0 else satz_short
        r[k] = d * (kurs - fill) / dist - satz / 36500.0 * (tag[x] - tag[e]) * fill / dist
        aus[k] = x
        grund[k] = g
        frei = x
    return r, aus, grund


@njit(parallel=True, cache=True)
def lauf_zwillinge(tw, lam, sd, sdist, nacht, modus, zahl, sp, halte_min,
                   o, h, lo, c, tmin, sess, tag, lcx, atrx, tiefx, hochx, lagex, stx):
    """tw[k, b]: Einstiegskerze des Zwillings von Trade k im Lauf b. lam[k, b]: Schwankung dort geteilt durch die
    Schwankung am echten Einstieg. Stop-Abstand und Spread des Zwillings sind die echten mal lam, nacht[k] ist die
    Übernachtgebühr des echten Trades in R je Nacht. Rückgabe je Lauf: Summe R, Gewinne, Verluste."""
    nt, nb = tw.shape
    summe = np.zeros(nb)
    gew = np.zeros(nb)
    verl = np.zeros(nb)
    for b in prange(nb):
        s = 0.0
        g = 0.0
        v = 0.0
        for k in range(nt):
            e = tw[k, b]
            d = sd[k]
            f = lam[k, b]
            dist = sdist[k] * f
            x, kurs, fill, _ = _trade(e, d, dist, modus, zahl, sp * f, halte_min, o, h, lo, c, tmin, sess,
                                      lcx, atrx, tiefx, hochx, lagex, stx)
            rr = d * (kurs - fill) / dist - nacht[k] * (tag[x] - tag[e])
            s += rr
            if rr > 0:
                g += rr
            else:
                v -= rr
        summe[b] = s
        gew[b] = g
        verl[b] = v
    return summe, gew, verl


def _kern_felder(m: Markt) -> tuple:
    return (m.o, m.h, m.l, m.c, m.tmin, m.sess, m.tag)


def rechne(m: Markt, e, d, dist, modus: int, zahl: float, xeb: str | None, faktor: float = 1.0):
    """Echter Lauf einer Variante. faktor 1,5 ist die Robust-Rechnung (Spread und Übernachtgebühr mal 1,5)."""
    return lauf_echt(e, d, dist, modus, zahl, SPREAD * faktor, SATZ_LONG * faktor, SATZ_SHORT * faktor, MIN_ABSTAND,
                     HALTE_MIN, *_kern_felder(m), *x_felder(m, xeb))


def nacht_r(m: Markt, e: np.ndarray, d: np.ndarray, dist: np.ndarray) -> np.ndarray:
    """Übernachtgebühr des echten Trades in R je Nacht (wie in lauf_echt, mit dem einfachen Spread)."""
    fill = m.o[e] + np.where(d > 0, SPREAD, 0.0)
    return np.where(d > 0, SATZ_LONG, SATZ_SHORT) / 36500.0 * fill / dist


def zwillinge(m: Markt, tw, lam, d, dist, modus: int, zahl: float, xeb: str | None, nacht=None):
    """Zwillings-Läufe einer Variante. Ohne `nacht` kommt die Gebühr je Nacht aus den Einstiegen selbst (tw[:, 0])."""
    tw, d, dist = np.ascontiguousarray(tw), np.ascontiguousarray(d), np.ascontiguousarray(dist, dtype=float)
    nacht = nacht_r(m, tw[:, 0], d, dist) if nacht is None else nacht
    return lauf_zwillinge(tw, np.ascontiguousarray(lam, dtype=float), d, dist, np.ascontiguousarray(nacht, dtype=float),
                          modus, zahl, SPREAD, HALTE_MIN, *_kern_felder(m), *x_felder(m, xeb))


# ---------------------------------------------------------------------------------------------------------------------
# Zwillinge: die ganze Strategie um Handelstage verschoben

@dataclass
class Kalender:
    """Erlaubte 1-Minuten-Kerzen eines Fensters nach Zeit, je Kerze der Handelstag (laufende Nummer im Fenster) mal 1440
    plus Minuten seit 17:00 New York."""
    kerzen: np.ndarray
    key: np.ndarray
    tage: int
    je_kerze: np.ndarray                                         # je Kerze des Marktes: ihr Schlüssel, -1 wenn nicht erlaubt


def kalender(m: Markt, von, bis) -> Kalender:
    key = ("kalender", str(pd.Timestamp(von)), str(pd.Timestamp(bis)))
    if key not in m.cache:
        v, b = np.datetime64(pd.Timestamp(von), "ns"), np.datetime64(pd.Timestamp(bis), "ns")
        erlaubt = np.flatnonzero(~m.gesperrt & ~m.nach_luecke & (m.t >= v) & (m.t < b)).astype(np.int64)
        tage, nr = np.unique(m.tag[erlaubt], return_inverse=True)
        k = nr.astype(np.int64) * 1440 + m.nymin[erlaubt]
        if len(k) and (np.diff(k) <= 0).any():
            raise ValueError("Die Uhr der Handelstage läuft nicht streng vorwärts")
        je = np.full(len(m), -1, np.int64)
        je[erlaubt] = k
        m.cache[key] = Kalender(erlaubt, k, int(len(tage)), je)
    return m.cache[key]


def schritte(tage: int, anzahl: int | None = None) -> np.ndarray:
    """Die Verschiebungen in Handelstagen: 1 bis tage - 1 - SPERRE_TAGE. So landet kein Zwilling am Tag des echten
    Einstiegs oder in den SPERRE_TAGE Handelstagen davor. Mit `anzahl` nur so viele, gleichmäßig über alle verteilt."""
    hoechste = tage - 1 - SPERRE_TAGE
    if hoechste < 1:
        raise ValueError("Das Fenster ist zu kurz für eine Verschiebung")
    alle = np.arange(1, hoechste + 1, dtype=np.int64)
    if anzahl is None or anzahl >= len(alle):
        return alle
    return np.unique(np.round(np.linspace(1, hoechste, int(anzahl))).astype(np.int64))


def verschiebe(kal: Kalender, e: np.ndarray, schr: np.ndarray) -> np.ndarray:
    """tw[k, b]: Einstieg k um schr[b] Handelstage nach vorn verschoben, zur selben Uhrzeit in New York, sonst an der
    nächsten erlaubten Kerze danach. Nach dem letzten Handelstag des Fensters geht es an seinem ersten weiter."""
    k = kal.je_kerze[e]
    if len(e) and k.min() < 0:
        raise ValueError("Einstieg außerhalb der erlaubten Kerzen")
    ziel = ((k // 1440)[:, None] + schr[None, :]) % kal.tage * 1440 + (k % 1440)[:, None]
    p = np.searchsorted(kal.key, ziel, side="left")
    p[p == len(kal.key)] = 0
    return kal.kerzen[p]


def vola_faktor(m: Markt, ebene: str, e: np.ndarray, tw: np.ndarray) -> np.ndarray:
    """ATR der Stop-Ebene (letzte fertige Kerze) am Zwilling geteilt durch den ATR am echten Einstieg. Fehlt einer: 1."""
    k = m.eb[ebene]
    a = ind(k, "atr", ZW_ATR)

    def bei(i: np.ndarray) -> np.ndarray:
        q = k.lc[i]
        return np.where(q >= 0, a[np.maximum(q, 0)], np.nan)

    with np.errstate(divide="ignore", invalid="ignore"):
        lam = bei(tw) / bei(e)[:, None]
    return np.where(np.isfinite(lam) & (lam > 0), lam, 1.0)


# ---------------------------------------------------------------------------------------------------------------------
# Kennzahlen

def gf(r: np.ndarray) -> float | None:
    """Gewinnfaktor, ungerundet. Ohne Verlust: None."""
    g, v = float(r[r > 0].sum()), float(-r[r < 0].sum())
    return g / v if v > 0 else None


def kennzahlen(r: np.ndarray) -> dict:
    r = np.asarray(r, float)
    if not len(r):
        return {"trades": 0, "pf": None, "summe_r": 0.0, "treffer": None, "rueckgang_r": 0.0}
    eq = np.r_[0.0, np.cumsum(r)]
    f = gf(r)
    return {"trades": int(len(r)), "pf": None if f is None else round(f, 2), "summe_r": round(float(r.sum()), 1),
            "treffer": round(float((r > 0).mean() * 100), 1),
            "rueckgang_r": round(float((np.maximum.accumulate(eq) - eq).max()), 1)}


def holm(ps: dict[str, float], alpha: float = 0.05) -> dict[str, bool]:
    """Holm über alle: die k-kleinste p muss höchstens alpha / (m - k + 1) sein, sonst fällt sie und alle größeren."""
    reihe = sorted(ps, key=lambda k: (ps[k], k))
    out, offen = {}, True
    for k, name in enumerate(reihe):
        offen = offen and ps[name] <= alpha / (len(reihe) - k)
        out[name] = offen
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Auswahl (erste Hälfte)

SPALTEN = ["key", "einstieg", "ebene", "filter", "stop", "ausstieg", "signale", "trades", "je_woche", "pf", "summe_r",
           "pf_robust", "median_halte_min", "zw_mittel", "zw_sd", "z", "rang_pct", "zw_pf12"]


def im_fenster(m: Markt, e: np.ndarray, von, bis) -> np.ndarray:
    return (m.t[e] >= np.datetime64(pd.Timestamp(von), "ns")) & (m.t[e] < np.datetime64(pd.Timestamp(bis), "ns"))


def auswahl_zelle(m: Markt, fam: str, ebene: str, flt: str, von, bis, laeufe: int, min_trades: int) -> list[dict]:
    """Alle Varianten einer Zelle im Fenster: echter Lauf, Robust-Lauf und Zwillinge (nur ab min_trades Trades)."""
    e, d = einstiege(m, fam, ebene)
    ok = im_fenster(m, e, von, bis)
    e, d = e[ok], d[ok]
    ok = filter_maske(m, flt, ebene, e, d)
    e, d = np.ascontiguousarray(e[ok]), np.ascontiguousarray(d[ok])
    wochen = (pd.Timestamp(bis) - pd.Timestamp(von)) / pd.Timedelta(days=7)
    out, lam_seb, lam = [], None, None
    kal = kalender(m, von, bis)
    tw = verschiebe(kal, e, schritte(kal.tage, laeufe))          # dieselben Verschiebungen für alle Varianten der Zelle
    for sname, art, seb in stop_liste(ebene):
        dist = np.ascontiguousarray(stop_abstand(m, art, seb, e, d))
        with np.errstate(divide="ignore", invalid="ignore"):
            nacht = nacht_r(m, e, d, dist)
        if seb != lam_seb:                                       # Schwankung der Stop-Ebene am Zwilling und am Einstieg
            lam_seb, lam = seb, vola_faktor(m, seb, e, tw)
        for aname, modus, zahl, xeb in ausstieg_liste(ebene):
            r, aus, _ = rechne(m, e, d, dist, modus, zahl, xeb)
            gen = ~np.isnan(r)
            rr = r[gen]
            n = int(gen.sum())
            f = gf(rr) if n else None
            zeile = {"key": f"{fam}.{ebene}.{flt}.{sname}.{aname}", "einstieg": fam, "ebene": ebene, "filter": flt,
                     "stop": sname, "ausstieg": aname, "signale": int(len(e)), "trades": n,
                     "je_woche": round(n / wochen, 3), "pf": f, "summe_r": float(rr.sum()) if n else 0.0,
                     "pf_robust": None, "median_halte_min": None, "zw_mittel": None, "zw_sd": None, "z": None,
                     "rang_pct": None, "zw_pf12": None}
            if n:
                zeile["median_halte_min"] = float(np.median(m.tmin[aus[gen]] - m.tmin[e[gen]]))
                rob, _, _ = rechne(m, e, d, dist, modus, zahl, xeb, ROBUST)
                zeile["pf_robust"] = gf(rob[~np.isnan(rob)])
            if n >= min_trades:
                s, g, v = zwillinge(m, tw[gen], lam[gen], d[gen], dist[gen], modus, zahl, xeb, nacht[gen])
                sd = float(s.std())
                zeile.update(zw_mittel=float(s.mean()), zw_sd=sd,
                             z=(float(rr.sum()) - float(s.mean())) / sd if sd > 0 else None,
                             rang_pct=float((s < rr.sum()).mean() * 100),
                             zw_pf12=float((g >= float(P["auswahl"]["min_gewinnfaktor"]) * v).mean()))
            out.append(zeile)
    return out


def waehle_finalisten(tab: pd.DataFrame) -> tuple[list[dict], pd.DataFrame]:
    """Die Auswahl-Regel der VORAB-Datei. tab: eine Zeile je Variante (SPALTEN). Rückgabe: Finalisten in der
    Reihenfolge der Wahl, und die Tabelle der Zellen."""
    a = P["auswahl"]
    t = tab.copy()
    for sp in ("pf", "pf_robust", "z", "rang_pct", "median_halte_min"):
        t[sp] = pd.to_numeric(t[sp], errors="coerce")
    t["wertbar"] = (t["trades"] >= int(a["wertbar_min_trades"])) & t["z"].notna()
    t["quali"] = (t["wertbar"] & (t["pf"] >= float(a["min_gewinnfaktor"])) & (t["pf_robust"] >= float(a["min_robust"]))
                  & (t["rang_pct"] >= float(a["min_rang_pct"])))
    zeilen = []
    for (fam, eb, flt), g in t.groupby(["einstieg", "ebene", "filter"], sort=False):
        w = g[g["wertbar"]]
        q = g[g["quali"]].sort_values(["z", "pf", "key"], ascending=[False, False, True])
        zelle = {"einstieg": fam, "ebene": eb, "filter": flt, "varianten": int(len(g)), "wertbar": int(len(w)),
                 "qualifiziert": int(len(q)), "zellwert": None, "zaehlt": False, "finalist": None, "schnell": False}
        if len(w) >= int(a["zelle_min_wertbar"]):
            zelle["zellwert"] = float(np.quantile(w["z"].to_numpy(float), float(a["zellwert_quantil"])))
            if len(q):
                f = q.iloc[0]
                zelle.update(zaehlt=True, finalist=f["key"],
                             schnell=bool(f["je_woche"] >= float(a["schnell"]["min_trades_je_woche"])
                                          and f["median_halte_min"] <= float(a["schnell"]["max_median_halte_tage"]) * 1440))
        zeilen.append(zelle)
    zt = pd.DataFrame(zeilen)
    kand = zt[zt["zaehlt"]].sort_values(["zellwert", "finalist"], ascending=[False, True])
    gewaehlt, je_fam = [], {}

    def nimm(z) -> None:
        gewaehlt.append(z["finalist"])
        je_fam[z["einstieg"]] = je_fam.get(z["einstieg"], 0) + 1

    def frei(z) -> bool:
        return z["finalist"] not in gewaehlt and je_fam.get(z["einstieg"], 0) < int(a["max_je_einstieg"])

    for _, z in kand[kand["schnell"]].iterrows():
        if len(gewaehlt) < int(a["plaetze_schnell"]) and frei(z):
            nimm(z)
    for _, z in kand.iterrows():
        if len(gewaehlt) < int(a["finalisten_max"]) and frei(z):
            nimm(z)
    zeile = t.set_index("key")
    zw = zt.set_index("finalist")
    out = []
    for key in gewaehlt:
        f = zeile.loc[key]
        out.append({"key": key, "einstieg": f["einstieg"], "ebene": f["ebene"], "filter": f["filter"],
                    "stop": f["stop"], "ausstieg": f["ausstieg"], "schnell": bool(zw.loc[key, "schnell"]),
                    "zellwert": round(float(zw.loc[key, "zellwert"]), 3), "trades": int(f["trades"]),
                    "je_woche": round(float(f["je_woche"]), 2), "pf": round(float(f["pf"]), 3),
                    "pf_robust": round(float(f["pf_robust"]), 3), "z": round(float(f["z"]), 3),
                    "rang_pct": round(float(f["rang_pct"]), 1),
                    "median_halte_min": round(float(f["median_halte_min"]), 1)})
    return out, zt


def zufalls_zaehlung(tab: pd.DataFrame) -> list[dict]:
    """Je Einstiegs-Art: wertbare Varianten mit Gewinnfaktor ab 1,2, echt und im Mittel der Zwillings-Läufe."""
    a = P["auswahl"]
    t = tab.copy()
    for sp in ("pf", "pf_robust", "z", "rang_pct", "zw_pf12"):
        t[sp] = pd.to_numeric(t[sp], errors="coerce")
    w = t[(t["trades"] >= int(a["wertbar_min_trades"])) & t["z"].notna()]
    out = []
    for fam in [*P["einstiege"], "alle"]:
        g = w if fam == "alle" else w[w["einstieg"] == fam]
        alle = t if fam == "alle" else t[t["einstieg"] == fam]
        quali = ((g["pf"] >= float(a["min_gewinnfaktor"])) & (g["pf_robust"] >= float(a["min_robust"]))
                 & (g["rang_pct"] >= float(a["min_rang_pct"])))
        out.append({"einstieg": fam, "varianten": int(len(alle)), "wertbar": int(len(g)),
                    "pf_ab_1_2": int((g["pf"] >= float(a["min_gewinnfaktor"])).sum()),
                    "zufall_pf_ab_1_2": round(float(g["zw_pf12"].sum()), 1),
                    "rang_ab_90": int((g["rang_pct"] >= float(a["min_rang_pct"])).sum()),
                    "zufall_rang_ab_90": round(len(g) * (100 - float(a["min_rang_pct"])) / 100, 1),
                    "qualifiziert": int(quali.sum())})
    return out


def _abstand(ebene: str, name: str) -> tuple[str, int | None]:
    """Aus "atr2_15m" oder "trail_atr_1h" die Art und den Abstand der Ebene zur Einstiegs-Ebene (None: ohne Ebene)."""
    art, _, letzte = name.rpartition("_")
    if letzte in LEITER:
        return art, LEITER.index(letzte) - LEITER.index(ebene)
    return name, None


def karte(tab: pd.DataFrame) -> dict:
    """Auskunft aus der Auswahl-Hälfte: was lief zusammen gut? Nur wertbare Varianten, kein Test."""
    a = P["auswahl"]
    t = tab.copy()
    for sp in ("pf", "z", "rang_pct"):
        t[sp] = pd.to_numeric(t[sp], errors="coerce")
    w = t[(t["trades"] >= int(a["wertbar_min_trades"])) & t["z"].notna()].copy()
    if not len(w):
        return {}
    for sp, quelle in (("stop", "stop"), ("ausstieg", "ausstieg")):
        teile = [_abstand(eb, name) for eb, name in zip(w["ebene"], w[quelle])]
        w[f"{sp}_art"] = [x[0] for x in teile]
        w[f"{sp}_abstand"] = [-1 if x[1] is None else x[1] for x in teile]

    def gruppe(spalten: list[str]) -> list[dict]:
        out = []
        for key, g in w.groupby(spalten, sort=False):
            key = key if isinstance(key, tuple) else (key,)
            out.append({**{s: (int(k) if isinstance(k, (int, np.integer)) else k) for s, k in zip(spalten, key)},
                        "wertbar": int(len(g)), "pf_median": round(float(g["pf"].median()), 2),
                        "z_median": round(float(g["z"].median()), 2),
                        "rang_ab_90_pct": round(float((g["rang_pct"] >= float(a["min_rang_pct"])).mean() * 100), 1)})
        return out

    return {"einstieg_ebene": gruppe(["einstieg", "ebene"]), "filter": gruppe(["filter"]),
            "stop": gruppe(["stop_art", "stop_abstand"]), "ausstieg": gruppe(["ausstieg_art", "ausstieg_abstand"])}


def lade_markt(ordner: pathlib.Path, von, bis) -> Markt:
    """Markt aus dem Datenordner, Kerzen von `von` bis vor `bis`."""
    ordner = pathlib.Path(ordner)
    von, bis = pd.Timestamp(von), pd.Timestamp(bis)
    gold = lies_gold(ordner)
    gold = gold[(gold.index >= von) & (gold.index < bis)]
    fremd = {}
    for name in P["daten"]["andere_maerkte"]:
        df = lies_fremd(ordner, name)
        fremd[name] = df[(df.index >= von) & (df.index < bis)]
    tage, werte = lies_realzins(ordner)
    ok = tage < np.datetime64(bis, "D")
    termine = lies_termine()
    termine = termine[(termine >= np.datetime64(von, "ns")) & (termine < np.datetime64(bis, "ns"))]
    return markt(gold, fremd, (tage[ok], werte[ok]), termine)


def daten_siegel(ordner: pathlib.Path) -> dict:
    ordner = pathlib.Path(ordner)
    namen = ["XAUUSD_1min_utc.csv.gz", "DFII10.csv", *[f"{x}_5min.csv.gz" for x in P["daten"]["andere_maerkte"]]]
    return {n: sha256_datei(ordner / n)[:16] for n in namen}


def lauf_auswahl(ordner: pathlib.Path, arbeit: pathlib.Path) -> int:
    from suche.runde1 import sha256_text
    arbeit.mkdir(parents=True, exist_ok=True)
    a = P["auswahl"]
    t0 = time.time()
    m = lade_markt(ordner, VORLAUF_AB, MITTE + NACHLAUF)
    print(f"Markt geladen: {len(m)} Kerzen bis {pd.Timestamp(m.t[-1])}, {time.time() - t0:.0f} s, numba {SCHNELL}", flush=True)
    for fam, p in P["einstiege"].items():
        for eb in p["zeitebenen"]:
            ziel = arbeit / f"auswahl_{fam}_{eb}.csv"
            if ziel.exists():
                continue
            t1 = time.time()
            zeilen = []
            for flt in FILTER:
                zeilen += auswahl_zelle(m, fam, eb, flt, HAUPT_VON, MITTE, int(a["verschiebungen"]),
                                        int(a["wertbar_min_trades"]))
            pd.DataFrame(zeilen, columns=SPALTEN).to_csv(ziel, index=False)
            print(f"{fam} {eb}: {len(zeilen)} Varianten, {time.time() - t1:.0f} s", flush=True)
    teile = [pd.read_csv(arbeit / f"auswahl_{fam}_{eb}.csv") for fam, p in P["einstiege"].items() for eb in p["zeitebenen"]]
    tab = pd.concat(teile, ignore_index=True)
    if len(tab) != int(P["varianten"]):
        raise SystemExit(f"{len(tab)} Varianten gerechnet, erwartet {P['varianten']}")
    gesamt = arbeit / "auswahl_varianten.csv.gz"
    tab.to_csv(gesamt, index=False)
    fin, zt = waehle_finalisten(tab)
    zt.to_csv(arbeit / "auswahl_zellen.csv", index=False)
    vorab_sha = sha256_text(VORAB.read_text(encoding="utf-8"))
    kopf = ("# Finalisten der Gold-Matrix. Gewählt nur aus der Auswahl-Hälfte (Einstieg 01.01.2024 bis vor "
            f"{P['fenster']['mitte']} UTC)\n# nach der Regel in suche/VORAB_gold_matrix.yaml, Abschnitt auswahl. "
            "Die Bestätigungs-Hälfte war dabei nicht geladen.\n# Diese Datei wird versiegelt, bevor die "
            "Bestätigungs-Hälfte gerechnet wird, und danach nie geändert.\n\n")
    inhalt = {"format": 1, "gold_matrix_finalisten": {
        "vorab_sha256": vorab_sha, "varianten_gerechnet": int(len(tab)), "zellen_die_zaehlen": int(zt["zaehlt"].sum()),
        "tabelle_sha256": sha256_datei(gesamt), "finalisten": fin}}
    FINALISTEN.write_text(kopf + yaml.safe_dump(inhalt, allow_unicode=True, sort_keys=False, width=110), encoding="utf-8")
    res = {"vorab_sha256": vorab_sha, "daten": daten_siegel(ordner), "kerzen": [str(pd.Timestamp(m.t[0])), str(pd.Timestamp(m.t[-1]))],
           "varianten": int(len(tab)), "zellen": int(len(zt)), "zellen_die_zaehlen": int(zt["zaehlt"].sum()),
           "finalisten": fin, "zufalls_zaehlung": zufalls_zaehlung(tab), "karte": karte(tab),
           "zellen_tabelle": json.loads(zt.sort_values("zellwert", ascending=False).head(60).to_json(orient="records"))}
    ERGEBNIS.with_name(ERGEBNIS.name + "_auswahl.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Auswahl fertig: {len(fin)} Finalisten aus {int(zt['zaehlt'].sum())} Zellen, {time.time() - t0:.0f} s")
    for f in fin:
        print(f["key"], f["trades"], f["pf"], f["z"], f["rang_pct"], "schnell" if f["schnell"] else "")
    return 0


# ---------------------------------------------------------------------------------------------------------------------
# Bestätigung (zweite Hälfte) und Auskunft

def trades_von(m: Markt, f: dict, von, bis, faktor: float = 1.0) -> pd.DataFrame:
    """Alle Trades eines Finalisten im Fenster als Tabelle."""
    stops = {name: (art, seb) for name, art, seb in stop_liste(f["ebene"])}
    aust = {name: (modus, zahl, xeb) for name, modus, zahl, xeb in ausstieg_liste(f["ebene"])}
    art, seb = stops[f["stop"]]
    modus, zahl, xeb = aust[f["ausstieg"]]
    e, d = einstiege(m, f["einstieg"], f["ebene"])
    ok = im_fenster(m, e, von, bis)
    e, d = e[ok], d[ok]
    ok = filter_maske(m, f["filter"], f["ebene"], e, d)
    e, d = np.ascontiguousarray(e[ok]), np.ascontiguousarray(d[ok])
    dist = np.ascontiguousarray(stop_abstand(m, art, seb, e, d))
    r, aus, grund = rechne(m, e, d, dist, modus, zahl, xeb, faktor)
    gen = ~np.isnan(r)
    return pd.DataFrame({"e": e[gen], "zeit": m.t[e[gen]], "d": d[gen], "r_usd": dist[gen], "r": r[gen],
                         "zeit_aus": m.t[aus[gen]], "halte_min": m.tmin[aus[gen]] - m.tmin[e[gen]],
                         "grund": [GRUND[int(g)] for g in grund[gen]]})


def _teil(tr: pd.DataFrame, von, bis) -> pd.DataFrame:
    return tr[(tr["zeit"] >= pd.Timestamp(von)) & (tr["zeit"] < pd.Timestamp(bis))]


def _pf_n(tr: pd.DataFrame) -> tuple:
    k = kennzahlen(tr["r"].to_numpy())
    return (k["pf"], k["trades"])


def bewerte_finalist(m: Markt, f: dict, laeufe: int | None = None) -> tuple[dict, pd.DataFrame]:
    """Ein Finalist über das ganze Hauptfenster, Zwillinge nur für die Trades der Bestätigungs-Hälfte. Ohne `laeufe`
    zählen alle Verschiebungen."""
    tr = trades_von(m, f, HAUPT_VON, HAUPT_BIS)
    rob = trades_von(m, f, HAUPT_VON, HAUPT_BIS, ROBUST)
    wochen = (HAUPT_BIS - HAUPT_VON) / pd.Timedelta(days=7)
    k = kennzahlen(tr["r"].to_numpy())
    h2 = _teil(tr, MITTE, HAUPT_BIS)
    b = {**k, "je_woche": round(k["trades"] / wochen, 2), "robust_pf": kennzahlen(rob["r"].to_numpy())["pf"],
         "h1": _pf_n(_teil(tr, HAUPT_VON, MITTE)), "h2": _pf_n(h2), "j2026": _pf_n(_teil(tr, "2026-01-01", HAUPT_BIS)),
         "long": kennzahlen(tr.loc[tr["d"] > 0, "r"].to_numpy()), "short": kennzahlen(tr.loc[tr["d"] < 0, "r"].to_numpy()),
         "je_jahr": {str(j): round(float(tr.loc[tr["zeit"].dt.year == j, "r"].sum()), 1) for j in (2024, 2025, 2026)},
         "letzte_2_jahre": kennzahlen(_teil(tr, "2024-11-01", HAUPT_BIS)["r"].to_numpy()),
         "median_halte_min": float(tr["halte_min"].median()) if len(tr) else None,
         "spread_r": round(float((SPREAD / tr["r_usd"]).mean()), 3) if len(tr) else None,
         "ohne_top3_r": round(float(np.sort(tr["r"].to_numpy())[:-3].sum()), 1) if len(tr) > 3 else None,
         "gruende": {str(g): int(n) for g, n in tr["grund"].value_counts().items()}}
    if len(h2):
        modus, zahl, xeb = {name: (mo, za, xe) for name, mo, za, xe in ausstieg_liste(f["ebene"])}[f["ausstieg"]]
        e = h2["e"].to_numpy(np.int64)
        seb = {name: eb for name, _, eb in stop_liste(f["ebene"])}[f["stop"]]
        d, dist = h2["d"].to_numpy(np.int64), h2["r_usd"].to_numpy(float)
        kal = kalender(m, MITTE, HAUPT_BIS)
        tw = verschiebe(kal, e, schritte(kal.tage, laeufe))
        s, _, _ = zwillinge(m, tw, vola_faktor(m, seb, e, tw), d, dist, modus, zahl, xeb, nacht_r(m, e, d, dist))
        echt, sd = float(h2["r"].sum()), float(s.std())
        b["zufall"] = {"geschlagen_pct": round(float((s < echt).mean() * 100), 2),
                       "p": float((1 + (s >= echt).sum()) / (len(s) + 1)),
                       "z": round((echt - float(s.mean())) / sd, 3) if sd > 0 else None,
                       "median_r": round(float(np.median(s)), 1), "echt_r": round(echt, 1), "laeufe": int(len(s))}
    else:
        b["zufall"] = {"geschlagen_pct": None, "p": 1.0, "z": None, "median_r": None, "echt_r": 0.0, "laeufe": 0}
    return b, tr


def urteil_finalist(b: dict, holm_ok: bool) -> tuple[str, list[str]]:
    """Urteil eines Finalisten: bestanden braucht alle Hürden, Holm und z ab der Schwelle. Wer nur an Holm oder z
    scheitert, ist Kandidat, und das zählt als nicht bestanden."""
    from suche.nachpruefung_2024_26 import urteil
    bst = P["bestaetigung"]
    zufall_ok = (b["zufall"]["geschlagen_pct"] or 0) >= float(bst["min_rang_pct"])
    ok, fehlt = urteil({"trades": b["trades"], "pf": b["pf"], "robust_pf": b["robust_pf"], "h1": b["h1"],
                        "h2": b["h2"], "j2026": b["j2026"], "zufall": zufall_ok})
    z = b["zufall"].get("z")
    z_ok = z is not None and z >= float(bst["min_z"])
    if ok and not holm_ok:
        fehlt = fehlt + ["Holm"]
    if ok and not z_ok:
        fehlt = fehlt + [f"z unter {_z(float(bst['min_z']), 1)}"]
    return ("bestanden" if ok and holm_ok and z_ok else "kandidat" if ok else "durchgefallen"), fehlt


def kombi(listen: list[pd.DataFrame]) -> dict:
    """Mehrere Finalisten als eine Liste von Trades in R, nach Ausstiegszeit geordnet."""
    if not listen:
        return kennzahlen(np.array([]))
    alle = pd.concat(listen, ignore_index=True).sort_values("zeit_aus")
    wochen = (HAUPT_BIS - HAUPT_VON) / pd.Timedelta(days=7)
    k = kennzahlen(alle["r"].to_numpy())
    return {**k, "je_woche": round(k["trades"] / wochen, 2),
            "je_jahr": {str(j): round(float(alle.loc[alle["zeit"].dt.year == j, "r"].sum()), 1) for j in (2024, 2025, 2026)}}


def lauf_bestaetigung(ordner: pathlib.Path, arbeit: pathlib.Path) -> int:
    from suche.runde1 import sha256_text
    arbeit.mkdir(parents=True, exist_ok=True)
    fin = yaml.safe_load(FINALISTEN.read_text(encoding="utf-8"))["gold_matrix_finalisten"]
    liste = fin["finalisten"]
    bst = P["bestaetigung"]
    t0 = time.time()
    res = {"vorab_sha256": sha256_text(VORAB.read_text(encoding="utf-8")),
           "finalisten_sha256": sha256_text(FINALISTEN.read_text(encoding="utf-8")), "daten": daten_siegel(ordner),
           "numba": SCHNELL, "finalisten": {}}
    auswahl = ERGEBNIS.with_name(ERGEBNIS.name + "_auswahl.json")
    if auswahl.exists():
        aw = json.loads(auswahl.read_text(encoding="utf-8"))
        res.update(varianten=aw["varianten"], zellen=aw["zellen"], zellen_die_zaehlen=aw["zellen_die_zaehlen"],
                   zufalls_zaehlung=aw["zufalls_zaehlung"], karte=aw.get("karte", {}))
    trades = {}
    if liste:
        m = lade_markt(ordner, VORLAUF_AB, pd.Timestamp("2100-01-01"))
        res["kerzen"] = [str(pd.Timestamp(m.t[0])), str(pd.Timestamp(m.t[-1]))]
        for f in liste:
            b, tr = bewerte_finalist(m, f, None if bst["verschiebungen"] == "alle" else int(bst["verschiebungen"]))
            b["auswahl"] = {k: f[k] for k in ("schnell", "zellwert", "trades", "pf", "z", "rang_pct")}
            b.update({k: f[k] for k in ("einstieg", "ebene", "filter", "stop", "ausstieg")})
            res["finalisten"][f["key"]] = b
            trades[f["key"]] = tr
            tr.drop(columns=["e"]).to_csv(arbeit / f"trades_{f['key']}.csv", index=False)
            print(f["key"], b["trades"], b["pf"], b["h2"], b["zufall"], f"{time.time() - t0:.0f} s", flush=True)
        del m
        hm = holm({k: b["zufall"]["p"] for k, b in res["finalisten"].items()}, float(bst["holm_alpha"]))
        for key, b in res["finalisten"].items():
            b["holm"] = bool(hm[key])
            b["urteil"], b["fehlt"] = urteil_finalist(b, b["holm"])
        # Auskunft: ältere Jahre und die letzten 4 Jahre als eigene Läufe mit eigenem Vorlauf
        for name, daten_von, von, bis in (("alt_2016_2023", "2015-01-01", "2016-01-01", "2024-01-01"),
                                          ("letzte_4_jahre", "2021-11-01", "2022-11-01", HAUPT_BIS)):
            m = lade_markt(ordner, daten_von, pd.Timestamp(bis) + NACHLAUF)
            for f in liste:
                tr = trades_von(m, f, von, bis)
                wochen = (pd.Timestamp(bis) - pd.Timestamp(von)) / pd.Timedelta(days=7)
                k = kennzahlen(tr["r"].to_numpy())
                res["finalisten"][f["key"]][name] = {**k, "je_woche": round(k["trades"] / wochen, 2)}
            del m
            print("Auskunft", name, f"{time.time() - t0:.0f} s", flush=True)
        gut = [k for k, b in res["finalisten"].items() if b["urteil"] == "bestanden"]
        kand = [k for k, b in res["finalisten"].items() if b["urteil"] == "kandidat"]
        res["kombi"] = {"bestanden": kombi([trades[k] for k in gut]),
                        "bestanden_und_kandidaten": kombi([trades[k] for k in gut + kand])}
    ERGEBNIS.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n",
                                             encoding="utf-8")
    ERGEBNIS.with_suffix(".md").write_text(bericht(res), encoding="utf-8")
    print(bericht(res))
    return 0


# ---------------------------------------------------------------------------------------------------------------------
# Bericht

def _z(x, n: int = 2) -> str:
    return "–" if x is None or (isinstance(x, float) and x != x) else f"{x:.{n}f}".replace(".", ",")


def _halte(minuten) -> str:
    if minuten is None:
        return "–"
    if minuten < 120:
        return f"{_z(minuten, 0)} Min."
    if minuten < 2880:
        return f"{_z(minuten / 60, 1)} Std."
    return f"{_z(minuten / 1440, 1)} Tage"


URTEIL_TEXT = {"bestanden": "bestanden", "kandidat": "Kandidat", "durchgefallen": "durchgefallen"}


def bericht(res: dict) -> str:
    fin = res["finalisten"]
    reihe = sorted(fin, key=lambda k: ({"bestanden": 0, "kandidat": 1, "durchgefallen": 2}[fin[k]["urteil"]],
                                       -fin[k]["je_woche"]))
    n_gut = sum(b["urteil"] == "bestanden" for b in fin.values())
    n_kand = sum(b["urteil"] == "kandidat" for b in fin.values())
    z = ["# Gold-Matrix: Ergebnis", "",
         f"Regeln: suche/VORAB_gold_matrix.yaml (Prüfsumme {res['vorab_sha256'][:8]} im Protokoll, festgelegt vor der "
         f"Rechnung). Finalisten: suche/VORAB_gold_matrix_finalisten.yaml (Prüfsumme {res['finalisten_sha256'][:8]}, "
         "festgelegt vor der Bestätigung).",
         "Daten: XAUUSD 1 Min. (HistData, echte UTC), Spread 0,50 USD, Übernachtgebühr eingerechnet. "
         "Hauptfenster: Einstieg 01.01.2024 bis 30.10.2026, Auswahl bis 31.05.2025, Bestätigung danach.", "",
         f"Gerechnet: {res.get('varianten', '–')} Varianten in {res.get('zellen', '–')} Zellen. "
         f"{res.get('zellen_die_zaehlen', '–')} Zellen schafften die Auswahl-Hürden, {len(fin)} Finalisten kamen in die "
         f"Bestätigung. Bestanden: {n_gut}. Kandidaten: {n_kand}. Durchgefallen: {len(fin) - n_gut - n_kand}.", ""]
    if not fin:
        z += ["Keine Zelle schaffte die Auswahl-Hürden. Es gibt keinen Finalisten, die Bestätigungs-Hälfte blieb ungeöffnet.", ""]
    else:
        z += ["## Finalisten im Hauptfenster", "",
              "| Finalist | Urteil | Trades | je Woche | Gewinnfaktor | Summe R | Treffer | 1,5x Kosten | Hälfte 1 | "
              "Hälfte 2 | 2026 | Zufall Hälfte 2 | p | Holm | z |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for k in reihe:
            b = fin[k]
            z.append(f"| {k} | {URTEIL_TEXT[b['urteil']]} | {b['trades']} | {_z(b['je_woche'])} | {_z(b['pf'])} | "
                     f"{_z(b['summe_r'], 1)} | {_z(b['treffer'], 0)} % | {_z(b['robust_pf'])} | "
                     f"{_z(b['h1'][0])} ({b['h1'][1]}) | {_z(b['h2'][0])} ({b['h2'][1]}) | {_z(b['j2026'][0])} ({b['j2026'][1]}) | "
                     f"{_z(b['zufall']['geschlagen_pct'], 1)} % | {_z(b['zufall']['p'], 4)} | {'ja' if b['holm'] else 'nein'} | "
                     f"{_z(b['zufall'].get('z'))} |")
        z += ["", "Was fehlt, je Finalist:", ""]
        for k in reihe:
            z.append(f"- {k}: {', '.join(fin[k]['fehlt']) if fin[k]['fehlt'] else 'nichts'}")
        z += ["", "## Auskunft", "",
              "| Finalist | in der Auswahl (Trades, GF, z) | Long (Trades, GF, R) | Short (Trades, GF, R) | Haltezeit Mitte | "
              "größter Rückgang | Spread je Trade | 2024, 2025, 2026 in R | ohne die 3 größten | letzte 2 Jahre (Trades, GF, R) | "
              "letzte 4 Jahre (Trades, GF, R) | 2016 bis 2023 (Trades, GF, R) |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for k in reihe:
            b = fin[k]

            def drei(x: dict | None) -> str:
                return "–" if not x else f"{x['trades']}, {_z(x['pf'])}, {_z(x['summe_r'], 1)}"
            a = b["auswahl"]
            z.append(f"| {k} | {a['trades']}, {_z(a['pf'])}, {_z(a['z'])} | {drei(b['long'])} | {drei(b['short'])} | "
                     f"{_halte(b['median_halte_min'])} | {_z(b['rueckgang_r'], 1)} R | {_z(b['spread_r'])} R | "
                     f"{', '.join(_z(b['je_jahr'][j], 1) for j in ('2024', '2025', '2026'))} | {_z(b['ohne_top3_r'], 1)} R | "
                     f"{drei(b['letzte_2_jahre'])} | {drei(b.get('letzte_4_jahre'))} | {drei(b.get('alt_2016_2023'))} |")
        z.append("")
        for name, titel in (("bestanden", "Alle bestandenen zusammen"),
                            ("bestanden_und_kandidaten", "Bestandene und Kandidaten zusammen")):
            kb = res.get("kombi", {}).get(name)
            if kb and kb["trades"]:
                z.append(f"{titel}: {kb['trades']} Trades ({_z(kb['je_woche'])} je Woche), Gewinnfaktor {_z(kb['pf'])}, "
                         f"Summe {_z(kb['summe_r'], 1)} R, größter Rückgang {_z(kb['rueckgang_r'], 1)} R, je Jahr "
                         f"{', '.join(_z(kb['je_jahr'][j], 1) for j in ('2024', '2025', '2026'))} R.")
        z.append("")
    if res.get("zufalls_zaehlung"):
        z += ["## Zufalls-Zählung in der Auswahl-Hälfte", "",
              "Wie viele Varianten sehen gut aus, und wie viele wären es, wenn man die Strategie um Tage verschiebt?", "",
              "| Einstieg | Varianten | wertbar (ab 50 Trades) | Gewinnfaktor ab 1,2 | davon mit Zufall erwartet | "
              "schlägt 90 % der Zwillinge | davon mit Zufall erwartet | alle Hürden |", "|---|---|---|---|---|---|---|---|"]
        for q in res["zufalls_zaehlung"]:
            z.append(f"| {q['einstieg']} | {q['varianten']} | {q['wertbar']} | {q['pf_ab_1_2']} | "
                     f"{_z(q['zufall_pf_ab_1_2'], 1)} | {q['rang_ab_90']} | {_z(q['zufall_rang_ab_90'], 1)} | {q['qualifiziert']} |")
        z.append("")
    if res.get("karte"):
        ka = res["karte"]
        ab = {-1: "–", 0: "Ebene des Einstiegs", 1: "eine Ebene höher", 2: "zwei Ebenen höher", 3: "drei Ebenen höher"}
        kopf = "wertbar | Gewinnfaktor Mitte | z Mitte | schlägt 90 % der Zwillinge |"
        werte = lambda q: f"{q['wertbar']} | {_z(q['pf_median'])} | {_z(q['z_median'])} | {_z(q['rang_ab_90_pct'], 1)} % |"
        z += ["## Karte der Auswahl-Hälfte", "",
              "Was lief zusammen gut? Nur Varianten mit mindestens 50 Trades, nur die Auswahl-Hälfte (01.01.2024 bis "
              "31.05.2025). Das ist Auskunft und kein Test: Mit reinem Zufall schlagen 10 % der Varianten 90 % ihrer "
              "Zwillinge, und z liegt bei 0.", "",
              f"| Einstieg | Zeitebene | {kopf}", "|---|---|---|---|---|---|"]
        z += [f"| {q['einstieg']} | {q['ebene']} | {werte(q)}" for q in ka["einstieg_ebene"]]
        z += ["", f"| Filter | {kopf}", "|---|---|---|---|---|"]
        z += [f"| {q['filter']} | {werte(q)}" for q in ka["filter"]]
        z += ["", f"| Stop | Stop-Ebene | {kopf}", "|---|---|---|---|---|---|"]
        z += [f"| {q['stop_art']} | {ab[q['stop_abstand']]} | {werte(q)}" for q in ka["stop"]]
        z += ["", f"| Ausstieg | Ausstiegs-Ebene | {kopf}", "|---|---|---|---|---|---|"]
        z += [f"| {q['ausstieg_art']} | {ab[q['ausstieg_abstand']]} | {werte(q)}" for q in ka["ausstieg"]]
        z.append("")
    laeufe = max([b["zufall"]["laeufe"] for b in fin.values()], default=0)
    z += ["Bestanden heißt: alle Hürden aus suche/VORAB_bewertung_2024_26.yaml im Hauptfenster (mindestens 100 Trades, "
          "Gewinnfaktor ab 1,2, mit 1,5-fachen Kosten ab 1,0, beide Hälften und 2026 über 1,0), in der "
          "Bestätigungs-Hälfte mindestens 95 % der Zwillings-Läufe geschlagen, Holm über alle Finalisten und z ab "
          f"{_z(float(P['bestaetigung']['min_z']), 1)} (die Summe liegt so viele Standardabweichungen über dem Mittel "
          "der Läufe). Kandidat heißt: alles außer Holm oder z, das zählt als nicht bestanden. Ein Zwillings-Lauf ist "
          "die ganze Strategie, "
          "als Block um ganze Handelstage nach vorn verschoben: jeder Trade in dieselbe Richtung, zur selben Uhrzeit in "
          "New York, mit demselben Ausstieg. Stop-Abstand und Kosten sind an die Schwankung am neuen Tag angepasst. "
          f"Jede mögliche Verschiebung ist ein Lauf{f' (hier {laeufe})' if laeufe else ''}. Bei {len(fin)} Finalisten ohne "
          f"echten Vorteil schaffen im Mittel {_z(len(fin) * 0.05, 1)} die 95 % nur durch Glück. Keine Nachbesserung "
          "nach dem Ergebnis.", ""]
    return "\n".join(z)


def main(argv: list[str]) -> int:
    from suche.runde1 import journal_add, sha256_text
    if argv[:1] == ["--festlegen"]:
        journal_add(f"{argv[1]} VORAB_gold_matrix sha256 {sha256_text(VORAB.read_text(encoding='utf-8'))}")
        return 0
    if argv[:1] == ["--festlegen-finalisten"]:
        journal_add(f"{argv[1]} VORAB_gold_matrix_finalisten sha256 {sha256_text(FINALISTEN.read_text(encoding='utf-8'))}")
        return 0
    if not vorab_ok():
        raise SystemExit("suche/VORAB_gold_matrix.yaml steht so nicht im Protokoll. Erst --festlegen \"Grund\".")
    if len(argv) != 3 or argv[0] not in ("auswahl", "bestaetigung"):
        raise SystemExit(__doc__)
    ordner, arbeit = pathlib.Path(argv[1]), pathlib.Path(argv[2])
    if argv[0] == "auswahl":
        if FINALISTEN.exists():
            raise SystemExit("Die Finalisten stehen schon fest (suche/VORAB_gold_matrix_finalisten.yaml). Die Auswahl läuft nur einmal.")
        return lauf_auswahl(ordner, arbeit)
    if not finalisten_ok():
        raise SystemExit("Die Finalisten stehen so nicht im Protokoll. Erst --festlegen-finalisten \"Grund\".")
    return lauf_bestaetigung(ordner, arbeit)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
