import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { DayTimeline, ScoreBreakdown, ValidationPanel } from '@/components/Itinerary';
import { SolverTrace } from '@/components/Pipeline';
import { Badge, Button, Drawer, EmptyState, Meter, Toggle } from '@/components/ui';
import type { Itinerary, ItineraryDay } from '@/lib/types';

/* -------------------------------------------------------------------------- */
describe('Button', () => {
  it('renders and fires', async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Generate</Button>);
    await userEvent.click(screen.getByRole('button', { name: 'Generate' }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('is disabled and marked busy while loading', () => {
    render(<Button loading>Working</Button>);
    const button = screen.getByRole('button');
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
  });
});

describe('Toggle', () => {
  it('exposes switch semantics for screen readers', async () => {
    const onChange = vi.fn();
    render(<Toggle label="Share location" checked={false} onChange={onChange} />);
    const toggle = screen.getByRole('switch', { name: /share location/i });
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    await userEvent.click(toggle);
    expect(onChange).toHaveBeenCalledWith(true);
  });
});

describe('Meter', () => {
  it('exposes an accessible meter role with a value', () => {
    render(<Meter value={0.42} label="Fairness" />);
    const meter = screen.getByRole('meter', { name: 'Fairness' });
    expect(meter).toHaveAttribute('aria-valuenow', '42');
  });

  it('clamps out-of-range values', () => {
    render(<Meter value={1.8} label="Over" />);
    expect(screen.getByRole('meter', { name: 'Over' })).toHaveAttribute('aria-valuenow', '100');
  });
});

describe('Drawer', () => {
  it('is a modal dialog and closes on Escape', async () => {
    const onClose = vi.fn();
    render(
      <Drawer open onClose={onClose} title="Taj Mahal">
        <p>Body</p>
      </Drawer>
    );
    expect(screen.getByRole('dialog', { name: 'Taj Mahal' })).toHaveAttribute('aria-modal', 'true');
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalled();
  });

  it('renders nothing when closed', () => {
    render(
      <Drawer open={false} onClose={() => {}} title="Hidden">
        <p>Body</p>
      </Drawer>
    );
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});

describe('EmptyState', () => {
  it('explains what to do next', () => {
    render(<EmptyState title="No trips yet" description="Create your first group trip." />);
    expect(screen.getByText('No trips yet')).toBeInTheDocument();
    expect(screen.getByText('Create your first group trip.')).toBeInTheDocument();
  });
});

describe('Badge', () => {
  it('renders its content', () => {
    render(<Badge tone="saffron">Verify</Badge>);
    expect(screen.getByText('Verify')).toBeInTheDocument();
  });
});

/* -------------------------------------------------------------------------- */
const day: ItineraryDay = {
  id: 'day-1',
  day_index: 0,
  calendar_date: '2026-11-10',
  start_min: 540,
  end_min: 1140,
  base_lat: 12.97,
  base_lon: 77.59,
  travel_km: 12.4,
  travel_min: 48,
  weather: { condition: 'clear', temp_min_c: 18, temp_max_c: 28, is_fallback: false },
  weather_advisories: [],
  theme: 'Old city heritage',
  notes: '',
  activities: [
    {
      id: 'a1',
      sequence: 1,
      kind: 'visit',
      title: 'Lalbagh Botanical Garden',
      attraction_slug: 'lalbagh-botanical-garden',
      attraction_id: 'x',
      start_min: 570,
      end_min: 690,
      start_time: '09:30',
      end_time: '11:30',
      duration_min: 120,
      opens_time: '06:00',
      closes_time: '19:00',
      travel_from_prev_min: 18,
      travel_from_prev_km: 4.2,
      travel_mode: 'car',
      lat: 12.95,
      lon: 77.58,
      est_cost_low_inr: 25,
      est_cost_high_inr: 40,
      weather_suitability: 0.92,
      warnings: ['Opening hours change during flower shows - verify before visiting.'],
      why_selected: 'Strong match for your group interest in nature.',
      score_breakdown: { interest_match: 0.72, group_fairness: 0.55, crowd_penalty: 0.25 },
      is_mandatory: false,
      locked: false,
    },
    {
      id: 'a2',
      sequence: 2,
      kind: 'meal',
      title: 'Meal break',
      attraction_slug: null,
      attraction_id: null,
      start_min: 720,
      end_min: 770,
      start_time: '12:00',
      end_time: '12:50',
      duration_min: 50,
      opens_time: null,
      closes_time: null,
      travel_from_prev_min: 5,
      travel_from_prev_km: 0,
      travel_mode: 'car',
      lat: null,
      lon: null,
      est_cost_low_inr: 0,
      est_cost_high_inr: 0,
      weather_suitability: 1,
      warnings: [],
      why_selected: 'A midday break keeps the plan realistic.',
      score_breakdown: {},
      is_mandatory: false,
      locked: false,
    },
  ],
};

describe('DayTimeline', () => {
  it('renders stops with their times', () => {
    render(<DayTimeline day={day} onOpenPlace={() => {}} />);
    expect(screen.getByText('Lalbagh Botanical Garden')).toBeInTheDocument();
    expect(screen.getByText('09:30')).toBeInTheDocument();
    expect(screen.getByText('Meal break')).toBeInTheDocument();
  });

  it('shows travel time between stops', () => {
    render(<DayTimeline day={day} onOpenPlace={() => {}} />);
    expect(screen.getByText(/18 min travel/)).toBeInTheDocument();
  });

  it('surfaces verification warnings rather than hiding them', () => {
    render(<DayTimeline day={day} onOpenPlace={() => {}} />);
    expect(screen.getByText(/verify before visiting/i)).toBeInTheDocument();
  });

  it('reveals the reasoning on demand', async () => {
    render(<DayTimeline day={day} onOpenPlace={() => {}} />);
    expect(screen.queryByText(/Strong match for your group/)).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: /why was this selected/i }));
    expect(screen.getByText(/Strong match for your group/)).toBeInTheDocument();
  });

  it('opens the place drawer when a stop is clicked', async () => {
    const onOpen = vi.fn();
    render(<DayTimeline day={day} onOpenPlace={onOpen} />);
    await userEvent.click(
      screen.getByRole('button', { name: /Lalbagh Botanical Garden.*open details/i })
    );
    expect(onOpen).toHaveBeenCalledWith(
      'lalbagh-botanical-garden',
      'Strong match for your group interest in nature.'
    );
  });

  it('shows both the visit slot and the opening window', () => {
    render(<DayTimeline day={day} onOpenPlace={() => {}} />);
    expect(screen.getByText('09:30')).toBeInTheDocument(); // visit starts
    expect(screen.getByText('11:30')).toBeInTheDocument(); // visit ends
    expect(screen.getByText('06:00–19:00')).toBeInTheDocument(); // place is open
  });

  it('labels recorded hours as unverified', () => {
    render(<DayTimeline day={day} onOpenPlace={() => {}} />);
    expect(screen.getByText(/unverified/)).toBeInTheDocument();
  });

  it('says hours are unrecorded rather than implying all-day opening', () => {
    // The solver substitutes a 00:00-24:00 window internally so it has something
    // to plan against. Rendering that as "Open 00:00-24:00" would turn an absence
    // of data into a confident claim.
    const noHours = {
      ...day,
      activities: [{ ...day.activities[0], opens_time: null, closes_time: null }],
    };
    render(<DayTimeline day={noHours} onOpenPlace={() => {}} />);
    expect(screen.getByText(/Opening hours not recorded/i)).toBeInTheDocument();
    expect(screen.queryByText(/00:00–24:00/)).toBeNull();
  });

  it('does not show opening hours for a meal break', () => {
    const mealOnly = { ...day, activities: [day.activities[1]] };
    render(<DayTimeline day={mealOnly} onOpenPlace={() => {}} />);
    expect(screen.queryByText(/Opening hours not recorded/i)).toBeNull();
  });
});

describe('ScoreBreakdown', () => {
  it('labels components in plain language', () => {
    render(<ScoreBreakdown breakdown={{ interest_match: 0.8, crowd_penalty: 0.3 }} />);
    expect(screen.getByText('Interest match')).toBeInTheDocument();
    expect(screen.getByText('Crowd penalty')).toBeInTheDocument();
  });

  it('says so when there is nothing stored', () => {
    render(<ScoreBreakdown breakdown={{}} />);
    expect(screen.getByText(/no score breakdown/i)).toBeInTheDocument();
  });
});

/* -------------------------------------------------------------------------- */
function makeItinerary(overrides: Partial<Itinerary> = {}): Itinerary {
  return {
    id: 'i1',
    trip_id: 't1',
    version: 1,
    status: 'active',
    generator: 'ortools',
    trigger: 'initial',
    is_valid: true,
    validation: { is_valid: true, checks_run: 66, errors: [], warnings: [] },
    total_travel_km: 42,
    total_travel_min: 120,
    total_visit_min: 480,
    activity_count: 8,
    fairness_score: 0.94,
    least_satisfied_score: 0.61,
    consensus_score: 0.88,
    utility_score: 6.2,
    preference_coverage: {},
    per_member_coverage: {},
    cost: {
      low_inr: 30000,
      high_inr: 42000,
      per_person_low_inr: 10000,
      per_person_high_inr: 14000,
      display: 'Expected cost: ₹10,000 – ₹14,000 per person',
      breakdown: {},
      assumptions: [],
    },
    summary_text: '',
    explanation_source: 'template',
    llm_provider: null,
    degraded_services: [],
    solver_stats: {},
    created_at: '2026-08-01T00:00:00Z',
    days: [],
    ...overrides,
  };
}

describe('ValidationPanel', () => {
  it('reports how many checks ran', () => {
    render(<ValidationPanel itinerary={makeItinerary()} />);
    expect(screen.getByText('Passed')).toBeInTheDocument();
    expect(screen.getByText(/66 constraint checks/)).toBeInTheDocument();
  });

  it('shows errors when validation failed', () => {
    render(
      <ValidationPanel
        itinerary={makeItinerary({
          is_valid: false,
          validation: {
            is_valid: false,
            checks_run: 66,
            errors: [
              {
                code: 'outside_opening_hours',
                severity: 'error',
                message: 'Scheduled while closed.',
                day_index: 0,
                slug: 'x',
              },
            ],
            warnings: [],
          },
        })}
      />
    );
    expect(screen.getByText('Failed')).toBeInTheDocument();
    expect(screen.getByText(/Scheduled while closed/)).toBeInTheDocument();
  });

  it('discloses when fallback data was used', () => {
    render(<ValidationPanel itinerary={makeItinerary({ degraded_services: ['weather'] })} />);
    expect(screen.getByText(/Fallback data was used/i)).toBeInTheDocument();
  });
});

/* -------------------------------------------------------------------------- */
describe('SolverTrace', () => {
  const stats = {
    generator: 'ortools',
    fingerprint: 'abc123def456789012345',
    days: [
      {
        day: 0,
        status: 'OPTIMAL',
        solve_ms: 41.2,
        objective: 8123.5,
        candidates: 9,
        selected: 4,
        relaxations: [],
      },
      {
        day: 1,
        status: 'FEASIBLE',
        solve_ms: 63.8,
        objective: 6440.0,
        candidates: 8,
        selected: 3,
        relaxations: ['reduce_activities'],
      },
    ],
  };

  it('reports each day from the real solve', () => {
    render(<SolverTrace stats={stats} generator="ortools" checksRun={66} />);
    expect(screen.getByText('OPTIMAL')).toBeInTheDocument();
    expect(screen.getByText('FEASIBLE')).toBeInTheDocument();
    expect(screen.getByText('OR-Tools CP-SAT')).toBeInTheDocument();
    expect(screen.getByText('105 ms')).toBeInTheDocument(); // 41.2 + 63.8
  });

  it('says which constraints were relaxed rather than hiding it', () => {
    render(<SolverTrace stats={stats} generator="ortools" checksRun={66} />);
    expect(screen.getByText(/Constraints relaxed on day 2/i)).toBeInTheDocument();
    expect(screen.getByText(/reduce_activities/)).toBeInTheDocument();
  });

  it('renders nothing rather than throwing on malformed solver output', () => {
    // solver_stats is telemetry, not a contract. A diagnostics panel must never be
    // able to take down the itinerary it is describing.
    const { container } = render(
      <SolverTrace
        stats={{ days: [null, 'nonsense', { day: 'x' }] as unknown as unknown[] }}
        generator="ortools"
        checksRun={66}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when there are no stats at all', () => {
    const { container } = render(
      <SolverTrace stats={undefined} generator="ortools" checksRun={0} />
    );
    expect(container).toBeEmptyDOMElement();
  });
});
