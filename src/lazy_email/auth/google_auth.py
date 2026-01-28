"""Google OAuth 2.0 authentication module.

This module handles the OAuth 2.0 flow for Google APIs (Gmail and Sheets).
It manages credentials.json and token.json files, providing user-friendly
guidance through the authentication process.
"""

from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

from lazy_email.config import get_settings

# OAuth 2.0 scopes required for the application
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",  # Read Gmail messages
    "https://www.googleapis.com/auth/spreadsheets",  # Read/write Google Sheets
]


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


def _print_setup_guide() -> None:
    """Print user-friendly setup instructions for Google Cloud credentials.

    This guide walks users through creating OAuth credentials if they
    haven't done so already.
    """
    print("\n" + "=" * 70)
    print("GOOGLE CLOUD SETUP REQUIRED")
    print("=" * 70)
    print("\nYou need to set up Google Cloud credentials to use this tool.")
    print("\nFollow these steps:")
    print("\n1. Go to: https://console.cloud.google.com/")
    print("2. Create a new project (or select an existing one)")
    print("3. Enable the Gmail API and Google Sheets API:")
    print("   - Navigate to 'APIs & Services' > 'Library'")
    print("   - Search for 'Gmail API' and click 'Enable'")
    print("   - Search for 'Google Sheets API' and click 'Enable'")
    print("\n4. Create OAuth 2.0 credentials:")
    print("   - Go to 'APIs & Services' > 'Credentials'")
    print("   - Click 'Create Credentials' > 'OAuth client ID'")
    print("   - Select 'Desktop app' as the application type")
    print("   - Give it a name (e.g., 'Lazy Email Tool')")
    print("   - Click 'Create'")
    print("\n5. Download the credentials:")
    print("   - Click the download button (⬇) next to your new OAuth client")
    print("   - Save the file as 'credentials.json' in this directory:")
    print(f"   {_get_credentials_file_path().parent}")
    print("\n6. Re-run this command after saving credentials.json")
    print("=" * 70 + "\n")


def _get_credentials_file_path() -> Path:
    """Get the path to the credentials.json file.

    Returns:
        Path to credentials.json file.
    """
    settings = get_settings()
    return settings.credentials_path


def _get_token_file_path() -> Path:
    """Get the path to the token.json file.

    Returns:
        Path to token.json file.
    """
    settings = get_settings()
    return settings.token_path


def _load_existing_token() -> Optional[Credentials]:
    """Load existing token from token.json if it exists.

    Returns:
        Credentials object if token exists and is valid, None otherwise.
    """
    token_path = _get_token_file_path()
    if not token_path.exists():
        return None

    try:
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        return creds
    except Exception as e:
        print(f"Warning: Could not load existing token: {e}")
        return None


def _refresh_expired_credentials(creds: Credentials) -> Credentials:
    """Refresh expired credentials using the refresh token.

    Args:
        creds: Expired credentials with a refresh token.

    Returns:
        Refreshed credentials.

    Raises:
        AuthenticationError: If refresh fails.
    """
    try:
        creds.refresh(Request())
        return creds
    except Exception as e:
        raise AuthenticationError(f"Failed to refresh credentials: {e}") from e


def _run_oauth_flow() -> Credentials:
    """Run the OAuth 2.0 flow to obtain new credentials.

    This opens a browser window for the user to authenticate and
    authorize the application.

    Returns:
        New credentials obtained from OAuth flow.

    Raises:
        AuthenticationError: If OAuth flow fails.
    """
    creds_path = _get_credentials_file_path()

    if not creds_path.exists():
        _print_setup_guide()
        raise AuthenticationError(
            f"Credentials file not found: {creds_path}\n"
            "Please follow the setup guide above."
        )

    try:
        print("\n" + "=" * 70)
        print("AUTHENTICATION REQUIRED")
        print("=" * 70)
        print("\nA browser window will open for you to:")
        print("1. Sign in to your Google account")
        print("2. Grant permission to access Gmail and Google Sheets")
        print("\nThis is a one-time setup. Your credentials will be saved locally.")
        print("=" * 70 + "\n")

        flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
        creds = flow.run_local_server(port=0)

        print("\n✓ Authentication successful!")
        return creds
    except Exception as e:
        raise AuthenticationError(f"OAuth flow failed: {e}") from e


def _save_credentials(creds: Credentials) -> None:
    """Save credentials to token.json for future use.

    Args:
        creds: Credentials to save.
    """
    token_path = _get_token_file_path()
    try:
        token_path.write_text(creds.to_json())
        print(f"✓ Credentials saved to {token_path}")
    except Exception as e:
        print(f"Warning: Could not save credentials: {e}")


def get_credentials() -> Credentials:
    """Get valid Google API credentials.

    This function handles the complete OAuth flow:
    1. Checks for existing token.json
    2. Refreshes expired credentials if possible
    3. Runs OAuth flow if needed (opens browser)
    4. Saves new credentials for future use

    Returns:
        Valid Credentials object ready for API calls.

    Raises:
        AuthenticationError: If authentication fails at any step.
    """
    # Try to load existing token
    creds = _load_existing_token()

    # If no credentials or they're invalid, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Refresh expired credentials
            print("Refreshing expired credentials...")
            creds = _refresh_expired_credentials(creds)
            _save_credentials(creds)
        else:
            # Run full OAuth flow
            creds = _run_oauth_flow()
            _save_credentials(creds)

    return creds


def get_gmail_service() -> Resource:
    """Get an authenticated Gmail API service.

    Returns:
        Gmail API service resource ready for API calls.

    Raises:
        AuthenticationError: If authentication fails.
    """
    try:
        creds = get_credentials()
        service = build("gmail", "v1", credentials=creds)
        return service
    except Exception as e:
        raise AuthenticationError(f"Failed to build Gmail service: {e}") from e


def get_sheets_service() -> Resource:
    """Get an authenticated Google Sheets API service.

    Returns:
        Sheets API service resource ready for API calls.

    Raises:
        AuthenticationError: If authentication fails.
    """
    try:
        creds = get_credentials()
        service = build("sheets", "v4", credentials=creds)
        return service
    except Exception as e:
        raise AuthenticationError(f"Failed to build Sheets service: {e}") from e


def verify_authentication() -> bool:
    """Verify that authentication is working correctly.

    This performs a lightweight API call to check credentials.

    Returns:
        True if authentication is valid, False otherwise.
    """
    try:
        service = get_gmail_service()
        # Make a lightweight API call to verify access
        service.users().getProfile(userId="me").execute()
        return True
    except Exception:
        return False
