"""Admin CRUD router for Employee and GroupEmployee bindings."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from shifttracker.admin.deps import get_db
from shifttracker.db.models import Employee, GroupEmployee, TelegramGroup

router = APIRouter(prefix="/employees", tags=["employees"])


def _get_templates():
    from shifttracker.admin.router import templates
    return templates


@router.get("/")
async def list_employees(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Employee).order_by(Employee.name))
    employees = result.scalars().all()
    return _get_templates().TemplateResponse(
        request,
        "admin/employees/list.html",
        {"employees": employees},
    )


@router.get("/add")
async def add_employee_form(request: Request):
    return _get_templates().TemplateResponse(
        request,
        "admin/employees/form.html",
        {"employee": None, "bindings": [], "all_groups": []},
    )


@router.post("/add")
async def add_employee(
    request: Request,
    name: str = Form(...),
    telegram_user_id: Optional[int] = Form(default=None),
    employee_code: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    employee = Employee(
        name=name,
        telegram_user_id=telegram_user_id or None,
        employee_code=employee_code or None,
    )
    db.add(employee)
    await db.commit()
    return RedirectResponse("/admin/employees/", status_code=303)


@router.get("/{employee_id}/edit")
async def edit_employee_form(
    employee_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Employee)
        .options(selectinload(Employee.group_bindings).selectinload(GroupEmployee.group))
        .where(Employee.id == uuid.UUID(employee_id))
    )
    employee = result.scalar_one_or_none()
    if employee is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Employee not found")

    groups_result = await db.execute(select(TelegramGroup).order_by(TelegramGroup.name))
    all_groups = groups_result.scalars().all()

    return _get_templates().TemplateResponse(
        request,
        "admin/employees/form.html",
        {
            "employee": employee,
            "bindings": employee.group_bindings,
            "all_groups": all_groups,
        },
    )


@router.post("/{employee_id}/edit")
async def edit_employee(
    employee_id: str,
    request: Request,
    name: str = Form(...),
    telegram_user_id: Optional[int] = Form(default=None),
    employee_code: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Employee).where(Employee.id == uuid.UUID(employee_id)))
    employee = result.scalar_one_or_none()
    if employee is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Employee not found")
    employee.name = name
    employee.telegram_user_id = telegram_user_id or None
    employee.employee_code = employee_code or None
    await db.commit()
    return RedirectResponse("/admin/employees/", status_code=303)


@router.delete("/{employee_id}")
async def delete_employee(
    employee_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Employee).where(Employee.id == uuid.UUID(employee_id)))
    employee = result.scalar_one_or_none()
    if employee is not None:
        await db.delete(employee)
        await db.commit()
    return Response(status_code=200)


@router.post("/{employee_id}/bindings/add")
async def add_binding(
    employee_id: str,
    request: Request,
    group_id: str = Form(...),
    sheet_row: Optional[int] = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    binding = GroupEmployee(
        employee_id=uuid.UUID(employee_id),
        group_id=uuid.UUID(group_id),
        sheet_row=sheet_row,
    )
    db.add(binding)
    await db.commit()
    return RedirectResponse(f"/admin/employees/{employee_id}/edit", status_code=303)


@router.delete("/{employee_id}/bindings/{binding_id}")
async def delete_binding(
    employee_id: str,
    binding_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GroupEmployee).where(GroupEmployee.id == uuid.UUID(binding_id))
    )
    binding = result.scalar_one_or_none()
    if binding is not None:
        await db.delete(binding)
        await db.commit()
    return Response(status_code=200)
