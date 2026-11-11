"""The demo bot must trade exactly like the 250-EUR backtest (`run_live`) and never send orders on its own."""
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from gold.backtest.engine import run_live
from gold.backtest.pine_port import signals_b_short, signals_c_long
from gold.bot import runner
from gold.bot.capital import CapitalClient
from gold.bot.rules import (Account, GoldLimits, Quote, Signals, bars_from_prices, catch_up, decide,
                            last_bar_is_current, roll_account_marks, stop_level)

NOW = datetime(2026, 10, 30, 10, 3, tzinfo=timezone.utc)
RICH = Account(equity_eur=1e6, balance_eur=1e6, available_eur=1e6, peak_eur=1e6, day_start_eur=1e6,
               week_start_eur=1e6)
QUOTE = Quote(bid=4000.0, offer=4000.3, eurusd=1.117, margin_rate=0.05)
OPEN = GoldLimits(risk_per_trade_pct=100.0)


def hourly_bars(seed, n=3000, start="2026-01-05"):
    rng = np.random.default_rng(seed)
    close = 4000 * np.exp(np.cumsum(rng.standard_t(4, n) * 0.002))
    open_ = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.0005, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.0015, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.0015, n)))
    idx = pd.date_range(start, periods=n, freq="60min")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=idx)


def candles(bars, spread=0.3):
    return [{"snapshotTime": f"{t:%Y-%m-%dT%H:%M:%S}", "snapshotTimeUTC": f"{t:%Y-%m-%dT%H:%M:%S}",
             **{f"{k}Price": {"bid": r[k], "ask": r[k] + spread} for k in ("open", "high", "low", "close")},
             "lastTradedVolume": 1} for t, r in bars.iterrows()]


def write_limits(tmp_path, text):
    path = tmp_path / "limits.yaml"
    path.write_text("stage: 1\n" + text, encoding="utf-8")
    return path


def test_without_gold_section_the_bot_only_calculates(tmp_path):
    assert GoldLimits.load(write_limits(tmp_path, "")).stage == 0


def test_gold_section_is_read_and_checked(tmp_path):
    limits = GoldLimits.load(write_limits(tmp_path, "gold:\n  stage: 1\n  sides: [long]\n  conflict: reverse\n"))
    assert (limits.stage, limits.sides, limits.conflict, limits.stop_usd) == (1, ("long",), "reverse", 5.6)
    with pytest.raises(ValueError):
        GoldLimits.load(write_limits(tmp_path, "gold:\n  conflict: maybe\n"))
    with pytest.raises(ValueError):
        GoldLimits.load(write_limits(tmp_path, "gold:\n  timeframe: 5min\n"))


def test_running_candle_is_dropped_and_only_the_fresh_one_counts():
    bars = hourly_bars(1, n=5, start="2026-10-30 06:00")       # last candle opens 10:00 and is still running
    got, spread = bars_from_prices(candles(bars), NOW)
    assert got.index[-1] == pd.Timestamp("2026-10-30 09:00") and len(got) == 4
    assert spread.round(6).eq(0.3).all()
    assert last_bar_is_current(got, NOW)
    assert not last_bar_is_current(got.iloc[:-1], NOW)          # 08:00 is old news at 10:03


def test_decisions_follow_the_backtest_rules():
    none = Signals(False, False, False, False)
    assert decide(Signals(True, False, False, False), 0, OPEN, RICH, QUOTE).action == "open"
    assert decide(Signals(False, False, True, False), 0, OPEN, RICH, QUOTE).side == -1
    assert decide(Signals(True, False, True, False), 0, OPEN, RICH, QUOTE).action == "none"
    assert decide(Signals(False, True, False, False), 1, OPEN, RICH, QUOTE).action == "close"
    assert decide(Signals(False, False, True, False), 1, OPEN, RICH, QUOTE).action == "none"
    rev = decide(Signals(False, False, True, False), 1, GoldLimits(conflict="reverse", risk_per_trade_pct=100), RICH, QUOTE)
    assert (rev.action, rev.side) == ("reverse", -1)
    assert decide(Signals(True, False, False, False), 1, OPEN, RICH, QUOTE).action == "none"     # no add-ons
    assert decide(none, 1, OPEN, RICH, QUOTE).action == "none"
    short_off = GoldLimits(sides=("long",), risk_per_trade_pct=100)
    assert decide(Signals(True, False, True, False), 0, short_off, RICH, QUOTE).action == "open"  # short signal ignored


def test_limits_block_new_entries_but_never_the_exit():
    tired = Account(equity_eur=230, balance_eur=230, available_eur=200, peak_eur=250, day_start_eur=250, week_start_eur=250)
    d = decide(Signals(True, False, False, False), 0, GoldLimits(), tired, QUOTE)
    assert d.action == "none" and any("Tageslimit" in r for r in d.reasons)
    assert decide(Signals(False, True, False, False), 1, GoldLimits(), tired, QUOTE).action == "close"
    broke = Account(equity_eur=180, balance_eur=250, available_eur=100, peak_eur=250, day_start_eur=250, week_start_eur=250)
    reasons = decide(Signals(True, False, False, False), 0, GoldLimits(), broke, QUOTE).reasons
    assert any("Not-Aus" in r for r in reasons) and any("Margin" in r for r in reasons)
    wide = Quote(bid=4000.0, offer=4001.5, eurusd=1.117, margin_rate=0.05)
    assert any("Spread" in r for r in decide(Signals(True, False, False, False), 0, OPEN, RICH, wide).reasons)


def acc(eur):
    return Account(equity_eur=eur, balance_eur=eur, available_eur=eur, peak_eur=eur, day_start_eur=eur, week_start_eur=eur)


