"""Tests für gold/short_bot.py: die neue Führung (Ziele mal 0,75, Prüfer, Halten), nur fertige 1-Std.- und 4-Std.-Kerzen,
die Zusammenlegung der drei Seiten, Größen und der Lauf auf dem Demokonto (nur Konto 5, nie das Hauptkonto, nie die
Dateien des Gold-Bots)."""
import json

import numpy as np
import pandas as pd
import pytest

from gold import short_bot as sb
from gold import tiktok_schatten as ts
from suche.demo_bots import Quote, with_now_bar

NY = "America/New_York"
HAUPT = "111111113150"


def _b(o, h, lo, c, sp=0.0, start="2026-03-02 15:00"):
    n = len(o)
    idx = pd.date_range(start, periods=n, freq="15min")
    bars = pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx, dtype=float)
    return ts.basis(bars, pd.Series(sp, index=idx, dtype=float))


def _q(**kw):
    base = dict(bid=4000.0, offer=4000.3, tradeable=True, currency="USD", lot=1.0, min_size=0.01, size_step=0.01,
                margin_pct=5.0, decimals=2, min_dist=0.1, eur_rate=1.08)
    base.update(kw)
    return Quote(**base)


# --------------------------------------------------------------------------------------------------------------------
# Führung

def test_ziele_mal_075_und_einstand():
    # Verkauf bei 100, Stop 102 (1 R = 2). Erstes Ziel 0,75 R = 98,5 statt 98, dann Einstand für den Rest
    o = [100, 100, 99.4, 98.8, 99.0, 99.6]
    h = [100.2, 100.3, 99.6, 99.1, 99.7, 100.4]
    lo = [99.8, 99.3, 98.6, 98.4, 98.9, 99.5]
    b = _b(o, h, lo, o)
    teile, offen = sb.fuehre_neu(b, -1, 1, 6, 100.0, 102.0)
    assert teile[0] == {"w": 1 / 3, "px": 98.5, "j": 3, "grund": "tp1"}
    assert teile[1]["grund"] == "einstand" and teile[1]["px"] == 100.0 and not offen


def test_pruefer_schliesst_am_einstieg():
    # Verkauf bei 100, Stop 102: Kurs läuft auf 101,2 (über 0,5 R = 101), kommt dann auf 100 zurück -> raus am Einstieg
    o = [100, 100, 100.6, 101.0, 100.4, 99.8]
    h = [100.2, 100.7, 101.2, 101.1, 100.5, 99.9]
    lo = [99.8, 99.9, 100.5, 100.3, 99.9, 99.6]
    b = _b(o, h, lo, o)
    teile, offen = sb.fuehre_neu(b, -1, 1, 6, 100.0, 102.0)
    assert teile == [{"w": 1.0, "px": 100.0, "j": 4, "grund": "pruefer"}] and not offen
    assert sb.fehl_index(b, -1, 1, 6, 100.0, 2.0) == 2
    # Erreicht er vorher sein erstes Ziel, wird er nie zum Fehltrade
    o2 = [100, 100, 98.6, 99.6, 100.8, 100.8]
    h2 = [100.2, 100.1, 99.8, 101.2, 101.0, 101.0]
    lo2 = [99.8, 98.4, 98.5, 99.5, 100.6, 100.6]
    assert sb.fehl_index(_b(o2, h2, lo2, o2), -1, 1, 6, 100.0, 2.0) == -1


def test_halten_im_minus_bis_einstieg():
    # Gegensignal (jf = 3) im Minus: der Short bleibt offen und schließt, sobald der Kurs wieder bei 100 ist
    o = [100, 100, 100.3, 100.4, 100.3, 99.9]
    h = [100.2, 100.4, 100.5, 100.6, 100.4, 100.0]
    lo = [99.9, 99.9, 100.2, 100.2, 99.95, 99.8]
    b = _b(o, h, lo, o)
    teile, offen = sb.fuehre_neu(b, -1, 1, 3, 100.0, 102.0)
    assert teile == [{"w": 1.0, "px": 100.0, "j": 4, "grund": "halten"}] and not offen
    # Im Plus zum Gegensignal bleibt alles wie vorher: raus zur Eröffnung
    o3 = [100, 100, 99.6, 99.4, 99.3]
    b3 = _b(o3, [x + 0.2 for x in o3], [x - 0.2 for x in o3], o3)
    teile3, _ = sb.fuehre_neu(b3, -1, 1, 3, 100.0, 102.0)
    assert teile3 == [{"w": 1.0, "px": 99.4, "j": 3, "grund": "gegensignal"}]


