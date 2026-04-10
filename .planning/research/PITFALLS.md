# Pitfalls Research

**Domain:** Telegram bot + Google Sheets shift tracking at scale (200 groups, thousands of photos/day)
**Researched:** 2026-04-10
**Confidence:** HIGH (Telegram API limits verified via official docs; Sheets limits verified via official docs; architecture patterns from multiple corroborating sources)

---

## Critical Pitfalls

### Pitfall 1: Bot Privacy Mode Blocks All Photo Messages

**What goes wrong:**
The bot is added to 200 groups, polling starts, and zero messages arrive — not because photos aren't being sent, but because Telegram's privacy mode is ON by default for all bots. In privacy mode, a bot only receives messages explicitly directed at it (commands, replies to the bot, @mentions). Ordinary photo messages from employees are silently invisible to the bot.

**Why it happens:**
Privacy mode is opt-out and requires a BotFather setting change plus the bot being re-added to each group after the change. Developers test in a private chat or a group where they are admin and miss the issue entirely until deploying to real groups.

**How to avoid:**
Disable privacy mode via BotFather (`/setprivacy` → Disable) before any group integrations. After changing the setting, the bot must be removed and re-added to every existing group. Alternatively, make the bot an admin in each group — admins always receive all messages regardless of privacy mode. For 200 groups, admin status is the more reliable long-term approach.

**Warning signs:**
- Bot receives zero `message` updates despite active group traffic
- Bot receives only updates it directly triggered (its own commands or replies to it)
- No errors in logs, just silence

**Phase to address:**
Phase 1 (Telegram Bot Infrastructure) — verify and document the required BotFather configuration and group onboarding procedure before any other development.

---

### Pitfall 2: Google Sheets Write Quota Exhausted at Scale

**What goes wrong:**
At peak load (shift start times), hundreds of employees simultaneously send check-in photos. Each photo triggers a write to Google Sheets. With 200 groups, each group potentially having 10-50 employees checking in within the same 5-minute window, the bot hits the **60 write requests per minute per user per project** quota. Writes fail with HTTP 429, the shift record is lost, and the employee appears absent in the report.

**Why it happens:**
Developers test with 1-2 groups at low frequency and the quota never triggers. At real scale, shift windows create synchronized write bursts that are completely different from development patterns. The 60 req/min limit is per-user (the service account), not per-spreadsheet.

**How to avoid:**
1. Never write immediately on photo receipt. Buffer all writes in PostgreSQL first, mark as "pending sync."
2. Use a dedicated Sheets writer worker that batches writes via `spreadsheets.values.batchUpdate` — one API call can update N cells across N rows. A single `batchUpdate` counts as **one request** regardless of how many ranges it covers.
3. Implement exponential backoff with jitter on 429 responses.
4. Keep the "source of truth" in PostgreSQL; Sheets is a display layer only. A failed Sheets write is recoverable; a lost database record is not.

**Warning signs:**
- HTTP 429 errors in logs during morning shift windows (06:00-09:00) but not at other times
- Growing backlog of "pending sync" records
- Sheets showing fewer check-ins than the database

**Phase to address:**
Phase 2 (Google Sheets Integration) — implement the buffer/batch write architecture from day one, not as a retrofit.

---

### Pitfall 3: Midnight Crossover Assigns Check-in to Wrong Shift Date

**What goes wrong:**
Night shift employees (e.g., 22:00-06:00) send their check-in photo at 23:45 on Monday. The system records the shift date as "Monday" because `datetime.now().date()` returns Monday. The spreadsheet row for Monday already has their name marked, but Tuesday's row — where the night shift outcome is reported — remains blank. The supervisor sees Monday's column fine, but Tuesday's column shows the night-shift guard as absent.

A subtler variant: a guard checks in at 00:15. The system assigns Tuesday as the shift date, but supervisors think of this night shift as "Monday's shift" because it started on Monday evening.

