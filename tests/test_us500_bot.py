"""Tests für suche/us500_bot.py: Trend-Rücksetzer US500 (Entscheidung ohne Netz, Lauf mit einem Demokonto im Kleinen)."""
import numpy as np
import pandas as pd

from suche import london_bot as lb
from suche import runde5 as r5
from suche import us500_bot as ub
from test_london_bot import A1, HAUPT, NEU, FakeClient

NY = "America/New_York"


def stunden(schluesse, letzter_tag: str) -> pd.DataFrame:
    """Bid-Stundenkerzen (Index = Beginn in UTC): je Werktag die 24 Stunden bis 15:00 New York, Kurs läuft linear vom
    Vortagesschluss zum Tagesschluss. Der letzte Wert ist der Schluss von `letzter_tag` um 15:00 New York."""
    tage = pd.bdate_range(end=letzter_tag, periods=len(schluesse))
    rows, idx = [], []
    for i, d in enumerate(tage):
        vor = schluesse[i - 1] if i else schluesse[0]
        start = pd.Timestamp(d.date(), tz=NY) + pd.Timedelta(hours=15) - pd.Timedelta(hours=24)
        for k in range(24):
            o = vor + (schluesse[i] - vor) * k / 24
            c = vor + (schluesse[i] - vor) * (k + 1) / 24
            idx.append(start + pd.Timedelta(hours=k))
            rows.append((o, max(o, c) + 0.5, min(o, c) - 0.5, c))
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"],
                      index=pd.DatetimeIndex(idx).tz_convert("UTC").tz_localize(None))
    return df[~df.index.duplicated(keep="last")]


def lauf(ny: str) -> pd.Timestamp:
    return pd.Timestamp(ny, tz=NY).tz_convert("UTC").tz_localize(None)


AUFWAERTS = list(5000 * 1.001 ** np.arange(300))
RUECKSETZER = AUFWAERTS + [AUFWAERTS[-1] * 0.985, AUFWAERTS[-1] * 0.97]          # zwei Tage fallen, über SMA 200
TAG = "2026-11-04"                                                                   # Mittwoch


def test_wartet_bis_15_uhr_und_verpasst_nach_16_uhr():
    bars = stunden(RUECKSETZER, TAG)
    d = ub.entscheide(bars, lauf(f"{TAG} 14:46"), {})
    assert d["action"] == "none" and not d.get("erledigt") and "15 Uhr" in d["why"]
    d = ub.entscheide(bars, lauf(f"{TAG} 16:01"), {})
    assert d["action"] == "none" and d.get("erledigt")
    d = ub.entscheide(bars, lauf(f"{TAG} 15:01"), {"tag_erledigt": TAG})
    assert d["action"] == "none" and d["why"] == "heute schon entschieden"
    d = ub.entscheide(bars, lauf("2026-11-07 15:01"), {})
    assert d["action"] == "none" and d["why"] == "Wochenende"


def test_ruecksetzer_ueber_sma200_oeffnet_long_mit_notstop_3_atr():
    bars = stunden(RUECKSETZER, TAG)
    d = ub.entscheide(bars, lauf(f"{TAG} 15:01"), {})
    assert d["action"] == "open" and d["side"] == 1 and d["tag"] == TAG and d["signal_bar"] == TAG
    T = ub.tageskerzen(bars[bars.index < ub.schnitt_utc(lauf(f"{TAG} 15:01"))])
    assert abs(d["stop_dist"] - 3 * r5.atr(T, 20)[-1]) < 1e-9 and d["werte"]["rsi2"] < 10
    assert ub.abstaende(d, 5000.0, 5000.6) == (d["stop_dist"], None)


def test_gleiche_tageskerzen_wie_im_backtest():
    bars = stunden(RUECKSETZER, TAG)
    T = ub.tageskerzen(bars)
    assert str(T.datum[-1]) == TAG and abs(T.c[-1] - RUECKSETZER[-1]) < 1e-9
    assert abs(T.c[-2] - RUECKSETZER[-2]) < 1e-9 and len(T.c) == len(RUECKSETZER)


def test_kein_signal_ohne_ruecksetzer_und_unvollstaendige_kerze_wartet():
    d = ub.entscheide(stunden(AUFWAERTS, TAG), lauf(f"{TAG} 15:01"), {})
    assert d["action"] == "none" and d.get("erledigt") and "kein Signal" in d["why"]
    halb = stunden(RUECKSETZER, TAG).iloc[:-3]                                    # die letzten Stunden fehlen noch
    d = ub.entscheide(halb, lauf(f"{TAG} 15:01"), {})
    assert d["action"] == "none" and not d.get("erledigt")


