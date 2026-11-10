"""Gold-Staffel auf Account 1: dieselben Einstiege wie der Gold-Bot C/B, dazu gestaffelte Take-Profits mit Wächter
(nur Capital.com-DEMO).

Kirons Wort vom 10.11.2026 16:25 UTC (Take-Profits verteilt, nach TP1 wird TP1 der Ausstieg, TP2 etwa 70 bis 80 €, TP3
beim perfekten Kurs, ein Überprüfer gegen das Zurücklaufen ins Minus) und seine Wahl auf der Karte um 16:37 UTC: "Zweiter
Gold-Bot auf Account 1". Regel: suche/VORAB_gold_staffel.yaml, Rechnung suche/ergebnis_gold_staffel.md (2023-25 schlechter
als der Gold-Bot, geht trotzdem als Demo-Vorwärtstest live). Läuft im 5-Min.-Lauf (pine5m.yml).

- Einstieg: Öffnet der Gold-Bot auf dem Hauptkonto einen Trade (journal/gold-chart.json, Feld position), öffnet dieser
  Bot im nächsten Lauf dieselbe Richtung mit derselben Größe und demselben Stop auf Account 1. Nur Trades, die nach dem
  Start dieses Bots und höchstens 60 Min. vorher eröffnet wurden. 1 R = Abstand eigener Einstieg zu Stop.
- Staffel: TP1 +2 R, TP2 +4 R, TP3 +6 R als Take-Profit beim Broker. Wächter in jedem Lauf: Hat der Kurs seit dem
  Einstieg TP1 erreicht, kommt der Stop auf TP1, nach TP2 auf TP2. Nur nach vorn. Ist der Kurs schon zu nah am neuen
  Stop, schließt er sofort.
- Ausstieg wie beim Gold-Bot: Schließt der Gold-Bot seinen Trade (eigenes Ausstiegssignal), schließt dieser Bot seinen
  auch, wenn er dann noch offen ist.
- Der Gold-Bot selbst bleibt unverändert. Dieser Bot schreibt nur journal/gold-staffel/ und journal/gold-staffel.json.

Aufruf: python -m suche.gold_staffel_bot [--dry-run]
"""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import pathlib
import sys
from datetime import datetime, timezone

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_gold_staffel.yaml"
KEY = "VORAB_gold_staffel sha256 "
JOURNAL = ROOT / "journal"
BOT_ID = "gold-staffel"
NAME = "Gold-Staffel (TP 2/4/6 R mit Wächter)"
KONTO = "332263725196465310"            # Account 1 (dort handeln sonst nur die Scalper, kein Gold)
KONTO_NAME = "Account 1"
EPIC = "GOLD"
TP = (2.0, 4.0, 6.0)
KOPIER_FENSTER = pd.Timedelta(minutes=60)
LEBENSZEICHEN = pd.Timedelta(minutes=30)
REGEL = ("Gleiche Einstiege, Größe und Stop wie der Gold-Bot C/B auf dem Hauptkonto, dazu Take-Profits verteilt: "
         "TP1 +2 R, TP2 +4 R, TP3 +6 R beim Broker. Wächter alle 5 Minuten: nach TP1 kommt der Stop auf TP1, nach TP2 "
         "auf TP2, so endet ein Trade, der +2 R erreicht hat, nie mehr im Minus. Schließt der Gold-Bot, schließt er auch.")
TEST = ("Rechnung 2023-25 nur als Auskunft: +32,1 R statt +109,7 R beim Gold-Bot (GF 1,25 statt 1,69), 2026 -7,8 R "
        "statt +8,0 R, 2015-22 -99,6 R statt -199,5 R. Geht auf Kirons Wunsch trotzdem live (Vergleich nach 40 Trades).")


def vorab_ok() -> bool:
    from suche.runde1 import journal_lines, last_value, sha256_text
    return VORAB.exists() and last_value(journal_lines(), KEY) == sha256_text(VORAB.read_text(encoding="utf-8"))


