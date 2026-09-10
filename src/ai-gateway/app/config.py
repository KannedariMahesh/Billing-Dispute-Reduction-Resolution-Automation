from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Billing Dispute AI Gateway"
    environment: str = "development"
    audit_log_path: Path = Path.cwd() / "output" / "audit_log.jsonl"
    model_config = SettingsConfigDict(env_prefix="AI_GATEWAY_", env_file=".env")


settings = Settings()
