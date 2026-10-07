# isso aq avisa push no chat: todo commit publico do dono em
# qualquer repo aparece la com autor, msg e status do workflow.
# poll de 5min no events do usuario (1 chamada cobre tudo) com
# etag. sem comando: nao aparece na ajuda, so trabalha.

import asyncio
import json
import logging
import os
import re
import urllib.parse
import urllib.request

import discord
from discord import app_commands
from discord.ext import commands, tasks

import data
import visual

log = logging.getLogger("alt.github")

USER = (os.getenv("GITHUB_USER") or "OFabiano1").strip()
TOKEN = (os.getenv("GITHUB_TOKEN") or "").strip()
CHANNEL_ID = int(os.getenv("GITHUB_CHANNEL_ID", "1261521924002152501") or 0)
INTERVALO_MIN = 5
MAX_POSTS = 3

BASE = "https://api.github.com"
HEADERS = {
    "User-Agent": "ALT-bot",
    "Accept": "application/vnd.github+json",
}
if TOKEN:
    # com token sobe pra 5000/h e enxerga repo privado.
    HEADERS["Authorization"] = f"Bearer {TOKEN}"

# etag por url: 304 nao conta no rate limit. corpo cacheado:
# 304 devolve o ultimo corpo em vez de None (None quebra
# quem chama: repo "some", eventos "somem").
_etags: dict[str, str] = {}
_corpos: dict[str, object] = {}


def _get(caminho: str, query: dict | None = None):
    """get com etag. retorna (dados, etag). 304 reusa o ultimo corpo."""
    qs = f"?{urllib.parse.urlencode(query)}" if query else ""
    url = f"{BASE}{caminho}{qs}"
    headers = dict(HEADERS)
    if url in _etags:
        headers["If-None-Match"] = _etags[url]
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            etag = resp.headers.get("ETag")
            if etag:
                _etags[url] = etag
            dados = json.load(resp)
            _corpos[url] = dados
            if len(_corpos) > 50:
                _corpos.pop(next(iter(_corpos)))
            return dados, etag
    except urllib.error.HTTPError as e:
        if e.code == 304 and url in _corpos:
            return _corpos[url], _etags.get(url)
        raise


def _linha_workflow(runs: list | None) -> str | None:
    if not runs:
        return None
    run = runs[0]
    nome = run.get("name", "workflow")
    if run.get("status") != "completed":
        return f"{nome}: 🟡 rodando."
    ok = run.get("conclusion") == "success"
    return f"{nome}: {'✅ passou.' if ok else '❌ falhou.'}"


async def _pushes_novos() -> list[tuple[dict, str | None]]:
    """push events ainda nao postados: [(evento, linha_workflow)]."""
    try:
        eventos, _ = await asyncio.to_thread(_get, f"/users/{USER}/events", {"per_page": 30})
    except Exception:
        log.exception("github: falha ao buscar eventos de %s", USER)
        return []
    if not eventos:
        return []
    pushes = [e for e in eventos if e.get("type") == "PushEvent"]
    if not pushes:
        return []
    algum_visto = False
    for e in pushes:
        if await asyncio.to_thread(data.viu_evento, e["id"]):
            algum_visto = True
            break
    if not algum_visto:
        # primeira vez: posta so o mais recente, marca o resto sem postar.
        # (se postasse tudo, cuspia historico; se nada, o ultimo commit sumia.)
        for e in pushes:
            await asyncio.to_thread(data.salvar_evento, e["id"])
        log.info("github: monitorando pushes de %s", USER)
        novo = pushes[0]
        repo = novo["repo"]["name"]
        try:
            runs, _ = await asyncio.to_thread(
                _get, f"/repos/{repo}/actions/runs", {"per_page": 1}
            )
            lista = runs.get("workflow_runs") if isinstance(runs, dict) else runs
            wf = _linha_workflow(lista)
        except Exception:
            log.exception("github: falha ao buscar workflow de %s", repo)
            wf = None
        return [(novo, wf)]
    novos = []
    for e in reversed(pushes):
        if await asyncio.to_thread(data.viu_evento, e["id"]):
            continue
        novos.append(e)
    novos = novos[:MAX_POSTS]
    saidas = []
    wfs: dict[str, str | None] = {}
    for e in novos:
        repo = e["repo"]["name"]
        if repo not in wfs:
            try:
                runs, _ = await asyncio.to_thread(
                    _get, f"/repos/{repo}/actions/runs", {"per_page": 1}
                )
                lista = runs.get("workflow_runs") if isinstance(runs, dict) else runs
                wfs[repo] = _linha_workflow(lista)
            except Exception:
                log.exception("github: falha ao buscar workflow de %s", repo)
                wfs[repo] = None
        await asyncio.to_thread(data.salvar_evento, e["id"])
        saidas.append((e, wfs[repo]))
    return saidas


