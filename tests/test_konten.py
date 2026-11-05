"""Tests für eigene Demokonten je Bot (gold/bot/konten.py, suche/demo_bots.py, gold/bot/runner.py)."""
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from gold.bot import konten
from gold.bot.capital import CapitalClient
from suche import demo_bots as db
from tests.test_demo_bots import CFG, R3, FakeClient, bars_until, stub_prepare

STAMP = "2026-11-03T10:46:00"
BOTS = [{"id": "oil-brent", "konto_namen": ["brent"]}, {"id": "j225", "konto_namen": ["japan"]},
        {"id": "gold2", "eigenes_konto": True, "konto_namen": ["2.0"]}]


def acc(aid, name="Demo", bal=1000.0, preferred=False):
    return {"accountId": aid, "accountName": name, "currency": "EUR", "preferred": preferred,
            "balance": {"balance": bal, "available": bal}}


def test_first_run_records_the_main_account_and_assigns_by_name_then_in_order():
    accounts = [acc("1001", "Haupt", 995.17, True), acc("1003", "Konto Japan"), acc("1002", "Demo 2"), acc("1004", "Demo 3")]
    k, log = konten.zuordnen({}, accounts, BOTS, {"1002": True, "1003": True, "1004": True}, "1001", set(), STAMP)
    assert k["haupt"] == "1001"
    assert k["zuordnung"] == {"j225": "1003", "oil-brent": "1002", "gold2": "1004"}
    assert k["start"]["1001"] == 995.17 and k["start"]["1002"] == 1000.0
    assert [x["fuer"] for x in k["konten"]] == ["gold", "oil-brent", "j225", "gold2"]
    assert {e["wie"] for e in log if e["event"] == "konto zugeordnet"} == {"Name", "Reihenfolge"}
    # zweiter Lauf: nichts ändert sich, auch wenn das Hauptkonto nicht mehr bevorzugt ist
    k2, log2 = konten.zuordnen(k, accounts, BOTS, {}, "1004", set(), STAMP)
    assert k2["haupt"] == "1001" and k2["zuordnung"] == k["zuordnung"] and not [e for e in log2 if e["event"] != "hauptkonto"]


def test_busy_accounts_and_bots_with_open_positions_wait():
    accounts = [acc("1001", preferred=True), acc("1002"), acc("1003")]
    k, _ = konten.zuordnen({}, accounts, BOTS, {"1002": False, "1003": True}, "1001", {"oil-brent"}, STAMP)
    assert k["zuordnung"] == {"j225": "1003"}            # 1002 hat eine Position, oil-brent hat noch eine offene
    # Konto gelöscht: Zuordnung fällt weg
    k2, log = konten.zuordnen(k, [acc("1001", preferred=True)], BOTS, {}, "1001", set(), STAMP)
    assert k2["zuordnung"] == {} and any(e["event"] == "konto weg" for e in log)


def test_every_assigned_account_gets_a_start_balance():
    """Kritik D7 (05.11.2026): das US500-Konto stand in zuordnung, aber ohne start. Fehlt er, gilt der heutige Stand."""
    accounts = [acc("1001", preferred=True), acc("1002", "US500", 1000.0)]
    alt = {"haupt": "1001", "zuordnung": {"oil-brent": "1002"}, "start": {"1001": 995.17}}
    k, _ = konten.zuordnen(alt, accounts, BOTS, {}, "1001", set(), STAMP)
    assert k["start"] == {"1001": 995.17, "1002": 1000.0}
    k2, _ = konten.zuordnen(k, [acc("1001", preferred=True), acc("1002", "US500", 990.0)], BOTS, {}, "1001", set(), STAMP)
    assert k2["start"]["1002"] == 1000.0                 # einmal gesetzt, bleibt der Startstand