def test_offene_position_raus_ueber_sma5_sonst_nach_5_tagen():
    erholt = RUECKSETZER + [RUECKSETZER[-1] * 1.03]                                 # Schluss über SMA 5
    d = ub.entscheide(stunden(erholt, "2026-11-05"), lauf("2026-11-05 15:01"), {"open": {"side": 1, "tag": TAG}})
    assert d["action"] == "close" and "Ausstiegssignal" in d["reason"]
    weiter = RUECKSETZER + [RUECKSETZER[-1] * 0.999 ** k for k in range(1, 6)]     # bleibt unter SMA 5
    d = ub.entscheide(stunden(weiter, "2026-11-11"), lauf("2026-11-11 15:01"), {"open": {"side": 1, "tag": TAG}})
    assert d["action"] == "close" and d["reason"] == "zeit"
    d = ub.entscheide(stunden(weiter[:-1], "2026-11-10"), lauf("2026-11-10 15:01"), {"open": {"side": 1, "tag": TAG}})
    assert d["action"] == "none" and d.get("erledigt") and "4 Tage" in d["why"]


class US500Client(FakeClient):
    def market(self, epic):
        if epic == "EURUSD":
            return {"snapshot": {"bid": 1.08, "offer": 1.08}, "instrument": {}, "dealingRules": {}}
        last = float(self.bars["close"].iloc[-1])
        return {"snapshot": {"bid": last, "offer": last + 0.6, "marketStatus": "TRADEABLE", "decimalPlacesFactor": 1},
                "instrument": {"currency": "USD", "lotSize": 1, "marginFactor": 5, "marginFactorUnit": "PERCENTAGE"},
                "dealingRules": {"minDealSize": {"value": 0.01}, "minSizeIncrement": {"value": 0.01},
                                 "minStopOrProfitDistance": {"unit": "PERCENTAGE", "value": 0.01}}}

    def _get(self, path, **params):
        assert path == "/prices/US500" and params["resolution"] == "HOUR"
        return {"prices": self.prices("US500")}


def test_lauf_oeffnet_auf_eigenem_konto_ohne_ziel_und_kehrt_zurueck():
    c = US500Client(stunden(RUECKSETZER, TAG), {HAUPT: "Account", A1: "Account 1", NEU: "US500"})
    k = {"format": 1, "haupt": HAUPT, "zuordnung": {"oil-brent": A1}}
    st, neu, log = lb.run(c, {}, k, lauf(f"{TAG} 15:01").to_pydatetime(), bot=ub.US500)
    assert k["zuordnung"]["us500-ruecksetzer"] == NEU and len(c.orders) == 1 and c.orders[0][0] == NEU
    body = c.orders[0][1]
    assert body["epic"] == "US500" and body["direction"] == "BUY" and body["size"] == 0.01
    assert "profitDistance" not in body and body["stopDistance"] > 0
    assert st["tag_erledigt"] == TAG and st["open"]["tag"] == TAG and c.account_id == HAUPT
    # Später am selben Tag: keine Abrufe mehr nötig, kein zweiter Trade
    st, neu, log = lb.run(c, st, k, lauf(f"{TAG} 15:16").to_pydatetime(), bot=ub.US500)
    assert len(c.orders) == 1 and not neu


def test_lauf_ausserhalb_des_fensters_holt_keine_kerzen():
    c = US500Client(stunden(RUECKSETZER, TAG))
    abrufe = []
    c._get = lambda path, **p: abrufe.append(path) or {"prices": []}
    st, neu, log = lb.run(c, {}, {"format": 1, "haupt": HAUPT, "zuordnung": {"oil-brent": A1}},
                          lauf(f"{TAG} 11:01").to_pydatetime(), bot=ub.US500)
    assert not abrufe and not c.orders and "wartet" in st["status"]


def test_kurze_stundenhistorie_wird_mit_tageskerzen_ergaenzt():
    """Reichen die Stundenkerzen nur 60 Tage zurück, kommen die älteren Tage aus den Tageskerzen; das Signal bleibt."""
    bars = stunden(RUECKSETZER, TAG)
    T_voll = ub.tageskerzen(bars)
    kurz = bars[bars.index >= bars.index[-24 * 60]]
    tage = T_voll.datum[:-59]                                   # der erste Stundentag kommt aus der Tageskerze
    day = [{"snapshotTimeUTC": f"{d}T00:00:00", "openPrice": {"bid": o, "ask": o}, "highPrice": {"bid": h, "ask": h},
            "lowPrice": {"bid": l, "ask": l}, "closePrice": {"bid": c, "ask": c}}
           for d, o, h, l, c in zip(tage, T_voll.o, T_voll.h, T_voll.l, T_voll.c)]

    class C:
        def _get(self, path, **p):
            if p["resolution"] == "DAY":
                return {"prices": day}
            von, bis = pd.Timestamp(p["from"]), pd.Timestamp(p["to"])
            teil = kurz[(kurz.index >= von) & (kurz.index < bis)]
            return {"prices": [{"snapshotTimeUTC": t.strftime("%Y-%m-%dT%H:%M:%S"), "openPrice": {"bid": r.open},
                                "highPrice": {"bid": r.high}, "lowPrice": {"bid": r.low}, "closePrice": {"bid": r.close}}
                               for t, r in zip(teil.index, teil.itertuples(index=False))]}

    jetzt = lauf(f"{TAG} 15:01")
    erg = ub.hole_stunden(C(), jetzt, {})
    T = ub.tageskerzen(erg[erg.index < ub.schnitt_utc(jetzt)])
    assert len(T.c) == len(T_voll.c) and abs(r5.sma(T.c, 200)[-1] - r5.sma(T_voll.c, 200)[-1]) < 1e-6
    d = ub.entscheide(erg, jetzt, {})
    assert d["action"] == "open" and d["side"] == 1


