from __future__ import annotations

from time import monotonic

import discord
from discord.ext import commands
from openai import AsyncOpenAI

from bot.client import NaviBot


class AIChatCog(commands.Cog):
    def __init__(self, bot: NaviBot) -> None:
        self.bot = bot
        api_key = (
            bot.settings.openai_api_key.get_secret_value()
            if bot.settings.openai_api_key
            else None
        )
        self.client = AsyncOpenAI(api_key=api_key) if api_key else None
        self.cooldowns: dict[tuple[int, int], float] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        if not await self.bot.module_enabled(message.guild.id, "ai_chat"):
            return

        config = await self.bot.configs.get(message.guild.id, message.guild.name)
        mentioned = self.bot.user is not None and self.bot.user in message.mentions
        in_ai_channel = config.ai_channel_id is not None and message.channel.id == config.ai_channel_id
        if not mentioned and not in_ai_channel:
            return

        if self.client is None:
            await message.reply(
                "AI_CHAT_UNAVAILABLE: falta OPENAI_API_KEY en el entorno.",
                mention_author=False,
            )
            return

        key = (message.guild.id, message.author.id)
        now = monotonic()
        if now < self.cooldowns.get(key, 0):
            return
        self.cooldowns[key] = now + 15

        content = message.content
        if self.bot.user:
            content = content.replace(f"<@{self.bot.user.id}>", "").replace(
                f"<@!{self.bot.user.id}>", ""
            )
        content = content.strip()[:4000]
        if not content:
            return

        async with message.channel.typing():
            try:
                response = await self.client.responses.create(
                    model=config.ai_model or self.bot.settings.openai_model,
                    instructions=config.ai_system_prompt,
                    input=(
                        f"Servidor: {message.guild.name}\n"
                        f"Operador: {message.author.display_name}\n"
                        f"Consulta: {content}"
                    ),
                    max_output_tokens=500,
                )
                output = (response.output_text or "Sin respuesta.")[:1900]
            except Exception:
                await message.reply(
                    "AI_PROVIDER_ERROR: no se pudo completar la solicitud.",
                    mention_author=False,
                )
                return

        await message.reply(
            output,
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: NaviBot) -> None:
    await bot.add_cog(AIChatCog(bot))
