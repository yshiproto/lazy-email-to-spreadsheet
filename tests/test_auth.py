"""Tests for Google OAuth authentication module."""

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, Mock

import pytest
from google.oauth2.credentials import Credentials

from lazy_email.auth.google_auth import (
    SCOPES,
    AuthenticationError,
    get_credentials,
    get_gmail_service,
    get_sheets_service,
    verify_authentication,
)

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.fixtures import FixtureRequest
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture


@pytest.fixture
def mock_credentials() -> Mock:
    """Create a mock Credentials object.

    Returns:
        Mock Credentials with valid=True.
    """
    creds = Mock(spec=Credentials)
    creds.valid = True
    creds.expired = False
    creds.refresh_token = None
    creds.to_json.return_value = '{"token": "mock_token"}'
    return creds


@pytest.fixture
def mock_expired_credentials() -> Mock:
    """Create a mock expired Credentials object with refresh token.

    Returns:
        Mock expired Credentials with refresh_token.
    """
    creds = Mock(spec=Credentials)
    creds.valid = False
    creds.expired = True
    creds.refresh_token = "mock_refresh_token"
    creds.to_json.return_value = '{"token": "mock_refreshed_token"}'
    return creds


class TestGetCredentials:
    """Tests for get_credentials function."""

    def test_get_credentials_with_valid_token(
        self, mocker: "MockerFixture", mock_credentials: Mock, tmp_path: Path
    ) -> None:
        """Test loading valid existing credentials from token.json."""
        # Setup
        token_file = tmp_path / "token.json"
        token_file.write_text('{"token": "existing"}')

        mocker.patch("lazy_email.auth.google_auth._get_token_file_path", return_value=token_file)
        mocker.patch(
            "lazy_email.auth.google_auth.Credentials.from_authorized_user_file",
            return_value=mock_credentials,
        )

        # Execute
        result = get_credentials()

        # Verify
        assert result == mock_credentials
        assert result.valid is True

    def test_get_credentials_refreshes_expired_token(
        self, mocker: "MockerFixture", mock_expired_credentials: Mock, tmp_path: Path
    ) -> None:
        """Test refreshing expired credentials with refresh token."""
        # Setup
        token_file = tmp_path / "token.json"
        token_file.write_text('{"token": "expired"}')

        mocker.patch("lazy_email.auth.google_auth._get_token_file_path", return_value=token_file)
        mocker.patch(
            "lazy_email.auth.google_auth.Credentials.from_authorized_user_file",
            return_value=mock_expired_credentials,
        )
        # Mock refresh to make credentials valid
        def refresh_side_effect(request):
            mock_expired_credentials.valid = True
            mock_expired_credentials.expired = False

        mock_expired_credentials.refresh.side_effect = refresh_side_effect

        # Execute
        result = get_credentials()

        # Verify
        mock_expired_credentials.refresh.assert_called_once()
        assert result == mock_expired_credentials

    def test_get_credentials_runs_oauth_flow_when_no_token(
        self, mocker: "MockerFixture", mock_credentials: Mock, tmp_path: Path
    ) -> None:
        """Test running OAuth flow when token.json doesn't exist."""
        # Setup
        token_file = tmp_path / "token.json"
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text('{"client_id": "mock"}')

        mocker.patch("lazy_email.auth.google_auth._get_token_file_path", return_value=token_file)
        mocker.patch(
            "lazy_email.auth.google_auth._get_credentials_file_path", return_value=creds_file
        )

        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_credentials
        mocker.patch(
            "lazy_email.auth.google_auth.InstalledAppFlow.from_client_secrets_file",
            return_value=mock_flow,
        )

        # Execute
        result = get_credentials()

        # Verify
        mock_flow.run_local_server.assert_called_once_with(port=0)
        assert result == mock_credentials

    def test_get_credentials_raises_error_when_credentials_missing(
        self, mocker: "MockerFixture", tmp_path: Path
    ) -> None:
        """Test error raised when credentials.json is missing."""
        # Setup
        token_file = tmp_path / "token.json"
        creds_file = tmp_path / "credentials.json"  # Does not exist

        mocker.patch("lazy_email.auth.google_auth._get_token_file_path", return_value=token_file)
        mocker.patch(
            "lazy_email.auth.google_auth._get_credentials_file_path", return_value=creds_file
        )

        # Execute & Verify
        with pytest.raises(AuthenticationError, match="Credentials file not found"):
            get_credentials()


class TestGetServices:
    """Tests for get_gmail_service and get_sheets_service."""

    def test_get_gmail_service(
        self, mocker: "MockerFixture", mock_credentials: Mock
    ) -> None:
        """Test creating Gmail API service."""
        # Setup
        mocker.patch("lazy_email.auth.google_auth.get_credentials", return_value=mock_credentials)
        mock_build = mocker.patch("lazy_email.auth.google_auth.build")
        mock_service = Mock()
        mock_build.return_value = mock_service

        # Execute
        result = get_gmail_service()

        # Verify
        mock_build.assert_called_once_with("gmail", "v1", credentials=mock_credentials)
        assert result == mock_service

    def test_get_sheets_service(
        self, mocker: "MockerFixture", mock_credentials: Mock
    ) -> None:
        """Test creating Sheets API service."""
        # Setup
        mocker.patch("lazy_email.auth.google_auth.get_credentials", return_value=mock_credentials)
        mock_build = mocker.patch("lazy_email.auth.google_auth.build")
        mock_service = Mock()
        mock_build.return_value = mock_service

        # Execute
        result = get_sheets_service()

        # Verify
        mock_build.assert_called_once_with("sheets", "v4", credentials=mock_credentials)
        assert result == mock_service

    def test_get_gmail_service_raises_on_build_failure(
        self, mocker: "MockerFixture", mock_credentials: Mock
    ) -> None:
        """Test error handling when building Gmail service fails."""
        # Setup
        mocker.patch("lazy_email.auth.google_auth.get_credentials", return_value=mock_credentials)
        mocker.patch("lazy_email.auth.google_auth.build", side_effect=Exception("Build failed"))

        # Execute & Verify
        with pytest.raises(AuthenticationError, match="Failed to build Gmail service"):
            get_gmail_service()


class TestVerifyAuthentication:
    """Tests for verify_authentication function."""

    def test_verify_authentication_success(self, mocker: "MockerFixture") -> None:
        """Test successful authentication verification."""
        # Setup
        mock_service = Mock()
        mock_service.users().getProfile().execute.return_value = {"emailAddress": "test@test.com"}
        mocker.patch("lazy_email.auth.google_auth.get_gmail_service", return_value=mock_service)

        # Execute
        result = verify_authentication()

        # Verify
        assert result is True
        mock_service.users().getProfile.assert_called_once_with(userId="me")

    def test_verify_authentication_failure(self, mocker: "MockerFixture") -> None:
        """Test authentication verification failure."""
        # Setup
        mocker.patch(
            "lazy_email.auth.google_auth.get_gmail_service",
            side_effect=Exception("Auth failed"),
        )

        # Execute
        result = verify_authentication()

        # Verify
        assert result is False


class TestScopes:
    """Tests for OAuth scopes configuration."""

    def test_scopes_include_gmail_readonly(self) -> None:
        """Verify Gmail readonly scope is included."""
        assert "https://www.googleapis.com/auth/gmail.readonly" in SCOPES

    def test_scopes_include_sheets_readwrite(self) -> None:
        """Verify Sheets read/write scope is included."""
        assert "https://www.googleapis.com/auth/spreadsheets" in SCOPES

    def test_scopes_count(self) -> None:
        """Verify we have exactly 2 scopes."""
        assert len(SCOPES) == 2
