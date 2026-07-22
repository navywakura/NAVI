from __future__ import annotations

import re

import discord
from discord.ext import commands
from sqlalchemy import func, select

from bot.client import NaviBot
from bot.utils.context import require_guild_module, safe_text, send_response
from database.connection import AsyncSessionLocal
from database.models import Tag

TAG_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
RESERVED = {"create", "show", "edit", "delete", "raw", "list", "search", "info", "claim"}


def normalize_name(name: str) -> str:
    return name.strip().lower()


def render_tag(content: str, ctx: commands.Context, arguments: str) -> str:
    values = arguments.split()
    replacements = {
        "{user}": ctx.author.display_name,
        "{username}": ctx.author.name,
        "{mention}": ctx.author.mention,
        "{server}": ctx.guild.name if ctx.guild else "Direct Message",
        "{channel}": getattr(ctx.channel, "mention", getattr(ctx.channel, "name", "channel")),
        "{member_count}": str(ctx.guild.member_count or len(ctx.guild.members)) if ctx.guild else "1",
        "{args}": arguments,
    }
    rendered = content
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    for index in range(1, 10):
        rendered = rendered.replace(f"{{{index}}}", values[index - 1] if index <= len(values) else "")
    return safe_text(rendered, 2000)


class TagsCog(commands.Cog):
    def __init__(self, bot: NaviBot) -> None:
        self.bot = bot

    async def _guard(self, ctx: commands.Context) -> bool:
        return await require_guild_module(ctx, self.bot, "tags")

    async def _find(self, session, guild_id: int, name: str) -> Tag | None:
        result = await session.execute(
            select(Tag).where(Tag.guild_id == guild_id, Tag.name == normalize_name(name))
        )
        return result.scalar_one_or_none()

    @commands.hybrid_group(name="tag", description="Sistema de respuestas locales por servidor.", invoke_without_command=True)
    async def tag(self, ctx: commands.Context) -> None:
        await send_response(ctx, "Subcomandos: create, show, edit, delete, raw, list, search, info, claim.", ephemeral=True)

    async def _show(self, ctx: commands.Context, name: str, arguments: str = "") -> None:
        if not await self._guard(ctx):
            return
        async with AsyncSessionLocal() as session:
            row = await self._find(session, ctx.guild.id, name)
            if row is None:
                await send_response(ctx, f"Tag `{normalize_name(name)}` inexistente.", ephemeral=True)
                return
            row.uses += 1
            await session.commit()
            output = render_tag(row.content, ctx, arguments)
        await send_response(ctx, output)

    @tag.command(name="create", description="Crea un tag local en este servidor.")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def tag_create(self, ctx: commands.Context, name: str, *, content: str) -> None:
        if not await self._guard(ctx):
            return
        normalized = normalize_name(name)
        if not TAG_NAME.fullmatch(normalized) or normalized in RESERVED:
            await send_response(ctx, "Nombre inválido. Usa 2-64 caracteres: letras minúsculas, números, `_` o `-`.", ephemeral=True)
            return
        if not content.strip() or len(content) > 2000:
            await send_response(ctx, "El contenido debe tener entre 1 y 2000 caracteres.", ephemeral=True)
            return
        async with AsyncSessionLocal() as session:
            if await self._find(session, ctx.guild.id, normalized):
                await send_response(ctx, "Ese tag ya existe.", ephemeral=True)
                return
            row = Tag(
                guild_id=ctx.guild.id,
                name=normalized,
                content=safe_text(content.strip(), 2000),
                owner_id=ctx.author.id,
            )
            session.add(row)
            await session.commit()
        await send_response(ctx, f"Tag `{normalized}` creado.")

    @tag.command(name="show", description="Muestra un tag y admite argumentos opcionales.")
    async def tag_show(self, ctx: commands.Context, name: str, *, arguments: str = "") -> None:
        await self._show(ctx, name, arguments)

    @tag.command(name="edit", description="Edita un tag que posees.")
    async def tag_edit(self, ctx: commands.Context, name: str, *, content: str) -> None:
        if not await self._guard(ctx):
            return
        async with AsyncSessionLocal() as session:
            row = await self._find(session, ctx.guild.id, name)
            if row is None:
                await send_response(ctx, "Tag inexistente.", ephemeral=True)
                return
            if row.owner_id != ctx.author.id and not ctx.author.guild_permissions.manage_messages:
                await send_response(ctx, "No eres propietario del tag.", ephemeral=True)
                return
            row.content = safe_text(content.strip(), 2000)
            await session.commit()
        await send_response(ctx, f"Tag `{row.name}` actualizado.")

    @tag.command(name="delete", description="Elimina un tag que posees.")
    async def tag_delete(self, ctx: commands.Context, name: str) -> None:
        if not await self._guard(ctx):
            return
        async with AsyncSessionLocal() as session:
            row = await self._find(session, ctx.guild.id, name)
            if row is None:
                await send_response(ctx, "Tag inexistente.", ephemeral=True)
                return
            if row.owner_id != ctx.author.id and not ctx.author.guild_permissions.manage_messages:
                await send_response(ctx, "No eres propietario del tag.", ephemeral=True)
                return
            normalized = row.name
            await session.delete(row)
            await session.commit()
        await send_response(ctx, f"Tag `{normalized}` eliminado.")

    @tag.command(name="raw", description="Muestra el contenido sin procesar de un tag.")
    async def tag_raw(self, ctx: commands.Context, name: str) -> None:
        if not await self._guard(ctx):
            return
        async with AsyncSessionLocal() as session:
            row = await self._find(session, ctx.guild.id, name)
        if row is None:
            await send_response(ctx, "Tag inexistente.", ephemeral=True)
            return
        escaped = row.content.replace("```", "`\u200b``")
        await send_response(ctx, f"```text\n{escaped[:1900]}\n```", ephemeral=True)

    @tag.command(name="list", description="Lista tags del servidor o de un propietario.")
    async def tag_list(self, ctx: commands.Context, owner: discord.Member | None = None) -> None:
        if not await self._guard(ctx):
            return
        query = select(Tag).where(Tag.guild_id == ctx.guild.id)
        if owner:
            query = query.where(Tag.owner_id == owner.id)
        query = query.order_by(Tag.uses.desc(), Tag.name.asc()).limit(50)
        async with AsyncSessionLocal() as session:
            result = await session.execute(query)
            rows = result.scalars().all()
        if not rows:
            await send_response(ctx, "No hay tags para ese filtro.", ephemeral=True)
            return
        await send_response(ctx, " · ".join(f"`{row.name}` ({row.uses})" for row in rows), ephemeral=True)

    @tag.command(name="search", description="Busca tags por nombre.")
    async def tag_search(self, ctx: commands.Context, query: str) -> None:
        if not await self._guard(ctx):
            return
        needle = normalize_name(query)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Tag)
                .where(Tag.guild_id == ctx.guild.id, func.lower(Tag.name).contains(needle))
                .order_by(Tag.uses.desc())
                .limit(25)
            )
            rows = result.scalars().all()
        await send_response(ctx, " · ".join(f"`{row.name}`" for row in rows) if rows else "Sin coincidencias.", ephemeral=True)

    @tag.command(name="info", description="Muestra metadatos de un tag.")
    async def tag_info(self, ctx: commands.Context, name: str) -> None:
        if not await self._guard(ctx):
            return
        async with AsyncSessionLocal() as session:
            row = await self._find(session, ctx.guild.id, name)
        if row is None:
            await send_response(ctx, "Tag inexistente.", ephemeral=True)
            return
        embed = discord.Embed(title=f"TAG // {row.name}", color=discord.Color.from_rgb(72, 209, 174))
        embed.add_field(name="Propietario", value=f"<@{row.owner_id}>")
        embed.add_field(name="Usos", value=str(row.uses))
        embed.add_field(name="Creado", value=f"<t:{int(row.created_at.timestamp())}:R>")
        embed.add_field(name="Actualizado", value=f"<t:{int(row.updated_at.timestamp())}:R>")
        embed.add_field(name="ID", value=f"`{row.tag_id}`", inline=False)
        await send_response(ctx, embed=embed, ephemeral=ctx.interaction is not None)

    @tag.command(name="claim", description="Reclama un tag huérfano cuyo propietario ya no está.")
    async def tag_claim(self, ctx: commands.Context, name: str) -> None:
        if not await self._guard(ctx):
            return
        async with AsyncSessionLocal() as session:
            row = await self._find(session, ctx.guild.id, name)
            if row is None:
                await send_response(ctx, "Tag inexistente.", ephemeral=True)
                return
            owner_present = ctx.guild.get_member(row.owner_id) is not None
            if owner_present and not ctx.author.guild_permissions.manage_messages:
                await send_response(ctx, "El propietario original sigue en el servidor.", ephemeral=True)
                return
            row.owner_id = ctx.author.id
            await session.commit()
        await send_response(ctx, f"Propiedad del tag `{row.name}` transferida a {ctx.author.mention}.")


async def setup(bot: NaviBot) -> None:
    await bot.add_cog(TagsCog(bot))
