import asyncio
import random

import discord
from discord import app_commands
from discord.ext import commands

import visual
import data

# xp ganho por mensagem (mín, máx)
XP_MIN = 10
XP_MAX = 25

# janela de cooldown para não contar XP de cada mensagem seguida.
COOLDOWN = 60  # segundos

BARRA_CHEIA = "█"
BARRA_VAZIA = "░"
BARRA_CELULAS = 10


class Niveis(commands.Cog, name="Níveis"):
    """sistema de XP e níveis."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cooldown: dict[int, float] = {}

    # ─── ganho de xp por mensagem ───
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        agora = discord.utils.utcnow().timestamp()
        if agora - self.cooldown.get(message.author.id, 0) < COOLDOWN:
            return
        self.cooldown[message.author.id] = agora

        # o SQLite é síncrono; tirar do event loop evita travar todos os
        # listeners durante a escrita.
        _, nivel, subiu = await asyncio.to_thread(
            data.ganhar_xp, message.author.id, random.randint(XP_MIN, XP_MAX)
        )

        if subiu:
            embed = discord.Embed(
                title="Subiu de nível!",
                description=(
                    f"{message.author.mention} agora é **nível {nivel}**! {visual.AXOLOTL}"
                ),
                color=visual.PRIMARY,
            )
            embed.set_footer(text=visual.FOOTER)
            await message.channel.send(embed=embed)

    # ─── >xp ───
    @commands.command(name="xp")
    async def xp(self, ctx: commands.Context, membro: discord.Member = None):
        """veja seu nível e XP atual."""
        membro = membro or ctx.author
        xp, nivel = await asyncio.to_thread(data.buscar_xp, membro.id)

        xp_prox = data.xp_para_proximo(nivel)
        celulas = int((xp / xp_prox) * BARRA_CELULAS)
        progresso = BARRA_CHEIA * celulas + BARRA_VAZIA * (BARRA_CELULAS - celulas)

        embed = discord.Embed(
            title=f"Rank de {membro.display_name}",
            color=visual.PRIMARY,
        )
        embed.add_field(name="Nível", value=str(nivel), inline=True)
        embed.add_field(name="XP", value=f"{xp}/{xp_prox}", inline=True)
        embed.add_field(name="Progresso", value=f"`{progresso}`", inline=False)
        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.set_footer(text=visual.FOOTER)
        await ctx.send(embed=embed)

    # ─── >ranking ───
    @commands.command(name="ranking", aliases=["top"])
    async def ranking(self, ctx: commands.Context):
        """ranking dos top 5 membros do servidor por xp."""
        ranking = await asyncio.to_thread(data.top_xp, 5)
        if not ranking:
            await ctx.send(f"{visual.AXOLOTL} ninguém tem XP ainda! Comecem a conversar!")
            return

        medalhas = [f"**{i}.**" for i in range(1, 6)]
        linhas = []

        for i, (user_id, nivel, xp) in enumerate(ranking):
            membro = ctx.guild.get_member(user_id)
            nome = membro.display_name if membro else f"Usuário {user_id}"
            linhas.append(f"{medalhas[i]} {nome} — Nível **{nivel}** | {xp} XP")

        embed = discord.Embed(
            title="Top 5 — Ranking de Níveis",
            description="\n".join(linhas),
            color=visual.WARNING,
        )
        embed.set_footer(text=visual.FOOTER)
        await ctx.send(embed=embed)

    # ─── >setxp (admin) ───
    @commands.command(name="setxp")
    @commands.has_permissions(administrator=True)
    async def setxp(self, ctx: commands.Context, membro: discord.Member, xp: int):
        """[admin] define o XP total de um membro e recalcula o nível."""
        xp_final, nivel = await asyncio.to_thread(data.definir_xp, membro.id, xp)
        await ctx.send(
            f"{visual.AXOLOTL} XP de {membro.mention} definido para "
            f"**{xp_final}** (nível **{nivel}**)."
        )

    # ─── /xp ───
    @app_commands.command(name="xp", description="veja seu nível e XP atual.")
    @app_commands.describe(membro="ver o xp de outro membro (opcional)")
    async def xp_slash(
        self, interaction: discord.Interaction, membro: discord.Member | None = None
    ):
        """versão slash do >xp."""
        membro = membro or interaction.user
        xp, nivel = await asyncio.to_thread(data.buscar_xp, membro.id)

        xp_prox = data.xp_para_proximo(nivel)
        celulas = int((xp / xp_prox) * BARRA_CELULAS)
        progresso = BARRA_CHEIA * celulas + BARRA_VAZIA * (BARRA_CELULAS - celulas)

        embed = discord.Embed(
            title=f"Rank de {membro.display_name}",
            color=visual.PRIMARY,
        )
        embed.add_field(name="Nível", value=str(nivel), inline=True)
        embed.add_field(name="XP", value=f"{xp}/{xp_prox}", inline=True)
        embed.add_field(name="Progresso", value=f"`{progresso}`", inline=False)
        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.set_footer(text=visual.FOOTER)
        await interaction.response.send_message(embed=embed)

    # ─── /ranking ───
    @app_commands.command(name="ranking", description="ranking dos top 5 membros do servidor.")
    async def ranking_slash(self, interaction: discord.Interaction):
        """versão slash do >ranking."""
        ranking = await asyncio.to_thread(data.top_xp, 5)
        if not ranking:
            await interaction.response.send_message(
                f"{visual.AXOLOTL} ninguém tem XP ainda! Comecem a conversar!",
                ephemeral=True,
            )
            return

        medalhas = [f"**{i}.**" for i in range(1, 6)]
        linhas = []

        for i, (user_id, nivel, xp) in enumerate(ranking):
            membro = interaction.guild.get_member(user_id) if interaction.guild else None
            nome = membro.display_name if membro else f"Usuário {user_id}"
            linhas.append(f"{medalhas[i]} {nome} — Nível **{nivel}** | {xp} XP")

        embed = discord.Embed(
            title="Top 5 — Ranking de Níveis",
            description="\n".join(linhas),
            color=visual.WARNING,
        )
        embed.set_footer(text=visual.FOOTER)
        await interaction.response.send_message(embed=embed)

    # ─── /top (alias antigo do /ranking) ───
    @app_commands.command(name="top", description="ranking dos top 5 membros do servidor.")
    async def top_slash(self, interaction: discord.Interaction):
        """alias antigo: mesmo que /ranking."""
        ranking = await asyncio.to_thread(data.top_xp, 5)
        if not ranking:
            await interaction.response.send_message(
                f"{visual.AXOLOTL} ninguém tem XP ainda! Comecem a conversar!",
                ephemeral=True,
            )
            return

        medalhas = [f"**{i}.**" for i in range(1, 6)]
        linhas = []

        for i, (user_id, nivel, xp) in enumerate(ranking):
            membro = interaction.guild.get_member(user_id) if interaction.guild else None
            nome = membro.display_name if membro else f"Usuário {user_id}"
            linhas.append(f"{medalhas[i]} {nome} — Nível **{nivel}** | {xp} XP")

        embed = discord.Embed(
            title="Top 5 — Ranking de Níveis",
            description="\n".join(linhas),
            color=visual.WARNING,
        )
        embed.set_footer(text=visual.FOOTER)
        await interaction.response.send_message(embed=embed)

    # ─── /setxp (admin) ───
    @app_commands.command(name="setxp", description="[admin] define o XP total de um membro.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(membro="quem recebe o XP", xp="valor total de XP")
    async def setxp_slash(
        self, interaction: discord.Interaction, membro: discord.Member, xp: int
    ):
        """versão slash do >setxp."""
        xp_final, nivel = await asyncio.to_thread(data.definir_xp, membro.id, xp)
        await interaction.response.send_message(
            f"{visual.AXOLOTL} XP de {membro.mention} definido para "
            f"**{xp_final}** (nível **{nivel}**)."
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Niveis(bot))
