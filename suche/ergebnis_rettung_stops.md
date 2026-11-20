# Stop-Prüfung „Rettung“ für sechs Nicht-Gold-Bots

Regeln: suche/VORAB_rettung_stops.yaml (versiegelt am 19.11.2026 um 18:03 UTC, vor dem Rechnen). Gerechnet einmal am 19.11.2026 um 18:05 UTC.
Kirons Frage vom 19.11.2026: ob die Stops den Verlust so klein wie möglich halten, und ob man im Minus am Einstand oder mit kleinstem Minus schnell rausgehen sollte.
Gleiche Einstiege wie der Bot, nur der Ausstieg ändert sich. Gepaarter Test über alle Jahre, Holm über alle 15 Fassungen, dazu das Hauptfenster 2024 bis 2026.

**Ergebnis: 0 von 15 Fassungen bestehen, es gibt keinen Kandidaten. Kein Bot ändert sich.**

Die Rettung macht die einzelnen Verluste kleiner, aber sie schneidet mehr spätere Gewinner ab, als sie Verlierer rettet. Bei den Scalpern kostet sie fast den ganzen Gewinn, bei den Rücksetzern und beim Noise-Band ändert sie kaum etwas, beim 4-Std.-Ausbruch hilft sie ein wenig, aber nicht mehr, als der Zufall auch brächte.

## Die drei Fassungen

- **Rettung am Einstand.** War der Trade einmal einen halben Stop-Abstand im Minus, liegt ab der nächsten Kerze eine Limit-Order am bezahlten Einstieg. Kommt der Kurs zurück, endet der Trade ohne Verlust.
- **Rettung mit kleinem Minus.** Gleicher Auslöser, die Limit-Order liegt bei einem Viertel des Stop-Abstands im Minus.
- **Stop halb so weit.** Der Stop liegt halb so weit weg, Ziel und Zeit-Ausstieg bleiben. Nur für die drei Bots, die im Stop-Raster vom 04.11.2026 fehlten.

1 R ist der Abstand zum Stop des Bots. In Euro steht jeweils das Ergebnis mit 5 € Risiko je Trade.

## Hauptfenster 2024 bis 2026

| Bot | Fassung | Trades | Summe R | in Euro | Gewinnfaktor | Trefferquote | mittlerer Verlust R | tiefstes Tal R | Urteil |
|---|---|---|---|---|---|---|---|---|---|
| US500-Rücksetzer | heute | 41 | 6,93 | +35 € | 3,43 | 88 % | -0,57 | 1,65 |  |
| US500-Rücksetzer | Rettung am Einstand | 41 | 6,62 | +33 € | 3,29 | 83 % | -0,41 | 1,65 | durchgefallen |
| US500-Rücksetzer | Rettung mit kleinem Minus | 41 | 7,71 | +39 € | 5,26 | 83 % | -0,26 | 0,57 | durchgefallen |
| US100-Rücksetzer | heute | 40 | 7,89 | +39 € | 4,75 | 85 % | -0,35 | 1,57 |  |
| US100-Rücksetzer | Rettung am Einstand | 40 | 7,55 | +38 € | 5,57 | 75 % | -0,17 | 1,13 | durchgefallen |
| US100-Rücksetzer | Rettung mit kleinem Minus | 40 | 5,85 | +29 € | 2,75 | 75 % | -0,34 | 1,38 | durchgefallen |
| Nasdaq Noise-Band | heute | 29 | 4,00 | +20 € | 3,82 | 69 % | -0,16 | 0,47 |  |
| Nasdaq Noise-Band | Rettung am Einstand | 29 | 4,00 | +20 € | 3,82 | 69 % | -0,16 | 0,47 | durchgefallen |
| Nasdaq Noise-Band | Rettung mit kleinem Minus | 29 | 4,03 | +20 € | 3,90 | 69 % | -0,15 | 0,47 | durchgefallen |
| Scalper Nasdaq | heute | 182 | 50,31 | +252 € | 1,46 | 37 % | -0,96 | 15,01 |  |
| Scalper Nasdaq | Rettung am Einstand | 182 | -20,64 | −103 € | 0,77 | 21 % | -0,99 | 24,81 | durchgefallen |
| Scalper Nasdaq | Rettung mit kleinem Minus | 182 | -30,89 | −154 € | 0,69 | 21 % | -0,70 | 32,81 | durchgefallen |
| Scalper Nasdaq | Stop halb so weit | 182 | -2,14 | −11 € | 0,97 | 21 % | -0,50 | 13,66 | durchgefallen |
| Scalper DAX | heute | 175 | 75,48 | +377 € | 1,67 | 33 % | -0,97 | 13,39 |  |
| Scalper DAX | Rettung am Einstand | 175 | 39,84 | +199 € | 1,52 | 21 % | -1,00 | 11,60 | durchgefallen |
| Scalper DAX | Rettung mit kleinem Minus | 175 | 30,09 | +150 € | 1,35 | 21 % | -0,62 | 13,10 | durchgefallen |
| Scalper DAX | Stop halb so weit | 175 | 46,34 | +232 € | 1,67 | 21 % | -0,50 | 9,60 | durchgefallen |
| 4-Std.-Ausbruch DAX, FTSE, Nikkei | heute | 393 | 17,15 | +86 € | 1,30 | 53 % | -0,31 | 4,31 |  |
| 4-Std.-Ausbruch DAX, FTSE, Nikkei | Rettung am Einstand | 393 | 17,96 | +90 € | 1,32 | 52 % | -0,30 | 3,94 | durchgefallen |
| 4-Std.-Ausbruch DAX, FTSE, Nikkei | Rettung mit kleinem Minus | 393 | 18,14 | +91 € | 1,33 | 52 % | -0,29 | 4,09 | durchgefallen |
| 4-Std.-Ausbruch DAX, FTSE, Nikkei | Stop halb so weit | 393 | 16,32 | +82 € | 1,29 | 53 % | -0,31 | 4,75 | durchgefallen |

