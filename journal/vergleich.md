# Demo-Vergleich, Stand 2026-11-25

Nur Demokonten. Verglichen wird in R (1 R = Risiko bis zum Stop). Soll = Schnitt der Bewertung 2025-2026 im selben Zeitraum.

| # | Strategie | Gruppe | Demo-Trades | Summe R | Gewinnfaktor | Demo-€ | Soll bisher | Aufstieg |
|---|---|---|---|---|---|---|---|---|
| 1 | Gold-Bot C/B | verbessern | 4 | +10,29 | 6,12 | +181,00 | 4,5 Trades, +0,97 R | 4 von 100 Demo-Trades, 22 von 61 Tagen |
| 2 | Trend-Rücksetzer US500 | behalten | 0 | +0,00 | – | +0,00 | 0,8 Trades, +0,17 R | 0 von 100 Demo-Trades, 21 von 61 Tagen |
| 3 | Nasdaq Noise Long | behalten | 0 | +0,00 | – | +0,00 | 0,6 Trades, +0,07 R | 0 von 100 Demo-Trades, 21 von 61 Tagen |
| 4 | Trend-Rücksetzer US100 | behalten | 0 | +0,00 | – | +0,00 | 0,7 Trades, +0,07 R | 0 von 100 Demo-Trades, 21 von 61 Tagen |
| 5 | London GBP/USD | labor | 0 | +0,00 | – | +0,00 | 1,6 Trades, +0,17 R | 0 von 100 Demo-Trades, 20 von 61 Tagen |
| 6 | Noise USD/JPY | labor | 12 | -0,18 | 0,42 | -1,58 | 7,4 Trades, +0,14 R | 12 von 100 Demo-Trades, 20 von 61 Tagen |
| 7 | Trend-Rücksetzer Dow | labor | 1 | -1,00 | 0,00 | -2,12 | 0,7 Trades, +0,06 R | 1 von 100 Demo-Trades, 20 von 61 Tagen |
| 8 | Vortag GBP/USD | behalten | 1 | -1,00 | 0,00 | -3,37 | 4,0 Trades, +0,51 R | 1 von 100 Demo-Trades, 21 von 61 Tagen |
| 9 | Vortag EUR/USD 1 x ATR (Mess-Bot) | messung | 1 | -1,00 | 0,00 | -7,01 | – | Mess-Bot: Vergleich mit Vortag EUR/USD, kein Aufstieg |
| 10 | Gold nur Long (Teil C) | messung | 1 | -1,01 | 0,00 | -19,16 | – | Mess-Zeile: C allein gegen C und B, Urteil mit dem Gold-Bot Ende Januar 2027 (verpasst C-Signale, solange B offen ist) |
| 11 | Vortag EUR/USD | behalten | 1 | -1,04 | 0,00 | -3,66 | 4,1 Trades, +1,31 R | 1 von 100 Demo-Trades, 21 von 61 Tagen |
| 12 | Gold Groß-Box, Stop 1,25-fach (Schatten) | zwilling | 2 | -1,80 | 0,00 | +0,00 | – | Zwilling: 2 von 40 Trades |
| 13 | Vortag GBP/JPY | behalten | 4 | -4,08 | 0,00 | -18,09 | – | – |

**Kombi (6 Kern-Strategien auf einem Konto):** 6 Trades, -6,12 R, Gewinnfaktor 0,00, Soll bisher 10,2 Trades und +2,13 R. Aufstieg: 6 von 100 Demo-Trades, 21 von 61 Tagen.

| Monat | Kombi-Trades | Summe R | mit 1.000 € bei 1 % |
|---|---|---|---|
| 2026-11 | 6 | -6,12 | -61 € |

**Gruppe aller Bots (19 feste Mitglieder, davon 1 herausgefallen, suche/VORAB_aufstieg_alle.yaml):** 83 Trades, +40,89 R, Gewinnfaktor 2,20. Aufstieg: 83 von 100 Demo-Trades, 22 von 61 Tagen.
Aus der Gruppe gefallen: pine-tp3 (Gewinnfaktor 0.52 nach 49 Trades).

## Auf Kirons Wunsch, außerhalb der Prüfung nach 15 und 40 Trades

Diese Bots haben ein festes Konto (suche/mitnutzer.py). Sie stehen nicht in der Rangliste und nicht in der Kombi. Ihr Urteil nach 40 Trades steht in ihrer eigenen Regeldatei. Den Weg zu echtem Geld regelt suche/VORAB_aufstieg_alle.yaml (Spalte Aufstieg).

