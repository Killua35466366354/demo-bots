"""Tests für suche/krypto4h_bot.py: Der Bot sieht mit Stundenkerzen dieselben Einstiege, Stops und Ausstiege wie der
Test der YouTube-Runde (Fassung ausbruch4h_krypto) mit 5-Minuten-Kerzen. Er handelt nur auf Account 5, höchstens
einen Trade je Markt, mit Stop beim Broker und ohne Ziel, und steigt nach 4 fertigen 4-Std.-Kerzen aus. Alle Kurse und
Kontonummern hier sind erfunden."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from suche import krypto4h_bot as kb
from suche import krypto4h_gegenprobe as gp
from suche import mitnutzer
from suche import rueckblick as rb
from suche import youtube_runde as yr
from suche import youtube_runde2 as y2
from suche.demo_bots import Quote

# Die Mitnutzer lesen ihre Kontonummer beim Import aus journal/konten.json. Darum hier einmal alle mit der echten Datei
# importieren, bevor die Fixture unten konten.load ersetzt. Sonst hängt der Konto-Test an der Reihenfolge: allein
# gestartet (wie im Workflow) importierte er vix_sprung_bot erst unter der Fixture und fand dessen Konto leer.
mitnutzer.bots()

ROOT = Path(__file__).resolve().parents[1]
HAUPT = "111111113150"
KONTO_V = "111111115555"
MIN = pd.Timedelta(minutes=1)
SYM, EPIC = "BTCUSD", "BTCUSD"
SPREAD = 30.0
EURUSD = 1.1
# Termine der erfundenen Welt: einer genau zum Schluss einer 4-Std.-Kerze (14 Uhr New York, wie die Fed), einer mitten
# in einer Kerze (8:30 Uhr New York, wie CPI und NFP)
TERMINE = np.array(["2025-09-17T18:00", "2025-10-03T12:30"], dtype="datetime64[ns]")
VON, BIS = "2025-08-15", "2025-10-31"


def erfundene_kurse(von="2025-01-01", bis="2025-11-01", seed=7, start=60000.0) -> pd.DataFrame:
    """5-Minuten-Kerzen rund um die Uhr wie bei Krypto. Erst steigt der Kurs, dann fällt er: So gibt es Ausbrüche mit
    dem Tagestrend in beide Richtungen."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(von, bis, freq="5min", inclusive="left")
    n = len(idx)
    drift = np.where(np.arange(n) < n * 0.85, 1.5e-5, -2.5e-5)
    c = start * np.exp(np.cumsum(rng.normal(drift, 0.0011, n)))
    o = np.r_[start, c[:-1]]
    h = np.maximum(o, c) * (1 + rng.uniform(0, 0.0005, n))
    lo = np.minimum(o, c) * (1 - rng.uniform(0, 0.0005, n))
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx).round(1)


def schreibe_npz(df: pd.DataFrame, ordner: Path) -> None:
    """Kursdatei im Format von suche/youtube_runde.baue_krypto."""
    ny = df.index.tz_localize("UTC").tz_convert(rb.NY).tz_localize(None)
    tag = (ny + pd.Timedelta(hours=7)).normalize()
    np.savez(ordner / f"{SYM}.npz", t=df.index.values.astype("datetime64[ns]"), o=df["open"].to_numpy(float),
             h=df["high"].to_numpy(float), l=df["low"].to_numpy(float), c=df["close"].to_numpy(float),
             sp=np.full(len(df), SPREAD), nymin=np.asarray(ny.hour * 60 + ny.minute, dtype=np.int32),
             tag=tag.values.astype("datetime64[D]"), prof=np.full(96, 0.0005))


@pytest.fixture(autouse=True)
def _welt(monkeypatch):
    from gold.bot import konten
    monkeypatch.setattr(kb, "vorab_ok", lambda: True)
    monkeypatch.setattr(kb, "KONTO", KONTO_V)
    monkeypatch.setattr(rb, "termine_utc", lambda: TERMINE)
    monkeypatch.setattr(konten, "load", lambda *a: {})


@pytest.fixture(scope="module")
def w(tmp_path_factory):
    """Die erfundene Welt: 5-Minuten-Kerzen, der Markt des Tests, die Stundenkerzen des Brokers und alles, was der Test
    im Fenster handeln dürfte."""
    ordner = tmp_path_factory.mktemp("krypto4h")
    df = erfundene_kurse()
    schreibe_npz(df, ordner)
    cfg = kb.lade_cfg(pruefen=True)
    m = yr.Markt(SYM, ordner, cfg)
    alle = yr.signale(kb.GRUNDREGEL, m, cfg, TERMINE)
    sig = [s for s in alle if pd.Timestamp(VON) <= pd.Timestamp(m.t[s["i0"]]) < pd.Timestamp(BIS) + pd.Timedelta(days=1)]
    test = {kb.naechste_grenze(pd.Timestamp(m.t[s["i0"] - 1])): s for s in sig}
    return SimpleNamespace(ordner=ordner, df=df, cfg=cfg, m=m, alle=alle, sig=sig, test=test, std=gp.stunden_aus(m),
                           lang=sorted(t for t, s in test.items() if s["d"] > 0),
                           kurz=sorted(t for t, s in test.items() if s["d"] < 0))


