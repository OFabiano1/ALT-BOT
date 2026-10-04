# isso aq e a cara do bot: cor, emoji, rodape, categorias.
# nada disso se espalha pelo resto do codigo, tudo importa daqui.

import os

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

# ─── categorias da ajuda ───
CATEGORIAS = {
    "Geral":     "Geral",
    "jogos":     "Jogos",
    "Níveis":    "Níveis",
    "tickets":   "Tickets",
    "Status":    "Status",
    "Economia":  "Economia",
    "Mudae":     "Mudae",
    "Halloween": "Halloween",
}
