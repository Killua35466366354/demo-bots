"""Sicherheitsschalter des Gold-Bots (Kritik D4, gold/bot/VORAB_sicherheit.yaml): pausiert nur neue Einstiege,
rechnet jedes Mal neu aus dem Trade-Journal und gilt nur mit seiner Prüfsumme im Protokoll."""
import pytest

from gold.bot import schalter
from gold.bot.rules import Account, GoldLimits, Quote, Signals, decide

RICH = Account(equity_eur=1e6, balance_eur=1e6, available_eur=1e6, peak_eur=1e6, day_start_eur=1e6,
               week_start_eur=1e6)
QUOTE = Quote(bid=4000.0, offer=4000.3, eurusd=1.117, margin_rate=0.05)


def regel():
    r = schalter.gesiegelte_regel()
    assert r is not None
    return r


def trade(r, opened="2026-11-10T10:11:00", **kw):
    return {"dealId": kw.get("deal", "x"), "side": "long", "r": r, "opened_utc": opened,
            "entry_bar": kw.get("bar"), "closed_utc": kw.get("closed", "2026-11-10T12:11:00+00:00")}


def test_the_committed_rule_is_sealed_in_the_protocol():
    r = regel()
    assert r["start"] == "2026-11-03T09:05:00Z"
    p = r["pause_wenn"]
    assert (p["summe_r_hoechstens"], p["urteil_nach_trades"], p["urteil_summe_r_ueber"],
            p["urteil_pf_r_mindestens"]) == (-8.0, 30, 0.0, 1.2)


def test_a_changed_rule_file_counts_as_unsealed(tmp_path):
    vorab = tmp_path / "VORAB_sicherheit.yaml"
    vorab.write_text(schalter.VORAB.read_text(encoding="utf-8").replace("-8.0", "-80.0"), encoding="utf-8")
    assert schalter.gesiegelte_regel(vorab, schalter.PROTOKOLL) is None
    assert schalter.gesiegelte_regel(schalter.VORAB, tmp_path / "fehlt.md") is None


def test_without_a_sealed_rule_the_bot_pauses_rather_than_trading_unprotected():
    s = schalter.pruefen([], None)
    assert s.pause and "Prüfsumme" in s.grund


def test_no_trades_no_pause():
    s = schalter.pruefen([], regel())
    assert not s.pause and s.trades == 0 and s.summe_r == 0 and s.pf_r is None


def test_minus_8_r_since_start_pauses_and_minus_7_does_not():
    assert not schalter.pruefen([trade(-1.0)] * 7, regel()).pause
    s = schalter.pruefen([trade(-1.0)] * 8, regel())
    assert s.pause and "-8.00 R" in s.grund and s.trades == 8


def test_a_win_in_between_counts():
    rs = [-1.0] * 6 + [3.0] + [-1.0] * 4          # Summe -7
    assert not schalter.pruefen([trade(r) for r in rs], regel()).pause


def test_trades_before_the_start_do_not_count():
    old = trade(-1.01, opened="2026-11-02T19:11:28.466")    # der Short vom 02.11. mit dem alten 5,60-$-Stop
    assert schalter.pruefen([old] + [trade(-1.0)] * 7, regel()).summe_r == -7.0


def test_start_falls_back_to_entry_bar_then_closed_time():
    t = trade(-1.0, opened=None, bar="2026-11-02 18:00:00")
    assert schalter.pruefen([t], regel()).trades == 0
    t = trade(-1.0, opened=None, bar=None, closed="2026-11-04T01:00:00+00:00")
    assert schalter.pruefen([t], regel()).trades == 1


def test_a_trade_without_r_is_skipped_with_a_note():
    s = schalter.pruefen([trade(None, deal="d9")], regel())
    assert s.trades == 0 and s.hinweise == ["Trade d9 ohne r, zählt nicht"]


def test_verdict_after_30_trades_becomes_binding():
    # Summe über 0, aber Gewinnfaktor unter 1,2: 8 Gewinner zu 1,4 R, 22 Verlierer zu 0,5 R -> PF 1,018
    bad = [trade(1.4)] * 8 + [trade(-0.5)] * 22
    assert not schalter.pruefen(bad[:29], regel()).pause
    s = schalter.pruefen(bad, regel())
    assert s.pause and "Urteil nach 30 Trades" in s.grund
    zero = [trade(2.0)] * 10 + [trade(-1.0)] * 20    # Summe genau 0 R: nicht über 0
    assert schalter.pruefen(zero, regel()).pause
    passed = [trade(2.5)] * 10 + [trade(-1.0)] * 20  # +5 R, PF 1,25
    s = schalter.pruefen(passed, regel())
    assert not s.pause and s.pf_r == pytest.approx(1.25)


def test_verdict_uses_the_first_30_trades_only():
    passed = [trade(2.5)] * 10 + [trade(-1.0)] * 20
    later = passed + [trade(-1.0)] * 5                # danach Verluste, Summe 0, aber noch nicht -8
    assert not schalter.pruefen(later, regel()).pause
    assert schalter.pruefen(passed + [trade(-1.0)] * 13, regel()).pause   # Summe -8: Pause über den ersten Teil


def test_pause_blocks_entries_and_reversals_but_never_the_exit():
    grund = "Sicherheitsschalter: Test"
    d = decide(Signals(True, False, False, False), 0, GoldLimits(risk_per_trade_pct=100.0), RICH, QUOTE, pause=grund)
    assert d.action == "none" and d.reasons[0] == grund
    d = decide(Signals(False, True, False, False), 1, GoldLimits(), RICH, QUOTE, pause=grund)
    assert d.action == "close"
    d = decide(Signals(False, False, True, False), 1, GoldLimits(conflict="reverse", risk_per_trade_pct=100.0),
               RICH, QUOTE, pause=grund)
    assert d.action == "none" and grund in d.reasons
    d = decide(Signals(True, False, False, False), 0, GoldLimits(risk_per_trade_pct=100.0), RICH, QUOTE)
    assert d.action == "open"