def test_client_switches_only_when_needed():
    class Resp:
        ok, status_code, headers = True, 200, {"X-SECURITY-TOKEN": "neu"}

        @staticmethod
        def json():
            return {}

    class Sess:
        calls = []

        def request(self, method, url, **kw):
            self.calls.append((method, url.rsplit("/", 1)[-1], kw.get("json")))
            return Resp()

    c = CapitalClient("k", "i", "p", session=Sess())
    c._tokens, c.account_id = {"CST": "a", "X-SECURITY-TOKEN": "alt"}, "1001"
    c.switch_account("1001")
    assert Sess.calls == []
    c.switch_account("1002")
    assert Sess.calls == [("PUT", "session", {"accountId": "1002"})]
    assert c.account_id == "1002" and c._tokens["X-SECURITY-TOKEN"] == "neu"


class MultiClient(FakeClient):
    """Mehrere Demokonten: Positionen und Orders gelten für das aktive Konto."""

    def __init__(self, bars, ids=("1001", "1002", "1003")):
        self.ids = list(ids)
        self.account_id = ids[0]
        self.by_acc = {i: [] for i in ids}
        self.switches = []
        super().__init__(bars)

    def accounts(self):
        return [acc(i, preferred=(i == self.ids[0])) for i in self.ids]

    def switch_account(self, aid):
        if aid != self.account_id:
            self.switches.append(aid)
            self.account_id = aid

    @property
    def positions_(self):
        return self.by_acc[self.account_id]

    @positions_.setter
    def positions_(self, value):
        self.by_acc[self.account_id] = value


def test_each_bot_trades_on_its_own_account_and_gold2_needs_one(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "JDIR", tmp_path)
    bars = bars_until("2026-11-03 10:30", n=600)
    monkeypatch.setattr(db, "prepare", stub_prepare({"2026-11-03 10:30": "long"}))
    monkeypatch.setattr(db, "fetch", lambda client, epic, tf: (client._prices(client.bars), client._prices(client.bars)))
    cfg = {**CFG, "reserve_margin_eigen_eur": 0,
           "extra_bots": [{**CFG["bots"][0], "id": "x-gold2", "epic": "GBPUSD", "eigenes_konto": True}]}
    # nur ein Konto: der Extra-Bot wartet, der normale Bot handelt auf dem Hauptkonto
    one = MultiClient(bars, ids=("1001",))
    kont: dict = {}
    st, _, _ = db.run(one, cfg, R3, {}, datetime(2026, 11, 3, 10, 46, tzinfo=timezone.utc), kont=kont)
    assert st["bots"]["x-gold2"]["status"] == "wartet auf ein eigenes Demokonto"
    assert len(one.by_acc["1001"]) == 1 and kont["haupt"] == "1001"
    # drei Konten: jeder Bot bekommt eins, die Order landet dort, am Ende ist das Hauptkonto aktiv
    c = MultiClient(bars)
    kont = {}
    st, _, log = db.run(c, cfg, R3, {}, datetime(2026, 11, 3, 10, 46, tzinfo=timezone.utc), kont=kont)
    assert kont["zuordnung"] == {"t-EURUSD": "1002", "x-gold2": "1003"}
    assert [p["market"]["epic"] for p in c.by_acc["1002"]] == ["EURUSD"]
    assert [p["market"]["epic"] for p in c.by_acc["1003"]] == ["GBPUSD"] and c.by_acc["1001"] == []
    assert st["bots"]["t-EURUSD"]["open"]["konto"] == "1002" and c.account_id == "1001"
    assert st["konten"]["x-gold2"]["eigen"] and st["konten"]["x-gold2"]["id"] == "…1003"
    cp = db.cockpit(cfg, st, [])
    assert [b["id"] for b in cp["bots"]] == ["t-EURUSD", "x-gold2"] and cp["bots"][1]["extra"]
    assert cp["bots"][0]["position"]["side"] == "long"


