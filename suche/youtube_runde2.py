"""Zweite YouTube-Runde vom 19.11.2026: fünf vorab festgelegte Regeln aus ganz anderen Arten von YouTube-Videos.

Regeln: suche/VORAB_youtube_runde2.yaml (versiegelt im Protokoll, bevor mit Kursen ab 2024 gerechnet wurde).
Die Rechnung (Kosten, ein Trade, Zwillinge, Hürden, Holm) ist die von suche/rueckblick.py, unverändert. Der Markt mit
sieben Handelstagen für Krypto kommt aus suche/youtube_runde.py. Neu sind nur die fünf Regeln.

Aufruf:
    python -m suche.youtube_runde2 daten <Arbeit>               baut die npz-Dateien (HistData, Krypto)
    python -m suche.youtube_runde2 --festlegen                  schreibt die Prüfsumme der Regeldatei ins Protokoll
    python -m suche.youtube_runde2 entwicklung <Arbeit>         nur Kurse bis Ende 2023, prüft das Programm, kein Ergebnis
    python -m suche.youtube_runde2 probelauf <Arbeit> <Saat>    ganze Rechnung auf erfundenen Märkten ohne Vorteil
    python -m suche.youtube_runde2 rechnen <Arbeit>             die Rechnung (nur mit passender Prüfsumme)
"""
from __future__ import annotations

import contextlib
import pathlib
import sys

import numpy as np
import pandas as pd
import yaml

from suche import rueckblick as rb
from suche import rueckblick_daten as rd
from suche import youtube_runde as yr
from suche.runde1 import journal_add, journal_lines, last_value, sha256_text

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_youtube_runde2.yaml"
KEY = "VORAB_youtube_runde2 sha256 "
ERGEBNIS = ROOT / "suche" / "ergebnis_youtube_runde2"
NY = rb.NY
MIN = rb.MIN
HISTDATA = ("SPXUSD", "NSXUSD", "GRXEUR", "UKXGBP", "JPXJPY", "XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD")


def lade_vorab(pruefen: bool = True) -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if pruefen and last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("VORAB_youtube_runde2.yaml passt nicht zur Prüfsumme im Protokoll. Erst versiegeln, dann rechnen.")
    return yaml.safe_load(text)["youtube_runde2"]


Markt = yr.Markt                                       # wie suche/youtube_runde.py, Krypto mit sieben Handelstagen


# ---------------------------------------------------------------------------------------------------------------------
# Hilfen

def _ny_utc(tage: pd.DatetimeIndex, minute: int) -> np.ndarray:
    """Kalendertage (New York) plus Minute des Tages -> UTC als datetime64[ns]."""
    return (tage + pd.Timedelta(minutes=minute)).tz_localize(NY).tz_convert("UTC").tz_localize(None) \
        .values.astype("datetime64[ns]")


