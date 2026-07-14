from fastapi.testclient import TestClient

from backend.app.auth import auth_store
from backend.app.main import app


def _register(client: TestClient) -> str:
    response = client.post(
        "/api/auth/register",
        json={
            "name": "ტესტ მომხმარებელი",
            "email": "api-test@example.com",
            "password": "strong-pass-123",
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def test_protected_tools_require_authentication(tmp_path) -> None:
    original_path = auth_store.path
    auth_store.path = tmp_path / "api-auth.db"
    try:
        with TestClient(app) as client:
            grammar = client.post(
                "/api/grammar/check",
                json={"text": "გამარჯობა"},
            )
            library = client.post(
                "/api/library/search",
                json={"query": "ვაჟა-ფშაველა"},
            )
        assert grammar.status_code == 401
        assert library.status_code == 401
    finally:
        auth_store.path = original_path


def test_authenticated_chat_and_tools(tmp_path) -> None:
    original_path = auth_store.path
    auth_store.path = tmp_path / "api-auth.db"
    try:
        with TestClient(app) as client:
            token = _register(client)
            headers = {"Authorization": f"Bearer {token}"}

            grammar = client.post(
                "/api/grammar/check",
                headers=headers,
                json={"text": "რათქმაუნდა, მოვალ."},
            )
            assert grammar.status_code == 200
            assert grammar.json()["corrected"].startswith("რა თქმა უნდა")

            greeting = client.post(
                "/api/chat",
                headers=headers,
                json={"message": "გამარჯობა", "mode": "learn"},
            )
            assert greeting.status_code == 200
            assert "ნებისმიერ თემაზე" in greeting.text

            river = client.post(
                "/api/chat",
                headers=headers,
                json={
                    "message": "რომელია ყველაზე დიდი მდინარე?",
                    "mode": "learn",
                },
            )
            assert river.status_code == 200
            assert "ამაზონი" in river.text
            assert "არაგვი" not in river.text
    finally:
        auth_store.path = original_path
