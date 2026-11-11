"""Tests für gold/zonen_bot.py (Gold-Zonen Bruch, suche/VORAB_gold_zonen_bot.yaml): höchstens eine Limit-Order an der
Linie, die dem Kurs am nächsten ist, Füllung, Ziel aus dem Füllkurs, Einstand nach 2 R, Zeit-Ausstieg, Kurslücke,
verbrauchte Zonen, Wochenende, Sperren und Journal. Nur auf Account 2, nie auf dem Hauptkonto. Alle Kurse hier sind
erfunden, das Hauptkonto auch. Account 2 kommt aus dem Code des Bots und steht in keiner Zeile dieser Datei."""
import copy
import json

import pandas as pd
import pytest

from gold import zonen_bot as zb
from suche import gold_zonen as gz
from suche.demo_bots import Quote

HAUPT = "1111" + "0000" + "3150"                    # erfunden, nur die Endung zählt
NOW = pd.Timestamp("2026-03-04 15:03", tz="UTC")    # Mittwoch, 10:03 Uhr New York
MIN5 = pd.Timedelta(minutes=5)


def _q(**kw):
    base = dict(bid=4000.0, offer=4000.3, tradeable=True, currency="USD", lot=1.0, min_size=0.01, size_step=0.01,
                margin_pct=5.0, decimals=2, min_dist=0.1, eur_rate=1.08)
    base.update(kw)
    return Quote(**base)


def kand(name="W2026030210", d=1, linie=3990.0, innen=3982.0, stop=3976.0, rest=20, beruehrt=False):
    return {"name": name, "d": d, "linie": linie, "innen": innen, "stop": stop, "atr_bruch": 24.0,
            "bruch": "2026-03-03 21:00:00", "rest": rest, "beruehrt": beruehrt}


LANG, LANG2 = kand(), kand("W2026030206", linie=3980.0, innen=3973.0, stop=3967.0)
KURZ = kand("U2026030214", d=-1, linie=4020.0, innen=4028.0, stop=4034.0)


def kerzen5(now, n=40, bid=4000.0, sp=0.3, **anders) -> list[dict]:
    """n 5-Minuten-Kerzen bis zur laufenden, ruhig um bid (Hoch +1, Tief -1). anders: "HH:MM" -> (hoch, tief)."""
    ende = pd.Timestamp(now).tz_convert(None).floor("5min")
    out = []
    for t in pd.date_range(end=ende, periods=n, freq="5min"):
        hoch, tief = anders.get(f"k{t:%H%M}", (bid + 1.0, bid - 1.0))
        out.append({"snapshotTimeUTC": t.strftime("%Y-%m-%dT%H:%M:%S"),
                    "openPrice": {"bid": bid, "ask": bid + sp}, "highPrice": {"bid": hoch, "ask": hoch + sp},
                    "lowPrice": {"bid": tief, "ask": tief + sp}, "closePrice": {"bid": bid, "ask": bid + sp}})
    return out


class Antwort:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class Konto:
    """Capital.com zum Testen: Hauptkonto und Account 2, Gold-Positionen und Limit-Orders auf Account 2, ohne Netz."""

    def __init__(self, bid=4000.0, offer=4000.3, konto2=True):
        self.account_id = HAUPT
        self.bid, self.offer = bid, offer
        self.konto2 = konto2
        self.handelbar = True
        self.pos: dict[str, dict] = {}
        self.wo: dict[str, dict] = {}
        self.fremd: list[dict] = []
        self.acts: dict[str, list] = {}             # je Deal, für broker_exit
        self.aktivitaet: list | None = []           # /history/activity, None = nicht lesbar
        self.m5: list[dict] | None = None
        self.ablehnen = False
        self.ohne_bestaetigung = False              # confirm scheitert, die Order liegt aber beim Broker
        self.post_kaputt = False                    # schon das Legen scheitert: Es gibt keine Order
        self.loeschen_kaputt = False
        self.eur_ok = True
        self.calls: list = []
        self.refs: dict = {}
        self.nr = 0

    def accounts(self):
        out = [{"accountId": HAUPT, "balance": {"balance": 990.0, "available": 900.0}}]
        if self.konto2:
            out.append({"accountId": zb.KONTO, "balance": {"balance": 1000.0, "available": 1000.0}})
        return out

    def switch_account(self, aid):
        self.account_id = aid

    def market(self, epic):
        if epic == "GOLD":
            return {"snapshot": {"bid": self.bid, "offer": self.offer, "decimalPlacesFactor": 2,
                                 "marketStatus": "TRADEABLE" if self.handelbar else "CLOSED"},
                    "instrument": {"currency": "USD", "lotSize": 1, "marginFactor": 5, "marginFactorUnit": "PERCENTAGE"},
                    "dealingRules": {"minDealSize": {"value": 0.01}, "minSizeIncrement": {"value": 0.01},
                                     "minStopOrProfitDistance": {"unit": "POINTS", "value": 0.1}}}
        if not self.eur_ok:
            raise RuntimeError("EURUSD nicht lesbar")
        return {"snapshot": {"bid": 1.08, "offer": 1.08}}

    def positions(self):
        assert self.account_id == zb.KONTO, "der Zonen-Bot darf nur auf Account 2 Positionen lesen"
        return [{"market": {"epic": "GOLD"}, "position": p} for p in self.pos.values()] + self.fremd

    def prices(self, epic, resolution, max_bars):
        assert epic == "GOLD" and resolution == "MINUTE_5"
        return (self.m5 or [])[-max_bars:]

    def _get(self, path, **params):
        assert self.account_id == zb.KONTO
        if path == "/workingorders":
            return {"workingOrders": [{"workingOrderData": {"dealId": k, "epic": v["epic"], "direction": v["direction"],
                                                            "orderLevel": v["level"]}} for k, v in self.wo.items()]}
        if path == "/history/activity":
            if self.aktivitaet is None:
                raise RuntimeError("500 nicht lesbar")
            return {"activities": self.aktivitaet}
        raise AssertionError(f"unerwarteter Abruf {path}")

    def _request(self, method, path, json=None):
        assert self.account_id == zb.KONTO, "Orders nur auf Account 2"
        self.calls.append((method, path, json))
        self.nr += 1
        ref = f"R{self.nr}"
        if method == "POST" and path == "/workingorders":
            if self.post_kaputt:
                raise RuntimeError("503 beim Legen")
            if self.ablehnen:
                self.refs[ref] = {"dealStatus": "REJECTED", "reason": "TEST"}
            else:
                self.wo[f"W{self.nr}"] = dict(json)
                self.refs[ref] = {"dealStatus": "ACCEPTED", "dealId": f"W{self.nr}"}
        elif method == "DELETE" and path.startswith("/workingorders/"):
            deal = path.rsplit("/", 1)[1]
            if deal not in self.wo or self.loeschen_kaputt:
                raise RuntimeError("404 Order gibt es nicht mehr")
            del self.wo[deal]
        elif method == "PUT" and path.startswith("/positions/"):
            self.pos[path.rsplit("/", 1)[1]].update(dict(json))
        else:
            raise AssertionError(f"unerwarteter Aufruf {method} {path}")
        return Antwort({"dealReference": ref})

    def confirm(self, ref):
        if self.ohne_bestaetigung:
            raise RuntimeError("Zeit abgelaufen bei der Bestätigung")
        return self.refs.get(ref, {"dealStatus": "ACCEPTED"})

    def close_position(self, deal_id):
        assert self.account_id == zb.KONTO
        self.calls.append(("DELETE", f"/positions/{deal_id}", None))
        p = self.pos.pop(deal_id)
        return {"dealStatus": "ACCEPTED", "level": self.bid if p.get("direction") == "BUY" else self.offer}

    def activity(self, deal_id, since, until):
        assert pd.Timestamp(until) - pd.Timestamp(since) <= pd.Timedelta(days=1), "der Broker gibt höchstens einen Tag"
        if self.aktivitaet is None:
            raise RuntimeError("500 nicht lesbar")
        return self.acts.get(deal_id, [])

    # ---- Hilfen für die Tests ----

    def fuelle(self, deal: str, level: float, wann) -> str:
        """Die Limit-Order füllt: Sie verschwindet, eine Position mit neuer Deal-ID entsteht."""
        o = self.wo.pop(deal)
        self.pos["P" + deal] = {"dealId": "P" + deal, "direction": o["direction"], "size": o["size"], "level": level,
                                "stopLevel": o["stopLevel"], "profitLevel": o.get("profitLevel"),
                                "createdDateUTC": pd.Timestamp(wann).tz_convert(None).strftime("%Y-%m-%dT%H:%M:%S")}
        return "P" + deal

    def posts(self):
        return [c[2] for c in self.calls if c[0] == "POST" and c[1] == "/workingorders"]

    def geloescht(self):
        """Versuche, eine Order zu löschen (auch gescheiterte)."""
        return [c[1].rsplit("/", 1)[1] for c in self.calls if c[0] == "DELETE" and c[1].startswith("/workingorders/")]

    def aenderungen(self):
        return [c[2] for c in self.calls if c[0] == "PUT"]

    def geschlossen(self):
        return [c[1].rsplit("/", 1)[1] for c in self.calls if c[0] == "DELETE" and c[1].startswith("/positions/")]


