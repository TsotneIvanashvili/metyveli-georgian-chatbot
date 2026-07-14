import sqlite3

import pytest
from fastapi import HTTPException

from backend.app.auth import (
    AuthStore,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    require_user,
)


def test_register_login_session_and_logout(tmp_path) -> None:
    database = tmp_path / "auth-test.db"
    store = AuthStore(database)
    store.initialize()

    user, token = store.register(
        "ნინო",
        "NINO@example.com",
        "strong-pass-123",
    )
    assert user["email"] == "nino@example.com"
    assert store.user_for_token(token) == user

    with sqlite3.connect(database) as connection:
        stored = connection.execute(
            "SELECT password_hash FROM users WHERE id = ?",
            (user["id"],),
        ).fetchone()[0]
    assert stored != "strong-pass-123"
    assert stored.startswith("pbkdf2_sha256$")

    logged_in_user, second_token = store.authenticate(
        "nino@example.com",
        "strong-pass-123",
    )
    assert logged_in_user == user
    assert second_token != token

    store.logout(second_token)
    assert store.user_for_token(second_token) is None


def test_duplicate_and_invalid_credentials(tmp_path) -> None:
    store = AuthStore(tmp_path / "auth-test.db")
    store.initialize()
    store.register("ნინო", "nino@example.com", "strong-pass-123")

    with pytest.raises(EmailAlreadyRegisteredError):
        store.register(
            "სხვა ნინო",
            "nino@example.com",
            "another-pass-123",
        )

    with pytest.raises(InvalidCredentialsError):
        store.authenticate("nino@example.com", "wrong-password")


def test_missing_bearer_token_is_rejected() -> None:
    with pytest.raises(HTTPException) as error:
        require_user(None)
    assert error.value.status_code == 401
