# Ergebnis Scalping mit Marktvorhersage vom 20.11.2026

Keine der sechs Varianten besteht, und keine ist Kandidat. Die beste brachte auf 1.000 € mit 10 € Risiko je Trade von
Januar 2024 bis Oktober 2026 rund +313 €, also etwa 0,9 % im Monat (Gewinnfaktor 1,05, nötig 1,2). Die Vorhersage hilft
etwas, denn ohne sie verlieren dieselben Einstiege klar (-525 € und -1.302 €). Nach den Kosten bleibt aber zu wenig
übrig. Mehr Hebel macht es schlimmer. Schon mit 10 % Risiko je Trade wäre selbst die beste Variante im August 2024 pleite
gewesen. Es geht nichts live, an keinem Bot ändert sich etwas.

Regeln: `suche/VORAB_vorhersage_scalp.yaml`, Siegel `e0984eb619263e20e377d07da0b84099c86200a16d4ff9bcbf29056de8b4a166`,
im Protokoll am 20.11.2026 16:37 UTC, committet und gepusht vor dem Rechnen, einmal gerechnet um 16:38 UTC. Programm
`suche/vorhersage_scalp.py`. Hauptfenster Januar 2024 bis Oktober 2026, nach Spread und Rutschen (Capital.com-Spread je
Viertelstunde). Gewinnfaktor heißt Gewinne geteilt durch Verluste. Holm über sechs Varianten.

Bild: `/mnt/project-files/vorhersage-scalp-2026-11-20/vorhersage-scalping.png` (Projektordner, gebaut mit `bild.py` daneben).

## Kirons Idee und wie sie gerechnet wurde

Kirons Wunsch: Wenn man weiß, dass ein Markt heute eher steigt, mehrmals am Tag kaufen, wenn er gerade gegen die
Vorhersage fällt, und nach einem kleinen Gewinn raus. Mit hohem Hebel, damit aus wenig Geld viel wird.

- **Vorhersage.** Das Vorhersage-Modell der großen Runde (läuft als Bot modell-indizes), der Tag nach einem VIX-Sprung
  (läuft als Bot vix-sprung) und zum Vergleich der einfache Tagestrend. Märkte US500, US100, DAX, FTSE 100, Nikkei 225.
- **Einstieg gegen die Bewegung.** Entweder drei Kauf-Limit-Orders 0,25, 0,5 und 0,75 ATR unter dem Kurs von 18:00 New
  York mit gemeinsamem Stop 1,25 ATR darunter ("3 Stufen"), oder ein Kauf, wenn der Kurs unter das Bollinger-Band fällt.
  ATR ist die mittlere Tagesspanne der letzten 14 Tage.
- **Kleines Ziel.** 0,2 ATR (bei Hebel 20 etwa 4 bis 9 % auf die Margin, das sind Kirons "3 bis 4 % oder mehr") oder
  0,5 ATR. Eine Stufe liegt nach ihrem Ziel wieder bereit, höchstens 6 Einstiege je Markt und Tag, nach einem Stop ist
  der Tag vorbei, alles schließt vor 15:55 New York.
- **Zufallsvergleich.** Die Vorhersage wird um k Tage verschoben und alles neu gerechnet (669 Verschiebungen). So zeigt
  sich, ob die Vorhersage hilft oder ob das Plus nur vom steigenden Markt kommt.

## Alle sechs und die zwei Kontrollen

Euro heißt Summe mit 10 € Risiko je Trade auf 1.000 € (10 € sind weg, wenn der Stop greift).

| Variante | Trades | je Woche | Treffer | Gewinnfaktor | 1,5-fache Kosten | Hälften | 2026 | Zufall geschlagen | z | Euro | Rendite pro Monat | Urteil |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Modell, 3 Stufen, Ziel 0,5 ATR (`modell_leiter_gross`) | 2.438 | 16,5 | 57 % | 1,05 | 1,03 | 1,01 und 1,11 | 1,14 | 96,9 % | 1,81 | +313 € | +0,9 % | durchgefallen: Gewinnfaktor |
| Modell, Bollinger, Ziel 0,5 ATR (`modell_band_gross`) | 1.805 | 12,2 | 58 % | 1,06 | 1,03 | 1,12 und 1,00 | 0,93 | 91,0 % | 1,42 | +312 € | +0,9 % | durchgefallen: Gewinnfaktor, Hälften, 2026, Zufall |
| VIX-Sprung, 3 Stufen, Ziel 0,2 ATR (`vix_leiter_klein`) | 833 | 5,6 | 79 % | 1,18 | 1,15 | 1,20 und 1,15 | 1,26 | 94,0 % | 1,48 | +238 € | +0,7 % | durchgefallen: Gewinnfaktor, Zufall |
| Modell, Bollinger, Ziel 0,2 ATR (`modell_band_klein`) | 2.659 | 18,0 | 73 % | 1,01 | 0,97 | 1,02 und 1,01 | 0,99 | 93,7 % | 1,55 | +68 € | +0,2 % | durchgefallen: Gewinnfaktor, Kosten, 2026, Zufall |
| Modell, 3 Stufen, Ziel 0,2 ATR (`modell_leiter_klein`) | 3.462 | 23,5 | 72 % | 0,98 | 0,94 | 0,93 und 1,05 | 1,11 | 95,4 % | 1,66 | -107 € | -0,3 % | durchgefallen: Gewinnfaktor, Kosten, Hälften |
| Tagestrend, 3 Stufen, Ziel 0,2 ATR (`trend_leiter_klein`) | 5.996 | 40,6 | 68 % | 0,85 | 0,82 | 0,85 und 0,86 | 0,90 | 41,0 % | -0,12 | -1.587 € | -4,7 % | durchgefallen: alles |
| Kontrolle ohne Vorhersage, 3 Stufen (`immer_leiter_klein`) | 6.745 | 45,7 | 70 % | 0,89 | 0,85 | 0,88 und 0,91 | 1,00 | | | -1.302 € | -3,8 % | nur Auskunft |
| Kontrolle ohne Vorhersage, Bollinger (`immer_band_klein`) | 5.156 | 34,9 | 72 % | 0,94 | 0,89 | 0,98 und 0,91 | 0,95 | | | -525 € | -1,5 % | nur Auskunft |

