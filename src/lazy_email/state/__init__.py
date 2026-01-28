"""State management module for processing resume functionality.

This module provides state persistence for tracking processed email messages,
enabling stop/resume functionality when processing large email batches.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from lazy_email.config import get_settings

logger = logging.getLogger(__name__)


class ProcessingState(BaseModel):
    """Represents the current processing state.

    Attributes:
        processed_ids: Set of Gmail message IDs that have been processed.
        last_processed_id: The most recently processed message ID.
        last_run: Timestamp of the last processing run.
        since_date: The --since date filter used for this processing session.
        total_processed: Total number of messages processed in this session.
        total_written: Total number of rows written to the sheet.
    """

    processed_ids: set[str] = Field(default_factory=set)
    last_processed_id: Optional[str] = None
    last_run: Optional[str] = None
    since_date: Optional[str] = None
    total_processed: int = 0
    total_written: int = 0

    class Config:
        """Pydantic configuration."""

        # Allow set type
        arbitrary_types_allowed = True


class StateManager:
    """Manages processing state for stop/resume functionality.

    Saves and loads state from a JSON file to track which emails have
    been processed. Supports periodic saves to prevent data loss on
    unexpected interruptions.

    Attributes:
        state_file: Path to the state JSON file.
        state: Current ProcessingState object.
        save_interval: Number of messages between automatic saves.
    """

    def __init__(
        self,
        state_file: Optional[Path] = None,
        save_interval: int = 10,
    ) -> None:
        """Initialize the state manager.

        Args:
            state_file: Path to state file. Defaults to settings.state_file_path.
            save_interval: Messages between auto-saves. Default 10.
        """
        settings = get_settings()
        self.state_file = state_file or settings.state_file_path
        self.save_interval = save_interval
        self.state = ProcessingState()
        self._unsaved_count = 0

    def load(self) -> bool:
        """Load state from file if it exists.

        Returns:
            True if state was loaded, False if no state file exists.
        """
        if not self.state_file.exists():
            logger.info("No existing state file found, starting fresh")
            return False

        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)

            # Convert processed_ids list back to set
            if "processed_ids" in data:
                data["processed_ids"] = set(data["processed_ids"])

            self.state = ProcessingState(**data)
            logger.info(
                f"Loaded state: {len(self.state.processed_ids)} messages previously processed"
            )
            return True
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse state file: {e}")
            return False
        except Exception as e:
            logger.warning(f"Failed to load state: {e}")
            return False

    def save(self) -> None:
        """Save current state to file."""
        try:
            # Update last run timestamp
            self.state.last_run = datetime.now().isoformat()

            # Convert to dict and handle set serialization
            data = self.state.model_dump()
            data["processed_ids"] = list(data["processed_ids"])

            with open(self.state_file, "w") as f:
                json.dump(data, f, indent=2)

            self._unsaved_count = 0
            logger.debug(f"State saved: {len(self.state.processed_ids)} messages tracked")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def is_processed(self, message_id: str) -> bool:
        """Check if a message has already been processed.

        Args:
            message_id: Gmail message ID to check.

        Returns:
            True if message was already processed.
        """
        return message_id in self.state.processed_ids

    def mark_processed(self, message_id: str, auto_save: bool = True) -> None:
        """Mark a message as processed.

        Args:
            message_id: Gmail message ID that was processed.
            auto_save: Whether to auto-save after save_interval messages.
        """
        self.state.processed_ids.add(message_id)
        self.state.last_processed_id = message_id
        self.state.total_processed += 1
        self._unsaved_count += 1

        # Auto-save periodically
        if auto_save and self._unsaved_count >= self.save_interval:
            self.save()

    def mark_written(self, count: int = 1) -> None:
        """Update the count of rows written to the sheet.

        Args:
            count: Number of rows written.
        """
        self.state.total_written += count

    def set_since_date(self, since_date: str) -> None:
        """Set the since date filter for this session.

        Args:
            since_date: Date string in YYYY-MM-DD format.
        """
        self.state.since_date = since_date

    def get_unprocessed(self, message_ids: list[str]) -> list[str]:
        """Filter out already processed message IDs.

        Args:
            message_ids: List of message IDs to filter.

        Returns:
            List of message IDs that have not been processed.
        """
        return [mid for mid in message_ids if mid not in self.state.processed_ids]

    def get_progress_summary(self) -> str:
        """Get a human-readable progress summary.

        Returns:
            Summary string with processing statistics.
        """
        lines = []

        if self.state.last_run:
            lines.append(f"Last run: {self.state.last_run}")

        if self.state.since_date:
            lines.append(f"Processing emails since: {self.state.since_date}")

        lines.append(f"Messages processed: {self.state.total_processed}")
        lines.append(f"Rows written to sheet: {self.state.total_written}")
        lines.append(f"Unique messages tracked: {len(self.state.processed_ids)}")

        return "\n".join(lines)

    def reset(self) -> None:
        """Reset state to initial values.

        Use with caution - this clears all tracking data.
        """
        self.state = ProcessingState()
        self._unsaved_count = 0

        # Delete state file if it exists
        if self.state_file.exists():
            try:
                self.state_file.unlink()
                logger.info("State file deleted")
            except Exception as e:
                logger.warning(f"Failed to delete state file: {e}")

    def has_previous_session(self) -> bool:
        """Check if there's a previous incomplete session.

        Returns:
            True if there's state from a previous run.
        """
        return self.state_file.exists() and len(self.state.processed_ids) > 0

    def get_resume_prompt(self) -> str:
        """Get a prompt message for resuming a previous session.

        Returns:
            User-friendly prompt about previous session.
        """
        if not self.has_previous_session():
            return ""

        return (
            f"\n📋 Previous session found:\n"
            f"   - {len(self.state.processed_ids)} messages already processed\n"
            f"   - Last run: {self.state.last_run or 'Unknown'}\n"
            f"   - Since date: {self.state.since_date or 'Not set'}\n"
            f"\nResume this session? (y/n): "
        )
