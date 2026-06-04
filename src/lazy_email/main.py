"""CLI entry point for lazy-email-to-spreadsheet.

This module provides the command-line interface for processing Gmail emails,
extracting job application data using a local LLM, and writing to Google Sheets.
"""

import argparse
import logging
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from typing import NoReturn

from lazy_email.auth.google_auth import (
    AuthenticationError,
    get_credentials,
    verify_authentication,
)
from lazy_email.cli_progress import ProgressReporter, create_progress_reporter
from lazy_email.config import get_settings, update_settings
from lazy_email.gmail.client import GmailClient, GmailClientError
from lazy_email.llm.extractor import JobApplicationExtractor, LLMExtractorError
from lazy_email.models.email import JobApplication
from lazy_email.sheets.client import SheetsClient, SheetsClientError
from lazy_email.state import StateManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class GracefulExit(Exception):
    """Raised when user requests graceful exit (Ctrl+C)."""

    pass


def setup_signal_handlers(state_manager: StateManager) -> None:
    """Set up signal handlers for graceful shutdown.

    Args:
        state_manager: StateManager to save on shutdown.
    """

    def handle_signal(_signum: int, _frame: object) -> NoReturn:
        print("\n\n⚠ Interrupt received. Saving progress...")
        state_manager.save()
        print("✓ Progress saved. You can resume by running the command again.")
        print(f"\n{state_manager.get_progress_summary()}")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)


def validate_date(date_str: str) -> str:
    """Validate date string is in YYYY-MM-DD format.

    Args:
        date_str: Date string to validate.

    Returns:
        Validated date string.

    Raises:
        argparse.ArgumentTypeError: If date format is invalid.
    """
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return date_str
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid date format: '{date_str}'. Use YYYY-MM-DD (e.g., 2025-12-01)"
        ) from None


