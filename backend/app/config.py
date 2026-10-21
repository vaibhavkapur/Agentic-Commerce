from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime configuration. Every value can be overridden through environment variables."""

    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    app_name: str = "Accounts Payable Exception Agent"
    environment: str = "development"

    # Persistence. SQLite is the zero-configuration default; point this at Supabase PostgreSQL
    # (postgresql+psycopg://...) for a hosted deployment. Schema is created by SQLAlchemy metadata
    # in development; the equivalent PostgreSQL DDL is in supabase/migrations (see scripts/export_schema.py).
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'ap.db'}"

    # Documents. "local" writes private files under storage_dir; "supabase" uses Supabase Storage.
    storage_backend: str = "local"
    storage_dir: Path = BASE_DIR / "data" / "storage"
    storage_signed_url_ttl_seconds: int = 300
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    supabase_storage_bucket: str = "case-documents"

    # Authentication. Supabase Auth issues HS256 JWTs signed with the project JWT secret and
    # audience "authenticated"; the same verifier is used for locally issued development tokens.
    auth_jwt_secret: str = "development-only-secret-change-me-before-deploying"
    auth_jwt_audience: str = "authenticated"
    auth_token_ttl_seconds: int = 8 * 3600
    dev_login_enabled: bool = True

    # Approval policy.
    approval_policy_version: str = "ap-policy-v1"
    approval_ttl_hours: int = 72

    # Agent execution.
    agent_run_mode: str = "inline"  # "inline" runs in the API process, "worker" queues for app.worker
    langgraph_checkpoint_path: Path = BASE_DIR / "data" / "checkpoints.sqlite"
    agent_max_model_calls: int = 6
    agent_max_tool_calls: int = 30
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    agent_prompt_version: str = "ap-agent-prompt-v1"

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.langgraph_checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    if settings.database_url.startswith("sqlite:///"):
        Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(
            parents=True, exist_ok=True
        )
    return settings
