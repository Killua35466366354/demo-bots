"""Runde "YouTube 19.11.2026": vier vorab festgelegte Regeln aus YouTube-Videos auf US-Indizes und Krypto.

Regeln: suche/VORAB_youtube_runde.yaml (versiegelt im Protokoll, bevor mit Kursen ab 2024 gerechnet wurde).
Die Rechnung (Kosten, ein Trade, Zwillinge, Hürden, Holm) ist die von suche/rueckblick.py, unverändert. Neu sind nur
die Regeln, die Krypto-Daten und ein Markt, bei dem alle sieben Tage Handelstage sind.

Aufruf:
    python -m suche.youtube_runde daten <Arbeit>               baut die npz-Dateien (Indizes wie rueckblick_daten, Krypto aus Binance)
    python -m suche.youtube_runde --festlegen                  schreibt die Prüfsumme der Regeldatei ins Protokoll
    python -m suche.youtube_runde entwicklung <Arbeit>         nur Kurse bis Ende 2023, prüft das Programm, kein Ergebnis
    python -m suche.youtube_runde probelauf <Arbeit> <Saat>    ganze Rechnung auf erfundenen Märkten ohne Vorteil
    python -m suche.youtube_runde rechnen <Arbeit>             die Rechnung (nur mit passender Prüfsumme)
"""
from __future__ import annotations

import contextlib
import io
import pathlib
import sys
import zipfile

import numpy as np
import pandas as pd
import yaml

from suche import rueckblick as rb
from suche import rueckblick_daten as rd
from suche.runde1 import journal_add, journal_lines, last_value, sha256_text

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_youtube_runde.yaml"
KEY = "VORAB_youtube_runde sha256 "
ERGEBNIS = ROOT / "suche" / "ergebnis_youtube_runde"
KRYPTO_ROH = pathlib.Path("/mnt/project-files/strategie-suche/daten/krypto/roh")
KRYPTO = {"BTCUSD": ("BTCUSDT", "BTCUSD"), "ETHUSD": ("ETHUSDT", "ETHUSD")}   # Symbol -> (Binance, Capital.com-Epic)
NY = rb.NY
MIN = rb.MIN


def lade_vorab(pruefen: bool = True) -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if pruefen and last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("VORAB_youtube_runde.yaml passt nicht zur Prüfsumme im Protokoll. Erst versiegeln, dann rechnen.")
    return yaml.safe_load(text)["youtube_runde"]


# ---------------------------------------------------------------------------------------------------------------------
# Daten

