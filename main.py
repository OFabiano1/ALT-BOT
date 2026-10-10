import discord
from discord import app_commands
from discord.components import MediaGalleryItem
from discord.ext import commands
from dotenv import load_dotenv

import asyncio
import inspect
import logging
import os
import sys

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
    "cogs.voz",
    "cogs.server",
    "cogs.github",
    "cogs.daily",
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
    await ctx.send(f"{visual.AXOLOTL} hello world!")


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
    "Voz",
    "Deadlock",
    "Níveis",
    "Servidor",
    "jogos",
    "Economia",
    "tickets",
    "Mudae",
    "Halloween",
    "Status",
)

# cogs que aparecem dentro de outra secao da ajuda.
FUSAO_CATEGORIAS = {
    "GitHub": "Servidor",
    "Diárias": "Servidor",
}

# banner da ajuda. padrao embutido, mas link de cdn expira:
# quando cair, bota o link novo no env que ele prevalece.
AJUDA_BANNER_URL = os.getenv(
    "AJUDA_BANNER_URL",
    "https://cdn.discordapp.com/attachments/1017344173843693628/1556923654787309628/ajuda.png?backend=b2&ex=6ac5eda5&is=6ac49c25&hm=bfbe7708bd12f3485c2ffd864d7092b5b57e5cb80c87c99eccf815a8342be1f9&",
)

# emoji de cada secao (pela titulo exibido).
CATEGORIA_EMOJIS = {
    "Geral": "✨",
    "Voz": "🔊",
    "Deadlock": "🎮",
    "Níveis": "⭐",
    "Servidor": "🖥️",
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
        chave = FUSAO_CATEGORIAS.get(chave, chave)
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
            mapa[cmd.name] = FUSAO_CATEGORIAS.get(cog.qualified_name, cog.qualified_name)
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


def _texto_resumo() -> str:
    return (
        f"**{visual.AXOLOTL} Comandos do ALT**\n"
        "funciono com `>` e com `/` — usa o que preferir.\n"
        "escolhe uma categoria aqui embaixo.\n"
        f"{visual.FOOTER}"
    )


def _texto_secao(titulo: str, linhas: list[str]) -> str:
    emoji = CATEGORIA_EMOJIS.get(titulo, "")
    nome = f"{emoji} {titulo}".strip()
    return f"**{visual.AXOLOTL} {nome}**\n" + "\n".join(linhas) + f"\n{visual.FOOTER}"


def _texto_tudo(secoes: list[tuple[str, list[str]]]) -> list[str]:
    return [
        f"**{titulo}**\n" + "\n".join(linhas) + f"\n{visual.FOOTER}"
        for titulo, linhas in secoes
    ]


def _galeria() -> discord.ui.MediaGallery | None:
    if AJUDA_BANNER_URL:
        return discord.ui.MediaGallery(MediaGalleryItem(media=AJUDA_BANNER_URL))
    return None


class AjudaLayout(discord.ui.LayoutView):
    """ajuda em container roxo. expira em 3min."""

    def __init__(self, secoes: list[tuple[str, list[str]]], estado: tuple = ("resumo",)):
        super().__init__(timeout=180)
        self._secoes = secoes
        self._mapa = dict(secoes)
        if estado[0] == "tudo":
            textos = _texto_tudo(secoes)
        elif estado[0] == "secao":
            textos = [_texto_secao(estado[1], self._mapa[estado[1]])]
        else:
            textos = [_texto_resumo()]
        filhos: list = [discord.ui.TextDisplay(t) for t in textos]
        galeria = _galeria()
        if galeria is not None:
            filhos.append(galeria)
        botoes = [self._botao_categoria(t) for t, _ in secoes]
        botoes.append(self._botao_tudo())
        botoes.append(self._botao_inicio())
        for i in range(0, len(botoes), 5):
            linha = discord.ui.ActionRow()
            for b in botoes[i : i + 5]:
                linha.add_item(b)
            filhos.append(linha)
        container = discord.ui.Container(*filhos, accent_colour=visual.PRIMARY)
        self.add_item(container)

    @classmethod
    def resumo(cls, secoes):
        return cls(secoes, ("resumo",))

    @classmethod
    def secao(cls, secoes, titulo):
        return cls(secoes, ("secao", titulo))

    @classmethod
    def tudo(cls, secoes):
        return cls(secoes, ("tudo",))

    def _botao_categoria(self, titulo: str) -> discord.ui.Button:
        botao = discord.ui.Button(
            label=titulo,
            emoji=CATEGORIA_EMOJIS.get(titulo),
            style=discord.ButtonStyle.secondary,
            custom_id=f"ajuda:cat:{titulo}",
        )

        async def mostrar(interaction: discord.Interaction, alvo=titulo):
            await interaction.response.edit_message(
                view=AjudaLayout.secao(self._secoes, alvo)
            )

        botao.callback = mostrar
        return botao

    def _botao_tudo(self) -> discord.ui.Button:
        tudo = discord.ui.Button(
            label="tudo",
            emoji="📋",
            style=discord.ButtonStyle.primary,
            custom_id="ajuda:tudo",
        )

        async def mostrar_tudo(interaction: discord.Interaction):
            await interaction.response.edit_message(view=AjudaLayout.tudo(self._secoes))

        tudo.callback = mostrar_tudo
        return tudo

    def _botao_inicio(self) -> discord.ui.Button:
        inicio = discord.ui.Button(
            label="início",
            emoji="🏠",
            style=discord.ButtonStyle.secondary,
            custom_id="ajuda:inicio",
        )

        async def voltar(interaction: discord.Interaction):
            await interaction.response.edit_message(view=AjudaLayout.resumo(self._secoes))

        inicio.callback = voltar
        return inicio


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
    await ctx.send(view=AjudaLayout.resumo(_linhas_ajuda(travas)))


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
        view=AjudaLayout.resumo(_linhas_ajuda(travas)),
        ephemeral=True,
    )


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
        # esses numeros nao batem com o esperado. o pid entrega
        # instancia zumbi (dois processos com o mesmo token).
        log.info(
            "boot pid=%d | comandos registrados: %d prefixo, %d slash",
            os.getpid(),
            len(bot.commands),
            sum(1 for _ in bot.tree.walk_commands()),
        )

        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
