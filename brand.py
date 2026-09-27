"""Identidade visual do ALT.

Constantes de marca centralizadas para que todo embed, comando e
mensagem pertença ao mesmo sistema visual.

Referência: prompt.txt — AXOLOTL BR.
"""

# ── Símbolo ──────────────────────────────────────────────────
AXOLOTL = "\U0001FADF"  # 🫟

# ── Paleta ───────────────────────────────────────────────────
# Superfícies do dark mode. A profundidade vem de camadas e bordas
# controladas, não de fundo preto chapado.
BASE      = 0x0E1116
SURFACE_1 = 0x151A21
SURFACE_2 = 0x1C232C
BORDER    = 0x2A3440
TEXT      = 0xE8EDF2
TEXT_DIM  = 0x8A97A6

# Cores de destaque. O verde é elemento, não dominante — a assinatura
# continua sendo o rosa do axolote.
PRIMARY   = 0xF07FB0  # rosa axolote
SECONDARY = 0x52D6A8  # verde axolote

# Estados funcionais
INFO    = 0x6CB6FF
SUCCESS = 0x4ADE80
WARNING = 0xFBBF24
ERROR   = 0xFF7B7B

# ── Assinatura ───────────────────────────────────────────────
FOOTER = "Player to Player • Axolotl BR"

# ── Rótulos de categoria (comandos de ajuda) ─────────────────
CATEGORIAS = {
    "Geral":     "🤖 Geral",
    "jogos":     "🎮 Jogos",
    "Níveis":    "⭐ Níveis",
    "tickets":   "🎫 Tickets",
    "Status":    "📡 Status",
    "Status ":   "📡 Status",
}
