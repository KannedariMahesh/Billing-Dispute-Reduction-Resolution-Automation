from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    correlation_id: str
    timestamp: datetime
    customer_id: str
    anomaly: dict[str, Any]
    stage1: dict[str, Any]
    sources_queried: list[str]
    stage2: dict[str, Any]
    final_action: str
