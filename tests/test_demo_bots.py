"""Tests für suche/demo_bots.py: Demo-Bots der Strategie-Suche Runde 3 (nur Demokonto)."""
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from gold.backtest.sizing import atr_rma
from gold.v2.fuehrung import Markt
from suche import demo_bots as db
from suche.runde3 import Prepared

R3 = yaml.safe_load(Path("suche/VORAB_runde3.yaml").read_text(encoding="utf-8"))["runde_3"]
CFG = {"aktiv": True, "handelstage": 4, "reserve_margin_eur": 400, "max_risiko_eur": 10, "max_tagesverlust_r": 6,
       "bots": [{"id": "t-EURUSD", "epic": "EURUSD", "name": "EUR/USD", "typ": "CURRENCIES", "zeitrahmen": "15min",
                 "logik": "gold", "seiten": "C+B"}]}


def bars_until(end: str, n: int = 400, tf: str = "15min", start_px: float = 1.10) -> pd.DataFrame:
    idx = pd.date_range(end=pd.Timestamp(end), periods=n, freq=tf)
    rng = np.random.default_rng(1)
    c = start_px + np.cumsum(rng.normal(0, 0.0005, n))
    return pd.DataFrame({"open": c, "high": c + 0.0008, "low": c - 0.0008, "close": c}, index=idx)


def stub_prepare(signal: dict):
    """prepare-Ersatz: echte Markt-Arrays, aber Einstiege und Ausstiegssignale nach Wunsch (Zeit -> Art)."""
    def fake(B, S, hourly, tf, events, nw):
        n = len(B)
        el, es = np.zeros(n, bool), np.zeros(n, bool)
        lx, sx = np.zeros(n, bool), np.zeros(n, bool)
        for t, kind in signal.items():
            if pd.Timestamp(t) in B.index:
                k = B.index.get_loc(pd.Timestamp(t))
                {"long": el, "short": es, "long_exit": lx, "short_exit": sx}[kind][k] = True
        sc = pd.DataFrame({"exit": lx}, index=B.index)
        sb = pd.DataFrame({"exit": sx}, index=B.index)
        m = Markt.build(B, S, atr_rma(B), sc, sb, np.zeros(n, int), np.full(n, np.nan), np.zeros(n, bool))
        return Prepared(tf, B, m, {"gold": (el, es), "gold2": (el, es)}, {"gold": (el, es), "gold2": (el, es)})
    return fake


def quote(**kw) -> db.Quote:
    base = dict(bid=1.1, offer=1.1001, tradeable=True, currency="USD", lot=1.0, min_size=100.0, size_step=100.0,
                margin_pct=3.33, decimals=5, min_dist=0.0, eur_rate=1.16)
    base.update(kw)
    return db.Quote(**base)


def test_end_after_skips_the_weekend():
    assert db.end_after(pd.Timestamp("2026-11-03 08:11"), 4) == pd.Timestamp("2026-11-09 08:11")   # Di -> Mo
    assert db.end_after(pd.Timestamp("2026-11-07 10:00"), 4) == pd.Timestamp("2026-11-12 10:00")   # Sa -> Do


def test_frame_uses_open_spread_and_drops_the_running_bar():
    prices = [{"snapshotTimeUTC": f"2026-11-03T10:{m:02d}:00", "openPrice": {"bid": 1.0, "ask": 1.0002},
               "highPrice": {"bid": 1.1, "ask": 1.1002}, "lowPrice": {"bid": 0.9, "ask": 0.9002},
               "closePrice": {"bid": 1.05, "ask": 1.0505}} for m in (0, 15, 30)]
    bars, sp = db.only_closed(*db.frame(prices), pd.Timestamp("2026-11-03 10:44"), "15min")
    assert list(bars.index.minute) == [0, 15] and sp.iloc[0] == pytest.approx(0.0002)


def test_decide_opens_on_a_signal_of_the_bar_that_just_closed(monkeypatch):
    bars = bars_until("2026-11-03 10:30")
    monkeypatch.setattr(db, "prepare", stub_prepare({"2026-11-03 10:30": "long", "2026-11-03 10:00": "short"}))
    d = db.decide(CFG["bots"][0], R3, bars, pd.Series(0.0001, index=bars.index), bars, quote(), {},
                  pd.Timestamp("2026-11-03 10:46"), pd.Series(dtype="datetime64[ns]"))
    assert d["action"] == "open" and d["side"] == 1 and d["t_sig"] == "2026-11-03 10:30:00"
    assert d["stop_dist"] == pytest.approx(d["atr"]) and d["tp_dist"] is None      # gold: Stop 1 x ATR, kein Ziel