@pytest.fixture
def welt(monkeypatch):
    """Der Plan zum Einstellen (welt["plan"]), ohne echte Kerzen. Die Rechnung des Plans prüfen eigene Tests."""
    welt = {"plan": {"kandidaten": [], "linien": {"1": [], "-1": []}}, "vorab": True, "zuordnung": {}, "plaene": 0}

    def plan(stunden, now):
        welt["plaene"] += 1
        if welt["plan"] is None:
            return None
        stunde = pd.Timestamp(now).floor("h")
        return {"stunde": str(stunde), "gerechnet_bis": str(stunde), "kerzen_4h": 300, "letzte_4h": str(stunde),
                "atr_4h": 24.0, **copy.deepcopy(welt["plan"])}

    def stunden(client, now):
        t = pd.Timestamp(now).floor("h") - pd.Timedelta(hours=1)
        return pd.DataFrame({"open": [4000.0], "high": [4001.0], "low": [3999.0], "close": [4000.0], "ask_low": [3999.3]},
                            index=pd.DatetimeIndex([t]))

    from gold.bot import konten
    monkeypatch.setattr(konten, "load", lambda *a: {"zuordnung": welt["zuordnung"]})
    monkeypatch.setattr(zb, "vorab_ok", lambda: welt["vorab"])
    monkeypatch.setattr(zb, "stundenkerzen", stunden)
    monkeypatch.setattr(zb, "plan_rechnen", plan)
    return welt


def lauf(k: Konto, st: dict, now, **kw):
    if kw.pop("kerzen", True):
        k.m5 = kerzen5(now, **kw)
    return zb.run(k, st, pd.Timestamp(now).to_pydatetime())


def gefuellt(welt, level=3984.0, linien=None):
    """Die Kauf-Order für LANG liegt (nähere Linie), dann füllt sie zu level. Rückgabe: Konto, Stand, Deal-ID."""
    welt["plan"]["kandidaten"] = [LANG, LANG2, KURZ]
    welt["plan"]["linien"] = linien or {"1": [], "-1": [4040.0, 4100.0]}
    k = Konto()
    st, *_ = lauf(k, {}, NOW)
    kauf = next(d for d, o in k.wo.items() if o["direction"] == "BUY")
    deal = k.fuelle(kauf, level, NOW + pd.Timedelta(minutes=2))
    k.bid, k.offer = level + 1.0, level + 1.3
    return k, st, deal


# --------------------------------------------------------------------------------------------------------------------
# Zeit, Kerzen, Größe (ohne Netz)

def test_wochenende_und_ende_der_order():
    t = pd.Timestamp
    assert not zb.wochenende(t("2026-03-06 21:44")) and zb.wochenende(t("2026-03-06 21:45"))      # Freitag 16:45 EST
    assert zb.wochenende(t("2026-03-07 12:00")) and zb.wochenende(t("2026-03-08 22:04"))          # Sonntag 18:04 EDT
    assert not zb.wochenende(t("2026-03-08 22:05")) and not zb.wochenende(t("2026-03-04 15:03"))
    assert zb.order_ende(t("2026-03-04 15:03")) == t("2026-03-06 21:45")
    assert zb.order_ende(t("2026-03-08 22:05")) == t("2026-03-13 20:45")                          # Sommerzeit: 16:45 EDT
    assert zb.order_ende(t("2026-03-06 21:44")) == t("2026-03-06 21:45")
    # Handelstag wechselt um 17:00 Uhr New York: ein Trade über diese Uhrzeit kostet eine Nacht
    assert zb.handelstag(t("2026-03-04 22:01")) - zb.handelstag(t("2026-03-04 21:59")) == 1


def test_kerzen_mit_ask_tief():
    roh = kerzen5(NOW, n=3, k1500=(4003.0, 3991.0))
    roh[0]["lowPrice"] = {"bid": 3998.0}                          # ohne Ask: Bid-Tief plus Spread zur Eröffnung
    roh.append({"snapshotTimeUTC": "2026-03-04T15:05:00", "openPrice": {"bid": None}})            # kaputt: fällt weg
    df = zb.kerzen_ask(roh)
    assert list(df.columns) == ["open", "high", "low", "close", "ask_low"] and len(df) == 3
    assert df["ask_low"].iloc[0] == pytest.approx(3998.3) and df["ask_low"].iloc[-1] == pytest.approx(3991.3)
    assert df["high"].iloc[-1] == 4003.0 and df.index[-1] == pd.Timestamp("2026-03-04 15:00")
    assert zb.kerzen_ask([]).empty


def test_groesse():
    assert zb.groesse(14.0, _q()) == (0.38, "")                   # 5 € * 1,08 / 14 $ = 0,385 Unzen, abgerundet
    assert zb.groesse(2.0, _q())[0] == zb.MAX_OZ                  # nie mehr als 1 Unze
    size, warum = zb.groesse(2000.0, _q())
    assert size is None and "zu grob" in warum                    # 0,01 Unzen wären 18,5 € Risiko
    assert zb.groesse(14.0, _q(eur_rate=None))[0] is None
    assert zb.groesse(60.0, _q(min_size=0.1, size_step=0.1))[0] == 0.1    # kleinste Größe, Risiko 5,56 €: noch erlaubt


