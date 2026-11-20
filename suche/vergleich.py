"""Vergleich der Demo-Profite aller Bots und Aufstiegs-Check (nur Capital.com-Demo, nie echtes Geld).

Kirons Wunsch vom 05.11.2026, 10:17 UTC: alle Demo-Bots laufen die nächsten Wochen live, "die profite dann abgleichen
und bewerten"; was profitabel ist (allein oder mehrere zusammen), kommt später mit echtem Geld auf ein Konto im privaten
Repo. Dieses Modul liest nur Dateien (journal/, suche/*.yaml), spricht mit keinem Broker und ändert keinen Bot:

1. Rangliste aller Bots mit Demo-Lauf: Demo-Trades seit dem jetzigen Konto, Summe R, Gewinnfaktor auf R, Demo-Euro,
   größter Rückgang in R. Daneben das Soll: so viele Trades und R hätte die Strategie im selben Zeitraum im Schnitt der
   Bewertung 2025-2026 gemacht (journal/portfolio.json, 1 % Risiko auf 1.000 € = 10 € je R).
2. Die Kombi: alle Strategien unter "behalten" (suche/auswahl.yaml) zusammen, so wie sie später auf einem Konto lägen,
   mit Monatssummen.
3. Aufstieg je Strategie und für die Kombi: "reif für Kirons Entscheidung" oder warum noch nicht. Es gilt
   suche/VORAB_aufstieg_alle.yaml (Punkt 5), solange ihre Prüfsumme im Protokoll steht, sonst suche/VORAB_aufstieg.yaml.
   Es entscheidet immer Kiron.
4. Eigene Gruppe "auf Kirons Wunsch" (Projekt-Prüfung 11.11.2026, Befund B-19): die Bots mit festem Konto aus
   suche/mitnutzer.py (Pine-Bots, Scalper, Gold-Staffel, Groß-Box). Sie stehen nicht unter der Prüfung nach 15/40 Trades,
   nicht in der Rangliste und nicht in der Kombi. Über sie urteilt ihre eigene Regeldatei, den Aufstieg prüft Punkt 5.
   Hier stehen sie, damit kein Urteil vergessen wird: Demo-Trades und R aus ihrer eigenen Trade-Datei, das Urteil als der
   Text, den der Bot selbst schreibt.
5. Aufstieg nach suche/VORAB_aufstieg_alle.yaml (Kirons Wahl vom 18.11.2026 "2 Monate und 100 Trades", nur wenn ihre
   Prüfsumme im Protokoll steht): jeder Bot allein, die Kombi und die feste Gruppe aller Bots brauchen 100 Trades,
   mindestens 61 Tage und in den letzten 61 Tagen eine Summe über 0. Gewinnfaktor 1,2 für die sechs Kern-Bots und ihre
   Kombi, 1,3 für alle anderen und die Gruppe. Auch hier entscheidet immer Kiron.

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
VORAB_ALLE = ROOT / "suche" / "VORAB_aufstieg_alle.yaml"
KEY_ALLE = "VORAB_aufstieg_alle sha256 "
AUSWAHL = ROOT / "suche" / "auswahl.yaml"
WOCHEN_BEWERTUNG = (pd.Timestamp("2026-10-30") - pd.Timestamp("2025-01-01")).days / 7   # Fenster der Bewertung
EUR_JE_R = 10.0                     # 1 % Risiko auf 1.000 €
GOLD = dp.HAUPT_BOT                 # Gold-Bot C/B auf dem Hauptkonto
GOLD_LONG = "gold-cb-long"           # Mess-Zeile: nur die C-Trades des Gold-Bots (suche/VORAB_messbots.yaml)
MESS_TEXT = {"status": "messung", "text": "Mess-Bot: Vergleich mit Vortag EUR/USD, kein Aufstieg"}
# Gold fürs Urteil: nur Trades mit der jetzigen Regel (Stop 1 x ATR seit 03.11.2026 09:05 UTC, gleicher Start wie
# gold/bot/VORAB_sicherheit.yaml). Der Wochenbericht zeigt zusätzlich alle Demo-Trades seit 31.10. (Kritik D7).
GOLD_START = "2026-11-03T09:05:00"


def _versiegelt(datei: Path, key: str, abschnitt: str) -> dict | None:
    from suche.runde1 import journal_lines, last_value
    from suche.runde3 import sha256_text
    if not datei.exists():
        return None
    text = datei.read_text(encoding="utf-8")
    if last_value(journal_lines(), key) != sha256_text(text):
        return None
    return yaml.safe_load(text)[abschnitt]


def regel() -> dict | None:
    """Die Regel aus VORAB_aufstieg.yaml, nur wenn ihre Prüfsumme im Protokoll steht."""
    return _versiegelt(VORAB, KEY, "aufstieg")


def regel_alle() -> dict | None:
    """Die Regel aus VORAB_aufstieg_alle.yaml (alle Bots, die Kombi und die Gruppe), nur wenn versiegelt."""
    return _versiegelt(VORAB_ALLE, KEY_ALLE, "aufstieg_alle")


def kennzahlen(trades: list[dict], feld: str = "r") -> dict:
    """Trades nach Schlusszeit sortiert: Anzahl, Treffer, Summe R, Gewinnfaktor, Euro, größter Rückgang in R. Mit
    feld="pct" dieselben Zahlen in Prozent vom Kurs (für Bots ohne Stop, die kein R haben); die Schlüssel heißen gleich."""
    r = [float(t[feld]) for t in trades if t.get(feld) is not None]
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


def _tage(start, tag: pd.Timestamp | None) -> int:
    """Ganze Tage vom Start bis zum Tag der Prüfung (UTC), ohne Start 0."""
    s = wb._ts(start) if start is not None and not isinstance(start, pd.Timestamp) else start
    if s is None or tag is None:
        return 0
    return max((tag.date() - s.date()).days, 0)


def _start(trades: list[dict], start=None):
    """Der Start aus der Karte oder Zählung, sonst der erste Trade (Einstieg, sonst Schluss)."""
    if start:
        return start
    zeiten = [str(t.get("opened_utc") or t.get("closed_utc") or "") for t in trades]
    zeiten = [z for z in zeiten if z]
    return min(zeiten) if zeiten else None


def pruefe(trades: list[dict], k: dict, rueckgang_max: float | None = None, feld: str = "r",
           zeit: dict | None = None, start=None, tag: pd.Timestamp | None = None) -> dict:
    """Aufstieg nach den Kriterien k (einzeln oder kombi aus VORAB_aufstieg.yaml, einzeln_kern, einzeln oder kombi aus
    VORAB_aufstieg_alle.yaml). trades nach Schlusszeit sortiert. feld="pct" für einen Bot ohne Stop, der in Prozent vom
    Kurs misst. Mit zeit (VORAB_aufstieg_alle.yaml) zählen dazu die Tage seit start bis tag und die Summe der letzten
    Tage."""
    z = kennzahlen(trades, feld)
    n, ab = z["trades"], k["ab_trades"]
    einheit = "R" if feld == "r" else "%"
    tage = _tage(start, tag) if zeit else None
    if n < ab or (zeit and tage < zeit["mindestens_tage"]):
        txt = f"{n} von {ab} Demo-Trades"
        return {"status": "sammelt", "text": txt if not zeit else f"{txt}, {tage} von {zeit['mindestens_tage']} Tagen"}
    fehlt = []
    if not _pf_ok(z["pf_r"], k["pf_mindestens"]):
        fehlt.append(f"Gewinnfaktor {z['pf_r']:.2f} unter {k['pf_mindestens']}")
    if z["summe_r"] <= k["summe_r_ueber"]:
        fehlt.append(f"Summe {z['summe_r']:+.2f} {einheit} nicht über {k['summe_r_ueber']}")
    if zeit:
        ab_tag = (tag - pd.Timedelta(days=zeit["letzte_tage"])).date().isoformat()
        letzte = round(sum(float(t[feld]) for t in trades
                           if t.get(feld) is not None and str(t.get("closed_utc") or "") >= ab_tag), 2)
        if letzte <= zeit["summe_letzte_tage_ueber"]:
            fehlt.append(f"letzte {zeit['letzte_tage']} Tage {letzte:+.2f} {einheit} nicht über "
                         f"{zeit['summe_letzte_tage_ueber']}")
    zweite = kennzahlen([t for t in trades if t.get(feld) is not None][n // 2:], feld)
    if not _pf_ok(zweite["pf_r"], k["zweite_haelfte_pf_mindestens"]):
        fehlt.append(f"neuere Hälfte Gewinnfaktor {zweite['pf_r']:.2f} unter {k['zweite_haelfte_pf_mindestens']}")
    if rueckgang_max is not None and z["rueckgang_r"] > rueckgang_max:
        fehlt.append(f"Rückgang {z['rueckgang_r']:.1f} R über {rueckgang_max:.1f} R")
    if fehlt:
        return {"status": "nicht_reif", "text": "; ".join(fehlt)}
    return {"status": "reif", "text": "reif für Kirons Entscheidung (echtes Geld nur nach seinem Ja und einem PR)"}


def pruefe_gruppe(mitglied_trades: dict[str, list[dict]], g: dict, zeit: dict | None = None, start=None,
                  tag: pd.Timestamp | None = None) -> dict:
    """Die feste Gruppe aus VORAB_aufstieg_alle.yaml: alle Mitglieder zusammen, nur Trades mit R. Ein Mitglied ab
    jedes_mitglied.ab_trades mit Gewinnfaktor darunter fällt heraus, dann braucht der Rest pf_nach_ausfall. Ohne das
    Mitglied mit der höchsten Summe R (alle Gold-Bots als eines) muss der Rest über ohne_bestes_pf_ueber liegen. start
    ist der früheste Start der Mitglieder."""
    jm = g["jedes_mitglied"]
    mit_r = {bid: _sortiert([t for t in ts if t.get("r") is not None]) for bid, ts in mitglied_trades.items()}
    draussen, drin = [], []
    for bid in g["mitglieder"]:
        if bid not in mit_r:
            continue
        z = kennzahlen(mit_r[bid])
        if z["trades"] >= jm["ab_trades"] and not _pf_ok(z["pf_r"], jm["pf_mindestens"]):
            draussen.append({"id": bid, "warum": f"Gewinnfaktor {z['pf_r']:.2f} nach {z['trades']} Trades"})
        else:
            drin.append(bid)
    alle = _sortiert([t for bid in drin for t in mit_r[bid]])
    k = dict(g)
    if draussen:
        k["pf_mindestens"] = g["pf_nach_ausfall"]
    a = pruefe(alle, k, zeit=zeit, start=start, tag=tag)
    einheiten: dict[str, list[dict]] = {}
    for bid in drin:
        einheiten.setdefault("gold" if bid in set(g.get("gold") or []) else bid, []).extend(mit_r[bid])
    bestes = max(einheiten, key=lambda e: (round(sum(float(t["r"]) for t in einheiten[e]), 6), e), default=None)
    ohne = kennzahlen(_sortiert([t for e, ts in einheiten.items() if e != bestes for t in ts]))
    if a["status"] == "reif" and not (ohne["trades"] and (ohne["pf_r"] is None or ohne["pf_r"] > g["ohne_bestes_pf_ueber"])):
        pf = "–" if ohne["pf_r"] is None else f"{ohne['pf_r']:.2f}"
        a = {"status": "nicht_reif", "text": f"ohne ihr bestes Mitglied ({bestes}) Gewinnfaktor {pf}, nötig über "
                                              f"{g['ohne_bestes_pf_ueber']}"}
    return {"fest": len(g["mitglieder"]), "mitglieder": drin, "draussen": draussen, "ist": kennzahlen(alle),
            "monate": _monate(alle),
            "bestes": bestes, "ohne_bestes": ohne, "aufstieg": a}


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


def _gruppe(bid: str, aus: dict, abgeloest: set, mess: set = frozenset()) -> str:
    if bid in mess:
        return "messung"                            # Mess-Bot (suche/VORAB_messbots.yaml), kein Kandidat für echtes Geld
    for g in ("behalten", "verbessern", "labor", "abschalten"):
        if bid in (aus.get(g) or {}):
            return g
    return "abgeloest" if bid in abgeloest else "labor"


def _sortiert(trades: list[dict]) -> list[dict]:
    return sorted(trades, key=lambda t: str(t.get("closed_utc") or ""))


def _zwillinge(laeufe: dict) -> tuple[dict, dict | None]:
    """Einträge aus suche/zwillinge.yaml mit Trade-Datei (ein Fehler dort hält den Vergleich nie auf)."""
    try:
        from suche import zwilling as zw
        liste = {z: e for z, e in zw.eintraege().items() if isinstance(e, dict) and e.get("trades")
                 and e.get("start_utc") and e.get("original") and z not in laeufe}
        return liste, zw.regel()
    except Exception:                                   # noqa: BLE001
        return {}, None


def _zwilling_stand(bid: str, e: dict, rg: dict | None, trades: list[dict], laeufe: dict, kont: dict, now) -> dict:
    """Stand eines Zwillings gegen sein Original im selben Zeitraum (suche/VORAB_zwilling.yaml)."""
    if rg is None:
        return {"status": "keine_regel", "text": "Prüfsumme von VORAB_zwilling.yaml fehlt"}
    from suche import zwilling as zw
    org = e["original"]
    ab = max(str(e["start_utc"]), str(dp.seit_wann(kont, org) or ""))
    if org in laeufe:
        o = dp.demo_trades(laeufe[org], org, ab)
    else:                                               # Bot mit festem Konto im Code (suche/mitnutzer.py)
        o = [t for t in wb._lines(J / org / "trades.jsonl") if str(t.get("closed_utc") or "") >= ab]
    st = zw.stand(trades, o, rg, str(e["start_utc"]), now, e)
    return {"status": st["status"], "text": st["text"], "original": org}


def _einheit(trades: list[dict]) -> str:
    """"r", wenn die Trades R haben. "pct" nur, wenn kein Trade R hat, aber jeder Prozent vom Kurs (Bot ohne Stop,
    z. B. der Nikkei-Scalper scalp-j225); dann misst er in Prozent, und ohne das stünde er mit 0 Trades da."""
    zu = [t for t in trades if t.get("closed_utc")]
    if zu and not any(t.get("r") is not None for t in zu) and all(t.get("pct") is not None for t in zu):
        return "pct"
    return "r"


def _wunsch(rg_alle: dict | None = None, tag: pd.Timestamp | None = None
            ) -> tuple[list[dict], str | None, dict[str, list[dict]]]:
    """Bots mit festem Konto (suche/mitnutzer.py), die neue Trades öffnen: eine Zeile je Bot aus seinem eigenen Journal
    (journal/<bot>.json und journal/<bot>/trades.jsonl), mit dem Aufstieg nach VORAB_aufstieg_alle.yaml (einzeln). Dazu
    die Trades je Bot für die Gruppe. Ein Fehler hier hält den Vergleich nie auf."""
    try:
        from suche import mitnutzer
        liste = mitnutzer.aktive()
    except Exception as e:                              # noqa: BLE001
        return [], f"suche/mitnutzer.py nicht lesbar ({type(e).__name__})", {}
    out, alle_trades = [], {}
    for b in liste:
        bid = b["bot"]
        karte = wb._read(J / f"{bid}.json", {})
        karte = karte if isinstance(karte, dict) else {}
        alle = wb._lines(J / bid / "trades.jsonl")
        feld = _einheit(alle)
        trades = _sortiert([t for t in alle if t.get(feld) is not None])
        alle_trades[bid] = trades
        z = karte.get("zusammenfassung") if isinstance(karte.get("zusammenfassung"), dict) else {}
        seit = str(karte.get("start") or "")[:10] or None
        out.append({"id": bid, "name": str(karte.get("name") or bid).split(" (")[0], "konto": b["konto_name"],
                    "seit": seit, "start": _start(trades, seit), "ist": kennzahlen(trades, feld),
                    "einheit": "%" if feld == "pct" else "R",
                    "urteil": z.get("urteil"), "vorab": karte.get("vorab"),
                    "test": karte.get("test") or karte.get("backtest"),
                    "aufstieg": {"status": "keine_regel", "text": "Prüfsumme von VORAB_aufstieg_alle.yaml fehlt"}
                    if rg_alle is None else pruefe(trades, rg_alle["einzeln"], None, feld, rg_alle["zeit"],
                                                   _start(trades, seit), tag)})
    return out, None, alle_trades


def vergleich(now: datetime | None = None, sammeln: dict | None = None) -> dict:
    """Der Demo-Vergleich. Mit sammeln (ein leeres dict) legt er dort die Trades ab, die er für die Gruppe ("gruppe")
    und die Kern-Kombi ("kern") zählt, je Bot, damit suche/kombinierer.py keine zweite Liste führen muss."""
    now = now or datetime.now(timezone.utc)
    tag = pd.Timestamp(now.astimezone(timezone.utc).date())
    rg = regel()
    rg_alle = regel_alle()
    kern = set((rg_alle or {}).get("kern") or [])
    zeit = (rg_alle or {}).get("zeit")
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
    mess = set(kont.get("messung") or {})

    laeufe = {GOLD: J / "gold-trades.jsonl", **dp.laeufe()}
    zwl, zw_rg = _zwillinge(laeufe)
    zeilen, alle_trades, starts = [], {}, {}
    for bid, datei in {**laeufe, **{z: ROOT / e["trades"] for z, e in zwl.items()}}.items():
        if bid in zwl:
            seit = str(zwl[bid]["start_utc"])           # ein Zwilling zählt ab seinem Start (suche/VORAB_zwilling.yaml)
            trades = [t for t in dp.demo_trades(datei, bid, seit) if t.get("bot") == bid]
        elif bid == GOLD:
            seit = GOLD_START
            trades = [t for t in wb._lines(datei) if str(t.get("closed_utc") or "") >= seit]
        else:
            seit = dp.seit_wann(kont, bid)
            trades = dp.demo_trades(datei, bid, seit)
        trades = _sortiert(trades)
        aktiv = bid == GOLD or bid in zu or (bid in zwl and not zwl[bid].get("ende_utc"))
        if not aktiv and not trades:
            continue                                    # nie gelaufen oder abgelöst ohne Demo-Trade
        alle_trades[bid] = trades
        p = rang.get(bid, {})
        z = kennzahlen(trades)
        start = wb._ts(seit or seit_aus) or tag
        starts[bid] = start
        soll = _soll(p, start, tag) if aktiv else None
        # Nach VORAB_aufstieg_alle.yaml (Kirons Wahl vom 18.11.2026), solange versiegelt, sonst nach VORAB_aufstieg.yaml
        if rg_alle is not None:
            ek = rg_alle["einzeln_kern"] if bid in kern else rg_alle["einzeln"]
        else:
            ek = (rg or {}).get("einzeln")
        rueck_max = None
        if ek and p.get("eur_1000_rueckgang") is not None:
            rr = ek["rueckgang_r"]
            rueck_max = max(rr["mal_bewertung"] * p["eur_1000_rueckgang"] / EUR_JE_R, rr["mindestens"])
        name, markt = namen.get(bid, (p.get("name") or ("Gold C/B" if bid == GOLD else bid), p.get("markt")))
        if bid in zwl:
            e = zwl[bid]
            name = e.get("name") or f"Zwilling von {namen.get(e['original'], (e['original'],))[0]}"
            markt = markt or namen.get(e["original"], (None, None))[1]
        zeilen.append({
            "id": bid, "name": p.get("name") or name, "markt": p.get("markt") or markt or ("Gold" if bid == GOLD else None),
            "gruppe": "zwilling" if bid in zwl else _gruppe(bid, aus, abgeloest, mess), "aktiv": aktiv,
            "konto": "Hauptkonto" if bid == GOLD else "Schatten (keine Order)" if bid in zwl and str(
                zwl[bid].get("konto")) == "schatten" and aktiv else konto_name.get("…" + str(zu.get(bid, ""))[-4:])
            if aktiv else None,
            "seit": None if start is None else start.isoformat(), "ist": z, "soll": soll,
            "abweichung_r": None if not soll or soll["summe_r"] is None else round(z["summe_r"] - soll["summe_r"], 2),
            "bewertung": None if not p else {"rang": p.get("rang"), "pf": p.get("pf"), "eur_1000": p.get("eur_1000"),
                                             "bestanden": p.get("bestanden")},
            "monate": _monate(trades),
            "aufstieg": _zwilling_stand(bid, zwl[bid], zw_rg, trades, laeufe, kont, now) if bid in zwl
            else None if not aktiv else MESS_TEXT if bid in mess else (
                {"status": "keine_regel", "text": "Prüfsumme von VORAB_aufstieg.yaml fehlt"}
                if ek is None else pruefe(trades, ek, rueck_max, zeit=zeit, start=start, tag=tag))})
    # ---- Mess-Zeile "Gold nur Long" (Kritik F2/D4, suche/VORAB_messbots.yaml): die C-Trades des Hauptkontos ----
    if GOLD in alle_trades:
        lt = [t for t in alle_trades[GOLD] if (t.get("strategy") or ("C" if t.get("side") == "long" else "B")) == "C"]
        zeilen.append({"id": GOLD_LONG, "name": "Gold nur Long (Teil C)", "markt": "Gold", "gruppe": "messung",
                       "aktiv": True, "konto": "Hauptkonto (aus Gold C/B)", "seit": GOLD_START, "ist": kennzahlen(lt),
                       "soll": None, "abweichung_r": None, "bewertung": None, "monate": _monate(lt),
                       "aufstieg": {"status": "messung", "text": "Mess-Zeile: C allein gegen C und B, Urteil mit dem "
                                    "Gold-Bot Ende Januar 2027 (verpasst C-Signale, solange B offen ist)"}})
    zeilen.sort(key=lambda b: (not b["aktiv"], -b["ist"]["summe_r"], (b["bewertung"] or {}).get("rang") or 999))
    for i, b in enumerate(zeilen, 1):
        b["rang"] = i

    # ---- Kombi: alle "behalten" zusammen, so wie sie später auf einem Konto lägen ----
    mitglieder = [bid for bid in (aus.get("behalten") or {}) if bid in alle_trades]
    k_aus, drin = [], []
    kr = rg_alle["kombi"] if rg_alle is not None else (rg or {}).get("kombi")
    jm = (kr or {}).get("jedes_mitglied") or {"ab_trades": 10, "pf_mindestens": 1.0}
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
             "aufstieg": {"status": "keine_regel", "text": "Prüfsumme von VORAB_aufstieg.yaml fehlt"} if kr is None
             else pruefe(kt, kr, zeit=zeit, start=min((starts[b] for b in mitglieder), default=None), tag=tag)}
    if sammeln is not None:
        sammeln["kern"] = {bid: alle_trades[bid] for bid in drin}
    letzte = max((str(t.get("closed_utc")) for ts in alle_trades.values() for t in ts if t.get("closed_utc")), default=None)
    wunsch, wunsch_fehler, wunsch_trades = _wunsch(rg_alle, tag)
    starts.update({b["id"]: wb._ts(b["start"]) for b in wunsch if b.get("start")})
    # ---- Gruppe aller Bots (VORAB_aufstieg_alle.yaml): Mitglieder fest seit dem Siegel, auch abgeschaltete zählen ----
    gruppe = None
    if rg_alle is not None:
        gt = {}
        for bid in rg_alle["gruppe"]["mitglieder"]:
            if bid in alle_trades:
                gt[bid] = alle_trades[bid]
            elif bid in wunsch_trades:
                gt[bid] = wunsch_trades[bid]
            elif (J / bid / "trades.jsonl").exists():
                gt[bid] = _sortiert(wb._lines(J / bid / "trades.jsonl"))
                starts.setdefault(bid, wb._ts(_start(gt[bid])))
        st = [starts[b] for b in gt if starts.get(b) is not None]
        gruppe = pruefe_gruppe(gt, rg_alle["gruppe"], zeit, min(st, default=None), tag)
        if sammeln is not None:
            sammeln["gruppe"] = gt
    return {"format": 1, "tag": tag.date().isoformat(), "letzter_trade_utc": letzte,
            "regel_aufstieg": "festgelegt" if rg else "Prüfsumme fehlt",
            "regel_aufstieg_alle": "festgelegt" if rg_alle else "Prüfsumme fehlt",
            "rangliste": zeilen, "kombi": kombi, "gruppe": gruppe, "wunsch": wunsch, "wunsch_fehler": wunsch_fehler,
            "hinweis": "Nur Demokonten (Spielgeld, kleinste Größen): verglichen wird in R. Soll = Schnitt der Bewertung "
                       "2025-2026 im selben Zeitraum (1 % Risiko auf 1.000 € = 10 € je R). Wenige Trades sagen fast "
                       "nichts; über echtes Geld entscheidet immer Kiron. " + (
                           "Aufstieg nach suche/VORAB_aufstieg_alle.yaml: 100 Trades und mindestens 61 Tage, die "
                           "letzten 61 Tage im Plus, Gewinnfaktor 1,2 für die Kern-Bots und ihre Kombi, 1,3 für alle "
                           "anderen und die Gruppe." if rg_alle is not None else
                           "Aufstieg nach suche/VORAB_aufstieg.yaml (40 Trades, Kombi 60).")}


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
    g = v.get("gruppe")
    if g:
        i = g["ist"]
        z += ["", f"**Gruppe aller Bots ({g['fest']} feste Mitglieder, davon {len(g['draussen'])} herausgefallen, "
              "suche/VORAB_aufstieg_alle.yaml):** "
              f"{i['trades']} Trades, {de(i['summe_r'])} R, Gewinnfaktor {de(i['pf_r'], 2, False)}. "
              f"Aufstieg: {g['aufstieg']['text']}."]
        if g["draussen"]:
            z.append("Aus der Gruppe gefallen: " + ", ".join(f"{d['id']} ({d['warum']})" for d in g["draussen"]) + ".")
    w = v.get("wunsch") or []
    if w or v.get("wunsch_fehler"):
        z += ["", "## Auf Kirons Wunsch, außerhalb der Prüfung nach 15 und 40 Trades", "",
              "Diese Bots haben ein festes Konto (suche/mitnutzer.py). Sie stehen nicht in der Rangliste und nicht in der "
              "Kombi. Ihr Urteil nach 40 Trades steht in ihrer eigenen Regeldatei. Den Weg zu echtem Geld regelt "
              "suche/VORAB_aufstieg_alle.yaml (Spalte Aufstieg).", ""]
    if v.get("wunsch_fehler"):
        z.append(f"Die Liste ließ sich nicht lesen: {v['wunsch_fehler']}.")
    if w:
        z += ["| Bot | Konto | seit | Demo-Trades | Summe | Gewinnfaktor | Demo-€ | Urteil laut Bot | Regeldatei | "
              "Aufstieg |", "|---|---|---|---|---|---|---|---|---|---|"]
        for b in w:
            i = b["ist"]
            summe = f"{de(i['summe_r'])} {b.get('einheit') or 'R'}"
            auf = (b.get("aufstieg") or {}).get("text") or "–"
            z.append(f"| {b['name']} | {b['konto']} | {b['seit'] or '–'} | {i['trades']} | {summe} | "
                     f"{de(i['pf_r'], 2, False)} | {de(i['eur'])} | {b['urteil'] or '–'} | {b['vorab'] or '–'} | {auf} |")
    z += ["", f"Der Gold-Bot zählt hier ab {GOLD_START[:10]} {GOLD_START[11:16]} UTC (seit dem Stop 1 x ATR). Der "
          "Wochenbericht zählt alle seine Demo-Trades seit dem 31.10.2026, darum kann dort ein Trade mehr stehen."]
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
