'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { PageShell } from '@/components/Shell';
import { Button, Card, Field, Input } from '@/components/ui';
import { useAuth } from '@/lib/auth';

export default function RegisterPage() {
  const router = useRouter();
  const { signUp } = useAuth();

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const passwordTooShort = password.length > 0 && password.length < 8;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < 8) return;
    setBusy(true);
    setError(null);
    try {
      await signUp(email, password, name);
      router.push('/plan');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell className="max-w-md">
      <h1 className="mb-1 font-display text-3xl text-ink dark:text-sand-100">Create an account</h1>
      <p className="mb-6 text-sm text-ink-muted dark:text-sand-400">
        We store your email, display name and a password hash. Nothing else.
      </p>

      <Card className="p-6">
        <form onSubmit={submit} className="space-y-4">
          <Field label="Your name" required htmlFor="name">
            <Input
              id="name"
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={120}
              required
            />
          </Field>
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
          <Field
            label="Password"
            required
            htmlFor="password"
            hint="At least 8 characters. A passphrase is fine — long passwords are not truncated."
            error={passwordTooShort ? 'Passwords must be at least 8 characters.' : undefined}
          >
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={8}
              required
            />
          </Field>

          {error && (
            <p role="alert" className="text-sm text-clay-500">
              {error}
            </p>
          )}

          <Button type="submit" full loading={busy} disabled={password.length < 8}>
            Create account
          </Button>
        </form>
      </Card>

      <p className="mt-4 text-center text-sm text-ink-muted dark:text-sand-400">
        Already have an account?{' '}
        <Link href="/login" className="font-semibold text-indigo-600 hover:underline dark:text-indigo-300">
          Sign in
        </Link>
      </p>
    </PageShell>
  );
}
