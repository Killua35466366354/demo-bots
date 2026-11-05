"""Wochen-Test aller Bots auf Capital.com (Demo): kurzer Stand für das 12-Stunden-Update an Kiron.

    python -m suche.wochenbericht                         # Text (Markdown) für die Nachricht
    python -m suche.wochenbericht --seit 2026-11-03T19:00 # dazu: was seit diesem Zeitpunkt (UTC) passiert ist
    python -m suche.wochenbericht --json                  # dieselben Zahlen als JSON (für das Cockpit)

Kirons Wunsch vom 03.11.2026: alle Bots eine Woche live auf dem Capital.com-Demokonto, jeder auf einem eigenen Konto,
alle 12 Stunden ein Update mit kurzer Analyse. Liest nur Dateien aus dem Repo (Journal und Einstellungen), ändert nichts
und spricht mit keinem Broker:
- Gold-Bot C und B: journal/gold-trades.jsonl, journal/gold-chart.json (offene Position), Hauptkonto
- Gold-Bot 2.0 und die 5 Test-Bots: journal/demo-bots.json, journal/demo-bots/trades.jsonl
- Konten: journal/konten.json (gold/bot/konten.py); Gold-Bot 2.0 im Schatten: journal/gold2-schatten.json

Erwartung je Woche = Backtest-Trades und Summe R über 35 Wochen (März bis Oktober 2026, Runde 3), nur als Maßstab.
Eine Woche ist viel zu kurz, um daraus etwas zu schließen; der Bericht sagt das auch so.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
J = ROOT / "journal"
BERLIN = ZoneInfo("Europe/Berlin")
WOCHEN_BT = 35.0                         # März bis Oktober 2026
CHART = {"15min": "15-Min.", "30min": "30-Min.", "60min": "1-Std."}
# Gold-Bot C und B so, wie er jetzt handelt (Stop 1 x ATR, Ausstieg auf eigenes Signal): Runde 3, GOLD 60 Min., C+B
GOLD_REF = {"trades": 60, "pf_r": 1.09, "win_pct": 23.3, "sum_r": 4.1}
# Der Gold-Bot handelt seit dem 31.10.2026 auf dem Demo-Hauptkonto (gold/bot/konten.py), also schon vor dem Wochen-Test.
# Er zählt alle seine Demo-Trades, sonst stünde dort "0 Trades", obwohl er einen hatte (Kritik D7 vom 05.11.2026).
GOLD_DEMO_START = pd.Timestamp("2026-10-31 12:00:00")
# Bots aus anderen Runden, die seit Kirons Wunsch vom 04.11.2026 ("alle Strategien gleich auswerten, dann wählen",
# suche/VORAB_bewertung.yaml) die Konten abgelöster Wochen-Test-Bots bekommen: (Bot-ID, Name, Markt, Chart,
# Cockpit-Datei, Trade-Datei). Im Bericht stehen sie, sobald sie ein Konto haben.
WEITERE = [
    ("us500-ruecksetzer", "Trend-Rücksetzer US500", "US500", "Tag", "us500-bot.json", "us500-bot/trades.jsonl"),
    ("r5-ruecksetzer-us100", "Trend-Rücksetzer US100", "US100", "Tag", "us100-ruecksetzer.json",
     "us100-ruecksetzer/trades.jsonl"),
    ("r5-ruecksetzer-us30", "Trend-Rücksetzer Dow", "US30", "Tag", "us30-ruecksetzer.json", "us30-ruecksetzer/trades.jsonl"),
    ("r7-nasdaq-noise-long", "Nasdaq Noise Long", "US100", "30-Min.", "r7-nasdaq-bot.json", "r7-nasdaq-bot/trades.jsonl"),
    ("r6-vortag-usdjpy", "Vortag USD/JPY", "USDJPY", "15-Min.", "r6-bots.json", "r6-bots/trades.jsonl"),
    ("r6-london-gbpusd", "London GBP/USD", "GBPUSD", "15-Min.", "r6-bots.json", "r6-bots/trades.jsonl"),
    ("r6-noise-usdjpy", "Noise USD/JPY", "USDJPY", "15-Min.", "r6-bots.json", "r6-bots/trades.jsonl"),
    ("r6-vortag-eurusd", "Vortag EUR/USD", "EURUSD", "15-Min.", "r6-bots.json", "r6-bots/trades.jsonl"),
    ("r6-vortag-gbpusd", "Vortag GBP/USD", "GBPUSD", "15-Min.", "r6-bots.json", "r6-bots/trades.jsonl"),
    ("r6-vortag-gbpjpy", "Vortag GBP/JPY", "GBPJPY", "15-Min.", "r6-bots.json", "r6-bots/trades.jsonl"),
    ("r6-vortag-eurusd-1atr", "Vortag EUR/USD 1 x ATR (Mess-Bot)", "EURUSD", "15-Min.", "r6-bots.json",
     "r6-bots/trades.jsonl"),
]


def weitere_bots(kont: dict) -> list[dict]:
    """Die Bots aus WEITERE, die laut journal/konten.json ein Konto haben, im selben Format wie die übrigen."""
    zu, start = kont.get("zuordnung") or {}, kont.get("start") or {}
    out = []
    for bid, name, markt, chart, datei, tdatei in WEITERE:
        aid = zu.get(bid)
        if not aid:
            continue
        cp = _read(J / datei, {})
        if isinstance(cp.get("bots"), list):                 # Runde-6-Datei: eine Karte je Bot
            cp = next((b for b in cp["bots"] if b.get("bot") == bid), {})
        mine = [{"r": t.get("r"), "eur": t.get("pnl_eur"), "side": t.get("side"), "zu": t.get("closed_utc"),
                 "auf": t.get("opened_utc"), "grund": t.get("reason"), "entry": t.get("entry"), "exit": t.get("exit")}
                for t in _lines(J / tdatei) if t.get("bot") in (bid, None)]
        bal, st0 = cp.get("kontostand"), start.get(str(aid))
        pos = cp.get("position")
        out.append({"id": bid, "name": name, "markt": markt, "chart": chart, "seiten": "",
                    "konto": {"id": "…" + str(aid)[-4:], "name": cp.get("konto_name"), "eigen": True, "balance": bal,
                              "start": st0, "seit_start": None if bal is None or st0 is None
                              else round(float(bal) - float(st0), 2)},
                    "status": cp.get("status") or "startet beim nächsten Lauf",
                    "position": None if not pos else {"side": pos.get("side"), "entry": pos.get("entry"),
                                                      "stop": pos.get("stop") or pos.get("stop_level"),
                                                      "upl": pos.get("upl"), "opened_utc": pos.get("opened_utc")},
                    "live": _stats(mine), "trades": mine, "ref": None})
    return out


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except (OSError, ValueError):
        return default


def _lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for x in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(x))
        except ValueError:
            continue
    return out


def _ts(text) -> pd.Timestamp | None:
    if not text:
        return None
    t = pd.Timestamp(str(text).replace("Z", ""))
    return t.tz_convert("UTC").tz_localize(None) if t.tzinfo else t


def _berlin(t: pd.Timestamp | None, fmt: str = "%a %d.%m. %H:%M") -> str:
    if t is None:
        return "–"
    tage = {"Mon": "Mo", "Tue": "Di", "Wed": "Mi", "Thu": "Do", "Fri": "Fr", "Sat": "Sa", "Sun": "So"}
    s = t.tz_localize("UTC").tz_convert(BERLIN).strftime(fmt)
    for en, de in tage.items():
        s = s.replace(en, de)
    return s


def _de(v: float | None, nd: int = 2, plus: bool = True) -> str:
    if v is None:
        return "–"
    s = f"{v:+.{nd}f}" if plus else f"{v:.{nd}f}"
    return s.replace(".", ",")


def _stats(trades: list[dict]) -> dict:
    r = [float(t["r"]) for t in trades if t.get("r") is not None]
    eur = [float(t["eur"]) for t in trades if t.get("eur") is not None]
    gw, vl = sum(x for x in r if x > 0), -sum(x for x in r if x <= 0)
    return {"trades": len(r), "gewonnen": sum(1 for x in r if x > 0), "sum_r": round(sum(r), 2),
            "pf_r": round(gw / vl, 2) if vl > 0 else None, "eur": round(sum(eur), 2) if eur else 0.0}


def _ref(bt: dict | None) -> dict | None:
    if not bt or not bt.get("trades"):
        return None
    n = float(bt["trades"])
    return {"trades_woche": round(n / WOCHEN_BT, 1), "r_woche": round(float(bt.get("sum_r") or 0) / WOCHEN_BT, 2),
            "r_je_trade": round(float(bt.get("sum_r") or 0) / n, 2), "pf_r": bt.get("pf_r"), "win_pct": bt.get("win_pct")}


def stand(now: datetime | None = None, seit: pd.Timestamp | None = None) -> dict:
    now_ts = _ts((now or datetime.now(timezone.utc)).isoformat())
    cfg = yaml.safe_load((ROOT / "suche" / "demo_bots.yaml").read_text(encoding="utf-8"))
    demo = _read(J / "demo-bots.json", {})
    kont = _read(J / "konten.json", {})
    start = _ts(demo.get("start_utc")) or pd.Timestamp("2026-11-03 07:14:21")
    ende = _ts(cfg.get("wochentest_ende_utc") or cfg.get("ende_utc") or demo.get("ende_utc"))
    bots = []

    # ---- Gold-Bot C und B auf dem Hauptkonto ----
    gt = [{"r": t.get("r"), "eur": t.get("pnl_eur"), "side": t.get("side"), "zu": t.get("closed_utc"),
           "auf": t.get("opened_utc"), "grund": t.get("reason"), "entry": t.get("entry"), "exit": t.get("exit")}
          for t in _lines(J / "gold-trades.jsonl")]
    gt = [t for t in gt if (_ts(t["zu"]) or start) >= GOLD_DEMO_START]   # Gold zählt alle seine Demo-Trades
    gc = _read(J / "gold-chart.json", {})
    pos = gc.get("position")
    haupt = next((k for k in kont.get("konten") or [] if k.get("fuer") == "gold"), None)
    h_start = (kont.get("start") or {}).get(str(kont.get("haupt"))) if kont.get("haupt") else None
    bots.append({"id": "gold", "name": "Gold C/B", "markt": "Gold", "chart": "1-Std., Demo seit 31.10.", "seiten": "C+B",
                 "konto": None if not haupt else {"id": haupt.get("id"), "name": haupt.get("name"), "eigen": False,
                                                  "balance": haupt.get("balance"), "start": h_start,
                                                  "seit_start": None if haupt.get("balance") is None or h_start is None
                                                  else round(float(haupt["balance"]) - float(h_start), 2)},
                 "status": "Position offen" if pos else "wartet auf Signal",
                 "position": None if not pos else {"side": pos.get("side"), "entry": pos.get("entry"),
                                                   "stop": pos.get("stop"), "upl": pos.get("upl")},
                 "live": _stats(gt), "trades": gt, "ref": _ref(GOLD_REF),
                 "stand_utc": gc.get("updated_utc")})

    # ---- Gold-Bot 2.0 und die Test-Bots (Lauf der Demo-Bots) ----
    dt = _lines(J / "demo-bots" / "trades.jsonl")
    by_id = {b.get("id"): b for b in demo.get("bots") or []}
    for b in list(cfg.get("bots") or []) + list(cfg.get("extra_bots") or []):
        d = by_id.get(b["id"], {})
        mine = [{"r": t.get("r"), "eur": t.get("pnl_eur"), "side": t.get("side"), "zu": t.get("closed_utc"),
                 "auf": t.get("opened_utc"), "grund": t.get("reason"), "entry": t.get("entry"), "exit": t.get("exit")}
                for t in dt if t.get("bot") == b["id"]]
        status = d.get("status") or ("wartet auf ein eigenes Demokonto" if b.get("eigenes_konto") else "startet beim nächsten Lauf")
        bots.append({"id": b["id"], "name": b["name"], "markt": b["epic"], "chart": CHART.get(b["zeitrahmen"], b["zeitrahmen"]),
                     "seiten": b["seiten"], "konto": d.get("konto"), "status": status, "position": d.get("position"),
                     "live": _stats(mine), "trades": mine, "ref": _ref(b.get("backtest"))})
    bots += weitere_bots(kont)
    schatten = _read(J / "gold2-schatten.json", {})
    st = [t for t in schatten.get("trades") or [] if (_ts(t.get("out")) or start) >= start]
    tage = max((now_ts - start).total_seconds() / 86400, 0.0)
    neu = []
    if seit is not None:
        for b in bots:
            for t in b["trades"]:
                if (_ts(t["zu"]) or pd.Timestamp.min) > seit:
                    neu.append({"bot": b["name"], "art": "zu", "zeit": t["zu"], "side": t["side"], "r": t["r"],
                                "eur": t["eur"], "grund": t["grund"]})
            p = b.get("position")
            auf = _ts((p or {}).get("opened_utc")) if p else None
            if p and auf and auf > seit:
                neu.append({"bot": b["name"], "art": "auf", "zeit": p.get("opened_utc"), "side": p.get("side"),
                            "entry": p.get("entry")})
        neu.sort(key=lambda e: str(e["zeit"]))
    alle = [t for b in bots for t in b["trades"]]
    return {"format": 1, "stand_utc": now_ts.isoformat(), "start_utc": start.isoformat(),
            "ende_utc": None if ende is None else ende.isoformat(), "tag": round(tage, 1),
            "gesamt": _stats(alle), "bots": bots, "neu": neu,
            "schatten_gold2": {"trades": len(st), "sum_r": round(sum(float(t["r"]) for t in st), 2)},
            "konten_eigen": sum(1 for b in bots if (b.get("konto") or {}).get("eigen")),
            "hinweis": "Demokonto (Spielgeld). Eine Woche ist zu kurz für ein Urteil; Erwartung = Backtest März bis Oktober 2026 je Woche."}


def text(s: dict) -> str:
    """Kurzer deutscher Stand als Markdown-Tabelle (eine Zeile je Bot)."""
    start, ende, now = (_ts(s.get(k)) for k in ("start_utc", "ende_utc", "stand_utc"))
    head = (f"**Wochen-Test (Demo)**, Stand {_berlin(now)} Uhr · Tag {_de(s['tag'], 1, False)} von 7 · "
            f"Ende {_berlin(ende)} Uhr")
    rows = ["| Bot (Chart) | Konto | Trades | Ergebnis | Erwartung/Woche | Jetzt |", "|---|---|---|---|---|---|"]
    for b in s["bots"]:
        k, L, R, p = b.get("konto") or {}, b["live"], b.get("ref") or {}, b.get("position")
        konto = "–" if not k else (("eigenes " if k.get("eigen") else "Haupt ") + (k.get("id") or "")
                                    + (f", {_de(k.get('seit_start'))} €" if k.get("eigen") and k.get("seit_start") is not None
                                       else ""))
        erg = "–" if not L["trades"] else f"{_de(L['sum_r'])} R · {_de(L['eur'])} €"
        tr = "0" if not L["trades"] else f"{L['trades']} ({L['gewonnen']} im Plus)"
        erw = "–" if not R else f"{_de(R['trades_woche'], 1, False)} Trades, {_de(R['r_woche'], 1)} R"
        jetzt = b["status"]
        if p:
            jetzt = f"{'Kauf' if p.get('side') == 'long' else 'Verkauf'} offen" + (
                f", {_de(p.get('upl'))} €" if p.get("upl") is not None else "")
        name = b["name"].split(" (")[0]
        rows.append(f"| {name} ({b['markt']} {b['chart']}) | {konto} | {tr} | {erg} | {erw} | {jetzt} |")
    g = s["gesamt"]
    out = [head, "", *rows, "",
           f"Zusammen: {g['trades']} Trades, {_de(g['sum_r'])} R, {_de(g['eur'])} € (Spielgeld)."]
    if s.get("neu"):
        out.append("Neu seit dem letzten Update: " + "; ".join(
            f"{e['bot']} {'Kauf' if e['side'] == 'long' else 'Verkauf'} "
            + (f"eröffnet zu {e.get('entry')}" if e["art"] == "auf" else f"zu ({e.get('grund')}), {_de(e.get('r'))} R")
            for e in s["neu"]) + ".")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seit", help="Zeitpunkt UTC des letzten Updates")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    s = stand(seit=_ts(a.seit) if a.seit else None)
    print(json.dumps(s, ensure_ascii=False, indent=1, default=str) if a.json else text(s))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
