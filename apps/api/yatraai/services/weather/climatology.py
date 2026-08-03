"""Committed monthly climate normals per destination cluster.

These are **seasonal averages, not forecasts**, and every value produced from
them is flagged ``is_fallback=True`` so the UI can say so plainly. They exist so
the planner keeps making weather-aware decisions when Open-Meteo is unreachable,
and so the test suite is deterministic and offline.

Values are approximate long-run monthly normals for each cluster centre:
``(temp_min_c, temp_max_c, precipitation_mm_per_day, precip_probability)``.
"""

from __future__ import annotations

from datetime import date

from yatraai.services.planner.models import DayWeather

# month -> (t_min, t_max, precip_mm_day, precip_probability)
ClimateRow = tuple[float, float, float, float]

CLIMATOLOGY: dict[str, dict[int, ClimateRow]] = {
    "bengaluru": {
        1: (16, 28, 0.1, 0.03),
        2: (17, 31, 0.2, 0.05),
        3: (20, 33, 0.3, 0.07),
        4: (22, 34, 1.6, 0.22),
        5: (21, 33, 3.7, 0.35),
        6: (20, 29, 3.0, 0.40),
        7: (20, 28, 3.3, 0.45),
        8: (20, 28, 4.3, 0.48),
        9: (20, 28, 6.5, 0.50),
        10: (19, 28, 5.6, 0.45),
        11: (17, 27, 2.1, 0.25),
        12: (16, 27, 0.5, 0.10),
    },
    "hyderabad": {
        1: (15, 29, 0.1, 0.03),
        2: (17, 32, 0.2, 0.04),
        3: (21, 36, 0.4, 0.06),
        4: (25, 39, 0.8, 0.10),
        5: (27, 40, 1.0, 0.15),
        6: (24, 34, 3.6, 0.42),
        7: (23, 30, 5.5, 0.55),
        8: (22, 29, 5.7, 0.58),
        9: (22, 30, 5.7, 0.50),
        10: (20, 30, 3.3, 0.32),
        11: (17, 29, 0.8, 0.12),
        12: (14, 28, 0.2, 0.05),
    },
    "delhi-agra": {
        1: (7, 20, 0.7, 0.10),
        2: (10, 24, 0.7, 0.12),
        3: (15, 30, 0.6, 0.10),
        4: (21, 36, 0.4, 0.08),
        5: (26, 40, 0.8, 0.12),
        6: (28, 39, 2.6, 0.30),
        7: (27, 35, 6.9, 0.55),
        8: (26, 33, 8.0, 0.60),
        9: (25, 34, 3.7, 0.35),
        10: (19, 33, 0.4, 0.08),
        11: (12, 28, 0.1, 0.04),
        12: (8, 23, 0.3, 0.06),
    },
    "varanasi": {
        1: (9, 22, 0.7, 0.10),
        2: (12, 26, 0.6, 0.10),
        3: (17, 33, 0.4, 0.08),
        4: (23, 38, 0.3, 0.07),
        5: (27, 40, 0.9, 0.13),
        6: (28, 38, 3.5, 0.35),
        7: (27, 33, 10.0, 0.62),
        8: (27, 32, 9.6, 0.65),
        9: (26, 32, 6.4, 0.45),
        10: (21, 32, 1.5, 0.15),
        11: (14, 29, 0.2, 0.05),
        12: (10, 24, 0.2, 0.05),
    },
    "rishikesh-haridwar": {
        1: (7, 20, 1.5, 0.15),
        2: (9, 23, 1.6, 0.18),
        3: (14, 29, 1.4, 0.16),
        4: (18, 34, 0.8, 0.12),
        5: (22, 37, 1.6, 0.18),
        6: (24, 36, 6.0, 0.42),
        7: (24, 31, 18.0, 0.75),
        8: (24, 30, 17.0, 0.78),
        9: (22, 31, 8.0, 0.50),
        10: (17, 30, 1.2, 0.14),
        11: (11, 26, 0.2, 0.05),
        12: (7, 22, 0.6, 0.09),
    },
    "puri-konark": {
        1: (17, 27, 0.3, 0.06),
        2: (20, 29, 0.7, 0.10),
        3: (23, 31, 0.6, 0.09),
        4: (26, 32, 1.2, 0.15),
        5: (27, 33, 2.7, 0.28),
        6: (26, 32, 7.5, 0.55),
        7: (26, 31, 10.5, 0.68),
        8: (26, 31, 10.0, 0.70),
        9: (26, 31, 8.5, 0.60),
        10: (24, 31, 5.0, 0.40),
        11: (20, 29, 1.0, 0.12),
        12: (17, 27, 0.2, 0.05),
    },
    "shillong-cherrapunji": {
        1: (5, 16, 0.4, 0.08),
        2: (7, 18, 1.4, 0.16),
        3: (11, 22, 4.5, 0.35),
        4: (14, 23, 11.0, 0.55),
        5: (16, 23, 21.0, 0.70),
        6: (18, 23, 45.0, 0.88),
        7: (18, 23, 50.0, 0.92),
        8: (18, 23, 38.0, 0.88),
        9: (17, 23, 22.0, 0.72),
        10: (14, 22, 8.0, 0.45),
        11: (9, 20, 1.2, 0.14),
        12: (6, 17, 0.3, 0.07),
    },
    "gangtok": {
        1: (4, 13, 1.5, 0.18),
        2: (5, 14, 2.5, 0.25),
        3: (9, 18, 5.0, 0.38),
        4: (12, 21, 8.0, 0.48),
        5: (14, 22, 12.0, 0.58),
        6: (16, 22, 20.0, 0.75),
        7: (17, 22, 25.0, 0.82),
        8: (17, 22, 21.0, 0.78),
        9: (16, 22, 14.0, 0.62),
        10: (12, 20, 5.0, 0.35),
        11: (8, 17, 1.0, 0.14),
        12: (5, 14, 0.6, 0.10),
    },
    "meghalaya-jaintia-dawki": {
        1: (8, 21, 0.4, 0.08),
        2: (10, 23, 1.3, 0.15),
        3: (14, 27, 4.0, 0.32),
        4: (17, 28, 10.0, 0.52),
        5: (19, 28, 19.0, 0.68),
        6: (21, 29, 38.0, 0.86),
        7: (21, 29, 42.0, 0.90),
        8: (21, 29, 32.0, 0.86),
        9: (20, 29, 19.0, 0.70),
        10: (17, 27, 7.0, 0.42),
        11: (12, 25, 1.0, 0.13),
        12: (9, 22, 0.3, 0.07),
    },
    "kedarnath": {
        1: (-9, 1, 3.0, 0.35),
        2: (-8, 2, 3.5, 0.38),
        3: (-4, 6, 3.5, 0.36),
        4: (0, 11, 2.5, 0.30),
        5: (3, 14, 2.5, 0.30),
        6: (6, 16, 5.0, 0.45),
        7: (8, 16, 14.0, 0.72),
        8: (8, 16, 13.0, 0.72),
        9: (6, 15, 7.0, 0.50),
        10: (1, 12, 1.5, 0.20),
        11: (-4, 8, 0.6, 0.12),
        12: (-7, 4, 1.8, 0.25),
    },
}

