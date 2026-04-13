# ShiftTracker

**Система автоматического заполнения таблицы смен на основе фотографий из Telegram-групп.**

Бот мониторит рабочие чаты, распознаёт факт заступления сотрудника на смену по фото с подписью и автоматически проставляет отметку "1" в таблице смен. Рассчитана на масштаб до 200 групп с тысячами фото в сутки.

## Как это работает

```
Сотрудник               Система                    Оператор
    |                      |                          |
    |-- фото в группу ---->|                          |
    |   "Иванов на смене"  |                          |
    |                      |-- определяет сотрудника   |
    |                      |-- определяет дату смены   |
    |                      |-- ставит "1" в таблицу    |
    |                      |                          |
    |-- фото без подписи ->|                          |
    |                      |-- не может определить --> |-- проверяет вручную
    |                      |                          |-- подтверждает/отклоняет
```

## Возможности

- **Telegram-бот** — молча принимает фото из групп, не мешает переписке
- **Идентификация сотрудника** — по Telegram-аккаунту, подписи к фото, привязке группы
- **Ночные смены** — корректно определяет дату при переходе через полночь
- **Защита от дублей** — повторное фото не создаст вторую отметку
- **Очередь проверки** — спорные случаи отправляются оператору
- **Google Sheets** — автоматическая запись "1" в таблицу смен (батчинг, retry)
- **Веб-админка** — управление группами, сотрудниками, правилами, таблица смен
- **Масштабируемость** — asyncio + 8 воркеров, очередь с backpressure

## Архитектура

```
┌─────────────┐     ┌──────────────────────────────────────┐     ┌──────────────┐
│  Telegram   │     │           ShiftTracker               │     │ Google Sheets│
│  Группы     │────>│                                      │────>│  Таблица     │
│  (фото)     │     │  ┌─────┐  ┌──────────┐  ┌────────┐  │     │  смен        │
└─────────────┘     │  │ Bot │->│ Pipeline  │->│ Sheets │  │     └──────────────┘
                    │  │ API │  │ Workers   │  │ Writer │  │
                    │  └─────┘  └──────────┘  └────────┘  │     ┌──────────────┐
                    │               │                      │     │  Админка     │
                    │          ┌────┴─────┐                │────>│  (FastAPI +  │
                    │          │ PostgreSQL│                │     │  Bootstrap)  │
                    │          │   / SQLite│                │     └──────────────┘
                    │          └──────────┘                │
                    └──────────────────────────────────────┘
```

## Стек технологий

| Компонент | Технология |
|-----------|-----------|
| Telegram-бот | Python 3.11 + aiogram 3.27 |
| Веб-сервер | FastAPI + Uvicorn |
| База данных | PostgreSQL (прод) / SQLite (dev) |
| ORM | SQLAlchemy 2.0 async |
| Миграции | Alembic |
| Шаблоны | Jinja2 + Bootstrap 5 + htmx |
| Google Sheets | gspread + Service Account |
| Очередь | asyncio.Queue (in-process) |

## Быстрый старт

### 1. Клонирование
```bash
git clone https://github.com/yakuraog/shifttracker.git
cd shifttracker
```

### 2. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 3. Настройка
```bash
cp .env.example .env
# Отредактируйте .env — укажите BOT_TOKEN от @BotFather
```

### 4. Запуск
```bash
uvicorn shifttracker.app:create_app --factory --reload
```

### 5. Настройка бота
- Создайте бота через @BotFather (`/newbot`)
- Отключите Group Privacy: `/mybots` -> Bot Settings -> Group Privacy -> OFF
- Добавьте бота в рабочую группу как администратора

### 6. Админка
Откройте http://localhost:8000/admin/login
- Логин: `admin` / Пароль: `changeme`

## Конфигурация (.env)

