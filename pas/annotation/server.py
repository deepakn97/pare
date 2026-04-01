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

from pas.annotation.models import Annotation, Sample, SampleResponse
from pas.trajectory.models import TernaryDecision  # noqa: TC001 - Pydantic needs runtime access

logger = logging.getLogger(__name__)

# Templates directory
TEMPLATES_DIR = Path(__file__).parent / "templates"


class AnnotationRequest(BaseModel):
    """Request body for submitting an annotation."""

    sample_id: str
    decision: TernaryDecision
    gather_context_rationale: str | None = None


class AnnotationServer:
    """Server for managing annotation state and serving samples."""

    def __init__(self, samples_file: Path, annotations_file: Path, annotators_per_sample: int = 2) -> None:
        """Initialize the annotation server.

        Args:
            samples_file: Path to the samples parquet file.
            annotations_file: Path to the annotations CSV file (created if not exists).
            annotators_per_sample: Number of annotations required per sample.
        """
        self.samples_file = samples_file
        self.annotations_file = annotations_file
        self.annotators_per_sample = annotators_per_sample

        # Load samples
        if not samples_file.exists():
            raise FileNotFoundError(f"Samples file not found: {samples_file}. Run 'pas annotation sample' first.")

        self.samples_df = pl.read_parquet(samples_file)
        logger.info(f"Loaded {len(self.samples_df)} samples from {samples_file}")

        # Build sample lookup
        self._samples: dict[str, Sample] = {}
        for row in self.samples_df.iter_rows(named=True):
            sample = Sample(**row)
            self._samples[sample.sample_id] = sample

        # Split tutorial and real samples
        self._tutorial_samples: dict[str, Sample] = {sid: s for sid, s in self._samples.items() if s.tutorial}
        self._real_samples: dict[str, Sample] = {sid: s for sid, s in self._samples.items() if not s.tutorial}
        if self._tutorial_samples:
            logger.info(f"Tutorial: {len(self._tutorial_samples)}, Real: {len(self._real_samples)}")
        else:
            logger.info(f"No tutorial samples found. All {len(self._real_samples)} samples are for annotation.")

        # Initialize annotations file
        self.annotations_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.annotations_file.exists():
            with open(self.annotations_file, "w") as f:
                f.write(Annotation.csv_header())
            logger.info(f"Created annotations file: {self.annotations_file}")

        # In-memory annotation tracking (real samples only)
        self._annotation_counts: dict[str, int] = {}  # sample_id -> count
        self._user_annotations: dict[str, set[str]] = {}  # user_id -> set of sample_ids
        self._lock = threading.Lock()

        # Load existing annotations
        self._load_annotation_state()

        # Tutorial completion tracking
        # Maps annotator_id -> {sample_id: decision} for tutorial samples
        self._tutorial_annotations: dict[str, dict[str, str]] = {}
        self._tutorial_annotations_file = self.annotations_file.parent / f"{self.annotations_file.stem}_tutorial.csv"
        if not self._tutorial_annotations_file.exists():
            with open(self._tutorial_annotations_file, "w") as f:
                f.write(Annotation.csv_header())
        self._load_tutorial_annotation_state()

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

    def _load_tutorial_annotation_state(self) -> None:
        """Load existing tutorial annotations into memory."""
        if not self._tutorial_annotations_file.exists():
            return
        try:
            df = pl.read_csv(self._tutorial_annotations_file)
            if len(df) == 0:
                return
            for row in df.iter_rows(named=True):
                annotator_id = row["annotator_id"]
                sample_id = row["sample_id"]
                decision = row["human_decision"]
                if annotator_id not in self._tutorial_annotations:
                    self._tutorial_annotations[annotator_id] = {}
                self._tutorial_annotations[annotator_id][sample_id] = decision
            logger.info(f"Loaded tutorial annotations for {len(self._tutorial_annotations)} annotators")
        except Exception as e:
            logger.warning(f"Failed to load tutorial annotations: {e}")

    def get_sample(self, sample_id: str) -> Sample | None:
        """Get a sample by ID (tutorial or real)."""
        return self._samples.get(sample_id)

    def get_next_sample(self, annotator_id: str) -> Sample | None:
        """Get the next available real (non-tutorial) sample for an annotator.

        Args:
            annotator_id: The annotator's anonymous ID.

        Returns:
            The next real sample to annotate, or None if all done.
        """
        user_done = self._user_annotations.get(annotator_id, set())

        for sample_id, sample in self._real_samples.items():
            if sample_id in user_done:
                continue
            if self._annotation_counts.get(sample_id, 0) >= self.annotators_per_sample:
                continue
            return sample

        return None

    def record_annotation(
        self,
        sample_id: str,
        annotator_id: str,
        human_decision: TernaryDecision,
        gather_context_rationale: str | None = None,
    ) -> bool:
        """Record a real (non-tutorial) annotation.

        Args:
            sample_id: The sample being annotated.
            annotator_id: The annotator's anonymous ID.
            human_decision: The human's accept/reject/gather_context decision.
            gather_context_rationale: Free-text rationale when decision is gather_context.

        Returns:
            True if recorded successfully.

        Raises:
            ValueError: If sample not found or already annotated by this user.
        """
        sample = self.get_sample(sample_id)
        if not sample:
            raise ValueError(f"Sample not found: {sample_id}")

        with self._lock:
            if annotator_id in self._user_annotations and sample_id in self._user_annotations[annotator_id]:
                raise ValueError(f"User {annotator_id} already annotated sample {sample_id}")

            annotation = Annotation.create(
                sample_id=sample_id,
                annotator_id=annotator_id,
                human_decision=human_decision,
                gather_context_rationale=gather_context_rationale,
            )

            with open(self.annotations_file, "a") as f:
                f.write(annotation.to_csv_row())

            self._annotation_counts[sample_id] = self._annotation_counts.get(sample_id, 0) + 1

            if annotator_id not in self._user_annotations:
                self._user_annotations[annotator_id] = set()
            self._user_annotations[annotator_id].add(sample_id)

            logger.info(
                f"Recorded annotation: sample={sample_id[:20]}..., user={annotator_id[:8]}..., decision={human_decision}"
            )

        return True

    def get_progress(self, annotator_id: str) -> dict[str, int]:
        """Get progress statistics for an annotator (real samples only).

        Args:
            annotator_id: The annotator's anonymous ID.

        Returns:
            Dictionary with completed and total counts.
        """
        user_done = self._user_annotations.get(annotator_id, set())

        total = 0
        completed = len(user_done)

        for sample_id in self._real_samples:
            if self._annotation_counts.get(sample_id, 0) < self.annotators_per_sample:
                total += 1

        total = max(total, completed)

        return {
            "completed": completed,
            "total": total,
        }

    def get_overall_stats(self) -> dict[str, Any]:
        """Get overall annotation statistics."""
        total_samples = len(self._real_samples)

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

    # --- Tutorial methods ---

    def is_tutorial_completed(self, annotator_id: str) -> bool:
        """Check if annotator has completed all tutorial samples.

        Args:
            annotator_id: The annotator's anonymous ID.

        Returns:
            True if all tutorial samples answered or no tutorials configured.
        """
        if not self._tutorial_samples:
            return True
        with self._lock:
            done = self._tutorial_annotations.get(annotator_id, {})
            return len(done) >= len(self._tutorial_samples)

    def get_next_tutorial_sample(self, annotator_id: str) -> Sample | None:
        """Get the next unanswered tutorial sample for an annotator.

        Args:
            annotator_id: The annotator's anonymous ID.

        Returns:
            Next tutorial Sample, or None if all done.
        """
        with self._lock:
            done = self._tutorial_annotations.get(annotator_id, {})
            for sample_id, sample in self._tutorial_samples.items():
                if sample_id not in done:
                    return sample
            return None

    def get_tutorial_summary(self, annotator_id: str) -> dict[str, Any]:
        """Get tutorial completion summary for an annotator.

        Uses in-memory tutorial annotation data (no file I/O).

        Args:
            annotator_id: The annotator's anonymous ID.

        Returns:
            Summary dict with correct, scored_total, total, answered.
        """
        with self._lock:
            decisions = self._tutorial_annotations.get(annotator_id, {})
            correct = 0
            scored_total = 0
            for sample_id, decision in decisions.items():
                sample = self._tutorial_samples.get(sample_id)
                if sample and sample.correct_decision is not None:
                    scored_total += 1
                    if decision == sample.correct_decision:
                        correct += 1
            return {
                "correct": correct,
                "scored_total": scored_total,
                "total": len(self._tutorial_samples),
                "answered": len(decisions),
            }

    def record_tutorial_annotation(
        self,
        sample_id: str,
        annotator_id: str,
        human_decision: TernaryDecision,
        gather_context_rationale: str | None = None,
    ) -> dict[str, Any]:
        """Record a tutorial annotation and return feedback.

        Writes to tutorial_annotations.csv (not annotations.csv).

        Args:
            sample_id: The tutorial sample being annotated.
            annotator_id: The annotator's anonymous ID.
            human_decision: The annotator's decision.
            gather_context_rationale: Free-text rationale when decision is gather_context.

        Returns:
            Feedback dict with correct, correct_decision, and explanation.

        Raises:
            ValueError: If sample not found in tutorial samples.
        """
        sample = self._tutorial_samples.get(sample_id)
        if not sample:
            raise ValueError(f"Tutorial sample not found: {sample_id}")

        annotation = Annotation.create(
            sample_id=sample_id,
            annotator_id=annotator_id,
            human_decision=human_decision,
            gather_context_rationale=gather_context_rationale,
        )

        with self._lock:
            with open(self._tutorial_annotations_file, "a") as f:
                f.write(annotation.to_csv_row())
            if annotator_id not in self._tutorial_annotations:
                self._tutorial_annotations[annotator_id] = {}
            self._tutorial_annotations[annotator_id][sample_id] = human_decision

        correct_decision = sample.correct_decision
        is_correct = human_decision == correct_decision if correct_decision is not None else None

        logger.info(
            f"Tutorial annotation: sample={sample_id[:20]}..., user={annotator_id[:8]}..., "
            f"decision={human_decision}, correct={is_correct}"
        )

        return {
            "correct": is_correct,
            "correct_decision": correct_decision,
            "explanation": sample.explanation or "",
        }


