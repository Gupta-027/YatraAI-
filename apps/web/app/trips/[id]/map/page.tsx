'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';

import { MiniMap, type MapPoint } from '@/components/Map';
import { PageShell } from '@/components/Shell';
import {
  Badge,
  Button,
  Callout,
  Card,
  CardSkeleton,
  ErrorState,
  Field,
  SectionHeading,
  Select,
  Toggle,
} from '@/components/ui';
import { api } from '@/lib/api';
import { useRequireAuth } from '@/lib/auth';
import { relativeTime, seededColour } from '@/lib/utils';

export default function LiveMapPage() {
  const { id } = useParams<{ id: string }>();
  const { loading: authLoading } = useRequireAuth();
  const queryClient = useQueryClient();

  const [consented, setConsented] = useState(false);
  const [precision, setPrecision] = useState<'approximate' | 'exact'>('approximate');
  const [interval, setIntervalSeconds] = useState(60);
  const [duration, setDuration] = useState(4);
  const [sharing, setSharing] = useState(false);
  const [geoError, setGeoError] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  const consent = useQuery({
    queryKey: ['consent', id],
    queryFn: () => api.consentText(id),
    enabled: !!id,
  });
  const group = useQuery({
    queryKey: ['group-location', id],
    queryFn: () => api.groupLocation(id),
    enabled: !!id,
    refetchInterval: 15_000,
  });

  const start = useMutation({
    mutationFn: () =>
      api.startSharing(id, {
        consent_granted: true,
        precision,
        update_interval_seconds: interval,
        duration_hours: duration,
      }),
    onSuccess: () => {
      setSharing(true);
      void postPosition();
    },
  });

  const stop = useMutation({
    mutationFn: () => api.stopSharing(id),
    onSuccess: () => {
      setSharing(false);
      void queryClient.invalidateQueries({ queryKey: ['group-location', id] });
    },
  });

  const sos = useMutation({
    mutationFn: (message: string) => api.raiseSos(id, message),
  });

  /** Reads a position from the browser and posts it. Never runs unprompted. */
  const postPosition = useCallback(async () => {
    if (!('geolocation' in navigator)) {
      setGeoError('This browser does not expose a location API.');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        setGeoError(null);
        try {
          await api.postPoint(id, pos.coords.latitude, pos.coords.longitude, pos.coords.accuracy);
          void queryClient.invalidateQueries({ queryKey: ['group-location', id] });
        } catch (error) {
          setGeoError((error as Error).message);
          setSharing(false);
        }
      },
      (error) => setGeoError(`Location unavailable: ${error.message}`),
      { enableHighAccuracy: precision === 'exact', timeout: 15_000, maximumAge: 30_000 }
    );
  }, [id, precision, queryClient]);

  // The browser is polled only while sharing is explicitly on, and the timer is
  // torn down the moment it stops or the page unmounts.
  useEffect(() => {
    if (!sharing) {
      if (timerRef.current) window.clearInterval(timerRef.current);
      timerRef.current = null;
      return;
    }
    timerRef.current = window.setInterval(() => void postPosition(), interval * 1000);
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
    };
  }, [sharing, interval, postPosition]);

  const points: MapPoint[] = [];
  if (group.data) {
    group.data.positions.forEach((p) =>
      points.push({
        lat: p.lat,
        lon: p.lon,
        label: p.display_name,
        sublabel: `${p.is_approximate ? 'Approximate' : 'Exact'} · ${relativeTime(p.recorded_at)}`,
        colour: seededColour(p.display_name),
        kind: 'member',
      })
    );
    if (group.data.suggested_meeting_point) {
      points.push({
        lat: group.data.suggested_meeting_point.lat,
        lon: group.data.suggested_meeting_point.lon,
        label: group.data.suggested_meeting_point.label,
        sublabel: group.data.suggested_meeting_point.reason,
        colour: '#e07a3f',
        kind: 'meeting',
      });
    }
  }

  return (
    <PageShell>
      <div className="mb-2">
        <Link href={`/trips/${id}`} className="text-sm text-ink-muted hover:underline dark:text-sand-400">
          ← Back to itinerary
        </Link>
      </div>

      <SectionHeading
        level={1}
        title="Live group map"
        description="Consent-based, expiring and deletable. Nothing is shared until you explicitly turn it on."
      />

      {authLoading && <CardSkeleton lines={4} />}

      <div className="grid gap-5 lg:grid-cols-[1fr_22rem]">
        <div className="space-y-5">
          <MiniMap points={points} height={420} />

          {group.data?.separation_warning && (
            <Callout tone="saffron" title="Your group has spread out">
              The furthest member is {group.data.max_separation_km.toFixed(1)} km from the group
              centre.{' '}
              {group.data.suggested_meeting_point &&
                `Suggested regroup point: ${group.data.suggested_meeting_point.label}. ${group.data.suggested_meeting_point.reason}`}
            </Callout>
          )}

          {group.data?.eta_to_next && group.data.eta_to_next.length > 0 && (
            <Card className="p-5">
              <h2 className="mb-1 font-display text-base text-ink dark:text-sand-100">
                ETA to {group.data.next_activity?.title}
              </h2>
              <p className="mb-3 text-xs text-ink-faint">
                Estimated with the same routing model the planner uses.
              </p>
              <ul className="space-y-2">
                {group.data.eta_to_next.map((eta) => (
                  <li key={eta.member_id} className="flex items-center justify-between text-sm">
                    <span className="text-ink dark:text-sand-200">{eta.display_name}</span>
                    <span className="text-ink-muted dark:text-sand-400">
                      {eta.distance_km.toFixed(1)} km · about {eta.eta_minutes} min
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card className="p-5">
            <h2 className="mb-3 font-display text-base text-ink dark:text-sand-100">
              Who is sharing
            </h2>
            {group.isLoading && <CardSkeleton lines={2} />}
            {group.data?.positions.length === 0 && (
              <p className="text-sm text-ink-faint">
                Nobody is sharing their location right now.
              </p>
            )}
            <ul className="space-y-2">
              {group.data?.positions.map((p) => (
                <li
                  key={p.member_id}
                  className="flex flex-wrap items-center justify-between gap-2 text-sm"
                >
                  <span className="flex items-center gap-2">
                    <span
                      aria-hidden="true"
                      className="h-2.5 w-2.5 rounded-full"
                      style={{ background: seededColour(p.display_name) }}
                    />
                    <span className="text-ink dark:text-sand-200">{p.display_name}</span>
                  </span>
                  <span className="flex items-center gap-2">
                    <Badge tone={p.is_approximate ? 'neutral' : 'saffron'}>
                      {p.is_approximate ? 'Approximate' : 'Exact'}
                    </Badge>
                    <span className="text-xs text-ink-faint">
                      {relativeTime(p.recorded_at)}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        </div>

        {/* ---- controls ---- */}
        <aside className="space-y-4 lg:sticky lg:top-24 lg:self-start">
          <Card className="p-5">
            <h2 className="mb-2 font-display text-base text-ink dark:text-sand-100">
              Location sharing
            </h2>

            {!sharing ? (
              <>
                <div className="mb-4 rounded-xl border border-[rgb(var(--line))] bg-[rgb(var(--surface-2))] p-3.5">
                  <p className="text-xs leading-relaxed text-ink-muted dark:text-sand-400">
                    {consent.data?.text ?? group.data?.consent_text ?? 'Loading consent text…'}
                  </p>
                  {consent.data?.guarantees && (
                    <ul className="mt-2 space-y-1">
                      {consent.data.guarantees.map((g) => (
                        <li key={g} className="text-[11px] text-teal-600 dark:text-teal-300">
                          · {g}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className="space-y-3">
                  <Field label="Precision" htmlFor="prec">
                    <Select
                      id="prec"
                      value={precision}
                      onChange={(e) => setPrecision(e.target.value as typeof precision)}
                    >
                      <option value="approximate">
                        Approximate — snapped to about 500 m (recommended)
                      </option>
                      <option value="exact">Exact position</option>
                    </Select>
                  </Field>
                  <Field label="Update every" htmlFor="int">
                    <Select
                      id="int"
                      value={String(interval)}
                      onChange={(e) => setIntervalSeconds(Number(e.target.value))}
                    >
                      <option value="30">30 seconds</option>
                      <option value="60">1 minute</option>
                      <option value="300">5 minutes</option>
                      <option value="900">15 minutes</option>
                    </Select>
                  </Field>
                  <Field label="Stop automatically after" htmlFor="dur">
                    <Select
                      id="dur"
                      value={String(duration)}
                      onChange={(e) => setDuration(Number(e.target.value))}
                    >
                      <option value="1">1 hour</option>
                      <option value="4">4 hours</option>
                      <option value="8">8 hours</option>
                      <option value="12">12 hours (maximum)</option>
                    </Select>
                  </Field>

                  <Toggle
                    label="I consent to sharing my location"
                    checked={consented}
                    onChange={setConsented}
                    description="Required. Sharing cannot start without this."
                  />

                  <Button
                    full
                    disabled={!consented}
                    loading={start.isPending}
                    onClick={() => start.mutate()}
                  >
                    Start sharing
                  </Button>
                  {start.isError && (
                    <ErrorState message={(start.error as Error).message} />
                  )}
                </div>
              </>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <span className="relative flex h-2.5 w-2.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-teal-400 opacity-70" />
                    <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-teal-500" />
                  </span>
                  <span className="text-sm font-semibold text-teal-600 dark:text-teal-300">
                    Sharing is on
                  </span>
                </div>
                <p className="text-xs text-ink-muted dark:text-sand-400">
                  Posting a {precision} position every {interval} seconds. It stops automatically
                  after {duration} hour{duration === 1 ? '' : 's'}.
                </p>
                <Button variant="secondary" full onClick={() => setSharing(false)}>
                  Pause
                </Button>
                <Button
                  variant="danger"
                  full
                  loading={stop.isPending}
                  onClick={() => stop.mutate()}
                >
                  Stop and delete my trail
                </Button>
              </div>
            )}

            {geoError && (
              <p className="mt-3 text-xs text-clay-500" role="alert">
                {geoError}
              </p>
            )}
          </Card>

          {/* ---- SOS ---- */}
          <Card className="border-clay-400/40 p-5">
            <h2 className="mb-1 font-display text-base text-clay-600 dark:text-clay-400">
              Emergency (demo)
            </h2>
            <Callout tone="clay">
              <strong>This is a demonstration only.</strong> It notifies members of this trip inside
              the app. It does <strong>not</strong> contact emergency services, and must never be
              relied on in a real emergency.
            </Callout>
            <Button
              variant="danger"
              full
              className="mt-3"
              loading={sos.isPending}
              onClick={() => sos.mutate('Requesting help from the group')}
            >
              Raise demo SOS
            </Button>
            {sos.isSuccess && (
              <p className="mt-2 text-xs text-teal-600 dark:text-teal-300">
                Demo alert raised — your group will see it in the chat.
              </p>
            )}
          </Card>
        </aside>
      </div>
    </PageShell>
  );
}
