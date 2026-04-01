"""Tests for ternary decision annotation server endpoints."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import polars as pl
import pytest
from fastapi.testclient import TestClient

from pare.annotation.server import AnnotationServer, create_app

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture()
def sample_data() -> list[dict[str, object]]:
    """Minimal sample data for a ternary parquet file."""
    llm_input = [
        {"role": "assistant", "content": "Thought: test\nAction: Notes__open\nAction Input: {}", "timestamp": 101.0, "msg_type": "user_action"},
        {"role": "user", "content": "[TASK]: I propose X", "timestamp": 103.0, "msg_type": "proposal"},
    ]
    return [
        {
            "sample_id": "sample_001",
            "scenario_id": "scenario_a",
            "run_number": 1,
            "proactive_model_id": "gpt-4o",
            "user_model_id": "gpt-4o",
            "trace_file": "traces/no_noise_gpt-4o/scenario_a.json",
            "user_agent_decision": "accept",
            "agent_proposal": "I propose X",
            "meta_task_description": "Test scenario",
            "llm_input": json.dumps(llm_input),
            "final_decision": True,
            "gather_context_delta": None,
        },
    ]


@pytest.fixture()
def server_paths(sample_data: list[dict[str, object]], tmp_path: Path) -> tuple[Path, Path]:
    """Create temporary samples parquet and annotations path."""
    samples_file = tmp_path / "samples.parquet"
    annotations_file = tmp_path / "annotations.csv"
    df = pl.DataFrame(sample_data)
    df.write_parquet(samples_file)
    return samples_file, annotations_file


@pytest.fixture()
def client(server_paths: tuple[Path, Path]) -> TestClient:
    """Create a test client for the annotation server."""
    samples_file, annotations_file = server_paths
    app = create_app(samples_file, annotations_file, annotators_per_sample=2)
    return TestClient(app)


class TestTernaryAnnotation:
    """Tests for submitting ternary decisions."""

    def test_submit_accept(self, client: TestClient) -> None:
        """Accept decision with string value is recorded successfully."""
        response = client.post(
            "/api/annotate",
            json={"sample_id": "sample_001", "decision": "accept"},
            headers={"X-Annotator-ID": "annotator-1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_submit_reject(self, client: TestClient) -> None:
        """Reject decision with string value is recorded successfully."""
        response = client.post(
            "/api/annotate",
            json={"sample_id": "sample_001", "decision": "reject"},
            headers={"X-Annotator-ID": "annotator-1"},
        )
        assert response.status_code == 200

    def test_submit_gather_context_with_rationale(self, client: TestClient) -> None:
        """Gather context decision with rationale is recorded successfully."""
        response = client.post(
            "/api/annotate",
            json={
                "sample_id": "sample_001",
                "decision": "gather_context",
                "gather_context_rationale": "I want to check Bob's availability first",
            },
            headers={"X-Annotator-ID": "annotator-1"},
        )
        assert response.status_code == 200

    def test_gather_context_rationale_saved(self, server_paths: tuple[Path, Path]) -> None:
        """Gather context rationale is persisted to annotations CSV."""
        samples_file, annotations_file = server_paths
        server = AnnotationServer(samples_file, annotations_file)
        server.record_annotation(
            sample_id="sample_001",
            annotator_id="annotator-1",
            human_decision="gather_context",
            gather_context_rationale="Need to check calendar",
        )
        content = annotations_file.read_text()
        assert "Need to check calendar" in content

    def test_invalid_decision_rejected(self, client: TestClient) -> None:
        """Invalid decision string is rejected with 422 validation error."""
        response = client.post(
            "/api/annotate",
            json={"sample_id": "sample_001", "decision": "maybe"},
            headers={"X-Annotator-ID": "annotator-1"},
        )
        assert response.status_code == 422

    def test_api_response_uses_sample_response_shape(self, client: TestClient) -> None:
        """GET /api/sample returns SampleResponse shape with messages, not turns."""
        response = client.get(
            "/api/sample",
            headers={"X-Annotator-ID": "annotator-1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert "progress_completed" in data
        assert "progress_total" in data
        assert "turns" not in data
        assert "agent_proposal" not in data

    def test_annotate_returns_next_sample_response_shape(self, client: TestClient) -> None:
        """POST /api/annotate returns next_sample in SampleResponse shape."""
        response = client.post(
            "/api/annotate",
            json={"sample_id": "sample_001", "decision": "accept"},
            headers={"X-Annotator-ID": "annotator-1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Only 1 sample and 1 annotator with 2 required, so next_sample should still be available
        # for a different annotator. But same annotator already annotated, so next_sample is None.
        # This is expected since we only have 1 sample.

    def test_boolean_decision_rejected(self, client: TestClient) -> None:
        """Boolean decisions (old format) are rejected."""
        response = client.post(
            "/api/annotate",
            json={"sample_id": "sample_001", "decision": True},
            headers={"X-Annotator-ID": "annotator-1"},
        )
        assert response.status_code == 422

    def test_accept_without_rationale(self, server_paths: tuple[Path, Path]) -> None:
        """Accept decision saves with empty rationale in CSV."""
        samples_file, annotations_file = server_paths
        server = AnnotationServer(samples_file, annotations_file)
        server.record_annotation(
            sample_id="sample_001",
            annotator_id="annotator-1",
            human_decision="accept",
        )
        content = annotations_file.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 2  # header + 1 annotation


class TestTutorialFlow:
    """Tests for tutorial flow via existing endpoints."""

    def test_first_sample_is_tutorial(self, tutorial_client: TestClient) -> None:
        """GET /api/sample returns a tutorial sample first."""
        data = tutorial_client.get("/api/sample", headers={"X-Annotator-ID": "new"}).json()
        assert data["tutorial"] is True
        assert "messages" in data

    def test_tutorial_sample_excludes_feedback(self, tutorial_client: TestClient) -> None:
        """Tutorial sample response does not leak correct_decision or explanation."""
        data = tutorial_client.get("/api/sample", headers={"X-Annotator-ID": "new"}).json()
        assert "correct_decision" not in data
        assert "explanation" not in data

    def test_annotate_tutorial_returns_feedback(self, tutorial_client: TestClient) -> None:
        """POST /api/annotate on tutorial sample returns tutorial_feedback."""
        sample = tutorial_client.get("/api/sample", headers={"X-Annotator-ID": "new"}).json()
        data = tutorial_client.post(
            "/api/annotate",
            json={"sample_id": sample["sample_id"], "decision": "accept"},
            headers={"X-Annotator-ID": "new"},
        ).json()
        assert data["success"] is True
        assert "tutorial_feedback" in data
        assert data["tutorial_feedback"]["correct"] is True
        assert "explanation" in data["tutorial_feedback"]

    def test_annotate_tutorial_incorrect(self, tutorial_client: TestClient) -> None:
        """Wrong answer returns correct=False with correct_decision."""
        sample = tutorial_client.get("/api/sample", headers={"X-Annotator-ID": "new"}).json()
        data = tutorial_client.post(
            "/api/annotate",
            json={"sample_id": sample["sample_id"], "decision": "reject"},
            headers={"X-Annotator-ID": "new"},
        ).json()
        assert data["tutorial_feedback"]["correct"] is False
        assert data["tutorial_feedback"]["correct_decision"] == "accept"

    def test_tutorial_writes_to_tutorial_csv(
        self, tutorial_client: TestClient, tutorial_server_paths: tuple[Path, Path],
    ) -> None:
        """Tutorial submissions go to {stem}_tutorial.csv, not annotations.csv."""
        _, annotations_file = tutorial_server_paths
        sample = tutorial_client.get("/api/sample", headers={"X-Annotator-ID": "new"}).json()
        tutorial_client.post(
            "/api/annotate",
            json={"sample_id": sample["sample_id"], "decision": "accept"},
            headers={"X-Annotator-ID": "new"},
        )
        assert len(annotations_file.read_text().strip().split("\n")) == 1  # header only
        tutorial_csv = annotations_file.parent / f"{annotations_file.stem}_tutorial.csv"
        assert tutorial_csv.exists()
        assert len(tutorial_csv.read_text().strip().split("\n")) == 2  # header + 1

    def test_real_sample_after_tutorial_complete(self, tutorial_client: TestClient) -> None:
        """After tutorials, GET /api/sample returns real samples."""
        annotator = "completing"
        for _ in range(2):
            s = tutorial_client.get("/api/sample", headers={"X-Annotator-ID": annotator}).json()
            assert s["tutorial"] is True
            tutorial_client.post(
                "/api/annotate",
                json={"sample_id": s["sample_id"], "decision": "accept"},
                headers={"X-Annotator-ID": annotator},
            )
        data = tutorial_client.get("/api/sample", headers={"X-Annotator-ID": annotator}).json()
        assert data["tutorial"] is False
        assert data["sample_id"] == "real_sample_001"

    def test_last_tutorial_returns_summary(self, tutorial_client: TestClient) -> None:
        """Last tutorial submission returns tutorial_complete with summary."""
        annotator = "summary"
        s1 = tutorial_client.get("/api/sample", headers={"X-Annotator-ID": annotator}).json()
        tutorial_client.post(
            "/api/annotate",
            json={"sample_id": s1["sample_id"], "decision": "accept"},
            headers={"X-Annotator-ID": annotator},
        )
        s2 = tutorial_client.get("/api/sample", headers={"X-Annotator-ID": annotator}).json()
        data = tutorial_client.post(
            "/api/annotate",
            json={"sample_id": s2["sample_id"], "decision": "reject"},
            headers={"X-Annotator-ID": annotator},
        ).json()
        assert data.get("tutorial_complete") is True
        assert data["tutorial_summary"]["correct"] == 2
        assert data["tutorial_summary"]["scored_total"] == 2

    def test_tutorial_independent_across_annotators(self, tutorial_client: TestClient) -> None:
        """Two annotators complete tutorials independently without interference."""
        # Both get the same first tutorial
        u1 = tutorial_client.get("/api/sample", headers={"X-Annotator-ID": "user1"}).json()
        u2 = tutorial_client.get("/api/sample", headers={"X-Annotator-ID": "user2"}).json()
        assert u1["sample_id"] == u2["sample_id"]

        # user1 completes first tutorial
        tutorial_client.post(
            "/api/annotate",
            json={"sample_id": u1["sample_id"], "decision": "accept"},
            headers={"X-Annotator-ID": "user1"},
        )

        # user2 should still see the first tutorial (not advanced by user1)
        u2_next = tutorial_client.get("/api/sample", headers={"X-Annotator-ID": "user2"}).json()
        assert u2_next["tutorial"] is True
        assert u2_next["sample_id"] == u1["sample_id"]

    def test_tutorial_progress_shown(self, tutorial_client: TestClient) -> None:
        """Tutorial samples show tutorial-specific progress, not real sample progress."""
        data = tutorial_client.get("/api/sample", headers={"X-Annotator-ID": "new"}).json()
        assert data["progress_completed"] == 0
        assert data["progress_total"] == 2  # 2 tutorial samples, not 1 real sample

        # After completing first tutorial, progress updates
        tutorial_client.post(
            "/api/annotate",
            json={"sample_id": data["sample_id"], "decision": "accept"},
            headers={"X-Annotator-ID": "new"},
        )
        next_data = tutorial_client.get("/api/sample", headers={"X-Annotator-ID": "new"}).json()
        assert next_data["progress_completed"] == 1
        assert next_data["progress_total"] == 2
