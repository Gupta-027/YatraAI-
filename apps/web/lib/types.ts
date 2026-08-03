/**
 * Types mirroring the FastAPI response schemas.
 *
 * These are hand-maintained rather than generated at build time so the frontend
 * has no build-time dependency on a running backend. `npm run typecheck` will
 * catch drift the moment a component uses a field the API does not return, and
 * `scripts/check-openapi-drift.mjs` diffs these against a live /openapi.json.
 */

export interface ClusterSummary {
  id: string;
  slug: string;
  name: string;
  state: string;
  region: string;
  summary: string;
  travel_style: string[];
  center_lat: number;
  center_lon: number;
  best_months: number[];
  avoid_months: number[];
  recommended_days: number;
  intercity_hub: string | null;
  hero_image_url: string | null;
  image_attribution: string | null;
  attraction_count: number;
}

export interface ClusterDetail extends ClusterSummary {
  daily_cost_baseline: Record<string, Record<string, number>>;
  timezone: string;
  categories: string[];
  accessibility_summary: {
    wheelchair_friendly: number;
    indoor_options: number;
    senior_friendly: number;
    child_friendly: number;
    total: number;
  };
}

export interface AttractionSummary {
  id: string;
  slug: string;
  name: string;
  locality: string;
  city: string;
  lat: number;
  lon: number;
  categories: string[];
  summary: string;
  typical_duration_min: number;
  indoor_outdoor: string;
  typical_crowd_level: string;
  wheelchair_accessible: string;
  senior_friendly: number;
  child_friendly: number;
  physical_intensity: number;
  quality_score: number;
  hero_image_url: string | null;
  image_attribution: string | null;
  needs_verification: boolean;
  cluster_slug: string;
}

export interface ScheduleEntry {
  day_of_week: number;
  day_label: string;
  opens: string | null;
  closes: string | null;
  is_closed: boolean;
  season: string;
  note: string;
  verified: boolean;
}

export interface CostEntry {
  visitor_type: string;
  label: string;
  currency: string;
  amount_min: number;
  amount_max: number;
  is_free: boolean;
  note: string;
  verified: boolean;
}

export interface SourceEntry {
  url: string;
  title: string;
  source_type: string;
  covers_fields: string[];
  last_verified_at: string | null;
}

export interface NearbyAttraction {
  slug: string;
  name: string;
  cluster_slug: string;
  distance_km: number | null;
  categories: string[];
}

export interface AttractionDetail extends AttractionSummary {
  history: string;
  significance: string;
  interesting_facts: string[];
  min_duration_min: number;
  max_duration_min: number;
  best_time_of_day: string[];
  suitable_months: number[];
  weather_sensitivity: number;
  crowd_by_time: Record<string, string>;
  accessibility_notes: string;
  dress_code: string;
  photography_policy: string;
  local_customs: string[];
  schedules: ScheduleEntry[];
  costs: CostEntry[];
  sources: SourceEntry[];
  nearby: NearbyAttraction[];
  data_confidence: string;
  verification_note: string;
  last_verified_at: string | null;
  knowledge_topics: string[];
}

export interface User {
  id: string;
  email: string;
  display_name: string;
  home_city: string | null;
  avatar_seed: string;
  is_admin: boolean;
  is_demo: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  user: User;
}

export type Pace = 'relaxed' | 'balanced' | 'packed';
export type TransportMode = 'walk' | 'car' | 'taxi' | 'public' | 'mixed';
export type Mobility = 'full' | 'limited_walking' | 'wheelchair';
export type Tier = 'budget' | 'midrange' | 'premium';

export interface PreferenceInput {
  interests: Record<string, number>;
  ranked_choices: string[];
  pace: Pace;
  budget_sensitivity: number;
  indoor_outdoor_pref: 'indoor' | 'outdoor' | 'mixed';
  dietary: string;
  mobility_level: Mobility;
  max_walk_minutes: number;
  earliest_start_min: number;
  latest_end_min: number;
  must_visit_slugs: string[];
  avoid_slugs: string[];
  is_senior: boolean;
  is_child: boolean;
  notes: string;
}

