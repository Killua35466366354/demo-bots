# Ideen und Strategien im Demo-Labor

Kirons Wunsch vom 05.11.2026, 10:17 UTC: Das öffentliche Repo testet alle Demo-Bots und Strategien. Was profitabel ist,
allein oder mehrere zusammen, kommt später ins private Repo und mit echtem Geld auf ein Konto. Alte Vorschläge von Kiron
und neue Ideen werden hier gesammelt, damit nichts verloren geht und nichts doppelt getestet wird.

So wird die Liste gepflegt:

- Jede neue Idee kommt unter "Offene Ideen". Gerechnet wird erst, wenn die Regel vorab in einer `suche/VORAB_*.yaml`
  steht und ihre Prüfsumme im Protokoll `journal/strategie-suche-protokoll.md`.
- Große Rechnungen laufen einmal als Workflow in diesem Repo oder lokal, nie täglich und nie als lange Claude-Sitzung.
- Das Ergebnis kommt in die Tabelle, auch wenn die Idee durchfällt. Gleiche Einträge in maschinenlesbarer Form stehen in
  den Projektdateien: `demo-check/ideen.jsonl` (alle Strategien) und `gold-bot/lernjournal/ideen.jsonl` (Gold).
- Kein Bot ändert seine Regeln selbst. Änderungen nur per PR, den Kiron merged.

Stand: 05.11.2026.

## 1. Was gerade live auf den Demokonten läuft

| Strategie | Konto | Gruppe | Bewertung 2025-2026 (Gewinnfaktor, Euro mit 1.000 € bei 1 %) |
|---|---|---|---|
| Vortag EUR/USD | Account 4 | behalten | 1,67, +426 € |
| Vortag GBP/USD | "Vortag USDJPY" | behalten | 1,22, +165 € |
| Trend-Rücksetzer US500 | "US500" (Top 3 auf einem Konto) | behalten | 5,82, +55 € |
| Nasdaq Noise Long | "US500" (Top 3) | behalten | 3,54, +23 € |
| Trend-Rücksetzer US100 | "US500" (Top 3) | behalten | 1,91, +23 € |
| Gold C/B mit 1-ATR-Stop | Hauptkonto | verbessern | 1,17, +298 € (2026 allein 0,95) |
| Gold-Bot 2.0 | kein Konto, nur Schatten | | |
| TikTok-Box (stream_box), box_175, gross_klein_3, große Box (gross_box_kerze) und Gesamt-Linie alle_sieben | kein Konto, nur Schatten (`gold/tiktok_schatten.py`) | Schatten | alle ohne bestandenen Test, stream_box 11/2024-10/2026 0,96, box_175 (genauerer Nachbau, Faktor 1,75) 0,96, gross_klein_3 1,41 aber erst nach dem Ansehen gewählt, gross_box_kerze 1,21 (knapp durchgefallen, Kontrolle 2022-2024 0,96), alle_sieben (alle sieben Boxen zugleich, gross_box, box_1h und box_laufen nur als Teile) 1,03; Urteil nach 40 Schatten-Trades, bei alle_sieben frühestens nach 4 Wochen und 200 Trades (portfolio-manager `suche/VORAB_runde12b.yaml` bis `VORAB_runde12e.yaml`) |
| Brent-Öl | Account 1 | Labor | 1,49, +289 € (2025 allein -177 €) |
| Trend-Rücksetzer Dow | Account 5 | Labor | 1,48, +19 € |
| London-Stunde GBP/USD | Account 6 | Labor | 1,45, +59 € |
| Noise-Band USD/JPY | Account 7 | Labor | 1,39, +49 € |
| Vortag GBP/JPY | Account 3 | behalten | 1,45, +190 € (Test vom 05.11.2026, 2026 allein +0,5 €) |
| Vortag EUR/USD mit 1 x ATR | Account 2 | Mess-Bot | kein eigener Test: misst gegen Vortag EUR/USD, ob der breitere Stop das Rutschen besser verkraftet |
| Gold nur Long (Teil C) | Hauptkonto, nur gezählt | Mess-Zeile | die C-Trades des Gold-Bots, Urteil mit dem Gold-Bot Ende Januar 2027 |

Labor heißt: Vorwärtstest auf sonst leeren Demokonten nach Kirons Entscheidung vom 05.11.2026
(`suche/VORAB_labor.yaml`), getrennt vom Kern, nicht in der Kombi. Die Konten bekommen sie beim ersten Lauf nach dem
Merge. Account 3 bekam am 05.11. Vortag GBP/JPY, Account 2 bekommt der Mess-Bot (`suche/VORAB_messbots.yaml`, Kirons
Ja vom 05.11.2026 17:07 UTC). Für alle gilt seit 05.11. zusätzlich eine feste Frist von 6 Monaten
(`suche/VORAB_frist.yaml`), für die Vortag-Bots die Rutsch-Regel (`suche/VORAB_rutschen.yaml`). Der Vergleich aller
Bots steht nach jedem Lauf in `journal/vergleich.md`.

