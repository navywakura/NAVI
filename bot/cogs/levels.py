from __future__ import annotations

import random
from collections import defaultdict
from time import monotonic

import discord
from discord.ext import commands, tasks
from sqlalchemy import select

from bot.client import NaviBot
from database.connection import AsyncSessionLocal
from database.models import LevelRole, MemberLevel


def level_for_xp(xp: int) -> int:
    return int((max(0, xp) / 100) ** 0.5)


async def _member_level(session, guild_id: int, user_id: int) -> MemberLevel:
    record = await session.get(MemberLevel, (guild_id, user_id))
    if record is None:
        record = MemberLevel(guild_id=guild_id, user_id=user_id)
        session.add(record)
        await session.flush()
    return record


class LevelsCog(commands.Cog):
    def __init__(self, bot: NaviBot) -> None:
        self.bot = bot
        self.message_cooldowns: dict[tuple[int, int], float] = {}
        self.voice_xp_tick.start()

    def cog_unload(self) -> None:
        self.voice_xp_tick.cancel()

    async def _grant_xp(self, member: discord.Member, amount: int) -> tuple[int, int]:
        async with AsyncSessionLocal() as session:
            record = await _member_level(session, member.guild.id, member.id)
            old_level = record.level
            record.xp += amount
            record.level = level_for_xp(record.xp)
            new_level = record.level
            await session.commit()

            if new_level > old_level:
                result = await session.execute(
                    select(LevelRole)
                    .where(
                        LevelRole.guild_id == member.guild.id,
                        LevelRole.level <= new_level,
                    )
                    .order_by(LevelRole.level.asc())
                )
                rewards = result.scalars().all()
                for reward in rewards:
                    role = member.guild.get_role(reward.role_id)
                    if role and role not in member.roles:
                        try:
                            await member.add_roles(role, reason="N.A.V.I level reward")
                        except discord.Forbidden:
                            pass
            return old_level, new_level

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot or not isinstance(message.author, discord.Member):
            return
        if not await self.bot.module_enabled(message.guild.id, "levels"):
            return
        config = await self.bot.configs.get(message.guild.id, message.guild.name)
        key = (message.guild.id, message.author.id)
        now = monotonic()
        if now < self.message_cooldowns.get(key, 0):
            return
        self.message_cooldowns[key] = now + config.xp_cooldown_seconds
        old_level, new_level = await self._grant_xp(
            message.author, random.randint(config.xp_min, config.xp_max)
        )
        if new_level > old_level:
            await message.channel.send(
                f"{message.author.mention} alcanzó el nivel **{new_level}**.",
                allowed_mentions=discord.AllowedMentions(users=True),
            )

    @tasks.loop(minutes=1)
    async def voice_xp_tick(self) -> None:
        for guild in self.bot.guilds:
            if not await self.bot.module_enabled(guild.id, "levels"):
                continue
            config = await self.bot.configs.get(guild.id, guild.name)
            if config.voice_xp_per_minute <= 0:
                continue
            members: set[discord.Member] = set()
            for channel in guild.voice_channels:
                for member in channel.members:
                    if not member.bot and member.voice and not member.voice.self_deaf:
                        members.add(member)
            for member in members:
                await self._grant_xp(member, config.voice_xp_per_minute)

    @voice_xp_tick.before_loop
    async def before_voice_xp(self) -> None:
        await self.bot.wait_until_ready()

    @commands.hybrid_command(name="leaderboard", description="Muestra el ranking de experiencia del servidor.")
    async def leaderboard(self, ctx: commands.Context):
        if ctx.guild is None:
            await ctx.reply("Comando disponible solo en servidores.", mention_author=False)
            return
        if not await self.bot.module_enabled(ctx.guild.id, "levels"):
            await ctx.reply("Módulo de niveles desactivado.", mention_author=False)
            return

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(MemberLevel)
                .where(MemberLevel.guild_id == ctx.guild.id)
                .order_by(MemberLevel.xp.desc())
                .limit(10)
            )
            rows = result.scalars().all()

        if not rows:
            await ctx.reply("Sin datos de experiencia todavía.", mention_author=False)
            return
        lines = []
        for position, row in enumerate(rows, start=1):
            member = ctx.guild.get_member(row.user_id)
            name = member.display_name if member else f"User {row.user_id}"
            lines.append(f"`{position:02}` **{name}** — nivel {row.level} · {row.xp:,} XP")
        await ctx.reply("\n".join(lines), mention_author=False)


async def setup(bot: NaviBot) -> None:
    await bot.add_cog(LevelsCog(bot))
