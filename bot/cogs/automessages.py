from __future__ import annotations

from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks
from sqlalchemy import select

from bot.client import NaviBot
from database.connection import AsyncSessionLocal
from database.models import AutoMessage


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class AutoMessagesCog(commands.Cog):
    def __init__(self, bot: NaviBot) -> None:
        self.bot = bot
        self.dispatch_due_messages.start()

    def cog_unload(self) -> None:
        self.dispatch_due_messages.cancel()

    @tasks.loop(minutes=1)
    async def dispatch_due_messages(self) -> None:
        now = _utcnow()
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(AutoMessage)
                .where(AutoMessage.enabled.is_(True), AutoMessage.next_run_at <= now)
                .order_by(AutoMessage.next_run_at.asc())
                .limit(100)
            )
            jobs = result.scalars().all()

            for job in jobs:
                guild = self.bot.get_guild(job.guild_id)
                if guild is None or not await self.bot.module_enabled(job.guild_id, "automessages"):
                    job.next_run_at = now + timedelta(minutes=max(1, job.interval_minutes))
                    continue

                channel = guild.get_channel(job.channel_id)
                if isinstance(channel, discord.TextChannel):
                    try:
                        await channel.send(
                            job.content[:2000],
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                    except discord.HTTPException:
                        pass
                job.next_run_at = now + timedelta(minutes=max(1, job.interval_minutes))

            if jobs:
                await session.commit()

    @dispatch_due_messages.before_loop
    async def before_dispatch(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: NaviBot) -> None:
    await bot.add_cog(AutoMessagesCog(bot))
