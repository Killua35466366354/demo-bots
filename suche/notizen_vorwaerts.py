"""Vorwärts-Zählung des Kandidaten ausbruch4h_welt_ziel_1r (Kirons Wahl vom 19.11.2026), ohne Bot und ohne Order.

Regeln: suche/VORAB_notizen_vorwaerts.yaml, die Fassung selbst aus suche/VORAB_notizen_runde.yaml (beide Siegel
werden geprüft). Gezählt werden nur Einstiege ab dem 20.11.2026 auf Kerzen, die es beim Siegel noch nicht gab.

Aufruf:
    python -m suche.notizen_vorwaerts --festlegen            schreibt die Prüfsumme der Regeldatei ins Protokoll
    python -m suche.notizen_vorwaerts zaehlen <Arbeit>       zählt mit den Kursdateien im Arbeitsordner
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import yaml

from suche import notizen_runde as nr
from suche import rueckblick as rb
from suche.runde1 import journal_add, journal_lines, last_value, sha256_text

ROOT = pathlib.Path(__file__).resolve().parents[1]
VORAB = ROOT / "suche" / "VORAB_notizen_vorwaerts.yaml"
KEY = "VORAB_notizen_vorwaerts sha256 "
ERGEBNIS = ROOT / "suche" / "ergebnis_notizen_vorwaerts"


def lade_vorab(pruefen: bool = True) -> tuple[dict, dict]:
    text = VORAB.read_text(encoding="utf-8")
    if pruefen and last_value(journal_lines(), KEY) != sha256_text(text):
        raise SystemExit("VORAB_notizen_vorwaerts.yaml passt nicht zur Prüfsumme im Protokoll.")
    v = yaml.safe_load(text)["notizen_vorwaerts"]
    cfg = nr.lade_vorab(pruefen=pruefen)
    cfg["varianten"] = {v["fassung"]: cfg["varianten"][v["fassung"]]}
    return v, cfg


def urteil(e: dict, v: dict, letzter_tag: str) -> str:
    u = v["urteil_40"]
    n, gf, rob, summe = e.get("trades", 0), e.get("gewinnfaktor"), e.get("gewinnfaktor_robust"), e.get("summe_R", 0)
    if n < u["trades"]:
        return "verworfen (Frist)" if letzter_tag > v["frist"] else "zählt weiter"
    gut = gf is not None and gf >= 1.2 and rob is not None and rob >= 1.0 and summe > 0
    if gut:
        return "bestanden"
    if (gf is not None and gf < 1.0) or summe <= 0:
        return "verworfen"
    return "zählt weiter bis 100" if n < 100 else "verworfen"


def zaehle(arbeit: pathlib.Path, v: dict, cfg: dict) -> dict:
    sym = cfg["varianten"][v["fassung"]]["maerkte"]
    letzter = min(str(np.load(arbeit / f"{s}.npz")["t"].max())[:10] for s in sym)
    fenster = (v["zaehlt_ab"], letzter)
    erg, tr = nr.rechne(arbeit, cfg, None, fenster, v["zaehlt_ab"], mit_zwillingen=False)
    e = erg[v["fassung"]]
    e["fenster"] = {"von": fenster[0], "bis": fenster[1]}
    e["urteil_vorwaerts"] = urteil(e, v, letzter)
    for k in ("urteil", "durchgefallen_bei", "holm", "haelfte_1", "haelfte_2", "jahr_2026"):
        e.pop(k, None)                                       # Hürden der Rückschau gelten hier nicht
    return {"erg": e, "trades": tr}


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--festlegen":
        zeile = KEY + sha256_text(VORAB.read_text(encoding="utf-8"))
        journal_add(zeile)
        print(zeile)
        return 0
    if len(argv) != 2 or argv[0] != "zaehlen":
        raise SystemExit(__doc__)
    v, cfg = lade_vorab(pruefen=True)
    z = zaehle(pathlib.Path(argv[1]), v, cfg)
    kopf = {"modus": "Vorwärts-Zählung", "vorab_sha256": sha256_text(VORAB.read_text(encoding="utf-8"))}
    rb.schreibe({v["fassung"]: z["erg"]}, z["trades"], cfg, ERGEBNIS, kopf)
    print(json.dumps(z["erg"], ensure_ascii=False, default=str)[:800])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
