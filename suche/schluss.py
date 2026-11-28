"""Belegt den Schluss einer Position zum Markt, bevor ein Bot ihn bucht.

Am 27.11.2026 um 20:46 UTC schloss das Vorhersage-Modell seinen US500-Kauf zur Ausstiegszeit. Capital.com bestätigte den
Schluss ohne "REJECTED" und mit dem Kurs 0,24, die Position lag aber weiter offen. Der Bot buchte -19,69 R statt etwa
+0,2 R, hielt die Position im nächsten Lauf für fremd und führte sie nicht mehr. Dieselbe Buchung ohne Prüfung hatten
der Tag nach einem VIX-Sprung, Williams %R, der 4-Std.-Ausbruch auf DAX, FTSE, Nikkei und auf Bitcoin, Ether, Bollinger
Krypto und die drei Kopierer in suche/buendel_bot.py.

Darum gilt ein Schluss erst als belegt, wenn die Position nicht mehr in der Liste des Kontos steht und der bestätigte Kurs
höchstens einen Stop-Abstand vom Kurs des Laufs entfernt liegt. Sonst bucht der Bot nichts. Liegt die Position noch da,
schließt er sie im nächsten Lauf wieder nach seinen Regeln. Ist sie weg, liest er den Schlusskurs wie nach einem Stop aus
der Kontoaktivität. Dieser Teil sendet nichts an den Broker, er liest nur die Positionen."""

from __future__ import annotations


def _num(x) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def noch_offen(client, deal_id: str) -> bool | None:
    """Steht die Position noch in der Liste des aktiven Kontos? None, wenn die Liste nicht lesbar ist."""
    try:
        alle = client.positions()
    except Exception as err:                # noqa: BLE001 - dann zählt nur der Kurs
        print(f"Positionen nach dem Schluss nicht lesbar: {err}")
        return None
    return any(str((x.get("position") or {}).get("dealId")) == str(deal_id) for x in alle or [])


def belegt(client, conf: dict | None, deal_id: str, kurs: float | None,
           abstand: float | None) -> tuple[float | None, dict]:
    """(Schlusskurs, {}) für einen belegten Schluss, sonst (None, Angaben fürs Log). `kurs` ist der Kurs des Laufs, zu
    dem die Position zum Markt schließt (Kauf am Bid, Verkauf am Ask), `abstand` der Stop-Abstand des Trades. Ohne Kurs
    in der Bestätigung gilt `kurs`. Ohne `kurs` zählt nur, ob die Position weg ist."""
    level, kurs, abstand = _num((conf or {}).get("level")), _num(kurs), _num(abstand)
    offen = noch_offen(client, deal_id)
    weit = level is not None and kurs is not None and abstand is not None and abs(level - kurs) > abs(abstand)
    schluss = kurs if level is None else level
    if offen or weit or schluss is None:
        return None, {"kurs_bestaetigt": level, "kurs_lauf": kurs, "noch_offen": offen}
    return schluss, {}
