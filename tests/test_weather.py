from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import requests

import data_layer.weather as weather_module
from data_layer.weather import WeatherUnavailable

TODAY = datetime.now(timezone.utc).date()


class FakeResponse:
    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        error: requests.RequestException | None = None,
    ) -> None:
        self.payload = payload or {}
        self.error = error

    def raise_for_status(self) -> None:
        if self.error is not None:
            raise self.error

    def json(self) -> dict[str, Any]:
        return self.payload


def successful_payload() -> dict[str, Any]:
    return {
        "daily": {
            "temperature_2m_max": [82.5],
            "wind_speed_10m_max": [8.25],
            "wind_direction_10m_dominant": [314.6],
            "precipitation_probability_max": [19.6],
        }
    }


def test_get_forecast_maps_response_and_request_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request: dict[str, Any] = {}
    target_date = TODAY + timedelta(days=1)

    def fake_get(url: str, **kwargs: Any) -> FakeResponse:
        request.update({"url": url, **kwargs})
        return FakeResponse(successful_payload())

    monkeypatch.setattr(weather_module.requests, "get", fake_get)

    forecast = weather_module.get_forecast(38.627, -90.1994, target_date)

    assert request["url"] == weather_module.API_URL
    assert request["timeout"] == weather_module.TIMEOUT_SECONDS
    assert request["params"]["latitude"] == 38.627
    assert request["params"]["longitude"] == -90.1994
    assert request["params"]["start_date"] == target_date.isoformat()
    assert request["params"]["end_date"] == target_date.isoformat()
    assert request["params"]["temperature_unit"] == "fahrenheit"
    assert request["params"]["wind_speed_unit"] == "mph"
    assert forecast.high_temp_f == 82.5
    assert forecast.wind_speed_mph == 8.25
    assert forecast.wind_direction_deg == 315
    assert forecast.precipitation_probability_pct == 20


def test_get_forecast_rejects_date_beyond_horizon() -> None:
    target_date = TODAY + timedelta(days=weather_module.FORECAST_HORIZON_DAYS + 1)

    with pytest.raises(WeatherUnavailable, match="No forecast"):
        weather_module.get_forecast(38.627, -90.1994, target_date)


def test_get_forecast_wraps_request_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        weather_module.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(error=requests.Timeout("timed out")),
    )

    with pytest.raises(WeatherUnavailable, match="Open-Meteo request failed"):
        weather_module.get_forecast(38.627, -90.1994, TODAY)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"daily": {"temperature_2m_max": []}},
    ],
)
def test_get_forecast_rejects_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
) -> None:
    monkeypatch.setattr(
        weather_module.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(payload),
    )

    with pytest.raises(WeatherUnavailable, match="Unexpected response"):
        weather_module.get_forecast(38.627, -90.1994, TODAY)


def test_get_forecast_rejects_null_daily_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = successful_payload()
    payload["daily"]["wind_speed_10m_max"] = [None]
    monkeypatch.setattr(
        weather_module.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(payload),
    )

    with pytest.raises(WeatherUnavailable, match="No forecast"):
        weather_module.get_forecast(38.627, -90.1994, TODAY)
