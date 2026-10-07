# isso aq e quest diaria/semanal + xp por call.
# voz paga pouco de proposito: +5xp por hora, so conta quem
# nao ta mutado nem surdo (afk nao conta). msg conta sempre.
# completou, pagou na hora. reset sozinho por chave de periodo.

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

import data
import visual

log = logging.getLogger("alt.quests")

DIARIAS = [
    {"id": "msg10", "nome": "manda 10 mensagens", "meta": 10, "xp": 20},
    {"id": "call30", "nome": "30min em call", "meta": 30, "xp": 15},
    {"id": "ptp1", "nome": "vence 1 ptp", "meta": 1, "xp": 10},
]
SEMANAIS = [
    {"id": "msg100", "nome": "manda 100 mensagens", "meta": 100, "xp": 60},
    {"id": "call5h", "nome": "5h em call", "meta": 300, "xp": 50},
]

VOZ_TICK_MIN = 5
VOZ_XP_HORA = 5


def _vale(membro: discord.Member) -> bool:
    # bot nunca. mutado/surdo (proprio ou server) e afk nao contam.
    if membro.bot:
        return False
    voz = membro.voice
    if voz is None:
        return False
    if voz.self_mute or voz.mute or voz.self_deaf or voz.deaf or voz.afk:
        return False
    return True


async def _festeja(canal, nome: str, xp: int):
    try:
        await canal.send(f"{visual.AXOLOTL} quest completa: **{nome}** +{xp}xp!")
    except Exception:
        pass


class Quests(commands.Cog, name="Quests"):
    """quests diarias/semanais e xp por tempo de call."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.conta_voz.is_running():
            self.conta_voz.start()
            log.info("quests: contador de voz a cada %dmin", VOZ_TICK_MIN)

    # ─── conta msg ───
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        dia = await asyncio.to_thread(data.hoje_key)
        sem = await asyncio.to_thread(data.semana_key)
        for quest in DIARIAS:
            if quest["id"] != "msg10":
                continue
            _, agora, _, _, _ = await asyncio.to_thread(
                data.quest_evento,
                message.author.id,
                quest["id"],
                dia,
                1,
                quest["meta"],
                quest["xp"],
            )
            if agora:
                await _festeja(message.channel, quest["nome"], quest["xp"])
        for quest in SEMANAIS:
            if quest["id"] != "msg100":
                continue
            _, agora, _, _, _ = await asyncio.to_thread(
                data.quest_evento,
                message.author.id,
                quest["id"],
                sem,
                1,
                quest["meta"],
                quest["xp"],
            )
            if agora:
                await _festeja(message.channel, quest["nome"], quest["xp"])

    # ─── conta voz ───
    @tasks.loop(minutes=VOZ_TICK_MIN)
    async def conta_voz(self):
        dia = await asyncio.to_thread(data.hoje_key)
        sem = await asyncio.to_thread(data.semana_key)
        for guild in self.bot.guilds:
            for canal in guild.voice_channels:
                for membro in canal.members:
                    if not _vale(membro):
                        continue
                    await asyncio.to_thread(
                        data.quest_evento,
                        membro.id,
                        "call30",
                        dia,
                        VOZ_TICK_MIN,
                        30,
                        15,
                    )
                    await asyncio.to_thread(
                        data.quest_evento,
                        membro.id,
                        "call5h",
                        sem,
                        VOZ_TICK_MIN,
                        300,
                        50,
                    )
                    minutos, pago = await asyncio.to_thread(
                        data.somar_voz, membro.id, dia, VOZ_TICK_MIN
                    )
                    if minutos - pago >= 60:
                        await asyncio.to_thread(data.ganhar_xp, membro.id, VOZ_XP_HORA)
                        await asyncio.to_thread(data.pagar_voz, membro.id, dia, pago + 60)
                        log.info("quests: +5xp de voz pra %d", membro.id)

    @conta_voz.before_loop
    async def before_conta_voz(self):
        await self.bot.wait_until_ready()

    def _linhas(self, quests: list[dict], estado: dict) -> list[str]:
        linhas = []
        for q in quests:
            prog, ok = estado.get(q["id"], (0, False))
            marca = "✅" if ok else f"{min(prog, q['meta'])}/{q['meta']}"
            linhas.append(f"{marca} {q['nome']} — +{q['xp']}xp")
        return linhas

    # ─── >quests ───
    @commands.command(name="quests")
    async def quests(self, ctx: commands.Context, membro: discord.Member = None):
        """veja suas quests diarias e semanais."""
        membro = membro or ctx.author
        dia = await asyncio.to_thread(data.hoje_key)
        sem = await asyncio.to_thread(data.semana_key)
        est_d = await asyncio.to_thread(data.estado_quests, membro.id, dia)
        est_s = await asyncio.to_thread(data.estado_quests, membro.id, sem)
        minutos, _ = await asyncio.to_thread(data.buscar_voz, membro.id, dia)
        embed = discord.Embed(
            title=f"Quests de {membro.display_name}",
            color=visual.PRIMARY,
        )
        embed.add_field(
            name="diárias (reset 00:00)",
            value="\n".join(self._linhas(DIARIAS, est_d)),
            inline=False,
        )
        embed.add_field(
            name="semanais (reset segunda 00:00)",
            value="\n".join(self._linhas(SEMANAIS, est_s)),
            inline=False,
        )
        embed.add_field(
            name="voz hoje",
            value=f"{minutos}min em call (+5xp por hora, sem contar mutado)",
            inline=False,
        )
        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.set_footer(text=visual.FOOTER)
        await ctx.send(embed=embed)

    # ─── /quests ───
    @app_commands.command(name="quests", description="veja suas quests diarias e semanais.")
    @app_commands.describe(membro="ver as quests de outro membro (opcional)")
    async def quests_slash(
        self, interaction: discord.Interaction, membro: discord.Member | None = None
    ):
        """versão slash do >quests."""
        membro = membro or interaction.user
        dia = await asyncio.to_thread(data.hoje_key)
        sem = await asyncio.to_thread(data.semana_key)
        est_d = await asyncio.to_thread(data.estado_quests, membro.id, dia)
        est_s = await asyncio.to_thread(data.estado_quests, membro.id, sem)
        minutos, _ = await asyncio.to_thread(data.buscar_voz, membro.id, dia)
        embed = discord.Embed(
            title=f"Quests de {membro.display_name}",
            color=visual.PRIMARY,
        )
        embed.add_field(
            name="diárias (reset 00:00)",
            value="\n".join(self._linhas(DIARIAS, est_d)),
            inline=False,
        )
        embed.add_field(
            name="semanais (reset segunda 00:00)",
            value="\n".join(self._linhas(SEMANAIS, est_s)),
            inline=False,
        )
        embed.add_field(
            name="voz hoje",
            value=f"{minutos}min em call (+5xp por hora, sem contar mutado)",
            inline=False,
        )
        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.set_footer(text=visual.FOOTER)
        await interaction.response.send_message(embed=embed)

    def cog_unload(self):
        if self.conta_voz.is_running():
            self.conta_voz.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(Quests(bot))
