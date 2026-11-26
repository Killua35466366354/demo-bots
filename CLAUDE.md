# CLAUDE.md für das Repo demo-bots

Dieses Repo ist Kirons öffentliches Testlabor. Alle Bots handeln nur auf Demokonten von Capital.com, also mit Spielgeld.
Das private Repo `portfolio-manager` enthält das echte Depot, das Cockpit und die ältere Forschung. Wer hier arbeitet,
liest zuerst diese Datei. Sie beschreibt den Stand der Projekt-Prüfung vom 11.11.2026.

## Feste Regeln

1. **Bots ändern nie ihre eigenen Regeln.** Jede Änderung kommt als Pull Request. Nur Kiron merged.
2. **Nie mergen, nie force-pushen, nie direkt auf `main` pushen.** Arbeite auf deinem eigenen Zweig.
3. **Kein Claude platziert, ändert oder storniert Orders.** Orders kommen nur aus den Bots nach ihren festgelegten Regeln.
   Einen Workflow von Hand anstoßen nur mit Kirons Ja für genau diesen Fall.
4. **Tests werden vorab festgelegt.** Erst die Datei `suche/VORAB_<name>.yaml` schreiben, dann ihre Prüfsumme ins
   Protokoll, dann committen, erst danach mit echten Kursen rechnen. Nie nach dem Ergebnis nachbessern. Bei mehreren
   Varianten Holm über alle.
5. **Bewertung:** `suche/VORAB_bewertung_2024_26.yaml`. 2024 bis 2026 zählt am meisten, ältere Jahre sind Auskunft.
   Bestanden heißt mindestens 100 Trades, Gewinnfaktor ab 1,2, mit 1,5-fachen Kosten ab 1,0, beide Hälften und 2026
   über 1,0 und der Zufallsvergleich geschlagen.
6. **Urteil über laufende Bots:** 15 Trades (Frühwarnung und Ablösung), 40 Trades (Urteil), Gewinnfaktor mindestens
   1,2 (`suche/VORAB_wechsel.yaml`). **Aufstieg zu echtem Geld** (`suche/VORAB_aufstieg_alle.yaml`, Kirons Wahl vom
   18.11.2026 "2 Monate und 100 Trades", ersetzt dafür `suche/VORAB_aufstieg.yaml` mit 40 Trades und Kombi 60): jeder
   Bot allein, die Kombi der Kern-Bots und eine feste Gruppe aller Bots brauchen 100 Demo-Trades, mindestens 61 Tage,
   in den letzten 61 Tagen eine Summe über 0 und eine neuere Hälfte ohne Verlust. Gewinnfaktor 1,2 für die Kern-Bots
   und ihre Kombi, 1,3 für alle anderen und die Gruppe. Seit Kirons Wahl vom 21.11.2026 brauchen auch die drei
   Vortag-Bots allein 1,3 (`suche/VORAB_aufstieg_vortag.yaml`). Mess-Bots und Zwillinge nie. Den Schritt zu echtem
   Geld entscheidet nur Kiron.
7. **Eine Woche live** (`suche/VORAB_eine_woche.yaml`): 7 Tage ab Start, Kontoübergabe oder letzter Regeländerung
   keine Regeländerung und keine Abschaltung. Gilt nicht für `gold-cb`.
8. **Zwilling-Regel** (`suche/VORAB_zwilling.yaml`): Verbesserungen laufen als Zwilling neben dem unveränderten Bot,
   höchstens einer je Original, höchstens ein neuer pro Woche, nie für `gold-cb` oder Mess-Bots.
9. **Live geht nur nach Kirons Wahl** auf einer Karte und über einen PR, auch wenn ein Test bestanden hat.
10. **Keine Schlüssel, Passwörter oder Kontonummern** in Chat, Dokumenten, PR-Texten oder neuen Dateien. Das Repo ist
    öffentlich. Konten heißen in Texten nach ihrem Namen ("Account 5", "US500"). In Tests nur erfundene Nummern. Die
    Nummer eines Demokontos steht nur dort, wo ein Bot sie zum Handeln braucht: als Konstante `KONTO` in seinem Code
    und in `journal/konten.json`. Sie wird von dort gelesen und nie abgetippt oder ausgegeben.
11. **Kein Test wird abgeschaltet, übersprungen oder gelockert**, damit etwas grün wird. Eine versiegelte VORAB-Datei
    wird nie geändert. Eine neue Regel bekommt eine neue Datei.
12. **Keine Modellnamen** in Commits, PR-Titeln, PR-Texten oder Code.
13. **Fremde Bereiche:** Jeder Thread im Projekt besitzt seinen Code und seine Zweige. Erst absprechen, dann ändern.

## Siegel und Protokoll

- `journal/strategie-suche-protokoll.md` wird nur angehängt. Eine Regeldatei gilt nur, wenn dort die Zeile
  `<Dateiname ohne .yaml> sha256 <Prüfsumme>` steht. Die letzte Zeile mit diesem Schlüssel zählt.
- Fehlt eine Zeile oder passt sie nicht, öffnen die Bots nichts mehr. Das ist gewollt.
- **Nie zwei offene PRs, die beide an das Protokoll anhängen.** Das gibt einen Konflikt.
- **Konflikte löst der Thread selbst in seinem Zweig**, Zeichen für Zeichen, nie im Web-Editor. Bei #30 und #35 ging
  dabei je eine Siegel-Zeile verloren, und Bots standen still.
