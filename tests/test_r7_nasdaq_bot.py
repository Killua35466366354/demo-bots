"""Tests für suche/r7_nasdaq_bot.py: Noise-Band nur Long auf dem Nasdaq (Kalender, Band, Einstiege, Ausstieg nach 5
Handelstagen, Lauf auf einem eigenen Demokonto mit dem Namen "Nasdaq", nie auf einem Ersatzkonto)."""
import bisect

import numpy as np
import pandas as pd

from suche import london_bot as lb
from suche import r7_nasdaq_bot as nb
from test_london_bot import A1, HAUPT, NEU, FakeClient

NY = "America/New_York"
TAG = "2026-11-04"                       # Mittwoch, Winterzeit (New York = UTC - 5)


def utc(ny: str) -> pd.Timestamp:
    return pd.Timestamp(ny, tz=NY).tz_convert("UTC").tz_localize(None)


def kerzen(tage: int, bis: str, heute: list | None = None) -> pd.DataFrame:
    """15-Minuten-Bid-Kerzen an `tage` Werktagen bis zum Vortag von `bis` (18:00 New York am Vorabend bis 17:00), Kurs
    20000. In der Sitzung steigt der Kurs ab der ersten Kerze auf 20020 (+0,1 %), danach zurück. Spanne je Kerze 50,
    in den letzten 14 Tagen 20 (Markt ruhiger als sonst). `heute`: Schlusskurse der Sitzung am Tag `bis` ab 9:30."""
    rows, idx = [], []
    tage_l = list(pd.bdate_range(end=pd.Timestamp(bis) - pd.Timedelta(days=1), periods=tage))
    for j, d in enumerate(tage_l):
        r = 10.0 if j >= tage - 14 else 25.0
        start = pd.Timestamp(d.date(), tz=NY) - pd.Timedelta(hours=6)
        for q in range(92):
            t = start + pd.Timedelta(minutes=15 * q)
            m = t.hour * 60 + t.minute
            c = 20020.0 if 9 * 60 + 30 <= m < 16 * 60 else 20000.0
            o = rows[-1][3] if rows else 20000.0
            if m == 9 * 60 + 30:
                o = 20000.0
            idx.append(t)
            rows.append((o, max(o, c) + r, min(o, c) - r, c))
    if heute:
        start = pd.Timestamp(bis, tz=NY) - pd.Timedelta(hours=6)
        for q in range(62 + len(heute)):
            t = start + pd.Timedelta(minutes=15 * q)
            k = q - 62
            c = heute[k] if k >= 0 else 20000.0
            o = 20000.0 if k <= 0 else heute[k - 1]
            idx.append(t)
            rows.append((o, max(o, c) + 10, min(o, c) - 10, c))
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"],
                        index=pd.DatetimeIndex(idx).tz_convert("UTC").tz_localize(None))


