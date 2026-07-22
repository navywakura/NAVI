from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from time import monotonic

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import and_, or_, select

from bot.client import NaviBot
from bot.utils.context import require_guild_module, safe_text, send_response
from bot.utils.social import get_preference, is_blocked
from database.connection import AsyncSessionLocal
from database.models import (
    Confession,
    Marriage,
    MarriageProposal,
    SocialBlock,
    SocialPreference,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def active_marriage(session, guild_id: int, user_id: int) -> Marriage | None:
    result = await session.execute(
        select(Marriage).where(
            Marriage.guild_id == guild_id,
            Marriage.active.is_(True),
            or_(Marriage.user_a_id == user_id, Marriage.user_b_id == user_id),
        )
    )
    return result.scalar_one_or_none()


class SocialSettingsView(discord.ui.View):
    def __init__(self, guild_id: int, user_id: int, preference: SocialPreference) -> None:
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.user_id = user_id
        self.interactions_enabled = preference.interactions_enabled
        self.letters_enabled = preference.letters_enabled
        self.confessions_enabled = preference.confessions_enabled
        self._refresh()

    def _refresh(self) -> None:
        self.interactions.label = f"Interacciones: {'ON' if self.interactions_enabled else 'OFF'}"
        self.letters.label = f"Cartas: {'ON' if self.letters_enabled else 'OFF'}"
        self.confessions.label = f"Confesiones: {'ON' if self.confessions_enabled else 'OFF'}"
        self.interactions.style = discord.ButtonStyle.success if self.interactions_enabled else discord.ButtonStyle.danger
        self.letters.style = discord.ButtonStyle.success if self.letters_enabled else discord.ButtonStyle.danger
        self.confessions.style = discord.ButtonStyle.success if self.confessions_enabled else discord.ButtonStyle.danger

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Este panel pertenece a otro operador.", ephemeral=True)
            return False
        return True

    async def _save(self) -> None:
        async with AsyncSessionLocal() as session:
            row = await session.get(SocialPreference, (self.guild_id, self.user_id))
            if row is None:
                row = SocialPreference(guild_id=self.guild_id, user_id=self.user_id)
                session.add(row)
            row.interactions_enabled = self.interactions_enabled
            row.letters_enabled = self.letters_enabled
            row.confessions_enabled = self.confessions_enabled
            await session.commit()

    @discord.ui.button(label="Interacciones", style=discord.ButtonStyle.secondary)
    async def interactions(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        self.interactions_enabled = not self.interactions_enabled
        self._refresh()
        await self._save()
        await interaction.response.edit_message(content="Preferencias sociales actualizadas.", view=self)

    @discord.ui.button(label="Cartas", style=discord.ButtonStyle.secondary)
    async def letters(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        self.letters_enabled = not self.letters_enabled
        self._refresh()
        await self._save()
        await interaction.response.edit_message(content="Preferencias sociales actualizadas.", view=self)

    @discord.ui.button(label="Confesiones", style=discord.ButtonStyle.secondary)
    async def confessions(self, interaction: discord.Interaction, _button: discord.ui.Button) -> None:
        self.confessions_enabled = not self.confessions_enabled
        self._refresh()
        await self._save()
        await interaction.response.edit_message(content="Preferencias sociales actualizadas.", view=self)


class SocialCog(commands.Cog):
    social_app = app_commands.Group(name="social", description="Controles personales de interacción.")
    social_block_app = app_commands.Group(name="block", description="Gestiona bloqueos sociales.", parent=social_app)

    def __init__(self, bot: NaviBot) -> None:
        self.bot = bot
        self._cooldowns: dict[tuple[int, int], float] = {}

    async def _cooldown_allowed(self, guild_id: int, user_id: int, guild_name: str | None = None) -> tuple[bool, float]:
        config = await self.bot.configs.get(guild_id, guild_name)
        key = (guild_id, user_id)
        now = monotonic()
        retry_at = self._cooldowns.get(key, 0.0)
        if retry_at > now:
            return False, retry_at - now
        self._cooldowns[key] = now + config.social_cooldown_seconds
        return True, 0.0

    async def _guard(self, ctx: commands.Context) -> bool:
        if not await require_guild_module(ctx, self.bot, "social"):
            return False
        allowed, retry_after = await self._cooldown_allowed(ctx.guild.id, ctx.author.id, ctx.guild.name)
        if not allowed:
            await send_response(ctx, f"Canal social en cooldown. Reintenta en {retry_after:.1f}s.", ephemeral=True)
            return False
        return True

    @commands.hybrid_command(name="ship", description="Calcula compatibilidad determinista entre dos usuarios.")
    async def ship(self, ctx: commands.Context, user1: discord.Member, user2: discord.Member) -> None:
        if not await self._guard(ctx):
            return
        low, high = sorted((user1.id, user2.id))
        digest = hashlib.sha256(f"{ctx.guild.id}:{low}:{high}:ship".encode()).hexdigest()
        score = int(digest[:8], 16) % 101
        filled = round(score / 10)
        bar = "█" * filled + "░" * (10 - filled)
        await send_response(ctx, f"💞 {user1.mention} × {user2.mention}\n`[{bar}]` **{score}%**")

    @commands.hybrid_command(name="confess", description="Publica una confesión en el canal configurado.")
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def confess(self, ctx: commands.Context, *, message: str) -> None:
        if not await self._guard(ctx):
            return
        config = await self.bot.configs.get(ctx.guild.id, ctx.guild.name)
        preference = await get_preference(ctx.guild.id, ctx.author.id)
        if not preference.confessions_enabled:
            await send_response(ctx, "Has desactivado las confesiones en `/social settings`.", ephemeral=True)
            return
        if not config.confessions_enabled or not config.confession_channel_id:
            await send_response(ctx, "Las confesiones no están configuradas en el dashboard.", ephemeral=True)
            return
        channel = ctx.guild.get_channel(config.confession_channel_id)
        if not isinstance(channel, discord.TextChannel):
            await send_response(ctx, "Canal de confesiones no disponible.", ephemeral=True)
            return
        content = safe_text(message.strip(), 1800)
        async with AsyncSessionLocal() as session:
            record = Confession(
                guild_id=ctx.guild.id,
                author_id=ctx.author.id,
                content=content,
                anonymous=config.anonymous_confessions,
            )
            session.add(record)
            await session.commit()
        embed = discord.Embed(
            title="N.A.V.I // CONFESSION",
            description=content,
            color=discord.Color.from_rgb(120, 92, 180),
            timestamp=utcnow(),
        )
        if not config.anonymous_confessions:
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        else:
            embed.set_footer(text=f"Registro anónimo #{record.confession_id[:8]}")
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        await send_response(ctx, "Confesión transmitida.", ephemeral=True)

    @commands.hybrid_command(name="letter", description="Envía una carta privada a otro miembro.")
    @commands.cooldown(1, 20, commands.BucketType.user)
    async def letter(self, ctx: commands.Context, user: discord.Member, *, message: str) -> None:
        if not await self._guard(ctx):
            return
        if user.bot or user.id == ctx.author.id:
            await send_response(ctx, "Destinatario inválido.", ephemeral=True)
            return
        if await is_blocked(ctx.guild.id, ctx.author.id, user.id):
            await send_response(ctx, "Canal social bloqueado entre ambos operadores.", ephemeral=True)
            return
        preference = await get_preference(ctx.guild.id, user.id)
        if not preference.letters_enabled:
            await send_response(ctx, "El destinatario no acepta cartas.", ephemeral=True)
            return
        embed = discord.Embed(
            title=f"Carta desde {ctx.guild.name}",
            description=safe_text(message, 1800),
            color=discord.Color.from_rgb(72, 209, 174),
        )
        embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.display_avatar.url)
        try:
            await user.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.Forbidden:
            await send_response(ctx, "No se pudo abrir un canal privado con el destinatario.", ephemeral=True)
            return
        await send_response(ctx, f"Carta entregada a {user.mention}.", ephemeral=True)

    async def _app_guard(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not await self.bot.module_enabled(interaction.guild.id, "social"):
            await interaction.response.send_message("Módulo social no disponible.", ephemeral=True)
            return False
        allowed, retry_after = await self._cooldown_allowed(
            interaction.guild.id, interaction.user.id, interaction.guild.name
        )
        if not allowed:
            await interaction.response.send_message(
                f"Canal social en cooldown. Reintenta en {retry_after:.1f}s.", ephemeral=True
            )
            return False
        return True

    async def _block_add_db(self, guild_id: int, actor_id: int, user: discord.Member) -> str:
        if user.id == actor_id or user.bot:
            raise ValueError("Usuario inválido.")
        async with AsyncSessionLocal() as session:
            row = await session.get(SocialBlock, (guild_id, actor_id, user.id))
            if row is None:
                session.add(SocialBlock(guild_id=guild_id, user_id=actor_id, blocked_user_id=user.id))
                await session.commit()
        return f"{user.mention} añadido a tu lista de bloqueo social."

    async def _block_remove_db(self, guild_id: int, actor_id: int, user: discord.Member) -> str:
        async with AsyncSessionLocal() as session:
            row = await session.get(SocialBlock, (guild_id, actor_id, user.id))
            if row:
                await session.delete(row)
                await session.commit()
        return f"Bloqueo retirado para {user.mention}."

    async def _block_list_db(self, guild_id: int, actor_id: int) -> str:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SocialBlock).where(
                    SocialBlock.guild_id == guild_id,
                    SocialBlock.user_id == actor_id,
                )
            )
            rows = result.scalars().all()
        return "\n".join(f"• <@{row.blocked_user_id}>" for row in rows) if rows else "Lista de bloqueo vacía."

    # Prefix counterpart for the exact slash hierarchy: /social block add|remove|list.
    @commands.group(name="social", invoke_without_command=True)
    async def social_prefix(self, ctx: commands.Context) -> None:
        await send_response(ctx, "Subcomandos: `social block add/remove/list` y `social settings`.", ephemeral=True)

    @social_prefix.group(name="block", invoke_without_command=True)
    async def social_block_prefix(self, ctx: commands.Context) -> None:
        await send_response(ctx, "Usa `add`, `remove` o `list`.", ephemeral=True)

    @social_block_prefix.command(name="add")
    async def block_add_prefix(self, ctx: commands.Context, user: discord.Member) -> None:
        if not await self._guard(ctx):
            return
        try:
            result = await self._block_add_db(ctx.guild.id, ctx.author.id, user)
        except ValueError as exc:
            await send_response(ctx, str(exc), ephemeral=True)
            return
        await send_response(ctx, result, ephemeral=True)

    @social_block_prefix.command(name="remove")
    async def block_remove_prefix(self, ctx: commands.Context, user: discord.Member) -> None:
        if await self._guard(ctx):
            await send_response(ctx, await self._block_remove_db(ctx.guild.id, ctx.author.id, user), ephemeral=True)

    @social_block_prefix.command(name="list")
    async def block_list_prefix(self, ctx: commands.Context) -> None:
        if await self._guard(ctx):
            await send_response(ctx, await self._block_list_db(ctx.guild.id, ctx.author.id), ephemeral=True)

    @social_prefix.command(name="settings")
    async def social_settings_prefix(self, ctx: commands.Context) -> None:
        if not await self._guard(ctx):
            return
        preference = await get_preference(ctx.guild.id, ctx.author.id)
        await send_response(ctx, "Controla qué tipos de comunicación aceptas en este servidor.", view=SocialSettingsView(ctx.guild.id, ctx.author.id, preference), ephemeral=True)

    @social_block_app.command(name="add", description="Bloquea interacciones de un usuario.")
    async def block_add_slash(self, interaction: discord.Interaction, user: discord.Member) -> None:
        if not await self._app_guard(interaction):
            return
        try:
            result = await self._block_add_db(interaction.guild.id, interaction.user.id, user)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message(result, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @social_block_app.command(name="remove", description="Retira un bloqueo social.")
    async def block_remove_slash(self, interaction: discord.Interaction, user: discord.Member) -> None:
        if await self._app_guard(interaction):
            result = await self._block_remove_db(interaction.guild.id, interaction.user.id, user)
            await interaction.response.send_message(result, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @social_block_app.command(name="list", description="Muestra tu lista de bloqueo social.")
    async def block_list_slash(self, interaction: discord.Interaction) -> None:
        if await self._app_guard(interaction):
            result = await self._block_list_db(interaction.guild.id, interaction.user.id)
            await interaction.response.send_message(result, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @social_app.command(name="settings", description="Abre tus preferencias sociales.")
    async def social_settings_slash(self, interaction: discord.Interaction) -> None:
        if not await self._app_guard(interaction):
            return
        preference = await get_preference(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            "Controla qué tipos de comunicación aceptas en este servidor.",
            view=SocialSettingsView(interaction.guild.id, interaction.user.id, preference),
            ephemeral=True,
        )

    @commands.hybrid_group(name="marriage", description="Sistema social de parejas del servidor.", invoke_without_command=True)
    async def marriage(self, ctx: commands.Context) -> None:
        await send_response(ctx, "Subcomandos: propose, accept, decline, proposals, status, divorce, leaderboard.", ephemeral=True)

    @marriage.command(name="propose", description="Envía una propuesta de matrimonio social.")
    async def marriage_propose(self, ctx: commands.Context, user: discord.Member) -> None:
        if not await self._guard(ctx):
            return
        if user.bot or user.id == ctx.author.id or await is_blocked(ctx.guild.id, ctx.author.id, user.id):
            await send_response(ctx, "No se puede crear esa propuesta.", ephemeral=True)
            return
        async with AsyncSessionLocal() as session:
            if await active_marriage(session, ctx.guild.id, ctx.author.id) or await active_marriage(session, ctx.guild.id, user.id):
                await send_response(ctx, "Uno de los usuarios ya tiene una relación activa.", ephemeral=True)
                return
            result = await session.execute(
                select(MarriageProposal).where(
                    MarriageProposal.guild_id == ctx.guild.id,
                    MarriageProposal.proposer_id == ctx.author.id,
                    MarriageProposal.target_id == user.id,
                    MarriageProposal.status == "pending",
                )
            )
            if result.scalar_one_or_none():
                await send_response(ctx, "Ya existe una propuesta pendiente.", ephemeral=True)
                return
            session.add(MarriageProposal(guild_id=ctx.guild.id, proposer_id=ctx.author.id, target_id=user.id))
            await session.commit()
        await send_response(ctx, f"💍 {user.mention}, has recibido una propuesta de {ctx.author.mention}. Usa `/marriage accept` o `/marriage decline`.")

    @marriage.command(name="accept", description="Acepta tu propuesta pendiente más reciente.")
    async def marriage_accept(self, ctx: commands.Context) -> None:
        if not await self._guard(ctx):
            return
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(MarriageProposal)
                .where(
                    MarriageProposal.guild_id == ctx.guild.id,
                    MarriageProposal.target_id == ctx.author.id,
                    MarriageProposal.status == "pending",
                )
                .order_by(MarriageProposal.created_at.desc())
                .limit(1)
            )
            proposal = result.scalar_one_or_none()
            if proposal is None:
                await send_response(ctx, "No hay propuestas pendientes.", ephemeral=True)
                return
            if await active_marriage(session, ctx.guild.id, proposal.proposer_id) or await active_marriage(session, ctx.guild.id, ctx.author.id):
                proposal.status = "expired"
                proposal.resolved_at = utcnow()
                await session.commit()
                await send_response(ctx, "La propuesta ya no es válida.", ephemeral=True)
                return
            low, high = sorted((proposal.proposer_id, proposal.target_id))
            pair_result = await session.execute(
                select(Marriage).where(
                    Marriage.guild_id == ctx.guild.id,
                    Marriage.user_a_id == low,
                    Marriage.user_b_id == high,
                )
            )
            marriage = pair_result.scalar_one_or_none()
            if marriage is None:
                marriage = Marriage(guild_id=ctx.guild.id, user_a_id=low, user_b_id=high)
                session.add(marriage)
            else:
                marriage.active = True
                marriage.accepted_at = utcnow()
                marriage.divorced_at = None
            proposal.status = "accepted"
            proposal.resolved_at = utcnow()
            await session.commit()
        await send_response(ctx, f"💍 Relación activada entre <@{proposal.proposer_id}> y {ctx.author.mention}.")

    @marriage.command(name="decline", description="Rechaza tu propuesta pendiente más reciente.")
    async def marriage_decline(self, ctx: commands.Context) -> None:
        if not await self._guard(ctx):
            return
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(MarriageProposal)
                .where(
                    MarriageProposal.guild_id == ctx.guild.id,
                    MarriageProposal.target_id == ctx.author.id,
                    MarriageProposal.status == "pending",
                )
                .order_by(MarriageProposal.created_at.desc())
                .limit(1)
            )
            proposal = result.scalar_one_or_none()
            if proposal is None:
                await send_response(ctx, "No hay propuestas pendientes.", ephemeral=True)
                return
            proposal.status = "declined"
            proposal.resolved_at = utcnow()
            await session.commit()
        await send_response(ctx, "Propuesta rechazada.", ephemeral=True)

    @marriage.command(name="proposals", description="Lista tus propuestas recibidas pendientes.")
    async def marriage_proposals(self, ctx: commands.Context) -> None:
        if not await self._guard(ctx):
            return
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(MarriageProposal)
                .where(
                    MarriageProposal.guild_id == ctx.guild.id,
                    MarriageProposal.target_id == ctx.author.id,
                    MarriageProposal.status == "pending",
                )
                .order_by(MarriageProposal.created_at.desc())
                .limit(10)
            )
            rows = result.scalars().all()
        await send_response(ctx, "\n".join(f"• <@{row.proposer_id}> · `{row.proposal_id[:8]}`" for row in rows) if rows else "No hay propuestas pendientes.", ephemeral=True)

    @marriage.command(name="status", description="Consulta el estado matrimonial de un usuario.")
    async def marriage_status(self, ctx: commands.Context, user: discord.Member | None = None) -> None:
        if not await self._guard(ctx):
            return
        target = user or ctx.author
        async with AsyncSessionLocal() as session:
            row = await active_marriage(session, ctx.guild.id, target.id)
        if row is None:
            await send_response(ctx, f"{target.mention} no tiene una relación activa.")
            return
        partner = row.user_b_id if row.user_a_id == target.id else row.user_a_id
        await send_response(ctx, f"💍 {target.mention} está vinculado con <@{partner}> desde <t:{int(row.accepted_at.timestamp())}:D>.")

    @marriage.command(name="divorce", description="Finaliza tu relación social activa.")
    async def marriage_divorce(self, ctx: commands.Context) -> None:
        if not await self._guard(ctx):
            return
        async with AsyncSessionLocal() as session:
            row = await active_marriage(session, ctx.guild.id, ctx.author.id)
            if row is None:
                await send_response(ctx, "No tienes una relación activa.", ephemeral=True)
                return
            partner = row.user_b_id if row.user_a_id == ctx.author.id else row.user_a_id
            row.active = False
            row.divorced_at = utcnow()
            await session.commit()
        await send_response(ctx, f"Vínculo con <@{partner}> finalizado.")

    @marriage.command(name="leaderboard", description="Muestra las relaciones activas más antiguas.")
    async def marriage_leaderboard(self, ctx: commands.Context) -> None:
        if not await self._guard(ctx):
            return
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Marriage)
                .where(Marriage.guild_id == ctx.guild.id, Marriage.active.is_(True))
                .order_by(Marriage.accepted_at.asc())
                .limit(10)
            )
            rows = result.scalars().all()
        if not rows:
            await send_response(ctx, "No hay relaciones activas.")
            return
        lines = [f"`{i:02}` <@{row.user_a_id}> × <@{row.user_b_id}> · <t:{int(row.accepted_at.timestamp())}:R>" for i, row in enumerate(rows, 1)]
        await send_response(ctx, "\n".join(lines))


async def setup(bot: NaviBot) -> None:
    await bot.add_cog(SocialCog(bot))
