"""Stop-Prüfung "Rettung" vom 19.11.2026: Kirons Frage, ob die Stops der Bots den Verlust so klein wie möglich halten.

Kiron am 19.11.2026: Wenn ein Trade schon ins Minus läuft, beim kleinsten Minus oder knapp am Einstand schnell raus,
bevor es weiter ins Minus geht. Diese Prüfung rechnet genau das für die Nicht-Gold-Bots, deren Test die Kerzen fair
nachspielen kann. Die Einstiege bleiben die des Bots, nur der Ausstieg ändert sich, und jede Fassung wird Trade für
Trade mit dem unveränderten Original verglichen (gepaart, wie suche/ausstiege_kern.py).

Regeln: suche/VORAB_rettung_stops.yaml (versiegelt im Protokoll, bevor eine Fassung gerechnet wurde).

Aufruf:
    python -m suche.rettung_stops --festlegen           schreibt die Prüfsumme der Regeldatei ins Protokoll
    python -m suche.rettung_stops wege <Arbeit>         rechnet nur die Originale nach und zählt sie (keine Fassung)
    python -m suche.rettung_stops rechnen <Arbeit>      die Rechnung (nur mit passender Prüfsumme)
<Arbeit> ist der Ordner mit den Kursdateien (npz) von python -m suche.youtube_runde2 daten <Arbeit>.
Ändert an keinem Bot etwas.
"""
from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import yaml

from suche import ausstiege_kern as ak
from suche import notizen_runde as nr
from suche import opens as op
from suche import rueckblick as rb
from suche import runde5 as r5
from suche import scalping as sc
from suche import scalping2 as s2
from suche import scalping_opens as so
from suche.runde1 import journal_add, journal_lines, last_value, sha256_text

HERE = pathlib.Path(__file__).resolve().parent
VORAB = HERE / "VORAB_rettung_stops.yaml"
KEY = "VORAB_rettung_stops sha256 "
ERGEBNIS = HERE / "ergebnis_rettung_stops"
WELT_FASSUNG = "ausbruch4h_welt_ziel_1r"
SCALPER = {"scalp-us100": "NSXUSD", "scalp-de40": "GRXEUR"}        # beide: Eröffnung, folgen_10r, 15 Min., Filter alle
R5_MAERKTE = {"r5-ruecksetzer-us500": "SPXUSD", "r5-ruecksetzer-us100": "NSXUSD"}


def lade_vorab(pruefen: bool = True) -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if pruefen and last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("VORAB_rettung_stops.yaml passt nicht zur Prüfsumme im Protokoll. Erst versiegeln, dann rechnen.")
    return yaml.safe_load(text)["rettung_stops"]


# ---------------------------------------------------------------------------------------------------------------------
# Ein Trade des Originals mit seinem Weg

@dataclass
class Weg:
    """Ein Trade des Originals. Alle Größen in R (1 R = Abstand zum Stop des Bots), gemessen vom bezahlten Einstieg.
    gut und schlecht sind je Kerze der beste und der schlechteste Kurs, zu dem der Trade hätte enden können (Long: Bid,
    Short: Ask). Die Kerzen sind die, in denen der Trade ganz oder bis zu seinem Ausstieg lief. Eine Einstiegskerze,
    in der die Order erst mitten in der Kerze ausgelöst wurde, zählt nicht mit."""
    bot: str
    t: pd.Timestamp
    r: float                     # Ergebnis des Originals nach allen Kosten
    brutto: float                # Ergebnis des Originals vor der Übernachtgebühr (Spread ist im Einstieg)
    gut: np.ndarray
    schlecht: np.ndarray
    ende: str                    # "stop" | "ziel" | "zeit"
    halb: float | None = None    # Ergebnis mit halbem Stop-Abstand in denselben R (nur wo festgelegt)
    extra: dict = field(default_factory=dict)


