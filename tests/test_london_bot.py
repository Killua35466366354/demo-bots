"""Tests für suche/london_bot.py: London-Breakout EUR/USD (Entscheidung ohne Netz)."""
import pandas as pd

from suche import london_bot as lb


def tag_bars(datum: str, bis_london: str, ausbruch: dict | None = None, tz: str = "Europe/London") -> pd.DataFrame:
    """15-Minuten-Bid-Kerzen von 0:00 London bis (ohne) `bis_london`, Bereich 1,0990 bis 1,1010. ausbruch: Kerzenbeginn
    London 'HH:MM' -> (hoch, tief) für einzelne Kerzen."""
    start = pd.Timestamp(f"{datum} 00:00", tz=tz)
    ende = pd.Timestamp(f"{datum} {bis_london}", tz=tz)
    idx = pd.date_range(start, ende, freq="15min", inclusive="left")
    df = pd.DataFrame({"open": 1.1, "high": 1.1005, "low": 1.0995, "close": 1.1}, index=idx)
    df.iloc[3, df.columns.get_loc("high")] = 1.1010           # Bereichshoch
    df.iloc[5, df.columns.get_loc("low")] = 1.0990            # Bereichstief
    for hhmm, (h, l) in (ausbruch or {}).items():
        t = pd.Timestamp(f"{datum} {hhmm}", tz=tz)
        df.loc[t, ["high", "low"]] = [h, l]
    df.index = df.index.tz_convert("UTC").tz_localize(None)
    return df


def lauf_nach(datum: str, hhmm: str, tz: str = "Europe/London") -> pd.Timestamp:
    """Laufzeit eine Minute nach Ende der Kerze, die um hhmm London beginnt."""
    return (pd.Timestamp(f"{datum} {hhmm}", tz=tz) + pd.Timedelta(minutes=16)).tz_convert("UTC")


def test_long_breakout_opens_with_range_levels():
    bars = tag_bars("2026-11-04", "10:15", {"10:00": (1.1020, 1.1000)})
    d = lb.entscheide(bars, lauf_nach("2026-11-04", "10:00"), {})
    assert d["action"] == "open" and d["side"] == 1
    assert d["stop_level"] == 1.0990 and abs(d["ziel_level"] - 1.1030) < 1e-12
    assert lb.abstaende(d, bid=1.1018, offer=1.1019) == (1.1019 - 1.0990, 1.1030 - 1.1019)


def test_short_breakout_in_summer_time():
    bars = tag_bars("2026-07-08", "09:00", {"08:45": (1.1000, 1.0980)})
    d = lb.entscheide(bars, lauf_nach("2026-07-08", "08:45"), {})
    assert d["action"] == "open" and d["side"] == -1
    assert d["stop_level"] == 1.1010 and abs(d["ziel_level"] - 1.0970) < 1e-12


def test_missed_breakout_is_not_chased():
    bars = tag_bars("2026-11-04", "11:00", {"10:00": (1.1020, 1.1000)})
    d = lb.entscheide(bars, lauf_nach("2026-11-04", "10:45"), {})
    assert d["action"] == "none" and d.get("erledigt")


def test_both_sides_in_one_bar_means_no_trade():
    bars = tag_bars("2026-11-04", "09:15", {"09:00": (1.1020, 1.0980)})
    d = lb.entscheide(bars, lauf_nach("2026-11-04", "09:00"), {})
    assert d["action"] == "none" and d.get("erledigt")


def test_no_trade_before_8_or_after_late_breakout():
    bars = tag_bars("2026-11-04", "07:45")
    assert lb.entscheide(bars, lauf_nach("2026-11-04", "07:30"), {})["action"] == "none"
    bars = tag_bars("2026-11-04", "16:45", {"16:30": (1.1020, 1.1000)})
    d = lb.entscheide(bars, lauf_nach("2026-11-04", "16:30"), {})
    assert d["action"] == "none" and d.get("erledigt")


def test_one_trade_per_day_and_weekend():
    bars = tag_bars("2026-11-04", "10:15", {"10:00": (1.1020, 1.1000)})
    assert lb.entscheide(bars, lauf_nach("2026-11-04", "10:00"), {"tag_erledigt": "2026-11-04"})["action"] == "none"
    bars = tag_bars("2026-11-07", "10:15", {"10:00": (1.1020, 1.1000)})            # Samstag
    assert lb.entscheide(bars, lauf_nach("2026-11-07", "10:00"), {})["action"] == "none"


