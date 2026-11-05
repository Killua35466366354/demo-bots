"""Schattenlauf von Gold-Bot 2.0 neben dem Demo-Bot: rechnet jede Stunde mit, sendet NIE eine Order.

    python -m gold.v2.schatten          # holt Kerzen vom Capital.com-Demokonto, rechnet, schreibt das Journal

Kiron wollte 2.0 neben dem bestehenden Bot laufen sehen (02.11.2026). 2.0 hat Runde 3 NICHT bestanden
(gold/backtest/PROTOKOLL.md). Der Schattenlauf sammelt nur neue Daten nach dem 23.10.2026 und zählt nicht als
bestandener Test. Der Code kann keine Order senden: Er ruft beim Broker nur Anmeldung und Kerzen ab.

Regeln: genau die in Runde 3 gewählte Führung (Ziel 0,5 x ATR, höchstens 8 Stunden, Stop 1,5 x ATR, eigenes
Ausstiegssignal nur im Plus, raus bei Richtungswechsel und vor US-Terminen) und dieselben Filter. Jeder Lauf
rechnet einen offenen Schatten-Trade aus den Kerzen neu (gold.v2.fuehrung.manage), damit Backtest und Schattenlauf
denselben Code nutzen. Kurse und Spreads sind die echten der Demokerzen (Bid, Spread am Kerzenschluss).

Dateien (nur Journal, ändern nichts am Demo-Bot):
- journal/gold2-schatten.json: Stand, offener Trade, alle Schatten-Trades, Zusammenfassung (für das Cockpit)
- journal/gold2-schatten.jsonl: ein Ereignis je Zeile (Signal, gesperrt, Einstieg, Ausstieg)

ForexFactory (Kirons OK vom 02.11.2026): Der Wochenkalender wird nur mitgeschrieben. Bei jedem Signal steht dabei,
ob ein wichtiger US-Termin von dort die Pause ausgelöst hätte; im Stand stehen die nächsten Termine von dort und die,
die in gold/v2/termine.yaml fehlen. Entscheidungen ändert das nicht, weil es nicht getestet ist.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from gold.backtest.protocol import VORAB
from gold.backtest.runde2 import pf
from gold.backtest.runde3 import prepare, v2_fuehrung
from gold.v2 import news
from gold.v2.fuehrung import manage

ROOT = Path(__file__).resolve().parents[2]
STATE = "gold2-schatten.json"
LOG = "gold2-schatten.jsonl"
GEWAEHLT = (0.5, 8, "atr 1.5")          # Runde 3, Auswahl mit 2023-24 (PROTOKOLL.md)
KONTO_START, RISIKO_PCT = 250.0, 2.0    # Schattenkonto zum Anschauen, ohne Rundung auf 0,01 Unzen
MIN_BARS = 1300                         # 50 Handelstage für den Tagesdurchschnitt plus Vorlauf
CHUNK_DAYS = 40                         # weniger als 1.000 Stundenkerzen je Abruf
FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


def config() -> dict:
    return yaml.safe_load(VORAB.read_text(encoding="utf-8"))


def fuehrung(cfg: dict):
    return v2_fuehrung(cfg["runde_3"], *GEWAEHLT, True, True)


def fetch_candles(client, epic: str, chunks: int = 2) -> list[dict]:
    """Die letzten 1.000 Stundenkerzen und davor `chunks` Blöcke zu je 40 Tagen (Capital.com liefert höchstens
    1.000 je Abruf). Nur lesende Abrufe."""
    out = client.prices(epic, "HOUR", 1000)
    for _ in range(chunks):
        if not out:
            break
        first = min(pd.Timestamp(p["snapshotTimeUTC"]) for p in out)
        frm = first - pd.Timedelta(days=CHUNK_DAYS)
        older = client._get(f"/prices/{epic}", resolution="HOUR", max=1000,
                            **{"from": frm.strftime("%Y-%m-%dT%H:%M:%S"),
                               "to": first.strftime("%Y-%m-%dT%H:%M:%S")}).get("prices", [])
        out = older + out
    return out


def _r(side: int, p: dict, m, swap_pct: float) -> float:
    days = m.index.normalize()
    nights = int((days[p["t_out"]] - days[p["t_in"]]).days)
    swap = m.c[p["t_in"]] * swap_pct / 100 / 365 * nights
    return (side * (p["exit_px"] - p["entry_px"]) - swap) / p["risk_dist"]


def _blocked_why(P: dict, t: int, side: int) -> list[str]:
    why = []
    if P["richtung"][t] != side:
        why.append({1: "Markt-Richtung oben", -1: "Markt-Richtung unten", 0: "Markt-Richtung uneinig"}[int(P["richtung"][t])])
    if P["pause"][t]:
        why.append("Pause rund um einen US-Termin")
    if P["shock"][t]:
        why.append("Schock-Pause nach einer sehr großen Kerze")
    return why


def step(bars: pd.DataFrame, spread: pd.Series, state: dict, now: datetime, cfg: dict,
         ff: pd.DataFrame | None = None) -> tuple[dict, list[dict]]:
    """Verarbeitet alle fertigen Kerzen seit dem letzten Lauf. Reine Funktion ohne Netz (testbar).
    ff: ForexFactory-Termine (news.ff_events), nur zum Mitschreiben."""
    swap = cfg["kosten"]["swap_pct_jahr"]
    f = fuehrung(cfg)
    P = prepare(bars, cfg, spread)
    m, idx = P["m"], bars.index
    n = len(idx)
    st = dict(state)
    st.setdefault("trades", [])
    events: list[dict] = []
    stamp = now.isoformat(timespec="seconds")
    if not st.get("start"):                     # erster Lauf: ab jetzt, keine Rückrechnung
        st["start"] = str(idx[-1])
        st["cursor"] = str(idx[-1])
        events.append({"time": stamp, "event": "start", "bar": str(idx[-1])})
    pos_after = int(idx.searchsorted(pd.Timestamp(st["cursor"]), side="right"))
    long_in, short_in = P["entries"]["voll"]
    raw_l, raw_s = P["entries"]["roh"]
    t = pos_after
    while True:
        op = st.get("open")
        if op:
            ts = pd.Timestamp(op["t_sig"])
            if ts not in idx:
                events.append({"time": stamp, "event": "fehler", "why": f"Signalkerze {ts} fehlt in den Kerzen, Trade verworfen"})
                st["open"] = None
                continue
            side, t_sig = int(op["side"]), int(idx.get_loc(ts))
            p = manage(m, side, t_sig, f)
            if p is None or p["reason"] == "datenende":
                break                            # noch offen oder wartet auf die Füllung
            r = _r(side, p, m, swap)
            trade = {"side": "long" if side > 0 else "short", "signal": str(idx[t_sig]), "in": str(idx[p["t_in"]]),
                     "out": str(idx[p["t_out"]]), "in_px": round(float(p["entry_px"]), 2),
                     "out_px": round(float(p["exit_px"]), 2), "stop_usd": round(float(p["risk_dist"]), 2),
                     "usd_oz": round(float(side * (p["exit_px"] - p["entry_px"])), 2), "r": round(float(r), 3),
                     "why": p["reason"]}
            st["trades"].append(trade)
            events.append({"time": stamp, "event": "ausstieg", **trade})
            st["open"] = None
            t = max(t, p["t_out"])
            continue
        found = None
        for u in range(t, n):
            if long_in[u] and short_in[u]:
                events.append({"time": stamp, "event": "gesperrt", "bar": str(idx[u]), "why": ["Long und Short zugleich"]})
            elif long_in[u] or short_in[u]:
                found = u
                break
            elif raw_l[u] or raw_s[u]:
                side = 1 if raw_l[u] else -1
                events.append({"time": stamp, "event": "gesperrt", "bar": str(idx[u]),
                               "side": "long" if side > 0 else "short", "why": _blocked_why(P, u, side)})
        if found is None:
            break
        side = 1 if long_in[found] else -1
        st["open"] = {"side": side, "t_sig": str(idx[found])}
        sig_ev = {"time": stamp, "event": "signal", "bar": str(idx[found]), "side": "long" if side > 0 else "short"}
        if ff is not None:
            fill = news.fill_times(idx)[found]
            nw = cfg["runde_3"]["news"]
            sig_ev["forexfactory_haette_gesperrt"] = news.ff_window(ff, fill, nw["pause_vorher_h"], nw["pause_nachher_h"])
        events.append(sig_ev)
        t = found + 1
    st["cursor"] = str(idx[-1])
    st["updated_utc"] = stamp
    st["open_detail"] = _open_detail(st.get("open"), m, idx, f)
    st["richtung"] = int(P["richtung"][-1])
    st["summary"] = summary(st["trades"])
    ev = P["events"]
    now_utc = pd.Timestamp(now)
    now_utc = now_utc.tz_convert("UTC").tz_localize(None) if now_utc.tzinfo else now_utc
    st["naechste_termine"] = [str(x) for x in ev[ev > now_utc].head(3)]
    st["termine_bis"] = str(ev.max()) if len(ev) else None
    st["warnungen"] = []
    if len(ev) and ev.max() < now_utc + pd.Timedelta(days=45):
        st["warnungen"].append("Termin-Liste läuft in weniger als 45 Tagen aus: gold/v2/termine.yaml ergänzen")
    if ff is not None:
        own = ev.to_numpy()
        missing = [f"{x.utc:%Y-%m-%d %H:%M} {x.title}" for x in ff.itertuples()
                   if not len(own) or np.abs((own - x.utc.to_datetime64()) / np.timedelta64(1, "m")).min() > 30]
        st["forexfactory"] = {"abgerufen_utc": stamp,
                              "naechste": [f"{x.utc:%Y-%m-%d %H:%M} {x.title}" for x in ff[ff["utc"] > now_utc].head(5).itertuples()],
                              "nicht_in_termine_yaml": missing[:10], "hinweis": "nur mitgeschrieben, ändert keine Entscheidung"}
    st["hinweis"] = "Schattenlauf ohne Order. 2.0 hat Runde 3 nicht bestanden; das hier zählt nicht als Test für echtes Geld."
    st["fuehrung"] = {"ziel_atr": GEWAEHLT[0], "max_stunden": GEWAEHLT[1], "stop": GEWAEHLT[2],
                      "ausstieg_signal": "nur im Plus", "richtung": True, "news": True}
    return st, events


def _open_detail(op: dict | None, m, idx, f) -> dict | None:
    if not op:
        return None
    t_sig = int(idx.get_loc(pd.Timestamp(op["t_sig"])))
    side = int(op["side"])
    a = float(m.atr[t_sig])
    out = {"side": "long" if side > 0 else "short", "signal": op["t_sig"], "atr": round(a, 2)}
    if t_sig + 1 >= len(idx):
        out["stand"] = "wartet auf die Füllung zur nächsten Eröffnung"
        return out
    t_in = t_sig + 1
    epx = m.o[t_in] + m.sp[t_in] if side > 0 else m.o[t_in]
    mark = m.c[-1] if side > 0 else m.c[-1] + m.sp[-1]
    dist = f.stop_atr * a
    out.update({"in": str(idx[t_in]), "in_px": round(float(epx), 2), "stop": round(float(epx - side * dist), 2),
                "ziel": round(float(epx + side * f.tp_atr * a), 2), "stunden": int(len(idx) - t_in),
                "jetzt_r": round(float(side * (mark - epx) / dist), 2), "stand": "offen"})
    return out


def summary(trades: list[dict]) -> dict:
    r = np.array([t["r"] for t in trades], float)
    konto = KONTO_START
    for x in r:
        konto *= 1 + RISIKO_PCT / 100 * x
    return {"trades": int(len(r)), "win_pct": round(100 * float((r > 0).mean()), 1) if len(r) else None,
            "sum_r": round(float(r.sum()), 2), "pf_r": pf(r) if len(r) else None,
            "usd_oz": round(float(sum(t["usd_oz"] for t in trades)), 2),
            "konto_eur": round(konto, 2), "konto_start_eur": KONTO_START,
            "vorwaerts_ziel": "Auswertung nach 30 Trades: Summe R über 0 und Gewinnfaktor mindestens 1,2"}


def main(argv: list[str]) -> int:
    from gold.bot.capital import CapitalClient
    from gold.bot.rules import bars_from_prices
    from gold.bot.runner import clean_credentials, CRED_KEYS

    creds = clean_credentials({k: os.environ.get(k, "") for k in CRED_KEYS})
    if not all(creds):
        print("Keine Capital.com-Zugangsdaten, Schattenlauf übersprungen")
        return 0
    journal = ROOT / "journal"
    path = journal / STATE
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    now = datetime.now(timezone.utc)
    client = CapitalClient(*creds, environment="demo")
    client.login()
    try:
        bars, spread = bars_from_prices(fetch_candles(client, "GOLD"), now)
    finally:
        try:
            client.logout()
        except Exception:               # noqa: BLE001 - Abmelden ist nur Ordnung
            pass
    if len(bars) < MIN_BARS:
        print(f"Nur {len(bars)} Stundenkerzen, der Schattenlauf braucht {MIN_BARS}; nichts geschrieben")
        return 0
    if state.get("cursor") and pd.Timestamp(state["cursor"]) >= bars.index[-1]:
        print(f"Kerze {bars.index[-1]} ist schon verarbeitet")
        return 0
    cfg = config()
    ff = None
    try:                                # ForexFactory ist nur Beiwerk: ein Fehler stoppt den Schattenlauf nie
        import requests
        resp = requests.get(FF_URL, timeout=10, headers={"User-Agent": "portfolio-manager gold shadow (hourly)"})
        resp.raise_for_status()
        ff = news.ff_events(resp.json())
    except Exception as err:            # noqa: BLE001
        print(f"ForexFactory nicht gelesen: {err}")
    st, events = step(bars, spread, state, now, cfg, ff)
    journal.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if events:
        with open(journal / LOG, "a", encoding="utf-8") as fh:
            for e in events:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(json.dumps({"summary": st["summary"], "open": st["open_detail"], "events": events}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
