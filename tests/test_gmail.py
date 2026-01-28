"""Tests for Gmail API client."""

import base64
from datetime import datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

import pytest
from googleapiclient.errors import HttpError

from lazy_email.gmail.client import (
    GmailClient,
    GmailClientError,
    _extract_header_value,
    _extract_text_from_payload,
    _parse_email_date,
)
from lazy_email.models.email import EmailMessage

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.fixtures import FixtureRequest
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture


@pytest.fixture
def mock_gmail_service() -> Mock:
    """Create a mock Gmail API service.

    Returns:
        Mock Gmail service with message list and get methods.
    """
    service = Mock()
    return service


@pytest.fixture
def sample_gmail_message() -> dict[str, Any]:
    """Create a sample Gmail API message response.

    Returns:
        Dictionary mimicking Gmail API message format.
    """
    content = "Thank you for applying to the Software Engineer position at Acme Corp."
    encoded_content = base64.urlsafe_b64encode(content.encode()).decode()

    return {
        "id": "abc123def456",
        "threadId": "thread123",
        "payload": {
            "headers": [
                {"name": "From", "value": "careers@acmecorp.com"},
                {"name": "Date", "value": "Mon, 10 Jan 2026 14:30:00 +0000"},
                {"name": "Subject", "value": "Application Received"},
            ],
            "body": {"data": encoded_content},
        },
    }


@pytest.fixture
def sample_multipart_message() -> dict[str, Any]:
    """Create a sample multipart Gmail message.

    Returns:
        Dictionary mimicking Gmail API multipart message format.
    """
    plain_text = "This is plain text content."
    html_text = "<html><body>This is HTML content.</body></html>"

    plain_encoded = base64.urlsafe_b64encode(plain_text.encode()).decode()
    html_encoded = base64.urlsafe_b64encode(html_text.encode()).decode()

    return {
        "id": "multipart123",
        "threadId": "thread456",
        "payload": {
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "Date", "value": "Tue, 11 Jan 2026 09:15:00 +0000"},
            ],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": plain_encoded}},
                {"mimeType": "text/html", "body": {"data": html_encoded}},
            ],
        },
    }


class TestExtractHeaderValue:
    """Tests for _extract_header_value helper function."""

    def test_extract_existing_header(self) -> None:
        """Test extracting a header that exists."""
        headers = [
            {"name": "From", "value": "test@example.com"},
            {"name": "Subject", "value": "Test Subject"},
        ]
        assert _extract_header_value(headers, "From") == "test@example.com"

    def test_extract_case_insensitive(self) -> None:
        """Test header extraction is case-insensitive."""
        headers = [{"name": "Subject", "value": "Test"}]
        assert _extract_header_value(headers, "subject") == "Test"
        assert _extract_header_value(headers, "SUBJECT") == "Test"

    def test_extract_missing_header(self) -> None:
        """Test extracting a header that doesn't exist returns empty string."""
        headers = [{"name": "From", "value": "test@example.com"}]
        assert _extract_header_value(headers, "To") == ""


class TestParseEmailDate:
    """Tests for _parse_email_date helper function."""

    def test_parse_standard_date(self) -> None:
        """Test parsing standard email date format."""
        date_str = "Mon, 10 Jan 2026 14:30:00 +0000"
        result = _parse_email_date(date_str)
        assert isinstance(result, datetime)
        assert result.day == 10
        assert result.month == 1
        assert result.year == 2026

    def test_parse_invalid_date_raises_error(self) -> None:
        """Test parsing invalid date raises ValueError."""
        with pytest.raises(ValueError, match="Failed to parse date"):
            _parse_email_date("invalid date string")


class TestExtractTextFromPayload:
    """Tests for _extract_text_from_payload helper function."""

    def test_extract_simple_body(self) -> None:
        """Test extracting text from simple message body."""
        content = "Hello, World!"
        encoded = base64.urlsafe_b64encode(content.encode()).decode()
        payload = {"body": {"data": encoded}}

        result = _extract_text_from_payload(payload)
        assert result == content

    def test_extract_from_multipart_plain_text(self) -> None:
        """Test extracting plain text from multipart message."""
        plain_text = "Plain text content"
        encoded = base64.urlsafe_b64encode(plain_text.encode()).decode()

        payload = {
            "parts": [
                {"mimeType": "text/plain", "body": {"data": encoded}},
                {"mimeType": "text/html", "body": {"data": "aHRtbA=="}},
            ]
        }

        result = _extract_text_from_payload(payload)
        assert result == plain_text

    def test_extract_html_when_no_plain_text(self) -> None:
        """Test extracting HTML when plain text is not available."""
        html = "<p>HTML content</p>"
        encoded = base64.urlsafe_b64encode(html.encode()).decode()

        payload = {"parts": [{"mimeType": "text/html", "body": {"data": encoded}}]}

        result = _extract_text_from_payload(payload)
        assert "HTML content" in result  # HTML tags should be stripped

    def test_extract_empty_payload(self) -> None:
        """Test extracting from empty payload returns empty string."""
        payload = {}
        result = _extract_text_from_payload(payload)
        assert result == ""