## 2. Kirons Vorschläge und was daraus wurde

### Gold

| Vorschlag | Stand | Quelle |
|---|---|---|
| Stop bei 1 x ATR | live seit 03.11.2026 | Gold-Lernjournal Idee 1 |
| Länger halten, Hebel/CFD, Markt- und News-Checker, Confluence-Stop, tägliches Selbstlernen | gerechnet bzw. umgesetzt | Gold-Lernjournal |
| Bei +50 raus, Teilgewinn, Break-even, weiter Stop mit Geduld, Nachkauf | durchgefallen | Gold-Lernjournal |
| Phasen, Wende, Megatrend-Schalter, immer im Markt (Flip) und umgekehrt, Verlierer umdrehen, Halten mit Take-Profit | durchgefallen | Gold-Lernjournal bis Idee 62, PR #156 |
| Tagesrichtung aus Vorhersagen (Welt-Lagebild) | durchgefallen, 0 von 6 | PR #140 |
| Signal-Box der TikTok-Live-Streams und TradingTop-Videos nachbauen, nur die letzten 2 Jahre testen, Vorhersage live mitlaufen lassen | Runde 12 und 12b durchgefallen, läuft als Schatten seit dem Merge | portfolio-manager Runde 12/12b, PR #196 |
| Stream-Box mit dem verbessern, was Fotos und Videos nutzen (Faktor 1,75, Rest laufen lassen, 4-Std.-Trend, nur London/New York, 1 Std., Kombi, FVG-Rücklauf, Docht-Kerze am Level) | Runde 12c, alle 8 durchgefallen (beste box_1h 1,13), box_175 läuft im Schatten mit | portfolio-manager Runde 12c, PR #199 |
| Große Box aus box_175, gross_klein_3 und Box auf 1 Std. (1 Std. und 4-Std.-Bruch gleich, Einstiege auf 15 Min., halten bis zur neuen Box, starke Signalkerze) | Runde 12d, PF 1,21 knapp durchgefallen, gross_box_kerze läuft im Schatten mit | portfolio-manager Runde 12d |
| Alle sieben Gold-Boxen zugleich in einem Konto (alle_sieben mit Hedging, alle_ein_konto ohne Gegenrichtung) | Runde 12e, alle_sieben PF 1,03, alle_ein_konto 1,16 (robust 1,11, Kontrolle 2022-2024 0,94), beide durchgefallen, alle_sieben läuft im Schatten mit | portfolio-manager `suche/VORAB_runde12e.yaml`, `suche/PROTOKOLL.md` Runde 12e |
| Kleines Konto mit 50 € und alle 2 Monate 50 € dazu | gerechnet | Gold-Thread |
| Sicherheitsschalter | nur vorwärts beobachtet | Gold-Lernjournal Idee 34 |
| Gold-Matrix: Einstiege, Stops und Ausstiege quer über 1 Min. bis 4 Std. (13 Einstiege mit runden Marken, Pivots, Dollar, Silber und Aktien, 5 Filter mit Tagestrend, Realzins und News-Richtung, 9 Stops, 24 Ausstiege, 54.375 Varianten) | keiner der 12 Finalisten bestanden, 3 Kandidaten (zählen als nicht bestanden). Am nächsten der 4-Std.-Ausbruch mit Tagestrend (GF 2,35, alle Verschiebungen geschlagen, z 2,93 statt 3,0). Schnelle Strategien auf 1 Min. und 5 Min. halten in der zweiten Hälfte nicht. Der 4-Std.-Ausbruch läuft seit Kirons Wahl vom 11.11.2026 19:59 UTC als Vorwärtstest auf Account 4 (`gold-ausbruch4h`, `suche/VORAB_gold_ausbruch4h_bot.yaml`, Urteil nach 40 Trades) | Kirons Wunsch vom 11.11.2026, `suche/VORAB_gold_matrix.yaml`, `suche/ergebnis_gold_matrix.md`, PR #42 |
| Verlierer umdrehen, zweiter Anlauf mit der Gold-Matrix: die 8 Varianten, die in der ersten Hälfte am deutlichsten schlechter waren als ihre Zwillinge, in der Gegenrichtung handeln (Kirons Frage vom 19.11.2026) | durchgefallen, 0 von 8. In der zweiten Hälfte verlieren 7 von 8 auch umgedreht, zusammen -677 R gegen -796 R der Originale. In der ersten Hälfte waren rund 97 % der Verluste aller 28.923 Verlierer Kosten, und es gab nicht mehr auffällige Verlierer (52), als der Zufall liefert (54). Nicht wiederholen | `suche/VORAB_gold_matrix_umkehr.yaml`, `suche/ergebnis_gold_matrix_umkehr.md` |

