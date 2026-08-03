"""Shared response envelopes and primitives."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorDetail(BaseModel):
    code: str
    message: str
    detail: object | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int = 50
    offset: int = 0


class ServiceBanner(BaseModel):
    """Honest disclosure of degraded providers, rendered as a UI banner."""

    degraded: bool = False
    messages: list[str] = Field(default_factory=list)
    providers: dict = Field(default_factory=dict)


class Ack(BaseModel):
    ok: bool = True
    message: str = ""
