"""Zwillinge: Verbesserungen laufen als eigener Bot neben dem unveränderten Original (nur Capital.com-Demo).

Regel: suche/VORAB_zwilling.yaml (gilt nur mit ihrer Prüfsumme im Protokoll). Liste: suche/zwillinge.yaml.
Dieses Modul liest nur Dateien, spricht mit keinem Broker und ändert keinen Bot:

- fehler(): prüft einen Eintrag der Liste gegen die Regel (tests/test_zwilling.py, bei jedem PR).
- stand(): wo der Zwilling steht (sammelt, früh beendet, reif für Kirons Entscheidung, nicht besser, Frist).
- offen(): darf der Zwilling noch neue Trades öffnen? Der Code eines Zwillings fragt das vor jedem neuen Trade.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from suche import demo_pruefung as dp

ROOT = Path(__file__).resolve().parents[1]
REGEL = ROOT / "suche" / "VORAB_zwilling.yaml"
KEY = "VORAB_zwilling sha256 "
LISTE = ROOT / "suche" / "zwillinge.yaml"
FELDER = ("original", "vorab", "vorab_key", "start_utc", "konto", "trades", "pr")
OFFEN = ("sammelt", "frist", "reif")    # reif: er handelt weiter, bis Kiron entscheidet


def regel() -> dict | None:
    return dp._versiegelt(REGEL, KEY, "zwilling")


def eintraege(path: Path = LISTE) -> dict:
    if not path.exists():
        return {}
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("zwillinge") or {}


def versiegelt_um(key: str, sha: str, lines: list[str] | None = None) -> str | None:
    """Zeit der ersten Protokollzeile mit dieser Prüfsumme ("- JJJJ-MM-TT HH:MM UTC: ..."), sonst None."""
    from suche.runde1 import journal_lines
    for line in lines if lines is not None else journal_lines():
        if f"{key}{sha}" in line and line.startswith("- "):
            try:
                return pd.Timestamp(line[2:22].replace(" UTC", "")).isoformat()
            except ValueError:
                return None
    return None


def _ts(x) -> pd.Timestamp | None:
    try:
        t = pd.Timestamp(str(x))
    except ValueError:
        return None
    return t.tz_localize(None) if t.tzinfo else t


def fehler(zid: str, e: dict, rg: dict, *, bots: set, mess: set, zuordnung: dict, alle: dict,
           woche_bis_original: str | None, lines: list[str] | None = None, root: Path = ROOT) -> list[str]:
    """Was an einem Eintrag der Liste gegen VORAB_zwilling.yaml verstößt (leer = in Ordnung).

    bots: IDs aller Bots mit Lauf (ohne Zwillinge), mess: Mess-Bots, zuordnung: journal/konten.json zuordnung,
    alle: die ganze Liste (für einen Zwilling je Original und einen neuen je Woche)."""
    from suche.runde1 import journal_lines, last_value
    from suche.runde3 import sha256_text
    out = [f"Feld {f} fehlt" for f in FELDER if e.get(f) in (None, "")]
    if out:
        return out
    org = e["original"]
    start = _ts(e["start_utc"])
    if start is None:
        return [f"start_utc {e['start_utc']!r} ist kein Zeitpunkt"]
    if zid == org or zid in bots:
        out.append(f"{zid} braucht eine eigene Bot-ID")
    if org not in bots:
        out.append(f"Original {org} hat keinen Bot-Lauf")
    if org in (rg.get("nie_fuer") or []) or org == dp.HAUPT_BOT:
        out.append(f"für {org} gibt es keinen Zwilling (eigener Plan)")
    if org in mess:
        out.append(f"{org} ist ein Mess-Bot, für ihn gibt es keinen Zwilling")
    vorab = root / e["vorab"]
    lines = lines if lines is not None else journal_lines()
    if not vorab.exists():
        out.append(f"{e['vorab']} fehlt")
    else:
        sha = sha256_text(vorab.read_text(encoding="utf-8"))
        if last_value(lines, e["vorab_key"]) != sha:
            out.append(f"Prüfsumme von {e['vorab']} steht nicht im Protokoll")
        else:
            um = _ts(versiegelt_um(e["vorab_key"], sha, lines))
            if um is None or um > start:
                out.append(f"{e['vorab']} wurde erst nach dem Start des Zwillings festgelegt")
    wb = _ts(woche_bis_original) if woche_bis_original else None
    if (rg.get("start") or {}).get("nach_tag_7_des_originals") and wb is not None and start < wb:
        out.append(f"Start {start} vor Tag 7 des Originals ({wb})")
    if str(e["konto"]) != "schatten":
        andere = [b for b, k in zuordnung.items() if str(k) == str(e["konto"]) and b != zid]
        if andere:
            out.append(f"Konto {e['konto']} gehört schon {', '.join(andere)}")
    je_org = (rg.get("start") or {}).get("je_original_hoechstens", 1)
    laufend = [z for z, x in alle.items() if x.get("original") == org and not x.get("ende_utc")]
    if not e.get("ende_utc") and len(laufend) > je_org:
        out.append(f"mehr als {je_org} laufender Zwilling für {org}: {', '.join(sorted(laufend))}")
    je_woche = (rg.get("start") or {}).get("neu_je_woche_hoechstens", 1)
    woche = start.isocalendar()[:2]
    gleiche = [z for z, x in alle.items() if (t := _ts(x.get("start_utc"))) is not None and t.isocalendar()[:2] == woche]
    if len(gleiche) > je_woche:
        out.append(f"mehr als {je_woche} neuer Zwilling in Kalenderwoche {woche[1]}/{woche[0]}: {', '.join(sorted(gleiche))}")
    return out


def _pf(trades: list[dict]) -> float | None:
    return dp.kennzahl(trades)["pf"]


def _pf_ok(pf: float | None, mindestens: float) -> bool:
    return pf is None or pf >= mindestens          # ohne Verlust-Trade gilt der Gewinnfaktor als hoch


def _sortiert(trades: list[dict]) -> list[dict]:
    return sorted(trades, key=lambda t: str(t.get("closed_utc") or ""))


def stand(zw: list[dict], org: list[dict], rg: dict, start: str, now, e: dict | None = None) -> dict:
    """Stand des Zwillings: zw seine Trades ab start, org die Trades des Originals ab start (je nach Schlusszeit)."""
    e = e or {}
    if e.get("ende_utc"):
        return {"status": "beendet", "text": f"beendet am {str(e['ende_utc'])[:10]}: {e.get('ende_grund') or ''}".strip()}
    zw = _sortiert([t for t in zw if t.get("r") is not None])
    org = _sortiert([t for t in org if t.get("r") is not None])
    fr, er = rg["frueh_ende"], rg["ersatz"]
    n = len(zw)
    for k in range(fr["ab_trades"], min(n, er["ab_trades"] - 1) + 1):   # früh beendet bleibt beendet
        pf = _pf(zw[:k])
        if pf is not None and pf < fr["ende_wenn_pf_unter"]:
            return {"status": "frueh_ende", "text": f"Zwilling endet: Gewinnfaktor {pf:.2f} nach {k} Trades "
                    f"unter {fr['ende_wenn_pf_unter']}", "zwilling": dp.kennzahl(zw[:k]), "original": dp.kennzahl(org)}
    if n >= er["ab_trades"]:
        z = zw[:er["ab_trades"]]                     # die ersten 40 entscheiden, damit spätere Trades nichts verschieben
        bis = str(z[-1].get("closed_utc") or "")
        o = [t for t in org if str(t.get("closed_utc") or "") <= bis]
        kz, ko = dp.kennzahl(z), dp.kennzahl(o)
        fehlt = []
        if not _pf_ok(kz["pf"], er["pf_mindestens"]):
            fehlt.append(f"Gewinnfaktor {kz['pf']:.2f} unter {er['pf_mindestens']}")
        if not _pf_ok(_pf(z[len(z) // 2:]), er["zweite_haelfte_pf_mindestens"]):
            fehlt.append(f"neuere Hälfte unter Gewinnfaktor {er['zweite_haelfte_pf_mindestens']}")
        if er.get("summe_r_hoeher_als_original") and kz["summe_r"] <= ko["summe_r"]:
            fehlt.append(f"Summe {kz['summe_r']:+.2f} R nicht über dem Original ({ko['summe_r']:+.2f} R)")
        if er.get("pf_mindestens_wie_original") and ko["trades"] and kz["pf"] is not None:
            if ko["pf"] is None:
                fehlt.append("das Original hatte im selben Zeitraum keinen Verlust-Trade")
            elif kz["pf"] < ko["pf"]:
                fehlt.append(f"Gewinnfaktor {kz['pf']:.2f} unter dem des Originals ({ko['pf']:.2f})")
        if fehlt:
            return {"status": "nicht_besser", "text": "Zwilling endet: " + "; ".join(fehlt),
                    "zwilling": kz, "original": ko}
        hinweis = " Kosten nicht live geprüft (Schatten)." if str(e.get("konto")) == "schatten" else ""
        return {"status": "reif", "text": "reif für Kirons Entscheidung über den Ersatz (nur per PR mit seinem Merge)."
                + hinweis, "zwilling": kz, "original": ko}
    kz = dp.kennzahl(zw)
    t0, jetzt = _ts(start), _ts(pd.Timestamp(now).isoformat())
    if t0 is not None and jetzt is not None and jetzt >= t0 + pd.DateOffset(months=int(rg.get("frist_monate") or 6)):
        return {"status": "frist", "text": f"{n} von {er['ab_trades']} Trades nach {rg.get('frist_monate')} Monaten, "
                "Bericht an Kiron", "zwilling": kz, "original": dp.kennzahl(org)}
    return {"status": "sammelt", "text": f"Zwilling: {n} von {er['ab_trades']} Trades", "zwilling": kz,
            "original": dp.kennzahl(org)}


def offen(st: dict) -> bool:
    """Darf der Zwilling neue Trades öffnen? Solange er sammelt, nach der Frist und reif bis zu Kirons Entscheidung."""
    return st.get("status") in OFFEN
