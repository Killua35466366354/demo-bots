"""Runde "Kirons Notizen" vom 19.11.2026: elf vorab festgelegte Fassungen schon gerechneter Regeln.

Kiron hat am 19.11.2026 im Strategie-Katalog jede Strategie bewertet und zu vielen eine Notiz geschrieben (länger
halten, früheres Ziel, Gewinn sichern, umdrehen, auch verkaufen). Diese Runde rechnet seine Notizen zu den Karten
Nr. 25 bis 39, die aus den Runden "Starker Rückblick" und den beiden YouTube-Runden stammen.

Regeln: suche/VORAB_notizen_runde.yaml (versiegelt im Protokoll, bevor mit Kursen ab 2024 gerechnet wurde).
Die Grundregeln kommen unverändert aus den versiegelten Dateien VORAB_rueckblick, VORAB_youtube_runde und
VORAB_youtube_runde2 (ihr Siegel wird beim Laden geprüft). Die Rechnung (Kosten, ein Trade, Zwillinge, Hürden, Holm)
ist die von suche/rueckblick.py. Neu sind nur die Änderungen je Fassung und der Stufen-Stop.

Aufruf:
    python -m suche.notizen_runde --festlegen                  schreibt die Prüfsumme der Regeldatei ins Protokoll
    python -m suche.notizen_runde entwicklung <Arbeit>         nur Kurse bis Ende 2023, prüft das Programm, kein Ergebnis
    python -m suche.notizen_runde probelauf <Arbeit> <Saat>    ganze Rechnung auf erfundenen Märkten ohne Vorteil
    python -m suche.notizen_runde rechnen <Arbeit>             die Rechnung (nur mit passender Prüfsumme)
Die Kursdateien (npz) baut python -m suche.youtube_runde2 daten <Arbeit>.
"""
from __future__ import annotations

import contextlib
import math
import pathlib
import sys

import numpy as np
import pandas as pd
import yaml

from suche import rueckblick as rb
from suche import youtube_runde as yr
from suche import youtube_runde2 as y2
from suche.runde1 import journal_add, journal_lines, last_value, sha256_text

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_notizen_runde.yaml"
KEY = "VORAB_notizen_runde sha256 "
ERGEBNIS = ROOT / "suche" / "ergebnis_notizen_runde"
MIN = rb.MIN
QUELLEN = {"rueckblick": rb, "youtube_runde": yr, "youtube_runde2": y2}

Markt = yr.Markt                                       # Krypto mit sieben Handelstagen, sonst wie rueckblick.Markt
_ORIG = {"trade": rb._trade, "viele": rb._viele}
_GRUND = {q: mod.signale for q, mod in QUELLEN.items()}   # die Regeln der Quellen, bevor rb.signale ersetzt wird
_STUFE = 0.0                                           # Schritt des Stufen-Stops in R der laufenden Fassung, 0 = keiner
_LAUF: dict = {}                                       # Arbeit, bis, Saat der laufenden Rechnung (für _kreuz)


def lade_vorab(pruefen: bool = True) -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if pruefen and last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("VORAB_notizen_runde.yaml passt nicht zur Prüfsumme im Protokoll. Erst versiegeln, dann rechnen.")
    cfg = yaml.safe_load(text)["notizen_runde"]
    # Die Grundregeln immer aus den versiegelten Dateien, nie abgetippt.
    cfg["quell_regeln"] = {q: QUELLEN[q].lade_vorab(pruefen=True)["regeln"] for q in QUELLEN}
    return cfg


# ---------------------------------------------------------------------------------------------------------------------
# Stufen-Stop: wie rueckblick._trade, nur rückt der Stop nach jeder fertigen 5-Minuten-Kerze in Stufen nach

@rb.njit(cache=True)
def _trade_stufen(o, h, l, c, sp, i0, d, lvl, sd, zd, imax, kf, rutsch, schritt):
    """Wie rueckblick._trade. Dazu: Hat der Trade nach einer fertigen Kerze mindestens k Stufen (k mal schritt R)
    Gewinn gesehen, liegt der Stop ab der nächsten Kerze bei (k minus 1) Stufen Gewinn. Ab 1 Stufe also auf Einstand,
    ab 2 Stufen auf 1 Stufe Gewinn. Der Stop rückt nie zurück. Long misst am Bid, Short am Ask."""
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
        stop = ref - sd
        ziel = ref + zd if zd > 0 else 1e300
        best = 0.0
        if lvl == lvl:
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
            # Das Hoch der Einstiegskerze liegt nach dem Auslösen (der Kurs kam von unten durch die Marke).
            best = max(best, (h[i0] - ref) / sd)
            if best >= schritt:
                stop = max(stop, ref + (math.floor(best / schritt) - 1.0) * schritt * sd)
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
            best = max(best, (h[j] - ref) / sd)
            if best >= schritt:
                stop = max(stop, ref + (math.floor(best / schritt) - 1.0) * schritt * sd)
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
        stop = ref + sd
        ziel = ref - zd if zd > 0 else -1e300
        best = 0.0
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
            best = max(best, (ref - (l[i0] + s0)) / sd)
            if best >= schritt:
                stop = min(stop, ref - (math.floor(best / schritt) - 1.0) * schritt * sd)
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
            best = max(best, (ref - (l[j] + sj)) / sd)
            if best >= schritt:
                stop = min(stop, ref - (math.floor(best / schritt) - 1.0) * schritt * sd)
            j += 1