def test_open_position_on_the_main_account_moves_only_after_it_is_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "JDIR", tmp_path)
    bars = bars_until("2026-11-03 10:30", n=600)
    monkeypatch.setattr(db, "prepare", stub_prepare({}))
    monkeypatch.setattr(db, "fetch", lambda client, epic, tf: (client._prices(client.bars), client._prices(client.bars)))
    c = MultiClient(bars, ids=("1001", "1002"))
    c.by_acc["1001"] = [{"market": {"epic": "EURUSD"}, "position": {"dealId": "D7", "direction": "BUY", "level": 1.1}}]
    state = {"start_utc": "2026-11-03T07:14:00", "ende_utc": "2026-11-09T07:14:00",
             "bots": {"t-EURUSD": {"open": {"dealId": "D7", "side": 1, "t_sig": "2026-11-03 09:00:00", "entry": 1.1,
                                            "stop_dist": 0.001, "tp_dist": None, "size": 100,
                                            "opened_utc": "2026-11-03T09:16:00"}}}}
    kont = {"haupt": "1001", "zuordnung": {}}
    st, trades, _ = db.run(c, CFG, R3, state, datetime(2026, 11, 3, 10, 46, tzinfo=timezone.utc), kont=kont)
    assert kont["zuordnung"] == {} and not trades and st["bots"]["t-EURUSD"]["open"]["dealId"] == "D7"


def test_config_extra_bots_only_on_an_own_account_and_end_moved():
    cfg = yaml.safe_load(Path("suche/demo_bots.yaml").read_text(encoding="utf-8"))
    assert cfg["extra_bots"] and all(b.get("eigenes_konto") is True for b in cfg["extra_bots"] if b["epic"] == "GOLD")
    assert not {b["epic"] for b in cfg["extra_bots"]} & {b["epic"] for b in cfg["bots"]}
    ids = [b["id"] for b in db.alle_bots(cfg)]
    assert len(ids) == len(set(ids))
    assert cfg["wochentest_ende_utc"] == "2026-11-10T09:45:00" and cfg["ende_utc"] > cfg["wochentest_ende_utc"]
    # Bewertung 2025-2026: nur nicht bestandene Bots geben ihr Konto ab, jeder an einen anderen Nachfolger
    abl = cfg["abgeloest"]
    assert set(abl) <= set(ids) and "oil-brent" not in abl and len({n["an"] for n in abl.values()}) == len(abl)


def test_gold_runner_uses_the_main_account(tmp_path):
    src = Path("gold/bot/runner.py").read_text(encoding="utf-8").split("def run(")[1].split("quote_for(")[0]
    assert "konten.haupt_von(" in src and "konten.wechseln(client, haupt)" in src
    # neue Konten, eines davon bevorzugt: das Hauptkonto bleibt das bekannte (Endung 3150)
    accounts = [acc("2001", preferred=True), acc("9993150"), acc("2002")]
    assert konten.haupt_von(accounts, {}, "2001") == "9993150"
    assert konten.haupt_von(accounts, {"haupt": "2002"}, "2001") == "2002"
    assert konten.haupt_von([acc("2001", preferred=True)], {}, None) == "2001"
    konten.save({"haupt": "1001"}, tmp_path)
    assert konten.load(tmp_path)["haupt"] == "1001" and konten.load(tmp_path / "fehlt") == {}


