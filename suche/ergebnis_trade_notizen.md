# Ergebnis der Runde „Kirons Trade-Notizen“ vom 20.11.2026

Keine der sechs neuen Fassungen besteht, und in dieser Runde konnte auch keine bestehen, weil sie Regeln ändert, deren
Ergebnis schon bekannt war. Drei Fassungen sind Kandidat, alle drei sind dasselbe Vorhersage-Modell auf fünf Indizes.
Nur eine Fassung ist nach dem vorab festgelegten Vergleich besser als ihr Original: das Modell mit mehr Merkmalen
(`modell_breit`, 1.724 Trades, Gewinnfaktor 1,27, +552 € statt +457 €, z 2,49 statt 1,89). Das ist kein Beleg. Später
einsteigen macht die Geduld-Regel wertlos (aus +98 € werden −1 € und −5 €). Mehr Märkte bringen der Geduld-Regel mehr
Trades, aber keinen Vorteil gegen Zufallstage. Die Verkäufe des Modells verlieren. Die lernende Markt-Auswahl hat
den schwachen DAX nicht erkannt. Es geht nichts live, an keinem Bot ändert sich etwas.

Regeln: `suche/VORAB_trade_notizen.yaml`, Siegel `c79a70dabcc8be02ad1e183cf4f346f162abf3e94986b6c85b83f60ec79e9515`,
im Protokoll am 20.11.2026 06:35 UTC, committet und gepusht vor dem Rechnen (Commit `73568bf`), einmal gerechnet um
06:40 UTC. Programm `suche/grosse_runde.py` (Durchgang 3), Rechnung von `suche/rueckblick.py`. Hauptfenster Januar 2024
bis Oktober 2026, nach Spread, Rutschen und Übernachtgebühr. Gewinnfaktor heißt Gewinne geteilt durch Verluste. Holm
zählt mit 32 Varianten (26 aus der großen Runde und die 6 hier). z sagt, wie viele Streuungen die Summe über dem
Mittel zufällig verschobener Tage liegt. Nötig sind 3.

## Woher die sechs Fassungen kommen

Kiron hat am 20.11.2026 im Trade-Katalog zwei Karten mit „Ändern“ bewertet und im Thread verlangt, die fünf
profitabelsten Regeln nach Märkten durchzusehen.

- Notiz zur Karte „Geduld mit sinkendem Ziel“: „minimal um 1 oder 2 candeln erzögert einsteigen,...“. Daraus wurden
  `geduld_stufen_spaeter1` und `geduld_stufen_spaeter2` (eine und zwei Stundenkerzen später, sonst nichts geändert).
- Notiz zur Karte „Vorhersage-Modell Indizes“: „analysire alle märkte bei einem schlechten markt/ loss trade so das
  daraus shorts gemacht werden können,... nutze auch news und andere verschiedene variablen“. Daraus wurden
  `modell_breit` und `modell_breit_08`. Das Modell sieht zusätzlich die anderen vier Indizes vom Vortag, den Abstand
  zum 20-Tage-Hoch, die Tage mit Fed-Entscheid, US-Inflation und US-Arbeitsmarkt und die Dark-Pool-Käufe (DIX).
  Verkauft wird wie bisher erst, wenn das Modell höchstens 46 % (42 %) für einen steigenden Tag sieht.
- Nachricht im Thread („mehr oder weniger Märkte“, „selbstlernender Modus“, „für die einzelnen Märkte bestimmte Regeln“):
  Daraus wurden `geduld_stufen_fuenf` (die Geduld-Regel auf allen fünf Indizes) und `modell_auswahl` (jeder Markt darf
  in einem Jahr nur handeln, wenn er in den zwei Jahren davor mit mindestens 100 Trades im Plus lag).

Nicht gerechnet wurde das Streichen einzelner Märkte nach dem Blick auf das Ergebnis (zum Beispiel „ohne DAX“). Das
wäre Auswahl danach und steht als Lehre im Archiv. Nachrichten-Texte gibt es in den Daten nicht, darum heißt „News“
hier feste Termine. Die Stops stehen bei allen Regeln in ATR, also in der mittleren Tagesspanne des jeweiligen Markts.
Sie passen sich darum jedem neuen Markt von selbst an.

## Alle sechs neben ihrem Original

