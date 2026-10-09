# isso aq conta os dias pro halloween todo dia 00:00.
# manda msg no chat + atualiza o status da call via http direto
# (`bot.http.edit_voice_channel_status`, o discord.py nao tem wrapper).
# se o status falhar, loga e segue — a msg do dia continua saindo.

import datetime
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands, tasks

import data
import visual

log = logging.getLogger("alt.halloween")

TEXT_CHANNEL_ID = data.env_int("HALLOWEEN_TEXT_CHANNEL_ID", 1058335767274995752)
VOICE_CHANNEL_ID = data.env_int("HALLOWEEN_VOICE_CHANNEL_ID", 1310398751575113758)

# UTC-3 fixo. ZoneInfo("America/Sao_Paulo") precisaria do pacote `tzdata`
# no Windows — sem DST desde 2019, o offset fixo é equivalente e sem dep nova.
TZ = datetime.timezone(datetime.timedelta(hours=-3), name="America/Sao_Paulo")
MEIA_NOITE = datetime.time(hour=0, minute=0, tzinfo=TZ)


def proximo_halloween(hoje: datetime.date) -> datetime.date:
    """31/out deste ano, ou do ano que vem se já passou."""
    ano = hoje.year
    alvo = datetime.date(ano, 10, 31)
    if hoje > alvo:
        alvo = datetime.date(ano + 1, 10, 31)
    return alvo


def dias_faltando(hoje: datetime.date) -> int:
    return (proximo_halloween(hoje) - hoje).days


def texto_status(dias: int) -> str:
    if dias == 0:
        return "🎃💚 feliz halloween! é hoje!"
    if dias == 1:
        return "🎃 é amanhã! falta 1 dia pro halloween"
    return f"🎃 faltam {dias} dias pro halloween"


def texto_mensagem(dias: int) -> str:
    if dias == 0:
        return f"🎃 {visual.AXOLOTL} É HOJE! feliz halloween, galera! 💚"
    if dias == 1:
        return f"🎃 {visual.AXOLOTL} é amanhã! falta **1 dia** pro halloween... preparem as fantasias. 💚"
    return f"🎃 {visual.AXOLOTL} faltam **{dias} dias** pro halloween! 💚"


class Halloween(commands.Cog, name="Halloween"):
    """mensagem diária + status da call com o countdown."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not TEXT_CHANNEL_ID or not VOICE_CHANNEL_ID:
            log.warning(
                "HALLOWEEN_TEXT/VOICE_CHANNEL_ID nao definidos — countdown inativo"
            )

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.countdown.is_running():
            self.countdown.start()
            log.info("halloween: loop diario 00:00 iniciado")

    async def _enviar_mensagem(self, dias: int) -> bool:
        """manda o embed do countdown no chat. True se enviou."""
        if not TEXT_CHANNEL_ID:
            return False
        try:
            canal = self.bot.get_channel(TEXT_CHANNEL_ID)
            if canal is None:
                canal = await self.bot.fetch_channel(TEXT_CHANNEL_ID)
            # dia 31: verde festa. resto do ano: roxo em foco.
            festa = dias == 0
            embed = discord.Embed(
                title="🎃 É HOJE! feliz halloween 💚" if festa else "🎃 countdown pro halloween 💚",
                description=texto_mensagem(dias),
                color=visual.SUCCESS if festa else visual.PRIMARY,
            )
            embed.set_footer(text=visual.FOOTER)
            await canal.send(embed=embed)
            return True
        except Exception:
            log.exception("halloween: falha ao enviar mensagem")
            return False

    async def _atualizar_status(self, dias: int) -> bool:
        """atualiza o voice channel status da call. True se ok.

        Não é o nome do canal — é o status (PUT /voice-status).
        """
        if not VOICE_CHANNEL_ID:
            return False
        try:
            await self.bot.http.edit_voice_channel_status(
                texto_status(dias),
                channel_id=VOICE_CHANNEL_ID,
            )
            return True
        except Exception:
            log.exception("halloween: falha ao atualizar status da call")
            return False

    @tasks.loop(time=MEIA_NOITE)
    async def countdown(self):
        hoje = datetime.datetime.now(TZ).date()
        dias = dias_faltando(hoje)
        log.info("halloween: %d dia(s) faltando (%s)", dias, hoje.isoformat())

        # 1. mensagem no chat
        await self._enviar_mensagem(dias)

        # 2. status da call
        await self._atualizar_status(dias)

    @countdown.before_loop
    async def before_countdown(self):
        await self.bot.wait_until_ready()

    # ─── >halloween ───
    @commands.command(name="halloween")
    async def halloween(self, ctx: commands.Context):
        """🎃 mostra o countdown e atualiza o status da call na hora."""
        hoje = datetime.datetime.now(TZ).date()
        dias = dias_faltando(hoje)
        await ctx.send(texto_mensagem(dias))
        if VOICE_CHANNEL_ID and not await self._atualizar_status(dias):
            await ctx.send(
                "aviso: a mensagem foi, mas o status da call não atualizou — "
                "confere se eu tenho a permissão **Voice Channel Status** na call."
            )

    # ─── /halloween ───
    @app_commands.command(name="halloween", description="🎃 countdown pro halloween + atualiza a call.")
    async def halloween_slash(self, interaction: discord.Interaction):
        """versão slash do >halloween."""
        hoje = datetime.datetime.now(TZ).date()
        dias = dias_faltando(hoje)
        await interaction.response.send_message(texto_mensagem(dias))
        if VOICE_CHANNEL_ID and not await self._atualizar_status(dias):
            await interaction.followup.send(
                "aviso: a mensagem foi, mas o status da call não atualizou — "
                "confere se eu tenho a permissão **Voice Channel Status** na call.",
                ephemeral=True,
            )

    def cog_unload(self):
        if self.countdown.is_running():
            self.countdown.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(Halloween(bot))
