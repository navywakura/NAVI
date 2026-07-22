from datetime import datetime, timezone

from bot.cogs.levels import level_for_xp
from database.connection import _normalise_database_url
from web.app import _manageable_guilds


def test_database_url_normalisation() -> None:
    assert _normalise_database_url("postgres://u:p@host/db").startswith("postgresql+asyncpg://")
    assert _normalise_database_url("postgresql://u:p@host/db").startswith("postgresql+asyncpg://")
    assert _normalise_database_url("sqlite:///./navi.db") == "sqlite+aiosqlite:///./navi.db"


def test_manageable_guild_filter() -> None:
    guilds = [
        {"id": "1", "name": "Owner", "owner": True, "permissions": "0", "icon": None},
        {"id": "2", "name": "Admin", "owner": False, "permissions": str(1 << 3), "icon": None},
        {"id": "3", "name": "Manager", "owner": False, "permissions": str(1 << 5), "icon": None},
        {"id": "4", "name": "Member", "owner": False, "permissions": "0", "icon": None},
    ]
    assert [item["id"] for item in _manageable_guilds(guilds)] == ["1", "2", "3"]


def test_level_curve() -> None:
    assert level_for_xp(0) == 0
    assert level_for_xp(100) == 1
    assert level_for_xp(400) == 2
    assert level_for_xp(900) == 3
