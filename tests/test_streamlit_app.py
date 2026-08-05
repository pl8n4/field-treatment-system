from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import data_layer.work_orders as work_orders


def test_streamlit_app_starts_with_empty_work_order_queue(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(work_orders, "DB_PATH", tmp_path / "work_orders.db")

    app = AppTest.from_file("app.py").run(timeout=30)

    assert not app.exception
    assert app.title[0].value == "Field Treatment System"
    assert [tab.label for tab in app.tabs] == [
        "Submit Request",
        "Work Order Queue",
    ]
    assert "thread_id" in app.session_state
    assert "workflow" in app.session_state
    assert "No work orders have been created yet." in [info.value for info in app.info]
