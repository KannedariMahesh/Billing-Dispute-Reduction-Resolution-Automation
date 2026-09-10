from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

from ..audit.service import AuditService
from ..context.client import scan_context
from ..context.models import AnomalyScanResponse, CaseRequest

SRC_ROOT = Path(__file__).resolve().parents[3] / "src"
if str(SRC_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(SRC_ROOT))

from orchestrator import run_case  # noqa: E402

router = APIRouter(prefix="/api/v1")


def audit_service(request: Request) -> AuditService:
    return request.app.state.audit_service


@router.get("/anomalies", response_model=AnomalyScanResponse)
def anomalies(as_of: date = Query(..., description="Evaluation date in YYYY-MM-DD format")):
    cases = [CaseRequest.model_validate(case) for case in scan_context(as_of)]
    return AnomalyScanResponse(as_of=as_of, cases=cases)


@router.post("/cases", status_code=201)
def process_case(case: CaseRequest, request: Request):
    record = run_case(case.model_dump(mode="json"))
    record["correlation_id"] = request.state.correlation_id
    return audit_service(request).record(record)


@router.get("/audits")
def list_audits(request: Request):
    return audit_service(request).list_records()


@router.get("/audits/{correlation_id}")
def get_audit(correlation_id: str, request: Request):
    record = audit_service(request).get_record(correlation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Audit record not found")
    return record
