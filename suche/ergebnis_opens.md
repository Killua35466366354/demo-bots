# Opens aus Kirons Strategie-Video: Ergebnis

Regel: `suche/VORAB_opens.yaml` (sha256 `9db5b74f1d1c…`), Code `suche/opens.py`.

## Teil A: Laufende Bots nur in Richtung eines Opens

Trades der Bewertung 2025 bis 10/2026. PF = Gewinnfaktor in R. p = Anteil zufälliger gleich großer Auswahlen, die mindestens so gut sind.

| Bot | Original | Jahr | Quartal | Monat | Woche | Alle vier | Bestanden |
|---|---|---|---|---|---|---|---|
| r6-vortag-eurusd | 133 Tr., PF 1,67, 52,2 R | 69 Tr., PF 1,68, 27,4 R, p 0,476 | 74 Tr., PF 1,73, 30,9 R, p 0,413 | 84 Tr., PF 1,75, 35,6 R, p 0,376 | 99 Tr., PF 1,76, 42,8 R, p 0,295 | 30 Tr., PF 1,48, 8,6 R, p 0,645 | keiner |
| r6-vortag-gbpusd | 130 Tr., PF 1,29, 24,5 R | 66 Tr., PF 1,26, 11,2 R, p 0,565 | 71 Tr., PF 1,27, 12,9 R, p 0,534 | 82 Tr., PF 1,35, 18,2 R, p 0,387 | 107 Tr., PF 1,42, 28,4 R, p 0,125 | 33 Tr., PF 1,37, 7,7 R, p 0,430 | keiner |
| r6-london-gbpusd | 53 Tr., PF 1,33, 5,9 R | 39 Tr., PF 1,26, 3,5 R, p 0,624 | 41 Tr., PF 1,43, 5,5 R, p 0,350 | 33 Tr., PF 1,35, 4,5 R, p 0,479 | 36 Tr., PF 1,24, 2,8 R, p 0,623 | 20 Tr., PF 1,11, 0,8 R, p 0,671 | keiner |
| r6-noise-usdjpy | 254 Tr., PF 1,54, 4,9 R | 125 Tr., PF 0,96, -0,2 R, p 0,865 | 155 Tr., PF 0,91, -0,5 R, p 0,942 | 161 Tr., PF 1,03, 0,1 R, p 0,908 | 178 Tr., PF 1,48, 2,9 R, p 0,588 | 72 Tr., PF 0,84, -0,4 R, p 0,808 | keiner |
| us500 | 25 Tr., PF 7,51, 16,5 R | 23 Tr., PF 6,59, 14,2 R, p 0,797 | 23 Tr., PF 6,54, 14,0 R, p 0,836 | 14 Tr., PF 3,50, 6,3 R, p 0,961 | 7 Tr., PF 2,75, 2,8 R, p 0,889 | 6 Tr., PF 2,55, 2,5 R, p 0,878 | keiner |
| r5-ruecksetzer-us100 | 23 Tr., PF 2,06, 7,0 R | 21 Tr., PF 1,55, 3,6 R, p 0,982 | 15 Tr., PF 1,57, 3,1 R, p 0,709 | 12 Tr., PF 0,98, -0,1 R, p 0,912 | 3 Tr., PF 99,00, 3,2 R, p 0,377 | 2 Tr., PF 99,00, 2,8 R, p 0,493 | keiner |
| r7-nasdaq-noise-long | 20 Tr., PF 3,84, 2,3 R | 20 Tr., PF 3,84, 2,3 R, p - | 16 Tr., PF 4,55, 2,3 R, p 0,267 | 17 Tr., PF 3,47, 1,9 R, p 0,583 | 14 Tr., PF 2,73, 1,4 R, p 0,798 | 10 Tr., PF 2,47, 1,0 R, p 0,761 | keiner |

## Teil B: Rücklauf zum Wochen- bzw. Tages-Open in Richtung der großen Opens

Zeitraum 11/2024 bis 10/2026, Kontrolle 11/2022 bis 10/2024.

