# Kombinierer, Stand 2026-11-20

Alle Demo-Bots zusammen als ein Konto mit 1.000 € und 10 € Risiko je Trade stehen bei +140 € nach 55 Trades. Mit den Regeln eines echten Kontos (höchstens 3 offene Trades, einer je Markt) hätte es 25 davon genommen und +21 € gebracht. Mit Margin-Ampel (höchstens 30 % des Kontos als Sicherheitsgeld gebunden) wären es 19 Trades und +69 € gewesen.

Ein Konto, ein Topf von 1.000 €, jeder Trade riskiert 10 € (1 R). Die Regeln stehen in suche/VORAB_schatten.yaml und suche/VORAB_kombinierer_margin.yaml (Margin-Ampel). Margin ist das Sicherheitsgeld, das der Broker für offene Trades festhält. Nur Demokonten, nur Auskunft, kein Bot liest diese Datei.

## Gruppe aller Bots (wie im Demo-Vergleich)

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 55 von 55 | – | +140 € | −135 € | +140 € (14,0 %) | 3.519 € |
| Regeln eines echten Kontos | 25 von 55 | schon genug offen 2, Markt schon belegt 26, Tagesstopp 2 | +21 € | −87 € | +21 € (2,1 %) | 1.722 € |
| weitere Kontoregeln (nur Vergleich) | 35 von 55 | Markt schon belegt 16, Tagesstopp 4 | +7 € | −105 € | +7 € (0,7 %) | 3.262 € |
| Kontoregeln mit Margin-Ampel 30 % | 19 von 55 | Markt schon belegt 27, zu wenig Margin frei 7, Tagesstopp 2 | +69 € | −57 € | +69 € (6,9 %) | 260 € |
| mit Margin-Ampel 50 % (nur Vergleich) | 20 von 55 | Markt schon belegt 27, zu wenig Margin frei 6, Tagesstopp 2 | +72 € | −57 € | +72 € (7,2 %) | 306 € |

## Kern-Kombi

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| Regeln eines echten Kontos | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| weitere Kontoregeln (nur Vergleich) | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| Kontoregeln mit Margin-Ampel 30 % | 0 von 6 | zu wenig Margin frei 6 | 0 € | 0 € | 0 € (0,0 %) | – |
| mit Margin-Ampel 50 % (nur Vergleich) | 0 von 6 | zu wenig Margin frei 6 | 0 € | 0 € | 0 € (0,0 %) | – |

