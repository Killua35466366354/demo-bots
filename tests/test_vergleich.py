"""Vergleich der Demo-Profite und Aufstiegs-Check (suche/vergleich.py, suche/VORAB_aufstieg.yaml)."""
import json
from datetime import datetime, timezone

import pandas as pd
import yaml

from suche import vergleich as vg

REGEL = yaml.safe_load(open("suche/VORAB_aufstieg.yaml", encoding="utf-8"))["aufstieg"]


def _t(rs):
    t0 = pd.Timestamp("2027-01-01 15:00")
    return [{"r": r, "pnl_eur": r * 2, "closed_utc": (t0 + pd.Timedelta(days=i)).isoformat()} for i, r in enumerate(rs)]


def test_rule_is_registered_in_protocol():
    assert vg.regel() == REGEL, "Prüfsumme von VORAB_aufstieg.yaml fehlt im Protokoll oder ist veraltet"


def test_kennzahlen_drawdown_and_profit_factor():
    z = vg.kennzahlen(_t([1, -1, -1, 2, -0.5]))
    assert z["trades"] == 5 and z["gewonnen"] == 2 and z["summe_r"] == 0.5
    assert z["pf_r"] == round(3 / 2.5, 2) and z["rueckgang_r"] == 2.0 and z["eur"] == 1.0
    assert vg.kennzahlen(_t([1, 2]))["pf_r"] is None          # ohne Verlust: hoch


def test_single_needs_40_trades_and_all_hurdles():
    e = REGEL["einzeln"]
    assert vg.pruefe(_t([1] * 39), e, 3)["status"] == "sammelt"
    gut = [1.0, -1.0, 1.0] * 14                                  # 42 Trades, Gewinnfaktor 2
    assert vg.pruefe(_t(gut), e, 6)["status"] == "reif"
    p = vg.pruefe(_t(gut), e, 0.5)
    assert p["status"] == "nicht_reif" and "Rückgang" in p["text"]
    spaet_schlecht = [1.0] * 25 + [-1.0, -1.0, 0.5] * 5         # vorne Glück, die neuere Hälfte verliert
    p = vg.pruefe(_t(spaet_schlecht), e, 30)
    assert p["status"] == "nicht_reif" and "neuere Hälfte" in p["text"]
    p = vg.pruefe(_t([1.0, -1.0] * 20), e, 30)                    # Gewinnfaktor 1,0
    assert p["status"] == "nicht_reif" and "Gewinnfaktor" in p["text"]


def test_kombi_needs_60_trades():
    k = REGEL["kombi"]
    assert vg.pruefe(_t([1.0, -1.0, 1.0] * 19), k)["status"] == "sammelt"      # 57 Trades
    assert vg.pruefe(_t([1.0, -1.0, 1.0] * 20), k)["status"] == "reif"


def test_report_ranks_live_bots_and_kombi_only_holds_kept_strategies():
    v = vg.vergleich(datetime(2026, 11, 7, 8, 0, tzinfo=timezone.utc))
    aus = yaml.safe_load(open("suche/auswahl.yaml", encoding="utf-8"))["auswahl"]
    ids = [b["id"] for b in v["rangliste"]]
    zu = json.load(open("journal/konten.json", encoding="utf-8")).get("zuordnung") or {}
    # Eine neu behaltene Strategie steht erst in der Rangliste, wenn ersatz() ihr ein Konto gegeben hat (nächster Lauf).
    assert vg.GOLD in ids and {b for b in aus["behalten"] if b in zu} <= set(ids)
    assert [b["rang"] for b in v["rangliste"]] == list(range(1, len(ids) + 1))
    aktiv = [b["aktiv"] for b in v["rangliste"]]
    assert aktiv == sorted(aktiv, reverse=True)                 # aktive Bots zuerst
    assert set(v["kombi"]["mitglieder"]) | {d["id"] for d in v["kombi"]["draussen"]} <= set(aus["behalten"])
    assert v["regel_aufstieg"] == "festgelegt"
    assert all(b["aufstieg"]["status"] in ("sammelt", "nicht_reif", "reif") for b in v["rangliste"]
               if b["aktiv"] and b["gruppe"] != "messung")
    # Mess-Zeile "Gold nur Long" (suche/VORAB_messbots.yaml): nur C-Trades, nie ein Aufstieg, nie in der Kombi
    gl = next(b for b in v["rangliste"] if b["id"] == vg.GOLD_LONG)
    g = next(b for b in v["rangliste"] if b["id"] == vg.GOLD)
    assert gl["gruppe"] == "messung" and gl["aufstieg"]["status"] == "messung" and gl["ist"]["trades"] <= g["ist"]["trades"]
    assert vg.GOLD_LONG not in v["kombi"]["mitglieder"]
    assert vg.GOLD_START == "2026-11-03T09:05:00"               # fürs Urteil zählt nur die jetzige Regel (1-ATR-Stop)
    assert all(b["aufstieg"] is None for b in v["rangliste"] if not b["aktiv"])
    assert "| # | Strategie |" in vg.text(v) and v["tag"] == "2026-11-07"


