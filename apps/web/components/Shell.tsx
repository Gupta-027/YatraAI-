'use client';

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';

import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { cn } from '@/lib/utils';

import { Avatar, Badge, Button, NavLink } from './ui';

const NAV = [
  { href: '/destinations', label: 'Destinations' },
  { href: '/trips', label: 'My trips' },
];

/**
 * Honest disclosure banner.
 *
 * When a provider is on its fallback the user is told exactly what that means
 * for the data they are looking at. The product never silently downgrades.
 */
export function ServiceBanner() {
  const { data } = useQuery({
    queryKey: ['service-status'],
    queryFn: api.serviceStatus,
    refetchInterval: 120_000,
    retry: false,
  });
  const [dismissed, setDismissed] = useState(false);

  if (!data?.degraded || dismissed || !data.messages.length) return null;

  return (
    <div
      role="status"
      className="border-b border-saffron-200 bg-saffron-50 dark:border-saffron-400/30 dark:bg-saffron-400/10"
    >
      <div className="mx-auto flex max-w-6xl items-start gap-3 px-4 py-2.5 sm:px-6">
        <Badge tone="saffron" className="mt-0.5 shrink-0">
          Using fallback data
        </Badge>
        <ul className="flex-1 space-y-0.5 text-xs text-ink-muted dark:text-sand-300">
          {data.messages.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
        <button
          onClick={() => setDismissed(true)}
          className="shrink-0 text-xs font-semibold text-saffron-600 hover:underline dark:text-saffron-200"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}

function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem('yatraai.theme');
    const prefers = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const isDark = stored ? stored === 'dark' : prefers;
    setDark(isDark);
    document.documentElement.classList.toggle('dark', isDark);
  }, []);

  return (
    <button
      type="button"
      onClick={() => {
        const next = !dark;
        setDark(next);
        document.documentElement.classList.toggle('dark', next);
        localStorage.setItem('yatraai.theme', next ? 'dark' : 'light');
      }}
      aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}
      className="grid h-9 w-9 place-items-center rounded-full text-base text-ink-muted hover:bg-sand-200/70 dark:text-sand-300 dark:hover:bg-white/5"
    >
      <span aria-hidden="true">{dark ? '☀' : '☾'}</span>
    </button>
  );
}

export function Header() {
  const pathname = usePathname();
  const { user, signOut, loading } = useAuth();
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-[rgb(var(--line))] bg-[rgb(var(--surface))]/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2.5">
          <span
            aria-hidden="true"
            className="grid h-8 w-8 place-items-center rounded-full bg-saffron-400 text-base font-bold text-white"
          >
            ✈
          </span>
          <span className="leading-tight">
            <span className="block font-display text-lg font-semibold tracking-tight text-ink dark:text-sand-100">
              YatraAI
            </span>
            <span className="block text-[11px] text-ink-faint">Built by Gupta Prasad Adhikari</span>
          </span>
        </Link>

        <nav aria-label="Main" className="ml-2 hidden items-center gap-0.5 md:flex">
          {NAV.map((item) => (
            <NavLink key={item.href} href={item.href} active={pathname?.startsWith(item.href)}>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <ThemeToggle />
          {loading ? null : user ? (
            <div className="flex items-center gap-2">
              <span className="flex items-center gap-2 px-2 py-1">
                <Avatar name={user.display_name} size={28} />
                <span className="hidden text-sm font-medium text-ink dark:text-sand-200 sm:inline">
                  {user.display_name}
                </span>
              </span>
              <Button variant="ghost" size="sm" onClick={signOut}>
                Sign out
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Link href="/login">
                <Button variant="ghost" size="sm">
                  Sign in
                </Button>
              </Link>
              <Link href="/plan">
                <Button size="sm">Plan a trip</Button>
              </Link>
            </div>
          )}
          <button
            type="button"
            aria-expanded={open}
            aria-label="Toggle navigation"
            onClick={() => setOpen((v) => !v)}
            className="rounded-lg border border-[rgb(var(--line))] px-2.5 py-2 text-xs font-semibold md:hidden"
          >
            Menu
          </button>
        </div>
      </div>

      {open && (
        <nav aria-label="Mobile" className="border-t border-[rgb(var(--line))] px-4 py-2 md:hidden">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setOpen(false)}
              className={cn(
                'block rounded-lg px-3 py-2.5 text-sm font-medium',
                pathname?.startsWith(item.href)
                  ? 'bg-indigo-50 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-200'
                  : 'text-ink-muted dark:text-sand-400'
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      )}
    </header>
  );
}

export function Footer() {
  return (
    <footer className="mt-16 border-t border-[rgb(var(--line))]">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-6 text-xs text-ink-faint sm:px-6">
        <span>© YatraAI · Simple group itineraries for India</span>
        <span>Opening hours and fees may change, check before you go.</span>
      </div>
    </footer>
  );
}

export function PageShell({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <ServiceBanner />
      <Header />
      <main id="main" className={cn('mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6', className)}>
        {children}
      </main>
      <Footer />
    </div>
  );
}
