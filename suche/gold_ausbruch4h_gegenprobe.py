"""Gegenprobe für den Demo-Bot gold-ausbruch4h (gold/ausbruch4h_bot.py): Sieht der Bot dieselben Einstiege, Stops und
Ausstiege wie der Test der Gold-Matrix?

    python -m suche.gold_ausbruch4h_gegenprobe <Datenordner> [<Ausgabe.json>]

Der Test rechnet mit 1-Minuten-Kerzen und Indikatoren ab 2023. Der Bot bekommt nur fertige Stundenkerzen und höchstens
TAGE_KERZEN Kalendertage Vorlauf. Diese Gegenprobe gibt der Rechnung des Bots (ab.signal, ab.kerzen_seit) zu jedem
4-Std.-Schluss im Hauptfenster genau das: Stundenkerzen, gebaut aus den 1-Minuten-Kerzen des Tests, und als aktuellen
Kurs die Eröffnung der Minute, in der der Test einsteigt. Dann vergleicht sie.

Sie rechnet keine neue Regel und kein neues Ergebnis in R. Sie prüft nur, ob die Umsetzung dieselben Entscheidungen
trifft wie die versiegelte Regel (suche/VORAB_gold_matrix.yaml). Was sie nicht prüfen kann, steht in
suche/VORAB_gold_ausbruch4h_bot.yaml unter abweichungen_vom_test: andere Kursquelle, echter Spread, Einstieg und
Ausstieg ein paar Minuten nach dem Schluss.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd

from gold import ausbruch4h_bot as ab
from suche import gold_matrix as gm


def stunden_aus_minuten(gold: pd.DataFrame) -> pd.DataFrame:
    """Stundenkerzen wie vom Broker: Beginn zur vollen Stunde, nur Stunden mit Kursen."""
    return gold.groupby(gold.index.floor("h")).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                                                   close=("close", "last"))


def gegenprobe(gold: pd.DataFrame, von, bis, tage: int = ab.TAGE_KERZEN) -> dict:
    """gold: 1-Minuten-Bid in echter UTC, auch vor dem Vorlauf des Tests (für den Vorlauf des Bots)."""
    von, bis = pd.Timestamp(von), pd.Timestamp(bis)
    f = ab.V
    m = gm.markt(gold[gold.index >= gm.VORLAUF_AB], termine=gm.lies_termine())
    std = stunden_aus_minuten(gold)
    vorlauf = pd.Timedelta(days=tage)

    # Der Test: alle Einstiege, die er nehmen dürfte (vor der Frage, ob schon ein Trade offen ist), und seine Trades
    e, d = gm.einstiege(m, f["einstieg"], f["ebene"])
    drin = gm.im_fenster(m, e, von, bis)
    e, d = e[drin], d[drin]
    trend = gm.filter_maske(m, f["filter"], f["ebene"], e, d)
    dist = gm.stop_abstand(m, f["stop_art"], f["stop_ebene"], e, d)
    gut = trend & (dist >= gm.MIN_ABSTAND)
    test = {pd.Timestamp(m.t[e[i]]): (int(d[i]), float(dist[i])) for i in np.flatnonzero(gut)}
    trades = gm.trades_von(m, f, von, bis)

    # Der Bot: zu jedem 4-Std.-Schluss im Fenster
    k4 = m.eb[f["ebene"]]
    bot, zu_test, wartet = {}, {}, 0
    grenzen = 0
    for j in range(len(k4)):
        i1 = int(k4.ende1[j])
        if i1 + 1 >= len(m):
            continue
        letzte, te = pd.Timestamp(m.t[i1]), pd.Timestamp(m.t[i1 + 1])
        t_g = ab.naechste_grenze(letzte)
        if not (von <= t_g < bis):
            continue
        grenzen += 1
        nah = te - letzte <= pd.Timedelta(minutes=gm.LUECKE_MIN)
        kurs = float(m.o[i1 + 1]) if nah else float(m.c[i1])
        s = ab.signal(std[(std.index < t_g) & (std.index >= t_g - vorlauf)], t_g, t_g, kurs)
        wartet += bool(s["warten"])
        if s["ok"]:
            bot[t_g] = (int(s["richtung"]), float(s["dist"]))
        if te in test:
            zu_test[t_g] = te
    beide = sorted(t for t in bot if t in zu_test)
    nur_bot = sorted(t for t in bot if t not in zu_test)
    nur_test = sorted(str(te) for t, te in zu_test.items() if t not in bot)
    ohne_grenze = sorted(str(te) for te in test if te not in set(zu_test.values()))
    abw = np.array([abs(bot[t][1] - test[zu_test[t]][1]) for t in beide]) if beide else np.array([0.0])
    rel = np.array([abs(bot[t][1] - test[zu_test[t]][1]) / test[zu_test[t]][1] for t in beide]) if beide else abw

    # Die Trades des Tests: Einstieg beim Bot gleich? Ausstieg nach Zeit in derselben Minute fällig?
    je_einstieg = {te: t for t, te in zu_test.items()}
    tr_gleich = aus_gleich = aus_regel = 0
    abweichungen = []
    for row in trades.itertuples():
        te, tx = pd.Timestamp(row.zeit), pd.Timestamp(row.zeit_aus)
        t_g = je_einstieg.get(te)
        gleich = t_g in bot and bot[t_g][0] == int(row.d)
        tr_gleich += bool(gleich)
        if not gleich:
            abweichungen.append({"einstieg": str(te), "art": "Einstieg fehlt beim Bot"})
        if row.grund != "regel" or t_g is None:
            continue
        aus_regel += 1
        davor = pd.Timestamp(m.t[int(np.searchsorted(m.t, np.datetime64(tx, "ns"))) - 1])      # letzte gehandelte Minute
        ab_wann = t_g - ab.VORLAUF_TRADE
        n_dann = ab.kerzen_seit(std[(std.index >= ab_wann) & (std.index + ab.STUNDE <= tx)], t_g, tx)
        n_davor = ab.kerzen_seit(std[(std.index >= ab_wann) & (std.index + ab.STUNDE <= davor)], t_g, davor)
        if n_dann == ab.ZEIT_KERZEN and n_davor == ab.ZEIT_KERZEN - 1:
            aus_gleich += 1
        else:
            abweichungen.append({"einstieg": str(te), "ausstieg": str(tx), "art": "Ausstieg nach Zeit anders",
                                 "kerzen_dann": n_dann, "kerzen_davor": n_davor})
    return {"fenster": [str(von), str(bis)], "vorlauf_tage_bot": tage, "grenzen_geprueft": grenzen,
            "bot_wartet_auf_kerze": wartet, "test_einstiege_erlaubt": len(test), "bot_einstiege_erlaubt": len(bot),
            "beide": len(beide), "richtung_gleich": int(sum(bot[t][0] == test[zu_test[t]][0] for t in beide)),
            "nur_bot": [str(t) for t in nur_bot], "nur_test": nur_test, "test_ohne_grenze": ohne_grenze,
            "stop_abstand_abweichung_usd": {"groesste": round(float(abw.max()), 4), "median": round(float(np.median(abw)), 4)},
            "stop_abstand_abweichung_anteil": {"groesste": round(float(rel.max()), 5)},
            "trades_im_test": int(len(trades)), "trades_einstieg_gleich": tr_gleich,
            "trades_ausstieg_nach_zeit": aus_regel, "trades_ausstieg_gleich": aus_gleich, "abweichungen": abweichungen}


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    if not (gm.vorab_ok() and gm.finalisten_ok()):
        print("Die Regeln der Gold-Matrix sind nicht festgelegt, nichts gerechnet")
        return 1
    t0 = time.time()
    gold = gm.lies_gold(pathlib.Path(argv[0]))
    fenster = gm.P["fenster"]
    res = gegenprobe(gold, fenster["haupt_von"], fenster["haupt_bis"])
    res["sekunden"] = round(time.time() - t0)
    text = json.dumps(res, ensure_ascii=False, indent=1)
    print(text)
    if len(argv) > 1:
        pathlib.Path(argv[1]).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
