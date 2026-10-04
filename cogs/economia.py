import asyncio
import logging
import random
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

import brand
import database

log = logging.getLogger("alt.economia")

# ── ganhos ───────────────────────────────────────────────────
DAILY_DIAMANTES = 100
DAILY_AMETISTA = 2

MSG_COOLDOWN = 60  # segundos
MSG_DIMA_MIN = 5
MSG_DIMA_MAX = 15

ROLL_CUSTO = 5  # ametista por giro

# ── auras (id -> nome, preço em ametista, descrição) ──────────
AURAS = {
    "brisa":      {"nome": "brisa do lago",         "preco": 10,  "desc": "aura inicial do lago"},
    "musgo":      {"nome": "manto de musgo",        "preco": 25,  "desc": "camuflagem tranquila"},
    "profundeza": {"nome": "olhar das profundezas", "preco": 50,  "desc": "o fundo do lago te observa"},
    "dourada":    {"nome": "escama dourada",        "preco": 100, "desc": "brilho raro de player antigo"},
    "ancestral":  {"nome": "presença ancestral",    "preco": 200, "desc": "o lago inteiro respeita"},
}

# ── axolotls colecionáveis (gacha, peso soma 100) ─────────────
AXOLOTLS = {
    "bebe":      {"nome": "bebê axolotl",       "rar": "comum",    "peso": 40},
    "rosa":      {"nome": "axolotl rosa",       "rar": "comum",    "peso": 25},
    "musgo":     {"nome": "axolotl de musgo",   "rar": "incomum",  "peso": 15},
    "dourado":   {"nome": "axolotl dourado",    "rar": "raro",     "peso": 10},
    "cristal":   {"nome": "axolotl de cristal", "rar": "épico",    "peso": 6},
    "abissal":   {"nome": "axolotl abissal",    "rar": "épico",    "peso": 3},
    "ancestral": {"nome": "axolotl ancestral",  "rar": "lendário", "peso": 1},
}

COR_RAR = {
    "comum": brand.TEXT_DIM,
    "incomum": brand.SECONDARY,
    "raro": brand.INFO,
    "épico": brand.PRIMARY,
    "lendário": brand.WARNING,
}

# Opções de aura pros slash (nome bonito -> id).
_ESCOLHAS_AURA = [
    app_commands.Choice(name=info["nome"], value=aid) for aid, info in AURAS.items()
]


def _sortear_axolotl() -> str:
    ids = list(AXOLOTLS)
    pesos = [AXOLOTLS[i]["peso"] for i in ids]
    return random.choices(ids, weights=pesos, k=1)[0]


def _embed_saldo(membro: discord.Member, dima: int, amet: int, aura_id: str | None, total_axo: int) -> discord.Embed:
    aura_nome = AURAS[aura_id]["nome"] if aura_id in AURAS else "nenhuma"
    embed = discord.Embed(
        title=f"{brand.AXOLOTL} saldo de {membro.display_name}",
        color=brand.PRIMARY,
    )
    embed.add_field(name=f"{brand.DIAMANTE} diamantes", value=str(dima), inline=True)
    embed.add_field(name=f"{brand.AMETHYST} ametista", value=str(amet), inline=True)
    embed.add_field(name="✨ aura", value=aura_nome, inline=True)
    embed.add_field(name=f"{brand.AXOLOTL} axolotls", value=str(total_axo), inline=True)
    embed.set_thumbnail(url=membro.display_avatar.url)
    embed.set_footer(text=brand.FOOTER)
    return embed


