from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from shifttracker.config import Settings

# Templates for auth pages (login does not use base.html sidebar)
_templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

auth_router = APIRouter(tags=["auth"])


def require_session(request: Request) -> str:
    """FastAPI dependency: enforces admin session. Redirects to /admin/login if not authenticated."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})
    return user


@auth_router.get("/login")
async def login_get(request: Request):
    # Starlette 1.x: request is first arg, context is second
    return _templates.TemplateResponse(request, "login.html")


@auth_router.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    settings = Settings()
    if username == settings.admin_username and password == settings.admin_password:
        request.session["user"] = username
        return RedirectResponse("/admin/", status_code=303)
    return _templates.TemplateResponse(
        request,
        "login.html",
        {"error": "Invalid credentials"},
        status_code=200,
    )


@auth_router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)