def test_merkt_sich_den_normalen_ausstieg():
    o = [100] * 6
    b = _b(o, [100.2] * 6, [99.8] * 6, o)
    log = {}
    with sb.neue_fuehrung(log, "gross_box"):
        ts.fuehre(b, -1, 1, 4, 100.0, 102.0)
    assert ts.fuehre is sb._ORIG
    assert log[("gross_box", 1, -1)]["jf"] == 4


# --------------------------------------------------------------------------------------------------------------------
# Nur fertige Kerzen, frisches Signal

def _basis_bis(ende_ny: str, viertel: int) -> ts.Basis:
    ende = pd.Timestamp(ende_ny, tz=NY).tz_convert("UTC").tz_localize(None)
    idx = pd.date_range(end=ende - pd.Timedelta("15min"), periods=viertel, freq="15min")
    x = np.linspace(100, 101, viertel)
    return ts.basis(pd.DataFrame({"open": x, "high": x + 0.1, "low": x - 0.1, "close": x}, index=idx),
                    pd.Series(0.0, index=idx))


def test_nur_fertige_stunden_und_vier_stunden():
    b = _basis_bis("2026-03-04 12:45", 40)           # letzte Viertelstunde 12:30 bis 12:45 New York
    assert len(sb.fertig(ts.ebene(b, "1h"), b, "1h").c) == len(ts.ebene(b, "1h").c) - 1
    assert len(sb.fertig(ts.ebene(b, "4h"), b, "4h").c) == len(ts.ebene(b, "4h").c) - 1
    b = _basis_bis("2026-03-04 14:00", 40)           # 13:00 bis 14:00 fertig, 4 Std. 10:00 bis 14:00 fertig
    assert len(sb.fertig(ts.ebene(b, "1h"), b, "1h").c) == len(ts.ebene(b, "1h").c)
    assert len(sb.fertig(ts.ebene(b, "4h"), b, "4h").c) == len(ts.ebene(b, "4h").c)
    b = _basis_bis("2026-03-04 17:00", 40)           # Tagesschluss: die 4 Std. ab 14:00 hat nur drei Stunden
    assert len(sb.fertig(ts.ebene(b, "4h"), b, "4h").c) == len(ts.ebene(b, "4h").c)


def test_frisch():
    ende = pd.Timestamp("2026-03-04 15:00")
    assert sb.frisch(ende, ende + pd.Timedelta(minutes=4))
    assert not sb.frisch(ende, ende + pd.Timedelta(minutes=31))
    # Tagesschluss 17:00 New York (22:00 UTC im Winter): nach der Öffnung um 18:00 New York zählt das Signal noch
    schluss = pd.Timestamp("2026-03-04 22:00")
    assert sb.frisch(schluss, pd.Timestamp("2026-03-04 23:03"))
    assert not sb.frisch(schluss, pd.Timestamp("2026-03-04 23:40"))


# --------------------------------------------------------------------------------------------------------------------
# Zusammenlegen und Größen

def _t(j0, d=-1, fehl=-1, jende=None, r=1.0):
    return {"_j0": j0, "richtung": d, "_fehl": fehl, "_jende": jende if jende is not None else j0 + 3,
            "ergebnis_r": r, "einstieg_zeit": str(j0)}


def test_kombi_gleiche_einmal_und_sperre():
    trades = {"gross_klein_3": [_t(1), _t(20, fehl=21, jende=40)], "gross_box_kerze": [_t(1), _t(8), _t(25)],
              "gross_box": [_t(8), _t(30, d=1)]}
    gen, weg, doppelt = sb.kombi(trades)
    assert [(s, t["_j0"]) for s, t in gen] == [("gross_klein_3", 1), ("gross_box_kerze", 8), ("gross_klein_3", 20)]
    assert [(s, t["_j0"]) for s, t in weg] == [("gross_box_kerze", 25)] and doppelt == 2


