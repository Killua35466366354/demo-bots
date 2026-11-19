# Runde „Starker Rückblick“: Ergebnis

Regeln: suche/VORAB_rueckblick.yaml (Prüfsumme 244db0bd im Protokoll, festgelegt am 18.11.2026 21:41 UTC, vor der Rechnung). Programm: suche/rueckblick.py, Daten: suche/rueckblick_daten.py.
Daten: HistData 5-Minuten-Kerzen (Bid, echtes UTC). Kosten: echter Capital.com-Spread je Viertelstunde, Stop-Orders einen halben Spread schlechter, Übernachtgebühr eingerechnet. Hauptfenster: Einstieg 01.01.2024 bis 30.10.2026, Hälfte 2 ab 01.06.2025. Gerechnet wurde genau einmal.

**Ergebnis: Keine der sechs Varianten besteht. Eine ist Kandidat (4-Std.-Ausbruch auf DAX, FTSE und Nikkei), fünf sind durchgefallen.** Kandidat heißt nach der Regeldatei: nicht bestanden und kein Beleg, höchstens ein Schattenlauf ohne Order.

## Die sechs Varianten im Hauptfenster

| Variante | Urteil | Trades | je Woche | Gewinnfaktor | Summe R | Treffer | 1,5x Kosten | Hälfte 1 | Hälfte 2 | 2026 | Zufall geschlagen | p | Holm | z | nötig für z = 3 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 4-Std.-Ausbruch Silber (`ausbruch4h_silber`) | durchgefallen | 139 | 0,94 | 1,33 | 6,9 | 55 % | 1,18 | 0,82 (56) | 1,90 (83) | 1,78 (37) | 98,7 % | 0,0149 | nein | 2,29 | 10,8 R |
| 4-Std.-Ausbruch S&P 500 und Nasdaq (`ausbruch4h_us_index`) | durchgefallen | 332 | 2,25 | 0,90 | -6,4 | 49 % | 0,89 | 1,01 (152) | 0,80 (180) | 0,78 (98) | 31,9 % | 0,6811 | nein | -0,49 | 32,1 R |
| 4-Std.-Ausbruch DAX, FTSE und Nikkei (`ausbruch4h_welt_index`) | Kandidat | 389 | 2,64 | 1,24 | 13,4 | 53 % | 1,20 | 1,09 (187) | 1,40 (202) | 1,59 (109) | 96,6 % | 0,0358 | nein | 1,81 | 24,7 R |
| 4-Std.-Ausbruch 7 Währungspaare (`ausbruch4h_fx`) | durchgefallen | 955 | 6,47 | 0,79 | -38,5 | 45 % | 0,73 | 0,79 (485) | 0,79 (470) | 0,69 (275) | 33,4 % | 0,6667 | nein | -0,45 | 22,2 R |
| Dienstag S&P 500 und Nasdaq (`dienstag_us_index`) | durchgefallen | 87 | 0,59 | 0,99 | 0,0 | 46 % | 0,98 | 0,96 (47) | 1,04 (40) | 1,23 (25) | 37,3 % | 0,6274 | nein | -0,26 | 10,1 R |
| Dienstag DAX, FTSE und Nikkei (`dienstag_welt_index`) | durchgefallen | 188 | 1,27 | 1,13 | 1,9 | 56 % | 1,10 | 1,56 (84) | 0,88 (104) | 0,83 (63) | 66,8 % | 0,3328 | nein | 0,45 | 10,7 R |

Lesehilfe: R ist das Ergebnis eines Trades geteilt durch seinen Stop-Abstand, 1 R ist also der geplante Verlust am Stop. Der Gewinnfaktor ist Gewinne geteilt durch Verluste. „Zufall geschlagen“ sagt, wie viele der Zwillings-Läufe (dieselben Trades an anderen Tagen) schlechter waren. z misst den Abstand zum Mittel dieser Läufe, die Hürde ist 3. Die letzte Spalte nennt die Summe in R, die für z = 3 nötig gewesen wäre.

