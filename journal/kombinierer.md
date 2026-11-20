# Kombinierer, Stand 2026-11-20

Alle Demo-Bots zusammen als ein Konto mit 1.000 € und 10 € Risiko je Trade stehen bei +173 € nach 64 Trades. Mit den Regeln eines echten Kontos (höchstens 3 offene Trades, einer je Markt) hätte es 29 davon genommen und +11 € gebracht. Mit Margin-Ampel (höchstens 30 % des Kontos als Sicherheitsgeld gebunden) wären es 23 Trades und +59 € gewesen.

Ein Konto, ein Topf von 1.000 €, jeder Trade riskiert 10 € (1 R). Die Regeln stehen in suche/VORAB_schatten.yaml und suche/VORAB_kombinierer_margin.yaml (Margin-Ampel). Margin ist das Sicherheitsgeld, das der Broker für offene Trades festhält. Nur Demokonten, nur Auskunft, kein Bot liest diese Datei.

## Gruppe aller Bots (wie im Demo-Vergleich)

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 64 von 64 | – | +173 € | −135 € | +173 € (17,3 %) | 3.519 € |
| Regeln eines echten Kontos | 29 von 64 | schon genug offen 2, Markt schon belegt 31, Tagesstopp 2 | +11 € | −87 € | +11 € (1,1 %) | 1.722 € |
| weitere Kontoregeln (nur Vergleich) | 40 von 64 | Markt schon belegt 20, Tagesstopp 4 | +4 € | −105 € | +4 € (0,3 %) | 3.262 € |
| Kontoregeln mit Margin-Ampel 30 % | 23 von 64 | Markt schon belegt 32, zu wenig Margin frei 7, Tagesstopp 2 | +59 € | −57 € | +59 € (5,9 %) | 260 € |
| mit Margin-Ampel 50 % (nur Vergleich) | 24 von 64 | Markt schon belegt 32, zu wenig Margin frei 6, Tagesstopp 2 | +62 € | −57 € | +62 € (6,2 %) | 306 € |

## Kern-Kombi

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| Regeln eines echten Kontos | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| weitere Kontoregeln (nur Vergleich) | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| Kontoregeln mit Margin-Ampel 30 % | 0 von 6 | zu wenig Margin frei 6 | 0 € | 0 € | 0 € (0,0 %) | – |
| mit Margin-Ampel 50 % (nur Vergleich) | 0 von 6 | zu wenig Margin frei 6 | 0 € | 0 € | 0 € (0,0 %) | – |

