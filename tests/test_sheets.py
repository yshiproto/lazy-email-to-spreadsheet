"""Tests for Google Sheets API client."""

from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
from googleapiclient.errors import HttpError

from lazy_email.models.email import ApplicationStatus, JobApplication
from lazy_email.sheets.client import SheetsClient, SheetsClientError

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.fixtures import FixtureRequest
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture


@pytest.fixture
def mock_sheets_service() -> Mock:
    """Create a mock Sheets API service.

    Returns:
        Mock Sheets service with spreadsheets methods.
    """
    service = Mock()
    return service


@pytest.fixture
def sample_job_application() -> JobApplication:
    """Create a sample JobApplication for testing.

    Returns:
        JobApplication with test data.
    """
    return JobApplication(
        company_name="Google",
        role="Software Engineer",
        status=ApplicationStatus.SUBMITTED,
        date_submitted="2026-01-10",
        email_link="https://mail.google.com/mail/u/0/#inbox/test123",
    )


@pytest.fixture
def sample_job_applications() -> list[JobApplication]:
    """Create multiple sample JobApplications for testing.

    Returns:
        List of JobApplication objects.
    """
    return [
        JobApplication(
            company_name="Google",
            role="Software Engineer",
            status=ApplicationStatus.SUBMITTED,
            date_submitted="2026-01-10",
            email_link="https://mail.google.com/mail/u/0/#inbox/test1",
        ),
        JobApplication(
            company_name="Meta",
            role="Data Scientist",
            status=ApplicationStatus.INTERVIEW,
            date_submitted="2026-01-11",
            email_link="https://mail.google.com/mail/u/0/#inbox/test2",
        ),
        JobApplication(
            company_name="Amazon",
            role="SDE",
            status=ApplicationStatus.OA_INVITE,
            date_submitted="2026-01-12",
            email_link="https://mail.google.com/mail/u/0/#inbox/test3",
        ),
    ]


class TestSheetsClientInit:
    """Tests for SheetsClient initialization."""

    def test_init_with_service(self, mock_sheets_service: Mock) -> None:
        """Test initializing client with provided service."""
        client = SheetsClient(
            service=mock_sheets_service,
            spreadsheet_id="test_id",
            sheet_name="TestSheet",
            batch_size=25,
        )

        assert client.service == mock_sheets_service
        assert client.spreadsheet_id == "test_id"
        assert client.sheet_name == "TestSheet"
        assert client.batch_size == 25

    def test_init_with_defaults(self, mocker: "MockerFixture") -> None:
        """Test initializing client with default settings."""
        mock_settings = Mock()
        mock_settings.spreadsheet_id = "default_id"
        mock_settings.sheet_name = "Sheet1"
        mock_settings.sheets_batch_size = 50

        mocker.patch("lazy_email.sheets.client.get_settings", return_value=mock_settings)
        mocker.patch("lazy_email.sheets.client.get_sheets_service", return_value=Mock())

        client = SheetsClient()

        assert client.spreadsheet_id == "default_id"
        assert client.sheet_name == "Sheet1"
        assert client.batch_size == 50


class TestJobToRow:
    """Tests for _job_to_row conversion."""

    def test_job_to_row_conversion(
        self, mock_sheets_service: Mock, sample_job_application: JobApplication
    ) -> None:
        """Test converting JobApplication to row values."""
        client = SheetsClient(
            service=mock_sheets_service,
            spreadsheet_id="test_id",
            sheet_name="Test",
        )

        row = client._job_to_row(sample_job_application)

        assert row == [
            "Google",
            "Submitted Application - Pending Response",  # Enum value
            "Software Engineer",
            "2026-01-10",
            "https://mail.google.com/mail/u/0/#inbox/test123",
        ]

    def test_job_to_row_uses_enum_value(self, mock_sheets_service: Mock) -> None:
        """Test that status enum value is used for dropdown matching."""
        job = JobApplication(
            company_name="Test",
            role="Test Role",
            status=ApplicationStatus.INTERVIEW,
            date_submitted="2026-01-13",
            email_link="https://example.com",
        )

        client = SheetsClient(
            service=mock_sheets_service,
            spreadsheet_id="test_id",
            sheet_name="Test",
        )

        row = client._job_to_row(job)

        # Should use full enum value for dropdown
        assert row[1] == "Interview"


