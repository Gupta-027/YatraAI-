/**
 * Typed API client.
 *
 * One place owns the base URL, the auth header, error shape and timeouts, so no
 * component ever calls `fetch` directly. Errors are normalised into `ApiError`
 * so the UI can branch on a stable `code` rather than parsing messages.
 */

import type {
  AskResponse,
  AttractionDetail,
  AttractionSummary,
  ChatMessage,
  ClusterDetail,
  ClusterSummary,
  DashboardMetrics,
  GroupLocation,
  Itinerary,
  ModifyResponse,
  PreferenceInput,
  Proposal,
  QualityReport,
  Recommendation,
  RetrievedChunk,
  ServiceBanner,
  SharingSession,
  TokenResponse,
  Trip,
  User,
  VoteTally,
} from './types';

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, '') || 'http://localhost:8000';

const TOKEN_KEY = 'yatraai.token';
const DEFAULT_TIMEOUT_MS = 45_000;
// Planning runs the optimiser; it legitimately takes longer than a read.
const LONG_TIMEOUT_MS = 120_000;

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: unknown;

  constructor(status: number, code: string, message: string, detail?: unknown) {
    super(message);
    this.name = 'ApiRequestError';
    this.status = status;
    this.code = code;
    this.detail = detail;
  }

  get isAuthError() {
    return this.status === 401 || this.status === 403;
  }
  get isRateLimited() {
    return this.status === 429;
  }
  get isInfeasible() {
    return this.code === 'planning_infeasible';
  }
}

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  if (typeof window === 'undefined') return;
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
    window.dispatchEvent(new Event('yatraai:auth'));
  } catch {
    /* private browsing - the app still works, just without persistence */
  }
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  timeoutMs?: number;
  auth?: boolean;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, timeoutMs = DEFAULT_TIMEOUT_MS, auth = true, headers, ...rest } = options;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const finalHeaders: Record<string, string> = {
    Accept: 'application/json',
    ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    ...((headers as Record<string, string>) ?? {}),
  };
  const token = auth ? getToken() : null;
  if (token) finalHeaders.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...rest,
      headers: finalHeaders,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
      cache: 'no-store',
    });
  } catch (error) {
    clearTimeout(timer);
    if ((error as Error).name === 'AbortError') {
      throw new ApiRequestError(408, 'timeout', 'The request took too long. Please try again.');
    }
    throw new ApiRequestError(
      0,
      'network_error',
      `Cannot reach the API at ${API_BASE}. Is the backend running?`
    );
  }
  clearTimeout(timer);

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { error: { code: 'bad_response', message: text.slice(0, 300) } };
    }
  }

  if (!response.ok) {
    const err = (payload as { error?: { code?: string; message?: string; detail?: unknown } })
      ?.error;
    throw new ApiRequestError(
      response.status,
      err?.code ?? `http_${response.status}`,
      err?.message ?? `Request failed (${response.status})`,
      err?.detail
    );
  }
  return payload as T;
}

