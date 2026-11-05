"""Sicherheitsschalter des Gold-Bots (Kritik D4, Regel in gold/bot/VORAB_sicherheit.yaml). Reiner Code ohne Netz.

Der Schalter zählt die abgeschlossenen Trades seit `start` aus journal/gold-trades.jsonl und sagt, ob der Bot neue
Einstiege pausieren muss: Summe R seit start höchstens `summe_r_hoechstens`, oder die ersten `urteil_nach_trades`
Trades bestehen das Urteil nicht (Summe R über `urteil_summe_r_ueber` und Gewinnfaktor in R mindestens
`urteil_pf_r_mindestens`). Er rechnet bei jedem Lauf neu aus dem Journal, hat also keinen eigenen Zustand, den der
Bot zurücksetzen könnte. Zurück geht es nur mit einem neuen `start`, den Kiron per PR einträgt.

Die Regel gilt nur mit ihrer Prüfsumme im Protokoll (journal/strategie-suche-protokoll.md). Fehlt sie oder passt sie
nicht, pausiert der Bot lieber, als ohne Schalter weiterzuhandeln.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
VORAB = Path(__file__).resolve().parent / "VORAB_sicherheit.yaml"
PROTOKOLL = ROOT / "journal" / "strategie-suche-protokoll.md"
KEY = "VORAB_sicherheit sha256 "


@dataclass
class Stand:
    pause: bool
    grund: str | None
    trades: int
    summe_r: float
    pf_r: float | None
    hinweise: list[str] = field(default_factory=list)

    def journal(self) -> dict:
        return {"pause": self.pause, "grund": self.grund, "trades": self.trades, "summe_r": round(self.summe_r, 2),
                "pf_r": None if self.pf_r is None else round(self.pf_r, 3), "hinweise": self.hinweise}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def gesiegelte_regel(vorab: Path = VORAB, protokoll: Path = PROTOKOLL) -> dict | None:
    """Die Regel, nur wenn die letzte Prüfsumme im Protokoll zur Datei passt. Sonst None."""
    if not vorab.exists() or not protokoll.exists():
        return None
    text = vorab.read_text(encoding="utf-8")
    sha = None
    for line in reversed(protokoll.read_text(encoding="utf-8").splitlines()):
        if KEY in line:
            sha = line.split(KEY, 1)[1].split()[0].rstrip(".,;")
            break
    if sha != _sha(text):
        return None
    return yaml.safe_load(text)["sicherheitsschalter"]


def _utc(text) -> datetime | None:
    if not text:
        return None
    try:
        t = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def lese_trades(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _pf(rs: list[float]) -> float:
    gewinn = sum(r for r in rs if r > 0)
    verlust = -sum(r for r in rs if r < 0)
    return float("inf") if verlust == 0 else gewinn / verlust


def pruefen(trades: list[dict], regel: dict | None) -> Stand:
    """Stand des Schalters für die abgeschlossenen Trades (älteste zuerst, wie im Journal)."""
    if regel is None:
        return Stand(True, "Sicherheitsschalter: Regel fehlt oder Prüfsumme passt nicht zum Protokoll, keine neuen "
                           "Einstiege bis zur Klärung", 0, 0.0, None)
    start = _utc(regel["start"])
    p = regel["pause_wenn"]
    rs, hinweise = [], []
    for t in trades:
        when = _utc(t.get("opened_utc")) or _utc(t.get("entry_bar")) or _utc(t.get("closed_utc"))
        if when is None or when < start:
            continue
        if t.get("r") is None:
            hinweise.append(f"Trade {t.get('dealId')} ohne r, zählt nicht")
            continue
        rs.append(float(t["r"]))
    summe = float(sum(rs))
    pf = _pf(rs) if rs else None
    n_urteil = int(p["urteil_nach_trades"])
    grund = None
    if summe <= float(p["summe_r_hoechstens"]):
        grund = (f"Sicherheitsschalter: Summe {summe:.2f} R seit {regel['start']} ist {p['summe_r_hoechstens']:g} R "
                 f"oder tiefer, keine neuen Einstiege bis zu Kirons Entscheidung")
    elif len(rs) >= n_urteil:
        erste = rs[:n_urteil]
        s30, pf30 = sum(erste), _pf(erste)
        if not (s30 > float(p["urteil_summe_r_ueber"]) and pf30 >= float(p["urteil_pf_r_mindestens"])):
            grund = (f"Sicherheitsschalter: Urteil nach {n_urteil} Trades nicht bestanden (Summe {s30:.2f} R, "
                     f"Gewinnfaktor {pf30:.2f}), keine neuen Einstiege bis zu Kirons Entscheidung")
    return Stand(grund is not None, grund, len(rs), summe, pf, hinweise)
