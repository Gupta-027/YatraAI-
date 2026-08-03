"""Routing provider abstraction.

``OSRMRouter`` calls a real road-network router; ``HaversineRouter`` is the
always-available fallback. The planner only ever sees ``RouteMatrix``, so it
cannot tell which produced it - except through ``is_fallback``, which is
surfaced honestly in the UI banner and the analytics dashboard.
"""

from __future__ import annotations

import functools
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx

from yatraai.config import get_settings
from yatraai.core.telemetry import track
from yatraai.logging_config import get_logger
from yatraai.services.routing.distance import estimate_leg

log = get_logger(__name__)

Coord = tuple[float, float]


@dataclass
class RouteMatrix:
    """Symmetric-ish distance/duration matrix over an ordered list of points."""

    points: list[Coord]
    distance_km: list[list[float]]
    duration_min: list[list[float]]
    provider: str
    is_fallback: bool = False
    mode: str = "car"
    notes: list[str] = field(default_factory=list)

    def leg(self, i: int, j: int) -> tuple[float, float]:
        return self.distance_km[i][j], self.duration_min[i][j]

    @property
    def size(self) -> int:
        return len(self.points)


class Router(ABC):
    name: str = "base"
    is_fallback: bool = False

    @abstractmethod
    def matrix(self, points: list[Coord], mode: str = "car") -> RouteMatrix: ...


class HaversineRouter(Router):
    """Offline fallback: great-circle distance x detour factor / mean speed.

    Assumptions are documented and conservative. Accuracy against OSRM on the
    seed catalogue is measured in ``evaluation/reports/routing_accuracy.md``.
    """

    name = "haversine"
    is_fallback = True

    def matrix(self, points: list[Coord], mode: str = "car") -> RouteMatrix:
        n = len(points)
        distance = [[0.0] * n for _ in range(n)]
        duration = [[0.0] * n for _ in range(n)]
        with track("routing", self.name, "matrix") as state:
            state["fallback_used"] = True
            for i in range(n):
                for j in range(i + 1, n):
                    km, minutes = estimate_leg(*points[i], *points[j], mode=mode)
                    distance[i][j] = distance[j][i] = km
                    duration[i][j] = duration[j][i] = minutes
        return RouteMatrix(
            points=points,
            distance_km=distance,
            duration_min=duration,
            provider=self.name,
            is_fallback=True,
            mode=mode,
            notes=[
                "Straight-line distance scaled by a documented detour factor and "
                "mean-speed assumption. Real road times will differ."
            ],
        )


class OSRMRouter(Router):
    """Public OSRM demo server (or a self-hosted instance) via the /table service."""

    name = "osrm"

    OSRM_PROFILE = {
        "car": "driving",
        "taxi": "driving",
        "mixed": "driving",
        "walk": "foot",
        "public": "driving",
    }

    def __init__(self, base_url: str, timeout: float = 8.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def matrix(self, points: list[Coord], mode: str = "car") -> RouteMatrix:
        if len(points) < 2:
            return HaversineRouter().matrix(points, mode)

        profile = self.OSRM_PROFILE.get(mode, "driving")
        coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
        url = f"{self.base_url}/table/v1/{profile}/{coords}"
        params = {"annotations": "distance,duration"}

        with track("routing", self.name, "matrix") as state:
            try:
                response = httpx.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
                payload = response.json()
                if payload.get("code") != "Ok":
                    raise ValueError(f"OSRM returned code={payload.get('code')}")

                durations = payload["durations"]
                distances = payload.get("distances")
                n = len(points)
                duration_min = [[0.0] * n for _ in range(n)]
                distance_km = [[0.0] * n for _ in range(n)]
                for i in range(n):
                    for j in range(n):
                        secs = durations[i][j]
                        duration_min[i][j] = round((secs or 0) / 60.0, 2)
                        if distances:
                            distance_km[i][j] = round((distances[i][j] or 0) / 1000.0, 4)
                        else:
                            distance_km[i][j] = round(
                                estimate_leg(*points[i], *points[j], mode)[0], 4
                            )
                return RouteMatrix(
                    points=points,
                    distance_km=distance_km,
                    duration_min=duration_min,
                    provider=self.name,
                    is_fallback=False,
                    mode=mode,
                )
            except Exception as exc:
                state["fallback_used"] = True
                state["error_kind"] = type(exc).__name__
                state["ok"] = False
                log.warning("routing.osrm_failed", error=str(exc), points=len(points))
                fallback = HaversineRouter().matrix(points, mode)
                fallback.notes.insert(
                    0, f"OSRM unavailable ({type(exc).__name__}); using fallback."
                )
                return fallback


@functools.lru_cache(maxsize=1)
def get_router() -> Router:
    s = get_settings()
    if s.routing_provider == "osrm":
        return OSRMRouter(s.osrm_base_url, s.routing_timeout_seconds)
    return HaversineRouter()


def reset_router_cache() -> None:
    get_router.cache_clear()
