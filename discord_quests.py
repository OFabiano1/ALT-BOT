# isso aq lista as quests ativas do proprio discord.
# fonte: api.discordquest.com (dataset comunitario, sem token).
# a api oficial so lista por id e com contexto de usuario,
# nao serve pro bot. cache de 6h: quest muda devagar.

import datetime
import json
import threading
import time
import urllib.request

BASE = "https://api.discordquest.com/api/quests"
HEADERS = {"User-Agent": "ALT-bot"}

# cache em memoria: (expira_em, lista).
_cache: tuple[float, list] | None = None
_cache_lock = threading.Lock()

MAX_QUESTS = 6


def _num(alvo) -> int:
    try:
        return int(alvo or 0)
    except (TypeError, ValueError):
        return 0


def _tempo(alvo: int) -> str:
    if alvo <= 0:
        return ""
    if alvo < 120:
        return f"{alvo}s"
    return f"{round(alvo / 60)}min"


def _tarefa_legivel(tipo: str, alvo) -> str:
    n = _num(alvo)
    if tipo in ("ACHIEVEMENT_IN_ACTIVITY", "ACHIEVEMENT_IN_GAME"):
        return f"{n} conquistas" if n > 0 else "conquistas"
    tempo = _tempo(n)
    mapa = {
        "WATCH_VIDEO": "assiste",
        "WATCH_VIDEO_ON_MOBILE": "assiste no celular",
        "PLAY_ON_DESKTOP": "joga",
        "PLAY_ON_XBOX": "joga no xbox",
        "PLAY_ON_PLAYSTATION": "joga no playstation",
        "PLAY_ACTIVITY": "joga",
        "STREAM_ON_DESKTOP": "faz live de",
    }
    verbo = mapa.get(tipo, tipo.lower().replace("_", " "))
    return f"{verbo} {tempo}".strip()


def _quando(texto: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(texto)
    except (TypeError, ValueError):
        return None


def _ativa(q: dict, agora: float) -> bool:
    cfg = q.get("config", {}) or {}
    if cfg.get("config_version") != 2 or q.get("preview"):
        return False
    inicio = _quando(cfg.get("starts_at", ""))
    fim = _quando(cfg.get("expires_at", ""))
    if inicio is None or fim is None:
        return False
    return inicio.timestamp() <= agora < fim.timestamp()


def buscar_ativas() -> list[dict]:
    """top quests ativas: [{nome, jogo, tarefas, recompensa, expira, url}]."""
    global _cache
    agora = time.time()
    with _cache_lock:
        if _cache is not None and _cache[0] > agora:
            return _cache[1]
    req = urllib.request.Request(BASE, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        dados = json.load(resp)
    if not isinstance(dados, list):
        raise ValueError("resposta invalida")
    ativas = [q for q in dados if _ativa(q, agora)]
    ativas.sort(key=lambda q: q.get("config", {}).get("expires_at", ""))
    saida = []
    for q in ativas[:MAX_QUESTS]:
        cfg = q.get("config", {}) or {}
        msgs = cfg.get("messages", {}) or {}
        tarefas_cfg = (cfg.get("task_config_v2", {}) or {}).get("tasks", {}) or {}
        tarefas = []
        for tipo, t in tarefas_cfg.items():
            legivel = _tarefa_legivel(tipo, (t or {}).get("target"))
            if legivel and legivel not in tarefas:
                tarefas.append(legivel)
        orbs = []
        for r in ((cfg.get("rewards_config", {}) or {}).get("rewards", []) or []):
            if not isinstance(r, dict):
                continue
            nome = ((r.get("messages") or {}).get("name") or "").strip()
            if nome:
                rotulo = nome
            elif r.get("orb_quantity"):
                rotulo = f"{r['orb_quantity']} Orbs"
            else:
                continue
            if rotulo not in orbs:
                orbs.append(rotulo)
        expira_dt = _quando(cfg.get("expires_at", ""))
        expira = expira_dt.strftime("%d/%m") if expira_dt else ""
        saida.append(
            {
                "nome": msgs.get("quest_name", "") or msgs.get("game_title", ""),
                "jogo": msgs.get("game_title", ""),
                "tarefas": tarefas,
                "recompensa": ", ".join(orbs),
                "expira": expira,
                "url": f"https://discord.com/quests/{q.get('id', '')}",
            }
        )
    with _cache_lock:
        _cache = (agora + 6 * 3600, saida)
    return saida