def test_groessen():
    q = _q()
    sizes, _ = sb.groessen(20.0, q, ts.GEWICHTE)              # 5 € = 5,40 $ bei 20 $ Stop: 0,27 Unzen
    assert sizes == [0.09, 0.09, 0.09]
    sizes, _ = sb.groessen(2.0, q, (1 / 3, 2 / 3))             # 2,70 Unzen, gedeckelt auf 1 Unze
    assert sizes == [0.33, 0.66]
    sizes, warum = sb.groessen(20.0, _q(min_size=1.0, size_step=1.0), ts.GEWICHTE)
    assert sizes is None and "zu grob" in warum


# --------------------------------------------------------------------------------------------------------------------
# Ohne Blick in die Zukunft: Live-Lauf (nur fertige Kerzen plus Kerze "jetzt") findet dieselben Shorts wie die
# Rechnung über alle Kerzen

def _zufall(n=1000, seed=8):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-05 00:00", periods=n, freq="15min")
    c = 4000 + np.cumsum(rng.normal(0, 3, n))
    o = np.r_[4000, c[:-1]]
    h = np.maximum(o, c) + rng.uniform(0, 2, n)
    lo = np.minimum(o, c) - rng.uniform(0, 2, n)
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx), pd.Series(0.3, index=idx)


def test_live_wie_gesamtrechnung():
    bars, sp = _zufall()
    b = ts.basis(bars, sp)
    trades, _ = sb.simuliere(b)
    n_all = len(bars)
    ab = n_all - 40
    gesamt = {}
    for s in sb.SEITEN:
        for t in trades[s]:
            if t["richtung"] < 0 and t["_j0"] >= ab:
                gesamt.setdefault(t["_j0"], s)
    live = {}
    for k in range(ab, n_all):
        t_ph = bars.index[k - 1] + pd.Timedelta("15min")
        b2, s2 = with_now_bar(bars.iloc[:k], sp.iloc[:k], t_ph, bars["open"].iloc[k], bars["open"].iloc[k] + 0.3)
        bb = ts.basis(b2, s2)
        tr, _ = sb.simuliere(bb, len(bb) - 1)
        kand = [s for s in sb.SEITEN for t in tr[s] if t["richtung"] < 0 and t["_j0"] == len(bb) - 1]
        if kand:
            live[k] = kand[0]
    assert gesamt and live == gesamt


# --------------------------------------------------------------------------------------------------------------------
# Der Lauf auf dem Demokonto

