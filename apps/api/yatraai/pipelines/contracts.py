"""Pandera schema contracts for the Silver and Gold layers.

These are executable data contracts: the pipeline refuses to promote a dataset
that violates them, and ``tests/data_quality`` runs the same checks in CI so a
bad seed edit fails the build rather than the demo.
"""

from __future__ import annotations

from pandera.pandas import Check, Column, DataFrameSchema

VALID_INDOOR_OUTDOOR = ["indoor", "outdoor", "mixed"]
VALID_CROWD = ["low", "medium", "high", "very_high"]
VALID_ACCESS = ["yes", "partial", "no", "unknown"]
VALID_CONFIDENCE = ["high", "medium", "low"]
VALID_SOURCE_TYPE = ["official", "government", "encyclopedic", "openstreetmap", "editorial"]

# India bounding box - a coordinate outside this is a data-entry error, not a place.
INDIA_LAT = (6.5, 37.5)
INDIA_LON = (68.0, 97.5)


SILVER_CLUSTERS = DataFrameSchema(
    {
        "slug": Column(str, Check.str_matches(r"^[a-z0-9-]+$"), unique=True, nullable=False),
        "name": Column(str, Check.str_length(min_value=2, max_value=160)),
        "state": Column(str, Check.str_length(min_value=2)),
        "region": Column(
            str, Check.isin(["north", "south", "east", "west", "northeast", "central"])
        ),
        "center_lat": Column(float, Check.in_range(*INDIA_LAT)),
        "center_lon": Column(float, Check.in_range(*INDIA_LON)),
        "recommended_days": Column(int, Check.in_range(1, 21)),
        "summary": Column(str, Check.str_length(min_value=40)),
        "n_best_months": Column(int, Check.in_range(0, 12)),
        "n_attractions": Column(int, Check.ge(8), nullable=False),
    },
    strict=False,
    coerce=True,
    name="silver_clusters",
)


SILVER_ATTRACTIONS = DataFrameSchema(
    {
        "cluster_slug": Column(str, Check.str_matches(r"^[a-z0-9-]+$")),
        "slug": Column(str, Check.str_matches(r"^[a-z0-9-]+$")),
        "attraction_key": Column(str, unique=True, nullable=False),
        "name": Column(str, Check.str_length(min_value=2, max_value=200)),
        "city": Column(str, Check.str_length(min_value=2)),
        "lat": Column(float, Check.in_range(*INDIA_LAT)),
        "lon": Column(float, Check.in_range(*INDIA_LON)),
        "n_categories": Column(int, Check.ge(1)),
        "summary": Column(str, Check.str_length(min_value=25, max_value=600)),
        "typical_duration_min": Column(int, Check.in_range(10, 600)),
        "min_duration_min": Column(int, Check.in_range(5, 600)),
        "max_duration_min": Column(int, Check.in_range(10, 900)),
        "indoor_outdoor": Column(str, Check.isin(VALID_INDOOR_OUTDOOR)),
        "weather_sensitivity": Column(float, Check.in_range(0.0, 1.0)),
        "typical_crowd_level": Column(str, Check.isin(VALID_CROWD)),
        "wheelchair_accessible": Column(str, Check.isin(VALID_ACCESS)),
        "senior_friendly": Column(int, Check.in_range(1, 5)),
        "child_friendly": Column(int, Check.in_range(1, 5)),
        "physical_intensity": Column(int, Check.in_range(1, 5)),
        "quality_score": Column(float, Check.in_range(0.0, 1.0)),
        "n_suitable_months": Column(int, Check.in_range(1, 12)),
        "n_sources": Column(int, Check.ge(1), nullable=False),
        "n_facts": Column(int, Check.ge(0)),
        "has_history": Column(bool),
        "has_significance": Column(bool),
        "data_confidence": Column(str, Check.isin(VALID_CONFIDENCE)),
        "last_verified": Column(str, Check.str_matches(r"^\d{4}-\d{2}-\d{2}$"), nullable=True),
    },
    checks=[
        Check(
            lambda df: (
                (df["min_duration_min"] <= df["typical_duration_min"])
                & (df["typical_duration_min"] <= df["max_duration_min"])
            ),
            name="duration_ordering",
            error="min_duration <= typical_duration <= max_duration must hold",
        ),
    ],
    strict=False,
    coerce=True,
    name="silver_attractions",
)


