from fastapi import FastAPI

from .api.routes import router
from .audit.repository import AuditRepository
from .audit.service import AuditService
from .config import settings
from .middleware.audit import AuditRequestMiddleware
from .middleware.correlation import CorrelationMiddleware

app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(CorrelationMiddleware)
app.add_middleware(AuditRequestMiddleware)
app.state.audit_service = AuditService(AuditRepository(settings.audit_log_path))
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.app_name}