def test_weekly_report_reads_the_journal_and_names_every_bot(monkeypatch, tmp_path):
    import json

    from suche import wochenbericht as wb
    (tmp_path / "demo-bots").mkdir()
    (tmp_path / "demo-bots.json").write_text(json.dumps({
        "start_utc": "2026-11-03T07:14:21", "bots": [
            {"id": "us30", "status": "Position offen", "konto": {"id": "…1002", "eigen": True, "seit_start": -3.5},
             "position": {"side": "short", "entry": 47000, "upl": -3.5, "opened_utc": "2026-11-03T15:01:00"}}]}))
    (tmp_path / "demo-bots" / "trades.jsonl").write_text(json.dumps(
        {"bot": "copper", "r": 2.0, "pnl_eur": 4.0, "side": "long", "closed_utc": "2026-11-03T14:00:00"}) + "\n")
    (tmp_path / "gold-trades.jsonl").write_text(json.dumps(
        {"r": -1.01, "pnl_eur": -4.83, "side": "short", "closed_utc": "2026-11-03T01:11:37+00:00"}) + "\n")
    monkeypatch.setattr(wb, "J", tmp_path)
    s = wb.stand(datetime(2026, 11, 3, 19, 0, tzinfo=timezone.utc), seit=wb._ts("2026-11-03T08:00"))
    ids = [b["id"] for b in s["bots"]]
    assert ids[:2] == ["gold", "oil-brent"] and {"gold2", "dax"} <= set(ids)
    assert s["bots"][0]["live"]["trades"] == 1            # Gold zählt jeden Demo-Trade seit 31.10. (Kritik D7)
    assert s["gesamt"] == {"trades": 2, "gewonnen": 1, "sum_r": 0.99, "pf_r": 1.98, "eur": -0.83}
    assert [e["art"] for e in s["neu"]] == ["zu", "auf"]
    t = wb.text(s)
    assert "Dow Jones (US30 15-Min.) | eigenes …1002, -3,50 € |" in t and "Verkauf offen" in t
    assert "wartet auf ein eigenes Demokonto" in t and "Kupfer" in t


# ---------- Schluss beim Broker richtig buchen (Fehler vom 03.11.2026: Dow-Trades zum Einstiegskurs gebucht) ----------

def _acts(entry, stop_px):
    """So liefert Capital.com die Kontoaktivität: neueste zuerst, die Eröffnung durch den Bot mit source USER."""
    return [{"dateUTC": "2026-11-03T13:31:20.100", "source": "SL", "type": "POSITION", "status": "ACCEPTED",
             "details": {"level": stop_px, "actions": [{"actionType": "POSITION_CLOSED"}]}},
            {"dateUTC": "2026-11-03T10:46:47.300", "source": "USER", "type": "POSITION", "status": "ACCEPTED",
             "details": {"level": entry, "actions": [{"actionType": "POSITION_OPENED"}]}}]


def test_broker_exit_never_takes_the_opening_as_the_close():
    class C:
        acts = {"D1": _acts(51713.0, 51765.9)}

        def activity(self, deal_id, since, until):
            return self.acts.get(deal_id, [])

    now = datetime(2026, 11, 3, 13, 31, tzinfo=timezone.utc)
    assert db.broker_exit(C(), {"dealId": "D1", "opened_utc": "2026-11-03T10:46:47.387"}, now) == (51765.9, "SL")
    C.acts["D1"] = C.acts["D1"][1:]                       # nur die Eröffnung: kein Schluss, dann schätzt der Bot den Stop
    assert db.broker_exit(C(), {"dealId": "D1", "opened_utc": "2026-11-03T10:46:47.387"}, now) == (None, "")


def test_wrongly_booked_trades_are_rebooked_from_their_own_account(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "JDIR", tmp_path)
    bars = bars_until("2026-11-03 13:30", n=600)
    monkeypatch.setattr(db, "prepare", stub_prepare({}))
    monkeypatch.setattr(db, "fetch", lambda client, epic, tf: (client._prices(client.bars), client._prices(client.bars)))
    c = MultiClient(bars, ids=("1001", "1002"))
    c.acts = {"D1": _acts(1.1, 1.099)}
    wrong = {"bot": "t-EURUSD", "name": "T", "epic": "EURUSD", "zeitrahmen": "15min", "logik": "gold", "side": "long",
             "dealId": "D1", "size": 100, "entry": 1.1, "exit": 1.1, "stop_dist": 0.001, "tp_dist": None,
             "signal_bar": "2026-11-03 10:30:00", "opened_utc": "2026-11-03T10:46:47.387",
             "closed_utc": "2026-11-03T13:31:34.905159", "reason": "von Hand geschlossen", "r": -0.0, "pnl": -0.0,
             "waehrung": "USD", "pnl_eur": -0.0, "geschaetzt": False, "konto": "…1002"}
    ok = {**wrong, "dealId": "D2", "exit": 1.102, "r": 2.0, "reason": "Stop (laut Kerzen)"}
    buchungen = [wrong, ok]
    kont = {"haupt": "1001", "zuordnung": {"t-EURUSD": "1002"}}
    _, _, log = db.run(c, CFG, R3, {}, datetime(2026, 11, 3, 19, 1, tzinfo=timezone.utc), kont=kont, buchungen=buchungen)
    t = buchungen[0]
    assert t["exit"] == 1.099 and t["r"] == pytest.approx(-1.0, abs=0.01) and t["reason"] == "Stop beim Broker"
    assert t["closed_utc"] == "2026-11-03T13:31:34.905159" and t["korrigiert"] and t["konto"] == "…1002"
    assert buchungen[1] is ok and [e["event"] for e in log].count("nachgebucht") == 1
    assert "1002" in c.switches and c.account_id == "1001"
    # nächster Lauf: nichts mehr zu tun
    _, _, log2 = db.run(c, CFG, R3, {}, datetime(2026, 11, 3, 19, 16, tzinfo=timezone.utc), kont=kont, buchungen=buchungen)
    assert not [e for e in log2 if e["event"] == "nachgebucht"]


