"""Admin CRUD router for CaptionRule."""
import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from shifttracker.admin.deps import get_db
from shifttracker.db.models import CaptionRule, Employee, TelegramGroup

router = APIRouter(prefix="/caption-rules", tags=["caption-rules"])


def _get_templates():
    from shifttracker.admin.router import templates
    return templates


@router.get("/")
async def list_caption_rules(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CaptionRule)
        .options(selectinload(CaptionRule.group), selectinload(CaptionRule.employee))
        .order_by(CaptionRule.id)
    )
    rules = result.scalars().all()
    return _get_templates().TemplateResponse(
        request,
        "admin/caption_rules/list.html",
        {"rules": rules},
    )


@router.get("/add")
async def add_rule_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    groups_result = await db.execute(select(TelegramGroup).order_by(TelegramGroup.name))
    all_groups = groups_result.scalars().all()
    employees_result = await db.execute(select(Employee).order_by(Employee.name))
    all_employees = employees_result.scalars().all()
    return _get_templates().TemplateResponse(
        request,
        "admin/caption_rules/form.html",
        {"rule": None, "all_groups": all_groups, "all_employees": all_employees},
    )


@router.post("/add")
async def add_rule(
    request: Request,
    group_id: str = Form(...),
    employee_id: str = Form(...),
    pattern: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    rule = CaptionRule(
        group_id=uuid.UUID(group_id),
        employee_id=uuid.UUID(employee_id),
        pattern=pattern,
    )
    db.add(rule)
    await db.commit()
    return RedirectResponse("/admin/caption-rules/", status_code=303)


@router.get("/{rule_id}/edit")
async def edit_rule_form(
    rule_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CaptionRule).where(CaptionRule.id == uuid.UUID(rule_id))
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Caption rule not found")

    groups_result = await db.execute(select(TelegramGroup).order_by(TelegramGroup.name))
    all_groups = groups_result.scalars().all()
    employees_result = await db.execute(select(Employee).order_by(Employee.name))
    all_employees = employees_result.scalars().all()

    return _get_templates().TemplateResponse(
        request,
        "admin/caption_rules/form.html",
        {"rule": rule, "all_groups": all_groups, "all_employees": all_employees},
    )


@router.post("/{rule_id}/edit")
async def edit_rule(
    rule_id: str,
    request: Request,
    group_id: str = Form(...),
    employee_id: str = Form(...),
    pattern: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CaptionRule).where(CaptionRule.id == uuid.UUID(rule_id))
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Caption rule not found")
    rule.group_id = uuid.UUID(group_id)
    rule.employee_id = uuid.UUID(employee_id)
    rule.pattern = pattern
    await db.commit()
    return RedirectResponse("/admin/caption-rules/", status_code=303)


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CaptionRule).where(CaptionRule.id == uuid.UUID(rule_id))
    )
    rule = result.scalar_one_or_none()
    if rule is not None:
        await db.delete(rule)
        await db.commit()
    return Response(status_code=200)
