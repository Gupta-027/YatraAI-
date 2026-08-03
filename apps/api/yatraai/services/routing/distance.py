"""Great-circle distance and the documented offline travel-time model.

Speed and detour assumptions live in ``planner/models.py`` and are stated in
``docs/optimization.md``. They are deliberately conservative: underestimating
travel time is the failure mode that produces itineraries which cannot actually
be walked, so the fallback errs slow.
"""

from __future__ import annotations

import math

from yatraai.services.planner.models import MODE_DETOUR_FACTOR, MODE_SPEED_KMPH

EARTH_RADIUS_KM = 6371.0088

# Fixed overheads a pure distance/speed model misses: parking, walking to the
# entrance, waiting for a taxi. Applied once per leg.
MODE_FIXED_OVERHEAD_MIN: dict[str, float] = {
    "walk": 2.0,
    "car": 8.0,
    "taxi": 10.0,
    "public": 14.0,
    "mixed": 9.0,
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    if lat1 == lat2 and lon1 == lon2:
        return 0.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, a)))


def road_distance_km(straight_km: float, mode: str = "car") -> float:
    """Apply the documented detour factor to a straight-line distance."""
    return straight_km * MODE_DETOUR_FACTOR.get(mode, 1.35)


def travel_minutes(distance_km: float, mode: str = "car") -> float:
    """Travel time for a road distance, including a fixed per-leg overhead."""
    if distance_km <= 0:
        return 0.0
    speed = MODE_SPEED_KMPH.get(mode, 24.0)
    return (distance_km / speed) * 60.0 + MODE_FIXED_OVERHEAD_MIN.get(mode, 8.0)


def estimate_leg(
    lat1: float, lon1: float, lat2: float, lon2: float, mode: str = "car"
) -> tuple[float, float]:
    """``(distance_km, duration_min)`` from coordinates alone."""
    straight = haversine_km(lat1, lon1, lat2, lon2)
    road = road_distance_km(straight, mode)
    return round(road, 4), round(travel_minutes(road, mode), 2)
