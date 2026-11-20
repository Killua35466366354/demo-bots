# Ergebnis Spiegel der Vorhersage-Scalper vom 20.11.2026

Keiner der acht Spiegel besteht, und keiner ist Kandidat. Alle acht liegen unter Gewinnfaktor 1. Der beste Spiegel
(Modell mit Bollinger, Stop 0,5 ATR) hätte auf 1.000 € mit 10 € Risiko je Trade von Januar 2024 bis Oktober 2026 rund
-1.385 € gebracht, also mehr als das ganze Konto verloren. Auch die Spiegel der Verlierer verlieren. Es geht nichts live,
an keinem Bot ändert sich etwas.

Regeln: `suche/VORAB_vorhersage_spiegel.yaml`, Siegel `0d11c1a6559c95170ab3c1adda64298a3e0788ec2bc43db46d0869185258b932`,
im Protokoll am 20.11.2026 19:40 UTC, committet und gepusht um 19:41 UTC vor dem Rechnen, einmal gerechnet um
19:42 UTC. Alles, was dort nicht steht, kommt unverändert aus der versiegelten Vorlage `suche/VORAB_vorhersage_scalp.yaml`
(Ergebnis `suche/ergebnis_vorhersage_scalp.md`). Programm `suche/vorhersage_spiegel.py`. Hauptfenster Januar 2024 bis
Oktober 2026, nach Spread und Rutschen (Capital.com-Spread je Viertelstunde). Gewinnfaktor heißt Gewinne geteilt durch
Verluste. Holm über acht. Weil die Spiegel erst nach dem Ergebnis der Vorlage feststanden, hätte einer höchstens
Kandidat werden können.

Bild: `/mnt/project-files/vorhersage-scalp-2026-11-20/spiegel.png` (Projektordner, gebaut mit `bild_spiegel.py` daneben).

## Kirons Idee und wie sie gerechnet wurde

Kirons Wunsch vom 20.11.2026 19:08 UTC: die profitablen und die ganz falschen Fassungen nicht einfach umdrehen, sondern
logisch spiegeln. Aus Long wird Short und aus Short wird Long, aus dem Take Profit wird der Stop Loss und aus dem Stop
Loss der Take Profit.

- **Welche Fassungen.** Ob ein einzelner Trade gewinnt, weiß man erst hinterher. Darum wurden ganze Regeln gespiegelt,
  und zwar alle acht: die vier mit Plus und die vier mit Minus, auch die zwei Kontrollen ohne Vorhersage.
- **Spiegeln.** Gleicher Tag, gleiche Marken, gleiche Zeiten. Wo die Vorlage mit einer Kauf-Limit-Order unter dem Kurs
  wartete, liegt jetzt eine Verkaufs-Stop-Order (sie verkauft, wenn der Kurs auf die Marke fällt). Der Stop liegt im
  Abstand des alten Ziels (0,2 oder 0,5 ATR), das Ziel am alten Stop (1,25 ATR vom Kurs um 18:00 New York bei den
  3 Stufen, 0,75 ATR beim Bollinger-Band). ATR ist die mittlere Tagesspanne der letzten 14 Tage.
- **Tagesregeln gespiegelt.** Nach dem Ziel (dem alten Stop) ist der Tag vorbei, nach einem Stop (dem alten Ziel) liegt
  die Stufe wieder bereit, höchstens 6 Einstiege je Markt und Tag, alles schließt vor 15:55 New York.
- **Zufallsvergleich.** Bei den sechs mit Vorhersage wird die Vorhersage um k Tage verschoben (669 Läufe). Bei den zwei
  ohne Vorhersage (jeden Tag verkaufen) wird jeden Tag die Richtung ausgelost (669 Münzwurf-Läufe).
- **Gegenprobe ohne Kosten.** Vor dem Siegel, nur an US500-Kursen bis Ende 2023: 98 % der Spiegel-Trades sind genau das
  Gegenteil eines Trades der Vorlage. Das Programm spiegelt also wirklich.

## Alle acht

Euro heißt Summe mit 10 € Risiko je Trade auf 1.000 € (10 € sind weg, wenn der Stop greift).