def test_plan_aus_stundenkerzen_gibt_dieselbe_order_wie_die_rechnung(monkeypatch):
    """Ohne eingestellten Plan: Aus Stundenkerzen mit einem gebrochenen Widerstand bei 110 legt der Bot die Kauf-Order
    genau auf 110, mit dem Stop der Rechnung (suche.gold_zonen.wartende_bruch)."""
    from gold.bot import konten
    kerzen = ([(100.0, 101.0, 99.0, 100.0)] * 265 + [(104.0, 110.0, 103.0, 106.0)] + [(100.0, 101.0, 99.0, 100.0)] * 9
              + [(100.0, 112.0, 99.0, 111.0)] + [(114.0, 115.0, 113.0, 114.0)] * 24)
    rows = []
    for o, h, lo, c in kerzen:                                    # je 4-Std.-Kerze vier Stundenkerzen
        rows += [(o, o, lo, lo), (lo, h, lo, h), (h, h, c, c), (c, c, c, c)]
    ende = pd.Timestamp("2026-03-04 15:00")                       # 10:00 Uhr New York: eine 4-Std.-Kerze ist gerade fertig
    idx = pd.date_range(end=ende - pd.Timedelta(hours=1), periods=len(rows), freq="1h")
    stunden = pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"])
    stunden["ask_low"] = stunden["low"] + 0.3
    monkeypatch.setattr(konten, "load", lambda *a: {})
    monkeypatch.setattr(zb, "vorab_ok", lambda: True)
    monkeypatch.setattr(zb, "stundenkerzen", lambda client, now: stunden)
    plan = zb.plan_rechnen(stunden, NOW.tz_convert(None))
    assert plan["kerzen_4h"] == 300 and plan["letzte_4h"] == "2026-03-04 15:00:00" and plan["gerechnet_bis"] == str(ende)
    w = [x for x in plan["kandidaten"] if x["linie"] == 110.0]
    assert len(w) == 1 and w[0]["d"] == 1 and w[0]["rest"] == 6 and not w[0]["beruehrt"]
    m = gz.markt(stunden[["open", "high", "low", "close"]])
    assert w == [x for x in gz.wartende_bruch(m, 300, 0.3)[0] if x["linie"] == 110.0]
    assert zb.plan_rechnen(stunden.iloc[-800:], NOW.tz_convert(None)) is None     # nur 200 Kerzen: kein Plan

    k = Konto(bid=114.0, offer=114.3)
    st, log, fertig, blick = lauf(k, {}, NOW, bid=114.0)
    (order,) = k.posts()
    stop = round(w[0]["stop"], 2)
    assert order["direction"] == "BUY" and order["level"] == 110.0 and order["type"] == "LIMIT"
    assert order["stopLevel"] == stop and stop < round(w[0]["innen"], 2) < 110.0
    assert order["profitLevel"] == pytest.approx(110.0 + 10 * (110.0 - stop), abs=0.011)     # kein Ziel ab 4 R: 10 R
    assert order["size"] == zb.MAX_OZ and order["goodTillDate"] == "2026-03-06T21:45:00"
    assert st["orders"][0]["name"] == w[0]["name"] and blick["zonen"][0]["stand"] == "Order liegt"
    assert k.account_id == HAUPT                                  # nach dem Lauf wieder auf dem alten Konto


# --------------------------------------------------------------------------------------------------------------------
# Orders

def test_nur_eine_limit_order_an_der_linie_die_dem_kurs_am_naechsten_ist(welt):
    welt["plan"]["kandidaten"] = [LANG2, KURZ, LANG]
    k = Konto()                                                   # Ask 4000,30: Kauf-Linie 3990 ist 10,30 $ entfernt,
    st, log, fertig, blick = lauf(k, {}, NOW)                     # Verkaufs-Linie 4020 vom Bid 20 $
    (kauf,) = k.posts()
    assert kauf == {"epic": "GOLD", "direction": "BUY", "size": 0.38, "level": 3990.0, "type": "LIMIT",
                    "goodTillDate": "2026-03-06T21:45:00", "guaranteedStop": False, "stopLevel": 3976.0,
                    "profitLevel": 4130.0}                        # Stop 14 $ entfernt, kein Ziel in Sicht: 10 R
    assert [o["name"] for o in st["orders"]] == [LANG["name"]] and fertig == [] and st["trade"] is None
    assert zb.status(st) == "Order liegt: Kauf bei 3990.00 (Stop 3976.00)"
    assert [z["stand"] for z in blick["zonen"]].count("Order liegt") == 1
    # nächster Lauf in derselben Stunde: nichts Neues, kein zweiter Plan
    st2, log2, *_ = lauf(k, st, NOW + MIN5)
    assert len(k.posts()) == 1 and k.geloescht() == [] and log2 == [] and welt["plaene"] == 1
    assert st2["orders"] == st["orders"] and k.account_id == HAUPT
    # der Kurs steigt: Jetzt ist die Verkaufs-Linie näher. Die Kauf-Order geht weg, die Verkaufs-Order kommt.
    k.bid, k.offer = 4012.0, 4012.3
    st3, log3, *_ = lauf(k, st2, NOW + 2 * MIN5, bid=4012.0)
    verkauf = k.posts()[-1]
    assert len(k.posts()) == 2 and len(k.geloescht()) == 1 and len(k.wo) == 1
    assert verkauf["direction"] == "SELL" and verkauf["level"] == 4020.0 and verkauf["stopLevel"] == 4034.0
    assert verkauf["profitLevel"] == 3880.0 and [o["name"] for o in st3["orders"]] == [KURZ["name"]]
    assert st3["verbraucht"] == {}                                # die Kauf-Zone ist nicht verbraucht, nur ohne Order


def test_laesst_sich_die_alte_order_nicht_loeschen_kommt_keine_zweite(welt):
    """Nie zwei Orders beim Broker: Scheitert das Löschen, wartet die neue Order auf den nächsten Lauf."""
    welt["plan"]["kandidaten"] = [LANG, KURZ]
    k = Konto()
    st, *_ = lauf(k, {}, NOW)
    k.bid, k.offer = 4012.0, 4012.3
    k.loeschen_kaputt = True
    st, log, *_ = lauf(k, st, NOW + MIN5, bid=4012.0)
    assert len(k.posts()) == 1 and len(k.wo) == 1 and st["orders"][0]["loeschen"] is True
    assert any(e["event"] == "Order löschen fehlgeschlagen" for e in log)
    k.loeschen_kaputt = False
    st, log, *_ = lauf(k, st, NOW + 2 * MIN5, bid=4012.0)
    assert [p["direction"] for p in k.posts()] == ["BUY", "SELL"] and len(k.wo) == 1
    assert [o["name"] for o in st["orders"]] == [KURZ["name"]]


def test_ziel_ist_die_naechste_zone_der_gegenseite_ab_4_r(welt):
    welt["plan"]["kandidaten"] = [LANG, KURZ]
    welt["plan"]["linien"] = {"1": [3900.0, 3960.0, 3970.0], "-1": [4040.0, 4052.0, 4100.0]}
    k = Konto()
    lauf(k, {}, NOW)
    (kauf,) = k.posts()
    assert kauf["direction"] == "BUY" and kauf["profitLevel"] == 4052.0      # 4040 wären nur 3,6 R, 4052 sind 4,4 R
    k = Konto(bid=4012.0, offer=4012.3)
    lauf(k, {}, NOW, bid=4012.0)
    (verkauf,) = k.posts()
    assert verkauf["direction"] == "SELL" and verkauf["profitLevel"] == 3960.0    # 3970 wären 3,6 R, 3960 sind 4,3 R


