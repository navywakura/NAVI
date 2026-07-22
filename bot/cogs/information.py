from __future__ import annotations

import re
from datetime import timezone

import discord
from discord.ext import commands

from bot.client import NaviBot
from bot.utils.context import send_response

CUSTOM_EMOJI = re.compile(r"<(?P<animated>a?):(?P<name>[A-Za-z0-9_]+):(?P<id>\d+)>")


def timestamp(value) -> str:
    return f"<t:{int(value.replace(tzinfo=timezone.utc).timestamp())}:F>"


def yes_no(value: bool) -> str:
    return "Sí" if value else "No"


class InformationCog(commands.Cog):
    def __init__(self, bot: NaviBot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="avatar", description="Muestra el avatar de un usuario.")
    async def avatar(self, ctx: commands.Context, user: discord.Member | None = None) -> None:
        target = user or ctx.author
        asset = target.display_avatar.replace(size=4096)
        embed = discord.Embed(title=f"Avatar // {target}", color=target.color if isinstance(target, discord.Member) else discord.Color.blurple())
        embed.set_image(url=asset.url)
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Abrir original", url=asset.url))
        await send_response(ctx, embed=embed, view=view)

    @commands.hybrid_command(name="banner", description="Muestra el banner de un usuario.")
    async def banner(self, ctx: commands.Context, user: discord.Member | None = None) -> None:
        target = user or ctx.author
        fetched = await self.bot.fetch_user(target.id)
        if fetched.banner is None:
            await send_response(ctx, "El usuario no tiene banner personalizado.", ephemeral=True)
            return
        asset = fetched.banner.replace(size=4096)
        embed = discord.Embed(title=f"Banner // {target}", color=discord.Color.blurple())
        embed.set_image(url=asset.url)
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Abrir original", url=asset.url))
        await send_response(ctx, embed=embed, view=view)

    @commands.hybrid_command(name="userinfo", description="Muestra información de un miembro.")
    async def userinfo(self, ctx: commands.Context, user: discord.Member | None = None) -> None:
        if ctx.guild is None:
            await send_response(ctx, "Comando disponible solo en servidores.", ephemeral=True)
            return
        target = user or ctx.author
        embed = discord.Embed(title=f"USER // {target}", color=target.color)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="ID", value=f"`{target.id}`")
        embed.add_field(name="Bot", value=yes_no(target.bot))
        embed.add_field(name="Cuenta creada", value=f"<t:{int(target.created_at.timestamp())}:R>")
        embed.add_field(name="Entrada al servidor", value=f"<t:{int(target.joined_at.timestamp())}:R>" if target.joined_at else "Desconocida")
        embed.add_field(name="Rol superior", value=target.top_role.mention)
        embed.add_field(name="Roles", value=str(max(0, len(target.roles) - 1)))
        flags = [name.replace("_", " ").title() for name, enabled in target.public_flags if enabled]
        if flags:
            embed.add_field(name="Flags", value=", ".join(flags)[:1024], inline=False)
        await send_response(ctx, embed=embed)

    @commands.hybrid_command(name="serverinfo", description="Muestra información del servidor.")
    async def serverinfo(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await send_response(ctx, "Comando disponible solo en servidores.", ephemeral=True)
            return
        guild = ctx.guild
        embed = discord.Embed(title=f"SERVER // {guild.name}", color=discord.Color.from_rgb(72, 209, 174))
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="ID", value=f"`{guild.id}`")
        embed.add_field(name="Propietario", value=f"<@{guild.owner_id}>")
        embed.add_field(name="Creado", value=f"<t:{int(guild.created_at.timestamp())}:R>")
        embed.add_field(name="Miembros", value=str(guild.member_count or len(guild.members)))
        embed.add_field(name="Canales", value=f"{len(guild.text_channels)} texto · {len(guild.voice_channels)} voz")
        embed.add_field(name="Roles", value=str(len(guild.roles)))
        embed.add_field(name="Emojis", value=str(len(guild.emojis)))
        embed.add_field(name="Boosts", value=f"Nivel {guild.premium_tier} · {guild.premium_subscription_count or 0}")
        embed.add_field(name="Verificación", value=str(guild.verification_level).replace("_", " ").title())
        await send_response(ctx, embed=embed)

    @commands.hybrid_command(name="roleinfo", description="Muestra información de un rol.")
    async def roleinfo(self, ctx: commands.Context, role: discord.Role) -> None:
        embed = discord.Embed(title=f"ROLE // {role.name}", color=role.color)
        embed.add_field(name="ID", value=f"`{role.id}`")
        embed.add_field(name="Posición", value=str(role.position))
        embed.add_field(name="Miembros", value=str(len(role.members)))
        embed.add_field(name="Mencionable", value=yes_no(role.mentionable))
        embed.add_field(name="Separado", value=yes_no(role.hoist))
        embed.add_field(name="Gestionado", value=yes_no(role.managed))
        embed.add_field(name="Creado", value=f"<t:{int(role.created_at.timestamp())}:R>")
        await send_response(ctx, embed=embed)

    @commands.hybrid_command(name="channelinfo", description="Muestra información de un canal.")
    async def channelinfo(self, ctx: commands.Context, channel: discord.TextChannel | None = None) -> None:
        target = channel or ctx.channel
        if not isinstance(target, (discord.TextChannel, discord.Thread)):
            await send_response(ctx, "Canal no compatible.", ephemeral=True)
            return
        embed = discord.Embed(title=f"CHANNEL // {target.name}", color=discord.Color.from_rgb(72, 209, 174))
        embed.add_field(name="ID", value=f"`{target.id}`")
        embed.add_field(name="Tipo", value=str(target.type).replace("_", " ").title())
        embed.add_field(name="Creado", value=f"<t:{int(target.created_at.timestamp())}:R>")
        if isinstance(target, discord.TextChannel):
            embed.add_field(name="Categoría", value=target.category.name if target.category else "Sin categoría")
            embed.add_field(name="Slowmode", value=f"{target.slowmode_delay}s")
            embed.add_field(name="NSFW", value=yes_no(target.nsfw))
            if target.topic:
                embed.add_field(name="Tema", value=target.topic[:1024], inline=False)
        await send_response(ctx, embed=embed)

    @commands.hybrid_command(name="emojiinfo", description="Muestra información de un emoji personalizado o Unicode.")
    async def emojiinfo(self, ctx: commands.Context, emoji: str) -> None:
        match = CUSTOM_EMOJI.fullmatch(emoji.strip())
        if not match:
            codepoints = " ".join(f"U+{ord(char):04X}" for char in emoji)
            await send_response(ctx, f"Emoji: {emoji}\nCodepoints: `{codepoints}`")
            return
        emoji_id = int(match.group("id"))
        animated = bool(match.group("animated"))
        extension = "gif" if animated else "png"
        url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{extension}?size=1024"
        embed = discord.Embed(title=f"EMOJI // {match.group('name')}", color=discord.Color.blurple())
        embed.add_field(name="ID", value=f"`{emoji_id}`")
        embed.add_field(name="Animado", value=yes_no(animated))
        embed.add_field(name="Creado", value=f"<t:{int(discord.utils.snowflake_time(emoji_id).timestamp())}:R>")
        embed.set_image(url=url)
        await send_response(ctx, embed=embed)

    @commands.hybrid_command(name="botinfo", description="Muestra información operativa de N.A.V.I.")
    async def botinfo(self, ctx: commands.Context) -> None:
        user = self.bot.user
        embed = discord.Embed(title="N.A.V.I // BOT INFO", color=discord.Color.from_rgb(72, 209, 174))
        if user:
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.add_field(name="ID", value=f"`{user.id}`")
        embed.add_field(name="Servidores", value=str(len(self.bot.guilds)))
        embed.add_field(name="Usuarios visibles", value=str(sum(g.member_count or 0 for g in self.bot.guilds)))
        embed.add_field(name="Latencia", value=f"{self.bot.latency * 1000:.1f} ms")
        embed.add_field(name="discord.py", value=discord.__version__)
        embed.add_field(name="Comandos prefijo", value=str(len(self.bot.commands)))
        embed.add_field(name="Comandos slash", value=str(len(self.bot.tree.get_commands())))
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Dashboard", url=self.bot.settings.dashboard_url))
        view.add_item(discord.ui.Button(label="Invitar", url=self.bot.settings.effective_invite_url))
        await send_response(ctx, embed=embed, view=view)

    @commands.hybrid_command(name="snowflake", description="Analiza un ID snowflake de Discord.")
    async def snowflake(self, ctx: commands.Context, snowflake_id: str) -> None:
        try:
            value = int(snowflake_id.strip().strip("<@!#&>"))
            created = discord.utils.snowflake_time(value)
        except (ValueError, OverflowError):
            await send_response(ctx, "Snowflake inválido.", ephemeral=True)
            return
        await send_response(
            ctx,
            f"ID: `{value}`\nCreado: <t:{int(created.timestamp())}:F> · <t:{int(created.timestamp())}:R>\nWorker: `{(value & 0x3E0000) >> 17}` · Process: `{(value & 0x1F000) >> 12}` · Increment: `{value & 0xFFF}`",
        )

    @commands.hybrid_command(name="permissions", description="Muestra permisos efectivos de un miembro en un canal.")
    async def permissions(self, ctx: commands.Context, user: discord.Member | None = None, channel: discord.TextChannel | None = None) -> None:
        if ctx.guild is None:
            await send_response(ctx, "Comando disponible solo en servidores.", ephemeral=True)
            return
        target = user or ctx.author
        target_channel = channel or ctx.channel
        perms = target_channel.permissions_for(target) if hasattr(target_channel, "permissions_for") else target.guild_permissions
        enabled = [name.replace("_", " ").title() for name, value in perms if value]
        embed = discord.Embed(
            title=f"PERMISSIONS // {target.display_name}",
            description=", ".join(enabled)[:4000] or "Sin permisos efectivos.",
            color=target.color,
        )
        embed.set_footer(text=f"Canal: {getattr(target_channel, 'name', 'global')}")
        await send_response(ctx, embed=embed, ephemeral=ctx.interaction is not None)


async def setup(bot: NaviBot) -> None:
    await bot.add_cog(InformationCog(bot))
