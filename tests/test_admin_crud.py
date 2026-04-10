"""Integration tests for Admin CRUD: Groups, Employees, Caption Rules, GroupEmployee bindings."""
import pytest


def login(client):
    """Login helper — authenticates with default test credentials."""
    from shifttracker.config import Settings
    settings = Settings()
    resp = client.post(
        "/admin/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
        follow_redirects=True,
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

def test_group_crud(test_client):
    login(test_client)

    # Create
    resp = test_client.post(
        "/admin/groups/add",
        data={
            "name": "TestGroup",
            "chat_id": "-100123456",
            "sheet_id": "spreadsheet_1",
            "sheet_name": "Sheet1",
            "shift_start_hour": "6",
            "shift_end_hour": "22",
            "timezone": "Europe/Moscow",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "TestGroup" in resp.text

    # List
    resp = test_client.get("/admin/groups/")
    assert resp.status_code == 200
    assert "TestGroup" in resp.text
    assert "-100123456" in resp.text

    # Find group id from list page — we'll use /add then /edit via redirect inspection
    # Edit: post to update name
    resp_list = test_client.get("/admin/groups/")
    # Extract group id from "edit" link in HTML
    import re
    match = re.search(r'/admin/groups/([0-9a-f-]+)/edit', resp_list.text)
    assert match, "Could not find edit link in groups list"
    group_id = match.group(1)

    resp = test_client.post(
        f"/admin/groups/{group_id}/edit",
        data={
            "name": "TestGroupUpdated",
            "chat_id": "-100123456",
            "sheet_id": "spreadsheet_1",
            "sheet_name": "Sheet1",
            "shift_start_hour": "6",
            "shift_end_hour": "22",
            "timezone": "Europe/Moscow",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "TestGroupUpdated" in resp.text

    # Delete
    resp = test_client.delete(f"/admin/groups/{group_id}")
    assert resp.status_code == 200

    # Verify deleted
    resp = test_client.get("/admin/groups/")
    assert "TestGroupUpdated" not in resp.text


def test_group_shift_window(test_client):
    login(test_client)

    resp = test_client.post(
        "/admin/groups/add",
        data={
            "name": "NightShiftGroup",
            "chat_id": "-100999888",
            "sheet_id": "",
            "sheet_name": "Sheet1",
            "shift_start_hour": "20",
            "shift_end_hour": "8",
            "timezone": "Europe/Moscow",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    resp_list = test_client.get("/admin/groups/")
    import re
    match = re.search(r'/admin/groups/([0-9a-f-]+)/edit', resp_list.text)
    assert match
    group_id = match.group(1)

    resp = test_client.get(f"/admin/groups/{group_id}/edit")
    assert resp.status_code == 200
    assert "20" in resp.text
    assert "8" in resp.text


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------

def test_employee_crud(test_client):
    login(test_client)

    # Create
    resp = test_client.post(
        "/admin/employees/add",
        data={
            "name": "Alice",
            "telegram_user_id": "12345678",
            "employee_code": "EMP001",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "Alice" in resp.text

    # List
    resp = test_client.get("/admin/employees/")
    assert resp.status_code == 200
    assert "Alice" in resp.text

    import re
    match = re.search(r'/admin/employees/([0-9a-f-]+)/edit', resp.text)
    assert match, "Could not find edit link in employees list"
    emp_id = match.group(1)

    # Edit
    resp = test_client.post(
        f"/admin/employees/{emp_id}/edit",
        data={
            "name": "AliceUpdated",
            "telegram_user_id": "12345678",
            "employee_code": "EMP001",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "AliceUpdated" in resp.text

    # Delete
    resp = test_client.delete(f"/admin/employees/{emp_id}")
    assert resp.status_code == 200

    resp = test_client.get("/admin/employees/")
    assert "AliceUpdated" not in resp.text


# ---------------------------------------------------------------------------
# Group-Employee bindings
# ---------------------------------------------------------------------------

def test_group_employee_binding(test_client):
    login(test_client)

    # Create group
    resp = test_client.post(
        "/admin/groups/add",
        data={
            "name": "BindGroup",
            "chat_id": "-100777666",
            "sheet_id": "",
            "sheet_name": "Sheet1",
            "shift_start_hour": "6",
            "shift_end_hour": "22",
            "timezone": "Europe/Moscow",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    import re
    resp_list = test_client.get("/admin/groups/")
    match = re.search(r'/admin/groups/([0-9a-f-]+)/edit', resp_list.text)
    assert match
    group_id = match.group(1)

    # Create employee
    resp = test_client.post(
        "/admin/employees/add",
        data={
            "name": "Bob",
            "telegram_user_id": "99887766",
            "employee_code": "EMP002",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    resp_list = test_client.get("/admin/employees/")
    match = re.search(r'/admin/employees/([0-9a-f-]+)/edit', resp_list.text)
    assert match
    emp_id = match.group(1)

    # Add binding
    resp = test_client.post(
        f"/admin/employees/{emp_id}/bindings/add",
        data={"group_id": group_id, "sheet_row": "5"},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    # Verify binding shows up on employee edit page
    resp = test_client.get(f"/admin/employees/{emp_id}/edit")
    assert resp.status_code == 200
    assert "BindGroup" in resp.text

    # Find binding id
    match = re.search(r'/admin/employees/[0-9a-f-]+/bindings/([0-9a-f-]+)', resp.text)
    assert match, "Could not find binding delete link"
    binding_id = match.group(1)

    # Delete binding
    resp = test_client.delete(f"/admin/employees/{emp_id}/bindings/{binding_id}")
    assert resp.status_code == 200

    # Verify binding removed — binding row for the group is gone from the bindings table body.
    # The group name may still appear in the "Add Binding" dropdown — that's expected.
    resp = test_client.get(f"/admin/employees/{emp_id}/edit")
    assert binding_id not in resp.text
