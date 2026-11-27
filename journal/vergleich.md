# Demo-Vergleich, Stand 2026-11-27

Nur Demokonten. Verglichen wird in R (1 R = Risiko bis zum Stop). Soll = Schnitt der Bewertung 2025-2026 im selben Zeitraum.

| # | Strategie | Gruppe | Demo-Trades | Summe R | Gewinnfaktor | Demo-€ | Soll bisher | Aufstieg |
|---|---|---|---|---|---|---|---|---|
| 1 | Gold-Bot C/B | verbessern | 6 | +8,28 | 3,06 | +134,58 | 4,9 Trades, +1,06 R | 6 von 100 Demo-Trades, 24 von 61 Tagen |
| 2 | Gold Groß-Box, Stop 1,25-fach (Schatten) | zwilling | 8 | +1,96 | 1,70 | +0,00 | – | Zwilling: 8 von 40 Trades |
| 3 | Trend-Rücksetzer US500 | behalten | 0 | +0,00 | – | +0,00 | 0,9 Trades, +0,19 R | 0 von 100 Demo-Trades, 23 von 61 Tagen |
| 4 | Nasdaq Noise Long | behalten | 0 | +0,00 | – | +0,00 | 0,7 Trades, +0,08 R | 0 von 100 Demo-Trades, 23 von 61 Tagen |
| 5 | Trend-Rücksetzer US100 | behalten | 0 | +0,00 | – | +0,00 | 0,8 Trades, +0,08 R | 0 von 100 Demo-Trades, 23 von 61 Tagen |
| 6 | London GBP/USD | labor | 0 | +0,00 | – | +0,00 | 1,7 Trades, +0,19 R | 0 von 100 Demo-Trades, 22 von 61 Tagen |
| 7 | Noise USD/JPY | labor | 14 | -0,23 | 0,35 | -2,07 | 8,2 Trades, +0,16 R | 14 von 100 Demo-Trades, 22 von 61 Tagen |
| 8 | Trend-Rücksetzer Dow | labor | 1 | -1,00 | 0,00 | -2,12 | 0,7 Trades, +0,06 R | 1 von 100 Demo-Trades, 22 von 61 Tagen |
| 9 | Gold nur Long (Teil C) | messung | 1 | -1,01 | 0,00 | -19,16 | – | Mess-Zeile: C allein gegen C und B, Urteil mit dem Gold-Bot Ende Januar 2027 (verpasst C-Signale, solange B offen ist) |
| 10 | Vortag GBP/USD | behalten | 2 | -2,00 | 0,00 | -8,99 | 4,4 Trades, +0,56 R | 2 von 100 Demo-Trades, 23 von 61 Tagen |
| 11 | Vortag EUR/USD 1 x ATR (Mess-Bot) | messung | 2 | -2,00 | 0,00 | -16,12 | – | Mess-Bot: Vergleich mit Vortag EUR/USD, kein Aufstieg |
| 12 | Vortag EUR/USD | behalten | 2 | -2,04 | 0,00 | -8,85 | 4,5 Trades, +1,44 R | 2 von 100 Demo-Trades, 23 von 61 Tagen |
| 13 | Vortag GBP/JPY | behalten | 4 | -4,08 | 0,00 | -18,09 | – | – |

**Kombi (6 Kern-Strategien auf einem Konto):** 8 Trades, -8,12 R, Gewinnfaktor 0,00, Soll bisher 11,3 Trades und +2,35 R. Aufstieg: 8 von 100 Demo-Trades, 23 von 61 Tagen.

| Monat | Kombi-Trades | Summe R | mit 1.000 € bei 1 % |
|---|---|---|---|
| 2026-11 | 8 | -8,12 | -81 € |

**Gruppe aller Bots (19 feste Mitglieder, davon 1 herausgefallen, suche/VORAB_aufstieg_alle.yaml):** 104 Trades, +20,06 R, Gewinnfaktor 1,36. Aufstieg: 104 von 100 Demo-Trades, 24 von 61 Tagen.
Aus der Gruppe gefallen: pine-tp3 (Gewinnfaktor 0.52 nach 49 Trades).

## Auf Kirons Wunsch, außerhalb der Prüfung nach 15 und 40 Trades

Diese Bots haben ein festes Konto (suche/mitnutzer.py). Sie stehen nicht in der Rangliste und nicht in der Kombi. Ihr Urteil nach 40 Trades steht in ihrer eigenen Regeldatei. Den Weg zu echtem Geld regelt suche/VORAB_aufstieg_alle.yaml (Spalte Aufstieg).

