"""Große Runde vom 19.11.2026: Regeln mit anderer Information als dem Kurs, Kirons Geduld-Idee und zwei Vorhersage-Modelle.

Regeln: suche/VORAB_grosse_runde.yaml (Durchgang 1) und suche/VORAB_grosse_runde2.yaml (Durchgang 2), jede versiegelt im
Protokoll, bevor mit Kursen ab 2024 gerechnet wurde. Die Rechnung (Kosten, ein Trade, Zwillinge, Hürden) ist die von
suche/rueckblick.py. Neu sind hier:

- Regeln, die Termine, den VIX, Zinsen und Finanzierungssätze lesen (nur Werte, die vor dem Handelstag feststanden),
- ein Trade mit Zielen in Stufen für Kirons Idee "Verlierer halten, bis sie zurückkommen" (nur Long, Marktorder),
- ein Vorhersage-Modell (logistische Regression), das jedes Jahr nur mit älteren Jahren neu gelernt wird,
- Holm mit einer festen Gesamtzahl über beide Durchgänge (huerden.holm_anzahl),
- in Durchgang 2 dazu: eine Reihe gegen ihr eigenes Quantil (DIX), der Geduld-Ausstieg nach einem VIX-Sprung, der
  Schub der letzten halben Stunde, runde Marken bei Devisen, die Umkehr nach dem Fonds-Fenster bei Bitcoin und zwei
  seltene Regeln mit fester Eröffnung (Tokio nach einem US-Schreck, der Morgen des Verfallstags).

Aufruf (N ist der Durchgang, 1 oder 2):
    python -m suche.grosse_runde N --festlegen                 schreibt die Prüfsumme der Regeldatei ins Protokoll
    python -m suche.grosse_runde N entwicklung <Arbeit>        nur Kurse bis Ende 2023, prüft das Programm, kein Ergebnis
    python -m suche.grosse_runde N probelauf <Arbeit> <Saat>   ganze Rechnung auf erfundenen Märkten ohne Vorteil
    python -m suche.grosse_runde N rechnen <Arbeit>            die Rechnung (nur mit passender Prüfsumme)

Die Kursdateien baut python -m suche.youtube_runde2 daten <Arbeit>, dazu python -m suche.rueckblick_daten <Arbeit>
für die übrigen Devisen. FRED-Reihen und Finanzierungssätze liegen im Projektordner (siehe Regeldatei, daten.fremd).
"""
from __future__ import annotations

import functools
import contextlib
import io
import pathlib
import sys
import zipfile

import numpy as np
import pandas as pd
import yaml

from suche import rueckblick as rb
from suche import youtube_runde as yr
from suche import youtube_runde2 as y2
from suche.rueckblick import njit
from suche.runde1 import journal_add, journal_lines, last_value, sha256_text

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATEIEN = {1: "grosse_runde", 2: "grosse_runde2"}
FRED = pathlib.Path("/mnt/project-files/strategie-suche/daten/fred")
FUNDING = pathlib.Path("/mnt/project-files/strategie-suche/daten/krypto/funding")
FREMD = {"DIX": (pathlib.Path("/mnt/project-files/strategie-suche/daten/squeezemetrics/DIX.csv"), "dix")}   # Reihe -> (Datei, Spalte)
NY = rb.NY
MIN = rb.MIN
_ECHTE_TRADES, _ZWILLINGS_SUMMEN = rb.echte_trades, rb.zwillings_summen     # die unveränderten Funktionen


def vorab(nr: int) -> pathlib.Path:
    return ROOT / "suche" / f"VORAB_{DATEIEN[nr]}.yaml"


def schluessel(nr: int) -> str:
    return f"VORAB_{DATEIEN[nr]} sha256 "


def lade_vorab(nr: int = 1, pruefen: bool = True) -> dict:
    text = vorab(nr).read_text(encoding="utf-8")
    if pruefen and last_value(journal_lines(), schluessel(nr)) != sha256_text(text):
        raise SystemExit(f"{vorab(nr).name} passt nicht zur Prüfsumme im Protokoll. Erst versiegeln, dann rechnen.")
    return yaml.safe_load(text)["grosse_runde"]


# ---------------------------------------------------------------------------------------------------------------------
# Markt: wie suche/youtube_runde.py (Krypto mit sieben Handelstagen). Er merkt sich, womit er gebaut wurde, damit eine
# Regel einen zweiten Markt mit denselben Kursen (und im Probelauf derselben Saat) dazuholen kann.

_MAERKTE: dict = {}


class Markt(yr.Markt):
    def __init__(self, sym: str, arbeit: pathlib.Path, cfg: dict, bis: str | None = None, saat: int | None = None):
        super().__init__(sym, arbeit, cfg, bis, saat)
        self.arbeit, self.cfg_, self.bis, self.saat = arbeit, cfg, bis, saat
        _MAERKTE[(sym, str(arbeit), bis, saat)] = self


def partner(m: Markt, sym: str) -> Markt:
    if sym == m.sym:
        return m
    key = (sym, str(m.arbeit), m.bis, m.saat)
    return _MAERKTE[key] if key in _MAERKTE else Markt(sym, m.arbeit, m.cfg_, m.bis, m.saat)


# ---------------------------------------------------------------------------------------------------------------------
# Fremde Reihen. Eine Regel bekommt für einen Handelstag nur Werte mit einem Datum strikt vor diesem Handelstag.

@functools.lru_cache(maxsize=None)
def fred(name: str) -> tuple[np.ndarray, np.ndarray]:
    if name in FREMD:
        datei, spalte = FREMD[name]
        df = pd.read_csv(datei)
        df = df[[df.columns[0], spalte]]
    else:
        df = pd.read_csv(FRED / f"{name}.csv")
    w = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    ok = w.notna().to_numpy()
    return df.iloc[:, 0].to_numpy("datetime64[D]")[ok], w.to_numpy(float)[ok]


