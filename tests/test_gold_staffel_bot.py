"""Tests für suche/gold_staffel_bot.py (Gold-Staffel auf Account 1, Kirons Wahl vom 10.11.2026 16:37 UTC).

- Regeln versiegelt, Stufen 2/4/6 R wie in suche/VORAB_gold_staffel.yaml, Konto ist Account 1 (nie das Hauptkonto).
- Einstieg: kopiert nur einen neuen Trade des Gold-Bots (nach dem Start, höchstens 60 Min. alt), gleiche Richtung,
  Größe und Stop, TP3 beim Broker.
- Wächter: Stop nach TP1 auf TP1, nach TP2 auf TP2, nie zurück, nur fertige Kerzen; zu nah: sofort raus.
- Schließt der Gold-Bot, schließt die Staffel auch. Schluss durch den Broker wird richtig benannt (TP3, Wächter-Stop).
"""
import json

import pandas as pd
import pytest

from suche import gold_staffel_bot as gs

HAUPT = "111111113150"


def _t(s: str) -> pd.Timestamp:
    return pd.Timestamp(s)


def _utc(s: str):
    return _t(s).tz_localize("UTC").to_pydatetime()


def kerze(zeit: str, hoch: float, tief: float, spread: float = 0.3) -> dict:
    return {"snapshotTimeUTC": zeit, "openPrice": {"bid": tief, "ask": tief + spread},
            "highPrice": {"bid": hoch, "ask": hoch + spread}, "lowPrice": {"bid": tief, "ask": tief + spread},
            "closePrice": {"bid": hoch, "ask": hoch + spread}}


class Broker:
    """Capital.com zum Testen: Hauptkonto aktiv, Gold auf Account 1."""

    def __init__(self, bid=4050.5, spread=0.3, frei=5000.0):
        self.account_id = HAUPT
        self.bid, self.spread, self.frei, self.min_dist = bid, spread, frei, 0.0
        self.kerzen: list[dict] = []
        self.pos: dict[str, dict] = {}
        self.posts: list[dict] = []
        self.puts: list[tuple[str, dict]] = []
        self.closed: list[str] = []
        self.acts: dict[str, list[dict]] = {}
        self.fill: float | None = None
        self.n = 0

    def accounts(self):
        return [{"accountId": HAUPT, "balance": {"available": 900}},
                {"accountId": gs.KONTO, "balance": {"available": self.frei}}]

    def switch_account(self, aid):
        self.account_id = aid

    def _get(self, path, **kw):
        assert path == "/session", path
        return {"accountId": self.account_id}

    def market(self, epic):
        if epic == "EURUSD":
            return {"snapshot": {"bid": 1.1599, "offer": 1.1601}}
        assert epic == "GOLD"
        return {"snapshot": {"bid": self.bid, "offer": round(self.bid + self.spread, 2), "marketStatus": "TRADEABLE",
                             "decimalPlacesFactor": 2},
                "instrument": {"currency": "USD", "lotSize": 1, "marginFactor": 5},
                "dealingRules": {"minDealSize": {"value": 0.01}, "minSizeIncrement": {"value": 0.01},
                                 "minStopOrProfitDistance": {"value": self.min_dist}}}

    def positions(self):
        assert self.account_id == gs.KONTO
        return list(self.pos.values())

    def prices(self, epic, res, n):
        assert self.account_id == gs.KONTO and epic == "GOLD" and res == "MINUTE_5"
        return self.kerzen[-n:]

    def _request(self, method, path, json=None):
        assert self.account_id == gs.KONTO
        if method == "POST":
            assert path == "/positions"
            self.posts.append(json)
            self.n += 1
            deal = f"S{self.n}"
            self.fill = round(self.bid + self.spread, 2) if json["direction"] == "BUY" else self.bid
            self.pos[deal] = {"market": {"epic": json["epic"]},
                              "position": {"dealId": deal, "size": json["size"], "stopLevel": json["stopLevel"],
                                           "profitLevel": json["profitLevel"]}}
        else:
            assert method == "PUT" and path.startswith("/positions/"), (method, path)
            deal = path.rsplit("/", 1)[1]
            self.puts.append((deal, json))
            self.pos[deal]["position"].update(json)

        class R:
            def json(self_inner):
                return {"dealReference": deal}
        return R()

    def confirm(self, ref):
        return {"dealStatus": "ACCEPTED", "level": self.fill, "affectedDeals": [{"dealId": ref}]}

    def close_position(self, deal):
        assert self.account_id == gs.KONTO
        self.closed.append(deal)
        self.pos.pop(deal)
        return {"dealStatus": "ACCEPTED", "level": self.bid}

    def activity(self, deal, since, until):
        return self.acts.get(deal, [])


