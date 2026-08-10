"""The field and product records the plan was built from.

Like the conditions panel, this reports rather than judges: it puts the field's
recorded state next to the label's limits so a reviewer can see what the rule
engine was working with.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui import formatting


def render(
    field: dict[str, Any],
    product: dict[str, Any],
    history: list[dict[str, Any]],
    plan: dict[str, Any],
) -> None:
    field_column, product_column = st.columns(2)

    with field_column:
        st.markdown("**Field record**")
        if field:
            _rows(
                (
                    ("Name", f"{field.get('name', '—')} ({field.get('id', '—')})"),
                    ("Crop", field.get("crop", "—")),
                    ("Recorded area", f"{field.get('acres', '—')} acres"),
                    ("Growth stage", field.get("growth_stage", "—")),
                    ("Trait package", _trait(field.get("trait_package"))),
                    ("Expected harvest", field.get("expected_harvest_date", "—")),
                    (
                        "Distance to sensitive site",
                        f"{field.get('feet_to_sensitive_site', '—')} ft",
                    ),
                )
            )
        else:
            st.caption("No field record was loaded.")

    with product_column:
        st.markdown("**Label limits**")
        if product:
            _rows(
                (
                    ("Product", product.get("name", "—")),
                    ("EPA registration", product.get("epa_reg_no", "—")),
                    (
                        "Allowed traits",
                        _traits(product.get("allowed_traits")),
                    ),
                    ("Growth-stage window", _stage_window(product)),
                    (
                        "Maximum rate",
                        formatting.optional(
                            product.get("max_rate_fl_oz_per_acre"), " fl oz/acre"
                        ),
                    ),
                    (
                        "Seasonal maximum",
                        formatting.optional(
                            product.get("max_seasonal_fl_oz_per_acre"), " fl oz/acre"
                        ),
                    ),
                    (
                        "Applications per season",
                        formatting.optional(product.get("max_applications_per_season")),
                    ),
                    (
                        "Restricted-entry interval",
                        formatting.optional(product.get("rei_hours"), " hours"),
                    ),
                    (
                        "Pre-harvest interval",
                        formatting.optional(product.get("phi_days"), " days"),
                    ),
                )
            )
        else:
            st.caption("No product record was loaded.")

    st.markdown("**Application history this season**")
    _render_history(history, product, plan)


def _render_history(
    history: list[dict[str, Any]],
    product: dict[str, Any],
    plan: dict[str, Any],
) -> None:
    if not history:
        st.caption("No prior applications are recorded for this field.")
        return

    st.dataframe(
        [
            {
                "Applied": entry.get("applied_on"),
                "Product": entry.get("product"),
                "Rate (fl oz/acre)": entry.get("rate_fl_oz_per_acre"),
            }
            for entry in history
        ],
        hide_index=True,
        width="stretch",
    )

    product_name = plan.get("product_name") or product.get("name")
    if not product_name:
        return

    applied = [
        entry.get("rate_fl_oz_per_acre") or 0
        for entry in history
        if entry.get("product") == product_name
    ]
    if not applied:
        return

    seasonal_cap = product.get("max_seasonal_fl_oz_per_acre")
    total = sum(applied)
    proposed = plan.get("proposed_rate") or 0
    line = (
        f"Already applied for {product_name}: **{total:g} fl oz/acre** "
        f"across {len(applied)} application(s). "
        f"With the proposed {proposed:g} fl oz/acre the season would reach "
        f"**{total + proposed:g} fl oz/acre**."
    )
    if seasonal_cap is not None:
        line += f" The label's seasonal maximum is {seasonal_cap:g} fl oz/acre."
    st.caption(line)


def _rows(pairs: tuple[tuple[str, Any], ...]) -> None:
    for label, value in pairs:
        left, right = st.columns([2, 3], vertical_alignment="top")
        left.caption(label)
        right.markdown(str(value))


def _trait(value: Any) -> str:
    """TraitPackage may arrive as the enum or as its value, depending on dump."""
    if value is None:
        return "—"
    raw = getattr(value, "value", value)
    return str(raw).replace("_", " ")


def _traits(values: Any) -> str:
    if values is None:
        return "No trait restriction"
    if not values:
        return "—"
    return ", ".join(_trait(value) for value in values)


def _stage_window(product: dict[str, Any]) -> str:
    earliest = product.get("earliest_growth_stage")
    latest = product.get("latest_growth_stage")
    exclusive = product.get("latest_growth_stage_exclusive")

    if latest:
        end = f"through {latest}"
    elif exclusive:
        end = f"up to but not including {exclusive}"
    else:
        end = None

    if earliest and end:
        return f"{earliest} {end}"
    if earliest:
        return f"from {earliest}"
    if end:
        return end.capitalize()
    return "No label limit"
