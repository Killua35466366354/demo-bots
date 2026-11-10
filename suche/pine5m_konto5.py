"""Pine-Gold-Hand-Bot auf Account 5: Hedging, Termin-Pause und Hintergrund im Test (suche/VORAB_pine5m_konto5.yaml).

Einstiege, Kosten, R, Abfänger und Zeiträume aus suche/pine5m.py (Variante abfaenger), Markt nur XAUUSD.
Aufruf: python -m suche.pine5m_konto5
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
VORAB = ROOT / "suche" / "VORAB_pine5m_konto5.yaml"
KEY = "VORAB_pine5m_konto5 sha256 "
SYMBOL = "XAUUSD"
VARIANTEN = ("abfaenger", "k5_hedge", "k5_hedge_termin", "k5_hedge_termin_hg")
NEWS_VOR, NEWS_NACH = pd.Timedelta(minutes=60), pd.Timedelta(minutes=30)
HG_SMA_TAGE, HG_EMA_4H = 50, 50


def check_vorab() -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("VORAB_pine5m_konto5.yaml passt nicht zur Prüfsumme im Journal.")
    return yaml.safe_load(text)["pine5m_konto5"]


def termin_sperre(t: pd.DatetimeIndex) -> np.ndarray:
    """True, wenn der Signalschluss (Kerzenbeginn + 5 Min.) 60 Min. vor bis 30 Min. nach einem Termin liegt."""
    from gold.v2 import termine
    ev = termine.load()["utc"].to_numpy("datetime64[ns]")
    schluss = (t + pd.Timedelta(minutes=5)).to_numpy("datetime64[ns]")
    # nächster Termin ab schluss - 30 Min.: liegt er vor schluss + 60 Min., ist gesperrt
    j = np.searchsorted(ev, schluss - np.timedelta64(30, "m"))
    nxt = np.where(j < len(ev), ev[np.minimum(j, len(ev) - 1)], np.datetime64("2262-01-01"))
    return nxt <= schluss + np.timedelta64(60, "m")


def hintergrund(df: pd.DataFrame) -> np.ndarray:
    """+1: letzter fertiger Tagesschluss über SMA 50 und letzter fertiger 4-Std.-Schluss über EMA 50, -1: beide darunter,
    0 sonst. Stand zum Signalschluss (Kerzenbeginn + 5 Min.), nur fertige Kerzen."""
    c = df["close"]
    tag = c.resample("1D").last().dropna()
    sma = tag.rolling(HG_SMA_TAGE).mean()
    a_tag = np.sign(tag - sma).where(sma.notna(), 0.0)
    a_tag.index = a_tag.index + pd.Timedelta(days=1)            # gilt ab Tagesende
    h4 = c.resample("4h").last().dropna()
    ema = h4.ewm(span=HG_EMA_4H, adjust=False).mean()
    f_h4 = np.sign(h4 - ema)
    f_h4.iloc[:HG_EMA_4H + 10] = 0.0
    f_h4.index = f_h4.index + pd.Timedelta(hours=4)             # gilt ab Kerzenende
    schluss = df.index + pd.Timedelta(minutes=5)
    a = a_tag.reindex(schluss, method="ffill").fillna(0.0).to_numpy()
    f = f_h4.reindex(schluss, method="ffill").fillna(0.0).to_numpy()
    return np.where((a > 0) & (f > 0), 1, np.where((a < 0) & (f < 0), -1, 0))


class Markt(p5.Markt):
    def __init__(self, spec: dict, df: pd.DataFrame):
        super().__init__(spec, df)
        self.sperre = termin_sperre(self.t)
        self.hg = hintergrund(df)

    def simuliere(self, von: str, bis: str, variante: str, faktor: float = 1.0) -> list[dict]:
        if variante == "abfaenger":
            return super().simuliere(von, bis, variante, faktor)
        termin, hg = "termin" in variante, variante.endswith("_hg")
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
            if len(offen) >= p5.MAX_OFFEN:
                continue
            if termin and self.sperre[i]:
                continue
            if hg and self.hg[i] == -d:
                continue
            tr = self.trade(i, d, "abfaenger", faktor)
            offen.append(tr)
            out.append(tr)
        return out


def extra(trades: list[dict]) -> dict:
    r = np.array([t["r"] for t in trades]) if trades else np.zeros(0)
    return {"groesster_verlust_r": round(float(r.min()), 2) if len(r) else None,
            "gleichzeitig_beide_seiten": None}


def beide_seiten(trades: list[dict]) -> int:
    """Wie oft beim Einstieg eine Position der Gegenrichtung offen war (nur mit Hedging möglich)."""
    n = 0
    for k, t in enumerate(trades):
        if any(o["d"] != t["d"] and o["i0"] <= t["i0"] < o["ie"] for o in trades[:k]):
            n += 1
    return n


def rechne(ordner: pathlib.Path = p5.DATEN) -> dict:
    spec = next(s for s in p5.maerkte() if s["symbol"] == SYMBOL)
    m = Markt(spec, p5.lade(SYMBOL, ordner))
    out = {}
    for var in VARIANTEN:
        tr = m.simuliere(*p5.ZEITRAUM, var)
        tr_k = m.simuliere(*p5.KONTROLLE, var)
        out[var] = {
            "zeitraum": p5.kennzahlen(m, tr, *p5.ZEITRAUM),
            "robust": p5.kennzahlen(m, m.simuliere(*p5.ZEITRAUM, var, p5.ROBUST), *p5.ZEITRAUM),
            "haelfte_1": p5.kennzahlen(m, p5.teil(tr, m, *p5.HAELFTEN[0]), *p5.HAELFTEN[0]),
            "haelfte_2": p5.kennzahlen(m, p5.teil(tr, m, *p5.HAELFTEN[1]), *p5.HAELFTEN[1]),
            "jahr_2026": p5.kennzahlen(m, p5.teil(tr, m, *p5.JAHR_2026), *p5.JAHR_2026),
            "kontrolle": p5.kennzahlen(m, tr_k, *p5.KONTROLLE),
            "groesster_verlust_r": extra(tr)["groesster_verlust_r"],
            "gegen_offene_seite": beide_seiten(tr)}
        z = out[var]["zeitraum"]
        print(var, z["trades"], z["pf_r"], z["summe_r"], out[var]["kontrolle"]["pf_r"], flush=True)
    return out


def wahl(res: dict) -> dict:
    a, b = res["k5_hedge_termin"], res["k5_hedge_termin_hg"]
    hg = b["zeitraum"]["pf_r"] > a["zeitraum"]["pf_r"] and b["kontrolle"]["pf_r"] > a["kontrolle"]["pf_r"]
    live = "k5_hedge_termin_hg" if hg else "k5_hedge_termin"
    ok, fehl = p5.bestanden(res[live])
    return {"hintergrund_live": hg, "live_variante": live, "bestanden": ok, "verfehlt": fehl,
            "alle": {k: p5.bestanden(v) for k, v in res.items()}}


def bericht(res: dict, u: dict) -> str:
    z = ["# Pine-Gold-Hand-Bot auf Account 5 (Gold 5 Min.)", "",
         "Regeln suche/VORAB_pine5m_konto5.yaml. Alle Varianten mit dem Abfänger aus VORAB_pine5m.", "",
         f"**Live: {u['live_variante']}** (Hintergrund {'drin' if u['hintergrund_live'] else 'draußen'}), "
         + ("bestanden." if u["bestanden"] else "nicht bestanden: " + "; ".join(u["verfehlt"]) + "."), "",
         "| Variante | Trades | je Woche | PF | Summe R | Rückgang R | Long R | Short R | gegen offene Seite | "
         "größter Verlust R | PF ×1,5 | H1 | H2 | 2026 | Kontrolle | Summe R Kontrolle |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, a in res.items():
        zz = a["zeitraum"]
        z.append(f"| {k} | {zz['trades']} | {zz['je_woche']} | {zz['pf_r']} | {zz['summe_r']} | "
                 f"{zz['max_rueckgang_r']} | {zz['long_r']} | {zz['short_r']} | {a['gegen_offene_seite']} | "
                 f"{a['groesster_verlust_r']} | {a['robust']['pf_r']} | {a['haelfte_1']['pf_r']} | "
                 f"{a['haelfte_2']['pf_r']} | {a['jahr_2026']['pf_r']} | {a['kontrolle']['pf_r']} | "
                 f"{a['kontrolle']['summe_r']} |")
    return "\n".join(z) + "\n"


def main(argv: list[str]) -> int:
    check_vorab()
    p5.check_vorab()
    res = rechne()
    u = wahl(res)
    erg = {"vorab_sha256": sha256_text(VORAB.read_text(encoding="utf-8")), "wahl": u, "varianten": res}
    (ROOT / "suche" / "ergebnis_pine5m_konto5.json").write_text(json.dumps(erg, ensure_ascii=False, indent=1) + "\n",
                                                               encoding="utf-8")
    (ROOT / "suche" / "ergebnis_pine5m_konto5.md").write_text(bericht(res, u), encoding="utf-8")
    print(json.dumps({k: v for k, v in u.items() if k != "alle"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
