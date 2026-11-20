# Ergebnis der großen Runde vom 19.11.2026, Durchgang 1

Keine der dreizehn Regeln besteht. Zwei sind Kandidaten, das heißt alle Hürden geschafft, aber kein Beleg: der Tag nach
einem VIX-Sprung auf US500 und US100 (Gewinnfaktor 1,93, z 2,17) und das Vorhersage-Modell auf fünf Indizes
(Gewinnfaktor 1,21, z 1,89). Kirons Geduld-Idee (viele kleine Gewinne, Verlierer halten) hat 2024 bis 2026 ein Plus
mit 79 bis 96 % Treffern, aber sie schlägt zufällige Tage nicht und die erste Hälfte liegt bei null. Das Plus kommt
vom steigenden Markt, nicht vom Einstieg. Es geht nichts live, an keinem Bot ändert sich etwas.

Regeln: `suche/VORAB_grosse_runde.yaml`, Siegel `32340eceb9f4b4917836360375b52d13e8b6306f8283aec417863f24cab6c116`, im Protokoll am 19.11.2026 17:40 UTC, committet und
gepusht vor dem Rechnen, einmal gerechnet um 17:42 UTC. Programm `suche/grosse_runde.py`, Rechnung von
`suche/rueckblick.py`. Hauptfenster Januar 2024 bis Oktober 2026, nach Spread, Rutschen und Übernachtgebühr.
Gewinnfaktor heißt Gewinne geteilt durch Verluste. Holm zählt mit 26 Varianten über beide Durchgänge.

## Alle dreizehn

Euro heißt: Summe mit 10 € Risiko je Trade (10 € sind weg, wenn der Stop greift).

| Regel | Märkte | Haltedauer | Trades | je Woche | Treffer | Gewinnfaktor | 1,5-fache Kosten | Hälften | 2026 | Zufall geschlagen | z | Euro | Urteil |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Tag nach einem VIX-Sprung (`vix_sprung_us`) | US500, US100 | 1 Tag | 136 | 0,9 | 62 % | 1,93 | 1,92 | 1,26 und 3,36 | 2,45 | 98,8 % | 2,17 | +92 € | Kandidat: Holm und z fehlen |
| Geduld mit sinkendem Ziel in Stufen (`geduld_us_stufen`) | US500, US100 | Stunden bis 10 Tage | 463 | 3,1 | 79 % | 1,53 | 1,51 | 0,97 und 2,99 | 2,01 | 78,5 % | 0,84 | +98 € | durchgefallen: Hälften, Zufall 95 % |
| Geduld praktisch ohne Stop (10 ATR) (`geduld_us_fern`) | US500, US100 | Stunden bis 30 Tage | 337 | 2,3 | 96 % | 1,40 | 1,38 | 0,85 und 2,64 | 1,09 | 33,1 % | -0,30 | +20 € | durchgefallen: Hälften, Zufall 95 % |
| Geduld mit kleinem Ziel, Notstop 3 ATR (`geduld_us_ziel`) | US500, US100 | Stunden bis 10 Tage | 419 | 2,8 | 93 % | 1,34 | 1,32 | 1,00 und 1,87 | 1,11 | 72,2 % | 0,69 | +73 € | durchgefallen: Hälften, Zufall 95 % |
| Vorhersage-Modell Indizes (`modell_indizes`) | 5 Indizes | 1 Tag | 1.874 | 12,7 | 55 % | 1,21 | 1,16 | 1,09 und 1,34 | 1,27 | 97,5 % | 1,89 | +457 € | Kandidat: Holm und z fehlen |
| Fed-Zyklus, Wochen 2, 4, 6 (`fed_zyklus_us`) | US500, US100 | 1 Tag | 552 | 3,7 | 58 % | 1,14 | 1,12 | 0,93 und 1,48 | 1,29 | 60,3 % | 0,25 | +58 € | durchgefallen: Gewinnfaktor, Hälften, Zufall 95 % |
| Umschichtung zum Monatsende (`umschichtung_us`) | US500, US100 | 1 Tag | 274 | 1,9 | 52 % | 1,11 | 1,10 | 1,21 und 1,03 | 0,75 | 75,4 % | 0,65 | +23 € | durchgefallen: Gewinnfaktor, 2026, Zufall 95 % |
| Zahlentage (Inflation, Arbeitsmarkt) (`zahlentag_us`) | US500, US100 | 1 Tag | 130 | 0,9 | 55 % | 1,01 | 1,00 | 1,13 und 0,88 | 0,68 | 39,9 % | -0,25 | +2 € | durchgefallen: Gewinnfaktor, Hälften, 2026, Zufall 95 % |
| Zins-Schwung USD/JPY (`zins_schwung_usdjpy`) | USD/JPY | 1 Tag | 246 | 1,7 | 49 % | 0,94 | 0,87 | 0,94 und 0,94 | 0,75 | 63,4 % | 0,34 | -25 € | durchgefallen: Gewinnfaktor, 1,5-fache Kosten, Hälften, 2026, Zufall 95 % |
| Vormittag sagt Nachmittag in Tokio (`tokio_nachmittag`) | Nikkei | 2,5 Std. | 461 | 3,1 | 45 % | 0,83 | 0,78 | 0,88 und 0,80 | 0,97 | 31,8 % | -0,49 | -89 € | durchgefallen: Gewinnfaktor, 1,5-fache Kosten, Hälften, 2026, Zufall 95 % |
| Finanzierungssatz als Gegenzeichen (`funding_krypto`) | Bitcoin, Ether | 24 Std. | 619 | 4,2 | 44 % | 0,67 | 0,64 | 0,72 und 0,61 | 0,64 | 2,3 % | -2,09 | -311 € | durchgefallen: Gewinnfaktor, 1,5-fache Kosten, Hälften, 2026, Zufall 95 % |
| Realzins und Gold (`realzins_gold`) | Gold | 1 Tag | 184 | 1,2 | 41 % | 0,64 | 0,60 | 0,50 und 1,08 | 1,05 | 8,8 % | -1,38 | -138 € | durchgefallen: Gewinnfaktor, 1,5-fache Kosten, Hälften, Zufall 95 % |
| Vorhersage-Modell Devisen (`modell_devisen`) | 7 Dollar-Paare | 1 Tag | 1.158 | 7,8 | 43 % | 0,57 | 0,40 | 0,52 und 0,62 | 0,70 | 59,3 % | 0,24 | -818 € | durchgefallen: Gewinnfaktor, 1,5-fache Kosten, Hälften, 2026, Zufall 95 % |