def _num(x) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def _ts(x) -> pd.Timestamp | None:
    if not x:
        return None
    try:
        t = pd.Timestamp(str(x))
    except ValueError:
        return None
    return t.tz_convert("UTC").tz_localize(None) if t.tzinfo else t


def stufen(entry: float, dist: float, d: int) -> list[float]:
    """TP1, TP2, TP3 als Kurse."""
    return [round(entry + d * k * dist, 2) for k in TP]


def erreicht(tr: dict, bestes: float) -> int:
    """Höchste erreichte Stufe (0, 1 oder 2) bei diesem besten Kurs (Long: höchster Bid, Short: tiefster Ask)."""
    d, tp1, tp2 = int(tr["richtung"]), float(tr["tp"][0]), float(tr["tp"][1])
    if d * (bestes - tp2) >= 0:
        return 2
    if d * (bestes - tp1) >= 0:
        return 1
    return 0


def bester_kurs(tr: dict, raw5: list[dict], q, now: pd.Timestamp) -> float:
    """Bester Kurs seit dem Einstieg: fertige 5-Min.-Kerzen, die nach dem Einstieg begonnen haben, der Kurs jetzt und
    der beste Kurs aus früheren Läufen (die Kerzen reichen nur 25 Std. zurück)."""
    d, ab = int(tr["richtung"]), pd.Timestamp(tr["opened_utc"])
    werte = [q.bid if d > 0 else q.offer]
    if tr.get("bester") is not None:
        werte.append(float(tr["bester"]))
    for p in raw5:
        t = pd.Timestamp(p["snapshotTimeUTC"])
        if t >= ab and t + pd.Timedelta(minutes=5) <= now:
            x = _num((p["highPrice"] if d > 0 else p["lowPrice"]).get("bid" if d > 0 else "ask"))
            if x is not None:
                werte.append(x)
    return max(werte) if d > 0 else min(werte)


def gold_position() -> dict | None:
    """Offene Position des Gold-Bots laut journal/gold-chart.json (geschrieben stündlich vom Gold-Bot)."""
    p = JOURNAL / "gold-chart.json"
    with contextlib.suppress(OSError, ValueError):
        c = json.loads(p.read_text(encoding="utf-8"))
        pos = c.get("position")
        return {"stand": c.get("updated_utc"), "position": pos if isinstance(pos, dict) and pos.get("dealId") else None}
    return None


