import random
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SpanStatus(str, Enum):
    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    parent_span_id: str | None = None
    status: SpanStatus = SpanStatus.UNSET
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    duration_ms: float | None = None

    def set_attribute(self, key: str, value: Any):
        self.attributes[key] = value

    def add_event(self, name: str, attributes: dict | None = None):
        self.events.append(
            {
                "name": name,
                "timestamp": time.time(),
                "attributes": attributes or {},
            }
        )

    def finish(self, status: SpanStatus = SpanStatus.OK):
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.status = status

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "status": self.status.value,
            "attributes": self.attributes,
            "events": self.events,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
        }


_current_span: ContextVar[Span | None] = ContextVar("_current_span", default=None)


class TracingContext:
    """Collects spans for a single agent run."""

    def __init__(self, agent_name: str, session_id: str, sample_rate: float = 1.0):
        self.trace_id = uuid.uuid4().hex
        self.agent_name = agent_name
        self.session_id = session_id
        self.spans: list[Span] = []
        self.is_sampled = random.random() < sample_rate
        self._span_stack: list[Span] = []

    def start_span(self, name: str, attributes: dict | None = None, parent_span_id: str | None = None) -> Span:
        parent_id = parent_span_id or (self._span_stack[-1].span_id if self._span_stack else None)
        span = Span(name=name, trace_id=self.trace_id, parent_span_id=parent_id)
        if attributes:
            span.attributes.update(attributes)
        self._span_stack.append(span)
        self.spans.append(span)
        _current_span.set(span)
        return span

    def finish_span(self, span: Span, status: SpanStatus = SpanStatus.OK):
        span.finish(status=status)
        if self._span_stack and self._span_stack[-1] is span:
            self._span_stack.pop()
        parent = self._span_stack[-1] if self._span_stack else None
        _current_span.set(parent)

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "agent": self.agent_name,
            "session_id": self.session_id,
            "is_sampled": self.is_sampled,
            "spans": [s.to_dict() for s in self.spans],
        }


def get_current_span() -> Span | None:
    return _current_span.get()
