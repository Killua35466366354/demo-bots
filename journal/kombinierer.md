# Kombinierer, Stand 2026-11-22

Alle Demo-Bots zusammen als ein Konto mit 1.000 € und 10 € Risiko je Trade stehen bei +176 € nach 67 Trades. Mit den Regeln eines echten Kontos (höchstens 3 offene Trades, einer je Markt) hätte es 30 davon genommen und +34 € gebracht. Mit Margin-Ampel (höchstens 30 % des Kontos als Sicherheitsgeld gebunden) wären es 24 Trades und +82 € gewesen.

Ein Konto, ein Topf von 1.000 €, jeder Trade riskiert 10 € (1 R). Die Regeln stehen in suche/VORAB_schatten.yaml und suche/VORAB_kombinierer_margin.yaml (Margin-Ampel). Margin ist das Sicherheitsgeld, das der Broker für offene Trades festhält. Nur Demokonten, nur Auskunft, kein Bot liest diese Datei.

## Gruppe aller Bots (wie im Demo-Vergleich)

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 67 von 67 | – | +176 € | −135 € | +176 € (17,6 %) | 3.519 € |
| Regeln eines echten Kontos | 30 von 67 | schon genug offen 2, Markt schon belegt 33, Tagesstopp 2 | +34 € | −87 € | +34 € (3,4 %) | 1.722 € |
| weitere Kontoregeln (nur Vergleich) | 42 von 67 | Markt schon belegt 21, Tagesstopp 4 | +17 € | −105 € | +17 € (1,7 %) | 3.262 € |
| Kontoregeln mit Margin-Ampel 30 % | 24 von 67 | Markt schon belegt 34, zu wenig Margin frei 7, Tagesstopp 2 | +82 € | −57 € | +82 € (8,2 %) | 260 € |
| mit Margin-Ampel 50 % (nur Vergleich) | 25 von 67 | Markt schon belegt 34, zu wenig Margin frei 6, Tagesstopp 2 | +85 € | −57 € | +85 € (8,5 %) | 306 € |

## Kern-Kombi

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| Regeln eines echten Kontos | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| weitere Kontoregeln (nur Vergleich) | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| Kontoregeln mit Margin-Ampel 30 % | 0 von 6 | zu wenig Margin frei 6 | 0 € | 0 € | 0 € (0,0 %) | – |
| mit Margin-Ampel 50 % (nur Vergleich) | 0 von 6 | zu wenig Margin frei 6 | 0 € | 0 € | 0 € (0,0 %) | – |

