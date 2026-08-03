# Entity-relationship model

31 tables in five groups. Rendered as Mermaid — GitHub displays this natively.

## Catalogue (the fact layer)

```mermaid
erDiagram
    destination_clusters ||--o{ attractions : contains
    attractions ||--o{ attraction_schedules : "opening hours"
    attractions ||--o{ attraction_costs : "fee bands"
    attractions ||--o{ attraction_sources : provenance

    destination_clusters {
        uuid id PK
        string slug UK
        string name
        string state
        string region
        float center_lat
        float center_lon
        json best_months
        json avoid_months
        int recommended_days
        json daily_cost_baseline
    }
    attractions {
        uuid id PK
        uuid cluster_id FK
        string slug
        float lat
        float lon
        json categories
        text history
        text significance
        json interesting_facts
        int typical_duration_min
        json suitable_months
        string indoor_outdoor
        float weather_sensitivity
        string wheelchair_accessible
        int senior_friendly
        int child_friendly
        int physical_intensity
        float quality_score
        bool needs_verification
        date last_verified_at
    }
    attraction_schedules {
        uuid id PK
        uuid attraction_id FK
        int day_of_week
        int opens_min
        int closes_min
        bool is_closed
        bool verified
    }
    attraction_costs {
        uuid id PK
        uuid attraction_id FK
        string visitor_type
        float amount_min
        float amount_max
        bool is_free
        bool verified
    }
    attraction_sources {
        uuid id PK
        uuid attraction_id FK
        text url
        string source_type
        json covers_fields
        date last_verified_at
    }
```

`UNIQUE (cluster_id, slug)` lets two clusters both have a `fort`.
`verified` on schedules and costs is **always false** in the seed set — a data-quality test
enforces it.

## Trips and collaboration

```mermaid
erDiagram
    users ||--o{ trips : owns
    users ||--o{ trip_members : "is"
    destination_clusters ||--o{ trips : "planned for"
    trips ||--o{ trip_members : has
    trip_members ||--|| member_preferences : submits
    trips ||--o{ votes : on
    trips ||--o{ chat_messages : in
    trips ||--o{ change_proposals : proposes

    users {
        uuid id PK
        string email UK
        string display_name
        text password_hash
        string supabase_user_id UK
        bool is_admin
        bool is_demo
    }
    trips {
        uuid id PK
        uuid owner_id FK
        uuid cluster_id FK
        date start_date
        date end_date
        int traveller_count
        float budget_per_person_inr
        string pace
        string transport_mode
        int day_start_min
        int day_end_min
        bool accessibility_required
        json must_visit_slugs
        json avoid_slugs
        string invite_code UK
    }
    trip_members {
        uuid id PK
        uuid trip_id FK
        uuid user_id FK
        string role
        string status
        float weight
    }
    member_preferences {
        uuid id PK
        uuid member_id FK,UK
        json interests
        json ranked_choices
        string mobility_level
        int earliest_start_min
        int latest_end_min
        bool submitted
    }
    votes {
        uuid id PK
        uuid trip_id FK
        uuid member_id FK
        string subject_type
        string subject_id
        string value
    }
    change_proposals {
        uuid id PK
        uuid trip_id FK
        uuid itinerary_id FK
        string action
        json diff
        uuid candidate_itinerary_id
        int required_approvals
        string status
    }
```

`UNIQUE (member_id, subject_type, subject_id)` on votes makes one-member-one-vote a schema
guarantee rather than application logic.

## Itineraries

```mermaid
erDiagram
    trips ||--o{ itineraries : generates
    itineraries ||--o{ itinerary_days : has
    itinerary_days ||--o{ itinerary_activities : contains
    trips ||--o{ recommendation_scores : ranks
    attractions ||--o{ itinerary_activities : "scheduled as"
    itineraries ||--o{ feedback : receives

    itineraries {
        uuid id PK
        uuid trip_id FK
        int version
        uuid parent_itinerary_id
        string status
        string generator
        string trigger
        bool is_valid
        json validation_report
        float total_travel_km
        float fairness_score
        float least_satisfied_score
        float consensus_score
        float cost_per_person_low_inr
        float cost_per_person_high_inr
        text summary_text
        string explanation_source
        json degraded_services
        json solver_stats
        string input_fingerprint
    }
    itinerary_days {
        uuid id PK
        uuid itinerary_id FK
        int day_index
        date calendar_date
        float base_lat
        float base_lon
        float travel_km
        json weather
        json weather_advisories
    }
    itinerary_activities {
        uuid id PK
        uuid day_id FK
        int sequence
        string kind
        uuid attraction_id FK
        int start_min
        int end_min
        int travel_from_prev_min
        float weather_suitability
        json warnings
        text why_selected
        json score_breakdown
        bool is_mandatory
    }
    recommendation_scores {
        uuid id PK
        uuid trip_id FK
        uuid attraction_id FK
        string method
        float total_score
        int rank
        bool selected
        json components
        json per_member_scores
        json eligibility
        text explanation
    }
```

