# Phase 2: Google Sheets Integration - Research

**Researched:** 2026-04-10
**Domain:** gspread 6.x + asyncio integration, batch write architecture, rate-limit handling
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- Use `gspread` library with service account authentication (JSON key file)
- Service account email shared with target spreadsheet as editor
- Wrap synchronous gspread calls with `asyncio.get_event_loop().run_in_executor(None, ...)` for async compatibility
- Each group/object can have its own spreadsheet configured in `telegram_groups.sheet_id` and `telegram_groups.sheet_name`
- Rows = employees, columns = dates (headers in row 1, format: DD.MM or DD.MM.YYYY)
- Cell value "1" marks that employee showed up for that shift date
- Employee row mapping stored in `group_employees.sheet_row` (integer, 1-indexed)
- Date column resolved dynamically by scanning header row for matching date
- Background task runs every 5 seconds
- Collects all shift_records with sheet_write_status = PENDING
- Groups by spreadsheet_id for batch operations
- Uses gspread `batch_update` (single API call per spreadsheet) to write multiple cells
- After successful write: update sheet_write_status to WRITTEN + set written_at timestamp
- On API error: increment retry_count, set status to ERROR if retry_count > 5, otherwise keep PENDING
- Exponential backoff on rate limit (429): 2^retry_count seconds, max 60s
- Find employee row: use `group_employees.sheet_row` (pre-configured by admin)
- Find date column: scan header row (row 1) for matching date string
- Cache header row per spreadsheet for 5 minutes (avoid repeated reads)
- If date column not found: log error, set status to ERROR with reason "date_column_not_found"
- If sheet_row is 0 or null: log error, set status to ERROR with reason "employee_row_not_configured"
- After writing "1", also write the Telegram message link (source_link) in adjacent cell or notes
- Message link format: `https://t.me/c/{chat_id}/{message_id}`
- Before writing "1", check if cell already contains "1"; if yes: skip write, log as DUPLICATE_SHEET_SKIP
- PostgreSQL is source of truth — Sheets is display layer only
- If Sheets is down, nothing is lost — records stay PENDING in DB

### Claude's Discretion

- Exact gspread API calls and error handling
- Header row caching implementation
- Retry task lifecycle management
- Test mocking strategy for Google Sheets API

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SHEET-01 | System automatically writes "1" into cell (employee row + date column) in Google Sheets | gspread `worksheet.batch_update()` with A1 notation; column resolved by header scan; row from `group_employees.sheet_row` |
| SHEET-02 | System saves a link to the source message as the basis for the mark | `source_link` from ShiftRecord written to adjacent cell (col+1) in same batch_update payload |
| SHEET-03 | Repeated mark for same employee on same date does not create a duplicate; logged to journal | Pre-write cell read via `worksheet.get(range)` in same executor call; if "1" found, write DUPLICATE_SHEET_SKIP to ProcessingLog |
| SHEET-04 | Records are buffered and sent in batches to comply with API limits (60 req/min) | 5-second flush loop; groups PENDING records by spreadsheet_id; one `batch_update` call per spreadsheet per flush |
| SHEET-05 | On write error, record is saved in DB with PENDING status and retried | retry_count column on ShiftRecord; exponential backoff `2^retry_count` capped at 60s; status→ERROR after 5 retries |
</phase_requirements>

---

## Summary

Phase 2 adds a single background service — the Sheets writer — that consumes `ShiftRecord` rows with `sheet_write_status = PENDING` from PostgreSQL and writes them to Google Sheets via gspread. The architecture is a polling loop (every 5 seconds) that fetches all pending records, groups them by spreadsheet, resolves cell addresses, and issues one `worksheet.batch_update()` call per spreadsheet per flush cycle. Because gspread is synchronous, all API calls are offloaded to the default thread-pool executor via `asyncio.get_event_loop().run_in_executor(None, fn)`, keeping the asyncio event loop unblocked.

