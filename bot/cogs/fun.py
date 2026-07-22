from __future__ import annotations

import random

from discord.ext import commands

from bot.client import NaviBot
from bot.utils.context import require_guild_module, send_response


class BasicFunCog(commands.Cog):
    def __init__(self, bot: NaviBot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="8ball", description="Consulta la matriz probabilística de N.A.V.I.")
    async def eight_ball(self, ctx: commands.Context, *, question: str) -> None:
        if not await require_guild_module(ctx, self.bot, "fun"):
            return
        answer = random.choice(
            (
                "Sí. Probabilidad alta.",
                "No. El vector no converge.",
                "Posible, pero faltan datos.",
                "Los logs indican que sí.",
                "Resultado indeterminado. Repite más tarde.",
                "No confiaría en ese plan.",
                "Afirmativo.",
                "Negativo.",
            )
        )
        await send_response(ctx, f"**QUERY:** {question[:500]}\n**N.A.V.I:** {answer}")

    @commands.hybrid_command(name="choose", description="Selecciona una opción separada por |.")
    async def choose(self, ctx: commands.Context, *, options: str) -> None:
        if not await require_guild_module(ctx, self.bot, "fun"):
            return
        values = [item.strip() for item in options.split("|") if item.strip()]
        if len(values) < 2 or len(values) > 20:
            await send_response(ctx, "Introduce entre 2 y 20 opciones separadas con `|`.", ephemeral=True)
            return
        await send_response(ctx, f"Selección: **{random.choice(values)[:500]}**")

    @commands.hybrid_command(name="coinflip", description="Lanza una moneda.")
    async def coinflip(self, ctx: commands.Context) -> None:
        if await require_guild_module(ctx, self.bot, "fun"):
            await send_response(ctx, random.choice(("🪙 **Cara**", "🪙 **Cruz**")))


async def setup(bot: NaviBot) -> None:
    await bot.add_cog(BasicFunCog(bot))
