from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import get_settings
from database.models import Base


def _normalise_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("sqlite:///"):
        return "sqlite+aiosqlite:///" + url[len("sqlite:///") :]
    return url


settings = get_settings()
_database_url = _normalise_database_url(settings.database_url)

_engine_kwargs: dict[str, object] = {"pool_pre_ping": True, "echo": False}
if _database_url.startswith("sqlite+"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine: AsyncEngine = create_async_engine(_database_url, **_engine_kwargs)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


def _apply_compatibility_columns(connection) -> None:
    """Small idempotent migration for installations created by the v1.0 MVP.

    New tables are created by ``metadata.create_all``. Existing ``guild_configs``
    tables need explicit columns because ``create_all`` never alters a table.
    """

    inspector = inspect(connection)
    if "guild_configs" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("guild_configs")}
    additions = {
        "animals_enabled": "BOOLEAN NOT NULL DEFAULT TRUE",
        "games_enabled": "BOOLEAN NOT NULL DEFAULT TRUE",
        "social_enabled": "BOOLEAN NOT NULL DEFAULT TRUE",
        "roleplay_enabled": "BOOLEAN NOT NULL DEFAULT TRUE",
        "images_enabled": "BOOLEAN NOT NULL DEFAULT TRUE",
        "tags_enabled": "BOOLEAN NOT NULL DEFAULT TRUE",
        "moderation_enabled": "BOOLEAN NOT NULL DEFAULT TRUE",
        "reminders_enabled": "BOOLEAN NOT NULL DEFAULT TRUE",
        "confession_channel_id": "BIGINT NULL",
        "confessions_enabled": "BOOLEAN NOT NULL DEFAULT FALSE",
        "anonymous_confessions": "BOOLEAN NOT NULL DEFAULT TRUE",
        "social_cooldown_seconds": "INTEGER NOT NULL DEFAULT 8",
        "social_gifs_enabled": "BOOLEAN NOT NULL DEFAULT TRUE",
        "modlog_channel_id": "BIGINT NULL",
    }
    for name, ddl in additions.items():
        if name not in existing:
            connection.exec_driver_sql(f"ALTER TABLE guild_configs ADD COLUMN {name} {ddl}")


async def init_db() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(_apply_compatibility_columns)


async def close_db() -> None:
    await engine.dispose()
