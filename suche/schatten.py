"""Schatten-Labor: alle 52 Fassungen der sechs versiegelten Runden vorwärts zählen, ohne Bot und ohne Order. Seit
20.11.2026 zählt modell_breit aus der Runde "Kirons Trade-Notizen" als 53. Fassung mit (Kirons Wahl,
suche/VORAB_schatten_modell_breit.yaml, Holm dann über 53).

Kirons Wunsch vom 20.11.2026: alle Strategien die ganze Zeit im Schatten testen. Regeln: suche/VORAB_schatten.yaml.
Jede Fassung rechnet mit genau den Funktionen, Zahlen und Kosten ihres Tests (suche/rueckblick.py und die Runden, die
darauf aufbauen), auf Kerzen, die es beim Siegel noch nicht gab. Gezählt werden nur geschlossene Trades ab dem
Zählbeginn. Das Labor meldet nur: Frühzeichen (Auskunft) und Kandidat (dann eine Karte an Kiron). Es ändert nie einen
Bot. Kein KI-Modell, nur festes Rechnen.

Aufruf:
    python -m suche.schatten --festlegen                      Prüfsumme der Regeldatei ins Protokoll
    python -m suche.schatten nachladen <Kursordner> <JJJJ-MM>   neuen HistData- und Krypto-Monat als neue Dateien holen
    python -m suche.schatten daten <Kursordner> <Arbeit>        Arbeitsordner (npz) aus Grunddateien und Monaten bauen
    python -m suche.schatten zaehlen <Arbeit>                   vorwärts zählen, schreibt suche/ergebnis_schatten.*
    python -m suche.schatten probelauf <Arbeit> <von> <bis>     dieselbe Zählung auf alten Kerzen, nur um das Programm
                                                                zu prüfen (kein Ergebnis, schreibt nichts ins Repo)

Monatsdateien: <Kursordner>/monate/<SYMBOL>_5min_<JJJJ-MM>.csv.gz (HistData), <Kursordner>/monate/DIX_<JJJJ-MM>.csv
(squeezemetrics, der neueste Stand gilt) und <Kursordner>/krypto/roh/ (Binance).
Die Grunddateien <Kursordner>/<SYMBOL>_5min.csv.gz werden nie überschrieben.
"""
from __future__ import annotations

import gzip
import json
import pathlib
import sys
import tempfile

import numpy as np
import pandas as pd
import yaml

from suche import rueckblick as rb
from suche.runde1 import journal_add, journal_lines, last_value, sha256_text

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_schatten.yaml"
KEY = "VORAB_schatten sha256 "
ERGEBNIS = ROOT / "suche" / "ergebnis_schatten"
BINANCE = "https://data.binance.vision/data/spot/monthly/klines/{s}/5m/{s}-5m-{m}.zip"
DIX_URL = "https://squeezemetrics.com/monitor/static/DIX.csv"
ZUSATZ = ROOT / "suche" / "VORAB_schatten_modell_breit.yaml"
KEY_Z = "VORAB_schatten_modell_breit sha256 "


def lade_vorab(pruefen: bool = True) -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if pruefen and last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("VORAB_schatten.yaml passt nicht zur Prüfsumme im Protokoll. Erst versiegeln, dann rechnen.")
    return yaml.safe_load(text)


def lade_zusatz(pruefen: bool = True) -> dict:
    """suche/VORAB_schatten_modell_breit.yaml: die 53. Fassung (Kirons Wahl vom 20.11.2026)."""
    text = ZUSATZ.read_text(encoding="utf-8")
    if pruefen and last_value(journal_lines(), KEY_Z) != sha256_text(text):
        raise SystemExit(f"{ZUSATZ.name} passt nicht zur Prüfsumme im Protokoll. Erst versiegeln, dann rechnen.")
    return yaml.safe_load(text)


# ---------------------------------------------------------------------------------------------------------------------
# Die Runden: je Runde ihre versiegelte Datei (Siegel wird geprüft) und ihre Rechnung

