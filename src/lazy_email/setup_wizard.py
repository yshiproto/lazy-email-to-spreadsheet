"""Interactive setup wizard for lazy-email.

Guides new users through all prerequisites in one command:

    lazy-email setup

Checks in order:
  1. Google authentication (credentials.json + OAuth flow)
  2. Google Sheet URL configuration
  3. Ollama installation and running state
  4. LLM model availability (with offer to pull)
  5. End-to-end connection verification
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from lazy_email.auth.google_auth import (
    AuthenticationError,
    get_credentials,
    get_gmail_service,
    run_login_flow,
)
from lazy_email.config import get_settings, update_settings


def _header(step: int, total: int, title: str) -> None:
    print(f"\n[{step}/{total}] {title}")
    print("─" * 50)


def _check_ollama_running() -> bool:
    settings = get_settings()
    try:
        req = urllib.request.Request(f"{settings.ollama_host}/api/tags")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, ConnectionRefusedError, OSError):
        return False


def _start_ollama() -> bool:
    """Start Ollama in the background; wait up to 5 s for it to respond."""
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        for _ in range(10):
            time.sleep(0.5)
            if _check_ollama_running():
                return True
        return False
    except FileNotFoundError:
        return False


def _check_google_auth(step: int, total: int) -> bool:
    _header(step, total, "Google Authentication")

    # Already authenticated?
    try:
        get_credentials()
        service = get_gmail_service()
        profile = service.users().getProfile(userId="me").execute()
        email = profile.get("emailAddress", "unknown")
        print(f"  ✓ Authenticated as {email}")
        return True
    except AuthenticationError:
        pass

    # Need credentials file
    import os

    has_creds = (
        bool(os.environ.get("CREDENTIALS_PATH"))
        or Path("credentials.json").exists()
    )

    if not has_creds:
        print("  ✗ No Google OAuth credentials found.\n")
        print("  To authenticate, you need an OAuth 2.0 credentials file:")
        print("  1. Go to https://console.cloud.google.com/")
        print("  2. APIs & Services → Credentials → Create Credentials → OAuth client ID")
        print("  3. Application type: Desktop app")
        print("  4. Download JSON → save as credentials.json in this folder")
        print()
        print("  Or set: export CREDENTIALS_PATH=/path/to/credentials.json")
        print()
        try:
            input("  Press Enter when credentials.json is ready (Ctrl+C to abort)...")
        except KeyboardInterrupt:
            print()
            return False

    # Run login flow
    try:
        run_login_flow()
        service = get_gmail_service()
        profile = service.users().getProfile(userId="me").execute()
        email = profile.get("emailAddress", "unknown")
        print(f"  ✓ Authenticated as {email}")
        return True
    except Exception as e:
        print(f"  ✗ Authentication failed: {e}")
        return False


def _check_spreadsheet(step: int, total: int) -> bool:
    _header(step, total, "Google Sheet")

    settings = get_settings()
    if settings.spreadsheet_id:
        print(f"  ✓ Spreadsheet configured: {settings.spreadsheet_id}")
        return True

    print("  No spreadsheet configured.")
    print("  Enter your Google Sheets URL or ID (Enter to skip):")
    try:
        user_input = input("  > ").strip()
    except KeyboardInterrupt:
        print()
        print("  ⊘ Skipped.")
        return True  # Not fatal — can pass --spreadsheet-id at run time

    if not user_input:
        print("  ⊘ Skipped. Pass --spreadsheet-id when running.")
        return True

    import argparse
    import re

    def _extract_id(value: str) -> str:
        if "docs.google.com" in value or "spreadsheets" in value:
            match = re.search(r"/d/([a-zA-Z0-9-_]+)", value)
            if match:
                return match.group(1)
            raise argparse.ArgumentTypeError(
                f"Could not extract spreadsheet ID from URL: {value}"
            )
        return value

    try:
        spreadsheet_id = _extract_id(user_input)
        update_settings(spreadsheet_id=spreadsheet_id)
        print(f"  ✓ Spreadsheet configured: {spreadsheet_id}")
        return True
    except argparse.ArgumentTypeError as e:
        print(f"  ✗ {e}")
        return False


def _check_ollama(step: int, total: int) -> bool:
    _header(step, total, "Ollama")

    if _check_ollama_running():
        print("  ✓ Ollama is running")
        return True

    if shutil.which("ollama"):
        print("  ✗ Ollama is installed but not running.")
        try:
            response = input("  Start it now? [Y/n]: ").strip().lower()
        except KeyboardInterrupt:
            print()
            return False
        if response in ("", "y", "yes"):
            print("  Starting Ollama...", end=" ", flush=True)
            if _start_ollama():
                print("✓")
                return True
            print("✗")
            print("  Could not start Ollama. Run 'ollama serve' in another terminal.")
            return False
        return False

    print("  ✗ Ollama is not installed.")
    print("  Install it from: https://ollama.ai/download")
    try:
        input("  Press Enter once installed (Ctrl+C to abort)...")
    except KeyboardInterrupt:
        print()
        return False

    if _check_ollama_running():
        print("  ✓ Ollama is running")
        return True

    if shutil.which("ollama"):
        print("  Starting Ollama...", end=" ", flush=True)
        if _start_ollama():
            print("✓")
            return True
        print("✗")

    print("  ✗ Ollama still not running. Run 'ollama serve' manually, then re-run setup.")
    return False


def _check_model(step: int, total: int) -> bool:
    _header(step, total, "LLM Model")

    settings = get_settings()
    model = settings.ollama_model

    # Check if model is available via ollama list
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if model in result.stdout:
            print(f"  ✓ Model {model} is available")
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    print(f"  ✗ Model {model} is not available.")
    try:
        response = input(f"  Pull it now? [Y/n]: ").strip().lower()
    except KeyboardInterrupt:
        print()
        print(f"  ⊘ Skipped. Run: ollama pull {model}")
        return False

    if response not in ("", "y", "yes"):
        print(f"  ⊘ Skipped. Run: ollama pull {model}")
        return False

    print(f"  Pulling {model}... (this may take a few minutes)")
    try:
        result = subprocess.run(
            ["ollama", "pull", model],
            timeout=600,
        )
        if result.returncode == 0:
            print(f"  ✓ Model {model} ready")
            return True
        print(f"  ✗ Failed to pull {model} (exit {result.returncode})")
        return False
    except subprocess.TimeoutExpired:
        print(f"  ✗ Pull timed out. Run: ollama pull {model}")
        return False
    except FileNotFoundError:
        print("  ✗ ollama not found. Is it installed and on PATH?")
        return False


def _verify_connections(step: int, total: int) -> bool:
    _header(step, total, "Verify Connections")

    all_ok = True

    # Gmail
    print("  • Gmail access...", end=" ", flush=True)
    try:
        service = get_gmail_service()
        profile = service.users().getProfile(userId="me").execute()
        email = profile.get("emailAddress", "")
        print(f"✓ ({email})")
    except Exception as e:
        print(f"✗ ({e})")
        all_ok = False

    # Sheets (optional — only if configured)
    settings = get_settings()
    if settings.spreadsheet_id:
        print("  • Sheets access...", end=" ", flush=True)
        try:
            from lazy_email.sheets.client import SheetsClient, SheetsClientError

            sheets = SheetsClient()
            sheets.verify_connection()
            print("✓")
        except Exception as e:
            print(f"✗ ({e})")
            all_ok = False
    else:
        print("  • Sheets access: skipped (no spreadsheet configured)")

    # LLM
    print("  • LLM connection...", end=" ", flush=True)
    try:
        from lazy_email.llm.extractor import JobApplicationExtractor, LLMExtractorError

        extractor = JobApplicationExtractor()
        if extractor.verify_connection():
            print("✓")
        else:
            print("✗ (model not responding)")
            all_ok = False
    except Exception as e:
        print(f"✗ ({e})")
        all_ok = False

    return all_ok


def run_setup_wizard() -> int:
    """Run the interactive setup wizard. Returns 0 on full success, 1 otherwise."""
    print("\n" + "=" * 60)
    print("  📧 Lazy Email — Setup Wizard")
    print("=" * 60)
    print("\nChecking all prerequisites. Follow the prompts.\n")

    steps: list[tuple[str, object]] = [
        ("Google Authentication", _check_google_auth),
        ("Google Sheet", _check_spreadsheet),
        ("Ollama", _check_ollama),
        ("LLM Model", _check_model),
        ("Verify Connections", _verify_connections),
    ]
    total = len(steps)
    results: dict[str, bool] = {}

    for i, (name, fn) in enumerate(steps, 1):
        try:
            results[name] = fn(i, total)  # type: ignore[operator]
        except KeyboardInterrupt:
            print("\n\n  Setup interrupted.")
            return 1

    # Summary
    print("\n" + "=" * 60)
    for name, ok in results.items():
        icon = "✓" if ok else "✗"
        print(f"  {icon} {name}")
    print("=" * 60)

    if all(results.values()):
        print("\n  ✓ Setup complete! You're ready to run:")
        print("    lazy-email --since 2025-01-01\n")
        return 0

    failed = [name for name, ok in results.items() if not ok]
    print(f"\n  ✗ Needs attention: {', '.join(failed)}")
    print("  Re-run 'lazy-email setup' after fixing these.\n")
    return 1
