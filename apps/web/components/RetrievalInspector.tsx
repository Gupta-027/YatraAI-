'use client';

import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import type { RetrievedChunk } from '@/lib/types';
import { cn } from '@/lib/utils';

import { Badge, Spinner } from './ui';

const ARMS = [
  { key: 'dense_score', label: 'Dense', hint: 'embedding cosine', bar: 'bg-indigo-500' },
  { key: 'lexical_score', label: 'BM25', hint: 'term frequency', bar: 'bg-teal-400' },
  { key: 'rerank_score', label: 'Rerank', hint: 'feature model', bar: 'bg-saffron-400' },
] as const;

/**
 * Shows what retrieval actually did for the question just asked.
 *
 * Each arm is normalised against the top scorer *within that arm* — the three are
 * on different scales (cosine, BM25, a feature score) and plotting them on one
 * axis would imply a comparability that does not exist. The bars answer "which
 * chunk did this arm prefer", which is the question worth asking, rather than
 * "which arm scored higher", which is meaningless.
 */
function normalise(chunks: RetrievedChunk[], key: (typeof ARMS)[number]['key']): number[] {
  const values = chunks.map((c) => Math.max(0, c[key]));
  const max = Math.max(...values, 0);
  return max > 0 ? values.map((v) => v / max) : values.map(() => 0);
}

export function RetrievalInspector({
  question,
  clusterSlug,
  attractionSlug,
  enabled = true,
}: {
  question: string;
  clusterSlug?: string | null;
  attractionSlug?: string | null;
  enabled?: boolean;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['retrieve', question, clusterSlug, attractionSlug],
    queryFn: () =>
      api.retrieve({
        question,
        cluster_slug: clusterSlug ?? null,
        attraction_slug: attractionSlug ?? null,
        top_k: 5,
      }),
    enabled: enabled && question.trim().length > 3,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  if (!enabled || question.trim().length <= 3) return null;

  if (isLoading) {
    return (
      <p className="flex items-center gap-2 py-3 text-xs text-ink-faint">
        <Spinner className="h-3 w-3" /> Scoring candidates…
      </p>
    );
  }

  // A debug panel is never worth an error state in front of the user's answer.
  if (error || !data || data.length === 0) return null;

  const bars = Object.fromEntries(
    ARMS.map((arm) => [arm.key, normalise(data, arm.key)])
  ) as Record<(typeof ARMS)[number]['key'], number[]>;

  const rankedByFused = [...data]
    .map((c, i) => ({ i, fused: c.fused_score }))
    .sort((a, b) => b.fused - a.fused);
  const winner = rankedByFused[0]?.i;

  return (
    <div className="rounded-xl border border-[rgb(var(--line))] bg-[rgb(var(--surface-2))] p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-ink-muted dark:text-sand-300">
          Retrieval
        </h4>
        <p className="text-[11px] text-ink-faint">
          {data.length} chunks · hybrid dense + BM25 · fused by RRF · reranked
        </p>
      </div>

      <div className="mb-2 flex gap-3 text-[11px] text-ink-faint">
        {ARMS.map((arm) => (
          <span key={arm.key} className="flex items-center gap-1">
            <span className={cn('inline-block h-2 w-2 rounded-sm', arm.bar)} />
            {arm.label}
          </span>
        ))}
      </div>

      <ol className="space-y-2.5">
        {data.map((chunk, i) => (
          <li
            key={chunk.chunk_id}
            className={cn(
              'rounded-lg border px-3 py-2',
              i === winner
                ? 'border-indigo-300 bg-indigo-50/60 dark:border-indigo-400/40 dark:bg-indigo-500/10'
                : 'border-transparent'
            )}
          >
            <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
              <span className="font-mono text-[11px] text-ink-faint">{i + 1}</span>
              <span className="truncate text-xs font-medium text-ink dark:text-sand-200">
                {chunk.heading}
              </span>
              <Badge tone="neutral">{chunk.content_category}</Badge>
              {i === winner && <Badge tone="indigo">top</Badge>}
            </div>
            <div className="space-y-1">
              {ARMS.map((arm) => (
                <div key={arm.key} className="flex items-center gap-2">
                  <span className="w-12 shrink-0 text-[10px] text-ink-faint">{arm.label}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-sand-300 dark:bg-white/10">
                    <div
                      className={cn('h-full rounded-full', arm.bar)}
                      style={{ width: `${bars[arm.key][i] * 100}%` }}
                    />
                  </div>
                  <span className="w-11 shrink-0 text-right font-mono text-[10px] tabular-nums text-ink-faint">
                    {chunk[arm.key].toFixed(3)}
                  </span>
                </div>
              ))}
            </div>
          </li>
        ))}
      </ol>

      <p className="mt-3 text-[11px] leading-relaxed text-ink-faint">
        Bars are normalised within each arm — cosine, BM25 and the reranker are on different
        scales, so comparing them across arms would be meaningless. Reranking is worth{' '}
        <strong>+12.9 pp top-1</strong> on the benchmark.
      </p>
    </div>
  );
}
