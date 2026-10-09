# isso aq desenha o card png do /stats com a cara do deadlock.
# fontes oficiais: retail demo no display, radiance no texto.
# retratos e ranks oficiais, tudo baixado da deadlock-api e
# cacheado em data/dl_assets. so pillow, sem matplotlib.
# sem rede no import: tudo que baixa roda via asyncio.to_thread no cog.
# qualquer falha levanta DeadlockCardError e o cog cai pro texto.

import concurrent.futures
import re
import threading
import unicodedata
from io import BytesIO
from pathlib import Path

import urllib.request

from PIL import Image, ImageDraw, ImageFont

import deadlock_api

# ─── erro ───


class DeadlockCardError(Exception):
    """nao deu pra montar o card (rede, fonte, imagem)."""


# ─── cores (as mesmas do visual.py) ───

BASE = (14, 17, 22)
BORDA = (42, 52, 64)
TEXTO = (232, 237, 242)
TEXTO_APAGADO = (138, 151, 166)
VIOLETA = (143, 0, 255)
VIOLETA_CLARO = (186, 108, 255)
VERDE = (74, 222, 128)

LARGURA = 1000
MARGEM = 40

HEADERS = {"User-Agent": "ALT-bot/1.0 (+discord)"}

ARQ_DISPLAY = "retaildemo-bold.otf"
ARQ_TEXTO = "radiance-regular.otf"
ARQ_TEXTO_BOLD = "radiance-bold.otf"

# a retail do cdn e subset: so isso desenha nela.
SEGUROS_DISPLAY = re.compile(r"[^A-Za-z0-9 .,]")


# ─── texto ───


def _seguro(texto: str) -> str:
    """pro display: sem acento e so caractere que a retail tem."""
    base = (
        unicodedata.normalize("NFKD", texto or "")
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return SEGUROS_DISPLAY.sub("", base)


# ─── arquivos ───


def _pasta() -> Path:
    pasta = Path(deadlock_api.__file__).parent / "data" / "dl_assets"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _baixar(url: str | None, nome: str) -> Path | None:
    """baixa uma vez e reusa do disco. None se sem url ou se falhar."""
    if not url:
        return None
    destino = _pasta() / nome
    if destino.exists() and destino.stat().st_size > 0:
        return destino
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as resp:
            dados = resp.read()
        if not dados:
            return None
        destino.write_bytes(dados)
        return destino
    except Exception:
        return None


# cache em memoria: retrato nao muda, nao faz sentido
# decodificar e redimensionar toda vez. lock pq o render
# roda em varias threads (asyncio.to_thread no cog).
_FONT_CACHE: dict = {}
_IMG_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()


def _baixar_todos(pares: list[tuple[str, str | None]]) -> None:
    """baixa em paralelo o que ainda nao esta no disco."""
    pasta = _pasta()
    alvos = [
        (nome, url)
        for nome, url in pares
        if url and not (pasta / nome).exists()
    ]
    if not alvos:
        return
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(8, len(alvos))
    ) as ex:
        list(ex.map(lambda p: _baixar(p[1], p[0]), alvos))


def _fontes():
    """pegar(estilo, tamanho): display, texto ou texto_bold."""
    mapa = deadlock_api.buscar_fontes()
    arq_display = _baixar(mapa.get(ARQ_DISPLAY), ARQ_DISPLAY)
    arq_texto = _baixar(mapa.get(ARQ_TEXTO), ARQ_TEXTO)
    arq_bold = _baixar(mapa.get(ARQ_TEXTO_BOLD), ARQ_TEXTO_BOLD)
    if arq_texto is None or arq_bold is None:
        raise DeadlockCardError("sem fonte oficial")
    if arq_display is None:
        arq_display = arq_bold  # reserva: radiance no lugar da retail

    def pegar(estilo: str, tamanho: int):
        chave = (estilo, tamanho)
        with _CACHE_LOCK:
            hit = _FONT_CACHE.get(chave)
        if hit is not None:
            return hit
        arq = {
            "display": arq_display,
            "texto": arq_texto,
            "texto_bold": arq_bold,
        }[estilo]
        try:
            fonte = ImageFont.truetype(str(arq), tamanho)
        except Exception as e:
            raise DeadlockCardError(f"fonte quebrou: {e}") from e
        with _CACHE_LOCK:
            _FONT_CACHE[chave] = fonte
        return fonte

    return pegar


