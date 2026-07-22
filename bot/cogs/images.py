from __future__ import annotations

import asyncio
from typing import Literal

import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from bot.client import NaviBot
from bot.utils.context import defer, require_guild_module, send_response
from bot.utils.media import (
    apply_operation,
    attachment_bytes,
    avatar_bytes,
    fit_text,
    font,
    image_file,
    load_image,
    rounded,
    square_avatar,
    wrap_text,
)


def _caption_image(image: Image.Image, text: str) -> Image.Image:
    image = image.convert("RGB")
    width = image.width
    draw_probe = ImageDraw.Draw(image)
    text_font = fit_text(draw_probe, text, max(200, width - 60), max(28, width // 12), bold=True)
    lines = wrap_text(draw_probe, text, text_font, width - 60)[:5]
    line_height = max(36, text_font.size + 10 if hasattr(text_font, "size") else 42)
    caption_height = 40 + line_height * len(lines)
    canvas = Image.new("RGB", (width, image.height + caption_height), "white")
    canvas.paste(image, (0, caption_height))
    draw = ImageDraw.Draw(canvas)
    y = 20
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=text_font)
        x = (width - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, font=text_font, fill="black")
        y += line_height
    return canvas


def _meme_image(image: Image.Image, top: str, bottom: str) -> Image.Image:
    canvas = image.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    size = max(24, min(90, canvas.width // 10))
    meme_font = font(size, bold=True)

    def draw_centered(text: str, y: int, anchor: str) -> None:
        lines = wrap_text(draw, text.upper(), meme_font, canvas.width - 40)[:3]
        if anchor == "bottom":
            y -= len(lines) * (size + 8)
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=meme_font, stroke_width=4)
            x = (canvas.width - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=meme_font, fill="white", stroke_width=4, stroke_fill="black")
            y += size + 8

    if top:
        draw_centered(top, 16, "top")
    if bottom:
        draw_centered(bottom, canvas.height - 16, "bottom")
    return canvas


def _quote_image(image: Image.Image, text: str, author: str) -> Image.Image:
    size = (1200, 675)
    background = ImageOps.fit(image.convert("RGB"), size, Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(30))
    canvas = background.convert("RGBA")
    canvas.alpha_composite(Image.new("RGBA", size, (0, 0, 0, 175)))
    draw = ImageDraw.Draw(canvas)
    avatar = rounded(square_avatar(image, 190), 95)
    canvas.alpha_composite(avatar, (80, 75))
    draw.text((310, 100), author[:40], font=font(42, bold=True), fill=(72, 209, 174))
    quote_font = font(40)
    y = 310
    for line in wrap_text(draw, text, quote_font, 1000)[:6]:
        draw.text((100, y), line, font=quote_font, fill="white")
        y += 55
    draw.text((930, 620), "N.A.V.I", font=font(22, bold=True), fill=(190, 196, 205))
    return canvas.convert("RGB")


def _avatar_card(image: Image.Image, name: str) -> Image.Image:
    canvas = Image.new("RGBA", (800, 800), (14, 17, 22, 255))
    draw = ImageDraw.Draw(canvas)
    avatar = rounded(square_avatar(image, 560), 280)
    canvas.alpha_composite(avatar, (120, 80))
    draw.ellipse((116, 76, 684, 644), outline=(72, 209, 174), width=8)
    name_font = fit_text(draw, name, 680, 52, bold=True)
    bbox = draw.textbbox((0, 0), name, font=name_font)
    draw.text(((800 - (bbox[2] - bbox[0])) // 2, 680), name, font=name_font, fill="white")
    draw.text((30, 30), "N.A.V.I // AVATAR NODE", font=font(22, bold=True), fill=(120, 130, 145))
    return canvas


class ImagesCog(commands.Cog):
    def __init__(self, bot: NaviBot) -> None:
        self.bot = bot

    @commands.hybrid_group(name="image", description="Edición de imágenes con Pillow.", invoke_without_command=True)
    async def image(self, ctx: commands.Context) -> None:
        await send_response(ctx, "Subcomandos: resize, crop, rotate, flip, grayscale, invert, blur, sharpen, pixelate, caption, quote, meme, avatar.", ephemeral=True)

    async def _guard(self, ctx: commands.Context) -> bool:
        return await require_guild_module(ctx, self.bot, "images")

    async def _source(self, ctx: commands.Context, attachment: discord.Attachment | None, user: discord.Member | None) -> Image.Image:
        if attachment is None and ctx.message and ctx.message.attachments:
            attachment = ctx.message.attachments[0]
        if attachment is not None:
            data = await attachment_bytes(attachment)
        else:
            data = await avatar_bytes(user or ctx.author)
        return await asyncio.to_thread(load_image, data)

    async def _simple(self, ctx: commands.Context, operation: str, attachment: discord.Attachment | None, user: discord.Member | None, **kwargs) -> None:
        if not await self._guard(ctx):
            return
        await defer(ctx)
        try:
            source = await self._source(ctx, attachment, user)
            output = await asyncio.to_thread(apply_operation, source, operation, **kwargs)
        except (ValueError, OSError) as exc:
            await send_response(ctx, f"IMAGE_ERROR: {exc}", ephemeral=True)
            return
        await send_response(ctx, file=image_file(output, f"navi-{operation}.png"))

    @image.command(name="resize", description="Redimensiona una imagen o avatar.")
    async def resize(self, ctx: commands.Context, width: int, height: int, attachment: discord.Attachment | None = None, user: discord.Member | None = None) -> None:
        await self._simple(ctx, "resize", attachment, user, width=width, height=height)

    @image.command(name="crop", description="Recorta una región de la imagen.")
    async def crop(self, ctx: commands.Context, x: int, y: int, width: int, height: int, attachment: discord.Attachment | None = None, user: discord.Member | None = None) -> None:
        await self._simple(ctx, "crop", attachment, user, x=x, y=y, width=width, height=height)

    @image.command(name="rotate", description="Rota una imagen.")
    async def rotate(self, ctx: commands.Context, degrees: float = 90.0, attachment: discord.Attachment | None = None, user: discord.Member | None = None) -> None:
        await self._simple(ctx, "rotate", attachment, user, degrees=degrees)

    @image.command(name="flip", description="Voltea una imagen horizontal o verticalmente.")
    async def flip(self, ctx: commands.Context, direction: Literal["horizontal", "vertical"] = "horizontal", attachment: discord.Attachment | None = None, user: discord.Member | None = None) -> None:
        await self._simple(ctx, "flip", attachment, user, direction=direction)

    @image.command(name="grayscale", description="Convierte una imagen a escala de grises.")
    async def grayscale(self, ctx: commands.Context, attachment: discord.Attachment | None = None, user: discord.Member | None = None) -> None:
        await self._simple(ctx, "grayscale", attachment, user)

    @image.command(name="invert", description="Invierte los colores de una imagen.")
    async def invert(self, ctx: commands.Context, attachment: discord.Attachment | None = None, user: discord.Member | None = None) -> None:
        await self._simple(ctx, "invert", attachment, user)

    @image.command(name="blur", description="Aplica desenfoque gaussiano.")
    async def blur(self, ctx: commands.Context, radius: float = 3.0, attachment: discord.Attachment | None = None, user: discord.Member | None = None) -> None:
        await self._simple(ctx, "blur", attachment, user, radius=radius)

    @image.command(name="sharpen", description="Aumenta la nitidez.")
    async def sharpen(self, ctx: commands.Context, factor: float = 2.0, attachment: discord.Attachment | None = None, user: discord.Member | None = None) -> None:
        await self._simple(ctx, "sharpen", attachment, user, factor=factor)

    @image.command(name="pixelate", description="Pixeliza una imagen.")
    async def pixelate(self, ctx: commands.Context, block: int = 12, attachment: discord.Attachment | None = None, user: discord.Member | None = None) -> None:
        await self._simple(ctx, "pixelate", attachment, user, block=block)

    @image.command(name="caption", description="Añade un texto superior a una imagen.")
    async def caption(self, ctx: commands.Context, text: str, attachment: discord.Attachment | None = None, user: discord.Member | None = None) -> None:
        if not await self._guard(ctx):
            return
        await defer(ctx)
        try:
            source = await self._source(ctx, attachment, user)
            output = await asyncio.to_thread(_caption_image, source, text[:500])
        except (ValueError, OSError) as exc:
            await send_response(ctx, f"IMAGE_ERROR: {exc}", ephemeral=True)
            return
        await send_response(ctx, file=image_file(output, "caption.png"))

    @image.command(name="quote", description="Genera una tarjeta de cita usando una imagen o avatar.")
    async def quote(self, ctx: commands.Context, text: str, user: discord.Member | None = None, attachment: discord.Attachment | None = None) -> None:
        if not await self._guard(ctx):
            return
        target = user or ctx.author
        await defer(ctx)
        try:
            source = await self._source(ctx, attachment, target)
            output = await asyncio.to_thread(_quote_image, source, text[:700], target.display_name)
        except (ValueError, OSError) as exc:
            await send_response(ctx, f"IMAGE_ERROR: {exc}", ephemeral=True)
            return
        await send_response(ctx, file=image_file(output, "quote.png"))

    @image.command(name="meme", description="Añade texto superior e inferior estilo meme.")
    async def meme(self, ctx: commands.Context, top: str, bottom: str = "", attachment: discord.Attachment | None = None, user: discord.Member | None = None) -> None:
        if not await self._guard(ctx):
            return
        await defer(ctx)
        try:
            source = await self._source(ctx, attachment, user)
            output = await asyncio.to_thread(_meme_image, source, top[:300], bottom[:300])
        except (ValueError, OSError) as exc:
            await send_response(ctx, f"IMAGE_ERROR: {exc}", ephemeral=True)
            return
        await send_response(ctx, file=image_file(output, "meme.png"))

    @image.command(name="avatar", description="Genera una tarjeta de avatar.")
    async def avatar(self, ctx: commands.Context, user: discord.Member | None = None) -> None:
        if not await self._guard(ctx):
            return
        target = user or ctx.author
        await defer(ctx)
        source = await self._source(ctx, None, target)
        output = await asyncio.to_thread(_avatar_card, source, target.display_name)
        await send_response(ctx, file=image_file(output, "avatar-card.png"))


async def setup(bot: NaviBot) -> None:
    await bot.add_cog(ImagesCog(bot))
