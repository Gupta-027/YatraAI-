"""CP-SAT day scheduler.

Formulation
-----------
Each day is a **prize-collecting travelling-salesman problem with time windows**
(PC-TSPTW) solved with OR-Tools CP-SAT.

*Nodes* — index 0 is the depot (the group's base for that day); 1..n are
candidate attractions; one node is a mandatory meal break.

*Variables*
    ``arc[i][j] ∈ {0,1}``   the tour goes directly from i to j
    ``arc[i][i] ∈ {0,1}``   node i is **skipped** (self-loop)
    ``start[i] ∈ [0, 1440]`` service start time in minutes from midnight

*Constraints*
    ``AddCircuit`` over all arcs, which simultaneously enforces a single tour and
    lets unselected nodes drop out via their self-loop.
    ``arc[i][j] ⇒ start[j] ≥ start[i] + service_i + travel_ij``  (time propagation)
    ``start[i] ≥ open_i`` and ``start[i] + service_i ≤ close_i``  (opening hours)
    ``start[i] ≥ day_start`` and ``start[i] + service_i ≤ day_end``
    ``Σ visit_i ≤ max_activities_for_pace``
    ``Σ entry_cost_i · visit_i ≤ daily_activity_budget``
    ``Σ travel_ij · arc_ij ≤ max_daily_travel_minutes``
    mandatory nodes: ``visit_i = 1``

*Objective*
    ``maximise Σ score_i·visit_i·W_SCORE − W_TRAVEL·Σ travel_ij·arc_ij``

The travel penalty is what stops the solver picking two high-scoring places at
opposite ends of the city when three good ones sit together.

Determinism: ``num_workers=1`` plus a fixed ``random_seed`` makes the solver
reproducible, which the test suite asserts.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from ortools.sat.python import cp_model

from yatraai.config import get_settings
from yatraai.logging_config import get_logger
from yatraai.services.planner.models import (
    PACE_PROFILE,
    AttractionCandidate,
    DayWeather,
    PlannedActivity,
    ScoredAttraction,
    TripContext,
)
from yatraai.services.routing.base import RouteMatrix

log = get_logger(__name__)

SCORE_SCALE = 1000
TRAVEL_WEIGHT = 4  # penalty per travel-minute, in scaled score units
MEAL_DURATION_MIN = 50
MEAL_WINDOW = (12 * 60, 14 * 60 + 30)
MEAL_TRAVEL_MIN = 5  # assume you eat near wherever you already are
REST_DURATION_MIN = 30


@dataclass
class DayPlanRequest:
    day_index: int
    calendar_date: date
    weekday: int
    candidates: list[ScoredAttraction]
    base_lat: float
    base_lon: float
    day_start_min: int
    day_end_min: int
    matrix: RouteMatrix
    weather: DayWeather | None = None
    max_activities: int = 4
    max_travel_min: int = 210
    daily_activity_budget: float | None = None
    mandatory_slugs: set[str] = field(default_factory=set)
    include_meal: bool = True
    include_rest: bool = False
    transport_mode: str = "car"


@dataclass
class DayPlanResult:
    day_index: int
    activities: list[PlannedActivity]
    travel_km: float
    travel_min: int
    status: str
    objective: float
    solve_ms: float
    relaxations: list[str] = field(default_factory=list)
    unscheduled_mandatory: list[str] = field(default_factory=list)


def _service_minutes(scored: ScoredAttraction, pace: str) -> int:
    """Visit duration, shortened on a packed schedule and lengthened when relaxed."""
    c = scored.candidate
    if pace == "packed":
        return max(c.min_duration_min, int(c.typical_duration_min * 0.8))
    if pace == "relaxed":
        return min(c.max_duration_min, int(c.typical_duration_min * 1.15))
    return c.typical_duration_min


def _opening_bounds(
    scored: ScoredAttraction, weekday: int, day_start: int, day_end: int, service: int
) -> tuple[int, int] | None:
    """Widest feasible ``(earliest_start, latest_start)`` on this weekday."""
    windows = scored.candidate.opening_windows_for(weekday)
    if not windows:
        return None
    best: tuple[int, int] | None = None
    for opens, closes in windows:
        earliest = max(opens, day_start)
        latest = min(closes, day_end) - service
        if latest >= earliest:
            span = latest - earliest
            if best is None or span > (best[1] - best[0]):
                best = (earliest, latest)
    return best


def _containing_window(
    candidate: AttractionCandidate, weekday: int, start_min: int
) -> tuple[int | None, int | None]:
    """The opening interval a scheduled start falls inside, for display.

    Returns ``(None, None)`` when the attraction records no hours. That is a
    genuine absence and the UI says "hours not recorded" rather than showing a
    fabricated 00:00-24:00, which is what ``opening_windows_for`` substitutes for
    the *solver's* benefit.
    """
    if not candidate.windows:
        return None, None
    windows = candidate.opening_windows_for(weekday)
    if not windows:
        return None, None
    for opens, closes in windows:
        if opens <= start_min < closes:
            return opens, closes
    # Scheduled outside every window would be a validator error, not a display
    # problem - fall back to the widest window rather than guessing.
    return max(windows, key=lambda w: w[1] - w[0])


def solve_day(request: DayPlanRequest, pace: str = "balanced") -> DayPlanResult:
    """Solve one day. Progressively relaxes soft limits rather than failing."""
    # Relaxations are ordered least-harmful first. The travel cap is relaxed only
    # modestly: a day that drives for six hours is technically feasible and
    # practically useless, so we would rather schedule fewer stops.
    attempts: list[tuple[str, dict]] = [
        ("full", {}),
        ("reduce_activities", {"max_activities": max(1, request.max_activities - 1)}),
        ("relax_travel_cap", {"max_travel_min": int(request.max_travel_min * 1.25)}),
        (
            "drop_budget_cap",
            {
                "daily_activity_budget": None,
                "max_activities": max(1, request.max_activities - 1),
                "max_travel_min": int(request.max_travel_min * 1.4),
            },
        ),
        (
            "minimal_day",
            {
                "daily_activity_budget": None,
                "max_activities": 2,
                "max_travel_min": int(request.max_travel_min * 1.5),
            },
        ),
    ]

    relaxations: list[str] = []
    for name, overrides in attempts:
        result = _solve_once(request, pace, overrides)
        if result.status in {"OPTIMAL", "FEASIBLE"}:
            result.relaxations = relaxations
            return result
        if name != attempts[-1][0]:
            relaxations.append(name)
            log.info("planner.relaxing", day=request.day_index, relaxation=name)

    return DayPlanResult(
        day_index=request.day_index,
        activities=[],
        travel_km=0.0,
        travel_min=0,
        status="INFEASIBLE",
        objective=0.0,
        solve_ms=0.0,
        relaxations=relaxations,
        unscheduled_mandatory=sorted(request.mandatory_slugs),
    )


def _solve_once(request: DayPlanRequest, pace: str, overrides: dict) -> DayPlanResult:
    started = time.perf_counter()
    settings = get_settings()

    max_activities = overrides.get("max_activities", request.max_activities)
    max_travel_min = overrides.get("max_travel_min", request.max_travel_min)
    budget = overrides.get("daily_activity_budget", request.daily_activity_budget)

    day_start, day_end = request.day_start_min, request.day_end_min

    # ---- node construction -------------------------------------------------
    # 0 = depot, 1..k = attractions, then optional meal / rest nodes.
    usable: list[ScoredAttraction] = []
    bounds: list[tuple[int, int]] = []
    services: list[int] = []
    for scored in request.candidates:
        service = _service_minutes(scored, pace)
        window = _opening_bounds(scored, request.weekday, day_start, day_end, service)
        if window is None:
            continue
        usable.append(scored)
        bounds.append(window)
        services.append(service)

    if not usable:
        return DayPlanResult(
            request.day_index,
            [],
            0.0,
            0,
            "EMPTY",
            0.0,
            (time.perf_counter() - started) * 1000,
        )

    n_attractions = len(usable)
    meal_index = 1 + n_attractions if request.include_meal else None
    rest_index = (
        (meal_index + 1 if meal_index is not None else 1 + n_attractions)
        if request.include_rest
        else None
    )
    n_nodes = 1 + n_attractions + int(request.include_meal) + int(request.include_rest)

    # Travel time between nodes. Matrix index 0 is the depot, matching our layout.
    def travel(i: int, j: int) -> int:
        if i == j:
            return 0
        if i in (meal_index, rest_index) or j in (meal_index, rest_index):
            return MEAL_TRAVEL_MIN
        return int(round(request.matrix.duration_min[i][j]))

    def travel_km(i: int, j: int) -> float:
        if i == j or i in (meal_index, rest_index) or j in (meal_index, rest_index):
            return 0.0
        return float(request.matrix.distance_km[i][j])

    model = cp_model.CpModel()

    # ---- variables ---------------------------------------------------------
    start: list[cp_model.IntVar] = []
    lower_bound: list[int] = []
    for node in range(n_nodes):
        if node == 0:
            lo, hi = day_start, day_start
            name = "start_depot"
        elif node == meal_index:
            lo = max(day_start, MEAL_WINDOW[0])
            hi = max(lo, min(MEAL_WINDOW[1], day_end - MEAL_DURATION_MIN))
            name = "start_meal"
        elif node == rest_index:
            lo, hi = day_start, max(day_start, day_end - REST_DURATION_MIN)
            name = "start_rest"
        else:
            lo, hi = bounds[node - 1]
            name = f"start_{node}"
        lower_bound.append(lo)
        start.append(model.NewIntVar(lo, hi, name))

    def service_of(node: int) -> int:
        if node == 0:
            return 0
        if node == meal_index:
            return MEAL_DURATION_MIN
        if node == rest_index:
            return REST_DURATION_MIN
        return services[node - 1]

    arcs: list[tuple[int, int, cp_model.IntVar]] = []
    arc_lit: dict[tuple[int, int], cp_model.IntVar] = {}
    visit: dict[int, cp_model.IntVar] = {}

    for i in range(n_nodes):
        for j in range(n_nodes):
            if i == j:
                if i == 0:
                    continue  # the depot is always in the tour
                skip = model.NewBoolVar(f"skip_{i}")
                arcs.append((i, i, skip))
                arc_lit[(i, i)] = skip
                v = model.NewBoolVar(f"visit_{i}")
                model.Add(v == 1 - skip)
                visit[i] = v
            else:
                lit = model.NewBoolVar(f"arc_{i}_{j}")
                arcs.append((i, j, lit))
                arc_lit[(i, j)] = lit

    model.AddCircuit(arcs)

    # ---- time propagation --------------------------------------------------
    for i in range(n_nodes):
        for j in range(1, n_nodes):
            if i == j:
                continue
            transit = service_of(i) + travel(i, j)
            model.Add(start[j] >= start[i] + transit).OnlyEnforceIf(arc_lit[(i, j)])

    for node in range(1, n_nodes):
        model.Add(start[node] + service_of(node) <= day_end).OnlyEnforceIf(visit[node])
        model.Add(start[node] >= day_start).OnlyEnforceIf(visit[node])
        # Pin unvisited nodes to their lower bound so they cannot wander and
        # create spurious time-propagation pressure on the rest of the model.
        model.Add(start[node] == lower_bound[node]).OnlyEnforceIf(arc_lit[(node, node)])

    # ---- mandatory nodes ---------------------------------------------------
    for idx, scored in enumerate(usable, start=1):
        if scored.candidate.slug in request.mandatory_slugs:
            model.Add(visit[idx] == 1)
    scheduled_slugs = {s.candidate.slug for s in usable}
    unscheduled_mandatory = sorted(request.mandatory_slugs - scheduled_slugs)

    if meal_index is not None:
        model.Add(visit[meal_index] == 1)
    if rest_index is not None:
        model.Add(visit[rest_index] == 1)

    # ---- capacity constraints ---------------------------------------------
    attraction_visits = [visit[i] for i in range(1, n_attractions + 1)]
    if attraction_visits:
        model.Add(sum(attraction_visits) <= max_activities)
        model.Add(sum(attraction_visits) >= min(1, len(attraction_visits)))

    total_travel = sum(
        travel(i, j) * arc_lit[(i, j)] for i in range(n_nodes) for j in range(n_nodes) if i != j
    )
    model.Add(total_travel <= max_travel_min)

    if budget is not None:
        cost_terms = [
            int(round(usable[i - 1].candidate.entry_cost_max)) * visit[i]
            for i in range(1, n_attractions + 1)
        ]
        if cost_terms:
            model.Add(sum(cost_terms) <= int(round(budget)))

    # ---- objective ---------------------------------------------------------
    # Scores can be negative after penalties; shift so skipping is never rewarded.
    raw_scores = [usable[i - 1].total_score for i in range(1, n_attractions + 1)]
    shift = min(0.0, min(raw_scores) if raw_scores else 0.0)
    score_terms = [
        int(round((raw_scores[i - 1] - shift + 0.05) * SCORE_SCALE)) * visit[i]
        for i in range(1, n_attractions + 1)
    ]
    model.Maximize(sum(score_terms) - TRAVEL_WEIGHT * total_travel)

    # ---- solve -------------------------------------------------------------
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(settings.ortools_time_limit_seconds)
    solver.parameters.num_workers = 1  # determinism over raw speed
    solver.parameters.random_seed = settings.planner_random_seed
    solver.parameters.log_search_progress = False
    status = solver.Solve(model)
    status_name = solver.StatusName(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return DayPlanResult(
            request.day_index,
            [],
            0.0,
            0,
            status_name,
            0.0,
            (time.perf_counter() - started) * 1000,
            unscheduled_mandatory=unscheduled_mandatory,
        )

    # ---- decode ------------------------------------------------------------
    selected = [node for node in range(1, n_nodes) if solver.Value(visit[node]) == 1]
    selected.sort(key=lambda node: solver.Value(start[node]))

    activities: list[PlannedActivity] = []
    total_km = 0.0
    total_min = 0
    previous = 0
    for sequence, node in enumerate(selected, start=1):
        leg_min = travel(previous, node)
        leg_km = travel_km(previous, node)
        total_km += leg_km
        total_min += leg_min
        s_start = solver.Value(start[node])
        service = service_of(node)

        if node == meal_index:
            activities.append(
                PlannedActivity(
                    kind="meal",
                    sequence=sequence,
                    title="Meal break",
                    start_min=s_start,
                    end_min=s_start + service,
                    travel_from_prev_min=leg_min,
                    travel_from_prev_km=round(leg_km, 3),
                    travel_mode=request.transport_mode,
                    why_selected="A midday break is reserved so the plan stays realistic.",
                )
            )
        elif node == rest_index:
            activities.append(
                PlannedActivity(
                    kind="rest",
                    sequence=sequence,
                    title="Rest break",
                    start_min=s_start,
                    end_min=s_start + service,
                    travel_from_prev_min=leg_min,
                    travel_from_prev_km=round(leg_km, 3),
                    travel_mode=request.transport_mode,
                    why_selected="Added because the group asked for a relaxed pace.",
                )
            )
        else:
            scored = usable[node - 1]
            c = scored.candidate
            # The window this visit actually sits inside. Picking the one that
            # contains the scheduled start (rather than the first of the day)
            # matters for split-hours sites like temples that shut at midday.
            opens_min, closes_min = _containing_window(c, request.weekday, s_start)
            activities.append(
                PlannedActivity(
                    kind="visit",
                    sequence=sequence,
                    title=c.name,
                    slug=c.slug,
                    attraction_id=c.attraction_id,
                    start_min=s_start,
                    end_min=s_start + service,
                    opens_min=opens_min,
                    closes_min=closes_min,
                    lat=c.lat,
                    lon=c.lon,
                    travel_from_prev_min=leg_min,
                    travel_from_prev_km=round(leg_km, 3),
                    travel_mode=request.transport_mode,
                    est_cost_low_inr=c.entry_cost_min,
                    est_cost_high_inr=c.entry_cost_max,
                    weather_suitability=scored.breakdown.weather_suitability,
                    why_selected=scored.explanation,
                    score_breakdown=scored.breakdown.to_dict(),
                    is_mandatory=scored.is_mandatory,
                    warnings=_activity_warnings(scored, request.weather),
                )
            )
        previous = node

    # Return leg to base.
    if selected:
        total_km += travel_km(previous, 0)
        total_min += travel(previous, 0)

    return DayPlanResult(
        day_index=request.day_index,
        activities=activities,
        travel_km=round(total_km, 3),
        travel_min=int(total_min),
        status=status_name,
        objective=float(solver.ObjectiveValue()),
        solve_ms=round((time.perf_counter() - started) * 1000, 2),
        unscheduled_mandatory=unscheduled_mandatory,
    )


def _activity_warnings(scored: ScoredAttraction, weather: DayWeather | None) -> list[str]:
    c = scored.candidate
    warnings: list[str] = []
    if c.needs_verification:
        warnings.append(
            c.verification_note
            or "Opening hours and fees change - verify with the official source before visiting."
        )
    if weather is not None and scored.breakdown.weather_suitability < 0.6:
        warnings.append("The forecast is poor for this outdoor stop - have an indoor backup.")
    if c.typical_crowd_level in ("high", "very_high"):
        warnings.append("Expect significant crowds; arriving at opening time helps.")
    if c.physical_intensity >= 4:
        warnings.append("Physically demanding - not suitable for everyone in a mixed group.")
    if c.wheelchair_accessible == "no":
        warnings.append("Not wheelchair accessible.")
    return warnings


def build_matrix_points(
    base: tuple[float, float], candidates: Sequence[ScoredAttraction]
) -> list[tuple[float, float]]:
    """Depot first, then candidates - the index layout the solver assumes."""
    return [base] + [(s.candidate.lat, s.candidate.lon) for s in candidates]


def pace_limits(ctx: TripContext) -> tuple[int, int]:
    profile = PACE_PROFILE.get(ctx.pace, PACE_PROFILE["balanced"])
    return int(profile["max_activities"]), int(profile["max_travel_min"])
