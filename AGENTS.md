# AGENTS — ALT (Discord bot Axolotl BR)

## Marca (resumo MASTER UNIVERSE)

- **AXOLOTL BR — Sua comunidade na internet. De player para player. JOGAR. CRIAR. CONECTAR.**
- Voz: humana, PT-BR natural, direta. Nunca corporativa (`"solução inovadora"` proibido). Social: `"O servidor tá vivo. Cola aí."`
- Axolote 🫟 é símbolo, não decoração em tudo. Sem neon/RGB excessivo, sem template genérico de Discord/Minecraft, sem estética crypto/cassino.
- NUNCA: inventar números, status, usuários, eventos, parceiros, funcionalidades. Nunca misturar identidades antigas. Regra de ouro: parece Axolotl? fortalece? ajuda a comunidade? Se não, não criar.

## Stack

- Python 3.12+, `discord.py>=2.3.0` + `PyNaCl` + `davey` + `python-dotenv` (`requirements.txt`). SQLite WAL via stdlib, sem ORM.
- Entrada `main.py` (intents, cogs, slash sync). Identidade/cores só em `brand.py` — não espalhar hex.

## Run

- `python -m venv .venv; .venv\Scripts\activate; pip install -r requirements.txt; copy .env.example .env; python main.py`
- Ativar intents privilegiados `members` + `message_content` no Developer Portal.
- `.env`: `TOKEN` (obrigatório), `GUILD_ID` (slash em segundos), `MOD_ROLE_ID` + `TICKET_CHANNEL_ID` (tickets), `TICKET_BANNER_URL` + `REPOST_GIF` (CDN do Discord expira — trocar por env, nunca hardcodar).

## Estrutura

- `cogs/`: `auto_response.py` (resposta `w`, repost gif), `status.py` (rotativo), `jogos.py` (ptp), `niveis.py` (XP/rank), `tickets.py` (thread privada).
- `database.py` = XP/níveis/placar. `data/` é runtime local — nunca commitar.

## Deploy ShardCloud

- Raiz com `main.py` + `requirements.txt` + `.shardcloud` com `MAIN=main.py` minúsculo (Linux case-sensitive).
- HTTP porta 80, mínimo 512MB. Nunca zipar `.env`, `data/`, `__pycache__/`, `*.pyc`, `venv/`. DB em `/app/data/alt.db`, sem backup automático nos planos básicos.
