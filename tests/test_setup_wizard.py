"""Tests for the setup wizard module."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, Mock, patch

import pytest

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from pytest_mock.plugin import MockerFixture


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_gmail_service() -> Mock:
    svc = Mock()
    svc.users.return_value.getProfile.return_value.execute.return_value = {
        "emailAddress": "user@example.com"
    }
    return svc


# ---------------------------------------------------------------------------
# _check_ollama_running
# ---------------------------------------------------------------------------


class TestCheckOllamaRunning:
    def test_returns_true_when_ollama_responds(self, mocker: "MockerFixture") -> None:
        mock_resp = Mock()
        mock_resp.status = 200
        mock_cm = Mock()
        mock_cm.__enter__ = Mock(return_value=mock_resp)
        mock_cm.__exit__ = Mock(return_value=False)
        mocker.patch("urllib.request.urlopen", return_value=mock_cm)

        from lazy_email.setup_wizard import _check_ollama_running

        assert _check_ollama_running() is True

    def test_returns_false_on_connection_error(self, mocker: "MockerFixture") -> None:
        import urllib.error

        mocker.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused"))

        from lazy_email.setup_wizard import _check_ollama_running

        assert _check_ollama_running() is False

    def test_returns_false_on_timeout(self, mocker: "MockerFixture") -> None:
        mocker.patch("urllib.request.urlopen", side_effect=TimeoutError())

        from lazy_email.setup_wizard import _check_ollama_running

        assert _check_ollama_running() is False


# ---------------------------------------------------------------------------
# _start_ollama
# ---------------------------------------------------------------------------


class TestStartOllama:
    def test_returns_true_when_ollama_starts(self, mocker: "MockerFixture") -> None:
        mocker.patch("subprocess.Popen")
        mocker.patch("time.sleep")
        mocker.patch("lazy_email.setup_wizard._check_ollama_running", return_value=True)

        from lazy_email.setup_wizard import _start_ollama

        assert _start_ollama() is True

    def test_returns_false_when_ollama_not_found(self, mocker: "MockerFixture") -> None:
        mocker.patch("subprocess.Popen", side_effect=FileNotFoundError())

        from lazy_email.setup_wizard import _start_ollama

        assert _start_ollama() is False

    def test_returns_false_when_ollama_never_starts(self, mocker: "MockerFixture") -> None:
        mocker.patch("subprocess.Popen")
        mocker.patch("time.sleep")
        mocker.patch("lazy_email.setup_wizard._check_ollama_running", return_value=False)

        from lazy_email.setup_wizard import _start_ollama

        assert _start_ollama() is False


# ---------------------------------------------------------------------------
# _check_google_auth
# ---------------------------------------------------------------------------


class TestCheckGoogleAuth:
    def test_already_authenticated(
        self,
        mocker: "MockerFixture",
        mock_gmail_service: Mock,
        capsys: "CaptureFixture",
    ) -> None:
        mocker.patch("lazy_email.setup_wizard.get_credentials")
        mocker.patch("lazy_email.setup_wizard.get_gmail_service", return_value=mock_gmail_service)

        from lazy_email.setup_wizard import _check_google_auth

        result = _check_google_auth(1, 5)

        assert result is True
        assert "user@example.com" in capsys.readouterr().out

    def test_auth_error_then_login_succeeds(
        self,
        mocker: "MockerFixture",
        mock_gmail_service: Mock,
        capsys: "CaptureFixture",
    ) -> None:
        from lazy_email.auth.google_auth import AuthenticationError

        mocker.patch(
            "lazy_email.setup_wizard.get_credentials",
            side_effect=AuthenticationError("not logged in"),
        )
        mocker.patch("os.environ.get", return_value=None)
        mocker.patch("lazy_email.setup_wizard.Path.exists", return_value=True)
        mocker.patch("lazy_email.setup_wizard.run_login_flow")
        mocker.patch("lazy_email.setup_wizard.get_gmail_service", return_value=mock_gmail_service)

        from lazy_email.setup_wizard import _check_google_auth

        result = _check_google_auth(1, 5)

        assert result is True

    def test_auth_failure_returns_false(
        self,
        mocker: "MockerFixture",
        capsys: "CaptureFixture",
    ) -> None:
        from lazy_email.auth.google_auth import AuthenticationError

        mocker.patch(
            "lazy_email.setup_wizard.get_credentials",
            side_effect=AuthenticationError("no token"),
        )
        mocker.patch("os.environ.get", return_value=None)
        mocker.patch("lazy_email.setup_wizard.Path.exists", return_value=True)
        mocker.patch(
            "lazy_email.setup_wizard.run_login_flow",
            side_effect=Exception("OAuth failed"),
        )

        from lazy_email.setup_wizard import _check_google_auth

        result = _check_google_auth(1, 5)

        assert result is False


# ---------------------------------------------------------------------------
# _check_spreadsheet
# ---------------------------------------------------------------------------


class TestCheckSpreadsheet:
    def test_already_configured(
        self,
        mocker: "MockerFixture",
        capsys: "CaptureFixture",
    ) -> None:
        settings = Mock()
        settings.spreadsheet_id = "existing_id"
        mocker.patch("lazy_email.setup_wizard.get_settings", return_value=settings)

        from lazy_email.setup_wizard import _check_spreadsheet

        result = _check_spreadsheet(2, 5)

        assert result is True
        assert "existing_id" in capsys.readouterr().out

    def test_user_enters_url(
        self,
        mocker: "MockerFixture",
        capsys: "CaptureFixture",
    ) -> None:
        settings = Mock()
        settings.spreadsheet_id = None
        mocker.patch("lazy_email.setup_wizard.get_settings", return_value=settings)
        mocker.patch(
            "builtins.input",
            return_value="https://docs.google.com/spreadsheets/d/ABC123/edit",
        )
        mock_update = mocker.patch("lazy_email.setup_wizard.update_settings")

        from lazy_email.setup_wizard import _check_spreadsheet

        result = _check_spreadsheet(2, 5)

        assert result is True
        mock_update.assert_called_once_with(spreadsheet_id="ABC123")

    def test_user_skips_entry(
        self,
        mocker: "MockerFixture",
        capsys: "CaptureFixture",
    ) -> None:
        settings = Mock()
        settings.spreadsheet_id = None
        mocker.patch("lazy_email.setup_wizard.get_settings", return_value=settings)
        mocker.patch("builtins.input", return_value="")

        from lazy_email.setup_wizard import _check_spreadsheet

        result = _check_spreadsheet(2, 5)

        # Skipping is not fatal
        assert result is True
        assert "Skip" in capsys.readouterr().out

    def test_invalid_url_returns_false(
        self,
        mocker: "MockerFixture",
    ) -> None:
        settings = Mock()
        settings.spreadsheet_id = None
        mocker.patch("lazy_email.setup_wizard.get_settings", return_value=settings)
        mocker.patch("builtins.input", return_value="not-a-valid-url-or-id")

        from lazy_email.setup_wizard import _check_spreadsheet

        # A plain ID (no "docs.google.com") is accepted as-is
        # so test with malformed URL that trips the extractor
        mocker.patch("builtins.input", return_value="https://docs.google.com/bad-url")
        result = _check_spreadsheet(2, 5)

        assert result is False


# ---------------------------------------------------------------------------
# _check_ollama
# ---------------------------------------------------------------------------


class TestCheckOllama:
    def test_already_running(
        self,
        mocker: "MockerFixture",
        capsys: "CaptureFixture",
    ) -> None:
        mocker.patch("lazy_email.setup_wizard._check_ollama_running", return_value=True)

        from lazy_email.setup_wizard import _check_ollama

        result = _check_ollama(3, 5)

        assert result is True
        assert "running" in capsys.readouterr().out

    def test_installed_but_not_running_user_starts(
        self,
        mocker: "MockerFixture",
        capsys: "CaptureFixture",
    ) -> None:
        mocker.patch("lazy_email.setup_wizard._check_ollama_running", return_value=False)
        mocker.patch("shutil.which", return_value="/usr/local/bin/ollama")
        mocker.patch("builtins.input", return_value="y")
        mocker.patch("lazy_email.setup_wizard._start_ollama", return_value=True)

        from lazy_email.setup_wizard import _check_ollama

        result = _check_ollama(3, 5)

        assert result is True

    def test_installed_but_not_running_user_declines(
        self,
        mocker: "MockerFixture",
    ) -> None:
        mocker.patch("lazy_email.setup_wizard._check_ollama_running", return_value=False)
        mocker.patch("shutil.which", return_value="/usr/local/bin/ollama")
        mocker.patch("builtins.input", return_value="n")

        from lazy_email.setup_wizard import _check_ollama

        result = _check_ollama(3, 5)

        assert result is False

    def test_not_installed_returns_false(
        self,
        mocker: "MockerFixture",
        capsys: "CaptureFixture",
    ) -> None:
        mocker.patch("lazy_email.setup_wizard._check_ollama_running", return_value=False)
        mocker.patch("shutil.which", return_value=None)
        mocker.patch("builtins.input", side_effect=KeyboardInterrupt)

        from lazy_email.setup_wizard import _check_ollama

        result = _check_ollama(3, 5)

        assert result is False


# ---------------------------------------------------------------------------
# _check_model
# ---------------------------------------------------------------------------


class TestCheckModel:
    def test_model_already_available(
        self,
        mocker: "MockerFixture",
        capsys: "CaptureFixture",
    ) -> None:
        settings = Mock()
        settings.ollama_model = "qwen2.5:3b"
        mocker.patch("lazy_email.setup_wizard.get_settings", return_value=settings)
        mocker.patch(
            "subprocess.run",
            return_value=Mock(stdout="qwen2.5:3b  ...", returncode=0),
        )

        from lazy_email.setup_wizard import _check_model

        result = _check_model(4, 5)

        assert result is True
        assert "available" in capsys.readouterr().out

    def test_model_missing_user_pulls(
        self,
        mocker: "MockerFixture",
        capsys: "CaptureFixture",
    ) -> None:
        settings = Mock()
        settings.ollama_model = "qwen2.5:3b"
        mocker.patch("lazy_email.setup_wizard.get_settings", return_value=settings)

        call_count = 0

        def fake_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if cmd == ["ollama", "list"]:
                return Mock(stdout="other_model", returncode=0)
            # ollama pull
            return Mock(returncode=0)

        mocker.patch("subprocess.run", side_effect=fake_run)
        mocker.patch("builtins.input", return_value="y")

        from lazy_email.setup_wizard import _check_model

        result = _check_model(4, 5)

        assert result is True
        assert call_count == 2

    def test_model_missing_user_skips(
        self,
        mocker: "MockerFixture",
    ) -> None:
        settings = Mock()
        settings.ollama_model = "qwen2.5:3b"
        mocker.patch("lazy_email.setup_wizard.get_settings", return_value=settings)
        mocker.patch(
            "subprocess.run",
            return_value=Mock(stdout="other_model", returncode=0),
        )
        mocker.patch("builtins.input", return_value="n")

        from lazy_email.setup_wizard import _check_model

        result = _check_model(4, 5)

        assert result is False

    def test_ollama_list_timeout_falls_through(
        self,
        mocker: "MockerFixture",
    ) -> None:
        settings = Mock()
        settings.ollama_model = "qwen2.5:3b"
        mocker.patch("lazy_email.setup_wizard.get_settings", return_value=settings)
        mocker.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ollama", 10))
        mocker.patch("builtins.input", return_value="n")

        from lazy_email.setup_wizard import _check_model

        # Falls through to pull prompt; user says no
        result = _check_model(4, 5)

        assert result is False


# ---------------------------------------------------------------------------
# _verify_connections
# ---------------------------------------------------------------------------


class TestVerifyConnections:
    def test_all_connections_pass(
        self,
        mocker: "MockerFixture",
        mock_gmail_service: Mock,
        capsys: "CaptureFixture",
    ) -> None:
        settings = Mock()
        settings.spreadsheet_id = "ABC123"
        mocker.patch("lazy_email.setup_wizard.get_settings", return_value=settings)
        mocker.patch("lazy_email.setup_wizard.get_gmail_service", return_value=mock_gmail_service)

        mock_sheets = Mock()
        mock_sheets.verify_connection.return_value = None
        mocker.patch(
            "lazy_email.sheets.client.SheetsClient", return_value=mock_sheets
        )

        mock_extractor = Mock()
        mock_extractor.verify_connection.return_value = True
        mocker.patch(
            "lazy_email.llm.extractor.JobApplicationExtractor", return_value=mock_extractor
        )

        from lazy_email.setup_wizard import _verify_connections

        result = _verify_connections(5, 5)

        assert result is True
        out = capsys.readouterr().out
        assert "Gmail" in out or "gmail" in out.lower()

    def test_gmail_failure_returns_false(
        self,
        mocker: "MockerFixture",
        capsys: "CaptureFixture",
    ) -> None:
        settings = Mock()
        settings.spreadsheet_id = None
        mocker.patch("lazy_email.setup_wizard.get_settings", return_value=settings)
        mocker.patch(
            "lazy_email.setup_wizard.get_gmail_service",
            side_effect=Exception("auth failed"),
        )

        mock_extractor = Mock()
        mock_extractor.verify_connection.return_value = True
        mocker.patch(
            "lazy_email.llm.extractor.JobApplicationExtractor", return_value=mock_extractor
        )

        from lazy_email.setup_wizard import _verify_connections

        result = _verify_connections(5, 5)

        assert result is False

    def test_sheets_skipped_when_no_spreadsheet(
        self,
        mocker: "MockerFixture",
        mock_gmail_service: Mock,
        capsys: "CaptureFixture",
    ) -> None:
        settings = Mock()
        settings.spreadsheet_id = None
        mocker.patch("lazy_email.setup_wizard.get_settings", return_value=settings)
        mocker.patch("lazy_email.setup_wizard.get_gmail_service", return_value=mock_gmail_service)

        mock_extractor = Mock()
        mock_extractor.verify_connection.return_value = True
        mocker.patch(
            "lazy_email.llm.extractor.JobApplicationExtractor", return_value=mock_extractor
        )

        from lazy_email.setup_wizard import _verify_connections

        result = _verify_connections(5, 5)

        out = capsys.readouterr().out
        assert "skipped" in out
        assert result is True


# ---------------------------------------------------------------------------
# run_setup_wizard (integration)
# ---------------------------------------------------------------------------


class TestRunSetupWizard:
    def test_full_success_returns_zero(
        self,
        mocker: "MockerFixture",
        capsys: "CaptureFixture",
    ) -> None:
        mocker.patch("lazy_email.setup_wizard._check_google_auth", return_value=True)
        mocker.patch("lazy_email.setup_wizard._check_spreadsheet", return_value=True)
        mocker.patch("lazy_email.setup_wizard._check_ollama", return_value=True)
        mocker.patch("lazy_email.setup_wizard._check_model", return_value=True)
        mocker.patch("lazy_email.setup_wizard._verify_connections", return_value=True)

        from lazy_email.setup_wizard import run_setup_wizard

        rc = run_setup_wizard()

        assert rc == 0
        out = capsys.readouterr().out
        assert "Setup complete" in out

    def test_partial_failure_returns_one(
        self,
        mocker: "MockerFixture",
        capsys: "CaptureFixture",
    ) -> None:
        mocker.patch("lazy_email.setup_wizard._check_google_auth", return_value=True)
        mocker.patch("lazy_email.setup_wizard._check_spreadsheet", return_value=True)
        mocker.patch("lazy_email.setup_wizard._check_ollama", return_value=False)
        mocker.patch("lazy_email.setup_wizard._check_model", return_value=False)
        mocker.patch("lazy_email.setup_wizard._verify_connections", return_value=False)

        from lazy_email.setup_wizard import run_setup_wizard

        rc = run_setup_wizard()

        assert rc == 1
        out = capsys.readouterr().out
        assert "Needs attention" in out

    def test_keyboard_interrupt_returns_one(
        self,
        mocker: "MockerFixture",
        capsys: "CaptureFixture",
    ) -> None:
        mocker.patch(
            "lazy_email.setup_wizard._check_google_auth",
            side_effect=KeyboardInterrupt,
        )

        from lazy_email.setup_wizard import run_setup_wizard

        rc = run_setup_wizard()

        assert rc == 1
