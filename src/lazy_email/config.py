"""Application configuration management.

This module handles loading configuration from environment variables
with sensible defaults for all settings. Supports runtime overrides
from CLI arguments.
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All settings have sensible defaults and can be overridden via
    environment variables or a .env file.

    Attributes:
        spreadsheet_id: Google Sheets spreadsheet ID from the URL.
        sheet_name: Name of the sheet tab to write to.
        ollama_model: Ollama model name for LLM extraction.
        ollama_host: Ollama server URL.
        gmail_requests_per_second: Rate limit for Gmail API requests.
        sheets_writes_per_minute: Rate limit for Sheets API writes.
        sheets_batch_size: Number of rows to batch before writing.
        state_file_path: Path to the processing state JSON file.
        credentials_path: Path to Google OAuth credentials.json file.
        token_path: Path to store the OAuth token.json file.
    """

    # Google Sheets Configuration
    spreadsheet_id: str = Field(
        default="",
        description="Google Sheets spreadsheet ID",
    )
    sheet_name: str = Field(
        default="Sheet1",
        description="Name of the sheet tab",
    )

    # Ollama Configuration
    ollama_model: str = Field(
        default="qwen2.5:3b",
        description="Ollama model for extraction",
    )
    ollama_host: str = Field(
        default="http://localhost:11434",
        description="Ollama server URL",
    )

    # Rate Limiting Configuration
    gmail_requests_per_second: int = Field(
        default=40,
        description="Max Gmail API requests per second",
    )
    sheets_writes_per_minute: int = Field(
        default=50,
        description="Max Sheets API writes per minute",
    )
    sheets_batch_size: int = Field(
        default=50,
        description="Rows to batch before writing",
    )

    # State Management
    state_file_path: Path = Field(
        default=Path("processing_state.json"),
        description="Path to state file",
    )

    # OAuth Paths
    credentials_path: Path = Field(
        default=Path("credentials.json"),
        description="Path to OAuth credentials",
    )
    token_path: Path = Field(
        default=Path("token.json"),
        description="Path to OAuth token",
    )

    class Config:
        """Pydantic settings configuration."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        # Map environment variable names to field names
        env_prefix = ""

    @classmethod
    def from_env(cls) -> "Settings":
        """Create settings instance from environment variables.

        Returns:
            Settings instance with values loaded from environment.
        """
        return cls(
            spreadsheet_id=os.getenv("SPREADSHEET_ID", ""),
            sheet_name=os.getenv("SHEET_NAME", "Sheet1"),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
            ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            gmail_requests_per_second=int(os.getenv("GMAIL_REQUESTS_PER_SECOND", "40")),
            sheets_writes_per_minute=int(os.getenv("SHEETS_WRITES_PER_MINUTE", "50")),
            sheets_batch_size=int(os.getenv("SHEETS_BATCH_SIZE", "50")),
            state_file_path=Path(os.getenv("STATE_FILE_PATH", "processing_state.json")),
            credentials_path=Path(os.getenv("CREDENTIALS_PATH", "credentials.json")),
            token_path=Path(os.getenv("TOKEN_PATH", "token.json")),
        )


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance.

    Returns:
        The global Settings instance.
    """
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def update_settings(
    spreadsheet_id: Optional[str] = None,
    sheet_name: Optional[str] = None,
    ollama_model: Optional[str] = None,
) -> Settings:
    """Update global settings with CLI overrides.

    Args:
        spreadsheet_id: Override spreadsheet ID from CLI.
        sheet_name: Override sheet name from CLI.
        ollama_model: Override Ollama model from CLI.

    Returns:
        Updated Settings instance.
    """
    global _settings
    current = get_settings()

    # Create new settings with overrides
    _settings = Settings(
        spreadsheet_id=spreadsheet_id or current.spreadsheet_id,
        sheet_name=sheet_name or current.sheet_name,
        ollama_model=ollama_model or current.ollama_model,
        ollama_host=current.ollama_host,
        gmail_requests_per_second=current.gmail_requests_per_second,
        sheets_writes_per_minute=current.sheets_writes_per_minute,
        sheets_batch_size=current.sheets_batch_size,
        state_file_path=current.state_file_path,
        credentials_path=current.credentials_path,
        token_path=current.token_path,
    )
    return _settings
