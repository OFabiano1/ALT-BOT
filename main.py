import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

import asyncio
import inspect
import logging
import os
import sys

import random
import brand
import database

load_dotenv()

TOKEN = os.getenv("TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

COGS = (
    "cogs.auto_response",
    "cogs.status",
    "cogs.jogos",
    "cogs.niveis",
    "cogs.tickets",
    "cogs.economia",
    "cogs.mudae",
    "cogs.halloween",
)

# Intents mínimos. `members` e `message_content` são privilegiados e
# precisam estar habilitados no Developer Portal — ambos são usados de
# verdade (menções em tickets, XP por mensagem, cargos de moderação).
# `Intents.all()` ligava também `presences` e `typing`, que não são
# usados e só aumentam a superfície.
# `guild_messages`/`dm_messages` são os eventos de mensagem em si — sem
# eles o bot nem recebe a mensagem (prefixo `>` morre, slash continua).
# `message_content` sozinho só libera o texto, não o evento.
intents = discord.Intents(
    guilds=True,
    members=True,
    message_content=True,
    guild_messages=True,
    dm_messages=True,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    # stdout/stderr é o que a ShardCloud captura como log do container.
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("alt")

bot = commands.Bot(command_prefix=">", intents=intents)


# bot está online
@bot.event
async def on_ready():
    # Sem GUILD_ID o sync é global e pode levar até uma hora para
    # propagar. Apontando para o guild, vale em segundos.
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        synced = await bot.tree.sync(guild=guild)
        log.info("slash commands sincronizados no guild: %d", len(synced))
    else:
        log.warning("GUILD_ID nao definido — sync global (pode demorar ate 1h)")
        synced = await bot.tree.sync()
        log.info("slash commands sincronizados globalmente: %d", len(synced))

    log.info("%s online — %s", bot.user, brand.FOOTER)


@bot.event
async def on_command_error(ctx: commands.Context, erro: commands.CommandError):
    if isinstance(erro, commands.CommandNotFound):
        return
    if isinstance(erro, commands.CommandOnCooldown):
        await ctx.send(f"calma! tenta de novo em **{erro.retry_after:.0f}s**.")
        return
    if isinstance(erro, commands.CheckFailure):
        await ctx.send("sem permissão pra isso!")
        return
    log.warning("comando %s falhou: %s: %s", ctx.command, type(erro).__name__, erro)
    # Mostra a causa raiz (ex: Forbidden) em vez do wrapper genérico.
    original = getattr(erro, "original", erro)
    log.exception("comando %s falhou", ctx.command)
    # Erro visível no chat — comando que falha em silêncio é indepurável.
    try:
        await ctx.send(f"❌ deu ruim: `{type(original).__name__}: {original}`")
    except discord.DiscordException:
        pass


@bot.tree.error
async def on_tree_error(
    interaction: discord.Interaction, erro: app_commands.AppCommandError
):
    """Mesma visibilidade pros slash: nada falha em silêncio."""
    if isinstance(erro, app_commands.CommandOnCooldown):
        texto = f"calma! tenta de novo em **{erro.retry_after:.0f}s**."
    elif isinstance(erro, app_commands.CheckFailure):
        texto = "sem permissão pra isso!"
    else:
        original = getattr(erro, "original", erro)
        log.exception("slash /%s falhou", interaction.command_name)
        texto = f"❌ deu ruim: `{type(original).__name__}: {original}`"
    try:
        if interaction.response.is_done():
            await interaction.followup.send(texto, ephemeral=True)
        else:
            await interaction.response.send_message(texto, ephemeral=True)
    except discord.DiscordException:
        pass


# hello world
@bot.command()
async def axolotl(ctx):
    await ctx.send(f"{brand.AXOLOTL} Hello World!")


@bot.tree.command(name="axolotl", description="Hello World do axolote.")
async def axolotl_slash(interaction: discord.Interaction):
    await interaction.response.send_message(f"{brand.AXOLOTL} Hello World!")


# restart
@bot.command()
@commands.is_owner()
async def restart(ctx):
    await ctx.send("reiniciando...")
    # os.system é bloqueante e deixa o processo antigo vivo — no deploy
    # isso criava um bot zumbi. execv substitui a imagem do processo,
    # então não sobra ninguém.
    await bot.close()
    sys.stdout.flush()
    os.execv(sys.executable, [sys.executable, *sys.argv])


@bot.tree.command(name="restart", description="[dono] Reinicia o bot.")
async def restart_slash(interaction: discord.Interaction):
    info = await bot.application_info()
    if interaction.user.id != info.owner.id:
        await interaction.response.send_message("sem permissão pra isso!", ephemeral=True)
        return
    await interaction.response.send_message("reiniciando...")
    await bot.close()
    sys.stdout.flush()
    os.execv(sys.executable, [sys.executable, *sys.argv])


# latencia
@bot.command()
async def ping(ctx):
    await ctx.send(f"pong!: {round(bot.latency * 1000)}ms")


# latencia (slash)
@bot.tree.command(name="ping", description="Mostra a latência do bot.")
async def slash_ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"pong!: {round(bot.latency * 1000)}ms")


# ajuda
def _grupos_comandos() -> dict[str, list[tuple[str, str | None]]]:
    """Comandos de prefixo agrupados: {categoria: [(nome, doc)]}."""
    grupos: dict[str, list[tuple[str, str | None]]] = {}
    for cmd in bot.commands:
        if cmd.name in ("ajuda", "help") or cmd.hidden:
            continue
        chave = cmd.cog.qualified_name if cmd.cog else "Geral"
        grupos.setdefault(chave, []).append((cmd.name, cmd.short_doc))
    return grupos


def _embed_ajuda(linhas_por_categoria: dict[str, list[str]]) -> discord.Embed:
    """Monta o embed da ajuda. Usado pelo `>` e pelo `/`."""
    embed = discord.Embed(
        title=f"{brand.AXOLOTL} Comandos do ALT",
        description="funciono com `>` e com `/` — usa o que preferir.",
        color=brand.PRIMARY,
    )
    for chave, linhas in linhas_por_categoria.items():
        embed.add_field(
            name=brand.CATEGORIAS.get(chave, chave),
            value="\n".join(linhas),
            inline=False,
        )
    slash = " ".join(
        f"`/{c.name}`" for c in sorted(bot.tree.walk_commands(), key=lambda c: c.name)
    )
    embed.add_field(name="⌨️ slash", value=slash or "`/ping`", inline=False)
    embed.set_footer(text=brand.FOOTER)
    return embed


@bot.command(name="ajuda")
async def ajuda(ctx):
    """Mostra todos os comandos do bot."""

    async def permissao(cmd: commands.Command) -> str:
        """Rótulo de bloqueio se o autor não puder usar o comando."""
        for check in cmd.checks:
            # `cmd.checks` guarda os predicates nus (sem `.predicate`) —
            # o getattr cobre os dois formatos. E cada predicate pode ser
            # sync (ex: has_permissions) ou async (ex: is_owner).
            predicate = getattr(check, "predicate", check)
            try:
                resultado = predicate(ctx)
                if inspect.isawaitable(resultado):
                    resultado = await resultado
            except commands.CheckFailure:
                return "🔒 restrito"
            if resultado is False:
                return "🔒 restrito"
        return ""

    linhas: dict[str, list[str]] = {}
    for cmd in bot.commands:
        if cmd.name in ("ajuda", "help") or cmd.hidden:
            continue
        chave = cmd.cog.qualified_name if cmd.cog else "Geral"
        uso = f"`>{cmd.name} {await permissao(cmd)}`".rstrip()
        if cmd.short_doc:
            uso += f" — {cmd.short_doc}"
        linhas.setdefault(chave, []).append(uso)
    await ctx.send(embed=_embed_ajuda(linhas))


@bot.tree.command(name="ajuda", description="Mostra todos os comandos do bot.")
async def ajuda_slash(interaction: discord.Interaction):
    """Versão slash da ajuda (efêmera — só você vê)."""
    slash_nomes = {c.name for c in bot.tree.walk_commands()}
    linhas: dict[str, list[str]] = {}
    for chave, cmds in _grupos_comandos().items():
        grupo = []
        for nome, doc in cmds:
            uso = f"`/{nome}`" if nome in slash_nomes else f"`>{nome}`"
            if doc:
                uso += f" — {doc}"
            grupo.append(uso)
        linhas[chave] = grupo
    await interaction.response.send_message(embed=_embed_ajuda(linhas), ephemeral=True)


# call
@bot.command(name="call")
async def call(ctx):
    """entra na call de voz que você está."""
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

        if ctx.voice_client is not None:
            await ctx.voice_client.move_to(canal)
            await ctx.send(f"fui pra **{canal.name}**! 🎧")
            return

        await canal.connect()
        await ctx.send(f"tô na call **{canal.name}**! 🎧")
    except Exception as erro:
        log.exception("falha ao entrar na call")
        await ctx.send(f"❌ não consegui entrar na call: `{type(erro).__name__}`")


@bot.tree.command(name="call", description="Me chama pra call de voz que você tá.")
async def call_slash(interaction: discord.Interaction):
    """Versão slash do >call."""
    membro = interaction.user
    if (
        interaction.guild is None
        or not isinstance(membro, discord.Member)
        or membro.voice is None
        or membro.voice.channel is None
    ):
        await interaction.response.send_message(
            "você precisa estar em uma call de voz para eu entrar!", ephemeral=True
        )
        return
    canal = membro.voice.channel
    try:
        permissoes = canal.permissions_for(interaction.guild.me)
        if not permissoes.connect:
            await interaction.response.send_message(
                f"não tenho permissão de **conectar** no canal **{canal.name}**!",
                ephemeral=True,
            )
            return
        vc = interaction.guild.voice_client
        if vc is not None:
            await vc.move_to(canal)
        else:
            await canal.connect()
        await interaction.response.send_message(f"tô na call **{canal.name}**! 🎧")
    except Exception as erro:
        log.exception("falha ao entrar na call (slash)")
        texto = f"❌ não consegui entrar na call: `{type(erro).__name__}`"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(texto, ephemeral=True)
            else:
                await interaction.response.send_message(texto, ephemeral=True)
        except discord.DiscordException:
            pass


# sair
@bot.command(name="sair")
async def sair(ctx):
    """sai da call de voz."""
    vc = ctx.voice_client
    if vc is None:
        await ctx.send("não estou em call")
        return
    await vc.disconnect()
    await ctx.send("saí da call! 👋")


@bot.tree.command(name="sair", description="Tira o bot da call de voz.")
async def sair_slash(interaction: discord.Interaction):
    """Versão slash do >sair."""
    vc = interaction.guild.voice_client if interaction.guild else None
    if vc is None:
        await interaction.response.send_message("não estou em call", ephemeral=True)
        return
    await vc.disconnect()
    await interaction.response.send_message("saí da call! 👋")


async def main():
    if not TOKEN:
        log.error("TOKEN nao encontrado — defina no .env ou nas variaveis de ambiente")
        sys.exit(1)

    database.init()
    log.info("banco de dados pronto")

    async with bot:
        for cog in COGS:
            await bot.load_extension(cog)
            log.info("cog carregada: %s", cog)

        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
