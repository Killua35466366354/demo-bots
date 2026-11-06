"""Gold-Short-Bot, Komitee 2: sechs Varianten der Führung nach suche/VORAB_gold_short_k2.yaml (Prüfsumme im Protokoll).

    python -m suche.gold_short_k2 <ausgabe-ordner>     # rechnet alles, schreibt k2.json, BERICHT.md und chart.json

Braucht die HistData-Kerzen und den Capital.com-Spread aus dem Repo portfolio-manager (suche/runde12.py), Pfad über
PORTFOLIO_MANAGER (Standard /home/user/portfolio-manager). Nur Forschung, kein Teil des laufenden Bots und nicht in CI.
Die Führung rechnet Kerze für Kerze. Mit der Grundeinstellung gibt sie genau die Trades von gold/short_bot.fuehre_neu.
"""
from __future__ import annotations

import contextlib
import json
import os
import pathlib
import sys
from dataclasses import dataclass, field, replace
from typing import Callable

import numpy as np
import pandas as pd

from gold import short_bot as sb
from gold import tiktok_schatten as ts
from suche.runde1 import sha256_text, journal_lines, last_value

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_gold_short_k2.yaml"
KEY = "VORAB_gold_short_k2 sha256 "
PM = pathlib.Path(os.environ.get("PORTFOLIO_MANAGER", "/home/user/portfolio-manager"))
DUKA = pathlib.Path("/mnt/project-files/strategie-suche/daten/XAUUSD_dukascopy_1m_20261026_20261105.csv.gz")
SEITEN = sb.SEITEN
BOX_SEITEN = ("gross_box_kerze", "gross_box")


# --------------------------------------------------------------------------------------------------------------------
# Kerzen

