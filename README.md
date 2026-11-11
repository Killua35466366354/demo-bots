# Demo-Bots

Handelsbots, die nur auf **Demokonten von Capital.com** handeln, also mit Spielgeld. Hier gibt es kein echtes Geld
und keine Anlageberatung. Die Strategien sind Vorwärtstests: Jede hat vorab festgelegte Regeln und ein vorab
festgelegtes Urteil nach einer bestimmten Zahl von Trades.

## Was hier läuft

| Workflow | Was | Wann |
|---|---|---|
| `gold-bot.yml` | Gold-Bot (Strategien C und B aus `gold/strategies/`, Stop 1 x ATR), dazu Gold-Bot 2.0 und TikTok-Box im Schatten (ohne Order) | jede Stunde zur Minute 11 |
| `demo-bots.yml` | Kern-, Labor- und Mess-Bots (Vortag-Bots, US-Index-Rücksetzer, Nasdaq Noise-Band Long, London, Noise USD/JPY), Gold-Hand-Bot, Gold Groß-Box, Prüfung nach 15/40 Trades, Rutsch-Regel und Frist, Vergleich aller Bots, Wache | jeden Tag rund um die Uhr, alle 15 Minuten |
| `pine5m.yml` | Pine-Gold-Bots, Scalper (Nasdaq, DAX, Nikkei), Gold-Staffel, Gold-Zonen Bruch | alle 5 Minuten |
| `tests.yml` | alle Tests | bei jedem Pull Request |

Angestoßen werden die Läufe von außen über [cron-job.org](https://cron-job.org) (workflow_dispatch). GitHubs eigene
Zeitpläne starten zu unzuverlässig. Jeder Lauf schreibt seine Ergebnisse nach `journal/`.

Welcher Bot auf welchem Konto handelt, zeigen `journal/konten.json` (Bots unter der Prüfung) und
`python -m suche.mitnutzer` (Bots mit festem Konto). Den Stand aller Bots zeigt `journal/vergleich.md`.

## Alarme

Jeder der drei Läufe meldet sich am Ende bei [healthchecks.io](https://healthchecks.io) (Checks `gold-bot`, `demo-bots`,
`pine5m`). Bleibt eine Meldung aus, kommt eine E-Mail. Dazu prüft `suche/wache.py` bei jedem 15-Minuten-Lauf zwei Dinge.

- Check `siegel`: Jede Regeldatei `suche/VORAB_*.yaml` steht mit ihrer Prüfsumme im Protokoll. Sonst öffnen die Bots
  nichts mehr, und das soll jemand merken.
- Check `bot-schritte`: Kein Bot-Schritt ist 3 Läufe in Folge gescheitert. Die Schritte laufen mit `continue-on-error`,
  ein Fehler macht den Lauf also nicht rot.

## Regeln

- Die Bots ändern nie ihre eigenen Regeln. Jede Änderung kommt als Pull Request, und nur der Besitzer des Repos merged.
- Ohne grüne Tests handelt kein Bot (jeder Lauf prüft zuerst seine Tests).
- `config/limits.yaml` enthält die Grenzen des Gold-Bots. Sie ändern sich nur per Pull Request.
- `journal/strategie-suche-protokoll.md` enthält die Prüfsummen der Vorab-Regeln (`suche/VORAB_*.yaml`). Ein Bot
  prüft nur nach einer Regel, deren Prüfsumme dort steht.
- Neue Strategien werden vorab festgelegt und dann erst gerechnet. Bewertet wird nach
  `suche/VORAB_bewertung_2024_26.yaml`. Live geht nur, was der Besitzer auswählt.
- Für alle, die hier mit Claude arbeiten, steht das Wichtigste in [`CLAUDE.md`](CLAUDE.md).

## Einrichten

Repository-Secrets (Settings, Secrets and variables, Actions): `CAPITAL_API_KEY`, `CAPITAL_IDENTIFIER`,
`CAPITAL_API_PASSWORD`, dazu optional `TELEGRAM_BOT_TOKEN` und `TELEGRAM_CHAT_ID` für Meldungen und `HC_PING_KEY` für die
Alarme.
Repository-Variable `GOLD_BOT_ENABLED` = `true`.

Lokal testen: `pip install -r requirements.txt` und dann `python -m pytest -q`.