def kurs_um(w, t) -> float:
    return float(w.df["open"].loc[pd.Timestamp(t)])


def utc(t):
    return pd.Timestamp(t).tz_localize("UTC").to_pydatetime()


def sig_bei(w, t_g, **kw):
    fenster = w.std[(w.std.index < t_g) & (w.std.index >= t_g - pd.Timedelta(days=kb.TAGE_KERZEN))]
    return kb.signal(SYM, kw.get("stunden", fenster), t_g, kw.get("bid", kurs_um(w, t_g)), w.cfg, TERMINE)


# --------------------------------------------------------------------------------------------------------------------
# Bot und Test sehen dasselbe

def test_bot_sieht_dieselben_einstiege_stops_und_ausstiege_wie_der_test(w, monkeypatch):
    monkeypatch.setattr(kb, "MAERKTE", {SYM: EPIC})
    res = gp.gegenprobe(SYM, w.ordner, w.cfg, TERMINE, VON, BIS)
    assert res["test_einstiege"] == len(w.test) >= 15 and len(w.lang) >= 3 and len(w.kurz) >= 3
    assert res["bot_einstiege"] == res["beide"] == res["richtung_gleich"] == len(w.test)
    assert res["nur_bot"] == {} and res["nur_test"] == {} and res["verpasst_ohne_kurse"] == []
    assert res["stop_abweichung_rel"]["groesste"] < 1e-9 and res["trades_mit_ziel"] == 0
    assert res["trades_ausstieg_nach_zeit"] >= 3 and res["trades_ausstieg_gleich"] == res["trades_ausstieg_nach_zeit"]
    assert res["bot_wartet"] == 0                      # genug Tage Vorlauf, und an jeder Grenze ist die Stunde davor da


def test_fassung_kommt_aus_der_versiegelten_runde(w):
    spec = w.cfg["varianten"][kb.FASSUNG]
    assert list(w.cfg["varianten"]) == [kb.FASSUNG] and spec == {"regel": "ausbruch4h", "maerkte": ["BTCUSD", "ETHUSD"]}
    assert kb.MAERKTE == {"BTCUSD": "BTCUSD", "ETHUSD": "ETHUSD"}
    p = kb.regel(w.cfg)
    assert (p["kanal"], p["stop_kerzen"], p["halte_kerzen"], p["halte_tage_max"], p["frist_min"]) == (20, 10, 4, 14, 60)
    assert (p["stop_min_atr"], p["stop_max_atr"], p["min_kerzen"], p["sperre_utc"]) == (0.5, 4.0, 24, [1255, 1385])
    assert w.cfg["kosten"]["nacht_pro_jahr"]["krypto"] == {"long": 0.2, "short": 0.2}
    assert w.cfg["daten"]["krypto_alle_tage"] == ["BTCUSD", "ETHUSD"] and w.m.klasse == "krypto"


def test_kein_ziel_und_ausstieg_nach_16_stunden(w):
    for s in w.sig:
        assert s["zd"] == 0.0 and s["sd"] > 0
        assert pd.Timestamp(s["t_max"]) - pd.Timestamp(w.m.t[s["i0"]]) == pd.Timedelta(hours=16)


def test_auch_am_wochenende(w):
    assert any(t.weekday() >= 5 for t in w.test)          # Krypto handelt alle sieben Tage, der Test auch
    tage = pd.DatetimeIndex(w.m.tage[w.m.gi])
    assert set(tage.weekday) == set(range(7))


def test_schluessel_wie_im_test(w):
    k = y2._kerzen_4h(w.m)
    eigene = kb.schluessel(w.m.t, w.m.nymin)
    assert (eigene[k["a"]] == k["key"]).all() and len(np.unique(eigene)) == len(k["key"])


@pytest.mark.parametrize("jetzt, beginn, naechste", [
    ("2026-01-07 12:10", "2026-01-07 11:00", "2026-01-07 15:00"),      # Winter: 6 Uhr New York ist 11 Uhr UTC
    ("2026-07-04 14:01", "2026-07-04 14:00", "2026-07-04 18:00"),      # Sommer, Samstag: 10 Uhr New York ist 14 Uhr UTC
    ("2026-11-01 05:30", "2026-11-01 02:00", "2026-11-01 07:00"),      # Uhr zurück: diese Kerze dauert 5 Stunden
    ("2026-03-08 08:10", "2026-03-08 07:00", "2026-03-08 10:00"),      # Uhr vor: diese Kerze dauert 3 Stunden
])
def test_grenzen_der_4h_kerzen_liegen_auf_new_york(jetzt, beginn, naechste):
    assert kb.grenze(pd.Timestamp(jetzt)) == pd.Timestamp(beginn)
    assert kb.naechste_grenze(pd.Timestamp(jetzt)) == pd.Timestamp(naechste)
    idx = pd.date_range(beginn, naechste, freq="5min", inclusive="left")
    assert len(set(kb._block(idx))) == 1 and kb._block([pd.Timestamp(naechste)])[0] != kb._block(idx)[0]


