"""TikTok-Box im Schatten: rechnet jede Stunde mit, sendet NIE eine Order.

    python -m gold.tiktok_schatten        # holt Viertelstunden-Kerzen vom Capital.com-Demokonto, rechnet, schreibt das Journal

Kirons Wunsch vom 06.11.2026: die Signal-Box der TikTok-Live-Streams nachbauen und die Vorhersage live mitlaufen lassen,
so dass sie immer in einem Trade ist. Festgelegt im Repo portfolio-manager in suche/VORAB_runde12b.yaml (Prüfsumme im
Journal dort). Keine Strategie hat einen Test bestanden: stream_box fiel 11/2024 bis 10/2026 durch (PF_R 0,96),
gross_klein_3 sah in dieser Zeit gut aus (PF_R 1,41), wurde aber erst nach dem Ansehen gewählt und fiel über 11 Jahre
durch. Der Schatten sammelt nur neue Daten ab seinem ersten Lauf. Urteil nach 40 fertigen Trades je Strategie: PF_R
mindestens 1,2 und Summe R über 0, dann Vorschlag an Kiron für ein Demokonto, nur mit seinem Ja. Der Code ruft beim
Broker nur Anmeldung und Kerzen ab und kann keine Order senden.

Strategien (wie portfolio-manager suche/runde12.py und runde12b.py):
- stream_box: SuperTrend (ATR 20 nach Wilder, Faktor 2) auf 15-Minuten-Kerzen. Jeder Richtungswechsel ist ein Signal.
  Stop an der SuperTrend-Linie, Abstand 0,5 bis 3 ATR(14). Je ein Drittel bei 1, 2, 3 R, nach TP1 Stop auf Einstand,
  das nächste Signal schließt den Rest und dreht. Die Richtung des SuperTrend ist die laufende Vorhersage.
- box_175: wie stream_box, aber Faktor 1,75. Auf echten XAUUSD-Minuten (Dukascopy 03.-05.11.2026) passt 1,75 besser zu
  den Umkehrungen der Streams (9 von 15 statt 5 von 15). Vorab festgelegt in portfolio-manager suche/VORAB_runde12c.yaml,
  dort 11/2024 bis 10/2026 durchgefallen (PF_R 0,96). Kommt laut Vorab in jedem Fall in den Schatten, weil sie die Box
  genauer nachbaut. Zählt erst ab ihrem eigenen ersten Lauf (start_je), nicht rückwirkend.
- gross_klein_3: Strukturbruch (Schluss über dem letzten Swing-Hoch, Swing-Länge 5) auf 15 Min., 1 Std. und 4 Std.
  (4 Std. ab 18:00 New York wie TradingView/OANDA). Ein 15-Min.-Signal zählt nur, wenn die 4-Std.- und die 1-Std.-Box
  in dieselbe Richtung laufen und der Kurs in der grünen Zone der 4-Std.-Box liegt (zwischen Einstieg und TP3). Stop am
  Gegen-Swing (0,5 bis 3 ATR), Drittel und Einstand wie oben, raus spätestens wenn die 4-Std.-Box endet.

Ausführung auf den 15-Min.-Kerzen (der Backtest nutzt 5-Min.-Kerzen): Einstieg zur nächsten Eröffnung, Kauf zum Ask
(Bid + Spread), Stop vor Ziel in derselben Kerze, Lücken zur Eröffnung. Kosten: Spread der Kerzen, Übernachtgebühr
6,5 % (Kauf) bzw. 2,0 % (Verkauf) im Jahr.

Dateien (nur Journal, ändern nichts an den Demo-Bots):
- journal/tiktok-schatten.json: Stand, laufende Vorhersage, offene Trades, alle fertigen Trades, Zusammenfassung
- journal/tiktok-schatten.jsonl: ein Ereignis je Zeile (neuer Trade, Trade fertig)
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STATE = "tiktok-schatten.json"
LOG = "tiktok-schatten.jsonl"
EPIC = "GOLD"
NY = "America/New_York"
SWING = 5
ST_ATR, ST_FAKTOR = 20, 2.0
ST_FAKTOR_GENAUER = 1.75                      # box_175, portfolio-manager suche/VORAB_runde12c.yaml
ZIELE, GEWICHTE = (1.0, 2.0, 3.0), (1 / 3, 1 / 3, 1 / 3)
SATZ = {1: 6.5, -1: 2.0}                     # Übernachtgebühr in % im Jahr
URTEIL_NACH, URTEIL_PF = 40, 1.2
MIN_BARS = 400                                # etwa 4 Handelstage Vorlauf für 4-Std.-Swings und ATR
CHUNK_DAYS = 10                               # weniger als 1.000 Viertelstunden-Kerzen je Abruf
STRATEGIEN = ("stream_box", "gross_klein_3", "box_175")


# --------------------------------------------------------------------------------------------------------------------
# Kerzen

@dataclass
class Basis:
    """15-Minuten-Bid-Kerzen mit Spread und Handelstag (endet 17:00 New York)."""
    t: np.ndarray            # datetime64[ns] UTC, Beginn
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    sp: np.ndarray
    tag: np.ndarray          # datetime64[D]
    ny: pd.DatetimeIndex

    def __len__(self) -> int:
        return len(self.t)


def basis(bars: pd.DataFrame, spread: pd.Series) -> Basis:
    idx = pd.DatetimeIndex(bars.index)
    nyz = idx.tz_localize("UTC").tz_convert(NY)
    ny = nyz.tz_localize(None)
    tag = (ny + pd.Timedelta(hours=7)).normalize().values.astype("datetime64[D]")
    sp = spread.reindex(idx).ffill().bfill().to_numpy(float)
    return Basis(idx.values.astype("datetime64[ns]"), bars["open"].to_numpy(float), bars["high"].to_numpy(float),
                 bars["low"].to_numpy(float), bars["close"].to_numpy(float), sp, tag, ny)


@dataclass
class Ebene:
    name: str
    ende: np.ndarray         # Ende der letzten 15-Min.-Kerze der Gruppe
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    i1: np.ndarray           # letzte 15-Min.-Kerze der Gruppe
    atr: np.ndarray = field(default=None)


def ebene(b: Basis, name: str) -> Ebene:
    t = pd.DatetimeIndex(b.t)
    if name == "15m":
        g = t.floor("15min")
    elif name == "1h":
        g = t.floor("1h")
    elif name == "4h":
        g = (b.ny + pd.Timedelta(hours=6)).floor("4h")
    else:
        raise ValueError(name)
    g = np.asarray(g.values)
    neu = np.r_[True, g[1:] != g[:-1]]
    i0 = np.flatnonzero(neu)
    i1 = np.r_[i0[1:] - 1, len(g) - 1]
    h = np.maximum.reduceat(b.h, i0)
    lo = np.minimum.reduceat(b.l, i0)
    c = b.c[i1]
    e = Ebene(name, b.t[i1] + np.timedelta64(15, "m"), h, lo, c, i1)
    e.atr = atr_wilder(h, lo, c, 14)
    return e


def atr_wilder(h, lo, c, n=14) -> np.ndarray:
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.vstack([h - lo, np.abs(h - pc), np.abs(lo - pc)]), axis=0)
    out = np.full(len(h), np.nan)
    if len(h) < n:
        return out
    out[n - 1] = tr[:n].mean()
    for i in range(n, len(h)):
        out[i] = out[i - 1] + (tr[i] - out[i - 1]) / n
    return out


# --------------------------------------------------------------------------------------------------------------------
# Signale

@dataclass
class Signal:
    k: int
    d: int
    gegen: float             # Stop-Kurs vor der Begrenzung (Gegen-Swing oder SuperTrend-Linie)


def strukturbrueche(e: Ebene, n: int = SWING) -> list[Signal]:
    h, lo, c = e.h, e.l, e.c
    ph = pl = np.nan
    ph_frei = pl_frei = False
    out = []
    for k in range(len(c)):
        i = k - n
        if i >= n:
            if h[i] > h[i - n:i].max() and h[i] >= h[i + 1:k + 1].max():
                ph, ph_frei = h[i], True
            if lo[i] < lo[i - n:i].min() and lo[i] <= lo[i + 1:k + 1].min():
                pl, pl_frei = lo[i], True
        hoch = ph_frei and c[k] > ph
        tief = pl_frei and c[k] < pl
        if hoch:
            ph_frei = False
        if tief:
            pl_frei = False
        if hoch and not tief:
            out.append(Signal(k, 1, float(pl)))
        elif tief and not hoch:
            out.append(Signal(k, -1, float(ph)))
    return out


def supertrend(h, lo, c, n: int = ST_ATR, faktor: float = ST_FAKTOR):
    a = atr_wilder(h, lo, c, n)
    hl2 = (h + lo) / 2
    unten, oben = hl2 - faktor * a, hl2 + faktor * a
    richt = np.zeros(len(c), int)
    linie = np.full(len(c), np.nan)
    fu = fo = np.nan
    d = 0
    for i in range(len(c)):
        if not np.isfinite(a[i]):
            continue
        if np.isnan(fu):
            fu, fo, d = unten[i], oben[i], 1 if c[i] >= hl2[i] else -1
        else:
            fu = max(unten[i], fu) if c[i - 1] > fu else unten[i]
            fo = min(oben[i], fo) if c[i - 1] < fo else oben[i]
            if d == 1 and c[i] < fu:
                d = -1
            elif d == -1 and c[i] > fo:
                d = 1
        richt[i] = d
        linie[i] = fu if d == 1 else fo
    return richt, linie


def st_signale(e: Ebene, faktor: float = ST_FAKTOR) -> list[Signal]:
    richt, linie = supertrend(e.h, e.l, e.c, faktor=faktor)
    return [Signal(k, int(richt[k]), float(linie[k])) for k in range(1, len(richt))
            if richt[k] != 0 and richt[k - 1] != 0 and richt[k] != richt[k - 1]]


# --------------------------------------------------------------------------------------------------------------------
# Führung auf den 15-Minuten-Kerzen

def _erster(mask: np.ndarray, ab: int) -> int:
    if ab >= len(mask):
        return -1
    k = int(np.argmax(mask[ab:]))
    return ab + k if mask[ab + k] else -1


def fuehre(b: Basis, d: int, j0: int, jf: int, einstieg: float, stop: float) -> tuple[list[dict], bool]:
    """Teile (w, px, j, grund) auf den Kerzen j0 .. jf-1, Rest zur Eröffnung von jf. Zweiter Wert: noch offen."""
    n = len(b)
    jf = min(jf, n)
    r = abs(einstieg - stop)
    if d > 0:
        lo, hi, op = b.l[j0:jf], b.h[j0:jf], b.o[j0:jf]
    else:
        lo, hi, op = (b.l + b.sp)[j0:jf], (b.h + b.sp)[j0:jf], (b.o + b.sp)[j0:jf]
    teile, rest = [], 1.0
    stop_akt, stop_ab, ziel_ab = stop, 0, 0
    for m, (zr, w) in enumerate(zip(ZIELE, GEWICHTE)):
        ziel = einstieg + d * zr * r
        s_mask = (lo <= stop_akt) if d > 0 else (hi >= stop_akt)
        z_mask = (hi >= ziel) if d > 0 else (lo <= ziel)
        ks, kz = _erster(s_mask, stop_ab), _erster(z_mask, ziel_ab)
        if ks >= 0 and (kz < 0 or ks <= kz):
            px = min(op[ks], stop_akt) if d > 0 else max(op[ks], stop_akt)
            teile.append({"w": rest, "px": float(px), "j": j0 + ks, "grund": "stop" if m == 0 else "einstand"})
            return teile, False
        if kz < 0:
            break
        px = max(op[kz], ziel) if d > 0 else min(op[kz], ziel)
        teile.append({"w": w, "px": float(px), "j": j0 + kz, "grund": f"tp{m + 1}"})
        rest -= w
        ziel_ab = kz
        if m == 0:
            stop_akt, stop_ab = einstieg, kz + 1
    if rest > 1e-9:
        if jf < n:
            px = b.o[jf] if d > 0 else b.o[jf] + b.sp[jf]
            teile.append({"w": rest, "px": float(px), "j": jf, "grund": "gegensignal"})
            return teile, False
        return teile, True
    return teile, False


def ergebnis_r(b: Basis, d: int, j0: int, einstieg: float, r: float, teile: list[dict], offen: bool) -> float:
    """R nach Spread und Übernachtgebühr. Ein offener Rest zählt zum letzten Schluss (nur zur Anzeige)."""
    rate = SATZ[d] / 100.0
    rest = 1.0 - sum(t["w"] for t in teile)
    alle = list(teile)
    if offen and rest > 1e-9:
        n = len(b) - 1
        alle.append({"w": rest, "px": float(b.c[n] if d > 0 else b.c[n] + b.sp[n]), "j": n})
    tot = 0.0
    for t in alle:
        naechte = max(int((b.tag[t["j"]] - b.tag[j0]).astype(int)), 0)
        tot += t["w"] * (d * (t["px"] - einstieg) / r - rate / 365.0 * naechte * einstieg / r)
    return float(tot)


def _zeit(b: Basis, j: int) -> str:
    return str(pd.Timestamp(b.t[min(j, len(b) - 1)]))


def signalbox(b: Basis, e: Ebene, sig: list[Signal], erlaubt=None, zwang=None) -> list[dict]:
    n = len(b)
    eintritt = [int(e.i1[s.k]) + 1 for s in sig]
    naechstes_gegen = [n] * len(sig)
    letzt = {1: n, -1: n}
    for q in range(len(sig) - 1, -1, -1):
        naechstes_gegen[q] = letzt[-sig[q].d]
        letzt[sig[q].d] = eintritt[q]
    out: list[dict] = []
    offen_bis, offen_d = -1, 0
    for q, s in enumerate(sig):
        j0 = eintritt[q]
        a = e.atr[s.k]
        if j0 >= n or not np.isfinite(a):
            continue
        if j0 <= offen_bis and s.d == offen_d:
            continue
        if erlaubt is not None and not erlaubt(s):
            continue
        einstieg = float(b.o[j0] + b.sp[j0] if s.d > 0 else b.o[j0])
        roh = s.d * (einstieg - s.gegen) if np.isfinite(s.gegen) else 0.0
        dist = float(np.clip(roh, 0.5 * a, 3.0 * a))
        stop = einstieg - s.d * dist
        jf = naechstes_gegen[q] if zwang is None else min(naechstes_gegen[q], zwang(s))
        if jf <= j0:
            continue
        teile, offen = fuehre(b, s.d, j0, jf, einstieg, stop)
        res = ergebnis_r(b, s.d, j0, einstieg, dist, teile, offen)
        letzt_j = max([t["j"] for t in teile], default=n - 1) if not offen else n - 1
        grund = "offen" if offen else max(teile, key=lambda t: t["j"])["grund"]
        ende = _zeit(b, letzt_j) if grund == "gegensignal" else str(pd.Timestamp(b.t[letzt_j]) + pd.Timedelta("15min"))
        out.append({"signal": str(pd.Timestamp(e.ende[s.k])), "einstieg_zeit": _zeit(b, j0), "richtung": s.d,
                    "einstieg": round(einstieg, 2), "stop": round(stop, 2),
                    "tp1": round(einstieg + s.d * dist, 2), "tp2": round(einstieg + s.d * 2 * dist, 2),
                    "tp3": round(einstieg + s.d * 3 * dist, 2), "r_usd": round(dist, 2),
                    "teile": [{"grund": t["grund"], "px": round(t["px"], 2), "zeit": _zeit(b, t["j"]),
                               "anteil": round(t["w"], 3)} for t in teile],
                    "ergebnis_r": round(res, 3), "grund": grund, "ende": None if offen else ende, "offen": offen,
                    "_j0": j0, "_ende_j": letzt_j if grund != "gegensignal" else letzt_j - 1})
        offen_bis, offen_d = (n if offen else (letzt_j - 1 if grund == "gegensignal" else letzt_j)), s.d
    return out


def gross_klein(b: Basis, klein: Ebene, sig_k: list[Signal], gross: list[dict], mitte: list[dict]) -> list[dict]:
    def aktiv(trs: list[dict], t: pd.Timestamp, d: int) -> dict | None:
        for tr in trs:
            if tr["richtung"] == d and pd.Timestamp(tr["signal"]) <= t and (
                    tr["offen"] or t < pd.Timestamp(tr["ende"])):
                return tr
        return None

    def erlaubt(s: Signal) -> bool:
        t = pd.Timestamp(klein.ende[s.k])
        g = aktiv(gross, t, s.d)
        if g is None or aktiv(mitte, t, s.d) is None:
            return False
        kurs = klein.c[s.k]
        return (g["einstieg"] <= kurs < g["tp3"]) if s.d > 0 else (g["tp3"] < kurs <= g["einstieg"])

    def zwang(s: Signal) -> int:
        g = aktiv(gross, pd.Timestamp(klein.ende[s.k]), s.d)
        if g is None or g["offen"]:
            return len(b)
        return int(np.searchsorted(b.t, np.datetime64(pd.Timestamp(g["ende"]))))

    return signalbox(b, klein, sig_k, erlaubt=erlaubt, zwang=zwang)


def alle(b: Basis) -> tuple[dict[str, list[dict]], dict]:
    m15, h1, h4 = ebene(b, "15m"), ebene(b, "1h"), ebene(b, "4h")
    out = {"stream_box": signalbox(b, m15, st_signale(m15))}
    box4 = signalbox(b, h4, strukturbrueche(h4))
    box1 = signalbox(b, h1, strukturbrueche(h1))
    out["gross_klein_3"] = gross_klein(b, m15, strukturbrueche(m15), box4, box1)
    out["box_175"] = signalbox(b, m15, st_signale(m15, ST_FAKTOR_GENAUER))

    def richtung(faktor: float) -> dict:
        richt, linie = supertrend(m15.h, m15.l, m15.c, faktor=faktor)
        return {"richtung": int(richt[-1]), "linie": round(float(linie[-1]), 2) if np.isfinite(linie[-1]) else None,
                "gerade_gedreht": bool(len(richt) > 1 and richt[-2] != 0 and richt[-1] != richt[-2])}

    vorhersage = {**richtung(ST_FAKTOR), "kerze": str(pd.Timestamp(m15.ende[-1])), "kurs": round(float(b.c[-1]), 2),
                  "genauer_175": richtung(ST_FAKTOR_GENAUER)}
    return out, vorhersage


# --------------------------------------------------------------------------------------------------------------------
# Stand und Journal

def pf(r) -> float | None:
    r = np.asarray(r, float)
    if len(r) == 0:
        return None
    g, v = r[r > 0].sum(), -r[r < 0].sum()
    return None if v == 0 else round(float(g / v), 3)


def zusammenfassung(fertig: list[dict]) -> dict:
    r = [t["ergebnis_r"] for t in fertig]
    n = len(r)
    urteil = f"läuft ({n} von {URTEIL_NACH} Trades)"
    if n >= URTEIL_NACH:
        erste = r[:URTEIL_NACH]
        ok = (pf(erste) or 0) >= URTEIL_PF and sum(erste) > 0
        urteil = "bestanden, Vorschlag an Kiron" if ok else "durchgefallen, Schatten endet"
    return {"trades": n, "pf_r": pf(r), "summe_r": round(float(sum(r)), 2),
            "trefferquote": round(sum(x > 0 for x in r) / n, 3) if n else None, "urteil": urteil}


def _sauber(t: dict) -> dict:
    return {k: v for k, v in t.items() if not k.startswith("_")}


def step(bars: pd.DataFrame, spread: pd.Series, state: dict, now: datetime) -> tuple[dict, list[dict]]:
    """Rechnet alles aus den Kerzen neu und übernimmt nur Trades mit Einstieg ab dem Start des Schattens."""
    b = basis(bars, spread)
    st = dict(state)
    jetzt_start = str(pd.Timestamp(b.t[-1]) + pd.Timedelta("15min"))
    st.setdefault("start", jetzt_start)
    # Jede Strategie zählt ab ihrem eigenen ersten Lauf, eine später dazugekommene (box_175) nicht rückwirkend.
    alt_fertig = state.get("fertig")
    start_je = dict(st.get("start_je") or {})
    for name in STRATEGIEN:
        if name not in start_je:
            start_je[name] = st["start"] if alt_fertig is None or name in alt_fertig else jetzt_start
    st["start_je"] = start_je
    st["fertig"] = dict(st.get("fertig") or {})
    trades, vorhersage = alle(b)
    events: list[dict] = []
    offen_neu = {}
    for name in STRATEGIEN:
        start = pd.Timestamp(start_je[name])
        fertig = st["fertig"].setdefault(name, [])
        letzte = pd.Timestamp(fertig[-1]["einstieg_zeit"]) if fertig else None
        alt_offen = (state.get("offen") or {}).get(name)
        for t in trades[name]:
            tin = pd.Timestamp(t["einstieg_zeit"])
            if tin < start or (letzte is not None and tin <= letzte):
                continue
            if t["offen"]:
                offen_neu[name] = _sauber(t)
                if not alt_offen or alt_offen.get("einstieg_zeit") != t["einstieg_zeit"]:
                    events.append({"zeit": now.isoformat(timespec="seconds"), "strategie": name, "ereignis": "einstieg",
                                   **{k: t[k] for k in ("einstieg_zeit", "richtung", "einstieg", "stop", "tp1", "tp2",
                                                        "tp3")}})
            else:
                fertig.append(_sauber(t))
                letzte = tin
                events.append({"zeit": now.isoformat(timespec="seconds"), "strategie": name, "ereignis": "fertig",
                               **{k: t[k] for k in ("einstieg_zeit", "richtung", "einstieg", "grund", "ergebnis_r")}})
    st["offen"] = offen_neu
    def text(v: dict) -> str:
        seite = "Kauf" if v["richtung"] > 0 else "Verkauf"
        return f"Gerade auf {seite} gedreht, neuer Trade zur nächsten Eröffnung" if v["gerade_gedreht"] else seite

    st["vorhersage"] = {**vorhersage, "text": text(vorhersage) + " (SuperTrend 20/2 auf 15 Min., die Richtung der "
                        "Stream-Box)", "text_175": text(vorhersage["genauer_175"]) + " (SuperTrend 20/1,75, genauerer "
                        "Nachbau)"}
    st["zusammenfassung"] = {name: zusammenfassung(st["fertig"][name]) for name in STRATEGIEN}
    st["stand"] = now.isoformat(timespec="seconds")
    st["letzte_kerze"] = str(pd.Timestamp(b.t[-1]))
    st["hinweis"] = ("Nur Schatten, keine Order. Keine der drei Strategien hat einen Backtest bestanden (portfolio-"
                     "manager suche/VORAB_runde12b.yaml und VORAB_runde12c.yaml). Urteil nach 40 fertigen Trades je "
                     "Strategie.")
    return st, events


def fetch_candles(client, epic: str = EPIC, chunks: int = 1) -> list[dict]:
    """Die letzten 1.000 Viertelstunden-Kerzen und davor `chunks` Blöcke zu je 10 Tagen. Nur lesende Abrufe."""
    out = client.prices(epic, "MINUTE_15", 1000)
    for _ in range(chunks):
        if not out:
            break
        first = min(pd.Timestamp(p["snapshotTimeUTC"]) for p in out)
        frm = first - pd.Timedelta(days=CHUNK_DAYS)
        older = client._get(f"/prices/{epic}", resolution="MINUTE_15", max=1000,
                            **{"from": frm.strftime("%Y-%m-%dT%H:%M:%S"),
                               "to": first.strftime("%Y-%m-%dT%H:%M:%S")}).get("prices", [])
        out = older + out
    return out


def main(argv: list[str]) -> int:
    from gold.bot.capital import CapitalClient
    from gold.bot.rules import bars_from_prices
    from gold.bot.runner import CRED_KEYS, clean_credentials

    creds = clean_credentials({k: os.environ.get(k, "") for k in CRED_KEYS})
    if not all(creds):
        print("Keine Capital.com-Zugangsdaten, TikTok-Schatten übersprungen")
        return 0
    journal = ROOT / "journal"
    path = journal / STATE
    state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    now = datetime.now(timezone.utc)
    client = CapitalClient(*creds, environment="demo")
    client.login()
    try:
        bars, spread = bars_from_prices(fetch_candles(client), now, "15min")
    finally:
        try:
            client.logout()
        except Exception:               # noqa: BLE001 - Abmelden ist nur Ordnung
            pass
    if len(bars) < MIN_BARS:
        print(f"Nur {len(bars)} Viertelstunden-Kerzen, der Schatten braucht {MIN_BARS}; nichts geschrieben")
        return 0
    if state.get("letzte_kerze") and pd.Timestamp(state["letzte_kerze"]) >= bars.index[-1]:
        print(f"Kerze {bars.index[-1]} ist schon verarbeitet")
        return 0
    st, events = step(bars, spread, state, now)
    journal.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if events:
        with open(journal / LOG, "a", encoding="utf-8") as fh:
            for ev in events:
                fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
    print(json.dumps({"vorhersage": st["vorhersage"], "zusammenfassung": st["zusammenfassung"], "ereignisse": events},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
