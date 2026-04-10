# Feature Research

**Domain:** Automated shift check-in tracking — Telegram photo messages to Google Sheets
**Researched:** 2026-04-10
**Confidence:** HIGH (core features), MEDIUM (edge-case behaviors), HIGH (anti-features)

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features the client assumes will exist. Missing any of these makes the system feel broken or untrustworthy.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Photo message ingestion from Telegram groups | Core trigger — no photo detection means no system | LOW | aiogram 3 `message_handler` with filter `content_types=ContentType.PHOTO` |
| Employee identification by caption text | Guards write name/post in the caption — this is the existing convention | MEDIUM | Fuzzy match against employee registry; falls back to Telegram account if caption ambiguous |
| Employee identification by Telegram account | Backup when caption is absent or ambiguous | LOW | `message.from_user.id` → lookup in employee_accounts table |
| Group-to-object mapping | Each group represents a specific guard post/facility | LOW | Many-to-one: group_id → object; stored in config table |
| Shift date resolution with time-window logic | Night shifts cross midnight — naive date = wrong day | MEDIUM | Configurable window per shift-type (e.g. 20:00–06:00 = "previous calendar day"); see detail below |
| Idempotent Google Sheets write ("1" in cell) | Duplicate photo or retry must not write twice | MEDIUM | Check cell value before writing; log dedup events; Sheets API allows cell-level read before write |
| Duplicate submission rejection | Same employee, same shift date, same group → discard second photo | LOW | DB unique constraint on (employee_id, shift_date, group_id) |
| Processing journal / audit log | Every message must have a traceable outcome | MEDIUM | States: ACCEPTED / REJECTED / PENDING_REVIEW / ERROR — stored with message_id, group_id, timestamp, reason |
| Manual review queue for ambiguous cases | When employee cannot be resolved confidently, a human decides | MEDIUM | Queue table + admin UI action (accept with manual employee assignment, or reject with reason) |
| Admin web interface | Configure groups, employees, shift windows, review queue | MEDIUM | FastAPI + minimal HTML or React; CRUD for employee registry and group config |
| Employee registry (name, aliases, Telegram accounts) | Needed for identification logic to function | LOW | employees table: id, full_name, telegram_user_id, caption_aliases[] |
| Real-time processing | Client expects marks to appear in Sheets within seconds of photo send | MEDIUM | aiogram handler → async task queue (asyncio or Celery) → Sheets write |

---

### Differentiators (Competitive Advantage)

Features that go beyond baseline expectations and directly serve the client's reliability/trust needs.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Confidence scoring on employee identification | System expresses how certain it is — LOW confidence → auto-route to review | MEDIUM | Score = weighted combo of caption match quality + account match + group context; threshold configurable |
| Per-group shift window configuration | Different objects have different shift times (22:00–10:00 vs 08:00–20:00) | LOW | shift_windows table: group_id, shift_label, start_hour, end_hour, date_offset (-1/0) |
| Audit trail linking Sheets cell to source message | Every "1" in the spreadsheet is traceable to a specific Telegram message | LOW | Log: sheet_id, cell_address, message_link, processed_at, operator_id (if manual) |
| Operator Telegram notifications for review queue | Instead of checking admin UI, operator gets a Telegram message with photo and accept/reject buttons | HIGH | Requires separate operator bot or inline keyboard callback; significant UX win for mobile operators |
| Graceful degradation on Sheets API quota exhaustion | At 300 writes/min project quota, spikes may cause drops; queued retry prevents silent data loss | MEDIUM | Write queue with exponential backoff and dead-letter logging for failed writes |
| Configurable caption parsing rules per group | Some groups may use different conventions (post number, initials) | MEDIUM | Rule table: group_id → regex pattern or keyword list; default falls back to global rules |

