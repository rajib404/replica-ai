"""Admin dashboard routers.

Aggregates all admin sub-routers under a single ``admin_router``
mounted at ``/api/admin`` from ``app/main.py``.
"""

from fastapi import APIRouter

from app.routers.admin import (
    analytics,
    auth,
    health,
    logs,
    maintenance,
    overview,
    owners,
    rules,
)

admin_router = APIRouter(prefix="/api/admin", tags=["admin"])
admin_router.include_router(auth.router)
admin_router.include_router(overview.router)
admin_router.include_router(owners.router)
admin_router.include_router(health.router)
admin_router.include_router(logs.router)
admin_router.include_router(rules.router)
admin_router.include_router(analytics.router)
admin_router.include_router(maintenance.router)