def test_letzte_entscheidungszeit_und_probe():
    assert ub.letzte_entscheidungszeit(lauf("2026-11-04 15:30")) == lauf("2026-11-04 15:01")
    assert ub.letzte_entscheidungszeit(lauf("2026-11-04 10:00")) == lauf("2026-11-03 15:01")
    assert ub.letzte_entscheidungszeit(lauf("2026-11-09 09:00")) == lauf("2026-11-06 15:01")     # Montag früh -> Freitag
    c = US500Client(stunden(RUECKSETZER, TAG))
    p = ub.probe(c, lauf(f"{TAG} 20:00"))
    assert p["entscheidung"]["action"] == "open" and p["tageskerzen"] == len(RUECKSETZER) and not c.orders


def test_us100_und_dow_handeln_nur_auf_dem_zugeordneten_konto_mit_eigenem_markt():
    """Bewertung 2025-2026 (suche/VORAB_bewertung.yaml): dieselbe Regel auf US100 und US30, nur mit Zuordnung."""
    class US100Client(US500Client):
        def _get(self, path, **params):
            assert path == "/prices/US100" and params["resolution"] == "HOUR"
            return {"prices": self.prices("US100")}

    c = US100Client(stunden(RUECKSETZER, TAG), {HAUPT: "Account", A1: "Account 4", NEU: "US500"})
    # ohne Zuordnung: kein Konto (Name passt nie), keine Order
    st, _, _ = lb.run(c, {}, {"format": 1, "haupt": HAUPT, "zuordnung": {}}, lauf(f"{TAG} 15:01").to_pydatetime(),
                      bot=ub.US100)
    assert not c.orders and st.get("konto") is None
    # mit Zuordnung (Konto eines abgelösten Bots): Order auf US100 genau dort
    k = {"format": 1, "haupt": HAUPT, "zuordnung": {"r5-ruecksetzer-us100": A1}}
    st, _, _ = lb.run(c, {}, k, lauf(f"{TAG} 15:01").to_pydatetime(), bot=ub.US100)
    assert len(c.orders) == 1 and c.orders[0][0] == A1 and c.orders[0][1]["epic"] == "US100"
    assert ub.US100.jdir.name == "us100-ruecksetzer" and ub.US30.epic == "US30"
    assert {b.bot_id for b in ub.WEITERE} == {"r5-ruecksetzer-us100", "r5-ruecksetzer-us30"}


def test_abgeloester_bot_oeffnet_nichts_und_gibt_das_leere_konto_ab():
    """Prüfung nach 15/40 Demo-Trades (suche/VORAB_wechsel.yaml): abgelöst heißt keine neue Order; ist das Konto leer,
    geht es an den Nachfolger (oder wird frei), und danach sucht der Bot kein Konto mehr."""
    c = US500Client(stunden(RUECKSETZER, TAG), {HAUPT: "Account", A1: "US500"})
    k = {"format": 1, "haupt": HAUPT, "zuordnung": {ub.BOT_ID: A1},
         "abgeloest": {ub.BOT_ID: {"an": "nachfolger", "grund": "Test"}}}
    st, _, log = lb.run(c, {}, k, lauf(f"{TAG} 15:01").to_pydatetime(), bot=ub.US500)
    assert not c.orders and k["zuordnung"] == {"nachfolger": A1} and st["konto_id"] is None
    assert st["status"].startswith("abgelöst, Konto an nachfolger") and any(e["event"] == "konto übergeben" for e in log)
    st, _, _ = lb.run(c, st, k, lauf(f"{TAG} 15:16").to_pydatetime(), bot=ub.US500)
    assert not c.orders and k["zuordnung"] == {"nachfolger": A1}
    k2 = {"format": 1, "haupt": HAUPT, "zuordnung": {ub.BOT_ID: A1}, "abgeloest": {ub.BOT_ID: {"an": None}}}
    vorher = lb._stand(k2)
    lb.run(c, {}, k2, lauf(f"{TAG} 15:01").to_pydatetime(), bot=ub.US500)
    assert not c.orders and k2["zuordnung"] == {} and k2["frei"] == [A1]
    assert lb._stand(k2) != vorher            # wird gespeichert, obwohl der Bot jetzt kein Konto mehr hat (Fehler 04.11.)


