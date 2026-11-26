"""Bündel ohne Gold und Gold-Bündel (suche/buendel_bot.py): kopieren Trades der Mitglieder auf "Vortag USDJPY",
nur mit erfundenen Kontonummern und einem erfundenen Broker."""
import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from suche import buendel_bot as bb
from suche.demo_bots import Quote

HAUPT, QUELLE, BUENDEL = "9000003150", "9000001111", "9000002222"
JETZT = datetime(2026, 11, 23, 15, 0, tzinfo=timezone.utc)
REGEL = bb.lade_regel()                                  # die erste Regel von buendel9 (9 Mitglieder)
OHNE_GOLD = bb.lade_regel(bb.VORAB_OHNE_GOLD)            # buendel9 seit 26.11.2026
GOLD = bb.lade_regel(bb.VORAB_GOLD)                      # das Gold-Bündel seit 26.11.2026


class Antwort:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class Broker:
    """Capital.com zum Testen: Hauptkonto, ein Konto der Mitglieder und das Bündel-Konto."""

    def __init__(self, frei=990.0, hedging=True, margin=5.0):
        self.account_id = HAUPT
        self.frei, self.hedging, self.margin = frei, hedging, margin
        self.pos: dict[str, dict[str, dict]] = {HAUPT: {}, QUELLE: {}, BUENDEL: {}}
        self.acts: dict[str, list] = {}
        self.calls: list = []
        self.refs: dict = {}
        self.nr = 0
        self.order_fehler = False
        self.hedging_fehler = False
        self.kurs = {"DE40": 20000.0, "GOLD": 4000.0, "GBPUSD": 1.30}
        self.uhr = JETZT                                 # Eröffnungszeit neuer Positionen beim Broker

    def accounts(self):
        return [{"accountId": HAUPT, "accountName": "Account", "currency": "EUR", "balance": {"available": 900.0}},
                {"accountId": QUELLE, "accountName": "Account 1", "currency": "EUR", "balance": {"available": 900.0}},
                {"accountId": BUENDEL, "accountName": "Vortag USDJPY", "currency": "EUR",
                 "balance": {"balance": 1000.0, "available": self.frei}}]

    def switch_account(self, aid):
        self.calls.append(("konto", aid))
        self.account_id = aid

    def quelle(self, deal, epic="DE40", richtung="BUY", level=20000.0, stop=19950.0, ziel=20500.0, alter_min=5):
        self.pos[QUELLE][deal] = {"dealId": deal, "epic": epic, "direction": richtung, "level": level, "size": 0.1,
                                  "stopLevel": stop, "profitLevel": ziel,
                                  "createdDateUTC": (JETZT - timedelta(minutes=alter_min)).strftime("%Y-%m-%dT%H:%M:%S.000")}

    def positions(self):
        return [{"market": {"epic": p["epic"]}, "position": p} for p in self.pos[self.account_id].values()]

    def market(self, epic):
        if epic in self.kurs:
            cur = {"DE40": "EUR", "GOLD": "USD", "GBPUSD": "USD"}[epic]
            b = self.kurs[epic]
            return {"snapshot": {"bid": b, "offer": b + (1.2 if epic == "DE40" else 0.3), "decimalPlacesFactor": 2,
                                 "marketStatus": "TRADEABLE"},
                    "instrument": {"currency": cur, "lotSize": 1, "marginFactor": self.margin,
                                   "marginFactorUnit": "PERCENTAGE"},
                    "dealingRules": {"minDealSize": {"value": 0.01}, "minSizeIncrement": {"value": 0.01},
                                     "minStopOrProfitDistance": {"unit": "POINTS", "value": 1.0}}}
        return {"snapshot": {"bid": 1.08, "offer": 1.08}}          # EURUSD

    def _get(self, path, **params):
        assert path == "/accounts/preferences" and self.account_id == BUENDEL
        return {"hedgingMode": self.hedging}

    def _request(self, method, path, json=None):
        assert self.account_id == BUENDEL, "der Bot darf nur auf dem Bündel-Konto etwas ändern"
        self.calls.append((method, path, json))
        if path == "/accounts/preferences":
            if self.hedging_fehler:
                raise RuntimeError("geht nicht")
            self.hedging = bool(json["hedgingMode"])
            return Antwort({})
        if method == "PUT":
            deal = path.rsplit("/", 1)[1]
            self.pos[BUENDEL][deal].update(json)
            self.nr += 1
            self.refs[f"R{self.nr}"] = {"dealStatus": "ACCEPTED"}
            return Antwort({"dealReference": f"R{self.nr}"})
        assert method == "POST" and path == "/positions"
        if self.order_fehler:
            raise RuntimeError("Zeitüberschreitung")
        self.nr += 1
        ref, deal = f"R{self.nr}", f"K{self.nr}"
        level = self.market(json["epic"])["snapshot"]["offer" if json["direction"] == "BUY" else "bid"]
        self.pos[BUENDEL][deal] = {"dealId": deal, "epic": json["epic"], "direction": json["direction"],
                                   "level": level, "size": json["size"], "stopLevel": json["stopLevel"],
                                   "profitLevel": json.get("profitLevel"),
                                   "createdDateUTC": (self.uhr + timedelta(seconds=20)).strftime("%Y-%m-%dT%H:%M:%S.000")}
        # wie Capital.com: oben die Deal-ID der Order, unter affectedDeals die der Position
        self.refs[ref] = {"dealStatus": "ACCEPTED", "dealId": f"O{self.nr}", "affectedDeals": [{"dealId": deal}],
                          "level": level}
        return Antwort({"dealReference": ref})

    def confirm(self, ref):
        return self.refs.get(ref, {"dealStatus": "ACCEPTED"})

    def close_position(self, deal_id):
        assert self.account_id == BUENDEL
        self.calls.append(("DELETE", deal_id))
        p = self.pos[BUENDEL].pop(deal_id)
        b = self.kurs[p["epic"]]
        return {"dealStatus": "ACCEPTED", "level": b if p["direction"] == "BUY" else b + 1.2}

    def activity(self, deal_id, since, until):
        return self.acts.get(deal_id, [])

    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]


@pytest.fixture(autouse=True)
def umgebung(monkeypatch):
    monkeypatch.setattr(bb, "KONTO", BUENDEL)
    monkeypatch.setattr(bb, "vorab_ok", lambda *a, **k: True)
    monkeypatch.setattr(bb, "_konto_aus_code", lambda modul: QUELLE)


