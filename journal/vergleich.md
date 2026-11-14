# Demo-Vergleich, Stand 2026-11-14

Nur Demokonten. Verglichen wird in R (1 R = Risiko bis zum Stop). Soll = Schnitt der Bewertung 2025-2026 im selben Zeitraum.

| # | Strategie | Gruppe | Demo-Trades | Summe R | Gewinnfaktor | Demo-€ | Soll bisher | Aufstieg |
|---|---|---|---|---|---|---|---|---|
| 1 | Noise USD/JPY | labor | 3 | +0,01 | 1,12 | +0,09 | 3,2 Trades, +0,06 R | 3 von 40 Demo-Trades |
| 2 | Trend-Rücksetzer US500 | behalten | 0 | +0,00 | – | +0,00 | 0,4 Trades, +0,08 R | 0 von 40 Demo-Trades |
| 3 | Nasdaq Noise Long | behalten | 0 | +0,00 | – | +0,00 | 0,3 Trades, +0,03 R | 0 von 40 Demo-Trades |
| 4 | Trend-Rücksetzer US100 | behalten | 0 | +0,00 | – | +0,00 | 0,3 Trades, +0,03 R | 0 von 40 Demo-Trades |
| 5 | Trend-Rücksetzer Dow | labor | 0 | +0,00 | – | +0,00 | 0,3 Trades, +0,02 R | 0 von 40 Demo-Trades |
| 6 | London GBP/USD | labor | 0 | +0,00 | – | +0,00 | 0,7 Trades, +0,08 R | 0 von 40 Demo-Trades |
| 7 | Vortag GBP/USD | behalten | 1 | -1,00 | 0,00 | -3,37 | 1,9 Trades, +0,23 R | 1 von 40 Demo-Trades |
| 8 | Vortag EUR/USD 1 x ATR (Mess-Bot) | messung | 1 | -1,00 | 0,00 | -7,01 | – | Mess-Bot: Vergleich mit Vortag EUR/USD, kein Aufstieg |
| 9 | Gold-Bot C/B | verbessern | 1 | -1,01 | 0,00 | -19,16 | 2,2 Trades, +0,47 R | 1 von 40 Demo-Trades |
| 10 | Gold nur Long (Teil C) | messung | 1 | -1,01 | 0,00 | -19,16 | – | Mess-Zeile: C allein gegen C und B, Urteil mit dem Gold-Bot Ende Januar 2027 (verpasst C-Signale, solange B offen ist) |
| 11 | Vortag EUR/USD | behalten | 1 | -1,04 | 0,00 | -3,66 | 1,9 Trades, +0,61 R | 1 von 40 Demo-Trades |
| 12 | Vortag GBP/JPY | behalten | 3 | -3,02 | 0,00 | -13,05 | 1,2 Trades, +0,24 R | 3 von 40 Demo-Trades |

**Kombi (6 Kern-Strategien auf einem Konto):** 5 Trades, -5,06 R, Gewinnfaktor 0,00, Soll bisher 6,0 Trades und +1,22 R. Aufstieg: 5 von 60 Demo-Trades.

| Monat | Kombi-Trades | Summe R | mit 1.000 € bei 1 % |
|---|---|---|---|
| 2026-11 | 5 | -5,06 | -51 € |

## Auf Kirons Wunsch, außerhalb der Prüfung nach 15 und 40 Trades

Diese Bots haben ein festes Konto (suche/mitnutzer.py). Sie stehen nicht in der Rangliste und nicht in der Kombi. Über jeden urteilt seine eigene Regeldatei, hier stehen sie nur, damit kein Urteil vergessen wird.

| Bot | Konto | seit | Demo-Trades | Summe R | Gewinnfaktor | Demo-€ | Urteil laut Bot | Regeldatei |
|---|---|---|---|---|---|---|---|---|
| Nasdaq Eröffnungskerze | Account 1 | 2026-11-10 | 0 | +0,00 | – | +0,00 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_scalping_opens.yaml |
| DAX Eröffnungskerze | Account 1 | 2026-11-10 | 3 | -1,70 | 0,16 | -8,25 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_scalping_opens.yaml |
| Nikkei letzte halbe Stunde | Account 1 | 2026-11-10 | 0 | +0,00 | – | +0,00 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_scalping_opens.yaml |
| Gold-Staffel | Account 1 | 2026-11-10 | 1 | +0,25 | – | +3,60 | Demo-Vorwärtstest, Vergleich mit dem Gold-Bot nach 40 Trades | suche/VORAB_gold_staffel.yaml |
| Gold Groß-Box | Account 6 | 2026-11-10 | 6 | +2,03 | 1,67 | +9,44 | läuft (6 von 40 Trades) | suche/VORAB_gold_grossbox.yaml |
| Gold-Zonen Bruch | Account 2 | 2026-11-11 | 1 | -1,00 | 0,00 | -4,85 | läuft (1 von 40 Trades) | suche/VORAB_gold_zonen_bot.yaml |
| Gold 4-Std.-Ausbruch mit Tagestrend | Account 4 | 2026-11-12 | 1 | +0,98 | – | +4,52 | läuft (1 von 40 Trades) | suche/VORAB_gold_ausbruch4h_bot.yaml |
| Pine-Gold Hand auf Account 5 | Account 5 | 2026-11-10 | 10 | +3,13 | 1,40 | +15,37 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_pine5m_abfang4h.yaml |
| Pine-Gold TP 3 € | US500 | 2026-11-10 | 14 | -10,59 | 0,23 | -52,60 | Demo-Vorwärtstest, Urteil nach 40 Trades | suche/VORAB_pine5m.yaml |

Der Gold-Bot zählt hier ab 2026-11-03 09:05 UTC (seit dem Stop 1 x ATR). Der Wochenbericht zählt alle seine Demo-Trades seit dem 31.10.2026, darum kann dort ein Trade mehr stehen.
