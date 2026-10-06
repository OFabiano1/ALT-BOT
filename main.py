import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

import asyncio
import inspect
import logging
import os
import sys
import time
from pathlib import Path

import visual
import data

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
    "cogs.deadlock",
)

# so liga o minimo: sem `guild_messages` o `>` nem chega,
# sem `message_content` chega sem texto. `members` e o texto
# sao privilegiados, tem que ligar no developer portal.
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
    # sem GUILD_ID o sync é global e pode levar até uma hora para
    # propagar. Apontando para o guild, vale em segundos.
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        synced = await bot.tree.sync(guild=guild)
        log.info("slash commands sincronizados no guild: %d", len(synced))
    else:
        log.warning("GUILD_ID nao definido — sync global (pode demorar ate 1h)")
        synced = await bot.tree.sync()
        log.info("slash commands sincronizados globalmente: %d", len(synced))

    log.info("%s online — %s", bot.user, visual.FOOTER)

    # volta pras calls fixadas (sobrevive a restart e queda).
    for guild in bot.guilds:
        canal_id = await asyncio.to_thread(data.voz_fixa, guild.id)
        if canal_id is not None and guild.voice_client is None:
            try:
                canal = guild.get_channel(canal_id)
                if canal is None:
                    canal = await bot.fetch_channel(canal_id)
                await canal.connect()
                log.info("voltei pra call fixada %d", canal_id)
            except Exception:
                log.exception("nao consegui voltar pra call fixada %d", canal_id)


async def _voltar_call(guild_id: int, channel_id: int, tentativas: int = 3):
    # espera um pouco pra nao brigar com queda rapida seguida.
    await asyncio.sleep(5)
    for _ in range(tentativas):
        guild = bot.get_guild(guild_id)
        if guild is None or guild.voice_client is not None:
            return
        try:
            canal = guild.get_channel(channel_id)
            if canal is None:
                canal = await bot.fetch_channel(channel_id)
            await canal.connect()
            log.info("voltei pra call fixada %d", channel_id)
            return
        except (discord.NotFound, discord.Forbidden):
            # call sumiu ou perdi acesso: desfixa pra nao tentar pra sempre.
            await asyncio.to_thread(data.soltar_voz, guild_id)
            return
        except Exception:
            log.exception("falha ao voltar pra call, tento de novo")
            await asyncio.sleep(10)


# audio de boas-vindas: toca quando alguem entra na call do bot.
# caminho absoluto pra nao depender de onde o app foi aberto.
AUDIO_OI = Path(__file__).parent / "kkkiaimen.mp3"

# um oi a cada 30s por servidor: sem isso entra-e-sai vira spam.
OI_COOLDOWN = 30
_ultimo_oi: dict[int, float] = {}


async def _oi_quem_chegou(membro, antes, depois):
    # ignora bot (senao um bot entrando vira festa infinita).
    if membro.bot:
        return
    vc = membro.guild.voice_client
    if vc is None or not vc.is_connected():
        return
    # so conta entrar na call do bot: sair ou mutar nao conta.
    if depois.channel is None or depois.channel.id != vc.channel.id:
        return
    if antes.channel is not None and antes.channel.id == vc.channel.id:
        return
    agora = time.monotonic()
    if agora - _ultimo_oi.get(membro.guild.id, 0) < OI_COOLDOWN:
        return
    if vc.is_playing():
        return
    if not AUDIO_OI.exists():
        log.warning("audio de boas-vindas nao encontrado: %s", AUDIO_OI)
        return
    try:
        vc.play(discord.FFmpegPCMAudio(str(AUDIO_OI)))
        _ultimo_oi[membro.guild.id] = agora
        log.info("oi pra %s na call", membro.display_name)
    except FileNotFoundError:
        log.error("ffmpeg nao encontrado no host — sem audio na call")
    except Exception:
        log.exception("nao consegui tocar o audio de boas-vindas")


@bot.event
async def on_voice_state_update(membro, antes, depois):
    # queda do proprio bot: volta pra fixada.
    if bot.user is not None and membro.id == bot.user.id:
        if depois.channel is not None or antes.channel is None:
            return
        canal_id = await asyncio.to_thread(data.voz_fixa, membro.guild.id)
        if canal_id is None:
            return
        log.info("cai da call, voltando pra fixada %d", canal_id)
        asyncio.create_task(_voltar_call(membro.guild.id, canal_id))
        return
    # boas-vindas: alguem entrou na call onde o bot esta, toca o audio.
    await _oi_quem_chegou(membro, antes, depois)


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
    # mostra a causa raiz (ex: Forbidden) em vez do wrapper genérico.
    original = getattr(erro, "original", erro)
    log.exception("comando %s falhou: %s", ctx.command, original)
    # erro visível no chat — comando que falha em silêncio é indepurável.
    try:
        await ctx.send(f"deu ruim: `{type(original).__name__}: {original}`")
    except discord.DiscordException:
        pass


