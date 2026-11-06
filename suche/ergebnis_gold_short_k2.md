# Gold-Short-Bot, Komitee 2: Ergebnis

Vorab: suche/VORAB_gold_short_k2.yaml (sha256 07f44b83a5fb…). Zeitraum A Einstieg 01.11.2024 bis 30.10.2026, Kontrolle 01.11.2022 bis 31.10.2024. PF_R = Gewinnfaktor in R. Offene Trades am Ende mit Marktwert.

| Regel | Trades | PF_R | Summe R | robust | Zufall | Hälfte 1 | Hälfte 2 | 2026 | Kontrolle PF_R | Kontrolle R | bestanden |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Bot heute (Vergleich) | 472 | 0,95 | -7,2 | 0,93 | 78,0 | 0,84 | 1,05 | 1,35 | 0,68 | -67,4 | – |
| Vorschuss | 464 | 1,00 | 0,3 | 0,98 | 77,5 | 0,96 | 1,03 | 1,32 | 0,75 | -49,8 | nein |
| Sitzungs-Ernte | 475 | 0,98 | -2,9 | 0,96 | 84,5 | 0,86 | 1,08 | 1,38 | 0,63 | -76,3 | nein |
| Reife-Prüfer | 492 | 1,00 | 0,2 | 0,99 | 87,0 | 0,81 | 1,16 | 1,46 | 0,67 | -73,5 | nein |
| Läufer | 421 | 0,70 | -38,8 | 0,69 | 28,5 | 0,49 | 0,89 | 1,20 | 0,65 | -69,6 | nein |
| Doppelte Box | 448 | 1,07 | 12,1 | 1,06 | 81,5 | 0,81 | 1,27 | 1,58 | 0,70 | -69,9 | nein |
| Longs dazu (nur Longs gewertet) | 793 | 1,19 | 43,5 | 1,13 | 100,0 | 1,33 | 0,99 | 0,90 | 1,01 | 1,5 | nein |

Bestanden nur mit mindestens 100 Trades, PF_R ab 1,3, robust ab 1,15, Zufall ab 95, beide Hälften, 2026 und Kontrolle über 1,0.

Longs und Shorts zusammen (nur Info): 1265 Trades, PF_R 1,10, 36,3 R; Kontrolle PF_R 0,85, -65,9 R.

## Nachbarwerte (nur Stabilität)

| Variante | Trades | PF_R | Summe R |
|---|---:|---:|---:|
| vorschuss_0.4 | 466 | 1,01 | 1,8 |
| vorschuss_0.6 | 467 | 1,01 | 1,3 |
| sitzungs_ernte_0.2 | 476 | 0,99 | -1,3 |
| sitzungs_ernte_0.4 | 474 | 0,96 | -5,4 |
| reife_1.5 | 495 | 0,98 | -2,8 |
| reife_2.5 | 489 | 1,00 | -0,3 |

## Kirons Beispiele (Kerzen bis 05.11.2026, Dukascopy)

| Regel | #461 | #472 | #473 | Summe ohne die drei (bei Longs dazu: Shorts und Longs) |
|---|---|---|---|---:|
| Bot heute (Vergleich) | 0,00 R (halten) | -1,02 R (stop) | -1,00 R (stop) | -8,8 |
| Vorschuss | 0,00 R (halten) | kein Trade (Seite hatte schon die Höchstzahl offener Trades) | -0,50 R (tp1, stop) | -2,5 |
| Sitzungs-Ernte | 0,00 R (halten) | 0,36 R (ernte, einstand) | 0,31 R (ernte, einstand) | -4,6 |
| Reife-Prüfer | 0,00 R (halten) | -1,02 R (stop) | -1,00 R (stop) | -0,9 |
| Läufer | 0,00 R (pruefer) | -1,02 R (stop) | -1,00 R (stop) | -41,9 |
| Doppelte Box | 0,00 R (halten) | kein Trade (Seite hatte schon die Höchstzahl offener Trades) | -1,00 R (stop) | 9,4 |
| Longs dazu (nur Longs gewertet) | 0,00 R (halten) | -1,02 R (stop) | -1,00 R (stop) | 34,7 |

## Gold steigt oder fällt (Schluss über oder unter dem von 20 Handelstagen vorher, nur Info)

| Regel | steigt Trades | steigt PF_R | steigt R | fällt Trades | fällt PF_R | fällt R |
|---|---:|---:|---:|---:|---:|---:|
| Bot heute (Vergleich) | 153 | 0,81 | -9,6 | 319 | 1,02 | 2,3 |
| Vorschuss | 155 | 0,86 | -6,7 | 309 | 1,07 | 7,0 |
| Sitzungs-Ernte | 154 | 0,88 | -6,0 | 321 | 1,03 | 3,1 |
| Reife-Prüfer | 154 | 0,82 | -9,2 | 338 | 1,09 | 9,4 |
| Läufer | 145 | 0,47 | -25,5 | 276 | 0,84 | -13,4 |
| Doppelte Box | 147 | 0,86 | -8,6 | 301 | 1,19 | 20,7 |
| Longs dazu (nur Longs gewertet) | 618 | 1,39 | 65,6 | 175 | 0,62 | -22,1 |

