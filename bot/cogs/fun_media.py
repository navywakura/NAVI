from __future__ import annotations

import asyncio
import hashlib
import random
import re
from io import BytesIO

import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from bot.client import NaviBot
from bot.utils.context import defer, require_guild_module, safe_text, send_response
from bot.utils.media import (
    avatar_bytes,
    download_url,
    fit_text,
    font,
    gif_file,
    image_file,
    load_image,
    petpet_frames,
    rounded,
    square_avatar,
    wrap_text,
)

FORTUNES = (
    "Un proceso bloqueado se resolverá cuando dejes de forzarlo.",
    "La próxima decisión correcta parecerá pequeña al principio.",
    "Un operador silencioso observa más de lo que declara.",
    "Evita desplegar en viernes. El sistema ya te avisó.",
    "Tu siguiente error contendrá información útil.",
    "Una conexión antigua volverá a aparecer en los logs.",
)
CAT_FACTS = (
    "Los gatos pueden rotar sus orejas de forma independiente.",
    "El patrón de la nariz de un gato es individual, como una huella.",
    "Los gatos pasan gran parte del día durmiendo para conservar energía.",
)
DOG_FACTS = (
    "El olfato de un perro es mucho más sensible que el humano.",
    "Los perros interpretan señales humanas como gestos y dirección de la mirada.",
    "La forma y movilidad de las orejas varían enormemente entre razas.",
)
MESSAGE_URL = re.compile(r"https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)")


def _spongify(text: str) -> str:
    upper = True
    result = []
    for character in text:
        if character.isalpha():
            result.append(character.upper() if upper else character.lower())
            upper = not upper
        else:
            result.append(character)
    return "".join(result)


def _bonk_image(actor: Image.Image, target: Image.Image) -> Image.Image:
    canvas = Image.new("RGB", (900, 500), (18, 20, 24))
    draw = ImageDraw.Draw(canvas)
    canvas.paste(rounded(square_avatar(actor, 260), 40), (90, 150), rounded(square_avatar(actor, 260), 40))
    canvas.paste(rounded(square_avatar(target, 260), 40), (550, 150), rounded(square_avatar(target, 260), 40))
    draw.line((300, 170, 600, 80), fill=(170, 112, 62), width=38)
    draw.ellipse((560, 50, 720, 150), fill=(190, 130, 75), outline=(240, 210, 160), width=8)
    draw.text((355, 340), "BONK", font=font(72, bold=True), fill=(255, 255, 255))
    draw.text((20, 20), "N.A.V.I // IMPACT EVENT", font=font(24, bold=True), fill=(72, 209, 174))
    return canvas


def _profile_card(image: Image.Image, title: str, subtitle: str, badge: str) -> Image.Image:
    canvas = Image.new("RGB", (1000, 560), (15, 17, 21))
    draw = ImageDraw.Draw(canvas)
    avatar = rounded(square_avatar(image, 360), 54)
    canvas.paste(avatar, (70, 100), avatar)
    draw.rounded_rectangle((470, 100, 930, 460), radius=32, fill=(28, 31, 38), outline=(72, 209, 174), width=3)
    draw.text((500, 135), badge, font=font(28, bold=True), fill=(72, 209, 174))
    title_font = fit_text(draw, title, 390, 58, bold=True)
    draw.text((500, 210), title, font=title_font, fill=(245, 245, 245))
    for index, line in enumerate(wrap_text(draw, subtitle, font(28), 390)[:5]):
        draw.text((500, 300 + index * 38), line, font=font(28), fill=(190, 196, 205))
    draw.text((30, 24), "N.A.V.I // MEDIA CORE", font=font(24, bold=True), fill=(130, 138, 150))
    return canvas


def _match_card(users: list[tuple[str, Image.Image]]) -> Image.Image:
    canvas = Image.new("RGB", (1000, 700), (14, 16, 20))
    draw = ImageDraw.Draw(canvas)
    draw.text((40, 30), "N.A.V.I // MATCH MATRIX", font=font(34, bold=True), fill=(72, 209, 174))
    positions = [(80, 130), (560, 130), (80, 410), (560, 410)]
    for (name, image), (x, y) in zip(users, positions):
        avatar = rounded(square_avatar(image, 190), 36)
        canvas.paste(avatar, (x, y), avatar)
        draw.text((x + 210, y + 55), name[:18], font=fit_text(draw, name[:18], 170, 32, bold=True), fill="white")
    draw.text((450, 320), "VS", font=font(64, bold=True), fill=(230, 86, 86))
    return canvas


