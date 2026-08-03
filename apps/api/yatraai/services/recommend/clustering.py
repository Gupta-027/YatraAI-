"""Geographic clustering: decide *which day* each attraction belongs to.

Why cluster before scheduling
-----------------------------
Solving one big vehicle-routing problem across all days lets the optimiser
produce a day that zig-zags across a city. Real travellers plan by area. So we
partition candidates into ``n_days`` spatial groups first, then run the schedule
optimiser *within* each day. This also shrinks the CP-SAT model from
``O((k·days)²)`` arcs to ``days · O(k²)``, which is what keeps solve times in
the hundreds of milliseconds.

Two strategies:

``balanced_kmeans``
    K-means on the haversine-corrected plane, then a balancing pass that moves
    points from over-full to under-full clusters by smallest centroid-distance
    increase. Plain k-means happily produces a 9-stop day and a 1-stop day;
    the balancing pass is what makes the output usable.

``single_day``
    Trivial pass-through for one-day trips.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from yatraai.services.planner.models import ScoredAttraction
from yatraai.services.routing.distance import haversine_km


@dataclass
class GeoCluster:
    index: int
    members: list[ScoredAttraction]
    centroid_lat: float
    centroid_lon: float

    @property
    def size(self) -> int:
        return len(self.members)

    def spread_km(self) -> float:
        if len(self.members) < 2:
            return 0.0
        return max(
            haversine_km(self.centroid_lat, self.centroid_lon, m.candidate.lat, m.candidate.lon)
            for m in self.members
        )


def _project(lat: float, lon: float, ref_lat: float) -> tuple[float, float]:
    """Equirectangular projection to kilometres - accurate enough at city scale."""
    return (lat * 111.32, lon * 111.32 * math.cos(math.radians(ref_lat)))


def _centroid(items: Sequence[ScoredAttraction]) -> tuple[float, float]:
    if not items:
        return 0.0, 0.0
    return (
        sum(i.candidate.lat for i in items) / len(items),
        sum(i.candidate.lon for i in items) / len(items),
    )


def cluster_by_day(
    scored: Sequence[ScoredAttraction],
    n_days: int,
    *,
    seed: int = 20240101,
    max_iterations: int = 60,
) -> list[GeoCluster]:
    """Partition attractions into ``n_days`` geographically coherent groups.

    Deterministic: seeding uses k-means++ style farthest-point initialisation on
    a slug-sorted list, so the same inputs always produce the same partition.
    """
    items = sorted(scored, key=lambda s: s.candidate.slug)
    if n_days <= 1 or len(items) <= 1:
        lat, lon = _centroid(items)
        return [GeoCluster(0, list(items), lat, lon)]

    n_days = min(n_days, len(items))
    ref_lat = sum(i.candidate.lat for i in items) / len(items)
    coords = [_project(i.candidate.lat, i.candidate.lon, ref_lat) for i in items]

    # --- deterministic farthest-point seeding ---
    # Start from the highest-scoring attraction, then repeatedly take the point
    # furthest from all chosen seeds. No RNG, so results are reproducible.
    best_index = max(range(len(items)), key=lambda k: (items[k].total_score, -k))
    seed_indices = [best_index]
    while len(seed_indices) < n_days:
        furthest, best_distance = None, -1.0
        for k, point in enumerate(coords):
            if k in seed_indices:
                continue
            d = min(math.dist(point, coords[s]) for s in seed_indices)
            if d > best_distance:
                furthest, best_distance = k, d
        if furthest is None:
            break
        seed_indices.append(furthest)

    centroids = [coords[k] for k in seed_indices]
    assignment = [0] * len(items)

    for _ in range(max_iterations):
        changed = False
        for k, point in enumerate(coords):
            nearest = min(range(len(centroids)), key=lambda c: math.dist(point, centroids[c]))
            if assignment[k] != nearest:
                assignment[k] = nearest
                changed = True
        for c in range(len(centroids)):
            group = [coords[k] for k in range(len(items)) if assignment[k] == c]
            if group:
                centroids[c] = (
                    sum(p[0] for p in group) / len(group),
                    sum(p[1] for p in group) / len(group),
                )
        if not changed:
            break

    assignment = _balance(assignment, coords, centroids, n_days)

    clusters: list[GeoCluster] = []
    for c in range(n_days):
        members = [items[k] for k in range(len(items)) if assignment[k] == c]
        members.sort(key=lambda s: (-s.total_score, s.candidate.slug))
        lat, lon = _centroid(members)
        clusters.append(GeoCluster(c, members, lat, lon))

    # Order days so the group starts near their base: cluster 0 is the tightest.
    clusters.sort(key=lambda c: (-c.size, c.index))
    for i, cluster in enumerate(clusters):
        cluster.index = i
    return clusters


# A balancing move is refused when it would drag a point this far (km) from the
# cluster it geographically belongs to. Without this guard a wide multi-city
# cluster like Delhi-Agra gets Delhi sites shuffled into the Agra day purely to
# even out counts, and the optimiser then has to drive 200 km mid-day.
MAX_BALANCE_MOVE_KM = 25.0


def _balance(
    assignment: list[int],
    coords: list[tuple[float, float]],
    centroids: list[tuple[float, float]],
    n_clusters: int,
) -> list[int]:
    """Move points from over-full to under-full clusters - but never across a gulf.

    Geography wins over balance. An unbalanced day is a minor annoyance; a day
    that crosses a 200 km gap is an unusable itinerary.
    """
    n = len(coords)
    target = n / n_clusters
    upper = math.ceil(target * 1.4)
    lower = max(1, math.floor(target * 0.5))

    for _ in range(n):
        sizes = [assignment.count(c) for c in range(n_clusters)]
        over = [c for c in range(n_clusters) if sizes[c] > upper]
        under = [c for c in range(n_clusters) if sizes[c] < lower]
        if not over or not under:
            break

        source = max(over, key=lambda c: sizes[c])
        target_cluster = min(under, key=lambda c: sizes[c])
        movable = [k for k in range(n) if assignment[k] == source]
        if not movable:
            break
        # Move the point whose reassignment costs the least extra distance...
        best = min(
            movable,
            key=lambda k: (
                math.dist(coords[k], centroids[target_cluster])
                - math.dist(coords[k], centroids[source])
            ),
        )
        # ...but refuse outright if it would strand the point far from home.
        extra_km = math.dist(coords[best], centroids[target_cluster]) - math.dist(
            coords[best], centroids[source]
        )
        if extra_km > MAX_BALANCE_MOVE_KM:
            break
        assignment[best] = target_cluster

    return assignment


def order_clusters_by_proximity(
    clusters: list[GeoCluster], base_lat: float, base_lon: float
) -> list[GeoCluster]:
    """Nearest-first day ordering so travel ramps up rather than jumping about."""
    ordered = sorted(
        clusters, key=lambda c: haversine_km(base_lat, base_lon, c.centroid_lat, c.centroid_lon)
    )
    for i, cluster in enumerate(ordered):
        cluster.index = i
    return ordered
