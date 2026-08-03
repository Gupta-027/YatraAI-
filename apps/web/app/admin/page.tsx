'use client';

import { useQuery } from '@tanstack/react-query';

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
import { ApiRequestError, api } from '@/lib/api';
import { useRequireAuth } from '@/lib/auth';
import { relativeTime, titleise } from '@/lib/utils';

export default function AdminPage() {
  const { loading } = useRequireAuth();

  const quality = useQuery({
    queryKey: ['data-quality'],
    queryFn: api.dataQuality,
    enabled: !loading,
    retry: false,
  });
  const coverage = useQuery({
    queryKey: ['coverage'],
    queryFn: api.coverage,
    enabled: !loading,
    retry: false,
  });
  const runs = useQuery({
    queryKey: ['pipeline-runs'],
    queryFn: api.pipelineRuns,
    enabled: !loading,
    retry: false,
  });
  const ragRuns = useQuery({
    queryKey: ['rag-evaluations'],
    queryFn: api.ragEvaluations,
    enabled: !loading,
    retry: false,
  });

  const forbidden =
    quality.error instanceof ApiRequestError && quality.error.status === 403;

  return (
    <PageShell>
      <SectionHeading
        level={1}
        title="Data quality & operations"
        description="The same checks that gate the Airflow pipeline, evaluated against the live database. An error-level failure blocks a release."
      />

      {forbidden && (
        <Callout tone="saffron" title="Administrator access required">
          These endpoints are restricted to admin accounts. Promote a user by setting{' '}
          <code className="rounded bg-black/5 px-1 dark:bg-white/10">is_admin = true</code> on their
          row, then reload.
        </Callout>
      )}

      {quality.isLoading && <CardSkeleton lines={6} />}
      {quality.error && !forbidden && (
        <ErrorState message={(quality.error as Error).message} onRetry={() => void quality.refetch()} />
      )}

      {quality.data && (
        <>
          <div className="mb-5 grid gap-4 sm:grid-cols-4">
            <Stat
              label="Overall"
              value={quality.data.status.toUpperCase()}
              tone={
                quality.data.status === 'pass'
                  ? 'teal'
                  : quality.data.status === 'warn'
                    ? 'saffron'
                    : 'clay'
              }
            />
            <Stat label="Checks passed" value={`${quality.data.passed}/${quality.data.total}`} />
            <Stat label="Errors" value={String(quality.data.errors)} tone={quality.data.errors ? 'clay' : 'teal'} />
            <Stat
              label="Warnings"
              value={String(quality.data.warnings)}
              tone={quality.data.warnings ? 'saffron' : 'teal'}
            />
          </div>

          <Card className="mb-5 p-5">
            <h2 className="mb-3 font-display text-base text-ink dark:text-sand-100">Checks</h2>
            <ul className="space-y-2.5">
              {quality.data.checks.map((check) => (
                <li
                  key={check.name}
                  className="flex flex-wrap items-start justify-between gap-3 border-b border-[rgb(var(--line))]/60 pb-2.5 last:border-0"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-ink dark:text-sand-200">
                      {titleise(check.name)}
                    </p>
                    <p className="text-xs text-ink-muted dark:text-sand-400">{check.detail}</p>
                  </div>
                  <Badge
                    tone={check.passed ? 'teal' : check.severity === 'error' ? 'clay' : 'saffron'}
                  >
                    {check.passed ? 'Pass' : titleise(check.severity)}
                  </Badge>
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}

      {coverage.data && (
        <Card className="mb-5 p-5">
          <h2 className="mb-3 font-display text-base text-ink dark:text-sand-100">
            Catalogue coverage
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[rgb(var(--line))] text-left text-xs uppercase tracking-wide text-ink-faint">
                  <th className="pb-2 pr-4 font-medium">Destination</th>
                  <th className="pb-2 pr-4 font-medium">Attractions</th>
                  <th className="pb-2 pr-4 font-medium">Mean quality</th>
                  <th className="pb-2 pr-4 font-medium">Need verification</th>
                  <th className="pb-2 font-medium">Oldest review</th>
                </tr>
              </thead>
              <tbody>
                {(coverage.data as Record<string, unknown>[]).map((row) => (
                  <tr
                    key={String(row.cluster_slug)}
                    className="border-b border-[rgb(var(--line))]/60"
                  >
                    <td className="py-2 pr-4 text-ink dark:text-sand-200">{String(row.name)}</td>
                    <td className="py-2 pr-4 tabular-nums text-ink-muted">
                      {String(row.attractions)}
                    </td>
                    <td className="py-2 pr-4">
                      <div className="w-24">
                        <Meter value={Number(row.mean_quality)} />
                      </div>
                    </td>
                    <td className="py-2 pr-4 tabular-nums text-ink-muted">
                      {String(row.needs_verification)}
                    </td>
                    <td className="py-2 text-xs text-ink-faint">
                      {String(row.oldest_verification ?? '—')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        {runs.data && (
          <Card className="p-5">
            <h2 className="mb-3 font-display text-base text-ink dark:text-sand-100">
              Pipeline runs
            </h2>
            {(runs.data as Record<string, unknown>[]).length === 0 ? (
              <p className="text-sm text-ink-faint">
                No runs recorded. Execute{' '}
                <code className="rounded bg-black/5 px-1 dark:bg-white/10">make pipeline</code>.
              </p>
            ) : (
              <ul className="space-y-2">
                {(runs.data as Record<string, unknown>[]).slice(0, 12).map((run, i) => (
                  <li key={i} className="flex items-center justify-between gap-3 text-sm">
                    <div className="min-w-0">
                      <p className="truncate text-ink dark:text-sand-200">
                        {String(run.pipeline)}
                      </p>
                      <p className="text-xs text-ink-faint">
                        {String(run.layer)} · {String(run.rows_out)} rows out ·{' '}
                        {Number(run.duration_ms).toFixed(0)} ms
                        {run.finished_at ? ` · ${relativeTime(String(run.finished_at))}` : ''}
                      </p>
                    </div>
                    <Badge tone={run.status === 'success' ? 'teal' : 'clay'}>
                      {String(run.status)}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        )}

        {ragRuns.data && (
          <Card className="p-5">
            <h2 className="mb-1 font-display text-base text-ink dark:text-sand-100">
              RAG benchmark runs
            </h2>
            <p className="mb-3 text-xs text-ink-faint">{ragRuns.data.note}</p>
            {ragRuns.data.runs.length === 0 ? (
              <p className="text-sm text-ink-faint">No evaluation runs stored yet.</p>
            ) : (
              <ul className="space-y-3">
                {ragRuns.data.runs.slice(0, 6).map((run, i) => (
                  <li key={i} className="border-b border-[rgb(var(--line))]/60 pb-2.5 last:border-0">
                    <p className="truncate font-mono text-xs text-ink-muted dark:text-sand-400">
                      {String(run.run_id)}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      <Badge tone="neutral">{String(run.questions)} questions</Badge>
                      <Badge tone="teal">
                        faithfulness {Number(run.faithfulness).toFixed(2)}
                      </Badge>
                      <Badge tone="indigo">
                        citations {Number(run.citation_correctness).toFixed(2)}
                      </Badge>
                      <Badge tone="neutral">{Number(run.latency_ms).toFixed(0)} ms</Badge>
                      <Badge tone="saffron">{String(run.abstained)} abstained</Badge>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        )}
      </div>
    </PageShell>
  );
}

function Stat({
  label,
  value,
  tone = 'indigo',
}: {
  label: string;
  value: string;
  tone?: 'indigo' | 'teal' | 'saffron' | 'clay';
}) {
  const colours = {
    indigo: 'text-indigo-600 dark:text-indigo-300',
    teal: 'text-teal-500',
    saffron: 'text-saffron-500',
    clay: 'text-clay-500',
  };
  return (
    <Card className="p-5">
      <p className="text-xs text-ink-faint">{label}</p>
      <p className={`font-display text-2xl ${colours[tone]}`}>{value}</p>
    </Card>
  );
}
