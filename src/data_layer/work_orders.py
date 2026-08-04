import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from workflow.schemas import TreatmentPlan, WorkOrderResult

DB_PATH = Path(__file__).resolve().parents[2] / "work_orders.db"


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """
    Create the work_orders table if it doesn't exist.
    Call this once at application startup.
    """
    with _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS work_orders (
                work_order_id   TEXT PRIMARY KEY,
                thread_id       TEXT NOT NULL,
                field_id        TEXT NOT NULL,
                product_name    TEXT NOT NULL,
                treatment_date  TEXT NOT NULL,
                proposed_rate   REAL NOT NULL,
                treated_acres   REAL NOT NULL,
                status          TEXT NOT NULL DEFAULT 'simulated',
                created_at      TEXT NOT NULL,
                message         TEXT NOT NULL
            )
        """)


def create_work_order(plan: TreatmentPlan, thread_id: str) -> WorkOrderResult:
    """
    Write a simulated work order to the SQLite store.
    Only called after explicit human approval.
    """
    work_order_id = f"WO-{uuid.uuid4().hex[:8].upper()}"
    created_at = datetime.now(datetime.timezone.utc).isoformat()
    message = (
        "A simulated work-order record was created. "
        "No real treatment was scheduled."
    )

    with _get_connection() as conn:
        conn.execute("""
            INSERT INTO work_orders (
                work_order_id, thread_id, field_id, product_name,
                treatment_date, proposed_rate, treated_acres,
                status, created_at, message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            work_order_id,
            thread_id,
            plan.field_id,
            plan.product_name,
            plan.treatment_date.isoformat(),
            plan.proposed_rate,
            plan.treated_acres,
            "simulated",
            created_at,
            message,
        ))

    return WorkOrderResult(
        work_order_id=work_order_id,
        status="simulated",
        message=message,
    )


def get_all_work_orders() -> list[dict]:
    """
    Return all work orders for the Streamlit review queue.
    """
    with _get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM work_orders ORDER BY created_at DESC
        """).fetchall()
    return [dict(row) for row in rows]


def get_work_order(work_order_id: str) -> dict | None:
    """
    Return a single work order by ID.
    """
    with _get_connection() as conn:
        row = conn.execute("""
            SELECT * FROM work_orders WHERE work_order_id = ?
        """, (work_order_id,)).fetchone()
    return dict(row) if row else None