import asyncio
import logging
import random

import discord
from discord import app_commands
from discord.ext import commands

import brand
import database

log = logging.getLogger("alt.niveis")

# XP ganho por mensagem (mín, máx)
XP_MIN = 10
XP_MAX = 25

# Janela de cooldown para não contar XP de cada mensagem seguida.
COOLDOWN = 60  # segundos

BARRA_CHEIA = "█"
BARRA_VAZIA = "░"
BARRA_CELULAS = 10


class Niveis(commands.Cog, name="Níveis"):
    """Sistema de XP e níveis."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cooldown: dict[int, float] = {}

    # ── Ganho de XP por mensagem ─────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        agora = discord.utils.utcnow().timestamp()
        if agora - self.cooldown.get(message.author.id, 0) < COOLDOWN:
            return
        self.cooldown[message.author.id] = agora

        # O SQLite é síncrono; tirar do event loop evita travar todos os
        # listeners durante a escrita.
        _, nivel, subiu = await asyncio.to_thread(
            database.ganhar_xp, message.author.id, random.randint(XP_MIN, XP_MAX)
        )

        if subiu:
            embed = discord.Embed(
                title="Subiu de nível!",
                description=(
                    f"{message.author.mention} agora é **nível {nivel}**! {brand.AXOLOTL}"
                ),
                color=brand.PRIMARY,
            )
            embed.set_footer(text=brand.FOOTER)
            await message.channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_cog_unload(self):
        self.cooldown.clear()

    # ── >rank ────────────────────────────────────────────────
    @commands.command(name="rank")
    async def rank(self, ctx: commands.Context, membro: discord.Member = None):
        """Veja seu nível e XP atual."""
        membro = membro or ctx.author
        xp, nivel = await asyncio.to_thread(database.buscar_xp, membro.id)

        xp_prox = database.xp_para_proximo(nivel)
        celulas = int((xp / xp_prox) * BARRA_CELULAS)
        progresso = BARRA_CHEIA * celulas + BARRA_VAZIA * (BARRA_CELULAS - celulas)

        embed = discord.Embed(
            title=f"Rank de {membro.display_name}",
            color=brand.PRIMARY,
        )
        embed.add_field(name="Nível", value=str(nivel), inline=True)
        embed.add_field(name="XP", value=f"{xp}/{xp_prox}", inline=True)
        embed.add_field(name="Progresso", value=f"`{progresso}`", inline=False)
        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.set_footer(text=brand.FOOTER)
        await ctx.send(embed=embed)

    # ── >top ─────────────────────────────────────────────────
    @commands.command(name="top")
    async def top(self, ctx: commands.Context):
        """Ranking dos top 10 membros do servidor."""
        ranking = await asyncio.to_thread(database.top_xp, 10)
        if not ranking:
            await ctx.send(f"{brand.AXOLOTL} ninguém tem XP ainda! Comecem a conversar!")
            return

        medalhas = [f"**{i}.**" for i in range(1, 11)]
        linhas = []

        for i, (user_id, nivel, xp) in enumerate(ranking):
            membro = ctx.guild.get_member(user_id)
            nome = membro.display_name if membro else f"Usuário {user_id}"
            linhas.append(f"{medalhas[i]} {nome} — Nível **{nivel}** | {xp} XP")

        embed = discord.Embed(
            title="Top 10 — Ranking de Níveis",
            description="\n".join(linhas),
            color=brand.WARNING,
        )
        embed.set_footer(text=brand.FOOTER)
        await ctx.send(embed=embed)

    # ── >setxp (admin) ───────────────────────────────────────
    @commands.command(name="setxp")
    @commands.has_permissions(administrator=True)
    async def setxp(self, ctx: commands.Context, membro: discord.Member, xp: int):
        """[Admin] Define o XP total de um membro e recalcula o nível."""
        xp_final, nivel = await asyncio.to_thread(database.definir_xp, membro.id, xp)
        await ctx.send(
            f"{brand.AXOLOTL} XP de {membro.mention} definido para "
            f"**{xp_final}** (nível **{nivel}**)."
        )

    # ── /rank ────────────────────────────────────────────────
    @app_commands.command(name="rank", description="Veja seu nível e XP atual.")
    @app_commands.describe(membro="ver o rank de outro membro (opcional)")
    async def rank_slash(
        self, interaction: discord.Interaction, membro: discord.Member | None = None
    ):
        """Versão slash do >rank."""
        membro = membro or interaction.user
        xp, nivel = await asyncio.to_thread(database.buscar_xp, membro.id)

        xp_prox = database.xp_para_proximo(nivel)
        celulas = int((xp / xp_prox) * BARRA_CELULAS)
        progresso = BARRA_CHEIA * celulas + BARRA_VAZIA * (BARRA_CELULAS - celulas)

        embed = discord.Embed(
            title=f"Rank de {membro.display_name}",
            color=brand.PRIMARY,
        )
        embed.add_field(name="Nível", value=str(nivel), inline=True)
        embed.add_field(name="XP", value=f"{xp}/{xp_prox}", inline=True)
        embed.add_field(name="Progresso", value=f"`{progresso}`", inline=False)
        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.set_footer(text=brand.FOOTER)
        await interaction.response.send_message(embed=embed)

    # ── /top ─────────────────────────────────────────────────
    @app_commands.command(name="top", description="Ranking dos top 10 membros do servidor.")
    async def top_slash(self, interaction: discord.Interaction):
        """Versão slash do >top."""
        ranking = await asyncio.to_thread(database.top_xp, 10)
        if not ranking:
            await interaction.response.send_message(
                f"{brand.AXOLOTL} ninguém tem XP ainda! Comecem a conversar!",
                ephemeral=True,
            )
            return

        medalhas = [f"**{i}.**" for i in range(1, 11)]
        linhas = []

        for i, (user_id, nivel, xp) in enumerate(ranking):
            membro = interaction.guild.get_member(user_id) if interaction.guild else None
            nome = membro.display_name if membro else f"Usuário {user_id}"
            linhas.append(f"{medalhas[i]} {nome} — Nível **{nivel}** | {xp} XP")

        embed = discord.Embed(
            title="Top 10 — Ranking de Níveis",
            description="\n".join(linhas),
            color=brand.WARNING,
        )
        embed.set_footer(text=brand.FOOTER)
        await interaction.response.send_message(embed=embed)

    # ── /setxp (admin) ───────────────────────────────────────
    @app_commands.command(name="setxp", description="[Admin] Define o XP total de um membro.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(membro="quem recebe o XP", xp="valor total de XP")
    async def setxp_slash(
        self, interaction: discord.Interaction, membro: discord.Member, xp: int
    ):
        """Versão slash do >setxp."""
        xp_final, nivel = await asyncio.to_thread(database.definir_xp, membro.id, xp)
        await interaction.response.send_message(
            f"{brand.AXOLOTL} XP de {membro.mention} definido para "
            f"**{xp_final}** (nível **{nivel}**)."
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Niveis(bot))
