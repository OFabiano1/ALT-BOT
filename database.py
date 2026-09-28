"""Persistência do ALT.

SQLite em modo WAL. Substitui o JSON que era reescrito inteiro a cada
mensagem — o que gerava escrita concorrente sem lock e custo O(n) por
mensagem. Aqui cada operação é uma transação atômica e indexada.

O caminho é absoluto para que o app não dependa do diretório atual.
"""

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "alt.db"
LEGACY_XP = Path(__file__).parent / "data" / "xp.json"

# Serializa acesso dentro do processo. BEGIN IMMEDIATE (abaixo) cuida da
# atomicidade da transação; este lock evita contenção entre tarefas do
# mesmo event loop.
_lock = threading.Lock()

# Coluna de placar para cada resultado. Mapeamento explícito em vez de
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
"""


@contextmanager
def _conectar():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Níveis ───────────────────────────────────────────────────
def xp_para_proximo(nivel: int) -> int:
    return nivel * 100


def buscar_xp(user_id: int) -> tuple[int, int]:
    """Retorna (xp, nivel). Números neutros para usuário desconhecido."""
    with _lock, _conectar() as conn:
        row = conn.execute(
            "SELECT xp, nivel FROM xp WHERE user_id = ?", (user_id,)
        ).fetchone()
    return (row["xp"], row["nivel"]) if row else (0, 1)


def ganhar_xp(user_id: int, ganho: int) -> tuple[int, int, bool]:
    """Soma XP e resolve a subida de nível.

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
    """Define o XP total acumulado e deriva o nível dele.

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
    """Top N por nível, desempate por XP. Retorna [(user_id, nivel, xp)]."""
    with _lock, _conectar() as conn:
        rows = conn.execute(
            "SELECT user_id, nivel, xp FROM xp "
            "ORDER BY nivel DESC, xp DESC LIMIT ?",
            (limite,),
        ).fetchall()
    return [(r["user_id"], r["nivel"], r["xp"]) for r in rows]


# ── Pedra, Tesoura e Papel ───────────────────────────────────
def buscar_ptp(user_id: int) -> tuple[int, int, int]:
    """Retorna (vitorias, derrotas, empates)."""
    with _lock, _conectar() as conn:
        row = conn.execute(
            "SELECT v, d, e FROM ptp WHERE user_id = ?", (user_id,)
        ).fetchone()
    return (row["v"], row["d"], row["e"]) if row else (0, 0, 0)


def registrar_ptp(user_id: int, resultado: str) -> tuple[int, int, int]:
    """Registra uma jogada e devolve o placar atualizado (v, d, e)."""
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
    """Top N por vitórias. Retorna [(user_id, v, d, e)]."""
    with _lock, _conectar() as conn:
        rows = conn.execute(
            "SELECT user_id, v, d, e FROM ptp "
            "WHERE (v + d + e) > 0 ORDER BY v DESC, e DESC LIMIT ?",
            (limite,),
        ).fetchall()
    return [(r["user_id"], r["v"], r["d"], r["e"]) for r in rows]


# ── Economia (diamantes + ametista + aura) ────────────────────
def buscar_saldo(user_id: int) -> tuple[int, int, str | None]:
    """Retorna (diamantes, ametista, aura_equipadada)."""
    with _lock, _conectar() as conn:
        row = conn.execute(
            "SELECT diamantes, ametista, aura FROM economia WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if row:
        return row["diamantes"], row["ametista"], row["aura"]
    return 0, 0, None


def adicionar_diamantes(user_id: int, qtd: int) -> int:
    """Soma (ou subtrai se negativo) diamantes. Nunca deixa negativo. Retorna total."""
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
    """Soma (ou subtrai se negativo) ametista. Nunca deixa negativo. Retorna total."""
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
    """Transfere diamantes entre usuários. Retorna (ok, saldo_origem, saldo_destino)."""
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
    """Tenta resgatar o daily. Retorna (ok, diamantes, ametista).

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
    """Top N por diamantes. Retorna [(user_id, diamantes)]."""
    with _lock, _conectar() as conn:
        rows = conn.execute(
            "SELECT user_id, diamantes FROM economia "
            "WHERE diamantes > 0 ORDER BY diamantes DESC LIMIT ?",
            (limite,),
        ).fetchall()
    return [(r["user_id"], r["diamantes"]) for r in rows]


# ── Auras ────────────────────────────────────────────────────
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


# ── Coleção de axolotls ──────────────────────────────────────
def adicionar_axolotl(user_id: int, axolotl_id: str) -> int:
    """Incrementa a coleção. Retorna a qtd atual daquele axolotl."""
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
    """Retorna [(axolotl_id, qtd)]."""
    with _lock, _conectar() as conn:
        rows = conn.execute(
            "SELECT axolotl_id, qtd FROM colecao WHERE user_id = ? ORDER BY qtd DESC",
            (user_id,),
        ).fetchall()
    return [(r["axolotl_id"], r["qtd"]) for r in rows]


# ── Migração ─────────────────────────────────────────────────
def migrar_xp_legado() -> int:
    """Importa data/xp.json uma única vez, se ele existir.

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
    """Cria o schema e migra dados legados. Idempotente."""
    with _lock, _conectar() as conn:
        conn.executescript(SCHEMA)
    migrar_xp_legado()
