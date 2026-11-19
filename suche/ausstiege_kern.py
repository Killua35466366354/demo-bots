"""Andere Ausstiege für drei laufende Demo-Bots nach Kirons Notizen Nr. 9, 11 und 13 (suche/VORAB_ausstiege_kern.yaml).

Gleiche Einstiege wie der Bot, nur der Ausstieg ändert sich, Vergleich Trade für Trade mit dem Original. Nur Backtest,
ändert an keinem Bot etwas. Nur Capital.com-DEMO, nie echtes Geld.

    python -m suche.ausstiege_kern --festlegen "Grund"
    python -m suche.ausstiege_kern <out_dir>
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd
import yaml

from suche import opens as op
from suche import r7_nasdaq_bot as r7
from suche import runde5 as r5
from suche import scalping as sc
from suche import scalping2 as s2
from suche import scalping_opens as so
from suche.rueckblick_daten import echtes_utc
from suche.runde1 import journal_add, journal_lines, last_value

HERE = pathlib.Path(__file__).resolve().parent
VORAB = HERE / "VORAB_ausstiege_kern.yaml"
KEY = "VORAB_ausstiege_kern sha256 "
DATEN = pathlib.Path("/mnt/project-files/strategie-suche/daten")
NOISE_CSV = pathlib.Path("/mnt/project-files/strategie-suche/runde7/nasdaq_noise_long_trades_2015_bis_2026.csv")
ERGEBNIS = HERE / "ergebnis_ausstiege_kern"

R5_PARAMETER = {"trend": 200, "unter": 10, "stop_atr": 3.0, "max_tage": 5}
R5_VORLAUF = 400
US100_SPREAD = sc.SPREAD["NSXUSD"]
ROBUST = 1.5
HAUPT_AB = "2025-01-01"
LAEUFE = 20_000
SAAT = 20261119
ALPHA = 0.05
DAX_AB = "2016-01-01"
DAX_FAKTOREN = {"r13_s075_z075": (0.75, 0.75), "r13_s075_z150": (0.75, 1.5), "r13_s150_z075": (1.5, 0.75),
                "r13_s150_z150": (1.5, 1.5)}


def check_vorab() -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if last_value(journal_lines(), KEY) != r5.sha256_text(text):
        raise SystemExit("VORAB_ausstiege_kern.yaml passt nicht zur Prüfsumme im Protokoll. Erst versiegeln.")
    return yaml.safe_load(text)["ausstiege_kern"]


def lade_5min(sym: str, utc: bool) -> pd.DataFrame:
    df = pd.read_csv(DATEN / f"{sym}_5min.csv.gz", index_col=0, parse_dates=True)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    if utc:
        t = echtes_utc(df.index)
        ok = ~t.isna()
        df = df[ok]
        df.index = t[ok]
        df = df[~df.index.duplicated(keep="last")].sort_index()
    df.index.name = "utc"
    return df


def kerzen(df: pd.DataFrame, regel: str) -> pd.DataFrame:
    return df.resample(regel, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


# ---------- Nr. 9 Rücksetzer US100 ----------

def r5_ausstieg(T: r5.Tage, s: r5.Signal, a20: np.ndarray, ti: int, d: int, sp_mult: float, fin_mult: float,
                einstand: bool = False, halb: bool = False, max_tage: int = 5) -> dict:
    """Ein Trade ab dem Schluss von Tag ti. Ohne Schalter genau wie runde5.simuliere (Notstop auf den Stunden, dann zum
    Tagesschluss Signal, Gegensignal oder Zeit)."""
    n = len(T.c)
    sp = T.sp * sp_mult
    ein = T.c[ti] + (sp if d > 0 else 0.0)
    atr = a20[ti]
    stop = T.c[ti] - d * s.stop_atr * atr
    fin_satz = (T.fin_long if d > 0 else T.fin_short) * fin_mult * T.c[ti]
    stufe = ein + d * atr
    beine: list[tuple[float, float, object, str]] = []        # (Anteil, Ausstieg, Zeit, Grund)
    rest, scharf, gefuellt = 1.0, False, False
    for t in range(ti + 1, n):
        a, b = T.i0[t], T.i1[t] + 1
        for k in range(a, b):
            spk = T.hsp[k] * sp_mult
            if d > 0:
                hit, fill = T.hl[k] <= stop, min(stop, T.ho[k])
            else:
                hit, fill = T.hh[k] + spk >= stop, max(stop, T.ho[k] + spk)
            if hit:
                beine.append((rest, fill, T.ht[k] + np.timedelta64(1, "h"), "einstand" if scharf else "stop"))
                rest = 0.0
                break
            if einstand or halb:
                erreicht = T.hh[k] >= stufe if d > 0 else T.hl[k] + spk <= stufe
                if erreicht and not scharf:
                    if halb and not gefuellt:
                        beine.append((0.5, stufe, T.ht[k] + np.timedelta64(1, "h"), "halb"))
                        rest, gefuellt = 0.5, True
                    scharf = True
                    stop = max(stop, ein) if d > 0 else min(stop, ein)
        if rest == 0.0:
            te = t
            break
        raus = (d > 0 and (s.xl[t] or s.es[t])) or (d < 0 and (s.xs[t] or s.el[t]))
        if t - ti >= max_tage:
            raus = True
        if raus or t == n - 1:
            beine.append((rest, T.c[t] + (sp if d < 0 else 0.0), T.t[t], "signal" if raus else "datenende"))
            te = t
            break
    r = 0.0
    for anteil, aus, t_aus, _ in beine:
        pnl = (aus - ein) * d - fin_satz * r5.naechte(T.t[ti], t_aus)
        r += anteil * pnl / atr
    return {"datum": str(T.datum[ti]), "ti": ti, "te": te, "d": d, "r": float(r), "grund": beine[-1][3]}


def rechne_us100() -> dict:
    cfg5 = r5.check_vorab()
    h1 = kerzen(lade_5min("NSXUSD", utc=True), "1h")
    T = r5.baue_tage("NSXUSD", h1, None, cfg5["kosten"])
    T.sp = US100_SPREAD
    T.hsp = np.full(len(T.hsp), US100_SPREAD)
    s = r5.sig_trend_ruecksetzer(T, R5_PARAMETER, {})
    start = int(np.searchsorted(T.datum, np.datetime64(T.datum[0]) + np.timedelta64(R5_VORLAUF, "D")))
    a20 = r5.atr(T, 20)
    out = {"bot": "r5-ruecksetzer-us100", "daten_von": str(T.datum[0]), "daten_bis": str(T.datum[-1])}
    for name, sp_mult in (("normal", 1.0), ("robust", ROBUST)):
        orig = r5.simuliere(T, s, start, sp_mult=sp_mult, fin_mult=sp_mult)
        nach = [r5_ausstieg(T, s, a20, t["ti"], t["d"], sp_mult, sp_mult) for t in orig]
        abw = max((abs(a["r"] - b["r"]) for a, b in zip(orig, nach)), default=0.0)
        if abw > 1e-9:
            raise SystemExit(f"Nachrechnung Rücksetzer weicht ab ({abw}).")
        out[name] = {
            "original": nach,
            "r9a_einstand": [r5_ausstieg(T, s, a20, t["ti"], t["d"], sp_mult, sp_mult, einstand=True) for t in orig],
            "r9b_halb_und_10_tage": [r5_ausstieg(T, s, a20, t["ti"], t["d"], sp_mult, sp_mult, halb=True, max_tage=10)
                                     for t in orig],
        }
    return out


# ---------- Nr. 11 Nasdaq Noise Long ----------

def _ny_minute_utc(tag: str, minute: int) -> pd.Timestamp:
    ts = pd.Timestamp(tag) + pd.Timedelta(minutes=minute)
    return ts.tz_localize(r7.TZ).tz_convert("UTC").tz_localize(None)


def noise_ausstieg(b: pd.DataFrame, row, tage: int, einstand: bool, kosten_mult: float) -> dict | None:
    t0 = pd.Timestamp(row.einstieg_utc)
    i0 = int(b.index.searchsorted(t0))
    if i0 >= len(b) or b.index[i0] != t0:
        return None
    aus_tag = r7.handelstage_nach(row.tag, tage)
    t_aus = _ny_minute_utc(aus_tag, r7.aus_minute(aus_tag))
    ie = int(b.index.searchsorted(t_aus - pd.Timedelta(minutes=15)))
    if ie >= len(b) or b.index[ie] != t_aus - pd.Timedelta(minutes=15):
        ie = int(b.index.searchsorted(t_aus)) - 1
    nacht_o = r5.naechte(np.datetime64(t0), np.datetime64(pd.Timestamp(row.ausstieg_utc)))
    je_nacht = float(row.uebernacht_pct) / nacht_o if nacht_o else 0.0
    sp_pct = 2 * (float(row.ergebnis_pct) - float(row.ergebnis_pct_kosten_1_5)) - float(row.uebernacht_pct)
    e = float(b["open"].iloc[i0])
    ein = e * (1 + sp_pct / 100)                  # bezahlter Ask
    risiko = float(row.risiko_pct_5atr)
    stop = ein * (1 - risiko / 100)
    stufe = ein * (1 + risiko / 5 / 100)
    o, h, l, c = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    aus, grund, t_ende, scharf = None, "zeit", b.index[ie] + pd.Timedelta(minutes=15), False
    for k in range(i0, ie + 1):
        if l[k] <= stop:
            aus, grund, t_ende = min(stop, o[k]), ("einstand" if scharf else "stop"), b.index[k] + pd.Timedelta(minutes=15)
            break
        if einstand and not scharf and h[k] >= stufe:
            scharf, stop = True, max(stop, ein)
    if aus is None:
        aus = c[ie]
    naechte = r5.naechte(np.datetime64(t0), np.datetime64(t_ende))
    pct = (aus / e - 1) * 100 - kosten_mult * sp_pct - kosten_mult * je_nacht * naechte
    return {"datum": row.tag, "r": float(pct / risiko), "grund": grund, "aus": str(t_ende)}


def rechne_noise() -> dict:
    liste = pd.read_csv(NOISE_CSV)
    b = kerzen(lade_5min("NSXUSD", utc=False), "15min")
    out = {"bot": "r7-nasdaq-noise-long", "trades_liste": int(len(liste))}
    nach = [noise_ausstieg(b, row, r7.HALTE_TAGE, False, 1.0) for row in liste.itertuples()]
    fehlt = sum(x is None for x in nach)
    abw = [abs(x["r"] - float(row.r)) for x, row in zip(nach, liste.itertuples()) if x]
    grund_anders = sum(1 for x, row in zip(nach, liste.itertuples()) if x and x["grund"] != row.grund)
    out["nachrechnung"] = {"fehlt": fehlt, "median_abweichung_r": round(float(np.median(abw)), 4) if abw else None,
                           "max_abweichung_r": round(float(np.max(abw)), 4) if abw else None,
                           "grund_anders": grund_anders}
    if fehlt or not abw or np.median(abw) > 0.02 or grund_anders:
        out["abgebrochen"] = True
        return out
    for name, km in (("normal", 1.0), ("robust", ROBUST)):
        out[name] = {
            "original": [noise_ausstieg(b, row, r7.HALTE_TAGE, False, km) for row in liste.itertuples()],
            "r11a_einstand": [noise_ausstieg(b, row, r7.HALTE_TAGE, True, km) for row in liste.itertuples()],
            "r11b_einstand_10_tage": [noise_ausstieg(b, row, 10, True, km) for row in liste.itertuples()],
        }
    return out


# ---------- Nr. 13 Scalper DAX ----------

def dax_trades(m: sc.Markt, sf: float, ks: float, kz: float, von: str, bis: str) -> list[dict]:
    """scalping2.eroeffnung folgen_10r, nur Stop- und Ziel-Abstand mal ks und kz. Für ks = kz = 1 dieselben Trades."""
    tz, start, schluss = s2.sitzung("GRXEUR")
    zweite = (pd.Timestamp(f"2000-01-01 {start}") + pd.Timedelta(minutes=m.minuten)).strftime("%H:%M")
    s = m.spread * sf
    out = []
    for tag in sc.werktage(von, bis, tz):
        i1 = m.kerze(s2.oz(tag, start, tz))
        i0 = m.kerze(s2.oz(tag, zweite, tz))
        if i1 < 0 or i0 != i1 + 1:
            continue
        ende = s2.oz(tag, s2.schluss_von(schluss, tag), tz)
        ie = int(np.searchsorted(m.tn, np.datetime64(ende))) - 1
        if ie <= i0 or m.t[ie] < ende - pd.Timedelta(minutes=60):
            continue
        if m.c[i1] == m.o[i1]:
            continue
        d = 1 if m.c[i1] > m.o[i1] else -1
        stop = m.l[i1] if d == 1 else m.h[i1]
        if (d == 1 and m.o[i0] <= stop) or (d == -1 and m.o[i0] + s >= stop):
            continue
        entry = m.o[i0] + s if d == 1 else m.o[i0]
        dist = abs(entry - stop)
        tr = s2.trade_v(m, i0, ie, d, "close", s, stop_abstand=ks * dist, ziel_abstand=kz * 10 * dist)
        out.append({"t": m.t[i0], "d": d, "r": float(tr["r"]) if tr else 0.0,
                    "grund": tr["grund"] if tr else "kein_trade"})
    return sc.im(out, von, bis)


def rechne_dax() -> dict:
    df5 = lade_5min("GRXEUR", utc=True)
    p = op.perioden(df5)
    m = sc.Markt("GRXEUR", s2.zu_15(df5), s2.spreads()["GRXEUR"], minuten=15)
    bis = str(df5.index[-1])
    out = {"bot": "scalp-de40", "daten_von": str(df5.index[0]), "daten_bis": bis}
    for name, sf in (("normal", 1.0), ("robust", ROBUST)):
        orig = dax_trades(m, sf, 1.0, 1.0, DAX_AB, bis)
        maske = so.mit_opens(p, orig)["alle"]
        res = {"original": [t for t, k in zip(orig, maske) if k]}
        for v, (ks, kz) in DAX_FAKTOREN.items():
            alle = dax_trades(m, sf, ks, kz, DAX_AB, bis)
            if [(t["t"], t["d"]) for t in alle] != [(t["t"], t["d"]) for t in orig]:
                raise SystemExit(f"{v}: andere Einstiege als das Original.")
            res[v] = [t for t, k in zip(alle, maske) if k]
        for lst in res.values():
            for t in lst:
                t["datum"] = str(pd.Timestamp(t.pop("t")).date())
        out[name] = res
    return out


# ---------- Auswertung ----------

def pf(r) -> float | None:
    r = np.asarray(r, float)
    g, v = r[r > 0].sum(), -r[r < 0].sum()
    return None if v == 0 else float(g / v)


def kennz(tr: list[dict]) -> dict:
    r = np.array([t["r"] for t in tr], float)
    p = pf(r)
    return {"trades": int(len(r)), "summe_r": round(float(r.sum()), 2), "pf": round(p, 3) if p is not None else None}


def gepaart_p(diff: np.ndarray, rng: np.random.Generator) -> float:
    if len(diff) == 0 or not np.any(diff):
        return 1.0
    beob = diff.mean()
    treffer = 0
    for _ in range(LAEUFE // 1000):
        z = rng.choice((-1.0, 1.0), size=(1000, len(diff)))
        treffer += int(((z * diff).mean(axis=1) >= beob - 1e-12).sum())
    return (1 + treffer) / (1 + LAEUFE)


def holm(p: dict[str, float], alpha: float = ALPHA) -> dict[str, bool]:
    ordnung = sorted(p, key=p.get)
    ok, weiter = {}, True
    for i, k in enumerate(ordnung):
        weiter = weiter and p[k] <= alpha / (len(ordnung) - i)
        ok[k] = weiter
    return ok


def auswerten(bots: dict) -> dict:
    rng = np.random.default_rng(SAAT)
    zeilen, pwerte = {}, {}
    for bot in bots.values():
        if bot.get("abgebrochen"):
            continue
        n, rob = bot["normal"], bot["robust"]
        o = n["original"]
        for v, tr in n.items():
            if v == "original":
                continue
            paare = [(a, b) for a, b in zip(o, tr) if a and b]
            diff = np.array([b["r"] - a["r"] for a, b in paare])
            ho = [a for a, _ in paare if a["datum"] >= HAUPT_AB]
            hv = [b for a, b in paare if a["datum"] >= HAUPT_AB]
            hr = [b for a, b in zip(rob["original"], rob[v]) if a and b and a["datum"] >= HAUPT_AB]
            p = gepaart_p(diff, rng)
            pwerte[v] = p
            zeilen[v] = {"bot": bot["bot"], "lang_original": kennz([a for a, _ in paare]), "lang": kennz([b for _, b in paare]),
                         "lang_mittel_unterschied_r": round(float(diff.mean()), 4) if len(diff) else None,
                         "p": round(p, 5), "haupt_original": kennz(ho), "haupt": kennz(hv), "haupt_robust": kennz(hr)}
    ok_holm = holm(pwerte)
    for v, z in zeilen.items():
        h, ho, hr = z["haupt"], z["haupt_original"], z["haupt_robust"]
        gruende = []
        if not ok_holm[v]:
            gruende.append("Holm nicht bestanden")
        if not (h["summe_r"] > ho["summe_r"]):
            gruende.append("Hauptfenster Summe nicht höher")
        if h["pf"] is None or ho["pf"] is None or h["pf"] < ho["pf"]:
            gruende.append("Hauptfenster Gewinnfaktor nicht mindestens wie das Original")
        if h["pf"] is None or h["pf"] < 1.2:
            gruende.append("Hauptfenster Gewinnfaktor unter 1,2")
        if hr["pf"] is None or hr["pf"] < 1.0:
            gruende.append("1,5-fache Kosten unter 1,0")
        z["holm"] = ok_holm[v]
        z["bestanden"] = not gruende
        z["gruende"] = gruende
    return zeilen


def bericht(zeilen: dict, bots: dict) -> str:
    def f(x, n=2):
        return "-" if x is None else f"{x:.{n}f}".replace(".", ",")
    besteht = [v for v, z in zeilen.items() if z["bestanden"]]
    zeilen_md = ["# Andere Ausstiege für US100-Rücksetzer, Nasdaq Noise Long und DAX-Scalper", "",
                 "Regeln: suche/VORAB_ausstiege_kern.yaml (versiegelt vor dem Rechnen). Gleiche Einstiege wie der Bot, "
                 "nur der Ausstieg ändert sich. Langes Fenster für den gepaarten Test (Holm über 8 Varianten), "
                 "Hauptfenster ab 01.01.2025.", "",
                 f"**Ergebnis: {len(besteht)} von {len(zeilen)} Varianten bestehen.** "
                 + ("Bestanden: " + ", ".join(besteht) + "." if besteht else "Kein Bot ändert sich."), "",
                 "| Variante | Bot | Trades lang | GF Original lang | GF Variante lang | Unterschied je Trade (R) | p | Holm "
                 "| Trades ab 2025 | GF Original ab 2025 | GF Variante ab 2025 | Summe R Original | Summe R Variante "
                 "| GF 1,5x Kosten | bestanden |",
                 "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for v, z in zeilen.items():
        zeilen_md.append(
            f"| {v} | {z['bot']} | {z['lang']['trades']} | {f(z['lang_original']['pf'])} | {f(z['lang']['pf'])} "
            f"| {f(z['lang_mittel_unterschied_r'], 3)} | {f(z['p'], 4)} | {'ja' if z['holm'] else 'nein'} "
            f"| {z['haupt']['trades']} | {f(z['haupt_original']['pf'])} | {f(z['haupt']['pf'])} "
            f"| {f(z['haupt_original']['summe_r'])} | {f(z['haupt']['summe_r'])} | {f(z['haupt_robust']['pf'])} "
            f"| {'ja' if z['bestanden'] else 'nein'} |")
    zeilen_md += ["", "## Gründe", ""]
    for v, z in zeilen.items():
        zeilen_md.append(f"- {v}: " + ("bestanden" if z["bestanden"] else "; ".join(z["gruende"])))
    nr = bots["r11_nasdaq_noise_long"].get("nachrechnung")
    zeilen_md += ["", "## Hinweise", "",
                  "- Nr. 10 (Dow) ist nicht gerechnet. Im Projekt liegen keine Dow-Kerzen.",
                  f"- Nachrechnung Noise Long gegen die Trade-Liste der Runde 7: {json.dumps(nr, ensure_ascii=False)}.",
                  "- R beim Rücksetzer ist ein ATR 20 (Notstop 3 R), beim Noise Long der Stop-Abstand von 5 ATR "
                  "(1 ATR = 0,2 R), beim DAX-Scalper der eigene Stop-Abstand der Variante.",
                  "- Rücksetzer und DAX-Scalper rechnen auf echtem UTC, darum weichen ihre Originale etwas von den "
                  "alten Tests ab (dort lag im Sommer jede Kerze 1 Stunde zu spät)."]
    return "\n".join(zeilen_md) + "\n"


def run(out: pathlib.Path) -> dict:
    check_vorab()
    out.mkdir(parents=True, exist_ok=True)
    bots = {"r9_ruecksetzer_us100": rechne_us100(), "r11_nasdaq_noise_long": rechne_noise(),
            "r13_scalper_dax": rechne_dax()}
    zeilen = auswerten(bots)
    (out / "ausstiege_kern_trades.json").write_text(json.dumps(bots, ensure_ascii=False, default=str), encoding="utf-8")
    res = {"varianten": zeilen, "nachrechnung_noise": bots["r11_nasdaq_noise_long"].get("nachrechnung")}
    ERGEBNIS.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    ERGEBNIS.with_suffix(".md").write_text(bericht(zeilen, bots), encoding="utf-8")
    kurz = {v: {"p": z["p"], "gf_ab_2025": z["haupt"]["pf"], "bestanden": z["bestanden"]} for v, z in zeilen.items()}
    journal_add("Ausstiege Kern gerechnet (suche/ergebnis_ausstiege_kern.md), einmal: "
                + json.dumps(kurz, ensure_ascii=False))
    return res


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--festlegen":
        text = VORAB.read_text(encoding="utf-8")
        journal_add(f"VORAB_ausstiege_kern sha256 {r5.sha256_text(text)}")
        return 0
    run(pathlib.Path(argv[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
