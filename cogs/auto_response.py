import logging
import os

import discord
from discord.ext import commands

import visual

log = logging.getLogger("alt.auto_response")

# o link do CDN do Discord carrega assinatura `ex=`/`hm=` e expira,
# virando 404 depois de um tempo. Configurar por env permite trocar sem
# deploy. Vazio = repost desativado.
REPOST_GIF = os.getenv("REPOST_GIF", "")
REPOST_GIF = REPOST_GIF.strip()


class AutoResponse(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        if not REPOST_GIF:
            log.info("REPOST_GIF nao definido — repost automatico desativado")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ignora mensagens do próprio bot
        if message.author == self.bot.user:
            return

        # responde W com um emote da lista (personalidade do bot).
        if message.content.strip().lower() == "w":
            await message.channel.send(f"W {visual.emote()}")

        # repost do gif automaticamente
        if REPOST_GIF and REPOST_GIF in message.content:
            await message.channel.send(REPOST_GIF)


async def setup(bot):
    await bot.add_cog(AutoResponse(bot))
