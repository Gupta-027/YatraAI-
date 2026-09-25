'use client';

/**
 * Accessible primitives shared across every screen.
 *
 * Deliberately hand-built rather than pulled from a component library: the set
 * is small, the accessibility behaviour is the interesting part, and it keeps
 * the bundle free of a dependency whose API would need explaining anyway.
 */

import Link from 'next/link';
import {
  createContext,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react';

import { cn } from '@/lib/utils';

/* -------------------------------------------------------------------------- */
/* Button                                                                      */
/* -------------------------------------------------------------------------- */
type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'accent';
type ButtonSize = 'sm' | 'md' | 'lg';

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary:
    'bg-indigo-600 text-white hover:bg-indigo-700 active:bg-indigo-800 border border-indigo-600',
  accent:
    'bg-saffron-400 text-white hover:bg-saffron-500 active:bg-saffron-600 border border-saffron-400',
  secondary:
    'bg-[rgb(var(--surface))] text-indigo-600 dark:text-indigo-200 border border-[rgb(var(--line))] hover:bg-sand-200 dark:hover:bg-white/10',
  ghost:
    'bg-transparent text-ink dark:text-sand-100 border border-transparent hover:bg-sand-200/70 dark:hover:bg-white/5',
  danger: 'bg-clay-500 text-white hover:bg-clay-600 border border-clay-500',
};

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: 'text-sm px-3 py-1.5 gap-1.5',
  md: 'text-sm px-4 py-2.5 gap-2',
  lg: 'text-base px-6 py-3 gap-2',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  full?: boolean;
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  full = false,
  className,
  children,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        'inline-flex items-center justify-center rounded-xl font-semibold transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-55',
        BUTTON_VARIANTS[variant],
        BUTTON_SIZES[size],
        full && 'w-full',
        className
      )}
    >
      {loading && <Spinner className="h-4 w-4" />}
      {children}
    </button>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg className={cn('animate-spin', className)} viewBox="0 0 24 24" aria-hidden="true">
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
        fill="none"
      />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      />
    </svg>
  );
}

/* -------------------------------------------------------------------------- */
/* Surfaces                                                                    */
/* -------------------------------------------------------------------------- */
export function Card({
  className,
  children,
  as: Tag = 'div',
  ...props
}: { className?: string; children: ReactNode; as?: 'div' | 'article' | 'section' } & Record<
  string,
  unknown
>) {
  return (
    <Tag
      {...props}
      className={cn('surface rounded-2xl shadow-card', className)}
    >
      {children}
    </Tag>
  );
}

export function SectionHeading({
  title,
  description,
  action,
  level = 2,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  level?: 1 | 2 | 3;
}) {
  const Tag = (`h${level}` as unknown) as 'h2';
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <Tag
          className={cn(
            'font-display text-ink dark:text-sand-100',
            level === 1 ? 'text-3xl sm:text-4xl' : 'text-xl sm:text-2xl'
          )}
        >
          {title}
        </Tag>
        {description && (
          <p className="mt-1 max-w-2xl text-sm text-ink-muted dark:text-sand-400">{description}</p>
        )}
      </div>
      {action}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Badge                                                                       */
/* -------------------------------------------------------------------------- */
type BadgeTone = 'neutral' | 'indigo' | 'saffron' | 'teal' | 'clay';

const BADGE_TONES: Record<BadgeTone, string> = {
  neutral: 'bg-sand-200 text-ink-muted dark:bg-white/10 dark:text-sand-300',
  indigo: 'bg-indigo-50 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-200',
  saffron: 'bg-saffron-50 text-saffron-600 dark:bg-saffron-400/15 dark:text-saffron-200',
  teal: 'bg-teal-50 text-teal-500 dark:bg-teal-400/15 dark:text-teal-200',
  clay: 'bg-clay-400/10 text-clay-600 dark:bg-clay-400/20 dark:text-clay-400',
};

export function Badge({
  tone = 'neutral',
  children,
  className,
  title,
}: {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold',
        BADGE_TONES[tone],
        className
      )}
    >
      {children}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/* Form controls                                                               */
/* -------------------------------------------------------------------------- */
const FIELD_BASE =
  'w-full rounded-xl border border-[rgb(var(--line))] bg-[rgb(var(--surface))] px-3.5 py-2.5 ' +
  'text-sm text-ink dark:text-sand-100 placeholder:text-ink-faint ' +
  'focus:border-indigo-400 disabled:opacity-60';

export function Field({
  label,
  hint,
  error,
  required,
  children,
  htmlFor,
}: {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
  htmlFor?: string;
}) {
  return (
    <div className="space-y-1.5">
      <label
        htmlFor={htmlFor}
        className="block text-sm font-semibold text-ink dark:text-sand-200"
      >
        {label}
        {required && (
          <span className="ml-1 text-saffron-500" aria-hidden="true">
            *
          </span>
        )}
      </label>
      {children}
      {hint && !error && <p className="text-xs text-ink-muted dark:text-sand-400">{hint}</p>}
      {error && (
        <p role="alert" className="text-xs font-medium text-clay-500">
          {error}
        </p>
      )}
    </div>
  );
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cn(FIELD_BASE, className)} />;
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cn(FIELD_BASE, 'min-h-[90px]', className)} />;
}

