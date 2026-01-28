"""Tests for LLM extraction service."""

from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

from lazy_email.llm.extractor import (
    EXTRACTION_PROMPT,
    STATUS_MAPPINGS,
    JobApplicationExtractor,
    LLMExtractorError,
    _map_status_to_enum,
    _parse_llm_response,
)
from lazy_email.models.email import ApplicationStatus, EmailMessage, LLMExtractionResult

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.fixtures import FixtureRequest
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture


@pytest.fixture
def sample_email() -> EmailMessage:
    """Create a sample email message for testing.

    Returns:
        EmailMessage with job application content.
    """
    return EmailMessage(
        message_id="test123",
        content="Thank you for applying to the Software Engineer position at Google. We have received your application and will review it shortly.",
        date_sent=datetime(2026, 1, 10, 14, 30, 0),
        email_link="https://mail.google.com/mail/u/0/#inbox/test123",
        sender="careers@google.com",
    )


@pytest.fixture
def mock_ollama_client(mocker: "MockerFixture") -> Mock:
    """Create a mock Ollama client.

    Returns:
        Mock client with chat method.
    """
    mock_client = Mock()
    mocker.patch("lazy_email.llm.extractor.ollama.Client", return_value=mock_client)
    return mock_client


class TestMapStatusToEnum:
    """Tests for _map_status_to_enum function."""

    def test_map_submitted_variations(self) -> None:
        """Test mapping submitted status variations."""
        assert _map_status_to_enum("submitted") == ApplicationStatus.SUBMITTED
        assert _map_status_to_enum("SUBMITTED") == ApplicationStatus.SUBMITTED
        assert _map_status_to_enum("application received") == ApplicationStatus.SUBMITTED
        assert _map_status_to_enum("pending") == ApplicationStatus.SUBMITTED
        assert _map_status_to_enum("under review") == ApplicationStatus.SUBMITTED

    def test_map_rejected_variations(self) -> None:
        """Test mapping rejected status variations."""
        assert _map_status_to_enum("rejected") == ApplicationStatus.REJECTED
        assert _map_status_to_enum("not selected") == ApplicationStatus.REJECTED
        assert _map_status_to_enum("unsuccessful") == ApplicationStatus.REJECTED
        assert _map_status_to_enum("position filled") == ApplicationStatus.REJECTED

    def test_map_interview_variations(self) -> None:
        """Test mapping interview status variations."""
        assert _map_status_to_enum("interview") == ApplicationStatus.INTERVIEW
        assert _map_status_to_enum("interview scheduled") == ApplicationStatus.INTERVIEW
        assert _map_status_to_enum("phone screen") == ApplicationStatus.INTERVIEW
        assert _map_status_to_enum("technical interview") == ApplicationStatus.INTERVIEW

    def test_map_oa_invite_variations(self) -> None:
        """Test mapping OA invite status variations."""
        assert _map_status_to_enum("oa") == ApplicationStatus.OA_INVITE
        assert _map_status_to_enum("oa invite") == ApplicationStatus.OA_INVITE
        assert _map_status_to_enum("online assessment") == ApplicationStatus.OA_INVITE
        assert _map_status_to_enum("coding challenge") == ApplicationStatus.OA_INVITE
        assert _map_status_to_enum("hackerrank") == ApplicationStatus.OA_INVITE

    def test_map_na_variations(self) -> None:
        """Test mapping N/A status variations."""
        assert _map_status_to_enum("n/a") == ApplicationStatus.NA
        assert _map_status_to_enum("unknown") == ApplicationStatus.NA
        assert _map_status_to_enum("unclear") == ApplicationStatus.NA

    def test_map_unknown_defaults_to_na(self) -> None:
        """Test unknown status defaults to N/A."""
        assert _map_status_to_enum("something random") == ApplicationStatus.NA
        assert _map_status_to_enum("") == ApplicationStatus.NA

    def test_map_partial_match(self) -> None:
        """Test partial matching works for status variations."""
        assert _map_status_to_enum("your application was submitted") == ApplicationStatus.SUBMITTED
        assert _map_status_to_enum("we regret to inform you rejected") == ApplicationStatus.REJECTED


