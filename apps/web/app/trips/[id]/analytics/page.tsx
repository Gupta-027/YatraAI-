'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import {
  CartesianGrid,
  Line,
  LineChart,
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
import { useRequireAuth } from '@/lib/auth';
import { percent, rupees, titleise } from '@/lib/utils';

interface Version {
  version: number;
  generator: string;
  trigger: string;
  status: string;
  activities: number;
  travel_km: number;
  fairness: number;
  least_satisfied: number;
  cost_low: number;
  cost_high: number;
  created_at: string;
}

export default function TripAnalyticsPage() {
  const { id } = useParams<{ id: string }>();
  const { loading } = useRequireAuth();

  const data = useQuery({
    queryKey: ['trip-analytics', id],
    queryFn: () => api.tripAnalytics(id),
    enabled: !!id && !loading,
  });
  const recs = useQuery({
    queryKey: ['recommendations', id],
    queryFn: () => api.recommendations(id),
    enabled: !!id && !loading,
    retry: false,
  });

  if (data.isLoading) {
    return (
      <PageShell>
        <CardSkeleton lines={6} />
      </PageShell>
    );
  }
  if (data.error) {
    return (
      <PageShell>
        <ErrorState message={(data.error as Error).message} />
      </PageShell>
    );
  }

  const payload = data.data as unknown as {
    title: string;
    destination: string;
    members: number;
    versions: Version[];
    current: {
      fairness: number;
      consensus: number;
      least_satisfied: number;
      preference_coverage: Record<string, number>;
      per_member_coverage: Record<string, number>;
      validation: { checks_run?: number; errors?: unknown[]; warnings?: unknown[] };
      degraded_services: string[];
      solver_stats: Record<string, unknown>;
    } | null;
  };

  const chartData = payload.versions.map((v) => ({
    name: `v${v.version}`,
    fairness: Number((v.fairness * 100).toFixed(1)),
    leastSatisfied: Number((v.least_satisfied * 100).toFixed(1)),
    travel: Number(v.travel_km.toFixed(0)),
  }));

  return (
    <PageShell>
      <div className="mb-2">
        <Link href={`/trips/${id}`} className="text-sm text-ink-muted hover:underline dark:text-sand-400">
          ← Back to itinerary
        </Link>
      </div>

      <SectionHeading
        level={1}
        title="Why these places?"
        description={`${payload.title} · ${payload.destination} · ${payload.members} members`}
      />

      {payload.current && (
        <div className="mb-5 grid gap-4 sm:grid-cols-3">
          <Card className="p-5">
            <p className="text-xs text-ink-faint">Fairness index</p>
            <p className="font-display text-3xl text-indigo-600 dark:text-indigo-300">
              {payload.current.fairness.toFixed(3)}
            </p>
            <Meter value={payload.current.fairness} label="Fairness" />
          </Card>
          <Card className="p-5">
            <p className="text-xs text-ink-faint">Least-satisfied member</p>
            <p className="font-display text-3xl text-teal-500">
              {payload.current.least_satisfied.toFixed(3)}
            </p>
            <Meter value={payload.current.least_satisfied} tone="teal" label="Least satisfied" />
          </Card>
          <Card className="p-5">
            <p className="text-xs text-ink-faint">Consensus</p>
            <p className="font-display text-3xl text-saffron-500">
              {payload.current.consensus.toFixed(3)}
            </p>
            <Meter value={payload.current.consensus} tone="saffron" label="Consensus" />
          </Card>
        </div>
      )}

      {payload.versions.length > 1 && (
        <Card className="mb-5 p-5">
          <h2 className="mb-1 font-display text-base text-ink dark:text-sand-100">
            How the plan evolved
          </h2>
          <p className="mb-4 text-xs text-ink-muted dark:text-sand-400">
            Each modification produces a new version. This shows whether your changes helped or hurt
            the group.
          </p>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} stroke="rgb(var(--text-muted))" />
                <YAxis tick={{ fontSize: 11 }} stroke="rgb(var(--text-muted))" />
                <Tooltip
                  contentStyle={{
                    background: 'rgb(var(--surface))',
                    border: '1px solid rgb(var(--line))',
                    borderRadius: 12,
                    fontSize: 12,
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="fairness"
                  name="Fairness %"
                  stroke="#23306b"
                  strokeWidth={2}
                />
                <Line
                  type="monotone"
                  dataKey="leastSatisfied"
                  name="Least satisfied %"
                  stroke="#0f7b6c"
                  strokeWidth={2}
                />
                <Line
                  type="monotone"
                  dataKey="travel"
                  name="Travel km"
                  stroke="#e07a3f"
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <Card className="p-5">
          <h2 className="mb-3 font-display text-base text-ink dark:text-sand-100">
            Version history
          </h2>
          <ul className="space-y-2.5">
            {payload.versions.map((v) => (
              <li
                key={v.version}
                className="flex flex-wrap items-center justify-between gap-2 border-b border-[rgb(var(--line))]/60 pb-2.5 last:border-0"
              >
                <div>
                  <p className="text-sm font-medium text-ink dark:text-sand-200">
                    v{v.version} · {titleise(v.trigger)}
                  </p>
                  <p className="text-xs text-ink-faint">
                    {v.activities} stops · {v.travel_km.toFixed(0)} km ·{' '}
                    {rupees(v.cost_low)}–{rupees(v.cost_high)} pp
                  </p>
                </div>
                <div className="flex gap-1.5">
                  <Badge tone={v.status === 'active' ? 'teal' : 'neutral'}>
                    {titleise(v.status)}
                  </Badge>
                  <Badge tone="neutral">{titleise(v.generator)}</Badge>
                </div>
              </li>
            ))}
          </ul>
        </Card>

        {payload.current && (
          <Card className="p-5">
            <h2 className="mb-3 font-display text-base text-ink dark:text-sand-100">
              Per-member coverage
            </h2>
            <p className="mb-3 text-xs text-ink-muted dark:text-sand-400">
              How much of what each member asked for the plan actually delivers.
            </p>
            <ul className="space-y-3">
              {Object.entries(payload.current.per_member_coverage).map(([memberId, value]) => (
                <li key={memberId}>
                  <div className="mb-1 flex justify-between text-sm">
                    <span className="truncate font-mono text-xs text-ink-muted dark:text-sand-400">
                      {memberId.slice(0, 8)}
                    </span>
                    <span className="tabular-nums text-ink dark:text-sand-200">
                      {percent(value)}
                    </span>
                  </div>
                  <Meter value={value} tone={value < 0.4 ? 'clay' : 'teal'} label={memberId} />
                </li>
              ))}
            </ul>

            <div className="mt-4 border-t border-[rgb(var(--line))] pt-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">
                Interest coverage
              </p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(payload.current.preference_coverage).map(([k, v]) => (
                  <Badge key={k} tone={v >= 0.5 ? 'teal' : 'saffron'}>
                    {titleise(k)} {percent(v)}
                  </Badge>
                ))}
              </div>
            </div>
          </Card>
        )}
      </div>

      {recs.data && (
        <Card className="mt-5 p-5">
          <h2 className="mb-1 font-display text-base text-ink dark:text-sand-100">
            Ranked candidates
          </h2>
          <p className="mb-4 text-xs text-ink-muted dark:text-sand-400">
            Every attraction the planner considered, with the score it received and whether it made
            the itinerary. This is the recommendation system&apos;s actual output, not a summary of it.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[rgb(var(--line))] text-left text-xs uppercase tracking-wide text-ink-faint">
                  <th className="pb-2 pr-3 font-medium">#</th>
                  <th className="pb-2 pr-3 font-medium">Attraction</th>
                  <th className="pb-2 pr-3 font-medium">Score</th>
                  <th className="pb-2 pr-3 font-medium">Interest</th>
                  <th className="pb-2 pr-3 font-medium">Fairness</th>
                  <th className="pb-2 font-medium">In plan</th>
                </tr>
              </thead>
              <tbody>
                {recs.data.slice(0, 25).map((rec) => (
                  <tr key={rec.attraction_slug} className="border-b border-[rgb(var(--line))]/60">
                    <td className="py-2 pr-3 tabular-nums text-ink-faint">{rec.rank}</td>
                    <td className="py-2 pr-3 text-ink dark:text-sand-200">{rec.name}</td>
                    <td className="py-2 pr-3 tabular-nums text-ink-muted">
                      {rec.total_score.toFixed(3)}
                    </td>
                    <td className="py-2 pr-3">
                      <div className="w-16">
                        <Meter value={rec.components.interest_match ?? 0} />
                      </div>
                    </td>
                    <td className="py-2 pr-3">
                      <div className="w-16">
                        <Meter value={rec.components.group_fairness ?? 0} tone="teal" />
                      </div>
                    </td>
                    <td className="py-2">
                      {rec.selected ? (
                        <Badge tone="teal">Yes</Badge>
                      ) : (
                        <Badge tone="neutral">No</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {payload.current?.degraded_services && payload.current.degraded_services.length > 0 && (
        <div className="mt-5">
          <Callout tone="saffron" title="Fallback data was used for this plan">
            {payload.current.degraded_services.map(titleise).join(', ')}
          </Callout>
        </div>
      )}
    </PageShell>
  );
}
