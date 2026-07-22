from __future__ import annotations

from sqlalchemy import or_, select

from database.connection import AsyncSessionLocal
from database.models import SocialBlock, SocialPreference


async def is_blocked(guild_id: int, actor_id: int, target_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SocialBlock).where(
                SocialBlock.guild_id == guild_id,
                or_(
                    (SocialBlock.user_id == target_id) & (SocialBlock.blocked_user_id == actor_id),
                    (SocialBlock.user_id == actor_id) & (SocialBlock.blocked_user_id == target_id),
                ),
            )
        )
        return result.scalar_one_or_none() is not None


async def get_preference(guild_id: int, user_id: int) -> SocialPreference:
    async with AsyncSessionLocal() as session:
        preference = await session.get(SocialPreference, (guild_id, user_id))
        if preference is None:
            preference = SocialPreference(guild_id=guild_id, user_id=user_id)
            session.add(preference)
            await session.commit()
        return preference
