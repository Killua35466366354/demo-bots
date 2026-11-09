"""Kirons zwei TradingView-Strategien auf 5-Min.-Kerzen: A (Long) und B (Short) auf 21 Märkten.

Regeln: suche/VORAB_pine5m.yaml (versiegelt im Journal, bevor gerechnet wurde). Kirons Wunsch vom 09.11.2026 20:41 UTC.
Drei Varianten je Markt:
  pine       Ausstieg nur über das Pine-Ausstiegssignal der eigenen Seite (steht für Kirons eigenen Ausstieg)
  abfaenger  wie pine plus Trade-Abfänger wie beim Gold-Hand-Bot (Fehltrade und Notbremse)
  tp3        Take-Profit +0,6 R (= 3 € bei 5 € je R), kein Stop, kein Pine-Ausstieg
Alles in R gerechnet, 1 R = 3 x ATR(14) der 5-Min.-Kerzen beim Signal, mindestens 4 x Spread.

Aufruf: python -m suche.pine5m [--daten ORDNER] [--nur XAUUSD,EURUSD]
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd
import yaml

from gold.backtest import pine_port as pp
from suche.runde1 import journal_lines, last_value, sha256_text

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_pine5m.yaml"
KEY = "VORAB_pine5m sha256 "
DATEN = pathlib.Path("/mnt/project-files/strategie-suche/daten")
ZEITRAUM = ("2024-11-01", "2026-10-30 23:59")
HAELFTEN = (("2024-11-01", "2025-10-31 23:59"), ("2025-11-01", "2026-10-30 23:59"))
JAHR_2026 = ("2026-01-01", "2026-10-30 23:59")
KONTROLLE = ("2022-11-01", "2024-10-31 23:59")
VORLAUF = pd.Timedelta(days=60)
MAX_OFFEN = 4
R_ATR, R_MIN_SPREAD, ATR_N = 3.0, 4.0, 14
SWAP_JAHR = 0.05
TP_R = 0.6                       # 3 € bei 5 € je R
FEHL_R, ZIEL1_R, FEHL_STOP_R, FEHL_TP_R = 0.5, 0.75, 1.0, 0.0
NOT_R, NOT_ABSTAND_R = 1.0, 0.5
ROBUST = 1.5
MIN_TRADES = 100
EXTRA = [{"symbol": "AUDNZD", "name": "AUD/NZD", "art": "Währung", "spread": 0.0003, "stunden": [7, 20]},
         {"symbol": "GBPNZD", "name": "GBP/NZD", "art": "Währung", "spread": 0.0005, "stunden": [7, 20]}]
WEG = {"SPXUSD", "NSXUSD", "GBPUSD"}   # handeln schon andere Bots auf den Konten "US500" und "Vortag USDJPY"
VARIANTEN = ("pine", "abfaenger", "tp3")


def check_vorab() -> dict:
    text = VORAB.read_text(encoding="utf-8")
    if last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("VORAB_pine5m.yaml passt nicht zur Prüfsumme im Journal. Erst versiegeln, dann rechnen.")
    return yaml.safe_load(text)["pine5m"]


def maerkte() -> list[dict]:
    r1 = yaml.safe_load((ROOT / "suche" / "VORAB.yaml").read_text(encoding="utf-8"))["runde_1"]["maerkte"]
    return list(r1) + EXTRA


def lade(symbol: str, ordner: pathlib.Path = DATEN) -> pd.DataFrame:
    df = pd.read_csv(ordner / f"{symbol}_5min.csv.gz", parse_dates=["utc"], index_col="utc")
    df = df[df.index >= pd.Timestamp(KONTROLLE[0]) - VORLAUF]
    return df[~df.index.duplicated()].sort_index()


def atr_rma(df: pd.DataFrame, n: int = ATR_N) -> pd.Series:
    c1 = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - c1).abs(), (df["low"] - c1).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def in_stunden(idx: pd.DatetimeIndex, stunden) -> np.ndarray:
    h = idx.hour + idx.minute / 60
    a, b = stunden
    return (h >= a) & (h < b)


class Markt:
    """Kerzen, Signale und R eines Marktes, einmal gerechnet für alle Zeiträume und Varianten."""

    def __init__(self, spec: dict, df: pd.DataFrame):
        self.spec, self.df = spec, df
        self.o, self.h, self.l, self.c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        self.t = df.index
        self.n = len(df)
        sa, sb = pp.signals_a_long(df), pp.signals_b_short(df)
        self.ein = {1: sa["entry"].fillna(False).to_numpy(bool), -1: sb["entry"].fillna(False).to_numpy(bool)}
        self.aus = {1: sa["exit"].fillna(False).to_numpy(bool), -1: sb["exit"].fillna(False).to_numpy(bool)}
        self.atr = atr_rma(df).to_numpy(float)
        self.zeit_ok = in_stunden(self.t, spec["stunden"])
        self.tag = (self.t - pd.Timedelta(hours=22)).floor("D")       # Swap-Nacht: 22 Uhr UTC
        self.tag_nr = ((self.tag - pd.Timestamp("2000-01-01")) // pd.Timedelta(days=1)).to_numpy()
        # nächstes Ausstiegssignal ab jeder Kerze (inklusive), -1 wenn keines mehr kommt
        self.naechster_aus = {d: self._naechster(self.aus[d]) for d in (1, -1)}
        # letzte Kerze jedes Kalendertags (UTC) für die Tagesbewertung
        tage = self.t.floor("D")
        self.tagesende = np.flatnonzero(np.r_[tage[1:] != tage[:-1], True])

    @staticmethod
    def _naechster(mask: np.ndarray) -> np.ndarray:
        idx = np.where(mask, np.arange(len(mask)), len(mask))
        nxt = np.minimum.accumulate(idx[::-1])[::-1]
        return np.where(nxt >= len(mask), -1, nxt)

    def r_dist(self, i: int) -> float:
        return max(R_ATR * self.atr[i], R_MIN_SPREAD * self.spec["spread"])

    def kandidaten(self, von: str, bis: str) -> list[tuple[int, int]]:
        """(Signal-Kerze, Richtung) in Zeitfolge. Long und Short in derselben Kerze widersprechen sich: beide verfallen,
        außer eine Seite ist schon offen (das entscheidet simuliere)."""
        a, b = self.t.searchsorted(pd.Timestamp(von)), self.t.searchsorted(pd.Timestamp(bis), side="right")
        out = []
        for i in range(max(a, 1), min(b, self.n - 1)):
            if not self.zeit_ok[i] or not np.isfinite(self.atr[i]):
                continue
            if self.ein[1][i] and self.ein[-1][i]:
                out.append((i, 0))
            elif self.ein[1][i]:
                out.append((i, 1))
            elif self.ein[-1][i]:
                out.append((i, -1))
        return out

    def _profit(self, i0: int, d: int, sp: float, entry: float, r: float):
        """Ab Kerze i0 bis Datenende in R aus Sicht des Trades: Eröffnung, bester und schlechtester Kurs, Schluss.
        Long verkauft zum Bid, Short kauft zum Ask (Bid plus Spread)."""
        sl = slice(i0, self.n)
        if d == 1:
            return ((self.o[sl] - entry) / r, (self.h[sl] - entry) / r, (self.l[sl] - entry) / r, (self.c[sl] - entry) / r)
        return ((entry - self.o[sl] - sp) / r, (entry - self.l[sl] - sp) / r, (entry - self.h[sl] - sp) / r,
                (entry - self.c[sl] - sp) / r)

    def trade(self, i: int, d: int, variante: str, faktor: float = 1.0) -> dict:
        """Ein Trade aus dem Signal in Kerze i, Füllung zur Eröffnung von i+1. Unabhängig von anderen Trades."""
        sp = self.spec["spread"] * faktor
        i0 = i + 1
        r = self.r_dist(i)
        entry = self.o[i0] + sp if d == 1 else self.o[i0]
        opn, fav, adv, cls = self._profit(i0, d, sp, entry, r)
        m = len(opn)
        s = self.naechster_aus[d][i0] if variante != "tp3" else -1     # Pine-Ausstiegssignal ab i0
        ende = m - 1 if s < 0 or s + 1 >= self.n else s - i0          # letzte Kerze, in der Stop/Ziel noch zählen
        grund, k, res = None, None, None

        def erst(mask):
            j = int(np.argmax(mask)) if len(mask) else 0
            return j if len(mask) and mask[j] else None

        if variante == "tp3":
            j = erst((opn >= TP_R) | (fav >= TP_R))
            if j is not None:
                k, res, grund = j, (opn[j] if opn[j] >= TP_R else TP_R), "ziel"
        elif variante == "abfaenger":
            w = slice(0, ende + 1)
            jf, jz = erst(adv[w] <= -FEHL_R), erst(fav[w] >= ZIEL1_R)
            if jf is not None and (jz is None or jf <= jz):
                stop, tp, ab, grund = -FEHL_STOP_R, FEHL_TP_R, jf + 1, "fehltrade"
            elif jz is not None:
                jn = erst(adv[jz + 1:ende + 1] <= -NOT_R)
                stop, tp, ab, grund = (None, None, None, None) if jn is None else \
                    (cls[jz + 1 + jn] - NOT_ABSTAND_R, None, jz + 2 + jn, "notbremse")
            else:
                stop = None
            if stop is not None and ab <= ende:
                w2 = slice(ab, ende + 1)
                ev = (opn[w2] <= stop) | (adv[w2] <= stop)
                if tp is not None:
                    ev = ev | (opn[w2] >= tp) | (fav[w2] >= tp)
                j = erst(ev)
                if j is not None:
                    jj = ab + j
                    if opn[jj] <= stop or (tp is not None and opn[jj] >= tp):
                        res = opn[jj]
                    elif adv[jj] <= stop:
                        res = stop
                    else:
                        res = tp
                    k = jj
                    grund = grund + ("_stop" if res <= stop or res < 0 else "_einstand")
        if k is None:
            if variante != "tp3" and s >= 0 and s + 1 < self.n:
                k, res, grund = s + 1 - i0, opn[s + 1 - i0], "pine"
            else:
                k, res, grund = m - 1, cls[m - 1], "offen"
        ie = i0 + k
        naechte = int(self.tag_nr[ie] - self.tag_nr[i0])
        swap = naechte * SWAP_JAHR / 365 * entry / r
        return {"i": i, "i0": i0, "ie": ie, "d": d, "r_dist": r, "entry": entry, "r": float(res - swap),
                "grund": grund, "kerzen": int(ie - i0), "swap_r": float(swap)}

    def simuliere(self, von: str, bis: str, variante: str, faktor: float = 1.0) -> list[dict]:
        """Alle Signale im Zeitraum mit den Kontoregeln: höchstens 4 offen, nie gegen die Gegenrichtung."""
        offen: list[dict] = []
        out = []
        for i, d in self.kandidaten(von, bis):
            i0 = i + 1
            # zur Eröffnung geschlossen (Pine-Ausstieg) ist vor der neuen Füllung zu, in der Kerze erst danach
            offen = [o for o in offen if o["ie"] > i0 or (o["ie"] == i0 and o["grund"] not in ("pine",))]
            if d == 0:
                if not offen:
                    continue
                d = offen[0]["d"]            # widersprüchliches Signal: nur die offene Seite stockt auf
            if len(offen) >= MAX_OFFEN or any(o["d"] != d for o in offen):
                continue
            tr = self.trade(i, d, variante, faktor)
            offen.append(tr)
            out.append(tr)
        return out

    def tageswerte(self, trades: list[dict], von: str) -> np.ndarray:
        """Konto in R zum Tagesschluss, offene Positionen zum Schlusskurs bewertet (für tp3 wichtig)."""
        if not trades:
            return np.zeros(1)
        a = self.t.searchsorted(pd.Timestamp(von))
        ende = max(t["ie"] for t in trades)
        tage = self.tagesende[(self.tagesende >= a) & (self.tagesende <= ende)]
        if len(tage) == 0:
            return np.zeros(1)
        werte = np.zeros(len(tage))
        for t in trades:
            # realisiert ab dem Tag des Ausstiegs
            werte[tage >= t["ie"]] += t["r"]
            offen = (tage >= t["i0"]) & (tage < t["ie"])
            if offen.any():
                px = self.c[tage[offen]]
                sp = 0.0 if t["d"] == 1 else self.spec["spread"]
                werte[offen] += ((px - t["entry"]) if t["d"] == 1 else (t["entry"] - px - sp)) / t["r_dist"]
        return werte


def kennzahlen(m: Markt, trades: list[dict], von: str, bis: str, tage: np.ndarray | None = None) -> dict:
    wochen = (pd.Timestamp(bis) - pd.Timestamp(von)) / pd.Timedelta(days=7)
    r = np.array([t["r"] for t in trades]) if trades else np.zeros(0)
    gew, ver = r[r > 0].sum(), -r[r < 0].sum()
    pf = round(float(gew / ver), 2) if ver > 0 else (99.0 if gew > 0 else 0.0)
    if tage is None:
        reihen = np.cumsum([t["r"] for t in sorted(trades, key=lambda t: t["ie"])]) if trades else np.zeros(1)
    else:
        reihen = tage
    dd = float(np.max(np.maximum.accumulate(np.r_[0.0, reihen]) - np.r_[0.0, reihen])) if len(reihen) else 0.0
    dauer = [t["kerzen"] * 5 / 60 for t in trades]
    gruende: dict[str, int] = {}
    for t in trades:
        gruende[t["grund"]] = gruende.get(t["grund"], 0) + 1
    return {"trades": len(trades), "je_woche": round(len(trades) / wochen, 2), "pf_r": pf,
            "summe_r": round(float(r.sum()), 1), "max_rueckgang_r": round(dd, 1),
            "haltedauer_std_median": round(float(np.median(dauer)), 1) if dauer else None,
            "haltedauer_std_mittel": round(float(np.mean(dauer)), 1) if dauer else None,
            "long_r": round(float(sum(t["r"] for t in trades if t["d"] == 1)), 1),
            "short_r": round(float(sum(t["r"] for t in trades if t["d"] == -1)), 1),
            "long_n": sum(1 for t in trades if t["d"] == 1), "short_n": sum(1 for t in trades if t["d"] == -1),
            "trefferquote_pct": round(100 * float((r > 0).mean()), 1) if len(r) else None,
            "gruende": gruende, "swap_r": round(float(sum(t["swap_r"] for t in trades)), 1)}


def teil(trades: list[dict], m: Markt, von: str, bis: str) -> list[dict]:
    a, b = pd.Timestamp(von), pd.Timestamp(bis)
    return [t for t in trades if a <= m.t[t["i0"]] <= b]


def rechne_markt(spec: dict, ordner: pathlib.Path = DATEN) -> dict:
    m = Markt(spec, lade(spec["symbol"], ordner))
    out = {"symbol": spec["symbol"], "name": spec["name"], "kandidat": spec["symbol"] not in WEG,
           "kerzen": m.n, "bis": str(m.t[-1]), "varianten": {}}
    for v in VARIANTEN:
        tr = m.simuliere(*ZEITRAUM, v)
        tr_rob = m.simuliere(*ZEITRAUM, v, ROBUST)
        tr_k = m.simuliere(*KONTROLLE, v)
        tg = m.tageswerte(tr, ZEITRAUM[0]) if v == "tp3" else None
        tgk = m.tageswerte(tr_k, KONTROLLE[0]) if v == "tp3" else None
        out["varianten"][v] = {
            "zeitraum": kennzahlen(m, tr, *ZEITRAUM, tg),
            "robust": kennzahlen(m, tr_rob, *ZEITRAUM),
            "haelfte_1": kennzahlen(m, teil(tr, m, *HAELFTEN[0]), *HAELFTEN[0]),
            "haelfte_2": kennzahlen(m, teil(tr, m, *HAELFTEN[1]), *HAELFTEN[1]),
            "jahr_2026": kennzahlen(m, teil(tr, m, *JAHR_2026), *JAHR_2026),
            "kontrolle": kennzahlen(m, tr_k, *KONTROLLE, tgk),
        }
        if v == "tp3":
            offen = [t for t in tr if t["grund"] == "offen"]
            out["varianten"][v]["offen_am_ende"] = {"n": len(offen), "r": round(sum(t["r"] for t in offen), 1),
                                                     "aeltester_tage": round(max(((m.n - 1 - t["i0"]) * 5 / 1440
                                                                                 for t in offen), default=0), 0)}
    return out


def bestanden(v: dict) -> tuple[bool, list[str]]:
    z = v["zeitraum"]
    fehl = []
    if z["trades"] < MIN_TRADES:
        fehl.append(f"nur {z['trades']} Trades")
    if z["pf_r"] < 1.2:
        fehl.append(f"Gewinnfaktor {z['pf_r']}")
    if v["robust"]["pf_r"] < 1.0:
        fehl.append(f"mit 1,5-fachem Spread {v['robust']['pf_r']}")
    for k, name in (("haelfte_1", "1. Hälfte"), ("haelfte_2", "2. Hälfte"), ("jahr_2026", "2026"),
                    ("kontrolle", "Kontrolle 2022-24")):
        if v[k]["pf_r"] <= 1.0:
            fehl.append(f"{name} {v[k]['pf_r']}")
    return not fehl, fehl


def urteil(res: list[dict]) -> dict:
    zeilen = []
    for r in res:
        ok, fehl = bestanden(r["varianten"]["abfaenger"])
        r["bestanden"], r["verfehlt"] = ok, fehl
        zeilen.append(r)
    kand = [r for r in zeilen if r["kandidat"] and r["varianten"]["abfaenger"]["zeitraum"]["trades"] >= MIN_TRADES]
    key = lambda r: (r["varianten"]["abfaenger"]["zeitraum"]["pf_r"], r["varianten"]["abfaenger"]["zeitraum"]["trades"])
    ok = sorted([r for r in kand if r["bestanden"]], key=key, reverse=True)
    if ok:
        return {"bester": ok[0]["symbol"], "bestanden": True, "bestandene": [r["symbol"] for r in ok]}
    best = sorted(kand, key=key, reverse=True)
    return {"bester": best[0]["symbol"] if best else None, "bestanden": False, "bestandene": [],
            "hinweis": "Kein Markt bestanden. Der beste Kandidat geht nur als Demo-Vorwärtstest live (Test nicht bestanden)."}


def bericht(res: list[dict], u: dict) -> str:
    z = ["# Kirons Pine A (Long) und B (Short) auf 5 Min.", "",
         f"Regeln suche/VORAB_pine5m.yaml. Zeitraum {ZEITRAUM[0]} bis {ZEITRAUM[1][:10]}, Kontrolle {KONTROLLE[0]} bis "
         f"{KONTROLLE[1][:10]}. R = 3 x ATR(14) auf 5 Min. Spread ×1, robust ×1,5. Swap 5 %/Jahr.", "",
         f"**Bester Markt: {u['bester']}**, " + ("bestanden." if u["bestanden"] else "kein Markt hat bestanden."), ""]
    for v in VARIANTEN:
        z += [f"## Variante {v}", "",
              "| Markt | Trades | je Woche | PF | Summe R | Rückgang R | Std. (Median) | PF ×1,5 | H1 | H2 | 2026 | Kontrolle |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in sorted(res, key=lambda r: -r["varianten"][v]["zeitraum"]["pf_r"]):
            a = r["varianten"][v]
            zz = a["zeitraum"]
            name = r["symbol"] + ("" if r["kandidat"] else " (nicht wählbar)")
            z.append(f"| {name} | {zz['trades']} | {zz['je_woche']} | {zz['pf_r']} | {zz['summe_r']} | "
                     f"{zz['max_rueckgang_r']} | {zz['haltedauer_std_median']} | {a['robust']['pf_r']} | "
                     f"{a['haelfte_1']['pf_r']} | {a['haelfte_2']['pf_r']} | {a['jahr_2026']['pf_r']} | "
                     f"{a['kontrolle']['pf_r']} |")
        z.append("")
    return "\n".join(z) + "\n"


def main(argv: list[str]) -> int:
    check_vorab()
    ordner = DATEN
    nur = None
    if "--daten" in argv:
        ordner = pathlib.Path(argv[argv.index("--daten") + 1])
    if "--nur" in argv:
        nur = set(argv[argv.index("--nur") + 1].split(","))
    res = []
    for spec in maerkte():
        if nur and spec["symbol"] not in nur:
            continue
        r = rechne_markt(spec, ordner)
        a = r["varianten"]["abfaenger"]["zeitraum"]
        print(spec["symbol"], a["trades"], a["pf_r"], a["summe_r"], flush=True)
        res.append(r)
    u = urteil(res)
    erg = {"vorab_sha256": sha256_text(VORAB.read_text(encoding="utf-8")), "urteil": u, "maerkte": res}
    if not nur:
        (ROOT / "suche" / "ergebnis_pine5m.json").write_text(json.dumps(erg, ensure_ascii=False, indent=1) + "\n",
                                                             encoding="utf-8")
        (ROOT / "suche" / "ergebnis_pine5m.md").write_text(bericht(res, u), encoding="utf-8")
    print(json.dumps(u, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