- `suche/wache.py` prüft alle Siegel. Im PR macht `tests/test_wache.py` einen fehlenden Eintrag rot. Im Betrieb meldet
  der 15-Minuten-Lauf an healthchecks.io.
- Hilfen: `suche.runde1.journal_add(text)`, `sha256_text`, `last_value`. Viele Rechen-Programme haben `--festlegen`.

## Was wo läuft

| Workflow | Takt | Was |
|---|---|---|
| `gold-bot.yml` | jede Stunde zur Minute 11 | Gold-Bot C/B (`gold-cb`), dazu Gold-Bot 2.0 und TikTok-Box im Schatten (ohne Order) |
| `demo-bots.yml` | alle 15 Minuten | Prüfung nach 15/40 Trades, Rücksetzer, Vortag-, London- und Noise-Bots, Gold-Hand, Groß-Box, Gold 4-Std.-Ausbruch, 4-Std.-Ausbruch DAX/FTSE/Nikkei, Bollinger Krypto, Vorhersage-Modell Indizes, VIX-Sprung, Williams %R, 4-Std.-Ausbruch Krypto, Bündel ohne Gold, Gold-Bündel, V1 mit wachsendem Einsatz, Vergleich, Kunden-Stimmung (nur mitschreiben, `suche/stimmung.py`), Wache |
| `pine5m.yml` | alle 5 Minuten | Pine-Gold-Bots, Scalper, Gold-Staffel, Gold-Zonen, Wache |
| `tests.yml` | bei jedem PR | alle Tests |

Angestoßen wird von außen über cron-job.org. Bot-Schritte laufen mit `continue-on-error`, damit ein Fehler die anderen
nicht aufhält. Darum zählt die Wache gescheiterte Schritte und meldet ab 3 Läufen in Folge.

Alarme bei healthchecks.io (E-Mail an Kiron): `gold-bot`, `demo-bots`, `pine5m` (Lebenszeichen), `siegel`,
`bot-schritte`. Zeitplan und Wartezeit richtet `ops/lebenszeichen.py` im privaten Repo ein.

## Bots und Konten

Welcher Bot auf welchem Konto handelt, steht an zwei Stellen. Beide sind die Quelle, keine zweite Liste führen.

- `journal/konten.json` unter `zuordnung`: Bots unter der Prüfung nach 15/40 Trades.
- `python -m suche.mitnutzer`: Bots mit festem Konto im Code (Scalper, Gold-Staffel, Groß-Box, Gold-Zonen, Gold
  4-Std.-Ausbruch, 4-Std.-Ausbruch DAX/FTSE/Nikkei, Bollinger Krypto, Vorhersage-Modell Indizes, VIX-Sprung,
  Williams %R, 4-Std.-Ausbruch Krypto, Bündel ohne Gold, Gold-Bündel, V1 mit wachsendem Einsatz, Pine-Bots, Gold-Hand).

Mehrere Bots teilen sich ein Konto. Ein Bot darf darum nie fremde Positionen als eigene zählen oder schließen. Die
Prüfung vergibt kein Konto, auf dem ein Mitnutzer handelt. Ein neuer Bot mit festem Konto wird in `suche/mitnutzer.py`
eingetragen.

`journal/konten.json` nennt unter `konten` jedes Konto nur mit den letzten vier Stellen (…1234). Wer sein Konto nach
dem Namen sucht, nimmt `suche.mitnutzer.konto_nach_name`. Sie findet die volle Nummer unter `zuordnung`, `frei` oder
`haupt`. Mit der gekürzten Nummer fanden `welt-ausbruch4h` und `krypto-bollinger` ihr Konto beim Broker nicht und
handelten bis zum 20.11.2026 nie (Lauf meldet "kein Konto"). `tests/test_mitnutzer.py` prüft das jetzt.

Gruppen (Stand 11.11.2026, 20 Bots):

- **Kern und Kombi** (Test bestanden): US500- und US100-Rücksetzer, Nasdaq Noise-Band, Vortag EUR/USD, GBP/USD, GBP/JPY. Vortag
  GBP/JPY ist seit dem 22.11.2026 beendet (Kirons Wort, größtes Minus, `BEENDET` in `suche/r6_bots.py`), seine Trades
  zählen in Kombi und Gruppe weiter.
- **Labor** (knapp durchgefallen, läuft auf Kirons Wunsch): Dow-Rücksetzer, London GBP/USD, Noise USD/JPY.
- **Mess-Bot:** Vortag EUR/USD mit 1-ATR-Stop. Misst nur, wird nie verbessert.
- **Gold:** `gold-cb`, Gold-Staffel, Groß-Box, `pine-k5`, `gold-zonen`, `gold-ausbruch4h`. Sechs Bots auf einem Markt,
  sie verlieren oft gemeinsam. Vor einem weiteren Gold-Bot erst diese auswerten. `pine-tp3` ist seit dem 22.11.2026
  abgeschaltet (Kirons Wort, der Bot mit dem größten Minus, 48 Demo-Trades, Gewinnfaktor 0,52). Er öffnet nichts Neues,
  ein offener Trade läuft nach seinen Regeln zu Ende. In der festen Gruppe aller Bots zählen seine Trades weiter.
  Dazu rechnet der Schatten-Zwilling `gold-grossbox-weiter125` mit (Groß-Box mit 1,25-fachem Stop, keine Order,
  `gold/grossbox_zwilling.py`, `suche/VORAB_gold_grossbox_weiter125.yaml`, Kirons Wahl vom 19.11.2026).