class TestParseLLMResponse:
    """Tests for _parse_llm_response function."""

    def test_parse_valid_json(self) -> None:
        """Test parsing valid JSON response."""
        response = '{"company_name": "Google", "role": "Software Engineer", "status": "submitted"}'
        result = _parse_llm_response(response)

        assert isinstance(result, LLMExtractionResult)
        assert result.company_name == "Google"
        assert result.role == "Software Engineer"
        assert result.status_raw == "submitted"

    def test_parse_json_with_markdown_code_block(self) -> None:
        """Test parsing JSON wrapped in markdown code block."""
        response = '```json\n{"company_name": "Meta", "role": "Data Scientist", "status": "interview"}\n```'
        result = _parse_llm_response(response)

        assert result.company_name == "Meta"
        assert result.role == "Data Scientist"
        assert result.status_raw == "interview"

    def test_parse_json_with_whitespace(self) -> None:
        """Test parsing JSON with extra whitespace."""
        response = '  \n  {"company_name": "Amazon", "role": "SDE", "status": "oa_invite"}  \n  '
        result = _parse_llm_response(response)

        assert result.company_name == "Amazon"
        assert result.role == "SDE"
        assert result.status_raw == "oa_invite"

    def test_parse_invalid_json_returns_defaults(self) -> None:
        """Test invalid JSON returns default values."""
        response = "This is not valid JSON"
        result = _parse_llm_response(response)

        assert result.company_name == "Unknown"
        assert result.role == "Unknown"
        assert result.status_raw == "N/A"

    def test_parse_partial_json_uses_defaults(self) -> None:
        """Test partial JSON uses defaults for missing fields."""
        response = '{"company_name": "Netflix"}'
        result = _parse_llm_response(response)

        assert result.company_name == "Netflix"
        assert result.role == "Unknown"
        assert result.status_raw == "n/a"


class TestJobApplicationExtractor:
    """Tests for JobApplicationExtractor class."""

    def test_init_with_defaults(self, mocker: "MockerFixture") -> None:
        """Test extractor initializes with default settings."""
        mock_settings = Mock()
        mock_settings.ollama_model = "qwen2.5:3b"
        mock_settings.ollama_host = "http://localhost:11434"
        mocker.patch("lazy_email.llm.extractor.get_settings", return_value=mock_settings)
        mocker.patch("lazy_email.llm.extractor.ollama.Client")

        extractor = JobApplicationExtractor()

        assert extractor.model == "qwen2.5:3b"
        assert extractor.host == "http://localhost:11434"

    def test_init_with_custom_values(self, mocker: "MockerFixture") -> None:
        """Test extractor initializes with custom values."""
        mocker.patch("lazy_email.llm.extractor.ollama.Client")

        extractor = JobApplicationExtractor(
            model="llama3.2:3b",
            host="http://custom:11434",
        )

        assert extractor.model == "llama3.2:3b"
        assert extractor.host == "http://custom:11434"

    def test_extract_from_content(
        self, mock_ollama_client: Mock, mocker: "MockerFixture"
    ) -> None:
        """Test extracting data from email content."""
        # Setup mock response
        mock_ollama_client.chat.return_value = {
            "message": {
                "content": '{"company_name": "Google", "role": "Software Engineer", "status": "submitted"}'
            }
        }
        mocker.patch("lazy_email.llm.extractor.get_settings", return_value=Mock(
            ollama_model="qwen2.5:3b",
            ollama_host="http://localhost:11434"
        ))

        extractor = JobApplicationExtractor()
        result = extractor.extract_from_content("Thank you for applying to Google...")

        assert result.company_name == "Google"
        assert result.role == "Software Engineer"
        assert result.status_raw == "submitted"

    def test_extract_from_email(
        self, mock_ollama_client: Mock, sample_email: EmailMessage, mocker: "MockerFixture"
    ) -> None:
        """Test extracting JobApplication from EmailMessage."""
        # Setup mock response
        mock_ollama_client.chat.return_value = {
            "message": {
                "content": '{"company_name": "Google", "role": "Software Engineer", "status": "submitted"}'
            }
        }
        mocker.patch("lazy_email.llm.extractor.get_settings", return_value=Mock(
            ollama_model="qwen2.5:3b",
            ollama_host="http://localhost:11434"
        ))

        extractor = JobApplicationExtractor()
        result = extractor.extract_from_email(sample_email)

        assert result.company_name == "Google"
        assert result.role == "Software Engineer"
        assert result.status == ApplicationStatus.SUBMITTED
        assert result.date_submitted == "2026-01-10"
        assert result.email_link == sample_email.email_link

    def test_extract_batch_success(
        self, mock_ollama_client: Mock, sample_email: EmailMessage, mocker: "MockerFixture"
    ) -> None:
        """Test batch extraction with multiple emails."""
        mock_ollama_client.chat.return_value = {
            "message": {
                "content": '{"company_name": "TestCo", "role": "Engineer", "status": "interview"}'
            }
        }
        mocker.patch("lazy_email.llm.extractor.get_settings", return_value=Mock(
            ollama_model="qwen2.5:3b",
            ollama_host="http://localhost:11434"
        ))

        extractor = JobApplicationExtractor()
        emails = [sample_email, sample_email]
        results = extractor.extract_batch(emails)

        assert len(results) == 2
        assert all(r.company_name == "TestCo" for r in results)
        assert all(r.status == ApplicationStatus.INTERVIEW for r in results)

    def test_extract_batch_with_failure(
        self, mock_ollama_client: Mock, sample_email: EmailMessage, mocker: "MockerFixture"
    ) -> None:
        """Test batch extraction handles failures gracefully."""
        from ollama import ResponseError

        # First call succeeds, second fails
        mock_ollama_client.chat.side_effect = [
            {"message": {"content": '{"company_name": "Good", "role": "Dev", "status": "submitted"}'}},
            ResponseError("Model error"),
        ]
        mocker.patch("lazy_email.llm.extractor.get_settings", return_value=Mock(
            ollama_model="qwen2.5:3b",
            ollama_host="http://localhost:11434"
        ))

        extractor = JobApplicationExtractor()
        emails = [sample_email, sample_email]
        results = extractor.extract_batch(emails)

        assert len(results) == 2
        assert results[0].company_name == "Good"
        assert results[1].company_name == "Unknown"  # Fallback for failed extraction
        assert results[1].status == ApplicationStatus.NA

    def test_call_llm_error_handling(
        self, mock_ollama_client: Mock, mocker: "MockerFixture"
    ) -> None:
        """Test LLM call error handling."""
        from ollama import ResponseError

        mock_ollama_client.chat.side_effect = ResponseError("Connection failed")
        mocker.patch("lazy_email.llm.extractor.get_settings", return_value=Mock(
            ollama_model="qwen2.5:3b",
            ollama_host="http://localhost:11434"
        ))

        extractor = JobApplicationExtractor()

        with pytest.raises(LLMExtractorError, match="Ollama API error"):
            extractor.extract_from_content("test content")

    def test_verify_connection_success(
        self, mock_ollama_client: Mock, mocker: "MockerFixture"
    ) -> None:
        """Test successful connection verification."""
        mock_ollama_client.list.return_value = {
            "models": [{"name": "qwen2.5:3b"}]
        }
        mock_ollama_client.chat.return_value = {
            "message": {"content": '{"test": "ok"}'}
        }
        mocker.patch("lazy_email.llm.extractor.get_settings", return_value=Mock(
            ollama_model="qwen2.5:3b",
            ollama_host="http://localhost:11434"
        ))

        extractor = JobApplicationExtractor()
        result = extractor.verify_connection()

        assert result is True

    def test_verify_connection_model_not_found(
        self, mock_ollama_client: Mock, mocker: "MockerFixture", capsys: "CaptureFixture[str]"
    ) -> None:
        """Test connection verification when model is not found."""
        mock_ollama_client.list.return_value = {
            "models": [{"name": "other-model:latest"}]
        }
        mocker.patch("lazy_email.llm.extractor.get_settings", return_value=Mock(
            ollama_model="qwen2.5:3b",
            ollama_host="http://localhost:11434"
        ))

        extractor = JobApplicationExtractor()
        result = extractor.verify_connection()

        assert result is False
        captured = capsys.readouterr()
        assert "not found" in captured.out
        assert "ollama pull" in captured.out


