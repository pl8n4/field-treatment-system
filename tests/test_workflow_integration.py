from collections import deque
from datetime import date
from typing import Any
from uuid import uuid4

import pytest

import workflow.graph as graph_module
from data_layer.schemas import LabelChunk, WeatherForecast
from data_layer.weather import WeatherUnavailable
from workflow.graph import AgriculturalWorkflow
from workflow.schemas import (
    CriticDecision,
    IntakeDecision,
    TreatmentPlan,
    TreatmentRequest,
)


class QueueChain:
    """Deterministic replacement for one structured-output model chain."""

    def __init__(self, *results: Any) -> None:
        self.results = deque(results)
        self.inputs: list[dict[str, Any]] = []

    def invoke(self, inputs: dict[str, Any]) -> Any:
        self.inputs.append(inputs)
        if not self.results:
            raise AssertionError("Fake chain received more calls than expected")
        return self.results.popleft()


def intake_decision(
    *,
    field_id: str = "F-02",
    product: str = "Enlist One",
    acres: float | None = 80,
    requested_rate: float | None = None,
) -> IntakeDecision:
    return IntakeDecision(
        request=TreatmentRequest(
            field_id=field_id,
            crop="soybean",
            observed_issue="weeds",
            proposed_product=product,
            proposed_date="2026-08-02",
            acres=acres,
            requested_rate=requested_rate,
        ),
        issue_type="weed",
        next_step="gather_context",
        routing_reason="All required request fields are present.",
    )


def treatment_plan(
    *,
    field_id: str = "F-02",
    product: str = "Enlist One",
    rate: float = 32,
    acres: float = 80,
) -> TreatmentPlan:
    return TreatmentPlan(
        field_id=field_id,
        product_name=product,
        treatment_date=date(2026, 8, 2),
        proposed_rate=rate,
        treated_acres=acres,
        timing_summary="Test treatment timing.",
        buffer_summary="Test buffer summary.",
        rei_summary="Test restricted-entry interval summary.",
        phi_summary="Test pre-harvest interval summary.",
        citations=["test-label.pdf, page 1"],
        human_review_required=True,
    )


def critic_decision(verdict: str = "clean") -> CriticDecision:
    return CriticDecision(
        verdict=verdict,
        explanation="Deterministic test review.",
        citations=["test-label.pdf, page 1"],
    )


def forecast() -> WeatherForecast:
    return WeatherForecast(
        latitude=39.2389,
        longitude=-92.3012,
        target_date=date(2026, 8, 2),
        high_temp_f=82,
        wind_speed_mph=8,
        wind_direction_deg=315,
        precipitation_probability_pct=20,
    )


def evidence_for(product: str) -> LabelChunk:
    return LabelChunk(
        text="Test product-label evidence.",
        product=product,
        epa_reg_no="62719-695",
        page=1,
        source="test-label.pdf",
    )


def build_workflow(
    monkeypatch: pytest.MonkeyPatch,
    *,
    intakes: list[IntakeDecision],
    plans: list[TreatmentPlan] | None = None,
    reviews: list[CriticDecision] | None = None,
) -> tuple[AgriculturalWorkflow, dict[type, QueueChain]]:
    chains = {
        IntakeDecision: QueueChain(*intakes),
        TreatmentPlan: QueueChain(*(plans or [])),
        CriticDecision: QueueChain(*(reviews or [])),
    }

    monkeypatch.setattr(
        AgriculturalWorkflow,
        "_build_chat_model",
        staticmethod(lambda: object()),
    )

    def fake_structured_chain(
        self: AgriculturalWorkflow,
        prompt: Any,
        schema: type,
    ) -> QueueChain:
        del self, prompt
        return chains[schema]

    monkeypatch.setattr(
        AgriculturalWorkflow,
        "_build_structured_chain",
        fake_structured_chain,
    )

    return AgriculturalWorkflow(), chains


def install_successful_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    retrieved_products: list[str] | None = None,
) -> None:
    monkeypatch.setattr(graph_module, "get_forecast", lambda *args: forecast())

    def fake_search(
        query: str,
        *,
        product: str | None = None,
        k: int = 4,
        **kwargs: Any,
    ) -> list[LabelChunk]:
        del query, k, kwargs
        assert product is not None
        if retrieved_products is not None:
            retrieved_products.append(product)
        return [evidence_for(product)]

    monkeypatch.setattr(graph_module, "search", fake_search)


@pytest.mark.parametrize(
    ("decision", "expected_status", "expects_work_order"),
    [
        ("approved", "simulated_work_order_created", True),
        ("rejected", "rejected", False),
    ],
)
def test_compiled_workflow_interrupt_and_resume(
    monkeypatch: pytest.MonkeyPatch,
    decision: str,
    expected_status: str,
    expects_work_order: bool,
) -> None:
    retrieved_products: list[str] = []
    install_successful_boundaries(monkeypatch, retrieved_products)
    workflow, chains = build_workflow(
        monkeypatch,
        intakes=[intake_decision(requested_rate=32)],
        plans=[treatment_plan()],
        reviews=[critic_decision()],
    )
    thread_id = str(uuid4())

    interrupted = workflow.start("Treat F-02 with Enlist One.", thread_id)

    assert interrupted.get("__interrupt__")
    assert interrupted["field_record"].id == "F-02"
    assert interrupted["product_record"].name == "Enlist One"
    assert interrupted["rule_result"].all_passed is True
    assert len(interrupted["rule_result"].checks) == 16
    assert interrupted["request"].acres == 80
    assert interrupted["request"].requested_rate == 32
    assert set(retrieved_products) == {"Enlist One"}
    assert "Enlist One" in chains[TreatmentPlan].inputs[0]["evidence"]

    completed = workflow.resume_human_review(decision, thread_id)

    assert completed["final_status"] == expected_status
    assert ("work_order" in completed) is expects_work_order
    if expects_work_order:
        assert completed["work_order"].status == "simulated"


