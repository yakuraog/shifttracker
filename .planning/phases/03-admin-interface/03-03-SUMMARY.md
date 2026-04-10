---
phase: 03-admin-interface
plan: "03"
subsystem: admin-review
tags: [admin, review-queue, htmx, fastapi, jinja2, tdd, processing-log, shift-record]
dependency_graph:
  requires:
    - shifttracker/admin/router.py (admin_router, templates)
    - shifttracker/admin/auth.py (require_session)
    - shifttracker/admin/deps.py (get_db)
    - shifttracker/db/models.py (ProcessingLog, ShiftRecord, Employee, TelegramGroup)
    - shifttracker/templates/base.html (sidebar layout)
    - tests/conftest.py (test_client fixture)
  provides:
    - shifttracker/admin/routers/review.py (review router: list, approve, reject)
    - shifttracker/templates/admin/review/list.html (review queue page with filter form)
    - shifttracker/templates/admin/review/_item.html (row partial with htmx forms)
    - tests/test_admin_review.py (5 integration tests covering all behaviors)
  affects:
    - SheetsWriter background task picks up PENDING ShiftRecords created on approve
tech_stack:
  added: []
  patterns:
    - TDD: tests written first (RED), then implementation (GREEN)
    - hx-post with hx-target="closest tr" hx-swap="outerHTML" for row removal on approve/reject
    - Bootstrap collapse for inline approve/reject forms per row
    - IntegrityError catch + pre-check for UniqueConstraint(employee_id, shift_date)
    - asyncio.new_event_loop() in sync test helpers to run async DB seed coroutines
key_files:
  created:
    - shifttracker/admin/routers/review.py
    - shifttracker/templates/admin/review/list.html
    - shifttracker/templates/admin/review/_item.html
    - tests/test_admin_review.py
  modified:
    - shifttracker/admin/router.py (added review router include)
decisions:
  - "Approve handler does pre-check for existing ShiftRecord before insert to avoid relying solely on IntegrityError — provides clear 409 response without DB exception path"
  - "hx-swap outerHTML on tr removes the row from the queue on successful approve/reject — no page reload needed"
  - "asyncio.new_event_loop() used in test seed helpers since pytest-asyncio loop is not active during synchronous test body"
metrics:
  duration: ~8 minutes
  completed: 2026-04-10T18:50:35Z
  tasks_completed: 2
  files_created: 4
  files_modified: 1
---

# Phase 03 Plan 03: Review Queue Summary

**One-liner:** Manual review queue with approve (creates PENDING ShiftRecord) and reject (stores operator comment), backed by 5 integration tests using TDD.

## What Was Built

The admin review queue allows operators to process `NEEDS_REVIEW` ProcessingLog entries that the bot could not automatically resolve (e.g., unidentified employees).

### Endpoints

| Method | Path | Behavior |
|--------|------|----------|
| GET | `/admin/review/` | List all NEEDS_REVIEW items with optional group_id/date_from/date_to filters |
| POST | `/admin/review/{id}/approve` | Create ShiftRecord(status=ACCEPTED, sheet_write_status=PENDING), update log to ACCEPTED |
| POST | `/admin/review/{id}/reject` | Update log to REJECTED with operator comment |

### Key Behaviors

- Approving creates a `ShiftRecord` with `sheet_write_status="PENDING"` — SheetsWriter background task picks this up automatically (no direct coupling needed)
- Duplicate approval (same employee+date) returns HTTP 409 Conflict via pre-check + IntegrityError fallback
- Group filter resolves `chat_id` from `TelegramGroup.id` for correct SQL filtering
- Each review row shows employee name (resolved via LEFT JOIN-style query), group name, reason, and source link

### Templates

- `list.html`: extends `base.html`, filter form at top, Bootstrap table with one row per item
- `_item.html`: Bootstrap collapse for inline approve/reject forms, htmx removes row on success

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Failing tests for review queue | 5f07060 | tests/test_admin_review.py |
| 1 (GREEN) | Review queue router and templates | baa515a | review.py, router.py, list.html, _item.html |
| 2 | Integration tests (created in Task 1 per TDD) | 5f07060 | tests/test_admin_review.py |

## Deviations from Plan

None - plan executed exactly as written. Task 2 tests were created during the TDD RED phase of Task 1 (as intended by the TDD workflow).

### Pre-existing Out-of-Scope Issues

`test_admin_crud.py` was already failing before this plan (CRUD routers for groups/employees not yet implemented — part of plan 03-02). Logged to deferred-items as out of scope.

## Verification

- `pytest tests/test_admin_review.py`: 5/5 passed
- All acceptance criteria grep checks: passed
- REVIEW-01: queue visible (list endpoint returns NEEDS_REVIEW items)
- REVIEW-02: approve and reject actions work
- REVIEW-03: approve triggers Sheets write via PENDING status
- REVIEW-04: reject stores operator comment

## Self-Check: PASSED
