from pydantic import BaseModel, Field


class BookIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    author: str = Field(min_length=1, max_length=160)
    isbn: str = Field(default="", max_length=20)
    price: float = Field(ge=0, le=10_000)
    year: int = Field(default=0, ge=0, le=2100)
    description: str = Field(default="", max_length=4000)
    in_stock: bool = True


class BookOut(BookIn):
    id: int


class BookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    author: str | None = Field(default=None, min_length=1, max_length=160)
    isbn: str | None = None
    price: float | None = Field(default=None, ge=0)
    year: int | None = Field(default=None, ge=0, le=2100)
    description: str | None = None
    in_stock: bool | None = None