def _abl_setup(monkeypatch, tmp_path, signal):
    monkeypatch.setattr(db, "JDIR", tmp_path)
    bars = bars_until("2026-11-03 10:30", n=600)
    monkeypatch.setattr(db, "prepare", stub_prepare(signal))
    monkeypatch.setattr(db, "fetch", lambda client, epic, tf: (client._prices(client.bars), client._prices(client.bars)))
    cfg = {**CFG, "reserve_margin_eigen_eur": 0,
           "extra_bots": [{**CFG["bots"][0], "id": "x-gold2", "epic": "GBPUSD", "eigenes_konto": True}],
           "abgeloest": {"t-EURUSD": {"an": "r6-test", "seit": "2026-11-04", "grund": "Bewertung 2025-2026"}}}
    kont = {"haupt": "1001", "zuordnung": {"t-EURUSD": "1002", "x-gold2": "1003"}, "start": {},
            "konten": [{"id": "…1002", "fuer": "t-EURUSD"}, {"id": "…1003", "fuer": "x-gold2"}]}
    return MultiClient(bars), cfg, kont


def test_replaced_bot_trades_no_more_and_hands_its_account_to_the_successor(monkeypatch, tmp_path):
    c, cfg, kont = _abl_setup(monkeypatch, tmp_path, {"2026-11-03 10:30": "long"})
    now = datetime(2026, 11, 3, 10, 46, tzinfo=timezone.utc)
    st, trades, log = db.run(c, cfg, R3, {}, now, kont=kont)
    assert c.by_acc["1002"] == [] and [p["market"]["epic"] for p in c.by_acc["1003"]] == ["GBPUSD"]
    assert kont["zuordnung"] == {"r6-test": "1002", "x-gold2": "1003"}
    assert kont["uebergaben"][0] | {"zeit": None} == {"zeit": None, "konto": "…1002", "konto_id": "1002", "name": "Demo",
                                                     "von": "t-EURUSD", "an": "r6-test", "kontostand": 1000.0}
    assert {e["id"]: e["fuer"] for e in kont["konten"]}["…1002"] == "r6-test" and kont["start"]["1002"] == 1000.0
    assert [e["event"] for e in log].count("konto übergeben") == 1
    assert st["bots"]["t-EURUSD"]["status"] == "abgelöst, Konto an r6-test" and st["konten"]["t-EURUSD"] is None
    cp = db.cockpit(cfg, st, [])
    assert cp["bots"][0]["abgeloest"]["an"] == "r6-test" and cp["bots"][1]["abgeloest"] is None
    # nächster Lauf: der abgelöste Bot bekommt kein Konto zurück, nichts wird doppelt übergeben
    st2, _, log2 = db.run(c, cfg, R3, st, now, kont=kont)
    assert kont["zuordnung"] == {"r6-test": "1002", "x-gold2": "1003"} and len(kont["uebergaben"]) == 1
    assert not [e for e in log2 if e.get("event") in ("konto übergeben", "konto zugeordnet")]


