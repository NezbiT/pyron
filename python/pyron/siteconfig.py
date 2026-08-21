"""Singleton site settings: name, contact, hours. Public templates read this."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlmodel import Field, Session, SQLModel, select

_TEL_KEEP = re.compile(r"[^\d+]")


class SiteSettings(SQLModel, table=True):
    __tablename__ = "pyron_site"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(default="", max_length=120)
    tagline: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=120)
    hours: str = Field(default="", max_length=200)
    address: str = Field(default="", max_length=200)
    website: str = Field(default="", max_length=200)


@dataclass(frozen=True)
class SiteView:
    name: str = ""
    tagline: str = ""
    phone: str = ""
    email: str = ""
    hours: str = ""
    address: str = ""
    website: str = ""

    @property
    def phone_href(self) -> str:
        digits = _TEL_KEEP.sub("", self.phone)
        return f"tel:{digits}" if digits else ""


def _as_view(row: SiteSettings | None, fallback: str = "Pyron") -> SiteView:
    if row is None:
        return SiteView(name=fallback)
    return SiteView(
        name=(row.name or "").strip() or fallback,
        tagline=(row.tagline or "").strip(),
        phone=(row.phone or "").strip(),
        email=(row.email or "").strip(),
        hours=(row.hours or "").strip(),
        address=(row.address or "").strip(),
        website=(row.website or "").strip(),
    )


def load_site(engine: Any, fallback: str = "Pyron") -> SiteView:
    if engine is None:
        return SiteView(name=fallback)
    try:
        with Session(engine) as db:
            row = db.exec(select(SiteSettings).where(SiteSettings.id == 1)).first()
            if row is None:
                row = db.exec(select(SiteSettings).limit(1)).first()
            return _as_view(row, fallback)
    except Exception:
        return SiteView(name=fallback)


def seed_site(engine: Any, title: str = "Pyron") -> None:
    if engine is None:
        return
    name = (title or "Pyron").strip() or "Pyron"
    with Session(engine) as db:
        try:
            if db.exec(select(SiteSettings).limit(1)).first() is not None:
                return
        except Exception:
            return
        db.add(
            SiteSettings(
                id=1,
                name=name,
                tagline="",
                phone="",
                email="",
                hours="",
                address="",
                website="",
            )
        )
        db.commit()


def save_site(engine: Any, values: dict[str, Any]) -> SiteView:
    with Session(engine) as db:
        row = db.exec(select(SiteSettings).where(SiteSettings.id == 1)).first()
        if row is None:
            row = db.exec(select(SiteSettings).limit(1)).first()
        if row is None:
            row = SiteSettings(id=1)
            db.add(row)
        row.name = str(values.get("name") or "").strip()
        row.tagline = str(values.get("tagline") or "").strip()
        row.phone = str(values.get("phone") or "").strip()
        row.email = str(values.get("email") or "").strip().lower()
        row.hours = str(values.get("hours") or "").strip()
        row.address = str(values.get("address") or "").strip()
        row.website = _normalize_website(str(values.get("website") or "").strip())
        db.add(row)
        db.commit()
        db.refresh(row)
        return _as_view(row, row.name or "Pyron")


def clean_site_values(values: dict[str, Any], fallback: str = "Pyron") -> dict[str, Any]:
    name = str(values.get("name") or "").strip() or fallback
    email = str(values.get("email") or "").strip()
    if email and "@" not in email:
        raise ValueError("That email is missing an @.")
    website = str(values.get("website") or "").strip()
    if website and " " in website:
        raise ValueError("The website should be one URL, without spaces.")
    return {
        "name": name,
        "tagline": str(values.get("tagline") or "").strip(),
        "phone": str(values.get("phone") or "").strip(),
        "email": email.lower() if email else "",
        "hours": str(values.get("hours") or "").strip(),
        "address": str(values.get("address") or "").strip(),
        "website": website,
    }


def _normalize_website(url: str) -> str:
    if not url:
        return ""
    if url.startswith(("http://", "https://", "/")):
        return url
    return "https://" + url