## Alle Jahre, gepaarter Test

„Eingegriffen“ zählt die Trades, bei denen die Fassung den Ausstieg geändert hat. „Gespart“ ist, was sie bei Trades gewann, die im Original verloren. „Verschenkt“ ist, was sie bei Trades verlor, die im Original gewannen.

| Bot | Fassung | Trades | Summe R heute | Summe R Fassung | Unterschied je Trade R | p | Holm | eingegriffen | davon später Gewinner | gespart R | verschenkt R |
|---|---|---|---|---|---|---|---|---|---|---|---|
| US500-Rücksetzer | Rettung am Einstand | 136 | 8,77 | 7,91 | -0,006 | 0,7052 | nein | 10 | 7 | 1,38 | -2,25 |
| US500-Rücksetzer | Rettung mit kleinem Minus | 136 | 8,77 | 9,32 | 0,004 | 0,4154 | nein | 22 | 7 | 4,54 | -4,00 |
| US100-Rücksetzer | Rettung am Einstand | 139 | 10,53 | 10,45 | -0,001 | 0,5235 | nein | 14 | 9 | 1,59 | -1,68 |
| US100-Rücksetzer | Rettung mit kleinem Minus | 139 | 10,53 | 8,96 | -0,011 | 0,7760 | nein | 25 | 9 | 2,36 | -3,93 |
| Nasdaq Noise-Band | Rettung am Einstand | 138 | 12,08 | 12,10 | 0,000 | 0,4979 | nein | 1 | 0 | 0,02 | 0,00 |
| Nasdaq Noise-Band | Rettung mit kleinem Minus | 138 | 12,08 | 12,16 | 0,001 | 0,4467 | nein | 8 | 0 | 0,08 | 0,00 |
| Scalper Nasdaq | Rettung am Einstand | 727 | -5,22 | -137,11 | -0,181 | 1,0000 | nein | 208 | 117 | 82,21 | -214,11 |
| Scalper Nasdaq | Rettung mit kleinem Minus | 727 | -5,22 | -170,54 | -0,227 | 1,0000 | nein | 234 | 117 | 78,04 | -243,36 |
| Scalper Nasdaq | Stop halb so weit | 727 | -5,22 | -51,42 | -0,064 | 0,9002 | nein | 586 | 117 | 226,41 | -272,61 |
| Scalper DAX | Rettung am Einstand | 607 | 107,04 | 10,37 | -0,159 | 0,9962 | nein | 202 | 77 | 118,31 | -214,98 |
| Scalper DAX | Rettung mit kleinem Minus | 607 | 107,04 | -19,13 | -0,208 | 0,9996 | nein | 230 | 77 | 108,06 | -234,23 |
| Scalper DAX | Stop halb so weit | 607 | 107,04 | 58,20 | -0,081 | 0,8866 | nein | 497 | 77 | 204,15 | -252,98 |
| 4-Std.-Ausbruch DAX, FTSE, Nikkei | Rettung am Einstand | 1119 | -2,22 | 0,26 | 0,002 | 0,0765 | nein | 29 | 12 | 4,60 | -2,12 |
| 4-Std.-Ausbruch DAX, FTSE, Nikkei | Rettung mit kleinem Minus | 1119 | -2,22 | 1,31 | 0,003 | 0,0991 | nein | 94 | 12 | 8,65 | -5,12 |
| 4-Std.-Ausbruch DAX, FTSE, Nikkei | Stop halb so weit | 1119 | -2,22 | -2,94 | -0,001 | 0,5610 | nein | 219 | 11 | 7,04 | -7,77 |

