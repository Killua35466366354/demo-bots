"""Kombinierer: mehrere Strategien als EIN Konto mit einem Topf von 1.000 € (Kirons Wunsch vom 20.11.2026).

Regeln: Abschnitt "kombinierer" in suche/VORAB_schatten.yaml. Jeder Trade riskiert 1 % des Starttopfs (10 € je R).
Die Trades laufen nach Einstiegszeit durch die Kontoregeln: höchstens so viele offene Trades, höchstens so viele je
Markt, Tagesstopp und Gesamtbremse. Was ein echtes Konto so nicht nehmen könnte, zählt als verpasst. So zeigt die
Rechnung, was ein einziges echtes Konto mit allen Bots zusammen gebracht hätte, und nicht nur die Summe aller Bots.

Liest nur Journale, spricht mit keinem Broker, sendet keine Order, kein Bot liest seine Dateien. Kein KI-Modell: der
Satz für Kiron kommt aus einer festen Vorlage.

Aufruf:
    python -m suche.kombinierer                       zeigt den Stand der Demo-Bots
    python -m suche.kombinierer --schreiben           schreibt journal/kombinierer.json und journal/kombinierer.md
    python -m suche.kombinierer auskunft <trades.csv>  dieselben Regeln auf eine Trade-Liste (Spalten id, markt, ein,
                                                      aus, r, wahlweise margin_je_r), etwa Backtest-Trades, nur Auskunft

Margin-Ampel (seit 20.11.2026, suche/VORAB_kombinierer_margin.yaml): zwei weitere Regeln, bei denen ein Trade nur
genommen wird, wenn die Margin aller offenen Trades mit ihm zusammen höchstens 30 % (50 % zum Vergleich) des
Kontostands ist. Margin = 10 € * Einstieg / Stop-Abstand / Hebel des Marktes.
"""
from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

import pandas as pd
import yaml

from suche.runde1 import journal_lines, last_value, sha256_text

ROOT = pathlib.Path(__file__).resolve().parents[1]
J = ROOT / "journal"
VORAB = ROOT / "suche" / "VORAB_schatten.yaml"
KEY = "VORAB_schatten sha256 "
VORAB_M = ROOT / "suche" / "VORAB_kombinierer_margin.yaml"
KEY_M = "VORAB_kombinierer_margin sha256 "
NAMEN = {"ohne_grenzen": "ohne Grenzen", "konto": "Regeln eines echten Kontos",
         "konto_weiter": "weitere Kontoregeln (nur Vergleich)",
         "konto_margin": "Kontoregeln mit Margin-Ampel 30 %", "konto_margin_50": "mit Margin-Ampel 50 % (nur Vergleich)"}
GRUND = {"hoechstens_offen": "schon genug offen", "je_markt": "Markt schon belegt", "tagesstopp": "Tagesstopp",
         "gesamtbremse": "Gesamtbremse", "margin": "zu wenig Margin frei", "margin_unbekannt": "Margin unbekannt"}
# Markt je Bot, wenn seine Trades keinen "epic" tragen. Ein Markt = eine Position im Sinne von je_markt_hoechstens.
MARKT = {"gold-cb": "GOLD", "gold-staffel": "GOLD", "gold-grossbox": "GOLD", "gold-zonen": "GOLD",
         "gold-ausbruch4h": "GOLD", "pine-k5": "GOLD", "pine-tp3": "GOLD", "gold-hand": "GOLD",
         "scalp-us100": "US100", "scalp-de40": "DE40", "scalp-j225": "J225", "us500-ruecksetzer": "US500",
         "r5-ruecksetzer-us500": "US500", "r5-ruecksetzer-us100": "US100", "r7-nasdaq-noise-long": "US100",
         "r5-ruecksetzer-us30": "US30", "r6-vortag-eurusd": "EURUSD", "r6-vortag-gbpusd": "GBPUSD",
         "r6-vortag-gbpjpy": "GBPJPY", "r6-london-gbpusd": "GBPUSD", "r6-noise-usdjpy": "USDJPY"}


