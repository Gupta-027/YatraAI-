'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useState } from 'react';

import { PageShell } from '@/components/Shell';
import { Button, Callout, Card, CardSkeleton, Field, Input } from '@/components/ui';
import { useAuth } from '@/lib/auth';

// `useSearchParams` opts the subtree into client-side rendering, so Next.js
// requires an explicit Suspense boundary around it.
export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <PageShell className="max-w-md">
          <CardSkeleton lines={5} />
        </PageShell>
      }
    >
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const next = search.get('next') ?? '/trips';
  const { signIn, signInAsDemo } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<'form' | 'demo' | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy('form');
    setError(null);
    try {
      await signIn(email, password);
      router.push(next);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function demo() {
    setBusy('demo');
    setError(null);
    try {
      await signInAsDemo();
      router.push('/trips');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <PageShell className="max-w-md">
      <h1 className="mb-1 font-display text-3xl text-ink dark:text-sand-100">Sign in</h1>
      <p className="mb-6 text-sm text-ink-muted dark:text-sand-400">
        Sign in to plan trips, submit preferences and collaborate with your group.
      </p>

      <Card className="p-6">
        <form onSubmit={submit} className="space-y-4">
          <Field label="Email" required htmlFor="email">
            <Input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </Field>
          <Field label="Password" required htmlFor="password">
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </Field>

          {error && (
            <p role="alert" className="text-sm text-clay-500">
              {error}
            </p>
          )}

          <Button type="submit" full loading={busy === 'form'}>
            Sign in
          </Button>
        </form>

        <div className="my-5 flex items-center gap-3">
          <span className="h-px flex-1 bg-[rgb(var(--line))]" />
          <span className="text-xs text-ink-faint">or</span>
          <span className="h-px flex-1 bg-[rgb(var(--line))]" />
        </div>

        <Button variant="secondary" full loading={busy === 'demo'} onClick={demo}>
          Open the demo account
        </Button>
        <p className="mt-2 text-center text-xs text-ink-faint">
          A three-member Bengaluru trip with deliberately conflicting preferences.
        </p>
      </Card>

      <p className="mt-4 text-center text-sm text-ink-muted dark:text-sand-400">
        No account?{' '}
        <Link href="/register" className="font-semibold text-indigo-600 hover:underline dark:text-indigo-300">
          Create one
        </Link>
      </p>

      <div className="mt-6">
        <Callout tone="indigo" title="A note on the demo account">
          Demo data is synthetic and clearly labelled as such throughout the product and in
          analytics. It is never presented as real user activity.
        </Callout>
      </div>
    </PageShell>
  );
}
