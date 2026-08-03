"""Itinerary explanation - stage 8, the only place the LLM touches the plan.

The contract is strict: the LLM receives a **already-validated** structured
itinerary and is asked to narrate it. It cannot add, remove or reorder anything,
because its output is a paragraph of prose that sits *beside* the timeline, not
the timeline itself. If the model is unavailable the template version is used and
the response says so.
"""

from __future__ import annotations

from yatraai.logging_config import get_logger
from yatraai.services.llm.base import LLMMessage, LLMResponse, get_llm_provider, safe_context
from yatraai.services.planner.models import PlanResult, TripContext

log = get_logger(__name__)

SYSTEM_PROMPT = """You are a travel writer summarising an itinerary that has ALREADY been
computed and validated by a deterministic planner.

Absolute rules:
- Use ONLY the facts inside <context>. Never add attractions, timings, prices or claims.
- Never contradict the schedule. If a detail is absent, omit it rather than inventing it.
- Do not present opening hours or fees as confirmed; the data is explicitly unverified.
- Write 3 short paragraphs, warm and practical, in British English. No bullet points,
  no headings, no markdown.
- Mention the group-fairness reasoning if the context includes it.
- If the context mentions degraded data sources, acknowledge it in one clause."""


def _hhmm(minutes: int) -> str:
    return f"{int(minutes) // 60:02d}:{int(minutes) % 60:02d}"


def build_template_summary(result: PlanResult, ctx: TripContext) -> str:
    """Deterministic explanation. Always available; used verbatim without an LLM."""
    if not result.days or not any(d.visits for d in result.days):
        return "No feasible itinerary could be built from the current constraints."

    total_stops = result.metrics.activity_count
    lines: list[str] = [
        f"Your {ctx.days}-day {ctx.cluster_slug.replace('-', ' ').title()} plan covers "
        f"{total_stops} places at a {ctx.pace} pace, with about "
        f"{result.metrics.total_travel_km:.0f} km and "
        f"{result.metrics.total_travel_min // 60}h {result.metrics.total_travel_min % 60}m "
        f"of travel in total."
    ]

    for day in result.days:
        visits = day.visits
        if not visits:
            lines.append(f"Day {day.day_index + 1} ({day.calendar_date:%a %d %b}) is left free.")
            continue
        names = ", ".join(v.title for v in visits)
        lines.append(
            f"Day {day.day_index + 1} ({day.calendar_date:%a %d %b}) starts at "
            f"{_hhmm(visits[0].start_min)} and covers {names}, with "
            f"{day.travel_min} minutes of travel."
        )
        if day.weather_advisories:
            lines.append(f"  Weather note: {day.weather_advisories[0]}")
        if day.notes:
            lines.append(f"  {day.notes}")

    coverage = result.metrics.preference_coverage
    if coverage:
        well_covered = [k for k, v in coverage.items() if v >= 0.6]
        if well_covered:
            lines.append("Group interests represented: " + ", ".join(sorted(well_covered)) + ".")
    lines.append(
        f"Group fairness scored {result.metrics.fairness_score:.2f} out of 1.00, and the "
        f"least-well-served member still gets {result.metrics.least_satisfied_score:.0%} "
        "of what they asked for."
    )
    lines.append(
        f"Estimated cost: Rs.{result.cost.per_person_low_inr:,.0f}-"
        f"Rs.{result.cost.per_person_high_inr:,.0f} per person, including a contingency buffer."
    )
    lines.append(
        "Opening hours and entry fees in this plan are recorded as unverified - confirm them "
        "with the official source before you travel."
    )
    if result.degraded_services:
        lines.append(
            "Note: "
            + ", ".join(result.degraded_services)
            + " data was unavailable, so fallbacks were used."
        )
    return "\n".join(lines)


def _context_block(result: PlanResult, ctx: TripContext) -> str:
    parts = [
        f"Destination: {ctx.cluster_slug}",
        f"Dates: {ctx.start_date} to {ctx.end_date} ({ctx.days} days)",
        f"Travellers: {ctx.traveller_count}, pace: {ctx.pace}, transport: {ctx.transport_mode}",
        f"Total travel: {result.metrics.total_travel_km:.0f} km / "
        f"{result.metrics.total_travel_min} minutes",
        f"Group fairness index: {result.metrics.fairness_score:.2f}; least-satisfied member "
        f"coverage: {result.metrics.least_satisfied_score:.2f}",
        f"Estimated cost per person: Rs.{result.cost.per_person_low_inr:,.0f}-"
        f"Rs.{result.cost.per_person_high_inr:,.0f}",
        "",
    ]
    for day in result.days:
        parts.append(f"DAY {day.day_index + 1} ({day.calendar_date:%A %d %B}):")
        if day.weather:
            parts.append(
                f"  weather: {day.weather.condition}, "
                f"{day.weather.temp_min_c:.0f}-{day.weather.temp_max_c:.0f} C"
                + (" (seasonal average, not a forecast)" if day.weather.is_fallback else "")
            )
        for activity in day.activities:
            if activity.kind != "visit":
                parts.append(
                    f"  {_hhmm(activity.start_min)}-{_hhmm(activity.end_min)} {activity.title}"
                )
                continue
            parts.append(
                f"  {_hhmm(activity.start_min)}-{_hhmm(activity.end_min)} {activity.title} "
                f"({activity.travel_from_prev_min} min travel). Why: {activity.why_selected}"
            )
        if day.notes:
            parts.append(f"  note: {day.notes}")
        parts.append("")

    if result.degraded_services:
        parts.append(f"Degraded data sources: {', '.join(result.degraded_services)}")
    parts.append(
        "All opening hours and fees are recorded as UNVERIFIED and must be described as such."
    )
    return "\n".join(parts)


def explain_itinerary(result: PlanResult, ctx: TripContext) -> tuple[str, LLMResponse | None]:
    """Return ``(summary_text, llm_response_or_None)``.

    Falls back to the template silently on any failure - an itinerary is never
    blocked on the language model.
    """
    template = build_template_summary(result, ctx)
    provider = get_llm_provider()
    if provider.is_fallback:
        return template, None

    prompt = (
        "Summarise this validated itinerary for the travellers.\n\n"
        f"<context>\n{safe_context(_context_block(result, ctx))}\n</context>"
    )
    try:
        response = provider.complete(
            system=SYSTEM_PROMPT,
            messages=[LLMMessage("user", prompt)],
            max_tokens=700,
            temperature=0.4,
        )
        if response.is_fallback or len(response.text) < 80:
            return template, response
        return response.text, response
    except Exception as exc:  # pragma: no cover - providers self-heal
        log.warning("explain.failed", error=str(exc))
        return template, None