def regel(pruefen: bool = True) -> dict | None:
    """Der Abschnitt kombinierer, nur wenn das Siegel stimmt."""
    text = VORAB.read_text(encoding="utf-8")
    if pruefen and last_value(journal_lines(), KEY) != sha256_text(text):
        return None
    return yaml.safe_load(text)["kombinierer"]


def regel_margin(pruefen: bool = True) -> dict | None:
    """suche/VORAB_kombinierer_margin.yaml, nur wenn das Siegel stimmt."""
    text = VORAB_M.read_text(encoding="utf-8")
    if pruefen and last_value(journal_lines(), KEY_M) != sha256_text(text):
        return None
    return yaml.safe_load(text)


def mit_margin(k: dict, m: dict | None) -> dict:
    """Die Kontoregeln aus VORAB_schatten.yaml plus die Regeln mit Margin-Ampel, wenn deren Siegel stimmt."""
    return k if m is None else {**k, "regeln": {**k["regeln"], **m["regeln"]}}


# ---------------------------------------------------------------------------------------------------------------------
# Margin (suche/VORAB_kombinierer_margin.yaml)

def margin_je_r(markt: str, einstieg, abstand, m: dict) -> float | None:
    """Margin in Euro je 1 € Risiko: Positionswert (Einstieg / Stop-Abstand) geteilt durch den Hebel des Marktes."""
    try:
        e, a = float(einstieg), float(abstand)
    except (TypeError, ValueError):
        return None
    if not (e > 0 and a > 0):
        return None
    return e / a / m["margin"]["hebel"].get(markt, m["margin"]["hebel_sonst"])


def stop_abstand(t: dict) -> float | None:
    """Stop-Abstand eines Demo-Trades aus dem Journal, Reihenfolge wie in stop_abstand_live."""
    e = t.get("entry")
    if not isinstance(e, (int, float)) or e <= 0:
        return None
    for k in ("stop_level", "stop"):
        s = t.get(k)
        if isinstance(s, (int, float)) and not isinstance(s, bool) and s > 0 and s != e and abs(e - s) / e < 0.2:
            return abs(e - s)
    d = t.get("dist")
    if isinstance(d, (int, float)) and not isinstance(d, bool) and d > 0:
        return float(d)
    r, x = t.get("r"), t.get("exit")
    if isinstance(r, (int, float)) and isinstance(x, (int, float)) and abs(r) >= 0.3 and x != e:
        return abs(x - e) / abs(r)
    return None


def _median(werte: list[float]) -> float | None:
    return float(pd.Series(werte).median()) if werte else None


def margin_auffuellen(trades: list[dict], demo: list[dict] | None = None) -> list[dict]:
    """Fehlt margin_je_r: Median desselben Bots in derselben Liste, dann in den Demo-Trades, dann Median des Marktes
    in den Demo-Trades. Fehlt alles, bleibt None (zählt als "Margin unbekannt")."""
    demo = trades if demo is None else demo
    def nach(liste, feld):
        g = defaultdict(list)
        for x in liste:
            if x.get("margin_je_r") is not None and not x.get("margin_geschaetzt"):
                g[x[feld]].append(x["margin_je_r"])
        return {k: _median(v) for k, v in g.items()}
    eigen, demo_bot, demo_markt = nach(trades, "id"), nach(demo, "id"), nach(demo, "markt")
    for x in trades:
        if x.get("margin_je_r") is None:
            wert = eigen.get(x["id"]) or demo_bot.get(x["id"]) or demo_markt.get(x["markt"])
            x["margin_je_r"], x["margin_geschaetzt"] = wert, wert is not None
    return trades


# ---------------------------------------------------------------------------------------------------------------------
# Ein Konto, ein Topf

