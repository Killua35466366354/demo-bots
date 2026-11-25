"""Gold-Duo doppelt: der Gold-Bot C/B und Pine-K5 zusammen auf EINEM gedachten Konto mit 1.000 € und doppeltem Einsatz
(Kirons Wahl vom 25.11.2026 "g11", Vorschlag G11 des Gesamt-Komitees vom 24.11.2026).

Regeln: suche/VORAB_gold_duo_doppelt.yaml, versiegelt, bevor ein Trade gezählt wurde. Nur eine Zählung nach vorn: es
zählen nur Trades, die nach dem Siegel eröffnet wurden. Jeder Trade zählt mit der doppelten Größe des Demo-Trades. Ein
Trade zählt nur, wenn sein Sicherheitsgeld (Margin) noch auf das gedachte Konto passt. Liegt das Konto 30 % unter seinem
Höchststand, ist die Zählung beendet.

Liest nur die Dateien der zwei Bots im Journal, spricht mit keinem Broker, sendet keine Order, kein Bot liest das
Ergebnis. Kein KI-Modell: die Sätze für Kiron kommen aus festen Vorlagen.

Aufruf:
    python -m suche.gold_duo        zeigt den Stand

Der Kombinierer (suche/kombinierer.py) nimmt den Stand in journal/kombinierer.json (Schlüssel "gold_duo") und als
eigenen Abschnitt in journal/kombinierer.md auf. Ein Fehler hier hält den Kombinierer nie auf.
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
VORAB = ROOT / "suche" / "VORAB_gold_duo_doppelt.yaml"
KEY = "VORAB_gold_duo_doppelt sha256 "
NAMEN = {"gold-cb": "Gold-Bot C/B", "pine-k5": "Pine-K5"}
# Noch offene Positionen der zwei Bots (Datei, Schlüssel). Sie binden Sicherheitsgeld, solange sie offen sind.
OFFEN = {"gold-cb": ("journal/gold-state.json", "open_trade"), "pine-k5": ("journal/pine-k5.json", "offen")}
GRUND = {"margin": "kein Sicherheitsgeld frei", "margin_unbekannt": "Margin unbekannt", "bremse": "Bremse"}
STATUS = {"sammelt": "sammelt", "reif": "reif für Kirons Entscheidung", "nicht_reif": "nicht reif",
          "durchgefallen": "durchgefallen"}


def regel(pruefen: bool = True) -> dict | None:
    """Der Abschnitt gold_duo_doppelt, nur wenn das Siegel stimmt."""
    if not VORAB.exists():
        return None
    text = VORAB.read_text(encoding="utf-8")
    if pruefen and last_value(journal_lines(), KEY) != sha256_text(text):
        return None
    return yaml.safe_load(text)["gold_duo_doppelt"]


# ---------------------------------------------------------------------------------------------------------------------
# Trades der zwei Bots

def _ts(x) -> pd.Timestamp | None:
    if not x:
        return None
    try:
        t = pd.Timestamp(str(x))
    except ValueError:
        return None
    return (t.tz_convert("UTC").tz_localize(None) if t.tzinfo else t).floor("s")


def _zahl(x) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _zeilen(pfad: pathlib.Path) -> list[dict]:
    if not pfad.exists():
        return []
    out = []
    for z in pfad.read_text(encoding="utf-8").splitlines():
        try:
            x = json.loads(z)
        except ValueError:
            continue
        if isinstance(x, dict):
            out.append(x)
    return out


def _richtung(t: dict) -> int | None:
    """+1 Kauf, -1 Verkauf. Der Gold-Bot C/B schreibt side, Pine-K5 richtung."""
    if t.get("richtung") in (1, -1):
        return int(t["richtung"])
    return {"long": 1, "short": -1}.get(str(t.get("side") or "").lower())


def margin_eur(t: dict, k: dict) -> float | None:
    """Sicherheitsgeld des Trades mit doppelter Größe in Euro: Faktor x Größe x Einstieg / Hebel / Dollar je Euro."""
    size, entry = _zahl(t.get("size")), _zahl(t.get("entry"))
    if size is None or entry is None or size <= 0 or entry <= 0:
        return None
    return k["einsatz_faktor"] * size * entry / k["hebel"] / k["usd_je_eur"]


def als_trade(bot: str, t: dict, g: dict) -> dict | None:
    """Ein Journal-Trade als Trade des gedachten Kontos. Ohne Schluss ist er noch offen (eur None)."""
    ein, aus = _ts(t.get("opened_utc")), _ts(t.get("closed_utc"))
    if ein is None or ein < pd.Timestamp(g["start_utc"]):
        return None
    eur = _zahl(t.get("pnl_eur"))
    if aus is not None and eur is None:
        return None                                     # geschlossen, aber ohne Ergebnis: zählt nicht
    return {"bot": bot, "ein": ein, "aus": None if aus is None else max(aus, ein),
            "eur": None if aus is None else g["konto"]["einsatz_faktor"] * eur,
            "margin": margin_eur(t, g["konto"]), "richtung": _richtung(t)}


def trades(g: dict, root: pathlib.Path = ROOT) -> list[dict]:
    """Alle Trades der Mitglieder seit dem Start: die geschlossenen aus ihren Trade-Dateien und die noch offenen
    Positionen (nur für das Sicherheitsgeld)."""
    out = []
    for bot, datei in g["mitglieder"].items():
        for t in _zeilen(root / datei):
            if t.get("closed_utc"):
                x = als_trade(bot, t, g)
                if x is not None:
                    out.append(x)
        pfad, feld = OFFEN.get(bot, (None, None))
        if pfad and (root / pfad).exists():
            try:
                roh = json.loads((root / pfad).read_text(encoding="utf-8")).get(feld)
            except (OSError, ValueError, AttributeError):
                roh = None
            for t in ([roh] if isinstance(roh, dict) else roh if isinstance(roh, list) else []):
                if isinstance(t, dict) and not t.get("closed_utc"):
                    x = als_trade(bot, t, g)
                    if x is not None:
                        out.append(x)
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Ein gedachtes Konto

def _pf(werte: list[float]) -> float | None:
    gewinn, verlust = sum(x for x in werte if x > 0), -sum(x for x in werte if x < 0)
    return None if verlust == 0 else round(gewinn / verlust, 2)


def zaehlen(liste: list[dict], g: dict) -> dict:
    """Die Trades nach Eröffnung durch das gedachte Konto. Gebucht wird beim Schluss. Rückgabe mit der Liste der
    gebuchten Trades unter "gebucht" (nach Schlusszeit)."""
    k = g["konto"]
    topf = float(k["topf_eur"])
    spaet = pd.Timestamp.max
    offen: list[dict] = []
    gebucht: list[dict] = []
    konto = hoch = topf
    rueck = spitze = 0.0
    verpasst: Counter = Counter()
    bremse_seit = None

    def schliesse(bis) -> None:
        nonlocal konto, hoch, rueck
        faellig = [p for p in offen if p["aus"] is not None and (bis is None or p["aus"] <= bis)]
        for p in sorted(faellig, key=lambda p: (p["aus"], p["ein"], p["bot"])):
            offen.remove(p)
            konto += p["eur"]
            hoch = max(hoch, konto)
            rueck = max(rueck, hoch - konto)
            gebucht.append(p)

    for t in sorted(liste, key=lambda t: (t["ein"], t["aus"] or spaet, t["bot"])):
        schliesse(t["ein"])
        if bremse_seit is None and konto <= hoch * (1 - k["bremse_pct"] / 100):
            bremse_seit = t["ein"]
        if bremse_seit is not None:
            verpasst["bremse"] += t["aus"] is not None
            continue
        if t["margin"] is None:
            verpasst["margin_unbekannt"] += t["aus"] is not None
            continue
        belegt = sum(p["margin"] for p in offen)
        if belegt + t["margin"] > konto:
            verpasst["margin"] += t["aus"] is not None
            continue
        offen.append(t)
        spitze = max(spitze, belegt + t["margin"])
    schliesse(None)
    return {"gebucht": gebucht, "offen": len(offen), "verpasst": {a: n for a, n in sorted(verpasst.items()) if n},
            "endstand_eur": round(konto, 2), "summe_eur": round(konto - topf, 2),
            "groesster_rueckgang_eur": round(rueck, 2), "groesste_margin_eur": round(spitze, 2),
            "bremse_seit": None if bremse_seit is None else str(bremse_seit)}


def urteil(e: dict, u: dict, tage: int, tag: pd.Timestamp, bremse_pct: float = 30) -> dict:
    """Status nach dem Abschnitt urteil der Regeldatei."""
    werte = [p["eur"] for p in e["gebucht"]]
    n = len(werte)
    if e["bremse_seit"]:
        return {"status": "durchgefallen", "text": f"Bremse seit dem {_datum(e['bremse_seit'])}, das gedachte Konto lag "
                                                   f"{bremse_pct:g} % unter seinem Höchststand"}
    if n < u["ab_trades"] or tage < u["mindestens_tage"]:
        return {"status": "sammelt", "text": f"{n} von {u['ab_trades']} Trades, {tage} von {u['mindestens_tage']} Tagen"}
    fehlt = []
    pf = _pf(werte)
    if pf is not None and pf < u["pf_mindestens"]:
        fehlt.append(f"Gewinnfaktor {pf:.2f} unter {u['pf_mindestens']}".replace(".", ","))
    if sum(werte) <= u["summe_eur_ueber"]:
        fehlt.append(f"Summe {_eur(sum(werte))} nicht über {u['summe_eur_ueber']} €")
    ab = tag - pd.Timedelta(days=u["letzte_tage"])
    letzte = sum(p["eur"] for p in e["gebucht"] if p["aus"] >= ab)
    if letzte <= u["summe_letzte_tage_ueber"]:
        fehlt.append(f"letzte {u['letzte_tage']} Tage {_eur(letzte)} nicht über {u['summe_letzte_tage_ueber']} €")
    zweite = _pf(werte[n // 2:])
    if zweite is not None and zweite < u["zweite_haelfte_pf_mindestens"]:
        fehlt.append(f"neuere Hälfte Gewinnfaktor {zweite:.2f} unter {u['zweite_haelfte_pf_mindestens']}"
                     .replace(".", ","))
    if fehlt:
        return {"status": "nicht_reif", "text": ", ".join(fehlt)}
    return {"status": "reif", "text": "reif für Kirons Entscheidung (echtes Geld nur nach seinem Ja und einem PR)"}


def kennzahlen(e: dict, g: dict) -> dict:
    """Zahlen für den Bericht. Die Auskunft (beste Tage, Richtung, je Bot) hat keinen Einfluss auf das Urteil."""
    topf = float(g["konto"]["topf_eur"])
    b = e["gebucht"]
    werte = [p["eur"] for p in b]
    monate: dict = defaultdict(lambda: {"trades": 0, "eur": 0.0})
    tage: dict = defaultdict(float)
    je_bot: dict = {bot: {"trades": 0, "eur": 0.0} for bot in g["mitglieder"]}
    seite = {"kauf": {"trades": 0, "eur": 0.0}, "verkauf": {"trades": 0, "eur": 0.0}}
    for p in b:
        m = monate[p["aus"].strftime("%Y-%m")]
        m["trades"] += 1
        m["eur"] += p["eur"]
        tage[p["aus"].date().isoformat()] += p["eur"]
        je_bot[p["bot"]]["trades"] += 1
        je_bot[p["bot"]]["eur"] += p["eur"]
        if p["richtung"] in (1, -1):
            s = seite["kauf" if p["richtung"] == 1 else "verkauf"]
            s["trades"] += 1
            s["eur"] += p["eur"]
    beste = sorted(tage.items(), key=lambda x: (-x[1], x[0]))[:2]
    runde = lambda d: {a: {"trades": x["trades"], "eur": round(x["eur"], 2)} for a, x in d.items()}   # noqa: E731
    return {"trades": len(werte), "gewonnen": sum(1 for x in werte if x > 0), "pf": _pf(werte),
            "monate": {m: {"trades": x["trades"], "eur": round(x["eur"], 2), "pct": round(100 * x["eur"] / topf, 1)}
                       for m, x in sorted(monate.items())},
            "je_bot": runde(je_bot), "richtung": runde(seite),
            "beste_tage": [[d, round(v, 2)] for d, v in beste],
            "ohne_zwei_beste_tage_eur": round(sum(werte) - sum(v for _, v in beste), 2) if len(tage) > 2 else None}


# ---------------------------------------------------------------------------------------------------------------------
# Bericht

def _eur(x: float) -> str:
    s = f"{abs(x):,.0f}".replace(",", ".")
    return ("+" if round(x) > 0 else "−" if round(x) < 0 else "") + s + " €"


def _komma(x: float, stellen: int = 2) -> str:
    return f"{x:.{stellen}f}".replace(".", ",").replace("-", "−")


def _datum(iso: str) -> str:
    t = pd.Timestamp(iso)
    return f"{t.day}.{t.month}.{t.year}"


def satz(s: dict) -> str:
    seit = _datum(s["start_utc"])
    if not s["trades"]:
        return (f"Das Gold-Duo mit doppeltem Einsatz wartet auf den ersten gezählten Trade seit dem {seit}. Die Trades "
                "vom November davor zählen nicht.")
    wort = "Trade" if s["trades"] == 1 else "Trades"
    tage = "Tag" if s["tage"] == 1 else "Tagen"
    return (f"Das Gold-Duo mit doppeltem Einsatz steht nach {s['trades']} {wort} und {s['tage']} {tage} bei "
            f"{_eur(s['summe_eur'])} auf einem gedachten Konto mit 1.000 €. Der größte Rückgang war "
            f"{_eur(-s['groesster_rueckgang_eur'])}, das Urteil heißt {STATUS[s['urteil']['status']]}.")


def abschnitt(s: dict | None) -> list[str]:
    """Die Zeilen für journal/kombinierer.md."""
    if not s:
        return []
    kopf = ["## Gold-Duo doppelt (Zählung ohne Order)", ""]
    if s.get("fehler"):
        return kopf + [f"Die Zählung konnte in diesem Lauf nicht rechnen ({s['fehler']}). Der Kombinierer oben ist davon "
                       "nicht betroffen.", ""]
    z = kopf + [s["satz"], "",
                "Gold-Bot C/B und Pine-K5 zusammen auf einem gedachten Konto mit 1.000 €, jeder Trade mit der doppelten "
                f"Größe des Demo-Trades. Gezählt wird ab dem {_datum(s['start_utc'])} um "
                f"{pd.Timestamp(s['start_utc']).strftime('%H.%M')} Uhr UTC. Ein Trade zählt nur, wenn sein Sicherheitsgeld "
                "noch auf das Konto passt. Liegt das Konto 30 % unter seinem Höchststand, ist die Zählung beendet. Die "
                "Regeln stehen in suche/VORAB_gold_duo_doppelt.yaml. Nur Demokonten, nur Auskunft, kein Bot liest diese "
                "Zahlen.", "",
                "| Trades gezählt | verpasst | noch offen | Summe | Kontostand | größter Rückgang | größtes Sicherheitsgeld "
                "| Gewinnfaktor | Tage | Urteil |", "|---|---|---|---|---|---|---|---|---|---|"]
    vp = ", ".join(f"{GRUND.get(a, a)} {n}" for a, n in s["verpasst"].items()) or "–"
    pf = "–" if s["pf"] is None else _komma(s["pf"])
    z += [f"| {s['trades']} | {vp} | {s['offen']} | {_eur(s['summe_eur'])} | {_eur(s['endstand_eur']).lstrip('+')} | "
          f"{_eur(-s['groesster_rueckgang_eur'])} | {_eur(s['groesste_margin_eur']).lstrip('+')} | {pf} | "
          f"{s['tage']} von {s['regel']['mindestens_tage']} | {STATUS[s['urteil']['status']]} |", "",
          f"Stand des Urteils. {s['urteil']['text'][0].upper()}{s['urteil']['text'][1:]}.", ""]
    if s["monate"]:
        z += ["| Monat | Trades | Summe | Rendite pro Monat |", "|---|---|---|---|"]
        z += [f"| {m} | {x['trades']} | {_eur(x['eur'])} | {_komma(x['pct'], 1)} % |" for m, x in s["monate"].items()]
        z.append("")
    if s["trades"]:
        r, jb = s["richtung"], s["je_bot"]
        teile = [f"Verkäufe brachten {_eur(r['verkauf']['eur'])} aus {r['verkauf']['trades']} Trades, Käufe "
                 f"{_eur(r['kauf']['eur'])} aus {r['kauf']['trades']} Trades.",
                 " ".join(f"{NAMEN.get(bot, bot)} brachte {_eur(x['eur'])} aus {x['trades']} Trades." for bot, x in jb.items())]
        if s["ohne_zwei_beste_tage_eur"] is not None:
            teile.insert(0, f"Ohne die zwei besten Tage läge die Summe bei {_eur(s['ohne_zwei_beste_tage_eur'])}.")
        z += ["Auskunft ohne Einfluss auf das Urteil. " + " ".join(teile), ""]
    return z


def stand(now: datetime | None = None, root: pathlib.Path = ROOT, g: dict | None = None) -> dict | None:
    """Der Stand der Zählung, None ohne gültiges Siegel."""
    g = g or regel()
    if g is None:
        return None
    now = now or datetime.now(timezone.utc)
    tag = pd.Timestamp(now.astimezone(timezone.utc).date())
    tage = max((tag.date() - pd.Timestamp(g["start_utc"]).date()).days, 0)
    e = zaehlen(trades(g, root), g)
    out = {"format": 1, "start_utc": g["start_utc"], "topf_eur": g["konto"]["topf_eur"],
           "einsatz_faktor": g["konto"]["einsatz_faktor"], "tage": tage,
           "regel": {a: g["urteil"][a] for a in ("ab_trades", "mindestens_tage", "pf_mindestens")},
           **kennzahlen(e, g), **{a: e[a] for a in ("offen", "verpasst", "summe_eur", "endstand_eur",
                                                    "groesster_rueckgang_eur", "groesste_margin_eur", "bremse_seit")},
           "urteil": urteil(e, g["urteil"], tage, tag, g["konto"]["bremse_pct"])}
    out["satz"] = satz(out)
    return out


def main(argv: list[str]) -> int:
    s = stand()
    if s is None:
        print("Prüfsumme von VORAB_gold_duo_doppelt.yaml fehlt im Protokoll, das Gold-Duo zählt nicht.")
        return 0
    print("\n".join(abschnitt(s)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