# Used when a cluster is unknown: a neutral, mildly seasonal Indian profile.
DEFAULT_CLIMATE: dict[int, ClimateRow] = {
    1: (14, 27, 0.4, 0.08),
    2: (16, 30, 0.5, 0.09),
    3: (20, 33, 0.6, 0.10),
    4: (24, 36, 0.9, 0.14),
    5: (26, 37, 1.8, 0.22),
    6: (25, 33, 5.0, 0.45),
    7: (24, 31, 8.0, 0.60),
    8: (24, 30, 8.0, 0.62),
    9: (24, 31, 6.0, 0.50),
    10: (21, 31, 2.5, 0.28),
    11: (17, 29, 0.8, 0.12),
    12: (14, 27, 0.4, 0.08),
}


def _condition(precip_mm: float, probability: float, temp_max: float, temp_min: float) -> str:
    if temp_min <= 0 and precip_mm >= 2:
        return "snow"
    if precip_mm >= 20:
        return "heavy_rain"
    if precip_mm >= 5:
        return "rain"
    if probability >= 0.35:
        return "showers"
    if temp_max >= 38:
        return "hot_clear"
    if probability >= 0.15:
        return "partly_cloudy"
    return "clear"


def climatology_for(
    cluster_slug: str, day: date, *, lat: float = 0.0, lon: float = 0.0
) -> DayWeather:
    """Deterministic seasonal-normal weather for one day."""
    table = CLIMATOLOGY.get(cluster_slug, DEFAULT_CLIMATE)
    t_min, t_max, precip, probability = table[day.month]

    # Visibility drops in fog season on the plains and in monsoon cloud in the hills.
    visibility = 12.0
    if precip >= 15:
        visibility = 2.5
    elif precip >= 5:
        visibility = 6.0
    if cluster_slug in {"delhi-agra", "varanasi"} and day.month in (12, 1):
        visibility = 1.8  # north Indian winter fog
    if (
        cluster_slug in {"shillong-cherrapunji", "gangtok", "meghalaya-jaintia-dawki"}
        and precip > 10
    ):
        visibility = 1.5

    return DayWeather(
        calendar_date=day,
        condition=_condition(precip, probability, t_max, t_min),
        temp_min_c=float(t_min),
        temp_max_c=float(t_max),
        precipitation_mm=float(precip),
        precipitation_probability=float(probability),
        wind_kph=12.0,
        visibility_km=visibility,
        is_fallback=True,
        provider="seed-climatology",
    )