def test_wunsch_bots_stehen_in_eigener_gruppe_und_nie_in_rangliste_oder_kombi():
    from suche import mitnutzer as mn
    v = vg.vergleich(datetime(2026, 11, 11, 8, 0, tzinfo=timezone.utc))
    w = {b["id"]: b for b in v["wunsch"]}
    assert set(w) == {b["bot"] for b in mn.aktive()} and v["wunsch_fehler"] is None
    assert {"pine-k5", "scalp-us100", "scalp-de40", "scalp-j225", "gold-staffel", "gold-grossbox"} <= set(w)
    assert "pine-tp3" not in w                  # seit 22.11.2026 abgeschaltet (Kirons Wort), zählt nur noch in der Gruppe
    assert not set(w) & {b["id"] for b in v["rangliste"]}
    assert not set(w) & (set(v["kombi"]["mitglieder"]) | {d["id"] for d in v["kombi"]["draussen"]})
    for bid, b in w.items():
        p = vg.J / bid / "trades.jsonl"
        n = sum(1 for z in p.read_text(encoding="utf-8").splitlines() if z.strip()) if p.exists() else 0
        assert b["ist"]["trades"] <= n and b["konto"] and b["vorab"], bid
    t = vg.text(v)
    assert "## Auf Kirons Wunsch" in t and "Pine-Gold Hand auf Account 5" in t and "suche/VORAB_scalping_opens.yaml" in t
    assert "Der Gold-Bot zählt hier ab 2026-11-03 09:05 UTC" in t
    # die Dateien hängen weiter nur vom Tag und den Trades ab, nicht von der Uhrzeit des Laufs
    assert vg.vergleich(datetime(2026, 11, 11, 20, 0, tzinfo=timezone.utc)) == v


def test_wunsch_gruppe_haelt_den_vergleich_nie_auf(monkeypatch):
    from suche import mitnutzer as mn

    def kaputt():
        raise RuntimeError("Bot-Code fehlt")
    monkeypatch.setattr(mn, "aktive", kaputt)
    v = vg.vergleich(datetime(2026, 11, 11, 8, 0, tzinfo=timezone.utc))
    assert v["wunsch"] == [] and "nicht lesbar" in v["wunsch_fehler"] and v["rangliste"]
    assert "ließ sich nicht lesen" in vg.text(v)


def test_bots_ohne_stop_zaehlen_in_prozent():
    # Nikkei-Scalper (scalp-j225): kein Stop, darum kein R, nur Prozent vom Kurs; vorher stand er mit 0 Trades da
    ohne_r = [{"pct": 0.03, "pnl_eur": 0.01, "closed_utc": "2026-11-12T06:33:30"},
              {"pct": -0.05, "closed_utc": "2026-11-13T06:33:30"}, {"pct": None, "opened_utc": "2026-11-14T06:00:00"}]
    assert vg._einheit(ohne_r) == "pct"
    z = vg.kennzahlen(ohne_r, "pct")
    assert z["trades"] == 2 and z["summe_r"] == -0.02 and z["pf_r"] == 0.6 and z["gewonnen"] == 1
    mit_r = [{"r": -1.0, "pct": -0.3, "closed_utc": "2026-11-11T09:18:36"}, {"pct": 0.1, "closed_utc": "2026-11-12"}]
    assert vg._einheit(mit_r) == "r" and vg._einheit([]) == "r"
    v = vg.vergleich(datetime(2026, 11, 14, 8, 0, tzinfo=timezone.utc))
    assert all(b["einheit"] in ("R", "%") for b in v["wunsch"])


# ---- Aufstieg für alle Bots (suche/VORAB_aufstieg_alle.yaml, Kirons Wahl vom 18.11.2026 "2 Monate und 100 Trades") ----
ALLE = yaml.safe_load(open("suche/VORAB_aufstieg_alle.yaml", encoding="utf-8"))["aufstieg_alle"]
Z = ALLE["zeit"]
START = "2027-01-01"                                             # erster Trade von _t()
TAG = pd.Timestamp("2027-04-20")                                 # 109 Tage nach START, alle Trades von _t() bis 102 davor


