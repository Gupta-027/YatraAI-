'use client';

import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { DestinationCard } from '@/components/DestinationCard';
import { PageShell } from '@/components/Shell';
import { Button, Skeleton } from '@/components/ui';
import { api } from '@/lib/api';
import { destinationImage } from '@/lib/utils';

const STEPS = [
  ['Pick a place', 'Choose one of ten destinations and your dates.'],
  ['Tell us your style', 'Group size, budget, pace and what you enjoy.'],
  ['Get your plan', 'A day-by-day itinerary with times and travel.'],
];

export default function HomePage() {
  const router = useRouter();
  const { data: clusters, isLoading } = useQuery({
    queryKey: ['destinations'],
    queryFn: api.destinations,
  });
  const [destination, setDestination] = useState('');

  return (
    <PageShell className="pt-0">
      {/* ---------------- hero ---------------- */}
      <section className="relative -mx-4 mb-14 overflow-hidden sm:-mx-6 sm:rounded-b-3xl">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={destinationImage('delhi-agra', 1920)}
          alt=""
          className="absolute inset-0 h-full w-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-b from-black/55 via-black/35 to-black/60" />
        <div className="relative mx-auto max-w-3xl px-4 py-24 text-center sm:py-32">
          <h1 className="font-display text-4xl leading-tight text-white sm:text-6xl">
            Plan your India trip in minutes
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-base text-white/85 sm:text-lg">
            Tell us where you&apos;re going and what you like. We&apos;ll build a day-by-day
            itinerary for your whole group.
          </p>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              router.push(destination ? `/plan?destination=${destination}` : '/plan');
            }}
            className="mx-auto mt-8 flex max-w-xl flex-col gap-2 rounded-2xl bg-white p-2 shadow-lift sm:flex-row"
          >
            <label htmlFor="hero-destination" className="sr-only">
              Destination
            </label>
            <select
              id="hero-destination"
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              className="min-h-12 flex-1 rounded-xl bg-transparent px-4 text-base text-ink outline-none"
            >
              <option value="">Where do you want to go?</option>
              {clusters?.map((c) => (
                <option key={c.slug} value={c.slug}>
                  {c.name}
                </option>
              ))}
            </select>
            <Button type="submit" size="lg" className="min-h-12 px-7">
              Plan my trip
            </Button>
          </form>
        </div>
      </section>

      {/* ---------------- how it works ---------------- */}
      <section className="mb-16">
        <h2 className="mb-6 text-center font-display text-2xl text-ink dark:text-sand-100">
          How it works
        </h2>
        <ol className="grid gap-4 sm:grid-cols-3">
          {STEPS.map(([title, body], i) => (
            <li key={title} className="text-center">
              <span className="mx-auto mb-3 grid h-10 w-10 place-items-center rounded-full bg-saffron-50 font-semibold text-saffron-600 dark:bg-saffron-400/15 dark:text-saffron-200">
                {i + 1}
              </span>
              <p className="font-semibold text-ink dark:text-sand-100">{title}</p>
              <p className="mt-1 text-sm text-ink-muted dark:text-sand-400">{body}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* ---------------- destinations ---------------- */}
      <section>
        <h2 className="mb-6 font-display text-2xl text-ink dark:text-sand-100">
          Popular destinations
        </h2>
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {isLoading
            ? Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="aspect-[4/3] rounded-2xl" />
              ))
            : clusters?.map((cluster) => (
                <DestinationCard key={cluster.slug} cluster={cluster} />
              ))}
        </div>
      </section>
    </PageShell>
  );
}