`UNIQUE (trip_id, version)` gives an append-only version history — a modification supersedes
rather than mutates, which is what makes the trip-analytics timeline possible.

## Knowledge base

```mermaid
erDiagram
    source_documents ||--o{ document_chunks : "chunked into"
    document_chunks ||--|| chunk_embeddings : embedded

    source_documents {
        uuid id PK
        string doc_key UK
        string cluster_slug
        string attraction_slug
        string content_category
        text body
        text source_url
        string source_type
        date last_verified_at
        bool time_sensitive
        string content_hash
    }
    document_chunks {
        uuid id PK
        uuid document_id FK
        int chunk_index
        string heading
        text text
        string cluster_slug
        string attraction_slug
        string content_category
        text source_url
        json keywords
        string content_hash
    }
    chunk_embeddings {
        uuid id PK
        uuid chunk_id FK,UK
        string provider
        string model
        int dim
        vector vector
    }
    rag_evaluations {
        uuid id PK
        string run_id
        string question_id
        float retrieval_precision
        float faithfulness
        float citation_correctness
        float answer_completeness
        bool abstained
        float latency_ms
    }
```

Cluster, attraction and category are **denormalised onto chunks** so metadata filtering needs no
join on the hot retrieval path.

## Location and operations

```mermaid
erDiagram
    trips ||--o{ location_sharing_sessions : "consented in"
    location_sharing_sessions ||--o{ location_points : records
    trips ||--o{ sos_alerts : "demo only"

    location_sharing_sessions {
        uuid id PK
        uuid trip_id FK
        uuid member_id FK
        string status
        string precision
        int update_interval_seconds
        datetime consent_granted_at
        string consent_text_version
        datetime expires_at
        datetime stopped_at
    }
    location_points {
        uuid id PK
        uuid session_id FK
        float lat
        float lon
        bool is_approximate
        datetime recorded_at
        datetime expires_at
    }
    weather_snapshots {
        uuid id PK
        string cluster_slug
        date target_date
        string provider
        bool is_fallback
    }
    route_cache {
        uuid id PK
        string cache_key UK
        float distance_km
        float duration_min
        bool is_fallback
        int hits
    }
    pipeline_runs {
        uuid id PK
        string pipeline
        string layer
        string run_key
        int rows_in
        int rows_out
        int rows_rejected
        json checks
    }
    model_runs {
        uuid id PK
        string run_id UK
        string experiment
        string data_kind
        json params
        json metrics
    }
    audit_logs {
        uuid id PK
        uuid actor_user_id
        string action
        string entity_type
        uuid trip_id
        string request_id
        json detail
    }
    analytics_events {
        uuid id PK
        string event
        uuid trip_id
        string cluster_slug
        float numeric_value
        json properties
    }
```

Two schema-level privacy guarantees: every session carries `expires_at`, and every point carries
its own `expires_at`. There is no table capable of holding permanent location history.

`model_runs.data_kind` records `synthetic | real | mixed` so an ML result can never be mistaken
for one trained on genuine labels.

## Constraints worth noting

| Constraint | Prevents |
|---|---|
| `attraction_lat_range`, `attraction_lon_range` | Impossible coordinates |
| `attraction_duration_positive` | Zero-length visits |
| `trip_date_order` | End before start |
| `trip_day_window` | Day ending before it starts |
| `cost_range_valid` | `max < min` |
| `activity_time_order` | Non-positive activity duration |
| `loc_interval_min` (≥ 15 s) | Location polling abuse |
| `uq_vote_member_subject` | Double voting |
| `uq_attraction_cluster_slug` | Duplicate attractions in a cluster |
| `uq_itinerary_trip_version` | Version collisions |
