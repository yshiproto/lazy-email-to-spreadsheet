"""Pytest configuration and shared fixtures.

This module provides common fixtures used across all test modules.
"""

from datetime import datetime
from typing import TYPE_CHECKING

import pytest

from lazy_email.models.email import ApplicationStatus, EmailMessage, JobApplication

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture


@pytest.fixture
def sample_email_message() -> EmailMessage:
    """Create a sample EmailMessage for testing.

    Returns:
        An EmailMessage instance with test data.
    """
    return EmailMessage(
        message_id="abc123def456",
        content="Thank you for applying to the Software Engineer position at Acme Corp. We have received your application and will review it shortly.",
        date_sent=datetime(2026, 1, 10, 14, 30, 0),
        email_link="https://mail.google.com/mail/u/0/#inbox/abc123def456",
        sender="careers@acmecorp.com",
    )


@pytest.fixture
def sample_job_application() -> JobApplication:
    """Create a sample JobApplication for testing.

    Returns:
        A JobApplication instance with test data.
    """
    return JobApplication(
        company_name="Acme Corp",
        role="Software Engineer",
        status=ApplicationStatus.SUBMITTED,
        date_submitted="2026-01-10",
        email_link="https://mail.google.com/mail/u/0/#inbox/abc123def456",
    )


@pytest.fixture
def mock_env_vars(monkeypatch: "MonkeyPatch") -> None:
    """Set up mock environment variables for testing.

    Args:
        monkeypatch: Pytest monkeypatch fixture for modifying environment.
    """
    monkeypatch.setenv("SPREADSHEET_ID", "test_spreadsheet_id_123")
    monkeypatch.setenv("SHEET_NAME", "TestSheet")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setenv("GMAIL_REQUESTS_PER_SECOND", "40")
    monkeypatch.setenv("SHEETS_WRITES_PER_MINUTE", "50")
    monkeypatch.setenv("SHEETS_BATCH_SIZE", "50")
