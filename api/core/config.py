"""Application configuration"""
from enum import Enum
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Application environment"""
    LOCAL = "local"
    DEV = "dev"
    PROD = "prod"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    # API Configuration
    API_V1_STR: str = "/api/v1"
    APP_NAME: str = "AgentChat API"
    ENVIRONMENT: Environment = Environment.LOCAL
    LOG_LEVEL: str = "INFO"
    
    # Server Configuration
    PORT: int = 8080
    HOST: str = "0.0.0.0"

    # PostgreSQL Configuration
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "agentchat"
    POSTGRES_USER: str = "agentchat"
    POSTGRES_PASSWORD: str = "agentchat"
    
    # Sandbox backend: "subprocess" (default) or "modal"
    SANDBOX_BACKEND: str = "subprocess"

    # Modal Configuration (for sandbox execution)
    MODAL_TOKEN_ID: str = ""
    MODAL_TOKEN_SECRET: str = ""

    # Anthropic Configuration
    # Option A – Direct Anthropic API: set ANTHROPIC_API_KEY.
    # Option B – Azure AI Foundry: set CLAUDE_CODE_USE_FOUNDRY=1, ANTHROPIC_FOUNDRY_BASE_URL,
    #            ANTHROPIC_FOUNDRY_API_KEY, and optionally the model name overrides.
    ANTHROPIC_API_KEY: str = ""

    # Azure AI Foundry
    CLAUDE_CODE_USE_FOUNDRY: str = ""
    ANTHROPIC_FOUNDRY_BASE_URL: str = ""  # e.g. https://<resource>.services.ai.azure.com/anthropic
    ANTHROPIC_FOUNDRY_API_KEY: str = ""
    ANTHROPIC_DEFAULT_HAIKU_MODEL: str = ""
    ANTHROPIC_DEFAULT_SONNET_MODEL: str = ""
    ANTHROPIC_DEFAULT_OPUS_MODEL: str = ""

    # TAVILY API key
    TAVILY_API_KEY: str = ""

    # MinIO Configuration
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_SECURE: bool = False
    MINIO_BUCKET: str = "agentchat-artifacts"


settings = Settings()