@bot.tree.error
async def on_tree_error(
    interaction: discord.Interaction, erro: app_commands.AppCommandError
):
    """mesma visibilidade pros slash: nada falha em silêncio."""
    if isinstance(erro, app_commands.CommandOnCooldown):
        texto = f"calma! tenta de novo em **{erro.retry_after:.0f}s**."
    elif isinstance(erro, app_commands.CheckFailure):
        texto = "sem permissão pra isso!"
    else:
        original = getattr(erro, "original", erro)
        log.exception("slash /%s falhou", interaction.command_name)
        texto = f"deu ruim: `{type(original).__name__}: {original}`"
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
    await ctx.send(f"{visual.AXOLOTL} Axolotl!")


@bot.tree.command(name="axolotl", description="a assinatura do axolote.")
async def axolotl_slash(interaction: discord.Interaction):
    await interaction.response.send_message(f"{visual.AXOLOTL} Axolotl!")


# restart
async def _reiniciar():
    # execv troca a imagem do processo em vez de spawnar outro
    # (os.system deixava um bot zumbi vivo no deploy).
    await bot.close()
    sys.stdout.flush()
    os.execv(sys.executable, [sys.executable, *sys.argv])


@bot.command()
@commands.is_owner()
async def restart(ctx):
    await ctx.send("reiniciando...")
    await _reiniciar()


@bot.tree.command(name="restart", description="[dono] reinicia o bot.")
async def restart_slash(interaction: discord.Interaction):
    info = await bot.application_info()
    if interaction.user.id != info.owner.id:
        await interaction.response.send_message("sem permissão pra isso!", ephemeral=True)
        return
    await interaction.response.send_message("reiniciando...")
    await _reiniciar()


# latencia
@bot.command()
async def ping(ctx):
    await ctx.send(f"pong!: {round(bot.latency * 1000)}ms")


# latencia (slash)
@bot.tree.command(name="ping", description="mostra a latência do bot.")
async def slash_ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"pong!: {round(bot.latency * 1000)}ms")


# ajuda
ORDEM_AJUDA = (
    "Geral",
    "Deadlock",
    "Níveis",
    "jogos",
    "Economia",
    "tickets",
    "Mudae",
    "Halloween",
    "Status",
)

# banner da ajuda. padrao embutido, mas link de cdn expira:
# quando cair, bota o link novo no env que ele prevalece.
AJUDA_BANNER_URL = os.getenv(
    "AJUDA_BANNER_URL",
    "https://cdn.discordapp.com/attachments/1017344173843693628/1556923654787309628/ajuda.png?backend=b2&ex=6ac5eda5&is=6ac49c25&hm=bfbe7708bd12f3485c2ffd864d7092b5b57e5cb80c87c99eccf815a8342be1f9&",
)

# emoji de cada secao (pela titulo exibido).
CATEGORIA_EMOJIS = {
    "Geral": "✨",
    "Deadlock": "🎮",
    "Níveis": "⭐",
    "Jogos": "🎲",
    "Economia": "💎",
    "Tickets": "🎟️",
    "Mudae": "🃏",
    "Halloween": "🎃",
}


def _grupos_comandos() -> dict[str, list[tuple[str, str | None]]]:
    """comandos de prefixo agrupados: {categoria: [(nome, doc)]}."""
    grupos: dict[str, list[tuple[str, str | None]]] = {}
    for cmd in bot.commands:
        if cmd.name in ("ajuda", "help") or cmd.hidden:
            continue
        chave = cmd.cog.qualified_name if cmd.cog else "Geral"
        grupos.setdefault(chave, []).append((cmd.name, cmd.short_doc))
    return grupos


def _slash_por_nome() -> dict[str, app_commands.Command]:
    """todos os slash indexados por nome."""
    return {c.name: c for c in bot.tree.walk_commands()}


def _categoria_slash() -> dict[str, str]:
    """nome do slash -> categoria (nome da cog ou Geral)."""
    mapa: dict[str, str] = {}
    for cog in bot.cogs.values():
        for cmd in cog.get_app_commands():
            mapa[cmd.name] = cog.qualified_name
    for nome in _slash_por_nome():
        mapa.setdefault(nome, "Geral")
    return mapa