| Markt | Variante | Trades | je Woche | PF | robust | Hälfte 1 | Hälfte 2 | 2026 | Kontrolle | Summe R | Bestanden |
|---|---|---|---|---|---|---|---|---|---|---|---|
| EURUSD | woche | 40 | 0,38 | 0,60 | 0,59 | 0,45 | 0,75 | 0,80 | 0,80 | -3,9 | nein |
| EURUSD | tag | 79 | 0,76 | 1,09 | 1,06 | 1,79 | 0,64 | 0,63 | 0,67 | 1,2 | nein |
| GBPUSD | woche | 47 | 0,45 | 0,55 | 0,53 | 0,66 | 0,45 | 0,47 | 0,85 | -4,7 | nein |
| GBPUSD | tag | 63 | 0,61 | 0,89 | 0,84 | 1,79 | 0,53 | 0,52 | 0,69 | -1,3 | nein |
| USDJPY | woche | 50 | 0,48 | 0,66 | 0,65 | 0,41 | 0,86 | 0,86 | 0,38 | -4,2 | nein |
| USDJPY | tag | 66 | 0,63 | 1,05 | 1,04 | 0,79 | 1,21 | 1,21 | 1,88 | 0,6 | nein |
| AUDUSD | woche | 61 | 0,59 | 1,00 | 0,97 | 0,77 | 1,24 | 1,10 | 0,66 | 0,1 | nein |
| AUDUSD | tag | 78 | 0,75 | 0,71 | 0,70 | 0,69 | 0,72 | 0,66 | 0,88 | -4,0 | nein |
| USDCAD | woche | 35 | 0,34 | 0,70 | 0,68 | 1,24 | 0,39 | 0,29 | 1,12 | -2,2 | nein |
| USDCAD | tag | 68 | 0,65 | 1,08 | 0,90 | 1,67 | 0,68 | 0,74 | 0,81 | 0,8 | nein |
| USDCHF | woche | 44 | 0,42 | 0,87 | 0,80 | 0,56 | 1,80 | 1,81 | 1,34 | -1,1 | nein |
| USDCHF | tag | 79 | 0,76 | 0,93 | 0,89 | 1,57 | 0,37 | 0,45 | 0,95 | -1,0 | nein |
| NZDUSD | woche | 43 | 0,41 | 0,45 | 0,44 | 0,53 | 0,34 | 0,34 | 1,35 | -5,9 | nein |
| NZDUSD | tag | 54 | 0,52 | 0,91 | 0,75 | 1,34 | 0,38 | 0,45 | 0,73 | -0,7 | nein |
| EURGBP | woche | 54 | 0,52 | 0,54 | 0,48 | 0,51 | 0,58 | 0,82 | 0,69 | -6,2 | nein |
| EURGBP | tag | 100 | 0,96 | 0,54 | 0,48 | 0,69 | 0,44 | 0,63 | 0,44 | -9,7 | nein |
| EURJPY | woche | 52 | 0,50 | 0,57 | 0,56 | 0,69 | 0,49 | 0,55 | 0,41 | -5,9 | nein |
| EURJPY | tag | 78 | 0,75 | 0,44 | 0,43 | 0,37 | 0,52 | 0,34 | 1,60 | -9,9 | nein |
| GBPJPY | woche | 56 | 0,54 | 0,24 | 0,23 | 0,12 | 0,34 | 0,28 | 0,65 | -12,5 | nein |
| GBPJPY | tag | 80 | 0,77 | 0,59 | 0,58 | 0,55 | 0,64 | 0,37 | 1,13 | -7,2 | nein |
| EURCHF | woche | 47 | 0,45 | 0,82 | 0,71 | 1,15 | 0,49 | 0,43 | 1,29 | -1,8 | nein |
| EURCHF | tag | 93 | 0,89 | 0,55 | 0,46 | 0,49 | 0,63 | 0,76 | 0,53 | -8,5 | nein |
| XAGUSD | woche | 45 | 0,43 | 0,72 | 0,68 | 1,08 | 0,34 | 0,24 | 0,74 | -3,0 | nein |
| XAGUSD | tag | 77 | 0,74 | 0,99 | 0,94 | 1,14 | 0,84 | 0,31 | 0,79 | -0,1 | nein |
| WTIUSD | woche | 4 | 0,04 | 0,54 | 0,46 | - | 0,54 | 0,54 | 0,53 | -0,4 | nein |
| WTIUSD | tag | 8 | 0,08 | 2,72 | 2,69 | - | 2,72 | 2,72 | 0,53 | 1,6 | nein |
| SPXUSD | woche | 67 | 0,64 | 0,53 | 0,53 | 0,79 | 0,34 | 0,40 | 0,57 | -7,5 | nein |
| SPXUSD | tag | 61 | 0,59 | 0,71 | 0,70 | 0,60 | 0,92 | 0,92 | 1,27 | -3,7 | nein |
| NSXUSD | woche | 46 | 0,44 | 0,43 | 0,43 | 0,78 | 0,14 | 0,11 | 0,46 | -7,5 | nein |
| NSXUSD | tag | 73 | 0,70 | 1,01 | 1,00 | 0,64 | 2,44 | 2,44 | 0,74 | 0,2 | nein |
| GRXEUR | woche | 38 | 0,37 | 0,34 | 0,34 | 0,20 | 0,58 | 0,36 | 0,95 | -7,0 | nein |
| GRXEUR | tag | 69 | 0,66 | 0,52 | 0,52 | 0,40 | 0,75 | 0,85 | 0,98 | -6,6 | nein |
| UKXGBP | woche | 51 | 0,49 | 1,16 | 1,06 | 1,28 | 1,00 | 1,32 | 0,78 | 1,4 | nein |
| UKXGBP | tag | 64 | 0,62 | 0,56 | 0,53 | 0,61 | 0,50 | 0,42 | 0,69 | -5,4 | nein |
| JPXJPY | woche | 36 | 0,35 | 1,59 | 1,57 | 2,12 | 1,02 | 2,34 | 0,94 | 2,2 | nein |
| JPXJPY | tag | 37 | 0,36 | 1,55 | 1,20 | 1,45 | 1,88 | 2,95 | 0,53 | 2,2 | nein |
| XAUUSD | woche | 36 | 0,35 | 0,64 | 0,54 | 0,63 | 0,65 | 0,73 | 1,00 | -3,1 | nein |
| XAUUSD | tag | 83 | 0,80 | 1,37 | 1,37 | 1,25 | 1,60 | 0,85 | 1,35 | 4,2 | nein |
| AUDNZD | woche | 38 | 0,37 | 0,42 | 0,36 | 0,34 | 0,44 | 0,50 | 0,15 | -4,4 | nein |
| AUDNZD | tag | 47 | 0,45 | 1,11 | 1,01 | 2,10 | 0,37 | 0,37 | 1,07 | 0,6 | nein |
| GBPNZD | woche | 50 | 0,48 | 0,46 | 0,37 | 0,54 | 0,40 | 0,47 | 0,84 | -6,3 | nein |
| GBPNZD | tag | 63 | 0,61 | 0,52 | 0,48 | 0,33 | 1,15 | 1,05 | 0,95 | -6,0 | nein |

## Urteil

Teil A: kein Filter bestanden, alle Bots bleiben wie sie sind. Teil B: keine Regel auf keinem Markt bestanden. Keine Nachbesserung nach dem Ergebnis.
