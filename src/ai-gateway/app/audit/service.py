from __future__ import annotations

from typing import Any

from .repository import AuditRepository


class AuditService:
    def __init__(self, repository: AuditRepository):
        self.repository = repository

    def record(self, audit_record: dict[str, Any]) -> dict[str, Any]:
        self.repository.save(audit_record)
        return audit_record

    def list_records(self) -> list[dict[str, Any]]:
        return self.repository.list()

    def get_record(self, correlation_id: str) -> dict[str, Any] | None:
        return self.repository.get(correlation_id)
