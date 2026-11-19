# Ergebnis der großen Runde vom 19.11.2026, Durchgang 2

Keine der dreizehn Regeln besteht, und in diesem Durchgang konnte auch keine bestehen, weil er nach dem Ergebnis von
Durchgang 1 zusammengestellt wurde. Eine Regel ist Kandidat, das heißt alle Hürden geschafft, aber kein Beleg: das
strengere Vorhersage-Modell auf fünf Indizes (561 Trades, Gewinnfaktor 1,52, 99,6 % der Zufallsläufe geschlagen,
z 2,69). Die fünf Abwandlungen des VIX-Sprungs haben ein Plus, schlagen aber zufällige Tage nicht. Der Kandidat
VIX-Sprung aus Durchgang 1 steht damit auf dünnerem Eis. Die drei seltenen Regeln, die Kiron am 19.11.2026 verlangt
hat (Tokio-Eröffnung nach einem US-Schreck, Verfallstag-Morgen in den USA, in Tokio und Frankfurt), verlieren und sind
schlechter als zufällige Tage. Es geht nichts live, an keinem Bot ändert sich etwas.

Regeln: `suche/VORAB_grosse_runde2.yaml`, Siegel `5bd044c1611a364ca78a4e4ed21859bc6e25bf83bfdab3133fa83034165869e0`, im Protokoll am 19.11.2026 23:25 UTC, committet und
gepusht vor dem Rechnen, einmal gerechnet um 23:27 UTC. Programm `suche/grosse_runde.py`, Rechnung von
`suche/rueckblick.py`. Hauptfenster Januar 2024 bis Oktober 2026, nach Spread, Rutschen und Übernachtgebühr.
Gewinnfaktor heißt Gewinne geteilt durch Verluste. Holm zählt mit 26 Varianten über beide Durchgänge.

## Alle dreizehn

Euro heißt: Summe mit 10 € Risiko je Trade (10 € sind weg, wenn der Stop greift). Sortiert nach z.

