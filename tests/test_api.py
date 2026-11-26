import base64
import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    from app import store, main
    importlib.reload(store)
    importlib.reload(main)
    return TestClient(main.app)


def test_sample_scan_approve_reject_and_export(client):
    scan = client.post("/api/scans/sample").json()
    assert scan["summary"]["open_issues"] == 16
    sid = scan["id"]

    fix_issue = next(i for i in scan["issues"] if i["fix"]["action"] == "set_category")
    r = client.post(f"/api/scans/{sid}/issues/{fix_issue['id']}/decision", json={"decision": "approve"})
    assert r.status_code == 200
    assert r.json()["summary"]["approved"] == 1
    # Deciding twice is refused
    assert client.post(f"/api/scans/{sid}/issues/{fix_issue['id']}/decision",
                       json={"decision": "approve"}).status_code == 409

    other = next(i for i in scan["issues"] if i["status"] == "open" and i["id"] != fix_issue["id"])
    r = client.post(f"/api/scans/{sid}/issues/{other['id']}/decision", json={"decision": "reject"})
    assert r.json()["summary"]["rejected"] == 1

    rescanned = client.post(f"/api/scans/{sid}/rescan").json()
    assert rescanned["summary"]["open_issues"] == 14
    assert rescanned["summary"]["rejected"] == 1

    csv_text = client.get(f"/api/scans/{sid}/export/ledger").text
    assert fix_issue["fix"]["params"]["category"] in csv_text
    assert "approve" in client.get(f"/api/scans/{sid}/export/audit").text


def test_upload_and_bad_csv(client):
    good = "Date,Description,Amount\n2026-01-01,Coffee,-4.50\n2026-01-01,Coffee,-4.50\n"
    r = client.post("/api/scans", data={"name": "Test"}, files={"bank": ("bank.csv", good, "text/csv")})
    assert r.status_code == 200
    assert r.json()["summary"]["by_check"][0]["check"] == "duplicate"

    r = client.post("/api/scans", files={"bank": ("bad.csv", "foo,bar\n1,2\n", "text/csv")})
    assert r.status_code == 400


def test_chat_without_llm_key_uses_fallback(client):
    sid = client.post("/api/scans/sample").json()["id"]
    r = client.post(f"/api/scans/{sid}/chat", json={"message": "What should I fix first?"})
    assert "health score" in r.json()["answer"]
    assert len(r.json()["chat"]) == 2


def test_password_protection(client, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "s3cret")
    assert client.get("/api/scans").status_code == 401
    assert client.get("/health").status_code == 200
    token = base64.b64encode(b"owner:s3cret").decode()
    assert client.get("/api/scans", headers={"Authorization": f"Basic {token}"}).status_code == 200
