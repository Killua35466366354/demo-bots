"""Tests für die Runde-6-Demo-Bots: Regeln (suche/r6_regeln.py), Zwilling (suche/r6_zwilling.py) und der Lauf mit
einem nachgebauten Broker (suche/r6_bots.py). Ohne Netz."""
import numpy as np
import pandas as pd

from suche import r6_bots as rb
from suche import r6_regeln as rg
from suche import r6_zwilling as zw

NY, LON = "America/New_York", "Europe/London"


def utc(datum: str, hhmm: str, tz: str) -> pd.Timestamp:
    return pd.Timestamp(f"{datum} {hhmm}", tz=tz).tz_convert("UTC").tz_localize(None)


# ---------------------------------------------------------------------------------------------------------------------
# Platz 1: Vortageshoch/-tief

def vt_bars(bis_utc: pd.Timestamp, ausbruch: dict | None = None) -> pd.DataFrame:
    """15-Minuten-Bid-Kerzen ab Mo 02.11.2026 18:00 New York (Beginn des Handelstags Di 03.11.) bis vor `bis_utc`.
    Vortag (Di 03.11.): Hoch 150,5, Tief 149,5. Heute (Mi 04.11.): Kerzen 149,8 bis 150,2. ausbruch: Kerzenbeginn New York
    'HH:MM' am 04.11. -> (hoch, tief)."""
    idx = pd.date_range(utc("2026-11-02", "18:00", NY), bis_utc, freq="15min", inclusive="left")
    df = pd.DataFrame({"open": 150.0, "high": 150.2, "low": 149.8, "close": 150.0}, index=idx)
    df.loc[utc("2026-11-03", "09:00", NY), "high"] = 150.5
    df.loc[utc("2026-11-03", "11:00", NY), "low"] = 149.5
    for hhmm, (h, low) in (ausbruch or {}).items():
        df.loc[utc("2026-11-04", hhmm, NY), ["high", "low"]] = [h, low]
    return df


def test_vortag_wartet_bis_4_30_new_york():
    jetzt = utc("2026-11-04", "04:16", NY)
    d = rg.vt_entscheide(vt_bars(jetzt - pd.Timedelta(minutes=1)), jetzt, {})
    assert d["action"] == "none" and not d.get("erledigt")


def test_vortag_legt_stop_orders_mit_festen_kursen():
    """Stop seit 04.11.2026: 0,5 x ATR(14) der fertigen Viertelstunden (hier Kerzen von 0,4 Spanne: ATR 0,4, Stop 0,2
    hinter der Marke); das Ziel bleibt 25 % der Vortagesspanne."""
    jetzt = utc("2026-11-04", "04:31", NY)
    bars = vt_bars(jetzt - pd.Timedelta(minutes=1))
    d = rg.vt_entscheide(bars, jetzt, {})
    assert d["action"] == "orders" and (d["ph"], d["pl"]) == (150.5, 149.5)
    sa, atr = rg.vt_stop_abstand(bars)
    assert abs(atr - 0.4) < 1e-3 and abs(sa - 0.5 * atr) < 1e-12 and d["stop_abstand"] == sa and d["atr15"] == atr
    assert abs(d["long"]["stop"] - (150.5 - sa)) < 1e-9 and abs(d["long"]["ziel"] - 150.75) < 1e-9
    assert abs(d["short"]["stop"] - (149.5 + sa)) < 1e-9 and abs(d["short"]["ziel"] - 149.25) < 1e-9
    assert pd.Timestamp(d["gueltig_bis_utc"]) == utc("2026-11-04", "16:30", NY)


def test_vortag_stop_atr_nur_aus_fertigen_kerzen_und_genug_davon():
    jetzt = utc("2026-11-04", "04:31", NY)
    bars = vt_bars(jetzt - pd.Timedelta(minutes=1))
    a = rg.atr_rma(bars["high"].to_numpy(float), bars["low"].to_numpy(float), bars["close"].to_numpy(float), 14)
    assert rg.vt_stop_abstand(bars) == (0.5 * a[-1], a[-1])                  # Wert der letzten (fertigen) Kerze
    kurz = bars.iloc[-60:]                                                   # weniger als 70 Kerzen: keine ATR
    assert rg.vt_stop_abstand(kurz) is None
    tage = rg.vt_tage(bars)
    assert rg.vt_vortag(tage, pd.Timestamp("2026-11-04")) == (150.5, 149.5)


def test_vortag_frueher_ausbruch_heisst_kein_trade():
    jetzt = utc("2026-11-04", "04:31", NY)
    d = rg.vt_entscheide(vt_bars(jetzt - pd.Timedelta(minutes=1), {"03:00": (150.6, 150.0)}), jetzt, {})
    assert d["action"] == "none" and d.get("erledigt")


def test_vortag_ausbruch_genau_um_4_15_zaehlt_noch_als_frueh():
    jetzt = utc("2026-11-04", "04:31", NY)
    d = rg.vt_entscheide(vt_bars(jetzt - pd.Timedelta(minutes=1), {"04:15": (150.6, 150.0)}), jetzt, {})
    assert d["action"] == "none" and d.get("erledigt")


def nachhol_bars(bis_utc: pd.Timestamp, nach: tuple = (150.58, 150.45)) -> pd.DataFrame:
    """Ausbruch über das Vortageshoch 150,5 in der Kerze 06:00 New York, danach Kerzen zwischen `nach` (tief, hoch)."""
    df = vt_bars(bis_utc)
    df.loc[utc("2026-11-04", "06:00", NY), ["open", "high", "low", "close"]] = [150.2, 150.6, 150.15, 150.55]
    rest = df.index > utc("2026-11-04", "06:00", NY)
    df.loc[rest, ["open", "high", "low", "close"]] = [150.5, nach[0], nach[1], 150.5]
    return df


def test_vortag_verpasster_ausbruch_wird_nachgeholt():
    """Kiron 04.11.2026: lieber zu spät einsteigen als einen Trade verpassen. Stop und Ziel wie bei den Stop-Orders."""
    jetzt = utc("2026-11-04", "06:31", NY)
    bars = nachhol_bars(jetzt - pd.Timedelta(minutes=1))
    d = rg.vt_entscheide(bars, jetzt, {})
    assert d["action"] == "nachholen" and d["side"] == 1 and not d.get("erledigt")
    sa, _ = rg.vt_stop_abstand(bars.loc[:utc("2026-11-04", "04:15", NY)])      # ATR wie beim Legen um 4:31
    assert abs(d["stop"] - (150.5 - sa)) < 1e-9 and abs(d["ziel"] - 150.75) < 1e-9
    assert d["ausbruch_kerze"] == str(utc("2026-11-04", "06:00", NY)) and d["verspaetung_min"] == 31


def test_vortag_nachholen_nur_solange_der_trade_noch_liefe():
    zu_spaet = utc("2026-11-04", "07:16", NY)                                  # 76 Minuten nach Beginn der Kerze
    d = rg.vt_entscheide(nachhol_bars(zu_spaet - pd.Timedelta(minutes=1)), zu_spaet, {})
    assert d["action"] == "none" and d["erledigt"] and "zu spät" in " ".join(d["why"])
    jetzt = utc("2026-11-04", "06:31", NY)
    ziel = rg.vt_entscheide(nachhol_bars(jetzt - pd.Timedelta(minutes=1), (150.8, 150.45)), jetzt, {})
    assert ziel["action"] == "none" and "Ziel schon erreicht" in ziel["why"]
    stop = rg.vt_entscheide(nachhol_bars(jetzt - pd.Timedelta(minutes=1), (150.55, 150.1)), jetzt, {})
    assert stop["action"] == "none" and "Stop schon getroffen" in stop["why"]