def _quote_card(author: str, avatar: Image.Image, content: str) -> Image.Image:
    canvas = Image.new("RGB", (1200, 675), (11, 13, 17))
    blurred = ImageOps.fit(avatar.convert("RGB"), canvas.size, Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(28))
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 170))
    canvas = Image.alpha_composite(blurred.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(canvas)
    av = rounded(square_avatar(avatar, 180), 90)
    canvas.alpha_composite(av, (80, 70))
    draw.text((300, 90), author, font=font(42, bold=True), fill=(72, 209, 174))
    quote_font = font(38)
    lines = wrap_text(draw, content, quote_font, 1000)
    y = 310 - min(100, len(lines) * 15)
    for line in lines[:7]:
        draw.text((100, y), line, font=quote_font, fill="white")
        y += 52
    draw.text((900, 620), "N.A.V.I QUOTE", font=font(22, bold=True), fill=(190, 196, 205))
    return canvas.convert("RGB")


def _mockpost(author: str, avatar: Image.Image, text: str) -> Image.Image:
    canvas = Image.new("RGB", (1000, 580), (245, 247, 250))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((55, 45, 945, 535), radius=34, fill="white", outline=(205, 210, 218), width=3)
    av = rounded(square_avatar(avatar, 110), 55)
    canvas.paste(av, (100, 100), av)
    draw.text((235, 105), author[:28], font=font(34, bold=True), fill=(25, 30, 36))
    draw.text((235, 150), "@parody_operator · now", font=font(24), fill=(100, 108, 118))
    body_font = font(34)
    y = 250
    for line in wrap_text(draw, text, body_font, 760)[:5]:
        draw.text((105, y), line, font=body_font, fill=(30, 34, 40))
        y += 48
    draw.rectangle((55, 490, 945, 535), fill=(235, 75, 75))
    draw.text((315, 497), "PARODIA · CONTENIDO GENERADO", font=font(24, bold=True), fill="white")
    return canvas


def _twemoji_codepoint(emoji: str) -> str:
    values = [f"{ord(char):x}" for char in emoji if ord(char) != 0xFE0F]
    return "-".join(values)


class FunMediaCog(commands.Cog):
    def __init__(self, bot: NaviBot) -> None:
        self.bot = bot

    @commands.hybrid_group(name="fun", description="Herramientas de diversión y medios.", invoke_without_command=True)
    async def fun(self, ctx: commands.Context) -> None:
        await send_response(ctx, "Subcomandos: petpet, bonk, spongify, stonks, sus, match, fortune, catfact, dogfact, emojimix, quote, mockpost.", ephemeral=True)

    async def _guard(self, ctx: commands.Context) -> bool:
        return await require_guild_module(ctx, self.bot, "fun")

    @fun.command(name="petpet", description="Genera una animación petpet con el avatar de un usuario.")
    @commands.cooldown(1, 8, commands.BucketType.user)
    async def petpet(self, ctx: commands.Context, user: discord.Member | None = None) -> None:
        if not await self._guard(ctx):
            return
        target = user or ctx.author
        await defer(ctx)
        data = await avatar_bytes(target)
        frames = await asyncio.to_thread(petpet_frames, load_image(data))
        await send_response(ctx, file=gif_file(frames, "petpet.gif"))

    @fun.command(name="bonk", description="Genera un impacto BONK entre dos operadores.")
    @commands.cooldown(1, 8, commands.BucketType.user)
    async def bonk(self, ctx: commands.Context, user: discord.Member) -> None:
        if not await self._guard(ctx):
            return
        await defer(ctx)
        actor_data, target_data = await asyncio.gather(avatar_bytes(ctx.author), avatar_bytes(user))
        image = await asyncio.to_thread(_bonk_image, load_image(actor_data), load_image(target_data))
        await send_response(ctx, file=image_file(image, "bonk.png"))

    @fun.command(name="spongify", description="Alterna mayúsculas y minúsculas.")
    async def spongify(self, ctx: commands.Context, *, text: str) -> None:
        if await self._guard(ctx):
            await send_response(ctx, safe_text(_spongify(text), 1900))

    @fun.command(name="stonks", description="Genera una tarjeta STONKS.")
    async def stonks(self, ctx: commands.Context, user: discord.Member | None = None) -> None:
        if not await self._guard(ctx):
            return
        target = user or ctx.author
        await defer(ctx)
        image = load_image(await avatar_bytes(target))
        score = int(hashlib.sha256(f"{ctx.guild.id}:{target.id}:stonks".encode()).hexdigest()[:4], 16) % 1001
        card = await asyncio.to_thread(_profile_card, image, target.display_name, f"Índice bursátil personal: {score}%", "STONKS ANALYSIS")
        await send_response(ctx, file=image_file(card, "stonks.png"))

    @fun.command(name="sus", description="Calcula el índice SUS de un usuario.")
    async def sus(self, ctx: commands.Context, user: discord.Member | None = None) -> None:
        if not await self._guard(ctx):
            return
        target = user or ctx.author
        await defer(ctx)
        image = load_image(await avatar_bytes(target))
        score = int(hashlib.sha256(f"{ctx.guild.id}:{target.id}:sus".encode()).hexdigest()[:4], 16) % 101
        card = await asyncio.to_thread(_profile_card, image, target.display_name, f"Actividad sospechosa detectada: {score}%", "SUS PROTOCOL")
        await send_response(ctx, file=image_file(card, "sus.png"))

    @fun.command(name="match", description="Genera una matriz 2 contra 2.")
    async def match(self, ctx: commands.Context, user1: discord.Member, user2: discord.Member, user3: discord.Member, user4: discord.Member) -> None:
        if not await self._guard(ctx):
            return
        await defer(ctx)
        users = [user1, user2, user3, user4]
        data = await asyncio.gather(*(avatar_bytes(user) for user in users))
        card = await asyncio.to_thread(_match_card, [(u.display_name, load_image(d)) for u, d in zip(users, data)])
        await send_response(ctx, file=image_file(card, "match.png"))

    @fun.command(name="fortune", description="Obtén un pronóstico de N.A.V.I.")
    async def fortune(self, ctx: commands.Context) -> None:
        if await self._guard(ctx):
            await send_response(ctx, f"🔮 {random.choice(FORTUNES)}")

    @fun.command(name="catfact", description="Dato breve sobre gatos.")
    async def catfact(self, ctx: commands.Context) -> None:
        if await self._guard(ctx):
            await send_response(ctx, f"🐈 {random.choice(CAT_FACTS)}")

    @fun.command(name="dogfact", description="Dato breve sobre perros.")
    async def dogfact(self, ctx: commands.Context) -> None:
        if await self._guard(ctx):
            await send_response(ctx, f"🐕 {random.choice(DOG_FACTS)}")

    @fun.command(name="emojimix", description="Combina visualmente dos emojis usando Twemoji.")
    async def emojimix(self, ctx: commands.Context, emoji1: str, emoji2: str) -> None:
        if not await self._guard(ctx):
            return
        await defer(ctx)
        try:
            urls = [
                f"https://cdn.jsdelivr.net/gh/twitter/twemoji@latest/assets/72x72/{_twemoji_codepoint(emoji)}.png"
                for emoji in (emoji1, emoji2)
            ]
            if self.bot.web_client is None:
                raise RuntimeError("HTTP unavailable")
            raw = await asyncio.gather(*(download_url(self.bot.web_client, url, validate_public=False) for url in urls))
            images = [square_avatar(load_image(item), 256) for item in raw]
            canvas = Image.new("RGBA", (600, 320), (18, 20, 24, 255))
            canvas.alpha_composite(images[0], (30, 32))
            canvas.alpha_composite(images[1], (314, 32))
            draw = ImageDraw.Draw(canvas)
            draw.text((275, 122), "+", font=font(64, bold=True), fill=(72, 209, 174))
            await send_response(ctx, file=image_file(canvas, "emojimix.png"))
        except Exception:
            await send_response(ctx, f"Mezcla simbólica: {emoji1} + {emoji2} = {emoji1}{emoji2}")

    async def _resolve_quote(self, ctx: commands.Context, reference: str) -> tuple[str, str, Image.Image]:
        match = MESSAGE_URL.fullmatch(reference.strip())
        if match and ctx.guild and int(match.group(1)) == ctx.guild.id:
            channel = ctx.guild.get_channel(int(match.group(2)))
            if isinstance(channel, discord.TextChannel):
                message = await channel.fetch_message(int(match.group(3)))
                return message.author.display_name, message.clean_content or "[sin texto]", load_image(await avatar_bytes(message.author))
        return ctx.author.display_name, reference, load_image(await avatar_bytes(ctx.author))

    @fun.command(name="quote", description="Convierte texto o un enlace de mensaje en una tarjeta de cita.")
    async def quote(self, ctx: commands.Context, *, message: str) -> None:
        if not await self._guard(ctx):
            return
        await defer(ctx)
        author, content, avatar = await self._resolve_quote(ctx, message)
        card = await asyncio.to_thread(_quote_card, author, avatar, content[:700])
        await send_response(ctx, file=image_file(card, "quote.png"))

    @fun.command(name="mockpost", description="Genera una publicación ficticia marcada como parodia.")
    async def mockpost(self, ctx: commands.Context, *, text: str) -> None:
        if not await self._guard(ctx):
            return
        await defer(ctx)
        avatar = load_image(await avatar_bytes(ctx.author))
        card = await asyncio.to_thread(_mockpost, ctx.author.display_name, avatar, text[:500])
        await send_response(ctx, file=image_file(card, "parody-post.png"))


async def setup(bot: NaviBot) -> None:
    await bot.add_cog(FunMediaCog(bot))