def _binance_monat(pfad: pathlib.Path) -> pd.DataFrame:
    with zipfile.ZipFile(pfad) as z:
        name = z.namelist()[0]
        roh = pd.read_csv(io.BytesIO(z.read(name)), header=None, usecols=[0, 1, 2, 3, 4])
    if not np.issubdtype(roh[0].dtype, np.number):                # manche Dateien haben eine Kopfzeile
        roh = roh.iloc[1:].astype(float)
    ms = roh[0].astype(np.int64)
    ms = np.where(ms > 10**14, ms // 1000, ms)                    # ab 2025 stehen Mikrosekunden in den Dateien
    t = pd.to_datetime(ms, unit="ms")
    return pd.DataFrame({"open": roh[1].astype(float).to_numpy(), "high": roh[2].astype(float).to_numpy(),
                         "low": roh[3].astype(float).to_numpy(), "close": roh[4].astype(float).to_numpy()}, index=t)


def spread_anteil(epic: str) -> np.ndarray:
    """Median von (Ask minus Bid) geteilt durch Bid je Viertelstunde der New Yorker Uhr, 96 Werte."""
    df = pd.read_csv(rd.KERZEN / f"{epic}_MINUTE_15.csv.gz", parse_dates=["utc"], index_col="utc")
    rel = ((df["open_ask"] - df["open_bid"]) / df["open_bid"]).astype(float)
    rel = rel[rel > 0]
    ny = rel.index.tz_localize("UTC").tz_convert(NY)
    slot = np.asarray(ny.hour * 4 + ny.minute // 15)
    prof = pd.Series(rel.to_numpy(), index=slot).groupby(level=0).median().reindex(range(96))
    return prof.interpolate(limit_direction="both").to_numpy(float)


def baue_krypto(sym: str, ziel: pathlib.Path) -> dict:
    binance, epic = KRYPTO[sym]
    teile = [_binance_monat(p) for p in sorted(KRYPTO_ROH.glob(f"{binance}-5m-*.zip"))]
    df = pd.concat(teile)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    utc = df.index
    ny = utc.tz_localize("UTC").tz_convert(NY).tz_localize(None)
    tag = (ny + pd.Timedelta(hours=7)).normalize()               # Handelstag beginnt 17:00 New York
    nymin = np.asarray(ny.hour * 60 + ny.minute, dtype=np.int32)
    prof = spread_anteil(epic)
    sp = prof[np.asarray(ny.hour * 4 + ny.minute // 15)] * df["open"].to_numpy(float)
    np.savez_compressed(
        ziel / f"{sym}.npz",
        t=utc.values.astype("datetime64[ns]"), o=df["open"].to_numpy(float), h=df["high"].to_numpy(float),
        l=df["low"].to_numpy(float), c=df["close"].to_numpy(float), sp=sp.astype(float), nymin=nymin,
        tag=tag.values.astype("datetime64[D]"), prof=prof)
    return {"symbol": sym, "kerzen": int(len(df)), "von": str(utc[0]), "bis": str(utc[-1]),
            "spread_anteil_median": float(np.median(prof))}


# ---------------------------------------------------------------------------------------------------------------------
# Markt: wie rueckblick.Markt, bei Krypto sind alle sieben Tage Handelstage

class Markt(rb.Markt):
    def __init__(self, sym: str, arbeit: pathlib.Path, cfg: dict, bis: str | None = None, saat: int | None = None):
        if sym not in cfg["daten"].get("krypto_alle_tage", []):
            super().__init__(sym, arbeit, cfg, bis, saat)
            return
        z = np.load(arbeit / f"{sym}.npz")
        t = z["t"]
        ok = np.ones(len(t), bool)
        if bis is not None:
            ok &= t <= np.datetime64(bis)
        self.sym, self.klasse = sym, "krypto"
        self.t = t[ok]
        self.o, self.h, self.l, self.c = (z[k][ok].astype(float) for k in "ohlc")
        self.sp, self.nymin, tag = z["sp"][ok].astype(float), z["nymin"][ok].astype(np.int64), z["tag"][ok]
        if saat is not None:
            self._ohne_vorteil(saat)
            self.sp = z["prof"][(self.nymin // 15)] * self.o      # Spread folgt dem erfundenen Kurs
        self.n = len(self.t)
        self.ms17 = (self.nymin - 17 * 60) % 1440
        self.tage, self.first = np.unique(tag, return_index=True)
        self.tix = np.searchsorted(self.tage, tag)
        anzahl = np.diff(np.r_[self.first, self.n])
        gueltig = anzahl >= cfg["daten"]["min_kerzen_je_tag"]   # alle sieben Tage
        grenze = (pd.DatetimeIndex(self.tage) - pd.Timedelta(days=1) + pd.Timedelta(hours=17))
        self.t0 = grenze.tz_localize(NY).tz_convert("UTC").tz_localize(None).values.astype("datetime64[ns]")
        letzte = np.r_[self.first[1:], self.n] - 1
        hh = np.where(self.ms17 >= 60, self.h, -np.inf)
        ll = np.where(self.ms17 >= 60, self.l, np.inf)
        dh, dl, dc = np.maximum.reduceat(hh, self.first), np.minimum.reduceat(ll, self.first), self.c[letzte]
        self.gi = np.flatnonzero(gueltig)
        self.gpos = np.full(len(self.tage), -1, np.int64)
        self.gpos[self.gi] = np.arange(len(self.gi))
        self.gh, self.gl, self.gc = dh[self.gi], dl[self.gi], dc[self.gi]
        vc = np.r_[np.nan, self.gc[:-1]]
        tr = np.fmax(self.gh - self.gl, np.fmax(np.abs(self.gh - vc), np.abs(self.gl - vc)))
        atr = pd.Series(tr).rolling(14).mean().to_numpy()
        self.atr_vor = np.r_[np.nan, atr[:-1]]
        ema = pd.Series(self.gc).ewm(span=50, adjust=False).mean().to_numpy()
        e5 = np.r_[np.full(5, np.nan), ema[:-5]]
        warm = np.arange(len(self.gc)) >= cfg["trend"]["vorlauf_tage"]
        hoch, tief = (self.gc > ema) & (ema > e5) & warm, (self.gc < ema) & (ema < e5) & warm
        trend = hoch.astype(np.int64) - tief.astype(np.int64)
        self.trend_vor = np.r_[0, trend[:-1]]
        self.gtag = self.tage[self.gi]


# ---------------------------------------------------------------------------------------------------------------------
# Regeln. Jede gibt Signale zurück wie in rueckblick.py: i0, d, sd, zd, t_max, lvl (nur Stop-Order).

def _erste_ab(m: Markt, ab: np.ndarray, toleranz_min: int) -> np.ndarray:
    """Index der ersten Kerze ab jeder Zeit in ab, -1 wenn binnen toleranz_min keine Kerze kommt."""
    i = np.searchsorted(m.t, ab)
    ok = i < m.n
    ic = np.minimum(i, m.n - 1)
    ok &= (m.t[ic] - ab) <= np.timedelta64(toleranz_min, "m")
    return np.where(ok, i, -1)


def regel_williams(m: Markt, cfg: dict) -> list[dict]:
    p = cfg["regeln"]["williams"]
    sitz = (m.nymin >= p["sitzung_von_min"]) & (m.nymin < p["sitzung_bis_min"])
    idx = np.flatnonzero(sitz)
    if len(idx) == 0:
        return []
    tix = m.tix[idx]
    a = np.flatnonzero(np.r_[True, tix[1:] != tix[:-1]])
    b = np.r_[a[1:], len(idx)] - 1
    tage = tix[a]                                                   # Index in m.tage
    anzahl = b - a + 1
    H, L = np.maximum.reduceat(m.h[idx], a), np.minimum.reduceat(m.l[idx], a)
    C = m.c[idx[b]]
    letzte_min = m.nymin[idx[b]]
    voll = (anzahl >= p["min_kerzen_sitzung"]) & (letzte_min >= p["sitzung_bis_min"] - 5)
    keep = np.flatnonzero(voll)
    tage, H, L, C = tage[keep], H[keep], L[keep], C[keep]
    n = p["tage"]
    hh = pd.Series(H).rolling(n).max().to_numpy()
    ll = pd.Series(L).rolling(n).min().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        wr = -100.0 * (hh - C) / (hh - ll)
    # Kurs zum Börsenschluss: Eröffnung der ersten Kerze ab 16:00 New York am selben Handelstag
    schluss_utc = (pd.DatetimeIndex(m.tage[tage]) + pd.Timedelta(minutes=p["sitzung_bis_min"])).tz_localize(NY) \
        .tz_convert("UTC").tz_localize(None).values.astype("datetime64[ns]")
    i_s = _erste_ab(m, schluss_utc, p["toleranz_min"])
    i_s = np.where((i_s >= 0) & (m.tix[np.maximum(i_s, 0)] == tage), i_s, -1)
    raus = np.zeros(len(C), bool)
    raus[1:] = (C[1:] > H[:-1]) | (wr[1:] > p["raus_ueber"])
    sig = []
    for q in range(n, len(C) - 1):
        if not (wr[q] < p["kauf_unter"]) or i_s[q] < 0:
            continue
        i0 = int(i_s[q])
        g = m.gpos[m.tix[i0]]
        if g < 1 or not np.isfinite(m.atr_vor[g]):
            continue
        aus = None
        for e in range(q + 1, min(q + 1 + p["max_tage"], len(C))):
            if i_s[e] < 0:
                continue
            aus = e
            if raus[e]:
                break
        if aus is None:
            continue
        sig.append({"i0": i0, "d": 1, "sd": float(p["stop_atr"] * m.atr_vor[g]), "zd": 0.0, "t_max": m.t[i_s[aus]]})
    return sig


def regel_cme(m: Markt, cfg: dict) -> list[dict]:
    p = cfg["regeln"]["cme_luecke"]
    ny = pd.DatetimeIndex(m.t).tz_localize("UTC").tz_convert(NY)
    tage = pd.date_range(ny[0].normalize().tz_localize(None), ny[-1].normalize().tz_localize(None), freq="D")
    freitage = tage[tage.weekday == p["ref_wochentag"]]
    ref_t = (freitage + pd.Timedelta(minutes=p["ref_min"])).tz_localize(NY).tz_convert("UTC").tz_localize(None)
    sonntage = freitage + pd.Timedelta(days=2)
    ein_t = (sonntage + pd.Timedelta(minutes=p["ein_min"])).tz_localize(NY).tz_convert("UTC").tz_localize(None)
    raus_t = (freitage + pd.Timedelta(days=7, minutes=p["ref_min"])).tz_localize(NY).tz_convert("UTC").tz_localize(None)
    i_ref = _erste_ab(m, ref_t.values.astype("datetime64[ns]"), p["toleranz_min"])
    i_ein = _erste_ab(m, ein_t.values.astype("datetime64[ns]"), p["toleranz_min"])
    sig = []
    for q in range(len(freitage)):
        if i_ref[q] < 0 or i_ein[q] < 0:
            continue
        f, e = m.o[i_ref[q]], m.o[i_ein[q]]
        luecke = (e - f) / f
        if abs(luecke) < p["min_luecke"]:
            continue
        d = -1 if luecke > 0 else 1
        abstand = float(abs(e - f))
        sig.append({"i0": int(i_ein[q]), "d": d, "sd": abstand, "zd": abstand,
                    "t_max": raus_t[q].to_datetime64().astype("datetime64[ns]")})
    return sig


def regel_montag(m: Markt, cfg: dict) -> list[dict]:
    p = cfg["regeln"]["montag"]
    tag_utc = m.t.astype("datetime64[D]")
    wt = np.asarray(pd.DatetimeIndex(tag_utc).weekday)
    sig = []
    montage = np.unique(tag_utc[wt == 0])
    for mo in montage:
        a, b = np.searchsorted(m.t, mo.astype("datetime64[ns]")), np.searchsorted(m.t, (mo + np.timedelta64(1, "D")).astype("datetime64[ns]"))
        if b - a < cfg["daten"]["min_kerzen_je_tag"]:
            continue
        mh, ml = float(m.h[a:b].max()), float(m.l[a:b].min())
        breite = mh - ml
        if not breite > 0:
            continue
        ende = np.searchsorted(m.t, (mo + np.timedelta64(5, "D")).astype("datetime64[ns]"))  # Freitag 24:00 UTC
        oben = np.flatnonzero(m.h[b:ende] >= mh)
        unten = np.flatnonzero(m.l[b:ende] <= ml)
        jo = oben[0] if len(oben) else None
        ju = unten[0] if len(unten) else None
        if jo is None and ju is None:
            continue
        if jo is not None and ju is not None and jo == ju:
            continue
        if ju is None or (jo is not None and jo < ju):
            i0, d, lvl = b + int(jo), 1, mh
        else:
            i0, d, lvl = b + int(ju), -1, ml
        sig.append({"i0": int(i0), "d": d, "lvl": lvl, "sd": breite / 2.0, "zd": p["ziel_breiten"] * breite,
                    "t_max": (mo + np.timedelta64(7, "D")).astype("datetime64[ns]")})
    return sig


def signale(regel: str, m: Markt, cfg: dict, termine: np.ndarray) -> list[dict]:
    if regel == "williams":
        return regel_williams(m, cfg)
    if regel == "cme_luecke":
        return regel_cme(m, cfg)
    if regel == "montag":
        return regel_montag(m, cfg)
    if regel == "ausbruch4h":
        return rb.regel_ausbruch4h(m, cfg, termine)
    raise SystemExit(f"unbekannte Regel {regel}")


# ---------------------------------------------------------------------------------------------------------------------
# Rechnung: rueckblick.rechne unverändert, nur mit diesem Markt und diesen Regeln

@contextlib.contextmanager
def _diese_runde():
    alt = rb.Markt, rb.signale
    rb.Markt, rb.signale = Markt, signale
    try:
        yield
    finally:
        rb.Markt, rb.signale = alt


def rechne(arbeit: pathlib.Path, cfg: dict, bis, fenster, mitte, saat=None, mit_zwillingen=True):
    with _diese_runde():
        return rb.rechne(arbeit, cfg, bis, fenster, mitte, saat=saat, mit_zwillingen=mit_zwillingen)


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--festlegen":
        zeile = KEY + sha256_text(VORAB.read_text(encoding="utf-8"))
        journal_add(zeile)
        print(zeile)
        return 0
    modus, arbeit = argv[0], pathlib.Path(argv[1])
    if modus == "daten":
        arbeit.mkdir(parents=True, exist_ok=True)
        for sym in ("SPXUSD", "NSXUSD"):
            print(rd.baue(sym, arbeit), flush=True)
        for sym in KRYPTO:
            print(baue_krypto(sym, arbeit), flush=True)
        return 0
    if modus == "entwicklung":
        cfg = lade_vorab(pruefen=False)
        erg, tr = rechne(arbeit, cfg, "2023-12-31T23:59", ("2021-03-01", "2023-12-29"), "2022-08-01")
        rb.schreibe(erg, tr, cfg, arbeit / "entwicklung", {"modus": "entwicklung, nur Kurse bis Ende 2023, kein Ergebnis"})
    elif modus == "probelauf":
        cfg = lade_vorab(pruefen=False)
        saat = int(argv[2])
        f = cfg["fenster"]
        erg, tr = rechne(arbeit, cfg, None, (f["von"], f["bis"]), f["mitte"], saat=saat)
        rb.schreibe(erg, tr, cfg, arbeit / f"probelauf_{saat}", {"modus": "erfundener Markt ohne Vorteil", "saat": saat})
    elif modus == "rechnen":
        cfg = lade_vorab(pruefen=True)
        f = cfg["fenster"]
        erg, tr = rechne(arbeit, cfg, None, (f["von"], f["bis"]), f["mitte"])
        kopf = {"modus": "Rechnung", "vorab_sha256": sha256_text(VORAB.read_text(encoding="utf-8")), "fenster": f}
        rb.schreibe(erg, tr, cfg, ERGEBNIS, kopf)
        rb.schreibe(erg, tr, cfg, arbeit / "ergebnis_youtube_runde", kopf)
    else:
        raise SystemExit(__doc__)
    for n, e in erg.items():
        z = e.get("zufall", {})
        print(f"{n:22s} {e.get('trades', 0):5d} T  GF {e.get('gewinnfaktor')}  rob {e.get('gewinnfaktor_robust')}  "
              f"Summe {e.get('summe_R')}  H {e.get('haelfte_1', {}).get('gewinnfaktor')}/{e.get('haelfte_2', {}).get('gewinnfaktor')}  "
              f"Zufall {z.get('geschlagen_pct')} %  z {z.get('z')}  -> {e.get('urteil')} {e.get('durchgefallen_bei', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
