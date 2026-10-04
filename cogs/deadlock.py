# isso aq e o cantinho do deadlock (o jogo da valve) no bot.
# sem numero inventado: so o chamado pra jogar com a galera.

import discord
from discord import app_commands
from discord.ext import commands

import visual


class Deadlock(commands.Cog, name="Deadlock"):
    """chamado pro deadlock."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ─── >deadlock ───
    @commands.command(name="deadlock")
    async def deadlock(self, ctx: commands.Context):
        """chama a galera pro deadlock."""
        embed = discord.Embed(
            title=f"{visual.DEADLOCK} Deadlock",
            description=(
                "o shooter da valve que a comunidade joga.\n"
                "chama a galera na call e bora."
            ),
            color=visual.PRIMARY,
        )
        embed.set_footer(text=visual.FOOTER)
        await ctx.send(embed=embed)

    # ─── /deadlock ───
    @app_commands.command(name="deadlock", description="chama a galera pro deadlock.")
    async def deadlock_slash(self, interaction: discord.Interaction):
        """versão slash do >deadlock."""
        embed = discord.Embed(
            title=f"{visual.DEADLOCK} Deadlock",
            description=(
                "o shooter da valve que a comunidade joga.\n"
                "chama a galera na call e bora."
            ),
            color=visual.PRIMARY,
        )
        embed.set_footer(text=visual.FOOTER)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Deadlock(bot))
