# Gold-Matrix umgedreht: Ergebnis

**Ergebnis:** Von 8 umgedrehten Verlierern besteht 0. Kandidaten: 0. In der zweiten Hälfte liegen 1 von 8 nach Kosten im Plus, zusammen -677,2 R. Mit 10 € Risiko je Trade sind das -6772 €. Die Originale machten in derselben Zeit zusammen -795,8 R (-7958 €).

Regeln: suche/VORAB_gold_matrix_umkehr.yaml (Prüfsumme im Protokoll, festgelegt vor der Rechnung), einmal gerechnet mit suche/gold_matrix_umkehr.py. Daten, Kosten, Zwillinge und Hürden sind die der Gold-Matrix (suche/VORAB_gold_matrix.yaml). Erste Hälfte: Einstiege 01.01.2024 bis 31.05.2025. Zweite Hälfte: danach bis 30.10.2026.

## Was die alte Tabelle schon zeigte (erste Hälfte, 54.375 Varianten)

- 40317 Varianten hatten mindestens 50 Trades. 28923 davon waren Verlierer.
- Alle Verlierer zusammen verloren 2778 Tausend R. Ihre Zwillinge (gleiche Trades an zufälligen Tagen, gleiche Kosten) verloren 2702 Tausend R. Rund 97 % des Verlusts sind also Kosten und kein Fehler in der Richtung.
- Umgedreht wären geschätzt 10970 Varianten im Plus. Ohne jeden Vorteil erwartet man 11075. Im Original waren es 11394.
- Deutlich schlechter als ihre Zwillinge (z bis -3) waren 52 Varianten. Der Zufall allein liefert 54.

## Die umgedrehten Verlierer

| Variante (umgedreht) | Urteil | Trades | Gewinnfaktor | 1,5x Kosten | Hälfte 1 | Hälfte 2 | 2026 | Hälfte 2 in R | Zufall Hälfte 2 | p | Holm | z | Original Hälfte 1 in R | Original Hälfte 2 in R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pivot_abprall.5m.ohne.atr1_1h.zeit_15m | durchgefallen | 1085 | 0,92 | 0,82 | 0,97 (532) | 0,87 (553) | 1,10 (318) | -22,4 | 45,4 % | 0,5472 | nein | -0,12 | -96,9 | -32,7 |
| dollar_nachlauf.15m.dollar_wind.atr1_4h.ziel_1r | durchgefallen | 503 | 1,16 | 1,13 | 1,37 (262) | 0,97 (241) | 0,92 (132) | -4,2 | 62,1 % | 0,3811 | nein | 0,24 | -73,5 | -12,7 |
| dollar_nachlauf.15m.ohne.atr1_4h.ziel_1r | durchgefallen | 605 | 1,13 | 1,11 | 1,31 (305) | 0,97 (300) | 0,91 (162) | -3,9 | 67,7 % | 0,3257 | nein | 0,41 | -76,0 | -13,3 |
| schwungkerze.1m.ohne.atr1_1m.zeit_1m | durchgefallen | 3869 | 0,77 | 0,67 | 0,93 (266) | 0,76 (3603) | 0,79 (3015) | -496,6 | 24,5 % | 0,7557 | nein | -0,62 | -93,6 | -640,7 |
| pivot_abprall.1m.dollar_wind.atr2_5m.zeit_15m | durchgefallen | 532 | 0,99 | 0,91 | 1,10 (267) | 0,90 (265) | 0,97 (153) | -11,8 | 59,1 % | 0,4104 | nein | 0,23 | -81,7 | -38,0 |
| ruecksetzer.15m.realzins.swing_15m.ziel_2r | durchgefallen | 819 | 0,79 | 0,72 | 1,05 (212) | 0,70 (607) | 0,71 (435) | -133,0 | 2,0 % | 0,9805 | nein | -1,85 | -94,4 | -8,9 |
| ausbruch.15m.dollar_wind.swing_4h.trail_struktur_15m | durchgefallen | 2594 | 0,91 | 0,82 | 1,00 (1309) | 0,82 (1285) | 0,87 (760) | -15,0 | 23,2 % | 0,7687 | nein | -0,74 | -34,1 | 3,8 |
| band_umkehr.15m.realzins.swing_15m.ziel_2r | durchgefallen | 483 | 0,94 | 0,86 | 0,69 (124) | 1,04 (359) | 0,97 (241) | 9,7 | 95,8 % | 0,0456 | nein | 1,78 | -62,0 | -53,3 |

Was fehlt, je Variante:

- pivot_abprall.5m.ohne.atr1_1h.zeit_15m: GF 0.92, 1,5x Spread 0.82, 1. Hälfte 0.97, 2. Hälfte 0.87, Zufallsvergleich
- dollar_nachlauf.15m.dollar_wind.atr1_4h.ziel_1r: GF 1.16, 2. Hälfte 0.97, 2026 0.92, Zufallsvergleich
- dollar_nachlauf.15m.ohne.atr1_4h.ziel_1r: GF 1.13, 2. Hälfte 0.97, 2026 0.91, Zufallsvergleich
- schwungkerze.1m.ohne.atr1_1m.zeit_1m: GF 0.77, 1,5x Spread 0.67, 1. Hälfte 0.93, 2. Hälfte 0.76, 2026 0.79, Zufallsvergleich
- pivot_abprall.1m.dollar_wind.atr2_5m.zeit_15m: GF 0.99, 1,5x Spread 0.91, 2. Hälfte 0.9, 2026 0.97, Zufallsvergleich
- ruecksetzer.15m.realzins.swing_15m.ziel_2r: GF 0.79, 1,5x Spread 0.72, 2. Hälfte 0.7, 2026 0.71, Zufallsvergleich
- ausbruch.15m.dollar_wind.swing_4h.trail_struktur_15m: GF 0.91, 1,5x Spread 0.82, 1. Hälfte 1.0, 2. Hälfte 0.82, 2026 0.87, Zufallsvergleich
- band_umkehr.15m.realzins.swing_15m.ziel_2r: GF 0.94, 1,5x Spread 0.86, 1. Hälfte 0.69, 2026 0.97

## Auskunft

- Genaues Spiegelbild der zweiten Hälfte (Stop und Ausstieg des Originals vertauscht, Näherung aus den Summen): -4,2 R, -0,4 R, 3,2 R, -371,1 R, 6,9 R, -107,8 R, -18,2 R, -32,6 R.
- Spread je Trade in R: 0,057, 0,028, 0,028, 0,144, 0,088, 0,104, 0,013, 0,112.
- Holm zusammen mit den 12 Finalisten der Gold-Matrix (20 Prüfungen): 0 bestehen.

## Folge

Keine umgedrehte Variante besteht. "Verlierer umdrehen" gilt für die Gold-Matrix als geprüft und wird auf diesen Daten nicht wiederholt. An keinem Bot ändert sich etwas.
