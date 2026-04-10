---
phase: 3
slug: admin-interface
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-10
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio + httpx (TestClient) |
| **Config file** | pyproject.toml |
| **Quick run command** | `pytest tests/ -x -q --timeout=10` |
| **Full suite command** | `pytest tests/ -v --timeout=30` |
| **Estimated runtime** | ~20 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q --timeout=10`
- **After every plan wave:** Run `pytest tests/ -v --timeout=30`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| (populated during planning) | | | | | | | |

---

## Wave 0 Requirements

- [ ] `tests/test_admin_api.py` — stubs for admin CRUD tests
- [ ] `tests/test_review.py` — stubs for review queue tests
- [ ] httpx in pyproject.toml test dependencies (for async TestClient)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Web UI renders correctly in browser | ADMIN-06 | Visual/layout verification | Open localhost, navigate all pages, check Bootstrap renders |
| htmx interactions work smoothly | ADMIN-06 | Browser JS execution | Test form submissions, table filtering via htmx |

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
