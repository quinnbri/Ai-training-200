"""Observability and OpenTelemetry-compatible Tracing module for Cloud FinOps Copilot.

Provides structured JSON logging compatible with GCP Cloud Logging and an
in-memory + exportable span tracer for inspecting multi-agent and tool executions.
Automatically scrubs PII and secrets from all log payloads and trace spans.
"""

import datetime
import json
import logging
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

from .pii_scrubber import global_pii_scrubber


class GCPStructuredLogHandler(logging.Handler):
    """Formats log records as structured JSON for GCP Cloud Logging with PII redaction."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            raw_msg = record.getMessage()
            scrubbed_msg = global_pii_scrubber.scrub_text(raw_msg)
            log_entry: Dict[str, Any] = {
                "severity": record.levelname,
                "message": scrubbed_msg,
                "timestamp": datetime.datetime.fromtimestamp(
                    record.created, tz=datetime.timezone.utc
                ).isoformat(),
                "logger": record.name,
                "pii_scrubbed": True,
            }
            if hasattr(record, "trace_id"):
                log_entry["logging.googleapis.com/trace"] = getattr(record, "trace_id")
            if hasattr(record, "span_id"):
                log_entry["logging.googleapis.com/spanId"] = getattr(record, "span_id")
            sys.stdout.write(json.dumps(log_entry) + "\n")
            sys.stdout.flush()
        except Exception:
            self.handleError(record)


def get_logger(name: str = "cloud_finops_copilot") -> logging.Logger:
    """Returns a structured JSON logger instance."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        logger.addHandler(GCPStructuredLogHandler())
    return logger


class Span:
    """Represents a traced execution span for an agent step, subagent handoff, or tool call."""

    def __init__(
        self,
        name: str,
        span_type: str = "tool",
        parent_span_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.span_id = uuid.uuid4().hex[:16]
        self.trace_id = uuid.uuid4().hex
        self.name = name
        self.span_type = span_type
        self.parent_span_id = parent_span_id
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.duration_ms: Optional[float] = None
        self.status = "RUNNING"
        self.input_data: Any = None
        self.output_data: Any = None
        self.metadata = global_pii_scrubber.scrub_data(metadata or {})
        self.error: Optional[str] = None

    def finish(
        self,
        status: str = "SUCCESS",
        output_data: Any = None,
        error: Optional[str] = None,
    ) -> None:
        self.end_time = time.time()
        self.duration_ms = round((self.end_time - self.start_time) * 1000.0, 2)
        self.status = status
        if output_data is not None:
            self.output_data = global_pii_scrubber.scrub_data(output_data)
        if error is not None:
            self.error = global_pii_scrubber.scrub_text(str(error))
            self.status = "ERROR"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "name": self.name,
            "span_type": self.span_type,
            "parent_span_id": self.parent_span_id,
            "start_time_iso": datetime.datetime.fromtimestamp(
                self.start_time, tz=datetime.timezone.utc
            ).isoformat(),
            "duration_ms": self.duration_ms,
            "status": self.status,
            "input_data": global_pii_scrubber.scrub_data(self.input_data),
            "output_data": self.output_data,
            "metadata": self.metadata,
            "error": self.error,
            "pii_scrubbed": True,
        }


class AgentTracer:
    """Manages spans, latency metrics, and trace history for agent interactions."""

    def __init__(self, max_history: int = 200) -> None:
        self.max_history = max_history
        self.spans: List[Span] = []
        self.logger = get_logger("AgentTracer")

    def start_span(
        self,
        name: str,
        span_type: str = "tool",
        parent_span_id: Optional[str] = None,
        input_data: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Span:
        span = Span(
            name=name,
            span_type=span_type,
            parent_span_id=parent_span_id,
            metadata=metadata,
        )
        span.input_data = global_pii_scrubber.scrub_data(input_data)
        self.spans.append(span)
        if len(self.spans) > self.max_history:
            self.spans.pop(0)
        self.logger.info(
            f"Span started: {name}",
            extra={"span_id": span.span_id, "trace_id": span.trace_id},
        )
        return span

    def get_recent_spans(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in reversed(self.spans[-limit:])]

    def clear(self) -> None:
        self.spans.clear()


# Global shared tracer singleton
global_tracer = AgentTracer()