def test_bestaetigung_fehlt_dann_findet_der_naechste_lauf_die_order_wieder(welt):
    """Der Broker hat die Order, aber die Bestätigung kam nicht an. Der Bot legt keine zweite, sondern findet sie
    im nächsten Lauf an Richtung und Kurs wieder."""
    welt["plan"]["kandidaten"] = [LANG]
    k = Konto()
    k.ohne_bestaetigung = True
    st, log, *_ = lauf(k, {}, NOW)
    assert len(k.wo) == 1 and st["orders"][0]["dealId"] is None and st["versuche"] == {LANG["name"]: 1}
    assert any(e["event"] == "Order fehlgeschlagen" for e in log)
    k.ohne_bestaetigung = False
    st, log, fertig, _ = lauf(k, st, NOW + MIN5)
    (deal,) = k.wo
    assert len(k.posts()) == 1 and st["orders"][0]["dealId"] == deal and k.geloescht() == []
    assert any(e["event"].startswith("Order wiedergefunden") for e in log) and st["keine_order"] == []
    # und sie füllt ganz normal
    pos = k.fuelle(deal, 3990.0, NOW + pd.Timedelta(minutes=7))
    st, log, *_ = lauf(k, st, NOW + 2 * MIN5, bid=3991.0)
    assert st["trade"]["dealId"] == pos and st["orders"] == []


def test_bestaetigung_fehlt_und_die_order_fuellt_sofort(welt):
    welt["plan"]["kandidaten"] = [LANG]
    k = Konto()
    k.ohne_bestaetigung = True
    st, *_ = lauf(k, {}, NOW)
    k.ohne_bestaetigung = False
    (deal,) = k.wo
    pos = k.fuelle(deal, 3989.8, NOW + pd.Timedelta(minutes=2))
    k.bid, k.offer = 3990.5, 3990.8
    st, log, fertig, _ = lauf(k, st, NOW + MIN5, bid=3991.0)
    assert st["trade"]["dealId"] == pos and st["trade"]["entry"] == 3989.8 and st["orders"] == [] and len(k.posts()) == 1
    assert "fremde Gold-Position auf dem Konto" not in st["keine_order"]


def test_legen_scheitert_ganz_dann_neuer_versuch_im_naechsten_lauf(welt):
    welt["plan"]["kandidaten"] = [LANG]
    k = Konto()
    k.post_kaputt = True
    st, log, *_ = lauf(k, {}, NOW)
    assert k.wo == {} and st["orders"][0]["dealId"] is None
    k.post_kaputt = False
    st, log, fertig, _ = lauf(k, st, NOW + MIN5)
    assert len(k.wo) == 1 and len(k.posts()) == 2 and st["orders"][0]["dealId"] in k.wo and fertig == []
    assert any(e["event"].startswith("Order nicht mehr beim Broker") for e in log)


def test_order_bleibt_solange_sie_beim_broker_liegt_auch_wenn_die_stundenkerze_eine_beruehrung_zeigt(welt):
    welt["plan"]["kandidaten"] = [LANG]
    k = Konto()
    st, *_ = lauf(k, {}, NOW)
    welt["plan"]["kandidaten"] = [dict(LANG, beruehrt=True)]      # eine Stunde später: laut Kerze berührt, nicht gefüllt
    st, log, *_ = lauf(k, st, NOW + pd.Timedelta(hours=1))
    assert welt["plaene"] == 2 and k.geloescht() == [] and len(st["orders"]) == 1 and st["verbraucht"] == {}
    # ohne Order beim Broker gilt dieselbe Zone als verbraucht
    k2 = Konto()
    st2, log2, *_ = lauf(k2, {}, NOW)
    assert k2.posts() == [] and "Stundenkerzen" in st2["verbraucht"][LANG["name"]]["grund"]


def test_zone_gilt_nicht_mehr_dann_wird_die_order_geloescht_und_die_naechste_gelegt(welt):
    welt["plan"]["kandidaten"] = [LANG, LANG2]
    k = Konto()
    st, *_ = lauf(k, {}, NOW)
    assert [p["level"] for p in k.posts()] == [3990.0]
    welt["plan"]["kandidaten"] = [LANG2]                          # 30 Kerzen um oder Schluss zurück: LANG fällt weg
    st, log, *_ = lauf(k, st, NOW + pd.Timedelta(hours=1))
    assert len(k.geloescht()) == 1 and [p["level"] for p in k.posts()] == [3990.0, 3980.0]
    assert [o["name"] for o in st["orders"]] == [LANG2["name"]] and LANG["name"] not in st["verbraucht"]


def test_kurs_schon_an_der_linie_dann_ist_die_zone_verbraucht(welt):
    welt["plan"]["kandidaten"] = [LANG, LANG2]
    k = Konto(bid=3989.0, offer=3989.3)                           # Ask unter der Linie 3990, über 3980
    st, log, *_ = lauf(k, {}, NOW, bid=3995.0)
    assert "an oder hinter der Linie" in st["verbraucht"][LANG["name"]]["grund"]
    assert [p["level"] for p in k.posts()] == [3980.0]
    # Berührung in einer 5-Minuten-Kerze seit dem Plan, der Kurs ist längst wieder weg: genauso verbraucht
    k2 = Konto()
    st2, *_ = lauf(k2, {}, NOW + MIN5, k1500=(4001.0, 3989.6))    # Ask-Tief 3989,9
    assert "5-Minuten-Kerzen" in st2["verbraucht"][LANG["name"]]["grund"] and [p["level"] for p in k2.posts()] == [3980.0]
    # dieselbe Kerze vor dem Plan (schon in den Stundenkerzen gezählt) verbraucht nichts
    k3 = Konto()
    st3, *_ = lauf(k3, {}, NOW + MIN5, k1455=(4001.0, 3989.6))
    assert st3["verbraucht"] == {} and [p["level"] for p in k3.posts()] == [3990.0]


def test_order_weg_ohne_fuellung_wird_neu_gelegt(welt):
    welt["plan"]["kandidaten"] = [LANG]
    k = Konto()
    st, *_ = lauf(k, {}, NOW)
    k.wo.clear()                                                  # abgelaufen oder von Hand gelöscht
    st, log, fertig, _ = lauf(k, st, NOW + MIN5)
    assert any(e["event"].startswith("Order nicht mehr beim Broker") for e in log) and fertig == []
    assert len(k.posts()) == 2 and len(st["orders"]) == 1 and st["verbraucht"] == {}


def test_order_dreimal_abgelehnt_dann_ist_die_zone_verbraucht(welt):
    welt["plan"]["kandidaten"] = [LANG]
    k = Konto()
    k.ablehnen = True
    st = {}
    for i in range(4):
        st, log, *_ = lauf(k, st, NOW + i * MIN5)
    assert len(k.posts()) == 3 and st["orders"] == []
    assert "3-mal keine Order möglich" in st["verbraucht"][LANG["name"]]["grund"]


def test_markt_zu_oder_kurs_zu_nah_dann_wartet_die_order(welt):
    welt["plan"]["kandidaten"] = [LANG]
    k = Konto()
    k.handelbar = False
    st, log, *_ = lauf(k, {}, NOW)
    assert k.posts() == [] and st["keine_order"] == ["Markt gerade nicht handelbar"] and st["verbraucht"] == {}
    k.handelbar = True
    k.bid, k.offer = 3989.75, 3990.05                             # Ask 5 Cent über der Linie, Mindestabstand 10 Cent
    st, log, *_ = lauf(k, st, NOW + MIN5, bid=3995.0)
    assert k.posts() == [] and st["verbraucht"] == {} and st["versuche"] == {}
    assert any("Mindestabstand" in g for e in log if e["event"] == "Order nicht gelegt" for g in e["gruende"])
    st, log, *_ = lauf(k, st, NOW + 2 * MIN5, bid=3995.0)         # gleiche Lage: keine zweite Meldung
    assert log == [] and k.posts() == []
    k.bid, k.offer = 3995.0, 3995.3
    st, log, *_ = lauf(k, st, NOW + 3 * MIN5, bid=3995.0)
    assert len(k.posts()) == 1 and "wartet" not in st


