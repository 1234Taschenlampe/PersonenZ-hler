from __future__ import annotations

from typing import Any

from .inference_pipeline import ProcessingPipeline
from .types import ConsensusDecision


class _AggregateAwareDatabaseProxy:
    """Keep aggregate counts correct even when personal event storage is off."""

    def __init__(self, pipeline: "ProductionProcessingPipeline", database: Any) -> None:
        self._pipeline = pipeline
        self._database = database

    def __getattr__(self, name: str) -> Any:
        return getattr(self._database, name)

    def record_decision(self, decision: ConsensusDecision, model_name: str, processing_ms: float | None = None) -> int:
        event_id = self._database.record_decision(decision, model_name, processing_ms)
        if decision.counted and not decision.uncertain:
            self._pipeline.global_counts.apply(decision.event.direction, True, False)
        elif decision.uncertain:
            self._pipeline.global_counts.apply(decision.event.direction, True, True)
        else:
            self._pipeline.global_counts.apply(decision.event.direction, False, False)
        self._pipeline._persist_global_counts()  # noqa: SLF001 - pipeline-owned aggregate persistence
        return event_id


class ProductionProcessingPipeline(ProcessingPipeline):
    """Production semantics for entry/exit counting.

    The legacy GUI pipeline also has a live-presence counter that treats a
    sufficiently stable visible identity as an entry and its disappearance as
    an exit. That is useful for diagnostics, but it is not correct occupancy
    semantics for two physical entrance/exit cameras. Production counts are
    therefore changed only by validated A-neutral-B/B-neutral-A crossing
    events after dual-camera consensus. Visibility remains telemetry only.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.database = _AggregateAwareDatabaseProxy(self, self.database)

    def _sync_live_presence_counts(self, visible_ids: set[int], timestamp: float) -> None:
        _ = timestamp
        self.global_counts.visible = len(visible_ids)
        # Deliberately do not modify entered/exited/inside here. Those counters
        # represent physical passages and are updated through record_decision.
