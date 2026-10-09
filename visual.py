# isso aq e a cara do bot: cor, emoji, rodape, categorias.
# nada disso se espalha pelo resto do codigo, tudo importa daqui.

import os
import random

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# ─── simbolo ───

# os customs do servidor, os unicos que o bot usa. o env so
# sobrescreve se um dia o id mudar, o padrao ja e o certo.
_AXOLOTL = "<:02:1028808570466213918>"
AXOLOTL = (os.getenv("AXOLOTL_EMOJI") or _AXOLOTL).strip()

# ─── economia ───

_AMETHYST = "<:amethyst:1554127047666831360>"
_DIAMANTE = "<:diamond:1554260297789866134>"
AMETHYST = (os.getenv("AMETHYST_EMOJI") or _AMETHYST).strip()
DIAMANTE = (os.getenv("DIAMANTE_EMOJI") or _DIAMANTE).strip()

# ─── deadlock ───

# custom do deadlock (o jogo da valve), mesmo esquema dos outros.
_DEADLOCK = "<:DEADLOCK:1556293610939482167>"
DEADLOCK = (os.getenv("DEADLOCK_EMOJI") or _DEADLOCK).strip()


def _mapa_emojis(texto: str | None) -> dict[str, str]:
    # "holliday=<:dl_holliday:123>,wraith=<:dl_wraith:456>" -> {"holliday": "<...>"}
    # vazio ou par invalido so ignora, quem chama usa texto puro.
    mapa: dict[str, str] = {}
    for par in (texto or "").split(","):
        nome, sep, emoji = par.partition("=")
        if not sep:
            continue
        nome = nome.strip().lower()
        emoji = emoji.strip()
        if nome and emoji:
            mapa[nome] = emoji
    return mapa


# rank por tier (ex: initiate) e heroi por nome (ex: holliday).
# padrao vazio = texto puro, env so preenche quando o custom existir.
DEADLOCK_RANK_EMOJIS = _mapa_emojis(os.getenv("DEADLOCK_RANK_EMOJIS"))
DEADLOCK_HERO_EMOJIS = _mapa_emojis(os.getenv("DEADLOCK_HERO_EMOJIS"))


def deadlock_rank_emoji(tier_nome: str) -> str:
    """devolve 'emoji ' ou '' pra cair no texto puro."""
    emoji = DEADLOCK_RANK_EMOJIS.get((tier_nome or "").strip().lower(), "")
    return f"{emoji} " if emoji else ""


def deadlock_hero_emoji(heroi_nome: str) -> str:
    """devolve 'emoji ' ou '' pra cair no texto puro."""
    emoji = DEADLOCK_HERO_EMOJIS.get((heroi_nome or "").strip().lower(), "")
    return f"{emoji} " if emoji else ""

# ─── paleta ───

# superficies do dark mode. profundidade vem de camada e borda,
# nao de fundo preto chapado.
BASE      = 0x0E1116
SURFACE_1 = 0x151A21
SURFACE_2 = 0x1C232C
BORDER    = 0x2A3440
TEXT      = 0xE8EDF2
TEXT_DIM  = 0x8A97A6

# destaque e violeta, o verde e so elemento, nao dominante.
PRIMARY   = 0x8F00FF  # violeta axolotl
SECONDARY = 0x52D6A8  # verde axolote

# estados funcionais
INFO    = 0x6CB6FF
SUCCESS = 0x4ADE80
WARNING = 0xFBBF24
ERROR   = 0xFF7B7B

# ─── assinatura ───
FOOTER = "Player to Player • Axolotl BR"

# ─── emotes de texto ───

# a lista oficial, so ASCII (nada de unicode): todo charme do bot
# sai daqui via emote(). nada de emoticon solto no resto do codigo.
EMOTES = (":)", ":D", ";)", ";D", ":P", ":o", "xD", "XD", "o/")


def emote() -> str:
    """um emote aleatorio da lista."""
    return random.choice(EMOTES)

# ─── categorias da ajuda ───
CATEGORIAS = {
    "Geral":     "Geral",
    "Voz":       "Voz",
    "jogos":     "Jogos",
    "Níveis":    "Níveis",
    "tickets":   "Tickets",
    "Status":    "Status",
    "Economia":  "Economia",
    "Mudae":     "Mudae",
    "Halloween": "Halloween",
    "Deadlock":  "Deadlock",
    "Servidor":  "Servidor",
}
