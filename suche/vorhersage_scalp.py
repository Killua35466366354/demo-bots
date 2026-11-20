"""Scalping mit Marktvorhersage (Kirons Wunsch vom 20.11.2026): kleine Trades nur in der vorhergesagten Richtung.

Regeln: suche/VORAB_vorhersage_scalp.yaml (versiegelt im Protokoll, bevor mit Kursen ab 2024 gerechnet wurde).
Die Kosten und ein einzelner Trade zur Marktorder kommen aus suche/rueckblick.py, die Vorhersagen (Modell, VIX-Sprung)
aus suche/grosse_runde.py, unverändert. Neu sind hier nur:

- die Leiter: drei Limit-Orders gegen die Vorhersage mit gemeinsamem Stop, eine Stufe liegt nach ihrem Ziel wieder bereit,
- das Band: Einstieg zur Marktorder nach einem Schluss außerhalb des Bollinger-Bands, gegen die Vorhersage,
- der Zufallsvergleich mit verschobener Vorhersage (die Trades werden für jede Verschiebung neu gerechnet),
- die Hebel-Auskunft: dieselben Trades mit 1 bis 20 % Risiko je Trade auf 1.000 €.

Jeder Tag wird für Kauf und für Verkauf einmal gerechnet. Eine Vorhersage wählt dann je Tag eine der beiden Rechnungen.
So kostet jede Verschiebung im Zufallsvergleich nur eine Summe.

Aufruf:
    python -m suche.vorhersage_scalp --festlegen                 schreibt die Prüfsumme der Regeldatei ins Protokoll
    python -m suche.vorhersage_scalp entwicklung <Arbeit>        nur Kurse bis Ende 2023, prüft das Programm, kein Ergebnis
    python -m suche.vorhersage_scalp probelauf <Arbeit> <Saat>   ganze Rechnung auf erfundenen Märkten ohne Vorteil
    python -m suche.vorhersage_scalp rechnen <Arbeit>            die Rechnung (nur mit passender Prüfsumme)
    python -m suche.vorhersage_scalp hebel -                     nur die Hebel-Auskunft neu aus den gespeicherten Trades

Die Kursdateien baut python -m suche.rueckblick_daten <Arbeit> SPXUSD NSXUSD GRXEUR UKXGBP JPXJPY.
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
from suche import youtube_runde2 as y2
from suche.rueckblick import njit
from suche.runde1 import journal_add, journal_lines, last_value, sha256_text

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_vorhersage_scalp.yaml"
KEY = "VORAB_vorhersage_scalp sha256 "
ERGEBNIS = ROOT / "suche" / "ergebnis_vorhersage_scalp"
SPALTEN = ["variante", "markt", "tag", "ein_utc", "aus_utc", "richtung", "einstieg", "stop_abstand", "R", "R_robust",
           "art_aus"]


def lade_vorab(pruefen: bool = True) -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if pruefen and last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("VORAB_vorhersage_scalp.yaml passt nicht zur Prüfsumme im Protokoll. Erst versiegeln, dann rechnen.")
    return yaml.safe_load(text)["vorhersage_scalp"]


# ---------------------------------------------------------------------------------------------------------------------
# Die Leiter an einem Tag in einer Richtung. art_aus: 1 Ziel, 2 Stop, 3 Zeit.

@njit(cache=True)
def _leiter(o, h, l, sp, j0, j_ein_bis, j_aus, d, ref, atr, abstand, stufen, ziel_atr, stop_atr, max_ein, kf, rutsch,
            o_i0, o_ex, o_e, o_pnl, o_sd, o_art):
    """Reihenfolge in jeder Kerze (vorsichtig): erst neue Füllungen, dann der gemeinsame Stop für alle offenen Stufen
    (auch die eben gefüllten), erst danach die Ziele der Stufen aus früheren Kerzen."""
    stop = ref - d * stop_atr * atr                        # Kauf: Bid-Marke, Verkauf: Ask-Marke
    lv = np.empty(stufen)
    sd = np.empty(stufen)
    for k in range(stufen):
        lv[k] = ref - d * (k + 1) * abstand * atr          # Kauf: Ask-Marke, Verkauf: Bid-Marke
        sd[k] = abs(lv[k] - stop)
    offen = np.zeros(stufen, np.bool_)
    frei_ab = np.full(stufen, j0)
    e = np.zeros(stufen)
    zt = np.zeros(stufen)
    i0 = np.zeros(stufen, np.int64)
    n_ein = 0
    nt = 0
    for j in range(j0, j_aus + 1):
        s = sp[j] * kf
        if j == j_aus:                                     # Zeit: alles Offene zur Eröffnung schließen
            for k in range(stufen):
                if offen[k]:
                    pnl = (o[j] - e[k]) if d > 0 else (e[k] - (o[j] + s))
                    o_i0[nt], o_ex[nt], o_e[nt], o_pnl[nt], o_sd[nt], o_art[nt] = i0[k], j, e[k], pnl, sd[k], 3
                    nt += 1
                    offen[k] = False
            break
        if j <= j_ein_bis:                                 # 1. neue Füllungen
            for k in range(stufen):
                if offen[k] or j < frei_ab[k] or n_ein >= max_ein:
                    continue
                if d > 0:
                    if l[j] + s <= lv[k]:
                        offen[k], e[k], i0[k] = True, min(lv[k], o[j] + s), j
                        zt[k] = e[k] - s + ziel_atr * atr
                        n_ein += 1
                else:
                    if h[j] >= lv[k]:
                        offen[k], e[k], i0[k] = True, max(lv[k], o[j]), j
                        zt[k] = e[k] - ziel_atr * atr
                        n_ein += 1
        if d > 0:                                          # 2. gemeinsamer Stop
            getroffen = l[j] <= stop
            px = min(stop, o[j]) - rutsch * s
        else:
            getroffen = h[j] + s >= stop
            px = max(stop, o[j] + s) + rutsch * s
        if getroffen:
            for k in range(stufen):
                if offen[k]:
                    pnl = (px - e[k]) if d > 0 else (e[k] - px)
                    o_i0[nt], o_ex[nt], o_e[nt], o_pnl[nt], o_sd[nt], o_art[nt] = i0[k], j, e[k], pnl, sd[k], 2
                    nt += 1
                    offen[k] = False
            break
        for k in range(stufen):                            # 3. Ziele der Stufen aus früheren Kerzen
            if not offen[k] or i0[k] >= j:
                continue
            treffer = (h[j] >= zt[k]) if d > 0 else (l[j] + s <= zt[k])
            if treffer:
                pnl = (zt[k] - e[k]) if d > 0 else (e[k] - zt[k])
                o_i0[nt], o_ex[nt], o_e[nt], o_pnl[nt], o_sd[nt], o_art[nt] = i0[k], j, e[k], pnl, sd[k], 1
                nt += 1
                offen[k] = False
                frei_ab[k] = j + 1
    return nt


# ---------------------------------------------------------------------------------------------------------------------
# Tage und Vorhersagen

def tage(m: gr.Markt, cfg: dict) -> dict:
    """Je gültigem Handelstag: Bezugskerze (ab 18:00 New York), letzte Kerze für Einstiege (vor 15:00 New York) und
    Ausstiegskerze (ab 15:55 New York). ok nur, wenn alle drei in diesem Handelstag liegen."""
    th = cfg["tageshandel"]
    j0, aus = gr.tages_einstieg(m, cfg)
    j_aus = np.searchsorted(m.t, aus)
    ein_bis = np.searchsorted(m.t, y2._ny_utc(pd.DatetimeIndex(m.gtag), int(th["einstieg_bis_min"]))) - 1
    jc = np.minimum(j_aus, m.n - 1)
    ok = (j0 >= 0) & (j_aus < m.n) & (m.tix[jc] == m.gi) & (ein_bis >= np.maximum(j0, 0)) & np.isfinite(m.atr_vor)
    ok &= np.arange(len(m.gi)) >= 1
    return {"j0": j0, "ein_bis": ein_bis, "j_aus": j_aus, "ok": ok}


def richtung(m: gr.Markt, cfg: dict, name: str) -> np.ndarray:
    q = cfg["vorhersagen"][name]
    art = q["art"]
    if art == "modell":
        key = (name, str(m.arbeit), m.bis, m.saat)
        if key not in gr._MODELLE:
            p = {**q, "stop_atr": 2.0}
            gr.regel_modell(m, cfg, p, cfg["maerkte"], name)
        return np.asarray(gr._MODELLE[key][m.sym], np.int64)
    if art == "trend":
        return np.asarray(m.trend_vor, np.int64)
    if art == "reihe":
        return gr.richtung_reihe(m.gtag, q)
    if art == "immer_kauf":
        return np.ones(len(m.gtag), np.int64)
    raise SystemExit(f"unbekannte Vorhersage {name}")


def _bollinger(m: gr.Markt, p: dict) -> tuple[np.ndarray, np.ndarray]:
    c = pd.Series(m.c)
    mitte = c.rolling(int(p["fenster"])).mean()
    breite = float(p["breite"]) * c.rolling(int(p["fenster"])).std(ddof=0)
    return (mitte - breite).to_numpy(), (mitte + breite).to_numpy()


def tag_trades(m: gr.Markt, cfg: dict, einstieg: str, ziel_atr: float, d: int, kf: float) -> list[tuple]:
    """Alle Trades jedes gültigen Tags in Richtung d. Rückgabe je Trade: (g, i0, ex, e, pnl, sd, art)."""
    p = cfg["einstiege"][einstieg]
    rutsch = float(cfg["kosten"]["rutschen_spread"])
    tg = tage(m, cfg)
    out = []
    if p["art"] == "leiter":
        cap = 2 * int(p["max_einstiege"]) + int(p["stufen"])
        bufs = [np.zeros(cap, np.int64), np.zeros(cap, np.int64), np.zeros(cap), np.zeros(cap), np.zeros(cap),
                np.zeros(cap, np.int64)]
        for g in np.flatnonzero(tg["ok"]):
            j0 = int(tg["j0"][g])
            nt = _leiter(m.o, m.h, m.l, m.sp, j0, int(tg["ein_bis"][g]), int(tg["j_aus"][g]), d, float(m.o[j0]),
                         float(m.atr_vor[g]), float(p["abstand_atr"]), int(p["stufen"]), float(ziel_atr),
                         float(p["stop_atr"]), int(p["max_einstiege"]), kf, rutsch, *bufs)
            for q in range(nt):
                out.append((int(g), int(bufs[0][q]), int(bufs[1][q]), float(bufs[2][q]), float(bufs[3][q]),
                            float(bufs[4][q]), int(bufs[5][q])))
        return out
    if p["art"] == "band":
        unten, oben = m._band if hasattr(m, "_band") else _bollinger(m, p)
        m._band = (unten, oben)
        for g in np.flatnonzero(tg["ok"]):
            j0, bis, j_aus = int(tg["j0"][g]), int(tg["ein_bis"][g]), int(tg["j_aus"][g])
            ref, atr = float(m.o[j0]), float(m.atr_vor[g])
            sd, zd = float(p["stop_atr"]) * atr, float(ziel_atr) * atr
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
                ex, pnl, e = rb._trade(m.o, m.h, m.l, m.c, m.sp, i0, d, np.nan, sd, zd, j_aus, kf, rutsch)
                n_ein += 1
                art = 3 if ex >= j_aus else (1 if pnl > 0 else 2)
                out.append((int(g), int(i0), int(ex), float(e), float(pnl), sd, art))
                if art == 2:
                    break
                j = max(ex, i0)
        return out
    raise SystemExit(f"unbekannter Einstieg {einstieg}")


def tabelle(m: gr.Markt, cfg: dict, einstieg: str, ziel_atr: float) -> pd.DataFrame:
    """Trades für Kauf und Verkauf an jedem Tag, mit normalen und 1,5-fachen Kosten (gleiche Regel, eigene Füllungen)."""
    teile = []
    for d in (1, -1):
        for kf, spalte in ((1.0, "R"), (float(cfg["kosten"]["robust_faktor"]), "R_robust")):
            rows = tag_trades(m, cfg, einstieg, ziel_atr, d, kf)
            df = pd.DataFrame(rows, columns=["g", "i0", "ex", "einstieg", "pnl", "stop_abstand", "art"])
            df["R"] = df["pnl"] / df["stop_abstand"]
            df["richtung"], df["kf"] = d, spalte
            teile.append(df)
    return pd.concat(teile, ignore_index=True)


# ---------------------------------------------------------------------------------------------------------------------
# Rechnung

def _rund(x, n=2):
    return rb._rund(x, n)


def kennzahlen(w: pd.DataFrame, rr: np.ndarray, mitte: str, f0, f1, maerkte: list[str]) -> dict:
    r = w["R"].to_numpy(float)
    wtag = w["tag"].to_numpy().astype("datetime64[D]")
    h1, h2 = r[wtag < np.datetime64(mitte)], r[wtag >= np.datetime64(mitte)]
    j26 = r[wtag >= np.datetime64("2026-01-01")]
    wochen = max((f1 - f0) / np.timedelta64(7, "D"), 1.0)
    lang, kurz = r[w["richtung"].to_numpy() > 0], r[w["richtung"].to_numpy() < 0]
    ohne5 = np.sort(r)[:-5] if len(r) > 5 else np.array([])
    tage_n = int(len(np.unique(w["markt"].astype(str) + w["tag"].astype(str)))) if len(w) else 0
    arten = w["art_aus"].to_numpy() if len(w) else np.array([])
    return {"trades": int(len(r)), "trades_je_woche": _rund(len(r) / wochen), "markt_tage": tage_n,
            "gewinnfaktor": _rund(rb.pf(r)), "summe_R": _rund(r.sum()), "R_je_trade": _rund(r.mean() if len(r) else 0, 3),
            "trefferquote": _rund((r > 0).mean() if len(r) else 0), "gewinnfaktor_robust": _rund(rb.pf(rr)),
            "summe_R_robust": _rund(rr.sum()),
            "haelfte_1": {"trades": int(len(h1)), "gewinnfaktor": _rund(rb.pf(h1)), "summe_R": _rund(h1.sum())},
            "haelfte_2": {"trades": int(len(h2)), "gewinnfaktor": _rund(rb.pf(h2)), "summe_R": _rund(h2.sum())},
            "jahr_2026": {"trades": int(len(j26)), "gewinnfaktor": _rund(rb.pf(j26)), "summe_R": _rund(j26.sum())},
            "long": {"trades": int(len(lang)), "gewinnfaktor": _rund(rb.pf(lang)), "summe_R": _rund(lang.sum())},
            "short": {"trades": int(len(kurz)), "gewinnfaktor": _rund(rb.pf(kurz)), "summe_R": _rund(kurz.sum())},
            "ohne_5_beste": {"gewinnfaktor": _rund(rb.pf(ohne5)), "summe_R": _rund(ohne5.sum())},
            "ausstieg": {"ziel": int((arten == 1).sum()), "stop": int((arten == 2).sum()), "zeit": int((arten == 3).sum())},
            "groesster_verlust_R": _rund(r.min() if len(r) else 0, 3),
            "je_markt": {s: {"trades": int((w["markt"] == s).sum()), "gewinnfaktor": _rund(rb.pf(w.loc[w["markt"] == s, "R"])),
                             "summe_R": _rund(w.loc[w["markt"] == s, "R"].sum())} for s in maerkte}}


def rechne(arbeit: pathlib.Path, cfg: dict, bis, fenster, mitte, saat=None, mit_zwillingen=True):
    f0, f1 = np.datetime64(fenster[0]), np.datetime64(fenster[1])
    maerkte = {s: gr.Markt(s, arbeit, cfg, bis, saat) for s in cfg["maerkte"]}
    tab: dict = {}
    alle_var = {**cfg["varianten"], **cfg.get("kontrollen", {})}
    ergebnis, alle = {}, []
    for name, v in alle_var.items():
        e_, z_ = v["einstieg"], float(v["ziel_atr"])
        teile, tag_summen = [], {}
        for sym, m in maerkte.items():
            if (sym, e_, z_) not in tab:
                tab[(sym, e_, z_)] = tabelle(m, cfg, e_, z_)
            t = tab[(sym, e_, z_)]
            rich = richtung(m, cfg, v["vorhersage"])
            gtag = m.gtag
            im = (gtag >= f0.astype("datetime64[D]")) & (gtag <= f1.astype("datetime64[D]"))
            # Summe in R je Tag und Richtung (normale Kosten), für den Zufallsvergleich
            tn = t[t["kf"] == "R"]
            s_lang = np.bincount(tn.loc[tn["richtung"] > 0, "g"], weights=tn.loc[tn["richtung"] > 0, "R"], minlength=len(gtag))
            s_kurz = np.bincount(tn.loc[tn["richtung"] < 0, "g"], weights=tn.loc[tn["richtung"] < 0, "R"], minlength=len(gtag))
            tag_summen[sym] = (np.flatnonzero(im), rich, s_lang, s_kurz)
            gewaehlt = rich[t["g"].to_numpy()] == t["richtung"].to_numpy()
            sel = t[gewaehlt & (rich[t["g"].to_numpy()] != 0)].copy()
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
        e = {"vorhersage": v["vorhersage"], "einstieg": e_, "ziel_atr": z_, "kontrolle": name not in cfg["varianten"],
             **kennzahlen(norm, rob["R"].to_numpy(float), mitte, f0, f1, cfg["maerkte"]),
             "auskunft_vor_fenster": {"trades": int(len(alt)), "gewinnfaktor": _rund(rb.pf(alt["R"])) if len(alt) else None,
                                      "summe_R": _rund(alt["R"].sum()) if len(alt) else None}}
        if mit_zwillingen and name in cfg["varianten"]:
            n_min = min(len(x[0]) for x in tag_summen.values())
            schritte = np.arange(1, n_min - int(cfg["zwilling"]["sperre_davor_tage"]))
            summen = np.zeros(len(schritte))
            echt = 0.0
            for sym, (gf, rich, s_lang, s_kurz) in tag_summen.items():
                rf = rich[gf]
                wert = np.where(rf > 0, s_lang[gf], np.where(rf < 0, s_kurz[gf], 0.0))
                echt += float(wert.sum())
                for q, k in enumerate(schritte):
                    rk = np.roll(rf, int(k))
                    summen[q] += float(np.where(rk > 0, s_lang[gf], np.where(rk < 0, s_kurz[gf], 0.0)).sum())
            besser = int((summen >= echt - 1e-9).sum())
            sa = float(summen.std(ddof=1))
            e["zufall"] = {"laeufe": int(len(schritte)), "geschlagen_pct": _rund(100.0 * (summen < echt - 1e-9).mean(), 1),
                           "p": (1 + besser) / (len(schritte) + 1), "echt_R": _rund(echt), "mittel_R": _rund(summen.mean()),
                           "streuung_R": _rund(sa), "z": _rund((echt - summen.mean()) / sa if sa > 0 else 0.0),
                           "summe_fuer_z3": _rund(summen.mean() + 3 * sa)}
        ergebnis[name] = e
        norm = norm.assign(variante=name, R_robust=np.nan)
        alle.append(norm)
    nur_var = {n: e for n, e in ergebnis.items() if n in cfg["varianten"]}
    gr.urteile(nur_var, {**cfg, "varianten": cfg["varianten"]})
    for n, e in ergebnis.items():
        if n not in cfg["varianten"]:
            e["urteil"] = "Kontrolle, nur Auskunft"
    trades = pd.concat(alle, ignore_index=True)[SPALTEN] if alle else pd.DataFrame(columns=SPALTEN)
    return ergebnis, trades, maerkte


# ---------------------------------------------------------------------------------------------------------------------
# Hebel-Auskunft

def hebel(trades: pd.DataFrame, cfg: dict, fenster: tuple[str, str]) -> dict:
    """Konto mit festem Risiko-Anteil je Trade (Zinseszins), Trades in echter Reihenfolge. Margin = Positionswert durch
    Hebel. Positionswert = Risiko in Euro mal Einstieg durch Stop-Abstand (alles in Kurspunkten des Markts)."""
    h = cfg["hebel"]
    monate = float((np.datetime64(fenster[1]) - np.datetime64(fenster[0])) / np.timedelta64(1, "D")) / 30.44
    out = {}
    for name, w in trades.groupby("variante"):
        w = w.sort_values("ein_utc").reset_index(drop=True)
        ein = w["ein_utc"].to_numpy("datetime64[ns]")
        aus = w["aus_utc"].to_numpy("datetime64[ns]")
        r = w["R"].to_numpy(float)
        hebelwert = w["einstieg"].to_numpy(float) / w["stop_abstand"].to_numpy(float) / float(h["hebel_index"])
        # Bei gleicher Kerze: erst Ausstiege älterer Trades, dann Einstiege, dann Ausstiege von Trades, die in
        # derselben Kerze begonnen haben (Stop in der Kerze der Füllung).
        ereig = sorted([(t, 1, q) for q, t in enumerate(ein)] +
                       [(t, 2 if aus[q] == ein[q] else 0, q) for q, t in enumerate(aus)], key=lambda x: (x[0], x[1]))
        je = {}
        for a in h["anteile_pct"]:
            konto = float(h["start_eur"])
            risiko = np.zeros(len(r))
            offen_margin = 0.0
            hoch, tief_pct, margin_voll, max_margin = konto, 0.0, 0, 0.0
            tag_pnl: dict = {}
            pleite = None
            for t, art, q in ereig:
                if art == 1:
                    risiko[q] = konto * a / 100.0
                    offen_margin += risiko[q] * hebelwert[q]
                    max_margin = max(max_margin, offen_margin / konto if konto > 0 else np.inf)
                    if offen_margin > konto:
                        margin_voll += 1
                else:
                    pnl = risiko[q] * r[q]
                    konto += pnl
                    offen_margin -= risiko[q] * hebelwert[q]
                    tg = str(np.datetime64(t, "D"))
                    tag_pnl[tg] = tag_pnl.get(tg, 0.0) + pnl
                    hoch = max(hoch, konto)
                    tief_pct = min(tief_pct, konto / hoch - 1.0)
                    if konto <= 0.01 * float(h["start_eur"]):      # unter 10 € auf 1.000 € geht kein Trade mehr
                        pleite = tg
                        tief_pct = -1.0
                        break
            end = max(konto, 0.0)
            je[str(a)] = {"end_eur": _rund(end, 0), "rendite_pro_monat_pct": None if pleite else _rund(100 * ((end / h["start_eur"]) ** (1 / monate) - 1), 2),
                          "tiefster_rueckgang_pct": _rund(100 * tief_pct, 1),
                          "schlechtester_tag_eur": _rund(min(tag_pnl.values()) if tag_pnl else 0.0, 0),
                          "margin_ueber_konto_einstiege": int(margin_voll), "einstiege": int(len(r)),
                          "hoechste_margin_pct_konto": _rund(100 * max_margin, 0), "pleite_am": pleite,
                          "monate": _rund(monate, 1)}
        out[name] = je
    return out


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--festlegen":
        zeile = KEY + sha256_text(VORAB.read_text(encoding="utf-8"))
        journal_add(zeile)
        print(zeile)
        return 0
    modus, arbeit = argv[0], pathlib.Path(argv[1])
    if modus == "hebel":                                   # nur die Hebel-Auskunft neu, aus den gespeicherten Trades
        cfg = lade_vorab(pruefen=True)
        f = cfg["fenster"]
        tr = pd.read_csv(str(ERGEBNIS) + "_trades.csv.gz", parse_dates=["ein_utc", "aus_utc"])
        daten = json.loads(pathlib.Path(str(ERGEBNIS) + ".json").read_text(encoding="utf-8"))
        daten["hebel"] = hebel(tr, cfg, (f["von"], f["bis"]))
        pathlib.Path(str(ERGEBNIS) + ".json").write_text(json.dumps(daten, indent=1, ensure_ascii=False, default=str) + "\n",
                                                        encoding="utf-8")
        for n, je in daten["hebel"].items():
            print(n, {a: (x["end_eur"], x["rendite_pro_monat_pct"], x["tiefster_rueckgang_pct"], x["pleite_am"],
                          x["margin_ueber_konto_einstiege"]) for a, x in je.items()})
        return 0
    if modus == "entwicklung":
        cfg = lade_vorab(pruefen=False)
        cfg["maerkte"] = [s for s in cfg["maerkte"] if s != "GRXEUR"]
        fe = ("2021-03-01", "2023-12-29")
        erg, tr, mk = rechne(arbeit, cfg, "2023-12-31T23:59", fe, "2022-08-01")
        ziel, kopf = arbeit / "entwicklung_vorhersage_scalp", {"modus": "entwicklung, nur Kurse bis Ende 2023, kein Ergebnis"}
    elif modus == "probelauf":
        cfg = lade_vorab(pruefen=False)
        saat = int(argv[2])
        f = cfg["fenster"]
        fe = (f["von"], f["bis"])
        erg, tr, mk = rechne(arbeit, cfg, None, fe, f["mitte"], saat=saat)
        ziel, kopf = arbeit / f"probelauf_vorhersage_scalp_{saat}", {"modus": "erfundener Markt ohne Vorteil", "saat": saat}
    elif modus == "rechnen":
        cfg = lade_vorab(pruefen=True)
        f = cfg["fenster"]
        fe = (f["von"], f["bis"])
        erg, tr, mk = rechne(arbeit, cfg, None, fe, f["mitte"])
        ziel, kopf = ERGEBNIS, {"modus": "Rechnung", "vorab_sha256": sha256_text(VORAB.read_text(encoding="utf-8")), "fenster": f}
    else:
        raise SystemExit(__doc__)
    hb = hebel(tr, cfg, fe)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(str(ziel) + ".json").write_text(json.dumps({"kopf": kopf, "varianten": erg, "hebel": hb}, indent=1,
                                                            ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    tr.drop(columns=["R_robust"]).to_csv(str(ziel) + "_trades.csv.gz", index=False, float_format="%.6g")
    for n, e in erg.items():
        z = e.get("zufall", {})
        print(f"{n:22s} {e.get('trades', 0):5d} T {e.get('trades_je_woche')}/Wo  GF {e.get('gewinnfaktor')}  rob "
              f"{e.get('gewinnfaktor_robust')}  Summe {e.get('summe_R')}  Treffer {e.get('trefferquote')}  "
              f"H {e.get('haelfte_1', {}).get('gewinnfaktor')}/{e.get('haelfte_2', {}).get('gewinnfaktor')}  "
              f"2026 {e.get('jahr_2026', {}).get('gewinnfaktor')}  Zufall {z.get('geschlagen_pct')} %  z {z.get('z')}  "
              f"Aus {e.get('ausstieg')}  -> {e.get('urteil')} {e.get('durchgefallen_bei', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
