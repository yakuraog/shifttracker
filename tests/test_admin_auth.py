"""Admin authentication endpoint tests."""


def test_login_page_accessible(test_client):
    resp = test_client.get("/admin/login")
    assert resp.status_code == 200
    assert "login" in resp.text.lower()


def test_login_valid_credentials(test_client):
    resp = test_client.post(
        "/admin/login",
        data={"username": "admin", "password": "changeme"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/"


def test_login_invalid_credentials(test_client):
    resp = test_client.post(
        "/admin/login",
        data={"username": "admin", "password": "wrong"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "Invalid credentials" in resp.text


def test_admin_requires_auth(test_client):
    resp = test_client.get("/admin/", follow_redirects=False)
    assert resp.status_code == 303
    assert "/admin/login" in resp.headers["location"]


def test_dashboard_with_session(test_client):
    # Login first
    test_client.post(
        "/admin/login",
        data={"username": "admin", "password": "changeme"},
    )
    resp = test_client.get("/admin/")
    assert resp.status_code == 200
    assert "Dashboard" in resp.text


def test_logout(test_client):
    # Login
    test_client.post(
        "/admin/login",
        data={"username": "admin", "password": "changeme"},
    )
    # Logout
    resp = test_client.post("/admin/logout", follow_redirects=False)
    assert resp.status_code == 303
    # Should not be able to access admin anymore
    resp2 = test_client.get("/admin/", follow_redirects=False)
    assert resp2.status_code == 303
