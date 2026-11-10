# Markt-Bot (Scalping-Komitee Schritt 3a): Ergebnis

Regeln: suche/VORAB_markt_bot.yaml (versiegelt vor dem Rechnen). Trend-Rücksetzer wie der US500-Bot, unverändert, auf allen Aktien mit Capital.com-Stundenkerzen. Ergebnis in R (Tagesschwankung ATR 20).

Aktien: AAPL (LP), ABNB (LP), ALV (--), AMD (LP), AMZN (LP), ASML (LP), AVGO (LP), CCJ (--), DB1 (LP), GOOGL (LP), IBE (LP), JPM (LP), LLY (LP), META (LP), MSFT (LP), NFLX (LP), NVDA (LP), SAP (LP), SIE (LP), TSLA (LP)  (L = zählt im Lernen, P = zählt im Prüfen)

| Variante | Fenster | Trades | je Woche | PF | Summe R | Treffer | Zufall geschlagen |
|---|---|---|---|---|---|---|---|
| markt_rs | Lernen 2018-2024 | 1413 | 4.11 | 0.97 | -21.3 | 61.6 % | 100.0 % (Median Zufall 0.743) |
| markt_rs | Prüfen 2025-2026 | 411 | 4.31 | 1.096 | 17.6 | 63.7 % | 95.1 % (Median Zufall 0.894) |
| markt_rs | 2025 / 2026 | 225 / 186 | | 1.032 / 1.17 | | | |
| markt_rs | Prüfen 1,5-fache Kosten | 411 | | 1.02 | 3.8 | | |
| markt_rs_long | Lernen 2018-2024 | 1003 | 2.92 | 1.049 | 23.7 | 64.1 % | 91.6 % (Median Zufall 0.922) |
| markt_rs_long | Prüfen 2025-2026 | 286 | 3.0 | 1.242 | 27.0 | 63.6 % | 84.5 % (Median Zufall 1.043) |
| markt_rs_long | 2025 / 2026 | 154 / 132 | | 1.072 / 1.501 | | | |
| markt_rs_long | Prüfen 1,5-fache Kosten | 286 | | 1.135 | 15.7 | | |

**markt_rs**: durchgefallen: Lernen Gewinnfaktor 0.97; Prüfen Gewinnfaktor 1.096; Prüfen mit 1,5-fachen Kosten 1.02. Aktien im Plus (Prüfen): 72.2 %.

| Aktie | Trades Prüfen | Summe R | PF |
|---|---|---|---|
| NFLX | 30 | 9.1 | 2.032 |
| AAPL | 28 | 5.0 | 1.617 |
| MSFT | 18 | 4.92 | 1.724 |
| NVDA | 23 | 4.55 | 1.534 |
| ASML | 23 | 4.54 | 1.544 |
| AMD | 23 | 3.85 | 1.482 |
| SIE | 20 | 3.83 | 1.489 |
| SAP | 20 | 2.95 | 1.341 |
| LLY | 27 | 0.91 | 1.073 |
| GOOGL | 20 | 0.6 | 1.09 |
| AMZN | 25 | 0.23 | 1.018 |
| IBE | 22 | 0.19 | 1.027 |
| AVGO | 25 | 0.01 | 1.001 |
| JPM | 19 | -0.2 | 0.974 |
| TSLA | 19 | -2.44 | 0.772 |
| META | 23 | -4.51 | 0.733 |
| ABNB | 23 | -6.9 | 0.511 |
| DB1 | 23 | -9.07 | 0.516 |

**markt_rs_long**: durchgefallen: Lernen Gewinnfaktor 1.049; Lernen nur besser als 91.6 % Zufall; Prüfen nur besser als 84.5 % Zufall. Aktien im Plus (Prüfen): 66.7 %.

| Aktie | Trades Prüfen | Summe R | PF |
|---|---|---|---|
| NFLX | 15 | 9.83 | 14.807 |
| NVDA | 20 | 6.58 | 2.195 |
| AAPL | 19 | 5.61 | 2.242 |
| ASML | 16 | 4.83 | 2.012 |
| SIE | 18 | 4.26 | 1.624 |
| AMD | 15 | 2.95 | 1.525 |
| SAP | 9 | 2.37 | 2.249 |
| AMZN | 21 | 1.19 | 1.122 |
| LLY | 17 | 1.1 | 1.17 |
| META | 12 | 1.0 | 1.131 |
| JPM | 17 | 0.65 | 1.108 |
| IBE | 22 | 0.19 | 1.027 |
| AVGO | 21 | -0.5 | 0.94 |
| MSFT | 7 | -0.57 | 0.702 |
| TSLA | 11 | -1.5 | 0.78 |
| GOOGL | 16 | -1.78 | 0.733 |
| ABNB | 13 | -3.77 | 0.515 |
| DB1 | 17 | -5.44 | 0.573 |
