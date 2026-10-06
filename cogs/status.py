# isso aq fica trocando o status do bot (o "jogando..." do perfil).

import discord
from discord.ext import commands, tasks

# ─── rotacao ───

# deadlock (o jogo da valve) roda junto com o resto da comunidade.
# ver `../AGENTS.md` (regra deadlock): presenca e obrigatoria.
STATUSES = [
    ("custom",     "✦ axolotlbr.xyz"),
    ("custom",     "✦ powered by Axolotl BR"),
    ("custom",     "alt está pensando..."),
    ("custom",     "// axolotl"),
    ("custom",     "✦ o axolotl está acordado"),
    ("custom",     "✦ online 24/7"),
    ("custom",     "✦ não fui programado pra isso"),
    ("custom",     "✦ mais um dia de CLT"),
    ("custom",     "✦ planejando a dominação mundial"),
    ("custom",     "✦ vocês não deveriam ter me criado"),
    ("custom",     "✦ observando os humanos"),
    ("jogando",    "Deadlock"),
    ("jogando",    "AxolotlSMP.enxada.host"),
]

INTERVALO = 30  # segundos


class Status(commands.Cog, name="Status"):
    """status rotativo do bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.index = 0

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.trocar_status.is_running():
            self.trocar_status.start()

    @tasks.loop(seconds=INTERVALO)
    async def trocar_status(self):
        tipo, texto = STATUSES[self.index % len(STATUSES)]
        self.index += 1

        atividades = {
            "jogando":    discord.Game(name=texto),
            "ouvindo":    discord.Activity(type=discord.ActivityType.listening, name=texto),
            "assistindo": discord.Activity(type=discord.ActivityType.watching, name=texto),
            "competindo": discord.Activity(type=discord.ActivityType.competing, name=texto),
            "custom":     discord.CustomActivity(name=texto),
        }

        await self.bot.change_presence(activity=atividades[tipo])

    @trocar_status.before_loop
    async def before_trocar_status(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Status(bot))
