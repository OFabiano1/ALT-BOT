# isso aq avisa push no chat: todo commit publico do dono em
# qualquer repo aparece la com autor, msg e status do workflow.
# poll de 5min no events do usuario (1 chamada cobre tudo) com
# etag. sem comando: nao aparece na ajuda, so trabalha.

import asyncio
import json
import logging
import os
import urllib.parse
import urllib.request

import discord
from discord.ext import commands, tasks

import data

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

# etag por url: 304 nao conta no rate limit.
_etags: dict[str, str] = {}


def _get(caminho: str, query: dict | None = None):
    """get com etag. retorna (dados|None se 304, etag|None)."""
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
            return json.load(resp), etag
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return None, _etags.get(url)
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


class GitHub(commands.Cog, name="GitHub"):
    """monitor de pushes: sem comando, so o loop."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not CHANNEL_ID:
            log.warning("GITHUB_CHANNEL_ID nao definido — monitor inativo")

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
        if not CHANNEL_ID:
            return
        canal = self.bot.get_channel(CHANNEL_ID)
        if canal is None:
            try:
                canal = await self.bot.fetch_channel(CHANNEL_ID)
            except Exception:
                log.exception("github: canal %d nao encontrado", CHANNEL_ID)
                return
        for evento, wf in await _pushes_novos():
            try:
                await canal.send(_texto_push(evento, wf))
                log.info("github: postei push em %s", evento["repo"]["name"])
            except Exception:
                log.exception("github: falha ao postar %s", evento["repo"]["name"])

    @vigia.before_loop
    async def before_vigia(self):
        await self.bot.wait_until_ready()

    def cog_unload(self):
        if self.vigia.is_running():
            self.vigia.cancel()


async def setup(bot: commands.Bot):
    await bot.add_cog(GitHub(bot))