**Why it happens:**
Wall-clock date is used directly as shift date without considering shift windows. Business logic of "which shift does this timestamp belong to" is never encoded; only "what date is this timestamp."

**How to avoid:**
Implement a `resolve_shift_date(timestamp, group_id)` function that maps a timestamp to a shift using configured windows per group:
- Each group has configurable shift windows: `{"day": (06:00, 22:00), "night": (22:00, 06:00+1)}`
- Night shifts spanning midnight belong to the calendar date the shift *started* on
- Times between 00:00 and 06:00 in groups with night shifts resolve to the *previous* calendar day
- Default behavior (no night shifts configured): use calendar date as-is

Store the *resolved shift date* in the database, not the raw timestamp. Never derive the shift date at query time from the raw timestamp.

**Warning signs:**
- Night-shift guards showing as absent in their shift column
- Duplicate entries in adjacent date columns for night-shift groups
- Supervisor complaints that guards who "definitely showed up" appear absent on certain calendar days

**Phase to address:**
Phase 1 (Core Logic) — the shift date resolver must be built and unit-tested before any Sheets integration. Include explicit test cases: 23:45, 00:01, 00:15, 06:00 boundary.

---

### Pitfall 4: Duplicate Check-in Records Corrupt Attendance Data

**What goes wrong:**
Telegram delivers the same update more than once when the bot restarts mid-delivery, the webhook times out and Telegram retries, or the bot processes the same `update_id` twice during polling offset mismanagement. Result: one employee gets two "1" marks in the same cell or, worse, a second worker writes to an adjacent cell, corrupting the sheet layout.

**Why it happens:**
Telegram guarantees at-least-once delivery. Webhooks are retried if the server returns non-200. Polling with `getUpdates` re-delivers updates if the offset is not correctly advanced. Under restarts or crashes, the offset state may not be persisted, causing reprocessing of already-handled updates.

**How to avoid:**
Use the Inbox Pattern in PostgreSQL:
```sql
CREATE TABLE processed_updates (
    update_id BIGINT PRIMARY KEY,
    processed_at TIMESTAMPTZ DEFAULT NOW()
);
```
On every incoming update, attempt `INSERT INTO processed_updates (update_id) VALUES ($1) ON CONFLICT DO NOTHING`. If zero rows inserted, the update is a duplicate — skip processing entirely. This check must happen *before* any business logic and *within the same transaction* as writing the attendance record. Persist the polling offset to the database after each confirmed write, not in memory.

**Warning signs:**
- Duplicate rows in the `attendance_log` table for the same `(employee_id, shift_date)`
- Sheets cells showing "11" or formula errors instead of "1"
- Log entries showing the same `message_id` processed twice

**Phase to address:**
Phase 1 (Telegram Bot Infrastructure) — deduplcation must be in the message handler from the first commit. Adding it as a retrofit forces reprocessing historical data.

---

### Pitfall 5: Employee Identification Ambiguity Causes Silent Wrong Assignments

**What goes wrong:**
Two employees named "Иванов" work in different groups. One group has a `username` match, the other has caption-only matching. The caption "Иванов заступил" matches on surname alone. The bot assigns the check-in to the wrong Иванов (or creates a new unknown record), and neither employee appears correctly in the spreadsheet. No error is raised — the match is confident but wrong.

A secondary variant: an employee sends the check-in photo from a personal account (no username, or a different username than registered) while a colleague types the caption. The bot matches the caption to the wrong person.

**Why it happens:**
The matching algorithm is greedy — it finds "a match" and proceeds. There is no concept of "ambiguous match" that routes to manual review. The registry lookup is keyed on either username OR caption keyword, not requiring both to confirm.

**How to avoid:**
Implement a three-tier confidence model:
1. **HIGH confidence** (auto-approve): `telegram_user_id` matches exactly in the employee registry for this group
2. **MEDIUM confidence** (auto-approve + log for review): `username` matches with caption containing expected keywords
3. **LOW confidence** (mandatory manual review): caption-only match, or match produces more than one candidate

