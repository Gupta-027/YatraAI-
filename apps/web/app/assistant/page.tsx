'use client';

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { AskPanel } from '@/components/PlaceDrawer';
import { RetrievalInspector } from '@/components/RetrievalInspector';
import { PageShell } from '@/components/Shell';
import { Callout, Card, EmptyState, SectionHeading, Select } from '@/components/ui';
import { api } from '@/lib/api';

export default function AssistantPage() {
  const [cluster, setCluster] = useState('delhi-agra');
  const [lastQuestion, setLastQuestion] = useState('');
  const destinations = useQuery({ queryKey: ['destinations'], queryFn: api.destinations });

  return (
    <PageShell>
      <SectionHeading
        level={1}
        title="Travel assistant"
        description="Grounded in a cited knowledge base. Citations are computed from the retrieved text, not requested from a model."
      />

      <div className="grid gap-5 lg:grid-cols-[1fr_22rem]">
        <Card className="p-6">
          <div className="mb-5">
            <label
              htmlFor="cluster"
              className="mb-1 block text-sm font-semibold text-ink dark:text-sand-200"
            >
              Destination
            </label>
            <Select id="cluster" value={cluster} onChange={(e) => setCluster(e.target.value)}>
              {destinations.data?.map((c) => (
                <option key={c.slug} value={c.slug}>
                  {c.name}
                </option>
              ))}
            </Select>
          </div>
          <AskPanel clusterSlug={cluster} onAsked={setLastQuestion} />
        </Card>

        {/* The sidebar used to describe retrieval in five numbered paragraphs. It now
            shows the actual scores for the question just asked, which makes the same
            point without the prose and cannot drift out of date. */}
        <aside className="space-y-4 lg:sticky lg:top-24 lg:self-start">
          {lastQuestion ? (
            <RetrievalInspector question={lastQuestion} clusterSlug={cluster} />
          ) : (
            <EmptyState
              title="Ask something"
              description="The scores each retrieval arm gave every candidate chunk will appear here."
            />
          )}

          <Callout tone="saffron" title="What it will not do">
            Confirm today&apos;s ticket price or opening hours. Those change without notice, and the
            dataset records them as unverified.
          </Callout>
        </aside>
      </div>
    </PageShell>
  );
}
