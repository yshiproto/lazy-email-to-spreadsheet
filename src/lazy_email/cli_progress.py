"""Progress and status reporting helpers for the CLI.

The rest of the application talks to :class:`ProgressReporter` instead of Rich
or terminal-specific APIs directly. This keeps rendering choices isolated from
email, sheet, and state processing logic.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from enum import Enum
from typing import Any, TypeVar

try:
    from rich.console import Console
    from rich.logging import RichHandler
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TextColumn,
        TimeRemainingColumn,
    )
except ImportError:  # pragma: no cover - exercised only when optional dependency is absent
    Console = None
    RichHandler = None
    Progress = None
    SpinnerColumn = None
    TextColumn = None
    BarColumn = None
    TaskProgressColumn = None
    MofNCompleteColumn = None
    TimeRemainingColumn = None

T = TypeVar("T")


class OutputMode(str, Enum):
    """Supported CLI output modes."""

    MODERN = "modern"
    LEGACY = "legacy"
    DETERMINISTIC = "deterministic"


class ProgressReporter:
    """Small abstraction over modern, legacy, and deterministic CLI progress output."""

    def __init__(self, mode: OutputMode, console: Any | None = None) -> None:
        self.mode = mode
        self.console = console or (Console() if Console is not None else None)

    @classmethod
    def legacy(cls) -> ProgressReporter:
        """Create a reporter that preserves the previous print-oriented output."""
        return cls(OutputMode.LEGACY)

    @property
    def uses_legacy_output(self) -> bool:
        """Whether call sites should use the pre-progress output path."""
        return self.mode == OutputMode.LEGACY

    @property
    def uses_live_output(self) -> bool:
        """Whether Rich live rendering should be used."""
        return self.mode == OutputMode.MODERN and self.console is not None

    def step(self, step: int, total: int, message: str) -> None:
        """Print a high-level phase marker."""
        if self.uses_live_output:
            self.console.rule(f"[bold cyan][{step}/{total}] {message}", style="cyan")
            return

        print(f"\n[{step}/{total}] {message}")
        print("-" * 50)

    @contextmanager
    def status(self, message: str) -> Iterator[None]:
        """Show an indeterminate status for work without a meaningful total."""
        if self.uses_live_output:
            with self.console.status(message, spinner="dots"):
                yield
            return

        print(f"  • {message}...", end=" ", flush=True)
        yield

    def track(self, items: Iterable[T], *, description: str, total: int | None = None) -> Iterator[T]:
        """Iterate over items with known-total progress when modern output is active."""
        if self.uses_live_output and Progress is not None:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                MofNCompleteColumn(),
                TimeRemainingColumn(),
                console=self.console,
            ) as progress:
                task_id = progress.add_task(description, total=total)
                for item in items:
                    yield item
                    progress.advance(task_id)
            return

        if self.mode == OutputMode.DETERMINISTIC:
            suffix = f" ({total} items)" if total is not None else ""
            print(f"  • {description}{suffix}")

        yield from items

    def message(self, message: str) -> None:
        """Emit a stable message line."""
        if self.uses_live_output:
            self.console.print(message)
        else:
            print(message)

    def success(self, message: str) -> None:
        """Emit a success message."""
        self.message(f"  ✓ {message}")

    def failure(self, message: str) -> None:
        """Emit a failure message."""
        self.message(f"  ✗ {message}")


def _silence_library_loggers() -> None:
    """Silence verbose third-party loggers that write to stderr while Rich renders.

    Python's logging.StreamHandler caches a direct reference to sys.stderr at
    creation time, so Rich's redirect_stderr cannot intercept those writes.
    Setting these to WARNING prevents INFO-level chatter from pushing the live
    progress bar down and making it appear to add a new line per email.
    """
    for name in (
        "googleapiclient",
        "googleapiclient.discovery",
        "googleapiclient.discovery_cache",
        "urllib3",
        "urllib3.connectionpool",
        "httplib2",
        "google.auth",
        "google_auth_httplib2",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)


def create_progress_reporter(*, legacy_output: bool = False, dry_run: bool = False) -> ProgressReporter:
    """Create the appropriate reporter for the current invocation.

    Dry-run intentionally uses legacy output for the entire processing path so
    developer/test-oriented stdout remains stable.
    """
    if legacy_output or dry_run:
        return ProgressReporter(OutputMode.LEGACY)

    if not sys.stdout.isatty():
        return ProgressReporter(OutputMode.DETERMINISTIC)

    if Console is None:
        return ProgressReporter(OutputMode.DETERMINISTIC)

    # force_terminal=True ensures Rich uses ANSI escape codes for in-place
    # updates even in environments that mis-report terminal capabilities
    # (tmux, screen, some IDE terminals, TERM=dumb, etc.).
    _silence_library_loggers()
    console = Console(force_terminal=True)
    # Replace root logger's StreamHandler (which holds a cached sys.stderr
    # reference that Rich's redirect_stderr cannot intercept) with a
    # RichHandler that routes all log output through the same Console.
    # This prevents log writes from any library (ollama, httpx, etc.) from
    # bypassing Rich's live rendering and pushing the progress bar down.
    if RichHandler is not None:
        root = logging.getLogger()
        root.handlers = [RichHandler(console=console, show_path=False, markup=False)]
    return ProgressReporter(OutputMode.MODERN, console=console)