Write a `match_employee(message, group_id) → (employee, confidence, candidates)` function. Anything below HIGH confidence queues to manual review rather than auto-writing to Sheets. Never auto-write on ambiguous matches.

**Warning signs:**
- Manual review queue is always empty (the algorithm never escalates — bad)
- An employee complains their check-in was not recorded but the DB shows a record under a different employee
- The same time slot shows two different employees from the same group

**Phase to address:**
Phase 1 (Employee Identification Logic) — confidence tiers and the manual review queue must be designed before integration testing with real group members.

---

### Pitfall 6: Group-to-Supergroup Migration Breaks Chat ID References

**What goes wrong:**
A regular Telegram group with <200 members is upgraded to a supergroup (either manually by admin or automatically when certain features are enabled). The group's `chat_id` changes from a positive integer to a negative integer in the format `-100XXXXXXXXXX`. All existing database records mapping `group_id → employees` and `group_id → spreadsheet` now point to a dead chat ID. The bot stops receiving messages from that group and silently fails.

**Why it happens:**
Developers store the initial `chat_id` at group onboarding time and never handle the `migrate_to_chat_id` service message. Telegram sends this message to the old chat ID once migration occurs, but if the handler is missing, it is silently dropped.

**How to avoid:**
Implement a handler for `MigrateFromChatId` and `MigrateToChatId` service messages:
```python
@dp.message(F.migrate_to_chat_id)
async def handle_migration(message: Message):
    old_id = message.chat.id
    new_id = message.migrate_to_chat_id
    await group_service.update_chat_id(old_id, new_id)
```
Store `chat_id` in a dedicated `groups` table with an indexed lookup. Log all migrations to an audit trail.

**Warning signs:**
- A group suddenly stops producing records in the database
- Bot API returns `"Bad Request: group chat was upgraded to a supergroup chat"` with a `migrate_to_chat_id` field in the error
- The group is still active in Telegram but invisible to the bot

**Phase to address:**
Phase 1 (Telegram Bot Infrastructure) — migration handler should be part of the initial group event handlers.

---

### Pitfall 7: Bot Restart Causes Update Gap (Photos Lost During Downtime)

**What goes wrong:**
The bot is restarted for a deployment. During the 2-minute downtime, 30 employees send check-in photos. Telegram buffers updates for **up to 24 hours**. If using webhooks with `drop_pending_updates=True` (common in tutorials), all buffered updates are discarded. If using long-polling and the offset is not persisted, getUpdates starts from the last confirmed update but the application may crash before committing. Either way, photos sent during downtime are lost.

**Why it happens:**
Tutorial code uses `skip_updates=True` in aiogram's polling start or `drop_pending_updates` in webhook setup to "avoid processing stale messages" — a reasonable choice for interactive bots but catastrophic for attendance tracking where every message has business value.

**How to avoid:**
- For webhooks: never use `drop_pending_updates=True`. Telegram holds updates for 24 hours — process the backlog on startup.
- For polling: persist the last processed `update_id` to PostgreSQL, not in memory. On startup, read the stored offset and resume from there.
- On startup, explicitly process the update backlog at a controlled rate before entering normal processing mode.
- Implement a startup alert: "Resuming from offset X, processing Y buffered updates" — operators know downtime caused a backlog.

**Warning signs:**
- Absence spikes in the spreadsheet that correlate exactly with deployment times
- Employee complaints about "definitely sent the photo" with no database record
- Log shows zero updates processed in the 5 minutes after startup despite the group being active

**Phase to address:**
Phase 1 (Telegram Bot Infrastructure) — startup recovery must be validated with an explicit test: send messages while the bot is down, restart, verify all are processed.

---

### Pitfall 8: Telegram Rate Limit on Outbound Responses Causes Queue Starvation

