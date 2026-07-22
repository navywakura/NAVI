from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks
from sqlalchemy import select

from bot.client import NaviBot
from bot.utils.context import format_timedelta, require_guild_module, safe_text, send_response
from bot.utils.timeparse import parse_duration
from database.connection import AsyncSessionLocal
from database.models import AfkStatus, Reminder


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class RemindersCog(commands.Cog):
    def __init__(self, bot: NaviBot) -> None:
        self.bot = bot
        self.dispatch_reminders.start()

    def cog_unload(self) -> None:
        self.dispatch_reminders.cancel()

    @tasks.loop(seconds=15)
    async def dispatch_reminders(self) -> None:
        now = utcnow()
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Reminder)
                .where(Reminder.delivered.is_(False), Reminder.due_at <= now)
                .order_by(Reminder.due_at.asc())
                .limit(100)
            )
            reminders = result.scalars().all()
            for reminder in reminders:
                guild = self.bot.get_guild(reminder.guild_id)
                channel = guild.get_channel(reminder.channel_id) if guild else None
                delivered = False
                if isinstance(channel, (discord.TextChannel, discord.Thread)):
                    try:
                        await channel.send(
                            f"⏰ <@{reminder.user_id}> **Recordatorio**\n{safe_text(reminder.content, 1800)}",
                            allowed_mentions=discord.AllowedMentions(users=True),
                        )
                        delivered = True
                    except discord.HTTPException:
                        pass
                if not delivered:
                    user = self.bot.get_user(reminder.user_id)
                    if user:
                        try:
                            await user.send(f"⏰ **Recordatorio de {guild.name if guild else 'N.A.V.I'}**\n{safe_text(reminder.content, 1800)}")
                            delivered = True
                        except discord.HTTPException:
                            pass
                # Avoid retry storms. A failed notification remains auditable but is marked handled.
                reminder.delivered = True
            if reminders:
                await session.commit()

    @dispatch_reminders.before_loop
    async def before_dispatch(self) -> None:
        await self.bot.wait_until_ready()

    @commands.hybrid_command(name="remind", description="Programa un recordatorio. Ejemplo: /remind 1h30m Revisar logs")
    async def remind(self, ctx: commands.Context, when: str, *, message: str) -> None:
        if not await require_guild_module(ctx, self.bot, "reminders"):
            return
        try:
            delta = parse_duration(when)
        except ValueError as exc:
            await send_response(ctx, str(exc), ephemeral=True)
            return
        due = utcnow() + delta
        async with AsyncSessionLocal() as session:
            reminder = Reminder(
                guild_id=ctx.guild.id,
                user_id=ctx.author.id,
                channel_id=ctx.channel.id,
                content=safe_text(message, 1800),
                due_at=due,
            )
            session.add(reminder)
            await session.commit()
        await send_response(
            ctx,
            f"Recordatorio `{reminder.reminder_id[:8]}` programado para <t:{int(due.timestamp())}:F> (<t:{int(due.timestamp())}:R>).",
            ephemeral=True,
        )

    @commands.hybrid_command(name="reminders", description="Lista tus recordatorios pendientes.")
    async def reminders(self, ctx: commands.Context) -> None:
        if not await require_guild_module(ctx, self.bot, "reminders"):
            return
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Reminder)
                .where(
                    Reminder.guild_id == ctx.guild.id,
                    Reminder.user_id == ctx.author.id,
                    Reminder.delivered.is_(False),
                )
                .order_by(Reminder.due_at.asc())
                .limit(20)
            )
            rows = result.scalars().all()
        if not rows:
            await send_response(ctx, "No tienes recordatorios pendientes.", ephemeral=True)
            return
        lines = [
            f"`{row.reminder_id[:8]}` · <t:{int(as_utc(row.due_at).timestamp())}:R> · {row.content[:80]}"
            for row in rows
        ]
        await send_response(ctx, "\n".join(lines), ephemeral=True)

    @commands.hybrid_command(name="remind-delete", description="Elimina un recordatorio por su ID corto o completo.")
    async def remind_delete(self, ctx: commands.Context, reminder_id: str) -> None:
        if not await require_guild_module(ctx, self.bot, "reminders"):
            return
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Reminder).where(
                    Reminder.guild_id == ctx.guild.id,
                    Reminder.user_id == ctx.author.id,
                    Reminder.reminder_id.startswith(reminder_id.lower()),
                    Reminder.delivered.is_(False),
                )
            )
            rows = result.scalars().all()
            if len(rows) != 1:
                await send_response(ctx, "ID inexistente o ambiguo.", ephemeral=True)
                return
            await session.delete(rows[0])
            await session.commit()
        await send_response(ctx, "Recordatorio eliminado.", ephemeral=True)

    @commands.hybrid_command(name="afk", description="Activa tu estado AFK.")
    async def afk(self, ctx: commands.Context, *, reason: str = "AFK") -> None:
        if not await require_guild_module(ctx, self.bot, "reminders"):
            return
        async with AsyncSessionLocal() as session:
            row = await session.get(AfkStatus, (ctx.guild.id, ctx.author.id))
            if row is None:
                row = AfkStatus(guild_id=ctx.guild.id, user_id=ctx.author.id)
                session.add(row)
            row.reason = safe_text(reason, 500)
            row.since = utcnow()
            await session.commit()
        await send_response(ctx, f"Estado AFK activado: **{row.reason}**")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        async with AsyncSessionLocal() as session:
            own = await session.get(AfkStatus, (message.guild.id, message.author.id))
            if own:
                elapsed = utcnow() - as_utc(own.since)
                await session.delete(own)
                await session.commit()
                try:
                    await message.reply(
                        f"AFK desactivado. Ausencia: **{format_timedelta(elapsed)}**.",
                        mention_author=False,
                        delete_after=10,
                    )
                except discord.HTTPException:
                    pass

            mentioned_ids = {member.id for member in message.mentions if member.id != message.author.id}
            if not mentioned_ids:
                return
            result = await session.execute(
                select(AfkStatus).where(
                    AfkStatus.guild_id == message.guild.id,
                    AfkStatus.user_id.in_(mentioned_ids),
                )
            )
            afk_rows = result.scalars().all()
        if afk_rows:
            lines = [
                f"<@{row.user_id}> está AFK: **{row.reason}** · {format_timedelta(utcnow() - as_utc(row.since))}"
                for row in afk_rows[:5]
            ]
            try:
                await message.reply("\n".join(lines), mention_author=False, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                pass


async def setup(bot: NaviBot) -> None:
    await bot.add_cog(RemindersCog(bot))