def extract_spreadsheet_id(value: str) -> str:
    """Extract spreadsheet ID from URL or return as-is if already an ID.

    Args:
        value: Either a full Google Sheets URL or just the spreadsheet ID.

    Returns:
        The extracted spreadsheet ID.

    Raises:
        argparse.ArgumentTypeError: If unable to extract ID from URL.
    """
    # If it looks like a URL, extract the ID
    if "docs.google.com" in value or "spreadsheets" in value:
        # Pattern: /d/{spreadsheet_id}/
        match = re.search(r"/d/([a-zA-Z0-9-_]+)", value)
        if match:
            return match.group(1)
        raise argparse.ArgumentTypeError(
            f"Could not extract spreadsheet ID from URL: {value}"
        )
    # Otherwise assume it's already an ID
    return value


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for CLI.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        prog="lazy-email",
        description="Extract job application data from Gmail and populate Google Sheets.",
        epilog="Example: lazy-email --since 2025-01-01 --spreadsheet-id YOUR_ID --sheet-name 'Applications'",
    )

    parser.add_argument(
        "--since",
        type=validate_date,
        required=True,
        help="Process emails since this date (YYYY-MM-DD format)",
    )

    parser.add_argument(
        "--until",
        type=validate_date,
        default=None,
        help="Process emails until this date (YYYY-MM-DD format, exclusive)",
    )

    parser.add_argument(
        "--spreadsheet-id",
        type=extract_spreadsheet_id,
        help="Google Sheets spreadsheet ID or full URL (can also paste the URL)",
    )

    parser.add_argument(
        "--sheet-name",
        type=str,
        default=None,
        help="Name of the sheet tab to write to (default: Sheet1)",
    )

    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Ollama model to use (default: qwen2.5:3b)",
    )

    parser.add_argument(
        "--max-emails",
        type=int,
        default=None,
        help="Maximum number of emails to process (default: unlimited)",
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset processing state and start fresh",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview extracted data without writing to Google Sheets",
    )

    parser.add_argument(
        "--legacy-output",
        action="store_true",
        help="Use the previous print-based output instead of progress bars",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser


def print_banner() -> None:
    """Print application banner."""
    print("\n" + "=" * 60)
    print("  📧 Lazy Email to Spreadsheet")
    print("  Extract job applications from Gmail → Google Sheets")
    print("=" * 60 + "\n")


def print_step(step: int, total: int, message: str) -> None:
    """Print a step progress message.

    Args:
        step: Current step number.
        total: Total number of steps.
        message: Step description.
    """
    print(f"\n[{step}/{total}] {message}")
    print("-" * 50)


def check_ollama_running() -> bool:
    """Check if Ollama server is running.

    Returns:
        True if Ollama is responding, False otherwise.
    """
    import urllib.error
    import urllib.request

    settings = get_settings()
    try:
        req = urllib.request.Request(f"{settings.ollama_host}/api/tags")
        with urllib.request.urlopen(req, timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, ConnectionRefusedError):
        return False


def start_ollama(reporter: ProgressReporter | None = None) -> bool:
    """Start Ollama server in the background.

    Returns:
        True if Ollama started successfully, False otherwise.
    """
    reporter = reporter or ProgressReporter.legacy()
    if reporter.uses_legacy_output:
        print("  Starting Ollama...", end=" ", flush=True)
        try:
            # Start ollama serve in background
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            # Wait for it to be ready
            for _ in range(10):  # Wait up to 5 seconds
                time.sleep(0.5)
                if check_ollama_running():
                    print("✓")
                    return True
            print("✗ (timeout)")
            return False
        except FileNotFoundError:
            print("✗")
            print("\n  Ollama is not installed. Please install it from https://ollama.ai")
            return False
        except Exception as e:
            print(f"✗ ({e})")
            return False

    try:
        with reporter.status("Starting Ollama"):
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            for _ in range(10):  # Wait up to 5 seconds
                time.sleep(0.5)
                if check_ollama_running():
                    reporter.success("Ollama started")
                    return True
        reporter.failure("Ollama start timed out")
        return False
    except FileNotFoundError:
        reporter.failure("Ollama is not installed")
        print("\n  Ollama is not installed. Please install it from https://ollama.ai")
        return False
    except Exception as e:
        reporter.failure(f"Could not start Ollama ({e})")
        return False


def prompt_start_ollama(reporter: ProgressReporter | None = None) -> bool:
    """Prompt user to start Ollama if not running.

    Returns:
        True if Ollama is running (or was started), False otherwise.
    """
    if check_ollama_running():
        return True

    print("  ⚠ Ollama is not running.")
    response = input("  Start Ollama automatically? (y/n): ").strip().lower()

    if response in ("y", "yes"):
        return start_ollama(reporter)
    else:
        print("  Please start Ollama manually with: ollama serve")
        return False


def check_prerequisites(
    _state_manager: StateManager,
    dry_run: bool = False,
    reporter: ProgressReporter | None = None,
) -> bool:
    """Check all prerequisites are met before processing.

    Args:
        state_manager: StateManager for resume detection.
        dry_run: If True, skip Google Sheets connection check.
        reporter: Progress reporter controlling modern vs legacy output.

    Returns:
        True if all prerequisites pass, False otherwise.
    """
    reporter = reporter or ProgressReporter.legacy()

    if reporter.uses_legacy_output:
        print_step(1, 4, "Checking prerequisites...")

        # Check Google authentication
        print("  • Verifying Google authentication...", end=" ", flush=True)
        try:
            get_credentials()
            print("✓")
        except AuthenticationError as e:
            print("✗")
            print(f"\n{e}")
            return False

        # Verify Gmail access
        print("  • Testing Gmail access...", end=" ", flush=True)
        if verify_authentication():
            print("✓")
        else:
            print("✗")
            print("\nFailed to verify Gmail access. Please re-authenticate.")
            return False

        # Check Sheets connection (skip in dry-run mode)
        if dry_run:
            print("  • Skipping Google Sheets check (dry-run mode)")
        else:
            print("  • Verifying Google Sheets access...", end=" ", flush=True)
            try:
                sheets_client = SheetsClient()
                if sheets_client.verify_connection():
                    pass  # Message already printed by verify_connection
                else:
                    return False
            except SheetsClientError as e:
                print("✗")
                print(f"\nSheets error: {e}")
                return False

        # Check Ollama is running (with auto-start prompt)
        print("  • Checking Ollama...", end=" ", flush=True)
        if check_ollama_running():
            print("✓ (running)")
        else:
            print("")  # newline before prompt
            if not prompt_start_ollama(reporter):
                return False

        # Check LLM model
        print("  • Verifying LLM model...", end=" ", flush=True)
        try:
            extractor = JobApplicationExtractor()
            if extractor.verify_connection():
                print("✓")
            else:
                return False
        except LLMExtractorError as e:
            print("✗")
            print(f"\nLLM error: {e}")
            return False

        return True

    reporter.step(1, 4, "Checking prerequisites...")

    try:
        with reporter.status("Verifying Google authentication"):
            get_credentials()
        reporter.success("Google authentication verified")
    except AuthenticationError as e:
        reporter.failure("Google authentication failed")
        print(f"\n{e}")
        return False

    with reporter.status("Testing Gmail access"):
        gmail_ok = verify_authentication()
    if gmail_ok:
        reporter.success("Gmail access verified")
    else:
        reporter.failure("Failed to verify Gmail access")
        print("\nFailed to verify Gmail access. Please re-authenticate.")
        return False

    if dry_run:
        reporter.message("  • Skipping Google Sheets check (dry-run mode)")
    else:
        try:
            with reporter.status("Verifying Google Sheets access"):
                sheets_client = SheetsClient()
                sheets_ok = sheets_client.verify_connection()
            if not sheets_ok:
                return False
            reporter.success("Google Sheets access verified")
        except SheetsClientError as e:
            reporter.failure("Google Sheets access failed")
            print(f"\nSheets error: {e}")
            return False

    with reporter.status("Checking Ollama"):
        ollama_running = check_ollama_running()
    if ollama_running:
        reporter.success("Ollama is running")
    elif not prompt_start_ollama(reporter):
        return False

    try:
        with reporter.status("Verifying LLM model"):
            extractor = JobApplicationExtractor()
            model_ok = extractor.verify_connection()
        if model_ok:
            reporter.success("LLM model verified")
        else:
            return False
    except LLMExtractorError as e:
        reporter.failure("LLM model verification failed")
        print(f"\nLLM error: {e}")
        return False

    return True

def handle_resume_prompt(state_manager: StateManager, since_date: str) -> bool:
    """Handle resume prompt for previous session.

    Args:
        state_manager: StateManager with loaded state.
        since_date: The --since date from current invocation.

    Returns:
        True to continue (resume or fresh start), False to abort.
    """
    if not state_manager.has_previous_session():
        return True

    # Check if since_date matches
    if state_manager.state.since_date and state_manager.state.since_date != since_date:
        print(f"\n⚠ Previous session used --since {state_manager.state.since_date}")
        print(f"  Current command uses --since {since_date}")
        print("\nOptions:")
        print("  1. Continue with current date (previous progress will be kept)")
        print("  2. Reset and start fresh with new date")
        print("  3. Abort")

        while True:
            choice = input("\nChoice (1/2/3): ").strip()
            if choice == "1":
                state_manager.set_since_date(since_date)
                return True
            elif choice == "2":
                state_manager.reset()
                state_manager.set_since_date(since_date)
                return True
            elif choice == "3":
                return False
            print("Invalid choice. Please enter 1, 2, or 3.")

    # Same date - offer to resume
    prompt = state_manager.get_resume_prompt()
    print(prompt, end="", flush=True)

    while True:
        response = input().strip().lower()
        if response in ("y", "yes"):
            print("✓ Resuming previous session")
            return True
        elif response in ("n", "no"):
            print("Starting fresh...")
            state_manager.reset()
            state_manager.set_since_date(since_date)
            return True
        print("Please enter 'y' or 'n': ", end="", flush=True)


def process_emails(
    gmail_client: GmailClient,
    extractor: JobApplicationExtractor,
    sheets_client: SheetsClient | None,
    state_manager: StateManager,
    since_date: str,
    until_date: str | None,
    max_emails: int | None,
    dry_run: bool = False,
    reporter: ProgressReporter | None = None,
) -> None:
    """Main processing loop: fetch, extract, write.

    Args:
        gmail_client: Gmail API client.
        extractor: LLM extractor.
        sheets_client: Sheets API client (None in dry-run mode).
        state_manager: State manager for tracking.
        since_date: Start date filter for emails (inclusive).
        until_date: End date filter for emails (exclusive).
        max_emails: Maximum emails to process.
        dry_run: If True, print preview instead of writing to Sheets.
        reporter: Progress reporter controlling modern vs legacy output.
    """
    reporter = reporter or ProgressReporter.legacy()
    use_legacy_output = reporter.uses_legacy_output or dry_run

    date_range = f"since {since_date}"
    if until_date:
        date_range += f" until {until_date}"

    if use_legacy_output:
        print_step(2, 4, f"Fetching emails {date_range}...")
    else:
        reporter.step(2, 4, f"Fetching emails {date_range}...")

    # Fetch emails
    try:
        if use_legacy_output:
            emails = gmail_client.fetch_messages(
                since_date=since_date,
                until_date=until_date,
                max_results=max_emails,
            )
        else:
            with reporter.status("Fetching emails from Gmail"):
                emails = gmail_client.fetch_messages(
                    since_date=since_date,
                    until_date=until_date,
                    max_results=max_emails,
                )
        print(f"  Found {len(emails)} emails in primary inbox")
    except GmailClientError as e:
        print(f"  ✗ Failed to fetch emails: {e}")
        return

    if not emails:
        print("  No emails to process.")
        return

    # Filter out already processed (skip in dry-run mode)
    if dry_run:
        emails_to_process = emails
        print("  Processing all emails (dry-run ignores state)...")
    else:
        email_ids = [e.message_id for e in emails]
        unprocessed_ids = set(state_manager.get_unprocessed(email_ids))
        emails_to_process = [e for e in emails if e.message_id in unprocessed_ids]

        skipped = len(emails) - len(emails_to_process)
        if skipped > 0:
            print(f"  Skipping {skipped} already processed emails")

        if not emails_to_process:
            print("  All emails already processed.")
            return

    print(f"  Processing {len(emails_to_process)} new emails...")

    if use_legacy_output:
        print_step(3, 4, "Extracting job application data...")
    else:
        reporter.step(3, 4, "Extracting job application data...")

    # Process each email
    applications: list[JobApplication] = []
    email_iterator = enumerate(emails_to_process, 1)
    if not use_legacy_output:
        email_iterator = enumerate(
            reporter.track(
                emails_to_process,
                description="Transferring job applications",
                total=len(emails_to_process),
            ),
            1,
        )

    for i, email in email_iterator:
        try:
            if use_legacy_output:
                print(f"  [{i}/{len(emails_to_process)}] Processing...", end=" ", flush=True)

            # Extract data
            application = extractor.extract_from_email(email)
            applications.append(application)

            # Mark as processed (skip in dry-run mode)
            if not dry_run:
                state_manager.mark_processed(email.message_id)

            if use_legacy_output:
                print(f"✓ {application.company_name} - {application.role}")

        except LLMExtractorError as e:
            print(f"✗ Extraction failed: {e}")
            # Still mark as processed to avoid retry loops
            state_manager.mark_processed(email.message_id)

    if not use_legacy_output:
        reporter.success(f"Extracted {len(applications)} applications")

    if use_legacy_output:
        print_step(4, 4, "Writing to Google Sheets..." if not dry_run else "Preview (dry-run)...")
    else:
        reporter.step(4, 4, "Writing to Google Sheets...")

    if not applications:
        print("  No applications to write.")
        return

    # Dry-run: print preview table and return without writing
    if dry_run:
        print(f"\n  {'#':<4} {'Company Name':<35} {'Role':<40} {'Status'}")
        print(f"  {'─'*4} {'─'*35} {'─'*40} {'─'*30}")
        for i, app in enumerate(applications, 1):
            company = app.company_name[:33] + ".." if len(app.company_name) > 35 else app.company_name
            role = app.role[:38] + ".." if len(app.role) > 40 else app.role
            print(f"  {i:<4} {company:<35} {role:<40} {app.status.value}")
        print(f"\n  Total: {len(applications)} applications extracted")
        print("  (No data was written to Google Sheets)")
        return

    # Import deduplication helpers
    from lazy_email.models.email import normalize_company_name, normalize_role, should_update_status

    # Fetch existing applications for deduplication
    if use_legacy_output:
        print("  Loading existing applications for deduplication...", end=" ", flush=True)
        try:
            existing_apps = sheets_client.get_existing_applications()
            print(f"✓ ({len(existing_apps)} existing)")
        except SheetsClientError as e:
            print(f"✗ ({e})")
            existing_apps = {}
    else:
        try:
            with reporter.status("Loading existing applications for deduplication"):
                existing_apps = sheets_client.get_existing_applications()
            reporter.success(f"Loaded {len(existing_apps)} existing applications")
        except SheetsClientError as e:
            reporter.failure(f"Could not load existing applications ({e})")
            existing_apps = {}

    # Separate into new applications vs updates
    new_applications: list[JobApplication] = []
    updates_count = 0
    skipped_count = 0

    for app in applications:
        key = (normalize_company_name(app.company_name), normalize_role(app.role))

        if key in existing_apps:
            row_idx, current_status, _ = existing_apps[key]
            # row_idx == 0 means it's an in-batch duplicate (not yet written to sheet)
            if row_idx == 0:
                # Skip in-batch duplicates - we'll just keep the first one
                skipped_count += 1
                continue
            if should_update_status(current_status, app.status):
                # Update existing row with new status and email link
                try:
                    sheets_client.update_row(row_idx, app.status, app.email_link)
                    updates_count += 1
                    print(f"  ↻ Updated: {app.company_name} - {app.role} ({current_status.value} → {app.status.value})")
                except SheetsClientError as e:
                    print(f"  ✗ Failed to update {app.company_name}: {e}")
            else:
                skipped_count += 1
        else:
            new_applications.append(app)
            # Add to existing_apps to handle duplicates within this batch (row_idx=0 marks as in-batch)
            existing_apps[key] = (0, app.status, app.email_link)

    if skipped_count > 0:
        print(f"  ⊘ Skipped {skipped_count} duplicates (no status change)")

    # Write only new applications
    if new_applications:
        try:
            if use_legacy_output:
                written = sheets_client.append_rows(new_applications)
            else:
                with reporter.status("Adding new rows to Google Sheets"):
                    written = sheets_client.append_rows(new_applications)
            state_manager.mark_written(written)
            print(f"  ✓ Added {written} new rows")
        except SheetsClientError as e:
            print(f"  ✗ Failed to write to sheet: {e}")
    else:
        print("  No new applications to add.")

    if updates_count > 0:
        print(f"  ✓ Updated {updates_count} existing rows")

    # Final save (skip in dry-run so the same emails can be re-processed)
    if not dry_run:
        state_manager.save()

def main() -> int:
    """Main entry point for CLI.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    parser = create_parser()
    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    reporter = create_progress_reporter(
        legacy_output=args.legacy_output,
        dry_run=args.dry_run,
    )

    print_banner()

    # Get current settings and check for spreadsheet ID
    settings = get_settings()
    spreadsheet_id = args.spreadsheet_id or settings.spreadsheet_id

    # Prompt for spreadsheet ID if not provided (skip in dry-run mode)
    if not spreadsheet_id and not args.dry_run:
        print("📋 No spreadsheet ID configured.")
        print("   Paste your Google Sheets URL or spreadsheet ID below.")
        print("   (The ID is the long string in the URL between /d/ and /edit)\n")
        while True:
            user_input = input("Spreadsheet URL or ID: ").strip()
            if user_input:
                try:
                    spreadsheet_id = extract_spreadsheet_id(user_input)
                    print(f"   ✓ Using spreadsheet ID: {spreadsheet_id}\n")
                    break
                except argparse.ArgumentTypeError as e:
                    print(f"   ✗ {e}")
            else:
                print("   Please enter a valid spreadsheet URL or ID.")

    # Apply CLI overrides to settings
    update_settings(
        spreadsheet_id=spreadsheet_id,
        sheet_name=args.sheet_name,
        ollama_model=args.model,
    )

    # Initialize state manager
    state_manager = StateManager()
    state_manager.load()

    # Set up signal handlers for graceful exit
    setup_signal_handlers(state_manager)

    # Handle --reset flag
    if args.reset:
        print("Resetting processing state...")
        state_manager.reset()
        print("✓ State reset complete\n")

    # Set since date
    state_manager.set_since_date(args.since)

    # Handle resume prompt (skip in dry-run mode)
    if not args.dry_run and not handle_resume_prompt(state_manager, args.since):
        print("Aborted.")
        return 0

    if args.dry_run:
        print("Dry-run mode: results will be previewed, nothing written to Sheets\n")

    # Check prerequisites
    if not check_prerequisites(state_manager, dry_run=args.dry_run, reporter=reporter):
        print("\n✗ Prerequisites check failed. Please fix the issues above.")
        return 1

    # Initialize clients
    try:
        gmail_client = GmailClient()
        extractor = JobApplicationExtractor()
        sheets_client = None if args.dry_run else SheetsClient()
    except Exception as e:
        print(f"\n✗ Failed to initialize: {e}")
        return 1

    # Process emails
    try:
        process_emails(
            gmail_client=gmail_client,
            extractor=extractor,
            sheets_client=sheets_client,
            state_manager=state_manager,
            since_date=args.since,
            until_date=args.until,
            max_emails=args.max_emails,
            dry_run=args.dry_run,
            reporter=reporter,
        )
    except Exception as e:
        logger.exception("Unexpected error during processing")
        print(f"\n✗ Error: {e}")
        state_manager.save()
        return 1

    # Print summary
    print("\n" + "=" * 60)
    print("  ✓ Processing complete!")
    print("=" * 60)
    if not args.dry_run:
        print(f"\n{state_manager.get_progress_summary()}")

    # Rename spreadsheet with current date (skip in dry-run mode)
    if not args.dry_run:
        try:
            if reporter.uses_legacy_output:
                sheets_client.rename_spreadsheet()
            else:
                with reporter.status("Renaming spreadsheet"):
                    sheets_client.rename_spreadsheet()
            print("\n✓ Spreadsheet renamed with today's date.")
        except Exception as e:
            logger.warning(f"Could not rename spreadsheet: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
