# isso aq fala com a deadlock-api (https://github.com/deadlock-api).
# so stdlib: urllib roda via asyncio.to_thread no cog, sem dep nova.
# endpoints gratis: rank, hero-stats, match-history, steam, assets.
# card e account-stats sao patreon-only, por isso o geral agrega hero-stats.

import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# ─── config ───

BASE = (os.getenv("DEADLOCK_API_BASE") or "https://api.deadlock-api.com").rstrip("/")
TIMEOUT = float(os.getenv("DEADLOCK_TIMEOUT_S") or "10")
STEAM64_BASE = 76561197960265728

_HEADERS = {"User-Agent": "ALT-bot/1.0 (+discord)"}

# ─── erro ───


class DeadlockAPIError(Exception):
    """falha falando com a api (http, timeout, json)."""


# ─── cache simples ───

# chave -> (expira_em, valor). lock pq o acesso vem de threads.
_cache: dict[str, tuple[float, object]] = {}
_cache_lock = threading.Lock()


def _cache_get(chave: str) -> object | None:
    agora = time.time()
    with _cache_lock:
        hit = _cache.get(chave)
        if hit is None:
            return None
        expira, valor = hit
        if expira < agora:
            del _cache[chave]
            return None
        return valor


def _cache_set(chave: str, valor: object, ttl: float) -> None:
    with _cache_lock:
        _cache[chave] = (time.time() + ttl, valor)


# ─── http ───


def _get_json(caminho: str, query: dict | None = None) -> object:
    """get sincrono, levanta DeadlockAPIError com motivo curto."""
    qs = f"?{urllib.parse.urlencode(query)}" if query else ""
    url = f"{BASE}{caminho}{qs}"
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise DeadlockAPIError(f"http {e.code}") from e
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise DeadlockAPIError(f"{type(e).__name__}") from e


# ─── steam id ───

# STEAM_0:Y:Z -> account_id = Z * 2 + Y
_STEAM_OLD = re.compile(r"^STEAM_[01]:([01]):(\d+)$", re.IGNORECASE)
_DIGITOS_URL = re.compile(r"steamcommunity\.com/profiles/(\d{17})")


def steam64_para_account(steam64: int) -> int | None:
    """steam64 -> account_id (steamid3). None se fora da faixa."""
    conta = steam64 - STEAM64_BASE
    if 0 < conta < 2**32:
        return conta
    return None


def account_para_steam64(account_id: int) -> int:
    """account_id -> steam64."""
    return STEAM64_BASE + account_id


def extrair_account_id(texto: str) -> int | None:
    """tenta tirar o account_id do texto sem rede. None se nao der."""
    t = texto.strip()
    # url de perfil direto
    m = _DIGITOS_URL.search(t)
    if m:
        return steam64_para_account(int(m.group(1)))
    # formato antigo STEAM_0:Y:Z
    m = _STEAM_OLD.match(t)
    if m:
        return int(m.group(2)) * 2 + int(m.group(1))
    # so digitos: pode ser account_id ou steam64
    if re.fullmatch(r"\d+", t):
        num = int(t)
        if num >= STEAM64_BASE:
            return steam64_para_account(num)
        if 0 < num < 2**32:
            return num
    return None


def resolver_steam(texto: str) -> tuple[int, str | None]:
    """texto livre -> (account_id, personaname|None).

    aceita id, steam64, url ou nome (busca no steam-search e pega o 1o).
    levanta DeadlockAPIError se nao achar ninguem.
    """
    direto = extrair_account_id(texto)
    if direto is not None:
        return direto, None
    # nome/vanity: pesquisa e pega o primeiro com historico
    dados = _get_json(
        "/v1/players/steam-search",
        {"search_query": texto.strip(), "limit": 5},
    )
    if isinstance(dados, list) and dados:
        primeiro = dados[0]
        return int(primeiro["account_id"]), primeiro.get("personaname")
    raise DeadlockAPIError("perfil nao encontrado")


# ─── endpoints ───


def buscar_rank(account_id: int) -> dict:
    """rank atual (badge, rank=tier, subrank). cache 10min."""
    chave = f"rank:{account_id}"
    hit = _cache_get(chave)
    if isinstance(hit, dict):
        return hit
    dados = _get_json(f"/v1/players/{account_id}/rank")
    if not isinstance(dados, dict):
        raise DeadlockAPIError("resposta invalida")
    _cache_set(chave, dados, 600)
    return dados


def buscar_hero_stats(account_id: int) -> list:
    """stats por heroi (matches_played, wins, kills, deaths, assists). cache 10min."""
    chave = f"hero:{account_id}"
    hit = _cache_get(chave)
    if isinstance(hit, list):
        return hit
    dados = _get_json("/v1/players/hero-stats", {"account_ids": account_id})
    if not isinstance(dados, list):
        raise DeadlockAPIError("resposta invalida")
    _cache_set(chave, dados, 600)
    return dados


def buscar_match_history(account_id: int) -> list:
    """historico cru (sem cache, o 7d precisa de frescor)."""
    dados = _get_json(f"/v1/players/{account_id}/match-history")
    if not isinstance(dados, list):
        raise DeadlockAPIError("resposta invalida")
    return dados


def buscar_steam_profile(account_id: int) -> dict:
    """personaname + profileurl + avatar. cache 1h."""
    chave = f"steam:{account_id}"
    hit = _cache_get(chave)
    if isinstance(hit, dict):
        return hit
    dados = _get_json("/v1/players/steam", {"account_ids": account_id})
    perfil: dict = {}
    if isinstance(dados, list) and dados:
        perfil = dados[0]
    _cache_set(chave, perfil, 3600)
    return perfil


