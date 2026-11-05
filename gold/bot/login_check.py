"""Nur prüfen, ob Capital.com den Login annimmt: anmelden und sofort wieder abmelden. Keine Kurse, keine
Position, keine Order.

    python -m gold.bot.login_check demo
    python -m gold.bot.login_check live   # nur nach Kirons Ja

Hilft beim Fehler 401 error.invalid.details: klappt live und scheitert demo, fehlt das Demokonto. Scheitern
beide, passen Passwort oder E-Mail nicht zum Schlüssel.
"""

from __future__ import annotations

import os
import sys

from gold.bot.capital import CapitalClient, CapitalError
from gold.bot.runner import CRED_KEYS, clean_credentials


def check(client: CapitalClient) -> bool:
    try:
        client.login()
    except CapitalError as err:
        print(f"{client.environment}: Login abgelehnt ({err})")
        return False
    client.logout()
    print(f"{client.environment}: Login klappt, gleich wieder abgemeldet")
    return True


def main(argv: list[str]) -> int:
    environment = argv[0] if argv else "demo"
    if environment not in ("demo", "live"):
        print(f"Unbekannte Umgebung {environment}, nur demo oder live")
        return 2
    creds = clean_credentials({k: os.environ.get(k, "") for k in CRED_KEYS})
    if not all(creds):
        print("Keine Capital.com-Zugangsdaten in der Umgebung")
        return 2
    # Live nur für diesen einen Login; der Client wird nirgends weitergegeben, Order-Aufrufe gibt es hier nicht.
    client = CapitalClient(*creds, environment=environment, allow_live=environment == "live")
    return 0 if check(client) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