def journal(tmp_path, scalp=None, gold_cb=None, us500=None, welt=None, vergleich=None):
    """Dateien der Mitglieder im erfundenen Journal."""
    for bot, m in REGEL["mitglieder"].items():
        p = tmp_path / m["datei"]
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text("{}", encoding="utf-8")
    if scalp is not None:
        (tmp_path / "scalp-de40/state.json").write_text(json.dumps({"offen": scalp}), encoding="utf-8")
    if gold_cb is not None:
        (tmp_path / "gold-state.json").write_text(json.dumps({"open_trade": gold_cb}), encoding="utf-8")
    if us500 is not None:
        (tmp_path / "us500-bot/state.json").write_text(json.dumps({"open": us500, "konto_id": QUELLE}), encoding="utf-8")
    if welt is not None:
        (tmp_path / "welt-ausbruch4h/state.json").write_text(
            json.dumps({"maerkte": {"GRXEUR": {"trade": welt}, "UKXGBP": {"trade": None}}}), encoding="utf-8")
    if vergleich is not None:
        (tmp_path / "vergleich.json").write_text(json.dumps(vergleich), encoding="utf-8")
    return tmp_path


def lauf(broker, tmp_path, state=None, now=JETZT, send=True):
    return bb.run(broker, state or {}, now, send_orders=send, jdir=tmp_path, konten_daten={"haupt": HAUPT}, regel=REGEL)


def test_die_regel_kommt_aus_der_versiegelten_datei():
    assert REGEL["konto_name"] == bb.KONTO_NAME == "Vortag USDJPY"
    assert REGEL["geld"] == {"kapital_eur": 700, "risiko_eur": 7, "max_risiko_faktor": 2.0}
    assert REGEL["waechter"]["margin_anteil"] == 0.5 and REGEL["waechter"]["bremse_rueckgang"] == 0.3
    assert REGEL["waechter"]["frei_danach_eur"] == 250 and REGEL["kopieren"]["frist_minuten"] == 30
    assert set(REGEL["mitglieder"]) == {"gold-cb", "gold-zonen", "gold-ausbruch4h", "us500-ruecksetzer",
                                        "r5-ruecksetzer-us100", "r7-nasdaq-noise-long", "scalp-de40", "scalp-us100",
                                        "welt-ausbruch4h"}


def test_das_echte_konto_ist_vortag_usdjpy_und_keins_der_mitglieder(monkeypatch):
    """Mit dem echten journal/konten.json: Das Bündel teilt "Vortag USDJPY" nur mit Vortag GBP/USD und pine-hand."""
    from gold import ausbruch4h_bot, zonen_bot
    from gold.bot import konten
    from suche import mitnutzer, scalper_bot, welt4h_bot
    k = konten.load()
    echt = bb.konto_id(k)
    monkeypatch.setattr(bb, "KONTO", echt)           # die Liste der Mitnutzer mit dem echten Konto des Bündels
    assert echt and echt == str(k["zuordnung"]["r6-vortag-gbpusd"]) and not echt.endswith(bb.HAUPT_ENDUNG)
    mitglieder = {str(k["haupt"]), scalper_bot.KONTO, zonen_bot.KONTO, ausbruch4h_bot.KONTO, welt4h_bot.KONTO,
                  str(k["zuordnung"]["us500-ruecksetzer"]), str(k["zuordnung"]["r5-ruecksetzer-us100"]),
                  str(k["zuordnung"]["r7-nasdaq-noise-long"])}
    assert echt not in mitglieder
    andere = {b for b, aid in k["zuordnung"].items() if str(aid) == echt}
    andere |= {b["bot"] for b in mitnutzer.bots() if b["konto"] == echt}
    assert andere == {"r6-vortag-gbpusd", "pine-hand", "buendel9", "gold-buendel"}
    assert bb.SPERR_MAERKTE == ("GBPUSD",)


def test_quell_deals_liest_jede_art_von_datei(tmp_path):
    j = journal(tmp_path, scalp={"dealId": "S1"}, gold_cb={"dealId": "G1"}, us500={"dealId": "U1"},
                welt={"dealId": "W1"})
    deals, gelesen, fehler = bb.quell_deals(REGEL, j, {"haupt": HAUPT})
    assert fehler == [] and gelesen == set(REGEL["mitglieder"])
    assert {(d["bot"], d["dealId"], d["konto"]) for d in deals} == {
        ("scalp-de40", "S1", QUELLE), ("gold-cb", "G1", HAUPT), ("us500-ruecksetzer", "U1", QUELLE),
        ("welt-ausbruch4h", "W1", QUELLE)}


def test_groesse_fuer_7_euro_und_nie_mehr_als_doppelt():
    q = Quote(4000.0, 4000.3, True, "USD", 1.0, 0.01, 0.01, 5.0, 2, 0.1, 1.08)
    size, _ = bb.groesse(7.0, 10.0, q, 2.0)
    assert size == 0.75 and size * 10 / 1.08 <= 7.0
    grob = Quote(4000.0, 4000.3, True, "USD", 1.0, 1.0, 1.0, 5.0, 2, 0.1, 1.08)
    assert bb.groesse(7.0, 10.0, grob, 2.0)[0] == 1.0        # kleinste Größe riskiert 9,26 €, unter 14 €
    assert bb.groesse(7.0, 20.0, grob, 2.0)[0] is None       # 18,52 € wären mehr als doppelt so viel wie 7 €
    assert round(bb.margin_eur(0.75, 4000.0, q), 2) == round(0.75 * 4000 * 0.05 / 1.08, 2)


def test_kopiert_einen_neuen_trade_mit_stop_ziel_und_7_euro(tmp_path):
    b = Broker()
    b.quelle("S1")
    st, log, fertig = lauf(b, journal(tmp_path, scalp={"dealId": "S1"}))
    (post,) = b.posts()
    body = post[2]
    assert body["epic"] == "DE40" and body["direction"] == "BUY"
    assert body["stopLevel"] == 19950.0 and body["profitLevel"] == 20500.0
    assert body["size"] == 0.13                      # 7 € / (20001,2 - 19950) = 0,136, abgerundet
    k = st["kopien"]["S1"]
    assert k["dealId"] == "K1" and k["quelle"] == "scalp-de40" and k["stop_start"] == 19950.0
    assert any(e["event"] == "kopiert" for e in log) and fertig == []
    # der nächste Lauf kopiert denselben Trade nie ein zweites Mal
    st2, _, _ = lauf(b, tmp_path, st, now=JETZT + timedelta(minutes=15))
    assert len(b.posts()) == 1 and st2["kopien"]["S1"]["dealId"] == "K1"