class US100Client(US500Client):
    def _get(self, path, **params):
        assert path == "/prices/US100" and params["resolution"] == "HOUR"
        return {"prices": self.prices("US100")}


def _kombi_k(**extra):
    return {"format": 1, "haupt": HAUPT, "zuordnung": {"us500-ruecksetzer": NEU, "r5-ruecksetzer-us100": A1}, **extra}


def test_kombi_bot_zieht_ohne_position_ins_konto_des_ankers_und_gibt_sein_konto_frei():
    """suche/kombi.yaml (Kiron 04.11.2026: die besten 3 auf einem Demokonto)."""
    c = US100Client(stunden(RUECKSETZER, TAG), {HAUPT: "Account", A1: "Account 3", NEU: "US500"})
    k = _kombi_k()
    st, _, log = lb.run(c, {}, k, lauf(f"{TAG} 15:01").to_pydatetime(), bot=ub.US100)
    assert k["zuordnung"]["r5-ruecksetzer-us100"] == NEU and k["frei"] == [A1]
    assert any(e["event"] == "ins gemeinsame Konto umgezogen" for e in log)
    assert len(c.orders) == 1 and c.orders[0][0] == NEU and k["deals"] == {"D1": "r5-ruecksetzer-us100"}


def test_kombi_bot_mit_offener_position_bleibt_bis_sie_zu_ist_und_oeffnet_nichts():
    c = US100Client(stunden(RUECKSETZER, TAG), {HAUPT: "Account", A1: "Account 3", NEU: "US500"})
    c.pos[A1] = [{"market": {"epic": "US100"}, "position": {"dealId": "X1", "direction": "BUY", "level": 20000}}]
    st0 = {"open": {"dealId": "X1", "side": 1, "tag": "2026-11-03", "entry": 20000, "stop_dist": 600, "size": 0.01,
                    "lot": 1, "opened_utc": "2026-11-03T20:00:00"}}
    k = _kombi_k()
    st, _, _ = lb.run(c, st0, k, lauf(f"{TAG} 15:01").to_pydatetime(), bot=ub.US100)
    assert k["zuordnung"]["r5-ruecksetzer-us100"] == A1 and not k.get("frei") and not c.orders


def test_kombi_position_der_anderen_strategie_ist_nicht_fremd_aber_gegenposition_wird_nicht_eroeffnet():
    c = US100Client(stunden(RUECKSETZER, TAG), {HAUPT: "Account", A1: "Account 3", NEU: "US500"})
    k = _kombi_k(deals={"N1": "r7-nasdaq-noise-long"})
    k["zuordnung"]["r5-ruecksetzer-us100"] = NEU
    c.pos[NEU] = [{"market": {"epic": "US100"}, "position": {"dealId": "N1", "direction": "SELL", "level": 20000}}]
    st, _, log = lb.run(c, {}, k, lauf(f"{TAG} 15:01").to_pydatetime(), bot=ub.US100)
    assert not c.orders and st.get("open") is None
    assert any("Gegenposition" in " ".join(e.get("why") or []) for e in log)
    c.pos[NEU][0]["position"]["direction"] = "BUY"                   # gleiche Richtung: zwei getrennte Positionen
    st, _, _ = lb.run(c, {}, k, lauf(f"{TAG} 15:01").to_pydatetime(), bot=ub.US100)
    assert len(c.orders) == 1 and c.orders[0][0] == NEU and st["open"]["dealId"] != "N1"


def test_abgeloester_kombi_bot_verlaesst_nur_das_gemeinsame_konto():
    c = US100Client(stunden(RUECKSETZER, TAG), {HAUPT: "Account", A1: "Account 3", NEU: "US500"})
    k = _kombi_k(abgeloest={"r5-ruecksetzer-us100": {"an": None}}, deals={"U1": "us500-ruecksetzer"})
    k["zuordnung"]["r5-ruecksetzer-us100"] = NEU
    c.pos[NEU] = [{"market": {"epic": "US500"}, "position": {"dealId": "U1", "direction": "BUY", "level": 5000}}]
    lb.run(c, {}, k, lauf(f"{TAG} 15:01").to_pydatetime(), bot=ub.US100)
    assert k["zuordnung"] == {"us500-ruecksetzer": NEU} and not k.get("frei") and not c.orders
