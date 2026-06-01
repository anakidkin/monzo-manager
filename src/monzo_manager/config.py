from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    monzo_initial_refresh_token: str
    monzo_client_id: str
    monzo_client_secret: str

    monzo_account_id: str
    monzo_ongoing_pot_id: str
    monzo_nz_pot_id: str
    target_buffer_cents: int = 10000
    min_salary_amount_cents: int = 490000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