| Переменная | Описание | По умолчанию |
|-----------|----------|-------------|
| `BOT_TOKEN` | Токен Telegram-бота | — (обязательно) |
| `DATABASE_URL` | URL базы данных | `sqlite+aiosqlite:///shifttracker.db` |
| `TIMEZONE` | Часовой пояс | `Europe/Moscow` |
| `ADMIN_USERNAME` | Логин админки | `admin` |
| `ADMIN_PASSWORD` | Пароль админки | `changeme` |
| `GOOGLE_SHEETS_CREDENTIALS_FILE` | Путь к JSON-ключу сервис-аккаунта | — (опционально) |
| `WORKER_COUNT` | Количество воркеров обработки | `8` |

## Pipeline обработки сообщений

```
Telegram Update
     │
     ▼
[Дедупликация] ──── update_id уже обработан? → SKIP
     │
     ▼
[Валидация] ──── нет фото? пересланное? документ? → SKIP
     │
     ▼
[Идентификация] ── 5-уровневая система:
     │               1. Telegram аккаунт
     │               2. Точное совпадение ФИО
     │               3. Ключевые слова в подписи
     │               4. Единственный сотрудник в группе
     │               5. Не определён → NEEDS_REVIEW
     │
     ▼
[Дата смены] ──── учёт ночных смен и временных окон
     │
     ▼
[Бизнес-дедупликация] ── уже есть отметка за эту дату? → DUPLICATE
     │
     ▼
[Запись] ──── ShiftRecord (ACCEPTED) + ProcessingLog
     │
     ▼
[Google Sheets] ── батчинг каждые 5 сек, retry при ошибках
```

## API документация

Swagger UI доступен по адресу: `/docs`

## Тестирование

```bash
# Запуск всех тестов
pytest tests/ -v --timeout=30

# Быстрый прогон
pytest tests/ -x -q --timeout=10
```

**114 тестов** покрывают:
- Модели БД и ограничения уникальности
- Идентификацию сотрудников (10 сценариев)
- Определение даты смены (13 сценариев)
- Обработчики бота и дедупликацию
- End-to-end pipeline
- Google Sheets writer (мок)
- Админку (CRUD, авторизация, очередь проверки, таблица смен)

## Структура проекта

```
shifttracker/
├── bot/
│   ├── router.py          # Обработчики Telegram (фото, миграция)
│   └── middleware.py       # Middleware для обработки ошибок
├── pipeline/
│   ├── models.py           # ProcessingContext, IdentificationResult
│   ├── queue.py            # asyncio.Queue с backpressure
│   ├── worker.py           # Воркеры обработки сообщений
│   └── stages/
│       ├── identify.py     # 5-уровневая идентификация
│       ├── shift_date.py   # Определение даты с ночными сменами
│       ├── validate.py     # Фильтрация нерелевантных сообщений
│       └── deduplicate.py  # Inbox pattern + бизнес-дедупликация
├── sheets/
│   ├── client.py           # gspread клиент (service account)
│   ├── header_cache.py     # Кэш заголовков (5 мин TTL)
│   ├── cell_resolve.py     # Поиск ячейки по сотруднику + дате
│   └── writer.py           # Фоновая запись в Sheets (батчинг)
├── admin/
│   ├── auth.py             # Сессионная авторизация
│   ├── deps.py             # FastAPI-зависимости (БД, авторизация)
│   └── routers/
│       ├── dashboard.py    # Главная со статистикой
│       ├── groups.py       # CRUD групп
│       ├── employees.py    # CRUD сотрудников + привязки
│       ├── caption_rules.py # CRUD правил подписей
│       ├── review.py       # Очередь ручной проверки
│       └── shifts.py       # Таблица смен (grid view)
├── db/
│   ├── models.py           # 7 ORM-моделей (SQLAlchemy 2.0)
│   └── engine.py           # Async engine factory
├── templates/              # Jinja2 + Bootstrap 5 + htmx
├── config.py               # pydantic-settings
├── app.py                  # FastAPI app factory + lifespan
└── main.py                 # Uvicorn entry point
```

## Лицензия

MIT