def test_handelstag_wie_in_den_kursdateien(w):
    i = np.arange(0, w.m.n, 997)
    tage = (w.m.tage[w.m.tix[i]] - np.datetime64("1970-01-01")).astype(int)
    assert [kb.handelstag(pd.Timestamp(t)) for t in w.m.t[i]] == list(tage)
    assert kb.handelstag("2026-01-10 21:59") + 1 == kb.handelstag("2026-01-10 22:00")      # auch am Samstag
    assert kb.tagesende(pd.Timestamp("2026-01-07 11:00")) == pd.Timestamp("2026-01-07 22:00")
    assert kb.tagesende(pd.Timestamp("2026-07-04 22:00")) == pd.Timestamp("2026-07-05 21:00")


def test_sperre_ist_die_des_tests(w):
    p = kb.regel(w.cfg)
    assert [kb.gesperrt(t, p, TERMINE) for t in ("2025-09-17 17:44", "2025-09-17 17:45", "2025-09-17 18:15",
                                                 "2025-09-17 18:16")] == [False, True, True, False]
    assert [kb.gesperrt(t, p, TERMINE) for t in ("2025-09-16 20:54", "2025-09-16 20:55", "2025-09-16 23:05",
                                                 "2025-09-16 23:06")] == [False, True, True, False]


def test_signal_haengt_nicht_an_der_zukunft(w):
    t_g = w.lang[0]
    a = sig_bei(w, t_g)
    b = sig_bei(w, t_g, stunden=w.std)                         # mit allen späteren Stundenkerzen
    s = w.test[t_g]
    assert a["ok"] and (a["richtung"], a["dist"]) == (b["richtung"], b["dist"])
    assert a["dist"] == pytest.approx(s["sd"]) and a["schluss"] > a["hoch_davor"] and a["trend"]


def test_signal_wartet_wenn_die_letzte_stunde_fehlt_oder_zu_wenig_tage_da_sind(w, monkeypatch):
    t_g = w.lang[0]
    s = sig_bei(w, t_g, stunden=w.std[w.std.index < t_g - kb.STUNDE])
    assert s["warten"] and not s["ok"] and "Stundenkerze" in s["ergebnis"]
    monkeypatch.setattr(kb, "MIN_TAGE", 500)
    s = sig_bei(w, t_g)
    assert s["warten"] and not s["ok"] and "zu wenig Kerzen" in s["ergebnis"]


def test_gegen_den_tagestrend_gibt_es_keinen_einstieg(w):
    """Ein Ausbruch, der dem Tagestrend widerspricht: Der Test nimmt ihn nicht, der Bot auch nicht."""
    gefunden = None
    for t_g in pd.date_range("2025-08-15 02:00", "2025-10-30 02:00", freq="4h"):
        if t_g in w.test or kb.gesperrt(t_g, kb.regel(w.cfg), TERMINE):
            continue
        s = sig_bei(w, t_g)
        if s["richtung"] and s["trend"] is False:
            gefunden = s
            break
    assert gefunden and not gefunden["ok"] and "gegen den Tagestrend" in gefunden["ergebnis"]


def test_kerzen_seit_zaehlt_alle_sieben_tage(w):
    t_g = pd.Timestamp("2025-10-03 14:00")                     # Freitag 10 Uhr New York (Sommerzeit), danach Wochenende
    n = [kb.kerzen_seit(w.std, t_g, pd.Timestamp(x)) for x in
         ("2025-10-03 17:59", "2025-10-03 18:01", "2025-10-04 06:01", "2025-10-04 12:00", "2025-10-05 06:01")]
    assert n == [0, 1, 4, 5, 10]                               # Krypto hat keine Pause am Wochenende


def _q(**kw):
    base = dict(bid=60000.0, offer=60030.0, tradeable=True, currency="USD", lot=1.0, min_size=0.0001,
                size_step=0.0001, margin_pct=50.0, decimals=1, min_dist=1.0, eur_rate=EURUSD)
    base.update(kw)
    return Quote(**base)


def test_groesse():
    assert kb.groesse(550.0, _q()) == (0.01, "")               # 5 € = 5,50 $ / 550 $ = 0,01 Bitcoin
    assert kb.groesse(600.0, _q())[0] == 0.0091                # abgerundet auf die Schrittweite
    size, warum = kb.groesse(2000.0, _q(min_size=0.01, size_step=0.01))
    assert size is None and "zu grob" in warum
    assert kb.groesse(600.0, _q(eur_rate=None))[0] is None


