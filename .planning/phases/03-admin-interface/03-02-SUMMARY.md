---
phase: 03-admin-interface
plan: 02
subsystem: ui
tags: [fastapi, jinja2, sqlalchemy, htmx, bootstrap5, crud, admin]

# Dependency graph
requires:
  - phase: 03-admin-interface/03-01
    provides: auth, session dependency, base templates, conftest test_client fixture

provides:
  - TelegramGroup CRUD endpoints (list/add/edit/delete) with shift window fields
  - Employee CRUD endpoints (list/add/edit/delete)
  - GroupEmployee binding management (add/remove per employee)
  - CaptionRule CRUD endpoints (list/add/edit/delete with group+employee dropdowns)
  - Full integration test suite for all CRUD operations

affects: [03-admin-interface/03-03, 03-admin-interface/03-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "UUID string path params converted to uuid.UUID() before SQLAlchemy query (SQLite compatibility)"
    - "Lazy import of templates via _get_templates() avoids circular import in sub-routers"
    - "selectinload for GroupEmployee.group eager loading in employee edit form"
    - "TDD: test commit (RED) before implementation commit (GREEN)"

key-files:
  created:
    - shifttracker/admin/routers/groups.py
    - shifttracker/admin/routers/employees.py
    - shifttracker/admin/routers/caption_rules.py
    - shifttracker/templates/admin/groups/list.html
    - shifttracker/templates/admin/groups/form.html
    - shifttracker/templates/admin/employees/list.html
    - shifttracker/templates/admin/employees/form.html
    - shifttracker/templates/admin/employees/_bindings.html
    - shifttracker/templates/admin/caption_rules/list.html
    - shifttracker/templates/admin/caption_rules/form.html
    - tests/test_admin_crud.py
  modified:
    - shifttracker/admin/router.py

key-decisions:
  - "UUID string path params must be wrapped with uuid.UUID() before SQLAlchemy WHERE clause — SQLite aiosqlite rejects string UUIDs"
  - "Binding delete test asserts binding_id absent from page rather than group name absent — group name legitimately appears in Add Binding dropdown"
  - "selectinload(Employee.group_bindings).selectinload(GroupEmployee.group) used for eager loading nested relationship in employee edit endpoint"

patterns-established:
  - "Sub-router pattern: APIRouter per section, all mounted in admin/router.py with include_router + require_session dependency"
  - "Lazy template import: _get_templates() helper avoids circular import between router and sub-routers"
  - "htmx delete pattern: hx-delete on button, hx-target=closest tr, hx-swap=outerHTML for inline row removal"

requirements-completed: [ADMIN-01, ADMIN-02, ADMIN-03, ADMIN-04, ADMIN-05]

# Metrics
duration: 15min
completed: 2026-04-10
---

# Phase 3 Plan 02: Admin CRUD (Groups, Employees, Caption Rules) Summary

**Full CRUD for Groups, Employees, GroupEmployee bindings, and Caption Rules via FastAPI routers + Jinja2 templates with htmx inline delete and 103-test green suite**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-10T18:48:00Z
- **Completed:** 2026-04-10T18:53:07Z
- **Tasks:** 2
- **Files modified:** 12

## Accomplishments
- Groups CRUD with shift_start_hour/shift_end_hour fields, timezone, sheet_id — all persisted and editable
- Employees CRUD with GroupEmployee binding management (add binding with sheet_row, delete binding via htmx)
- Caption Rules CRUD with group and employee dropdown selects
- 5 integration tests (test_group_crud, test_group_shift_window, test_employee_crud, test_group_employee_binding, test_caption_rule_crud) all passing
- Full 103-test suite remains green

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Groups+Employees failing tests** - `84923b4` (test)
2. **Task 1 GREEN: Groups and Employees CRUD routers + templates** - `1531241` (feat)
3. **Task 2 RED: CaptionRule failing test** - `d15116b` (test)
4. **Task 2 GREEN: Caption Rules CRUD router + templates** - `7a81d3c` (feat)

_Note: TDD tasks have separate test (RED) and implementation (GREEN) commits_

## Files Created/Modified

- `shifttracker/admin/routers/groups.py` - TelegramGroup CRUD router with shift window fields
- `shifttracker/admin/routers/employees.py` - Employee CRUD + GroupEmployee binding endpoints
- `shifttracker/admin/routers/caption_rules.py` - CaptionRule CRUD with group/employee selection
- `shifttracker/admin/router.py` - Updated to include groups, employees, caption_rules routers
- `shifttracker/templates/admin/groups/list.html` - Groups table with htmx delete
- `shifttracker/templates/admin/groups/form.html` - Group form with shift window number inputs
- `shifttracker/templates/admin/employees/list.html` - Employees table with htmx delete
- `shifttracker/templates/admin/employees/form.html` - Employee form + bindings section
- `shifttracker/templates/admin/employees/_bindings.html` - Partial bindings table body for htmx
- `shifttracker/templates/admin/caption_rules/list.html` - Caption rules table with htmx delete
- `shifttracker/templates/admin/caption_rules/form.html` - Caption rule form with dropdowns
- `tests/test_admin_crud.py` - 5 integration tests covering all CRUD operations

## Decisions Made
- UUID string path params converted to `uuid.UUID()` before SQLAlchemy WHERE — SQLite aiosqlite driver rejects raw strings for UUID columns
- Binding delete test asserts `binding_id not in resp.text` rather than group name absent — group name legitimately remains in the "Add Binding" dropdown on the edit page
- `selectinload(Employee.group_bindings).selectinload(GroupEmployee.group)` used in employee edit endpoint to eager-load group names for the bindings table without N+1 queries

## Deviations from Plan

None - plan executed exactly as written. The UUID string conversion was a known SQLite/SQLAlchemy behavior handled inline during GREEN phase.

## Issues Encountered
- SQLAlchemy StatementError on UUID columns with SQLite: path param strings must be wrapped with `uuid.UUID()` before use in WHERE clauses. Applied consistently to all three routers.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All 5 admin CRUD requirements (ADMIN-01..05) are implemented and tested
- Groups, Employees, GroupEmployee bindings, and Caption Rules are fully manageable via admin UI
- Ready for Phase 3 Plan 03 (Shift Table view) and Plan 04 (final integration/verification)

---
*Phase: 03-admin-interface*
*Completed: 2026-04-10*
