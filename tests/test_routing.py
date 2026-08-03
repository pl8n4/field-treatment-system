import pytest

from data_layer.schemas import LabelChunk
from workflow.graph import AgriculturalWorkflow
from workflow.schemas import CriticDecision, RuleCheck, RuleEngineResult


@pytest.mark.parametrize(
    ("state", "expected_route"),
    [
        ({"error": "intake failed"}, "failure"),
        ({"missing_information": ["proposed_product"]}, "clarify"),
        ({"missing_information": []}, "gather_context"),
    ],
)
def test_route_after_intake(state: dict, expected_route: str) -> None:
    assert AgriculturalWorkflow._route_after_intake(state) == expected_route


@pytest.mark.parametrize(
    ("state", "expected_route"),
    [
        ({"error": "retrieval failed"}, "failure"),
        ({"evidence": []}, "clarify"),
        (
            {
                "evidence": [
                    LabelChunk(
                        text="Evidence",
                        source="label.pdf",
                        page=1,
                        product="Example Product",
                        epa_reg_no="00000-000",
                    )
                ]
            },
            "specialist",
        ),
    ],
)
def test_route_after_retrieval(state: dict, expected_route: str) -> None:
    assert AgriculturalWorkflow._route_after_retrieval(state) == expected_route


def critic_route_state(
    checks: list[RuleCheck],
    verdict: str,
    revision_count: int = 0,
    max_revisions: int = 1,
) -> dict:
    return {
        "rule_result": RuleEngineResult(
            checks=checks,
            all_passed=all(check.passed for check in checks),
        ),
        "review": CriticDecision(
            verdict=verdict,
            explanation="Test review.",
        ),
        "revision_count": revision_count,
        "max_revisions": max_revisions,
    }


def test_hard_rule_failure_routes_to_escalation() -> None:
    state = critic_route_state(
        [
            RuleCheck(
                rule_name="crop_compatibility",
                passed=False,
                severity="hard_violation",
                explanation="Crop is incompatible.",
            )
        ],
        verdict="hard_violation",
    )

    assert AgriculturalWorkflow._route_after_critic(state) == "escalate"


def test_fixable_failure_routes_to_specialist_when_revision_remains() -> None:
    state = critic_route_state(
        [
            RuleCheck(
                rule_name="wind",
                passed=False,
                severity="fixable",
                explanation="Wind is too high.",
            )
        ],
        verdict="fixable",
        revision_count=1,
        max_revisions=1,
    )

    assert AgriculturalWorkflow._route_after_critic(state) == "specialist"


def test_fixable_failure_escalates_after_revision_limit() -> None:
    state = critic_route_state(
        [
            RuleCheck(
                rule_name="wind",
                passed=False,
                severity="fixable",
                explanation="Wind is too high.",
            )
        ],
        verdict="fixable",
        revision_count=2,
        max_revisions=1,
    )

    assert AgriculturalWorkflow._route_after_critic(state) == "escalate"


def test_insufficient_information_routes_to_clarification() -> None:
    state = critic_route_state([], verdict="insufficient_info")

    assert AgriculturalWorkflow._route_after_critic(state) == "clarify"


def test_clean_review_routes_to_human_review() -> None:
    state = critic_route_state([], verdict="clean")

    assert AgriculturalWorkflow._route_after_critic(state) == "human_review"


@pytest.mark.parametrize(
    ("decision", "expected_route"),
    [
        ("approved", "write_work_order"),
        ("rejected", "rejected"),
    ],
)
def test_route_after_human_review(decision: str, expected_route: str) -> None:
    state = {"human_decision": decision}

    assert AgriculturalWorkflow._route_after_human_review(state) == expected_route