@rb.njit(cache=True)
def _viele_stufen(o, h, l, c, sp, i0, d, sd, zd, imax, kf, rutsch, schritt):
    m = i0.shape[0]
    ex, pnl, ein = np.empty(m, np.int64), np.empty(m), np.empty(m)
    for q in range(m):
        ex[q], pnl[q], ein[q] = _trade_stufen(o, h, l, c, sp, i0[q], d[q], np.nan, sd[q], zd[q], imax[q], kf[q],
                                              rutsch, schritt)
    return ex, pnl, ein


def _trade_wahl(o, h, l, c, sp, i0, d, lvl, sd, zd, imax, kf, rutsch):
    if _STUFE > 0:
        return _trade_stufen(o, h, l, c, sp, i0, d, lvl, sd, zd, imax, kf, rutsch, _STUFE)
    return _ORIG["trade"](o, h, l, c, sp, i0, d, lvl, sd, zd, imax, kf, rutsch)


def _viele_wahl(o, h, l, c, sp, i0, d, sd, zd, imax, kf, rutsch):
    if _STUFE > 0:
        return _viele_stufen(o, h, l, c, sp, i0, d, sd, zd, imax, kf, rutsch, _STUFE)
    return _ORIG["viele"](o, h, l, c, sp, i0, d, sd, zd, imax, kf, rutsch)


# ---------------------------------------------------------------------------------------------------------------------
# Neue Bauteile

def regel_dienstag_beide(m: Markt, cfg: dict) -> list[dict]:
    """rueckblick.regel_dienstag, dazu die Gegenseite: Schließt der Montag über dem Freitag, Verkauf."""
    p = cfg["regeln"]["dienstag"]
    zone, schluss = rb.SCHLUSS[m.sym]
    lok = pd.DatetimeIndex(m.t).tz_localize("UTC").tz_convert(zone)
    lmin = np.asarray(lok.hour * 60 + lok.minute)
    ltag = lok.tz_localize(None).normalize().values.astype("datetime64[D]")
    kand = np.flatnonzero((lmin >= schluss) & (lmin < schluss + p["toleranz_min"]))
    erst = kand[np.r_[True, ltag[kand][1:] != ltag[kand][:-1]]]
    tage = ltag[erst]
    wt = np.asarray(pd.DatetimeIndex(tage).weekday)
    kurs = m.o[erst]
    davor = m.c[np.maximum(erst - 1, 0)]
    sig = []
    for q in range(1, len(erst) - 1):
        if wt[q] != 0 or wt[q - 1] != 4 or (tage[q] - tage[q - 1]).astype(int) != 3:
            continue
        if wt[q + 1] != 1 or (tage[q + 1] - tage[q]).astype(int) != 1:
            continue
        if davor[q] < kurs[q - 1]:
            d = 1
        elif davor[q] > kurs[q - 1]:
            d = -1
        else:
            continue
        i0 = int(erst[q])
        g = m.gpos[m.tix[i0]]
        if g < 1 or not np.isfinite(m.atr_vor[g]):
            continue
        sig.append({"i0": i0, "d": d, "sd": float(p["stop_atr"] * m.atr_vor[g]), "zd": 0.0, "t_max": m.t[erst[q + 1]]})
    return sig


def regel_kreuz(m: Markt, cfg: dict, spec: dict) -> list[dict]:
    """Supertrend des S&P 500 (Regel supertrend der zweiten YouTube-Runde), gehandelt wird m in die Gegenrichtung."""
    k = spec["kreuz"]
    ref = Markt(k["signal_markt"], _LAUF["arbeit"], cfg, _LAUF["bis"], _LAUF["saat"])
    quelle = y2.regel_supertrend(ref, cfg)
    k4 = y2._kerzen_4h(m)
    atr = rb._wilder(k4["tr"], k["atr_n"])
    sig = []
    for s in quelle:
        t_sig = ref.t[s["i0"]]
        i0 = int(np.searchsorted(m.t, t_sig))
        if i0 >= m.n - 1 or (m.t[i0] - t_sig) > k["frist_min"] * MIN or y2._pause(m, i0, cfg):
            continue
        j = int(np.searchsorted(k4["b"], i0)) - 1          # letzte fertige 4-Std.-Kerze von m vor dem Einstieg
        if j < 0 or not np.isfinite(atr[j]) or m.t[i0] >= s["t_max"]:
            continue
        sd = float(k["stop_atr"] * atr[j])
        sig.append({"i0": i0, "d": -int(s["d"]) if k["gegenrichtung"] else int(s["d"]), "sd": sd,
                    "zd": float(k["ziel_r"] * sd), "t_max": s["t_max"]})
    return sig


