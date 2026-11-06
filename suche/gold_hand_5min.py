"""Gold-Hand-Bot: Bringen Einstiege auf 5-Min.-Kerzen mehr gute Einstiege? Nach suche/VORAB_gold_hand_5min.yaml.

    python -m suche.gold_hand_5min <ausgabe-ordner>     # rechnet alles, schreibt ergebnis.json und BERICHT.md

Braucht die HistData-Kerzen und den Capital.com-Spread aus portfolio-manager (wie suche/gold_short_k2.py). Nur
Forschung, kein Teil des laufenden Bots und nicht in CI.

Die 5-Min.-Fassung rechnet dieselben drei Seiten mit derselben Führung, nur dass die kleine Ebene (bei 15 Min. "15m")
aus 5-Min.-Kerzen besteht. Dafür ersetzt ebene_frei während der Rechnung tiktok_schatten.ebene: jede Gruppe endet
eine Kerzenlänge nach ihrer letzten Kerze (bei 5 Min. also 5 Min. statt 15 Min.).
"""
from __future__ import annotations

import contextlib
import json
import pathlib
import sys

import numpy as np
import pandas as pd

from gold import tiktok_schatten as ts
from suche import gold_short_k2 as k2
from suche.runde1 import journal_lines, last_value, sha256_text

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_gold_hand_5min.yaml"
KEY = "VORAB_gold_hand_5min sha256 "
ZEITRAUM = ("2024-11-01", "2026-10-30")
KONTROLLE = ("2022-11-01", "2024-10-31")
VORLAUF = pd.Timedelta(days=60)
MIN_TRADES = 50
SUCHE_KERZEN = 3000                       # so weit sucht erst_1r am Stück (gut 10 Handelstage auf 5 Min.)


def check_vorab() -> dict:
    ist = sha256_text(VORAB.read_text(encoding="utf-8"))
    soll = last_value(journal_lines(), KEY)
    return {"ok": ist == soll, "sha256": ist}


# --------------------------------------------------------------------------------------------------------------------
# Kerzen und Ebenen

