# Ergebnis: Rückgänge von V1

Regeln: `suche/VORAB_v1_rueckgang.yaml`, versiegelt vor dem Rechnen. Rechnung: `python -m suche.v1_rueckgang <Projektordner>`.

**Kein Filter bestanden.** Keiner der drei live erkennbaren Gründe macht V1 mit wachsendem Einsatz 2026 klar besser.

Konto: 1.000 € am 01.01.2026, 2 % Einsatz je Trade vom Kontostand, nur die Grenze des Brokers, jeder Trade 0,1 R schlechter. Ohne Filter am Ende 2.309 €, schlimmster Rückgang 33 %, 361 Trades.

Probelauf: Mit gemischten R bestand in 8 von 200 Mischungen mindestens ein Filter (4 %, erlaubt höchstens 10 %). Der Test taugt.

## Urteil 2026

| Filter | Wahl erfüllt | ausgelassen | Summe R ausgelassen | Ende | Rückgang | p | Holm | bestanden |
|---|---|---|---|---|---|---|---|---|
| F1 Gold nervös gegen sich selbst (GVZ) | ja | 36 | +10,3 R | 2.043 € | 31 % | 0,6117 | nein | nein |
| F2 zu viele offen (ab 3) | ja | 57 | -5,5 R | 2.558 € | 29 % | 0,1709 | nein | nein |
| F3 Gold bei Angst an der Börse (VIX über 20,67) | ja | 12 | +14,9 R | 1.861 € | 31 % | 0,8966 | nein | nein |

## Wahl November 2024 bis Dezember 2025

Ohne Filter am Ende 4.815 €, Rückgang 50 %.

| Filter | ausgelassen | Summe R ausgelassen | Ende | Rückgang | ins Urteil |
|---|---|---|---|---|---|
| F1 Gold nervös gegen sich selbst (GVZ) | 77 | -19,4 R | 7.322 € | 46 % | ja |
| F2 zu viele offen (ab 3) | 143 | -7,2 R | 5.969 € | 44 % | ja |
| F3 Gold bei Angst an der Börse (VIX über 20,67) | 43 | -16,2 R | 6.741 € | 45 % | ja |

## Auskunft: die drei tiefsten Rückgänge (01.11.2024 bis 31.10.2026, ohne Filter)

- 2025-04-21 bis 2025-08-26: von 6.359 € auf 3.162 € (50 %), 204 Trades, Gold -28,1 R, GVZ bei Gold-Trades im Schnitt 18,7, VIX im Schnitt 18,6. Je Bot: gold-zonen -27,5 R (34), scalp-us100 -11,2 R (29), welt-ausbruch4h -7,6 R (60), gold-ausbruch4h -0,7 R (11), r7-nasdaq-noise-long -0,1 R (10), gold-cb +0,1 R (30), r5-ruecksetzer-us100 +0,1 R (5), r5-ruecksetzer-us500 +0,5 R (3), scalp-de40 +16,0 R (22).
- 2026-03-30 bis 2026-08-03: von 9.581 € auf 6.419 € (33 %), 149 Trades, Gold -15,9 R, GVZ bei Gold-Trades im Schnitt 26,9, VIX im Schnitt 17,7. Je Bot: gold-zonen -24,9 R (25), scalp-de40 -2,7 R (20), welt-ausbruch4h -1,3 R (46), gold-ausbruch4h -0,8 R (14), r5-ruecksetzer-us500 -0,2 R (3), r5-ruecksetzer-us100 -0,2 R (4), r7-nasdaq-noise-long +0,6 R (1), scalp-us100 +2,5 R (17), gold-cb +9,8 R (19).
- 2024-12-17 bis 2025-01-10: von 1.901 € auf 1.455 € (23 %), 33 Trades, Gold -3,7 R, GVZ bei Gold-Trades im Schnitt 15,2, VIX im Schnitt 17,6. Je Bot: gold-cb -6,9 R (6), scalp-de40 -3,4 R (5), scalp-us100 -3,2 R (5), welt-ausbruch4h -1,7 R (9), r5-ruecksetzer-us500 -1,0 R (2), gold-ausbruch4h +0,1 R (1), r7-nasdaq-noise-long +0,2 R (1), r5-ruecksetzer-us100 +0,7 R (2), gold-zonen +3,1 R (2).

## Auskunft: ganze Zeit 01.11.2024 bis 31.10.2026 (Auswahlzeit steckt darin)

Ohne Filter 11.112 €, Rückgang 50 %.

| Filter | ausgelassen | Summe R ausgelassen | Ende | Rückgang |
|---|---|---|---|---|
| F1 Gold nervös gegen sich selbst (GVZ) | 113 | -9,1 R | 14.955 € | 46 % |
| F2 zu viele offen (ab 3) | 200 | -8,2 R | 13.946 € | 44 % |
| F3 Gold bei Angst an der Börse (VIX über 20,67) | 55 | -1,3 R | 12.542 € | 45 % |

## Auskunft: umdrehen statt auslassen, bester Fall 2026

Der ausgelassene Trade wird umgedreht genommen, mit -R minus 0,1 R. Die zweiten Kosten des Gegentrades fehlen, darum ist das der beste Fall. Kein Urteil, die Umkehr ist dreimal durchgefallen.

| Filter | Ende umgedreht | Rückgang umgedreht | Ende ausgelassen |
|---|---|---|---|
| F1 Gold nervös gegen sich selbst (GVZ) | 1.371 € | 33 % | 2.043 € |
| F2 zu viele offen (ab 3) | 2.306 € | 42 % | 2.558 € |
| F3 Gold bei Angst an der Börse (VIX über 20,67) | 1.279 € | 38 % | 1.861 € |

Ehrlich dazu: Die Trades sind Rückblick-Trades. V1 und seine Bots wurden an denselben Monaten ausgesucht. Darum zählt nur das Urteil an 2026. Offene Verluste, der Stop-out des Brokers und die kleinste Handelsgröße fehlen in der Rechnung.
