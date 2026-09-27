# ALT

> **The Discord bot behind Axolotl BR.**
> **Sua comunidade na internet.**

ALT é o bot oficial da comunidade **Axolotl BR** — feita para a internet, por gente da internet.

Ele cuida dos sistemas do servidor, automação, moderação e comunidade — simples o bastante para continuar sendo construído e testado.

**Player to Player.**

Feito por players, feito para players.

---

## O que ele faz

| Sistema | Comandos |
|---|---|
| **Geral** | `>axolotl` `>ping` `/ping` `>ajuda` `>restart` `>call` `>sair` |
| **Jogos** | `>ptp` `/ptp` `>placar` `>ranking` |
| **Níveis** | `>rank` `>top` `>setxp` *(admin)* |
| **Tickets** | `>setupticket` *(admin)* `>fecharticket` `>addticket` *(mod)* |
| **Extras** | resposta a `w`, repost de gif, status rotativo |

---

## Stack

* Python 3.12+
* [discord.py](https://discordpy.readthedocs.io/) 2.x
* SQLite (WAL) via stdlib
* [python-dotenv](https://pypi.org/project/python-dotenv/)

---

## Rodando local

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # preencha o TOKEN
python main.py
```

Os intents privilegiados `members` e `message_content` precisam estar
ligados no [Developer Portal](https://discord.com/developers/applications)
do bot, em **Bot → Privileged Gateway Intents**.

---

## Variáveis de ambiente

| Variável | Obrigatória | Para quê |
|---|---|---|
| `TOKEN` | sim | token do bot |
| `GUILD_ID` | recomendado | sincroniza slash commands só no seu servidor (segundos, em vez de até 1h do sync global) |
| `MOD_ROLE_ID` | para tickets | cargo que entra automaticamente nos tickets |
| `TICKET_CHANNEL_ID` | para tickets | canal onde `>setupticket` publica o dropdown |
| `TICKET_BANNER_URL` | opcional | imagem do embed da central de ajuda |
| `REPOST_GIF` | opcional | link repostado quando aparece na conversa (vazio = desativado) |

As URLs do Discord CDN carregam assinatura e **expiram**. Por isso
`TICKET_BANNER_URL` e `REPOST_GIF` são variáveis, e não constantes no
código — quando expirarem, troque sem precisar fazer deploy.

---

## Deploy (ShardCloud)

`basic` — 512 MB de RAM, suficiente para o bot + web no mesmo processo.

Arquivos necessários na raiz: `main.py`, `requirements.txt`, `.shardcloud`.

> ⚠️ **Nunca inclua o `.env` no arquivo enviado.** Ele contém o token do
> bot. No deploy, defina as variáveis de ambiente pelo painel da
> ShardCloud. Compactar a pasta inteira como está sobe o token junto.

Antes de compactar, remova: `__pycache__/`, `*.pyc`, `data/`, `.env`,
`venv/`, `.idea/`.

O `.shardcloud` precisa apontar `MAIN=main.py` em minúsculas — o
container é Linux e diferencia maiúsculas de minúsculas.

> **Publicação na Web** exige no mínimo 512 MB. Se for ligar o site /
> dashboard, o servidor HTTP precisa escutar na **porta 80** (não em
> `process.env.PORT`) e o `MEMORY` já precisa estar em 512 ou mais.

O banco fica em `/app/data/alt.db` e persiste entre deploys. Backups
automáticos só existem nos planos superiores — copie o arquivo
periodicamente se os dados importarem.

---

## Estrutura

```
main.py              entrada: intents, cogs, slash sync, logging
brand.py             paleta e constantes de identidade
database.py          SQLite (WAL) — XP, níveis e placar
cogs/
  auto_response.py   resposta a "w" e repost de gif
  status.py          status rotativo
  jogos.py           pedra, tesoura e papel
  niveis.py          XP e níveis
  tickets.py         tickets via thread privada
```

Constantes de cor, símbolo e assinaturas ficam em `brand.py` — não
espalhe hex novo pelo código.

---

## Licença

Parte do ecossistema **Axolotl BR**. © 2020 – 2026.
