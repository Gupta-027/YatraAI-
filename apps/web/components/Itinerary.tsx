'use client';

import { useState } from 'react';

import type { Activity, Itinerary, ItineraryDay } from '@/lib/types';
import { SCORE_LABEL, cn, durationLabel, percent, rupees, titleise, weatherIcon } from '@/lib/utils';

import { Badge, Button, Callout, Card, Meter } from './ui';

/* -------------------------------------------------------------------------- */
/* Day timeline                                                                */
/* -------------------------------------------------------------------------- */
export function DayTimeline({
  day,
  onOpenPlace,
  onRemove,
  onReplace,
  readOnly,
}: {
  day: ItineraryDay;
  onOpenPlace: (slug: string, why: string) => void;
  onRemove?: (slug: string) => void;
  onReplace?: (slug: string) => void;
  readOnly?: boolean;
}) {
  const visits = day.activities.filter((a) => a.kind === 'visit');

  return (
    <Card className="overflow-hidden">
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 border-b border-[rgb(var(--line))] bg-[rgb(var(--surface-2))] px-5 py-4">
        <div className="flex items-center gap-3">
          <span
            aria-hidden="true"
            className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-indigo-600 font-display text-lg font-bold text-white"
          >
            {day.day_index + 1}
          </span>
          <div>
            <h3 className="font-display text-lg leading-tight text-ink dark:text-sand-100">
              <span className="sr-only">Day {day.day_index + 1} — </span>
              {new Date(day.calendar_date + 'T00:00:00').toLocaleDateString('en-IN', {
                weekday: 'long',
                day: 'numeric',
                month: 'long',
              })}
            </h3>
            {day.theme && <p className="text-xs text-ink-faint">{day.theme}</p>}
          </div>
        </div>

        {/* Day totals as plain figures rather than badges — four grey pills read as
            decoration, while labelled numbers read as a summary. */}
        <dl className="flex flex-wrap items-center gap-x-5 gap-y-1 text-right">
          {day.weather?.condition && (
            <div>
              <dt className="text-[10px] uppercase tracking-wide text-ink-faint">Weather</dt>
              <dd
                className={cn(
                  'text-sm font-semibold tabular-nums',
                  day.weather.is_fallback
                    ? 'text-saffron-600 dark:text-saffron-300'
                    : 'text-ink dark:text-sand-200'
                )}
                title={
                  day.weather.is_fallback
                    ? 'Seasonal climatology, not a live forecast'
                    : undefined
                }
              >
                {weatherIcon(day.weather.condition)}
                {day.weather.temp_max_c !== null && day.weather.temp_max_c !== undefined
                  ? ` ${Math.round(day.weather.temp_min_c ?? 0)}–${Math.round(day.weather.temp_max_c)}°`
                  : ''}
              </dd>
            </div>
          )}
          <div>
            <dt className="text-[10px] uppercase tracking-wide text-ink-faint">Stops</dt>
            <dd className="text-sm font-semibold tabular-nums text-ink dark:text-sand-200">
              {visits.length}
            </dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-wide text-ink-faint">Travel</dt>
            <dd className="text-sm font-semibold tabular-nums text-ink dark:text-sand-200">
              {day.travel_km.toFixed(1)} km
            </dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-wide text-ink-faint">Moving</dt>
            <dd className="text-sm font-semibold tabular-nums text-ink dark:text-sand-200">
              {durationLabel(day.travel_min)}
            </dd>
          </div>
        </dl>
      </header>

      {(day.weather_advisories.length > 0 || day.notes) && (
        <div className="space-y-1.5 border-b border-[rgb(var(--line))] px-5 py-3">
          {day.notes && <p className="text-xs text-indigo-600 dark:text-indigo-300">{day.notes}</p>}
          {day.weather_advisories.map((advisory) => (
            <p key={advisory} className="text-xs text-saffron-600 dark:text-saffron-300">
              {advisory}
            </p>
          ))}
        </div>
      )}

      {day.activities.length === 0 ? (
        <p className="px-5 py-10 text-center text-sm text-ink-faint">
          Nothing scheduled. The solver found no candidate that fits this day&apos;s constraints.
        </p>
      ) : (
        <ol className="px-5 py-4">
          {day.activities.map((activity, i) => (
            <ActivityRow
              key={activity.id}
              activity={activity}
              isLast={i === day.activities.length - 1}
              onOpenPlace={onOpenPlace}
              onRemove={onRemove}
              onReplace={onReplace}
              readOnly={readOnly}
            />
          ))}
        </ol>
      )}
    </Card>
  );
}

