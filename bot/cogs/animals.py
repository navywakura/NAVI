from __future__ import annotations

import random

import discord
from discord.ext import commands

from bot.client import NaviBot
from bot.utils.context import require_guild_module, send_response

ANIMAL_ENDPOINTS = {
    "cat": ("https://api.thecatapi.com/v1/images/search", "url"),
    "dog": ("https://random.dog/woof.json", "url"),
    "fox": ("https://randomfox.ca/floof/", "image"),
    "bunny": ("https://api.bunnies.io/v2/loop/random/?media=gif,png", "media.poster"),
    "otter": ("https://api.otakugifs.xyz/gif?reaction=happy", "url"),
    "panda": ("https://some-random-api.com/animal/panda", "image"),
    "penguin": ("https://some-random-api.com/animal/penguin", "image"),
    "raccoon": ("https://some-random-api.com/animal/raccoon", "image"),
    "duck": ("https://random-d.uk/api/v2/random", "url"),
    "turtle": ("https://some-random-api.com/animal/turtle", "image"),
}

FALLBACK_IMAGES = {
    "cat": "https://cataas.com/cat",
    "dog": "https://placedog.net/640/480?random",
    "fox": "https://randomfox.ca/images/1.jpg",
    "bunny": "https://placehold.co/800x600/png?text=BUNNY+NODE",
    "otter": "https://placehold.co/800x600/png?text=OTTER+NODE",
    "panda": "https://placehold.co/800x600/png?text=PANDA+NODE",
    "penguin": "https://placehold.co/800x600/png?text=PENGUIN+NODE",
    "raccoon": "https://placehold.co/800x600/png?text=RACCOON+NODE",
    "duck": "https://random-d.uk/api/v2/randomimg",
    "turtle": "https://placehold.co/800x600/png?text=TURTLE+NODE",
}


def _extract(data, path: str) -> str | None:
    if isinstance(data, list):
        data = data[0] if data else None
    current = data
    for key in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current if isinstance(current, str) else None


class AnimalsCog(commands.Cog):
    def __init__(self, bot: NaviBot) -> None:
        self.bot = bot

    @commands.hybrid_group(name="animal", description="Solicita una imagen aleatoria de un animal.", invoke_without_command=True)
    async def animal(self, ctx: commands.Context) -> None:
        await send_response(ctx, "Usa `/animal cat`, `/animal dog`, `/animal fox`…", ephemeral=True)

    async def _send_animal(self, ctx: commands.Context, animal: str) -> None:
        if not await require_guild_module(ctx, self.bot, "animals"):
            return
        url = None
        endpoint, path = ANIMAL_ENDPOINTS[animal]
        if self.bot.web_client:
            try:
                response = await self.bot.web_client.get(endpoint)
                response.raise_for_status()
                url = _extract(response.json(), path)
            except Exception:
                url = None
        url = url or FALLBACK_IMAGES[animal]
        embed = discord.Embed(
            title=f"N.A.V.I // {animal.upper()} NODE",
            description=random.choice(("Muestra adquirida.", "Canal visual sincronizado.", "Entidad localizada.")),
            color=discord.Color.from_rgb(72, 209, 174),
        )
        embed.set_image(url=url)
        embed.set_footer(text=f"Solicitado por {ctx.author.display_name}")
        await send_response(ctx, embed=embed)

    @animal.command(name="cat", description="Gato aleatorio.")
    async def cat(self, ctx: commands.Context) -> None:
        await self._send_animal(ctx, "cat")

    @animal.command(name="dog", description="Perro aleatorio.")
    async def dog(self, ctx: commands.Context) -> None:
        await self._send_animal(ctx, "dog")

    @animal.command(name="fox", description="Zorro aleatorio.")
    async def fox(self, ctx: commands.Context) -> None:
        await self._send_animal(ctx, "fox")

    @animal.command(name="bunny", description="Conejo aleatorio.")
    async def bunny(self, ctx: commands.Context) -> None:
        await self._send_animal(ctx, "bunny")

    @animal.command(name="otter", description="Nutria aleatoria.")
    async def otter(self, ctx: commands.Context) -> None:
        await self._send_animal(ctx, "otter")

    @animal.command(name="panda", description="Panda aleatorio.")
    async def panda(self, ctx: commands.Context) -> None:
        await self._send_animal(ctx, "panda")

    @animal.command(name="penguin", description="Pingüino aleatorio.")
    async def penguin(self, ctx: commands.Context) -> None:
        await self._send_animal(ctx, "penguin")

    @animal.command(name="raccoon", description="Mapache aleatorio.")
    async def raccoon(self, ctx: commands.Context) -> None:
        await self._send_animal(ctx, "raccoon")

    @animal.command(name="duck", description="Pato aleatorio.")
    async def duck(self, ctx: commands.Context) -> None:
        await self._send_animal(ctx, "duck")

    @animal.command(name="turtle", description="Tortuga aleatoria.")
    async def turtle(self, ctx: commands.Context) -> None:
        await self._send_animal(ctx, "turtle")


async def setup(bot: NaviBot) -> None:
    await bot.add_cog(AnimalsCog(bot))
