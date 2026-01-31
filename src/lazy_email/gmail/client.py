"""Gmail API client module with rate limiting.

This module provides a high-level interface to the Gmail API for fetching
email messages from the primary inbox with date filtering and automatic
rate limit handling.
"""

import base64
import time
from datetime import datetime
from typing import Any, Optional

from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from lazy_email.auth.google_auth import get_gmail_service
from lazy_email.models.email import EmailMessage


class GmailClientError(Exception):
    """Raised when Gmail API operations fail."""

    pass


def _extract_header_value(headers: list[dict[str, str]], name: str) -> str:
    """Extract a header value from email headers.

    Args:
        headers: List of header dictionaries from Gmail API.
        name: Header name to extract (e.g., 'From', 'Date', 'Subject').

    Returns:
        Header value if found, empty string otherwise.
    """
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return header.get("value", "")
    return ""


def _parse_email_date(date_str: str) -> datetime:
    """Parse email date string to datetime object.

    Gmail date format: 'Mon, 10 Jan 2026 14:30:00 +0000'

    Args:
        date_str: Date string from email header.

    Returns:
        Parsed datetime object.

    Raises:
        ValueError: If date parsing fails.
    """
    from email.utils import parsedate_to_datetime

    try:
        return parsedate_to_datetime(date_str)
    except Exception as e:
        raise ValueError(f"Failed to parse date '{date_str}': {e}") from e


def _extract_text_from_payload(payload: dict[str, Any]) -> str:
    """Extract plain text content from email payload.

    Handles both simple and multipart messages. Prefers plain text
    over HTML content.

    Args:
        payload: Email payload from Gmail API.

    Returns:
        Decoded text content, or empty string if no text found.
    """
    # Check if payload has body data directly (simple message)
    if "body" in payload and "data" in payload["body"]:
        data = payload["body"]["data"]
        try:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        except Exception:
            return ""

    # Handle multipart messages
    if "parts" in payload:
        for part in payload["parts"]:
            mime_type = part.get("mimeType", "")

            # Prefer plain text
            if mime_type == "text/plain" and "body" in part and "data" in part["body"]:
                data = part["body"]["data"]
                try:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                except Exception:
                    continue

            # Recursively check nested parts
            if "parts" in part:
                text = _extract_text_from_payload(part)
                if text:
                    return text

        # Fallback to HTML if no plain text found
        for part in payload["parts"]:
            mime_type = part.get("mimeType", "")
            if mime_type == "text/html" and "body" in part and "data" in part["body"]:
                data = part["body"]["data"]
                try:
                    # Basic HTML stripping (could be improved with BeautifulSoup)
                    html = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                    # Simple HTML tag removal
                    import re

                    text = re.sub(r"<[^>]+>", "", html)
                    return text.strip()
                except Exception:
                    continue

    return ""


