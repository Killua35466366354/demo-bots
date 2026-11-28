"""Ein Schluss zum Markt zählt erst, wenn die Position weg ist und der Kurs passt (suche/schluss.py)."""

from __future__ import annotations

import inspect

import pytest

from suche import schluss


class Konto:
    def __init__(self, deals=(), fehler=False):
        self.deals, self.fehler = list(deals), fehler

    def positions(self):
        if self.fehler:
            raise RuntimeError("Zeitüberschreitung")
        return [{"market": {"epic": "US500"}, "position": {"dealId": d}} for d in self.deals]


def test_belegt_nur_wenn_die_position_weg_ist_und_der_kurs_passt():
    assert schluss.belegt(Konto(), {"dealStatus": "ACCEPTED", "level": 7296.0}, "D1", 7295.5, 367.3) == (7296.0, {})
    assert schluss.belegt(Konto(), {"dealStatus": "ACCEPTED"}, "D1", 7295.5, 367.3) == (7295.5, {})   # ohne Kurs
    level, info = schluss.belegt(Konto(["D1"]), {"level": 7296.0}, "D1", 7295.5, 367.3)               # noch offen
    assert level is None and info["noch_offen"] is True
    level, info = schluss.belegt(Konto(), {"level": 0.24}, "D1", 7296.0, 367.3)                       # 27.11.2026
    assert level is None and info == {"kurs_bestaetigt": 0.24, "kurs_lauf": 7296.0, "noch_offen": False}
    assert schluss.belegt(Konto(["D2"]), {"level": 7000.0}, "D1", 7296.0, 367.3) == (7000.0, {})     # 296 < 367


def test_ohne_liste_der_positionen_zaehlt_der_kurs():
    assert schluss.belegt(Konto(fehler=True), {"level": 7296.0}, "D1", 7295.5, 367.3) == (7296.0, {})
    level, info = schluss.belegt(Konto(fehler=True), {"level": 0.24}, "D1", 7296.0, 367.3)
    assert level is None and info["noch_offen"] is None


def test_ohne_kurs_des_laufs_zaehlt_nur_die_liste():
    assert schluss.belegt(Konto(), {"level": 0.24}, "D1", None, None) == (0.24, {})
    assert schluss.belegt(Konto(), {}, "D1", None, 5.0)[0] is None                     # gar kein Kurs: nichts buchen
    assert schluss.belegt(Konto(["D1"]), {"level": 7296.0}, "D1", None, None)[0] is None


@pytest.mark.parametrize("name", ["modell_indizes_bot", "vix_sprung_bot", "williams_bot", "krypto4h_bot",
                                  "welt4h_bot", "krypto_bollinger_bot", "buendel_bot"])
def test_jeder_bot_bucht_den_schluss_nur_mit_beleg(name):
    modul = __import__(f"suche.{name}", fromlist=["x"])
    quelle = inspect.getsource(modul.Lauf.schliesse)
    assert "belegt_pruefung.belegt(" in quelle and '"Schluss nicht belegt"' in quelle
