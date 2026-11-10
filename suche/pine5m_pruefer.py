"""Prüfer für den Pine-Gold-TP-Bot: 6 vorab festgelegte Varianten auf Gold 5 Min. (suche/VORAB_pine5m_pruefer.yaml).

Einstiege, Kosten, R, Kontoregeln und Zeiträume aus suche/pine5m.py. Ein Trade hat Ziel +0,6 R (3 € bei 5 € je R).
Nach der Wartezeit greift der Prüfer einmal ein, wenn der Trade seit dem Einstieg 0,5 R im Minus lag (Fehltrade), oder
nach 24 Std. (langes Warten). Aufruf: python -m suche.pine5m_pruefer
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd
import yaml

from suche import pine5m as p5
from suche.runde1 import journal_lines, last_value, sha256_text

ROOT = p5.ROOT
VORAB = ROOT / "suche" / "VORAB_pine5m_pruefer.yaml"
KEY = "VORAB_pine5m_pruefer sha256 "
FEHL_R, NOT_ABSTAND_R, LANG_STD = 0.5, 0.5, 24
SYMBOL = "XAUUSD"


def check_vorab() -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("VORAB_pine5m_pruefer.yaml passt nicht zur Prüfsumme im Journal.")
    return yaml.safe_load(text)["pine5m_pruefer"]


def _erst(mask: np.ndarray) -> int | None:
    if not len(mask):
        return None
    j = int(np.argmax(mask))
    return j if mask[j] else None


class Markt(p5.Markt):
    def trade(self, i: int, d: int, variante: str, faktor: float = 1.0) -> dict:
        if not variante.startswith("pruefer_"):
            return super().trade(i, d, variante, faktor)
        _, w_std, s_r = variante.split("_")
        w_std, s_r = float(w_std), float(s_r)
        sp = self.spec["spread"] * faktor
        i0 = i + 1
        r = self.r_dist(i)
        entry = self.o[i0] + sp if d == 1 else self.o[i0]
        opn, fav, adv, cls = self._profit(i0, d, sp, entry, r)
        m = len(opn)
        t = self.t[i0:]
        tp = p5.TP_R
        jw = int(t.searchsorted(t[0] + pd.Timedelta(hours=w_std)))     # erste Kerze, in der der Prüfer wirken darf
        jl = int(t.searchsorted(t[0] + pd.Timedelta(hours=LANG_STD)))

        def tp_treffer(a, b, ziel):
            j = _erst((opn[a:b] >= ziel) | (fav[a:b] >= ziel))
            return None if j is None else a + j

        # Erkennung (am Kerzenschluss jd, wirkt ab jd + 1)
        if jw >= m:
            jd_f = None
        elif jw > 0 and adv[:jw].min() <= -FEHL_R:
            jd_f = jw - 1
        else:
            j = _erst(adv[jw:] <= -FEHL_R)
            jd_f = None if j is None else jw + j
        jd_l = jl - 1 if 0 < jl <= m - 1 else None
        kand = [(jd, art) for jd, art in ((jd_f, "fehltrade"), (jd_l, "lang")) if jd is not None]
        jd, art = min(kand) if kand else (None, None)
        grund, k, res = None, None, None
        j_tp = tp_treffer(0, (jd + 1) if jd is not None else m, tp)
        if j_tp is not None:
            k, res, grund = j_tp, (opn[j_tp] if opn[j_tp] >= tp else tp), "ziel"
        elif jd is not None and jd + 1 < m:
            ja, cur = jd + 1, cls[jd]
            if art == "lang" and cur >= 0:
                k, res, grund = ja, opn[ja], "lang_raus"
            else:
                stop = -s_r if cur > -s_r else cur - NOT_ABSTAND_R
                ziel = 0.0 if cur < 0 else tp
                w = slice(ja, m)
                ev = (opn[w] <= stop) | (adv[w] <= stop) | (opn[w] >= ziel) | (fav[w] >= ziel)
                j = _erst(ev)
                if j is not None:
                    jj = ja + j
                    if opn[jj] <= stop or opn[jj] >= ziel:
                        res = opn[jj]
                    elif adv[jj] <= stop:
                        res = stop
                    else:
                        res = ziel
                    k = jj
                    grund = art + ("_stop" if res < 0 else ("_einstand" if ziel == 0.0 else "_ziel"))
        if k is None:
            k, res, grund = m - 1, cls[m - 1], "offen"
        ie = i0 + k
        naechte = int(self.tag_nr[ie] - self.tag_nr[i0])
        swap = naechte * p5.SWAP_JAHR / 365 * entry / r
        return {"i": i, "i0": i0, "ie": ie, "d": d, "r_dist": r, "entry": entry, "r": float(res - swap),
                "grund": grund, "kerzen": int(ie - i0), "swap_r": float(swap)}


def extra(trades: list[dict]) -> dict:
    r = np.array([t["r"] for t in trades]) if trades else np.zeros(0)
    los, win = r[r < 0], r[r > 0]
    return {"groesster_verlust_r": round(float(r.min()), 2) if len(r) else None,
            "groesster_verlust_eur": round(float(r.min()) * 5, 0) if len(r) else None,
            "verlierer_pct": round(100 * len(los) / len(r), 1) if len(r) else None,
            "mittel_gewinn_r": round(float(win.mean()), 3) if len(win) else None,
            "mittel_verlust_r": round(float(los.mean()), 3) if len(los) else None}


def varianten(v: dict) -> list[str]:
    return ["tp3"] + [f"pruefer_{w:g}_{s:g}" for w in v["wartezeit_std"] for s in v["stop_r"]]


def rechne(v: dict, ordner: pathlib.Path = p5.DATEN) -> dict:
    spec = next(s for s in p5.maerkte() if s["symbol"] == SYMBOL)
    m = Markt(spec, p5.lade(SYMBOL, ordner))
    out = {}
    for var in varianten(v):
        tr = m.simuliere(*p5.ZEITRAUM, var)
        tr_k = m.simuliere(*p5.KONTROLLE, var)
        out[var] = {
            "zeitraum": p5.kennzahlen(m, tr, *p5.ZEITRAUM, m.tageswerte(tr, p5.ZEITRAUM[0])),
            "robust": p5.kennzahlen(m, m.simuliere(*p5.ZEITRAUM, var, p5.ROBUST), *p5.ZEITRAUM),
            "haelfte_1": p5.kennzahlen(m, p5.teil(tr, m, *p5.HAELFTEN[0]), *p5.HAELFTEN[0]),
            "haelfte_2": p5.kennzahlen(m, p5.teil(tr, m, *p5.HAELFTEN[1]), *p5.HAELFTEN[1]),
            "jahr_2026": p5.kennzahlen(m, p5.teil(tr, m, *p5.JAHR_2026), *p5.JAHR_2026),
            "kontrolle": p5.kennzahlen(m, tr_k, *p5.KONTROLLE, m.tageswerte(tr_k, p5.KONTROLLE[0])),
            "extra": extra(tr), "extra_kontrolle": extra(tr_k)}
        z = out[var]["zeitraum"]
        print(var, z["trades"], z["pf_r"], z["summe_r"], out[var]["kontrolle"]["pf_r"], flush=True)
    return out


def wahl(res: dict) -> dict:
    kand = {k: v for k, v in res.items() if k != "tp3"}
    ok = {k: v for k, v in kand.items() if p5.bestanden(v)[0]}
    key = lambda k: (kand[k]["zeitraum"]["pf_r"], kand[k]["zeitraum"]["summe_r"])
    if ok:
        return {"gewaehlt": max(ok, key=key), "bestanden": True, "bestandene": sorted(ok, key=key, reverse=True)}
    return {"gewaehlt": max(kand, key=key), "bestanden": False, "bestandene": [],
            "verfehlt": {k: p5.bestanden(v)[1] for k, v in kand.items()}}


def bericht(res: dict, u: dict) -> str:
    z = ["# Prüfer für den Pine-Gold-TP-Bot (Gold 5 Min.)", "",
         "Regeln suche/VORAB_pine5m_pruefer.yaml. Variante pruefer_W_S: W Std. Wartezeit, Stop S R. Ziel +0,6 R = 3 €.",
         "", f"**Gewählt: {u['gewaehlt']}**, " + ("bestanden." if u["bestanden"] else "keine Variante hat bestanden."),
         "", "| Variante | Trades | je Woche | PF | Summe R | Rückgang R | Verlierer % | größter Verlust R | "
             "PF ×1,5 | H1 | H2 | 2026 | Kontrolle | Summe R Kontrolle |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, a in res.items():
        zz, e = a["zeitraum"], a["extra"]
        z.append(f"| {k} | {zz['trades']} | {zz['je_woche']} | {zz['pf_r']} | {zz['summe_r']} | "
                 f"{zz['max_rueckgang_r']} | {e['verlierer_pct']} | {e['groesster_verlust_r']} | {a['robust']['pf_r']} | "
                 f"{a['haelfte_1']['pf_r']} | {a['haelfte_2']['pf_r']} | {a['jahr_2026']['pf_r']} | "
                 f"{a['kontrolle']['pf_r']} | {a['kontrolle']['summe_r']} |")
    return "\n".join(z) + "\n"


def main(argv: list[str]) -> int:
    v = check_vorab()
    p5.check_vorab()
    res = rechne(v)
    u = wahl(res)
    erg = {"vorab_sha256": sha256_text(VORAB.read_text(encoding="utf-8")), "wahl": u, "varianten": res}
    (ROOT / "suche" / "ergebnis_pine5m_pruefer.json").write_text(json.dumps(erg, ensure_ascii=False, indent=1) + "\n",
                                                                 encoding="utf-8")
    (ROOT / "suche" / "ergebnis_pine5m_pruefer.md").write_text(bericht(res, u), encoding="utf-8")
    print(json.dumps(u, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