def test_decide_respects_the_side_setting(monkeypatch):
    bars = bars_until("2026-11-03 10:30")
    monkeypatch.setattr(db, "prepare", stub_prepare({"2026-11-03 10:30": "short"}))
    bot = {**CFG["bots"][0], "seiten": "nur C"}
    d = db.decide(bot, R3, bars, pd.Series(0.0001, index=bars.index), bars, quote(), {},
                  pd.Timestamp("2026-11-03 10:46"), pd.Series(dtype="datetime64[ns]"))
    assert d["action"] == "none"


def test_decide_closes_on_the_own_exit_signal(monkeypatch):
    bars = bars_until("2026-11-03 11:30")
    monkeypatch.setattr(db, "prepare", stub_prepare({"2026-11-03 11:30": "long_exit"}))
    sb = {"open": {"side": 1, "t_sig": "2026-11-03 10:30:00", "dealId": "D1"}}
    q = quote(bid=float(bars["close"].iloc[-1]), offer=float(bars["close"].iloc[-1]) + 0.0001)
    d = db.decide(CFG["bots"][0], R3, bars, pd.Series(0.0001, index=bars.index), bars, q, sb,
                  pd.Timestamp("2026-11-03 11:46"), pd.Series(dtype="datetime64[ns]"))
    assert d["action"] == "close" and d["reason"] == "signal"


def test_decide_holds_while_nothing_happens(monkeypatch):
    bars = bars_until("2026-11-03 11:30")
    monkeypatch.setattr(db, "prepare", stub_prepare({}))
    sb = {"open": {"side": 1, "t_sig": "2026-11-03 11:15:00", "dealId": "D1"}}
    last = float(bars["close"].iloc[-1])
    d = db.decide(CFG["bots"][0], R3, bars, pd.Series(0.0, index=bars.index), bars, quote(bid=last, offer=last), sb,
                  pd.Timestamp("2026-11-03 11:46"), pd.Series(dtype="datetime64[ns]"))
    assert d["action"] == "none"


def test_guards_protect_the_gold_bot_and_the_account():
    d = {"side": 1, "stop_dist": 0.0010, "tp_dist": None}
    now, ende = pd.Timestamp("2026-11-03 11:00"), pd.Timestamp("2026-11-09 11:00")
    why, order = db.guards(d, quote(), CFG, 1000.0, 0.0, now, ende)
    assert why == [] and order["size"] == 100.0 and order["risk_eur"] < 1
    assert any("Margin" in w for w in db.guards(d, quote(), CFG, 401.0, 0.0, now, ende)[0])
    assert any("im Minus" in w for w in db.guards(d, quote(), CFG, 1000.0, -6.0, now, ende)[0])
    assert any("Risiko" in w for w in db.guards({**d, "stop_dist": 1.0}, quote(), CFG, 1000.0, 0.0, now, ende)[0])
    assert any("Umrechnungskurs" in w for w in db.guards(d, quote(eur_rate=None), CFG, 1000.0, 0.0, now, ende)[0])
    assert any("Testzeit" in w for w in db.guards(d, quote(), CFG, 1000.0, 0.0, ende, ende)[0])
    # Mindestabstand des Brokers: Stop wird breiter und das steht dabei
    _, o2 = db.guards(d, quote(min_dist=0.002), CFG, 1000.0, 0.0, now, ende)
    assert o2["stop_dist"] == pytest.approx(0.0021) and o2["stop_breiter"]


class FakeClient:
    """Demokonto im Kleinen: Kerzen, Märkte, Positionen, Orders. Merkt sich jede Order."""
    environment = "demo"

    def __init__(self, bars: pd.DataFrame):
        self.bars = bars
        self.positions_ = []
        self.orders, self.closed = [], []
        self.acts = {}

    def login(self):
        pass

    def logout(self):
        pass

    def accounts(self):
        return [{"preferred": True, "currency": "EUR", "balance": {"balance": 1000.0, "available": 1000.0}}]

    def positions(self):
        return list(self.positions_)

    def market(self, epic):
        last = float(self.bars["close"].iloc[-1])
        return {"snapshot": {"bid": last, "offer": last + 0.0001, "marketStatus": "TRADEABLE", "decimalPlacesFactor": 5},
                "instrument": {"currency": "USD", "lotSize": 1,
                               "marginFactor": 3.33, "marginFactorUnit": "PERCENTAGE"},
                "dealingRules": {"minDealSize": {"value": 100}, "minSizeIncrement": {"value": 100}}}

    def prices(self, epic, resolution="HOUR", max_bars=1000):
        return self._prices(self.bars)

    def _prices(self, bars):
        return [{"snapshotTimeUTC": t.strftime("%Y-%m-%dT%H:%M:%S"),
                 "openPrice": {"bid": r.open, "ask": r.open + 0.0001}, "highPrice": {"bid": r.high, "ask": r.high + 0.0001},
                 "lowPrice": {"bid": r.low, "ask": r.low + 0.0001}, "closePrice": {"bid": r.close, "ask": r.close + 0.0001}}
                for t, r in zip(bars.index, bars.itertuples(index=False))]

    def _get(self, path, **params):
        return {"prices": []}

    def _request(self, method, path, **kw):
        assert method == "POST" and path == "/positions"
        body = kw["json"]
        self.orders.append(body)
        last = float(self.bars["close"].iloc[-1])
        self.positions_.append({"market": {"epic": body["epic"]},
                                "position": {"dealId": f"D{len(self.orders)}", "direction": body["direction"],
                                             "level": last + 0.0001, "size": body["size"], "upl": 0.0,
                                             "createdDateUTC": "2026-11-03T10:46:01"}})

        class R:
            @staticmethod
            def json():
                return {"dealReference": "ref"}
        return R()

    def confirm(self, ref):
        return {"dealStatus": "ACCEPTED", "level": float(self.bars["close"].iloc[-1]) + 0.0001}

    def close_position(self, deal_id):
        self.closed.append(deal_id)
        self.positions_ = [p for p in self.positions_ if p["position"]["dealId"] != deal_id]
        return {"dealStatus": "ACCEPTED", "level": float(self.bars["close"].iloc[-1])}

    def activity(self, deal_id, since, until):
        return self.acts.get(deal_id, [])