Euro heißt: Summe mit 10 € Risiko je Trade (10 € sind weg, wenn der Stop greift). Sortiert nach z. „Besser“ gilt nach
der vorab festgelegten Regel nur, wenn die neue Fassung mehr Euro UND ein höheres z hat als ihr Original.

| Fassung | Märkte | Trades | Treffer | Gewinnfaktor | 1,5-fache Kosten | Hälften | 2026 | Zufall geschlagen | z | Euro | Original (Euro, z) | Besser? | Urteil |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Modell mit mehr Merkmalen (`modell_breit`) | 5 Indizes | 1.724 | 55 % | 1,27 | 1,22 | 1,07 und 1,53 | 1,47 | 99,7 % | 2,49 | +552 € | `modell_indizes` +457 €, 1,89 | ja, kein Beleg | Kandidat: Holm und z fehlen |
| Modell mit lernender Markt-Auswahl (`modell_auswahl`) | 5 Indizes, je Jahr gewählt | 924 | 55 % | 1,33 | 1,29 | 1,15 und 1,38 | 1,27 | 97,5 % | 2,03 | +344 € | `modell_indizes` +457 €, 1,89 | nein, weniger Euro | Kandidat: Holm und z fehlen |
| Modell mit mehr Merkmalen, strenger (`modell_breit_08`) | 5 Indizes | 601 | 58 % | 1,30 | 1,25 | 1,05 und 1,81 | 1,55 | 95,4 % | 1,64 | +229 € | `modell_indizes_08` +326 €, 2,69 | nein, schlechter | Kandidat: Holm und z fehlen |
| Geduld auf fünf Indizes (`geduld_stufen_fuenf`) | 5 Indizes | 997 | 77 % | 1,28 | 1,25 | 1,19 und 1,37 | 1,16 | 73,1 % | 0,62 | +126 € | `geduld_us_stufen` +98 €, 0,84 | nein, z niedriger | durchgefallen: Zufall 95 % |
| Geduld, zwei Kerzen später (`geduld_stufen_spaeter2`) | US500, US100 | 428 | 76 % | 0,98 | 0,97 | 0,72 und 1,34 | 1,06 | 13,0 % | −1,14 | −5 € | `geduld_us_stufen` +98 €, 0,84 | nein, schlechter | durchgefallen: Gewinnfaktor, 1,5-fache Kosten, Hälften, Zufall 95 % |
| Geduld, eine Kerze später (`geduld_stufen_spaeter1`) | US500, US100 | 464 | 77 % | 1,00 | 0,98 | 0,77 und 1,26 | 0,90 | 10,6 % | −1,29 | −1 € | `geduld_us_stufen` +98 €, 0,84 | nein, schlechter | durchgefallen: Gewinnfaktor, 1,5-fache Kosten, Hälften, 2026, Zufall 95 % |

Vor 2024 (nur Auskunft) lagen alle sechs im Minus: Modell mit mehr Merkmalen 3.563 Trades mit Gewinnfaktor 0,93,
strenger 1.843 Trades mit 0,93, Markt-Auswahl 1.284 Trades mit 0,98, Geduld auf fünf Indizes 1.813 Trades mit 0,69,
eine Kerze später 1.154 Trades mit 0,77, zwei Kerzen später 1.086 Trades mit 0,82.

## Notiz 1: später einsteigen

Der ganze Gewinn der Geduld-Regel steckt in der ersten Stunde nach dem Signal. 387 der 464 Trades der Fassung „eine
Kerze später“ liegen genau eine Stunde nach einem Einstieg des Originals. Diese 387 Paare brachten im Original +73 €
und eine Stunde später −12 €. 95 der 305 Gewinner unter diesen Paaren waren im Original schon am Ziel, bevor die
spätere Fassung überhaupt einsteigt. Bei zwei Stunden sind es 110 von 263. Die Regel kauft einen kurzen Rücksetzer. Wer wartet, kauft
nach der Erholung. Beide Fassungen sind schlechter als zufällige Tage (10,6 % und 13,0 % geschlagen) und kommen ins
Archiv.

## Notiz 2: mehr Merkmale, Termine und Verkäufe