The schema needs two additions: a `written_at` timestamp and a `retry_count` integer on `ShiftRecord`, plus `sheet_id` and `sheet_name` columns on `TelegramGroup`. These require Alembic migrations. The `TelegramGroup.sheet_id` / `sheet_name` fields drive which spreadsheet and which worksheet tab each group writes to. The header row cache is a plain in-process dict keyed by `spreadsheet_id`, TTL managed with a stored timestamp — no external cache dependency needed.

The most important correctness invariant is that PostgreSQL is always updated before the function returns from the flush: either `WRITTEN`+`written_at` on success, or `retry_count` incremented on failure. This ensures the retry loop never loses a record even on process restart.

**Primary recommendation:** Implement the Sheets writer as an isolated `shifttracker/sheets/` module (writer, client, header cache). Wire it into `app.py` lifespan as a single background asyncio task alongside the existing pipeline workers. Keep gspread import-time initialisation lazy so unit tests never need real credentials.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| gspread | 6.2.1 | Google Sheets API v4 wrapper | Already in STACK.md; simplest correct abstraction over the REST API; handles auth, cell notation, batch operations |
| google-auth | 2.x | Service account credential loading | Required by gspread 6.x; `google-auth` replaced `oauth2client` in gspread 5+ |
| asyncio (stdlib) | — | Offload gspread calls to thread pool | `run_in_executor` is the locked decision; no extra library needed |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tenacity | 8.x | Exponential backoff decorator | Wrap the gspread executor call for 429 and 5xx retry; keeps retry logic declarative |
| loguru | 0.7.x | Structured logging | Already used in Phase 1; log every flush cycle with record count, errors, skips |

### Why NOT gspread-asyncio

The `gspread-asyncio` wrapper (v1.x) was considered but **should not be used here** because:

1. Its own README states it does not support bulk batch operations (the API predates gspread 6.x `batch_update`).
2. `run_in_executor` with plain gspread gives identical event-loop non-blocking behaviour with full access to `worksheet.batch_update()`.
3. The wrapper adds `AsyncioGspreadClientManager` lifecycle complexity that is not needed for a single-service-account, single-background-task pattern.

**Confidence:** HIGH (gspread-asyncio README confirmed; gspread 6.x `batch_update` confirmed via official docs)

### Installation

```bash
# Already in pyproject.toml as of Phase 1 stack (verify presence)
pip install gspread==6.2.1 google-auth

# Add to pyproject.toml [project.dependencies]
"gspread==6.2.1",
"google-auth>=2.0",
```

No new dev dependencies needed — mocking is done with `unittest.mock`.

---

## Architecture Patterns

### Recommended Module Structure

```
shifttracker/
└── sheets/
    ├── __init__.py
    ├── client.py        # gspread client factory: build_client(credentials_file) -> gspread.Client
    ├── header_cache.py  # in-process header row cache, TTL=300s
    ├── writer.py        # SheetsWriter class: flush loop, cell resolution, batch_update
    └── models.py        # SheetWriteRequest dataclass (optional, may be inline)
```

The `sheets/` module is a clean boundary — no other module imports gspread directly. All call sites use `SheetsWriter.start()` and the writer handles all Sheets I/O internally.

### Pattern 1: Background Flush Loop

**What:** An asyncio task that sleeps 5 seconds, wakes, queries DB for PENDING records, resolves cells, issues batch_update, updates DB statuses.

**When to use:** Always for this phase. The loop is started in `app.py` lifespan alongside `start_workers()`.

```python
# shifttracker/sheets/writer.py
import asyncio
from datetime import datetime
from loguru import logger

class SheetsWriter:
    def __init__(self, settings, session_factory):
        self._settings = settings
        self._session_factory = session_factory
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._flush_loop())
        logger.info("SheetsWriter background task started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(5)
            try:
                await self._flush()
            except Exception as e:
                logger.error(f"SheetsWriter flush error: {e}")

    async def _flush(self) -> None:
        async with self._session_factory() as session:
            pending = await _fetch_pending(session)
        if not pending:
            return
        # group by spreadsheet_id, resolve cells, batch_update
        ...
```

