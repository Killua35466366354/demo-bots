"""Adapter für die Capital.com Open API (REST).

Doku: https://open-api.capital.com/
- Anmeldung: POST /session mit Header X-CAP-API-KEY, Login (`identifier`) und dem eigenen Passwort
  des API-Schlüssels. Die Antwort trägt die Tokens CST und X-SECURITY-TOKEN im Header, sie gelten
  10 Minuten nach der letzten Nutzung.
- Eine Order (POST /positions) liefert nur eine dealReference. Ob sie wirklich ausgeführt wurde,
  steht erst in GET /confirms/{dealReference}.
- Order- und Schließ-Aufrufe werden nie automatisch wiederholt, damit keine Position doppelt entsteht.
- Mehrere Konten (Kirons Wunsch vom 03.11.2026: jeder Bot ein eigenes Demokonto): GET /accounts listet alle Konten
  des Logins, PUT /session {"accountId"} wechselt das aktive Konto dieser Sitzung. Orders, Positionen und
  Kontoaktivität gelten immer für das aktive Konto. Nach dem Login ist das bevorzugte Konto aktiv
  (`currentAccountId` in der Antwort).
"""

from __future__ import annotations

from datetime import datetime

import requests

BASE_URLS = {
    "demo": "https://demo-api-capital.backend-capital.com/api/v1",
    "live": "https://api-capital.backend-capital.com/api/v1",
}


class CapitalError(RuntimeError):
    pass


class CapitalClient:
    def __init__(
        self,
        api_key: str,
        identifier: str,
        password: str,
        environment: str = "demo",
        allow_live: bool = False,
        session: requests.Session | None = None,
        timeout: float = 20,
    ):
        if environment not in BASE_URLS:
            raise ValueError(f"Unbekannte Umgebung {environment}")
        if environment == "live" and not allow_live:
            raise PermissionError("Live-Handel ist gesperrt. Erst nach bestandener Demo und mit Kirons Bestätigung.")
        self.environment = environment
        self.base_url = BASE_URLS[environment]
        self.session = session or requests.Session()
        self.timeout = timeout
        self._login = {"identifier": identifier, "password": password, "encryptedPassword": False}
        self._api_key = api_key
        self._tokens: dict[str, str] = {}
        self.account_id: str | None = None       # aktives Konto dieser Sitzung

    def _request(self, method: str, path: str, **kwargs):
        headers = {**self._tokens, **kwargs.pop("headers", {})}
        response = self.session.request(method, self.base_url + path, headers=headers, timeout=self.timeout, **kwargs)
        if response.status_code == 429:
            raise CapitalError(f"Rate-Limit erreicht für {path}")
        if not response.ok:
            raise CapitalError(f"{method} {path} -> {response.status_code}: {response.text[:300]}")
        return response

    def login(self) -> dict:
        response = self._request("POST", "/session", json=self._login, headers={"X-CAP-API-KEY": self._api_key})
        cst, token = response.headers.get("CST"), response.headers.get("X-SECURITY-TOKEN")
        if not (cst and token):
            raise CapitalError("Anmeldung ohne CST oder X-SECURITY-TOKEN in der Antwort")
        self._tokens = {"CST": cst, "X-SECURITY-TOKEN": token}
        data = response.json()
        self.account_id = data.get("currentAccountId")
        return data

    def switch_account(self, account_id: str) -> None:
        """Macht `account_id` zum aktiven Konto dieser Sitzung (PUT /session). Tut nichts, wenn es schon aktiv ist:
        Capital.com lehnt den Wechsel auf das aktive Konto mit 400 ab. Neue Tokens in der Antwort gelten ab sofort."""
        if not account_id or account_id == self.account_id:
            return
        response = self._request("PUT", "/session", json={"accountId": account_id})
        for key in ("CST", "X-SECURITY-TOKEN"):
            if response.headers.get(key):
                self._tokens[key] = response.headers[key]
        self.account_id = account_id

    def logout(self) -> None:
        self._request("DELETE", "/session")
        self._tokens = {}
        self.account_id = None

    def _get(self, path: str, **params) -> dict:
        return self._request("GET", path, params=params or None).json()

    def accounts(self) -> list[dict]:
        return self._get("/accounts").get("accounts", [])

    def positions(self) -> list[dict]:
        return self._get("/positions").get("positions", [])

    def market(self, epic: str) -> dict:
        return self._get(f"/markets/{epic}")

    def prices(self, epic: str, resolution: str = "HOUR", max_bars: int = 1000) -> list[dict]:
        return self._get(f"/prices/{epic}", resolution=resolution, max=max_bars).get("prices", [])

    def activity(self, deal_id: str, since: datetime, until: datetime) -> list[dict]:
        """Kontoaktivität zu einem Deal, z. B. wenn der Stop beim Broker ausgelöst hat (nur lesen)."""
        fmt = "%Y-%m-%dT%H:%M:%S"
        params = {"dealId": deal_id, "detailed": "true", "from": since.strftime(fmt), "to": until.strftime(fmt)}
        return self._get("/history/activity", **params).get("activities", [])

    def confirm(self, deal_reference: str) -> dict:
        return self._get(f"/confirms/{deal_reference}")

    def open_position(self, epic: str, direction: str, size: float, stop_level: float | None = None) -> dict:
        if direction not in ("BUY", "SELL"):
            raise ValueError(f"Richtung {direction} gibt es nicht")
        body = {"epic": epic, "direction": direction, "size": size, "guaranteedStop": False}
        if stop_level is not None:
            body["stopLevel"] = round(stop_level, 2)
        ref = self._request("POST", "/positions", json=body).json()["dealReference"]
        return self.confirm(ref)

    def close_position(self, deal_id: str) -> dict:
        ref = self._request("DELETE", f"/positions/{deal_id}").json()["dealReference"]
        return self.confirm(ref)
