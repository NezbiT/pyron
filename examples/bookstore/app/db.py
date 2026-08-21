from pathlib import Path

from sqlmodel import Session, select

from app.models import Book
from pyron.db import create_engine, get_session, init_db

# Absolute path so /admin always hits this file, not a pyron.db created
# wherever the process happened to start.
DB_PATH = Path(__file__).resolve().parent.parent / "bookstore.db"
engine = create_engine(f"sqlite:///{DB_PATH.as_posix()}")
SessionDep = get_session(engine)

SEED = [
    {
        "title": "The Tide Tables",
        "author": "Mara Ellison",
        "isbn": "9780001112223",
        "price": 14.0,
        "year": 1984,
        "description": "A year of annotated tide charts from a North Sea harbour, with notes in the margins about who came in on which flood.",
    },
    {
        "title": "Copper & Salt",
        "author": "J. P. Havel",
        "isbn": "9780001112224",
        "price": 22.5,
        "year": 1971,
        "description": "Essays on shipbreaking yards. The copy on the shelf has a water stain that stops at chapter four.",
    },
    {
        "title": "Night Watch on the Barque",
        "author": "Selim Ortez",
        "isbn": "9780001112225",
        "price": 9.0,
        "year": 1958,
        "description": "A short novel that never leaves the deck of one ship. First English printing.",
    },
    {
        "title": "A Glossary of Knots",
        "author": "Edith Crane",
        "isbn": "9780001112226",
        "price": 18.0,
        "year": 1932,
        "description": "Practical, unsentimental, still the shop's most stolen book.",
    },
]


def setup() -> None:
    init_db(engine)
    with Session(engine) as session:
        existing = session.exec(select(Book)).first()
        if existing is not None:
            return
        for row in SEED:
            session.add(Book(**row))
        session.commit()
