from __future__ import annotations

import os
from dataclasses import dataclass


def _split_csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    """Container configuration loaded from environment variables."""

    postgres_url: str | None
    postgres_user: str | None
    postgres_password: str | None
    postgres_db: str | None
    postgres_host: str | None
    postgres_port: str | None

    jwt_secret: str
    jwt_algorithm: str
    jwt_exp_minutes: int

    cors_allow_origins: list[str]

    site_url: str

    @staticmethod
    def from_env() -> "Settings":
        # DB env vars come from the database container contract:
        # POSTGRES_URL, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_PORT
        #
        # Optional (but common) additions:
        # POSTGRES_HOST (and compatibility aliases DB_HOST).
        #
        # CORS env var compatibility:
        # - preferred: CORS_ALLOW_ORIGINS (comma-separated) or "*" for dev
        # - compatibility: ALLOWED_ORIGINS (already used by some deployments)
        cors_raw = os.getenv("CORS_ALLOW_ORIGINS")
        if cors_raw is None:
            cors_raw = os.getenv("ALLOWED_ORIGINS", "*")

        jwt_secret = os.getenv("JWT_SECRET")
        if not jwt_secret:
            # IMPORTANT: Must be set by orchestrator in .env; do not hardcode secrets.
            jwt_secret = "CHANGE_ME_IN_ENV"

        return Settings(
            postgres_url=os.getenv("POSTGRES_URL"),
            postgres_user=os.getenv("POSTGRES_USER"),
            postgres_password=os.getenv("POSTGRES_PASSWORD"),
            postgres_db=os.getenv("POSTGRES_DB"),
            postgres_host=os.getenv("POSTGRES_HOST") or os.getenv("DB_HOST"),
            postgres_port=os.getenv("POSTGRES_PORT") or os.getenv("DB_PORT"),
            jwt_secret=jwt_secret,
            jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
            jwt_exp_minutes=int(os.getenv("JWT_EXP_MINUTES", "10080")),  # 7 days
            cors_allow_origins=_split_csv(cors_raw) if cors_raw != "*" else ["*"],
            site_url=os.getenv("SITE_URL", "http://localhost:3000"),
        )


settings = Settings.from_env()
