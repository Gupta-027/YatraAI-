"""Trip cost estimation as a **range**, never a single false-precision number.

Five components, each with an explicit low/high band:

* **Accommodation** — cluster baseline x tier x nights x rooms (2 per room)
* **Food** — cluster baseline x tier x travellers x days
* **Local transport** — the plan's actual travel distance costed per km by mode,
  floored at the cluster's daily baseline so a light day is not free
* **Entry charges** — summed directly from the scheduled attractions' fee ranges
* **Contingency** — a percentage buffer that widens with trip length and with
  how much of the itinerary is weather-exposed

Every assumption is returned alongside the number so the UI can show its work.
Prediction error against real spend is measured once feedback exists — see
`docs/ml-experiments.md`; we do not report an accuracy figure we have not measured.
"""

from __future__ import annotations

from collections.abc import Sequence

from yatraai.services.planner.models import (
    AttractionCandidate,
    CostEstimate,
    PlannedDay,
    TripContext,
)

# Fallback per-person-per-day baselines in INR when a cluster has none recorded.
DEFAULT_BASELINE: dict[str, dict[str, float]] = {
    "budget": {"stay": 1000, "food": 400, "local_transport": 300},
    "midrange": {"stay": 2800, "food": 1000, "local_transport": 700},
    "premium": {"stay": 7500, "food": 2400, "local_transport": 1600},
}

# Per-km running cost by mode, INR. Low/high band.
TRANSPORT_COST_PER_KM: dict[str, tuple[float, float]] = {
    "walk": (0.0, 0.0),
    "public": (2.0, 4.0),
    "car": (12.0, 18.0),
    "taxi": (16.0, 26.0),
    "mixed": (9.0, 15.0),
}

# Uncertainty band applied to baseline figures (they are averages, not quotes).
BASELINE_SPREAD = (0.80, 1.30)


def estimate_cost(
    days: Sequence[PlannedDay],
    ctx: TripContext,
    candidates_by_slug: dict[str, AttractionCandidate],
    cluster_baseline: dict | None = None,
) -> CostEstimate:
    travellers = max(1, ctx.traveller_count)
    nights = max(0, ctx.days - 1)
    baseline = (cluster_baseline or {}).get(ctx.accommodation_tier) or DEFAULT_BASELINE.get(
        ctx.accommodation_tier, DEFAULT_BASELINE["midrange"]
    )

    assumptions: list[str] = []
    breakdown: dict[str, dict[str, float]] = {}

    # ---- accommodation -----------------------------------------------------
    rooms = (travellers + 1) // 2
    stay_rate = float(baseline.get("stay", 2800))
    stay_low = stay_rate * BASELINE_SPREAD[0] * rooms * nights
    stay_high = stay_rate * BASELINE_SPREAD[1] * rooms * nights
    breakdown["accommodation"] = {"low": round(stay_low, 2), "high": round(stay_high, 2)}
    assumptions.append(
        f"Accommodation: {rooms} room(s) for {nights} night(s) at the "
        f"'{ctx.accommodation_tier}' tier (Rs.{stay_rate:,.0f}/room/night baseline, "
        f"two people per room)."
    )

    # ---- food --------------------------------------------------------------
    food_rate = float(baseline.get("food", 1000))
    food_low = food_rate * BASELINE_SPREAD[0] * travellers * ctx.days
    food_high = food_rate * BASELINE_SPREAD[1] * travellers * ctx.days
    breakdown["food"] = {"low": round(food_low, 2), "high": round(food_high, 2)}
    assumptions.append(
        f"Food: Rs.{food_rate:,.0f} per person per day at the '{ctx.accommodation_tier}' tier."
    )

    # ---- local transport ---------------------------------------------------
    total_km = sum(d.travel_km for d in days)
    per_km_low, per_km_high = TRANSPORT_COST_PER_KM.get(ctx.transport_mode, (12.0, 18.0))
    # Vehicles are shared: cost scales with vehicles, not heads.
    vehicles = max(1, (travellers + 3) // 4)
    transport_low = total_km * per_km_low * vehicles
    transport_high = total_km * per_km_high * vehicles
    # Floor at the cluster baseline so a short-distance day still costs something.
    floor_rate = float(baseline.get("local_transport", 700))
    floor_low = floor_rate * BASELINE_SPREAD[0] * travellers * ctx.days * 0.5
    transport_low = max(transport_low, floor_low)
    transport_high = max(transport_high, floor_low * 1.6)
    breakdown["local_transport"] = {
        "low": round(transport_low, 2),
        "high": round(transport_high, 2),
    }
    assumptions.append(
        f"Local transport: {total_km:.0f} km of planned travel by '{ctx.transport_mode}' at "
        f"Rs.{per_km_low:.0f}-{per_km_high:.0f}/km across {vehicles} vehicle(s), "
        f"floored at the destination baseline."
    )

    # ---- entry charges -----------------------------------------------------
    entry_low = 0.0
    entry_high = 0.0
    priced = 0
    unpriced = 0
    for day in days:
        for activity in day.visits:
            candidate = candidates_by_slug.get(activity.slug or "")
            if candidate is None:
                continue
            if candidate.entry_cost_max <= 0:
                unpriced += 1
                continue
            priced += 1
            entry_low += candidate.entry_cost_min * travellers
            entry_high += candidate.entry_cost_max * travellers
    breakdown["entry_charges"] = {"low": round(entry_low, 2), "high": round(entry_high, 2)}
    assumptions.append(
        f"Entry charges: recorded fee ranges for {priced} ticketed stop(s) x {travellers} "
        f"traveller(s). {unpriced} stop(s) are free or have no recorded fee."
    )
    if priced:
        assumptions.append(
            "Entry fees in the dataset are recorded as unverified and change without notice."
        )

    # ---- contingency -------------------------------------------------------
    subtotal_low = stay_low + food_low + transport_low + entry_low
    subtotal_high = stay_high + food_high + transport_high + entry_high

    exposure = _weather_exposure(days, candidates_by_slug)
    contingency_pct = 0.08 + 0.01 * min(7, ctx.days) + 0.07 * exposure
    contingency_low = subtotal_low * (contingency_pct * 0.6)
    contingency_high = subtotal_high * contingency_pct
    breakdown["contingency"] = {
        "low": round(contingency_low, 2),
        "high": round(contingency_high, 2),
    }
    assumptions.append(
        f"Contingency: {contingency_pct:.0%} buffer for guides, tips, minor entries and "
        f"weather disruption ({exposure:.0%} of stops are weather-exposed)."
    )

    total_low = subtotal_low + contingency_low
    total_high = subtotal_high + contingency_high

    return CostEstimate(
        low_inr=round(total_low, 2),
        high_inr=round(total_high, 2),
        per_person_low_inr=round(total_low / travellers, 2),
        per_person_high_inr=round(total_high / travellers, 2),
        breakdown=breakdown,
        assumptions=assumptions,
    )


def _weather_exposure(
    days: Sequence[PlannedDay], candidates_by_slug: dict[str, AttractionCandidate]
) -> float:
    visits = [a for d in days for a in d.visits]
    if not visits:
        return 0.0
    exposed = 0
    for activity in visits:
        candidate = candidates_by_slug.get(activity.slug or "")
        if candidate and candidate.indoor_outdoor == "outdoor":
            exposed += 1
    return exposed / len(visits)


def format_range(estimate: CostEstimate) -> str:
    """``"Expected cost: Rs.18,500-Rs.21,300 per person"``."""
    return (
        f"Expected cost: Rs.{estimate.per_person_low_inr:,.0f}-"
        f"Rs.{estimate.per_person_high_inr:,.0f} per person"
    )
