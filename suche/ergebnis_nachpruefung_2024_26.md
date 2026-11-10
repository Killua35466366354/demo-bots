# Nachprüfung: Welche alten Tests bestehen, wenn 2024 bis 2026 zählt?

Regel: `suche/VORAB_bewertung_2024_26.yaml`. Kiron hat sie am 10.11.2026 um 17:05 UTC gewünscht, versiegelt wurde sie, bevor
nachgeprüft wurde.

**Bestanden heißt jetzt:** im Hauptfenster ab 01.01.2024

- mindestens 100 Trades,
- Gewinnfaktor mindestens 1,2,
- mit 1,5-fachem Spread mindestens 1,0, wo es diese Rechnung gibt,
- beide Hälften über 1,0,
- 2026 allein über 1,0,
- den Zufallsvergleich geschlagen, wo es einen gibt.

Alles vor 2024 ist nur Auskunft. Rechnung: `suche/nachpruefung_2024_26.py`, Zahlen: `suche/ergebnis_nachpruefung_2024_26.json`.

**1.862 Varianten nachgeprüft, 38 bestehen jetzt** (ohne doppelte Trades gezählt). Darunter sind 3, die schon live laufen.
Bei so vielen Varianten besteht auch mal eine nur durch Glück. Im Scalping-Test erreichten zufällige Zwillinge ähnliche
Gewinnfaktoren wie die besten echten Varianten.

## Mindestens 2 Trades je Woche (Kirons Vorrang)

| Strategie | Trades je Woche | Gewinnfaktor ab 2024 | 1,5x Spread | Zufall | Warum sie früher durchfiel |
|---|---|---|---|---|---|
| **Gold Groß-Box** (Runde 12d, TikTok-Box) | 9,1 | 1,21 | 1,15 | 95,5 % | Hürde in Runde 12 war GF 1,3 |
| **Gold Groß-Box Kerze** (Runde 12d) | 8,0 | 1,21 | 1,15 | 96 % | Hürde GF 1,3 |
| Nasdaq Eröffnungskerze, Filter Woche (Scalping mit Opens) | 2,7 | 1,49 | 1,46 | – | nur die 3 besten Märkte wurden genommen (Nasdaq läuft mit Filter „alle“, 1,2 je Woche) |
| DAX Eröffnungskerze, Filter Monat | 2,5 | 1,36 | 1,23 | – | wie oben (DAX läuft mit Filter „alle“) |
| Nasdaq Eröffnungskerze, Filter Monat / Jahr / Quartal | 2,2 bis 2,4 | 1,31 bis 1,35 | 1,30 bis 1,32 | – | wie oben |
| Gold Groß-Klein 3 (Runde 12) | 2,8 | 1,26 | nur über alle Jahre | 95 % über alle Jahre | 2015 bis 2022 im Minus |
| Gold Groß-Klein 3 als Teil eines Kontos mit Prüfer (12e bis 12h) | 2,4 bis 3,7 | 1,30 bis 1,60 | – | – | als ganzes Konto unter GF 1,3 |
| Gold Box 1 Std. / Box laufen (Teile aus 12g, 12h) | 2,2 / 3,8 | 1,44 / 1,21 | – | – | als ganzes Konto unter GF 1,3 |
| Gold Eröffnungskerze, Filter Monat (Scalping mit Opens) | 2,5 | 1,28 | 1,16 | – | nicht unter den 3 besten |
| FTSE Eröffnungskerze 2R, Filter Quartal | 2,5 | 1,21 | 1,14 | – | nicht unter den 3 besten |

„–“ heißt: Für diese Variante allein gibt es keine Rechnung dazu. Für die Teile aus 12e bis 12h gibt es Spread-Probe und
Zufall nur für das ganze Konto.

## Unter 2 Trades je Woche

| Strategie | Trades je Woche | Gewinnfaktor ab 2024 | 1,5x Spread | Bemerkung |
|---|---|---|---|---|
| Nasdaq / DAX Eröffnungskerze, Filter alle | 1,2 | 2,06 / 1,63 | 2,04 / 1,36 | **läuft schon** auf Account 1 |
| Nikkei letzte halbe Stunde, Filter Woche | 1,7 | 1,53 | 1,33 | **läuft schon** auf Account 1 |
| Gotobi CAD/JPY 1 Min. (Runde 2b) | 1,4 | 1,61 | 1,25 | Zufall bestanden, fiel nur an der Kontrolle 2022-24 (0,79) |
| S&P 500 / Nasdaq letzte halbe Stunde, Filter Monat | 1,8 | 1,47 / 1,43 | 1,37 / 1,36 | nicht unter den 3 besten |
| FTSE und DAX Eröffnungskerze 2R/10R, Filter alle | 1,2 bis 1,3 | 1,30 bis 1,41 | 1,23 bis 1,36 | nicht unter den 3 besten |
| Gold Groß-Klein 2 (Runde 12) | 1,3 | 1,25 | nur über alle Jahre | 2015 bis 2022 im Minus |

## Was auch mit der neuen Regel nicht besteht

- Pine 5 Min. auf 21 Märkten: alle 63 Varianten nicht bestanden.
- Gold-Short K2: alle 6 nicht bestanden.
- Markt-Bot auf 18 Aktien:
  - Long hat ab 2025 GF 1,24 und 3 Trades je Woche, schlägt den Zufall aber nur zu 84,5 %.
  - Long und Short zusammen kommen nur auf GF 1,10.
- Runden 7, 9, 10 und 11 (Trades gespeichert): nichts besteht.
- Runde 2b Scalping: außer Gotobi CAD/JPY nichts.

## Ohne neue Rechnung nicht nachprüfbar

Für diese Tests sind keine einzelnen Trades gespeichert, und ihr Rechenzeitraum beginnt vor 2024:

- Runden 1 bis 5 und 8
- Vortag-Paare
- TikTok
- YouTube
- Scalper und Scalping-Komitee Schritt 1
- Gold-Short-Boxen
- Langzeit

Prüfen kann man sie nur mit einer neuen Rechnung ab 2024.

## Ehrlich

- 2024 bis 2026 war für Gold ein starker Aufwärtstrend. Die Gold-Boxen fielen früher, weil sie 2022-24 nur um 1,0 lagen
  und 2015 bis 2022 verloren.
- Was nur in so einem Markt verdient, kann verlieren, wenn er dreht. Darum bleibt das Urteil nach 40 Demo-Trades die
  echte Prüfung.
- Live geht nichts davon ohne Kirons Wahl und einen PR.