/* -------------------------------------------------------------------------- */
/* Endpoints                                                                   */
/* -------------------------------------------------------------------------- */
export const api = {
  // ---- ops ----
  health: () => request<{ status: string; version: string }>('/health', { auth: false }),
  serviceStatus: () =>
    request<ServiceBanner>('/api/v1/auth/service-status', { auth: false }),

  // ---- auth ----
  register: (body: { email: string; password: string; display_name: string; home_city?: string }) =>
    request<TokenResponse>('/api/v1/auth/register', { method: 'POST', body, auth: false }),
  login: (body: { email: string; password: string }) =>
    request<TokenResponse>('/api/v1/auth/login', { method: 'POST', body, auth: false }),
  demoLogin: () =>
    request<TokenResponse>('/api/v1/auth/demo', { auth: false, timeoutMs: LONG_TIMEOUT_MS }),
  me: () => request<User>('/api/v1/auth/me'),

  // ---- destinations ----
  destinations: () => request<ClusterSummary[]>('/api/v1/destinations', { auth: false }),
  destination: (slug: string) =>
    request<ClusterDetail>(`/api/v1/destinations/${slug}`, { auth: false }),
  attractions: (slug: string, params?: Record<string, string | boolean | undefined>) => {
    const query = new URLSearchParams();
    Object.entries(params ?? {}).forEach(([k, v]) => {
      if (v !== undefined && v !== false && v !== '') query.set(k, String(v));
    });
    const qs = query.toString();
    return request<AttractionSummary[]>(
      `/api/v1/destinations/${slug}/attractions${qs ? `?${qs}` : ''}`,
      { auth: false }
    );
  },
  attraction: (clusterSlug: string, attractionSlug: string) =>
    request<AttractionDetail>(
      `/api/v1/destinations/${clusterSlug}/attractions/${attractionSlug}`,
      { auth: false }
    ),

  // ---- trips ----
  createTrip: (body: unknown) =>
    request<Trip>('/api/v1/trips', { method: 'POST', body, timeoutMs: LONG_TIMEOUT_MS }),
  trips: () => request<Trip[]>('/api/v1/trips'),
  trip: (id: string) => request<Trip>(`/api/v1/trips/${id}`),
  updateTrip: (id: string, body: unknown) =>
    request<Trip>(`/api/v1/trips/${id}`, { method: 'PATCH', body }),
  joinTrip: (invite_code: string, display_name?: string) =>
    request<Trip>('/api/v1/trips/join', { method: 'POST', body: { invite_code, display_name } }),
  rotateInvite: (id: string) =>
    request<Trip>(`/api/v1/trips/${id}/invite/rotate`, { method: 'POST' }),
  submitPreferences: (id: string, body: Partial<PreferenceInput>) =>
    request<Trip>(`/api/v1/trips/${id}/preferences`, { method: 'PUT', body }),
  optOut: (id: string) =>
    request<{ ok: boolean; message: string }>(`/api/v1/trips/${id}/opt-out`, { method: 'POST' }),

  // ---- itineraries ----
  generateItinerary: (id: string, body: Record<string, unknown> = {}) =>
    request<Itinerary>(`/api/v1/trips/${id}/itinerary`, {
      method: 'POST',
      body,
      timeoutMs: LONG_TIMEOUT_MS,
    }),
  itinerary: (id: string) => request<Itinerary>(`/api/v1/trips/${id}/itinerary`),
  itineraryVersions: (id: string) => request<Itinerary[]>(`/api/v1/trips/${id}/itinerary/versions`),
  validateItinerary: (id: string) =>
    request<Itinerary['validation']>(`/api/v1/trips/${id}/itinerary/validate`, { method: 'POST' }),
  modifyItinerary: (id: string, body: Record<string, unknown>) =>
    request<ModifyResponse>(`/api/v1/trips/${id}/itinerary/modify`, {
      method: 'POST',
      body,
      timeoutMs: LONG_TIMEOUT_MS,
    }),
  recommendations: (id: string) =>
    request<Recommendation[]>(`/api/v1/trips/${id}/recommendations`),

  // ---- assistant ----
  ask: (body: {
    question: string;
    cluster_slug?: string | null;
    attraction_slug?: string | null;
    top_k?: number;
  }) => request<AskResponse>('/api/v1/assistant/ask', { method: 'POST', body, auth: false }),
  suggestedQuestions: (attractionName?: string) =>
    request<string[]>(
      `/api/v1/assistant/suggested-questions${
        attractionName ? `?attraction_name=${encodeURIComponent(attractionName)}` : ''
      }`,
      { auth: false }
    ),
  whySelected: (tripId: string, slug: string) =>
    request<{ attraction_slug: string; explanation: string; source: string }>(
      `/api/v1/assistant/trips/${tripId}/why/${slug}`
    ),
  /** Raw retrieval with per-arm scores — powers the retrieval inspector. */
  retrieve: (body: {
    question: string;
    cluster_slug?: string | null;
    attraction_slug?: string | null;
    top_k?: number;
  }) =>
    request<RetrievedChunk[]>('/api/v1/assistant/retrieve', {
      method: 'POST',
      body,
      auth: false,
    }),

  // ---- collaboration ----
  vote: (tripId: string, body: Record<string, unknown>) =>
    request<VoteTally>(`/api/v1/trips/${tripId}/votes`, { method: 'POST', body }),
  votes: (tripId: string, subjectType: string, subjectId: string) =>
    request<VoteTally>(
      `/api/v1/trips/${tripId}/votes?subject_type=${subjectType}&subject_id=${subjectId}`
    ),
  proposals: (tripId: string) => request<Proposal[]>(`/api/v1/trips/${tripId}/proposals`),
  applyProposal: (tripId: string, proposalId: string) =>
    request<ModifyResponse>(`/api/v1/trips/${tripId}/proposals/${proposalId}/apply`, {
      method: 'POST',
      timeoutMs: LONG_TIMEOUT_MS,
    }),
  postMessage: (tripId: string, bodyText: string) =>
    request<ChatMessage>(`/api/v1/trips/${tripId}/chat`, {
      method: 'POST',
      body: { body: bodyText },
    }),
  messages: (tripId: string) => request<ChatMessage[]>(`/api/v1/trips/${tripId}/chat`),

  // ---- location ----
  consentText: (tripId: string) =>
    request<{ version: string; text: string; guarantees: string[] }>(
      `/api/v1/trips/${tripId}/location/consent-text`
    ),
  startSharing: (tripId: string, body: Record<string, unknown>) =>
    request<SharingSession>(`/api/v1/trips/${tripId}/location/start`, { method: 'POST', body }),
  setSharingStatus: (tripId: string, status: string) =>
    request<SharingSession>(`/api/v1/trips/${tripId}/location/status`, {
      method: 'POST',
      body: { status },
    }),
  postPoint: (tripId: string, lat: number, lon: number, accuracy_m?: number) =>
    request<{ ok: boolean; message: string }>(`/api/v1/trips/${tripId}/location/point`, {
      method: 'POST',
      body: { lat, lon, accuracy_m },
    }),
  groupLocation: (tripId: string) =>
    request<GroupLocation>(`/api/v1/trips/${tripId}/location/group`),
  stopSharing: (tripId: string) =>
    request<{ ok: boolean; message: string }>(`/api/v1/trips/${tripId}/location`, {
      method: 'DELETE',
    }),
  raiseSos: (tripId: string, message: string) =>
    request<Record<string, unknown>>(`/api/v1/trips/${tripId}/sos`, {
      method: 'POST',
      body: { message, acknowledge_demo: true },
    }),

  // ---- analytics ----
  dashboard: () => request<DashboardMetrics>('/api/v1/analytics/dashboard', { auth: false }),
  attractionStats: () =>
    request<
      {
        attraction_slug: string;
        name: string;
        times_scored: number;
        times_selected: number;
        selection_rate: number;
        average_score: number;
      }[]
    >('/api/v1/analytics/attractions', { auth: false }),
  tripAnalytics: (tripId: string) =>
    request<Record<string, unknown>>(`/api/v1/analytics/trips/${tripId}`),
  feedback: (body: Record<string, unknown>) =>
    request<{ ok: boolean; message: string }>('/api/v1/feedback', { method: 'POST', body }),

  // ---- admin ----
  dataQuality: () => request<QualityReport>('/api/v1/admin/data-quality'),
  coverage: () => request<Record<string, unknown>[]>('/api/v1/admin/coverage'),
  pipelineRuns: () => request<Record<string, unknown>[]>('/api/v1/admin/pipeline-runs'),
  ragEvaluations: () =>
    request<{ runs: Record<string, unknown>[]; note: string }>('/api/v1/admin/rag-evaluations'),
  metrics: () => request<Record<string, unknown>>('/api/v1/metrics', { auth: false }),
};
