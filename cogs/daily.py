# isso aq e a diaria: digest 00:00, apaga 23:59, quests e streak.
# quests: 1 partida de deadlock (verifico sozinho), termo (botao)
# e 10 msgs. fecha as 3 e a streak anda (+5xp por dia, teto 50).

import asyncio
import datetime
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands, tasks

import data
import deadlock_api
import discord_quests
import painel
import visual

log = logging.getLogger("alt.daily")

TERMO_URL = (os.getenv("TERMO_URL") or "https://term.ooo/").strip()
DIGEST_CHANNEL_ID = data.env_int("DIGEST_CHANNEL_ID", 1310398751575113758)

# utc-3 fixo, mesmo do halloween.
TZ = datetime.timezone(datetime.timedelta(hours=-3))
MEIA_NOITE = datetime.time(hour=0, minute=0, tzinfo=TZ)
APAGA_HORA = datetime.time(hour=23, minute=59, tzinfo=TZ)
VARREDURA_HORA = datetime.time(hour=23, minute=30, tzinfo=TZ)

QUESTS = [
    {"id": "deadlock1", "nome": "joga 1 partida de deadlock", "xp": 15},
    {"id": "termo1", "nome": "joga o termo do dia", "xp": 10},
    {"id": "msg10", "nome": "manda 10 mensagens", "xp": 20},
]
STREAK_XP_DIA = 5
STREAK_TETO = 50


def hoje_str() -> str:
    return datetime.datetime.now(TZ).date().isoformat()


def ontem_str() -> str:
    return (datetime.datetime.now(TZ).date() - datetime.timedelta(days=1)).isoformat()


def corte_hoje_ts() -> float:
    return datetime.datetime.combine(
        datetime.datetime.now(TZ).date(), datetime.time.min
    ).replace(tzinfo=TZ).timestamp()


async def avaliar_deadlock(discord_id: int, account_id: int, historico: list) -> bool:
    """marca deadlock1 se tem partida de hoje. True se completou agora."""
    dia = hoje_str()
    feitas = await asyncio.to_thread(data.feitas_no_dia, discord_id, dia)
    if "deadlock1" in feitas:
        return False
    corte = corte_hoje_ts()
    for m in historico:
        try:
            inicio = float(m.get("start_time", 0) or 0)
        except (TypeError, ValueError):
            continue
        if inicio >= corte:
            if await asyncio.to_thread(data.marcar_feita, discord_id, dia, "deadlock1"):
                await asyncio.to_thread(data.ganhar_xp, discord_id, 15)
            return True
    return False


async def _canal(bot: commands.Bot):
    if not DIGEST_CHANNEL_ID:
        return None
    canal = bot.get_channel(DIGEST_CHANNEL_ID)
    if canal is None:
        try:
            canal = await bot.fetch_channel(DIGEST_CHANNEL_ID)
        except Exception:
            log.exception("diarias: chat do digest nao encontrado")
            return None
    return canal


async def _termo_feito(interaction: discord.Interaction):
    dia = hoje_str()
    if await asyncio.to_thread(data.marcar_feita, interaction.user.id, dia, "termo1"):
        await asyncio.to_thread(data.ganhar_xp, interaction.user.id, 10)
        await interaction.response.send_message(
            "boa! termo de hoje feito, +10xp. 🔥", ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "termo de hoje ja feito. ✅", ephemeral=True
        )


async def _verificar_deadlock(interaction: discord.Interaction):
    steam = await asyncio.to_thread(data.buscar_deadlock, interaction.user.id)
    if steam is None:
        await interaction.response.send_message(
            "vincula tua steam primeiro com `>vincular`!", ephemeral=True
        )
        return
    await interaction.response.defer(ephemeral=True)
    try:
        hist = await asyncio.to_thread(deadlock_api.buscar_match_history, steam)
    except deadlock_api.DeadlockAPIError:
        await interaction.followup.send(
            "api do deadlock fora do ar, tenta depois!", ephemeral=True
        )
        return
    if await avaliar_deadlock(interaction.user.id, steam, hist):
        await interaction.followup.send(
            "achei partida tua hoje! +15xp. 🎮", ephemeral=True
        )
    else:
        await interaction.followup.send(
            "ainda nao vi partida tua hoje. joga uma! 🎮", ephemeral=True
        )


