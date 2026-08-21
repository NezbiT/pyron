from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Book(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True, max_length=200)
    author: str = Field(index=True, max_length=160)
    isbn: str = Field(default="", max_length=20)
    price: float = Field(ge=0)
    year: int = Field(default=0, ge=0, le=2100)
    description: str = Field(default="")
    in_stock: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
