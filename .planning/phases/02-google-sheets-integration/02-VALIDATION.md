---
phase: 2
slug: google-sheets-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-10
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio |
| **Config file** | pyproject.toml |
| **Quick run command** | `pytest tests/ -x -q --timeout=10` |
| **Full suite command** | `pytest tests/ -v --timeout=30` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q --timeout=10`
- **After every plan wave:** Run `pytest tests/ -v --timeout=30`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| (populated during planning) | | | | | | | |

---

## Wave 0 Requirements

- [ ] `tests/test_sheets.py` — stubs for Sheets writer tests
- [ ] `tests/test_sheets_buffer.py` — stubs for write buffer tests
- [ ] gspread + google-auth in pyproject.toml dependencies

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| "1" appears in real Google Sheet | SHEET-01 | Requires live Google Sheets API | Configure service account, create test sheet, send photo, verify cell |
| Rate limit handling under real load | SHEET-04 | Requires actual API quota testing | Send 70+ photos in 60s, verify all marks eventually appear |

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