- **Scalper** (Test durchgefallen, läuft auf Kirons Wunsch): Nasdaq, DAX, Nikkei.
- **Seit 19.11.2026:** `welt-ausbruch4h`, der 4-Std.-Ausbruch auf DAX, FTSE und Nikkei (Kandidat, Kirons Wahl).
- **Seit 20.11.2026:** `krypto-bollinger`, Bollinger und RSI auf Bitcoin und Ether umgedreht (Test durchgefallen,
  Kirons Wahl "die paar stärksten zu erst" aus dem Schatten direkt als Demo-Bot). Dazu `modell-indizes`, das
  Vorhersage-Modell auf US500, US100, DAX, FTSE und Nikkei (Kandidat, Kirons Wahl "Modell Indizes, jetzt bauen").
  Dazu `vix-sprung`, der Tag nach einem VIX-Sprung auf denselben fünf Indizes (Kandidat in Durchgang 1, Kirons Wunsch
  "baue danach aber weiter aus"). Dazu `williams-us`, Williams %R auf US500 und US100 (nicht bestanden, unter 100
  Trades, derselbe Wunsch). Dazu `krypto-ausbruch4h`, der 4-Std.-Ausbruch auf Bitcoin und Ether (nicht bestanden,
  2026 im Minus, derselbe Wunsch). Dazu `buendel9`, das Bündel aus 9 Bots auf "Vortag USDJPY". Es hat kein eigenes
  Signal und kopiert die Trades von 9 anderen Bots (Kirons Wahl "Ein Konto mit 9 Bots").
- **Seit 26.11.2026:** `gold-buendel`, das Gold-Bündel auf "Vortag USDJPY". Es kopiert die drei Gold-Bots aus
  `buendel9`, der seitdem nur noch die sechs anderen kopiert (Kirons Wahl "Zwei Bündel auf einem Konto"). Dazu
  `v1-wachsend`, V1 mit wachsendem Einsatz auf Account 3 neben dem Bollinger-Bot Krypto. Er kopiert alle 9 Bots von V1
  mit 2 % des eigenen gedachten Kontostands (Kirons Wahl "Eigener Demo-Bot auf Account 3").

## Gold-Bot C/B

- Grenzen in `config/limits.yaml` unter `gold`. Sie ändern sich nur per PR.
- `size` ist die Obergrenze. Würde der Stop mehr als `risk_per_trade_pct` des Kontos kosten, nimmt der Bot die größte
  Größe, die darunter bleibt (`gold/bot/rules.py` `trade_size`, Kirons Wahl vom 11.11.2026). Erst wenn selbst die
  kleinste Größe des Brokers zu teuer wäre, fällt das Signal aus.
- Feldnamen in `journal/gold-trades.jsonl` und im Zustand nicht umbenennen. Cockpit und Prüfungen lesen sie.

## Gold-Zonen-Bot

- `gold/zonen_bot.py`, Regeln `suche/VORAB_gold_zonen_bot.yaml` (versiegelt am 11.11.2026). Bruch mit Rollenwechsel an
  Zonen des 4-Std.-Charts auf Account 2, den er mit dem Mess-Bot teilt. Der Test ist durchgefallen
  (`suche/ergebnis_gold_zonen.md`). Der Bot läuft als Vorwärtstest auf Kirons Wahl vom 11.11.2026, Urteil nach 40 Trades.
- Es liegt höchstens eine Limit-Order beim Broker. Account 2 hat kein Hedging, eine Order der Gegenrichtung könnte einen
  offenen Trade schließen. Das nie lockern.
- Die Rechnung (Zonen, wartende Orders, Ziel) kommt aus `suche/gold_zonen.py`, denselben Funktionen wie im Test.
  `tests/test_gold_zonen.py` prüft, dass Bot und Test dieselbe Order sehen.

## Gold 4-Std.-Ausbruch

- `gold/ausbruch4h_bot.py`, Regeln `suche/VORAB_gold_ausbruch4h_bot.yaml` (versiegelt am 11.11.2026). Der nächste
  Kandidat der Gold-Matrix (`ausbruch.4h.trend_hoch.swing_4h.zeit_4h`) auf Account 4, den er mit dem Kern-Bot Vortag
  EUR/USD teilt. Der Test ist knapp nicht bestanden (`suche/ergebnis_gold_matrix.md`). Der Bot läuft als Vorwärtstest
  auf Kirons Wahl vom 11.11.2026, Urteil nach 40 Trades. Im Test brachte ein Trade im Schnitt nur +0,15 R.
- Signal, Tagestrend, Sperre und Stop-Abstand rechnen die Funktionen des Tests (`suche/gold_matrix.py`). Alle Zahlen
  der Regel kommen aus den versiegelten Dateien der Gold-Matrix. `tests/test_ausbruch4h_bot.py` und
  `python -m suche.gold_ausbruch4h_gegenprobe <Datenordner>` prüfen, dass Bot und Test dieselben Einstiege, Stops und
  Ausstiege sehen.
- Höchstens ein Trade. Jede 4-Std.-Kerze bekommt höchstens eine Order, eine gescheiterte Order wird nie wiederholt.

## 4-Std.-Ausbruch DAX, FTSE, Nikkei

