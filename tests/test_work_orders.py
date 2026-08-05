import sqlite3
from pathlib import Path

import pytest

import data_layer.work_orders as work_orders
from workflow.schemas import TreatmentPlan


@pytest.fixture
def temporary_work_order_db(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    database_path = tmp_path / "work_orders.db"
    monkeypatch.setattr(work_orders, "DB_PATH", database_path)
    work_orders.init_db()
    return database_path


def test_init_db_creates_work_orders_table(
    temporary_work_order_db: Path,
) -> None:
    with sqlite3.connect(temporary_work_order_db) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("work_orders",),
        ).fetchone()

    assert table == ("work_orders",)


def test_create_and_get_work_order_persists_plan_and_thread(
    temporary_work_order_db: Path,
    treatment_plan: TreatmentPlan,
) -> None:
    del temporary_work_order_db

    result = work_orders.create_work_order(treatment_plan, "thread-123")
    stored = work_orders.get_work_order(result.work_order_id)

    assert result.status == "simulated"
    assert stored is not None
    assert stored["thread_id"] == "thread-123"
    assert stored["field_id"] == treatment_plan.field_id
    assert stored["product_name"] == treatment_plan.product_name
    assert stored["treatment_date"] == treatment_plan.treatment_date.isoformat()
    assert stored["proposed_rate"] == treatment_plan.proposed_rate
    assert stored["treated_acres"] == treatment_plan.treated_acres
    assert stored["status"] == "simulated"
    assert stored["created_at"]


def test_get_work_order_returns_none_for_unknown_id(
    temporary_work_order_db: Path,
) -> None:
    del temporary_work_order_db

    assert work_orders.get_work_order("WO-UNKNOWN") is None


def test_work_order_ids_are_unique_and_newest_is_returned_first(
    temporary_work_order_db: Path,
    treatment_plan: TreatmentPlan,
) -> None:
    del temporary_work_order_db

    first = work_orders.create_work_order(treatment_plan, "thread-1")
    second = work_orders.create_work_order(treatment_plan, "thread-2")

    orders = work_orders.get_all_work_orders()

    assert first.work_order_id != second.work_order_id
    assert [order["work_order_id"] for order in orders] == [
        second.work_order_id,
        first.work_order_id,
    ]
