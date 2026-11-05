"""Kiron's rule: the Pine code stays exactly as it is in TradingView. This test fails on any change."""
import hashlib
import pathlib
import re

STRATEGIES = pathlib.Path(__file__).resolve().parents[1] / "gold" / "strategies"


def normalised_sha256(path):
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n")).strip() + "\n"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_original_strategies_match_recorded_checksums():
    recorded = dict(re.findall(r"\| (\S+\.pine) \| \d+ \| ([0-9a-f]{64}) \|",
                               (STRATEGIES / "CHECKSUMS.md").read_text(encoding="utf-8")))
    assert len(recorded) == 3
    for name, digest in recorded.items():
        assert normalised_sha256(STRATEGIES / name) == digest, f"{name} was changed"