# --------------------------------------------------------------------------------------------------------------------
# Füllung und Führung

def test_fuellung_wird_zum_trade_und_das_ziel_kommt_aus_dem_fuellkurs(welt):
    k, st, deal = gefuellt(welt, level=3984.0)
    (kauf,) = k.posts()                                           # nur diese eine Order lag beim Broker
    assert kauf["profitLevel"] == 4100.0                          # vorläufig, mit der Linie gerechnet: 4040 wären 3,6 R
    st, log, fertig, _ = lauf(k, st, NOW + MIN5, bid=3985.0, k1500=(4001.0, 3983.5))
    tr = st["trade"]
    assert tr["dealId"] == deal and tr["richtung"] == 1 and tr["entry"] == 3984.0 and tr["zone"] == LANG["name"]
    assert tr["r_usd"] == 8.0 and tr["stop"] == 3976.0            # Risiko vom Füllkurs bis zum Stop
    assert tr["ziel"] == 4040.0 and tr["ziel_r"] == 7.0           # mit dem Füllkurs sind 4040 jetzt 7 R entfernt
    assert tr["opened_utc"] == "2026-03-04T15:05:00" and tr["fuellkerze"] == "2026-03-04 15:05:00"
    assert k.aenderungen() == [{"stopLevel": 3976.0, "profitLevel": 4040.0}]
    assert k.geloescht() == [] and st["orders"] == [] and k.wo == {}
    assert st["verbraucht"][LANG["name"]]["grund"] == "gehandelt" and fertig == []
    assert len(k.posts()) == 1                                    # solange der Trade offen ist, keine neue Order
    assert st["keine_order"] == ["ein Trade ist offen"] and zb.status(st).startswith("Kauf offen ab 3984.00")
    # nächster Lauf: nichts zu tun
    st, log, *_ = lauf(k, st, NOW + 2 * MIN5, bid=3986.0)
    assert len(k.aenderungen()) == 1 and log == [] and st["trade"]["einstand"] is None


def test_andere_linie_waehrend_des_trades_beruehrt_ist_verbraucht_wie_im_test(welt):
    k, st, deal = gefuellt(welt, level=3984.0)
    st, *_ = lauf(k, st, NOW + MIN5, bid=3985.0, k1505=(3986.0, 3979.5))          # Ask-Tief 3979,8: Linie 3980 berührt
    assert "ohne dass eine Order lag" in st["verbraucht"][LANG2["name"]]["grund"]
    k.acts[deal] = [{"dateUTC": "2026-03-04T15:11:00", "source": "SL", "type": "POSITION", "status": "ACCEPTED",
                     "details": {"level": 3976.0, "actions": [{"actionType": "POSITION_CLOSED"}]}}]
    del k.pos[deal]
    k.bid, k.offer = 3990.0, 3990.3
    st, log, fertig, _ = lauf(k, st, NOW + 2 * MIN5, bid=3990.0)
    assert [t["grund"] for t in fertig] == ["stop"] and fertig[0]["r"] == -1.0 and fertig[0]["pnl_eur"] == -2.81
    assert st["trade"] is None and st["trades"] == 1 and st["summe_r"] == -1.0
    # danach liegt die Verkaufs-Order: beide Kauf-Zonen sind verbraucht
    assert [p["direction"] for p in k.posts()[1:]] == ["SELL"]


def test_einstand_nach_2_r(welt):
    k, st, deal = gefuellt(welt, level=3984.0)
    st, *_ = lauf(k, st, NOW + MIN5, bid=3985.0)
    # 2 R = 16 $: die Füllkerze selbst zählt nicht, erst die Kerze danach
    st, log, *_ = lauf(k, st, NOW + 2 * MIN5, bid=3985.0, k1505=(4000.5, 3984.5))
    assert st["trade"]["einstand"] is None and len(k.aenderungen()) == 1
    k.bid, k.offer = 3999.0, 3999.3
    st, log, *_ = lauf(k, st, NOW + 3 * MIN5, bid=3999.0, k1510=(4000.0, 3998.0))
    assert st["trade"]["bestes"] == 4000.0 and st["trade"]["einstand"] and st["trade"]["stop"] == 3984.0
    assert k.aenderungen()[-1] == {"stopLevel": 3984.0, "profitLevel": 4040.0}
    assert zb.status(st).endswith("Stop am Einstieg")
    # der Broker stoppt am Einstieg aus: Grund "einstand", 0 R
    k.acts[deal] = [{"dateUTC": "2026-03-04T15:22:00", "source": "SL", "type": "POSITION", "status": "ACCEPTED",
                     "details": {"level": 3984.0, "actions": [{"actionType": "POSITION_CLOSED"}]}}]
    del k.pos[deal]
    st, log, fertig, _ = lauf(k, st, NOW + 4 * MIN5, bid=3984.0)
    assert [(t["grund"], t["r"]) for t in fertig] == [("einstand", 0.0)] and fertig[0]["einstand"]


def test_einstand_kurs_schon_zu_nah_dann_zum_markt(welt):
    k, st, deal = gefuellt(welt, level=3984.0)
    st, *_ = lauf(k, st, NOW + MIN5, bid=3985.0)
    k.bid, k.offer = 3984.05, 3984.35                             # 2 R waren da, der Kurs ist zurück am Einstieg
    st, log, fertig, _ = lauf(k, st, NOW + 2 * MIN5, bid=3990.0, k1510=(4000.2, 3984.0))
    assert k.geschlossen() == [deal] and len(k.aenderungen()) == 1
    assert [(t["grund"], t["exit"]) for t in fertig] == [("einstand", 3984.05)] and st["trade"] is None


def test_ziel_beim_broker_und_uebernachtgebuehr_wie_im_test(welt):
    k, st, deal = gefuellt(welt, level=3984.0)
    st, *_ = lauf(k, st, NOW + MIN5, bid=3985.0)
    spaeter = NOW + pd.Timedelta(days=2)
    k.acts[deal] = [{"dateUTC": "2026-03-06T14:00:00", "source": "TP", "type": "POSITION", "status": "ACCEPTED",
                     "details": {"level": 4040.0, "actions": [{"actionType": "POSITION_CLOSED"}]}}]
    del k.pos[deal]
    st, log, fertig, _ = lauf(k, st, spaeter, bid=4040.0)
    t = fertig[0]
    gebuehr = 6.5 / 100 / 365 * 2 * 3984.0 / 8.0                  # 2 Nächte, Satz des Tests für Long
    assert t["grund"] == "ziel" and t["naechte"] == 2 and t["r_roh"] == 7.0 and t["gebuehr_r"] == round(gebuehr, 3)
    assert t["r"] == round(7.0 - gebuehr, 3) and t["pnl_eur"] == round(0.38 * 56.0 / 1.08, 2)