def rettung(w: Weg, ausloeser: float, ziel: float) -> tuple[float, bool]:
    """Rettungs-Ausstieg. War der Trade einmal bei `ausloeser` R (zum Beispiel -0,5), liegt ab der nächsten Kerze eine
    Limit-Order bei `ziel` R (0 = Einstand, -0,25 = kleines Minus). Wird sie erreicht, endet der Trade dort, sonst wie
    das Original. Vorsichtige Lesart: Die Order gilt erst ab der Kerze nach dem Auslöser, sie füllt genau zum Limit
    (kein besserer Kurs), und in der Kerze, in der das Original gestoppt wird, gilt der Stop zuerst.
    Gibt (Ergebnis in R, gerettet ja/nein) zurück."""
    n = len(w.gut)
    grenze = n - 1 if w.ende == "stop" else n
    scharf = False
    for k in range(n):
        if scharf and k < grenze and w.gut[k] >= ziel:
            return w.r + ziel - w.brutto, True
        if not scharf and w.schlecht[k] <= ausloeser:
            scharf = True
    return w.r, False


# ---------------------------------------------------------------------------------------------------------------------
# Die Wege je Bot (jeweils die Rechnung des Bots, unverändert)

def wege_r5(bot: str) -> tuple[list[Weg], dict]:
    """Trend-Rücksetzer wie suche/ausstiege_kern.rechne_us100 (runde5.simuliere), Stundenkerzen in echter UTC.
    1 R = der Notstop von 3 ATR 20, wie in der Gruppenrechnung N2."""
    sym = R5_MAERKTE[bot]
    cfg5 = r5.check_vorab()
    h1 = ak.kerzen(ak.lade_5min(sym, utc=True), "1h")
    T = r5.baue_tage(sym, h1, None, cfg5["kosten"])
    T.sp = sc.SPREAD[sym]
    T.hsp = np.full(len(T.hsp), sc.SPREAD[sym])
    s = r5.sig_trend_ruecksetzer(T, ak.R5_PARAMETER, {})
    start = int(np.searchsorted(T.datum, np.datetime64(T.datum[0]) + np.timedelta64(ak.R5_VORLAUF, "D")))
    a20 = r5.atr(T, 20)
    orig = r5.simuliere(T, s, start)
    out, abw = [], 0.0
    for t in orig:
        ti, d = t["ti"], t["d"]
        nach = ak.r5_ausstieg(T, s, a20, ti, d, 1.0, 1.0)
        abw = max(abw, abs(nach["r"] - t["r"]))
        te, atr = nach["te"], a20[ti]
        ein = T.c[ti] + (T.sp if d > 0 else 0.0)
        stop = T.c[ti] - d * s.stop_atr * atr
        sd = s.stop_atr * atr
        a, b = T.i0[ti + 1], T.i1[te] + 1
        ho, hh, hl, hsp = T.ho[a:b], T.hh[a:b], T.hl[a:b], T.hsp[a:b]
        seite = 0.0 if d > 0 else hsp
        treffer = (hl <= stop) if d > 0 else (hh + hsp >= stop)
        if nach["grund"] in ("stop", "einstand"):
            k = int(np.argmax(treffer))
            aus = min(stop, ho[k]) if d > 0 else max(stop, ho[k] + hsp[k])
            t_aus, ende, n = T.ht[a + k] + np.timedelta64(1, "h"), "stop", k + 1
        else:
            aus = T.c[te] + (T.sp if d < 0 else 0.0)
            t_aus, ende, n = T.t[te], "zeit", b - a
        pnl = (aus - ein) * d
        fin = (T.fin_long if d > 0 else T.fin_short) * T.c[ti] * r5.naechte(T.t[ti], t_aus)
        abw = max(abw, abs((pnl - fin) / atr - nach["r"]))
        gut = ((hh + seite - ein) * d if d > 0 else (ein - (hl + seite)))[:n] / sd
        schlecht = ((hl + seite - ein) if d > 0 else (ein - (hh + seite)))[:n] / sd
        out.append(Weg(bot, pd.Timestamp(T.t[ti]), (pnl - fin) / sd, pnl / sd, gut, schlecht, ende))
    return out, {"trades": len(out), "groesste_abweichung_r": float(abw)}


