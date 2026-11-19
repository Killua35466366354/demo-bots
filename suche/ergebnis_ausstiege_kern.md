# Andere Ausstiege für US100-Rücksetzer, Nasdaq Noise Long und DAX-Scalper

Regeln: suche/VORAB_ausstiege_kern.yaml (versiegelt vor dem Rechnen). Gleiche Einstiege wie der Bot, nur der Ausstieg ändert sich. Langes Fenster für den gepaarten Test (Holm über 8 Varianten), Hauptfenster ab 01.01.2025.

**Ergebnis: 0 von 8 Varianten bestehen.** Kein Bot ändert sich.

| Variante | Bot | Trades lang | GF Original lang | GF Variante lang | Unterschied je Trade (R) | p | Holm | Trades ab 2025 | GF Original ab 2025 | GF Variante ab 2025 | Summe R Original | Summe R Variante | GF 1,5x Kosten | bestanden |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r9a_einstand | r5-ruecksetzer-us100 | 139 | 1,54 | 1,74 | 0,029 | 0,2528 | nein | 24 | 2,28 | 2,61 | 7,80 | 7,80 | 2,44 | nein |
| r9b_halb_und_10_tage | r5-ruecksetzer-us100 | 139 | 1,54 | 1,71 | 0,017 | 0,3828 | nein | 24 | 2,28 | 3,05 | 7,80 | 8,93 | 2,87 | nein |
| r11a_einstand | r7-nasdaq-noise-long | 138 | 2,19 | 2,31 | -0,007 | 0,7864 | nein | 20 | 4,33 | 3,33 | 2,56 | 1,89 | 3,19 | nein |
| r11b_einstand_10_tage | r7-nasdaq-noise-long | 138 | 2,19 | 3,12 | 0,049 | 0,0261 | nein | 20 | 4,33 | 3,13 | 2,56 | 1,60 | 2,65 | nein |
| r13_s075_z075 | scalp-de40 | 607 | 1,26 | 1,32 | 0,061 | 0,1052 | nein | 121 | 1,70 | 1,65 | 55,33 | 54,80 | 1,50 | nein |
| r13_s075_z150 | scalp-de40 | 607 | 1,26 | 1,41 | 0,121 | 0,0127 | nein | 121 | 1,70 | 1,84 | 55,33 | 70,70 | 1,66 | nein |
| r13_s150_z075 | scalp-de40 | 607 | 1,26 | 1,28 | -0,019 | 0,6407 | nein | 121 | 1,70 | 1,69 | 55,33 | 44,72 | 1,65 | nein |
| r13_s150_z150 | scalp-de40 | 607 | 1,26 | 1,35 | 0,025 | 0,3160 | nein | 121 | 1,70 | 1,91 | 55,33 | 58,77 | 1,84 | nein |

## Gründe

- r9a_einstand: Holm nicht bestanden; Hauptfenster Summe nicht höher
- r9b_halb_und_10_tage: Holm nicht bestanden
- r11a_einstand: Holm nicht bestanden; Hauptfenster Summe nicht höher; Hauptfenster Gewinnfaktor nicht mindestens wie das Original
- r11b_einstand_10_tage: Holm nicht bestanden; Hauptfenster Summe nicht höher; Hauptfenster Gewinnfaktor nicht mindestens wie das Original
- r13_s075_z075: Holm nicht bestanden; Hauptfenster Summe nicht höher; Hauptfenster Gewinnfaktor nicht mindestens wie das Original
- r13_s075_z150: Holm nicht bestanden
- r13_s150_z075: Holm nicht bestanden; Hauptfenster Summe nicht höher; Hauptfenster Gewinnfaktor nicht mindestens wie das Original
- r13_s150_z150: Holm nicht bestanden

## Hinweise

- Nr. 10 (Dow) ist nicht gerechnet. Im Projekt liegen keine Dow-Kerzen.
- Nachrechnung Noise Long gegen die Trade-Liste der Runde 7: {"fehlt": 0, "median_abweichung_r": 0.0047, "max_abweichung_r": 0.1537, "grund_anders": 0}.
- R beim Rücksetzer ist ein ATR 20 (Notstop 3 R), beim Noise Long der Stop-Abstand von 5 ATR (1 ATR = 0,2 R), beim DAX-Scalper der eigene Stop-Abstand der Variante.
- Rücksetzer und DAX-Scalper rechnen auf echtem UTC, darum weichen ihre Originale etwas von den alten Tests ab (dort lag im Sommer jede Kerze 1 Stunde zu spät).
