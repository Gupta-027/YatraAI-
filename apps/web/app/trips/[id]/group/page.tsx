'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

import { PageShell } from '@/components/Shell';
import {
  Avatar,
  Badge,
  Button,
  Callout,
  Card,
  CardSkeleton,
  ErrorState,
  Field,
  Input,
  Meter,
  SectionHeading,
  Select,
  Slider,
  Textarea,
  Toggle,
} from '@/components/ui';
import { api } from '@/lib/api';
import { useAuth, useRequireAuth } from '@/lib/auth';
import { INTEREST_KEYS, INTEREST_LABEL, hhmm, relativeTime, titleise } from '@/lib/utils';

export default function GroupRoomPage() {
  const { id } = useParams<{ id: string }>();
  const { loading: authLoading } = useRequireAuth();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const trip = useQuery({ queryKey: ['trip', id], queryFn: () => api.trip(id), enabled: !!id });
  const proposals = useQuery({
    queryKey: ['proposals', id],
    queryFn: () => api.proposals(id),
    enabled: !!id,
    refetchInterval: 20_000,
  });
  const messages = useQuery({
    queryKey: ['chat', id],
    queryFn: () => api.messages(id),
    enabled: !!id,
    // Polling rather than websockets: one endpoint, no extra infrastructure,
    // and adequate for a group of a handful of people.
    refetchInterval: 8_000,
  });

  const myMember = trip.data?.members.find((m) => m.user_id === user?.id);

  return (
    <PageShell>
      <div className="mb-2">
        <Link href={`/trips/${id}`} className="text-sm text-ink-muted hover:underline dark:text-sand-400">
          ← Back to itinerary
        </Link>
      </div>

      <SectionHeading
        level={1}
        title="Group preference room"
        description="Everyone submits their own preferences. The planner aggregates them with a fairness-aware method rather than an average, so a minority is never quietly overruled."
      />

      {trip.isLoading && <CardSkeleton lines={6} />}
      {trip.error && <ErrorState message={(trip.error as Error).message} />}

      {trip.data && (
        <div className="grid gap-5 lg:grid-cols-[1fr_22rem]">
          <div className="space-y-5">
            {/* ---- invite ---- */}
            <Card className="p-5">
              <h2 className="mb-1 font-display text-base text-ink dark:text-sand-100">
                Invite your group
              </h2>
              <p className="mb-3 text-xs text-ink-muted dark:text-sand-400">
                Share this code. Each person submits preferences separately — that is what makes the
                fairness maths meaningful.
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <code className="rounded-xl border border-[rgb(var(--line))] bg-[rgb(var(--surface-2))] px-4 py-2.5 font-mono text-lg tracking-[0.3em] text-indigo-600 dark:text-indigo-300">
                  {trip.data.invite_code}
                </code>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void navigator.clipboard.writeText(trip.data!.invite_code)}
                >
                  Copy code
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    void navigator.clipboard.writeText(
                      `${window.location.origin}/trips?invite=${trip.data!.invite_code}`
                    )
                  }
                >
                  Copy link
                </Button>
              </div>
            </Card>

            {/* ---- members ---- */}
            <Card className="p-5">
              <h2 className="mb-3 font-display text-base text-ink dark:text-sand-100">
                Members ({trip.data.members.length})
              </h2>
              <ul className="space-y-3">
                {trip.data.members.map((member) => (
                  <li key={member.id} className="flex items-start gap-3">
                    <Avatar name={member.display_name} size={34} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-ink dark:text-sand-200">
                          {member.display_name}
                        </span>
                        {member.role === 'owner' && <Badge tone="indigo">Owner</Badge>}
                        {member.status === 'opted_out' && <Badge tone="clay">Opted out</Badge>}
                        <Badge tone={member.preferences?.submitted ? 'teal' : 'saffron'}>
                          {member.preferences?.submitted ? 'Preferences in' : 'Waiting'}
                        </Badge>
                      </div>
                      {member.preferences?.submitted && (
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {Object.entries(member.preferences.interests ?? {})
                            .filter(([, v]) => Number(v) >= 4)
                            .slice(0, 4)
                            .map(([k]) => (
                              <Badge key={k} tone="neutral">
                                {INTEREST_LABEL[k] ?? titleise(k)}
                              </Badge>
                            ))}
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </Card>

            {/* ---- my preferences ---- */}
            {myMember && <PreferenceForm tripId={id} member={myMember} />}

            {/* ---- proposals ---- */}
            <Card className="p-5">
              <h2 className="mb-1 font-display text-base text-ink dark:text-sand-100">
                Change proposals
              </h2>
              <p className="mb-3 text-xs text-ink-muted dark:text-sand-400">
                On a group trip, a change to the itinerary becomes a proposal. It applies once
                enough members approve.
              </p>
              {proposals.isLoading && <CardSkeleton lines={2} />}
              {proposals.data?.length === 0 && (
                <p className="text-sm text-ink-faint">No proposals yet.</p>
              )}
              <ul className="space-y-3">
                {proposals.data?.map((proposal) => (
                  <ProposalRow key={proposal.id} tripId={id} proposal={proposal} />
                ))}
              </ul>
            </Card>
          </div>

          {/* ---- chat ---- */}
          <aside className="lg:sticky lg:top-24 lg:self-start">
            <ChatPanel tripId={id} messages={messages.data ?? []} loading={messages.isLoading} />
          </aside>
        </div>
      )}
    </PageShell>
  );
}

/* -------------------------------------------------------------------------- */
function PreferenceForm({
  tripId,
  member,
}: {
  tripId: string;
  member: import('@/lib/types').TripMember;
}) {
  const queryClient = useQueryClient();
  const existing = member.preferences;

  const [interests, setInterests] = useState<Record<string, number>>(
    () =>
      (existing?.interests as Record<string, number>) ??
      Object.fromEntries(INTEREST_KEYS.map((k) => [k, 3]))
  );
  const [pace, setPace] = useState(existing?.pace ?? 'balanced');
  const [mobility, setMobility] = useState(existing?.mobility_level ?? 'full');
  const [dietary, setDietary] = useState(existing?.dietary ?? 'any');
  const [start, setStart] = useState(existing?.earliest_start_min ?? 540);
  const [end, setEnd] = useState(existing?.latest_end_min ?? 1200);
  const [isSenior, setIsSenior] = useState(false);
  const [notes, setNotes] = useState(existing?.notes ?? '');

  const save = useMutation({
    mutationFn: () =>
      api.submitPreferences(tripId, {
        interests,
        pace: pace as 'relaxed' | 'balanced' | 'packed',
        mobility_level: mobility as 'full' | 'limited_walking' | 'wheelchair',
        dietary,
        earliest_start_min: start,
        latest_end_min: end,
        is_senior: isSenior,
        notes,
      }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['trip', tripId] }),
  });

  return (
    <Card className="p-5">
      <h2 className="mb-1 font-display text-base text-ink dark:text-sand-100">Your preferences</h2>
      <p className="mb-4 text-xs text-ink-muted dark:text-sand-400">
        Rate each from 0 (not interested) to 5 (really want this).
      </p>

      <div className="space-y-2.5">
        {INTEREST_KEYS.map((key) => (
          <Slider
            key={key}
            label={INTEREST_LABEL[key]}
            value={interests[key] ?? 3}
            onChange={(v) => setInterests((prev) => ({ ...prev, [key]: v }))}
          />
        ))}
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <Field label="Preferred pace" htmlFor="pace">
          <Select id="pace" value={pace} onChange={(e) => setPace(e.target.value as typeof pace)}>
            <option value="relaxed">Relaxed</option>
            <option value="balanced">Balanced</option>
            <option value="packed">Packed</option>
          </Select>
        </Field>
        <Field label="Mobility" htmlFor="mob">
          <Select
            id="mob"
            value={mobility}
            onChange={(e) => setMobility(e.target.value as typeof mobility)}
          >
            <option value="full">No limitations</option>
            <option value="limited_walking">Limited walking</option>
            <option value="wheelchair">Wheelchair user</option>
          </Select>
        </Field>
        <Field label="Dietary" htmlFor="diet">
          <Select id="diet" value={dietary} onChange={(e) => setDietary(e.target.value)}>
            <option value="any">No preference</option>
            <option value="vegetarian">Vegetarian</option>
            <option value="vegan">Vegan</option>
            <option value="jain">Jain</option>
            <option value="halal">Halal</option>
            <option value="no_beef">No beef</option>
          </Select>
        </Field>
        <div className="flex items-end">
          <Toggle
            label="I am a senior traveller"
            checked={isSenior}
            onChange={setIsSenior}
            description="Adds rest breaks and lowers physical intensity."
          />
        </div>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Field label={`Earliest start: ${hhmm(start)}`} htmlFor="es">
          <input
            id="es"
            type="range"
            min={300}
            max={720}
            step={30}
            value={start}
            onChange={(e) => setStart(Number(e.target.value))}
            className="h-2 w-full cursor-pointer appearance-none rounded-full bg-sand-300 accent-indigo-600 dark:bg-white/15"
          />
        </Field>
        <Field label={`Latest end: ${hhmm(end)}`} htmlFor="le">
          <input
            id="le"
            type="range"
            min={900}
            max={1380}
            step={30}
            value={end}
            onChange={(e) => setEnd(Number(e.target.value))}
            className="h-2 w-full cursor-pointer appearance-none rounded-full bg-sand-300 accent-indigo-600 dark:bg-white/15"
          />
        </Field>
      </div>

      <div className="mt-4">
        <Field label="Anything else" htmlFor="notes">
          <Textarea
            id="notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            maxLength={1000}
          />
        </Field>
      </div>

      <div className="mt-4 flex items-center gap-3">
        <Button loading={save.isPending} onClick={() => save.mutate()}>
          Save preferences
        </Button>
        {save.isSuccess && <span className="text-sm text-teal-500">Saved.</span>}
        {save.isError && (
          <span className="text-sm text-clay-500">{(save.error as Error).message}</span>
        )}
      </div>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
function ProposalRow({
  tripId,
  proposal,
}: {
  tripId: string;
  proposal: import('@/lib/types').Proposal;
}) {
  const queryClient = useQueryClient();
  const vote = useMutation({
    mutationFn: (value: 'up' | 'down') =>
      api.vote(tripId, { subject_type: 'proposal', subject_id: proposal.id, value }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['proposals', tripId] });
      void queryClient.invalidateQueries({ queryKey: ['itinerary', tripId] });
    },
  });

  const settled = proposal.status !== 'open';

  return (
    <li>
      <Card className="p-4">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <span className="font-medium text-ink dark:text-sand-200">
            {titleise(proposal.action)}
          </span>
          <Badge
            tone={
              proposal.status === 'applied'
                ? 'teal'
                : proposal.status === 'open'
                  ? 'saffron'
                  : 'neutral'
            }
          >
            {titleise(proposal.status)}
          </Badge>
        </div>
        <p className="text-xs text-ink-muted dark:text-sand-400">
          {proposal.diff?.summary || 'No material change recorded.'}
        </p>
        {proposal.proposed_by && (
          <p className="mt-0.5 text-xs text-ink-faint">
            Proposed by {proposal.proposed_by} · {relativeTime(proposal.created_at)}
          </p>
        )}

        <div className="mt-3">
          <Meter
            value={proposal.approvals / Math.max(1, proposal.required_approvals)}
            tone="teal"
            label="Approvals"
          />
          <p className="mt-1 text-xs text-ink-faint">
            {proposal.approvals} of {proposal.required_approvals} approvals needed
            {proposal.rejections > 0 && ` · ${proposal.rejections} against`}
          </p>
        </div>

        {!settled && (
          <div className="mt-3 flex gap-2">
            <Button size="sm" loading={vote.isPending} onClick={() => vote.mutate('up')}>
              Approve
            </Button>
            <Button
              size="sm"
              variant="ghost"
              loading={vote.isPending}
              onClick={() => vote.mutate('down')}
            >
              Reject
            </Button>
          </div>
        )}
      </Card>
    </li>
  );
}

/* -------------------------------------------------------------------------- */
function ChatPanel({
  tripId,
  messages,
  loading,
}: {
  tripId: string;
  messages: import('@/lib/types').ChatMessage[];
  loading: boolean;
}) {
  const queryClient = useQueryClient();
  const [text, setText] = useState('');
  const endRef = useRef<HTMLDivElement>(null);

  const send = useMutation({
    mutationFn: (body: string) => api.postMessage(tripId, body),
    onSuccess: () => {
      setText('');
      void queryClient.invalidateQueries({ queryKey: ['chat', tripId] });
    },
  });

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  return (
    <Card className="flex h-[32rem] flex-col p-0">
      <header className="border-b border-[rgb(var(--line))] px-4 py-3">
        <h2 className="font-display text-base text-ink dark:text-sand-100">Group chat</h2>
      </header>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {loading && <CardSkeleton lines={2} />}
        {!loading && messages.length === 0 && (
          <p className="py-8 text-center text-sm text-ink-faint">
            No messages yet. Say hello to your group.
          </p>
        )}
        {messages.map((m) =>
          m.kind === 'system' ? (
            <Callout key={m.id} tone="indigo">
              <span className="text-xs">{m.body}</span>
            </Callout>
          ) : (
            <div
              key={m.id}
              className={`flex gap-2 ${m.is_mine ? 'flex-row-reverse text-right' : ''}`}
            >
              <Avatar name={m.author_name} size={28} />
              <div
                className={`max-w-[80%] rounded-2xl px-3 py-2 ${
                  m.is_mine
                    ? 'bg-indigo-600 text-white'
                    : 'bg-[rgb(var(--surface-2))] text-ink dark:text-sand-200'
                }`}
              >
                {!m.is_mine && (
                  <p className="text-[11px] font-semibold opacity-70">{m.author_name}</p>
                )}
                <p className="whitespace-pre-wrap text-sm">{m.body}</p>
                <p className="mt-0.5 text-[10px] opacity-60">{relativeTime(m.created_at)}</p>
              </div>
            </div>
          )
        )}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) send.mutate(text.trim());
        }}
        className="flex gap-2 border-t border-[rgb(var(--line))] p-3"
      >
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Message your group…"
          aria-label="Message"
          maxLength={2000}
        />
        <Button type="submit" size="sm" loading={send.isPending} disabled={!text.trim()}>
          Send
        </Button>
      </form>
    </Card>
  );
}
