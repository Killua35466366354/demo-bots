# Demo-Vergleich, Stand 2026-11-17

Nur Demokonten. Verglichen wird in R (1 R = Risiko bis zum Stop). Soll = Schnitt der Bewertung 2025-2026 im selben Zeitraum.

| # | Strategie | Gruppe | Demo-Trades | Summe R | Gewinnfaktor | Demo-€ | Soll bisher | Aufstieg |
|---|---|---|---|---|---|---|---|---|
| 1 | Trend-Rücksetzer US500 | behalten | 0 | +0,00 | – | +0,00 | 0,5 Trades, +0,11 R | 0 von 40 Demo-Trades |
| 2 | Nasdaq Noise Long | behalten | 0 | +0,00 | – | +0,00 | 0,4 Trades, +0,04 R | 0 von 40 Demo-Trades |
| 3 | Trend-Rücksetzer US100 | behalten | 0 | +0,00 | – | +0,00 | 0,4 Trades, +0,04 R | 0 von 40 Demo-Trades |
| 4 | Trend-Rücksetzer Dow | labor | 0 | +0,00 | – | +0,00 | 0,4 Trades, +0,03 R | 0 von 40 Demo-Trades |
| 5 | London GBP/USD | labor | 0 | +0,00 | – | +0,00 | 0,9 Trades, +0,10 R | 0 von 40 Demo-Trades |
| 6 | Noise USD/JPY | labor | 5 | -0,02 | 0,76 | -0,18 | 4,4 Trades, +0,08 R | 5 von 40 Demo-Trades |
| 7 | Vortag GBP/USD | behalten | 1 | -1,00 | 0,00 | -3,37 | 2,4 Trades, +0,31 R | 1 von 40 Demo-Trades |
| 8 | Vortag EUR/USD 1 x ATR (Mess-Bot) | messung | 1 | -1,00 | 0,00 | -7,01 | – | Mess-Bot: Vergleich mit Vortag EUR/USD, kein Aufstieg |
| 9 | Gold-Bot C/B | verbessern | 1 | -1,01 | 0,00 | -19,16 | 2,8 Trades, +0,61 R | 1 von 40 Demo-Trades |
| 10 | Gold nur Long (Teil C) | messung | 1 | -1,01 | 0,00 | -19,16 | – | Mess-Zeile: C allein gegen C und B, Urteil mit dem Gold-Bot Ende Januar 2027 (verpasst C-Signale, solange B offen ist) |
| 11 | Vortag EUR/USD | behalten | 1 | -1,04 | 0,00 | -3,66 | 2,5 Trades, +0,80 R | 1 von 40 Demo-Trades |
| 12 | Vortag GBP/JPY | behalten | 3 | -3,02 | 0,00 | -13,05 | 1,6 Trades, +0,33 R | 3 von 40 Demo-Trades |

**Kombi (6 Kern-Strategien auf einem Konto):** 5 Trades, -5,06 R, Gewinnfaktor 0,00, Soll bisher 7,8 Trades und +1,63 R. Aufstieg: 5 von 60 Demo-Trades.

| Monat | Kombi-Trades | Summe R | mit 1.000 € bei 1 % |
|---|---|---|---|
| 2026-11 | 5 | -5,06 | -51 € |

## Auf Kirons Wunsch, außerhalb der Prüfung nach 15 und 40 Trades

Diese Bots haben ein festes Konto (suche/mitnutzer.py). Sie stehen nicht in der Rangliste und nicht in der Kombi. Über jeden urteilt seine eigene Regeldatei, hier stehen sie nur, damit kein Urteil vergessen wird.

| Bot | Konto | seit | Demo-Trades | Summe | Gewinnfaktor | Demo-€ | Urteil laut Bot | Regeldatei |
|---|---|---|---|---|---|---|---|---|
| Nasdaq Eröffnungskerze | Account 1 | 2026-11-10 | 0 | +0,00 R | – | +0,00 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_scalping_opens.yaml |
| DAX Eröffnungskerze | Account 1 | 2026-11-10 | 3 | -1,70 R | 0,16 | -8,25 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_scalping_opens.yaml |
| Nikkei letzte halbe Stunde | Account 1 | 2026-11-10 | 1 | +0,03 % | – | +0,01 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_scalping_opens.yaml |
| Gold-Staffel | Account 1 | 2026-11-10 | 1 | +0,25 R | – | +3,60 | Demo-Vorwärtstest, Vergleich mit dem Gold-Bot nach 40 Trades | suche/VORAB_gold_staffel.yaml |
| Gold Groß-Box | Account 6 | 2026-11-10 | 7 | +3,04 R | 2,01 | +10,89 | läuft (7 von 40 Trades) | suche/VORAB_gold_grossbox.yaml |
| Gold-Zonen Bruch | Account 2 | 2026-11-11 | 2 | -2,00 R | 0,00 | -9,79 | läuft (2 von 40 Trades) | suche/VORAB_gold_zonen_bot.yaml |
| Gold 4-Std.-Ausbruch mit Tagestrend | Account 4 | 2026-11-12 | 2 | +0,89 R | 10,73 | +4,09 | läuft (2 von 40 Trades) | suche/VORAB_gold_ausbruch4h_bot.yaml |
| Pine-Gold Hand auf Account 5 | Account 5 | 2026-11-10 | 16 | +5,51 R | 1,66 | +27,22 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_pine5m_abfang4h.yaml |
| Pine-Gold TP 3 € | US500 | 2026-11-10 | 29 | -5,70 R | 0,65 | -28,40 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_pine5m.yaml |

Der Gold-Bot zählt hier ab 2026-11-03 09:05 UTC (seit dem Stop 1 x ATR). Der Wochenbericht zählt alle seine Demo-Trades seit dem 31.10.2026, darum kann dort ein Trade mehr stehen.