**Modell mit mehr Merkmalen (`modell_breit`).** 1.724 Trades, 55 % Treffer, Gewinnfaktor 1,27, mit 1,5-fachen Kosten
1,22, Hälften 1,07 und 1,53, 2026 1,47, ohne die 5 besten Trades 1,23, 9 von 12 Quartalen im Plus. Zufallsvergleich
99,7 % geschlagen, z 2,49 (nötig 3 und Holm über 32, p 0,0045 statt 0,0016). Mit 10 € Risiko je Trade wären es 552 €
in 34 Monaten gewesen, rund 16 € im Monat, das tiefste Tal lag bei −144 €. Gegenüber dem Original sind 1.394 Trades
gleich, 330 neu und 480 weggefallen.

Die Haken: Die Änderung wurde nach dem Blick auf Ergebnis und Trades des Originals gewählt, darum zählt das Ergebnis
höchstens als Kandidat. Vor 2024 brachte dieselbe Bauart nichts (0,93). 2024 allein war fast null (+27 €), das Plus
kommt aus 2025 und 2026 (+262 € und +263 €). Die strengere Schwelle, die beim Original geholfen hatte, hilft hier
nicht (`modell_breit_08` ist schlechter als `modell_indizes_08`). Zwei Fassungen derselben Idee widersprechen sich
also, und das spricht eher für Zufall bei den Merkmalen als für einen festen Vorteil.

**Verkäufe.** Das Modell verkauft jetzt öfter (142 statt 34 Verkäufe), aber die Verkäufe verlieren: Gewinnfaktor 0,73,
zusammen −54 €. 98 der 142 Verkäufe fielen in das Jahr 2024. Die Käufe allein bringen +606 € mit Gewinnfaktor 1,32.
In der strengeren Fassung gab es nur 7 Verkäufe (−16 €). Aus schlechten Tagen wurden mit diesen Merkmalen also keine
guten Verkäufe.

Je Markt (`modell_breit`): US100 347 Trades mit 1,36 (+151 €), FTSE 292 mit 1,47 (+144 €), US500 316 mit 1,29
(+113 €), Nikkei 321 mit 1,20 (+78 €), DAX 448 mit 1,12 (+66 €). Der DAX bleibt der schwächste Markt, ist mit mehr
Merkmalen aber besser als im Original (1,04).

## Mehr oder weniger Märkte

**Die fünf profitabelsten Regeln nach Märkten (nur Auskunft aus den vorhandenen Trade-Listen, nichts neu gerechnet).**

| Regel | Markt | Trades | Gewinnfaktor | Euro |
|---|---|---|---|---|
| Vorhersage-Modell Indizes (`modell_indizes`, +457 €) | FTSE | 321 | 1,49 | +146 € |
| | US100 | 394 | 1,31 | +141 € |
| | US500 | 344 | 1,21 | +92 € |
| | Nikkei | 328 | 1,13 | +54 € |
| | DAX | 487 | 1,04 | +25 € |
| Vorhersage-Modell strenger (`modell_indizes_08`, +326 €) | US100 | 120 | 1,99 | +115 € |
| | US500 | 89 | 1,89 | +83 € |
| | Nikkei | 85 | 1,81 | +76 € |
| | FTSE | 67 | 1,66 | +48 € |
| | DAX | 200 | 1,01 | +4 € |
| Geduld mit sinkendem Ziel (`geduld_us_stufen`, +98 €) | US500 | 235 | 1,59 | +53 € |
| | US100 | 228 | 1,47 | +46 € |
| VIX-Sprung (`vix_sprung_us`, +92 €) | US100 | 68 | 2,13 | +51 € |
| | US500 | 68 | 1,76 | +41 € |
| VIX-Sprung DAX, FTSE, Nikkei (`vix_sprung_welt`, +74 €) | Nikkei | 68 | 1,66 | +36 € |
| | FTSE | 68 | 1,37 | +24 € |
| | DAX | 68 | 1,24 | +14 € |

Jeder Markt lag in jeder der fünf Regeln im Plus. Es gibt also keinen Markt, den man streichen müsste, um ein Minus
loszuwerden. Der DAX ist in beiden Modellen der schwächste Markt. Ihn jetzt zu streichen wäre Auswahl nach dem
Ergebnis. Die ehrliche Form dieser Idee ist die lernende Auswahl, und die steht unten. Die zwei VIX-Regeln zusammen
sind 340 Trades und +166 € (reine Summe bekannter Trades, kein neuer Test).

