"""Base repository with common CRUD operations."""

from collections.abc import Sequence
from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    """Generic asynchronous repository providing common database operations."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, id: UUID) -> ModelT | None:
        """Get a single record by primary key."""
        result = await self.session.execute(
            select(self.model).where(getattr(self.model, "id") == id)  # noqa: B009 - ModelT has no static attr
        )
        return result.scalar_one_or_none()

    async def get_by(self, **kwargs: Any) -> ModelT | None:
        """Get a single record by arbitrary column filters."""
        query = select(self.model)
        for key, value in kwargs.items():
            query = query.where(getattr(self.model, key) == value)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list(
        self,
        *filters: Any,
        order_by: Any | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> Sequence[ModelT]:
        """List records with optional filtering, ordering, and pagination."""
        query = select(self.model)
        for clause in filters:
            query = query.where(clause)
        if order_by is not None:
            query = query.order_by(order_by)
        if limit is not None:
            query = query.limit(limit)
        if offset is not None:
            query = query.offset(offset)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count(self, *filters: Any) -> int:
        """Count records matching optional filters."""
        query = select(func.count()).select_from(self.model)
        for clause in filters:
            query = query.where(clause)
        result = await self.session.execute(query)
        return int(result.scalar_one())

    async def create(self, **kwargs: Any) -> ModelT:
        """Create a new record."""
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def add(self, instance: ModelT) -> ModelT:
        """Add an existing instance to the session."""
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def update(self, instance: ModelT, **kwargs: Any) -> ModelT:
        """Update fields on an instance."""
        for key, value in kwargs.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        await self.session.flush()
        return instance

    async def delete(self, instance: ModelT) -> None:
        """Delete an instance."""
        await self.session.delete(instance)
        await self.session.flush()

    async def upsert_by(
        self,
        match_fields: dict[str, Any],
        values: dict[str, Any],
    ) -> ModelT:
        """Get an existing record or create a new one."""
        instance = await self.get_by(**match_fields)
        if instance is None:
            return await self.create(**{**match_fields, **values})
        return await self.update(instance, **values)


def paginate_query(
    query: Select,
    page: int = 1,
    per_page: int = 30,
) -> Select:
    """Apply offset/limit pagination to a select query."""
    offset = (page - 1) * per_page
    return query.offset(offset).limit(per_page)
