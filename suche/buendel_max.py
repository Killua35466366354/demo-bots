"""Test Super-Bündel für 1.000 € (Regeln suche/VORAB_buendel_max.yaml, versiegelt vor dem Rechnen).

Alle gewählten Bots handeln gleichzeitig auf einem Konto mit 1.000 €. Je Stufe des Einsatzes je Trade fliegen so lange
die Bots mit dem wenigsten Euro je Euro Margin raus, bis Margin und Rückgang passen. Gewählt wird an November 2024 bis
Dezember 2025, das Urteil fällt an Januar bis Oktober 2026 gegen das heutige Bündel aus 9 Bots.

    python -m suche.buendel_max <Projektordner>      # schreibt suche/ergebnis_buendel_max.md

Spricht mit keinem Broker und ändert keinen Bot.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import numpy as np
import pandas as pd
import yaml

from suche.runde1 import last_value, sha256_text

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_buendel_max.yaml"
ERGEBNIS = ROOT / "suche" / "ergebnis_buendel_max.md"
PROTOKOLL = ROOT / "journal" / "strategie-suche-protokoll.md"
KEY = "VORAB_buendel_max sha256 "

BEENDET = ("pine-tp3", "r6-vortag-gbpjpy")
OHNE_MARGIN = ("scalp-us100", "scalp-j225")
MARGIN_VON = "scalp-de40"
# Die 9 Mitglieder des heutigen Bündels (suche/buendel_bot.py) mit ihrem Namen in der Trade-Datei.
BUENDEL9 = ("gold-cb", "gold-zonen", "gold-ausbruch4h", "r5-ruecksetzer-us500", "r5-ruecksetzer-us100",
            "r7-nasdaq-noise-long", "scalp-de40", "scalp-us100", "welt-ausbruch4h")


def regel() -> dict:
    return yaml.safe_load(VORAB.read_text(encoding="utf-8"))["buendel_max"]


def siegel_ok() -> bool:
    lines = PROTOKOLL.read_text(encoding="utf-8").splitlines()
    return last_value(lines, KEY) == sha256_text(VORAB.read_text(encoding="utf-8"))


def lade(projekt: pathlib.Path, soll_sha: str) -> pd.DataFrame:
    datei = projekt / "schatten-labor" / "alle_margin.csv"
    ist = hashlib.sha256(datei.read_bytes()).hexdigest()
    if ist != soll_sha:
        raise SystemExit(f"Trade-Datei passt nicht zur Regel: {ist} statt {soll_sha}")
    t = pd.read_csv(datei, parse_dates=["ein", "aus"])
    return margin_auffuellen(t)


def margin_auffuellen(t: pd.DataFrame) -> pd.DataFrame:
    t = t.copy()
    median = float(t.loc[t.id == MARGIN_VON, "margin_je_r"].median())
    fehlt = t.id.isin(OHNE_MARGIN) & t.margin_je_r.isna()
    t.loc[fehlt, "margin_je_r"] = median
    if t.margin_je_r.isna().any():
        raise SystemExit("Trades ohne Margin: " + ", ".join(sorted(t.loc[t.margin_je_r.isna(), "id"].unique())))
    return t


def zeitraum(t: pd.DataFrame, von: str, bis: str) -> pd.DataFrame:
    """Ein Trade gehört zum Zeitraum seines Einstiegs."""
    ende = pd.Timestamp(bis) + pd.Timedelta(days=1)
    return t[(t.ein >= pd.Timestamp(von)) & (t.ein < ende)]


def monate(von: str, bis: str) -> int:
    a, b = pd.Timestamp(von), pd.Timestamp(bis)
    return (b.year - a.year) * 12 + b.month - a.month + 1


def lauf(t: pd.DataFrame, einsatz: float, n_monate: int, start: float = 1000.0,
         grenze_margin: float = 0.80, grenze_rueckgang: float = 0.30) -> dict:
    """Ein Konto, jeder Trade wird genommen. Kontostand nur aus geschlossenen Trades, zuerst der Schluss bei
    gleicher Minute. Gibt Euro im Monat, Rendite, höchste Margin-Quote, Rückgang und machbar zurück."""
    if t.empty:
        return {"trades": 0, "eur_monat": 0.0, "rendite": 0.0, "margin_quote": 0.0, "margin_max": 0.0,
                "rueckgang_pct": 0.0, "rueckgang_eur": 0.0, "monate_minus": 0, "machbar": False}
    pnl = t.r.to_numpy(float) * einsatz
    m = t.margin_je_r.to_numpy(float) * einsatz
    ein = t.ein.to_numpy("datetime64[m]")
    aus = t.aus.to_numpy("datetime64[m]")
    n = len(t)
    # Art: 0 Schluss, 1 Eröffnung, 2 Schluss eines Trades ohne Dauer (erst nach seiner Eröffnung)
    zeit = np.concatenate([ein, aus])
    art = np.concatenate([np.ones(n, int), np.where(aus == ein, 2, 0)])
    dm = np.concatenate([m, -m])
    dg = np.concatenate([np.zeros(n), pnl])
    order = np.lexsort((art, zeit))
    margin = np.cumsum(dm[order])
    stand = start + np.cumsum(dg[order])
    margin = np.where(np.abs(margin) < 1e-9, 0.0, margin)
    quote = np.where(margin > 0, np.where(stand > 0, margin / np.maximum(stand, 1e-9), np.inf), 0.0)
    gesch = order >= n                                   # Ereignisse, die den Kontostand ändern
    kurve = np.concatenate([[start], stand[gesch]])
    spitze = np.maximum.accumulate(kurve)
    rueck_eur = float((spitze - kurve).max())
    rueck_pct = float(((spitze - kurve) / spitze).max())
    summe = float(pnl.sum())
    je_monat = pd.Series(pnl, index=t.ein.dt.to_period("M").to_numpy()).groupby(level=0).sum()
    q = float(quote.max())
    return {"trades": n, "eur_monat": summe / n_monate, "rendite": summe / n_monate / start,
            "margin_quote": q, "margin_max": float(margin.max()), "rueckgang_pct": rueck_pct,
            "rueckgang_eur": rueck_eur, "monate_minus": int((je_monat < 0).sum()),
            "machbar": bool(q <= grenze_margin and rueck_pct <= grenze_rueckgang)}


def effizienz(t: pd.DataFrame) -> pd.Series:
    """Summe € in der Wahl geteilt durch Margin-Euro-Tage in der Wahl (beides mit 10 € je R)."""
    tage = (t.aus - t.ein).dt.total_seconds() / 86400.0
    eur = (t.r * 10).groupby(t.id).sum()
    mt = (t.margin_je_r * 10 * tage).groupby(t.id).sum()
    return eur / mt.replace(0, np.nan)


def waehle(wahl: pd.DataFrame, rg: dict) -> dict:
    nm = monate(*[str(x) for x in rg["wahl"]["zeitraum"]])
    pool = wahl[~wahl.id.isin(BEENDET)]
    eur_monat_10 = (pool.r * 10).groupby(pool.id).sum() / nm
    raus_nix = sorted(eur_monat_10[eur_monat_10 < 2].index)
    uebrig = sorted(eur_monat_10[eur_monat_10 >= 2].index)
    eff = effizienz(pool[pool.id.isin(uebrig)])
    stufen = []
    for p in rg["konto"]["einsatz_stufen_prozent"]:
        einsatz = p / 100 * rg["konto"]["start_eur"]
        bots = list(uebrig)
        gestrichen = []
        while bots:
            e = lauf(pool[pool.id.isin(bots)], einsatz, nm)
            if e["machbar"]:
                break
            schwach = min(bots, key=lambda b: (eff[b], b))
            bots.remove(schwach)
            gestrichen.append(schwach)
        if not bots:
            e = lauf(pool.iloc[0:0], einsatz, nm)
        stufen.append({"stufe": p, "einsatz": einsatz, "bots": bots, "gestrichen": gestrichen, **e})
    machbar = [s for s in stufen if s["machbar"]]
    gewaehlt = max(machbar, key=lambda s: (s["eur_monat"], -s["stufe"])) if machbar else None
    return {"monate": nm, "eur_monat_10": eur_monat_10.round(2).to_dict(), "raus_nix": raus_nix,
            "uebrig": uebrig, "effizienz": eff.to_dict(), "stufen": stufen, "gewaehlt": gewaehlt}


def rechne(projekt: pathlib.Path) -> dict:
    rg = regel()
    if not siegel_ok():
        raise SystemExit("Siegel fehlt oder passt nicht. Erst festlegen, dann rechnen.")
    t = lade(projekt, rg["trades"]["sha256"])
    w_von, w_bis = [str(x) for x in rg["wahl"]["zeitraum"]]
    u_von, u_bis = [str(x) for x in rg["urteil"]["zeitraum"]]
    wahl = zeitraum(t, w_von, w_bis)
    urt = zeitraum(t, u_von, u_bis)
    nm_u = monate(u_von, u_bis)
    w = waehle(wahl, rg)
    g = w["gewaehlt"]
    urteil_stufen = []
    for s in w["stufen"]:
        e = lauf(urt[urt.id.isin(s["bots"])], s["einsatz"], nm_u) if s["bots"] else lauf(urt.iloc[0:0], 0, nm_u)
        urteil_stufen.append({"stufe": s["stufe"], "bots": s["bots"], **e})
    b9_u = lauf(urt[urt.id.isin(BUENDEL9)], 10.0, nm_u)
    alle_u = lauf(urt, 10.0, nm_u)
    b9_w = lauf(wahl[wahl.id.isin(BUENDEL9)], 10.0, w["monate"])
    alle_w = lauf(wahl, 10.0, w["monate"])
    erg = {"wahl": w, "urteil_stufen": urteil_stufen, "buendel9_urteil": b9_u, "alle_urteil": alle_u,
           "buendel9_wahl": b9_w, "alle_wahl": alle_w, "bestanden": False, "gruende": []}
    if g is None:
        erg["gruende"].append("keine Stufe in der Wahl machbar")
        return erg
    u = next(x for x in urteil_stufen if x["stufe"] == g["stufe"])
    erg["urteil"] = u
    if not u["eur_monat"] > 0:
        erg["gruende"].append("Euro im Monat nicht über 0")
    if not u["machbar"]:
        erg["gruende"].append("2026 nicht machbar (Margin oder Rückgang zu hoch)")
    if not u["rendite"] >= b9_u["rendite"]:
        erg["gruende"].append("Rendite pro Monat unter dem heutigen Bündel aus 9 Bots")
    erg["bestanden"] = not erg["gruende"]
    voll_bis = u_bis
    ganz = zeitraum(t, w_von, voll_bis)
    erg["ganz"] = lauf(ganz[ganz.id.isin(g["bots"])], g["einsatz"], monate(w_von, voll_bis))
    erg["ganz_buendel9"] = lauf(ganz[ganz.id.isin(BUENDEL9)], 10.0, monate(w_von, voll_bis))
    return erg


def _e(x: float, n: int = 0) -> str:
    s = f"{x:,.{n}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def _p(x: float, n: int = 1) -> str:
    return "∞" if not np.isfinite(x) else _e(100 * x, n) + " %"


def bericht(e: dict) -> str:
    w = e["wahl"]
    g = w["gewaehlt"]
    z = ["# Ergebnis Super-Bündel für 1.000 €", "",
         "Regeln: `suche/VORAB_buendel_max.yaml` (versiegelt vor dem Rechnen). Rechnung: `suche/buendel_max.py`.", ""]
    if e["bestanden"]:
        z.append(f"**Bestanden.** {len(g['bots'])} Bots mit {_e(g['stufe'], 2)} % Einsatz je Trade "
                 f"({_e(g['einsatz'])} € je R) brachten 2026 {_e(e['urteil']['eur_monat'])} € im Monat auf 1.000 € "
                 f"({_p(e['urteil']['rendite'])} Rendite pro Monat), das heutige Bündel aus 9 Bots "
                 f"{_e(e['buendel9_urteil']['eur_monat'])} € ({_p(e['buendel9_urteil']['rendite'])}).")
    else:
        z.append("**Nicht bestanden.** Gründe: " + ", ".join(e["gruende"]) + ".")
    z += ["", "## Wahl: November 2024 bis Dezember 2025", "",
          f"Gestrichen, weil unter 2 € im Monat mit 10 € je R: {', '.join(w['raus_nix']) or 'keiner'}.",
          f"Beendet und nicht dabei: {', '.join(BEENDET)}.", "",
          "| Bot | € im Monat mit 10 € je R | € je Euro Margin je Tag |", "|---|---:|---:|"]
    for b, v in sorted(w["eur_monat_10"].items(), key=lambda kv: -kv[1]):
        eff = w["effizienz"].get(b)
        z.append(f"| {b} | {_e(v, 1)} | {'' if eff is None or not np.isfinite(eff) else _e(eff, 4)} |")
    z += ["", "| Stufe | Bots | € im Monat | Rendite pro Monat | Rückgang | höchste Margin | Monate im Minus | machbar | gestrichen |",
          "|---:|---:|---:|---:|---:|---:|---:|---|---|"]
    for s in w["stufen"]:
        z.append(f"| {_e(s['stufe'], 2)} % | {len(s['bots'])} | {_e(s['eur_monat'])} | {_p(s['rendite'])} | "
                 f"{_p(s['rueckgang_pct'])} ({_e(s['rueckgang_eur'])} €) | {_p(s['margin_quote'])} ({_e(s['margin_max'])} €) | "
                 f"{s['monate_minus']} von {w['monate']} | {'ja' if s['machbar'] else 'nein'} | {', '.join(s['gestrichen']) or '-'} |")
    vergleich = (f"Zum Vergleich mit 1 %: alle 19 Bots {_e(e['alle_wahl']['eur_monat'])} € im Monat "
                 f"(Margin bis {_p(e['alle_wahl']['margin_quote'])}, Rückgang {_p(e['alle_wahl']['rueckgang_pct'])}), "
                 f"das heutige Bündel aus 9 Bots {_e(e['buendel9_wahl']['eur_monat'])} € "
                 f"(Margin bis {_p(e['buendel9_wahl']['margin_quote'])}, "
                 f"Rückgang {_p(e['buendel9_wahl']['rueckgang_pct'])}).")
    z += ["", vergleich, ""]
    if g:
        z += [f"Gewählt: Stufe {_e(g['stufe'], 2)} % mit {', '.join(g['bots'])}.", ""]
    z += ["## Urteil: Januar bis Oktober 2026", "",
          "| Stufe | Bots | € im Monat | Rendite pro Monat | Rückgang | höchste Margin | Monate im Minus | machbar |",
          "|---:|---:|---:|---:|---:|---:|---:|---|"]
    for s in e["urteil_stufen"]:
        mark = " (gewählt)" if g and s["stufe"] == g["stufe"] else ""
        z.append(f"| {_e(s['stufe'], 2)} %{mark} | {len(s['bots'])} | {_e(s['eur_monat'])} | {_p(s['rendite'])} | "
                 f"{_p(s['rueckgang_pct'])} ({_e(s['rueckgang_eur'])} €) | {_p(s['margin_quote'])} ({_e(s['margin_max'])} €) | "
                 f"{s['monate_minus']} von 10 | {'ja' if s['machbar'] else 'nein'} |")
    b9, al = e["buendel9_urteil"], e["alle_urteil"]
    z9 = (f"Heutiges Bündel aus 9 Bots mit 1 %: {_e(b9['eur_monat'])} € im Monat ({_p(b9['rendite'])}), "
          f"Rückgang {_p(b9['rueckgang_pct'])}, Margin bis {_p(b9['margin_quote'])}, {b9['monate_minus']} Monate im Minus.")
    z19 = (f"Alle 19 Bots mit 1 % (Auskunft): {_e(al['eur_monat'])} € im Monat ({_p(al['rendite'])}), "
           f"Rückgang {_p(al['rueckgang_pct'])}, Margin bis {_p(al['margin_quote'])}.")
    z += ["", z9, z19, ""]
    if "ganz" in e:
        gz, gb = e["ganz"], e["ganz_buendel9"]
        zg = (f"Gewählte Fassung: {_e(gz['eur_monat'])} € im Monat ({_p(gz['rendite'])}), "
              f"Rückgang {_p(gz['rueckgang_pct'])} ({_e(gz['rueckgang_eur'])} €), Margin bis {_p(gz['margin_quote'])}, "
              f"{gz['monate_minus']} Monate im Minus.")
        zb = (f"Heutiges Bündel aus 9 Bots mit 1 %: {_e(gb['eur_monat'])} € im Monat ({_p(gb['rendite'])}), "
              f"Rückgang {_p(gb['rueckgang_pct'])}.")
        z += ["## Ganzer Zeitraum November 2024 bis Oktober 2026 (Auskunft)", "", zg, zb, ""]
    hinweis = ("Der Kontostand zählt nur geschlossene Trades. Ein offener Verlust kann darum die 20 % Luft über der "
               "Margin aufbrauchen, das sieht diese Rechnung nicht. Kosten und Spread sind in den Trades enthalten, "
               "Zinsen über Nacht nicht.")
    z += ["## Ehrlich", "", regel()["ehrlich"], "", hinweis, ""]
    return "\n".join(z)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    e = rechne(pathlib.Path(argv[0]))
    ERGEBNIS.write_text(bericht(e), encoding="utf-8")
    kurz = {"bestanden": e["bestanden"], "gruende": e["gruende"],
            "gewaehlt": None if not e["wahl"]["gewaehlt"] else {k: e["wahl"]["gewaehlt"][k] for k in ("stufe", "bots", "eur_monat", "rendite")},
            "urteil": e.get("urteil"), "buendel9_urteil": e["buendel9_urteil"]}
    print(json.dumps(kurz, indent=1, ensure_ascii=False, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
