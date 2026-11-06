# Gold-Hand-Bot: Einstiege auf 5-Min.-Kerzen

Vorab: `suche/VORAB_gold_hand_5min.yaml` (sha256 `931ba27d…`, im Protokoll vor dem Rechnen). Daten: HistData XAUUSD 5 Min. mit Capital.com-Spread.

**Ergebnis: Die 5-Min.-Einstiege kommen nicht dazu. Der Bot bleibt bei 15 Min.**

## Zeitraum 01.11.2024 bis 30.10.2026

| Einstiege | Trades | Shorts | Longs | PF_R | Summe R | Treffer | zuerst 1 R dafür |
|---|---:|---:|---:|---:|---:|---:|---:|
| 15 Min. (heute) | 1265 | 472 | 793 | 1,10 | 36,3 | 0,39 | 0,53 |
| 5 Min. (alle) | 3115 | 1253 | 1862 | 1,00 | -3,7 | 0,37 | 0,48 |
| 5 Min. zusätzlich | 2635 | 1058 | 1577 | 0,95 | -45,2 | 0,36 | 0,48 |

480 der 5-Min.-Einstiege liegen im selben 15-Min.-Fenster und in derselben Richtung wie ein 15-Min.-Einstieg.

Getrennt nach Richtung (PF_R / zuerst 1 R dafür):

- 15 Min.: Shorts 472 Trades, 0,95 / 0,53; Longs 793 Trades, 1,19 / 0,53
- 5 Min. zusätzlich: Shorts 1058 Trades, 0,83 / 0,47; Longs 1577 Trades, 1,03 / 0,49

## Kontrolle 01.11.2022 bis 31.10.2024

| Einstiege | Trades | Shorts | Longs | PF_R | Summe R | Treffer | zuerst 1 R dafür |
|---|---:|---:|---:|---:|---:|---:|---:|
| 15 Min. (heute) | 1282 | 534 | 748 | 0,85 | -65,9 | 0,40 | 0,50 |
| 5 Min. (alle) | 3039 | 1319 | 1720 | 0,78 | -242,6 | 0,35 | 0,47 |
| 5 Min. zusätzlich | 2540 | 1091 | 1449 | 0,76 | -222,2 | 0,34 | 0,46 |

499 der 5-Min.-Einstiege liegen im selben 15-Min.-Fenster und in derselben Richtung wie ein 15-Min.-Einstieg.

Getrennt nach Richtung (PF_R / zuerst 1 R dafür):

- 15 Min.: Shorts 534 Trades, 0,68 / 0,45; Longs 748 Trades, 1,01 / 0,53
- 5 Min. zusätzlich: Shorts 1091 Trades, 0,62 / 0,41; Longs 1449 Trades, 0,89 / 0,50

## Prüfungen nach dem Vorab

- ja: mindestens 50 zusätzliche Trades
- nein: PF_R zusätzlich mindestens wie 15 Min. (Zeitraum)
- nein: zuerst 1 R dafür mindestens wie 15 Min. (Zeitraum)
- nein: PF_R zusätzlich mindestens wie 15 Min. (Kontrolle)
- nein: zuerst 1 R dafür mindestens wie 15 Min. (Kontrolle)
