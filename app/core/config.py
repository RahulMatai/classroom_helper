# app/core/config.py
# ════════════════════════════════════════════════
# Configuration Management
#
# WHY THIS FILE EXISTS:
# Single source of truth for all environment variables.
# Every other file imports settings from here —
# never directly from os.environ.
#
# HOW IT WORKS:
# Pydantic reads .env file automatically and validates
# every value on startup. If anything is missing
# the app refuses to start with a clear error.
#
# FOR JUNIORS:
# Never use os.getenv() anywhere else in the codebase.
# Always add new variables here first.
# ════════════════════════════════════════════════

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """
    All application settings loaded from .env file.

    Pydantic validates types automatically.
    If DATABASE_URL is missing — app won't start.
    If DEBUG is set to "true" — Pydantic converts to bool.
    No manual parsing needed anywhere.
    """

    # ── App ───────────────────────────────────────
    APP_NAME: str = "ClassroomCompanion"
    APP_ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str

    # ── Database ──────────────────────────────────
    DATABASE_URL: str

    # ── Redis ─────────────────────────────────────
    REDIS_URL: str

    # ── LLM ───────────────────────────────────────
    # We use different models per agent
    # Heavier models for complex reasoning
    # Lighter models for simple classification
    LLM_PROVIDER: str = "groq"
    GROQ_API_KEY: str

    MODEL_ROUTER: str = "llama-3.1-8b-instant"
    MODEL_SAFETY: str = "llama-3.1-8b-instant"
    MODEL_TEACHER: str = "llama-3.3-70b-versatile"
    MODEL_STUDENT: str = "llama-3.3-70b-versatile"
    MODEL_SUMMARISER: str = "mixtral-8x7b-32768"
    MODEL_REMINDER: str = "gemma2-9b-it"
    MODEL_PARENT: str = "mixtral-8x7b-32768"

    # ── Telegram ──────────────────────────────────
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_WEBHOOK_SECRET: str

    # ── Twilio ────────────────────────────────────
    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_WHATSAPP_NUMBER: str

    # ── Auth ──────────────────────────────────────
    MAGIC_LINK_TTL_MINUTES: int = 15
    JWT_ALGORITHM: str = "RS256"
    JWT_ACCESS_TTL_MINUTES: int = 60
    JWT_REFRESH_TTL_DAYS: int = 7
    JWT_PRIVATE_KEY: str = "generate_later"
    JWT_PUBLIC_KEY: str = "generate_later"

    # ── URLs ──────────────────────────────────────
    FRONTEND_URL: str = "http://localhost:8000"
    ALLOWED_ORIGINS: str = "http://localhost:8000,http://localhost:3000"

    # ── Supabase Storage ──────────────────────────
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    UPLOAD_BUCKET: str = "submissions"

    # ── Reminder Policy ───────────────────────────
    # These are defaults — Admin can override per tenant
    MAX_NUDGES_PER_DAY: int = 2
    QUIET_HOURS_START: int = 22
    QUIET_HOURS_END: int = 8
    ESCALATION_THRESHOLD: int = 3

    class Config:
        """
        Tells Pydantic where to find the .env file.
        env_file_encoding handles special characters
        in passwords and keys correctly.
        """
        env_file = ".env"
        env_file_encoding = "utf-8"

    # ── Computed Properties ───────────────────────
    @property
    def is_production(self) -> bool:
        """
        Use this instead of checking APP_ENV directly.

        Example:
            if settings.is_production:
                # enable strict security headers
        """
        return self.APP_ENV == "production"

    @property
    def allowed_origins_list(self) -> List[str]:
        """
        Returns ALLOWED_ORIGINS as a clean list.

        In .env we store as comma-separated string:
            ALLOWED_ORIGINS=http://localhost:8000,https://myapp.railway.app

        This property converts it to:
            ["http://localhost:8000", "https://myapp.railway.app"]
        """
        return [
            origin.strip()
            for origin in self.ALLOWED_ORIGINS.split(",")
        ]

    @property
    def database_url_async(self) -> str:
        """
        SQLAlchemy async driver needs postgresql+asyncpg://
        instead of postgresql://

        We store the standard format in .env and
        convert it here automatically.
        """
        return self.DATABASE_URL.replace(
            "postgresql://",
            "postgresql+asyncpg://"
        )


# ── Singleton Instance ────────────────────────────
# This is what every other file imports.
# Created once when the module loads.
# Never instantiate Settings() anywhere else.
#
# Usage in any file:
#   from app.core.config import settings
#   print(settings.APP_NAME)
settings = Settings()