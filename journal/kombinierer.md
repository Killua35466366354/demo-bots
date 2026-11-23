# Kombinierer, Stand 2026-11-23

Alle Demo-Bots zusammen als ein Konto mit 1.000 € und 10 € Risiko je Trade stehen bei +171 € nach 68 Trades. Mit den Regeln eines echten Kontos (höchstens 3 offene Trades, einer je Markt) hätte es 31 davon genommen und +29 € gebracht. Mit Margin-Ampel (höchstens 30 % des Kontos als Sicherheitsgeld gebunden) wären es 25 Trades und +77 € gewesen.

Ein Konto, ein Topf von 1.000 €, jeder Trade riskiert 10 € (1 R). Die Regeln stehen in suche/VORAB_schatten.yaml und suche/VORAB_kombinierer_margin.yaml (Margin-Ampel). Margin ist das Sicherheitsgeld, das der Broker für offene Trades festhält. Nur Demokonten, nur Auskunft, kein Bot liest diese Datei.

## Gruppe aller Bots (wie im Demo-Vergleich)

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 68 von 68 | – | +171 € | −135 € | +171 € (17,1 %) | 3.519 € |
| Regeln eines echten Kontos | 31 von 68 | schon genug offen 2, Markt schon belegt 33, Tagesstopp 2 | +29 € | −87 € | +29 € (2,9 %) | 1.722 € |
| weitere Kontoregeln (nur Vergleich) | 43 von 68 | Markt schon belegt 21, Tagesstopp 4 | +11 € | −105 € | +11 € (1,1 %) | 3.262 € |
| Kontoregeln mit Margin-Ampel 30 % | 25 von 68 | Markt schon belegt 34, zu wenig Margin frei 7, Tagesstopp 2 | +77 € | −57 € | +77 € (7,7 %) | 260 € |
| mit Margin-Ampel 50 % (nur Vergleich) | 26 von 68 | Markt schon belegt 34, zu wenig Margin frei 6, Tagesstopp 2 | +80 € | −57 € | +80 € (8,0 %) | 306 € |

## Kern-Kombi

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| Regeln eines echten Kontos | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| weitere Kontoregeln (nur Vergleich) | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| Kontoregeln mit Margin-Ampel 30 % | 0 von 6 | zu wenig Margin frei 6 | 0 € | 0 € | 0 € (0,0 %) | – |
| mit Margin-Ampel 50 % (nur Vergleich) | 0 von 6 | zu wenig Margin frei 6 | 0 € | 0 € | 0 € (0,0 %) | – |

