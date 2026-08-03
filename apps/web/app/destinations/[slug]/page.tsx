'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useMemo, useState } from 'react';

import { MiniMap } from '@/components/Map';
import { PlaceDrawer } from '@/components/PlaceDrawer';
import { PageShell } from '@/components/Shell';
import {
  Badge,
  Button,
  Card,
  CardSkeleton,
  EmptyState,
  ErrorState,
  SectionHeading,
  Select,
  Toggle,
} from '@/components/ui';
import { api } from '@/lib/api';
import { ACCESS_LABEL, durationLabel, monthNames, titleise } from '@/lib/utils';

export default function DestinationPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;

  const [category, setCategory] = useState('all');
  const [accessibleOnly, setAccessibleOnly] = useState(false);
  const [indoorOnly, setIndoorOnly] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  const cluster = useQuery({
    queryKey: ['destination', slug],
    queryFn: () => api.destination(slug),
  });

  const attractions = useQuery({
    queryKey: ['attractions', slug, category, accessibleOnly, indoorOnly],
    queryFn: () =>
      api.attractions(slug, {
        category: category === 'all' ? undefined : category,
        accessible_only: accessibleOnly,
        indoor_only: indoorOnly,
      }),
  });

  const mapPoints = useMemo(
    () =>
      (attractions.data ?? []).map((a) => ({
        lat: a.lat,
        lon: a.lon,
        label: a.name,
        sublabel: `${durationLabel(a.typical_duration_min)} · ${titleise(a.indoor_outdoor)}`,
      })),
    [attractions.data]
  );

  if (cluster.error) {
    return (
      <PageShell>
        <ErrorState
          title="Destination not found"
          message={(cluster.error as Error).message}
          onRetry={() => void cluster.refetch()}
        />
      </PageShell>
    );
  }

  return (
    <PageShell>
      {cluster.isLoading ? (
        <CardSkeleton lines={5} />
      ) : (
        cluster.data && (
          <>
            <div className="mb-6">
              <Link
                href="/destinations"
                className="text-sm text-ink-muted hover:underline dark:text-sand-400"
              >
                ← All destinations
              </Link>
              <SectionHeading
                level={1}
                title={cluster.data.name}
                description={cluster.data.summary}
                action={
                  <Link href={`/plan?destination=${slug}`}>
                    <Button>Plan a trip here</Button>
                  </Link>
                }
              />
              <div className="flex flex-wrap gap-2">
                <Badge tone="indigo">{cluster.data.state}</Badge>
                <Badge tone="neutral">{titleise(cluster.data.region)} India</Badge>
                <Badge tone="teal">Best: {monthNames(cluster.data.best_months)}</Badge>
                <Badge tone="neutral">{cluster.data.recommended_days} days typical</Badge>
                {cluster.data.avoid_months.length > 0 && (
                  <Badge tone="saffron">Avoid: {monthNames(cluster.data.avoid_months)}</Badge>
                )}
              </div>
            </div>

            <div className="mb-6 grid gap-4 lg:grid-cols-3">
              <Card className="p-5 lg:col-span-2">
                <h2 className="mb-3 font-display text-lg text-ink dark:text-sand-100">
                  What this destination offers
                </h2>
                <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <Stat
                    label="Attractions"
                    value={String(cluster.data.accessibility_summary.total)}
                  />
                  <Stat
                    label="Step-free options"
                    value={String(cluster.data.accessibility_summary.wheelchair_friendly)}
                  />
                  <Stat
                    label="Indoor options"
                    value={String(cluster.data.accessibility_summary.indoor_options)}
                  />
                  <Stat
                    label="Senior-friendly"
                    value={String(cluster.data.accessibility_summary.senior_friendly)}
                  />
                </dl>
                {cluster.data.intercity_hub && (
                  <p className="mt-4 text-sm text-ink-muted dark:text-sand-400">
                    <strong className="text-ink dark:text-sand-200">Getting there: </strong>
                    {cluster.data.intercity_hub}
                  </p>
                )}
              </Card>
              <Card className="p-5">
                <h2 className="mb-3 font-display text-lg text-ink dark:text-sand-100">
                  Daily cost baseline
                </h2>
                <p className="mb-3 text-xs text-ink-faint">
                  Per person per day, used by the cost estimator. Ranges, not quotes.
                </p>
                <ul className="space-y-2 text-sm">
                  {Object.entries(cluster.data.daily_cost_baseline ?? {}).map(([tier, values]) => (
                    <li key={tier} className="flex justify-between">
                      <span className="capitalize text-ink dark:text-sand-200">{tier}</span>
                      <span className="text-ink-muted dark:text-sand-400">
                        ₹
                        {Object.values(values as Record<string, number>)
                          .reduce((a, b) => a + b, 0)
                          .toLocaleString('en-IN')}
                      </span>
                    </li>
                  ))}
                </ul>
              </Card>
            </div>

            <div className="mb-6">
              <MiniMap points={mapPoints} height={320} />
            </div>
          </>
        )
      )}

      <SectionHeading title="Attractions" description="Click any place for its full record." />

      <Card className="mb-5 p-4">
        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <label htmlFor="cat" className="mb-1 block text-xs font-semibold text-ink-muted">
              Category
            </label>
            <Select id="cat" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="all">All categories</option>
              {cluster.data?.categories.map((c) => (
                <option key={c} value={c}>
                  {titleise(c)}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex items-end">
            <Toggle
              label="Step-free access only"
              checked={accessibleOnly}
              onChange={setAccessibleOnly}
            />
          </div>
          <div className="flex items-end">
            <Toggle
              label="Indoor / all-weather only"
              checked={indoorOnly}
              onChange={setIndoorOnly}
            />
          </div>
        </div>
      </Card>

      {attractions.isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      )}

      {attractions.data?.length === 0 && (
        <EmptyState
          title="No attractions match these filters"
          description="Relax a filter to see more of this destination."
          action={
            <Button
              variant="secondary"
              onClick={() => {
                setCategory('all');
                setAccessibleOnly(false);
                setIndoorOnly(false);
              }}
            >
              Clear filters
            </Button>
          }
        />
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {attractions.data?.map((a) => (
          <Card key={a.slug} className="flex flex-col p-5">
            <div className="mb-2 flex items-start justify-between gap-2">
              <h3 className="font-display text-base text-ink dark:text-sand-100">{a.name}</h3>
              {a.needs_verification && (
                <Badge tone="saffron" title="Hours and fees need checking before you travel">
                  Verify
                </Badge>
              )}
            </div>
            <p className="mb-3 flex-1 text-sm text-ink-muted dark:text-sand-400">{a.summary}</p>
            <div className="mb-3 flex flex-wrap gap-1.5">
              <Badge tone="neutral">{durationLabel(a.typical_duration_min)}</Badge>
              <Badge tone="neutral">{titleise(a.indoor_outdoor)}</Badge>
              <Badge
                tone={
                  a.wheelchair_accessible === 'yes'
                    ? 'teal'
                    : a.wheelchair_accessible === 'no'
                      ? 'clay'
                      : 'neutral'
                }
              >
                {ACCESS_LABEL[a.wheelchair_accessible]}
              </Badge>
            </div>
            <Button variant="secondary" size="sm" onClick={() => setSelected(a.slug)}>
              Know this place
            </Button>
          </Card>
        ))}
      </div>

      <PlaceDrawer
        clusterSlug={slug}
        attractionSlug={selected}
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
      />
    </PageShell>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-faint">{label}</dt>
      <dd className="font-display text-2xl text-indigo-600 dark:text-indigo-300">{value}</dd>
    </div>
  );
}