/**
 * The opening window this visit was scheduled inside.
 *
 * Three distinct states, and collapsing any two of them would mislead:
 *
 * - **Recorded hours** — shown, with the unverified caveat the dataset carries.
 * - **No recorded hours** — says so. It must never render as "open all day",
 *   which is what the solver internally substitutes so it has *some* window to
 *   plan against.
 * - **Not a place** — meals and rest breaks have no hours at all; render nothing.
 */
function OpeningHours({ activity }: { activity: Activity }) {
  if (!activity.opens_time || !activity.closes_time) {
    return (
      <p className="mt-0.5 text-xs text-ink-faint">
        Opening hours not recorded — check before you go
      </p>
    );
  }
  return (
    <p className="mt-0.5 text-xs text-ink-muted dark:text-sand-400">
      <span className="font-medium">Open</span>{' '}
      <span className="font-mono tabular-nums">
        {activity.opens_time}–{activity.closes_time}
      </span>{' '}
      <span className="text-ink-faint" title="Hours in this dataset are recorded as unverified">
        · unverified
      </span>
    </p>
  );
}

/** Dot colour by activity kind — a visit is the plan, a break is scaffolding. */
const KIND_DOT: Record<string, string> = {
  visit: 'bg-indigo-500',
  meal: 'bg-teal-400',
  rest: 'bg-sand-400 dark:bg-white/30',
  transfer: 'bg-sand-400 dark:bg-white/30',
};