**What goes wrong:**
The bot sends confirmation messages ("Check-in recorded") back to each group after processing. At peak load with 200 groups and simultaneous check-ins, the bot attempts to send 200 confirmation messages within seconds. Telegram enforces a **30 messages/second global limit** and a **20 messages/minute per chat limit**. The bot receives 429 RetryAfter errors and backs off — but the backoff queue blocks incoming update processing in naive single-threaded implementations, causing fresh photos to pile up unprocessed.

**Why it happens:**
Sending and receiving are conflated in the same async event loop without separation. Backoff on sends blocks the handler loop.

**How to avoid:**
Separate incoming update processing from outgoing notification dispatch:
- Process incoming photo → write to DB → ack immediately (return 200 to webhook)
- Send confirmation via a separate background task or queue with rate limiting
- Use aiogram's built-in `AioRateLimiter` middleware which handles 429 RetryAfter automatically
- Make confirmation messages optional/configurable — silence is acceptable for an audit system

**Warning signs:**
- `RetryAfter` errors appearing in logs during peak shift windows
- Incoming update processing slows down at exactly the times many check-ins happen simultaneously
- Confirmation messages delayed by 10+ minutes while database writes succeed immediately

**Phase to address:**
Phase 1 (Telegram Bot Infrastructure) — rate limiter middleware should be installed from the start, not retrofitted.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Write directly to Sheets on message receipt | Simpler code, no queue | 429 quota exhaustion at scale, lost records | Never for production; OK for single-group prototype only |
| Use wall-clock date as shift date | No config needed | Night shifts assigned to wrong column, silent data corruption | Never — implement shift windows even if empty |
| Skip deduplication for MVP | Faster to build | Duplicate attendance records requiring manual correction, data audit trail destroyed | Never — inbox pattern is 10 lines of SQL |
| Store chat_id as constant | Simple setup | Breaks permanently on group migration, no recovery path | Only for one-off scripts never maintained |
| Use `drop_pending_updates=True` | Clean state on restart | Lost attendance records during deployment | Never for attendance tracking |
| In-memory offset tracking for polling | Simpler restart logic | Lost updates on crash | Never — persist to DB |
| Caption-only employee matching without review queue | Fewer manual interventions | Wrong employee gets credit, trust in system destroyed | Never without confidence tier + fallback |
| Single spreadsheet for all groups | Simpler Sheets layout | Single-cell-write conflicts, 60 req/min exhausted faster | Only for fewer than 5 groups at low volume |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Telegram Bot API | Forgetting to disable privacy mode before adding bot to groups | Set via BotFather `/setprivacy` first, then add to groups (or use admin role) |
| Telegram Bot API | Using the same file_id across different bots | file_id is bot-specific — cannot be shared between bot tokens |
| Telegram Bot API | Assuming message.from_user is always set | In channels forwarded to groups, `from_user` may be None; always check before accessing |
| Telegram Bot API | Not handling `message.photo` as a list | Photos arrive as an array of sizes; always take `message.photo[-1]` for the highest resolution |
| Google Sheets API | One API call per attendance write | Use `batchUpdate` — group all pending writes into a single call |
| Google Sheets API | Writing to cells by absolute address hardcoded at dev time | Rows shift when lines are inserted; use named ranges or a header-lookup pattern to find columns by name |
| Google Sheets API | Using a personal OAuth token instead of a Service Account | Personal tokens expire and require browser re-auth; service accounts are headless |
| Google Sheets API | Not checking if the spreadsheet ID exists before writing | 404 on an invalid spreadsheet silently fails if exceptions are swallowed |
| aiogram + FastAPI | Running both in the same process with blocking calls | FastAPI and aiogram both need the asyncio event loop; ensure no blocking I/O in handlers |
| PostgreSQL + asyncio | Using synchronous SQLAlchemy driver with async code | Use `asyncpg` or `SQLAlchemy[asyncio]` — sync drivers block the event loop under load |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Synchronous Sheets writes inline with message handler | Handler loop latency increases, 429 errors block photo processing | Buffer in PostgreSQL, write asynchronously in background worker | > 5 simultaneous check-ins in any group |
| Reading the full spreadsheet to find cell position on every write | Slow writes (1-3 seconds per record), quota consumed on reads too | Cache spreadsheet structure (row/column map) in memory on startup, refresh daily | > 10 writes/minute |
| Processing updates sequentially in a single asyncio task | Throughput cap ~50 photos/minute, queue grows unbounded | Use aiogram's concurrent handler dispatch; fan out to worker pool for DB writes | > 20 active groups simultaneously |
| Full table scan in PostgreSQL to check deduplication | Latency spike under write bursts | Index on `(chat_id, message_id)` in the processed_updates table | > 10,000 rows in the table (days of operation) |
| Logging all photo file metadata to disk synchronously | Disk I/O blocks async loop, latency increases | Use async logging or structured log to PostgreSQL | > 100 photos/minute |
| Fetching employee registry from DB on every message | DB connection pool exhaustion under load | Cache the registry in memory (Redis or in-process dict), refresh on config change event | > 50 concurrent messages |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Accepting check-in photos from any Telegram user in a group | Employees not on the roster can generate attendance records for arbitrary names | Validate `from_user.id` against the employee registry; unknown user IDs go to manual review |
| Bot token stored in source code or `.env` committed to git | Token theft allows full bot impersonation, group spam, data exfiltration | Store token in environment variable or secrets manager; never commit `.env`; rotate token immediately if exposed |
| Google Service Account credentials JSON committed to repo | Full Google Sheets access for any attacker who reads the repo | Store credentials path in environment variable; use Secret Manager in production |
| No rate limiting on the admin web interface | Brute-force attacks on operator login | Implement request rate limiting on FastAPI endpoints (slowapi or nginx) |
| Trusting caption text as authoritative employee identifier without cross-check | An employee can type any colleague's name to generate a false attendance record for them | Always cross-validate caption match against `from_user.id` or `username`; log the raw message for audit |
| Serving webhook over HTTP | Man-in-the-middle can inject fake updates | Telegram requires HTTPS with a valid TLS certificate; use Let's Encrypt or Cloudflare |