def _td(paare):
    """Trades als (R, Tag nach START)."""
    t0 = pd.Timestamp("2027-01-01 15:00")
    return [{"r": r, "closed_utc": (t0 + pd.Timedelta(days=d)).isoformat()} for r, d in paare]


def test_regel_alle_ist_versiegelt_und_haelt_kirons_wahl():
    assert vg.regel_alle() == ALLE, "Prüfsumme von VORAB_aufstieg_alle.yaml fehlt im Protokoll oder ist veraltet"
    assert vg.regel() == REGEL                                   # die alte Datei bleibt versiegelt und unverändert
    for teil, pf in (("einzeln_kern", 1.2), ("einzeln", 1.3), ("kombi", 1.2), ("gruppe", 1.3)):
        assert ALLE[teil]["ab_trades"] == 100 and ALLE[teil]["pf_mindestens"] == pf, teil
        assert ALLE[teil]["zweite_haelfte_pf_mindestens"] == 1.0 and ALLE[teil]["summe_r_ueber"] == 0, teil
    assert Z["mindestens_tage"] == 61 and Z["letzte_tage"] == 61 and Z["summe_letzte_tage_ueber"] == 0
    aus = yaml.safe_load(open("suche/auswahl.yaml", encoding="utf-8"))["auswahl"]
    assert set(ALLE["kern"]) == set(aus["behalten"])              # genau die sechs Kern-Bots
    assert set(ALLE["kern"]) <= set(ALLE["gruppe"]["mitglieder"])
    assert set(ALLE["gruppe"]["gold"]) <= set(ALLE["gruppe"]["mitglieder"])
    mess = set(json.load(open("journal/konten.json", encoding="utf-8")).get("messung") or {})
    assert not mess & set(ALLE["gruppe"]["mitglieder"]) and vg.GOLD_LONG not in ALLE["gruppe"]["mitglieder"]


def test_einzeln_braucht_100_trades_und_61_tage():
    e = ALLE["einzeln"]
    gut = [1.0, -1.0, 1.0] * 34                                  # 102 Trades, Gewinnfaktor 2
    p = vg.pruefe(_t(gut[:99]), e, None, "r", Z, START, TAG)
    assert p["status"] == "sammelt" and p["text"] == "99 von 100 Demo-Trades, 109 von 61 Tagen"
    assert vg.pruefe(_t(gut), e, None, "r", Z, START, TAG)["status"] == "reif"
    p = vg.pruefe(_t(gut), e, None, "r", Z, "2027-02-19", TAG)    # 100 Trades, aber erst 60 Tage
    assert p["status"] == "sammelt" and p["text"] == "102 von 100 Demo-Trades, 60 von 61 Tagen"
    assert vg.pruefe(_t(gut), e, None, "r", Z, "2027-02-18", TAG)["status"] == "reif"   # genau 61 Tage reichen
    assert vg.pruefe(_t(gut), e, None, "r", Z, None, TAG)["status"] == "sammelt"         # ohne Start kein Aufstieg


def test_kern_braucht_1_2_alle_anderen_1_3():
    knapp = [1.25, -1.0] * 51                                    # 102 Trades, Gewinnfaktor 1,25
    assert vg.pruefe(_t(knapp), ALLE["einzeln_kern"], 30, "r", Z, START, TAG)["status"] == "reif"
    p = vg.pruefe(_t(knapp), ALLE["einzeln"], 30, "r", Z, START, TAG)
    assert p["status"] == "nicht_reif" and "unter 1.3" in p["text"]


def test_die_letzten_61_tage_muessen_im_plus_sein():
    e = ALLE["einzeln"]
    gut = list(zip([1.0, -1.0, 1.0] * 34, range(102)))           # Tag 0 bis 101, Gewinnfaktor 2
    spaet = gut + [(-1.0, 150), (-1.0, 151), (-1.0, 152)]         # danach nur noch drei Verluste
    tag = pd.Timestamp("2027-06-20")                             # 170 Tage nach START, die letzten 61 ab Tag 109
    p = vg.pruefe(_td(spaet), e, None, "r", Z, START, tag)
    assert p["status"] == "nicht_reif" and p["text"] == "letzte 61 Tage -3.00 R nicht über 0"
    p = vg.pruefe(_td(gut), e, None, "r", Z, START, tag)           # gar kein Trade in den letzten 61 Tagen
    assert p["status"] == "nicht_reif" and "letzte 61 Tage +0.00 R" in p["text"]
    assert vg.pruefe(_td(spaet + [(4.0, 160)]), e, None, "r", Z, START, tag)["status"] == "reif"
    assert vg.pruefe(_td(spaet), e)["status"] == "reif"          # die alte Regel ohne Zeit hätte ihn durchgelassen