def runde(name: str):
    """(lade_vorab(pruefen) -> cfg, rechne) der Runde."""
    if name == "rueckblick":
        return rb.lade_vorab, rb.rechne
    if name == "youtube_runde":
        from suche import youtube_runde as m
        return m.lade_vorab, m.rechne
    if name == "youtube_runde2":
        from suche import youtube_runde2 as m
        return m.lade_vorab, m.rechne
    if name == "notizen_runde":
        from suche import notizen_runde as m
        return m.lade_vorab, m.rechne
    if name in ("grosse_runde", "grosse_runde2", "trade_notizen"):
        from suche import grosse_runde as m
        nr = {"grosse_runde": 1, "grosse_runde2": 2, "trade_notizen": 3}[name]
        return (lambda pruefen=True: m.lade_vorab(nr, pruefen)), m.rechne
    raise KeyError(name)


def fassungen(v: dict, pruefen: bool = True) -> dict[str, dict]:
    """Alle Fassungen aller Runden: "<runde>:<fassung>" -> {runde, fassung, regel, maerkte}."""
    out = {}
    for r in v["schatten"]["runden"]:
        cfg = runde(r)[0](pruefen)
        for n, x in cfg["varianten"].items():
            out[f"{r}:{n}"] = {"runde": r, "fassung": n, "regel": x["regel"], "maerkte": list(x["maerkte"])}
    return out


def zusatz_cfg(z: dict, pruefen: bool = True) -> dict:
    """Die versiegelte Datei der Zusatz-Runde, nur mit den Fassungen aus z (heute modell_breit)."""
    cfg = runde(z["zusatz"]["runde"])[0](pruefen)
    return {**cfg, "varianten": {n: cfg["varianten"][n] for n in z["zusatz"]["fassungen"]}}


def fassungen_zusatz(z: dict, pruefen: bool = True) -> dict[str, dict]:
    r = z["zusatz"]["runde"]
    return {f"{r}:{n}": {"runde": r, "fassung": n, "regel": x["regel"], "maerkte": list(x["maerkte"]), "zusatz": True}
            for n, x in zusatz_cfg(z, pruefen)["varianten"].items()}


def termine_jahre() -> set[int]:
    """Kalenderjahre, für die gold/v2/termine.yaml Termine aller drei Arten (Fed, Inflation, Arbeitsmarkt) hat."""
    from suche import grosse_runde as gr
    kal = gr.kalender()
    jahre = [set(pd.DatetimeIndex(t.astype("datetime64[ns]")).year) for t in kal.values()]
    return set.intersection(*jahre) if jahre else set()


# ---------------------------------------------------------------------------------------------------------------------
# Kennzahlen, Vorteil-Test, Holm, Stufe

def _pf(r: np.ndarray) -> float | None:
    g, v = float(r[r > 0].sum()), float(-r[r < 0].sum())
    return None if v == 0 else g / v


def _ab(pf: float | None, mindestens: float) -> bool:
    return pf is None or pf >= mindestens          # ohne Verlust-Trade gilt der Gewinnfaktor als hoch


def p_vorzeichen(r: np.ndarray, laeufe: int, saat: int) -> float:
    """Einseitig: Anteil der Läufe mit zufälligem Vorzeichen je Trade, deren Summe mindestens so groß ist wie die echte."""
    r = np.asarray(r, float)
    if len(r) == 0:
        return 1.0
    rng = np.random.default_rng(saat)
    echt = float(r.sum())
    groesser = 0
    for k in range(0, laeufe, 1000):
        n = min(1000, laeufe - k)
        s = rng.choice(np.array([-1.0, 1.0]), size=(n, len(r)))
        groesser += int(((s * np.abs(r)).sum(axis=1) >= echt - 1e-12).sum())
    return (1 + groesser) / (laeufe + 1)


def holm(p: dict[str, float], alpha: float) -> set[str]:
    """Holm über alle Fassungen: die kleinsten p der Reihe nach gegen alpha / (m - i), bis eine scheitert."""
    m, ok = len(p), set()
    for i, (n, x) in enumerate(sorted(p.items(), key=lambda kv: (kv[1], kv[0]))):
        if x > alpha / (m - i):
            break
        ok.add(n)
    return ok


