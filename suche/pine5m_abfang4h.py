"""Pine-Gold-Hand-Bot auf Account 5: Trade-Abfänger erst nach 4 Std., dann Stop 0,5 R hinter dem besten Kurs.

Regeln suche/VORAB_pine5m_abfang4h.yaml (Kirons Wort vom 10.11.2026 11:18 UTC). Einstiege, Filter (Hedging,
Termin-Pause, Hintergrund), Kosten, R und Zeiträume aus suche/pine5m_konto5.py (Variante k5_hedge_termin_hg).
Aufruf: python -m suche.pine5m_abfang4h
"""
from __future__ import annotations

import json
import sys

import numpy as np
import yaml

from suche import pine5m as p5
from suche import pine5m_konto5 as k5
from suche.runde1 import journal_lines, last_value, sha256_text

ROOT = p5.ROOT
VORAB = ROOT / "suche" / "VORAB_pine5m_abfang4h.yaml"
KEY = "VORAB_pine5m_abfang4h sha256 "
WARTEN_KERZEN = 48                 # 4 Std. auf 5-Min.-Kerzen
NACHZIEH_R = 0.5
VARIANTEN = {"heute": "abfaenger", "abfang4h": "abfang4h", "ohne_abfang": "pine"}


def check_vorab() -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("VORAB_pine5m_abfang4h.yaml passt nicht zur Prüfsumme im Journal.")
    return yaml.safe_load(text)["pine5m_abfang4h"]


def nachziehen(opn: np.ndarray, fav: np.ndarray, adv: np.ndarray, a: int, ende: int,
               abstand: float = NACHZIEH_R) -> tuple[int, float] | None:
    """Stop `abstand` R hinter dem besten Kurs seit der Übernahme zur Eröffnung von Kerze a (alles in R aus Sicht des
    Trades). Je Kerze erst der Stop aus den Kerzen davor, dann der beste Kurs mit dieser Kerze. (Kerze, Ergebnis R) oder
    None, wenn der Stop bis Kerze `ende` nicht kommt."""
    if a > ende:
        return None
    best = opn[a]
    for j in range(a, ende + 1):
        stop = best - abstand
        if opn[j] <= stop:
            return j, float(opn[j])
        if adv[j] <= stop:
            return j, float(stop)
        best = max(best, fav[j])
    return None


class Markt(k5.Markt):
    def trade(self, i: int, d: int, variante: str, faktor: float = 1.0) -> dict:
        if variante != "abfang4h":
            return super().trade(i, d, variante, faktor)
        tr = super().trade(i, d, "pine", faktor)          # Pine-Ausstieg (steht für Kiron) oder offen bis Datenende
        sp = self.spec["spread"] * faktor
        i0, r, entry = tr["i0"], tr["r_dist"], tr["entry"]
        opn, fav, adv, _ = self._profit(i0, d, sp, entry, r)
        ende = tr["ie"] - i0 - (1 if tr["grund"] == "pine" else 0)      # letzte Kerze, in der der Stop noch zählt
        hit = nachziehen(opn, fav, adv, WARTEN_KERZEN, ende)
        if hit is None:
            return tr
        k, res = hit
        ie = i0 + k
        naechte = int(self.tag_nr[ie] - self.tag_nr[i0])
        swap = naechte * p5.SWAP_JAHR / 365 * entry / r
        return {**tr, "ie": ie, "r": float(res - swap), "grund": "abfang4h", "kerzen": int(k), "swap_r": float(swap)}

    def simuliere(self, von: str, bis: str, variante: str, faktor: float = 1.0) -> list[dict]:
        """Wie k5_hedge_termin_hg (Hedging, Termin-Pause, Hintergrund), nur der Ausstieg je nach Variante."""
        offen: list[dict] = []
        out = []
        for i, d in self.kandidaten(von, bis):
            i0 = i + 1
            offen = [o for o in offen if o["ie"] > i0 or (o["ie"] == i0 and o["grund"] not in ("pine",))]
            if d == 0:
                seiten = {o["d"] for o in offen}
                if len(seiten) != 1:
                    continue
                d = seiten.pop()
            if len(offen) >= p5.MAX_OFFEN or self.sperre[i] or self.hg[i] == -d:
                continue
            tr = self.trade(i, d, variante, faktor)
            offen.append(tr)
            out.append(tr)
        return out