class Antwort:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class Konto:
    """Capital.com zum Testen: Hauptkonto und Konto 5, Gold-Positionen auf Konto 5, Kerzen ohne Netz."""

    def __init__(self, bid=4000.0, offer=4000.3, konto5=True):
        self.account_id = HAUPT
        self.bid, self.offer = bid, offer
        self.konto5 = konto5
        self.pos: dict[str, dict] = {}
        self.fremd: list[dict] = []
        self.acts: dict[str, list] = {}
        self.calls: list = []
        self.refs: dict = {}
        self.nr = 0

    def accounts(self):
        out = [{"accountId": HAUPT, "balance": {"balance": 990.0, "available": 900.0}}]
        if self.konto5:
            out.append({"accountId": sb.KONTO, "balance": {"balance": 1000.0, "available": 1000.0}})
        return out

    def switch_account(self, aid):
        self.calls.append(("konto", aid))
        self.account_id = aid

    def market(self, epic):
        if epic == "GOLD":
            return {"snapshot": {"bid": self.bid, "offer": self.offer, "marketStatus": "TRADEABLE",
                                 "decimalPlacesFactor": 2},
                    "instrument": {"currency": "USD", "lotSize": 1, "marginFactor": 5, "marginFactorUnit": "PERCENTAGE"},
                    "dealingRules": {"minDealSize": {"value": 0.01}, "minSizeIncrement": {"value": 0.01},
                                     "minStopOrProfitDistance": {"unit": "POINTS", "value": 0.1}}}
        return {"snapshot": {"bid": 1.08, "offer": 1.08}}

    def positions(self):
        assert self.account_id == sb.KONTO, "Gold-Short-Bot darf nur auf Konto 5 Positionen lesen"
        return [{"market": {"epic": "GOLD"}, "position": p} for p in self.pos.values()] + self.fremd

    def prices(self, epic, resolution, max_bars):
        return []

    def _get(self, path, **params):
        return {"prices": []}

    def _request(self, method, path, json=None):
        assert self.account_id == sb.KONTO
        self.calls.append((method, path, json))
        self.nr += 1
        ref = f"R{self.nr}"
        if method == "POST" and path == "/positions":
            deal = f"D{self.nr}"
            p = {"dealId": deal, "level": self.bid, "size": json["size"], "direction": json["direction"],
                 "stopLevel": round(self.bid + json["stopDistance"], 2)}
            if json.get("profitDistance"):
                p["profitLevel"] = round(self.bid - json["profitDistance"], 2)
            self.pos[deal] = p
            self.refs[ref] = {"dealStatus": "ACCEPTED", "affectedDeals": [{"dealId": deal}], "level": self.bid}
        elif method == "PUT":
            deal = path.rsplit("/", 1)[1]
            self.pos[deal].update({k: v for k, v in json.items()})
            if "profitLevel" not in json:
                self.pos[deal].pop("profitLevel", None)
            self.refs[ref] = {"dealStatus": "ACCEPTED"}
        return Antwort({"dealReference": ref})

    def confirm(self, ref):
        return self.refs.get(ref, {"dealStatus": "ACCEPTED"})

    def close_position(self, deal_id):
        assert self.account_id == sb.KONTO
        self.calls.append(("DELETE", deal_id))
        self.pos.pop(deal_id)
        return {"dealStatus": "ACCEPTED", "level": self.offer}

    def activity(self, deal_id, since, until):
        return self.acts.get(deal_id, [])


def _bars_fuer(now, n=1300, kurs=4000.0):
    ende = pd.Timestamp(now).tz_convert(None).floor("15min") - pd.Timedelta("15min")
    idx = pd.date_range(end=ende, periods=n, freq="15min")
    x = np.full(n, kurs)
    return pd.DataFrame({"open": x, "high": x + 1, "low": x - 1, "close": x}, index=idx), pd.Series(0.3, index=idx)


@pytest.fixture
def welt(monkeypatch):
    """Kerzen und Modell zum Einstellen: modell["trades"] und modell["log"] gibt simuliere zurück; der Einstieg in der
    Kerze "jetzt" heißt j0 = "jetzt"."""
    modell = {"trades": {s: [] for s in sb.SEITEN}, "log": {}, "kerzen": None}

    def kerzen(prices, now, tf):
        return modell["kerzen"]

    def simuliere(b, n=None):
        n = len(b) - 1 if n is None else n
        trades = {s: [dict(t, _j0=n if t["_j0"] == "jetzt" else t["_j0"]) for t in trs]
                  for s, trs in modell["trades"].items()}
        log = {(s, (n if k == "jetzt" else k), d): dict(v, jf=n if v["jf"] == "jetzt" else v["jf"])
               for (s, k, d), v in modell["log"].items()}
        modell["n"] = n
        return trades, log

    from gold.bot import konten, rules
    monkeypatch.setattr(konten, "load", lambda *a: {})
    monkeypatch.setattr(rules, "bars_from_prices", kerzen)
    monkeypatch.setattr(sb, "simuliere", simuliere)
    monkeypatch.setattr(sb, "vorab_ok", lambda: True)
    return modell


def _signal(j0="jetzt", dist=20.0, art="gross_klein_3"):
    return {"_j0": j0, "richtung": -1, "r_usd": dist, "signal": "2026-03-04 15:00:00", "einstieg": 4000.0,
            "einstieg_zeit": "2026-03-04 15:15:00", "_fehl": -1, "_jende": 10 ** 9}


NOW = pd.Timestamp("2026-03-04 15:17", tz="UTC").to_pydatetime()


