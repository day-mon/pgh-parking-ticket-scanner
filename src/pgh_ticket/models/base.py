"""SQLAlchemy declarative base with CRUD mixin."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase

from pgh_ticket.models.mixins.crud import CRUDMixin


class Base(DeclarativeBase, CRUDMixin):
    pass
