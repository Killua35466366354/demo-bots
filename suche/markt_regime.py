"""Test Trend oder Seitwärts (Regeln suche/VORAB_markt_regime.yaml, versiegelt vor dem Rechnen).

Je Trade die Phase seines Markts aus dem Effizienz-Verhältnis der 20 Tagesschlüsse vor dem Einstieg. Gewählt wird je
Bot an November 2024 bis Dezember 2025, das Urteil fällt an 2026. Dazu als Auskunft der Anteil der Trendtage je Markt.

    python -m suche.markt_regime <Projektordner>      # schreibt suche/ergebnis_markt_regime.md

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

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_markt_regime.yaml"
ERGEBNIS = ROOT / "suche" / "ergebnis_markt_regime.md"
KEY = "VORAB_markt_regime sha256 "
NY = "America/New_York"


def regel() -> dict:
    return yaml.safe_load(VORAB.read_text(encoding="utf-8"))["markt_regime"]


def echtes_utc(idx: pd.Series) -> pd.DatetimeIndex:
    """HistData-Spalte utc in echtes UTC (LIESMICH_zeit.md): Index plus 2 Stunden als Ortszeit Europe/Athens."""
    lokal = pd.DatetimeIndex(pd.to_datetime(idx) + pd.Timedelta(hours=2))
    return lokal.tz_localize("Europe/Athens", ambiguous="NaT", nonexistent="NaT").tz_convert("UTC").tz_localize(None)


def tagesschluesse(pfad: pathlib.Path) -> pd.Series:
    """Letzter 5-Minuten-Schluss vor 17:00 New York je Handelstag. Index: Zeitpunkt des Schlusses (echtes UTC)."""
    d = pd.read_csv(pfad, usecols=["utc", "close"])
    t = echtes_utc(d["utc"])
    ok = ~t.isna()
    t, c = t[ok], d["close"].to_numpy()[ok]
    ny = pd.DatetimeIndex(t).tz_localize("UTC").tz_convert(NY)
    tag = (ny - pd.Timedelta(hours=17)).normalize().tz_localize(None) + pd.Timedelta(days=1)   # Handelstag endet 17:00 NY
    s = pd.Series(c, index=t + pd.Timedelta(minutes=5))      # Kerzen-Ende
    letzter = s.groupby(np.asarray(tag)).tail(1)
    return letzter.sort_index()


def effizienz(closes: np.ndarray, n: int) -> np.ndarray:
    """Effizienz-Verhältnis je Tag i aus den Schlüssen i-n bis i (n Bewegungen). NaN, solange n+1 Schlüsse fehlen."""
    c = np.asarray(closes, float)
    out = np.full(len(c), np.nan)
    bew = np.abs(np.diff(c))
    for i in range(n, len(c)):
        summe = bew[i - n:i].sum()
        out[i] = abs(c[i] - c[i - n]) / summe if summe > 0 else np.nan
    return out


def phase_je_trade(einstiege: pd.Series, schluesse: pd.Series, n: int, ab: float) -> pd.Series:
    """Für jeden Einstieg das Effizienz-Verhältnis der letzten n+1 Schlüsse, die vor dem Einstieg liegen."""
    er = effizienz(schluesse.to_numpy(), n)
    zeiten = schluesse.index.to_numpy()
    pos = np.searchsorted(zeiten, einstiege.to_numpy(dtype="datetime64[ns]"), side="left") - 1  # letzter Schluss davor
    wert = np.where(pos >= n, er[np.clip(pos, 0, len(er) - 1)], np.nan)
    ph = np.where(np.isnan(wert), None, np.where(wert >= ab, "trend", "seitwaerts"))
    return pd.Series(ph, index=einstiege.index), pd.Series(wert, index=einstiege.index)


def pf(r) -> float | None:
    r = np.asarray(r, float)
    g, v = r[r > 0].sum(), -r[r < 0].sum()
    return round(float(g / v), 3) if v > 0 else None


def zufall_p(r: np.ndarray, gewaehlt: np.ndarray, n: int, seed: int) -> float:
    """Anteil der Mischungen der Etiketten, in denen die Summe R der gewählten Etiketten mindestens so hoch ist wie echt."""
    rng = np.random.default_rng(seed)
    echt = r[gewaehlt].sum()
    k = int(gewaehlt.sum())
    if k == 0 or k == len(r):
        return 1.0
    treffer = 0
    for _ in range(n):
        idx = rng.permutation(len(r))[:k]
        treffer += r[idx].sum() >= echt - 1e-12
    return (treffer + 1) / (n + 1)


def holm(p: dict[str, float], alpha: float = 0.05) -> dict[str, bool]:
    out, m = {}, len(p)
    for i, (k, v) in enumerate(sorted(p.items(), key=lambda kv: kv[1])):
        if v > alpha / (m - i):
            for k2, _ in sorted(p.items(), key=lambda kv: kv[1])[i:]:
                out[k2] = False
            break
        out[k] = True
    return out


def rechne(projekt: pathlib.Path) -> dict:
    rg = regel()
    tdatei = projekt / "schatten-labor" / "alle_margin.csv"
    soll = rg["trades"]["sha256"]
    ist = hashlib.sha256(tdatei.read_bytes()).hexdigest()
    if ist != soll:
        raise SystemExit(f"Trade-Datei hat nicht die versiegelte Prüfsumme ({ist})")
    t = pd.read_csv(tdatei, parse_dates=["ein"])
    n, ab = int(rg["phase"]["tage"]), float(rg["phase"]["trend_ab"])
    daten = projekt / "strategie-suche" / "daten"
    schl = {}
    for markt, datei in rg["kurse"]["maerkte"].items():
        schl[markt] = tagesschluesse(daten / f"{datei}_5min.csv.gz")
    t["phase"], t["er"] = None, np.nan
    for markt, g in t.groupby("markt"):
        ph, wert = phase_je_trade(g["ein"], schl[markt], n, ab)
        t.loc[g.index, "phase"], t.loc[g.index, "er"] = ph, wert
    w0, w1 = (pd.Timestamp(x) for x in rg["wahl"]["zeitraum"])
    u0, u1 = (pd.Timestamp(x) for x in rg["urteil"]["zeitraum"])
    w1, u1 = w1 + pd.Timedelta(days=1), u1 + pd.Timedelta(days=1)
    mind_w = int(rg["wahl"]["mindestens_je_phase"])
    bots, p = {}, {}
    for bot, g in t[t["phase"].notna()].groupby("id"):
        wa = g[(g.ein >= w0) & (g.ein < w1)]
        ur = g[(g.ein >= u0) & (g.ein < u1)]
        z = {"markt": ",".join(sorted(set(g.markt))), "trades": len(g),
             "wahl": {ph: {"n": int((wa.phase == ph).sum()), "pf": pf(wa.r[wa.phase == ph])} for ph in ("trend", "seitwaerts")},
             "wahl_alle_pf": pf(wa.r), "ganz": {ph: {"n": int((g.phase == ph).sum()), "pf": pf(g.r[g.phase == ph]),
                                                     "summe_r": round(float(g.r[g.phase == ph].sum()), 2)}
                                               for ph in ("trend", "seitwaerts")}}
        gew = None
        if min(z["wahl"]["trend"]["n"], z["wahl"]["seitwaerts"]["n"]) >= mind_w:
            a, b = z["wahl"]["trend"]["pf"] or 0, z["wahl"]["seitwaerts"]["pf"] or 0
            kand = "trend" if a >= b else "seitwaerts"
            if (z["wahl"][kand]["pf"] or 0) > (z["wahl_alle_pf"] or 0):
                gew = kand
        z["gewaehlt"] = gew
        if gew:
            r = ur.r.to_numpy(float)
            mask = (ur.phase == gew).to_numpy()
            z["urteil"] = {"n": int(mask.sum()), "pf": pf(r[mask]), "pf_andere": pf(r[~mask]),
                           "summe_r": round(float(r[mask].sum()), 2), "alle_pf": pf(r)}
            p[bot] = zufall_p(r, mask, 10000, 20261120)
            z["urteil"]["p"] = round(p[bot], 4)
        bots[bot] = z
    h = holm(p)
    for bot, z in bots.items():
        if z["gewaehlt"]:
            u = z["urteil"]
            u["holm"] = h[bot]
            u["bestanden"] = bool(u["n"] >= 20 and (u["pf"] or 0) >= 1.2 and (u["pf"] or 0) > (u["pf_andere"] or 0) and h[bot])
    # Auskunft: Trendtage je Markt
    auskunft = {}
    for f in sorted(daten.glob("*_5min.csv.gz")):
        s = tagesschluesse(f)
        er = pd.Series(effizienz(s.to_numpy(), n), index=s.index)
        rich = np.sign(s - s.shift(n))
        teil = (s.index >= pd.Timestamp("2024-01-01")) & (s.index < pd.Timestamp("2026-11-01"))
        e2, r2 = er[teil].dropna(), rich[teil]
        if len(e2) < 100:
            continue
        tr = e2 >= ab
        auskunft[f.name.split("_")[0]] = {"tage": len(e2), "trend_anteil": round(float(tr.mean()), 3),
                                          "steigend": round(float(((r2[e2.index] > 0) & tr).mean()), 3),
                                          "fallend": round(float(((r2[e2.index] < 0) & tr).mean()), 3),
                                          "er_schnitt": round(float(e2.mean()), 3)}
    return {"bots": bots, "auskunft": auskunft, "n_filter": len(p),
            "bestanden": sorted(b for b, z in bots.items() if z.get("urteil", {}).get("bestanden"))}


NAMEN = {"XAUUSD": "Gold", "XAGUSD": "Silber", "SPXUSD": "S&P 500", "NSXUSD": "Nasdaq 100", "GRXEUR": "DAX", "UKXGBP": "FTSE 100",
         "JPXJPY": "Nikkei 225", "WTIUSD": "Öl (WTI)"}


def _z(x, n=2):
    return "–" if x is None else f"{x:.{n}f}".replace(".", ",")


def bericht(e: dict) -> str:
    z = ["# Ergebnis: Trend oder Seitwärts", "",
         "Regeln: `suche/VORAB_markt_regime.yaml`, versiegelt vor dem Rechnen. Rechnung: `python -m suche.markt_regime <Projektordner>`.", ""]
    best = e["bestanden"]
    z += [f"**{len(best)} von {e['n_filter']} Filtern bestanden.** " + ("Bestanden: " + ", ".join(best) + "." if best else
          "Kein Bot handelt im Urteil 2026 in seiner gewählten Phase klar besser."), ""]
    z += ["## Je Bot", "", "Gewählt an November 2024 bis Dezember 2025, Urteil an Januar bis Oktober 2026. GF heißt Gewinnfaktor.", "",
          "| Bot | Markt | Wahl Trend (n, GF) | Wahl Seitwärts (n, GF) | gewählt | 2026 gewählt (n, GF) | 2026 andere GF | p | bestanden |",
          "|---|---|---|---|---|---|---|---|---|"]
    for bot, b in sorted(e["bots"].items()):
        w, u = b["wahl"], b.get("urteil") or {}
        gew = {"trend": "Trend", "seitwaerts": "Seitwärts", None: "kein Filter"}[b["gewaehlt"]]
        z.append(f"| {bot} | {b['markt']} | {w['trend']['n']}, {_z(w['trend']['pf'])} | {w['seitwaerts']['n']}, {_z(w['seitwaerts']['pf'])} | "
                 f"{gew} | {u.get('n', '–')}, {_z(u.get('pf'))} | {_z(u.get('pf_andere'))} | {_z(u.get('p'), 3)} | "
                 f"{'ja' if u.get('bestanden') else ('nein' if u else '–')} |")
    z += ["", "## Auskunft: Welche Märkte laufen am längsten in eine Richtung", "",
          "Anteil der Handelstage 2024 bis Oktober 2026 mit Effizienz-Verhältnis ab 0,30 (Trendphase), getrennt nach Richtung. Kein Urteil.", "",
          "| Markt | Tage | Trendtage | davon steigend | davon fallend | Effizienz im Schnitt |", "|---|---|---|---|---|---|"]
    for m, a in sorted(e["auskunft"].items(), key=lambda kv: -kv[1]["trend_anteil"]):
        z.append(f"| {NAMEN.get(m, m)} | {a['tage']} | {_z(a['trend_anteil'] * 100, 0)} % | {_z(a['steigend'] * 100, 0)} % | "
                 f"{_z(a['fallend'] * 100, 0)} % | {_z(a['er_schnitt'])} |")
    z += ["", "## Auskunft: ganzer Zeitraum je Bot und Phase", "", "| Bot | Trend (n, GF, Summe R) | Seitwärts (n, GF, Summe R) |", "|---|---|---|"]
    for bot, b in sorted(e["bots"].items()):
        g = b["ganz"]
        z.append(f"| {bot} | {g['trend']['n']}, {_z(g['trend']['pf'])}, {_z(g['trend']['summe_r'], 1)} | "
                 f"{g['seitwaerts']['n']}, {_z(g['seitwaerts']['pf'])}, {_z(g['seitwaerts']['summe_r'], 1)} |")
    z += ["", "Ehrlich dazu: Die Trades sind Rückblick-Trades. Die Bots wurden an denselben Monaten fürs Bündel ausgesucht. Darum zählt nur das Urteil an 2026.", ""]
    return "\n".join(z)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    e = rechne(pathlib.Path(argv[0]))
    ERGEBNIS.write_text(bericht(e), encoding="utf-8")
    print(json.dumps({"bestanden": e["bestanden"], "n_filter": e["n_filter"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
