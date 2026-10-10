# isso aq e o hub do servidor: comunidade, discord, site e projetos.
# so dado real: o do discord vem do guild, o resto e fato do dono.
# axolotl smp entra como projeto, ip so quando existir (sem numero inventado).

import asyncio
import datetime

import discord
from discord import app_commands
from discord.ext import commands

import data
import deadlock_api
import painel
import visual

# site da comunidade (fato do dono, mesmo do status).
SITE_URL = "https://axolotlbr.xyz"

# projetos do ecossistema. ip do smp so entra aqui quando existir.
PROJETOS = (
    ("Axolotl SMP", "servidor de minecraft da comunidade — ip em breve"),
    ("ALT", "o bot do discord — `>ajuda` pra ver tudo"),
    ("site", "axolotlbr.xyz"),
)


def _desde_2020(guild: discord.Guild | None) -> str:
    # idade real do servidor no discord, ou o marco da marca.
    if guild is not None and guild.created_at is not None:
        criacao = guild.created_at
        anos = max(0, datetime.datetime.now(datetime.timezone.utc).year - criacao.year)
        return f"no discord desde {criacao.year} ({anos} anos)"
    return "desde 2020"


def _painel_hub(guild: discord.Guild | None) -> discord.ui.LayoutView:
    campos = [
        (
            "comunidade",
            f"jogar, criar e conectar. {_desde_2020(guild)}.",
        )
    ]
    if guild is not None:
        humanos = sum(1 for m in guild.members if not m.bot)
        bots = sum(1 for m in guild.members if m.bot)
        campos.append(
            (
                "discord",
                f"**{guild.name}** — {len(guild.members)} membros "
                f"({humanos} players, {bots} bots) · "
                f"{len(guild.text_channels)} chats · {len(guild.voice_channels)} calls",
            )
        )
    campos.append(("site", SITE_URL))
    campos.append(
        (
            "projetos",
            "\n".join(f"**{nome}** — {desc}" for nome, desc in PROJETOS),
        )
    )
    return painel.montar(
        f"{visual.AXOLOTL} Axolotl BR",
        linhas=["sua comunidade na internet desde 2020, de player pra player."],
        campos=campos,
    )


class Servidor(commands.Cog, name="Servidor"):
    """hub do servidor + perfil completo."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ─── >server ───
    @commands.command(name="server")
    async def server(self, ctx: commands.Context):
        """o hub do servidor."""
        await ctx.send(view=_painel_hub(ctx.guild))

    # ─── /server ───
    @app_commands.command(name="server", description="o hub do servidor.")
    async def server_slash(self, interaction: discord.Interaction):
        """versão slash do >server."""
        await interaction.response.send_message(view=_painel_hub(interaction.guild))

    # ─── >perfil ───
    @commands.command(name="perfil")
    async def perfil(self, ctx: commands.Context, membro: discord.Member = None):
        """veja seu perfil completo."""
        await ctx.send(view=await _montar_perfil(membro or ctx.author))

    # ─── /perfil ───
    @app_commands.command(name="perfil", description="veja seu perfil completo.")
    @app_commands.describe(membro="ver o perfil de outro membro (opcional)")
    async def perfil_slash(
        self, interaction: discord.Interaction, membro: discord.Member | None = None
    ):
        """versão slash do >perfil."""
        await interaction.response.defer()
        await interaction.followup.send(
            view=await _montar_perfil(
                membro or interaction.user  # type: ignore[arg-type]
            )
        )


BARRA_CHEIA = "█"
BARRA_VAZIA = "░"
BARRA_CELULAS = 10


async def _montar_perfil(membro: discord.Member) -> discord.ui.LayoutView:
    xp, nivel = await asyncio.to_thread(data.buscar_xp, membro.id)
    xp_prox = data.xp_para_proximo(nivel)
    celulas = int((xp / xp_prox) * BARRA_CELULAS)
    progresso = BARRA_CHEIA * celulas + BARRA_VAZIA * (BARRA_CELULAS - celulas)

    campos = [
        ("nível", f"**{nivel}** · `{xp}/{xp_prox}`\n`{progresso}`"),
    ]

    # deadlock: so se vinculado, com heroi top junto.
    steam = await asyncio.to_thread(data.buscar_deadlock, membro.id)
    if steam is None:
        campos.append(("deadlock", "não vinculado — usa `>vincular`."))
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
            linha = f"{visual.deadlock_rank_emoji(nome)}{persona} · {rank_txt}"
            topo = await asyncio.to_thread(deadlock_api.buscar_hero_stats, steam)
            if topo:
                melhor = max(topo, key=lambda h: int(h.get("matches_played", 0) or 0))
                heroes = await asyncio.to_thread(deadlock_api.buscar_heroes)
                hnome = heroes.get(int(melhor.get("hero_id", 0) or 0), "heroi")
                linha += (
                    f"\nherói top: {visual.deadlock_hero_emoji(hnome)}{hnome} "
                    f"({melhor.get('matches_played', 0)} partidas, "
                    f"{melhor.get('wins', 0)} vitórias)"
                )
            campos.append(("deadlock", linha))
        except deadlock_api.DeadlockAPIError:
            campos.append(("deadlock", "api fora do ar agora."))

    diamantes, ametista, aura = await asyncio.to_thread(data.buscar_saldo, membro.id)
    hoje = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    ultimo = await asyncio.to_thread(data.buscar_daily, membro.id)
    daily = "já resgatado" if ultimo == hoje else "disponível!"
    campos.append(
        (
            "economia",
            f"{visual.DIAMANTE} {diamantes} · {visual.AMETHYST} {ametista}"
            + (f" · aura {aura}" if aura else "")
            + f"\ndaily: {daily}",
        )
    )

    colecao = await asyncio.to_thread(data.buscar_colecao, membro.id)
    if colecao:
        total = sum(q for _, q in colecao)
        top = sorted(colecao, key=lambda c: c[1], reverse=True)[:3]
        campos.append(
            (
                "coleção",
                f"{len(colecao)} tipos, {total} no total — "
                + ", ".join(f"{a} x{q}" for a, q in top),
            )
        )
    else:
        campos.append(("coleção", "vazia — gira com `>roll`."))

    # servidor: so faz sentido dentro do servidor.
    if isinstance(membro, discord.Member) and membro.joined_at is not None:
        entrou = membro.joined_at.strftime("%d/%m/%Y")
        cargos = [c for c in membro.roles if not c.is_default()]
        linha = f"aqui desde **{entrou}**"
        if cargos:
            linha += f" · cargo top **{max(cargos, key=lambda c: c.position).name}**"
        campos.append(("servidor", linha))

    return painel.montar(
        f"👤 Perfil de {membro.display_name}",
        campos=campos,
        avatar=membro.display_avatar.url,
    )


async def setup(bot: commands.Bot):
    await bot.add_cog(Servidor(bot))
