from __future__ import annotations

from datetime import date
import requests
from data_layer.schemas import WeatherForecast

"""Open-Meteo forecast lookup. No API key, no signup.

Label rules are written directly against forecast values, so this output
becomes part of the compliance record.
"""

API_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_SECONDS = 10
FORECAST_HORIZON_DAYS = 16  # Open-Meteo's free-tier limit

_DAILY_VARIABLES = (
    "temperature_2m_max",
    "wind_speed_10m_max",
    "wind_direction_10m_dominant",
    "precipitation_probability_max",
)

class WeatherUnavailable(RuntimeError):
    """The forecast could not be retrieved or was incomplete."""


def get_forecast(latitude: float, longitude: float, target_date: date) -> WeatherForecast:
    """Daily forecast for one point and date.
    Raises WeatherUnavailable on network failure, an error response, or a date
    outside the forecast horizon.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": ",".join(_DAILY_VARIABLES),
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "America/Chicago",
        "start_date": target_date.isoformat(),
        "end_date": target_date.isoformat(),
    }

    try:
        response = requests.get(API_URL, params=params, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        daily = response.json()["daily"]
        values = [daily[name][0] for name in _DAILY_VARIABLES]
    except requests.RequestException as exc:
        raise WeatherUnavailable(f"Open-Meteo request failed: {exc}") from exc
    except (ValueError, KeyError, IndexError) as exc:
        raise WeatherUnavailable(f"Unexpected response from Open-Meteo: {exc}") from exc

    if any(value is None for value in values):
        raise WeatherUnavailable(
            f"No forecast for {target_date}; Open-Meteo covers about "
            f"{FORECAST_HORIZON_DAYS} days ahead."
        )

    high_temp_f, wind_speed_mph, wind_direction, precipitation_pct = values
    return WeatherForecast(
        latitude=latitude,
        longitude=longitude,
        target_date=target_date,
        high_temp_f=high_temp_f,
        wind_speed_mph=wind_speed_mph,
        wind_direction_deg=round(wind_direction),
        precipitation_probability_pct=round(precipitation_pct),
    )