def create_app(samples_file: Path, annotations_file: Path, annotators_per_sample: int = 2) -> FastAPI:  # noqa: C901
    """Create the FastAPI application.

    Args:
        samples_file: Path to the samples parquet file.
        annotations_file: Path to the annotations CSV file.
        annotators_per_sample: Number of annotations required per sample.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(title="PAS Annotation Interface")

    # Initialize server
    server = AnnotationServer(samples_file, annotations_file, annotators_per_sample)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> FileResponse:
        """Serve the main annotation UI."""
        return FileResponse(TEMPLATES_DIR / "index.html")

    @app.get("/api/sample")
    async def get_sample(
        x_annotator_id: str = Header(None, alias="X-Annotator-ID"),
    ) -> SampleResponse | dict[str, Any]:
        """Get the next sample for annotation.

        Serves tutorial samples first. After all tutorials are completed,
        serves real annotation samples.
        """
        if not x_annotator_id:
            raise HTTPException(status_code=400, detail="X-Annotator-ID header required")

        # Serve tutorial samples first
        if not server.is_tutorial_completed(x_annotator_id):
            tutorial_sample = server.get_next_tutorial_sample(x_annotator_id)
            if tutorial_sample:
                with server._lock:
                    tutorial_done = len(server._tutorial_annotations.get(x_annotator_id, {}))
                tutorial_total = len(server._tutorial_samples)
                return tutorial_sample.to_api_response(tutorial_done, tutorial_total)

        # Serve real samples
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
        """Submit an annotation.

        Handles both tutorial and real samples. Tutorial submissions
        return feedback and write to tutorial_annotations.csv.
        """
        if not x_annotator_id:
            raise HTTPException(status_code=400, detail="X-Annotator-ID header required")

        # Check if this is a tutorial sample
        sample = server.get_sample(request.sample_id)
        if sample and sample.tutorial:
            try:
                feedback = server.record_tutorial_annotation(
                    sample_id=request.sample_id,
                    annotator_id=x_annotator_id,
                    human_decision=request.decision,
                    gather_context_rationale=request.gather_context_rationale,
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e

            # Check if tutorial is now complete
            if server.is_tutorial_completed(x_annotator_id):
                summary = server.get_tutorial_summary(x_annotator_id)
                return {
                    "success": True,
                    "tutorial_feedback": feedback,
                    "tutorial_complete": True,
                    "tutorial_summary": summary,
                    "next_sample": None,
                }

            # Get next tutorial sample
            next_tutorial = server.get_next_tutorial_sample(x_annotator_id)
            next_sample_data = None
            if next_tutorial:
                with server._lock:
                    tutorial_done = len(server._tutorial_annotations.get(x_annotator_id, {}))
                tutorial_total = len(server._tutorial_samples)
                next_sample_data = next_tutorial.to_api_response(
                    tutorial_done,
                    tutorial_total,
                ).model_dump()

            return {
                "success": True,
                "tutorial_feedback": feedback,
                "next_sample": next_sample_data,
            }

        # Real annotation
        try:
            server.record_annotation(
                sample_id=request.sample_id,
                annotator_id=x_annotator_id,
                human_decision=request.decision,
                gather_context_rationale=request.gather_context_rationale,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

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
            "next_sample": next_sample.to_api_response(progress["completed"], progress["total"]).model_dump(),
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


def run_server(samples_file: Path, annotations_file: Path, port: int = 8000, annotators_per_sample: int = 2) -> None:
    """Run the annotation server.

    Args:
        samples_file: Path to the samples parquet file.
        annotations_file: Path to the annotations CSV file.
        port: Port to run the server on.
        annotators_per_sample: Number of annotations required per sample.
    """
    import uvicorn

    app = create_app(samples_file, annotations_file, annotators_per_sample)
    logger.info(f"Starting annotation server on http://localhost:{port}")
    logger.info(f"Samples: {samples_file}")
    logger.info(f"Annotations: {annotations_file}")

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")  # noqa: S104
