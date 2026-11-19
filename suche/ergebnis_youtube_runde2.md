# Ergebnis der zweiten YouTube-Runde vom 19.11.2026

Keine der fünf Regeln besteht. Am nächsten an null kommt ICT Silver Bullet auf US100 und US500 (Gewinnfaktor 1,01,
also nach Kosten etwa plus minus null). Supertrend, NR7 und Bollinger mit RSI verlieren. Bollinger mit RSI verliert am
meisten, auf Krypto noch mehr als auf Devisen. Es geht nichts live, an keinem Bot ändert sich etwas.

Regeln: `suche/VORAB_youtube_runde2.yaml`, Siegel `7309e3768bd8fe75b546b3231e7691173aba190d4058acf16673c5afa08454eb`,
im Protokoll am 19.11.2026 07:42 UTC, committet und gepusht vor dem Rechnen, einmal gerechnet um 07:44 UTC. Programm
`suche/youtube_runde2.py`, Rechnung von `suche/rueckblick.py` unverändert. Hauptfenster Januar 2024 bis Oktober 2026,
nach Spread, Rutschen und Übernachtgebühr. Gewinnfaktor heißt Gewinne geteilt durch Verluste.

## In Euro

Mit 1.000 € und 10 € Risiko je Trade wäre aus den 1.000 € geworden:

| Regel | Zeitebene | Trades | je Woche | Gewinnfaktor | Euro | Urteil |
|---|---|---|---|---|---|---|
| ICT Silver Bullet US100/US500 | 5 Min., bis 2 Std. | 1.298 | 8,8 | 1,01 | 1.035 € | durchgefallen, Gewinnfaktor und 1. Hälfte |
| NR7-Ausbruch, 11 Märkte | Tage | 1.018 | 6,9 | 0,97 | 830 € | durchgefallen |
| Supertrend 4 Std., 7 Märkte | 4 Std., Tage | 379 | 2,6 | 0,91 | 836 € | durchgefallen, 2026 0,55 |
| Bollinger + RSI, Devisen/Gold/Indizes | Stunden | 4.085 | 27,7 | 0,86 | −3.314 € (Konto leer) | durchgefallen |
| Bollinger + RSI, Bitcoin/Ether | Stunden | 1.727 | 11,7 | 0,69 | −3.474 € (Konto leer) | durchgefallen |

## Einzelheiten

**ICT Silver Bullet** (TTrades, JadeCap). 1.298 Trades, 46 % Treffer bei 2 R Ziel. Hälften 0,92 und 1,10, 2026 1,19.
S&P 500 1,11, Nasdaq 0,90. Long und Short je 1,01. Mit 1,5-fachen Kosten 0,97. Zufallsvergleich 85 % geschlagen, z 1,15.
Vor 2024 als Auskunft 4.082 Trades, Gewinnfaktor 0,88. Nach Kosten bleibt nichts übrig.

**NR7-Ausbruch** (Toby Crabel). 1.018 Trades, 42 % Treffer. Gut auf DAX 1,39, USD/JPY 1,35, Gold 1,25, schlecht auf
S&P 500 0,65 und AUD/USD 0,56. Das ist die Streuung, die Zufall auch liefert (77 % geschlagen, z 0,71). Vor 2024 0,86.

**Supertrend 4 Std.** (Trade Pro, TradingLab). 379 Trades, 37 % Treffer. Hälften 1,06 und 0,75, 2026 nur 0,55
(110 Trades). Gold 2,09 (47 Trades), sonst meist unter 1. Vor 2024 0,95. Zufall 33 % geschlagen.

**Bollinger + RSI** (TradingLab, 1,9 Mio. Aufrufe). Devisen, Gold, Indizes 4.085 Trades, 28 % Treffer, 0,86. Vor 2024
12.809 Trades, 0,76. Krypto 1.727 Trades, 23 % Treffer, 0,69, schlechter als 97 % der Zufallsläufe. Nach einem
starken Ausschlag läuft der Kurs öfter weiter, als er zur Mitte zurückkommt, und die Kosten treffen jeden der vielen
kleinen Trades.

## Probelauf und Entwicklung (vor dem Siegel)

8 Saaten auf erfundenen Märkten ohne Vorteil, 40 Rechnungen: keine bestand, eine wurde Kandidat (Supertrend, z 2,93).
Entwicklung März 2021 bis Dezember 2023: supertrend 1,15, bollinger 0,83, bollinger_krypto 0,76, nr7 0,95,
silver_bullet 1,07. Der Öl-Lagerbericht fiel vor dem Siegel weg, weil die Öl-Kurse 2024 und 2025 fehlen.

## Was das heißt

- Auch die ganz anderen Arten von YouTube-Strategien haben nach Kosten keinen Vorteil. Indikator-Kanäle („100 Mal
  getestet") zeigen meist Treffer ohne Spread und ohne Übernachtgebühr.
- Das Bild bleibt wie in allen Runden: kurze Trades verlieren nach Kosten, was hält, kauft Rückgänge auf US-Indizes.
- Keine Nachbesserung: kein anderes Fenster, keine andere Schwelle, keine Auswahl der guten Märkte im Nachhinein.

## Ideen-Vorrat (nicht gerechnet)

- Supertrend nur auf Gold (2,09) oder NR7 nur auf DAX, USD/JPY und Gold wäre eine Auswahl nach dem Blick auf das
  Ergebnis und darf nicht neu „bestehen".
- Öl-Lagerbericht: erst mit Öl-Kursen für 2024 und 2025 rechenbar.
- Optionsverfall-Woche und Feiertage auf US-Indizes: unter 100 Trades, höchstens als Filter für den laufenden
  Rücksetzer, mit eigener Regeldatei.
