"""The simulated work-order queue.

A table rather than a list of expanders: the queue grows without bound, and an
expander per row stops being scannable after a handful of records.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from data_layer.work_orders import get_all_work_orders
from ui.components import facts

COLUMNS = {
    "work_order_id": st.column_config.TextColumn("Work order"),
    "field_id": st.column_config.TextColumn("Field"),
    "product_name": st.column_config.TextColumn("Product"),
    "treatment_date": st.column_config.TextColumn("Treatment date"),
    "proposed_rate": st.column_config.NumberColumn(
        "Rate", format="%.1f fl oz/ac", help="Application rate per acre"
    ),
    "treated_acres": st.column_config.NumberColumn("Acres", format="%.1f"),
    "created_at": st.column_config.DatetimeColumn("Created", format="YYYY-MM-DD HH:mm"),
}


def render() -> None:
    orders = get_all_work_orders()
    if not orders:
        st.info(
            "No work orders have been created yet.",
            icon=":material/inbox:",
        )
        return

    st.caption(f"{len(orders)} simulated record(s), newest first.")

    selection = st.dataframe(
        [{key: order.get(key) for key in COLUMNS} for order in orders],
        column_config=COLUMNS,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key="work_order_table",
    )

    rows = selection.get("selection", {}).get("rows", [])
    if not rows:
        st.caption("Select a row to see the full record.")
        return

    _render_detail(orders[rows[0]])


def _render_detail(order: dict[str, Any]) -> None:
    with st.container(border=True):
        st.markdown(f"**{order['work_order_id']}**")

        facts.grid(
            [
                ("Field", order["field_id"]),
                ("Product", order["product_name"]),
                ("Treatment date", str(order["treatment_date"])),
                ("Application rate", f"{order['proposed_rate']} fl oz/acre"),
                ("Treated area", f"{order['treated_acres']} acres"),
                ("Status", str(order["status"]).capitalize()),
            ],
            per_row=3,
        )

        st.caption(f"Created {order['created_at']} · thread {order['thread_id'][:8]}")
        st.caption(order["message"])