def rechne(ordner=p5.DATEN) -> dict:
    spec = next(s for s in p5.maerkte() if s["symbol"] == k5.SYMBOL)
    m = Markt(spec, p5.lade(k5.SYMBOL, ordner))
    out = {}
    for name, var in VARIANTEN.items():
        tr = m.simuliere(*p5.ZEITRAUM, var)
        tr_k = m.simuliere(*p5.KONTROLLE, var)
        out[name] = {
            "zeitraum": p5.kennzahlen(m, tr, *p5.ZEITRAUM),
            "robust": p5.kennzahlen(m, m.simuliere(*p5.ZEITRAUM, var, p5.ROBUST), *p5.ZEITRAUM),
            "haelfte_1": p5.kennzahlen(m, p5.teil(tr, m, *p5.HAELFTEN[0]), *p5.HAELFTEN[0]),
            "haelfte_2": p5.kennzahlen(m, p5.teil(tr, m, *p5.HAELFTEN[1]), *p5.HAELFTEN[1]),
            "jahr_2026": p5.kennzahlen(m, p5.teil(tr, m, *p5.JAHR_2026), *p5.JAHR_2026),
            "kontrolle": p5.kennzahlen(m, tr_k, *p5.KONTROLLE),
            "groesster_verlust_r": k5.extra(tr)["groesster_verlust_r"],
            "anteil_abfaenger_pct": round(100 * sum(1 for t in tr if t["grund"] not in ("pine", "offen"))
                                          / max(1, len(tr)), 1)}
        z = out[name]["zeitraum"]
        print(name, z["trades"], z["pf_r"], z["summe_r"], out[name]["kontrolle"]["pf_r"], flush=True)
    return out


def bericht(res: dict) -> str:
    ok, fehl = p5.bestanden(res["abfang4h"])
    z = ["# Pine-Gold Account 5: Abfänger erst nach 4 Stunden (Gold 5 Min.)", "",
         "Regeln suche/VORAB_pine5m_abfang4h.yaml. Alle Varianten mit Hedging, Termin-Pause und Hintergrund wie der "
         "Bot heute. Kirons eigener Ausstieg steht im Test für das Pine-Ausstiegssignal.", "",
         "**abfang4h: " + ("bestanden.**" if ok else "nicht bestanden:** " + "; ".join(fehl) + ".")
         + " Geht auf Kirons Wunsch trotzdem live (Demo).", "",
         "| Variante | Trades | je Woche | PF | Summe R | Rückgang R | größter Verlust R | Haltedauer Std. (Median) | "
         "vom Abfänger geschlossen | PF ×1,5 | H1 | H2 | 2026 | Kontrolle | Summe R Kontrolle |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, a in res.items():
        zz = a["zeitraum"]
        z.append(f"| {k} | {zz['trades']} | {zz['je_woche']} | {zz['pf_r']} | {zz['summe_r']} | "
                 f"{zz['max_rueckgang_r']} | {a['groesster_verlust_r']} | {zz['haltedauer_std_median']} | "
                 f"{a['anteil_abfaenger_pct']} % | {a['robust']['pf_r']} | {a['haelfte_1']['pf_r']} | "
                 f"{a['haelfte_2']['pf_r']} | {a['jahr_2026']['pf_r']} | {a['kontrolle']['pf_r']} | "
                 f"{a['kontrolle']['summe_r']} |")
    return "\n".join(z) + "\n"


def main(argv: list[str]) -> int:
    check_vorab()
    k5.check_vorab()
    p5.check_vorab()
    res = rechne()
    ok, fehl = p5.bestanden(res["abfang4h"])
    erg = {"vorab_sha256": sha256_text(VORAB.read_text(encoding="utf-8")), "bestanden": ok, "verfehlt": fehl,
           "varianten": res}
    (ROOT / "suche" / "ergebnis_pine5m_abfang4h.json").write_text(json.dumps(erg, ensure_ascii=False, indent=1) + "\n",
                                                                  encoding="utf-8")
    (ROOT / "suche" / "ergebnis_pine5m_abfang4h.md").write_text(bericht(res), encoding="utf-8")
    print(bericht(res))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