def topf(trades: list[dict], r: dict, topf_eur: float, eur_je_r: float) -> dict:
    """trades: dicts mit id, markt, ein, aus (pd.Timestamp) und r. r: Kontoregeln (Werte None = ohne Grenze)."""
    liste = sorted(trades, key=lambda t: (t["ein"], t["id"]))
    offen: list[dict] = []
    konto = hoch = topf_eur
    rueck = 0.0
    tag_eur: dict = defaultdict(float)
    monate: dict = {}
    genommen, verpasst, bremse_seit = 0, Counter(), None
    spitze_margin: float | None = 0.0

    def schliesse(bis) -> None:
        nonlocal konto, hoch, rueck
        for p in sorted([p for p in offen if bis is None or p["aus"] <= bis], key=lambda p: (p["aus"], p["id"])):
            offen.remove(p)
            eur = float(p["r"]) * eur_je_r
            konto += eur
            hoch = max(hoch, konto)
            rueck = max(rueck, hoch - konto)
            tag_eur[p["aus"].date()] += eur
            m = monate.setdefault(p["aus"].strftime("%Y-%m"), {"trades": 0, "eur": 0.0})
            m["trades"] += 1
            m["eur"] += eur

    for t in liste:
        schliesse(t["ein"])
        if bremse_seit is None and r.get("gesamtbremse_pct") and konto <= hoch * (1 - r["gesamtbremse_pct"] / 100):
            bremse_seit = t["ein"]
        if bremse_seit is not None:
            verpasst["gesamtbremse"] += 1
            continue
        if r.get("tagesstopp_pct") and tag_eur[t["ein"].date()] <= -topf_eur * r["tagesstopp_pct"] / 100:
            verpasst["tagesstopp"] += 1
            continue
        if r.get("hoechstens_offen") and len(offen) >= r["hoechstens_offen"]:
            verpasst["hoechstens_offen"] += 1
            continue
        if r.get("je_markt_hoechstens") and sum(p["markt"] == t["markt"] for p in offen) >= r["je_markt_hoechstens"]:
            verpasst["je_markt"] += 1
            continue
        belegt = sum((p.get("margin_je_r") or 0.0) * eur_je_r for p in offen)
        neu = t.get("margin_je_r")
        if r.get("margin_hoechstens_pct"):
            if neu is None:
                verpasst["margin_unbekannt"] += 1
                continue
            if belegt + neu * eur_je_r > konto * r["margin_hoechstens_pct"] / 100:
                verpasst["margin"] += 1
                continue
        offen.append(t)
        genommen += 1
        if spitze_margin is not None:
            spitze_margin = None if neu is None else max(spitze_margin, belegt + neu * eur_je_r)
    schliesse(None)
    if monate:
        alle = pd.period_range(min(monate), max(monate), freq="M").strftime("%Y-%m")
        reihe = [round(monate.get(m, {}).get("eur", 0.0), 2) for m in alle]
    else:
        alle, reihe = [], []
    schnitt = sum(reihe) / len(reihe) if reihe else 0.0
    return {"trades": len(liste), "genommen": genommen, "verpasst": dict(sorted(verpasst.items())),
            "summe_eur": round(konto - topf_eur, 2), "endstand_eur": round(konto, 2),
            "groesster_rueckgang_eur": round(rueck, 2), "monate": {m: {"trades": monate.get(m, {}).get("trades", 0),
                                                                      "eur": e} for m, e in zip(alle, reihe)},
            "schnitt_monat_eur": round(schnitt, 2), "schnitt_monat_pct": round(100 * schnitt / topf_eur, 2),
            "schlechtester_monat_eur": min(reihe) if reihe else None,
            "monate_im_minus": sum(1 for e in reihe if e < 0), "gesamtbremse_seit": None if bremse_seit is None
            else str(bremse_seit),
            "groesste_margin_eur": None if spitze_margin is None or not genommen else round(spitze_margin, 2)}