def _botao_termo() -> discord.ui.Button:
    botao = discord.ui.Button(
        label="fiz o termo",
        emoji="✅",
        custom_id="diarias:termo",
        style=discord.ButtonStyle.success,
    )
    botao.callback = _termo_feito
    return botao


def _botao_verificar() -> discord.ui.Button:
    botao = discord.ui.Button(
        label="verificar deadlock",
        emoji="🔄",
        custom_id="diarias:verificar",
        style=discord.ButtonStyle.primary,
    )
    botao.callback = _verificar_deadlock
    return botao


class DiariasView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(_botao_termo())
        self.add_item(_botao_verificar())


def _linhas_quests_discord() -> str:
    # secao some em silencio se a api cair; o resto do digest segue.
    try:
        ativas = discord_quests.buscar_ativas()
    except Exception:
        log.exception("diarias: quests do discord fora do ar")
        return ""
    linhas = []
    for q in ativas:
        if not q["nome"]:
            continue
        partes = [f"• [{q['nome']}]({q['url']})"]
        if q["tarefas"]:
            partes.append(", ".join(q["tarefas"]))
        extras = " · ".join(p for p in [q["recompensa"], f"até {q['expira']}" if q["expira"] else ""] if p)
        if extras:
            partes.append(extras)
        linhas.append(" — ".join(partes))
    if not linhas:
        return ""
    return "🎯 **quests do discord:**\n" + "\n".join(linhas)


