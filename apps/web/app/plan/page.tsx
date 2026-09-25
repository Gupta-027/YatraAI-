'use client';

import { useMutation, useQuery } from '@tanstack/react-query';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useMemo, useState } from 'react';

import { PageShell } from '@/components/Shell';
import {
  Badge,
  Button,
  Card,
  ErrorState,
  Field,
  Input,
  Select,
  Textarea,
  Toggle,
} from '@/components/ui';
import { ApiRequestError, api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { INTEREST_KEYS, INTEREST_LABEL, destinationImage, hhmm } from '@/lib/utils';

interface FormState {
  cluster_slug: string;
  title: string;
  start_date: string;
  end_date: string;
  origin_label: string;
  traveller_count: number;
  budget_per_person_inr: number;
  pace: 'relaxed' | 'balanced' | 'packed';
  transport_mode: 'walk' | 'car' | 'taxi' | 'public' | 'mixed';
  accommodation_tier: 'budget' | 'midrange' | 'premium';
  day_start_min: number;
  day_end_min: number;
  has_children: boolean;
  has_seniors: boolean;
  accessibility_required: boolean;
  dietary: string;
  mobility_level: 'full' | 'limited_walking' | 'wheelchair';
  indoor_outdoor_pref: 'indoor' | 'outdoor' | 'mixed';
  interests: Record<string, number>;
  must_visit_slugs: string[];
  avoid_slugs: string[];
  notes: string;
}

function defaultDates() {
  const start = new Date();
  start.setDate(start.getDate() + 30);
  const end = new Date(start);
  end.setDate(end.getDate() + 2);
  return { start: start.toISOString().slice(0, 10), end: end.toISOString().slice(0, 10) };
}

// `useSearchParams` opts the subtree into client-side rendering, so Next.js
// requires an explicit Suspense boundary around it.
export default function PlanPage() {
  return (
    <Suspense
      fallback={
        <PageShell>
          <Card className="p-6">
            <p className="text-sm text-ink-muted">Loading the planner…</p>
          </Card>
        </PageShell>
      }
    >
      <PlanWizard />
    </Suspense>
  );
}

function PlanWizard() {
  const router = useRouter();
  const search = useSearchParams();
  const { user, loading: authLoading, signInAsDemo } = useAuth();
  const dates = useMemo(defaultDates, []);

  const [liked, setLiked] = useState<string[]>([]);
  const [form, setForm] = useState<FormState>({
    cluster_slug: search.get('destination') ?? '',
    title: '',
    start_date: search.get('start') ?? dates.start,
    end_date: search.get('end') ?? dates.end,
    origin_label: '',
    traveller_count: 3,
    budget_per_person_inr: 12000,
    pace: 'balanced',
    transport_mode: 'car',
    accommodation_tier: 'midrange',
    day_start_min: 540,
    day_end_min: 1140,
    has_children: false,
    has_seniors: false,
    accessibility_required: false,
    dietary: 'any',
    mobility_level: 'full',
    indoor_outdoor_pref: 'mixed',
    interests: Object.fromEntries(INTEREST_KEYS.map((k) => [k, 3])),
    must_visit_slugs: [],
    avoid_slugs: [],
    notes: '',
  });

  const destinations = useQuery({ queryKey: ['destinations'], queryFn: api.destinations });
  const attractions = useQuery({
    queryKey: ['attractions', form.cluster_slug],
    queryFn: () => api.attractions(form.cluster_slug),
    enabled: Boolean(form.cluster_slug),
  });

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const create = useMutation({
    mutationFn: async () => {
      const trip = await api.createTrip({
        cluster_slug: form.cluster_slug,
        title: form.title || `${selectedCluster?.name ?? 'Trip'} with friends`,
        start_date: form.start_date,
        end_date: form.end_date,
        origin_label: form.origin_label,
        traveller_count: form.traveller_count,
        budget_per_person_inr: form.budget_per_person_inr,
        budget_basis: 'per_person',
        pace: form.pace,
        transport_mode: form.transport_mode,
        accommodation_tier: form.accommodation_tier,
        day_start_min: form.day_start_min,
        day_end_min: form.day_end_min,
        has_children: form.has_children,
        has_seniors: form.has_seniors,
        accessibility_required: form.accessibility_required,
        must_visit_slugs: form.must_visit_slugs,
        avoid_slugs: form.avoid_slugs,
        notes: form.notes,
        owner_preferences: {
          // Chips are a simpler input than ten sliders: liked = 5, the rest = 2.
          interests: liked.length
            ? Object.fromEntries(INTEREST_KEYS.map((k) => [k, liked.includes(k) ? 5 : 2]))
            : form.interests,
          pace: form.pace,
          dietary: form.dietary,
          mobility_level: form.mobility_level,
          indoor_outdoor_pref: form.indoor_outdoor_pref,
          earliest_start_min: form.day_start_min,
          latest_end_min: form.day_end_min,
          must_visit_slugs: form.must_visit_slugs,
          avoid_slugs: form.avoid_slugs,
          is_senior: form.has_seniors,
        },
      });
      await api.generateItinerary(trip.id, {});
      return trip;
    },
    onSuccess: (trip) => router.push(`/trips/${trip.id}`),
  });

  const selectedCluster = destinations.data?.find((c) => c.slug === form.cluster_slug);
  const days =
    Math.round(
      (new Date(form.end_date).getTime() - new Date(form.start_date).getTime()) / 86_400_000
    ) + 1;

  const errors = validate(form, days);
  const ready = errors.length === 0;

  const failure = create.error as ApiRequestError | null;

  return (
    <PageShell>
      <div className="mb-8">
        <h1 className="font-display text-3xl text-ink dark:text-sand-100">Plan your trip</h1>
        <p className="mt-1 text-sm text-ink-muted dark:text-sand-400">
          Fill in the basics and we&apos;ll build your day-by-day itinerary.
        </p>
      </div>

      <div className="grid gap-8 lg:grid-cols-[1fr_22rem]">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (ready && user) create.mutate();
          }}
          className="space-y-6"
        >
          {/* ---------------- where & when ---------------- */}
          <Card className="space-y-5 p-6">
            <h2 className="font-display text-lg text-ink dark:text-sand-100">Where &amp; when</h2>
            <Field label="Destination" required htmlFor="cluster">
              <Select
                id="cluster"
                value={form.cluster_slug}
                onChange={(e) => update('cluster_slug', e.target.value)}
              >
                <option value="">Choose a destination…</option>
                {destinations.data?.map((c) => (
                  <option key={c.slug} value={c.slug}>
                    {c.name}, {c.state}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Start date" required htmlFor="start">
                <Input
                  id="start"
                  type="date"
                  value={form.start_date}
                  onChange={(e) => update('start_date', e.target.value)}
                />
              </Field>
              <Field label="End date" required htmlFor="end">
                <Input
                  id="end"
                  type="date"
                  value={form.end_date}
                  min={form.start_date}
                  onChange={(e) => update('end_date', e.target.value)}
                />
              </Field>
            </div>
          </Card>

          {/* ---------------- group ---------------- */}
          <Card className="space-y-5 p-6">
            <h2 className="font-display text-lg text-ink dark:text-sand-100">Your group</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Travellers" required htmlFor="count">
                <Input
                  id="count"
                  type="number"
                  min={1}
                  max={40}
                  value={form.traveller_count}
                  onChange={(e) => update('traveller_count', Number(e.target.value))}
                />
              </Field>
              <Field label="Budget per person (₹)" htmlFor="budget">
                <Input
                  id="budget"
                  type="number"
                  min={2000}
                  max={80000}
                  step={1000}
                  value={form.budget_per_person_inr}
                  onChange={(e) => update('budget_per_person_inr', Number(e.target.value))}
                />
              </Field>
            </div>
            <fieldset>
              <legend className="mb-2 text-sm font-semibold text-ink dark:text-sand-200">
                Pace
              </legend>
              <div className="grid grid-cols-3 gap-2">
                {(
                  [
                    ['relaxed', 'Relaxed', 'Up to 3 stops a day'],
                    ['balanced', 'Balanced', 'Up to 4 stops a day'],
                    ['packed', 'Packed', 'Up to 6 stops a day'],
                  ] as const
                ).map(([value, label, hint]) => (
                  <button
                    key={value}
                    type="button"
                    aria-pressed={form.pace === value}
                    onClick={() => update('pace', value)}
                    className={`rounded-xl border px-3 py-3 text-left transition-colors ${
                      form.pace === value
                        ? 'border-saffron-400 bg-saffron-50 dark:bg-saffron-400/10'
                        : 'border-[rgb(var(--line))] hover:border-saffron-300'
                    }`}
                  >
                    <span className="block text-sm font-semibold text-ink dark:text-sand-100">
                      {label}
                    </span>
                    <span className="block text-xs text-ink-faint">{hint}</span>
                  </button>
                ))}
              </div>
            </fieldset>
          </Card>

          {/* ---------------- interests ---------------- */}
          <Card className="p-6">
            <h2 className="font-display text-lg text-ink dark:text-sand-100">
              What do you enjoy?
            </h2>
            <p className="mb-4 text-sm text-ink-muted dark:text-sand-400">
              Pick as many as you like.
            </p>
            <div className="flex flex-wrap gap-2">
              {INTEREST_KEYS.map((key) => {
                const on = liked.includes(key);
                return (
                  <button
                    key={key}
                    type="button"
                    aria-pressed={on}
                    onClick={() =>
                      setLiked((l) => (on ? l.filter((k) => k !== key) : [...l, key]))
                    }
                    className={`rounded-full border px-4 py-2 text-sm font-medium transition-colors ${
                      on
                        ? 'border-saffron-400 bg-saffron-400 text-white'
                        : 'border-[rgb(var(--line))] text-ink-muted hover:border-saffron-300 dark:text-sand-300'
                    }`}
                  >
                    {INTEREST_LABEL[key]}
                  </button>
                );
              })}
            </div>
          </Card>

          {/* ---------------- advanced ---------------- */}
          <details className="group rounded-2xl border border-[rgb(var(--line))] bg-[rgb(var(--surface))]">
            <summary className="cursor-pointer list-none px-6 py-4 text-sm font-semibold text-ink dark:text-sand-100">
              More options
              <span className="ml-1 inline-block text-ink-faint transition-transform group-open:rotate-90">
                ›
              </span>
              <span className="ml-2 font-normal text-ink-faint">
                transport, timings, accessibility, must-see places
              </span>
            </summary>
            <div className="space-y-5 border-t border-[rgb(var(--line))] p-6">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Transport" htmlFor="transport">
                  <Select
                    id="transport"
                    value={form.transport_mode}
                    onChange={(e) =>
                      update('transport_mode', e.target.value as FormState['transport_mode'])
                    }
                  >
                    <option value="car">Private car</option>
                    <option value="taxi">Taxi / ride-hailing</option>
                    <option value="public">Public transport</option>
                    <option value="mixed">Mixed</option>
                    <option value="walk">Mostly walking</option>
                  </Select>
                </Field>
                <Field label="Stay" htmlFor="tier">
                  <Select
                    id="tier"
                    value={form.accommodation_tier}
                    onChange={(e) =>
                      update(
                        'accommodation_tier',
                        e.target.value as FormState['accommodation_tier']
                      )
                    }
                  >
                    <option value="budget">Budget</option>
                    <option value="midrange">Mid-range</option>
                    <option value="premium">Premium</option>
                  </Select>
                </Field>
                <Field label={`Day starts at ${hhmm(form.day_start_min)}`} htmlFor="dstart">
                  <input
                    id="dstart"
                    type="range"
                    min={300}
                    max={720}
                    step={30}
                    value={form.day_start_min}
                    onChange={(e) => update('day_start_min', Number(e.target.value))}
                    className="w-full accent-saffron-400"
                  />
                </Field>
                <Field label={`Day ends at ${hhmm(form.day_end_min)}`} htmlFor="dend">
                  <input
                    id="dend"
                    type="range"
                    min={900}
                    max={1380}
                    step={30}
                    value={form.day_end_min}
                    onChange={(e) => update('day_end_min', Number(e.target.value))}
                    className="w-full accent-saffron-400"
                  />
                </Field>
                <Field label="Dietary preference" htmlFor="diet">
                  <Select
                    id="diet"
                    value={form.dietary}
                    onChange={(e) => update('dietary', e.target.value)}
                  >
                    <option value="any">No preference</option>
                    <option value="vegetarian">Vegetarian</option>
                    <option value="vegan">Vegan</option>
                    <option value="jain">Jain</option>
                    <option value="halal">Halal</option>
                    <option value="no_beef">No beef</option>
                    <option value="no_pork">No pork</option>
                  </Select>
                </Field>
                <Field label="Mobility" htmlFor="mobility">
                  <Select
                    id="mobility"
                    value={form.mobility_level}
                    onChange={(e) =>
                      update('mobility_level', e.target.value as FormState['mobility_level'])
                    }
                  >
                    <option value="full">No limitations</option>
                    <option value="limited_walking">Limited walking</option>
                    <option value="wheelchair">Wheelchair user</option>
                  </Select>
                </Field>
              </div>
              <div className="space-y-3">
                <Toggle
                  label="Travelling with children"
                  checked={form.has_children}
                  onChange={(v) => update('has_children', v)}
                />
                <Toggle
                  label="Travelling with senior citizens"
                  checked={form.has_seniors}
                  onChange={(v) => update('has_seniors', v)}
                />
                <Toggle
                  label="Step-free access required"
                  checked={form.accessibility_required}
                  onChange={(v) => update('accessibility_required', v)}
                />
              </div>
              <PlacePicker
                title="Must visit"
                places={attractions.data ?? []}
                selected={form.must_visit_slugs}
                disabled={form.avoid_slugs}
                onToggle={(slug) =>
                  update(
                    'must_visit_slugs',
                    form.must_visit_slugs.includes(slug)
                      ? form.must_visit_slugs.filter((s) => s !== slug)
                      : [...form.must_visit_slugs, slug].slice(0, 15)
                  )
                }
              />
              <PlacePicker
                title="Skip these"
                tone="clay"
                places={attractions.data ?? []}
                selected={form.avoid_slugs}
                disabled={form.must_visit_slugs}
                onToggle={(slug) =>
                  update(
                    'avoid_slugs',
                    form.avoid_slugs.includes(slug)
                      ? form.avoid_slugs.filter((s) => s !== slug)
                      : [...form.avoid_slugs, slug].slice(0, 30)
                  )
                }
              />
              <Field label="Notes" htmlFor="notes">
                <Textarea
                  id="notes"
                  value={form.notes}
                  onChange={(e) => update('notes', e.target.value)}
                  maxLength={2000}
                  placeholder="Anything else we should know?"
                />
              </Field>
            </div>
          </details>

          {create.isError && (
            <ErrorState
              title={failure?.isInfeasible ? 'We could not fit a plan' : 'Something went wrong'}
              message={
                failure?.isInfeasible
                  ? 'Try a longer day, a slower pace, a bigger budget or fewer must-visit places.'
                  : (create.error as Error).message
              }
            />
          )}

          {/* ---------------- submit ---------------- */}
          <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
            {authLoading ? null : user ? (
              <Button type="submit" size="lg" loading={create.isPending} disabled={!ready}>
                {create.isPending ? 'Building your itinerary…' : 'Generate itinerary'}
              </Button>
            ) : (
              <>
                <Button
                  type="button"
                  size="lg"
                  disabled={!ready}
                  loading={create.isPending}
                  onClick={async () => {
                    await signInAsDemo();
                    create.mutate();
                  }}
                >
                  Generate as guest
                </Button>
                <Button
                  type="button"
                  size="lg"
                  variant="secondary"
                  onClick={() => router.push('/login?next=/plan')}
                >
                  Sign in to save
                </Button>
              </>
            )}
            {!ready && <p className="text-sm text-ink-faint">{errors[0]}</p>}
            {create.isPending && (
              <p className="text-sm text-ink-faint">This can take up to a minute.</p>
            )}
          </div>
        </form>

        {/* ---------------- preview ---------------- */}
        <aside className="hidden lg:block">
          <div className="sticky top-24 overflow-hidden rounded-2xl shadow-card">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={destinationImage(
                selectedCluster?.slug ?? 'delhi-agra',
                800,
                selectedCluster?.hero_image_url
              )}
              alt={selectedCluster?.name ?? ''}
              className="aspect-[4/5] w-full object-cover"
            />
            <div className="surface space-y-1 p-5">
              <p className="font-display text-lg text-ink dark:text-sand-100">
                {selectedCluster?.name ?? 'Your next trip'}
              </p>
              <p className="text-sm text-ink-muted dark:text-sand-400">
                {selectedCluster
                  ? `${days} ${days === 1 ? 'day' : 'days'} · ${form.traveller_count} travellers · ₹${form.budget_per_person_inr.toLocaleString('en-IN')} each`
                  : 'Choose a destination to get started.'}
              </p>
              {selectedCluster && (
                <p className="pt-2 text-sm leading-relaxed text-ink-muted dark:text-sand-400">
                  {selectedCluster.summary}
                </p>
              )}
            </div>
          </div>
        </aside>
      </div>
    </PageShell>
  );
}

function validate(form: FormState, days: number): string[] {
  const errors: string[] = [];
  if (!form.cluster_slug) errors.push('Choose a destination.');
  if (new Date(form.end_date) < new Date(form.start_date))
    errors.push('The end date cannot be before the start date.');
  if (days > 21) errors.push('Trips are limited to 21 days.');
  if (form.traveller_count < 1 || form.traveller_count > 40)
    errors.push('Travellers must be between 1 and 40.');
  if (form.day_end_min - form.day_start_min < 180)
    errors.push('Each day needs at least three hours between start and end.');
  return errors;
}

function PlacePicker({
  title,
  places,
  selected,
  disabled,
  onToggle,
  tone = 'indigo',
}: {
  title: string;
  places: { slug: string; name: string }[];
  selected: string[];
  disabled: string[];
  onToggle: (slug: string) => void;
  tone?: 'indigo' | 'clay';
}) {
  return (
    <div>
      <p className="mb-2 text-sm font-semibold text-ink dark:text-sand-200">
        {title}{' '}
        {selected.length > 0 && (
          <Badge tone={tone === 'clay' ? 'clay' : 'indigo'}>{selected.length}</Badge>
        )}
      </p>
      <div className="flex max-h-56 flex-wrap gap-2 overflow-y-auto rounded-xl border border-[rgb(var(--line))] p-3">
        {places.length === 0 && (
          <p className="text-sm text-ink-faint">Choose a destination first.</p>
        )}
        {places.map((p) => {
          const isSelected = selected.includes(p.slug);
          const isDisabled = disabled.includes(p.slug);
          return (
            <button
              key={p.slug}
              type="button"
              disabled={isDisabled}
              onClick={() => onToggle(p.slug)}
              aria-pressed={isSelected}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-40 ${
                isSelected
                  ? tone === 'clay'
                    ? 'border-clay-500 bg-clay-500 text-white'
                    : 'border-indigo-600 bg-indigo-600 text-white'
                  : 'border-[rgb(var(--line))] text-ink-muted hover:border-indigo-300 dark:text-sand-400'
              }`}
            >
              {p.name}
            </button>
          );
        })}
      </div>
    </div>
  );
}