def test_deal_id_der_position_nicht_der_order():
    """Fehler bis 26.11.2026: Das Bündel nahm die obere Deal-ID (Order) und fand keine Kopie unter seinen Positionen."""
    conf = {"dealStatus": "ACCEPTED", "dealId": "ORDER", "affectedDeals": [{"dealId": "POSITION", "status": "OPENED"}]}
    assert bb.deal_aus_bestaetigung(conf) == "POSITION"
    assert bb.deal_aus_bestaetigung({"dealId": "NUR"}) == "NUR" and bb.deal_aus_bestaetigung(None) == ""


def _gold(deal, size, created, richtung="SELL", level=4050.0, stop=4080.0, ziel=None, epic="GOLD"):
    return {"dealId": deal, "epic": epic, "direction": richtung, "level": level, "size": size, "stopLevel": stop,
            "profitLevel": ziel, "createdDateUTC": created.strftime("%Y-%m-%dT%H:%M:%S.000")}


def test_falsche_deal_id_wird_ueber_markt_groesse_und_zeit_berichtigt(tmp_path):
    b = Broker()
    b.quelle("S1")
    st, _, _ = lauf(b, journal(tmp_path, scalp={"dealId": "S1"}))
    st["kopien"]["S1"]["dealId"] = "O1"              # so merkte es sich der Bot bis zum 26.11.2026
    b.pos[BUENDEL]["V1"] = _gold("V1", 0.13, JETZT, richtung="BUY", level=1.3, stop=1.29, epic="GBPUSD")
    st2, log, fertig = lauf(b, tmp_path, st, now=JETZT + timedelta(minutes=15))
    assert st2["kopien"]["S1"]["dealId"] == "K1" and fertig == [] and "weg_seit" not in st2["kopien"]["S1"]
    (e,) = [e for e in log if e["event"] == "Deal-ID berichtigt"]
    assert e["alt"] == "O1" and e["dealId"] == "K1"
    assert not [c for c in b.calls if c[0] == "DELETE"]


def test_berichtigt_nie_gbpusd_eine_andere_groesse_oder_eine_spaetere_position():
    k = {"epic": "GOLD", "richtung": -1, "size": 0.26, "opened_utc": "2026-11-23T18:17:08"}
    t0 = pd.Timestamp("2026-11-23T18:17:08")
    def eigene(*pos):
        return {p["dealId"]: {"market": {"epic": p["epic"]}, "position": p} for p in pos}
    assert bb.passende_position(k, eigene(_gold("A", 0.26, t0 + pd.Timedelta(seconds=40))), set()) == "A"
    assert bb.passende_position(k, eigene(_gold("A", 0.27, t0)), set()) is None            # andere Größe
    assert bb.passende_position(k, eigene(_gold("A", 0.26, t0, richtung="BUY")), set()) is None
    assert bb.passende_position(k, eigene(_gold("A", 0.26, t0 + pd.Timedelta(minutes=20))), set()) is None
    assert bb.passende_position(k, eigene(_gold("A", 0.26, t0)), {"A"}) is None           # schon einer Kopie
    assert bb.passende_position(k, eigene(_gold("A", 0.26, t0), _gold("B", 0.26, t0)), set()) is None  # zwei
    g = {**k, "epic": "GBPUSD"}
    assert bb.passende_position(g, eigene(_gold("A", 0.26, t0, epic="GBPUSD")), set()) is None
    ohne = _gold("A", 0.26, t0)
    del ohne["createdDateUTC"]
    assert bb.passende_position(k, eigene(ohne), set()) is None


