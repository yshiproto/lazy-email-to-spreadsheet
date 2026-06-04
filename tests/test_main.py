"""Tests for the CLI main module."""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Mock external dependencies before importing main
sys.modules['google_auth_oauthlib'] = MagicMock()
sys.modules['google_auth_oauthlib.flow'] = MagicMock()
sys.modules['google.auth.transport.requests'] = MagicMock()
sys.modules['google.oauth2.credentials'] = MagicMock()
sys.modules['googleapiclient'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()
sys.modules['googleapiclient.errors'] = MagicMock()
sys.modules['ollama'] = MagicMock()
sys.modules['tenacity'] = MagicMock()

# Add src to path for testing without installation
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lazy_email.main import (  # noqa: E402
    create_parser,
    extract_spreadsheet_id,
    print_banner,
    print_step,
    validate_date,
)


class TestValidateDate:
    """Tests for the validate_date function."""

    def test_valid_date_format(self):
        """Test valid YYYY-MM-DD date is accepted."""
        result = validate_date("2025-01-15")
        assert result == "2025-01-15"

    def test_valid_date_various_formats(self):
        """Test various valid dates."""
        assert validate_date("2024-12-31") == "2024-12-31"
        assert validate_date("2025-06-01") == "2025-06-01"
        assert validate_date("2000-01-01") == "2000-01-01"

    def test_invalid_format_mm_dd_yyyy(self):
        """Test MM-DD-YYYY format raises error."""
        with pytest.raises(argparse.ArgumentTypeError) as exc_info:
            validate_date("12-15-2025")
        assert "Invalid date format" in str(exc_info.value)
        assert "YYYY-MM-DD" in str(exc_info.value)

    def test_invalid_format_slash_separator(self):
        """Test slash separator raises error."""
        with pytest.raises(argparse.ArgumentTypeError) as exc_info:
            validate_date("2025/01/15")
        assert "Invalid date format" in str(exc_info.value)

    def test_invalid_format_text(self):
        """Test text date raises error."""
        with pytest.raises(argparse.ArgumentTypeError) as exc_info:
            validate_date("January 15, 2025")
        assert "Invalid date format" in str(exc_info.value)

    def test_invalid_date_month_out_of_range(self):
        """Test month 13 raises error."""
        with pytest.raises(argparse.ArgumentTypeError):
            validate_date("2025-13-01")

    def test_invalid_date_day_out_of_range(self):
        """Test day 32 raises error."""
        with pytest.raises(argparse.ArgumentTypeError):
            validate_date("2025-01-32")


class TestExtractSpreadsheetId:
    """Tests for spreadsheet ID extraction."""

    def test_extract_from_full_url(self):
        """Test extracting ID from full Google Sheets URL."""
        url = "https://docs.google.com/spreadsheets/d/1eP_i4JCmCRG6LmaqssUf3FEX1D4oRMi0H8davQz9D9M/edit#gid=0"
        result = extract_spreadsheet_id(url)
        assert result == "1eP_i4JCmCRG6LmaqssUf3FEX1D4oRMi0H8davQz9D9M"

    def test_extract_from_url_without_edit(self):
        """Test extracting ID from URL without edit suffix."""
        url = "https://docs.google.com/spreadsheets/d/1eP_i4JCmCRG6LmaqssUf3FEX1D4oRMi0H8davQz9D9M"
        result = extract_spreadsheet_id(url)
        assert result == "1eP_i4JCmCRG6LmaqssUf3FEX1D4oRMi0H8davQz9D9M"

    def test_extract_raw_id(self):
        """Test passing raw ID returns as-is."""
        raw_id = "1eP_i4JCmCRG6LmaqssUf3FEX1D4oRMi0H8davQz9D9M"
        result = extract_spreadsheet_id(raw_id)
        assert result == raw_id

    def test_extract_from_url_with_dashes(self):
        """Test ID with dashes and underscores."""
        url = "https://docs.google.com/spreadsheets/d/abc-123_XYZ/edit"
        result = extract_spreadsheet_id(url)
        assert result == "abc-123_XYZ"

    def test_invalid_url_raises_error(self):
        """Test invalid URL raises error."""
        with pytest.raises(argparse.ArgumentTypeError):
            extract_spreadsheet_id("https://docs.google.com/spreadsheets/invalid")


class TestCreateParser:
    """Tests for the argument parser."""

    def test_since_required(self):
        """Test --since is required."""
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_since_accepted(self):
        """Test --since is properly parsed."""
        parser = create_parser()
        args = parser.parse_args(["--since", "2025-01-15"])
        assert args.since == "2025-01-15"

    def test_max_emails_default(self):
        """Test default max-emails value is unlimited."""
        parser = create_parser()
        args = parser.parse_args(["--since", "2025-01-01"])
        assert args.max_emails is None

    def test_max_emails_custom(self):
        """Test custom max-emails value."""
        parser = create_parser()
        args = parser.parse_args(["--since", "2025-01-01", "--max-emails", "50"])
        assert args.max_emails == 50

    def test_reset_flag_default(self):
        """Test --reset is False by default."""
        parser = create_parser()
        args = parser.parse_args(["--since", "2025-01-01"])
        assert args.reset is False

    def test_reset_flag_enabled(self):
        """Test --reset flag."""
        parser = create_parser()
        args = parser.parse_args(["--since", "2025-01-01", "--reset"])
        assert args.reset is True

    def test_verbose_flag_default(self):
        """Test -v/--verbose is False by default."""
        parser = create_parser()
        args = parser.parse_args(["--since", "2025-01-01"])
        assert args.verbose is False

    def test_verbose_flag_short(self):
        """Test -v flag."""
        parser = create_parser()
        args = parser.parse_args(["--since", "2025-01-01", "-v"])
        assert args.verbose is True

    def test_verbose_flag_long(self):
        """Test --verbose flag."""
        parser = create_parser()
        args = parser.parse_args(["--since", "2025-01-01", "--verbose"])
        assert args.verbose is True

    def test_dry_run_flag(self):
        """Test --dry-run flag."""
        parser = create_parser()
        args = parser.parse_args(["--since", "2025-01-01", "--dry-run"])
        assert args.dry_run is True

    def test_spreadsheet_id_flag(self):
        """Test --spreadsheet-id flag."""
        parser = create_parser()
        args = parser.parse_args([
            "--since", "2025-01-01",
            "--spreadsheet-id", "abc123"
        ])
        assert args.spreadsheet_id == "abc123"

    def test_spreadsheet_id_from_url(self):
        """Test --spreadsheet-id accepts URLs."""
        parser = create_parser()
        args = parser.parse_args([
            "--since", "2025-01-01",
            "--spreadsheet-id", "https://docs.google.com/spreadsheets/d/abc123/edit"
        ])
        assert args.spreadsheet_id == "abc123"

    def test_sheet_name_flag(self):
        """Test --sheet-name flag."""
        parser = create_parser()
        args = parser.parse_args([
            "--since", "2025-01-01",
            "--sheet-name", "Applications"
        ])
        assert args.sheet_name == "Applications"

    def test_model_flag(self):
        """Test --model flag."""
        parser = create_parser()
        args = parser.parse_args([
            "--since", "2025-01-01",
            "--model", "llama3:8b"
        ])
        assert args.model == "llama3:8b"


class TestPrintFunctions:
    """Tests for print helper functions."""

    def test_print_banner(self, capsys):
        """Test banner is printed correctly."""
        print_banner()
        captured = capsys.readouterr()
        assert "Lazy Email to Spreadsheet" in captured.out
        assert "Gmail → Google Sheets" in captured.out

    def test_print_step(self, capsys):
        """Test step progress is printed."""
        print_step(1, 4, "Testing step")
        captured = capsys.readouterr()
        assert "[1/4]" in captured.out
        assert "Testing step" in captured.out
        assert "-" * 50 in captured.out


class TestSignalHandlers:
    """Tests for signal handling."""

    def test_setup_signal_handlers_configures_sigint(self):
        """Test SIGINT handler is configured."""
        import signal

        from lazy_email.main import setup_signal_handlers

        mock_state_manager = MagicMock()

        # Store original handler
        original_handler = signal.getsignal(signal.SIGINT)

        try:
            setup_signal_handlers(mock_state_manager)

            # Check handler was changed
            new_handler = signal.getsignal(signal.SIGINT)
            assert new_handler != original_handler
        finally:
            # Restore original handler
            signal.signal(signal.SIGINT, original_handler)


class TestHandleResumePrompt:
    """Tests for resume prompt handling."""

    def test_no_previous_session_returns_true(self):
        """Test returns True when no previous session."""
        from lazy_email.main import handle_resume_prompt

        mock_state_manager = MagicMock()
        mock_state_manager.has_previous_session.return_value = False

        result = handle_resume_prompt(mock_state_manager, "2025-01-01")
        assert result is True

    @patch("builtins.input", return_value="y")
    def test_resume_same_date_yes(self, _mock_input):
        """Test user choosing to resume with same date."""
        from lazy_email.main import handle_resume_prompt
        from lazy_email.state import ProcessingState

        mock_state_manager = MagicMock()
        mock_state_manager.has_previous_session.return_value = True
        mock_state_manager.state = ProcessingState(
            since_date="2025-01-01",
            processed_ids={"msg1", "msg2"},
        )
        mock_state_manager.get_resume_prompt.return_value = "Resume? (y/n): "

        result = handle_resume_prompt(mock_state_manager, "2025-01-01")
        assert result is True
        mock_state_manager.reset.assert_not_called()

    @patch("builtins.input", return_value="n")
    def test_resume_same_date_no(self, _mock_input):
        """Test user choosing not to resume."""
        from lazy_email.main import handle_resume_prompt
        from lazy_email.state import ProcessingState

        mock_state_manager = MagicMock()
        mock_state_manager.has_previous_session.return_value = True
        mock_state_manager.state = ProcessingState(
            since_date="2025-01-01",
            processed_ids={"msg1", "msg2"},
        )
        mock_state_manager.get_resume_prompt.return_value = "Resume? (y/n): "

        result = handle_resume_prompt(mock_state_manager, "2025-01-01")
        assert result is True
        mock_state_manager.reset.assert_called_once()

    @patch("builtins.input", return_value="3")
    def test_different_date_abort(self, _mock_input):
        """Test user aborting when dates differ."""
        from lazy_email.main import handle_resume_prompt
        from lazy_email.state import ProcessingState

        mock_state_manager = MagicMock()
        mock_state_manager.has_previous_session.return_value = True
        mock_state_manager.state = ProcessingState(
            since_date="2024-12-01",  # Different date
            processed_ids={"msg1"},
        )

        result = handle_resume_prompt(mock_state_manager, "2025-01-01")
        assert result is False


class TestGracefulExit:
    """Tests for GracefulExit exception."""

    def test_graceful_exit_exception(self):
        """Test GracefulExit can be raised and caught."""
        from lazy_email.main import GracefulExit

        with pytest.raises(GracefulExit):
            raise GracefulExit()


class TestProgressOutputFlags:
    """Tests for progress-output CLI flags."""

    def test_legacy_output_flag_default(self):
        """Test --legacy-output is disabled by default."""
        parser = create_parser()
        args = parser.parse_args(["--since", "2025-01-01"])
        assert args.legacy_output is False

    def test_legacy_output_flag_enabled(self):
        """Test --legacy-output flag."""
        parser = create_parser()
        args = parser.parse_args(["--since", "2025-01-01", "--legacy-output"])
        assert args.legacy_output is True

    def test_legacy_output_help_text(self):
        """Test --legacy-output appears in help text."""
        parser = create_parser()
        assert "--legacy-output" in parser.format_help()


class TestProgressReporter:
    """Tests for the CLI progress reporter abstraction."""

    def test_track_preserves_items(self):
        """Test deterministic progress tracking yields every item exactly once."""
        from lazy_email.cli_progress import OutputMode, ProgressReporter

        reporter = ProgressReporter(OutputMode.DETERMINISTIC)
        items = ["a", "b", "c"]

        assert list(reporter.track(items, description="Testing", total=len(items))) == items

    def test_status_does_not_swallow_exceptions(self):
        """Test status contexts preserve exceptions from wrapped work."""
        from lazy_email.cli_progress import OutputMode, ProgressReporter

        reporter = ProgressReporter(OutputMode.DETERMINISTIC)

        with pytest.raises(ValueError), reporter.status("Exploding"):
            raise ValueError("boom")

    def test_create_reporter_falls_back_when_rich_is_unavailable(self, monkeypatch):
        """Test missing Rich degrades to deterministic output instead of crashing."""
        import lazy_email.cli_progress as cli_progress

        monkeypatch.setattr(cli_progress, "Console", None)
        monkeypatch.setattr(cli_progress.sys.stdout, "isatty", lambda: True)

        reporter = cli_progress.create_progress_reporter()

        assert reporter.mode == cli_progress.OutputMode.DETERMINISTIC


class TestProcessEmailsProgressBehavior:
    """Tests for process_emails progress behavior and processing semantics."""

    @staticmethod
    def _email(message_id: str):
        from lazy_email.models.email import EmailMessage

        return EmailMessage(
            message_id=message_id,
            subject=f"Subject {message_id}",
            content="content",
            date_sent=datetime(2025, 1, 1),
            email_link=f"https://mail.example/{message_id}",
            sender="sender@example.com",
        )

    @staticmethod
    def _application(company: str = "Acme", role: str = "Engineer"):
        from lazy_email.models.email import ApplicationStatus, JobApplication

        return JobApplication(
            company_name=company,
            role=role,
            status=ApplicationStatus.SUBMITTED,
            date_submitted="2025-01-01",
            email_link="https://mail.example/msg",
        )

    def test_legacy_output_preserves_step_and_per_email_messages(self, capsys):
        """Test legacy output keeps the old step and per-email processing UX."""
        from lazy_email.cli_progress import ProgressReporter
        from lazy_email.main import process_emails

        email = self._email("msg1")
        app = self._application()
        gmail_client = MagicMock()
        gmail_client.fetch_messages.return_value = [email]
        extractor = MagicMock()
        extractor.extract_from_email.return_value = app
        sheets_client = MagicMock()
        sheets_client.get_existing_applications.return_value = {}
        sheets_client.append_rows.return_value = 1
        state_manager = MagicMock()
        state_manager.get_unprocessed.return_value = ["msg1"]

        process_emails(
            gmail_client=gmail_client,
            extractor=extractor,
            sheets_client=sheets_client,
            state_manager=state_manager,
            since_date="2025-01-01",
            until_date=None,
            max_emails=None,
            dry_run=False,
            reporter=ProgressReporter.legacy(),
        )

        captured = capsys.readouterr()
        assert "[2/4] Fetching emails since 2025-01-01" in captured.out
        assert "[1/1] Processing..." in captured.out
        assert "✓ Acme - Engineer" in captured.out
        state_manager.mark_processed.assert_called_once_with("msg1")
        sheets_client.append_rows.assert_called_once_with([app])
        state_manager.mark_written.assert_called_once_with(1)
        state_manager.save.assert_called_once()

    def test_dry_run_preserves_preview_and_skips_sheet_writes(self, capsys):
        """Test dry-run keeps stable developer output and avoids sheet writes/save."""
        from lazy_email.cli_progress import OutputMode, ProgressReporter
        from lazy_email.main import process_emails

        email = self._email("msg1")
        app = self._application("ExampleCo", "Backend Engineer")
        gmail_client = MagicMock()
        gmail_client.fetch_messages.return_value = [email]
        extractor = MagicMock()
        extractor.extract_from_email.return_value = app
        state_manager = MagicMock()

        process_emails(
            gmail_client=gmail_client,
            extractor=extractor,
            sheets_client=None,
            state_manager=state_manager,
            since_date="2025-01-01",
            until_date=None,
            max_emails=None,
            dry_run=True,
            reporter=ProgressReporter(OutputMode.MODERN),
        )

        captured = capsys.readouterr()
        assert "[2/4] Fetching emails since 2025-01-01" in captured.out
        assert "Processing all emails (dry-run ignores state)" in captured.out
        assert "[1/1] Processing..." in captured.out
        assert "Preview (dry-run)" in captured.out
        assert "ExampleCo" in captured.out
        assert "(No data was written to Google Sheets)" in captured.out
        state_manager.save.assert_not_called()
        state_manager.mark_written.assert_not_called()

    def test_modern_progress_preserves_non_dry_run_processing_semantics(self):
        """Test modern progress wrapping does not change core call conditions."""
        from lazy_email.cli_progress import OutputMode, ProgressReporter
        from lazy_email.main import process_emails

        email = self._email("msg1")
        app = self._application()
        gmail_client = MagicMock()
        gmail_client.fetch_messages.return_value = [email]
        extractor = MagicMock()
        extractor.extract_from_email.return_value = app
        sheets_client = MagicMock()
        sheets_client.get_existing_applications.return_value = {}
        sheets_client.append_rows.return_value = 1
        state_manager = MagicMock()
        state_manager.get_unprocessed.return_value = ["msg1"]

        process_emails(
            gmail_client=gmail_client,
            extractor=extractor,
            sheets_client=sheets_client,
            state_manager=state_manager,
            since_date="2025-01-01",
            until_date=None,
            max_emails=None,
            dry_run=False,
            reporter=ProgressReporter(OutputMode.DETERMINISTIC),
        )

        gmail_client.fetch_messages.assert_called_once_with(
            since_date="2025-01-01",
            until_date=None,
            max_results=None,
        )
        extractor.extract_from_email.assert_called_once_with(email)
        state_manager.mark_processed.assert_called_once_with("msg1")
        sheets_client.get_existing_applications.assert_called_once_with()
        sheets_client.append_rows.assert_called_once_with([app])
        state_manager.mark_written.assert_called_once_with(1)
        state_manager.save.assert_called_once_with()