export interface TripMember {
  id: string;
  display_name: string;
  role: string;
  status: string;
  weight: number;
  joined_at: string | null;
  user_id: string | null;
  preferences: (PreferenceInput & { submitted: boolean }) | null;
}

export interface Trip {
  id: string;
  owner_id: string;
  cluster_id: string;
  title: string;
  start_date: string;
  end_date: string;
  origin_label: string;
  traveller_count: number;
  budget_per_person_inr: number | null;
  budget_total_inr: number | null;
  budget_basis: string;
  pace: Pace;
  transport_mode: TransportMode;
  accommodation_tier: Tier;
  day_start_min: number;
  day_end_min: number;
  has_children: boolean;
  has_seniors: boolean;
  accessibility_required: boolean;
  must_visit_slugs: string[];
  avoid_slugs: string[];
  status: string;
  invite_code: string;
  notes: string;
  created_at: string;
  cluster_slug: string;
  cluster_name: string;
  duration_days: number;
  members: TripMember[];
  preferences_submitted: number;
  has_itinerary: boolean;
}

export interface Activity {
  id: string;
  sequence: number;
  kind: 'visit' | 'meal' | 'rest' | 'transfer';
  title: string;
  attraction_slug: string | null;
  attraction_id: string | null;
  start_min: number;
  end_min: number;
  start_time: string;
  end_time: string;
  duration_min: number;
  /** Opening window this visit sits inside. `null` = the place records no hours. */
  opens_time: string | null;
  closes_time: string | null;
  travel_from_prev_min: number;
  travel_from_prev_km: number;
  travel_mode: string;
  lat: number | null;
  lon: number | null;
  est_cost_low_inr: number;
  est_cost_high_inr: number;
  weather_suitability: number;
  warnings: string[];
  why_selected: string;
  score_breakdown: Record<string, number>;
  is_mandatory: boolean;
  locked: boolean;
}

export interface DayWeather {
  date?: string;
  condition?: string;
  temp_min_c?: number | null;
  temp_max_c?: number | null;
  precipitation_mm?: number | null;
  precipitation_probability?: number | null;
  wind_kph?: number | null;
  visibility_km?: number | null;
  is_fallback?: boolean;
  provider?: string;
}

export interface ItineraryDay {
  id: string;
  day_index: number;
  calendar_date: string;
  start_min: number;
  end_min: number;
  base_lat: number;
  base_lon: number;
  travel_km: number;
  travel_min: number;
  weather: DayWeather;
  weather_advisories: string[];
  theme: string;
  notes: string;
  activities: Activity[];
}

export interface ValidationIssue {
  code: string;
  severity: string;
  message: string;
  day_index: number | null;
  slug: string | null;
}

export interface Itinerary {
  id: string;
  trip_id: string;
  version: number;
  status: string;
  generator: string;
  trigger: string;
  is_valid: boolean;
  validation: {
    is_valid: boolean;
    checks_run: number;
    errors: ValidationIssue[];
    warnings: ValidationIssue[];
  };
  total_travel_km: number;
  total_travel_min: number;
  total_visit_min: number;
  activity_count: number;
  fairness_score: number;
  least_satisfied_score: number;
  consensus_score: number;
  utility_score: number;
  preference_coverage: Record<string, number>;
  per_member_coverage: Record<string, number>;
  cost: {
    low_inr: number;
    high_inr: number;
    per_person_low_inr: number;
    per_person_high_inr: number;
    display: string;
    breakdown: Record<string, { low: number; high: number }>;
    assumptions: string[];
  };
  summary_text: string;
  explanation_source: string;
  llm_provider: string | null;
  degraded_services: string[];
  solver_stats: Record<string, unknown>;
  created_at: string;
  days: ItineraryDay[];
}

export interface Recommendation {
  attraction_slug: string;
  name: string;
  rank: number;
  total_score: number;
  selected: boolean;
  components: Record<string, number>;
  per_member_scores: Record<string, number>;
  eligibility: { eligible?: boolean; reasons?: string[] } & Record<string, unknown>;
  explanation: string;
}

export interface Citation {
  index: number;
  heading: string;
  source_url: string;
  source_type: string;
  attraction_slug: string | null;
  content_category: string;
  last_verified: string | null;
  snippet: string;
}

