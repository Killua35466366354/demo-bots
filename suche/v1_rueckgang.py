"""Test Rückgänge von V1 (Regeln suche/VORAB_v1_rueckgang.yaml, versiegelt vor dem Rechnen).

V1 mit wachsendem Einsatz (2 % des Kontostands, nur die Grenze des Brokers, jeder Trade 0,1 R schlechter) auf einem
Konto mit 1.000 €. Drei live erkennbare Gründe lassen Trades aus: F1 Gold nervös gegen sich selbst (GVZ), F2 zu viele
offen, F3 Gold bei Angst an der Börse (VIX). Gewählt an November 2024 bis Dezember 2025, Urteil an Januar bis Oktober
2026 gegen dasselbe Konto ohne Filter, mit Zufallsvergleich, Holm über alle drei und einem Probelauf auf gemischten R.

    python -m suche.v1_rueckgang <Projektordner> [--json <datei>]   # schreibt suche/ergebnis_v1_rueckgang.md

Spricht mit keinem Broker und ändert keinen Bot. Rechnet nur einmal: Liegt das Ergebnis schon da, bricht es ab.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import numpy as np
import pandas as pd
import yaml

from suche.buendel_max import margin_auffuellen
from suche.markt_regime import holm
from suche.runde1 import last_value, sha256_text

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_v1_rueckgang.yaml"
ERGEBNIS = ROOT / "suche" / "ergebnis_v1_rueckgang.md"
PROTOKOLL = ROOT / "journal" / "strategie-suche-protokoll.md"
KEY = "VORAB_v1_rueckgang sha256 "

EINSATZ = 0.02          # 2 % des Kontostands je Trade ("zurück ins Konto")
GVZ_TAGE, GVZ_QUANTIL = 250, 0.8
VIX_GRENZE = 20.67
GEDRAENGE = 3
MIN_AUS = 20
N_ZUFALL, SEED_ZUFALL = 2000, 20261126
N_PROBE, N_PROBE_ZUFALL, SEED_PROBE, PROBE_HOECHSTENS = 200, 200, 20261127, 0.10
FILTER = ("F1", "F2", "F3")


def regel() -> dict:
    return yaml.safe_load(VORAB.read_text(encoding="utf-8"))["v1_rueckgang"]


def siegel_ok() -> bool:
    lines = PROTOKOLL.read_text(encoding="utf-8").splitlines()
    return last_value(lines, KEY) == sha256_text(VORAB.read_text(encoding="utf-8"))


def _sha(pfad: pathlib.Path) -> str:
    return hashlib.sha256(pfad.read_bytes()).hexdigest()


def lade_trades(datei: pathlib.Path, soll: str, bots: list[str]) -> pd.DataFrame:
    if _sha(datei) != soll:
        raise SystemExit(f"Trade-Datei passt nicht zur Regel: {_sha(datei)}")
    t = pd.read_csv(datei, parse_dates=["ein", "aus"])
    t = margin_auffuellen(t)
    return t[t.id.isin(bots)].sort_values(["ein", "id"]).reset_index(drop=True)


def lade_fred(datei: pathlib.Path, soll: str) -> pd.Series:
    if _sha(datei) != soll:
        raise SystemExit(f"FRED-Datei {datei.name} passt nicht zur Regel: {_sha(datei)}")
    d = pd.read_csv(datei, parse_dates=["observation_date"]).set_index("observation_date")
    return pd.to_numeric(d.iloc[:, 0], errors="coerce").dropna().sort_index()


def letzter_wert(serie: pd.Series, einstiege: pd.Series) -> np.ndarray:
    """Position des letzten Werts, der beim Einstieg gilt. Der Wert vom Tag D gilt ab D+1 00:00 UTC. -1 heißt keiner."""
    gilt_ab = (serie.index + pd.Timedelta(days=1)).to_numpy(dtype="datetime64[ns]")
    return np.searchsorted(gilt_ab, einstiege.to_numpy(dtype="datetime64[ns]"), side="right") - 1


def merkmale(t: pd.DataFrame, vix: pd.Series, gvz: pd.Series) -> pd.DataFrame:
    """Je Trade: GVZ und seine Grenze, VIX, und ob F1 und F3 ihn auslassen. F2 hängt vom Konto ab."""
    gold = (t.markt == "GOLD").to_numpy()
    g = gvz.to_numpy()
    pg = letzter_wert(gvz, t.ein)
    gw = np.where(pg >= 0, g[np.clip(pg, 0, None)], np.nan)
    grenze = np.array([np.quantile(g[p - GVZ_TAGE:p], GVZ_QUANTIL) if p >= GVZ_TAGE else np.nan for p in pg])
    v = vix.to_numpy()
    pv = letzter_wert(vix, t.ein)
    vw = np.where(pv >= 0, v[np.clip(pv, 0, None)], np.nan)
    f1 = gold & ~np.isnan(grenze) & (gw > grenze)
    f3 = gold & ~np.isnan(vw) & (vw > VIX_GRENZE)
    return pd.DataFrame({"gvz": gw, "gvz_grenze": grenze, "vix": vw, "F1": f1, "F3": f3}, index=t.index)


def zeitraum(t: pd.DataFrame, von: str, bis: str) -> np.ndarray:
    """Positionen der Trades, deren Einstieg im Zeitraum liegt (bis einschließlich)."""
    ende = pd.Timestamp(bis) + pd.Timedelta(days=1)
    return np.flatnonzero(((t.ein >= pd.Timestamp(von)) & (t.ein < ende)).to_numpy())


class Konto:
    """Feste Reihenfolge der Ereignisse für eine Auswahl von Trades. Schluss vor Eröffnung bei gleicher Minute."""

    def __init__(self, t: pd.DataFrame, auswahl: np.ndarray, abzug: float = 0.1, start: float = 1000.0):
        self.auswahl = np.asarray(auswahl)
        sub = t.iloc[self.auswahl]
        ein = sub.ein.to_numpy(dtype="datetime64[m]").astype(np.int64)
        aus = sub.aus.to_numpy(dtype="datetime64[m]").astype(np.int64)
        ev = []
        for j in range(len(sub)):
            ev.append((int(ein[j]), 1, j))
            ev.append((int(aus[j]), 2 if aus[j] == ein[j] else 0, j))
        ev.sort(key=lambda e: (e[0], e[1]))
        self.ev = ev
        self.n = len(sub)
        self.r = sub.r.to_numpy(float)
        self.mj = sub.margin_je_r.to_numpy(float).tolist()
        self.abzug, self.start = abzug, start

    def lauf(self, raus=None, gedraenge: int | None = None, r=None, umkehr: bool = False, kurve: bool = False) -> dict:
        """raus: feste Auslassung je Trade (bool, Länge n). gedraenge: Auslassen ab so vielen offenen Trades.
        umkehr: statt auslassen umgedreht nehmen (-R, nur Auskunft). r: andere R je Trade (Probelauf)."""
        rr = (self.r if r is None else np.asarray(r, float)).tolist()
        raus = None if raus is None else np.asarray(raus, bool).tolist()
        mj, ab = self.mj, self.abzug
        stand = spitze = self.start
        offen_m, n_offen, leer = 0.0, 0, False
        stake, marg, vorz = [0.0] * self.n, [0.0] * self.n, [0.0] * self.n
        genommen, aus_f = [False] * self.n, [False] * self.n
        broker, ddp, dde = 0, 0.0, 0.0
        tief_zeit = spitze_zeit = None
        punkte = []
        for zeit, art, j in self.ev:
            if art == 1:
                flag = (raus is not None and raus[j]) or (gedraenge is not None and n_offen >= gedraenge)
                if flag:
                    aus_f[j] = True
                    if not umkehr:
                        continue
                s = EINSATZ * stand
                m = mj[j] * s
                if leer or offen_m + m > stand:
                    broker += 1
                    continue
                genommen[j], stake[j], marg[j] = True, s, m
                vorz[j] = -1.0 if (flag and umkehr) else 1.0
                offen_m += m
                n_offen += 1
            else:
                if not genommen[j]:
                    continue
                offen_m -= marg[j]
                n_offen -= 1
                if abs(offen_m) < 1e-9:
                    offen_m = 0.0
                stand += (vorz[j] * rr[j] - ab) * stake[j]
                if stand > spitze:
                    spitze = stand
                if (spitze - stand) / spitze > ddp:
                    ddp, dde = (spitze - stand) / spitze, spitze - stand
                if stand <= 0:
                    leer = True
                if kurve:
                    punkte.append((zeit, stand))
        out = {"ende": stand, "rueckgang_pct": ddp, "rueckgang_eur": dde, "spitze": spitze, "broker_aus": broker,
               "aus": np.array(aus_f), "genommen": np.array(genommen), "leer": leer}
        if kurve:
            out["punkte"] = punkte
        return out


def ausgelassen_r(k: Konto, res: dict, r=None) -> float:
    rr = k.r if r is None else np.asarray(r, float)
    return float((rr[res["aus"]] - k.abzug).sum())


def zufall_p(k: Konto, topf: np.ndarray, anzahl: int, ende_filter: float, n: int, seed: int) -> float:
    """Aus dem Topf (Positionen in k) n-mal genauso viele Trades zufällig auslassen und das Konto ohne Filter rechnen."""
    rng = np.random.default_rng(seed)
    if anzahl == 0 or anzahl > len(topf):
        return 1.0
    treffer = 0
    for _ in range(n):
        raus = np.zeros(k.n, bool)
        raus[rng.choice(topf, size=anzahl, replace=False)] = True
        treffer += k.lauf(raus=raus)["ende"] >= ende_filter - 1e-9
    return (treffer + 1) / (n + 1)


def filter_lauf(k: Konto, name: str, maske: dict, r=None, umkehr: bool = False, kurve: bool = False) -> dict:
    if name == "F2":
        return k.lauf(gedraenge=GEDRAENGE, r=r, umkehr=umkehr, kurve=kurve)
    return k.lauf(raus=maske[name], r=r, umkehr=umkehr, kurve=kurve)


def urteil(k: Konto, maske: dict, toepfe: dict, wahl_ok: dict, r=None, n_zufall: int = N_ZUFALL,
           seed: int = SEED_ZUFALL) -> dict:
    """Punkte 2 bis 6 der Regel je Filter (Punkt 1 kommt über wahl_ok). Gibt je Filter die Zahlen und bestanden."""
    ohne = k.lauf(r=r)
    out, p = {"ohne": ohne}, {}
    for f in FILTER:
        res = filter_lauf(k, f, maske, r=r)
        n_aus = int(res["aus"].sum())
        summe = ausgelassen_r(k, res, r)
        p[f] = zufall_p(_mit_r(k, r), toepfe[f], n_aus, res["ende"], n_zufall, seed)
        out[f] = {"res": res, "n_aus": n_aus, "summe_r_aus": summe, "p": p[f],
                  "punkte": {"min_aus": n_aus >= MIN_AUS, "summe_unter_0": summe < 0,
                             "ende_hoeher": res["ende"] > ohne["ende"],
                             "rueckgang_nicht_tiefer": res["rueckgang_pct"] <= ohne["rueckgang_pct"] + 1e-12}}
    h = holm(p, 0.05)
    for f in FILTER:
        out[f]["punkte"]["holm"] = h[f]
        out[f]["bestanden"] = bool(wahl_ok.get(f, True) and all(out[f]["punkte"].values()))
    return out


def _mit_r(k: Konto, r) -> Konto:
    """Dasselbe Konto mit anderen R (für den Zufallsvergleich im Probelauf)."""
    if r is None:
        return k
    k2 = object.__new__(Konto)
    k2.__dict__.update(k.__dict__)
    k2.r = np.asarray(r, float)
    return k2


def probelauf(k: Konto, maske: dict, toepfe: dict, n: int = N_PROBE, n_zufall: int = N_PROBE_ZUFALL,
              seed: int = SEED_PROBE) -> dict:
    rng = np.random.default_rng(seed)
    treffer, je = 0, {f: 0 for f in FILTER}
    for i in range(n):
        r = k.r[rng.permutation(k.n)]
        u = urteil(k, maske, toepfe, {}, r=r, n_zufall=n_zufall, seed=SEED_ZUFALL + 1 + i)
        if any(u[f]["bestanden"] for f in FILTER):
            treffer += 1
        for f in FILTER:
            je[f] += u[f]["bestanden"]
    return {"n": n, "mit_bestanden": treffer, "anteil": treffer / n, "je_filter": je, "taugt": treffer / n <= PROBE_HOECHSTENS}


def episoden(k: Konto, t: pd.DataFrame, mk: pd.DataFrame, anzahl: int = 3) -> list[dict]:
    """Die tiefsten Rückgänge (Höchststand bis Tief vor dem nächsten Höchststand) im Konto ohne Filter."""
    res = k.lauf(kurve=True)
    pkt = res["punkte"]
    werte = [k.start] + [v for _, v in pkt]
    zeiten = [None] + [z for z, _ in pkt]
    eps, hoch_i, tief_i = [], 0, 0
    for i in range(1, len(werte)):
        if werte[i] >= werte[hoch_i]:
            if werte[tief_i] < werte[hoch_i]:
                eps.append((hoch_i, tief_i))
            hoch_i = tief_i = i
        elif werte[i] < werte[tief_i]:
            tief_i = i
    if werte[tief_i] < werte[hoch_i]:
        eps.append((hoch_i, tief_i))
    eps.sort(key=lambda e: -(werte[e[0]] - werte[e[1]]) / werte[e[0]])
    sub = t.iloc[k.auswahl].reset_index(drop=True)
    sm = mk.iloc[k.auswahl].reset_index(drop=True)
    aus_min = sub.aus.to_numpy(dtype="datetime64[m]").astype(np.int64)
    out = []
    for a, b in eps[:anzahl]:
        za = zeiten[a] if zeiten[a] is not None else int(aus_min.min()) - 1
        zb = zeiten[b]
        drin = (aus_min > za) & (aus_min <= zb) & res["genommen"]
        je_bot = (sub.r[drin] - k.abzug).groupby(sub.id[drin]).agg(["size", "sum"]).sort_values("sum")
        out.append({"von": str(np.datetime64(za, "m").astype("datetime64[D]")), "bis": str(np.datetime64(zb, "m").astype("datetime64[D]")),
                    "hoch": werte[a], "tief": werte[b], "pct": (werte[a] - werte[b]) / werte[a], "trades": int(drin.sum()),
                    "je_bot": {i: {"n": int(r["size"]), "summe_r": float(r["sum"])} for i, r in je_bot.iterrows()},
                    "gold_anteil_r": float((sub.r[drin & (sub.markt == "GOLD").to_numpy()] - k.abzug).sum()),
                    "gvz_schnitt_gold": float(np.nanmean(sm.gvz[drin & (sub.markt == "GOLD").to_numpy()])) if (drin & (sub.markt == "GOLD").to_numpy()).any() else None,
                    "vix_schnitt": float(np.nanmean(sm.vix[drin]))})
    return out


def tageskurve(res: dict, von: str, bis: str, start: float) -> list[float]:
    s = pd.Series({pd.Timestamp(np.datetime64(z, "m")).normalize(): v for z, v in res["punkte"]})
    s = s.groupby(level=0).last()
    tage = pd.date_range(von, bis, freq="D")
    return [round(float(x), 2) for x in s.reindex(tage.union(s.index)).ffill().reindex(tage).fillna(start)]


def je_monat(k: Konto, t: pd.DataFrame, res: dict) -> dict:
    pkt = res["punkte"]
    out, vorher = {}, k.start
    for z, v in pkt:
        m = str(np.datetime64(z, "m").astype("datetime64[M]"))
        out[m] = out.get(m, 0.0) + v - vorher
        vorher = v
    return {m: round(x, 2) for m, x in sorted(out.items())}


def rechne(projekt: pathlib.Path, probe: bool = True) -> dict:
    rg = regel()
    t = lade_trades(projekt / "schatten-labor" / "alle_margin.csv", rg["trades"]["sha256"], rg["trades"]["bots"])
    vix = lade_fred(projekt / "strategie-suche" / "daten" / "fred" / "VIXCLS.csv", rg["kurse"]["vix"]["sha256"])
    gvz = lade_fred(projekt / "strategie-suche" / "daten" / "fred" / "GVZCLS.csv", rg["kurse"]["gvz"]["sha256"])
    mk = merkmale(t, vix, gvz)
    gold = (t.markt == "GOLD").to_numpy()
    e = {"trades": len(t)}

    def teil(von, bis):
        pos = zeitraum(t, von, bis)
        k = Konto(t, pos)
        maske = {f: mk[f].to_numpy()[pos] for f in ("F1", "F3")}
        toepfe = {"F1": np.flatnonzero(gold[pos]), "F3": np.flatnonzero(gold[pos]), "F2": np.arange(len(pos))}
        return k, maske, toepfe

    # Wahl
    kw, mw, _ = teil(*rg["wahl"]["zeitraum"])
    ohne_w = kw.lauf()
    wahl, wahl_ok = {}, {}
    for f in FILTER:
        res = filter_lauf(kw, f, mw)
        n_aus, summe = int(res["aus"].sum()), ausgelassen_r(kw, res)
        wahl_ok[f] = n_aus >= MIN_AUS and summe < 0
        wahl[f] = {"n_aus": n_aus, "summe_r_aus": summe, "ende": res["ende"], "rueckgang_pct": res["rueckgang_pct"], "ok": wahl_ok[f]}
    e["wahl"] = {"ohne": {"ende": ohne_w["ende"], "rueckgang_pct": ohne_w["rueckgang_pct"]}, **wahl}

    # Urteil 2026
    von, bis = rg["urteil"]["zeitraum"]
    ku, mu, tu = teil(von, bis)
    u = urteil(ku, mu, tu, wahl_ok)
    e["probelauf"] = probelauf(ku, mu, tu) if probe else None
    taugt = e["probelauf"] is None or e["probelauf"]["taugt"]
    ohne = ku.lauf(kurve=True)
    e["urteil"] = {"ohne": {"ende": ohne["ende"], "rueckgang_pct": ohne["rueckgang_pct"], "rueckgang_eur": ohne["rueckgang_eur"],
                            "trades": ku.n, "broker_aus": ohne["broker_aus"], "je_monat": je_monat(ku, t, ohne),
                            "kurve": tageskurve(ohne, von, bis, ku.start)}}
    for f in FILTER:
        x = u[f]
        rk = filter_lauf(ku, f, mu, kurve=True)
        um = filter_lauf(ku, f, mu, umkehr=True)
        e["urteil"][f] = {"n_aus": x["n_aus"], "summe_r_aus": x["summe_r_aus"], "ende": x["res"]["ende"],
                          "rueckgang_pct": x["res"]["rueckgang_pct"], "rueckgang_eur": x["res"]["rueckgang_eur"],
                          "p": x["p"], "punkte": x["punkte"], "bestanden": bool(x["bestanden"] and taugt),
                          "je_monat": je_monat(ku, t, rk), "kurve": tageskurve(rk, von, bis, ku.start),
                          "umkehr_bestfall_ende": um["ende"], "umkehr_bestfall_rueckgang_pct": um["rueckgang_pct"]}
    e["bestanden"] = [f for f in FILTER if e["urteil"][f]["bestanden"]]

    # Auskunft ganze Zeit
    kg, mg, _ = teil("2024-11-01", bis)
    og = kg.lauf(kurve=True)
    e["ganz"] = {"ohne": {"ende": og["ende"], "rueckgang_pct": og["rueckgang_pct"], "kurve": tageskurve(og, "2024-11-01", bis, kg.start)}}
    for f in FILTER:
        rk = filter_lauf(kg, f, mg, kurve=True)
        e["ganz"][f] = {"ende": rk["ende"], "rueckgang_pct": rk["rueckgang_pct"], "n_aus": int(rk["aus"].sum()),
                        "summe_r_aus": ausgelassen_r(kg, rk), "kurve": tageskurve(rk, "2024-11-01", bis, kg.start)}
    e["episoden"] = episoden(kg, t, mk)
    return e


NAMEN = {"F1": "F1 Gold nervös gegen sich selbst (GVZ)", "F2": "F2 zu viele offen (ab 3)", "F3": "F3 Gold bei Angst an der Börse (VIX über 20,67)"}


def _e(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".") + " €"


def _p(x: float, n: int = 0) -> str:
    return f"{100 * x:.{n}f}".replace(".", ",") + " %"


def _z(x: float, n: int = 1) -> str:
    return f"{x:.{n}f}".replace(".", ",")


def _r(x: float) -> str:
    return f"{x:+.1f}".replace(".", ",") + " R"


def bericht(e: dict) -> str:
    u, w = e["urteil"], e["wahl"]
    best = e["bestanden"]
    z = ["# Ergebnis: Rückgänge von V1", "",
         "Regeln: `suche/VORAB_v1_rueckgang.yaml`, versiegelt vor dem Rechnen. Rechnung: `python -m suche.v1_rueckgang <Projektordner>`.", ""]
    if best:
        z.append(f"**{len(best)} von 3 Filtern bestanden: " + ", ".join(NAMEN[f] for f in best) + ".** Das ist ein Kandidat für einen Demo-Bot, kein Beweis.")
    else:
        z.append("**Kein Filter bestanden.** Keiner der drei live erkennbaren Gründe macht V1 mit wachsendem Einsatz 2026 klar besser.")
    z += ["", f"Konto: 1.000 € am 01.01.2026, 2 % Einsatz je Trade vom Kontostand, nur die Grenze des Brokers, jeder Trade 0,1 R schlechter. "
          f"Ohne Filter am Ende {_e(u['ohne']['ende'])}, schlimmster Rückgang {_p(u['ohne']['rueckgang_pct'])}, {u['ohne']['trades']} Trades.", ""]
    pl = e.get("probelauf")
    if pl:
        z += [f"Probelauf: Mit gemischten R bestand in {pl['mit_bestanden']} von {pl['n']} Mischungen mindestens ein Filter "
              f"({_p(pl['anteil'])}, erlaubt höchstens 10 %). Der Test {'taugt' if pl['taugt'] else 'taugt nicht, darum besteht kein Filter'}.", ""]
    z += ["## Urteil 2026", "",
          "| Filter | Wahl erfüllt | ausgelassen | Summe R ausgelassen | Ende | Rückgang | p | Holm | bestanden |", "|---|---|---|---|---|---|---|---|---|"]
    for f in FILTER:
        x = u[f]
        z.append(f"| {NAMEN[f]} | {'ja' if w[f]['ok'] else 'nein'} | {x['n_aus']} | {_r(x['summe_r_aus'])} | {_e(x['ende'])} | "
                 f"{_p(x['rueckgang_pct'])} | {_z(x['p'], 4)} | {'ja' if x['punkte']['holm'] else 'nein'} | {'ja' if x['bestanden'] else 'nein'} |")
    z += ["", "## Wahl November 2024 bis Dezember 2025", "",
          f"Ohne Filter am Ende {_e(w['ohne']['ende'])}, Rückgang {_p(w['ohne']['rueckgang_pct'])}.", "",
          "| Filter | ausgelassen | Summe R ausgelassen | Ende | Rückgang | ins Urteil |", "|---|---|---|---|---|---|"]
    for f in FILTER:
        x = w[f]
        z.append(f"| {NAMEN[f]} | {x['n_aus']} | {_r(x['summe_r_aus'])} | {_e(x['ende'])} | {_p(x['rueckgang_pct'])} | {'ja' if x['ok'] else 'nein'} |")
    z += ["", "## Auskunft: die drei tiefsten Rückgänge (01.11.2024 bis 31.10.2026, ohne Filter)", ""]
    for ep in e["episoden"]:
        bots = ", ".join(f"{b} {_r(v['summe_r'])} ({v['n']})" for b, v in ep["je_bot"].items())
        gvz = "" if ep["gvz_schnitt_gold"] is None else f", GVZ bei Gold-Trades im Schnitt {_z(ep['gvz_schnitt_gold'])}"
        z.append(f"- {ep['von']} bis {ep['bis']}: von {_e(ep['hoch'])} auf {_e(ep['tief'])} ({_p(ep['pct'])}), {ep['trades']} Trades, "
                 f"Gold {_r(ep['gold_anteil_r'])}{gvz}, VIX im Schnitt {_z(ep['vix_schnitt'])}. Je Bot: {bots}.")
    g = e["ganz"]
    z += ["", "## Auskunft: ganze Zeit 01.11.2024 bis 31.10.2026 (Auswahlzeit steckt darin)", "",
          f"Ohne Filter {_e(g['ohne']['ende'])}, Rückgang {_p(g['ohne']['rueckgang_pct'])}.", "",
          "| Filter | ausgelassen | Summe R ausgelassen | Ende | Rückgang |", "|---|---|---|---|---|"]
    for f in FILTER:
        x = g[f]
        z.append(f"| {NAMEN[f]} | {x['n_aus']} | {_r(x['summe_r_aus'])} | {_e(x['ende'])} | {_p(x['rueckgang_pct'])} |")
    z += ["", "## Auskunft: umdrehen statt auslassen, bester Fall 2026", "",
          "Der ausgelassene Trade wird umgedreht genommen, mit -R minus 0,1 R. Die zweiten Kosten des Gegentrades fehlen, "
          "darum ist das der beste Fall. Kein Urteil, die Umkehr ist dreimal durchgefallen.", "",
          "| Filter | Ende umgedreht | Rückgang umgedreht | Ende ausgelassen |", "|---|---|---|---|"]
    for f in FILTER:
        x = u[f]
        z.append(f"| {NAMEN[f]} | {_e(x['umkehr_bestfall_ende'])} | {_p(x['umkehr_bestfall_rueckgang_pct'])} | {_e(x['ende'])} |")
    z += ["", "Ehrlich dazu: Die Trades sind Rückblick-Trades. V1 und seine Bots wurden an denselben Monaten ausgesucht. "
          "Darum zählt nur das Urteil an 2026. Offene Verluste, der Stop-out des Brokers und die kleinste Handelsgröße fehlen in der Rechnung.", ""]
    return "\n".join(z)


def _json(e: dict) -> dict:
    def sauber(x):
        if isinstance(x, dict):
            return {k: sauber(v) for k, v in x.items() if k not in ("res",)}
        if isinstance(x, (list, tuple)):
            return [sauber(v) for v in x]
        if isinstance(x, (np.bool_,)):
            return bool(x)
        if isinstance(x, (np.integer,)):
            return int(x)
        if isinstance(x, (np.floating, float)):
            return round(float(x), 6)
        return x
    return sauber(e)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    if not siegel_ok():
        raise SystemExit("Regeldatei nicht versiegelt oder geändert (Protokoll prüfen)")
    if ERGEBNIS.exists():
        raise SystemExit("Schon gerechnet: suche/ergebnis_v1_rueckgang.md liegt da. Ein zweiter Lauf braucht eine neue Regeldatei.")
    e = rechne(pathlib.Path(argv[0]))
    ERGEBNIS.write_text(bericht(e), encoding="utf-8")
    if "--json" in argv:
        pathlib.Path(argv[argv.index("--json") + 1]).write_text(json.dumps(_json(e), ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"bestanden": e["bestanden"], "ohne": round(e["urteil"]["ohne"]["ende"], 2),
                      **{f: round(e["urteil"][f]["ende"], 2) for f in FILTER}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
