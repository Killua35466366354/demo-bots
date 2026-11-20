# Kombinierer, Stand 2026-11-20

Alle Demo-Bots zusammen als ein Konto mit 1.000 € und 10 € Risiko je Trade stehen bei +203 € nach 58 Trades. Mit den Regeln eines echten Kontos (höchstens 3 offene Trades, einer je Markt) hätte es 26 davon genommen und +21 € gebracht. Mit Margin-Ampel (höchstens 30 % des Kontos als Sicherheitsgeld gebunden) wären es 20 Trades und +69 € gewesen.

Ein Konto, ein Topf von 1.000 €, jeder Trade riskiert 10 € (1 R). Die Regeln stehen in suche/VORAB_schatten.yaml und suche/VORAB_kombinierer_margin.yaml (Margin-Ampel). Margin ist das Sicherheitsgeld, das der Broker für offene Trades festhält. Nur Demokonten, nur Auskunft, kein Bot liest diese Datei.

## Gruppe aller Bots (wie im Demo-Vergleich)

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 58 von 58 | – | +203 € | −135 € | +203 € (20,3 %) | 3.519 € |
| Regeln eines echten Kontos | 26 von 58 | schon genug offen 2, Markt schon belegt 28, Tagesstopp 2 | +21 € | −87 € | +21 € (2,1 %) | 1.722 € |
| weitere Kontoregeln (nur Vergleich) | 37 von 58 | Markt schon belegt 17, Tagesstopp 4 | +14 € | −105 € | +14 € (1,4 %) | 3.262 € |
| Kontoregeln mit Margin-Ampel 30 % | 20 von 58 | Markt schon belegt 29, zu wenig Margin frei 7, Tagesstopp 2 | +69 € | −57 € | +69 € (6,9 %) | 260 € |
| mit Margin-Ampel 50 % (nur Vergleich) | 21 von 58 | Markt schon belegt 29, zu wenig Margin frei 6, Tagesstopp 2 | +72 € | −57 € | +72 € (7,2 %) | 306 € |

## Kern-Kombi

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| Regeln eines echten Kontos | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| weitere Kontoregeln (nur Vergleich) | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| Kontoregeln mit Margin-Ampel 30 % | 0 von 6 | zu wenig Margin frei 6 | 0 € | 0 € | 0 € (0,0 %) | – |
| mit Margin-Ampel 50 % (nur Vergleich) | 0 von 6 | zu wenig Margin frei 6 | 0 € | 0 € | 0 € (0,0 %) | – |