### Pattern 2: run_in_executor for gspread calls

**What:** All blocking gspread API calls are wrapped with `asyncio.get_event_loop().run_in_executor(None, fn)` using `functools.partial` for parameterised calls.

**Why:** gspread uses `requests` (synchronous HTTP). Calling it directly in an async function would block the event loop during network I/O.

```python
# Source: locked decision in CONTEXT.md; asyncio stdlib docs
import asyncio
import functools

async def _run_sync(fn, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        functools.partial(fn, *args, **kwargs)
    )

# Usage — reading header row:
header_row = await _run_sync(worksheet.row_values, 1)

# Usage — batch update:
await _run_sync(
    worksheet.batch_update,
    [{"range": "C5", "values": [["1"]]}, {"range": "D5", "values": [["https://t.me/c/..."]]}]
)
```

### Pattern 3: Header Row Cache

**What:** An in-process dict mapping `(spreadsheet_id, sheet_name)` to `(header_list, fetched_at)`. Cache TTL is 300 seconds. On cache miss or TTL expiry, the header row is re-read from Sheets via `run_in_executor`.

**Critical detail:** The header row read is itself an API call that counts against quota. Without caching, every flush cycle would consume one read + one write per spreadsheet. With caching, reads occur at most once every 5 minutes.

```python
# shifttracker/sheets/header_cache.py
from datetime import datetime, timedelta
from typing import Optional

_cache: dict[tuple[str, str], tuple[list[str], datetime]] = {}
CACHE_TTL = timedelta(seconds=300)

def get_cached(spreadsheet_id: str, sheet_name: str) -> Optional[list[str]]:
    key = (spreadsheet_id, sheet_name)
    if key in _cache:
        headers, fetched_at = _cache[key]
        if datetime.utcnow() - fetched_at < CACHE_TTL:
            return headers
    return None

def set_cached(spreadsheet_id: str, sheet_name: str, headers: list[str]) -> None:
    _cache[(spreadsheet_id, sheet_name)] = (headers, datetime.utcnow())

def invalidate(spreadsheet_id: str, sheet_name: str) -> None:
    _cache.pop((spreadsheet_id, sheet_name), None)
```

### Pattern 4: Cell Address Resolution

**What:** Given `sheet_row` (integer, from DB) and date string from `shift_date`, find the column index by scanning the header row. Convert row+col to A1 notation using `gspread.utils.rowcol_to_a1`.

```python
# Source: gspread.utils is part of gspread 6.x stdlib API
import gspread.utils

def resolve_cell(
    header_row: list[str],
    sheet_row: int,
    shift_date_str: str,  # "DD.MM" or "DD.MM.YYYY"
) -> tuple[str, str] | None:
    """Returns (value_cell_a1, link_cell_a1) or None if date not found."""
    for col_idx, header in enumerate(header_row, start=1):
        if header.strip() == shift_date_str:
            value_cell = gspread.utils.rowcol_to_a1(sheet_row, col_idx)
            link_cell = gspread.utils.rowcol_to_a1(sheet_row, col_idx + 1)
            return value_cell, link_cell
    return None
```

**Date string format:** The DB stores `shift_date` as a Python `date` object. Format it as `shift_date.strftime("%-d.%-m")` (Linux) or `shift_date.strftime("%#d.%#m")` (Windows) for the "D.M" form. Since production runs on Linux, use `%-d.%-m`. However, the header format may be `DD.MM` (zero-padded) — validate by reading an actual production header during integration testing.

**Important:** `strftime("%-d.%-m")` produces `"9.4"` not `"09.04"`. If the spreadsheet uses `"09.04"`, use `strftime("%d.%m")`. This must be confirmed against the actual client spreadsheet (flagged as a blocker in STATE.md).

### Pattern 5: Per-Spreadsheet Batching

