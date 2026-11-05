"""Trend-Rücksetzer US500: Entscheidung für einen Vorwärtstest auf einem eigenen Capital.com-DEMOKONTO.

Herkunft: Strategie-Suche Runde 5/5b (suche/PROTOKOLL.md). Runde 5 (11 Swing-Strategien auf Tageskerzen, 41 Märkte) hat
keine bestanden. Die Regel "trend_ruecksetzer" hielt aber auf den US-Indizes in Auswahl (2011-2016) und Prüfung
(2017-2021). Runde 5b hat sie unverändert, vorab festgelegt, auf dem nie geöffneten Siegel 2022-2026 geprüft und
bestanden: S&P 500 und Nasdaq 100 zusammen 131 Trades, Gewinnfaktor 1,73, besser als 99,8 % der Zufallsläufe, mit
1,5-fachen Kosten 1,62. US500 war in Auswahl und Prüfung der bessere der beiden Märkte. Nie echtes Geld.

Regeln (genau wie suche/runde5.py sig_trend_ruecksetzer mit den Werten aus VORAB_runde5.yaml, gleicher Code):
- Tageskerze = die 24 Stunden (Bid) bis 15:00 Uhr New York; Samstag/Sonntag zählen zum Montag.
- Entscheidung einmal am Tag im ersten Lauf ab 15:00 Uhr New York (spätestens bis 16:00), zum Schluss der Kerze bis 15:00.
- Long: Schluss über dem 200-Tage-Schnitt und RSI(2) unter 10. Short: Schluss unter dem 200-Tage-Schnitt und RSI(2)
  über 90. Einstieg sofort per Marktorder.
- Raus zum Tagesschluss, wenn der Schluss über (Long) bzw. unter (Short) dem 5-Tage-Schnitt liegt, beim Gegensignal oder
  spätestens nach 5 Handelstagen. Notstop beim Broker: 3 x ATR(20) vom Schluss. Kein Ziel.
- Kleinste Größe (0,01), höchstens 10 Euro Risiko bis zum Stop.

    python -m suche.us500_bot             # ein Lauf (im Workflow der Demo-Bots, Mo-Fr alle 15 Minuten)
    python -m suche.us500_bot --dry-run   # nur rechnen und ausgeben, keine Order, nichts speichern

Konto und Lauf wie beim London-Bot (suche/london_bot.py): eigenes Konto (Name mit "US500" bevorzugt, sonst das neueste
freie Konto ohne offene Position), nie das Hauptkonto, nie ein Konto eines anderen Bots. Am Ende ist wieder das
Hauptkonto aktiv. Dateien: journal/us500-bot/ und journal/us500-bot.json. Tests: tests/test_us500_bot.py.
"""
from __future__ import annotations

import sys
from functools import partial

import numpy as np
import pandas as pd

from suche import london_bot as lb
from suche import runde5 as r5

TZ = "America/New_York"
EPIC = "US500"
SYM = "SPXUSD"                      # gleiche Tageskerzen-Regel wie im Backtest (runde5.MAERKTE)
STUNDE = 15                         # Entscheidungszeitpunkt T in New York
SPAETESTENS = 16                    # danach gilt der Tag als verpasst
PARAMETER = {"trend": 200, "unter": 10, "stop_atr": 3.0, "max_tage": 5}     # VORAB_runde5.yaml trend_ruecksetzer
TAGE_HOLEN = 420                    # Kalendertage Stundenkerzen (für 200-Tage-Schnitt und ATR)
MIN_TAGE = 230
FENSTER_TAGE = 40                   # je Abruf höchstens 1000 Stundenkerzen
FMT = "%Y-%m-%dT%H:%M:%S"
KOSTEN0 = {"spread_ersatz": {"index_us": 0.0}, "uebernacht": {"index": {"long": 0.0, "short": 0.0}}}


