"""FastAPI server for the annotation interface."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

import polars as pl
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from pas.annotation.models import Annotation, Sample

logger = logging.getLogger(__name__)

# Templates directory
TEMPLATES_DIR = Path(__file__).parent / "templates"


class AnnotationRequest(BaseModel):
    """Request body for submitting an annotation."""

    sample_id: str
    decision: bool


class AnnotationServer:
    """Server for managing annotation state and serving samples."""

    def __init__(self, data_dir: Path, annotators_per_sample: int = 2) -> None:
        """Initialize the annotation server.

        Args:
            data_dir: Directory containing samples.parquet and annotations.csv.
            annotators_per_sample: Number of annotations required per sample.
        """
        self.data_dir = data_dir
        self.annotators_per_sample = annotators_per_sample

        # Load samples
        samples_file = data_dir / "samples.parquet"
        if not samples_file.exists():
            raise FileNotFoundError(f"Samples file not found: {samples_file}. Run 'pas annotation sample' first.")

        self.samples_df = pl.read_parquet(samples_file)
        logger.info(f"Loaded {len(self.samples_df)} samples from {samples_file}")

        # Build sample lookup
        self._samples: dict[str, Sample] = {}
        for row in self.samples_df.iter_rows(named=True):
            sample = Sample(**row)
            self._samples[sample.sample_id] = sample

        # Initialize annotations file
        self.annotations_file = data_dir / "annotations.csv"
        if not self.annotations_file.exists():
            with open(self.annotations_file, "w") as f:
                f.write(Annotation.csv_header())
            logger.info(f"Created annotations file: {self.annotations_file}")

        # In-memory annotation tracking
        self._annotation_counts: dict[str, int] = {}  # sample_id -> count
        self._user_annotations: dict[str, set[str]] = {}  # user_id -> set of sample_ids
        self._lock = threading.Lock()

        # Load existing annotations
        self._load_annotation_state()

    def _load_annotation_state(self) -> None:
        """Load existing annotations into memory."""
        if not self.annotations_file.exists():
            return

        try:
            annotations_df = pl.read_csv(self.annotations_file)
            if len(annotations_df) == 0:
                return

            # Count annotations per sample
            for sample_id in annotations_df["sample_id"].unique().to_list():
                count = len(annotations_df.filter(pl.col("sample_id") == sample_id))
                self._annotation_counts[sample_id] = count

            # Track which samples each user has annotated
            for row in annotations_df.iter_rows(named=True):
                user_id = row["annotator_id"]
                sample_id = row["sample_id"]
                if user_id not in self._user_annotations:
                    self._user_annotations[user_id] = set()
                self._user_annotations[user_id].add(sample_id)

            logger.info(
                f"Loaded {len(annotations_df)} existing annotations from {len(self._user_annotations)} annotators"
            )

        except Exception as e:
            logger.warning(f"Failed to load existing annotations: {e}")

    def get_sample(self, sample_id: str) -> Sample | None:
        """Get a sample by ID."""
        return self._samples.get(sample_id)

    def get_next_sample(self, annotator_id: str) -> Sample | None:
        """Get the next available sample for an annotator.

        Args:
            annotator_id: The annotator's anonymous ID.

        Returns:
            The next sample to annotate, or None if all done.
        """
        user_done = self._user_annotations.get(annotator_id, set())

        for sample_id, sample in self._samples.items():
            # Skip if user already annotated
            if sample_id in user_done:
                continue

            # Skip if sample has enough annotations
            if self._annotation_counts.get(sample_id, 0) >= self.annotators_per_sample:
                continue

            return sample

        return None

    def record_annotation(
        self,
        sample_id: str,
        annotator_id: str,
        human_decision: bool,
    ) -> bool:
        """Record an annotation.

        Args:
            sample_id: The sample being annotated.
            annotator_id: The annotator's anonymous ID.
            human_decision: The human's accept/reject decision.

        Returns:
            True if recorded successfully.

        Raises:
            ValueError: If sample not found or already annotated by this user.
        """
        sample = self.get_sample(sample_id)
        if not sample:
            raise ValueError(f"Sample not found: {sample_id}")

        with self._lock:
            # Check if user already annotated this sample
            if annotator_id in self._user_annotations and sample_id in self._user_annotations[annotator_id]:
                raise ValueError(f"User {annotator_id} already annotated sample {sample_id}")

            # Create annotation
            annotation = Annotation.create(
                sample_id=sample_id,
                annotator_id=annotator_id,
                human_decision=human_decision,
            )

            # Append to file
            with open(self.annotations_file, "a") as f:
                f.write(annotation.to_csv_row())

            # Update in-memory state
            self._annotation_counts[sample_id] = self._annotation_counts.get(sample_id, 0) + 1

            if annotator_id not in self._user_annotations:
                self._user_annotations[annotator_id] = set()
            self._user_annotations[annotator_id].add(sample_id)

            logger.info(
                f"Recorded annotation: sample={sample_id[:20]}..., user={annotator_id[:8]}..., decision={human_decision}"
            )

        return True

    def get_progress(self, annotator_id: str) -> dict[str, int]:
        """Get progress statistics for an annotator.

        Args:
            annotator_id: The annotator's anonymous ID.

        Returns:
            Dictionary with completed and total counts.
        """
        # Count samples this user can annotate (not yet annotated by them, not yet complete)
        user_done = self._user_annotations.get(annotator_id, set())

        total = 0
        completed = len(user_done)

        for sample_id in self._samples:
            if self._annotation_counts.get(sample_id, 0) < self.annotators_per_sample:
                total += 1

        # Add already completed by this user
        total = max(total, completed)

        return {
            "completed": completed,
            "total": total,
        }

    def get_overall_stats(self) -> dict[str, Any]:
        """Get overall annotation statistics."""
        total_samples = len(self._samples)

        complete_count = sum(1 for count in self._annotation_counts.values() if count >= self.annotators_per_sample)
        in_progress_count = sum(
            1 for count in self._annotation_counts.values() if 0 < count < self.annotators_per_sample
        )
        not_started_count = total_samples - len(self._annotation_counts)

        total_annotations = sum(self._annotation_counts.values())
        unique_annotators = len(self._user_annotations)

        return {
            "total_samples": total_samples,
            "complete": complete_count,
            "in_progress": in_progress_count,
            "not_started": not_started_count,
            "total_annotations": total_annotations,
            "unique_annotators": unique_annotators,
            "annotators_per_sample": self.annotators_per_sample,
        }


def create_app(data_dir: Path, annotators_per_sample: int = 2) -> FastAPI:  # noqa: C901
    """Create the FastAPI application.

    Args:
        data_dir: Directory containing samples and annotations.
        annotators_per_sample: Number of annotations required per sample.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(title="PAS Annotation Interface")

    # Initialize server
    server = AnnotationServer(data_dir, annotators_per_sample)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> FileResponse:
        """Serve the main annotation UI."""
        return FileResponse(TEMPLATES_DIR / "index.html")

    @app.get("/api/sample")
    async def get_sample(x_annotator_id: str = Header(None, alias="X-Annotator-ID")) -> dict[str, Any]:
        """Get the next sample for annotation."""
        if not x_annotator_id:
            raise HTTPException(status_code=400, detail="X-Annotator-ID header required")

        sample = server.get_next_sample(x_annotator_id)
        progress = server.get_progress(x_annotator_id)

        if not sample:
            return {
                "sample_id": None,
                "message": "You have completed all available samples. Thank you!",
                "progress": progress,
            }

        return sample.to_api_response(progress["completed"], progress["total"])

    @app.post("/api/annotate")
    async def submit_annotation(
        request: AnnotationRequest,
        x_annotator_id: str = Header(None, alias="X-Annotator-ID"),
    ) -> dict[str, Any]:
        """Submit an annotation."""
        if not x_annotator_id:
            raise HTTPException(status_code=400, detail="X-Annotator-ID header required")

        try:
            server.record_annotation(
                sample_id=request.sample_id,
                annotator_id=x_annotator_id,
                human_decision=request.decision,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        # Get next sample
        next_sample = server.get_next_sample(x_annotator_id)
        progress = server.get_progress(x_annotator_id)

        if not next_sample:
            return {
                "success": True,
                "next_sample": None,
                "message": "You have completed all available samples. Thank you!",
                "progress": progress,
            }

        return {
            "success": True,
            "next_sample": next_sample.to_api_response(progress["completed"], progress["total"]),
        }

    @app.get("/api/progress")
    async def get_progress_endpoint(
        x_annotator_id: str = Header(None, alias="X-Annotator-ID"),
    ) -> dict[str, Any]:
        """Get annotator's progress."""
        if not x_annotator_id:
            raise HTTPException(status_code=400, detail="X-Annotator-ID header required")

        progress = server.get_progress(x_annotator_id)
        total = progress["total"]
        completed = progress["completed"]
        percentage = (completed / total * 100) if total > 0 else 0

        return {
            "completed": completed,
            "total": total,
            "percentage": round(percentage, 1),
        }

    @app.get("/api/stats")
    async def get_stats() -> dict[str, Any]:
        """Get overall annotation statistics."""
        return server.get_overall_stats()

    return app


def run_server(data_dir: Path, port: int = 8000, annotators_per_sample: int = 2) -> None:
    """Run the annotation server.

    Args:
        data_dir: Directory containing samples and annotations.
        port: Port to run the server on.
        annotators_per_sample: Number of annotations required per sample.
    """
    import uvicorn

    app = create_app(data_dir, annotators_per_sample)
    logger.info(f"Starting annotation server on http://localhost:{port}")
    logger.info(f"Annotators per sample: {annotators_per_sample}")
    logger.info(f"Data directory: {data_dir}")

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")  # noqa: S104
