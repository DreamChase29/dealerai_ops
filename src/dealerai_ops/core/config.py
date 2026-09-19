"""Environment-based application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from dealerai_ops import __version__

EnvironmentName = Literal["local", "test", "development", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="DEALERAI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "DealerAI Ops"
    app_version: str = __version__
    environment: EnvironmentName = "local"
    log_level: LogLevel = "INFO"
    database_url: str = Field(default="sqlite+pysqlite:///:memory:")
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    no_show_model_dir: str = "work/models/no_show"
    no_show_model_version: str = "local-synthetic-v1"
    llm_provider: str = "local"
    bedrock_model_id: str = "anthropic.claude-3-haiku-20240307-v1:0"
    bedrock_region: str = "us-east-1"
    agent_version: str = __version__
    prompt_version: str = "local-agent-policy-v1"
    llm_model_version: str = "local-deterministic-v1"
    agent_max_tool_iterations: int = Field(default=4, ge=0, le=12)
    agent_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    agent_max_retrieval_chunks: int = Field(default=5, ge=1, le=10)
    observability_enabled: bool = True
    mlflow_enabled: bool = False
    mlflow_tracking_uri: str = "file:work/mlruns"
    mlflow_experiment_name: str = "dealerai-ops-local"


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
