"""Agent configuration and loading."""
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
import yaml

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

AGENT_DIR = Path(__file__).parent.parent.parent / "agent"

ALLOWED_ENV_VARS = {
    # Direct Anthropic
    "ANTHROPIC_API_KEY",
    # Azure AI Foundry
    "CLAUDE_CODE_USE_FOUNDRY",
    "ANTHROPIC_FOUNDRY_BASE_URL",
    "ANTHROPIC_FOUNDRY_API_KEY",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    # Other tools
    "TAVILY_API_KEY",
}


class AgentConfig(BaseModel):
    name: str
    description: str
    image: Optional[str] = None
    command: list[str] = Field(default_factory=lambda: ["python", "/app/run_agent.py"])
    env_vars: list[str] = Field(default_factory=list)
    timeout: int = 600
    idle_timeout: int = 120


def load_agent_config() -> AgentConfig:
    config_path = AGENT_DIR / "agent.yaml"
    with open(config_path) as f:
        data = yaml.safe_load(f)
    command = data.get("command") or data.get("entrypoint") or ["python", "/app/run_agent.py"]
    return AgentConfig(
        name=data.get("name", "agent"),
        description=data.get("description", ""),
        image=data.get("image"),
        command=command,
        env_vars=data.get("env_vars", []),
        timeout=data.get("timeout", 600),
        idle_timeout=data.get("idle_timeout", 120),
    )


def get_agent_env_vars(agent_config: AgentConfig) -> dict[str, str]:
    env = {}
    for var_name in agent_config.env_vars:
        if var_name not in ALLOWED_ENV_VARS:
            logger.warning(f"Agent requested non-whitelisted env var: {var_name}")
            continue
        value = getattr(settings, var_name, None)
        if value:
            env[var_name] = value
        else:
            logger.warning(f"Agent requires {var_name} but it's not set in settings")
    return env
