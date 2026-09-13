from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class AuditRepository:
    def __init__(self, path: Path):
        self.path = path

    def save(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    def list(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def get(self, correlation_id: str) -> dict[str, Any] | None:
        return next((record for record in self.list() if record.get("correlation_id") == correlation_id), None)