### Neue Strategien und Märkte

| Vorschlag | Stand | Quelle |
|---|---|---|
| Alle Märkte nach Gewinnfaktor über 1,2 bzw. 1,5 durchsuchen, die besten 5 auf Demo | gemacht (Runde 3); alle sechs Runde-3-Bots verloren 2025, abgelöst am 04.11.2026 | `VORAB_runde3.yaml`, `auswahl.yaml` |
| Aktien über Capital.com | 0 von 324 bestanden | Strategie-Suche |
| Scalping, 1 Minute, viele Trades | durchgefallen | Strategie-Suche |
| Ideen aus TikTok, YouTube, Reddit und dem Internet | London-Breakout und Asien-ORB durchgefallen (2015-2025 Gewinnfaktor 0,93 und 0,77); Trend-Rücksetzer US500 bestanden und live | `VORAB_us500.yaml`, `VORAB_langzeit.yaml` |
| Nur die letzten 3 bis 4 Wochen anschauen | kein dauerhafter Vorteil | Vier-Wochen-Check |
| Phasen-Erkenner, je Marktphase eine andere Strategie | durchgefallen | Runde 8 |
| Neue Familien für die 6 freien Konten | 11 Familien, keine bestanden | Runde 9 und 9b, PR #153 |
| Kreuzkurs-Wende | durchgefallen (2025-2026 Gewinnfaktor 0,58) | Runde 9c, PR #158 |
| Index über Nacht, Gotobi | verworfen | Runde 9, Nachanalyse |
| Opens aus dem TikTok von montyfinance (Tages-, Wochen-, Monats-, Quartals- und Jahres-Eröffnungskurs als Linien) als Filter für 7 laufende Bots und als eigene Rücklauf-Strategie auf 21 Märkten | durchgefallen, kein Filter und keine Regel bestanden; knapp: Vortag GBP/USD nur mit dem Wochen-Open PF 1,29 auf 1,42 (+3,9 R), aber Zufall p 0,125; Gold Rücklauf zum Tages-Open PF 1,37, Kontrolle 1,35, aber 2026 allein 0,85 | `VORAB_opens.yaml`, `ergebnis_opens.md`, Kirons Video vom 10.11.2026 |

### Risiko, Stops und Ablauf

| Vorschlag | Stand | Quelle |
|---|---|---|
| Stop am letzten Swing-Hoch/-Tief für alle Bots | gerechnet; Vortag EUR/USD und GBP/USD stoppen jetzt 0,5 x ATR | Protokoll 04.11.2026 12:55 und 13:20 UTC |
| Verlustgrenze 100 €, Pause nach Verlusten | kostet mehr als sie spart | Protokoll 04.11.2026 11:50 UTC |
| Keinen Trade verpassen, lieber zu spät einsteigen | live für Vortag (Nachholen bis 65 Minuten) | Protokoll 04.11.2026 14:00 UTC |
| Deutlich schlechtere Strategien automatisch wechseln | live (Prüfung nach 15 und 40 Trades) | `VORAB_wechsel.yaml` |

### Portfolio und Konten

| Vorschlag | Stand | Quelle |
|---|---|---|
| Alle Strategien gleich bewerten (2025-2026), dann wählen | gemacht | `VORAB_bewertung.yaml`, `journal/portfolio.json` |
| Nur die profitabelsten behalten, den Rest abschalten | gemacht am 04.11.2026 | `auswahl.yaml` |
| Die besten 3 auf einem Konto | live seit 04.11.2026 | `kombi.yaml` |
| Kombi-Konto je Monat, Woche und Tag ansehen | im Cockpit | Cockpit |
| Profite aller Demo-Bots abgleichen und bewerten | live ab diesem PR | `suche/vergleich.py`, `journal/vergleich.md` |
| Profitables zusammenführen und mit echtem Geld auf ein Konto | Regel vorab festgelegt, entscheiden wird Kiron | `VORAB_aufstieg_alle.yaml` (seit 18.11.2026, vorher `VORAB_aufstieg.yaml`) |
| Viele Strategien, die nicht gleichzeitig verlieren | **offen**, siehe N2 | |
| Gewinnquote 30/70 und ähnliche Verlustserien | teilweise: Pause nach Verlusten kostet mehr; Verlustserien gemeinsam siehe N2 | |
| Monatsinformationen für Trades | **offen**, siehe N5 | |

