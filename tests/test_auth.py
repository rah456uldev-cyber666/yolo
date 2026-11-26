from conftest import csrf, login, register

from app.auth.phone import normalize_phone


def test_phone_normalization():
    assert normalize_phone("98765 43210", "+91") == "+919876543210"
    assert normalize_phone("+1 (555) 123-4567") == "+15551234567"
    assert normalize_phone("0091 98765 43210") == "+919876543210"
    for bad in ["", "123", "abcdefghij"]:
        try:
            normalize_phone(bad)
            assert False, bad
        except ValueError:
            pass


def test_pages_require_login(client):
    r = client.get("/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert client.get("/api/history").status_code == 401


def test_post_without_csrf_is_rejected(client):
    assert client.post("/login", data={"phone": "9876543210", "password": "x"}).status_code == 400


def test_register_verify_login_flow(client, sent_codes):
    register(client, sent_codes)
    assert sent_codes[-1][0] == "+919876543210"
    r = login(client)
    assert r.status_code == 302 and r.headers["Location"].endswith("/")
    page = client.get("/")
    assert page.status_code == 200 and b"Ask a medical question" in page.data


def test_wrong_otp_and_unverified_login(client, sent_codes):
    token = csrf(client)
    client.post("/register", data={"csrf_token": token, "full_name": "A B", "phone": "9000000001",
                                   "password": "secret123", "confirm_password": "secret123"})
    r = client.post("/verify", data={"csrf_token": token, "otp": "000000" if sent_codes[-1][1] != "000000" else "111111"})
    assert b"Incorrect code" in r.data
    # unverified user cannot log in; gets redirected to verification
    r = login(client, phone="9000000001")
    assert r.status_code == 302 and "/verify" in r.headers["Location"]


def test_duplicate_registration_blocked(client, sent_codes):
    register(client, sent_codes, phone="9000000002")
    token = csrf(client)
    r = client.post("/register", data={"csrf_token": token, "full_name": "Other", "phone": "9000000002",
                                       "password": "secret123", "confirm_password": "secret123"})
    assert r.status_code == 400 and b"already registered" in r.data


def test_weak_password_rejected(client, sent_codes):
    token = csrf(client)
    r = client.post("/register", data={"csrf_token": token, "full_name": "A B", "phone": "9000000003",
                                       "password": "short", "confirm_password": "short"})
    assert r.status_code == 400 and b"Password needs" in r.data


def test_wrong_password_and_lockout(client, sent_codes):
    register(client, sent_codes, phone="9000000004")
    for _ in range(5):
        assert login(client, phone="9000000004", password="wrongpass1").status_code == 401
    r = login(client, phone="9000000004")  # correct password but locked
    assert r.status_code == 429


def test_password_reset(client, sent_codes):
    register(client, sent_codes, phone="9000000005")
    token = csrf(client)
    client.post("/forgot-password", data={"csrf_token": token, "phone": "9000000005"})
    code = sent_codes[-1][1]
    r = client.post("/reset-password", data={"csrf_token": token, "otp": code,
                                             "password": "newpass123", "confirm_password": "newpass123"})
    assert r.status_code == 302
    assert login(client, phone="9000000005", password="secret123").status_code == 401
    assert login(client, phone="9000000005", password="newpass123").status_code == 302


def test_logout(client, sent_codes):
    register(client, sent_codes, phone="9000000006")
    login(client, phone="9000000006")
    with client.session_transaction() as s:
        token = s["_csrf"]
    client.post("/logout", data={"csrf_token": token})
    assert client.get("/").status_code == 302