def test_falsch_gebuchte_offene_kopien_werden_wieder_gefuehrt(tmp_path):
    """Der Fall vom 20. bis 26.11.2026: Kopien als "beim Broker zu" mit -1 R gebucht, obwohl sie offen lagen."""
    b = Broker()
    auf_a, auf_b = JETZT - timedelta(days=2), JETZT - timedelta(minutes=100)
    def rec(qd, quelle, epic, richtung, size, entry, stop, auf, eur, deal):
        return {"id": "buendel9", "quelle": quelle, "quelle_deal": qd, "dealId": deal, "epic": epic,
                "richtung": richtung, "size": size, "entry": entry, "stop_start": stop, "stop": stop, "ziel": None,
                "exit": stop, "grund": bb.GESCHAETZT, "geschaetzt": True, "opened_utc": auf.strftime(bb.FMT),
                "closed_utc": (auf + timedelta(minutes=75)).strftime(bb.FMT), "risiko_eur": 7.0, "r": -1.0,
                "eur": eur}
    alt = [rec("G-alt", "gold-cb", "GOLD", -1, 0.26, 4050.0, 4080.0, auf_a, -7.0, "O-A"),       # Quelle schon zu
           rec("S-alt", "scalp-de40", "DE40", 1, 0.13, 20001.2, 19950.0, auf_b, -6.66, "O-B"),  # Quelle offen
           rec("Z-alt", "gold-zonen", "GOLD", -1, 0.15, 4050.0, 4100.0, auf_a, -6.75, "O-C"),   # wirklich zu
           rec("D-alt", "gold-cb", "GOLD", -1, 0.5, 4050.0, 4064.0, JETZT - timedelta(days=40), -7.0, "O-D")]
    b.pos[BUENDEL]["K-A"] = _gold("K-A", 0.26, auf_a + timedelta(seconds=20))
    b.pos[BUENDEL]["K-B"] = _gold("K-B", 0.13, auf_b + timedelta(seconds=30), richtung="BUY", level=20001.2,
                                  stop=19950.0, ziel=20500.0, epic="DE40")
    b.pos[BUENDEL]["K-D"] = _gold("K-D", 0.5, JETZT - timedelta(days=40), stop=4064.0)   # zu alt, bleibt liegen
    b.pos[BUENDEL]["V1"] = _gold("V1", 0.13, auf_b, richtung="BUY", level=1.3, stop=1.29, epic="GBPUSD")
    b.quelle("S-alt", alter_min=100)
    b.pos[QUELLE]["S-alt"]["stopLevel"] = 20001.2    # die Quelle hat den Stop inzwischen nachgezogen
    j = journal(tmp_path, scalp={"dealId": "S-alt"})
    (tmp_path / "buendel9").mkdir()
    (tmp_path / "buendel9/trades.jsonl").write_text("".join(json.dumps(t) + "\n" for t in alt), encoding="utf-8")
    st0 = {"kopien": {}, "gesehen": {"G-alt": {"bot": "gold-cb", "zeit": auf_a.strftime(bb.FMT), "grund": "alt"},
                                     "S-alt": {"bot": "scalp-de40", "zeit": auf_b.strftime(bb.FMT), "grund": "alt"}},
           "summe_eur": -27.41, "summe_r": -4.0, "trades": 4, "hoechst": 700.0}
    st, log, fertig = lauf(b, j, st0)
    wieder = [e for e in log if e["event"] == "Kopie wieder geführt"]
    assert {(e["alt"], e["dealId"]) for e in wieder} == {("O-A", "K-A"), ("O-B", "K-B")}
    (t,) = fertig                                    # Quelle von A ist zu: die Kopie geht wie jede andere raus
    assert ("DELETE", "K-A") in b.calls and t["grund"] == "Quelle zu" and t["dealId"] == "K-A"
    assert t["r"] == pytest.approx((4050.0 - 4001.2) / 30, abs=1e-3)
    k = st["kopien"]["S-alt"]                        # B wird geführt und an den Stop der Quelle angeglichen
    assert k["dealId"] == "K-B" and k["quelle_konto"] == QUELLE and k["stop"] == 20001.2
    assert ("PUT", "/positions/K-B", {"stopLevel": 20001.2, "profitLevel": 20500.0}) in b.calls
    assert set(st["kopien"]) == {"S-alt"} and "S-alt" not in st["gesehen"] and "G-alt" not in st["gesehen"]
    assert st["trades"] == 3 and st["summe_r"] == pytest.approx(-2.0 + t["r"], abs=1e-3)
    assert st["summe_eur"] == pytest.approx(-27.41 + 7.0 + 6.66 + t["eur"], abs=0.01)
    assert not [c for c in b.calls if c[0] == "DELETE" and c[1] in ("K-D", "V1")]
    assert not [c for c in b.calls if c[0] == "PUT" and c[1] in ("/positions/K-D", "/positions/V1")]
    assert bb.schreiben(st, log, fertig, REGEL, tmp_path / "buendel9", tmp_path / "buendel9.json")
    bleiben = [json.loads(x) for x in (tmp_path / "buendel9/trades.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(x["quelle_deal"], x["dealId"]) for x in bleiben] == [("Z-alt", "O-C"), ("D-alt", "O-D"), ("G-alt", "K-A")]
    storno = [json.loads(x) for x in (tmp_path / "buendel9/storniert.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(x["dealId"], x["neue_dealId"]) for x in storno] == [("O-A", "K-A"), ("O-B", "K-B")]
    karte = json.loads((tmp_path / "buendel9.json").read_text(encoding="utf-8"))
    assert karte["zusammenfassung"]["trades"] == 3 == st["trades"]
    assert karte["kontostand_gedacht_eur"] == pytest.approx(700 + st["summe_eur"], abs=0.01)
    # der nächste Lauf nimmt nichts ein zweites Mal zurück und schreibt nichts doppelt
    st2, log2, fertig2 = lauf(b, j, st, now=JETZT + timedelta(minutes=15))
    assert not [e for e in log2 if e["event"] == "Kopie wieder geführt"] and fertig2 == []
    assert st2["trades"] == 3 and st2["summe_eur"] == st["summe_eur"]
    assert bb.stornieren(st2, tmp_path / "buendel9") == 0


def test_ein_alter_trade_wird_nicht_kopiert(tmp_path):
    b = Broker()
    b.quelle("S1", alter_min=40)
    st, log, _ = lauf(b, journal(tmp_path, scalp={"dealId": "S1"}))
    assert b.posts() == [] and "älter als 30" in st["gesehen"]["S1"]["grund"]


def test_eine_gescheiterte_order_wird_nie_wiederholt(tmp_path):
    b = Broker()
    b.order_fehler = True
    b.quelle("S1")
    st, _, _ = lauf(b, journal(tmp_path, scalp={"dealId": "S1"}))
    assert "Order fehlgeschlagen" in st["gesehen"]["S1"]["grund"]
    assert len(b.posts()) == 1                       # der eine Versuch
    b.order_fehler = False
    st2, _, _ = lauf(b, tmp_path, st, now=JETZT + timedelta(minutes=15))
    assert len(b.posts()) == 1 and st2["kopien"] == {} and st2.get("versuche") == {}
    assert "Order fehlgeschlagen" in st2["gesehen"]["S1"]["grund"]


def test_quelle_zu_schliesst_die_kopie_und_bucht_r(tmp_path):
    b = Broker()
    b.quelle("S1")
    st, _, _ = lauf(b, journal(tmp_path, scalp={"dealId": "S1"}))
    (tmp_path / "scalp-de40/state.json").write_text(json.dumps({"offen": None}), encoding="utf-8")
    b.kurs["DE40"] = 20051.2                         # 50 Punkte über dem Einstieg der Kopie
    st2, log, fertig = lauf(b, tmp_path, st, now=JETZT + timedelta(minutes=15))
    assert ("DELETE", "K1") in b.calls and st2["kopien"] == {}
    (t,) = fertig
    assert t["grund"] == "Quelle zu" and t["r"] == pytest.approx(50 / 51.2, abs=1e-3)
    assert t["eur"] == pytest.approx(50 * 0.13, abs=0.01) and st2["trades"] == 1
    assert st2["summe_eur"] == pytest.approx(6.5, abs=0.01) and t["closed_utc"] and t["opened_utc"]


def test_quelle_beim_broker_zu_schliesst_die_kopie(tmp_path):
    b = Broker()
    b.quelle("S1")
    st, _, _ = lauf(b, journal(tmp_path, scalp={"dealId": "S1"}))
    del b.pos[QUELLE]["S1"]                          # Stop der Quelle ausgelöst, ihre Datei weiß es noch nicht
    st2, _, fertig = lauf(b, tmp_path, st, now=JETZT + timedelta(minutes=15))
    assert ("DELETE", "K1") in b.calls and fertig[0]["grund"] == "Quelle beim Broker zu"


def test_kopie_beim_broker_zu_wird_aus_der_aktivitaet_gebucht(tmp_path):
    b = Broker()
    b.quelle("S1")
    st, _, _ = lauf(b, journal(tmp_path, scalp={"dealId": "S1"}))
    del b.pos[BUENDEL]["K1"]
    b.acts["K1"] = [{"dateUTC": (JETZT + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S"), "source": "SL",
                     "type": "POSITION", "status": "ACCEPTED", "details": {"level": 19950.0, "actions": []}}]
    st2, _, fertig = lauf(b, tmp_path, st, now=JETZT + timedelta(minutes=15))
    (t,) = fertig
    assert t["grund"] == "Stop" and t["r"] == pytest.approx(-1.0) and not t["geschaetzt"]
    assert not [c for c in b.calls if c[0] == "DELETE"]


def test_stop_der_quelle_wird_angeglichen(tmp_path):
    b = Broker()
    b.quelle("S1")
    st, _, _ = lauf(b, journal(tmp_path, scalp={"dealId": "S1"}))
    b.pos[QUELLE]["S1"]["stopLevel"] = 20001.2       # Quelle zieht den Stop auf Einstand
    st2, log, _ = lauf(b, tmp_path, st, now=JETZT + timedelta(minutes=15))
    puts = [c for c in b.calls if c[0] == "PUT" and c[1].startswith("/positions/")]
    assert puts == [("PUT", "/positions/K1", {"stopLevel": 20001.2, "profitLevel": 20500.0})]
    assert st2["kopien"]["S1"]["stop"] == 20001.2 and st2["kopien"]["S1"]["stop_start"] == 19950.0
    lauf(b, tmp_path, st2, now=JETZT + timedelta(minutes=30))
    assert len([c for c in b.calls if c[0] == "PUT" and c[1].startswith("/positions/")]) == 1


def test_waechter_margin_und_frei_danach(tmp_path):
    b = Broker(margin=100.0)                         # Margin = ganzer Positionswert: 0,13 x 20.001 € = 2.600 €
    b.quelle("S1")
    st, _, _ = lauf(b, journal(tmp_path, scalp={"dealId": "S1"}))
    assert b.posts() == [] and "über 50 % von 700 €" in st["gesehen"]["S1"]["grund"]
    b2 = Broker(frei=300.0)                          # 130 € Margin, danach blieben nur 170 € frei
    b2.quelle("S2")
    st2, _, _ = lauf(b2, journal(tmp_path, scalp={"dealId": "S2"}))
    assert b2.posts() == [] and "blieben nur" in st2["gesehen"]["S2"]["grund"]


def test_bremse_ab_30_prozent_unter_dem_hoechststand(tmp_path):
    b = Broker()
    b.quelle("S1")
    st, _, _ = lauf(b, journal(tmp_path, scalp={"dealId": "S1"}))
    st["summe_eur"], st["hoechst"] = -205.0, 700.0     # gedacht 495 €, der Verlust von 6,66 € bremst unter 490 €
    (tmp_path / "scalp-de40/state.json").write_text(json.dumps({"offen": None}), encoding="utf-8")
    b.kurs["DE40"] = 19950.0
    st2, log, _ = lauf(b, tmp_path, st, now=JETZT + timedelta(minutes=15))
    assert st2.get("gebremst") and any(e["event"] == "Bremse" for e in log)
    b.quelle("S9")
    (tmp_path / "scalp-de40/state.json").write_text(json.dumps({"offen": {"dealId": "S9"}}), encoding="utf-8")
    st3, _, _ = lauf(b, tmp_path, st2, now=JETZT + timedelta(minutes=20))
    assert len(b.posts()) == 1 and "Bremse" in st3["gesehen"]["S9"]["grund"]


def test_mitglied_mit_40_trades_unter_1_2_bekommt_keine_kopie(tmp_path):
    b = Broker()
    b.quelle("S1")
    v = {"rangliste": [], "wunsch": [{"id": "scalp-de40", "ist": {"trades": 40, "pf_r": 1.05}},
                                     {"id": "gold-cb", "ist": {"trades": 12, "pf_r": 0.5}}]}
    st, _, _ = lauf(b, journal(tmp_path, scalp={"dealId": "S1"}, vergleich=v))
    assert b.posts() == [] and "Mitglied raus" in st["gesehen"]["S1"]["grund"]
    assert set(st["raus"]) == {"scalp-de40"}


def test_ohne_hedging_hoechstens_eine_kopie_je_markt(tmp_path):
    b = Broker(hedging=False)
    b.hedging_fehler = True
    b.quelle("S1")
    b.quelle("U1", richtung="SELL", level=20000.0, stop=20060.0, ziel=None)
    st, log, _ = lauf(b, journal(tmp_path, scalp={"dealId": "S1"}, us500={"dealId": "U1"}))
    assert len(b.posts()) == 1 and st["hedging"] is False
    (kopiert,) = st["kopien"]                        # die Mitglieder kommen in der Reihenfolge der Regeldatei
    (nicht,) = {"S1", "U1"} - {kopiert}
    assert "eine Kopie je Markt" in st["gesehen"][nicht]["grund"]
    b2 = Broker(hedging=False)
    b2.quelle("S1")
    b2.quelle("U1", richtung="SELL", level=20000.0, stop=20060.0, ziel=None)
    st2, log2, _ = lauf(b2, journal(tmp_path, scalp={"dealId": "S1"}, us500={"dealId": "U1"}))
    assert len(b2.posts()) == 2 and any(e["event"] == "Hedging eingeschaltet" for e in log2)
    (verkauf,) = [p[2] for p in b2.posts() if p[2]["direction"] == "SELL"]
    assert "profitLevel" not in verkauf and verkauf["stopLevel"] == 20060.0


def test_gesperrter_markt_ohne_stop_und_ohne_siegel(tmp_path, monkeypatch):
    b = Broker()
    b.quelle("S1", epic="GBPUSD", level=1.30, stop=1.29, ziel=None)
    st, _, _ = lauf(b, journal(tmp_path, scalp={"dealId": "S1"}))
    assert b.posts() == [] and "gesperrt" in st["gesehen"]["S1"]["grund"]
    b2 = Broker()
    b2.quelle("S2", stop=None)
    st2, _, _ = lauf(b2, journal(tmp_path, scalp={"dealId": "S2"}))
    assert b2.posts() == [] and st2["gesehen"]["S2"]["grund"] == "Quelle ohne Stop"
    monkeypatch.setattr(bb, "vorab_ok", lambda *a, **k: False)
    b3 = Broker()
    b3.quelle("S3")
    st3, _, _ = lauf(b3, journal(tmp_path, scalp={"dealId": "S3"}))
    assert b3.posts() == [] and st3["gesehen"]["S3"]["grund"] == "Siegel fehlt"


def test_ohne_konto_oder_auf_dem_hauptkonto_nichts(tmp_path, monkeypatch):
    b = Broker()
    b.quelle("S1")
    for konto in ("", HAUPT):
        monkeypatch.setattr(bb, "KONTO", konto)
        st, log, _ = lauf(b, journal(tmp_path, scalp={"dealId": "S1"}))
        assert log[-1]["event"] == "kein Konto" and b.calls == []


def test_trockenlauf_sendet_nichts(tmp_path):
    b = Broker()
    b.quelle("S1")
    st, log, _ = lauf(b, journal(tmp_path, scalp={"dealId": "S1"}), send=False)
    assert b.posts() == [] and st["kopien"] == {} and any(e["event"] == "würde kopieren" for e in log)


def test_schreibt_nur_eigene_dateien_und_nur_bei_aenderung(tmp_path):
    b = Broker()
    b.quelle("S1")
    st, log, fertig = lauf(b, journal(tmp_path, scalp={"dealId": "S1"}))
    jdir, karte = tmp_path / "buendel9", tmp_path / "buendel9.json"
    assert bb.schreiben(st, log, fertig, REGEL, jdir, karte)
    k = json.loads(karte.read_text(encoding="utf-8"))
    assert k["bot"] == "buendel9" and k["konto"] == "Vortag USDJPY" and len(k["offen"]) == 1
    assert k["zusammenfassung"]["trades"] == 0 and k["kontostand_gedacht_eur"] == 700.0
    assert k["zusammenfassung"]["summe_eur"] == 0.0 and k["zusammenfassung"]["pf_r"] is None   # Felder des Cockpits
    z = bb.bewertung([{"r": 1.0, "eur": 7.0}, {"r": -0.5, "eur": -3.5}])
    assert z["summe_eur"] == 3.5 and z["pf_r"] == z["gewinnfaktor"] == 2.0 and z["summe_r"] == 0.5
    st2 = {**st, "stand": "später"}
    assert not bb.schreiben(st2, [], [], REGEL, jdir, karte)
    with pytest.raises(RuntimeError):
        bb.schreiben(st, log, fertig, REGEL, tmp_path / "x", tmp_path / "konten.json")


def test_die_karte_im_journal_passt_zum_vergleich():
    """Die Karten im echten Journal. Bis zum ersten Lauf nach dem Merge nennt die von buendel9 noch die erste Regel,
    die des Gold-Bündels gibt es erst nach seinem ersten Lauf."""
    erlaubt = {"buendel9": ("VORAB_buendel9_bot.yaml", "VORAB_buendel9_ohne_gold.yaml"),
               "gold-buendel": ("VORAB_gold_buendel_bot.yaml",)}
    gelesen = 0
    for bid, dateien in erlaubt.items():
        pfad = bb.J / f"{bid}.json"
        if not pfad.exists():
            assert bid == bb.GOLD_ID
            continue
        karte = json.loads(pfad.read_text(encoding="utf-8"))
        assert karte["vorab"] in {f"suche/{d}" for d in dateien}
        regel = bb.lade_regel(bb.ROOT / karte["vorab"])
        assert karte["bot"] == bid == regel["bot_id"] and karte["konto"] == bb.KONTO_NAME
        assert karte["name"] == regel["name"] and karte["mitglieder"] == list(regel["mitglieder"])
        assert karte["start"] is None or pd.Timestamp(karte["start"]) >= pd.Timestamp("2026-11-20")
        assert karte["kapital_eur"] == 700
        gelesen += 1
    assert gelesen >= 1


# ---------- Zwei Bündel auf einem Konto (Kirons Wahl vom 26.11.2026 09:59 UTC) ----------

def _kopie(qd, deal, quelle, opened, epic="GOLD", richtung=-1, size=0.5, entry=4000.0, stop=4020.0, konto=HAUPT):
    return {"quelle": quelle, "quelle_deal": qd, "epic": epic, "richtung": richtung, "size": size, "stop": stop,
            "ziel": None, "margin_eur": 90.0, "risiko_eur": 7.0, "dealId": deal, "entry": entry, "stop_start": stop,
            "stop_quelle": stop, "ziel_quelle": None, "quelle_konto": konto, "lot": 1.0, "eur_rate": 1.08,
            "opened_utc": opened.strftime(bb.FMT)}


def gold_lauf(broker, tmp_path, state=None, now=JETZT, regel=GOLD, vorab=bb.VORAB_GOLD):
    return bb.run(broker, state or {}, now, jdir=tmp_path, konten_daten={"haupt": HAUPT}, regel=regel, vorab=vorab)


def test_die_neunerliste_teilt_sich_in_gold_und_den_rest():
    assert GOLD["bot_id"] == bb.GOLD_ID == "gold-buendel" and OHNE_GOLD["bot_id"] == bb.BOT_ID == "buendel9"
    gold, rest = set(GOLD["mitglieder"]), set(OHNE_GOLD["mitglieder"])
    assert gold == {"gold-cb", "gold-zonen", "gold-ausbruch4h"} and not gold & rest
    assert gold | rest == set(REGEL["mitglieder"])
    assert set(OHNE_GOLD["auslaufend"]) == gold and "auslaufend" not in GOLD
    for bot in REGEL["mitglieder"]:                   # dieselben Dateien wie in der ersten Regel
        neu = {**GOLD["mitglieder"], **OHNE_GOLD["mitglieder"]}[bot]
        assert neu == REGEL["mitglieder"][bot]
        if bot in gold:
            assert {k: v for k, v in OHNE_GOLD["auslaufend"][bot].items() if k != "grund"} == REGEL["mitglieder"][bot]
    for r in (GOLD, OHNE_GOLD):                       # Geld, Wächter und Frist wie in der ersten Regel
        assert r["konto_name"] == "Vortag USDJPY" and r["geld"] == REGEL["geld"]
        assert r["kopieren"]["frist_minuten"] == 30
        for k in ("margin_anteil", "frei_danach_eur", "bremse_rueckgang", "mitglied_raus"):
            assert r["waechter"][k] == REGEL["waechter"][k]
    assert bb.BUENDEL == ("buendel9", "gold-buendel")


def test_gold_buendel_kopiert_nur_gold_kauf_und_verkauf(tmp_path):
    """Kauf oder Verkauf kommt allein von der Quelle (Kirons Wunsch: "nicht nur short sondern shorts und longs")."""
    b = Broker()
    b.pos[HAUPT]["G1"] = _gold("G1", 1.0, JETZT - timedelta(minutes=5), richtung="BUY", level=4000.0, stop=3980.0,
                               ziel=4040.0)
    b.quelle("S1")                                     # ein Scalper-Trade, kein Mitglied des Gold-Bündels
    j = journal(tmp_path, scalp={"dealId": "S1"}, gold_cb={"dealId": "G1"})
    st, log, _ = gold_lauf(b, j)
    (post,) = b.posts()
    assert post[2]["epic"] == "GOLD" and post[2]["direction"] == "BUY" and post[2]["stopLevel"] == 3980.0
    assert set(st["kopien"]) == {"G1"} and "S1" not in st["gesehen"] and st["vorab"] == bb.VORAB_GOLD.name
    assert not any(e["event"] == "neue Regel" for e in log) and st.get("regeln") is None
    b.pos[QUELLE]["Z1"] = _gold("Z1", 1.0, JETZT + timedelta(minutes=10), richtung="SELL", level=4000.0, stop=4020.0)
    (tmp_path / "gold-zonen/state.json").write_text(json.dumps({"trade": {"dealId": "Z1"}}), encoding="utf-8")
    st2, _, _ = gold_lauf(b, tmp_path, st, now=JETZT + timedelta(minutes=15))
    assert [p[2]["direction"] for p in b.posts()] == ["BUY", "SELL"] and set(st2["kopien"]) == {"G1", "Z1"}
    assert st2["kopien"]["Z1"]["quelle"] == "gold-zonen" and st2["kopien"]["Z1"]["richtung"] == -1


def test_jedes_buendel_fasst_die_kopien_des_anderen_nie_an(tmp_path):
    b = Broker()
    offen = JETZT - timedelta(minutes=50)
    # buendel9 hält K9 (eine Gold-Kopie aus der Zeit mit 9 Mitgliedern), das Gold-Bündel hat eine Kopie mit falscher
    # Deal-ID, die nach Markt, Richtung, Größe und Zeit genau auf K9 passen würde
    b.pos[BUENDEL]["K9"] = _gold("K9", 0.5, offen + timedelta(seconds=20), level=4000.0, stop=4020.0)
    (tmp_path / "buendel9").mkdir()
    (tmp_path / "buendel9" / "state.json").write_text(
        json.dumps({"kopien": {"G7": _kopie("G7", "K9", "gold-cb", offen)}}), encoding="utf-8")
    j = journal(tmp_path, gold_cb={"dealId": "G7"})
    b.pos[HAUPT]["G7"] = _gold("G7", 1.0, offen, level=4000.0, stop=4020.0)
    st0 = {"start": "2026-11-23T14:00:00", "kopien": {"G8": _kopie("G8", "O1", "gold-cb", offen)}, "gesehen": {},
           "summe_eur": 0.0, "summe_r": 0.0, "trades": 0, "hoechst": 700.0}
    st, log, fertig = gold_lauf(b, j, st0)
    assert not any(e["event"] == "Deal-ID berichtigt" for e in log) and fertig == []
    assert st["kopien"]["G8"]["dealId"] == "O1" and st["kopien"]["G8"].get("weg_seit")
    assert "K9" in b.pos[BUENDEL] and not any(c[:2] == ("DELETE", "K9") for c in b.calls)
    # G7 hat buendel9 schon kopiert: das Gold-Bündel kopiert ihn nicht ein zweites Mal
    b.pos[HAUPT]["G7"]["createdDateUTC"] = (JETZT - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S.000")
    st2, _, _ = gold_lauf(b, j, {"start": "2026-11-23T14:00:00"})
    assert b.posts() == [] and "anderen Bündel" in st2["gesehen"]["G7"]["grund"]
    # und umgekehrt: buendel9 schließt die Kopie des Gold-Bündels nie, auch wenn er seine eigene sucht
    (tmp_path / "gold-buendel").mkdir()
    (tmp_path / "gold-buendel" / "state.json").write_text(
        json.dumps({"kopien": {"G8": _kopie("G8", "K9", "gold-cb", offen)}}), encoding="utf-8")
    (tmp_path / "buendel9" / "state.json").unlink()
    st3, log3, _ = gold_lauf(b, j, {**st0, "kopien": {"G6": _kopie("G6", "O2", "gold-cb", offen)}}, regel=OHNE_GOLD,
                             vorab=bb.VORAB_OHNE_GOLD)
    assert not any(e["event"] == "Deal-ID berichtigt" for e in log3) and st3["kopien"]["G6"]["dealId"] == "O2"
    assert "K9" in b.pos[BUENDEL]


def test_ohne_hedging_zaehlen_die_maerkte_des_anderen_buendels(tmp_path):
    b = Broker(hedging=False)
    b.hedging_fehler = True
    (tmp_path / "buendel9").mkdir()
    (tmp_path / "buendel9" / "state.json").write_text(
        json.dumps({"kopien": {"G7": _kopie("G7", "K9", "gold-cb", JETZT - timedelta(hours=2))}}), encoding="utf-8")
    b.pos[HAUPT]["G1"] = _gold("G1", 1.0, JETZT - timedelta(minutes=5))
    st, _, _ = gold_lauf(b, journal(tmp_path, gold_cb={"dealId": "G1"}))
    assert b.posts() == [] and "eine Kopie je Markt" in st["gesehen"]["G1"]["grund"]


def test_buendel9_ohne_gold_kopiert_kein_gold_mehr_und_fuehrt_offene_gold_kopien_zu_ende(tmp_path):
    b = Broker()
    offen = JETZT - timedelta(hours=3)
    b.pos[BUENDEL]["K0"] = _gold("K0", 0.5, offen + timedelta(seconds=20), level=4000.0, stop=4020.0)
    b.kurs["GOLD"] = 3990.0                            # die alte Gold-Kopie (Verkauf bei 4000) liegt 10 Punkte vorn
    b.pos[HAUPT]["G1"] = _gold("G1", 1.0, JETZT - timedelta(minutes=5))   # ein neuer Trade von Gold-Bot C/B
    b.quelle("S1")
    j = journal(tmp_path, scalp={"dealId": "S1"}, gold_cb={"dealId": "G1"})   # G0 ist bei der Quelle zu
    st0 = {"start": "2026-11-20T18:03:32", "kopien": {"G0": _kopie("G0", "K0", "gold-cb", offen)}, "gesehen": {},
           "summe_eur": -9.62, "summe_r": -1.3349, "trades": 6, "hoechst": 700.0}
    st, log, fertig = gold_lauf(b, j, st0, regel=OHNE_GOLD, vorab=bb.VORAB_OHNE_GOLD)
    (t,) = fertig
    assert t["quelle"] == "gold-cb" and t["grund"] == "Quelle zu" and ("DELETE", "K0") in b.calls
    assert t["r"] == pytest.approx((4000.0 - 3991.2) / 20, abs=1e-4)
    # Kontostand und Zählung laufen weiter (VORAB_aufstieg_alle: alle Kopien seit dem Start zählen)
    assert st["trades"] == 7 and st["summe_eur"] == pytest.approx(-9.62 + t["eur"], abs=0.01)
    assert st["start"] == "2026-11-20T18:03:32" and st["hoechst"] == 700.0
    assert st["vorab"] == bb.VORAB_OHNE_GOLD.name and st["regel_seit"] == JETZT.strftime(bb.FMT)
    assert st["regeln"] == [{"vorab": bb.VORAB.name, "bis": JETZT.strftime(bb.FMT)}]
    assert [e for e in log if e["event"] == "neue Regel"] == [
        {"time": JETZT.strftime(bb.FMT), "event": "neue Regel", "alt": bb.VORAB.name, "neu": bb.VORAB_OHNE_GOLD.name}]
    # der neue Gold-Trade bekommt hier keine Kopie mehr, der Scalper-Trade schon
    assert "Gold-Bündel" in st["gesehen"]["G1"]["grund"] and set(st["kopien"]) == {"S1"}
    assert [p[2]["epic"] for p in b.posts()] == ["DE40"]
    st2, log2, _ = gold_lauf(b, j, st, now=JETZT + timedelta(minutes=15), regel=OHNE_GOLD, vorab=bb.VORAB_OHNE_GOLD)
    assert not any(e["event"] == "neue Regel" for e in log2) and st2["regeln"] == st["regeln"]


def test_karte_und_dateien_des_gold_buendels(tmp_path):
    b = Broker()
    b.pos[HAUPT]["G1"] = _gold("G1", 1.0, JETZT - timedelta(minutes=5))
    st, log, fertig = gold_lauf(b, journal(tmp_path, gold_cb={"dealId": "G1"}))
    jdir, karte = tmp_path / "gold-buendel", tmp_path / "gold-buendel.json"
    assert bb.schreiben(st, log, fertig, GOLD, jdir, karte, vorab=bb.VORAB_GOLD)
    k = json.loads(karte.read_text(encoding="utf-8"))
    assert k["bot"] == "gold-buendel" and k["name"] == GOLD["name"] and k["vorab"] == "suche/VORAB_gold_buendel_bot.yaml"
    assert k["mitglieder"] == ["gold-cb", "gold-zonen", "gold-ausbruch4h"] and k["auslaufend"] == []
    assert k["regel"] == " ".join(GOLD["text"].split()) and "Käufe" in k["backtest"] and len(k["offen"]) == 1
    assert k["start"] == JETZT.strftime(bb.FMT) and k["regel_seit"] is None
    assert json.loads((jdir / "state.json").read_text(encoding="utf-8"))["kopien"]["G1"]["quelle"] == "gold-cb"
    for fremd in (("buendel9", "x.json"), ("x", "buendel9.json"), ("x", "gold-state.json")):
        with pytest.raises(RuntimeError):
            bb.schreiben(st, log, fertig, GOLD, tmp_path / fremd[0], tmp_path / fremd[1], vorab=bb.VORAB_GOLD)
    with pytest.raises(RuntimeError):                  # und buendel9 schreibt nie in die Dateien des Gold-Bündels
        bb.schreiben(st, log, fertig, OHNE_GOLD, jdir, tmp_path / "y.json", vorab=bb.VORAB_OHNE_GOLD)


def test_main_nimmt_nur_die_regeln_der_laufenden_buendel(monkeypatch, capsys):
    from gold.bot.runner import CRED_KEYS
    for k in CRED_KEYS:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(SystemExit):
        bb.main(["--regel", "suche/VORAB_buendel9_bot.yaml"])
    with pytest.raises(SystemExit):
        bb.main(["--regel", "suche/VORAB_aufstieg_alle.yaml"])
    for regel in ("suche/VORAB_gold_buendel_bot.yaml", "suche/VORAB_buendel9_ohne_gold.yaml", None):
        assert bb.main(["--regel", regel] if regel else []) == 0
    assert capsys.readouterr().out.count("Keine Capital.com-Zugangsdaten") == 3


def test_beide_buendel_laufen_im_15_minuten_lauf():
    import yaml
    steps = yaml.safe_load((bb.ROOT / ".github" / "workflows" / "demo-bots.yml").read_text(encoding="utf-8"))
    steps = steps["jobs"]["run"]["steps"]
    pos = {s.get("id"): i for i, s in enumerate(steps) if s.get("id")}
    b9, gb = steps[pos["buendel"]], steps[pos["gold_buendel"]]
    assert "python -m suche.buendel_bot --regel suche/VORAB_buendel9_ohne_gold.yaml" in b9["run"]
    assert "python -m suche.buendel_bot --regel suche/VORAB_gold_buendel_bot.yaml" in gb["run"]
    assert "--dry-run" in gb["run"] and "tests/test_buendel_bot.py" in gb["run"] and "touch" not in gb["run"]
    assert gb["continue-on-error"] is True and "!cancelled()" in gb["if"]
    assert pos["buendel"] < pos["gold_buendel"] < pos["vergleich"]
    # ohne --regel nähme der Bot buendel9 ohne Gold, nie die erste Regel mit 9 Mitgliedern
    assert "--regel" in b9["run"].split("python -m suche.buendel_bot", 1)[1].split("\n")[0]