class Economia(commands.Cog, name="Economia"):
    """diamantes, ametista, auras e coleção de axolotls."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cooldown: dict[int, float] = {}

    # ── farm passivo por mensagem ────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        agora = discord.utils.utcnow().timestamp()
        if agora - self.cooldown.get(message.author.id, 0) < MSG_COOLDOWN:
            return
        self.cooldown[message.author.id] = agora
        ganho = random.randint(MSG_DIMA_MIN, MSG_DIMA_MAX)
        await asyncio.to_thread(database.adicionar_diamantes, message.author.id, ganho)

    # ── >saldo / /saldo ─────────────────────────────────────
    @commands.command(name="saldo")
    async def saldo(self, ctx: commands.Context, membro: discord.Member = None):
        """veja seus diamantes, ametista, aura e coleção."""
        membro = membro or ctx.author
        dima, amet, aura = await asyncio.to_thread(database.buscar_saldo, membro.id)
        colecao = await asyncio.to_thread(database.buscar_colecao, membro.id)
        total = sum(q for _, q in colecao)
        await ctx.send(embed=_embed_saldo(membro, dima, amet, aura, total))

    @app_commands.command(name="saldo", description="veja seus diamantes, ametista, aura e coleção.")
    async def saldo_slash(self, interaction: discord.Interaction):
        dima, amet, aura = await asyncio.to_thread(database.buscar_saldo, interaction.user.id)
        colecao = await asyncio.to_thread(database.buscar_colecao, interaction.user.id)
        total = sum(q for _, q in colecao)
        membro = interaction.user
        await interaction.response.send_message(
            embed=_embed_saldo(membro, dima, amet, aura, total)
        )

    # ── >daily / /daily ─────────────────────────────────────
    async def _daily(self, user_id: int) -> tuple[bool, int, int]:
        hoje = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return await asyncio.to_thread(
            database.tentar_daily, user_id, DAILY_DIAMANTES, DAILY_AMETISTA, hoje
        )

    @commands.command(name="daily")
    async def daily(self, ctx: commands.Context):
        """resgate diário: diamantes + ametista. 1x por dia."""
        ok, dima, amet = await self._daily(ctx.author.id)
        if not ok:
            await ctx.send(
                f"{brand.AXOLOTL} {ctx.author.mention} você já resgatou hoje! volta amanhã."
            )
            return
        await ctx.send(
            f"{brand.AXOLOTL} {ctx.author.mention} resgatou "
            f"**{DAILY_DIAMANTES}** {brand.DIAMANTE} + **{DAILY_AMETISTA}** {brand.AMETHYST}!"
        )

    @app_commands.command(name="daily", description="resgate diário: diamantes + ametista.")
    async def daily_slash(self, interaction: discord.Interaction):
        ok, _, _ = await self._daily(interaction.user.id)
        if not ok:
            await interaction.response.send_message(
                f"{brand.AXOLOTL} você já resgatou hoje! volta amanhã.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"{brand.AXOLOTL} resgatado: **{DAILY_DIAMANTES}** {brand.DIAMANTE} + "
            f"**{DAILY_AMETISTA}** {brand.AMETHYST}!"
        )

    # ── >pay ─────────────────────────────────────────────────
    @commands.command(name="pay")
    async def pay(self, ctx: commands.Context, membro: discord.Member = None, qtd: int = 0):
        """transfira diamantes pra outro membro. ex: `>pay @ana 50`."""
        if membro is None or qtd <= 0:
            await ctx.send(f"{brand.AXOLOTL} uso: `>pay @membro quantia` (mínimo 1).")
            return
        if membro.bot:
            await ctx.send(f"{brand.AXOLOTL} não dá pra pagar pra bot.")
            return
        if membro.id == ctx.author.id:
            await ctx.send(f"{brand.AXOLOTL} não dá pra pagar pra você mesmo.")
            return
        ok, _, _ = await asyncio.to_thread(
            database.transferir_diamantes, ctx.author.id, membro.id, qtd
        )
        if not ok:
            await ctx.send(
                f"{brand.AXOLOTL} {ctx.author.mention} saldo insuficiente!"
            )
            return
        await ctx.send(
            f"{brand.DIAMANTE} {ctx.author.mention} enviou **{qtd}** diamantes pra {membro.mention}!"
        )

    # ── >dar (admin) ─────────────────────────────────────────
    @commands.command(name="dar")
    @commands.has_permissions(administrator=True)
    async def dar(self, ctx: commands.Context, membro: discord.Member = None, moeda: str = "", qtd: int = 0):
        """[admin] dá moedas. ex: `>dar @ana diamantes 100` ou `>dar @ana ametista 5`."""
        moeda = moeda.lower()
        if membro is None or qtd <= 0 or moeda not in ("diamantes", "diamante", "dima", "ametista", "amet"):
            await ctx.send(
                f"{brand.AXOLOTL} uso: `>dar @membro diamantes|ametista quantia`."
            )
            return
        if moeda in ("diamantes", "diamante", "dima"):
            total = await asyncio.to_thread(database.adicionar_diamantes, membro.id, qtd)
            await ctx.send(
                f"{brand.DIAMANTE} {membro.mention} recebeu **{qtd}** diamantes! (total: **{total}**)"
            )
        else:
            total = await asyncio.to_thread(database.adicionar_ametista, membro.id, qtd)
            await ctx.send(
                f"{brand.AMETHYST} {membro.mention} recebeu **{qtd}** ametista! (total: **{total}**)"
            )

    # ── >loja ────────────────────────────────────────────────
    @commands.command(name="loja")
    async def loja(self, ctx: commands.Context):
        """mostra as auras à venda e o giro de axolotl."""
        dima, amet, aura = await asyncio.to_thread(database.buscar_saldo, ctx.author.id)
        linhas = []
        for aid, info in AURAS.items():
            dono = "✅" if await asyncio.to_thread(database.tem_aura, ctx.author.id, aid) else ""
            equip = " (equipada)" if aura == aid else ""
            linhas.append(
                f"`{aid}` — **{info['nome']}** — **{info['preco']}** {brand.AMETHYST} {dono}{equip}\n└ {info['desc']}"
            )
        embed = discord.Embed(
            title=f"{brand.AXOLOTL} loja do lago",
            description="\n\n".join(linhas),
            color=brand.PRIMARY,
        )
        embed.add_field(
            name=f"{brand.AXOLOTL} giro de axolotl",
            value=f"`>roll` — **{ROLL_CUSTO}** {brand.AMETHYST} por giro. sorteia 1 dos 7 axolotls.",
            inline=False,
        )
        embed.add_field(
            name="seu saldo",
            value=f"**{dima}** {brand.DIAMANTE} • **{amet}** {brand.AMETHYST}",
            inline=False,
        )
        embed.set_footer(text=f">buy <id> compra aura • >aura <id> equipa • {brand.FOOTER}")
        await ctx.send(embed=embed)

    # ── >buy ─────────────────────────────────────────────────
    @commands.command(name="buy")
    async def buy(self, ctx: commands.Context, aura_id: str = None):
        """compra uma aura com ametista. ex: `>buy brisa`."""
        if aura_id is None or aura_id.lower() not in AURAS:
            await ctx.send(
                f"{brand.AXOLOTL} aura inválida! veja com `>loja`. opções: "
                + ", ".join(f"`{k}`" for k in AURAS)
            )
            return
        aura_id = aura_id.lower()
        if await asyncio.to_thread(database.tem_aura, ctx.author.id, aura_id):
            await ctx.send(f"{brand.AXOLOTL} você já tem essa aura! use `>aura {aura_id}` pra equipar.")
            return
        _, amet, _ = await asyncio.to_thread(database.buscar_saldo, ctx.author.id)
        preco = AURAS[aura_id]["preco"]
        if amet < preco:
            await ctx.send(
                f"{brand.AMETHYST} faltam **{preco - amet}** ametista pra **{AURAS[aura_id]['nome']}**!"
            )
            return
        await asyncio.to_thread(database.adicionar_ametista, ctx.author.id, -preco)
        await asyncio.to_thread(database.dar_aura, ctx.author.id, aura_id)
        await asyncio.to_thread(database.equipar_aura, ctx.author.id, aura_id)
        await ctx.send(
            f"{brand.AXOLOTL} {ctx.author.mention} comprou e equipou **{AURAS[aura_id]['nome']}**! ✨"
        )

    # ── >aura / >auras ───────────────────────────────────────
    @commands.command(name="aura")
    async def aura(self, ctx: commands.Context, aura_id: str = None):
        """equipa uma aura que você já tem. ex: `>aura brisa`."""
        if aura_id is None:
            await ctx.send(f"{brand.AXOLOTL} uso: `>aura <id>` — veja as suas com `>auras`.")
            return
        aura_id = aura_id.lower()
        if aura_id not in AURAS:
            await ctx.send(f"{brand.AXOLOTL} essa aura não existe! veja com `>loja`.")
            return
        if not await asyncio.to_thread(database.tem_aura, ctx.author.id, aura_id):
            await ctx.send(f"{brand.AXOLOTL} você ainda não tem essa aura! compre com `>buy {aura_id}`.")
            return
        await asyncio.to_thread(database.equipar_aura, ctx.author.id, aura_id)
        await ctx.send(f"✨ {ctx.author.mention} equipou **{AURAS[aura_id]['nome']}**!")

    @commands.command(name="auras")
    async def auras(self, ctx: commands.Context):
        """lista as auras que você possui."""
        _, _, equipada = await asyncio.to_thread(database.buscar_saldo, ctx.author.id)
        posses = await asyncio.to_thread(database.auras_usuario, ctx.author.id)
        if not posses:
            await ctx.send(f"{brand.AXOLOTL} você ainda não tem auras! veja com `>loja`.")
            return
        linhas = []
        for aid in posses:
            marca = " (equipada)" if aid == equipada else ""
            linhas.append(f"• **{AURAS[aid]['nome']}** (`{aid}`){marca}")
        await ctx.send(f"✨ suas auras:\n" + "\n".join(linhas))

    # ── >roll ────────────────────────────────────────────────
    @commands.command(name="roll")
    async def roll(self, ctx: commands.Context):
        """gira a coleção: 5 ametista = 1 axolotl aleatório."""
        _, amet, _ = await asyncio.to_thread(database.buscar_saldo, ctx.author.id)
        if amet < ROLL_CUSTO:
            await ctx.send(
                f"{brand.AMETHYST} você precisa de **{ROLL_CUSTO}** ametista pra girar! "
                f"(você tem **{amet}** — pegue com `>daily`)"
            )
            return
        await asyncio.to_thread(database.adicionar_ametista, ctx.author.id, -ROLL_CUSTO)
        sorteado = _sortear_axolotl()
        qtd = await asyncio.to_thread(database.adicionar_axolotl, ctx.author.id, sorteado)
        info = AXOLOTLS[sorteado]
        embed = discord.Embed(
            title=f"{brand.AXOLOTL} {info['nome']}!",
            description=(
                f"{ctx.author.mention} tirou um **{info['nome']}** ({info['rar']})!\n"
                f"você tem **{qtd}x** esse."
            ),
            color=COR_RAR.get(info["rar"], brand.PRIMARY),
        )
        embed.set_footer(text=brand.FOOTER)
        await ctx.send(embed=embed)

    @app_commands.command(name="roll", description="gire 5 ametista e tire um axolotl aleatório.")
    async def roll_slash(self, interaction: discord.Interaction):
        _, amet, _ = await asyncio.to_thread(database.buscar_saldo, interaction.user.id)
        if amet < ROLL_CUSTO:
            await interaction.response.send_message(
                f"{brand.AMETHYST} você precisa de **{ROLL_CUSTO}** ametista pra girar!",
                ephemeral=True,
            )
            return
        await asyncio.to_thread(database.adicionar_ametista, interaction.user.id, -ROLL_CUSTO)
        sorteado = _sortear_axolotl()
        qtd = await asyncio.to_thread(database.adicionar_axolotl, interaction.user.id, sorteado)
        info = AXOLOTLS[sorteado]
        embed = discord.Embed(
            title=f"{brand.AXOLOTL} {info['nome']}!",
            description=f"você tirou **{info['nome']}** ({info['rar']})! você tem **{qtd}x**.",
            color=COR_RAR.get(info["rar"], brand.PRIMARY),
        )
        embed.set_footer(text=brand.FOOTER)
        await interaction.response.send_message(embed=embed)

    # ── >colecao ─────────────────────────────────────────────
    @commands.command(name="colecao")
    async def colecao(self, ctx: commands.Context, membro: discord.Member = None):
        """mostra sua coleção de axolotls (ou a de outro membro)."""
        membro = membro or ctx.author
        itens = await asyncio.to_thread(database.buscar_colecao, membro.id)
        if not itens:
            await ctx.send(
                f"{brand.AXOLOTL} {membro.display_name} ainda não tem axolotls! use `>roll`."
            )
            return
        linhas = []
        for aid, qtd in itens:
            info = AXOLOTLS.get(aid, {"nome": aid, "rar": "?"})
            linhas.append(f"• **{info['nome']}** ({info['rar']}) — **{qtd}x**")
        embed = discord.Embed(
            title=f"{brand.AXOLOTL} coleção de {membro.display_name}",
            description="\n".join(linhas),
            color=brand.PRIMARY,
        )
        embed.set_footer(text=f"{len(itens)}/{len(AXOLOTLS)} espécies • {brand.FOOTER}")
        await ctx.send(embed=embed)

    # ── >topdima ─────────────────────────────────────────────
    @commands.command(name="topdima")
    async def topdima(self, ctx: commands.Context):
        """ranking dos mais ricos em diamantes."""
        ranking = await asyncio.to_thread(database.top_diamantes, 10)
        if not ranking:
            await ctx.send(f"{brand.AXOLOTL} ninguém tem diamantes ainda! use `>daily`.")
            return
        medalhas = ["🥇", "🥈", "🥉"] + [f"**{i}.**" for i in range(4, 11)]
        linhas = []
        for i, (uid, dima) in enumerate(ranking):
            membro = ctx.guild.get_member(uid) if ctx.guild else None
            nome = membro.display_name if membro else f"usuário {uid}"
            linhas.append(f"{medalhas[i]} {nome} — **{dima}** {brand.DIAMANTE}")
        embed = discord.Embed(
            title=f"{brand.DIAMANTE} top diamantes",
            description="\n".join(linhas),
            color=brand.WARNING,
        )
        embed.set_footer(text=brand.FOOTER)
        await ctx.send(embed=embed)

    # ── /pay ─────────────────────────────────────────────────
    @app_commands.command(name="pay", description="Transfira diamantes pra outro membro.")
    @app_commands.describe(membro="quem recebe", qtd="quantidade (mínimo 1)")
    async def pay_slash(
        self, interaction: discord.Interaction, membro: discord.Member, qtd: int
    ):
        """Versão slash do >pay."""
        autor = interaction.user
        if qtd <= 0:
            await interaction.response.send_message(
                f"{brand.AXOLOTL} a quantia mínima é 1.", ephemeral=True
            )
            return
        if membro.bot:
            await interaction.response.send_message(
                f"{brand.AXOLOTL} não dá pra pagar pra bot.", ephemeral=True
            )
            return
        if membro.id == autor.id:
            await interaction.response.send_message(
                f"{brand.AXOLOTL} não dá pra pagar pra você mesmo.", ephemeral=True
            )
            return
        ok, _, _ = await asyncio.to_thread(
            database.transferir_diamantes, autor.id, membro.id, qtd
        )
        if not ok:
            await interaction.response.send_message(
                f"{brand.AXOLOTL} saldo insuficiente!", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"{brand.DIAMANTE} {autor.mention} enviou **{qtd}** diamantes pra {membro.mention}!"
        )

    # ── /dar (admin) ─────────────────────────────────────────
    @app_commands.command(name="dar", description="[Admin] Dá moedas pra um membro.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(membro="quem recebe", moeda="qual moeda", qtd="quantidade")
    @app_commands.choices(moeda=[
        app_commands.Choice(name="diamantes", value="diamantes"),
        app_commands.Choice(name="ametista", value="ametista"),
    ])
    async def dar_slash(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        moeda: str,
        qtd: int,
    ):
        """Versão slash do >dar."""
        if qtd <= 0:
            await interaction.response.send_message(
                f"{brand.AXOLOTL} a quantia mínima é 1.", ephemeral=True
            )
            return
        if moeda == "diamantes":
            total = await asyncio.to_thread(database.adicionar_diamantes, membro.id, qtd)
            await interaction.response.send_message(
                f"{brand.DIAMANTE} {membro.mention} recebeu **{qtd}** diamantes! (total: **{total}**)"
            )
        else:
            total = await asyncio.to_thread(database.adicionar_ametista, membro.id, qtd)
            await interaction.response.send_message(
                f"{brand.AMETHYST} {membro.mention} recebeu **{qtd}** ametista! (total: **{total}**)"
            )

    # ── /loja ────────────────────────────────────────────────
    @app_commands.command(name="loja", description="Mostra as auras à venda e o giro de axolotl.")
    async def loja_slash(self, interaction: discord.Interaction):
        """Versão slash do >loja."""
        user_id = interaction.user.id
        dima, amet, aura = await asyncio.to_thread(database.buscar_saldo, user_id)
        linhas = []
        for aid, info in AURAS.items():
            dono = "✅" if await asyncio.to_thread(database.tem_aura, user_id, aid) else ""
            equip = " (equipada)" if aura == aid else ""
            linhas.append(
                f"`{aid}` — **{info['nome']}** — **{info['preco']}** {brand.AMETHYST} {dono}{equip}\n└ {info['desc']}"
            )
        embed = discord.Embed(
            title=f"{brand.AXOLOTL} loja do lago",
            description="\n\n".join(linhas),
            color=brand.PRIMARY,
        )
        embed.add_field(
            name=f"{brand.AXOLOTL} giro de axolotl",
            value=f"`/roll` — **{ROLL_CUSTO}** {brand.AMETHYST} por giro. sorteia 1 dos 7 axolotls.",
            inline=False,
        )
        embed.add_field(
            name="seu saldo",
            value=f"**{dima}** {brand.DIAMANTE} • **{amet}** {brand.AMETHYST}",
            inline=False,
        )
        embed.set_footer(text=f"/buy compra aura • /aura equipa • {brand.FOOTER}")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── /buy ─────────────────────────────────────────────────
    @app_commands.command(name="buy", description="Compra uma aura com ametista.")
    @app_commands.describe(aura_id="qual aura comprar")
    @app_commands.choices(aura_id=_ESCOLHAS_AURA)
    async def buy_slash(self, interaction: discord.Interaction, aura_id: str):
        """Versão slash do >buy."""
        user_id = interaction.user.id
        if await asyncio.to_thread(database.tem_aura, user_id, aura_id):
            await interaction.response.send_message(
                f"{brand.AXOLOTL} você já tem essa aura! equipe com `/aura`.",
                ephemeral=True,
            )
            return
        _, amet, _ = await asyncio.to_thread(database.buscar_saldo, user_id)
        preco = AURAS[aura_id]["preco"]
        if amet < preco:
            await interaction.response.send_message(
                f"{brand.AMETHYST} faltam **{preco - amet}** ametista pra **{AURAS[aura_id]['nome']}**!",
                ephemeral=True,
            )
            return
        await asyncio.to_thread(database.adicionar_ametista, user_id, -preco)
        await asyncio.to_thread(database.dar_aura, user_id, aura_id)
        await asyncio.to_thread(database.equipar_aura, user_id, aura_id)
        await interaction.response.send_message(
            f"{brand.AXOLOTL} você comprou e equipou **{AURAS[aura_id]['nome']}**! ✨"
        )

    # ── /aura ────────────────────────────────────────────────
    @app_commands.command(name="aura", description="Equipa uma aura que você já tem.")
    @app_commands.describe(aura_id="qual aura equipar")
    @app_commands.choices(aura_id=_ESCOLHAS_AURA)
    async def aura_slash(self, interaction: discord.Interaction, aura_id: str):
        """Versão slash do >aura."""
        user_id = interaction.user.id
        if not await asyncio.to_thread(database.tem_aura, user_id, aura_id):
            await interaction.response.send_message(
                f"{brand.AXOLOTL} você ainda não tem essa aura! compre com `/buy`.",
                ephemeral=True,
            )
            return
        await asyncio.to_thread(database.equipar_aura, user_id, aura_id)
        await interaction.response.send_message(
            f"✨ você equipou **{AURAS[aura_id]['nome']}**!"
        )

    # ── /auras ───────────────────────────────────────────────
    @app_commands.command(name="auras", description="Lista as auras que você possui.")
    async def auras_slash(self, interaction: discord.Interaction):
        """Versão slash do >auras."""
        user_id = interaction.user.id
        _, _, equipada = await asyncio.to_thread(database.buscar_saldo, user_id)
        posses = await asyncio.to_thread(database.auras_usuario, user_id)
        if not posses:
            await interaction.response.send_message(
                f"{brand.AXOLOTL} você ainda não tem auras! veja com `/loja`.",
                ephemeral=True,
            )
            return
        linhas = []
        for aid in posses:
            marca = " (equipada)" if aid == equipada else ""
            linhas.append(f"• **{AURAS[aid]['nome']}** (`{aid}`){marca}")
        await interaction.response.send_message(
            "✨ suas auras:\n" + "\n".join(linhas), ephemeral=True
        )

    # ── /colecao ─────────────────────────────────────────────
    @app_commands.command(name="colecao", description="Mostra a coleção de axolotls.")
    @app_commands.describe(membro="ver a coleção de outro membro (opcional)")
    async def colecao_slash(
        self, interaction: discord.Interaction, membro: discord.Member | None = None
    ):
        """Versão slash do >colecao."""
        membro = membro or interaction.user
        itens = await asyncio.to_thread(database.buscar_colecao, membro.id)
        if not itens:
            await interaction.response.send_message(
                f"{brand.AXOLOTL} {membro.display_name} ainda não tem axolotls! use `/roll`.",
                ephemeral=True,
            )
            return
        linhas = []
        for aid, qtd in itens:
            info = AXOLOTLS.get(aid, {"nome": aid, "rar": "?"})
            linhas.append(f"• **{info['nome']}** ({info['rar']}) — **{qtd}x**")
        embed = discord.Embed(
            title=f"{brand.AXOLOTL} coleção de {membro.display_name}",
            description="\n".join(linhas),
            color=brand.PRIMARY,
        )
        embed.set_footer(text=f"{len(itens)}/{len(AXOLOTLS)} espécies • {brand.FOOTER}")
        await interaction.response.send_message(embed=embed)

    # ── /topdima ─────────────────────────────────────────────
    @app_commands.command(name="topdima", description="Ranking dos mais ricos em diamantes.")
    async def topdima_slash(self, interaction: discord.Interaction):
        """Versão slash do >topdima."""
        ranking = await asyncio.to_thread(database.top_diamantes, 10)
        if not ranking:
            await interaction.response.send_message(
                f"{brand.AXOLOTL} ninguém tem diamantes ainda! use `/daily`.",
                ephemeral=True,
            )
            return
        medalhas = ["🥇", "🥈", "🥉"] + [f"**{i}.**" for i in range(4, 11)]
        linhas = []
        for i, (uid, dima) in enumerate(ranking):
            membro = interaction.guild.get_member(uid) if interaction.guild else None
            nome = membro.display_name if membro else f"usuário {uid}"
            linhas.append(f"{medalhas[i]} {nome} — **{dima}** {brand.DIAMANTE}")
        embed = discord.Embed(
            title=f"{brand.DIAMANTE} top diamantes",
            description="\n".join(linhas),
            color=brand.WARNING,
        )
        embed.set_footer(text=brand.FOOTER)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Economia(bot))