def test_2_percent_rule_with_one_ounce_and_5_60_stop():
    """5.60 $ / 1.117 = 5.01 EUR: just over 2 % of 250 EUR, fine from 251 EUR on.

    Bis 11.11.2026 fiel das Signal bei 250 EUR ganz weg ("Stop kostet 5.01"). Kirons Wahl vom 11.11.2026 09:42 UTC
    ("Ja, kleiner handeln"): Der Bot nimmt dann weniger als 1 Kontrakt. Die 2 % selbst gelten unverändert."""
    sig = Signals(True, False, False, False)
    klein = decide(sig, 0, GoldLimits(), acc(250), QUOTE)
    assert klein.action == "open" and klein.size == 0.99
    assert klein.size * 5.6 / QUOTE.eurusd <= 250 * 0.02          # nie mehr als 2 % vom Konto
    voll = decide(sig, 0, GoldLimits(), acc(251), QUOTE)
    assert voll.action == "open" and voll.size == 1.0
    assert stop_level(1, QUOTE, 5.6) == pytest.approx(3994.7) and stop_level(-1, QUOTE, 5.6) == pytest.approx(4005.6)


def test_trade_size_shrinks_instead_of_skipping_the_signal():
    """Der Fall vom 05.11.2026 17:11 UTC (journal/gold-decisions.jsonl): Konto 995,17 EUR, Stop 22,92 $ = 20,40 EUR,
    erlaubt 19,90 EUR. Vorher kein Trade, jetzt 0,97 Kontrakte."""
    from gold.bot.rules import entry_blocks, trade_size
    limits = GoldLimits(stop_usd=22.92)
    q = Quote(bid=4000.0, offer=4000.3, eurusd=1.1235, margin_rate=0.05)
    size = trade_size(limits, acc(995.17), q)
    assert size == 0.97 and entry_blocks(limits, acc(995.17), q, 1) == []
    assert size * 22.92 / 1.1235 <= 995.17 * 0.02 < (size + 0.01) * 22.92 / 1.1235   # größte erlaubte Stufe
    d = decide(Signals(False, False, True, False), 0, limits, acc(995.17), q)
    assert (d.action, d.side, d.size) == ("open", -1, 0.97)


def test_trade_size_never_above_the_limit_and_never_above_the_risk():
    from gold.bot.rules import trade_size
    q = Quote(bid=4000.0, offer=4000.3, eurusd=1.117, margin_rate=0.05)
    assert trade_size(GoldLimits(stop_usd=20.0), acc(1e6), q) == 1.0             # reiches Konto: nie mehr als size
    assert trade_size(GoldLimits(size=0.5, stop_usd=20.0), acc(1e6), q) == 0.5
    for eur in (150, 300, 600, 973.76, 1200):
        for stop in (5.6, 12.0, 18.67, 22.92, 35.0, 60.0):
            size = trade_size(GoldLimits(stop_usd=stop), acc(eur), q)
            assert 0 <= size <= 1.0
            assert size * stop / q.eurusd <= eur * 0.02 + 1e-9
            assert round(size * 100) == pytest.approx(size * 100)                # ganze 0,01er Schritte


def test_trade_size_uses_the_brokers_step_and_blocks_below_the_smallest_order():
    from gold.bot.rules import trade_size
    grob = Quote(bid=4000.0, offer=4000.3, eurusd=1.117, margin_rate=0.05, min_size=0.1, size_step=0.1)
    assert trade_size(GoldLimits(stop_usd=22.92), acc(995.17), grob) == 0.9
    sig = Signals(True, False, False, False)
    arm = decide(sig, 0, GoldLimits(stop_usd=22.92), acc(2.0), QUOTE)          # 0,01 Kontrakte kosten 0,21 EUR > 0,04 EUR
    assert arm.action == "none" and arm.size == 0.0
    assert any(r.startswith("Stop kostet 0.21 € schon bei der kleinsten Größe 0.01") for r in arm.reasons)


def test_margin_check_uses_the_smaller_size():
    """1 Kontrakt braucht 4000,3 * 0,05 / 1,117 = 179 EUR Margin. Mit 0,5 Kontrakten reichen 100 EUR frei."""
    knapp = Account(equity_eur=250.0, balance_eur=250.0, available_eur=100.0, peak_eur=250.0, day_start_eur=250.0,
                    week_start_eur=250.0)
    sig = Signals(True, False, False, False)
    assert any("Margin" in r for r in decide(sig, 0, GoldLimits(stop_usd=5.6, risk_per_trade_pct=100), knapp, QUOTE).reasons)
    d = decide(sig, 0, GoldLimits(stop_usd=11.2), knapp, QUOTE)                  # 2 % = 5 EUR -> 0,49 Kontrakte
    assert d.action == "open" and d.size == 0.49


def test_account_marks_roll_by_utc_day_and_week():
    s = roll_account_marks({}, 260, 250, NOW)
    assert (s["peak_eur"], s["day_start_eur"], s["week_start_eur"], s["week"]) == (260, 250, 250, "2026-10-26")
    s2 = roll_account_marks(s, 240, 245, datetime(2026, 10, 30, 23, 0, tzinfo=timezone.utc))
    assert (s2["peak_eur"], s2["day_start_eur"]) == (260, 250)                   # same day: unchanged
    s3 = roll_account_marks(s2, 240, 245, datetime(2026, 11, 2, 1, 0, tzinfo=timezone.utc))
    assert (s3["day_start_eur"], s3["week_start_eur"]) == (245, 245)


