import asyncio
import random

import discord
from discord import app_commands
from discord.ext import commands

import data
import painel
import visual
import data

OPCOES = ["pedra", "tesoura", "papel"]

# chave: o que o jogador fez.
VENCE = {
    "pedra":   "tesoura",
    "tesoura": "papel",
    "papel":   "pedra",
}

# falas do axolote, indexadas pelo mesmo resultado usado em
# data.registrar_ptp. Antes a lista de "derrota" era usada quando o
# jogador vencia e vice-versa, porque a chave saía do primeiro caractere
# da string.
FALAS = {
    "vitoria": [
        "essa eu não vi coming. boa.",
        "meu currículo não sobrevive a isso.",
        "vou precisar de mais treino. ou de terapia.",
        "ok. você é bom mesmo. irritante, mas bom.",
    ],
    "derrota": [
        "eu sabia. você não tinha chance.",
        "essa foi de manual.",
        "treinei dez mil rodadas pra esse momento.",
        f"{visual.AXOLOTL} o axolote dominou. sem discussão.",
    ],
    "empate": [
        "mesma energia. respeitei.",
        "empate. a gente se entende.",
        "clonou meu estilo, hein.",
        "dupla forte.",
    ],
}

CORES = {
    "vitoria": visual.SUCCESS,
    "derrota": visual.ERROR,
    "empate":  visual.WARNING,
}

TITULOS = {
    "vitoria": "VOCÊ GANHOU!",
    "derrota": "VOCÊ PERDEU!",
    "empate":  "EMPATE!",
}

MEDALHAS = ["1.", "2.", "3.", "4.", "5."]

# recompensa em diamantes por resultado do ptp.
PTP_DIAMANTES = {"vitoria": 20, "empate": 5, "derrota": 0}


def _jogada(usuario: int, escolha: str, jogada_bot: str) -> str:
    """traduz as duas escolhas no resultado do jogador."""
    if escolha == jogada_bot:
        return "empate"
    return "vitoria" if VENCE[escolha] == jogada_bot else "derrota"


