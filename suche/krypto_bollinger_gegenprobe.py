"""Gegenprobe für den Demo-Bot krypto-bollinger (suche/krypto_bollinger_bot.py): Sieht der Bot dieselben Einstiege,
Stops, Ziele und Ausstiege wie der Test der Runde "Kirons Notizen" (Fassung bollinger_umkehr_krypto_weit)?

    python -m suche.krypto_bollinger_gegenprobe <Arbeit> [<Ausgabe.json>] [<Markt> ...]

<Arbeit> ist der Ordner mit den Kursdateien des Tests (BTCUSD.npz, ETHUSD.npz, gebaut von
python -m suche.youtube_runde2 daten <Arbeit>). Der Test rechnet mit 5-Minuten-Kerzen. Der Bot bekommt nur fertige
Stundenkerzen und höchstens TAGE_KERZEN Kalendertage Vorlauf. Diese Gegenprobe gibt der Rechnung des Bots
(krypto_bollinger_bot.signal) zu jedem Schluss einer Stundenkerze im Hauptfenster genau das: Stundenkerzen, gebaut aus
den 5-Minuten-Kerzen des Tests, und als aktuellen Kurs die Eröffnung der 5-Minuten-Kerze, in der der Test einsteigt.
Dann vergleicht sie.

Sie rechnet keine neue Regel und kein neues Ergebnis in R. Sie prüft nur, ob die Umsetzung dieselben Entscheidungen
trifft wie die versiegelte Regel. Was sie nicht prüfen kann, steht in suche/VORAB_krypto_bollinger_bot.yaml unter
abweichungen_vom_test: andere Kursquelle, echter Spread, Einstieg und Ausstieg ein paar Minuten nach dem Schluss.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd

from suche import krypto_bollinger_bot as kb
from suche import notizen_runde as nr
from suche import rueckblick as rb


def stunden_aus(m) -> pd.DataFrame:
    """Stundenkerzen wie vom Broker: Beginn zur vollen Stunde, nur Stunden mit Kursen."""
    df = pd.DataFrame({"open": m.o, "high": m.h, "low": m.l, "close": m.c}, index=pd.DatetimeIndex(m.t))
    return df.groupby(df.index.floor("h")).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                                               close=("close", "last"))


def gegenprobe(sym: str, arbeit: pathlib.Path, cfg: dict, von: str, bis: str, tage: int | None = None,
               nur: list | None = None) -> dict:
    """nur: optional eine Liste von Stundengrenzen, an denen der Bot rechnet (für Tests). Sonst jede Stunde im Fenster,
    deren Stunde davor Kurse hat."""
    tage = tage or kb.TAGE_KERZEN
    von_t, bis_t = pd.Timestamp(von), pd.Timestamp(bis) + pd.Timedelta(days=1)     # der Test zählt den Tag "bis" mit
    m = nr.Markt(sym, arbeit, cfg)
    alle = nr.signale(kb.FASSUNG, m, cfg, kb.KEINE_TERMINE)
    sig = [s for s in alle if von_t <= pd.Timestamp(m.t[s["i0"]]) < bis_t]
    # Nur Signale, die der Test auch handeln könnte (rueckblick.echte_trades: Tag mit ATR davor)
    sig = [s for s in sig if m.gpos[m.tix[s["i0"]]] >= 1 and np.isfinite(m.atr_vor[m.gpos[m.tix[s["i0"]]]])]
    test = {}
    for s in sig:
        t_g = kb.naechste_grenze(pd.Timestamp(m.t[s["i0"] - 1]))
        test[t_g] = {"i0": int(s["i0"]), "d": int(s["d"]), "sd": float(s["sd"]), "zd": float(s["zd"]),
                     "spaet_min": (pd.Timestamp(m.t[s["i0"]]) - t_g).total_seconds() / 60}
    std = stunden_aus(m)
    t5 = pd.DatetimeIndex(m.t)
    if nur is None:
        grenzen = [g for g in std.index + kb.STUNDE if von_t <= g < bis_t]
    else:
        grenzen = [pd.Timestamp(g) for g in nur]
    bot, verpasst, wartet, grund = {}, [], 0, {}
    for t_g in grenzen:
        j = int(t5.searchsorted(t_g))
        if j >= len(t5):
            continue
        spaet = (t5[j] - t_g).total_seconds() / 60
        if spaet > kb.FRIST.total_seconds() / 60:           # in der Frist des Bots keine Kurse: der Bot steigt nie ein
            if t_g in test:
                verpasst.append(str(t_g))
            continue
        fenster = std[(std.index < t_g) & (std.index >= kb.vorlauf_ab(t_g) - pd.Timedelta(days=tage - kb.TAGE_KERZEN))]
        s = kb.signal(sym, fenster, t_g, float(m.o[j]), cfg)
        wartet += bool(s["warten"])
        grund[t_g] = s["ergebnis"]
        if s["ok"]:
            bot[t_g] = {"d": s["richtung"], "sd": s["dist"], "zd": s["ziel_abstand"], "ergebnis": s["ergebnis"]}

    beide = sorted(t for t in bot if t in test)
    p = kb.regel(cfg)
    nur_bot = {str(t): f"im Test {int(((t5 >= t - kb.STUNDE) & (t5 < t)).sum())} 5-Min.-Kerzen in der Signalkerze "
                       f"(nötig {int(p['min_kerzen'])})" for t in sorted(bot) if t not in test}
    nur_test = {str(t): grund.get(t, "keine Grenze des Bots") for t in sorted(test)
                if t not in bot and str(t) not in verpasst and (nur is None or t in set(grenzen))}
    richtung = sum(bot[t]["d"] == test[t]["d"] for t in beide)
    rel = [abs(bot[t]["sd"] - test[t]["sd"]) / test[t]["sd"] for t in beide]
    rel_z = [abs(bot[t]["zd"] - test[t]["zd"]) / test[t]["zd"] for t in beide]

    # Ausstieg nach Zeit: die Trades des Tests (höchstens einer je Markt). Der Bot schließt im ersten Lauf ab
    # bis_utc = Grenze + halte_stunden, der Test zur Eröffnung der ersten 5-Min.-Kerze ab t_max.
    tr = rb.echte_trades(m, sig, cfg)
    nach_zeit, gleich, abw = 0, 0, []
    for _, row in tr.iterrows():
        i0 = int(row["i0"])
        s = next(x for x in sig if x["i0"] == i0)
        aus = pd.Timestamp(row["aus_utc"])
        if aus < pd.Timestamp(s["t_max"]):
            continue                                          # Stop oder Ziel beim Broker
        nach_zeit += 1
        t_g = kb.naechste_grenze(pd.Timestamp(m.t[i0 - 1]))
        bis_utc = t_g + pd.Timedelta(hours=int(p["halte_stunden"]))
        if bis_utc == pd.Timestamp(s["t_max"]) and 0 <= (aus - bis_utc).total_seconds() / 60 <= 15:
            gleich += 1
        else:
            abw.append({"ein": str(m.t[i0]), "aus_test": str(aus), "bis_bot": str(bis_utc)})
    return {"markt": sym, "grenzen": len(grenzen), "test_einstiege": len(test), "bot_einstiege": len(bot),
            "beide": len(beide), "richtung_gleich": richtung, "nur_bot": nur_bot, "nur_test": nur_test,
            "verpasst_markt_zu": verpasst, "bot_wartet": wartet,
            "stop_abweichung_rel": {"groesste": round(max(rel), 9) if rel else 0.0,
                                    "mittel": round(float(np.mean(rel)), 9) if rel else 0.0},
            "ziel_abweichung_rel": {"groesste": round(max(rel_z), 9) if rel_z else 0.0},
            "test_spaet_ueber_0": sum(v["spaet_min"] > 0 for v in test.values()),
            "trades_im_test": int(len(tr)), "trades_ausstieg_nach_zeit": nach_zeit, "trades_ausstieg_gleich": gleich,
            "ausstieg_abweichungen": abw[:20]}


def main(argv: list[str]) -> int:
    if not argv:
        raise SystemExit(__doc__)
    arbeit = pathlib.Path(argv[0])
    cfg = kb.lade_cfg(pruefen=True)
    if cfg is None:
        raise SystemExit("Regeldateien passen nicht zu ihren Siegeln")
    f = cfg["fenster"]
    out = {"fassung": kb.FASSUNG, "fenster": f, "tage_kerzen": kb.TAGE_KERZEN, "frist_min": kb.FRIST.total_seconds() / 60,
           "maerkte": {}}
    for sym in (argv[2:] or kb.MAERKTE):
        t0 = time.time()
        out["maerkte"][sym] = r = gegenprobe(sym, arbeit, cfg, f["von"], f["bis"])
        r["sekunden"] = round(time.time() - t0, 1)
        print(json.dumps({k: v for k, v in r.items() if k != "ausstieg_abweichungen"}, ensure_ascii=False), flush=True)
    if len(argv) > 1:
        pathlib.Path(argv[1]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str) + "\n",
                                         encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
