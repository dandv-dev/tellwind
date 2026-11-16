from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"), extra="ignore", protected_namespaces=("settings_",)
    )

    openai_api_key: str = ""
    database_url: str = ""
    cron_secret: str = "change-me"
    public_url: str = ""
    render_external_url: str = ""  # set by Render; used when PUBLIC_URL isn't
    # Directory with the built SPA (index.html + assets) and brief-template.html
    static_dir: Path = REPO_DIR / "frontend" / "dist"
    fixtures_dir: Path = REPO_DIR / "fixtures"
    cookie_secure: bool = False
    session_days: int = 30
    seed_demo: bool = True
    scheduler_enabled: bool = True

    # Models. Luna is cheap and is used for bulk work; Terra writes the reasoning.
    model_classify: str = "gpt-5.6-luna"
    model_narrate: str = "gpt-5.6-terra"
    model_answer: str = "gpt-5.6-terra"
    model_embed: str = "text-embedding-3-small"

    @model_validator(mode="after")
    def _public_url(self) -> "Settings":
        if not self.public_url:
            self.public_url = self.render_external_url or "http://localhost:8000"
        return self

    @property
    def db_url(self) -> str:
        url = self.database_url
        if not url:
            data = BACKEND_DIR / "data"
            data.mkdir(exist_ok=True)
            return f"sqlite+aiosqlite:///{data / 'tellwind.db'}"
        # Render gives postgres://...; SQLAlchemy async wants postgresql+asyncpg://
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url[len("postgresql://") :]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