def wege_noise() -> tuple[list[Weg], dict]:
    """Nasdaq Noise-Band wie suche/ausstiege_kern.noise_ausstieg (Trade-Liste der Runde 7, 15-Min.-Kerzen auf der
    Dateizeit). 1 R = der Notstop von 5 ATR 14."""
    liste = pd.read_csv(ak.NOISE_CSV)
    b = ak.kerzen(ak.lade_5min("NSXUSD", utc=False), "15min")
    o, h, l, c = (b[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    out, abw, fehlt = [], [], 0
    for row in liste.itertuples():
        nach = ak.noise_ausstieg(b, row, ak.r7.HALTE_TAGE, False, 1.0)
        if nach is None:
            fehlt += 1
            continue
        abw.append(abs(nach["r"] - float(row.r)))
        i0 = int(b.index.searchsorted(pd.Timestamp(row.einstieg_utc)))
        ie = int(b.index.searchsorted(pd.Timestamp(nach["aus"]) - pd.Timedelta(minutes=15)))
        sp_pct = 2 * (float(row.ergebnis_pct) - float(row.ergebnis_pct_kosten_1_5)) - float(row.uebernacht_pct)
        e, risiko = o[i0], float(row.risiko_pct_5atr)
        ein = e * (1 + sp_pct / 100)
        sd = e * risiko / 100
        stop = ein * (1 - risiko / 100)
        ende = "stop" if nach["grund"] == "stop" else "zeit"
        aus = min(stop, o[ie]) if ende == "stop" else c[ie]
        brutto = (aus - ein) / sd
        out.append(Weg("r7-nasdaq-noise-long", pd.Timestamp(row.einstieg_utc), float(nach["r"]), float(brutto),
                       (h[i0:ie + 1] - ein) / sd, (l[i0:ie + 1] - ein) / sd, ende))
    return out, {"trades": len(out), "fehlt": fehlt,
                 "median_abweichung_r": float(np.median(abw)) if abw else None}


def wege_scalper(bot: str, faktor_halb: float | None) -> tuple[list[Weg], dict]:
    """Eröffnungs-Scalper wie suche/scalping2.eroeffnung (folgen_10r, 15-Min.-Kerzen in echter UTC, Open-Filter "alle",
    ab 2016 wie suche/ausstiege_kern.rechne_dax). 1 R = der Abstand zum anderen Ende der ersten Kerze."""
    sym = SCALPER[bot]
    df5 = ak.lade_5min(sym, utc=True)
    p = op.perioden(df5)
    m = sc.Markt(sym, s2.zu_15(df5), s2.spreads()[sym], minuten=15)
    s = m.spread
    orig = s2.eroeffnung(m, sym, "folgen_10r", 1.0, ak.DAX_AB, str(df5.index[-1]))
    maske = so.mit_opens(p, orig)["alle"]
    out, abw = [], 0.0
    for t, ok in zip(orig, maske):
        if not ok:
            continue
        i0, ie, d, dist, zdist = t["i0"], t["ie"], t["d"], t["r_dist"], t["ziel_dist"]
        entry = m.o[i0] + s if d == 1 else m.o[i0]
        seite = 0.0 if d == 1 else s
        stop, ziel = entry - d * dist, entry + d * zdist
        o, h, l = m.o[i0:ie + 1] + seite, m.h[i0:ie + 1] + seite, m.l[i0:ie + 1] + seite
        n = len(o)
        hs = (l <= stop) if d == 1 else (h >= stop)
        hz = (h >= ziel) if d == 1 else (l <= ziel)
        ks = int(np.argmax(hs)) if hs.any() else n
        kt = int(np.argmax(hz)) if hz.any() else n
        if ks < n and ks <= kt:
            luecke = ks > 0 and ((o[ks] <= stop) if d == 1 else (o[ks] >= stop))
            aus, ende, k = (o[ks] if luecke else stop), "stop", ks
        elif kt < n:
            aus, ende, k = ziel, "ziel", kt
        else:
            aus, ende, k = m.c[ie] + seite, "zeit", n - 1
        pnl = d * (aus - entry)
        abw = max(abw, abs(pnl / dist - t["r"])) if ende == t["grund"] else float("inf")
        gut = ((h - entry) if d == 1 else (entry - l))[:k + 1] / dist
        schlecht = ((l - entry) if d == 1 else (entry - h))[:k + 1] / dist
        halb = None
        if faktor_halb is not None:
            h2 = s2.trade_v(m, i0, ie, d, "close", s, stop_abstand=faktor_halb * dist, ziel_abstand=zdist)
            halb = float(h2["r"]) * faktor_halb if h2 else 0.0           # öffnet sie nicht, zählt der Trade mit 0 R
        out.append(Weg(bot, pd.Timestamp(m.t[i0]), float(t["r"]), pnl / dist, gut, schlecht, ende, halb=halb))
    return out, {"trades": len(out), "groesste_abweichung_r": float(abw)}


def wege_welt4h(arbeit: pathlib.Path, faktor_halb: float | None) -> tuple[list[Weg], dict]:
    """4-Std.-Ausbruch DAX, FTSE, Nikkei (Fassung ausbruch4h_welt_ziel_1r der Runde "Kirons Notizen"), dieselben
    Signale und dieselbe Trade-Rechnung wie suche/notizen_runde.py. 1 R = der Stop-Abstand der Regel."""
    cfg = nr.lade_vorab()
    v = cfg["varianten"][WELT_FASSUNG]
    term = rb.termine_utc()
    rutsch = cfg["kosten"]["rutschen_spread"]
    out, abw = [], 0.0
    for sym in v["maerkte"]:
        m = nr.Markt(sym, arbeit, cfg, None, None)
        sig = nr.signale(v["regel"], m, cfg, term)
        ref = rb.echte_trades(m, sig, cfg)
        frei_ab, zeile = -1, 0
        for s in sorted(sig, key=lambda x: x["i0"]):
            i0 = s["i0"]
            if i0 <= frei_ab or i0 >= m.n - 1:
                continue
            g = m.gpos[m.tix[i0]]
            if g < 1 or not np.isfinite(m.atr_vor[g]) or not (s["sd"] > 0):
                continue
            d, sd, zd, lvl = s["d"], s["sd"], s.get("zd", 0.0), s.get("lvl", np.nan)
            imax = int(m.kerze_ab(np.array([s["t_max"]]))[0])
            ex, pnl, e = rb._trade(m.o, m.h, m.l, m.c, m.sp, i0, d, lvl, sd, zd, imax, 1.0, rutsch)
            fin = rb.gebuehr(m, cfg, [d], [e], np.array([i0]), np.array([ex]))[0]
            frei_ab = ex
            abw = max(abw, abs((pnl - fin) / sd - float(ref["R"].iloc[zeile])))
            zeile += 1
            bezug = o_i0 = m.o[i0]                                         # Marke der Order (Bid)
            if lvl == lvl:
                bezug = max(lvl, o_i0) if d > 0 else min(lvl, o_i0)
            ziel_pnl = (bezug + zd - e) if d > 0 else (e - (bezug - zd))
            zeit_pnl = (m.o[ex] - e) if d > 0 else (e - (m.o[ex] + m.sp[ex]))
            ende_pnl = (m.c[ex] - e) if d > 0 else (e - (m.c[ex] + m.sp[ex]))
            a, b = i0 + 1, ex + 1                                          # die Einstiegskerze zählt nicht mit
            if zd > 0 and abs(pnl - ziel_pnl) < 1e-9:
                ende = "ziel"
            elif ex > i0 and ex >= imax and abs(pnl - zeit_pnl) < 1e-9:
                ende, b = "zeit", ex                                       # raus zur Eröffnung, die Kerze zählt nicht
            elif ex == m.n - 1 and abs(pnl - ende_pnl) < 1e-9:
                ende = "zeit"                                              # Datenende
            else:
                ende = "stop"
            h, l, sp = m.h[a:b], m.l[a:b], m.sp[a:b]
            gut = ((h - e) if d > 0 else (e - (l + sp))) / sd
            schlecht = ((l - e) if d > 0 else (e - (h + sp))) / sd
            halb = None
            if faktor_halb is not None:
                ex2, pnl2, e2 = rb._trade(m.o, m.h, m.l, m.c, m.sp, i0, d, lvl, faktor_halb * sd, zd, imax, 1.0, rutsch)
                halb = (pnl2 - rb.gebuehr(m, cfg, [d], [e2], np.array([i0]), np.array([ex2]))[0]) / sd
            out.append(Weg("welt-ausbruch4h", pd.Timestamp(m.t[i0]), (pnl - fin) / sd, pnl / sd, gut, schlecht, ende,
                           halb=halb, extra={"markt": sym}))
        if zeile != len(ref):
            raise SystemExit(f"{sym}: andere Trades als suche/notizen_runde ({zeile} statt {len(ref)}).")
    return out, {"trades": len(out), "groesste_abweichung_r": float(abw)}


def alle_wege(cfg: dict, arbeit: pathlib.Path, mit_fassungen: bool = True) -> tuple[dict[str, list[Weg]], dict]:
    f = float(cfg["varianten"]["stop_halb"]["faktor"]) if mit_fassungen else None
    wege, kontrolle = {}, {}
    for bot in cfg["bots"]:
        if bot in R5_MAERKTE:
            wege[bot], kontrolle[bot] = wege_r5(bot)
        elif bot == "r7-nasdaq-noise-long":
            wege[bot], kontrolle[bot] = wege_noise()
        elif bot in SCALPER:
            wege[bot], kontrolle[bot] = wege_scalper(bot, f)
        elif bot == "welt-ausbruch4h":
            wege[bot], kontrolle[bot] = wege_welt4h(arbeit, f)
        else:
            raise SystemExit(f"Für {bot} gibt es keine Rechnung.")
        k = kontrolle[bot]
        grenze = cfg["kontrolle"]["abweichung_r_max"]
        if k.get("fehlt") or k.get("groesste_abweichung_r", 0.0) > grenze or (k.get("median_abweichung_r") or 0.0) > 0.02:
            raise SystemExit(f"{bot}: die Nachrechnung des Originals weicht ab ({k}).")
    return wege, kontrolle


# ---------------------------------------------------------------------------------------------------------------------
# Auswertung

def tal(r: np.ndarray) -> float:
    if not len(r):
        return 0.0
    kurve = np.cumsum(r)
    return float((np.maximum.accumulate(np.r_[0.0, kurve])[1:] - kurve).max())


def kennz(r: np.ndarray) -> dict:
    r = np.asarray(r, float)
    p = ak.pf(r)
    minus = r[r < 0]
    return {"trades": int(len(r)), "summe_r": round(float(r.sum()), 2), "gewinnfaktor": round(p, 3) if p is not None else None,
            "trefferquote": round(float((r > 0).mean()), 3) if len(r) else None,
            "mittlerer_verlust_r": round(float(minus.mean()), 3) if len(minus) else None,
            "groesster_verlust_r": round(float(r.min()), 2) if len(r) else None, "tiefstes_tal_r": round(tal(r), 2)}


def gepaart_p(diff: np.ndarray, rng: np.random.Generator, laeufe: int) -> float:
    """Einseitiger Zeichen-Tausch-Test auf den Mittelwert, wie suche/ausstiege_kern.gepaart_p."""
    if len(diff) == 0 or not np.any(diff):
        return 1.0
    beob = diff.mean()
    treffer = 0
    for _ in range(laeufe // 1000):
        z = rng.choice((-1.0, 1.0), size=(1000, len(diff)))
        treffer += int(((z * diff).mean(axis=1) >= beob - 1e-12).sum())
    return (1 + treffer) / (1 + laeufe)


def _gf(k: dict) -> float:
    """Gewinnfaktor zum Vergleichen: ohne Verlust-Trades unendlich, wenn es Gewinne gab."""
    if k["gewinnfaktor"] is None:
        return float("inf") if k["summe_r"] > 0 else 0.0
    return k["gewinnfaktor"]


def fassungen(cfg: dict, w: list[Weg]) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Je Fassung (Ergebnis in R je Trade, hat die Fassung eingegriffen ja/nein)."""
    out = {}
    for name, v in cfg["varianten"].items():
        if w and w[0].bot not in v.get("bots", [x.bot for x in w]):
            continue
        if name == "stop_halb":
            r = np.array([x.halb for x in w], float)
            out[name] = (r, np.abs(r - np.array([x.r for x in w])) > 1e-9)
        else:
            paare = [rettung(x, float(v["ausloeser_r"]), float(v["ziel_r"])) for x in w]
            out[name] = (np.array([p[0] for p in paare], float), np.array([p[1] for p in paare], bool))
    return out


def auswerten(cfg: dict, wege: dict[str, list[Weg]]) -> dict:
    rng = np.random.default_rng(int(cfg["vergleich"]["saat"]))
    laeufe = int(cfg["vergleich"]["laeufe"])
    von, bis = (pd.Timestamp(x) for x in cfg["fenster"]["haupt"])
    zeilen, p = {}, {}
    for bot, w in wege.items():
        w = sorted(w, key=lambda x: x.t)
        t = pd.DatetimeIndex([x.t for x in w])
        haupt = np.asarray((t >= von) & (t <= bis + pd.Timedelta(days=1)))
        r0 = np.array([x.r for x in w], float)
        zeilen[bot] = {"original": {"lang": kennz(r0), "haupt": kennz(r0[haupt]),
                                    "von": str(t.min().date()) if len(t) else None,
                                    "bis": str(t.max().date()) if len(t) else None}}
        for name, (r1, griff) in fassungen(cfg, w).items():
            key = f"{bot}|{name}"
            diff = r1 - r0
            p[key] = gepaart_p(diff, rng, laeufe)
            spaeter_gewinner = int(((r0 > 0) & griff).sum())
            zeilen[bot][name] = {
                "lang": kennz(r1), "haupt": kennz(r1[haupt]), "p": round(p[key], 4),
                "unterschied_je_trade_r": round(float(diff.mean()), 4) if len(diff) else 0.0,
                "eingegriffen": int(griff.sum()), "eingegriffen_haupt": int(griff[haupt].sum()),
                "davon_im_original_gewinner": spaeter_gewinner,
                "davon_im_original_verlierer": int(((r0 <= 0) & griff).sum()),
                "gespart_bei_verlierern_r": round(float(diff[(r0 <= 0) & griff].sum()), 2),
                "verschenkt_bei_gewinnern_r": round(float(diff[(r0 > 0) & griff].sum()), 2)}
    holm = ak.holm(p, float(cfg["vergleich"]["alpha"]))
    for key, ok in holm.items():
        bot, name = key.split("|")
        z, o = zeilen[bot][name], zeilen[bot]["original"]
        mehr = z["haupt"]["summe_r"] > o["haupt"]["summe_r"]
        gf_ok = _gf(z["haupt"]) >= _gf(o["haupt"])
        z["holm"] = bool(ok)
        z["haupt_summe_hoeher"], z["haupt_gewinnfaktor_nicht_tiefer"] = bool(mehr), bool(gf_ok)
        z["urteil"] = ("bestanden" if ok and mehr and gf_ok else
                       "Kandidat" if p[key] <= float(cfg["vergleich"]["alpha"]) and mehr and gf_ok else "durchgefallen")
    return {"bots": zeilen, "anzahl_fassungen": len(p)}


def schreibe(erg: dict, kontrolle: dict, cfg: dict, ziel: pathlib.Path) -> None:
    erg = {**erg, "kontrolle": kontrolle, "fenster": cfg["fenster"], "varianten": cfg["varianten"]}
    ziel.with_suffix(".json").write_text(json.dumps(erg, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--festlegen":
        zeile = KEY + sha256_text(VORAB.read_text(encoding="utf-8"))
        journal_add(zeile)
        print(zeile)
        return 0
    modus, arbeit = argv[0], pathlib.Path(argv[1])
    if modus == "wege":
        cfg = lade_vorab(pruefen=False)
        _, kontrolle = alle_wege(cfg, arbeit, mit_fassungen=False)
        print(json.dumps(kontrolle, ensure_ascii=False, indent=1))
        return 0
    if modus == "rechnen":
        cfg = lade_vorab()
        wege, kontrolle = alle_wege(cfg, arbeit)
        erg = auswerten(cfg, wege)
        schreibe(erg, kontrolle, cfg, ERGEBNIS)
        for bot, z in erg["bots"].items():
            for name, x in z.items():
                if name != "original":
                    print(f"{bot:24s} {name:24s} p {x['p']:.4f} {x['urteil']}")
        return 0
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
