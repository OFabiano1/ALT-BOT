# isso aq e tudo de voz, versao leve: entrar, tocar, sair.
# sem banco, sem auto-rejoin, sem vigia. caiu? da >call de novo.

import asyncio
import logging
import time
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

import visual

log = logging.getLogger("alt.voz")

# audio de boas-vindas. caminho absoluto pra nao depender
# de onde o app foi aberto.
AUDIO_OI = Path(__file__).parent.parent / "kkkiaimen.mp3"

# um oi a cada 30s por servidor: sem isso entra-e-sai vira spam.
OI_COOLDOWN = 30

# a voz do host vive quebrada: o disconnect do discord.py espera
# ate 60s pela confirmacao. timeout curto pra nunca congelar comando.
TIMEOUT_SAIR = 8
TIMEOUT_ENTRAR = 30
TIMEOUT_MOVER = 20


async def _desconectar(vc, onde: str) -> bool:
    """desconecta com timeout curto. True se ok."""
    try:
        await asyncio.wait_for(vc.disconnect(force=True), timeout=TIMEOUT_SAIR)
        return True
    except asyncio.TimeoutError:
        log.warning("%s: disconnect travou, seguindo mesmo assim", onde)
        return False
    except Exception:
        log.exception("%s: disconnect falhou", onde)
        return False


def _fonte_oi():
    """audio do oi em opus direto: sem re-encode, sem libopus."""
    return discord.FFmpegOpusAudio(str(AUDIO_OI), bitrate=64)


def _depois_oi(erro):
    # o ffmpeg roda em thread propria: erro depois do play so aparece aqui.
    if erro:
        log.error("audio de boas-vindas falhou no meio: %s", erro)


def _tocar_oi(vc) -> str | None:
    """tenta tocar o oi. retorna o erro amigavel ou None se tocou."""
    if vc is None:
        return "não estou em call — me chama com `>call` primeiro!"
    if not vc.is_connected():
        log.warning("voice_client existe mas sem conexao — voz caiu no host")
        return "minha voz caiu — manda `>sair` e `>call` de novo!"
    if vc.is_playing():
        return "já tô tocando algo, calma!"
    if not AUDIO_OI.exists():
        log.warning("audio de boas-vindas nao encontrado: %s", AUDIO_OI)
        return "o mp3 sumiu do deploy!"
    try:
        vc.play(_fonte_oi(), after=_depois_oi)
        return None
    except discord.ClientException as erro:
        # ffmpeg ausente vem como ClientException, nao FileNotFoundError.
        if "was not found" in str(erro):
            log.error("ffmpeg nao encontrado no host — sem audio na call")
            return "ffmpeg nao encontrado no host — sem audio na call."
        log.warning("voz ocupada na hora do oi: %s", erro)
        return "a voz tá ocupada, tenta de novo em uns segundos!"
    except Exception:
        log.exception("nao consegui tocar o oi")
        return "deu ruim tentando tocar o oi!"


