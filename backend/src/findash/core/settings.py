from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_INVESTMENTS_DATABASE_URL = "sqlite:///.data/investments.db"


class Settings(BaseSettings):
    """Application settings, read from ``FINDASH_*`` environment variables."""

    model_config = SettingsConfigDict(env_prefix="FINDASH_")

    investments_database_url: str = DEFAULT_INVESTMENTS_DATABASE_URL


def get_settings() -> Settings:
    return Settings()
