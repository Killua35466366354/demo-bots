"""Tests für gold/grossbox_zwilling.py: mit Faktor 1,0 genau die Groß-Box, mit 1,25 nur der Stop weiter, Schritt für
Schritt dieselben Trades wie die Gesamtrechnung, nichts vor dem Start, nichts doppelt, nichts Neues nach dem Ende der
Zwilling-Regel, keine Order und keine fremden Dateien."""
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from gold import grossbox_bot as gb
from gold import grossbox_zwilling as gz
from gold import short_bot as sb
from gold import tiktok_schatten as ts

ROOT = Path(__file__).resolve().parents[1]


def _zufall(n=1400, seed=4):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-05 00:00", periods=n, freq="15min")
    c = 4000 + np.cumsum(rng.normal(0.15, 3, n))
    o = np.r_[4000, c[:-1]]
    h = np.maximum(o, c) + rng.uniform(0, 2, n)
    lo = np.minimum(o, c) - rng.uniform(0, 2, n)
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx), pd.Series(0.3, index=idx)


def _eintrag(start="2026-01-12T00:00:00"):
    return {"original": "gold-grossbox", "vorab": "suche/VORAB_gold_grossbox_weiter125.yaml",
            "vorab_key": gz.KEY, "start_utc": start, "konto": "schatten",
            "trades": "journal/gold-grossbox-weiter125/trades.jsonl", "pr": 0}


def _ebenen(b):
    return ts.ebene(b, "15m"), sb.fertig(ts.ebene(b, "1h"), b, "1h"), sb.fertig(ts.ebene(b, "4h"), b, "4h")


def test_faktor_eins_ist_genau_die_gross_box():
    for seed in (4, 7, 11):
        b = ts.basis(*_zufall(seed=seed))
        m15, h1, h4 = _ebenen(b)
        assert gz.gross_box_s(b, m15, h1, h4, 1.0) == ts.gross_box(b, m15, h1, h4, kerze=False)


def test_modell_wie_das_original_bis_auf_den_stop():
    b = ts.basis(*_zufall())
    orig, _ = gb.modell(b)
    orig = {t["einstieg_zeit"]: t for t in orig}
    zw = gz.modell(b)
    assert zw and gz.modell(b, 1.0) == [{k: v for k, v in t.items() if k != "_j0"} for t in orig.values()]
    gleich = [t for t in zw if t["einstieg_zeit"] in orig]
    assert len(gleich) >= 5
    for t in gleich:
        o = orig[t["einstieg_zeit"]]
        assert t["richtung"] == o["richtung"] and t["einstieg"] == o["einstieg"] and t["art"] == o["art"]
        assert abs(t["r_usd"] - 1.25 * o["r_usd"]) <= 0.02
        assert abs(abs(t["einstieg"] - t["stop"]) - t["r_usd"]) <= 0.02
        assert abs(abs(t["tp1"] - t["einstieg"]) - t["r_usd"]) <= 0.02     # erstes Drittel weiter bei 1 R


def _laeufe(bars, sp, e, schritt=4, ab=900, original=None):
    """Jede Stunde ein Lauf auf den bis dahin fertigen Kerzen, wie im Workflow."""
    st, alle_neu = {}, []
    now = None
    for k in range(ab, len(bars) + 1, schritt):
        now = (bars.index[k - 1] + pd.Timedelta("16min")).tz_localize("UTC").to_pydatetime()
        st, neu, _ = gz.step(bars.iloc[:k], sp.iloc[:k], st, now, e, original=original or [])
        alle_neu += neu
    return st, alle_neu


def test_schritt_fuer_schritt_wie_die_gesamtrechnung():
    bars, sp = _zufall()
    e = _eintrag(str(bars.index[900]))
    st, neu = _laeufe(bars, sp, e)
    voll = [t for t in gz.modell(ts.basis(bars, sp)) if pd.Timestamp(t["einstieg_zeit"]) >= bars.index[900]
            and not t["offen"]]
    assert len(neu) >= 3
    ids = [t["id"] for t in neu]
    assert len(ids) == len(set(ids))                                      # nichts doppelt
    assert all(t["opened_utc"] >= e["start_utc"].replace(" ", "T") for t in neu)   # nichts vor dem Start
    erwartet = {gz._iso(t["einstieg_zeit"]): t["ergebnis_r"] for t in voll}
    for t in neu:
        assert t["id"] in erwartet and t["r"] == erwartet[t["id"]]
    assert st["trades"] == neu and st["summe_r"] == round(sum(t["r"] for t in neu), 3)
    assert all(t["bot"] == gz.BOT_ID and t["schatten"] and "T" in t["closed_utc"] for t in neu)


