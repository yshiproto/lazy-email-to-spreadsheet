"""Tests for Pydantic models."""

from datetime import datetime
from typing import TYPE_CHECKING

import pytest

from lazy_email.models.email import (
    ApplicationStatus,
    EmailMessage,
    JobApplication,
    LLMExtractionResult,
)

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.fixtures import FixtureRequest
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture


class TestApplicationStatus:
    """Tests for ApplicationStatus enum."""

    def test_status_values_match_spreadsheet_dropdowns(self) -> None:
        """Verify status values exactly match the Google Sheet dropdown options."""
        assert ApplicationStatus.SUBMITTED.value == "Submitted Application - Pending Response"
        assert ApplicationStatus.REJECTED.value == "Rejected"
        assert ApplicationStatus.INTERVIEW.value == "Interview"
        assert ApplicationStatus.OA_INVITE.value == "OA Invite"
        assert ApplicationStatus.NA.value == "N/A"

    def test_status_is_string_enum(self) -> None:
        """Verify ApplicationStatus is a string enum for JSON serialization."""
        assert isinstance(ApplicationStatus.SUBMITTED.value, str)
        assert ApplicationStatus.SUBMITTED.value == "Submitted Application - Pending Response"


class TestEmailMessage:
    """Tests for EmailMessage model."""

    def test_email_message_creation(self) -> None:
        """Test creating an EmailMessage with all required fields."""
        email = EmailMessage(
            message_id="test123",
            content="Thank you for your application to the Software Engineer role.",
            date_sent=datetime(2026, 1, 13, 10, 0, 0),
            email_link="https://mail.google.com/mail/u/0/#inbox/test123",
            sender="test@example.com",
        )
        assert email.message_id == "test123"
        assert email.content == "Thank you for your application to the Software Engineer role."
        assert email.sender == "test@example.com"

    def test_email_message_default_sender(self) -> None:
        """Test EmailMessage with default empty sender."""
        email = EmailMessage(
            message_id="test123",
            content="Email body content here.",
            date_sent=datetime(2026, 1, 13, 10, 0, 0),
            email_link="https://mail.google.com/mail/u/0/#inbox/test123",
        )
        assert email.sender == ""


class TestJobApplication:
    """Tests for JobApplication model."""

    def test_job_application_creation(self) -> None:
        """Test creating a JobApplication with all fields."""
        app = JobApplication(
            company_name="Test Company",
            role="Software Engineer",
            status=ApplicationStatus.SUBMITTED,
            date_submitted="2026-01-13",
            email_link="https://mail.google.com/mail/u/0/#inbox/test123",
        )
        assert app.company_name == "Test Company"
        assert app.role == "Software Engineer"
        assert app.status == ApplicationStatus.SUBMITTED

    def test_job_application_default_status(self) -> None:
        """Test JobApplication defaults to N/A status."""
        app = JobApplication(
            company_name="Test Company",
            role="Software Engineer",
            date_submitted="2026-01-13",
            email_link="https://mail.google.com/mail/u/0/#inbox/test123",
        )
        assert app.status == ApplicationStatus.NA


class TestLLMExtractionResult:
    """Tests for LLMExtractionResult model."""

    def test_extraction_result_defaults(self) -> None:
        """Test LLMExtractionResult has sensible defaults."""
        result = LLMExtractionResult()
        assert result.company_name == "Unknown"
        assert result.role == "Unknown"
        assert result.status_raw == "N/A"

    def test_extraction_result_with_values(self) -> None:
        """Test LLMExtractionResult with provided values."""
        result = LLMExtractionResult(
            company_name="Acme Corp",
            role="Data Scientist",
            status_raw="interview",
        )
        assert result.company_name == "Acme Corp"
        assert result.role == "Data Scientist"
        assert result.status_raw == "interview"
