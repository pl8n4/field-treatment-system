from typing import Any

from data_layer.schemas import LabelChunk
from workflow.graph import AgriculturalWorkflow
from workflow.schemas import (
    CriticDecision,
    RuleCheck,
    RuleEngineResult,
    TreatmentPlan,
)


class FakeChain:
    def __init__(self, result: CriticDecision | Exception) -> None:
        self.result = result

    def invoke(self, inputs: dict[str, Any]) -> CriticDecision:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def workflow_with_review(
    review: CriticDecision | Exception,
) -> AgriculturalWorkflow:
    workflow = AgriculturalWorkflow.__new__(AgriculturalWorkflow)
    workflow.critic_chain = FakeChain(review)
    return workflow


def critic_state(
    treatment_plan: TreatmentPlan,
    evidence: list[LabelChunk],
    checks: list[RuleCheck],
    revision_count: int = 0,
) -> dict:
    return {
        "plan": treatment_plan,
        "evidence": evidence,
        "rule_result": RuleEngineResult(
            checks=checks,
            all_passed=all(check.passed for check in checks),
        ),
        "revision_count": revision_count,
    }


def test_critic_replaces_false_hard_violation_when_rules_pass(
    treatment_plan: TreatmentPlan,
    evidence: list[LabelChunk],
) -> None:
    workflow = workflow_with_review(
        CriticDecision(
            verdict="hard_violation",
            explanation="The model incorrectly reported a violation.",
        )
    )
    state = critic_state(
        treatment_plan,
        evidence,
        [
            RuleCheck(
                rule_name="crop_compatibility",
                passed=True,
                severity="hard_violation",
                explanation="Crop is compatible.",
            )
        ],
    )

    update = workflow._critic_node(state)

    assert update["review"].verdict == "clean"
    assert update["review"].citations == treatment_plan.citations
    assert "contradicted" in update["audit_log"][1]


def test_critic_replaces_clean_verdict_when_hard_rule_fails(
    treatment_plan: TreatmentPlan,
    evidence: list[LabelChunk],
) -> None:
    workflow = workflow_with_review(
        CriticDecision(
            verdict="clean",
            explanation="The model incorrectly reported a clean plan.",
        )
    )
    state = critic_state(
        treatment_plan,
        evidence,
        [
            RuleCheck(
                rule_name="crop_compatibility",
                passed=False,
                severity="hard_violation",
                explanation="Crop is incompatible.",
            )
        ],
    )

    update = workflow._critic_node(state)

    assert update["review"].verdict == "hard_violation"
    assert update["review"].issues == ["crop_compatibility"]


def test_critic_replaces_clean_verdict_when_fixable_rule_fails(
    treatment_plan: TreatmentPlan,
    evidence: list[LabelChunk],
) -> None:
    workflow = workflow_with_review(
        CriticDecision(
            verdict="clean",
            explanation="The model incorrectly reported a clean plan.",
        )
    )
    state = critic_state(
        treatment_plan,
        evidence,
        [
            RuleCheck(
                rule_name="wind",
                passed=False,
                severity="fixable",
                explanation="Wind exceeds the product maximum.",
            )
        ],
    )

    update = workflow._critic_node(state)

    assert update["review"].verdict == "fixable"
    assert update["review"].issues == ["wind"]
    assert update["revision_count"] == 1


def test_critic_converts_chain_exception_to_controlled_failure(
    treatment_plan: TreatmentPlan,
    evidence: list[LabelChunk],
) -> None:
    workflow = workflow_with_review(RuntimeError("model unavailable"))
    state = critic_state(treatment_plan, evidence, [])

    update = workflow._critic_node(state)

    assert update["error"] == "Critic failed: model unavailable"
    assert update["audit_log"] == ["Critic failed."]


def test_critic_preserves_matching_hard_violation(
    treatment_plan: TreatmentPlan,
    evidence: list[LabelChunk],
) -> None:
    model_review = CriticDecision(
        verdict="hard_violation",
        explanation="The crop is incompatible.",
        issues=["crop_compatibility"],
    )
    workflow = workflow_with_review(model_review)
    state = critic_state(
        treatment_plan,
        evidence,
        [
            RuleCheck(
                rule_name="crop_compatibility",
                passed=False,
                severity="hard_violation",
                explanation="Crop is incompatible.",
            )
        ],
    )

    update = workflow._critic_node(state)

    assert update["review"] == model_review
    assert "agreed" in update["audit_log"][1]


def test_critic_preserves_matching_fixable_verdict_and_counts_revision(
    treatment_plan: TreatmentPlan,
    evidence: list[LabelChunk],
) -> None:
    model_review = CriticDecision(
        verdict="fixable",
        explanation="The plan rate must be revised.",
        issues=["maximum_rate"],
    )
    workflow = workflow_with_review(model_review)
    state = critic_state(
        treatment_plan,
        evidence,
        [
            RuleCheck(
                rule_name="maximum_rate",
                passed=False,
                severity="fixable",
                explanation="Rate exceeds the maximum.",
            )
        ],
    )

    update = workflow._critic_node(state)

    assert update["review"] == model_review
    assert update["revision_count"] == 1
    assert "agreed" in update["audit_log"][1]