- `suche/welt4h_bot.py`, Regeln `suche/VORAB_welt_ausbruch4h_bot.yaml` (versiegelt am 19.11.2026). Der Kandidat der
  Runde "Kirons Notizen" (Fassung `ausbruch4h_welt_ziel_1r`) auf Account 7, den er mit dem Labor-Bot Noise USD/JPY
  teilt. Die Kontonummer liest er nach dem Namen aus `journal/konten.json`. Der Test ist nicht bestanden
  (`suche/ergebnis_notizen_runde.md`, z 2,26 statt 3). Der Bot läuft als Vorwärtstest auf Kirons Wahl vom 19.11.2026
  12:23 UTC, Urteil nach 40 Trades. Im Test brachte ein Trade im Schnitt nur +0,044 R.
- Die Vorwärts-Zählung ohne Bot (`suche/VORAB_notizen_vorwaerts.yaml`) läuft daneben unverändert weiter.
- Signal, Tagestrend, Sperre, Stop und Ziel rechnet die Funktion des Tests (`suche/notizen_runde.signale`) auf
  Stundenkerzen des Brokers. `tests/test_welt4h_bot.py` und `python -m suche.welt4h_gegenprobe <Datenordner>` prüfen,
  dass Bot und Test dieselben Einstiege, Stops, Ziele und Ausstiege sehen.
- Höchstens ein Trade je Markt. Jede 4-Std.-Kerze bekommt je Markt höchstens eine Order, eine gescheiterte Order wird
  nie wiederholt. Liegt eine fremde Position auf seinem Markt, öffnet er dort nichts.

## Bollinger Krypto umgedreht

- `suche/krypto_bollinger_bot.py`, Regeln `suche/VORAB_krypto_bollinger_bot.yaml` (versiegelt am 20.11.2026). Die
  Fassung `bollinger_umkehr_krypto_weit` der Runde "Kirons Notizen" auf Bitcoin und Ether (Epics BTCUSD, ETHUSD) auf
  Account 3, den er seit dem 26.11.2026 mit `v1-wachsend` teilt (Vortag GBP/JPY ist beendet). Die Kontonummer liest
  er nach dem Namen aus `journal/konten.json`. Der Test ist durchgefallen (`suche/ergebnis_notizen_runde.md`, Gewinnfaktor 1,07, neuere
  Hälfte 0,98). Der Bot läuft als Vorwärtstest auf Kirons Wahl vom 20.11.2026 11:53 UTC, Urteil nach 40 Trades. Im
  Test brachte ein Trade im Schnitt nur +0,046 R. Das Schatten-Labor zählt dieselbe Fassung unverändert weiter.
- Signal, Stop und Ziel rechnet die Funktion des Tests (`suche/notizen_runde.signale`) auf Stundenkerzen des Brokers.
  `tests/test_krypto_bollinger_bot.py` und `python -m suche.krypto_bollinger_gegenprobe <Datenordner>` prüfen, dass
  Bot und Test dieselben Einstiege, Stops, Ziele und Ausstiege sehen.
- Höchstens ein Trade je Markt. Jede Stundenkerze bekommt je Markt höchstens eine Order, eine gescheiterte Order wird
  nie wiederholt. Liegt eine fremde Position auf seinem Markt, öffnet er dort nichts. Krypto hat bei Capital.com für
  Privatkunden nur Hebel 2, darum darf eine Order bis 40 % des freien Gelds als Margin binden (andere Bots 20 %).

## Vorhersage-Modell Indizes

- `suche/modell_indizes_bot.py`, Regeln `suche/VORAB_modell_indizes_bot.yaml` (versiegelt am 20.11.2026). Die Fassung
  `modell_indizes` der großen Runde (`suche/VORAB_grosse_runde.yaml`) auf US500, US100, DAX, FTSE 100 und Nikkei 225
  (Epics US500, US100, DE40, UK100, J225) auf Account 6, den er mit der Groß-Box und dem London-Bot teilt. Die
  Kontonummer liest er nach dem Namen aus `journal/konten.json`. Der Test ist nicht bestanden, Kandidat
  (`suche/ergebnis_grosse_runde.md`, Gewinnfaktor 1,21, z 1,89, vor 2024 0,94, fast nur Käufe). Der Bot läuft als
  Vorwärtstest auf Kirons Wahl vom 20.11.2026 12:25 UTC, Urteil nach 40 Trades. Im Test brachte ein Trade im Schnitt
  nur +0,024 R. Das Schatten-Labor zählt dieselbe Fassung unverändert weiter.
- Das Modell lernt im Test jedes Jahr neu. Live nimmt der Bot die Zahlen, die der Test im Jahr benutzt
  (`suche/modell_indizes_gewichte.json`, Prüfsumme in der Regeldatei, gebaut mit
  `python -m suche.modell_indizes_gegenprobe gewichte <Datenordner>`). Für 2027 gibt es noch keine. Dann öffnet er
  nichts, bis neue Gewichte mit einer neuen Regeldatei per PR kommen (HistData bis Ende Dezember 2026).
- VIX und VIX3M holt er von Cboe, die Renditen 10 und 2 Jahre vom US-Finanzministerium. Das sind die Quellen der
  FRED-Reihen des Tests, FRED selbst kommt einen Tag zu spät. Fehlt im letzten Lauf der Frist der Wert vom Vortag,
  lässt er den Tag aus und zählt das im Zustand unter `ausgelassen`.
