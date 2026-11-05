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

Frei: 6 Demokonten (Account 1, 2, 3, 5, 6, 7). Der Vergleich aller Bots steht nach jedem Lauf in
`journal/vergleich.md`.

## 2. Kirons Vorschläge und was daraus wurde

### Gold

| Vorschlag | Stand | Quelle |
|---|---|---|
| Stop bei 1 x ATR | live seit 03.11.2026 | Gold-Lernjournal Idee 1 |
| Länger halten, Hebel/CFD, Markt- und News-Checker, Confluence-Stop, tägliches Selbstlernen | gerechnet bzw. umgesetzt | Gold-Lernjournal |
| Bei +50 raus, Teilgewinn, Break-even, weiter Stop mit Geduld, Nachkauf | durchgefallen | Gold-Lernjournal |
| Phasen, Wende, Megatrend-Schalter, immer im Markt (Flip) und umgekehrt, Verlierer umdrehen, Halten mit Take-Profit | durchgefallen | Gold-Lernjournal bis Idee 62, PR #156 |
| Tagesrichtung aus Vorhersagen (Welt-Lagebild) | durchgefallen, 0 von 6 | PR #140 |
| Kleines Konto mit 50 € und alle 2 Monate 50 € dazu | gerechnet | Gold-Thread |
| Sicherheitsschalter | nur vorwärts beobachtet | Gold-Lernjournal Idee 34 |

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
| Profitables zusammenführen und mit echtem Geld auf ein Konto | Regel vorab festgelegt, entscheiden wird Kiron | `VORAB_aufstieg.yaml` |
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
| N6 | Vorwärtstest der 4 abgeschalteten, aber bestandenen Strategien auf freien Konten (Brent, Dow-Rücksetzer, London GBP/USD, Noise USD/JPY) | Nur Demo-Geld; echte Trades zeigen, ob sie mehr als Zufall sind | klein, braucht aber Kirons Ja |

## 4. Nächste Tests in dieser Reihenfolge

1. N3 am Samstag im Wochen-Check-Thread, damit nichts doppelt läuft.
2. N2 und N1 zusammen, in einer vorab festgelegten Datei, lokal auf den Trades der Bewertung.
3. N6, wenn Kiron Ja sagt.
4. N4 und N5 zusammen als nächste Runde, einmal als Workflow in diesem Repo.

## 5. So kommt eine Strategie zu echtem Geld

Die Regel steht vorab in `suche/VORAB_aufstieg.yaml`: einzeln ab 40 Demo-Trades, Gewinnfaktor mindestens 1,2,
die neuere Hälfte der Trades nicht im Minus, Rückgang höchstens doppelt so groß wie in der Bewertung; oder die Kombi
der Kern-Strategien ab 60 Trades mit denselben Hürden. `journal/vergleich.md` zeigt nach jedem Lauf, wer reif ist.
Dann entscheidet Kiron, und echtes Geld gibt es nur über einen PR im privaten Repo.

Ehrlich: Beim Tempo der Bewertung erreicht die Kombi 60 Trades frühestens etwa im März 2027, eine einzelne
Vortag-Strategie 40 Trades etwa im Mai 2027.