def test_nach_dem_ende_nichts_neues_aber_offene_laufen_zu_ende():
    bars, sp = _zufall()
    e = _eintrag(str(bars.index[900]))
    e_end = {**e, "ende_utc": "2026-01-01T00:00:00", "ende_grund": "Test"}      # beendet: offen() ist falsch
    st, neu = _laeufe(bars, sp, e_end)
    assert neu == [] and st["offen"] == [] and st["neue_trades"] is False
    # Ein offener Trade aus dem letzten Lauf wird auch danach zu Ende gerechnet
    k = 1100
    now = (bars.index[k - 1] + pd.Timedelta("16min")).tz_localize("UTC").to_pydatetime()
    st1, _, _ = gz.step(bars.iloc[:k], sp.iloc[:k], {}, now, e, original=[])
    assert st1["offen"], "für den Test braucht es einen offenen Trade"
    st2, neu2 = st1, []
    for k2 in range(k + 4, len(bars) + 1, 4):
        now = (bars.index[k2 - 1] + pd.Timedelta("16min")).tz_localize("UTC").to_pydatetime()
        st2, n2, _ = gz.step(bars.iloc[:k2], sp.iloc[:k2], st2, now, e_end, original=[])
        neu2 += n2
    offen_ids = {gz._iso(t["einstieg_zeit"]) for t in st1["offen"]}
    assert neu2 and {t["id"] for t in neu2} <= offen_ids


def test_pause_ab_minus_25_r():
    bars, sp = _zufall()
    e = _eintrag(str(bars.index[900]))
    alt = {"trades": [{"opened_utc": "2026-01-01T00:00:00", "closed_utc": "2026-01-01T01:00:00", "r": -25.0,
                       "bot": gz.BOT_ID}], "fertig": ["2026-01-01 00:00:00"]}
    now = (bars.index[-1] + pd.Timedelta("16min")).tz_localize("UTC").to_pydatetime()
    st, neu, _ = gz.step(bars, sp, alt, now, e, original=[])
    assert neu == [] and st["offen"] == [] and st["neue_trades"] is False


def test_keine_order_und_nur_eigene_dateien(tmp_path):
    quelle = (ROOT / "gold" / "grossbox_zwilling.py").read_text(encoding="utf-8")
    for verboten in ("open_market", "create_position", "close_position", "/positions", "/workingorders", "_post(",
                     "_put(", "_delete(", "short_bot import", "grossbox_bot import"):
        assert verboten not in quelle, verboten
    assert gz.JDIR.name == gz.BOT_ID and gz.COCKPIT.name == f"{gz.BOT_ID}.json"
    assert gz.JDIR != gb.JDIR and gz.COCKPIT != gb.COCKPIT and gz.JDIR.name not in sb.GOLD_BOT_DATEIEN
    st = {"trades": [], "offen": [], "start": "x", "zwilling": {"status": "sammelt", "text": "Zwilling: 0 von 40"}}
    gz.schreiben(st, [{"bot": gz.BOT_ID, "r": 1.0}], [{"event": "fertig"}], tmp_path / "zw", tmp_path / "zw.json")
    assert sorted(p.name for p in (tmp_path / "zw").iterdir()) == ["log.jsonl", "state.json", "trades.jsonl"]
    assert json.loads((tmp_path / "zw.json").read_text(encoding="utf-8"))["konto"] == "Schatten (keine Order)"


def test_eintrag_in_der_zwillingsliste():
    liste = yaml.safe_load((ROOT / "suche" / "zwillinge.yaml").read_text(encoding="utf-8"))["zwillinge"]
    e = liste[gz.BOT_ID]
    assert e["original"] == gz.ORIGINAL and e["konto"] == "schatten" and e["vorab_key"] == gz.KEY
    assert e["vorab"] == str(gz.VORAB.relative_to(ROOT)) and e["trades"] == f"journal/{gz.BOT_ID}/trades.jsonl"
    assert isinstance(e["start_utc"], str) and "T" in e["start_utc"]