def test_ein_ziel_wird_nie_als_stop_gebucht_nur_weil_die_kontoaktivitaet_fehlt(welt):
    """Die Position ist beim Broker zu, aber der Schluss steht noch nicht in der Kontoaktivität. Der Bot wartet bis zu
    einer Stunde, statt sofort den Stop-Kurs zu buchen. Danach zählt der Stop-Kurs, als geschätzt markiert."""
    k, st, deal = gefuellt(welt, level=3984.0)
    st, *_ = lauf(k, st, NOW + MIN5, bid=3985.0)
    spaeter = NOW + pd.Timedelta(days=3)
    del k.pos[deal]
    k.bid, k.offer = 4041.0, 4041.3
    st, log, fertig, _ = lauf(k, st, spaeter, bid=4041.0)
    assert fertig == [] and st["trade"]["weg_seit"] and k.aenderungen()[1:] == [] and k.geschlossen() == []
    assert [e["event"] for e in log if "Schlusskurs" in e["event"]] == ["Position beim Broker zu, Schlusskurs noch nicht lesbar"]
    assert zb.status(st).startswith("Position beim Broker geschlossen") and len(k.posts()) == 1
    k.aktivitaet = None                                           # zweiter Lauf: Aktivität gar nicht lesbar
    st, log, fertig, _ = lauf(k, st, spaeter + MIN5, bid=4041.0)
    assert fertig == [] and not any("Schlusskurs" in e["event"] for e in log)
    k.aktivitaet = []
    k.acts[deal] = [
        {"dateUTC": "2026-03-07T15:00:00", "source": "USER", "type": "POSITION", "status": "ACCEPTED",
         "details": {"level": 3984.0, "actions": [{"actionType": "STOP_LIMIT_AMENDED"}]}},     # nur eine Änderung
        {"dateUTC": "2026-03-07T15:01:00", "source": "TP", "type": "POSITION", "status": "ACCEPTED",
         "details": {"level": 4040.0, "actions": [{"actionType": "POSITION_CLOSED"}]}}]
    st, log, fertig, _ = lauf(k, st, spaeter + 2 * MIN5, bid=4041.0)
    assert [(t["grund"], t["exit"], t["r_roh"]) for t in fertig] == [("ziel", 4040.0, 7.0)]
    assert "exit_geschaetzt" not in fertig[0] and st["trade"] is None
    # ohne jeden Schluss in der Aktivität: nach einer Stunde der Stop-Kurs, als geschätzt markiert
    k2, st2, deal2 = gefuellt(welt, level=3984.0)
    st2, *_ = lauf(k2, st2, NOW + MIN5, bid=3985.0)
    del k2.pos[deal2]
    st2, _, fertig2, _ = lauf(k2, st2, NOW + 2 * MIN5, bid=3975.0)
    st2, _, fertig3, _ = lauf(k2, st2, NOW + 13 * MIN5, bid=3975.0)
    assert fertig2 == [] and fertig3 == [] and st2["trade"]["weg_seit"]
    st2, _, fertig4, _ = lauf(k2, st2, NOW + 14 * MIN5, bid=3975.0)
    assert [(t["grund"], t["exit"], t["exit_geschaetzt"]) for t in fertig4] == [("stop", 3976.0, True)]


def test_ohne_kurs_eur_usd_wartet_die_order_und_zaehlt_nicht_als_versuch(welt):
    welt["plan"]["kandidaten"] = [LANG]
    k = Konto()
    k.eur_ok = False
    st = {}
    for i in range(4):
        st, log, *_ = lauf(k, st, NOW + i * MIN5)
    assert k.posts() == [] and st["versuche"] == {} and st["verbraucht"] == {}
    k.eur_ok = True
    st, log, *_ = lauf(k, st, NOW + 4 * MIN5)
    assert len(k.posts()) == 1


def test_zu_wenig_freie_marge_dann_wartet_die_order(welt, monkeypatch):
    welt["plan"]["kandidaten"] = [LANG]
    k = Konto()
    monkeypatch.setattr(k, "accounts", lambda: [{"accountId": zb.KONTO, "balance": {"balance": 60.0, "available": 60.0}}])
    st, log, *_ = lauf(k, {}, NOW)                                # Marge 0,38 Unzen * 3990 $ * 5 % / 1,08 = 70 €
    assert k.posts() == [] and st["versuche"] == {} and st["verbraucht"] == {}
    assert any("freie Marge" in g for e in log if e["event"] == "Order nicht gelegt" for g in e["gruende"])


def test_zeit_ausstieg_nach_14_kalendertagen(welt):
    k, st, deal = gefuellt(welt, level=3984.0)
    st, *_ = lauf(k, st, NOW + MIN5, bid=3985.0)
    vorher = NOW + pd.Timedelta(days=14)                          # Füllung war 15:05: noch 5 Minuten zu früh
    st, *_ = lauf(k, st, vorher, bid=3990.0)
    assert k.geschlossen() == []
    k.bid, k.offer = 3991.0, 3991.3
    st, log, fertig, _ = lauf(k, st, vorher + MIN5, bid=3991.0)
    assert k.geschlossen() == [deal] and [(t["grund"], t["exit"], t["naechte"]) for t in fertig] == [("zeit", 3991.0, 14)]


def test_fuellung_jenseits_der_inneren_linie_wird_sofort_geschlossen(welt):
    k, st, deal = gefuellt(welt, level=3981.0)                    # innere Linie 3982: Kurslücke durch die Zone
    st, log, fertig, _ = lauf(k, st, NOW + MIN5, bid=3982.0)
    assert k.geschlossen() == [deal] and k.aenderungen() == []
    t = fertig[0]
    assert t["grund"] == "kurslücke" and t["r_usd"] == 14.0 and t["exit"] == 3982.0 and t["r"] == round(1.0 / 14.0, 3)
    assert st["trade"] is None and st["verbraucht"][LANG["name"]]["grund"] == "gehandelt"


def test_gefuellt_und_schon_wieder_zu_zwischen_zwei_laeufen(welt):
    welt["plan"]["kandidaten"] = [LANG]
    k = Konto()
    st, *_ = lauf(k, {}, NOW)
    k.wo.clear()
    k.aktivitaet = [
        {"epic": "EURUSD", "dateUTC": "2026-03-04T15:04:00", "source": "SL", "type": "POSITION", "status": "ACCEPTED",
         "details": {"level": 1.08, "actions": [{"actionType": "POSITION_CLOSED"}]}},      # Mess-Bot, anderer Markt
        {"epic": "GOLD", "dateUTC": "2026-03-04T15:04:10", "source": "SYSTEM", "type": "POSITION", "status": "ACCEPTED",
         "details": {"level": 3989.9, "actions": [{"actionType": "POSITION_OPENED"}]}},
        {"epic": "GOLD", "dateUTC": "2026-03-04T15:06:30", "source": "SL", "type": "POSITION", "status": "ACCEPTED",
         "details": {"level": 3975.8, "actions": [{"actionType": "POSITION_CLOSED"}]}}]
    st, log, fertig, _ = lauf(k, st, NOW + MIN5, bid=3975.0)
    t = fertig[0]
    assert t["grund"] == "stop" and t["entry"] == 3989.9 and t["exit"] == 3975.8 and t["zwischen_zwei_laeufen"]
    assert t["r"] == round((3975.8 - 3989.9) / 13.9, 3) and not t["einstieg_geschaetzt"]
    assert st["verbraucht"][LANG["name"]]["grund"] == "gehandelt" and len(k.posts()) == 1 and st["orders"] == []