START = "2026-11-11T09:00:00"


def gold(deal="G1", opened="2026-11-11T10:00:05.123", stand="2026-11-11T10:00:30+00:00", side="long", stop=4030.0):
    return {"stand": stand, "position": {"side": side, "direction": "BUY" if side == "long" else "SELL",
                                         "entry": 4050.0, "size": 1.0, "stop": stop, "dealId": deal,
                                         "opened_utc": opened, "upl": 0.0}}


def offen(br: Broker) -> dict:
    """Ein Lauf um 10:03: kopiert den Long des Gold-Bots (Ask 4050,8, Stop 4030, 1 R = 20,8)."""
    lf = gs.run(br, {"start": START}, _utc("2026-11-11 10:03"), gold=gold())
    assert [e["event"] for e in lf.log] == ["eröffnet"], lf.log
    return lf.st


# ---------- Regeln ----------

def test_regeln_versiegelt_und_stufen_wie_vorab():
    assert gs.vorab_ok()
    vorab = gs.VORAB.read_text(encoding="utf-8")
    assert "tp1: +2 R" in vorab and "tp2: +4 R" in vorab and "tp3: +6 R" in vorab
    assert gs.TP == (2.0, 4.0, 6.0)
    assert gs.KONTO.endswith("5310") and not gs.KONTO.endswith("3150")


def test_stufen_und_erreicht():
    assert gs.stufen(4000.0, 20.0, 1) == [4040.0, 4080.0, 4120.0]
    assert gs.stufen(4000.0, 20.0, -1) == [3960.0, 3920.0, 3880.0]
    tr = {"richtung": 1, "tp": [4040.0, 4080.0, 4120.0]}
    assert [gs.erreicht(tr, x) for x in (4039.9, 4040.0, 4079.9, 4080.0, 4119.0)] == [0, 1, 1, 2, 2]
    tr = {"richtung": -1, "tp": [3960.0, 3920.0, 3880.0]}
    assert [gs.erreicht(tr, x) for x in (3960.1, 3960.0, 3920.0)] == [0, 1, 2]


# ---------- Einstieg ----------

def test_kopiert_gold_trade_mit_stop_und_tp3():
    br = Broker()
    st = offen(br)
    body = br.posts[0]
    assert body == {"epic": "GOLD", "direction": "BUY", "size": 1.0, "guaranteedStop": False, "stopLevel": 4030.0,
                    "profitLevel": round(4050.8 + 6 * 20.8, 2)}
    tr = st["offen"]
    assert tr["entry"] == 4050.8 and tr["dist"] == pytest.approx(20.8) and tr["gold_deal"] == "G1"
    assert tr["tp"] == pytest.approx([4092.4, 4134.0, 4175.6]) and tr["stufe"] == 0
    assert br.account_id == HAUPT                        # zurück aufs Hauptkonto
    # nächster Lauf: kein zweiter Trade auf denselben Gold-Trade
    lf = gs.run(br, st, _utc("2026-11-11 10:08"), gold=gold())
    assert len(br.posts) == 1 and lf.st["offen"]["dealId"] == "S1"


def test_short_wird_mit_short_kopiert():
    br = Broker(bid=4050.0)
    lf = gs.run(br, {"start": START}, _utc("2026-11-11 10:03"), gold=gold(side="short", stop=4070.0))
    body = br.posts[0]
    assert body["direction"] == "SELL" and body["stopLevel"] == 4070.0
    assert body["profitLevel"] == pytest.approx(4050.0 - 6 * 20.0)
    assert lf.st["offen"]["tp"] == pytest.approx([4010.0, 3970.0, 3930.0])


def test_alte_trades_nicht_kopiert():
    br = Broker()
    # der offene Gold-Trade vom 06.11.: vor dem Start dieses Bots
    lf = gs.run(br, {}, _utc("2026-11-11 10:03"), gold=gold(opened="2026-11-06T07:11:28.526"))
    assert [e["event"] for e in lf.log] == ["Gold-Trade nicht kopiert"] and lf.log[0]["warum"].startswith("vor dem")
    lf = gs.run(br, lf.st, _utc("2026-11-11 10:08"), gold=gold(opened="2026-11-06T07:11:28.526"))
    assert lf.log == [] and not br.posts                 # gemerkt, keine Meldung mehr
    # mehr als 60 Min. alt
    lf = gs.run(br, {"start": START}, _utc("2026-11-11 11:05"), gold=gold())
    assert lf.log[0]["warum"].startswith("zu alt") and not br.posts