- Merkmale, Stop und Ausstiegszeit rechnen die Funktionen des Tests (`suche/grosse_runde.merkmale`, `_tagestrades`)
  auf Stundenkerzen des Brokers. `tests/test_modell_indizes_bot.py` und
  `python -m suche.modell_indizes_gegenprobe pruefen <Datenordner>` prüfen, dass Bot und Test dieselben Einstiege,
  Stops und Ausstiege sehen.
- Einstieg ab 18:00 New York höchstens 20 Minuten nach dem ersten Kurs des Brokers, Stop 2 ATR beim Broker, kein Ziel,
  Ausstieg im ersten Lauf ab 15:40 New York. Höchstens ein Trade je Markt, eine gescheiterte Order wird nie
  wiederholt. Liegt eine fremde Position auf seinem Markt, öffnet er dort nichts.

## Tag nach einem VIX-Sprung

- `suche/vix_sprung_bot.py`, Regeln `suche/VORAB_vix_sprung_bot.yaml` (versiegelt am 20.11.2026). Die Fassungen
  `vix_sprung_us` (`suche/VORAB_grosse_runde.yaml`, US500 und US100) und `vix_sprung_welt`
  (`suche/VORAB_grosse_runde2.yaml`, DAX, FTSE 100 und Nikkei 225) unverändert auf Account 5, den er mit `pine-k5`
  und dem Dow-Rücksetzer teilt. Die Kontonummer liest er nach dem Namen aus `journal/konten.json`. US nicht
  bestanden, Kandidat (Gewinnfaktor 1,93, z 2,17, vor 2024 1,13), Welt durchgefallen (1,41, vor 2024 0,85). Zusammen
  340 Trades an nur 68 Tagen, 2024 verloren. Der Bot läuft als Vorwärtstest auf Kirons Wunsch vom 20.11.2026
  ("baue danach aber weiter aus"), Urteil nach 40 Trades. Im Test brachte ein Trade im Schnitt nur +0,049 R. Das
  Schatten-Labor zählt beide Fassungen unverändert weiter.
- Ist der VIX-Schluss vom letzten Handelstag mindestens 10 % über dem davor, kauft er ab 18:00 New York alle fünf
  Märkte. Stop 3 ATR beim Broker, kein Ziel, Ausstieg im ersten Lauf ab 15:40 New York. Nur Käufe, höchstens ein Trade
  je Markt, eine gescheiterte Order wird nie wiederholt. Liegt eine fremde Position auf seinem Markt, öffnet er dort
  nichts.
- Den VIX holt er von Cboe, der Quelle der FRED-Reihe des Tests. Ohne Sprung ist der Tag damit für alle fünf Märkte
  erledigt, ohne Kerzen vom Broker (etwa 91 % der Tage). Fehlt im letzten Lauf der Frist der Wert vom Vortag, lässt
  er den Tag aus und zählt das im Zustand unter `ausgelassen` (Grund `vix_alt`). Die Feiertage der Börse New York
  stehen im Code bis Ende 2027.
- Die Rechnung des Tests (`suche/grosse_runde.richtung_reihe`, `_tagestrades`) läuft auf Stundenkerzen des Brokers.
  `tests/test_vix_sprung_bot.py` und `python -m suche.vix_sprung_gegenprobe <Datenordner>` prüfen, dass Bot und Test
  dieselben Einstiege, Stops und Ausstiege sehen.

## Williams %R US500 und US100

- `suche/williams_bot.py`, Regeln `suche/VORAB_williams_bot.yaml` (versiegelt am 20.11.2026). Die Fassung
  `williams_us` der YouTube-Runde (`suche/VORAB_youtube_runde.yaml`) unverändert auf Account 7, den er mit dem
  4-Std.-Ausbruch DAX, FTSE, Nikkei und dem Labor-Bot Noise USD/JPY teilt. Die Kontonummer liest er nach dem Namen aus
  `journal/konten.json`. Der Test ist nicht bestanden (`suche/ergebnis_youtube_runde.md`, 77 Trades, Gewinnfaktor
  2,66, Holm erfüllt, aber unter 100 Trades und z 2,35 statt 3, vor 2024 1,51). Das Plus kam vor allem 2024. Bei 47
  von 77 Trades kaufte auch der US500-Rücksetzer. Der Bot läuft als Vorwärtstest auf Kirons Wunsch vom 20.11.2026
  ("baue danach aber weiter aus"), Urteil nach 40 Trades. Im Test brachte ein Trade im Schnitt +0,17 R. Das
  Schatten-Labor zählt dieselbe Fassung unverändert weiter.
- Schließt Williams %R(2) der Sitzung 9:30 bis 16:00 New York unter -90, kauft er im ersten Lauf ab 16:00 New York
  (höchstens 20 Minuten danach). Ausstieg ebenso um 16:00 New York, wenn der Schluss über dem Vortageshoch liegt oder
  %R über -30 schließt, spätestens nach 10 Sitzungen. Stop 3 ATR beim Broker, kein Ziel. Nur Käufe, höchstens ein
  Trade je Markt, an der Kerze des Ausstiegs kein neuer Kauf, eine gescheiterte Order wird nie wiederholt. Liegt eine
  fremde Position auf seinem Markt, öffnet er dort nichts. Fällt jeder Lauf der Frist aus, zählt er den Tag als
  `verpasst` und holt einen fälligen Ausstieg im nächsten Lauf um 16:00 nach.