class Lauf:
    def __init__(self, client, st: dict | None, now: pd.Timestamp, send: bool):
        self.client, self.now, self.send = client, now, send
        self.st = {"format": 1, "offen": None, "kopiert": [], "trades": 0, "summe_r": 0.0, "summe_eur": 0.0,
                   **(st or {})}
        self.st.setdefault("start", now.strftime("%Y-%m-%dT%H:%M:%S"))
        self.log: list[dict] = []
        self.fertige: list[dict] = []
        self.stamp = now.strftime("%Y-%m-%dT%H:%M:%S")

    def ev(self, event: str, **kw) -> None:
        self.log.append({"time": self.stamp, "bot": BOT_ID, "event": event, **kw})

    def eur(self, tr: dict, level: float, q) -> float | None:
        if not q or not q.eur_rate:
            return None
        return tr["richtung"] * (level - tr["entry"]) * tr["size"] * (q.lot or 1.0) / q.eur_rate

    def buche(self, tr: dict, level: float | None, quelle: str, q) -> None:
        rec = {**tr, "exit": None if level is None else round(level, 2), "quelle": quelle, "closed_utc": self.stamp}
        if level is not None and tr.get("dist"):
            rec["r"] = round(tr["richtung"] * (level - tr["entry"]) / tr["dist"], 3)
            self.st["summe_r"] = round(float(self.st["summe_r"]) + rec["r"], 3)
            e = self.eur(tr, level, q)
            rec["pnl_eur"] = None if e is None else round(e, 2)
            self.st["summe_eur"] = round(float(self.st["summe_eur"]) + float(rec["pnl_eur"] or 0), 2)
        self.st["trades"] = int(self.st["trades"]) + 1
        self.st["offen"] = None
        self.fertige.append(rec)
        self.ev("Trade zu", dealId=tr["dealId"], kurs=rec["exit"], r=rec.get("r"), eur=rec.get("pnl_eur"),
                quelle=quelle, stufe=tr.get("stufe", 0))

    def schliessen(self, q, quelle: str) -> bool:
        tr = self.st["offen"]
        if not self.send:
            self.ev("würde schließen", dealId=tr["dealId"], quelle=quelle)
            return False
        try:
            conf = self.client.close_position(tr["dealId"])
        except Exception as err:            # noqa: BLE001 - nächster Lauf versucht es wieder
            self.ev("schließen fehlgeschlagen", dealId=tr["dealId"], quelle=quelle, fehler=str(err)[:200])
            return False
        if str((conf or {}).get("dealStatus") or "").upper() == "REJECTED":
            self.ev("schließen abgelehnt", dealId=tr["dealId"], quelle=quelle, grund=(conf or {}).get("reason"))
            return False
        level = _num((conf or {}).get("level")) or (q.bid if tr["richtung"] > 0 else q.offer)
        self.buche(tr, level, quelle, q)
        return True

    # ---- Broker hat geschlossen (Stop, Wächter-Stop oder TP3) ----
    def abgleich(self, positionen: list[dict], q) -> None:
        from suche.demo_bots import broker_exit
        tr = self.st["offen"]
        if not tr or tr["dealId"] in {str(p["position"].get("dealId")) for p in positionen}:
            return
        level, quelle = broker_exit(self.client, {"dealId": tr["dealId"], "opened_utc": tr["opened_utc"]},
                                    self.now.to_pydatetime())
        quelle, stufe = str(quelle or "").upper(), int(tr.get("stufe", 0))
        if level is None:                    # Kontoaktivität nicht lesbar: der Stop von zuletzt als Schätzung
            name, level = ("Wächter-Stop TP%d" % stufe if stufe else "Stop") + " (geschätzt)", float(tr["stop"])
        elif quelle == "TP" or tr["richtung"] * (level - tr["tp"][2]) >= 0:
            name = "TP3"
        elif quelle == "USER":
            name = "von Hand geschlossen"
        elif quelle == "CLOSE_OUT":
            name = "Zwangsschließung (zu wenig Margin)"
        else:
            name = "Wächter-Stop TP%d" % stufe if stufe else "Stop"
        self.buche(tr, level, name, q)

    # ---- Wächter: Stop auf TP1 bzw. TP2 nachziehen ----
    def waechter(self, q, raw5: list[dict]) -> None:
        tr = self.st["offen"]
        if not tr:
            return
        bestes = bester_kurs(tr, raw5, q, self.now)
        tr["bester"] = round(bestes, 2)
        ziel = erreicht(tr, bestes)
        if ziel <= int(tr.get("stufe", 0)):
            return
        d, neu = int(tr["richtung"]), float(tr["tp"][ziel - 1])
        kurs = q.bid if d > 0 else q.offer
        abstand = max(1.05 * (q.min_dist or 0.0), 0.01)
        if d * (kurs - neu) <= abstand:
            self.ev("Wächter schließt", dealId=tr["dealId"], stufe=ziel, stop=neu, kurs=kurs)
            self.schliessen(q, f"Wächter TP{ziel} (Kurs schon zu nah)")
            return
        body = {"stopLevel": round(neu, 2), "profitLevel": round(float(tr["tp"][2]), 2)}
        if not self.send:
            self.ev("würde nachziehen", dealId=tr["dealId"], stufe=ziel, **body)
            return
        try:
            ref = self.client._request("PUT", f"/positions/{tr['dealId']}", json=body).json().get("dealReference")
            conf = self.client.confirm(ref) if ref else {}
        except Exception as err:            # noqa: BLE001 - nächster Lauf versucht es wieder
            self.ev("nachziehen fehlgeschlagen", dealId=tr["dealId"], stufe=ziel, fehler=str(err)[:200])
            return
        if str((conf or {}).get("dealStatus") or "").upper() == "REJECTED":
            self.ev("nachziehen abgelehnt", dealId=tr["dealId"], stufe=ziel, grund=(conf or {}).get("reason"))
            return
        tr["stufe"], tr["stop"] = ziel, body["stopLevel"]
        self.ev("Wächter zieht nach", dealId=tr["dealId"], stufe=ziel, stop=body["stopLevel"])

    # ---- Gold-Bot zu: auch schließen ----
    def gold_zu(self, gold: dict | None, q) -> None:
        tr = self.st["offen"]
        if not tr or gold is None:
            return
        stand = _ts(gold.get("stand"))
        if stand is None or stand <= pd.Timestamp(tr["opened_utc"]):
            return                           # Gold-Bot-Stand älter als unser Einstieg: noch nichts zu sagen
        pos = gold.get("position")
        if pos and str(pos.get("dealId")) == tr["gold_deal"]:
            return
        self.ev("Gold-Bot hat geschlossen", gold_deal=tr["gold_deal"])
        self.schliessen(q, "Gold-Bot zu")

    # ---- Einstieg: Trade des Gold-Bots kopieren ----
    def einstieg(self, gold: dict | None, q, available: float, positionen: list[dict]) -> None:
        if self.st["offen"] or gold is None or not gold.get("position"):
            return
        pos = gold["position"]
        deal = str(pos.get("dealId"))
        if deal in self.st["kopiert"]:
            return
        auf = _ts(pos.get("opened_utc"))
        if auf is None or auf < pd.Timestamp(self.st["start"]) or self.now - auf > KOPIER_FENSTER:
            self.st["kopiert"] = (self.st["kopiert"] + [deal])[-20:]
            self.ev("Gold-Trade nicht kopiert", gold_deal=deal,
                    warum="vor dem Start dieses Bots" if auf is not None and auf < pd.Timestamp(self.st["start"])
                    else "zu alt (mehr als 60 Min.)")
            return
        self.st["kopiert"] = (self.st["kopiert"] + [deal])[-20:]
        if positionen:
            self.ev("Gold schon offen auf Account 1, nichts kopiert", gold_deal=deal)
            return
        d = 1 if str(pos.get("side") or pos.get("direction", "")).lower() in ("long", "buy") else -1
        stop, size = _num(pos.get("stop")), _num(pos.get("size"))
        if stop is None or not size:
            self.ev("Gold-Trade ohne Stop oder Größe, nichts kopiert", gold_deal=deal)
            return
        if not q.tradeable:
            self.ev("Markt zu", gold_deal=deal)
            self.st["kopiert"].remove(deal)  # nächster Lauf versucht es wieder (innerhalb der 60 Min.)
            return
        kurs = q.offer if d > 0 else q.bid
        dist = d * (kurs - stop)
        if dist <= 0:
            self.ev("Kurs schon hinter dem Stop, nichts kopiert", gold_deal=deal, kurs=kurs, stop=stop)
            return
        marge = size * (q.lot or 1) * kurs * q.margin_pct / 100 / (q.eur_rate or 1)
        if marge > 0.8 * available:
            self.ev("zu wenig Margin", gold_deal=deal, marge=round(marge, 2), frei=round(available, 2))
            return
        tp = stufen(kurs, dist, d)
        body = {"epic": EPIC, "direction": "BUY" if d > 0 else "SELL", "size": size, "guaranteedStop": False,
                "stopLevel": round(stop, 2), "profitLevel": tp[2]}
        info = {"gold_deal": deal, "richtung": d, "size": size, "stop": body["stopLevel"], "tp": tp}
        if not self.send:
            self.ev("würde öffnen", **info, kurs=kurs)
            return
        try:
            ref = self.client._request("POST", "/positions", json=body).json()["dealReference"]
            conf = self.client.confirm(ref)
        except Exception as err:            # noqa: BLE001 - kein zweiter Versuch, damit nichts doppelt entsteht
            self.ev("Order fehlgeschlagen", **info, fehler=str(err)[:200])
            return
        if str((conf or {}).get("dealStatus") or "").upper() == "REJECTED":
            self.ev("Order abgelehnt", **info, grund=(conf or {}).get("reason"))
            return
        mein = str(((conf or {}).get("affectedDeals") or [{}])[0].get("dealId") or (conf or {}).get("dealId"))
        level = _num((conf or {}).get("level")) or kurs
        dist = abs(level - stop)
        self.st["offen"] = {"dealId": mein, "gold_deal": deal, "richtung": d, "size": size, "entry": round(level, 2),
                            "stop": round(stop, 2), "dist": round(dist, 4), "tp": stufen(level, dist, d)[:2] + [tp[2]],
                            "stufe": 0, "opened_utc": self.stamp}
        self.ev("eröffnet", **info, dealId=mein, entry=round(level, 2))


