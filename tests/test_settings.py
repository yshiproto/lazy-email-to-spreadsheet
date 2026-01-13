"""Tests for application settings loading from environment variables."""

from pathlib import Path
from typing import TYPE_CHECKING

from config.settings import Settings

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.fixtures import FixtureRequest
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture


def test_settings_from_env(monkeypatch: "MonkeyPatch") -> None:
    """Ensure settings load values from environment variables."""
    monkeypatch.setenv("SPREADSHEET_ID", "sheet_123")
    monkeypatch.setenv("SHEET_NAME", "Jobs")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("GMAIL_REQUESTS_PER_SECOND", "25")
    monkeypatch.setenv("SHEETS_WRITES_PER_MINUTE", "45")
    monkeypatch.setenv("SHEETS_BATCH_SIZE", "20")
    monkeypatch.setenv("STATE_FILE_PATH", "custom_state.json")
    monkeypatch.setenv("CREDENTIALS_PATH", "custom_credentials.json")
    monkeypatch.setenv("TOKEN_PATH", "custom_token.json")

    settings = Settings.from_env()

    assert settings.spreadsheet_id == "sheet_123"
    assert settings.sheet_name == "Jobs"
    assert settings.ollama_model == "qwen2.5:3b"
    assert settings.ollama_host == "http://localhost:11434"
    assert settings.gmail_requests_per_second == 25
    assert settings.sheets_writes_per_minute == 45
    assert settings.sheets_batch_size == 20
    assert settings.state_file_path == Path("custom_state.json")
    assert settings.credentials_path == Path("custom_credentials.json")
    assert settings.token_path == Path("custom_token.json")


def test_settings_defaults_when_env_missing(monkeypatch: "MonkeyPatch") -> None:
    """Ensure defaults are applied when environment variables are absent."""
    for key in [
        "SPREADSHEET_ID",
        "SHEET_NAME",
        "OLLAMA_MODEL",
        "OLLAMA_HOST",
        "GMAIL_REQUESTS_PER_SECOND",
        "SHEETS_WRITES_PER_MINUTE",
        "SHEETS_BATCH_SIZE",
        "STATE_FILE_PATH",
        "CREDENTIALS_PATH",
        "TOKEN_PATH",
    ]:
        monkeypatch.delenv(key, raising=False)

    settings = Settings.from_env()

    assert settings.spreadsheet_id == ""
    assert settings.sheet_name == "Sheet1"
    assert settings.ollama_model == "qwen2.5:3b"
    assert settings.ollama_host == "http://localhost:11434"
    assert settings.gmail_requests_per_second == 40
    assert settings.sheets_writes_per_minute == 50
    assert settings.sheets_batch_size == 50
    assert settings.state_file_path == Path("processing_state.json")
    assert settings.credentials_path == Path("credentials.json")
    assert settings.token_path == Path("token.json")
