from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from time import monotonic

import discord
import httpx
from discord.ext import commands

from config import Settings
from database.connection import AsyncSessionLocal
from database.models import GuildConfig

LOGGER = logging.getLogger(__name__)

COG_EXTENSIONS = (
    "bot.cogs.core",
    "bot.cogs.economy",
    "bot.cogs.levels",
    "bot.cogs.welcomes",
    "bot.cogs.automessages",
    "bot.cogs.fun",
    "bot.cogs.animals",
    "bot.cogs.fun_media",
    "bot.cogs.games",
    "bot.cogs.social",
    "bot.cogs.roleplay",
    "bot.cogs.reminders",
    "bot.cogs.moderation",
    "bot.cogs.information",
    "bot.cogs.images",
    "bot.cogs.tags",
    "bot.cogs.ai_chat",
)

MODULE_FIELDS = {
    "economy": "economy_enabled",
    "levels": "levels_enabled",
    "welcomes": "welcomes_enabled",
    "automessages": "automessages_enabled",
    "fun": "fun_enabled",
    "ai_chat": "ai_chat_enabled",
    "animals": "animals_enabled",
    "games": "games_enabled",
    "social": "social_enabled",
    "roleplay": "roleplay_enabled",
    "images": "images_enabled",
    "tags": "tags_enabled",
    "moderation": "moderation_enabled",
    "reminders": "reminders_enabled",
}


@dataclass(slots=True)
class _CacheEntry:
    expires_at: float
    config: GuildConfig


class GuildConfigService:
    """Small TTL cache used by every Cog to gate features per guild."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._cache: dict[int, _CacheEntry] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    async def get(self, guild_id: int, guild_name: str | None = None) -> GuildConfig:
        cached = self._cache.get(guild_id)
        if cached and cached.expires_at > monotonic():
            return cached.config

        lock = self._locks.setdefault(guild_id, asyncio.Lock())
        async with lock:
            cached = self._cache.get(guild_id)
            if cached and cached.expires_at > monotonic():
                return cached.config

            async with AsyncSessionLocal() as session:
                config = await session.get(GuildConfig, guild_id)
                if config is None:
                    config = GuildConfig(guild_id=guild_id, guild_name=guild_name)
                    session.add(config)
                    await session.commit()
                elif guild_name and config.guild_name != guild_name:
                    config.guild_name = guild_name
                    await session.commit()

            self._cache[guild_id] = _CacheEntry(
                expires_at=monotonic() + self._ttl_seconds,
                config=config,
            )
            return config

    def invalidate(self, guild_id: int) -> None:
        self._cache.pop(guild_id, None)

    async def enabled(self, guild_id: int, module: str) -> bool:
        field = MODULE_FIELDS.get(module)
        if field is None:
            raise ValueError(f"Unknown module: {module}")
        config = await self.get(guild_id)
        return bool(getattr(config, field))


async def dynamic_prefix(bot: "NaviBot", message: discord.Message):
    prefix = "!"
    if message.guild is not None:
        try:
            prefix = (await bot.configs.get(message.guild.id, message.guild.name)).prefix
        except Exception:
            LOGGER.exception("Failed to resolve prefix for guild %s", message.guild.id)
    return commands.when_mentioned_or(prefix)(bot, message)


class NaviBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.voice_states = True

        super().__init__(
            command_prefix=dynamic_prefix,
            intents=intents,
            help_command=None,
            case_insensitive=True,
            strip_after_prefix=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.settings = settings
        self.configs = GuildConfigService(settings.config_cache_ttl_seconds)
        self.web_client: httpx.AsyncClient | None = None
        self.tree.on_error = self.on_app_command_error

    async def setup_hook(self) -> None:
        self.web_client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            follow_redirects=True,
            headers={"User-Agent": "NAVI-Bot/1.1"},
        )
        for extension in COG_EXTENSIONS:
            await self.load_extension(extension)
            LOGGER.info("Loaded extension %s", extension)

        LOGGER.info(
            "Registered %d prefix commands and %d application commands",
            len(list(self.walk_commands())),
            len(list(self.tree.walk_commands())),
        )

        if self.settings.sync_commands:
            synced = await self.tree.sync()
            LOGGER.info("Synced %d global application commands", len(synced))

    async def close(self) -> None:
        if self.web_client is not None:
            await self.web_client.aclose()
            self.web_client = None
        await super().close()

    async def on_ready(self) -> None:
        LOGGER.info(
            "N.A.V.I online as %s (%s) in %d guilds",
            self.user,
            getattr(self.user, "id", "unknown"),
            len(self.guilds),
        )
        for guild in self.guilds:
            await self.configs.get(guild.id, guild.name)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self.configs.get(guild.id, guild.name)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.CommandNotFound):
            prefix = "!"
            if ctx.guild:
                prefix = (await self.configs.get(ctx.guild.id, ctx.guild.name)).prefix
            await ctx.reply(
                f"Comando no reconocido. Usa `{prefix}help` o `/help`.",
                mention_author=False,
                delete_after=12,
            )
            return
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(f"Cooldown activo. Reintenta en {error.retry_after:.1f}s.", mention_author=False)
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply("Permisos insuficientes para ejecutar esta operación.", mention_author=False)
            return
        if isinstance(error, commands.BadArgument):
            await ctx.reply(f"Parámetros inválidos: {error}", mention_author=False)
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(f"Falta el parámetro `{error.param.name}`. Usa `/help`.", mention_author=False)
            return
        LOGGER.error(
            "Unhandled prefix command error",
            exc_info=(type(error), error, error.__traceback__),
        )
        await ctx.reply("SYSTEM_ERROR: la operación no pudo completarse.", mention_author=False)


    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: discord.app_commands.AppCommandError,
    ) -> None:
        original = getattr(error, "original", error)
        if isinstance(error, discord.app_commands.CommandOnCooldown):
            message = f"Cooldown activo. Reintenta en {error.retry_after:.1f}s."
        elif isinstance(error, discord.app_commands.MissingPermissions):
            message = "Permisos insuficientes para ejecutar esta operación."
        elif isinstance(error, discord.app_commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            message = f"N.A.V.I no dispone de los permisos requeridos: `{missing}`."
        elif isinstance(error, discord.app_commands.TransformerError):
            message = "No se pudo interpretar uno de los parámetros."
        else:
            LOGGER.error(
                "Unhandled application command error",
                exc_info=(type(original), original, original.__traceback__),
            )
            message = "SYSTEM_ERROR: la operación no pudo completarse."

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    async def module_enabled(self, guild_id: int, module: str) -> bool:
        return await self.configs.enabled(guild_id, module)


def create_bot(settings: Settings) -> NaviBot:
    return NaviBot(settings)