def aendere(sig: list[dict], spec: dict) -> list[dict]:
    """Die Änderungen einer Fassung an fertigen Signalen. Richtung, Stop- und Ziel-Abstand, sonst nichts."""
    out = []
    for s in sig:
        s = dict(s)
        u = spec.get("umkehr")
        if u == "spiegel":                                  # alter Stop wird Ziel, altes Ziel wird Stop
            if "lvl" in s or not s["zd"] > 0:
                raise SystemExit("spiegel braucht eine Marktorder mit Ziel")
            s["d"], s["sd"], s["zd"] = -s["d"], s["zd"], s["sd"]
        elif u == "weit":                                   # Gegenrichtung, Stop nach Schwankung weiter, Ziel in R
            if "lvl" in s:
                raise SystemExit("weit braucht eine Marktorder")
            s["d"] = -s["d"]
            s["sd"] = s["sd"] * spec["stop_faktor"]
            s["zd"] = spec["ziel_r_umkehr"] * s["sd"]
        elif u is not None:
            raise SystemExit(f"unbekannte Umkehr {u}")
        if "ziel_r_neu" in spec:
            s["zd"] = float(spec["ziel_r_neu"]) * s["sd"]
        if "ziel_faktor" in spec:
            s["zd"] = float(spec["ziel_faktor"]) * s["zd"]
        out.append(s)
    return out


def regel_cfg(cfg: dict, spec: dict) -> dict:
    """Die Grundregel aus ihrer versiegelten Datei, nur mit den Zahlen aus "aendern" überschrieben."""
    basis = spec["basis"]
    regeln = {k: dict(v) for k, v in cfg["quell_regeln"][spec["quelle"]].items()}
    regeln[basis].update(spec.get("aendern", {}))
    return {**cfg, "regeln": regeln}


def signale(regel: str, m: Markt, cfg: dict, termine: np.ndarray) -> list[dict]:
    """rueckblick.rechne ruft das je Fassung und Markt auf, bevor es deren Trades und Zwillinge rechnet. Darum gilt
    der Stufen-Stop, der hier gesetzt wird, genau für diese Fassung (jede Fassung hat ihren eigenen Regelnamen)."""
    global _STUFE
    spec = cfg["varianten"][regel]
    _STUFE = float(spec.get("stufe_r", 0.0))
    q = regel_cfg(cfg, spec)
    basis = spec["basis"]
    if spec.get("kreuz"):
        roh = regel_kreuz(m, q, spec)
    elif spec.get("beide_seiten"):
        if basis != "dienstag":
            raise SystemExit("beide_seiten gibt es nur für dienstag")
        roh = regel_dienstag_beide(m, q)
    else:
        roh = _GRUND[spec["quelle"]](basis, m, q, termine)
    return aendere(roh, spec)


@contextlib.contextmanager
def _diese_runde():
    global _STUFE
    alt = rb.Markt, rb.signale, rb._trade, rb._viele
    rb.Markt, rb.signale, rb._trade, rb._viele = Markt, signale, _trade_wahl, _viele_wahl
    try:
        yield
    finally:
        rb.Markt, rb.signale, rb._trade, rb._viele = alt
        _STUFE = 0.0


def rechne(arbeit: pathlib.Path, cfg: dict, bis, fenster, mitte, saat=None, mit_zwillingen=True):
    for name, v in cfg["varianten"].items():
        if v["regel"] != name:
            raise SystemExit(f"{name}: der Regelname muss der Name der Fassung sein")
    _LAUF.update(arbeit=arbeit, bis=bis, saat=saat)
    with _diese_runde():
        return rb.rechne(arbeit, cfg, bis, fenster, mitte, saat=saat, mit_zwillingen=mit_zwillingen)


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--festlegen":
        zeile = KEY + sha256_text(VORAB.read_text(encoding="utf-8"))
        journal_add(zeile)
        print(zeile)
        return 0
    modus, arbeit = argv[0], pathlib.Path(argv[1])
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
        rb.schreibe(erg, tr, cfg, arbeit / "ergebnis_notizen_runde", kopf)
    else:
        raise SystemExit(__doc__)
    for n, e in erg.items():
        z = e.get("zufall", {})
        print(f"{n:30s} {e.get('trades', 0):5d} T  GF {e.get('gewinnfaktor')}  rob {e.get('gewinnfaktor_robust')}  "
              f"Summe {e.get('summe_R')}  H {e.get('haelfte_1', {}).get('gewinnfaktor')}/{e.get('haelfte_2', {}).get('gewinnfaktor')}  "
              f"2026 {e.get('jahr_2026', {}).get('gewinnfaktor')}  Zufall {z.get('geschlagen_pct')} %  z {z.get('z')}  "
              f"-> {e.get('urteil')} {e.get('durchgefallen_bei', '')}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