def test_konto_kommt_nach_dem_namen_aus_konten_json():
    kurz = "…" + KONTO_V[-4:]
    daten = {"konten": [{"id": "…0003", "name": "Account 3"}, {"id": kurz, "name": "Account 5"}],
             "zuordnung": {"r5-ruecksetzer-us30": KONTO_V, "r6-vortag-gbpjpy": "111111110003"}, "haupt": HAUPT,
             "frei": []}
    assert kb.konto_id(daten) == KONTO_V
    assert kb.konto_id({**daten, "zuordnung": {}}) == ""                       # volle ID nirgends: kein Konto
    assert kb.konto_id({**daten, "konten": daten["konten"] + [{"id": "…9999", "name": "Account 5"}]}) == ""
    assert kb.konto_id({}) == ""


def test_echtes_konto_steht_in_konten_json_und_kein_kern_bot_handelt_dort():
    from gold.bot import konten
    from suche import krypto_bollinger_bot, mitnutzer, vix_sprung_bot
    echt = json.loads((ROOT / "journal" / konten.DATEI).read_text(encoding="utf-8"))
    k = kb.konto_id(echt)
    assert k and not k.endswith(kb.HAUPT_ENDUNG) and k.isdigit() and len(k) > 5
    assert k == echt["zuordnung"]["r5-ruecksetzer-us30"] == vix_sprung_bot.konto_id(echt)
    assert k != krypto_bollinger_bot.konto_id(echt)            # Bitcoin und Ether des Bollinger-Bots: Account 3
    kern = ("us500-ruecksetzer", "r5-ruecksetzer-us100", "r7-nasdaq-noise-long", "r6-vortag-eurusd", "r6-vortag-gbpusd",
            "r6-vortag-gbpjpy")
    assert k not in [echt["zuordnung"][b] for b in kern]       # kein Kern-Bot auf diesem Konto
    andere = {b["bot"] for b in mitnutzer.bots() if b["konto"] == k and b["bot"] != kb.BOT_ID and b["neu"]}
    assert andere == {"pine-k5", "vix-sprung"}                 # Gold und Indizes, nie Krypto


# --------------------------------------------------------------------------------------------------------------------
# Der Lauf auf dem Demokonto

class Antwort:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class Konto:
    """Capital.com zum Testen: Hauptkonto und Account 5, Positionen dort, Stundenkerzen aus der erfundenen Welt für
    BTCUSD. Für ETHUSD liefert der Broker keine Kerzen, außer beide=True: dann dieselben wie für BTCUSD."""

    def __init__(self, std, bid=60000.0, konto=True, frei=900.0, beide=False):
        self.account_id = HAUPT
        self.std = std
        self.bid, self.offer = bid, bid + SPREAD
        self.konto, self.frei, self.markt_auf, self.beide = konto, frei, True, beide
        self.pos: dict[str, dict] = {}
        self.fremd: list[dict] = []
        self.acts: dict[str, list] = {}
        self.calls: list = []
        self.abrufe: list = []
        self.refs: dict = {}
        self.nr = 0
        self.order_fehler = False

    def accounts(self):
        out = [{"accountId": HAUPT, "balance": {"balance": 990.0, "available": 900.0}}]
        if self.konto:
            out.append({"accountId": KONTO_V, "balance": {"balance": 1000.0, "available": self.frei}})
        return out

    def switch_account(self, aid):
        self.calls.append(("konto", aid))
        self.account_id = aid

    def market(self, epic):
        if epic in kb.MAERKTE.values():
            return {"snapshot": {"bid": self.bid, "offer": self.offer, "decimalPlacesFactor": 1,
                                 "marketStatus": "TRADEABLE" if self.markt_auf else "CLOSED"},
                    "instrument": {"currency": "USD", "lotSize": 1, "marginFactor": 50, "marginFactorUnit": "PERCENTAGE"},
                    "dealingRules": {"minDealSize": {"value": 0.0001}, "minSizeIncrement": {"value": 0.0001},
                                     "minStopOrProfitDistance": {"unit": "POINTS", "value": 1.0}}}
        assert epic == "EURUSD"
        return {"snapshot": {"bid": EURUSD, "offer": EURUSD}}

    def positions(self):
        assert self.account_id == KONTO_V, "der Bot darf nur auf seinem Konto Positionen lesen"
        return [{"market": {"epic": p["epic"]}, "position": p} for p in self.pos.values()] + self.fremd

    def _get(self, path, **params):
        assert path.startswith("/prices/") and params["resolution"] == "HOUR" and params["max"] == 1000
        von, bis = pd.Timestamp(params["from"]), pd.Timestamp(params["to"])
        assert bis - von <= pd.Timedelta(days=40)
        self.abrufe.append((path, von, bis))
        if path != "/prices/BTCUSD" and not (self.beide and path == "/prices/ETHUSD"):
            return {"prices": []}
        df = self.std[(self.std.index >= von) & (self.std.index <= bis)]
        return {"prices": [{"snapshotTimeUTC": t.strftime("%Y-%m-%dT%H:%M:%S"),
                            **{f"{n}Price": {"bid": float(x), "ask": float(x) + SPREAD}
                               for n, x in zip(("open", "high", "low", "close"), row)}}
                           for t, row in zip(df.index, df[kb.SPALTEN].to_numpy())]}

    def _request(self, method, path, json=None):
        assert self.account_id == KONTO_V
        assert method == "POST" and path == "/positions"
        self.calls.append((method, path, json))
        self.nr += 1
        ref, deal = f"R{self.nr}", f"D{self.nr}"
        d = 1 if json["direction"] == "BUY" else -1
        level = self.offer if d > 0 else self.bid
        self.pos[deal] = {"dealId": deal, "epic": json["epic"], "level": level, "size": json["size"],
                          "direction": json["direction"], "stopLevel": json["stopLevel"]}
        self.refs[ref] = {"dealStatus": "ACCEPTED", "affectedDeals": [{"dealId": deal}], "level": level}
        if self.order_fehler:
            raise RuntimeError("Zeitüberschreitung")
        return Antwort({"dealReference": ref})

    def confirm(self, ref):
        return self.refs.get(ref, {"dealStatus": "ACCEPTED"})

    def close_position(self, deal_id):
        assert self.account_id == KONTO_V
        self.calls.append(("DELETE", deal_id))
        p = self.pos.pop(deal_id)
        return {"dealStatus": "ACCEPTED", "level": self.bid if p.get("direction") == "BUY" else self.offer}

    def activity(self, deal_id, since, until):
        assert until - since <= pd.Timedelta(days=1)
        return self.acts.get(deal_id, [])

    def posts(self):
        return [c for c in self.calls if c[0] == "POST"]