@pytest.mark.parametrize("conflict", ["first", "reverse"])
@pytest.mark.parametrize("seed", [3, 4])
def test_bot_replayed_bar_by_bar_makes_the_backtest_trades(seed, conflict):
    bars = hourly_bars(seed)
    sa, sb = signals_c_long(bars), signals_b_short(bars)
    tr, *_ = run_live(bars, pd.Series(0.3, index=bars.index), sa, sb, start_eur=1e6, conflict=conflict)
    expected = [(r.side, r.entry_time, r.exit_time) for r in tr.itertuples() if r.reason == "signal"]

    limits = GoldLimits(conflict=conflict, risk_per_trade_pct=100)
    pos, entry_time, pending, got = 0, None, None, []
    a_in, a_out, b_in, b_out = (s.to_numpy(bool) for s in (sa["entry"], sa["exit"], sb["entry"], sb["exit"]))
    for t, now in enumerate(bars.index):
        if pending is not None:                           # the order sent after bar t-1 fills at bar t's open
            if pending.action in ("close", "reverse"):
                got.append(("long" if pos > 0 else "short", entry_time, now))
                pos = 0
            if pending.action in ("open", "reverse"):
                pos, entry_time = pending.side, now
            pending = None
        d = decide(Signals(a_in[t], a_out[t], b_in[t], b_out[t]), pos, limits, RICH, QUOTE)
        pending = d if d.action != "none" else None
    assert len(expected) > 20
    assert got == expected


class FakeClient:
    environment = "demo"

    def __init__(self, bars, position=None):
        self.bars, self.position, self.orders = bars, position, []

    def login(self):
        return {}

    def accounts(self):
        return [{"preferred": True, "currency": "EUR", "balance": {"balance": 300.0, "profitLoss": 0.0, "available": 300.0}}]

    def prices(self, epic, resolution, max_bars):
        assert (epic, resolution) == ("GOLD", "HOUR")
        return candles(self.bars)

    def positions(self):
        return [self.position] if self.position else []

    def market(self, epic):
        snap = {"bid": 4000.0, "offer": 4000.3, "marketStatus": "TRADEABLE"} if epic == "GOLD" else {"bid": 1.117, "offer": 1.117}
        return {"snapshot": snap, "instrument": {"marginFactor": 5, "marginFactorUnit": "PERCENTAGE", "lotSize": 1}}

    def open_position(self, epic, direction, size, stop_level=None):
        self.orders.append(("open", epic, direction, size, round(stop_level, 2)))
        return {"dealStatus": "ACCEPTED", "level": 4000.3, "dealId": "d1"}

    def close_position(self, deal_id):
        self.orders.append(("close", deal_id))
        return {"dealStatus": "ACCEPTED", "level": 4000.0}


def force_long_signal(monkeypatch):
    def fake(bars, **kw):
        out = pd.DataFrame({"entry": False, "exit": False}, index=bars.index)
        out.iloc[-1, 0] = True
        return out
    monkeypatch.setattr(runner, "signals_c_long", fake)
    monkeypatch.setattr(runner, "signals_b_short", lambda bars, **kw: pd.DataFrame({"entry": False, "exit": False}, index=bars.index))


def test_stage_0_journals_the_decision_but_sends_nothing(tmp_path, monkeypatch):
    force_long_signal(monkeypatch)
    client = FakeClient(hourly_bars(5, n=400, start="2026-10-13 18:00"))
    rec = runner.run(client, GoldLimits(), tmp_path, NOW, notify=lambda m: None)
    assert rec["action"] == "open" and client.orders == []
    assert "nicht gesendet" in rec["results"][0]["step"]
    assert (tmp_path / "gold-decisions.jsonl").read_text().count("\n") == 1
    assert '"peak_eur": 300.0' in (tmp_path / "gold-state.json").read_text()


def test_stage_1_opens_with_the_emergency_stop(tmp_path, monkeypatch):
    force_long_signal(monkeypatch)
    client = FakeClient(hourly_bars(5, n=400, start="2026-10-13 18:00"))
    rec = runner.run(client, GoldLimits(stage=1), tmp_path, NOW, notify=lambda m: None)
    assert client.orders == [("open", "GOLD", "BUY", 1.0, 3994.7)]
    assert rec["results"][0]["dealStatus"] == "ACCEPTED"


def test_old_candles_mean_no_action(tmp_path, monkeypatch):
    force_long_signal(monkeypatch)
    client = FakeClient(hourly_bars(5, n=400, start="2026-10-01 00:00"))   # ends days before NOW (weekend, outage)
    assert runner.run(client, GoldLimits(stage=1), tmp_path, NOW, notify=lambda m: None) is None
    assert client.orders == []


def test_capital_client_login_and_order_flow():
    calls = []

    class Resp:
        def __init__(self, payload, headers=None):
            self.payload, self.headers, self.status_code, self.ok, self.text = payload, headers or {}, 200, True, ""

        def json(self):
            return self.payload

    class Session:
        def request(self, method, url, **kw):
            calls.append((method, url, kw))
            if url.endswith("/session"):
                return Resp({"currencyIsoCode": "EUR"}, {"CST": "c", "X-SECURITY-TOKEN": "x"})
            if method == "POST":
                return Resp({"dealReference": "o_1"})
            return Resp({"dealStatus": "ACCEPTED", "dealId": "d1"})

    client = CapitalClient("key", "me@example.com", "pw", session=Session())
    client.login()
    res = client.open_position("GOLD", "BUY", 1.0, stop_level=3994.7)
    assert calls[0][2]["headers"] == {"X-CAP-API-KEY": "key"}
    assert calls[0][2]["json"] == {"identifier": "me@example.com", "password": "pw", "encryptedPassword": False}
    assert calls[1][1].endswith("/api/v1/positions") and calls[1][2]["headers"] == {"CST": "c", "X-SECURITY-TOKEN": "x"}
    assert calls[1][2]["json"] == {"epic": "GOLD", "direction": "BUY", "size": 1.0, "guaranteedStop": False, "stopLevel": 3994.7}
    assert calls[2][1].endswith("/confirms/o_1") and res["dealStatus"] == "ACCEPTED"
    with pytest.raises(PermissionError):
        CapitalClient("k", "i", "p", environment="live")


def test_no_candles_at_all_is_handled():
    bars, spread = bars_from_prices([], NOW)
    assert bars.empty and spread.empty and not last_bar_is_current(bars, NOW)


def missed_table(index, **true_at):
    table = pd.DataFrame(False, index=index, columns=["long_entry", "long_exit", "short_entry", "short_exit"])
    for col, at in true_at.items():
        table.loc[at, col] = True
    return table