def test_neuer_short_drei_drittel_auf_konto_5(welt):
    welt["kerzen"] = _bars_fuer(NOW)
    welt["trades"]["gross_klein_3"] = [_signal()]
    welt["trades"]["gross_box_kerze"] = [_signal()]              # gleicher Einstieg: zählt einmal
    k = Konto()
    st, log, fertig, _ = sb.run(k, {}, NOW)
    assert len(st["offen"]) == 1 and st["offen"][0]["seite"] == "gross_klein_3"
    teile = st["offen"][0]["teile"]
    assert [t["size"] for t in teile] == [0.09, 0.09, 0.09]
    assert [t["ziel"] for t in teile] == [3985.0, 3970.0, 3955.0] and {t["stop"] for t in teile} == {4020.0}
    posts = [c for c in k.calls if c[0] == "POST"]
    assert len(posts) == 3 and all(c[2]["direction"] == "SELL" and c[2]["stopDistance"] == 20.0 for c in posts)
    assert k.calls[0] == ("konto", sb.KONTO) and k.account_id == HAUPT       # zurück aufs Hauptkonto
    # Nächster Lauf mit derselben Kerze: kein zweiter Short
    st2, _, _, _ = sb.run(k, st, NOW)
    assert len([c for c in k.calls if c[0] == "POST"]) == 3 and len(st2["offen"]) == 1


def test_gross_box_ein_drittel_mit_ziel_rest_ohne(welt):
    welt["kerzen"] = _bars_fuer(NOW)
    welt["trades"]["gross_box"] = [_signal()]
    k = Konto()
    st, _, _, _ = sb.run(k, {}, NOW)
    teile = st["offen"][0]["teile"]
    assert [t["size"] for t in teile] == [0.09, 0.18] and teile[0]["ziel"] == 3985.0 and teile[1]["ziel"] is None


def test_nie_auf_dem_hauptkonto(welt):
    welt["kerzen"] = _bars_fuer(NOW)
    welt["trades"]["gross_klein_3"] = [_signal()]
    k = Konto(konto5=False)
    st, log, _, blick = sb.run(k, {}, NOW)
    assert not st["offen"] and not [c for c in k.calls if c[0] in ("POST", "konto")]
    assert log[0]["event"] == "kein Konto"


def test_sperren_und_grenzen(welt):
    welt["kerzen"] = _bars_fuer(NOW)
    welt["trades"]["gross_klein_3"] = [_signal()]
    k = Konto()
    # fremde Gold-Position auf dem Konto: nichts Neues
    k.fremd = [{"market": {"epic": "GOLD"}, "position": {"dealId": "FREMD", "level": 3990.0, "size": 1}}]
    st, log, _, _ = sb.run(k, {}, NOW)
    assert not st["offen"] and "fremde Gold-Position auf dem Konto" in log[-1]["gruende"]
    # Pause ab -10 R
    k.fremd = []
    st, log, _, _ = sb.run(k, {"pausiert": {"seit": "x", "grund": "y"}}, NOW)
    assert not st["offen"] and "Pause ab -10 R" in log[-1]["gruende"]
    # Sperre: ein offener Short ist schon ein Fehltrade
    alt = {"offen": [{"id": "a", "seite": "gross_box", "einstieg_zeit": "2026-03-04 10:00:00", "dist": 20.0,
                      "opened_utc": "2026-03-04T10:01:00", "fehl": "2026-03-04T11:00:00", "tp1": False,
                      "zwang": None, "einstand": None, "halten": None, "signal": "s",
                      "teile": [{"dealId": "D0", "size": 0.1, "entry": 4000.0, "stop": 4020.0, "ziel": 4000.0,
                                 "ziel_orig": 3985.0, "ziel_nr": 1, "offen": True}]}]}
    k.pos["D0"] = {"dealId": "D0", "level": 4000.0, "size": 0.1, "stopLevel": 4020.0, "profitLevel": 4000.0}
    k.bid, k.offer = 4008.0, 4008.3
    welt["log"][("gross_box", 0, -1)] = {"jf": 10 ** 9}
    welt["trades"]["gross_box"] = [dict(_signal(j0=0))]
    st, log, _, _ = sb.run(k, alt, NOW)
    assert len(st["offen"]) == 1 and "Sperre: ein offener Short ist schon ein Fehltrade" in log[-1]["gruende"]


