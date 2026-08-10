"""Label-and-value blocks for text facts.

``st.metric`` renders its value as a single large line that clips rather than
wraps, so a date or a product name like "Paraquat 43.2% SL" gets cut off. These
render at body size and wrap, which is what text facts need; metrics are left
for actual numbers.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

Pair = tuple[str, Any]


def grid(pairs: list[Pair] | tuple[Pair, ...], *, per_row: int = 3) -> None:
    """Facts laid out in a bordered card, wrapping onto as many rows as needed."""
    items = [pair for pair in pairs if pair[1] not in (None, "")]
    if not items:
        return

    with st.container(border=True):
        for start in range(0, len(items), per_row):
            chunk = items[start : start + per_row]
            columns = st.columns(per_row, vertical_alignment="top")
            # The final row is deliberately short, leaving empty columns.
            for column, (label, value) in zip(columns, chunk, strict=False):
                with column:
                    st.caption(label)
                    st.markdown(f"**{value}**")


def rows(pairs: list[Pair] | tuple[Pair, ...]) -> None:
    """Facts as a label/value list, for narrow columns."""
    for label, value in pairs:
        left, right = st.columns([2, 3], vertical_alignment="top")
        left.caption(label)
        right.markdown(str(value))
