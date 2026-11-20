"""Spiegel der Runde "Scalping mit Marktvorhersage" (Kirons Wunsch vom 20.11.2026 19:08 UTC).

Regeln: suche/VORAB_vorhersage_spiegel.yaml (versiegelt im Protokoll, bevor die Spiegel mit Kursen ab 2024 gerechnet
wurden). Alles, was dort nicht steht, kommt unverändert aus der versiegelten Vorlage suche/VORAB_vorhersage_scalp.yaml
und aus suche/vorhersage_scalp.py (Tage, Vorhersagen, Bollinger-Band, Kennzahlen, Hebel-Auskunft).

Ein Spiegel handelt an denselben Tagen und Marken wie die Vorlage, aber in der Gegenrichtung. Der alte Stop wird das
Ziel, das alte Ziel wird der Stop. Neu sind hier nur:

- die gespiegelte Leiter: Stop-Orders an den drei Marken, Stop je Stufe im alten Ziel-Abstand, gemeinsames Ziel am
  alten Stop, nach dem Ziel ist der Tag vorbei, nach einem Stop liegt die Stufe wieder bereit,
- das gespiegelte Band: dasselbe Signal, Marktorder in der Gegenrichtung, Stop und Ziel getauscht,
- der Zufallsvergleich der zwei Spiegel ohne Vorhersage mit zufälliger Richtung je Tag.

Aufruf:
    python -m suche.vorhersage_spiegel --festlegen                 schreibt die Prüfsumme der Regeldatei ins Protokoll
    python -m suche.vorhersage_spiegel entwicklung <Arbeit>        nur Kurse bis Ende 2023, prüft das Programm, kein Ergebnis
    python -m suche.vorhersage_spiegel probelauf <Arbeit> <Saat>   ganze Rechnung auf erfundenen Märkten ohne Vorteil
    python -m suche.vorhersage_spiegel rechnen <Arbeit>            die Rechnung (nur mit passenden Prüfsummen)
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd
import yaml

from suche import grosse_runde as gr
from suche import rueckblick as rb
from suche import vorhersage_scalp as vs
from suche.rueckblick import njit
from suche.runde1 import journal_add, journal_lines, last_value, sha256_text

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_vorhersage_spiegel.yaml"
KEY = "VORAB_vorhersage_spiegel sha256 "
ERGEBNIS = ROOT / "suche" / "ergebnis_vorhersage_spiegel"


def lade_vorab(pruefen: bool = True) -> dict:
    """Die Vorlage (mit ihrem Siegel) und darüber die Teile dieser Regeldatei."""
    text = VORAB.read_text(encoding="utf-8")
    if pruefen and last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("VORAB_vorhersage_spiegel.yaml passt nicht zur Prüfsumme im Protokoll. Erst versiegeln, dann rechnen.")
    neu = yaml.safe_load(text)["vorhersage_spiegel"]
    if sha256_text(vs.VORAB.read_text(encoding="utf-8")) != neu["vorlage"]["sha256"]:
        raise SystemExit("Die Vorlage suche/VORAB_vorhersage_scalp.yaml passt nicht zur Prüfsumme in der Spiegel-Regel.")
    alt = vs.lade_vorab(pruefen=pruefen)
    return {**alt, "varianten": neu["varianten"], "kontrollen": {}, "zwilling": neu["zwilling"],
            "huerden": neu["huerden"], "hebel": neu["hebel"], "spiegel": neu["spiegel"]}


# ---------------------------------------------------------------------------------------------------------------------
# Die gespiegelte Leiter an einem Tag. d ist die Richtung der Vorlage, gehandelt wird -d. art_aus: 1 Ziel, 2 Stop, 3 Zeit.

@njit(cache=True)
def _leiter_spiegel(o, h, l, c, sp, j0, j_ein_bis, j_aus, d, ref, atr, abstand, stufen, sd_plan, ziel_atr, max_ein,
                    kf, rutsch, o_i0, o_ex, o_e, o_pnl, o_sd, o_art):
    """Reihenfolge in jeder Kerze (vorsichtig): erst neue Füllungen, dann die Stops aller offenen Stufen, erst danach
    das gemeinsame Ziel. In der Kerze der Füllung zählt für den Stop nur der Teil der Kerze nach der Füllung."""
    tp = ref - d * ziel_atr * atr                          # alter gemeinsamer Stop; Spiegel-Verkauf: Ask-Marke, -Kauf: Bid
    lv = np.empty(stufen)
    for k in range(stufen):
        lv[k] = ref - d * (k + 1) * abstand * atr          # Bid-Marke der Stop-Order
    offen = np.zeros(stufen, np.bool_)
    frei_ab = np.full(stufen, j0)
    e = np.zeros(stufen)
    sl = np.zeros(stufen)
    i0 = np.zeros(stufen, np.int64)
    n_ein = 0
    nt = 0
    for j in range(j0, j_aus + 1):
        s = sp[j] * kf
        if j == j_aus:                                     # Zeit: alles Offene zur Eröffnung schließen
            for k in range(stufen):
                if offen[k]:
                    pnl = (e[k] - (o[j] + s)) if d > 0 else (o[j] - e[k])
                    o_i0[nt], o_ex[nt], o_e[nt], o_pnl[nt], o_sd[nt], o_art[nt] = i0[k], j, e[k], pnl, sd_plan, 3
                    nt += 1
                    offen[k] = False
            break
        if j <= j_ein_bis:                                 # 1. neue Füllungen (Stop-Orders in der Gegenrichtung)
            for k in range(stufen):
                if offen[k] or j < frei_ab[k] or n_ein >= max_ein:
                    continue
                if d > 0:                                  # Vorlage kauft, Spiegel verkauft, wenn der Bid fällt
                    if l[j] <= lv[k]:
                        r0 = min(lv[k], o[j])
                        offen[k], e[k], i0[k] = True, r0 - rutsch * s, j
                        sl[k] = r0 + sd_plan               # Ask-Marke
                        n_ein += 1
                else:                                      # Vorlage verkauft, Spiegel kauft, wenn der Bid steigt
                    if h[j] >= lv[k]:
                        r0 = max(lv[k], o[j])
                        offen[k], e[k], i0[k] = True, r0 + s + rutsch * s, j
                        sl[k] = r0 - sd_plan               # Bid-Marke
                        n_ein += 1
        nah_hoch = (h[j] - o[j]) < (o[j] - l[j])
        for k in range(stufen):                            # 2. Stops je Stufe
            if not offen[k]:
                continue
            if i0[k] == j:
                if d > 0:
                    hoch = h[j] if (o[j] <= lv[k] or not nah_hoch) else c[j]
                    getroffen = hoch + s >= sl[k]
                    px = sl[k] + rutsch * s
                else:
                    tief = l[j] if (o[j] >= lv[k] or nah_hoch) else c[j]
                    getroffen = tief <= sl[k]
                    px = sl[k] - rutsch * s
            else:
                if d > 0:
                    getroffen = h[j] + s >= sl[k]
                    px = max(sl[k], o[j] + s) + rutsch * s
                else:
                    getroffen = l[j] <= sl[k]
                    px = min(sl[k], o[j]) - rutsch * s
            if getroffen:
                pnl = (e[k] - px) if d > 0 else (px - e[k])
                o_i0[nt], o_ex[nt], o_e[nt], o_pnl[nt], o_sd[nt], o_art[nt] = i0[k], j, e[k], pnl, sd_plan, 2
                nt += 1
                offen[k] = False
                frei_ab[k] = j + 1
        treffer = (l[j] + s <= tp) if d > 0 else (h[j] >= tp)
        if treffer:                                        # 3. gemeinsames Ziel, danach ist der Tag vorbei
            for k in range(stufen):
                if offen[k]:
                    pnl = (e[k] - tp) if d > 0 else (tp - e[k])
                    o_i0[nt], o_ex[nt], o_e[nt], o_pnl[nt], o_sd[nt], o_art[nt] = i0[k], j, e[k], pnl, sd_plan, 1
                    nt += 1
                    offen[k] = False
            break
    return nt


def tag_trades(m: gr.Markt, cfg: dict, einstieg: str, stop_atr: float, d: int, kf: float) -> list[tuple]:
    """Alle Spiegel-Trades jedes gültigen Tags zur Richtung d der Vorlage. Rückgabe je Trade: (g, i0, ex, e, pnl, sd, art)."""
    p = cfg["einstiege"][einstieg]
    rutsch = float(cfg["kosten"]["rutschen_spread"])
    tg = vs.tage(m, cfg)
    out = []
    if p["art"] == "leiter":
        cap = 2 * int(p["max_einstiege"]) + int(p["stufen"])
        bufs = [np.zeros(cap, np.int64), np.zeros(cap, np.int64), np.zeros(cap), np.zeros(cap), np.zeros(cap),
                np.zeros(cap, np.int64)]
        for g in np.flatnonzero(tg["ok"]):
            j0 = int(tg["j0"][g])
            atr = float(m.atr_vor[g])
            nt = _leiter_spiegel(m.o, m.h, m.l, m.c, m.sp, j0, int(tg["ein_bis"][g]), int(tg["j_aus"][g]), d,
                                 float(m.o[j0]), atr, float(p["abstand_atr"]), int(p["stufen"]), float(stop_atr) * atr,
                                 float(p["stop_atr"]), int(p["max_einstiege"]), kf, rutsch, *bufs)
            for q in range(nt):
                out.append((int(g), int(bufs[0][q]), int(bufs[1][q]), float(bufs[2][q]), float(bufs[3][q]),
                            float(bufs[4][q]), int(bufs[5][q])))
        return out
    if p["art"] == "band":
        unten, oben = m._band if hasattr(m, "_band") else vs._bollinger(m, p)
        m._band = (unten, oben)
        for g in np.flatnonzero(tg["ok"]):
            j0, bis, j_aus = int(tg["j0"][g]), int(tg["ein_bis"][g]), int(tg["j_aus"][g])
            ref, atr = float(m.o[j0]), float(m.atr_vor[g])
            sd, zd = float(stop_atr) * atr, float(p["stop_atr"]) * atr      # getauscht: altes Ziel ist Stop
            j, n_ein = j0, 0
            while j < bis and n_ein < int(p["max_einstiege"]):
                if d > 0:
                    sig = m.c[j] < unten[j] and m.c[j] < ref
                else:
                    sig = m.c[j] > oben[j] and m.c[j] > ref
                if not sig:
                    j += 1
                    continue
                i0 = j + 1
                ex, pnl, e = rb._trade(m.o, m.h, m.l, m.c, m.sp, i0, -d, np.nan, sd, zd, j_aus, kf, rutsch)
                n_ein += 1
                art = 3 if ex >= j_aus else (1 if pnl > 0 else 2)
                out.append((int(g), int(i0), int(ex), float(e), float(pnl), sd, art))
                if art == 1:                               # altes Stop-Ende: nach dem Ziel ist der Tag vorbei
                    break
                j = max(ex, i0)
        return out
    raise SystemExit(f"unbekannter Einstieg {einstieg}")


def tabelle(m: gr.Markt, cfg: dict, einstieg: str, stop_atr: float) -> pd.DataFrame:
    """Spiegel-Trades zu beiden Richtungen der Vorlage an jedem Tag, mit normalen und 1,5-fachen Kosten.
    Spalte richtung = Richtung der Vorlage (danach wählt die Vorhersage), gehandelt wird die Gegenrichtung."""
    teile = []
    for d in (1, -1):
        for kf, spalte in ((1.0, "R"), (float(cfg["kosten"]["robust_faktor"]), "R_robust")):
            rows = tag_trades(m, cfg, einstieg, stop_atr, d, kf)
            df = pd.DataFrame(rows, columns=["g", "i0", "ex", "einstieg", "pnl", "stop_abstand", "art"])
            df["R"] = df["pnl"] / df["stop_abstand"]
            df["richtung"], df["kf"] = d, spalte
            teile.append(df)
    return pd.concat(teile, ignore_index=True)


# ---------------------------------------------------------------------------------------------------------------------
# Rechnung

def rechne(arbeit: pathlib.Path, cfg: dict, bis, fenster, mitte, saat=None, mit_zwillingen=True):
    f0, f1 = np.datetime64(fenster[0]), np.datetime64(fenster[1])
    maerkte = {s: gr.Markt(s, arbeit, cfg, bis, saat) for s in cfg["maerkte"]}
    tab: dict = {}
    ergebnis, alle = {}, []
    for name, v in cfg["varianten"].items():
        e_, z_ = v["einstieg"], float(v["stop_atr"])
        teile, tag_summen = [], {}
        for sym, m in maerkte.items():
            if (sym, e_, z_) not in tab:
                tab[(sym, e_, z_)] = tabelle(m, cfg, e_, z_)
            t = tab[(sym, e_, z_)]
            rich = vs.richtung(m, cfg, v["vorhersage"])
            gtag = m.gtag
            im = (gtag >= f0.astype("datetime64[D]")) & (gtag <= f1.astype("datetime64[D]"))
            tn = t[t["kf"] == "R"]
            s_lang = np.bincount(tn.loc[tn["richtung"] > 0, "g"], weights=tn.loc[tn["richtung"] > 0, "R"], minlength=len(gtag))
            s_kurz = np.bincount(tn.loc[tn["richtung"] < 0, "g"], weights=tn.loc[tn["richtung"] < 0, "R"], minlength=len(gtag))
            tag_summen[sym] = (np.flatnonzero(im), rich, s_lang, s_kurz)
            gewaehlt = rich[t["g"].to_numpy()] == t["richtung"].to_numpy()
            sel = t[gewaehlt & (rich[t["g"].to_numpy()] != 0)].copy()
            sel["richtung"] = -sel["richtung"]             # ab hier die gehandelte Richtung
            sel["markt"], sel["tag"] = sym, gtag[sel["g"].to_numpy()]
            sel["ein_utc"], sel["aus_utc"] = m.t[sel["i0"].to_numpy()], m.t[sel["ex"].to_numpy()]
            sel["art_aus"] = sel["art"]
            teile.append(sel)
        df = pd.concat(teile, ignore_index=True)
        tag = df["tag"].to_numpy().astype("datetime64[D]")
        im = (tag >= f0.astype("datetime64[D]")) & (tag <= f1.astype("datetime64[D]"))
        norm, rob = df[(df["kf"] == "R") & im].sort_values("ein_utc"), df[(df["kf"] == "R_robust") & im]
        alt = df[(df["kf"] == "R") & (tag < f0.astype("datetime64[D]"))]
        if norm.empty:
            ergebnis[name] = {"trades": 0, "urteil": "durchgefallen"}
            continue
        e = {"vorlage": v["vorlage"], "vorhersage": v["vorhersage"], "einstieg": e_, "stop_atr": z_,
             **vs.kennzahlen(norm, rob["R"].to_numpy(float), mitte, f0, f1, cfg["maerkte"]),
             "auskunft_vor_fenster": {"trades": int(len(alt)), "gewinnfaktor": vs._rund(rb.pf(alt["R"])) if len(alt) else None,
                                      "summe_R": vs._rund(alt["R"].sum()) if len(alt) else None}}
        if mit_zwillingen:
            n_min = min(len(x[0]) for x in tag_summen.values())
            schritte = np.arange(1, n_min - int(cfg["zwilling"]["sperre_davor_tage"]))
            ohne = cfg["vorhersagen"][v["vorhersage"]]["art"] == "immer_kauf"
            rng = np.random.default_rng(int(cfg["zwilling"]["saat"]))
            summen = np.zeros(len(schritte))
            echt = 0.0
            for sym, (gf, rich, s_lang, s_kurz) in tag_summen.items():
                rf = rich[gf]
                wert = np.where(rf > 0, s_lang[gf], np.where(rf < 0, s_kurz[gf], 0.0))
                echt += float(wert.sum())
                for q, k in enumerate(schritte):
                    rk = rng.choice(np.array([-1, 1]), size=len(rf)) if ohne else np.roll(rf, int(k))
                    summen[q] += float(np.where(rk > 0, s_lang[gf], np.where(rk < 0, s_kurz[gf], 0.0)).sum())
            besser = int((summen >= echt - 1e-9).sum())
            sa = float(summen.std(ddof=1))
            e["zufall"] = {"art": "zufällige Richtung je Tag" if ohne else "verschobene Vorhersage",
                           "laeufe": int(len(schritte)), "geschlagen_pct": vs._rund(100.0 * (summen < echt - 1e-9).mean(), 1),
                           "p": (1 + besser) / (len(schritte) + 1), "echt_R": vs._rund(echt), "mittel_R": vs._rund(summen.mean()),
                           "streuung_R": vs._rund(sa), "z": vs._rund((echt - summen.mean()) / sa if sa > 0 else 0.0),
                           "summe_fuer_z3": vs._rund(summen.mean() + 3 * sa)}
        ergebnis[name] = e
        alle.append(norm.assign(variante=name, R_robust=np.nan))
    gr.urteile(ergebnis, cfg)
    trades = pd.concat(alle, ignore_index=True)[vs.SPALTEN] if alle else pd.DataFrame(columns=vs.SPALTEN)
    return ergebnis, trades, maerkte


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--festlegen":
        lade_vorab(pruefen=False)                          # prüft die Prüfsumme der Vorlage
        zeile = KEY + sha256_text(VORAB.read_text(encoding="utf-8"))
        journal_add(zeile)
        print(zeile)
        return 0
    modus, arbeit = argv[0], pathlib.Path(argv[1])
    if modus == "entwicklung":
        cfg = lade_vorab(pruefen=False)
        cfg["maerkte"] = [s for s in cfg["maerkte"] if s != "GRXEUR"]
        fe = ("2021-03-01", "2023-12-29")
        erg, tr, mk = rechne(arbeit, cfg, "2023-12-31T23:59", fe, "2022-08-01")
        ziel, kopf = arbeit / "entwicklung_vorhersage_spiegel", {"modus": "entwicklung, nur Kurse bis Ende 2023, kein Ergebnis"}
    elif modus == "probelauf":
        cfg = lade_vorab(pruefen=False)
        saat = int(argv[2])
        f = cfg["fenster"]
        fe = (f["von"], f["bis"])
        erg, tr, mk = rechne(arbeit, cfg, None, fe, f["mitte"], saat=saat)
        ziel, kopf = arbeit / f"probelauf_vorhersage_spiegel_{saat}", {"modus": "erfundener Markt ohne Vorteil", "saat": saat}
    elif modus == "rechnen":
        cfg = lade_vorab(pruefen=True)
        f = cfg["fenster"]
        fe = (f["von"], f["bis"])
        erg, tr, mk = rechne(arbeit, cfg, None, fe, f["mitte"])
        ziel, kopf = ERGEBNIS, {"modus": "Rechnung", "vorab_sha256": sha256_text(VORAB.read_text(encoding="utf-8")),
                                "vorlage_sha256": sha256_text(vs.VORAB.read_text(encoding="utf-8")), "fenster": f}
    else:
        raise SystemExit(__doc__)
    hb = vs.hebel(tr, cfg, fe)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(str(ziel) + ".json").write_text(json.dumps({"kopf": kopf, "varianten": erg, "hebel": hb}, indent=1,
                                                            ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    tr.drop(columns=["R_robust"]).to_csv(str(ziel) + "_trades.csv.gz", index=False, float_format="%.6g")
    for n, e in erg.items():
        z = e.get("zufall", {})
        print(f"{n:28s} {e.get('trades', 0):5d} T {e.get('trades_je_woche')}/Wo  GF {e.get('gewinnfaktor')}  rob "
              f"{e.get('gewinnfaktor_robust')}  Summe {e.get('summe_R')}  Treffer {e.get('trefferquote')}  "
              f"H {e.get('haelfte_1', {}).get('gewinnfaktor')}/{e.get('haelfte_2', {}).get('gewinnfaktor')}  "
              f"2026 {e.get('jahr_2026', {}).get('gewinnfaktor')}  Zufall {z.get('geschlagen_pct')} %  z {z.get('z')}  "
              f"Aus {e.get('ausstieg')}  -> {e.get('urteil')} {e.get('durchgefallen_bei', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