def _pm():
    """runde12 aus portfolio-manager laden, ohne dass dessen Pakete gold/suche die von demo-bots verdecken."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("pm_runde12", PM / "suche" / "runde12.py")
    alt = sys.path[:]
    gesichert = {m: sys.modules.pop(m) for m in list(sys.modules) if m.split(".")[0] in ("gold", "suche")}
    sys.path.insert(0, str(PM))
    try:
        mod = importlib.util.module_from_spec(spec)
        sys.modules["pm_runde12"] = mod
        spec.loader.exec_module(mod)
        return mod.DATEN, mod.spread_anteil()
    finally:
        sys.path[:] = alt
        for m in [m for m in sys.modules if m.split(".")[0] in ("gold", "suche")]:
            del sys.modules[m]
        sys.modules.update(gesichert)


_HD: dict = {}


def kerzen15(von: str, bis: str, duka: bool = False) -> pd.DataFrame:
    if "hd" not in _HD:
        daten, anteil = _pm()
        hd = pd.read_csv(daten, index_col=0, parse_dates=True)
        _HD["hd"] = hd[~hd.index.duplicated(keep="last")].sort_index()[["open", "high", "low", "close"]]
        _HD["anteil"] = anteil
    df = _HD["hd"].loc[von:bis + " 23:59"]
    if duka:
        dk = pd.read_csv(DUKA, index_col=0, parse_dates=True)
        m5 = dk.resample("5min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        df = pd.concat([df, m5[m5.index > df.index[-1]]])
    b = df.groupby(df.index.floor("15min")).agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    nyz = b.index.tz_localize("UTC").tz_convert("America/New_York")
    slot = np.asarray(nyz.hour * 60 + (nyz.minute // 15) * 15)
    b["spread"] = _HD["anteil"].reindex(slot).to_numpy(float) * b["open"].to_numpy(float)
    return b


def basis(von: str, bis: str, duka: bool = False) -> ts.Basis:
    x = kerzen15(von, bis, duka)
    return ts.basis(x[["open", "high", "low", "close"]], x["spread"])


# --------------------------------------------------------------------------------------------------------------------
# Führung Kerze für Kerze

@dataclass
class Cfg:
    name: str = "heute"
    ziele: Callable | None = None          # (seite, ziele, gewichte) -> (ziele in R, gewichte); None = mal 0,75
    pruefer_f: float | None = 0.5
    halten: bool = True
    einstand_mfe: float | None = None      # Stop erst ab diesem Höchstgewinn auf Einstand (sonst bei Ziel 1)
    ernte: dict | None = None              # {"min_r": 0.3, "anteil": 2/3}
    reife: dict | None = None              # {"ab_r": 2.0, "stop_r": 1.0, "st_faktor": 1.75}
    jf_4h: bool = False                    # Box-Seiten: Rest bis zum 4-Std.-Bruch gegen den Trade
    extra: dict = field(default_factory=dict)


_AKT: dict = {"seite": None, "log": None, "cfg": None, "jf_max": None, "cache": {}}


def _cache(b: ts.Basis, key: str):
    c = _AKT["cache"].setdefault(id(b), {"_b": b})
    if key in c:
        return c[key]
    if key in ("k1", "k-1"):
        d = 1 if key == "k1" else -1
        c[key] = (b.l, b.h, b.o, b.c) if d > 0 else (b.l + b.sp, b.h + b.sp, b.o + b.sp, b.c + b.sp)
    elif key == "sitzung":
        ende = pd.DatetimeIndex(b.t) + pd.Timedelta(minutes=15)
        lon = ende.tz_localize("UTC").tz_convert("Europe/London")
        ny = ende.tz_localize("UTC").tz_convert("America/New_York")
        hm_l = lon.hour * 60 + lon.minute
        hm_n = ny.hour * 60 + ny.minute
        c[key] = np.asarray((hm_l == 480) | (hm_n == 480) | (hm_n == 16 * 60 + 45))
    elif key.startswith("st"):
        faktor = float(key[2:])
        c[key] = ts.supertrend(b.h, b.l, b.c, faktor=faktor)[0]
    elif key == "bruch4h":
        h4 = ts.ebene(b, "4h")
        br = ts.strukturbrueche(h4)
        c[key] = {d: np.array(sorted(int(h4.i1[x.k]) + 1 for x in br if x.d == d), int) for d in (1, -1)}
    return c[key]


def naechster_bruch(b: ts.Basis, d: int, j0: int) -> int:
    """Index der Kerze, zu deren Eröffnung der nächste 4-Std.-Strukturbruch gegen einen Trade in Richtung d bekannt
    ist (nur fertige 4-Std.-Kerzen). len(b), wenn keiner kommt."""
    arr = _cache(b, "bruch4h")[-d]
    i = int(np.searchsorted(arr, j0, side="right"))
    return int(arr[i]) if i < len(arr) else len(b)


def fuehre_var(b, d, j0, jf, einstieg, stop, ziele=ts.ZIELE, gewichte=ts.GEWICHTE, grund_ende="gegensignal"):
    cfg: Cfg = _AKT["cfg"]
    seite = _AKT["seite"]
    n = len(b)
    roh = (tuple(ziele), tuple(gewichte), grund_ende)
    if cfg.jf_4h and seite in BOX_SEITEN:
        jf, grund_ende = naechster_bruch(b, d, j0), "bruch_4h"
    if _AKT["jf_max"] is not None:
        jf = min(jf, _AKT["jf_max"])
    jf = min(jf, n)
    a = abs(einstieg - stop)
    if cfg.ziele is None:
        zl, gw = tuple(z * sb.ZIEL_FAKTOR for z in ziele), tuple(gewichte)
    else:
        zl, gw = cfg.ziele(seite, tuple(ziele), tuple(gewichte))
    L, H, O, C = _cache(b, "k1" if d > 0 else "k-1")
    sitzung = _cache(b, "sitzung") if cfg.ernte else None
    st = _cache(b, "st%s" % cfg.reife["st_faktor"]) if cfg.reife else None
    teile, rest, stop_akt, stop_ab, m, fehl = [], 1.0, stop, j0, 0, -1
    mfe, geerntet, reif, fertig = 0.0, False, False, False
    k = j0
    while k < jf:
        lo, hi, op = L[k], H[k], O[k]
        if cfg.pruefer_f and fehl < 0 and m == 0 and not geerntet:
            adv = (einstieg - lo) if d > 0 else (hi - einstieg)
            if adv >= cfg.pruefer_f * a:
                fehl = k
        if k >= stop_ab and ((d > 0 and lo <= stop_akt) or (d < 0 and hi >= stop_akt)):
            px = min(op, stop_akt) if d > 0 else max(op, stop_akt)
            lage = d * (stop_akt - einstieg)
            g = "nachzug" if lage > 1e-9 else ("einstand" if abs(lage) <= 1e-9 else "stop")
            teile.append({"w": rest, "px": float(px), "j": k, "grund": g}); rest = 0.0; fertig = True
            break
        if fehl >= 0 and k > fehl and ((d > 0 and hi >= einstieg) or (d < 0 and lo <= einstieg)):
            px = max(op, einstieg) if d > 0 else min(op, einstieg)
            teile.append({"w": rest, "px": float(px), "j": k, "grund": "pruefer"}); rest = 0.0; fertig = True
            break
        if fehl < 0:
            while m < len(zl):
                ziel = einstieg + d * zl[m] * a
                if not ((d > 0 and hi >= ziel) or (d < 0 and lo <= ziel)):
                    break
                px = max(op, ziel) if d > 0 else min(op, ziel)
                w = min(gw[m], rest)
                teile.append({"w": w, "px": float(px), "j": k, "grund": f"tp{m + 1}"}); rest -= w
                if m == 0 and cfg.einstand_mfe is None and d * (stop_akt - einstieg) < 0:
                    stop_akt, stop_ab = einstieg, k + 1
                m += 1
            if rest <= 1e-9:
                fertig = True
                break
        fav = (hi - einstieg) if d > 0 else (einstieg - lo)
        mfe = max(mfe, fav / a)
        if cfg.einstand_mfe is not None and mfe >= cfg.einstand_mfe and d * (stop_akt - einstieg) < 0:
            stop_akt, stop_ab = einstieg, k + 1
        if cfg.reife:
            if mfe >= cfg.reife["ab_r"]:
                reif = True
                neu = einstieg + d * cfg.reife["stop_r"] * a
                if d * (neu - stop_akt) > 0:
                    stop_akt, stop_ab = neu, k + 1
            if reif and st[k] == -d and k + 1 < n:
                teile.append({"w": rest, "px": float(O[k + 1]), "j": k + 1, "grund": "reife"}); rest = 0.0; fertig = True
                break
        if cfg.ernte and not geerntet and m == 0 and fehl < 0 and sitzung[k] and k + 1 < n:
            gewinn = (C[k] - einstieg) if d > 0 else (einstieg - C[k])
            if gewinn >= cfg.ernte["min_r"] * a:
                w = rest * cfg.ernte["anteil"]
                teile.append({"w": w, "px": float(O[k + 1]), "j": k + 1, "grund": "ernte"}); rest -= w
                geerntet, m = True, len(zl) - 1
                if d * (stop_akt - einstieg) < 0:
                    stop_akt, stop_ab = einstieg, k + 1
        k += 1
    offen = False
    if not fertig and rest > 1e-9:
        if jf < n:
            teile.append({"w": rest, "px": float(O[jf]), "j": jf, "grund": grund_ende})
        else:
            offen = True
    if cfg.halten:
        teile, offen = sb.halten(b, d, einstieg, stop, teile, offen, grund_ende)
    if _AKT["log"] is not None:
        _AKT["log"][(seite, int(j0), int(d))] = {
            "jf": int(jf), "fehl": int(fehl), "offen": bool(offen),
            "jende": n if offen else max(t["j"] for t in teile),
            "ziele": roh[0], "gewichte": roh[1], "grund_ende": roh[2]}
    return teile, offen


@contextlib.contextmanager
def mit(cfg: Cfg, log: dict | None, seite: str, jf_max: int | None = None):
    alt = ts.fuehre
    ts.fuehre = fuehre_var
    _AKT.update(seite=seite, log=log, cfg=cfg, jf_max=jf_max)
    try:
        yield
    finally:
        ts.fuehre = alt
        _AKT.update(seite=None, log=None, cfg=None, jf_max=None)


def simuliere(b: ts.Basis, cfg: Cfg):
    """Wie short_bot.simuliere, nur mit fuehre_var(cfg)."""
    m15, h1, h4 = ts.ebene(b, "15m"), ts.ebene(b, "1h"), ts.ebene(b, "4h")
    box4 = ts.signalbox(b, h4, ts.strukturbrueche(h4))           # Filter-Boxen mit der alten Führung wie der Bot
    box1 = ts.signalbox(b, h1, ts.strukturbrueche(h1))
    log, out = {}, {}
    with mit(cfg, log, "gross_klein_3"):
        out["gross_klein_3"] = ts.gross_klein(b, m15, ts.strukturbrueche(m15), box4, box1)
    with mit(cfg, log, "gross_box_kerze"):
        out["gross_box_kerze"] = ts.gross_box(b, m15, h1, h4, kerze=True)
    with mit(cfg, log, "gross_box"):
        out["gross_box"] = ts.gross_box(b, m15, h1, h4, kerze=False)
    for seite, trs in out.items():
        for t in trs:
            j0 = int(np.searchsorted(b.t, np.datetime64(pd.Timestamp(t["einstieg_zeit"]))))
            info = log.get((seite, j0, int(t["richtung"]))) or {}
            t["_j0"], t["_jf"] = j0, info.get("jf")
            t["_fehl"], t["_jende"] = info.get("fehl", -1), info.get("jende", len(b))
            t["_info"] = info
    return out


# --------------------------------------------------------------------------------------------------------------------
# Die sechs Varianten (VORAB_gold_short_k2.yaml)

def _vorschuss(erst=0.5):
    def z(seite, ziele, gew):
        if seite == "gross_klein_3":
            return (erst, 1.5, 2.25), gew
        return (erst, ziele[1] * sb.ZIEL_FAKTOR), gew
    return z


def _laeufer(seite, ziele, gew):
    if seite == "gross_klein_3":
        return (0.75, 1.5), gew[:2]
    return (0.75,), gew[:1]


def _doppelt(seite, ziele, gew):
    return tuple(x * sb.ZIEL_FAKTOR * 2 for x in ziele), gew


HEUTE = Cfg()
VARIANTEN = {
    "vorschuss": Cfg("vorschuss", ziele=_vorschuss(0.5), einstand_mfe=1.0),
    "sitzungs_ernte": Cfg("sitzungs_ernte", ernte={"min_r": 0.3, "anteil": 2 / 3}),
    "reife": Cfg("reife", reife={"ab_r": 2.0, "stop_r": 1.0, "st_faktor": 1.75}),
    "laeufer": Cfg("laeufer", ziele=_laeufer, jf_4h=True),
    "doppelte_box": Cfg("doppelte_box", ziele=_doppelt),
    "longs": Cfg("longs"),
}
NACHBARN = {
    "vorschuss_0.4": Cfg("vorschuss_0.4", ziele=_vorschuss(0.4), einstand_mfe=1.0),
    "vorschuss_0.6": Cfg("vorschuss_0.6", ziele=_vorschuss(0.6), einstand_mfe=1.0),
    "sitzungs_ernte_0.2": Cfg("sitzungs_ernte_0.2", ernte={"min_r": 0.2, "anteil": 2 / 3}),
    "sitzungs_ernte_0.4": Cfg("sitzungs_ernte_0.4", ernte={"min_r": 0.4, "anteil": 2 / 3}),
    "reife_1.5": Cfg("reife_1.5", reife={"ab_r": 1.5, "stop_r": 1.0, "st_faktor": 1.75}),
    "reife_2.5": Cfg("reife_2.5", reife={"ab_r": 2.5, "stop_r": 1.0, "st_faktor": 1.75}),
}


# --------------------------------------------------------------------------------------------------------------------
# Zusammenlegen und Kennzahlen

def kombi(trades: dict, longs: bool = False):
    """Shorts wie short_bot.kombi. longs: dazu die Longs derselben drei Seiten, gleiche Einstiege einmal, Sperre unter
    Longs, ein Long nur, wenn gerade kein genommener Short offen ist."""
    gen, weg, _ = sb.kombi(trades)
    gen = [(s, t) for s, t in gen]
    if not longs:
        return gen, weg, []
    sh = [t for _, t in gen]
    kand = sorted(((t["_j0"], r, s, t) for r, s in enumerate(SEITEN) for t in trades.get(s, []) if t["richtung"] > 0),
                  key=lambda x: (x[0], x[1]))
    gl, wl, offen, gesehen = [], [], [], set()
    for j0, _, s, t in kand:
        if j0 in gesehen:
            continue
        gesehen.add(j0)
        if any(x["_j0"] <= j0 < x["_jende"] for x in sh):
            continue
        offen = [o for o in offen if o["_jende"] > j0]
        if any(0 <= o["_fehl"] < j0 for o in offen):
            wl.append((s, t))
            continue
        gl.append((s, t))
        offen.append(t)
    return gen, weg, gl


def ab(gen, von, bis=None):
    a, z = pd.Timestamp(von), pd.Timestamp(bis + " 23:59") if bis else None
    return [(s, t) for s, t in gen if pd.Timestamp(t["einstieg_zeit"]) >= a and (z is None or pd.Timestamp(t["einstieg_zeit"]) <= z)]


def kurz(gen) -> dict:
    r = np.array([t["ergebnis_r"] for _, t in gen], float)
    if len(r) == 0:
        return {"trades": 0, "pf_r": None, "summe_r": 0.0, "trefferquote": None}
    g, v = r[r > 0].sum(), -r[r < 0].sum()
    return {"trades": int(len(r)), "pf_r": round(float(g / v), 3) if v > 0 else None,
            "summe_r": round(float(r.sum()), 1), "trefferquote": round(float((r > 0).mean()), 3)}


def rueckgang(gen) -> float:
    s = sorted(gen, key=lambda x: x[1]["_jende"])
    eq = np.cumsum([t["ergebnis_r"] for _, t in s]) if s else np.zeros(1)
    return round(float((np.maximum.accumulate(np.r_[0, eq]) - np.r_[0, eq]).max()), 1)


@contextlib.contextmanager
def kosten(faktor: float):
    alt = dict(ts.SATZ)
    ts.SATZ.update({k: v * faktor for k, v in alt.items()})
    try:
        yield
    finally:
        ts.SATZ.clear()
        ts.SATZ.update(alt)


def robust_basis(b: ts.Basis, faktor: float) -> ts.Basis:
    return ts.Basis(b.t, b.o, b.h, b.l, b.c, b.sp * faktor, b.tag, b.ny)


def zufall(b, gen, cfg: Cfg, laeufe: int, seed: int) -> dict:
    if not gen:
        return {"zufall": None}
    n = len(gen)
    rr = {1: np.zeros(n), -1: np.zeros(n)}
    for q, (s, t) in enumerate(gen):
        j0, je = t["_j0"], min(t["_jende"] + 1, len(b))
        info = t["_info"]
        for d in (1, -1):
            e0 = float(b.o[j0] + b.sp[j0] if d > 0 else b.o[j0])
            with mit(cfg, None, s, jf_max=je):
                tl, offen = fuehre_var(b, d, j0, je, e0, e0 - d * t["r_usd"], info["ziele"], info["gewichte"],
                                       info["grund_ende"])
            rr[d][q] = ts.ergebnis_r(b, d, j0, e0, t["r_usd"], tl, offen)
    gr = np.array([t["_j0"] for _, t in gen])
    ids = {g: i for i, g in enumerate(sorted(set(gr.tolist())))}
    grp = np.array([ids[g] for g in gr.tolist()])
    rng = np.random.default_rng(seed)
    wahl = rng.integers(0, 2, size=(laeufe, len(ids))).astype(bool)[:, grp]
    summen = np.where(wahl, rr[1], rr[-1]).sum(axis=1)
    echt = sum(t["ergebnis_r"] for _, t in gen)
    return {"zufall": round(float((summen < echt).mean() * 100), 1), "zufall_median_r": round(float(np.median(summen)), 1)}


def pruefe(k, kr, zuf, h1, h2, j26, kon) -> dict:
    checks = {"trades": k["trades"] >= 100, "pf_r": (k["pf_r"] or 0) >= 1.3, "pf_r_robust": (kr["pf_r"] or 0) >= 1.15,
              "zufall": (zuf or 0) >= 95, "haelfte_1": (h1["pf_r"] or 0) > 1.0, "haelfte_2": (h2["pf_r"] or 0) > 1.0,
              "jahr_2026": (j26["pf_r"] or 0) > 1.0, "kontrolle": (kon["pf_r"] or 0) > 1.0}
    return {"checks": checks, "bestanden": all(checks.values())}


def gruende(gen) -> dict:
    out: dict = {}
    for _, t in gen:
        g = t["grund"]
        o = out.setdefault(g, [0, 0.0])
        o[0] += 1
        o[1] += t["ergebnis_r"]
    return {g: {"trades": v[0], "summe_r": round(v[1], 1)} for g, v in sorted(out.items(), key=lambda x: x[1][1])}


def gold_lage(b: ts.Basis, gen) -> dict:
    """Trades bei steigendem und fallendem Gold: Schluss vor dem Einstieg über oder unter dem Schluss 20 Handelstage
    vorher (nur zur Information)."""
    tage = pd.Series(b.c, index=pd.DatetimeIndex(b.tag)).groupby(level=0).last()
    tag_idx = {t: i for i, t in enumerate(tage.index)}
    auf, ab_ = [], []
    for s, t in gen:
        j0 = t["_j0"]
        i = tag_idx.get(pd.Timestamp(b.tag[j0]))
        if i is None or i < 20:
            continue
        (auf if b.c[j0 - 1] > tage.iloc[i - 20] else ab_).append((s, t))
    return {"gold_steigt": kurz(auf), "gold_faellt": kurz(ab_)}


# --------------------------------------------------------------------------------------------------------------------
# Lauf

def check_vorab() -> dict:
    import yaml
    text = VORAB.read_text(encoding="utf-8")
    soll = last_value(journal_lines(), KEY)
    if soll != sha256_text(text):
        raise SystemExit("VORAB_gold_short_k2.yaml passt nicht zur Prüfsumme im Protokoll")
    return yaml.safe_load(text)["gold_short_k2"]


def rechne_variante(name: str, cfg: Cfg, ba, br, bk, vor: dict, longs: bool = False) -> dict:
    za, ko = vor["daten"]["zeitraum_a"], vor["daten"]["kontrolle"]
    h = vor["bewertung"]["haelften"]
    z = vor["bewertung"]["zufall"]
    rob = float(vor["kosten"]["robust_faktor"])
    tr = simuliere(ba, cfg)
    gen, weg, gl = kombi(tr, longs)
    teil = ab(gl if longs else gen, za["test_ab"], za["bis"])
    with kosten(rob):
        g2, _, l2 = kombi(simuliere(br, cfg), longs)
    teil_r = ab(l2 if longs else g2, za["test_ab"], za["bis"])
    gk, _, lk = kombi(simuliere(bk, cfg), longs)
    teil_k = ab(lk if longs else gk, ko["test_ab"], ko["bis"])
    k = kurz(teil)
    kr, kon = kurz(teil_r), kurz(teil_k)
    h1, h2 = kurz(ab(teil, *h["haelfte_1"])), kurz(ab(teil, *h["haelfte_2"]))
    j26 = kurz(ab(teil, "2026-01-01", za["bis"]))
    zf = zufall(ba, teil, cfg, int(z["laeufe"]), int(z["seed"]))
    res = {"zeitraum_a": k, "robust": kr, **zf, "haelfte_1": h1, "haelfte_2": h2, "jahr_2026": j26,
           "kontrolle_2022_2024": kon, **pruefe(k, kr, zf.get("zufall"), h1, h2, j26, kon),
           "je_seite": {s: kurz([x for x in teil if x[0] == s]) for s in SEITEN},
           "gruende": gruende(teil), "rueckgang_r": rueckgang(teil), "gesperrt": len(ab(weg, za["test_ab"], za["bis"])),
           **gold_lage(ba, teil)}
    if longs:
        alle = ab(gen + gl, za["test_ab"], za["bis"])
        res["zusammen_mit_shorts"] = kurz(alle)
        res["zusammen_kontrolle"] = kurz(ab(gk + lk, ko["test_ab"], ko["bis"]))
    print(name, k, "robust", kr.get("pf_r"), zf, "H1", h1["pf_r"], "H2", h2["pf_r"], "2026", j26["pf_r"],
          "Kontrolle", kon, "bestanden", res["bestanden"], flush=True)
    return res


BEISPIELE = {"461": "2026-10-28 05:00:00", "472": "2026-10-30 17:15:00", "473": "2026-11-03 04:00:00"}


def chart_trades(bd: ts.Basis, cfg: Cfg, longs: bool) -> tuple[list, list]:
    tr = simuliere(bd, cfg)
    gen, weg, gl = kombi(tr, longs)
    t_ = lambda x: int(pd.Timestamp(x).timestamp())
    rows = []
    for s, t in ab(gen + gl, "2024-11-01"):
        dist = t["r_usd"]
        info = t["_info"]
        zl, _ = (cfg.ziele or (lambda s_, z, g: (tuple(x * sb.ZIEL_FAKTOR for x in z), g)))(s, info["ziele"], info["gewichte"])
        d = t["richtung"]
        rows.append({"seite": s, "art": t.get("art"), "d": d, "ein": t_(t["einstieg_zeit"]), "px": t["einstieg"],
                     "stop": t["stop"], "r": dist,
                     "ziele": [round(t["einstieg"] + d * z * dist, 2) for z in zl if z < 100],
                     "teile": [{"g": x["grund"], "px": x["px"], "t": t_(x["zeit"]), "w": x["anteil"]} for x in t["teile"]],
                     "e": t["ergebnis_r"], "g": t["grund"], "offen": t["offen"],
                     "fehl": t_(bd.t[t["_fehl"]]) if t["_fehl"] >= 0 else None,
                     "normal": t_(bd.t[t["_jf"]]) if t["_jf"] is not None and t["_jf"] < len(bd) else None})
    rows.sort(key=lambda x: x["ein"])
    gesperrt = [{"seite": s, "ein": t_(t["einstieg_zeit"]), "d": t["richtung"], "px": t["einstieg"]}
                for s, t in ab(weg, "2024-11-01")]
    return rows, gesperrt


TITEL = {"heute": "Bot heute (Vergleich)", "vorschuss": "Vorschuss", "sitzungs_ernte": "Sitzungs-Ernte", "reife": "Reife-Prüfer",
         "laeufer": "Läufer", "doppelte_box": "Doppelte Box", "longs": "Longs dazu (nur Longs gewertet)"}


def _z(x, n=2):
    return "–" if x is None else f"{x:.{n}f}".replace(".", ",")


def bericht(res: dict) -> str:
    """Kurzer Bericht in Markdown aus k2.json."""
    zeilen = ["# Gold-Short-Bot, Komitee 2: Ergebnis", "",
              f"Vorab: suche/VORAB_gold_short_k2.yaml (sha256 {res['vorab_sha256'][:12]}…). Zeitraum A Einstieg 01.11.2024 bis "
              "30.10.2026, Kontrolle 01.11.2022 bis 31.10.2024. PF_R = Gewinnfaktor in R. Offene Trades am Ende mit Marktwert.", "",
              "| Regel | Trades | PF_R | Summe R | robust | Zufall | Hälfte 1 | Hälfte 2 | 2026 | Kontrolle PF_R | Kontrolle R | bestanden |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for name in ["heute"] + list(VARIANTEN):
        v = res["heute"] if name == "heute" else res["varianten"][name]
        a, k = v["zeitraum_a"], v["kontrolle_2022_2024"]
        ok = "–" if name == "heute" else ("ja" if v["bestanden"] else "nein")
        zeilen.append(f"| {TITEL[name]} | {a['trades']} | {_z(a['pf_r'])} | {_z(a['summe_r'], 1)} | {_z(v['robust']['pf_r'])} | "
                      f"{_z(v.get('zufall'), 1)} | {_z(v['haelfte_1']['pf_r'])} | {_z(v['haelfte_2']['pf_r'])} | "
                      f"{_z(v['jahr_2026']['pf_r'])} | {_z(k['pf_r'])} | {_z(k['summe_r'], 1)} | {ok} |")
    zeilen += ["", "Bestanden nur mit mindestens 100 Trades, PF_R ab 1,3, robust ab 1,15, Zufall ab 95, beide Hälften, 2026 und "
               "Kontrolle über 1,0.", ""]
    lv = res["varianten"]["longs"]
    zeilen += [f"Longs und Shorts zusammen (nur Info): {lv['zusammen_mit_shorts']['trades']} Trades, PF_R "
               f"{_z(lv['zusammen_mit_shorts']['pf_r'])}, {_z(lv['zusammen_mit_shorts']['summe_r'], 1)} R; Kontrolle PF_R "
               f"{_z(lv['zusammen_kontrolle']['pf_r'])}, {_z(lv['zusammen_kontrolle']['summe_r'], 1)} R.", "",
               "## Nachbarwerte (nur Stabilität)", "", "| Variante | Trades | PF_R | Summe R |", "|---|---:|---:|---:|"]
    for name in NACHBARN:
        x = res["info"][name]
        zeilen.append(f"| {name} | {x['trades']} | {_z(x['pf_r'])} | {_z(x['summe_r'], 1)} |")
    zeilen += ["", "## Kirons Beispiele (Kerzen bis 05.11.2026, Dukascopy)", "", "| Regel | #461 | #472 | #473 | Summe ohne die drei (bei Longs dazu: Shorts und Longs) |",
               "|---|---|---|---|---:|"]
    for name, bsp in res["info"]["beispiele"].items():
        zellen = []
        for nr in BEISPIELE:
            x = bsp.get(nr)
            zellen.append("kein Trade (Seite hatte schon die Höchstzahl offener Trades)" if x is None else f"{_z(x['ergebnis_r'])} R ({', '.join(x['teile'])})")
        zeilen.append(f"| {TITEL[name]} | " + " | ".join(zellen) + f" | {_z(res['info']['ohne_beispiele_summe_r'][name], 1)} |")
    zeilen += ["", "## Gold steigt oder fällt (Schluss über oder unter dem von 20 Handelstagen vorher, nur Info)", "",
               "| Regel | steigt Trades | steigt PF_R | steigt R | fällt Trades | fällt PF_R | fällt R |", "|---|---:|---:|---:|---:|---:|---:|"]
    for name in ["heute"] + list(VARIANTEN):
        v = res["heute"] if name == "heute" else res["varianten"][name]
        s_, f_ = v["gold_steigt"], v["gold_faellt"]
        zeilen.append(f"| {TITEL[name]} | {s_['trades']} | {_z(s_['pf_r'])} | {_z(s_['summe_r'], 1)} | {f_['trades']} | "
                      f"{_z(f_['pf_r'])} | {_z(f_['summe_r'], 1)} |")
    zeilen += ["", "## Je Seite, Rückgang und Ausstiege (Zeitraum A)", ""]
    for name in ["heute"] + list(VARIANTEN):
        v = res["heute"] if name == "heute" else res["varianten"][name]
        seiten = ", ".join(f"{s} {x['trades']} Trades PF {_z(x['pf_r'])} {_z(x['summe_r'], 1)} R" for s, x in v["je_seite"].items())
        gr = ", ".join(f"{g} {x['trades']}/{_z(x['summe_r'], 1)} R" for g, x in v["gruende"].items())
        zeilen.append(f"- **{TITEL[name]}**: {seiten}. Größter Rückgang {_z(v['rueckgang_r'], 1)} R, gesperrt {v['gesperrt']}. "
                      f"Ausstiege: {gr}.")
    return "\n".join(zeilen) + "\n"


def main(argv: list[str]) -> int:
    out = pathlib.Path(argv[0] if argv else "k2_ergebnis")
    out.mkdir(parents=True, exist_ok=True)
    vor = check_vorab()
    za, ko = vor["daten"]["zeitraum_a"], vor["daten"]["kontrolle"]
    rob = float(vor["kosten"]["robust_faktor"])
    ba = basis(za["von"], za["bis"])
    br = robust_basis(ba, rob)
    bk = basis(ko["von"], ko["bis"])
    res = {"vorab_sha256": sha256_text(VORAB.read_text(encoding="utf-8")), "varianten": {}, "info": {}}
    res["heute"] = rechne_variante("heute", HEUTE, ba, br, bk, vor)
    for name, cfg in VARIANTEN.items():
        res["varianten"][name] = rechne_variante(name, cfg, ba, br, bk, vor, longs=(name == "longs"))
    for name, cfg in NACHBARN.items():
        gen, _, _ = kombi(simuliere(ba, cfg))
        res["info"][name] = kurz(ab(gen, za["test_ab"], za["bis"]))
        print("Nachbar", name, res["info"][name], flush=True)
    # Kirons Beispiele und Chart (Kerzen bis 05.11.2026 mit Dukascopy)
    bd = basis(za["von"], "2026-10-30", duka=True)
    chart = {}
    for name, cfg in [("heute", HEUTE)] + list(VARIANTEN.items()):
        rows, gesp = chart_trades(bd, cfg, longs=(name == "longs"))
        chart[name] = {"trades": rows, "gesperrt": gesp}
        bsp = {}
        for nr, zeit in BEISPIELE.items():
            t0 = int(pd.Timestamp(zeit).timestamp())
            x = next((r for r in rows if r["ein"] == t0 and r["d"] < 0), None)
            bsp[nr] = None if x is None else {"ergebnis_r": x["e"], "grund": x["g"], "teile": [t["g"] for t in x["teile"]]}
        res["info"].setdefault("beispiele", {})[name] = bsp
        ohne = [r["e"] for r in rows if r["ein"] <= int(pd.Timestamp(za["bis"] + " 23:59").timestamp())
                and str(pd.Timestamp(r["ein"], unit="s")) not in BEISPIELE.values() and (r["d"] < 0 or name == "longs")]
        res["info"].setdefault("ohne_beispiele_summe_r", {})[name] = round(float(sum(ohne)), 1)
    (out / "k2.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "chart.json").write_text(json.dumps(chart, separators=(",", ":")), encoding="utf-8")
    (out / "BERICHT.md").write_text(bericht(res), encoding="utf-8")
    print(json.dumps(res["info"]["beispiele"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
