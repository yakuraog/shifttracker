---
phase: 03-admin-interface
plan: "01"
subsystem: admin
tags: [admin, auth, templates, fastapi, jinja2, bootstrap, htmx, session]
dependency_graph:
  requires:
    - shifttracker/config.py
    - shifttracker/db/engine.py
    - shifttracker/db/models.py
    - shifttracker/app.py
  provides:
    - shifttracker/admin/auth.py (require_session, login/logout handlers)
    - shifttracker/admin/deps.py (get_db async session dependency)
    - shifttracker/admin/router.py (admin_router, templates instance)
    - shifttracker/templates/base.html (Bootstrap 5 sidebar layout)
    - tests/conftest.py (test_client fixture with SessionMiddleware)
  affects:
    - All subsequent admin plans (02-04) use require_session, get_db, templates, test_client
tech_stack:
  added:
    - starlette.middleware.sessions.SessionMiddleware (session cookie auth)
    - fastapi.templating.Jinja2Templates (Starlette 1.x API: request as first arg)
    - Bootstrap 5.3.3 CDN (CSS + JS bundle)
    - htmx 2.0.4 CDN (unpkg)
  patterns:
    - HTTPException(status_code=303) for redirect-as-auth-guard from Depends
    - Minimal test app pattern (no lifespan) for synchronous TestClient
    - Starlette 1.x TemplateResponse(request, name, context) signature
key_files:
  created:
    - shifttracker/admin/__init__.py
    - shifttracker/admin/auth.py
    - shifttracker/admin/deps.py
    - shifttracker/admin/router.py
    - shifttracker/admin/routers/__init__.py
    - shifttracker/admin/routers/dashboard.py
    - shifttracker/templates/base.html
    - shifttracker/templates/login.html
    - shifttracker/templates/admin/dashboard.html
    - tests/test_admin_auth.py
  modified:
    - shifttracker/config.py (added admin_username, admin_password, secret_key)
    - shifttracker/db/models.py (added relationship() on Employee, TelegramGroup, GroupEmployee, CaptionRule)
    - shifttracker/app.py (added SessionMiddleware + admin_router)
    - tests/conftest.py (added test_client fixture)
decisions:
  - "Starlette 1.0 TemplateResponse takes request as first positional arg, not inside context dict — updated all TemplateResponse calls"
  - "test_client builds minimal FastAPI app without lifespan to skip bot/workers startup"
  - "require_session raises HTTPException(303) with Location header — FastAPI converts this to redirect response"
  - "Dashboard stats use datetime.combine() not func.date() for cross-db SQLite/PostgreSQL compatibility"
metrics:
  duration_minutes: 4
  completed_date: "2026-04-10"
  tasks_completed: 2
  files_created: 10
  files_modified: 4
---

# Phase 03 Plan 01: Admin Interface Foundation Summary

**One-liner:** Bootstrap 5 + htmx admin interface with session-based auth, dashboard stats, and test_client fixture built on Starlette 1.x API.

## Tasks Completed

| # | Task | Commit | Status |
|---|------|--------|--------|
| 1 (TDD RED) | Failing tests for admin auth | 3816b65 | Done |
| 1 (TDD GREEN) | Config, auth module, deps, model relationships, base templates | dc71ad6 | Done |
| 2 | Wire admin router into app.py, conftest test_client, fix Starlette 1.x API | bdedb03 | Done |

## What Was Built

- **Auth system:** `require_session` Depends-compatible guard that raises HTTPException(303) to redirect unauthenticated requests to /admin/login. Login/logout handlers using Starlette SessionMiddleware cookie sessions.
- **Admin package:** `shifttracker/admin/` with auth, deps (get_db), router (admin_router + templates), and dashboard sub-router.
- **Dashboard:** Queries ProcessingLog for today's accepted/pending/error counts using `datetime.combine()` for cross-database compatibility.
- **Templates:** Bootstrap 5.3.3 sidebar layout (base.html), standalone login page, dashboard with stat cards.
- **Test infrastructure:** `test_client` fixture in conftest creates a minimal FastAPI test app (no lifespan) with in-memory SQLite, enabling synchronous TestClient testing.

## Test Results

```
6 passed in tests/test_admin_auth.py
93 passed total (all existing tests still pass)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed Starlette 1.x TemplateResponse API**
- **Found during:** Task 2 (first test run)
- **Issue:** Starlette 1.0.0 changed `TemplateResponse` signature — `request` is now the first positional argument, not a key inside the context dict. Caused `TypeError: unhashable type: 'dict'` in Jinja2 LRUCache.
- **Fix:** Updated all `TemplateResponse` calls in auth.py and dashboard.py to `TemplateResponse(request, "template.html", {context})`.
- **Files modified:** shifttracker/admin/auth.py, shifttracker/admin/routers/dashboard.py
- **Commit:** bdedb03

**2. [Rule 3 - Blocking] Cleaned up duplicate require_session definition**
- **Found during:** Task 1 implementation
- **Issue:** auth.py draft had two definitions of `require_session` (leftover from drafting). Consolidated to single clean definition.
- **Fix:** Removed the first stub definition, kept the HTTPException-based version.
- **Files modified:** shifttracker/admin/auth.py
- **Commit:** dc71ad6

## Self-Check: PASSED

All created files exist. All task commits verified.

| Check | Result |
|-------|--------|
| shifttracker/admin/auth.py | FOUND |
| shifttracker/admin/deps.py | FOUND |
| shifttracker/admin/router.py | FOUND |
| shifttracker/templates/base.html | FOUND |
| shifttracker/templates/login.html | FOUND |
| shifttracker/templates/admin/dashboard.html | FOUND |
| tests/test_admin_auth.py | FOUND |
| Commit 3816b65 | FOUND |
| Commit dc71ad6 | FOUND |
| Commit bdedb03 | FOUND |