## Die zwei Kandidaten

**Tag nach einem VIX-Sprung.** Schließt der VIX mindestens 10 % über dem Vortag, wird US500 und US100 für einen
Handelstag gekauft. 136 Trades, 62 % Treffer, Gewinnfaktor 1,93, US500 1,76, US100 2,13, 2026 2,45.
Ohne die 5 besten Trades 1,57. Zufallsvergleich 98,8 % geschlagen, z 2,17 (nötig 3 und jede der 670
Verschiebungen). Vor 2024 als Auskunft 388 Trades mit Gewinnfaktor 1,13, also deutlich schwächer. Der Haken:
Nur 0,9 Trades je Woche, und es sind oft dieselben Tage, an denen die Rücksetzer-Bots schon im Markt sind.

**Vorhersage-Modell Indizes.** 1.874 Trades, 55 % Treffer, Gewinnfaktor 1,21, mit 1,5-fachen Kosten 1,16.
Je Markt: US500 1,21, US100 1,31, DAX 1,04, FTSE 1,49, Nikkei 1,13. Das Modell kauft fast nur (1.840 Käufe,
34 Verkäufe). Zufallsvergleich 97,5 % geschlagen, z 1,89. Vor 2024 als Auskunft 3.441 Trades mit Gewinnfaktor 0,94.
Der Haken: Es ist im Kern "an etwa der Hälfte der Tage kaufen" in einem Markt, der 2024 bis 2026 stieg. In den
Jahren davor verlor dieselbe Bauart. Das ist ein schwacher Kandidat.

## Kirons Geduld-Idee

Einstieg nach einem kurzen Rücksetzer auf der Stundenkerze, nur Long, nur im Aufwärtstrend, Ziel 0,25 Tages-ATR.
Die drei Fassungen unterscheiden sich nur darin, was mit Verlierern geschieht. Die Euro-Zahlen sind so gerechnet,
dass ein gewöhnlicher Gewinn 3 € bringt.

