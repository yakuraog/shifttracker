"""
Employee identification stage — confidence ladder implementation.

Checks in this exact order (locked decision from 01-CONTEXT.md):
1. Telegram account match (telegram_user_id) — HIGH
2. Caption exact match (normalized employee name in normalized caption) — HIGH
3. Caption keyword match (CaptionRule patterns) — MEDIUM
4. Group fallback (exactly 1 employee in group) — LOW
5. No match — empty list (triggers NEEDS_REVIEW upstream)
"""
import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shifttracker.db.models import CaptionRule, Employee, GroupEmployee
from shifttracker.pipeline.models import IdentificationResult, ProcessingContext


def _normalize(text: str) -> str:
    """Trim, collapse multiple spaces, and lowercase."""
    return re.sub(r"\s+", " ", text.strip()).lower()


async def identify_employee(
    ctx: ProcessingContext, session: AsyncSession
) -> list[IdentificationResult]:
    """
    Identify employee(s) from the processing context using the confidence ladder.

    Returns a list of IdentificationResult — empty means no match (NEEDS_REVIEW).
    """
    normalized_caption: Optional[str] = (
        _normalize(ctx.caption) if ctx.caption is not None else None
    )

    # Step 1 — Telegram account match
    if ctx.sender_user_id is not None:
        stmt = select(Employee).where(Employee.telegram_user_id == ctx.sender_user_id)
        result = await session.execute(stmt)
        emp = result.scalar_one_or_none()
        if emp is not None:
            return [
                IdentificationResult(
                    employee_id=emp.id,
                    employee_name=emp.name,
                    method="telegram_account",
                    confidence="HIGH",
                )
            ]

    # Step 2 — Caption exact match
    if normalized_caption is not None and ctx.group_id is not None:
        stmt = (
            select(Employee)
            .join(GroupEmployee, GroupEmployee.employee_id == Employee.id)
            .where(GroupEmployee.group_id == ctx.group_id)
        )
        result = await session.execute(stmt)
        group_employees = result.scalars().all()

        caption_exact_results: list[IdentificationResult] = []
        for emp in group_employees:
            normalized_name = _normalize(emp.name)
            if normalized_name in normalized_caption:
                caption_exact_results.append(
                    IdentificationResult(
                        employee_id=emp.id,
                        employee_name=emp.name,
                        method="caption_exact",
                        confidence="HIGH",
                    )
                )
        if caption_exact_results:
            return caption_exact_results

    # Step 3 — Caption keyword match (CaptionRule patterns)
    if normalized_caption is not None and ctx.group_id is not None:
        stmt = select(CaptionRule).where(CaptionRule.group_id == ctx.group_id)
        result = await session.execute(stmt)
        rules = result.scalars().all()

        keyword_results: list[IdentificationResult] = []
        matched_employee_ids: set = set()
        for rule in rules:
            if rule.pattern.lower() in normalized_caption:
                if rule.employee_id not in matched_employee_ids:
                    emp_stmt = select(Employee).where(Employee.id == rule.employee_id)
                    emp_result = await session.execute(emp_stmt)
                    emp = emp_result.scalar_one_or_none()
                    if emp is not None:
                        keyword_results.append(
                            IdentificationResult(
                                employee_id=emp.id,
                                employee_name=emp.name,
                                method="caption_keyword",
                                confidence="MEDIUM",
                            )
                        )
                        matched_employee_ids.add(rule.employee_id)
        if keyword_results:
            return keyword_results

    # Step 4 — Group fallback (exactly 1 employee in group)
    if ctx.group_id is not None:
        stmt = select(GroupEmployee).where(GroupEmployee.group_id == ctx.group_id)
        result = await session.execute(stmt)
        group_members = result.scalars().all()

        if len(group_members) == 1:
            emp_stmt = select(Employee).where(Employee.id == group_members[0].employee_id)
            emp_result = await session.execute(emp_stmt)
            emp = emp_result.scalar_one_or_none()
            if emp is not None:
                return [
                    IdentificationResult(
                        employee_id=emp.id,
                        employee_name=emp.name,
                        method="group_fallback",
                        confidence="LOW",
                    )
                ]

    # Step 5 — No match
    return []