def test_einzeln_rechnet_auch_in_prozent():
    t0 = pd.Timestamp("2027-01-01 15:00")
    tr = [{"pct": x, "r": None, "closed_utc": (t0 + pd.Timedelta(days=i)).isoformat()}
          for i, x in enumerate([0.4, -0.2, 0.3] * 34)]
    assert vg.pruefe(tr, ALLE["einzeln"], None, "pct", Z, START, TAG)["status"] == "reif"
    assert vg.pruefe(tr, ALLE["einzeln"], None, "r", Z, START, TAG)["status"] == "sammelt"  # ohne R zählt er in R nicht


def _g(**mitglieder):
    g = dict(ALLE["gruppe"])
    g["mitglieder"] = list(mitglieder)
    g["gold"] = [m for m in mitglieder if m.startswith("gold")]
    return g, {m: _t(rs) for m, rs in mitglieder.items()}


def test_gruppe_braucht_100_trades_61_tage_und_nicht_nur_ein_starkes_mitglied():
    g, tr = _g(a=[1.0, -1.0, 1.0] * 20, b=[1.0, -1.0, 1.0] * 14)          # 102 Trades, beide gut
    p = vg.pruefe_gruppe(tr, g, Z, START, TAG)
    assert p["aufstieg"]["status"] == "reif" and p["ist"]["trades"] == 102 and not p["draussen"]
    assert vg.pruefe_gruppe(tr, g, Z, "2027-03-01", TAG)["aufstieg"]["status"] == "sammelt"   # erst 50 Tage
    g, tr = _g(a=[1.0, -1.0, 1.0] * 20, b=[1.0, -1.0, 1.0] * 13)          # 99 Trades
    assert vg.pruefe_gruppe(tr, g, Z, START, TAG)["aufstieg"]["status"] == "sammelt"
    # a trägt alles, b verliert (Gewinnfaktor 0,81, bleibt drin, weil unter 20 Trades): ohne a nicht über 1,0
    g, tr = _g(a=[3.0, -1.0] * 45, b=[0.9, -1.0] * 9 + [-1.0])
    p = vg.pruefe_gruppe(tr, g, Z, START, TAG)
    assert p["bestes"] == "a" and p["aufstieg"]["status"] == "nicht_reif" and "ohne ihr bestes Mitglied" in p["aufstieg"]["text"]


def test_gruppe_mitglied_faellt_heraus_und_dann_gilt_1_4():
    schwach = [1.0, -1.0, -1.0] * 8                                          # 24 Trades, Gewinnfaktor 0,5
    g, tr = _g(a=[1.35, -1.0] * 30, b=[1.35, -1.0] * 30, c=schwach)          # Rest: Gewinnfaktor 1,35
    p = vg.pruefe_gruppe(tr, g, Z, START, TAG)
    assert [d["id"] for d in p["draussen"]] == ["c"] and p["mitglieder"] == ["a", "b"]
    assert p["aufstieg"]["status"] == "nicht_reif" and "unter 1.4" in p["aufstieg"]["text"]
    g, tr = _g(a=[1.35, -1.0] * 30, b=[1.35, -1.0] * 30)                     # ohne Ausfall reicht 1,35
    assert vg.pruefe_gruppe(tr, g, Z, START, TAG)["aufstieg"]["status"] == "reif"
    g, tr = _g(a=[1.25, -1.0] * 30, b=[1.25, -1.0] * 30)                     # 1,25 reicht der Gruppe nie
    assert vg.pruefe_gruppe(tr, g, Z, START, TAG)["aufstieg"]["status"] == "nicht_reif"


def test_gruppe_zaehlt_alle_gold_bots_als_ein_mitglied():
    gold = [2.0, -1.0] * 25                                                  # je 50 Trades, +25 R
    rest = [1.0, -1.05] * 25                                                 # 50 Trades, knapp unter 1,0
    g, tr = _g(gold_a=gold, gold_b=gold, x=rest)
    p = vg.pruefe_gruppe(tr, g, Z, START, TAG)
    assert p["bestes"] == "gold" and p["aufstieg"]["status"] == "nicht_reif"
    g["gold"] = []                                                           # zählten sie einzeln, bliebe Gold im Rest
    assert vg.pruefe_gruppe(tr, g, Z, START, TAG)["aufstieg"]["status"] == "reif"