function ActivityRow({
  activity,
  isLast,
  onOpenPlace,
  onRemove,
  onReplace,
  readOnly,
}: {
  activity: Activity;
  isLast?: boolean;
  onOpenPlace: (slug: string, why: string) => void;
  onRemove?: (slug: string) => void;
  onReplace?: (slug: string) => void;
  readOnly?: boolean;
}) {
  const [showWhy, setShowWhy] = useState(false);
  const isVisit = activity.kind === 'visit';

  return (
    <li>
      {/* Travel leg. Drawn as a dashed segment of the same spine, so a gap in the
          day is visibly a journey rather than an unexplained blank. */}
      {activity.travel_from_prev_min > 0 && (
        <div className="flex gap-3">
          <span className="w-14 shrink-0" />
          <span className="flex w-3 shrink-0 justify-center" aria-hidden="true">
            <span className="h-full w-px border-l border-dashed border-[rgb(var(--line))]" />
          </span>
          <p className="min-w-0 flex-1 py-2 text-xs text-ink-faint">
            {activity.travel_from_prev_min} min travel
            {activity.travel_from_prev_km > 0 && ` · ${activity.travel_from_prev_km.toFixed(1)} km`}
            {' · '}
            {titleise(activity.travel_mode)}
          </p>
        </div>
      )}

      <div className="flex gap-3">
        {/* Time rail */}
        <div className="flex w-14 shrink-0 flex-col items-end">
          <span className="font-mono text-sm font-semibold leading-5 tabular-nums text-indigo-600 dark:text-indigo-300">
            {activity.start_time}
          </span>
          <span className="font-mono text-xs leading-4 tabular-nums text-ink-faint">
            {activity.end_time}
          </span>
        </div>

        {/* Spine: a continuous line with a dot marking each stop. This is what
            turns a list of rows into something that reads as a day. */}
        <div className="relative flex w-3 shrink-0 justify-center" aria-hidden="true">
          {!isLast && <span className="absolute inset-y-0 top-3 w-px bg-[rgb(var(--line))]" />}
          <span
            className={cn(
              'relative mt-1.5 h-2.5 w-2.5 rounded-full ring-4 ring-[rgb(var(--surface))]',
              KIND_DOT[activity.kind] ?? KIND_DOT.visit
            )}
          />
        </div>

        <div className="min-w-0 flex-1 pb-5">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <h4
                className={cn(
                  'font-semibold leading-5',
                  isVisit
                    ? 'text-[15px] text-ink dark:text-sand-100'
                    : 'text-sm text-ink-muted dark:text-sand-400'
                )}
              >
                {isVisit ? (
                  <button
                    onClick={() => onOpenPlace(activity.attraction_slug!, activity.why_selected)}
                    className="group/title text-left hover:text-indigo-600 dark:hover:text-indigo-300"
                  >
                    <span className="underline decoration-transparent underline-offset-2 transition-colors group-hover/title:decoration-current">
                      {activity.title}
                    </span>
                    <span
                      aria-hidden="true"
                      className="ml-1 text-ink-faint transition-transform group-hover/title:translate-x-0.5"
                    >
                      ›
                    </span>
                    <span className="sr-only"> — open details</span>
                  </button>
                ) : (
                  activity.title
                )}
              </h4>
              <p className="mt-0.5 text-xs text-ink-muted dark:text-sand-400">
                <span className="font-medium">{durationLabel(activity.duration_min)}</span>
                {activity.est_cost_high_inr > 0 && (
                  <>
                    {' · entry '}
                    <span className="tabular-nums">
                      {activity.est_cost_low_inr === activity.est_cost_high_inr
                        ? rupees(activity.est_cost_high_inr)
                        : `${rupees(activity.est_cost_low_inr)}–${rupees(activity.est_cost_high_inr)}`}
                    </span>
                    {' pp'}
                  </>
                )}
              </p>
              {isVisit && <OpeningHours activity={activity} />}
            </div>

            <div className="flex shrink-0 flex-wrap gap-1.5">
              {activity.is_mandatory && <Badge tone="indigo">Must visit</Badge>}
              {isVisit && activity.weather_suitability < 0.6 && (
                <Badge tone="saffron" title="The forecast is poor for this outdoor stop">
                  Weather risk
                </Badge>
              )}
              {activity.kind === 'meal' && <Badge tone="teal">Break</Badge>}
            </div>
          </div>

          {activity.warnings.length > 0 && (
            <ul className="mt-2 space-y-1">
              {activity.warnings.map((w) => (
                <li
                  key={w}
                  className="flex gap-1.5 rounded-lg bg-saffron-50 px-2 py-1 text-xs text-saffron-700 dark:bg-saffron-400/10 dark:text-saffron-200"
                >
                  <span aria-hidden="true">!</span>
                  <span>{w}</span>
                </li>
              ))}
            </ul>
          )}

          {isVisit && (
            <>
              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
                <button
                  onClick={() => setShowWhy((v) => !v)}
                  aria-expanded={showWhy}
                  className="text-xs font-semibold text-indigo-600 hover:underline dark:text-indigo-300"
                >
                  {showWhy ? 'Hide reasoning' : 'Why was this selected?'}
                </button>
                {/* Editing actions are secondary to reading the plan, so they sit
                    inline and quiet rather than as a row of buttons under every stop. */}
                {!readOnly && onReplace && (
                  <button
                    onClick={() => onReplace(activity.attraction_slug!)}
                    className="text-xs text-ink-faint hover:text-ink hover:underline dark:hover:text-sand-200"
                  >
                    Replace
                  </button>
                )}
                {!readOnly && onRemove && (
                  <button
                    onClick={() => onRemove(activity.attraction_slug!)}
                    className="text-xs text-ink-faint hover:text-clay-600 hover:underline dark:hover:text-clay-300"
                  >
                    Remove
                  </button>
                )}
              </div>

              {showWhy && (
                <div className="mt-2 rounded-xl border border-[rgb(var(--line))] bg-[rgb(var(--surface-2))] p-3.5">
                  <p className="mb-3 text-sm text-ink-muted dark:text-sand-300">
                    {activity.why_selected}
                  </p>
                  <ScoreBreakdown breakdown={activity.score_breakdown} />
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </li>
  );
}

/** Renders the stored score components — the numbers the optimiser actually used. */
export function ScoreBreakdown({ breakdown }: { breakdown: Record<string, number> }) {
  const positives = Object.entries(breakdown).filter(
    ([k, v]) => !k.includes('penalty') && k !== 'mandatory_bonus' && v > 0
  );
  const penalties = Object.entries(breakdown).filter(([k, v]) => k.includes('penalty') && v > 0);

  if (!positives.length && !penalties.length) {
    return <p className="text-xs text-ink-faint">No score breakdown stored for this activity.</p>;
  }

  return (
    <div className="space-y-2">
      {positives
        .sort((a, b) => b[1] - a[1])
        .map(([key, value]) => (
          <div key={key} className="grid grid-cols-[minmax(0,10rem)_1fr] items-center gap-3">
            <span className="truncate text-xs text-ink-muted dark:text-sand-400">
              {SCORE_LABEL[key] ?? titleise(key)}
            </span>
            <Meter value={value} label={SCORE_LABEL[key] ?? key} />
          </div>
        ))}
      {penalties.map(([key, value]) => (
        <div key={key} className="grid grid-cols-[minmax(0,10rem)_1fr] items-center gap-3">
          <span className="truncate text-xs text-ink-muted dark:text-sand-400">
            {SCORE_LABEL[key] ?? titleise(key)}
          </span>
          <Meter value={value} tone="clay" label={SCORE_LABEL[key] ?? key} />
        </div>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Summary panels                                                              */
/* -------------------------------------------------------------------------- */
export function ItinerarySummary({ itinerary }: { itinerary: Itinerary }) {
  return (
    <div className="space-y-4">
      <Card className="p-5">
        <h3 className="mb-3 font-display text-base text-ink dark:text-sand-100">Trip totals</h3>
        <dl className="grid grid-cols-2 gap-3">
          <Stat label="Stops" value={String(itinerary.activity_count)} />
          <Stat label="Travel" value={`${itinerary.total_travel_km.toFixed(0)} km`} />
          <Stat label="Time moving" value={durationLabel(itinerary.total_travel_min)} />
          <Stat label="Time visiting" value={durationLabel(itinerary.total_visit_min)} />
        </dl>
      </Card>

      <Card className="p-5">
        <h3 className="mb-1 font-display text-base text-ink dark:text-sand-100">Estimated cost</h3>
        <p className="mb-3 font-display text-2xl text-indigo-600 dark:text-indigo-300">
          {rupees(itinerary.cost.per_person_low_inr)} – {rupees(itinerary.cost.per_person_high_inr)}
        </p>
        <p className="mb-3 text-xs text-ink-faint">
          per person · {rupees(itinerary.cost.low_inr)} – {rupees(itinerary.cost.high_inr)} total
        </p>
        <ul className="space-y-1.5">
          {Object.entries(itinerary.cost.breakdown).map(([key, band]) => (
            <li key={key} className="flex justify-between text-sm">
              <span className="text-ink-muted dark:text-sand-400">{titleise(key)}</span>
              <span className="tabular-nums text-ink dark:text-sand-200">
                {rupees(band.low)} – {rupees(band.high)}
              </span>
            </li>
          ))}
        </ul>
        <details className="mt-3">
          <summary className="cursor-pointer text-xs font-semibold text-indigo-600 dark:text-indigo-300">
            How this was calculated
          </summary>
          <ul className="mt-2 space-y-1.5">
            {itinerary.cost.assumptions.map((a) => (
              <li key={a} className="text-xs text-ink-muted dark:text-sand-400">
                {a}
              </li>
            ))}
          </ul>
        </details>
      </Card>

      <Card className="p-5">
        <h3 className="mb-3 font-display text-base text-ink dark:text-sand-100">
          Group fairness
        </h3>
        <div className="space-y-3">
          <LabelledMeter
            label="Fairness index"
            value={itinerary.fairness_score}
            hint="Jain's index — 1.0 means everyone is equally served."
          />
          <LabelledMeter
            label="Least-satisfied member"
            value={itinerary.least_satisfied_score}
            hint="The floor this plan guarantees the worst-served person."
            tone="teal"
          />
          <LabelledMeter
            label="Consensus"
            value={itinerary.consensus_score}
            hint="How closely satisfaction is clustered across the group."
          />
        </div>

        {Object.keys(itinerary.preference_coverage).length > 0 && (
          <div className="mt-4 border-t border-[rgb(var(--line))] pt-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">
              Interest coverage
            </p>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(itinerary.preference_coverage).map(([interest, value]) => (
                <Badge key={interest} tone={value >= 0.5 ? 'teal' : 'saffron'}>
                  {titleise(interest)} {percent(value)}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </Card>

      <ValidationPanel itinerary={itinerary} />
    </div>
  );
}

export function ValidationPanel({ itinerary }: { itinerary: Itinerary }) {
  const { validation } = itinerary;
  return (
    <Card className="p-5">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="font-display text-base text-ink dark:text-sand-100">Validation</h3>
        <Badge tone={validation.is_valid ? 'teal' : 'clay'}>
          {validation.is_valid ? 'Passed' : 'Failed'}
        </Badge>
      </div>
      <p className="mb-3 text-xs text-ink-muted dark:text-sand-400">
        {validation.checks_run} constraint checks were re-derived independently of the optimiser.
        An itinerary is never displayed unless every error-level check passes.
      </p>

      {validation.errors.length > 0 && (
        <ul className="mb-3 space-y-1.5">
          {validation.errors.map((issue, i) => (
            <li key={i} className="text-xs text-clay-500">
              <strong>{issue.code}</strong>: {issue.message}
            </li>
          ))}
        </ul>
      )}

      {validation.warnings.length > 0 ? (
        <details>
          <summary className="cursor-pointer text-xs font-semibold text-saffron-600 dark:text-saffron-300">
            {validation.warnings.length} advisory warning
            {validation.warnings.length === 1 ? '' : 's'}
          </summary>
          <ul className="mt-2 space-y-1.5">
            {validation.warnings.map((issue, i) => (
              <li key={i} className="text-xs text-ink-muted dark:text-sand-400">
                {issue.message}
              </li>
            ))}
          </ul>
        </details>
      ) : (
        <p className="text-xs text-teal-500">No warnings.</p>
      )}

      {itinerary.degraded_services.length > 0 && (
        <Callout tone="saffron" title="Fallback data was used">
          {itinerary.degraded_services.map(titleise).join(', ')} data was unavailable when this plan
          was generated, so documented fallbacks were used instead.
        </Callout>
      )}
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-faint">{label}</dt>
      <dd className="font-display text-xl text-ink dark:text-sand-100">{value}</dd>
    </div>
  );
}

function LabelledMeter({
  label,
  value,
  hint,
  tone = 'indigo',
}: {
  label: string;
  value: number;
  hint: string;
  tone?: 'indigo' | 'teal';
}) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-sm text-ink dark:text-sand-200">{label}</span>
      </div>
      <Meter value={value} tone={tone} label={label} />
      <p className="mt-0.5 text-[11px] text-ink-faint">{hint}</p>
    </div>
  );
}
