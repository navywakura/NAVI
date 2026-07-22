from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.client import NaviBot
from bot.utils.context import require_guild_module, safe_text, send_response
from bot.utils.timeparse import parse_duration
from database.connection import AsyncSessionLocal
from database.models import WarningRecord


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ModerationCog(commands.Cog):
    def __init__(self, bot: NaviBot) -> None:
        self.bot = bot

    async def _guard(self, ctx: commands.Context, permission: str) -> bool:
        if not await require_guild_module(ctx, self.bot, "moderation"):
            return False
        perms = ctx.author.guild_permissions
        if not (perms.administrator or getattr(perms, permission, False)):
            await send_response(ctx, f"Permiso requerido: `{permission}`.", ephemeral=True)
            return False
        return True

    async def _can_target(self, ctx: commands.Context, target: discord.Member) -> bool:
        if target.id == ctx.guild.owner_id:
            await send_response(ctx, "No se puede actuar sobre el propietario del servidor.", ephemeral=True)
            return False
        if target.id == ctx.author.id:
            await send_response(ctx, "No puedes ejecutar esta acción sobre ti mismo/a.", ephemeral=True)
            return False
        if not ctx.author.guild_permissions.administrator and target.top_role >= ctx.author.top_role:
            await send_response(ctx, "Jerarquía insuficiente respecto al objetivo.", ephemeral=True)
            return False
        bot_member = ctx.guild.me
        if bot_member and target.top_role >= bot_member.top_role:
            await send_response(ctx, "El rol de N.A.V.I debe estar por encima del objetivo.", ephemeral=True)
            return False
        return True

    async def _modlog(self, ctx: commands.Context, action: str, target: str, reason: str, case_id: int | None = None) -> None:
        config = await self.bot.configs.get(ctx.guild.id, ctx.guild.name)
        if not config.modlog_channel_id:
            return
        channel = ctx.guild.get_channel(config.modlog_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        embed = discord.Embed(
            title=f"N.A.V.I // {action.upper()}",
            color=discord.Color.orange(),
            timestamp=utcnow(),
        )
        embed.add_field(name="Objetivo", value=target, inline=False)
        embed.add_field(name="Moderador", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
        embed.add_field(name="Razón", value=safe_text(reason, 1000), inline=False)
        if case_id is not None:
            embed.set_footer(text=f"Case #{case_id}")
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    @commands.hybrid_command(name="warn", description="Registra una advertencia para un miembro.")
    @app_commands.default_permissions(moderate_members=True)
    async def warn(self, ctx: commands.Context, user: discord.Member, *, reason: str = "Sin razón especificada") -> None:
        if not await self._guard(ctx, "moderate_members") or not await self._can_target(ctx, user):
            return
        async with AsyncSessionLocal() as session:
            record = WarningRecord(
                guild_id=ctx.guild.id,
                user_id=user.id,
                moderator_id=ctx.author.id,
                reason=safe_text(reason, 1800),
            )
            session.add(record)
            await session.commit()
        await self._modlog(ctx, "warn", f"{user} (`{user.id}`)", reason, record.warning_id)
        await send_response(ctx, f"Advertencia `#{record.warning_id}` registrada para {user.mention}.")

    @commands.hybrid_command(name="warnings", description="Lista las advertencias activas de un miembro.")
    @app_commands.default_permissions(moderate_members=True)
    async def warnings(self, ctx: commands.Context, user: discord.Member) -> None:
        if not await self._guard(ctx, "moderate_members"):
            return
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(WarningRecord)
                .where(
                    WarningRecord.guild_id == ctx.guild.id,
                    WarningRecord.user_id == user.id,
                    WarningRecord.active.is_(True),
                )
                .order_by(WarningRecord.created_at.desc())
                .limit(20)
            )
            rows = result.scalars().all()
        if not rows:
            await send_response(ctx, f"{user.mention} no tiene advertencias activas.", ephemeral=True)
            return
        lines = [f"`#{row.warning_id}` <t:{int(row.created_at.timestamp())}:d> · {row.reason[:120]} · <@{row.moderator_id}>" for row in rows]
        await send_response(ctx, "\n".join(lines), ephemeral=True)

    @commands.hybrid_command(name="unwarn", description="Retira una advertencia por Case ID.")
    @app_commands.default_permissions(moderate_members=True)
    async def unwarn(self, ctx: commands.Context, warning_id: int) -> None:
        if not await self._guard(ctx, "moderate_members"):
            return
        async with AsyncSessionLocal() as session:
            row = await session.get(WarningRecord, warning_id)
            if row is None or row.guild_id != ctx.guild.id or not row.active:
                await send_response(ctx, "Advertencia inexistente o ya retirada.", ephemeral=True)
                return
            row.active = False
            row.removed_at = utcnow()
            row.removed_by_id = ctx.author.id
            await session.commit()
        await self._modlog(ctx, "unwarn", f"User {row.user_id}", f"Retirada de advertencia #{warning_id}", warning_id)
        await send_response(ctx, f"Advertencia `#{warning_id}` retirada.")

    @commands.hybrid_command(name="timeout", description="Aísla temporalmente a un miembro. Ejemplo: 10m, 2h, 1d.")
    @app_commands.default_permissions(moderate_members=True)
    async def timeout(self, ctx: commands.Context, user: discord.Member, duration: str, *, reason: str = "Sin razón especificada") -> None:
        if not await self._guard(ctx, "moderate_members") or not await self._can_target(ctx, user):
            return
        try:
            delta = parse_duration(duration)
        except ValueError as exc:
            await send_response(ctx, str(exc), ephemeral=True)
            return
        if delta.days > 28:
            await send_response(ctx, "Discord limita los timeouts a 28 días.", ephemeral=True)
            return
        try:
            await user.timeout(delta, reason=f"{ctx.author}: {reason}")
        except discord.Forbidden:
            await send_response(ctx, "Discord rechazó la operación por jerarquía o permisos.", ephemeral=True)
            return
        await self._modlog(ctx, "timeout", f"{user} (`{user.id}`)", f"{reason} · {duration}")
        await send_response(ctx, f"{user.mention} aislado durante **{duration}**.")

    @commands.hybrid_command(name="untimeout", description="Retira el timeout de un miembro.")
    @app_commands.default_permissions(moderate_members=True)
    async def untimeout(self, ctx: commands.Context, user: discord.Member, *, reason: str = "Timeout retirado") -> None:
        if not await self._guard(ctx, "moderate_members") or not await self._can_target(ctx, user):
            return
        await user.timeout(None, reason=f"{ctx.author}: {reason}")
        await self._modlog(ctx, "untimeout", f"{user} (`{user.id}`)", reason)
        await send_response(ctx, f"Timeout retirado para {user.mention}.")

    @commands.hybrid_command(name="kick", description="Expulsa a un miembro.")
    @app_commands.default_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, user: discord.Member, *, reason: str = "Sin razón especificada") -> None:
        if not await self._guard(ctx, "kick_members") or not await self._can_target(ctx, user):
            return
        await user.kick(reason=f"{ctx.author}: {reason}")
        await self._modlog(ctx, "kick", f"{user} (`{user.id}`)", reason)
        await send_response(ctx, f"{user} expulsado.")

    @commands.hybrid_command(name="ban", description="Bloquea a un miembro del servidor.")
    @app_commands.default_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, user: discord.Member, delete_days: int = 0, *, reason: str = "Sin razón especificada") -> None:
        if not await self._guard(ctx, "ban_members") or not await self._can_target(ctx, user):
            return
        delete_seconds = max(0, min(7, delete_days)) * 86400
        await ctx.guild.ban(user, reason=f"{ctx.author}: {reason}", delete_message_seconds=delete_seconds)
        await self._modlog(ctx, "ban", f"{user} (`{user.id}`)", reason)
        await send_response(ctx, f"{user} bloqueado del servidor.")

    @commands.hybrid_command(name="unban", description="Retira un ban usando el ID del usuario.")
    @app_commands.default_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user_id: str, *, reason: str = "Ban retirado") -> None:
        if not await self._guard(ctx, "ban_members"):
            return
        try:
            target_id = int(user_id.strip())
            user = await self.bot.fetch_user(target_id)
            await ctx.guild.unban(user, reason=f"{ctx.author}: {reason}")
        except (ValueError, discord.NotFound):
            await send_response(ctx, "ID inválido o usuario no bloqueado.", ephemeral=True)
            return
        await self._modlog(ctx, "unban", f"{user} (`{user.id}`)", reason)
        await send_response(ctx, f"Ban retirado para {user}.")

    @commands.hybrid_command(name="purge", description="Elimina mensajes recientes del canal.")
    @app_commands.default_permissions(manage_messages=True)
    async def purge(self, ctx: commands.Context, amount: int, user: discord.Member | None = None) -> None:
        if not await self._guard(ctx, "manage_messages"):
            return
        if not isinstance(ctx.channel, discord.TextChannel):
            await send_response(ctx, "Canal no compatible.", ephemeral=True)
            return
        amount = max(1, min(200, amount))
        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)
        check = (lambda message: message.author.id == user.id) if user else None
        deleted = await ctx.channel.purge(limit=amount, check=check, reason=f"Purge by {ctx.author}")
        await send_response(ctx, f"Mensajes eliminados: **{len(deleted)}**.", ephemeral=True)

    @commands.hybrid_command(name="slowmode", description="Configura el modo lento del canal en segundos.")
    @app_commands.default_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, seconds: int) -> None:
        if not await self._guard(ctx, "manage_channels"):
            return
        if not isinstance(ctx.channel, discord.TextChannel):
            await send_response(ctx, "Canal no compatible.", ephemeral=True)
            return
        seconds = max(0, min(21600, seconds))
        await ctx.channel.edit(slowmode_delay=seconds, reason=f"Slowmode by {ctx.author}")
        await send_response(ctx, f"Slowmode configurado a **{seconds}s**.")

    @commands.hybrid_command(name="lock", description="Bloquea el envío de mensajes en un canal.")
    @app_commands.default_permissions(manage_channels=True)
    async def lock(self, ctx: commands.Context, channel: discord.TextChannel | None = None) -> None:
        if not await self._guard(ctx, "manage_channels"):
            return
        target = channel or ctx.channel
        if not isinstance(target, discord.TextChannel):
            await send_response(ctx, "Canal no compatible.", ephemeral=True)
            return
        overwrite = target.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await target.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Lock by {ctx.author}")
        await send_response(ctx, f"🔒 {target.mention} bloqueado.")

    @commands.hybrid_command(name="unlock", description="Desbloquea el envío de mensajes en un canal.")
    @app_commands.default_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context, channel: discord.TextChannel | None = None) -> None:
        if not await self._guard(ctx, "manage_channels"):
            return
        target = channel or ctx.channel
        if not isinstance(target, discord.TextChannel):
            await send_response(ctx, "Canal no compatible.", ephemeral=True)
            return
        overwrite = target.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await target.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Unlock by {ctx.author}")
        await send_response(ctx, f"🔓 {target.mention} desbloqueado.")

    @commands.hybrid_command(name="nickname", description="Cambia o elimina el apodo de un miembro.")
    @app_commands.default_permissions(manage_nicknames=True)
    async def nickname(self, ctx: commands.Context, user: discord.Member, *, nickname: str | None = None) -> None:
        if not await self._guard(ctx, "manage_nicknames") or not await self._can_target(ctx, user):
            return
        await user.edit(nick=nickname[:32] if nickname else None, reason=f"Nickname by {ctx.author}")
        await send_response(ctx, f"Apodo actualizado para {user.mention}.")


async def setup(bot: NaviBot) -> None:
    await bot.add_cog(ModerationCog(bot))
