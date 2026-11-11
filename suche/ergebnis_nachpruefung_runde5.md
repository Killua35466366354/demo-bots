# Nachtrag zur Nachprüfung 2024 bis 2026: Runde 5 und 5b (Tageskerzen)

Regel: `suche/VORAB_bewertung_2024_26.yaml`, unverändert. Gelesen wurden die gespeicherten Trades von Runde 5 (41 Märkte) und Runde 5b (US500, US100). Die Nachprüfung vom 10.11.2026 hatte sie nicht gelesen, weil sie nur CSV-Dateien kannte. Ergebnis je Trade in Tagesschwankungen (ATR 20), nach Spread und Übernachtgebühr.

**14 Varianten gelesen, 1 bestehen die Hürden, die es hier gibt.** Für diese Trades gibt es ab 2024 keine Rechnung mit 1,5-fachen Kosten und keinen Zufallsvergleich.

| Variante | Märkte | Trades ab 2024 | je Woche | Gewinnfaktor | Summe | Hälfte 1 | Hälfte 2 | 2026 | vor 2024 (Trades, GF) | bestanden | was fehlt |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Trendfolge Abstimmung 1/3/12 Monate (alle Märkte) | 41 | 415 | 2,82 | 0,65 | -255,7 | 0,64 (220) | 0,67 (195) | 0,38 (121) | 2432, 0,67 | nein | GF 0.65, 1. Hälfte 0.64, 2. Hälfte 0.67, 2026 0.38 |
| Trendfolge Donchian 55 Tage (alle Märkte) | 41 | 231 | 1,58 | 0,60 | -216,0 | 0,58 (127) | 0,62 (104) | 0,31 (70) | 1432, 0,67 | nein | GF 0.6, 1. Hälfte 0.58, 2. Hälfte 0.62, 2026 0.31 |
| Trendfolge EWMAC (alle Märkte) | 41 | 311 | 2,14 | 0,50 | -383,2 | 0,49 (174) | 0,51 (137) | 0,40 (103) | 2000, 0,60 | nein | GF 0.5, 1. Hälfte 0.49, 2. Hälfte 0.51, 2026 0.4 |
| Trendfolge 12 Monate (alle Märkte) | 41 | 153 | 1,07 | 0,80 | -71,6 | 0,48 (85) | 1,57 (68) | 1,22 (44) | 1115, 0,67 | nein | GF 0.8, 1. Hälfte 0.48 |
| Double 7 (Indizes) | 9 | 268 | 1,83 | 1,46 | 69,7 | 1,20 (124) | 1,78 (144) | 0,90 (77) | 960, 0,93 | nein | 2026 0.9 |
| IBS (Indizes) | 9 | 695 | 4,71 | 1,17 | 50,9 | 1,07 (324) | 1,27 (371) | 1,10 (226) | 3082, 0,87 | nein | GF 1.17 |
| Index-Momentum (Reddit) | 9 | 31 | 0,25 | 1,11 | 8,0 | 2,62 (18) | 0,11 (13) | 0,11 (10) | 156, 1,58 | nein | nur 31 Trades, GF 1.11, 2. Hälfte 0.11 |
| Monatswechsel (Indizes) | 9 | 272 | 1,90 | 0,82 | -30,8 | 0,59 (136) | 1,10 (136) | 1,19 (80) | 1246, 1,22 | nein | GF 0.82, 1. Hälfte 0.59 |
| RSI 2 (Indizes) | 9 | 215 | 1,48 | 1,65 | 51,4 | 1,24 (99) | 2,45 (116) | 1,44 (61) | 777, 1,04 | JA | – |
| Trend-Rücksetzer (alle Märkte) | 41 | 1319 | 8,94 | 0,94 | -37,9 | 0,90 (676) | 0,98 (643) | 0,72 (371) | 8289, 0,94 | nein | GF 0.94, 1. Hälfte 0.9, 2. Hälfte 0.98, 2026 0.72 |
| Schwankungs-Rücksetzer (Indizes) | 9 | 406 | 2,78 | 1,06 | 10,6 | 0,98 (237) | 1,23 (169) | 1,10 (134) | 1600, 0,83 | nein | GF 1.06, 1. Hälfte 0.98 |
| RSI 2 (nur US500 und US100) | 2 | 71 | 0,49 | 3,47 | 36,7 | 2,44 (39) | 11,30 (32) | 4,44 (19) | 21, 0,41 | nein | nur 71 Trades |
| Double 7 (nur US500 und US100) | 2 | 77 | 0,53 | 1,97 | 36,9 | 1,77 (37) | 2,24 (40) | 1,08 (23) | 20, 0,62 | nein | nur 77 Trades |
| Trend-Rücksetzer (nur US500 und US100, läuft als Bot) | 2 | 77 | 0,53 | 2,93 | 33,2 | 2,09 (45) | 10,13 (32) | 4,29 (19) | 54, 0,86 | nein | nur 77 Trades |

