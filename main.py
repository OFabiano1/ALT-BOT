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

# ajuda
@bot.command(name="ajuda")
async def ajuda(ctx):
    """Mostra todos os comandos do bot."""
    restricoes = {
        "restart":     "🔒 dono",
        "setxp":       "🔒 admin",
        "setupticket": "🔒 admin",
        "addticket":   "🔒 moderador",
    }

    embed = discord.Embed(
        title="🛠️ Comandos do ALT",
        description="comandos de prefixo `>` do bot.",
        color=0xFF69B4,
    )

    por_cog = {}
    for cmd in bot.commands:
        if cmd.name in ("ajuda", "help"):
            continue
        chave = cmd.cog.qualified_name if cmd.cog else "Geral"
        por_cog.setdefault(chave, []).append(cmd)

    rotulos = {
        "Geral":   "🤖 Geral",
        "jogos":   "🎮 Jogos",
        "Níveis":  "⭐ Níveis",
        "tickets": "🎫 Tickets",
    }

    for chave, cmds in por_cog.items():
        linhas = []
        for cmd in cmds:
            uso = f"`>{cmd.name}`"
            if cmd.name in restricoes:
                uso += f" {restricoes[cmd.name]}"
            if cmd.short_doc:
                uso += f" — {cmd.short_doc}"
            linhas.append(uso)
        embed.add_field(name=rotulos.get(chave, chave), value="\n".join(linhas), inline=True)

    embed.set_footer(text="Player to Player • Axolotl BR")
    await ctx.send(embed=embed)

# call
@bot.command(name="call")
async def call(ctx):
    """Entra na call de voz que você está."""
    try:
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            await ctx.send("você precisa estar em uma call de voz para eu entrar!")
            return

        canal = ctx.author.voice.channel

        permissoes = canal.permissions_for(ctx.guild.me)
        if not permissoes.connect:
            await ctx.send(f"não tenho permissão de **conectar** no canal **{canal.name}**!")
            return
        if not permissoes.speak:
            await ctx.send(f"não tenho permissão de **falar** no canal **{canal.name}**!")
            return

        if ctx.voice_client is not None:
            await ctx.voice_client.move_to(canal)
            await ctx.send(f"fui pra **{canal.name}**! 🎧")
            return

        await canal.connect()
        await ctx.send(f"tô na call **{canal.name}**! 🎧")
    except Exception as erro:
        await ctx.send(f"❌ não consegui entrar na call: `{type(erro).__name__}: {erro}`")

# sair
@bot.command(name="sair")
async def sair(ctx):
    """Sai da call de voz."""
    vc = ctx.voice_client
    if vc is None:
        await ctx.send("não estou em nenhuma call!")
        return
    await vc.disconnect()
    await ctx.send("saí da call! 👋")

async def main():
    async with bot:
        await bot.load_extension("cogs.auto_response")
        await bot.load_extension("cogs.jogos")
        await bot.load_extension("cogs.niveis")
        await bot.load_extension("cogs.tickets")
        await bot.start(TOKEN)

asyncio.run(main())

