# Phase 1: Foundation - Context

**Gathered:** 2026-04-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Telegram bot receives photo messages from connected groups, identifies employees, resolves shift dates, deduplicates messages, and records every outcome in the audit log. No UI, no Google Sheets writes — pure pipeline from Telegram to PostgreSQL.

</domain>

<decisions>
## Implementation Decisions

### Employee Identification Strategy
- Confidence ladder (checked in order):
  1. **Telegram account match** — user_id привязан к сотруднику в справочнике (highest confidence)
  2. **Caption exact match** — подпись содержит точное совпадение с ФИО/позывным/табельным номером
  3. **Caption keyword match** — подпись содержит ключевые слова из шаблонов идентификации группы
  4. **Single-employee group fallback** — если в группе привязан только один сотрудник, и фото от любого участника → этот сотрудник
  5. **No match → NEEDS_REVIEW** — ни один метод не сработал, отправляем на ручную проверку
- Если по подписи определяется несколько сотрудников — создаём отдельную запись для каждого
- Case-insensitive matching для подписей
- Подпись нормализуется: trim, collapse whitespace, lowercase для сравнения

### Shift Date Resolution
- Каждая группа/объект имеет настраиваемое окно смены: `shift_start_hour` и `shift_end_hour`
- Дефолтное окно: 06:00 — 22:00 (дневная смена)
- Для ночных смен (например 22:00 — 06:00): фото в 01:30 относится к предыдущему дню
- Алгоритм: `resolve_shift_date(message_datetime, shift_start_hour, shift_end_hour)` — если время сообщения < shift_start_hour и ночная смена активна, дата = вчера
- Фото за пределами ±2 часов от окна смены → NEEDS_REVIEW с причиной "outside_time_window"
- Часовой пояс: UTC+3 (Москва) по умолчанию, настраиваемый для каждой группы

### Edge Case Handling
- **Фото без подписи:** если Telegram user_id привязан к сотруднику → обработать; иначе → NEEDS_REVIEW с причиной "no_caption_no_account_match"
- **Несколько фото подряд от одного сотрудника за одну смену:** первое принимается, остальные логируются как DUPLICATE_SAME_SHIFT
- **Фото-документ (file, не photo):** игнорировать, обрабатываем только сжатые фото (photo object в Telegram API)
- **Пересланные сообщения:** игнорировать (forward_from != null), т.к. это не факт заступления
- **Отредактированное сообщение:** не переобрабатывать (update_id уже обработан)
- **Удалённое сообщение:** не откатывать отметку, но логировать событие удаления
- **Нерелевантные фото (мемы, скриншоты и т.д.):** на уровне v1 не фильтруем по содержимому — если фото подходит по идентификации и окну, оно принимается

### Message Processing Pipeline
- Ingestion → Dedup (update_id) → Filter (has photo?) → Identify (employee) → Resolve Date → Business Dedup (employee+date) → Write to DB → Queue for Sheets (Phase 2)
- asyncio.Queue с 8 worker coroutines для параллельной обработки
- Bounded queue (maxsize=500) для backpressure
- Все этапы логируются в processing_log с таймстемпами

### Database Schema Approach
- `employees` — справочник сотрудников (name, telegram_user_id, employee_code)
- `telegram_groups` — подключённые группы (chat_id, name, shift_start_hour, shift_end_hour, timezone)
- `group_employees` — привязка сотрудников к группам (many-to-many + sheet_row для Phase 2)
- `caption_rules` — шаблоны подписей для групп (group_id, pattern, employee_id)
- `shift_records` — записи о сменах (employee_id, shift_date, status, source_message_id, source_link)
- `processing_log` — журнал обработки (message_id, update_id, group_id, status, reason, employee_id, timestamps)
- `processed_updates` — дедупликация по update_id (UNIQUE constraint)
- Alembic для миграций
- Индексы: (employee_id, shift_date) UNIQUE на shift_records; update_id UNIQUE на processed_updates

### Bot Configuration
- Polling mode для разработки, webhook-ready architecture для продакшена
- Privacy mode must be OFF (BotFather → /setprivacy → Disable)
- Бот должен быть добавлен в группу как участник (не обязательно админ, но privacy mode отключён)
- Обработка migrate_to_chat_id: автоматическое обновление chat_id в telegram_groups
- pydantic-settings для конфигурации (BOT_TOKEN, DATABASE_URL, etc.)

### Claude's Discretion
- Exact SQLAlchemy model field types and constraints
- Alembic migration naming conventions
- Logging format and levels
- Project directory structure (src layout)
- Test framework choice (pytest recommended)
- Error retry strategies for Telegram API calls

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

No external specs — requirements are fully captured in the ТЗ from Google Sheets and decisions above.

### Project Documentation
- `.planning/PROJECT.md` — Project context, constraints, key decisions
- `.planning/REQUIREMENTS.md` — Full requirements with REQ-IDs (TGRAM-01..05, IDENT-01..05, SHIFT-01..04, JRNL-01..04 for this phase)
- `.planning/research/STACK.md` — Technology choices, library versions, integration patterns
- `.planning/research/ARCHITECTURE.md` — System architecture, component diagram, data flow
- `.planning/research/PITFALLS.md` — Critical pitfalls: privacy mode, rate limits, midnight crossover, dedup
- `.planning/research/FEATURES.md` — Feature landscape, table stakes, identification ladder
- `.planning/research/SUMMARY.md` — Research synthesis

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield project, no existing code

### Established Patterns
- None — patterns will be established in this phase

### Integration Points
- This phase creates the foundation that Phase 2 (Sheets) and Phase 3 (Admin UI) will build upon
- shift_records table must have a `sheet_write_status` column (PENDING/WRITTEN/ERROR) for Phase 2 consumption
- processing_log must be queryable by Phase 3 admin UI

</code_context>

<specifics>
## Specific Ideas

- Система должна быть "невидимой" для охранников — они просто шлют фото в чат как обычно
- PostgreSQL — source of truth; Google Sheets — display layer only (Phase 2)
- Inbox pattern: ON CONFLICT DO NOTHING на update_id для at-least-once delivery
- Бот не должен отвечать в группы (silent processing) — никаких сообщений в чат

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation*
*Context gathered: 2026-04-10*
