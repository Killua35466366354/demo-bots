# Demo-Vergleich, Stand 2026-11-19

Nur Demokonten. Verglichen wird in R (1 R = Risiko bis zum Stop). Soll = Schnitt der Bewertung 2025-2026 im selben Zeitraum.

| # | Strategie | Gruppe | Demo-Trades | Summe R | Gewinnfaktor | Demo-€ | Soll bisher | Aufstieg |
|---|---|---|---|---|---|---|---|---|
| 1 | Gold-Bot C/B | verbessern | 2 | +6,12 | 7,06 | +94,00 | 3,3 Trades, +0,70 R | 2 von 100 Demo-Trades, 16 von 61 Tagen |
| 2 | Trend-Rücksetzer US500 | behalten | 0 | +0,00 | – | +0,00 | 0,6 Trades, +0,12 R | 0 von 100 Demo-Trades, 15 von 61 Tagen |
| 3 | Nasdaq Noise Long | behalten | 0 | +0,00 | – | +0,00 | 0,4 Trades, +0,05 R | 0 von 100 Demo-Trades, 15 von 61 Tagen |
| 4 | Trend-Rücksetzer US100 | behalten | 0 | +0,00 | – | +0,00 | 0,5 Trades, +0,05 R | 0 von 100 Demo-Trades, 15 von 61 Tagen |
| 5 | Trend-Rücksetzer Dow | labor | 0 | +0,00 | – | +0,00 | 0,5 Trades, +0,04 R | 0 von 100 Demo-Trades, 14 von 61 Tagen |
| 6 | London GBP/USD | labor | 0 | +0,00 | – | +0,00 | 1,1 Trades, +0,12 R | 0 von 100 Demo-Trades, 14 von 61 Tagen |
| 7 | Gold Groß-Box, Stop 1,25-fach (Schatten) | zwilling | 0 | +0,00 | – | +0,00 | – | Zwilling: 0 von 40 Trades |
| 8 | Noise USD/JPY | labor | 7 | -0,03 | 0,76 | -0,20 | 5,2 Trades, +0,10 R | 7 von 100 Demo-Trades, 14 von 61 Tagen |
| 9 | Vortag GBP/USD | behalten | 1 | -1,00 | 0,00 | -3,37 | 2,8 Trades, +0,36 R | 1 von 100 Demo-Trades, 15 von 61 Tagen |
| 10 | Vortag EUR/USD 1 x ATR (Mess-Bot) | messung | 1 | -1,00 | 0,00 | -7,01 | – | Mess-Bot: Vergleich mit Vortag EUR/USD, kein Aufstieg |
| 11 | Gold nur Long (Teil C) | messung | 1 | -1,01 | 0,00 | -19,16 | – | Mess-Zeile: C allein gegen C und B, Urteil mit dem Gold-Bot Ende Januar 2027 (verpasst C-Signale, solange B offen ist) |
| 12 | Vortag EUR/USD | behalten | 1 | -1,04 | 0,00 | -3,66 | 2,9 Trades, +0,93 R | 1 von 100 Demo-Trades, 15 von 61 Tagen |
| 13 | Vortag GBP/JPY | behalten | 3 | -3,02 | 0,00 | -13,05 | 1,9 Trades, +0,38 R | 3 von 100 Demo-Trades, 14 von 61 Tagen |

**Kombi (6 Kern-Strategien auf einem Konto):** 5 Trades, -5,06 R, Gewinnfaktor 0,00, Soll bisher 9,1 Trades und +1,89 R. Aufstieg: 5 von 100 Demo-Trades, 15 von 61 Tagen.

| Monat | Kombi-Trades | Summe R | mit 1.000 € bei 1 % |
|---|---|---|---|
| 2026-11 | 5 | -5,06 | -51 € |