| Fassung | Trades | Treffer | Gewinnfaktor | 1. Hälfte | Summe | ein Notstop kostet | tiefstes Tal | längster Trade | Zufall geschlagen | vor 2024 |
|---|---|---|---|---|---|---|---|---|---|---|
| Notstop 3 ATR, höchstens 10 Tage | 419 | 93 % | 1,34 | 1,00 | +294 € | 43 € | -175 € | 15 Tage | 72,2 % | 0,89 |
| Notstop 10 ATR, höchstens 30 Tage | 337 | 96 % | 1,40 | 0,85 | +278 € | 146 € | -289 € | 45 Tage | 33,1 % | 1,10 |
| Ziel sinkt auf Einstand, dann auf kleinen Verlust | 463 | 79 % | 1,53 | 0,97 | +379 € | 40 € | -202 € | 14 Tage | 78,5 % | 0,78 |

Was das heißt: Die Trefferquote ist hoch, weil das Ziel nah und der Stop weit ist. Auf erfundenen Märkten ohne
jeden Vorteil hatten dieselben Regeln im Probelauf auch 89 bis 91 % Treffer. Ein Notstop frisst 13 bis 45 Gewinne.
Verschiebt man alle Einstiege auf zufällige andere Tage, kommt etwa gleich viel heraus (nur 33 bis 79 % der
Verschiebungen geschlagen, nötig sind 95 %). Vor 2024 lag der Gewinnfaktor bei 0,78 bis 1,10. Halten von Verlierern
macht also aus keinem Einstieg einen Vorteil. Es verschiebt nur, wann der Verlust kommt.

## Die anderen acht

- **Umschichtung zum Monatsende** (`umschichtung_us`): 274 Trades, Gewinnfaktor 1,11. 2026 nur 0,75, ohne die 5 besten Trades 0,98.
- **Fed-Zyklus, Wochen 2, 4, 6** (`fed_zyklus_us`): 552 Trades, Gewinnfaktor 1,14. Erste Hälfte 0,93, zufällige Tage sind gleich gut (60 % geschlagen).
- **Zahlentage (Inflation, Arbeitsmarkt)** (`zahlentag_us`): 130 Trades, Gewinnfaktor 1,01. Kein Unterschied zu gewöhnlichen Tagen mehr (2026 0,68).
- **Finanzierungssatz als Gegenzeichen** (`funding_krypto`): 619 Trades, Gewinnfaktor 0,67. Verliert klar, 2,3 % der Verschiebungen geschlagen. Umgedreht bliebe nach Kosten etwa null (Kosten rund 15 R von 31 R Verlust).
- **Vorhersage-Modell Devisen** (`modell_devisen`): 1.158 Trades, Gewinnfaktor 0,57. Verliert vor allem an den Kosten (mit 1,5-fachen Kosten 0,40).
- **Vormittag sagt Nachmittag in Tokio** (`tokio_nachmittag`): 461 Trades, Gewinnfaktor 0,83. Kein Schwung über die Mittagspause, beide Richtungen verlieren.
- **Zins-Schwung USD/JPY** (`zins_schwung_usdjpy`): 246 Trades, Gewinnfaktor 0,94. Der Kurs läuft der Rendite nicht nach.
- **Realzins und Gold** (`realzins_gold`): 184 Trades, Gewinnfaktor 0,64. Gold stieg 2024 bis 2026 auch bei steigendem Realzins, die Verkäufe verloren (0,51).

## Was daraus folgt

- Bestanden hat nichts. Kein Bot ändert sich, nichts geht live.
- Die zwei Kandidaten können in Durchgang 2 mit je einer logischen Änderung noch einmal geprüft werden. Was erst nach
  einer Änderung besteht, zählt höchstens als Kandidat.
- Die elf durchgefallenen Regeln stehen im Archiv `suche/VERWORFEN.md`.
- Alle Trades: `suche/ergebnis_grosse_runde_trades.csv.gz`, alle Zahlen: `suche/ergebnis_grosse_runde.json`.
