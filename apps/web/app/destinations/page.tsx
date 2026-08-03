'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useMemo, useState } from 'react';

import { PageShell } from '@/components/Shell';
import {
  Badge,
  Button,
  Card,
  CardSkeleton,
  EmptyState,
  ErrorState,
  Input,
  SectionHeading,
  Select,
} from '@/components/ui';
import { api } from '@/lib/api';
import { monthNames, titleise } from '@/lib/utils';

export default function DestinationsPage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['destinations'],
    queryFn: api.destinations,
  });

  const [query, setQuery] = useState('');
  const [region, setRegion] = useState('all');
  const [style, setStyle] = useState('all');

  const regions = useMemo(
    () => Array.from(new Set(data?.map((c) => c.region) ?? [])).sort(),
    [data]
  );
  const styles = useMemo(
    () => Array.from(new Set(data?.flatMap((c) => c.travel_style) ?? [])).sort(),
    [data]
  );

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toLowerCase();
    return data.filter((c) => {
      if (region !== 'all' && c.region !== region) return false;
      if (style !== 'all' && !c.travel_style.includes(style)) return false;
      if (!q) return true;
      return (
        c.name.toLowerCase().includes(q) ||
        c.state.toLowerCase().includes(q) ||
        c.summary.toLowerCase().includes(q)
      );
    });
  }, [data, query, region, style]);

  return (
    <PageShell>
      <SectionHeading
        level={1}
        title="Destinations"
        description="Ten circuits, 130 places, a cited source on every row. Hours and fees are recorded as unverified."
      />

      <Card className="mb-6 p-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <label htmlFor="q" className="mb-1 block text-xs font-semibold text-ink-muted">
              Search
            </label>
            <Input
              id="q"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Name, state or keyword"
            />
          </div>
          <div>
            <label htmlFor="region" className="mb-1 block text-xs font-semibold text-ink-muted">
              Region
            </label>
            <Select id="region" value={region} onChange={(e) => setRegion(e.target.value)}>
              <option value="all">All regions</option>
              {regions.map((r) => (
                <option key={r} value={r}>
                  {titleise(r)}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label htmlFor="style" className="mb-1 block text-xs font-semibold text-ink-muted">
              Travel style
            </label>
            <Select id="style" value={style} onChange={(e) => setStyle(e.target.value)}>
              <option value="all">Any style</option>
              {styles.map((s) => (
                <option key={s} value={s}>
                  {titleise(s)}
                </option>
              ))}
            </Select>
          </div>
        </div>
      </Card>

      {error && <ErrorState message={(error as Error).message} onRetry={() => void refetch()} />}

      {isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 9 }).map((_, i) => (
            <CardSkeleton key={i} lines={4} />
          ))}
        </div>
      )}

      {!isLoading && !error && filtered.length === 0 && (
        <EmptyState
          title="No destinations match"
          description="Try clearing the filters or searching for something broader."
          action={
            <Button
              variant="secondary"
              onClick={() => {
                setQuery('');
                setRegion('all');
                setStyle('all');
              }}
            >
              Clear filters
            </Button>
          }
        />
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.map((cluster) => (
          <Link key={cluster.slug} href={`/destinations/${cluster.slug}`} className="group">
            <Card className="flex h-full flex-col p-5 transition-shadow hover:shadow-lift">
              <div className="mb-2 flex items-start justify-between gap-2">
                <h2 className="font-display text-lg text-ink group-hover:text-indigo-600 dark:text-sand-100">
                  {cluster.name}
                </h2>
                <Badge tone="indigo">{cluster.attraction_count}</Badge>
              </div>
              <p className="mb-3 flex-1 text-sm text-ink-muted dark:text-sand-400">
                {cluster.summary}
              </p>
              <div className="mb-3 flex flex-wrap gap-1.5">
                {cluster.travel_style.slice(0, 3).map((s) => (
                  <Badge key={s} tone="neutral">
                    {titleise(s)}
                  </Badge>
                ))}
              </div>
              <dl className="grid grid-cols-2 gap-2 border-t border-[rgb(var(--line))] pt-3 text-xs">
                <div>
                  <dt className="text-ink-faint">State</dt>
                  <dd className="font-medium text-ink dark:text-sand-200">{cluster.state}</dd>
                </div>
                <div>
                  <dt className="text-ink-faint">Typical length</dt>
                  <dd className="font-medium text-ink dark:text-sand-200">
                    {cluster.recommended_days} days
                  </dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-ink-faint">Best months</dt>
                  <dd className="font-medium text-ink dark:text-sand-200">
                    {monthNames(cluster.best_months)}
                  </dd>
                </div>
              </dl>
            </Card>
          </Link>
        ))}
      </div>
    </PageShell>
  );
}