**Gruppe aller Bots (19 feste Mitglieder, davon 1 herausgefallen, suche/VORAB_aufstieg_alle.yaml):** 52 Trades, +13,41 R, Gewinnfaktor 1,62. Aufstieg: 52 von 100 Demo-Trades, 16 von 61 Tagen.
Aus der Gruppe gefallen: pine-tp3 (Gewinnfaktor 0.72 nach 40 Trades).

## Auf Kirons Wunsch, außerhalb der Prüfung nach 15 und 40 Trades

Diese Bots haben ein festes Konto (suche/mitnutzer.py). Sie stehen nicht in der Rangliste und nicht in der Kombi. Ihr Urteil nach 40 Trades steht in ihrer eigenen Regeldatei. Den Weg zu echtem Geld regelt suche/VORAB_aufstieg_alle.yaml (Spalte Aufstieg).

| Bot | Konto | seit | Demo-Trades | Summe | Gewinnfaktor | Demo-€ | Urteil laut Bot | Regeldatei | Aufstieg |
|---|---|---|---|---|---|---|---|---|---|
| Nasdaq Eröffnungskerze | Account 1 | 2026-11-10 | 0 | +0,00 R | – | +0,00 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_scalping_opens.yaml | 0 von 100 Demo-Trades, 9 von 61 Tagen |
| DAX Eröffnungskerze | Account 1 | 2026-11-10 | 3 | -1,70 R | 0,16 | -8,25 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_scalping_opens.yaml | 3 von 100 Demo-Trades, 9 von 61 Tagen |
| Nikkei letzte halbe Stunde | Account 1 | 2026-11-10 | 3 | -0,35 % | 0,09 | -0,11 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_scalping_opens.yaml | 3 von 100 Demo-Trades, 9 von 61 Tagen |
| Gold-Staffel | Account 1 | 2026-11-10 | 1 | +0,25 R | – | +3,60 | Demo-Vorwärtstest, Vergleich mit dem Gold-Bot nach 40 Trades | suche/VORAB_gold_staffel.yaml | 1 von 100 Demo-Trades, 9 von 61 Tagen |
| Gold Groß-Box | Account 6 | 2026-11-10 | 7 | +3,04 R | 2,01 | +10,89 | läuft (7 von 40 Trades) | suche/VORAB_gold_grossbox.yaml | 7 von 100 Demo-Trades, 9 von 61 Tagen |
| Gold-Zonen Bruch | Account 2 | 2026-11-11 | 2 | -2,00 R | 0,00 | -9,79 | läuft (2 von 40 Trades) | suche/VORAB_gold_zonen_bot.yaml | 2 von 100 Demo-Trades, 8 von 61 Tagen |
| Gold 4-Std.-Ausbruch mit Tagestrend | Account 4 | 2026-11-12 | 3 | +1,54 R | 17,92 | +6,97 | läuft (3 von 40 Trades) | suche/VORAB_gold_ausbruch4h_bot.yaml | 3 von 100 Demo-Trades, 7 von 61 Tagen |
| 4-Std.-Ausbruch DAX, FTSE, Nikkei | Account 7 | 2026-11-19 | 0 | +0,00 R | – | +0,00 | läuft (0 von 40 Trades) | suche/VORAB_welt_ausbruch4h_bot.yaml | 0 von 100 Demo-Trades, 0 von 61 Tagen |
| Pine-Gold Hand auf Account 5 | Account 5 | 2026-11-10 | 22 | +11,25 R | 2,35 | +55,48 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_pine5m_abfang4h.yaml | 22 von 100 Demo-Trades, 9 von 61 Tagen |
| Pine-Gold TP 3 € | US500 | 2026-11-10 | 40 | -5,92 R | 0,72 | -29,27 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_pine5m.yaml | 40 von 100 Demo-Trades, 9 von 61 Tagen |

Der Gold-Bot zählt hier ab 2026-11-03 09:05 UTC (seit dem Stop 1 x ATR). Der Wochenbericht zählt alle seine Demo-Trades seit dem 31.10.2026, darum kann dort ein Trade mehr stehen.
