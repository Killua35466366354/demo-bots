"""Gleiche Bewertung aller Demo-Strategien über 2025 und 2026 (suche/VORAB_bewertung.yaml). Nur rechnen, keine Order.

Kirons Wunsch vom 04.11.2026: alle Strategien gleich auswerten, mit einem Backtest über dieses und letztes Jahr, und erst
dann wählen, welche Bots auf die 9 Capital.com-Demokonten kommen (mehr Konten gibt Capital.com nicht).

    python -m suche.bewertung --festlegen "Grund"     # Prüfsumme der VORAB ins Journal, BEVOR gerechnet wird
    python -m suche.bewertung <pine_kerzen> <tag_kerzen> <r6_csv> <r7_csv> <out_dir> [<USDJPY_5min.csv.gz>]
    python -m suche.bewertung --euro <out_dir>          # Euro mit Hebelgrenze nachtragen (trades.csv, portfolio.json)

<pine_kerzen>: Ordner mit <EPIC>_MINUTE_15.csv.gz (kerzen.yml modus bewertung). <tag_kerzen>: Ordner mit <EPIC>_DAY.csv.gz
(kerzen.yml modus tag). <r6_csv>, <r7_csv>: Trade-Listen der Runde-6- und Runde-7-Threads (siehe VORAB).

Ergebnis: <out_dir>/bewertung.json (alle Kennzahlen, Monats-Tabellen, Rangliste, Wahl der Konten), <out_dir>/trades.csv
(jeder Trade jeder Strategie im Fenster).
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd
import yaml

from suche.runde1 import journal_add, journal_lines, last_value
from suche.runde3 import SIDES, fuehrung, prepare, read_capital, resample, run_r, sha256_text, span

HERE = pathlib.Path(__file__).resolve().parent
ROOT_J = HERE.parent / "journal"
VORAB = HERE / "VORAB_bewertung.yaml"
KEY = "VORAB_bewertung sha256 "
EUR_JE_R = 10.0             # 1 % von 1.000 Euro Risiko je Trade
# Korrektur 04.11.2026 (Hinweis aus dem Stop-Test, Projektdateien strategie-suche/stopwahl/): Mit 1.000 € kann eine
# Position nicht beliebig groß sein. Hebel für Privatkunden (Devisen 30, Indizes 20, Gold 20, andere Rohstoffe 10,
# Aktien 5), Margin höchstens die Hälfte des Kontos wie in suche/r6_bots.py. Und die Trend-Rücksetzer (Runde 5) rechnen
# R in ATR, ihr Stop liegt aber bei 3 x ATR: 1 % Risiko heißt dort 10 € bis zum Stop, also R / 3.
KONTO_EUR, MARGIN_ANTEIL = 1000.0, 0.5
HEBEL = {"FX": 30, "INDICES": 20, "GOLD": 20, "COMMODITIES": 10, "SHARES": 5}


def check_vorab() -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("suche/VORAB_bewertung.yaml steht so nicht im Journal. Erst --festlegen \"Grund\" und committen.")
    return yaml.safe_load(text)["bewertung"]


# ---------- Kennzahlen (für alle Strategien gleich) ----------

def pf(x) -> float | None:
    x = np.asarray([v for v in x if v is not None and np.isfinite(v)], float)
    if not len(x):
        return None
    loss = -x[x < 0].sum()
    return round(float(x[x > 0].sum() / loss), 3) if loss > 0 else 99.0


def markt_art(spec: dict) -> str:
    g = spec.get("gruppe")
    if g == "r6":
        return "FX"
    if g in ("r5", "r7"):
        return "INDICES"
    return "GOLD" if spec.get("epic") == "GOLD" else (spec.get("typ") or "INDICES")


def r_je_stop(spec: dict) -> float:
    """Wie viele R der Datei ein Risiko bis zum Stop sind (Trend-Rücksetzer: R in ATR, Stop 3 x ATR)."""
    if spec.get("gruppe") != "r5":
        return 1.0
    from suche import runde5 as r5
    return float(r5.check_vorab()["strategien"]["trend_ruecksetzer"]["parameter"]["stop_atr"])


def euro(pct, r, art: str, je_stop: float = 1.0) -> float | None:
    """Euro eines Trades mit 1 % Risiko (10 € bis zum Stop) auf 1.000 €, die Position höchstens so groß, wie die halbe
    Margin beim Privatkunden-Hebel erlaubt."""
    if r is None or pct is None or not np.isfinite(r):
        return None
    r_stop = float(r) / je_stop
    if r_stop == 0 or pct == 0:
        return round(r_stop * EUR_JE_R, 2)
    stop_pct = abs(float(pct) / r_stop)                       # Stop-Abstand in Prozent vom Kurs
    gross = min(EUR_JE_R * 100 / stop_pct, MARGIN_ANTEIL * KONTO_EUR * HEBEL.get(art, 10))
    return round(gross * float(pct) / 100, 2)


def kennzahlen(rows: list[dict]) -> dict:
    """rows: {einstieg (Zeit), pct, r (oder None)}. Gewinnfaktor auf pct, R nur wo es einen Stop gibt."""
    if not rows:
        return {"trades": 0, "pf": None, "summe_pct": 0.0, "treffer_pct": None, "pf_r": None, "summe_r": None,
                "max_rueckgang_pct": 0.0}
    pct = np.array([t["pct"] for t in rows], float)
    rs = [t.get("r") for t in rows]
    has_r = all(r is not None and np.isfinite(r) for r in rs)
    cum = np.r_[0.0, np.cumsum(pct)]
    cr = np.r_[0.0, np.cumsum(rs)] if has_r else None
    dd_r = float((np.maximum.accumulate(cr) - cr).max()) if has_r else None
    eur = [t.get("eur") for t in rows]
    has_eur = all(e is not None and np.isfinite(e) for e in eur)
    ce = np.r_[0.0, np.cumsum(eur)] if has_eur else None
    return {"trades": int(len(pct)), "pf": pf(pct), "summe_pct": round(float(pct.sum()), 2),
            "mittel_pct": round(float(pct.mean()), 4), "treffer_pct": round(100 * float((pct > 0).mean()), 1),
            "pf_r": pf(rs) if has_r else None, "summe_r": round(float(np.sum(rs)), 1) if has_r else None,
            "max_rueckgang_pct": round(float((np.maximum.accumulate(cum) - cum).max()), 2),
            "max_rueckgang_r": None if dd_r is None else round(dd_r, 1),
            # Kirons Frage vom 04.11.2026: "wie viel würden sie mit 1000 Euro verdienen?" So wie die Bots die Größe
            # wählen: 1 % Risiko je Trade (10 Euro bis zum Stop), ohne Zinseszins, mit Hebelgrenze (siehe euro()).
            # Nur Anzeige, nicht Teil der Regel.
            "eur_1000": round(float(np.sum(eur)), 0) if has_eur else (
                None if not has_r else round(float(np.sum(rs)) * EUR_JE_R, 0)),
            "eur_1000_rueckgang": round(float((np.maximum.accumulate(ce) - ce).max()), 0) if has_eur else (
                None if dd_r is None else round(dd_r * EUR_JE_R, 0))}


def monate(rows: list[dict], von: str, bis: str) -> list[dict]:
    """Monats-Tabelle: jeder Monat im Fenster, auch ohne Trade (dann 0 Trades)."""
    alle = pd.period_range(von[:7], bis[:7], freq="M").strftime("%Y-%m").tolist()
    out = []
    for mo in alle:
        sel = [t for t in rows if str(t["einstieg"])[:7] == mo]
        pct = [t["pct"] for t in sel]
        rs = [t.get("r") for t in sel]
        out.append({"monat": mo, "trades": len(sel), "summe_pct": round(float(np.sum(pct)), 2) if sel else 0.0,
                    "gewinner": int(sum(p > 0 for p in pct)),
                    "summe_r": round(float(np.sum(rs)), 2) if sel and all(r is not None for r in rs) else None})
    return out


def pruefe(k: dict, jahre: dict, regel: dict) -> dict:
    j = regel["je_jahr"]
    tests = {"trades": k["trades"] >= regel["min_trades"], "pf": (k["pf"] or 0) >= regel["min_pf"]}
    for y, v in jahre.items():
        tests[f"jahr_{y}"] = v["trades"] >= j["min_trades"] and (v["pf"] or 0) > j["min_pf"]
    return {"tests": tests, "bestanden": all(tests.values())}


# ---------- Trades je Gruppe ----------

def pine_trades(spec: dict, ordner: pathlib.Path, r3: dict, von: str, bis: str) -> list[dict]:
    """Kirons Pine C/B mit der Führung der Logik, genau der Code der Runde 3 und der Demo-Bots."""
    from gold.v2 import termine
    bars15, spread15 = read_capital(ordner / f"{spec['epic']}_MINUTE_15.csv.gz")
    hourly, _ = resample(bars15, spread15, "60min")
    bars, spread = resample(bars15, spread15, spec["zeitrahmen"])
    P = prepare(bars, spread, hourly, spec["zeitrahmen"], termine.load()["utc"], r3["logiken"]["gold2"]["news"])
    s = span(bars.index, (von, bis + " 23:59"))
    use_l, use_s = SIDES[spec["seiten"]]
    el, es = (x[s] for x in P.entries[spec["logik"]])
    swap = r3["kosten"]["swap_pct_jahr"].get(spec["typ"], 6.0)
    tr, r = run_r(P, s, el & use_l, es & use_s, fuehrung(r3["logiken"][spec["logik"]]), swap)
    if not len(tr):
        return []
    nights = (pd.to_datetime(tr["exit_time"]).dt.normalize() - pd.to_datetime(tr["entry_time"]).dt.normalize()).dt.days
    swap_px = tr["entry_px"] * swap / 100 / 365 * nights
    pct = ((tr["pnl_eur"] - swap_px) / tr["entry_px"] * 100).to_numpy(float)
    return [{"einstieg": str(row.entry_time), "ausstieg": str(row.exit_time), "richtung": row.side,
             "pct": round(float(p), 4), "r": round(float(rr), 3), "grund": row.reason}
            for row, p, rr in zip(tr.itertuples(), pct, r)]


R6_SCHATTEN = {"r6-vortag-eurusd": ("vortag_stop_oco", "EURUSD"), "r6-vortag-gbpusd": ("vortag_stop_oco", "GBPUSD")}


def r6_trades(spec: dict, df: pd.DataFrame) -> list[dict]:
    if spec["id"] in R6_SCHATTEN:
        strat, markt = R6_SCHATTEN[spec["id"]]
        sel = df[(df["strategie"] == strat) & (df["markt"] == markt)]
    else:
        sel = df[df["bot"] == spec["id"]]
    out = []
    for row in sel.itertuples():
        r = getattr(row, "R")
        out.append({"einstieg": str(row.einstieg_kerze_utc), "ausstieg": None,
                    "richtung": "long" if row.richtung > 0 else "short", "pct": round(float(row.pct), 4),
                    "r": None if pd.isna(r) else round(float(r), 3), "grund": row.grund})
    return out


def noise_r(rows: list[dict], usdjpy_5min: pathlib.Path) -> list[dict]:
    """R für Noise USD/JPY: im Backtest ohne Stop, der Bot legt beim Broker einen Notstop von 2 x Tages-ATR(14) und
    wählt die Größe nach 1 % Risiko bis dorthin (suche/r6_bots.py NOTSTOP_ATR). Also R = pct / (2 x ATR14 in % vom
    Kurs), ATR wie runde6/r6_regeln.tageswerte (Handelstag bis 17 Uhr New York, Tage vor dem Einstieg)."""
    from suche import r6_regeln as rg
    m5 = pd.read_csv(usdjpy_5min, index_col=0, parse_dates=True)
    h = m5.resample("60min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    lab = (rg.ortszeit(h.index, rg.NY) + pd.Timedelta(hours=7)).normalize()
    g = h.groupby(lab)
    d = pd.DataFrame({"h": g["high"].max(), "l": g["low"].min(), "c": g["close"].last(), "n": g["close"].size()})
    d = d[d["n"] >= 5]
    pc = d["c"].shift(1)
    tr = np.maximum(d["h"] - d["l"], np.maximum((d["h"] - pc).abs(), (d["l"] - pc).abs()))
    risk = (2.0 * tr.rolling(14).mean() / d["c"] * 100).shift(1)      # bis zum Vortag, in % vom Kurs
    out = []
    for t in rows:
        tag = rg.handelstag_ny17(pd.Timestamp(t["einstieg"]))
        rp = risk.asof(tag) if len(risk) else np.nan
        out.append({**t, "r": None if not rp or pd.isna(rp) else round(float(t["pct"]) / float(rp), 3)})
    return out


def r7_trades(df: pd.DataFrame) -> list[dict]:
    return [{"einstieg": str(row.einstieg_utc), "ausstieg": str(row.ausstieg_utc), "richtung": row.richtung,
             "pct": round(float(row.ergebnis_pct), 4), "r": round(float(row.r), 3), "grund": row.grund}
            for row in df.itertuples()]


def r5_trades(spec: dict, ordner: pathlib.Path) -> list[dict]:
    """Trend-Rücksetzer genau wie die Gegenprobe Runde 5c (Capital.com-Tageskerzen, gleiche Kosten)."""
    from suche import runde5 as r5
    from suche import runde5c
    cfg5 = r5.check_vorab()
    cfg = runde5c.check_vorab()
    st = cfg5["strategien"]["trend_ruecksetzer"]
    job = runde5c.markt(spec["epic"], ordner, cfg5, st, cfg)
    return [{"einstieg": t["datum"], "ausstieg": str(np.busday_offset(np.datetime64(t["datum"]), int(t.get("tage") or 0),
                                                                     roll="forward")),
             "richtung": "long" if t["d"] > 0 else "short",
             "pct": round(float(t["pct"]), 4), "r": round(float(t["r"]), 3), "grund": t["grund"]}
            for t in job["trades"]]


# ---------- Wahl der Konten ----------

def waehle(rangliste: list[dict], cfg: dict, belegung: dict[str, str]) -> dict:
    """belegung: Konto-Name -> Bot-ID heute. Gewählt: die besten bestandenen ohne den Gold-Bot (der bleibt auf dem
    Hauptkonto). Wer gewählt ist und ein Konto hat, behält es; freie Konten gehen der Reihe nach an die übrigen."""
    k = cfg["konten"]
    gewaehlt = [s["id"] for s in rangliste if s["bestanden"] and s["id"] != k["hauptkonto"]][:k["anzahl"]]
    neu = dict(belegung)
    frei = [konto for konto, bot in belegung.items() if bot not in gewaehlt]
    ohne = [b for b in gewaehlt if b not in belegung.values()]
    wechsel = []
    for bot in ohne:
        if not frei:
            break
        konto = frei.pop(0)
        wechsel.append({"konto": konto, "vorher": belegung[konto], "nachher": bot})
        neu[konto] = bot
    return {"gewaehlt": gewaehlt, "belegung": neu, "wechsel": wechsel,
            "bleiben_bis_testende": [{"konto": c, "bot": belegung[c]} for c in frei]}


# ---------- Lauf ----------

def run(pine: pathlib.Path, tag: pathlib.Path, r6_csv: pathlib.Path, r7_csv: pathlib.Path, out: pathlib.Path,
        belegung: dict[str, str] | None = None, usdjpy_5min: pathlib.Path | None = None) -> dict:
    cfg = check_vorab()
    r3 = yaml.safe_load((HERE / "VORAB_runde3.yaml").read_text(encoding="utf-8"))["runde_3"]
    von, bis = cfg["fenster"]
    r6 = pd.read_csv(r6_csv)
    r7 = pd.read_csv(r7_csv)
    alle, rows_all = [], []
    for spec in cfg["strategien"]:
        g = spec["gruppe"]
        try:
            if g == "pine":
                rows = pine_trades(spec, pine, r3, von, bis)
            elif g == "r6":
                rows = r6_trades(spec, r6)
                if spec["id"] == "r6-noise-usdjpy" and usdjpy_5min:
                    rows = noise_r(rows, usdjpy_5min)
            elif g == "r7":
                rows = r7_trades(r7)
            else:
                rows = r5_trades(spec, tag)
            fehler = None
        except Exception as err:          # noqa: BLE001 - eine Strategie darf die anderen nicht aufhalten
            rows, fehler = [], f"{type(err).__name__}: {err}"
        rows = sorted((t for t in rows if von <= str(t["einstieg"])[:10] <= bis), key=lambda t: str(t["einstieg"]))
        art, je_stop = markt_art(spec), r_je_stop(spec)
        for t in rows:
            t["eur"] = euro(t.get("pct"), t.get("r"), art, je_stop)
        k = kennzahlen(rows)
        jahre = {y: kennzahlen([t for t in rows if str(t["einstieg"])[:4] == y]) for y in cfg["jahre"]}
        p = pruefe(k, jahre, cfg["regel"])
        alle.append({**{x: spec.get(x) for x in ("id", "name", "gruppe", "epic", "markt", "zeitrahmen", "logik",
                                                   "seiten", "schatten") if spec.get(x) is not None},
                     **k, "jahre": jahre, **p, "monate": monate(rows, von, bis), "fehler": fehler})
        rows_all += [{"strategie": spec["id"], **t} for t in rows]
        print(spec["id"], k["trades"], k["pf"], p["bestanden"], fehler or "", flush=True)
    rang = sorted(alle, key=lambda s: (not s["bestanden"], -(s["pf"] or 0), -s["trades"]))
    for i, s in enumerate(rang, 1):
        s["rang"] = i
    res = {"format": 1, "fenster": cfg["fenster"], "regel": cfg["regel"], "mass": cfg["mass"],
           "ehrlich": cfg["ehrlich"], "strategien": rang}
    if belegung:
        res["wahl"] = waehle(rang, cfg, belegung)
    out.mkdir(parents=True, exist_ok=True)
    (out / "bewertung.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    pd.DataFrame(rows_all).to_csv(out / "trades.csv", index=False)
    journal_add("Bewertung 2025-2026 gerechnet: " + json.dumps(
        {s["id"]: [s["trades"], s["pf"], s["bestanden"]] for s in rang}, ensure_ascii=False))
    return res


# Bot-IDs, unter denen die Strategien in journal/konten.json und in ihren Journal-Dateien stehen (wo anders als hier).
BOT_ID = {"us500": "us500-ruecksetzer"}


def _jahr(k: dict) -> dict:
    return {x: k.get(x) for x in ("trades", "pf", "summe_pct", "summe_r", "treffer_pct", "eur_1000")}


def portfolio(res: dict, stand: str, warum: dict[str, str] | None = None) -> dict:
    """journal/portfolio.json für das Cockpit (Tabelle "Demo-Portfolio"): Rangliste, Konto und Rolle je Strategie,
    Kennzahlen je Jahr und die Monats-Tabelle. rolle: aktiv (hat ein Konto), wartet (gewählt, das Konto wird frei, sobald
    der Vorgänger seine Position geschlossen hat), abgeloest (Konto abgegeben), nicht_gewaehlt."""
    wahl = res.get("wahl") or {}
    jetzt = {bot: konto for konto, bot in (wahl.get("belegung") or {}).items()}
    vorher = {w["vorher"]: w for w in wahl.get("wechsel") or []}
    nachher = {w["nachher"]: w for w in wahl.get("wechsel") or []}
    namen = {s["id"]: s["name"] for s in res["strategien"]}
    bots = []
    for s in res["strategien"]:
        sid = s["id"]
        if sid == "gold-cb":
            konto, rolle = "Account (Hauptkonto)", "aktiv"
        elif sid in vorher:
            konto, rolle = None, "abgeloest"
        elif sid in nachher:
            konto, rolle = nachher[sid]["konto"], "wartet"
        elif sid in jetzt:
            konto, rolle = jetzt[sid], "aktiv"
        else:
            konto, rolle = None, "nicht_gewaehlt"
        bots.append({"rang": s["rang"], "id": BOT_ID.get(sid, sid), "name": s["name"],
                     "markt": s.get("epic") or s.get("markt"), "zeitrahmen": s.get("zeitrahmen"), "konto": konto,
                     "rolle": rolle, "ersetzt": namen.get(nachher[sid]["vorher"]) if sid in nachher else None,
                     "ersetzt_durch": namen.get(vorher[sid]["nachher"]) if sid in vorher else None,
                     "bestanden": s["bestanden"], "tests": s["tests"], "trades": s["trades"], "pf": s["pf"],
                     "summe_pct": s["summe_pct"], "summe_r": s.get("summe_r"), "treffer_pct": s["treffer_pct"],
                     "max_rueckgang_pct": s["max_rueckgang_pct"], "eur_1000": s.get("eur_1000"),
                     "eur_1000_rueckgang": s.get("eur_1000_rueckgang"),
                     "j2025": _jahr(s["jahre"]["2025"]), "j2026": _jahr(s["jahre"]["2026"]), "zufall_pct": None,
                     "warum": (warum or {}).get(sid),
                     "monate": [{k: m[k] for k in ("monat", "trades", "summe_pct", "gewinner")} for m in s["monate"]]})
    return {"format": 1, "stand_utc": stand, "zeitraum": " bis ".join(res["fenster"]),
            "regel": "Alle 17 Strategien gleich gerechnet: Einstiege 01.01.2025 bis 30.10.2026, Ergebnis in Prozent vom "
                     "Kurs nach Spread und Übernachtkosten. Bestanden: mindestens 20 Trades, Gewinnfaktor ab 1,2, 2025 "
                     "und 2026 je über 1,0 (suche/VORAB_bewertung.yaml).",
            "ehrlich": res.get("ehrlich"), "bots": bots}


# Wer heute welches Konto hat (journal/konten.json, Stand 04.11.2026 11:02 UTC), Konto-Name -> Bot-ID.
BELEGUNG = {"Account 1": "oil-brent", "Account 2": "j225", "Account 3": "us30", "Account 4": "copper",
            "Account 5": "intc", "Account 6": "gold2", "Account 7": "dax", "US500": "us500",
            "Vortag USDJPY": "r6-vortag-usdjpy"}


def euro_nachtragen(out: pathlib.Path, portfolio_json: pathlib.Path) -> dict:
    """Euro mit Hebelgrenze und Stop-Einheit in eine fertige Bewertung nachtragen (trades.csv bekommt "eur",
    bewertung.json und journal/portfolio.json die Euro-Felder), ohne die Strategien neu zu rechnen. Gewinnfaktor,
    Bestehen und Rangliste bleiben, wie sie sind."""
    cfg = yaml.safe_load(VORAB.read_text(encoding="utf-8"))["bewertung"]
    specs = {s["id"]: s for s in cfg["strategien"]}
    tr = pd.read_csv(out / "trades.csv")
    tr["eur"] = [euro(p, r, markt_art(specs[i]), r_je_stop(specs[i])) for i, p, r in zip(tr.strategie, tr.pct, tr.r)]
    tr.to_csv(out / "trades.csv", index=False)
    res = json.loads((out / "bewertung.json").read_text(encoding="utf-8"))
    neu = {}
    for s in res["strategien"]:
        g = tr[tr.strategie == s["id"]]
        rows = [{"pct": p, "r": r, "eur": e} for p, r, e in zip(g.pct, g.r, g.eur)]
        k = kennzahlen(rows)
        s["eur_1000"], s["eur_1000_rueckgang"] = k["eur_1000"], k["eur_1000_rueckgang"]
        for y, v in (s.get("jahre") or {}).items():
            v["eur_1000"] = kennzahlen([x for x, e in zip(rows, g.einstieg) if str(e)[:4] == y])["eur_1000"]
        neu[BOT_ID.get(s["id"], s["id"])] = s
    (out / "bewertung.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    pf = json.loads(portfolio_json.read_text(encoding="utf-8"))
    for b in pf["bots"]:
        s = neu.get(b["id"])
        if s:
            b["eur_1000"], b["eur_1000_rueckgang"] = s["eur_1000"], s["eur_1000_rueckgang"]
            for y in ("2025", "2026"):
                if isinstance(b.get(f"j{y}"), dict):
                    b[f"j{y}"]["eur_1000"] = s["jahre"][y]["eur_1000"]
    portfolio_json.write_text(json.dumps(pf, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {i: s["eur_1000"] for i, s in neu.items()}


def main(argv: list[str]) -> int:
    if argv[:1] == ["--euro"]:
        print(json.dumps(euro_nachtragen(pathlib.Path(argv[1]), ROOT_J / "portfolio.json"), ensure_ascii=False))
        return 0
    if argv[:1] == ["--festlegen"]:
        text = VORAB.read_text(encoding="utf-8")
        journal_add(f"Bewertung aller Demo-Strategien festgelegt, Grund: {argv[1]}. {KEY}{sha256_text(text)}")
        print("Im Journal:", sha256_text(text))
        return 0
    pine, tag, r6_csv, r7_csv, out = (pathlib.Path(a) for a in argv[:5])
    res = run(pine, tag, r6_csv, r7_csv, out, BELEGUNG, pathlib.Path(argv[5]) if len(argv) > 5 else None)
    print(json.dumps(res.get("wahl"), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
