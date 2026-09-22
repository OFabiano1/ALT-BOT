import discord
from discord.ext import commands

GIF = "https://cdn.discordapp.com/attachments/1425980403319312496/1454089728159907981/penisapro.gif"

class AutoResponse(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        # ignora mensagens do próprio bot
        if message.author == self.bot.user:
            return

        # responde W se a mensagem for apenas "w" (case insensitive)
        if message.content.strip().lower() == "w":
            await message.channel.send("W")

        # repost do gif automaticamente
        if GIF in message.content:
            await message.channel.send(GIF)


async def setup(bot):
    await bot.add_cog(AutoResponse(bot))