def test_kein_trade_wenn_gold_schon_offen_oder_zu_wenig_margin():
    br = Broker()
    br.pos["X"] = {"market": {"epic": "GOLD"}, "position": {"dealId": "X", "size": 1}}
    lf = gs.run(br, {"start": START}, _utc("2026-11-11 10:03"), gold=gold())
    assert lf.log[0]["event"].startswith("Gold schon offen") and not br.posts
    br = Broker(frei=150.0)                              # Marge 1 oz: 4050,8 * 5 % / 1,16 = 174,6 €
    lf = gs.run(br, {"start": START}, _utc("2026-11-11 10:03"), gold=gold())
    assert lf.log[0]["event"] == "zu wenig Margin" and not br.posts


def test_probelauf_schickt_nichts():
    br = Broker()
    lf = gs.run(br, {"start": START}, _utc("2026-11-11 10:03"), send=False, gold=gold())
    assert [e["event"] for e in lf.log] == ["würde öffnen"] and not br.posts and lf.st["offen"] is None


# ---------- Wächter ----------

def test_waechter_zieht_nach_tp1_und_tp2_und_nie_zurueck():
    br = Broker()
    st = offen(br)
    # 10:33: Hoch 4101 in einer fertigen Kerze, Kurs 4100 -> Stop auf TP1
    br.kerzen = [kerze("2026-11-11T10:05:00", 4060, 4049), kerze("2026-11-11T10:15:00", 4101, 4080),
                 kerze("2026-11-11T10:30:00", 4200, 4095)]   # 10:30 noch nicht fertig: zählt nicht
    br.bid = 4100.0
    lf = gs.run(br, st, _utc("2026-11-11 10:33"), gold=gold())
    assert br.puts == [("S1", {"stopLevel": 4092.4, "profitLevel": 4175.6})]
    assert lf.st["offen"]["stufe"] == 1 and lf.st["offen"]["stop"] == 4092.4
    assert [e["event"] for e in lf.log] == ["Wächter zieht nach"]
    # 11:03: TP2 erreicht -> Stop auf TP2
    br.kerzen.append(kerze("2026-11-11T10:55:00", 4141, 4120))
    br.bid = 4140.0
    lf = gs.run(br, lf.st, _utc("2026-11-11 11:03"), gold=gold())
    assert br.puts[-1] == ("S1", {"stopLevel": 4134.0, "profitLevel": 4175.6}) and lf.st["offen"]["stufe"] == 2
    # 11:08: Kurs fällt, Stop bleibt auf TP2
    br.bid = 4136.0
    lf = gs.run(br, lf.st, _utc("2026-11-11 11:08"), gold=gold())
    assert len(br.puts) == 2 and lf.log == [] and lf.st["offen"]["stop"] == 4134.0
    # Broker schließt am Wächter-Stop
    br.pos.clear()
    br.acts["S1"] = [{"dateUTC": "2026-11-11T11:10:00", "source": "SL", "type": "POSITION", "status": "ACCEPTED",
                      "details": {"level": 4134.0, "actions": [{"actionType": "POSITION_CLOSED"}]}}]
    lf = gs.run(br, lf.st, _utc("2026-11-11 11:13"), gold=gold())
    t = lf.fertige[0]
    assert t["quelle"] == "Wächter-Stop TP2" and t["r"] == pytest.approx(4.0)
    assert t["pnl_eur"] == pytest.approx((4134.0 - 4050.8) / 1.16, abs=0.01)
    assert lf.st["offen"] is None and lf.st["trades"] == 1 and lf.st["summe_r"] == pytest.approx(4.0)


def test_waechter_schliesst_wenn_kurs_schon_zu_nah():
    br = Broker()
    st = offen(br)
    br.kerzen = [kerze("2026-11-11T10:15:00", 4093, 4080)]  # TP1 4092,4 berührt
    br.bid = 4088.0                                       # jetzt schon unter TP1
    lf = gs.run(br, st, _utc("2026-11-11 10:33"), gold=gold())
    assert br.closed == ["S1"] and not br.puts
    t = lf.fertige[0]
    assert t["quelle"].startswith("Wächter TP1") and t["r"] == pytest.approx((4088.0 - 4050.8) / 20.8, abs=1e-3)


def test_bester_kurs_bleibt_ueber_die_kerzen_hinaus():
    """Die Kerzen reichen nur 25 Std. zurück, der beste Kurs steht darum auch im Zustand."""
    br = Broker()
    st = offen(br)
    st["offen"]["bester"] = 4100.0                        # aus einem früheren Lauf
    br.kerzen, br.bid = [], 4095.0
    lf = gs.run(br, st, _utc("2026-11-12 14:03"), gold=gold())
    assert br.puts == [("S1", {"stopLevel": 4092.4, "profitLevel": 4175.6})]


