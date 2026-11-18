"""Kunden-Stimmung (suche/stimmung.py): nur lesen und mitschreiben, nie eine Order, nie ein Fehler nach außen."""
import json
from datetime import datetime, timedelta, timezone

from gold.bot.capital import CapitalError
from suche import stimmung

JETZT = datetime(2026, 11, 18, 12, 16, tzinfo=timezone.utc)


class Client:
    """Antwortet auf /clientsentiment mit `alle` (oder wirft), auf /clientsentiment/<id> aus `einzeln`."""

    def __init__(self, alle=None, einzeln=None, login_fehler=None):
        self.alle, self.einzeln, self.login_fehler = alle, einzeln or {}, login_fehler
        self.calls, self.eingeloggt, self.ausgeloggt = [], False, False

    def login(self):
        if self.login_fehler:
            raise self.login_fehler
        self.eingeloggt = True

    def logout(self):
        self.ausgeloggt = True

    def _get(self, path, **params):
        self.calls.append((path, params))
        if path == "/clientsentiment":
            if isinstance(self.alle, Exception):
                raise self.alle
            return self.alle
        mid = path.rsplit("/", 1)[1]
        if mid not in self.einzeln:
            raise CapitalError(f"GET {path} -> 404: not found")
        return self.einzeln[mid]

    def __getattr__(self, name):            # jede andere Methode (Order, Kontowechsel) wäre ein Fehler
        raise AssertionError(f"stimmung darf {name} nie aufrufen")


def eintrag(mid, long):
    return {"marketId": mid, "longPositionPercentage": long, "shortPositionPercentage": round(100 - long, 2)}


def test_one_call_for_all_markets_writes_one_line(tmp_path):
    c = Client(alle={"clientSentiments": [eintrag(m, 50 + i) for i, m in enumerate(stimmung.MAERKTE)]})
    z = stimmung.lauf(c, JETZT, journal=tmp_path, schlaf=lambda s: None)
    assert [p for p, _ in c.calls] == ["/clientsentiment"]
    assert c.calls[0][1]["marketIds"] == ",".join(stimmung.MAERKTE)
    assert z["long"]["GOLD"] == 50 and z["long"]["USDJPY"] == 59 and z["fehlt"] == [] and z["fehler"] is None
    assert c.eingeloggt and c.ausgeloggt
    zeilen = stimmung.laden(tmp_path)
    assert zeilen == [z] and zeilen[0]["zeit"] == "2026-11-18T12:16Z"


def test_missing_markets_are_asked_one_by_one(tmp_path):
    c = Client(alle={"clientSentiments": [eintrag("GOLD", 71.4)]},
               einzeln={"US500": eintrag("US500", 45.2)})
    z = stimmung.lauf(c, JETZT, journal=tmp_path, schlaf=lambda s: None)
    assert z["long"] == {"GOLD": 71.4, "US500": 45.2}
    assert set(z["fehlt"]) == set(stimmung.MAERKTE) - {"GOLD", "US500"}
    assert "404" in z["fehler"]


def test_batch_error_falls_back_to_single_calls(tmp_path):
    c = Client(alle=CapitalError("GET /clientsentiment -> 404: error.not-found.marketId"),
               einzeln={m: eintrag(m, 60) for m in stimmung.MAERKTE})
    z = stimmung.lauf(c, JETZT, journal=tmp_path, schlaf=lambda s: None)
    assert len(z["long"]) == len(stimmung.MAERKTE) and z["fehlt"] == []
    assert z["fehler"].startswith("GET /clientsentiment -> 404")


def test_login_error_is_written_and_never_raised(tmp_path):
    c = Client(login_fehler=CapitalError("POST /session -> 401: error.invalid.details"))
    z = stimmung.lauf(c, JETZT, journal=tmp_path, schlaf=lambda s: None)
    assert z["long"] == {} and z["fehlt"] == list(stimmung.MAERKTE) and "401" in z["fehler"]
    assert stimmung.laden(tmp_path) == [z]


def test_second_run_within_ten_minutes_writes_nothing(tmp_path):
    c = Client(alle={"clientSentiments": [eintrag("GOLD", 70)]}, einzeln={})
    assert stimmung.lauf(c, JETZT, journal=tmp_path, schlaf=lambda s: None) is not None
    assert stimmung.lauf(c, JETZT + timedelta(minutes=9), journal=tmp_path, schlaf=lambda s: None) is None
    assert stimmung.lauf(c, JETZT + timedelta(minutes=15), journal=tmp_path, schlaf=lambda s: None) is not None
    assert len(stimmung.laden(tmp_path)) == 2


def test_dry_run_writes_nothing(tmp_path):
    c = Client(alle={"clientSentiments": [eintrag("GOLD", 70)]}, einzeln={})
    assert stimmung.lauf(c, JETZT, journal=tmp_path, trocken=True, schlaf=lambda s: None)["long"] == {"GOLD": 70}
    assert stimmung.laden(tmp_path) == []


def test_new_bot_market_from_vergleich_is_added(tmp_path):
    (tmp_path / "vergleich.json").write_text(json.dumps({"rangliste": [
        {"epic": "GOLD"}, {"epic": "Gold"}, {"epic": "OIL_BRENT"}, {"markt": "UK100"}, {"epic": None}]}),
        encoding="utf-8")
    assert stimmung.maerkte(tmp_path) == [*stimmung.MAERKTE, "OIL_BRENT", "UK100"]


def test_stimmung_bei_takes_the_last_line_before_entry_only():
    zeilen = [{"zeit": "2026-11-18T12:01Z", "long": {"GOLD": 70.0}},
              {"zeit": "2026-11-18T12:16Z", "long": {"GOLD": 72.0, "US500": 40.0}},
              {"zeit": "2026-11-18T12:31Z", "long": {"GOLD": 90.0}}]
    assert stimmung.stimmung_bei(zeilen, "GOLD", "2026-11-18T12:20:00Z") == 72.0
    assert stimmung.stimmung_bei(zeilen, "GOLD", datetime(2026, 11, 18, 12, 16, tzinfo=timezone.utc)) == 72.0
    assert stimmung.stimmung_bei(zeilen, "GOLD", "2026-11-18T12:00:00Z") is None          # nichts davor
    assert stimmung.stimmung_bei(zeilen, "US500", "2026-11-18T12:40:00Z") == 40.0
    assert stimmung.stimmung_bei(zeilen, "US500", "2026-11-18T12:47:00Z") is None         # älter als 30 Minuten
    assert stimmung.stimmung_bei(zeilen, "GOLD", "kaputt") is None


def test_main_without_credentials_is_quiet(monkeypatch, capsys):
    for k in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_API_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    assert stimmung.main([]) == 0
    assert "übersprungen" in capsys.readouterr().out