def test_vergleich_nutzt_100_trades_und_61_tage_fuer_alle():
    v = vg.vergleich(datetime(2026, 11, 18, 21, 0, tzinfo=timezone.utc))
    assert v["regel_aufstieg_alle"] == "festgelegt"
    for b in v["rangliste"] + v["wunsch"]:
        if b.get("gruppe") in ("messung", "zwilling") or not b.get("aktiv", True):
            continue
        a = b["aufstieg"]
        assert a["status"] in ("sammelt", "nicht_reif", "reif"), b["id"]
        assert a["status"] != "sammelt" or ("von 100 Demo-Trades" in a["text"] and "von 61 Tagen" in a["text"]), b["id"]
    k = v["kombi"]["aufstieg"]
    assert k["status"] != "sammelt" or "von 100 Demo-Trades" in k["text"]
    g = v["gruppe"]
    assert g["fest"] == len(ALLE["gruppe"]["mitglieder"]) and g["aufstieg"]["status"] in ("sammelt", "nicht_reif", "reif")
    assert set(g["mitglieder"]) | {d["id"] for d in g["draussen"]} <= set(ALLE["gruppe"]["mitglieder"])
    t = vg.text(v)
    assert "**Gruppe aller Bots (" in t and "| Aufstieg |" in t and "61 Tage" in v["hinweis"]
    assert vg.vergleich(datetime(2026, 11, 18, 8, 0, tzinfo=timezone.utc)) == v       # hängt nur vom Tag ab


def test_ohne_siegel_der_neuen_datei_gilt_die_alte_regel(monkeypatch):
    monkeypatch.setattr(vg, "regel_alle", lambda: None)
    v = vg.vergleich(datetime(2026, 11, 18, 21, 0, tzinfo=timezone.utc))
    assert v["regel_aufstieg_alle"] == "Prüfsumme fehlt" and v["gruppe"] is None
    for b in v["rangliste"]:
        if b["aktiv"] and b["gruppe"] not in ("messung", "zwilling") and b["aufstieg"]["status"] == "sammelt":
            assert b["aufstieg"]["text"].endswith("von 40 Demo-Trades"), b["id"]
    assert v["kombi"]["aufstieg"]["status"] != "sammelt" or v["kombi"]["aufstieg"]["text"].endswith("von 60 Demo-Trades")
    assert all(b["aufstieg"]["status"] == "keine_regel" for b in v["wunsch"])
    assert "40 Trades, Kombi 60" in v["hinweis"]


def test_vortag_bots_brauchen_seit_21_11_die_hoehere_huerde():
    vt = vg.regel_vortag()
    assert vt is not None, "Prüfsumme von VORAB_aufstieg_vortag.yaml fehlt im Protokoll oder ist veraltet"
    assert set(vt["bots"]) == {"r6-vortag-eurusd", "r6-vortag-gbpusd", "r6-vortag-gbpjpy"}
    assert set(vt["bots"]) <= set(ALLE["kern"])
    assert vg.kern_bots(ALLE, vt) == {"us500-ruecksetzer", "r5-ruecksetzer-us100", "r7-nasdaq-noise-long"}
    assert vg.kern_bots(ALLE, None) == set(ALLE["kern"])           # ohne Siegel bleibt alles wie vorher
    assert vg.kern_bots(None, vt) == set()
    v = vg.vergleich(datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc))
    assert v["regel_aufstieg_vortag"] == "festgelegt" and "VORAB_aufstieg_vortag" in v["hinweis"]


def test_vergleich_gibt_den_vortag_bots_die_huerde_1_3(monkeypatch):
    gesehen = []
    echt = vg.pruefe

    def merke(trades, k, *a, **kw):
        gesehen.append(k)
        return echt(trades, k, *a, **kw)
    monkeypatch.setattr(vg, "pruefe", merke)
    monkeypatch.setattr(vg, "kern_bots", lambda rg_alle, rg_vortag: {"x"} if rg_vortag else set(rg_alle["kern"]))
    vg.vergleich(datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc))
    assert ALLE["einzeln_kern"] not in gesehen                     # kein Bot aus der Rangliste heißt "x"
    gesehen.clear()
    monkeypatch.setattr(vg, "regel_vortag", lambda: None)
    vg.vergleich(datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc))
    assert ALLE["einzeln_kern"] in gesehen                         # ohne das neue Siegel wieder 1,2 für die Kern-Bots
