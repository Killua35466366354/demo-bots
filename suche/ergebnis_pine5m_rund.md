# Pine-Gold-Hand-Bot auf Account 5 rund um die Uhr (Gold 5 Min.)

Regeln suche/VORAB_pine5m_rund.yaml. Beide Varianten mit Hedging, Termin-Pause, Hintergrund und Abfänger (k5_hedge_termin_hg aus VORAB_pine5m_konto5).

**Live: k5_rund** (Kirons Wunsch, geht unabhängig vom Test live), nicht bestanden: Gewinnfaktor 1.0; mit 1,5-fachem Spread 0.92; 1. Hälfte 0.97; Kontrolle 2022-24 0.72.

| Variante | Trades | je Woche | PF | Summe R | Rückgang R | Long R | Short R | größter Verlust R | PF ×1,5 | H1 | H2 | 2026 | Kontrolle | Summe R Kontrolle |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| k5_7_20 | 2381 | 22.86 | 1.09 | 76.2 | 48.2 | 35.8 | 40.4 | -6.49 | 1.0 | 1.04 | 1.13 | 1.13 | 0.76 | -247.0 |
| k5_rund | 3959 | 38.02 | 1.0 | -7.0 | 88.3 | 41.8 | -48.7 | -8.35 | 0.92 | 0.97 | 1.02 | 1.02 | 0.72 | -445.7 |

Nur die Nachttrades von k5_rund (Signalkerze vor 7 oder ab 20 Uhr UTC):

| Teil | Trades | je Woche | PF | Summe R |
|---|---|---|---|---|
| Zeitraum | 1599 | 15.35 | 0.89 | -79.6 |
| Kontrolle | 1416 | 13.56 | 0.65 | -204.2 |

Fester Spread 0,50 wie in VORAB_pine5m. Nachts ist der Capital.com-Spread oft breiter, der Live-Bot nimmt den echten.
