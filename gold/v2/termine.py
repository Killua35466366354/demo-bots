"""Angekündigte US-Termine (Fed, Inflation, Arbeitsmarkt) aus gold/v2/termine.yaml als UTC-Zeitpunkte."""
from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yaml

TERMINE = Path(__file__).resolve().parent / "termine.yaml"
ARTEN = ("fomc", "cpi", "nfp")


def load(path: Path | str = TERMINE) -> pd.DataFrame:
    """Eine Zeile je Termin: utc (naiv, UTC), art. Sortiert."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    tz = ZoneInfo(raw.get("zeitzone", "America/New_York"))
    rows = []
    for art in ARTEN:
        hh, mm = (int(x) for x in raw[art]["uhrzeit"].split(":"))
        for tag in raw[art]["tage"]:
            d = tag if isinstance(tag, date) else date.fromisoformat(str(tag))
            local = datetime.combine(d, time(hh, mm), tzinfo=tz)
            rows.append({"utc": pd.Timestamp(local).tz_convert("UTC").tz_localize(None), "art": art})
    return pd.DataFrame(rows).sort_values("utc").reset_index(drop=True)


def last_date(events: pd.DataFrame, art: str | None = None) -> pd.Timestamp | None:
    ev = events if art is None else events[events["art"] == art]
    return ev["utc"].max() if len(ev) else None