class Jogos(commands.Cog, name="jogos"):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ─── lógica interna ───
    def _resolver(self, escolha: str | None, jogador) -> dict | None:
        """resolve a jogada e devolve os dados. None se a escolha for inválida."""
        if escolha is None or escolha.lower() not in OPCOES:
            return None

        escolha = escolha.lower()
        jogada_bot = random.choice(OPCOES)
        resultado = _jogada(jogador.id, escolha, jogada_bot)

        return {
            "titulo": TITULOS[resultado],
            "cor": CORES[resultado],
            "escolha": escolha,
            "jogada_bot": jogada_bot,
            "resultado": resultado,
            "jogador": jogador,
        }

    @staticmethod
    def _montar_painel(dados: dict, placar: tuple[int, int, int], recompensa: int = 0):
        v, d, e = placar
        linhas = [
            f"**{dados['jogador'].display_name}** jogou **{dados['escolha'].capitalize()}**",
            f"**alt** jogou **{dados['jogada_bot'].capitalize()}**",
            "",
            f"{visual.AXOLOTL} diz: {random.choice(FALAS[dados['resultado']])}",
        ]
        extra = f"  •  +{recompensa} {visual.DIAMANTE}" if recompensa else ""
        rodape = f"seu placar: {v}V {d}D {e}E{extra}  •  use >placar • {visual.FOOTER}"
        return painel.montar(
            dados["titulo"], linhas=linhas, rodape=rodape, accent=dados["cor"]
        )

    # ─── >ptp ───
    @commands.command(name="ptp")
    async def ptp_prefix(self, ctx: commands.Context, escolha: str | None = None):
        """joga Pedra, Tesoura e Papel contra o Axolotl."""
        dados = self._resolver(escolha, ctx.author)
        if dados is None:
            await ctx.send(
                f"{visual.AXOLOTL} escolha inválida seu baitola! "
                f"Use: `>ptp pedra`, `>ptp tesoura` ou `>ptp papel`"
            )
            return

        placar = await asyncio.to_thread(
            data.registrar_ptp, ctx.author.id, dados["resultado"]
        )
        recompensa = PTP_DIAMANTES.get(dados["resultado"], 0)
        if recompensa:
            await asyncio.to_thread(
                data.adicionar_diamantes, ctx.author.id, recompensa
            )
        await ctx.send(view=self._montar_painel(dados, placar, recompensa))

    # ─── /ptp (slash) ───
    @app_commands.command(name="ptp", description="jogue Pedra, Tesoura e Papel contra o ALT!")
    @app_commands.describe(escolha="sua jogada: pedra, tesoura ou papel")
    @app_commands.choices(escolha=[
        app_commands.Choice(name="pedra", value="pedra"),
        app_commands.Choice(name="tesoura", value="tesoura"),
        app_commands.Choice(name="papel", value="papel"),
    ])
    async def ptp_slash(self, interaction: discord.Interaction, escolha: str):
        dados = self._resolver(escolha, interaction.user)
        if dados is None:
            await interaction.response.send_message(
                f"{visual.AXOLOTL} escolha inválida seu baitola!",
                ephemeral=True,
            )
            return

        placar = await asyncio.to_thread(
            data.registrar_ptp, interaction.user.id, dados["resultado"]
        )
        recompensa = PTP_DIAMANTES.get(dados["resultado"], 0)
        if recompensa:
            await asyncio.to_thread(
                data.adicionar_diamantes, interaction.user.id, recompensa
            )
        await interaction.response.send_message(view=self._montar_painel(dados, placar, recompensa))

    # ─── >placar ───
    @commands.command(name="placar")
    async def ver_placar(self, ctx: commands.Context):
        """veja seu placar de Pedra, Tesoura e Papel."""
        v, d, e = await asyncio.to_thread(data.buscar_ptp, ctx.author.id)
        if v + d + e == 0:
            await ctx.send(
                f"{visual.AXOLOTL} {ctx.author.mention} você ainda não jogou nada! "
                f"Use `>ptp` para começar."
            )
            return

        total = v + d + e
        pct = round(v / total * 100)

        await ctx.send(
            view=painel.montar(
                f"Placar de {ctx.author.display_name}",
                campos=[
                    ("vitórias", str(v)),
                    ("derrotas", str(d)),
                    ("empates", str(e)),
                    ("taxa de vitória", f"{pct}%"),
                ],
            )
        )

    # ─── >rankingptp ───
    @commands.command(name="rankingptp")
    async def ranking(self, ctx: commands.Context):
        """veja o top 5 jogadores do ptp no servidor."""
        ranking = await asyncio.to_thread(data.top_ptp, 5)
        if not ranking:
            await ctx.send(
                f"{visual.AXOLOTL} ninguém jogou ainda! seja o primeiro com `>ptp`."
            )
            return

        linhas = []
        for i, (user_id, v, d, e) in enumerate(ranking):
            membro = ctx.guild.get_member(user_id)
            nome = membro.display_name if membro else f"usuário {user_id}"
            linhas.append(f"{MEDALHAS[i]} **{nome}** — {v}V {d}D {e}E")

        await ctx.send(view=painel.montar("Ranking — Top 5 Jogadores", linhas=linhas))

    # ─── /placar ───
    @app_commands.command(name="placar", description="veja seu placar de Pedra, Tesoura e Papel.")
    async def placar_slash(self, interaction: discord.Interaction):
        """versão slash do >placar."""
        v, d, e = await asyncio.to_thread(data.buscar_ptp, interaction.user.id)
        if v + d + e == 0:
            await interaction.response.send_message(
                f"{visual.AXOLOTL} você ainda não jogou nada! Use `/ptp` para começar.",
                ephemeral=True,
            )
            return

        total = v + d + e
        pct = round(v / total * 100)

        await interaction.response.send_message(
            view=painel.montar(
                f"Placar de {interaction.user.display_name}",
                campos=[
                    ("vitórias", str(v)),
                    ("derrotas", str(d)),
                    ("empates", str(e)),
                    ("taxa de vitória", f"{pct}%"),
                ],
            )
        )

    # ─── /rankingptp ───
    @app_commands.command(name="rankingptp", description="veja o top 5 jogadores do ptp no servidor.")
    async def ranking_slash(self, interaction: discord.Interaction):
        """versão slash do >rankingptp."""
        ranking = await asyncio.to_thread(data.top_ptp, 5)
        if not ranking:
            await interaction.response.send_message(
                f"{visual.AXOLOTL} ninguém jogou ainda! seja o primeiro com `/ptp`.",
                ephemeral=True,
            )
            return

        linhas = []
        for i, (user_id, v, d, e) in enumerate(ranking):
            membro = interaction.guild.get_member(user_id) if interaction.guild else None
            nome = membro.display_name if membro else f"usuário {user_id}"
            linhas.append(f"{MEDALHAS[i]} **{nome}** — {v}V {d}D {e}E")

        await interaction.response.send_message(
            view=painel.montar("Ranking — Top 5 Jogadores", linhas=linhas)
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Jogos(bot))
