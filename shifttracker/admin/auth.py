from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from shifttracker.config import Settings

# Templates for auth pages (login does not use base.html sidebar)
_templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

auth_router = APIRouter(tags=["auth"])


def require_session(request: Request) -> str:
    """FastAPI dependency: enforces admin session. Redirects to /admin/login if not authenticated."""
    user = request.session.get("user")
    if not user:
        response = RedirectResponse("/admin/login", status_code=303)
        raise _AuthRedirect(response)
    return user


class _AuthRedirect(Exception):
    """Internal exception to carry a redirect response through the dependency system."""

    def __init__(self, response: RedirectResponse):
        self.response = response


# Override require_session to use HTTPException approach compatible with FastAPI Depends
from fastapi import HTTPException
from starlette.responses import Response


def require_session(request: Request) -> str:  # noqa: F811
    """FastAPI dependency: enforces admin session. Redirects to /admin/login if not authenticated."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})
    return user


@auth_router.get("/login")
async def login_get(request: Request):
    return _templates.TemplateResponse("login.html", {"request": request})


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
        "login.html",
        {"request": request, "error": "Invalid credentials"},
        status_code=200,
    )


@auth_router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)
