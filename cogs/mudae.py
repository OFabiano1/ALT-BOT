# isso aq avisa quando os rolls do mudae voltam.
# fluxo: alguem roleta `$m`/`$wa` -> guarda pendente 15s ->
# o mudae responde com `rolls left` + tempo -> agenda o aviso.
# so agenda quando zerou os rolls. salvo no banco pra sobreviver a `>restart`.

import asyncio
import logging
import os
import re
import time

import discord
from discord import app_commands
from discord.ext import commands

import visual
import data

log = logging.getLogger("alt.mudae")

MUDAE_BOT_ID = data.env_int("MUDAE_BOT_ID", 432610292342587392)
DEFAULT_MINUTES = max(1, data.env_int("MUDAE_DEFAULT_MINUTES", 60))

# comandos do Mudae que consomem roll. `$tu`, `$daily`, `$vote`, `$dk`
# etc. não entram — só os de roletar waifu/husbando.
ROLL_RE = re.compile(
    r"^\$(m|ma|mc|mg|mi|mm|w|wa|wg|h|ha|hg|anime|manga|game)\b",
    re.IGNORECASE,
)
MENTION_RE = re.compile(r"<@!?(\d+)>")
ROLLS_LEFT_RE = re.compile(r"(\d+)\s*rolls?\s*(?:left|remaining|restantes?)", re.IGNORECASE)
RESET_HM_RE = re.compile(r"(\d+)\s*h(?:ours?|rs?|oras?)?\s*(\d+)?\s*min", re.IGNORECASE)
RESET_MIN_RE = re.compile(r"(\d+)\s*min", re.IGNORECASE)

PENDENTE_JANELA = 15  # segundos esperando a resposta do Mudae
MAX_MINUTOS = 180


def _texto_mudae(message: discord.Message) -> str:
    """junta conteúdo + embeds em um texto só para o parse."""
    partes = [message.content or ""]
    for emb in message.embeds:
        partes.append(emb.title or "")
        partes.append(emb.description or "")
        if emb.footer and emb.footer.text:
            partes.append(emb.footer.text)
        for f in emb.fields:
            partes.append(f.name or "")
            partes.append(f.value or "")
    return "\n".join(p for p in partes if p)


def parse_mudae(texto: str) -> tuple[int | None, int | None]:
    """extrai (rolls_left, minutos_reset) do texto do Mudae.

    Retorna minutos=None quando não deve agendar (ainda tem rolls ou
    sem tempo parseável).
    """
    baixo = texto.lower()

    rolls_left: int | None = None
    m = ROLLS_LEFT_RE.search(texto)
    if m:
        try:
            rolls_left = int(m.group(1))
        except ValueError:
            rolls_left = None

    # ainda tem rolls → sem reminder ("quando acabar" é a regra).
    if rolls_left is not None and rolls_left > 0:
        return rolls_left, None

    # só mensagem de roll agenda. Sem "roll" no texto (ex: claims,
    # daily, vote, kakera) não agenda — evita falso-positivo.
    if "roll" not in baixo:
        return rolls_left, None

    minutos: int | None = None
    hm = RESET_HM_RE.search(texto)
    if hm:
        try:
            h = int(hm.group(1))
            mi = int(hm.group(2)) if hm.group(2) else 0
            minutos = h * 60 + mi
        except ValueError:
            minutos = None
    else:
        mm = RESET_MIN_RE.search(texto)
        if mm:
            try:
                minutos = int(mm.group(1))
            except ValueError:
                minutos = None

    if minutos is not None:
        minutos = max(1, min(MAX_MINUTOS, minutos))
    return rolls_left, minutos


