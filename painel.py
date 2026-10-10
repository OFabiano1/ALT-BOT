# isso aq monta container roxo padrao pra todo o bot.
# um lugar so pra nao espalhar layout: titulo, texto/campos,
# imagem, avatar, botoes. tudo que era embed vira daqui.

import discord
from discord.components import MediaGalleryItem

import visual


def _texto(
    titulo: str, linhas: list[str] | None, campos: list | None, rodape: str
) -> str:
    partes = [titulo] if titulo else []
    if linhas:
        partes.append("\n".join(linhas))
    for nome, valor in campos or []:
        partes.append(f"**{nome}**\n{valor}")
    partes.append(rodape)
    return "\n".join(partes)


def montar(
    titulo: str,
    linhas: list[str] | None = None,
    campos: list | None = None,
    imagem: str | None = None,
    avatar: str | None = None,
    botoes: list | None = None,
    timeout: float | None = 180,
    accent: int | None = None,
    rodape: str | None = None,
) -> discord.ui.LayoutView:
    """LayoutView com container (roxo por padrao). botoes vao em fileiras dentro."""
    corpo = _texto(titulo, linhas, campos, visual.FOOTER if rodape is None else rodape)
    filhos: list = []
    if avatar:
        filhos.append(
            discord.ui.Section(
                discord.ui.TextDisplay(corpo),
                accessory=discord.ui.Thumbnail(media=avatar),
            )
        )
    else:
        filhos.append(discord.ui.TextDisplay(corpo))
    if imagem:
        filhos.append(discord.ui.MediaGallery(MediaGalleryItem(media=imagem)))
    soltos = [b for b in (botoes or []) if not isinstance(b, discord.ui.ActionRow)]
    prontas = [b for b in (botoes or []) if isinstance(b, discord.ui.ActionRow)]
    for i in range(0, len(soltos), 5):
        linha = discord.ui.ActionRow()
        for b in soltos[i : i + 5]:
            linha.add_item(b)
        filhos.append(linha)
    filhos.extend(prontas)
    container = discord.ui.Container(
        *filhos, accent_colour=visual.PRIMARY if accent is None else accent
    )
    view = discord.ui.LayoutView(timeout=timeout)
    view.add_item(container)
    return view


def fileiras(botoes: list) -> list:
    """agrupa botoes em fileiras de 5 (ActionRow)."""
    linhas = []
    for i in range(0, len(botoes), 5):
        linha = discord.ui.ActionRow()
        for b in botoes[i : i + 5]:
            linha.add_item(b)
        linhas.append(linha)
    return linhas