## 3. Offene Ideen

| Nr. | Idee | Warum | Kosten |
|---|---|---|---|
| N1 | Risiko in der Kombi verteilen: je Strategie nach Gewinnfaktor oder Schwankung statt überall 1 % | Mehr Gewinn bei gleichem Rückgang, ohne neue Strategie. Lernen auf 2025, prüfen auf 2026 | klein: vorhandene Trades der Bewertung |
| N2 | Gleichlauf der Kern-Strategien: verlieren sie in denselben Wochen und Monaten? | Kirons Streuungs-Idee. Wenn zwei immer zusammen verlieren, ist das Risiko der Kombi größer, als es aussieht | klein: vorhandene Trades der Bewertung |
| N3 | Vortag-Regel auf weiteren Währungspaaren | Mehr Trades im Monat bei gleichem Risiko je Trade | mittel; macht der Wochen-Check-Thread am Samstag |
| N4 | Vortag-Regel auf Indizes, Gold und Öl | Die Regel verdient auf EUR/USD und GBP/USD; vielleicht auch woanders. Lernen bis 2024, prüfen 2025-2026 | mittel: ein Workflow-Lauf |
| N5 | Monatswechsel bei Indizes: um den Monatswechsel long US500/US100 | Bekannter Kalender-Effekt bei Aktienindizes; das Monatsende bei Devisen (Runde 9) ist durchgefallen, bei Indizes noch nie gerechnet | mittel: ein Workflow-Lauf |
| N6 | Vorwärtstest der 4 abgeschalteten, aber bestandenen Strategien auf freien Konten (Brent, Dow-Rücksetzer, London GBP/USD, Noise USD/JPY) | Nur Demo-Geld; echte Trades zeigen, ob sie mehr als Zufall sind | **Kiron hat am 05.11.2026 Ja gesagt**, läuft als Labor |

## 4. Nächste Tests in dieser Reihenfolge

1. N3 am Samstag im Wochen-Check-Thread, damit nichts doppelt läuft.
2. N2 und N1 zusammen, in einer vorab festgelegten Datei, lokal auf den Trades der Bewertung.
3. N6 läuft seit Kirons Ja vom 05.11.2026 als Labor; Urteil nach 15/40 Trades wie bei allen.
4. N4 und N5 zusammen als nächste Runde, einmal als Workflow in diesem Repo.

## 5. So kommt eine Strategie zu echtem Geld