def _linhas_ajuda(travas: dict[str, str]) -> list[tuple[str, list[str]]]:
    """seções ordenadas [(titulo, linhas)]. `>` e `/` gêmeos na mesma linha."""
    prefix = _grupos_comandos()
    slash = _slash_por_nome()
    cat_slash = _categoria_slash()
    slash_por_cat: dict[str, list[app_commands.Command]] = {}
    for nome, cmd in slash.items():
        if nome == "ajuda":
            continue
        slash_por_cat.setdefault(cat_slash.get(nome, "Geral"), []).append(cmd)

    chaves = [c for c in ORDEM_AJUDA if c in prefix or c in slash_por_cat]
    chaves += [c for c in list(prefix) + list(slash_por_cat) if c not in chaves]
    secoes: list[tuple[str, list[str]]] = []
    for chave in chaves:
        linhas: list[str] = []
        fundidos: set[str] = set()
        for nome, doc in sorted(prefix.get(chave, [])):
            gemeo = slash.get(nome)
            if gemeo is not None and cat_slash.get(nome) == chave:
                uso = f"`>{nome}` `/{nome}`"
                fundidos.add(nome)
                trava = travas.get(f">{nome}", "") or travas.get(f"/{nome}", "")
            else:
                uso = f"`>{nome}`"
                trava = travas.get(f">{nome}", "")
            if trava:
                uso += f" {trava}"
            if doc:
                uso += f" — {doc}"
            linhas.append(uso)
        for cmd in sorted(slash_por_cat.get(chave, []), key=lambda c: c.name):
            if cmd.name in fundidos:
                continue
            uso = f"`/{cmd.name}`"
            trava = travas.get(f"/{cmd.name}", "")
            if trava:
                uso += f" {trava}"
            if cmd.description:
                uso += f" — {cmd.description}"
            linhas.append(uso)
        if linhas:
            secoes.append((visual.CATEGORIAS.get(chave, chave), linhas))
    return secoes


def _embed_ajuda(secoes: list[tuple[str, list[str]]]) -> discord.Embed:
    """monta o embed da ajuda. Usado pelo `>` e pelo `/`."""
    embed = discord.Embed(
        title=f"{visual.AXOLOTL} Comandos do ALT",
        description="funciono com `>` e com `/` — usa o que preferir.",
        color=visual.PRIMARY,
    )
    for titulo, linhas in secoes:
        embed.add_field(name=titulo, value="\n".join(linhas), inline=False)
    if AJUDA_BANNER_URL:
        embed.set_image(url=AJUDA_BANNER_URL)
    embed.set_footer(text=visual.FOOTER)
    return embed


def _embed_ajuda_resumo() -> discord.Embed:
    """capa da ajuda: banner + botoes por categoria."""
    embed = discord.Embed(
        title=f"{visual.AXOLOTL} Comandos do ALT",
        description=(
            "funciono com `>` e com `/` — usa o que preferir.\n"
            "escolhe uma categoria aqui embaixo."
        ),
        color=visual.PRIMARY,
    )
    if AJUDA_BANNER_URL:
        embed.set_image(url=AJUDA_BANNER_URL)
    embed.set_footer(text=visual.FOOTER)
    return embed


def _embed_ajuda_secao(titulo: str, linhas: list[str]) -> discord.Embed:
    """uma categoria so: titulo + comandos + banner."""
    emoji = CATEGORIA_EMOJIS.get(titulo, "")
    nome = f"{emoji} {titulo}".strip()
    embed = discord.Embed(
        title=f"{visual.AXOLOTL} {nome}",
        description="\n".join(linhas),
        color=visual.PRIMARY,
    )
    if AJUDA_BANNER_URL:
        embed.set_image(url=AJUDA_BANNER_URL)
    embed.set_footer(text=visual.FOOTER)
    return embed


class AjudaView(discord.ui.View):
    """botoes por categoria da ajuda. expira em 3min."""

    def __init__(self, secoes: list[tuple[str, list[str]]]):
        super().__init__(timeout=180)
        self._mapa = dict(secoes)
        for titulo, _linhas in secoes:
            self.add_item(self._botao_categoria(titulo))
        tudo = discord.ui.Button(
            label="tudo",
            emoji="📋",
            style=discord.ButtonStyle.primary,
            custom_id="ajuda:tudo",
        )

        async def mostrar_tudo(interaction: discord.Interaction):
            await interaction.response.edit_message(
                embed=_embed_ajuda(list(self._mapa.items())), view=self
            )

        tudo.callback = mostrar_tudo
        self.add_item(tudo)
        inicio = discord.ui.Button(
            label="início",
            emoji="🏠",
            style=discord.ButtonStyle.secondary,
            custom_id="ajuda:inicio",
        )

        async def voltar(interaction: discord.Interaction):
            await interaction.response.edit_message(
                embed=_embed_ajuda_resumo(), view=self
            )

        inicio.callback = voltar
        self.add_item(inicio)

    def _botao_categoria(self, titulo: str) -> discord.ui.Button:
        botao = discord.ui.Button(
            label=titulo,
            emoji=CATEGORIA_EMOJIS.get(titulo),
            style=discord.ButtonStyle.secondary,
            custom_id=f"ajuda:cat:{titulo}",
        )

        async def mostrar(interaction: discord.Interaction, alvo=titulo):
            await interaction.response.edit_message(
                embed=_embed_ajuda_secao(alvo, self._mapa[alvo]), view=self
            )

        botao.callback = mostrar
        return botao


