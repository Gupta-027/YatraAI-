"""Weather provider abstraction with an always-available climatology fallback.

``OpenMeteoProvider`` is the default live source (no API key, generous free
tier). ``SeedClimatologyProvider`` replays committed monthly normals so the
planner still produces weather-aware itineraries with no network at all - the
demo degrades in quality, never in function, and says so.
"""

from __future__ import annotations

import functools
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import date, timedelta

import httpx

from yatraai.config import get_settings
from yatraai.core.telemetry import track
from yatraai.logging_config import get_logger
from yatraai.services.planner.models import DayWeather
from yatraai.services.weather.climatology import climatology_for

log = get_logger(__name__)

# Open-Meteo WMO weather interpretation codes -> our condition vocabulary.
WMO_CONDITIONS: dict[int, str] = {
    0: "clear",
    1: "mostly_clear",
    2: "partly_cloudy",
    3: "overcast",
    45: "fog",
    48: "fog",
    51: "drizzle",
    53: "drizzle",
    55: "drizzle",
    61: "rain",
    63: "rain",
    65: "heavy_rain",
    66: "freezing_rain",
    67: "freezing_rain",
    71: "snow",
    73: "snow",
    75: "heavy_snow",
    77: "snow",
    80: "showers",
    81: "showers",
    82: "heavy_showers",
    85: "snow_showers",
    86: "snow_showers",
    95: "thunderstorm",
    96: "thunderstorm",
    99: "thunderstorm",
}


class WeatherProvider(ABC):
    name: str = "base"
    is_fallback: bool = False

    @abstractmethod
    def daily_forecast(
        self, lat: float, lon: float, start: date, end: date, cluster_slug: str = ""
    ) -> list[DayWeather]: ...


class SeedClimatologyProvider(WeatherProvider):
    """Committed monthly normals per cluster. Offline, deterministic, honest."""

    name = "seed"
    is_fallback = True

    def daily_forecast(
        self, lat: float, lon: float, start: date, end: date, cluster_slug: str = ""
    ) -> list[DayWeather]:
        with track("weather", self.name, "daily_forecast") as state:
            state["fallback_used"] = True
            days = (end - start).days + 1
            out = []
            for i in range(max(1, days)):
                day = start + timedelta(days=i)
                out.append(climatology_for(cluster_slug, day, lat=lat, lon=lon))
            return out


class OpenMeteoProvider(WeatherProvider):
    """Open-Meteo daily forecast. Falls back to climatology on any failure."""

    name = "open-meteo"

    def __init__(self, base_url: str, timeout: float = 8.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._fallback = SeedClimatologyProvider()

    def daily_forecast(
        self, lat: float, lon: float, start: date, end: date, cluster_slug: str = ""
    ) -> list[DayWeather]:
        today = date.today()
        # Open-Meteo forecasts ~16 days ahead; beyond that only climatology exists.
        if start > today + timedelta(days=15):
            log.info("weather.beyond_forecast_horizon", start=str(start))
            return self._fallback.daily_forecast(lat, lon, start, end, cluster_slug)

        params = {
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "daily": ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_sum",
                    "precipitation_probability_max",
                    "wind_speed_10m_max",
                ]
            ),
            "timezone": "Asia/Kolkata",
            "start_date": start.isoformat(),
            "end_date": min(end, today + timedelta(days=15)).isoformat(),
        }

        with track("weather", self.name, "daily_forecast") as state:
            try:
                response = httpx.get(
                    f"{self.base_url}/forecast", params=params, timeout=self.timeout
                )
                response.raise_for_status()
                payload = response.json()
                daily = payload["daily"]
                out: list[DayWeather] = []
                for i, iso in enumerate(daily["time"]):
                    code = daily["weather_code"][i]
                    out.append(
                        DayWeather(
                            calendar_date=date.fromisoformat(iso),
                            condition=WMO_CONDITIONS.get(int(code or 0), "unknown"),
                            temp_max_c=daily["temperature_2m_max"][i],
                            temp_min_c=daily["temperature_2m_min"][i],
                            precipitation_mm=daily["precipitation_sum"][i],
                            precipitation_probability=(
                                (daily["precipitation_probability_max"][i] or 0) / 100.0
                            ),
                            wind_kph=daily["wind_speed_10m_max"][i],
                            visibility_km=None,
                            is_fallback=False,
                            provider=self.name,
                        )
                    )
                # Pad any days past the forecast horizon with climatology.
                if out and out[-1].calendar_date < end:
                    out.extend(
                        self._fallback.daily_forecast(
                            lat, lon, out[-1].calendar_date + timedelta(days=1), end, cluster_slug
                        )
                    )
                return out
            except Exception as exc:
                state["fallback_used"] = True
                state["ok"] = False
                state["error_kind"] = type(exc).__name__
                log.warning("weather.openmeteo_failed", error=str(exc))
                return self._fallback.daily_forecast(lat, lon, start, end, cluster_slug)


@functools.lru_cache(maxsize=1)
def get_weather_provider() -> WeatherProvider:
    s = get_settings()
    if s.weather_provider == "open-meteo":
        return OpenMeteoProvider(s.open_meteo_base_url, 8.0)
    return SeedClimatologyProvider()


def reset_weather_cache() -> None:
    get_weather_provider.cache_clear()


def advisories_for(weather: DayWeather, cluster_slug: str = "") -> list[str]:
    """Plain-language warnings shown on the itinerary day header."""
    messages: list[str] = []
    if weather.is_wet:
        mm = weather.precipitation_mm or 0
        messages.append(
            f"Rain expected ({mm:.0f} mm). Outdoor stops were down-weighted and "
            "indoor alternatives preferred."
        )
    if weather.is_hot:
        messages.append(
            f"High of {weather.temp_max_c:.0f} degrees C. Outdoor visits were moved away "
            "from the midday window."
        )
    if weather.is_cold:
        messages.append(
            f"Low of {weather.temp_min_c:.0f} degrees C. Carry proper cold-weather layers."
        )
    if weather.is_low_visibility:
        messages.append("Poor visibility expected - viewpoints may show nothing.")
    if (weather.wind_kph or 0) > 45:
        messages.append("Strong winds - boating and ropeways may be suspended.")
    if cluster_slug in {"gangtok", "kedarnath", "shillong-cherrapunji"} and weather.is_wet:
        messages.append(
            "Mountain roads in this region close at short notice after heavy rain. "
            "Confirm road status locally before setting out."
        )
    if weather.is_fallback:
        messages.append(
            "Live forecast unavailable - these figures are seasonal averages, not a forecast."
        )
    return messages


def summarise(weather: Sequence[DayWeather]) -> dict:
    if not weather:
        return {}
    return {
        "days": len(weather),
        "any_fallback": any(w.is_fallback for w in weather),
        "wet_days": sum(1 for w in weather if w.is_wet),
        "hot_days": sum(1 for w in weather if w.is_hot),
        "provider": weather[0].provider,
    }
