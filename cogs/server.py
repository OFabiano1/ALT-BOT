# isso aq e o hub do servidor: comunidade, discord, site e projetos.
# so dado real: o do discord vem do guild, o resto e fato do dono.
# axolotl smp entra como projeto, ip so quando existir (sem numero inventado).

import datetime

import discord
from discord import app_commands
from discord.ext import commands

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


def _embed_hub(guild: discord.Guild | None) -> discord.Embed:
    embed = discord.Embed(
        title=f"{visual.AXOLOTL} Axolotl BR",
        description="sua comunidade na internet, de player pra player.",
        color=visual.PRIMARY,
    )
    embed.add_field(
        name="comunidade",
        value=f"jogar, criar e conectar. {_desde_2020(guild)}.",
        inline=False,
    )
    if guild is not None:
        humanos = sum(1 for m in guild.members if not m.bot)
        bots = sum(1 for m in guild.members if m.bot)
        embed.add_field(
            name="discord",
            value=(
                f"**{guild.name}** — {len(guild.members)} membros "
                f"({humanos} players, {bots} bots) · "
                f"{len(guild.text_channels)} chats · {len(guild.voice_channels)} calls"
            ),
            inline=False,
        )
    embed.add_field(name="site", value=SITE_URL, inline=False)
    embed.add_field(
        name="projetos",
        value="\n".join(f"**{nome}** — {desc}" for nome, desc in PROJETOS),
        inline=False,
    )
    embed.set_footer(text=visual.FOOTER)
    return embed


class Servidor(commands.Cog, name="Servidor"):
    """hub do servidor: comunidade, discord, site e projetos."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ─── >server ───
    @commands.command(name="server")
    async def server(self, ctx: commands.Context):
        """o hub do servidor."""
        await ctx.send(embed=_embed_hub(ctx.guild))

    # ─── /server ───
    @app_commands.command(name="server", description="o hub do servidor.")
    async def server_slash(self, interaction: discord.Interaction):
        """versão slash do >server."""
        await interaction.response.send_message(embed=_embed_hub(interaction.guild))


async def setup(bot: commands.Bot):
    await bot.add_cog(Servidor(bot))
