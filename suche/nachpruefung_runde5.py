"""Nachtrag zur Nachprüfung nach der Grundregel "2024 bis 2026 zählt am meisten": Runde 5 und 5b (Swing auf Tageskerzen).

Die Nachprüfung vom 10.11.2026 (suche/nachpruefung_2024_26.py) hat nur gespeicherte Trades im CSV-Format gelesen. Die
Trades von Runde 5 (41 Märkte, darunter vier Trendfolger über alle Märkte) liegen als JSON im Projektordner und fehlten
deshalb. Die versiegelte Regel suche/VORAB_bewertung_2024_26.yaml verlangt, alle gespeicherten Trades neu zu lesen.
Dieses Programm holt das nach. Anlass ist Punkt F3 der Kritik vom 05.11.2026 ("ein Trendfolger über viele Märkte").

Vor dem Lesen festgelegt (keine neuen Varianten, keine neuen Parameter):
- Gelesen werden genau die Varianten, die damals gerechnet wurden: die 11 Strategien von Runde 5 je über alle ihre Märkte
  (runde5/runde5_trades.json) und die 3 Strategien von Runde 5b nur auf US500 und US100 (runde5/runde5b_trades.json).
  Die Kombis von Runde 5 werden nicht neu gebaut.
- Zeit = Tag des Einstiegs, Ergebnis = Gewinn nach Spread und Übernachtgebühr in Tagesschwankungen (ATR 20), wie in
  Runde 5. Urteil mit urteil() der Nachprüfung, also denselben Hürden.
- Für diese Trades gibt es ab 2024 keine Rechnung mit 1,5-fachen Kosten und keinen Zufallsvergleich. Besteht eine
  Variante die übrigen Hürden, ist das nur ein Hinweis. Vor einem Bot müsste sie mit beidem neu gerechnet werden.
- Nur Auskunft: die vier Trendfolger je Marktklasse. Daraus kann nichts bestehen.

Aufruf: python -m suche.nachpruefung_runde5 <Projektordner strategie-suche>
Schreibt suche/ergebnis_nachpruefung_runde5.json und .md.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pandas as pd

from suche.nachpruefung_2024_26 import SUCHE, aus_trades, vorab_ok

TREND = ("tsmom_12m", "abstimmung", "ewmac", "donchian_trend")
NAMEN = {"tsmom_12m": "Trendfolge 12 Monate (alle Märkte)", "abstimmung": "Trendfolge Abstimmung 1/3/12 Monate (alle Märkte)",
         "ewmac": "Trendfolge EWMAC (alle Märkte)", "donchian_trend": "Trendfolge Donchian 55 Tage (alle Märkte)",
         "trend_ruecksetzer": "Trend-Rücksetzer (alle Märkte)", "rsi2_index": "RSI 2 (Indizes)", "ibs_index": "IBS (Indizes)",
         "double7_index": "Double 7 (Indizes)", "monatswechsel_index": "Monatswechsel (Indizes)",
         "index_momentum": "Index-Momentum (Reddit)", "vola_ruecksetzer": "Schwankungs-Rücksetzer (Indizes)"}
US = {"rsi2_index": "RSI 2 (nur US500 und US100)", "double7_index": "Double 7 (nur US500 und US100)",
      "trend_ruecksetzer": "Trend-Rücksetzer (nur US500 und US100, läuft als Bot)"}


def sammeln(trades: dict, strategie: str, maerkte=None) -> pd.DataFrame:
    """Alle Trades einer Strategie über die Märkte: Spalten zeit, r, markt."""
    rows = [(t["datum"], t["r"], sym) for sym, st in trades.items() if maerkte is None or sym in maerkte
            for t in st.get(strategie) or []]
    return pd.DataFrame(rows, columns=["zeit", "r", "markt"])


def pruefe(quelle: str, name: str, df: pd.DataFrame) -> dict | None:
    if df.empty:
        return None
    z = aus_trades(quelle, name, df["zeit"], df["r"])
    if z is not None:
        z["maerkte"] = int(df["markt"].nunique())
        z["pruefung"] = "gespeicherte Trades ab 2024, ohne 1,5-fache Kosten und ohne Zufallsvergleich"
    return z


def lesen(ordner: pathlib.Path) -> dict:
    r5 = json.loads((ordner / "runde5" / "runde5_trades.json").read_text(encoding="utf-8"))
    r5b = json.loads((ordner / "runde5" / "runde5b_trades.json").read_text(encoding="utf-8"))
    klassen = {s: m.get("klasse") for s, m in
               json.loads((ordner / "runde5" / "runde5.json").read_text(encoding="utf-8"))["maerkte"].items()}
    varianten = []
    for key in sorted({n for st in r5.values() for n in st}, key=lambda k: (k not in TREND, k)):
        z = pruefe("Runde 5", NAMEN.get(key, key), sammeln(r5, key))
        if z:
            varianten.append(z)
    for key, name in US.items():
        z = pruefe("Runde 5b", name, sammeln(r5b, key))
        if z:
            varianten.append(z)
    auskunft = []
    for key in TREND:
        for kl in sorted({k for k in klassen.values() if k}):
            z = pruefe("Runde 5", f"{NAMEN[key]}, nur {kl}", sammeln(r5, key, {s for s, k in klassen.items() if k == kl}))
            if z:
                auskunft.append({k: z[k] for k in ("name", "maerkte", "trades", "je_woche", "pf", "summe_r", "vor_2024_auskunft")})
    return {"varianten": varianten, "trendfolger_je_klasse_nur_auskunft": auskunft,
            "bestehen": [z["name"] for z in varianten if z["bestanden"]]}


def _z(x, n: int = 2) -> str:
    return "–" if x is None else f"{x:.{n}f}".replace(".", ",")


def bericht(res: dict) -> str:
    zeilen = ["# Nachtrag zur Nachprüfung 2024 bis 2026: Runde 5 und 5b (Tageskerzen)", "",
              "Regel: `suche/VORAB_bewertung_2024_26.yaml`, unverändert. Gelesen wurden die gespeicherten Trades von Runde 5 "
              "(41 Märkte) und Runde 5b (US500, US100). Die Nachprüfung vom 10.11.2026 hatte sie nicht gelesen, weil sie "
              "nur CSV-Dateien kannte. Ergebnis je Trade in Tagesschwankungen (ATR 20), nach Spread und Übernachtgebühr.", "",
              f"**{len(res['varianten'])} Varianten gelesen, {len(res['bestehen'])} bestehen die Hürden, die es hier gibt.** "
              "Für diese Trades gibt es ab 2024 keine Rechnung mit 1,5-fachen Kosten und keinen Zufallsvergleich.", "",
              "| Variante | Märkte | Trades ab 2024 | je Woche | Gewinnfaktor | Summe | Hälfte 1 | Hälfte 2 | 2026 | vor 2024 "
              "(Trades, GF) | bestanden | was fehlt |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for z in res["varianten"]:
        alt = z.get("vor_2024_auskunft") or {}
        zeilen.append(f"| {z['name']} | {z['maerkte']} | {z['trades']} | {_z(z['je_woche'])} | {_z(z['pf'])} | "
                      f"{_z(z['summe_r'], 1)} | {_z(z['h1'][0])} ({z['h1'][1]}) | {_z(z['h2'][0])} ({z['h2'][1]}) | "
                      f"{_z(z['j2026'][0])} ({z['j2026'][1]}) | {alt.get('trades', '–')}, {_z(alt.get('pf'))} | "
                      f"{'JA' if z['bestanden'] else 'nein'} | {', '.join(z['fehlt']) or '–'} |")
    zeilen += ["", "## Nur Auskunft: die vier Trendfolger je Marktklasse", "",
               "| Variante | Märkte | Trades ab 2024 | je Woche | Gewinnfaktor | Summe | vor 2024 (Trades, GF) |",
               "|---|---|---|---|---|---|---|"]
    for a in res["trendfolger_je_klasse_nur_auskunft"]:
        alt = a.get("vor_2024_auskunft") or {}
        zeilen.append(f"| {a['name']} | {a['maerkte']} | {a['trades']} | {_z(a['je_woche'])} | {_z(a['pf'])} | "
                      f"{_z(a['summe_r'], 1)} | {alt.get('trades', '–')}, {_z(alt.get('pf'))} |")
    zeilen += ["", "Aus der Tabelle je Marktklasse kann nichts bestehen. Sie zeigt nur, wo die Trendfolge ab 2024 verdient "
               "oder verloren hat. Keine Nachbesserung nach dem Ergebnis.", ""]
    return "\n".join(zeilen)


def main(argv: list[str]) -> int:
    if not vorab_ok():
        raise SystemExit("suche/VORAB_bewertung_2024_26.yaml steht so nicht im Protokoll.")
    res = lesen(pathlib.Path(argv[0]))
    (SUCHE / "ergebnis_nachpruefung_runde5.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n",
                                                             encoding="utf-8")
    (SUCHE / "ergebnis_nachpruefung_runde5.md").write_text(bericht(res), encoding="utf-8")
    print(bericht(res))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
