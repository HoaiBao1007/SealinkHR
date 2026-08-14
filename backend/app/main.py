from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

os.makedirs("uploads", exist_ok=True)


from app.api.dashboard import router as dashboard_router
from app.api.employees import router as employees_router
from app.api.departments import router as departments_router
from app.api.export import router as export_router
from app.api.importer import router as importer_router
from app.api.import_checkin_commit import router as import_checkin_commit_router
from app.api.override import router as override_router
from app.api.timesheet import router as timesheet_router
from app.api.salary_api import router as salary_router
from app.api.auth import router as auth_router
from app.api.user_portal import router as user_portal_router
from app.api.commission_api import router as commission_router
from app.api.holidays import router as holidays_router
from app.api.organization import router as organization_router
from app.api.hr_api import router as hr_router
from app.api.it_api import router as it_router
from app.api.role_dashboard import router as role_dashboard_router
from app.api.access_api import router as access_router
from app.api.notifications import router as notifications_router
from app.api.time_off import router as time_off_router
from app.core.settings import settings
from app.middleware.audit import audit_mutating_request

app = FastAPI(title=settings.app_name, version="0.1.0")

origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(audit_mutating_request)

app.include_router(auth_router)
app.include_router(user_portal_router)
app.include_router(importer_router, prefix="/api")
app.include_router(import_checkin_commit_router)
app.include_router(timesheet_router)
app.include_router(salary_router)
app.include_router(dashboard_router)
app.include_router(employees_router)
app.include_router(departments_router)
app.include_router(override_router)
app.include_router(export_router)
app.include_router(commission_router)
app.include_router(holidays_router)
app.include_router(organization_router)
app.include_router(hr_router)
app.include_router(it_router)
app.include_router(role_dashboard_router)
app.include_router(access_router)
app.include_router(notifications_router)
app.include_router(time_off_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    print("❌ FastAPI Validation Error:", exc.errors())
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )

