"""Google Sheets API client module with batching.

This module provides a high-level interface to the Google Sheets API for
appending job application data with automatic batching to respect rate limits.
"""

import logging
import time
from datetime import datetime
from typing import Optional

from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from lazy_email.config import get_settings
from lazy_email.auth.google_auth import get_sheets_service
from lazy_email.models.email import ApplicationStatus, JobApplication

logger = logging.getLogger(__name__)


class SheetsClientError(Exception):
    """Raised when Google Sheets API operations fail."""

    pass


class SheetsClient:
    """Google Sheets API client with batching and rate limiting.

    This client provides methods to append job application data to a
    Google Sheet with automatic batching to stay within API rate limits
    (60 writes/minute).

    Spreadsheet column structure:
    - Column A: Company Name
    - Column B: Application Status (dropdown)
    - Column C: Role
    - Column D: Date Submitted
    - Column E: Link to Job Email

    Attributes:
        service: Authenticated Sheets API service resource.
        spreadsheet_id: Google Sheets spreadsheet ID.
        sheet_name: Name of the sheet tab to write to.
        batch_size: Number of rows to batch before writing.
    """

    def __init__(
        self,
        service: Optional[Resource] = None,
        spreadsheet_id: Optional[str] = None,
        sheet_name: Optional[str] = None,
        batch_size: Optional[int] = None,
    ) -> None:
        """Initialize Sheets client.

        Args:
            service: Optional authenticated Sheets service. If not provided,
                    will create one using get_sheets_service().
            spreadsheet_id: Google Sheets ID. Defaults to settings.spreadsheet_id.
            sheet_name: Sheet tab name. Defaults to settings.sheet_name.
            batch_size: Rows per batch. Defaults to settings.sheets_batch_size.
        """
        settings = get_settings()

        self.service = service or get_sheets_service()
        self.spreadsheet_id = spreadsheet_id or settings.spreadsheet_id
        self.sheet_name = sheet_name or settings.sheet_name
        self.batch_size = batch_size or settings.sheets_batch_size

        # Track write timing for rate limiting
        self._last_write_time: float = 0
        self._writes_this_minute: int = 0
        self._minute_start_time: float = 0

    def _job_to_row(self, job: JobApplication) -> list[str]:
        """Convert JobApplication to spreadsheet row values.

        Args:
            job: JobApplication to convert.

        Returns:
            List of cell values in column order:
            [Company Name, Application Status, Role, Date Submitted, Email Link]
        """
        return [
            job.company_name,
            job.status.value,  # Use enum value for dropdown matching
            job.role,
            job.date_submitted,
            job.email_link,
        ]

    def _wait_for_rate_limit(self) -> None:
        """Wait if necessary to respect rate limits.

        Google Sheets API allows 60 writes/minute per user.
        This method tracks writes and adds delays when approaching the limit.
        """
        current_time = time.time()

        # Reset counter if a minute has passed
        if current_time - self._minute_start_time >= 60:
            self._writes_this_minute = 0
            self._minute_start_time = current_time

        # If we've hit the limit, wait until the minute resets
        if self._writes_this_minute >= 50:  # Leave buffer of 10
            wait_time = 60 - (current_time - self._minute_start_time)
            if wait_time > 0:
                logger.info(f"Rate limit approaching, waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
                self._writes_this_minute = 0
                self._minute_start_time = time.time()

        # Minimum delay between writes (1 second for safety)
        time_since_last = current_time - self._last_write_time
        if time_since_last < 1.0:
            time.sleep(1.0 - time_since_last)

    @retry(
        retry=retry_if_exception_type(HttpError),
        wait=wait_exponential(multiplier=1, min=1, max=64),
        stop=stop_after_attempt(5),
    )
    def _append_rows_with_retry(self, values: list[list[str]]) -> dict:
        """Append rows to sheet with rate limit retry.

        Args:
            values: List of row values to append.

        Returns:
            API response dictionary.

        Raises:
            SheetsClientError: If API call fails after retries.
        """
        try:
            range_name = f"{self.sheet_name}!A:E"
            body = {"values": values}

            result = (
                self.service.spreadsheets()
                .values()
                .append(
                    spreadsheetId=self.spreadsheet_id,
                    range=range_name,
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body=body,
                )
                .execute()
            )

            # Update rate limit tracking
            self._last_write_time = time.time()
            self._writes_this_minute += 1

            return result
        except HttpError as e:
            if e.resp.status in [429, 500, 503]:
                # Retry on rate limit or server errors
                raise
            raise SheetsClientError(f"Failed to append rows: {e}") from e

    def append_row(self, job: JobApplication) -> None:
        """Append a single job application row to the sheet.

        Args:
            job: JobApplication to append.

        Raises:
            SheetsClientError: If append fails.
        """
        self._wait_for_rate_limit()
        row = self._job_to_row(job)
        self._append_rows_with_retry([row])
        logger.info(f"Appended row: {job.company_name} - {job.role}")

    def append_rows(self, jobs: list[JobApplication]) -> int:
        """Append multiple job applications to the sheet.

        Jobs are batched to minimize API calls while respecting rate limits.

        Args:
            jobs: List of JobApplication objects to append.

        Returns:
            Number of rows successfully appended.

        Raises:
            SheetsClientError: If append fails.
        """
        if not jobs:
            return 0

        total_appended = 0

        # Process in batches
        for i in range(0, len(jobs), self.batch_size):
            batch = jobs[i : i + self.batch_size]
            rows = [self._job_to_row(job) for job in batch]

            self._wait_for_rate_limit()

            try:
                self._append_rows_with_retry(rows)
                total_appended += len(rows)
                logger.info(f"Appended batch of {len(rows)} rows ({total_appended}/{len(jobs)})")
            except SheetsClientError as e:
                logger.error(f"Failed to append batch: {e}")
                raise

        return total_appended

    def get_existing_email_links(self) -> set[str]:
        """Get all existing email links from the sheet.

        Useful for duplicate detection (future enhancement).

        Returns:
            Set of email links already in the sheet.

        Raises:
            SheetsClientError: If read fails.
        """
        try:
            range_name = f"{self.sheet_name}!E:E"  # Email link column
            result = (
                self.service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=self.spreadsheet_id,
                    range=range_name,
                )
                .execute()
            )

            values = result.get("values", [])
            # Skip header row if present, flatten to set
            links = {row[0] for row in values[1:] if row}
            return links
        except HttpError as e:
            raise SheetsClientError(f"Failed to read email links: {e}") from e

    def get_existing_applications(self) -> dict[tuple[str, str], tuple[int, ApplicationStatus, str]]:
        """Get all existing applications from the sheet for deduplication.

        Returns:
            Dict mapping (normalized_company, normalized_role) to (row_index, status, email_link).

        Raises:
            SheetsClientError: If read fails.
        """
        from lazy_email.models.email import normalize_company_name, normalize_role

        try:
            range_name = f"{self.sheet_name}!A:E"
            result = (
                self.service.spreadsheets()
                .values()
                .get(spreadsheetId=self.spreadsheet_id, range=range_name)
                .execute()
            )

            values = result.get("values", [])
            existing: dict[tuple[str, str], tuple[int, ApplicationStatus, str]] = {}

            # Skip header row, process data rows
            for i, row in enumerate(values[1:], start=2):  # Row 2 is first data row
                if len(row) >= 3:
                    company = row[0] if len(row) > 0 else ""
                    status_str = row[1] if len(row) > 1 else "N/A"
                    role = row[2] if len(row) > 2 else ""
                    email_link = row[4] if len(row) > 4 else ""

                    # Parse status
                    try:
                        status = ApplicationStatus(status_str)
                    except ValueError:
                        status = ApplicationStatus.NA

                    # Create normalized key
                    key = (normalize_company_name(company), normalize_role(role))
                    if key[0] and key[1]:  # Only add if both company and role exist
                        existing[key] = (i, status, email_link)

            return existing
        except HttpError as e:
            raise SheetsClientError(f"Failed to read existing applications: {e}") from e

    def update_row(self, row_index: int, status: ApplicationStatus, email_link: str) -> None:
        """Update an existing row's status and email link.

        Args:
            row_index: The 1-based row index in the sheet.
            status: New application status.
            email_link: New email link (to the most recent email).

        Raises:
            SheetsClientError: If update fails.
        """
        try:
            self._wait_for_rate_limit()

            # Update status (column B) and email link (column E)
            range_name = f"{self.sheet_name}!B{row_index}"
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption="USER_ENTERED",
                body={"values": [[status.value]]},
            ).execute()

            range_name = f"{self.sheet_name}!E{row_index}"
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption="USER_ENTERED",
                body={"values": [[email_link]]},
            ).execute()

            self._last_write_time = time.time()
            self._writes_this_minute += 2

            logger.info(f"Updated row {row_index}: status={status.value}")
        except HttpError as e:
            raise SheetsClientError(f"Failed to update row {row_index}: {e}") from e

    def verify_connection(self) -> bool:
        """Verify connection to the spreadsheet.

        Attempts to read the sheet to confirm access.

        Returns:
            True if connection is successful, False otherwise.
        """
        if not self.spreadsheet_id:
            print("\n⚠ SPREADSHEET_ID not configured.")
            print("Please set SPREADSHEET_ID in your .env file.")
            print("You can find it in the Google Sheets URL:")
            print("https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")
            return False

        try:
            # Try to read sheet metadata
            result = (
                self.service.spreadsheets()
                .get(spreadsheetId=self.spreadsheet_id)
                .execute()
            )
            title = result.get("properties", {}).get("title", "Unknown")
            print(f"✓ Connected to spreadsheet: {title}")

            # Verify sheet tab exists
            sheets = result.get("sheets", [])
            sheet_names = [s.get("properties", {}).get("title") for s in sheets]

            if self.sheet_name not in sheet_names:
                print(f"⚠ Sheet tab '{self.sheet_name}' not found.")
                print(f"Available tabs: {', '.join(sheet_names)}")
                return False

            print(f"✓ Found sheet tab: {self.sheet_name}")
            return True
        except HttpError as e:
            if e.resp.status == 404:
                print(f"\n⚠ Spreadsheet not found: {self.spreadsheet_id}")
                print("Please check your SPREADSHEET_ID is correct.")
            elif e.resp.status == 403:
                print("\n⚠ Access denied to spreadsheet.")
                print("Please ensure you have edit access to the spreadsheet.")
            else:
                print(f"\n⚠ Failed to connect to spreadsheet: {e}")
            return False

    def get_row_count(self) -> int:
        """Get the number of data rows in the sheet.

        Returns:
            Number of rows (excluding header).

        Raises:
            SheetsClientError: If read fails.
        """
        try:
            range_name = f"{self.sheet_name}!A:A"
            result = (
                self.service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=self.spreadsheet_id,
                    range=range_name,
                )
                .execute()
            )

            values = result.get("values", [])
            # Subtract 1 for header row
            return max(0, len(values) - 1)
        except HttpError as e:
            raise SheetsClientError(f"Failed to get row count: {e}") from e

    def rename_spreadsheet(self, date_suffix: Optional[str] = None) -> None:
        """Rename the spreadsheet by appending a date suffix to the title.

        Args:
            date_suffix: Optional date string to append. Defaults to current date in MM/DD/YYYY format.

        Raises:
            SheetsClientError: If rename fails.
        """
        if date_suffix is None:
            date_suffix = datetime.now().strftime("%m/%d/%Y")

        try:
            # Get current title
            result = (
                self.service.spreadsheets()
                .get(spreadsheetId=self.spreadsheet_id)
                .execute()
            )
            current_title = result.get("properties", {}).get("title", "Job Applications")

            # Append date suffix (avoid duplicating if already has a date)
            # Check if title already ends with a date pattern
            import re
            if re.search(r" - \d{2}/\d{2}/\d{4}$", current_title):
                # Replace existing date
                new_title = re.sub(r" - \d{2}/\d{2}/\d{4}$", f" - {date_suffix}", current_title)
            else:
                new_title = f"{current_title} - {date_suffix}"

            # Update title using batchUpdate
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={
                    "requests": [{
                        "updateSpreadsheetProperties": {
                            "properties": {"title": new_title},
                            "fields": "title"
                        }
                    }]
                }
            ).execute()

            logger.info(f"Renamed spreadsheet to: {new_title}")
        except HttpError as e:
            raise SheetsClientError(f"Failed to rename spreadsheet: {e}") from e