Durchgefallen bei:

- 4-Std.-Ausbruch Silber: Hälften, Holm, z unter 3
- 4-Std.-Ausbruch S&P 500 und Nasdaq: Gewinnfaktor, 1,5-fache Kosten, Hälften, 2026, Zufall 95 %, Holm, z unter 3
- 4-Std.-Ausbruch DAX, FTSE und Nikkei: Holm, z unter 3
- 4-Std.-Ausbruch 7 Währungspaare: Gewinnfaktor, 1,5-fache Kosten, Hälften, 2026, Zufall 95 %, Holm, z unter 3
- Dienstag S&P 500 und Nasdaq: Trades, Gewinnfaktor, 1,5-fache Kosten, Hälften, Zufall 95 %, Holm, z unter 3
- Dienstag DAX, FTSE und Nikkei: Gewinnfaktor, Hälften, 2026, Zufall 95 %, Holm, z unter 3

## Einzelheiten je Variante

| Variante | long | short | ohne die 5 besten Trades | je Markt | ältere Jahre (Auskunft) |
|---|---|---|---|---|---|
| 4-Std.-Ausbruch Silber | 1,58 (102, 7,7 R) | 0,89 (37, -0,8 R) | 1,02 (0,4 R) | Silber 1,33 (139, 6,9 R) | 0,51 (360, -45,6 R) |
| 4-Std.-Ausbruch S&P 500 und Nasdaq | 0,88 (281, -6,8 R) | 1,03 (51, 0,3 R) | 0,78 (-14,6 R) | S&P 500 0,75 (171, -10,0 R), Nasdaq 1,13 (161, 3,6 R) | 0,80 (947, -36,6 R) |
| 4-Std.-Ausbruch DAX, FTSE und Nikkei | 1,31 (332, 13,8 R) | 0,96 (57, -0,4 R) | 1,11 (6,4 R) | DAX 1,94 (121, 12,2 R), FTSE 0,76 (133, -6,0 R), Nikkei 1,37 (135, 7,2 R) | 0,87 (719, -16,8 R) |
| 4-Std.-Ausbruch 7 Währungspaare | 0,85 (566, -14,6 R) | 0,71 (389, -23,9 R) | 0,73 (-48,3 R) | EURUSD 0,97 (135, -0,8 R), GBPUSD 0,81 (134, -4,6 R), USDJPY 1,02 (139, 0,4 R), USDCHF 0,92 (130, -2,0 R), USDCAD 0,51 (161, -17,0 R), AUDUSD 0,81 (129, -4,4 R), NZDUSD 0,62 (127, -10,0 R) | 0,83 (3026, -94,1 R) |
| Dienstag S&P 500 und Nasdaq | 0,99 (87, -0,0 R) | – (0, 0,0 R) | 0,72 (-2,1 R) | S&P 500 0,89 (43, -0,5 R), Nasdaq 1,13 (44, 0,4 R) | 1,29 (306, 7,3 R) |
| Dienstag DAX, FTSE und Nikkei | 1,13 (188, 1,9 R) | – (0, 0,0 R) | 0,91 (-1,3 R) | DAX 1,24 (61, 1,2 R), FTSE 0,67 (64, -2,1 R), Nikkei 1,82 (63, 2,9 R) | 0,99 (396, -0,4 R) |

## Was das heißt

- **4-Std.-Ausbruch auf DAX, FTSE und Nikkei (Kandidat):** 389 Trades, etwa 2,6 je Woche, Gewinnfaktor 1,24, mit
  1,5-fachen Kosten 1,20, beide Hälften und 2026 im Plus. Er schlägt 96,6 % der Zwillings-Läufe, aber z ist 1,81 statt 3
  und Holm fehlt (p 0,036, nötig wären 0,0083). Der Gewinn kommt vom DAX (1,94) und vom Nikkei (1,37), der FTSE verliert
  (0,76). Er kommt fast ganz aus Käufen in einem steigenden Markt, die Verkäufe liegen bei 0,96. Ohne die fünf besten
  Trades bleibt 1,11. In den Jahren vor 2024 war dieselbe Regel auf diesen Märkten im Minus (0,87). Das ist kein Beleg.
