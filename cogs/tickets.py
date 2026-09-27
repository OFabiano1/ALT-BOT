import logging
import os

import discord
from discord.ext import commands

import brand

log = logging.getLogger("alt.tickets")

# ── Configure aqui ou no .env ────────────────────────────────
MOD_ROLE_ID       = int(os.getenv("MOD_ROLE_ID", "0"))
TICKET_CHANNEL_ID = int(os.getenv("TICKET_CHANNEL_ID", "0"))
TICKET_BANNER_URL = os.getenv("TICKET_BANNER_URL", "")
# ─────────────────────────────────────────────────────────────

# 7 dias em minutos — o padrão do Discord, então o ticket não
# archiva enquanto a conversa estiver ativa.
AUTO_ARCHIVE = 10080


def _ids_configurados() -> bool:
    return bool(MOD_ROLE_ID and TICKET_CHANNEL_ID)


async def criar_ticket(interaction: discord.Interaction, emoji: str, label: str):
    canal = interaction.channel

    # Procura um ticket aberto do mesmo usuário antes de criar outro.
    for thread in canal.threads:
        if str(interaction.user.id) in thread.name and not thread.archived:
            await interaction.response.send_message(
                ephemeral=True,
                content="você já tem um atendimento em andamento!",
            )
            return

    async for thread in canal.archived_threads(private=True):
        if str(interaction.user.id) in thread.name and not thread.archived:
            await interaction.response.send_message(
                ephemeral=True,
                content="você já tem um atendimento em andamento!",
            )
            return

    # Reaproveita um ticket arquivado do mesmo usuário em vez de abrir outro.
    ticket = None
    async for thread in canal.archived_threads(private=True):
        if str(interaction.user.id) in thread.name:
            ticket = thread
            break

    nome_thread = f"{emoji} | {interaction.user.name} - {interaction.user.id}"

    if ticket is not None:
        await ticket.edit(archived=False, locked=False)
        await ticket.edit(name=nome_thread, auto_archive_duration=AUTO_ARCHIVE, invitable=False)
    else:
        ticket = await canal.create_thread(
            name=nome_thread,
            type=discord.ChannelType.private_thread,
            auto_archive_duration=AUTO_ARCHIVE,
            invitable=False,
        )

    if MOD_ROLE_ID:
        cargo_mod = interaction.guild.get_role(MOD_ROLE_ID)
        if cargo_mod:
            for membro in cargo_mod.members:
                await ticket.add_user(membro)

    await interaction.response.send_message(
        ephemeral=True,
        content=f"criei um ticket para você! {ticket.mention}",
    )

    embed = discord.Embed(
        title=f"{emoji} {label}",
        description=(
            f"{interaction.user.mention} ticket criado!\n\n"
            "envie todas as informações possíveis sobre seu caso e aguarde até que um "
            "atendente responda.\n\n"
            "após a sua questão ser sanada, use `>fecharticket` para encerrar o atendimento."
        ),
        color=brand.PRIMARY,
    )
    embed.set_footer(text=f"ALT • Sistema de Tickets • {brand.FOOTER}")
    await ticket.send(embed=embed)


class Dropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(value="ticket",   label="Ticket",   emoji="🎫"),
            discord.SelectOption(value="denuncia", label="Denúncia", emoji="🚨"),
        ]
        super().__init__(
            placeholder="selecione uma opção...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="persistent_view:dropdown_help",
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "ticket":
            await criar_ticket(interaction, "🎫", "Ticket")
        elif self.values[0] == "denuncia":
            await criar_ticket(interaction, "🚨", "Denúncia")


class DropdownView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Dropdown())


class Tickets(commands.Cog, name="tickets"):
    """Sistema de tickets via thread privada."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(DropdownView())
        if not _ids_configurados():
            log.warning(
                "MOD_ROLE_ID / TICKET_CHANNEL_ID nao definidos — "
                ">setupticket e o preenchimento automatico de moderadores ficam inativos"
            )

    # ── >setupticket ─────────────────────────────────────────
    @commands.command(name="setupticket")
    @commands.has_permissions(administrator=True)
    async def setup_ticket(self, ctx: commands.Context):
        """[Admin] Envia o embed com o dropdown de tickets."""
        if not TICKET_CHANNEL_ID:
            await ctx.send("❌ `TICKET_CHANNEL_ID` não configurado!")
            return

        # get_channel() foi deprecado no discord.py 2.x.
        canal = ctx.guild.get_channel_or_thread(TICKET_CHANNEL_ID)
        if canal is None:
            await ctx.send("❌ canal de tickets não encontrado!")
            return

        embed = discord.Embed(
            title="Central de Ajuda",
            description=(
                "Boas-vindas ao atendimento do Axolotl BR\n"
                "Por aqui você pode reportar bugs de bots, realizar uma denúncia de outros "
                "membros, parcerias (sorteios, boost e patrocínios) e adicionar bots."
            ),
            color=brand.PRIMARY,
        )
        if TICKET_BANNER_URL:
            embed.set_image(url=TICKET_BANNER_URL)
        embed.set_footer(text=(
            f"© 2020 – 2026 Axolotl BR. Todos os direitos reservados.\n\n"
            "Para dar início ao seu atendimento, selecione uma das opções abaixo."
        ))

        await canal.send(embed=embed, view=DropdownView())
        await ctx.send("✅ embed de tickets enviado!", delete_after=5)

    # ── >fecharticket ────────────────────────────────────────
    @commands.command(name="fecharticket")
    async def fechar_ticket(self, ctx: commands.Context):
        """Fecha o ticket atual."""
        if not isinstance(ctx.channel, discord.Thread):
            await ctx.send("este comando só funciona dentro de um ticket!")
            return

        cargo_mod = ctx.guild.get_role(MOD_ROLE_ID) if MOD_ROLE_ID else None
        tem_permissao = str(ctx.author.id) in ctx.channel.name or (
            cargo_mod is not None and cargo_mod in ctx.author.roles
        )

        if not tem_permissao:
            await ctx.send("você não tem permissão para fechar este ticket!")
            return

        await ctx.send(f"o ticket foi fechado por {ctx.author.mention}, obrigado por entrar em contato!")
        await ctx.channel.edit(archived=True, locked=True)

    # ── >addticket ───────────────────────────────────────────
    @commands.command(name="addticket")
    @commands.has_permissions(manage_threads=True)
    async def add_ticket(self, ctx: commands.Context, membro: discord.Member):
        """[Mod] Adiciona um membro ao ticket atual."""
        if not isinstance(ctx.channel, discord.Thread):
            await ctx.send("use dentro de um ticket!")
            return
        await ctx.channel.add_user(membro)
        await ctx.send(f"{membro.mention} adicionado ao ticket!")


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
