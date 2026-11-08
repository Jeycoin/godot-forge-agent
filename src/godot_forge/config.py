from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GODOT_FORGE_",
        env_file=".env",
        extra="ignore",
    )

    model_provider: Literal["demo", "openai", "deepseek"] = "demo"
    model_name: str = "gpt-4o-mini"
    api_key: SecretStr | None = None
    base_url: str = "https://api.openai.com/v1"
    structured_output_method: Literal["function_calling", "json_mode", "json_schema"] = (
        "json_schema"
    )
    model_max_tokens: int = Field(default=8192, ge=1024, le=16384)
    model_timeout_seconds: int = Field(default=60, ge=1, le=180)
    engine_timeout_seconds: int = Field(default=20, ge=1, le=120)
    max_repairs: int = Field(default=2, ge=0, le=5)
    retrieval_top_k: int = Field(default=3, ge=1, le=8)
    workspace_path: Path = PROJECT_ROOT / "generated" / "game"
    database_path: Path = PROJECT_ROOT / "var" / "godot_forge.db"
    knowledge_path: Path = PROJECT_ROOT / "data" / "godot_docs.json"
    godot_path: Path | None = None
    langsmith_tracing: bool = False

    @model_validator(mode="after")
    def apply_provider_defaults(self) -> "Settings":
        if self.model_provider == "deepseek":
            if self.model_name == "gpt-4o-mini":
                self.model_name = "deepseek-chat"
            if self.base_url == "https://api.openai.com/v1":
                self.base_url = "https://api.deepseek.com/v1"
            if self.structured_output_method == "json_schema":
                self.structured_output_method = "json_mode"
        return self
