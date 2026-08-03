"""Lightweight span timing for external providers.

Every call to an LLM, routing or weather provider is wrapped so the analytics
dashboard can report real latency / error / fallback rates instead of guesses.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from yatraai.logging_config import get_logger

log = get_logger(__name__)

_MAX_SAMPLES = 500


@dataclass
class ServiceSample:
    service: str
    provider: str
    operation: str
    latency_ms: float
    ok: bool
    fallback_used: bool
    error_kind: str = ""
    at: float = field(default_factory=time.time)


class TelemetryBuffer:
    """Ring buffer of recent provider calls, aggregated on demand."""

    def __init__(self) -> None:
        self._samples: dict[str, deque[ServiceSample]] = defaultdict(
            lambda: deque(maxlen=_MAX_SAMPLES)
        )
        self._lock = threading.Lock()

    def record(self, sample: ServiceSample) -> None:
        with self._lock:
            self._samples[sample.service].append(sample)

    def summary(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        with self._lock:
            for service, samples in self._samples.items():
                items = list(samples)
                if not items:
                    continue
                latencies = sorted(s.latency_ms for s in items)
                n = len(latencies)
                out[service] = {
                    "calls": n,
                    "error_rate": round(sum(1 for s in items if not s.ok) / n, 4),
                    "fallback_rate": round(sum(1 for s in items if s.fallback_used) / n, 4),
                    "p50_ms": round(latencies[int(n * 0.50)] if n else 0.0, 2),
                    "p95_ms": round(latencies[min(n - 1, int(n * 0.95))] if n else 0.0, 2),
                    "max_ms": round(latencies[-1], 2),
                    "providers": sorted({s.provider for s in items}),
                }
        return out

    def clear(self) -> None:
        with self._lock:
            self._samples.clear()


telemetry = TelemetryBuffer()


@contextmanager
def track(service: str, provider: str, operation: str = "") -> Iterator[dict]:
    """Time a provider call.

    The yielded dict lets the body flag ``fallback_used`` / ``error_kind``.
    """
    state = {"fallback_used": False, "error_kind": "", "ok": True}
    started = time.perf_counter()
    try:
        yield state
    except Exception as exc:
        state["ok"] = False
        state["error_kind"] = type(exc).__name__
        raise
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        sample = ServiceSample(
            service=service,
            provider=provider,
            operation=operation,
            latency_ms=elapsed_ms,
            ok=bool(state["ok"]),
            fallback_used=bool(state["fallback_used"]),
            error_kind=str(state["error_kind"]),
        )
        telemetry.record(sample)
        log.debug(
            "provider.call",
            service=service,
            provider=provider,
            operation=operation,
            latency_ms=round(elapsed_ms, 2),
            ok=sample.ok,
            fallback=sample.fallback_used,
        )
