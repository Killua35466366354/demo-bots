# Kombinierer, Stand 2026-11-24

Alle Demo-Bots zusammen als ein Konto mit 1.000 € und 10 € Risiko je Trade stehen bei +196 € nach 73 Trades. Mit den Regeln eines echten Kontos (höchstens 3 offene Trades, einer je Markt) hätte es 33 davon genommen und +77 € gebracht. Mit Margin-Ampel (höchstens 30 % des Kontos als Sicherheitsgeld gebunden) wären es 27 Trades und +125 € gewesen.

Ein Konto, ein Topf von 1.000 €, jeder Trade riskiert 10 € (1 R). Die Regeln stehen in suche/VORAB_schatten.yaml und suche/VORAB_kombinierer_margin.yaml (Margin-Ampel). Margin ist das Sicherheitsgeld, das der Broker für offene Trades festhält. Nur Demokonten, nur Auskunft, kein Bot liest diese Datei.

## Gruppe aller Bots (wie im Demo-Vergleich)

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 73 von 73 | – | +196 € | −135 € | +196 € (19,6 %) | 3.519 € |
| Regeln eines echten Kontos | 33 von 73 | schon genug offen 2, Markt schon belegt 36, Tagesstopp 2 | +77 € | −87 € | +77 € (7,7 %) | 1.722 € |
| weitere Kontoregeln (nur Vergleich) | 47 von 73 | Markt schon belegt 21, Tagesstopp 5 | +28 € | −105 € | +28 € (2,8 %) | 3.262 € |
| Kontoregeln mit Margin-Ampel 30 % | 27 von 73 | Markt schon belegt 37, zu wenig Margin frei 7, Tagesstopp 2 | +125 € | −57 € | +125 € (12,5 %) | 260 € |
| mit Margin-Ampel 50 % (nur Vergleich) | 28 von 73 | Markt schon belegt 37, zu wenig Margin frei 6, Tagesstopp 2 | +128 € | −57 € | +128 € (12,8 %) | 306 € |

## Kern-Kombi

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| Regeln eines echten Kontos | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| weitere Kontoregeln (nur Vergleich) | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| Kontoregeln mit Margin-Ampel 30 % | 0 von 6 | zu wenig Margin frei 6 | 0 € | 0 € | 0 € (0,0 %) | – |
| mit Margin-Ampel 50 % (nur Vergleich) | 0 von 6 | zu wenig Margin frei 6 | 0 € | 0 € | 0 € (0,0 %) | – |