| Regel | Märkte | Haltedauer | Trades | je Woche | Treffer | Gewinnfaktor | 1,5-fache Kosten | Hälften | 2026 | Zufall geschlagen | z | Euro | Urteil |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Vorhersage-Modell Indizes, strenger (`modell_indizes_08`) | 5 Indizes | 1 Tag | 561 | 3,8 | 60 % | 1,52 | 1,46 | 1,23 und 2,23 | 1,50 | 99,6 % | 2,69 | +326 € | Kandidat: Holm und z fehlen |
| VIX-Sprung auf DAX, FTSE, Nikkei (`vix_sprung_welt`) | DAX, FTSE, Nikkei | 1 Tag | 204 | 1,4 | 59 % | 1,41 | 1,35 | 0,96 und 2,18 | 2,10 | 93,1 % | 1,50 | +74 € | durchgefallen: Hälften, Zufall 95 % |
| VIX-Sprung ab 7,5 % (`vix_sprung_us_75`) | US500, US100 | 1 Tag | 190 | 1,3 | 59 % | 1,36 | 1,35 | 1,00 und 1,97 | 1,91 | 88,2 % | 1,10 | +63 € | durchgefallen: Hälften, Zufall 95 % |
| VIX-Sprung auf Yen-Paaren (`vix_sprung_yen`) | USD/JPY, EUR/JPY, GBP/JPY | 1 Tag | 204 | 1,4 | 61 % | 1,16 | 0,98 | 1,90 und 0,73 | 0,58 | 85,6 % | 1,05 | +27 € | durchgefallen: Gewinnfaktor, 1,5-fache Kosten, Hälften, 2026, Zufall 95 % |
| VIX-Sprung, zwei Tage halten (`vix_sprung_us_2tage`) | US500, US100 | 2 Tage | 124 | 0,8 | 59 % | 1,42 | 1,41 | 0,93 und 2,45 | 2,52 | 80,3 % | 0,81 | +60 € | durchgefallen: Hälften, Zufall 95 % |
| Bitcoin nach dem Fonds-Fenster (`btc_fonds_fenster`) | Bitcoin | bis 4 Std. | 199 | 1,4 | 55 % | 0,68 | 0,60 | 0,76 und 0,53 | 0,52 | 77,7 % | 0,78 | -239 € | durchgefallen: Gewinnfaktor, 1,5-fache Kosten, Hälften, 2026, Zufall 95 % |
| Dark-Pool-Käufe (DIX) (`dix_us500`) | US500 | 1 Tag | 133 | 0,9 | 58 % | 1,29 | 1,27 | 1,09 und 1,63 | 1,38 | 71,6 % | 0,56 | +25 € | durchgefallen: Zufall 95 % |
| VIX-Sprung mit Geduld-Ausstieg (`vix_sprung_geduld`) | US500, US100 | Stunden bis 10 Tage | 124 | 0,8 | 88 % | 1,33 | 1,31 | 0,70 und 12,05 | 8,14 | 60,0 % | 0,33 | +22 € | durchgefallen: Hälften, Zufall 95 % |
| Hebel-Fonds, letzte halbe Stunde (`schluss_schub_us`) | US500, US100 | 25 Min. | 278 | 1,9 | 49 % | 0,94 | 0,90 | 0,72 und 1,61 | 1,07 | 54,8 % | 0,05 | -36 € | durchgefallen: Gewinnfaktor, 1,5-fache Kosten, Hälften, Zufall 95 % |
| Runde Marken bei Devisen (`runde_marke_fx`) | EUR/USD, GBP/USD, USD/JPY | bis 4 Std. | 182 | 1,2 | 34 % | 0,76 | 0,71 | 0,97 und 0,52 | 0,55 | 32,4 % | -0,48 | -315 € | durchgefallen: Gewinnfaktor, 1,5-fache Kosten, Hälften, 2026, Zufall 95 % |
| Verfallstag-Morgen, Anstieg und Umkehr (selten) (`verfallstag_morgen_us`) | US500, US100 | eine Nacht, dann 2,5 Std. | 134 | 0,9 | 45 % | 0,75 | 0,74 | 0,84 und 0,68 | 0,60 | 20,0 % | -0,85 | -106 € | durchgefallen: Gewinnfaktor, 1,5-fache Kosten, Hälften, 2026, Zufall 95 % |
| Tokio-Eröffnung nach einem US-Schreck (selten) (`tokio_nach_us_schreck`) | Nikkei, USD/JPY, EUR/JPY, GBP/JPY | 6 Std. | 115 | 0,8 | 44 % | 0,72 | 0,69 | 0,57 und 1,58 | 1,97 | 20,1 % | -0,86 | -55 € | durchgefallen: Gewinnfaktor, 1,5-fache Kosten, Hälften, Zufall 95 % |
| Verfalls-Abrechnung in Tokio und Frankfurt (selten) (`verfall_tokio_frankfurt`) | Nikkei, DAX | eine Nacht, dann 2 Std. | 136 | 0,9 | 44 % | 0,84 | 0,80 | 0,72 und 0,96 | 0,93 | 18,5 % | -0,86 | -84 € | durchgefallen: Gewinnfaktor, 1,5-fache Kosten, Hälften, 2026, Zufall 95 % |

## Der eine Kandidat

**Vorhersage-Modell Indizes, strenger.** Eine logistische Regression schätzt jeden Tag aus Rückblick, RSI und
Durchschnitten die Wahrscheinlichkeit für einen steigenden Tag. Sie wird jedes Jahr nur mit älteren Jahren neu
gelernt. Gekauft wird erst ab 58 % (in Durchgang 1 ab 54 %), verkauft bis 42 %. 561 Trades, 60 % Treffer,
Gewinnfaktor 1,52, mit 1,5-fachen Kosten 1,46, Hälften 1,23 und 2,23, 2026 1,50, ohne die 5 besten Trades 1,40.
Je Markt: US500 1,89, US100 1,99, FTSE 1,66, Nikkei 1,81, DAX 1,01 (200 Trades ohne Gewinn). Das Modell hat nur
gekauft, kein einziger Verkauf. 9 von 12 Quartalen im Plus. Zufallsvergleich 99,6 % geschlagen, z 2,69 (nötig 3 und
Holm über 26, p 0,006 statt 0,0019). Im Probelauf auf erfundenen Märkten war der Vergleich für diese Variante nicht
verzerrt. 558 der 561 Trades standen schon in Durchgang 1, die Regel ist also die strengere Hälfte desselben Modells.

