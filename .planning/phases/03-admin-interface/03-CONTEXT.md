# Phase 3: Admin Interface - Context

**Gathered:** 2026-04-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Web admin interface for system configuration, manual review queue, and shift table visibility. FastAPI REST API endpoints + simple server-rendered HTML templates (Jinja2). Completes the full end-to-end operator workflow. Does NOT add new Telegram bot features or Sheets logic.

</domain>

<decisions>
## Implementation Decisions

### Technology Choice — Server-Rendered HTML
- FastAPI + Jinja2 templates (no SPA framework — keep it simple for a test assignment)
- Bootstrap 5 CDN for styling (fast, professional, no build step)
- htmx for interactive elements (AJAX without JS complexity)
- All templates rendered server-side, minimal JavaScript
- No separate frontend build process — templates live in `shifttracker/templates/`

### Authentication
- Simple token-based auth (API key in header or session cookie)
- Admin credentials configured via environment variables (ADMIN_USERNAME, ADMIN_PASSWORD)
- Login page with session cookie for web UI
- API endpoints require Bearer token or valid session
- No OAuth, no JWT — simple and sufficient for v1

### Admin CRUD (ADMIN-01..05)
- Groups management: list, add, edit (name, chat_id, sheet_id, shift hours, timezone), delete
- Employees management: list, add, edit (name, telegram_user_id, employee_code), delete
- Group-employee bindings: assign/unassign employees to groups, set sheet_row
- Caption rules: list, add, edit (group, pattern, employee), delete
- Shift time windows: configured per group (shift_start_hour, shift_end_hour) — part of group edit form

### Manual Review Queue (REVIEW-01..04)
- List all processing_log entries with status NEEDS_REVIEW
- Each entry shows: employee name (if identified), group name, timestamp, caption text, source link
- Approve action: creates ShiftRecord with status ACCEPTED, triggers Sheets write
- Reject action: updates processing_log status to REJECTED with operator comment
- Filter by group, date range
- Sort by newest first

### Shift Table View (ADMIN-07)
- Grid view: employees as rows, dates as columns, "1" marks
- Filter by group/object, date range
- Click on "1" to see source message link and processing details
- History: show processing_log entries for a specific employee + date

### Web Interface Layout (ADMIN-06)
- Sidebar navigation: Dashboard, Groups, Employees, Caption Rules, Review Queue, Shift Table
- Dashboard: summary stats (total processed today, pending review count, errors count)
- Responsive layout (Bootstrap grid)

### Claude's Discretion
- Exact HTML/CSS template design
- Table pagination approach
- Form validation UX
- Dashboard chart/stat presentation
- Error page design

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Documentation
- `.planning/PROJECT.md` — Project context, roles (admin, operator, supervisor)
- `.planning/REQUIREMENTS.md` — REVIEW-01..04, ADMIN-01..07 requirements
- `.planning/research/FEATURES.md` — Manual review workflow patterns

### Existing Code
- `shifttracker/app.py` — FastAPI app factory to extend with routes
- `shifttracker/db/models.py` — All ORM models (Employee, TelegramGroup, etc.)
- `shifttracker/db/engine.py` — async_session_factory
- `shifttracker/config.py` — Settings to extend with admin credentials
- `shifttracker/sheets/writer.py` — SheetsWriter to trigger for approved reviews

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- FastAPI app factory in app.py — add routers
- SQLAlchemy async models — query directly
- SheetsWriter — call for approved review items

### Established Patterns
- pydantic-settings for config
- async SQLAlchemy sessions via async_session_factory
- Alembic for migrations (no schema changes needed for Phase 3)

### Integration Points
- app.py: mount admin API routers and serve templates
- processing_log: query for NEEDS_REVIEW entries
- shift_records: create on review approval
- sheets/writer.py: enqueue writes for approved items

</code_context>

<specifics>
## Specific Ideas

- Keep it simple — this is a test assignment, not a production admin panel
- Server-rendered HTML avoids the complexity of a separate frontend build
- htmx makes forms interactive without writing custom JavaScript
- Bootstrap 5 from CDN means zero frontend build tooling

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-admin-interface*
*Context gathered: 2026-04-10*
