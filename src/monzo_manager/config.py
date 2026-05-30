from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    monzo_access_token: str
    monzo_account_id: str
    monzo_savings_pot_id: str
    target_buffer_cents: int = 10000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