---

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Face recognition on photos | Seems like the obvious next step for verification | v1 scope explicitly excludes it; needs GPU infra, labeling, GDPR risk, false positive risk in security context; massive complexity jump | Use caption + account as dual-signal; add face recognition only in v2 after caption-based system is validated |
| Real-time push of every raw photo to admin UI | Operators want to "see what's coming in" | 1000s of photos/day per group = unusable UI; privacy/storage concerns | Show only PENDING_REVIEW queue; link to original Telegram message for context |
| Storing photo files in the database | Full audit trail seems to require photo storage | Massive storage growth at thousands of photos/day; Telegram retains photos for ≥1 year via message link | Store `message_link` (t.me/c/group_id/msg_id) — sufficient for audit, zero storage cost |
| Auto-resolve all duplicates silently | "Just take the first one" seems safe | Silent discard of legitimate second photo (e.g. shift correction, re-post after network failure) hides errors | Log ALL duplicates as DUPLICATE_REJECTED with reason; surface in admin UI for manual override if needed |
| Userbot / MTProto access to read all group messages | Wider access, no need to add bot to each group | Violates Telegram ToS; account ban risk; legally ambiguous for client; brittle | Bot API with bot added to group — explicit, stable, ToS-compliant |
| Payroll calculation from attendance marks | Logical extension of attendance data | Different domain, different compliance requirements, far out of scope | Keep system as source-of-truth for presence; export to payroll system separately |
| Unlimited groups without rate limit awareness | "Just scale to 500 groups" | Google Sheets API: 300 write requests/min per project, 60/min per user — at 200 groups with burst activity this is a real constraint | Batch writes, queue with backoff, monitor quota usage; design for batching from day one |

---

## Feature Dependencies

```
[Employee Registry]
    └──required by──> [Employee Identification by Caption]
    └──required by──> [Employee Identification by Telegram Account]
    └──required by──> [Confidence Scoring]

[Group Configuration (group→object mapping)]
    └──required by──> [Photo Message Ingestion]
    └──required by──> [Shift Date Resolution]
    └──required by──> [Per-Group Caption Rules]

[Shift Date Resolution]
    └──required by──> [Google Sheets Write]
    └──required by──> [Duplicate Rejection]

[Processing Journal / Audit Log]
    └──required by──> [Manual Review Queue]
    └──required by──> [Audit Trail to Sheets Cell]
    └──required by──> [Admin Web Interface — Review tab]

[Manual Review Queue]
    └──enhanced by──> [Operator Telegram Notifications]

[Google Sheets Write]
    └──required by──> [Idempotent Write Guard]
    └──protected by──> [Graceful Degradation / Retry Queue]

[Photo Message Ingestion] ──enables──> [Employee Identification]
[Employee Identification] ──feeds──> [Shift Date Resolution]
[Shift Date Resolution] ──feeds──> [Duplicate Rejection]
[Duplicate Rejection] ──gates──> [Google Sheets Write]
```

### Dependency Notes

- **Employee Registry required by identification:** Without a registry, caption text has nothing to match against. Registry must be populated before any group is activated.
- **Group configuration required by shift date resolution:** The time window (which hours map to which shift date) is per-group. A group with no window config cannot be processed — route to ERROR, not silent drop.
- **Audit log required by manual review:** The review queue IS the audit log filtered to PENDING_REVIEW state. They are the same data model, not separate systems.
- **Idempotent write requires reading the cell first:** Sheets API read + write = 2 API calls per check-in. At high volume this consumes quota. Mitigation: maintain a local DB record of "already written" cells as primary dedup layer; Sheets read as secondary safety net.
- **Duplicate rejection must precede Sheets write:** Check (employee_id, shift_date, group_id) uniqueness in DB before touching Sheets API. Never rely on Sheets as the dedup source of truth.

---

## Behavior Specifications

Concrete expected behaviors for the five specific areas asked about.

### Employee Identification

**Priority order (apply in sequence, stop at first confident match):**

1. Caption text → normalize (lowercase, strip punctuation) → exact match against `employees.caption_aliases`
2. Caption text → fuzzy match (Levenshtein distance ≤ 2) against all aliases — if single match above threshold, use it with MEDIUM confidence
3. `message.from_user.id` → exact match against `employees.telegram_user_id` — HIGH confidence if found
4. Group has exactly one registered employee → accept with LOW confidence, flag for review
5. No match → route to PENDING_REVIEW with all candidate matches listed for operator

**Identification confidence → processing action:**
| Confidence | Action |
|-----------|--------|
| HIGH (exact caption or account match) | Auto-accept, write to Sheets |
| MEDIUM (fuzzy caption match, single candidate) | Auto-accept with warning logged; configurable per installation |
| LOW (single employee in group, no text match) | Route to PENDING_REVIEW |
| NONE (no match found) | Route to PENDING_REVIEW |

### Shift Date Resolution (Midnight Crossover)

**Problem:** A guard photo sent at 01:30 on Tuesday morning belongs to Monday's night shift.

**Solution:** Configurable shift windows per group with a `date_offset` field.

```
shift_windows table:
  group_id        → which group this applies to
  shift_label     → e.g. "night", "day"
  window_start    → e.g. 20 (8pm)
  window_end      → e.g. 6 (6am next day)
  date_offset     → -1 means "assign to yesterday's date"
```

