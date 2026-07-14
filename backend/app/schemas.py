from typing import Literal

from pydantic import BaseModel, Field, field_validator


ChatMode = Literal["grammar", "literature", "learn"]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12_000)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        return value.strip()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4_000)
    mode: ChatMode = "learn"
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        return value.strip()


class GrammarRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12_000)

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class LibrarySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=8, ge=1, le=20)