- Die Kerzen: die jüngsten 1.000 5-Minuten-Kerzen von Capital.com (darin heute und die Sitzung davor) und davor
  Stundenkerzen. Sitzung, %R und Ausstieg rechnet `williams_bot.sitzungen` Zeile für Zeile wie
  `suche/youtube_runde.regel_williams`, ATR und Tageskerzen `suche/rueckblick.Markt`. `tests/test_williams_bot.py` und
  `python -m suche.williams_gegenprobe <Datenordner>` prüfen, dass Bot und Test dieselben Einstiege, Stops und
  Ausstiege sehen.

## 4-Std.-Ausbruch Bitcoin und Ether

- `suche/krypto4h_bot.py`, Regeln `suche/VORAB_krypto_ausbruch4h_bot.yaml` (versiegelt am 20.11.2026). Die Fassung
  `ausbruch4h_krypto` der YouTube-Runde (`suche/VORAB_youtube_runde.yaml`) unverändert auf Bitcoin und Ether (Epics
  BTCUSD, ETHUSD) auf Account 5, den er mit `pine-k5`, dem Labor-Bot Dow-Rücksetzer und dem VIX-Sprung teilt (kein
  Kern-Bot). Bitcoin und Ether des Bollinger-Bots liegen auf Account 3, so sperren sich die beiden nie. Die Kontonummer
  liest er nach dem Namen aus `journal/konten.json`. Der Test ist nicht bestanden (`suche/ergebnis_youtube_runde.md`,
  319 Trades, Gewinnfaktor 1,23, aber 2026 0,91 und z 2,35 statt 3, vor 2024 1,10). Das Plus kam vor allem aus 2024, aus
  Bitcoin und aus Käufen, ohne die 5 besten Trades 0,98. Der Bot läuft als Vorwärtstest auf Kirons Wunsch vom 20.11.2026
  ("baue danach aber weiter aus"), Urteil nach 40 Trades. Im Test brachte ein Trade im Schnitt +0,044 R. Das
  Schatten-Labor zählt dieselbe Fassung unverändert weiter.
- Wie der 4-Std.-Ausbruch DAX, FTSE, Nikkei, aber alle sieben Tage, ohne Ziel und mit Hebel 2: Schluss einer
  4-Std.-Kerze über dem Hoch der 20 Kerzen davor mit dem Tagestrend (EMA 50), Stop hinter dem Tief der letzten 10
  Kerzen beim Broker, Ausstieg nach 4 fertigen 4-Std.-Kerzen (16 Stunden). Verkauf spiegelbildlich. Höchstens ein Trade
  je Markt, an der Kerze des Ausstiegs kein neuer Einstieg, eine gescheiterte Order wird nie wiederholt. Liegt eine
  fremde Position auf seinem Markt, öffnet er dort nichts. Eine Order darf bis 40 % des freien Gelds als Margin binden,
  Orders aus demselben Lauf zählen mit.
- Signal, Tagestrend, Sperre und Stop rechnet die Funktion des Tests (`suche/youtube_runde.signale`, Regel
  `ausbruch4h`) auf Stundenkerzen des Brokers und dem Markt des Tests mit sieben Handelstagen. Der Bot schreibt seine
  Dateien nach jedem Schluss einer 4-Std.-Kerze, also mindestens alle 4 Stunden, auch am Wochenende.
  `tests/test_krypto4h_bot.py` und `python -m suche.krypto4h_gegenprobe <Datenordner>` prüfen, dass Bot und Test
  dieselben Einstiege, Stops und Ausstiege sehen.

## Bündel ohne Gold und Gold-Bündel

- `suche/buendel_bot.py`, ein Code für zwei Bündel auf dem Konto "Vortag USDJPY", das sie mit dem Kern-Bot Vortag
  GBP/USD und dem ruhenden pine-hand teilen. Welches Bündel ein Lauf führt, sagt `--regel`. Die Kontonummer liest er
  nach dem Namen aus `journal/konten.json`.
  - `buendel9`: Kirons Wahl vom 20.11.2026 16:20 UTC "Ein Konto mit 9 Bots", erste Regel `suche/VORAB_buendel9_bot.yaml`
    (versiegelt am 20.11.2026, bleibt unverändert). Seit Kirons Wahl vom 26.11.2026 09:59 UTC "Zwei Bündel auf einem
    Konto" gilt `suche/VORAB_buendel9_ohne_gold.yaml`: Er kopiert nur noch die Rücksetzer US500 und US100, das
    Noise-Band Nasdaq, `scalp-de40`, `scalp-us100` und `welt-ausbruch4h`. Die drei Gold-Bots stehen dort unter
    `auslaufend`: Ihre offenen Kopien laufen zu Ende, neue bekommen sie nicht. Kontostand und Zählung laufen weiter,
    der Wechsel steht im Zustand unter `regeln` und `regel_seit`.
  - `gold-buendel`: Kirons Wunsch vom 26.11.2026 09:53 UTC, die Gold-Bots als eigenes Bündel zu trennen, Regeln
    `suche/VORAB_gold_buendel_bot.yaml` (versiegelt am 26.11.2026). Er kopiert `gold-cb`, `gold-zonen` und
    `gold-ausbruch4h` mit eigenen gedachten 700 €. Mit Groß-Box, `pine-k5` und Gold-Staffel bremste der Backtest bei
    30 % Rückgang, darum nur diese drei.
