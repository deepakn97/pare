from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from pare.main import app

runner = CliRunner()


def test_scenarios_help_includes_registered_commands() -> None:
    result = runner.invoke(app, ["scenarios", "--help"])

    assert result.exit_code == 0, result.output
    assert "list" in result.output
    assert "split" in result.output
    assert "splits" in result.output
    assert "check-ids-file" in result.output
    assert "generate" in result.output


def test_scenarios_root_list_shortcut(monkeypatch) -> None:
    def fake_list_scenarios(
        scenarios_dirs: list[str] | None = None,
        apps: list[str] | None = None,
        id_contains: str | None = None,
        limit: int | None = None,
        as_json: bool = False,
    ) -> None:
        assert scenarios_dirs == ["generator"]
        assert apps == ["StatefulEmailApp"]
        assert id_contains == "meeting"
        assert limit == 1
        assert as_json is True

    monkeypatch.setattr("pare.cli.scenarios.list_scenarios", fake_list_scenarios)

    result = runner.invoke(
        app,
        [
            "scenarios",
            "--list",
            "--scenarios-dir",
            "generator",
            "--apps",
            "StatefulEmailApp",
            "--id-contains",
            "meeting",
            "--limit",
            "1",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output


def test_splits_json_reports_available_split_files(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "full.txt").write_text("scenario_a\n", encoding="utf-8")
    (tmp_path / "ablation.txt").write_text("scenario_b\n", encoding="utf-8")
    monkeypatch.setenv("PARE_BENCHMARK_SPLITS_DIR", str(tmp_path))

    result = runner.invoke(app, ["scenarios", "splits", "--json"])

    assert result.exit_code == 0, result.output
    assert '"available_splits": [' in result.output
    assert '"ablation"' in result.output
    assert '"full"' in result.output
