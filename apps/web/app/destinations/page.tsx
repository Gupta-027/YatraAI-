'use client';

import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { DestinationCard } from '@/components/DestinationCard';
import { PageShell } from '@/components/Shell';
import { EmptyState, ErrorState, Input, Skeleton } from '@/components/ui';
import { api } from '@/lib/api';
import { monthNames } from '@/lib/utils';

export default function DestinationsPage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['destinations'],
    queryFn: api.destinations,
  });
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (data ?? []).filter(
      (c) => !q || c.name.toLowerCase().includes(q) || c.state.toLowerCase().includes(q)
    );
  }, [data, query]);

  return (
    <PageShell>
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl text-ink dark:text-sand-100">Destinations</h1>
          <p className="mt-1 text-sm text-ink-muted dark:text-sand-400">
            Pick a place to start planning.
          </p>
        </div>
        <label htmlFor="q" className="sr-only">
          Search destinations
        </label>
        <Input
          id="q"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by name or state"
          className="max-w-xs"
        />
      </div>

      {error && <ErrorState message={(error as Error).message} onRetry={() => void refetch()} />}

      {!isLoading && !error && filtered.length === 0 && (
        <EmptyState title="No destinations match" description="Try a broader search." />
      )}

      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {isLoading
          ? Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="aspect-[4/3] rounded-2xl" />
            ))
          : filtered.map((cluster) => (
              <DestinationCard
                key={cluster.slug}
                cluster={cluster}
                subtitle={`${cluster.state} · best in ${monthNames(cluster.best_months)}`}
              />
            ))}
      </div>
    </PageShell>
  );
}
