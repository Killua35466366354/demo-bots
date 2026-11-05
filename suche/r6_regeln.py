"""Regeln der drei Demo-Bots aus Runde 6, ohne Netz (rein rechnend, getestet gegen den Backtest).

Jede Funktion bekommt nur FERTIGE 15-Minuten-Bid-Kerzen (Index = Kerzenbeginn UTC ohne Zeitzone) und den Zeitpunkt des
Laufs. Sie spielt den heutigen Tag genau so durch, wie der Backtest ihn gerechnet hätte (runde4b.s_vortag_stop_oco,
runde4b.s_london_stunde, runde4.noise_band_trades, Bedingungen aus runde6), und sagt, was der Bot JETZT tun soll.
Was der Backtest früher am Tag getan hätte und der Bot verpasst hat, wird nie nachgeholt.

Platz 1, Vortageshoch/-tief mit Stop-Orders (USD/JPY), bestanden:
  Handelstag 18 bis 17 Uhr New York. Stop-Orders am Hoch und Tief des Vortags (Bid), Stop 0,5 x ATR(14) der
  Viertelstunden-Kerzen beim Legen der Orders hinter der Marke (seit 04.11.2026, Kirons Wahl nach der Stop-Wahl, vorher
  10 % der Vortagesspanne; VORAB_r6_demo.yaml nachtrag_vortag_stop_2026_11_04), Ziel 25 % der Vortagesspanne davor, raus
  zum Tagesende. Bedingung "uhrzeit=hoch": Die erste Kerze des Tages, die über das
  Vortageshoch oder unter das Vortagestief geht, beginnt um 4:30 New York oder später (Grenze 615 Minuten nach 18 Uhr,
  aus den Lernjahren). Bricht der Kurs schon vorher aus, gibt es an dem Tag keinen Trade. Lagen beim Ausbruch noch
  keine Stop-Orders (Lauf ausgefallen), holt der Bot ihn bis 65 Minuten danach per Marktorder nach, solange Stop und
  Ziel noch nicht erreicht sind (seit 04.11.2026, Kirons Wunsch; vt_nachholen).
Platz 2, London-Stunde nur Long (GBP/USD), knapp nicht bestanden, auf Kirons Wunsch:
  Stundenkerzen London, Bereich = Hoch/Tief der Stunden 4 bis 8 Uhr (fünf Kerzen). Ab der 9-Uhr-Kerze: die erste Kerze,
  die unter dem Bereichshoch eröffnet, darüber schließt und deren Größe zwischen 1 und 2,5 x ATR(14) der Stunde davor liegt
  -> Long zur Eröffnung der nächsten Stunde, Stop am Bereichstief, Ziel 1,5 x Risiko, raus um 17 Uhr London. Bedingung
  "schwankung=niedrig": ATR(14)/ATR(100) der Tageskerzen bis gestern höchstens 0,8765.
Platz 3, Noise-Band (USD/JPY), knapp nicht bestanden, auf Kirons Wunsch:
  Sitzung 8 bis 17 Uhr London. Band = max/min(Eröffnung, Vortagesschluss) mal (1 +/- mittlere Bewegung bis zu dieser
  Kerze in den letzten 14 Tagen). Prüfung zum Schluss jeder halben Stunde: Schluss über dem Band long, darunter short,
  Einstieg zur Eröffnung der nächsten Kerze; raus, wenn der Schluss wieder unter max(Band, VWAP) bzw. über
  min(Band, VWAP) liegt, sonst zum Sitzungsschluss. Bedingung "schwankung=niedrig" mit Grenze 0,8658.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from suche.runde4b import atr_rma

NY, LON = "America/New_York", "Europe/London"
VERSCH = pd.Timedelta(hours=6)          # New York + 6 Stunden: 18:00 wird 0:00 des Handelstags (runde4b TAG24)

VORTAG = {"stop_anteil": 0.10, "ziel_anteil": 0.25, "uhrzeit_ueber": 615, "tag_ende": 23 * 60, "min_kerzen": 90,
          "stop_atr": 0.5, "atr_n": 14,       # stop_anteil gilt nicht mehr (bis 04.11.2026), nur noch stop_atr
          "nachholen_min": 65}                # verpasster Ausbruch: Marktorder bis 65 Minuten nach Beginn der Kerze
LONDON = {"bereich_von": 4, "bereich_bis": 8, "signal_ab": 9, "atr_n": 14, "atr_min": 1.0, "atr_max": 2.5, "ziel_r": 1.5,
          "sitzung_von": 4 * 60, "sitzung_bis": 17 * 60, "schwankung_max": 0.8764623991321253}
NOISE = {"vm": 1.0, "sitzung_von": 8 * 60, "sitzung_bis": 17 * 60, "kerzen": 36, "tage": 14,
         "schwankung_max": 0.8658283429128152}
SPAET = pd.Timedelta(minutes=20)       # ein Einstieg gilt nur in den ersten 20 Minuten nach dem Kerzenschluss


def _utc(t) -> pd.Timestamp:
    t = pd.Timestamp(t)
    return t.tz_convert("UTC").tz_localize(None) if t.tzinfo else t


def ortszeit(idx, tz: str) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(idx)
    return (idx if idx.tz is not None else idx.tz_localize("UTC")).tz_convert(tz).tz_localize(None)


# ---------------------------------------------------------------------------------------------------------------------
# Schwankung wie runde6.tagesmerkmale (Handelstag endet 17 Uhr New York), aus Stundenkerzen

def tageswerte(stunden: pd.DataFrame, tag) -> dict | None:
    """ATR(14), ATR(100) und Schwankung = ATR(14)/ATR(100) der Tageskerzen bis zum letzten fertigen Handelstag vor `tag`
    (Datum des Handelstags, der um 17 Uhr New York endet). stunden: Bid-Stundenkerzen, Index Beginn UTC. Wie
    runde6.tagesmerkmale(...).shift(1); ein Tag zählt ab 5 Stundenkerzen (dort: 20 Viertelstunden)."""
    if not len(stunden):
        return None
    lab = (ortszeit(stunden.index, NY) + pd.Timedelta(hours=7)).normalize()
    g = stunden.groupby(lab)
    d = pd.DataFrame({"h": g["high"].max(), "l": g["low"].min(), "c": g["close"].last(), "n": g["close"].size()})
    d = d[(d["n"] >= 5) & (d.index < pd.Timestamp(tag))]
    if len(d) < 101:
        return None
    pc = d["c"].shift(1)
    tr = np.maximum(d["h"] - d["l"], np.maximum((d["h"] - pc).abs(), (d["l"] - pc).abs()))
    a14, a100 = tr.rolling(14).mean().iloc[-1], tr.rolling(100).mean().iloc[-1]
    if pd.isna(a14) or pd.isna(a100) or not a100 > 0:
        return None
    return {"atr14": float(a14), "atr100": float(a100), "schwankung": float(a14 / a100), "bis": str(d.index[-1].date())}


def schwankung_fuer(stunden: pd.DataFrame, tag) -> float | None:
    w = tageswerte(stunden, tag)
    return None if w is None else w["schwankung"]


def handelstag_ny17(t) -> pd.Timestamp:
    """Datum des Handelstags (endet 17 Uhr New York), zu dem der Zeitpunkt t gehört."""
    return (ortszeit([_utc(t)], NY)[0] + pd.Timedelta(hours=7)).normalize()


# ---------------------------------------------------------------------------------------------------------------------
# Platz 1: Vortageshoch/-tief mit Stop-Orders

def vt_tage(bars: pd.DataFrame) -> dict:
    """Handelstage (18 bis 17 Uhr New York) -> Kerzen des Tages; nur Mo bis Fr, nur Kerzen vor 17 Uhr."""
    v = ortszeit(bars.index, NY) + VERSCH
    tod = v.hour * 60 + v.minute
    drin = (tod < VORTAG["tag_ende"]) & (v.weekday < 5)
    out: dict = {}
    for d, g in bars[drin].groupby(v[drin].normalize()):
        out[d] = g
    return out


def vt_vortag(tage: dict, tag: pd.Timestamp) -> tuple[float, float] | None:
    """Hoch und Tief (Bid) des letzten vollständigen Handelstags vor `tag` (wie runde4b: mindestens 90 Kerzen, erste
    Kerze um 18 Uhr New York)."""
    for d in sorted((d for d in tage if d < tag), reverse=True):
        g = tage[d]
        erste = ortszeit([g.index[0]], NY)[0] + VERSCH
        if len(g) >= VORTAG["min_kerzen"] and erste.hour == 0 and erste.minute == 0:
            return float(g["high"].max()), float(g["low"].min())
    return None


def vt_stop_abstand(bars: pd.DataFrame, faktor: float | None = None) -> tuple[float, float] | None:
    """Stop-Abstand der Vortags-Regel seit 04.11.2026: stop_atr x ATR(14) nach Wilder der fertigen 15-Minuten-Bid-Kerzen,
    Wert der letzten fertigen Kerze (beim Legen der Stop-Orders). Rückgabe (Abstand, ATR) oder None (zu wenig Kerzen).
    faktor: nur für den Mess-Bot mit 1 x ATR (suche/VORAB_messbots.yaml); sonst VORTAG["stop_atr"]."""
    if len(bars) < 5 * VORTAG["atr_n"]:
        return None
    a = atr_rma(bars["high"].to_numpy(float), bars["low"].to_numpy(float), bars["close"].to_numpy(float),
                VORTAG["atr_n"])[-1]
    if not (np.isfinite(a) and a > 0):
        return None
    return (VORTAG["stop_atr"] if faktor is None else float(faktor)) * float(a), float(a)


def vt_nachholen(bars: pd.DataFrame, tag: pd.Timestamp, t_aus: pd.Timestamp, d: int, ph: float, pl: float,
                 jetzt: pd.Timestamp, stop_atr: float | None = None) -> dict:
    """Kirons Wunsch vom 04.11.2026 13:53 UTC ("wenn du einen verpasst ... dann nimm den halt einfach ... zu spät"):
    Lagen beim Ausbruch noch keine Stop-Orders (Lauf ausgefallen oder zu spät), steigt der Bot per Marktorder nach,
    höchstens VORTAG["nachholen_min"] Minuten nach Beginn der Ausbruchskerze und nur, solange der Trade nach der Regel
    noch liefe: Ziel noch nicht erreicht, Stop noch nicht getroffen. Stop und Ziel sind dieselben Kurse wie bei den
    Stop-Orders (ATR wie beim Legen um 4:30 New York). VORAB_r6_demo.yaml nachtrag_vortag_nachholen_2026_11_04."""
    out = {"action": "none", "why": []}
    spaet = (jetzt - t_aus).total_seconds() / 60
    if spaet > VORTAG["nachholen_min"]:
        out["why"].append(f"zu spät zum Nachholen ({spaet:.0f} Minuten nach Beginn der Ausbruchskerze)")
        return out
    v = ortszeit(bars.index, NY) + VERSCH
    ab = VORTAG["uhrzeit_ueber"] + 15
    heute_ab = (v.normalize() == tag) & (np.asarray(v.hour * 60 + v.minute) >= ab)
    cut = int(np.argmax(heute_ab)) if heute_ab.any() else len(bars)
    sa = vt_stop_abstand(bars.iloc[:cut], stop_atr)
    if sa is None:
        out["why"].append("ATR der Viertelstunden unbekannt (zu wenig Kerzen)")
        return out
    spanne = ph - pl
    marke = ph if d > 0 else pl
    stop, ziel = marke - d * sa[0], marke + d * VORTAG["ziel_anteil"] * spanne
    ab_aus = bars.loc[t_aus:]
    danach = ab_aus.iloc[1:]
    if (ab_aus["high"].max() >= ziel) if d > 0 else (ab_aus["low"].min() <= ziel):
        out["why"].append("Ziel schon erreicht")
        return out
    stop_weg = (danach["low"].min() <= stop) if d > 0 else (danach["high"].max() >= stop)
    if bool(stop_weg) or (ab_aus["close"].iloc[0] - stop) * d <= 0:
        out["why"].append("Stop schon getroffen")
        return out
    out.update(action="nachholen", side=d, marke=marke, stop=stop, ziel=ziel, ph=ph, pl=pl, spanne=spanne,
               stop_abstand=sa[0], atr15=sa[1], ausbruch_kerze=str(t_aus), verspaetung_min=round(spaet))
    return out


def vt_entscheide(bars: pd.DataFrame, jetzt, zustand: dict) -> dict:
    """Platz 1. zustand: {"open": ..., "orders": ..., "tag_erledigt": "YYYY-MM-DD", "stop_atr": nur beim Mess-Bot}.
    action: none | orders (Stop-Orders legen) | cancel (offene Orders löschen) | close (Position schließen)."""
    jetzt = _utc(jetzt)
    v = ortszeit([jetzt], NY)[0] + VERSCH
    tag = v.normalize()
    minute = v.hour * 60 + v.minute
    out = {"action": "none", "tag": str(tag.date()), "why": []}
    op, orders = zustand.get("open"), zustand.get("orders")
    if op:
        if str(op.get("tag")) != out["tag"] or minute >= VORTAG["tag_ende"] - 15:
            out.update(action="close", reason="zeit", why=["Tagesende (16:45 New York)"])
        else:
            out["why"].append("Position offen")
        return out
    if orders:
        if str(orders.get("tag")) != out["tag"] or minute >= VORTAG["tag_ende"] - 30:
            out.update(action="cancel", why=["Einstiegszeit vorbei (16:30 New York)"])
        else:
            out["why"].append("Stop-Orders liegen")
        return out
    if v.weekday() >= 5:
        out["why"].append("Wochenende")
        return out
    if zustand.get("tag_erledigt") == out["tag"]:
        out["why"].append("heute erledigt")
        return out
    ab = VORTAG["uhrzeit_ueber"] + 15                  # erste erlaubte Kerze beginnt 630 Minuten nach 18 Uhr
    if minute < ab:
        out["why"].append("wartet bis 4:30 New York")
        return out
    if minute >= VORTAG["tag_ende"] - 30:
        out.update(erledigt=True, why=["nach 16:30 New York, heute nichts mehr"])
        return out
    tage = vt_tage(bars)
    vt = vt_vortag(tage, tag)
    if vt is None:
        out.update(erledigt=True, why=["Vortag unvollständig"])
        return out
    ph, pl = vt
    spanne = ph - pl
    if not spanne > 0:
        out.update(erledigt=True, why=["Vortagesspanne 0"])
        return out
    heute = tage.get(tag)
    if heute is not None and len(heute):
        v_h = ortszeit(heute.index, NY) + VERSCH
        for (t, k), vh in zip(heute.iterrows(), v_h):
            hoch, tief = k["high"] > ph, k["low"] < pl
            if not (hoch or tief):
                continue
            beginn = vh.hour * 60 + vh.minute
            ny = ortszeit([t], NY)[0]
            if hoch and tief:
                out.update(erledigt=True, why=["eine Kerze ging über Hoch und unter Tief: heute kein Trade"])
            elif beginn <= VORTAG["uhrzeit_ueber"]:
                out.update(erledigt=True, why=[f"schon um {ny:%H:%M} New York ausgebrochen (vor 4:30): heute kein Trade"])
            else:
                n = vt_nachholen(bars, tag, t, 1 if hoch else -1, ph, pl, jetzt, zustand.get("stop_atr"))
                if n["action"] == "nachholen":
                    out.update(n, why=[f"Ausbruch um {ny:%H:%M} New York verpasst, wird nachgeholt"])
                else:
                    out.update(erledigt=True, why=[f"Ausbruch um {ny:%H:%M} New York verpasst"] + n["why"])
            return out
    sa = vt_stop_abstand(bars, zustand.get("stop_atr"))
    if sa is None:
        out["why"].append("ATR der Viertelstunden unbekannt (zu wenig Kerzen)")
        return out
    s_a, z_a = sa[0], VORTAG["ziel_anteil"] * spanne
    bis = (pd.Timestamp(tag) + pd.Timedelta(minutes=VORTAG["tag_ende"] - 30) - VERSCH).tz_localize(NY)
    out.update(action="orders", ph=ph, pl=pl, spanne=spanne, stop_abstand=s_a, atr15=sa[1],
               long={"marke": ph, "stop": ph - s_a, "ziel": ph + z_a},
               short={"marke": pl, "stop": pl + s_a, "ziel": pl - z_a},
               gueltig_bis_utc=str(bis.tz_convert("UTC").tz_localize(None)),
               why=[f"kein Ausbruch bis jetzt, Stop-Orders an {ph} und {pl}"])
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Platz 2: London-Stunde nur Long

def stunden_atr_vor(stunden: pd.DataFrame) -> pd.Series:
    """ATR(14) nach Wilder der Stundenkerzen, je Stunde der Wert der Stunde davor (wie runde4b.s_london_stunde)."""
    if not len(stunden):
        return pd.Series(dtype=float)
    a = atr_rma(stunden["high"].to_numpy(), stunden["low"].to_numpy(), stunden["close"].to_numpy(), LONDON["atr_n"])
    return pd.Series(np.r_[np.nan, a[:-1]], index=stunden.index)


def ld_entscheide(bars: pd.DataFrame, stunden: pd.DataFrame, jetzt, zustand: dict, schwankung: float | None) -> dict:
    """Platz 2. bars: fertige 15-Minuten-Kerzen (mindestens ab 4 Uhr London heute). stunden: fertige Stundenkerzen (für
    die ATR). action: none | open | close."""
    jetzt = _utc(jetzt)
    lo_ = ortszeit([jetzt], LON)[0]
    tag = lo_.normalize()
    minute = lo_.hour * 60 + lo_.minute
    out = {"action": "none", "tag": str(tag.date()), "why": []}
    op = zustand.get("open")
    if op:
        if str(op.get("tag")) != out["tag"] or minute >= LONDON["sitzung_bis"]:
            out.update(action="close", reason="zeit", why=["17 Uhr London"])
        else:
            out["why"].append("Position offen")
        return out
    if lo_.weekday() >= 5:
        out["why"].append("Wochenende")
        return out
    if zustand.get("tag_erledigt") == out["tag"]:
        out["why"].append("heute erledigt")
        return out
    if minute < (LONDON["signal_ab"] + 1) * 60:
        out["why"].append("wartet bis 10 Uhr London (erste Signalkerze 9 bis 10 Uhr)")
        return out
    if minute >= LONDON["sitzung_bis"] - 60 + 16:
        out.update(erledigt=True, why=["nach 16 Uhr London kein Einstieg mehr"])
        return out
    if schwankung is None:
        out["why"].append("Schwankung unbekannt (zu wenig Tageskerzen)")
        return out
    if schwankung > LONDON["schwankung_max"]:
        out.update(erledigt=True, why=[f"Markt nicht ruhiger als sonst (Schwankung {schwankung:.3f} > 0,876): heute kein Trade"])
        return out
    lok = ortszeit(bars.index, LON)
    heute = bars[(lok.normalize() == tag) & (lok.hour * 60 + lok.minute >= LONDON["sitzung_von"])
                 & (lok.hour * 60 + lok.minute < LONDON["sitzung_bis"])]
    if not len(heute):
        out["why"].append("keine Kerzen heute")
        return out
    hl = ortszeit(heute.index, LON)
    st = heute.groupby(hl.hour).agg(o=("open", "first"), h=("high", "max"), l=("low", "min"), c=("close", "last"),
                                    n=("close", "size"), t0=("open", lambda s: s.index[0]))
    ber = st.loc[[h for h in range(LONDON["bereich_von"], LONDON["bereich_bis"] + 1) if h in st.index]]
    if len(ber) != LONDON["bereich_bis"] - LONDON["bereich_von"] + 1:
        out.update(erledigt=True, why=["Bereich 4 bis 9 Uhr unvollständig"])
        return out
    hi, lo = float(ber["h"].max()), float(ber["l"].min())
    atr_vor = stunden_atr_vor(stunden)
    aktuelle = lo_.hour                                # die Stunde, die gerade begonnen hat
    for h, s in st.iterrows():
        if h < LONDON["signal_ab"] or h >= aktuelle or h >= LONDON["sitzung_bis"] // 60 - 1:
            continue
        if s["n"] < 4:                                 # Stunde unvollständig: noch nicht fertig
            continue
        if not (s["o"] < hi < s["c"]):
            continue
        a = atr_vor.get(pd.Timestamp(s["t0"]).floor("60min"), np.nan)
        if not (pd.notna(a) and LONDON["atr_min"] * a <= s["h"] - s["l"] <= LONDON["atr_max"] * a):
            continue
        if h + 1 != aktuelle or minute - aktuelle * 60 >= SPAET.seconds // 60:
            out.update(erledigt=True, why=[f"Signal der {h}-Uhr-Kerze verpasst"])
            return out
        out.update(action="open", side=1, signal_bar=str(s["t0"]), hoch=hi, tief=lo, stop_level=lo,
                   ziel_r=LONDON["ziel_r"], erledigt=True,
                   why=[(f"{h}-Uhr-Kerze eröffnet unter {hi} und schließt darüber, Größe {s['h'] - s['l']:.5f} "
                         f"bei ATR {a:.5f}: Long")])
        return out
    out["why"].append("noch kein Signal")
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Platz 3: Noise-Band

def nb_sitzungen(bars: pd.DataFrame) -> dict:
    """Sitzungstage 8 bis 17 Uhr London -> Kerzen (nur Mo bis Fr)."""
    lok = ortszeit(bars.index, LON)
    tod = lok.hour * 60 + lok.minute
    drin = (tod >= NOISE["sitzung_von"]) & (tod < NOISE["sitzung_bis"]) & (lok.weekday < 5)
    return {d: g for d, g in bars[drin].groupby(lok[drin].normalize())}


def nb_band(tage: dict, tag: pd.Timestamp) -> dict | None:
    """Band und Vortagesschluss für `tag` aus den letzten 14 vollständigen Sitzungen davor (wie runde4.noise_band_trades:
    nur Tage mit allen 36 Kerzen ab 8 Uhr)."""
    voll = []
    for d in sorted(d for d in tage if d < tag):
        g = tage[d]
        erste = ortszeit([g.index[0]], LON)[0]
        if len(g) == NOISE["kerzen"] and erste.hour * 60 + erste.minute == NOISE["sitzung_von"]:
            voll.append(g)
    if len(voll) < NOISE["tage"]:
        return None
    bew = [np.abs(g["close"].to_numpy() / g["open"].iloc[0] - 1) for g in voll[-NOISE["tage"]:]]
    return {"sig": np.mean(bew, axis=0), "vortag_schluss": float(voll[-1]["close"].iloc[-1])}


def nb_ablauf(heute: pd.DataFrame, band: dict) -> list[dict]:
    """Was der Backtest heute bis jetzt getan hätte: Liste von {k, aktion: long/short/raus, zeit (Einstieg/Ausstieg =
    Eröffnung der Kerze k+1)}; dazu die Linien. heute: fertige Kerzen ab 8 Uhr London."""
    if not len(heute):
        return []
    o0 = float(heute["open"].iloc[0])
    sig = band["sig"]
    ub = max(o0, band["vortag_schluss"]) * (1 + NOISE["vm"] * sig)
    lb = min(o0, band["vortag_schluss"]) * (1 - NOISE["vm"] * sig)
    c, h, low = heute["close"].to_numpy(), heute["high"].to_numpy(), heute["low"].to_numpy()
    vw = np.cumsum((h + low + c) / 3) / np.arange(1, len(heute) + 1)
    out, pos = [], 0
    for k in range(1, min(len(heute), NOISE["kerzen"] - 1), 2):
        if pos == 0:
            if c[k] > ub[k]:
                pos = 1
            elif c[k] < lb[k]:
                pos = -1
            if pos:
                out.append({"k": k, "aktion": "long" if pos > 0 else "short", "zeit": heute.index[k] + pd.Timedelta(minutes=15),
                            "schluss": float(c[k]), "oben": float(ub[k]), "unten": float(lb[k]), "vwap": float(vw[k])})
        else:
            raus = c[k] < max(ub[k], vw[k]) if pos == 1 else c[k] > min(lb[k], vw[k])
            if raus:
                out.append({"k": k, "aktion": "raus", "zeit": heute.index[k] + pd.Timedelta(minutes=15),
                            "schluss": float(c[k]), "oben": float(ub[k]), "unten": float(lb[k]), "vwap": float(vw[k])})
                pos = 0
    return out


def nb_entscheide(bars: pd.DataFrame, jetzt, zustand: dict, schwankung: float | None, band: dict | None = None) -> dict:
    """Platz 3. action: none | open (side) | close. Mehrere Trades am Tag möglich. band: schon gerechnetes Band für heute
    (nb_band), sonst aus `bars` (dann müssen sie mindestens 14 vollständige Sitzungen zurückreichen)."""
    jetzt = _utc(jetzt)
    lo_ = ortszeit([jetzt], LON)[0]
    tag = lo_.normalize()
    minute = lo_.hour * 60 + lo_.minute
    out = {"action": "none", "tag": str(tag.date()), "why": []}
    op = zustand.get("open")
    if op and (str(op.get("tag")) != out["tag"] or minute >= NOISE["sitzung_bis"]):
        out.update(action="close", reason="zeit", why=["Sitzungsschluss 17 Uhr London"])
        return out
    if lo_.weekday() >= 5 or minute < NOISE["sitzung_von"] + 30 or minute >= NOISE["sitzung_bis"]:
        out["why"].append("außerhalb 8:30 bis 17 Uhr London")
        return out
    if schwankung is None and not op:
        out["why"].append("Schwankung unbekannt (zu wenig Tageskerzen)")
        return out
    if schwankung is not None and schwankung > NOISE["schwankung_max"] and not op:
        out["why"].append(f"Markt nicht ruhiger als sonst (Schwankung {schwankung:.3f} > 0,866): heute kein Trade")
        return out
    tage = nb_sitzungen(bars)
    band = band if band is not None else nb_band(tage, tag)
    if band is None:
        out["why"].append("weniger als 14 vollständige Sitzungen davor")
        return out
    heute = tage.get(tag, bars.iloc[0:0])
    ablauf = nb_ablauf(heute, band)
    soll = 0
    for e in ablauf:
        soll = 1 if e["aktion"] == "long" else -1 if e["aktion"] == "short" else 0
    letzte = ablauf[-1] if ablauf else None
    frisch = letzte is not None and jetzt - letzte["zeit"] < SPAET
    out["linien"] = None if not len(heute) else {k: letzte[k] for k in ("oben", "unten", "vwap")} if letzte else None
    if op:
        if soll != int(op["side"]):
            out.update(action="close", reason="signal", why=["Schluss zurück hinter Band bzw. VWAP"])
        else:
            out["why"].append("Position bleibt")
        return out
    if soll and frisch and letzte["aktion"] in ("long", "short"):
        out.update(action="open", side=soll, signal_bar=str(heute.index[letzte["k"]]),
                   why=[(f"Schluss {letzte['schluss']} {'über' if soll > 0 else 'unter'} dem Band "
                         f"({letzte['oben'] if soll > 0 else letzte['unten']:.3f})")])
    elif soll:
        out["why"].append("Einstieg des Backtests verpasst, wartet auf den nächsten")
    else:
        out["why"].append("kein Signal")
    return out
