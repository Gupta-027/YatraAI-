'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useMemo, useState } from 'react';

import { DayTimeline, ItinerarySummary } from '@/components/Itinerary';
import { PlaceDrawer } from '@/components/PlaceDrawer';
import { PageShell } from '@/components/Shell';
import {
  Button,
  Callout,
  Card,
  CardSkeleton,
  EmptyState,
  ErrorState,
  Skeleton,
} from '@/components/ui';
import { ApiRequestError, api } from '@/lib/api';
import { useRequireAuth } from '@/lib/auth';
import { destinationImage, durationLabel, formatDate, percent, rupees, titleise } from '@/lib/utils';

const QUICK_ACTIONS = [
  { action: 'make_day_relaxed', label: 'Make it relaxed', hint: 'Fewer stops, longer breaks' },
  { action: 'reduce_travel', label: 'Reduce travel', hint: 'Tighter geographic clustering' },
  { action: 'reduce_cost', label: 'Reduce cost', hint: 'Cut the budget by 20%' },
  { action: 'weather_replan', label: 'Replan for weather', hint: 'Refetch the forecast and re-score' },
];

const THEMES = ['historical', 'spiritual', 'nature', 'food', 'museums', 'adventure'];

export default function TripPage() {
  const { id } = useParams<{ id: string }>();
  const { loading: authLoading } = useRequireAuth();
  const queryClient = useQueryClient();

  const [place, setPlace] = useState<{ slug: string; why: string } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const trip = useQuery({ queryKey: ['trip', id], queryFn: () => api.trip(id), enabled: !!id });
  const itinerary = useQuery({
    queryKey: ['itinerary', id],
    queryFn: () => api.itinerary(id),
    enabled: !!id,
    retry: false,
  });

  const generate = useMutation<import('@/lib/types').Itinerary, Error, boolean>({
    mutationFn: (force: boolean) => api.generateItinerary(id, { force_regenerate: force }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['itinerary', id] });
      void queryClient.invalidateQueries({ queryKey: ['trip', id] });
      setNotice(null);
    },
  });

  const modify = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.modifyItinerary(id, body),
    onSuccess: (response) => {
      setNotice(response.message);
      void queryClient.invalidateQueries({ queryKey: ['itinerary', id] });
      void queryClient.invalidateQueries({ queryKey: ['proposals', id] });
    },
  });

  if (authLoading || trip.isLoading) {
    return (
      <PageShell>
        <Skeleton className="mb-6 h-10 w-1/2" />
        <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
          <div className="space-y-4">
            <CardSkeleton lines={6} />
            <CardSkeleton lines={6} />
          </div>
          <CardSkeleton lines={8} />
        </div>
      </PageShell>
    );
  }

  if (trip.error) {
    return (
      <PageShell>
        <ErrorState message={(trip.error as Error).message} onRetry={() => void trip.refetch()} />
      </PageShell>
    );
  }

  const t = trip.data!;
  const noItinerary =
    itinerary.error instanceof ApiRequestError && itinerary.error.code === 'no_itinerary';

  return (
    <PageShell>
      <div className="relative -mx-4 -mt-8 mb-8 overflow-hidden sm:-mx-6 sm:rounded-b-3xl">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={destinationImage(t.cluster_slug, 1600)}
          alt=""
          className="absolute inset-0 h-full w-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/30 to-black/10" />
        <div className="relative px-4 pb-8 pt-28 sm:px-8">
          <Link href="/trips" className="text-sm text-white/80 hover:underline">
            ← My trips
          </Link>
          <h1 className="mt-2 font-display text-3xl text-white sm:text-4xl">{t.title}</h1>
          <p className="mt-1 text-sm text-white/85">
            {t.cluster_name} · {formatDate(t.start_date)} – {formatDate(t.end_date)} ·{' '}
            {t.duration_days} days · {t.traveller_count} travellers
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Link href={`/trips/${id}/group`}>
              <Button size="sm" variant="secondary">
                Invite group
              </Button>
            </Link>
            <Link href={`/trips/${id}/map`}>
              <Button size="sm" variant="secondary">
                Map
              </Button>
            </Link>
            <Button size="sm" variant="secondary" onClick={() => window.print()}>
              Print / PDF
            </Button>
          </div>
        </div>
      </div>

      {notice && (
        <div className="mb-4">
          <Callout tone="teal">{notice}</Callout>
        </div>
      )}

      {noItinerary && (
        <EmptyState
          title="No itinerary yet"
          description="Runs the full pipeline: filter, score, cluster, solve, validate."
          action={
            <Button loading={generate.isPending} onClick={() => generate.mutate(false)}>
              Generate itinerary
            </Button>
          }
        />
      )}

      {generate.isError && (
        <ErrorState
          title={
            (generate.error as ApiRequestError)?.isInfeasible
              ? 'No feasible itinerary'
              : 'Generation failed'
          }
          message={
            (generate.error as ApiRequestError)?.isInfeasible
              ? 'Your constraints leave no valid schedule. Widen the day window, relax the pace, or remove a must-visit place.'
              : (generate.error as Error).message
          }
        />
      )}

      {itinerary.isLoading && !noItinerary && (
        <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
          <div className="space-y-4">
            <CardSkeleton lines={6} />
            <CardSkeleton lines={6} />
          </div>
          <CardSkeleton lines={8} />
        </div>
      )}

      {itinerary.data && (
        <>
          {/* ---- summary ---- */}
          <Card className="mb-5 p-5">
            <div className="mb-2 flex items-center justify-between gap-3">
              <h2 className="font-display text-lg text-ink dark:text-sand-100">Your plan</h2>
              <Button
                variant="ghost"
                size="sm"
                loading={generate.isPending}
                onClick={() => generate.mutate(true)}
              >
                Regenerate
              </Button>
            </div>
            <p className="whitespace-pre-line text-sm leading-relaxed text-ink-muted dark:text-sand-300">
              {itinerary.data.summary_text}
            </p>
          </Card>

          {/* ---- modification actions ---- */}
          <Card className="mb-5 p-5">
            <h2 className="mb-3 font-display text-base text-ink dark:text-sand-100">
              Not quite right?
            </h2>
            <div className="flex flex-wrap gap-2">
              {QUICK_ACTIONS.map((qa) => (
                <Button
                  key={qa.action}
                  variant="secondary"
                  size="sm"
                  title={qa.hint}
                  loading={modify.isPending && modify.variables?.action === qa.action}
                  onClick={() =>
                    modify.mutate(
                      qa.action === 'reduce_cost'
                        ? { action: qa.action, budget_reduction_pct: 20 }
                        : { action: qa.action }
                    )
                  }
                >
                  {qa.label}
                </Button>
              ))}
            </div>

            {/* Themes and per-day regeneration are real actions but rarely the first
                thing anyone wants, and as flat button rows they doubled the height of
                this card. Behind a disclosure they cost nothing until asked for. */}
            <details className="group mt-3">
              <summary className="cursor-pointer list-none text-xs font-semibold text-indigo-600 hover:underline dark:text-indigo-300">
                More options
                <span className="ml-1 inline-block transition-transform group-open:rotate-90">
                  ›
                </span>
              </summary>
              <div className="mt-3 space-y-3">
                <div>
                  <p className="mb-1.5 text-xs text-ink-muted dark:text-sand-400">Add a theme</p>
                  <div className="flex flex-wrap gap-2">
                    {THEMES.map((theme) => (
                      <Button
                        key={theme}
                        variant="ghost"
                        size="sm"
                        loading={modify.isPending && modify.variables?.theme === theme}
                        onClick={() => modify.mutate({ action: 'add_theme', theme })}
                      >
                        + {titleise(theme)}
                      </Button>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="mb-1.5 text-xs text-ink-muted dark:text-sand-400">
                    Regenerate one day
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {itinerary.data.days.map((day) => (
                      <Button
                        key={day.id}
                        variant="ghost"
                        size="sm"
                        loading={modify.isPending && modify.variables?.day_index === day.day_index}
                        onClick={() =>
                          modify.mutate({ action: 'regenerate_day', day_index: day.day_index })
                        }
                      >
                        Day {day.day_index + 1}
                      </Button>
                    ))}
                  </div>
                </div>
              </div>
            </details>
            {modify.isError && (
              <div className="mt-3">
                <ErrorState
                  title={
                    (modify.error as ApiRequestError)?.isInfeasible
                      ? 'That change is not feasible'
                      : 'Change failed'
                  }
                  message={
                    (modify.error as ApiRequestError)?.isInfeasible
                      ? 'That adjustment leaves no valid schedule. Try a smaller change.'
                      : (modify.error as Error).message
                  }
                />
              </div>
            )}
            {modify.data?.requires_group_approval && (
              <div className="mt-3">
                <Callout tone="saffron" title="Waiting for group approval">
                  {modify.data.message} Changes: {modify.data.diff.summary}.{' '}
                  <Link href={`/trips/${id}/group`} className="font-semibold underline">
                    Open the group room to vote
                  </Link>
                  .
                </Callout>
              </div>
            )}
          </Card>

          {/* ---- timeline + summary ---- */}
          <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
            <div className="space-y-5">
              {itinerary.data.days.map((day) => (
                <DayTimeline
                  key={day.id}
                  day={day}
                  onOpenPlace={(slug, why) => setPlace({ slug, why })}
                  onRemove={(slug) =>
                    modify.mutate({ action: 'remove_activity', attraction_slug: slug })
                  }
                  onReplace={(slug) =>
                    modify.mutate({ action: 'replace_activity', attraction_slug: slug })
                  }
                />
              ))}
            </div>
            <aside className="space-y-4 lg:sticky lg:top-24 lg:self-start">
              <ItinerarySummary itinerary={itinerary.data} />
              <Card className="p-5">
                <h3 className="mb-2 font-display text-base text-ink dark:text-sand-100">
                  Share &amp; export
                </h3>
                <div className="space-y-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    full
                    onClick={() => {
                      void navigator.clipboard.writeText(t.invite_code);
                      setNotice(`Invite code ${t.invite_code} copied.`);
                    }}
                  >
                    Copy invite code
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    full
                    onClick={() => downloadItinerary(itinerary.data!, t.title)}
                  >
                    Download as JSON
                  </Button>
                </div>
              </Card>
            </aside>
          </div>
        </>
      )}

      <PlaceDrawer
        clusterSlug={t.cluster_slug}
        attractionSlug={place?.slug ?? null}
        open={Boolean(place)}
        onClose={() => setPlace(null)}
        tripId={id}
        whySelected={place?.why}
        onRemove={(slug) => {
          modify.mutate({ action: 'remove_activity', attraction_slug: slug });
          setPlace(null);
        }}
        onReplace={(slug) => {
          modify.mutate({ action: 'replace_activity', attraction_slug: slug });
          setPlace(null);
        }}
      />
    </PageShell>
  );
}

function downloadItinerary(itinerary: import('@/lib/types').Itinerary, title: string) {
  const payload = {
    title,
    generated_at: itinerary.created_at,
    validated: itinerary.is_valid,
    checks_run: itinerary.validation.checks_run,
    totals: {
      stops: itinerary.activity_count,
      travel_km: itinerary.total_travel_km,
      travel_time: durationLabel(itinerary.total_travel_min),
      cost_per_person: `${rupees(itinerary.cost.per_person_low_inr)} – ${rupees(itinerary.cost.per_person_high_inr)}`,
      fairness: percent(itinerary.fairness_score),
    },
    days: itinerary.days.map((d) => ({
      date: d.calendar_date,
      travel_km: d.travel_km,
      weather: d.weather,
      advisories: d.weather_advisories,
      activities: d.activities.map((a) => ({
        time: `${a.start_time}–${a.end_time}`,
        title: a.title,
        why: a.why_selected,
        warnings: a.warnings,
      })),
    })),
    disclaimer:
      'Opening hours and entry fees in this dataset are recorded as unverified. Confirm with the official source before travelling.',
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${title.replace(/\W+/g, '-').toLowerCase()}-itinerary.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}
