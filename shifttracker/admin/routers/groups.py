"""Admin CRUD router for TelegramGroup."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shifttracker.admin.deps import get_db
from shifttracker.db.models import TelegramGroup

router = APIRouter(prefix="/groups", tags=["groups"])


def _get_templates():
    from shifttracker.admin.router import templates
    return templates


@router.get("/")
async def list_groups(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TelegramGroup).order_by(TelegramGroup.name))
    groups = result.scalars().all()
    return _get_templates().TemplateResponse(
        request,
        "admin/groups/list.html",
        {"groups": groups},
    )


@router.get("/add")
async def add_group_form(request: Request):
    return _get_templates().TemplateResponse(
        request,
        "admin/groups/form.html",
        {"group": None},
    )


@router.post("/add")
async def add_group(
    request: Request,
    name: str = Form(...),
    chat_id: int = Form(...),
    sheet_id: Optional[str] = Form(default=None),
    sheet_name: str = Form(default="Sheet1"),
    shift_start_hour: int = Form(default=6),
    shift_end_hour: int = Form(default=22),
    timezone: str = Form(default="Europe/Moscow"),
    db: AsyncSession = Depends(get_db),
):
    group = TelegramGroup(
        name=name,
        chat_id=chat_id,
        sheet_id=sheet_id or None,
        sheet_name=sheet_name,
        shift_start_hour=shift_start_hour,
        shift_end_hour=shift_end_hour,
        timezone=timezone,
    )
    db.add(group)
    await db.commit()
    return RedirectResponse("/admin/groups/", status_code=303)


@router.get("/{group_id}/edit")
async def edit_group_form(
    group_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TelegramGroup).where(TelegramGroup.id == uuid.UUID(group_id)))
    group = result.scalar_one_or_none()
    if group is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Group not found")
    return _get_templates().TemplateResponse(
        request,
        "admin/groups/form.html",
        {"group": group},
    )


@router.post("/{group_id}/edit")
async def edit_group(
    group_id: str,
    request: Request,
    name: str = Form(...),
    chat_id: int = Form(...),
    sheet_id: Optional[str] = Form(default=None),
    sheet_name: str = Form(default="Sheet1"),
    shift_start_hour: int = Form(default=6),
    shift_end_hour: int = Form(default=22),
    timezone: str = Form(default="Europe/Moscow"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TelegramGroup).where(TelegramGroup.id == uuid.UUID(group_id)))
    group = result.scalar_one_or_none()
    if group is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Group not found")
    group.name = name
    group.chat_id = chat_id
    group.sheet_id = sheet_id or None
    group.sheet_name = sheet_name
    group.shift_start_hour = shift_start_hour
    group.shift_end_hour = shift_end_hour
    group.timezone = timezone
    await db.commit()
    return RedirectResponse("/admin/groups/", status_code=303)


@router.delete("/{group_id}")
async def delete_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TelegramGroup).where(TelegramGroup.id == uuid.UUID(group_id)))
    group = result.scalar_one_or_none()
    if group is not None:
        await db.delete(group)
        await db.commit()
    return Response(status_code=200)