def _texto_push(evento: dict, wf: str | None) -> str:
    repo = evento["repo"]["name"]
    commits = evento.get("payload", {}).get("commits", [])[:MAX_POSTS]
    linhas = [f"🦎 {repo}"]
    if not commits:
        # push grande: a api nem sempre lista os commits.
        linhas.append(f"{USER} fez um novo push")
        linhas.append(f"https://github.com/{repo}")
    elif len(commits) == 1:
        autor = commits[0].get("author", {}).get("name", USER)
        msg = commits[0]["message"].splitlines()[0][:120]
        sha = evento["payload"].get("head", "")[:7]
        url = f"https://github.com/{repo}/commit/{sha}" if sha else f"https://github.com/{repo}"
        linhas.append(f"{autor} fez um novo commit")
        linhas.append(f"[{msg}]({url})")
    else:
        linhas.append(f"{len(commits)} commits novos")
        for c in commits:
            autor = c.get("author", {}).get("name", USER)
            msg = c["message"].splitlines()[0][:120]
            linhas.append(f"• {msg} — {autor}")
    if wf:
        linhas.append(f"Workflow: {wf}")
    return "\n".join(linhas)


def _limpar_repo(texto: str) -> str | None:
    """aceita link ou dono/repo. retorna 'dono/repo' ou None se invalido."""
    t = (texto or "").strip()
    t = re.sub(r"^https?://github\.com/", "", t, flags=re.IGNORECASE)
    t = t.strip("/").removesuffix(".git")
    if re.fullmatch(r"[\w.-]+/[\w.-]+", t):
        return t
    return None


async def _repo_existe(repo: str) -> bool:
    """confere na api se o repo existe."""
    try:
        dados, _ = await asyncio.to_thread(_get, f"/repos/{repo}")
        return isinstance(dados, dict)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise
    except Exception:
        log.exception("github: falha ao conferir %s", repo)
        raise


