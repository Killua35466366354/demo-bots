# Demo-Vergleich, Stand 2026-11-20

Nur Demokonten. Verglichen wird in R (1 R = Risiko bis zum Stop). Soll = Schnitt der Bewertung 2025-2026 im selben Zeitraum.

| # | Strategie | Gruppe | Demo-Trades | Summe R | Gewinnfaktor | Demo-€ | Soll bisher | Aufstieg |
|---|---|---|---|---|---|---|---|---|
| 1 | Gold-Bot C/B | verbessern | 2 | +6,12 | 7,06 | +94,00 | 3,5 Trades, +0,74 R | 2 von 100 Demo-Trades, 17 von 61 Tagen |
| 2 | Noise USD/JPY | labor | 8 | +0,01 | 1,12 | +0,16 | 5,5 Trades, +0,11 R | 8 von 100 Demo-Trades, 15 von 61 Tagen |
| 3 | Trend-Rücksetzer US500 | behalten | 0 | +0,00 | – | +0,00 | 0,6 Trades, +0,13 R | 0 von 100 Demo-Trades, 16 von 61 Tagen |
| 4 | Nasdaq Noise Long | behalten | 0 | +0,00 | – | +0,00 | 0,5 Trades, +0,05 R | 0 von 100 Demo-Trades, 16 von 61 Tagen |
| 5 | Trend-Rücksetzer US100 | behalten | 0 | +0,00 | – | +0,00 | 0,5 Trades, +0,05 R | 0 von 100 Demo-Trades, 16 von 61 Tagen |
| 6 | London GBP/USD | labor | 0 | +0,00 | – | +0,00 | 1,2 Trades, +0,13 R | 0 von 100 Demo-Trades, 15 von 61 Tagen |
| 7 | Gold Groß-Box, Stop 1,25-fach (Schatten) | zwilling | 0 | +0,00 | – | +0,00 | – | Zwilling: 0 von 40 Trades |
| 8 | Trend-Rücksetzer Dow | labor | 1 | -1,00 | 0,00 | -2,12 | 0,5 Trades, +0,04 R | 1 von 100 Demo-Trades, 15 von 61 Tagen |
| 9 | Vortag GBP/USD | behalten | 1 | -1,00 | 0,00 | -3,37 | 3,0 Trades, +0,38 R | 1 von 100 Demo-Trades, 16 von 61 Tagen |
| 10 | Vortag EUR/USD 1 x ATR (Mess-Bot) | messung | 1 | -1,00 | 0,00 | -7,01 | – | Mess-Bot: Vergleich mit Vortag EUR/USD, kein Aufstieg |
| 11 | Gold nur Long (Teil C) | messung | 1 | -1,01 | 0,00 | -19,16 | – | Mess-Zeile: C allein gegen C und B, Urteil mit dem Gold-Bot Ende Januar 2027 (verpasst C-Signale, solange B offen ist) |
| 12 | Vortag EUR/USD | behalten | 1 | -1,04 | 0,00 | -3,66 | 3,1 Trades, +0,99 R | 1 von 100 Demo-Trades, 16 von 61 Tagen |
| 13 | Vortag GBP/JPY | behalten | 4 | -4,08 | 0,00 | -18,09 | 2,0 Trades, +0,41 R | 4 von 100 Demo-Trades, 15 von 61 Tagen |

**Kombi (6 Kern-Strategien auf einem Konto):** 6 Trades, -6,12 R, Gewinnfaktor 0,00, Soll bisher 9,7 Trades und +2,01 R. Aufstieg: 6 von 100 Demo-Trades, 16 von 61 Tagen.

| Monat | Kombi-Trades | Summe R | mit 1.000 € bei 1 % |
|---|---|---|---|
| 2026-11 | 6 | -6,12 | -61 € |