def btc(st):
    return st["maerkte"][SYM]


def test_kauf_wie_im_test_mit_stop_vom_bid_und_ohne_ziel(w):
    t_g = w.lang[0]
    s = w.test[t_g]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, fertig, blick = kb.run(k, {}, utc(t_g + MIN))
    tr = btc(st)["trade"]
    stop = round(k.bid - s["sd"], 1)
    assert tr["richtung"] == 1 and tr["dist"] == pytest.approx(s["sd"], abs=1e-5) and tr["grenze"] == str(t_g)
    assert tr["entry"] == k.offer and tr["stop"] == stop and "ziel" not in tr and tr["spaet_min"] == 1.0
    assert k.posts() == [("POST", "/positions", {"epic": EPIC, "direction": "BUY", "size": kb.groesse(s["sd"], _q())[0],
                                                  "guaranteedStop": False, "stopLevel": stop})]
    assert k.calls[0] == ("konto", KONTO_V) and k.account_id == HAUPT              # zurück aufs Hauptkonto
    assert btc(st)["letzte_grenze"] == str(t_g) and [e["event"] for e in log] == ["Kauf eröffnet"]
    assert tr["halte_kerzen"] == 4 and tr["bis_utc"] == str(t_g + pd.Timedelta(days=14)) and tr["satz_nacht"] == 0.2
    assert tr["margin_eur"] == pytest.approx(tr["size"] * k.bid * 0.5 / EURUSD, abs=0.01)
    # Ether wartet, weil der Broker dort keine Kerzen liefert
    assert "Stundenkerze" in blick["maerkte"]["ETHUSD"]["wartet"]
    # der nächste Lauf in derselben Kerze öffnet nichts Zweites
    st2, _, _, _ = kb.run(k, st, utc(t_g + 16 * MIN))
    assert len(k.posts()) == 1 and btc(st2)["trade"]["dealId"] == tr["dealId"]


def test_verkauf_wie_im_test(w):
    t_g = w.kurz[0]
    s = w.test[t_g]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, _, _ = kb.run(k, {}, utc(t_g + MIN))
    tr = btc(st)["trade"]
    assert tr["richtung"] == -1 and tr["entry"] == k.bid and tr["stop"] == round(k.bid + s["sd"], 1)
    assert k.posts()[0][2]["direction"] == "SELL" and tr["satz_nacht"] == 0.2


def test_einstieg_am_wochenende(w):
    t_g = next(t for t in w.test if t.weekday() >= 5)
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, _, _, _ = kb.run(k, {}, utc(t_g + MIN))
    assert len(k.posts()) == 1 and btc(st)["trade"]["grenze"] == str(t_g)


def test_ausstieg_nach_vier_fertigen_4h_kerzen_mit_gebuehr_je_nacht(w):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, _, _, _ = kb.run(k, {}, utc(t_g + MIN))
    s = w.test[t_g]
    tr = btc(st)["trade"]
    for now in gp.laeufe_ab(t_g, 2000):
        k.bid, k.offer = kurs_um(w, now.floor("5min")), kurs_um(w, now.floor("5min")) + SPREAD
        st, log, fertig, _ = kb.run(k, st, utc(now))
        if fertig:
            break
    assert fertig and fertig[0]["grund"] == "zeit" and ("DELETE", tr["dealId"]) in k.calls
    t_max = pd.Timestamp(s["t_max"])
    assert t_max <= now < t_max + pd.Timedelta(minutes=16)                       # erster Lauf danach
    r = fertig[0]
    naechte = kb.handelstag(now) - kb.handelstag(t_g)
    assert r["naechte"] == naechte and r["gebuehr_r"] == pytest.approx(0.2 * naechte / 365 * tr["entry"] / tr["dist"],
                                                                       abs=1e-3)
    assert btc(st)["trade"] is None and btc(st)["letzter_schluss"] == r["closed_utc"]
    assert st["trades"] == 1 and st["summe_r"] == r["r"]