def _ny(ts: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(ts).tz_localize("UTC").tz_convert(TZ)


def schnitt_utc(now_utc: pd.Timestamp) -> pd.Timestamp:
    """Heute 15:00 Uhr New York in UTC (ohne Zeitzone)."""
    ny = _ny(now_utc)
    return ny.normalize().replace(hour=STUNDE).tz_convert("UTC").tz_localize(None)


def im_fenster(now_utc: pd.Timestamp) -> bool:
    ny = _ny(now_utc)
    return ny.day_of_week < 5 and STUNDE <= ny.hour < SPAETESTENS


def tageskerzen(bars: pd.DataFrame, sym: str = SYM):
    """Stundenkerzen (Bid, Index = Beginn in UTC) -> Tageskerzen genau wie im Backtest (runde5.baue_tage)."""
    return r5.baue_tage(sym, bars, None, KOSTEN0)


def entscheide(bars: pd.DataFrame, now_utc: pd.Timestamp, sb: dict, sym: str = SYM) -> dict:
    """Rückgabe wie london_bot.entscheide: action none/open/close, why, tag, erledigt; bei open side, signal_bar,
    stop_dist; bei close reason."""
    now = pd.Timestamp(now_utc)
    tag = str(_ny(now).date())
    out = {"action": "none", "tag": tag, "signal_bar": None}
    if _ny(now).day_of_week >= 5:
        return {**out, "why": "Wochenende"}
    if sb.get("tag_erledigt") == tag:
        return {**out, "why": "heute schon entschieden"}
    if not im_fenster(now):
        if _ny(now).hour >= SPAETESTENS:
            return {**out, "why": "15-Uhr-Entscheidung verpasst", "erledigt": True}
        return {**out, "why": "wartet auf 15 Uhr New York"}
    cut = schnitt_utc(now)
    bars = bars[bars.index < cut] if len(bars) else bars
    if not len(bars):
        return {**out, "why": "keine Kerzen"}
    T = tageskerzen(bars, sym)
    n = len(T.c) - 1
    if len(T.c) < MIN_TAGE:
        return {**out, "why": f"zu wenig Tageskerzen ({len(T.c)})"}
    if str(T.datum[n]) != tag or pd.Timestamp(T.t[n]) != cut:
        return {**out, "why": "heutige Kerze bis 15 Uhr New York noch nicht fertig"}
    s = r5.sig_trend_ruecksetzer(T, PARAMETER, {})
    a20 = r5.atr(T, 20)
    werte = {"schluss": round(float(T.c[n]), 2), "sma200": round(float(r5.sma(T.c, 200)[n]), 2),
             "sma5": round(float(r5.sma(T.c, 5)[n]), 2), "rsi2": round(float(r5.rsi(T.c, 2)[n]), 1),
             "atr20": round(float(a20[n]), 2)}
    out = {**out, "signal_bar": str(T.datum[n]), "werte": werte}
    op = sb.get("open")
    if op:
        side = int(op["side"])
        gehalten = int((T.datum > np.datetime64(str(op.get("tag")))).sum()) if op.get("tag") else 0
        if (side > 0 and (s.xl[n] or s.es[n])) or (side < 0 and (s.xs[n] or s.el[n])):
            return {**out, "action": "close", "reason": "Ausstiegssignal (5-Tage-Schnitt oder Gegensignal)",
                    "why": f"Ausstieg nach {gehalten} Tagen: {werte}"}
        if gehalten >= PARAMETER["max_tage"]:
            return {**out, "action": "close", "reason": "zeit", "why": f"{gehalten} Handelstage gehalten"}
        return {**out, "why": f"Position bleibt ({gehalten} Tage): {werte}", "erledigt": True}
    side = 1 if (s.el[n] and not s.xl[n]) else -1 if (s.es[n] and not s.xs[n]) else 0
    if not side:
        return {**out, "why": f"kein Signal: {werte}", "erledigt": True}
    if not (a20[n] > 0):
        return {**out, "why": "ATR fehlt", "erledigt": True}
    return {**out, "action": "open", "side": side, "stop_dist": float(PARAMETER["stop_atr"] * a20[n]),
            "why": f"{'Long' if side > 0 else 'Short'}: {werte}"}


def abstaende(d: dict, bid: float, offer: float) -> tuple[float, float | None] | None:
    """Stop als Abstand (3 x ATR vom Schluss), kein Ziel."""
    return (d["stop_dist"], None) if d.get("stop_dist", 0) > 0 else None


def _tag_als_stunden(day: pd.DataFrame, vor: pd.Timestamp) -> pd.DataFrame:
    """Tageskerzen (Bid) vor `vor` als je vier Stunden 11 bis 15 Uhr New York, damit runde5.baue_tage sie als einen Tag
    liest (O/H/L/C der Tageskerze). Nur für den 200-Tage-Schnitt, falls die Stundenkerzen nicht weit genug zurückreichen."""
    rows, idx = [], []
    for t, r in day.iterrows():
        d = pd.Timestamp(t).normalize()
        if d.day_of_week >= 5 or d >= pd.Timestamp(vor):
            continue
        for k in range(4):
            idx.append(pd.Timestamp(d.date(), tz=TZ) + pd.Timedelta(hours=11 + k))
            rows.append((r.open, r.high, r.low, r.close) if k == 0 else (r.close, r.close, r.close, r.close))
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close"], dtype=float)
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"],
                        index=pd.DatetimeIndex(idx).tz_convert("UTC").tz_localize(None))


