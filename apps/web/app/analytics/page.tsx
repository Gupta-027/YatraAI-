'use client';

import { useQuery } from '@tanstack/react-query';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { PageShell } from '@/components/Shell';
import {
  Badge,
  Callout,
  Card,
  CardSkeleton,
  ErrorState,
  Meter,
  SectionHeading,
} from '@/components/ui';
import { api } from '@/lib/api';
import { percent, rupees, titleise } from '@/lib/utils';

const CHART_COLOURS = ['#23306b', '#e07a3f', '#0f7b6c', '#7285cd', '#c9612a', '#4fc4b0'];

export default function AnalyticsPage() {
  const metrics = useQuery({ queryKey: ['dashboard'], queryFn: api.dashboard });
  const attractions = useQuery({ queryKey: ['attraction-stats'], queryFn: api.attractionStats });

  if (metrics.isLoading) {
    return (
      <PageShell>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <CardSkeleton key={i} lines={2} />
          ))}
        </div>
      </PageShell>
    );
  }

  if (metrics.error) {
    return (
      <PageShell>
        <ErrorState
          message={(metrics.error as Error).message}
          onRetry={() => void metrics.refetch()}
        />
      </PageShell>
    );
  }

  const m = metrics.data!;

  return (
    <PageShell>
      <SectionHeading
        level={1}
        title="Metrics"
        description="Aggregates only. Coordinates are stripped at write time and never reach an analytics row."
      />

      {/* ---- headline ---- */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Trips created" value={String(m.trips.total ?? 0)} />
        <Stat label="Itineraries generated" value={String(m.itineraries.total ?? 0)} />
        <Stat
          label="Average group size"
          value={String(m.trips.average_group_size ?? 0)}
          hint="travellers per trip"
        />
        <Stat
          label="Average budget"
          value={rupees(m.trips.average_budget_per_person_inr ?? 0)}
          hint="per person"
        />
      </div>

      <div className="mb-6 grid gap-5 lg:grid-cols-2">
        {/* ---- destination popularity ---- */}
        <Card className="p-5">
          <h2 className="mb-4 font-display text-base text-ink dark:text-sand-100">
            Destination popularity
          </h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={m.destination_popularity} layout="vertical" margin={{ left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 11 }} stroke="rgb(var(--text-muted))" />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={130}
                  tick={{ fontSize: 11 }}
                  stroke="rgb(var(--text-muted))"
                />
                <Tooltip
                  contentStyle={{
                    background: 'rgb(var(--surface))',
                    border: '1px solid rgb(var(--line))',
                    borderRadius: 12,
                    fontSize: 12,
                  }}
                />
                <Bar dataKey="trips" radius={[0, 6, 6, 0]}>
                  {m.destination_popularity.map((_, i) => (
                    <Cell key={i} fill={CHART_COLOURS[i % CHART_COLOURS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* ---- itinerary quality ---- */}
        <Card className="p-5">
          <h2 className="mb-4 font-display text-base text-ink dark:text-sand-100">
            Itinerary quality
          </h2>
          <div className="space-y-3.5">
            <MetricRow
              label="Average fairness (Jain)"
              value={m.itineraries.average_fairness}
              hint="1.0 means every member is equally served"
            />
            <MetricRow
              label="Least-satisfied member"
              value={m.itineraries.average_least_satisfied}
              hint="The floor guaranteed to the worst-served person"
              tone="teal"
            />
            <MetricRow
              label="Consensus"
              value={m.itineraries.average_consensus}
              hint="How tightly satisfaction is clustered"
            />
            <MetricRow
              label="Constraint violation rate"
              value={m.itineraries.constraint_violation_rate}
              hint="Itineraries that failed validation — should be zero"
              tone="clay"
            />
            <MetricRow
              label="Regeneration rate"
              value={m.itineraries.regeneration_rate}
              hint="How often users ask for a new version"
              tone="saffron"
            />
            <MetricRow
              label="LLM explanation rate"
              value={m.itineraries.llm_explanation_rate}
              hint="Rest fall back to deterministic templates"
            />
          </div>
          <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-[rgb(var(--line))] pt-3">
            <MiniStat
              label="Avg travel"
              value={`${(m.itineraries.average_travel_km ?? 0).toFixed(0)} km`}
            />
            <MiniStat
              label="Avg stops"
              value={String((m.itineraries.average_activities ?? 0).toFixed(1))}
            />
            <MiniStat
              label="Removals"
              value={String(m.itineraries.attraction_removal_events ?? 0)}
            />
          </dl>
        </Card>
      </div>

      <div className="mb-6 grid gap-5 lg:grid-cols-3">
        {/* ---- RAG ---- */}
        <Card className="p-5">
          <h2 className="mb-4 font-display text-base text-ink dark:text-sand-100">
            Assistant quality
          </h2>
          {m.rag.evaluations ? (
            <div className="space-y-3">
              <MetricRow label="Retrieval precision" value={m.rag.average_retrieval_precision} />
              <MetricRow label="Faithfulness" value={m.rag.average_faithfulness} tone="teal" />
              <MetricRow label="Citation correctness" value={m.rag.average_citation_correctness} />
              <MetricRow label="Answer completeness" value={m.rag.average_completeness} />
              <p className="text-xs text-ink-faint">
                {m.rag.evaluations} benchmark questions ·{' '}
                {(m.rag.average_latency_ms ?? 0).toFixed(0)} ms average
              </p>
            </div>
          ) : (
            <p className="text-sm text-ink-faint">
              No evaluation runs recorded yet. Run{' '}
              <code className="rounded bg-black/5 px-1 dark:bg-white/10">
                python evaluation/run_rag_eval.py
              </code>
              .
            </p>
          )}
        </Card>

        {/* ---- providers ---- */}
        <Card className="p-5">
          <h2 className="mb-4 font-display text-base text-ink dark:text-sand-100">
            Provider health
          </h2>
          <ul className="space-y-3">
            {Object.entries(m.providers).map(([service, stats]) => (
              <li key={service}>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm text-ink dark:text-sand-200">{titleise(service)}</span>
                  <Badge tone={Number(stats.error_rate ?? 0) > 0 ? 'clay' : 'teal'}>
                    {Number(stats.calls ?? 0)} calls
                  </Badge>
                </div>
                <p className="text-xs text-ink-faint">
                  p95 {Number(stats.p95_ms ?? 0).toFixed(0)} ms · fallback{' '}
                  {percent(Number(stats.fallback_rate ?? 0))} · errors{' '}
                  {percent(Number(stats.error_rate ?? 0))}
                </p>
              </li>
            ))}
            {Object.keys(m.providers).length === 0 && (
              <li className="text-sm text-ink-faint">No provider calls recorded yet.</li>
            )}
          </ul>
        </Card>

        {/* ---- data freshness ---- */}
        <Card className="p-5">
          <h2 className="mb-4 font-display text-base text-ink dark:text-sand-100">
            Data pipeline
          </h2>
          <dl className="space-y-2 text-sm">
            <Row label="Last pipeline" value={String(m.data_freshness.last_pipeline ?? 'never run')} />
            <Row label="Status" value={String(m.data_freshness.status ?? '—')} />
            <Row label="Rows produced" value={String(m.data_freshness.rows_out ?? 0)} />
            <Row
              label="Finished"
              value={
                m.data_freshness.last_run_at
                  ? new Date(String(m.data_freshness.last_run_at)).toLocaleString('en-IN')
                  : '—'
              }
            />
          </dl>
          <div className="mt-4 border-t border-[rgb(var(--line))] pt-3">
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-faint">
              Location privacy
            </p>
            <p className="text-sm text-ink dark:text-sand-200">
              {m.location_privacy.sessions_active} active of {m.location_privacy.sessions_total}{' '}
              sessions
            </p>
            <p className="mt-1 text-xs text-ink-faint">{m.location_privacy.note}</p>
          </div>
        </Card>
      </div>

      {/* ---- cost accuracy honesty ---- */}
      <div className="mb-6">
        <Callout
          tone={m.feedback.spend_comparison.samples > 0 ? 'teal' : 'saffron'}
          title="Cost-estimate accuracy"
        >
          {m.feedback.spend_comparison.samples > 0 ? (
            <>
              {m.feedback.spend_comparison.samples} trips reported actual spend.{' '}
              {percent(m.feedback.spend_comparison.within_estimated_range ?? 0)} fell inside the
              estimated range, with a mean absolute error of{' '}
              {percent(m.feedback.spend_comparison.mean_absolute_percentage_error ?? 0)}.
            </>
          ) : (
            m.feedback.spend_comparison.note
          )}
        </Callout>
      </div>

      {/* ---- attraction selection ---- */}
      <Card className="p-5">
        <h2 className="mb-1 font-display text-base text-ink dark:text-sand-100">
          Which attractions the planner picks
        </h2>
        <p className="mb-4 text-xs text-ink-muted dark:text-sand-400">
          Selection rate is how often a scored attraction actually made it into an itinerary. A
          consistently low rate on a high-quality place usually means a geography or opening-hours
          problem worth investigating.
        </p>
        {attractions.isLoading && <CardSkeleton lines={4} />}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[rgb(var(--line))] text-left text-xs uppercase tracking-wide text-ink-faint">
                <th className="pb-2 pr-4 font-medium">Attraction</th>
                <th className="pb-2 pr-4 font-medium">Scored</th>
                <th className="pb-2 pr-4 font-medium">Selected</th>
                <th className="pb-2 pr-4 font-medium">Rate</th>
                <th className="pb-2 font-medium">Avg score</th>
              </tr>
            </thead>
            <tbody>
              {attractions.data?.map((row) => (
                <tr key={row.attraction_slug} className="border-b border-[rgb(var(--line))]/60">
                  <td className="py-2 pr-4 text-ink dark:text-sand-200">{row.name}</td>
                  <td className="py-2 pr-4 tabular-nums text-ink-muted">{row.times_scored}</td>
                  <td className="py-2 pr-4 tabular-nums text-ink-muted">{row.times_selected}</td>
                  <td className="py-2 pr-4">
                    <div className="w-24">
                      <Meter
                        value={row.selection_rate}
                        tone={row.selection_rate > 0.5 ? 'teal' : 'saffron'}
                      />
                    </div>
                  </td>
                  <td className="py-2 tabular-nums text-ink-muted">
                    {row.average_score.toFixed(3)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </PageShell>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card className="p-5">
      <p className="text-xs text-ink-faint">{label}</p>
      <p className="font-display text-3xl text-indigo-600 dark:text-indigo-300">{value}</p>
      {hint && <p className="text-xs text-ink-faint">{hint}</p>}
    </Card>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[11px] text-ink-faint">{label}</dt>
      <dd className="text-sm font-semibold text-ink dark:text-sand-200">{value}</dd>
    </div>
  );
}

function MetricRow({
  label,
  value,
  hint,
  tone = 'indigo',
}: {
  label: string;
  value: number;
  hint?: string;
  tone?: 'indigo' | 'teal' | 'saffron' | 'clay';
}) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="text-sm text-ink dark:text-sand-200">{label}</span>
        <span className="text-sm font-semibold tabular-nums text-ink dark:text-sand-100">
          {value.toFixed(3)}
        </span>
      </div>
      <Meter value={value} tone={tone} label={label} />
      {hint && <p className="mt-0.5 text-[11px] text-ink-faint">{hint}</p>}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-ink-muted dark:text-sand-400">{label}</dt>
      <dd className="text-ink dark:text-sand-200">{value}</dd>
    </div>
  );
}
