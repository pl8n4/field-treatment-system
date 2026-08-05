from typing import Any
from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

import workflow.graph as graph_module
from data_layer.schemas import (
    Application,
    FarmField,
    LabelChunk,
    ProductLimits,
    WeatherForecast,
)
from workflow.graph import AgriculturalWorkflow, _stage_in_window
from workflow.schemas import CriticDecision, TreatmentRequest


class RaisingChain:
    def invoke(self, inputs: dict[str, Any]) -> None:
        del inputs
        raise RuntimeError("test boundary failed")


def test_content_to_text_handles_supported_content_shapes() -> None:
    assert AgriculturalWorkflow._content_to_text("plain text") == "plain text"
    assert (
        AgriculturalWorkflow._content_to_text([{"text": "first"}, {"other": "second"}])
        == "first {'other': 'second'}"
    )
    assert AgriculturalWorkflow._content_to_text(42) == "42"


def test_format_conversation_labels_human_and_assistant_messages() -> None:
    workflow = AgriculturalWorkflow.__new__(AgriculturalWorkflow)

    conversation = workflow._format_conversation(
        {
            "messages": [
                HumanMessage(content="request"),
                AIMessage(content="clarification"),
            ]
        }
    )

    assert conversation == "User: request\nAssistant: clarification"


def test_clarify_uses_review_issues_when_missing_list_is_empty() -> None:
    review = CriticDecision(
        verdict="insufficient_info",
        explanation="More evidence is required.",
        issues=["label evidence"],
    )

    update = AgriculturalWorkflow._clarify_node(
        {"missing_information": [], "review": review}
    )

    assert update["final_status"] == "needs_information"
    assert "label evidence" in update["final_message"]


def test_build_chat_model_configures_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor = Mock(return_value=object())
    monkeypatch.setattr(graph_module, "MODEL_PROVIDER", "ollama")
    monkeypatch.setattr(graph_module, "ChatOllama", constructor)

    AgriculturalWorkflow._build_chat_model()

    constructor.assert_called_once_with(
        model=graph_module.OLLAMA_MODEL,
        base_url=graph_module.OLLAMA_BASE_URL,
        temperature=0,
        num_predict=graph_module.MODEL_MAX_TOKENS,
    )


def test_build_chat_model_configures_gemini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor = Mock(return_value=object())
    monkeypatch.setattr(graph_module, "MODEL_PROVIDER", "gemini")
    monkeypatch.setattr(graph_module, "ChatGoogleGenerativeAI", constructor)

    AgriculturalWorkflow._build_chat_model()

    constructor.assert_called_once_with(
        model=graph_module.GEMINI_MODEL,
        max_tokens=graph_module.MODEL_MAX_TOKENS,
        temperature=0,
        max_retries=2,
    )


def test_context_exception_becomes_controlled_failure(
    monkeypatch: pytest.MonkeyPatch,
    treatment_request: TreatmentRequest,
) -> None:
    monkeypatch.setattr(
        graph_module,
        "find_field",
        Mock(side_effect=RuntimeError("records unavailable")),
    )

    update = AgriculturalWorkflow._gather_context_node({"request": treatment_request})

    assert update["error"] == "Context gathering failed: records unavailable"


def test_retrieval_exception_becomes_controlled_failure(
    monkeypatch: pytest.MonkeyPatch,
    treatment_request: TreatmentRequest,
    field_record: FarmField,
    product_record: ProductLimits,
) -> None:
    workflow = AgriculturalWorkflow.__new__(AgriculturalWorkflow)
    monkeypatch.setattr(
        graph_module,
        "search",
        Mock(side_effect=RuntimeError("vector store unavailable")),
    )

    update = workflow._retrieve_node(
        {
            "request": treatment_request,
            "field_record": field_record,
            "product_record": product_record,
        }
    )

    assert update["error"] == "Retrieval failed: vector store unavailable"


def test_retrieval_without_observed_issue_uses_standard_queries(
    monkeypatch: pytest.MonkeyPatch,
    treatment_request: TreatmentRequest,
    field_record: FarmField,
    product_record: ProductLimits,
    evidence: list[LabelChunk],
) -> None:
    workflow = AgriculturalWorkflow.__new__(AgriculturalWorkflow)
    request = treatment_request.model_copy(update={"observed_issue": None})
    search = Mock(return_value=evidence)
    monkeypatch.setattr(graph_module, "search", search)

    update = workflow._retrieve_node(
        {
            "request": request,
            "field_record": field_record,
            "product_record": product_record,
        }
    )

    assert update["error"] is None
    assert search.call_count == len(graph_module.EVIDENCE_QUERIES)


def test_specialist_exception_becomes_controlled_failure(
    treatment_request: TreatmentRequest,
    field_record: FarmField,
    product_record: ProductLimits,
    application_history: list[Application],
    weather: WeatherForecast,
    evidence: list[LabelChunk],
) -> None:
    workflow = AgriculturalWorkflow.__new__(AgriculturalWorkflow)
    workflow.specialist_chain = RaisingChain()

    update = workflow._specialist_node(
        {
            "request": treatment_request,
            "field_record": field_record,
            "product_record": product_record,
            "application_history": application_history,
            "weather": weather,
            "evidence": evidence,
        }
    )

    assert update["error"] == "Specialist failed: test boundary failed"


def test_rule_engine_exception_becomes_controlled_failure() -> None:
    update = AgriculturalWorkflow._rule_engine_node({})

    assert update["error"].startswith("Rule engine failed:")


@pytest.mark.parametrize(
    ("stage", "expected"),
    [
        ("V5", False),
        ("V6", True),
        ("R2", True),
        ("R3", False),
        ("unknown", False),
    ],
)
def test_stage_window_enforces_inclusive_bounds(
    product_record: ProductLimits,
    stage: str,
    expected: bool,
) -> None:
    assert _stage_in_window(stage, product_record) is expected


def test_stage_window_ignores_unrecognised_optional_bound(
    product_record: ProductLimits,
) -> None:
    product = product_record.model_copy(
        update={"earliest_growth_stage": "unrecognised"}
    )

    assert _stage_in_window("R2", product) is True