- Kein Bündel erfindet ein Signal. Die Deal-ID liest es aus der Datei des Mitglieds, Stop und Ziel beim Broker auf
  dessen Konto. Kauf oder Verkauf, Stop und Ziel wie die Quelle, eine eigene Richtungsregel gibt es nicht. 7 € Risiko
  auf ein gedachtes Konto von 700 €. Zieht die Quelle ihren Stop nach, gleicht es die Kopie an. Schließt die Quelle,
  schließt es die Kopie zum Markt.
- Nur Trades, die die Quelle vor höchstens 30 Minuten eröffnet hat. Jeder Trade bekommt höchstens eine Kopie auf dem
  Konto, auch über beide Bündel. Eine gescheiterte Order wird nie wiederholt. Jedes Bündel fasst nur seine eigenen
  Kopien an ihrer Deal-ID an, nie GBPUSD und nie eine Kopie des anderen Bündels (`fremde_kopien` aus dessen
  `state.json`).
- Konto-Wächter je Bündel: Margin aller Kopien höchstens 50 % des gedachten Kontostands, beim Broker bleiben danach
  mindestens 250 € frei (für Vortag GBP/USD). Liegt der gedachte Kontostand 30 % unter seinem Höchststand, kopiert es
  nichts Neues mehr, bis Kiron mit einer neuen Regeldatei entscheidet. Es schaltet den Hedging-Modus des Kontos ein,
  ohne Hedging höchstens eine Kopie je Markt, die Kopien des anderen Bündels zählen mit. Ein Mitglied mit 40
  Demo-Trades und Gewinnfaktor unter 1,2 (`journal/vergleich.json`) bekommt keine neuen Kopien mehr.
- Urteil wie jeder andere Bot nach `suche/VORAB_aufstieg_alle.yaml` (einzeln, in R der Kopien, alle Kopien in
  `journal/<bot>/trades.jsonl` seit dem Start). Keins steht in der festen Gruppe aller Bots, damit kein Trade doppelt
  zählt. Backtest (Auskunft, an denselben Monaten ausgesucht, 2026 mit eigenen 700 €): Bündel aus 9 Bots 9,2 %
  Rendite pro Monat, ohne Gold 5,5 % (84 % des Gewinns über zwei Jahre von den Scalpern, deren Test durchgefallen ist),
  Gold-Bündel 3,6 % (5 von 10 Monaten im Minus, 198 Käufe +109 R, 159 Verkäufe +9 R).
- Beide laufen im 15-Minuten-Lauf nach den anderen Bots, erst `buendel9`, dann `gold-buendel`. Kopien der Scalper und
  der Gold-Zonen (5-Minuten-Lauf) kommen darum bis zu 15 Minuten später als die Quelle. Jedes schreibt nur
  `journal/<bot>/` und `journal/<bot>.json`.
- Bis zum 26.11.2026 merkte sich `buendel9` die Deal-ID der Order statt der Position (`deal_aus_bestaetigung`). Er fand
  keine seiner 7 Kopien unter seinen Positionen und buchte jede nach gut einer Stunde mit -1 R als "beim Broker zu",
  auch die noch offenen. Seitdem sucht er eine fehlende Kopie erst nach Markt, Richtung, Größe und Eröffnungszeit
  (`passende_position`). Eine als geschätzt gebuchte Kopie, die noch offen liegt, führt er wieder. Ihre falsche Buchung
  steht danach in `journal/buendel9/storniert.jsonl`. Im ersten Lauf danach (26.11.2026 10:03 UTC) waren es 4 Kopien.

## V1 mit wachsendem Einsatz

- Kirons Wunsch vom 26.11.2026 13:07 UTC ("alles mal nach den echten Regeln") und seine Wahl 13:36 UTC "Eigener
  Demo-Bot auf Account 3". Derselbe Code `suche/buendel_bot.py`, Regeln `suche/VORAB_v1_wachsend_bot.yaml`, Schritt
  `v1_wachsend` im 15-Minuten-Lauf nach `gold-buendel`. Er kopiert jeden neuen Trade der 9 Bots von V1 (die Mitglieder
  der ersten Regel von `buendel9`) auf Account 3, den er mit `krypto-bollinger` teilt.
- Einsatz 2 % des eigenen gedachten Kontostands bei der Eröffnung, Start 1.000 €. Gewinne gehen zurück ins Konto, der
  Einsatz wächst mit, Verluste lassen ihn schrumpfen. Keine Bremse, nur die Grenze des Brokers: Margin aller Kopien
  höchstens 100 % des gedachten Kontostands, beim Broker bleiben 250 € frei für den Bollinger-Bot. Fällt der gedachte
  Kontostand auf 0 €, kopiert er nichts mehr.
- Nie BTCUSD oder ETHUSD, nie eine Position des Bollinger-Bots. Die Kopien der Bündel auf "Vortag USDJPY" sind für ihn
  nicht fremd (anderes Konto), derselbe Trade kann dort und hier je eine Kopie bekommen. Er steht darum wie die Bündel
  nicht in der festen Gruppe aller Bots.
