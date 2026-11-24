# Kombinierer, Stand 2026-11-24

Alle Demo-Bots zusammen als ein Konto mit 1.000 € und 10 € Risiko je Trade stehen bei +152 € nach 72 Trades. Mit den Regeln eines echten Kontos (höchstens 3 offene Trades, einer je Markt) hätte es 32 davon genommen und +33 € gebracht. Mit Margin-Ampel (höchstens 30 % des Kontos als Sicherheitsgeld gebunden) wären es 26 Trades und +81 € gewesen.

Ein Konto, ein Topf von 1.000 €, jeder Trade riskiert 10 € (1 R). Die Regeln stehen in suche/VORAB_schatten.yaml und suche/VORAB_kombinierer_margin.yaml (Margin-Ampel). Margin ist das Sicherheitsgeld, das der Broker für offene Trades festhält. Nur Demokonten, nur Auskunft, kein Bot liest diese Datei.

## Gruppe aller Bots (wie im Demo-Vergleich)

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 72 von 72 | – | +152 € | −135 € | +152 € (15,2 %) | 3.519 € |
| Regeln eines echten Kontos | 32 von 72 | schon genug offen 2, Markt schon belegt 36, Tagesstopp 2 | +33 € | −87 € | +33 € (3,3 %) | 1.722 € |
| weitere Kontoregeln (nur Vergleich) | 46 von 72 | Markt schon belegt 21, Tagesstopp 5 | −16 € | −105 € | −16 € (−1,6 %) | 3.262 € |
| Kontoregeln mit Margin-Ampel 30 % | 26 von 72 | Markt schon belegt 37, zu wenig Margin frei 7, Tagesstopp 2 | +81 € | −57 € | +81 € (8,1 %) | 260 € |
| mit Margin-Ampel 50 % (nur Vergleich) | 27 von 72 | Markt schon belegt 37, zu wenig Margin frei 6, Tagesstopp 2 | +84 € | −57 € | +84 € (8,4 %) | 306 € |

## Kern-Kombi

| Regeln | Trades genommen | verpasst | Summe | größter Rückgang | Schnitt je Monat | größte Margin |
|---|---|---|---|---|---|---|
| ohne Grenzen | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| Regeln eines echten Kontos | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| weitere Kontoregeln (nur Vergleich) | 6 von 6 | – | −61 € | −61 € | −61 € (−6,1 %) | 2.466 € |
| Kontoregeln mit Margin-Ampel 30 % | 0 von 6 | zu wenig Margin frei 6 | 0 € | 0 € | 0 € (0,0 %) | – |
| mit Margin-Ampel 50 % (nur Vergleich) | 0 von 6 | zu wenig Margin frei 6 | 0 € | 0 € | 0 € (0,0 %) | – |

