"""TikTok-Box im Schatten: Umkehr, Drittel mit Einstand, Stop vor Ziel, Verkauf zum Ask, Stand über mehrere Läufe."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from gold import tiktok_schatten as ts


def _bars(close, spread=0.3, start="2026-11-02 00:00"):
    c = np.asarray(close, float)
    idx = pd.date_range(start, periods=len(c), freq="15min")
    o = np.r_[c[0], c[:-1]]
    df = pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.5, "low": np.minimum(o, c) - 0.5, "close": c}, index=idx)
    return df, pd.Series(spread, index=idx)


def test_supertrend_dreht_einmal():
    c = np.r_[np.linspace(100, 130, 60), np.linspace(129, 90, 40)]
    richt, linie = ts.supertrend(c + 0.5, c - 0.5, c, n=5, faktor=2.0)
    gueltig = richt[richt != 0]
    assert gueltig[0] == 1 and gueltig[-1] == -1
    assert int((np.diff(gueltig) != 0).sum()) == 1
    k = int(np.flatnonzero(richt == -1)[0])
    assert k > 60 and linie[k] > c[k]


def test_drittel_und_einstand():
    # Kauf bei 100, R = 2: TP1 102 wird erreicht, danach fällt der Kurs auf den Einstieg zurück
    df, sp = _bars([100, 101, 102.5, 101, 99, 98])
    b = ts.basis(df, sp)
    teile, offen = ts.fuehre(b, 1, 1, len(b), 100.0, 98.0)
    assert not offen
    assert [t["grund"] for t in teile] == ["tp1", "einstand"]
    assert teile[0]["px"] == 102.0 and abs(teile[0]["w"] - 1 / 3) < 1e-9
    assert teile[1]["px"] == 100.0 and abs(teile[1]["w"] - 2 / 3) < 1e-9


def test_stop_vor_ziel_in_derselben_kerze():
    df, sp = _bars([100, 100, 100])
    df.iloc[1, df.columns.get_loc("high")], df.iloc[1, df.columns.get_loc("low")] = 103.0, 97.0   # über TP1 und unter Stop
    b = ts.basis(df, sp)
    teile, _ = ts.fuehre(b, 1, 1, len(b), 100.0, 98.0)
    assert teile == [{"w": 1.0, "px": 98.0, "j": 1, "grund": "stop"}]


def test_verkauf_wird_zum_ask_geschlossen():
    df, sp = _bars([100, 100, 100, 100], spread=1.0)
    df["high"] = df["close"] + 0.2                  # Bid erreicht den Stop 101 nie, der Ask (Bid + 1) schon
    b = ts.basis(df, sp)
    teile, _ = ts.fuehre(b, -1, 1, len(b), 100.0, 101.0)
    assert teile[0]["grund"] == "stop" and teile[0]["j"] == 1


def test_gegensignal_schliesst_zur_eroeffnung_und_offen_bleibt_offen():
    b = ts.basis(*_bars([100, 100.5, 100.2, 100.4, 100.1]))
    teile, offen = ts.fuehre(b, 1, 1, 3, 100.0, 95.0)
    assert not offen and teile == [{"w": 1.0, "px": float(b.o[3]), "j": 3, "grund": "gegensignal"}]
    teile, offen = ts.fuehre(b, 1, 1, len(b), 100.0, 95.0)
    assert offen and teile == []


def test_step_merkt_start_und_haengt_nur_neue_trades_an():
    rng = np.random.default_rng(7)
    c = 4000 + np.cumsum(rng.normal(0, 3, 2400))
    df, sp = _bars(c)
    t1 = df.index[1499]
    now1 = (t1 + pd.Timedelta("15min")).to_pydatetime().replace(tzinfo=timezone.utc)
    st, ev = ts.step(df.iloc[:1500], sp.iloc[:1500], {}, now1)
    assert st["start"] == str(t1 + pd.Timedelta("15min"))
    assert all(len(v) == 0 for v in st["fertig"].values()) and ev == []
    assert st["vorhersage"]["richtung"] in (1, -1)
    for end in range(1504, 2400, 4):
        now = (df.index[end - 1] + pd.Timedelta("15min")).to_pydatetime().replace(tzinfo=timezone.utc)
        st, _ = ts.step(df.iloc[end - 1400:end], sp.iloc[end - 1400:end], st, now)
    fertig = st["fertig"]["stream_box"]
    assert len(fertig) > 5
    zeiten = [t["einstieg_zeit"] for t in fertig]
    assert zeiten == sorted(set(zeiten)) and zeiten[0] >= st["start"]
    # dieselben Trades wie eine Rechnung über alle Kerzen
    ganz, _ = ts.alle(ts.basis(df.iloc[:2396], sp.iloc[:2396]))
    soll = [(t["einstieg_zeit"], t["ergebnis_r"]) for t in ganz["stream_box"]
            if t["einstieg_zeit"] >= st["start"] and not t["offen"]]
    assert [(t["einstieg_zeit"], t["ergebnis_r"]) for t in fertig] == soll


def test_urteil_erst_nach_40():
    assert ts.zusammenfassung([{"ergebnis_r": 1.0}] * 39)["urteil"].startswith("läuft")
    gut = [{"ergebnis_r": 1.0}] * 25 + [{"ergebnis_r": -1.0}] * 15
    assert ts.zusammenfassung(gut)["urteil"].startswith("bestanden")
    schlecht = [{"ergebnis_r": 1.0}] * 20 + [{"ergebnis_r": -1.0}] * 20
    assert ts.zusammenfassung(schlecht)["urteil"].startswith("durchgefallen")


def test_keine_order_funktion():
    text = (ts.ROOT / "gold" / "tiktok_schatten.py").read_text(encoding="utf-8")
    for verboten in ("open_position", "create_position", "close_position", "/positions\"", "_request(\"POST\""):
        assert verboten not in text


def test_box_175_dreht_oefter_als_20_2():
    rng = np.random.default_rng(11)
    c = 4000 + np.cumsum(rng.normal(0, 3, 1500))
    df, sp = _bars(c)
    trades, vorhersage = ts.alle(ts.basis(df, sp))
    assert len(trades["box_175"]) >= len(trades["stream_box"]) > 5
    assert vorhersage["genauer_175"]["richtung"] in (1, -1)


def test_box_175_zaehlt_erst_ab_eigenem_start():
    # Ein alter Stand ohne box_175 (Schatten lief schon): box_175 startet beim nächsten Lauf, nicht rückwirkend
    rng = np.random.default_rng(7)
    c = 4000 + np.cumsum(rng.normal(0, 3, 2400))
    df, sp = _bars(c)
    t1 = df.index[1499]
    alt = {"start": str(t1 + pd.Timedelta("15min")), "fertig": {"stream_box": [], "gross_klein_3": []}}
    end = 1900
    now = (df.index[end - 1] + pd.Timedelta("15min")).to_pydatetime().replace(tzinfo=timezone.utc)
    st, _ = ts.step(df.iloc[end - 1400:end], sp.iloc[end - 1400:end], alt, now)
    assert st["start_je"]["stream_box"] == alt["start"]
    assert st["start_je"]["box_175"] == str(df.index[end - 1] + pd.Timedelta("15min"))
    assert st["fertig"]["box_175"] == [] and len(st["fertig"]["stream_box"]) > 0
    assert "box_175" in st["zusammenfassung"] and "text_175" in st["vorhersage"]


def test_gross_box_hoechstens_drei_offen_und_nur_in_boxrichtung():
    rng = np.random.default_rng(3)
    c = 4000 + np.cumsum(rng.normal(0.2, 3, 2400))
    df, sp = _bars(c)
    b = ts.basis(df, sp)
    m15, h1, h4 = ts.ebene(b, "15m"), ts.ebene(b, "1h"), ts.ebene(b, "4h")
    trs = ts.gross_box(b, m15, h1, h4)
    assert len(trs) > 5
    gd = ts.grosse_richtung(b, h1, h4)
    for t in trs:
        j0 = int(np.searchsorted(b.t, np.datetime64(pd.Timestamp(t["einstieg_zeit"]))))
        assert gd[j0] == t["richtung"] and t["art"] in ("a", "b", "c")
    # nie mehr als 3 zugleich offen
    for t in trs:
        tin = pd.Timestamp(t["einstieg_zeit"])
        offen = [x for x in trs if pd.Timestamp(x["einstieg_zeit"]) <= tin
                 and (x["offen"] or pd.Timestamp(x["ende"]) > tin)]
        assert len(offen) <= 3
    assert any(t["grund"] == "neue_box" for t in trs)
    assert len(ts.gross_box(b, m15, h1, h4, kerze=False)) >= len(trs)


def test_mehrfach_frueher_offener_trade_zaehlt_wenn_er_spaeter_schliesst():
    now = datetime(2026, 11, 6, 10, tzinfo=timezone.utc)
    a = {"einstieg_zeit": "2026-11-06 08:00:00", "richtung": 1, "einstieg": 1.0, "stop": 0.0, "tp1": 2.0, "art": "a",
         "grund": "offen", "ergebnis_r": 0.0, "offen": True}
    b = {**a, "einstieg_zeit": "2026-11-06 08:30:00", "art": "b", "offen": False, "grund": "stop", "ergebnis_r": -1.0}
    fertig, offen, ev = [], {}, []
    ts._mehrfach("gross_box_kerze", [a, b], fertig, [], pd.Timestamp("2026-11-06 07:00"), now, offen, ev)
    assert [t["einstieg_zeit"] for t in fertig] == ["2026-11-06 08:30:00"]
    assert [t["einstieg_zeit"] for t in offen["gross_box_kerze"]] == ["2026-11-06 08:00:00"]
    a_fertig = {**a, "offen": False, "grund": "neue_box", "ergebnis_r": 2.5}
    offen2, ev2 = {}, []
    ts._mehrfach("gross_box_kerze", [a_fertig, b], fertig, offen["gross_box_kerze"], pd.Timestamp("2026-11-06 07:00"),
                 now, offen2, ev2)
    assert sorted(t["einstieg_zeit"] for t in fertig) == ["2026-11-06 08:00:00", "2026-11-06 08:30:00"]
    assert offen2 == {} and [e["ereignis"] for e in ev2] == ["fertig"]
    # ein unbekannter alter Trade (Neuberechnung) zählt nicht
    alt = {**b, "einstieg_zeit": "2026-11-06 08:15:00"}
    ts._mehrfach("gross_box_kerze", [alt], fertig, [], pd.Timestamp("2026-11-06 07:00"), now, {}, [])
    assert len(fertig) == 2


def test_gross_box_im_schatten_wie_in_einer_rechnung():
    rng = np.random.default_rng(3)
    c = 4000 + np.cumsum(rng.normal(0.2, 3, 2400))
    df, sp = _bars(c)
    t1 = df.index[1499]
    now1 = (t1 + pd.Timedelta("15min")).to_pydatetime().replace(tzinfo=timezone.utc)
    st, _ = ts.step(df.iloc[:1500], sp.iloc[:1500], {}, now1)
    for end in range(1504, 2400, 4):
        now = (df.index[end - 1] + pd.Timedelta("15min")).to_pydatetime().replace(tzinfo=timezone.utc)
        st, _ = ts.step(df.iloc[max(0, end - 1400):end], sp.iloc[max(0, end - 1400):end], st, now)
    fertig = st["fertig"]["gross_box_kerze"]
    ganz, _ = ts.alle(ts.basis(df.iloc[:2396], sp.iloc[:2396]))
    soll = sorted((t["einstieg_zeit"], t["ergebnis_r"]) for t in ganz["gross_box_kerze"]
                  if t["einstieg_zeit"] >= st["start"] and not t["offen"])
    ist = sorted((t["einstieg_zeit"], t["ergebnis_r"]) for t in fertig)
    assert len(soll) > 3 and ist == soll
    assert st["vorhersage"]["grosse_box"] in (-1, 0, 1) and "text_gross" in st["vorhersage"]
