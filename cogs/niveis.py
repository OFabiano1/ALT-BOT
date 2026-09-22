import discord
from discord.ext import commands
import json
import os
import random

AXOLOTE = "XD"
XP_FILE = "data/xp.json"

# XP ganho por mensagem (mín, máx)
XP_MIN = 10
XP_MAX = 25

# XP necessário para subir de nível (nivel * 100)
def xp_para_proximo(nivel: int) -> int:
    return nivel * 100


def carregar_xp() -> dict:
    if not os.path.exists(XP_FILE):
        os.makedirs("data", exist_ok=True)
        return {}
    with open(XP_FILE, "r") as f:
        return json.load(f)


def salvar_xp(data: dict):
    os.makedirs("data", exist_ok=True)
    with open(XP_FILE, "w") as f:
        json.dump(data, f, indent=2)


class Niveis(commands.Cog, name="Níveis"):
    """Sistema de XP e níveis."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cooldown: set[int] = set()  # evita spam de XP

    def _get_usuario(self, data: dict, user_id: str) -> dict:
        if user_id not in data:
            data[user_id] = {"xp": 0, "nivel": 1}
        return data[user_id]

    # ── Ganho de XP por mensagem ─────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.author.id in self.cooldown:
            return

        # cooldown de 60s por usuário
        self.cooldown.add(message.author.id)
        self.bot.loop.call_later(60, self.cooldown.discard, message.author.id)

        data = carregar_xp()
        uid  = str(message.author.id)
        user = self._get_usuario(data, uid)

        ganho       = random.randint(XP_MIN, XP_MAX)
        user["xp"] += ganho
        subiu       = False

        while user["xp"] >= xp_para_proximo(user["nivel"]):
            user["xp"]    -= xp_para_proximo(user["nivel"])
            user["nivel"] += 1
            subiu          = True

        salvar_xp(data)

        if subiu:
            embed = discord.Embed(
                title="🎉 Subiu de nível!",
                description=f"{message.author.mention} agora é **nível {user['nivel']}**! {AXOLOTE}",
                color=0xFF69B4,
            )
            await message.channel.send(embed=embed)

    # ── >rank ────────────────────────────────────────────────
    @commands.command(name="rank")
    async def rank(self, ctx: commands.Context, membro: discord.Member = None):
        """Veja seu nível e XP atual."""
        membro = membro or ctx.author
        data   = carregar_xp()
        uid    = str(membro.id)
        user   = self._get_usuario(data, uid)
        salvar_xp(data)

        nivel    = user["nivel"]
        xp_atual = user["xp"]
        xp_prox  = xp_para_proximo(nivel)
        barra    = int((xp_atual / xp_prox) * 10)
        progresso = "█" * barra + "░" * (10 - barra)

        embed = discord.Embed(
            title=f"📊 Rank de {membro.display_name}",
            color=0xFF69B4,
        )
        embed.add_field(name="🏅 Nível",   value=str(nivel),   inline=True)
        embed.add_field(name="✨ XP",       value=f"{xp_atual}/{xp_prox}", inline=True)
        embed.add_field(name="📈 Progresso", value=f"`{progresso}`", inline=False)
        embed.set_thumbnail(url=membro.display_avatar.url)
        await ctx.send(embed=embed)

    # ── >top ─────────────────────────────────────────────────
    @commands.command(name="top")
    async def top(self, ctx: commands.Context):
        """Ranking dos top 10 membros do servidor."""
        data = carregar_xp()
        if not data:
            await ctx.send(f"{AXOLOTE} ninguém tem XP ainda! Comecem a conversar!")
            return

        ordenado = sorted(
            data.items(),
            key=lambda x: (x[1]["nivel"], x[1]["xp"]),
            reverse=True,
        )[:10]

        medalhas = ["🥇", "🥈", "🥉"] + [f"**{i}.**" for i in range(4, 11)]
        linhas   = []

        for i, (uid, user) in enumerate(ordenado):
            membro = ctx.guild.get_member(int(uid))
            nome   = membro.display_name if membro else f"Usuário {uid}"
            linhas.append(f"{medalhas[i]} {nome} — Nível **{user['nivel']}** | {user['xp']} XP")

        embed = discord.Embed(
            title="🏆 Top 10 — Ranking de Níveis",
            description="\n".join(linhas),
            color=0xFFD700,
        )
        await ctx.send(embed=embed)

    # ── >setxp (owner) ───────────────────────────────────────
    @commands.command(name="setxp")
    @commands.has_permissions(administrator=True)
    async def setxp(self, ctx: commands.Context, membro: discord.Member, xp: int):
        """[Admin] Define o XP de um membro manualmente."""
        data       = carregar_xp()
        uid        = str(membro.id)
        user       = self._get_usuario(data, uid)
        user["xp"] = max(0, xp)
        salvar_xp(data)
        await ctx.send(f"{AXOLOTE} XP de {membro.mention} definido para **{xp}**!")


async def setup(bot: commands.Bot):
    await bot.add_cog(Niveis(bot))