**Geduld auf fünf Indizes (`geduld_stufen_fuenf`).** 997 statt 463 Trades, +126 € statt +98 €, aber z 0,62 statt 0,84
und nur 73,1 % der Zufallsläufe geschlagen. Die drei neuen Märkte bringen kaum etwas: FTSE 205 Trades mit 1,25
(+22 €), Nikkei 186 mit 1,04 (+4 €), DAX 143 mit 1,02 (+2 €). Die 463 Trades auf US500 und US100 sind dieselben wie im
Original. Mehr Märkte heißt hier mehr Trades und kaum mehr Geld. Vor 2024 lag die Fassung bei 0,69.

**Lernende Markt-Auswahl (`modell_auswahl`).** Jeder Markt darf in einem Jahr nur handeln, wenn er in den zwei Jahren
davor mit mindestens 100 Trades einen Gewinnfaktor über 1,0 hatte. Das Ergebnis: 2024 durfte kein Markt handeln, 2025
durften US500, US100 und FTSE, 2026 alle fünf. 924 Trades, Gewinnfaktor 1,33 (Original 1,21), z 2,03 (Original 1,89),
aber nur +344 € statt +457 €. Die Auswahl hat 2025 den DAX (+44 € im Original) und den Nikkei (+33 €) ausgesperrt
und 2026 den DAX zugelassen, der dann −13 € brachte. Sie hat den schwachen Markt also nicht erkannt. Das passt zur
Lehre im Archiv, dass sich die schwächsten Märkte im Rückblick nicht sicher erkennen lassen. Alle 924 Trades sind
Trades des Originals mit demselben Ergebnis.

## Was nicht gebaut wurde und warum

- Ein Komitee aus mehreren Agenten, das je Markt eigene Regeln einstellt, wurde nicht aufgesetzt. Eigene Regeln je
  Markt auf denselben Kursen sind Auswahl danach, mit fünf Märkten und mehreren Stellschrauben je Markt gäbe es sehr
  viele Varianten und Holm würde entsprechend strenger. Die vorab festgelegte Form davon ist die lernende Auswahl.
- Keine eigenen Stops je Markt. Alle Stops stehen in ATR und passen sich dem Markt an.
- Kein Streichen des DAX oder eines anderen Markts nach dem Ergebnis.

## Gegenprüfung

- Die Summen und Gewinnfaktoren aller sechs Fassungen stimmen mit einer zweiten Rechnung aus der Trade-Liste überein.
- Alle 5.138 Einstiege liegen genau auf der Eröffnung der Einstiegskerze plus Spread (größte Abweichung 0,0002 R).
- Die Trades von Durchgang 1 und 2 kommen mit dem geänderten Programm unverändert heraus (6.853 und 2.584 Trades).
- Der US-Teil von `geduld_stufen_fuenf` und alle Trades von `modell_auswahl` sind Trade für Trade gleich dem Original.
- Vor dem Siegel: Entwicklung nur mit Kursen bis Ende 2023 und 40 Probeläufe auf erfundenen Märkten ohne Vorteil
  (z im Mittel −0,22, Streuung 0,91, kein Kandidat). Der Zufallsvergleich ist für diese Bauarten nicht zu freundlich.

## Was daraus folgt

- Bestanden hat nichts. Kein Bot ändert sich, nichts geht live.
- Über alle drei Durchgänge: 32 Regeln gerechnet, 0 bestanden, 6 Kandidaten. Fünf davon sind dasselbe
  Vorhersage-Modell in fünf Fassungen, der sechste ist der VIX-Sprung.
- Später einsteigen bei der Geduld-Regel ist erledigt und kommt ins Archiv, ebenso die Geduld-Regel auf fünf Indizes.
- `modell_breit` ist die einzige Fassung, die nach der vorab festgelegten Regel besser ist als ihr Original. Ein
  Beleg wäre erst eine Zählung ohne Order auf neuen Kursen. Ob sie mitgezählt wird, entscheidet nur Kiron.
- Die Verkäufe des Modells und die lernende Markt-Auswahl haben nicht geholfen.
- Alle Trades: `suche/ergebnis_trade_notizen_trades.csv.gz`, alle Zahlen: `suche/ergebnis_trade_notizen.json`.