export interface AskResponse {
  question: string;
  answer: string;
  citations: Citation[];
  abstained: boolean;
  confidence: number;
  topic: string;
  strategy: string;
  provider: string;
  is_fallback: boolean;
  latency_ms: number;
  warnings: string[];
  retrieved_chunk_ids: string[];
}

/** One retrieved chunk with the score each retrieval arm gave it. */
export interface RetrievedChunk {
  chunk_id: string;
  heading: string;
  content_category: string;
  attraction_slug: string | null;
  source_url: string | null;
  dense_score: number;
  lexical_score: number;
  fused_score: number;
  rerank_score: number;
  text: string;
}

export interface ServiceBanner {
  degraded: boolean;
  messages: string[];
  providers: Record<string, Record<string, unknown>>;
}

export interface ModifyResponse {
  applied: boolean;
  itinerary: Itinerary | null;
  diff: {
    added: string[];
    removed: string[];
    moved: { slug: string; from_day: number; to_day: number }[];
    travel_km_delta: number;
    travel_min_delta: number;
    cost_per_person_delta_low: number;
    cost_per_person_delta_high: number;
    fairness_delta: number;
    summary: string;
  };
  validation: Itinerary['validation'];
  requires_group_approval: boolean;
  proposal_id: string | null;
  message: string;
}

export interface VoteTally {
  subject_type: string;
  subject_id: string;
  up: number;
  down: number;
  abstain: number;
  total_members: number;
  my_vote: string | null;
  votes: { member: string; value: string; comment: string; at: string }[];
}

export interface Proposal {
  id: string;
  action: string;
  status: string;
  diff: ModifyResponse['diff'];
  required_approvals: number;
  approvals: number;
  rejections: number;
  created_at: string;
  resolved_at: string | null;
  proposed_by: string | null;
}

export interface ChatMessage {
  id: string;
  author_name: string;
  body: string;
  kind: string;
  meta: Record<string, unknown>;
  created_at: string;
  is_mine: boolean;
}

export interface GroupLocation {
  positions: {
    member_id: string;
    display_name: string;
    lat: number;
    lon: number;
    is_approximate: boolean;
    accuracy_m: number | null;
    recorded_at: string;
    expires_at: string;
    precision: string;
  }[];
  sharing_members: number;
  separation_warning: boolean;
  max_separation_km: number;
  centroid: { lat: number; lon: number } | null;
  suggested_meeting_point: {
    lat: number;
    lon: number;
    label: string;
    reason: string;
  } | null;
  next_activity: {
    title: string;
    slug: string | null;
    lat: number | null;
    lon: number | null;
    date: string;
    start_min: number;
  } | null;
  eta_to_next?: {
    member_id: string;
    display_name: string;
    distance_km: number;
    eta_minutes: number;
  }[];
  per_member_distance_km?: Record<string, number>;
  consent_text: string;
  consent_text_version: string;
}

export interface SharingSession {
  id: string;
  status: string;
  precision: string;
  update_interval_seconds: number;
  consent_granted_at: string;
  consent_text_version: string;
  expires_at: string;
  last_point_at: string | null;
  consent_text: string;
}

export interface DashboardMetrics {
  generated_at: string;
  window_days: number;
  trips: Record<string, number | null>;
  destination_popularity: { cluster_slug: string; name: string; trips: number }[];
  itineraries: Record<string, number>;
  collaboration: Record<string, number>;
  feedback: {
    accepted: number;
    rejected: number;
    acceptance_rate: number;
    average_rating: number | null;
    spend_comparison: {
      samples: number;
      note?: string;
      within_estimated_range?: number;
      mean_absolute_percentage_error?: number | null;
    };
  };
  rag: Record<string, number>;
  providers: Record<string, Record<string, unknown>>;
  data_freshness: Record<string, string | number | null>;
  location_privacy: { sessions_total: number; sessions_active: number; note: string };
}

export interface QualityReport {
  status: string;
  passed: number;
  total: number;
  errors: number;
  warnings: number;
  checks: {
    name: string;
    passed: boolean;
    severity: string;
    detail: string;
    value: unknown;
  }[];
}

export interface ApiError {
  code: string;
  message: string;
  detail?: unknown;
}