def stunden_aus(b: pd.DataFrame) -> pd.DataFrame:
    return b.resample("60min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


def preise(b: pd.DataFrame) -> list[dict]:
    return [{"snapshotTimeUTC": t.strftime("%Y-%m-%dT%H:%M:%S"),
             "openPrice": {"bid": r.open, "ask": r.open + 1}, "highPrice": {"bid": r.high, "ask": r.high + 1},
             "lowPrice": {"bid": r.low, "ask": r.low + 1}, "closePrice": {"bid": r.close, "ask": r.close + 1}}
            for t, r in zip(b.index, b.itertuples(index=False))]


class NasdaqClient(FakeClient):
    def __init__(self, b15: pd.DataFrame, namen: dict | None = None):
        super().__init__(b15, namen)
        self.reihen = {"MINUTE_15": preise(b15), "HOUR": preise(stunden_aus(b15))}
        self.abrufe = []

    def market(self, epic):
        if epic == "EURUSD":
            return {"snapshot": {"bid": 1.08, "offer": 1.08}, "instrument": {}, "dealingRules": {}}
        last = float(self.bars["close"].iloc[-1])
        return {"snapshot": {"bid": last, "offer": last + 1.8, "marketStatus": "TRADEABLE", "decimalPlacesFactor": 1},
                "instrument": {"currency": "USD", "lotSize": 1, "marginFactor": 5, "marginFactorUnit": "PERCENTAGE"},
                "dealingRules": {"minDealSize": {"value": 0.001}, "minSizeIncrement": {"value": 0.001},
                                 "minStopOrProfitDistance": {"unit": "PERCENTAGE", "value": 0.01}}}

    def _get(self, path, **p):
        assert path == "/prices/US100"
        self.abrufe.append(p["resolution"])
        reihe = self.reihen[p["resolution"]]
        zeiten = [x["snapshotTimeUTC"] for x in reihe]
        a, z = bisect.bisect_left(zeiten, p["from"]), bisect.bisect_right(zeiten, p["to"])
        return {"prices": reihe[a:z][-1000:]}


# --------------------------------------------------------------------------------------------------------------------
# Kalender

def test_feiertage_und_kurze_tage():
    assert {"2026-12-25", "2026-04-03", "2026-01-01"} <= nb.frei_tage(2026)
    assert {"2027-12-24", "2027-03-26"} <= nb.frei_tage(2027)          # Weihnachten am Samstag -> Freitag frei
    assert "2027-12-31" not in nb.frei_tage(2027) and "2027-12-31" not in nb.frei_tage(2028)   # Neujahr 2028 Samstag
    assert {"2022-12-26", "2023-01-02"} <= nb.frei_tage(2022) | nb.frei_tage(2023)              # am Sonntag -> Montag
    kurz = nb.kurztage(2026)
    for d in ("2026-01-19", "2026-02-16", "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26",
              "2026-11-27", "2026-12-24"):
        assert d in kurz, d
    assert TAG not in kurz and "2026-11-25" not in kurz
    assert nb.ist_handelstag("2026-11-26") and not nb.ist_handelstag("2026-12-25") and not nb.ist_handelstag("2026-11-07")


def test_fuenfter_handelstag_und_ausstiegszeit():
    assert nb.handelstage_nach(TAG, 5) == "2026-11-10"
    assert nb.handelstage_nach("2026-12-22", 5) == "2026-12-29"            # 25.12. zählt nicht
    assert nb.handelstage_nach("2026-11-20", 5) == "2026-11-26"            # Thanksgiving zählt (Kerzen bis 13 Uhr)
    op = {"tag": TAG}
    assert not nb.faellig(op, utc("2026-11-10 15:59")) and nb.faellig(op, utc("2026-11-10 16:01"))
    assert nb.faellig(op, utc("2026-11-11 10:01"))
    op = {"tag": "2026-11-20"}
    assert not nb.faellig(op, utc("2026-11-26 12:31")) and nb.faellig(op, utc("2026-11-26 12:46"))


# --------------------------------------------------------------------------------------------------------------------
# Band, Tagesplan, Einstiege

def test_sitzungen_nur_vollstaendig_und_band():
    b = kerzen(20, TAG)
    s = nb.sitzungen(b)
    assert len(s) == 20 and all(len(i) == 26 for _, i in s)
    ohne = b.drop(index=[utc("2026-11-03 09:30")])                     # erste Kerze fehlt: Tag zählt nicht
    assert "2026-11-03" not in {t for t, _ in nb.sitzungen(ohne)}
    bd = nb.band(b, TAG)
    assert len(bd["sig"]) == 24 and np.allclose(bd["sig"], 0.001) and bd["vorschluss"] == 20020.0
    assert bd["letzte_sitzung"] == "2026-11-03"
    assert "zu wenig" in nb.band(kerzen(14, TAG), TAG)["why"]


def test_tagesplan_bedingung_ruhiger_markt():
    b = kerzen(130, TAG)
    p = nb.tagesplan(b, stunden_aus(b), TAG)
    assert p["ok"] and p["schwankung"] < nb.SCHWANKUNG_MAX and p["atr_bis"] == "2026-11-03"
    laut = b.copy()
    laut["high"] += np.where(laut.index > utc("2026-10-15 00:00"), 60, 0)  # zuletzt mehr Schwankung als sonst
    p = nb.tagesplan(laut, stunden_aus(laut), TAG)
    assert not p["ok"] and "nicht ruhiger" in p["why"]
    p = nb.tagesplan(b, stunden_aus(b), "2026-11-27")
    assert not p["ok"] and "Feiertag" in p["why"]


def test_einstiege_wie_backtest_mit_wiedereinstieg():
    plan = {"sig": [0.001] * 24, "vorschluss": 20000.0}
    heute = kerzen(1, TAG, [20005, 20010, 20030, 20030, 20030, 20010, 20015, 20050, 20060])
    heute = heute[heute.index >= utc(f"{TAG} 09:30")]
    e = nb.einstiege(plan, heute)
    assert [(x["k"], x["kerze"]) for x in e] == [(3, 4), (7, 8)] and e[0]["oben"] == 20020.0


def test_entscheide_einstieg_nur_in_der_einstiegskerze():
    plan = {"tag": TAG, "ok": True, "sig": [0.001] * 24, "vorschluss": 20000.0, "atr14": 120.0}
    heute = kerzen(1, TAG, [20005, 20010, 20030, 20030])
    heute = heute[heute.index >= utc(f"{TAG} 09:30")]
    heute.attrs["plan"] = plan
    d = nb.entscheide(heute, utc(f"{TAG} 10:31"), {})
    assert d["action"] == "open" and d["side"] == 1 and d["stop_dist"] == 600.0
    assert d["signal_bar"] == str(utc(f"{TAG} 10:15"))
    d = nb.entscheide(heute, utc(f"{TAG} 10:46"), {})
    assert d["action"] == "none" and not d.get("erledigt")                 # verpasst, aber später wieder möglich
    assert nb.entscheide(heute, utc(f"{TAG} 15:16"), {})["erledigt"]
    assert nb.entscheide(heute, utc(f"{TAG} 09:46"), {})["action"] == "none"
    zu = pd.DataFrame(columns=heute.columns)
    zu.attrs["plan"] = {"tag": TAG, "ok": False, "why": "Markt nicht ruhiger als sonst"}
    d = nb.entscheide(zu, utc(f"{TAG} 10:01"), {})
    assert d["action"] == "none" and d["erledigt"]
    op = {"tag": TAG}
    assert nb.entscheide(zu, utc("2026-11-09 16:01"), {"open": op})["action"] == "none"
    assert nb.entscheide(zu, utc("2026-11-10 16:01"), {"open": op})["action"] == "close"


# --------------------------------------------------------------------------------------------------------------------
# Lauf mit Demokonten

def test_lauf_nimmt_nur_das_konto_nasdaq():
    b = kerzen(130, TAG, [20010, 20060])
    c = NasdaqClient(b, {HAUPT: "Account", A1: "Account 1", NEU: "Account 8"})
    k = {"format": 1, "haupt": HAUPT, "zuordnung": {"oil-brent": A1}}
    st, neu, log = lb.run(c, {}, k, utc(f"{TAG} 10:01").to_pydatetime(), bot=nb.NASDAQ)
    assert nb.BOT_ID not in k["zuordnung"] and not c.orders and "Nasdaq" in st["status"]
    c = NasdaqClient(b, {HAUPT: "Account", A1: "Account 1", NEU: "Noise USDJPY"})
    st, neu, log = lb.run(c, {}, k, utc(f"{TAG} 10:01").to_pydatetime(), bot=nb.NASDAQ)
    assert nb.BOT_ID not in k["zuordnung"] and not c.orders


def test_lauf_oeffnet_long_mit_notstop_ohne_ziel_und_kehrt_zurueck():
    b = kerzen(130, TAG, [20010, 20060])
    c = NasdaqClient(b, {HAUPT: "Account", A1: "Account 1", NEU: "Nasdaq"})
    k = {"format": 1, "haupt": HAUPT, "zuordnung": {"oil-brent": A1}}
    st, neu, log = lb.run(c, {}, k, utc(f"{TAG} 10:01").to_pydatetime(), bot=nb.NASDAQ)
    assert k["zuordnung"][nb.BOT_ID] == NEU and len(c.orders) == 1 and c.orders[0][0] == NEU
    body = c.orders[0][1]
    assert body["epic"] == "US100" and body["direction"] == "BUY" and body["size"] == 0.001
    assert "profitDistance" not in body and body["stopDistance"] == round(5 * st["plan"]["atr14"], 1)
    assert st["plan"]["ok"] and st["open"]["tag"] == TAG and c.account_id == HAUPT
    # Später: Position bleibt, keine Kerzen mehr nötig; am 5. Handelstag um 16 Uhr raus
    c.abrufe.clear()
    st, neu, log = lb.run(c, st, k, utc("2026-11-09 16:01").to_pydatetime(), bot=nb.NASDAQ)
    assert not c.abrufe and not c.closed and st["status"] == "Position offen"
    st, neu, log = lb.run(c, st, k, utc("2026-11-10 16:01").to_pydatetime(), bot=nb.NASDAQ)
    assert c.closed and len(neu) == 1 and neu[0]["reason"] == "5. Handelstag erreicht" and st["open"] is None


def test_lauf_ausserhalb_des_fensters_holt_keine_kerzen():
    b = kerzen(130, TAG)
    for zeit in (f"{TAG} 09:46", f"{TAG} 15:16", "2026-11-07 12:01"):
        c = NasdaqClient(b, {HAUPT: "Account", A1: "Account 1", NEU: "Nasdaq"})
        st, neu, log = lb.run(c, {}, {"format": 1, "haupt": HAUPT, "zuordnung": {"oil-brent": A1}},
                              utc(zeit).to_pydatetime(), bot=nb.NASDAQ)
        assert not c.abrufe and not c.orders, zeit


def test_tagesplan_einmal_am_tag():
    b = kerzen(130, TAG, [20010, 20020, 20015, 20018])
    c = NasdaqClient(b, {HAUPT: "Account", A1: "Account 1", NEU: "Nasdaq"})
    k = {"format": 1, "haupt": HAUPT, "zuordnung": {"oil-brent": A1}}
    st, _, _ = lb.run(c, {}, k, utc(f"{TAG} 10:01").to_pydatetime(), bot=nb.NASDAQ)
    n = len(c.abrufe)
    assert "HOUR" in c.abrufe and not c.orders
    st, _, _ = lb.run(c, st, k, utc(f"{TAG} 10:31").to_pydatetime(), bot=nb.NASDAQ)
    assert c.abrufe[n:] == ["MINUTE_15"] and not c.orders


def test_vorab_festgelegt():
    import hashlib
    from suche.runde1 import journal_lines, last_value
    text = (lb.ROOT / "suche" / "VORAB_r7_nasdaq.yaml").read_text(encoding="utf-8")
    assert last_value(journal_lines(), "VORAB_r7_nasdaq sha256 ") == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_cockpit_karte_mit_kontoname_und_urteil(tmp_path):
    import json
    p = tmp_path / "r7-nasdaq-bot.json"
    p.write_text(json.dumps({"status": "wartet auf ein eigenes Demokonto mit „Nasdaq“ im Namen", "regel": "x"}),
                 encoding="utf-8")
    nb.cockpit_ergaenzen(p)
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["konto_vorschlag"] == "Nasdaq" and d["vorab"]["urteil"]["nach_trades"] == 40
    assert d["status"].startswith("wartet auf ein eigenes Demokonto")
