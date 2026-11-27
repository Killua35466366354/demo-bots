# Kombinierer, Stand 2026-11-27

Alle Demo-Bots zusammen als ein Konto mit 1.000 € und 10 € Risiko je Trade stehen bei +232 € nach 102 Trades. Mit den Regeln eines echten Kontos (höchstens 3 offene Trades, einer je Markt) hätte es 46 davon genommen und +19 € gebracht. Mit Margin-Ampel (höchstens 30 % des Kontos als Sicherheitsgeld gebunden) wären es 38 Trades und +87 € gewesen.

Ein Konto, ein Topf von 1.000 €, jeder Trade riskiert 10 € (1 R). Die Regeln stehen in suche/VORAB_schatten.yaml und suche/VORAB_kombinierer_margin.yaml (Margin-Ampel). Margin ist das Sicherheitsgeld, das der Broker für offene Trades festhält. Nur Demokonten, nur Auskunft, kein Bot liest diese Datei.

## Gruppe aller Bots (wie im Demo-Vergleich)

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 102 von 102 | – | +232 € | −177 € | +232 € (23,2 %) | 3.519 € |
| Regeln eines echten Kontos | 46 von 102 | schon genug offen 3, Markt schon belegt 51, Tagesstopp 2 | +19 € | −87 € | +19 € (1,9 %) | 1.868 € |
| weitere Kontoregeln (nur Vergleich) | 64 von 102 | Markt schon belegt 32, Tagesstopp 6 | −25 € | −105 € | −25 € (−2,5 %) | 3.262 € |
| Kontoregeln mit Margin-Ampel 30 % | 38 von 102 | Markt schon belegt 53, zu wenig Margin frei 9, Tagesstopp 2 | +87 € | −57 € | +87 € (8,7 %) | 260 € |
| mit Margin-Ampel 50 % (nur Vergleich) | 39 von 102 | Markt schon belegt 53, zu wenig Margin frei 8, Tagesstopp 2 | +90 € | −57 € | +90 € (9,0 %) | 306 € |

## Kern-Kombi

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 8 von 8 | – | −81 € | −81 € | −81 € (−8,1 %) | 2.466 € |
| Regeln eines echten Kontos | 8 von 8 | – | −81 € | −81 € | −81 € (−8,1 %) | 2.466 € |
| weitere Kontoregeln (nur Vergleich) | 8 von 8 | – | −81 € | −81 € | −81 € (−8,1 %) | 2.466 € |
| Kontoregeln mit Margin-Ampel 30 % | 0 von 8 | zu wenig Margin frei 8 | 0 € | 0 € | 0 € (0,0 %) | – |
| mit Margin-Ampel 50 % (nur Vergleich) | 0 von 8 | zu wenig Margin frei 8 | 0 € | 0 € | 0 € (0,0 %) | – |

## Gold-Duo doppelt (Zählung ohne Order)

Das Gold-Duo mit doppeltem Einsatz steht nach 9 Trades und 2 Tagen bei −192 € auf einem gedachten Konto mit 1.000 €. Der größte Rückgang war −192 €, das Urteil heißt sammelt.

Gold-Bot C/B und Pine-K5 zusammen auf einem gedachten Konto mit 1.000 €, jeder Trade mit der doppelten Größe des Demo-Trades. Gezählt wird ab dem 25.11.2026 um 08.00 Uhr UTC. Ein Trade zählt nur, wenn sein Sicherheitsgeld noch auf das Konto passt. Liegt das Konto 30 % unter seinem Höchststand, ist die Zählung beendet. Die Regeln stehen in suche/VORAB_gold_duo_doppelt.yaml. Nur Demokonten, nur Auskunft, kein Bot liest diese Zahlen.

| Trades gezählt | verpasst | noch offen | Summe | Kontostand | größter Rückgang | größtes Sicherheitsgeld | Gewinnfaktor | Tage | Urteil |
|---|---|---|---|---|---|---|---|---|---|
| 9 | – | 1 | −192 € | 808 € | −192 € | 740 € | 0,00 | 2 von 61 | sammelt |

Stand des Urteils. 9 von 100 Trades, 2 von 61 Tagen.

| Monat | Trades | Summe | Rendite pro Monat |
|---|---|---|---|
| 2026-11 | 9 | −192 € | −19,2 % |

Auskunft ohne Einfluss auf das Urteil. Verkäufe brachten −128 € aus 7 Trades, Käufe −64 € aus 2 Trades. Gold-Bot C/B brachte −93 € aus 2 Trades. Pine-K5 brachte −99 € aus 7 Trades.

