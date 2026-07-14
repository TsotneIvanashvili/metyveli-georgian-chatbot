from __future__ import annotations

import base64
import hashlib
import re
import secrets
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator

from .config import get_settings

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - local SQLite mode does not need it.
    psycopg = None
    dict_row = None


PASSWORD_ITERATIONS = 310_000
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailAlreadyRegisteredError(ValueError):
    pass


class InvalidCredentialsError(ValueError):
    pass


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        clean = re.sub(r"\s+", " ", value).strip()
        if len(clean) < 2:
            raise ValueError("სახელი მინიმუმ 2 სიმბოლოს უნდა შეიცავდეს.")
        return clean

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        clean = value.casefold().strip()
        if not EMAIL_PATTERN.fullmatch(clean):
            raise ValueError("ელფოსტის ფორმატი არასწორია.")
        return clean


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        return value.casefold().strip()


class AuthUser(BaseModel):
    id: str
    name: str
    email: str
    created_at: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUser


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return (
        f"pbkdf2_sha256${PASSWORD_ITERATIONS}"
        f"${_encode(salt)}${_encode(digest)}"
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _decode(salt),
            int(iterations),
        )
        return secrets.compare_digest(actual, _decode(expected))
    except (TypeError, ValueError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SQLiteAuthStore:
    def __init__(self, path: Path, session_days: int = 7) -> None:
        self.path = path
        self.session_seconds = session_days * 86_400

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_user
                    ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_expiry
                    ON sessions(expires_at);
                """
            )
            connection.execute(
                "DELETE FROM sessions WHERE expires_at <= ?",
                (int(time.time()),),
            )

    @staticmethod
    def _public_user(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "email": row["email"],
            "created_at": row["created_at"],
        }

    def _create_session(
        self,
        connection: sqlite3.Connection,
        user_id: str,
    ) -> str:
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        connection.execute(
            """
            INSERT INTO sessions(token_hash, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                _token_hash(token),
                user_id,
                now,
                now + self.session_seconds,
            ),
        )
        return token

    def register(
        self,
        name: str,
        email: str,
        password: str,
    ) -> tuple[dict, str]:
        user_id = secrets.token_hex(16)
        created_at = datetime.now(UTC).isoformat()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO users(id, name, email, password_hash, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        name,
                        email.casefold(),
                        hash_password(password),
                        created_at,
                    ),
                )
                token = self._create_session(connection, user_id)
        except sqlite3.IntegrityError as exc:
            raise EmailAlreadyRegisteredError from exc

        return (
            {
                "id": user_id,
                "name": name,
                "email": email.casefold(),
                "created_at": created_at,
            },
            token,
        )

    def authenticate(
        self,
        email: str,
        password: str,
    ) -> tuple[dict, str]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE email = ? COLLATE NOCASE",
                (email.casefold(),),
            ).fetchone()
            if row is None or not verify_password(
                password,
                row["password_hash"],
            ):
                raise InvalidCredentialsError
            token = self._create_session(connection, row["id"])
            return self._public_user(row), token

    def user_for_token(self, token: str) -> dict | None:
        now = int(time.time())
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT users.id, users.name, users.email, users.created_at
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ? AND sessions.expires_at > ?
                """,
                (_token_hash(token), now),
            ).fetchone()
        return self._public_user(row) if row is not None else None

    def logout(self, token: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE token_hash = ?",
                (_token_hash(token),),
            )


AuthStore = SQLiteAuthStore


class PostgresAuthStore:
    def __init__(self, database_url: str, session_days: int = 7) -> None:
        self.database_url = database_url
        self.session_seconds = session_days * 86_400

    def _connect(self):
        if psycopg is None or dict_row is None:
            raise RuntimeError(
                "PostgreSQL auth requires the psycopg package. "
                "Install backend requirements before using DATABASE_URL."
            )
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower
                    ON users (lower(email))
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL
                        REFERENCES users(id) ON DELETE CASCADE,
                    created_at BIGINT NOT NULL,
                    expires_at BIGINT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_user
                    ON sessions(user_id)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_expiry
                    ON sessions(expires_at)
                """
            )
            connection.execute(
                "DELETE FROM sessions WHERE expires_at <= %s",
                (int(time.time()),),
            )

    @staticmethod
    def _public_user(row: dict[str, Any]) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "email": row["email"],
            "created_at": row["created_at"],
        }

    def _create_session(self, connection, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        connection.execute(
            """
            INSERT INTO sessions(token_hash, user_id, created_at, expires_at)
            VALUES (%s, %s, %s, %s)
            """,
            (
                _token_hash(token),
                user_id,
                now,
                now + self.session_seconds,
            ),
        )
        return token

    def register(
        self,
        name: str,
        email: str,
        password: str,
    ) -> tuple[dict, str]:
        user_id = secrets.token_hex(16)
        created_at = datetime.now(UTC).isoformat()
        normalized_email = email.casefold()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO users(id, name, email, password_hash, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        name,
                        normalized_email,
                        hash_password(password),
                        created_at,
                    ),
                )
                token = self._create_session(connection, user_id)
        except Exception as exc:
            if psycopg is not None and isinstance(
                exc,
                psycopg.errors.UniqueViolation,
            ):
                raise EmailAlreadyRegisteredError from exc
            raise

        return (
            {
                "id": user_id,
                "name": name,
                "email": normalized_email,
                "created_at": created_at,
            },
            token,
        )

    def authenticate(
        self,
        email: str,
        password: str,
    ) -> tuple[dict, str]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE lower(email) = lower(%s)",
                (email.casefold(),),
            ).fetchone()
            if row is None or not verify_password(
                password,
                row["password_hash"],
            ):
                raise InvalidCredentialsError
            token = self._create_session(connection, row["id"])
            return self._public_user(row), token

    def user_for_token(self, token: str) -> dict | None:
        now = int(time.time())
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT users.id, users.name, users.email, users.created_at
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = %s AND sessions.expires_at > %s
                """,
                (_token_hash(token), now),
            ).fetchone()
        return self._public_user(row) if row is not None else None

    def logout(self, token: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE token_hash = %s",
                (_token_hash(token),),
            )


def create_auth_store(settings):
    if settings.database_url:
        return PostgresAuthStore(
            settings.database_url,
            session_days=settings.auth_session_days,
        )
    return SQLiteAuthStore(
        settings.auth_database_path,
        session_days=settings.auth_session_days,
    )


settings = get_settings()
auth_store = create_auth_store(settings)
bearer_scheme = HTTPBearer(auto_error=False)


def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
) -> dict:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ავტორიზაცია აუცილებელია.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = auth_store.user_for_token(credentials.credentials)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="სესია აღარ მოქმედებს. თავიდან გაიარე ავტორიზაცია.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
