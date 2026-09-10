from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class CaseRequest(BaseModel):
    customer_id: str = Field(min_length=1)
    anomaly_type: Literal["usage_anomaly", "recurring_anomaly"]
    delta_gbp: float
    detected_at: date
    contributing_events: list[dict] = Field(default_factory=list)


class AnomalyScanResponse(BaseModel):
    as_of: date
    cases: list[CaseRequest]
