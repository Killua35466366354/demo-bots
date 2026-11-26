# Kombinierer, Stand 2026-11-26

Alle Demo-Bots zusammen als ein Konto mit 1.000 € und 10 € Risiko je Trade stehen bei +333 € nach 91 Trades. Mit den Regeln eines echten Kontos (höchstens 3 offene Trades, einer je Markt) hätte es 41 davon genommen und +36 € gebracht. Mit Margin-Ampel (höchstens 30 % des Kontos als Sicherheitsgeld gebunden) wären es 33 Trades und +104 € gewesen.

Ein Konto, ein Topf von 1.000 €, jeder Trade riskiert 10 € (1 R). Die Regeln stehen in suche/VORAB_schatten.yaml und suche/VORAB_kombinierer_margin.yaml (Margin-Ampel). Margin ist das Sicherheitsgeld, das der Broker für offene Trades festhält. Nur Demokonten, nur Auskunft, kein Bot liest diese Datei.

## Gruppe aller Bots (wie im Demo-Vergleich)

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 91 von 91 | – | +333 € | −135 € | +333 € (33,3 %) | 3.519 € |
| Regeln eines echten Kontos | 41 von 91 | schon genug offen 3, Markt schon belegt 45, Tagesstopp 2 | +36 € | −87 € | +36 € (3,6 %) | 1.868 € |
| weitere Kontoregeln (nur Vergleich) | 57 von 91 | Markt schon belegt 28, Tagesstopp 6 | +27 € | −105 € | +27 € (2,7 %) | 3.262 € |
| Kontoregeln mit Margin-Ampel 30 % | 33 von 91 | Markt schon belegt 47, zu wenig Margin frei 9, Tagesstopp 2 | +104 € | −57 € | +104 € (10,4 %) | 260 € |
| mit Margin-Ampel 50 % (nur Vergleich) | 34 von 91 | Markt schon belegt 47, zu wenig Margin frei 8, Tagesstopp 2 | +107 € | −57 € | +107 € (10,7 %) | 306 € |

## Kern-Kombi

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 8 von 8 | – | −81 € | −81 € | −81 € (−8,1 %) | 2.466 € |
| Regeln eines echten Kontos | 8 von 8 | – | −81 € | −81 € | −81 € (−8,1 %) | 2.466 € |
| weitere Kontoregeln (nur Vergleich) | 8 von 8 | – | −81 € | −81 € | −81 € (−8,1 %) | 2.466 € |
| Kontoregeln mit Margin-Ampel 30 % | 0 von 8 | zu wenig Margin frei 8 | 0 € | 0 € | 0 € (0,0 %) | – |
| mit Margin-Ampel 50 % (nur Vergleich) | 0 von 8 | zu wenig Margin frei 8 | 0 € | 0 € | 0 € (0,0 %) | – |

## Gold-Duo doppelt (Zählung ohne Order)

Das Gold-Duo mit doppeltem Einsatz steht nach 3 Trades und 1 Tag bei −66 € auf einem gedachten Konto mit 1.000 €. Der größte Rückgang war −66 €, das Urteil heißt sammelt.

Gold-Bot C/B und Pine-K5 zusammen auf einem gedachten Konto mit 1.000 €, jeder Trade mit der doppelten Größe des Demo-Trades. Gezählt wird ab dem 25.11.2026 um 08.00 Uhr UTC. Ein Trade zählt nur, wenn sein Sicherheitsgeld noch auf das Konto passt. Liegt das Konto 30 % unter seinem Höchststand, ist die Zählung beendet. Die Regeln stehen in suche/VORAB_gold_duo_doppelt.yaml. Nur Demokonten, nur Auskunft, kein Bot liest diese Zahlen.

| Trades gezählt | verpasst | noch offen | Summe | Kontostand | größter Rückgang | größtes Sicherheitsgeld | Gewinnfaktor | Tage | Urteil |
|---|---|---|---|---|---|---|---|---|---|
| 3 | – | 1 | −66 € | 934 € | −66 € | 385 € | 0,00 | 1 von 61 | sammelt |

Stand des Urteils. 3 von 100 Trades, 1 von 61 Tagen.

| Monat | Trades | Summe | Rendite pro Monat |
|---|---|---|---|
| 2026-11 | 3 | −66 € | −6,6 % |

Auskunft ohne Einfluss auf das Urteil. Verkäufe brachten −66 € aus 3 Trades, Käufe 0 € aus 0 Trades. Gold-Bot C/B brachte −47 € aus 1 Trades. Pine-K5 brachte −20 € aus 2 Trades.

