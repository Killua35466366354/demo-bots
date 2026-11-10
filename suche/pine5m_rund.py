"""Pine-Gold-Hand-Bot auf Account 5 rund um die Uhr (suche/VORAB_pine5m_rund.yaml).

Wie k5_hedge_termin_hg aus suche/pine5m_konto5.py, nur ohne Zeitfenster 7 bis 20 Uhr UTC.
Aufruf: python -m suche.pine5m_rund
"""
from __future__ import annotations

import json
import sys

import pandas as pd
import yaml

from suche import pine5m as p5
from suche import pine5m_konto5 as k5
from suche.runde1 import journal_lines, last_value, sha256_text

ROOT = p5.ROOT
VORAB = ROOT / "suche" / "VORAB_pine5m_rund.yaml"
KEY = "VORAB_pine5m_rund sha256 "
LIVE = "k5_hedge_termin_hg"
VARIANTEN = {"k5_7_20": (7, 20), "k5_rund": (0, 24)}


def check_vorab() -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("VORAB_pine5m_rund.yaml passt nicht zur Prüfsumme im Journal.")
    return yaml.safe_load(text)["pine5m_rund"]


def nacht(trades: list[dict], m: p5.Markt) -> list[dict]:
    """Trades, deren Signalkerze (i0 - 1) außerhalb von 7 bis 20 Uhr UTC liegt."""
    out = []
    for t in trades:
        s = m.t[t["i0"] - 1]
        if not 7 <= s.hour + s.minute / 60 < 20:
            out.append(t)
    return out


def rechne(ordner=p5.DATEN) -> dict:
    basis = next(s for s in p5.maerkte() if s["symbol"] == k5.SYMBOL)
    df = p5.lade(k5.SYMBOL, ordner)
    out = {}
    for var, stunden in VARIANTEN.items():
        m = k5.Markt({**basis, "stunden": list(stunden)}, df)
        tr = m.simuliere(*p5.ZEITRAUM, LIVE)
        tr_k = m.simuliere(*p5.KONTROLLE, LIVE)
        out[var] = {
            "zeitraum": p5.kennzahlen(m, tr, *p5.ZEITRAUM),
            "robust": p5.kennzahlen(m, m.simuliere(*p5.ZEITRAUM, LIVE, p5.ROBUST), *p5.ZEITRAUM),
            "haelfte_1": p5.kennzahlen(m, p5.teil(tr, m, *p5.HAELFTEN[0]), *p5.HAELFTEN[0]),
            "haelfte_2": p5.kennzahlen(m, p5.teil(tr, m, *p5.HAELFTEN[1]), *p5.HAELFTEN[1]),
            "jahr_2026": p5.kennzahlen(m, p5.teil(tr, m, *p5.JAHR_2026), *p5.JAHR_2026),
            "kontrolle": p5.kennzahlen(m, tr_k, *p5.KONTROLLE),
            "groesster_verlust_r": k5.extra(tr)["groesster_verlust_r"],
            "gegen_offene_seite": k5.beide_seiten(tr),
            "nacht": p5.kennzahlen(m, nacht(tr, m), *p5.ZEITRAUM),
            "nacht_kontrolle": p5.kennzahlen(m, nacht(tr_k, m), *p5.KONTROLLE)}
        z = out[var]["zeitraum"]
        print(var, z["trades"], z["pf_r"], z["summe_r"], out[var]["kontrolle"]["pf_r"], flush=True)
    return out


def wahl(res: dict) -> dict:
    ok, fehl = p5.bestanden(res["k5_rund"])
    return {"live_variante": "k5_rund", "bestanden": ok, "verfehlt": fehl,
            "alle": {k: p5.bestanden(v) for k, v in res.items()}}


def bericht(res: dict, u: dict) -> str:
    z = ["# Pine-Gold-Hand-Bot auf Account 5 rund um die Uhr (Gold 5 Min.)", "",
         "Regeln suche/VORAB_pine5m_rund.yaml. Beide Varianten mit Hedging, Termin-Pause, Hintergrund und Abfänger "
         "(k5_hedge_termin_hg aus VORAB_pine5m_konto5).", "",
         "**Live: k5_rund** (Kirons Wunsch, geht unabhängig vom Test live), "
         + ("bestanden." if u["bestanden"] else "nicht bestanden: " + "; ".join(u["verfehlt"]) + "."), "",
         "| Variante | Trades | je Woche | PF | Summe R | Rückgang R | Long R | Short R | größter Verlust R | "
         "PF ×1,5 | H1 | H2 | 2026 | Kontrolle | Summe R Kontrolle |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, a in res.items():
        zz = a["zeitraum"]
        z.append(f"| {k} | {zz['trades']} | {zz['je_woche']} | {zz['pf_r']} | {zz['summe_r']} | "
                 f"{zz['max_rueckgang_r']} | {zz['long_r']} | {zz['short_r']} | {a['groesster_verlust_r']} | "
                 f"{a['robust']['pf_r']} | {a['haelfte_1']['pf_r']} | {a['haelfte_2']['pf_r']} | "
                 f"{a['jahr_2026']['pf_r']} | {a['kontrolle']['pf_r']} | {a['kontrolle']['summe_r']} |")
    n, nk = res["k5_rund"]["nacht"], res["k5_rund"]["nacht_kontrolle"]
    z += ["", "Nur die Nachttrades von k5_rund (Signalkerze vor 7 oder ab 20 Uhr UTC):", "",
          "| Teil | Trades | je Woche | PF | Summe R |", "|---|---|---|---|---|",
          f"| Zeitraum | {n['trades']} | {n['je_woche']} | {n['pf_r']} | {n['summe_r']} |",
          f"| Kontrolle | {nk['trades']} | {nk['je_woche']} | {nk['pf_r']} | {nk['summe_r']} |", "",
          "Fester Spread 0,50 wie in VORAB_pine5m. Nachts ist der Capital.com-Spread oft breiter, der Live-Bot nimmt "
          "den echten."]
    return "\n".join(z) + "\n"


def main(argv: list[str]) -> int:
    check_vorab()
    k5.check_vorab()
    p5.check_vorab()
    res = rechne()
    u = wahl(res)
    erg = {"vorab_sha256": sha256_text(VORAB.read_text(encoding="utf-8")), "wahl": u, "varianten": res}
    (ROOT / "suche" / "ergebnis_pine5m_rund.json").write_text(json.dumps(erg, ensure_ascii=False, indent=1) + "\n",
                                                             encoding="utf-8")
    (ROOT / "suche" / "ergebnis_pine5m_rund.md").write_text(bericht(res, u), encoding="utf-8")
    print(json.dumps({k: v for k, v in u.items() if k != "alle"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
