"""Pydantic document model for MongoDB collections."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field


class Document(BaseModel):
    """A MongoDB document. Register it on the admin panel like a SQLModel table."""

    model_config = ConfigDict(extra="ignore")
    collection: ClassVar[str] = ""
    database: ClassVar[str | None] = None
    id: str | None = Field(default=None)