def test_schluss_des_letzten_trades_zaehlt_nie_fuer_die_naechste_order(welt):
    """Der Stop des alten Trades steht noch in der Kontoaktivität. Verschwindet danach eine neue Order ohne Füllung,
    darf daraus kein Trade werden."""
    k, st, deal = gefuellt(welt, level=3984.0)
    st, *_ = lauf(k, st, NOW + MIN5, bid=3985.0)
    schluss = {"epic": "GOLD", "dealId": deal, "dateUTC": "2026-03-04T15:14:59", "source": "SL", "type": "POSITION",
               "status": "ACCEPTED", "details": {"level": 3976.0, "actions": [{"actionType": "POSITION_CLOSED"}]}}
    k.acts[deal] = [schluss]
    k.aktivitaet = [schluss]
    del k.pos[deal]
    k.bid, k.offer = 4010.0, 4010.3
    st, log, fertig, _ = lauf(k, st, NOW + 2 * MIN5, bid=4010.0)             # bucht den Stop, legt die Verkaufs-Order
    assert len(fertig) == 1 and st["letzte_deals"] == [deal] and [p["direction"] for p in k.posts()] == ["BUY", "SELL"]
    k.wo.clear()                                                  # die neue Order verschwindet ohne Füllung
    st, log, fertig, _ = lauf(k, st, NOW + 3 * MIN5, bid=4010.0)
    assert fertig == [] and st["trades"] == 1 and KURZ["name"] not in st["verbraucht"]
    assert any(e["event"].startswith("Order nicht mehr beim Broker") for e in log)


def test_kontoaktivitaet_nicht_lesbar_dann_bleibt_die_order_im_zustand(welt):
    welt["plan"]["kandidaten"] = [LANG]
    k = Konto()
    st, *_ = lauf(k, {}, NOW)
    k.wo.clear()
    k.aktivitaet = None
    st, log, fertig, _ = lauf(k, st, NOW + MIN5)
    assert fertig == [] and len(st["orders"]) == 1 and len(k.posts()) == 1       # nichts doppelt gelegt
    assert any(e["event"] == "Kontoaktivität nicht lesbar" for e in log)


def test_fremde_gold_position_wird_nie_uebernommen(welt):
    welt["plan"]["kandidaten"] = [LANG]
    k = Konto()
    st, *_ = lauf(k, {}, NOW)
    k.wo.clear()                                                  # Order weg, und jemand hat von Hand Gold gekauft
    k.fremd = [{"market": {"epic": "GOLD"}, "position": {"dealId": "X1", "direction": "BUY", "size": 0.5, "level": 3999.0}}]
    st, log, fertig, _ = lauf(k, st, NOW + MIN5)
    assert st["trade"] is None and fertig == [] and len(k.posts()) == 1 and k.geschlossen() == []
    assert "fremde Gold-Position auf dem Konto" in st["keine_order"]


# --------------------------------------------------------------------------------------------------------------------
# Wochenende, Sperren, Pause

def test_am_wochenende_liegt_keine_order(welt):
    welt["plan"]["kandidaten"] = [LANG, KURZ]
    freitag = pd.Timestamp("2026-03-06 21:38", tz="UTC")          # 16:38 Uhr New York
    k = Konto()
    st, *_ = lauf(k, {}, freitag)
    assert len(k.posts()) == 1 and k.posts()[0]["goodTillDate"] == "2026-03-06T21:45:00"
    st, log, *_ = lauf(k, st, freitag + 2 * MIN5)                 # 16:48 Uhr: Order weg
    assert len(k.geloescht()) == 1 and st["orders"] == [] and st["keine_order"][0].startswith("Wochenende")
    st, log, *_ = lauf(k, st, pd.Timestamp("2026-03-07 12:03", tz="UTC"))
    assert len(k.posts()) == 1 and welt["plaene"] == 1            # Samstag: keine Order, kein neuer Plan
    st, log, *_ = lauf(k, st, pd.Timestamp("2026-03-08 22:08", tz="UTC"))        # Sonntag 18:08 Uhr New York
    assert len(k.posts()) == 2 and welt["plaene"] == 2 and st["keine_order"] == []
    assert k.posts()[1]["goodTillDate"] == "2026-03-13T20:45:00"


@pytest.mark.parametrize("fall, text", [("vorab", "nicht festgelegt"), ("fremd", "fremde Gold-Position"),
                                        ("order", "fremde Gold-Order"), ("anderer", "auch für gold-neu vergeben"),
                                        ("pause", "Pause ab -25 R")])
def test_sperren_keine_neue_order_und_die_liegende_wird_geloescht(welt, fall, text):
    welt["plan"]["kandidaten"] = [LANG, KURZ]
    k = Konto()
    st, *_ = lauf(k, {}, NOW)
    (meine,) = k.wo
    if fall == "vorab":
        welt["vorab"] = False
    elif fall == "fremd":
        k.fremd = [{"market": {"epic": "GOLD"}, "position": {"dealId": "X1", "direction": "SELL", "size": 1.0, "level": 4001.0}}]
    elif fall == "order":                                         # jemand hat von Hand eine Gold-Order gelegt
        k.wo["X9"] = {"epic": "GOLD", "direction": "SELL", "level": 4050.0}
    elif fall == "anderer":
        welt["zuordnung"] = {"gold-neu": zb.KONTO, "r6-vortag-eurusd-1atr": zb.KONTO}
    else:
        st["pausiert"] = {"seit": "2026-03-01T00:00:00", "grund": "Test"}
    st, log, *_ = lauf(k, st, NOW + MIN5)
    assert k.geloescht() == [meine] and st["orders"] == [] and len(k.posts()) == 1
    assert any(text in g for g in st["keine_order"])
    assert (fall == "order") == ("X9" in k.wo)                    # eine fremde Order löscht der Bot nie
    st, log, *_ = lauf(k, st, NOW + 2 * MIN5)                     # gleiche Lage: keine zweite Meldung
    assert log == [] and len(k.posts()) == 1


def test_pause_ab_minus_25_r(welt):
    k, st, deal = gefuellt(welt, level=3984.0)
    st, *_ = lauf(k, st, NOW + MIN5, bid=3985.0)
    st["summe_r"] = -24.5
    k.acts[deal] = [{"dateUTC": "2026-03-04T15:11:00", "source": "SL", "type": "POSITION", "status": "ACCEPTED",
                     "details": {"level": 3976.0, "actions": [{"actionType": "POSITION_CLOSED"}]}}]
    del k.pos[deal]
    st, log, fertig, _ = lauf(k, st, NOW + 2 * MIN5, bid=3990.0)
    assert st["summe_r"] == -25.5 and st["pausiert"] and "Kirons Entscheidung" in st["pausiert"]["grund"]
    assert len(k.posts()) == 1 and zb.status(st).startswith("Pause")             # keine neue Order mehr


def test_ohne_plan_oder_ohne_kerzen_keine_order(welt):
    welt["plan"] = None
    k = Konto()
    st, log, *_ = lauf(k, {}, NOW)
    assert k.posts() == [] and st["keine_order"] == ["kein Plan"] and st["plan"] is None
    welt["plan"] = {"kandidaten": [LANG], "linien": {"1": [], "-1": []}}
    k.m5 = []
    st, log, *_ = zb.run(k, st, NOW.to_pydatetime())
    assert k.posts() == [] and st["keine_order"] == ["keine 5-Minuten-Kerzen"]
    st, log, *_ = lauf(k, st, NOW + MIN5)
    assert len(k.posts()) == 1


def test_fehlt_die_letzte_stundenkerze_bleibt_der_alte_plan(welt, monkeypatch):
    welt["plan"]["kandidaten"] = [LANG]
    k = Konto()
    st, *_ = lauf(k, {}, NOW)
    alt = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "ask_low": [1.0]},
                       index=pd.DatetimeIndex(["2026-03-04 14:00"]))      # die Kerze 15 bis 16 Uhr fehlt noch
    monkeypatch.setattr(zb, "stundenkerzen", lambda client, now: alt)
    st, log, *_ = lauf(k, st, NOW + pd.Timedelta(hours=1))
    assert st["plan"]["stunde"] == "2026-03-04 15:00:00" and st["keine_order"] == ["Plan nicht aus dieser Stunde"]
    assert k.geloescht() == [] and len(st["orders"]) == 1         # die liegende Order bleibt
    st, log, *_ = lauf(k, st, NOW + pd.Timedelta(hours=5))        # Plan älter als 4 Stunden: Order weg
    assert len(k.geloescht()) == 1 and "Plan älter als 4 Stunden" in st["keine_order"]


