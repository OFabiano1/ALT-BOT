import discord
from discord.ext import commands
from discord import app_commands
import random

AXOLOTE = "XD"
CORACOES = ["💗", "💖", "💝", "💕", "🩷"]

OPCOES      = ["pedra", "tesoura", "papel"]
EMOJIS_JOGO = {"pedra": "🪨", "tesoura": "✂️", "papel": "📄"}

VENCE = {
    "pedra":   "tesoura",
    "tesoura": "papel",
    "papel":   "pedra",
}

PIADAS_VITORIA = [
    "uhuuul eu gosto de dar o cu",
    "uhuuul eu gosto de dar o cu",
    "uhuuul eu gosto de dar o cu",
    "uhuuul eu gosto de dar o cu",
]

PIADAS_DERROTA = [
    "uhuuul eu gosto de dar o cu",
    "uhuuul eu gosto de dar o cu",
    "uhuuul eu gosto de dar o cu",
    "uhuuul eu gosto de dar o cu",
]

PIADAS_EMPATE = [
    "uhuuul eu gosto de dar o cu",
    "uhuuul eu gosto de dar o cu",
    "uhuuul eu gosto de dar o cu",
]


class Jogos(commands.Cog, name="jogos"):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # placar compartilhado: {user_id: {"v": int, "d": int, "e": int}}
        self.placar: dict[int, dict] = {}

    # ── Lógica interna ───────────────────────────────────────
    def _atualizar_placar(self, user_id: int, resultado: str):
        if user_id not in self.placar:
            self.placar[user_id] = {"v": 0, "d": 0, "e": 0}
        self.placar[user_id][resultado[0]] += 1  # "v", "d" ou "e"

    async def _jogar_ptp(self, ctx: commands.Context, escolha: str | None, jogador: discord.Member | discord.User):
        if escolha is None or escolha.lower() not in OPCOES:
            await ctx.send(
                f"{AXOLOTE} escolha inválida seu baitola! Use: `>ptp pedra`, `>ptp tesoura` ou `>ptp papel`"
            )
            return

        escolha    = escolha.lower()
        bot_jogada = random.choice(OPCOES)

        emoji_jogador = EMOJIS_JOGO[escolha]
        emoji_bot     = EMOJIS_JOGO[bot_jogada]

        if escolha == bot_jogada:
            resultado_texto = random.choice(PIADAS_EMPATE)
            cor    = 0xFFD700
            titulo = "⚖️ EMPATE!"
            self._atualizar_placar(jogador.id, "empate")
        elif VENCE[escolha] == bot_jogada:
            resultado_texto = random.choice(PIADAS_DERROTA)
            cor    = 0x00FF7F
            titulo = "🎉 W VOCÊ GANHOU!"
            self._atualizar_placar(jogador.id, "vitoria")
        else:
            resultado_texto = random.choice(PIADAS_VITORIA)
            cor    = 0xFF4500
            titulo = "💀 L VOCÊ PERDEU!"
            self._atualizar_placar(jogador.id, "derrota")

        p = self.placar[jogador.id]
        embed = discord.Embed(title=titulo, color=cor)
        embed.add_field(
            name=f"{jogador.display_name} jogou",
            value=f"{emoji_jogador} **{escolha.capitalize()}**",
            inline=True,
        )
        embed.add_field(
            name="alt jogou",
            value=f"{emoji_bot} **{bot_jogada.capitalize()}**",
            inline=True,
        )
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="💬 Axolote diz:", value=resultado_texto, inline=False)
        embed.set_footer(
            text=f"seu placar: {p['v']}V {p['d']}D {p['e']}E  •  use >placar para ver tudo"
        )
        await ctx.send(embed=embed)

    # ── >ptp ─────────────────────────────────────────────────
    @commands.command(name="ptp")
    async def ptp_prefix(self, ctx: commands.Context, escolha: str = None):
        """Joga Pedra, Tesoura e Papel contra o Axolote."""
        await self._jogar_ptp(ctx, escolha, ctx.author)

    # ── /ptp (slash) ─────────────────────────────────────────
    @app_commands.command(name="ptp", description="jogue Pedra, Tesoura e Papel contra o ALT!")
    @app_commands.describe(escolha="sua jogada: pedra, tesoura ou papel")
    @app_commands.choices(escolha=[
        app_commands.Choice(name="🪨 pedra",   value="pedra"),
        app_commands.Choice(name="✂️ tesoura", value="tesoura"),
        app_commands.Choice(name="📄 papel",   value="papel"),
    ])
    async def ptp_slash(self, interaction: discord.Interaction, escolha: str):
        ctx = await commands.Context.from_interaction(interaction)
        await self._jogar_ptp(ctx, escolha, interaction.user)

    # ── >placar ──────────────────────────────────────────────
    @commands.command(name="placar")
    async def ver_placar(self, ctx: commands.Context):
        """Veja seu placar de Pedra, Tesoura e Papel."""
        uid = ctx.author.id
        if uid not in self.placar or all(v == 0 for v in self.placar[uid].values()):
            await ctx.send(
                f"{AXOLOTE} {ctx.author.mention} você ainda não jogou nada! Use `>ptp` para começar."
            )
            return

        p     = self.placar[uid]
        total = p["v"] + p["d"] + p["e"]
        pct   = round(p["v"] / total * 100) if total else 0

        embed = discord.Embed(
            title=f"📊 placar de {ctx.author.display_name}",
            color=0xFF69B4,
        )
        embed.add_field(name="✅ vitórias", value=str(p["v"]), inline=True)
        embed.add_field(name="❌ derrotas", value=str(p["d"]), inline=True)
        embed.add_field(name="⚖️ empates",  value=str(p["e"]), inline=True)
        embed.add_field(name="🎯 taxa de vitória", value=f"{pct}%", inline=False)
        await ctx.send(embed=embed)

    # ── >ranking ─────────────────────────────────────────────
    @commands.command(name="ranking")
    async def ranking(self, ctx: commands.Context):
        """Veja o top 5 jogadores do servidor."""
        if not self.placar:
            await ctx.send(f"{AXOLOTE} ninguém jogou ainda! seja o primeiro com `>ptp`.")
            return

        ordenado = sorted(self.placar.items(), key=lambda x: x[1]["v"], reverse=True)[:5]
        embed    = discord.Embed(title="🏆 Ranking — Top 5 Jogadores", color=0xFFD700)
        medalhas = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        linhas   = []

        for i, (uid, p) in enumerate(ordenado):
            membro = ctx.guild.get_member(uid)
            nome   = membro.display_name if membro else f"usuário {uid}"
            linhas.append(f"{medalhas[i]} **{nome}** — {p['v']}V {p['d']}D {p['e']}E")

        embed.description = "\n".join(linhas)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Jogos(bot))