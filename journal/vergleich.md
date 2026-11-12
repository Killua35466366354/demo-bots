# Demo-Vergleich, Stand 2026-11-12

Nur Demokonten. Verglichen wird in R (1 R = Risiko bis zum Stop). Soll = Schnitt der Bewertung 2025-2026 im selben Zeitraum.

| # | Strategie | Gruppe | Demo-Trades | Summe R | Gewinnfaktor | Demo-€ | Soll bisher | Aufstieg |
|---|---|---|---|---|---|---|---|---|
| 1 | Noise USD/JPY | labor | 3 | +0,01 | 1,12 | +0,09 | 2,5 Trades, +0,05 R | 3 von 40 Demo-Trades |
| 2 | Trend-Rücksetzer US500 | behalten | 0 | +0,00 | – | +0,00 | 0,3 Trades, +0,07 R | 0 von 40 Demo-Trades |
| 3 | Nasdaq Noise Long | behalten | 0 | +0,00 | – | +0,00 | 0,2 Trades, +0,03 R | 0 von 40 Demo-Trades |
| 4 | Trend-Rücksetzer US100 | behalten | 0 | +0,00 | – | +0,00 | 0,3 Trades, +0,03 R | 0 von 40 Demo-Trades |
| 5 | Vortag EUR/USD | behalten | 0 | +0,00 | – | +0,00 | 1,5 Trades, +0,48 R | 0 von 40 Demo-Trades |
| 6 | Trend-Rücksetzer Dow | labor | 0 | +0,00 | – | +0,00 | 0,2 Trades, +0,02 R | 0 von 40 Demo-Trades |
| 7 | London GBP/USD | labor | 0 | +0,00 | – | +0,00 | 0,5 Trades, +0,06 R | 0 von 40 Demo-Trades |
| 8 | Vortag EUR/USD 1 x ATR (Mess-Bot) | messung | 0 | +0,00 | – | +0,00 | – | Mess-Bot: Vergleich mit Vortag EUR/USD, kein Aufstieg |
| 9 | Vortag GBP/USD | behalten | 1 | -1,00 | 0,00 | -3,37 | 1,5 Trades, +0,19 R | 1 von 40 Demo-Trades |
| 10 | Gold-Bot C/B | verbessern | 1 | -1,01 | 0,00 | -19,16 | 1,8 Trades, +0,39 R | 1 von 40 Demo-Trades |
| 11 | Gold nur Long (Teil C) | messung | 1 | -1,01 | 0,00 | -19,16 | – | Mess-Zeile: C allein gegen C und B, Urteil mit dem Gold-Bot Ende Januar 2027 (verpasst C-Signale, solange B offen ist) |
| 12 | Vortag GBP/JPY | behalten | 1 | -1,02 | 0,00 | -4,08 | 0,9 Trades, +0,19 R | 1 von 40 Demo-Trades |

**Kombi (6 Kern-Strategien auf einem Konto):** 2 Trades, -2,02 R, Gewinnfaktor 0,00, Soll bisher 4,7 Trades und +0,99 R. Aufstieg: 2 von 60 Demo-Trades.

| Monat | Kombi-Trades | Summe R | mit 1.000 € bei 1 % |
|---|---|---|---|
| 2026-11 | 2 | -2,02 | -20 € |

## Auf Kirons Wunsch, außerhalb der Prüfung nach 15 und 40 Trades

Diese Bots haben ein festes Konto (suche/mitnutzer.py). Sie stehen nicht in der Rangliste und nicht in der Kombi. Über jeden urteilt seine eigene Regeldatei, hier stehen sie nur, damit kein Urteil vergessen wird.

| Bot | Konto | seit | Demo-Trades | Summe R | Gewinnfaktor | Demo-€ | Urteil laut Bot | Regeldatei |
|---|---|---|---|---|---|---|---|---|
| Nasdaq Eröffnungskerze | Account 1 | 2026-11-10 | 0 | +0,00 | – | +0,00 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_scalping_opens.yaml |
| DAX Eröffnungskerze | Account 1 | 2026-11-10 | 2 | -2,02 | 0,00 | -9,82 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_scalping_opens.yaml |
| Nikkei letzte halbe Stunde | Account 1 | 2026-11-10 | 0 | +0,00 | – | +0,00 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_scalping_opens.yaml |
| Gold-Staffel | Account 1 | 2026-11-10 | 0 | +0,00 | – | +0,00 | Demo-Vorwärtstest, Vergleich mit dem Gold-Bot nach 40 Trades | suche/VORAB_gold_staffel.yaml |
| Gold Groß-Box | Account 6 | 2026-11-10 | 4 | -2,68 | 0,11 | -12,95 | läuft (4 von 40 Trades) | suche/VORAB_gold_grossbox.yaml |
| Gold-Zonen Bruch | Account 2 | 2026-11-11 | 0 | +0,00 | – | +0,00 | läuft (0 von 40 Trades) | suche/VORAB_gold_zonen_bot.yaml |
| Gold 4-Std.-Ausbruch mit Tagestrend | Account 4 | 2026-11-12 | 0 | +0,00 | – | +0,00 | läuft (0 von 40 Trades) | suche/VORAB_gold_ausbruch4h_bot.yaml |
| Pine-Gold Hand auf Account 5 | Account 5 | 2026-11-10 | 4 | -5,72 | 0,00 | -28,48 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_pine5m_abfang4h.yaml |
| Pine-Gold TP 3 € | US500 | 2026-11-10 | 9 | -11,46 | 0,10 | -56,75 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_pine5m.yaml |

Der Gold-Bot zählt hier ab 2026-11-03 09:05 UTC (seit dem Stop 1 x ATR). Der Wochenbericht zählt alle seine Demo-Trades seit dem 31.10.2026, darum kann dort ein Trade mehr stehen.
