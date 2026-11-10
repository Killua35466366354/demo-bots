"""Tests für suche/scalper_bot.py (Top 3 Scalper mit Open-Filter auf Account 1) und suche/scalping_opens.py.

- Regeln versiegelt, die 3 Bots sind genau die 3 gewählten aus suche/ergebnis_scalping_opens.json, je ein Markt.
- Der Bot entscheidet Tag für Tag wie der Test: Richtung, Stop und Filter (Eröffnungskerze und letzte halbe Stunde),
  auf Zufallskerzen gegen suche/scalping2.py und suche/scalping_opens.py gerechnet.
- Opens aus Stundenkerzen gleich den Opens aus suche/opens.py (Handelstag bis 17:00 New York).
- Ein Lauf: Order mit Stop und Ziel beim Broker, 5 € je R, Zeit-Ausstieg, Schluss durch den Broker, nie zwei Positionen.
"""
import json

import numpy as np
import pandas as pd
import pytest

from suche import opens as op
from suche import scalper_bot as sb
from suche import scalping as sc
from suche import scalping2 as s2
from suche import scalping_opens as so

US100, DE40, J225 = sb.BOTS


def _fuenf(von="2025-09-01", bis="2026-02-28", saat=3, kurs=20000.0, schritt=8.0):
    """5-Min.-Bid-Kerzen Mo-Fr rund um die Uhr (UTC), Zufallsweg mit kleinen Lücken."""
    idx = pd.date_range(von, bis, freq="5min")
    idx = idx[idx.weekday < 5]
    rng = np.random.default_rng(saat)
    c = kurs + np.cumsum(rng.normal(0, schritt, len(idx)))
    o = np.r_[kurs, c[:-1]] + rng.normal(0, schritt / 10, len(idx))
    h = np.maximum(o, c) + rng.uniform(0, schritt, len(idx))
    lo = np.minimum(o, c) - rng.uniform(0, schritt, len(idx))
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx)


def test_regeln_versiegelt_und_bots_wie_ergebnis():
    assert sb.vorab_ok()
    so.check_vorab()
    erg = json.loads((sb.ROOT / "suche" / "ergebnis_scalping_opens.json").read_text(encoding="utf-8"))
    assert erg["vorab_sha256"] == sb.sha256_vorab()
    gew = [(g["familie"], g["variante"], g["markt"], g["kerzen"], g["filter"]) for g in erg["gewaehlt"]]
    assert gew == [(b.familie, b.variante, b.sym, b.kerzen, b.filter) for b in sb.BOTS]
    assert len({b.epic for b in sb.BOTS}) == 3 and len({b.sym for b in sb.BOTS}) == 3
    assert sb.KONTO.endswith("5310") and not sb.KONTO.endswith("3150")


def test_auswahl_regel():
    def v(markt, pf, n, f="woche"):
        return {"markt": markt, "filter": f, "zeitraum": {"pf": pf, "trades": n}}
    res = [v("A", 3.0, 99), v("B", 2.0, 100), v("B", 1.9, 300, "jahr"), v("C", 1.5, 120), v("C", 1.5, 150, "jahr"),
           v("D", 1.4, 500), v("E", 1.3, 200)]
    w = so.waehle(res)
    assert [(r["markt"], r["zeitraum"]["trades"]) for r in w] == [("B", 100), ("C", 150), ("D", 500)]