def test_an_der_kerze_des_ausstiegs_kein_neuer_einstieg(w):
    """Endet ein Trade nach Zeit genau mit dem Schluss einer Kerze, nimmt der Test an dieser Kerze kein neues Signal
    (rueckblick.echte_trades: i0 <= frei_ab). Der Bot auch nicht."""
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, _, _, _ = kb.run(k, {}, utc(t_g + MIN))
    t_max = pd.Timestamp(w.test[t_g]["t_max"])
    st, log, fertig, _ = kb.run(k, st, utc(t_max + MIN))
    assert fertig and btc(st)["letzte_pruefung"]["ergebnis"].startswith("der letzte Trade endete erst")
    assert len(k.posts()) == 1


def test_stop_beim_broker_wird_gebucht(w):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, _, _, _ = kb.run(k, {}, utc(t_g + MIN))
    tr = btc(st)["trade"]
    k.pos.pop(tr["dealId"])
    k.acts[tr["dealId"]] = [{"dateUTC": (t_g + 30 * MIN).strftime("%Y-%m-%dT%H:%M:%S"), "source": "SL",
                             "type": "POSITION", "status": "ACCEPTED", "details": {"level": tr["stop"], "actions": []}}]
    st, log, fertig, _ = kb.run(k, st, utc(t_g + 46 * MIN))
    r = fertig[0]
    assert r["grund"] == "stop" and r["exit"] == tr["stop"] and r["markt"] == SYM and "exit_geschaetzt" not in r
    assert r["r_roh"] == pytest.approx((tr["stop"] - tr["entry"]) / tr["dist"], abs=1e-3)
    assert r["pnl_eur"] == round(tr["size"] * (tr["stop"] - tr["entry"]) / EURUSD, 2)
    # ein Stop mitten in der Kerze sperrt die nächste Kerze nicht (wie im Test)
    assert pd.Timestamp(btc(st)["letzter_schluss"]) < kb.naechste_grenze(t_g)


def test_schluss_nicht_lesbar_wird_nach_einer_stunde_als_stop_geschaetzt(w):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, _, _, _ = kb.run(k, {}, utc(t_g + MIN))
    tr = btc(st)["trade"]
    k.pos.pop(tr["dealId"])
    st, log, fertig, _ = kb.run(k, st, utc(t_g + 16 * MIN))
    assert not fertig and log[0]["event"].startswith("Position beim Broker zu") and "Schlusskurs" in kb.status(st)
    k.bid, k.offer = tr["entry"] + 500, tr["entry"] + 530                    # auch auf der Gewinnseite: es gibt kein Ziel
    st, log, fertig, _ = kb.run(k, st, utc(t_g + 76 * MIN))
    assert fertig[0]["grund"] == "stop" and fertig[0]["exit"] == tr["stop"] and fertig[0]["exit_geschaetzt"]


def test_sperren(w, monkeypatch):
    t_g = w.lang[0]
    jetzt = utc(t_g + MIN)
    k = Konto(w.std, bid=kurs_um(w, t_g))
    k.fremd = [{"market": {"epic": EPIC}, "position": {"dealId": "FREMD", "level": 59990.0, "size": 1}},
               {"market": {"epic": "GOLD"}, "position": {"dealId": "PINE", "level": 3550.0, "size": 0.2}}]
    st, log, _, _ = kb.run(k, {}, jetzt)
    assert btc(st)["trade"] is None and not k.posts() and "fremde Position auf BTCUSD im Konto" in log[-1]["gruende"]
    assert btc(st)["fremd"] == ["FREMD"] and not [c for c in k.calls if c[0] == "DELETE"]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    k.fremd = [{"market": {"epic": "GOLD"}, "position": {"dealId": "PINE", "level": 3550.0, "size": 0.2}},
               {"market": {"epic": "US30"}, "position": {"dealId": "DOW", "level": 44000.0, "size": 0.1}}]
    st, _, _, _ = kb.run(k, {}, jetzt)                                       # Gold und Dow der Mitnutzer stören nicht
    assert len(k.posts()) == 1
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, _, _ = kb.run(k, {"pausiert": {"seit": "x", "grund": "y"}}, jetzt)
    assert not k.posts() and "Pause ab -25 R" in log[-1]["gruende"]
    k = Konto(w.std, bid=kurs_um(w, t_g), frei=20.0)
    st, log, _, _ = kb.run(k, {}, jetzt)
    assert not k.posts() and any("des freien Gelds" in g for g in log[-1]["gruende"])
    monkeypatch.setattr(kb, "vorab_ok", lambda: False)
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, _, _ = kb.run(k, {}, jetzt)
    assert not k.posts() and any("nicht festgelegt" in g for g in log[-1]["gruende"])


