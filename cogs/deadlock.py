# isso aq e o cantinho do deadlock (o jogo da valve) no bot.
# stats vem da deadlock-api gratis: rank, hero-stats, match-history, steam.
# sem numero inventado: se a api nao tem, o bot fala que nao tem.

import asyncio
import concurrent.futures
import io
import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

import data
import deadlock_api
import deadlock_card
import visual
from cogs import daily

log = logging.getLogger("alt.deadlock")

# ─── vinculo ───

# menção <@123> ou id cru de discord dentro do >stats.
_MENCAO = re.compile(r"<@!?(\d+)>")
# tokens que ligam o modo 7 dias / 1 dia no prefixo.
_TOKENS_7D = {"7d", "7dias", "7-dias", "semana", "week"}
_TOKENS_1D = {"1d", "1dia", "1-dia", "dia", "hoje", "today"}


def _embed_vinculo() -> discord.Embed:
    # sem vínculo nao tem rank nem stats: pede pra vincular e explica.
    return discord.Embed(
        title=f"{visual.DEADLOCK} vincule sua conta do deadlock",
        description=(
            "pra usar esse comando vc precisa conectar sua conta da steam.\n\n"
            "é rápido: usa `>vincular` com seu id, link ou nome da steam\n"
            "ou aperta o botão aqui embaixo. leva menos de um minuto\n"
            "e seu rank, stats e cargos passam a funcionar sozinhos."
        ),
        color=visual.PRIMARY,
    )