Die Haken: Vor 2024 brachte dieselbe Bauart als Auskunft 1.652 Trades mit Gewinnfaktor 0,97, also nichts. Die
Schwelle wurde nach dem ersten Ergebnis strenger gemacht (einmal, vorab festgelegt), darum zählt das Ergebnis
höchstens als Kandidat. Das Modell kauft überdurchschnittlich oft nach schwachen Tagen (beim US500 61 % der Käufe
nach einem Minus-Tag statt 43 %, bei rund 30 % der Käufe lag der RSI 2 unter 10). Das ist die Gegend, in der die
Rücksetzer-Bots schon handeln. 49 der 136 Trades des VIX-Sprungs aus Durchgang 1 sind auch Trades dieses Modells.
Mit 10 € Risiko je Trade wären es 326 € in 34 Monaten gewesen, rund 10 € im Monat.

## Der VIX-Sprung und seine fünf Abwandlungen

Der Kandidat aus Durchgang 1 (VIX schließt 10 % höher, einen Tag US500 und US100 kaufen) hatte Gewinnfaktor 1,93
und schlug 98,8 % der Zufallsläufe. Jede Abwandlung ist schwächer.

| Fassung | Trades | Gewinnfaktor | 1. Hälfte | Zufall geschlagen | z | vor 2024 |
|---|---|---|---|---|---|---|
| Durchgang 1, ein Tag, ab 10 % | 136 | 1,93 | 1,26 | 98,8 % | 2,17 | 1,13 |
| zwei Tage halten | 124 | 1,42 | 0,93 | 80,3 % | 0,81 | 1,15 |
| schon ab 7,5 % | 190 | 1,36 | 1,00 | 88,2 % | 1,10 | 1,18 |
| DAX, FTSE, Nikkei | 204 | 1,41 | 0,96 | 93,1 % | 1,50 | 0,85 |
| mit Geduld-Ausstieg | 124 | 1,33 | 0,70 | 60,0 % | 0,33 | 1,03 |
| Yen-Paare | 204 | 1,16 | 1,90 | 85,6 % | 1,05 | 0,69 |

Was das heißt: Nach einem VIX-Sprung zu kaufen brachte 2024 bis 2026 in jeder Fassung ein Plus. Bei den vier
Index-Fassungen kommt es aber ganz aus der zweiten Hälfte (ab Juni 2025), bei den Yen-Paaren ganz aus der ersten,
und zufällig verschobene Tage waren in 7 bis 40 % der Läufe genauso gut. Dazu kommt der Befund aus dem Probelauf: bei Regeln mit einem Schreck als Auslöser ist der
Zufallsvergleich zu freundlich. Die Fassung aus Durchgang 1 war die beste von sechs. Das spricht eher für Glück bei
der Wahl von Schwelle und Haltedauer als für einen festen Vorteil. Der Geduld-Ausstieg (88 % Treffer) macht es
nicht besser, sondern schlechter.

## Kirons seltene Regeln

Kiron wollte am 19.11.2026 auch Regeln sehen, die nur etwa einmal im Monat handeln, eine Nachricht abwarten oder eine
bestimmte Eröffnung handeln. Drei davon ließen sich mit den vorhandenen Kursen sofort rechnen.

- **Tokio-Eröffnung nach einem US-Schreck** (`tokio_nach_us_schreck`): Fällt der US500 um mindestens 1,5 %, am
  nächsten Morgen um 9 Uhr Tokio Nikkei und drei Yen-Paare kaufen, um 15 Uhr verkaufen. 29 Schreck-Tage in 34
  Monaten, 115 Trades, 44 % Treffer, Gewinnfaktor 0,72. Nikkei 1,09, USD/JPY 0,45, EUR/JPY 0,76, GBP/JPY 0,56.
  Nur 20 % der Zufallsläufe geschlagen. Eine Wende am Tokioter Morgen gab es nach Kosten nicht.