# ─── imagens ───


def _arredondar(img: Image.Image, raio: int) -> Image.Image:
    mascara = Image.new("L", img.size, 0)
    ImageDraw.Draw(mascara).rounded_rectangle([0, 0, *img.size], raio, fill=255)
    saida = Image.new("RGBA", img.size, (0, 0, 0, 0))
    saida.paste(img, (0, 0), mascara)
    return saida


def _retrato(url: str | None, nome_arquivo: str, tamanho: int) -> Image.Image | None:
    """retrato quadrado arredondado. None se nao baixar/abrir."""
    chave = (nome_arquivo, tamanho)
    with _CACHE_LOCK:
        hit = _IMG_CACHE.get(chave)
    if hit is not None:
        return hit
    arq = _baixar(url, nome_arquivo)
    if arq is None:
        return None
    try:
        with Image.open(arq) as img:
            img = img.convert("RGBA")
            lado = min(img.size)
            esq = (img.size[0] - lado) // 2
            topo = (img.size[1] - lado) // 2
            img = img.crop((esq, topo, esq + lado, topo + lado))
            img = img.resize((tamanho, tamanho), Image.LANCZOS)
            resultado = _arredondar(img, tamanho // 4)
    except Exception:
        return None
    with _CACHE_LOCK:
        _IMG_CACHE[chave] = resultado
    return resultado


# ─── desenho ───


def _barra(
    desenho: ImageDraw.ImageDraw,
    x: int,
    y: int,
    largura: int,
    altura: int,
    fracao: float,
    cor: tuple = VIOLETA,
):
    fracao = max(0.0, min(1.0, fracao))
    desenho.rounded_rectangle([x, y, x + largura, y + altura], altura // 2, fill=BORDA)
    cheio = int(largura * fracao)
    if cheio > 0:
        desenho.rounded_rectangle([x, y, x + cheio, y + altura], altura // 2, fill=cor)


def _base(altura: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (LARGURA, altura), BASE)
    desenho = ImageDraw.Draw(img)
    desenho.rounded_rectangle([4, 4, LARGURA - 4, altura - 4], 28, outline=BORDA, width=2)
    return img, desenho


def _rodape(desenho: ImageDraw.ImageDraw, altura: int, pegar) -> None:
    texto = "Player to Player • Axolotl BR"
    fonte = pegar("texto", 20)
    comp = desenho.textlength(texto, font=fonte)
    desenho.text(
        (LARGURA - MARGEM - comp, altura - MARGEM),
        texto,
        font=fonte,
        fill=TEXTO_APAGADO,
    )


def _cabecalho(
    desenho: ImageDraw.ImageDraw,
    img: Image.Image,
    pegar,
    persona: str,
    rank_txt: str,
    retrato: Image.Image | None,
    rank_img: Image.Image | None,
) -> int:
    """header com retrato, nome e rank. retorna o y livre."""
    y = MARGEM
    if retrato is not None:
        img.paste(retrato, (MARGEM, y), retrato)
    else:
        desenho.rounded_rectangle([MARGEM, y, MARGEM + 120, y + 120], 24, fill=BORDA)
        desenho.text(
            (MARGEM + 44, y + 22), "?", font=pegar("display", 56), fill=TEXTO_APAGADO
        )
    desenho.text(
        (MARGEM + 150, y + 6),
        _seguro(persona)[:24],
        font=pegar("display", 56),
        fill=TEXTO,
    )
    rx = MARGEM + 150
    ry = y + 76
    if rank_img is not None:
        img.paste(rank_img, (rx, ry - 8), rank_img)
        rx += rank_img.size[0] + 12
    desenho.text(
        (rx, ry),
        _seguro(rank_txt) or "obscurus",
        font=pegar("display", 32),
        fill=VIOLETA_CLARO,
    )
    return y + 150


def _numeros(
    desenho: ImageDraw.ImageDraw,
    pegar,
    y: int,
    colunas: list[tuple[str, str, str]],
) -> int:
    """linha de numeros grandes: [(rotulo, valor, sufixo)]. retorna o y livre."""
    fonte_rotulo = pegar("texto", 24)
    fonte_valor = pegar("display", 44)
    fonte_sufixo = pegar("texto_bold", 32)
    largura_col = (LARGURA - MARGEM * 2) // max(1, len(colunas))
    for i, (rotulo, valor, sufixo) in enumerate(colunas):
        x = MARGEM + i * largura_col
        desenho.text((x, y), rotulo.upper(), font=fonte_rotulo, fill=TEXTO_APAGADO)
        desenho.text((x, y + 30), valor, font=fonte_valor, fill=TEXTO)
        if sufixo:
            off = desenho.textlength(valor, font=fonte_valor)
            desenho.text(
                (x + off + 6, y + 40), sufixo, font=fonte_sufixo, fill=TEXTO_APAGADO
            )
    return y + 96


def render(pacote: dict, periodo: str) -> bytes:
    """card png do stats. periodo: geral ou 7d. retorna os bytes."""
    try:
        r = pacote["resumo"]
        rank_assets = deadlock_api.buscar_rank_assets()
        tier = int(pacote.get("tier", 0) or 0)
        url_rank = (rank_assets.get(tier) or {}).get("imagem")
        retratos: dict = pacote.get("retratos", {})

        # prefetch paralelo: fontes + retratos + rank de uma vez.
        # sem isso o primeiro card pagava ~10 downloads em fila.
        mapa_fontes = deadlock_api.buscar_fontes()
        pares = [
            (ARQ_DISPLAY, mapa_fontes.get(ARQ_DISPLAY)),
            (ARQ_TEXTO, mapa_fontes.get(ARQ_TEXTO)),
            (ARQ_TEXTO_BOLD, mapa_fontes.get(ARQ_TEXTO_BOLD)),
            (f"rank_{tier}.png", url_rank),
        ]
        if periodo in ("7d", "1d"):
            hid_sem = int(r.get("heroi_top", 0) or 0)
            pares.append((f"heroi_{hid_sem}.png", retratos.get(hid_sem)))
        else:
            for hid, _, _ in r.get("top", []):
                pares.append((f"heroi_{hid}.png", retratos.get(hid)))
        _baixar_todos(pares)
        pegar = _fontes()

        if periodo in ("7d", "1d"):
            hid_top = int(r.get("heroi_top", 0) or 0)
            assets_top = pacote.get("hero_assets", {}).get(hid_top, {})
            retrato = _retrato(retratos.get(hid_top), f"heroi_{hid_top}.png", 120)
            rank_img = _retrato(url_rank, f"rank_{tier}.png", 56)
            altura = 480
            img, desenho = _base(altura)
            y = _cabecalho(
                desenho,
                img,
                pegar,
                pacote["persona"],
                pacote["rank_txt"],
                retrato,
                rank_img,
            )
            y = _numeros(
                desenho,
                pegar,
                y,
                [
                    ("partidas", str(r["partidas"]), ""),
                    ("vitórias", str(r["vitorias"]), ""),
                    ("kda", f"{r['kda']:.2f}", ""),
                ],
            )
            _barra(
                desenho,
                MARGEM,
                y,
                LARGURA - MARGEM * 2,
                26,
                (r["vitorias"] / r["partidas"]) if r["partidas"] else 0.0,
            )
            y += 44
            fonte_linha = pegar("texto", 24)
            desenho.text(
                (MARGEM, y),
                f"k {r['k']}  •  d {r['d']}  •  a {r['a']}",
                font=fonte_linha,
                fill=TEXTO_APAGADO,
            )
            y += 44
            nome_top = assets_top.get("nome", f"heroi {hid_top}")
            vazio_card = (
                "sem partidas hoje" if periodo == "1d" else "sem partidas nos últimos 7 dias"
            )
            desenho.text(
                (MARGEM, y),
                f"herói mais jogado: {nome_top} ({r['heroi_top_qtd']} partidas)"
                if r["heroi_top_qtd"]
                else vazio_card,
                font=pegar("texto_bold", 28),
                fill=TEXTO,
            )
        else:
            top = r.get("top", [])
            assets = pacote.get("hero_assets", {})
            hid_top = top[0][0] if top else 0
            retrato = _retrato(retratos.get(hid_top), f"heroi_{hid_top}.png", 120)
            rank_img = _retrato(url_rank, f"rank_{tier}.png", 56)
            altura = 480 + max(0, len(top)) * 64
            img, desenho = _base(altura)
            y = _cabecalho(
                desenho,
                img,
                pegar,
                pacote["persona"],
                pacote["rank_txt"],
                retrato,
                rank_img,
            )
            y = _numeros(
                desenho,
                pegar,
                y,
                [
                    ("partidas", str(r["partidas"]), ""),
                    ("vitórias", str(r["vitorias"]), ""),
                    ("win rate", f"{r['winrate']:.1f}", "%"),
                ],
            )
            _barra(
                desenho, MARGEM, y, LARGURA - MARGEM * 2, 26, r["winrate"] / 100.0
            )
            y += 44
            fonte_linha = pegar("texto", 24)
            desenho.text(
                (MARGEM, y),
                f"k {r['k']}  •  d {r['d']}  •  a {r['a']}  •  kda {r['kda']:.2f}",
                font=fonte_linha,
                fill=TEXTO_APAGADO,
            )
            y += 52
            desenho.text(
                (MARGEM, y),
                "HERÓIS PRINCIPAIS",
                font=fonte_linha,
                fill=TEXTO_APAGADO,
            )
            y += 36
            max_partidas = max([m for _, m, _ in top], default=1)
            fonte_heroi = pegar("texto", 28)
            for hid, partidas, vitorias in top:
                mini = _retrato(retratos.get(hid), f"heroi_{hid}.png", 48)
                if mini is not None:
                    img.paste(mini, (MARGEM, y), mini)
                nome = assets.get(hid, {}).get("nome", f"heroi {hid}")
                desenho.text(
                    (MARGEM + 62, y + 8), nome[:18], font=fonte_heroi, fill=TEXTO
                )
                placar = f"{partidas}p • {vitorias}v"
                comp = desenho.textlength(placar, font=fonte_heroi)
                desenho.text(
                    (LARGURA - MARGEM - comp - 320, y + 8),
                    placar,
                    font=fonte_heroi,
                    fill=TEXTO_APAGADO,
                )
                _barra(
                    desenho,
                    LARGURA - MARGEM - 300,
                    y + 14,
                    300,
                    20,
                    partidas / max_partidas,
                    VIOLETA,
                )
                y += 64

        _rodape(desenho, altura, pegar)
        saida = BytesIO()
        img.save(saida, format="PNG")
        return saida.getvalue()
    except DeadlockCardError:
        raise
    except Exception as e:
        raise DeadlockCardError(f"render quebrou: {e}") from e


# ─── rank ───


def _url_rank_sub(tier: int, sub: int) -> str | None:
    if tier <= 0:
        return None
    base = (deadlock_api.BASE or "").rstrip("/")
    if not base:
        return None
    return f"{base}/v1/assets/ranks/{tier}/{max(1, sub)}/image"


def render_rank(pacote: dict, info: dict) -> bytes:
    """card do rank: badge oficial, tier romano e progresso pro proximo."""
    try:
        pegar = _fontes()
        tier = int(info.get("tier", 0) or 0)
        sub = int(info.get("sub", 0) or 0)
        # proximo: sobe o sub, ou vira tier+1 sub 1. obscurus mira o tier 1.
        if info.get("topo"):
            nt, ns = 0, 0
        elif info.get("obscurus"):
            nt, ns = 1, 1
        elif sub >= 6:
            nt, ns = tier + 1, 1
        else:
            nt, ns = tier, sub + 1
        assets = deadlock_api.buscar_rank_assets()
        img_atual = (assets.get(tier) or {}).get("imagem")
        img_prox = (assets.get(nt) or {}).get("imagem") if nt else None
        _baixar_todos(
            [
                (f"trank_{tier}.png", img_atual),
                (f"trank_{nt}.png", img_prox),
            ]
        )
        atual = _retrato(img_atual, f"trank_{tier}.png", 200)
        prox = _retrato(img_prox, f"trank_{nt}.png", 200) if nt else None
        altura = 560
        img, desenho = _base(altura)
        desenho.text(
            (MARGEM, MARGEM),
            _seguro(pacote.get("persona", "steam")),
            font=pegar("display", 44),
            fill=TEXTO,
        )
        y_badge = 120
        if atual is not None:
            img.paste(atual, (MARGEM, y_badge), atual)
        x_prox = LARGURA - MARGEM - 200
        if prox is not None:
            img.paste(prox, (x_prox, y_badge), prox)
        else:
            desenho.text(
                (x_prox + 40, y_badge + 80),
                "TOPO",
                font=pegar("display", 48),
                fill=VIOLETA_CLARO,
            )
        fonte_nome = pegar("texto_bold", 28)
        nome_atual = _seguro(info.get("tier_nome", "obscurus")).upper()
        nome_prox = _seguro(info.get("proximo_nome", "")).upper()
        w = desenho.textlength(nome_atual, font=fonte_nome)
        desenho.text(
            (MARGEM + (200 - w) / 2, y_badge + 210),
            nome_atual,
            font=fonte_nome,
            fill=TEXTO,
        )
        if nome_prox:
            w2 = desenho.textlength(nome_prox, font=fonte_nome)
            desenho.text(
                (x_prox + (200 - w2) / 2, y_badge + 210),
                nome_prox,
                font=fonte_nome,
                fill=TEXTO,
            )
        y = y_badge + 280
        # pips dos subranks com parcial no atual
        if info.get("obscurus"):
            fracao, marcado = 0.0, 0
        elif info.get("topo"):
            fracao, marcado = 1.0, 6
        else:
            fracao = info.get("atual", 0) / 1000.0
            marcado = max(1, min(6, sub))
        x0, n_seg, gap = MARGEM, 6, 12
        larg = (LARGURA - MARGEM * 2 - gap * (n_seg - 1)) // n_seg
        for i in range(1, n_seg + 1):
            x = x0 + (i - 1) * (larg + gap)
            desenho.rounded_rectangle([x, y, x + larg, y + 26], 13, fill=BORDA)
            if info.get("topo") or i < marcado:
                desenho.rounded_rectangle([x, y, x + larg, y + 26], 13, fill=VERDE)
            elif i == marcado and fracao > 0:
                cheio = int(larg * max(0.0, min(1.0, fracao)))
                if cheio > 0:
                    desenho.rounded_rectangle([x, y, x + cheio, y + 26], 13, fill=VERDE)
        y += 44
        if marcado:
            cx = x0 + (marcado - 1) * (larg + gap) + larg / 2
            rom = deadlock_api.romano(marcado)
            fonte_rom = pegar("display", 36)
            w3 = desenho.textlength(rom, font=fonte_rom)
            desenho.text((cx - w3 / 2, y - 108), rom, font=fonte_rom, fill=TEXTO)
            desenho.polygon(
                [(cx - 10, y - 46), (cx + 10, y - 46), (cx, y - 34)],
                fill=TEXTO,
            )
            linha = (
                "topo! sem próximo."
                if info.get("topo")
                else f"faltam {info.get('falta', 0)} pontos"
            )
            desenho.text(
                (MARGEM, y),
                linha,
                font=pegar("texto", 24),
                fill=TEXTO_APAGADO,
            )
        else:
            desenho.text(
                (MARGEM, y),
                "em placement: jogue ranqueadas pra ganhar rank!",
                font=pegar("texto", 24),
                fill=TEXTO,
            )
        _rodape(desenho, altura, pegar)
        saida = BytesIO()
        img.save(saida, format="PNG")
        return saida.getvalue()
    except DeadlockCardError:
        raise
    except Exception as e:
        raise DeadlockCardError(f"render rank quebrou: {e}") from e