def test_full_cycle_open_broker_stop_and_test_end(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "JDIR", tmp_path)
    bars = bars_until("2026-11-03 10:30", n=600)
    monkeypatch.setattr(db, "prepare", stub_prepare({"2026-11-03 10:30": "long"}))
    monkeypatch.setattr(db, "fetch", lambda client, epic, tf: (client._prices(client.bars), client._prices(client.bars)))
    c = FakeClient(bars)
    now = datetime(2026, 11, 3, 10, 46, tzinfo=timezone.utc)
    st, trades, log = db.run(c, CFG, R3, {}, now)
    assert len(c.orders) == 1 and c.orders[0]["direction"] == "BUY" and "stopDistance" in c.orders[0]
    assert "profitDistance" not in c.orders[0]                          # Logik gold hat kein Ziel
    assert st["bots"]["t-EURUSD"]["open"]["dealId"] == "D1" and st["ende_utc"] == "2026-11-09T10:46:00"
    # gleicher Lauf noch einmal in derselben Kerze: nichts Neues
    st2, trades2, _ = db.run(c, CFG, R3, st, datetime(2026, 11, 3, 10, 50, tzinfo=timezone.utc))
    assert len(c.orders) == 1 and not trades2
    # Broker-Stop löst aus: Position weg, Schlusskurs aus der Kontoaktivität
    c.positions_ = []
    entry = st["bots"]["t-EURUSD"]["open"]["entry"]
    stop_px = entry - st["bots"]["t-EURUSD"]["open"]["stop_dist"]
    c.acts["D1"] = [{"source": "SL", "details": {"level": stop_px, "actions": [{"actionType": "POSITION_CLOSED"}]}}]
    c.bars = bars_until("2026-11-03 10:45", n=601)
    st3, trades3, _ = db.run(c, CFG, R3, st2, datetime(2026, 11, 3, 11, 1, tzinfo=timezone.utc))
    assert len(trades3) == 1 and trades3[0]["r"] == pytest.approx(-1.0, abs=0.01)
    assert trades3[0]["reason"] == "Stop beim Broker" and st3["bots"]["t-EURUSD"].get("open") is None
    # Testende: offene Position wird geschlossen, danach Phase beendet
    st3["bots"]["t-EURUSD"]["open"] = {"dealId": "D9", "side": 1, "t_sig": "2026-11-03 10:30:00", "entry": 1.1,
                                       "stop_dist": 0.001, "tp_dist": None, "size": 100, "opened_utc": "2026-11-03T11:01:00"}
    c.positions_ = [{"market": {"epic": "EURUSD"}, "position": {"dealId": "D9", "direction": "BUY", "level": 1.1}}]
    st4, trades4, _ = db.run(c, CFG, R3, st3, datetime(2026, 11, 9, 11, 0, tzinfo=timezone.utc))
    assert c.closed == ["D9"] and st4["phase"] == "beendet" and trades4[0]["reason"] == "Testende"
    cp = db.cockpit(CFG, st4, trades3 + trades4)
    assert cp["format"] == 1 and cp["bots"][0]["bewertung"] == "zu wenige Trades" and len(cp["trades"]) == 2


def test_dry_run_sends_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "JDIR", tmp_path)
    bars = bars_until("2026-11-03 10:30", n=600)
    monkeypatch.setattr(db, "prepare", stub_prepare({"2026-11-03 10:30": "long"}))
    monkeypatch.setattr(db, "fetch", lambda client, epic, tf: (client._prices(client.bars), client._prices(client.bars)))
    c = FakeClient(bars)
    st, _, log = db.run(c, CFG, R3, {}, datetime(2026, 11, 3, 10, 46, tzinfo=timezone.utc), send_orders=False)
    assert c.orders == [] and any("Trockenlauf" in e["event"] for e in log)


