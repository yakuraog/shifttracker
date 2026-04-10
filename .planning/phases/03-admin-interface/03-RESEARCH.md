# Phase 3: Admin Interface - Research

**Researched:** 2026-04-10
**Domain:** FastAPI + Jinja2 server-rendered admin UI, htmx, session auth, async SQLAlchemy CRUD
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Technology Choice — Server-Rendered HTML**
- FastAPI + Jinja2 templates (no SPA framework — keep it simple for a test assignment)
- Bootstrap 5 CDN for styling (fast, professional, no build step)
- htmx for interactive elements (AJAX without JS complexity)
- All templates rendered server-side, minimal JavaScript
- No separate frontend build process — templates live in `shifttracker/templates/`

**Authentication**
- Simple token-based auth (API key in header or session cookie)
- Admin credentials configured via environment variables (ADMIN_USERNAME, ADMIN_PASSWORD)
- Login page with session cookie for web UI
- API endpoints require Bearer token or valid session
- No OAuth, no JWT — simple and sufficient for v1

**Admin CRUD (ADMIN-01..05)**
- Groups management: list, add, edit (name, chat_id, sheet_id, shift hours, timezone), delete
- Employees management: list, add, edit (name, telegram_user_id, employee_code), delete
- Group-employee bindings: assign/unassign employees to groups, set sheet_row
- Caption rules: list, add, edit (group, pattern, employee), delete
- Shift time windows: configured per group (shift_start_hour, shift_end_hour) — part of group edit form

**Manual Review Queue (REVIEW-01..04)**
- List all processing_log entries with status NEEDS_REVIEW
- Each entry shows: employee name (if identified), group name, timestamp, caption text, source link
- Approve action: creates ShiftRecord with status ACCEPTED, triggers Sheets write
- Reject action: updates processing_log status to REJECTED with operator comment
- Filter by group, date range
- Sort by newest first

**Shift Table View (ADMIN-07)**
- Grid view: employees as rows, dates as columns, "1" marks
- Filter by group/object, date range
- Click on "1" to see source message link and processing details
- History: show processing_log entries for a specific employee + date

**Web Interface Layout (ADMIN-06)**
- Sidebar navigation: Dashboard, Groups, Employees, Caption Rules, Review Queue, Shift Table
- Dashboard: summary stats (total processed today, pending review count, errors count)
- Responsive layout (Bootstrap grid)

### Claude's Discretion
- Exact HTML/CSS template design
- Table pagination approach
- Form validation UX
- Dashboard chart/stat presentation
- Error page design

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope

</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| REVIEW-01 | Спорные случаи отображаются в очереди ручной проверки для оператора | ProcessingLog query WHERE status='NEEDS_REVIEW'; Jinja2 table template with htmx filter |
| REVIEW-02 | Оператор может подтвердить или отклонить отметку из очереди | htmx hx-post approve/reject endpoints; partial template swap for row removal |
| REVIEW-03 | После подтверждения оператором система ставит "1" в таблицу смен | POST /admin/review/{id}/approve creates ShiftRecord status=ACCEPTED with sheet_write_status=PENDING; SheetsWriter picks it up automatically |
| REVIEW-04 | После отклонения оператором запись помечается как отклоненная с комментарием | POST /admin/review/{id}/reject sets ProcessingLog.status=REJECTED and saves operator comment |
| ADMIN-01 | Администратор управляет списком подключенных Telegram-групп | TelegramGroup CRUD: list/add/edit/delete via Jinja2 forms + htmx |
| ADMIN-02 | Администратор управляет справочником сотрудников (CRUD) | Employee CRUD: list/add/edit/delete; also manage GroupEmployee bindings (assign to groups, set sheet_row) |
| ADMIN-03 | Администратор настраивает правила привязки групп к сотрудникам и объектам | GroupEmployee table: assign/unassign employees to groups, set sheet_row |
| ADMIN-04 | Администратор настраивает допустимые временные окна подтверждения смены | shift_start_hour/shift_end_hour fields on TelegramGroup edit form (already in model) |
| ADMIN-05 | Администратор настраивает правила идентификации (шаблоны подписей, привязки аккаунтов) | CaptionRule CRUD: pattern + employee_id + group_id; telegram_user_id on Employee edit |
| ADMIN-06 | Веб-интерфейс для всех функций администрирования | Sidebar layout template (base.html); all CRUD pages use template inheritance |
| ADMIN-07 | Руководитель может просматривать итоговую таблицу и отчетность по выходам на смену | Shift grid: query ShiftRecord JOIN Employee filtered by group+date range; render as HTML table |