def _kerzen_4h(m: Markt) -> dict:
    """4-Std.-Kerzen wie rueckblick.regel_ausbruch4h (Beginn 18, 22, 2, 6, 10, 14 Uhr New York)."""
    ms18 = (m.nymin - 18 * 60) % 1440
    tag18 = (m.t - ms18.astype("timedelta64[m]")).astype("datetime64[D]").astype(np.int64)
    return rb._kerzen(m, tag18 * 6 + ms18 // 240)


def _kerzen_1h(m: Markt) -> dict:
    return rb._kerzen(m, m.t.astype("datetime64[h]").astype(np.int64))


def _rsi(c: np.ndarray, n: int) -> np.ndarray:
    d = np.diff(c, prepend=np.nan)
    auf = rb._wilder(np.where(d > 0, d, 0.0), n)
    ab = rb._wilder(np.where(d < 0, -d, 0.0), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = auf / ab
    return np.where(ab == 0, 100.0, 100.0 - 100.0 / (1.0 + rs))


def _pause(m: Markt, i0: int, cfg: dict) -> bool:
    """Kein Einstieg in der Stunde 17 bis 18 Uhr New York (Tageswechsel, breiter Spread). Krypto ausgenommen."""
    return m.klasse != "krypto" and m.ms17[i0] < cfg["daten"]["pause_min"]


def supertrend(H, L, C, atr, faktor):
    """Supertrend wie bei TradingView: Bänder um (Hoch+Tief)/2, Richtung wechselt, wenn der Schluss das Band kreuzt."""
    n = len(C)
    mitte = (H + L) / 2.0
    ub, lb = mitte + faktor * atr, mitte - faktor * atr
    fu, fl = ub.copy(), lb.copy()
    richtung = np.zeros(n, np.int64)
    linie = np.full(n, np.nan)
    for i in range(1, n):
        if not np.isfinite(atr[i]):
            continue
        if np.isfinite(fu[i - 1]) and np.isfinite(atr[i - 1]):
            fu[i] = ub[i] if (ub[i] < fu[i - 1] or C[i - 1] > fu[i - 1]) else fu[i - 1]
            fl[i] = lb[i] if (lb[i] > fl[i - 1] or C[i - 1] < fl[i - 1]) else fl[i - 1]
        alt = richtung[i - 1] if richtung[i - 1] != 0 else 1
        if alt > 0:
            richtung[i] = -1 if C[i] < fl[i] else 1
        else:
            richtung[i] = 1 if C[i] > fu[i] else -1
        linie[i] = fl[i] if richtung[i] > 0 else fu[i]
    return richtung, linie


# ---------------------------------------------------------------------------------------------------------------------
# Regeln. Jede gibt Signale zurück wie in rueckblick.py: i0, d, sd, zd, t_max, lvl (nur Stop-Order).

def regel_supertrend(m: Markt, cfg: dict) -> list[dict]:
    p = cfg["regeln"]["supertrend"]
    k = _kerzen_4h(m)
    H, L, C = k["H"], k["L"], k["C"]
    schluss = m.t[k["b"]] + 5 * MIN
    atr = rb._wilder(k["tr"], p["atr_n"])
    richtung, linie = supertrend(H, L, C, atr, p["faktor"])
    ema = pd.Series(C).ewm(span=p["ema"], adjust=False).mean().to_numpy()
    warm = np.arange(len(C)) >= p["ema"]
    wechsel = np.flatnonzero((richtung[1:] != richtung[:-1]) & (richtung[:-1] != 0)) + 1
    sig = []
    for w, j in enumerate(wechsel):
        d = int(richtung[j])
        if not warm[j] or k["n"][j] < p["min_kerzen"] or not np.isfinite(atr[j]):
            continue
        if (d > 0 and not C[j] > ema[j]) or (d < 0 and not C[j] < ema[j]):
            continue
        i0 = k["b"][j] + 1
        if i0 >= m.n - 1 or (m.t[i0] - schluss[j]) > p["frist_min"] * MIN or _pause(m, i0, cfg):
            continue
        kurs = m.o[i0]
        sd = float(np.clip(abs(kurs - linie[j]), p["stop_min_atr"] * atr[j], p["stop_max_atr"] * atr[j]))
        t_max = m.t[i0] + np.timedelta64(p["halte_tage_max"], "D")
        if w + 1 < len(wechsel):
            t_max = min(t_max, schluss[wechsel[w + 1]])
        sig.append({"i0": int(i0), "d": d, "sd": sd, "zd": float(p["ziel_r"] * sd), "t_max": t_max})
    return sig


def regel_bollinger(m: Markt, cfg: dict) -> list[dict]:
    p = cfg["regeln"]["bollinger_rsi"]
    k = _kerzen_1h(m)
    C = k["C"]
    schluss = m.t[k["b"]] + 5 * MIN
    s = pd.Series(C)
    mitte = s.rolling(p["bb_n"]).mean().to_numpy()
    sa = s.rolling(p["bb_n"]).std(ddof=0).to_numpy()
    oben, unten = mitte + p["bb_breite"] * sa, mitte - p["bb_breite"] * sa
    rsi = _rsi(C, p["rsi_n"])
    atr = rb._wilder(k["tr"], p["atr_n"])
    sig = []
    for j in range(p["bb_n"] + p["rsi_n"], len(C) - 1):
        if k["n"][j] < p["min_kerzen"] or not np.isfinite(atr[j]):
            continue
        if C[j] < unten[j] and rsi[j] < p["rsi_unten"]:
            d = 1
        elif C[j] > oben[j] and rsi[j] > p["rsi_oben"]:
            d = -1
        else:
            continue
        i0 = k["b"][j] + 1
        if i0 >= m.n - 1 or (m.t[i0] - schluss[j]) > p["frist_min"] * MIN or _pause(m, i0, cfg):
            continue
        zd = d * (mitte[j] - m.o[i0])
        if not zd > 0:
            continue
        sig.append({"i0": int(i0), "d": d, "sd": float(p["stop_atr"] * atr[j]), "zd": float(zd),
                    "t_max": m.t[i0] + np.timedelta64(p["halte_stunden"], "h")})
    return sig


def regel_nr7(m: Markt, cfg: dict) -> list[dict]:
    p = cfg["regeln"]["nr7"]
    n = p["tage"]
    r = m.gh - m.gl
    sig = []
    for g in range(n, len(r) - 3):
        if not (r[g] > 0 and r[g] < r[g - n + 1:g].min()):
            continue
        tag = m.gi[g + 1]
        a = m.first[tag]
        b = m.first[tag + 1] if tag + 1 < len(m.first) else m.n
        hoch, tief = m.gh[g], m.gl[g]
        frei = np.flatnonzero(m.ms17[a:b] >= cfg["daten"]["pause_min"])
        if len(frei) == 0:
            continue
        ix = a + frei
        oben = ix[m.h[ix] >= hoch]
        unten = ix[m.l[ix] <= tief]
        jo = oben[0] if len(oben) else None
        ju = unten[0] if len(unten) else None
        if jo is None and ju is None:
            continue
        if jo is not None and ju is not None and jo == ju:
            continue
        if ju is None or (jo is not None and jo < ju):
            i0, d, lvl = int(jo), 1, float(hoch)
        else:
            i0, d, lvl = int(ju), -1, float(tief)
        t_max = m.t0[m.gi[g + 1 + p["halte_tage"]]] - 5 * MIN      # letzte Kerze vor dem Tageswechsel
        sig.append({"i0": i0, "d": d, "lvl": lvl, "sd": float(hoch - tief), "zd": 0.0, "t_max": t_max})
    return sig


def regel_silver_bullet(m: Markt, cfg: dict) -> list[dict]:
    p = cfg["regeln"]["silver_bullet"]
    im = np.flatnonzero((m.nymin >= p["fenster_von_min"]) & (m.nymin < p["fenster_bis_min"]))
    sig = []
    if len(im) == 0:
        return sig
    tix = m.tix[im]
    starts = np.flatnonzero(np.r_[True, tix[1:] != tix[:-1]])
    ends = np.r_[starts[1:], len(im)]
    for s0, s1 in zip(starts, ends):
        ix = im[s0:s1]
        for q in range(2, len(ix)):
            k0, k1, k2 = ix[q - 2], ix[q - 1], ix[q]
            if k2 - k0 != 2 or (m.t[k2] - m.t[k0]) != 10 * MIN:
                continue
            if m.l[k2] > m.h[k0]:
                d = 1
            elif m.h[k2] < m.l[k0]:
                d = -1
            else:
                continue
            i0 = k2 + 1
            if i0 >= m.n - 1 or m.nymin[i0] > p["fenster_bis_min"] or m.tix[i0] != m.tix[k2]:
                break
            sd = (m.o[i0] - m.l[k0]) if d > 0 else (m.h[k0] - m.o[i0])
            if not sd > 0:
                break
            tag_ny = pd.Timestamp(m.t[k2]).tz_localize("UTC").tz_convert(NY).normalize().tz_localize(None)
            t_max = _ny_utc(pd.DatetimeIndex([tag_ny]), p["ausstieg_min"])[0]
            sig.append({"i0": int(i0), "d": d, "sd": float(sd), "zd": float(p["ziel_r"] * sd), "t_max": t_max})
            break                                              # nur die erste Lücke im Fenster
    return sig


def signale(regel: str, m: Markt, cfg: dict, termine: np.ndarray) -> list[dict]:
    if regel == "supertrend":
        return regel_supertrend(m, cfg)
    if regel == "bollinger_rsi":
        return regel_bollinger(m, cfg)
    if regel == "nr7":
        return regel_nr7(m, cfg)
    if regel == "silver_bullet":
        return regel_silver_bullet(m, cfg)
    raise SystemExit(f"unbekannte Regel {regel}")


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
        for sym in HISTDATA:
            print(rd.baue(sym, arbeit), flush=True)
        for sym in yr.KRYPTO:
            print(yr.baue_krypto(sym, arbeit), flush=True)
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
        rb.schreibe(erg, tr, cfg, arbeit / "ergebnis_youtube_runde2", kopf)
    else:
        raise SystemExit(__doc__)
    for n, e in erg.items():
        z = e.get("zufall", {})
        print(f"{n:22s} {e.get('trades', 0):5d} T  GF {e.get('gewinnfaktor')}  rob {e.get('gewinnfaktor_robust')}  "
              f"Summe {e.get('summe_R')}  H {e.get('haelfte_1', {}).get('gewinnfaktor')}/{e.get('haelfte_2', {}).get('gewinnfaktor')}  "
              f"2026 {e.get('jahr_2026', {}).get('gewinnfaktor')}  Zufall {z.get('geschlagen_pct')} %  z {z.get('z')}  "
              f"-> {e.get('urteil')} {e.get('durchgefallen_bei', '')}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
