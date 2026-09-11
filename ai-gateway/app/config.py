from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Billing Dispute AI Gateway"
    environment: str = "development"
    # config.py is at ai-gateway/app/config.py — two levels up is the project root
    audit_log_path: Path = Path(__file__).resolve().parents[2] / "output" / "audit_log.jsonl"

    # LLM settings — set AI_GATEWAY_USE_LLM=true to enable Ollama-backed reasoning
    use_llm: bool = True
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4:latest"    # alternatives: qwen3:30b
    ollama_timeout: int = 60           # seconds per request

    model_config = SettingsConfigDict(env_prefix="AI_GATEWAY_", env_file=".env")


settings = Settings()