SILVER_SCHEDULES = DataFrameSchema(
    {
        "attraction_key": Column(str, nullable=False),
        "day_of_week": Column(int, Check.in_range(-1, 6)),
        # Nullable integers: a "closed on Mondays" row legitimately has no times.
        "opens_min": Column("Int64", Check.in_range(0, 1440), nullable=True),
        "closes_min": Column("Int64", Check.in_range(0, 1560), nullable=True),
        "is_closed": Column(bool),
        "verified": Column(bool),
    },
    checks=[
        Check(
            lambda df: df["is_closed"] | df["opens_min"].notna(),
            name="open_rows_need_opening_time",
            error="a non-closed schedule row must have an opening time",
        ),
    ],
    strict=False,
    coerce=True,
    name="silver_schedules",
)


SILVER_COSTS = DataFrameSchema(
    {
        "attraction_key": Column(str, nullable=False),
        "visitor_type": Column(str, Check.str_length(min_value=3)),
        "currency": Column(str, Check.isin(["INR"])),
        "amount_min": Column(float, Check.ge(0)),
        "amount_max": Column(float, Check.ge(0)),
        "is_free": Column(bool),
        "verified": Column(bool),
    },
    checks=[
        Check(
            lambda df: df["amount_max"] >= df["amount_min"],
            name="cost_range_ordering",
            error="amount_max must be >= amount_min",
        ),
    ],
    strict=False,
    coerce=True,
    name="silver_costs",
)


SILVER_SOURCES = DataFrameSchema(
    {
        "attraction_key": Column(str, nullable=False),
        "url": Column(str, Check.str_startswith("https://")),
        "domain": Column(str, Check.str_length(min_value=4)),
        "source_type": Column(str, Check.isin(VALID_SOURCE_TYPE)),
        "allowed_domain": Column(bool, Check.eq(True), nullable=False),
    },
    strict=False,
    coerce=True,
    name="silver_sources",
)


GOLD_ATTRACTION_FEATURES = DataFrameSchema(
    {
        "attraction_key": Column(str, unique=True, nullable=False),
        "cluster_slug": Column(str, nullable=False),
        "slug": Column(str, nullable=False),
        "quality_score": Column(float, Check.in_range(0.0, 1.0)),
        "accessibility_score": Column(float, Check.in_range(0.0, 1.0)),
        "family_score": Column(float, Check.in_range(0.0, 1.0)),
        "indoor_score": Column(float, Check.in_range(0.0, 1.0)),
        "crowd_penalty": Column(float, Check.in_range(0.0, 1.0)),
        "cost_index": Column(float, Check.in_range(0.0, 1.0)),
        "evidence_score": Column(float, Check.in_range(0.0, 1.0)),
        "duration_hours": Column(float, Check.in_range(0.1, 10.0)),
        "verification_required": Column(bool),
    }
    | {f"season_score_{m}": Column(float, Check.in_range(0.0, 1.0)) for m in range(1, 13)},
    strict=False,
    coerce=True,
    name="gold_attraction_features",
)


GOLD_CLUSTER_METRICS = DataFrameSchema(
    {
        "cluster_slug": Column(str, unique=True, nullable=False),
        "n_attractions": Column(int, Check.ge(8)),
        "mean_quality": Column(float, Check.in_range(0.0, 1.0)),
        "pct_wheelchair_ok": Column(float, Check.in_range(0.0, 1.0)),
        "pct_indoor": Column(float, Check.in_range(0.0, 1.0)),
        "median_duration_min": Column(float, Check.gt(0)),
        "geo_spread_km": Column(float, Check.ge(0)),
        "pct_needs_verification": Column(float, Check.in_range(0.0, 1.0)),
        "n_categories": Column(int, Check.ge(3)),
    },
    strict=False,
    coerce=True,
    name="gold_cluster_metrics",
)


ALL_SCHEMAS: dict[str, DataFrameSchema] = {
    "silver_clusters": SILVER_CLUSTERS,
    "silver_attractions": SILVER_ATTRACTIONS,
    "silver_schedules": SILVER_SCHEDULES,
    "silver_costs": SILVER_COSTS,
    "silver_sources": SILVER_SOURCES,
    "gold_attraction_features": GOLD_ATTRACTION_FEATURES,
    "gold_cluster_metrics": GOLD_CLUSTER_METRICS,
}


def validate(name: str, df, *, lazy: bool = True):
    """Validate a dataframe against its contract. Raises ``pa.errors.SchemaErrors``."""
    schema = ALL_SCHEMAS[name]
    return schema.validate(df, lazy=lazy)
