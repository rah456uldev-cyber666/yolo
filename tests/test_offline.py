import types

import requests
from conftest import csrf

from app.auth import sms
from app.components import llm as llm_mod
from app.config import config


class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body or {}
        self.text = str(body)

    def json(self):
        return self._body


def test_auto_without_keys_shows_otp_on_screen(client, monkeypatch, sent_codes):
    monkeypatch.setattr(config, "SMS_PROVIDER", "auto")
    monkeypatch.setattr(config, "FAST2SMS_API_KEY", "")
    monkeypatch.setattr(config, "TWILIO_ACCOUNT_SID", "")
    token = csrf(client)
    client.post("/register", data={"csrf_token": token, "full_name": "Off Line", "phone": "9200000001",
                                   "password": "secret123", "confirm_password": "secret123"})
    page = client.get("/verify").data.decode()
    assert "Offline mode" in page and sent_codes[-1][1] in page


def test_fast2sms_used_first_when_key_set(monkeypatch):
    calls = []
    monkeypatch.setattr(config, "SMS_PROVIDER", "auto")
    monkeypatch.setattr(config, "FAST2SMS_API_KEY", "k")
    monkeypatch.setattr(config, "TWILIO_ACCOUNT_SID", "sid")
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setattr(config, "TWILIO_FROM_NUMBER", "+15550000000")
    monkeypatch.setattr(sms.requests, "post",
                        lambda url, **kw: calls.append(url) or FakeResp(200, {"return": True}))
    assert sms.deliver_otp("+919876543210", "123456") == sms.DELIVERED_SMS
    assert "fast2sms" in calls[0] and len(calls) == 1
    # non-Indian number goes to Twilio
    calls.clear()
    assert sms.deliver_otp("+15551234567", "123456") == sms.DELIVERED_SMS
    assert "twilio" in calls[0]


def test_falls_back_to_twilio_then_screen_when_offline(monkeypatch, sent_codes):
    calls = []
    monkeypatch.setattr(config, "SMS_PROVIDER", "auto")
    monkeypatch.setattr(config, "FAST2SMS_API_KEY", "k")
    monkeypatch.setattr(config, "TWILIO_ACCOUNT_SID", "sid")
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setattr(config, "TWILIO_FROM_NUMBER", "+15550000000")

    def offline(url, **kw):
        calls.append(url)
        raise requests.ConnectionError("no internet")
    monkeypatch.setattr(sms.requests, "post", offline)
    assert sms.deliver_otp("+919876543210", "654321") == sms.DELIVERED_SCREEN
    assert len(calls) == 2 and sent_codes[-1] == ("+919876543210", "654321")


def test_ollama_client(monkeypatch):
    monkeypatch.setattr(llm_mod.requests, "post",
                        lambda url, **kw: FakeResp(200, {"message": {"content": " Hello "}}))
    assert llm_mod.OllamaChat().invoke("hi").content == "Hello"
    monkeypatch.setattr(llm_mod.requests, "post", lambda url, **kw: FakeResp(404, {}))
    try:
        llm_mod.OllamaChat().invoke("hi")
        assert False
    except llm_mod.LlmUnavailable as e:
        assert "ollama pull" in str(e)


def test_default_provider_is_local():
    assert config.LLM_PROVIDER == "ollama"
    assert isinstance(llm_mod.load_llm(), llm_mod.OllamaChat)
