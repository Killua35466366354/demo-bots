"""Minutenkerzen von HistData.com laden und als 5-Minuten-Kerzen je Markt speichern (Strategie-Suche).

Usage (from the repo root):
    python -m suche.daten <zielordner> [SYMBOL ...]

Lädt je Markt die Jahresdateien 2015-2025 und die Monatsdateien 2026, rechnet die Zeit von EST ohne Sommerzeit
(UTC-5) auf UTC um und schreibt <zielordner>/<SYMBOL>_5min.csv.gz. Die ZIPs werden nach dem Umwandeln gelöscht.
HistData hat nur Bid-Kurse; der Spread kommt im Test aus suche/VORAB.yaml.
"""
from __future__ import annotations

import io
import pathlib
import re
import sys
import tempfile
import time
import zipfile

import pandas as pd
import requests

BASE = "https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes"
GET = "https://www.histdata.com/get.php"
YEARS = range(2015, 2026)
MONTHS_2026 = range(1, 11)
EST = pd.Timedelta(hours=5)


def parse_zip(blob: bytes) -> pd.DataFrame:
    """HistData Generic ASCII: `20240102 180000;2063.10;2064.53;2062.91;2064.40;0`, Zeit EST (UTC-5)."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        raw = pd.read_csv(z.open(name), sep=";", header=None, names=["t", "open", "high", "low", "close", "v"],
                          dtype={"t": str})
    idx = pd.to_datetime(raw["t"], format="%Y%m%d %H%M%S") + EST
    return pd.DataFrame(raw[["open", "high", "low", "close"]].to_numpy(float), index=pd.DatetimeIndex(idx, name="utc"),
                        columns=["open", "high", "low", "close"])


def to_bars(m1: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    m1 = m1[~m1.index.duplicated(keep="last")].sort_index()
    return m1.resample(rule, label="left", closed="left").agg(agg).dropna(subset=["open"])


def fetch(session: requests.Session, symbol: str, year: int, month: int | None = None, tries: int = 4) -> bytes | None:
    page = f"{BASE}/{symbol.lower()}/{year}" + (f"/{month}" if month else "")
    for k in range(tries):
        try:
            html = session.get(page, timeout=30).text
            tk = re.search(r'name="tk" id="tk" value="([^"]+)"', html)
            if not tk:
                return None
            form = {"tk": tk.group(1), "date": str(year), "datemonth": f"{year}{month:02d}" if month else str(year),
                    "platform": "ASCII", "timeframe": "M1", "fxpair": symbol.upper()}
            r = session.post(GET, data=form, headers={"Referer": page}, timeout=180)
            if r.ok and r.content[:2] == b"PK":
                return r.content
        except requests.RequestException:
            pass
        time.sleep(2 ** (k + 1))
    return None


def load_market(symbol: str, session: requests.Session | None = None) -> tuple[pd.DataFrame, list[str]]:
    session = session or requests.Session()
    parts, missing = [], []
    jobs = [(y, None) for y in YEARS] + [(2026, m) for m in MONTHS_2026]
    for year, month in jobs:
        blob = fetch(session, symbol, year, month)
        if blob is None:
            missing.append(f"{year}" + (f"-{month:02d}" if month else ""))
            continue
        parts.append(to_bars(parse_zip(blob), "5min"))
        time.sleep(1.0)
    bars = pd.concat(parts).sort_index() if parts else pd.DataFrame(columns=["open", "high", "low", "close"])
    return bars[~bars.index.duplicated(keep="last")], missing


def read_bars(path: str | pathlib.Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index.name = "utc"
    return df


def main(argv: list[str]) -> int:
    out = pathlib.Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    import yaml
    cfg = yaml.safe_load((pathlib.Path(__file__).parent / "VORAB.yaml").read_text(encoding="utf-8"))
    symbols = argv[1:] or [m["symbol"] for m in cfg["runde_1"]["maerkte"]]
    session = requests.Session()
    for sym in symbols:
        target = out / f"{sym}_5min.csv.gz"
        if target.exists():
            print(sym, "schon da", flush=True)
            continue
        bars, missing = load_market(sym, session)
        with tempfile.NamedTemporaryFile(dir=out, suffix=".tmp", delete=False) as tmp:
            bars.to_csv(tmp.name, compression="gzip", float_format="%.8g")
        pathlib.Path(tmp.name).replace(target)
        print(sym, len(bars), "Kerzen", bars.index[0] if len(bars) else "-", bars.index[-1] if len(bars) else "-",
              "fehlt:", missing or "nichts", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