**What:** Group all PENDING records by `(spreadsheet_id, sheet_name)` before issuing API calls. For each group, build a single `batch_update` payload covering all cells.

```python
# Pseudocode — full implementation in writer.py
from collections import defaultdict

groups: dict[tuple[str, str], list[ShiftRecord]] = defaultdict(list)
for record in pending_records:
    key = (record.spreadsheet_id, record.sheet_name)
    groups[key].append(record)

for (spreadsheet_id, sheet_name), records in groups.items():
    update_payload = []
    for rec in records:
        cells = resolve_cell(headers, rec.sheet_row, rec.shift_date_str)
        if cells:
            value_cell, link_cell = cells
            update_payload.append({"range": value_cell, "values": [["1"]]})
            update_payload.append({"range": link_cell, "values": [[rec.source_link]]})
    # One API call covers all records for this spreadsheet
    await _run_sync(worksheet.batch_update, update_payload)
```

### Schema Changes Required

Phase 2 needs two Alembic migrations:

**Migration 1 — extend `telegram_groups`:**
```sql
ALTER TABLE telegram_groups ADD COLUMN sheet_id VARCHAR(200);
ALTER TABLE telegram_groups ADD COLUMN sheet_name VARCHAR(200) DEFAULT 'Sheet1';
```

**Migration 2 — extend `shift_records`:**
```sql
ALTER TABLE shift_records ADD COLUMN written_at TIMESTAMPTZ;
ALTER TABLE shift_records ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0;
```

The `sheet_write_status` column already exists on `ShiftRecord` (`NOT_NEEDED | PENDING | WRITTEN | ERROR`). The `retry_count` column is new.

### app.py lifespan integration

```python
# Add to shifttracker/app.py lifespan, after start_workers()
from shifttracker.sheets.writer import SheetsWriter

sheets_writer = SheetsWriter(settings=settings, session_factory=async_session_factory)
await sheets_writer.start()
app.state.sheets_writer = sheets_writer

# In the shutdown section, before engine.dispose():
await sheets_writer.stop()
```

### Anti-Patterns to Avoid

- **One API call per record:** Never call `worksheet.update_cell(row, col, "1")` inside the pipeline worker when a ShiftRecord is created. The worker writes `sheet_write_status = PENDING` and exits. The Sheets writer handles all I/O.
- **Blocking gspread in async context:** Never call `gc.open_by_key(...)` or any gspread method without `run_in_executor`. Even credential refresh is synchronous.
- **Reading header row on every flush:** Without the cache, each 5-second flush cycle reads the header row for every active spreadsheet — consuming quota before any writes happen.
- **Using mutable default `self._buffer` shared across flushes without atomic swap:** The writer must atomically snapshot and clear the pending list to avoid processing the same record twice. In this implementation the DB is the buffer — records are fetched by query, not kept in memory, so this isn't an issue. However, if an in-memory buffer is introduced, use `batch, self._buffer = self._buffer, []` atomic swap.
- **Not updating DB status after successful write:** If the writer calls `batch_update` but crashes before updating `sheet_write_status = WRITTEN`, the next flush will re-process and attempt to write "1" again. The duplicate protection (check if cell already = "1") is the safety net for this case.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| A1 notation from row/col integers | Custom `chr(65 + col)` math | `gspread.utils.rowcol_to_a1(row, col)` | Handles cols beyond Z (AA, AB...) correctly; already in gspread |
| Service account credential loading | JSON parsing + manual token refresh | `google.oauth2.service_account.Credentials.from_service_account_file(path)` | Handles key rotation, token lifetime, scopes |
| HTTP 429 exponential backoff | Custom `while True: sleep(2**n)` | `tenacity.retry` with `wait_exponential` | Handles max wait, jitter, max attempts declaratively; well-tested |
| Thread-safe executor call wrapping | Custom thread pool | `asyncio.run_in_executor(None, fn)` | Uses the default `ThreadPoolExecutor` managed by asyncio; correct and zero-config |