- **4-Std.-Ausbruch auf Silber:** Gewinnfaktor 1,33 und 98,7 % der Zwillinge geschlagen, aber die erste Hälfte war im
  Minus (0,82) und ohne die fünf besten Trades bleibt 1,02. Durchgefallen.
- **4-Std.-Ausbruch auf S&P 500, Nasdaq und Devisen:** im Minus. Auf den sieben Währungspaaren verliert die Regel
  gleichmäßig in beiden Hälften (0,79). Der Gold-Kandidat überträgt sich also nicht einfach auf andere Märkte.
- **Dienstag-Regel (Turnaround Tuesday):** auf den US-Indizes 87 Trades mit Gewinnfaktor 0,99, auf DAX, FTSE und Nikkei
  1,13 mit einer zweiten Hälfte im Minus. Von einem Vorteil ist 2024 bis 2026 nichts zu sehen.
- **Beispiel in Euro:** Mit 10 € Risiko je Trade hätte der Kandidat in knapp drei Jahren etwa +134 € gebracht, Silber
  +69 €, die Devisen-Variante −385 €. Für „bestanden“ hätte der Kandidat etwa +247 € gebraucht.

## Probelauf vor dem Siegel

Das ganze Programm lief 24-mal auf erfundenen Märkten ohne Vorteil (jede 5-Minuten-Kerze bekommt ein zufälliges
Vorzeichen, die Schwankung über den Tag bleibt). Von 144 Läufen der sechs Varianten bestand keiner, keiner wurde
Kandidat. z lag je Variante im Mittel bei −0,3 bis 0,2 mit Streuung 0,6 bis 1,0, das größte z war 2,5. 7 von 144 Läufen
schlugen 95 % der Zwillinge, erwartet sind etwa 7. Der Zufallsvergleich ist für diese sechs Varianten also richtig
geeicht. Aufruf: `python -m suche.rueckblick probelauf <Arbeitsordner> <Saat>`.

Auf den Kursen bis Ende 2023 (nur zur Prüfung des Programms) lag der 4-Std.-Ausbruch auf allen vier Marktgruppen im
Minus (0,38 bis 0,84), die Dienstag-Regel bei 1,21 (US) und 0,93 (DAX, FTSE, Nikkei).

## Befund: Die Vortag-Regel lässt sich mit Kerzen nicht fair rechnen

Im Entwurf standen zwei weitere Familien: die Vortag-Regel (Ausbruch über das Hoch oder unter das Tief des Vortags, Stop
0,5 ATR der 15-Minuten-Kerzen) auf Indizes und Metallen, mit und ohne Tagestrend. Sie sind nicht Teil der versiegelten
Datei und wurden auf den Kursen ab 2024 nicht gerechnet.

- Der Stop ist so eng, dass er oft schon in der Einstiegskerze liegt. Dann entscheidet die angenommene Reihenfolge von
  Hoch und Tief in dieser Kerze über das Ergebnis. Zählt die ganze Kerze, verliert die Regel fast jeden Trade. Liest man
  die Kerze wie TradingView (Eröffnung näher am Hoch: erst Hoch, dann Tief), zeigte sie auf den US-Indizes bis 2023
  einen Gewinnfaktor von 1,40 und z 6,9.
- Im Probelauf ohne jeden Vorteil streute das z dieser Familien mit 3,4 statt 1 und erreichte 4,4. Der Zufallsvergleich
  ist dort also nicht geeicht, weil der echte Trade die günstige Lesart bekommt und der Zwilling nicht.