def test_unknown_field_routes_to_clarification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow, _ = build_workflow(
        monkeypatch,
        intakes=[intake_decision(field_id="F-99")],
    )

    state = workflow.start("Treat unknown field F-99.", str(uuid4()))

    assert state["final_status"] == "needs_information"
    assert any("F-99" in item for item in state["missing_information"])
    assert "plan" not in state


def test_weather_failure_routes_to_clarification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow, _ = build_workflow(
        monkeypatch,
        intakes=[intake_decision()],
    )

    def unavailable(*args: Any) -> WeatherForecast:
        del args
        raise WeatherUnavailable("forecast unavailable for test")

    monkeypatch.setattr(graph_module, "get_forecast", unavailable)

    state = workflow.start("Treat F-02 with Enlist One.", str(uuid4()))

    assert state["final_status"] == "needs_information"
    assert "forecast unavailable for test" in state["missing_information"][0]
    assert "evidence" not in state


def test_context_uses_field_acres_and_product_default_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_successful_boundaries(monkeypatch)
    workflow, _ = build_workflow(
        monkeypatch,
        intakes=[intake_decision(acres=None, requested_rate=None)],
        plans=[treatment_plan(acres=96.5, rate=32)],
        reviews=[critic_decision()],
    )

    state = workflow.start("Treat F-02 with Enlist One.", str(uuid4()))

    assert state.get("__interrupt__")
    assert state["field_record"].acres == 96.5
    assert state["product_record"].default_rate_fl_oz_per_acre == 32
    assert state["request"].acres == 96.5
    assert state["request"].requested_rate == 32
    assert state["plan"].treated_acres == 96.5
    assert state["plan"].proposed_rate == 32


def test_requested_acres_above_field_size_routes_to_clarification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow, _ = build_workflow(
        monkeypatch,
        intakes=[intake_decision(acres=100)],
    )

    state = workflow.start("Treat 100 acres of F-02.", str(uuid4()))

    assert state["final_status"] == "needs_information"
    assert "100.0" in state["missing_information"][0]
    assert "96.5" in state["missing_information"][0]
    assert "plan" not in state


def test_missing_requested_and_default_rate_routes_to_clarification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product = graph_module.find_product("Enlist One")
    assert product is not None
    product_without_default = product.model_copy(
        update={"default_rate_fl_oz_per_acre": None}
    )
    monkeypatch.setattr(
        graph_module,
        "find_product",
        lambda name: product_without_default,
    )
    workflow, _ = build_workflow(
        monkeypatch,
        intakes=[intake_decision(requested_rate=None)],
    )

    state = workflow.start("Treat F-02 with Enlist One.", str(uuid4()))

    assert state["final_status"] == "needs_information"
    assert state["missing_information"] == ["An application rate for Enlist One"]
    assert "plan" not in state


def test_fixable_failure_revises_plan_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_successful_boundaries(monkeypatch)
    workflow, chains = build_workflow(
        monkeypatch,
        intakes=[intake_decision()],
        plans=[
            treatment_plan(rate=40),
            treatment_plan(rate=32),
        ],
        reviews=[
            critic_decision(),
            critic_decision(),
        ],
    )

    state = workflow.start("Treat F-02 with Enlist One.", str(uuid4()))

    assert state.get("__interrupt__")
    assert state["plan"].proposed_rate == 32
    assert state["revision_count"] == 1
    assert len(chains[TreatmentPlan].inputs) == 2
    assert "maximum_rate" in chains[TreatmentPlan].inputs[1]["previous_review"]


def test_hard_rule_failure_escalates_despite_clean_critic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_successful_boundaries(monkeypatch)
    workflow, _ = build_workflow(
        monkeypatch,
        intakes=[intake_decision(field_id="F-01", requested_rate=32)],
        plans=[treatment_plan(field_id="F-01")],
        reviews=[critic_decision("clean")],
    )

    state = workflow.start("Apply Enlist One to F-01.", str(uuid4()))

    assert state["final_status"] == "escalated"
    assert state["review"].verdict == "hard_violation"
    assert "trait_compatibility" in state["review"].issues
    assert "__interrupt__" not in state


def test_thread_ids_keep_checkpoint_state_isolated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_successful_boundaries(monkeypatch)
    workflow, _ = build_workflow(
        monkeypatch,
        intakes=[
            intake_decision(field_id="F-02", requested_rate=32),
            intake_decision(
                field_id="F-06",
                product="Roundup PowerMax 3",
                acres=77,
                requested_rate=32,
            ),
        ],
        plans=[
            treatment_plan(),
            treatment_plan(
                field_id="F-06",
                product="Roundup PowerMax 3",
                acres=77,
            ),
        ],
        reviews=[critic_decision(), critic_decision()],
    )

    first = workflow.start("First request.", str(uuid4()))
    second = workflow.start("Second request.", str(uuid4()))

    assert first.get("__interrupt__")
    assert second.get("__interrupt__")
    assert first["request"].field_id == "F-02"
    assert first["plan"].product_name == "Enlist One"
    assert second["request"].field_id == "F-06"
    assert second["plan"].product_name == "Roundup PowerMax 3"
