'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useState } from 'react';

import { PageShell } from '@/components/Shell';
import {
  Avatar,
  Badge,
  Button,
  Card,
  CardSkeleton,
  EmptyState,
  ErrorState,
  Field,
  Input,
  SectionHeading,
} from '@/components/ui';
import { api } from '@/lib/api';
import { useRequireAuth } from '@/lib/auth';
import { destinationImage, formatDate, titleise } from '@/lib/utils';

export default function TripsPage() {
  const { loading: authLoading } = useRequireAuth();
  const queryClient = useQueryClient();
  const [inviteCode, setInviteCode] = useState('');

  const trips = useQuery({ queryKey: ['trips'], queryFn: api.trips, enabled: !authLoading });

  const join = useMutation({
    mutationFn: (code: string) => api.joinTrip(code.trim().toUpperCase()),
    onSuccess: () => {
      setInviteCode('');
      void queryClient.invalidateQueries({ queryKey: ['trips'] });
    },
  });

  return (
    <PageShell>
      <SectionHeading
        level={1}
        title="My trips"
        description="Trips you own or have been invited to."
        action={
          <Link href="/plan">
            <Button>New trip</Button>
          </Link>
        }
      />

      <Card className="mb-6 p-5">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (inviteCode.trim().length >= 4) join.mutate(inviteCode);
          }}
          className="flex flex-wrap items-end gap-3"
        >
          <div className="min-w-[14rem] flex-1">
            <Field
              label="Join a trip"
              htmlFor="invite"
              hint="Ask the trip owner for their 8-character invite code."
              error={join.isError ? (join.error as Error).message : undefined}
            >
              <Input
                id="invite"
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value.toUpperCase())}
                placeholder="ABCD2345"
                maxLength={12}
                className="font-mono uppercase tracking-widest"
              />
            </Field>
          </div>
          <Button type="submit" loading={join.isPending} disabled={inviteCode.trim().length < 4}>
            Join
          </Button>
        </form>
      </Card>

      {trips.isLoading && (
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <CardSkeleton key={i} lines={4} />
          ))}
        </div>
      )}

      {trips.error && (
        <ErrorState message={(trips.error as Error).message} onRetry={() => void trips.refetch()} />
      )}

      {trips.data?.length === 0 && (
        <EmptyState
          title="No trips yet"
          description="Create your first group trip, or join one with an invite code."
          action={
            <Link href="/plan">
              <Button>Plan a trip</Button>
            </Link>
          }
        />
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {trips.data?.map((trip) => (
          <Link key={trip.id} href={`/trips/${trip.id}`} className="group">
            <Card className="h-full overflow-hidden transition-shadow hover:shadow-lift">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={destinationImage(trip.cluster_slug, 800)}
                alt=""
                loading="lazy"
                className="h-40 w-full object-cover"
              />
              <div className="p-5">
              <div className="mb-2 flex items-start justify-between gap-2">
                <h2 className="font-display text-lg text-ink group-hover:text-saffron-500 dark:text-sand-100">
                  {trip.title}
                </h2>
                <Badge tone={trip.has_itinerary ? 'teal' : 'saffron'}>
                  {trip.has_itinerary ? 'Planned' : titleise(trip.status)}
                </Badge>
              </div>
              <p className="text-sm text-ink-muted dark:text-sand-400">
                {trip.cluster_name} · {formatDate(trip.start_date)} – {formatDate(trip.end_date)}
              </p>
              <p className="mt-0.5 text-xs text-ink-faint">
                {trip.duration_days} days · {trip.traveller_count} travellers ·{' '}
                {titleise(trip.pace)} pace
              </p>

              <div className="mt-3 flex items-center justify-between gap-3 border-t border-[rgb(var(--line))] pt-3">
                <div className="flex -space-x-2">
                  {trip.members.slice(0, 5).map((m) => (
                    <span key={m.id} className="ring-2 ring-[rgb(var(--surface))]">
                      <Avatar name={m.display_name} size={26} />
                    </span>
                  ))}
                </div>
                <span className="text-xs text-ink-faint">
                  {trip.preferences_submitted}/{trip.members.length} preferences in
                </span>
              </div>
              </div>
            </Card>
          </Link>
        ))}
      </div>
    </PageShell>
  );
}