- **Verfallstag-Morgen, Anstieg und Umkehr** (`verfallstag_morgen_us`): Am Abend vor dem dritten Freitag kaufen, zur
  Abrechnung um 9:30 New York verkaufen, danach bis 12 Uhr auf fallende Kurse setzen. 34 Verfallstage, 134 Trades,
  45 % Treffer, Gewinnfaktor 0,75. Der Kauf über Nacht verlor (0,62), die Umkehr danach brachte nichts (0,94).
  Die Studie (Daten bis 2021) fand im Mittel 0,14 % Anstieg, 2024 bis 2026 war davon auf dem CFD nichts zu sehen.
- **Verfalls-Abrechnung in Tokio und Frankfurt** (`verfall_tokio_frankfurt`): dieselbe Regel für den Nikkei (zweiter
  Freitag) und den DAX (dritter Freitag). 136 Trades, Gewinnfaktor 0,84. Kein Teil brachte einen nennenswerten Gewinn (die Umkehr beim DAX plus 0,3 R in
  34 Trades, alles andere im Minus).

Was das heißt: Eine seltene Regel ist nicht von selbst besser. Diese drei haben im Schnitt bei 44 bis 45 % der
Trades gewonnen und nach Kosten Geld verloren. Weitere seltene Regeln aus der Suche (Quartalszahlen und
Insider-Käufe bei Einzelaktien, Monatsende bei Staatsanleihen, Freischaltungen bei kleinen Kryptos) brauchen Daten,
die im Projekt noch fehlen, und sind darum nicht gerechnet. Die Umkehr nach dem Fed-Entscheid hat im Fenster nur 23
Termine und kann im Rückblick nichts belegen.

## Die anderen vier

- **Dark-Pool-Käufe (DIX)** (`dix_us500`): 133 Trades, Gewinnfaktor 1,29. Zufällige Tage waren fast so gut (72 %
  geschlagen), ohne die 5 besten Trades 1,05.
- **Hebel-Fonds, letzte halbe Stunde** (`schluss_schub_us`): 278 Trades, Gewinnfaktor 0,94. Käufe 1,36, Verkäufe
  0,70. Kein Schub am Schluss, der die Kosten trägt.
- **Runde Marken bei Devisen** (`runde_marke_fx`): 182 Trades, Gewinnfaktor 0,76, 34 % Treffer bei Ziel 20 und Stop
  12 Pips. 2026 nur 0,55.
- **Bitcoin nach dem Fonds-Fenster** (`btc_fonds_fenster`): 199 Trades, Gewinnfaktor 0,68. Käufe 1,02, Verkäufe
  0,49. Keine Umkehr nach 16 Uhr New York.

## Was daraus folgt

- Bestanden hat nichts. Kein Bot ändert sich, nichts geht live.
- Über beide Durchgänge: 26 Regeln gerechnet, 0 bestanden, 3 Kandidaten (VIX-Sprung, Vorhersage-Modell Indizes und
  dessen strengere Fassung). Die zwei Modell-Kandidaten sind dieselbe Idee.
- Der VIX-Sprung hat seine Nachprüfung nicht bestanden. Er bleibt als Kandidat im Katalog, mit dem Vermerk, dass
  fünf Abwandlungen ihn nicht stützen.
- Das strengere Modell ist der bessere Kandidat. Ein nächster ehrlicher Schritt wäre, es ohne Order vorwärts
  mitzuzählen. Das entscheidet nur Kiron.
- Es gibt keinen dritten Durchgang. Die zwölf durchgefallenen Regeln kommen ins Archiv `suche/VERWORFEN.md`.
- Alle Trades: `suche/ergebnis_grosse_runde2_trades.csv.gz`, alle Zahlen: `suche/ergebnis_grosse_runde2.json`.