| Spiegel von | Trades | je Woche | Treffer | Gewinnfaktor | 1,5-fache Kosten | Hälften | 2026 | Zufall geschlagen | Euro Spiegel | Euro Vorlage | Urteil |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Modell, 3 Stufen, Ziel 0,5 ATR (`spiegel_modell_leiter_gross`) | 2.492 | 16,9 | 41 % | 0,84 | 0,82 | 0,86 und 0,82 | 0,81 | 3,4 % | -1.765 € | +313 € | durchgefallen |
| Modell, Bollinger, Ziel 0,5 ATR (`spiegel_modell_band_gross`) | 1.817 | 12,3 | 41 % | 0,84 | 0,81 | 0,79 und 0,90 | 0,97 | 10,2 % | -1.385 € | +312 € | durchgefallen |
| VIX-Sprung, 3 Stufen, Ziel 0,2 ATR (`spiegel_vix_leiter_klein`) | 860 | 5,8 | 20 % | 0,66 | 0,63 | 0,64 und 0,71 | 0,65 | 1,0 % | -2.404 € | +238 € | durchgefallen |
| Modell, Bollinger, Ziel 0,2 ATR (`spiegel_modell_band_klein`) | 2.741 | 18,6 | 25 % | 0,81 | 0,77 | 0,78 und 0,85 | 0,87 | 9,6 % | -3.778 € | +68 € | durchgefallen |
| Modell, 3 Stufen, Ziel 0,2 ATR (`spiegel_modell_leiter_klein`) | 3.575 | 24,2 | 27 % | 0,84 | 0,79 | 0,87 und 0,82 | 0,79 | 5,7 % | -4.126 € | -107 € | durchgefallen |
| Tagestrend, 3 Stufen, Ziel 0,2 ATR (`spiegel_trend_leiter_klein`) | 6.209 | 42,1 | 30 % | 0,95 | 0,88 | 0,92 und 0,97 | 0,95 | 60,2 % | -2.323 € | -1.587 € | durchgefallen |
| ohne Vorhersage, 3 Stufen (`spiegel_immer_leiter_klein`) | 7.009 | 47,5 | 28 % | 0,91 | 0,85 | 0,89 und 0,93 | 0,86 | 0,3 % | -4.528 € | -1.302 € | durchgefallen |
| ohne Vorhersage, Bollinger (`spiegel_immer_band_klein`) | 5.329 | 36,1 | 26 % | 0,86 | 0,81 | 0,80 und 0,92 | 0,90 | 1,9 % | -5.539 € | -525 € | durchgefallen |

Vor 2024 (nur Auskunft) lag jeder Spiegel ebenfalls unter 1 (0,68 bis 0,92).

## Was das heißt

- **Die Spiegel der Gewinner verlieren, wie erwartet.** Die Vorhersage hilft ein wenig in ihre Richtung. Wer gegen sie
  handelt, verliert diesen kleinen Vorteil und zahlt dazu die Kosten.
- **Die Spiegel der Verlierer lagen vor den Kosten im Plus, aber nur zwei.** Grob geschätzt aus der Rechnung mit
  1,5-fachen Kosten hätte der Spiegel des Tagestrends vor den Kosten etwa +4.000 € gebracht und der Spiegel der
  3 Stufen ohne Vorhersage etwa +2.700 €. Spread und Rutschen kosteten aber jeweils rund 6.400 und 7.200 €. Nach den
  Kosten bleiben -2.323 € und -4.528 €.
- **Warum der Spiegel mehr verliert als die Vorlage.** Aus dem kleinen Ziel wird ein kleiner Stop. Mit 10 € Risiko je
  Trade ist jeder Trade darum 1,5- bis 5-mal so groß wie in der Vorlage, und der Spread kostet entsprechend mehr Euro.
  Die Spiegel der Verlierer handeln dazu 36 bis 48 Trades pro Woche. Der Spread ist bei jedem Trade fällig, ganz egal in welche Richtung.
- **Niedrige Trefferquote.** Mit kleinem Stop und großem Ziel trifft der Spiegel nur 20 bis 41 % der Trades.
- **Archiv bestätigt.** Wie bei Turtle Soup gespiegelt (Gewinnfaktor 0,25 auf 0,19) hilft das Tauschen von Ziel und
  Stop nicht, wenn die Kosten groß gegen die Bewegung sind.

## Mehr Hebel (nur Auskunft)

Dieselben Trades, jeder Trade riskiert einen festen Anteil des Kontos (Zinseszins), Start 1.000 €. Schon mit 1 % je
Trade fällt bei fünf der acht Spiegel das Konto unter 10 €. Die drei anderen enden bei 208 € (Modell mit Bollinger,
Ziel 0,5 ATR), 107 € (Modell mit 3 Stufen, Ziel 0,5 ATR) und 56 € (VIX-Sprung). Mit 2 % je Trade bleiben höchstens
30 € übrig, sieben der acht sind pleite.

## Was daraus folgt

- Bestanden hat nichts. Kein Bot ändert sich, nichts geht live.
- Die acht Spiegel stehen im Archiv (`suche/VERWORFEN.md`), dazu die Lehre "Ziel und Stop tauschen".
- Nicht wiederholen: weder Umdrehen noch Spiegeln dieser Scalper auf den fünf Indizes.
- Alle Trades: `suche/ergebnis_vorhersage_spiegel_trades.csv.gz`, alle Zahlen: `suche/ergebnis_vorhersage_spiegel.json`.
