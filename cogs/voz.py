# isso aq e tudo de voz: entrar, sair, oi manual e boas-vindas.
# >call fixa a call no banco, >sair solta. sem >sair ele nao sai:
# se cair ou for kickado, volta sozinho. restart nao tira.

import asyncio
import logging
import time
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

import data
import visual

log = logging.getLogger("alt.voz")

# audio de boas-vindas. caminho absoluto pra nao depender
# de onde o app foi aberto.
AUDIO_OI = Path(__file__).parent.parent / "kkkiaimen.mp3"

# um oi a cada 30s por servidor: sem isso entra-e-sai vira spam.
OI_COOLDOWN = 30


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
        vc.play(discord.FFmpegPCMAudio(str(AUDIO_OI)), after=_depois_oi)
        return None
    except FileNotFoundError:
        log.error("ffmpeg nao encontrado no host — sem audio na call")
        return "ffmpeg nao encontrado no host — sem audio na call."
    except Exception:
        log.exception("nao consegui tocar o oi")
        return "deu ruim tentando tocar o oi!"


def _depois_oi(erro):
    # o ffmpeg roda em thread propria: erro depois do play so aparece aqui.
    if erro:
        log.error("audio de boas-vindas falhou no meio: %s", erro)


class Voz(commands.Cog, name="Voz"):
    """call fixa, oi manual e boas-vindas pra quem chega."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._ultimo_oi: dict[int, float] = {}

    # ─── volta sozinho ───
    @commands.Cog.listener()
    async def on_ready(self):
        # volta pras calls fixadas (sobrevive a restart e queda).
        for guild in self.bot.guilds:
            canal_id = await asyncio.to_thread(data.voz_fixa, guild.id)
            if canal_id is None:
                continue
            await self._conectar_limpo(guild, canal_id, "voltei pra call fixada")

    @commands.Cog.listener()
    async def on_voice_state_update(self, membro, antes, depois):
        # queda do proprio bot: volta pra fixada.
        if self.bot.user is not None and membro.id == self.bot.user.id:
            if depois.channel is not None or antes.channel is None:
                return
            canal_id = await asyncio.to_thread(data.voz_fixa, membro.guild.id)
            if canal_id is None:
                return
            log.info("cai da call, voltando pra fixada %d", canal_id)
            asyncio.create_task(self._voltar_call(membro.guild.id, canal_id))
            return
        # boas-vindas: alguem entrou na call onde o bot esta.
        await self._oi_quem_chegou(membro, antes, depois)

    async def _conectar_limpo(self, guild: discord.Guild, canal_id: int, msg_ok: str):
        """limpa voz morta e conecta. False se falhar."""
        vc = guild.voice_client
        if vc is not None and not vc.is_connected():
            try:
                await vc.disconnect(force=True)
            except Exception:
                pass
            vc = None
            log.info("limpei voz morta")
        if vc is not None:
            return True
        try:
            canal = guild.get_channel(canal_id)
            if canal is None:
                canal = await self.bot.fetch_channel(canal_id)
            await canal.connect()
            log.info("%s %d", msg_ok, canal_id)
            return True
        except Exception:
            log.exception("nao consegui conectar na call %d", canal_id)
            return False

    async def _voltar_call(self, guild_id: int, channel_id: int, tentativas: int = 3):
        # espera um pouco pra nao brigar com queda rapida seguida.
        await asyncio.sleep(5)
        for _ in range(tentativas):
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                return
            vc = guild.voice_client
            if vc is not None and vc.is_connected():
                return
            if await self._conectar_limpo(guild, channel_id, "voltei pra call fixada"):
                return
            await asyncio.sleep(10)

    # ─── boas-vindas ───
    async def _oi_quem_chegou(self, membro, antes, depois):
        # ignora bot (senao um bot entrando vira festa infinita).
        if membro.bot:
            return
        # so conta entrar numa call: sair ou mutar nao conta.
        if depois.channel is None:
            return
        if antes.channel is not None and antes.channel.id == depois.channel.id:
            return
        vc = membro.guild.voice_client
        if vc is None or not vc.is_connected():
            log.info("%s entrou na call mas nao estou la — sem oi", membro.display_name)
            return
        # so conta entrar na mesma call do bot.
        if depois.channel.id != vc.channel.id:
            return
        agora = time.monotonic()
        if agora - self._ultimo_oi.get(membro.guild.id, 0) < OI_COOLDOWN:
            return
        if vc.is_playing():
            return
        if not AUDIO_OI.exists():
            log.warning("audio de boas-vindas nao encontrado: %s", AUDIO_OI)
            return
        try:
            vc.play(discord.FFmpegPCMAudio(str(AUDIO_OI)), after=_depois_oi)
            self._ultimo_oi[membro.guild.id] = agora
            log.info("oi pra %s na call", membro.display_name)
        except FileNotFoundError:
            log.error("ffmpeg nao encontrado no host — sem audio na call")
        except Exception:
            log.exception("nao consegui tocar o audio de boas-vindas")

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
                try:
                    await vc.disconnect(force=True)
                except Exception:
                    pass
                vc = None
                log.info("limpei voz morta no >call")

            if vc is not None:
                await vc.move_to(canal)
            else:
                await canal.connect()
            await asyncio.to_thread(data.fixar_voz, ctx.guild.id, canal.id)
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
                try:
                    await vc.disconnect(force=True)
                except Exception:
                    pass
                vc = None
                log.info("limpei voz morta no /call")
            if vc is not None:
                await vc.move_to(canal)
            else:
                await canal.connect()
            await asyncio.to_thread(data.fixar_voz, interaction.guild.id, canal.id)
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
        await asyncio.to_thread(data.soltar_voz, ctx.guild.id)
        try:
            await vc.disconnect(force=True)
        except Exception:
            log.exception("sair: disconnect falhou, banco ja solto")
        await ctx.send("saí da call!")

    # ─── /sair ───
    @app_commands.command(name="sair", description="tira o bot da call de voz.")
    async def sair_slash(self, interaction: discord.Interaction):
        """versão slash do >sair."""
        vc = interaction.guild.voice_client if interaction.guild else None
        if vc is None:
            await interaction.response.send_message("não estou em call", ephemeral=True)
            return
        await asyncio.to_thread(data.soltar_voz, interaction.guild.id)
        try:
            await vc.disconnect(force=True)
        except Exception:
            log.exception("sair: disconnect falhou, banco ja solto")
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