def test_catch_up_closes_on_a_missed_exit_but_never_opens_late():
    idx = pd.date_range("2026-10-30 07:00", periods=2, freq="60min")
    none = Signals(False, False, False, False)
    sig, notes = catch_up(none, 1, missed_table(idx, long_exit=idx[0], short_entry=idx[1]))
    assert sig.long_exit and not sig.short_entry
    assert decide(sig, 1, OPEN, RICH, QUOTE).action == "close"
    assert "07:00:00 verpasst, jetzt nachgeholt" in notes[0] and "nicht nachgeholt" in notes[1]
    sig, notes = catch_up(none, 0, missed_table(idx, long_entry=idx[1], long_exit=idx[0]))
    assert sig == none and decide(sig, 0, OPEN, RICH, QUOTE).action == "none" and len(notes) == 1
    assert catch_up(none, -1, missed_table(idx[:0])) == (none, [])


def test_second_attempt_on_the_same_candle_does_nothing(tmp_path, monkeypatch):
    force_long_signal(monkeypatch)
    client = FakeClient(hourly_bars(5, n=400, start="2026-10-13 18:00"))
    runner.run(client, GoldLimits(stage=1), tmp_path, NOW, notify=lambda m: None)
    later = NOW.replace(minute=41)
    assert runner.run(client, GoldLimits(stage=1), tmp_path, later, notify=lambda m: None) is None
    assert len(client.orders) == 1
    dry = runner.run(client, GoldLimits(stage=1), tmp_path, later, notify=lambda m: None, send_orders=False)
    assert dry["action"] == "open" and len(client.orders) == 1


def test_a_missed_run_still_closes_on_its_exit_signal(tmp_path, monkeypatch):
    bars = hourly_bars(5, n=400, start="2026-10-13 18:00")
    flags = pd.DataFrame({"entry": False, "exit": False}, index=bars.index)
    flags.loc[bars.index[-2], "exit"] = True                      # exit at 08:00, the run at 09:11 fell out
    monkeypatch.setattr(runner, "signals_c_long", lambda b, **kw: flags.copy())
    monkeypatch.setattr(runner, "signals_b_short", lambda b, **kw: pd.DataFrame({"entry": False, "exit": False}, index=b.index))
    (tmp_path / "gold-state.json").write_text('{"last_bar": "%s"}' % bars.index[-3], encoding="utf-8")
    client = FakeClient(bars, position={"market": {"epic": "GOLD"}, "position": {"direction": "BUY", "dealId": "d7"}})
    rec = runner.run(client, GoldLimits(stage=1), tmp_path, NOW, notify=lambda m: None)
    assert client.orders == [("close", "d7")] and rec["missed_bars"] == 1
    assert "verpasst, jetzt nachgeholt" in rec["reasons"][0]
    assert f'"last_bar": "{bars.index[-1]}"' in (tmp_path / "gold-state.json").read_text()


def test_pasted_whitespace_is_removed_and_hints_never_show_a_secret():
    raw = {"CAPITAL_API_KEY": " k3yABCDEFGH12345\n", "CAPITAL_IDENTIFIER": "Me@Example.com ",
           "CAPITAL_API_PASSWORD": "pass word\r\n"}
    assert runner.clean_credentials(raw) == ["k3yABCDEFGH12345", "Me@Example.com", "pass word"]
    hints = runner.login_hints(raw)
    text = " ".join(hints)
    assert all(secret not in text for secret in ("k3yABCDEFGH12345", "Me@Example.com", "pass word"))
    assert sum("am Rand" in h for h in hints) == 3 and hints[-1] == "CAPITAL_API_KEY hat 16 Zeichen"
    relay = runner.login_hints({"CAPITAL_API_KEY": "k", "CAPITAL_IDENTIFIER": "x1@privaterelay.appleid.com",
                                "CAPITAL_API_PASSWORD": "k"})
    assert any("Apple" in h for h in relay) and any("gleich dem Schlüssel" in h for h in relay)
    assert any("keine E-Mail" in h for h in runner.login_hints({"CAPITAL_IDENTIFIER": "kiron"}))


def test_rejected_login_prints_the_hints_and_still_fails(monkeypatch, capsys):
    monkeypatch.setenv("CAPITAL_API_KEY", "key\n")
    monkeypatch.setenv("CAPITAL_IDENTIFIER", "me@example.com")
    monkeypatch.setenv("CAPITAL_API_PASSWORD", "pw")
    seen = {}

    def reject(client, *args, **kw):
        seen["login"] = client._login, client._api_key
        raise runner.CapitalError('POST /session -> 401: {"errorCode":"error.invalid.details"}')

    monkeypatch.setattr(runner, "run", reject)
    with pytest.raises(runner.CapitalError):
        runner.main(["--dry-run"])
    assert seen["login"][1] == "key" and seen["login"][0]["identifier"] == "me@example.com"
    out = capsys.readouterr().out
    assert "lehnt den Login ab" in out and "CAPITAL_API_KEY hatte Leerzeichen" in out


def test_login_check_only_signs_in_and_out(monkeypatch, capsys):
    from gold.bot import login_check

    calls = []

    class Resp:
        def __init__(self, status, headers=None):
            self.status_code, self.ok, self.headers, self.text = status, status < 400, headers or {}, ""
            if status == 401:
                self.text = '{"errorCode":"error.invalid.details"}'

        def json(self):
            return {}

    class Session:
        def __init__(self, status):
            self.status = status

        def request(self, method, url, **kw):
            calls.append((method, url.split("/api/v1")[0], url.split("/api/v1")[1]))
            return Resp(self.status, {"CST": "c", "X-SECURITY-TOKEN": "x"})

    def client(environment, status):
        return CapitalClient("k", "me@example.com", "pw", environment=environment,
                             allow_live=environment == "live", session=Session(status))

    assert login_check.check(client("live", 200))
    assert calls == [("POST", "https://api-capital.backend-capital.com", "/session"),
                     ("DELETE", "https://api-capital.backend-capital.com", "/session")]
    calls.clear()
    assert not login_check.check(client("demo", 401))
    assert calls == [("POST", "https://demo-api-capital.backend-capital.com", "/session")]
    assert "demo: Login abgelehnt" in capsys.readouterr().out
    monkeypatch.delenv("CAPITAL_API_KEY", raising=False)
    assert login_check.main(["live"]) == 2 and login_check.main(["echt"]) == 2


