"""Gegenprobe für den Demo-Bot vix-sprung (suche/vix_sprung_bot.py): Bot gegen Test, Tag für Tag.

    python -m suche.vix_sprung_gegenprobe <Arbeit> [<Ausgabe.json>] [<Markt> ...] [--ganz]

<Arbeit> ist der Ordner mit den Kursdateien des Tests (SPXUSD.npz, NSXUSD.npz, GRXEUR.npz, UKXGBP.npz, JPXJPY.npz,
gebaut von python -m suche.youtube_runde2 daten <Arbeit>). Den VIX liest der Test aus dem Projektordner
(suche/grosse_runde.FRED, VIXCLS.csv), seine Prüfsumme steht in suche/VORAB_grosse_runde.yaml.

Der Bot bekommt nur Stundenkerzen (vom Broker). Diese Gegenprobe baut aus den 5-Minuten-Kerzen des Tests Stundenkerzen,
gibt sie der Rechnung des Bots (vix_sprung_bot.signal) zu jedem Handelstag zur Minute des Einstiegs im Test und
vergleicht Einstieg, Stop-Abstand und Ausstieg mit den Signalen des Tests (vix_sprung_us aus Durchgang 1 für US500 und
US100, vix_sprung_welt aus Durchgang 2 für DAX, FTSE und Nikkei). Dazu prüft sie die Abkürzung des Bots: An Tagen ohne
Sprung erledigt er den Tag schon mit dem VIX allein, ohne Kerzen.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd

from suche import grosse_runde as gr
from suche import modell_indizes_gegenprobe as mg
from suche import vix_sprung_bot as vb


def gegenprobe(sym: str, arbeit: pathlib.Path, cfgs: dict, von: str, bis: str, nur: list | None = None,
               test_signale: list[dict] | None = None, fred: pathlib.Path | None = None,
               abkuerzung: bool = True) -> dict:
    """Bot gegen Test auf einem Markt, je Handelstag im Fenster [von, bis]. nur: optional einige Handelstage.
    test_signale und fred nur für die Tests mit erfundenen Kursen: die Signale des Tests (sonst gr.signale) und der
    Ordner mit dem VIX (sonst die Datei des Tests). abkuerzung=False rechnet auch an Tagen ohne Sprung die ganze
    Rechnung des Bots mit Kerzen (langsamer)."""
    cfg, p = cfgs[vb.DURCHGANG[sym]], vb.regel(sym, cfgs)
    m = gr.Markt(sym, arbeit, cfg, cfg["fenster"]["bis"])
    if test_signale is None:
        with vb.mb.fred_ordner(fred):
            test_signale = gr.signale(vb.FASSUNG[sym], m, cfg, np.array([], dtype="datetime64[ns]"))
    i_ein, _ = gr.tages_einstieg(m, cfg)
    test = {}
    for s in test_signale:
        g = int(m.gpos[m.tix[s["i0"]]])
        if g < 1 or not np.isfinite(m.atr_vor[g]):
            continue
        test[str(m.gtag[g])[:10]] = s
    std = mg.stunden_aus(m)
    von_d, bis_d = np.datetime64(von), np.datetime64(bis)
    tage = [g for g in range(1, len(m.gtag)) if von_d <= m.gtag[g] <= bis_d]
    if nur is not None:
        tage = [g for g in tage if str(m.gtag[g])[:10] in set(nur)]
    beide, nur_bot, nur_test, stop_rel, aus_gleich, ein_gleich = 0, {}, {}, [], 0, 0
    kein_einstieg, wartet, abkuerzung_falsch = 0, {}, {}
    for g in tage:
        tag = str(m.gtag[g])[:10]
        e = int(i_ein[g])
        if e < 0:                                                 # der Test hat an diesem Tag keine Einstiegskerze
            kein_einstieg += 1
            if tag in test:
                nur_test[tag] = "Test ohne Einstiegskerze?"
            continue
        if abkuerzung and vb.sprung(pd.Timestamp(tag), p, fred)["richtung"] == 0:   # wie der Bot: ohne Sprung erledigt
            if tag in test:
                abkuerzung_falsch[tag] = "Abkürzung sagt kein Sprung, der Test kauft"
            continue
        t_e = pd.Timestamp(m.t[e])
        s = vb.signal(sym, std[std.index < t_e.floor("h")], t_e, float(m.o[e]), cfgs, fred=fred)
        if s["warten"]:
            wartet[tag] = s["ergebnis"]
            if tag in test:
                nur_test[tag] = s["ergebnis"]
            continue
        if s["ok"] and tag in test:
            beide += 1
            t = test[tag]
            ein_gleich += int(t["i0"]) == e and int(t["d"]) == s["richtung"] == 1
            stop_rel.append(abs(s["dist"] - float(t["sd"])) / float(t["sd"]))
            aus_gleich += pd.Timestamp(s["bis_utc"]) == pd.Timestamp(t["t_max"])
        elif s["ok"]:
            nur_bot[tag] = s["ergebnis"]
        elif tag in test:
            nur_test[tag] = s["ergebnis"]
    return {"markt": sym, "fassung": vb.FASSUNG[sym], "tage": len(tage),
            "test_signale": sum(1 for t in test if von <= t <= bis), "bot_signale": beide + len(nur_bot),
            "beide": beide, "einstieg_gleich": int(ein_gleich), "nur_bot": nur_bot, "nur_test": nur_test,
            "abkuerzung_falsch": abkuerzung_falsch, "kein_einstieg_im_test": kein_einstieg, "bot_wartet": wartet,
            "stop_abweichung_rel": {"groesste": round(max(stop_rel), 12) if stop_rel else 0.0},
            "ausstieg_gleich": int(aus_gleich)}


def main(argv: list[str]) -> int:
    if not argv:
        raise SystemExit(__doc__)
    arbeit = pathlib.Path(argv[0])
    cfgs = vb.lade_cfg(pruefen=True)
    if cfgs is None:
        raise SystemExit("Regeldateien der großen Runde passen nicht zu ihren Siegeln")
    ganz = "--ganz" in argv
    argv = [a for a in argv if a != "--ganz"]
    out = {"maerkte": {}, "abkuerzung": not ganz}
    for sym in argv[2:] or list(vb.MAERKTE):
        cfg = cfgs[vb.DURCHGANG[sym]]
        von, bis = cfg["fenster"]["von"], cfg["fenster"]["bis"]
        t0 = time.time()
        out["maerkte"][sym] = r = gegenprobe(sym, arbeit, cfgs, von, bis, abkuerzung=not ganz)
        r.update(von=von, bis=bis, sekunden=round(time.time() - t0, 1))
        print(json.dumps({k: (v if not isinstance(v, dict) or len(v) < 6 else f"{len(v)} Tage")
                          for k, v in r.items()}, ensure_ascii=False), flush=True)
    if len(argv) > 1:
        pathlib.Path(argv[1]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str) + "\n",
                                         encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
