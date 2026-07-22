from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import discord
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from bot.client import NaviBot
from config import Settings
from database.connection import AsyncSessionLocal
from database.models import DashboardSession, GuildConfig

DISCORD_API = "https://discord.com/api/v10"
DISCORD_AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
SESSION_COOKIE = "navi_session"
ADMINISTRATOR = 1 << 3
MANAGE_GUILD = 1 << 5

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _csrf_token(settings: Settings, raw_session_token: str) -> str:
    return hmac.new(
        settings.session_secret.get_secret_value().encode("utf-8"),
        raw_session_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _avatar_url(user: dict[str, Any]) -> str | None:
    avatar = user.get("avatar")
    if not avatar:
        return None
    extension = "gif" if str(avatar).startswith("a_") else "png"
    return (
        f"https://cdn.discordapp.com/avatars/{user['id']}/{avatar}.{extension}?size=128"
    )


def _manageable_guilds(guilds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for guild in guilds:
        permissions = int(guild.get("permissions", "0"))
        if guild.get("owner") or permissions & (ADMINISTRATOR | MANAGE_GUILD):
            result.append(
                {
                    "id": str(guild["id"]),
                    "name": guild.get("name", "Unnamed guild"),
                    "icon": guild.get("icon"),
                    "owner": bool(guild.get("owner")),
                    "permissions": str(permissions),
                }
            )
    return result


@dataclass(slots=True)
class AuthenticatedSession:
    record: DashboardSession
    raw_token: str


class GuildConfigInput(BaseModel):
    prefix: str = Field(default="!", min_length=1, max_length=5)

    economy_enabled: bool = False
    levels_enabled: bool = False
    welcomes_enabled: bool = False
    automessages_enabled: bool = False
    fun_enabled: bool = False
    ai_chat_enabled: bool = False
    animals_enabled: bool = False
    games_enabled: bool = False
    social_enabled: bool = False
    roleplay_enabled: bool = False
    images_enabled: bool = False
    tags_enabled: bool = False
    moderation_enabled: bool = False
    reminders_enabled: bool = False

    currency_name: str = Field(default="credits", min_length=1, max_length=32)
    daily_amount: int = Field(default=100, ge=0, le=10_000_000)
    work_min_amount: int = Field(default=20, ge=0, le=10_000_000)
    work_max_amount: int = Field(default=80, ge=0, le=10_000_000)

    xp_min: int = Field(default=10, ge=1, le=10_000)
    xp_max: int = Field(default=20, ge=1, le=10_000)
    xp_cooldown_seconds: int = Field(default=60, ge=5, le=86_400)
    voice_xp_per_minute: int = Field(default=5, ge=0, le=10_000)

    welcome_channel_id: int | None = None
    goodbye_channel_id: int | None = None
    welcome_message: str = Field(max_length=2_000)
    goodbye_message: str = Field(max_length=2_000)

    confession_channel_id: int | None = None
    confessions_enabled: bool = False
    anonymous_confessions: bool = True
    social_cooldown_seconds: int = Field(default=8, ge=1, le=300)
    social_gifs_enabled: bool = True
    modlog_channel_id: int | None = None

    ai_channel_id: int | None = None
    ai_model: str | None = Field(default=None, max_length=100)
    ai_system_prompt: str = Field(max_length=4_000)

    @model_validator(mode="after")
    def validate_ranges(self) -> "GuildConfigInput":
        if self.work_max_amount < self.work_min_amount:
            raise ValueError("work_max_amount must be greater than or equal to work_min_amount")
        if self.xp_max < self.xp_min:
            raise ValueError("xp_max must be greater than or equal to xp_min")
        return self


def _parse_optional_snowflake(value: Any) -> int | None:
    if value in (None, "", "0"):
        return None
    parsed = int(str(value))
    if parsed <= 0:
        raise ValueError("Invalid Discord snowflake")
    return parsed


def _form_bool(form: Any, key: str) -> bool:
    return str(form.get(key, "")).lower() in {"1", "true", "on", "yes"}


async def _load_session(request: Request, db: AsyncSession) -> AuthenticatedSession | None:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        return None

    record = await db.get(DashboardSession, _token_hash(raw_token))
    if record is None:
        return None

    if _as_utc(record.expires_at) <= _utcnow():
        await db.delete(record)
        await db.commit()
        return None

    return AuthenticatedSession(record=record, raw_token=raw_token)


def _guild_from_session(session: DashboardSession, guild_id: int) -> dict[str, Any] | None:
    for guild in session.manageable_guilds:
        if int(guild["id"]) == guild_id:
            return guild
    return None


async def _current_discord_authorisation(
    bot: NaviBot, user_id: int, guild_id: int
) -> tuple[discord.Guild, discord.Member] | None:
    guild = bot.get_guild(guild_id)
    if guild is None:
        return None

    member = guild.get_member(user_id)
    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    allowed = (
        guild.owner_id == user_id
        or member.guild_permissions.administrator
        or member.guild_permissions.manage_guild
    )
    return (guild, member) if allowed else None


def create_app(settings: Settings, bot: NaviBot) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.http = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            headers={"User-Agent": "NAVI-Dashboard/1.0"},
        )
        yield
        await app.state.http.aclose()

    app = FastAPI(title="N.A.V.I Dashboard", version="1.0.0", lifespan=lifespan)
    app.state.bot = bot
    app.state.settings = settings

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret.get_secret_value(),
        session_cookie="navi_oauth",
        max_age=600,
        same_site="lax",
        https_only=settings.cookie_secure,
    )
    if settings.allowed_host_list != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_host_list)

    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.path.startswith(("/dashboard", "/guilds", "/callback")):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse(
            {
                "status": "online",
                "bot_ready": bot.is_ready(),
                "guilds": len(bot.guilds),
            }
        )

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        async with AsyncSessionLocal() as db:
            auth = await _load_session(request, db)
        if auth:
            return RedirectResponse("/dashboard", status_code=303)
        return TEMPLATES.TemplateResponse(
            request=request,
            name="index.html",
            context={"title": "N.A.V.I // Access"},
        )

    @app.get("/login")
    async def login(request: Request):
        state = secrets.token_urlsafe(32)
        request.session["oauth_state"] = state
        query = urlencode(
            {
                "response_type": "code",
                "client_id": settings.discord_client_id,
                "scope": "identify guilds",
                "state": state,
                "redirect_uri": settings.discord_redirect_uri,
                "prompt": "consent",
            }
        )
        return RedirectResponse(f"{DISCORD_AUTHORIZE_URL}?{query}", status_code=302)

    @app.get("/callback")
    async def callback(request: Request, code: str | None = None, state: str | None = None):
        expected_state = request.session.pop("oauth_state", None)
        if not code or not state or not expected_state or not hmac.compare_digest(state, expected_state):
            return TEMPLATES.TemplateResponse(
                request=request,
                name="index.html",
                context={"title": "N.A.V.I // Access denied", "error": "OAuth state inválido."},
                status_code=400,
            )

        client: httpx.AsyncClient = request.app.state.http
        token_response = await client.post(
            DISCORD_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.discord_redirect_uri,
            },
            auth=httpx.BasicAuth(
                settings.discord_client_id,
                settings.discord_client_secret.get_secret_value(),
            ),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_response.is_error:
            return TEMPLATES.TemplateResponse(
                request=request,
                name="index.html",
                context={"title": "N.A.V.I // OAuth error", "error": "Discord rechazó el intercambio OAuth2."},
                status_code=502,
            )

        token_data = token_response.json()
        access_token = token_data["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        user_response, guilds_response = await asyncio.gather(
            client.get(f"{DISCORD_API}/users/@me", headers=headers),
            client.get(f"{DISCORD_API}/users/@me/guilds", headers=headers),
        )
        user_response.raise_for_status()
        guilds_response.raise_for_status()

        user = user_response.json()
        guilds = _manageable_guilds(guilds_response.json())
        raw_session_token = secrets.token_urlsafe(48)
        expires_at = _utcnow() + timedelta(hours=settings.session_ttl_hours)

        async with AsyncSessionLocal() as db:
            db.add(
                DashboardSession(
                    token_hash=_token_hash(raw_session_token),
                    user_id=int(user["id"]),
                    username=user.get("global_name") or user.get("username") or "Discord user",
                    avatar_url=_avatar_url(user),
                    manageable_guilds=guilds,
                    expires_at=expires_at,
                )
            )
            await db.commit()

        response = RedirectResponse("/dashboard", status_code=303)
        response.set_cookie(
            SESSION_COOKIE,
            raw_session_token,
            max_age=settings.session_ttl_hours * 3600,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            path="/",
        )
        return response

    @app.get("/logout")
    async def logout(request: Request):
        raw_token = request.cookies.get(SESSION_COOKIE)
        if raw_token:
            async with AsyncSessionLocal() as db:
                record = await db.get(DashboardSession, _token_hash(raw_token))
                if record:
                    await db.delete(record)
                    await db.commit()
        request.session.clear()
        response = RedirectResponse("/", status_code=303)
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request):
        async with AsyncSessionLocal() as db:
            auth = await _load_session(request, db)
            if auth is None:
                return RedirectResponse("/", status_code=303)

            guild_ids = [int(item["id"]) for item in auth.record.manageable_guilds]
            configured: set[int] = set()
            if guild_ids:
                result = await db.execute(
                    select(GuildConfig.guild_id).where(GuildConfig.guild_id.in_(guild_ids))
                )
                configured = set(result.scalars().all())

        guilds: list[dict[str, Any]] = []
        for item in auth.record.manageable_guilds:
            guild_id = int(item["id"])
            guilds.append(
                {
                    **item,
                    "bot_present": bot.get_guild(guild_id) is not None,
                    "configured": guild_id in configured,
                }
            )

        return TEMPLATES.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={"session": auth.record, "guilds": guilds},
        )

    @app.get("/guilds/{guild_id}", response_class=HTMLResponse)
    async def guild_config(request: Request, guild_id: int):
        async with AsyncSessionLocal() as db:
            auth = await _load_session(request, db)
            if auth is None:
                return RedirectResponse("/", status_code=303)
            if _guild_from_session(auth.record, guild_id) is None:
                return HTMLResponse("Forbidden", status_code=403)

            current = await _current_discord_authorisation(bot, auth.record.user_id, guild_id)
            if current is None:
                return HTMLResponse(
                    "N.A.V.I no está en el servidor o ya no tienes permisos de gestión.",
                    status_code=403,
                )
            discord_guild, _member = current

            config = await db.get(GuildConfig, guild_id)
            if config is None:
                config = GuildConfig(guild_id=guild_id, guild_name=discord_guild.name)
                db.add(config)
                await db.commit()

        channels = sorted(
            [channel for channel in discord_guild.text_channels], key=lambda item: item.position
        )
        return TEMPLATES.TemplateResponse(
            request=request,
            name="guild_config.html",
            context={
                "session": auth.record,
                "guild": discord_guild,
                "channels": channels,
                "config": config,
                "csrf_token": _csrf_token(settings, auth.raw_token),
                "saved": request.query_params.get("saved") == "1",
            },
        )

    @app.post("/guilds/{guild_id}")
    async def update_guild_config(request: Request, guild_id: int):
        form = await request.form()
        async with AsyncSessionLocal() as db:
            auth = await _load_session(request, db)
            if auth is None:
                return RedirectResponse("/", status_code=303)
            if _guild_from_session(auth.record, guild_id) is None:
                return HTMLResponse("Forbidden", status_code=403)

            supplied_csrf = str(form.get("csrf_token", ""))
            expected_csrf = _csrf_token(settings, auth.raw_token)
            if not hmac.compare_digest(supplied_csrf, expected_csrf):
                return HTMLResponse("Invalid CSRF token", status_code=403)

            current = await _current_discord_authorisation(bot, auth.record.user_id, guild_id)
            if current is None:
                return HTMLResponse("Forbidden", status_code=403)
            discord_guild, _member = current

            try:
                payload = GuildConfigInput(
                    prefix=str(form.get("prefix", "!")),
                    economy_enabled=_form_bool(form, "economy_enabled"),
                    levels_enabled=_form_bool(form, "levels_enabled"),
                    welcomes_enabled=_form_bool(form, "welcomes_enabled"),
                    automessages_enabled=_form_bool(form, "automessages_enabled"),
                    fun_enabled=_form_bool(form, "fun_enabled"),
                    ai_chat_enabled=_form_bool(form, "ai_chat_enabled"),
                    animals_enabled=_form_bool(form, "animals_enabled"),
                    games_enabled=_form_bool(form, "games_enabled"),
                    social_enabled=_form_bool(form, "social_enabled"),
                    roleplay_enabled=_form_bool(form, "roleplay_enabled"),
                    images_enabled=_form_bool(form, "images_enabled"),
                    tags_enabled=_form_bool(form, "tags_enabled"),
                    moderation_enabled=_form_bool(form, "moderation_enabled"),
                    reminders_enabled=_form_bool(form, "reminders_enabled"),
                    currency_name=str(form.get("currency_name", "credits")),
                    daily_amount=int(form.get("daily_amount", 100)),
                    work_min_amount=int(form.get("work_min_amount", 20)),
                    work_max_amount=int(form.get("work_max_amount", 80)),
                    xp_min=int(form.get("xp_min", 10)),
                    xp_max=int(form.get("xp_max", 20)),
                    xp_cooldown_seconds=int(form.get("xp_cooldown_seconds", 60)),
                    voice_xp_per_minute=int(form.get("voice_xp_per_minute", 5)),
                    welcome_channel_id=_parse_optional_snowflake(form.get("welcome_channel_id")),
                    goodbye_channel_id=_parse_optional_snowflake(form.get("goodbye_channel_id")),
                    welcome_message=str(form.get("welcome_message", "")),
                    goodbye_message=str(form.get("goodbye_message", "")),
                    confession_channel_id=_parse_optional_snowflake(form.get("confession_channel_id")),
                    confessions_enabled=_form_bool(form, "confessions_enabled"),
                    anonymous_confessions=_form_bool(form, "anonymous_confessions"),
                    social_cooldown_seconds=int(form.get("social_cooldown_seconds", 8)),
                    social_gifs_enabled=_form_bool(form, "social_gifs_enabled"),
                    modlog_channel_id=_parse_optional_snowflake(form.get("modlog_channel_id")),
                    ai_channel_id=_parse_optional_snowflake(form.get("ai_channel_id")),
                    ai_model=(str(form.get("ai_model", "")).strip() or None),
                    ai_system_prompt=str(form.get("ai_system_prompt", "")),
                )
            except (ValueError, TypeError, ValidationError) as exc:
                return PlainTextResponse(f"Invalid configuration: {exc}", status_code=422)

            config = await db.get(GuildConfig, guild_id)
            if config is None:
                config = GuildConfig(guild_id=guild_id)
                db.add(config)

            config.guild_name = discord_guild.name
            for field, value in payload.model_dump().items():
                setattr(config, field, value)
            await db.commit()

        bot.configs.invalidate(guild_id)
        return RedirectResponse(f"/guilds/{guild_id}?saved=1", status_code=303)

    return app