@bot.command(name="ajuda")
async def ajuda(ctx):
    """mostra todos os comandos do bot."""

    async def permissao(cmd: commands.Command) -> str:
        """rótulo de bloqueio se o autor não puder usar o comando."""
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
                return "restrito"
            if resultado is False:
                return "restrito"
        return ""

    travas: dict[str, str] = {}
    for cmds in _grupos_comandos().values():
        for nome, _doc in cmds:
            cmd = bot.get_command(nome)
            trava = await permissao(cmd) if cmd else ""
            if trava:
                travas[f">{nome}"] = trava
    await ctx.send(embed=_embed_ajuda_resumo(), view=AjudaView(_linhas_ajuda(travas)))


@bot.tree.command(name="ajuda", description="mostra todos os comandos do bot.")
async def ajuda_slash(interaction: discord.Interaction):
    """versão slash da ajuda (efêmera — só você vê)."""
    travas: dict[str, str] = {}
    for cmd in bot.tree.walk_commands():
        if cmd.name == "ajuda":
            continue
        for check in cmd.checks:
            try:
                resultado = check(interaction)
                if inspect.isawaitable(resultado):
                    resultado = await resultado
            except app_commands.AppCommandError:
                travas[f"/{cmd.name}"] = "restrito"
                break
            if resultado is False:
                travas[f"/{cmd.name}"] = "restrito"
                break
    await interaction.response.send_message(
        embed=_embed_ajuda_resumo(),
        view=AjudaView(_linhas_ajuda(travas)),
        ephemeral=True,
    )


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
            return

        if ctx.voice_client is not None:
            await ctx.voice_client.move_to(canal)
            await asyncio.to_thread(data.fixar_voz, ctx.guild.id, canal.id)
            await ctx.send(f"fui pra **{canal.name}**!")
            return

        await canal.connect()
        await asyncio.to_thread(data.fixar_voz, ctx.guild.id, canal.id)
        await ctx.send(f"tô na call **{canal.name}**!")
    except Exception as erro:
        log.exception("falha ao entrar na call")
        await ctx.send(f"não consegui entrar na call: `{type(erro).__name__}`")


@bot.tree.command(name="call", description="me chama pra call de voz que você tá.")
async def call_slash(interaction: discord.Interaction):
    """versão slash do >call."""
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
        await asyncio.to_thread(data.fixar_voz, interaction.guild.id, canal.id)
        await interaction.response.send_message(f"tô na call **{canal.name}**!")
    except Exception as erro:
        log.exception("falha ao entrar na call (slash)")
        texto = f"não consegui entrar na call: `{type(erro).__name__}`"
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
    await asyncio.to_thread(data.soltar_voz, ctx.guild.id)
    await vc.disconnect()
    await ctx.send("saí da call!")


@bot.tree.command(name="sair", description="tira o bot da call de voz.")
async def sair_slash(interaction: discord.Interaction):
    """versão slash do >sair."""
    vc = interaction.guild.voice_client if interaction.guild else None
    if vc is None:
        await interaction.response.send_message("não estou em call", ephemeral=True)
        return
    await asyncio.to_thread(data.soltar_voz, interaction.guild.id)
    await vc.disconnect()
    await interaction.response.send_message("saí da call!")


async def main():
    if not TOKEN:
        log.error("TOKEN nao encontrado — defina no .env ou nas variaveis de ambiente")
        sys.exit(1)

    data.init()
    log.info("banco de dados pronto")

    async with bot:
        for cog in COGS:
            await bot.load_extension(cog)
            log.info("cog carregada: %s", cog)

        # identifica o build no log: se o shardcloud nao puxou o codigo novo,
        # esses numeros nao batem com o esperado.
        log.info(
            "comandos registrados: %d prefixo, %d slash",
            len(bot.commands),
            sum(1 for _ in bot.tree.walk_commands()),
        )

        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
