# N.A.V.I — Discord Bot Multi-Tenant

N.A.V.I (Network Automated Virtual Intelligence) is a multi-server Discord bot written in Python 3.11+ with `discord.py`, FastAPI, async SQLAlchemy and Discord OAuth2.

The bot and dashboard run in one asynchronous process. Every server receives an isolated `GuildConfig` row and isolated data for economy, levels, tags, social controls, moderation records, reminders and games.

## Current status — v1.1 Command Core

- Hybrid commands: slash commands and the configured text prefix share the same implementation.
- Dynamic prefix per server, configurable from the dashboard. Default: `!`.
- `/help`, `!help`, `/ping`, `/dashboard`.
- Animals, fun media, games, social interactions, roleplay, marriage, reminders and AFK.
- Moderation and mod-log.
- Information and utility commands.
- Pillow image editing without generative AI.
- Local server tags with variables and ownership.
- Existing economy, XP, welcomes and scheduled messages.
- Dashboard module switches and social/moderation configuration.

The complete command index is in [`COMMANDS.md`](COMMANDS.md).

## Prefix command fix

`NaviBot` resolves the prefix from the current guild configuration and all command modules use `discord.py` hybrid commands where Discord supports that hierarchy. Therefore both forms are valid:

```text
/work
!work

/tag show rules
!tag show rules
```

Unknown prefix commands are handled by N.A.V.I and no longer produce an unhandled `CommandNotFound` traceback.

## Local installation

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python main.py
```

On Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python main.py
```

## Discord application configuration

1. Create an application and bot in the Discord Developer Portal.
2. Enable **Server Members Intent** and **Message Content Intent**.
3. Register `http://localhost:8000/callback` as an OAuth2 redirect during local development.
4. Invite the bot with `bot` and `applications.commands` scopes.
5. Give it only the permissions needed by enabled modules.
6. Set `SYNC_COMMANDS=true` for the first controlled startup after command changes.
7. Once the log confirms synchronization, return `SYNC_COMMANDS=false`.

## Environment variables

The minimum local configuration is:

```env
ENVIRONMENT=development
COOKIE_SECURE=false
ALLOWED_HOSTS=localhost,127.0.0.1
SYNC_COMMANDS=true

DISCORD_TOKEN=replace_me
DISCORD_CLIENT_ID=replace_me
DISCORD_CLIENT_SECRET=replace_me
DISCORD_REDIRECT_URI=http://localhost:8000/callback
SESSION_SECRET=replace_with_a_long_random_value

DATABASE_URL=sqlite+aiosqlite:///./navi.db
PUBLIC_BASE_URL=http://localhost:8000
```

Generate the session secret with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Do not commit `.env`, bot tokens, OAuth secrets or database credentials.

## Database

SQLite is supported for local development. PostgreSQL is the intended deployment database.

On startup:

- `Base.metadata.create_all()` creates missing tables.
- A compatibility routine adds the new v1.1 `GuildConfig` fields to databases created by the original MVP.

This compatibility routine is intentionally limited. Add Alembic before making incompatible production migrations.

## Dashboard configuration added in v1.1

The existing configuration page now exposes switches for:

- Animals
- Games
- Social
- Roleplay
- Images
- Tags
- Moderation
- Reminders

It also includes confession settings, social GIF controls, social cooldown, confession channel and mod-log channel. The visual dashboard redesign and public landing are intentionally outside this release.

## Tests

```bash
pip install -r requirements-dev.txt
python -m compileall -q .
pytest -q
```

GitHub Actions runs the same checks on pushes and pull requests.

## Deployment note

The included `render.yaml` belongs to the earlier Render deployment plan. Review its service/database plans before using it. N.A.V.I should run as a single bot process until distributed locks and leader election are implemented; multiple replicas would duplicate gateway sessions and scheduled jobs.
