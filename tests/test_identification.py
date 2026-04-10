"""
Tests for employee identification confidence ladder.
TDD: Tests written before implementation.
"""
import uuid
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from shifttracker.db.models import Employee, TelegramGroup, GroupEmployee, CaptionRule
from shifttracker.pipeline.models import ProcessingContext, IdentificationResult
from shifttracker.pipeline.stages.identify import identify_employee


def make_context(
    sender_user_id=None,
    caption=None,
    group_id=None,
    message_datetime=None,
):
    return ProcessingContext(
        update_id=1,
        message_id=100,
        chat_id=-1001234567890,
        sender_user_id=sender_user_id,
        caption=caption,
        message_datetime=message_datetime or datetime(2026, 4, 10, 14, 0, tzinfo=ZoneInfo("Europe/Moscow")),
        group_id=group_id,
    )


@pytest.fixture
async def group(async_session: AsyncSession):
    grp = TelegramGroup(
        chat_id=-1001234567890,
        name="Test Group",
        shift_start_hour=6,
        shift_end_hour=22,
        timezone="Europe/Moscow",
    )
    async_session.add(grp)
    await async_session.flush()
    return grp


@pytest.fixture
async def employee_ivan(async_session: AsyncSession):
    emp = Employee(name="Иванов Иван", telegram_user_id=111111)
    async_session.add(emp)
    await async_session.flush()
    return emp


@pytest.fixture
async def employee_petrov(async_session: AsyncSession):
    emp = Employee(name="Петров Петр", telegram_user_id=222222)
    async_session.add(emp)
    await async_session.flush()
    return emp


@pytest.fixture
async def group_with_ivan(async_session: AsyncSession, group, employee_ivan):
    ge = GroupEmployee(group_id=group.id, employee_id=employee_ivan.id)
    async_session.add(ge)
    await async_session.flush()
    return group


@pytest.fixture
async def group_with_two_employees(async_session: AsyncSession, group, employee_ivan, employee_petrov):
    ge1 = GroupEmployee(group_id=group.id, employee_id=employee_ivan.id)
    ge2 = GroupEmployee(group_id=group.id, employee_id=employee_petrov.id)
    async_session.add(ge1)
    async_session.add(ge2)
    await async_session.flush()
    return group


async def test_telegram_account_match_returns_high_confidence(
    async_session: AsyncSession, group_with_ivan, employee_ivan
):
    """telegram_user_id match returns HIGH confidence with method=telegram_account."""
    ctx = make_context(sender_user_id=111111, group_id=group_with_ivan.id)
    results = await identify_employee(ctx, async_session)
    assert len(results) == 1
    assert results[0].method == "telegram_account"
    assert results[0].confidence == "HIGH"
    assert results[0].employee_id == employee_ivan.id
    assert results[0].employee_name == "Иванов Иван"


async def test_caption_exact_match_returns_high_confidence(
    async_session: AsyncSession, group_with_ivan, employee_ivan
):
    """Exact name in caption returns HIGH confidence with method=caption_exact."""
    ctx = make_context(
        sender_user_id=999999,  # no match
        caption="Сегодня на смене Иванов Иван",
        group_id=group_with_ivan.id,
    )
    results = await identify_employee(ctx, async_session)
    assert len(results) == 1
    assert results[0].method == "caption_exact"
    assert results[0].confidence == "HIGH"
    assert results[0].employee_id == employee_ivan.id


async def test_caption_keyword_match_returns_medium_confidence(
    async_session: AsyncSession, group_with_ivan, employee_ivan, async_session_factory=None
):
    """CaptionRule pattern match returns MEDIUM confidence with method=caption_keyword."""
    rule = CaptionRule(
        group_id=group_with_ivan.id,
        pattern="иван",
        employee_id=employee_ivan.id,
    )
    async_session.add(rule)
    await async_session.flush()

    ctx = make_context(
        sender_user_id=999999,  # no account match
        caption="Заступил иван на смену",
        group_id=group_with_ivan.id,
    )
    results = await identify_employee(ctx, async_session)
    assert len(results) == 1
    assert results[0].method == "caption_keyword"
    assert results[0].confidence == "MEDIUM"
    assert results[0].employee_id == employee_ivan.id


