"""Opens aus Kirons Strategie-Video (suche/VORAB_opens.yaml). Nur rechnen, keine Order.

Kirons Wunsch vom 10.11.2026 10:33 UTC: das Video (TikTok montyfinance) analysieren und alle Strategien damit verbessern.
Das Video erklärt nur die Eröffnungskurse (Opens) von Tag, Woche, Monat, Quartal und Jahr als objektive Linien.

    python -m suche.opens <daten_ordner> <trades.csv>

<daten_ordner>: Projektdateien strategie-suche/daten mit {SYMBOL}_5min.csv.gz (HistData-Bid, UTC).
<trades.csv>: Projektdateien strategie-suche/bewertung/trades.csv (Bewertung vom 04.11.2026).
Ergebnis: suche/ergebnis_opens.json und suche/ergebnis_opens.md, eine Zeile im Protokoll.
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd
import yaml

from suche.runde1 import journal_add, journal_lines, last_value, sha256_text

HERE = pathlib.Path(__file__).resolve().parent
VORAB = HERE / "VORAB_opens.yaml"
KEY = "VORAB_opens sha256 "
NY = "America/New_York"
SEED = 20261110
N_ZUFALL = 5000
LADEN_AB = pd.Timestamp("2021-12-01")
EXTRA = {"AUDNZD": {"symbol": "AUDNZD", "spread": 0.0003, "stunden": [7, 20]},
         "GBPNZD": {"symbol": "GBPNZD", "spread": 0.0005, "stunden": [7, 20]}}
FILTER = {"jahr": "o_jahr", "quartal": "o_quartal", "monat": "o_monat", "woche": "o_woche"}
ZEITRAUM = ("2024-11-01", "2026-10-30")
HAELFTEN = (("2024-11-01", "2025-10-31"), ("2025-11-01", "2026-10-30"))
JAHR_2026 = ("2026-01-01", "2026-10-30")
KONTROLLE = ("2022-11-01", "2024-10-31")


def check_vorab() -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("suche/VORAB_opens.yaml weicht von der Prüfsumme im Protokoll ab, erst festlegen.")
    return yaml.safe_load(text)["opens"]


def lade(ordner: pathlib.Path, symbol: str) -> pd.DataFrame:
    d = pd.read_csv(ordner / f"{symbol}_5min.csv.gz", index_col=0, parse_dates=True)
    d = d[~d.index.duplicated(keep="last")].sort_index()
    return d[d.index >= LADEN_AB]


def perioden(bars: pd.DataFrame) -> pd.DataFrame:
    """Handelstag (endet 17:00 New York) und die Opens von Tag, Woche, Monat, Quartal und Jahr je Kerze."""
    ny = bars.index.tz_localize("UTC").tz_convert(NY).tz_localize(None)
    tag = (ny + pd.Timedelta(hours=7)).normalize()
    p = bars.copy()
    p["tag"] = tag
    p = p[tag.weekday < 5]
    t = pd.DatetimeIndex(p["tag"])
    keys = {"o_tag": t, "o_woche": t - pd.to_timedelta(t.weekday, unit="D"), "o_monat": t.to_period("M"),
            "o_quartal": t.to_period("Q"), "o_jahr": t.year}
    for col, k in keys.items():
        p[col] = p.groupby(np.asarray(k))["open"].transform("first").to_numpy()
    return p


def pf(r) -> float | None:
    r = np.asarray(r, float)
    if not len(r):
        return None
    g, v = r[r > 0].sum(), -r[r < 0].sum()
    return float(g / v) if v > 0 else (99.0 if g > 0 else None)


def runde(x, n=3):
    return None if x is None else round(float(x), n)


def kennzahlen(r) -> dict:
    r = np.asarray(r, float)
    return {"trades": int(len(r)), "pf_r": runde(pf(r)), "summe_r": runde(r.sum()) if len(r) else 0.0,
            "r_je_trade": runde(r.mean()) if len(r) else None}


# ---------------------------------------------------------------------------------------------------------------------
# Teil A: Open-Filter auf den Trades der laufenden Bots

def zufall_p(r: np.ndarray, k: int, ziel: float | None) -> float | None:
    if ziel is None or k == 0 or k >= len(r):
        return None
    rng = np.random.default_rng(SEED)
    idx = np.argsort(rng.random((N_ZUFALL, len(r))), axis=1)[:, :k]
    s = r[idx]
    g, v = np.where(s > 0, s, 0).sum(1), -np.where(s < 0, s, 0).sum(1)
    pfs = np.where(v > 0, g / np.where(v > 0, v, 1), np.where(g > 0, 99.0, 0.0))
    return float((pfs >= ziel - 1e-12).mean())


def teil_a(cfg: dict, ordner: pathlib.Path, trades_csv: pathlib.Path) -> dict:
    regel = cfg["teil_a_filter"]
    t = pd.read_csv(trades_csv)
    t["einstieg"] = pd.to_datetime(t["einstieg"], format="mixed")     # Tages-Bots haben nur ein Datum
    t = t[(t["einstieg"] >= "2025-01-01") & (t["einstieg"] < "2026-10-31")]
    cache: dict[str, pd.DataFrame] = {}
    out = {}
    for strat, sym in regel["strategien"].items():
        if sym not in cache:
            cache[sym] = perioden(lade(ordner, sym))
        p = cache[sym]
        d = t[t["strategie"] == strat].sort_values("einstieg").reset_index(drop=True)
        pos = p.index.searchsorted(d["einstieg"] - pd.Timedelta(minutes=5), side="right") - 1
        if (pos < 0).any():
            raise SystemExit(f"{strat}: Einstieg vor den Kerzen")
        ref = p.iloc[pos]
        alter = (d["einstieg"].to_numpy() - ref.index.to_numpy()) / np.timedelta64(1, "h")
        kurs = ref["close"].to_numpy(float)
        seite = np.where(d["richtung"].str.lower().str.startswith("l"), 1.0, -1.0)
        r = d["r"].to_numpy(float)
        jahr = d["einstieg"].dt.year.to_numpy()
        mit = {f: seite * (kurs - ref[c].to_numpy(float)) > 0 for f, c in FILTER.items()}
        mit["alle"] = mit["jahr"] & mit["quartal"] & mit["monat"] & mit["woche"]
        orig = kennzahlen(r)
        orig["je_jahr"] = {str(y): kennzahlen(r[jahr == y]) for y in (2025, 2026)}
        zeile = {"markt": sym, "original": orig, "max_alter_kurs_std": runde(alter.max(), 1), "filter": {}}
        for f, m in mit.items():
            k = kennzahlen(r[m])
            k["anteil"] = runde(m.mean() if len(m) else 0.0)
            k["weg"] = kennzahlen(r[~m])
            k["je_jahr"] = {str(y): kennzahlen(r[m & (jahr == y)]) for y in (2025, 2026)}
            k["p_zufall"] = runde(zufall_p(r, int(m.sum()), k["pf_r"]), 4)
            k["gruende"] = pruefe_a(orig, k)
            k["bestanden"] = not k["gruende"]
            zeile["filter"][f] = k
        ok = [(f, k) for f, k in zeile["filter"].items() if k["bestanden"]]
        ok.sort(key=lambda x: (x[1]["pf_r"], x[1]["trades"]), reverse=True)
        zeile["gewaehlt"] = ok[0][0] if ok else None
        out[strat] = zeile
    return out


def pruefe_a(orig: dict, k: dict) -> list[str]:
    g = []
    if k["trades"] < 15 or k["trades"] < 0.4 * orig["trades"]:
        g.append(f"nur {k['trades']} von {orig['trades']} Trades")
    if k["pf_r"] is None or k["pf_r"] < 1.2 or orig["pf_r"] is None or k["pf_r"] < orig["pf_r"] + 0.15:
        g.append(f"PF {k['pf_r']} statt mindestens 1,2 und Original {orig['pf_r']} plus 0,15")
    if k["weg"]["summe_r"] > 0:
        g.append(f"weggefiltert Summe R {k['weg']['summe_r']} über 0")
    for y in ("2025", "2026"):
        ky, oy = k["je_jahr"][y], orig["je_jahr"][y]
        if ky["trades"] < 5 or oy["r_je_trade"] is None or ky["r_je_trade"] is None or ky["r_je_trade"] <= oy["r_je_trade"]:
            g.append(f"{y} R je Trade {ky['r_je_trade']} nicht über {oy['r_je_trade']} ({ky['trades']} Trades)")
    if k["p_zufall"] is None or k["p_zufall"] > 0.01:
        g.append(f"Zufall p {k['p_zufall']} über 0,01")
    return g


# ---------------------------------------------------------------------------------------------------------------------
# Teil B: Rücklauf zum Wochen- bzw. Tages-Open in Richtung von Jahres-, Quartals- und Monats-Open

def tages_atr(p: pd.DataFrame) -> pd.Series:
    """ATR je Handelstag D = Mittel der wahren Spanne der letzten 14 fertigen Tage (ab 100 Kerzen) vor D."""
    g = p.groupby("tag")
    d = pd.DataFrame({"h": g["high"].max(), "l": g["low"].min(), "c": g["close"].last(), "n": g["close"].size()})
    d = d[d["n"] >= 100]
    pc = d["c"].shift(1)
    tr = np.maximum(d["h"] - d["l"], np.maximum((d["h"] - pc).abs(), (d["l"] - pc).abs()))
    atr = tr.rolling(14).mean()
    alle = pd.DatetimeIndex(sorted(p["tag"].unique()))
    pos = atr.index.searchsorted(alle, side="left") - 1
    vals = np.where(pos >= 0, atr.to_numpy()[np.clip(pos, 0, None)], np.nan)
    return pd.Series(vals, index=alle)


def simuliere(p: pd.DataFrame, atr: pd.Series, spread: float, stunden: list, variante: str) -> list[dict]:
    von, bis = float(stunden[0]), float(stunden[1])
    std = p.index.hour + p.index.minute / 60.0
    in_zeit = (std >= von) & (std < bis)
    einstieg_ok = in_zeit & (std < bis - 1.0)
    trades = []
    for tag, idx in p.groupby("tag").indices.items():
        a = atr.get(tag, np.nan)
        if not np.isfinite(a) or a <= 0:
            continue
        sub = p.iloc[idx]
        erst = sub.iloc[0]
        o_t = float(erst["o_tag"])
        hoeher = [o_t > float(erst[c]) for c in ("o_jahr", "o_quartal", "o_monat")]
        tiefer = [o_t < float(erst[c]) for c in ("o_jahr", "o_quartal", "o_monat")]
        s = 1 if all(hoeher) else (-1 if all(tiefer) else 0)
        if s == 0:
            continue
        z, e = in_zeit[idx], einstieg_ok[idx]
        if not z.any():
            continue
        hi, lo, cl = sub["high"].to_numpy(float), sub["low"].to_numpy(float), sub["close"].to_numpy(float)
        n = len(sub)
        if variante == "woche":
            linie = float(erst["o_woche"])
            if not (s * (o_t - linie) > 0):
                continue
            aktiv_ab = 0
        else:
            linie = o_t
            weg = (hi >= o_t + 0.25 * a) if s > 0 else (lo <= o_t - 0.25 * a)
            arm = np.flatnonzero(weg & z)
            if not len(arm):
                continue
            aktiv_ab = arm[0] + 1
        treffer = (lo <= linie - spread) if s > 0 else (hi >= linie)
        kand = np.flatnonzero(treffer & e & (np.arange(n) >= aktiv_ab))
        if not len(kand):
            continue
        i = kand[0]
        ende = np.flatnonzero(z)[-1]
        if ende < i:
            continue
        stop, ziel = linie - s * a, linie + 2 * s * a
        r, grund = None, "schluss"
        for j in range(i, ende + 1):
            if s > 0:
                if lo[j] <= stop:
                    r, grund = -1.0, "stop"
                    break
                if j > i and hi[j] >= ziel:
                    r, grund = 2.0, "ziel"
                    break
            else:
                if hi[j] + spread >= stop:
                    r, grund = -1.0, "stop"
                    break
                if j > i and lo[j] + spread <= ziel:
                    r, grund = 2.0, "ziel"
                    break
        if r is None:
            r = (cl[ende] - linie) / a if s > 0 else (linie - (cl[ende] + spread)) / a
        trades.append({"zeit": sub.index[i], "seite": "long" if s > 0 else "short", "r": float(r), "grund": grund})
    return trades


def auswerten(trades: list[dict], von: str, bis: str) -> dict:
    t = [x for x in trades if pd.Timestamp(von) <= x["zeit"] < pd.Timestamp(bis) + pd.Timedelta(days=1)]
    r = np.array([x["r"] for x in t], float)
    k = kennzahlen(r)
    wochen = (pd.Timestamp(bis) - pd.Timestamp(von)).days / 7.0
    k["je_woche"] = runde(len(r) / wochen, 2)
    cum = np.cumsum(r) if len(r) else np.zeros(1)
    k["rueckgang_r"] = runde((np.maximum.accumulate(np.concatenate([[0.0], cum])) - np.concatenate([[0.0], cum])).max())
    for seite in ("long", "short"):
        rs = np.array([x["r"] for x in t if x["seite"] == seite], float)
        k[seite] = {"trades": int(len(rs)), "pf_r": runde(pf(rs))}
    return k


def pruefe_b(k: dict) -> list[str]:
    z, g = k["zeitraum"], []
    if z["trades"] < 40:
        g.append(f"nur {z['trades']} Trades")
    if z["pf_r"] is None or z["pf_r"] < 1.2:
        g.append(f"PF {z['pf_r']} unter 1,2")
    if k["robust"]["pf_r"] is None or k["robust"]["pf_r"] < 1.0:
        g.append(f"robust {k['robust']['pf_r']} unter 1,0")
    for name in ("haelfte_1", "haelfte_2", "jahr_2026", "kontrolle"):
        if k[name]["pf_r"] is None or k[name]["pf_r"] <= 1.0:
            g.append(f"{name} {k[name]['pf_r']} nicht über 1,0")
    return g


def teil_b(ordner: pathlib.Path) -> dict:
    basis = yaml.safe_load((HERE / "VORAB.yaml").read_text(encoding="utf-8"))["runde_1"]["maerkte"]
    maerkte = {m["symbol"]: m for m in basis}
    maerkte.update(EXTRA)
    out = {}
    for sym, m in maerkte.items():
        p = perioden(lade(ordner, sym))
        atr = tages_atr(p)
        out[sym] = {}
        for v in ("woche", "tag"):
            tr = simuliere(p, atr, float(m["spread"]), m["stunden"], v)
            rob = simuliere(p, atr, 1.5 * float(m["spread"]), m["stunden"], v)
            k = {"zeitraum": auswerten(tr, *ZEITRAUM), "robust": auswerten(rob, *ZEITRAUM),
                 "haelfte_1": auswerten(tr, *HAELFTEN[0]), "haelfte_2": auswerten(tr, *HAELFTEN[1]),
                 "jahr_2026": auswerten(tr, *JAHR_2026), "kontrolle": auswerten(tr, *KONTROLLE)}
            k["gruende"] = pruefe_b(k)
            k["bestanden"] = not k["gruende"]
            out[sym][v] = k
        print(sym, {v: (out[sym][v]["zeitraum"]["trades"], out[sym][v]["zeitraum"]["pf_r"]) for v in out[sym]},
              flush=True)
    return out


# ---------------------------------------------------------------------------------------------------------------------

def zahl(x, n=2) -> str:
    return "-" if x is None else f"{x:.{n}f}".replace(".", ",")


def bericht(erg: dict) -> str:
    a, b = erg["teil_a"], erg["teil_b"]
    z = ["# Opens aus Kirons Strategie-Video: Ergebnis", "",
         f"Regel: `suche/VORAB_opens.yaml` (sha256 `{erg['vorab_sha256'][:12]}…`), Code `suche/opens.py`.", "",
         "## Teil A: Laufende Bots nur in Richtung eines Opens", "",
         "Trades der Bewertung 2025 bis 10/2026. PF = Gewinnfaktor in R. p = Anteil zufälliger gleich großer Auswahlen, "
         "die mindestens so gut sind.", "",
         "| Bot | Original | Jahr | Quartal | Monat | Woche | Alle vier | Bestanden |", "|---|---|---|---|---|---|---|---|"]
    for s, x in a.items():
        o = x["original"]
        zellen = [f"{o['trades']} Tr., PF {zahl(o['pf_r'])}, {zahl(o['summe_r'], 1)} R"]
        for f in ("jahr", "quartal", "monat", "woche", "alle"):
            k = x["filter"][f]
            zellen.append(f"{k['trades']} Tr., PF {zahl(k['pf_r'])}, {zahl(k['summe_r'], 1)} R, p {zahl(k['p_zufall'], 3)}")
        z.append(f"| {s} | " + " | ".join(zellen) + f" | {x['gewaehlt'] or 'keiner'} |")
    z += ["", "## Teil B: Rücklauf zum Wochen- bzw. Tages-Open in Richtung der großen Opens", "",
          "Zeitraum 11/2024 bis 10/2026, Kontrolle 11/2022 bis 10/2024.", "",
          "| Markt | Variante | Trades | je Woche | PF | robust | Hälfte 1 | Hälfte 2 | 2026 | Kontrolle | Summe R | Bestanden |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for sym, vs in b.items():
        for v, k in vs.items():
            zr = k["zeitraum"]
            z.append(f"| {sym} | {v} | {zr['trades']} | {zahl(zr['je_woche'])} | {zahl(zr['pf_r'])} | "
                     f"{zahl(k['robust']['pf_r'])} | {zahl(k['haelfte_1']['pf_r'])} | {zahl(k['haelfte_2']['pf_r'])} | "
                     f"{zahl(k['jahr_2026']['pf_r'])} | {zahl(k['kontrolle']['pf_r'])} | {zahl(zr['summe_r'], 1)} | "
                     f"{'ja' if k['bestanden'] else 'nein'} |")
    z += ["", "## Urteil", "", erg["urteil"], ""]
    return "\n".join(z)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    cfg = check_vorab()
    ordner, trades_csv = pathlib.Path(argv[0]), pathlib.Path(argv[1])
    a = teil_a(cfg, ordner, trades_csv)
    b = teil_b(ordner)
    a_ok = {s: x["gewaehlt"] for s, x in a.items() if x["gewaehlt"]}
    b_ok = sorted(((sym, v, k["zeitraum"]["pf_r"], k["zeitraum"]["trades"]) for sym, vs in b.items()
                   for v, k in vs.items() if k["bestanden"]), key=lambda x: (x[2], x[3]), reverse=True)[:2]
    teile = []
    teile.append("Teil A: " + (", ".join(f"{s} mit Filter {f}" for s, f in a_ok.items()) + " bestanden, "
                               "Zwilling-Vorschlag im Schatten" if a_ok else "kein Filter bestanden, alle Bots bleiben wie sie sind"))
    teile.append("Teil B: " + (", ".join(f"{s} {v} (PF {zahl(pf_)}, {n} Trades)" for s, v, pf_, n in b_ok)
                               + " bestanden, Vorschlag Schatten-Vorwärtstest" if b_ok else "keine Regel auf keinem Markt bestanden"))
    urteil = ". ".join(teile) + ". Keine Nachbesserung nach dem Ergebnis."
    erg = {"vorab_sha256": sha256_text(VORAB.read_text(encoding="utf-8")), "urteil": urteil,
           "teil_a": a, "teil_b": b, "teil_b_vorschlag": [list(x) for x in b_ok]}
    (HERE / "ergebnis_opens.json").write_text(json.dumps(erg, ensure_ascii=False, indent=1, default=str) + "\n",
                                              encoding="utf-8")
    (HERE / "ergebnis_opens.md").write_text(bericht(erg), encoding="utf-8")
    journal_add(f"Opens gerechnet (suche/opens.py nach suche/VORAB_opens.yaml, Ergebnis suche/ergebnis_opens.md): {urteil}")
    print(urteil)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
