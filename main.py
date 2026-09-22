import discord
from discord.ext import commands

import os
import sys

from dotenv import load_dotenv
import asyncio

load_dotenv()
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=">", intents=intents)

# bot está online
@bot.event
async def on_ready():
    print("─" * 50)
    print(f"  {bot.user} - hello world! ᓬ(•⤙•๑)ᕒ")
    print(f"  ↳ Powered by Axolotl BR © 2020 - 2026")
    print("─" * 50)

# hello world
@bot.command()
async def axolotl(ctx):
    await ctx.send("Hello World!")

# restart
@bot.command()
@commands.is_owner()
async def restart(ctx):
    await ctx.send("🔄 reiniciando...")
    await bot.close()
    os.system(f'python "{sys.argv[0]}"')
    sys.exit(0)

# latencia
@bot.command()
async def ping(ctx):
    await ctx.send(f'pong!: {round(bot.latency*1000)}ms')

async def main():
    async with bot:
        await bot.load_extension("cogs.auto_response")
        await bot.load_extension("cogs.jogos")
        await bot.load_extension("cogs.niveis")
        await bot.load_extension("cogs.tickets")
        await bot.start(TOKEN)

asyncio.run(main())

