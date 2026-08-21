"""Public options for how a model appears on the admin panel."""

from __future__ import annotations


class TabularInline:
    """One-level children on the change form (Django TabularInline, simplified)."""

    model: type | None = None
    fk_name: str | None = None
    extra: int = 1
    exclude: list[str] | None = None


class ModelAdmin:
    """How a table or document appears on the panel. Same idea as Django's ModelAdmin."""

    list_display: list[str] | None = None
    search_fields: list[str] | None = None
    list_filter: list[str] | None = None
    exclude: list[str] | None = None
    ordering: str | None = None
    list_per_page: int = 25
    verbose_name: str | None = None
    verbose_name_plural: str | None = None
    can_create: bool = True
    can_edit: bool = True
    can_delete: bool = True
    inlines: list[type] | None = None
    actions: list[str] | None = None

    def __init__(self, model: type | None = None) -> None:
        if model is not None:
            self.model = model