def lauf(client, st: dict | None, now: pd.Timestamp, available: float, send: bool, gold: dict | None) -> Lauf:
    from suche.demo_bots import eur_rate, quote_from_market
    lf = Lauf(client, st, now, send)
    q = quote_from_market(client.market(EPIC), None)
    q.eur_rate = eur_rate(client, q.currency, {})
    positionen = [p for p in client.positions() if (p.get("market") or {}).get("epic") == EPIC]
    lf.abgleich(positionen, q)
    if lf.st["offen"]:
        raw5 = client.prices(EPIC, "MINUTE_5", 300)
        lf.waechter(q, raw5)
    if lf.st["offen"]:
        lf.gold_zu(gold, q)
    if lf.st["offen"] is None:
        if any(e["event"] == "Trade zu" for e in lf.log):
            positionen = [p for p in client.positions() if (p.get("market") or {}).get("epic") == EPIC]
        lf.einstieg(gold, q, available, positionen)
    lf.st["stand"] = lf.stamp
    return lf


def run(client, st: dict | None, now: datetime, send: bool = True, gold: dict | None = None) -> Lauf:
    nowts = pd.Timestamp(now).tz_convert("UTC").tz_localize(None) if pd.Timestamp(now).tzinfo else pd.Timestamp(now)
    if not vorab_ok():
        lf = Lauf(client, st, nowts, send)
        lf.ev("Regeln nicht versiegelt, nichts getan")
        return lf
    konto = next((a for a in client.accounts() if str(a.get("accountId")) == KONTO), None)
    if konto is None:
        lf = Lauf(client, st, nowts, send)
        lf.ev("kein Konto", konto="…" + KONTO[-4:])
        return lf
    available = float(_num((konto.get("balance") or {}).get("available")) or 0)
    vorher = client.account_id
    client.switch_account(KONTO)
    try:
        aktiv = None
        with contextlib.suppress(Exception):
            aktiv = str((client._get("/session") or {}).get("accountId") or "") or None
        if aktiv is not None and aktiv != KONTO:
            lf = Lauf(client, st, nowts, send)
            lf.ev("anderes Konto aktiv, nichts getan", aktiv="…" + aktiv[-4:])
            return lf
        try:
            return lauf(client, st, nowts, available, send, gold)
        except Exception as err:             # noqa: BLE001 - die anderen Bots im Lauf laufen weiter
            lf = Lauf(client, st, nowts, send)
            lf.ev("Fehler", fehler=f"{type(err).__name__}: {err}"[:300])
            return lf
    finally:
        with contextlib.suppress(Exception):
            if vorher and vorher != KONTO:
                client.switch_account(vorher)


