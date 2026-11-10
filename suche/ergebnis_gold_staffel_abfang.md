# Gold-Staffel mit Abfänger wie Account 5: Rechnung

Regel: `suche/VORAB_gold_staffel_abfang.yaml`, versiegelt am 10.11.2026 um 17:04 UTC, bevor gerechnet wurde. Rechnung: Projektordner `gold-bot/staffel/staffel_abfang.py`, gleiche Trades und Kosten wie die Staffel-Rechnung.

Varianten: **heute** = Gold-Bot C/B ohne Änderung, **Staffel** = TP 2/4/6 R mit Wächter (live seit PR #34), **Staffel + Abfänger** = dazu nach 4 Std. Stop 0,5 R hinter dem besten Kurs (geht live), **Staffel + Break-even** = Stop auf den Einstieg ab +1 R (nur Auskunft).

| Zeitraum | Trades | heute | Staffel | Staffel + Abfänger | Staffel + Break-even |
|---|---|---|---|---|---|
| 2023-25 (Entwicklung) | 208 | +109,7 R (GF 1,69) | +32,1 R (GF 1,25) | +6,8 R (GF 1,07) | +13,0 R (GF 1,12) |
| 2026 (Jan. bis Okt.) | 49 | +8,0 R (GF 1,21) | -7,8 R (GF 0,78) | -7,4 R (GF 0,70) | -11,2 R (GF 0,62) |
| 2015-22 (nur Auskunft) | 536 | -199,5 R (GF 0,58) | -99,6 R (GF 0,74) | -76,8 R (GF 0,73) | -85,3 R (GF 0,72) |
| 2024-26 (nachgetragen, Kirons Regel 17:05 UTC) | 188 | +50,1 R (GF 1,34) | +14,0 R (GF 1,11) | -0,1 R (GF 1,00) | +1,3 R (GF 1,01) |

Trades, die erst mindestens +1 R im Plus waren und dann mit Verlust endeten:

| Zeitraum | heute | Staffel | Staffel + Abfänger | Staffel + Break-even |
|---|---|---|---|---|
| 2023-25 (Entwicklung) | 52 | 25 | 29 | 1 |
| 2026 (Jan. bis Okt.) | 8 | 6 | 0 | 0 |
| 2015-22 (nur Auskunft) | 159 | 80 | 47 | 2 |
| 2024-26 (nachgetragen, Kirons Regel 17:05 UTC) | 48 | 27 | 20 | 0 |

Ausstiege mit Abfänger 2023-25: Abfänger 105, Wächter TP1 31, TP2 2, TP3 0, wie heute 70.

## Urteil

- Besser als die Staffel ohne Abfänger in allen drei versiegelten Zeiträumen: **nein**. 2023-25 bringt der Abfänger deutlich weniger, 2026 und 2015-22 etwas weniger Minus.
- Break-even in allen drei Zeiträumen besser als der Abfänger: **nein**, darum laut Regel keine Karte, live geht der Abfänger.
- Der Gold-Bot verdient sein Geld mit wenigen großen Läufen (größter Gewinner 2023-25 +15,7 R). Jede Stufe, die früher Gewinne sichert, schneidet genau diese Läufe ab. Dafür enden viel weniger Trades, die schon im Plus waren, mit Verlust.
- Geht trotzdem live, weil Kiron den Abfänger sehen will (Demo-Vorwärtstest, Urteil nach 40 Trades).

Hinweis: Ohne Übernacht-Kosten für Trades, die früher schließen (wie staffel.py und lock.py): leicht zugunsten der Varianten. Gleiche Trades wie die Rechnung vom 10.11. 16:29 UTC.
