from __future__ import annotations

import platform
import time

import discord
from discord.ext import commands

from bot.client import NaviBot
from bot.utils.context import send_response

STARTED_AT = time.monotonic()

HELP_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Core": ("help", "ping", "dashboard"),
    "Economía": ("daily", "balance", "pay", "work", "leaderboard"),
    "Animales": ("animal cat/dog/fox/bunny/otter/panda/penguin/raccoon/duck/turtle",),
    "Diversión": ("8ball", "choose", "coinflip", "fun …", "game …"),
    "Social": ("ship", "confess", "letter", "social block …", "marriage …"),
    "Roleplay": ("act …", "react …", "interact …"),
    "Utilidad": ("remind", "reminders", "afk", "avatar", "userinfo", "serverinfo"),
    "Moderación": ("warn", "warnings", "timeout", "kick", "ban", "purge", "lock"),
    "Imágenes": ("image resize/crop/rotate/flip/grayscale/invert/blur/sharpen/pixelate/caption/quote/meme/avatar",),
    "Tags": ("tag create/show/edit/delete/raw/list/search/info/claim",),
}


class HelpView(discord.ui.View):
    def __init__(self, author_id: int, prefix: str, dashboard_url: str) -> None:
        super().__init__(timeout=120)
        self.author_id = author_id
        self.prefix = prefix
        self.dashboard_url = dashboard_url
        options = [
            discord.SelectOption(label=category, value=category, description=f"Comandos de {category.lower()}")
            for category in HELP_CATEGORIES
        ]
        select = discord.ui.Select(placeholder="Selecciona un módulo", options=options)
        select.callback = self.select_callback
        self.add_item(select)
        self.add_item(discord.ui.Button(label="Dashboard", url=dashboard_url))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Este panel pertenece a otro operador.", ephemeral=True)
            return False
        return True

    async def select_callback(self, interaction: discord.Interaction) -> None:
        select = next(item for item in self.children if isinstance(item, discord.ui.Select))
        category = select.values[0]
        commands_list = HELP_CATEGORIES[category]
        embed = discord.Embed(
            title=f"N.A.V.I // {category.upper()}",
            description="\n".join(f"`/{name}`" for name in commands_list),
            color=discord.Color.from_rgb(72, 209, 174),
        )
        embed.set_footer(text=f"Prefijo actual: {self.prefix}")
        await interaction.response.edit_message(embed=embed, view=self)


class CoreCog(commands.Cog):
    def __init__(self, bot: NaviBot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="help", description="Muestra todos los módulos y comandos de N.A.V.I.")
    async def help_command(self, ctx: commands.Context, category: str | None = None) -> None:
        prefix = "!"
        if ctx.guild:
            prefix = (await self.bot.configs.get(ctx.guild.id, ctx.guild.name)).prefix
        if category:
            match = next((name for name in HELP_CATEGORIES if name.lower() == category.lower()), None)
            if match:
                embed = discord.Embed(
                    title=f"N.A.V.I // {match.upper()}",
                    description="\n".join(f"`/{name}`" for name in HELP_CATEGORIES[match]),
                    color=discord.Color.from_rgb(72, 209, 174),
                )
                embed.set_footer(text=f"También disponibles con prefijo: {prefix}")
                await send_response(ctx, embed=embed)
                return

        embed = discord.Embed(
            title="N.A.V.I // COMMAND INDEX",
            description=(
                "Sistema de comandos híbridos. Puedes usar slash commands o el prefijo configurado.\n"
                f"**Prefijo actual:** `{prefix}`"
            ),
            color=discord.Color.from_rgb(72, 209, 174),
        )
        for name, values in HELP_CATEGORIES.items():
            embed.add_field(name=name, value=" · ".join(f"`/{value}`" for value in values), inline=False)
        embed.set_footer(text="Selecciona un módulo para ver su índice.")
        await send_response(ctx, embed=embed, view=HelpView(ctx.author.id, prefix, self.bot.settings.dashboard_url))

    @commands.hybrid_command(name="ping", description="Muestra la latencia y el estado de N.A.V.I.")
    async def ping(self, ctx: commands.Context) -> None:
        uptime = int(time.monotonic() - STARTED_AT)
        embed = discord.Embed(title="N.A.V.I // STATUS", color=discord.Color.green())
        embed.add_field(name="Gateway", value=f"`{self.bot.latency * 1000:.1f} ms`")
        embed.add_field(name="Uptime", value=f"`{uptime // 3600}h {(uptime % 3600) // 60}m`")
        embed.add_field(name="Nodos", value=f"`{len(self.bot.guilds)} guilds`")
        embed.set_footer(text=f"Python {platform.python_version()} · discord.py {discord.__version__}")
        await send_response(ctx, embed=embed)

    @commands.hybrid_command(name="dashboard", description="Abre el dashboard administrativo de N.A.V.I.")
    async def dashboard(self, ctx: commands.Context) -> None:
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Abrir Dashboard", url=self.bot.settings.dashboard_url))
        await send_response(
            ctx,
            "Autentícate con Discord para gestionar únicamente los servidores donde tienes permisos.",
            view=view,
            ephemeral=ctx.interaction is not None,
        )


async def setup(bot: NaviBot) -> None:
    await bot.add_cog(CoreCog(bot))
