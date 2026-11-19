"""Gegenprobe für den Demo-Bot welt-ausbruch4h (suche/welt4h_bot.py): Sieht der Bot dieselben Einstiege, Stops,
Ziele und Ausstiege wie der Test der Runde "Kirons Notizen" (Fassung ausbruch4h_welt_ziel_1r)?

    python -m suche.welt4h_gegenprobe <Arbeit> [<Ausgabe.json>]

<Arbeit> ist der Ordner mit den Kursdateien des Tests (GRXEUR.npz, UKXGBP.npz, JPXJPY.npz, gebaut von
python -m suche.youtube_runde2 daten <Arbeit>). Der Test rechnet mit 5-Minuten-Kerzen. Der Bot bekommt nur fertige
Stundenkerzen und höchstens TAGE_KERZEN Kalendertage Vorlauf. Diese Gegenprobe gibt der Rechnung des Bots
(welt4h_bot.signal, welt4h_bot.kerzen_seit) zu jedem Schluss einer 4-Std.-Kerze im Hauptfenster genau das:
Stundenkerzen, gebaut aus den 5-Minuten-Kerzen des Tests, und als aktuellen Kurs die Eröffnung der 5-Minuten-Kerze, in
der der Test einsteigt. Dann vergleicht sie.

Sie rechnet keine neue Regel und kein neues Ergebnis in R. Sie prüft nur, ob die Umsetzung dieselben Entscheidungen
trifft wie die versiegelte Regel. Was sie nicht prüfen kann, steht in suche/VORAB_welt_ausbruch4h_bot.yaml unter
abweichungen_vom_test: andere Kursquelle, echter Spread, Einstieg und Ausstieg ein paar Minuten nach dem Schluss.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd

from suche import notizen_runde as nr
from suche import rueckblick as rb
from suche import welt4h_bot as wb

LAUF_MINUTEN = (1, 16, 31, 46)          # so oft kommt der Lauf (demo-bots.yml, alle 15 Minuten)


def stunden_aus(m) -> pd.DataFrame:
    """Stundenkerzen wie vom Broker: Beginn zur vollen Stunde, nur Stunden mit Kursen."""
    df = pd.DataFrame({"open": m.o, "high": m.h, "low": m.l, "close": m.c}, index=pd.DatetimeIndex(m.t))
    return df.groupby(df.index.floor("h")).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                                               close=("close", "last"))


def laeufe_ab(t: pd.Timestamp, n: int) -> list[pd.Timestamp]:
    """Die nächsten n Läufe ab der Zeit t."""
    h = pd.Timestamp(t).floor("h")
    out = []
    while len(out) < n:
        out += [h + pd.Timedelta(minutes=k) for k in LAUF_MINUTEN if h + pd.Timedelta(minutes=k) >= t]
        h += wb.STUNDE
    return out[:n]


def gegenprobe(sym: str, arbeit: pathlib.Path, cfg: dict, termine: np.ndarray, von: str, bis: str,
               tage: int | None = None) -> dict:
    tage = tage or wb.TAGE_KERZEN
    von_t, bis_t = pd.Timestamp(von), pd.Timestamp(bis) + pd.Timedelta(days=1)     # der Test zählt den Tag "bis" mit
    m = nr.Markt(sym, arbeit, cfg)
    sig = [s for s in nr.signale(wb.FASSUNG, m, cfg, termine) if von_t <= pd.Timestamp(m.t[s["i0"]]) < bis_t]
    test = {}
    for s in sig:
        t_g = wb.naechste_grenze(pd.Timestamp(m.t[s["i0"] - 1]))
        test[t_g] = {"i0": int(s["i0"]), "d": int(s["d"]), "sd": float(s["sd"]), "zd": float(s["zd"]),
                     "spaet_min": (pd.Timestamp(m.t[s["i0"]]) - t_g).total_seconds() / 60}
    std = stunden_aus(m)
    t5 = pd.DatetimeIndex(m.t)

    # Der Bot: zu jedem Schluss einer 4-Std.-Kerze im Fenster, an dem die letzte Stunde davor Kurse hat
    b = wb._block(std.index)
    ende = std.index[np.r_[b[1:] != b[:-1], True]] + wb.STUNDE       # letzte Stunde einer Kerze -> Schluss der Kerze
    grenzen = [g for g in ende if von_t <= g < bis_t and wb._block([g])[0] != wb._block([g - wb.STUNDE])[0]]
    bot, verpasst, wartet, grund = {}, [], 0, {}
    for t_g in grenzen:
        j = int(t5.searchsorted(t_g))
        if j >= len(t5):
            continue
        spaet = (t5[j] - t_g).total_seconds() / 60
        if spaet > wb.FRIST.total_seconds() / 60:          # Markt in der Frist des Bots zu: der Bot steigt nie ein
            if t_g in test:
                verpasst.append(str(t_g))
            continue
        fenster = std[(std.index < t_g) & (std.index >= t_g - pd.Timedelta(days=tage))]
        s = wb.signal(sym, fenster, t_g, float(m.o[j]), cfg, termine)
        wartet += bool(s["warten"])
        grund[t_g] = s["ergebnis"]
        if s["ok"]:
            bot[t_g] = {"d": s["richtung"], "sd": s["dist"], "zd": s["ziel_abstand"], "ergebnis": s["ergebnis"]}

    beide = sorted(t for t in bot if t in test)
    # Zu jeder Abweichung der Grund: beim Bot sein Ergebnis, beim Test die Zahl der 5-Min.-Kerzen in der Signalkerze
    # (der Bot sieht nur Stundenkerzen und zählt jede volle Stunde als 12 Kerzen)
    p = wb.regel(cfg)
    nur_bot = {str(t): f"im Test {int(((t5 >= t - 4 * wb.STUNDE) & (t5 < t)).sum())} 5-Min.-Kerzen in der Signalkerze "
                       f"(nötig {int(p['min_kerzen'])})" for t in sorted(bot) if t not in test}
    nur_test = {str(t): grund.get(t, "keine Grenze des Bots") for t in sorted(test)
                if t not in bot and str(t) not in verpasst}
    richtung = sum(bot[t]["d"] == test[t]["d"] for t in beide)
    rel = [abs(bot[t]["sd"] - test[t]["sd"]) / test[t]["sd"] for t in beide]
    rel_z = [abs(bot[t]["zd"] - test[t]["zd"]) / test[t]["zd"] for t in beide]

    # Ausstieg nach Zeit: die Trades des Tests (höchstens einer je Markt) gegen das Zählen des Bots
    tr = rb.echte_trades(m, sig, cfg)
    nach_zeit, gleich, abw = 0, 0, []
    for _, row in tr.iterrows():
        i0 = int(row["i0"])
        s = next(x for x in sig if x["i0"] == i0)
        aus = pd.Timestamp(row["aus_utc"])
        if aus < pd.Timestamp(s["t_max"]):
            continue                                          # Stop oder Ziel beim Broker, nicht die Zählung
        nach_zeit += 1
        t_ein = pd.Timestamp(m.t[i0])
        t_g = wb.naechste_grenze(pd.Timestamp(m.t[i0 - 1]))
        bis_utc = t_g + pd.Timedelta(days=int(p["halte_tage_max"]))
        nah = std[(std.index >= t_g) & (std.index < t_g + pd.Timedelta(days=16))]
        lauf_aus = None
        for now in laeufe_ab(t_ein, 16 * 24 * 4):
            offen = t5.searchsorted(now - pd.Timedelta(minutes=14)) < t5.searchsorted(now + pd.Timedelta(minutes=1))
            if not offen:                                     # Markt zu: der Bot wartet
                continue
            if now >= bis_utc or wb.kerzen_seit(nah, t_g, now) >= int(p["halte_kerzen"]):
                lauf_aus = now
                break
        diff = None if lauf_aus is None else (lauf_aus - aus).total_seconds() / 60
        if diff is not None and 0 <= diff <= 16:              # erster Lauf nach dem Ausstieg des Tests
            gleich += 1
        else:
            abw.append({"ein": str(t_ein), "aus_test": str(aus), "aus_bot": str(lauf_aus), "minuten": diff})
    return {"markt": sym, "grenzen": len(grenzen), "test_einstiege": len(test), "bot_einstiege": len(bot),
            "beide": len(beide), "richtung_gleich": richtung, "nur_bot": nur_bot, "nur_test": nur_test,
            "verpasst_markt_zu": verpasst, "bot_wartet": wartet,
            "stop_abweichung_rel": {"groesste": round(max(rel), 6) if rel else 0.0,
                                    "mittel": round(float(np.mean(rel)), 6) if rel else 0.0},
            "ziel_abweichung_rel": {"groesste": round(max(rel_z), 6) if rel_z else 0.0},
            "test_spaet_ueber_0": sum(v["spaet_min"] > 0 for v in test.values()),
            "trades_im_test": int(len(tr)), "trades_ausstieg_nach_zeit": nach_zeit, "trades_ausstieg_gleich": gleich,
            "ausstieg_abweichungen": abw[:20]}


def main(argv: list[str]) -> int:
    if not argv:
        raise SystemExit(__doc__)
    arbeit = pathlib.Path(argv[0])
    cfg = wb.lade_cfg(pruefen=True)
    if cfg is None:
        raise SystemExit("Regeldateien passen nicht zu ihren Siegeln")
    f = cfg["fenster"]
    term = rb.termine_utc()
    out = {"fassung": wb.FASSUNG, "fenster": f, "tage_kerzen": wb.TAGE_KERZEN, "frist_min": wb.FRIST.total_seconds() / 60,
           "maerkte": {}}
    for sym in (argv[2:] or wb.MAERKTE):
        t0 = time.time()
        out["maerkte"][sym] = r = gegenprobe(sym, arbeit, cfg, term, f["von"], f["bis"])
        r["sekunden"] = round(time.time() - t0, 1)
        print(json.dumps({k: v for k, v in r.items() if k != "ausstieg_abweichungen"}, ensure_ascii=False), flush=True)
    if len(argv) > 1:
        pathlib.Path(argv[1]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str) + "\n",
                                         encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
