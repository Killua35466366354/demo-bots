"""Nachprüfung alter Backtests nach der Grundregel "2024 bis 2026 zählen am meisten" (suche/VORAB_bewertung_2024_26.yaml,
Kirons Wort vom 10.11.2026 17:05 UTC). Keine neuen Varianten, nur das Lesen der gespeicherten Ergebnisse:

- Ergebnis-Dateien im Repo, deren Rechenzeitraum ganz ab 2024 liegt (01.11.2024 bis 30.10.2026): Scalping Schritt 2,
  Runde 2b, Scalping mit Opens, Pine 5 Min., Gold-Short K2. Es gilt die Regel ohne die Kontrolle 2022-24 (nur Auskunft).
- Gespeicherte einzelne Trades im Projektordner strategie-suche (Zeit und Ergebnis in R): ab 01.01.2024 neu gezählt.
  Dort gibt es keine Rechnung mit 1,5-fachem Spread und keinen Zufallsvergleich, das steht dabei.

Aufruf: python -m suche.nachpruefung_2024_26 [<Projektordner strategie-suche>]
Schreibt suche/ergebnis_nachpruefung_2024_26.json und .md.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUCHE = ROOT / "suche"
VORAB = SUCHE / "VORAB_bewertung_2024_26.yaml"
KEY = "VORAB_bewertung_2024_26 sha256 "
AB = pd.Timestamp("2024-01-01")
MIN_TRADES, MIN_PF, MIN_ROBUST, MIN_2026_TRADES = 100, 1.2, 1.0, 20
VIELE = 2.0                                  # Trades je Woche: zuerst melden
# Auswertungen der laufenden Bots (keine durchgefallenen Strategien) und Stop-Vergleiche bleiben draußen
OHNE = ("bewertung/", "runde6/auswertung", "stopwahl/", "swingstop/", "vier_wochen/", "langzeit/")


def vorab_ok() -> bool:
    from suche.runde1 import journal_lines, last_value, sha256_text
    return VORAB.exists() and last_value(journal_lines(), KEY) == sha256_text(VORAB.read_text(encoding="utf-8"))


def _pf(b: dict | None) -> float | None:
    if not isinstance(b, dict):
        return None
    x = b.get("pf", b.get("pf_r"))
    return None if x is None else float(x)


def _n(b: dict | None) -> int:
    return int((b or {}).get("trades") or 0)


def urteil(z: dict) -> tuple[bool, list[str]]:
    """z: trades, pf, robust_pf, h1/h2 (pf, n), j2026 (pf, n), zufall (True/False/None)."""
    fehlt = []
    if z["trades"] < MIN_TRADES:
        fehlt.append(f"nur {z['trades']} Trades")
    if z["pf"] is None or z["pf"] < MIN_PF:
        fehlt.append(f"GF {z['pf']}")
    if z.get("robust_pf") is not None and z["robust_pf"] < MIN_ROBUST:
        fehlt.append(f"1,5x Spread {z['robust_pf']}")
    for h in ("h1", "h2"):
        pf, n = z[h]
        if n and (pf is None or pf <= 1.0):
            fehlt.append(f"{'1.' if h == 'h1' else '2.'} Hälfte {pf}")
    pf, n = z["j2026"]
    if n >= MIN_2026_TRADES and (pf is None or pf <= 1.0):
        fehlt.append(f"2026 {pf}")
    if z.get("zufall") is False:
        fehlt.append("Zufallsvergleich")
    return not fehlt, fehlt


def aus_json_eintrag(quelle: str, name: str, e: dict, alt_bestanden, zufall=None) -> dict:
    z = {"quelle": quelle, "name": name, "fenster": "01.11.2024 bis 30.10.2026", "trades": _n(e.get("zeitraum")),
         "je_woche": (e.get("zeitraum") or {}).get("je_woche"), "pf": _pf(e.get("zeitraum")),
         "summe_r": (e.get("zeitraum") or {}).get("summe", (e.get("zeitraum") or {}).get("summe_r")),
         "robust_pf": _pf(e.get("robust")), "h1": (_pf(e.get("haelfte_1")), _n(e.get("haelfte_1"))),
         "h2": (_pf(e.get("haelfte_2")), _n(e.get("haelfte_2"))),
         "j2026": (_pf(e.get("jahr_2026")), _n(e.get("jahr_2026"))), "zufall": zufall,
         "kontrolle_pf_auskunft": _pf(e.get("kontrolle")), "alt_bestanden": alt_bestanden,
         "pruefung": "wie im Test, ohne Kontrolle 2022-24"}
    z["bestanden"], z["fehlt"] = urteil(z)
    return z


def repo_ergebnisse() -> list[dict]:
    rows = []
    for e in json.loads((SUCHE / "ergebnis_scalping.json").read_text(encoding="utf-8")):
        v = (e.get("vergleich") or {}).get("bestanden")
        rows.append(aus_json_eintrag("Scalping Schritt 2", f"{e['variante']} {e['markt']}", e, e.get("bestanden"), v))
    for e in json.loads((SUCHE / "ergebnis_scalping2.json").read_text(encoding="utf-8")):
        v = (e.get("vergleich") or {}).get("bestanden")
        rows.append(aus_json_eintrag("Runde 2b Scalping", f"{e['familie']}/{e['variante']} {e['markt']} {e['kerzen']} Min.",
                                     e, e.get("bestanden"), v))
    so = json.loads((SUCHE / "ergebnis_scalping_opens.json").read_text(encoding="utf-8"))
    for e in so["varianten"]:
        rows.append(aus_json_eintrag("Scalping mit Opens", f"{e['familie']}/{e['variante']} {e['markt']} "
                                     f"{e['kerzen']} Min. Filter {e['filter']}", e, None, None))
    p5 = json.loads((SUCHE / "ergebnis_pine5m.json").read_text(encoding="utf-8"))
    for m in p5["maerkte"]:
        for v, e in (m.get("varianten") or {}).items():
            rows.append(aus_json_eintrag("Pine 5 Min.", f"{v} {m['symbol']}", e, m.get("bestanden") if v == "abfaenger"
                                         else None, None))
    mb = json.loads((SUCHE / "ergebnis_markt_bot.json").read_text(encoding="utf-8"))
    for v in mb["varianten"]:
        pr = v["pruefen"]
        zuf = not any("Prüfen nur besser als" in x for x in v.get("verfehlt") or [])
        e2 = {"zeitraum": {**pr, "summe": pr.get("summe_r")}, "robust": v.get("robust_pruefen"),
              "haelfte_1": v.get("jahr_2025"), "haelfte_2": v.get("jahr_2026"), "jahr_2026": v.get("jahr_2026")}
        z = aus_json_eintrag("Markt-Bot (18 Aktien)", v["variante"], e2, v.get("bestanden"), zuf)
        z["fenster"], z["pruefung"] = "01.01.2025 bis 30.10.2026 (Prüfzeitraum)", "Hälften = 2025 und 2026"
        rows.append(z)
    k2 = json.loads((SUCHE / "ergebnis_gold_short_k2.json").read_text(encoding="utf-8"))
    for v, e in k2["varianten"].items():
        e2 = {"zeitraum": e.get("zeitraum_a"), "robust": e.get("robust"), "haelfte_1": e.get("haelfte_1"),
              "haelfte_2": e.get("haelfte_2"), "jahr_2026": e.get("jahr_2026"), "kontrolle": e.get("kontrolle_2022_2024")}
        zuf = e.get("zufall")
        zuf_ok = None if zuf is None else (float(zuf) >= 95 if not isinstance(zuf, dict) else None)
        rows.append(aus_json_eintrag("Gold-Short K2", v, e2, e.get("bestanden"), zuf_ok))
    return rows


# ---------- einzelne Trades im Projektordner ----------

ZEIT = ("t", "einstieg_utc", "einstieg_kerze_utc", "einstieg", "datum", "einstieg_tag", "tag")
GRUPPE = ("teil", "seite", "bot", "variante", "strategie", "familie")


def r_spalte(df: pd.DataFrame) -> str | None:
    if "ergebnis" in df.columns and "stop" in df.columns:      # Runde 12: r = Abstand, ergebnis = R
        return "ergebnis"
    for c in ("R", "r"):
        if c in df.columns:
            return c
    return None


def zeit_spalte(df: pd.DataFrame) -> str | None:
    for c in ZEIT:
        if c in df.columns:
            t = pd.to_datetime(df[c], errors="coerce", utc=True)
            if t.notna().mean() > 0.9:
                return c
    return None


def kennzahlen(r: np.ndarray) -> dict:
    g, v = r[r > 0].sum(), -r[r < 0].sum()
    return {"trades": int(len(r)), "pf": round(float(g / v), 2) if v > 0 else None, "summe_r": round(float(r.sum()), 1)}


def aus_trades(quelle: str, name: str, t: pd.Series, r: pd.Series) -> dict | None:
    t = pd.to_datetime(t, errors="coerce", utc=True).dt.tz_localize(None)
    ok = t.notna() & r.notna()
    t, r = t[ok], r[ok].astype(float)
    if not len(t) or t.max() < AB:
        return None
    m = t >= AB
    tt, rr = t[m], r[m].to_numpy()
    start, ende = max(AB, tt.min().normalize()), tt.max()
    wochen = max((ende - start).days / 7, 1)
    mitte = start + (ende - start) / 2
    k = kennzahlen(rr)
    h1, h2 = kennzahlen(rr[(tt < mitte).to_numpy()]), kennzahlen(rr[(tt >= mitte).to_numpy()])
    j = kennzahlen(rr[(tt >= pd.Timestamp("2026-01-01")).to_numpy()])
    alt = kennzahlen(r[~m].to_numpy()) if (~m).any() else None
    z = {"quelle": quelle, "name": name, "fenster": f"{start:%d.%m.%Y} bis {ende:%d.%m.%Y}", "trades": k["trades"],
         "je_woche": round(k["trades"] / wochen, 2), "pf": k["pf"], "summe_r": k["summe_r"], "robust_pf": None,
         "h1": (h1["pf"], h1["trades"]), "h2": (h2["pf"], h2["trades"]), "j2026": (j["pf"], j["trades"]),
         "zufall": None, "vor_2024_auskunft": alt, "alt_bestanden": None,
         "pruefung": "einzelne Trades ab 2024, ohne 1,5-fachen Spread und ohne Zufallsvergleich"}
    z["bestanden"], z["fehlt"] = urteil(z)
    return z


def zusatz_runde12(ordner: pathlib.Path, rel: str, name: str) -> tuple[float | None, bool | None, str | None]:
    """Runde 12d bis 12h: Spread-Probe und Zufall stehen in der Ergebnis-Datei (Zeitraum 11/2024 bis 10/2026), aber nur
    für ganze Strategien, nicht für einzelne Teile eines Kontos."""
    runde = rel.split("/")[0]
    if runde not in ("runde12d", "runde12e", "runde12f", "runde12g", "runde12h"):
        return None, None, None
    try:
        d = json.loads((ordner / runde / f"{runde}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None, None
    s = d.get("strategien") or {}
    v = s.get(name) if isinstance(s, dict) else None
    if not isinstance(v, dict):
        return None, None, None
    rb = (v.get("robust") or {}).get("pf_r")
    zf = v.get("zufall")
    return (None if rb is None else round(float(rb), 3)), (None if zf is None else float(zf) >= 95), \
        (None if v.get("kontrolle") is None else (v.get("kontrolle") or {}).get("pf_r"))


def projekt_trades(ordner: pathlib.Path) -> tuple[list[dict], list[str]]:
    rows, gelesen = [], []
    for p in sorted(ordner.rglob("*.csv*")):
        rel = p.relative_to(ordner).as_posix()
        if rel.startswith("daten/") or rel.startswith("aktien/") or any(rel.startswith(o) for o in OHNE):
            continue
        if not ("trade" in p.name.lower()):
            continue
        try:
            df = pd.read_csv(p)
        except Exception:                    # noqa: BLE001
            continue
        rc, tc = r_spalte(df), zeit_spalte(df)
        if rc is None or tc is None:
            continue
        gelesen.append(rel)
        grp = [c for c in GRUPPE if c in df.columns and df[c].nunique() <= 60]
        stamm = rel.rsplit(".csv", 1)[0]
        if grp:
            for key, g in df.groupby(grp):
                key = key if isinstance(key, tuple) else (key,)
                z = aus_trades(rel.split("/")[0], f"{stamm} {' '.join(map(str, key))}", g[tc], g[rc])
                if z:
                    rows.append(z)
        else:
            z = aus_trades(rel.split("/")[0], stamm, df[tc], df[rc])
            if z:
                name = p.name.split(".csv")[0].replace(rel.split("/")[0] + "_", "").replace("_trades", "")
                rb, zf, ko = zusatz_runde12(ordner, rel, name)
                if rb is not None or zf is not None:
                    z["robust_pf"], z["zufall"], z["kontrolle_pf_auskunft"] = rb, zf, ko
                    z["pruefung"] = "einzelne Trades ab 2024, Spread-Probe und Zufall aus der Ergebnis-Datei"
                    z["bestanden"], z["fehlt"] = urteil(z)
                rows.append(z)
    return rows, gelesen


def main(argv: list[str]) -> int:
    if not vorab_ok():
        print("Regel nicht versiegelt, nichts gerechnet")
        return 1
    rows = repo_ergebnisse()
    gelesen = []
    if argv:
        r2, gelesen = projekt_trades(pathlib.Path(argv[0]))
        rows += r2
    neu, gesehen = [], set()
    for z in rows:                           # dieselben Trades in mehreren Dateien (Teile eines Kontos) nur einmal
        key = (z["trades"], z["pf"], z["summe_r"])
        if z["bestanden"] and z["alt_bestanden"] is not True and key not in gesehen:
            gesehen.add(key)
            neu.append(z)
    neu.sort(key=lambda z: (0 if (z["je_woche"] or 0) >= VIELE else 1, -(z["pf"] or 0)))
    je_quelle = {}
    for z in rows:
        q = je_quelle.setdefault(z["quelle"], {"geprueft": 0, "bestehen_jetzt": 0, "bestanden_frueher": 0})
        q["geprueft"] += 1
        q["bestehen_jetzt"] += int(z["bestanden"])
        q["bestanden_frueher"] += int(z["alt_bestanden"] is True)
    out = {"vorab": "suche/VORAB_bewertung_2024_26.yaml", "geprueft": len(rows), "bestehen_jetzt": len(neu),
           "hinweis": "bestehen_jetzt zählt jede Variante einmal, auch wenn dieselben Trades in mehreren Dateien stehen.",
           "je_quelle": je_quelle, "trade_dateien": gelesen, "neu_bestanden": neu}
    (SUCHE / "ergebnis_nachpruefung_2024_26.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str)
                                                              + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k not in ("neu_bestanden", "trade_dateien")}, ensure_ascii=False,
                     indent=1))
    for z in neu[:60]:
        print(f"{z['je_woche']:>6} /W  GF {z['pf']:<5} {z['trades']:>5} Tr  {z['quelle']}: {z['name']}  "
              f"[robust {z['robust_pf']}, H1 {z['h1']}, H2 {z['h2']}, 2026 {z['j2026']}, Kontrolle "
              f"{z.get('kontrolle_pf_auskunft')}]")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