class Diarias(commands.Cog, name="Diárias"):
    """digest diario, quests e streak."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(DiariasView())

    @commands.Cog.listener()
    async def on_ready(self):
        for loop in (self.digest_00, self.apaga_2359, self.varredura_2330):
            if not loop.is_running():
                loop.start()
        log.info("diarias: loops 00:00, 23:30 e 23:59 armados")

    # ─── conta msg ───
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        dia = hoje_str()
        total = await asyncio.to_thread(
            data.somar_contador, message.author.id, dia, "msg", 1
        )
        if total == 10:
            if await asyncio.to_thread(
                data.marcar_feita, message.author.id, dia, "msg10"
            ):
                await asyncio.to_thread(data.ganhar_xp, message.author.id, 20)
                try:
                    await message.channel.send(
                        f"{visual.AXOLOTL} quest completa: **manda 10 mensagens** +20xp!"
                    )
                except Exception:
                    pass

    # ─── digest 00:00 ───
    @tasks.loop(time=MEIA_NOITE)
    async def digest_00(self):
        canal = await _canal(self.bot)
        if canal is None:
            return
        dia = hoje_str()
        try:
            secao = await asyncio.to_thread(_linhas_quests_discord)
            linhas = [
                f"🧩 termo do dia — {TERMO_URL}",
                "🎮 deadlock — joga **1 partida** (verifico sozinho)",
                "💬 manda **10 mensagens** por aqui",
                "fecha as 3 e mantém tua streak 🔥 — `>quests` pra ver",
            ]
            if secao:
                linhas += ["", secao]
            msg = await canal.send(
                view=painel.montar(
                    "🌅 bom dia! diárias de hoje:",
                    linhas=linhas,
                    botoes=[_botao_termo(), _botao_verificar()],
                )
            )
            await asyncio.to_thread(data.salvar_digest, dia, canal.id, msg.id)
            log.info("diarias: digest postado")
        except Exception:
            log.exception("diarias: falha ao postar digest")

    @digest_00.before_loop
    async def before_digest(self):
        await self.bot.wait_until_ready()

    # ─── varredura 23:30 (1 chamada por vinculado/dia) ───
    @tasks.loop(time=VARREDURA_HORA)
    async def varredura_2330(self):
        for discord_id, steam in await asyncio.to_thread(data.listar_deadlocks):
            try:
                hist = await asyncio.to_thread(
                    deadlock_api.buscar_match_history, steam
                )
            except deadlock_api.DeadlockAPIError:
                continue
            try:
                if await avaliar_deadlock(discord_id, steam, hist):
                    log.info("diarias: deadlock1 auto pra %d", discord_id)
            except Exception:
                log.exception("diarias: falha avaliando %d", discord_id)

    @varredura_2330.before_loop
    async def before_varredura(self):
        await self.bot.wait_until_ready()

    # ─── apaga + streak 23:59 ───
    @tasks.loop(time=APAGA_HORA)
    async def apaga_2359(self):
        dia = hoje_str()
        salvo = await asyncio.to_thread(data.buscar_digest, dia)
        if salvo is not None:
            channel_id, message_id = salvo
            try:
                canal = self.bot.get_channel(channel_id)
                if canal is None:
                    canal = await self.bot.fetch_channel(channel_id)
                msg = await canal.fetch_message(message_id)
                await msg.delete()
                log.info("diarias: digest apagado")
            except Exception:
                log.exception("diarias: falha ao apagar digest")
        ontem = ontem_str()
        obrigatorias = [q["id"] for q in QUESTS]
        quem = set(await asyncio.to_thread(data.quem_jogou, dia))
        quem.update(uid for uid, _, _ in await asyncio.to_thread(data.streak_ativos))
        for uid in quem:
            feitas = await asyncio.to_thread(data.feitas_no_dia, uid, dia)
            if all(q in feitas for q in obrigatorias):
                prev, ultimo = await asyncio.to_thread(data.buscar_streak, uid)
                novo = prev + 1 if ultimo == ontem else 1
                bonus = min(STREAK_TETO, STREAK_XP_DIA * novo)
                await asyncio.to_thread(data.ganhar_xp, uid, bonus)
                await asyncio.to_thread(data.salvar_streak, uid, novo, dia)
                log.info("diarias: streak %d -> %d", uid, novo)
            else:
                prev, _ = await asyncio.to_thread(data.buscar_streak, uid)
                if prev > 0:
                    await asyncio.to_thread(data.salvar_streak, uid, 0, dia)

    @apaga_2359.before_loop
    async def before_apaga(self):
        await self.bot.wait_until_ready()

    # ─── >quests ───
    @commands.command(name="quests")
    async def quests(self, ctx: commands.Context, membro: discord.Member = None):
        """veja as diárias de hoje e tua streak."""
        membro = membro or ctx.author
        dia = hoje_str()
        feitas = await asyncio.to_thread(data.feitas_no_dia, membro.id, dia)
        dias, _ = await asyncio.to_thread(data.buscar_streak, membro.id)
        linhas = []
        for q in QUESTS:
            marca = "✅" if q["id"] in feitas else "⬜"
            linhas.append(f"{marca} {q['nome']} — +{q['xp']}xp")
        await ctx.send(
            view=painel.montar(
                f"Diárias de {membro.display_name} 🔥 {dias}",
                linhas=linhas,
                avatar=membro.display_avatar.url,
                botoes=[_botao_termo(), _botao_verificar()],
            )
        )

    # ─── /quests ───
    @app_commands.command(name="quests", description="veja as diárias de hoje e tua streak.")
    @app_commands.describe(membro="ver as diárias de outro membro (opcional)")
    async def quests_slash(
        self, interaction: discord.Interaction, membro: discord.Member | None = None
    ):
        """versão slash do >quests."""
        membro = membro or interaction.user
        dia = hoje_str()
        feitas = await asyncio.to_thread(data.feitas_no_dia, membro.id, dia)
        dias, _ = await asyncio.to_thread(data.buscar_streak, membro.id)
        linhas = []
        for q in QUESTS:
            marca = "✅" if q["id"] in feitas else "⬜"
            linhas.append(f"{marca} {q['nome']} — +{q['xp']}xp")
        await interaction.response.send_message(
            view=painel.montar(
                f"Diárias de {membro.display_name} 🔥 {dias}",
                linhas=linhas,
                avatar=membro.display_avatar.url,
                botoes=[_botao_termo(), _botao_verificar()],
            )
        )

    def cog_unload(self):
        for loop in (self.digest_00, self.apaga_2359, self.varredura_2330):
            if loop.is_running():
                loop.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(Diarias(bot))