def test_kein_account_2_oder_trockenlauf_sendet_nichts(welt):
    welt["plan"]["kandidaten"] = [LANG]
    k = Konto(konto2=False)
    st, log, fertig, blick = lauf(k, {}, NOW)
    assert k.calls == [] and "nicht gefunden" in blick["status"] and k.account_id == HAUPT
    k = Konto()
    k.m5 = kerzen5(NOW)
    st, log, fertig, blick = zb.run(k, {}, NOW.to_pydatetime(), send_orders=False)
    assert k.calls == [] and st["orders"] == [] and any(e["event"] == "würde Order legen" for e in log)


def test_nie_das_hauptkonto(monkeypatch):
    assert not zb.KONTO.endswith(zb.HAUPT_ENDUNG) and zb.KONTO.endswith("2606") and zb.KONTO_NAME == "Account 2"
    k = Konto()
    la = zb.Lauf(k, {}, NOW.to_pydatetime())
    with pytest.raises(RuntimeError):                             # aktives Konto ist noch das Hauptkonto
        la.nur_mein_konto()
    monkeypatch.setattr(zb, "KONTO", HAUPT)                       # stünde das Hauptkonto im Code: kein Lauf
    st, log, *_ = zb.run(k, {}, NOW.to_pydatetime())
    assert k.calls == [] and log[0]["event"] == "kein Konto"


# --------------------------------------------------------------------------------------------------------------------
# Journal, Urteil, Regeldatei

def test_journal_nur_eigene_dateien_und_nur_bei_aenderung(welt, tmp_path):
    welt["plan"]["kandidaten"] = [LANG]
    k = Konto()
    st, log, fertig, blick = lauf(k, {}, NOW)
    jdir, cp = tmp_path / "gold-zonen", tmp_path / "gold-zonen.json"
    assert zb.schreiben(st, log, fertig, blick, jdir, cp) is True
    karte = json.loads(cp.read_text(encoding="utf-8"))
    assert karte["bot"] == "gold-zonen" and karte["konto"] == "Account 2 …2606" and karte["vorab"].endswith("_bot.yaml")
    assert karte["zusammenfassung"]["urteil"] == "läuft (0 von 40 Trades)" and "DURCHGEFALLEN" in karte["backtest"]
    assert zb.KONTO not in cp.read_text(encoding="utf-8") + (jdir / "state.json").read_text(encoding="utf-8")
    st2, log2, fertig2, blick2 = lauf(k, st, NOW + MIN5)          # nur die Uhrzeit ist neu: nichts schreiben
    assert log2 == [] and zb.schreiben(st2, log2, fertig2, blick2, jdir, cp) is False
    assert json.loads((jdir / "state.json").read_text(encoding="utf-8"))["stand"] == st["stand"]
    assert len((jdir / "log.jsonl").read_text(encoding="utf-8").splitlines()) == len(log)
    with pytest.raises(RuntimeError):
        zb.schreiben(st, log, fertig, blick, tmp_path / "gold-state.json", cp)
    with pytest.raises(RuntimeError):
        zb.schreiben(st, log, fertig, blick, jdir, tmp_path / "gold-trades.jsonl")
    assert zb.JDIR.name == "gold-zonen" and zb.COCKPIT.name == "gold-zonen.json"


def test_urteil_nach_15_und_40_trades():
    def tr(werte):
        return [{"r": r, "pnl_eur": r * 5} for r in werte]
    assert zb.bewertung([])["urteil"] == "läuft (0 von 40 Trades)" and zb.bewertung([])["pf_r"] is None
    b = zb.bewertung(tr([-1.0] * 13 + [3.0, 3.0]))
    assert b["pf_r"] == 0.46 and "Zwischencheck nach 15 Trades" in b["urteil"]
    assert zb.bewertung(tr([-1.0] * 12 + [3.0] * 3))["urteil"] == "läuft (15 von 40 Trades)"      # GF 0,75
    gut = zb.bewertung(tr(([-1.0] * 6 + [9.0]) * 6))              # die ersten 40 zählen: GF 45 / 35 = 1,29
    assert gut["trades"] == 42 and gut["urteil"].startswith("bestanden nach 40 Trades")
    knapp = zb.bewertung(tr(([-1.0] * 7 + [8.0]) * 5))            # GF 1,14: unter 1,2
    assert knapp["pf_r"] == 1.14 and knapp["urteil"].startswith("durchgefallen nach 40 Trades")


def test_code_und_regeldatei_passen_zusammen():
    """Die Zahlen im Code sind die Zahlen der Regeldatei, und die Regeldatei steht mit ihrer Prüfsumme im Protokoll."""
    import yaml
    cfg = yaml.safe_load(zb.VORAB.read_text(encoding="utf-8"))["gold_zonen_bot"]
    assert zb.vorab_ok(), "suche/VORAB_gold_zonen_bot.yaml steht nicht mit passender Prüfsumme im Protokoll"
    assert cfg["bot"] == zb.BOT_ID and "Account 2" in cfg["konto"] and zb.KONTO[-4:] in cfg["konto"]
    assert zb.KONTO not in zb.VORAB.read_text(encoding="utf-8")
    assert "B_alle" in cfg["regel"] and "suche/VORAB_gold_zonen.yaml" in cfg["regel"]
    assert cfg["groesse"]["risiko_eur"] == zb.RISIKO_EUR and cfg["groesse"]["max_unzen"] == zb.MAX_OZ
    assert "mehr als\n      verdoppeln".replace("\n      ", " ") in cfg["groesse"]["runden"] and zb.MAX_RISIKO_FAKTOR == 2.0
    assert any(f"Ab {zb.PAUSE_R:.0f} R" in s for s in cfg["sperren"])
    u = cfg["urteil"]
    assert u["nach_trades"] == zb.URTEIL_NACH and "mindestens 1,2" in u["bestanden"] and zb.URTEIL_PF == 1.2
    assert u["zwischencheck"].startswith(f"Nach {zb.ZWISCHEN_NACH} Trades") and "unter 0,6" in u["zwischencheck"]
    a = cfg["ausfuehrung"]
    assert f"etwa {zb.TAGE_KERZEN} Tage" in a["kerzen"] and "16:45" in a["wochenende"] and "18:05" in a["wochenende"]
    assert "14 Kalendertage" in a["zeit"] and gz.HALTE_TAGE == 14 and "2 R" in a["einstand"] and gz.EINSTAND_R == 2.0
    assert f"{zb.MAX_VERSUCHE}-mal" in a["order"]


def test_bot_steht_als_mitnutzer_auf_account_2_und_nie_in_der_zuordnung():
    from gold.bot import konten
    from suche import mitnutzer as mn
    eintrag = next(b for b in mn.bots() if b["bot"] == zb.BOT_ID)
    assert eintrag == {"bot": "gold-zonen", "konto": zb.KONTO, "konto_name": "Account 2", "neu": True,
                       "quelle": "gold/zonen_bot.py"}
    kont = konten.load(zb.ROOT / "journal")
    assert zb.BOT_ID not in (kont.get("zuordnung") or {})
    assert "gold-zonen" in mn.konten()[zb.KONTO]                  # so vergibt die Prüfung Account 2 nie neu
