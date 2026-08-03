"""Single source of truth for "which providers are live vs degraded".

Surfaced on ``/ready``, in the analytics dashboard and as the honest warning
banner in the UI whenever fallback data is being served.
"""

from __future__ import annotations

from yatraai.config import get_settings
from yatraai.core.telemetry import telemetry


def service_status_snapshot() -> dict:
    s = get_settings()
    stats = telemetry.summary()

    def _mode(service: str, configured: str, fallback_name: str) -> dict:
        info = stats.get(service, {})
        fallback_rate = float(info.get("fallback_rate", 0.0))
        degraded = fallback_rate > 0.0 or float(info.get("error_rate", 0.0)) > 0.0
        return {
            "configured": configured,
            "fallback": fallback_name,
            "degraded": degraded,
            "fallback_rate": fallback_rate,
            "calls": info.get("calls", 0),
            "p95_ms": info.get("p95_ms", 0.0),
        }

    return {
        "llm": _mode("llm", s.llm_provider, "template-explanations"),
        "routing": _mode("routing", s.routing_provider, "haversine"),
        "weather": _mode("weather", s.weather_provider, "seed-climatology"),
        "embeddings": _mode("embeddings", s.embedding_provider, "hashing"),
        "database": {"configured": "postgres" if s.uses_postgres else "sqlite"},
    }


def active_degradations() -> list[str]:
    """Human-readable list of currently degraded subsystems (for UI banners)."""
    snapshot = service_status_snapshot()
    messages: list[str] = []
    if snapshot["routing"]["degraded"]:
        messages.append(
            "Road routing is unavailable - travel times use straight-line distance "
            "with documented speed assumptions."
        )
    if snapshot["weather"]["degraded"]:
        messages.append(
            "Live weather is unavailable - forecasts use committed seasonal climatology."
        )
    if snapshot["llm"]["degraded"]:
        messages.append(
            "The language model is unavailable - explanations use deterministic templates."
        )
    if snapshot["embeddings"]["degraded"]:
        messages.append("Transformer embeddings unavailable - using the deterministic fallback.")
    return messages