| Bot | Konto | seit | Demo-Trades | Summe | Gewinnfaktor | Demo-€ | Urteil laut Bot | Regeldatei | Aufstieg |
|---|---|---|---|---|---|---|---|---|---|
| Nasdaq Eröffnungskerze | Account 1 | 2026-11-10 | 1 | -1,01 R | 0,00 | -5,05 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_scalping_opens.yaml | 1 von 100 Demo-Trades, 17 von 61 Tagen |
| DAX Eröffnungskerze | Account 1 | 2026-11-10 | 3 | -1,70 R | 0,16 | -8,25 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_scalping_opens.yaml | 3 von 100 Demo-Trades, 17 von 61 Tagen |
| Nikkei letzte halbe Stunde | Account 1 | 2026-11-10 | 5 | -0,55 % | 0,06 | -0,17 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_scalping_opens.yaml | 5 von 100 Demo-Trades, 17 von 61 Tagen |
| Gold-Staffel | Account 1 | 2026-11-10 | 5 | -0,69 R | 0,62 | -15,21 | Demo-Vorwärtstest, Vergleich mit dem Gold-Bot nach 40 Trades | suche/VORAB_gold_staffel.yaml | 5 von 100 Demo-Trades, 17 von 61 Tagen |
| Gold Groß-Box | Account 6 | 2026-11-10 | 16 | +10,72 R | 2,76 | +46,36 | läuft (16 von 40 Trades) | suche/VORAB_gold_grossbox.yaml | 16 von 100 Demo-Trades, 17 von 61 Tagen |
| Gold-Zonen Bruch | Account 2 | 2026-11-11 | 3 | -3,01 R | 0,00 | -14,57 | läuft (3 von 40 Trades) | suche/VORAB_gold_zonen_bot.yaml | 3 von 100 Demo-Trades, 16 von 61 Tagen |
| Gold 4-Std.-Ausbruch mit Tagestrend | Account 4 | 2026-11-12 | 5 | +1,62 R | 3,44 | +7,26 | läuft (5 von 40 Trades) | suche/VORAB_gold_ausbruch4h_bot.yaml | 5 von 100 Demo-Trades, 15 von 61 Tagen |
| 4-Std.-Ausbruch DAX, FTSE, Nikkei | Account 7 | 2026-11-19 | 1 | -0,28 R | 0,00 | -1,39 | läuft (1 von 40 Trades) | suche/VORAB_welt_ausbruch4h_bot.yaml | 1 von 100 Demo-Trades, 8 von 61 Tagen |
| Bollinger Krypto umgedreht | Account 3 | 2026-11-20 | 8 | -2,36 R | 0,62 | -11,53 | läuft (8 von 40 Trades) | suche/VORAB_krypto_bollinger_bot.yaml | 8 von 100 Demo-Trades, 7 von 61 Tagen |
| Vorhersage-Modell Indizes | Account 6 | 2026-11-20 | 5 | +2,78 R | – | +11,38 | läuft (5 von 40 Trades) | suche/VORAB_modell_indizes_bot.yaml | 5 von 100 Demo-Trades, 7 von 61 Tagen |
| Tag nach einem VIX-Sprung | Account 5 | 2026-11-20 | 5 | +1,85 R | – | +8,87 | läuft (5 von 40 Trades) | suche/VORAB_vix_sprung_bot.yaml | 5 von 100 Demo-Trades, 7 von 61 Tagen |
| Williams %R | Account 7 | 2026-11-20 | 2 | +1,14 R | – | +4,37 | läuft (2 von 40 Trades) | suche/VORAB_williams_bot.yaml | 2 von 100 Demo-Trades, 7 von 61 Tagen |
| 4-Std.-Ausbruch Bitcoin, Ether | Account 5 | 2026-11-20 | 3 | -0,73 R | 0,08 | -3,56 | läuft (3 von 40 Trades) | suche/VORAB_krypto_ausbruch4h_bot.yaml | 3 von 100 Demo-Trades, 7 von 61 Tagen |
| Bündel ohne Gold | Vortag USDJPY | 2026-11-20 | 7 | -2,34 R | 0,55 | +0,00 | Urteil nach VORAB_aufstieg_alle.yaml (einzeln): 100 Demo-Trades, 61 Tage, Gewinnfaktor 1,3 | suche/VORAB_buendel9_ohne_gold.yaml | 7 von 100 Demo-Trades, 7 von 61 Tagen |
| Gold-Bündel aus 3 Bots | Vortag USDJPY | 2026-11-26 | 0 | +0,00 R | – | +0,00 | Urteil nach VORAB_aufstieg_alle.yaml (einzeln): 100 Demo-Trades, 61 Tage, Gewinnfaktor 1,3 | suche/VORAB_gold_buendel_bot.yaml | 0 von 100 Demo-Trades, 1 von 61 Tagen |
| V1 mit wachsendem Einsatz | Account 3 | 2026-11-26 | 0 | +0,00 R | – | +0,00 | Urteil nach VORAB_aufstieg_alle.yaml (einzeln): 100 Demo-Trades, 61 Tage, Gewinnfaktor 1,3 | suche/VORAB_v1_wachsend_bot.yaml | 0 von 100 Demo-Trades, 1 von 61 Tagen |
| Pine-Gold Hand auf Account 5 | Account 5 | 2026-11-10 | 42 | +15,19 R | 1,56 | +74,31 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_pine5m_abfang4h.yaml | 42 von 100 Demo-Trades, 17 von 61 Tagen |

Der Gold-Bot zählt hier ab 2026-11-03 09:05 UTC (seit dem Stop 1 x ATR). Der Wochenbericht zählt alle seine Demo-Trades seit dem 31.10.2026, darum kann dort ein Trade mehr stehen.