class Mudae(commands.Cog, name="Mudae"):
    """marca quem roletou quando os rolls voltarem."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.timers: dict[int, asyncio.Task] = {}
        # user_id -> (channel_id, timestamp)
        self.pendentes: dict[int, tuple[int, float]] = {}

    @commands.Cog.listener()
    async def on_ready(self):
        # reagenda reminders que sobreviveram a restart.
        try:
            todos = await asyncio.to_thread(data.listar_mudae)
        except Exception:
            log.exception("falha ao carregar reminders do Mudae")
            return
        agora = time.time()
        for user_id, channel_id, guild_id, expires_at in todos:
            delay = expires_at - agora
            if delay <= 0:
                await asyncio.to_thread(data.remover_mudae, user_id)
                continue
            self.timers[user_id] = asyncio.create_task(
                self._dormir_e_avisar(user_id, channel_id, delay / 60)
            )
        if todos:
            log.info("mudae: %d reminder(s) reagendado(s)", len(todos))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return

        # 1. humano roletando — guarda pendente.
        if not message.author.bot:
            if ROLL_RE.match((message.content or "").strip()):
                self.pendentes[message.author.id] = (message.channel.id, time.time())
                self.bot.loop.create_task(
                    self._fallback(message.author.id, message.channel.id, message.guild.id)
                )
            return

        # 2. resposta do Mudae — extrai tempo e agenda.
        if message.author.id != MUDAE_BOT_ID:
            return
        await self._tratar_resposta_mudae(message)

    async def _tratar_resposta_mudae(self, message: discord.Message):
        texto = _texto_mudae(message)
        if not texto.strip():
            return
        rolls_left, minutos = parse_mudae(texto)
        if minutos is None:
            return

        dono = await self._achar_dono(message)
        if dono is None:
            log.debug("mudae: resposta sem dono identificável")
            return

        self.pendentes.pop(dono, None)
        await self.agendar(dono, message.channel.id, message.guild.id, minutos)

    async def _achar_dono(self, message: discord.Message) -> int | None:
        # via reply (Mudae responde em thread/reply do comando).
        try:
            ref = message.reference
            if ref and ref.message_id:
                original = await message.channel.fetch_message(ref.message_id)
                if original and not original.author.bot:
                    return original.author.id
        except Exception:
            pass

        # via mention direta na resposta.
        for membro in message.mentions:
            if not membro.bot:
                return membro.id

        # via <@id> dentro do embed.
        m = MENTION_RE.search(_texto_mudae(message))
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass

        # fallback: pendente mais recente deste canal (15s).
        agora = time.time()
        melhor: int | None = None
        melhor_ts = 0.0
        for uid, (cid, ts) in self.pendentes.items():
            if cid == message.channel.id and agora - ts <= PENDENTE_JANELA and ts > melhor_ts:
                melhor, melhor_ts = uid, ts
        return melhor

    async def _fallback(self, user_id: int, channel_id: int, guild_id: int):
        """se o Mudae não respondeu com tempo parseável em 15s, usa o default."""
        await asyncio.sleep(PENDENTE_JANELA)
        if user_id not in self.pendentes:
            return  # já tratado pela resposta do Mudae
        cid, _ = self.pendentes.pop(user_id)
        if user_id in self.timers and not self.timers[user_id].done():
            return  # já agendado
        log.info("mudae: sem tempo no embed, usando default %dmin p/ %d", DEFAULT_MINUTES, user_id)
        await self.agendar(user_id, cid, guild_id, DEFAULT_MINUTES)

    async def agendar(self, user_id: int, channel_id: int, guild_id: int, minutos: int):
        """agenda (ou reagenda) o aviso. Um ativo por usuário."""
        antiga = self.timers.pop(user_id, None)
        if antiga and not antiga.done():
            antiga.cancel()

        expires_at = time.time() + minutos * 60
        try:
            await asyncio.to_thread(data.salvar_mudae, user_id, channel_id, guild_id, expires_at)
        except Exception:
            log.exception("falha ao salvar reminder do Mudae")
            return

        self.timers[user_id] = asyncio.create_task(
            self._dormir_e_avisar(user_id, channel_id, minutos)
        )
        log.info("mudae: reminder %dmin p/ %d no canal %d", minutos, user_id, channel_id)

    async def _dormir_e_avisar(self, user_id: int, channel_id: int, minutos: float):
        try:
            await asyncio.sleep(max(1, minutos * 60))
            canal = self.bot.get_channel(channel_id)
            if canal is None:
                try:
                    canal = await self.bot.fetch_channel(channel_id)
                except Exception:
                    canal = None
            if canal is not None:
                embed = discord.Embed(
                    title=f"{visual.AXOLOTL} rolls de volta!",
                    description=f"<@{user_id}> seus rolls do Mudae voltaram!",
                    color=visual.SECONDARY,
                )
                embed.set_footer(text=visual.FOOTER)
                await canal.send(embed=embed)
            else:
                log.warning("mudae: canal %d sumiu, dropando reminder %d", channel_id, user_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("falha ao avisar reminder do Mudae")
        finally:
            try:
                await asyncio.to_thread(data.remover_mudae, user_id)
            except Exception:
                pass
            self.timers.pop(user_id, None)
            self.pendentes.pop(user_id, None)

    # ─── >mudae [min] ───
    @commands.command(name="mudae")
    async def mudae_manual(self, ctx: commands.Context, minutos: int = 0):
        """agenda aviso manual. ex: `>mudae 7` te marca em 7 min."""
        if minutos <= 0 or minutos > MAX_MINUTOS:
            await ctx.send(
                f"{visual.AXOLOTL} uso: `>mudae <minutos>` (1–{MAX_MINUTOS}). "
                f"o auto-reminder já pega seus `$m`/`$wa` sozinho."
            )
            return
        await self.agendar(ctx.author.id, ctx.channel.id, ctx.guild.id if ctx.guild else 0, minutos)
        await ctx.send(
            f"{visual.AXOLOTL} {ctx.author.mention} te marco em **{minutos} min**!"
        )

    @commands.command(name="mudae_stop")
    async def mudae_stop(self, ctx: commands.Context):
        """cancela seu reminder do Mudae."""
        tarefa = self.timers.pop(ctx.author.id, None)
        if tarefa and not tarefa.done():
            tarefa.cancel()
        self.pendentes.pop(ctx.author.id, None)
        await asyncio.to_thread(data.remover_mudae, ctx.author.id)
        await ctx.send(f"{visual.AXOLOTL} reminder cancelado!")

    # ─── /mudae ───
    @app_commands.command(name="mudae", description="agenda aviso manual dos rolls do Mudae.")
    @app_commands.describe(minutos="em quantos minutos te marco (1–180)")
    async def mudae_slash(self, interaction: discord.Interaction, minutos: int):
        """versão slash do >mudae."""
        if minutos <= 0 or minutos > MAX_MINUTOS:
            await interaction.response.send_message(
                f"{visual.AXOLOTL} usa 1–{MAX_MINUTOS} minutos. "
                f"o auto-reminder já pega seus `$m`/`$wa` sozinho.",
                ephemeral=True,
            )
            return
        guild_id = interaction.guild.id if interaction.guild else 0
        await self.agendar(interaction.user.id, interaction.channel.id, guild_id, minutos)
        await interaction.response.send_message(
            f"{visual.AXOLOTL} te marco em **{minutos} min**!", ephemeral=True
        )

    # ─── /mudae_stop ───
    @app_commands.command(name="mudae_stop", description="cancela seu reminder do Mudae.")
    async def mudae_stop_slash(self, interaction: discord.Interaction):
        """versão slash do >mudae_stop."""
        tarefa = self.timers.pop(interaction.user.id, None)
        if tarefa and not tarefa.done():
            tarefa.cancel()
        self.pendentes.pop(interaction.user.id, None)
        await asyncio.to_thread(data.remover_mudae, interaction.user.id)
        await interaction.response.send_message(
            f"{visual.AXOLOTL} reminder cancelado!", ephemeral=True
        )

    def cog_unload(self):
        for t in self.timers.values():
            if not t.done():
                t.cancel()
        self.timers.clear()
        self.pendentes.clear()


async def setup(bot: commands.Bot):
    await bot.add_cog(Mudae(bot))