def test_short_range_gives_no_trade():
    bars = tag_bars("2026-11-04", "10:15", {"10:00": (1.1020, 1.1000)}).iloc[20:]   # erst ab 5:00 Uhr Kerzen
    d = lb.entscheide(bars, lauf_nach("2026-11-04", "10:00"), {})
    assert d["action"] == "none" and d.get("erledigt")


def test_open_position_closes_at_17_london():
    sb = {"open": {"tag": "2026-11-04", "side": 1}}
    bars = tag_bars("2026-11-04", "17:00")
    assert lb.entscheide(bars, lauf_nach("2026-11-04", "16:30"), sb)["action"] == "none"
    assert lb.entscheide(bars, lauf_nach("2026-11-04", "16:45"), sb)["action"] == "close"


def test_distances_none_when_price_already_past_target():
    d = {"side": 1, "stop_level": 1.0990, "ziel_level": 1.1030}
    assert lb.abstaende(d, bid=1.1031, offer=1.1032) is None


# ---------- Lauf mit einem Demokonto im Kleinen ----------

HAUPT, A1, NEU = "332117868107093150", "332263725196465310", "332264999999999999"


class FakeClient:
    """Drei Demokonten (Hauptkonto, Konto eines anderen Bots, neues Konto), Positionen je Konto, Orders."""
    environment = "demo"

    def __init__(self, bars: pd.DataFrame, konten_namen: dict | None = None):
        self.bars = bars
        self.account_id = HAUPT
        self.namen = konten_namen or {HAUPT: "Account", A1: "Account 1", NEU: "Account 8"}
        self.pos = {aid: [] for aid in self.namen}
        self.orders, self.closed, self.wechsel = [], [], []

    def login(self):
        self.account_id = HAUPT

    def logout(self):
        pass

    def accounts(self):
        return [{"accountId": aid, "accountName": n, "currency": "EUR", "status": "ENABLED",
                 "balance": {"balance": 1000.0, "available": 1000.0}} for aid, n in self.namen.items()]

    def switch_account(self, aid):
        self.account_id = aid
        self.wechsel.append(aid)

    def positions(self):
        return list(self.pos[self.account_id])

    def market(self, epic):
        last = float(self.bars["close"].iloc[-1])
        return {"snapshot": {"bid": last, "offer": last + 0.0001, "marketStatus": "TRADEABLE", "decimalPlacesFactor": 5},
                "instrument": {"currency": "USD", "lotSize": 1, "marginFactor": 3.33, "marginFactorUnit": "PERCENTAGE"},
                "dealingRules": {"minDealSize": {"value": 100}, "minSizeIncrement": {"value": 100}}}

    def prices(self, epic, resolution="HOUR", max_bars=1000):
        return [{"snapshotTimeUTC": t.strftime("%Y-%m-%dT%H:%M:%S"),
                 "openPrice": {"bid": r.open, "ask": r.open + 0.0001}, "highPrice": {"bid": r.high, "ask": r.high + 0.0001},
                 "lowPrice": {"bid": r.low, "ask": r.low + 0.0001}, "closePrice": {"bid": r.close, "ask": r.close + 0.0001}}
                for t, r in zip(self.bars.index, self.bars.itertuples(index=False))]

    def _request(self, method, path, **kw):
        assert method == "POST" and path == "/positions"
        body = kw["json"]
        self.orders.append((self.account_id, body))
        self.pos[self.account_id].append({"market": {"epic": body["epic"]},
                                          "position": {"dealId": f"D{len(self.orders)}", "level": 1.1001,
                                                       "createdDateUTC": "2026-11-04T10:16:01"}})

        class R:
            @staticmethod
            def json():
                return {"dealReference": "ref"}
        return R()

    def confirm(self, ref):
        return {"dealStatus": "ACCEPTED", "level": 1.1001}

    def close_position(self, deal_id):
        self.closed.append((self.account_id, deal_id))
        self.pos[self.account_id] = [p for p in self.pos[self.account_id] if p["position"]["dealId"] != deal_id]
        return {"dealStatus": "ACCEPTED", "level": 1.1012}

    def activity(self, deal_id, since, until):
        return []


