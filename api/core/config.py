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
    
    # Anthropic API key
    ANTHROPIC_API_KEY: str = ""

    # TAVILY API key
    TAVILY_API_KEY: str = ""

    # MinIO Configuration
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_SECURE: bool = False
    MINIO_BUCKET: str = "agentchat-artifacts"


settings = Settings()