**Resolution algorithm:**
1. Extract `message.date` (UTC) → convert to configured timezone for the group
2. Find matching shift window for the local time of day
3. Apply `date_offset` to get the logical shift date
4. If no window matches (e.g. photo at 14:00 when only night window is configured): route to PENDING_REVIEW with "no shift window match" reason — do NOT silently assign to today

**Edge case — midnight boundary (23:58 to 00:02):** Use UTC-precise timestamps, not string dates. The timezone conversion + window lookup handles this correctly if implemented properly. No special-casing needed.

### Duplicate Handling

**Definition of a duplicate:** Same `(employee_id, shift_date, group_id)` tuple already exists with state ACCEPTED in the processing log.

**On duplicate detection:**
- Create log entry with state `DUPLICATE_REJECTED`
- Include reference to original accepted entry
- Do NOT write to Sheets
- Do NOT silently discard — every photo gets a log record

**Configurable override:** Admin can promote a DUPLICATE_REJECTED entry to ACCEPTED (e.g. if first photo was wrong and operator manually corrected it). This must revert the first entry to SUPERSEDED and write to Sheets if the cell was already "1" (idempotent — no harm in writing "1" again).

### Manual Review Workflow

**Queue entry contains:**
- Original Telegram message link (t.me/c/group_id/msg_id)
- Photo thumbnail (fetched via Bot API `file_id`, not stored)
- Caption text (raw)
- Telegram sender info
- List of candidate employee matches (if any) with confidence scores
- Reason for routing to review
- Timestamp received

**Operator actions:**
1. **Accept with employee assignment** — select employee from dropdown, confirm shift date, submit → system writes to Sheets + closes queue entry
2. **Reject** — select reason (not a check-in photo, wrong group, spam) → log closes with REJECTED state, no Sheets write
3. **Escalate** — mark as needing supervisor review; no state change

**SLA:** Queue entries older than 4 hours should surface as alerts. This is not an MVP feature but should be designed into the data model (created_at on queue entry is sufficient).

### Audit Logging

**Every message processed must produce exactly one log record.** No silent outcomes.

**Log record fields:**
| Field | Type | Notes |
|-------|------|-------|
| id | UUID | Primary key |
| telegram_message_id | bigint | From Telegram |
| telegram_group_id | bigint | Group where photo was sent |
| received_at | timestamptz | When bot received it |
| sender_telegram_id | bigint | `message.from_user.id` |
| caption_raw | text | Verbatim caption text |
| resolved_employee_id | FK | Null if unresolved |
| identification_method | enum | CAPTION_EXACT / CAPTION_FUZZY / ACCOUNT / MANUAL / NONE |
| identification_confidence | enum | HIGH / MEDIUM / LOW / NONE |
| shift_date | date | Resolved logical date |
| shift_window_matched | FK | Which window rule applied |
| status | enum | ACCEPTED / DUPLICATE_REJECTED / PENDING_REVIEW / REJECTED / ERROR |
| rejection_reason | text | Null if accepted |
| sheets_cell_ref | text | e.g. "Sheet1!D7", null if not written |
| sheets_written_at | timestamptz | Null if not written |
| reviewed_by_operator_id | FK | Null if auto-processed |
| reviewed_at | timestamptz | Null if auto-processed |

**Immutability:** Log entries are never updated after state transition; state changes create new entries or append a review_events child table. This preserves the full history.

---

## MVP Definition

### Launch With (v1)

Minimum viable — validates that automation works end-to-end on real data.

- [ ] Photo message ingestion from configured Telegram groups
- [ ] Employee identification: caption exact + fuzzy match + account lookup
- [ ] Shift date resolution with configurable time windows
- [ ] Duplicate rejection with DB uniqueness constraint
- [ ] Google Sheets write with idempotent guard and retry on 429
- [ ] Processing audit log with all states
- [ ] Manual review queue with accept/reject in admin UI
- [ ] Employee registry CRUD in admin UI
- [ ] Group configuration CRUD (group → object, shift windows)

### Add After Validation (v1.x)

Features to add once v1 is live on real groups and operator feedback is available.

- [ ] Confidence score display in review queue — trigger: operators complain about too many review items
- [ ] Per-group caption parsing rules — trigger: groups with non-standard caption conventions identified
- [ ] Operator Telegram notifications for review queue — trigger: operators miss queue items due to not checking admin UI
- [ ] Graceful quota degradation with retry queue dashboard — trigger: Sheets 429 errors observed in production