def alle_regeln(trades: list[dict], k: dict) -> dict:
    eur = k["topf_eur"] * k["risiko_je_trade_pct"] / 100
    return {name: topf(trades, r, k["topf_eur"], eur) for name, r in k["regeln"].items()}


# ---------------------------------------------------------------------------------------------------------------------
# Die Demo-Trades: genau die Trades, die journal/vergleich.json für die Gruppe und die Kern-Kombi zählt

def _ts(x) -> pd.Timestamp | None:
    if not x:
        return None
    t = pd.Timestamp(str(x))
    return (t.tz_convert("UTC").tz_localize(None) if t.tzinfo else t).floor("s")


def als_konto_trades(bid: str, trades: list[dict], m: dict | None = None) -> list[dict]:
    """Demo-Trades als Konto-Trades. Mit m (VORAB_kombinierer_margin) auch die Margin je 1 € Risiko."""
    out = []
    for t in trades:
        aus, ein = _ts(t.get("closed_utc")), _ts(t.get("opened_utc") or t.get("closed_utc"))
        if t.get("r") is None or aus is None:
            continue
        x = {"id": bid, "markt": str(t.get("epic") or MARKT.get(bid) or bid), "ein": min(ein, aus), "aus": aus,
             "r": float(t["r"])}
        if m is not None:
            x["margin_je_r"] = margin_je_r(x["markt"], t.get("entry"), stop_abstand(t), m)
        out.append(x)
    return out


def demo_gruppen(now: datetime | None = None, m: dict | None = None) -> tuple[dict, dict]:
    """(Gruppen-Trades je Name, vergleich) aus suche/vergleich.py, ohne eine eigene zweite Liste zu führen."""
    from suche import vergleich as vg
    sammeln: dict = {}
    v = vg.vergleich(now, sammeln=sammeln)
    gruppen = {}
    if v.get("gruppe"):
        drin = set(v["gruppe"]["mitglieder"])
        gruppen["demo_gruppe"] = [x for bid, ts in sammeln.get("gruppe", {}).items() if bid in drin
                                  for x in als_konto_trades(bid, ts, m)]
    gruppen["demo_kern"] = [x for bid, ts in sammeln.get("kern", {}).items() for x in als_konto_trades(bid, ts, m)]
    if m is not None:
        alle = [x for ts in gruppen.values() for x in ts]
        for ts in gruppen.values():
            margin_auffuellen(ts, alle)
    return gruppen, v


# ---------------------------------------------------------------------------------------------------------------------
# Bericht

def _eur(x: float) -> str:
    s = f"{abs(x):,.0f}".replace(",", ".")
    return ("+" if x > 0 else "−" if x < 0 else "") + s + " €"


def satz(stand: dict) -> str:
    g = stand["gruppen"].get("demo_gruppe")
    if not g or not g["ohne_grenzen"]["trades"]:
        return "Der Kombinierer wartet auf die ersten Demo-Trades der Gruppe aller Bots."
    o, k = g["ohne_grenzen"], g["konto"]
    return (f"Alle Demo-Bots zusammen als ein Konto mit 1.000 € und 10 € Risiko je Trade stehen bei {_eur(o['summe_eur'])} "
            f"nach {o['trades']} Trades. Mit den Regeln eines echten Kontos (höchstens 3 offene Trades, einer je Markt) "
            f"hätte es {k['genommen']} davon genommen und {_eur(k['summe_eur'])} gebracht."
            + (f" Mit Margin-Ampel (höchstens 30 % des Kontos als Sicherheitsgeld gebunden) wären es "
               f"{g['konto_margin']['genommen']} Trades und {_eur(g['konto_margin']['summe_eur'])} gewesen."
               if "konto_margin" in g else ""))