class GmailClient:
    """Gmail API client with rate limiting and filtering.

    This client provides methods to fetch emails from the primary inbox
    with date filtering and automatic rate limit handling using exponential
    backoff.

    Attributes:
        service: Authenticated Gmail API service resource.
        user_id: Gmail user ID (default: 'me' for authenticated user).
    """

    def __init__(self, service: Optional[Resource] = None) -> None:
        """Initialize Gmail client.

        Args:
            service: Optional authenticated Gmail service. If not provided,
                    will create one using get_gmail_service().
        """
        self.service = service or get_gmail_service()
        self.user_id = "me"

    @retry(
        retry=retry_if_exception_type(HttpError),
        wait=wait_exponential(multiplier=1, min=1, max=64),
        stop=stop_after_attempt(5),
    )
    def _list_messages_page(
        self, query: str, max_results: int = 100, page_token: Optional[str] = None
    ) -> tuple[list[dict[str, str]], Optional[str]]:
        """List a single page of message IDs matching query.

        Args:
            query: Gmail search query string.
            max_results: Maximum number of messages per page.
            page_token: Token for fetching next page.

        Returns:
            Tuple of (messages list, next page token or None).

        Raises:
            GmailClientError: If API call fails after retries.
        """
        try:
            request = self.service.users().messages().list(
                userId=self.user_id, q=query, maxResults=max_results
            )
            if page_token:
                request = self.service.users().messages().list(
                    userId=self.user_id, q=query, maxResults=max_results, pageToken=page_token
                )
            results = request.execute()
            return results.get("messages", []), results.get("nextPageToken")
        except HttpError as e:
            if e.resp.status in [429, 500, 503]:
                # Retry on rate limit or server errors
                raise
            raise GmailClientError(f"Failed to list messages: {e}") from e

    def _list_messages_with_retry(
        self, query: str, max_results: Optional[int] = None
    ) -> list[dict[str, str]]:
        """List all message IDs matching query with pagination.

        Args:
            query: Gmail search query string.
            max_results: Maximum number of messages to return. None = unlimited.

        Returns:
            List of message metadata dictionaries with 'id' and 'threadId'.

        Raises:
            GmailClientError: If API call fails after retries.
        """
        all_messages: list[dict[str, str]] = []
        page_token: Optional[str] = None
        page_size = 100  # Gmail API max per page

        while True:
            messages, page_token = self._list_messages_page(query, page_size, page_token)
            all_messages.extend(messages)

            # Check if we've hit the user's limit
            if max_results is not None and len(all_messages) >= max_results:
                return all_messages[:max_results]

            # No more pages
            if not page_token:
                break

        return all_messages

    @retry(
        retry=retry_if_exception_type(HttpError),
        wait=wait_exponential(multiplier=1, min=1, max=64),
        stop=stop_after_attempt(5),
    )
    def _get_message_with_retry(self, message_id: str) -> dict[str, Any]:
        """Get full message details with rate limit retry.

        Args:
            message_id: Gmail message ID.

        Returns:
            Full message metadata and payload.

        Raises:
            GmailClientError: If API call fails after retries.
        """
        try:
            message = (
                self.service.users()
                .messages()
                .get(userId=self.user_id, id=message_id, format="full")
                .execute()
            )
            return message
        except HttpError as e:
            if e.resp.status in [429, 500, 503]:
                # Retry on rate limit or server errors
                raise
            raise GmailClientError(f"Failed to get message {message_id}: {e}") from e

    def _build_query(self, since_date: Optional[str] = None, until_date: Optional[str] = None) -> str:
        """Build Gmail search query string.

        Args:
            since_date: Optional date in YYYY-MM-DD format to filter emails (inclusive).
            until_date: Optional date in YYYY-MM-DD format to filter emails (exclusive).

        Returns:
            Gmail query string (e.g., 'category:primary after:2025/12/01 before:2025/12/31').
        """
        query_parts = ["category:primary"]

        if since_date:
            # Convert YYYY-MM-DD to YYYY/MM/DD for Gmail query
            query_date = since_date.replace("-", "/")
            query_parts.append(f"after:{query_date}")

        if until_date:
            # Convert YYYY-MM-DD to YYYY/MM/DD for Gmail query
            query_date = until_date.replace("-", "/")
            query_parts.append(f"before:{query_date}")

        return " ".join(query_parts)

    def _parse_message_to_email(self, message: dict[str, Any]) -> EmailMessage:
        """Parse Gmail API message to EmailMessage model.

        Args:
            message: Full message from Gmail API.

        Returns:
            EmailMessage instance with extracted data.

        Raises:
            GmailClientError: If required data cannot be extracted.
        """
        try:
            message_id = message["id"]
            headers = message["payload"]["headers"]

            # Extract headers
            date_str = _extract_header_value(headers, "Date")
            sender = _extract_header_value(headers, "From")
            subject = _extract_header_value(headers, "Subject")

            # Parse date
            try:
                date_sent = _parse_email_date(date_str)
            except ValueError:
                # Fallback to current time if date parsing fails
                date_sent = datetime.now()

            # Extract email content
            content = _extract_text_from_payload(message["payload"])

            # Build Gmail link
            email_link = f"https://mail.google.com/mail/u/0/#inbox/{message_id}"

            return EmailMessage(
                message_id=message_id,
                subject=subject,
                content=content,
                date_sent=date_sent,
                email_link=email_link,
                sender=sender,
            )
        except KeyError as e:
            raise GmailClientError(f"Missing required field in message: {e}") from e

    def fetch_messages(
        self,
        since_date: Optional[str] = None,
        until_date: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> list[EmailMessage]:
        """Fetch emails from primary inbox with optional date filter.

        Args:
            since_date: Optional date in YYYY-MM-DD format. Only emails
                       received on or after this date will be fetched.
            until_date: Optional date in YYYY-MM-DD format. Only emails
                       received before this date will be fetched (exclusive).
            max_results: Maximum number of emails to fetch. None = unlimited.

        Returns:
            List of EmailMessage objects.

        Raises:
            GmailClientError: If fetching or parsing fails.
        """
        query = self._build_query(since_date, until_date)

        # List message IDs
        message_list = self._list_messages_with_retry(query, max_results)

        if not message_list:
            return []

        # Fetch full message details
        emails: list[EmailMessage] = []
        for msg_meta in message_list:
            message_id = msg_meta["id"]

            # Get full message with rate limiting
            message = self._get_message_with_retry(message_id)

            # Parse to EmailMessage
            email = self._parse_message_to_email(message)
            emails.append(email)

            # Small delay to stay within rate limits (40 req/sec = 25ms between requests)
            time.sleep(0.025)

        return emails

    def fetch_single_message(self, message_id: str) -> EmailMessage:
        """Fetch a single email by message ID.

        Args:
            message_id: Gmail message ID.

        Returns:
            EmailMessage object.

        Raises:
            GmailClientError: If fetching or parsing fails.
        """
        message = self._get_message_with_retry(message_id)
        return self._parse_message_to_email(message)
