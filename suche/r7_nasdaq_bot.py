"""Noise-Band nur Long auf dem Nasdaq (US100), mit weitem Stop und 5 Tagen Halten: Vorwärtstest auf einem eigenen
Capital.com-DEMOKONTO (Kirons Wahl vom 04.11.2026 nach Runde 7, suche/VORAB_r7_nasdaq.yaml). Nie echtes Geld.

Herkunft: Runde 7 (suche/VORAB_runde7.yaml, suche/PROTOKOLL.md). Einstieg wie runde4.noise_band_trades (nur Long, vm 1,0)
mit der Runde-6-Bedingung "Markt ruhiger als sonst" (ATR 14 / ATR 100 der Tageskerzen bis zum Vortag <= 0,8654),
Ausstieg aus Runde 7 (freie Wahl): Stop 5 x ATR(14) der Tageskerzen, kein Ziel, raus um 16:00 New York am 5.
Handelstag (Einstiegstag = Tag 1). Prüf-Jahre 2021-2026: 61 Trades, Gewinnfaktor 2,11, Zufall 99,1 %.

Regeln (gleiche Rechnung wie der Backtest):
- Sitzung 9:30-16:00 New York, 15-Minuten-Kerzen (Bid). Ein Sitzungstag zählt nur vollständig (mindestens 24 Kerzen,
  erste um 9:30). An US-Feiertagen und kurzen Börsentagen gibt es keine volle Sitzung, also keinen Einstieg.
- Band: sigma[k] = Mittel der letzten 14 vollständigen Sitzungen von |Schluss[k] / Eröffnung 9:30 - 1| (k < 24);
  oben[k] = max(Eröffnung heute 9:30, Schluss der letzten vollständigen Sitzung) x (1 + sigma[k]).
- Prüfpunkte: Schluss der Kerzen 1, 3, ..., 21 (10:00, 10:30, ..., 15:00 New York). Das Band-Signal des Backtests
  läuft den ganzen Tag mit (rein über dem Band, raus unter max(Band, VWAP), wieder rein); jeder Einstieg daraus ist ein
  Einstieg für den Bot, wenn er gerade keine Position hat (Eröffnung der nächsten Kerze, also im Lauf direkt danach).
- Notstop beim Broker 5 x ATR(14) der Tageskerzen (Handelstag bis 17:00 New York, Stand Vortag). Kein Ziel.
- Raus im ersten Lauf ab 16:00 New York am 5. Handelstag (an US-Feiertagen und kurzen Tagen ab 12:45). Handelstage:
  Montag bis Freitag ohne Weihnachten, Neujahr und Karfreitag (dort gibt es im Backtest keine Kerzen).

    python -m suche.r7_nasdaq_bot             # ein Lauf (im Workflow der Demo-Bots, Mo-Fr alle 15 Minuten)
    python -m suche.r7_nasdaq_bot --dry-run   # nur rechnen und ausgeben, keine Order, nichts speichern

Konto: nur ein Demokonto, dessen Name "Nasdaq" (oder "US100") enthält; nie das Hauptkonto, nie ein Ersatzkonto.
Dateien: journal/r7-nasdaq-bot/ und journal/r7-nasdaq-bot.json. Nachspiel gegen den Backtest: suche/r7_nasdaq_nachspiel.py.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd

from suche import london_bot as lb
from suche import r6_regeln as rg

TZ = "America/New_York"
EPIC = "US100"
BEGINN = 9 * 60 + 30
ENDE = 16 * 60
N_SITZUNG = 24                       # kürzeste Sitzung im Backtest (runde4.noise_band_trades: n = min Länge)
PRUEFPUNKTE = tuple(range(1, N_SITZUNG - 1, 2))      # 1, 3, ..., 21
LETZTER_EINSTIEG = BEGINN + 15 * (PRUEFPUNKTE[-1] + 1)   # 15:00: Eröffnung der Kerze nach dem letzten Prüfpunkt
SIG_TAGE = 14
VM = 1.0
SCHWANKUNG_MAX = 0.8653728646155798  # Runde 6, noise_band_long: schwankung=niedrig (Drittel-Grenze aus 2015-2020)
STOP_ATR = 5.0
HALTE_TAGE = 5
AUS_MINUTE = 16 * 60                  # Zeitausstieg 16:00 New York (Schluss der Kerze 15:45-16:00)
AUS_MINUTE_KURZ = 12 * 60 + 45        # an US-Feiertagen und kurzen Tagen enden die Kerzen um 13:00/13:15
TAGE_STUNDEN = 170                    # Kalendertage Stundenkerzen für ATR 100 (einmal am Tag)
TAGE_BAND = 45                        # Kalendertage 15-Minuten-Kerzen für 14 volle Sitzungen (auch nach Weihnachten)


def _ny(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    return (t if t.tzinfo else t.tz_localize("UTC")).tz_convert(TZ)


def _minute(ts) -> int:
    n = _ny(ts)
    return n.hour * 60 + n.minute


# --------------------------------------------------------------------------------------------------------------------
# Kalender (US-Börse)

def _ostern(j: int) -> date:
    """Ostersonntag (gregorianisch, Meeus/Jones/Butcher)."""
    a, b, c = j % 19, j // 100, j % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    return date(j, (h + l_ - 7 * m + 114) // 31, (h + l_ - 7 * m + 114) % 31 + 1)


def _nter(j: int, monat: int, wtag: int, n: int) -> date:
    """n-ter Wochentag (0 = Montag) im Monat; n = -1: der letzte."""
    if n > 0:
        d = date(j, monat, 1)
        d += timedelta(days=(wtag - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)
    d = date(j + (monat == 12), monat % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - wtag) % 7)


def _beobachtet(d: date) -> date:
    """Feiertag am Samstag -> Freitag davor, am Sonntag -> Montag danach."""
    return d - timedelta(days=1) if d.weekday() == 5 else d + timedelta(days=1) if d.weekday() == 6 else d


@lru_cache(maxsize=None)
def frei_tage(j: int) -> frozenset:
    """Werktage ohne Handel im Nasdaq-CFD (keine Kerzen im Backtest): Weihnachten, Neujahr (beobachtet), Karfreitag."""
    out = {_beobachtet(date(j, 12, 25)), _ostern(j) - timedelta(days=2)}
    if date(j, 1, 1).weekday() != 5:        # Neujahr am Samstag: kein freier Freitag davor
        out.add(_beobachtet(date(j, 1, 1)))
    return frozenset(str(d) for d in out)


@lru_cache(maxsize=None)
def kurztage(j: int) -> frozenset:
    """US-Börsenfeiertage und kurze Börsentage (Schluss 13:00): dort gibt es keine volle Sitzung 9:30-16:00."""
    thanks = _nter(j, 11, 3, 4)
    tage = {_nter(j, 1, 0, 3), _nter(j, 2, 0, 3), _ostern(j) - timedelta(days=2), _nter(j, 5, 0, -1),
            _beobachtet(date(j, 7, 4)), _nter(j, 9, 0, 1), thanks, thanks + timedelta(days=1),
            _beobachtet(date(j, 12, 25))}
    if date(j, 1, 1).weekday() != 5:
        tage.add(_beobachtet(date(j, 1, 1)))
    if j >= 2022:
        tage.add(_beobachtet(date(j, 6, 19)))
    for kurz in (date(j, 7, 3), date(j, 12, 24)):                         # Vortag von 4. Juli und Weihnachten
        tage.add(kurz)
    return frozenset(str(d) for d in tage if d.weekday() < 5)


def ist_handelstag(tag: str) -> bool:
    t = pd.Timestamp(tag)
    return t.day_of_week < 5 and tag not in frei_tage(t.year)


def ist_kurztag(tag: str) -> bool:
    return tag in kurztage(pd.Timestamp(tag).year)


def handelstage_nach(tag: str, n: int) -> str:
    """Datum des n-ten Handelstags ab `tag` (tag = 1)."""
    t = pd.Timestamp(tag)
    zaehl = 1
    while zaehl < n:
        t += pd.Timedelta(days=1)
        if ist_handelstag(str(t.date())):
            zaehl += 1
    return str(t.date())


# --------------------------------------------------------------------------------------------------------------------
# Reine Rechnung (ohne Netz, testbar, vom Nachspiel genutzt)

def sitzungen(bars: pd.DataFrame) -> list[tuple[str, np.ndarray]]:
    """Vollständige Sitzungstage wie runde4.baue_markt: (Datum New York, Positionen der Kerzen 9:30-16:00)."""
    if not len(bars):
        return []
    lok = bars.index.tz_localize("UTC").tz_convert(TZ)
    tod = np.asarray(lok.hour * 60 + lok.minute)
    drin = (tod >= BEGINN) & (tod < ENDE) & (np.asarray(lok.weekday) < 5)
    pos = np.flatnonzero(drin)
    if not len(pos):
        return []
    tage = np.asarray(lok.tz_localize(None).normalize()[pos])
    grenzen = np.flatnonzero(tage[1:] != tage[:-1]) + 1
    out = []
    for teil in np.split(pos, grenzen):
        if len(teil) >= (ENDE - BEGINN) // 15 - 2 and tod[teil[0]] == BEGINN:
            out.append((str(lok[teil[0]].date()), teil))
    return out


def band(bars: pd.DataFrame, tag: str) -> dict:
    """Band-Breite je Kerze und Schluss der letzten vollständigen Sitzung vor `tag` (15-Minuten-Bid-Kerzen)."""
    s = [x for x in sitzungen(bars) if x[0] < tag]
    if len(s) < SIG_TAGE + 1:
        return {"why": f"zu wenig vollständige Sitzungen ({len(s)})"}
    o, c = bars["open"].to_numpy(float), bars["close"].to_numpy(float)
    bew = np.array([np.abs(c[idx[:N_SITZUNG]] / o[idx[0]] - 1) for _, idx in s[-SIG_TAGE:]])
    return {"sig": [float(x) for x in bew.mean(axis=0)], "vorschluss": float(c[s[-1][1][-1]]),
            "letzte_sitzung": s[-1][0]}


def tagesplan(bars: pd.DataFrame, stunden: pd.DataFrame, tag: str) -> dict:
    """Alles, was für den Sitzungstag `tag` vorher feststeht: Band, Schwankung und ATR(14) der Tageskerzen bis zum
    Vortag (aus Stundenkerzen wie bei den Runde-6-Bots, r6_regeln.tageswerte)."""
    out = {"tag": tag, "ok": False}
    if ist_kurztag(tag) or not ist_handelstag(tag):
        return {**out, "why": "US-Feiertag oder kurzer Börsentag: keine volle Sitzung, heute kein Einstieg"}
    bd = band(bars, tag)
    out.update(bd)
    w = rg.tageswerte(stunden, pd.Timestamp(tag))
    if w:
        out.update(schwankung=w["schwankung"], atr14=w["atr14"], atr_bis=w["bis"])
    if "sig" not in bd:
        return {**out, "why": bd["why"]}
    if not w or not w["atr14"] > 0:
        return {**out, "why": "zu wenig Tageskerzen für ATR 14 / ATR 100"}
    if w["schwankung"] > SCHWANKUNG_MAX:
        return {**out, "why": f"Markt nicht ruhiger als sonst (Schwankung {w['schwankung']:.3f} > 0,865): heute kein Trade"}
    return {**out, "ok": True, "why": f"Bedingung erfüllt (Schwankung {w['schwankung']:.3f} <= 0,865)"}


def einstiege(plan: dict, heute: pd.DataFrame) -> list[dict]:
    """Einstiege des Band-Signals (wie runde4.noise_band_trades, nur Long) aus den fertigen Kerzen der heutigen Sitzung
    ab 9:30: je Einstieg die Kerze (Position ab 9:30), deren Eröffnung der Einstieg ist."""
    if not len(heute) or _minute(heute.index[0]) != BEGINN:
        return []
    o0 = float(heute["open"].iloc[0])
    basis = max(o0, float(plan["vorschluss"]))
    h, l, c = (heute[k].to_numpy(float)[:N_SITZUNG] for k in ("high", "low", "close"))
    vw = np.cumsum((h + l + c) / 3) / np.arange(1, len(c) + 1)
    out, drin = [], False
    for k in PRUEFPUNKTE:
        if k >= len(c):
            break
        oben = basis * (1 + VM * plan["sig"][k])
        if not drin and c[k] > oben:
            drin = True
            out.append({"k": k, "kerze": k + 1, "schluss": float(c[k]), "oben": round(oben, 2)})
        elif drin and c[k] < max(oben, vw[k]):
            drin = False
    return out


def aus_minute(tag: str) -> int:
    return AUS_MINUTE_KURZ if ist_kurztag(tag) else AUS_MINUTE


def faellig(op: dict, now_utc) -> bool:
    """Zeitausstieg fällig: ab 16:00 New York am 5. Handelstag (kurzer Tag: 12:45) oder später."""
    aus = handelstage_nach(op["tag"], HALTE_TAGE)
    heute = str(_ny(now_utc).date())
    return heute > aus or (heute == aus and _minute(now_utc) >= aus_minute(aus))


def entscheide(bars: pd.DataFrame, now_utc: pd.Timestamp, sb: dict) -> dict:
    """Wie london_bot.entscheide. bars: heutige fertige Sitzungskerzen ab 9:30; der Tagesplan in bars.attrs["plan"]."""
    now = pd.Timestamp(now_utc)
    ny = _ny(now)
    tag = str(ny.date())
    out = {"action": "none", "tag": tag, "signal_bar": None}
    op = sb.get("open")
    if op:
        aus = handelstage_nach(op["tag"], HALTE_TAGE)
        if faellig(op, now):
            return {**out, "action": "close", "reason": "zeit", "why": f"5. Handelstag ({aus}) erreicht"}
        return {**out, "why": f"Position bleibt bis {aus} {aus_minute(aus) // 60}:{aus_minute(aus) % 60:02d} New York"}
    if ny.day_of_week >= 5:
        return {**out, "why": "Wochenende"}
    if sb.get("tag_erledigt") == tag:
        return {**out, "why": "heute schon entschieden"}
    m = _minute(now)
    if m < BEGINN + 30:
        return {**out, "why": "wartet auf den ersten Prüfpunkt (10:00 New York)"}
    plan = bars.attrs.get("plan") or {}
    if plan.get("tag") != tag:
        return {**out, "why": "kein Tagesplan"}
    if not plan.get("ok"):
        return {**out, "why": plan.get("why", "Bedingung nicht erfüllt"), "erledigt": True}
    if m >= LETZTER_EINSTIEG + 15:
        return {**out, "why": "kein Einstieg mehr heute (letzter um 15:00 New York)", "erledigt": True}
    if not len(bars):
        return {**out, "why": "keine Kerzen von heute"}
    beginn = pd.Timestamp(bars.index[0])
    for e in einstiege(plan, bars):
        start = beginn + pd.Timedelta(minutes=15 * e["kerze"])
        if start <= now < start + pd.Timedelta(minutes=15):
            return {**out, "action": "open", "side": 1, "signal_bar": str(bars.index[e["k"]]),
                    "stop_dist": float(STOP_ATR * plan["atr14"]), "oben": e["oben"],
                    "why": f"Long: Schluss {e['schluss']:.1f} über dem Band {e['oben']:.1f} (Prüfpunkt {e['k']})"}
    return {**out, "why": f"kein neuer Schluss über dem Band ({len(bars)} Kerzen)"}


def abstaende(d: dict, bid: float, offer: float) -> tuple[float, float | None] | None:
    """Notstop 5 x ATR(14), kein Ziel."""
    return (d["stop_dist"], None) if d.get("stop_dist", 0) > 0 else None


# --------------------------------------------------------------------------------------------------------------------
# Kerzen von Capital.com

def hole_kerzen(client, now_utc: pd.Timestamp, st: dict) -> pd.DataFrame:
    """Heutige fertige Sitzungskerzen ab 9:30; der Tagesplan wird einmal am Tag gerechnet und im Zustand gemerkt."""
    from suche.r6_bots import kerzen_zeitraum
    leer = pd.DataFrame(columns=["open", "high", "low", "close"], dtype=float)
    ny = _ny(now_utc)
    tag = str(ny.date())
    m = ny.hour * 60 + ny.minute
    if (st.get("open") or ny.day_of_week >= 5 or st.get("tag_erledigt") == tag
            or not (BEGINN + 30 <= m < LETZTER_EINSTIEG + 15)):
        return leer
    now = pd.Timestamp(now_utc)
    plan = st.get("plan") if (st.get("plan") or {}).get("tag") == tag else None
    if plan is None:
        stunden, _ = kerzen_zeitraum(client, EPIC, "HOUR", TAGE_STUNDEN, now)
        b15, _ = kerzen_zeitraum(client, EPIC, "MINUTE_15", TAGE_BAND, now)
        plan = tagesplan(b15, stunden, tag)
        plan.update(stundenkerzen=int(len(stunden)), kerzen_15=int(len(b15)))
        st["plan"] = plan
    if not plan.get("ok"):
        out = leer.copy()
        out.attrs["plan"] = plan
        return out
    beginn = ny.normalize().replace(hour=9, minute=30).tz_convert("UTC").tz_localize(None)
    heute, _ = kerzen_zeitraum(client, EPIC, "MINUTE_15", 1, now)
    heute = heute[heute.index >= beginn]
    heute = heute[[_minute(t) < ENDE for t in heute.index]] if len(heute) else heute
    heute.attrs["plan"] = plan
    return heute


def _ny_tag(ts: pd.Timestamp) -> str:
    return str(_ny(ts).date())


BOT_ID = "r7-nasdaq-noise-long"
KONTO_NAMEN = ("nasdaq", "us100", "us 100")
FREMDE = ("london", "eurusd", "asien", "asia", "gbpnzd", "brent", "japan", "dow", "us30", "kupfer", "copper", "intel",
          "dax", "de40", "gold", "us500", "us 500", "s&p", "sp500", "rücksetzer", "ruecksetzer", "vortag", "usdjpy",
          "gbpusd", "noise")
REGEL_TEXT = ("Noise-Band nur Long auf dem Nasdaq (Runde 7): Schluss über dem Band (10:00-15:00 New York, alle 30 "
              "Minuten), nur wenn der Markt ruhiger ist als sonst; Notstop 5 x Tages-ATR, kein Ziel, raus um 16 Uhr New "
              "York am 5. Handelstag; kleinste Größe. Prüf-Jahre 2021-2026: 61 Trades, Gewinnfaktor 2,11, aber nur "
              "1,0 R im Jahr und im Nasdaq-Aufschwung. Vorwärtstest vorab festgelegt (suche/VORAB_r7_nasdaq.yaml), "
              "Urteil nach 40 Trades (etwa 3 bis 4 Jahre).")
NASDAQ = lb.BotDef(BOT_ID, EPIC, KONTO_NAMEN, FREMDE, entscheide, abstaende, _ny_tag, lb.ROOT / "journal" / "r7-nasdaq-bot",
                   lb.ROOT / "journal" / "r7-nasdaq-bot.json", REGEL_TEXT, "5. Handelstag erreicht",
                   kerzen=hole_kerzen, warte_text="wartet auf einen Schluss über dem Band (10:00-15:00 New York)",
                   nur_mit_namen=True)


VORAB = lb.ROOT / "suche" / "VORAB_r7_nasdaq.yaml"


def cockpit_ergaenzen(path) -> None:
    """Für die Karte im Cockpit: Name, gewünschter Kontoname und Urteilsregel aus der VORAB-Datei."""
    import json

    import yaml
    d = json.loads(path.read_text(encoding="utf-8"))
    v = yaml.safe_load(VORAB.read_text(encoding="utf-8"))["r7_nasdaq_vorwaerts"]
    d.update(name="Noise-Band Long Nasdaq", konto_vorschlag="Nasdaq",
             vorab={"datei": "suche/VORAB_r7_nasdaq.yaml", "urteil": v["urteil"], "zwischencheck": v["zwischencheck"]})
    path.write_text(json.dumps(d, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    rc = lb.main(argv, NASDAQ)
    if "--dry-run" not in argv and NASDAQ.cockpit.exists():
        cockpit_ergaenzen(NASDAQ.cockpit)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
