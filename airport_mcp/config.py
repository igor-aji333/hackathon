"""Runtime configuration, read from environment variables and an optional `.env` file."""

from enum import Enum
from pathlib import Path
from typing import Literal, Optional

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageBackend(str, Enum):
    LOCAL = "local"
    S3 = "s3"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    storage_backend: StorageBackend = Field(
        StorageBackend.LOCAL, validation_alias="AIRPORT_MCP_STORAGE_BACKEND"
    )
    local_data_dir: Path = Field(
        Path.home() / ".airport_mcp_data", validation_alias="AIRPORT_MCP_DATA_DIR"
    )
    s3_bucket: Optional[str] = Field(None, validation_alias="AIRPORT_MCP_S3_BUCKET")
    s3_prefix: str = Field("airport_mcp/", validation_alias="AIRPORT_MCP_S3_KEY")

    mcp_transport: Literal["stdio", "streamable-http", "sse"] = Field(
        "stdio", validation_alias="MCP_TRANSPORT"
    )
    mcp_host: str = Field("127.0.0.1", validation_alias="MCP_HOST")
    mcp_port: int = Field(8000, validation_alias="MCP_PORT")
    # Hosting platforms (Databricks Apps, Cloud Run, Heroku, ...) inject the port to serve on.
    platform_port: Optional[int] = Field(
        None, validation_alias=AliasChoices("DATABRICKS_APP_PORT", "PORT")
    )

    @model_validator(mode="after")
    def _require_bucket_for_s3(self) -> "Settings":
        if self.storage_backend is StorageBackend.S3 and not self.s3_bucket:
            raise ValueError("AIRPORT_MCP_S3_BUCKET must be set when AIRPORT_MCP_STORAGE_BACKEND=s3")
        return self