class TestGmailClient:
    """Tests for GmailClient class."""

    def test_init_with_service(self, mock_gmail_service: Mock) -> None:
        """Test initializing client with provided service."""
        client = GmailClient(service=mock_gmail_service)
        assert client.service == mock_gmail_service
        assert client.user_id == "me"

    def test_build_query_primary_only(self) -> None:
        """Test building query for primary inbox only."""
        client = GmailClient(service=Mock())
        query = client._build_query()
        assert query == "category:primary"

    def test_build_query_with_since_date(self) -> None:
        """Test building query with since date filter."""
        client = GmailClient(service=Mock())
        query = client._build_query(since_date="2025-12-01")
        assert query == "category:primary after:2025/12/01"

    def test_parse_message_to_email(
        self, sample_gmail_message: dict[str, Any], mock_gmail_service: Mock
    ) -> None:
        """Test parsing Gmail message to EmailMessage model."""
        client = GmailClient(service=mock_gmail_service)
        email = client._parse_message_to_email(sample_gmail_message)

        assert isinstance(email, EmailMessage)
        assert email.message_id == "abc123def456"
        assert email.sender == "careers@acmecorp.com"
        assert "Acme Corp" in email.content
        assert email.email_link == "https://mail.google.com/mail/u/0/#inbox/abc123def456"

    def test_parse_multipart_message(
        self, sample_multipart_message: dict[str, Any], mock_gmail_service: Mock
    ) -> None:
        """Test parsing multipart message prefers plain text."""
        client = GmailClient(service=mock_gmail_service)
        email = client._parse_message_to_email(sample_multipart_message)

        assert isinstance(email, EmailMessage)
        assert email.content == "This is plain text content."

    def test_fetch_messages_empty_inbox(self, mocker: "MockerFixture") -> None:
        """Test fetching messages when inbox is empty."""
        mock_service = Mock()
        mock_service.users().messages().list().execute.return_value = {"messages": []}

        client = GmailClient(service=mock_service)
        result = client.fetch_messages(since_date="2026-01-01")

        assert result == []

    def test_fetch_messages_with_results(
        self, mocker: "MockerFixture", sample_gmail_message: dict[str, Any]
    ) -> None:
        """Test fetching messages with results."""
        mock_service = Mock()

        # Mock list response
        mock_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "abc123def456"}]
        }

        # Mock get response
        mock_service.users().messages().get().execute.return_value = sample_gmail_message

        # Mock sleep to speed up test
        mocker.patch("time.sleep")

        client = GmailClient(service=mock_service)
        result = client.fetch_messages(since_date="2026-01-10")

        assert len(result) == 1
        assert isinstance(result[0], EmailMessage)
        assert result[0].message_id == "abc123def456"

    def test_fetch_single_message(
        self, sample_gmail_message: dict[str, Any], mock_gmail_service: Mock
    ) -> None:
        """Test fetching a single message by ID."""
        mock_gmail_service.users().messages().get().execute.return_value = sample_gmail_message

        client = GmailClient(service=mock_gmail_service)
        email = client.fetch_single_message("abc123def456")

        assert isinstance(email, EmailMessage)
        assert email.message_id == "abc123def456"

    def test_list_messages_rate_limit_error(self, mocker: "MockerFixture") -> None:
        """Test rate limit handling in list messages."""
        mock_service = Mock()

        # Create HttpError mock
        mock_response = Mock()
        mock_response.status = 429

        error = HttpError(resp=mock_response, content=b"Rate limit exceeded")

        # First call raises rate limit, second succeeds
        mock_service.users().messages().list().execute.side_effect = [
            error,
            {"messages": []},
        ]

        client = GmailClient(service=mock_service)

        # Should retry and succeed
        result = client._list_messages_with_retry("category:primary")
        assert result == []

    def test_get_message_non_retryable_error(self) -> None:
        """Test non-retryable errors raise GmailClientError."""
        mock_service = Mock()

        # Create non-retryable error (404)
        mock_response = Mock()
        mock_response.status = 404
        error = HttpError(resp=mock_response, content=b"Not found")

        mock_service.users().messages().get().execute.side_effect = error

        client = GmailClient(service=mock_service)

        with pytest.raises(GmailClientError, match="Failed to get message"):
            client._get_message_with_retry("nonexistent_id")


class TestGmailClientIntegration:
    """Integration-style tests for GmailClient workflow."""

    def test_complete_fetch_workflow(
        self, mocker: "MockerFixture", sample_gmail_message: dict[str, Any]
    ) -> None:
        """Test complete workflow from list to parse."""
        mock_service = Mock()

        # Mock list
        mock_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "abc123def456"}, {"id": "xyz789"}]
        }

        # Mock get for each message
        mock_service.users().messages().get().execute.return_value = sample_gmail_message

        # Mock sleep
        mocker.patch("time.sleep")

        client = GmailClient(service=mock_service)
        emails = client.fetch_messages(since_date="2026-01-01", max_results=10)

        assert len(emails) == 2
        assert all(isinstance(email, EmailMessage) for email in emails)
        assert all(email.message_id in ["abc123def456", "xyz789"] for email in emails)