def test_foreign_position_is_never_touched(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "JDIR", tmp_path)
    bars = bars_until("2026-11-03 10:30", n=600)
    monkeypatch.setattr(db, "prepare", stub_prepare({"2026-11-03 10:30": "long"}))
    monkeypatch.setattr(db, "fetch", lambda client, epic, tf: (client._prices(client.bars), client._prices(client.bars)))
    c = FakeClient(bars)
    c.positions_ = [{"market": {"epic": "EURUSD"}, "position": {"dealId": "KIRON", "direction": "SELL", "level": 1.1}}]
    st, _, _ = db.run(c, CFG, R3, {}, datetime(2026, 11, 3, 10, 46, tzinfo=timezone.utc))
    assert c.orders == [] and c.closed == [] and "fremde" in st["bots"]["t-EURUSD"]["status"]


def test_demo_only_and_config_rules():
    src = Path("suche/demo_bots.py").read_text(encoding="utf-8")
    assert 'environment="demo"' in src and "live" not in src.split("def main")[1].split("CapitalClient(")[1][:40]
    cfg = yaml.safe_load(Path("suche/demo_bots.yaml").read_text(encoding="utf-8"))
    epics = [b["epic"] for b in cfg["bots"]]
    assert len(epics) == len(set(epics)) and len(epics) <= R3["regel_demo"]["anzahl"]
    assert not set(epics) & set(R3["regel_demo"]["nie"])
    assert all(b["logik"] in ("gold", "gold2") and b["zeitrahmen"] in db.RES for b in cfg["bots"])


def test_chart_file_has_candles_ema_and_markers(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "JDIR", tmp_path)
    bars = bars_until("2026-11-03 10:30", n=600)
    monkeypatch.setattr(db, "prepare", stub_prepare({"2026-11-03 10:30": "long"}))
    monkeypatch.setattr(db, "fetch", lambda client, epic, tf: (client._prices(client.bars), client._prices(client.bars)))
    c = FakeClient(bars)
    charts = {}
    st, _, _ = db.run(c, CFG, R3, {}, datetime(2026, 11, 3, 10, 46, tzinfo=timezone.utc), charts=charts)
    ser = charts["t-EURUSD"]
    first = pd.Timestamp(ser["kerzen"][0][0])
    assert ser["kerzen"][-1][0] == "2026-11-03 10:30:00" and first >= pd.Timestamp("2026-11-03 10:30") - pd.Timedelta(days=db.CHART_TAGE)
    assert len(ser["kerzen"]) == 600                                     # 600 Viertelstunden = 6,25 Tage, alle drin
    assert len(ser["kerzen"][0]) == 5 and ser["ema200"] and "richtung" not in ser      # Logik gold: keine Richtung
    # offene Position: Einstiegspfeil auf der Signalkerze
    ch = db.chart_file(CFG, st, [], charts)
    b = ch["bots"][0]
    assert ch["format"] == 1 and b["position"]["side"] == "long"
    assert b["marker"] == [{"zeit": "2026-11-03 10:30:00", "art": "einstieg", "side": "long",
                            "preis": st["bots"]["t-EURUSD"]["open"]["entry"], "text": "Long Einstieg (offen)"}]
    # Broker-Stop: Ausstieg nach der letzten fertigen Kerze landet auf der letzten Kerze
    c.positions_ = []
    op = st["bots"]["t-EURUSD"]["open"]
    c.acts["D1"] = [{"source": "SL", "details": {"level": op["entry"] - op["stop_dist"],
                                                  "actions": [{"actionType": "POSITION_CLOSED"}]}}]
    c.bars = bars_until("2026-11-03 10:45", n=601)
    charts2 = {}
    st2, trades, _ = db.run(c, CFG, R3, st, datetime(2026, 11, 3, 11, 1, tzinfo=timezone.utc), charts=charts2)
    b2 = db.chart_file(CFG, st2, trades, charts2)["bots"][0]
    assert b2["position"] is None and [m["art"] for m in b2["marker"]] == ["einstieg", "ausstieg"]
    assert b2["marker"][1]["zeit"] == "2026-11-03 10:45:00" and "-1.00 R" in b2["marker"][1]["text"]
    # Bot ohne neue Kerzen (z. B. Markt zu): Kerzen bleiben aus der alten Datei
    old = db.chart_file(CFG, st2, trades, charts2)
    b3 = db.chart_file(CFG, st2, trades, {}, old)["bots"][0]
    assert b3["kerzen"] == b2["kerzen"] and len(b3["marker"]) == 2