def kennzahlen(w: pd.DataFrame, bis: str) -> dict:
    """w: Vorwärts-Trades einer Fassung, nach Ausstieg sortiert."""
    r, rr = w["R"].to_numpy(float), w["R_robust"].to_numpy(float)
    if not len(r):
        return {"trades": 0, "summe_R": 0.0, "gewinnfaktor": None, "gewinnfaktor_robust": None}
    aus = pd.to_datetime(w["aus_utc"])
    erst = pd.to_datetime(w["ein_utc"]).min()
    ende = pd.Timestamp(bis)
    letzte = r[aus.to_numpy() >= (ende - pd.Timedelta(days=61)).to_datetime64()]
    neu = r[len(r) // 2:]
    rund = lambda x, n=2: None if x is None else round(float(x), n)            # noqa: E731
    return {"trades": int(len(r)), "summe_R": rund(r.sum()), "R_je_trade": rund(r.mean(), 3),
            "gewinnfaktor": rund(_pf(r)), "gewinnfaktor_robust": rund(_pf(rr)), "treffer": rund((r > 0).mean()),
            "erster_trade": str(erst)[:16], "tage": int((ende - erst.normalize()).days),
            "letzte_61_tage_R": rund(letzte.sum()), "neuere_haelfte_gewinnfaktor": rund(_pf(neu))}


def stufe(e: dict, s: dict, holm_ok: bool) -> str:
    n, pf, rob = e["trades"], e.get("gewinnfaktor"), e.get("gewinnfaktor_robust")
    k, f, w = s["kandidat"], s["fruehzeichen"], s["schwach"]
    if (n >= k["trades"] and e["tage"] >= k["tage"] and _ab(pf, k["gewinnfaktor"]) and _ab(rob, k["gewinnfaktor_robust"])
            and e["letzte_61_tage_R"] > k["letzte_summe_r_ueber"]
            and _ab(e["neuere_haelfte_gewinnfaktor"], k["neuere_haelfte_gewinnfaktor"]) and holm_ok):
        return "kandidat"
    if n >= f["trades"] and _ab(pf, f["gewinnfaktor"]) and _ab(rob, f["gewinnfaktor_robust"]) and e["summe_R"] > f["summe_r_ueber"]:
        return "fruehzeichen"
    if n >= w["trades"] and pf is not None and pf < w["gewinnfaktor_unter"]:
        return "schwach"
    return "zaehlt"


def bewerte(trades: pd.DataFrame, alle: dict[str, dict], v: dict, bis: str,
            zusatz: dict[str, dict] | None = None) -> dict[str, dict]:
    """Je Fassung Kennzahlen, p, Holm und Stufe. trades mit Spalte "fassung". Die Fassungen aus zusatz bekommen ihre
    Saat nach den alten (saat plus 52 und weiter), Holm läuft über alle zusammen."""
    s = v["schatten"]
    t = s["test_vorteil"]
    erg, p = {}, {}
    reihe = list(enumerate(sorted(alle))) + [(len(alle) + j, n) for j, n in enumerate(sorted(zusatz or {}))]
    alle = {**alle, **(zusatz or {})}
    for i, n in reihe:
        w = trades[trades["fassung"] == n].sort_values(["aus_utc", "ein_utc"]) if len(trades) else trades
        e = {**alle[n], **kennzahlen(w, bis)}
        p[n] = e["p"] = round(p_vorzeichen(w["R"].to_numpy(float) if len(w) else np.array([]), t["laeufe"], t["saat"] + i), 5)
        erg[n] = e
    ok = holm(p, s["stufen"]["kandidat"]["holm_alpha"])
    for n, e in erg.items():
        e["holm"] = n in ok
        e["stufe"] = stufe(e, s["stufen"], e["holm"])
    return erg


# ---------------------------------------------------------------------------------------------------------------------
# Zählen

def zaehle(arbeit: pathlib.Path, v: dict, ab: str, bis: str | None = None, pruefen: bool = True,
           z: dict | None = None) -> tuple[dict, pd.DataFrame, str]:
    """Alle Fassungen von ab bis zur letzten Kerze (oder bis). Nur Trades, die vor der letzten Kerze ihres Markts
    geschlossen sind. Mit z (suche/VORAB_schatten_modell_breit.yaml) auch die Zusatz-Fassung. Gibt (Bewertung, Trades,
    letzter Tag) zurück."""
    alle = fassungen(v, pruefen)
    soll = v["schatten"]["fassungen"]
    if len(alle) != soll:
        raise SystemExit(f"{len(alle)} Fassungen gefunden, festgelegt sind {soll}.")
    zus = fassungen_zusatz(z, pruefen) if z else {}
    if z and len(alle) + len(zus) != z["fassungen_gesamt"]:
        raise SystemExit(f"{len(alle) + len(zus)} Fassungen gefunden, festgelegt sind {z['fassungen_gesamt']}.")
    if (arbeit / "DIX.csv").exists():                    # neuester DIX-Stand aus dem Arbeitsordner (baue_arbeit)
        from suche import grosse_runde as gr
        gr.FREMD["DIX"] = (arbeit / "DIX.csv", gr.FREMD["DIX"][1])
        gr.fred.cache_clear()
    runden = [(r, None) for r in v["schatten"]["runden"]] + ([(z["zusatz"]["runde"], zusatz_cfg(z, pruefen))] if z else [])
    hinweis: dict[str, str] = {}
    teile, letzte = [], []
    for r, cfg in runden:
        lade, rechne = runde(r)
        cfg = cfg if cfg is not None else lade(pruefen)
        maerkte = sorted({m for x in cfg["varianten"].values() for m in x["maerkte"]})
        ende = {m: pd.Timestamp(np.load(arbeit / f"{m}.npz")["t"].max()) for m in maerkte}
        if bis is not None:
            ende = {m: min(e, pd.Timestamp(bis) + pd.Timedelta(hours=23, minutes=59)) for m, e in ende.items()}
        bis_r = max(ende.values()).date().isoformat()
        letzte.append(bis_r)
        if bis_r < ab:
            continue
        mitte = (pd.Timestamp(ab) + (pd.Timestamp(bis_r) - pd.Timestamp(ab)) / 2).date().isoformat()
        _, tr = rechne(arbeit, cfg, None if bis is None else f"{bis}T23:59", (ab, bis_r), mitte, mit_zwillingen=False)
        if tr.empty:
            continue
        tr = tr[pd.to_datetime(tr["ein_utc"]) >= pd.Timestamp(ab)]
        offen = pd.to_datetime(tr["aus_utc"]).to_numpy() >= tr["markt"].map(ende).to_numpy(dtype="datetime64[ns]")
        tr = tr[~offen].copy()                           # noch offen oder am Datenende geschlossen: zählt später
        tr["fassung"] = r + ":" + tr["variante"].astype(str)
        if z and r == z["zusatz"]["runde"]:              # ohne Termine für das Jahr sähe das Modell Fed-Tage als normal
            ok = pd.to_datetime(tr["ein_utc"]).dt.year.isin(termine_jahre())
            for n, k in tr[~ok]["fassung"].value_counts().items():
                hinweis[n] = f"{k} Trades nicht gezählt, gold/v2/termine.yaml hat für ihr Jahr nicht alle Termine"
            tr = tr[ok]
        teile.append(tr)
    trades = pd.concat(teile, ignore_index=True) if teile else pd.DataFrame(
        columns=["fassung", "variante", "markt", "ein_utc", "aus_utc", "richtung", "R", "R_robust"])
    bis_alle = min(letzte) if letzte else ab
    erg = bewerte(trades, alle, v, bis_alle, zus)
    for n, h in hinweis.items():
        erg[n]["hinweis"] = h
    return erg, trades, bis_alle


def bericht(erg: dict, bis: str, ab: str) -> str:
    st = pd.Series([e["stufe"] for e in erg.values()]).value_counts().to_dict()
    n = sum(e["trades"] for e in erg.values())
    zeilen = [f"# Schatten-Labor, Stand {bis}", "",
              f"{len(erg)} Fassungen aus den versiegelten Runden werden ohne Order vorwärts gezählt, ab {ab}. "
              f"Bisher {n} geschlossene Vorwärts-Trades. Kandidaten {st.get('kandidat', 0)}, Frühzeichen "
              f"{st.get('fruehzeichen', 0)}, schwach {st.get('schwach', 0)}, noch zu wenige Trades {st.get('zaehlt', 0)}.",
              "", "Kandidat heißt 100 Trades, 61 Tage, Gewinnfaktor ab 1,3 und Holm über alle Fassungen bestanden. Dann "
              "kommt eine Karte an Kiron. Ein Bot entsteht nur über einen PR (suche/VORAB_schatten.yaml).", "",
              "| Fassung | Regel | Trades | Summe R | Gewinnfaktor | mit 1,5-fachen Kosten | p | Stufe |",
              "|---|---|---|---|---|---|---|---|"]
    fmt = lambda x: "–" if x is None else f"{x:.2f}".replace(".", ",")         # noqa: E731
    rang = {"kandidat": 0, "fruehzeichen": 1, "zaehlt": 2, "schwach": 3}
    wort = {"kandidat": "Kandidat", "fruehzeichen": "Frühzeichen", "zaehlt": "zählt weiter", "schwach": "schwach"}
    for n, e in sorted(erg.items(), key=lambda kv: (rang[kv[1]["stufe"]], -(kv[1].get("summe_R") or 0), kv[0])):
        zeilen.append(f"| {n} | {e['regel']} | {e['trades']} | {fmt(e.get('summe_R'))} | {fmt(e.get('gewinnfaktor'))} | "
                      f"{fmt(e.get('gewinnfaktor_robust'))} | {e['p']:.4f} | {wort[e['stufe']]} |".replace(f"{e['p']:.4f}", f"{e['p']:.4f}".replace(".", ",")))
    hinweise = [f"- {n}: {e['hinweis']}" for n, e in sorted(erg.items()) if e.get("hinweis")]
    if hinweise:
        zeilen += ["", "Hinweise", "", *hinweise]
    return "\n".join(zeilen) + "\n"


def schreibe(erg: dict, trades: pd.DataFrame, bis: str, ab: str, ziel: pathlib.Path, kopf: dict) -> None:
    ziel.with_suffix(".json").write_text(json.dumps({**kopf, "zaehlt_ab": ab, "bis": bis, "fassungen": erg},
                                                    ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    ziel.with_suffix(".md").write_text(bericht(erg, bis, ab), encoding="utf-8")
    spalten = [c for c in ["fassung", "markt", "ein_utc", "aus_utc", "richtung", "R", "R_robust"] if c in trades.columns]
    with gzip.open(ziel.parent / (ziel.name + "_trades.csv.gz"), "wt", encoding="utf-8") as f:
        trades[spalten].sort_values(["fassung", "ein_utc"]).to_csv(f, index=False)


# ---------------------------------------------------------------------------------------------------------------------
# Daten: neuen Monat holen (neue Dateien, nie überschreiben) und den Arbeitsordner bauen

def nachladen(kurs: pathlib.Path, monat: str) -> list[str]:
    import requests

    from suche import daten as hd
    from suche import rueckblick_daten as rd
    from suche import youtube_runde as yr
    jahr, mon = (int(x) for x in monat.split("-"))
    (kurs / "monate").mkdir(parents=True, exist_ok=True)
    s, out = requests.Session(), []
    for sym in rd.MAERKTE:
        ziel = kurs / "monate" / f"{sym}_5min_{monat}.csv.gz"
        if ziel.exists() or not (kurs / f"{sym}_5min.csv.gz").exists():
            continue
        blob = hd.fetch(s, sym, jahr, mon)
        if blob is None:
            out.append(f"{sym} {monat}: bei HistData noch nicht da")
            continue
        hd.to_bars(hd.parse_zip(blob), "5min").to_csv(ziel, index_label="utc", compression="gzip")
        out.append(f"{sym} {monat}: geladen")
    roh = kurs / "krypto" / "roh"
    for binance, _epic in yr.KRYPTO.values():
        ziel = roh / f"{binance}-5m-{monat}.zip"
        if ziel.exists() or not roh.exists():
            continue
        r = s.get(BINANCE.format(s=binance, m=monat), timeout=120)
        if r.ok and r.content[:2] == b"PK":
            ziel.write_bytes(r.content)
            out.append(f"{binance} {monat}: geladen")
        else:
            out.append(f"{binance} {monat}: bei Binance noch nicht da")
    ziel = kurs / "monate" / f"DIX_{monat}.csv"          # DIX für modell_breit und die DIX-Regel, neuer Stand als neue Datei
    if not ziel.exists():
        r = s.get(DIX_URL, timeout=120)
        if r.ok and r.text.startswith("date,"):
            ziel.write_text(r.text, encoding="utf-8")
            out.append(f"DIX {monat}: geladen, letzter Tag {r.text.strip().splitlines()[-1].split(',')[0]}")
        else:
            out.append(f"DIX {monat}: nicht geladen")
    return out


def baue_arbeit(kurs: pathlib.Path, arbeit: pathlib.Path) -> list[dict]:
    """Grunddatei plus alle Monatsdateien je Markt zusammen, dann genau dieselbe Umrechnung wie in den Tests."""
    from suche import rueckblick_daten as rd
    from suche import youtube_runde as yr
    arbeit.mkdir(parents=True, exist_ok=True)
    out = []
    alt = rd.DATEN, yr.KRYPTO_ROH
    with tempfile.TemporaryDirectory() as tmp:
        try:
            for sym in rd.MAERKTE:
                basis = kurs / f"{sym}_5min.csv.gz"
                if not basis.exists():
                    continue
                monate = sorted((kurs / "monate").glob(f"{sym}_5min_*.csv.gz"))
                rd.DATEN = kurs
                if monate:                               # nur dann zusammenfügen, die Grunddatei bleibt, wie sie ist
                    teile = [pd.read_csv(x, index_col=0, parse_dates=True) for x in [basis, *monate]]
                    df = pd.concat(teile)
                    df = df[~df.index.duplicated(keep="last")].sort_index()
                    df.to_csv(pathlib.Path(tmp) / basis.name, index_label="utc", compression="gzip")
                    rd.DATEN = pathlib.Path(tmp)
                out.append(rd.baue(sym, arbeit))
            yr.KRYPTO_ROH = kurs / "krypto" / "roh"
            if yr.KRYPTO_ROH.exists():
                for sym in yr.KRYPTO:
                    out.append(yr.baue_krypto(sym, arbeit))
        finally:
            rd.DATEN, yr.KRYPTO_ROH = alt
    dix = sorted((kurs / "monate").glob("DIX_*.csv"))
    if dix:                                              # der neueste Stand zählt, die Grunddatei bleibt, wie sie ist
        (arbeit / "DIX.csv").write_text(dix[-1].read_text(encoding="utf-8"), encoding="utf-8")
        out.append({"DIX": dix[-1].name})
    return out


# ---------------------------------------------------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    if argv and argv[0] == "--festlegen":
        zeile = KEY + sha256_text(VORAB.read_text(encoding="utf-8"))
        journal_add(zeile)
        print(zeile)
        return 0
    if len(argv) >= 3 and argv[0] == "nachladen":
        for z in nachladen(pathlib.Path(argv[1]), argv[2]):
            print(z, flush=True)
        return 0
    if len(argv) == 3 and argv[0] == "daten":
        for z in baue_arbeit(pathlib.Path(argv[1]), pathlib.Path(argv[2])):
            print(z, flush=True)
        return 0
    if len(argv) == 2 and argv[0] == "zaehlen":
        v = lade_vorab(pruefen=True)
        z = lade_zusatz(pruefen=True)
        ab = v["schatten"]["zaehlt_ab"]
        erg, tr, bis = zaehle(pathlib.Path(argv[1]), v, ab, z=z)
        kopf = {"modus": "Vorwärts-Zählung", "vorab_sha256": sha256_text(VORAB.read_text(encoding="utf-8")),
                "zusatz_sha256": sha256_text(ZUSATZ.read_text(encoding="utf-8"))}
        schreibe(erg, tr, bis, ab, ERGEBNIS, kopf)
        st = pd.Series([e["stufe"] for e in erg.values()]).value_counts().to_dict()
        journal_add(f"schatten zählung bis {bis}: {len(erg)} Fassungen, {len(tr)} Trades, Stufen "
                    + ", ".join(f"{k} {v}" for k, v in sorted(st.items())))
        print(bericht(erg, bis, ab))
        return 0
    if len(argv) == 4 and argv[0] == "probelauf":
        v = lade_vorab(pruefen=False)
        erg, tr, bis = zaehle(pathlib.Path(argv[1]), v, argv[2], argv[3], pruefen=False, z=lade_zusatz(pruefen=False))
        ziel = pathlib.Path(argv[1]) / "probelauf_schatten"
        schreibe(erg, tr, bis, argv[2], ziel, {"modus": "Probelauf auf alten Kerzen, kein Ergebnis"})
        print(bericht(erg, bis, argv[2]))
        return 0
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
