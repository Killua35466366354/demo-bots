"""Eine Woche live (suche/VORAB_eine_woche.yaml, Fassung B des Gerichts, Kirons Ja vom 06.11.2026 10:25 UTC).

Neue Marker, die einen Demo-Bot stoppen (abgeloest in suche/demo_bots.yaml, BEENDET in suche/r6_bots.py), brauchen ein
Datum "seit" frühestens am Tag 7 des Bots oder Kirons eigenes datiertes Wort. Läuft nur bei PRs und lokal (nicht im
Demo-Bots-Lauf), damit ein Fehler hier nie die Bots oder die eingefrorenen Prüfungen aufhält."""
from __future__ import annotations

import json

import pandas as pd
import yaml

from suche import demo_pruefung as dp
from suche.r6_bots import BEENDET


def _marker() -> dict[str, dict]:
    cfg = yaml.safe_load((dp.ROOT / "suche" / "demo_bots.yaml").read_text(encoding="utf-8"))
    return {**{k: dict(v or {}) for k, v in (cfg.get("abgeloest") or {}).items()},
            **{k: dict(v or {}) for k, v in BEENDET.items()}}


def test_rule_is_journaled_and_matches_the_court_wording():
    wo = dp.woche_regel()
    assert wo is not None, "Prüfsumme von VORAB_eine_woche.yaml fehlt im Protokoll"
    assert wo["tage"] == 7 and wo["nie_fuer"] == ["gold-cb"]
    assert wo["wortlaut_b"].startswith("For seven calendar days from the latest of its start_utc")
    assert dp.regel() is not None, "VORAB_wechsel.yaml muss unverändert gelten"


def test_new_stop_markers_respect_the_first_week():
    wo = dp.woche_regel()
    kont = json.loads((dp.J / "konten.json").read_text(encoding="utf-8")) if (dp.J / "konten.json").exists() else {}
    ab = pd.Timestamp(wo["ab"])
    for bot_id, m in _marker().items():
        assert m.get("seit"), f"{bot_id}: Marker ohne Datum seit"
        seit = pd.Timestamp(m["seit"])
        if seit < ab or dp.kirons_wort(m.get("grund")):
            continue                                   # vor der Regel gesetzt oder Kirons datiertes Wort
        bis = dp.woche_bis(kont, bot_id, wo, dp.start_utc(bot_id))
        assert bis is None or seit >= pd.Timestamp(bis), f"{bot_id}: Marker am {seit} vor Tag 7 ({bis})"
