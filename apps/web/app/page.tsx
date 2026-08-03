'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';

import { PipelineStrip } from '@/components/Pipeline';
import { PageShell } from '@/components/Shell';
import { Badge, Button, Card, CardSkeleton, SectionHeading } from '@/components/ui';
import { api } from '@/lib/api';

const MEASURED = [
  { value: '−57%', label: 'travel vs greedy', sub: '6 scenarios' },
  { value: '0.95', label: 'retrieval MRR', sub: '34 questions' },
  { value: '1.00', label: 'abstention accuracy', sub: 'refuses when it should' },
  { value: '330', label: 'tests passing', sub: 'lint + types clean' },
];

export default function HomePage() {
  const { data: clusters, isLoading } = useQuery({
    queryKey: ['destinations'],
    queryFn: api.destinations,
  });

  return (
    <PageShell>
      {/* ---------------- hero ---------------- */}
      <section className="relative -mx-4 mb-12 overflow-hidden bg-hero-warm px-4 pb-12 pt-10 sm:-mx-6 sm:px-6 sm:pt-14">
        <div className="mx-auto max-w-3xl text-center">
          <Badge tone="teal" className="mb-5">
            Constraint solver · hybrid RAG · fairness ranking
          </Badge>
          <h1 className="font-display text-4xl leading-[1.1] text-ink dark:text-sand-100 sm:text-6xl">
            Group itineraries that are{' '}
            <span className="text-indigo-600 dark:text-indigo-300">fair</span>,{' '}
            <span className="text-saffron-500">explainable</span> and{' '}
            <span className="text-teal-500">feasible</span>.
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-base text-ink-muted dark:text-sand-300">
            Four people, four preferences, one schedule that respects opening hours, travel time and
            budget — with the reason for every stop.
          </p>
          <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
            <Link href="/plan">
              <Button size="lg">Plan a trip</Button>
            </Link>
            <Link href="/login">
              <Button size="lg" variant="secondary">
                Open the demo
              </Button>
            </Link>
          </div>
        </div>

        <dl className="mx-auto mt-10 grid max-w-3xl grid-cols-2 gap-4 sm:grid-cols-4">
          {MEASURED.map((stat) => (
            <div key={stat.label} className="text-center">
              <dt className="sr-only">{stat.label}</dt>
              <dd>
                <p className="font-display text-3xl text-indigo-600 dark:text-indigo-300">
                  {stat.value}
                </p>
                <p className="mt-0.5 text-xs font-medium text-ink dark:text-sand-200">
                  {stat.label}
                </p>
                <p className="text-[11px] text-ink-faint">{stat.sub}</p>
              </dd>
            </div>
          ))}
        </dl>
      </section>

      {/* ---------------- how it works ---------------- */}
      <section className="mb-12">
        <SectionHeading
          title="How a plan gets built"
          description="Five stages. The model runs last and changes nothing."
        />
        <PipelineStrip />
      </section>

      {/* ---------------- destinations ---------------- */}
      <section className="mb-12">
        <SectionHeading
          title="Ten destinations"
          action={
            <Link href="/destinations">
              <Button variant="secondary" size="sm">
                See all
              </Button>
            </Link>
          }
        />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {isLoading
            ? Array.from({ length: 6 }).map((_, i) => <CardSkeleton key={i} />)
            : clusters?.slice(0, 6).map((cluster) => (
                <Link key={cluster.slug} href={`/destinations/${cluster.slug}`} className="group">
                  <Card className="flex h-full items-center justify-between gap-3 p-4 transition-shadow hover:shadow-lift">
                    <div className="min-w-0">
                      <h3 className="truncate font-display text-base text-ink group-hover:text-indigo-600 dark:text-sand-100">
                        {cluster.name}
                      </h3>
                      <p className="text-xs text-ink-faint">
                        {cluster.state} · {cluster.recommended_days} days
                      </p>
                    </div>
                    <Badge tone="indigo">{cluster.attraction_count}</Badge>
                  </Card>
                </Link>
              ))}
        </div>
      </section>

      {/* ---------------- guarantees ---------------- */}
      <section className="mb-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ['No verified hours or fees', 'Every schedule row is labelled unverified.'],
            ['Cited or silent', 'The assistant abstains when the corpus cannot answer.'],
            ['Approximate location', 'Opt-in, snapped to ~500 m, deleted on stop.'],
            ['No invented metrics', 'Every number here re-runs from a script in the repo.'],
          ].map(([title, body]) => (
            <Card key={title} className="p-4">
              <p className="text-sm font-semibold text-ink dark:text-sand-100">{title}</p>
              <p className="mt-1 text-xs leading-relaxed text-ink-muted dark:text-sand-400">
                {body}
              </p>
            </Card>
          ))}
        </div>
      </section>
    </PageShell>
  );
}
