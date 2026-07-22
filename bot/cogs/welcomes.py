from __future__ import annotations

import discord
from discord.ext import commands

from bot.client import NaviBot


def render_template(template: str, member: discord.Member) -> str:
    return (
        template.replace("{user}", member.mention)
        .replace("{server}", member.guild.name)
        .replace("{count}", str(member.guild.member_count or 0))
    )[:2000]


class WelcomesCog(commands.Cog):
    def __init__(self, bot: NaviBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not await self.bot.module_enabled(member.guild.id, "welcomes"):
            return
        config = await self.bot.configs.get(member.guild.id, member.guild.name)
        channel = member.guild.get_channel(config.welcome_channel_id) if config.welcome_channel_id else member.guild.system_channel
        if isinstance(channel, discord.TextChannel):
            await channel.send(
                render_template(config.welcome_message, member),
                allowed_mentions=discord.AllowedMentions(users=True),
            )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if not await self.bot.module_enabled(member.guild.id, "welcomes"):
            return
        config = await self.bot.configs.get(member.guild.id, member.guild.name)
        channel = member.guild.get_channel(config.goodbye_channel_id) if config.goodbye_channel_id else member.guild.system_channel
        if isinstance(channel, discord.TextChannel):
            await channel.send(
                render_template(config.goodbye_message, member),
                allowed_mentions=discord.AllowedMentions.none(),
            )


async def setup(bot: NaviBot) -> None:
    await bot.add_cog(WelcomesCog(bot))