</phase_requirements>

---

## Summary

Phase 3 adds a complete web admin interface on top of the existing FastAPI app. The stack is already chosen and justified: FastAPI + Jinja2 server-side rendering, Bootstrap 5 from CDN, htmx for partial page updates. No new Python packages are required beyond `itsdangerous` (already installed as a transitive dependency of Starlette) — everything needed is already in the virtualenv.

The key architectural pattern is standard FastAPI router organization: one `APIRouter` per section (`/admin/groups`, `/admin/employees`, `/admin/review`, `/admin/shifts`), all mounted under a `/admin` prefix with a session-auth dependency. Templates use Jinja2 inheritance from a `base.html` layout with Bootstrap 5 sidebar. Interactive actions (approve/reject review queue items, delete records, filter tables) use htmx `hx-post`/`hx-get` attributes that swap partial HTML fragments without full page reload.

The review queue approve action has a critical integration point: it must create a `ShiftRecord` with `sheet_write_status='PENDING'` so the existing `SheetsWriter` background task picks it up automatically. No direct Sheets API call is needed from the admin controller — the write is delegated to the already-running writer loop.

**Primary recommendation:** Mount an `admin_router` with `prefix="/admin"` and a `require_session` dependency, organize sub-routers per section, use Jinja2 `TemplateResponse` for full-page renders and partial templates for htmx swaps. Extend `Settings` with `admin_username`/`admin_password` and `secret_key` for session signing.

---

## Standard Stack

### Core (all already installed in environment)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.135.3 (env) | Router, TemplateResponse, Depends | Already the app framework |
| Jinja2 | 3.1.6 (env) | Server-side HTML rendering | FastAPI's official templating layer |
| Starlette SessionMiddleware | (bundled w/ Starlette 1.0.0) | Signed cookie sessions for auth | Built into Starlette, no extra dep |
| itsdangerous | 2.2.0 (env) | Session cookie signing | Required by SessionMiddleware; already installed as transitive dep |
| python-multipart | 0.0.26 (env) | Form POST body parsing | Required for `Form(...)` in FastAPI; already installed via `fastapi[standard]` |
| Bootstrap 5 | 5.3.x CDN | CSS/JS components | No build step; load from CDN in base.html |
| htmx | 2.x CDN | Declarative AJAX | No build step; load from CDN in base.html |

### No New Packages Required

All required packages are already present. The only Settings extensions needed are:

```python
# Add to shifttracker/config.py Settings class
admin_username: str = "admin"
admin_password: str = "changeme"
secret_key: str = "dev-secret-change-in-production"
```

**Installation (nothing new):**
```bash
# No new pip installs — all dependencies already present
# fastapi[standard] bundles jinja2, python-multipart
# starlette bundles SessionMiddleware
# itsdangerous already installed as starlette transitive dep
```

---

## Architecture Patterns

### Recommended Project Structure

