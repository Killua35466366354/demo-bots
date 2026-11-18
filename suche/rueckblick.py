"""Runde "Starker Rückblick" (18.11.2026): zwölf vorab festgelegte Varianten auf Indizes, Metallen und Devisen.

Regeln: suche/VORAB_rueckblick.yaml (versiegelt im Protokoll, bevor mit Kursen ab 2024 gerechnet wurde).
Daten: python -m suche.rueckblick_daten <Arbeit> (echtes UTC, Spread-Profil von Capital.com).

Aufruf:
    python -m suche.rueckblick --festlegen                 schreibt die Prüfsumme der Regeldatei ins Protokoll
    python -m suche.rueckblick entwicklung <Arbeit>        nur Kurse bis Ende 2023, prüft das Programm, kein Ergebnis
    python -m suche.rueckblick probelauf <Arbeit> <Saat>   ganze Rechnung auf einem erfundenen Markt ohne Vorteil
    python -m suche.rueckblick rechnen <Arbeit>            die Rechnung (nur mit passender Prüfsumme)

Kosten: Bid-Kerzen. Long kauft zum Ask (Bid plus Spread) und verkauft zum Bid, Short umgekehrt. Stop-Orders (Einstieg
und Schutz-Stop) füllen einen halben Spread schlechter. Berührt eine Kerze Stop und Ziel, zählt der Stop. Springt die
Eröffnung über den Stop, zählt die Eröffnung. Übernachtgebühr je Kalendernacht (17:00 New York).
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd
import yaml
from numba import njit

from suche.runde1 import journal_add, journal_lines, last_value, sha256_text

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_rueckblick.yaml"
KEY = "VORAB_rueckblick sha256 "
TERMINE = ROOT / "gold" / "v2" / "termine.yaml"
ERGEBNIS = ROOT / "suche" / "ergebnis_rueckblick"
NY = "America/New_York"
MIN = np.timedelta64(1, "m")
KLASSE = {"SPXUSD": "index", "NSXUSD": "index", "GRXEUR": "index", "UKXGBP": "index", "JPXJPY": "index",
          "XAUUSD": "metall", "XAGUSD": "metall"}
SCHLUSS = {"SPXUSD": (NY, 16 * 60), "NSXUSD": (NY, 16 * 60), "GRXEUR": ("Europe/Berlin", 17 * 60 + 30),
           "UKXGBP": ("Europe/London", 16 * 60 + 30), "JPXJPY": ("Asia/Tokyo", 15 * 60)}


def lade_vorab(pruefen: bool = True) -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if pruefen and last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("VORAB_rueckblick.yaml passt nicht zur Prüfsumme im Protokoll. Erst versiegeln, dann rechnen.")
    return yaml.safe_load(text)["rueckblick"]


# ---------------------------------------------------------------------------------------------------------------------
# Markt

class Markt:
    def __init__(self, sym: str, arbeit: pathlib.Path, cfg: dict, bis: str | None = None, saat: int | None = None):
        z = np.load(arbeit / f"{sym}.npz")
        t = z["t"]
        ok = np.ones(len(t), bool)
        if bis is not None:
            ok &= t <= np.datetime64(bis)
        ab = cfg["daten"].get("ab", {}).get(sym)
        if ab:
            ok &= t >= np.datetime64(ab)
        self.sym, self.klasse = sym, KLASSE.get(sym, "fx")
        self.t = t[ok]
        self.o, self.h, self.l, self.c = (z[k][ok].astype(float) for k in "ohlc")
        self.sp, self.nymin, tag = z["sp"][ok].astype(float), z["nymin"][ok].astype(np.int64), z["tag"][ok]
        if saat is not None:
            self._ohne_vorteil(saat)
        self.n = len(self.t)
        self.ms17 = (self.nymin - 17 * 60) % 1440                 # Minuten seit 17:00 New York
        self.tage, self.first = np.unique(tag, return_index=True)
        self.tix = np.searchsorted(self.tage, tag)
        anzahl = np.diff(np.r_[self.first, self.n])
        wt = np.asarray(pd.DatetimeIndex(self.tage).weekday)
        gueltig = (anzahl >= cfg["daten"]["min_kerzen_je_tag"]) & (wt < 5)
        grenze = (pd.DatetimeIndex(self.tage) - pd.Timedelta(days=1) + pd.Timedelta(hours=17))
        self.t0 = grenze.tz_localize(NY).tz_convert("UTC").tz_localize(None).values.astype("datetime64[ns]")
        letzte = np.r_[self.first[1:], self.n] - 1
        # Tageskerze ohne die Stunde 17 bis 18 Uhr New York (wie die Vortag-Regel)
        hh = np.where(self.ms17 >= 60, self.h, -np.inf)
        ll = np.where(self.ms17 >= 60, self.l, np.inf)
        dh, dl, dc = np.maximum.reduceat(hh, self.first), np.minimum.reduceat(ll, self.first), self.c[letzte]
        self.gi = np.flatnonzero(gueltig)                         # gültige Handelstage (Index in tage)
        self.gpos = np.full(len(self.tage), -1, np.int64)
        self.gpos[self.gi] = np.arange(len(self.gi))
        self.gh, self.gl, self.gc = dh[self.gi], dl[self.gi], dc[self.gi]
        vc = np.r_[np.nan, self.gc[:-1]]
        tr = np.fmax(self.gh - self.gl, np.fmax(np.abs(self.gh - vc), np.abs(self.gl - vc)))
        atr = pd.Series(tr).rolling(14).mean().to_numpy()
        self.atr_vor = np.r_[np.nan, atr[:-1]]                    # ATR 14 der Tage bis zum Vortag, je gültigem Tag
        ema = pd.Series(self.gc).ewm(span=50, adjust=False).mean().to_numpy()
        e5 = np.r_[np.full(5, np.nan), ema[:-5]]
        warm = np.arange(len(self.gc)) >= cfg["trend"]["vorlauf_tage"]
        hoch, tief = (self.gc > ema) & (ema > e5) & warm, (self.gc < ema) & (ema < e5) & warm
        trend = hoch.astype(np.int64) - tief.astype(np.int64)
        self.trend_vor = np.r_[0, trend[:-1]]                     # Tagestrend am Ende des Vortags, je gültigem Tag
        self.gtag = self.tage[self.gi]

    def _ohne_vorteil(self, saat: int) -> None:
        """Erfundener Markt ohne Vorteil: jede 5-Minuten-Kerze bekommt ein zufälliges Vorzeichen. Schwankung und ihre
        Uhrzeit bleiben, jede Richtung ist Zufall."""
        rng = np.random.default_rng([saat, sum(map(ord, self.sym))])
        lo, lh, ll, lc = (np.log(x) for x in (self.o, self.h, self.l, self.c))
        luecke = np.r_[0.0, lo[1:] - lc[:-1]]
        s = rng.choice(np.array([-1.0, 1.0]), size=len(lo))
        rh, rl, rc = lh - lo, ll - lo, lc - lo
        nh, nl, nc = np.where(s > 0, rh, -rl), np.where(s > 0, rl, -rh), s * rc
        neu_o = lo[0] + np.cumsum(s * luecke + np.r_[0.0, nc[:-1]])
        self.o, self.h, self.l, self.c = np.exp(neu_o), np.exp(neu_o + nh), np.exp(neu_o + nl), np.exp(neu_o + nc)

    def kerze_ab(self, zeit: np.ndarray) -> np.ndarray:
        return np.searchsorted(self.t, zeit)


# ---------------------------------------------------------------------------------------------------------------------
# Ein Trade

@njit(cache=True)
def _trade(o, h, l, c, sp, i0, d, lvl, sd, zd, imax, kf, rutsch):
    """Einstieg in Kerze i0. lvl = nan: zum Markt bei der Eröffnung. Sonst Stop-Order an der Marke lvl (Bid).
    Stop- und Ziel-Abstand zählen vom Bid beim Einstieg (bei der Stop-Order von der Marke).
    Gibt (Ausstiegskerze, Ergebnis in Kurspunkten, Einstiegskurs) zurück."""
    n = o.shape[0]
    s0 = sp[i0] * kf
    if imax <= i0:
        imax = i0 + 1
    j = i0
    if d > 0:
        if lvl == lvl:
            luecke = o[i0] >= lvl
            ref = max(lvl, o[i0])
            e = ref + s0 + rutsch * s0
        else:
            luecke = True
            ref = o[i0]
            e = ref + s0
        stop = ref - sd                                   # Bid-Marke
        ziel = ref + zd if zd > 0 else 1e300
        if lvl == lvl:
            # Einstiegskerze einer Stop-Order wie in runde4b: Eröffnung näher am Hoch -> O, Hoch, Tief, Schluss,
            # sonst O, Tief, Hoch, Schluss. Stop und Ziel zählen erst nach dem Auslösen.
            nah_hoch = (h[i0] - o[i0]) < (o[i0] - l[i0])
            if luecke and not nah_hoch:
                if l[i0] <= stop:
                    return i0, stop - rutsch * s0 - e, e
                if h[i0] >= ziel:
                    return i0, ziel - e, e
            else:
                if h[i0] >= ziel:
                    return i0, ziel - e, e
                danach = l[i0] if nah_hoch else c[i0]
                if danach <= stop:
                    return i0, stop - rutsch * s0 - e, e
            j = i0 + 1
        while True:
            if j >= n:
                return n - 1, c[n - 1] - e, e
            if j > i0:
                if j >= imax:
                    return j, o[j] - e, e
                if o[j] <= stop:
                    return j, o[j] - rutsch * sp[j] * kf - e, e
            if l[j] <= stop:
                return j, stop - rutsch * sp[j] * kf - e, e
            if h[j] >= ziel:
                return j, ziel - e, e
            j += 1
    else:
        if lvl == lvl:
            luecke = o[i0] <= lvl
            ref = min(lvl, o[i0])
            e = ref - rutsch * s0
        else:
            luecke = True
            ref = o[i0]
            e = ref
        stop = ref + sd                                   # Ask-Marke
        ziel = ref - zd if zd > 0 else -1e300
        if lvl == lvl:
            nah_hoch = (h[i0] - o[i0]) < (o[i0] - l[i0])
            if luecke and nah_hoch:
                if h[i0] + s0 >= stop:
                    return i0, e - (stop + rutsch * s0), e
                if l[i0] + s0 <= ziel:
                    return i0, e - ziel, e
            else:
                if l[i0] + s0 <= ziel:
                    return i0, e - ziel, e
                danach = c[i0] if nah_hoch else h[i0]
                if danach + s0 >= stop:
                    return i0, e - (stop + rutsch * s0), e
            j = i0 + 1
        while True:
            if j >= n:
                return n - 1, e - (c[n - 1] + sp[n - 1] * kf), e
            sj = sp[j] * kf
            if j > i0:
                if j >= imax:
                    return j, e - (o[j] + sj), e
                if o[j] + sj >= stop:
                    return j, e - (o[j] + sj + rutsch * sj), e
            if h[j] + sj >= stop:
                return j, e - (stop + rutsch * sj), e
            if l[j] + sj <= ziel:
                return j, e - ziel, e
            j += 1


@njit(cache=True)
def _viele(o, h, l, c, sp, i0, d, sd, zd, imax, kf, rutsch):
    m = i0.shape[0]
    ex, pnl, ein = np.empty(m, np.int64), np.empty(m), np.empty(m)
    for q in range(m):
        ex[q], pnl[q], ein[q] = _trade(o, h, l, c, sp, i0[q], d[q], np.nan, sd[q], zd[q], imax[q], kf[q], rutsch)
    return ex, pnl, ein


def gebuehr(m: Markt, cfg: dict, d, ein, i0, ex) -> np.ndarray:
    satz = cfg["kosten"]["nacht_pro_jahr"][m.klasse]
    r = np.where(np.asarray(d) > 0, satz["long"], satz["short"])
    naechte = (m.tage[m.tix[ex]] - m.tage[m.tix[i0]]).astype(np.int64)
    return np.asarray(ein) * r * naechte / 365.0


def echte_trades(m: Markt, sig: list[dict], cfg: dict) -> pd.DataFrame:
    """Signale der Reihe nach, höchstens ein Trade gleichzeitig je Markt. Jede Zeile bekommt auch das Ergebnis mit
    1,5-fachem Spread (gleiche Einstiege)."""
    rutsch, rob = cfg["kosten"]["rutschen_spread"], cfg["kosten"]["robust_faktor"]
    rows, frei_ab = [], -1
    for s in sorted(sig, key=lambda x: x["i0"]):
        i0 = s["i0"]
        if i0 <= frei_ab or i0 >= m.n - 1:
            continue
        g = m.gpos[m.tix[i0]]
        if g < 1 or not np.isfinite(m.atr_vor[g]) or not (s["sd"] > 0):
            continue
        imax = int(m.kerze_ab(np.array([s["t_max"]]))[0])
        ex, pnl, e = _trade(m.o, m.h, m.l, m.c, m.sp, i0, s["d"], s.get("lvl", np.nan), s["sd"], s.get("zd", 0.0),
                            imax, 1.0, rutsch)
        ex2, pnl2, e2 = _trade(m.o, m.h, m.l, m.c, m.sp, i0, s["d"], s.get("lvl", np.nan), s["sd"], s.get("zd", 0.0),
                               imax, rob, rutsch)
        fin = gebuehr(m, cfg, [s["d"]], [e], np.array([i0]), np.array([ex]))[0]
        fin2 = gebuehr(m, cfg, [s["d"]], [e2], np.array([i0]), np.array([ex2]))[0]
        frei_ab = ex
        tm = np.datetime64(s["t_max"], "ns")
        gx = m.gpos[m.tix[min(imax, m.n - 1)]]
        rows.append({"markt": m.sym, "ein_utc": m.t[i0], "aus_utc": m.t[ex], "richtung": int(s["d"]),
                     "einstieg": e, "ausstieg": e + s["d"] * pnl, "stop_abstand": s["sd"], "ziel_abstand": s.get("zd", 0.0),
                     "R": (pnl - fin) / s["sd"], "R_robust": (pnl2 - fin2) / s["sd"], "gebuehr_R": fin / s["sd"],
                     "i0": i0, "g": int(g), "ab_ein": (m.t[i0] - m.t0[m.tix[i0]]) / MIN,
                     "tage_bis_aus": int(max(gx, g) - g),
                     "ab_aus": (tm - m.t0[m.gi[max(gx, g)]]) / MIN, "tag": m.tage[m.tix[i0]]})
    return pd.DataFrame(rows)


def zwillings_summen(m: Markt, tr: pd.DataFrame, g_a: int, g_b: int, schritte: np.ndarray, cfg: dict) -> np.ndarray:
    """Summe in R je Verschiebung. Die Trades des Fensters wandern als Block um k gültige Handelstage nach vorn."""
    out = np.zeros(len(schritte))
    if tr.empty:
        return out
    n_fenster = g_b - g_a + 1
    g = tr["g"].to_numpy(np.int64)
    d = tr["richtung"].to_numpy(np.int64)
    sd, zd = tr["stop_abstand"].to_numpy(float), tr["ziel_abstand"].to_numpy(float)
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
        ok = (i0 < m.n - 1) & (m.tix[i0c] == tag2) & (m.t[i0c] - t_ein <= spaet) & np.isfinite(f) & (f > 0)
        if not ok.any():
            continue
        g_aus = np.minimum(g2 + weiter, len(m.gi) - 1)
        imax = np.searchsorted(m.t, m.t0[m.gi[g_aus]] + ab_aus)
        i0k, dk, fk = i0c[ok], d[ok], f[ok]
        ex, pnl, ein = _viele(m.o, m.h, m.l, m.c, m.sp, i0k, dk, sd[ok] * fk, zd[ok] * fk, imax[ok], fk, rutsch)
        fin = gebuehr(m, cfg, dk, ein, i0k, ex)
        out[q] = float(((pnl - fin) / (sd[ok] * fk)).sum())
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Regeln. Jede gibt Signale zurück: i0 (Kerze), d (+1/-1), sd (Stop-Abstand), zd (Ziel-Abstand, 0 = keins),
# t_max (spätester Ausstieg), lvl (Marke einer Stop-Order, fehlt bei Marktorder).

def _wilder(tr: np.ndarray, n: int) -> np.ndarray:
    return pd.Series(tr).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean().to_numpy()


def _kerzen(m: Markt, schluessel: np.ndarray) -> dict:
    """Kerzen aus 5-Minuten-Kerzen zusammenfassen. schluessel steigt mit der Zeit."""
    a = np.flatnonzero(np.r_[True, schluessel[1:] != schluessel[:-1]])
    b = np.r_[a[1:], m.n] - 1
    H, L, C = np.maximum.reduceat(m.h, a), np.minimum.reduceat(m.l, a), m.c[b]
    vc = np.r_[np.nan, C[:-1]]
    tr = np.fmax(H - L, np.fmax(np.abs(H - vc), np.abs(L - vc)))
    return {"a": a, "b": b, "H": H, "L": L, "C": C, "tr": tr, "n": b - a + 1, "key": schluessel[a]}


def regel_ausbruch4h(m: Markt, cfg: dict, termine: np.ndarray) -> list[dict]:
    p = cfg["regeln"]["ausbruch4h"]
    # 4-Std.-Kerzen beginnen 18, 22, 2, 6, 10, 14 Uhr New York. Die Stunde 17 bis 18 Uhr zählt zur Kerze ab 14 Uhr.
    ms18 = (m.nymin - 18 * 60) % 1440
    tag18 = (m.t - ms18.astype("timedelta64[m]")).astype("datetime64[D]").astype(np.int64)
    k = _kerzen(m, tag18 * 6 + ms18 // 240)
    schluss = m.t[k["b"]] + 5 * MIN
    voll = (k["n"] >= p["min_kerzen"])
    atr = _wilder(k["tr"], p["atr_n"])
    H, L, C = k["H"], k["L"], k["C"]
    hh = pd.Series(H).rolling(p["kanal"]).max().shift(1).to_numpy()
    ll = pd.Series(L).rolling(p["kanal"]).min().shift(1).to_numpy()
    tief10 = pd.Series(L).rolling(p["stop_kerzen"]).min().to_numpy()
    hoch10 = pd.Series(H).rolling(p["stop_kerzen"]).max().to_numpy()
    ueber, unter = C > hh, C < ll
    sig = []
    for j in range(p["kanal"] + 2, len(C) - 1):
        d = 1 if (ueber[j] and not ueber[j - 1]) else (-1 if (unter[j] and not unter[j - 1]) else 0)
        if d == 0 or not voll[j] or not np.isfinite(atr[j]):
            continue
        i0 = k["b"][j] + 1
        if i0 >= m.n - 1 or (m.t[i0] - schluss[j]) > p["frist_min"] * MIN:
            continue
        g = m.gpos[m.tix[i0]]
        if g < 1 or m.trend_vor[g] != d:
            continue
        utc_min = int((m.t[i0] - m.t[i0].astype("datetime64[D]")) / MIN)
        if p["sperre_utc"][0] <= utc_min <= p["sperre_utc"][1]:
            continue
        if len(termine) and np.min(np.abs((termine - m.t[i0]) / MIN)) <= p["termin_sperre_min"]:
            continue
        kurs = m.o[i0]
        roh = (kurs - (tief10[j] - p["stop_puffer_atr"] * atr[j])) if d > 0 else ((hoch10[j] + p["stop_puffer_atr"] * atr[j]) - kurs)
        sd = float(np.clip(roh, p["stop_min_atr"] * atr[j], p["stop_max_atr"] * atr[j]))
        j_aus = min(j + p["halte_kerzen"], len(C) - 1)
        t_max = min(schluss[j_aus], m.t[i0] + np.timedelta64(p["halte_tage_max"], "D"))
        sig.append({"i0": int(i0), "d": d, "sd": sd, "zd": 0.0, "t_max": t_max})
    return sig


def regel_vortag(m: Markt, cfg: dict, mit_trend: bool) -> list[dict]:
    p = cfg["regeln"]["vortag"]
    k15 = _kerzen(m, m.t.astype("datetime64[m]").astype(np.int64) // 15)
    atr15 = _wilder(k15["tr"], p["atr_n"])
    ende15 = (k15["key"] + 1) * 15                                  # Minute, in der die 15-Minuten-Kerze fertig ist
    sig = []
    for g in range(1, len(m.gi)):
        tag = m.gi[g]
        vh, vt = m.gh[g - 1], m.gl[g - 1]
        if not (np.isfinite(vh) and np.isfinite(vt) and vh > vt):
            continue
        a, b = m.first[tag], (m.first[tag + 1] if tag + 1 < len(m.first) else m.n)
        ms = m.ms17[a:b]
        drin = np.flatnonzero(ms >= 60)
        if len(drin) == 0:
            continue
        a2 = a + drin[0]
        raus_hoch, raus_tief = m.h[a2:b] > vh, m.l[a2:b] < vt
        treffer = np.flatnonzero(raus_hoch | raus_tief)
        if len(treffer) == 0:
            continue
        i0 = a2 + treffer[0]
        if m.ms17[i0] < p["fruehestens_ms17"] or (raus_hoch[treffer[0]] and raus_tief[treffer[0]]):
            continue
        d = 1 if raus_hoch[treffer[0]] else -1
        if mit_trend and m.trend_vor[g] != d:
            continue
        legen = int((m.t0[tag] + np.timedelta64(p["fruehestens_ms17"], "m")).astype("datetime64[m]").astype(np.int64))
        q = int(np.searchsorted(ende15, legen, side="right")) - 1
        if q < 0 or not np.isfinite(atr15[q]):
            continue
        sig.append({"i0": int(i0), "d": d, "lvl": float(vh if d > 0 else vt), "sd": float(p["stop_atr"] * atr15[q]),
                    "zd": float(p["ziel_anteil"] * (vh - vt)), "t_max": m.t0[tag] + np.timedelta64(24, "h")})
    return sig


def regel_dienstag(m: Markt, cfg: dict) -> list[dict]:
    p = cfg["regeln"]["dienstag"]
    zone, schluss = SCHLUSS[m.sym]
    lok = pd.DatetimeIndex(m.t).tz_localize("UTC").tz_convert(zone)
    lmin = np.asarray(lok.hour * 60 + lok.minute)
    ltag = lok.tz_localize(None).normalize().values.astype("datetime64[D]")
    kand = np.flatnonzero((lmin >= schluss) & (lmin < schluss + p["toleranz_min"]))
    erst = kand[np.r_[True, ltag[kand][1:] != ltag[kand][:-1]]]     # erste Kerze ab Börsenschluss, je Ortstag
    tage = ltag[erst]
    wt = np.asarray(pd.DatetimeIndex(tage).weekday)
    kurs = m.o[erst]                                                # Kurs zum Börsenschluss (Bid)
    davor = m.c[np.maximum(erst - 1, 0)]                            # letzter Kurs vor dem Börsenschluss
    sig = []
    for q in range(1, len(erst) - 1):
        if wt[q] != 0 or wt[q - 1] != 4 or (tage[q] - tage[q - 1]).astype(int) != 3:
            continue
        if wt[q + 1] != 1 or (tage[q + 1] - tage[q]).astype(int) != 1:
            continue
        if not davor[q] < kurs[q - 1]:
            continue
        i0 = int(erst[q])
        g = m.gpos[m.tix[i0]]
        if g < 1 or not np.isfinite(m.atr_vor[g]):
            continue
        sig.append({"i0": i0, "d": 1, "sd": float(p["stop_atr"] * m.atr_vor[g]), "zd": 0.0, "t_max": m.t[erst[q + 1]]})
    return sig


def signale(regel: str, m: Markt, cfg: dict, termine: np.ndarray) -> list[dict]:
    if regel == "ausbruch4h":
        return regel_ausbruch4h(m, cfg, termine)
    if regel == "vortag":
        return regel_vortag(m, cfg, False)
    if regel == "vortag_trend":
        return regel_vortag(m, cfg, True)
    if regel == "dienstag":
        return regel_dienstag(m, cfg)
    raise SystemExit(f"unbekannte Regel {regel}")


# ---------------------------------------------------------------------------------------------------------------------
# Auswertung

def pf(r: np.ndarray) -> float | None:
    r = np.asarray(r, float)
    plus, minus = r[r > 0].sum(), -r[r < 0].sum()
    if len(r) == 0:
        return None
    return float(plus / minus) if minus > 0 else float("inf")


def _rund(x, n=2):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None if x is None else (999.0 if x > 0 else -999.0)
    return round(float(x), n)


def termine_utc() -> np.ndarray:
    roh = yaml.safe_load(TERMINE.read_text(encoding="utf-8"))
    tz, out = roh.get("zeitzone", NY), []
    for k in ("fomc", "cpi", "nfp"):
        for tag in roh[k]["tage"]:
            out.append(pd.Timestamp(f"{pd.Timestamp(tag).date()} {roh[k]['uhrzeit']}").tz_localize(tz)
                       .tz_convert("UTC").tz_localize(None))
    return np.array(sorted(out), dtype="datetime64[ns]")


def rechne(arbeit: pathlib.Path, cfg: dict, bis: str | None, fenster: tuple[str, str], mitte: str,
           saat: int | None = None, mit_zwillingen: bool = True) -> tuple[dict, pd.DataFrame]:
    term = termine_utc()
    f0, f1 = np.datetime64(fenster[0]), np.datetime64(fenster[1])
    maerkte: dict[str, Markt] = {}
    cache: dict[tuple[str, str], pd.DataFrame] = {}
    ergebnis, alle = {}, []
    for name, v in cfg["varianten"].items():
        teile, summen, n_min = [], None, None
        for sym in v["maerkte"]:
            if sym not in maerkte:
                maerkte[sym] = Markt(sym, arbeit, cfg, bis, saat)
            m = maerkte[sym]
            if (v["regel"], sym) not in cache:
                cache[(v["regel"], sym)] = echte_trades(m, signale(v["regel"], m, cfg, term), cfg)
            tr = cache[(v["regel"], sym)]
            teile.append(tr.assign(variante=name) if not tr.empty else tr)
            gf = np.flatnonzero((m.gtag >= f0.astype("datetime64[D]")) & (m.gtag <= f1.astype("datetime64[D]")))
            if len(gf) < 200:
                continue
            n_min = len(gf) if n_min is None else min(n_min, len(gf))
        tr_alle = pd.concat([x for x in teile if not x.empty]) if any(not x.empty for x in teile) else pd.DataFrame()
        if tr_alle.empty:
            ergebnis[name] = {"trades": 0, "urteil": "durchgefallen"}
            continue
        tag = tr_alle["tag"].to_numpy().astype("datetime64[D]")
        im = (tag >= f0.astype("datetime64[D]")) & (tag <= f1.astype("datetime64[D]"))
        w = tr_alle[im].sort_values("ein_utc")
        alt = tr_alle[tag < f0.astype("datetime64[D]")]
        r, rr = w["R"].to_numpy(float), w["R_robust"].to_numpy(float)
        wtag = w["tag"].to_numpy().astype("datetime64[D]")
        h1, h2 = r[wtag < np.datetime64(mitte)], r[wtag >= np.datetime64(mitte)]
        j26 = r[wtag >= np.datetime64("2026-01-01")] if fenster[1] >= "2026" else np.array([])
        wochen = max((f1 - f0) / np.timedelta64(7, "D"), 1.0)
        lang, kurz = r[w["richtung"].to_numpy() > 0], r[w["richtung"].to_numpy() < 0]
        ohne5 = np.sort(r)[:-5] if len(r) > 5 else np.array([])
        e = {"regel": v["regel"], "maerkte": v["maerkte"], "trades": int(len(r)), "trades_je_woche": _rund(len(r) / wochen),
             "gewinnfaktor": _rund(pf(r)), "summe_R": _rund(r.sum()), "R_je_trade": _rund(r.mean() if len(r) else 0, 3),
             "trefferquote": _rund((r > 0).mean() if len(r) else 0), "gewinnfaktor_robust": _rund(pf(rr)),
             "haelfte_1": {"trades": int(len(h1)), "gewinnfaktor": _rund(pf(h1))},
             "haelfte_2": {"trades": int(len(h2)), "gewinnfaktor": _rund(pf(h2))},
             "jahr_2026": {"trades": int(len(j26)), "gewinnfaktor": _rund(pf(j26))},
             "long": {"trades": int(len(lang)), "gewinnfaktor": _rund(pf(lang)), "summe_R": _rund(lang.sum())},
             "short": {"trades": int(len(kurz)), "gewinnfaktor": _rund(pf(kurz)), "summe_R": _rund(kurz.sum())},
             "ohne_5_beste": {"gewinnfaktor": _rund(pf(ohne5)), "summe_R": _rund(ohne5.sum())},
             "je_markt": {s: {"trades": int((w["markt"] == s).sum()), "gewinnfaktor": _rund(pf(w.loc[w["markt"] == s, "R"])),
                              "summe_R": _rund(w.loc[w["markt"] == s, "R"].sum())} for s in v["maerkte"]},
             "auskunft_vor_fenster": {"trades": int(len(alt)), "gewinnfaktor": _rund(pf(alt["R"])) if len(alt) else None,
                                      "summe_R": _rund(alt["R"].sum()) if len(alt) else None}}
        if mit_zwillingen and n_min is not None and len(r) > 0:
            schritte = np.arange(1, n_min - cfg["zwilling"]["sperre_davor_tage"])
            summen = np.zeros(len(schritte))
            for sym in v["maerkte"]:
                m = maerkte[sym]
                gf = np.flatnonzero((m.gtag >= f0.astype("datetime64[D]")) & (m.gtag <= f1.astype("datetime64[D]")))
                if len(gf) < 200:
                    continue
                wm = w[w["markt"] == sym]
                summen += zwillings_summen(m, wm, int(gf[0]), int(gf[-1]), schritte, cfg)
            echt = float(r.sum())
            besser = int((summen >= echt).sum())
            sa = float(summen.std(ddof=1))
            e["zufall"] = {"laeufe": int(len(schritte)), "geschlagen_pct": _rund(100.0 * (summen < echt).mean(), 1),
                           "p": (1 + besser) / (len(schritte) + 1), "mittel_R": _rund(summen.mean()),
                           "streuung_R": _rund(sa), "z": _rund((echt - summen.mean()) / sa if sa > 0 else 0.0),
                           "summe_fuer_z3": _rund(summen.mean() + 3 * sa)}
        ergebnis[name] = e
        alle.append(w)
    urteile(ergebnis, cfg)
    spalten = ["variante", "markt", "ein_utc", "aus_utc", "richtung", "einstieg", "ausstieg", "stop_abstand",
               "ziel_abstand", "R", "R_robust", "gebuehr_R"]
    return ergebnis, (pd.concat(alle)[spalten] if alle else pd.DataFrame(columns=spalten))


def urteile(erg: dict, cfg: dict) -> None:
    h = cfg["huerden"]
    mit_p = sorted(((e["zufall"]["p"], n) for n, e in erg.items() if "zufall" in e))
    anzahl = len(cfg["varianten"])                                  # Holm über wirklich alle Varianten
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
        rang_ok = bool(z) and z["geschlagen_pct"] >= h["min_rang_pct"]
        if not rang_ok:
            gruende.append("Zufall 95 %")
        e["holm"] = n in holm_ok
        streng = []
        if not e["holm"]:
            streng.append("Holm")
        if not z or z["z"] < h["min_z"]:
            streng.append("z unter 3")
        e["durchgefallen_bei"] = gruende + streng
        e["urteil"] = "durchgefallen" if gruende else ("Kandidat" if streng else "bestanden")


def schreibe(erg: dict, trades: pd.DataFrame, cfg: dict, ziel: pathlib.Path, kopf: dict) -> None:
    ziel.parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(str(ziel) + ".json").write_text(json.dumps({"kopf": kopf, "varianten": erg}, indent=1, ensure_ascii=False,
                                                            default=str) + "\n", encoding="utf-8")
    trades.to_csv(str(ziel) + "_trades.csv.gz", index=False, float_format="%.6g")


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--festlegen":
        zeile = KEY + sha256_text(VORAB.read_text(encoding="utf-8"))
        journal_add(zeile)
        print(zeile)
        return 0
    modus, arbeit = argv[0], pathlib.Path(argv[1])
    if modus == "entwicklung":
        cfg = lade_vorab(pruefen=False)
        cfg["varianten"] = {n: {**v, "maerkte": [s for s in v["maerkte"] if s != "GRXEUR"]} for n, v in cfg["varianten"].items()}
        erg, tr = rechne(arbeit, cfg, "2023-12-31T23:59", ("2021-03-01", "2023-12-29"), "2022-08-01")
        schreibe(erg, tr, cfg, arbeit / "entwicklung", {"modus": "entwicklung, nur Kurse bis Ende 2023, kein Ergebnis"})
    elif modus == "probelauf":
        cfg = lade_vorab(pruefen=False)
        saat = int(argv[2])
        f = cfg["fenster"]
        erg, tr = rechne(arbeit, cfg, None, (f["von"], f["bis"]), f["mitte"], saat=saat)
        schreibe(erg, tr, cfg, arbeit / f"probelauf_{saat}", {"modus": "erfundener Markt ohne Vorteil", "saat": saat})
    elif modus == "rechnen":
        cfg = lade_vorab(pruefen=True)
        f = cfg["fenster"]
        erg, tr = rechne(arbeit, cfg, None, (f["von"], f["bis"]), f["mitte"])
        kopf = {"modus": "Rechnung", "vorab_sha256": sha256_text(VORAB.read_text(encoding="utf-8")), "fenster": f}
        schreibe(erg, tr, cfg, ERGEBNIS, kopf)
        schreibe(erg, tr, cfg, arbeit / "ergebnis_rueckblick", kopf)
    else:
        raise SystemExit(__doc__)
    for n, e in erg.items():
        z = e.get("zufall", {})
        print(f"{n:28s} {e.get('trades', 0):5d} T  GF {e.get('gewinnfaktor')}  rob {e.get('gewinnfaktor_robust')}  "
              f"Summe {e.get('summe_R')}  H {e.get('haelfte_1', {}).get('gewinnfaktor')}/{e.get('haelfte_2', {}).get('gewinnfaktor')}  "
              f"Zufall {z.get('geschlagen_pct')} %  z {z.get('z')}  -> {e.get('urteil')} {e.get('durchgefallen_bei', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
