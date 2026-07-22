from __future__ import annotations

import logging
from time import monotonic

import discord
from discord.ext import commands
from sqlalchemy import select

from bot.client import NaviBot
from bot.utils.context import require_guild_module, send_response
from bot.utils.social import get_preference, is_blocked
from database.connection import AsyncSessionLocal
from database.models import InteractionStat

LOGGER = logging.getLogger(__name__)

ACT_TEXT = {'dance': '{actor} ejecuta una secuencia de baile.', 'laugh': '{actor} se ríe.', 'cry': '{actor} está llorando.', 'facepalm': '{actor} ejecuta un facepalm.', 'sleep': '{actor} entra en modo reposo.', 'think': '{actor} procesa una idea.', 'sing': '{actor} empieza a cantar.', 'cook': '{actor} está cocinando.', 'eat': '{actor} está comiendo.', 'run': '{actor} inicia una carrera.', 'jump': '{actor} salta.', 'wink': '{actor} guiña un ojo.', 'smug': '{actor} muestra una expresión smug.', 'pout': '{actor} hace pucheros.', 'clap': '{actor} aplaude.'}
REACT_TEXT = {'happy': '{actor} está feliz.', 'sad': '{actor} está triste.', 'angry': '{actor} está enfadado/a.', 'blush': '{actor} se sonroja.', 'bored': '{actor} está aburrido/a.', 'confused': '{actor} está confundido/a.', 'scared': '{actor} está asustado/a.', 'smile': '{actor} sonríe.', 'shrug': '{actor} se encoge de hombros.', 'thinking': '{actor} está pensando.', 'baka': '{actor} dice: baka.', 'disgust': '{actor} muestra disgusto.', 'scream': '{actor} grita.', 'peek': '{actor} observa desde un punto seguro.', 'wasted': '{actor} ha quedado fuera de servicio.'}
INTERACTION_TEXT = {'hug': '{actor} abraza a {target}.', 'kiss': '{actor} besa a {target}.', 'pat': '{actor} acaricia a {target}.', 'cuddle': '{actor} se acurruca con {target}.', 'highfive': '{actor} choca los cinco con {target}.', 'handhold': '{actor} toma la mano de {target}.', 'feed': '{actor} alimenta a {target}.', 'bite': '{actor} muerde a {target}.', 'poke': '{actor} toca a {target}.', 'bonk': '{actor} aplica BONK a {target}.', 'slap': '{actor} da una bofetada de roleplay a {target}.', 'heal': '{actor} cura a {target}.', 'greet': '{actor} saluda a {target}.', 'bye': '{actor} se despide de {target}.', 'cheeks': '{actor} pellizca las mejillas de {target}.'}

MEDIA_ALIASES = {
    "facepalm": "facepalm", "think": "think", "thinking": "think", "highfive": "highfive",
    "handhold": "handhold", "cheeks": "pat", "greet": "wave", "bye": "wave",
    "heal": "happy", "wasted": "dead", "disgust": "disgust", "baka": "baka",
}