async def test_group_fallback_single_employee_returns_low_confidence(
    async_session: AsyncSession, group_with_ivan, employee_ivan
):
    """Single-employee group returns LOW confidence with method=group_fallback."""
    ctx = make_context(
        sender_user_id=None,  # no account
        caption=None,  # no caption
        group_id=group_with_ivan.id,
    )
    results = await identify_employee(ctx, async_session)
    assert len(results) == 1
    assert results[0].method == "group_fallback"
    assert results[0].confidence == "LOW"
    assert results[0].employee_id == employee_ivan.id


async def test_no_match_returns_empty_list(
    async_session: AsyncSession, group_with_two_employees
):
    """Two employees in group, no match → empty list (triggers NEEDS_REVIEW upstream)."""
    ctx = make_context(
        sender_user_id=None,
        caption=None,
        group_id=group_with_two_employees.id,
    )
    results = await identify_employee(ctx, async_session)
    assert results == []


async def test_caption_with_two_employees_returns_two_results(
    async_session: AsyncSession,
    group_with_two_employees,
    employee_ivan,
    employee_petrov,
):
    """Caption containing two names returns two IdentificationResults."""
    ctx = make_context(
        sender_user_id=None,
        caption="Иванов Иван, Петров Петр",
        group_id=group_with_two_employees.id,
    )
    results = await identify_employee(ctx, async_session)
    assert len(results) == 2
    methods = {r.method for r in results}
    assert methods == {"caption_exact"}
    confidences = {r.confidence for r in results}
    assert confidences == {"HIGH"}
    employee_ids = {r.employee_id for r in results}
    assert employee_ids == {employee_ivan.id, employee_petrov.id}


async def test_caption_normalization_extra_whitespace(
    async_session: AsyncSession, group_with_ivan, employee_ivan
):
    """Caption with extra whitespace still matches after normalization."""
    ctx = make_context(
        sender_user_id=None,
        caption="  Иванов  Иван  на смене",
        group_id=group_with_ivan.id,
    )
    results = await identify_employee(ctx, async_session)
    assert len(results) == 1
    assert results[0].method == "caption_exact"
    assert results[0].employee_id == employee_ivan.id


async def test_telegram_account_takes_priority_over_caption(
    async_session: AsyncSession, group_with_ivan, employee_ivan
):
    """telegram_user_id match takes priority — only one result returned."""
    ctx = make_context(
        sender_user_id=111111,  # matches ivan
        caption="Иванов Иван на смене",  # also matches ivan
        group_id=group_with_ivan.id,
    )
    results = await identify_employee(ctx, async_session)
    assert len(results) == 1
    assert results[0].method == "telegram_account"
    assert results[0].confidence == "HIGH"


async def test_photo_without_caption_works_via_telegram_user_id(
    async_session: AsyncSession, group_with_ivan, employee_ivan
):
    """No caption, but telegram_user_id matches → identified correctly."""
    ctx = make_context(
        sender_user_id=111111,
        caption=None,
        group_id=group_with_ivan.id,
    )
    results = await identify_employee(ctx, async_session)
    assert len(results) == 1
    assert results[0].method == "telegram_account"
    assert results[0].employee_id == employee_ivan.id


async def test_photo_without_caption_group_fallback(
    async_session: AsyncSession, group_with_ivan, employee_ivan
):
    """No caption, no telegram match → group fallback (single employee)."""
    ctx = make_context(
        sender_user_id=None,
        caption=None,
        group_id=group_with_ivan.id,
    )
    results = await identify_employee(ctx, async_session)
    assert len(results) == 1
    assert results[0].method == "group_fallback"
