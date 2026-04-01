"""Tests for retryable error detection and cache write retry."""

from __future__ import annotations

import errno
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path

from pas.multi_scenario_runner import _is_retryable_error
from pas.scenarios.validation_result import PASScenarioValidationResult


class TestIsRetryableError:
    """Tests for the _is_retryable_error helper function."""

    def test_emfile_error_is_retryable(self) -> None:
        """OSError with EMFILE errno should be retryable."""
        error = OSError(errno.EMFILE, "Too many open files")
        assert _is_retryable_error(error=error, result=None) is True

    def test_enfile_error_is_retryable(self) -> None:
        """OSError with ENFILE errno should be retryable."""
        error = OSError(errno.ENFILE, "Too many open files in system")
        assert _is_retryable_error(error=error, result=None) is True

    def test_enomem_error_is_retryable(self) -> None:
        """OSError with ENOMEM errno should be retryable."""
        error = OSError(errno.ENOMEM, "Cannot allocate memory")
        assert _is_retryable_error(error=error, result=None) is True

    def test_other_oserror_not_retryable(self) -> None:
        """OSError with non-resource errno should not be retryable."""
        error = OSError(errno.ENOENT, "No such file or directory")
        assert _is_retryable_error(error=error, result=None) is False

    def test_type_error_not_retryable(self) -> None:
        """Non-OSError exceptions should not be retryable."""
        error = TypeError("argument of type 'NoneType' is not iterable")
        assert _is_retryable_error(error=error, result=None) is False

    def test_none_error_not_retryable(self) -> None:
        """None error should not be retryable."""
        assert _is_retryable_error(error=None, result=None) is False

    def test_retryable_error_in_result_exception(self) -> None:
        """OSError wrapped inside result.exception should be retryable."""
        result = PASScenarioValidationResult(
            success=False,
            exception=OSError(errno.EMFILE, "Too many open files"),
        )
        assert _is_retryable_error(error=None, result=result) is True

    def test_non_retryable_error_in_result_exception(self) -> None:
        """Non-retryable exception in result should not be retryable."""
        result = PASScenarioValidationResult(
            success=False,
            exception=TypeError("bad type"),
        )
        assert _is_retryable_error(error=None, result=result) is False

    def test_error_takes_precedence_over_result(self) -> None:
        """When both error and result have exceptions, error is checked."""
        error = OSError(errno.EMFILE, "Too many open files")
        result = PASScenarioValidationResult(
            success=False,
            exception=TypeError("bad type"),
        )
        assert _is_retryable_error(error=error, result=result) is True


class TestCacheWriteRetry:
    """Tests for cache write retry on transient OS errors."""

    def test_cache_write_retries_on_emfile(self, tmp_path: Path) -> None:
        """write_cached_result should retry on EMFILE errors."""
        from pas.scenarios.utils.caching import CachedScenarioResult, write_cached_result

        mock_config = MagicMock()
        mock_scenario = MagicMock()
        mock_scenario.scenario_id = "test_scenario"
        mock_result = PASScenarioValidationResult(success=True)

        # Create a real CachedScenarioResult to avoid asdict issues with mocks
        fake_cached = CachedScenarioResult(
            success=True,
            exception_type=None,
            exception_message=None,
            export_path=None,
            rationale=None,
            duration=1.0,
            proposal_count=0,
            acceptance_count=0,
            read_only_actions=0,
            write_actions=0,
            number_of_turns=1,
            cache_key="test_scenario_abc123",
            scenario_id="test_scenario",
            run_number=None,
            config_hash="abc123",
            scenario_hash="def456",
        )

        call_count = 0
        original_open = open

        def mock_open_fn(path: str, mode: str = "r", *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            nonlocal call_count
            if mode == "w" and str(path).endswith(".json"):
                call_count += 1
                if call_count <= 2:
                    raise OSError(errno.EMFILE, "Too many open files")
            return original_open(path, mode, *args, **kwargs)

        with (
            patch("pas.scenarios.utils.caching._get_cache_dir", return_value=tmp_path),
            patch("pas.scenarios.utils.caching.CachedScenarioResult.from_scenario_result", return_value=fake_cached),
            patch("pas.scenarios.utils.caching._get_cache_file_path", return_value=tmp_path / "test.json"),
            patch("builtins.open", side_effect=mock_open_fn),
            patch("pas.scenarios.utils.caching.time.sleep"),
        ):
            write_cached_result(mock_config, mock_scenario, mock_result)

        assert call_count == 3  # 2 failures + 1 success
