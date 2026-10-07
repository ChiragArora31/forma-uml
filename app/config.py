from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"), env_prefix="FORMA_", extra="ignore", populate_by_name=True
    )
    mode: str = "sample"
    data_dir: Path = Path(".data")
    plantuml_jar: Path = Path(".tools/plantuml.jar")
    java: str = "java"
    model: str = "gpt-4.1-mini"
    api_key: str = ""
    base_url: str | None = None
    generation_timeout: float = 90
    render_timeout: float = 20
    render_concurrency: int = 3
    max_active_generations: int = 4
    cookie_secure: bool = False
    frontend_dir: Path = Path("frontend/dist")
    database_url: str | None = Field(
        default=None, validation_alias=AliasChoices("FORMA_DATABASE_URL", "DATABASE_URL")
    )
    database_url_unpooled: str | None = Field(default=None, validation_alias="DATABASE_URL_UNPOOLED")
    oidc_token: str = Field(default="", validation_alias="VERCEL_OIDC_TOKEN")
