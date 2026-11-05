# Demo-Bots

Handelsbots, die nur auf **Demokonten von Capital.com** handeln, also mit Spielgeld. Hier gibt es kein echtes Geld
und keine Anlageberatung. Die Strategien sind Vorwärtstests: Jede hat vorab festgelegte Regeln und ein vorab
festgelegtes Urteil nach einer bestimmten Zahl von Trades.

## Was hier läuft

| Workflow | Was | Wann |
|---|---|---|
| `gold-bot.yml` | Gold-Bot (Strategien C und B aus `gold/strategies/`, Stop 1 x ATR) und Gold-Bot 2.0 im Schatten (ohne Order) | jede Stunde zur Minute 11 |
| `demo-bots.yml` | Kern-, Labor- und Mess-Bots (Vortag-Bots, US-Index-Rücksetzer, Nasdaq Noise-Band Long, Brent, London, Noise USD/JPY), Prüfung nach 15/40 Trades, Rutsch-Regel und Frist | jeden Tag rund um die Uhr, alle 15 Minuten |
| `tests.yml` | alle Tests | bei jedem Pull Request |

Angestoßen werden die Läufe von außen über [cron-job.org](https://cron-job.org) (workflow_dispatch). GitHubs eigene
Zeitpläne starten zu unzuverlässig. Jeder Lauf schreibt seine Ergebnisse nach `journal/`.

## Regeln

- Die Bots ändern nie ihre eigenen Regeln. Jede Änderung kommt als Pull Request, und nur der Besitzer des Repos merged.
- Ohne grüne Tests handelt kein Bot (jeder Lauf prüft zuerst seine Tests).
- `config/limits.yaml` enthält die Grenzen des Gold-Bots. Sie ändern sich nur per Pull Request.
- `journal/strategie-suche-protokoll.md` enthält die Prüfsummen der Vorab-Regeln (`suche/VORAB_*.yaml`). Ein Bot
  prüft nur nach einer Regel, deren Prüfsumme dort steht.

## Einrichten

Repository-Secrets (Settings, Secrets and variables, Actions): `CAPITAL_API_KEY`, `CAPITAL_IDENTIFIER`,
`CAPITAL_API_PASSWORD`, dazu optional `TELEGRAM_BOT_TOKEN` und `TELEGRAM_CHAT_ID` für Meldungen.
Repository-Variable `GOLD_BOT_ENABLED` = `true`.

Lokal testen: `pip install -r requirements.txt` und dann `python -m pytest -q`.
