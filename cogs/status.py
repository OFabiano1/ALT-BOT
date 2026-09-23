import discord
from discord.ext import commands, tasks

# (tipo de atividade, texto do status)
STATUSES = [
    ("jogando",    "no Axolotl SMP"),
    ("jogando",    "Minecraft"),
    ("ouvindo",    "a comunidade"),
    ("assistindo", "a galera jogar"),
    ("competindo", "de player pra player"),
]

INTERVALO = 30  # segundos


class Status(commands.Cog, name="Status"):
    """Status rotativo do bot."""

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
        }

        await self.bot.change_presence(activity=atividades[tipo])

    @trocar_status.before_loop
    async def before_trocar_status(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Status(bot))