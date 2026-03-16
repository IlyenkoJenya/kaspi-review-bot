from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.config import config
from src.database.models import Base

engine: AsyncEngine | None = None
async_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db() -> None:
    """Initialize database engine and create all tables."""
    global engine, async_session_factory

    engine = create_async_engine(
        config.database_url,
        echo=False,
        connect_args={"check_same_thread": False} if "sqlite" in config.database_url else {},
    )

    async_session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Return a new async session. Caller is responsible for closing it."""
    if async_session_factory is None:
        raise RuntimeError("Database is not initialized. Call init_db() first.")
    return async_session_factory()


async def close_db() -> None:
    """Dispose the engine on shutdown."""
    if engine:
        await engine.dispose()