class TestStatusMappings:
    """Tests for STATUS_MAPPINGS dictionary."""

    def test_all_status_values_are_valid_enums(self) -> None:
        """Verify all mapped values are valid ApplicationStatus enums."""
        for status in STATUS_MAPPINGS.values():
            assert isinstance(status, ApplicationStatus)

    def test_mappings_cover_all_enum_values(self) -> None:
        """Verify mappings exist for all ApplicationStatus values."""
        mapped_statuses = set(STATUS_MAPPINGS.values())
        enum_statuses = set(ApplicationStatus)
        assert mapped_statuses == enum_statuses


class TestExtractionPrompt:
    """Tests for extraction prompt template."""

    def test_prompt_contains_required_fields(self) -> None:
        """Verify prompt mentions all required extraction fields."""
        assert "company_name" in EXTRACTION_PROMPT
        assert "role" in EXTRACTION_PROMPT
        assert "status" in EXTRACTION_PROMPT

    def test_prompt_contains_status_options(self) -> None:
        """Verify prompt lists all status options."""
        assert "submitted" in EXTRACTION_PROMPT
        assert "rejected" in EXTRACTION_PROMPT
        assert "interview" in EXTRACTION_PROMPT
        assert "oa_invite" in EXTRACTION_PROMPT
        assert "n/a" in EXTRACTION_PROMPT

    def test_prompt_has_placeholder_for_content(self) -> None:
        """Verify prompt has placeholder for email content."""
        assert "{email_content}" in EXTRACTION_PROMPT
