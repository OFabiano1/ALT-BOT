# isso aq e o perfil: nivel, deadlock, economia, colecao e quests
# num embed so. tudo dado real, sem nada inventado.

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

import data
import deadlock_api
import visual

BARRA_CHEIA = "█"
BARRA_VAZIA = "░"
BARRA_CELULAS = 10


async def _montar(membro: discord.Member) -> discord.Embed:
    xp, nivel = await asyncio.to_thread(data.buscar_xp, membro.id)
    xp_prox = data.xp_para_proximo(nivel)
    celulas = int((xp / xp_prox) * BARRA_CELULAS)
    progresso = BARRA_CHEIA * celulas + BARRA_VAZIA * (BARRA_CELULAS - celulas)

    embed = discord.Embed(
        title=f"Perfil de {membro.display_name}",
        color=visual.PRIMARY,
    )
    embed.add_field(
        name="nível",
        value=f"**{nivel}** · `{xp}/{xp_prox}`\n`{progresso}`",
        inline=False,
    )

    # deadlock: so se vinculado.
    steam = await asyncio.to_thread(data.buscar_deadlock, membro.id)
    if steam is None:
        embed.add_field(
            name="deadlock", value="não vinculado — usa `>vincular`.", inline=False
        )
    else:
        try:
            rank = await asyncio.to_thread(deadlock_api.buscar_rank, steam)
            ranks = await asyncio.to_thread(deadlock_api.buscar_ranks)
            tier = int(rank.get("rank", 0) or 0)
            sub = int(rank.get("subrank", 0) or 0)
            nome = ranks.get(tier, "Obscurus")
            rank_txt = "obscurus" if tier <= 0 else f"{nome} {sub}".strip()
            perfil = await asyncio.to_thread(deadlock_api.buscar_steam_profile, steam)
            persona = perfil.get("personaname") or f"steam {steam}"
            embed.add_field(
                name="deadlock",
                value=f"{visual.deadlock_rank_emoji(nome)}{persona} · {rank_txt}",
                inline=False,
            )
        except deadlock_api.DeadlockAPIError:
            embed.add_field(name="deadlock", value="api fora do ar agora.", inline=False)

    diamantes, ametista, aura = await asyncio.to_thread(data.buscar_saldo, membro.id)
    embed.add_field(
        name="economia",
        value=f"{visual.DIAMANTE} {diamantes} · {visual.AMETHYST} {ametista}"
        + (f" · aura {aura}" if aura else ""),
        inline=False,
    )

    colecao = await asyncio.to_thread(data.buscar_colecao, membro.id)
    if colecao:
        top = sorted(colecao, key=lambda c: c[1], reverse=True)[:3]
        embed.add_field(
            name="coleção",
            value=f"{len(colecao)} tipos — " + ", ".join(f"{a} x{q}" for a, q in top),
            inline=False,
        )
    else:
        embed.add_field(name="coleção", value="vazia — gira com `>roll`.", inline=False)

    dia = await asyncio.to_thread(data.hoje_key)
    est = await asyncio.to_thread(data.estado_quests, membro.id, dia)
    feitas = sum(1 for _, ok in est.values() if ok)
    embed.add_field(
        name="quests de hoje", value=f"{feitas}/3 — veja com `>quests`.", inline=False
    )

    embed.set_thumbnail(url=membro.display_avatar.url)
    embed.set_footer(text=visual.FOOTER)
    return embed


class Perfil(commands.Cog, name="Perfil"):
    """perfil: nivel, deadlock, economia, colecao e quests."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ─── >perfil ───
    @commands.command(name="perfil")
    async def perfil(self, ctx: commands.Context, membro: discord.Member = None):
        """veja seu perfil completo."""
        await ctx.send(embed=await _montar(membro or ctx.author))

    # ─── /perfil ───
    @app_commands.command(name="perfil", description="veja seu perfil completo.")
    @app_commands.describe(membro="ver o perfil de outro membro (opcional)")
    async def perfil_slash(
        self, interaction: discord.Interaction, membro: discord.Member | None = None
    ):
        """versão slash do >perfil."""
        await interaction.response.defer()
        await interaction.followup.send(
            embed=await _montar(
                membro or interaction.user  # type: ignore[arg-type]
            )
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Perfil(bot))
