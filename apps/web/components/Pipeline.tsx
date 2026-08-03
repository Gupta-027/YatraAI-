'use client';

import { cn } from '@/lib/utils';

import { Badge, Card } from './ui';

/* -------------------------------------------------------------------------- */
/* Pipeline strip                                                             */
/* -------------------------------------------------------------------------- */

/**
 * The product thesis as a diagram rather than a paragraph.
 *
 * Four solid nodes are deterministic; the fifth is dashed because it is the only
 * stage a language model touches. That single visual difference carries the whole
 * argument, so the copy underneath can be two or three words per node instead of a
 * sentence.
 */
const STAGES = [
  { key: 'data', label: 'Data', detail: '130 places · 142 sources', kind: 'det' },
  { key: 'rank', label: 'Rank', detail: '9 scored features', kind: 'det' },
  { key: 'solve', label: 'Solve', detail: 'CP-SAT · 48 ms', kind: 'det' },
  { key: 'check', label: 'Validate', detail: '15 constraints', kind: 'det' },
  { key: 'write', label: 'Narrate', detail: 'LLM · optional', kind: 'gen' },
] as const;

export function PipelineStrip() {
  return (
    <div>
      <ol className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {STAGES.map((stage, i) => (
          <li key={stage.key} className="relative">
            <div
              className={cn(
                'h-full rounded-xl border px-3 py-3',
                stage.kind === 'det'
                  ? 'border-[rgb(var(--line))] bg-[rgb(var(--surface))]'
                  : 'border-dashed border-saffron-400 bg-saffron-50 dark:bg-saffron-400/10'
              )}
            >
              <div className="flex items-center gap-1.5">
                <span
                  className={cn(
                    'grid h-5 w-5 place-items-center rounded-md text-[10px] font-bold tabular-nums',
                    stage.kind === 'det'
                      ? 'bg-indigo-600 text-white'
                      : 'bg-saffron-400 text-ink'
                  )}
                >
                  {i + 1}
                </span>
                <span className="text-sm font-semibold text-ink dark:text-sand-100">
                  {stage.label}
                </span>
              </div>
              <p className="mt-1.5 font-mono text-[11px] leading-tight text-ink-muted dark:text-sand-400">
                {stage.detail}
              </p>
            </div>
          </li>
        ))}
      </ol>
      <p className="mt-3 text-xs text-ink-muted dark:text-sand-400">
        <span className="inline-block h-2 w-2 rounded-sm border border-dashed border-saffron-400 align-middle" />{' '}
        Dashed = the only stage a language model touches. It narrates a plan it did not choose.
      </p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Solver trace                                                               */
/* -------------------------------------------------------------------------- */

interface DayStat {
  day: number;
  status: string;
  solve_ms: number;
  objective: number;
  candidates: number;
  selected: number;
  relaxations: string[];
}

/**
 * Narrow, defensive parse of `itinerary.solver_stats`.
 *
 * The field is typed `Record<string, unknown>` because it is solver output, not a
 * contract. Anything unparseable renders nothing rather than throwing — a
 * diagnostics panel must never be able to take down the itinerary it describes.
 */
function parseDays(stats: Record<string, unknown> | undefined): DayStat[] {
  const raw = stats?.days;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((entry) => {
    if (typeof entry !== 'object' || entry === null) return [];
    const d = entry as Record<string, unknown>;
    if (typeof d.day !== 'number') return [];
    return [
      {
        day: d.day,
        status: typeof d.status === 'string' ? d.status : 'unknown',
        solve_ms: typeof d.solve_ms === 'number' ? d.solve_ms : 0,
        objective: typeof d.objective === 'number' ? d.objective : 0,
        candidates: typeof d.candidates === 'number' ? d.candidates : 0,
        selected: typeof d.selected === 'number' ? d.selected : 0,
        relaxations: Array.isArray(d.relaxations)
          ? d.relaxations.filter((r): r is string => typeof r === 'string')
          : [],
      },
    ];
  });
}

function statusTone(status: string): 'teal' | 'saffron' | 'clay' {
  if (status === 'OPTIMAL') return 'teal';
  if (status === 'INFEASIBLE') return 'clay';
  return 'saffron';
}

/**
 * What the optimiser actually did, per day.
 *
 * Every number here is read back from the solve that produced the itinerary on
 * screen — CP-SAT's own status, wall-clock, objective value, and how many
 * candidates it had to choose from. Nothing is illustrative.
 */
export function SolverTrace({
  stats,
  generator,
  checksRun,
}: {
  stats: Record<string, unknown> | undefined;
  generator: string;
  checksRun: number;
}) {
  const days = parseDays(stats);
  if (!days.length) return null;

  const totalMs = days.reduce((sum, d) => sum + d.solve_ms, 0);
  const totalCandidates = days.reduce((sum, d) => sum + d.candidates, 0);
  const totalSelected = days.reduce((sum, d) => sum + d.selected, 0);
  const relaxed = days.filter((d) => d.relaxations.length > 0);
  const fingerprint = typeof stats?.fingerprint === 'string' ? stats.fingerprint : null;

  return (
    <Card className="overflow-hidden">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-[rgb(var(--line))] bg-[rgb(var(--surface-2))] px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-ink dark:text-sand-100">Solver trace</h3>
          <p className="text-xs text-ink-faint">Read back from the solve that produced this plan</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone="indigo">{generator === 'ortools' ? 'OR-Tools CP-SAT' : generator}</Badge>
          <Badge tone="neutral">{totalMs.toFixed(0)} ms</Badge>
          <Badge tone="neutral">{checksRun} checks</Badge>
        </div>
      </header>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-ink-faint">
            <tr className="border-b border-[rgb(var(--line))]">
              <th scope="col" className="px-4 py-2 font-medium">Day</th>
              <th scope="col" className="px-4 py-2 font-medium">Status</th>
              <th scope="col" className="px-4 py-2 text-right font-medium">Chosen</th>
              <th scope="col" className="px-4 py-2 text-right font-medium">Objective</th>
              <th scope="col" className="px-4 py-2 text-right font-medium">Solve</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[rgb(var(--line))]">
            {days.map((d) => (
              <tr key={d.day}>
                <td className="px-4 py-2 font-medium text-ink dark:text-sand-200">{d.day + 1}</td>
                <td className="px-4 py-2">
                  <Badge tone={statusTone(d.status)}>{d.status}</Badge>
                </td>
                <td className="px-4 py-2 text-right font-mono tabular-nums text-ink-muted dark:text-sand-400">
                  {d.selected}
                  <span className="text-ink-faint"> / {d.candidates}</span>
                </td>
                <td className="px-4 py-2 text-right font-mono tabular-nums text-ink-muted dark:text-sand-400">
                  {d.objective.toLocaleString()}
                </td>
                <td className="px-4 py-2 text-right font-mono tabular-nums text-ink-muted dark:text-sand-400">
                  {d.solve_ms.toFixed(0)} ms
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="space-y-1.5 border-t border-[rgb(var(--line))] px-4 py-3 text-xs text-ink-muted dark:text-sand-400">
        <p>
          Selected <strong className="text-ink dark:text-sand-200">{totalSelected}</strong> of{' '}
          {totalCandidates} eligible candidates. Objective maximises score minus a weighted travel
          penalty.
        </p>
        {relaxed.length > 0 && (
          <p className="text-saffron-600 dark:text-saffron-300">
            Constraints relaxed on {relaxed.length === 1 ? 'day' : 'days'}{' '}
            {relaxed.map((d) => d.day + 1).join(', ')}:{' '}
            {[...new Set(relaxed.flatMap((d) => d.relaxations))].join(', ')}. The plan is feasible
            but the original limits could not all be met.
          </p>
        )}
        {fingerprint && (
          <p className="font-mono text-[11px] text-ink-faint">
            input fingerprint {fingerprint.slice(0, 16)} · same inputs always produce this plan
          </p>
        )}
      </div>
    </Card>
  );
}