- Das Komitee hat nachgemessen (Projektordner `komitee-2026-11-18/pruefung/eichung/`, Gold bis 2023, 242 Trades): Die
  Lesart sagt bei 15 % der Trades „Stop in der Einstiegskerze“, 1-Minuten-Kerzen zeigen 30 bis 75 %. Der Fehler geht
  fast immer in die günstige Richtung. Auch 1-Minuten-Kerzen lösen das nicht auf.
- Folge: Diese Regel ist nur mit Tick-Daten oder live prüfbar. Der Test der drei laufenden Vortag-Bots (EUR/USD,
  GBP/USD, GBP/JPY) nutzte dieselbe Lesart auf 15-Minuten-Kerzen. Ihr Rückblick ist darum wahrscheinlich zu günstig.
  Das Komitee prüft das an ihren echten Demo-Trades. An den Bots wurde nichts geändert.

## Ideen-Vorrat aus der Recherche vom 18.11.2026

Vier Berichte (Studien, Bücher und Blogs, Foren mit Live-Zahlen, andere Datenquellen) liegen im Projektordner
`strategie-suche/rueckblick-2026-11-18/research/`. Die Recherche fand nichts, das klar stärker ist als das Vorhandene
und sich mit unseren Kursen sauber rechnen lässt. Noch nicht gerechnet, in dieser Reihenfolge sinnvoll:

| Nr. | Idee | Quelle | Trades | Hauptzweifel |
|---|---|---|---|---|
| R1 | Umschichtungs-Druck: Laufen Aktien den Anleihen davon, ist der S&P 500 am nächsten Tag schwächer, vor allem in den letzten 5 Handelstagen des Monats | Harvey, Mazzoleni, Melone 2025 (NBER 33554) | täglich bis 1 je Woche | nur im Rückblick der Autoren belegt, viel Gewinn aus 2008 und 2020, braucht eine Anleihe-Reihe von außen |
| R2 | Nacht vor Arbeitsmarktbericht, ISM und BIP: US500 von 16:00 New York bis kurz vor der Zahl kaufen | Hu, Pan, Wang, Zhu 2022 (JFE) | etwa 36 im Jahr | der Verwandte vor der Fed-Sitzung ist hier schon durchgefallen, wenig Trades |
| R3 | Tag nach einem VIX-Sprung von 2,5 oder 3 Punkten: US500 einen Tag kaufen | dieselbe Studie | selten | braucht VIX-Tagesdaten (CBOE, ohne Schlüssel) |
| R4 | Zahlentag-Prämie: US500 über Tage mit Arbeitsmarktbericht, CPI und Fed halten | Savor und Wilson 2013 (JFQA) | etwa 0,6 je Woche | vor allem Marktrichtung, laut R2-Studie hält wohl nur der Arbeitsmarkttag |
| R5 | Letzte halbe Stunde folgt dem Tag („rest of day“), 5 Indizes | Baltussen, Da, Lasser, Martens 2021 (JFE) | etwa 25 je Woche | nur 2,7 Basispunkte je Trade vor Kosten, überschneidet sich mit dem Scalping-Komitee |
| R6 | VIX gegen VIX3M als Schalter für die vorhandenen Index-Bots | Fassas und Hourvouliades 2019, die einfache Fassung ist Händler-Wissen ohne saubere Studie | kein eigener Trade | die Quellen widersprechen sich in der Richtung, nur als Auskunft an vorhandenen Trades prüfen |
| R7 | Schwäche kaufen auf US-Indizes mit anderen Auslösern (unteres Band plus IBS, 3-Tage-Hoch/Tief, mehrere Tage im Minus, %b) | Connors, Quantitativo | je 6 bis 15 im Jahr | derselbe Effekt wie der laufende RSI(2)-Bot, mehr Trades, aber keine neue Quelle von Gewinn |
| R8 | Übernacht gegen Tag, Paar DAX gegen FTSE | Della Corte, Kosowski, Wang 2015 (Scout des Komitees) | täglich | vor Kosten gerechnet, widerspricht unserem eigenen Befund zur Eröffnung |
| R9 | Vortag-Regel auf Indizes | eigene Regel | etwa 4 je Woche | nur mit Tick-Daten oder live prüfbar (siehe oben) |

