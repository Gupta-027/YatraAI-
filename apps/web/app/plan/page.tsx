'use client';

import { useMutation, useQuery } from '@tanstack/react-query';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useMemo, useState } from 'react';

import { PageShell } from '@/components/Shell';
import {
  Badge,
  Button,
  Callout,
  Card,
  ErrorState,
  Field,
  Input,
  SectionHeading,
  Select,
  Slider,
  Textarea,
  Toggle,
} from '@/components/ui';
import { ApiRequestError, api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { INTEREST_KEYS, INTEREST_LABEL, hhmm, titleise } from '@/lib/utils';

const STEPS = [
  { id: 'where', title: 'Where & when' },
  { id: 'who', title: 'Who is travelling' },
  { id: 'style', title: 'Style & budget' },
  { id: 'interests', title: 'Your interests' },
  { id: 'musts', title: 'Must-visit & avoid' },
  { id: 'review', title: 'Review' },
];

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

  const [step, setStep] = useState(0);
  const [form, setForm] = useState<FormState>({
    cluster_slug: search.get('destination') ?? '',
    title: '',
    start_date: dates.start,
    end_date: dates.end,
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
          interests: form.interests,
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

  const stepErrors = validateStep(step, form, days);
  const canContinue = stepErrors.length === 0;

  if (!authLoading && !user) {
    return (
      <PageShell>
        <SectionHeading
          level={1}
          title="Plan a group trip"
          description="You'll need an account so the trip can be saved and shared with your group."
        />
        <Card className="mx-auto max-w-md p-7 text-center">
          <p className="mb-5 text-sm text-ink-muted dark:text-sand-400">
            Sign in to continue, or open the demo account which already has a three-member trip with
            deliberately conflicting preferences.
          </p>
          <div className="flex flex-col gap-2">
            <Button onClick={() => router.push('/login?next=/plan')}>Sign in</Button>
            <Button variant="secondary" onClick={() => void signInAsDemo()}>
              Use the demo account
            </Button>
          </div>
        </Card>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <SectionHeading
        level={1}
        title="Plan a group trip"
        description="Every input becomes a hard constraint or a scoring weight."
      />

      {/* ---- stepper ---- */}
      <ol className="mb-6 flex flex-wrap gap-2" aria-label="Progress">
        {STEPS.map((s, i) => (
          <li key={s.id}>
            <button
              onClick={() => i <= step && setStep(i)}
              disabled={i > step}
              aria-current={i === step ? 'step' : undefined}
              className={`rounded-xl border px-3 py-2 text-xs font-semibold transition-colors ${
                i === step
                  ? 'border-indigo-600 bg-indigo-600 text-white'
                  : i < step
                    ? 'border-teal-300 bg-teal-50 text-teal-600 dark:bg-teal-400/10 dark:text-teal-200'
                    : 'border-[rgb(var(--line))] text-ink-faint'
              }`}
            >
              <span className="mr-1.5">{i + 1}</span>
              {s.title}
            </button>
          </li>
        ))}
      </ol>

      <Card className="p-6">
        {/* ---------------- 0: where ---------------- */}
        {step === 0 && (
          <div className="space-y-5">
            <Field label="Destination" required htmlFor="cluster">
              <Select
                id="cluster"
                value={form.cluster_slug}
                onChange={(e) => update('cluster_slug', e.target.value)}
              >
                <option value="">Choose a destination…</option>
                {destinations.data?.map((c) => (
                  <option key={c.slug} value={c.slug}>
                    {c.name} — {c.state} ({c.attraction_count} places)
                  </option>
                ))}
              </Select>
            </Field>

            {selectedCluster && (
              <Callout tone="indigo">
                {selectedCluster.summary}
                <span className="mt-1 block text-xs">
                  Typical length {selectedCluster.recommended_days} days.
                </span>
              </Callout>
            )}

            <Field label="Trip name" htmlFor="title" hint="Optional — we'll generate one otherwise.">
              <Input
                id="title"
                value={form.title}
                onChange={(e) => update('title', e.target.value)}
                placeholder="Long weekend with the cousins"
                maxLength={160}
              />
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

            <Field
              label="Starting location"
              htmlFor="origin"
              hint="Where each day begins — usually your hotel area."
            >
              <Input
                id="origin"
                value={form.origin_label}
                onChange={(e) => update('origin_label', e.target.value)}
                placeholder="City centre"
              />
            </Field>
          </div>
        )}

        {/* ---------------- 1: who ---------------- */}
        {step === 1 && (
          <div className="space-y-5">
            <Field label="Number of travellers" required htmlFor="count">
              <Input
                id="count"
                type="number"
                min={1}
                max={40}
                value={form.traveller_count}
                onChange={(e) => update('traveller_count', Number(e.target.value))}
              />
            </Field>
            <div className="space-y-3">
              <Toggle
                label="Travelling with children"
                checked={form.has_children}
                onChange={(v) => update('has_children', v)}
                description="Raises the weight of child-friendly places and shortens long days."
              />
              <Toggle
                label="Travelling with senior citizens"
                checked={form.has_seniors}
                onChange={(v) => update('has_seniors', v)}
                description="Adds rest breaks and favours lower physical intensity."
              />
              <Toggle
                label="Step-free access required"
                checked={form.accessibility_required}
                onChange={(v) => update('accessibility_required', v)}
                description="Inaccessible places are removed entirely, not just down-ranked."
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Your mobility" htmlFor="mobility">
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
            </div>
          </div>
        )}

        {/* ---------------- 2: style ---------------- */}
        {step === 2 && (
          <div className="space-y-5">
            <Field label="Pace" htmlFor="pace" hint="Sets the hard cap on stops and travel per day.">
              <Select
                id="pace"
                value={form.pace}
                onChange={(e) => update('pace', e.target.value as FormState['pace'])}
              >
                <option value="relaxed">Relaxed — up to 3 stops, longer breaks</option>
                <option value="balanced">Balanced — up to 4 stops</option>
                <option value="packed">Packed — up to 6 stops, shorter visits</option>
              </Select>
            </Field>

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
              <Field label="Accommodation" htmlFor="tier">
                <Select
                  id="tier"
                  value={form.accommodation_tier}
                  onChange={(e) =>
                    update('accommodation_tier', e.target.value as FormState['accommodation_tier'])
                  }
                >
                  <option value="budget">Budget</option>
                  <option value="midrange">Mid-range</option>
                  <option value="premium">Premium</option>
                </Select>
              </Field>
            </div>

            <Field
              label={`Budget per person: ₹${form.budget_per_person_inr.toLocaleString('en-IN')}`}
              htmlFor="budget"
              hint="Used as a hard cap on entry fees and to size the cost estimate."
            >
              <input
                id="budget"
                type="range"
                min={2000}
                max={80000}
                step={1000}
                value={form.budget_per_person_inr}
                onChange={(e) => update('budget_per_person_inr', Number(e.target.value))}
                className="h-2 w-full cursor-pointer appearance-none rounded-full bg-sand-300 accent-indigo-600 dark:bg-white/15"
              />
            </Field>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={`Day starts at ${hhmm(form.day_start_min)}`} htmlFor="dstart">
                <input
                  id="dstart"
                  type="range"
                  min={300}
                  max={720}
                  step={30}
                  value={form.day_start_min}
                  onChange={(e) => update('day_start_min', Number(e.target.value))}
                  className="h-2 w-full cursor-pointer appearance-none rounded-full bg-sand-300 accent-indigo-600 dark:bg-white/15"
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
                  className="h-2 w-full cursor-pointer appearance-none rounded-full bg-sand-300 accent-indigo-600 dark:bg-white/15"
                />
              </Field>
            </div>

            <Field label="Indoor / outdoor preference" htmlFor="io">
              <Select
                id="io"
                value={form.indoor_outdoor_pref}
                onChange={(e) =>
                  update('indoor_outdoor_pref', e.target.value as FormState['indoor_outdoor_pref'])
                }
              >
                <option value="mixed">A mix</option>
                <option value="outdoor">Mostly outdoors</option>
                <option value="indoor">Mostly indoors</option>
              </Select>
            </Field>
          </div>
        )}

        {/* ---------------- 3: interests ---------------- */}
        {step === 3 && (
          <div className="space-y-5">
            <Callout tone="indigo" title="These are your preferences, not the group's">
              Every member submits their own. The planner aggregates them with a fairness-aware
              method that protects whoever would otherwise be least satisfied.
            </Callout>
            <div className="space-y-3">
              {INTEREST_KEYS.map((key) => (
                <Slider
                  key={key}
                  label={INTEREST_LABEL[key]}
                  value={form.interests[key]}
                  onChange={(v) => update('interests', { ...form.interests, [key]: v })}
                />
              ))}
            </div>
          </div>
        )}

        {/* ---------------- 4: musts ---------------- */}
        {step === 4 && (
          <div className="space-y-5">
            <Callout tone="saffron">
              Must-visit places are scheduled first and are guaranteed to appear. Anything you avoid
              is removed from consideration entirely.
            </Callout>
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
              title="Avoid"
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
            <Field label="Anything else we should know?" htmlFor="notes">
              <Textarea
                id="notes"
                value={form.notes}
                onChange={(e) => update('notes', e.target.value)}
                maxLength={2000}
                placeholder="One of us gets motion sick on mountain roads…"
              />
            </Field>
          </div>
        )}

        {/* ---------------- 5: review ---------------- */}
        {step === 5 && (
          <div className="space-y-5">
            <h2 className="font-display text-xl text-ink dark:text-sand-100">
              Ready to generate
            </h2>
            <dl className="grid gap-3 sm:grid-cols-2">
              <Review label="Destination" value={selectedCluster?.name ?? '—'} />
              <Review label="Dates" value={`${form.start_date} → ${form.end_date} (${days} days)`} />
              <Review label="Travellers" value={String(form.traveller_count)} />
              <Review
                label="Budget"
                value={`₹${form.budget_per_person_inr.toLocaleString('en-IN')} per person`}
              />
              <Review label="Pace" value={titleise(form.pace)} />
              <Review label="Transport" value={titleise(form.transport_mode)} />
              <Review
                label="Day window"
                value={`${hhmm(form.day_start_min)} – ${hhmm(form.day_end_min)}`}
              />
              <Review
                label="Accessibility"
                value={form.accessibility_required ? 'Step-free required' : 'No requirement'}
              />
              <Review
                label="Must visit"
                value={form.must_visit_slugs.length ? form.must_visit_slugs.join(', ') : 'None'}
              />
              <Review
                label="Avoiding"
                value={form.avoid_slugs.length ? form.avoid_slugs.join(', ') : 'None'}
              />
            </dl>

            <Callout tone="teal" title="What happens next">
              We filter out anything infeasible, score the rest against your group, cluster them
              geographically, build a travel-time matrix, optimise each day with OR-Tools, then run
              15 validation checks. You&apos;ll only see the plan if it passes all of them.
            </Callout>

            {create.isError && (
              <ErrorState
                title={
                  (create.error as ApiRequestError)?.isInfeasible
                    ? 'No feasible itinerary'
                    : 'Could not create the trip'
                }
                message={
                  (create.error as ApiRequestError)?.isInfeasible
                    ? 'Your constraints leave no valid schedule. Try widening the day window, relaxing the pace, or raising the budget.'
                    : (create.error as Error).message
                }
              />
            )}
          </div>
        )}

        {/* ---- errors + nav ---- */}
        {stepErrors.length > 0 && (
          <ul className="mt-5 space-y-1">
            {stepErrors.map((e) => (
              <li key={e} className="text-sm text-clay-500">
                {e}
              </li>
            ))}
          </ul>
        )}

        <div className="mt-7 flex items-center justify-between gap-3 border-t border-[rgb(var(--line))] pt-5">
          <Button
            variant="ghost"
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0}
          >
            Back
          </Button>
          {step < STEPS.length - 1 ? (
            <Button onClick={() => setStep((s) => s + 1)} disabled={!canContinue}>
              Continue
            </Button>
          ) : (
            <Button
              size="lg"
              loading={create.isPending}
              onClick={() => create.mutate()}
              disabled={!canContinue}
            >
              {create.isPending ? 'Optimising your itinerary…' : 'Generate itinerary'}
            </Button>
          )}
        </div>
      </Card>
    </PageShell>
  );
}

function validateStep(step: number, form: FormState, days: number): string[] {
  const errors: string[] = [];
  if (step === 0) {
    if (!form.cluster_slug) errors.push('Choose a destination to continue.');
    if (new Date(form.end_date) < new Date(form.start_date))
      errors.push('The end date cannot be before the start date.');
    if (days > 21) errors.push('Trips are limited to 21 days in this version.');
  }
  if (step === 1 && (form.traveller_count < 1 || form.traveller_count > 40)) {
    errors.push('Traveller count must be between 1 and 40.');
  }
  if (step === 2) {
    if (form.day_end_min <= form.day_start_min)
      errors.push('The day must end after it starts.');
    else if (form.day_end_min - form.day_start_min < 180)
      errors.push('A planning day needs to be at least three hours long.');
  }
  return errors;
}

function Review({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[rgb(var(--line))] bg-[rgb(var(--surface-2))] px-3.5 py-2.5">
      <dt className="text-xs text-ink-faint">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium text-ink dark:text-sand-200">{value}</dd>
    </div>
  );
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