```
shifttracker/
├── app.py                      # Extend: mount admin_router, add SessionMiddleware
├── config.py                   # Extend: add admin_username, admin_password, secret_key
├── admin/
│   ├── __init__.py
│   ├── auth.py                 # require_session dependency, login/logout handlers
│   ├── router.py               # Main admin APIRouter, includes sub-routers
│   ├── routers/
│   │   ├── groups.py           # /admin/groups CRUD
│   │   ├── employees.py        # /admin/employees CRUD + group bindings
│   │   ├── caption_rules.py    # /admin/caption-rules CRUD
│   │   ├── review.py           # /admin/review queue + approve/reject
│   │   ├── shifts.py           # /admin/shifts grid view
│   │   └── dashboard.py        # /admin/ dashboard stats
│   └── deps.py                 # get_db dependency for admin routes
├── templates/
│   ├── base.html               # Bootstrap 5 sidebar layout, htmx CDN
│   ├── login.html              # Login form (no sidebar)
│   ├── admin/
│   │   ├── dashboard.html
│   │   ├── groups/
│   │   │   ├── list.html
│   │   │   ├── form.html       # Add/edit form (reused for both)
│   │   │   └── _row.html       # htmx partial: single table row
│   │   ├── employees/
│   │   │   ├── list.html
│   │   │   ├── form.html
│   │   │   └── _bindings.html  # htmx partial: group binding table
│   │   ├── caption_rules/
│   │   │   ├── list.html
│   │   │   └── form.html
│   │   ├── review/
│   │   │   ├── list.html
│   │   │   └── _item.html      # htmx partial: review queue row swap
│   │   └── shifts/
│   │       └── grid.html       # Date grid view
```

### Pattern 1: SessionMiddleware Auth

**What:** Starlette's SessionMiddleware stores a signed dict in a cookie. A `require_session` dependency reads `request.session["user"]` and redirects to `/admin/login` if absent.

**When to use:** All admin routes (applied via `dependencies=[Depends(require_session)]` on the router).

```python
# shifttracker/admin/auth.py
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse

def require_session(request: Request):
    if not request.session.get("user"):
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})
    return request.session["user"]

# Login endpoint
@router.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    settings = Settings()
    if username == settings.admin_username and password == settings.admin_password:
        request.session["user"] = username
        return RedirectResponse("/admin/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})
```

```python
# shifttracker/app.py — add to create_app()
from starlette.middleware.sessions import SessionMiddleware
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
```