Vor 2024 (nur Auskunft) lag jede Variante unter 1: Modell 3 Stufen 0,80 und 0,88, Modell Bollinger 0,90 und 0,93,
Tagestrend 0,80, VIX-Sprung 0,95.

## Was das heißt

- **Die Vorhersage hilft ein wenig.** Mit dem Modell schlagen die Einstiege 91 bis 97 % der verschobenen Vorhersagen,
  ohne Vorhersage verlieren sie. Das ist ein Hinweis, aber kein Beleg (z 1,4 bis 1,8, nötig 3, Holm nicht erfüllt).
  Der einfache Tagestrend hilft gar nicht (41 %).
- **Die Kosten fressen den Rest.** Grob geschätzt aus der Rechnung mit 1,5-fachen Kosten kosten Spread und Rutschen bei
  den Modell-Varianten 28 bis 46 R, das ist etwa die Hälfte des Gewinns vor Kosten. Mit 20 Trades pro Woche zahlt man
  sehr oft den Spread.
- **Hohe Trefferquote ist kein Beweis.** 72 bis 79 % Treffer mit dem kleinen Ziel, trotzdem kaum Gewinn. Ein Stop
  kostet etwa 1 R, ein Ziel bringt nur 0,2 bis 0,4 R.
- **Fast nur Käufe.** Das Modell sagt fast immer "steigt" (2.401 Käufe, 37 Verkäufe bei der besten Variante). Die
  wenigen Verkäufe verloren (Gewinnfaktor 0,33).
- **FTSE war der stärkste Markt** (1,28 bis 1,48), DAX der schwächste (0,86 bis 0,94). Einen Markt nach dem Ergebnis
  auszuwählen wäre Auswahl danach und zählt nicht.

## Mehr Hebel (nur Auskunft)

Dieselben Trades, aber jeder Trade riskiert einen festen Anteil des Kontos (Gewinne bleiben drin), Start 1.000 €.

| Variante | 1 % je Trade | 2 % | 5 % | 10 % | 20 % |
|---|---|---|---|---|---|
| Modell, 3 Stufen, Ziel 0,5 ATR | 1.113 €, tiefstes Tal -47 % | 801 €, Tal -75 % | pleite 05.08.2024 | pleite 12.04.2024 | pleite 19.01.2024 |
| Modell, Bollinger, Ziel 0,5 ATR | 1.259 €, Tal -28 % | 1.340 €, Tal -50 % | 563 €, Tal -85 % | pleite 23.09.2026 | pleite 19.04.2024 |
| VIX-Sprung, 3 Stufen, Ziel 0,2 ATR | 1.221 €, Tal -22 % | 1.370 €, Tal -40 % | 927 €, Tal -80 % | pleite 05.08.2024 | pleite 15.04.2024 |

"Pleite" heißt unter 10 € (dann geht kein Trade mehr). Ab 2 % Risiko je Trade hätte die Margin bei Hebel 20 bei der
Modell-Leiter an etwa 100 Einstiegen über dem Kontostand gelegen, der Broker hätte diese Orders abgelehnt. Der
5. August 2024 war der Tag des Yen-Schocks. An so einem Tag laufen alle drei Stufen auf allen Märkten in den Stop.
Hoher Hebel macht aus einem kleinen Vorteil keinen großen, er macht den einen schlechten Tag tödlich.

Die Hebel-Auskunft wurde nach der Rechnung einmal neu aus den gespeicherten Trades geschrieben
(`python -m suche.vorhersage_scalp hebel -`), weil ein Stop in der Kerze der Füllung zuerst vor seinem eigenen Einstieg
gebucht wurde. Die Trades und Urteile sind dieselben.

## Was daraus folgt

- Bestanden hat nichts. Kein Bot ändert sich, nichts geht live.
- Die sechs Varianten stehen im Archiv (`suche/VERWORFEN.md`).
- Ein möglicher nächster Schritt mit eigenem Siegel wäre, das Modell nicht zum Scalpen, sondern als Filter für einen
  Bot zu nehmen, der schon einen Vorteil hat (zum Beispiel die Rücksetzer nur an Tagen mit "steigt"). Das ist nicht
  gerechnet und nur auf Kirons Zeichen.
- Alle Trades: `suche/ergebnis_vorhersage_scalp_trades.csv.gz`, alle Zahlen: `suche/ergebnis_vorhersage_scalp.json`.
