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
| **Jogos** | `>ptp` `/ptp` `>placar` `>ranking` (vitória +20 💎, empate +5) |
| **Níveis** | `>rank` `>top` `>setxp` *(admin)* |
| **Economia** | `>saldo` `/saldo` `>daily` `/daily` `>pay` `>dar` *(admin)* `>loja` `>buy` `>aura` `>auras` `>roll` `/roll` `>colecao` `>topdima` |
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
| `AXOLOTL_EMOJI` | recomendado | emoji oficial `:02:` como `<:02:ID>` (fallback 🫟) |
| `AMETHYST_EMOJI` | recomendado | `:amethyst:` do servidor como `<:amethyst:ID>` (fallback 💜) |
| `DIAMANTE_EMOJI` | opcional | custom de diamante (padrão 💎) |

As URLs do Discord CDN carregam assinatura e **expiram**. Por isso
`TICKET_BANNER_URL` e `REPOST_GIF` são variáveis, e não constantes no
código — quando expirarem, troque sem precisar fazer deploy.

---

## Estrutura

```
main.py              entrada: intents, cogs, slash sync, logging
brand.py             paleta e constantes de identidade
database.py          SQLite (WAL) — XP, níveis, placar e economia
cogs/
  auto_response.py   resposta a "w" e repost de gif
  status.py          status rotativo
  jogos.py           pedra, tesoura e papel (+diamantes)
  niveis.py          XP e níveis
  economia.py        diamantes, ametista, daily, loja, auras, roll/coleção
  tickets.py         tickets via thread privada
```

Constantes de cor, símbolo e assinaturas ficam em `brand.py` — não
espalhe hex novo pelo código.

---

## Licença

Parte do ecossistema **Axolotl BR**. © 2020 – 2026.