Nicht testen (spart eine Runde): Übernacht-Drift 2 bis 3 Uhr New York (laut New York Fed seit 2021 verschwunden),
Intraday-Momentum auf Devisen (0,3 Basispunkte je Trade), R-Breaker und HLHB aus Foren (kein Beleg), Kalender-Effekte
mit weniger als 12 Trades im Jahr.

## Warum live meist schlechter ist, und was daraus für den Live-Vergleich folgt

Die Zahlen aus der Recherche: Bei 215 Strategien von Banken fiel die Kennzahl Sharpe (Rendite geteilt durch
Schwankung) im Mittel von 1,20 im Rückblick auf 0,31 live (Suhonen, Lennkh, Perez 2017). Bei 72 veröffentlichten
Strategien blieb etwa die Hälfte übrig (Falck, Rej, Thesmar 2022). Die Gründe der Größe nach: Auswahl der besten aus
vielen Versuchen, Verfall nach der Veröffentlichung, Kosten und Ausführung, die der Rückblick zu günstig rechnet, und
ein Demokonto füllt freundlicher als echtes Geld. Nur den dritten Grund kann ein Demo-Versuch schnell messen.

Eigene Rechnung dazu: Um einen Gewinnfaktor von 1,3 von 1,0 zu unterscheiden, braucht man etwa 360 bis 400 Trades.
Bei 40 Live-Trades zeigt ein Bot ohne jeden Vorteil in 32 % der Fälle einen Gewinnfaktor ab 1,2, bei 100 Trades in
18 %, bei 200 Trades in 9 %. Ein paar Wochen live können einen Vorteil also nicht beweisen. Sie können aber zeigen, ob
live dasselbe passiert wie im Rückblick, weil dabei jeder Trade mit sich selbst verglichen wird. Dafür reichen etwa
25 bis 100 Trades.

Vorschlag für die nächste Regeldatei eines Live-Versuchs (noch nicht festgelegt, mit dem Thread der Demo-Strategien
abzustimmen):

1. Zwei getrennte Urteile: Treue (ist live gleich dem Rückblick auf denselben Trades) und Vorteil (ist der Gewinn echt).
2. Zu jedem Live-Trade ein Rückblick-Zwilling auf den Kerzen des Brokers. Je Trade mitschreiben: Wunschkurs, Füllkurs,
   Spread beim Einstieg, Rutschen in R, Gebühr, abgelehnte Orders.
3. Treue bestanden nach 50 Paaren, wenn mindestens 95 % der Signale übereinstimmen und live im Mittel höchstens
   0,05 R schlechter ist. Reparatur-Stopp ab 25 Paaren, wenn live im Mittel mehr als 0,10 R schlechter ist.
4. Erwartung für live vorab auf die Hälfte des Rückblicks setzen. Was danach und mit 1,5-fachen Kosten nicht über
   Gewinnfaktor 1,0 liegt, geht nicht live.
5. Pause nur an festen Prüfpunkten (20, 40, 60, 100, 150 Trades) gegen eine vorab gerechnete Untergrenze.
6. In jeder Regeldatei steht, wie viele Varianten probiert wurden.
7. Das Urteil über den Vorteil fällt für eine vorab benannte Gruppe ab etwa 350 Trades. Bots auf demselben Markt
   zählen je Tag als ein Trade.

## Dateien

- Zahlen: `suche/ergebnis_rueckblick.json`, alle 2.090 Trades: `suche/ergebnis_rueckblick_trades.csv.gz`
- Bild und Recherche-Berichte: Projektordner `strategie-suche/rueckblick-2026-11-18/`
- Nachrechnen: `python -m suche.rueckblick_daten <Arbeitsordner>`, dann `python -m suche.rueckblick rechnen <Arbeitsordner>`
- Kein Bot wurde gebaut oder geändert. Live geht nur nach Kirons Wahl auf einer Karte und über einen PR.
