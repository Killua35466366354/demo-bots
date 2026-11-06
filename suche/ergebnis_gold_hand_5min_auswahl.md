# Gold-Hand-Bot: Auswahl der 5-Min.-Einstiege

Vorab: `suche/VORAB_gold_hand_5min_auswahl.yaml` (sha256 `87e7789b…`, im Protokoll vor dem Rechnen). Daten: HistData XAUUSD 5 Min. mit Capital.com-Spread.

**Ergebnis: Keine Auswahl besteht. Der Bot bleibt bei 15-Min.-Einstiegen.**

## Zeitraum 01.11.2024 bis 30.10.2026

| Einstiege | Trades | PF_R | Summe R | zuerst 1 R dafür |
|---|---:|---:|---:|---:|
| 15 Min. wie live (Vergleich) | 1163 | 1,18 | 60,6 | 0,54 |
| 5 Min. zusätzlich, wie live (nicht gegen den Hintergrund) | 2490 | 1,00 | 2,5 | 0,49 |
| 5 Min. zusätzlich, nur mit dem Trend | 1674 | 1,22 | 111,5 | 0,51 |
| 5 Min. zusätzlich, mit dem Trend, höchstens 2 am Tag | 550 | 1,29 | 53,0 | 0,49 |
| nur 5 Min. statt 15 Min., wie live | 2921 | 1,05 | 48,4 | 0,49 |

## Kontrolle 01.11.2022 bis 31.10.2024

| Einstiege | Trades | PF_R | Summe R | zuerst 1 R dafür |
|---|---:|---:|---:|---:|
| 15 Min. wie live (Vergleich) | 1174 | 0,86 | -56,3 | 0,50 |
| 5 Min. zusätzlich, wie live (nicht gegen den Hintergrund) | 2399 | 0,74 | -230,4 | 0,46 |
| 5 Min. zusätzlich, nur mit dem Trend | 1734 | 0,76 | -151,1 | 0,47 |
| 5 Min. zusätzlich, mit dem Trend, höchstens 2 am Tag | 553 | 0,57 | -87,5 | 0,47 |
| nur 5 Min. statt 15 Min., wie live | 2829 | 0,76 | -243,0 | 0,47 |

## Prüfungen nach dem Vorab

- 5 Min. zusätzlich, wie live (nicht gegen den Hintergrund): nicht bestanden (pf_zeitraum, erst_1r_zeitraum, pf_kontrolle, erst_1r_kontrolle)
- 5 Min. zusätzlich, nur mit dem Trend: nicht bestanden (erst_1r_zeitraum, pf_kontrolle, erst_1r_kontrolle)
- 5 Min. zusätzlich, mit dem Trend, höchstens 2 am Tag: nicht bestanden (erst_1r_zeitraum, pf_kontrolle, erst_1r_kontrolle)
- nur 5 Min. statt 15 Min., wie live: nicht bestanden (pf_zeitraum, erst_1r_zeitraum, pf_kontrolle, erst_1r_kontrolle)
