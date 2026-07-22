from __future__ import annotations

import asyncio
import ipaddress
import socket
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import discord
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 16_000_000


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def fit_text(draw: ImageDraw.ImageDraw, text: str, width: int, start_size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    size = start_size
    while size > 12:
        candidate = font(size, bold=bold)
        if draw.textbbox((0, 0), text, font=candidate)[2] <= width:
            return candidate
        size -= 2
    return font(12, bold=bold)


def wrap_text(draw: ImageDraw.ImageDraw, text: str, text_font: ImageFont.ImageFont, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=text_font)[2] <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def _validate_host(hostname: str) -> None:
    addresses = socket.getaddrinfo(hostname, None)
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("La URL apunta a una red no permitida.")


async def download_url(client, url: str, *, validate_public: bool = True) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL inválida.")
    if validate_public:
        await asyncio.to_thread(_validate_host, parsed.hostname)
    async with client.stream("GET", url, follow_redirects=True) as response:
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            raise ValueError("El recurso no es una imagen.")
        data = bytearray()
        async for chunk in response.aiter_bytes():
            data.extend(chunk)
            if len(data) > MAX_DOWNLOAD_BYTES:
                raise ValueError("Imagen demasiado grande.")
    return bytes(data)


async def attachment_bytes(attachment: discord.Attachment) -> bytes:
    if attachment.size > MAX_DOWNLOAD_BYTES:
        raise ValueError("El archivo supera 10 MB.")
    if attachment.content_type and not attachment.content_type.startswith("image/"):
        raise ValueError("El archivo adjunto no es una imagen.")
    return await attachment.read()


async def avatar_bytes(user: discord.abc.User) -> bytes:
    return await user.display_avatar.replace(size=1024, static_format="png").read()


def load_image(data: bytes) -> Image.Image:
    image = Image.open(BytesIO(data))
    image.load()
    if image.width * image.height > MAX_PIXELS:
        raise ValueError("La resolución máxima es 16 megapíxeles.")
    return ImageOps.exif_transpose(image).convert("RGBA")


def image_file(image: Image.Image, filename: str = "navi-output.png", *, format_name: str = "PNG") -> discord.File:
    buffer = BytesIO()
    image.save(buffer, format=format_name, optimize=True)
    buffer.seek(0)
    return discord.File(buffer, filename=filename)


def gif_file(frames: list[Image.Image], filename: str = "navi-output.gif", duration: int = 80) -> discord.File:
    buffer = BytesIO()
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0,
        disposal=2,
    )
    buffer.seek(0)
    return discord.File(buffer, filename=filename)


def square_avatar(image: Image.Image, size: int) -> Image.Image:
    return ImageOps.fit(image.convert("RGBA"), (size, size), method=Image.Resampling.LANCZOS)


def rounded(image: Image.Image, radius: int) -> Image.Image:
    image = image.convert("RGBA")
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, image.width, image.height), radius=radius, fill=255)
    result = Image.new("RGBA", image.size)
    result.paste(image, mask=mask)
    return result


def petpet_frames(image: Image.Image) -> list[Image.Image]:
    avatar = square_avatar(image, 112)
    frames: list[Image.Image] = []
    squashes = [(0, 0, 112, 112), (4, 8, 108, 104), (6, 14, 106, 98), (3, 8, 109, 104), (0, 0, 112, 112)]
    hand_positions = [(67, 2), (64, 8), (61, 14), (64, 8), (67, 2)]
    for box, hand in zip(squashes, hand_positions):
        frame = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        resized = avatar.resize((box[2] - box[0], box[3] - box[1]), Image.Resampling.LANCZOS)
        frame.alpha_composite(resized, (8 + box[0], 12 + box[1]))
        draw = ImageDraw.Draw(frame)
        x, y = hand
        draw.ellipse((x, y, x + 50, y + 28), fill=(244, 190, 145, 255), outline=(30, 30, 30, 255), width=2)
        for offset in range(4):
            draw.rounded_rectangle((x + 2 + offset * 10, y + 18, x + 11 + offset * 10, y + 42), radius=4, fill=(244, 190, 145, 255), outline=(30, 30, 30, 255), width=1)
        frames.append(frame)
    return frames


def apply_operation(image: Image.Image, operation: str, **kwargs) -> Image.Image:
    operation = operation.lower()
    if operation == "resize":
        width = max(16, min(4096, int(kwargs["width"])))
        height = max(16, min(4096, int(kwargs["height"])))
        return image.resize((width, height), Image.Resampling.LANCZOS)
    if operation == "crop":
        x = max(0, int(kwargs.get("x", 0)))
        y = max(0, int(kwargs.get("y", 0)))
        width = max(1, int(kwargs["width"]))
        height = max(1, int(kwargs["height"]))
        return image.crop((x, y, min(image.width, x + width), min(image.height, y + height)))
    if operation == "rotate":
        return image.rotate(float(kwargs.get("degrees", 90)), expand=True, resample=Image.Resampling.BICUBIC)
    if operation == "flip":
        return ImageOps.flip(image) if kwargs.get("direction") == "vertical" else ImageOps.mirror(image)
    if operation == "grayscale":
        return ImageOps.grayscale(image).convert("RGBA")
    if operation == "invert":
        rgb = ImageOps.invert(image.convert("RGB"))
        rgb.putalpha(image.getchannel("A"))
        return rgb
    if operation == "blur":
        return image.filter(ImageFilter.GaussianBlur(radius=max(0.1, min(30, float(kwargs.get("radius", 3))))))
    if operation == "sharpen":
        return ImageEnhance.Sharpness(image).enhance(max(0, min(8, float(kwargs.get("factor", 2)))))
    if operation == "pixelate":
        block = max(2, min(100, int(kwargs.get("block", 12))))
        small = image.resize((max(1, image.width // block), max(1, image.height // block)), Image.Resampling.NEAREST)
        return small.resize(image.size, Image.Resampling.NEAREST)
    raise ValueError(f"Operación no soportada: {operation}")
