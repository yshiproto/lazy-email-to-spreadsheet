"""Tests for state management module."""

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from lazy_email.state import ProcessingState, StateManager

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.fixtures import FixtureRequest
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture


@pytest.fixture
def temp_state_file(tmp_path: Path) -> Path:
    """Create a temporary state file path.

    Returns:
        Path to temporary state file.
    """
    return tmp_path / "test_state.json"


@pytest.fixture
def state_manager(temp_state_file: Path) -> StateManager:
    """Create a StateManager with temporary file.

    Returns:
        StateManager instance using temp file.
    """
    return StateManager(state_file=temp_state_file, save_interval=5)


class TestProcessingState:
    """Tests for ProcessingState model."""

    def test_default_values(self) -> None:
        """Test ProcessingState initializes with correct defaults."""
        state = ProcessingState()

        assert state.processed_ids == set()
        assert state.last_processed_id is None
        assert state.last_run is None
        assert state.since_date is None
        assert state.total_processed == 0
        assert state.total_written == 0

    def test_with_values(self) -> None:
        """Test ProcessingState with provided values."""
        state = ProcessingState(
            processed_ids={"id1", "id2"},
            last_processed_id="id2",
            last_run="2026-01-13T10:00:00",
            since_date="2026-01-01",
            total_processed=2,
            total_written=2,
        )

        assert len(state.processed_ids) == 2
        assert "id1" in state.processed_ids
        assert state.last_processed_id == "id2"


class TestStateManagerInit:
    """Tests for StateManager initialization."""

    def test_init_with_custom_file(self, temp_state_file: Path) -> None:
        """Test StateManager with custom state file path."""
        manager = StateManager(state_file=temp_state_file)

        assert manager.state_file == temp_state_file
        assert manager.save_interval == 10  # Default

    def test_init_with_custom_interval(self, temp_state_file: Path) -> None:
        """Test StateManager with custom save interval."""
        manager = StateManager(state_file=temp_state_file, save_interval=25)

        assert manager.save_interval == 25


class TestStateManagerLoadSave:
    """Tests for state loading and saving."""

    def test_load_no_file(self, state_manager: StateManager) -> None:
        """Test loading when no state file exists."""
        result = state_manager.load()

        assert result is False
        assert len(state_manager.state.processed_ids) == 0

    def test_save_and_load(self, state_manager: StateManager) -> None:
        """Test saving and loading state."""
        # Add some state
        state_manager.mark_processed("msg1", auto_save=False)
        state_manager.mark_processed("msg2", auto_save=False)
        state_manager.set_since_date("2026-01-01")
        state_manager.save()

        # Create new manager and load
        new_manager = StateManager(
            state_file=state_manager.state_file, save_interval=5
        )
        result = new_manager.load()

        assert result is True
        assert len(new_manager.state.processed_ids) == 2
        assert "msg1" in new_manager.state.processed_ids
        assert "msg2" in new_manager.state.processed_ids
        assert new_manager.state.since_date == "2026-01-01"

    def test_load_corrupted_file(
        self, temp_state_file: Path, state_manager: StateManager
    ) -> None:
        """Test loading corrupted state file returns False."""
        # Write invalid JSON
        temp_state_file.write_text("{ invalid json }")

        result = state_manager.load()

        assert result is False

    def test_save_updates_last_run(self, state_manager: StateManager) -> None:
        """Test that saving updates last_run timestamp."""
        assert state_manager.state.last_run is None

        state_manager.save()

        assert state_manager.state.last_run is not None
        assert "2026" in state_manager.state.last_run


class TestStateManagerMarkProcessed:
    """Tests for marking messages as processed."""

    def test_mark_processed(self, state_manager: StateManager) -> None:
        """Test marking a message as processed."""
        state_manager.mark_processed("msg123", auto_save=False)

        assert "msg123" in state_manager.state.processed_ids
        assert state_manager.state.last_processed_id == "msg123"
        assert state_manager.state.total_processed == 1

    def test_mark_processed_auto_save(self, state_manager: StateManager) -> None:
        """Test auto-save after save_interval messages."""
        # save_interval is 5
        for i in range(4):
            state_manager.mark_processed(f"msg{i}", auto_save=True)

        # File should not exist yet (4 < 5)
        assert not state_manager.state_file.exists()

        # 5th message should trigger save
        state_manager.mark_processed("msg4", auto_save=True)

        assert state_manager.state_file.exists()

    def test_is_processed(self, state_manager: StateManager) -> None:
        """Test checking if message is processed."""
        state_manager.mark_processed("msg123", auto_save=False)

        assert state_manager.is_processed("msg123") is True
        assert state_manager.is_processed("msg456") is False


