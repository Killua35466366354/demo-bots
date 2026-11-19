# Ergebnis der YouTube-Runde vom 19.11.2026

Keine der vier Regeln besteht. Am nächsten kommen Williams %R auf US500 und US100 (zu wenige Trades) und der
4-Std.-Ausbruch auf Bitcoin (2026 im Minus). Die beiden beliebten Krypto-Ideen „CME-Lücke schließt sich immer" und
„Montagsbereich" verlieren deutlich. Es geht nichts live, an keinem Bot ändert sich etwas.

Regeln: `suche/VORAB_youtube_runde.yaml`, Siegel `6b248b29d019b2c30924318c2ffc83e85fb9c3d2890b67bef21393a2c0d3209a`,
im Protokoll am 19.11.2026 07:15 UTC, einmal gerechnet um 07:17 UTC. Programm `suche/youtube_runde.py`, Rechnung von
`suche/rueckblick.py` unverändert. Hauptfenster Januar 2024 bis Oktober 2026, nach Spread, Rutschen und Übernachtgebühr.

## In Euro

Mit 1.000 € und 10 € Risiko je Trade wäre aus den 1.000 € geworden:

| Regel | Zeitebene | Trades | Gewinnfaktor | Euro | Urteil | woran gescheitert |
|---|---|---|---|---|---|---|
| Williams %R US500/US100 | Tage | 77 | 2,66 | 1.131 € | durchgefallen | unter 100 Trades, z 2,35 unter 3 |
| 4-Std.-Ausbruch Bitcoin/Ether | 16 Stunden | 319 | 1,23 | 1.139 € | durchgefallen | 2026 Gewinnfaktor 0,91, z 2,35 unter 3 |
| CME-Lücke Bitcoin/Ether | Wochenende bis Freitag | 160 | 0,77 | 798 € | durchgefallen | fast alles |
| Montagsbereich Bitcoin/Ether | Woche | 286 | 0,69 | 376 € | durchgefallen | fast alles |

Bild: `/mnt/project-files/strategie-suche/youtube-2026-11-19/youtube-runde-euro.png`.

## Einzelheiten

**Williams %R (Quantified Strategies).** 77 Trades, 81 % Treffer, beide Hälften 2,39 und 3,28, 2026 1,75 (18 Trades),
mit 1,5-fachen Kosten 2,65, ohne die 5 besten 2,21. S&P 500 4,21 (41 Trades), Nasdaq 1,82 (36). Zufallsvergleich
99,9 % geschlagen, p 0,003 (Holm erfüllt), z 2,35 (für z 3 wären 16,2 R nötig gewesen, es waren 13,1 R).
Vor 2024 als Auskunft 327 Trades, Gewinnfaktor 1,51. Die Regel ist stark, aber sie ist fast derselbe Trade wie der
laufende Trend-Rücksetzer. Bei 47 von 77 Trades gab es binnen 2 Tagen auch ein RSI-2-Kaufsignal über dem
200-Tage-Schnitt. Sie brächte also mehr vom Selben, kaum neue Streuung.

**4-Std.-Ausbruch auf Krypto** (der Gold-Kandidat, jede Zahl gleich). 319 Trades, 2,2 je Woche, Gewinnfaktor 1,23,
1,5-fache Kosten 1,19, Hälften 1,32 und 1,13, 2026 0,91 (87 Trades). Bitcoin 1,42, Ether 1,06. Long 1,40, Short 1,02.
Ohne die 5 besten Trades 0,98, der Gewinn hängt also an wenigen großen Trends. Zufall 98,7 % geschlagen, z 2,35.
Vor 2024 425 Trades, 1,10.

**CME-Lücke.** 45 % Treffer bei Ziel und Stop gleich weit. Bitcoin 0,61, Ether 0,91. Vor 2024 0,73. Die Lücke
schließt sich oft, aber zu oft erst, nachdem der Kurs vorher gleich weit in die andere Richtung gelaufen ist.

**Montagsbereich (Ausbruch).** 31 % Treffer bei 2 R Ziel, Gewinnfaktor 0,69, 2026 0,52. Vor 2024 0,81.

## Probelauf und Entwicklung (vor dem Siegel)

8 Saaten auf erfundenen Märkten ohne Vorteil: keine der 32 Rechnungen bestand oder wurde Kandidat, z im Mittel 0,0,
Streuung 1,15. Entwicklung März 2021 bis Dezember 2023: williams_us 1,20, cme 0,61, ausbruch4h 0,84, montag 0,70.

## Was das heißt

- Was YouTube am meisten zeigt, hat das Projekt jetzt fast vollständig gerechnet. Ohne Ausnahme gilt: was unter
  einer Stunde handelt, verliert nach Kosten. Was hält, kauft Rückgänge auf US-Indizes, und das läuft schon.
- Krypto als neue Anlageklasse brachte keinen Beleg. Der 4-Std.-Ausbruch auf Bitcoin ist der einzige Rest, aber 2026
  verlor er, und das Ergebnis hängt an wenigen Trends.
- Keine Nachbesserung: kein anderes Fenster, keine andere Schwelle, keine weitere Variante.

## Ideen-Vorrat (nicht gerechnet)

- Williams %R als Zwilling des US500-Rücksetzers wäre nach `suche/VORAB_zwilling.yaml` nur ein Schatten und bräuchte
  eine eigene, neue Regeldatei. Weil die Trades meist dieselben sind, lohnt das wenig.
- Der 4-Std.-Ausbruch auf Bitcoin allein wäre eine Auswahl nach dem Blick auf das Ergebnis und darf nicht neu
  „bestehen". Höchstens ein Vorwärtstest ohne Order, nur nach Kirons Wahl.
