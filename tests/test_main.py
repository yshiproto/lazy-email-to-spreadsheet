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

from lazy_email.main import (
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
        """Test default max-emails value."""
        parser = create_parser()
        args = parser.parse_args(["--since", "2025-01-01"])
        assert args.max_emails == 100

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
    def test_resume_same_date_yes(self, mock_input):
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
    def test_resume_same_date_no(self, mock_input):
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
    def test_different_date_abort(self, mock_input):
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