def hole_stunden(client, now_utc: pd.Timestamp, st: dict, epic: str = EPIC) -> pd.DataFrame:
    """Stundenkerzen der letzten TAGE_HOLEN Tage, nur im Entscheidungsfenster (sonst leer: spart Abrufe). Reichen sie
    nicht weit genug zurück, ergänzen Capital.com-Tageskerzen die älteren Tage (nur für den 200-Tage-Schnitt)."""
    from suche.demo_bots import frame
    tag = str(_ny(now_utc).date())
    leer = pd.DataFrame(columns=["open", "high", "low", "close"], dtype=float)
    if not im_fenster(now_utc) or st.get("tag_erledigt") == tag:
        return leer
    teile, bis = [], pd.Timestamp(now_utc)
    beginn = bis - pd.Timedelta(days=TAGE_HOLEN)
    while bis > beginn:
        von = max(beginn, bis - pd.Timedelta(days=FENSTER_TAGE))
        try:
            got = client._get(f"/prices/{epic}", resolution="HOUR", max=1000,
                              **{"from": von.strftime(FMT), "to": bis.strftime(FMT)}).get("prices", [])
        except Exception:                # noqa: BLE001 - weiter zurück gibt es keine Stundenkerzen
            got = []
        if not got:
            break
        teile.extend(got)
        bis = von
    bars, _ = frame(teile)
    bars = bars[bars.index + pd.Timedelta(hours=1) <= pd.Timestamp(now_utc)]
    lab = r5.tageslabel(bars.index, TZ, STUNDE) if len(bars) else np.array([], "datetime64[D]")
    if len(np.unique(lab)) < MIN_TAGE + 10:
        day, _ = frame(client._get(f"/prices/{epic}", resolution="DAY", max=400).get("prices", []))
        if len(lab):                     # erster (meist unvollständiger) Tag kommt aus der Tageskerze
            bars = bars[lab > lab[0]]
            vor = pd.Timestamp(lab[0]) + pd.Timedelta(days=1)
        else:
            vor = pd.Timestamp(_ny(now_utc).date())
        bars = pd.concat([_tag_als_stunden(day, vor), bars]).sort_index()
        bars = bars[~bars.index.duplicated(keep="last")]
    return bars


def _ny_tag(ts: pd.Timestamp) -> str:
    return str(_ny(ts).date())


BOT_ID = "us500-ruecksetzer"
KONTO_NAMEN = ("us500", "us 500", "s&p", "sp500", "rücksetzer", "ruecksetzer")
FREMDE = ("london", "eurusd", "asien", "asia", "gbpnzd", "brent", "japan", "dow", "us30", "kupfer", "copper",
          "intel", "dax", "de40", "gold")
REGEL_TEXT = ("Trend-Rücksetzer US500 (Runde 5b): einmal am Tag um 15 Uhr New York; über dem 200-Tage-Schnitt kaufen, "
              "wenn RSI(2) unter 10 schließt, darunter verkaufen bei RSI(2) über 90; raus über/unter dem 5-Tage-Schnitt, "
              "beim Gegensignal oder nach 5 Handelstagen; Notstop 3 x ATR(20), kein Ziel, kleinste Größe. Siegel "
              "2022-2026 (S&P 500 + Nasdaq 100): 131 Trades, Gewinnfaktor 1,73, Zufall 99,8 %. Vorwärtstest seit "
              "Kirons Merge (suche/VORAB_us500.yaml).")
US500 = lb.BotDef(BOT_ID, EPIC, KONTO_NAMEN, FREMDE, entscheide, abstaende, _ny_tag, lb.ROOT / "journal" / "us500-bot",
                  lb.ROOT / "journal" / "us500-bot.json", REGEL_TEXT, "nach 5 Handelstagen", kerzen=hole_stunden,
                  warte_text="wartet auf das nächste Signal (15 Uhr New York)")


