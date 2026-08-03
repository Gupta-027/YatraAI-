'use client';

import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';

import { api } from '@/lib/api';
import type { AskResponse, AttractionDetail } from '@/lib/types';
import {
  ACCESS_LABEL,
  CROWD_LABEL,
  durationLabel,
  monthNames,
  rupees,
  titleise,
} from '@/lib/utils';

import { MiniMap } from './Map';
import {
  Badge,
  Button,
  Callout,
  Card,
  Drawer,
  ErrorState,
  Input,
  Skeleton,
  Tab,
  TabList,
  TabPanel,
  Tabs,
} from './ui';

interface PlaceDrawerProps {
  clusterSlug: string;
  attractionSlug: string | null;
  open: boolean;
  onClose: () => void;
  /** Present when opened from an itinerary — enables the trip-aware actions. */
  tripId?: string;
  onReplace?: (slug: string) => void;
  onRemove?: (slug: string) => void;
  whySelected?: string;
}

export function PlaceDrawer({
  clusterSlug,
  attractionSlug,
  open,
  onClose,
  tripId,
  onReplace,
  onRemove,
  whySelected,
}: PlaceDrawerProps) {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['attraction', clusterSlug, attractionSlug],
    queryFn: () => api.attraction(clusterSlug, attractionSlug as string),
    enabled: open && Boolean(attractionSlug),
  });

  return (
    <Drawer open={open} onClose={onClose} title={data?.name ?? 'Place details'}>
      {isLoading && <PlaceSkeleton />}
      {error && (
        <ErrorState message={(error as Error).message} onRetry={() => void refetch()} />
      )}
      {data && (
        <PlaceContent
          place={data}
          clusterSlug={clusterSlug}
          tripId={tripId}
          onReplace={onReplace}
          onRemove={onRemove}
          whySelected={whySelected}
        />
      )}
    </Drawer>
  );
}

function PlaceSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-40 w-full" />
      <Skeleton className="h-6 w-2/3" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-1/2" />
    </div>
  );
}

