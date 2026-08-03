"""Canonical interest taxonomy and the category -> interest mapping.

Members express preferences over ~10 stable interest dimensions rather than over
the ~60 free-form category tags in the catalogue. That separation matters: new
attractions can introduce new tags without invalidating every stored preference
profile, and the aggregation maths operates on a fixed-width vector.
"""

from __future__ import annotations

from typing import Final

INTERESTS: Final[tuple[str, ...]] = (
    "heritage",
    "spiritual",
    "nature",
    "adventure",
    "food",
    "shopping",
    "museums",
    "photography",
    "relaxation",
    "wildlife",
)

INTEREST_LABELS: Final[dict[str, str]] = {
    "heritage": "History & architecture",
    "spiritual": "Temples & spiritual sites",
    "nature": "Nature & landscapes",
    "adventure": "Adventure & activity",
    "food": "Food & markets",
    "shopping": "Shopping & crafts",
    "museums": "Museums & galleries",
    "photography": "Photography spots",
    "relaxation": "Slow & relaxed",
    "wildlife": "Wildlife & birding",
}

# A category may contribute to several interests with different strengths.
CATEGORY_TO_INTERESTS: Final[dict[str, dict[str, float]]] = {
    # --- built heritage ---
    "heritage": {"heritage": 1.0, "photography": 0.4},
    "unesco": {"heritage": 1.0, "photography": 0.6},
    "asi-monument": {"heritage": 1.0},
    "architecture": {"heritage": 0.9, "photography": 0.6},
    "fort": {"heritage": 1.0, "photography": 0.5, "adventure": 0.3},
    "palace": {"heritage": 1.0, "photography": 0.5},
    "history": {"heritage": 1.0},
    "memorial": {"heritage": 0.7, "relaxation": 0.3},
    "landmark": {"heritage": 0.6, "photography": 0.8},
    "winter-seat": {"heritage": 0.5, "spiritual": 0.8},
    # --- spiritual ---
    "spiritual": {"spiritual": 1.0},
    "temple": {"spiritual": 1.0, "heritage": 0.5},
    "mosque": {"spiritual": 1.0, "heritage": 0.6},
    "monastery": {"spiritual": 1.0, "heritage": 0.5, "photography": 0.4},
    "buddhist": {"spiritual": 0.9, "heritage": 0.6},
    "jain": {"spiritual": 0.9, "heritage": 0.6},
    "pilgrimage": {"spiritual": 1.0},
    "ritual": {"spiritual": 0.9, "photography": 0.5},
    # --- nature ---
    "nature": {"nature": 1.0},
    "garden": {"nature": 0.9, "relaxation": 0.7},
    "lake": {"nature": 0.9, "relaxation": 0.6, "photography": 0.5},
    "river": {"nature": 0.9, "photography": 0.5},
    "waterfall": {"nature": 1.0, "photography": 0.8},
    "viewpoint": {"nature": 0.8, "photography": 1.0},
    "beach": {"nature": 0.8, "relaxation": 0.9},
    "forest": {"nature": 1.0, "wildlife": 0.5},
    "hot-spring": {"nature": 0.7, "relaxation": 0.8},
    "high-altitude": {"nature": 0.9, "adventure": 0.7},
    "mountain": {"nature": 0.9, "adventure": 0.6, "photography": 0.5},
    "cave": {"nature": 0.7, "adventure": 0.8},
    "outdoor": {"nature": 0.6},
    "sunrise": {"photography": 0.9, "nature": 0.6},
    # --- adventure ---
    "adventure": {"adventure": 1.0},
    "trek": {"adventure": 1.0, "nature": 0.8},
    "activity": {"adventure": 0.9},
    "water": {"adventure": 0.8, "nature": 0.5},
    "swimming": {"adventure": 0.6, "relaxation": 0.6},
    "camping": {"adventure": 0.8, "nature": 0.7},
    "expert": {"adventure": 1.0},
    "base-camp": {"adventure": 0.6},
    # --- food & shopping ---
    "food": {"food": 1.0},
    "market": {"shopping": 0.9, "food": 0.6, "photography": 0.4},
    "shopping": {"shopping": 1.0},
    "urban": {"food": 0.4, "shopping": 0.5},
    # --- museums & culture ---
    "museum": {"museums": 1.0, "heritage": 0.5},
    "art": {"museums": 0.9, "heritage": 0.3},
    "science": {"museums": 0.9},
    "cultural": {"museums": 0.5, "heritage": 0.6},
    "research": {"museums": 0.7},
    "aviation": {"museums": 0.8},
    "entertainment": {"relaxation": 0.6, "museums": 0.2},
    "village": {"nature": 0.4, "photography": 0.4, "relaxation": 0.4},
    "unique": {"photography": 0.5, "heritage": 0.3},
    "offbeat": {"nature": 0.4, "adventure": 0.4},
    "hidden-gem": {"heritage": 0.5, "photography": 0.4},
    # --- other ---
    "wildlife": {"wildlife": 1.0, "nature": 0.7},
    "birding": {"wildlife": 1.0, "nature": 0.6},
    "safari": {"wildlife": 1.0, "adventure": 0.5},
    "photo-spot": {"photography": 1.0},
    "family": {"relaxation": 0.4},
    "modern": {"photography": 0.3},
    "free": {},
    "day-trip": {},
    "indoor": {},
    "border": {"photography": 0.3},
    "permit-required": {},
    "boating": {"adventure": 0.5, "relaxation": 0.5, "nature": 0.4},
}


def interest_vector(categories: list[str]) -> dict[str, float]:
    """Map catalogue category tags to a normalised interest vector in [0,1]."""
    vector = dict.fromkeys(INTERESTS, 0.0)
    for category in categories or []:
        for interest, weight in CATEGORY_TO_INTERESTS.get(category, {}).items():
            if interest in vector:
                vector[interest] = max(vector[interest], weight)
    return vector


def default_preferences() -> dict[str, int]:
    """A neutral profile: everything mildly interesting (3 on a 0-5 scale)."""
    return dict.fromkeys(INTERESTS, 3)


def normalise_preferences(raw: dict | None) -> dict[str, float]:
    """Clamp a submitted preference dict to ``{interest: 0..5}`` floats."""
    out = {}
    source = raw or {}
    for interest in INTERESTS:
        try:
            value = float(source.get(interest, 3))
        except (TypeError, ValueError):
            value = 3.0
        out[interest] = max(0.0, min(5.0, value))
    return out