def test_vortag_offene_position_schliesst_um_16_45():
    op = {"tag": "2026-11-04", "side": 1}
    assert rg.vt_entscheide(rb.LEER, utc("2026-11-04", "16:31", NY), {"open": op})["action"] == "none"
    assert rg.vt_entscheide(rb.LEER, utc("2026-11-04", "16:46", NY), {"open": op})["action"] == "close"
    orders = {"tag": "2026-11-04"}
    assert rg.vt_entscheide(rb.LEER, utc("2026-11-04", "16:31", NY), {"orders": orders})["action"] == "cancel"


# ---------------------------------------------------------------------------------------------------------------------
# Platz 2: London-Stunde

def ld_bars(bis_utc: pd.Timestamp, signal: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """GBP/USD am Mi 04.11.2026: Bereich 4 bis 9 Uhr London 1,2690 bis 1,2710; die 9-Uhr-Stunde eröffnet bei 1,2705 und
    schließt bei 1,2715. Dazu Stundenkerzen der zwei Tage davor mit 10 Pips Spanne (für die ATR)."""
    idx = pd.date_range(utc("2026-11-04", "00:00", LON), bis_utc, freq="15min", inclusive="left")
    df = pd.DataFrame({"open": 1.2700, "high": 1.2704, "low": 1.2696, "close": 1.2700}, index=idx)
    df.loc[utc("2026-11-04", "05:00", LON), "high"] = 1.2710
    df.loc[utc("2026-11-04", "06:00", LON), "low"] = 1.2690
    if signal:
        for hhmm, o, h, low, c in (("09:00", 1.2705, 1.2707, 1.2702, 1.2706), ("09:15", 1.2706, 1.2709, 1.2704, 1.2708),
                                   ("09:30", 1.2708, 1.2712, 1.2706, 1.2711), ("09:45", 1.2711, 1.2716, 1.2709, 1.2715)):
            t = utc("2026-11-04", hhmm, LON)
            if t in df.index:
                df.loc[t] = [o, h, low, c]
    vor = pd.date_range(utc("2026-11-02", "00:00", LON), utc("2026-11-04", "00:00", LON), freq="60min",
                        inclusive="left")
    alt = pd.DataFrame({"open": 1.27, "high": 1.2705, "low": 1.2695, "close": 1.27}, index=vor)
    st = pd.concat([alt, rb_stunden(df)])
    return df, st[st.index + pd.Timedelta(hours=1) <= bis_utc]


def rb_stunden(b: pd.DataFrame) -> pd.DataFrame:
    return b.resample("60min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


def test_london_long_zur_naechsten_stunde_mit_stop_am_bereichstief():
    jetzt = utc("2026-11-04", "10:01", LON)
    bars, st = ld_bars(jetzt - pd.Timedelta(minutes=1))
    d = rg.ld_entscheide(bars, st, jetzt, {}, 0.7)
    assert d["action"] == "open" and d["side"] == 1 and d["stop_level"] == 1.2690 and d["ziel_r"] == 1.5
    assert pd.Timestamp(d["signal_bar"]) == utc("2026-11-04", "09:00", LON)


def test_london_verpasst_und_unruhiger_markt():
    jetzt = utc("2026-11-04", "10:31", LON)
    bars, st = ld_bars(jetzt - pd.Timedelta(minutes=1))
    d = rg.ld_entscheide(bars, st, jetzt, {}, 0.7)
    assert d["action"] == "none" and d.get("erledigt")
    jetzt = utc("2026-11-04", "10:01", LON)
    bars, st = ld_bars(jetzt - pd.Timedelta(minutes=1))
    d = rg.ld_entscheide(bars, st, jetzt, {}, 0.95)
    assert d["action"] == "none" and d.get("erledigt")


def test_london_schliesst_um_17_uhr():
    op = {"tag": "2026-11-04", "side": 1}
    assert rg.ld_entscheide(rb.LEER, rb.LEER, utc("2026-11-04", "16:46", LON), {"open": op}, None)["action"] == "none"
    assert rg.ld_entscheide(rb.LEER, rb.LEER, utc("2026-11-04", "17:01", LON), {"open": op}, None)["action"] == "close"


# ---------------------------------------------------------------------------------------------------------------------
# Platz 3: Noise-Band

def nb_heute(bis_utc: pd.Timestamp, schluesse: dict) -> pd.DataFrame:
    idx = pd.date_range(utc("2026-11-04", "08:00", LON), bis_utc, freq="15min", inclusive="left")
    df = pd.DataFrame({"open": 150.0, "high": 150.05, "low": 149.95, "close": 150.0}, index=idx)
    for hhmm, c in schluesse.items():
        t = utc("2026-11-04", hhmm, LON)
        if t in df.index:
            df.loc[t, ["high", "close"]] = [max(c, 150.05), c]
    return df


BAND = {"sig": np.full(36, 0.001), "vortag_schluss": 150.0}       # Band 150,15 / 149,85


def test_noise_long_ueber_dem_band_und_raus_beim_gegensignal():
    jetzt = utc("2026-11-04", "08:31", LON)
    d = rg.nb_entscheide(nb_heute(jetzt - pd.Timedelta(minutes=1), {"08:15": 150.3}), jetzt, {}, 0.7, BAND)
    assert d["action"] == "open" and d["side"] == 1
    jetzt = utc("2026-11-04", "09:01", LON)
    op = {"tag": "2026-11-04", "side": 1}
    d = rg.nb_entscheide(nb_heute(jetzt - pd.Timedelta(minutes=1), {"08:15": 150.3}), jetzt, {"open": op}, 0.7, BAND)
    assert d["action"] == "close" and d["reason"] == "signal"


def test_noise_kein_spaeter_einstieg_und_unruhiger_markt():
    jetzt = utc("2026-11-04", "09:01", LON)                          # Signal von 8:30 ist nicht mehr frisch
    d = rg.nb_entscheide(nb_heute(jetzt - pd.Timedelta(minutes=1), {"08:15": 150.3, "08:45": 150.3}), jetzt, {}, 0.7,
                         BAND)
    assert d["action"] == "none"
    jetzt = utc("2026-11-04", "08:31", LON)
    d = rg.nb_entscheide(nb_heute(jetzt - pd.Timedelta(minutes=1), {"08:15": 150.3}), jetzt, {}, 0.95, BAND)
    assert d["action"] == "none"


# ---------------------------------------------------------------------------------------------------------------------
# Hilfen

def test_fertiger_tag():
    assert rb.fertiger_tag("vortag_stop_oco", utc("2026-11-04", "16:46", NY)) == "2026-11-03"
    assert rb.fertiger_tag("vortag_stop_oco", utc("2026-11-04", "17:01", NY)) == "2026-11-04"
    assert rb.fertiger_tag("noise_band", utc("2026-11-09", "09:00", LON)) == "2026-11-06"      # Montag früh: Freitag
    assert rb.fertiger_tag("london_stunde_long", utc("2026-11-04", "17:01", LON)) == "2026-11-04"


class Q:
    def __init__(self, eur_rate=175.0, lot=1.0, step=100.0, min_size=100.0, margin=3.33):
        self.eur_rate, self.lot, self.size_step, self.min_size, self.margin_pct = eur_rate, lot, step, min_size, margin
        self.currency = "JPY"


def test_groesse_ein_prozent_hoechstens_10_euro_und_margin():
    size, info, why = rb.groesse(Q(), 0.09, 1000.0, 2000.0, 150.0)       # 10 EUR / (0,09 / 175) = 19.444 -> 19.400
    assert why == [] and size == 19400.0 and info["risiko_eur"] <= 10.0
    size, _, why = rb.groesse(Q(), 0.09, 300.0, 2000.0, 150.0)           # 1 % von 300 = 3 EUR
    assert size == 5800.0
    size, info, why = rb.groesse(Q(), 0.09, 1000.0, 1000.0, 150.0)       # Margin höchstens die Hälfte von 1000 EUR
    assert size == 17500.0 and info["margin_eur"] <= 500.0
    size, _, why = rb.groesse(Q(step=100000.0, min_size=100000.0), 0.09, 1000.0, 1000.0, 150.0)
    assert size is None and "mehr als 10 EUR" in why[0]


HAUPT, ANDERER, VT, LD, NB, ALT = "3150", "5310", "9001", "9002", "9003", "8878"


def accounts(namen: dict) -> list[dict]:
    return [{"accountId": aid, "accountName": n, "currency": "EUR", "status": "ENABLED",
             "balance": {"balance": 1000.0, "available": 1000.0}} for aid, n in namen.items()]


def test_konto_nur_mit_passendem_namen():
    acc = accounts({HAUPT: "Account", ANDERER: "Account 1", ALT: "US500", VT: "Vortag USDJPY", NB: "Noise USDJPY"})
    kont = {"zuordnung": {"us500-ruecksetzer": ALT}}
    assert rb.konto_fuer(rb.VORTAG, acc, kont, HAUPT, lambda a: True) == VT
    assert rb.konto_fuer(rb.NOISE, acc, kont, HAUPT, lambda a: True) == NB
    assert rb.konto_fuer(rb.LONDON, acc, kont, HAUPT, lambda a: True) is None     # kein Ersatzkonto
    kont2 = {"zuordnung": {"jemand": VT}}
    assert rb.konto_fuer(rb.VORTAG, acc, kont2, HAUPT, lambda a: True) is None    # gehört schon einem anderen Bot
    acc3 = accounts({HAUPT: "Vortag", ANDERER: "Account 1"})
    assert rb.konto_fuer(rb.VORTAG, acc3, {}, HAUPT, lambda a: True) is None       # nie das Hauptkonto


def test_konto_aus_der_zuordnung_auch_ohne_passenden_namen():
    """Kontolimit erreicht (04.11.2026): demo_bots gibt Konten beendeter Bots weiter, indem es zuordnung[r6-...]
    schreibt. Der Name passt dann nicht, das Konto gilt trotzdem."""
    acc = accounts({HAUPT: "Account", "3678": "Account 6", "9086": "Account 5", "6542": "Account 7"})
    kont = {"zuordnung": {"r6-vortag-usdjpy": "3678", "r6-london-gbpusd": "9086"}}
    assert rb.konto_fuer(rb.VORTAG, acc, kont, HAUPT, lambda a: True) == "3678"
    assert rb.konto_fuer(rb.LONDON, acc, kont, HAUPT, lambda a: True) == "9086"
    assert rb.konto_fuer(rb.NOISE, acc, kont, HAUPT, lambda a: True) is None       # noch nicht übergeben


def test_vortag_eurusd_gbpusd_nur_ueber_die_zuordnung():
    """Die Vortags-Bots auf EUR/USD und GBP/USD nehmen sich nie ein Konto über den Namen, nur über die Zuordnung."""
    acc = accounts({HAUPT: "Account", "3678": "Account 6", "1111": "Vortag EURUSD", "2222": "GBPUSD"})
    assert rb.konto_fuer(rb.VORTAG_EURUSD, acc, {"zuordnung": {}}, HAUPT, lambda a: True) is None
    assert rb.konto_fuer(rb.VORTAG_GBPUSD, acc, {"zuordnung": {}}, HAUPT, lambda a: True) is None
    kont = {"zuordnung": {"r6-vortag-eurusd": "3678"}}
    assert rb.konto_fuer(rb.VORTAG_EURUSD, acc, kont, HAUPT, lambda a: True) == "3678"
    assert rb.VORTAG_EURUSD.regel == rb.VORTAG_GBPUSD.regel == rb.VORTAG_ATR_REGEL and "0,5 x ATR" in rb.VORTAG_ATR_REGEL
    assert rb.VORTAG_GBPUSD.strategie == "vortag_stop_oco"
    assert [b.bot_id for b in rb.BOTS] == ["r6-vortag-usdjpy", "r6-london-gbpusd", "r6-noise-usdjpy",
                                           "r6-vortag-eurusd", "r6-vortag-gbpusd", "r6-vortag-gbpjpy"]


def test_vortag_gbpjpy_gleiche_regel_und_nur_ueber_die_zuordnung():
    """GBP/JPY (Test vom 05.11.2026) nutzt genau die Regel von EUR/USD und GBP/USD und nimmt sich kein Konto selbst."""
    acc = accounts({HAUPT: "Account", "4494": "Account 2", "2606": "Account 3", "1111": "GBPJPY"})
    assert rb.VORTAG_GBPJPY.regel == rb.VORTAG_ATR_REGEL and rb.VORTAG_GBPJPY.strategie == "vortag_stop_oco"
    assert rb.VORTAG_GBPJPY.epic == "GBPJPY" and rb.VORTAG_GBPJPY.konto_namen == ()
    assert rb.konto_fuer(rb.VORTAG_GBPJPY, acc, {"zuordnung": {}}, HAUPT, lambda a: True) is None
    kont = {"zuordnung": {"r6-vortag-gbpjpy": "4494"}}
    assert rb.konto_fuer(rb.VORTAG_GBPJPY, acc, kont, HAUPT, lambda a: True) == "4494"
    assert rb.pip("GBPJPY") == 0.01


# ---------------------------------------------------------------------------------------------------------------------
# Zwilling

def test_zwilling_findet_den_vortags_trade_und_vergleicht():
    bis = utc("2026-11-04", "17:00", NY)
    bars = vt_bars(bis)
    bars.loc[utc("2026-11-04", "06:00", NY)] = [150.3, 150.6, 150.25, 150.5]          # Ausbruch über 150,5
    bars.loc[utc("2026-11-04", "06:15", NY):utc("2026-11-04", "07:45", NY)] = [150.5, 150.6, 150.45, 150.5]
    bars.loc[utc("2026-11-04", "08:00", NY)] = [150.5, 150.8, 150.45, 150.7]           # Ziel 150,75
    sp = pd.Series(0.01, index=bars.index)
    z = zw.zwilling_tag("vortag_stop_oco", "USDJPY", bars, sp, "2026-11-04")
    assert z["tag_gezaehlt"] and len(z["trades"]) == 1
    t = z["trades"][0]
    assert t["side"] == "long" and t["zaehlt"] and t["grund"] == "ziel"
    assert pd.Timestamp(t["einstieg_kerze"]) == utc("2026-11-04", "06:00", NY)
    v = zw.vergleiche(z["trades"], [{"einstieg_kerze": t["einstieg_kerze"], "side": "long", "pct": t["pct"]}])
    assert v["gleich"]
    assert not zw.vergleiche(z["trades"], [])["gleich"]
    # Der Zwilling nimmt denselben Stop wie der Bot beim Legen um 4:31 New York (ATR der Kerzen bis 4:15)
    sa, _ = rg.vt_stop_abstand(bars.loc[:utc("2026-11-04", "04:15", NY)])
    assert abs(t["stop_abst"] - sa) < 1e-6


def test_zwilling_eurusd_gbpusd_schatten_bis_zum_konto(monkeypatch):
    """Ohne Konto bleiben EUR/USD und GBP/USD Schatten wie bisher; mit Konto vergleicht der Zwilling mit dem Bot."""
    monkeypatch.setattr(rb, "kerzen", lambda *a, **k: (pd.DataFrame(), pd.Series(dtype=float)))
    monkeypatch.setattr(rb, "kerzen_zeitraum", lambda *a, **k: (pd.DataFrame(), pd.Series(dtype=float)))
    monkeypatch.setattr(rb, "tageswerte", lambda *a, **k: {"schwankung": 0.5})
    monkeypatch.setattr(zw, "zwilling_tag", lambda *a, **k: {"tag_gezaehlt": True, "trades": []})
    lauf = rb.Lauf(None, utc("2026-11-04", "17:30", NY), {}, True)
    rows = rb.zwillinge(lauf, {"bots": {}}, [])
    keys = sorted((r["strategie"], r["markt"]) for r in rows)
    assert keys == sorted([("vortag_stop_oco", "USDJPY"), ("london_stunde_long", "GBPUSD"), ("noise_band", "USDJPY"),
                           ("vortag_stop_oco", "EURUSD"), ("vortag_stop_oco", "GBPUSD"),
                           ("vortag_stop_oco", "GBPJPY")])
    by = {(r["strategie"], r["markt"]): r for r in rows}
    assert by[("vortag_stop_oco", "EURUSD")]["schatten"] and not by[("vortag_stop_oco", "EURUSD")]["konto"]
    assert not by[("vortag_stop_oco", "GBPJPY")]["konto"]          # GBP/JPY ohne Konto: Zwilling schreibt nur mit
    assert not by[("london_stunde_long", "GBPUSD")]["schatten"] and not by[("noise_band", "USDJPY")]["schatten"]
    assert by[("vortag_stop_oco", "USDJPY")]["schatten"]                  # beendet: nur noch Schatten
    lauf2 = rb.Lauf(None, utc("2026-11-05", "17:30", NY), {}, True)
    rows2 = rb.zwillinge(lauf2, {"bots": {"r6-vortag-eurusd": {"konto_id": "3678"}}}, [])
    eu = next(r for r in rows2 if r["markt"] == "EURUSD")
    assert eu["konto"] and not eu["schatten"] and eu["vergleich"]["gleich"]


# ---------------------------------------------------------------------------------------------------------------------
# Lauf mit nachgebautem Broker

class Antwort:
    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class FakeBroker:
    """Hauptkonto, Konto eines anderen Bots und die drei Konten der Runde-6-Bots."""
    environment = "demo"

    def __init__(self, namen: dict | None = None, kurs: dict | None = None):
        self.namen = namen or {HAUPT: "Account", ANDERER: "Account 1", VT: "Vortag USDJPY", LD: "London GBPUSD",
                               NB: "Noise USDJPY"}
        self.account_id = HAUPT
        self.pos = {a: [] for a in self.namen}
        self.wo = {a: [] for a in self.namen}
        self.kurs = kurs or {"USDJPY": (150.0, 150.01), "GBPUSD": (1.2710, 1.27112), "EURJPY": (175.0, 175.02),
                             "EURUSD": (1.08, 1.08002)}
        self.requests, self.closed, self.activities = [], [], []
        self.n = 0

    def login(self):
        self.account_id = HAUPT

    def logout(self):
        pass

    def accounts(self):
        return accounts(self.namen)

    def switch_account(self, aid):
        self.account_id = aid

    def positions(self):
        return list(self.pos[self.account_id])

    def market(self, epic):
        bid, offer = self.kurs[epic]
        dec = 3 if epic.endswith("JPY") else 5
        return {"snapshot": {"bid": bid, "offer": offer, "marketStatus": "TRADEABLE", "decimalPlacesFactor": dec},
                "instrument": {"currency": "JPY" if epic.endswith("JPY") else "USD", "lotSize": 1, "marginFactor": 3.33,
                               "marginFactorUnit": "PERCENTAGE"},
                "dealingRules": {"minDealSize": {"value": 100}, "minSizeIncrement": {"value": 100},
                                 "minStopOrProfitDistance": {"unit": "POINTS", "value": 0.0}}}

    def prices(self, epic, resolution="HOUR", max_bars=1000):
        return []

    def _get(self, path, **params):
        if path == "/workingorders":
            return {"workingOrders": [{"workingOrderData": w} for w in self.wo[self.account_id]]}
        if path == "/history/activity":
            return {"activities": self.activities}
        return {"prices": []}

    def _request(self, method, path, **kw):
        self.requests.append((self.account_id, method, path, kw.get("json")))
        self.n += 1
        if method == "POST" and path == "/workingorders":
            self.wo[self.account_id].append({"dealId": f"W{self.n}", "epic": kw["json"]["epic"],
                                             "direction": kw["json"]["direction"], "orderLevel": kw["json"]["level"]})
        elif method == "DELETE" and path.startswith("/workingorders/"):
            did = path.rsplit("/", 1)[1]
            self.wo[self.account_id] = [w for w in self.wo[self.account_id] if w["dealId"] != did]
        elif method == "POST" and path == "/positions":
            b = kw["json"]
            self.pos[self.account_id].append({"market": {"epic": b["epic"]}, "position": {
                "dealId": f"P{self.n}", "direction": b["direction"], "size": b["size"],
                "level": self.kurs[b["epic"]][1 if b["direction"] == "BUY" else 0], "createdDateUTC": "2026-11-04T10:00:05",
                "stopLevel": b.get("stopLevel"), "profitLevel": b.get("profitLevel")}})
        return Antwort({"dealReference": f"R{self.n}"})

    def confirm(self, ref):
        return {"dealStatus": "ACCEPTED", "dealId": f"W{ref[1:]}"}

    def close_position(self, deal_id):
        self.closed.append((self.account_id, deal_id))
        self.pos[self.account_id] = [p for p in self.pos[self.account_id] if p["position"]["dealId"] != deal_id]
        return {"dealStatus": "ACCEPTED", "level": 150.2}

    def activity(self, deal_id, since, until):
        return self.activities


def ohne_zwilling(monkeypatch):
    monkeypatch.setattr(rb, "zwillinge", lambda lauf, state, trades: [])


def vortag_usdjpy_aktiv(monkeypatch):
    """Die Läufe der Vortags-Regel werden am USD/JPY-Bot getestet (derselbe Code wie EUR/USD und GBP/USD); dafür gilt er
    hier als nicht beendet."""
    monkeypatch.setattr(rb, "BEENDET", {})


def test_vortag_lauf_legt_orders_loescht_die_andere_und_schliesst(monkeypatch):
    ohne_zwilling(monkeypatch)
    vortag_usdjpy_aktiv(monkeypatch)
    fb = FakeBroker()
    jetzt = utc("2026-11-04", "04:31", NY)
    monkeypatch.setattr(rb, "kerzen", lambda c, e, r, n, t: (vt_bars(t - pd.Timedelta(minutes=1)), pd.Series(dtype=float)))
    monkeypatch.setattr(rb, "entscheidung_markt", lambda *a: {"action": "none", "tag": "2026-11-04", "why": ["test"]})
    kont = {"haupt": HAUPT, "zuordnung": {"anderer": ANDERER}}
    st, neu, log, _ = rb.run(fb, {}, kont, jetzt)
    posts = [r for r in fb.requests if r[1] == "POST" and r[2] == "/workingorders"]
    assert len(posts) == 2 and all(r[0] == VT for r in posts)
    lang = next(r[3] for r in posts if r[3]["direction"] == "BUY")
    kurz = next(r[3] for r in posts if r[3]["direction"] == "SELL")
    sa, _ = rg.vt_stop_abstand(vt_bars(jetzt - pd.Timedelta(minutes=1)))
    assert abs(lang["level"] - 150.51) < 1e-9 and lang["stopLevel"] == round(150.5 - sa, 3)
    assert kurz["level"] == 149.5 and kurz["stopLevel"] == round(149.5 + sa, 3)
    assert lang["profitLevel"] == 150.75 and kurz["profitLevel"] == 149.25
    o = st["bots"]["r6-vortag-usdjpy"]["orders"]
    assert o["long"]["stop"] == lang["stopLevel"] and o["short"]["stop"] == kurz["stopLevel"] and o["stop_abstand"] == sa
    assert lang["goodTillDate"] == "2026-11-04T21:30:00" and lang["type"] == "STOP"
    assert kont["zuordnung"]["r6-vortag-usdjpy"] == VT and fb.account_id == HAUPT
    assert st["bots"]["r6-vortag-usdjpy"]["status"] == "Stop-Orders liegen"
    assert "wartet auf ein eigenes Demokonto" not in st["bots"]["r6-london-gbpusd"]["status"]

    # Die Kauf-Order löst aus: Position da, Order weg. Der nächste Lauf löscht die Verkaufs-Order.
    buy = next(w for w in fb.wo[VT] if w["direction"] == "BUY")
    fb.wo[VT].remove(buy)
    fb.pos[VT].append({"market": {"epic": "USDJPY"}, "position": {
        "dealId": "POS1", "direction": "BUY", "size": lang["size"], "level": 150.512, "createdDateUTC": "2026-11-04T11:07:12"}})
    st, neu, log, _ = rb.run(fb, st, kont, utc("2026-11-04", "06:16", NY))
    assert fb.wo[VT] == [] and st["bots"]["r6-vortag-usdjpy"]["open"]["dealId"] == "POS1"
    assert st["bots"]["r6-vortag-usdjpy"]["open"]["rutschen_pips"] == 0.2

    # 16:46 New York: raus
    st, neu, log, _ = rb.run(fb, st, kont, utc("2026-11-04", "16:46", NY))
    assert (VT, "POS1") in fb.closed and len(neu) == 1
    t = neu[0]
    assert t["side"] == "long" and t["entry"] == 150.512 and t["exit"] == 150.2 and t["pct"] < 0
    assert t["einstieg_kerze"] == str(pd.Timestamp("2026-11-04 11:00:00"))
    assert st["bots"]["r6-vortag-usdjpy"]["open"] is None


def test_vortag_ausgeloest_und_zwischen_zwei_laeufen_ausgestoppt(monkeypatch):
    ohne_zwilling(monkeypatch)
    vortag_usdjpy_aktiv(monkeypatch)
    fb = FakeBroker()
    monkeypatch.setattr(rb, "kerzen", lambda c, e, r, n, t: (vt_bars(t - pd.Timedelta(minutes=1)), pd.Series(dtype=float)))
    monkeypatch.setattr(rb, "entscheidung_markt", lambda *a: {"action": "none", "tag": "2026-11-04", "why": ["test"]})
    kont = {"haupt": HAUPT, "zuordnung": {}}
    st, _, _, _ = rb.run(fb, {}, kont, utc("2026-11-04", "04:31", NY))
    sell = next(w for w in fb.wo[VT] if w["direction"] == "SELL")
    fb.wo[VT].remove(sell)
    fb.activities = [
        {"epic": "USDJPY", "dateUTC": "2026-11-04T10:05:00", "source": "SYSTEM", "type": "POSITION", "status": "ACCEPTED",
         "details": {"level": 149.498, "actions": [{"actionType": "POSITION_OPENED"}]}},
        {"epic": "USDJPY", "dateUTC": "2026-11-04T10:12:00", "source": "SL", "type": "POSITION", "status": "ACCEPTED",
         "details": {"level": 149.61, "actions": [{"actionType": "POSITION_CLOSED"}]}}]
    st, neu, log, _ = rb.run(fb, st, kont, utc("2026-11-04", "05:16", NY))
    assert len(neu) == 1 and neu[0]["side"] == "short" and neu[0]["entry"] == 149.498 and neu[0]["exit"] == 149.61
    assert neu[0]["reason"] == "Stop beim Broker" and fb.wo[VT] == []
    s = st["bots"]["r6-vortag-usdjpy"]
    assert s["orders"] is None and s["tag_erledigt"] == "2026-11-04"
    st, neu, _, _ = rb.run(fb, st, kont, utc("2026-11-04", "05:31", NY))
    assert neu == [] and not [r for r in fb.requests if r[2] == "/workingorders" and r[1] == "POST"][2:]


def test_markt_bots_oeffnen_mit_stop_ziel_und_notstop(monkeypatch):
    ohne_zwilling(monkeypatch)
    fb = FakeBroker()
    monkeypatch.setattr(rb, "kerzen", lambda c, e, r, n, t: (rb.LEER, pd.Series(dtype=float)))

    def entscheidung(lauf, bot, st, state, op):
        if bot.strategie == "london_stunde_long":
            return {"action": "open", "side": 1, "tag": "2026-11-04", "stop_level": 1.2690, "ziel_r": 1.5,
                    "signal_bar": "2026-11-04 09:00:00", "erledigt": True, "why": ["test"]}
        return {"action": "open", "side": -1, "tag": "2026-11-04", "signal_bar": "2026-11-04 08:15:00",
                "tageswerte": {"atr14": 1.2}, "why": ["test"]}
    monkeypatch.setattr(rb, "entscheidung_markt", entscheidung)
    kont = {"haupt": HAUPT, "zuordnung": {}}
    st, _, log, _ = rb.run(fb, {}, kont, utc("2026-11-04", "10:01", LON))
    ld = next(r[3] for r in fb.requests if r[0] == LD and r[2] == "/positions")
    assert ld["direction"] == "BUY" and ld["stopLevel"] == 1.269 and abs(ld["profitLevel"] - 1.2740) < 1e-9
    nb = next(r[3] for r in fb.requests if r[0] == NB and r[2] == "/positions")
    assert nb["direction"] == "SELL" and nb["stopDistance"] == 2.4 and "profitLevel" not in nb
    s = st["bots"]["r6-london-gbpusd"]
    assert s["open"]["einstieg_kerze"] == "2026-11-04 10:00:00" and s["tag_erledigt"] == "2026-11-04"
    assert st["bots"]["r6-noise-usdjpy"]["open"]["einstieg_kerze"] == "2026-11-04 08:30:00"
    assert fb.account_id == HAUPT


def test_ohne_konto_wartet_der_bot_und_handelt_nirgends(monkeypatch):
    ohne_zwilling(monkeypatch)
    vortag_usdjpy_aktiv(monkeypatch)
    fb = FakeBroker(namen={HAUPT: "Account", ANDERER: "Account 1", "7777": "Account 8"})
    monkeypatch.setattr(rb, "kerzen", lambda c, e, r, n, t: (vt_bars(t - pd.Timedelta(minutes=1)), pd.Series(dtype=float)))
    kont = {"haupt": HAUPT, "zuordnung": {}}
    st, neu, log, _ = rb.run(fb, {}, kont, utc("2026-11-04", "04:31", NY))
    assert fb.requests == [] and neu == [] and kont["zuordnung"] == {}
    assert all("wartet auf ein eigenes Demokonto" in s["status"] for s in st["bots"].values())
    assert fb.account_id == HAUPT


def test_vortag_eurusd_handelt_auf_dem_zugeordneten_konto(monkeypatch):
    ohne_zwilling(monkeypatch)
    fb = FakeBroker(namen={HAUPT: "Account", ANDERER: "Account 1", "3678": "Account 6"})
    f = 1.08 / 150.0                                    # dieselben Kerzen, auf EUR/USD-Kurse umgerechnet

    def kerzen(c, e, r, n, t):
        b = vt_bars(t - pd.Timedelta(minutes=1))
        return (b * f if e == "EURUSD" else b), pd.Series(dtype=float)
    monkeypatch.setattr(rb, "kerzen", kerzen)
    kont = {"haupt": HAUPT, "zuordnung": {"anderer": ANDERER, "r6-vortag-eurusd": "3678"}}
    st, neu, log, _ = rb.run(fb, {}, kont, utc("2026-11-04", "04:31", NY))
    posts = [r for r in fb.requests if r[1] == "POST" and r[2] == "/workingorders"]
    assert len(posts) == 2 and all(r[0] == "3678" and r[3]["epic"] == "EURUSD" for r in posts)
    lang = next(r[3] for r in posts if r[3]["direction"] == "BUY")
    assert abs(lang["level"] - round(150.5 * f + 0.00002, 5)) < 1e-9
    assert st["bots"]["r6-vortag-eurusd"]["status"] == "Stop-Orders liegen"
    assert "wartet auf ein eigenes Demokonto" in st["bots"]["r6-vortag-gbpusd"]["status"]
    assert st["bots"]["r6-vortag-usdjpy"]["status"].startswith("beendet")
    assert fb.account_id == HAUPT


GB = "4094"                                             # Konto "Vortag USDJPY", geht an Vortag GBP/USD


def gbp_kerzen(c, e, r, n, t):
    b = vt_bars(t - pd.Timedelta(minutes=1))
    return (b * (1.271 / 150.0) if e == "GBPUSD" else b), pd.Series(dtype=float)


def test_beendeter_vortag_bot_loescht_orders_und_gibt_sein_konto_weiter(monkeypatch):
    """Vortag USD/JPY ist beendet (Vergleich 2025 bis heute nicht bestanden). Liegende Stop-Orders löscht er, legt keine
    neuen und gibt sein leeres Konto im selben Lauf an Vortag GBP/USD; der handelt dort sofort."""
    ohne_zwilling(monkeypatch)
    fb = FakeBroker(namen={HAUPT: "Account", ANDERER: "Account 1", GB: "Vortag USDJPY"})
    fb.wo[GB] = [{"dealId": "W1", "epic": "USDJPY", "direction": "BUY", "orderLevel": 150.51},
                 {"dealId": "W2", "epic": "USDJPY", "direction": "SELL", "orderLevel": 149.5}]
    st0 = {"bots": {"r6-vortag-usdjpy": {"orders": {"tag": "2026-11-04", "long": {"dealId": "W1"},
                                                    "short": {"dealId": "W2"}}}}}
    monkeypatch.setattr(rb, "kerzen", gbp_kerzen)
    kont = {"haupt": HAUPT, "zuordnung": {"anderer": ANDERER, "r6-vortag-usdjpy": GB},
            "konten": [{"id": "…4094", "name": "Vortag USDJPY", "fuer": "r6-vortag-usdjpy"}]}
    st, neu, log, _ = rb.run(fb, st0, kont, utc("2026-11-04", "06:46", NY))
    deletes = [r for r in fb.requests if r[1] == "DELETE"]
    assert {r[2] for r in deletes} == {"/workingorders/W1", "/workingorders/W2"} and all(r[0] == GB for r in deletes)
    assert "r6-vortag-usdjpy" not in kont["zuordnung"] and kont["zuordnung"]["r6-vortag-gbpusd"] == GB
    assert kont["uebergaben"][0]["von"] == "r6-vortag-usdjpy" and kont["uebergaben"][0]["an"] == "r6-vortag-gbpusd"
    assert kont["konten"][0]["fuer"] == "r6-vortag-gbpusd" and kont["start"][GB] == 1000.0
    alt = st["bots"]["r6-vortag-usdjpy"]
    assert alt["status"].startswith("beendet") and "an r6-vortag-gbpusd übergeben" in alt["status"]
    assert alt["konto_name"] is None and neu == []
    posts = [r for r in fb.requests if r[1] == "POST" and r[2] == "/workingorders"]
    assert len(posts) == 2 and all(r[0] == GB and r[3]["epic"] == "GBPUSD" for r in posts)
    assert st["bots"]["r6-vortag-gbpusd"]["status"] == "Stop-Orders liegen"
    assert fb.account_id == HAUPT

    # Nächster Lauf: nichts mehr beim beendeten Bot, das Konto bleibt beim Nachfolger.
    n = len(fb.requests)
    st, _, _, _ = rb.run(fb, st, kont, utc("2026-11-04", "07:01", NY))
    assert not [r for r in fb.requests[n:] if r[3] and r[3].get("epic") == "USDJPY"]
    assert kont["zuordnung"]["r6-vortag-gbpusd"] == GB and len(kont["uebergaben"]) == 1


def test_vortag_lauf_holt_verpassten_ausbruch_per_marktorder_nach(monkeypatch):
    ohne_zwilling(monkeypatch)
    vortag_usdjpy_aktiv(monkeypatch)
    fb = FakeBroker()
    fb.kurs["USDJPY"] = (150.52, 150.53)
    jetzt = utc("2026-11-04", "06:31", NY)
    monkeypatch.setattr(rb, "kerzen", lambda c, e, r, n, t: (nachhol_bars(t - pd.Timedelta(minutes=1)), pd.Series(dtype=float)))
    monkeypatch.setattr(rb, "entscheidung_markt", lambda *a: {"action": "none", "tag": "2026-11-04", "why": ["test"]})
    kont = {"haupt": HAUPT, "zuordnung": {"anderer": ANDERER}}
    st, _, log, _ = rb.run(fb, {}, kont, jetzt)
    posts = [r for r in fb.requests if r[1] == "POST" and r[2] == "/positions"]
    assert len(posts) == 1 and posts[0][0] == VT and posts[0][3]["direction"] == "BUY"
    assert not [r for r in fb.requests if r[1] == "POST" and r[2] == "/workingorders"]
    sa, _ = rg.vt_stop_abstand(nachhol_bars(jetzt).loc[:utc("2026-11-04", "04:15", NY)])
    assert posts[0][3]["stopLevel"] == round(150.5 - sa, 3) and posts[0][3]["profitLevel"] == 150.75
    op = st["bots"]["r6-vortag-usdjpy"]["open"]
    assert op["nachgeholt"] and op["einstieg_kerze"] == str(utc("2026-11-04", "06:00", NY)) and op["verspaetung_min"] == 31
    assert st["bots"]["r6-vortag-usdjpy"]["tag_erledigt"] == "2026-11-04"
    assert [e for e in log if e.get("event") == "Ausbruch nachgeholt (Marktorder)"]
    # Kurs schon am Stop: kein Nachholen, Tag erledigt
    fb2 = FakeBroker()
    fb2.kurs["USDJPY"] = (150.2, 150.21)
    st2, _, log2, _ = rb.run(fb2, {}, {"haupt": HAUPT, "zuordnung": {"anderer": ANDERER}}, jetzt)
    assert not [r for r in fb2.requests if r[1] == "POST" and r[2] == "/positions"]
    assert st2["bots"]["r6-vortag-usdjpy"]["tag_erledigt"] == "2026-11-04"


def test_vortag_stop_rueckt_auf_den_mindestabstand_des_brokers(monkeypatch):
    """Ist 0,5 x ATR enger als der Mindestabstand des Brokers, liegt der Stop bei 1,05 x Mindestabstand von der Order."""
    ohne_zwilling(monkeypatch)
    vortag_usdjpy_aktiv(monkeypatch)
    fb = FakeBroker()
    alt = fb.market

    def market(epic):
        m = alt(epic)
        m["dealingRules"]["minStopOrProfitDistance"] = {"unit": "POINTS", "value": 0.22}
        return m
    fb.market = market
    jetzt = utc("2026-11-04", "04:31", NY)
    monkeypatch.setattr(rb, "kerzen", lambda c, e, r, n, t: (vt_bars(t - pd.Timedelta(minutes=1)), pd.Series(dtype=float)))
    monkeypatch.setattr(rb, "entscheidung_markt", lambda *a: {"action": "none", "tag": "2026-11-04", "why": ["test"]})
    kont = {"haupt": HAUPT, "zuordnung": {"anderer": ANDERER}}
    st, _, log, _ = rb.run(fb, {}, kont, jetzt)
    posts = [r[3] for r in fb.requests if r[1] == "POST" and r[2] == "/workingorders"]
    lang = next(p for p in posts if p["direction"] == "BUY")
    kurz = next(p for p in posts if p["direction"] == "SELL")
    assert lang["stopLevel"] == round(150.51 - 0.231, 3) and kurz["stopLevel"] == round(149.5 + 0.231, 3)
    assert lang["profitLevel"] == 150.75 and kurz["profitLevel"] == 149.25
    gelegt = [e for e in log if e.get("event") == "Stop-Orders gelegt"]
    assert gelegt and gelegt[0]["stop_erweitert"]["min_dist"] == 0.22


def test_beendeter_vortag_bot_fuehrt_offene_position_zu_ende(monkeypatch):
    """Mit offener Position bleibt das Konto beim alten Bot, bis sie zu ist (hier um 16:46 New York); dann geht es weiter."""
    ohne_zwilling(monkeypatch)
    fb = FakeBroker(namen={HAUPT: "Account", ANDERER: "Account 1", GB: "Vortag USDJPY"})
    fb.pos[GB] = [{"market": {"epic": "USDJPY"}, "position": {"dealId": "POS1", "direction": "BUY", "size": 1000,
                                                             "level": 150.512, "createdDateUTC": "2026-11-04T11:07:12"}}]
    op = {"dealId": "POS1", "side": 1, "tag": "2026-11-04", "signal_bar": None, "einstieg_kerze": "2026-11-04 11:00:00",
          "entry": 150.512, "stop_level": 150.4, "ziel_level": 150.75, "size": 1000, "lot": 1, "currency": "JPY",
          "eur_rate": 170.0, "opened_utc": "2026-11-04 11:07:12", "konto_kurz": "…4094"}
    monkeypatch.setattr(rb, "kerzen", gbp_kerzen)
    kont = {"haupt": HAUPT, "zuordnung": {"r6-vortag-usdjpy": GB}}
    st, neu, _, _ = rb.run(fb, {"bots": {"r6-vortag-usdjpy": {"open": op}}}, kont, utc("2026-11-04", "10:01", NY))
    assert neu == [] and kont["zuordnung"] == {"r6-vortag-usdjpy": GB}
    assert "Position läuft noch zu Ende" in st["bots"]["r6-vortag-usdjpy"]["status"]
    assert not [r for r in fb.requests if r[1] == "POST"]
    st, neu, _, _ = rb.run(fb, st, kont, utc("2026-11-04", "16:46", NY))
    assert (GB, "POS1") in fb.closed and len(neu) == 1 and neu[0]["bot"] == "r6-vortag-usdjpy"
    assert kont["zuordnung"] == {"r6-vortag-gbpusd": GB}
    assert not [r for r in fb.requests if r[1] == "POST" and r[2] == "/workingorders"]   # nach 16:00 keine neuen


# ---------------------------------------------------------------------------------------------------------------------
# Automatischer Wechsel nach 15/40 Demo-Trades (suche/demo_pruefung.py, journal/konten.json["abgeloest"])

def test_ende_fuer_beendet_und_abgeloest():
    assert rb.ende_fuer("r6-vortag-usdjpy", {})["an"] == "r6-vortag-gbpusd"
    kont = {"abgeloest": {"r6-noise-usdjpy": {"an": None, "grund": "nach 15 Trades Gewinnfaktor 0,40 unter 0,6"}}}
    e = rb.ende_fuer("r6-noise-usdjpy", kont)
    assert e == {"an": None, "status": "abgelöst (nach 15 Trades Gewinnfaktor 0,40 unter 0,6)"}
    assert rb.ende_fuer("r6-london-gbpusd", kont) is None


def test_konto_fuer_nimmt_nie_ein_freies_konto():
    """Ein freies Konto (abgelöst ohne Nachfolger) vergibt nur die Prüfung, nie ein Bot über seinen Namen."""
    acc = accounts({HAUPT: "Account", NB: "Noise USDJPY", VT: "Vortag USDJPY"})
    kont = {"zuordnung": {}, "frei": [NB, VT]}
    assert rb.konto_fuer(rb.NOISE, acc, kont, HAUPT, lambda a: True) is None
    assert rb.konto_fuer(rb.VORTAG, acc, kont, HAUPT, lambda a: True) is None
    assert rb.konto_fuer(rb.NOISE, acc, {"zuordnung": {}}, HAUPT, lambda a: True) == NB


def test_abgeloester_noise_bot_fuehrt_position_zu_ende_und_gibt_das_konto_frei(monkeypatch):
    """Abgelöst ohne Nachfolger: kein neuer Trade, die offene Position läuft nach den Noise-Regeln weiter (hier bis zum
    Gegensignal), danach kommt das leere Konto in kont["frei"] und bleibt dort, auch bei neuen Signalen."""
    ohne_zwilling(monkeypatch)
    fb = FakeBroker()
    fb.pos[NB] = [{"market": {"epic": "USDJPY"}, "position": {"dealId": "POS9", "direction": "SELL", "size": 1000,
                                                             "level": 149.8, "createdDateUTC": "2026-11-04T08:31:00"}}]
    op = {"dealId": "POS9", "side": -1, "tag": "2026-11-04", "signal_bar": "2026-11-04 08:15:00",
          "einstieg_kerze": "2026-11-04 08:30:00", "entry": 149.8, "stop_level": 152.2, "ziel_level": None,
          "notstop": True, "size": 1000, "lot": 1, "currency": "JPY", "eur_rate": 170.0,
          "opened_utc": "2026-11-04T08:31:00", "konto_kurz": "…9003"}
    monkeypatch.setattr(rb, "kerzen", lambda c, e, r, n, t: (rb.LEER, pd.Series(dtype=float)))
    antwort = {"r6-noise-usdjpy": {"action": "none", "tag": "2026-11-04", "why": ["Position läuft"]}}

    def entscheidung(lauf, bot, st, state, op):
        if bot.bot_id == "r6-noise-usdjpy":
            return antwort["r6-noise-usdjpy"] if op else {"action": "open", "side": 1, "tag": "2026-11-04",
                                                          "signal_bar": "2026-11-04 13:00:00",
                                                          "tageswerte": {"atr14": 1.2}, "why": ["test"]}
        return {"action": "none", "tag": "2026-11-04", "why": ["test"]}
    monkeypatch.setattr(rb, "entscheidung_markt", entscheidung)
    grund = "nach 15 Trades Gewinnfaktor 0,40 unter 0,6"
    kont = {"haupt": HAUPT, "zuordnung": {"r6-noise-usdjpy": NB},
            "abgeloest": {"r6-noise-usdjpy": {"an": None, "seit": "2026-12-15T10:00:00+00:00", "grund": grund}},
            "konten": [{"id": "…9003", "name": "Noise USDJPY", "fuer": "r6-noise-usdjpy"}]}
    st0 = {"bots": {"r6-noise-usdjpy": {"open": op}}}
    st, neu, _, _ = rb.run(fb, st0, kont, utc("2026-12-15", "11:01", LON))
    s = st["bots"]["r6-noise-usdjpy"]
    assert neu == [] and s["open"]["dealId"] == "POS9" and kont["zuordnung"]["r6-noise-usdjpy"] == NB
    assert s["status"] == f"abgelöst ({grund}); Position läuft noch zu Ende"
    assert not [r for r in fb.requests if r[0] == NB and r[1] == "POST"]

    antwort["r6-noise-usdjpy"] = {"action": "close", "reason": "gegensignal", "tag": "2026-11-04", "why": ["test"]}
    st, neu, log, _ = rb.run(fb, st, kont, utc("2026-12-15", "11:16", LON))
    assert (NB, "POS9") in fb.closed and len(neu) == 1 and neu[0]["bot"] == "r6-noise-usdjpy"
    assert "r6-noise-usdjpy" not in kont["zuordnung"] and kont["frei"] == [NB]
    u = kont["uebergaben"][-1]
    assert u["von"] == "r6-noise-usdjpy" and u["an"] is None and kont["konten"][0]["fuer"] is None
    s = st["bots"]["r6-noise-usdjpy"]
    assert s["status"] == f"abgelöst ({grund}); Konto freigegeben" and s["konto_id"] is None
    assert any(e.get("event") == "konto frei" for e in log)
    assert not [r for r in fb.requests if r[0] == NB and r[1] == "POST"]

    # Neues Signal danach: nichts, weder auf dem alten Konto noch anderswo; das Konto bleibt frei.
    n = len(fb.requests)
    st, neu, _, _ = rb.run(fb, st, kont, utc("2026-12-15", "13:16", LON))
    assert neu == [] and not [r for r in fb.requests[n:] if r[1] == "POST"] and kont["frei"] == [NB]
    assert st["bots"]["r6-noise-usdjpy"]["status"] == f"abgelöst ({grund}); Konto freigegeben"
    assert fb.account_id == HAUPT


def test_abgeloester_london_bot_gibt_sein_leeres_konto_an_den_nachfolger(monkeypatch):
    """Abgelöst mit Nachfolger und ohne offene Position: kein neuer Trade trotz Signal, das Konto geht im selben Lauf an
    den Nachfolger."""
    ohne_zwilling(monkeypatch)
    fb = FakeBroker()
    monkeypatch.setattr(rb, "kerzen", lambda c, e, r, n, t: (rb.LEER, pd.Series(dtype=float)))

    def entscheidung(lauf, bot, st, state, op):
        if bot.strategie == "london_stunde_long":
            return {"action": "open", "side": 1, "tag": "2026-11-04", "stop_level": 1.2690, "ziel_r": 1.5,
                    "signal_bar": "2026-11-04 09:00:00", "erledigt": True, "why": ["test"]}
        return {"action": "none", "tag": "2026-11-04", "why": ["test"]}
    monkeypatch.setattr(rb, "entscheidung_markt", entscheidung)
    kont = {"haupt": HAUPT, "zuordnung": {"r6-london-gbpusd": LD},
            "abgeloest": {"r6-london-gbpusd": {"an": "us100-ruecksetzer", "grund": "nach 40 Trades Gewinnfaktor 0,85"}}}
    st, neu, log, _ = rb.run(fb, {}, kont, utc("2026-11-04", "10:01", LON))
    assert not [r for r in fb.requests if r[0] == LD and r[1] == "POST"] and neu == []
    assert kont["zuordnung"].get("us100-ruecksetzer") == LD and "r6-london-gbpusd" not in kont["zuordnung"]
    assert kont.get("frei") is None and kont["uebergaben"][-1]["an"] == "us100-ruecksetzer"
    s = st["bots"]["r6-london-gbpusd"]
    assert s["status"].startswith("abgelöst (nach 40 Trades") and s["status"].endswith("an us100-ruecksetzer übergeben")
    assert any(e.get("event") == "konto übergeben" for e in log)
    assert fb.account_id == HAUPT


def test_abgeloester_vortag_bot_ohne_nachfolger_loescht_orders_und_gibt_frei(monkeypatch):
    ohne_zwilling(monkeypatch)
    fb = FakeBroker(namen={HAUPT: "Account", "3678": "Account 6"})
    fb.wo["3678"] = [{"dealId": "W1", "epic": "EURUSD", "direction": "BUY", "orderLevel": 1.0836},
                     {"dealId": "W2", "epic": "EURUSD", "direction": "SELL", "orderLevel": 1.0764}]
    st0 = {"bots": {"r6-vortag-eurusd": {"orders": {"tag": "2026-11-04", "long": {"dealId": "W1"},
                                                    "short": {"dealId": "W2"}}}}}
    f = 1.08 / 150.0
    monkeypatch.setattr(rb, "kerzen", lambda c, e, r, n, t: (vt_bars(t - pd.Timedelta(minutes=1)) * f,
                                                              pd.Series(dtype=float)))
    kont = {"haupt": HAUPT, "zuordnung": {"r6-vortag-eurusd": "3678"},
            "abgeloest": {"r6-vortag-eurusd": {"an": None, "grund": "nach 15 Trades Gewinnfaktor 0,50 unter 0,6"}}}
    st, neu, _, _ = rb.run(fb, st0, kont, utc("2026-11-04", "06:46", NY))
    assert {r[2] for r in fb.requests if r[1] == "DELETE"} == {"/workingorders/W1", "/workingorders/W2"}
    assert not [r for r in fb.requests if r[1] == "POST"] and neu == []
    assert kont["frei"] == ["3678"] and "r6-vortag-eurusd" not in kont["zuordnung"]
    assert st["bots"]["r6-vortag-eurusd"]["status"].endswith("; Konto freigegeben")
    assert fb.account_id == HAUPT


def test_cockpit_fasst_zusammen():
    trades = [{"bot": "r6-vortag-usdjpy", "pct": 0.2, "pnl_eur": 3.0}, {"bot": "r6-vortag-usdjpy", "pct": -0.1, "pnl_eur": -1.5}]
    zwl = [{"strategie": "vortag_stop_oco", "markt": "EURUSD", "trades": [{"pct": 0.1, "zaehlt": True}]}]
    c = rb.cockpit({"bots": {}}, trades, zwl)
    assert c["bots"][0]["zusammenfassung"]["pf"] == 2.0 and c["schatten"][0]["zusammenfassung"]["trades"] == 1