**Gruppe aller Bots (19 feste Mitglieder, davon 1 herausgefallen, suche/VORAB_aufstieg_alle.yaml):** 58 Trades, +20,28 R, Gewinnfaktor 1,86. Aufstieg: 58 von 100 Demo-Trades, 17 von 61 Tagen.
Aus der Gruppe gefallen: pine-tp3 (Gewinnfaktor 0.58 nach 45 Trades).

## Auf Kirons Wunsch, außerhalb der Prüfung nach 15 und 40 Trades

Diese Bots haben ein festes Konto (suche/mitnutzer.py). Sie stehen nicht in der Rangliste und nicht in der Kombi. Ihr Urteil nach 40 Trades steht in ihrer eigenen Regeldatei. Den Weg zu echtem Geld regelt suche/VORAB_aufstieg_alle.yaml (Spalte Aufstieg).

| Bot | Konto | seit | Demo-Trades | Summe | Gewinnfaktor | Demo-€ | Urteil laut Bot | Regeldatei | Aufstieg |
|---|---|---|---|---|---|---|---|---|---|
| Nasdaq Eröffnungskerze | Account 1 | 2026-11-10 | 0 | +0,00 R | – | +0,00 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_scalping_opens.yaml | 0 von 100 Demo-Trades, 10 von 61 Tagen |
| DAX Eröffnungskerze | Account 1 | 2026-11-10 | 3 | -1,70 R | 0,16 | -8,25 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_scalping_opens.yaml | 3 von 100 Demo-Trades, 10 von 61 Tagen |
| Nikkei letzte halbe Stunde | Account 1 | 2026-11-10 | 3 | -0,35 % | 0,09 | -0,11 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_scalping_opens.yaml | 3 von 100 Demo-Trades, 10 von 61 Tagen |
| Gold-Staffel | Account 1 | 2026-11-10 | 1 | +0,25 R | – | +3,60 | Demo-Vorwärtstest, Vergleich mit dem Gold-Bot nach 40 Trades | suche/VORAB_gold_staffel.yaml | 1 von 100 Demo-Trades, 10 von 61 Tagen |
| Gold Groß-Box | Account 6 | 2026-11-10 | 8 | +8,65 R | 3,87 | +37,73 | läuft (8 von 40 Trades) | suche/VORAB_gold_grossbox.yaml | 8 von 100 Demo-Trades, 10 von 61 Tagen |
| Gold-Zonen Bruch | Account 2 | 2026-11-11 | 2 | -2,00 R | 0,00 | -9,79 | läuft (2 von 40 Trades) | suche/VORAB_gold_zonen_bot.yaml | 2 von 100 Demo-Trades, 9 von 61 Tagen |
| Gold 4-Std.-Ausbruch mit Tagestrend | Account 4 | 2026-11-12 | 4 | +2,20 R | 25,19 | +10,12 | läuft (4 von 40 Trades) | suche/VORAB_gold_ausbruch4h_bot.yaml | 4 von 100 Demo-Trades, 8 von 61 Tagen |
| 4-Std.-Ausbruch DAX, FTSE, Nikkei | Account 7 | 2026-11-19 | 0 | +0,00 R | – | +0,00 | läuft (0 von 40 Trades) | suche/VORAB_welt_ausbruch4h_bot.yaml | 0 von 100 Demo-Trades, 1 von 61 Tagen |
| Pine-Gold Hand auf Account 5 | Account 5 | 2026-11-10 | 23 | +13,87 R | 2,67 | +68,17 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_pine5m_abfang4h.yaml | 23 von 100 Demo-Trades, 10 von 61 Tagen |
| Pine-Gold TP 3 € | US500 | 2026-11-10 | 45 | -11,19 R | 0,58 | -55,03 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_pine5m.yaml | 45 von 100 Demo-Trades, 10 von 61 Tagen |

Der Gold-Bot zählt hier ab 2026-11-03 09:05 UTC (seit dem Stop 1 x ATR). Der Wochenbericht zählt alle seine Demo-Trades seit dem 31.10.2026, darum kann dort ein Trade mehr stehen.
