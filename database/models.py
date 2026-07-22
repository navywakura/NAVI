from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class GuildConfig(Base):
    """Multi-tenant configuration. One row exists for every Discord guild."""

    __tablename__ = "guild_configs"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    guild_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prefix: Mapped[str] = mapped_column(String(5), default="!", nullable=False)

    economy_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    levels_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    welcomes_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    automessages_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fun_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ai_chat_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    animals_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    games_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    social_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    roleplay_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    images_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tags_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    moderation_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    currency_name: Mapped[str] = mapped_column(String(32), default="credits", nullable=False)
    daily_amount: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    work_min_amount: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    work_max_amount: Mapped[int] = mapped_column(Integer, default=80, nullable=False)

    xp_min: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    xp_max: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    xp_cooldown_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    voice_xp_per_minute: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    welcome_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    goodbye_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    welcome_message: Mapped[str] = mapped_column(
        Text,
        default="Bienvenido/a {user} a {server}. Operadores activos: {count}.",
        nullable=False,
    )
    goodbye_message: Mapped[str] = mapped_column(
        Text,
        default="{user} ha abandonado {server}. Operadores activos: {count}.",
        nullable=False,
    )

    confession_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    confessions_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    anonymous_confessions: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    social_cooldown_seconds: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    social_gifs_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    modlog_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    ai_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_system_prompt: Mapped[str] = mapped_column(
        Text,
        default=(
            "Eres N.A.V.I, el sistema central de administración del servidor. "
            "Responde de forma sobria, analítica, breve y profesional."
        ),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class DashboardSession(Base):
    """Server-side dashboard session. The browser only receives a random token."""

    __tablename__ = "dashboard_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    manageable_guilds: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class EconomyAccount(Base):
    __tablename__ = "economy_accounts"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    balance: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    last_daily_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_work_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (Index("ix_economy_guild_balance", "guild_id", "balance"),)


class MemberLevel(Base):
    __tablename__ = "member_levels"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    xp: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (Index("ix_levels_guild_xp", "guild_id", "xp"),)


class LevelRole(Base):
    __tablename__ = "level_roles"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    level: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("guild_id", "role_id", name="uq_level_role_guild_role"),
    )


class RoleShopItem(Base):
    __tablename__ = "role_shop_items"

    item_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    role_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AutoMessage(Base):
    __tablename__ = "auto_messages"

    message_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Tag(Base):
    __tablename__ = "tags"

    tag_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    uses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("guild_id", "name", name="uq_tag_guild_name"),
        Index("ix_tags_guild_uses", "guild_id", "uses"),
    )


class SocialBlock(Base):
    __tablename__ = "social_blocks"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    blocked_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SocialPreference(Base):
    __tablename__ = "social_preferences"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    interactions_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    letters_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    confessions_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class InteractionStat(Base):
    __tablename__ = "interaction_stats"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    target_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    action: Mapped[str] = mapped_column(String(32), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class MarriageProposal(Base):
    __tablename__ = "marriage_proposals"

    proposal_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    proposer_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    target_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_marriage_proposal_target_status", "guild_id", "target_id", "status"),)


class Marriage(Base):
    __tablename__ = "marriages"

    marriage_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    user_a_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    user_b_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    divorced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("guild_id", "user_a_id", "user_b_id", name="uq_marriage_pair"),
        Index("ix_marriages_guild_active", "guild_id", "active"),
    )


class Confession(Base):
    __tablename__ = "confessions"

    confession_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    author_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    anonymous: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Reminder(Base):
    __tablename__ = "reminders"

    reminder_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (Index("ix_reminders_due", "delivered", "due_at"),)


class AfkStatus(Base):
    __tablename__ = "afk_statuses"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    reason: Mapped[str] = mapped_column(String(500), default="AFK", nullable=False)
    since: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class WarningRecord(Base):
    __tablename__ = "warning_records"

    warning_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    moderator_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_by_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    __table_args__ = (Index("ix_warnings_guild_user_active", "guild_id", "user_id", "active"),)


class GameStat(Base):
    __tablename__ = "game_stats"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    game: Mapped[str] = mapped_column(String(32), primary_key=True)
    wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    losses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    draws: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