class Voz(commands.Cog, name="Voz"):
    """entra, toca o oi, sai. nada mais."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._ultimo_oi: dict[int, float] = {}

    # ─── boas-vindas ───
    @commands.Cog.listener()
    async def on_voice_state_update(self, membro, antes, depois):
        # ignora bot.
        if membro.bot:
            return
        # so conta entrar numa call: sair ou mutar nao conta.
        if depois.channel is None:
            return
        if antes.channel is not None and antes.channel.id == depois.channel.id:
            return
        vc = membro.guild.voice_client
        if vc is None or not vc.is_connected():
            return
        # so conta entrar na mesma call do bot.
        if depois.channel.id != vc.channel.id:
            return
        agora = time.monotonic()
        if agora - self._ultimo_oi.get(membro.guild.id, 0) < OI_COOLDOWN:
            return
        erro = _tocar_oi(vc)
        if erro is None:
            self._ultimo_oi[membro.guild.id] = agora
            log.info("oi pra %s na call", membro.display_name)

    # ─── >call ───
    @commands.command(name="call")
    async def call(self, ctx: commands.Context):
        """entra na call de voz que você está."""
        try:
            voz = ctx.author.voice
            if voz is None or voz.channel is None:
                await ctx.send("você precisa estar em uma call de voz para eu entrar!")
                return

            canal = voz.channel

            permissoes = canal.permissions_for(ctx.guild.me)
            if not permissoes.connect:
                await ctx.send(
                    f"não tenho permissão de **conectar** no canal **{canal.name}**!"
                )
                return
            if not permissoes.speak:
                await ctx.send(
                    f"não tenho permissão de **falar** no canal **{canal.name}**!"
                )
                return

            vc = ctx.voice_client
            if vc is not None and not vc.is_connected():
                await _desconectar(vc, ">call")
                vc = None

            try:
                if vc is not None:
                    await asyncio.wait_for(vc.move_to(canal), timeout=TIMEOUT_MOVER)
                else:
                    await asyncio.wait_for(canal.connect(), timeout=TIMEOUT_ENTRAR)
            except asyncio.TimeoutError:
                log.warning(">call: voz demorou demais")
                await ctx.send(
                    "a voz tá demorando pra responder (rede do host tá lenta). "
                    "tenta de novo em uns segundos!"
                )
                return
            await ctx.send(f"tô na call **{canal.name}**!")
        except Exception as erro:
            log.exception("falha ao entrar na call")
            await ctx.send(f"não consegui entrar na call: `{type(erro).__name__}`")

    # ─── /call ───
    @app_commands.command(name="call", description="me chama pra call de voz que você tá.")
    async def call_slash(self, interaction: discord.Interaction):
        """versão slash do >call."""
        membro = interaction.user
        if (
            interaction.guild is None
            or not isinstance(membro, discord.Member)
            or membro.voice is None
            or membro.voice.channel is None
        ):
            await interaction.response.send_message(
                "você precisa estar em uma call de voz para eu entrar!", ephemeral=True
            )
            return
        canal = membro.voice.channel
        try:
            permissoes = canal.permissions_for(interaction.guild.me)
            if not permissoes.connect:
                await interaction.response.send_message(
                    f"não tenho permissão de **conectar** no canal **{canal.name}**!",
                    ephemeral=True,
                )
                return
            if not permissoes.speak:
                await interaction.response.send_message(
                    f"não tenho permissão de **falar** no canal **{canal.name}**!",
                    ephemeral=True,
                )
                return
            vc = interaction.guild.voice_client
            if vc is not None and not vc.is_connected():
                await _desconectar(vc, "/call")
                vc = None
            try:
                if vc is not None:
                    await asyncio.wait_for(vc.move_to(canal), timeout=TIMEOUT_MOVER)
                else:
                    await asyncio.wait_for(canal.connect(), timeout=TIMEOUT_ENTRAR)
            except asyncio.TimeoutError:
                log.warning("/call: voz demorou demais")
                texto = (
                    "a voz tá demorando pra responder (rede do host tá lenta). "
                    "tenta de novo em uns segundos!"
                )
                try:
                    if interaction.response.is_done():
                        await interaction.followup.send(texto, ephemeral=True)
                    else:
                        await interaction.response.send_message(texto, ephemeral=True)
                except discord.DiscordException:
                    pass
                return
            await interaction.response.send_message(f"tô na call **{canal.name}**!")
        except Exception as erro:
            log.exception("falha ao entrar na call (slash)")
            texto = f"não consegui entrar na call: `{type(erro).__name__}`"
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(texto, ephemeral=True)
                else:
                    await interaction.response.send_message(texto, ephemeral=True)
            except discord.DiscordException:
                pass

    # ─── >sair ───
    @commands.command(name="sair")
    async def sair(self, ctx: commands.Context):
        """sai da call de voz."""
        vc = ctx.voice_client
        if vc is None:
            await ctx.send("não estou em call")
            return
        await _desconectar(vc, ">sair")
        await ctx.send("saí da call!")

    # ─── /sair ───
    @app_commands.command(name="sair", description="tira o bot da call de voz.")
    async def sair_slash(self, interaction: discord.Interaction):
        """versão slash do >sair."""
        vc = interaction.guild.voice_client if interaction.guild else None
        if vc is None:
            await interaction.response.send_message("não estou em call", ephemeral=True)
            return
        await _desconectar(vc, "/sair")
        await interaction.response.send_message("saí da call!")

    # ─── >oi ───
    @commands.command(name="oi")
    async def oi(self, ctx: commands.Context):
        """toca o audio de boas-vindas na call atual."""
        erro = _tocar_oi(ctx.voice_client)
        await ctx.send(f"{visual.AXOLOTL} oi!" if erro is None else erro)

    # ─── /oi ───
    @app_commands.command(name="oi", description="toca o audio de boas-vindas na call atual.")
    async def oi_slash(self, interaction: discord.Interaction):
        """versão slash do >oi."""
        vc = interaction.guild.voice_client if interaction.guild else None
        erro = _tocar_oi(vc)
        if erro is None:
            await interaction.response.send_message(f"{visual.AXOLOTL} oi!")
        else:
            await interaction.response.send_message(erro, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Voz(bot))
