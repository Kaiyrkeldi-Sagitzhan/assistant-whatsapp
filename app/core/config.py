from functools import lru_cache
from typing import Union

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="dev", alias="APP_ENV")
    app_name: str = Field(default="Task Assistant API", alias="APP_NAME")
    app_timezone: str = Field(default="Asia/Almaty", alias="APP_TIMEZONE")
    app_debug: bool = Field(default=False, alias="APP_DEBUG")

    database_url: str = Field(
        default="postgresql+psycopg://assistant:assistant@localhost:5432/assistant",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    gemini_api_key: str = Field(default="replace_me", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-1.5-flash", alias="GEMINI_MODEL")

    whatsapp_verify_token: str = Field(default="replace_me", alias="WHATSAPP_VERIFY_TOKEN")
    whatsapp_access_token: str = Field(default="replace_me", alias="WHATSAPP_ACCESS_TOKEN")
    whatsapp_phone_number_id: str = Field(default="replace_me", alias="WHATSAPP_PHONE_NUMBER_ID")
    whatsapp_graph_version: str = Field(default="v20.0", alias="WHATSAPP_GRAPH_VERSION")
    whatsapp_test_recipient: Union[str, None] = Field(default=None, alias="WHATSAPP_TEST_RECIPIENT")

    google_calendar_client_id: str = Field(default="replace_me", alias="GOOGLE_CALENDAR_CLIENT_ID")
    google_calendar_client_secret: str = Field(
        default="replace_me", alias="GOOGLE_CALENDAR_CLIENT_SECRET"
    )
    google_calendar_redirect_uri: str = Field(
        default="http://localhost:8000/oauth/google/callback",
        alias="GOOGLE_CALENDAR_REDIRECT_URI",
    )

    email_inbound_secret: str = Field(default="replace_me", alias="EMAIL_INBOUND_SECRET")


@lru_cache
def get_settings() -> Settings:
    return Settings()
