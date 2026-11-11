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
6. **Urteil über laufende Bots:** 15 Trades (Frühwarnung und Ablösung), 40 Trades (Urteil), Kombi 60 Trades,
   Gewinnfaktor mindestens 1,2 (`suche/VORAB_aufstieg.yaml`, `suche/VORAB_wechsel.yaml`). Den Schritt zu echtem Geld
   entscheidet nur Kiron.
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
| `demo-bots.yml` | alle 15 Minuten | Prüfung nach 15/40 Trades, Rücksetzer, Vortag-, London- und Noise-Bots, Gold-Hand, Groß-Box, Vergleich, Wache |
| `pine5m.yml` | alle 5 Minuten | Pine-Gold-Bots, Scalper, Gold-Staffel, Gold-Zonen, Wache |
| `tests.yml` | bei jedem PR | alle Tests |

Angestoßen wird von außen über cron-job.org. Bot-Schritte laufen mit `continue-on-error`, damit ein Fehler die anderen
nicht aufhält. Darum zählt die Wache gescheiterte Schritte und meldet ab 3 Läufen in Folge.

Alarme bei healthchecks.io (E-Mail an Kiron): `gold-bot`, `demo-bots`, `pine5m` (Lebenszeichen), `siegel`,
`bot-schritte`. Zeitplan und Wartezeit richtet `ops/lebenszeichen.py` im privaten Repo ein.

## Bots und Konten

Welcher Bot auf welchem Konto handelt, steht an zwei Stellen. Beide sind die Quelle, keine zweite Liste führen.

- `journal/konten.json` unter `zuordnung`: Bots unter der Prüfung nach 15/40 Trades.
- `python -m suche.mitnutzer`: Bots mit festem Konto im Code (Scalper, Gold-Staffel, Groß-Box, Gold-Zonen, Pine-Bots,
  Gold-Hand).

Mehrere Bots teilen sich ein Konto. Ein Bot darf darum nie fremde Positionen als eigene zählen oder schließen. Die
Prüfung vergibt kein Konto, auf dem ein Mitnutzer handelt. Ein neuer Bot mit festem Konto wird in `suche/mitnutzer.py`
eingetragen.

Gruppen (Stand 11.11.2026, 19 Bots):

- **Kern und Kombi** (Test bestanden): US500- und US100-Rücksetzer, Nasdaq Noise-Band, Vortag EUR/USD, GBP/USD, GBP/JPY.
- **Labor** (knapp durchgefallen, läuft auf Kirons Wunsch): Dow-Rücksetzer, London GBP/USD, Noise USD/JPY.
- **Mess-Bot:** Vortag EUR/USD mit 1-ATR-Stop. Misst nur, wird nie verbessert.
- **Gold:** `gold-cb`, Gold-Staffel, Groß-Box, `pine-k5`, `pine-tp3`, `gold-zonen`. Sechs Bots auf einem Markt, sie
  verlieren oft gemeinsam. Vor einem weiteren Gold-Bot erst diese auswerten.
- **Scalper** (Test durchgefallen, läuft auf Kirons Wunsch): Nasdaq, DAX, Nikkei.

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

## Arbeiten im Repo

- Tests: `python -m pytest -p no:warnings`. Vor jedem Push lokal grün.
- PR als Entwurf, bis der letzte Push drin ist. Möglichst ein gebündelter PR.
- Kiron merged erst, wenn der grüne Haken da ist. Zeigt GitHub "Resolve conflicts", wartet er und schreibt dem Thread.
- Kursdaten liegen nicht im Repo, sondern im Projektordner `strategie-suche/daten/` (5-Minuten-Kerzen, Bid, UTC).
- Was schon gerechnet wurde, steht in `suche/IDEEN.md`, in den Dateien `suche/ergebnis_*.md` und im Protokoll. Erst dort
  nachsehen, dann eine Idee neu testen. Die Trendfolge über viele Märkte ist zweimal durchgefallen (Runde 5 und
  `suche/ergebnis_nachpruefung_runde5.md`), Zonen und News auf Gold einmal (`suche/ergebnis_gold_zonen.md`).
- Texte für Kiron: Deutsch, einfache ganze Sätze, zuerst was er tun muss, Schritte nummeriert mit direktem Link.