**Key insight:** gspread handles all the Sheets API v4 HTTP complexity — authentication headers, JSON serialisation, error parsing, range expansion. The application only needs to provide credentials + a list of `{range, values}` dicts.

---

## Common Pitfalls

### Pitfall 1: Date Format Mismatch in Header Scan

**What goes wrong:** `resolve_cell` finds no column for a valid shift date. Records accumulate with status `ERROR / date_column_not_found`. No attendance is written.

**Why it happens:** The header row uses `"09.04"` (zero-padded) but the code formats shift_date as `"9.4"` (no padding), or vice versa. The exact format depends on how the client's spreadsheet was created — this is not standardised.

**How to avoid:** Read one real header cell from the production spreadsheet during integration testing before Phase 2 goes live. Normalise the format at resolution time: strip whitespace, try both `strftime("%d.%m")` and `strftime("%-d.%-m")` if the first doesn't match.

**Warning signs:** `date_column_not_found` errors in logs for dates that visually exist in the spreadsheet.

### Pitfall 2: gspread Client Not Thread-Safe Across Executor Calls

**What goes wrong:** Two concurrent `run_in_executor` calls using the same `gspread.Client` object corrupt each other's HTTP session state.

**Why it happens:** `gspread.Client` uses `requests.Session` under the hood, which is not thread-safe for concurrent use.

**How to avoid:** Either (a) create a new `gspread.Client` per flush cycle (safe, slight overhead), or (b) use a single-threaded executor (`ThreadPoolExecutor(max_workers=1)`) to serialise all gspread calls. Option (b) is recommended since the flush loop itself is sequential — only one flush runs at a time, so there is no concurrency issue with the default executor as long as the writer never fans out gspread calls across multiple concurrent tasks.

**Warning signs:** Intermittent `requests.exceptions.ConnectionError` or garbled responses from Sheets API under load.

### Pitfall 3: Credentials File Path Misconfiguration

**What goes wrong:** App starts but Sheets writes fail with `FileNotFoundError` or `google.auth.exceptions.DefaultCredentialsError`. The error may be swallowed in the flush loop and only visible in logs.

**Why it happens:** `GOOGLE_SHEETS_CREDENTIALS_FILE` env var is not set or points to the wrong path. The error surfaces only when the first flush runs, not at startup.

**How to avoid:** Validate credentials file existence and parse-ability at lifespan startup — before starting the flush task. Fail fast with a clear error message if the file is missing or malformed.

```python
# In app.py lifespan, before sheets_writer.start():
import os
cred_path = settings.google_sheets_credentials_file
if cred_path and not os.path.exists(cred_path):
    raise RuntimeError(f"GOOGLE_SHEETS_CREDENTIALS_FILE not found: {cred_path}")
```

**Warning signs:** All records stay in PENDING forever with no error log entries (executor call never reached).

### Pitfall 4: sheet_row = 0 or None Causes Wrong Cell Write

**What goes wrong:** An employee has `sheet_row = 0` or `sheet_row = NULL` in `group_employees`. `gspread.utils.rowcol_to_a1(0, col)` raises `IncorrectCellLabel` or writes to row 0 which is the header row, overwriting column headers.

**Why it happens:** Admin hasn't configured the employee's row number yet (new employee added to group but not mapped to the spreadsheet).

**How to avoid:** The locked decision covers this: check `sheet_row` before resolution; if zero or null, set `sheet_write_status = ERROR` with reason `"employee_row_not_configured"`. Never pass row=0 to gspread utils.

**Warning signs:** Spreadsheet header row contains "1" values; `IncorrectCellLabel` exceptions in logs.

### Pitfall 5: Retry Storm on Persistent Failures

**What goes wrong:** A spreadsheet is deleted or the service account loses access. Every flush cycle retries all records for that spreadsheet, incrementing `retry_count` rapidly. After `retry_count > 5` records are set to ERROR, but while they're retrying they consume quota and delay writes to healthy spreadsheets.