| Bot | Konto | seit | Demo-Trades | Summe | Gewinnfaktor | Demo-€ | Urteil laut Bot | Regeldatei | Aufstieg |
|---|---|---|---|---|---|---|---|---|---|
| Nasdaq Eröffnungskerze | Account 1 | 2026-11-10 | 1 | -1,01 R | 0,00 | -5,05 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_scalping_opens.yaml | 1 von 100 Demo-Trades, 15 von 61 Tagen |
| DAX Eröffnungskerze | Account 1 | 2026-11-10 | 3 | -1,70 R | 0,16 | -8,25 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_scalping_opens.yaml | 3 von 100 Demo-Trades, 15 von 61 Tagen |
| Nikkei letzte halbe Stunde | Account 1 | 2026-11-10 | 5 | -0,55 % | 0,06 | -0,17 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_scalping_opens.yaml | 5 von 100 Demo-Trades, 15 von 61 Tagen |
| Gold-Staffel | Account 1 | 2026-11-10 | 3 | +0,60 R | 2,11 | +13,19 | Demo-Vorwärtstest, Vergleich mit dem Gold-Bot nach 40 Trades | suche/VORAB_gold_staffel.yaml | 3 von 100 Demo-Trades, 15 von 61 Tagen |
| Gold Groß-Box | Account 6 | 2026-11-10 | 13 | +11,44 R | 3,28 | +49,96 | läuft (13 von 40 Trades) | suche/VORAB_gold_grossbox.yaml | 13 von 100 Demo-Trades, 15 von 61 Tagen |
| Gold-Zonen Bruch | Account 2 | 2026-11-11 | 2 | -2,00 R | 0,00 | -9,79 | läuft (2 von 40 Trades) | suche/VORAB_gold_zonen_bot.yaml | 2 von 100 Demo-Trades, 14 von 61 Tagen |
| Gold 4-Std.-Ausbruch mit Tagestrend | Account 4 | 2026-11-12 | 4 | +2,20 R | 25,19 | +10,12 | läuft (4 von 40 Trades) | suche/VORAB_gold_ausbruch4h_bot.yaml | 4 von 100 Demo-Trades, 13 von 61 Tagen |
| 4-Std.-Ausbruch DAX, FTSE, Nikkei | Account 7 | 2026-11-19 | 1 | -0,28 R | 0,00 | -1,39 | läuft (1 von 40 Trades) | suche/VORAB_welt_ausbruch4h_bot.yaml | 1 von 100 Demo-Trades, 6 von 61 Tagen |
| Bollinger Krypto umgedreht | Account 3 | 2026-11-20 | 4 | +1,78 R | 1,83 | +9,03 | läuft (4 von 40 Trades) | suche/VORAB_krypto_bollinger_bot.yaml | 4 von 100 Demo-Trades, 5 von 61 Tagen |
| Vorhersage-Modell Indizes | Account 6 | 2026-11-20 | 5 | +2,78 R | – | +11,38 | läuft (5 von 40 Trades) | suche/VORAB_modell_indizes_bot.yaml | 5 von 100 Demo-Trades, 5 von 61 Tagen |
| Tag nach einem VIX-Sprung | Account 5 | 2026-11-20 | 5 | +1,85 R | – | +8,87 | läuft (5 von 40 Trades) | suche/VORAB_vix_sprung_bot.yaml | 5 von 100 Demo-Trades, 5 von 61 Tagen |
| Williams %R | Account 7 | 2026-11-20 | 2 | +1,14 R | – | +4,37 | läuft (2 von 40 Trades) | suche/VORAB_williams_bot.yaml | 2 von 100 Demo-Trades, 5 von 61 Tagen |
| 4-Std.-Ausbruch Bitcoin, Ether | Account 5 | 2026-11-20 | 2 | -0,11 R | 0,38 | -0,47 | läuft (2 von 40 Trades) | suche/VORAB_krypto_ausbruch4h_bot.yaml | 2 von 100 Demo-Trades, 5 von 61 Tagen |
| Bündel aus 9 Bots | Vortag USDJPY | 2026-11-20 | 4 | -4,00 R | 0,00 | +0,00 | Urteil nach VORAB_aufstieg_alle.yaml (einzeln): 100 Demo-Trades, 61 Tage, Gewinnfaktor 1,3 | suche/VORAB_buendel9_bot.yaml | 4 von 100 Demo-Trades, 5 von 61 Tagen |
| Pine-Gold Hand auf Account 5 | Account 5 | 2026-11-10 | 34 | +28,36 R | 3,02 | +139,41 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_pine5m_abfang4h.yaml | 34 von 100 Demo-Trades, 15 von 61 Tagen |

Der Gold-Bot zählt hier ab 2026-11-03 09:05 UTC (seit dem Stop 1 x ATR). Der Wochenbericht zählt alle seine Demo-Trades seit dem 31.10.2026, darum kann dort ein Trade mehr stehen.