function PlaceContent({
  place,
  clusterSlug,
  tripId,
  onReplace,
  onRemove,
  whySelected,
}: {
  place: AttractionDetail;
  clusterSlug: string;
  tripId?: string;
  onReplace?: (slug: string) => void;
  onRemove?: (slug: string) => void;
  whySelected?: string;
}) {
  const [saved, setSaved] = useState(false);
  const [expandHistory, setExpandHistory] = useState(false);

  const longHistory = place.history.length > 340;
  const historyText =
    longHistory && !expandHistory ? `${place.history.slice(0, 330).trimEnd()}…` : place.history;

  return (
    <div className="space-y-6">
      {/* ---- hero (placeholder-safe: no remote image is required) ---- */}
      <div className="relative h-40 overflow-hidden rounded-2xl bg-hero-warm">
        <div className="absolute inset-0 grid place-items-center">
          <span className="font-display text-5xl text-indigo-600/25 dark:text-indigo-200/25">
            {place.name
              .split(/\s+/)
              .slice(0, 2)
              .map((w) => w[0])
              .join('')}
          </span>
        </div>
        {place.image_attribution && (
          <p className="absolute bottom-1 right-2 text-[10px] text-ink-faint">
            {place.image_attribution}
          </p>
        )}
      </div>

      <div>
        <div className="mb-2 flex flex-wrap gap-1.5">
          {place.categories.slice(0, 5).map((c) => (
            <Badge key={c} tone="indigo">
              {titleise(c)}
            </Badge>
          ))}
        </div>
        <p className="text-sm text-ink-muted dark:text-sand-300">{place.summary}</p>
        <p className="mt-1 text-xs text-ink-faint">
          {place.locality ? `${place.locality}, ` : ''}
          {place.city}
        </p>
      </div>

      {/* ---- key facts ---- */}
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Fact label="Typical visit" value={durationLabel(place.typical_duration_min)} />
        <Fact
          label="Best time"
          value={
            place.best_time_of_day.length
              ? place.best_time_of_day.map((t) => titleise(t)).join(', ')
              : 'Any time'
          }
        />
        <Fact label="Crowds" value={CROWD_LABEL[place.typical_crowd_level] ?? '—'} />
        <Fact label="Setting" value={titleise(place.indoor_outdoor)} />
      </dl>

      {whySelected && (
        <Callout tone="teal" title="Why this place is in your itinerary">
          {whySelected}
        </Callout>
      )}

      {place.needs_verification && (
        <Callout tone="saffron" title="Verify before visiting">
          {place.verification_note ||
            'Opening hours and entry fees change without notice. Confirm with the official source below.'}
        </Callout>
      )}

      <Tabs defaultValue="story">
        <TabList label="Place information">
          <Tab value="story">Story</Tab>
          <Tab value="visit">Visiting</Tab>
          <Tab value="access">Access &amp; etiquette</Tab>
          <Tab value="ask">Ask</Tab>
          <Tab value="sources">Sources</Tab>
        </TabList>

        {/* ---------------- story ---------------- */}
        <TabPanel value="story">
          <div className="space-y-5">
            <section>
              <h3 className="mb-1.5 font-display text-base text-ink dark:text-sand-100">History</h3>
              <p className="whitespace-pre-line text-sm leading-relaxed text-ink-muted dark:text-sand-300">
                {historyText}
              </p>
              {longHistory && (
                <button
                  onClick={() => setExpandHistory((v) => !v)}
                  className="mt-1.5 text-sm font-semibold text-indigo-600 hover:underline dark:text-indigo-300"
                >
                  {expandHistory ? 'Show less' : 'Read more'}
                </button>
              )}
            </section>

            <section>
              <h3 className="mb-1.5 font-display text-base text-ink dark:text-sand-100">
                Why it matters
              </h3>
              <p className="text-sm leading-relaxed text-ink-muted dark:text-sand-300">
                {place.significance}
              </p>
            </section>

            {place.interesting_facts.length > 0 && (
              <section>
                <h3 className="mb-1.5 font-display text-base text-ink dark:text-sand-100">
                  Things you might not know
                </h3>
                <ul className="space-y-2">
                  {place.interesting_facts.map((fact) => (
                    <li key={fact} className="flex gap-2.5 text-sm text-ink-muted dark:text-sand-300">
                      <span aria-hidden="true" className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-saffron-400" />
                      {fact}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        </TabPanel>

        {/* ---------------- visiting ---------------- */}
        <TabPanel value="visit">
          <div className="space-y-5">
            <section>
              <h3 className="mb-2 font-display text-base text-ink dark:text-sand-100">
                Opening hours
              </h3>
              {place.schedules.length ? (
                <ul className="space-y-1.5">
                  {place.schedules.map((s, i) => (
                    <li key={i} className="flex items-center justify-between gap-3 text-sm">
                      <span className="text-ink dark:text-sand-200">{s.day_label}</span>
                      <span className="text-ink-muted dark:text-sand-400">
                        {s.is_closed ? 'Closed' : `${s.opens ?? '?'} – ${s.closes ?? '?'}`}
                        {s.note && <span className="ml-1 text-xs text-ink-faint">({s.note})</span>}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-ink-muted">Not recorded — verify before visiting.</p>
              )}
              <p className="mt-2 text-xs text-ink-faint">
                All hours are recorded as unverified in our dataset.
              </p>
            </section>

            <section>
              <h3 className="mb-2 font-display text-base text-ink dark:text-sand-100">Entry</h3>
              {place.costs.length ? (
                <ul className="space-y-1.5">
                  {place.costs.map((c, i) => (
                    <li key={i} className="flex items-center justify-between gap-3 text-sm">
                      <span className="text-ink dark:text-sand-200">{c.label}</span>
                      <span className="text-ink-muted dark:text-sand-400">
                        {c.is_free || c.amount_max === 0
                          ? 'Free'
                          : c.amount_min === c.amount_max
                            ? rupees(c.amount_max)
                            : `${rupees(c.amount_min)} – ${rupees(c.amount_max)}`}
                        {c.note && <span className="ml-1 text-xs text-ink-faint">({c.note})</span>}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-ink-muted">Not recorded — verify before visiting.</p>
              )}
            </section>

            <dl className="grid grid-cols-2 gap-3">
              <Fact label="Suitable months" value={monthNames(place.suitable_months)} />
              <Fact
                label="Plan between"
                value={`${durationLabel(place.min_duration_min)} – ${durationLabel(place.max_duration_min)}`}
              />
            </dl>

            {place.lat && (
              <section>
                <h3 className="mb-2 font-display text-base text-ink dark:text-sand-100">Location</h3>
                <MiniMap
                  points={[{ lat: place.lat, lon: place.lon, label: place.name }]}
                  height={200}
                />
              </section>
            )}
          </div>
        </TabPanel>

        {/* ---------------- access & etiquette ---------------- */}
        <TabPanel value="access">
          <div className="space-y-5">
            <section>
              <h3 className="mb-2 font-display text-base text-ink dark:text-sand-100">
                Accessibility
              </h3>
              <div className="mb-2 flex flex-wrap gap-2">
                <Badge
                  tone={
                    place.wheelchair_accessible === 'yes'
                      ? 'teal'
                      : place.wheelchair_accessible === 'no'
                        ? 'clay'
                        : 'saffron'
                  }
                >
                  {ACCESS_LABEL[place.wheelchair_accessible]}
                </Badge>
                <Badge tone="neutral">Seniors {place.senior_friendly}/5</Badge>
                <Badge tone="neutral">Children {place.child_friendly}/5</Badge>
                <Badge tone={place.physical_intensity >= 4 ? 'clay' : 'neutral'}>
                  Physical demand {place.physical_intensity}/5
                </Badge>
              </div>
              <p className="text-sm text-ink-muted dark:text-sand-300">
                {place.accessibility_notes}
              </p>
            </section>

            {place.dress_code && (
              <section>
                <h3 className="mb-1.5 font-display text-base text-ink dark:text-sand-100">
                  Dress code
                </h3>
                <p className="text-sm text-ink-muted dark:text-sand-300">{place.dress_code}</p>
              </section>
            )}

            {place.photography_policy && (
              <section>
                <h3 className="mb-1.5 font-display text-base text-ink dark:text-sand-100">
                  Photography
                </h3>
                <p className="text-sm text-ink-muted dark:text-sand-300">
                  {place.photography_policy}
                </p>
              </section>
            )}

            {place.local_customs.length > 0 && (
              <section>
                <h3 className="mb-1.5 font-display text-base text-ink dark:text-sand-100">
                  Local customs
                </h3>
                <ul className="space-y-2">
                  {place.local_customs.map((custom) => (
                    <li key={custom} className="flex gap-2.5 text-sm text-ink-muted dark:text-sand-300">
                      <span aria-hidden="true" className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-teal-400" />
                      {custom}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        </TabPanel>

        {/* ---------------- ask ---------------- */}
        <TabPanel value="ask">
          <AskPanel clusterSlug={clusterSlug} place={place} />
        </TabPanel>

        {/* ---------------- sources ---------------- */}
        <TabPanel value="sources">
          <div className="space-y-3">
            <p className="text-sm text-ink-muted dark:text-sand-400">
              Every claim on this page traces to one of these. Data confidence for this record is{' '}
              <strong>{place.data_confidence}</strong>
              {place.last_verified_at ? `, last reviewed ${place.last_verified_at}` : ''}.
            </p>
            <ul className="space-y-2">
              {place.sources.map((source) => (
                <li key={source.url}>
                  <Card className="p-3.5">
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="text-sm font-semibold text-indigo-600 hover:underline dark:text-indigo-300"
                    >
                      {source.title || source.url}
                    </a>
                    <p className="mt-1 break-all text-xs text-ink-faint">{source.url}</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <Badge tone="neutral">{titleise(source.source_type)}</Badge>
                      {source.covers_fields.map((field) => (
                        <Badge key={field} tone="neutral">
                          {titleise(field)}
                        </Badge>
                      ))}
                    </div>
                  </Card>
                </li>
              ))}
            </ul>
          </div>
        </TabPanel>
      </Tabs>

      {/* ---- nearby ---- */}
      {place.nearby.length > 0 && (
        <section>
          <h3 className="mb-2 font-display text-base text-ink dark:text-sand-100">
            Nearby itinerary locations
          </h3>
          <ul className="flex flex-wrap gap-2">
            {place.nearby.map((n) => (
              <li key={n.slug}>
                <Badge tone="neutral">
                  {n.name}
                  {n.distance_km !== null && (
                    <span className="text-ink-faint"> · {n.distance_km.toFixed(1)} km</span>
                  )}
                </Badge>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ---- actions ---- */}
      <div className="flex flex-wrap gap-2 border-t border-[rgb(var(--line))] pt-4">
        <Button
          variant={saved ? 'secondary' : 'primary'}
          size="sm"
          onClick={() => setSaved((v) => !v)}
        >
          {saved ? 'Saved' : 'Save place'}
        </Button>
        {tripId && onReplace && (
          <Button variant="secondary" size="sm" onClick={() => onReplace(place.slug)}>
            Replace this place
          </Button>
        )}
        {tripId && onRemove && (
          <Button variant="ghost" size="sm" onClick={() => onRemove(place.slug)}>
            Remove from itinerary
          </Button>
        )}
      </div>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[rgb(var(--line))] bg-[rgb(var(--surface-2))] px-3 py-2">
      <dt className="text-[11px] font-medium uppercase tracking-wide text-ink-faint">{label}</dt>
      <dd className="mt-0.5 text-sm font-semibold text-ink dark:text-sand-200">{value}</dd>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Ask-about-this-place assistant                                              */
/* -------------------------------------------------------------------------- */
export function AskPanel({
  clusterSlug,
  place,
  onAsked,
}: {
  clusterSlug: string;
  place?: AttractionDetail | null;
  /** Fires with each submitted question so a parent can show the retrieval for it. */
  onAsked?: (question: string) => void;
}) {
  const [question, setQuestion] = useState('');
  const [history, setHistory] = useState<AskResponse[]>([]);
  const endRef = useRef<HTMLDivElement>(null);

  const { data: suggestions } = useQuery({
    queryKey: ['suggested-questions', place?.name],
    queryFn: () => api.suggestedQuestions(place?.name),
  });

  const ask = useMutation({
    mutationFn: (q: string) =>
      api.ask({
        question: q,
        cluster_slug: clusterSlug,
        attraction_slug: place?.slug ?? null,
      }),
    onSuccess: (response) => setHistory((h) => [...h, response]),
  });

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [history.length]);

  function submit(q: string) {
    const trimmed = q.trim();
    if (trimmed.length < 3) return;
    setQuestion('');
    onAsked?.(trimmed);
    ask.mutate(trimmed);
  }

  return (
    <div className="space-y-4">
      <Callout tone="indigo">
        Answers come only from cited sources in our knowledge base. If we don&apos;t hold the answer,
        the assistant says so rather than guessing.
      </Callout>

      {history.length === 0 && suggestions && (
        <div className="flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              onClick={() => submit(s)}
              className="rounded-full border border-[rgb(var(--line))] px-3 py-1.5 text-xs font-medium text-ink-muted transition-colors hover:border-indigo-300 hover:text-indigo-600 dark:text-sand-400 dark:hover:text-indigo-200"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <div className="space-y-4">
        {history.map((entry, i) => (
          <div key={i} className="space-y-2">
            <p className="text-sm font-semibold text-ink dark:text-sand-100">{entry.question}</p>
            <Card
              className={
                entry.abstained ? 'border-saffron-200 bg-saffron-50/60 p-4' : 'p-4'
              }
            >
              <p className="whitespace-pre-line text-sm leading-relaxed text-ink-muted dark:text-sand-300">
                {entry.answer}
              </p>

              {entry.citations.length > 0 && (
                <div className="mt-3 border-t border-[rgb(var(--line))] pt-3">
                  <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
                    Sources
                  </p>
                  <ol className="space-y-1">
                    {entry.citations.map((c) => (
                      <li key={c.index} className="text-xs text-ink-muted dark:text-sand-400">
                        <span className="font-semibold">[{c.index}]</span> {c.heading} ·{' '}
                        <a
                          href={c.source_url}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="text-indigo-600 hover:underline dark:text-indigo-300"
                        >
                          source
                        </a>
                        {c.last_verified && (
                          <span className="text-ink-faint"> · reviewed {c.last_verified}</span>
                        )}
                      </li>
                    ))}
                  </ol>
                </div>
              )}

              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                {entry.abstained && <Badge tone="saffron">No verified answer</Badge>}
                {!entry.abstained && (
                  <Badge tone="teal">Confidence {(entry.confidence * 100).toFixed(0)}%</Badge>
                )}
                <Badge tone="neutral">{entry.latency_ms.toFixed(0)} ms</Badge>
                <Badge tone="neutral">{entry.provider}</Badge>
              </div>

              {entry.warnings.length > 0 && (
                <ul className="mt-2 space-y-0.5">
                  {entry.warnings.map((w) => (
                    <li key={w} className="text-[11px] text-saffron-600 dark:text-saffron-300">
                      {w}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        ))}
        {ask.isPending && <Skeleton className="h-24 w-full" />}
        {ask.isError && <ErrorState message={(ask.error as Error).message} />}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(question);
        }}
        className="flex gap-2"
      >
        <Input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={
            place ? `Ask about ${place.name}…` : 'Ask about any place in this destination…'
          }
          aria-label="Your question"
          maxLength={500}
        />
        <Button type="submit" loading={ask.isPending} disabled={question.trim().length < 3}>
          Ask
        </Button>
      </form>
    </div>
  );
}