def _offener(entry=4000.0, ziel_orig=(3985.0, 3970.0, 3955.0)):
    return {"id": "a", "seite": "gross_klein_3", "einstieg_zeit": str(pd.Timestamp(NOW).tz_localize(None).floor("15min")
                                                                     - pd.Timedelta("3h")),
            "dist": 20.0, "opened_utc": "2026-03-04T12:16:00", "fehl": None, "tp1": False, "zwang": None,
            "einstand": None, "halten": None, "signal": "s",
            "teile": [{"dealId": f"P{i}", "size": 0.09, "entry": entry, "stop": entry + 20, "ziel": z,
                       "ziel_orig": z, "ziel_nr": i + 1, "offen": True} for i, z in enumerate(ziel_orig)]}


def _pos_aus(k, tr):
    for t in tr["teile"]:
        if t["offen"]:
            k.pos[t["dealId"]] = {"dealId": t["dealId"], "level": t["entry"], "size": t["size"],
                                  "stopLevel": t["stop"], "profitLevel": t["ziel"]}


def _modell_offen(welt, k0, jf):
    welt["trades"]["gross_klein_3"] = [dict(_signal(j0=k0))]
    welt["log"][("gross_klein_3", k0, -1)] = {"jf": jf}


def test_erstes_ziel_dann_einstand(welt):
    welt["kerzen"] = (bars, sp) = _bars_fuer(NOW)
    tr = _offener()
    k = Konto(bid=3980.0, offer=3980.3)
    _pos_aus(k, tr)
    k0 = int(np.searchsorted(bars.index.values, np.datetime64(pd.Timestamp(tr["einstieg_zeit"]))))
    _modell_offen(welt, k0, 10 ** 9)
    del k.pos["P0"]                                              # erstes Drittel am Ziel geschlossen
    k.acts["P0"] = [{"dateUTC": "2026-03-04T14:00:00", "source": "TP", "type": "POSITION", "status": "ACCEPTED",
                     "details": {"level": 3985.0, "actions": [{"actionType": "POSITION_CLOSED"}]}}]
    st, log, _, _ = sb.run(k, {"offen": [tr]}, NOW)
    t = st["offen"][0]
    assert t["tp1"] and t["einstand"] and t["teile"][0]["grund"] == "ziel"
    assert k.pos["P1"]["stopLevel"] == 4000.0 and k.pos["P1"]["profitLevel"] == 3970.0
    assert k.pos["P2"]["stopLevel"] == 4000.0 and k.pos["P2"]["profitLevel"] == 3955.0


def test_fehltrade_ziel_auf_einstieg(welt):
    bars, sp = _bars_fuer(NOW)
    welt["kerzen"] = (bars, sp)
    tr = _offener()
    k = Konto(bid=4011.0, offer=4011.3)                         # 0,5 R = 10 $ gegen den Short
    _pos_aus(k, tr)
    k0 = int(np.searchsorted(bars.index.values, np.datetime64(pd.Timestamp(tr["einstieg_zeit"]))))
    _modell_offen(welt, k0, 10 ** 9)
    st, log, _, _ = sb.run(k, {"offen": [tr]}, NOW)
    t = st["offen"][0]
    assert t["fehl"] and all(k.pos[f"P{i}"]["profitLevel"] == 4000.0 for i in range(3))
    assert all(k.pos[f"P{i}"]["stopLevel"] == 4020.0 for i in range(3))
    # Beim Broker am Einstieg geschlossen: Trade fertig mit 0 R, Grund Prüfer
    for i in range(3):
        del k.pos[f"P{i}"]
        k.acts[f"P{i}"] = [{"dateUTC": "2026-03-04T15:20:00", "source": "TP", "type": "POSITION",
                            "status": "ACCEPTED", "details": {"level": 4000.0, "actions": []}}]
    st2, _, fertig, _ = sb.run(k, st, NOW)
    assert not st2["offen"] and fertig[0]["r"] == 0.0 and {x["grund"] for x in fertig[0]["teile"]} == {"pruefer"}