def vor(name: str, tage: np.ndarray, k: int = 0, lag: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Letzter Wert der Reihe mit Datum strikt vor dem Handelstag (k = 0) oder k Beobachtungen davor.
    lag = 1 heißt: die Reihe erscheint einen Tag später, es zählt nur, was strikt vor dem Vortag liegt.
    Gibt (Wert, Datum) zurück, ohne Beobachtung nan und NaT."""
    d, w = fred(name)
    grenze = np.asarray(tage).astype("datetime64[D]") - np.timedelta64(lag, "D")
    i = np.searchsorted(d, grenze, side="left") - 1 - k
    ok = i >= 0
    ic = np.maximum(i, 0)
    return np.where(ok, w[ic], np.nan), np.where(ok, d[ic], np.datetime64("NaT", "D"))


@functools.lru_cache(maxsize=None)
def funding(binance: str) -> tuple[np.ndarray, np.ndarray]:
    """Finanzierungssätze der Dauer-Kontrakte von Binance (alle 8 Stunden). Zeit in UTC, Satz je 8 Stunden."""
    teile = []
    for pfad in sorted(FUNDING.glob(f"{binance}-fundingRate-*.zip")):
        with zipfile.ZipFile(pfad) as z:
            teile.append(pd.read_csv(io.BytesIO(z.read(z.namelist()[0]))))
    df = pd.concat(teile).drop_duplicates("calc_time").sort_values("calc_time")
    return pd.to_datetime(df["calc_time"].to_numpy(np.int64), unit="ms").values.astype("datetime64[ns]"), \
        df["last_funding_rate"].to_numpy(float)


def kalender() -> dict:
    roh = yaml.safe_load(rb.TERMINE.read_text(encoding="utf-8"))
    return {k: np.array(sorted(pd.Timestamp(t).date() for t in roh[k]["tage"]), dtype="datetime64[D]")
            for k in ("fomc", "cpi", "nfp")}


# ---------------------------------------------------------------------------------------------------------------------
# Ein Trade mit Zielen in Stufen (nur Long, Marktorder). Ohne Stufe rechnet er genau wie rueckblick._trade.

@njit(cache=True)
def _trade_stufen(o, h, l, c, sp, i0, sd, zd, iw1, z2, iw2, z3, imax, kf, rutsch):
    """Long zum Markt in Kerze i0. Bis Kerze iw1 gilt das Ziel zd über dem Bid beim Einstieg (wie rueckblick._trade).
    Ab iw1 liegt das Ziel bei Einstiegskurs plus z2, ab iw2 bei Einstiegskurs plus z3. z2 und z3 dürfen 0 oder negativ
    sein (Ausstieg auf Einstand oder mit kleinem Verlust). Liegt die Eröffnung der Wechsel-Kerze schon über dem neuen
    Ziel, zählt die Eröffnung. Der Stop gilt immer. Gibt (Ausstiegskerze, Ergebnis in Kurspunkten, Einstiegskurs)."""
    n = o.shape[0]
    s0 = sp[i0] * kf
    if imax <= i0:
        imax = i0 + 1
    ref = o[i0]
    e = ref + s0
    stop = ref - sd
    j = i0
    while True:
        if j >= n:
            return n - 1, c[n - 1] - e, e
        if j < iw1:
            ziel = ref + zd if zd > 0 else 1e300
        elif j < iw2:
            ziel = e + z2
        else:
            ziel = e + z3
        if j > i0:
            if j >= imax:
                return j, o[j] - e, e
            if o[j] <= stop:
                return j, o[j] - rutsch * sp[j] * kf - e, e
            if (j == iw1 or j == iw2) and o[j] >= ziel:
                return j, o[j] - e, e
        if l[j] <= stop:
            return j, stop - rutsch * sp[j] * kf - e, e
        if h[j] >= ziel:
            return j, ziel - e, e
        j += 1


@njit(cache=True)
def _viele_stufen(o, h, l, c, sp, i0, sd, zd, iw1, z2, iw2, z3, imax, kf, rutsch):
    m = i0.shape[0]
    ex, pnl, ein = np.empty(m, np.int64), np.empty(m), np.empty(m)
    for q in range(m):
        ex[q], pnl[q], ein[q] = _trade_stufen(o, h, l, c, sp, i0[q], sd[q], zd[q], iw1[q], z2[q], iw2[q], z3[q],
                                              imax[q], kf[q], rutsch)
    return ex, pnl, ein


def _wechsel(m: Markt, g: np.ndarray, cfg: dict) -> np.ndarray:
    """Kerze, mit der ein gültiger Handelstag nach der Pause beginnt (18:00 New York)."""
    g = np.minimum(np.asarray(g), len(m.gi) - 1)
    return np.searchsorted(m.t, m.t0[m.gi[g]] + np.timedelta64(cfg["daten"]["pause_min"], "m"))


def echte_trades(m: Markt, sig: list[dict], cfg: dict) -> pd.DataFrame:
    """Wie rueckblick.echte_trades. Signale mit dem Feld "stufen" = ((Tage1, z2), (Tage2, z3)) laufen mit Zielen in
    Stufen. Der Wechsel ist der Beginn des Handelstags g + Tage (g ist der Handelstag des Einstiegs)."""
    if not any("stufen" in s for s in sig):
        return _ECHTE_TRADES(m, sig, cfg)
    rutsch, rob = cfg["kosten"]["rutschen_spread"], cfg["kosten"]["robust_faktor"]
    rows, frei_ab = [], -1
    for s in sorted(sig, key=lambda x: x["i0"]):
        i0 = s["i0"]
        if i0 <= frei_ab or i0 >= m.n - 1:
            continue
        g = m.gpos[m.tix[i0]]
        if g < 1 or not np.isfinite(m.atr_vor[g]) or not (s["sd"] > 0) or s["d"] != 1:
            continue
        (w1, z2), (w2, z3) = s["stufen"]
        if g + w2 >= len(m.gi):
            continue
        imax = int(m.kerze_ab(np.array([s["t_max"]]))[0])
        iw1, iw2 = (int(x) for x in _wechsel(m, np.array([g + w1, g + w2]), cfg))
        ex, pnl, e = _trade_stufen(m.o, m.h, m.l, m.c, m.sp, i0, s["sd"], s["zd"], iw1, z2, iw2, z3, imax, 1.0, rutsch)
        ex2, pnl2, e2 = _trade_stufen(m.o, m.h, m.l, m.c, m.sp, i0, s["sd"], s["zd"], iw1, z2, iw2, z3, imax, rob, rutsch)
        fin = rb.gebuehr(m, cfg, [1], [e], np.array([i0]), np.array([ex]))[0]
        fin2 = rb.gebuehr(m, cfg, [1], [e2], np.array([i0]), np.array([ex2]))[0]
        frei_ab = ex
        tm = np.datetime64(s["t_max"], "ns")
        gx = m.gpos[m.tix[min(imax, m.n - 1)]]
        rows.append({"markt": m.sym, "ein_utc": m.t[i0], "aus_utc": m.t[ex], "richtung": 1,
                     "einstieg": e, "ausstieg": e + pnl, "stop_abstand": s["sd"], "ziel_abstand": s["zd"],
                     "R": (pnl - fin) / s["sd"], "R_robust": (pnl2 - fin2) / s["sd"], "gebuehr_R": fin / s["sd"],
                     "i0": i0, "g": int(g), "ab_ein": (m.t[i0] - m.t0[m.tix[i0]]) / MIN,
                     "tage_bis_aus": int(max(gx, g) - g),
                     "ab_aus": (tm - m.t0[m.gi[max(gx, g)]]) / MIN, "tag": m.tage[m.tix[i0]],
                     "w1": int(w1), "z2": float(z2), "w2": int(w2), "z3": float(z3)})
    return pd.DataFrame(rows)


def zwillings_summen(m: Markt, tr: pd.DataFrame, g_a: int, g_b: int, schritte: np.ndarray, cfg: dict) -> np.ndarray:
    """Wie rueckblick.zwillings_summen. Trades mit Zielen in Stufen wandern mit ihren Stufen (alle Abstände mal
    ATR am Zwilling geteilt durch ATR am echten Einstieg)."""
    if tr.empty or "z2" not in tr.columns:
        return _ZWILLINGS_SUMMEN(m, tr, g_a, g_b, schritte, cfg)
    out = np.zeros(len(schritte))
    n_fenster = g_b - g_a + 1
    g = tr["g"].to_numpy(np.int64)
    sd, zd = tr["stop_abstand"].to_numpy(float), tr["ziel_abstand"].to_numpy(float)
    z2, z3 = tr["z2"].to_numpy(float), tr["z3"].to_numpy(float)
    w1, w2 = tr["w1"].to_numpy(np.int64), tr["w2"].to_numpy(np.int64)
    ab_ein = (tr["ab_ein"].to_numpy(float) * 60e9).astype("timedelta64[ns]")
    ab_aus = (tr["ab_aus"].to_numpy(float) * 60e9).astype("timedelta64[ns]")
    weiter = tr["tage_bis_aus"].to_numpy(np.int64)
    rutsch = cfg["kosten"]["rutschen_spread"]
    spaet = np.timedelta64(cfg["zwilling"]["spaet_min"], "m")
    for q, k in enumerate(schritte):
        g2 = g_a + (g - g_a + int(k)) % n_fenster
        tag2 = m.gi[g2]
        t_ein = m.t0[tag2] + ab_ein
        i0 = np.searchsorted(m.t, t_ein)
        i0c = np.minimum(i0, m.n - 2)
        f = m.atr_vor[g2] / m.atr_vor[g]
        ok = (i0 < m.n - 1) & (m.tix[i0c] == tag2) & (m.t[i0c] - t_ein <= spaet) & np.isfinite(f) & (f > 0) \
            & (g2 + w2 < len(m.gi))
        if not ok.any():
            continue
        g_aus = np.minimum(g2 + weiter, len(m.gi) - 1)
        imax = np.searchsorted(m.t, m.t0[m.gi[g_aus]] + ab_aus)
        iw1, iw2 = _wechsel(m, g2 + w1, cfg), _wechsel(m, g2 + w2, cfg)
        i0k, fk = i0c[ok], f[ok]
        ex, pnl, ein = _viele_stufen(m.o, m.h, m.l, m.c, m.sp, i0k, sd[ok] * fk, zd[ok] * fk, iw1[ok], z2[ok] * fk,
                                     iw2[ok], z3[ok] * fk, imax[ok], fk, rutsch)
        fin = rb.gebuehr(m, cfg, np.ones(len(i0k), np.int64), ein, i0k, ex)
        out[q] = float(((pnl - fin) / (sd[ok] * fk)).sum())
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Regeln. Jede gibt Signale zurück wie in rueckblick.py: i0, d, sd, zd, t_max, dazu bei Bedarf stufen.

def tages_einstieg(m: Markt, cfg: dict) -> tuple[np.ndarray, np.ndarray]:
    """Je gültigem Handelstag die erste Kerze nach der Pause (ab 18:00 New York, -1 wenn keine rechtzeitig kommt) und
    der späteste Ausstieg (15:55 New York desselben Handelstags, also vor der Übernachtgebühr). Die Index-Kurse von
    HistData enden um 16:15 New York, darum nicht später."""
    p = cfg["tageshandel"]
    start = m.t0[m.gi] + np.timedelta64(cfg["daten"]["pause_min"], "m")
    i = yr._erste_ab(m, start, p["toleranz_min"])
    i = np.where((i >= 0) & (m.tix[np.maximum(i, 0)] == m.gi), i, -1)
    return i, y2._ny_utc(pd.DatetimeIndex(m.gtag), p["aus_min"])


def _tagestrades(m: Markt, cfg: dict, richtung: np.ndarray, stop_atr: float, halte_tage: int = 1,
                 geduld: dict | None = None) -> list[dict]:
    """Einstieg nach der Pause, Ausstieg 15:55 New York am selben Handelstag (halte_tage 1) oder an einem späteren.
    Mit geduld = {ziel_atr, stufen, max_tage} endet der Trade wie die Geduld-Regel: kleines Ziel, das in Stufen sinkt,
    spätester Ausstieg 15:55 New York am Handelstag g plus max_tage."""
    i, aus = tages_einstieg(m, cfg)
    sig = []
    for g in np.flatnonzero(richtung != 0):
        if g < 1 or i[g] < 0 or not np.isfinite(m.atr_vor[g]):
            continue
        atr = float(m.atr_vor[g])
        s = {"i0": int(i[g]), "d": int(richtung[g]), "sd": float(stop_atr * atr), "zd": 0.0,
             "t_max": aus[min(g + halte_tage - 1, len(aus) - 1)]}
        if geduld:
            s["zd"] = float(geduld["ziel_atr"]) * atr
            s["t_max"] = aus[min(g + int(geduld["max_tage"]), len(aus) - 1)]
            s["stufen"] = tuple((int(tage), float(z) * atr) for tage, z in geduld["stufen"])
        sig.append(s)
    return sig


def _auf_markt(m: Markt, tage: np.ndarray, richtung: np.ndarray) -> np.ndarray:
    """Richtung je Datum auf die gültigen Handelstage von m legen."""
    out = np.zeros(len(m.gtag), np.int64)
    pos = np.searchsorted(m.gtag, tage)
    ok = (pos < len(m.gtag)) & (m.gtag[np.minimum(pos, len(m.gtag) - 1)] == tage)
    out[pos[ok]] = richtung[ok]
    return out


def richtung_umschichtung(s: Markt, p: dict) -> np.ndarray:
    """Je gültigem Handelstag des Signal-Markts: -1, wenn Aktien im laufenden Monat vor Anleihen liegen, +1 umgekehrt.
    Nur in den letzten p["tage"] Handelstagen des Monats, gemessen mit den Schlusskursen bis zum Vortag."""
    n = len(s.gtag)
    mon = s.gtag.astype("datetime64[M]")
    letzter = np.r_[mon[1:] != mon[:-1], True]
    ende_soll = (pd.Timestamp(s.gtag[-1]) + pd.offsets.BMonthEnd(0)).to_datetime64().astype("datetime64[D]")
    letzter[-1] = bool(s.gtag[-1] >= ende_soll)                    # der letzte Monat der Daten zählt nur, wenn er voll ist
    ende = np.full(n, -1, np.int64)                                 # Index des letzten Handelstags im eigenen Monat
    ref = np.full(n, -1, np.int64)                                  # Index des letzten Handelstags im Vormonat
    letzte_pos, vor_pos = -1, -1
    for g in range(n):
        ref[g] = vor_pos
        if letzter[g]:
            vor_pos = g
    for g in range(n - 1, -1, -1):
        if letzter[g]:
            letzte_pos = g
        ende[g] = letzte_pos if (letzte_pos >= 0 and mon[letzte_pos] == mon[g]) else -1
    y_jetzt, _ = vor(p["reihe"], s.gtag)
    out = np.zeros(n, np.int64)
    for g in range(2, n):
        if ende[g] < 0 or ref[g] < 0 or ende[g] - g >= p["tage"] or g - 1 <= ref[g]:
            continue
        aktien = s.gc[g - 1] / s.gc[ref[g]] - 1.0
        y_ref = vor(p["reihe"], np.array([s.gtag[ref[g]] + np.timedelta64(1, "D")]))[0][0]
        tage = float((s.gtag[g - 1] - s.gtag[ref[g]]).astype(np.int64))
        anleihen = -p["laufzeit_jahre"] * (y_jetzt[g] - y_ref) / 100.0 + y_ref / 100.0 * tage / 365.0
        abstand = aktien - anleihen
        if np.isfinite(abstand) and abs(abstand) >= p["schwelle"]:
            out[g] = -1 if abstand > 0 else 1
    return out


def regel_umschichtung(m: Markt, cfg: dict, p: dict) -> list[dict]:
    s = partner(m, p["signal_markt"])
    return _tagestrades(m, cfg, _auf_markt(m, s.gtag, richtung_umschichtung(s, p)), p["stop_atr"])


def richtung_fed_zyklus(gtag: np.ndarray, fomc: np.ndarray, spannen: list) -> np.ndarray:
    """+1 an den Handelstagen der genannten Spannen nach einem Zinsentscheid (Tag 0), aber nie ab dem Tag vor dem
    nächsten Entscheid."""
    out = np.zeros(len(gtag), np.int64)
    pos = np.searchsorted(gtag, fomc)
    for q, g0 in enumerate(pos):
        if g0 >= len(gtag) or gtag[g0] != fomc[q]:
            continue
        grenze = pos[q + 1] - 1 if q + 1 < len(pos) else len(gtag)
        for a, b in spannen:
            for g in range(g0 + a, g0 + b + 1):
                if g < grenze and g < len(gtag):
                    out[g] = 1
    return out


def _reihe_wert(w: np.ndarray, p: dict) -> np.ndarray:
    """Je Beobachtung der Wert, den die Regel ansieht: der Stand (niveau) oder die Änderung über p["tage"]."""
    if p.get("niveau"):
        return w
    k = int(p["tage"])
    aend = (w[k:] / w[:-k] - 1.0) if p.get("relativ") else (w[k:] - w[:-k])
    return np.r_[np.full(k, np.nan), aend]


def quantil_vor(gtag: np.ndarray, p: dict) -> np.ndarray:
    """Je Handelstag das Quantil der p["quantil"]["fenster"] Beobachtungen VOR der jüngsten, die die Regel sehen darf.
    Die jüngste Beobachtung selbst zählt nicht mit."""
    d, w = fred(p["reihe"])
    q = pd.Series(_reihe_wert(w, p)).rolling(int(p["quantil"]["fenster"])).quantile(float(p["quantil"]["q"])).shift(1).to_numpy()
    grenze = np.asarray(gtag).astype("datetime64[D]") - np.timedelta64(p.get("lag", 0), "D")
    i = np.searchsorted(d, grenze, side="left") - 1
    return np.where(i >= 0, q[np.maximum(i, 0)], np.nan)


def richtung_reihe(gtag: np.ndarray, p: dict) -> np.ndarray:
    """Änderung einer fremden Reihe über p["tage"] Beobachtungen (oder ihr Stand mit niveau). Anstieg ab der Schwelle
    gibt p["vorzeichen"], Rückgang das Gegenteil. Mit "quantil" ist die Schwelle das Quantil der Beobachtungen davor
    (nur mit nur_anstieg). Der jüngste Wert darf höchstens p["frisch_tage"] Kalendertage alt sein."""
    lag = p.get("lag", 0)
    a, d1 = vor(p["reihe"], gtag, 0, lag)
    if p.get("niveau"):
        wert = a
    else:
        b, _ = vor(p["reihe"], gtag, p["tage"], lag)
        wert = (a / b - 1.0) if p.get("relativ") else (a - b)
    alter = (gtag - d1).astype("timedelta64[D]").astype(float)
    frisch = np.isfinite(wert) & (alter <= p["frisch_tage"])
    if "quantil" in p:
        if not p.get("nur_anstieg"):
            raise SystemExit("quantil geht nur mit nur_anstieg")
        schwelle = quantil_vor(gtag, p)
        frisch &= np.isfinite(schwelle)
    else:
        schwelle = p["schwelle"]
    with np.errstate(invalid="ignore"):
        out = np.where(wert >= schwelle, p["vorzeichen"], 0)
        if not p.get("nur_anstieg"):
            out = np.where(wert <= -schwelle, -p["vorzeichen"], out)
    return np.where(frisch, out, 0).astype(np.int64)


def regel_tokio(m: Markt, cfg: dict, p: dict) -> list[dict]:
    """Vormittag sagt Nachmittag in Tokio. Zeiten in Tokioter Ortszeit (UTC plus 9, keine Sommerzeit)."""
    neun = np.timedelta64(9, "h")
    tage = np.unique((m.t + neun).astype("datetime64[D]"))
    tage = tage[np.asarray(pd.DatetimeIndex(tage).weekday) < 5]

    def erste(minute: int) -> np.ndarray:
        zeit = tage.astype("datetime64[ns]") + np.timedelta64(minute, "m") - neun
        return yr._erste_ab(m, zeit, p["toleranz_min"])

    i_schluss, i_mittag, i_ein = erste(p["schluss_min"]), erste(p["mittag_min"]), erste(p["ein_min"])
    sig = []
    for q in range(1, len(tage)):
        if min(i_schluss[q - 1], i_mittag[q], i_ein[q]) < 0 or (tage[q] - tage[q - 1]).astype(np.int64) > 4:
            continue
        lauf = m.o[i_mittag[q]] / m.o[i_schluss[q - 1]] - 1.0
        if abs(lauf) < p["schwelle"]:
            continue
        i0 = int(i_ein[q])
        g = m.gpos[m.tix[i0]]
        if g < 1 or not np.isfinite(m.atr_vor[g]):
            continue
        sig.append({"i0": i0, "d": 1 if lauf > 0 else -1, "sd": float(p["stop_atr"] * m.atr_vor[g]), "zd": 0.0,
                    "t_max": tage[q].astype("datetime64[ns]") + np.timedelta64(p["schluss_min"], "m") - neun})
    return sig


def regel_funding(m: Markt, cfg: dict, p: dict) -> list[dict]:
    """Extreme Finanzierungssätze als Gegenzeichen. Verglichen wird mit den p["fenster"] Sätzen davor."""
    t, r = funding(yr.KRYPTO[m.sym][0])
    s = pd.Series(r)
    hoch = s.rolling(p["fenster"]).quantile(p["quantil_hoch"]).shift(1).to_numpy()
    tief = s.rolling(p["fenster"]).quantile(p["quantil_tief"]).shift(1).to_numpy()
    with np.errstate(invalid="ignore"):
        d = np.where(r > hoch, -1, np.where(r < tief, 1, 0))
    i = yr._erste_ab(m, t + np.timedelta64(p["warte_min"], "m"), p["toleranz_min"])
    sig = []
    for q in np.flatnonzero(d != 0):
        i0 = int(i[q])
        if i0 < 0:
            continue
        g = m.gpos[m.tix[i0]]
        if g < 1 or not np.isfinite(m.atr_vor[g]):
            continue
        sig.append({"i0": i0, "d": int(d[q]), "sd": float(p["stop_atr"] * m.atr_vor[g]), "zd": 0.0,
                    "t_max": m.t[i0] + np.timedelta64(p["halte_std"], "h")})
    return sig


def regel_geduld(m: Markt, cfg: dict, p: dict) -> list[dict]:
    """Kirons Geduld-Idee in ihrer logischsten Form: kleiner Rücksetzer auf der Stundenkerze im Aufwärtstrend, nur
    Long, kleines Ziel, weiter Notstop, lange Geduld. Mit "stufen" sinkt das Ziel nach Tagen auf Einstand und dann
    auf einen kleinen Verlust."""
    k = y2._kerzen_1h(m)
    rsi = y2._rsi(k["C"], p["rsi_n"])
    ende = m.t[k["b"]] + 5 * MIN
    ny_ende = (m.nymin[k["b"]] + 5) % 1440
    sma = pd.Series(m.gc).rolling(p["trend_tage"]).mean().to_numpy()
    erlaubt = richtung_reihe(m.gtag, p["nur_nach"]) == 1 if "nur_nach" in p else np.ones(len(m.gtag), bool)
    with np.errstate(invalid="ignore"):
        kand = np.flatnonzero((rsi < p["rsi_unter"]) & (k["n"] >= p["min_kerzen"])
                              & (ny_ende >= p["von_min"]) & (ny_ende <= p["bis_min"]))
    sig = []
    for j in kand:
        i0 = int(k["b"][j] + 1)
        if i0 >= m.n - 1 or (m.t[i0] - ende[j]) > p["frist_min"] * MIN:
            continue
        g = m.gpos[m.tix[i0]]
        if g < 2 or not np.isfinite(m.atr_vor[g]) or not np.isfinite(sma[g - 1]) or not m.gc[g - 1] > sma[g - 1]:
            continue
        if not erlaubt[g]:
            continue
        gx = min(g + p["max_tage"], len(m.gi) - 1)
        atr = float(m.atr_vor[g])
        s = {"i0": i0, "d": 1, "sd": p["stop_atr"] * atr, "zd": p["ziel_atr"] * atr,
             "t_max": y2._ny_utc(pd.DatetimeIndex([m.gtag[gx]]), p["aus_min"])[0]}
        if "stufen" in p:
            s["stufen"] = tuple((int(tage), float(z) * atr) for tage, z in p["stufen"])
        sig.append(s)
    return sig


def regel_schluss_schub(m: Markt, cfg: dict, p: dict) -> list[dict]:
    """Hebel-Fonds am Schluss: liegt der Markt zur Uhrzeit ein_min (New York) weit genug vom Schluss des vorigen
    Handelstags entfernt, wird in dieselbe Richtung gehandelt und zur Uhrzeit aus_min geschlossen."""
    tage = pd.DatetimeIndex(m.gtag)
    i_ein = yr._erste_ab(m, y2._ny_utc(tage, p["ein_min"]), p["toleranz_min"])
    aus = y2._ny_utc(tage, p["aus_min"])
    schwelle = float(p["schwelle"][m.sym])
    sig = []
    for g in range(1, len(m.gtag)):
        i0 = int(i_ein[g])
        if i0 < 0 or m.tix[i0] != m.gi[g] or not np.isfinite(m.atr_vor[g]):
            continue
        lauf = m.o[i0] / m.gc[g - 1] - 1.0
        if abs(lauf) < schwelle:
            continue
        sig.append({"i0": i0, "d": 1 if lauf > 0 else -1, "sd": float(p["stop_anteil"] * m.o[i0]), "zd": 0.0,
                    "t_max": aus[g]})
    return sig


def marken_signale(t: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray, pip: float, p: dict) -> list[tuple[int, int]]:
    """Runde Marken: (Kerze, Richtung) für jede Kerze, die zwischen von_min und bis_min Londoner Zeit beginnt und als
    erste des Londoner Tages mehr als abstand_pips jenseits einer runden Marke schließt, wenn Hoch (oder Tief) der
    vorher_min Minuten davor ganz auf der anderen Seite der Marke lag. Gerechnet wird in Pips auf eine Stelle."""
    schritt, ab, n_vor = float(p["marke_pips"]), float(p["abstand_pips"]), int(p["vorher_min"]) // 5
    lon = pd.DatetimeIndex(t).tz_localize("UTC").tz_convert("Europe/London")
    lmin = np.asarray(lon.hour * 60 + lon.minute)
    ltag = lon.tz_localize(None).values.astype("datetime64[D]")
    cp, hp, lp = (np.round(x / pip, 1) for x in (c, h, l))
    hoch = pd.Series(hp).rolling(n_vor).max().shift(1).to_numpy()
    tief = pd.Series(lp).rolling(n_vor).min().shift(1).to_numpy()
    dicht = np.zeros(len(t), bool)
    dicht[n_vor:] = (t[n_vor:] - t[:-n_vor]) <= (n_vor * 5 + int(p["luecke_min"])) * MIN
    erster = np.r_[True, ltag[1:] != ltag[:-1]]
    sc = pd.Series(cp)
    max_vor = np.where(erster, -np.inf, np.r_[-np.inf, sc.groupby(ltag).cummax().to_numpy()[:-1]])
    min_vor = np.where(erster, np.inf, np.r_[np.inf, sc.groupby(ltag).cummin().to_numpy()[:-1]])
    oben = np.floor((cp - ab) / schritt) * schritt                # höchste runde Marke unter Schluss minus Abstand
    unten = np.ceil((cp + ab) / schritt) * schritt
    zeit = (lmin >= p["von_min"]) & (lmin < p["bis_min"]) & dicht
    with np.errstate(invalid="ignore"):
        auf = zeit & (cp - ab > oben) & (hoch < oben) & (max_vor - ab <= oben)
        runter = zeit & (cp + ab < unten) & (tief > unten) & (min_vor + ab >= unten)
    return sorted([(int(j), 1) for j in np.flatnonzero(auf)] + [(int(j), -1) for j in np.flatnonzero(runter)])


def regel_runde_marke(m: Markt, cfg: dict, p: dict) -> list[dict]:
    """Stop-Häufung hinter runden Marken (Osler 2003): dem ersten Schluss jenseits der Marke folgen."""
    pip = float(p["pip"][m.sym])
    sig = []
    for j, d in marken_signale(m.t, m.h, m.l, m.c, pip, p):
        i0 = j + 1
        if i0 >= m.n - 1 or (m.t[i0] - m.t[j]) > (5 + int(p["frist_min"])) * MIN:
            continue
        g = m.gpos[m.tix[i0]]
        if g < 1 or not np.isfinite(m.atr_vor[g]):
            continue
        sig.append({"i0": i0, "d": d, "sd": float(p["stop_pips"]) * pip, "zd": float(p["ziel_pips"]) * pip,
                    "t_max": m.t[i0] + np.timedelta64(int(p["halte_min"]), "m")})
    return sig


def regel_fonds_fenster(m: Markt, cfg: dict, p: dict) -> list[dict]:
    """Umkehr nach dem Fenster, in dem die Bitcoin-Fonds ihren Abrechnungskurs bilden (15 bis 16 Uhr New York).
    US-Börsentage sind die gültigen Handelstage des Markts p["boersentage"]."""
    tage = pd.DatetimeIndex(partner(m, p["boersentage"]).gtag)
    tol = int(p["toleranz_min"])
    i_a, i_b, i_e = (yr._erste_ab(m, y2._ny_utc(tage, p[k]), tol) for k in ("von_min", "bis_min", "ein_min"))
    aus = y2._ny_utc(tage, p["aus_min"])
    sig = []
    for q in range(len(tage)):
        if min(i_a[q], i_b[q], i_e[q]) < 0:
            continue
        a, b, i0 = m.o[i_a[q]], m.o[i_b[q]], int(i_e[q])
        lauf = b / a - 1.0
        if abs(lauf) < p["schwelle"]:
            continue
        g = m.gpos[m.tix[i0]]
        if g < 1 or not np.isfinite(m.atr_vor[g]):
            continue
        weite = abs(b - a)
        sig.append({"i0": i0, "d": -1 if lauf > 0 else 1, "sd": float(p["stop_anteil"] * weite),
                    "zd": float(p["ziel_anteil"] * weite), "t_max": aus[q]})
    return sig


def regel_us_schreck(m: Markt, cfg: dict, p: dict) -> list[dict]:
    """Tokio-Eröffnung nach einem US-Schreck: fiel der Signal-Markt an einem Handelstag von Schluss zu Schluss um
    mindestens p["schwelle"], wird am nächsten Werktag zur Uhrzeit ein_min gekauft und zur Uhrzeit aus_min
    geschlossen. Zeiten in Tokioter Ortszeit (UTC plus 9, keine Sommerzeit). Der Handelstag des Signal-Markts endet
    um 17:00 New York, Tokio öffnet zwei bis drei Stunden später."""
    s = partner(m, p["signal_markt"])
    neun = np.timedelta64(9, "h")
    lauf = s.gc[1:] / s.gc[:-1] - 1.0
    sig = []
    for g in np.flatnonzero(lauf <= -p["schwelle"]) + 1:
        morgen = s.gtag[g].astype("datetime64[D]") + np.timedelta64(1, "D")
        while pd.Timestamp(morgen).weekday() >= 5:
            morgen = morgen + np.timedelta64(1, "D")
        basis = morgen.astype("datetime64[ns]") - neun
        i0 = int(yr._erste_ab(m, np.array([basis + np.timedelta64(int(p["ein_min"]), "m")]), p["toleranz_min"])[0])
        if i0 < 0:
            continue
        gm = m.gpos[m.tix[i0]]
        if gm < 1 or not np.isfinite(m.atr_vor[gm]):
            continue
        sig.append({"i0": i0, "d": 1, "sd": float(p["stop_atr"] * m.atr_vor[gm]), "zd": 0.0,
                    "t_max": basis + np.timedelta64(int(p["aus_min"]), "m")})
    return sig


def _ort_utc(tage: np.ndarray, minute: int, zone: str) -> np.ndarray:
    """Kalendertage am Ort (Zeitzone zone) plus Minute des Tages -> UTC als datetime64[ns]."""
    return (pd.DatetimeIndex(tage) + pd.Timedelta(minutes=int(minute))).tz_localize(zone).tz_convert("UTC") \
        .tz_localize(None).values.astype("datetime64[ns]")


def verfallstage(gtag: np.ndarray, nummer: int) -> np.ndarray:
    """Index (in gtag) des Verfallstags je Monat, das ist der nummer-te Freitag. Ist er kein gültiger Handelstag
    (Feiertag), gilt der gültige Handelstag davor, höchstens drei Kalendertage früher."""
    gtag = np.asarray(gtag).astype("datetime64[D]")
    out = []
    for monat in np.unique(gtag.astype("datetime64[M]")):
        erster = monat.astype("datetime64[D]")
        wochentag = (erster.astype(np.int64) + 3) % 7              # 0 ist Montag (der 01.01.1970 war ein Donnerstag)
        freitag = erster + np.timedelta64(int((4 - wochentag) % 7 + 7 * (nummer - 1)), "D")
        if freitag > gtag[-1]:
            continue
        g = int(np.searchsorted(gtag, freitag, side="right")) - 1
        if g >= 1 and 0 <= (freitag - gtag[g]).astype(np.int64) <= 3:
            out.append(g)
    return np.array(sorted(set(out)), np.int64)


def regel_verfallstag(m: Markt, cfg: dict, p: dict) -> list[dict]:
    """Verfallstag-Morgen in zwei Teilen. Teil 1: Kauf am gültigen Handelstag vor dem Verfallstag zur Uhrzeit kauf_min,
    Ausstieg am Verfallstag zur Uhrzeit wechsel_min (dann wird abgerechnet). Teil 2: Verkauf am Verfallstag zur Uhrzeit
    short_min, Ausstieg zur Uhrzeit aus_min. Uhrzeiten am Ort des Markts (p["ort"][Symbol])."""
    q = p["ort"][m.sym]
    zone, tol = q["zone"], int(p["toleranz_min"])
    sig = []
    for g in verfallstage(m.gtag, int(q["nummer"])):
        tag, vortag = m.gtag[g:g + 1], m.gtag[g - 1:g]
        if (tag[0] - vortag[0]).astype("timedelta64[D]").astype(np.int64) > 4:      # Lücke in den Kursen
            continue
        i_kauf = int(yr._erste_ab(m, _ort_utc(vortag, q["kauf_min"], zone), tol)[0])
        i_short = int(yr._erste_ab(m, _ort_utc(tag, q["short_min"], zone), tol)[0])
        if i_kauf >= 0:
            sig.append({"i0": i_kauf, "d": 1, "sd": float(p["stop_anteil"] * m.o[i_kauf]), "zd": 0.0,
                        "t_max": _ort_utc(tag, q["wechsel_min"], zone)[0]})
        if i_short >= 0:
            sig.append({"i0": i_short, "d": -1, "sd": float(p["stop_anteil"] * m.o[i_short]), "zd": 0.0,
                        "t_max": _ort_utc(tag, q["aus_min"], zone)[0]})
    return sig


# ---------------------------------------------------------------------------------------------------------------------
# Vorhersage-Modell: logistische Regression über eine Gruppe von Märkten, jedes Jahr nur mit älteren Jahren gelernt.

def _versetzt(x: np.ndarray, k: int) -> np.ndarray:
    return np.r_[np.full(k, np.nan), x[:-k]] if k > 0 else x


def merkmale(m: Markt, cfg: dict, p: dict) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Merkmale je gültigem Handelstag g, alle aus Werten, die am Ende von g minus 1 feststanden. Dazu das Ergebnis
    des Tageshandels (1 = der Kurs beim Ausstieg liegt über dem Einstieg nach der Pause, nan ohne Handel)."""
    gc, atr = m.gc, m.atr_vor
    c1 = _versetzt(gc, 1)
    sp, namen = [], []
    for k in p["rueckblick_tage"]:
        sp.append((c1 - _versetzt(gc, 1 + k)) / (atr * np.sqrt(k)))
        namen.append(f"lauf_{k}")
    for n in p["rsi"]:
        sp.append(_versetzt(y2._rsi(gc, n), 1) / 50.0 - 1.0)
        namen.append(f"rsi_{n}")
    for n in p["schnitt_tage"]:
        sma = pd.Series(gc).rolling(n).mean().to_numpy()
        sp.append((c1 - _versetzt(sma, 1)) / (atr * np.sqrt(n)))
        namen.append(f"abstand_{n}")
    with np.errstate(invalid="ignore", divide="ignore"):
        ibs = (m.gc - m.gl) / (m.gh - m.gl) - 0.5
    sp.append(_versetzt(np.where(np.isfinite(ibs), ibs, 0.0), 1))
    namen.append("lage_im_tag")
    sp.append(atr / pd.Series(atr).rolling(100, min_periods=50).mean().to_numpy() - 1.0)
    namen.append("schwankung")
    wt = np.asarray(pd.DatetimeIndex(m.gtag).weekday)
    for w in range(4):
        sp.append((wt == w).astype(float))
        namen.append(f"wochentag_{w}")
    v1, d1 = vor("VIXCLS", m.gtag)
    v2, _ = vor("VIXCLS", m.gtag, 1)
    x1, dx = vor("VXVCLS", m.gtag)
    sp += [np.log(v1 / 20.0), np.log(v1 / v2), np.where(dx == d1, v1 / x1 - 1.0, np.nan)]
    namen += ["vix", "vix_aenderung", "vix_kurve"]
    for reihe in ("DGS10", "DGS2"):
        a, _ = vor(reihe, m.gtag)
        b, _ = vor(reihe, m.gtag, 5)
        sp.append(a - b)
        namen.append(f"{reihe}_5")
    X = np.column_stack(sp)
    i, aus = tages_einstieg(m, cfg)
    ia = np.minimum(np.searchsorted(m.t, aus), m.n - 1)
    ok = (i >= 0) & (m.tix[ia] == m.gi) & (ia > np.maximum(i, 0))
    y = np.where(ok, (m.o[ia] > m.o[np.maximum(i, 0)]).astype(float), np.nan)
    return X, y, namen


def logistisch(X: np.ndarray, y: np.ndarray, strafe: float, schritte: int = 30) -> np.ndarray:
    """Logistische Regression mit L2-Strafe (nicht auf dem Achsenabschnitt in Spalte 0), Newton-Verfahren."""
    w = np.zeros(X.shape[1])
    s = np.full(X.shape[1], float(strafe))
    s[0] = 0.0
    for _ in range(schritte):
        q = 1.0 / (1.0 + np.exp(-np.clip(X @ w, -30, 30)))
        grad = X.T @ (q - y) + s * w
        hess = (X * (q * (1 - q))[:, None]).T @ X + np.diag(s) + 1e-9 * np.eye(X.shape[1])
        schritt = np.linalg.solve(hess, grad)
        w = w - schritt
        if np.max(np.abs(schritt)) < 1e-8:
            break
    return w


def vorhersagen(tage: np.ndarray, X: np.ndarray, y: np.ndarray, p: dict) -> np.ndarray:
    """Wahrscheinlichkeit für "steigt" je Zeile. Jedes Kalenderjahr wird nur mit Zeilen aus früheren Jahren gelernt.
    Merkmale werden mit Mittel und Streuung der Lernjahre gleich skaliert, Lücken bekommen das Mittel."""
    jahr = tage.astype("datetime64[Y]").astype(np.int64) + 1970
    out = np.full(len(y), np.nan)
    for j in np.unique(jahr):
        lern = (jahr < j) & np.isfinite(y)
        ziel = jahr == j
        if lern.sum() < p["min_lernzeilen"] or len(np.unique(jahr[lern])) < p["min_lernjahre"]:
            continue
        mittel = np.nanmean(X[lern], axis=0)
        streu = np.nanstd(X[lern], axis=0)
        streu = np.where(streu > 0, streu, 1.0)

        def skaliert(a: np.ndarray) -> np.ndarray:
            z = (a - mittel) / streu
            z = np.clip(np.where(np.isfinite(z), z, 0.0), -5.0, 5.0)
            return np.column_stack([np.ones(len(z)), z])

        w = logistisch(skaliert(X[lern]), y[lern], p["strafe"])
        out[ziel] = 1.0 / (1.0 + np.exp(-np.clip(skaliert(X[ziel]) @ w, -30, 30)))
    return out


_MODELLE: dict = {}


def regel_modell(m: Markt, cfg: dict, p: dict, gruppe: list[str], name: str) -> list[dict]:
    key = (name, str(m.arbeit), m.bis, m.saat)
    if key not in _MODELLE:
        teile = []
        for nr, sym in enumerate(gruppe):
            pm = partner(m, sym)
            X, y, _ = merkmale(pm, cfg, p)
            eigen = np.zeros((len(y), len(gruppe) - 1))             # eigener Achsenabschnitt je Markt (außer dem ersten)
            if nr > 0:
                eigen[:, nr - 1] = 1.0
            teile.append((sym, pm.gtag, np.column_stack([X, eigen]), y))
        tage = np.concatenate([t[1] for t in teile])
        prob = vorhersagen(tage, np.vstack([t[2] for t in teile]), np.concatenate([t[3] for t in teile]), p)
        _MODELLE[key], a = {}, 0
        for sym, gtag, _, _ in teile:
            q = prob[a:a + len(gtag)]
            a += len(gtag)
            with np.errstate(invalid="ignore"):
                _MODELLE[key][sym] = np.where(q >= 0.5 + p["abstand"], 1, np.where(q <= 0.5 - p["abstand"], -1, 0))
    return _tagestrades(m, cfg, _MODELLE[key][m.sym], p["stop_atr"])


# ---------------------------------------------------------------------------------------------------------------------
# Verteiler, Urteil, Rechnung

def signale(regel: str, m: Markt, cfg: dict, termine: np.ndarray) -> list[dict]:
    p = cfg["regeln"][regel]
    art = p["art"]
    if art == "umschichtung":
        return regel_umschichtung(m, cfg, p)
    if art == "fed_zyklus":
        return _tagestrades(m, cfg, richtung_fed_zyklus(m.gtag, kalender()["fomc"], p["spannen"]), p["stop_atr"])
    if art == "zahlentag":
        tage = np.unique(np.concatenate([kalender()[k] for k in p["termine"]]))
        return _tagestrades(m, cfg, _auf_markt(m, tage, np.ones(len(tage), np.int64)), p["stop_atr"])
    if art == "reihe":
        return _tagestrades(m, cfg, richtung_reihe(m.gtag, p), p["stop_atr"], p.get("halte_tage", 1), p.get("geduld"))
    if art == "tokio":
        return regel_tokio(m, cfg, p)
    if art == "funding":
        return regel_funding(m, cfg, p)
    if art == "geduld":
        return regel_geduld(m, cfg, p)
    if art == "modell":
        return regel_modell(m, cfg, p, cfg["varianten"][regel]["maerkte"], regel)
    if art == "schluss_schub":
        return regel_schluss_schub(m, cfg, p)
    if art == "runde_marke":
        return regel_runde_marke(m, cfg, p)
    if art == "fonds_fenster":
        return regel_fonds_fenster(m, cfg, p)
    if art == "us_schreck":
        return regel_us_schreck(m, cfg, p)
    if art == "verfallstag":
        return regel_verfallstag(m, cfg, p)
    raise SystemExit(f"unbekannte Art {art} in Regel {regel}")


def urteile(erg: dict, cfg: dict) -> None:
    """Wie rueckblick.urteile, nur zählt Holm mit der festen Gesamtzahl aller geplanten Varianten beider Durchgänge
    (huerden.holm_anzahl). Nicht gerechnete Varianten zählen damit wie Varianten mit p = 1."""
    h = cfg["huerden"]
    mit_p = sorted(((e["zufall"]["p"], n) for n, e in erg.items() if "zufall" in e))
    anzahl = max(int(h["holm_anzahl"]), len(cfg["varianten"]))
    holm_ok, noch = set(), True
    for rang, (p, n) in enumerate(mit_p):
        noch = noch and p <= h["holm_alpha"] / (anzahl - rang)
        if noch:
            holm_ok.add(n)
    for n, e in erg.items():
        if e.get("trades", 0) == 0:
            continue
        gruende = []
        if e["trades"] < h["min_trades"]:
            gruende.append("Trades")
        if e["gewinnfaktor"] is None or e["gewinnfaktor"] < h["min_gewinnfaktor"]:
            gruende.append("Gewinnfaktor")
        if e["gewinnfaktor_robust"] is None or e["gewinnfaktor_robust"] < h["min_robust"]:
            gruende.append("1,5-fache Kosten")
        for k in ("haelfte_1", "haelfte_2"):
            if e[k]["gewinnfaktor"] is None or e[k]["gewinnfaktor"] <= 1.0:
                gruende.append("Hälften")
                break
        if e["jahr_2026"]["trades"] >= h["jahr_2026_ab_trades"] and e["jahr_2026"]["gewinnfaktor"] <= 1.0:
            gruende.append("2026")
        z = e.get("zufall")
        if not (bool(z) and z["geschlagen_pct"] >= h["min_rang_pct"]):
            gruende.append("Zufall 95 %")
        e["holm"] = n in holm_ok
        streng = []
        if not e["holm"]:
            streng.append("Holm")
        if not z or z["z"] < h["min_z"]:
            streng.append("z unter 3")
        e["durchgefallen_bei"] = gruende + streng
        e["urteil"] = "durchgefallen" if gruende else ("Kandidat" if streng else "bestanden")
        if e["urteil"] == "bestanden" and h.get("hoechstens_kandidat"):
            e["urteil"], e["hinweis"] = "Kandidat", "nach dem ersten Ergebnis geändert, darum höchstens Kandidat"


@contextlib.contextmanager
def _diese_runde():
    alt = rb.Markt, rb.signale, rb.echte_trades, rb.zwillings_summen, rb.urteile
    rb.Markt, rb.signale, rb.echte_trades, rb.zwillings_summen, rb.urteile = \
        Markt, signale, echte_trades, zwillings_summen, urteile
    try:
        yield
    finally:
        rb.Markt, rb.signale, rb.echte_trades, rb.zwillings_summen, rb.urteile = alt


def rechne(arbeit: pathlib.Path, cfg: dict, bis, fenster, mitte, saat=None, mit_zwillingen=True):
    with _diese_runde():
        return rb.rechne(arbeit, cfg, bis, fenster, mitte, saat=saat, mit_zwillingen=mit_zwillingen)


def zusatz(trades: pd.DataFrame, erg: dict) -> None:
    """Ehrliche Zusatzzahlen je Variante: größter Verlust, längste Haltedauer, tiefstes Tal der Summe (alles in R)."""
    for name, e in erg.items():
        w = trades[trades["variante"] == name].sort_values("aus_utc") if len(trades) else trades
        if not len(w):
            continue
        r = w["R"].to_numpy(float)
        lauf = np.cumsum(r)
        tage = (pd.to_datetime(w["aus_utc"]) - pd.to_datetime(w["ein_utc"])).dt.total_seconds().to_numpy() / 86400.0
        gewinne = r[r > 0]
        e["zusatz"] = {"groesster_verlust_R": rb._rund(r.min(), 3), "mittlerer_gewinn_R": rb._rund(gewinne.mean() if len(gewinne) else 0, 3),
                       "tiefstes_tal_R": rb._rund(float((lauf - np.maximum.accumulate(np.r_[0.0, lauf])[1:]).min())),
                       "haltedauer_tage_mittel": rb._rund(tage.mean(), 2), "haltedauer_tage_max": rb._rund(tage.max(), 1)}


def main(argv: list[str]) -> int:
    nr = int(argv[0])
    datei, key, ergebnis = vorab(nr), schluessel(nr), ROOT / "suche" / f"ergebnis_{DATEIEN[nr]}"
    if argv[1] == "--festlegen":
        zeile = key + sha256_text(datei.read_text(encoding="utf-8"))
        journal_add(zeile)
        print(zeile)
        return 0
    modus, arbeit = argv[1], pathlib.Path(argv[2])
    if modus == "entwicklung":
        cfg = lade_vorab(nr, pruefen=False)
        cfg["varianten"] = {n: {**v, "maerkte": [s for s in v["maerkte"] if s != "GRXEUR"]} for n, v in cfg["varianten"].items()}
        erg, tr = rechne(arbeit, cfg, "2023-12-31T23:59", ("2021-03-01", "2023-12-29"), "2022-08-01")
        ziel, kopf = arbeit / f"entwicklung_{nr}", {"modus": "entwicklung, nur Kurse bis Ende 2023, kein Ergebnis"}
    elif modus == "probelauf":
        cfg = lade_vorab(nr, pruefen=False)
        saat = int(argv[3])
        f = cfg["fenster"]
        erg, tr = rechne(arbeit, cfg, None, (f["von"], f["bis"]), f["mitte"], saat=saat)
        ziel, kopf = arbeit / f"probelauf_{nr}_{saat}", {"modus": "erfundener Markt ohne Vorteil", "saat": saat}
    elif modus == "rechnen":
        cfg = lade_vorab(nr, pruefen=True)
        f = cfg["fenster"]
        erg, tr = rechne(arbeit, cfg, None, (f["von"], f["bis"]), f["mitte"])
        ziel, kopf = ergebnis, {"modus": "Rechnung", "vorab_sha256": sha256_text(datei.read_text(encoding="utf-8")), "fenster": f}
    else:
        raise SystemExit(__doc__)
    zusatz(tr, erg)
    rb.schreibe(erg, tr, cfg, ziel, kopf)
    if modus == "rechnen":
        rb.schreibe(erg, tr, cfg, arbeit / f"ergebnis_{DATEIEN[nr]}", kopf)
    for n, e in erg.items():
        z, x = e.get("zufall", {}), e.get("zusatz", {})
        print(f"{n:24s} {e.get('trades', 0):5d} T  GF {e.get('gewinnfaktor')}  rob {e.get('gewinnfaktor_robust')}  "
              f"Summe {e.get('summe_R')}  Treffer {e.get('trefferquote')}  H {e.get('haelfte_1', {}).get('gewinnfaktor')}/"
              f"{e.get('haelfte_2', {}).get('gewinnfaktor')}  Zufall {z.get('geschlagen_pct')} %  z {z.get('z')}  "
              f"größter Verlust {x.get('groesster_verlust_R')}  -> {e.get('urteil')} {e.get('durchgefallen_bei', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