def zusammenfassung(st: dict, alle: list[dict]) -> dict:
    r = [t["r"] for t in alle if t.get("r") is not None]
    g, v = sum(x for x in r if x > 0), -sum(x for x in r if x < 0)
    return {"trades": int(st.get("trades") or 0), "pf_r": (round(g / v, 2) if v > 0 else None),
            "summe_r": st.get("summe_r"), "summe_eur": st.get("summe_eur"),
            "urteil": "Demo-Vorwärtstest, Vergleich mit dem Gold-Bot nach 40 Trades"}


def _ohne_stand(st: dict) -> dict:
    """Zustand ohne Uhrzeit und ohne besten Kurs (der ändert sich fast jeden Lauf und ist nur die Reserve)."""
    s = {k: v for k, v in st.items() if k != "stand"}
    if isinstance(s.get("offen"), dict):
        s["offen"] = {k: v for k, v in s["offen"].items() if k != "bester"}
    return s


def status(st: dict) -> str:
    """Eine Zeile für das Cockpit."""
    o = st.get("offen")
    if not isinstance(o, dict):
        return "wartet auf den nächsten Trade des Gold-Bots"
    seite = "Long" if int(o.get("richtung") or 1) > 0 else "Short"
    tp = o.get("tp") or [None]
    if o.get("stufe"):
        return f"{seite} offen, Wächter hat den Stop auf TP{o['stufe']} gezogen ({o.get('stop')})"
    return f"{seite} offen, Stop {o.get('stop')}, TP1 bei {tp[0]}"


