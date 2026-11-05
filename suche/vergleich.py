"""Vergleich der Demo-Profite aller Bots und Aufstiegs-Check (nur Capital.com-Demo, nie echtes Geld).

Kirons Wunsch vom 05.11.2026, 10:17 UTC: alle Demo-Bots laufen die nächsten Wochen live, "die profite dann abgleichen
und bewerten"; was profitabel ist (allein oder mehrere zusammen), kommt später mit echtem Geld auf ein Konto im privaten
Repo. Dieses Modul liest nur Dateien (journal/, suche/*.yaml), spricht mit keinem Broker und ändert keinen Bot:

1. Rangliste aller Bots mit Demo-Lauf: Demo-Trades seit dem jetzigen Konto, Summe R, Gewinnfaktor auf R, Demo-Euro,
   größter Rückgang in R. Daneben das Soll: so viele Trades und R hätte die Strategie im selben Zeitraum im Schnitt der
   Bewertung 2025-2026 gemacht (journal/portfolio.json, 1 % Risiko auf 1.000 € = 10 € je R).
2. Die Kombi: alle Strategien unter "behalten" (suche/auswahl.yaml) zusammen, so wie sie später auf einem Konto lägen,
   mit Monatssummen.
3. Aufstieg nach suche/VORAB_aufstieg.yaml (nur wenn ihre Prüfsumme im Protokoll steht): je Strategie und für die Kombi
   "reif für Kirons Entscheidung" oder warum noch nicht. Es entscheidet immer Kiron.

    python -m suche.vergleich                # Text
    python -m suche.vergleich --schreiben    # dazu journal/vergleich.json und journal/vergleich.md

Die Dateien hängen nur vom Tag und den Trades ab, nicht von der Uhrzeit: ein Lauf ohne neuen Trade ändert sie höchstens
einmal am Tag.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from suche import demo_pruefung as dp
from suche import wochenbericht as wb

ROOT = Path(__file__).resolve().parents[1]
J = ROOT / "journal"
VORAB = ROOT / "suche" / "VORAB_aufstieg.yaml"
KEY = "VORAB_aufstieg sha256 "
AUSWAHL = ROOT / "suche" / "auswahl.yaml"
WOCHEN_BEWERTUNG = (pd.Timestamp("2026-10-30") - pd.Timestamp("2025-01-01")).days / 7   # Fenster der Bewertung
EUR_JE_R = 10.0                     # 1 % Risiko auf 1.000 €
GOLD = dp.HAUPT_BOT                 # Gold-Bot C/B auf dem Hauptkonto
GOLD_START = "2026-11-03T07:14:21"  # Beginn des Demo-Vergleichs (journal/demo-bots.json start_utc)


def regel() -> dict | None:
    """Die Regel aus VORAB_aufstieg.yaml, nur wenn ihre Prüfsumme im Protokoll steht."""
    from suche.runde1 import journal_lines, last_value
    from suche.runde3 import sha256_text
    text = VORAB.read_text(encoding="utf-8")
    if last_value(journal_lines(), KEY) != sha256_text(text):
        return None
    return yaml.safe_load(text)["aufstieg"]


def kennzahlen(trades: list[dict]) -> dict:
    """Trades nach Schlusszeit sortiert: Anzahl, Treffer, Summe R, Gewinnfaktor, Euro, größter Rückgang in R."""
    r = [float(t["r"]) for t in trades if t.get("r") is not None]
    g, v = sum(x for x in r if x > 0), -sum(x for x in r if x < 0)
    hoch = summe = rueck = 0.0
    for x in r:
        summe += x
        hoch = max(hoch, summe)
        rueck = max(rueck, hoch - summe)
    eur = [float(t["pnl_eur"]) for t in trades if t.get("pnl_eur") is not None]
    return {"trades": len(r), "gewonnen": sum(1 for x in r if x > 0),
            "treffer_pct": None if not r else round(100 * sum(1 for x in r if x > 0) / len(r), 1),
            "summe_r": round(sum(r), 2), "pf_r": None if v == 0 else round(g / v, 2),
            "eur": round(sum(eur), 2), "rueckgang_r": round(rueck, 2)}


def _pf_ok(pf: float | None, mindestens: float) -> bool:
    return pf is None or pf >= mindestens          # ohne Verlust-Trade gilt der Gewinnfaktor als hoch


def pruefe(trades: list[dict], k: dict, rueckgang_max: float | None = None) -> dict:
    """Aufstieg nach den Kriterien k (einzeln oder kombi aus VORAB_aufstieg.yaml). trades nach Schlusszeit sortiert."""
    z = kennzahlen(trades)
    n, ab = z["trades"], k["ab_trades"]
    if n < ab:
        return {"status": "sammelt", "text": f"{n} von {ab} Demo-Trades"}
    fehlt = []
    if not _pf_ok(z["pf_r"], k["pf_mindestens"]):
        fehlt.append(f"Gewinnfaktor {z['pf_r']:.2f} unter {k['pf_mindestens']}")
    if z["summe_r"] <= k["summe_r_ueber"]:
        fehlt.append(f"Summe {z['summe_r']:+.2f} R nicht über {k['summe_r_ueber']}")
    zweite = kennzahlen(trades[n // 2:])
    if not _pf_ok(zweite["pf_r"], k["zweite_haelfte_pf_mindestens"]):
        fehlt.append(f"neuere Hälfte Gewinnfaktor {zweite['pf_r']:.2f} unter {k['zweite_haelfte_pf_mindestens']}")
    if rueckgang_max is not None and z["rueckgang_r"] > rueckgang_max:
        fehlt.append(f"Rückgang {z['rueckgang_r']:.1f} R über {rueckgang_max:.1f} R")
    if fehlt:
        return {"status": "nicht_reif", "text": "; ".join(fehlt)}
    return {"status": "reif", "text": "reif für Kirons Entscheidung (echtes Geld nur nach seinem Ja und einem PR)"}


def _monate(trades: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for t in trades:
        m = str(t.get("closed_utc") or "")[:7]
        if len(m) == 7 and t.get("r") is not None:
            e = out.setdefault(m, {"trades": 0, "summe_r": 0.0, "eur": 0.0})
            e["trades"] += 1
            e["summe_r"] = round(e["summe_r"] + float(t["r"]), 2)
            e["eur"] = round(e["eur"] + float(t.get("pnl_eur") or 0), 2)
    return dict(sorted(out.items()))


def _soll(p: dict, seit: pd.Timestamp, tag: pd.Timestamp) -> dict | None:
    """Erwartung im Zeitraum seit..tag im Schnitt der Bewertung 2025-2026."""
    if not p.get("trades"):
        return None
    wochen = max((tag - seit).total_seconds() / 604800, 0.0)
    return {"wochen": round(wochen, 1), "trades": round(p["trades"] / WOCHEN_BEWERTUNG * wochen, 1),
            "summe_r": None if p.get("eur_1000") is None
            else round(p["eur_1000"] / EUR_JE_R / WOCHEN_BEWERTUNG * wochen, 2)}


def _gruppe(bid: str, aus: dict, abgeloest: set) -> str:
    for g in ("behalten", "verbessern", "labor", "abschalten"):
        if bid in (aus.get(g) or {}):
            return g
    return "abgeloest" if bid in abgeloest else "labor"


def _sortiert(trades: list[dict]) -> list[dict]:
    return sorted(trades, key=lambda t: str(t.get("closed_utc") or ""))


def vergleich(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    tag = pd.Timestamp(now.astimezone(timezone.utc).date())
    rg = regel()
    aus = (yaml.safe_load(AUSWAHL.read_text(encoding="utf-8")) or {}).get("auswahl") or {} if AUSWAHL.exists() else {}
    seit_aus = (aus.get("seit") or "2026-11-04")
    pf = wb._read(J / "portfolio.json", {})
    kont = wb._read(J / "konten.json", {})
    rang = {b.get("id"): b for b in pf.get("bots") or []}
    namen = {w[0]: (w[1], w[2]) for w in wb.WEITERE}
    cfg = yaml.safe_load((ROOT / "suche" / "demo_bots.yaml").read_text(encoding="utf-8")) or {}
    namen.update({b["id"]: (b.get("name") or b["id"], b.get("epic")) for b in list(cfg.get("bots") or [])
                  + list(cfg.get("extra_bots") or [])})
    konto_name = {str(k.get("id")): k.get("name") for k in kont.get("konten") or []}
    zu = kont.get("zuordnung") or {}
    abgeloest = set(kont.get("abgeloest") or {}) | set(cfg.get("abgeloest") or {}) | set(dp._r6_beendet())

    laeufe = {GOLD: J / "gold-trades.jsonl", **dp.laeufe()}
    zeilen, alle_trades = [], {}
    for bid, datei in laeufe.items():
        if bid == GOLD:
            seit = GOLD_START
            trades = [t for t in wb._lines(datei) if str(t.get("closed_utc") or "") >= seit]
        else:
            seit = dp.seit_wann(kont, bid)
            trades = dp.demo_trades(datei, bid, seit)
        trades = _sortiert(trades)
        aktiv = bid == GOLD or bid in zu
        if not aktiv and not trades:
            continue                                    # nie gelaufen oder abgelöst ohne Demo-Trade
        alle_trades[bid] = trades
        p = rang.get(bid, {})
        z = kennzahlen(trades)
        start = wb._ts(seit or seit_aus) or tag
        soll = _soll(p, start, tag) if aktiv else None
        rueck_max = None
        if rg and p.get("eur_1000_rueckgang") is not None:
            rr = rg["einzeln"]["rueckgang_r"]
            rueck_max = max(rr["mal_bewertung"] * p["eur_1000_rueckgang"] / EUR_JE_R, rr["mindestens"])
        name, markt = namen.get(bid, (p.get("name") or ("Gold C/B" if bid == GOLD else bid), p.get("markt")))
        zeilen.append({
            "id": bid, "name": p.get("name") or name, "markt": p.get("markt") or markt or ("Gold" if bid == GOLD else None),
            "gruppe": _gruppe(bid, aus, abgeloest), "aktiv": aktiv,
            "konto": "Hauptkonto" if bid == GOLD else konto_name.get("…" + str(zu.get(bid, ""))[-4:]) if aktiv else None,
            "seit": None if start is None else start.isoformat(), "ist": z, "soll": soll,
            "abweichung_r": None if not soll or soll["summe_r"] is None else round(z["summe_r"] - soll["summe_r"], 2),
            "bewertung": None if not p else {"rang": p.get("rang"), "pf": p.get("pf"), "eur_1000": p.get("eur_1000"),
                                             "bestanden": p.get("bestanden")},
            "monate": _monate(trades),
            "aufstieg": None if not aktiv else ({"status": "keine_regel", "text": "Prüfsumme von VORAB_aufstieg.yaml fehlt"}
                                                if rg is None else pruefe(trades, rg["einzeln"], rueck_max))})
    zeilen.sort(key=lambda b: (not b["aktiv"], -b["ist"]["summe_r"], (b["bewertung"] or {}).get("rang") or 999))
    for i, b in enumerate(zeilen, 1):
        b["rang"] = i

    # ---- Kombi: alle "behalten" zusammen, so wie sie später auf einem Konto lägen ----
    mitglieder = [bid for bid in (aus.get("behalten") or {}) if bid in alle_trades]
    k_aus, drin = [], []
    jm = (rg or {}).get("kombi", {}).get("jedes_mitglied") or {"ab_trades": 10, "pf_mindestens": 1.0}
    for bid in mitglieder:
        z = kennzahlen(alle_trades[bid])
        if z["trades"] >= jm["ab_trades"] and not _pf_ok(z["pf_r"], jm["pf_mindestens"]):
            k_aus.append({"id": bid, "warum": f"Gewinnfaktor {z['pf_r']:.2f} nach {z['trades']} Trades"})
        else:
            drin.append(bid)
    kt = _sortiert([t for bid in drin for t in alle_trades[bid]])
    soll_k = [b["soll"] for b in zeilen if b["id"] in drin and b["soll"]]
    kombi = {"mitglieder": drin, "draussen": k_aus, "ist": kennzahlen(kt), "monate": _monate(kt),
             "soll": {"trades": round(sum(s["trades"] for s in soll_k), 1),
                      "summe_r": round(sum(s["summe_r"] or 0 for s in soll_k), 2)},
             "aufstieg": {"status": "keine_regel", "text": "Prüfsumme von VORAB_aufstieg.yaml fehlt"} if rg is None
             else pruefe(kt, rg["kombi"])}
    letzte = max((str(t.get("closed_utc")) for ts in alle_trades.values() for t in ts if t.get("closed_utc")), default=None)
    return {"format": 1, "tag": tag.date().isoformat(), "letzter_trade_utc": letzte,
            "regel_aufstieg": "festgelegt" if rg else "Prüfsumme fehlt",
            "rangliste": zeilen, "kombi": kombi,
            "hinweis": "Nur Demokonten (Spielgeld, kleinste Größen): verglichen wird in R. Soll = Schnitt der Bewertung "
                       "2025-2026 im selben Zeitraum (1 % Risiko auf 1.000 € = 10 € je R). Wenige Trades sagen fast "
                       "nichts; über echtes Geld entscheidet immer Kiron (suche/VORAB_aufstieg.yaml)."}


def text(v: dict) -> str:
    de = wb._de
    z = [f"# Demo-Vergleich, Stand {v['tag']}", "",
         "Nur Demokonten. Verglichen wird in R (1 R = Risiko bis zum Stop). Soll = Schnitt der Bewertung 2025-2026 im "
         "selben Zeitraum.", "",
         "| # | Strategie | Gruppe | Demo-Trades | Summe R | Gewinnfaktor | Demo-€ | Soll bisher | Aufstieg |",
         "|---|---|---|---|---|---|---|---|---|"]
    for b in v["rangliste"]:
        i, s = b["ist"], b["soll"]
        soll = "–" if not s else f"{de(s['trades'], 1, False)} Trades, {de(s['summe_r'])} R"
        auf = "–" if not b["aufstieg"] else b["aufstieg"]["text"]
        z.append(f"| {b['rang']} | {b['name']} | {b['gruppe']} | {i['trades']} | {de(i['summe_r'])} | "
                 f"{de(i['pf_r'], 2, False)} | {de(i['eur'])} | {soll} | {auf} |")
    k = v["kombi"]
    i = k["ist"]
    z += ["", f"**Kombi ({len(k['mitglieder'])} Kern-Strategien auf einem Konto):** {i['trades']} Trades, "
          f"{de(i['summe_r'])} R, Gewinnfaktor {de(i['pf_r'], 2, False)}, Soll bisher {de(k['soll']['trades'], 1, False)} "
          f"Trades und {de(k['soll']['summe_r'])} R. Aufstieg: {k['aufstieg']['text']}."]
    if k["draussen"]:
        z.append("Aus der Kombi gefallen: " + ", ".join(f"{d['id']} ({d['warum']})" for d in k["draussen"]) + ".")
    if k["monate"]:
        z += ["", "| Monat | Kombi-Trades | Summe R | mit 1.000 € bei 1 % |", "|---|---|---|---|"]
        for m, e in k["monate"].items():
            z.append(f"| {m} | {e['trades']} | {de(e['summe_r'])} | {de(e['summe_r'] * EUR_JE_R, 0)} € |")
    return "\n".join(z) + "\n"


def main(argv: list[str]) -> int:
    v = vergleich()
    t = text(v)
    if "--schreiben" in argv:
        (J / "vergleich.json").write_text(json.dumps(v, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (J / "vergleich.md").write_text(t, encoding="utf-8")
    print(t)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
