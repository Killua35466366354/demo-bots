# Kombinierer, Stand 2026-11-26

Alle Demo-Bots zusammen als ein Konto mit 1.000 € und 10 € Risiko je Trade stehen bei +326 € nach 93 Trades. Mit den Regeln eines echten Kontos (höchstens 3 offene Trades, einer je Markt) hätte es 42 davon genommen und +33 € gebracht. Mit Margin-Ampel (höchstens 30 % des Kontos als Sicherheitsgeld gebunden) wären es 34 Trades und +101 € gewesen.

Ein Konto, ein Topf von 1.000 €, jeder Trade riskiert 10 € (1 R). Die Regeln stehen in suche/VORAB_schatten.yaml und suche/VORAB_kombinierer_margin.yaml (Margin-Ampel). Margin ist das Sicherheitsgeld, das der Broker für offene Trades festhält. Nur Demokonten, nur Auskunft, kein Bot liest diese Datei.

## Gruppe aller Bots (wie im Demo-Vergleich)

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 93 von 93 | – | +326 € | −135 € | +326 € (32,6 %) | 3.519 € |
| Regeln eines echten Kontos | 42 von 93 | schon genug offen 3, Markt schon belegt 46, Tagesstopp 2 | +33 € | −87 € | +33 € (3,3 %) | 1.868 € |
| weitere Kontoregeln (nur Vergleich) | 59 von 93 | Markt schon belegt 28, Tagesstopp 6 | +20 € | −105 € | +20 € (2,0 %) | 3.262 € |
| Kontoregeln mit Margin-Ampel 30 % | 34 von 93 | Markt schon belegt 48, zu wenig Margin frei 9, Tagesstopp 2 | +101 € | −57 € | +101 € (10,1 %) | 260 € |
| mit Margin-Ampel 50 % (nur Vergleich) | 35 von 93 | Markt schon belegt 48, zu wenig Margin frei 8, Tagesstopp 2 | +104 € | −57 € | +104 € (10,4 %) | 306 € |

## Kern-Kombi

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 8 von 8 | – | −81 € | −81 € | −81 € (−8,1 %) | 2.466 € |
| Regeln eines echten Kontos | 8 von 8 | – | −81 € | −81 € | −81 € (−8,1 %) | 2.466 € |
| weitere Kontoregeln (nur Vergleich) | 8 von 8 | – | −81 € | −81 € | −81 € (−8,1 %) | 2.466 € |
| Kontoregeln mit Margin-Ampel 30 % | 0 von 8 | zu wenig Margin frei 8 | 0 € | 0 € | 0 € (0,0 %) | – |
| mit Margin-Ampel 50 % (nur Vergleich) | 0 von 8 | zu wenig Margin frei 8 | 0 € | 0 € | 0 € (0,0 %) | – |

## Gold-Duo doppelt (Zählung ohne Order)

Das Gold-Duo mit doppeltem Einsatz steht nach 4 Trades und 1 Tag bei −70 € auf einem gedachten Konto mit 1.000 €. Der größte Rückgang war −70 €, das Urteil heißt sammelt.

Gold-Bot C/B und Pine-K5 zusammen auf einem gedachten Konto mit 1.000 €, jeder Trade mit der doppelten Größe des Demo-Trades. Gezählt wird ab dem 25.11.2026 um 08.00 Uhr UTC. Ein Trade zählt nur, wenn sein Sicherheitsgeld noch auf das Konto passt. Liegt das Konto 30 % unter seinem Höchststand, ist die Zählung beendet. Die Regeln stehen in suche/VORAB_gold_duo_doppelt.yaml. Nur Demokonten, nur Auskunft, kein Bot liest diese Zahlen.

| Trades gezählt | verpasst | noch offen | Summe | Kontostand | größter Rückgang | größtes Sicherheitsgeld | Gewinnfaktor | Tage | Urteil |
|---|---|---|---|---|---|---|---|---|---|
| 4 | – | 3 | −70 € | 930 € | −70 € | 740 € | 0,00 | 1 von 61 | sammelt |

Stand des Urteils. 4 von 100 Trades, 1 von 61 Tagen.

| Monat | Trades | Summe | Rendite pro Monat |
|---|---|---|---|
| 2026-11 | 4 | −70 € | −7,0 % |

Auskunft ohne Einfluss auf das Urteil. Verkäufe brachten −70 € aus 4 Trades, Käufe 0 € aus 0 Trades. Gold-Bot C/B brachte −47 € aus 1 Trades. Pine-K5 brachte −23 € aus 3 Trades.

