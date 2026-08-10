"""Forecast conditions for the treatment date, against the label's limits.

This panel reports and does not judge. The rule engine decides whether the
forecast is compliant; if this panel drew its own conclusions it could
contradict that verdict, so it shows the forecast beside the limit and leaves
the comparison visible instead of asserting it.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui import formatting


def render(weather: dict[str, Any], product: dict[str, Any]) -> None:
    if not weather:
        st.info("No forecast was recorded for this request.")
        return

    st.caption(
        f"Forecast for {weather.get('target_date', 'the treatment date')} at "
        f"{weather.get('latitude')}, {weather.get('longitude')}"
    )

    wind, temperature, precipitation = st.columns(3)

    wind.metric(
        "Wind speed",
        f"{weather.get('wind_speed_mph', '—')} mph",
        border=True,
        help="The label's wind range is the drift control the buffer depends on.",
    )
    wind.caption(f"Label range: {_wind_range(product)}")

    direction = weather.get("wind_direction_deg")
    temperature.metric(
        "Wind direction",
        formatting.compass_point(direction) if direction is not None else "—",
        border=True,
    )
    temperature.caption(
        f"{direction}° · buffer "
        f"{formatting.optional(product.get('downwind_buffer_ft'), ' ft')}"
    )

    precipitation.metric(
        "High temperature",
        f"{weather.get('high_temp_f', '—')} °F",
        border=True,
    )
    precipitation.caption(
        f"Rain probability: {weather.get('precipitation_probability_pct', '—')}%"
    )


def _wind_range(product: dict[str, Any]) -> str:
    low = product.get("wind_min_mph")
    high = product.get("wind_max_mph")
    if low is None and high is None:
        return "No label limit"
    if low is None:
        return f"up to {high} mph"
    if high is None:
        return f"from {low} mph"
    return f"{low}–{high} mph"
