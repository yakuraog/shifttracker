---
phase: 1
slug: foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-10
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio |
| **Config file** | pyproject.toml (Wave 0 installs) |
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

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — shared fixtures (async session, test DB)
- [ ] `tests/test_models.py` — stubs for DB model tests
- [ ] `tests/test_pipeline.py` — stubs for processing pipeline tests
- [ ] `tests/test_shift_date.py` — stubs for shift date resolution
- [ ] `tests/test_identification.py` — stubs for employee identification
- [ ] `pyproject.toml` — pytest + pytest-asyncio + dependencies

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Bot receives photos from real Telegram group | TGRAM-01 | Requires live Telegram environment | Add bot to test group, send photo, check DB log |
| Bot handles group migration | TGRAM-04 | Requires actual group→supergroup migration | Upgrade a test group, verify chat_id updated |

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