**Why it happens:** No circuit-breaker on per-spreadsheet errors.

**How to avoid:** After 3 consecutive errors for the same `spreadsheet_id` within one flush cycle, skip that spreadsheet for the remainder of the flush and log a warning. This is a medium-priority guard; the `retry_count > 5 → ERROR` rule is the primary protection.

**Warning signs:** Every flush log shows `ERROR` for the same spreadsheet_id; records for other spreadsheets are delayed.

---

## Code Examples

Verified patterns from official sources and locked decisions:

### Service Account Authentication

```python
# shifttracker/sheets/client.py
# Source: google-auth official docs + gspread 6.x oauth2 guide
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

def build_client(credentials_file: str) -> gspread.Client:
    """Build a synchronous gspread client from a service account JSON file."""
    creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
    return gspread.authorize(creds)
```

### Fetching and Opening a Worksheet

```python
# Source: gspread 6.x API docs (spreadsheet.get_worksheet_by_id / worksheet_by_title)
import functools
import asyncio

async def open_worksheet(
    gc: gspread.Client,
    spreadsheet_id: str,
    sheet_name: str,
) -> gspread.Worksheet:
    loop = asyncio.get_event_loop()
    spreadsheet = await loop.run_in_executor(
        None, functools.partial(gc.open_by_key, spreadsheet_id)
    )
    worksheet = await loop.run_in_executor(
        None, functools.partial(spreadsheet.worksheet, sheet_name)
    )
    return worksheet
```

### Reading Header Row (for cache population)

```python
# Source: gspread Worksheet.row_values() — confirmed in gspread 6.x docs
async def fetch_header_row(worksheet: gspread.Worksheet) -> list[str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, worksheet.row_values, 1)
```

### batch_update — Write Multiple Cells in One API Call

```python
# Source: gspread 6.x Worksheet.batch_update docs
# https://docs.gspread.org/en/latest/api/models/worksheet.html
async def batch_write(
    worksheet: gspread.Worksheet,
    updates: list[dict],  # [{"range": "C5", "values": [["1"]]}, ...]
) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        functools.partial(
            worksheet.batch_update,
            updates,
            value_input_option="RAW",
        ),
    )
```

### Retry with Exponential Backoff (tenacity)

```python
# Source: tenacity 8.x docs; pattern matches locked decision (2^retry_count, max 60s)
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import gspread.exceptions

@retry(
    retry=retry_if_exception_type(gspread.exceptions.APIError),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(6),  # matches retry_count > 5
    reraise=True,
)
async def batch_write_with_retry(worksheet, updates):
    await batch_write(worksheet, updates)
```

**Note:** `tenacity` wraps the async function directly. The `APIError` exception is raised by gspread for 429 and 5xx responses. The locked decision specifies tracking `retry_count` in the DB — this tenacity decorator is used for the single-flush-cycle retry, while the DB `retry_count` tracks cross-cycle persistence.

### Checking Existing Cell Value (Duplicate Protection)

```python
# Source: gspread Worksheet.get() — returns list of lists
async def cell_has_value(
    worksheet: gspread.Worksheet,
    cell_a1: str,
    expected: str = "1",
) -> bool:
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, functools.partial(worksheet.get, cell_a1)
    )
    if result and result[0] and result[0][0] == expected:
        return True
    return False
```

**Important quota note:** Each `worksheet.get()` call is one read request. Checking every cell before writing doubles the read quota. Implementation options:

1. **Include cell reads in the header row fetch** — not directly applicable, but reading the entire batch range in one call is possible.
2. **Skip pre-check, rely on Phase 1 dedup** — the DB `UniqueConstraint("employee_id", "shift_date")` on `shift_records` already prevents duplicate PENDING records in most cases. The cell pre-check is defence-in-depth per the locked decision; accept the extra read cost.
3. **Read all cells in one call** — use `worksheet.get("A1:ZZ1000")` or a targeted range to batch-read all cells that will be written, then check in-memory. This reduces N cell reads to 1 API call.