class FillingClient(FakeClient):
    """Wie der Broker: nach einer angenommenen Order ist die Position da, nach dem Schließen weg."""

    def open_position(self, epic, direction, size, stop_level=None):
        res = super().open_position(epic, direction, size, stop_level)
        self.position = {"market": {"epic": epic}, "position": {
            "direction": direction, "dealId": res["dealId"], "level": res["level"], "size": size,
            "stopLevel": round(stop_level, 2), "createdDateUTC": "2026-10-30T10:03:05.000", "upl": -0.3}}
        return res


def test_chart_file_has_the_last_candles_and_the_position_after_the_order(tmp_path, monkeypatch):
    force_long_signal(monkeypatch)
    bars = hourly_bars(5, n=700, start="2026-10-01 10:00")
    client = FillingClient(bars)
    rec = runner.run(client, GoldLimits(stage=1), tmp_path, NOW, notify=lambda m: None)
    chart = runner.json.loads((tmp_path / "gold-chart.json").read_text(encoding="utf-8"))
    assert chart["format"] == 1 and chart["epic"] == "GOLD" and chart["timeframe"] == "60min"
    assert chart["columns"] == ["time_utc", "open", "high", "low", "close"]
    assert len(chart["bars"]) == runner.CHART_BARS
    assert chart["bars"][-1][0] == rec["bar"] == "2026-10-30 09:00:00"         # gleiche Schreibweise wie das Journal
    last = bars.loc[pd.Timestamp(rec["bar"])]
    assert chart["bars"][-1][1:] == [round(last[k], 2) for k in ("open", "high", "low", "close")]
    assert chart["position"] == {"side": "long", "direction": "BUY", "entry": 4000.3, "size": 1.0, "stop": 3994.7,
                                 "dealId": "d1", "opened_utc": "2026-10-30T10:03:05.000", "upl": -0.3}
    assert chart["account"] == {"equity": 300.0, "currency": "EUR"}


def test_chart_file_never_changes_the_decision(tmp_path, monkeypatch):
    force_long_signal(monkeypatch)
    client = FakeClient(hourly_bars(5, n=400, start="2026-10-13 18:00"))
    monkeypatch.setattr(runner, "chart_snapshot", lambda *a, **k: 1 / 0)
    rec = runner.run(client, GoldLimits(stage=1), tmp_path, NOW, notify=lambda m: None)
    assert rec["action"] == "open" and client.orders == [("open", "GOLD", "BUY", 1.0, 3994.7)]
    assert not (tmp_path / "gold-chart.json").exists()
    assert "last_bar" in (tmp_path / "gold-state.json").read_text()


def test_chart_file_without_position_and_in_stage_0(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "signals_c_long", lambda b, **kw: pd.DataFrame({"entry": False, "exit": False}, index=b.index))
    monkeypatch.setattr(runner, "signals_b_short", lambda b, **kw: pd.DataFrame({"entry": False, "exit": False}, index=b.index))
    client = FakeClient(hourly_bars(5, n=400, start="2026-10-13 18:00"))
    assert runner.run(client, GoldLimits(), tmp_path, NOW, notify=lambda m: None)["action"] == "none"
    chart = runner.json.loads((tmp_path / "gold-chart.json").read_text(encoding="utf-8"))
    assert chart["position"] is None and len(chart["bars"]) == 400 and chart["bars"][-1][0] == "2026-10-30 09:00:00"


class BrokerClient(FillingClient):
    """Wie FillingClient, schließt beim Schließen die Position und kennt die Kontoaktivität."""

    def __init__(self, bars, position=None, activities=None):
        super().__init__(bars, position)
        self.activities, self.asked = activities, []

    def close_position(self, deal_id):
        res = super().close_position(deal_id)
        self.position = None
        return {**res, "level": 4012.5}

    def activity(self, deal_id, since, until):
        self.asked.append((deal_id, since, until))
        if self.activities is None:
            raise RuntimeError("404")
        return self.activities


def no_signals_patch(monkeypatch, exit_long=False):
    def c(bars, **kw):
        out = pd.DataFrame({"entry": False, "exit": False}, index=bars.index)
        out.iloc[-1, 1] = exit_long
        return out
    monkeypatch.setattr(runner, "signals_c_long", c)
    monkeypatch.setattr(runner, "signals_b_short", lambda bars, **kw: pd.DataFrame({"entry": False, "exit": False}, index=bars.index))


def open_long_state(tmp_path, bars):
    trade = {"side": "long", "direction": "BUY", "entry": 4000.3, "size": 1.0, "stop": 3994.7, "dealId": "d1",
             "opened_utc": "2026-10-30T07:11:05.000", "upl": None, "bar": "2026-10-30 06:00:00"}
    (tmp_path / "gold-state.json").write_text(runner.json.dumps({"last_bar": str(bars.index[-2]), "open_trade": trade}),
                                              encoding="utf-8")
    return {"market": {"epic": "GOLD"}, "position": {"direction": "BUY", "dealId": "d1", "level": 4000.3, "size": 1.0,
                                                     "stopLevel": 3994.7, "createdDateUTC": "2026-10-30T07:11:05.000"}}