def basis(von: str, bis: str, minuten: int) -> ts.Basis:
    """HistData-Kerzen zu `minuten` zusammengefasst, Spread je 15-Min.-Fenster New York wie Komitee 2."""
    if "hd" not in k2._HD:
        k2.kerzen15(von, von)
    df = k2._HD["hd"].loc[von:bis + " 23:59"]
    b = df.groupby(df.index.floor(f"{minuten}min")).agg({"open": "first", "high": "max", "low": "min",
                                                         "close": "last"})
    nyz = b.index.tz_localize("UTC").tz_convert("America/New_York")
    slot = np.asarray(nyz.hour * 60 + (nyz.minute // 15) * 15)
    b["spread"] = k2._HD["anteil"].reindex(slot).to_numpy(float) * b["open"].to_numpy(float)
    return ts.basis(b[["open", "high", "low", "close"]], b["spread"])


_ORIG_EBENE = ts.ebene
_BAR = {"min": 15}


def ebene_frei(b: ts.Basis, name: str) -> ts.Ebene:
    """Wie tiktok_schatten.ebene, aber die kleine Ebene ("15m") und das Gruppenende für die Kerzenlänge _BAR."""
    m = _BAR["min"]
    if m == 15:
        return _ORIG_EBENE(b, name)
    t = pd.DatetimeIndex(b.t)
    if name == "15m":
        g = t.floor(f"{m}min")
    elif name == "1h":
        g = t.floor("1h")
    elif name == "4h":
        g = (b.ny + pd.Timedelta(hours=6)).floor("4h")
    else:
        raise ValueError(name)
    g = np.asarray(g.values)
    neu = np.r_[True, g[1:] != g[:-1]]
    i0 = np.flatnonzero(neu)
    i1 = np.r_[i0[1:] - 1, len(g) - 1]
    h = np.maximum.reduceat(b.h, i0)
    lo = np.minimum.reduceat(b.l, i0)
    c = b.c[i1]
    e = ts.Ebene(name, b.t[i1] + np.timedelta64(m, "m"), h, lo, c, i1)
    e.atr = ts.atr_wilder(h, lo, c, 14)
    e.o = b.o[i0]
    return e


@contextlib.contextmanager
def kerzenlaenge(minuten: int):
    alt = ts.ebene
    _BAR["min"] = minuten
    ts.ebene = ebene_frei
    try:
        yield
    finally:
        ts.ebene = alt
        _BAR["min"] = 15


# --------------------------------------------------------------------------------------------------------------------
# Einstiege und Maße

def einstiege(b: ts.Basis, minuten: int) -> list[tuple[str, dict]]:
    """Alle Einstiege des Hand-Bots: Shorts wie short_bot.kombi, Longs nur ohne offenen Short."""
    with kerzenlaenge(minuten):
        trades = k2.simuliere(b, k2.HEUTE)
    gen, _, gl = k2.kombi(trades, longs=True)
    return sorted(gen + gl, key=lambda x: x[1]["einstieg_zeit"])


def erst_1r(b5: ts.Basis, t: dict) -> int | None:
    """1, wenn der Kurs zuerst 1 R in Trade-Richtung läuft, 0, wenn zuerst 1 R dagegen (beides in einer Kerze: 0),
    None, wenn bis zum Datenende keins von beiden."""
    d, e, r = int(t["richtung"]), float(t["einstieg"]), float(t["r_usd"])
    j = int(np.searchsorted(b5.t, np.datetime64(pd.Timestamp(t["einstieg_zeit"]))))
    lo, hi = (b5.l, b5.h) if d > 0 else (b5.l + b5.sp, b5.h + b5.sp)
    while j < len(b5):
        k = min(len(b5), j + SUCHE_KERZEN)
        if d > 0:
            gegen, dafuer = lo[j:k] <= e - r, hi[j:k] >= e + r
        else:
            gegen, dafuer = hi[j:k] >= e + r, lo[j:k] <= e - r
        ig = int(np.argmax(gegen)) if gegen.any() else None
        idf = int(np.argmax(dafuer)) if dafuer.any() else None
        if ig is not None and (idf is None or ig <= idf):
            return 0
        if idf is not None:
            return 1
        j = k
    return None


def masse(gen: list[tuple[str, dict]], b5: ts.Basis) -> dict:
    out = k2.kurz(gen)
    e1 = [erst_1r(b5, t) for _, t in gen]
    e1 = [x for x in e1 if x is not None]
    out["erst_1r"] = round(float(np.mean(e1)), 3) if e1 else None
    out["shorts"] = sum(1 for _, t in gen if t["richtung"] < 0)
    out["longs"] = sum(1 for _, t in gen if t["richtung"] > 0)
    for name, d in (("nur_shorts", -1), ("nur_longs", 1)):
        teil = [(s, t) for s, t in gen if t["richtung"] == d]
        k = k2.kurz(teil)
        k["erst_1r"] = (round(float(np.mean([x for x in (erst_1r(b5, t) for _, t in teil) if x is not None])), 3)
                        if teil else None)
        out[name] = k
    return out


def fenster(t: dict) -> tuple[str, int]:
    return str(pd.Timestamp(t["einstieg_zeit"]).floor("15min")), int(t["richtung"])


def zeitraum(von: str, bis: str) -> dict:
    start = str((pd.Timestamp(von) - VORLAUF).date())
    b15, b5 = basis(start, bis, 15), basis(start, bis, 5)
    e15 = k2.ab(einstiege(b15, 15), von, bis)
    e5 = k2.ab(einstiege(b5, 5), von, bis)
    alt = {fenster(t) for _, t in e15}
    extra = [(s, t) for s, t in e5 if fenster(t) not in alt]
    return {"von": von, "bis": bis, "e15": masse(e15, b5), "e5": masse(e5, b5), "zusaetzlich": masse(extra, b5),
            "gleich": len(e5) - len(extra)}


def urteil(z: dict, k: dict) -> dict:
    def mind(a, b):
        return a is not None and b is not None and a >= b
    pruef = {
        "trades_ab_50": z["zusaetzlich"]["trades"] >= MIN_TRADES,
        "pf_zeitraum": mind(z["zusaetzlich"]["pf_r"], z["e15"]["pf_r"]),
        "erst_1r_zeitraum": mind(z["zusaetzlich"]["erst_1r"], z["e15"]["erst_1r"]),
        "pf_kontrolle": mind(k["zusaetzlich"]["pf_r"], k["e15"]["pf_r"]),
        "erst_1r_kontrolle": mind(k["zusaetzlich"]["erst_1r"], k["e15"]["erst_1r"]),
    }
    return {"pruefungen": pruef, "dazu": all(pruef.values())}


# --------------------------------------------------------------------------------------------------------------------
# Bericht

def _z(x, n=2):
    return "–" if x is None else f"{x:.{n}f}".replace(".", ",")


def bericht(res: dict) -> str:
    z, k, u = res["zeitraum"], res["kontrolle"], res["urteil"]
    zeilen = ["# Gold-Hand-Bot: Einstiege auf 5-Min.-Kerzen", "",
              f"Vorab: `suche/VORAB_gold_hand_5min.yaml` (sha256 `{res['vorab']['sha256'][:8]}…`, im Protokoll vor "
              "dem Rechnen). Daten: HistData XAUUSD 5 Min. mit Capital.com-Spread.", "",
              "**Ergebnis: " + ("Die 5-Min.-Einstiege kommen dazu (Vorschlag an Kiron)." if u["dazu"]
                               else "Die 5-Min.-Einstiege kommen nicht dazu. Der Bot bleibt bei 15 Min.") + "**", ""]
    for titel, x in (("Zeitraum 01.11.2024 bis 30.10.2026", z), ("Kontrolle 01.11.2022 bis 31.10.2024", k)):
        zeilen += [f"## {titel}", "",
                   "| Einstiege | Trades | Shorts | Longs | PF_R | Summe R | Treffer | zuerst 1 R dafür |",
                   "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for name, key in (("15 Min. (heute)", "e15"), ("5 Min. (alle)", "e5"), ("5 Min. zusätzlich", "zusaetzlich")):
            m = x[key]
            zeilen.append(f"| {name} | {m['trades']} | {m['shorts']} | {m['longs']} | {_z(m['pf_r'])} | "
                          f"{_z(m['summe_r'], 1)} | {_z(m['trefferquote'])} | {_z(m['erst_1r'])} |")
        zeilen += ["", f"{x['gleich']} der 5-Min.-Einstiege liegen im selben 15-Min.-Fenster und in derselben Richtung "
                   "wie ein 15-Min.-Einstieg.", ""]
        zeilen += ["Getrennt nach Richtung (PF_R / zuerst 1 R dafür):", ""]
        for name, key in (("15 Min.", "e15"), ("5 Min. zusätzlich", "zusaetzlich")):
            s, lg = x[key]["nur_shorts"], x[key]["nur_longs"]
            zeilen.append(f"- {name}: Shorts {s['trades']} Trades, {_z(s['pf_r'])} / {_z(s['erst_1r'])}; "
                          f"Longs {lg['trades']} Trades, {_z(lg['pf_r'])} / {_z(lg['erst_1r'])}")
        zeilen.append("")
    zeilen += ["## Prüfungen nach dem Vorab", ""]
    namen = {"trades_ab_50": "mindestens 50 zusätzliche Trades",
             "pf_zeitraum": "PF_R zusätzlich mindestens wie 15 Min. (Zeitraum)",
             "erst_1r_zeitraum": "zuerst 1 R dafür mindestens wie 15 Min. (Zeitraum)",
             "pf_kontrolle": "PF_R zusätzlich mindestens wie 15 Min. (Kontrolle)",
             "erst_1r_kontrolle": "zuerst 1 R dafür mindestens wie 15 Min. (Kontrolle)"}
    for key, ok in u["pruefungen"].items():
        zeilen.append(f"- {'ja' if ok else 'nein'}: {namen[key]}")
    return "\n".join(zeilen) + "\n"


def main(argv: list[str]) -> int:
    aus = pathlib.Path(argv[0] if argv else "gold_hand_5min_out")
    aus.mkdir(parents=True, exist_ok=True)
    vor = check_vorab()
    if not vor["ok"]:
        print("VORAB_gold_hand_5min.yaml passt nicht zur Prüfsumme im Protokoll")
        return 1
    res = {"vorab": vor, "zeitraum": zeitraum(*ZEITRAUM), "kontrolle": zeitraum(*KONTROLLE)}
    res["urteil"] = urteil(res["zeitraum"], res["kontrolle"])
    (aus / "ergebnis.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n",
                                       encoding="utf-8")
    (aus / "BERICHT.md").write_text(bericht(res), encoding="utf-8")
    print(bericht(res))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
