"""Tests für suche/welt4h_bot.py: Der Bot sieht mit Stundenkerzen dieselben Einstiege, Stops, Ziele und Ausstiege wie
der Test der Runde "Kirons Notizen" (Fassung ausbruch4h_welt_ziel_1r) mit 5-Minuten-Kerzen. Er handelt nur auf
Account 7, höchstens einen Trade je Markt, mit Stop und Ziel beim Broker, und steigt nach 4 fertigen 4-Std.-Kerzen
aus. Alle Kurse und Kontonummern hier sind erfunden."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from suche import notizen_runde as nr
from suche import rueckblick as rb
from suche import welt4h_bot as wb
from suche import welt4h_gegenprobe as gp
from suche import youtube_runde2 as y2
from suche.demo_bots import Quote

ROOT = Path(__file__).resolve().parents[1]
HAUPT = "111111113150"
KONTO7 = "111111117777"
MIN = pd.Timedelta(minutes=1)
SYM, EPIC = "GRXEUR", "DE40"
# Termine der erfundenen Welt: einer genau zum Schluss einer 4-Std.-Kerze (10 Uhr New York), einer mitten in einer Kerze
TERMINE = np.array(["2025-09-17T14:00", "2025-10-03T12:30"], dtype="datetime64[ns]")
VON, BIS = "2025-08-15", "2025-10-31"


def handelszeiten(von: str, bis: str) -> pd.DatetimeIndex:
    """5-Minuten-Kerzen wie beim DAX auf HistData: Sonntag 23 Uhr bis Freitag 21 Uhr UTC, jeden Abend 21 bis 23 Uhr zu."""
    idx = pd.date_range(von, bis, freq="5min", inclusive="left")
    zu = (idx.weekday == 5) | ((idx.weekday == 4) & (idx.hour >= 21)) | ((idx.weekday == 6) & (idx.hour < 23)) \
        | ((idx.hour >= 21) & (idx.hour < 23))
    return idx[~zu]


def erfundene_kurse(von="2025-01-02", bis="2025-11-01", seed=11, start=20000.0) -> pd.DataFrame:
    """Erst steigt der Kurs, dann fällt er: So gibt es Ausbrüche mit dem Tagestrend in beide Richtungen."""
    rng = np.random.default_rng(seed)
    idx = handelszeiten(von, bis)
    n = len(idx)
    drift = np.where(np.arange(n) < n * 0.85, 2.0e-5, -3.0e-5)
    c = start * np.exp(np.cumsum(rng.normal(drift, 0.0011, n)))
    o = np.r_[start, c[:-1]]
    h = np.maximum(o, c) * (1 + rng.uniform(0, 0.0006, n))
    lo = np.minimum(o, c) * (1 - rng.uniform(0, 0.0006, n))
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx).round(1)


def schreibe_npz(df: pd.DataFrame, ordner: Path) -> None:
    """Kursdatei im Format von suche/rueckblick_daten.py."""
    ny = df.index.tz_localize("UTC").tz_convert(rb.NY).tz_localize(None)
    tag = (ny + pd.Timedelta(hours=7)).normalize()
    np.savez(ordner / f"{SYM}.npz", t=df.index.values.astype("datetime64[ns]"), o=df["open"].to_numpy(float),
             h=df["high"].to_numpy(float), l=df["low"].to_numpy(float), c=df["close"].to_numpy(float),
             sp=np.full(len(df), 1.2), nymin=np.asarray(ny.hour * 60 + ny.minute, dtype=np.int32),
             tag=tag.values.astype("datetime64[D]"), prof=np.full(96, 1.2))


@pytest.fixture(autouse=True)
def _welt(monkeypatch):
    from gold.bot import konten
    monkeypatch.setattr(wb, "MIN_TAGESKERZEN", 60)             # die erfundene Welt ist nur 10 Monate lang
    monkeypatch.setattr(wb, "vorab_ok", lambda: True)
    monkeypatch.setattr(wb, "KONTO", KONTO7)
    monkeypatch.setattr(rb, "termine_utc", lambda: TERMINE)
    monkeypatch.setattr(konten, "load", lambda *a: {})


@pytest.fixture(scope="module")
def w(tmp_path_factory):
    """Die erfundene Welt: 5-Minuten-Kerzen, der Markt des Tests, die Stundenkerzen des Brokers und alles, was der Test
    im Fenster handeln dürfte."""
    ordner = tmp_path_factory.mktemp("welt")
    df = erfundene_kurse()
    schreibe_npz(df, ordner)
    cfg = wb.lade_cfg(pruefen=True)
    m = nr.Markt(SYM, ordner, cfg)
    sig = [s for s in nr.signale(wb.FASSUNG, m, cfg, TERMINE)
           if pd.Timestamp(VON) <= pd.Timestamp(m.t[s["i0"]]) < pd.Timestamp(BIS) + pd.Timedelta(days=1)]
    test = {wb.naechste_grenze(pd.Timestamp(m.t[s["i0"] - 1])): s for s in sig}
    return SimpleNamespace(ordner=ordner, df=df, cfg=cfg, m=m, sig=sig, test=test, std=gp.stunden_aus(m),
                           lang=sorted(t for t, s in test.items() if s["d"] > 0 and pd.Timestamp(m.t[s["i0"]]) == t),
                           kurz=sorted(t for t, s in test.items() if s["d"] < 0 and pd.Timestamp(m.t[s["i0"]]) == t))


def kurs_um(w, t) -> float:
    return float(w.df["open"].loc[pd.Timestamp(t)])


def utc(t):
    return pd.Timestamp(t).tz_localize("UTC").to_pydatetime()


def sig_bei(w, t_g, **kw):
    fenster = w.std[(w.std.index < t_g) & (w.std.index >= t_g - pd.Timedelta(days=wb.TAGE_KERZEN))]
    return wb.signal(SYM, kw.get("stunden", fenster), t_g, kw.get("bid", kurs_um(w, t_g)), w.cfg, TERMINE)


# --------------------------------------------------------------------------------------------------------------------
# Bot und Test sehen dasselbe

def test_bot_sieht_dieselben_einstiege_stops_ziele_und_ausstiege_wie_der_test(w, monkeypatch):
    monkeypatch.setattr(wb, "MAERKTE", {SYM: EPIC})
    res = gp.gegenprobe(SYM, w.ordner, w.cfg, TERMINE, VON, BIS)
    assert res["test_einstiege"] == len(w.test) >= 15 and w.lang and w.kurz
    assert res["bot_einstiege"] == res["beide"] == res["richtung_gleich"] == len(w.test) - len(res["verpasst_markt_zu"])
    assert res["nur_bot"] == {} and res["nur_test"] == {}
    assert res["stop_abweichung_rel"]["groesste"] < 1e-9 and res["ziel_abweichung_rel"]["groesste"] < 1e-9
    assert res["trades_ausstieg_nach_zeit"] >= 3 and res["trades_ausstieg_gleich"] == res["trades_ausstieg_nach_zeit"]
    assert res["bot_wartet"] == 0                      # genug Tage Vorlauf, und an jeder Grenze ist die Stunde davor da


def test_fassung_kommt_aus_der_versiegelten_runde(w):
    spec = w.cfg["varianten"][wb.FASSUNG]
    assert list(w.cfg["varianten"]) == [wb.FASSUNG] and spec["ziel_r_neu"] == 1.0 and spec["basis"] == "ausbruch4h"
    assert wb.MAERKTE == {"GRXEUR": "DE40", "UKXGBP": "UK100", "JPXJPY": "J225"}
    p = wb.regel(w.cfg)
    assert (p["kanal"], p["stop_kerzen"], p["halte_kerzen"], p["halte_tage_max"], p["frist_min"]) == (20, 10, 4, 14, 60)
    assert w.cfg["quell_regeln"]["rueckblick"]["ausbruch4h"] == p


def test_ziel_ist_ein_r(w):
    for s in w.sig:
        assert s["zd"] == pytest.approx(s["sd"]) and s["sd"] > 0


def test_schluessel_wie_im_test(w):
    k = y2._kerzen_4h(w.m)
    eigene = wb.schluessel(w.m.t, w.m.nymin)
    assert (eigene[k["a"]] == k["key"]).all() and len(np.unique(eigene)) == len(k["key"])


@pytest.mark.parametrize("jetzt, beginn, naechste", [
    ("2026-01-07 12:10", "2026-01-07 11:00", "2026-01-07 15:00"),      # Winter: 6 Uhr New York ist 11 Uhr UTC
    ("2026-07-01 14:01", "2026-07-01 14:00", "2026-07-01 18:00"),      # Sommer: 10 Uhr New York ist 14 Uhr UTC
    ("2026-11-01 05:30", "2026-11-01 02:00", "2026-11-01 07:00"),      # Uhr zurück: diese Kerze dauert 5 Stunden
    ("2026-03-08 08:10", "2026-03-08 07:00", "2026-03-08 10:00"),      # Uhr vor: diese Kerze dauert 3 Stunden
])
def test_grenzen_der_4h_kerzen_liegen_auf_new_york(jetzt, beginn, naechste):
    assert wb.grenze(pd.Timestamp(jetzt)) == pd.Timestamp(beginn)
    assert wb.naechste_grenze(pd.Timestamp(jetzt)) == pd.Timestamp(naechste)
    idx = pd.date_range(beginn, naechste, freq="5min", inclusive="left")
    assert len(set(wb._block(idx))) == 1 and wb._block([pd.Timestamp(naechste)])[0] != wb._block(idx)[0]


def test_handelstag_wie_in_den_kursdateien(w):
    i = np.arange(0, w.m.n, 997)
    tage = (w.m.tage[w.m.tix[i]] - np.datetime64("1970-01-01")).astype(int)
    assert [wb.handelstag(pd.Timestamp(t)) for t in w.m.t[i]] == list(tage)
    assert wb.handelstag("2026-01-09 21:59") + 1 == wb.handelstag("2026-01-09 22:00")      # 17:00 New York im Winter
    assert wb.tagesende(pd.Timestamp("2026-01-07 11:00")) == pd.Timestamp("2026-01-07 22:00")
    assert wb.tagesende(pd.Timestamp("2026-07-01 22:00")) == pd.Timestamp("2026-07-02 21:00")


def test_sperre_ist_die_des_tests(w):
    p = wb.regel(w.cfg)
    assert [wb.gesperrt(t, p, TERMINE) for t in ("2025-09-17 13:44", "2025-09-17 13:45", "2025-09-17 14:15",
                                                 "2025-09-17 14:16")] == [False, True, True, False]
    assert [wb.gesperrt(t, p, TERMINE) for t in ("2025-09-16 20:54", "2025-09-16 20:55", "2025-09-16 23:05",
                                                 "2025-09-16 23:06")] == [False, True, True, False]


def test_signal_haengt_nicht_an_der_zukunft(w):
    t_g = w.lang[0]
    a = sig_bei(w, t_g)
    b = sig_bei(w, t_g, stunden=w.std)                         # mit allen späteren Stundenkerzen
    s = w.test[t_g]
    assert a["ok"] and (a["richtung"], a["dist"], a["ziel_abstand"]) == (b["richtung"], b["dist"], b["ziel_abstand"])
    assert a["dist"] == pytest.approx(s["sd"]) and a["schluss"] > a["hoch_davor"] and a["trend"]


def test_signal_wartet_wenn_die_letzte_stunde_fehlt_oder_zu_wenig_tage_da_sind(w, monkeypatch):
    t_g = w.lang[0]
    s = sig_bei(w, t_g, stunden=w.std[w.std.index < t_g - wb.STUNDE])
    assert s["warten"] and not s["ok"] and "Stundenkerze" in s["ergebnis"]
    monkeypatch.setattr(wb, "MIN_TAGESKERZEN", 500)
    s = sig_bei(w, t_g)
    assert s["warten"] and not s["ok"] and "zu wenig Kerzen" in s["ergebnis"]


def test_gegen_den_tagestrend_gibt_es_keinen_einstieg(w):
    """Ein Ausbruch, der dem Tagestrend widerspricht: Der Test nimmt ihn nicht, der Bot auch nicht."""
    gefunden = None
    for t_g in pd.date_range("2025-08-18 06:00", "2025-10-30 06:00", freq="4h"):
        if t_g in w.test or t_g - wb.STUNDE not in w.std.index or t_g not in w.df.index:
            continue
        s = sig_bei(w, t_g)
        if s["richtung"] and s["trend"] is False:
            gefunden = s
            break
    assert gefunden and not gefunden["ok"] and "gegen den Tagestrend" in gefunden["ergebnis"]


def test_kerzen_seit_zaehlt_nur_kerzen_mit_kursen(w):
    t_g = pd.Timestamp("2025-10-03 14:00")                     # Freitag 10 Uhr New York (Sommerzeit), danach Wochenende
    n = [wb.kerzen_seit(w.std, t_g, pd.Timestamp(x)) for x in
         ("2025-10-03 17:59", "2025-10-03 18:01", "2025-10-04 12:00", "2025-10-05 23:01", "2025-10-06 02:01")]
    assert n == [0, 1, 2, 2, 3]                                # 14-18, 18-22 (Kurse bis 21 Uhr), Sonntag 22-02


def _q(**kw):
    base = dict(bid=20000.0, offer=20001.2, tradeable=True, currency="EUR", lot=1.0, min_size=0.001, size_step=0.001,
                margin_pct=5.0, decimals=1, min_dist=1.0, eur_rate=1.0)
    base.update(kw)
    return Quote(**base)


def test_groesse():
    assert wb.groesse(250.0, _q()) == (0.02, "")               # 5 € / 250 Punkte = 0,02 je Punkt
    assert wb.groesse(250.0, _q(currency="JPY", eur_rate=180.0, min_size=0.1, size_step=0.1))[0] == 3.6
    size, warum = wb.groesse(2000.0, _q(min_size=0.1, size_step=0.1))
    assert size is None and "zu grob" in warum
    assert wb.groesse(250.0, _q(eur_rate=None))[0] is None


def test_konto_kommt_nach_dem_namen_aus_konten_json():
    daten = {"konten": [{"id": "111111110001", "name": "Account 6"}, {"id": KONTO7, "name": "Account 7"}]}
    assert wb.konto_id(daten) == KONTO7
    assert wb.konto_id({"konten": daten["konten"] + [{"id": "111111110002", "name": "Account 7"}]}) == ""
    assert wb.konto_id({}) == ""


def test_konto_mit_gekuerzter_id_wird_ueber_die_volle_id_der_zuordnung_gefunden():
    # So steht es wirklich in journal/konten.json: unter "konten" nur die letzten vier Stellen, die volle ID unter
    # "zuordnung", "frei" oder "haupt". Mit der gekürzten ID fand der Bot sein Konto beim Broker nicht (20.11.2026).
    kurz = "…" + KONTO7[-4:]
    daten = {"konten": [{"id": "…0001", "name": "Account 6"}, {"id": kurz, "name": "Account 7"}],
             "zuordnung": {"anderer-bot": KONTO7, "noch-einer": "111111110001"}, "haupt": HAUPT, "frei": []}
    assert wb.konto_id(daten) == KONTO7
    assert wb.konto_id({**daten, "zuordnung": {}, "frei": [KONTO7]}) == KONTO7
    assert wb.konto_id({**daten, "zuordnung": {}}) == ""                       # volle ID nirgends: kein Konto
    doppelt = {**daten, "frei": ["999999990000" + KONTO7[-4:]]}                   # zwei volle IDs mit derselben Endung
    assert wb.konto_id(doppelt) == ""


def test_echtes_konto_steht_in_konten_json_und_ist_nie_das_hauptkonto():
    from gold.bot import konten
    echt = konten.DATEI and (ROOT / "journal" / konten.DATEI)
    import json
    k = wb.konto_id(json.loads(echt.read_text(encoding="utf-8")))
    assert k and not k.endswith(wb.HAUPT_ENDUNG)
    assert k.isdigit() and len(k) > 5, "volle Konto-ID, nicht die gekürzte aus der Liste der Konten"


# --------------------------------------------------------------------------------------------------------------------
# Der Lauf auf dem Demokonto

class Antwort:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class Konto:
    """Capital.com zum Testen: Hauptkonto und Account 7, Positionen auf Account 7, Stundenkerzen aus der erfundenen
    Welt für DE40. Für UK100 und J225 liefert der Broker keine Kerzen. Die erfundene Welt schwankt stärker als der DAX,
    darum ist die kleinste Größe hier 0,001."""

    def __init__(self, std, bid=20000.0, konto7=True, frei=900.0):
        self.account_id = HAUPT
        self.std = std
        self.bid, self.offer = bid, bid + 1.2
        self.konto7, self.frei, self.markt_auf = konto7, frei, True
        self.pos: dict[str, dict] = {}
        self.fremd: list[dict] = []
        self.acts: dict[str, list] = {}
        self.calls: list = []
        self.abrufe: list = []
        self.refs: dict = {}
        self.nr = 0
        self.order_fehler = False
        self.fehlt: set = set()

    def accounts(self):
        out = [{"accountId": HAUPT, "balance": {"balance": 990.0, "available": 900.0}}]
        if self.konto7:
            out.append({"accountId": KONTO7, "balance": {"balance": 1000.0, "available": self.frei}})
        return out

    def switch_account(self, aid):
        self.calls.append(("konto", aid))
        self.account_id = aid

    def market(self, epic):
        if epic in wb.MAERKTE.values():
            cur = {"DE40": "EUR", "UK100": "GBP", "J225": "JPY"}[epic]
            return {"snapshot": {"bid": self.bid, "offer": self.offer, "decimalPlacesFactor": 1,
                                 "marketStatus": "TRADEABLE" if self.markt_auf else "CLOSED"},
                    "instrument": {"currency": cur, "lotSize": 1, "marginFactor": 5, "marginFactorUnit": "PERCENTAGE"},
                    "dealingRules": {"minDealSize": {"value": 0.001}, "minSizeIncrement": {"value": 0.001},
                                     "minStopOrProfitDistance": {"unit": "POINTS", "value": 1.0}}}
        return {"snapshot": {"bid": 0.87 if epic == "EURGBP" else 180.0, "offer": 0.87 if epic == "EURGBP" else 180.0}}

    def positions(self):
        assert self.account_id == KONTO7, "der Bot darf nur auf Account 7 Positionen lesen"
        return [{"market": {"epic": p["epic"]}, "position": p} for p in self.pos.values()] + self.fremd

    def _get(self, path, **params):
        assert path.startswith("/prices/") and params["resolution"] == "HOUR" and params["max"] == 1000
        von, bis = pd.Timestamp(params["from"]), pd.Timestamp(params["to"])
        assert bis - von <= pd.Timedelta(days=40)
        self.abrufe.append((path, von, bis))
        if path != "/prices/DE40":
            return {"prices": []}
        df = self.std[(self.std.index >= von) & (self.std.index <= bis) & ~self.std.index.isin(list(self.fehlt))]
        return {"prices": [{"snapshotTimeUTC": t.strftime("%Y-%m-%dT%H:%M:%S"),
                            **{f"{n}Price": {"bid": float(x), "ask": float(x) + 1.2}
                               for n, x in zip(("open", "high", "low", "close"), row)}}
                           for t, row in zip(df.index, df[wb.SPALTEN].to_numpy())]}

    def _request(self, method, path, json=None):
        assert self.account_id == KONTO7
        assert method == "POST" and path == "/positions"
        self.calls.append((method, path, json))
        self.nr += 1
        ref, deal = f"R{self.nr}", f"D{self.nr}"
        d = 1 if json["direction"] == "BUY" else -1
        level = self.offer if d > 0 else self.bid
        self.pos[deal] = {"dealId": deal, "epic": json["epic"], "level": level, "size": json["size"],
                          "direction": json["direction"], "stopLevel": json["stopLevel"], "profitLevel": json["profitLevel"]}
        self.refs[ref] = {"dealStatus": "ACCEPTED", "affectedDeals": [{"dealId": deal}], "level": level}
        if self.order_fehler:
            raise RuntimeError("Zeitüberschreitung")
        return Antwort({"dealReference": ref})

    def confirm(self, ref):
        return self.refs.get(ref, {"dealStatus": "ACCEPTED"})

    def close_position(self, deal_id):
        assert self.account_id == KONTO7
        self.calls.append(("DELETE", deal_id))
        p = self.pos.pop(deal_id)
        return {"dealStatus": "ACCEPTED", "level": self.bid if p.get("direction") == "BUY" else self.offer}

    def activity(self, deal_id, since, until):
        assert until - since <= pd.Timedelta(days=1)
        return self.acts.get(deal_id, [])

    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]


def de40(st):
    return st["maerkte"][SYM]


def test_kauf_wie_im_test_mit_stop_und_ziel_vom_bid(w):
    t_g = w.lang[0]
    s = w.test[t_g]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, fertig, blick = wb.run(k, {}, utc(t_g + MIN))
    tr = de40(st)["trade"]
    stop, ziel = round(k.bid - s["sd"], 1), round(k.bid + s["zd"], 1)
    assert tr["richtung"] == 1 and tr["dist"] == pytest.approx(s["sd"], abs=1e-5) and tr["grenze"] == str(t_g)
    assert tr["entry"] == k.offer and (tr["stop"], tr["ziel"]) == (stop, ziel) and tr["spaet_min"] == 1.0
    assert k.posts() == [("POST", "/positions", {"epic": EPIC, "direction": "BUY", "size": wb.groesse(s["sd"], _q())[0],
                                                  "guaranteedStop": False, "stopLevel": stop, "profitLevel": ziel})]
    assert k.calls[0] == ("konto", KONTO7) and k.account_id == HAUPT              # zurück aufs Hauptkonto
    assert de40(st)["letzte_grenze"] == str(t_g) and [e["event"] for e in log] == ["Kauf eröffnet"]
    assert tr["halte_kerzen"] == 4 and tr["bis_utc"] == str(t_g + pd.Timedelta(days=14)) and tr["satz_nacht"] == 0.065
    # die anderen Märkte warten, weil der Broker dort keine Kerzen liefert
    assert all("Stundenkerze" in blick["maerkte"][x]["wartet"] for x in ("UKXGBP", "JPXJPY"))
    # der nächste Lauf in derselben Kerze öffnet nichts Zweites
    st2, _, _, _ = wb.run(k, st, utc(t_g + 16 * MIN))
    assert len(k.posts()) == 1 and de40(st2)["trade"]["dealId"] == tr["dealId"]


def test_verkauf_wie_im_test(w):
    t_g = w.kurz[0]
    s = w.test[t_g]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, _, _ = wb.run(k, {}, utc(t_g + MIN))
    tr = de40(st)["trade"]
    assert tr["richtung"] == -1 and tr["entry"] == k.bid
    assert (tr["stop"], tr["ziel"]) == (round(k.bid + s["sd"], 1), round(k.bid - s["zd"], 1))
    assert k.posts()[0][2]["direction"] == "SELL" and tr["satz_nacht"] == 0.02


def test_ausstieg_nach_vier_fertigen_4h_kerzen(w):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, _, _, _ = wb.run(k, {}, utc(t_g + MIN))
    s = w.test[t_g]
    deal = de40(st)["trade"]["dealId"]
    aus = gp.laeufe_ab(t_g, 2000)
    for now in aus:
        st, log, fertig, _ = wb.run(k, st, utc(now))
        if fertig:
            break
    assert fertig and fertig[0]["grund"] == "zeit" and ("DELETE", deal) in k.calls
    t_max = pd.Timestamp(s["t_max"])
    assert t_max <= now < t_max + pd.Timedelta(minutes=16) or now >= t_max                 # erster Lauf danach
    assert de40(st)["trade"] is None and de40(st)["letzter_schluss"] == fertig[0]["closed_utc"]
    assert st["trades"] == 1 and st["summe_r"] == fertig[0]["r"]


def test_stop_und_ziel_beim_broker_werden_gebucht(w):
    t_g = w.lang[0]
    for quelle, grund in (("SL", "stop"), ("TP", "ziel")):
        k = Konto(w.std, bid=kurs_um(w, t_g))
        st, _, _, _ = wb.run(k, {}, utc(t_g + MIN))
        tr = de40(st)["trade"]
        level = tr["stop"] if quelle == "SL" else tr["ziel"]
        k.pos.pop(tr["dealId"])
        k.acts[tr["dealId"]] = [{"dateUTC": (t_g + 30 * MIN).strftime("%Y-%m-%dT%H:%M:%S"), "source": quelle,
                                 "type": "POSITION", "status": "ACCEPTED", "details": {"level": level, "actions": []}}]
        st, log, fertig, _ = wb.run(k, st, utc(t_g + 46 * MIN))
        r = fertig[0]
        assert r["grund"] == grund and r["exit"] == level and r["markt"] == SYM and "exit_geschaetzt" not in r
        assert r["r_roh"] == pytest.approx((level - tr["entry"]) / tr["dist"], abs=1e-3) and r["naechte"] == 0
        assert r["pnl_eur"] == round(tr["size"] * (level - tr["entry"]), 2)


def test_schluss_nicht_lesbar_wird_nach_einer_stunde_geschaetzt(w):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, _, _, _ = wb.run(k, {}, utc(t_g + MIN))
    tr = de40(st)["trade"]
    k.pos.pop(tr["dealId"])
    st, log, fertig, _ = wb.run(k, st, utc(t_g + 16 * MIN))
    assert not fertig and log[0]["event"].startswith("Position beim Broker zu") and "Schlusskurs" in wb.status(st)
    k.bid, k.offer = tr["ziel"] + 5, tr["ziel"] + 6.2                         # Kurs jetzt über dem Ziel
    st, log, fertig, _ = wb.run(k, st, utc(t_g + 76 * MIN))
    assert fertig[0]["grund"] == "ziel" and fertig[0]["exit"] == tr["ziel"] and fertig[0]["exit_geschaetzt"]


def test_sperren(w, monkeypatch):
    t_g = w.lang[0]
    jetzt = utc(t_g + MIN)
    k = Konto(w.std, bid=kurs_um(w, t_g))
    k.fremd = [{"market": {"epic": EPIC}, "position": {"dealId": "FREMD", "level": 19990.0, "size": 1}},
               {"market": {"epic": "USDJPY"}, "position": {"dealId": "NOISE", "level": 150.0, "size": 1}}]
    st, log, _, _ = wb.run(k, {}, jetzt)
    assert de40(st)["trade"] is None and not k.posts() and "fremde Position auf DE40 im Konto" in log[-1]["gruende"]
    assert de40(st)["fremd"] == ["FREMD"] and not [c for c in k.calls if c[0] == "DELETE"]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    k.fremd = [{"market": {"epic": "USDJPY"}, "position": {"dealId": "NOISE", "level": 150.0, "size": 1}}]
    st, _, _, _ = wb.run(k, {}, jetzt)                                       # USD/JPY des Noise-Bots stört nicht
    assert len(k.posts()) == 1
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, _, _ = wb.run(k, {"pausiert": {"seit": "x", "grund": "y"}}, jetzt)
    assert not k.posts() and "Pause ab -25 R" in log[-1]["gruende"]
    k = Konto(w.std, bid=kurs_um(w, t_g), frei=20.0)
    st, log, _, _ = wb.run(k, {}, jetzt)
    assert not k.posts() and any("des freien Gelds" in g for g in log[-1]["gruende"])
    monkeypatch.setattr(wb, "vorab_ok", lambda: False)
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, _, _ = wb.run(k, {}, jetzt)
    assert not k.posts() and any("nicht festgelegt" in g for g in log[-1]["gruende"])


def test_nie_auf_dem_hauptkonto_und_nie_ohne_konto(w, monkeypatch):
    k = Konto(w.std, konto7=False)
    st, log, _, blick = wb.run(k, {}, utc(w.lang[0] + MIN))
    assert not [c for c in k.calls if c[0] in ("POST", "konto")] and "nicht gefunden" in blick["status"]
    monkeypatch.setattr(wb, "KONTO", "")
    k = Konto(w.std)
    st, log, _, blick = wb.run(k, {}, utc(w.lang[0] + MIN))
    assert not k.calls and "journal/konten.json" in blick["status"]
    monkeypatch.setattr(wb, "KONTO", "111111113150")                        # endet wie das Hauptkonto
    st, log, _, blick = wb.run(Konto(w.std), {}, utc(w.lang[0] + MIN))
    assert log[0]["event"] == "kein Konto"


def test_frist_markt_zu_und_trockenlauf(w):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, _, _, _ = wb.run(k, {}, utc(t_g + 26 * MIN))                          # frischer Bot, Frist vorbei
    assert not k.posts() and "Start des Bots" in de40(st)["letzte_pruefung"]["ergebnis"]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    k.markt_auf = False
    st, _, _, blick = wb.run(k, {}, utc(t_g + MIN))
    assert not k.posts() and blick["maerkte"][SYM]["wartet"] == "Markt zu" and de40(st).get("letzte_grenze") is None
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, _, _ = wb.run(k, {}, utc(t_g + MIN), send_orders=False)
    assert not k.posts() and log[-1]["event"] == "würde kaufen" and de40(st).get("letzte_grenze") is None


def test_order_ohne_bestaetigung_wird_uebernommen(w):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    k.order_fehler = True
    st, log, _, _ = wb.run(k, {}, utc(t_g + MIN))
    assert len(k.posts()) == 1 and de40(st)["trade"]["dealId"] == "D1"        # sofort in den Positionen gefunden
    st2, _, _, _ = wb.run(k, st, utc(t_g + 16 * MIN))
    assert len(k.posts()) == 1


def test_handelspause_sperrt_ohne_abruf(w):
    abend = pd.Timestamp("2025-09-16 22:00")                                  # 18 Uhr New York, in der Sperre
    k = Konto(w.std)
    st, _, _, _ = wb.run(k, {}, utc(abend + MIN))
    assert not k.abrufe and not k.posts() and "Sperre" in de40(st)["letzte_pruefung"]["ergebnis"]


def test_schreiben(tmp_path, w):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, fertig, blick = wb.run(k, {}, utc(t_g + MIN))
    j, c = tmp_path / "welt-ausbruch4h", tmp_path / "welt-ausbruch4h.json"
    assert wb.schreiben(st, log, fertig, blick, j, c)
    assert not wb.schreiben(st, [], [], blick, j, c)                          # nichts Neues, nichts geschrieben
    import json
    karte = json.loads(c.read_text(encoding="utf-8"))
    assert karte["bot"] == "welt-ausbruch4h" and karte["konto"] == "Account 7" and KONTO7 not in c.read_text()
    assert karte["offen"][0]["epic"] == EPIC and karte["zusammenfassung"]["urteil"].startswith("läuft (0 von 40")
    with pytest.raises(RuntimeError):
        wb.schreiben(st, log, fertig, blick, j, tmp_path / "konten.json")


def test_bewertung():
    tr = [{"r": 1.0, "markt": "GRXEUR", "pnl_eur": 5}] * 25 + [{"r": -1.0, "markt": "UKXGBP", "pnl_eur": -5}] * 15
    b = wb.bewertung(tr)
    assert b["trades"] == 40 and b["pf_r"] == pytest.approx(25 / 15, abs=1e-3) and b["urteil"].startswith("bestanden")
    assert b["je_markt"]["UKXGBP"] == {"trades": 15, "summe_r": -15.0}
    b = wb.bewertung([{"r": -1.0}] * 15)
    assert b["urteil"].startswith("Zwischencheck")


def test_mitnutzer_kennt_den_bot():
    from suche import mitnutzer
    b = {x["bot"]: x for x in mitnutzer.bots()}["welt-ausbruch4h"]
    assert b["konto_name"] == "Account 7" and b["neu"] and b["konto"] == KONTO7


def test_regeln_sind_versiegelt(monkeypatch):
    monkeypatch.undo()
    assert wb.vorab_ok(), "suche/VORAB_welt_ausbruch4h_bot.yaml braucht seine Prüfsumme im Protokoll"
    vorab = wb.VORAB.read_text(encoding="utf-8")
    assert wb.KONTO not in vorab and "Account 7" in vorab
    for wort in (wb.FASSUNG, "-25 R", "NICHT bestanden", "2,26", "nach_trades: 40", "12:23 UTC", "notizen_vorwaerts"):
        assert wort in vorab, wort
    import yaml
    r = yaml.safe_load(vorab)["welt_ausbruch4h_bot"]
    assert r["bot"] == wb.BOT_ID
    assert r["groesse"]["risiko_eur"] == wb.RISIKO_EUR and r["groesse"]["margin_anteil"] == wb.MARGE_ANTEIL
    assert r["groesse"]["max_risiko_faktor"] == wb.MAX_RISIKO_FAKTOR
    assert r["ausfuehrung"]["frist_min"] == wb.FRIST.total_seconds() / 60
    assert r["ausfuehrung"]["vorlauf_tage"] == wb.TAGE_KERZEN and r["ausfuehrung"]["min_handelstage"] == wb.MIN_TAGESKERZEN
    assert r["urteil"]["nach_trades"] == wb.URTEIL_NACH and r["urteil"]["pause_r"] == wb.PAUSE_R
    z = r["gegenprobe_zahlen"]
    assert set(z) == set(wb.MAERKTE) and all(z[m]["stop_abweichung"] == 0 for m in z)


def test_ablauf_im_workflow():
    wf = (ROOT / ".github" / "workflows" / "demo-bots.yml").read_text(encoding="utf-8")
    assert "python -m pytest -q tests/test_welt4h_bot.py" in wf and "python -m suche.welt4h_bot" in wf
    assert "touch .tests-ok/welt_ausbruch4h" in wf and "python -m suche.welt4h_bot --dry-run" in wf