# ---------- Schluss ----------

def test_gold_bot_zu_schliesst_auch():
    br = Broker()
    st = offen(br)
    # Stand des Gold-Bots älter als unser Einstieg: nichts
    lf = gs.run(br, st, _utc("2026-11-11 10:08"), gold={"stand": "2026-11-11T10:00:30+00:00", "position": None})
    assert not br.closed and lf.st["offen"]
    # neuer Stand ohne Position: der Gold-Bot hat geschlossen
    br.bid = 4060.0
    lf = gs.run(br, lf.st, _utc("2026-11-11 11:13"), gold={"stand": "2026-11-11T11:11:30+00:00", "position": None})
    assert br.closed == ["S1"] and lf.fertige[0]["quelle"] == "Gold-Bot zu"
    assert lf.fertige[0]["r"] == pytest.approx((4060.0 - 4050.8) / 20.8, abs=1e-3)


def test_broker_schliesst_mit_tp3_oder_stop():
    br = Broker()
    st = offen(br)
    br.pos.clear()
    br.acts["S1"] = [{"dateUTC": "2026-11-11T12:00:00", "source": "TP", "type": "POSITION", "status": "ACCEPTED",
                      "details": {"level": 4175.6, "actions": [{"actionType": "POSITION_CLOSED"}]}}]
    lf = gs.run(br, st, _utc("2026-11-11 12:03"), gold=gold())
    assert lf.fertige[0]["quelle"] == "TP3" and lf.fertige[0]["r"] == pytest.approx(6.0)
    # ohne lesbare Kontoaktivität: der Stop als Schätzung
    br = Broker()
    st = offen(br)
    br.pos.clear()
    lf = gs.run(br, st, _utc("2026-11-11 12:03"), gold=gold())
    assert lf.fertige[0]["quelle"] == "Stop (geschätzt)" and lf.fertige[0]["r"] == pytest.approx(-1.0)


def test_ohne_siegel_nichts(monkeypatch):
    monkeypatch.setattr(gs, "vorab_ok", lambda: False)
    br = Broker()
    lf = gs.run(br, {"start": START}, _utc("2026-11-11 10:03"), gold=gold())
    assert lf.log[0]["event"].startswith("Regeln nicht versiegelt") and not br.posts and br.account_id == HAUPT


# ---------- Journal ----------

def test_gold_position_aus_dem_chart(tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "JOURNAL", tmp_path)
    assert gs.gold_position() is None
    (tmp_path / "gold-chart.json").write_text(json.dumps({"updated_utc": "2026-11-10T16:11:28+00:00",
                                                          "position": gold()["position"]}), encoding="utf-8")
    g = gs.gold_position()
    assert g["stand"] == "2026-11-10T16:11:28+00:00" and g["position"]["dealId"] == "G1"
    (tmp_path / "gold-chart.json").write_text(json.dumps({"updated_utc": "x", "position": None}), encoding="utf-8")
    assert gs.gold_position()["position"] is None


def test_journal_ohne_neues_nur_alle_30_minuten(tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "JOURNAL", tmp_path)
    tr = {"dealId": "S1", "stufe": 0, "bester": 4060.0}
    st = {"format": 1, "offen": tr, "kopiert": ["G1"], "trades": 0, "summe_r": 0.0, "summe_eur": 0.0,
          "start": START, "stand": "2026-11-11T10:03:00"}
    assert gs.schreiben(st, [], []) is True
    nur_kurs = {**st, "offen": {**tr, "bester": 4070.0}, "stand": "2026-11-11T10:08:00"}
    assert gs.schreiben(nur_kurs, [], []) is False                      # nur Zeit und bester Kurs neu
    ev = [{"time": "2026-11-11T10:13:00", "bot": gs.BOT_ID, "event": "Wächter zieht nach", "stufe": 1}]
    assert gs.schreiben({**st, "stand": "2026-11-11T10:13:00"}, ev, []) is True
    assert gs.schreiben({**st, "stand": "2026-11-11T10:43:01"}, [], []) is True     # Lebenszeichen
    karte = json.loads((tmp_path / "gold-staffel.json").read_text(encoding="utf-8"))
    assert karte["stand"] == "2026-11-11T10:43:01" and karte["konto"] == "…5310"
    assert (tmp_path / "gold-staffel" / "log.jsonl").read_text(encoding="utf-8").count("\n") == 1


def test_ohne_zugangsdaten_nichts(monkeypatch, capsys):
    for k in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_API_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    assert gs.main([]) == 0
    assert "übersprungen" in capsys.readouterr().out