def buscar_heroes() -> dict[int, str]:
    """id -> nome do heroi. cache 24h."""
    chave = "assets:heroes"
    hit = _cache_get(chave)
    if isinstance(hit, dict):
        return hit  # type: ignore[return-value]
    dados = _get_json("/v1/assets/heroes")
    mapa: dict[int, str] = {}
    if isinstance(dados, list):
        for h in dados:
            try:
                mapa[int(h["id"])] = str(h["name"])
            except (KeyError, TypeError, ValueError):
                continue
    _cache_set(chave, mapa, 86400)
    return mapa


def buscar_ranks() -> dict[int, str]:
    """tier -> nome do rank. cache 24h."""
    chave = "assets:ranks"
    hit = _cache_get(chave)
    if isinstance(hit, dict):
        return hit  # type: ignore[return-value]
    dados = _get_json("/v1/assets/ranks")
    mapa: dict[int, str] = {}
    if isinstance(dados, list):
        for r in dados:
            try:
                mapa[int(r["tier"])] = str(r["name"])
            except (KeyError, TypeError, ValueError):
                continue
    _cache_set(chave, mapa, 86400)
    return mapa


def buscar_rank_assets() -> dict[int, dict]:
    """tier -> {nome, imagem}. imagem oficial pra embutir no card. cache 24h."""
    chave = "assets:ranks:full"
    hit = _cache_get(chave)
    if isinstance(hit, dict):
        return hit  # type: ignore[return-value]
    dados = _get_json("/v1/assets/ranks")
    mapa: dict[int, dict] = {}
    if isinstance(dados, list):
        for r in dados:
            try:
                tier = int(r["tier"])
                imgs = r.get("images", {}) or {}
                mapa[tier] = {
                    "nome": str(r["name"]),
                    "imagem": imgs.get("large") or imgs.get("small"),
                }
            except (KeyError, TypeError, ValueError):
                continue
    _cache_set(chave, mapa, 86400)
    return mapa


def buscar_hero_assets() -> dict[int, dict]:
    """id -> {nome, retrato}. retrato oficial pro card. cache 24h."""
    chave = "assets:heroes:full"
    hit = _cache_get(chave)
    if isinstance(hit, dict):
        return hit  # type: ignore[return-value]
    dados = _get_json("/v1/assets/heroes")
    mapa: dict[int, dict] = {}
    if isinstance(dados, list):
        for h in dados:
            try:
                hid = int(h["id"])
                imgs = h.get("images", {}) or {}
                mapa[hid] = {
                    "nome": str(h["name"]),
                    "retrato": imgs.get("icon_image_small")
                    or imgs.get("icon_hero_card"),
                }
            except (KeyError, TypeError, ValueError):
                continue
    _cache_set(chave, mapa, 86400)
    return mapa


def buscar_fontes() -> dict[str, str]:
    """arquivo da fonte -> url no cdn. cache 24h."""
    chave = "assets:fonts"
    hit = _cache_get(chave)
    if isinstance(hit, dict):
        return hit  # type: ignore[return-value]
    dados = _get_json("/v1/assets/fonts")
    mapa = dict(dados) if isinstance(dados, dict) else {}
    _cache_set(chave, mapa, 86400)
    return mapa


# ─── agregação ───


def _kda(k: int, d: int, a: int) -> float:
    return (k + a) / max(1, d)


def resumo_geral(hero_stats: list) -> dict:
    """agrega hero-stats: partidas, vitorias, kda, top 5 herois."""
    partidas = sum(int(h.get("matches_played", 0) or 0) for h in hero_stats)
    vitorias = sum(int(h.get("wins", 0) or 0) for h in hero_stats)
    k = sum(int(h.get("kills", 0) or 0) for h in hero_stats)
    d = sum(int(h.get("deaths", 0) or 0) for h in hero_stats)
    a = sum(int(h.get("assists", 0) or 0) for h in hero_stats)
    top = sorted(hero_stats, key=lambda h: int(h.get("matches_played", 0) or 0), reverse=True)[:5]
    return {
        "partidas": partidas,
        "vitorias": vitorias,
        "derrotas": max(0, partidas - vitorias),
        "winrate": (vitorias / partidas * 100) if partidas else 0.0,
        "k": k,
        "d": d,
        "a": a,
        "kda": _kda(k, d, a),
        "top": [
            (
                int(h.get("hero_id", 0) or 0),
                int(h.get("matches_played", 0) or 0),
                int(h.get("wins", 0) or 0),
            )
            for h in top
            if int(h.get("matches_played", 0) or 0) > 0
        ],
    }


def resumo_7d(match_history: list, dias: int = 7) -> dict:
    """filtra por start_time e agrega. vitoria = player_match_outcome == 1."""
    corte = time.time() - dias * 86400
    jogos = [m for m in match_history if float(m.get("start_time", 0) or 0) >= corte]
    partidas = len(jogos)
    vitorias = sum(1 for m in jogos if int(m.get("player_match_outcome", 0) or 0) == 1)
    k = sum(int(m.get("player_kills", 0) or 0) for m in jogos)
    d = sum(int(m.get("player_deaths", 0) or 0) for m in jogos)
    a = sum(int(m.get("player_assists", 0) or 0) for m in jogos)
    por_heroi: dict[int, int] = {}
    for m in jogos:
        hid = int(m.get("hero_id", 0) or 0)
        por_heroi[hid] = por_heroi.get(hid, 0) + 1
    top_heroi = max(por_heroi.items(), key=lambda kv: kv[1]) if por_heroi else (0, 0)
    return {
        "partidas": partidas,
        "vitorias": vitorias,
        "derrotas": max(0, partidas - vitorias),
        "k": k,
        "d": d,
        "a": a,
        "kda": _kda(k, d, a),
        "heroi_top": top_heroi[0],
        "heroi_top_qtd": top_heroi[1],
    }
