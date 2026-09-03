from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.config import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield one database session per request and close it afterward."""
    async with SessionFactory() as session:
        yield session


DatabaseSession = Annotated[AsyncSession, Depends(get_session)]