export function Select({
  className,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...props} className={cn(FIELD_BASE, 'appearance-none pr-9', className)}>
      {children}
    </select>
  );
}

export function Slider({
  label,
  value,
  onChange,
  min = 0,
  max = 5,
  id,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  id?: string;
}) {
  const generated = useId();
  const inputId = id ?? generated;
  return (
    <div className="flex items-center gap-3">
      <label htmlFor={inputId} className="w-48 shrink-0 text-sm text-ink dark:text-sand-200">
        {label}
      </label>
      <input
        id={inputId}
        type="range"
        min={min}
        max={max}
        step={1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-valuetext={`${value} out of ${max}`}
        className="h-2 flex-1 cursor-pointer appearance-none rounded-full bg-sand-300 accent-indigo-600 dark:bg-white/15"
      />
      <output
        htmlFor={inputId}
        className="w-8 text-right text-sm font-semibold tabular-nums text-indigo-600 dark:text-indigo-200"
      >
        {value}
      </output>
    </div>
  );
}

export function Toggle({
  label,
  checked,
  onChange,
  description,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  description?: string;
}) {
  const id = useId();
  return (
    <div className="flex items-start gap-3">
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          'mt-0.5 h-6 w-11 shrink-0 rounded-full border transition-colors',
          checked
            ? 'border-indigo-600 bg-indigo-600'
            : 'border-[rgb(var(--line))] bg-sand-300 dark:bg-white/15'
        )}
      >
        <span
          className={cn(
            'block h-4 w-4 rounded-full bg-white shadow transition-transform',
            checked ? 'translate-x-6' : 'translate-x-1'
          )}
        />
      </button>
      <div>
        <label htmlFor={id} className="cursor-pointer text-sm font-medium text-ink dark:text-sand-200">
          {label}
        </label>
        {description && (
          <p className="text-xs text-ink-muted dark:text-sand-400">{description}</p>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Feedback states                                                             */
/* -------------------------------------------------------------------------- */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn('shimmer rounded-xl bg-sand-200 dark:bg-white/10', className)}
      aria-hidden="true"
    />
  );
}

export function CardSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <Card className="p-5">
      <Skeleton className="mb-3 h-5 w-2/3" />
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={cn('mb-2 h-3', i === lines - 1 ? 'w-1/2' : 'w-full')} />
      ))}
    </Card>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon = '·',
}: {
  title: string;
  description: string;
  action?: ReactNode;
  icon?: string;
}) {
  return (
    <Card className="flex flex-col items-center gap-3 px-6 py-14 text-center">
      <div
        aria-hidden="true"
        className="grid h-12 w-12 place-items-center rounded-2xl bg-sand-200 text-xl font-bold text-indigo-400 dark:bg-white/10"
      >
        {icon}
      </div>
      <h3 className="font-display text-lg text-ink dark:text-sand-100">{title}</h3>
      <p className="max-w-md text-sm text-ink-muted dark:text-sand-400">{description}</p>
      {action}
    </Card>
  );
}

export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <Card className="border-clay-400/40 bg-clay-400/5 p-6" role="alert">
      <h3 className="font-display text-lg text-clay-600 dark:text-clay-400">{title}</h3>
      <p className="mt-1 text-sm text-ink-muted dark:text-sand-300">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-4" onClick={onRetry}>
          Try again
        </Button>
      )}
    </Card>
  );
}

