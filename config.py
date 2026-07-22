from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded exclusively from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = Field(default=8000, validation_alias="PORT")

    discord_token: SecretStr
    discord_client_id: str
    discord_client_secret: SecretStr
    discord_redirect_uri: str
    public_base_url: str | None = None
    support_url: str | None = None
    invite_url: str | None = None

    database_url: str = "sqlite+aiosqlite:///./navi.db"
    session_secret: SecretStr
    session_ttl_hours: int = 12
    cookie_secure: bool = True
    allowed_hosts: str = "*"

    sync_commands: bool = False
    config_cache_ttl_seconds: int = 30

    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.5"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def allowed_host_list(self) -> list[str]:
        values = [item.strip() for item in self.allowed_hosts.split(",") if item.strip()]
        return values or ["*"]

    @property
    def dashboard_url(self) -> str:
        if self.public_base_url:
            return self.public_base_url.rstrip("/") + "/dashboard"
        parsed = urlsplit(self.discord_redirect_uri)
        base = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        return base.rstrip("/") + "/dashboard"

    @property
    def effective_invite_url(self) -> str:
        if self.invite_url:
            return self.invite_url
        return (
            "https://discord.com/oauth2/authorize"
            f"?client_id={self.discord_client_id}&scope=bot%20applications.commands"
            "&permissions=274878221376"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