def schreiben(st: dict, log: list[dict], fertige: list[dict]) -> bool:
    """Nur eigene Dateien. Ohne Neues höchstens alle 30 Min. ein Lebenszeichen."""
    ordner = JOURNAL / BOT_ID
    alt = None
    with contextlib.suppress(OSError, ValueError):
        alt = json.loads((ordner / "state.json").read_text(encoding="utf-8"))
    wichtig = [e for e in log if not e["event"].startswith("würde ")]
    if (isinstance(alt, dict) and alt.get("stand") and st.get("stand") and not wichtig and not fertige
            and _ohne_stand(alt) == _ohne_stand(json.loads(json.dumps(st, default=str)))
            and pd.Timestamp(st["stand"]) - pd.Timestamp(alt["stand"]) < LEBENSZEICHEN):
        return False
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=1, default=str) + "\n",
                                       encoding="utf-8")
    for name, rows in (("log.jsonl", wichtig), ("trades.jsonl", fertige)):
        if rows:
            with open(ordner / name, "a", encoding="utf-8") as fh:
                fh.writelines(json.dumps(x, ensure_ascii=False, default=str) + "\n" for x in rows)
    p = ordner / "trades.jsonl"
    alle = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []
    karte = {"bot": BOT_ID, "name": NAME, "epic": EPIC, "konto": "…" + KONTO[-4:], "konto_name": KONTO_NAME,
             "stand": st.get("stand"), "start": st.get("start"), "status": status(st), "regel": REGEL, "vorab": "suche/VORAB_gold_staffel.yaml",
             "test": TEST, "offen": st.get("offen"), "zusammenfassung": zusammenfassung(st, alle),
             "letzte_trades": alle[-5:]}
    (JOURNAL / f"{BOT_ID}.json").write_text(json.dumps(karte, ensure_ascii=False, indent=1, default=str) + "\n",
                                            encoding="utf-8")
    return True


def main(argv: list[str]) -> int:
    from gold.bot.capital import CapitalClient
    from gold.bot.runner import CRED_KEYS, clean_credentials

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="nur rechnen, keine Order")
    args = ap.parse_args(argv)
    creds = clean_credentials({k: os.environ.get(k, "") for k in CRED_KEYS})
    if not all(creds):
        print("Keine Capital.com-Zugangsdaten, Gold-Staffel übersprungen")
        return 0
    p = JOURNAL / BOT_ID / "state.json"
    st = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    client = CapitalClient(*creds, environment="demo")
    client.login()
    try:
        lf = run(client, st, datetime.now(timezone.utc), send=not args.dry_run, gold=gold_position())
    finally:
        with contextlib.suppress(Exception):
            client.logout()
    print(BOT_ID, json.dumps({"ereignisse": lf.log, "fertig": lf.fertige, "offen": lf.st.get("offen")},
                             ensure_ascii=False, default=str))
    if not args.dry_run:
        schreiben(lf.st, lf.log, lf.fertige)
    return 1 if any(e["event"] == "Fehler" for e in lf.log) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