class TestStateManagerGetUnprocessed:
    """Tests for filtering unprocessed messages."""

    def test_get_unprocessed_all_new(self, state_manager: StateManager) -> None:
        """Test with all new messages."""
        message_ids = ["msg1", "msg2", "msg3"]

        result = state_manager.get_unprocessed(message_ids)

        assert result == ["msg1", "msg2", "msg3"]

    def test_get_unprocessed_some_processed(
        self, state_manager: StateManager
    ) -> None:
        """Test filtering out processed messages."""
        state_manager.mark_processed("msg1", auto_save=False)
        state_manager.mark_processed("msg3", auto_save=False)

        message_ids = ["msg1", "msg2", "msg3", "msg4"]
        result = state_manager.get_unprocessed(message_ids)

        assert result == ["msg2", "msg4"]

    def test_get_unprocessed_all_processed(
        self, state_manager: StateManager
    ) -> None:
        """Test when all messages are already processed."""
        state_manager.mark_processed("msg1", auto_save=False)
        state_manager.mark_processed("msg2", auto_save=False)

        message_ids = ["msg1", "msg2"]
        result = state_manager.get_unprocessed(message_ids)

        assert result == []


class TestStateManagerMarkWritten:
    """Tests for tracking written rows."""

    def test_mark_written_single(self, state_manager: StateManager) -> None:
        """Test marking single row as written."""
        state_manager.mark_written()

        assert state_manager.state.total_written == 1

    def test_mark_written_batch(self, state_manager: StateManager) -> None:
        """Test marking batch of rows as written."""
        state_manager.mark_written(10)

        assert state_manager.state.total_written == 10

    def test_mark_written_accumulates(self, state_manager: StateManager) -> None:
        """Test that written count accumulates."""
        state_manager.mark_written(5)
        state_manager.mark_written(3)
        state_manager.mark_written(2)

        assert state_manager.state.total_written == 10


class TestStateManagerProgressSummary:
    """Tests for progress summary."""

    def test_get_progress_summary(self, state_manager: StateManager) -> None:
        """Test getting progress summary."""
        state_manager.set_since_date("2026-01-01")
        state_manager.mark_processed("msg1", auto_save=False)
        state_manager.mark_processed("msg2", auto_save=False)
        state_manager.mark_written(2)
        state_manager.save()

        summary = state_manager.get_progress_summary()

        assert "2026-01-01" in summary
        assert "Messages processed: 2" in summary
        assert "Rows written to sheet: 2" in summary
        assert "Unique messages tracked: 2" in summary


class TestStateManagerReset:
    """Tests for state reset."""

    def test_reset_clears_state(self, state_manager: StateManager) -> None:
        """Test that reset clears all state."""
        state_manager.mark_processed("msg1", auto_save=False)
        state_manager.mark_written(5)
        state_manager.save()

        state_manager.reset()

        assert len(state_manager.state.processed_ids) == 0
        assert state_manager.state.total_processed == 0
        assert state_manager.state.total_written == 0

    def test_reset_deletes_file(self, state_manager: StateManager) -> None:
        """Test that reset deletes the state file."""
        state_manager.mark_processed("msg1", auto_save=False)
        state_manager.save()

        assert state_manager.state_file.exists()

        state_manager.reset()

        assert not state_manager.state_file.exists()


class TestStateManagerSessionDetection:
    """Tests for session detection."""

    def test_has_previous_session_false(self, state_manager: StateManager) -> None:
        """Test no previous session when file doesn't exist."""
        assert state_manager.has_previous_session() is False

    def test_has_previous_session_true(self, state_manager: StateManager) -> None:
        """Test detecting previous session."""
        state_manager.mark_processed("msg1", auto_save=False)
        state_manager.save()
        state_manager.load()

        assert state_manager.has_previous_session() is True

    def test_get_resume_prompt_no_session(self, state_manager: StateManager) -> None:
        """Test resume prompt when no previous session."""
        prompt = state_manager.get_resume_prompt()

        assert prompt == ""

    def test_get_resume_prompt_with_session(
        self, state_manager: StateManager
    ) -> None:
        """Test resume prompt with previous session."""
        state_manager.mark_processed("msg1", auto_save=False)
        state_manager.set_since_date("2026-01-01")
        state_manager.save()
        state_manager.load()

        prompt = state_manager.get_resume_prompt()

        assert "Previous session found" in prompt
        assert "1 messages already processed" in prompt
        assert "2026-01-01" in prompt


class TestStateFileFormat:
    """Tests for state file JSON format."""

    def test_state_file_is_valid_json(self, state_manager: StateManager) -> None:
        """Test that saved state file is valid JSON."""
        state_manager.mark_processed("msg1", auto_save=False)
        state_manager.save()

        with open(state_manager.state_file) as f:
            data = json.load(f)

        assert "processed_ids" in data
        assert "last_processed_id" in data
        assert "total_processed" in data

    def test_state_file_processed_ids_as_list(
        self, state_manager: StateManager
    ) -> None:
        """Test that processed_ids is saved as a list (JSON-compatible)."""
        state_manager.mark_processed("msg1", auto_save=False)
        state_manager.mark_processed("msg2", auto_save=False)
        state_manager.save()

        with open(state_manager.state_file) as f:
            data = json.load(f)

        assert isinstance(data["processed_ids"], list)
        assert len(data["processed_ids"]) == 2
