"""Tests for Google OAuth authentication module."""

import os
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, Mock

import pytest
from google.oauth2.credentials import Credentials

from lazy_email.auth.google_auth import (
    SCOPES,
    AuthenticationError,
    _get_credentials_path,
    _migrate_legacy_token,
    get_credentials,
    get_gmail_service,
    get_sheets_service,
    run_login_flow,
    verify_authentication,
)

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture


@pytest.fixture
def mock_credentials() -> Mock:
    """Create a mock Credentials object with valid=True."""
    creds = Mock(spec=Credentials)
    creds.valid = True
    creds.expired = False
    creds.refresh_token = None
    creds.to_json.return_value = '{"token": "mock_token"}'
    return creds


@pytest.fixture
def mock_expired_credentials() -> Mock:
    """Create a mock expired Credentials object with a refresh token."""
    creds = Mock(spec=Credentials)
    creds.valid = False
    creds.expired = True
    creds.refresh_token = "mock_refresh_token"
    creds.to_json.return_value = '{"token": "mock_refreshed_token"}'
    return creds


class TestGetCredentialsPath:
    """Tests for _get_credentials_path() resolution order."""

    def test_env_var_takes_priority(
        self, mocker: "MockerFixture", tmp_path: Path
    ) -> None:
        """CREDENTIALS_PATH env var overrides CWD credentials.json."""
        creds_file = tmp_path / "my_creds.json"
        creds_file.write_text('{"installed": {}}')
        mocker.patch.dict(os.environ, {"CREDENTIALS_PATH": str(creds_file)})

        result = _get_credentials_path()

        assert result == creds_file

    def test_env_var_missing_file_raises(
        self, mocker: "MockerFixture", tmp_path: Path
    ) -> None:
        """CREDENTIALS_PATH set but file missing raises AuthenticationError."""
        missing = tmp_path / "nonexistent.json"
        mocker.patch.dict(os.environ, {"CREDENTIALS_PATH": str(missing)})

        with pytest.raises(AuthenticationError, match="CREDENTIALS_PATH is set but file not found"):
            _get_credentials_path()

    def test_cwd_credentials_used_when_no_env_var(
        self, monkeypatch: "MonkeyPatch", tmp_path: Path
    ) -> None:
        """credentials.json in CWD is used when no env var is set."""
        monkeypatch.delenv("CREDENTIALS_PATH", raising=False)
        monkeypatch.chdir(tmp_path)
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text('{"installed": {}}')

        result = _get_credentials_path()

        assert isinstance(result, Path)
        assert result.resolve() == creds_file.resolve()

    def test_raises_when_no_credentials_found(
        self, monkeypatch: "MonkeyPatch", tmp_path: Path
    ) -> None:
        """AuthenticationError raised with setup guidance when no credentials exist."""
        monkeypatch.delenv("CREDENTIALS_PATH", raising=False)
        monkeypatch.chdir(tmp_path)  # no credentials.json here

        with pytest.raises(AuthenticationError, match="lazy-email setup"):
            _get_credentials_path()


class TestMigrateToken:
    """Tests for _migrate_legacy_token()."""

    def test_migrates_cwd_token_to_config_dir(
        self, mocker: "MockerFixture", monkeypatch: "MonkeyPatch", tmp_path: Path
    ) -> None:
        """Legacy token.json in CWD is moved to the config dir."""
        monkeypatch.chdir(tmp_path)
        legacy_token = tmp_path / "token.json"
        legacy_token.write_text('{"token": "old"}')

        new_token = tmp_path / "config" / "token.json"
        mocker.patch("lazy_email.auth.google_auth._get_token_file_path", return_value=new_token)

        _migrate_legacy_token()

        assert not legacy_token.exists()
        assert new_token.exists()
        assert new_token.read_text() == '{"token": "old"}'

    def test_does_not_overwrite_existing_token(
        self, mocker: "MockerFixture", monkeypatch: "MonkeyPatch", tmp_path: Path
    ) -> None:
        """Does not overwrite an existing token in the config dir."""
        monkeypatch.chdir(tmp_path)
        legacy_token = tmp_path / "token.json"
        legacy_token.write_text('{"token": "old"}')

        new_dir = tmp_path / "config"
        new_dir.mkdir()
        new_token = new_dir / "token.json"
        new_token.write_text('{"token": "new"}')
        mocker.patch("lazy_email.auth.google_auth._get_token_file_path", return_value=new_token)

        _migrate_legacy_token()

        assert legacy_token.exists()
        assert new_token.read_text() == '{"token": "new"}'

    def test_no_op_when_no_legacy_token(
        self, mocker: "MockerFixture", monkeypatch: "MonkeyPatch", tmp_path: Path
    ) -> None:
        """No error when no legacy token exists."""
        monkeypatch.chdir(tmp_path)
        new_token = tmp_path / "config" / "token.json"
        mocker.patch("lazy_email.auth.google_auth._get_token_file_path", return_value=new_token)

        _migrate_legacy_token()  # should not raise