## Nur Auskunft: die vier Trendfolger je Marktklasse

| Variante | Märkte | Trades ab 2024 | je Woche | Gewinnfaktor | Summe | vor 2024 (Trades, GF) |
|---|---|---|---|---|---|---|
| Trendfolge 12 Monate (alle Märkte), nur energie | 2 | 4 | 0,03 | 11,15 | 23,1 | 46, 1,77 |
| Trendfolge 12 Monate (alle Märkte), nur fx | 28 | 129 | 0,90 | 0,58 | -128,4 | 882, 0,52 |
| Trendfolge 12 Monate (alle Märkte), nur index_asien | 3 | 8 | 0,07 | 1,59 | 12,0 | 55, 0,39 |
| Trendfolge 12 Monate (alle Märkte), nur index_eu | 4 | 8 | 0,06 | 1,13 | 2,5 | 64, 1,15 |
| Trendfolge 12 Monate (alle Märkte), nur metall | 2 | 4 | 0,03 | 6,67 | 19,2 | 44, 1,00 |
| Trendfolge Abstimmung 1/3/12 Monate (alle Märkte), nur energie | 2 | 10 | 0,08 | 1,98 | 10,3 | 84, 1,12 |
| Trendfolge Abstimmung 1/3/12 Monate (alle Märkte), nur fx | 28 | 328 | 2,23 | 0,45 | -321,3 | 1883, 0,63 |
| Trendfolge Abstimmung 1/3/12 Monate (alle Märkte), nur index_asien | 3 | 28 | 0,19 | 1,07 | 3,6 | 128, 0,56 |
| Trendfolge Abstimmung 1/3/12 Monate (alle Märkte), nur index_eu | 4 | 31 | 0,22 | 0,44 | -37,3 | 170, 0,62 |
| Trendfolge Abstimmung 1/3/12 Monate (alle Märkte), nur index_us | 2 | 7 | 0,06 | 2,67 | 13,2 | 63, 1,33 |
| Trendfolge Abstimmung 1/3/12 Monate (alle Märkte), nur metall | 2 | 11 | 0,08 | 6,41 | 75,7 | 104, 0,89 |
| Trendfolge EWMAC (alle Märkte), nur energie | 2 | 14 | 0,11 | 0,55 | -11,1 | 71, 1,00 |
| Trendfolge EWMAC (alle Märkte), nur fx | 28 | 243 | 1,68 | 0,38 | -367,5 | 1559, 0,53 |
| Trendfolge EWMAC (alle Märkte), nur index_asien | 3 | 23 | 0,18 | 0,60 | -23,9 | 113, 0,39 |
| Trendfolge EWMAC (alle Märkte), nur index_eu | 4 | 15 | 0,13 | 0,23 | -38,6 | 138, 0,69 |
| Trendfolge EWMAC (alle Märkte), nur index_us | 2 | 8 | 0,14 | 0,39 | -11,0 | 41, 1,67 |
| Trendfolge EWMAC (alle Märkte), nur metall | 2 | 8 | 0,06 | 5,59 | 68,9 | 78, 1,09 |
| Trendfolge Donchian 55 Tage (alle Märkte), nur energie | 2 | 9 | 0,07 | 0,47 | -7,4 | 66, 0,97 |
| Trendfolge Donchian 55 Tage (alle Märkte), nur fx | 28 | 166 | 1,13 | 0,43 | -243,3 | 1089, 0,60 |
| Trendfolge Donchian 55 Tage (alle Märkte), nur index_asien | 3 | 19 | 0,16 | 0,60 | -15,0 | 73, 0,67 |
| Trendfolge Donchian 55 Tage (alle Märkte), nur index_eu | 4 | 11 | 0,09 | 1,12 | 2,3 | 93, 0,78 |
| Trendfolge Donchian 55 Tage (alle Märkte), nur index_us | 2 | 9 | 0,07 | 1,73 | 3,6 | 49, 1,05 |
| Trendfolge Donchian 55 Tage (alle Märkte), nur metall | 2 | 17 | 0,12 | 2,42 | 43,7 | 62, 1,09 |

Aus der Tabelle je Marktklasse kann nichts bestehen. Sie zeigt nur, wo die Trendfolge ab 2024 verdient oder verloren hat. Keine Nachbesserung nach dem Ergebnis.
