"""Application configuration managed by Pydantic Settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = Field(
        default="sqlite:///./geomeasure.db",
        description="SQLAlchemy database connection URL",
    )

    # Storage
    UPLOAD_DIR: Path = Field(
        default=Path("./uploads"),
        description="Base directory for temporary file processing and uploads",
    )

    # Limits & Security Defenses
    MAX_UPLOAD_MB: int = Field(
        default=50,
        description="Maximum permitted upload size in megabytes",
    )
    MAX_UNCOMPRESSED_MB: int = Field(
        default=250,
        description="Maximum uncompressed size permitted during ZIP extraction",
    )
    MAX_ZIP_ENTRIES: int = Field(
        default=250,
        description="Maximum number of files allowed inside an uploaded archive",
    )
    MAX_COMPRESSION_RATIO: float = Field(
        default=50.0,
        description="Maximum compression ratio threshold to prevent zip-bomb attacks",
    )

    # Measurement Precision & Validation
    GEODESIC_TOLERANCE_PCT: float = Field(
        default=0.5,
        description="Percentage tolerance between projected and geodesic measurements",
    )

    # Pagination Limits
    DEFAULT_PAGE_SIZE: int = Field(default=100, ge=1, le=1000)
    MAX_PAGE_SIZE: int = Field(default=1000, ge=1, le=5000)

    # Server & Logging
    LOG_LEVEL: str = Field(default="INFO")
    ENVIRONMENT: str = Field(default="development")
    CORS_ORIGINS: list[str] = Field(default=["*"])
    ENABLE_ASYNC_MODE: bool = Field(default=True)

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Parse comma-delimited strings into a list of allowed origins."""
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    @property
    def max_upload_bytes(self) -> int:
        """Maximum upload size in bytes."""
        return self.MAX_UPLOAD_MB * 1024 * 1024

    @property
    def max_uncompressed_bytes(self) -> int:
        """Maximum extraction size in bytes."""
        return self.MAX_UNCOMPRESSED_MB * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Singleton getter for application settings."""
    settings = Settings()
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return settings
