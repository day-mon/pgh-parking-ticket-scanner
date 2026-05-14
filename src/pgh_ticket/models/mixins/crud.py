"""Async CRUD mixin for SQLAlchemy models."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self, Sequence

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

type FilterDict = dict[str, object]
type OrderByClause = list[
    ColumnElement[object] | InstrumentedAttribute[object]
]


class CRUDMixin:
    """Async CRUD operations for SQLAlchemy models."""

    def merge(self, data: dict, *, exclude: set[str] | None = None) -> None:
        """Update fields from a dict, skipping primary keys and excluded fields."""
        skip = exclude or set()
        for key, value in data.items():
            if key in skip:
                continue
            if hasattr(self, key):
                setattr(self, key, value)

    @classmethod
    async def create(
        cls, session: AsyncSession, commit: bool = True, **kwargs: object
    ) -> Self:
        obj = cls(**kwargs)
        session.add(obj)
        if commit:
            await session.commit()
            await session.refresh(obj)
        return obj

    @classmethod
    async def bulk_create(
        cls,
        session: AsyncSession,
        objects: list[dict[str, object]],
        commit: bool = True,
    ) -> None:
        session.add_all([cls(**o) for o in objects])
        if commit:
            await session.commit()

    @classmethod
    async def get_or_create(
        cls,
        session: AsyncSession,
        defaults: FilterDict | None = None,
        commit: bool = True,
        **kwargs: object,
    ) -> tuple[Self, bool]:
        if obj := await cls.filter_one(session, **kwargs):
            return obj, False
        create_kwargs = {**(defaults or {}), **kwargs}
        return await cls.create(session, commit=commit, **create_kwargs), True

    @classmethod
    async def get(cls, session: AsyncSession, pk: object) -> Self | None:
        return await session.get(cls, pk)

    @classmethod
    async def get_or_raise(cls, session: AsyncSession, pk: object) -> Self:
        if obj := await session.get(cls, pk):
            return obj
        raise NoResultFound(f"{cls.__name__} with pk={pk!r} not found")

    @classmethod
    async def filter_one(
        cls, session: AsyncSession, **kwargs: object
    ) -> Self | None:
        return (
            await session.execute(select(cls).filter_by(**kwargs).limit(1))
        ).scalars().first()

    @classmethod
    async def list(
        cls,
        session: AsyncSession,
        limit: int | None = None,
        offset: int | None = None,
        order_by: OrderByClause | None = None,
    ) -> Sequence[Self]:
        stmt = select(cls)
        if order_by:
            stmt = stmt.order_by(*order_by)
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return (await session.execute(stmt)).scalars().all()

    @classmethod
    async def filter(
        cls,
        session: AsyncSession,
        *,
        filters: FilterDict | None = None,
        or_filters: FilterDict | None = None,
        limit: int | None = None,
        offset: int | None = None,
        order_by: OrderByClause | None = None,
    ) -> Sequence[Self]:
        stmt = select(cls)

        and_clauses = [
            getattr(cls, key) == value
            for key, value in (filters or {}).items()
        ]
        or_clauses = [
            getattr(cls, key) == value
            for key, value in (or_filters or {}).items()
        ]

        if and_clauses and or_clauses:
            stmt = stmt.where(and_(*and_clauses, or_(*or_clauses)))
        elif and_clauses:
            stmt = stmt.where(and_(*and_clauses))
        elif or_clauses:
            stmt = stmt.where(or_(*or_clauses))

        if order_by:
            stmt = stmt.order_by(*order_by)
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)

        return (await session.execute(stmt)).scalars().all()

    @classmethod
    async def search(
        cls,
        session: AsyncSession,
        column: str,
        query: str,
        *,
        case_sensitive: bool = False,
        limit: int | None = None,
        offset: int | None = None,
    ) -> Sequence[Self]:
        col: InstrumentedAttribute[object] = getattr(cls, column)
        pattern = f"%{query}%"
        condition = col.like(pattern) if case_sensitive else col.ilike(pattern)
        stmt = select(cls).where(condition)
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return (await session.execute(stmt)).scalars().all()

    @classmethod
    async def update(
        cls, session: AsyncSession, pk: object, commit: bool = True, **kwargs: object
    ) -> Self | None:
        if not (obj := await session.get(cls, pk)):
            return None
        for key, value in kwargs.items():
            setattr(obj, key, value)
        session.add(obj)
        if commit:
            await session.commit()
            await session.refresh(obj)
        return obj

    @classmethod
    async def update_or_raise(
        cls, session: AsyncSession, pk: object, **kwargs: object
    ) -> Self:
        if not (obj := await cls.update(session, pk, True, **kwargs)):
            raise NoResultFound(f"{cls.__name__} with pk={pk!r} not found")
        return obj

    @classmethod
    async def upsert(cls, session: AsyncSession, **kwargs: object) -> Self:
        """Merge by PK — updates if exists, inserts if not."""
        obj = cls(**kwargs)
        merged = await session.merge(obj)
        await session.commit()
        await session.refresh(merged)
        return merged

    @classmethod
    async def delete(
        cls, session: AsyncSession, pk: object, commit: bool = True
    ) -> bool:
        if not (obj := await session.get(cls, pk)):
            return False
        await session.delete(obj)
        if commit:
            await session.commit()
        return True

    @classmethod
    async def delete_or_raise(
        cls, session: AsyncSession, pk: object
    ) -> None:
        if not await cls.delete(session, pk):
            raise NoResultFound(f"{cls.__name__} with pk={pk!r} not found")

    @classmethod
    async def bulk_delete(
        cls, session: AsyncSession, **filters: object
    ) -> int:
        objs = await cls.filter(session, filters=filters)
        for obj in objs:
            await session.delete(obj)
        await session.commit()
        return len(objs)

    @classmethod
    async def count(
        cls, session: AsyncSession, **filters: object
    ) -> int:
        stmt = select(func.count()).select_from(cls)
        if filters:
            clauses = [getattr(cls, k) == v for k, v in filters.items()]
            stmt = stmt.where(and_(*clauses))
        return (await session.execute(stmt)).scalar_one()

    @classmethod
    async def exists(cls, session: AsyncSession, **kwargs: object) -> bool:
        return await cls.count(session, **kwargs) > 0
