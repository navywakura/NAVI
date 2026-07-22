from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands
from sqlalchemy import select

from bot.client import NaviBot
from bot.utils.context import format_timedelta, require_guild_module, send_response
from database.connection import AsyncSessionLocal
from database.models import EconomyAccount


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def _account(session, guild_id: int, user_id: int, lock: bool = False) -> EconomyAccount:
    query = select(EconomyAccount).where(
        EconomyAccount.guild_id == guild_id,
        EconomyAccount.user_id == user_id,
    )
    if lock:
        query = query.with_for_update()
    result = await session.execute(query)
    account = result.scalar_one_or_none()
    if account is None:
        account = EconomyAccount(guild_id=guild_id, user_id=user_id)
        session.add(account)
        await session.flush()
    return account


class EconomyCog(commands.Cog):
    def __init__(self, bot: NaviBot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="balance", description="Consulta el saldo de un operador.")
    async def balance(self, ctx: commands.Context, user: discord.Member | None = None) -> None:
        if not await require_guild_module(ctx, self.bot, "economy"):
            return
        target = user or ctx.author
        config = await self.bot.configs.get(ctx.guild.id)
        async with AsyncSessionLocal() as session:
            account = await _account(session, ctx.guild.id, target.id)
            await session.commit()
        await send_response(ctx, f"{target.mention}: **{account.balance:,} {config.currency_name}**")

    @commands.hybrid_command(name="daily", description="Reclama la asignación diaria.")
    async def daily(self, ctx: commands.Context) -> None:
        if not await require_guild_module(ctx, self.bot, "economy"):
            return
        config = await self.bot.configs.get(ctx.guild.id)
        now = _utcnow()
        async with AsyncSessionLocal() as session:
            account = await _account(session, ctx.guild.id, ctx.author.id, lock=True)
            last_daily = _as_utc(account.last_daily_at)
            if last_daily and now - last_daily < timedelta(hours=24):
                remaining = timedelta(hours=24) - (now - last_daily)
                await send_response(ctx, f"Asignación ya reclamada. Próxima ventana en {format_timedelta(remaining)}.", ephemeral=True)
                return
            account.balance += config.daily_amount
            account.last_daily_at = now
            await session.commit()
        await send_response(ctx, f"Asignación procesada: **+{config.daily_amount:,} {config.currency_name}**.")

    @commands.hybrid_command(name="work", description="Ejecuta una tarea y recibe una recompensa.")
    async def work(self, ctx: commands.Context) -> None:
        if not await require_guild_module(ctx, self.bot, "economy"):
            return
        config = await self.bot.configs.get(ctx.guild.id)
        now = _utcnow()
        jobs = (
            "auditaste los logs del nodo",
            "optimizaste una consulta SQL",
            "parcheaste un servicio inestable",
            "clasificaste incidencias del servidor",
            "limpiaste la cola de procesos",
        )
        async with AsyncSessionLocal() as session:
            account = await _account(session, ctx.guild.id, ctx.author.id, lock=True)
            last_work = _as_utc(account.last_work_at)
            if last_work and now - last_work < timedelta(minutes=30):
                remaining = timedelta(minutes=30) - (now - last_work)
                await send_response(ctx, f"Nodo ocupado. Reintenta en {format_timedelta(remaining)}.", ephemeral=True)
                return
            reward = random.randint(config.work_min_amount, config.work_max_amount)
            account.balance += reward
            account.last_work_at = now
            await session.commit()
        await send_response(ctx, f"{random.choice(jobs).capitalize()}. Recompensa: **+{reward:,} {config.currency_name}**.")

    @commands.hybrid_command(name="pay", description="Transfiere créditos a otro operador.")
    async def pay(self, ctx: commands.Context, user: discord.Member, amount: int) -> None:
        if not await require_guild_module(ctx, self.bot, "economy"):
            return
        if amount <= 0 or user.bot or user.id == ctx.author.id:
            await send_response(ctx, "Transferencia inválida.", ephemeral=True)
            return
        config = await self.bot.configs.get(ctx.guild.id)
        async with AsyncSessionLocal() as session:
            sender = await _account(session, ctx.guild.id, ctx.author.id, lock=True)
            receiver = await _account(session, ctx.guild.id, user.id, lock=True)
            if sender.balance < amount:
                await send_response(ctx, "Saldo insuficiente.", ephemeral=True)
                return
            sender.balance -= amount
            receiver.balance += amount
            await session.commit()
        await send_response(ctx, f"Transferencia confirmada: **{amount:,} {config.currency_name}** a {user.mention}.")


async def setup(bot: NaviBot) -> None:
    await bot.add_cog(EconomyCog(bot))
