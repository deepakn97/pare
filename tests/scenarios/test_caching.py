"""Tests for PAS cache invalidation of results with exceptions.

Cached results with any exception_type should be treated as cache misses,
forcing a rerun of the scenario.
"""

from unittest.mock import MagicMock, patch

from pas.scenarios.utils.caching import (
    CachedScenarioResult,
    maybe_load_cached_result,
)


def _make_cached_result(
    success=True,
    exception_type=None,
    exception_message=None,
    config_hash="abc123",
    scenario_hash="def456",
):
    """Create a CachedScenarioResult for testing."""
    return CachedScenarioResult(
        success=success,
        exception_type=exception_type,
        exception_message=exception_message,
        export_path=None,
        rationale=None,
        duration=1.0,
        proposal_count=0,
        acceptance_count=0,
        read_only_actions=0,
        write_actions=0,
        number_of_turns=1,
        cache_key="test_scenario_run_1_abc123",
        scenario_id="test_scenario",
        run_number=1,
        config_hash=config_hash,
        scenario_hash=scenario_hash,
    )


def _make_mock_config():
    config = MagicMock()
    config.get_config_hash.return_value = "abc123"
    return config


def _make_mock_scenario():
    scenario = MagicMock()
    scenario.scenario_id = "test_scenario"
    scenario.run_number = 1
    scenario.seed = 0
    scenario.nb_turns = 10
    scenario.config = None
    scenario.additional_system_prompt = None
    scenario.tags = []
    scenario.events = []
    return scenario


class TestCacheExceptionInvalidation:
    def test_cached_result_with_exception_is_skipped(self, tmp_path):
        """Cached results with exceptions should be treated as cache miss."""
        cached = _make_cached_result(
            success=False,
            exception_type="AttributeError",
            exception_message="'NoneType' object has no attribute 'lower'",
        )
        cache_file = tmp_path / f"{cached.cache_key}.json"
        cache_file.write_text(cached.to_json())

        with (
            patch("pas.scenarios.utils.caching._get_cache_dir", return_value=tmp_path),
            patch("pas.scenarios.utils.caching._generate_config_hash", return_value="abc123"),
            patch("pas.scenarios.utils.caching._generate_scenario_hash", return_value="def456"),
        ):
            result = maybe_load_cached_result(_make_mock_config(), _make_mock_scenario())

        assert result is None

    def test_cached_result_without_exception_is_loaded(self, tmp_path):
        """Cached results without exceptions should be loaded normally."""
        cached = _make_cached_result(success=True)
        cache_file = tmp_path / f"{cached.cache_key}.json"
        cache_file.write_text(cached.to_json())

        with (
            patch("pas.scenarios.utils.caching._get_cache_dir", return_value=tmp_path),
            patch("pas.scenarios.utils.caching._generate_config_hash", return_value="abc123"),
            patch("pas.scenarios.utils.caching._generate_scenario_hash", return_value="def456"),
        ):
            result = maybe_load_cached_result(_make_mock_config(), _make_mock_scenario())

        assert result is not None
        assert result.success is True

    def test_cached_result_with_server_error_is_skipped(self, tmp_path):
        """Cached results with ServerError should be treated as cache miss."""
        cached = _make_cached_result(
            success=False,
            exception_type="ServerError",
            exception_message="RateLimitError: rate limit exceeded",
        )
        cache_file = tmp_path / f"{cached.cache_key}.json"
        cache_file.write_text(cached.to_json())

        with (
            patch("pas.scenarios.utils.caching._get_cache_dir", return_value=tmp_path),
            patch("pas.scenarios.utils.caching._generate_config_hash", return_value="abc123"),
            patch("pas.scenarios.utils.caching._generate_scenario_hash", return_value="def456"),
        ):
            result = maybe_load_cached_result(_make_mock_config(), _make_mock_scenario())

        assert result is None

    def test_cached_result_with_failure_but_no_exception_is_loaded(self, tmp_path):
        """Cached results that failed validation (success=False) but have no exception should be loaded."""
        cached = _make_cached_result(success=False, exception_type=None)
        cache_file = tmp_path / f"{cached.cache_key}.json"
        cache_file.write_text(cached.to_json())

        with (
            patch("pas.scenarios.utils.caching._get_cache_dir", return_value=tmp_path),
            patch("pas.scenarios.utils.caching._generate_config_hash", return_value="abc123"),
            patch("pas.scenarios.utils.caching._generate_scenario_hash", return_value="def456"),
        ):
            result = maybe_load_cached_result(_make_mock_config(), _make_mock_scenario())

        assert result is not None
        assert result.success is False