# Dieselbe Regel auf Nasdaq 100 und Dow (Kirons Wunsch vom 04.11.2026: alle Strategien gleich bewerten, die besten auf
# die Demokonten; suche/VORAB_bewertung.yaml, Ergebnis journal/portfolio.json). Sie handeln nur auf einem Konto, das ihnen
# die Demo-Bots in journal/konten.json zuordnen (Konto eines abgelösten Bots); ohne Zuordnung läuft gar nichts.
# Dow: HistData hat keine Dow-Reihe; die Tageskerzen-Regel braucht nur Zeitzone und Uhrzeit (New York, 15 Uhr), die
# gleichen wie beim S&P 500.
def _weiterer(bot_id: str, epic: str, sym: str, name: str, ordner: str, beleg: str) -> lb.BotDef:
    regel = (f"Trend-Rücksetzer {name} (Runde 5b/5c, gleiche Regel wie US500): einmal am Tag um 15 Uhr New York; über dem "
             "200-Tage-Schnitt kaufen, wenn RSI(2) unter 10 schließt, darunter verkaufen bei RSI(2) über 90; raus über/"
             "unter dem 5-Tage-Schnitt, beim Gegensignal oder nach 5 Handelstagen; Notstop 3 x ATR(20), kein Ziel, "
             f"kleinste Größe. {beleg}")
    return lb.BotDef(bot_id, epic, (bot_id,), FREMDE, partial(entscheide, sym=sym), abstaende, _ny_tag,
                     lb.ROOT / "journal" / ordner, lb.ROOT / "journal" / f"{ordner}.json", regel, "nach 5 Handelstagen",
                     kerzen=partial(hole_stunden, epic=epic), warte_text="wartet auf das nächste Signal (15 Uhr New York)",
                     nur_mit_namen=True)


US100 = _weiterer("r5-ruecksetzer-us100", "US100", "NSXUSD", "US100 (Nasdaq 100)", "us100-ruecksetzer",
                  "Capital.com-Tageskerzen 2025 bis Oktober 2026: 23 Trades, Gewinnfaktor 1,91.")
US30 = _weiterer("r5-ruecksetzer-us30", "US30", "SPXUSD", "Dow (US30)", "us30-ruecksetzer",
                 "Capital.com-Tageskerzen 2025 bis Oktober 2026: 23 Trades, Gewinnfaktor 1,48.")
WEITERE = (US100, US30)


def letzte_entscheidungszeit(now_utc: pd.Timestamp) -> pd.Timestamp:
    """Der letzte Werktag 15:01 New York vor `now_utc` (UTC ohne Zeitzone)."""
    ny = _ny(now_utc)
    t = ny.normalize() + pd.Timedelta(hours=STUNDE, minutes=1)
    while t > ny or t.day_of_week >= 5:
        t = (t - pd.Timedelta(days=1)).normalize() + pd.Timedelta(hours=STUNDE, minutes=1)
    return t.tz_convert("UTC").tz_localize(None)


def probe(client, now_utc: pd.Timestamp) -> dict:
    """Nur lesen: Kerzen holen und die Entscheidung für den letzten 15-Uhr-Zeitpunkt rechnen (keine Order)."""
    t = letzte_entscheidungszeit(now_utc)
    bars = hole_stunden(client, t, {})
    d = entscheide(bars, t, {})
    T = tageskerzen(bars[bars.index < schnitt_utc(t)]) if len(bars) else None
    return {"zeitpunkt_utc": str(t), "stundenkerzen": int(len(bars)), "tageskerzen": 0 if T is None else int(len(T.c)),
            "erste_kerze": str(bars.index[0]) if len(bars) else None, "entscheidung": d}


def main(argv: list[str]) -> int:
    rc = lb.main(argv, US500)
    from gold.bot import konten
    zu = konten.load().get("zuordnung") or {}
    for bot in WEITERE:                 # nur mit zugeordnetem Konto; ein Fehler hier hält US500 nie auf
        if bot.bot_id in zu:
            try:
                rc = lb.main(argv, bot) or rc
            except Exception as err:    # noqa: BLE001
                print(f"{bot.bot_id}: Fehler {str(err)[:200]}")
    if "--dry-run" in argv:             # Trockenlauf: zusätzlich die Entscheidung des letzten 15-Uhr-Zeitpunkts zeigen
        import json
        import os
        from gold.bot.capital import CapitalClient
        from gold.bot.runner import CRED_KEYS, clean_credentials
        creds = clean_credentials({k: os.environ.get(k, "") for k in CRED_KEYS})
        if all(creds):
            client = CapitalClient(*creds, environment="demo")
            try:
                client.login()
                print(json.dumps({"probe": probe(client, pd.Timestamp.now(tz="UTC").tz_localize(None))},
                                 ensure_ascii=False, indent=1, default=str))
            except Exception as err:    # noqa: BLE001
                print(f"Probe fehlgeschlagen: {str(err)[:200]}")
            finally:
                try:
                    client.logout()
                except Exception:       # noqa: BLE001
                    pass
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