**Recommendation (Claude's discretion):** Use option 3 — build the full set of target cell addresses, read them in one `worksheet.batch_get(ranges)` call, check in memory, then write only cells that don't already contain "1". This uses one extra read API call per spreadsheet per flush but avoids N individual reads.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `oauth2client` for service account auth | `google-auth` (`google.oauth2.service_account`) | gspread 5.0 (2021) | oauth2client is unmaintained; google-auth is the current library |
| `worksheet.update_cell(row, col, value)` per write | `worksheet.batch_update([{range, values}, ...])` | gspread 3.x+ | One API call for N cells; critical for quota compliance |
| gspread-asyncio wrapper | `run_in_executor` with plain gspread | — | gspread-asyncio doesn't expose batch_update; plain gspread 6.x does |
| Hard-coded cell addresses | Header-row column scan + `rowcol_to_a1` | — | Dynamic column resolution survives spreadsheet edits |

**Deprecated/outdated:**

- `oauth2client`: Do not install; gspread 6.x raises `ImportError` if you try to pass oauth2client credentials
- `gspread-asyncio` for batch writes: Its README explicitly states batch operations are not supported; use `run_in_executor` with plain gspread instead
- `worksheet.update(range, values)` (single range per call): Functional but wastes quota; `batch_update` is strictly better

---

## Open Questions

1. **Date header format in the production spreadsheet**
   - What we know: The convention is DD.MM or DD.MM.YYYY (from CONTEXT.md)
   - What's unclear: Whether the client uses zero-padded (`"09.04"`) or non-padded (`"9.4"`) day/month values; whether a year suffix is always present
   - Recommendation: Read one real header cell before Phase 2 goes live. Add format-normalisation logic that tries both padded and non-padded forms, logging which one matched. This is flagged as a concern in STATE.md.

2. **`sheet_id` and `sheet_name` column absence from `telegram_groups`**
   - What we know: CONTEXT.md specifies these fields; the current `TelegramGroup` model in `models.py` does not have them
   - What's unclear: Whether a default `sheet_name = "Sheet1"` is always valid, or whether groups will use named tabs
   - Recommendation: Add both columns to the Alembic migration with nullable defaults (`sheet_id` nullable, `sheet_name` defaults to `"Sheet1"`). Records with `sheet_id = NULL` are skipped by the writer and logged.

3. **`retry_count` column absence from `shift_records`**
   - What we know: The `ShiftRecord` model has `sheet_write_status` but no `retry_count` or `written_at`
   - What's unclear: Nothing — these need to be added via migration
   - Recommendation: First task in Wave 0 is the Alembic migration adding both columns.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.23 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `asyncio_mode = "auto"`, `timeout = 10` |
| Quick run command | `pytest tests/ -x --timeout=10 -q` |
| Full suite command | `pytest tests/ --timeout=10` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SHEET-01 | Writer writes "1" to correct cell (row+column) | unit | `pytest tests/test_sheets_writer.py::test_write_one_cell -x` | Wave 0 |
| SHEET-01 | Date column not found → ERROR status + reason | unit | `pytest tests/test_sheets_writer.py::test_date_column_not_found -x` | Wave 0 |
| SHEET-01 | sheet_row=None → ERROR status + reason | unit | `pytest tests/test_sheets_writer.py::test_employee_row_not_configured -x` | Wave 0 |
| SHEET-02 | Source link written to adjacent cell | unit | `pytest tests/test_sheets_writer.py::test_source_link_written -x` | Wave 0 |
| SHEET-03 | Cell already "1" → skip write, log DUPLICATE_SHEET_SKIP | unit | `pytest tests/test_sheets_writer.py::test_duplicate_sheet_skip -x` | Wave 0 |
| SHEET-04 | Multiple records batched into one batch_update call | unit | `pytest tests/test_sheets_writer.py::test_batch_groups_by_spreadsheet -x` | Wave 0 |
| SHEET-05 | API error → retry_count incremented, status stays PENDING | unit | `pytest tests/test_sheets_writer.py::test_retry_on_api_error -x` | Wave 0 |
| SHEET-05 | retry_count > 5 → status set to ERROR | unit | `pytest tests/test_sheets_writer.py::test_max_retries_sets_error -x` | Wave 0 |
| SHEET-05 | 429 response → exponential backoff applied | unit | `pytest tests/test_sheets_writer.py::test_429_backoff -x` | Wave 0 |

**Mocking strategy (Claude's discretion):** All gspread API calls are mocked with `unittest.mock.AsyncMock` and `MagicMock`. The `_run_sync` helper is patched to return mock values synchronously. Tests use the existing `async_session` SQLite fixture from `tests/conftest.py`. No real Google credentials are needed in tests.

### Sampling Rate

- **Per task commit:** `pytest tests/test_sheets_writer.py -x --timeout=10 -q`
- **Per wave merge:** `pytest tests/ --timeout=10`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_sheets_writer.py` — all SHEET-01..05 test cases (file does not exist yet)
- [ ] `tests/test_header_cache.py` — TTL expiry, cache hit, cache miss
- [ ] `shifttracker/sheets/__init__.py` — module must exist before tests can import
- [ ] Alembic migration: `alembic revision --autogenerate -m "add_sheets_fields"` — adds `written_at`, `retry_count` to `shift_records`; `sheet_id`, `sheet_name` to `telegram_groups`
- [ ] `pyproject.toml` — add `gspread==6.2.1` and `google-auth>=2.0` to `[project.dependencies]`

---

## Sources

### Primary (HIGH confidence)

- gspread 6.2.1 official docs — `Worksheet.batch_update()` method signature, `row_values()`, `get()`: https://docs.gspread.org/en/master/api/models/spreadsheet.html
- gspread 6.x Worksheet docs — `batch_update` data format confirmed: https://docs.gspread.org/en/latest/api/models/worksheet.html
- `.planning/research/STACK.md` — gspread 6.2.1 version, google-auth 2.x, asyncio strategy, rate limits
- `.planning/research/PITFALLS.md` — Sheets quota: 60 req/min/user, 300 req/min/project; batch_update = 1 request regardless of N ranges
- `.planning/research/ARCHITECTURE.md` — `SheetsWriter` design pattern, flush interval, buffer architecture
- `shifttracker/db/models.py` — `ShiftRecord.sheet_write_status` column, `GroupEmployee.sheet_row`, existing model constraints
- `shifttracker/app.py` — lifespan pattern, how to add the writer task alongside existing workers
- `shifttracker/pipeline/worker.py` — confirmed `sheet_write_status="PENDING"` set at record creation (line 98)

### Secondary (MEDIUM confidence)

- gspread-asyncio GitHub README — confirmed batch_update not supported by wrapper; run_in_executor is the correct approach: https://github.com/dgilman/gspread_asyncio
- tenacity 8.x PyPI — `retry_if_exception_type`, `wait_exponential` pattern: https://pypi.org/project/tenacity/
- Google Sheets API official limits — 60 write req/min/user, 300/min/project: https://developers.google.com/workspace/sheets/api/limits

### Tertiary (LOW confidence — flag for validation)

- Date header format (DD.MM vs D.M): assumed from CONTEXT.md description, not verified against actual client spreadsheet

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — gspread 6.2.1 confirmed; run_in_executor pattern confirmed; google-auth requirement confirmed
- Architecture: HIGH — directly derived from locked decisions in CONTEXT.md and existing code in app.py/worker.py
- Pitfalls: HIGH — rate limit numbers from official Google docs; thread-safety pitfall from gspread internals knowledge (requests.Session)
- Date format: LOW — client spreadsheet format not directly verified; flagged as open question

**Research date:** 2026-04-10
**Valid until:** 2026-05-10 (gspread 6.x is stable; Google Sheets API v4 is stable with no deprecation notices)
