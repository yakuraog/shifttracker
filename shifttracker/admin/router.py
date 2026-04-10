from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.templating import Jinja2Templates

from shifttracker.admin.auth import auth_router, require_session
from shifttracker.admin.routers import dashboard
from shifttracker.admin.routers import review

# Absolute path resolution to avoid CWD-relative template loading issues
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

admin_router = APIRouter()

# Auth routes: /admin/login, /admin/logout (no session required)
admin_router.include_router(auth_router)

# Dashboard: /admin/ (requires session)
admin_router.include_router(
    dashboard.router,
    dependencies=[Depends(require_session)],
)

# Review queue: /admin/review/ (requires session)
admin_router.include_router(
    review.router,
    dependencies=[Depends(require_session)],
)
