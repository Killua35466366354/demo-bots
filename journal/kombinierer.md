# Kombinierer, Stand 2026-11-25

Alle Demo-Bots zusammen als ein Konto mit 1.000 € und 10 € Risiko je Trade stehen bei +409 € nach 83 Trades. Mit den Regeln eines echten Kontos (höchstens 3 offene Trades, einer je Markt) hätte es 37 davon genommen und +76 € gebracht. Mit Margin-Ampel (höchstens 30 % des Kontos als Sicherheitsgeld gebunden) wären es 31 Trades und +124 € gewesen.

Ein Konto, ein Topf von 1.000 €, jeder Trade riskiert 10 € (1 R). Die Regeln stehen in suche/VORAB_schatten.yaml und suche/VORAB_kombinierer_margin.yaml (Margin-Ampel). Margin ist das Sicherheitsgeld, das der Broker für offene Trades festhält. Nur Demokonten, nur Auskunft, kein Bot liest diese Datei.

## Gruppe aller Bots (wie im Demo-Vergleich)

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 83 von 83 | – | +409 € | −135 € | +409 € (40,9 %) | 3.519 € |
| Regeln eines echten Kontos | 37 von 83 | schon genug offen 2, Markt schon belegt 42, Tagesstopp 2 | +76 € | −87 € | +76 € (7,6 %) | 1.722 € |
| weitere Kontoregeln (nur Vergleich) | 52 von 83 | Markt schon belegt 25, Tagesstopp 6 | +73 € | −105 € | +73 € (7,3 %) | 3.262 € |
| Kontoregeln mit Margin-Ampel 30 % | 31 von 83 | Markt schon belegt 43, zu wenig Margin frei 7, Tagesstopp 2 | +124 € | −57 € | +124 € (12,4 %) | 260 € |
| mit Margin-Ampel 50 % (nur Vergleich) | 32 von 83 | Markt schon belegt 43, zu wenig Margin frei 6, Tagesstopp 2 | +127 € | −57 € | +127 € (12,8 %) | 306 € |

## Kern-Kombi

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| Regeln eines echten Kontos | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| weitere Kontoregeln (nur Vergleich) | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| Kontoregeln mit Margin-Ampel 30 % | 0 von 6 | zu wenig Margin frei 6 | 0 € | 0 € | 0 € (0,0 %) | – |
| mit Margin-Ampel 50 % (nur Vergleich) | 0 von 6 | zu wenig Margin frei 6 | 0 € | 0 € | 0 € (0,0 %) | – |

## Gold-Duo doppelt (Zählung ohne Order)

Das Gold-Duo mit doppeltem Einsatz wartet auf den ersten gezählten Trade seit dem 25.11.2026. Die Trades vom November davor zählen nicht.

Gold-Bot C/B und Pine-K5 zusammen auf einem gedachten Konto mit 1.000 €, jeder Trade mit der doppelten Größe des Demo-Trades. Gezählt wird ab dem 25.11.2026 um 08.00 Uhr UTC. Ein Trade zählt nur, wenn sein Sicherheitsgeld noch auf das Konto passt. Liegt das Konto 30 % unter seinem Höchststand, ist die Zählung beendet. Die Regeln stehen in suche/VORAB_gold_duo_doppelt.yaml. Nur Demokonten, nur Auskunft, kein Bot liest diese Zahlen.

| Trades gezählt | verpasst | noch offen | Summe | Kontostand | größter Rückgang | größtes Sicherheitsgeld | Gewinnfaktor | Tage | Urteil |
|---|---|---|---|---|---|---|---|---|---|
| 0 | – | 2 | 0 € | 1.000 € | 0 € | 96 € | – | 0 von 61 | sammelt |

Stand des Urteils. 0 von 100 Trades, 0 von 61 Tagen.