def trades_of(tmp_path):
    path = tmp_path / "gold-trades.jsonl"
    return [runner.json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def test_opening_stores_the_open_trade(tmp_path, monkeypatch):
    force_long_signal(monkeypatch)
    client = FillingClient(hourly_bars(5, n=400, start="2026-10-13 18:00"))
    runner.run(client, GoldLimits(stage=1), tmp_path, NOW, notify=lambda m: None)
    state = runner.json.loads((tmp_path / "gold-state.json").read_text(encoding="utf-8"))
    assert state["open_trade"]["dealId"] == "d1" and state["open_trade"]["bar"] == "2026-10-30 09:00:00"
    assert state["open_trade"]["entry"] == 4000.3 and state["open_trade"]["stop"] == 3994.7
    assert trades_of(tmp_path) == []


def test_exit_signal_writes_the_trade_with_profit(tmp_path, monkeypatch):
    bars = hourly_bars(5, n=400, start="2026-10-13 18:00")
    no_signals_patch(monkeypatch, exit_long=True)
    client = BrokerClient(bars, position=open_long_state(tmp_path, bars))
    rec = runner.run(client, GoldLimits(stage=1), tmp_path, NOW, notify=lambda m: None)
    assert client.orders == [("close", "d1")] and rec["trades_closed"] == 1
    [t] = trades_of(tmp_path)
    assert (t["side"], t["strategy"], t["reason"], t["exit"], t["exit_bar"]) == ("long", "C", "Ausstiegssignal", 4012.5, rec["bar"])
    assert t["pnl_usd"] == 12.2 and t["r"] == pytest.approx(12.2 / 5.6, abs=0.01)
    assert t["pnl_eur"] == round(12.2 / 1.117, 2) and t["balance_after_eur"] == round(300.0 + t["pnl_eur"], 2)
    assert t["entry_bar"] == "2026-10-30 06:00:00" and t["exit_estimated"] is False
    state = runner.json.loads((tmp_path / "gold-state.json").read_text(encoding="utf-8"))
    assert state["open_trade"] is None


def test_broker_stop_between_runs_is_found_in_the_activity(tmp_path, monkeypatch):
    bars = hourly_bars(5, n=400, start="2026-10-13 18:00")
    no_signals_patch(monkeypatch)
    open_long_state(tmp_path, bars)
    acts = [{"dateUTC": "2026-10-30T09:40:00", "source": "SL", "type": "POSITION", "status": "ACCEPTED",
             "details": {"level": 3994.6, "actions": [{"actionType": "POSITION_CLOSED", "dealId": "d1"}]}}]
    client = BrokerClient(bars, position=None, activities=acts)
    msgs = []
    rec = runner.run(client, GoldLimits(stage=1), tmp_path, NOW, notify=msgs.append)
    [t] = trades_of(tmp_path)
    assert (t["reason"], t["exit"], t["exit_bar"], t["exit_estimated"]) == ("Stop beim Broker", 3994.6, None, False)
    assert t["pnl_usd"] == -5.7 and t["r"] == pytest.approx(-5.7 / 5.6, abs=0.01) and t["balance_after_eur"] == 300.0
    assert client.asked[0][0] == "d1" and client.orders == [] and rec["trades_closed"] == 1
    assert any("Stop beim Broker" in m for m in msgs)
    assert '"trades_closed": 1' in (tmp_path / "gold-decisions.jsonl").read_text(encoding="utf-8")


def test_opening_row_in_the_activity_is_never_taken_as_the_close(tmp_path, monkeypatch):
    # Echte Antwort vom 03.11.2026: neueste zuerst, actions leer, die Eröffnung des Bots steht als USER drin
    bars = hourly_bars(5, n=400, start="2026-10-13 18:00")
    no_signals_patch(monkeypatch)
    open_long_state(tmp_path, bars)
    acts = [{"dateUTC": "2026-10-30T09:40:00.983", "source": "SL", "type": "POSITION", "status": "ACCEPTED",
             "details": {"level": 3994.6, "actions": []}},
            {"dateUTC": "2026-10-29T22:02:00.279", "source": "SYSTEM", "type": "SWAP", "status": "ACCEPTED",
             "details": {"level": 3998.1, "actions": []}},
            {"dateUTC": "2026-10-30T07:11:04.950", "source": "USER", "type": "POSITION", "status": "ACCEPTED",
             "details": {"level": 4000.3, "actions": []}}]
    runner.run(BrokerClient(bars, position=None, activities=acts), GoldLimits(stage=1), tmp_path, NOW,
               notify=lambda m: None)
    [t] = trades_of(tmp_path)
    assert (t["reason"], t["exit"], t["pnl_usd"], t["exit_estimated"]) == ("Stop beim Broker", 3994.6, -5.7, False)


def test_close_activity_rules():
    opening = {"dateUTC": "2026-11-02T19:11:28.405", "source": "USER", "type": "POSITION", "status": "ACCEPTED",
               "level": 3954.76, "actions": []}
    stop = {"dateUTC": "2026-11-03T00:31:03.983", "source": "SL", "type": "POSITION", "status": "ACCEPTED",
            "level": 3960.45, "actions": []}
    swap = {"dateUTC": "2026-11-02T22:02:00.279", "source": "SYSTEM", "type": "SWAP", "status": "ACCEPTED",
            "level": 3946.56, "actions": []}
    by_hand = {**opening, "dateUTC": "2026-11-02T23:05:00.000", "level": 3949.1}
    opened = "2026-11-02T19:11:28.466"
    assert runner.close_activity([stop, swap, opening], opened) is stop
    assert runner.close_activity([opening, swap, stop], None) is stop
    assert runner.close_activity([by_hand, swap, opening], opened) is by_hand
    assert runner.close_activity([opening, by_hand], None) is by_hand
    assert runner.close_activity([swap, opening], opened) is None
    assert runner.close_activity([opening], None) is None


def test_unreadable_activity_estimates_the_exit_at_the_stop(tmp_path, monkeypatch):
    bars = hourly_bars(5, n=400, start="2026-10-13 18:00")
    no_signals_patch(monkeypatch)
    open_long_state(tmp_path, bars)
    client = BrokerClient(bars, position=None, activities=None)
    runner.run(client, GoldLimits(stage=1), tmp_path, NOW, notify=lambda m: None)
    [t] = trades_of(tmp_path)
    assert (t["exit"], t["exit_estimated"], t["reason"]) == (3994.7, True, "beim Broker geschlossen")
    assert "nicht lesbar" in t["broker"]


def test_dry_run_never_writes_trades_or_changes_the_open_trade(tmp_path, monkeypatch):
    bars = hourly_bars(5, n=400, start="2026-10-13 18:00")
    no_signals_patch(monkeypatch)
    open_long_state(tmp_path, bars)
    client = BrokerClient(bars, position=None, activities=[])
    runner.run(client, GoldLimits(stage=1), tmp_path, NOW, notify=lambda m: None, send_orders=False)
    assert trades_of(tmp_path) == [] and client.asked == []
    state = runner.json.loads((tmp_path / "gold-state.json").read_text(encoding="utf-8"))
    assert state["open_trade"]["dealId"] == "d1"


def test_capital_activity_asks_only_for_that_deal():
    calls = []

    class Resp:
        status_code = 200

        def json(self):
            return {"activities": [{"dealId": "d1"}]}

    client = CapitalClient("k", "e", "p", environment="demo")
    client._request = lambda method, path, **kw: calls.append((method, path, kw)) or Resp()
    out = client.activity("d1", datetime(2026, 10, 29, 9, 0), datetime(2026, 10, 30, 9, 0))
    assert out == [{"dealId": "d1"}]
    assert calls == [("GET", "/history/activity", {"params": {"dealId": "d1", "detailed": "true",
                                                             "from": "2026-10-29T09:00:00", "to": "2026-10-30T09:00:00"}})]


def test_atr_stop_is_off_unless_kiron_sets_it(tmp_path, monkeypatch):
    force_long_signal(monkeypatch)
    client = FillingClient(hourly_bars(5, n=400, start="2026-10-13 18:00"))
    rec = runner.run(client, GoldLimits(stage=1), tmp_path, NOW, notify=lambda m: None)
    assert rec["stop_usd"] == 5.6 and rec["atr14"] > 0
    assert client.position["position"]["stopLevel"] == 3994.7


def test_atr_stop_uses_atr14_of_the_signal_bar(tmp_path, monkeypatch):
    from gold.backtest.sizing import atr_rma
    force_long_signal(monkeypatch)
    bars = hourly_bars(5, n=400, start="2026-10-13 18:00")
    client = FillingClient(bars)
    rec = runner.run(client, GoldLimits(stage=1, stop_atr=1.0, risk_per_trade_pct=100.0), tmp_path, NOW,
                     notify=lambda m: None)
    done, _ = runner.bars_from_prices(client.prices("GOLD", "HOUR", 1000), NOW)
    want = round(float(atr_rma(done, 14)[-1]), 2)
    assert rec["action"] == "open" and rec["stop_usd"] == want and want != 5.6
    assert client.position["position"]["stopLevel"] == round(4000.3 - want, 2)
    state = runner.json.loads((tmp_path / "gold-state.json").read_text(encoding="utf-8"))
    assert state["open_trade"]["stop"] == round(4000.3 - want, 2)


def test_atr_stop_counts_in_the_risk_check(tmp_path, monkeypatch):
    force_long_signal(monkeypatch)
    client = FillingClient(hourly_bars(5, n=400, start="2026-10-13 18:00"))
    rec = runner.run(client, GoldLimits(stage=1, stop_atr=3.0, risk_per_trade_pct=0.01), tmp_path, NOW,
                     notify=lambda m: None)
    assert rec["action"] == "none" and client.orders == []
    assert any(r.startswith("Stop kostet") for r in rec["reasons"])


def test_runner_sends_the_smaller_size_and_journals_it(tmp_path, monkeypatch):
    """Konto 300 EUR, 2 % = 6 EUR. Stop 1 x ATR(14) der Signalkerze: Der Bot schickt so viele Kontrakte, dass der Stop
    höchstens 6 EUR kostet, und schreibt Größe und Grund ins Journal. Der Stop-Kurs bleibt derselbe wie bei 1 Kontrakt."""
    from gold.backtest.sizing import atr_rma
    force_long_signal(monkeypatch)
    bars = hourly_bars(5, n=400, start="2026-10-13 18:00")
    client = FillingClient(bars)
    rec = runner.run(client, GoldLimits(stage=1, stop_atr=1.0), tmp_path, NOW, notify=lambda m: None)
    done, _ = runner.bars_from_prices(client.prices("GOLD", "HOUR", 1000), NOW)
    atr = round(float(atr_rma(done, 14)[-1]), 2)
    assert atr / 1.117 > 6.0                                                    # 1 Kontrakt wäre zu teuer gewesen
    want = math.floor(6.0 / (atr / 1.117) / 0.01 + 1e-9) * 0.01
    assert rec["action"] == "open" and rec["size"] == pytest.approx(want) and 0 < rec["size"] < 1.0
    assert "höchstens 2 %" in rec["size_why"]
    [order] = client.orders
    assert order[:3] == ("open", "GOLD", "BUY") and order[3] == pytest.approx(want)
    assert order[4] == round(4000.3 - atr, 2)                                   # Stop wie bei 1 Kontrakt
    assert order[3] * atr / 1.117 <= 6.0
    state = runner.json.loads((tmp_path / "gold-state.json").read_text(encoding="utf-8"))
    assert state["open_trade"]["size"] == pytest.approx(want, abs=0.005)
    chart = runner.json.loads((tmp_path / "gold-chart.json").read_text(encoding="utf-8"))
    assert chart["position"]["size"] == pytest.approx(want, abs=0.005)          # das kopiert die Gold-Staffel


def test_runner_reads_smallest_order_and_step_from_the_broker():
    class C(FakeClient):
        def market(self, epic):
            m = super().market(epic)
            m["dealingRules"] = {"minDealSize": {"value": 0.05}, "minSizeIncrement": {"value": 0.05}}
            return m
    q = runner.quote_for(C(None), "GOLD", "EUR")
    assert (q.min_size, q.size_step) == (0.05, 0.05)
    q = runner.quote_for(FakeClient(None), "GOLD", "EUR")                       # ohne Angabe: 0,01
    assert (q.min_size, q.size_step) == (0.01, 0.01)


def test_stop_atr_must_be_sensible(tmp_path):
    good = tmp_path / "ok.yaml"
    good.write_text("gold:\n  stage: 1\n  stop_usd: 5.6\n  stop_atr: 1.0\n", encoding="utf-8")
    assert GoldLimits.load(good).stop_atr == 1.0
    bad = tmp_path / "bad.yaml"
    bad.write_text("gold:\n  stop_atr: 7\n", encoding="utf-8")
    with pytest.raises(ValueError):
        GoldLimits.load(bad)


def losing_trades(tmp_path, n):
    rows = [{"dealId": f"v{i}", "side": "short", "r": -1.0, "opened_utc": "2026-11-04T10:11:00",
             "closed_utc": "2026-11-04T12:11:00+00:00"} for i in range(n)]
    (tmp_path / "gold-trades.jsonl").write_text("".join(runner.json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_safety_switch_blocks_the_entry_and_tells_kiron_once(tmp_path, monkeypatch):
    force_long_signal(monkeypatch)
    losing_trades(tmp_path, 8)
    msgs = []
    client = FakeClient(hourly_bars(5, n=400, start="2026-10-13 18:00"))
    rec = runner.run(client, GoldLimits(stage=1), tmp_path, NOW, notify=msgs.append)
    assert rec["action"] == "none" and client.orders == []
    assert rec["reasons"][0].startswith("Sicherheitsschalter") and rec["schalter"]["pause"] is True
    assert rec["schalter"]["trades"] == 8 and rec["schalter"]["summe_r"] == -8.0
    assert sum("Sicherheitsschalter" in m and "Einstiegssignal" not in m for m in msgs) == 1
    state = runner.json.loads((tmp_path / "gold-state.json").read_text(encoding="utf-8"))
    assert state["schalter_pause"].startswith("Sicherheitsschalter")


def test_safety_switch_message_is_not_repeated_on_the_next_run(tmp_path, monkeypatch):
    force_long_signal(monkeypatch)
    losing_trades(tmp_path, 8)
    bars = hourly_bars(5, n=400, start="2026-10-13 18:00")
    (tmp_path / "gold-state.json").write_text(runner.json.dumps({"last_bar": str(bars.index[-2]),
                                                                 "schalter_pause": "Sicherheitsschalter: alt"}),
                                              encoding="utf-8")
    msgs = []
    runner.run(FakeClient(bars), GoldLimits(stage=1), tmp_path, NOW, notify=msgs.append)
    assert not any("Offene Positionen laufen" in m for m in msgs)


def test_seven_losses_still_trade_and_the_record_shows_the_count(tmp_path, monkeypatch):
    force_long_signal(monkeypatch)
    losing_trades(tmp_path, 7)
    client = FakeClient(hourly_bars(5, n=400, start="2026-10-13 18:00"))
    rec = runner.run(client, GoldLimits(stage=1), tmp_path, NOW, notify=lambda m: None)
    assert rec["action"] == "open" and len(client.orders) == 1
    assert rec["schalter"] == {"pause": False, "grund": None, "trades": 7, "summe_r": -7.0, "pf_r": 0.0,
                               "hinweise": []}


def test_safety_switch_never_stops_the_exit(tmp_path, monkeypatch):
    bars = hourly_bars(5, n=400, start="2026-10-13 18:00")
    no_signals_patch(monkeypatch, exit_long=True)
    losing_trades(tmp_path, 8)
    client = BrokerClient(bars, position=open_long_state(tmp_path, bars))
    rec = runner.run(client, GoldLimits(stage=1), tmp_path, NOW, notify=lambda m: None)
    assert client.orders == [("close", "d1")] and rec["trades_closed"] == 1


class OpenProfitClient(BrokerClient):
    """Wie Capital.com mit offenem Gewinn: balance = deposit + profitLoss, das offene Ergebnis steckt schon drin."""

    def accounts(self):
        return [{"preferred": True, "currency": "EUR",
                 "balance": {"balance": 310.9, "deposit": 300.0, "profitLoss": 10.9, "available": 290.0}}]


def test_open_profit_is_counted_once_in_the_account(tmp_path, monkeypatch):
    bars = hourly_bars(5, n=400, start="2026-10-13 18:00")
    no_signals_patch(monkeypatch)
    client = OpenProfitClient(bars, position=open_long_state(tmp_path, bars))
    rec = runner.run(client, GoldLimits(stage=1), tmp_path, NOW, notify=lambda m: None)
    assert rec["equity"] == 310.9                     # nicht 321,80 (offener Gewinn doppelt)
    state = runner.json.loads((tmp_path / "gold-state.json").read_text(encoding="utf-8"))
    assert state["peak_eur"] == 310.9
    assert state["day_start_eur"] == 300.0 and state["week_start_eur"] == 300.0   # nur abgeschlossene Trades


def test_balance_after_a_bot_exit_is_cash_plus_the_result(tmp_path, monkeypatch):
    bars = hourly_bars(5, n=400, start="2026-10-13 18:00")
    no_signals_patch(monkeypatch, exit_long=True)
    client = OpenProfitClient(bars, position=open_long_state(tmp_path, bars))
    runner.run(client, GoldLimits(stage=1), tmp_path, NOW, notify=lambda m: None)
    [t] = trades_of(tmp_path)
    assert t["balance_after_eur"] == round(300.0 + t["pnl_eur"], 2)