class TestAppendRow:
    """Tests for append_row method."""

    def test_append_single_row(
        self,
        mock_sheets_service: Mock,
        sample_job_application: JobApplication,
        mocker: "MockerFixture",
    ) -> None:
        """Test appending a single row."""
        mock_sheets_service.spreadsheets().values().append().execute.return_value = {
            "updates": {"updatedRows": 1}
        }
        mocker.patch("time.sleep")

        client = SheetsClient(
            service=mock_sheets_service,
            spreadsheet_id="test_id",
            sheet_name="Test",
        )

        client.append_row(sample_job_application)

        # Verify append was called
        mock_sheets_service.spreadsheets().values().append.assert_called()

    def test_append_row_with_rate_limit_error(
        self,
        mock_sheets_service: Mock,
        sample_job_application: JobApplication,
        mocker: "MockerFixture",
    ) -> None:
        """Test append retries on rate limit error."""
        # First call fails with 429, second succeeds
        mock_response = Mock()
        mock_response.status = 429
        error = HttpError(resp=mock_response, content=b"Rate limit")

        mock_sheets_service.spreadsheets().values().append().execute.side_effect = [
            error,
            {"updates": {"updatedRows": 1}},
        ]
        mocker.patch("time.sleep")

        client = SheetsClient(
            service=mock_sheets_service,
            spreadsheet_id="test_id",
            sheet_name="Test",
        )

        # Should succeed after retry
        client.append_row(sample_job_application)


class TestAppendRows:
    """Tests for append_rows method."""

    def test_append_multiple_rows(
        self,
        mock_sheets_service: Mock,
        sample_job_applications: list[JobApplication],
        mocker: "MockerFixture",
    ) -> None:
        """Test appending multiple rows."""
        mock_sheets_service.spreadsheets().values().append().execute.return_value = {
            "updates": {"updatedRows": 3}
        }
        mocker.patch("time.sleep")

        client = SheetsClient(
            service=mock_sheets_service,
            spreadsheet_id="test_id",
            sheet_name="Test",
            batch_size=50,  # All in one batch
        )

        count = client.append_rows(sample_job_applications)

        assert count == 3

    def test_append_rows_batching(
        self,
        mock_sheets_service: Mock,
        mocker: "MockerFixture",
    ) -> None:
        """Test rows are batched correctly."""
        mock_sheets_service.spreadsheets().values().append().execute.return_value = {
            "updates": {"updatedRows": 2}
        }
        mocker.patch("time.sleep")

        # Create 5 jobs
        jobs = [
            JobApplication(
                company_name=f"Company{i}",
                role=f"Role{i}",
                status=ApplicationStatus.SUBMITTED,
                date_submitted="2026-01-10",
                email_link=f"https://example.com/{i}",
            )
            for i in range(5)
        ]

        client = SheetsClient(
            service=mock_sheets_service,
            spreadsheet_id="test_id",
            sheet_name="Test",
            batch_size=2,  # Small batch size for testing
        )

        count = client.append_rows(jobs)

        assert count == 5
        # Should have 3 batches: 2, 2, 1
        assert mock_sheets_service.spreadsheets().values().append().execute.call_count == 3

    def test_append_empty_list(self, mock_sheets_service: Mock) -> None:
        """Test appending empty list returns 0."""
        client = SheetsClient(
            service=mock_sheets_service,
            spreadsheet_id="test_id",
            sheet_name="Test",
        )

        count = client.append_rows([])

        assert count == 0
        mock_sheets_service.spreadsheets().values().append.assert_not_called()