- Vorher geprüft und durchgefallen: drei live erkennbare Gründe für die tiefen Rückgänge von V1
  (`suche/ergebnis_v1_rueckgang.md`, 0 von 3, umdrehen war überall schlechter). Darum hat er keinen Filter. Rückblick
  (Auskunft, an denselben Monaten ausgesucht): Start 01.01.2026 mit 1.000 € Ende Oktober 2.309 €, Rückgang 33 %.
  Urteil nach `suche/VORAB_aufstieg_alle.yaml` einzeln (100 Demo-Trades, 61 Tage, Gewinnfaktor 1,3). Echtes Geld
  entscheidet nur Kiron.

## Schatten-Labor und Kombinierer

- Seit 20.11.2026 (Kirons Wunsch, Regeln `suche/VORAB_schatten.yaml`). Kein Bot liest ihre Dateien, keine Order.
- **Schatten-Labor** (`suche/schatten.py`): alle 52 Fassungen der sechs Runden auf `suche/rueckblick.py` zählen ab
  23.11.2026 ohne Order vorwärts, einmal im Monat auf neuen HistData-Kerzen (`nachladen`, `daten`, `zaehlen`). Neue
  Monate kommen als eigene Dateien nach `strategie-suche/daten/monate/`, die Grunddateien bleiben unverändert.
  Kandidat erst nach 100 Trades, 61 Tagen, Gewinnfaktor 1,3 und Holm über alle 52. Dann eine Karte an Kiron für
  einen Demo-Bot mit eigener VORAB-Datei. Nichts steigt von allein auf.
  Seit 20.11.2026 zählt `modell_breit` aus der Runde "Kirons Trade-Notizen" als 53. Fassung mit (Kirons Wahl,
  `suche/VORAB_schatten_modell_breit.yaml`, Holm dann über 53). `nachladen` holt dafür jeden Monat den DIX als neue
  Datei. Ein Trade von `modell_breit` zählt nur in Jahren, für die `gold/v2/termine.yaml` alle Termine hat.
- **Kombinierer** (`suche/kombinierer.py`, Schritt im 15-Minuten-Lauf): rechnet die Gruppe aller Bots und die
  Kern-Kombi als ein Konto mit 1.000 € und 10 € je R, ohne Grenzen und mit den Regeln eines echten Kontos
  (höchstens 3 offen, einer je Markt, Tagesstopp 3 %, Bremse 20 %). Die Trades kommen aus `suche/vergleich.py`
  (`sammeln`), es gibt keine zweite Liste. Ergebnis in `journal/kombinierer.md`.
- **Margin-Ampel** (seit 20.11.2026, Kirons Ja, `suche/VORAB_kombinierer_margin.yaml`): zwei weitere Regeln im
  Kombinierer. Ein Trade zählt nur, wenn die Margin aller offenen Trades mit ihm höchstens 30 % (zum Vergleich 50 %)
  des Kontostands ist. Margin = 10 € mal Einstieg durch Stop-Abstand durch Hebel (30 Devisen, 20 Gold und Indizes).
  Ein Vortag-Trade mit 2 bis 3 Pips Stop bindet so über 1.000 €. Die alten Regeln bleiben unverändert daneben.
- **Gold-Duo doppelt** (seit 25.11.2026, Kirons Wahl "g11", `suche/gold_duo.py`, `suche/VORAB_gold_duo_doppelt.yaml`):
  eine Zählung ohne Order als eigener Abschnitt in `journal/kombinierer.md`. Gold-Bot C/B und Pine-K5 zusammen auf
  einem gedachten Konto mit 1.000 €, jeder Trade mit der doppelten Größe des Demo-Trades. Es zählen nur Trades, die ab
  dem 25.11.2026 08:00 UTC eröffnet wurden. Der November davor (+207 €, fast alles an zwei Tagen mit fallendem Gold)
  zählt nicht. Ein Trade zählt nur, wenn sein Sicherheitsgeld bei Hebel 20 noch auf das Konto passt. Liegt das Konto
  30 % unter seinem Höchststand, ist die Zählung beendet. Urteil nach 100 gezählten Trades und 61 Tagen mit
  Gewinnfaktor 1,3. "reif" heißt nur eine Karte an Kiron. Kein neuer Bot, kein Konto, keine Zwillings-Regel berührt.

## Arbeiten im Repo

- Tests: `python -m pytest -p no:warnings`. Vor jedem Push lokal grün.
- PR als Entwurf, bis der letzte Push drin ist. Möglichst ein gebündelter PR.
- Kiron merged erst, wenn der grüne Haken da ist. Zeigt GitHub "Resolve conflicts", wartet er und schreibt dem Thread.
- Kursdaten liegen nicht im Repo, sondern im Projektordner `strategie-suche/daten/` (5-Minuten-Kerzen, Bid, UTC).
- Was schon gerechnet wurde, steht in `suche/IDEEN.md`, in den Dateien `suche/ergebnis_*.md` und im Protokoll. Erst dort
  nachsehen, dann eine Idee neu testen. Die Trendfolge über viele Märkte ist zweimal durchgefallen (Runde 5 und
  `suche/ergebnis_nachpruefung_runde5.md`), Zonen und News auf Gold einmal (`suche/ergebnis_gold_zonen.md`), die
  Gold-Matrix über alle Zeitebenen von 1 Min. bis 4 Std. einmal (`suche/ergebnis_gold_matrix.md`, 54.375 Varianten,
  0 bestanden, 3 Kandidaten).
- Texte für Kiron: Deutsch, einfache ganze Sätze, zuerst was er tun muss, Schritte nummeriert mit direktem Link.
