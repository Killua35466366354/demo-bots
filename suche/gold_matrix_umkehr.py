"""Gold-Matrix umgedreht: Werden die schlimmsten Verlierer der Gold-Matrix zu Gewinnern, wenn man sie umdreht?

Kirons Wunsch vom 19.11.2026. Regeln, Auswahl und Hürden stehen in suche/VORAB_gold_matrix_umkehr.yaml und sind dort
festgelegt, bevor gerechnet wurde (Prüfsumme im Protokoll). Das Rechenwerk ist suche/gold_matrix.py, unverändert. Dieser
Code dreht nur die Richtung jedes Signals um und bewertet das Ergebnis mit denselben Hürden.

    python -m suche.gold_matrix_umkehr --festlegen "Grund"                     # Prüfsumme ins Protokoll, BEVOR gerechnet wird
    python -m suche.gold_matrix_umkehr rechnen <Datenordner> <Arbeitsordner> [Tabelle]   # einmal, schreibt das Ergebnis

Die Tabelle ist auswahl_varianten.csv.gz der Gold-Matrix. Ist sie angegeben, prüft das Programm ihre Prüfsumme und dass
die Auswahl-Regel genau die versiegelten Umkehr-Finalisten liefert. Ohne Siegel rechnet das Programm nicht.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

import numpy as np
import pandas as pd
import yaml

from suche import gold_matrix as gm

ROOT = gm.ROOT
VORAB = ROOT / "suche" / "VORAB_gold_matrix_umkehr.yaml"
KEY = "VORAB_gold_matrix_umkehr sha256 "
ERGEBNIS = ROOT / "suche" / "ergebnis_gold_matrix_umkehr"
EUR_JE_R = 10.0                                                  # Euro-Beispiel: 10 € Risiko je Trade


def regel() -> dict:
    return yaml.safe_load(VORAB.read_text(encoding="utf-8"))["gold_matrix_umkehr"]


def vorab_ok() -> bool:
    from suche.runde1 import journal_lines, last_value, sha256_text
    return VORAB.exists() and last_value(journal_lines(), KEY) == sha256_text(VORAB.read_text(encoding="utf-8"))


def teile(key: str) -> dict:
    """Name einer Variante in ihre fünf Bausteine."""
    fam, ebene, flt, stop, ausstieg = key.split(".")
    return {"key": key, "einstieg": fam, "ebene": ebene, "filter": flt, "stop": stop, "ausstieg": ausstieg}


# ---------------------------------------------------------------------------------------------------------------------
# Auswahl aus der Tabelle der ersten Hälfte (keine Kurse)

def waehle(tab: pd.DataFrame, a: dict) -> list[dict]:
    """Die Auswahl-Regel der VORAB-Datei: die Varianten mit dem kleinsten z, höchstens eine je Zelle."""
    t = tab.copy()
    for sp in ("trades", "summe_r", "zw_mittel", "z"):
        t[sp] = pd.to_numeric(t[sp], errors="coerce")
    t = t[(t["trades"] >= int(a["wertbar_min_trades"])) & t["z"].notna()].copy()
    t["schaetzung"] = 2.0 * t["zw_mittel"] - t["summe_r"]
    t = t[(t["z"] <= float(a["max_z"])) & (t["schaetzung"] > 0)].sort_values(["z", "key"])
    out, je_fam, zellen = [], {}, set()
    for _, f in t.iterrows():
        if len(out) >= int(a["finalisten_max"]):
            break
        zelle = (f["einstieg"], f["ebene"], f["filter"])
        if zelle in zellen or je_fam.get(f["einstieg"], 0) >= int(a["max_je_einstieg"]):
            continue
        zellen.add(zelle)
        je_fam[f["einstieg"]] = je_fam.get(f["einstieg"], 0) + 1
        out.append({"key": f["key"], "trades": int(f["trades"]), "z": round(float(f["z"]), 3),
                    "summe_r": round(float(f["summe_r"]), 1), "schaetzung_r": round(float(f["schaetzung"]), 1)})
    return out


def pruefe_tabelle(pfad: pathlib.Path, p: dict) -> None:
    """Die Tabelle ist die versiegelte, und die Regel liefert genau die versiegelten Umkehr-Finalisten."""
    if gm.sha256_datei(pfad) != p["quelle"]["tabelle_sha256"]:
        raise SystemExit(f"{pfad} ist nicht die versiegelte Tabelle der Gold-Matrix")
    soll, ist = [f["key"] for f in p["finalisten"]], [f["key"] for f in waehle(pd.read_csv(pfad), p["auswahl"])]
    if soll != ist:
        raise SystemExit(f"Die Auswahl-Regel liefert andere Finalisten als versiegelt: {ist}")


# ---------------------------------------------------------------------------------------------------------------------
# Umgedrehter Lauf

def trades_umkehr(m: gm.Markt, f: dict, von, bis, faktor: float = 1.0) -> pd.DataFrame:
    """Alle Trades der umgedrehten Variante im Fenster. Signale, Filter und Stop-Abstand kommen vom Original, gehandelt
    wird die Gegenrichtung (Spalte d ist schon umgedreht)."""
    stops = {name: (art, seb) for name, art, seb in gm.stop_liste(f["ebene"])}
    aust = {name: (modus, zahl, xeb) for name, modus, zahl, xeb in gm.ausstieg_liste(f["ebene"])}
    art, seb = stops[f["stop"]]
    modus, zahl, xeb = aust[f["ausstieg"]]
    e, d = gm.einstiege(m, f["einstieg"], f["ebene"])
    ok = gm.im_fenster(m, e, von, bis)
    e, d = e[ok], d[ok]
    ok = gm.filter_maske(m, f["filter"], f["ebene"], e, d)       # der Filter sieht die Richtung des Originals
    e, d = np.ascontiguousarray(e[ok]), np.ascontiguousarray(d[ok])
    dist = np.ascontiguousarray(gm.stop_abstand(m, art, seb, e, d))   # Abstand des Originals
    u = np.ascontiguousarray(-d)
    r, aus, grund = gm.rechne(m, e, u, dist, modus, zahl, xeb, faktor)
    gen = ~np.isnan(r)
    return pd.DataFrame({"e": e[gen], "zeit": m.t[e[gen]], "d": u[gen], "r_usd": dist[gen], "r": r[gen],
                         "zeit_aus": m.t[aus[gen]], "halte_min": m.tmin[aus[gen]] - m.tmin[e[gen]],
                         "grund": [gm.GRUND[int(g)] for g in grund[gen]]})


def _summe(tr: pd.DataFrame, von, bis) -> float:
    return float(gm._teil(tr, von, bis)["r"].sum())


def bewerte_umkehr(m: gm.Markt, f: dict, laeufe: int | None = None) -> tuple[dict, pd.DataFrame]:
    """Eine umgedrehte Variante über das ganze Hauptfenster, bewertet wie ein Finalist der Gold-Matrix. Zwillinge nur
    für die Trades der zweiten Hälfte. Dazu als Auskunft das Original im selben Lauf."""
    von, mitte, bis = gm.HAUPT_VON, gm.MITTE, gm.HAUPT_BIS
    tr = trades_umkehr(m, f, von, bis)
    rob = trades_umkehr(m, f, von, bis, gm.ROBUST)
    wochen = (bis - von) / pd.Timedelta(days=7)
    k = gm.kennzahlen(tr["r"].to_numpy())
    h2 = gm._teil(tr, mitte, bis)
    b = {**k, "je_woche": round(k["trades"] / wochen, 2), "robust_pf": gm.kennzahlen(rob["r"].to_numpy())["pf"],
         "h1": gm._pf_n(gm._teil(tr, von, mitte)), "h2": gm._pf_n(h2), "j2026": gm._pf_n(gm._teil(tr, "2026-01-01", bis)),
         "h1_r": round(_summe(tr, von, mitte), 1), "h2_r": round(float(h2["r"].sum()), 1),
         "median_halte_min": float(tr["halte_min"].median()) if len(tr) else None,
         "spread_r": round(float((gm.SPREAD / tr["r_usd"]).mean()), 3) if len(tr) else None}
    if len(h2):
        modus, zahl, xeb = {name: (mo, za, xe) for name, mo, za, xe in gm.ausstieg_liste(f["ebene"])}[f["ausstieg"]]
        seb = {name: eb for name, _, eb in gm.stop_liste(f["ebene"])}[f["stop"]]
        e = h2["e"].to_numpy(np.int64)
        d, dist = h2["d"].to_numpy(np.int64), h2["r_usd"].to_numpy(float)
        kal = gm.kalender(m, mitte, bis)
        tw = gm.verschiebe(kal, e, gm.schritte(kal.tage, laeufe))
        s, _, _ = gm.zwillinge(m, tw, gm.vola_faktor(m, seb, e, tw), d, dist, modus, zahl, xeb, gm.nacht_r(m, e, d, dist))
        echt, sd = float(h2["r"].sum()), float(s.std())
        b["zufall"] = {"geschlagen_pct": round(float((s < echt).mean() * 100), 2),
                       "p": float((1 + (s >= echt).sum()) / (len(s) + 1)),
                       "z": round((echt - float(s.mean())) / sd, 3) if sd > 0 else None,
                       "mittel_r": round(float(s.mean()), 1), "echt_r": round(echt, 1), "laeufe": int(len(s))}
    else:
        b["zufall"] = {"geschlagen_pct": None, "p": 1.0, "z": None, "mittel_r": None, "echt_r": 0.0, "laeufe": 0}
    # Auskunft: das Original im selben Lauf und das genaue Spiegelbild der zweiten Hälfte als Näherung
    orig, orob = gm.trades_von(m, f, von, bis), gm.trades_von(m, f, von, bis, gm.ROBUST)
    o2, o2r = _summe(orig, mitte, bis), _summe(orob, mitte, bis)
    b["original"] = {"h1": gm._pf_n(gm._teil(orig, von, mitte)), "h2": gm._pf_n(gm._teil(orig, mitte, bis)),
                     "h1_r": round(_summe(orig, von, mitte), 1), "h2_r": round(o2, 1),
                     "spiegel_h2_r": round(-o2 - 4.0 * (o2 - o2r), 1)}
    return b, tr


# ---------------------------------------------------------------------------------------------------------------------
# Lauf und Bericht

def rechnen(ordner: pathlib.Path, arbeit: pathlib.Path, tabelle: pathlib.Path | None) -> int:
    from suche.runde1 import sha256_text
    p = regel()
    if tabelle is not None:
        pruefe_tabelle(tabelle, p)
    arbeit.mkdir(parents=True, exist_ok=True)
    bst = gm.P["bestaetigung"]
    t0 = time.time()
    m = gm.lade_markt(ordner, gm.VORLAUF_AB, pd.Timestamp("2100-01-01"))
    res = {"vorab_sha256": sha256_text(VORAB.read_text(encoding="utf-8")), "daten": gm.daten_siegel(ordner),
           "numba": gm.SCHNELL, "kerzen": [str(pd.Timestamp(m.t[0])), str(pd.Timestamp(m.t[-1]))],
           "tabelle_geprueft": tabelle is not None, "vorschau": p["vorschau"], "finalisten": {}}
    for zeile in p["finalisten"]:
        f = teile(zeile["key"])
        b, tr = bewerte_umkehr(m, f, None if bst["verschiebungen"] == "alle" else int(bst["verschiebungen"]))
        b["auswahl"] = {k: zeile[k] for k in ("trades", "pf", "summe_r", "zw_mittel", "z")}
        res["finalisten"][f["key"]] = b
        tr.drop(columns=["e"]).to_csv(arbeit / f"trades_umkehr_{f['key']}.csv", index=False)
        print(f["key"], b["trades"], b["pf"], b["h2"], b["zufall"], f"{time.time() - t0:.0f} s", flush=True)
    ps = {k: b["zufall"]["p"] for k, b in res["finalisten"].items()}
    hm = gm.holm(ps, float(bst["holm_alpha"]))
    for key, b in res["finalisten"].items():
        b["holm"] = bool(hm[key])
        b["urteil"], b["fehlt"] = gm.urteil_finalist(b, b["holm"])
    alt = gm.ERGEBNIS.with_suffix(".json")
    if alt.exists():                                             # Auskunft: Holm zusammen mit den 12 Finalisten der Gold-Matrix
        alle = {**ps, **{"matrix:" + k: v["zufall"]["p"]
                         for k, v in json.loads(alt.read_text(encoding="utf-8"))["finalisten"].items()}}
        zus = gm.holm(alle, float(bst["holm_alpha"]))
        res["holm_mit_gold_matrix"] = {"pruefungen": len(alle), "bestehen": sorted(k for k in ps if zus[k])}
    ERGEBNIS.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str) + "\n",
                                             encoding="utf-8")
    ERGEBNIS.with_suffix(".md").write_text(bericht(res), encoding="utf-8")
    print(bericht(res))
    return 0


def _pf(x) -> str:
    return f"{gm._z(x[0])} ({x[1]})"


def bericht(res: dict) -> str:
    fin, v = res["finalisten"], res["vorschau"]
    gut = [k for k, b in fin.items() if b["urteil"] == "bestanden"]
    kand = [k for k, b in fin.items() if b["urteil"] == "kandidat"]
    plus = [k for k, b in fin.items() if b["h2_r"] > 0]
    summe2 = sum(b["h2_r"] for b in fin.values())
    orig2 = sum(b["original"]["h2_r"] for b in fin.values())
    z = ["# Gold-Matrix umgedreht: Ergebnis", "",
         f"**Ergebnis:** Von {len(fin)} umgedrehten Verlierern besteht {len(gut)}. Kandidaten: {len(kand)}. "
         f"In der zweiten Hälfte liegen {len(plus)} von {len(fin)} nach Kosten im Plus, zusammen "
         f"{gm._z(summe2, 1)} R. Mit 10 € Risiko je Trade sind das {gm._z(summe2 * EUR_JE_R, 0)} €. Die Originale "
         f"machten in derselben Zeit zusammen {gm._z(orig2, 1)} R ({gm._z(orig2 * EUR_JE_R, 0)} €).", "",
         "Regeln: suche/VORAB_gold_matrix_umkehr.yaml (Prüfsumme im Protokoll, festgelegt vor der Rechnung), einmal "
         "gerechnet mit suche/gold_matrix_umkehr.py. Daten, Kosten, Zwillinge und Hürden sind die der Gold-Matrix "
         "(suche/VORAB_gold_matrix.yaml). Erste Hälfte: Einstiege 01.01.2024 bis 31.05.2025. Zweite Hälfte: danach "
         "bis 30.10.2026.", "",
         "## Was die alte Tabelle schon zeigte (erste Hälfte, 54.375 Varianten)", "",
         f"- {v['wertbare_varianten']} Varianten hatten mindestens 50 Trades. {v['verlierer']} davon waren Verlierer.",
         f"- Alle Verlierer zusammen verloren {gm._z(-v['verlust_aller_verlierer_r'] / 1000, 0)} Tausend R. Ihre "
         f"Zwillinge (gleiche Trades an zufälligen Tagen, gleiche Kosten) verloren "
         f"{gm._z(-v['davon_verlieren_auch_die_zwillinge_r'] / 1000, 0)} Tausend R. Rund "
         f"{gm._z(100.0 * v['davon_verlieren_auch_die_zwillinge_r'] / v['verlust_aller_verlierer_r'], 0)} % des "
         "Verlusts sind also Kosten und kein Fehler in der Richtung.",
         f"- Umgedreht wären geschätzt {v['umgedreht_im_plus_geschaetzt']} Varianten im Plus. Ohne jeden Vorteil "
         f"erwartet man {v['im_plus_ohne_jeden_vorteil_erwartet']}. Im Original waren es {v['im_plus']}.",
         f"- Deutlich schlechter als ihre Zwillinge (z bis -3) waren {v['z_bis_minus_3']} Varianten. Der Zufall "
         f"allein liefert {v['z_bis_minus_3_ohne_jeden_vorteil_erwartet']}.", "",
         "## Die umgedrehten Verlierer", "",
         "| Variante (umgedreht) | Urteil | Trades | Gewinnfaktor | 1,5x Kosten | Hälfte 1 | Hälfte 2 | 2026 | Hälfte 2 in R | "
         "Zufall Hälfte 2 | p | Holm | z | Original Hälfte 1 in R | Original Hälfte 2 in R |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for key, b in fin.items():
        zf = b["zufall"]
        z.append(f"| {key} | {gm.URTEIL_TEXT[b['urteil']]} | {b['trades']} | {gm._z(b['pf'])} | {gm._z(b['robust_pf'])} | "
                 f"{_pf(b['h1'])} | {_pf(b['h2'])} | {_pf(b['j2026'])} | {gm._z(b['h2_r'], 1)} | "
                 f"{gm._z(zf['geschlagen_pct'], 1)} % | {gm._z(zf['p'], 4)} | {'ja' if b['holm'] else 'nein'} | "
                 f"{gm._z(zf['z'])} | {gm._z(b['original']['h1_r'], 1)} | {gm._z(b['original']['h2_r'], 1)} |")
    z += ["", "Was fehlt, je Variante:", ""]
    z += [f"- {key}: {', '.join(b['fehlt']) if b['fehlt'] else 'nichts'}" for key, b in fin.items()]
    z += ["", "## Auskunft", "",
          "- Genaues Spiegelbild der zweiten Hälfte (Stop und Ausstieg des Originals vertauscht, Näherung aus den "
          "Summen): " + ", ".join(f"{gm._z(b['original']['spiegel_h2_r'], 1)} R" for b in fin.values()) + ".",
          "- Spread je Trade in R: " + ", ".join(gm._z(b["spread_r"], 3) for b in fin.values()) + "."]
    if "holm_mit_gold_matrix" in res:
        h = res["holm_mit_gold_matrix"]
        z.append(f"- Holm zusammen mit den 12 Finalisten der Gold-Matrix ({h['pruefungen']} Prüfungen): "
                 f"{len(h['bestehen'])} bestehen.")
    z += ["", "## Folge", "",
          ("Bestanden hat: " + ", ".join(gut) + ". Vorschlag an Kiron auf einer Karte (Schatten ohne Order)." if gut else
           "Keine umgedrehte Variante besteht. \"Verlierer umdrehen\" gilt für die Gold-Matrix als geprüft und wird auf "
           "diesen Daten nicht wiederholt. An keinem Bot ändert sich etwas."), ""]
    return "\n".join(z)


def main(argv: list[str]) -> int:
    from suche.runde1 import journal_add, sha256_text
    if argv[:1] == ["--festlegen"]:
        journal_add(f"{argv[1]} VORAB_gold_matrix_umkehr sha256 {sha256_text(VORAB.read_text(encoding='utf-8'))}")
        return 0
    if not gm.vorab_ok() or not vorab_ok():
        raise SystemExit("suche/VORAB_gold_matrix_umkehr.yaml steht so nicht im Protokoll. Erst --festlegen \"Grund\".")
    if len(argv) not in (3, 4) or argv[0] != "rechnen":
        raise SystemExit(__doc__)
    if ERGEBNIS.with_suffix(".json").exists():
        raise SystemExit("Das Ergebnis steht schon (suche/ergebnis_gold_matrix_umkehr.json). Gerechnet wird nur einmal.")
    return rechnen(pathlib.Path(argv[1]), pathlib.Path(argv[2]), pathlib.Path(argv[3]) if len(argv) == 4 else None)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
