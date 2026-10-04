# isso aq e a cara do bot: cor, emoji, rodape, categorias.
# nada disso se espalha pelo resto do codigo, tudo importa daqui.

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# ─── simbolo ───

# o emoji oficial e o custom `:02:`, vem do env como `<:02:id>`.
# nunca hardcoda `<:02:...>` no codigo, so via env.
AXOLOTL = os.getenv("AXOLOTL_EMOJI", "").strip()

# ─── economia ───

# `:amethyst:` e `:diamond:` tambem sao customs do servidor, via env.
AMETHYST = os.getenv("AMETHYST_EMOJI", "").strip()
DIAMANTE = os.getenv("DIAMANTE_EMOJI", "").strip()

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
