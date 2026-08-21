"""Harbor Bindings — Pyron example: SSR catalog + JSON API + OpenAPI."""

from __future__ import annotations

from sqlmodel import Session, select
from starlette.requests import Request

from contextlib import asynccontextmanager

from app.db import engine, setup
from app.models import Book
from app.schemas import BookIn, BookOut, BookUpdate
from pyron import APIRouter, HTTPException, ModelAdmin, Pyron, Query, permission_required
from pyron.responses import RedirectResponse


@asynccontextmanager
async def lifespan(_app: Pyron):
    setup()
    yield


app = Pyron(
    title="Harbor Bindings",
    version="0.6.2",
    description="A used bookstore. The catalog is server-rendered for search engines; "
    "the same records are available as JSON.",
    templates="templates",
    static_dir="static",
    servers=[{"url": "/", "description": "this server"}],
    lifespan=lifespan,
    admin=True,
    admin_engine=engine,
)


class BookAdmin(ModelAdmin):
    list_display = ["id", "title", "author", "price", "in_stock"]
    search_fields = ["title", "author", "isbn"]
    list_filter = ["in_stock"]


app.admin.register(Book, BookAdmin)

api = APIRouter(prefix="/api", tags=["books"])


def _session() -> Session:
    return Session(engine)


def _to_out(book: Book) -> BookOut:
    return BookOut.model_validate(book, from_attributes=True)


# ---------------------------------------------------------------------------
# Pages (SSR — this is what crawlers and humans without JS get)
# ---------------------------------------------------------------------------


@app.get("/", tags=["pages"], include_in_schema=False)
async def home(request: Request):
    with _session() as session:
        books = session.exec(select(Book).order_by(Book.title).limit(4)).all()
    return await app.render(
        request,
        "home.html",
        {"books": books, "page": "home"},
    )


@app.get("/catalog", tags=["pages"], include_in_schema=False)
async def catalog(request: Request, q: str = ""):
    with _session() as session:
        stmt = select(Book).order_by(Book.title)
        books = session.exec(stmt).all()
    if q:
        needle = q.lower()
        books = [b for b in books if needle in b.title.lower() or needle in b.author.lower()]
    return await app.render(
        request,
        "catalog.html",
        {"books": books, "q": q, "page": "catalog"},
    )


@app.get("/books/{book_id}", tags=["pages"], include_in_schema=False)
async def book_page(request: Request, book_id: int):
    with _session() as session:
        book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(404, "That book is not on the shelf.")
    return await app.render(request, "book.html", {"book": book, "page": "catalog"})


@app.get("/acquire", tags=["pages"], include_in_schema=False)
async def acquire_form(request: Request, error: str = "", title: str = "", author: str = ""):
    return await app.render(
        request,
        "acquire.html",
        {
            "page": "acquire",
            "error": error,
            "form": {"title": title, "author": author, "price": "", "year": "", "description": ""},
        },
    )


@app.api_route("/acquire", methods=["POST"], tags=["pages"], include_in_schema=False)
async def acquire_submit(request: Request):
    form = await request.form()
    title = str(form.get("title") or "").strip()
    author = str(form.get("author") or "").strip()
    try:
        price = float(str(form.get("price") or "0"))
    except ValueError:
        price = -1
    try:
        year = int(str(form.get("year") or "0"))
    except ValueError:
        year = 0
    description = str(form.get("description") or "").strip()
    if not title or not author:
        return await app.render(
            request,
            "acquire.html",
            {
                "page": "acquire",
                "error": "A book needs a title and an author — both, not one.",
                "form": {
                    "title": title,
                    "author": author,
                    "price": form.get("price") or "",
                    "year": form.get("year") or "",
                    "description": description,
                },
            },
            status_code=422,
        )
    if price < 0:
        return await app.render(
            request,
            "acquire.html",
            {
                "page": "acquire",
                "error": "Price has to be a number, zero or more. You can list a book as free.",
                "form": {
                    "title": title,
                    "author": author,
                    "price": form.get("price") or "",
                    "year": form.get("year") or "",
                    "description": description,
                },
            },
            status_code=422,
        )
    with _session() as session:
        book = Book(
            title=title,
            author=author,
            price=price,
            year=year,
            description=description,
            in_stock=True,
        )
        session.add(book)
        session.commit()
        session.refresh(book)
        book_id = book.id
    return RedirectResponse(f"/books/{book_id}", status_code=303)


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------


@api.get("/books", response_model=list)
async def list_books(q: str = Query("", description="Filter by title or author")) -> list[BookOut]:
    with _session() as session:
        books = session.exec(select(Book).order_by(Book.title)).all()
    if q:
        needle = q.lower()
        books = [b for b in books if needle in b.title.lower() or needle in b.author.lower()]
    return [_to_out(b) for b in books]


@api.get("/books/{book_id}", response_model=BookOut)
async def get_book(book_id: int) -> BookOut:
    with _session() as session:
        book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(404, "That book is not on the shelf.")
    return _to_out(book)


@api.post("/books", status_code=201, response_model=BookOut)
async def create_book(payload: BookIn) -> BookOut:
    with _session() as session:
        book = Book(**payload.model_dump())
        session.add(book)
        session.commit()
        session.refresh(book)
        return _to_out(book)


@api.patch("/books/{book_id}", response_model=BookOut)
async def update_book(book_id: int, payload: BookUpdate) -> BookOut:
    with _session() as session:
        book = session.get(Book, book_id)
        if book is None:
            raise HTTPException(404, "That book is not on the shelf.")
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(book, key, value)
        session.add(book)
        session.commit()
        session.refresh(book)
        return _to_out(book)


@api.delete("/books/{book_id}", status_code=204)
@permission_required("book.delete")
async def delete_book(book_id: int) -> None:
    with _session() as session:
        book = session.get(Book, book_id)
        if book is None:
            raise HTTPException(404, "That book is not on the shelf.")
        session.delete(book)
        session.commit()


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    from pyron._bridge import CORE

    return {"status": "ok", "core": CORE}


app.include_router(api)
