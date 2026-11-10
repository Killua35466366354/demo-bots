# Gold-Staffel: gestaffelte Take-Profits mit Wächter (nur Auskunft)

Nach `suche/VORAB_gold_staffel.yaml` (versiegelt 10.11.2026 16:29 UTC). Gerechnet im Projektordner mit
`gold-bot/staffel/staffel.py` (gleiches Modell und gleiche Trades wie die Rechnung „Gewinn sichern“ vom 04.11.),
Daten `strategie-suche/daten/XAUUSD_5min.csv.gz` (im VORAB steht gold-bot/data/, es sind dieselben Daten).

Staffel: TP1 +2 R, TP2 +4 R (Stop zieht ab der nächsten 5-Min.-Kerze dorthin nach), TP3 +6 R schließt.

| Zeitraum | Trades | Bot heute | mit Staffel | Unterschied | GF heute | GF Staffel | erst +2 R, dann Verlust (heute → Staffel) |
|---|---|---|---|---|---|---|---|
| 2023–2025 | 208 | +109,7 R | +32,1 R | −77,6 R | 1,69 | 1,25 | 27 → 0 |
| 2026 bis Oktober (Info) | 49 | +8,0 R | −7,8 R | −15,9 R | 1,21 | 0,78 | 2 → 0 |
| 2015–2022 (Info, schon geöffnet) | 536 | −199,5 R | −99,6 R | +99,9 R | 0,58 | 0,74 | 79 → 0 |

Ausstiege mit Staffel 2023–25: 72 am nachgezogenen Stop bei TP1, 5 bei TP2, 0 bei TP3, 131 wie heute.

**Ergebnis: schlechter** (besser hieße mehr R in allen drei Zeiträumen). Die Staffel schließt die meisten
Gewinner schon bei +2 R, weil der Kurs fast immer kurz zurückläuft, bevor er weitergeht. Die großen Läufer
(bis +15,7 R) bringen dem Bot den Gewinn, die Staffel kappt sie bei 4 R. In den Verlustjahren 2015–2022 halbiert
sie die Verluste. Kein Trade, der +2 R erreicht hat, endet mit ihr noch im Minus.

Kirons Trade vom 06.11. (Stundenkerzen): TP1 am 09.11. 00:00 UTC, TP2 um 02:00 UTC, danach Rücklauf unter TP2, also
mit Staffel bei etwa +4 R (etwa +72 €) zu. Ohne Staffel steht er am 10.11. bei etwa 0.

Ohne Übernacht-Kosten für die Trades, die die Staffel früher schließt: leicht zugunsten der Staffel.
Keine Nachbesserung nach dem Ergebnis. Live nur nach Kirons Wahl auf der Karte vom 10.11.2026.
