import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Minutes from midnight -> "09:30". */
export function hhmm(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return '--:--';
  const m = Math.max(0, Math.round(minutes));
  return `${String(Math.floor(m / 60) % 24).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}

export function durationLabel(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  if (h && m) return `${h}h ${m}m`;
  if (h) return `${h}h`;
  return `${m}m`;
}

const INR = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
});

export function rupees(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '--';
  return INR.format(Math.round(value));
}

export function rupeeRange(low: number, high: number): string {
  return `${rupees(low)} – ${rupees(high)}`;
}

export function formatDate(iso: string, opts: Intl.DateTimeFormatOptions = {}): string {
  const d = new Date(iso + (iso.length === 10 ? 'T00:00:00' : ''));
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-IN', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    ...opts,
  });
}

export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const diff = Date.now() - then;
  const minutes = Math.round(diff / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

const MONTHS = [
  '',
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

export function monthNames(months: number[]): string {
  if (!months?.length) return 'All year';
  if (months.length === 12) return 'All year';
  return months
    .slice()
    .sort((a, b) => a - b)
    .map((m) => MONTHS[m])
    .join(', ');
}

export function titleise(value: string): string {
  return value
    .replace(/[-_]/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function percent(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`;
}

/** Deterministic pastel from a string - used for member avatars and map pins. */
export function seededColour(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash << 5) - hash + seed.charCodeAt(i);
    hash |= 0;
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue} 55% 45%)`;
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('');
}

export const ACCESS_LABEL: Record<string, string> = {
  yes: 'Step-free access',
  partial: 'Partly accessible',
  no: 'Not wheelchair accessible',
  unknown: 'Access not recorded',
};

export const CROWD_LABEL: Record<string, string> = {
  low: 'Usually quiet',
  medium: 'Moderately busy',
  high: 'Busy',
  very_high: 'Very crowded',
};

export const SCORE_LABEL: Record<string, string> = {
  interest_match: 'Interest match',
  group_fairness: 'Fairness to everyone',
  seasonal_suitability: 'Right season',
  weather_suitability: 'Weather suitability',
  budget_suitability: 'Budget fit',
  distance_penalty: 'Distance penalty',
  crowd_penalty: 'Crowd penalty',
  accessibility_suitability: 'Accessibility',
  attraction_quality: 'Attraction quality',
  evidence_quality: 'Source quality',
  mandatory_bonus: 'Must-visit',
};

export const INTEREST_LABEL: Record<string, string> = {
  heritage: 'History & architecture',
  spiritual: 'Temples & spiritual sites',
  nature: 'Nature & landscapes',
  adventure: 'Adventure & activity',
  food: 'Food & markets',
  shopping: 'Shopping & crafts',
  museums: 'Museums & galleries',
  photography: 'Photography spots',
  relaxation: 'Slow & relaxed',
  wildlife: 'Wildlife & birding',
};

export const INTEREST_KEYS = Object.keys(INTEREST_LABEL);

export function weatherIcon(condition?: string): string {
  if (!condition) return '·';
  if (condition.includes('rain') || condition.includes('shower')) return 'Rain';
  if (condition.includes('snow')) return 'Snow';
  if (condition.includes('thunder')) return 'Storm';
  if (condition.includes('fog')) return 'Fog';
  if (condition.includes('cloud') || condition === 'overcast') return 'Cloud';
  if (condition.includes('hot')) return 'Hot';
  return 'Clear';
}

/**
 * Wikimedia Commons photos (freely licensed) per destination, until the API
 * carries its own `hero_image_url`. Special:FilePath resizes server-side.
 */
const DESTINATION_PHOTOS: Record<string, string> = {
  bengaluru: 'Vidhana_Soudha_2012.jpg',
  'delhi-agra': 'Taj_Mahal_(Edited).jpeg',
  gangtok: 'Kangch-Goechala.jpg',
  hyderabad: 'Charminar_Hyderabad_1.jpg',
  kedarnath: 'Kedarnath_Temple_in_Rainy_season.jpg',
  'meghalaya-jaintia-dawki': 'Umngot_river,_Dawki.jpg',
  'puri-konark': 'Konarka_Temple.jpg',
  'rishikesh-haridwar': 'Rishikesh-Lakshman_Jhula_by_Kaustubh_Nayyar.jpg',
  'shillong-cherrapunji': 'NohKaLikai_Falls_V2_Wiki.jpg',
  varanasi: 'Dasaswamedh_ghat-varanasi_india-andres_larin.jpg',
};

export function destinationImage(slug: string, width = 800, fallback?: string | null): string {
  const file = DESTINATION_PHOTOS[slug] ?? DESTINATION_PHOTOS['delhi-agra'];
  return (
    fallback ||
    `https://commons.wikimedia.org/wiki/Special:FilePath/${encodeURIComponent(file)}?width=${width}`
  );
}