class RoleplayCog(commands.Cog):
    def __init__(self, bot: NaviBot) -> None:
        self.bot = bot
        self._cooldowns: dict[tuple[int, int], float] = {}

    async def _guard(self, ctx: commands.Context) -> bool:
        if not await require_guild_module(ctx, self.bot, "roleplay"):
            return False
        config = await self.bot.configs.get(ctx.guild.id, ctx.guild.name)
        key = (ctx.guild.id, ctx.author.id)
        now = monotonic()
        retry_at = self._cooldowns.get(key, 0.0)
        if retry_at > now:
            await send_response(ctx, f"Canal social en cooldown. Reintenta en {retry_at - now:.1f}s.", ephemeral=True)
            return False
        self._cooldowns[key] = now + config.social_cooldown_seconds
        return True

    async def _media(self, action: str) -> str | None:
        if self.bot.web_client is None:
            return None
        reaction = MEDIA_ALIASES.get(action, action)
        endpoints = (
            f"https://nekos.best/api/v2/{reaction}",
            f"https://api.otakugifs.xyz/gif?reaction={reaction}",
        )
        for endpoint in endpoints:
            try:
                response = await self.bot.web_client.get(endpoint)
                response.raise_for_status()
                data = response.json()
                if isinstance(data.get("results"), list) and data["results"]:
                    url = data["results"][0].get("url")
                else:
                    url = data.get("url")
                if isinstance(url, str):
                    return url
            except Exception:
                continue
        return None

    async def _self_action(self, ctx: commands.Context, action: str, mapping: dict[str, str]) -> None:
        if not await self._guard(ctx):
            return
        text = mapping[action].format(actor=ctx.author.mention)
        embed = discord.Embed(description=text, color=discord.Color.from_rgb(72, 209, 174))
        config = await self.bot.configs.get(ctx.guild.id, ctx.guild.name)
        if config.social_gifs_enabled:
            media = await self._media(action)
            if media:
                embed.set_image(url=media)
        embed.set_footer(text=f"N.A.V.I // {action.upper()}")
        await send_response(ctx, embed=embed)

    async def _interaction(self, ctx: commands.Context, action: str, user: discord.Member) -> None:
        if not await self._guard(ctx):
            return
        if user.bot and self.bot.user and user.id != self.bot.user.id:
            await send_response(ctx, "El objetivo no admite interacciones.", ephemeral=True)
            return
        if user.id == ctx.author.id:
            await send_response(ctx, "No puedes dirigirte esa interacción a ti mismo/a.", ephemeral=True)
            return
        if await is_blocked(ctx.guild.id, ctx.author.id, user.id):
            await send_response(ctx, "Interacción bloqueada por las preferencias sociales.", ephemeral=True)
            return
        preference = await get_preference(ctx.guild.id, user.id)
        if not preference.interactions_enabled:
            await send_response(ctx, "El usuario ha desactivado las interacciones.", ephemeral=True)
            return
        async with AsyncSessionLocal() as session:
            row = await session.get(InteractionStat, (ctx.guild.id, ctx.author.id, user.id, action))
            if row is None:
                row = InteractionStat(guild_id=ctx.guild.id, actor_id=ctx.author.id, target_id=user.id, action=action)
                session.add(row)
            row.count += 1
            await session.commit()
            count = row.count
        text = INTERACTION_TEXT[action].format(actor=ctx.author.mention, target=user.mention)
        embed = discord.Embed(description=text, color=discord.Color.from_rgb(120, 92, 180))
        config = await self.bot.configs.get(ctx.guild.id, ctx.guild.name)
        if config.social_gifs_enabled:
            media = await self._media(action)
            if media:
                embed.set_image(url=media)
        embed.set_footer(text=f"Interacciones registradas: {count}")
        await send_response(ctx, embed=embed)

    @commands.hybrid_group(name="act", description="Acciones personales de roleplay.", invoke_without_command=True)
    async def act(self, ctx: commands.Context) -> None:
        await send_response(ctx, "Acciones: dance, laugh, cry, facepalm, sleep, think, sing, cook, eat, run, jump, wink, smug, pout, clap.", ephemeral=True)

    @commands.hybrid_group(name="react", description="Reacciones personales.", invoke_without_command=True)
    async def react(self, ctx: commands.Context) -> None:
        await send_response(ctx, "Reacciones: happy, sad, angry, blush, bored, confused, scared, smile, shrug, thinking, baka, disgust, scream, peek, wasted.", ephemeral=True)

    @commands.hybrid_group(name="interact", description="Interacciones dirigidas a otro usuario.", invoke_without_command=True)
    async def interact(self, ctx: commands.Context) -> None:
        await send_response(ctx, "Interacciones: hug, kiss, pat, cuddle, highfive, handhold, feed, bite, poke, bonk, slap, heal, greet, bye, cheeks.", ephemeral=True)

    @act.command(name="dance", description="Acción de roleplay: dance.")
    async def act_dance(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "dance", ACT_TEXT)

    @act.command(name="laugh", description="Acción de roleplay: laugh.")
    async def act_laugh(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "laugh", ACT_TEXT)

    @act.command(name="cry", description="Acción de roleplay: cry.")
    async def act_cry(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "cry", ACT_TEXT)

    @act.command(name="facepalm", description="Acción de roleplay: facepalm.")
    async def act_facepalm(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "facepalm", ACT_TEXT)

    @act.command(name="sleep", description="Acción de roleplay: sleep.")
    async def act_sleep(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "sleep", ACT_TEXT)

    @act.command(name="think", description="Acción de roleplay: think.")
    async def act_think(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "think", ACT_TEXT)

    @act.command(name="sing", description="Acción de roleplay: sing.")
    async def act_sing(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "sing", ACT_TEXT)

    @act.command(name="cook", description="Acción de roleplay: cook.")
    async def act_cook(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "cook", ACT_TEXT)

    @act.command(name="eat", description="Acción de roleplay: eat.")
    async def act_eat(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "eat", ACT_TEXT)

    @act.command(name="run", description="Acción de roleplay: run.")
    async def act_run(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "run", ACT_TEXT)

    @act.command(name="jump", description="Acción de roleplay: jump.")
    async def act_jump(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "jump", ACT_TEXT)

    @act.command(name="wink", description="Acción de roleplay: wink.")
    async def act_wink(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "wink", ACT_TEXT)

    @act.command(name="smug", description="Acción de roleplay: smug.")
    async def act_smug(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "smug", ACT_TEXT)

    @act.command(name="pout", description="Acción de roleplay: pout.")
    async def act_pout(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "pout", ACT_TEXT)

    @act.command(name="clap", description="Acción de roleplay: clap.")
    async def act_clap(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "clap", ACT_TEXT)

    @react.command(name="happy", description="Reacción: happy.")
    async def react_happy(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "happy", REACT_TEXT)

    @react.command(name="sad", description="Reacción: sad.")
    async def react_sad(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "sad", REACT_TEXT)

    @react.command(name="angry", description="Reacción: angry.")
    async def react_angry(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "angry", REACT_TEXT)

    @react.command(name="blush", description="Reacción: blush.")
    async def react_blush(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "blush", REACT_TEXT)

    @react.command(name="bored", description="Reacción: bored.")
    async def react_bored(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "bored", REACT_TEXT)

    @react.command(name="confused", description="Reacción: confused.")
    async def react_confused(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "confused", REACT_TEXT)

    @react.command(name="scared", description="Reacción: scared.")
    async def react_scared(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "scared", REACT_TEXT)

    @react.command(name="smile", description="Reacción: smile.")
    async def react_smile(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "smile", REACT_TEXT)

    @react.command(name="shrug", description="Reacción: shrug.")
    async def react_shrug(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "shrug", REACT_TEXT)

    @react.command(name="thinking", description="Reacción: thinking.")
    async def react_thinking(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "thinking", REACT_TEXT)

    @react.command(name="baka", description="Reacción: baka.")
    async def react_baka(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "baka", REACT_TEXT)

    @react.command(name="disgust", description="Reacción: disgust.")
    async def react_disgust(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "disgust", REACT_TEXT)

    @react.command(name="scream", description="Reacción: scream.")
    async def react_scream(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "scream", REACT_TEXT)

    @react.command(name="peek", description="Reacción: peek.")
    async def react_peek(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "peek", REACT_TEXT)

    @react.command(name="wasted", description="Reacción: wasted.")
    async def react_wasted(self, ctx: commands.Context) -> None:
        await self._self_action(ctx, "wasted", REACT_TEXT)

    @interact.command(name="hug", description="Interacción: hug.")
    async def interact_hug(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._interaction(ctx, "hug", user)

    @interact.command(name="kiss", description="Interacción: kiss.")
    async def interact_kiss(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._interaction(ctx, "kiss", user)

    @interact.command(name="pat", description="Interacción: pat.")
    async def interact_pat(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._interaction(ctx, "pat", user)

    @interact.command(name="cuddle", description="Interacción: cuddle.")
    async def interact_cuddle(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._interaction(ctx, "cuddle", user)

    @interact.command(name="highfive", description="Interacción: highfive.")
    async def interact_highfive(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._interaction(ctx, "highfive", user)

    @interact.command(name="handhold", description="Interacción: handhold.")
    async def interact_handhold(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._interaction(ctx, "handhold", user)

    @interact.command(name="feed", description="Interacción: feed.")
    async def interact_feed(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._interaction(ctx, "feed", user)

    @interact.command(name="bite", description="Interacción: bite.")
    async def interact_bite(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._interaction(ctx, "bite", user)

    @interact.command(name="poke", description="Interacción: poke.")
    async def interact_poke(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._interaction(ctx, "poke", user)

    @interact.command(name="bonk", description="Interacción: bonk.")
    async def interact_bonk(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._interaction(ctx, "bonk", user)

    @interact.command(name="slap", description="Interacción: slap.")
    async def interact_slap(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._interaction(ctx, "slap", user)

    @interact.command(name="heal", description="Interacción: heal.")
    async def interact_heal(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._interaction(ctx, "heal", user)

    @interact.command(name="greet", description="Interacción: greet.")
    async def interact_greet(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._interaction(ctx, "greet", user)

    @interact.command(name="bye", description="Interacción: bye.")
    async def interact_bye(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._interaction(ctx, "bye", user)

    @interact.command(name="cheeks", description="Interacción: cheeks.")
    async def interact_cheeks(self, ctx: commands.Context, user: discord.Member) -> None:
        await self._interaction(ctx, "cheeks", user)


async def setup(bot: NaviBot) -> None:
    await bot.add_cog(RoleplayCog(bot))