def test_normaler_ausstieg_im_plus_schliesst_im_minus_halten(welt):
    bars, sp = _bars_fuer(NOW)
    welt["kerzen"] = (bars, sp)
    k0 = int(np.searchsorted(bars.index.values, np.datetime64(pd.Timestamp(_offener()["einstieg_zeit"]))))
    # im Plus: alle Teile zum Markt
    tr = _offener()
    k = Konto(bid=3992.0, offer=3992.3)
    _pos_aus(k, tr)
    _modell_offen(welt, k0, "jetzt")
    st, _, fertig, _ = sb.run(k, {"offen": [tr]}, NOW)
    assert not st["offen"] and fertig[0]["r"] == pytest.approx((4000.0 - 3992.3) / 20.0, abs=1e-3)
    # im Minus (aber noch kein Fehltrade): halten, Ziel auf den Einstieg
    tr = _offener()
    k = Konto(bid=4005.0, offer=4005.3)
    _pos_aus(k, tr)
    st, log, _, _ = sb.run(k, {"offen": [tr]}, NOW)
    assert st["offen"][0]["halten"] and all(k.pos[f"P{i}"]["profitLevel"] == 4000.0 for i in range(3))
    # nicht mehr im Modell: gilt als fällig
    welt["trades"]["gross_klein_3"] = []
    tr = _offener()
    k = Konto(bid=3992.0, offer=3992.3)
    _pos_aus(k, tr)
    st, log, fertig, _ = sb.run(k, {"offen": [tr]}, NOW)
    assert not st["offen"] and any(e["event"] == "Ausstieg im Plus" and e["grund"] == "nicht mehr im Modell"
                                   for e in log)


def test_pause_ab_minus_zehn_r(welt):
    welt["kerzen"] = _bars_fuer(NOW)
    tr = _offener()
    k = Konto(bid=4020.0, offer=4020.3)
    k.acts = {f"P{i}": [{"dateUTC": "2026-03-04T15:00:00", "source": "SL", "type": "POSITION", "status": "ACCEPTED",
                         "details": {"level": 4020.0, "actions": []}}] for i in range(3)}
    st, log, fertig, _ = sb.run(k, {"offen": [tr], "summe_r": -9.5, "trades": 20}, NOW)
    assert fertig[0]["r"] == -1.0 and st["summe_r"] == -10.5 and st["pausiert"]


def test_trockenlauf_aendert_nichts(welt):
    welt["kerzen"] = _bars_fuer(NOW)
    welt["trades"]["gross_klein_3"] = [_signal()]
    k = Konto()
    st, log, _, _ = sb.run(k, {}, NOW, send_orders=False)
    assert not [c for c in k.calls if c[0] in ("POST", "PUT", "DELETE")] and log[-1]["event"] == "würde verkaufen"


def test_schreibt_nur_eigene_dateien(tmp_path):
    sb.schreiben({"offen": [], "stand": "x"}, [{"event": "e"}], [{"r": 1.0, "pnl_eur": 4.0}], {}, tmp_path / "gs",
                 tmp_path / "gold-short.json")
    assert sorted(p.name for p in (tmp_path / "gs").iterdir()) == ["log.jsonl", "state.json", "trades.jsonl"]
    c = json.loads((tmp_path / "gold-short.json").read_text(encoding="utf-8"))
    assert c["zusammenfassung"]["trades"] == 1
    with pytest.raises(RuntimeError):
        sb.schreiben({}, [], [], {}, tmp_path / "x", tmp_path / "gold-state.json")
    assert "gold-trades" not in sb.JDIR.name and sb.COCKPIT.name not in sb.GOLD_BOT_DATEIEN


def test_anderer_gold_bot_auf_konto_5(welt, monkeypatch):
    from gold.bot import konten
    welt["kerzen"] = _bars_fuer(NOW)
    welt["trades"]["gross_klein_3"] = [_signal()]
    monkeypatch.setattr(konten, "load", lambda *a: {"zuordnung": {"gold2": sb.KONTO, "r5-ruecksetzer-us30": sb.KONTO}})
    st, log, _, _ = sb.run(Konto(), {}, NOW)
    assert not st["offen"] and any("gold2" in g for g in log[-1]["gruende"])


def test_workflow_testet_vor_dem_lauf():
    from pathlib import Path
    wf = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "demo-bots.yml").read_text(encoding="utf-8")
    assert wf.index("tests/test_gold_short.py") < wf.index("python -m gold.short_bot")
    assert '-ge 6' in wf and wf.count("touch .tests-ok/") == 6