def bericht(stand: dict) -> str:
    z = [f"# Kombinierer, Stand {stand['tag']}", "", stand["satz"], "",
         "Ein Konto, ein Topf von 1.000 €, jeder Trade riskiert 10 € (1 R). Die Regeln stehen in "
         "suche/VORAB_schatten.yaml und suche/VORAB_kombinierer_margin.yaml (Margin-Ampel). Margin ist das "
         "Sicherheitsgeld, das der Broker für offene Trades festhält. Nur Demokonten, nur Auskunft, kein Bot liest "
         "diese Datei.", ""]
    titel = {"demo_gruppe": "Gruppe aller Bots (wie im Demo-Vergleich)", "demo_kern": "Kern-Kombi"}
    for g, erg in stand["gruppen"].items():
        z += [f"## {titel.get(g, g)}", "", "| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | "
              "Schnitt je Monat | größte Margin |", "|---|---|---|---|---|---|---|"]
        for name, e in erg.items():
            vp = ", ".join(f"{GRUND.get(k, k)} {v}" for k, v in e["verpasst"].items()) or "–"
            pct = f"{e['schnitt_monat_pct']:.1f}".replace(".", ",").replace("-", "−")
            mg = "–" if e.get("groesste_margin_eur") is None else _eur(e["groesste_margin_eur"]).lstrip("+")
            z.append(f"| {NAMEN.get(name, name)} | {e['genommen']} von {e['trades']} | {vp} | {_eur(e['summe_eur'])} | "
                     f"{_eur(-e['groesster_rueckgang_eur'])} | {_eur(e['schnitt_monat_eur'])} ({pct} %) | {mg} |")
        n = stand.get("margin_geschaetzt", {}).get(g)
        if n and n[0]:
            z += ["", f"Bei {n[0]} von {n[1]} Trades fehlt der Stop-Abstand im Journal, ihre Margin ist der Median "
                      "desselben Bots oder Marktes."]
        z.append("")
    return "\n".join(z) + "\n"


def stand(now: datetime | None = None) -> dict | None:
    k = regel()
    if k is None:
        return None
    m = regel_margin()
    k = mit_margin(k, m)
    now = now or datetime.now(timezone.utc)
    gruppen, _ = demo_gruppen(now, m)
    out = {"format": 1, "tag": now.astimezone(timezone.utc).date().isoformat(), "topf_eur": k["topf_eur"],
           "eur_je_r": k["topf_eur"] * k["risiko_je_trade_pct"] / 100, "regeln": k["regeln"],
           "gruppen": {g: alle_regeln(ts, k) for g, ts in gruppen.items()}}
    if m is not None:
        out["margin_geschaetzt"] = {g: [sum(1 for x in ts if x.get("margin_geschaetzt") or x.get("margin_je_r") is None),
                                        len(ts)] for g, ts in gruppen.items()}
    out["satz"] = satz(out)
    return out


def lies_csv(pfad: pathlib.Path) -> list[dict]:
    d = pd.read_csv(pfad)
    out = [{"id": str(x.id), "markt": str(x.markt), "ein": pd.Timestamp(x.ein), "aus": pd.Timestamp(x.aus),
            "r": float(x.r)} for x in d.itertuples()]
    if "margin_je_r" in d:
        for x, mj in zip(out, d.margin_je_r):
            x["margin_je_r"] = None if pd.isna(mj) else float(mj)
    return out


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "auskunft":
        k = regel()
        if k is None:
            raise SystemExit("VORAB_schatten.yaml passt nicht zur Prüfsumme im Protokoll.")
        print(json.dumps(alle_regeln(lies_csv(pathlib.Path(argv[1])), mit_margin(k, regel_margin())),
                         ensure_ascii=False, indent=1))
        return 0
    s = stand()
    if s is None:
        print("Prüfsumme von VORAB_schatten.yaml fehlt im Protokoll, der Kombinierer rechnet nicht.")
        return 0
    if argv and argv[0] == "--schreiben":
        (J / "kombinierer.json").write_text(json.dumps(s, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (J / "kombinierer.md").write_text(bericht(s), encoding="utf-8")
    print(bericht(s))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