def test_margin_der_ersten_order_zaehlt_im_selben_lauf_mit(w):
    t_g = w.lang[0]
    s = w.test[t_g]
    size = kb.groesse(s["sd"], _q())[0]
    marge = size * kurs_um(w, t_g) * 0.5 / EURUSD
    k = Konto(w.std, bid=kurs_um(w, t_g), frei=3.0 * marge, beide=True)     # Ether sieht dieselben Kerzen
    st, log, _, _ = kb.run(k, {}, utc(t_g + MIN))
    assert [c[2]["epic"] for c in k.posts()] == ["BTCUSD"]
    ether = [e for e in log if e["markt"] == "ETHUSD"][-1]
    assert ether["event"] == "Einstieg ausgelassen" and any("des freien Gelds" in g for g in ether["gruende"])
    k = Konto(w.std, bid=kurs_um(w, t_g), frei=10.0 * marge, beide=True)
    kb.run(k, {}, utc(t_g + MIN))
    assert [c[2]["epic"] for c in k.posts()] == ["BTCUSD", "ETHUSD"]


def test_ohne_lesbare_regeldatei_kein_signal_aber_der_offene_trade_endet(w, monkeypatch):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, _, _, _ = kb.run(k, {}, utc(t_g + MIN))
    monkeypatch.setattr(kb, "lade_cfg", lambda pruefen=False: None)
    t_max = pd.Timestamp(w.test[t_g]["t_max"])
    st, log, fertig, blick = kb.run(k, st, utc(t_max + MIN))
    assert fertig and fertig[0]["grund"] == "zeit"
    k2 = Konto(w.std, bid=kurs_um(w, w.lang[1]))
    st2, _, _, blick2 = kb.run(k2, {}, utc(w.lang[1] + MIN))
    assert not k2.posts() and "Siegel" in blick2["maerkte"][SYM]["wartet"] and btc(st2).get("letzte_grenze") is None


def test_nie_auf_dem_hauptkonto_und_nie_ohne_konto(w, monkeypatch):
    k = Konto(w.std, konto=False)
    st, log, _, blick = kb.run(k, {}, utc(w.lang[0] + MIN))
    assert not [c for c in k.calls if c[0] in ("POST", "konto")] and "nicht gefunden" in blick["status"]
    monkeypatch.setattr(kb, "KONTO", "")
    k = Konto(w.std)
    st, log, _, blick = kb.run(k, {}, utc(w.lang[0] + MIN))
    assert not k.calls and "journal/konten.json" in blick["status"]
    monkeypatch.setattr(kb, "KONTO", "111111113150")                        # endet wie das Hauptkonto
    st, log, _, blick = kb.run(Konto(w.std), {}, utc(w.lang[0] + MIN))
    assert log[0]["event"] == "kein Konto"


def test_frist_markt_zu_und_trockenlauf(w):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, _, _, _ = kb.run(k, {}, utc(t_g + 26 * MIN))                          # frischer Bot, Frist vorbei
    assert not k.posts() and "Start des Bots" in btc(st)["letzte_pruefung"]["ergebnis"]
    st, _, _, _ = kb.run(k, {"maerkte": {SYM: {"trade": None, "letzte_grenze": "2020-01-01 00:00:00"}}},
                         utc(t_g + 26 * MIN))
    assert btc(st)["letzte_pruefung"]["ergebnis"].startswith("verfallen")
    k = Konto(w.std, bid=kurs_um(w, t_g))
    k.markt_auf = False
    st, _, _, blick = kb.run(k, {}, utc(t_g + MIN))
    assert not k.posts() and blick["maerkte"][SYM]["wartet"] == "Markt zu" and btc(st).get("letzte_grenze") is None
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, _, _ = kb.run(k, {}, utc(t_g + MIN), send_orders=False)
    assert not k.posts() and log[-1]["event"] == "würde kaufen" and btc(st).get("letzte_grenze") is None


def test_order_ohne_bestaetigung_wird_uebernommen(w):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    k.order_fehler = True
    st, log, _, _ = kb.run(k, {}, utc(t_g + MIN))
    assert len(k.posts()) == 1 and btc(st)["trade"]["dealId"] == "D1"        # sofort in den Positionen gefunden
    st2, _, _, _ = kb.run(k, st, utc(t_g + 16 * MIN))
    assert len(k.posts()) == 1