**Source:** [Starlette Middleware docs](https://www.starlette.dev/middleware/#sessionmiddleware) — HIGH confidence

### Pattern 2: get_db Dependency (Async Session)

**What:** Reuse `async_session_factory` from `shifttracker/db/engine.py` via a `Depends`-compatible async generator.

**When to use:** Every admin route that queries the database.

```python
# shifttracker/admin/deps.py
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from shifttracker.db.engine import async_session_factory

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
```

**Source:** FastAPI official docs — HIGH confidence

### Pattern 3: Jinja2Templates + APIRouter

**What:** Create a shared `Jinja2Templates` instance pointed at `shifttracker/templates/`. Each router module uses it to return `TemplateResponse`.

**When to use:** Every HTML-returning endpoint.

```python
# shifttracker/admin/router.py
from fastapi import APIRouter
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="shifttracker/templates")

# shifttracker/admin/routers/groups.py
from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from shifttracker.db.models import TelegramGroup
from shifttracker.admin.router import templates
from shifttracker.admin.deps import get_db
from shifttracker.admin.auth import require_session

router = APIRouter(prefix="/groups", dependencies=[Depends(require_session)])

@router.get("/")
async def groups_list(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TelegramGroup).order_by(TelegramGroup.name))
    groups = result.scalars().all()
    return templates.TemplateResponse("admin/groups/list.html", {"request": request, "groups": groups})
```

**Source:** [FastAPI Templates docs](https://fastapi.tiangolo.com/advanced/templates/) — HIGH confidence

### Pattern 4: htmx Partial Swap for CRUD Actions

**What:** Delete/approve/reject buttons use `hx-delete` or `hx-post` to trigger a server action. The server returns either an empty 200 (row removed) or a replacement HTML fragment.

**When to use:** Delete operations, review queue approve/reject, inline status updates.

```html
<!-- Delete row: hx-confirm prompts before request; empty 200 response removes the row -->
<tr id="group-{{ group.id }}">
  <td>{{ group.name }}</td>
  <td>
    <button
      hx-delete="/admin/groups/{{ group.id }}"
      hx-target="#group-{{ group.id }}"
      hx-swap="outerHTML"
      hx-confirm="Delete {{ group.name }}?"
      class="btn btn-sm btn-danger">Delete</button>
  </td>
</tr>
```

```python
@router.delete("/{group_id}")
async def delete_group(group_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    group = await db.get(TelegramGroup, group_id)
    if group:
        await db.delete(group)
        await db.commit()
    return Response(status_code=200)  # empty body removes the row via outerHTML swap
```

**Source:** [htmx Delete Row example](https://htmx.org/examples/delete-row/) — HIGH confidence

### Pattern 5: Review Queue Approve — SheetsWriter Integration

**What:** Approving a NEEDS_REVIEW ProcessingLog entry requires: (1) creating a ShiftRecord with `sheet_write_status='PENDING'`, (2) updating the ProcessingLog status to `ACCEPTED`. The SheetsWriter background task running in `app.state.sheets_writer` will automatically pick up the PENDING record on its next flush cycle.

**When to use:** POST /admin/review/{id}/approve

```python
@router.post("/{log_id}/approve")
async def approve_review(
    log_id: uuid.UUID,
    request: Request,
    employee_id: uuid.UUID = Form(...),
    shift_date: date = Form(...),
    db: AsyncSession = Depends(get_db),
):
    log = await db.get(ProcessingLog, log_id)
    if not log:
        raise HTTPException(404)

    # Create ShiftRecord — SheetsWriter picks it up automatically
    shift = ShiftRecord(
        employee_id=employee_id,
        shift_date=shift_date,
        status="ACCEPTED",
        source_message_id=log.message_id,
        source_link=log.source_link or "",
        sheet_write_status="PENDING",
    )
    db.add(shift)

    # Update ProcessingLog
    log.status = "ACCEPTED"
    log.employee_id = employee_id
    log.shift_date = shift_date

    await db.commit()

    # Return empty partial so htmx removes the row from the review list
    return Response(status_code=200)
```

**Key insight:** `sheet_write_status='PENDING'` is the only integration needed. The SheetsWriter loop already handles dedup detection, retry logic, and the actual Sheets API call.

### Pattern 6: Base Template with Bootstrap 5 Sidebar

**What:** `base.html` provides the full HTML skeleton with Bootstrap 5 CDN, htmx CDN, and a sidebar nav. All admin pages use `{% extends "base.html" %}`.

```html
<!-- shifttracker/templates/base.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}ShiftTracker Admin{% endblock %}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
<div class="container-fluid">
  <div class="row">
    <!-- Sidebar -->
    <nav class="col-md-2 d-md-block bg-light sidebar">
      <div class="position-sticky pt-3">
        <ul class="nav flex-column">
          <li class="nav-item"><a class="nav-link" href="/admin/">Dashboard</a></li>
          <li class="nav-item"><a class="nav-link" href="/admin/groups/">Groups</a></li>
          <li class="nav-item"><a class="nav-link" href="/admin/employees/">Employees</a></li>
          <li class="nav-item"><a class="nav-link" href="/admin/caption-rules/">Caption Rules</a></li>
          <li class="nav-item"><a class="nav-link" href="/admin/review/">Review Queue</a></li>
          <li class="nav-item"><a class="nav-link" href="/admin/shifts/">Shift Table</a></li>
        </ul>
      </div>
    </nav>
    <!-- Main content -->
    <main class="col-md-10 ms-sm-auto px-md-4">
      {% block content %}{% endblock %}
    </main>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js"></script>
</body>
</html>
```

### Anti-Patterns to Avoid

- **Importing `templates` from `app.py`:** Creates circular imports when routers reference `app`. Instead, create a shared `Jinja2Templates` instance in `shifttracker/admin/router.py` or `shifttracker/admin/templates.py` and import from there.
- **Calling SheetsWriter directly from admin routes:** The admin `approve` action should only write to the DB. SheetsWriter runs in the background. Calling it directly creates coupling and can block the event loop if the Sheets API is slow.
- **Storing plain-text passwords in session:** Never store the password. Store only the username string in `request.session["user"]`.
- **Using `GET` for destructive operations:** Delete/approve/reject must use `hx-delete` or `hx-post`, never `hx-get`. Browsers preload GET links which could accidentally trigger destructive actions.
- **Opening a new session per query inside a single request:** Use a single `get_db` dependency per request. Multiple `Depends(get_db)` calls in one handler will create multiple sessions.
- **Forgetting `hx-boost` or full page reloads for forms without htmx:** Simple forms that do a full POST-redirect-GET (PRG pattern) are perfectly fine for add/edit operations. htmx is only needed when partial updates are required.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Session cookie signing | Custom HMAC cookie logic | Starlette `SessionMiddleware` | itsdangerous handles signing, expiry, and tamper detection |
| Form body parsing | Manual `await request.body()` parsing | FastAPI `Form(...)` + `python-multipart` | Already installed; handles multipart and urlencoded automatically |
| CSRF protection | Custom token generation/validation | `hx-boost` + SameSite=Lax cookie (default) | SessionMiddleware defaults to SameSite=Lax which mitigates CSRF for same-origin form posts |
| Pagination | Custom OFFSET/LIMIT logic in every route | Simple `limit`/`offset` query params + SQLAlchemy `.limit().offset()` | Sufficient for this scale; avoid external pagination libs for a test assignment |
| Template globals (e.g., current user) | Thread-local or global state | Jinja2 `templates.env.globals["..."]` or pass in every `TemplateResponse` context | Jinja2 env globals are the clean way to inject values like `app_name` available in all templates |

**Key insight:** Session auth at this scope is 20 lines of code. Don't reach for `fastapi-login`, `fastapi-users`, or any auth library — they add abstraction for OAuth/JWT flows that this project explicitly does not need.

---

## Common Pitfalls

### Pitfall 1: Templates Directory Resolution
**What goes wrong:** `Jinja2Templates(directory="templates")` resolves relative to the current working directory when uvicorn starts, not relative to the Python module. If uvicorn is started from the project root, `"shifttracker/templates"` works. If run from inside `shifttracker/`, `"templates"` works. Mismatch causes `TemplateNotFound` errors.
**Why it happens:** Jinja2 uses a filesystem loader with the given path as-is.
**How to avoid:** Use an absolute path derived from `__file__`:
```python
from pathlib import Path
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
```
**Warning signs:** `TemplateNotFound: base.html` error on startup.

### Pitfall 2: SessionMiddleware Must Be Added Before Routers Are Mounted
**What goes wrong:** `app.add_middleware(SessionMiddleware, ...)` called after `app.include_router(...)` silently works in development but middleware order matters in some edge cases.
**How to avoid:** Add all middleware in `create_app()` before including any routers. The canonical order: create app → add middleware → include routers.

### Pitfall 3: Redirect After POST Returns Wrong Status Code
**What goes wrong:** After a form POST (add/edit/delete), redirecting with `status_code=302` (default) instead of `303` causes some browsers to re-POST on the redirect, creating duplicate records.
**How to avoid:** Always use `RedirectResponse(..., status_code=303)` after a successful form POST.

### Pitfall 4: ShiftRecord Uniqueness Constraint on Approve
**What goes wrong:** `ShiftRecord` has `UniqueConstraint("employee_id", "shift_date")`. If an operator approves the same review item twice, or if a `ShiftRecord` already exists for that employee+date, the INSERT will raise `IntegrityError`.
**How to avoid:** Before inserting in the approve handler, check for an existing ShiftRecord:
```python
existing = await db.execute(
    select(ShiftRecord).where(
        ShiftRecord.employee_id == employee_id,
        ShiftRecord.shift_date == shift_date,
    )
)
if existing.scalar_one_or_none():
    # Handle conflict: return 409 or update existing record
```

### Pitfall 5: htmx Requests Expect Partial HTML, Not Full Pages
**What goes wrong:** An htmx `hx-post` button triggers a redirect response (303). Browsers follow redirects normally, but htmx will swap the full redirected page HTML into the target element, breaking the layout.
**How to avoid:** For htmx-triggered endpoints, always return either a partial HTML fragment or an empty 200 response. Never return a redirect from an htmx endpoint unless using `HX-Redirect` response header:
```python
# For htmx: signal client-side redirect via header
from fastapi.responses import Response
return Response(status_code=200, headers={"HX-Redirect": "/admin/review/"})
```

### Pitfall 6: Shift Grid Performance
**What goes wrong:** The shift table view queries all `ShiftRecord` rows for a date range, joined to `Employee`. With many employees and wide date ranges, this can return thousands of rows, making the page slow.
**How to avoid:** Always require a date range filter before rendering the grid. Default to the current week (7 days). Add a mandatory group filter or limit date range to max 31 days.

---

## Code Examples

Verified patterns from official sources:

### Register Admin Router in app.py

```python
# shifttracker/app.py — inside create_app()
from starlette.middleware.sessions import SessionMiddleware
from shifttracker.admin.router import admin_router

def create_app() -> FastAPI:
    app = FastAPI(title="ShiftTracker", version="0.1.0", lifespan=lifespan)

    # Middleware must be added before routers
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

    # Existing health route
    @app.get("/health")
    async def health():
        return {"status": "ok"}

    # Mount admin UI
    app.include_router(admin_router, prefix="/admin")

    return app
```

### Async CRUD Query Pattern

```python
# List with optional filter
from sqlalchemy import select
from shifttracker.db.models import Employee

async def list_employees(db: AsyncSession, search: str | None = None):
    stmt = select(Employee).order_by(Employee.name)
    if search:
        stmt = stmt.where(Employee.name.ilike(f"%{search}%"))
    result = await db.execute(stmt)
    return result.scalars().all()

# Get or 404
async def get_or_404(db: AsyncSession, model, id):
    obj = await db.get(model, id)
    if obj is None:
        raise HTTPException(status_code=404)
    return obj
```

### Dashboard Stats Query

```python
from sqlalchemy import func, and_
from datetime import date

async def get_dashboard_stats(db: AsyncSession) -> dict:
    today = date.today()

    # Count today's accepted processing logs
    accepted_today = await db.scalar(
        select(func.count(ProcessingLog.id)).where(
            and_(
                func.date(ProcessingLog.created_at) == today,
                ProcessingLog.status == "ACCEPTED",
            )
        )
    )

    # Count NEEDS_REVIEW queue depth
    pending_review = await db.scalar(
        select(func.count(ProcessingLog.id)).where(
            ProcessingLog.status == "NEEDS_REVIEW"
        )
    )

    # Count today's errors
    errors_today = await db.scalar(
        select(func.count(ProcessingLog.id)).where(
            and_(
                func.date(ProcessingLog.created_at) == today,
                ProcessingLog.status == "ERROR",
            )
        )
    )

    return {
        "accepted_today": accepted_today or 0,
        "pending_review": pending_review or 0,
        "errors_today": errors_today or 0,
    }
```

### Shift Grid Query

```python
from sqlalchemy.orm import joinedload

async def get_shift_grid(
    db: AsyncSession,
    group_id: uuid.UUID,
    date_from: date,
    date_to: date,
) -> dict:
    # Get employees in the group
    ge_result = await db.execute(
        select(GroupEmployee)
        .options(joinedload(GroupEmployee.employee))  # requires relationship defined
        .where(GroupEmployee.group_id == group_id)
        .order_by(GroupEmployee.sheet_row)
    )
    group_employees = ge_result.scalars().all()
    employee_ids = [ge.employee_id for ge in group_employees]

    # Get shift records in date range
    sr_result = await db.execute(
        select(ShiftRecord).where(
            ShiftRecord.employee_id.in_(employee_ids),
            ShiftRecord.shift_date >= date_from,
            ShiftRecord.shift_date <= date_to,
            ShiftRecord.status == "ACCEPTED",
        )
    )
    records = sr_result.scalars().all()

    # Build a lookup: (employee_id, shift_date) -> ShiftRecord
    grid = {(r.employee_id, r.shift_date): r for r in records}

    return {"group_employees": group_employees, "grid": grid}
```

**Note:** The current models do not define `relationship()` attributes. The planner should include a task to add `relationship()` to `GroupEmployee` and `Employee` if joinedload is needed, or use explicit joins in queries instead.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Passing `name` as first positional arg to `TemplateResponse` | Pass `request=request` as keyword arg | FastAPI 0.108.0 | Old pattern still works but triggers deprecation warning |
| `Depends(get_db)` with `Session` (sync) | `Depends(get_db)` with `AsyncSession` | SQLAlchemy 2.0+ | Async sessions are now first-class; always use async in this project |
| htmx 1.x `hx-swap-oob` for out-of-band swaps | htmx 2.x — same API, `hx-boost` improvements | htmx 2.0 (2024) | CDN URL should target `htmx.org@2.0.4` not `1.9.x` |

**Deprecated/outdated:**
- `from starlette.responses import HTMLResponse` for templates: use `TemplateResponse` directly instead; setting `response_class=HTMLResponse` on the route is optional but good for OpenAPI docs.

---

## Open Questions

1. **SQLAlchemy `relationship()` declarations missing from models**
   - What we know: `GroupEmployee`, `Employee`, `TelegramGroup` have FK columns but no `relationship()` attributes defined in `models.py`
   - What's unclear: Whether the planner should add relationships to models (schema change, no migration needed — just Python-level) or always use explicit joins
   - Recommendation: Add `relationship()` attributes in a Wave 0 task — makes admin query code simpler and avoids N+1 queries. No Alembic migration needed since relationships are ORM-only.

2. **ProcessingLog lacks `caption_text` field for review queue display**
   - What we know: CONTEXT.md says the review queue shows "caption text" per entry. The `ProcessingLog` model has no `caption_text` column — only `reason` and `source_link`.
   - What's unclear: Was caption text ever stored? The Phase 1 processing pipeline may have logged it in `reason`, or it may be absent entirely.
   - Recommendation: Check Phase 1 pipeline code before planning. If `caption_text` is genuinely absent, the review queue will need to either show `reason` or add a migration to store caption text. The planner should verify this and add a migration task if needed.

3. **`func.date()` cross-database compatibility for dashboard stats**
   - What we know: The project uses PostgreSQL in production and SQLite in tests. `func.date(ProcessingLog.created_at)` works in SQLite but PostgreSQL may require `cast(ProcessingLog.created_at, Date)`.
   - Recommendation: Use `ProcessingLog.created_at >= datetime.combine(today, time.min)` comparisons instead of `func.date()` for cross-db compatibility.

---

## Validation Architecture

> config.json not found — treating nyquist_validation as enabled.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]` asyncio_mode = "auto", timeout = 10) |
| Quick run command | `pytest tests/test_admin_auth.py tests/test_admin_crud.py -x --timeout=10` |
| Full suite command | `pytest tests/ --timeout=10` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REVIEW-01 | NEEDS_REVIEW entries appear in review list | unit (async SQLAlchemy) | `pytest tests/test_admin_review.py::test_review_list -x` | ❌ Wave 0 |
| REVIEW-02 | Approve/reject endpoints return 200 and update DB | integration (TestClient) | `pytest tests/test_admin_review.py::test_approve -x` | ❌ Wave 0 |
| REVIEW-03 | Approve creates ShiftRecord with sheet_write_status=PENDING | unit | `pytest tests/test_admin_review.py::test_approve_creates_shift_record -x` | ❌ Wave 0 |
| REVIEW-04 | Reject sets ProcessingLog status=REJECTED with comment | unit | `pytest tests/test_admin_review.py::test_reject_stores_comment -x` | ❌ Wave 0 |
| ADMIN-01 | Group CRUD: create/edit/delete persists in DB | unit | `pytest tests/test_admin_crud.py::test_group_crud -x` | ❌ Wave 0 |
| ADMIN-02 | Employee CRUD: create/edit/delete persists in DB | unit | `pytest tests/test_admin_crud.py::test_employee_crud -x` | ❌ Wave 0 |
| ADMIN-03 | GroupEmployee assign/unassign and sheet_row save | unit | `pytest tests/test_admin_crud.py::test_group_employee_binding -x` | ❌ Wave 0 |
| ADMIN-04 | Group edit saves shift_start_hour/shift_end_hour | unit | `pytest tests/test_admin_crud.py::test_group_shift_window -x` | ❌ Wave 0 |
| ADMIN-05 | CaptionRule CRUD persists pattern+employee_id | unit | `pytest tests/test_admin_crud.py::test_caption_rule_crud -x` | ❌ Wave 0 |
| ADMIN-06 | Base template renders sidebar nav (smoke) | smoke (TestClient) | `pytest tests/test_admin_smoke.py::test_sidebar_navigation -x` | ❌ Wave 0 |
| ADMIN-07 | Shift grid returns correct cells for date range + group | unit | `pytest tests/test_admin_shifts.py::test_shift_grid_query -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/test_admin_crud.py tests/test_admin_review.py -x --timeout=10`
- **Per wave merge:** `pytest tests/ --timeout=10`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_admin_auth.py` — login/logout, session requirement, redirect on unauthenticated access
- [ ] `tests/test_admin_crud.py` — CRUD for Groups, Employees, GroupEmployee bindings, CaptionRules (covers ADMIN-01..05)
- [ ] `tests/test_admin_review.py` — review queue list, approve, reject (covers REVIEW-01..04)
- [ ] `tests/test_admin_shifts.py` — shift grid query correctness (covers ADMIN-07)
- [ ] `tests/test_admin_smoke.py` — rendered HTML smoke tests for sidebar + template inheritance (covers ADMIN-06)
- [ ] `tests/conftest.py` update — add `test_client` fixture using FastAPI's `TestClient` with session middleware configured for tests

---

## Sources

### Primary (HIGH confidence)
- [FastAPI Templates docs](https://fastapi.tiangolo.com/advanced/templates/) — Jinja2Templates setup, TemplateResponse API, url_for in templates
- [FastAPI Static Files docs](https://fastapi.tiangolo.com/tutorial/static-files/) — StaticFiles mount pattern
- [FastAPI Dependencies with yield](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/) — get_db pattern
- [Starlette Middleware docs](https://www.starlette.dev/middleware/#sessionmiddleware) — SessionMiddleware, itsdangerous signing
- [htmx Delete Row example](https://htmx.org/examples/delete-row/) — hx-delete + outerHTML swap
- [htmx hx-confirm attribute](https://htmx.org/attributes/hx-confirm/) — confirmation dialogs
- Environment inspection: FastAPI 0.135.3, Jinja2 3.1.6, itsdangerous 2.2.0, python-multipart 0.0.26, Starlette 1.0.0 all confirmed installed

### Secondary (MEDIUM confidence)
- [TestDriven.io — Using HTMX with FastAPI](https://testdriven.io/blog/fastapi-htmx/) — hx-post form patterns, HX-Request header detection
- [htmx Bootstrap Modal example](https://htmx.org/examples/modal-bootstrap/) — server-powered modal pattern

### Tertiary (LOW confidence)
- Various blog posts on FastAPI + Jinja2 + htmx admin panel patterns — consistent with official docs

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages confirmed installed in virtualenv; APIs verified from official docs
- Architecture: HIGH — standard FastAPI router/template patterns from official docs; htmx attributes from official reference
- Pitfalls: HIGH — template path resolution, session middleware order, and UniqueConstraint conflict are all reproducible, verified issues
- Review queue integration: HIGH — SheetsWriter pattern already implemented in Phase 2; approve action simply sets sheet_write_status=PENDING

**Research date:** 2026-04-10
**Valid until:** 2026-05-10 (stable stack — FastAPI, Jinja2, htmx, Bootstrap 5 APIs are stable)