Seit dem 18.11.2026 steht die Regel vorab in `suche/VORAB_aufstieg_alle.yaml` (Kirons Wahl "2 Monate und 100
Trades"). Jeder Bot allein, die Kombi der Kern-Strategien und eine feste Gruppe aller Bots brauchen 100 Demo-Trades,
mindestens 61 Tage, in den letzten 61 Tagen eine Summe über 0, die neuere Hälfte der Trades nicht im Minus und
Gewinnfaktor mindestens 1,2 (die sechs Kern-Bots und ihre Kombi) oder 1,3 (alle anderen und die Gruppe). Vorher galt
`suche/VORAB_aufstieg.yaml` mit 40 Trades und Kombi 60. `journal/vergleich.md` zeigt nach jedem Lauf, wer reif ist.
Dann entscheidet Kiron, und echtes Geld gibt es nur über einen PR im privaten Repo.

Ehrlich: Auch so besteht ein Bot ohne Vorteil die Hürde mit Gewinnfaktor 1,3 noch in etwa einem von zehn Fällen. Beim
Tempo vom 18.11.2026 wäre Pine-Gold auf Account 5 im Januar 2027 so weit, die Kern-Bots als Kombi etwa im Sommer 2027.

## 6. Runde „Starker Rückblick“ (18.11.2026)

Kirons Wunsch: Strategien suchen, die im Rückblick stark sind, und sie danach live gegen den Rückblick prüfen.
Gerechnet wurden sechs vorab festgelegte Varianten (`suche/VORAB_rueckblick.yaml`): der 4-Std.-Ausbruch mit Tagestrend
(Gold-Kandidat) auf Silber, US-Indizes, DAX/FTSE/Nikkei und sieben Währungspaaren, dazu die Dienstag-Regel auf
Indizes. Ergebnis in `suche/ergebnis_rueckblick.md`: keine besteht, der 4-Std.-Ausbruch auf DAX, FTSE und Nikkei ist
Kandidat (nicht bestanden, kein Beleg), fünf sind durchgefallen.

Dort stehen auch:

- der Befund, dass die Vortag-Regel mit engem Stop auf Kerzen nicht fair zu rechnen ist (betrifft N4 und den Rückblick
  der laufenden Vortag-Bots),
- der Ideen-Vorrat R1 bis R9 aus der Recherche (Umschichtungs-Druck zum Monatsende, Nacht vor dem
  Arbeitsmarktbericht, Tag nach einem VIX-Sprung und weitere) mit Quelle und Hauptzweifel,
- ein Vorschlag, wie ein Live-Versuch Treue zum Rückblick und echten Vorteil getrennt prüft.

## 7. YouTube-Runde (19.11.2026)

Kirons Wunsch: große YouTube-Suche, alle möglichen Strategien testen und kombinieren, verschiedener werden. Gesucht
wurde mit 33 Suchen (403 Videos). Fast alles Beliebte war schon gerechnet (siehe oben). Neu gerechnet wurden vier
Regeln, vorab festgelegt in `suche/VORAB_youtube_runde.yaml`. Ergebnis in `suche/ergebnis_youtube_runde.md`: keine
besteht, kein Kandidat.

| Regel | Trades | Gewinnfaktor | Stand |
|---|---|---|---|
| Williams %R(2) auf US500/US100 (Quantified Strategies) | 77 | 2,66 | durchgefallen (unter 100 Trades, z 2,35). Meist dieselben Trades wie der Trend-Rücksetzer |
| 4-Std.-Ausbruch (Gold-Kandidat) auf Bitcoin/Ether | 319 | 1,23 | durchgefallen (2026 0,91, z 2,35), ohne die 5 besten 0,98 |
| CME-Lücke Bitcoin/Ether („schließt sich immer") | 160 | 0,77 | durchgefallen |
| Montagsbereich Bitcoin/Ether (Ausbruch) | 286 | 0,69 | durchgefallen |

Nicht neu rechnen: CME-Lücke und Montagsbereich auf Krypto. Williams %R und der Krypto-Ausbruch nur mit einer neuen
Regeldatei und Kirons Wahl, und nur als Vorwärtstest ohne Order.

## 8. Zweite YouTube-Runde (19.11.2026)

Kirons Wunsch: ganz andere Arten von Strategien und Videos. Gesucht wurde mit 24 neuen Suchen (369 Videos, 343 neu):
Indikator-Kanäle („100 Mal getestet"), Ruhe vor dem Ausbruch, Kalender, Öl-Bericht, Paare, Carry, Gitter, ICT und
Krypto-Rückkehr zum Mittel. Gerechnet wurden fünf Regeln, vorab festgelegt in `suche/VORAB_youtube_runde2.yaml`.
Ergebnis in `suche/ergebnis_youtube_runde2.md`: keine besteht, kein Kandidat.

| Regel | Trades | Gewinnfaktor | Stand |
|---|---|---|---|
| ICT Silver Bullet auf US100/US500 (TTrades) | 1.298 | 1,01 | durchgefallen, nach Kosten null |
| NR7-Ausbruch auf 11 Märkten (Crabel) | 1.018 | 0,97 | durchgefallen |
| Supertrend 4 Std. mit EMA 200 (Trade Pro) | 379 | 0,91 | durchgefallen, 2026 0,55 |
| Bollinger + RSI auf Stunden, Devisen/Gold/Indizes (TradingLab) | 4.085 | 0,86 | durchgefallen |
| Bollinger + RSI auf Stunden, Bitcoin/Ether | 1.727 | 0,69 | durchgefallen |

Nicht gerechnet: Öl-Lagerbericht (Öl-Kurse 2024 und 2025 fehlen), Optionsverfall und Feiertage (unter 100 Trades),
Gold zu Silber und Paare (zwei Beine), Carry (Zinsdaten je Tag), Gitter und Martingale (kein fester Stop). Ichimoku,
Heikin Ashi und MACD sind dieselbe Familie wie Supertrend.

## 9. Runde „Kirons Notizen“ (19.11.2026)

Kiron hat im Strategie-Katalog alle 110 Strategien bewertet und Notizen geschrieben. Seine Notizen zu den Karten 25 bis
39 wurden elf feste Fassungen, vorab festgelegt in `suche/VORAB_notizen_runde.yaml`. Ergebnis in
`suche/ergebnis_notizen_runde.md`: keine besteht, ein Kandidat.

| Fassung (Karte) | Trades | vorher | jetzt | Stand |
|---|---|---|---|---|
| 4-Std.-Ausbruch DAX/FTSE/Nikkei mit Ziel 1 R (34) | 393 | 1,24 | 1,30 | Kandidat (z 2,26, Holm fehlt), zum zweiten Mal in dieser Familie |
| Bollinger Krypto umgedreht, Stop 1,5 ATR, Ziel 2 R (29) | 1.150 | 0,69 | 1,07 | durchgefallen, schlägt den Zufall (z 3,09), verdient nach Kosten zu wenig |
| Bollinger Krypto gespiegelt (29) | 1.667 | 0,69 | 0,93 | durchgefallen |
| Montagsbereich Krypto mit Stufen-Stop (33) | 286 | 0,69 | 0,97 | durchgefallen |
| Montagsbereich Krypto mit Ziel 1 R (33) | 286 | 0,69 | 0,90 | durchgefallen |
| Supertrend S&P 500, Trade auf USD/JPY in Gegenrichtung (27) | 67 | 0,91 | 0,97 | durchgefallen, zu wenige Trades |
| Dienstag US500/US100 beide Seiten, Ziel 0,5 ATR (38) | 247 | 0,99 | 0,98 | durchgefallen |
| Dienstag DAX/FTSE/Nikkei mit Stufen-Stop (39) | 188 | 1,13 | 0,94 | durchgefallen |
| Silver Bullet ohne Ziel bis 16 Uhr (25) | 1.298 | 1,01 | 0,96 | durchgefallen |
| Bollinger Stunden gespiegelt (28) | 4.001 | 0,86 | 0,86 | durchgefallen |
| CME-Lücke mit halber Lücke als Ziel (32) | 160 | 0,77 | 0,61 | durchgefallen |

Nicht neu rechnen: alle elf auf denselben Kursen. Nur DAX und Nikkei oder nur Ether zu nehmen wäre Auswahl nach dem
Ergebnis. Der Kandidat nur vorwärts auf neuen Kerzen, mit eigener Regeldatei und Kirons Wahl. Alles, was je verworfen
wurde oder durchgefiel, steht mit Grund in `suche/VERWORFEN.md`.

Kirons Wahl vom 19.11.2026 11:08 UTC: Der Kandidat wird ohne Bot vorwärts gezählt (`suche/VORAB_notizen_vorwaerts.yaml`,
`python -m suche.notizen_vorwaerts zaehlen <Arbeit>`). Nur Einstiege ab 20.11.2026, Urteil bei 40 Trades, erwartet
etwa März 2027.

Kirons Wahl vom 19.11.2026 12:23 UTC: Der Kandidat handelt zusätzlich als Demo-Bot auf Account 7 (`suche/welt4h_bot.py`,
`suche/VORAB_welt_ausbruch4h_bot.yaml`). Dieselbe Regel, eigenes Urteil nach 40 Demo-Trades. Die Zählung ohne Bot
bleibt, wie sie ist.

## 10. Andere Ausstiege für laufende Bots (19.11.2026)

Kirons Notizen Nr. 9, 11 und 13 aus dem Strategie-Katalog, versiegelt in `suche/VORAB_ausstiege_kern.yaml`, Code
`suche/ausstiege_kern.py`, Ergebnis `suche/ergebnis_ausstiege_kern.md`. Gleiche Einstiege wie der Bot, nur der
Ausstieg ändert sich, gepaarter Test über alle Jahre mit Holm über 8 Varianten, dazu die Hürden ab 2025.

**Keine der 8 Varianten besteht, kein Bot ändert sich.** Stop auf Einstand ab +1 ATR und die Hälfte bei +1 ATR bringen
beim US100-Rücksetzer keinen Beleg (p 0,25 und 0,38). Beim Nasdaq Noise Long beendet der Stop auf Einstand gute Trades
zu früh, seit 2025 sinkt der Gewinnfaktor von 4,33 auf 3,33. Einziger Kandidat ist der DAX-Scalper mit Stop mal 0,75 und
Ziel mal 1,5 (607 Trades, Gewinnfaktor 1,26 auf 1,41, seit 2025 1,70 auf 1,84, p 0,013, Holm verlangt 0,006). Er ist
durchgefallen und wird kein Zwilling. Nr. 10 (Dow) ist nicht gerechnet, im Projekt liegen keine Dow-Kerzen.

## 11. Stop-Prüfung „Rettung“ (19.11.2026)

Kirons Frage vom 19.11.2026, ob die Stops den Verlust so klein wie möglich halten und ob man im Minus am Einstand oder
mit kleinstem Minus schnell rausgehen sollte. Versiegelt in `suche/VORAB_rettung_stops.yaml`, Code
`suche/rettung_stops.py`, Ergebnis `suche/ergebnis_rettung_stops.md`. Sechs Nicht-Gold-Bots (US500- und
US100-Rücksetzer, Nasdaq Noise-Band, Scalper Nasdaq und DAX, 4-Std.-Ausbruch DAX, FTSE, Nikkei), gleiche Einstiege wie
der Bot, gepaarter Test über alle Jahre mit Holm über 15 Fassungen, dazu das Hauptfenster 2024 bis 2026.

**Keine der 15 Fassungen besteht, es gibt keinen Kandidaten, kein Bot ändert sich.** Neu war der Ausstieg nach einem
Rücklauf ins Minus: War der Trade einen halben Stop-Abstand im Minus, liegt eine Limit-Order am Einstand oder bei einem
Viertel Stop-Abstand im Minus. Die Rettung macht einzelne Verluste kleiner, schneidet aber mehr spätere Gewinner ab, als
sie Verlierer rettet. Scalper Nasdaq im Hauptfenster von +50,3 R auf −20,6 R (208 Eingriffe, 117 davon wären Gewinner
geworden), Scalper DAX von +75,5 R auf +39,8 R. Rücksetzer und Noise-Band ohne Beleg (p 0,42 bis 0,78), 4-Std.-Ausbruch
leicht besser, aber p 0,08 und 0,10. Der halbe Stop ist bei beiden Scalpern und beim 4-Std.-Ausbruch schlechter.

Nicht gerechnet: die drei Vortag-Bots und der Mess-Bot (Stops von 2 bis 7 Pips, auf 5-Minuten-Kerzen nicht fair, gehört
zur Nachrechnung mit Minutenkerzen), Noise USD/JPY und Scalper Nikkei (kein Stop in der Regel), London GBP/USD
(Test-Programm im privaten Repo), Dow (keine Kerzen), Gold (rechnet der Gold-Thread).

## 12. Große Runde (19.11.2026)

Kirons große Recherche vom 19.11.2026: Ideen-Suchen in zehn Bereichen. Gerechnet wurde aus den ersten fünf
(Aktienindizes, Vorhersagen, Scalping, Devisen, Seltene Regeln, zusammen 244 Ideen, jede gesichtet). Die Listen liegen im
Projektordner `strategie-katalog/recherche-2026-11-19/`. Zwei Durchgänge mit je 13 Regeln, versiegelt in
`suche/VORAB_grosse_runde.yaml` und `suche/VORAB_grosse_runde2.yaml`, Code `suche/grosse_runde.py`, Ergebnisse
`suche/ergebnis_grosse_runde.md` und `suche/ergebnis_grosse_runde2.md`. Holm zählt mit 26 über beide Durchgänge.
Durchgang 2 wurde nach dem Ergebnis von Durchgang 1 zusammengestellt und konnte darum höchstens Kandidaten bringen.

**Keine der 26 Regeln besteht, es geht nichts live, kein Bot ändert sich.** Drei Kandidaten, davon zweimal dieselbe
Idee: das Vorhersage-Modell auf fünf Indizes in der strengeren Fassung (561 Trades, Gewinnfaktor 1,52, z 2,69, vor 2024
aber 0,97 und DAX 1,01), dasselbe Modell mit lockerer Schwelle (1.874 Trades, 1,21, z 1,89) und der Tag nach einem
VIX-Sprung auf US500 und US100 (136 Trades, 1,93, z 2,17). Die fünf Abwandlungen des VIX-Sprungs (zwei Tage halten,
Schwelle 7,5 %, DAX, FTSE und Nikkei, Yen-Paare, Geduld-Ausstieg) schlagen Zufallstage nicht (z 0,33 bis 1,50). Das
schwächt diesen Kandidaten.

Durchgefallen und nicht zu wiederholen: Kirons Geduld-Idee mit kleinem Ziel und weitem oder sinkendem Stop in vier
Fassungen (79 bis 96 % Treffer, aber nicht besser als Zufallstage), Fed-Zyklus in geraden Wochen, Umschichtung zum
Monatsende, Kauf an Zahlentagen, Zins-Schwung USD/JPY, Vormittag sagt Nachmittag in Tokio, Finanzierungssatz bei Krypto
als Gegenzeichen, Realzins und Gold, Vorhersage-Modell auf Devisen, Dark-Pool-Käufe (DIX), Hebel-Fonds in der letzten
halben Stunde, runde Marken bei Devisen, Bitcoin nach dem Fonds-Fenster.

Seltene Regeln mit Termin oder fester Eröffnung (Kirons Wunsch vom 19.11.2026, 20:58 Uhr): Tokio-Eröffnung nach einem
US-Schreck (Gewinnfaktor 0,72), Verfallstag-Morgen in New York (0,75), Verfalls-Abrechnung in Tokio und Frankfurt
(0,84). Alle drei sind schlechter als zufällige Tage. Eine Regel mit einem Termin im Monat kommt allein nie auf 100
Trades, darum liefen sie über mehrere Märkte. Die Hürde wurde nicht gesenkt.

Lehre für den Zufallsvergleich: Bei Regeln, die ein Schreck-Tag auslöst, und beim Fonds-Fenster ist die Verschiebung zu
freundlich (Probeläufe auf erfundenen Märkten im Kopf von `suche/VORAB_grosse_runde2.yaml`). Ein Kandidat aus dieser
Runde ist kein Beweis. Der ehrliche nächste Schritt ist Mitzählen ohne Order, und das entscheidet nur Kiron.

## 13. Runde „Kirons Trade-Notizen“ (20.11.2026)

Kiron hat im Trade-Katalog zwei gerechnete Regeln der großen Runde mit „Ändern“ bewertet und verlangt, die fünf
profitabelsten Regeln nach Märkten durchzusehen. Sechs neue Fassungen, versiegelt in `suche/VORAB_trade_notizen.yaml`,
Code `suche/grosse_runde.py` (Durchgang 3), Ergebnis `suche/ergebnis_trade_notizen.md`. Der Sache nach ist das ein
dritter Durchgang auf denselben Kursen, darum war das beste Urteil Kandidat. Holm zählt mit 32.

**Keine der sechs Fassungen besteht, es geht nichts live, kein Bot ändert sich.** Drei Kandidaten, alle dasselbe
Vorhersage-Modell auf fünf Indizes: mit mehr Merkmalen (andere Indizes vom Vortag, Termine, DIX, 1.724 Trades,
Gewinnfaktor 1,27, z 2,49, als einzige Fassung mehr Euro und höheres z als ihr Original), dieselbe strenger (601
Trades, 1,30, z 1,64, schlechter als das strengere Original) und mit lernender Markt-Auswahl (924 Trades, 1,33,
z 2,03, weniger Euro als das Original).

Durchgefallen und nicht zu wiederholen: die Geduld-Regel eine oder zwei Stundenkerzen später einsteigen (Gewinnfaktor
1,00 und 0,98, der Gewinn steckt in der ersten Stunde nach dem Signal) und die Geduld-Regel auf fünf statt zwei
Indizes (997 Trades, 1,28, aber nur 73 % der Zufallsläufe geschlagen, DAX und Nikkei bringen nichts).

Befunde: Die Verkäufe des Modells verlieren auch mit mehr Merkmalen (142 Verkäufe, Gewinnfaktor 0,73). Die lernende
Markt-Auswahl aus den zwei Jahren davor hat den schwachen DAX nicht erkannt und 2024 ganz ausgesetzt. Jeder Markt lag
in jeder der fünf besten Regeln im Plus, ein Streichen einzelner Märkte nach dem Ergebnis wurde nicht gerechnet.

Kirons Wahl vom 20.11.2026 11:53 UTC ("die paar stärksten zu erst", Schatten soll direkt Live-Demo sein): Die Fassung
`bollinger_umkehr_krypto_weit` (durchgefallen, Gewinnfaktor 1,07) handelt als Demo-Bot auf Account 3
(`suche/krypto_bollinger_bot.py`, `suche/VORAB_krypto_bollinger_bot.yaml`). Eigenes Urteil nach 40 Demo-Trades. Das
Schatten-Labor zählt sie unverändert weiter.

Kirons Wahl vom 20.11.2026 12:25 UTC ("Modell Indizes, jetzt bauen"): Die Fassung `modell_indizes` der großen Runde
(Kandidat, Gewinnfaktor 1,21, z 1,89, vor 2024 0,94) handelt als Demo-Bot auf Account 6
(`suche/modell_indizes_bot.py`, `suche/VORAB_modell_indizes_bot.yaml`). Die Gewichte je Jahr kommen aus dem Test
(`suche/modell_indizes_gewichte.json`), VIX und Renditen live von Cboe und vom US-Finanzministerium. Eigenes Urteil
nach 40 Demo-Trades, bei 12,7 Trades je Woche etwa Mitte Dezember 2026. Das Schatten-Labor zählt sie unverändert
weiter.

Kirons Wunsch vom 20.11.2026 12:26 UTC ("baue danach aber weiter aus"): Die Fassungen `vix_sprung_us` (Kandidat,
Gewinnfaktor 1,93, z 2,17, vor 2024 1,13) und `vix_sprung_welt` (durchgefallen, 1,41, vor 2024 0,85) handeln als ein
Demo-Bot auf Account 5 (`suche/vix_sprung_bot.py`, `suche/VORAB_vix_sprung_bot.yaml`). Den VIX holt er von Cboe. Alle
340 Trades des Tests liegen an nur 68 Tagen, 2024 verlor die Regel. Eigenes Urteil nach 40 Demo-Trades, das sind etwa
8 Sprung-Tage, also etwa Mitte März 2027. Das Schatten-Labor zählt beide Fassungen unverändert weiter.
