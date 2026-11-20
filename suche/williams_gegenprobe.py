"""Gegenprobe für den Demo-Bot williams-us (suche/williams_bot.py): Bot gegen Test, Tag für Tag.

    python -m suche.williams_gegenprobe <Arbeit> [<Ausgabe.json>] [<Markt> ...]

<Arbeit> ist der Ordner mit den Kursdateien des Tests (SPXUSD.npz, NSXUSD.npz, gebaut von
python -m suche.youtube_runde daten <Arbeit>).

Der Bot bekommt vom Broker die letzten 1.000 5-Minuten-Kerzen und davor Stundenkerzen. Diese Gegenprobe baut beides aus
den 5-Minuten-Kerzen des Tests, gibt es der Rechnung des Bots (williams_bot.signal) an jedem Handelstag zur Kerze um
16:00 New York und spielt den Bot durch: höchstens ein Trade je Markt, Ausstieg nach dem Signal des Bots, Stop wie im
Test (suche/rueckblick._trade bis zur Kerze um 16:00). Dann vergleicht sie jeden Trade des Bots (Einstiegskerze,
Stop-Abstand, Ausstiegskerze) mit den Trades des Tests (suche/rueckblick.echte_trades auf
suche/youtube_runde.regel_williams).
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd

from suche import modell_indizes_gegenprobe as mg
from suche import rueckblick as rb
from suche import williams_bot as wb
from suche import youtube_runde as yr

VORLAUF = pd.Timedelta(days=30)       # so lange vor dem Fenster spielt der Bot schon mit (ein offener Trade des Tests)


def gegenprobe(sym: str, arbeit: pathlib.Path, cfg: dict, von: str, bis: str) -> dict:
    """Bot gegen Test auf einem Markt, Handelstage von von bis bis (Trades mit Einstieg in diesem Fenster zählen)."""
    p = wb.regel(cfg)
    m = yr.Markt(sym, arbeit, cfg, cfg["fenster"]["bis"])
    test = rb.echte_trades(m, yr.regel_williams(m, cfg), cfg)
    s = wb.sitzungen(m, p)
    std = mg.stunden_aus(m)
    fuenf = pd.DataFrame({"open": m.o, "high": m.h, "low": m.l, "close": m.c}, index=pd.DatetimeIndex(m.t))
    rutsch = cfg["kosten"]["rutschen_spread"]
    von_d, bis_d = np.datetime64(von), np.datetime64(bis)
    start = np.datetime64(pd.Timestamp(von) - VORLAUF)
    offen, bot, wartet, tage = None, [], {}, 0
    for k in range(len(s["C"])):
        e, d = int(s["i_s"][k]), s["datum"][k]
        if e < 0 or d < start or d > bis_d:
            continue
        tage += int(d >= von_d)
        if offen is not None:                                  # Stop beim Broker vor der Kerze um 16:00?
            ex, _, _ = rb._trade(m.o, m.h, m.l, m.c, m.sp, offen["i0"], 1, np.nan, offen["sd"], 0.0, e, 1.0, rutsch)
            if ex < e:
                bot.append({**offen, "ex": int(ex), "grund": "stop"})
                offen = None
        tag = pd.Timestamp(d)
        t_s = wb.schluss(tag, p)
        f = fuenf[fuenf.index < t_s].iloc[-wb.FUENF_MAX:]
        sig = wb.signal(sym, std[std.index < t_s], f, pd.Timestamp(m.t[e]), float(m.o[e]), cfg,
                        offen_seit=offen["tag"] if offen else None,
                        geprueft_bis=offen.get("geprueft") if offen else None)
        if sig["warten"]:
            wartet[str(d)] = sig["ergebnis"]
            continue
        if offen is not None:
            if not sig["raus"]:
                offen["geprueft"] = str(d)
                continue
            bot.append({**offen, "ex": e, "grund": sig["grund"]})
            offen = None
            if not sig.get("faellig_seit"):
                continue                                       # gleiche Kerze: der Test kauft dort nicht
        if sig["kauf"]:
            offen = {"i0": e, "sd": float(sig["dist"]), "tag": str(d)}
    if offen is not None:
        ex, _, _ = rb._trade(m.o, m.h, m.l, m.c, m.sp, offen["i0"], 1, np.nan, offen["sd"], 0.0, m.n, 1.0, rutsch)
        bot.append({**offen, "ex": int(ex), "grund": "Ende der Daten"})
    im = lambda t: von_d <= m.t[int(t)] <= bis_d + np.timedelta64(1, "D")      # noqa: E731
    b = {int(x["i0"]): x for x in bot if im(x["i0"])}
    t = {int(r.i0): r for r in test.itertuples() if im(r.i0)}
    beide = sorted(set(b) & set(t))
    stop_rel = [abs(b[i]["sd"] - float(t[i].stop_abstand)) / float(t[i].stop_abstand) for i in beide]
    aus = {i: int(np.searchsorted(m.t, np.datetime64(pd.Timestamp(t[i].aus_utc), "ns"))) for i in beide}
    aus_gleich = sum(int(b[i]["ex"]) == aus[i] for i in beide)
    aus_anders = {str(m.t[i])[:16]: {"bot": str(m.t[b[i]["ex"]])[:16], "test": str(t[i].aus_utc)[:16]}
                  for i in beide if int(b[i]["ex"]) != aus[i]}
    gruende: dict = {}
    for i in beide:
        gruende[b[i]["grund"]] = gruende.get(b[i]["grund"], 0) + 1
    return {"markt": sym, "tage": tage, "test_trades": len(t), "bot_trades": len(b), "beide": len(beide),
            "nur_bot": [str(m.t[i])[:16] for i in sorted(set(b) - set(t))],
            "nur_test": [str(m.t[i])[:16] for i in sorted(set(t) - set(b))],
            "bot_wartet": wartet, "stop_abweichung_rel": {"groesste": round(max(stop_rel), 12) if stop_rel else 0.0},
            "ausstieg_gleich": int(aus_gleich), "ausstieg_anders": aus_anders, "gruende": gruende}


def main(argv: list[str]) -> int:
    if not argv:
        raise SystemExit(__doc__)
    arbeit = pathlib.Path(argv[0])
    cfg = wb.lade_cfg(pruefen=True)
    if cfg is None:
        raise SystemExit("Regeldatei der YouTube-Runde passt nicht zu ihrem Siegel")
    von, bis = cfg["fenster"]["von"], cfg["fenster"]["bis"]
    out = {"maerkte": {}}
    for sym in argv[2:] or list(wb.MAERKTE):
        t0 = time.time()
        out["maerkte"][sym] = r = gegenprobe(sym, arbeit, cfg, von, bis)
        r.update(von=von, bis=bis, sekunden=round(time.time() - t0, 1))
        print(json.dumps({k: (v if not isinstance(v, (dict, list)) or len(v) < 6 else f"{len(v)} Einträge")
                          for k, v in r.items()}, ensure_ascii=False), flush=True)
    if len(argv) > 1:
        pathlib.Path(argv[1]).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str) + "\n",
                                         encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