### Future Consideration (v2+)

Defer until core system is validated and client confirms direction.

- [ ] Face recognition on check-in photos — requires GPU infra, labeled training data, privacy assessment; only pursue if caption-based system has high false-positive rate
- [ ] Integration with HR / payroll systems (1C, etc.) — out of scope per PROJECT.md
- [ ] Mobile app for operators — web interface sufficient for v1; reconsider based on usage patterns
- [ ] Predictive no-show alerts ("guard hasn't checked in, shift starts in 30 min") — requires shift schedule data, not just attendance records

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Photo ingestion from Telegram groups | HIGH | LOW | P1 |
| Caption-based employee identification | HIGH | MEDIUM | P1 |
| Shift date resolution (midnight crossover) | HIGH | MEDIUM | P1 |
| Duplicate rejection | HIGH | LOW | P1 |
| Google Sheets idempotent write | HIGH | MEDIUM | P1 |
| Processing audit log | HIGH | MEDIUM | P1 |
| Manual review queue | HIGH | MEDIUM | P1 |
| Employee registry admin CRUD | HIGH | LOW | P1 |
| Group / shift window config admin CRUD | HIGH | LOW | P1 |
| Telegram account identification (backup) | MEDIUM | LOW | P1 |
| Confidence scoring on identification | MEDIUM | MEDIUM | P2 |
| Retry queue / quota graceful degradation | MEDIUM | MEDIUM | P2 |
| Per-group caption parsing rules | MEDIUM | MEDIUM | P2 |
| Operator Telegram notifications (review) | MEDIUM | HIGH | P2 |
| Audit trail linking cell to message | MEDIUM | LOW | P1 (included in log) |
| Face recognition | LOW (v1) | VERY HIGH | P3 |
| Payroll integration | LOW (v1) | HIGH | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

---

## Competitor Feature Analysis

| Feature | DutyTick (Telegram-based) | TARGPatrol (guard management) | ShiftTracker (this project) |
|---------|--------------------------|------------------------------|----------------------------|
| Telegram-native check-in | Yes — text message | No — mobile app | Yes — photo in existing group |
| Photo verification | Premium add-on only | Yes (patrol photos) | Core feature (photo = trigger) |
| Google Sheets integration | Not documented | No | Yes — primary output |
| Works in existing group chats | Yes | No — dedicated app | Yes — no workflow change for guards |
| Midnight shift handling | Not documented | Yes | Yes — configurable windows |
| Manual review queue | Not documented | Limited | Yes — explicit queue with approval |
| Audit log per message | Not documented | Yes | Yes — immutable record per message |
| Scale: 200+ groups | Not documented | Yes | Designed for this scale |

**Key insight:** ShiftTracker's differentiating constraint is that it works inside existing Telegram group chats without changing guard behavior. Guards already send photos in their groups. The system is invisible to them. Competitors require behavior change (new app, new commands) — this system requires zero change from the guards.

---

## Sources

- [DutyTick — Telegram-Based Attendance Tracking](https://dutytick.com/) — competitor product in same space
- [Google Sheets API Usage Limits](https://developers.google.com/workspace/sheets/api/limits) — 300 writes/min per project, 60/min per user
- [Factorial HR — How to manage overnight shifts](https://help.factorialhr.com/en_US/shift-management/how-to-manage-overnight-shifts) — date_offset pattern for overnight shift date assignment
- [BizX — Cross Midnight Attendance Recording](https://www.bizxtechnologies.com/cross-midnight-attendance-recording-time-sheet-mobile/) — industry standard terminology for midnight crossover
- [PeopleStrong — HRMS Audit Log](https://www.peoplestrong.com/blog/hrms-audit-log/) — audit log field requirements
- [MyShyft — Approval Status Tracking](https://www.myshyft.com/blog/approval-status-tracking/) — manual review queue UX patterns
- [GitHub — TelegramAttendanceBot](https://github.com/AsutoshPati/TelegramAttendanceBot) — open-source reference for Telegram attendance patterns
- [n8n Community — Telegram Bot + Google Sheets Attendance](https://community.n8n.io/t/employee-attendance-tracker-with-telegram-bot-and-google-sheets/187992) — existing integration pattern
- [Empmonitor — Biometric Attendance System Guide](https://empmonitor.com/blog/biometric-attendance-system/) — duplicate prevention, audit requirements

---
*Feature research for: Automated shift check-in tracking via Telegram photo messages*
*Researched: 2026-04-10*
