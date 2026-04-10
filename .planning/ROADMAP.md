# Roadmap: ShiftTracker

## Overview

ShiftTracker is built in three delivery phases that follow the natural dependency order of the system. Phase 1 establishes the entire data foundation and processing pipeline — the bot receives photos, identifies employees, resolves shift dates, deduplicates, and writes to the audit log, all without a UI. Phase 2 adds Google Sheets as the display layer, consuming SHEET_WRITE_PENDING records produced by the Phase 1 pipeline. Phase 3 exposes configuration and the manual review queue through a web admin interface, completing the full end-to-end operator workflow. Every v1 requirement is covered.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation** - Telegram ingestion, processing pipeline, employee identification, shift date resolution, deduplication, and audit log
- [ ] **Phase 2: Google Sheets Integration** - Batched writes to Google Sheets with rate-limit handling and retry resilience
- [ ] **Phase 3: Admin Interface** - Web UI for employee/group configuration, manual review queue, and shift table visibility

## Phase Details

### Phase 1: Foundation
**Goal**: The system receives photo messages from Telegram groups, identifies employees, resolves shift dates, deduplicates, and records every outcome in the audit log — all without a UI
**Depends on**: Nothing (first phase)
**Requirements**: TGRAM-01, TGRAM-02, TGRAM-03, TGRAM-04, TGRAM-05, IDENT-01, IDENT-02, IDENT-03, IDENT-04, IDENT-05, SHIFT-01, SHIFT-02, SHIFT-03, SHIFT-04, JRNL-01, JRNL-02, JRNL-03, JRNL-04
**Success Criteria** (what must be TRUE):
  1. A photo sent in a connected Telegram group is recorded in the database with status RECEIVED within seconds, including its source link
  2. A photo with a recognizable caption or sender account produces a PROCESSED log entry with the correct employee and resolved shift date (including midnight crossover correctness)
  3. Sending the same Telegram message twice does not create a second log entry or shift record
  4. A photo with an unrecognizable sender produces a NEEDS_REVIEW log entry, not a silent drop
  5. The audit log shows the status and rejection reason for every processed message — accepted, skipped, pending review, or error
**Plans:** 3/4 plans executed

Plans:
- [ ] 01-01-PLAN.md — Project scaffold, DB models, config, Alembic migration, test infrastructure
- [ ] 01-02-PLAN.md — Employee identification (confidence ladder) and shift date resolution
- [ ] 01-03-PLAN.md — Bot handlers, message validation, queue, and update deduplication
- [ ] 01-04-PLAN.md — Pipeline worker wiring, FastAPI app factory, end-to-end tests

### Phase 2: Google Sheets Integration
**Goal**: Every confirmed shift attendance mark is written as "1" into the correct Google Sheets cell, with resilience against quota limits and transient failures
**Depends on**: Phase 1
**Requirements**: SHEET-01, SHEET-02, SHEET-03, SHEET-04, SHEET-05
**Success Criteria** (what must be TRUE):
  1. After a photo is processed successfully, the corresponding cell (employee row + shift date column) in Google Sheets shows "1"
  2. The audit log entry for that mark contains a link back to the original Telegram message
  3. Sending a second photo for the same employee on the same date does not overwrite or duplicate the existing "1" — the duplicate attempt is logged
  4. During a burst of 70+ write operations within 60 seconds, all marks eventually appear in Sheets without data loss
  5. If Sheets is temporarily unreachable, marks remain in SHEET_WRITE_PENDING state and are retried automatically until they succeed
**Plans**: TBD

### Phase 3: Admin Interface
**Goal**: An operator can configure the system, process the manual review queue, and view the shift attendance table through a web interface — completing the full end-to-end workflow
**Depends on**: Phase 2
**Requirements**: REVIEW-01, REVIEW-02, REVIEW-03, REVIEW-04, ADMIN-01, ADMIN-02, ADMIN-03, ADMIN-04, ADMIN-05, ADMIN-06, ADMIN-07
**Success Criteria** (what must be TRUE):
  1. An administrator can add, edit, and remove Telegram groups, employees, caption matching rules, and shift time windows through the web interface
  2. An operator can see all NEEDS_REVIEW items in a queue, open the source Telegram message, then approve or reject each item with a reason — approved items produce a "1" in Sheets, rejected items are logged with a comment
  3. A supervisor can view the current shift attendance table and history of automated changes per employee per date
  4. Authenticated access to all admin endpoints is enforced — unauthenticated requests are rejected
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 3/4 | In Progress|  |
| 2. Google Sheets Integration | 0/TBD | Not started | - |
| 3. Admin Interface | 0/TBD | Not started | - |