class VincularModal(discord.ui.Modal, title="vincular deadlock"):
    # modal do botão: pede o steam em texto livre.
    steam = discord.ui.TextInput(
        label="seu steam (id, link ou nome)",
        placeholder="ex: 842141322 ou https://steamcommunity.com/profiles/...",
        required=True,
        max_length=120,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            texto = str(self.steam.value or "").strip()
            if not texto:
                await interaction.response.send_message(
                    "me fala seu id, link ou nome da steam!", ephemeral=True
                )
                return
            account_id, _ = await asyncio.to_thread(deadlock_api.resolver_steam, texto)
            await asyncio.to_thread(
                data.vincular_deadlock, interaction.user.id, account_id
            )
            perfil = await asyncio.to_thread(
                deadlock_api.buscar_steam_profile, account_id
            )
            link = perfil.get("profileurl") or (
                f"https://steamcommunity.com/profiles/{deadlock_api.account_para_steam64(account_id)}"
            )
            nome = perfil.get("personaname") or "conta"
            await interaction.response.send_message(
                f"{visual.DEADLOCK} {nome} vinculado! {link}\n"
                "agora é só usar `>stats` ou `/stats`.",
                ephemeral=True,
            )
        except deadlock_api.DeadlockAPIError:
            await interaction.response.send_message(
                "não achei esse perfil na steam. confere o id, link ou nome e tenta de novo.",
                ephemeral=True,
            )
        except Exception:
            await interaction.response.send_message(
                "deu ruim ao vincular, tenta de novo em uns segundos.", ephemeral=True
            )


class VincularView(discord.ui.View):
    # botão embaixo do aviso de vínculo.
    def __init__(self, timeout: float = 180):
        super().__init__(timeout=timeout)

    @discord.ui.button(label="vincular conta", style=discord.ButtonStyle.primary)
    async def vincular(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ):
        await interaction.response.send_modal(VincularModal())


# ─── stats ───


def _separar_args_stats(texto: str) -> tuple[str | None, str]:
    # ">stats @alguem 7d" -> (alvo, periodo). periodo: 1d, 7d ou geral.
    tokens = (texto or "").split()
    periodo = "geral"
    resto = []
    for t in tokens:
        baixo = t.strip().lower()
        if baixo in _TOKENS_7D:
            periodo = "7d"
        elif baixo in _TOKENS_1D:
            periodo = "1d"
        else:
            resto.append(t)
    alvo = " ".join(resto).strip() or None
    return alvo, periodo


def _carregar_stats(account_id: int, periodo: str) -> dict:
    # tudo que o embed precisa, numa thread só pra nao travar o loop.
    # as chamadas sao independentes: vao juntas em paralelo.
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        f_rank = ex.submit(deadlock_api.buscar_rank, account_id)
        f_perfil = ex.submit(deadlock_api.buscar_steam_profile, account_id)
        f_heroes = ex.submit(deadlock_api.buscar_hero_assets)
        f_ranks = ex.submit(deadlock_api.buscar_rank_assets)
        if periodo in ("7d", "1d"):
            historico = ex.submit(deadlock_api.buscar_match_history, account_id).result()
            resumo = deadlock_api.resumo_7d(
                historico,
                dias=1 if periodo == "1d" else 7,
            )
        else:
            historico = []
            resumo = deadlock_api.resumo_geral(
                ex.submit(deadlock_api.buscar_hero_stats, account_id).result()
            )
        rank = f_rank.result()
        perfil = f_perfil.result()
        hero_assets = f_heroes.result()
        rank_assets = f_ranks.result()
    tier = int(rank.get("rank", 0) or 0)
    sub = int(rank.get("subrank", 0) or 0)
    nome_rank = (rank_assets.get(tier) or {}).get("nome", "Obscurus")
    if tier <= 0:
        rank_txt = "obscurus"
    else:
        rank_txt = f"{nome_rank} {sub}".strip()
    return {
        "persona": perfil.get("personaname") or f"steam {account_id}",
        "profileurl": perfil.get("profileurl")
        or f"https://steamcommunity.com/profiles/{deadlock_api.account_para_steam64(account_id)}",
        "rank_txt": rank_txt,
        "rank_emoji": visual.deadlock_rank_emoji(nome_rank),
        "tier": tier,
        "rank_img": (rank_assets.get(tier) or {}).get("imagem"),
        "resumo": resumo,
        "historico": historico,
        "heroes": {hid: v["nome"] for hid, v in hero_assets.items()},
        "hero_assets": hero_assets,
        "retratos": {hid: v["retrato"] for hid, v in hero_assets.items()},
    }


async def _anexar_card(
    pacote: dict, periodo: str, embed: discord.Embed
) -> discord.File | None:
    # tenta o card png; se falhar ou demorar, o texto segue sozinho.
    try:
        png = await asyncio.wait_for(
            asyncio.to_thread(deadlock_card.render, pacote, periodo), timeout=20
        )
        arquivo = discord.File(io.BytesIO(png), filename="deadlock_stats.png")
        embed.set_image(url="attachment://deadlock_stats.png")
        return arquivo
    except asyncio.TimeoutError:
        log.warning("deadlock: card demorou, vai so texto")
        return None
    except Exception:
        log.exception("deadlock: card falhou, vai so texto")
        return None


def _embed_stats_geral(pacote: dict) -> discord.Embed:
    r = pacote["resumo"]
    linhas = [
        f"partidas: **{r['partidas']}** · vitórias: **{r['vitorias']}** · win rate: **{r['winrate']:.1f}%**",
        f"k / d / a: **{r['k']} / {r['d']} / {r['a']}** · kda **{r['kda']:.2f}**",
    ]
    top = []
    for hid, m, w in r["top"]:
        nome = pacote["heroes"].get(hid, f"heroi {hid}")
        top.append(f"{visual.deadlock_hero_emoji(nome)}{nome} — {m} partidas, {w} vitórias")
    desc = "\n".join(linhas)
    if top:
        desc += "\n\n**heróis principais**\n" + "\n".join(top)
    if not r["partidas"]:
        desc += "\n\nsem partidas registradas na api pra essa conta."
    embed = discord.Embed(
        title=f"{pacote['rank_emoji']}{pacote['persona']} · {pacote['rank_txt']}",
        description=desc,
        color=visual.PRIMARY,
    )
    embed.set_footer(text=visual.FOOTER)
    return embed


def _embed_stats_7d(pacote: dict, periodo: str = "7d") -> discord.Embed:
    r = pacote["resumo"]
    nome_top = pacote["heroes"].get(r["heroi_top"], f"heroi {r['heroi_top']}")
    vazio = "sem partidas hoje." if periodo == "1d" else "sem partidas nos últimos 7 dias."
    desc = (
        f"partidas concluídas: **{r['partidas']}** "
        f"({r['vitorias']} vitórias, {r['derrotas']} derrotas)\n"
        f"k / d / a: **{r['k']} / {r['d']} / {r['a']}** · kda **{r['kda']:.2f}**"
    )
    if r["heroi_top_qtd"]:
        desc += f"\nherói mais jogado: {visual.deadlock_hero_emoji(nome_top)}{nome_top} ({r['heroi_top_qtd']} partidas)"
    if not r["partidas"]:
        desc += f"\n\n{vazio}"
    embed = discord.Embed(
        title=f"{pacote['rank_emoji']}{pacote['persona']} · {pacote['rank_txt']} · {periodo}",
        description=desc,
        color=visual.PRIMARY,
    )
    embed.set_footer(text=visual.FOOTER)
    return embed


async def _anexar_card_rank(
    pacote: dict, info: dict, embed: discord.Embed
) -> discord.File | None:
    # tenta o card do rank; se falhar ou demorar, o texto segue sozinho.
    try:
        png = await asyncio.wait_for(
            asyncio.to_thread(deadlock_card.render_rank, pacote, info), timeout=20
        )
        arquivo = discord.File(io.BytesIO(png), filename="deadlock_rank.png")
        embed.set_image(url="attachment://deadlock_rank.png")
        return arquivo
    except asyncio.TimeoutError:
        log.warning("deadlock: card de rank demorou, vai so texto")
        return None
    except Exception:
        log.exception("deadlock: card de rank falhou, vai so texto")
        return None


def _embed_rank(pacote: dict, info: dict) -> discord.Embed:
    if info.get("obscurus"):
        desc = "em placement: jogue ranqueadas pra ganhar rank!"
    elif info.get("topo"):
        desc = "topo do eternus. sem próximo, só lenda."
    else:
        desc = (
            f"`{info.get('atual', 0)} / 1000` pontos\n"
            f"faltam **{info.get('falta', 0)}** pontos pro próximo: **{info.get('proximo_txt', '')}**"
        )
    embed = discord.Embed(
        title=f"{pacote['rank_emoji']}{pacote['persona']} · {info.get('rank_txt', 'obscurus')}",
        description=desc,
        color=visual.PRIMARY,
    )
    embed.set_footer(text=visual.FOOTER)
    return embed


async def _resolver_steam_do_stats(
    guild: discord.Guild | None,
    autor_id: int,
    membro: discord.Member | None,
    steam_txt: str | None,
    alvo_txt: str | None,
) -> tuple[int | None, str | None]:
    # ordem: steam explícito > membro mencionado > vínculo próprio.
    # retorna (account_id, aviso). aviso setado = manda embed de vínculo.
    if steam_txt:
        try:
            account_id, _ = await asyncio.to_thread(
                deadlock_api.resolver_steam, steam_txt
            )
            return account_id, None
        except deadlock_api.DeadlockAPIError:
            return None, "não achei esse perfil na steam."
    if membro is not None:
        link = await asyncio.to_thread(data.buscar_deadlock, membro.id)
        if link is None:
            return None, "vínculo"
        return link, None
    if alvo_txt:
        # menção ou id de discord no prefixo
        m = _MENCAO.search(alvo_txt)
        candidato = m.group(1) if m else alvo_txt.strip()
        if guild is not None and re.fullmatch(r"\d{15,20}", candidato):
            achado = guild.get_member(int(candidato))
            if achado is not None:
                link = await asyncio.to_thread(data.buscar_deadlock, achado.id)
                if link is None:
                    return None, "vínculo"
                return link, None
        try:
            account_id, _ = await asyncio.to_thread(
                deadlock_api.resolver_steam, alvo_txt
            )
            return account_id, None
        except deadlock_api.DeadlockAPIError:
            return None, "não achei esse perfil na steam."
    link = await asyncio.to_thread(data.buscar_deadlock, autor_id)
    if link is None:
        return None, "vínculo"
    return link, None


# ─── texto do >deadlock ───


def _texto_deadlock() -> str:
    # hub do deadlock: o chamado + onde ficam stats geral e semanal.
    return (
        "o shooter da valve que a comunidade joga.\n"
        "chama a galera na call e bora.\n\n"
        f"{visual.AXOLOTL} vincula sua steam com `>vincular`\n"
        "e usa `>stats` pra ver rank, win rate e herois.\n"
        "`>stats 1d` mostra as partidas do dia, `>stats 7d` o resumo semanal."
    )


class Deadlock(commands.Cog, name="Deadlock"):
    """deadlock: vínculo, stats geral e resumo semanal."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ─── >deadlock ───
    @commands.command(name="deadlock")
    async def deadlock(self, ctx: commands.Context):
        """hub do deadlock: vincular, stats geral, 1d e resumo semanal."""
        embed = discord.Embed(
            title=f"{visual.DEADLOCK} Deadlock",
            description=_texto_deadlock(),
            color=visual.PRIMARY,
        )
        embed.set_footer(text=visual.FOOTER)
        await ctx.send(embed=embed)

    # ─── /deadlock ───
    @app_commands.command(
        name="deadlock", description="deadlock: vincular, stats, 1d e resumo semanal."
    )
    async def deadlock_slash(self, interaction: discord.Interaction):
        """versão slash do >deadlock."""
        embed = discord.Embed(
            title=f"{visual.DEADLOCK} Deadlock",
            description=_texto_deadlock(),
            color=visual.PRIMARY,
        )
        embed.set_footer(text=visual.FOOTER)
        await interaction.response.send_message(embed=embed)

    # ─── >vincular ───
    @commands.command(name="vincular")
    async def vincular(self, ctx: commands.Context, *, steam: str = ""):
        """vincula sua steam: >vincular <id, link ou nome>."""
        texto = (steam or "").strip()
        if not texto:
            await ctx.send(embed=_embed_vinculo(), view=VincularView())
            return
        try:
            account_id, _ = await asyncio.to_thread(deadlock_api.resolver_steam, texto)
        except deadlock_api.DeadlockAPIError:
            await ctx.send("não achei esse perfil na steam. confere e tenta de novo.")
            return
        await asyncio.to_thread(data.vincular_deadlock, ctx.author.id, account_id)
        perfil = await asyncio.to_thread(deadlock_api.buscar_steam_profile, account_id)
        link = perfil.get("profileurl") or (
            f"https://steamcommunity.com/profiles/{deadlock_api.account_para_steam64(account_id)}"
        )
        nome = perfil.get("personaname") or "conta"
        await ctx.send(f"{visual.DEADLOCK} {nome} vinculado! {link}")

    # ─── /vincular ───
    @app_commands.command(name="vincular", description="vincula sua steam ao discord.")
    @app_commands.describe(steam="id, link ou nome da steam")
    async def vincular_slash(self, interaction: discord.Interaction, steam: str):
        """versão slash do >vincular."""
        try:
            account_id, _ = await asyncio.to_thread(deadlock_api.resolver_steam, steam)
        except deadlock_api.DeadlockAPIError:
            await interaction.response.send_message(
                "não achei esse perfil na steam. confere e tenta de novo.",
                ephemeral=True,
            )
            return
        await asyncio.to_thread(data.vincular_deadlock, interaction.user.id, account_id)
        perfil = await asyncio.to_thread(deadlock_api.buscar_steam_profile, account_id)
        link = perfil.get("profileurl") or (
            f"https://steamcommunity.com/profiles/{deadlock_api.account_para_steam64(account_id)}"
        )
        nome = perfil.get("personaname") or "conta"
        await interaction.response.send_message(
            f"{visual.DEADLOCK} {nome} vinculado! {link}"
        )

    # ─── >desvincular ───
    @commands.command(name="desvincular")
    async def desvincular(self, ctx: commands.Context):
        """tira o vínculo da sua steam."""
        saiu = await asyncio.to_thread(data.desvincular_deadlock, ctx.author.id)
        await ctx.send(
            "vínculo removido." if saiu else "vc nem tinha vínculo. usa `>vincular`."
        )

    # ─── /desvincular ───
    @app_commands.command(name="desvincular", description="tira o vínculo da sua steam.")
    async def desvincular_slash(self, interaction: discord.Interaction):
        """versão slash do >desvincular."""
        saiu = await asyncio.to_thread(data.desvincular_deadlock, interaction.user.id)
        await interaction.response.send_message(
            "vínculo removido." if saiu else "vc nem tinha vínculo. usa `/vincular`.",
            ephemeral=True,
        )

    # ─── >stats ───
    @commands.command(name="stats")
    async def stats(self, ctx: commands.Context, *, args: str = ""):
        """stats do deadlock: >stats [@membro|steam] [1d|7d]."""
        alvo_txt, periodo = _separar_args_stats(args)
        account_id, aviso = await _resolver_steam_do_stats(
            ctx.guild, ctx.author.id, None, None, alvo_txt
        )
        if account_id is None:
            if aviso == "vínculo":
                await ctx.send(embed=_embed_vinculo(), view=VincularView())
            else:
                await ctx.send(aviso or "deu ruim ao resolver a conta.")
            return
        try:
            async with ctx.typing():
                pacote = await asyncio.to_thread(_carregar_stats, account_id, periodo)
        except deadlock_api.DeadlockAPIError as e:
            await ctx.send(f"deu ruim buscando na api: `{e}`. tenta de novo em uns segundos.")
            return
        # quest oportunista: historico ja veio, sem chamada extra.
        if pacote.get("historico"):
            dono = await asyncio.to_thread(data.buscar_discord_por_steam, account_id)
            if dono is not None:
                await daily.avaliar_deadlock(dono, account_id, pacote["historico"])
        embed = (
            _embed_stats_7d(pacote, periodo)
            if periodo in ("7d", "1d")
            else _embed_stats_geral(pacote)
        )
        arquivo = await _anexar_card(pacote, periodo, embed)
        await ctx.send(embed=embed, file=arquivo)

    # ─── /stats ───
    @app_commands.command(name="stats", description="stats do deadlock (geral, 1 dia ou 7 dias).")
    @app_commands.describe(
        membro="ver o stats de outro membro (precisa de vínculo)",
        steam="id, link ou nome da steam (consulta avulsa, sem salvar)",
        periodo="geral, 1 dia ou últimos 7 dias",
    )
    @app_commands.choices(
        periodo=[
            app_commands.Choice(name="geral", value="geral"),
            app_commands.Choice(name="1 dia", value="1d"),
            app_commands.Choice(name="7 dias", value="7d"),
        ]
    )
    async def stats_slash(
        self,
        interaction: discord.Interaction,
        membro: discord.Member | None = None,
        steam: str | None = None,
        periodo: str = "geral",
    ):
        """versão slash do >stats."""
        if periodo not in ("geral", "7d", "1d"):
            periodo = "geral"
        await interaction.response.defer()
        account_id, aviso = await _resolver_steam_do_stats(
            interaction.guild, interaction.user.id, membro, steam, None
        )
        if account_id is None:
            if aviso == "vínculo":
                await interaction.followup.send(
                    embed=_embed_vinculo(), view=VincularView()
                )
            else:
                await interaction.followup.send(aviso or "deu ruim ao resolver a conta.")
            return
        try:
            pacote = await asyncio.to_thread(_carregar_stats, account_id, periodo)
        except deadlock_api.DeadlockAPIError as e:
            await interaction.followup.send(
                f"deu ruim buscando na api: `{e}`. tenta de novo em uns segundos."
            )
            return
        # quest oportunista: historico ja veio, sem chamada extra.
        if pacote.get("historico"):
            dono = await asyncio.to_thread(data.buscar_discord_por_steam, account_id)
            if dono is not None:
                await daily.avaliar_deadlock(dono, account_id, pacote["historico"])
        embed = (
            _embed_stats_7d(pacote, periodo)
            if periodo in ("7d", "1d")
            else _embed_stats_geral(pacote)
        )
        arquivo = await _anexar_card(pacote, periodo, embed)
        await interaction.followup.send(embed=embed, file=arquivo)

    # ─── >rank ───
    @commands.command(name="rank")
    async def rank(self, ctx: commands.Context, *, args: str = ""):
        """rank do deadlock com progresso pro próximo."""
        alvo_txt, _periodo = _separar_args_stats(args)
        account_id, aviso = await _resolver_steam_do_stats(
            ctx.guild, ctx.author.id, None, None, alvo_txt
        )
        if account_id is None:
            if aviso == "vínculo":
                await ctx.send(embed=_embed_vinculo(), view=VincularView())
            else:
                await ctx.send(aviso or "deu ruim ao resolver a conta.")
            return
        try:
            rank, ranks, perfil = await asyncio.gather(
                asyncio.to_thread(deadlock_api.buscar_rank, account_id),
                asyncio.to_thread(deadlock_api.buscar_ranks),
                asyncio.to_thread(deadlock_api.buscar_steam_profile, account_id),
            )
        except deadlock_api.DeadlockAPIError as e:
            await ctx.send(f"deu ruim buscando na api: `{e}`. tenta de novo em uns segundos.")
            return
        pacote = {
            "persona": perfil.get("personaname") or f"steam {account_id}",
            "rank_emoji": visual.deadlock_rank_emoji(ranks.get(int(rank.get("rank", 0) or 0), "")),
        }
        info = deadlock_api.info_rank(rank, deadlock_api.NOMES_PT)
        embed = _embed_rank(pacote, info)
        arquivo = await _anexar_card_rank(pacote, info, embed)
        await ctx.send(embed=embed, file=arquivo)

    # ─── /rank ───
    @app_commands.command(name="rank", description="rank do deadlock com progresso pro próximo.")
    @app_commands.describe(
        membro="ver o rank de outro membro (precisa de vínculo)",
        steam="id, link ou nome da steam (consulta avulsa, sem salvar)",
    )
    async def rank_slash(
        self,
        interaction: discord.Interaction,
        membro: discord.Member | None = None,
        steam: str | None = None,
    ):
        """versão slash do >rank."""
        await interaction.response.defer()
        account_id, aviso = await _resolver_steam_do_stats(
            interaction.guild, interaction.user.id, membro, steam, None
        )
        if account_id is None:
            if aviso == "vínculo":
                await interaction.followup.send(
                    embed=_embed_vinculo(), view=VincularView()
                )
            else:
                await interaction.followup.send(aviso or "deu ruim ao resolver a conta.")
            return
        try:
            rank, ranks, perfil = await asyncio.gather(
                asyncio.to_thread(deadlock_api.buscar_rank, account_id),
                asyncio.to_thread(deadlock_api.buscar_ranks),
                asyncio.to_thread(deadlock_api.buscar_steam_profile, account_id),
            )
        except deadlock_api.DeadlockAPIError as e:
            await interaction.followup.send(
                f"deu ruim buscando na api: `{e}`. tenta de novo em uns segundos."
            )
            return
        pacote = {
            "persona": perfil.get("personaname") or f"steam {account_id}",
            "rank_emoji": visual.deadlock_rank_emoji(ranks.get(int(rank.get("rank", 0) or 0), "")),
        }
        info = deadlock_api.info_rank(rank, deadlock_api.NOMES_PT)
        embed = _embed_rank(pacote, info)
        arquivo = await _anexar_card_rank(pacote, info, embed)
        await interaction.followup.send(embed=embed, file=arquivo)


async def setup(bot: commands.Bot):
    await bot.add_cog(Deadlock(bot))
