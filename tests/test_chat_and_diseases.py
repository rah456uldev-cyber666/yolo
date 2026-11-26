from conftest import login, register

from app.chat import emergency_notice
from app.diseases import repository as repo


def _logged_in(client, sent_codes, phone):
    register(client, sent_codes, phone=phone)
    login(client, phone=phone)
    with client.session_transaction() as s:
        return s["_csrf"]


def test_chat_api_and_history(client, sent_codes):
    token = _logged_in(client, sent_codes, "9100000001")
    r = client.post("/api/chat", json={"question": "What are the symptoms of chickenpox?"},
                    headers={"X-CSRF-Token": token})
    assert r.status_code == 200
    body = r.get_json()
    assert body["content"].startswith("Fake answer")
    assert body["sources"][0]["page"] == 12
    assert any(d["slug"] == "chickenpox" for d in body["diseases"])
    history = client.get("/api/history").get_json()
    assert [m["role"] for m in history] == ["user", "assistant"]


def test_chat_output_is_escaped(client, sent_codes):
    token = _logged_in(client, sent_codes, "9100000002")
    client.post("/", data={"csrf_token": token, "prompt": "<script>alert(1)</script>"})
    page = client.get("/").data
    assert b"<script>alert(1)</script>" not in page
    assert b"&lt;script&gt;" in page


def test_emergency_notice():
    assert emergency_notice("I have crushing chest pain")
    assert "crisis" in emergency_notice("I want to kill myself")
    assert emergency_notice("what is a cataract") is None


def test_disease_database():
    assert repo.stats()["count"] > 100
    d = repo.get_by_slug("common-cold")
    assert d and "sneezing" in d["symptoms"]
    assert repo.search("dengue")[0]["slug"] == "dengue-fever"
    terms, results = repo.symptom_check("runny nose, sneezing, sore throat")
    assert results and results[0]["disease"]["slug"] == "common-cold"


def test_disease_pages(client, sent_codes):
    _logged_in(client, sent_codes, "9100000003")
    assert b"Disease library" in client.get("/diseases?q=fever").data
    assert b"Common symptoms" in client.get("/diseases/common-cold").data
    assert client.get("/diseases/not-a-disease").status_code == 404
    assert client.get("/api/diseases/cataracts").get_json()["name"] == "Cataracts"


def test_health(client):
    assert client.get("/health").get_json()["status"] == "ok"