def kont():
    return {"format": 1, "haupt": HAUPT, "zuordnung": {"oil-brent": A1}}


def test_run_takes_new_account_opens_and_returns_to_main():
    c = FakeClient(tag_bars("2026-11-04", "10:15", {"10:00": (1.1020, 1.1000)}))
    k = kont()
    st, neu, log = lb.run(c, {}, k, lauf_nach("2026-11-04", "10:00").to_pydatetime())
    assert k["zuordnung"]["london-eurusd"] == NEU and st["konto_id"] == NEU
    assert len(c.orders) == 1 and c.orders[0][0] == NEU
    body = c.orders[0][1]
    assert body["epic"] == "EURUSD" and body["direction"] == "BUY" and body["size"] == 100
    assert abs(body["stopDistance"] - (1.1001 - 1.0990)) < 1e-9 and abs(body["profitDistance"] - (1.1030 - 1.1001)) < 1e-9
    assert st["open"]["tag"] == "2026-11-04" and st["tag_erledigt"] == "2026-11-04"
    assert c.account_id == HAUPT and not c.pos[HAUPT] and not c.pos[A1]
    # Später am Tag: kein zweiter Trade; um 17 Uhr London raus
    c.bars = tag_bars("2026-11-04", "17:00", {"10:00": (1.1020, 1.1000)})
    st, neu, log = lb.run(c, st, k, lauf_nach("2026-11-04", "13:00").to_pydatetime())
    assert len(c.orders) == 1 and not neu
    st, neu, log = lb.run(c, st, k, lauf_nach("2026-11-04", "16:45").to_pydatetime())
    assert c.closed == [(NEU, "D1")] and st["open"] is None
    assert neu[0]["reason"] == "17 Uhr London" and neu[0]["pct"] > 0 and c.account_id == HAUPT


def test_run_waits_without_free_account():
    c = FakeClient(tag_bars("2026-11-04", "10:15", {"10:00": (1.1020, 1.1000)}), {HAUPT: "Account", A1: "Account 1"})
    st, neu, log = lb.run(c, {}, kont(), lauf_nach("2026-11-04", "10:00").to_pydatetime())
    assert not c.orders and "wartet" in st["status"] and c.account_id == HAUPT


def test_find_account_prefers_name_and_never_takes_main_or_other_bots():
    accs = [{"accountId": HAUPT, "accountName": "London"}, {"accountId": A1, "accountName": "London 2"},
            {"accountId": NEU, "accountName": "Account 8"}, {"accountId": "332265000000000001", "accountName": "Account 9"}]
    assert lb.finde_konto(accs, kont(), HAUPT, {}, lambda a: True) == "332265000000000001"   # neuestes freies
    accs[2]["accountName"] = "London EURUSD"
    assert lb.finde_konto(accs, kont(), HAUPT, {}, lambda a: True) == NEU
    assert lb.finde_konto(accs, kont(), HAUPT, {}, lambda a: a != NEU) == "332265000000000001"
    assert lb.finde_konto(accs, {**kont(), "zuordnung": {"oil-brent": A1, "london-eurusd": NEU}}, HAUPT, {},
                          lambda a: False) == NEU


def test_own_position_without_state_is_adopted_and_closed_at_17():
    c = FakeClient(tag_bars("2026-11-04", "17:00"))
    c.pos[NEU].append({"market": {"epic": "EURUSD"},
                       "position": {"dealId": "X1", "direction": "SELL", "level": 1.1000, "size": 100,
                                    "stopLevel": 1.1010, "profitLevel": 1.0970, "createdDateUTC": "2026-11-04T10:16:01"}})
    k = {**kont(), "zuordnung": {"oil-brent": A1, "london-eurusd": NEU}}
    st, neu, log = lb.run(c, {}, k, lauf_nach("2026-11-04", "16:45").to_pydatetime())
    assert any(e["event"] == "Position übernommen" for e in log)
    assert c.closed == [(NEU, "X1")] and neu[0]["side"] == "short" and c.account_id == HAUPT