export function Callout({
  tone = 'indigo',
  title,
  children,
}: {
  tone?: 'indigo' | 'saffron' | 'teal' | 'clay';
  title?: string;
  children: ReactNode;
}) {
  const tones = {
    indigo: 'border-indigo-200 bg-indigo-50/60 dark:border-indigo-500/30 dark:bg-indigo-500/10',
    saffron: 'border-saffron-200 bg-saffron-50/70 dark:border-saffron-400/30 dark:bg-saffron-400/10',
    teal: 'border-teal-200 bg-teal-50/70 dark:border-teal-400/30 dark:bg-teal-400/10',
    clay: 'border-clay-400/40 bg-clay-400/8 dark:border-clay-400/30 dark:bg-clay-400/10',
  };
  return (
    <div className={cn('rounded-2xl border p-4 text-sm', tones[tone])}>
      {title && <p className="mb-1 font-semibold text-ink dark:text-sand-100">{title}</p>}
      <div className="text-ink-muted dark:text-sand-300">{children}</div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Drawer (used by the place detail panel)                                     */
/* -------------------------------------------------------------------------- */
export function Drawer({
  open,
  onClose,
  title,
  children,
  width = 'max-w-2xl',
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  width?: string;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      // Focus trap: keep Tab inside the drawer while it is open.
      if (e.key === 'Tab' && panelRef.current) {
        const focusable = panelRef.current.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    panelRef.current?.focus();
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
      previous?.focus();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div
        className="absolute inset-0 bg-ink/40 backdrop-blur-[2px]"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={cn(
          'relative flex h-full w-full flex-col overflow-y-auto bg-[rgb(var(--surface))] shadow-lift',
          'animate-fade-up sm:border-l sm:border-[rgb(var(--line))]',
          width
        )}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between gap-4 border-b border-[rgb(var(--line))] bg-[rgb(var(--surface))]/95 px-5 py-4 backdrop-blur">
          <h2 className="font-display text-lg text-ink dark:text-sand-100">{title}</h2>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close panel">
            Close
          </Button>
        </div>
        <div className="px-5 py-5">{children}</div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Tabs                                                                        */
/* -------------------------------------------------------------------------- */
const TabsContext = createContext<{ value: string; setValue: (v: string) => void } | null>(null);

export function Tabs({
  defaultValue,
  children,
  className,
}: {
  defaultValue: string;
  children: ReactNode;
  className?: string;
}) {
  const [value, setValue] = useState(defaultValue);
  return (
    <TabsContext.Provider value={{ value, setValue }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  );
}

export function TabList({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div
      role="tablist"
      aria-label={label}
      className="mb-4 flex gap-1 overflow-x-auto rounded-xl border border-[rgb(var(--line))] bg-[rgb(var(--surface-2))] p-1"
    >
      {children}
    </div>
  );
}

export function Tab({ value, children }: { value: string; children: ReactNode }) {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error('Tab must be used inside Tabs');
  const active = ctx.value === value;
  return (
    <button
      role="tab"
      type="button"
      aria-selected={active}
      onClick={() => ctx.setValue(value)}
      className={cn(
        'whitespace-nowrap rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors',
        active
          ? 'bg-[rgb(var(--surface))] text-indigo-600 shadow-sm dark:text-indigo-200'
          : 'text-ink-muted hover:text-ink dark:text-sand-400 dark:hover:text-sand-100'
      )}
    >
      {children}
    </button>
  );
}

export function TabPanel({ value, children }: { value: string; children: ReactNode }) {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error('TabPanel must be used inside Tabs');
  if (ctx.value !== value) return null;
  return (
    <div role="tabpanel" className="animate-fade-up">
      {children}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Misc                                                                        */
/* -------------------------------------------------------------------------- */
export function Avatar({ name, size = 32 }: { name: string; size?: number }) {
  const bg = `hsl(${
    Math.abs(name.split('').reduce((a, c) => (a << 5) - a + c.charCodeAt(0), 0)) % 360
  } 45% 42%)`;
  const text = name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join('');
  return (
    <span
      title={name}
      style={{ width: size, height: size, background: bg, fontSize: size * 0.4 }}
      className="inline-grid shrink-0 place-items-center rounded-full font-bold text-white"
    >
      {text}
    </span>
  );
}

export function Meter({
  value,
  label,
  tone = 'indigo',
}: {
  value: number;
  label?: string;
  tone?: 'indigo' | 'teal' | 'saffron' | 'clay';
}) {
  const tones = {
    indigo: 'bg-indigo-500',
    teal: 'bg-teal-400',
    saffron: 'bg-saffron-400',
    clay: 'bg-clay-500',
  };
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="flex items-center gap-2">
      <div
        className="h-1.5 flex-1 overflow-hidden rounded-full bg-sand-300 dark:bg-white/10"
        role="meter"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
      >
        <div className={cn('h-full rounded-full', tones[tone])} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-9 text-right text-xs tabular-nums text-ink-muted dark:text-sand-400">
        {Math.round(pct)}%
      </span>
    </div>
  );
}

export function NavLink({
  href,
  children,
  active,
}: {
  href: string;
  children: ReactNode;
  active?: boolean;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'rounded-lg px-3 py-2 text-sm font-medium transition-colors',
        active
          ? 'bg-indigo-50 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-200'
          : 'text-ink-muted hover:bg-sand-200/70 hover:text-ink dark:text-sand-400 dark:hover:bg-white/5 dark:hover:text-sand-100'
      )}
    >
      {children}
    </Link>
  );
}