def test_replaced_bot_with_an_open_position_keeps_its_account_until_the_position_is_closed(monkeypatch, tmp_path):
    c, cfg, kont = _abl_setup(monkeypatch, tmp_path, {"2026-11-03 10:30": "long"})
    c.by_acc["1002"] = [{"market": {"epic": "EURUSD"}, "position": {"dealId": "D7", "direction": "BUY", "level": 1.1}}]
    state = {"start_utc": "2026-11-03T07:14:00", "ende_utc": "2026-11-10T09:45:00",
             "bots": {"t-EURUSD": {"open": {"dealId": "D7", "side": 1, "t_sig": "2026-11-03 09:00:00", "entry": 1.1,
                                            "stop_dist": 0.001, "tp_dist": None, "size": 100, "konto": "1002",
                                            "opened_utc": "2026-11-03T09:16:00"}}}}
    now = datetime(2026, 11, 3, 10, 46, tzinfo=timezone.utc)
    st, trades, log = db.run(c, cfg, R3, state, now, kont=kont)
    assert kont["zuordnung"]["t-EURUSD"] == "1002" and "r6-test" not in kont["zuordnung"]
    assert st["bots"]["t-EURUSD"]["open"]["dealId"] == "D7" and not trades
    # Stop beim Broker ausgelöst: Trade gebucht, kein neuer Einstieg trotz Signal, Konto geht an den Nachfolger
    c.by_acc["1002"] = []
    st["bots"]["t-EURUSD"].pop("last_bar", None)
    st2, trades2, log2 = db.run(c, cfg, R3, st, now, kont=kont)
    assert len(trades2) == 1 and trades2[0]["bot"] == "t-EURUSD" and c.by_acc["1002"] == []
    assert st2["bots"]["t-EURUSD"]["open"] is None and kont["zuordnung"].get("r6-test") == "1002"
    assert "t-EURUSD" not in kont["zuordnung"]


def test_portfolio_role_turns_active_once_the_account_is_mapped():
    pf = {"bots": [{"id": "r6-test", "rolle": "wartet"}, {"id": "t-EURUSD", "rolle": "abgeloest"},
                   {"id": "x", "rolle": "wartet"}]}
    assert db.portfolio_rollen(pf, {"r6-test": "1003"}) is True
    assert [b["rolle"] for b in pf["bots"]] == ["aktiv", "abgeloest", "wartet"]
    assert db.portfolio_rollen(pf, {"r6-test": "1003"}) is False


def test_bot_replaced_by_the_demo_check_without_successor_frees_its_account(monkeypatch, tmp_path):
    """Prüfung nach 15/40 Demo-Trades (suche/demo_pruefung.py): abgelöst über journal/konten.json, ohne Nachfolger."""
    c, cfg, kont = _abl_setup(monkeypatch, tmp_path, {"2026-11-03 10:30": "long"})
    cfg = {k: v for k, v in cfg.items() if k != "abgeloest"}
    kont["abgeloest"] = {"x-gold2": {"an": None, "grund": "Test"}}
    now = datetime(2026, 11, 3, 10, 46, tzinfo=timezone.utc)
    st, _, log = db.run(c, cfg, R3, {}, now, kont=kont)
    assert c.by_acc["1003"] == [] and kont["zuordnung"] == {"t-EURUSD": "1002"} and kont["frei"] == ["1003"]
    assert st["bots"]["x-gold2"]["status"] == "abgelöst, Konto wird frei" and "konto frei" in [e["event"] for e in log]
    # das freie Konto nimmt sich kein anderer Bot dieses Laufs
    st2, _, _ = db.run(c, cfg, R3, st, now, kont=kont)
    assert kont["zuordnung"] == {"t-EURUSD": "1002"} and kont["frei"] == ["1003"]