class TestGetExistingEmailLinks:
    """Tests for get_existing_email_links method."""

    def test_get_existing_links(self, mock_sheets_service: Mock) -> None:
        """Test retrieving existing email links."""
        mock_sheets_service.spreadsheets().values().get().execute.return_value = {
            "values": [
                ["Email Link"],  # Header
                ["https://mail.google.com/1"],
                ["https://mail.google.com/2"],
                ["https://mail.google.com/3"],
            ]
        }

        client = SheetsClient(
            service=mock_sheets_service,
            spreadsheet_id="test_id",
            sheet_name="Test",
        )

        links = client.get_existing_email_links()

        assert len(links) == 3
        assert "https://mail.google.com/1" in links
        assert "https://mail.google.com/2" in links

    def test_get_existing_links_empty_sheet(self, mock_sheets_service: Mock) -> None:
        """Test retrieving links from empty sheet."""
        mock_sheets_service.spreadsheets().values().get().execute.return_value = {
            "values": [["Email Link"]]  # Just header
        }

        client = SheetsClient(
            service=mock_sheets_service,
            spreadsheet_id="test_id",
            sheet_name="Test",
        )

        links = client.get_existing_email_links()

        assert len(links) == 0


class TestVerifyConnection:
    """Tests for verify_connection method."""

    def test_verify_connection_success(
        self, mock_sheets_service: Mock, capsys: "CaptureFixture[str]"
    ) -> None:
        """Test successful connection verification."""
        mock_sheets_service.spreadsheets().get().execute.return_value = {
            "properties": {"title": "Job Applications"},
            "sheets": [
                {"properties": {"title": "Sheet1"}},
                {"properties": {"title": "Archive"}},
            ],
        }

        client = SheetsClient(
            service=mock_sheets_service,
            spreadsheet_id="test_id",
            sheet_name="Sheet1",
        )

        result = client.verify_connection()

        assert result is True
        captured = capsys.readouterr()
        assert "Connected to spreadsheet" in captured.out
        assert "Job Applications" in captured.out

    def test_verify_connection_sheet_not_found(
        self, mock_sheets_service: Mock, capsys: "CaptureFixture[str]"
    ) -> None:
        """Test connection verification when sheet tab not found."""
        mock_sheets_service.spreadsheets().get().execute.return_value = {
            "properties": {"title": "Job Applications"},
            "sheets": [{"properties": {"title": "OtherSheet"}}],
        }

        client = SheetsClient(
            service=mock_sheets_service,
            spreadsheet_id="test_id",
            sheet_name="Sheet1",
        )

        result = client.verify_connection()

        assert result is False
        captured = capsys.readouterr()
        assert "not found" in captured.out

    def test_verify_connection_no_spreadsheet_id(
        self, mock_sheets_service: Mock, capsys: "CaptureFixture[str]"
    ) -> None:
        """Test connection verification with missing spreadsheet ID."""
        client = SheetsClient(
            service=mock_sheets_service,
            spreadsheet_id="",
            sheet_name="Sheet1",
        )

        result = client.verify_connection()

        assert result is False
        captured = capsys.readouterr()
        assert "SPREADSHEET_ID not configured" in captured.out

    def test_verify_connection_access_denied(
        self, mock_sheets_service: Mock, capsys: "CaptureFixture[str]"
    ) -> None:
        """Test connection verification with access denied error."""
        mock_response = Mock()
        mock_response.status = 403
        error = HttpError(resp=mock_response, content=b"Access denied")

        mock_sheets_service.spreadsheets().get().execute.side_effect = error

        client = SheetsClient(
            service=mock_sheets_service,
            spreadsheet_id="test_id",
            sheet_name="Sheet1",
        )

        result = client.verify_connection()

        assert result is False
        captured = capsys.readouterr()
        assert "Access denied" in captured.out


class TestGetRowCount:
    """Tests for get_row_count method."""

    def test_get_row_count(self, mock_sheets_service: Mock) -> None:
        """Test getting row count."""
        mock_sheets_service.spreadsheets().values().get().execute.return_value = {
            "values": [
                ["Header"],
                ["Row1"],
                ["Row2"],
                ["Row3"],
            ]
        }

        client = SheetsClient(
            service=mock_sheets_service,
            spreadsheet_id="test_id",
            sheet_name="Test",
        )

        count = client.get_row_count()

        assert count == 3  # Excludes header

    def test_get_row_count_empty_sheet(self, mock_sheets_service: Mock) -> None:
        """Test getting row count from empty sheet."""
        mock_sheets_service.spreadsheets().values().get().execute.return_value = {
            "values": [["Header"]]
        }

        client = SheetsClient(
            service=mock_sheets_service,
            spreadsheet_id="test_id",
            sheet_name="Test",
        )

        count = client.get_row_count()

        assert count == 0
