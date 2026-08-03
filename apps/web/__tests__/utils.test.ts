import { describe, expect, it } from 'vitest';

import {
  durationLabel,
  hhmm,
  initials,
  monthNames,
  percent,
  rupeeRange,
  rupees,
  seededColour,
  titleise,
  weatherIcon,
} from '@/lib/utils';

describe('hhmm', () => {
  it('formats minutes from midnight', () => {
    expect(hhmm(0)).toBe('00:00');
    expect(hhmm(540)).toBe('09:00');
    expect(hhmm(1234)).toBe('20:34');
  });

  it('handles missing values without throwing', () => {
    expect(hhmm(null)).toBe('--:--');
    expect(hhmm(undefined)).toBe('--:--');
  });

  it('wraps past midnight rather than showing hour 25', () => {
    expect(hhmm(1500)).toBe('01:00');
  });
});

describe('durationLabel', () => {
  it('renders hours and minutes', () => {
    expect(durationLabel(90)).toBe('1h 30m');
    expect(durationLabel(120)).toBe('2h');
    expect(durationLabel(45)).toBe('45m');
  });
});

describe('currency', () => {
  it('formats rupees with Indian digit grouping', () => {
    expect(rupees(1250000)).toContain('12,50,000');
  });

  it('renders a range, never a single false-precision figure', () => {
    const range = rupeeRange(18500, 21300);
    expect(range).toContain('18,500');
    expect(range).toContain('21,300');
    expect(range).toContain('–');
  });

  it('handles missing values', () => {
    expect(rupees(null)).toBe('--');
    expect(rupees(undefined)).toBe('--');
  });
});

describe('monthNames', () => {
  it('names the months', () => {
    expect(monthNames([1, 2, 12])).toBe('Jan, Feb, Dec');
  });

  it('collapses a full year', () => {
    expect(monthNames([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])).toBe('All year');
    expect(monthNames([])).toBe('All year');
  });

  it('sorts out-of-order input', () => {
    expect(monthNames([12, 1, 6])).toBe('Jan, Jun, Dec');
  });
});

describe('titleise', () => {
  it('turns slugs into readable labels', () => {
    expect(titleise('taj-mahal')).toBe('Taj Mahal');
    expect(titleise('asi_monument')).toBe('Asi Monument');
  });
});

describe('percent', () => {
  it('formats a 0-1 ratio', () => {
    expect(percent(0.523)).toBe('52%');
    expect(percent(0.523, 1)).toBe('52.3%');
  });
});

describe('seededColour', () => {
  it('is deterministic for the same name', () => {
    expect(seededColour('Asha')).toBe(seededColour('Asha'));
  });

  it('differs between names', () => {
    expect(seededColour('Asha')).not.toBe(seededColour('Ben'));
  });
});

describe('initials', () => {
  it('takes at most two initials', () => {
    expect(initials('Asha Kumari Devi')).toBe('AK');
    expect(initials('Ben')).toBe('B');
  });
});

describe('weatherIcon', () => {
  it('maps conditions to short labels', () => {
    expect(weatherIcon('heavy_rain')).toBe('Rain');
    expect(weatherIcon('clear')).toBe('Clear');
    expect(weatherIcon('thunderstorm')).toBe('Storm');
    expect(weatherIcon(undefined)).toBe('·');
  });
});