---

## UX Pitfalls (Operator Interface)

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Manual review queue has no SLA or notification | Ambiguous check-ins pile up unresolved, nightly Sheets sync runs with gaps | Alert operator on new manual review items via Telegram message or email |
| Admin interface shows all 200 groups in one unsorted list | Impossible to find a specific group quickly | Group by organization/division, add search, show last-activity timestamp |
| No visibility into "what happened to this message" | Operator cannot explain to guard why check-in was not recorded | Every incoming message gets a log entry with status: accepted / rejected / manual_review / duplicate / error |
| Spreadsheet sync errors shown nowhere in the UI | Silent data loss; Sheets show fewer records than actual check-ins | Show sync status per group: "last synced 5 min ago — 3 pending writes" |
| Shift window configuration is global, not per-group | Night-shift groups and day-only groups share the same time boundaries | Shift windows must be configurable per group, with a sensible default |

---

## "Looks Done But Isn't" Checklist

- [ ] **Privacy mode disabled:** The bot added to a test group actually receives plain photo messages (not just /commands). Verify by sending a photo without any @mention and confirming a DB record is created.
- [ ] **Midnight shift logic:** Send a test photo at 23:50 in a group configured for night shifts and verify the resolved shift date is the current calendar day, not tomorrow.
- [ ] **Duplicate protection:** Send the same `update_id` twice (simulate webhook retry) and verify exactly one DB record is created.
- [ ] **Group migration handler:** Simulate migration by updating the `chat_id` in the DB manually to the supergroup ID and verify the bot continues receiving messages.
- [ ] **Sheets quota under load:** Fire 70 write requests within one minute and verify all are eventually written (via retry queue) with no silent data loss.
- [ ] **Update recovery on restart:** Send photos while the bot is stopped, restart the bot, verify all missed photos are processed within 60 seconds of startup.
- [ ] **Ambiguous employee escalation:** Send a photo with a caption matching two employees and verify it lands in the manual review queue, not auto-assigned.
- [ ] **Service account authentication:** Revoke and re-grant service account access; verify the bot reconnects without operator intervention.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Privacy mode not disabled — messages never received | HIGH | Disable in BotFather, re-add bot to all affected groups, manually enter missed attendance for the gap period |
| Sheets quota exhaustion — writes lost | MEDIUM | All writes buffered in PostgreSQL; retry worker catches up automatically once the 429 clears; verify gap in Sheets vs DB |
| Midnight crossover — wrong date column | MEDIUM | Identify affected records in DB by shift window, run a migration script to correct resolved_shift_date, re-sync Sheets |
| Duplicate records written to Sheets | LOW | Deduplicate DB records with SQL (keep earliest per employee+date), re-run Sheets sync for affected date range |
| Group migration — chat_id dead | MEDIUM | Query Telegram for current supergroup ID, update `groups.chat_id` in DB, no historical data loss |
| Update gap on restart (wrong offset or drop_pending) | HIGH | If within 24 hours: Telegram still has buffered updates — correct offset and restart. Beyond 24 hours: manual entry required for the gap |
| Wrong employee assigned (ambiguity) | MEDIUM | Audit log contains raw message data; manual correction in admin UI; re-sync affected spreadsheet cell |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Privacy mode blocking messages | Phase 1: Telegram Bot Infrastructure | Integration test: photo in group → DB record created |
| Sheets quota exhaustion | Phase 2: Google Sheets Integration | Load test: 70 write requests in 60 seconds, all eventually persisted |
| Midnight crossover wrong date | Phase 1: Core Business Logic | Unit tests with timestamps at 23:50, 00:01, 00:15, 06:00 for each shift type |
| Duplicate check-in records | Phase 1: Telegram Bot Infrastructure | Inject duplicate update_id, assert exactly 1 DB record |
| Employee identification ambiguity | Phase 1: Employee Identification | Unit tests: single match → auto-approve; two matches → manual review queue |
| Group-to-supergroup migration | Phase 1: Telegram Bot Infrastructure | Handler test: process migrate_to_chat_id message, verify DB updated |
| Update gap on restart | Phase 1: Telegram Bot Infrastructure | Restart test: messages sent during downtime processed on resume |
| Outbound rate limit blocking inbound | Phase 1: Telegram Bot Infrastructure | Rate limiter middleware installed; load test at 30 simultaneous sends |

---

## Sources

- Telegram Bot API official documentation — Privacy mode: https://core.telegram.org/bots/features
- Telegram Bot API official FAQ — Rate limits (30 msg/s global, 20 msg/min per group): https://core.telegram.org/bots/faq
- Google Sheets API official limits — 60 write req/min/user, 300 req/min/project: https://developers.google.com/workspace/sheets/api/limits
- Google Sheets API batch update guide: https://developers.google.com/workspace/sheets/api/guides/batchupdate
- Telegram group migration behavior (chat_id change): https://github.com/tdlib/telegram-bot-api/issues/266
- aiogram GitHub discussion on rate limit with getUpdates: https://github.com/aiogram/aiogram/discussions/1422
- Telegram limits reference: https://limits.tginfo.me/en
- Inbox Pattern for idempotency: https://dev.to/actor-dev/inbox-pattern-51af
- Deduplication in distributed systems: https://www.architecture-weekly.com/p/deduplication-in-distributed-systems
- GramIO rate limits guide: https://gramio.dev/rate-limits

---
*Pitfalls research for: Telegram shift tracking bot (ShiftTracker) — Telegram + Google Sheets + Python/aiogram*
*Researched: 2026-04-10*