## Je Seite, Rückgang und Ausstiege (Zeitraum A)

- **Bot heute (Vergleich)**: gross_klein_3 141 Trades PF 1,08 3,7 R, gross_box_kerze 260 Trades PF 0,91 -7,6 R, gross_box 71 Trades PF 0,82 -3,3 R. Größter Rückgang 44,0 R, gesperrt 39. Ausstiege: stop 144/-145,3 R, pruefer 130/-0,2 R, halten 14/-0,1 R, tp2 1/1,5 R, tp1 2/3,0 R, offen 2/3,2 R, gegensignal 5/4,3 R, einstand 110/28,0 R, tp3 22/33,0 R, neue_box 42/65,3 R.
- **Vorschuss**: gross_klein_3 134 Trades PF 1,19 7,5 R, gross_box_kerze 260 Trades PF 1,01 1,2 R, gross_box 70 Trades PF 0,54 -8,4 R. Größter Rückgang 42,0 R, gesperrt 32. Ausstiege: stop 158/-141,2 R, pruefer 113/-0,1 R, halten 8/-0,1 R, tp1 2/2,8 R, tp2 3/4,2 R, gegensignal 6/4,8 R, offen 2/9,4 R, einstand 98/9,6 R, tp3 23/32,6 R, neue_box 51/78,2 R.
- **Sitzungs-Ernte**: gross_klein_3 142 Trades PF 1,11 4,7 R, gross_box_kerze 261 Trades PF 0,94 -4,6 R, gross_box 72 Trades PF 0,83 -3,1 R. Größter Rückgang 39,4 R, gesperrt 40. Ausstiege: stop 140/-141,2 R, pruefer 128/-0,1 R, halten 11/-0,1 R, ernte 2/0,6 R, tp2 1/1,5 R, tp1 2/3,0 R, offen 2/3,3 R, gegensignal 5/4,3 R, einstand 122/31,9 R, tp3 22/32,6 R, neue_box 40/61,4 R.
- **Reife-Prüfer**: gross_klein_3 141 Trades PF 1,07 3,2 R, gross_box_kerze 275 Trades PF 0,97 -2,5 R, gross_box 76 Trades PF 0,97 -0,5 R. Größter Rückgang 41,2 R, gesperrt 40. Ausstiege: stop 148/-149,3 R, pruefer 139/-0,2 R, halten 14/-0,1 R, tp2 1/1,5 R, gegensignal 3/2,1 R, tp1 2/3,0 R, offen 2/3,2 R, neue_box 8/4,0 R, nachzug 16/14,8 R, einstand 104/26,5 R, tp3 20/30,0 R, reife 35/64,6 R.
- **Läufer**: gross_klein_3 130 Trades PF 1,07 2,9 R, gross_box_kerze 234 Trades PF 0,54 -35,4 R, gross_box 57 Trades PF 0,48 -6,4 R. Größter Rückgang 63,1 R, gesperrt 31. Ausstiege: stop 129/-130,2 R, pruefer 126/-0,2 R, halten 5/-0,0 R, offen 2/3,2 R, bruch_4h 9/20,3 R, einstand 126/33,1 R, gegensignal 24/35,0 R.
- **Doppelte Box**: gross_klein_3 125 Trades PF 1,21 9,9 R, gross_box_kerze 256 Trades PF 0,92 -8,1 R, gross_box 67 Trades PF 1,46 10,3 R. Größter Rückgang 59,0 R, gesperrt 42. Ausstiege: stop 168/-170,3 R, halten 26/-0,2 R, pruefer 140/-0,2 R, offen 2/11,3 R, einstand 38/20,2 R, tp3 7/21,0 R, gegensignal 18/30,0 R, neue_box 49/100,2 R.
- **Longs dazu (nur Longs gewertet)**: gross_klein_3 207 Trades PF 1,50 25,5 R, gross_box_kerze 485 Trades PF 1,14 20,7 R, gross_box 101 Trades PF 0,91 -2,7 R. Größter Rückgang 30,8 R, gesperrt 39. Ausstiege: stop 220/-224,9 R, halten 18/-0,4 R, pruefer 252/1,8 R, tp1 1/3,4 R, tp2 6/8,8 R, gegensignal 17/13,2 R, tp3 25/37,2 R, einstand 164/42,3 R, neue_box 90/162,1 R.