def test_handelspause_und_termin_sperren_ohne_abruf(w):
    abend = pd.Timestamp("2025-09-16 22:00")                                  # 18 Uhr New York, in der Sperre
    k = Konto(w.std)
    st, _, _, _ = kb.run(k, {}, utc(abend + MIN))
    assert not k.abrufe and not k.posts() and "Sperre" in btc(st)["letzte_pruefung"]["ergebnis"]
    fed = pd.Timestamp("2025-09-17 18:00")                                    # 14 Uhr New York, Termin der Fed
    k = Konto(w.std)
    st, _, _, _ = kb.run(k, {}, utc(fed + MIN))
    assert not k.abrufe and "Termin" in btc(st)["letzte_pruefung"]["ergebnis"] and fed not in w.test


def test_schreiben(tmp_path, w):
    t_g = w.lang[0]
    k = Konto(w.std, bid=kurs_um(w, t_g))
    st, log, fertig, blick = kb.run(k, {}, utc(t_g + MIN))
    j, c = tmp_path / "krypto-ausbruch4h", tmp_path / "krypto-ausbruch4h.json"
    assert kb.schreiben(st, log, fertig, blick, j, c)
    assert not kb.schreiben(st, [], [], blick, j, c)                          # nichts Neues, nichts geschrieben
    karte = json.loads(c.read_text(encoding="utf-8"))
    assert karte["bot"] == "krypto-ausbruch4h" and karte["konto"] == "Account 5" and KONTO_V not in c.read_text()
    assert karte["offen"][0]["epic"] == EPIC and karte["zusammenfassung"]["urteil"].startswith("läuft (0 von 40")
    assert "kein Ziel" in karte["status"] and karte["maerkte"] == {"BTCUSD": "Bitcoin", "ETHUSD": "Ether"}
    for fremd in ("konten.json", "krypto-bollinger.json", "welt-ausbruch4h.json"):
        with pytest.raises(RuntimeError):
            kb.schreiben(st, log, fertig, blick, j, tmp_path / fremd)


def test_bewertung():
    tr = [{"r": 1.0, "markt": "BTCUSD", "pnl_eur": 5}] * 25 + [{"r": -1.0, "markt": "ETHUSD", "pnl_eur": -5}] * 15
    b = kb.bewertung(tr)
    assert b["trades"] == 40 and b["pf_r"] == pytest.approx(25 / 15, abs=1e-3) and b["urteil"].startswith("bestanden")
    assert b["je_markt"]["ETHUSD"] == {"trades": 15, "summe_r": -15.0}
    b = kb.bewertung([{"r": -1.0}] * 15)
    assert b["urteil"].startswith("Zwischencheck")


def test_mitnutzer_kennt_den_bot():
    from suche import mitnutzer
    b = {x["bot"]: x for x in mitnutzer.bots()}["krypto-ausbruch4h"]
    assert b["konto_name"] == "Account 5" and b["neu"] and b["konto"] == KONTO_V
    assert b["quelle"] == "suche/krypto4h_bot.py"


def test_regeln_sind_versiegelt(monkeypatch):
    monkeypatch.undo()
    assert kb.vorab_ok(), "suche/VORAB_krypto_ausbruch4h_bot.yaml braucht seine Prüfsumme im Protokoll"
    vorab = kb.VORAB.read_text(encoding="utf-8")
    assert kb.KONTO not in vorab and "Account 5" in vorab and "kein Kern-Bot" in vorab
    for wort in (kb.FASSUNG, "-25 R", "NICHT bestanden", "2,35", "0,91", "nach_trades: 40", "11:53 UTC", "12:26 UTC",
                 "Schatten-Labor"):
        assert wort in vorab, wort
    import yaml
    r = yaml.safe_load(vorab)["krypto_ausbruch4h_bot"]
    assert r["bot"] == kb.BOT_ID
    assert r["groesse"]["risiko_eur"] == kb.RISIKO_EUR and r["groesse"]["margin_anteil"] == kb.MARGE_ANTEIL
    assert r["groesse"]["max_risiko_faktor"] == kb.MAX_RISIKO_FAKTOR
    assert r["ausfuehrung"]["frist_min"] == kb.FRIST.total_seconds() / 60
    assert r["ausfuehrung"]["vorlauf_tage"] == kb.TAGE_KERZEN and r["ausfuehrung"]["min_tage"] == kb.MIN_TAGE
    assert r["urteil"]["nach_trades"] == kb.URTEIL_NACH and r["urteil"]["pause_r"] == kb.PAUSE_R
    z = r["gegenprobe_zahlen"]
    assert set(z) == set(kb.MAERKTE) and all(z[m]["stop_abweichung"] == 0 for m in z)


def test_ablauf_im_workflow():
    wf = (ROOT / ".github" / "workflows" / "demo-bots.yml").read_text(encoding="utf-8")
    assert "python -m pytest -q tests/test_krypto4h_bot.py" in wf and "python -m suche.krypto4h_bot" in wf
    assert "touch .tests-ok/krypto4h" in wf and "python -m suche.krypto4h_bot --dry-run" in wf
    assert '[ "$n" -ge 15 ]' in wf and "von 15 Testgruppen" in wf and wf.count("touch .tests-ok/") == 15
