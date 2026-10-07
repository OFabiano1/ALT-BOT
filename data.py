# isso aq guarda tudo do bot: xp, placar, grana, colecao, mudae.
# sqlite em modo wal, cada operacao e uma transacao atomica.
# caminho absoluto pra nao depender de onde o app foi aberto.

import datetime
import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "alt.db"
LEGACY_XP = Path(__file__).parent / "data" / "xp.json"

# serializa acesso dentro do processo. BEGIN IMMEDIATE (abaixo) cuida da
# atomicidade da transação; este lock evita contenção entre tarefas do
# mesmo event loop.
# RLock porque quest_evento chama buscar_xp/ganhar_xp com o lock preso.
_lock = threading.RLock()

# coluna de placar para cada resultado. Mapeamento explícito em vez de
# derivar a chave do primeiro caractere da string.
COLUNA_PTP = {"vitoria": "v", "derrota": "d", "empate": "e"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS xp (
    user_id INTEGER PRIMARY KEY,
    xp      INTEGER NOT NULL DEFAULT 0,
    nivel   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS ptp (
    user_id INTEGER PRIMARY KEY,
    v       INTEGER NOT NULL DEFAULT 0,
    d       INTEGER NOT NULL DEFAULT 0,
    e       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS economia (
    user_id   INTEGER PRIMARY KEY,
    diamantes INTEGER NOT NULL DEFAULT 0,
    ametista  INTEGER NOT NULL DEFAULT 0,
    aura      TEXT,
    last_daily TEXT
);

CREATE TABLE IF NOT EXISTS colecao (
    user_id    INTEGER NOT NULL,
    axolotl_id TEXT NOT NULL,
    qtd        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, axolotl_id)
);

CREATE TABLE IF NOT EXISTS auras (
    user_id INTEGER NOT NULL,
    aura_id TEXT NOT NULL,
    PRIMARY KEY (user_id, aura_id)
);

CREATE TABLE IF NOT EXISTS mudae_reminder (
    user_id    INTEGER PRIMARY KEY,
    channel_id INTEGER NOT NULL,
    guild_id   INTEGER NOT NULL DEFAULT 0,
    expires_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS voz_fixa (
    guild_id   INTEGER PRIMARY KEY,
    channel_id INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS deadlock_links (
    discord_id INTEGER PRIMARY KEY,
    steam_id   INTEGER NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS quest_progress (
    user_id   INTEGER NOT NULL,
    periodo   TEXT NOT NULL,
    quest_id  TEXT NOT NULL,
    progresso INTEGER NOT NULL DEFAULT 0,
    concluida INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, periodo, quest_id)
);

CREATE TABLE IF NOT EXISTS voice_time (
    user_id INTEGER NOT NULL,
    dia     TEXT NOT NULL,
    minutos INTEGER NOT NULL DEFAULT 0,
    pago    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, dia)
);

CREATE TABLE IF NOT EXISTS github_seen (
    repo       TEXT PRIMARY KEY,
    sha        TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS github_seen_events (
    event_id   TEXT PRIMARY KEY,
    updated_at REAL NOT NULL
);
"""


@contextmanager
def _conectar():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        conn.row_factory = sqlite3.Row
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─── níveis ───
def xp_para_proximo(nivel: int) -> int:
    return nivel * 100


def buscar_xp(user_id: int) -> tuple[int, int]:
    """retorna (xp, nivel). Números neutros para usuário desconhecido."""
    with _lock, _conectar() as conn:
        row = conn.execute(
            "SELECT xp, nivel FROM xp WHERE user_id = ?", (user_id,)
        ).fetchone()
    return (row["xp"], row["nivel"]) if row else (0, 1)


def ganhar_xp(user_id: int, ganho: int) -> tuple[int, int, bool]:
    """soma XP e resolve a subida de nível.

    Leitura, cálculo e escrita na mesma transação — é isso que elimina a
    corrupção que o JSON sofria.

    Retorna (xp, nivel, subiu).
    """
    with _lock, _conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT xp, nivel FROM xp WHERE user_id = ?", (user_id,)
        ).fetchone()
        xp, nivel = (row["xp"], row["nivel"]) if row else (0, 1)

        xp = max(0, xp + ganho)
        subiu = False
        while xp >= xp_para_proximo(nivel):
            xp -= xp_para_proximo(nivel)
            nivel += 1
            subiu = True

        conn.execute(
            "INSERT INTO xp (user_id, xp, nivel) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET xp = excluded.xp, nivel = excluded.nivel",
            (user_id, xp, nivel),
        )
        return xp, nivel, subiu


def definir_xp(user_id: int, xp: int) -> tuple[int, int]:
    """define o XP total acumulado e deriva o nível dele.

    Retorna (xp, nivel).
    """
    with _lock, _conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")
        xp = max(0, xp)
        nivel = 1
        while xp >= xp_para_proximo(nivel):
            xp -= xp_para_proximo(nivel)
            nivel += 1

        conn.execute(
            "INSERT INTO xp (user_id, xp, nivel) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET xp = excluded.xp, nivel = excluded.nivel",
            (user_id, xp, nivel),
        )
        return xp, nivel


def top_xp(limite: int = 10) -> list[tuple[int, int, int]]:
    """top N por nível, desempate por XP. Retorna [(user_id, nivel, xp)]."""
    with _lock, _conectar() as conn:
        rows = conn.execute(
            "SELECT user_id, nivel, xp FROM xp "
            "ORDER BY nivel DESC, xp DESC LIMIT ?",
            (limite,),
        ).fetchall()
    return [(r["user_id"], r["nivel"], r["xp"]) for r in rows]


# ─── pedra, tesoura e papel ───
def buscar_ptp(user_id: int) -> tuple[int, int, int]:
    """retorna (vitorias, derrotas, empates)."""
    with _lock, _conectar() as conn:
        row = conn.execute(
            "SELECT v, d, e FROM ptp WHERE user_id = ?", (user_id,)
        ).fetchone()
    return (row["v"], row["d"], row["e"]) if row else (0, 0, 0)


def registrar_ptp(user_id: int, resultado: str) -> tuple[int, int, int]:
    """registra uma jogada e devolve o placar atualizado (v, d, e)."""
    # `coluna` só pode ser uma das três chaves de COLUNA_PTP — o dict é a
    # validação, o valor do usuário nunca entra no SQL.
    coluna = COLUNA_PTP[resultado]
    with _lock, _conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            f"INSERT INTO ptp (user_id, {coluna}) VALUES (?, 1) "
            f"ON CONFLICT(user_id) DO UPDATE SET {coluna} = {coluna} + 1",
            (user_id,),
        )
        row = conn.execute(
            "SELECT v, d, e FROM ptp WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["v"], row["d"], row["e"]


def top_ptp(limite: int = 5) -> list[tuple[int, int, int, int]]:
    """top N por vitórias. Retorna [(user_id, v, d, e)]."""
    with _lock, _conectar() as conn:
        rows = conn.execute(
            "SELECT user_id, v, d, e FROM ptp "
            "WHERE (v + d + e) > 0 ORDER BY v DESC, e DESC LIMIT ?",
            (limite,),
        ).fetchall()
    return [(r["user_id"], r["v"], r["d"], r["e"]) for r in rows]


# ─── economia (diamantes + ametista + aura) ───
def buscar_saldo(user_id: int) -> tuple[int, int, str | None]:
    """retorna (diamantes, ametista, aura_equipadada)."""
    with _lock, _conectar() as conn:
        row = conn.execute(
            "SELECT diamantes, ametista, aura FROM economia WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if row:
        return row["diamantes"], row["ametista"], row["aura"]
    return 0, 0, None


def adicionar_diamantes(user_id: int, qtd: int) -> int:
    """soma (ou subtrai se negativo) diamantes. Nunca deixa negativo. Retorna total."""
    with _lock, _conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT diamantes FROM economia WHERE user_id = ?", (user_id,)
        ).fetchone()
        total = (row["diamantes"] if row else 0) + qtd
        total = max(0, total)
        conn.execute(
            "INSERT INTO economia (user_id, diamantes) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET diamantes = ?",
            (user_id, total, total),
        )
        return total


def adicionar_ametista(user_id: int, qtd: int) -> int:
    """soma (ou subtrai se negativo) ametista. Nunca deixa negativo. Retorna total."""
    with _lock, _conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT ametista FROM economia WHERE user_id = ?", (user_id,)
        ).fetchone()
        total = (row["ametista"] if row else 0) + qtd
        total = max(0, total)
        conn.execute(
            "INSERT INTO economia (user_id, ametista) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET ametista = ?",
            (user_id, total, total),
        )
        return total


def transferir_diamantes(origem: int, destino: int, qtd: int) -> tuple[bool, int, int]:
    """transfere diamantes entre usuários. Retorna (ok, saldo_origem, saldo_destino)."""
    if qtd <= 0 or origem == destino:
        s_o, _, _ = buscar_saldo(origem)
        s_d, _, _ = buscar_saldo(destino)
        return False, s_o, s_d
    with _lock, _conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")
        r1 = conn.execute(
            "SELECT diamantes FROM economia WHERE user_id = ?", (origem,)
        ).fetchone()
        s_origem = r1["diamantes"] if r1 else 0
        if s_origem < qtd:
            return False, s_origem, (
                conn.execute(
                    "SELECT diamantes FROM economia WHERE user_id = ?", (destino,)
                ).fetchone() or {"diamantes": 0}
            )["diamantes"]
        r2 = conn.execute(
            "SELECT diamantes FROM economia WHERE user_id = ?", (destino,)
        ).fetchone()
        s_dest = r2["diamantes"] if r2 else 0
        conn.execute(
            "INSERT INTO economia (user_id, diamantes) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET diamantes = ?",
            (origem, s_origem - qtd, s_origem - qtd),
        )
        conn.execute(
            "INSERT INTO economia (user_id, diamantes) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET diamantes = ?",
            (destino, s_dest + qtd, s_dest + qtd),
        )
        return True, s_origem - qtd, s_dest + qtd


def tentar_daily(user_id: int, dima: int, amet: int, hoje: str) -> tuple[bool, int, int]:
    """tenta resgatar o daily. Retorna (ok, diamantes, ametista).

    `hoje` é YYYY-MM-DD em UTC. Se last_daily == hoje, nega.
    """
    with _lock, _conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT diamantes, ametista, last_daily FROM economia WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row and row["last_daily"] == hoje:
            return False, row["diamantes"], row["ametista"]
        d_total = (row["diamantes"] if row else 0) + dima
        a_total = (row["ametista"] if row else 0) + amet
        conn.execute(
            "INSERT INTO economia (user_id, diamantes, ametista, last_daily) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET "
            "diamantes = excluded.diamantes, ametista = excluded.ametista, "
            "last_daily = excluded.last_daily",
            (user_id, d_total, a_total, hoje),
        )
        return True, d_total, a_total


def top_diamantes(limite: int = 10) -> list[tuple[int, int]]:
    """top N por diamantes. Retorna [(user_id, diamantes)]."""
    with _lock, _conectar() as conn:
        rows = conn.execute(
            "SELECT user_id, diamantes FROM economia "
            "WHERE diamantes > 0 ORDER BY diamantes DESC LIMIT ?",
            (limite,),
        ).fetchall()
    return [(r["user_id"], r["diamantes"]) for r in rows]


# ─── auras ───
def tem_aura(user_id: int, aura_id: str) -> bool:
    with _lock, _conectar() as conn:
        row = conn.execute(
            "SELECT 1 FROM auras WHERE user_id = ? AND aura_id = ?",
            (user_id, aura_id),
        ).fetchone()
    return row is not None


def dar_aura(user_id: int, aura_id: str) -> None:
    with _lock, _conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT OR IGNORE INTO auras (user_id, aura_id) VALUES (?, ?)",
            (user_id, aura_id),
        )


def auras_usuario(user_id: int) -> list[str]:
    with _lock, _conectar() as conn:
        rows = conn.execute(
            "SELECT aura_id FROM auras WHERE user_id = ?", (user_id,)
        ).fetchall()
    return [r["aura_id"] for r in rows]


def equipar_aura(user_id: int, aura_id: str | None) -> None:
    with _lock, _conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO economia (user_id, aura) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET aura = excluded.aura",
            (user_id, aura_id),
        )


# ─── coleção de axolotls ───
def adicionar_axolotl(user_id: int, axolotl_id: str) -> int:
    """incrementa a coleção. Retorna a qtd atual daquele axolotl."""
    with _lock, _conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO colecao (user_id, axolotl_id, qtd) VALUES (?, ?, 1) "
            "ON CONFLICT(user_id, axolotl_id) DO UPDATE SET qtd = qtd + 1",
            (user_id, axolotl_id),
        )
        row = conn.execute(
            "SELECT qtd FROM colecao WHERE user_id = ? AND axolotl_id = ?",
            (user_id, axolotl_id),
        ).fetchone()
        return row["qtd"]


def buscar_colecao(user_id: int) -> list[tuple[str, int]]:
    """retorna [(axolotl_id, qtd)]."""
    with _lock, _conectar() as conn:
        rows = conn.execute(
            "SELECT axolotl_id, qtd FROM colecao WHERE user_id = ? ORDER BY qtd DESC",
            (user_id,),
        ).fetchall()
    return [(r["axolotl_id"], r["qtd"]) for r in rows]


# ─── mudae reminder ───
def salvar_mudae(user_id: int, channel_id: int, guild_id: int, expires_at: float) -> None:
    """agenda/substitui o reminder. Um ativo por usuário."""
    with _lock, _conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO mudae_reminder (user_id, channel_id, guild_id, expires_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET "
            "channel_id = excluded.channel_id, guild_id = excluded.guild_id, "
            "expires_at = excluded.expires_at",
            (user_id, channel_id, guild_id, expires_at),
        )


def remover_mudae(user_id: int) -> None:
    with _lock, _conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM mudae_reminder WHERE user_id = ?", (user_id,))


def listar_mudae() -> list[tuple[int, int, int, float]]:
    """retorna [(user_id, channel_id, guild_id, expires_at)]."""
    with _lock, _conectar() as conn:
        rows = conn.execute(
            "SELECT user_id, channel_id, guild_id, expires_at FROM mudae_reminder"
        ).fetchall()
    return [(r["user_id"], r["channel_id"], r["guild_id"], r["expires_at"]) for r in rows]


# ─── voz fixa ───
def fixar_voz(guild_id: int, channel_id: int) -> None:
    """marca a call pra ficar. sobrevivem restart e queda."""
    with _lock, _conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO voz_fixa (guild_id, channel_id) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id",
            (guild_id, channel_id),
        )


def soltar_voz(guild_id: int) -> None:
    """desmarca a call. so o >sair chama isso."""
    with _lock, _conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM voz_fixa WHERE guild_id = ?", (guild_id,))


def voz_fixa(guild_id: int) -> int | None:
    """devolve a call fixada ou None."""
    with _lock, _conectar() as conn:
        row = conn.execute(
            "SELECT channel_id FROM voz_fixa WHERE guild_id = ?", (guild_id,)
        ).fetchone()
    return row["channel_id"] if row else None


# ─── vínculo deadlock (discord -> steam) ───
def vincular_deadlock(discord_id: int, steam_id: int) -> None:
    """salva/troca o vínculo deadlock. um por usuário."""
    import time

    with _lock, _conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO deadlock_links (discord_id, steam_id, updated_at) "
            "VALUES (?, ?, ?) ON CONFLICT(discord_id) DO UPDATE SET "
            "steam_id = excluded.steam_id, updated_at = excluded.updated_at",
            (discord_id, steam_id, time.time()),
        )


def desvincular_deadlock(discord_id: int) -> bool:
    """remove o vínculo. retorna True se existia."""
    with _lock, _conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "DELETE FROM deadlock_links WHERE discord_id = ?", (discord_id,)
        )
        return cur.rowcount > 0


def buscar_deadlock(discord_id: int) -> int | None:
    """devolve o steam_id vinculado ou None."""
    with _lock, _conectar() as conn:
        row = conn.execute(
            "SELECT steam_id FROM deadlock_links WHERE discord_id = ?",
            (discord_id,),
        ).fetchone()
    return int(row["steam_id"]) if row else None


# ─── períodos (quests) ───

# utc-3 fixo, mesmo do halloween. dia e semana iso no horario da comunidade.
_TZ = datetime.timezone(datetime.timedelta(hours=-3))


def hoje_key() -> str:
    """YYYY-MM-DD de hoje. chave das quests diarias."""
    return datetime.datetime.now(_TZ).date().isoformat()


def semana_key() -> str:
    """YYYY-Www da semana iso. chave das quests semanais."""
    hoje = datetime.datetime.now(_TZ).date()
    ano, sem, _ = hoje.isocalendar()
    return f"{ano}-W{sem:02d}"


# ─── quests ───
def quest_evento(
    user_id: int, quest_id: str, periodo: str, ganho: int, meta: int, recompensa: int
) -> tuple[int, bool, int, int, bool]:
    """soma progresso e, se bater a meta, paga o xp na hora.

    Retorna (progresso, concluiu_agora, xp, nivel, subiu).
    Idempotente: depois de concluida, so acumula numero, nao paga de novo.
    """
    with _lock, _conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO quest_progress (user_id, periodo, quest_id, progresso) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(user_id, periodo, quest_id) DO NOTHING",
            (user_id, periodo, quest_id, 0),
        )
        row = conn.execute(
            "SELECT progresso, concluida FROM quest_progress "
            "WHERE user_id = ? AND periodo = ? AND quest_id = ?",
            (user_id, periodo, quest_id),
        ).fetchone()
        progresso = row["progresso"] + ganho
        concluiu_agora = False
        xp, nivel = buscar_xp(user_id)
        subiu = False
        if not row["concluida"] and progresso >= meta:
            conn.execute(
                "UPDATE quest_progress SET progresso = ?, concluida = 1 "
                "WHERE user_id = ? AND periodo = ? AND quest_id = ?",
                (progresso, user_id, periodo, quest_id),
            )
            concluiu_agora = True
        else:
            conn.execute(
                "UPDATE quest_progress SET progresso = ? "
                "WHERE user_id = ? AND periodo = ? AND quest_id = ?",
                (progresso, user_id, periodo, quest_id),
            )
    if concluiu_agora:
        xp, nivel, subiu = ganhar_xp(user_id, recompensa)
    return progresso, concluiu_agora, xp, nivel, subiu


def estado_quests(user_id: int, periodo: str) -> dict[str, tuple[int, bool]]:
    """{quest_id: (progresso, concluida)} no periodo."""
    with _lock, _conectar() as conn:
        rows = conn.execute(
            "SELECT quest_id, progresso, concluida FROM quest_progress "
            "WHERE user_id = ? AND periodo = ?",
            (user_id, periodo),
        ).fetchall()
    return {r["quest_id"]: (r["progresso"], bool(r["concluida"])) for r in rows}


# ─── tempo de call (xp por voz) ───
def somar_voz(user_id: int, dia: str, minutos: int) -> tuple[int, int]:
    """soma minutos de call no dia. retorna (minutos, pago)."""
    with _lock, _conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO voice_time (user_id, dia, minutos) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, dia) DO NOTHING",
            (user_id, dia, 0),
        )
        conn.execute(
            "UPDATE voice_time SET minutos = minutos + ? WHERE user_id = ? AND dia = ?",
            (minutos, user_id, dia),
        )
        row = conn.execute(
            "SELECT minutos, pago FROM voice_time WHERE user_id = ? AND dia = ?",
            (user_id, dia),
        ).fetchone()
        return row["minutos"], row["pago"]


def pagar_voz(user_id: int, dia: str, pago_min: int) -> None:
    """marca ate que minuto o xp de voz ja foi pago no dia."""
    with _lock, _conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE voice_time SET pago = ? WHERE user_id = ? AND dia = ?",
            (pago_min, user_id, dia),
        )


def buscar_voz(user_id: int, dia: str) -> tuple[int, int]:
    """retorna (minutos, pago) de call no dia."""
    with _lock, _conectar() as conn:
        row = conn.execute(
            "SELECT minutos, pago FROM voice_time WHERE user_id = ? AND dia = ?",
            (user_id, dia),
        ).fetchone()
    return (row["minutos"], row["pago"]) if row else (0, 0)


# ─── github monitorado ───
def buscar_github(repo: str) -> str | None:
    """ultimo sha postado do repo, ou None (primeira vez)."""
    with _lock, _conectar() as conn:
        row = conn.execute(
            "SELECT sha FROM github_seen WHERE repo = ?", (repo,)
        ).fetchone()
    return row["sha"] if row else None


def salvar_github(repo: str, sha: str) -> None:
    """marca o sha como ja postado."""
    import time

    with _lock, _conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO github_seen (repo, sha, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(repo) DO UPDATE SET sha = excluded.sha, "
            "updated_at = excluded.updated_at",
            (repo, sha, time.time()),
        )


def viu_evento(event_id: str) -> bool:
    """True se o evento do github ja foi postado."""
    with _lock, _conectar() as conn:
        row = conn.execute(
            "SELECT 1 FROM github_seen_events WHERE event_id = ?", (event_id,)
        ).fetchone()
    return row is not None


def salvar_evento(event_id: str) -> None:
    """marca o evento como ja postado."""
    import time

    with _lock, _conectar() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT OR IGNORE INTO github_seen_events (event_id, updated_at) "
            "VALUES (?, ?)",
            (event_id, time.time()),
        )


# ─── migração ───
def migrar_xp_legado() -> int:
    """importa data/xp.json uma única vez, se ele existir.

    Sem isso, todo o nível acumulado antes do SQLite seria perdido no
    primeiro deploy. Só roda se a tabela xp estiver vazia.
    """
    if not LEGACY_XP.exists():
        return 0

    with _lock, _conectar() as conn:
        tem_tabela = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'xp'"
        ).fetchone()
        if not tem_tabela:
            return 0

        total = conn.execute("SELECT COUNT(*) FROM xp").fetchone()[0]
        if total:
            return 0

        try:
            with open(LEGACY_XP, "r", encoding="utf-8") as f:
                dados = json.load(f)
        except (json.JSONDecodeError, OSError):
            return 0

        inseridos = 0
        for uid, dados_user in dados.items():
            try:
                user_id = int(uid)
                xp = int(dados_user["xp"])
                nivel = int(dados_user["nivel"])
            except (KeyError, TypeError, ValueError):
                continue
            conn.execute(
                "INSERT OR IGNORE INTO xp (user_id, xp, nivel) VALUES (?, ?, ?)",
                (user_id, max(0, xp), max(1, nivel)),
            )
            inseridos += 1

    return inseridos


def init() -> None:
    """cria o schema e migra dados legados. idempotente."""
    with _lock, _conectar() as conn:
        conn.executescript(SCHEMA)
        # wal e sync persistem no arquivo, configura uma vez so aqui
        # em vez de repetir em toda conexao (toda msg de xp).
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    migrar_xp_legado()