class TestGetCredentials:
    """Tests for get_credentials function."""

    def test_get_credentials_with_valid_token(
        self, mocker: "MockerFixture", mock_credentials: Mock, tmp_path: Path
    ) -> None:
        """Load valid existing credentials from token file."""
        token_file = tmp_path / "token.json"
        token_file.write_text('{"token": "existing"}')

        mocker.patch("lazy_email.auth.google_auth._migrate_legacy_token")
        mocker.patch("lazy_email.auth.google_auth._get_token_file_path", return_value=token_file)
        mocker.patch(
            "lazy_email.auth.google_auth.Credentials.from_authorized_user_file",
            return_value=mock_credentials,
        )

        result = get_credentials()

        assert result == mock_credentials
        assert result.valid is True

    def test_get_credentials_refreshes_expired_token(
        self, mocker: "MockerFixture", mock_expired_credentials: Mock, tmp_path: Path
    ) -> None:
        """Refresh expired credentials using the refresh token."""
        token_file = tmp_path / "token.json"
        token_file.write_text('{"token": "expired"}')

        mocker.patch("lazy_email.auth.google_auth._migrate_legacy_token")
        mocker.patch("lazy_email.auth.google_auth._get_token_file_path", return_value=token_file)
        mocker.patch(
            "lazy_email.auth.google_auth.Credentials.from_authorized_user_file",
            return_value=mock_expired_credentials,
        )

        def refresh_side_effect(request):
            mock_expired_credentials.valid = True
            mock_expired_credentials.expired = False

        mock_expired_credentials.refresh.side_effect = refresh_side_effect

        result = get_credentials()

        mock_expired_credentials.refresh.assert_called_once()
        assert result == mock_expired_credentials

    def test_get_credentials_raises_when_no_token(
        self, mocker: "MockerFixture", tmp_path: Path
    ) -> None:
        """Raise AuthenticationError directing user to run lazy-email setup/login."""
        token_file = tmp_path / "token.json"  # does not exist

        mocker.patch("lazy_email.auth.google_auth._migrate_legacy_token")
        mocker.patch("lazy_email.auth.google_auth._get_token_file_path", return_value=token_file)

        with pytest.raises(AuthenticationError, match="lazy-email setup"):
            get_credentials()

    def test_get_credentials_raises_when_credentials_path_missing(
        self, mocker: "MockerFixture", tmp_path: Path
    ) -> None:
        """Raise AuthenticationError when CREDENTIALS_PATH points to missing file."""
        missing = tmp_path / "nonexistent.json"
        mocker.patch.dict(os.environ, {"CREDENTIALS_PATH": str(missing)})

        with pytest.raises(AuthenticationError, match="CREDENTIALS_PATH is set but file not found"):
            _get_credentials_path()