@pytest.mark.parametrize("art", ["jahr", "quartal", "monat", "woche"])
def test_opens_aus_stundenkerzen_wie_opens_py(art):
    df = _fuenf("2025-12-15", "2026-01-20", saat=5)
    p = op.perioden(df)
    std = df.resample("60min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    for t in pd.date_range("2025-12-22", "2026-01-19", freq="D"):
        t = t + pd.Timedelta(hours=15)
        if t not in p.index:
            continue
        tag = sb.handelstag(t)
        assert sb.open_aus_kerzen(std, tag, art) == pytest.approx(p.loc[t, f"o_{art}"]), (art, t)


def _wie_test(bot, df, trades, maske):
    """Für jeden Tag mit Einstiegszeit: entscheidet der Bot 3 Min. danach wie der Test?"""
    p = op.perioden(df)
    erwartet = {t["t"]: t for t, k in zip(trades, maske) if k}
    alle = {t["t"]: t for t in trades}
    n_trade = n_filter = 0
    for tag in pd.date_range("2025-10-01", "2026-02-19", freq="D"):
        jetzt = tag + pd.Timedelta(hours=12)
        z = sb.zeiten(bot, jetzt)
        if z is None:
            continue
        jetzt = z["ein"] + pd.Timedelta(minutes=3)
        z = sb.zeiten(bot, jetzt)
        b5 = df[df.index + pd.Timedelta(minutes=5) <= jetzt]
        b_tf = s2.zu_15(b5) if bot.kerzen == 15 else b5
        b_tf = b_tf[b_tf.index + pd.Timedelta(minutes=bot.kerzen) <= jetzt]
        ref = b5.index[b5.index <= z["ein"] - pd.Timedelta(minutes=5)][-1]
        opens = {a: float(p.loc[ref, f"o_{a}"]) for a in sb.OPEN_SPALTEN}
        o = float(df.loc[z["ein"], "open"])
        sig = sb.entscheide(bot, z, b5, b_tf, opens, o, o + 0.5, ein_open=o)
        if z["ein"] in erwartet:
            t = erwartet[z["ein"]]
            assert sig["d"] == t["d"], (tag, sig, t)
            if t.get("r_dist"):
                assert sig["dist"] == pytest.approx(t["r_dist"]), (tag, sig, t)
            n_trade += 1
        else:
            assert sig["d"] == 0, (tag, sig)
            if z["ein"] in alle:
                assert sig["warum"].startswith("Filter"), (tag, sig)
                n_filter += 1
    return n_trade, n_filter


def test_eroeffnungskerze_entscheidet_wie_der_test():
    df = _fuenf(saat=11)
    m = sc.Markt("NSXUSD", s2.zu_15(df), 0.5, minuten=15)
    tr = s2.eroeffnung(m, "NSXUSD", "folgen_10r", 1.0, "2025-10-01", "2026-02-20")
    maske = so.mit_opens(op.perioden(df), tr)["alle"]
    n_trade, n_filter = _wie_test(US100, df, tr, maske)
    assert n_trade >= 15 and n_filter >= 15


def test_dax_eroeffnungskerze_entscheidet_wie_der_test():
    df = _fuenf(saat=12)
    m = sc.Markt("GRXEUR", s2.zu_15(df), 0.5, minuten=15)
    tr = s2.eroeffnung(m, "GRXEUR", "folgen_10r", 1.0, "2025-10-01", "2026-02-20")
    maske = so.mit_opens(op.perioden(df), tr)["alle"]
    n_trade, n_filter = _wie_test(DE40, df, tr, maske)
    assert n_trade >= 15 and n_filter >= 15


def test_letzte_halbe_stunde_entscheidet_wie_der_test():
    df = _fuenf(saat=13, kurs=50000.0, schritt=15.0)
    m = sc.Markt("JPXJPY", df, 0.5, minuten=5)
    tr = s2.halbe_stunde(m, "JPXJPY", "gegen", 1.0, "2025-10-01", "2026-02-20")
    maske = so.mit_opens(op.perioden(df), tr)["woche"]
    n_trade, n_filter = _wie_test(J225, df, tr, maske)
    assert n_trade >= 20 and n_filter >= 20


def test_zeiten():
    z = sb.zeiten(US100, pd.Timestamp("2026-11-10 15:00"))
    assert (z["erste"], z["ein"], z["aus"]) == (pd.Timestamp("2026-11-10 14:30"), pd.Timestamp("2026-11-10 14:45"),
                                                 pd.Timestamp("2026-11-10 21:00"))
    z = sb.zeiten(DE40, pd.Timestamp("2026-07-01 07:30"))
    assert (z["ein"], z["aus"]) == (pd.Timestamp("2026-07-01 07:15"), pd.Timestamp("2026-07-01 15:30"))
    z = sb.zeiten(J225, pd.Timestamp("2026-11-10 06:03"))
    assert (z["ein"], z["aus"]) == (pd.Timestamp("2026-11-10 06:00"), pd.Timestamp("2026-11-10 06:30"))
    assert sb.zeiten(US100, pd.Timestamp("2026-11-14 15:00")) is None


class Q:
    def __init__(self, bid=20000.0, offer=20001.0, lot=1.0, min_size=0.01, step=0.01, eur=1.16, margin=5.0):
        self.bid, self.offer, self.lot, self.min_size, self.size_step = bid, offer, lot, min_size, step
        self.eur_rate, self.margin_pct, self.tradeable, self.decimals, self.min_dist = eur, margin, True, 1, 0.0
        self.currency = "USD"


def test_groesse_fuenf_euro_je_r():
    assert sb.groesse(US100, 50.0, Q()) == pytest.approx(0.11)          # 5 * 1,16 / 50 = 0,116 -> 0,11
    assert sb.groesse(US100, 5000.0, Q()) == pytest.approx(0.01)        # darunter: kleinste Größe
    assert sb.groesse(J225, None, Q(min_size=1.0, step=1.0)) == 1.0     # ohne Stop: kleinste Größe


# ---------- ein Lauf mit Capital.com zum Testen ----------

def _raw(df):
    return [{"snapshotTimeUTC": t.strftime("%Y-%m-%dT%H:%M:%S"),
             "openPrice": {"bid": r.open, "ask": r.open + 1}, "highPrice": {"bid": r.high, "ask": r.high + 1},
             "lowPrice": {"bid": r.low, "ask": r.low + 1}, "closePrice": {"bid": r.close, "ask": r.close + 1}}
            for t, r in df.iterrows()]


class Broker:
    def __init__(self, df):
        self.df = df
        self.account_id = "111111113150"
        self.pos: dict[str, dict] = {}
        self.posts: list[dict] = []
        self.closed: list[str] = []
        self.now = None
        self.n = 0

    def accounts(self):
        return [{"accountId": "111111113150", "balance": {"available": 900}},
                {"accountId": sb.KONTO, "balance": {"available": 1000}}]

    def switch_account(self, aid):
        self.account_id = aid

    def _get(self, path, **kw):
        if path == "/session":
            return {"accountId": self.account_id}
        if path.startswith("/prices/"):
            von, bis = pd.Timestamp(kw["from"]), pd.Timestamp(kw["to"])
            if self.now is not None and bis > self.now:        # wie Capital.com: kein Ende in der Zukunft
                raise RuntimeError(f"GET {path} -> 400: {{\"errorCode\":\"error.invalid.daterange\"}}")
            std = self.df.resample("60min").agg({"open": "first", "high": "max", "low": "min",
                                                 "close": "last"}).dropna()
            return {"prices": _raw(std[(std.index >= von) & (std.index <= bis)])}
        raise AssertionError(path)

    def prices(self, epic, res, n):
        d = self.df[self.df.index <= self.now]
        if res == "MINUTE_15":
            d = s2.zu_15(d)
        return _raw(d.tail(n))

    def market(self, epic):
        if epic.startswith("EUR"):
            return {"snapshot": {"bid": 1.1599, "offer": 1.1601}}
        k = float(self.df[self.df.index <= self.now]["close"].iloc[-1])
        return {"snapshot": {"bid": k, "offer": k + 1, "marketStatus": "TRADEABLE", "decimalPlacesFactor": 1},
                "instrument": {"currency": "USD" if epic != "DE40" else "EUR", "lotSize": 1, "marginFactor": 5},
                "dealingRules": {"minDealSize": {"value": 0.01}, "minSizeIncrement": {"value": 0.01}}}

    def positions(self):
        assert self.account_id == sb.KONTO
        return list(self.pos.values())

    def _request(self, method, path, json=None):
        assert self.account_id == sb.KONTO and method == "POST" and path == "/positions"
        self.posts.append(json)
        self.n += 1
        deal = f"D{self.n}"
        self.pos[deal] = {"market": {"epic": json["epic"]}, "position": {"dealId": deal, "size": json["size"]}}

        class R:
            def json(self_inner):
                return {"dealReference": deal}
        return R()

    def confirm(self, ref):
        return {"dealStatus": "ACCEPTED", "level": 20001.0 if ref == "D1" else 20000.0,
                "affectedDeals": [{"dealId": ref}]}

    def close_position(self, deal):
        self.closed.append(deal)
        self.pos.pop(deal)
        return {"dealStatus": "ACCEPTED", "level": 20100.0}

    def activity(self, *a, **k):
        return []


def _markt_us100(richtung=1):
    """Kerzen, an denen US100 am 10.11.2026 Long (bzw. Short) nimmt: alle Opens darunter (darüber)."""
    idx = pd.date_range("2025-12-29", "2026-11-10 21:30", freq="5min")
    idx = idx[idx.weekday < 5]
    x = np.linspace(19000, 20000, len(idx)) if richtung > 0 else np.linspace(21000, 20000, len(idx))
    df = pd.DataFrame({"open": x, "high": x + 2, "low": x - 2, "close": x}, index=idx)
    erste = pd.Timestamp("2026-11-10 14:30")
    for k in range(3):                        # erste 15-Min.-Kerze grün (bzw. rot), Spanne 40 Punkte
        t = erste + pd.Timedelta(minutes=5 * k)
        o = 20000 - richtung * (20 - 10 * k)
        df.loc[t] = [o, max(o, o + richtung * 10) + (20 if k == 2 and richtung > 0 else 0),
                     min(o, o + richtung * 10) - (20 if k == 0 and richtung > 0 else 0), o + richtung * 10]
    return df


def test_lauf_us100_oeffnet_mit_stop_und_ziel_und_schliesst_zur_zeit():
    df = _markt_us100()
    br = Broker(df)
    br.now = pd.Timestamp("2026-11-10 14:48")
    out = sb.run(br, {}, br.now.tz_localize("UTC").to_pydatetime())
    l = out["scalp-us100"]
    assert [e["event"] for e in l.log] == ["eröffnet"], l.log
    body = br.posts[0]
    assert body["epic"] == "US100" and body["direction"] == "BUY"
    assert body["stopLevel"] < 20000 < body["profitLevel"]
    ask = br.market("US100")["snapshot"]["offer"]           # Ziel 10 R ab dem Kurs beim Senden der Order
    assert body["profitLevel"] == pytest.approx(ask + 10 * (ask - body["stopLevel"]), abs=0.2)
    assert body["size"] == pytest.approx(sb.groesse(US100, ask - body["stopLevel"], Q()), abs=0.011)
    dist = 20001.0 - body["stopLevel"]                      # 1 R ab der echten Füllung (20.001)
    assert br.account_id == "111111113150"               # zurück aufs Hauptkonto
    st = l.st
    # zweiter Lauf am selben Tag: nichts Neues
    br.now = pd.Timestamp("2026-11-10 14:53")
    out = sb.run(br, {"scalp-us100": st}, br.now.tz_localize("UTC").to_pydatetime())
    assert out["scalp-us100"].log == [] and len(br.posts) == 1
    # 16:00 New York: raus
    br.now = pd.Timestamp("2026-11-10 21:03")
    out = sb.run(br, {"scalp-us100": out["scalp-us100"].st}, br.now.tz_localize("UTC").to_pydatetime())
    l = out["scalp-us100"]
    assert br.closed == ["D1"] and l.st["offen"] is None and l.st["trades"] == 1
    assert l.fertige[0]["quelle"] == "Zeit" and l.fertige[0]["r"] == pytest.approx(99.0 / dist, abs=0.01)


def test_lauf_filter_verhindert_den_trade():
    df = _markt_us100(richtung=-1)                         # rote Kerze: Short
    df.loc[df.index < pd.Timestamp("2026-11-10"), ["open", "high", "low", "close"]] -= 2000   # alle Opens weit unter dem Kurs
    br = Broker(df)
    br.now = pd.Timestamp("2026-11-10 14:48")
    out = sb.run(br, {}, br.now.tz_localize("UTC").to_pydatetime())
    ev = out["scalp-us100"].log
    assert [e["event"] for e in ev] == ["kein Trade"] and ev[0]["warum"].startswith("Filter") and not br.posts


def test_lauf_broker_schliesst_und_keine_zweite_position():
    df = _markt_us100()
    br = Broker(df)
    br.now = pd.Timestamp("2026-11-10 14:48")
    st = sb.run(br, {}, br.now.tz_localize("UTC").to_pydatetime())["scalp-us100"].st
    br.pos.clear()                                         # Stop oder Ziel beim Broker
    br.now = pd.Timestamp("2026-11-10 15:03")
    l = sb.run(br, {"scalp-us100": st}, br.now.tz_localize("UTC").to_pydatetime())["scalp-us100"]
    assert l.st["offen"] is None and l.st["trades"] == 1 and len(br.posts) == 1
    # eine fremde US100-Position auf dem Konto: kein neuer Trade
    br2 = Broker(df)
    br2.pos["X"] = {"market": {"epic": "US100"}, "position": {"dealId": "X", "size": 1}}
    br2.now = pd.Timestamp("2026-11-10 14:48")
    l = sb.run(br2, {}, br2.now.tz_localize("UTC").to_pydatetime())["scalp-us100"]
    assert not br2.posts and l.log[0]["event"].startswith("Position schon offen")


def test_lauf_verpasst_nach_zehn_minuten():
    df = _markt_us100()
    br = Broker(df)
    br.now = pd.Timestamp("2026-11-10 15:00")
    l = sb.run(br, {}, br.now.tz_localize("UTC").to_pydatetime())["scalp-us100"]
    assert [e["event"] for e in l.log] == ["verpasst"] and not br.posts


def test_ohne_siegel_nichts(monkeypatch):
    monkeypatch.setattr(sb, "vorab_ok", lambda: False)
    br = Broker(_markt_us100())
    br.now = pd.Timestamp("2026-11-10 14:48")
    out = sb.run(br, {}, br.now.tz_localize("UTC").to_pydatetime())
    assert all(o.log[0]["event"].startswith("Regeln nicht versiegelt") for o in out.values()) and not br.posts


def test_wochen_open_mitten_in_der_woche_lesbar():
    """Erster Live-Lauf 10.11.2026: das Fenster für den Wochen-Open reichte in die Zukunft, Capital.com sagte 400."""
    br = Broker(_markt_us100())
    br.now = pd.Timestamp("2026-11-10 14:48")
    tag = pd.Timestamp("2026-11-10")
    w = sb.hole_open(br, "US100", tag, "woche", br.now)
    erwartet = br.df[br.df.index >= pd.Timestamp("2026-11-08 22:00")]["open"].iloc[0]   # Wochenbeginn 17:00 New York
    assert w == pytest.approx(erwartet)
    with pytest.raises(RuntimeError, match="invalid.daterange"):
        sb.hole_open(br, "US100", tag, "woche")                    # ohne Grenze: wie vorher abgelehnt


def test_journal_ohne_neues_nur_alle_30_minuten(tmp_path, monkeypatch):
    monkeypatch.setattr(sb, "JOURNAL", tmp_path)
    st = {"format": 1, "offen": None, "opens": {}, "trades": 0, "stand": "2026-11-10T12:43:38",
          "start": "2026-11-10T12:43:38"}
    assert sb.schreiben(US100, dict(st), [], []) is True
    assert sb.schreiben(US100, {**st, "stand": "2026-11-10T12:48:38"}, [], []) is False      # nur die Zeit neu
    ev = [{"time": "2026-11-10T12:53:38", "bot": "scalp-us100", "event": "verpasst", "tag": "2026-11-10"}]
    assert sb.schreiben(US100, {**st, "stand": "2026-11-10T12:53:38"}, ev, []) is True        # Ereignis: sofort
    assert sb.schreiben(US100, {**st, "stand": "2026-11-10T12:58:38", "tag_erledigt": "2026-11-10"}, [], []) is True
    assert sb.schreiben(US100, {**st, "stand": "2026-11-10T13:28:39", "tag_erledigt": "2026-11-10"}, [], []) is True
    karte = json.loads((tmp_path / "scalp-us100.json").read_text(encoding="utf-8"))
    assert karte["stand"] == "2026-11-10T13:28:39"
