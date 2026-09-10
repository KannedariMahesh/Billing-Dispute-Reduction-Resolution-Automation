"""Adapter for the existing local context sources."""

from datetime import date
from pathlib import Path
import sys

SRC_ROOT = Path(__file__).resolve().parents[3] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from monitor import scan_for_anomalies  # noqa: E402


def scan_context(as_of: date) -> list[dict]:
    return scan_for_anomalies(as_of)