## Was die Zahlen sagen

- **Scalper.** Beim Nasdaq-Scalper griff die Rettung am Einstand 208 Mal ein. 91 dieser Trades hätten verloren, dort sparte sie 82 R. 117 wären aber noch Gewinner geworden, dort verschenkte sie 214 R. Im Hauptfenster wird aus +252 € ein Ergebnis von −103 €. Beim DAX-Scalper wird aus +377 € ein Ergebnis von +199 €. Diese Bots leben von wenigen großen Gewinnern, und gerade die laufen oft erst ins Minus.
- **Stop halb so weit.** Der einzelne Verlust halbiert sich, aber die Trefferquote fällt (Nasdaq-Scalper von 37 % auf 21 %). Unter dem Strich bleibt weniger: Nasdaq −11 € statt +252 €, DAX +232 € statt +377 €.
- **Rücksetzer.** Die Rettung greift nur 10 bis 25 Mal in zehn Jahren ein. Bei der Rettung am Einstand wären zwei von drei geretteten Trades noch Gewinner geworden (16 von 24), bei der Rettung mit kleinem Minus jeder dritte (16 von 47). Beim US500 sieht die Rettung mit kleinem Minus im Hauptfenster besser aus (7,71 R statt 6,93 R, tiefstes Tal 0,57 statt 1,65 R), beim US100 dieselbe Fassung schlechter. Das ist Streuung bei 40 Trades, kein Beleg (p 0,42 und 0,78).
- **Nasdaq Noise-Band.** Der Notstop liegt 5 ATR entfernt. Kein Trade wurde je gestoppt, und die Rettung griff nur bei 1 und bei 8 von 138 Trades ein. Sie ändert dort praktisch nichts.
- **4-Std.-Ausbruch DAX, FTSE, Nikkei.** Hier hilft die Rettung ein wenig (+90 € statt +86 € im Hauptfenster, p 0,08 und 0,10). Das reicht weder für Holm noch für einen Kandidaten (dafür wäre p höchstens 0,05 nötig).

## Nicht gerechnet

- Vortag EUR/USD, GBP/USD, GBP/JPY und der Mess-Bot. Die Stops liegen nur 2 bis 7 Pips entfernt, auf 5-Minuten-Kerzen ist das nicht fair zu rechnen. Die Frage gehört zur Nachrechnung mit Minutenkerzen im Thread Demo-Strategien.
- Noise USD/JPY und Scalper Nikkei. Beide haben in ihrer Regel keinen Stop und enden nach der Uhr am selben Tag.
- London GBP/USD. Sein Test-Programm liegt im privaten Repo auf einem anderen Unterbau.
- Dow-Rücksetzer. Im Projekt liegen keine Dow-Kerzen.
- Gold. Rechnet der Gold-Thread.

## Kontrolle

Alle 2.866 Originale kamen aus den Kerzen genau so heraus wie im Programm des Bots (größte Abweichung 0,000 R, Nasdaq Noise-Band gegen die alte Trade-Liste im Median 0,005 R).
Lesart vorsichtig, also eher gegen die neue Fassung: Limit erst ab der Kerze nach dem Auslöser, Füllung genau zum Limit, in der Stop-Kerze gilt der Stop zuerst.