class TestRunLoginFlow:
    """Tests for run_login_flow()."""

    def test_already_authenticated_skips_flow(
        self, mocker: "MockerFixture", mock_credentials: Mock, capsys: "CaptureFixture"
    ) -> None:
        """Valid existing token skips browser flow and prints informational message."""
        mocker.patch("lazy_email.auth.google_auth.get_credentials", return_value=mock_credentials)

        run_login_flow(reauth=False)

        out = capsys.readouterr().out
        assert "Already authenticated" in out

    def test_reauth_forces_browser_flow(
        self, mocker: "MockerFixture", mock_credentials: Mock, tmp_path: Path
    ) -> None:
        """--reauth bypasses existing token and runs the OAuth flow."""
        token_path = tmp_path / "token.json"
        mocker.patch("lazy_email.auth.google_auth._get_token_file_path", return_value=token_path)
        mock_run = mocker.patch(
            "lazy_email.auth.google_auth._run_oauth_flow", return_value=mock_credentials
        )
        mocker.patch("lazy_email.auth.google_auth._save_credentials")

        run_login_flow(reauth=True)

        mock_run.assert_called_once()

    def test_creates_config_dir_if_missing(
        self, mocker: "MockerFixture", mock_credentials: Mock, tmp_path: Path
    ) -> None:
        """Config directory is created when it does not exist."""
        token_path = tmp_path / "nonexistent_dir" / "token.json"
        mocker.patch("lazy_email.auth.google_auth._get_token_file_path", return_value=token_path)
        mocker.patch(
            "lazy_email.auth.google_auth.get_credentials",
            side_effect=AuthenticationError("not logged in"),
        )
        mocker.patch("lazy_email.auth.google_auth._run_oauth_flow", return_value=mock_credentials)
        mocker.patch("lazy_email.auth.google_auth._save_credentials")

        run_login_flow(reauth=False)

        assert token_path.parent.exists()


class TestGetServices:
    """Tests for get_gmail_service and get_sheets_service."""

    def test_get_gmail_service(
        self, mocker: "MockerFixture", mock_credentials: Mock
    ) -> None:
        """Create Gmail API service with valid credentials."""
        mocker.patch("lazy_email.auth.google_auth.get_credentials", return_value=mock_credentials)
        mock_build = mocker.patch("lazy_email.auth.google_auth.build")
        mock_service = Mock()
        mock_build.return_value = mock_service

        result = get_gmail_service()

        mock_build.assert_called_once_with("gmail", "v1", credentials=mock_credentials)
        assert result == mock_service

    def test_get_sheets_service(
        self, mocker: "MockerFixture", mock_credentials: Mock
    ) -> None:
        """Create Sheets API service with valid credentials."""
        mocker.patch("lazy_email.auth.google_auth.get_credentials", return_value=mock_credentials)
        mock_build = mocker.patch("lazy_email.auth.google_auth.build")
        mock_service = Mock()
        mock_build.return_value = mock_service

        result = get_sheets_service()

        mock_build.assert_called_once_with("sheets", "v4", credentials=mock_credentials)
        assert result == mock_service

    def test_get_gmail_service_raises_on_build_failure(
        self, mocker: "MockerFixture", mock_credentials: Mock
    ) -> None:
        """Error handling when building Gmail service fails."""
        mocker.patch("lazy_email.auth.google_auth.get_credentials", return_value=mock_credentials)
        mocker.patch("lazy_email.auth.google_auth.build", side_effect=Exception("Build failed"))

        with pytest.raises(AuthenticationError, match="Failed to build Gmail service"):
            get_gmail_service()


class TestVerifyAuthentication:
    """Tests for verify_authentication function."""

    def test_verify_authentication_success(self, mocker: "MockerFixture") -> None:
        """Successful authentication verification returns True."""
        mock_service = Mock()
        # Use .return_value chain to configure without incrementing call counts
        mock_service.users.return_value.getProfile.return_value.execute.return_value = {
            "emailAddress": "test@test.com"
        }
        mocker.patch("lazy_email.auth.google_auth.get_gmail_service", return_value=mock_service)

        result = verify_authentication()

        assert result is True
        mock_service.users.return_value.getProfile.assert_called_once_with(userId="me")

    def test_verify_authentication_failure(self, mocker: "MockerFixture") -> None:
        """Authentication verification failure returns False."""
        mocker.patch(
            "lazy_email.auth.google_auth.get_gmail_service",
            side_effect=Exception("Auth failed"),
        )

        result = verify_authentication()

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
