"""Google OAuth 2.0 authentication module.

Authentication is split into two distinct flows:

- ``lazy-email login`` — runs the OAuth browser consent flow and persists a
  token to the platform config directory.
- ``get_credentials()`` — loads the persisted token (raises
  :class:`AuthenticationError` when the token is absent, directing the user
  to run ``lazy-email setup`` or ``lazy-email login`` first).

The OAuth credentials file is resolved in this order:

1. ``CREDENTIALS_PATH`` env var → path to a credentials.json file
2. ``credentials.json`` in the current working directory
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

from lazy_email.config import get_settings

# OAuth 2.0 scopes required for the application
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/spreadsheets",
]


class AuthenticationError(Exception):
    """Raised when authentication fails."""


def _get_credentials_path() -> Path:
    """Resolve the OAuth credentials file path.

    Resolution order:

    1. ``CREDENTIALS_PATH`` env var — explicit override (file must exist).
    2. ``credentials.json`` in the current working directory.

    Returns:
        Path to the credentials.json file.

    Raises:
        AuthenticationError: If no credentials file is found.
    """
    credentials_path_env = os.environ.get("CREDENTIALS_PATH")
    if credentials_path_env:
        path = Path(credentials_path_env)
        if path.exists():
            return path
        raise AuthenticationError(
            f"CREDENTIALS_PATH is set but file not found: {path}"
        )

    cwd_creds = Path("credentials.json")
    if cwd_creds.exists():
        return cwd_creds

    raise AuthenticationError(
        "Google OAuth credentials not found.\n"
        "Run 'lazy-email setup' to configure the tool, or place credentials.json "
        "in the current directory (or set CREDENTIALS_PATH)."
    )


def _get_token_file_path() -> Path:
    """Return the path to the persisted OAuth token file."""
    return get_settings().token_path


def _migrate_legacy_token() -> None:
    """Move a CWD ``token.json`` into the platform config dir (one-time).

    Earlier versions stored ``token.json`` in the working directory. This
    silently relocates it on the first run after upgrading so existing users
    don't lose their session.
    """
    legacy = Path("token.json")
    new_path = _get_token_file_path()
    if legacy.resolve() == new_path.resolve():
        return  # Same file — TOKEN_PATH env var override in effect
    if legacy.exists() and not new_path.exists():
        new_path.parent.mkdir(parents=True, exist_ok=True)
        legacy.rename(new_path)


def _load_existing_token() -> Optional[Credentials]:
    """Load credentials from the token file if it exists."""
    token_path = _get_token_file_path()
    if not token_path.exists():
        return None
    try:
        return Credentials.from_authorized_user_file(str(token_path), SCOPES)
    except Exception as e:  # noqa: BLE001
        print(f"Warning: Could not load existing token: {e}")
        return None


def _refresh_expired_credentials(creds: Credentials) -> Credentials:
    """Refresh expired credentials using the stored refresh token.

    Raises:
        AuthenticationError: If the refresh request fails.
    """
    try:
        creds.refresh(Request())
        return creds
    except Exception as e:
        raise AuthenticationError(f"Failed to refresh credentials: {e}") from e


def _run_oauth_flow() -> Credentials:
    """Open a browser window and run the OAuth consent flow.

    Raises:
        AuthenticationError: If credentials file is missing or the flow fails.
    """
    creds_path = _get_credentials_path()
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
        return flow.run_local_server(port=0)
    except Exception as e:
        raise AuthenticationError(f"OAuth flow failed: {e}") from e


def _save_credentials(creds: Credentials) -> None:
    """Persist credentials to the token file."""
    token_path = _get_token_file_path()
    try:
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())
    except Exception as e:  # noqa: BLE001
        print(f"Warning: Could not save credentials: {e}")


def run_login_flow(reauth: bool = False) -> None:
    """Run the browser-based OAuth login flow.

    Called by ``lazy-email login`` and ``lazy-email setup``. On success the
    token is saved to the platform config directory so subsequent
    :func:`get_credentials` calls succeed without user interaction.

    Args:
        reauth: When *True*, always run the full browser flow even if a valid
            token already exists.
    """
    token_path = _get_token_file_path()

    if not reauth and token_path.exists():
        try:
            creds = get_credentials()
            if creds.valid:
                print("✓ Already authenticated. Use --reauth to re-authenticate.")
                return
        except AuthenticationError:
            pass  # Fall through to fresh flow

    token_path.parent.mkdir(parents=True, exist_ok=True)
    print("Opening browser for Google authentication...")
    print("Grant access to Gmail (read) and Google Sheets (read/write).\n")
    creds = _run_oauth_flow()
    _save_credentials(creds)
    print(f"✓ Authenticated successfully. Token saved to {token_path}")


def get_credentials() -> Credentials:
    """Return valid Google API credentials.

    Loads the saved token and refreshes it if expired. Raises
    :class:`AuthenticationError` when no token is present — the caller should
    direct the user to run ``lazy-email setup`` or ``lazy-email login``.

    Returns:
        A valid :class:`Credentials` object.

    Raises:
        AuthenticationError: If no token exists or the token cannot be
            refreshed.
    """
    _migrate_legacy_token()
    creds = _load_existing_token()

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing expired credentials...")
            creds = _refresh_expired_credentials(creds)
            _save_credentials(creds)
        else:
            raise AuthenticationError(
                "Not authenticated. Run 'lazy-email setup' or 'lazy-email login' "
                "to authenticate."
            )

    return creds


def get_gmail_service() -> Resource:
    """Return an authenticated Gmail API service.

    Raises:
        AuthenticationError: If authentication fails.
    """
    try:
        creds = get_credentials()
        return build("gmail", "v1", credentials=creds)
    except Exception as e:
        raise AuthenticationError(f"Failed to build Gmail service: {e}") from e


def get_sheets_service() -> Resource:
    """Return an authenticated Google Sheets API service.

    Raises:
        AuthenticationError: If authentication fails.
    """
    try:
        creds = get_credentials()
        return build("sheets", "v4", credentials=creds)
    except Exception as e:
        raise AuthenticationError(f"Failed to build Sheets service: {e}") from e


def verify_authentication() -> bool:
    """Return *True* if the stored credentials can access Gmail."""
    try:
        service = get_gmail_service()
        service.users().getProfile(userId="me").execute()
        return True
    except Exception:
        return False
