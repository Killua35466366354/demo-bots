"""Schatten-Zwilling der Gold Groß-Box mit 1,25-fachem Stopabstand. Rechnet mit, sendet NIE eine Order.

    python -m gold.grossbox_zwilling        # holt Viertelstunden-Kerzen vom Capital.com-Demokonto, rechnet, schreibt das Journal

Kirons Wahl vom 19.11.2026 12:38 UTC ("Ja, als Schatten-Zwilling"). Regeln in suche/VORAB_gold_grossbox_weiter125.yaml,
Prüfsumme im Protokoll vor dem ersten Lauf, ohne passende Prüfsumme rechnet der Zwilling nichts. Eintrag in
suche/zwillinge.yaml, Urteil nach suche/VORAB_zwilling.yaml gegen das unveränderte Original gold-grossbox
(gold/grossbox_bot.py).

Das Modell ist genau gold/tiktok_schatten.gross_box mit kerze=False, nur der Stopabstand jedes Einstiegs (nach der Grenze
0,5 bis 3 ATR) ist 1,25-mal so groß. 1 R ist der neue Abstand, das erste Drittel geht bei 1 R, danach Einstand, der Rest
läuft bis zur neuen Box. tests/test_grossbox_zwilling.py prüft, dass das Modell mit Faktor 1,0 genau die Groß-Box ist.

Der Code ruft beim Broker nur Anmeldung, Kerzen und Abmeldung ab. Er schreibt nur journal/gold-grossbox-weiter125/ und
journal/gold-grossbox-weiter125.json.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from gold import tiktok_schatten as ts

ROOT = ts.ROOT
BOT_ID = "gold-grossbox-weiter125"
ORIGINAL = "gold-grossbox"
NAME = "Gold Groß-Box, Stop 1,25-fach (Schatten-Zwilling)"
FAKTOR = 1.25
PAUSE_R = -25.0                       # wie im Original
MIN_BARS, CHUNKS = 1200, 2            # wie das Original (gold/short_bot.py): 1.000 Kerzen plus 2 x 10 Tage
VORAB = ROOT / "suche" / "VORAB_gold_grossbox_weiter125.yaml"
KEY = "VORAB_gold_grossbox_weiter125 sha256 "
JDIR = ROOT / "journal" / BOT_ID
COCKPIT = ROOT / "journal" / f"{BOT_ID}.json"
ORIGINAL_TRADES = ROOT / "journal" / ORIGINAL / "trades.jsonl"
REGEL = ("Wie die Groß-Box (große Box aus 1-Std.-SuperTrend und 4-Std.-Strukturbruch, Einstiege nur in Boxrichtung, "
         "höchstens 3 offen, ein Drittel bei 1 R, dann Einstand, der Rest bis zur neuen Box), nur der Stop ist "
         "1,25-mal so weit weg. Schatten ohne Order.")
TEST = ("Versiegelter Test 11/2024 bis 10/2026: 856 Trades, GF 1,25 statt 1,21, +93,6 R statt +93,4 R, tiefster "
        "Rückgang 63,5 R statt 76,7 R. Gleicher Gewinn, ruhigerer Verlauf.")


def vorab_ok(lines: list[str] | None = None) -> bool:
    """Ist suche/VORAB_gold_grossbox_weiter125.yaml mit seiner Prüfsumme im Protokoll festgelegt?"""
    from suche.runde1 import journal_lines, last_value, sha256_text
    if not VORAB.exists():
        return False
    return last_value(lines if lines is not None else journal_lines(), KEY) == sha256_text(
        VORAB.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------------------------------------
# Das Modell

def gross_box_s(b: ts.Basis, m15: ts.Ebene, h1: ts.Ebene, h4: ts.Ebene, faktor: float = FAKTOR) -> list[dict]:
    """gold/tiktok_schatten.gross_box (kerze=False), nur der Stopabstand mal faktor. Mit faktor 1,0 genau das Original."""
    n = len(b)
    gd = ts.grosse_richtung(b, h1, h4)
    ende = ts.box_ende(gd)
    _, l1 = ts.supertrend(h1.h, h1.l, h1.c)
    kand = []                                         # (j0, art, d, gegen, atr, signalzeit)
    for j in range(1, n):
        if gd[j] == 0 or gd[j - 1] == gd[j]:
            continue
        i = int(np.searchsorted(h1.ende, b.t[j], side="right")) - 1
        if i < 0 or not np.isfinite(h1.atr[i]) or not np.isfinite(l1[i]):
            continue
        kand.append((j, "a", int(gd[j]), float(l1[i]), float(h1.atr[i]), str(pd.Timestamp(b.t[j]))))
    for art, sig in (("b", ts.st_signale(m15, ts.ST_FAKTOR_GENAUER)), ("c", ts.strukturbrueche(m15))):
        for x in sig:
            j0 = int(m15.i1[x.k]) + 1
            if j0 >= n or gd[j0] != x.d or not np.isfinite(m15.atr[x.k]):
                continue
            kand.append((j0, art, x.d, x.gegen, float(m15.atr[x.k]), str(pd.Timestamp(m15.ende[x.k]))))
    kand.sort(key=lambda x: (x[0], x[1]))
    out: list[dict] = []
    offen_bis: list[int] = []
    benutzt = -1
    for j0, art, d, gegen, a, sz in kand:
        if j0 == benutzt:
            continue
        offen_bis = [x for x in offen_bis if x >= j0]
        if len(offen_bis) >= ts.GROSS_MAX_OFFEN:
            continue
        jf = int(ende[j0])
        einstieg = float(b.o[j0] + b.sp[j0] if d > 0 else b.o[j0])
        roh = d * (einstieg - gegen) if np.isfinite(gegen) else 0.0
        dist = float(np.clip(roh, 0.5 * a, 3.0 * a)) * faktor
        stop = einstieg - d * dist
        teile, offen = ts.fuehre(b, d, j0, jf, einstieg, stop, *ts.LAUFEN, grund_ende="neue_box")
        res = ts.ergebnis_r(b, d, j0, einstieg, dist, teile, offen)
        letzt_j = max([t["j"] for t in teile], default=n - 1) if not offen else n - 1
        grund = "offen" if offen else max(teile, key=lambda t: t["j"])["grund"]
        ende_t = ts._zeit(b, letzt_j) if grund == "neue_box" else str(pd.Timestamp(b.t[letzt_j]) + pd.Timedelta("15min"))
        out.append({"signal": sz, "einstieg_zeit": ts._zeit(b, j0), "richtung": d, "art": art,
                    "einstieg": round(einstieg, 2), "stop": round(stop, 2), "tp1": round(einstieg + d * dist, 2),
                    "tp2": None, "tp3": None, "r_usd": round(dist, 2),
                    "teile": [{"grund": t["grund"], "px": round(t["px"], 2), "zeit": ts._zeit(b, t["j"]),
                               "anteil": round(t["w"], 3)} for t in teile],
                    "ergebnis_r": round(res, 3), "grund": grund, "ende": None if offen else ende_t, "offen": offen})
        offen_bis.append(n if offen else (letzt_j - 1 if grund == "neue_box" else letzt_j))
        benutzt = j0
    return out


def modell(b: ts.Basis, faktor: float = FAKTOR) -> list[dict]:
    """Das Modell auf fertigen Viertelstunden-Kerzen. 1-Std.- und 4-Std.-Kerzen nur, wenn sie fertig sind."""
    from gold import short_bot as sb
    m15 = ts.ebene(b, "15m")
    h1 = sb.fertig(ts.ebene(b, "1h"), b, "1h")
    h4 = sb.fertig(ts.ebene(b, "4h"), b, "4h")
    return gross_box_s(b, m15, h1, h4, faktor)


# --------------------------------------------------------------------------------------------------------------------
# Stand und Journal

def _iso(x) -> str | None:
    return None if x is None else pd.Timestamp(x).isoformat()


def zeile(t: dict) -> dict:
    """Ein fertiger Trade für journal/gold-grossbox-weiter125/trades.jsonl (Felder wie bei den anderen Bots)."""
    return {"bot": BOT_ID, "id": _iso(t["einstieg_zeit"]), "art": t["art"], "richtung": t["richtung"],
            "seite": "Kauf" if t["richtung"] > 0 else "Verkauf", "signal": t["signal"],
            "opened_utc": _iso(t["einstieg_zeit"]), "entry": t["einstieg"], "stop": t["stop"], "tp1": t["tp1"],
            "dist": t["r_usd"], "teile": t["teile"], "grund": t["grund"], "closed_utc": _iso(t["ende"]),
            "r": t["ergebnis_r"], "schatten": True}


def _lies(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def eintrag() -> dict:
    """Der Eintrag des Zwillings in suche/zwillinge.yaml (leer, wenn er fehlt)."""
    from suche import zwilling as zw
    return zw.eintraege().get(BOT_ID) or {}


def zwilling_stand(fertig: list[dict], e: dict, now: datetime, original: list[dict] | None = None) -> dict:
    """Stand nach suche/VORAB_zwilling.yaml (sammelt, früh beendet, reif, nicht besser, Frist, beendet)."""
    from suche import zwilling as zw
    rg = zw.regel()
    if rg is None or not e:
        return {"status": "keine_regel", "text": "VORAB_zwilling.yaml oder der Eintrag in suche/zwillinge.yaml fehlt"}
    start = str(e["start_utc"])
    org = [t for t in (original if original is not None else _lies(ORIGINAL_TRADES))
           if t.get("r") is not None and str(t.get("closed_utc") or "") >= start]
    return zw.stand(fertig, org, rg, start, now, e)


def step(bars: pd.DataFrame, spread: pd.Series, state: dict, now: datetime, e: dict,
         original: list[dict] | None = None) -> tuple[dict, list[dict], list[dict]]:
    """Rechnet das Modell aus den fertigen Kerzen neu und übernimmt nur Trades mit Einstieg ab start_utc.

    Rückgabe: neuer Zustand, neu fertige Trades (Zeilen für trades.jsonl), Ereignisse (log.jsonl). state["fertig"]
    hält die Einstiegszeiten der fertigen Trades, state["offen"] die offenen Trades des letzten Laufs. Ein Trade, der
    beim letzten Lauf nicht offen war und vor dem letzten fertigen beginnt, ist eine Neuberechnung und zählt nicht."""
    from suche import zwilling as zw
    b = ts.basis(bars, spread)
    st = dict(state)
    stamp = now.isoformat(timespec="seconds")
    start = pd.Timestamp(e["start_utc"]).tz_localize(None) if pd.Timestamp(e["start_utc"]).tzinfo else pd.Timestamp(
        e["start_utc"])
    bekannt = set(st.get("fertig") or [])
    alt_offen = {t["einstieg_zeit"] for t in st.get("offen") or []}
    alle_fertig = [t for t in st.get("trades") or []]
    summe = float(sum(t["r"] for t in alle_fertig))
    letzte = max((pd.Timestamp(t["opened_utc"]) for t in alle_fertig), default=None)
    stand = zwilling_stand(alle_fertig, e, now, original)
    darf_neu = zw.offen(stand) and summe > PAUSE_R
    neu_fertig, events, offen = [], [], []
    for t in modell(b):
        tin = pd.Timestamp(t["einstieg_zeit"])
        if tin < start or t["einstieg_zeit"] in bekannt:
            continue
        if letzte is not None and tin <= letzte and t["einstieg_zeit"] not in alt_offen:
            continue
        if t["einstieg_zeit"] not in alt_offen and not darf_neu:
            continue                                  # nichts Neues mehr (Zwilling-Regel oder -25 R)
        if t["offen"]:
            offen.append({k: v for k, v in t.items() if not k.startswith("_")})
            if t["einstieg_zeit"] not in alt_offen:
                events.append({"time": stamp, "event": "einstieg", **{k: t[k] for k in (
                    "einstieg_zeit", "richtung", "art", "einstieg", "stop", "tp1", "r_usd")}})
        else:
            z = zeile(t)
            neu_fertig.append(z)
            bekannt.add(t["einstieg_zeit"])
            events.append({"time": stamp, "event": "fertig", **{k: z[k] for k in (
                "opened_utc", "richtung", "entry", "grund", "closed_utc", "r")}})
    alle_fertig = alle_fertig + neu_fertig
    st.update({"format": 1, "bot": BOT_ID, "start": str(e["start_utc"]), "fertig": sorted(bekannt),
               "trades": alle_fertig, "offen": offen, "letzte_kerze": str(pd.Timestamp(b.t[-1])), "stand": stamp,
               "summe_r": round(float(sum(t["r"] for t in alle_fertig)), 3),
               "zwilling": zwilling_stand(alle_fertig, e, now, original), "neue_trades": darf_neu})
    return st, neu_fertig, events


def zusammenfassung(trades: list[dict], stand: dict) -> dict:
    r = [float(t["r"]) for t in trades]
    n = len(r)
    return {"trades": n, "pf_r": ts.pf(r), "summe_r": round(float(sum(r)), 2),
            "trefferquote": round(sum(x > 0 for x in r) / n, 3) if n else None, "summe_eur": None,
            "urteil": stand.get("text") or stand.get("status")}


def cockpit(st: dict) -> dict:
    trades = st.get("trades") or []
    return {"bot": BOT_ID, "name": NAME, "konto": "Schatten (keine Order)", "original": ORIGINAL, "stand": st.get("stand"),
            "start": st.get("start"), "status": "rechnet mit" if st.get("neue_trades") else "keine neuen Trades",
            "regel": REGEL, "backtest": TEST, "vorab": str(VORAB.relative_to(ROOT)), "vorab_ok": True,
            "offen": st.get("offen") or [], "zusammenfassung": zusammenfassung(trades, st.get("zwilling") or {}),
            "zwilling": st.get("zwilling"), "letzte_trades": trades[-10:],
            "hinweis": "Nur Schatten, keine Order. Kosten aus den Kerzen, nicht live geprüft."}


def schreiben(st: dict, neu: list[dict], events: list[dict], jdir: Path = JDIR, cockpit_pfad: Path = COCKPIT) -> None:
    jdir.mkdir(parents=True, exist_ok=True)
    (jdir / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for name, rows in (("trades.jsonl", neu), ("log.jsonl", events)):
        if rows:
            with open(jdir / name, "a", encoding="utf-8") as fh:
                fh.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    cockpit_pfad.write_text(json.dumps(cockpit(st), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    from gold.bot.capital import CapitalClient
    from gold.bot.rules import bars_from_prices
    from gold.bot.runner import CRED_KEYS, clean_credentials

    if not vorab_ok():
        print("VORAB_gold_grossbox_weiter125.yaml passt nicht zur Prüfsumme im Protokoll, der Zwilling rechnet nichts")
        return 0
    e = eintrag()
    if not e.get("start_utc"):
        print(f"{BOT_ID} fehlt in suche/zwillinge.yaml, der Zwilling rechnet nichts")
        return 0
    creds = clean_credentials({k: os.environ.get(k, "") for k in CRED_KEYS})
    if not all(creds):
        print("Keine Capital.com-Zugangsdaten, Groß-Box-Zwilling übersprungen")
        return 0
    path = JDIR / "state.json"
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    now = datetime.now(timezone.utc)
    client = CapitalClient(*creds, environment="demo")
    client.login()
    try:
        bars, spread = bars_from_prices(ts.fetch_candles(client, ts.EPIC, chunks=CHUNKS), now, "15min")
    finally:
        try:
            client.logout()
        except Exception:               # noqa: BLE001 - Abmelden ist nur Ordnung
            pass
    if len(bars) < MIN_BARS:
        print(f"Nur {len(bars)} Viertelstunden-Kerzen, der Zwilling braucht {MIN_BARS}; nichts geschrieben")
        return 0
    if state.get("letzte_kerze") and pd.Timestamp(state["letzte_kerze"]) >= bars.index[-1]:
        print(f"Kerze {bars.index[-1]} ist schon verarbeitet")
        return 0
    st, neu, events = step(bars, spread, state, now, e)
    schreiben(st, neu, events)
    print(json.dumps({"zwilling": st["zwilling"], "offen": len(st["offen"]), "neu_fertig": neu, "ereignisse": events},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
