"""Gold-Hand-Bot: eine Auswahl der 5-Min.-Einstiege nach suche/VORAB_gold_hand_5min_auswahl.yaml.

    python -m suche.gold_hand_5min_auswahl <ausgabe-ordner>     # schreibt ergebnis.json und BERICHT.md

Einstiege, Kerzen und Maße kommen aus suche/gold_hand_5min.py, der Hintergrund aus gold/v2/richtung.direction auf
Stundenkerzen derselben HistData-Kurse. Nur Forschung, kein Teil des laufenden Bots und nicht in CI.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd

from gold.v2.richtung import direction
from suche import gold_hand_5min as g5
from suche import gold_short_k2 as k2
from suche.runde1 import journal_lines, last_value, sha256_text

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_gold_hand_5min_auswahl.yaml"
KEY = "VORAB_gold_hand_5min_auswahl sha256 "
REIHENFOLGE = ("v1_wie_live", "v2_mit_trend", "v3_zwei_am_tag", "v4_nur_5min")
NAMEN = {"v1_wie_live": "5 Min. zusätzlich, wie live (nicht gegen den Hintergrund)",
         "v2_mit_trend": "5 Min. zusätzlich, nur mit dem Trend",
         "v3_zwei_am_tag": "5 Min. zusätzlich, mit dem Trend, höchstens 2 am Tag",
         "v4_nur_5min": "nur 5 Min. statt 15 Min., wie live"}


def check_vorab() -> dict:
    ist = sha256_text(VORAB.read_text(encoding="utf-8"))
    return {"ok": ist == last_value(journal_lines(), KEY), "sha256": ist}


def hintergrund_reihe(von: str, bis: str) -> tuple[np.ndarray, np.ndarray]:
    """(Zeitpunkt, ab dem der Wert gilt, Wert) je Stundenkerze."""
    if "hd" not in k2._HD:
        k2.kerzen15(von, von)
    df = k2._HD["hd"].loc[von:bis + " 23:59"]
    h = df.resample("60min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    r = direction(h)
    ab = (h.index + pd.Timedelta("60min")).values
    return ab, r.to_numpy(int)


def hg_bei(reihe, t: str) -> int:
    ab, wert = reihe
    i = int(np.searchsorted(ab, np.datetime64(pd.Timestamp(t)), side="right")) - 1
    return int(wert[i]) if i >= 0 else 0


def handelstag(t: str) -> str:
    ny = pd.Timestamp(t).tz_localize("UTC").tz_convert("America/New_York").tz_localize(None)
    return str((ny + pd.Timedelta(hours=7)).normalize().date())


def zeitraum(von: str, bis: str) -> dict:
    start = str((pd.Timestamp(von) - g5.VORLAUF).date())
    reihe = hintergrund_reihe(str((pd.Timestamp(von) - pd.Timedelta(days=200)).date()), bis)
    b15, b5 = g5.basis(start, bis, 15), g5.basis(start, bis, 5)
    e15 = k2.ab(g5.einstiege(b15, 15), von, bis)
    e5 = k2.ab(g5.einstiege(b5, 5), von, bis)
    hg = {id(t): hg_bei(reihe, t["einstieg_zeit"]) for _, t in e15 + e5}
    live = lambda gen: [(s, t) for s, t in gen if hg[id(t)] != -int(t["richtung"])]
    trend = lambda gen: [(s, t) for s, t in gen if hg[id(t)] == int(t["richtung"])]
    vergleich = live(e15)
    alt = {g5.fenster(t) for _, t in e15}
    extra = [(s, t) for s, t in e5 if g5.fenster(t) not in alt]
    v2 = trend(extra)
    v3, je_tag = [], {}
    for s, t in v2:
        tag = handelstag(t["einstieg_zeit"])
        if je_tag.get(tag, 0) < 2:
            v3.append((s, t))
            je_tag[tag] = je_tag.get(tag, 0) + 1
    sets = {"v1_wie_live": live(extra), "v2_mit_trend": v2, "v3_zwei_am_tag": v3, "v4_nur_5min": live(e5)}
    return {"von": von, "bis": bis, "vergleich": g5.masse(vergleich, b5),
            "auswahlen": {k: g5.masse(v, b5) for k, v in sets.items()},
            "hintergrund_anteil": {str(k): int(sum(1 for _, t in e15 if hg[id(t)] == k)) for k in (-1, 0, 1)}}


def urteil(z: dict, k: dict) -> dict:
    def mind(a, b):
        return a is not None and b is not None and a >= b
    out = {}
    for name in REIHENFOLGE:
        a, ak = z["auswahlen"][name], k["auswahlen"][name]
        p = {"trades_ab_50": a["trades"] >= g5.MIN_TRADES,
             "pf_zeitraum": mind(a["pf_r"], z["vergleich"]["pf_r"]),
             "erst_1r_zeitraum": mind(a["erst_1r"], z["vergleich"]["erst_1r"]),
             "pf_kontrolle": mind(ak["pf_r"], k["vergleich"]["pf_r"]),
             "erst_1r_kontrolle": mind(ak["erst_1r"], k["vergleich"]["erst_1r"])}
        out[name] = {"pruefungen": p, "bestanden": all(p.values())}
    gewaehlt = next((n for n in REIHENFOLGE if out[n]["bestanden"]), None)
    return {"je_auswahl": out, "gewaehlt": gewaehlt}


def bericht(res: dict) -> str:
    z, k, u = res["zeitraum"], res["kontrolle"], res["urteil"]
    _z = g5._z
    zeilen = ["# Gold-Hand-Bot: Auswahl der 5-Min.-Einstiege", "",
              f"Vorab: `suche/VORAB_gold_hand_5min_auswahl.yaml` (sha256 `{res['vorab']['sha256'][:8]}…`, im Protokoll "
              "vor dem Rechnen). Daten: HistData XAUUSD 5 Min. mit Capital.com-Spread.", "",
              "**Ergebnis: " + (f"{NAMEN[u['gewaehlt']]} besteht (Vorschlag an Kiron)." if u["gewaehlt"]
                               else "Keine Auswahl besteht. Der Bot bleibt bei 15-Min.-Einstiegen.") + "**", ""]
    for titel, x in (("Zeitraum 01.11.2024 bis 30.10.2026", z), ("Kontrolle 01.11.2022 bis 31.10.2024", k)):
        zeilen += [f"## {titel}", "", "| Einstiege | Trades | PF_R | Summe R | zuerst 1 R dafür |",
                   "|---|---:|---:|---:|---:|"]
        rows = [("15 Min. wie live (Vergleich)", x["vergleich"])] + [(NAMEN[n], x["auswahlen"][n]) for n in REIHENFOLGE]
        for name, m in rows:
            zeilen.append(f"| {name} | {m['trades']} | {_z(m['pf_r'])} | {_z(m['summe_r'], 1)} | {_z(m['erst_1r'])} |")
        zeilen.append("")
    zeilen += ["## Prüfungen nach dem Vorab", ""]
    for n in REIHENFOLGE:
        p = u["je_auswahl"][n]["pruefungen"]
        nein = [key for key, ok in p.items() if not ok]
        zeilen.append(f"- {NAMEN[n]}: " + ("bestanden" if not nein else "nicht bestanden (" + ", ".join(nein) + ")"))
    return "\n".join(zeilen) + "\n"


def main(argv: list[str]) -> int:
    aus = pathlib.Path(argv[0] if argv else "gold_hand_5min_auswahl_out")
    aus.mkdir(parents=True, exist_ok=True)
    vor = check_vorab()
    if not vor["ok"]:
        print("VORAB_gold_hand_5min_auswahl.yaml passt nicht zur Prüfsumme im Protokoll")
        return 1
    res = {"vorab": vor, "zeitraum": zeitraum(*g5.ZEITRAUM), "kontrolle": zeitraum(*g5.KONTROLLE)}
    res["urteil"] = urteil(res["zeitraum"], res["kontrolle"])
    (aus / "ergebnis.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n",
                                       encoding="utf-8")
    (aus / "BERICHT.md").write_text(bericht(res), encoding="utf-8")
    print(bericht(res))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
