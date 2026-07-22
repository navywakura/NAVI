from __future__ import annotations

from datetime import timedelta
from typing import Any

import discord
from discord.ext import commands

from bot.client import NaviBot


async def send_response(
    ctx: commands.Context,
    content: str | None = None,
    *,
    embed: discord.Embed | None = None,
    embeds: list[discord.Embed] | None = None,
    file: discord.File | None = None,
    files: list[discord.File] | None = None,
    view: discord.ui.View | None = None,
    ephemeral: bool = False,
    allowed_mentions: discord.AllowedMentions | None = None,
) -> discord.Message | None:
    """Reply correctly from either a prefix or slash invocation of a hybrid command."""

    allowed_mentions = allowed_mentions or discord.AllowedMentions.none()
    if ctx.interaction is not None:
        kwargs: dict[str, Any] = {
            "content": content,
            "embed": embed,
            "embeds": embeds,
            "file": file,
            "files": files,
            "view": view,
            "ephemeral": ephemeral,
            "allowed_mentions": allowed_mentions,
        }
        kwargs = {key: value for key, value in kwargs.items() if value is not None}
        if ctx.interaction.response.is_done():
            return await ctx.interaction.followup.send(wait=True, **kwargs)
        await ctx.interaction.response.send_message(**kwargs)
        try:
            return await ctx.interaction.original_response()
        except discord.HTTPException:
            return None

    return await ctx.send(
        content=content,
        embed=embed,
        embeds=embeds,
        file=file,
        files=files,
        view=view,
        allowed_mentions=allowed_mentions,
    )


async def defer(ctx: commands.Context, *, ephemeral: bool = False) -> None:
    if ctx.interaction is not None and not ctx.interaction.response.is_done():
        await ctx.interaction.response.defer(ephemeral=ephemeral, thinking=True)


async def require_guild_module(
    ctx: commands.Context,
    bot: NaviBot,
    module: str,
    *,
    admin_only: bool = False,
) -> bool:
    if ctx.guild is None:
        await send_response(ctx, "Comando disponible solo dentro de un servidor.", ephemeral=True)
        return False
    if not await bot.module_enabled(ctx.guild.id, module):
        await send_response(ctx, f"Módulo `{module}` desactivado en este servidor.", ephemeral=True)
        return False
    if admin_only and not ctx.author.guild_permissions.manage_guild:
        await send_response(ctx, "Permiso requerido: `Gestionar servidor`.", ephemeral=True)
        return False
    return True


def format_timedelta(value: timedelta) -> str:
    total = max(0, int(value.total_seconds()))
    days, total = divmod(total, 86400)
    hours, total = divmod(total, 3600)
    minutes, seconds = divmod(total, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts[:3])


def safe_text(value: str, limit: int = 2000) -> str:
    return value.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")[:limit]
