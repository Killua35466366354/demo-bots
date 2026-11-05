"""Benachrichtigungen. Ohne Telegram-Zugang wird nur ins Log geschrieben.

Mit `log_path` landet jede Meldung zusätzlich in einer Datei im Journal (journal/hinweise.jsonl). Seit 05.11.2026:
Die Telegram-Secrets sind leer, jede Warnung stand bis dahin nur im GitHub-Log, das niemand liest. Die Datei geht mit
dem Journal ins Repo, Claude und das Cockpit können sie lesen.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

KEEP_NOTES = 300  # so viele Meldungen bleiben in der Datei, ältere fallen heraus


class Notifier:
    def __init__(self, token: str | None = None, chat_id: str | None = None, log_path: Path | str | None = None):
        self.token = token if token is not None else os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id if chat_id is not None else os.environ.get("TELEGRAM_CHAT_ID")
        self.log_path = Path(log_path) if log_path else None
        self.sent: list[str] = []

    def __call__(self, text: str) -> None:
        self.sent.append(text)
        print(f"[Hinweis] {text}")
        if self.log_path is not None:
            self._log(text)
        if not (self.token and self.chat_id):
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": text},
                timeout=10,
            ).raise_for_status()
        except requests.RequestException as exc:
            # Eine fehlende Nachricht darf den Lauf nicht abbrechen, sie steht trotzdem im Journal.
            print(f"[Warnung] Telegram nicht erreichbar: {exc}")

    def _log(self, text: str) -> None:
        """Meldung anhängen, nur die letzten KEEP_NOTES behalten. Ein Fehler hier bricht keinen Lauf ab."""
        row = {"zeit": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "text": text}
        try:
            lines = self.log_path.read_text(encoding="utf-8").splitlines() if self.log_path.exists() else []
            lines.append(json.dumps(row, ensure_ascii=False))
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.write_text("\n".join(lines[-KEEP_NOTES:]) + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"[Warnung] Hinweis-Datei nicht schreibbar: {exc}")
