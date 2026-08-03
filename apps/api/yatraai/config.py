"""Central application settings.

Every external dependency is expressed as a *provider* string so the application
can degrade to a fully-offline mode (mock LLM, hashing embeddings, seed weather,
haversine routing, SQLite) without any code change.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
SEED_DIR = DATA_DIR / "seed"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- runtime -----------------------------------------------------------
    yatra_env: Literal["development", "test", "production"] = "development"
    yatra_log_level: str = "INFO"
    yatra_log_json: bool = False
    yatra_api_host: str = "0.0.0.0"
    yatra_api_port: int = 8000

    # ---- database ----------------------------------------------------------
    database_url: str | None = None
    sqlite_fallback_path: str = "./yatraai.sqlite3"

    # ---- auth --------------------------------------------------------------
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 120
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_jwt_secret: str | None = None

    # ---- cors --------------------------------------------------------------
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # ---- llm ---------------------------------------------------------------
    llm_provider: Literal["mock", "anthropic", "gemini"] = "mock"
    llm_model: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    llm_timeout_seconds: float = 30.0
    llm_max_output_tokens: int = 1200

    # ---- embeddings --------------------------------------------------------
    embedding_provider: Literal["hashing", "sentence-transformers"] = "hashing"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # ---- weather -----------------------------------------------------------
    weather_provider: Literal["open-meteo", "seed"] = "open-meteo"
    open_meteo_base_url: str = "https://api.open-meteo.com/v1"
    weather_cache_ttl_seconds: int = 3600

    # ---- routing -----------------------------------------------------------
    routing_provider: Literal["osrm", "haversine"] = "haversine"
    osrm_base_url: str = "https://router.project-osrm.org"
    routing_timeout_seconds: float = 8.0

    # ---- optimizer ---------------------------------------------------------
    ortools_time_limit_seconds: int = 10
    planner_random_seed: int = 20240101

    # ---- rate limiting -----------------------------------------------------
    rate_limit_ai_per_minute: int = 15
    rate_limit_default_per_minute: int = 120

    # ---- privacy -----------------------------------------------------------
    location_point_retention_minutes: int = 120
    location_session_max_hours: int = 12

    # ---- ingestion ---------------------------------------------------------
    # Suffix-matched: "gov.in" admits "asi.gov.in" and "megtourism.gov.in" alike.
    # Only official, government, academic and named institutional domains are
    # allowed to become citations.
    ingest_allowed_domains: str = (
        "gov.in,nic.in,ac.in,unesco.org,"
        "karnatakatourism.org,salarjungmuseum.in,hal-india.co.in,taralaya.org,"
        "shrikashivishwanath.org,shreejagannatha.in,bahaihouseofworship.in,"
        "openstreetmap.org,wikipedia.org,wikidata.org"
    )

    # ---- derived / helpers -------------------------------------------------
    @field_validator("cors_origins", "ingest_allowed_domains", mode="before")
    @classmethod
    def _coerce_csv(cls, v: object) -> str:
        if isinstance(v, (list, tuple)):
            return ",".join(str(x) for x in v)
        return str(v) if v is not None else ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_ingest_domains(self) -> set[str]:
        return {d.strip().lower() for d in self.ingest_allowed_domains.split(",") if d.strip()}

    @property
    def is_production(self) -> bool:
        return self.yatra_env == "production"

    def assert_production_ready(self) -> list[str]:
        """Return blocking misconfigurations. Called on startup in production."""
        problems: list[str] = []
        if not self.is_production:
            return problems
        if len(self.jwt_secret) < 32 or "dev-only" in self.jwt_secret:
            problems.append("JWT_SECRET must be a unique value of at least 32 characters.")
        if not self.database_url:
            problems.append("DATABASE_URL must be set in production (SQLite fallback refused).")
        if any(o.startswith("http://") and "localhost" not in o for o in self.cors_origin_list):
            problems.append("CORS_ORIGINS must use https:// for non-localhost origins.")
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            problems.append("LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY.")
        if self.llm_provider == "gemini" and not self.gemini_api_key:
            problems.append("LLM_PROVIDER=gemini requires GEMINI_API_KEY.")
        return problems

    @property
    def resolved_database_url(self) -> str:
        """Postgres when configured, otherwise a local SQLite file.

        SQLite keeps the demo runnable with zero infrastructure; pgvector-backed
        Postgres is used whenever DATABASE_URL is present.
        """
        if self.database_url:
            return self.database_url
        path = Path(self.sqlite_fallback_path)
        if not path.is_absolute():
            path = REPO_ROOT / path
        return f"sqlite+pysqlite:///{path.as_posix()}"

    @property
    def uses_postgres(self) -> bool:
        return self.resolved_database_url.startswith("postgres")

    @property
    def seed_dir(self) -> Path:
        return SEED_DIR

    @property
    def data_dir(self) -> Path:
        return DATA_DIR


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Used by tests that mutate the environment."""
    get_settings.cache_clear()


settings: Settings = get_settings()