class GitHub(commands.Cog, name="GitHub"):
    """liga repo ao chat + monitor de pushes."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not CHANNEL_ID:
            log.warning("GITHUB_CHANNEL_ID nao definido — sem fallback de destino")

    # ─── >github ───
    @commands.command(name="github")
    @commands.has_permissions(administrator=True)
    async def github(self, ctx: commands.Context, *, args: str = ""):
        """[admin] liga repo a este chat: >github <link|dono/repo>."""
        texto = (args or "").strip()
        if not texto:
            await ctx.send(
                "uso: `>github <link ou dono/repo>` pra avisar push aqui, "
                "`>github lista` pra ver, `>github remover <repo>` pra tirar."
            )
            return
        if texto.lower() == "lista":
            vinc = await asyncio.to_thread(data.listar_destinos)
            if not vinc:
                await ctx.send("nenhum repo vinculado. usa `>github <repo>` aqui.")
                return
            await ctx.send(
                "\n".join(f"**{r}** → <#{c}>" for r, c in vinc[:20])
            )
            return
        alvo = texto
        if texto.lower().startswith("remover "):
            alvo = texto[8:].strip()
            repo = _limpar_repo(alvo)
            if repo is None:
                await ctx.send("repo inválido! manda o link ou `dono/repo`.")
                return
            saiu = await asyncio.to_thread(data.desvincular_repo, repo, ctx.channel.id)
            await ctx.send(
                f"{repo} fora daqui." if saiu else f"{repo} nem tava vinculado aqui."
            )
            return
        repo = _limpar_repo(texto)
        if repo is None:
            await ctx.send("repo inválido! manda o link ou `dono/repo`.")
            return
        try:
            ok = await _repo_existe(repo)
        except Exception:
            await ctx.send("api do github fora do ar, tenta de novo em uns segundos.")
            return
        if not ok:
            await ctx.send("repo não encontrado no github. confere o nome.")
            return
        await asyncio.to_thread(data.vincular_repo, repo, ctx.channel.id)
        await ctx.send(f"{visual.AXOLOTL} pushes de **{repo}** caem aqui agora!")

    # ─── /github ───
    @app_commands.command(name="github", description="[admin] liga repo a este chat pra avisar push.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        acao="o que fazer",
        repo="link ou dono/repo (vincular e remover)",
    )
    @app_commands.choices(
        acao=[
            app_commands.Choice(name="vincular", value="vincular"),
            app_commands.Choice(name="lista", value="lista"),
            app_commands.Choice(name="remover", value="remover"),
        ]
    )
    async def github_slash(
        self, interaction: discord.Interaction, acao: str, repo: str | None = None
    ):
        """versão slash do >github."""
        if acao == "lista":
            vinc = await asyncio.to_thread(data.listar_destinos)
            if not vinc:
                await interaction.response.send_message(
                    "nenhum repo vinculado. usa `/github vincular` aqui.", ephemeral=True
                )
                return
            await interaction.response.send_message(
                "\n".join(f"**{r}** → <#{c}>" for r, c in vinc[:20]), ephemeral=True
            )
            return
        limpo = _limpar_repo(repo or "")
        if limpo is None:
            await interaction.response.send_message(
                "repo inválido! manda o link ou `dono/repo`.", ephemeral=True
            )
            return
        if acao == "remover":
            ch = interaction.channel.id if interaction.channel else 0
            saiu = await asyncio.to_thread(data.desvincular_repo, limpo, ch)
            await interaction.response.send_message(
                f"{limpo} fora daqui." if saiu else f"{limpo} nem tava vinculado aqui."
            )
            return
        try:
            ok = await _repo_existe(limpo)
        except Exception:
            await interaction.response.send_message(
                "api do github fora do ar, tenta de novo em uns segundos.",
                ephemeral=True,
            )
            return
        if not ok:
            await interaction.response.send_message(
                "repo não encontrado no github. confere o nome.", ephemeral=True
            )
            return
        ch = interaction.channel.id if interaction.channel else 0
        await asyncio.to_thread(data.vincular_repo, limpo, ch)
        await interaction.response.send_message(
            f"{visual.AXOLOTL} pushes de **{limpo}** caem aqui agora!"
        )

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.vigia.is_running():
            self.vigia.start()
            log.info(
                "github: vigia de pushes de %s a cada %dmin -> chat %d",
                USER,
                INTERVALO_MIN,
                CHANNEL_ID,
            )

    @tasks.loop(minutes=INTERVALO_MIN)
    async def vigia(self):
        for evento, wf in await _pushes_novos():
            repo = evento["repo"]["name"]
            canais = await asyncio.to_thread(data.destinos_repo, repo)
            if not canais and CHANNEL_ID:
                canais = [CHANNEL_ID]
            for chat_id in canais:
                canal = self.bot.get_channel(chat_id)
                if canal is None:
                    try:
                        canal = await self.bot.fetch_channel(chat_id)
                    except Exception:
                        log.exception("github: canal %d nao encontrado", chat_id)
                        continue
                try:
                    await canal.send(_texto_push(evento, wf))
                    log.info("github: postei push de %s no chat %d", repo, chat_id)
                except Exception:
                    log.exception("github: falha ao postar %s", repo)

    @vigia.before_loop
    async def before_vigia(self):
        await self.bot.wait_until_ready()

    def cog_unload(self):
        if self.vigia.is_running():
            self.vigia.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(GitHub(bot))
