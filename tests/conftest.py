import os
import sys
import tempfile
import types

import pytest

# Use throwaway databases/logs and never call real SMS or LLM services in tests.
_tmp = tempfile.mkdtemp(prefix="medibot-test-")
os.environ["USER_DB_PATH"] = os.path.join(_tmp, "users.db")
os.environ["LOGS_DIR"] = os.path.join(_tmp, "logs")
os.environ["SMS_PROVIDER"] = "console"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["OTP_RESEND_COOLDOWN_SECONDS"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeRag:
    def answer(self, question, history=None, disease_info=""):
        return {"answer": f"Fake answer to: {question}", "search_query": question,
                "sources": [{"source": "book.pdf", "page": 12, "snippet": "snippet"}]}


fake_retriever = types.ModuleType("app.components.retriever")
fake_retriever.get_rag_service = lambda: FakeRag()
sys.modules["app.components.retriever"] = fake_retriever


@pytest.fixture
def sent_codes(monkeypatch):
    codes = []
    from app.auth import sms
    monkeypatch.setattr(sms.ConsoleSmsProvider, "send_otp", lambda self, phone, code: codes.append((phone, code)))
    return codes


@pytest.fixture
def app():
    from app.application import create_app
    path = os.path.join(_tmp, f"users-{os.urandom(4).hex()}.db")
    return create_app({"TESTING": True, "USER_DB_PATH": path})


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client):
    client.get("/login")
    with client.session_transaction() as s:
        return s["_csrf"]


def register(client, sent_codes, phone="9876543210", password="secret123", name="Test User"):
    token = csrf(client)
    r = client.post("/register", data={"csrf_token": token, "full_name": name, "phone": phone,
                                       "password": password, "confirm_password": password})
    assert r.status_code == 302, r.data
    code = sent_codes[-1][1]
    r = client.post("/verify", data={"csrf_token": token, "otp": code})
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    return token


def login(client, phone="9876543210", password="secret123"):
    token = csrf(client)
    return client.post("/login", data={"csrf_token": token, "phone": phone, "password": password})
