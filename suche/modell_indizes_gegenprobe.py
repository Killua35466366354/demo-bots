"""Gewichte und Gegenprobe für den Demo-Bot modell-indizes (suche/modell_indizes_bot.py).

    python -m suche.modell_indizes_gegenprobe gewichte <Arbeit>                  schreibt suche/modell_indizes_gewichte.json
    python -m suche.modell_indizes_gegenprobe pruefen <Arbeit> [<Ausgabe.json>]  Bot gegen Test, Tag für Tag

<Arbeit> ist der Ordner mit den Kursdateien des Tests (SPXUSD.npz, NSXUSD.npz, GRXEUR.npz, UKXGBP.npz, JPXJPY.npz,
gebaut von python -m suche.youtube_runde2 daten <Arbeit>). Die FRED-Reihen liest der Test aus dem Projektordner
(suche/grosse_runde.FRED), ihre Prüfsummen stehen in suche/VORAB_grosse_runde.yaml.

gewichte: Der Test (suche/grosse_runde.vorhersagen) lernt das Modell zu jedem Kalenderjahr neu, nur mit den Zeilen aller
fünf Märkte aus den Jahren davor. Live kann der Bot nicht lernen, ihm fehlen die Kurse von HistData. Darum schreibt
dieses Programm für jedes Jahr genau das, was der Test in diesem Jahr benutzt: Mittel und Streuung der Lernzeilen und
die gelernten Gewichte. Es prüft dabei, dass diese Zahlen für jede Zeile des Jahres dieselbe Wahrscheinlichkeit geben wie
der Test.

pruefen: Der Bot bekommt nur Stundenkerzen (vom Broker). Diese Gegenprobe baut aus den 5-Minuten-Kerzen des Tests
Stundenkerzen, gibt sie der Rechnung des Bots (modell_indizes_bot.signal) zu jedem Handelstag zur Minute des Einstiegs im
Test und vergleicht Richtung, Stop-Abstand und Ausstieg mit den Signalen des Tests. Dazu zählt sie, wie oft sich die
Richtung ändern würde, wenn VIX oder Zinsen einen Tag älter wären (falls eine Quelle live zu spät kommt).
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd

from suche import grosse_runde as gr
from suche import modell_indizes_bot as mb


def teile(arbeit: pathlib.Path, cfg: dict, bis: str | None = None) -> list[tuple]:
    """Je Markt (Name, Handelstage, Merkmale samt Grundwert-Spalten, Ergebnis), genau wie gr.regel_modell."""
    p, gruppe = mb.regel(cfg), mb.gruppe(cfg)
    out = []
    for nr_, sym in enumerate(gruppe):
        m = gr.Markt(sym, arbeit, cfg, bis)
        X, y, _ = gr.merkmale(m, cfg, p, gruppe)
        out.append((sym, m.gtag, np.column_stack([X, mb.grundwerte(nr_, len(gruppe), len(y))]), y))
    return out


def parameter(tage: np.ndarray, X: np.ndarray, y: np.ndarray, p: dict, jahr: int) -> dict | None:
    """Was gr.vorhersagen für das Kalenderjahr `jahr` lernt: Mittel und Streuung der Lernzeilen und die Gewichte."""
    jahre = tage.astype("datetime64[Y]").astype(np.int64) + 1970
    lern = (jahre < jahr) & np.isfinite(y)
    if lern.sum() < p["min_lernzeilen"] or len(np.unique(jahre[lern])) < p["min_lernjahre"]:
        return None
    mittel = np.nanmean(X[lern], axis=0)
    streu = np.nanstd(X[lern], axis=0)
    streu = np.where(streu > 0, streu, 1.0)
    z = (X[lern] - mittel) / streu
    z = np.clip(np.where(np.isfinite(z), z, 0.0), -5.0, 5.0)
    w = gr.logistisch(np.column_stack([np.ones(len(z)), z]), y[lern], p["strafe"])
    return {"jahr": int(jahr), "lernzeilen": int(lern.sum()), "lernjahre": sorted(int(j) for j in np.unique(jahre[lern])),
            "mittel": [float(x) for x in mittel], "streu": [float(x) for x in streu], "gewichte": [float(x) for x in w]}


def gewichte_bauen(arbeit: pathlib.Path, jahre: list[int]) -> dict:
    cfg = mb.lade_cfg(pruefen=True)
    if cfg is None:
        raise SystemExit("Regeldateien passen nicht zu ihren Siegeln")
    p = mb.regel(cfg)
    tl = teile(arbeit, cfg, cfg["fenster"]["bis"])
    tage = np.concatenate([t[1] for t in tl])
    X = np.vstack([t[2] for t in tl])
    y = np.concatenate([t[3] for t in tl])
    test = gr.vorhersagen(tage, X, y, p)                            # die Wahrscheinlichkeiten des Tests
    jahr_z = tage.astype("datetime64[Y]").astype(np.int64) + 1970
    out = {"fassung": mb.FASSUNG, "maerkte": mb.gruppe(cfg), "merkmale": mb.merkmal_namen(cfg),
           "quelle": "python -m suche.modell_indizes_gegenprobe gewichte <Arbeit> (Kurse von HistData bis "
                     f"{cfg['fenster']['bis']}, FRED-Reihen aus dem Projektordner)", "jahre": {}}
    for j in jahre:
        par = parameter(tage, X, y, p, j)
        if par is None:
            raise SystemExit(f"Für {j} lernt der Test kein Modell")
        zeilen = jahr_z == j
        if zeilen.any():                                           # dieselbe Wahrscheinlichkeit wie im Test?
            q = np.array([mb.wahrscheinlichkeit(x, par) for x in X[zeilen]])
            diff = float(np.nanmax(np.abs(q - test[zeilen])))
            par["pruefung"] = {"zeilen": int(zeilen.sum()), "groesste_abweichung": diff}
            if not diff < 1e-9:
                raise SystemExit(f"{j}: Gewichte geben eine andere Wahrscheinlichkeit als der Test ({diff})")
        out["jahre"][str(j)] = par
    return out


# --------------------------------------------------------------------------------------------------------------------
# Gegenprobe Bot gegen Test

def stunden_aus(m) -> pd.DataFrame:
    """Stundenkerzen wie vom Broker: Beginn zur vollen Stunde, nur Stunden mit Kursen."""
    df = pd.DataFrame({"open": m.o, "high": m.h, "low": m.l, "close": m.c}, index=pd.DatetimeIndex(m.t))
    return df.groupby(df.index.floor("h")).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                                               close=("close", "last"))


def gegenprobe(sym: str, arbeit: pathlib.Path, cfg: dict, gew: dict, von: str, bis: str,
               nur: list | None = None, test_signale: list[dict] | None = None, fred: pathlib.Path | None = None) -> dict:
    """Bot gegen Test auf einem Markt, je Handelstag im Fenster [von, bis]. nur: optional einige Handelstage.
    test_signale und fred nur für die Tests mit erfundenen Kursen: die Signale des Tests (sonst gr.signale) und der
    Ordner mit den fremden Reihen (sonst die Dateien des Tests)."""
    m = gr.Markt(sym, arbeit, cfg, cfg["fenster"]["bis"])
    alle = test_signale if test_signale is not None else gr.signale(mb.FASSUNG, m, cfg,
                                                                     np.array([], dtype="datetime64[ns]"))
    i_ein, aus = gr.tages_einstieg(m, cfg)
    test = {}
    for s in alle:
        g = int(m.gpos[m.tix[s["i0"]]])
        if g < 1 or not np.isfinite(m.atr_vor[g]):
            continue
        test[str(m.gtag[g])[:10]] = s
    std = stunden_aus(m)
    von_d, bis_d = np.datetime64(von), np.datetime64(bis)
    tage = [g for g in range(1, len(m.gtag)) if von_d <= m.gtag[g] <= bis_d]
    if nur is not None:
        tage = [g for g in tage if str(m.gtag[g])[:10] in set(nur)]
    beide, nur_bot, nur_test, richtung_anders, stop_rel, aus_gleich = 0, {}, {}, {}, [], 0
    kein_einstieg, wartet = 0, {}
    probs = []
    for g in tage:
        tag = str(m.gtag[g])[:10]
        e = int(i_ein[g])
        if e < 0:                                                 # der Test hat an diesem Tag keine Einstiegskerze
            kein_einstieg += 1
            if tag in test:
                nur_test[tag] = "Test ohne Einstiegskerze?"
            continue
        t_e = pd.Timestamp(m.t[e])
        s = mb.signal(sym, std[std.index < t_e.floor("h")], t_e, float(m.o[e]), cfg, gew, fred=fred)
        if s["warten"]:
            wartet[tag] = s["ergebnis"]
            if tag in test:
                nur_test[tag] = s["ergebnis"]
            continue
        if s.get("wahrscheinlichkeit") is not None:
            probs.append(s["wahrscheinlichkeit"])
        if s["ok"] and tag in test:
            beide += 1
            t = test[tag]
            if s["richtung"] != int(t["d"]):
                richtung_anders[tag] = {"bot": s["richtung"], "test": int(t["d"])}
            stop_rel.append(abs(s["dist"] - float(t["sd"])) / float(t["sd"]))
            aus_gleich += pd.Timestamp(s["bis_utc"]) == pd.Timestamp(t["t_max"])
        elif s["ok"]:
            nur_bot[tag] = s["ergebnis"]
        elif tag in test:
            nur_test[tag] = s["ergebnis"]
    return {"markt": sym, "tage": len(tage), "test_signale": sum(1 for t in test if von <= t <= bis),
            "bot_signale": beide + len(nur_bot), "beide": beide, "richtung_anders": richtung_anders,
            "nur_bot": nur_bot, "nur_test": nur_test, "kein_einstieg_im_test": kein_einstieg, "bot_wartet": wartet,
            "stop_abweichung_rel": {"groesste": round(max(stop_rel), 12) if stop_rel else 0.0},
            "ausstieg_gleich": int(aus_gleich)}


def empfindlichkeit(arbeit: pathlib.Path, cfg: dict, gew: dict, von: str, bis: str) -> dict:
    """Wie oft ändert sich die Richtung des Tests (in [von, bis]), wenn der jüngste Wert einer Reihe fehlt, also die
    Quelle einen Tag zu spät veröffentlicht? Gerechnet mit den Merkmalen des Tests und den Gewichten des Jahres."""
    p, gruppe = mb.regel(cfg), mb.gruppe(cfg)
    out = {}
    for name, reihen in (("VIX und VIX3M", ("VIXCLS", "VXVCLS")), ("Zinsen 10 und 2 Jahre", ("DGS10", "DGS2")),
                         ("alle vier", ("VIXCLS", "VXVCLS", "DGS10", "DGS2"))):
        geaendert, gezaehlt = 0, 0
        for nr_, sym in enumerate(gruppe):
            m = gr.Markt(sym, arbeit, cfg, cfg["fenster"]["bis"])
            X, _, _ = gr.merkmale(m, cfg, p, gruppe)
            with mb.fremd_verspaetet(reihen):
                X2, _, _ = gr.merkmale(m, cfg, p, gruppe)
            gw = mb.grundwerte(nr_, len(gruppe), len(X))
            i_ein, _ = gr.tages_einstieg(m, cfg)
            for g in range(1, len(m.gtag)):
                tag = str(m.gtag[g])[:10]
                if not (von <= tag <= bis) or i_ein[g] < 0 or not np.isfinite(m.atr_vor[g]):
                    continue
                par = gew["jahre"].get(tag[:4])
                if par is None:
                    continue
                a = mb.richtung(mb.wahrscheinlichkeit(np.r_[X[g], gw[g]], par), p)
                b = mb.richtung(mb.wahrscheinlichkeit(np.r_[X2[g], gw[g]], par), p)
                gezaehlt += 1
                geaendert += a != b
        out[name] = {"tage": gezaehlt, "richtung_anders": geaendert,
                     "anteil": round(geaendert / gezaehlt, 4) if gezaehlt else None}
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        raise SystemExit(__doc__)
    modus, arbeit = argv[0], pathlib.Path(argv[1])
    if modus == "gewichte":
        out = gewichte_bauen(arbeit, mb.JAHRE)
        mb.GEWICHTE.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        for j, par in out["jahre"].items():
            print(j, par["lernzeilen"], par.get("pruefung"))
        return 0
    if modus != "pruefen":
        raise SystemExit(__doc__)
    cfg = mb.lade_cfg(pruefen=True)
    gew = mb.lade_gewichte(pruefen=False)
    if cfg is None or gew is None:
        raise SystemExit("Regeldateien oder Gewichte fehlen")
    von, bis = cfg["fenster"]["von"], cfg["fenster"]["bis"]
    out = {"fassung": mb.FASSUNG, "von": von, "bis": bis, "maerkte": {}}
    for sym in argv[3:] or mb.gruppe(cfg):
        t0 = time.time()
        out["maerkte"][sym] = r = gegenprobe(sym, arbeit, cfg, gew, von, bis)
        r["sekunden"] = round(time.time() - t0, 1)
        print(json.dumps({k: (v if not isinstance(v, dict) or len(v) < 6 else f"{len(v)} Tage")
                          for k, v in r.items()}, ensure_ascii=False), flush=True)
    out["empfindlichkeit"] = empfindlichkeit(arbeit, cfg, gew, von, bis)
    print(json.dumps(out["empfindlichkeit"], ensure_ascii=False), flush=True)
    if len(argv) > 2:
        pathlib.Path(argv[2]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str) + "\n",
                                         encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
